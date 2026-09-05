"""Trace estruturado local — fonte de verdade da Parte 2 (ADR 0004).

Formato alinhado ao golden set (`eval/expected-paths.json`): cada passo tem um campo
`step` na forma `"GET /assets/asset_G501"`, idêntico ao usado no gabarito, para que a
camada determinística da avaliação compare trajetórias sem tradução de formato.

Além do `step`, guardamos os componentes separados (`method`, `path`, `query`) e qual
papel fez a chamada — consequência aceita no ADR 0001: com múltiplos agentes, saber
*quem* chamou é parte do que a avaliação precisa inspecionar.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceStep:
    """Uma chamada à API industrial, como ela de fato aconteceu."""

    step: str  # "GET /assets/asset_G501?status=pending" — formato do golden set
    method: str
    path: str
    query: dict[str, Any]
    agent: str  # qual papel fez a chamada (supervisor/investigador/...)
    status_code: int
    ok: bool
    mode: str | None  # envelope probabilístico: complete|partial|inconclusive|...
    notes: str | None
    error: str | None
    latency_ms: int
    at: str
    body: dict[str, Any] | None = None  # payload enviado em ações (POST/PATCH)
    response: Any = None  # `data` do envelope, ou corpo do erro
    # Consulta que o agente repetiu e foi servida do cache da execução. Fica registrada
    # para a avaliação continuar medindo a repetição como desperdício de raciocínio,
    # ainda que o custo de rede e de tokens tenha sido evitado.
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "method": self.method,
            "path": self.path,
            "query": self.query,
            "agent": self.agent,
            "status_code": self.status_code,
            "ok": self.ok,
            "mode": self.mode,
            "notes": self.notes,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "at": self.at,
            "body": self.body,
            "response": self.response,
            "from_cache": self.from_cache,
        }


@dataclass
class LlmCall:
    """Consumo de uma chamada ao LLM.

    Registrado por papel porque o custo de um agente multiagente não é uniforme: saber
    que o Investigador consome N vezes mais que o Supervisor é o que permite dimensionar
    uma rodada e justificar (ou refutar) a escolha de arquitetura do ADR 0001.
    """

    agent: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "at": self.at,
        }


@dataclass
class Trace:
    """Registro completo de uma execução do agente sobre um caso."""

    case_id: str
    ticket_id: str
    seed: str | None
    user_id: str
    asset_id: str | None
    message: str
    model: str = ""
    started_at: str = field(default_factory=_now)
    steps: list[TraceStep] = field(default_factory=list)
    llm_calls: list[LlmCall] = field(default_factory=list)
    # Preenchidos pelos nós do grafo ao longo da execução.
    routing: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    decision: str | None = None
    justification: str | None = None
    final_answer: str | None = None
    stop_reason: str | None = None
    error: str | None = None
    finished_at: str | None = None

    # -- registro ---------------------------------------------------------
    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def add_routing(self, *, turn: int, source: str, target: str, reason: str | None) -> None:
        """Registra uma decisão de roteamento (quem o Supervisor acionou e por quê)."""
        self.routing.append(
            {"turn": turn, "from": source, "to": target, "reason": reason, "at": _now()}
        )

    def add_finding(self, *, agent: str, summary: str) -> None:
        """Resumo que um papel worker produz ao encerrar sua apuração."""
        self.findings.append({"agent": agent, "summary": summary, "at": _now()})

    def add_llm_call(self, *, agent: str, response: Any) -> None:
        """Extrai o consumo de tokens de uma resposta do LLM, se o provedor informar.

        Silencioso quando o provedor não devolve `usage_metadata`: a ausência da métrica
        não pode interromper o atendimento do caso.
        """
        usage = getattr(response, "usage_metadata", None) or {}
        if not usage:
            return
        self.llm_calls.append(
            LlmCall(
                agent=agent,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
            )
        )

    @property
    def token_usage(self) -> dict[str, Any]:
        """Consumo agregado da execução, com a quebra por papel."""
        by_agent: dict[str, dict[str, int]] = {}
        for call in self.llm_calls:
            slot = by_agent.setdefault(
                call.agent, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            )
            slot["calls"] += 1
            slot["input_tokens"] += call.input_tokens
            slot["output_tokens"] += call.output_tokens
            slot["total_tokens"] += call.total_tokens

        return {
            "llm_calls": len(self.llm_calls),
            "input_tokens": sum(c.input_tokens for c in self.llm_calls),
            "output_tokens": sum(c.output_tokens for c in self.llm_calls),
            "total_tokens": sum(c.total_tokens for c in self.llm_calls),
            "by_agent": by_agent,
        }

    def close(
        self,
        *,
        decision: str | None,
        justification: str | None,
        final_answer: str | None,
        stop_reason: str,
        error: str | None = None,
    ) -> None:
        self.decision = decision
        self.justification = justification
        self.final_answer = final_answer
        self.stop_reason = stop_reason
        self.error = error
        self.finished_at = _now()

    # -- serialização -----------------------------------------------------
    @property
    def path_taken(self) -> list[str]:
        """Só a sequência de `step`s — o que a Parte 2 compara com `expected_path`."""
        return [s.step for s in self.steps]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "ticket_id": self.ticket_id,
            "seed": self.seed,
            "user_id": self.user_id,
            "asset_id": self.asset_id,
            "message": self.message,
            "model": self.model,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "decision": self.decision,
            "justification": self.justification,
            "final_answer": self.final_answer,
            "stop_reason": self.stop_reason,
            "error": self.error,
            "path_taken": self.path_taken,
            "token_usage": self.token_usage,
            "steps": [s.to_dict() for s in self.steps],
            "llm_calls": [c.to_dict() for c in self.llm_calls],
            "routing": self.routing,
            "findings": self.findings,
        }

    def save(self, directory: Path, filename: str | None = None) -> Path:
        """Grava o trace como JSON. Um arquivo por execução, para não perder histórico."""
        directory.mkdir(parents=True, exist_ok=True)
        stamp = self.started_at.replace(":", "").replace("-", "").replace(".", "")[:15]
        name = filename or f"{self.case_id}__seed-{self.seed or 'none'}__{stamp}.json"
        target = directory / name
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return target
