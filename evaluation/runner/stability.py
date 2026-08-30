"""Camada 3 da pirâmide — estabilidade entre seeds (ADR 0005).

Um cenário é instável apenas se a RESOLUÇÃO FINAL divergir entre execuções. Variação de
trajetória não conta: o agente pode investigar em ordens diferentes e chegar à mesma
conclusão — isso é comportamento esperado, não defeito.

A distinção importa porque medir instabilidade pela trajetória produziria um número alto
e sem significado, escondendo o que de fato compromete confiabilidade: o mesmo caso
sendo ora orientado, ora escalado.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, Field


class StabilityResult(BaseModel):
    """Consistência da resolução de um caso ao longo de várias execuções."""

    case_id: str
    runs: int
    decisions: list[str | None]
    distinct_decisions: list[str]
    majority_decision: str | None
    agreement_rate: float = Field(description="Fração das execuções que ficaram na decisão majoritária.")
    stable: bool
    trajectory_variation: float = Field(
        description="Variação de trajetória entre execuções — reportada, não penalizada."
    )


def evaluate_stability(traces: list[dict[str, Any]]) -> StabilityResult:
    """Agrega execuções do MESMO caso (seeds diferentes) num veredito de estabilidade."""
    if not traces:
        raise ValueError("evaluate_stability precisa de ao menos uma execução")

    case_id = traces[0].get("case_id", "")
    decisions = [t.get("decision") for t in traces]
    counts = Counter(d for d in decisions if d is not None)

    majority, majority_count = (counts.most_common(1)[0] if counts else (None, 0))
    agreement = majority_count / len(decisions) if decisions else 0.0

    # Trajetória: quantos conjuntos de chamadas distintos apareceram.
    trajectories = {tuple(sorted(set(t.get("path_taken", [])))) for t in traces}
    variation = (len(trajectories) - 1) / (len(traces) - 1) if len(traces) > 1 else 0.0

    return StabilityResult(
        case_id=case_id,
        runs=len(traces),
        decisions=decisions,
        distinct_decisions=sorted(counts),
        majority_decision=majority,
        agreement_rate=round(agreement, 3),
        # Estável = uma única resolução em todas as execuções bem-sucedidas.
        stable=len(counts) <= 1,
        trajectory_variation=round(variation, 3),
    )
