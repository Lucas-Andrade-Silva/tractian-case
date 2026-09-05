"""Camada 1 da pirâmide — avaliação determinística (ADR 0005).

Roda primeiro porque é gratuita e instantânea: filtra o que dá para julgar por código
antes de gastar chamadas de LLM nas camadas seguintes.

Julga trajetória como *referência*, não como script rígido: a ordem pode variar sem
penalidade, porque um bom agente pode investigar numa sequência diferente e ainda assim
sustentar a conclusão. O que é cobrado com rigor é o que tem consequência — a resolução
final e as ações de impacto executadas.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .golden import GoldenCase


class DeterministicResult(BaseModel):
    """Métricas objetivas de uma execução contra o gabarito."""

    case_id: str
    seed: str | None
    executed: bool = Field(description="A execução chegou ao fim sem quebrar?")
    execution_error: str | None = None

    decision: str | None = None
    accepted_decisions: list[str] = Field(
        default_factory=list, description="Resoluções que o cenário admite como corretas."
    )
    ambiguous_scenario: bool = Field(
        default=False, description="O cenário aceita mais de um desfecho — a escolha não é penalizada."
    )
    decision_match: bool = False

    evidence_recall: float = Field(
        default=0.0, description="Fração das consultas do gabarito que o agente também fez."
    )
    missing_queries: list[str] = Field(default_factory=list)
    extra_queries: list[str] = Field(default_factory=list)

    required_actions: list[str] = Field(
        default_factory=list, description="Ações exigidas pelo cenário (vazio se o desfecho é ambíguo)."
    )
    executed_actions: list[str] = Field(default_factory=list)
    missing_actions: list[str] = Field(default_factory=list)
    unexpected_actions: list[str] = Field(default_factory=list)

    num_calls: int = 0
    repeated_calls: int = Field(default=0, description="Chamadas idênticas repetidas.")
    repetition_rate: float = 0.0

    http_errors: int = 0
    retried_after_error: list[str] = Field(
        default_factory=list,
        description="Chamadas repetidas após já terem sido rejeitadas — insistir no erro.",
    )

    justification_present: bool = False
    justification_length: int = 0

    @property
    def passed(self) -> bool:
        """Aprovação da camada determinística.

        Exige o que tem consequência real: executou, decidiu como esperado, realizou as
        ações de impacto previstas e não executou nenhuma ação não prevista.
        """
        return (
            self.executed
            and self.decision_match
            and not self.missing_actions
            and not self.unexpected_actions
        )


def evaluate_deterministic(trace: dict[str, Any], golden: GoldenCase) -> DeterministicResult:
    """Compara um trace do agente com o item correspondente do gabarito."""
    path_taken: list[str] = trace.get("path_taken", [])
    steps: list[dict[str, Any]] = trace.get("steps", [])

    queries_taken = [s for s in path_taken if s.startswith("GET ")]
    actions_taken = [s for s in path_taken if s.startswith(("POST ", "PATCH "))]

    expected_queries = golden.expected_queries

    # Consultas: comparadas como conjuntos — a ordem é livre por design.
    taken_set = set(queries_taken)
    hit = [q for q in expected_queries if q in taken_set]
    recall = len(hit) / len(expected_queries) if expected_queries else 1.0

    # Ações de impacto: comparadas ignorando o corpo, mas exigindo o mesmo alvo.
    executed_set = set(actions_taken)
    required_actions = golden.required_actions

    decision = trace.get("decision")
    justification = trace.get("justification") or ""

    repeated = _count_repeats(path_taken)
    error_steps = [s for s in steps if not s.get("ok")]

    return DeterministicResult(
        case_id=trace.get("case_id", golden.case_id),
        seed=trace.get("seed"),
        executed=trace.get("error") is None,
        execution_error=trace.get("error"),
        decision=decision,
        accepted_decisions=sorted(golden.accepted_decisions),
        ambiguous_scenario=golden.is_ambiguous,
        decision_match=decision in golden.accepted_decisions,
        evidence_recall=round(recall, 3),
        missing_queries=[q for q in expected_queries if q not in taken_set],
        extra_queries=sorted(taken_set - set(expected_queries)),
        required_actions=required_actions,
        executed_actions=actions_taken,
        missing_actions=sorted(set(required_actions) - executed_set),
        unexpected_actions=sorted(executed_set - golden.allowed_actions),
        num_calls=len(path_taken),
        repeated_calls=repeated,
        repetition_rate=round(repeated / len(path_taken), 3) if path_taken else 0.0,
        http_errors=len(error_steps),
        retried_after_error=_retries_after_error(steps),
        justification_present=bool(justification.strip()),
        justification_length=len(justification.strip()),
    )


def _count_repeats(path: list[str]) -> int:
    """Quantas chamadas são repetição exata de uma anterior."""
    seen: set[str] = set()
    repeats = 0
    for step in path:
        if step in seen:
            repeats += 1
        seen.add(step)
    return repeats


def _retries_after_error(steps: list[dict[str, Any]]) -> list[str]:
    """Chamadas refeitas depois de já terem sido rejeitadas pela API.

    Insistir numa chamada já recusada (ex.: repetir uma ação após 403) é o padrão de
    falha que interessa medir: o agente ignorou o retorno em vez de tratá-lo.
    """
    failed: set[str] = set()
    offenders: list[str] = []
    for step in steps:
        label = step.get("step", "")
        if label in failed and label not in offenders:
            offenders.append(label)
        if not step.get("ok"):
            failed.add(label)
    return offenders
