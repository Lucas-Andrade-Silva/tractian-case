"""Cliente HTTP da API industrial — único ponto de saída do agente para o mundo.

Toda chamada passa por aqui, e é aqui que o trace é gravado: o que o LLM *diz* que fez
não é fonte de verdade; o que saiu neste cliente é.

Erros HTTP (403 sem permissão, 400 justificativa fraca, 404) **não** viram exceção. São
devolvidos como resultado estruturado para o agente ler e reagir — o enforcement de
permissão é da API, não de um bloqueio prévio em código (ADR 0003). Bloquear antes
eliminaria justamente o comportamento que CEN-14/15/16 avaliam.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .trace import Trace, TraceStep


class ApiClient:
    """Wrapper HTTP com trace embutido e contexto de usuário/seed da execução."""

    def __init__(
        self,
        *,
        base_url: str,
        user_id: str,
        trace: Trace,
        seed: str | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.seed = seed
        self.trace = trace
        # Qual papel está chamando agora; os nós do grafo atualizam antes de agir.
        self.current_agent = "supervisor"
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_s,
            headers={"x-user-id": user_id},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- núcleo -----------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        with_seed: bool = True,
    ) -> dict[str, Any]:
        """Executa a chamada, registra no trace e devolve um resultado uniforme.

        O retorno é sempre um dict com `ok`; nunca levanta por status HTTP.
        """
        params = {k: v for k, v in (query or {}).items() if v is not None}
        # O seed vale só para GETs de consulta (é o que a API varia probabilisticamente).
        if with_seed and self.seed and method == "GET":
            params["seed"] = self.seed

        started = time.perf_counter()
        status_code = 0
        error: str | None = None
        payload: Any = None
        try:
            response = self._http.request(method, path, params=params, json=body)
            status_code = response.status_code
            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text}
        except httpx.HTTPError as exc:  # timeout, conexão recusada, DNS...
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = int((time.perf_counter() - started) * 1000)

        result = self._interpret(status_code, payload, error)
        self.trace.add_step(
            TraceStep(
                step=_step_label(method, path, params),
                method=method,
                path=path,
                query={k: v for k, v in params.items() if k != "seed"},
                agent=self.current_agent,
                status_code=status_code,
                ok=result["ok"],
                mode=result.get("mode"),
                notes=result.get("notes"),
                error=result.get("error"),
                latency_ms=latency_ms,
                at=_iso_now(),
                body=body,
                response=result.get("data") if result["ok"] else payload,
            )
        )
        return result

    @staticmethod
    def _interpret(status_code: int, payload: Any, error: str | None) -> dict[str, Any]:
        """Traduz a resposta crua num resultado que o agente consegue interpretar."""
        if error:
            return {"ok": False, "error": error, "error_kind": "transport", "status_code": 0}

        if 200 <= status_code < 300:
            # GETs de consulta vêm no envelope {mode, notes, data}; ações vêm cruas.
            if isinstance(payload, dict) and "mode" in payload and "data" in payload:
                return {
                    "ok": True,
                    "status_code": status_code,
                    "mode": payload.get("mode"),
                    "notes": payload.get("notes"),
                    "data": payload.get("data"),
                }
            return {"ok": True, "status_code": status_code, "mode": None, "data": payload}

        code = payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("message") if isinstance(payload, dict) else str(payload)
        return {
            "ok": False,
            "status_code": status_code,
            "error": message or f"HTTP {status_code}",
            "error_kind": (code or "").lower() or f"http_{status_code}",
            "data": payload,
        }

    # -- atalhos ----------------------------------------------------------
    def get(self, path: str, **query: Any) -> dict[str, Any]:
        return self.request("GET", path, query=query)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, body=body, with_seed=False)

    def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.request("PATCH", path, body=body, with_seed=False)


def _step_label(method: str, path: str, params: dict[str, Any]) -> str:
    """Monta o rótulo do passo no formato do golden set.

    O `seed` fica de fora de propósito: ele é um artefato de reprodutibilidade da
    avaliação, não uma escolha de investigação do agente, e o gabarito não o inclui.
    """
    meaningful = {k: v for k, v in params.items() if k != "seed"}
    if not meaningful:
        return f"{method} {path}"
    query = "&".join(f"{k}={v}" for k, v in sorted(meaningful.items()))
    return f"{method} {path}?{query}"


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
