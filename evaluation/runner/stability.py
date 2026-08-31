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
from typing import Any  # noqa: F401  (usado nas anotações de evaluate_stability)

from pydantic import BaseModel, Field


class StabilityResult(BaseModel):
    """Consistência da resolução de um caso ao longo de várias execuções."""

    case_id: str
    runs: int
    successful_runs: int = Field(
        description="Execuções que produziram uma resolução; só elas podem ser comparadas."
    )
    decisions: list[str | None]
    distinct_decisions: list[str]
    majority_decision: str | None
    agreement_rate: float | None = Field(
        description="Fração das execuções bem-sucedidas na decisão majoritária. None se nada concluiu."
    )
    measurable: bool = Field(
        description="Houve ao menos uma execução bem-sucedida? Sem isso, estabilidade não é medível."
    )
    stable: bool | None = Field(
        description="None quando não medível — 'não concluiu nada' não é o mesmo que 'concluiu sempre igual'."
    )
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
    successful = sum(counts.values())

    majority, majority_count = (counts.most_common(1)[0] if counts else (None, 0))
    # A concordância é sobre o que de fato concluiu. Dividir pelo total de execuções
    # misturaria "divergiu" com "quebrou", que são falhas diferentes.
    agreement = majority_count / successful if successful else None

    # Trajetória: quantos conjuntos de chamadas distintos apareceram.
    trajectories = {tuple(sorted(set(t.get("path_taken", [])))) for t in traces}
    variation = (len(trajectories) - 1) / (len(traces) - 1) if len(traces) > 1 else 0.0

    return StabilityResult(
        case_id=case_id,
        runs=len(traces),
        successful_runs=successful,
        decisions=decisions,
        distinct_decisions=sorted(counts),
        majority_decision=majority,
        agreement_rate=round(agreement, 3) if agreement is not None else None,
        measurable=successful > 0,
        # Estável = uma única resolução entre as execuções bem-sucedidas. Sem nenhuma
        # execução bem-sucedida não há o que comparar: o resultado é "não medido", e
        # tratá-lo como estável reportaria 100% de estabilidade num agente que só falhou.
        stable=(len(counts) <= 1) if successful else None,
        trajectory_variation=round(variation, 3),
    )
