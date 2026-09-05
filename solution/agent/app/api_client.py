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
        # Cache de consultas desta execução. O prompt pede que o agente não repita
        # chamadas, mas prompt não é garantia: um GET repetido custa uma volta inteira de
        # LLM (~1.900 tokens de prompt + schemas) para devolver um dado já conhecido.
        # Ações (POST/PATCH) nunca entram aqui — repeti-las tem efeito real.
        self._query_cache: dict[str, dict[str, Any]] = {}
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

        label = _step_label(method, path, params)

        # Consulta repetida: devolve o resultado já obtido em vez de gastar a chamada.
        # O passo é registrado no trace com `from_cache=True`, para que a avaliação
        # continue vendo que o agente pediu o dado duas vezes — o desperdício de
        # raciocínio é medido, só o custo de rede e de tokens é que é evitado.
        if method == "GET" and label in self._query_cache:
            cached = self._query_cache[label]
            self.trace.add_step(
                TraceStep(
                    step=label,
                    method=method,
                    path=path,
                    query={k: v for k, v in params.items() if k != "seed"},
                    agent=self.current_agent,
                    status_code=cached.get("status_code", 200),
                    ok=cached["ok"],
                    mode=cached.get("mode"),
                    notes=cached.get("notes"),
                    error=cached.get("error"),
                    latency_ms=0,
                    at=_iso_now(),
                    body=None,
                    response=cached.get("data"),
                    from_cache=True,
                )
            )
            return {
                **cached,
                "notes": _repeat_note(cached.get("notes")),
            }

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
        # Só consultas bem-sucedidas entram no cache: um erro pode ser transitório, e
        # cachear falha impediria o agente de tentar de novo legitimamente.
        if method == "GET" and result.get("ok"):
            self._query_cache[label] = result
        self.trace.add_step(
            TraceStep(
                step=label,
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


def _repeat_note(notes: str | None) -> str:
    """Avisa o agente, na própria resposta, que ele já tinha pedido este dado."""
    aviso = (
        "Esta consulta já havia sido feita nesta investigação; o resultado é o mesmo. "
        "Não repita consultas — use a evidência já obtida e siga para a conclusão."
    )
    return f"{notes} | {aviso}" if notes else aviso


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
