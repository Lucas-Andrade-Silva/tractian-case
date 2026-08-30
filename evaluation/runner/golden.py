"""Carregamento do golden set — o ÚNICO módulo que lê `eval/`.

Concentrar essa leitura num só lugar é o que torna verificável a regra de separação do
projeto: o agente nunca importa daqui, e qualquer vazamento do gabarito para o contexto
do agente apareceria como um import deste módulo dentro de `agent/`.

## Por que existe a tabela de resoluções aceitas

`eval/expected-paths.json` traz a trajetória esperada, mas NÃO traz a resolução esperada
(orientar/agir/escalar). Derivá-la da trajetória — "terminou em POST /escalate, logo
escalar" — funciona para os cenários inequívocos e falha nos demais, porque vários
cenários declaram explicitamente MAIS DE UMA resolução aceitável:

- CEN-06 (TKT-INV-08): "investigar → agir/escalar"
- CEN-09 (TKT-INV-11): "investigar → agir/escalar", com o `POST request-retraining`
  marcado como "(Opcional)" na própria trajetória
- CEN-03 (TKT-INV-06) e CEN-08 (TKT-INV-10): "investigar → orientar/escalar"

Nesses casos a trajetória do gabarito é só de consultas, e a derivação automática diria
"orientar" — reprovando um agente que agiu ou escalou, exatamente o que o cenário
autoriza. A tabela abaixo transcreve o campo "Resolução esperada" de cada cenário de
`docs/test-scenarios.md`, que é a fonte declarada dessa informação.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_PATH = REPO_ROOT / "eval" / "expected-paths.json"

DecisionKind = Literal["orientar", "agir", "escalar"]

_ESCALATE_MARKER = "/escalate"
_ACTION_MARKERS = ("/reprocess", "/request-specialist", "/request-retraining")

# Resoluções aceitas por caso, transcritas de "Resolução esperada" em
# docs/test-scenarios.md. Um conjunto com mais de um elemento significa que o cenário
# admite mais de um desfecho correto — e a avaliação não pode punir a escolha entre eles.
ACCEPTED_DECISIONS: dict[str, frozenset[str]] = {
    "case_tkt_inv_04": frozenset({"escalar"}),              # CEN-01 investigar → explicar + escalar
    "case_tkt_inv_05": frozenset({"agir"}),                 # CEN-02 investigar → agir
    "case_tkt_inv_06": frozenset({"orientar", "escalar"}),  # CEN-03 investigar → orientar/escalar
    "case_tkt_inv_11b": frozenset({"orientar", "agir"}),    # CEN-04 orientar + agir (recomendar)
    "case_tkt_inv_07": frozenset({"orientar"}),             # CEN-05 investigar → orientar
    "case_tkt_inv_08": frozenset({"agir", "escalar"}),      # CEN-06 investigar → agir/escalar
    "case_tkt_inv_09": frozenset({"agir"}),                 # CEN-07 investigar → agir
    "case_tkt_exe_12": frozenset({"agir"}),                 # CEN-07 (execução) → agir
    "case_tkt_inv_10": frozenset({"orientar", "escalar"}),  # CEN-08 investigar → orientar/escalar
    "case_tkt_inv_11": frozenset({"agir", "escalar"}),      # CEN-09 investigar → agir/escalar
    "case_tkt_exe_16": frozenset({"escalar"}),              # CEN-10 executar → escalar
    "case_tkt_ctx_01": frozenset({"orientar"}),             # CEN-11 contextualizar → orientar
    "case_tkt_ctx_02": frozenset({"orientar"}),             # CEN-12 contextualizar → orientar
    "case_tkt_ctx_03": frozenset({"orientar"}),             # CEN-13 contextualizar → orientar
    "case_tkt_exe_13": frozenset({"agir"}),                 # CEN-14 executar → agir (especialista)
    "case_tkt_exe_14": frozenset({"agir"}),                 # CEN-15 executar → agir
    "case_tkt_exe_15": frozenset({"agir", "escalar"}),      # CEN-16 executar → agir/escalar
}


@dataclass(frozen=True)
class GoldenCase:
    """Um item do gabarito, com as resoluções aceitas pelo cenário correspondente."""

    case_id: str
    ticket_id: str
    root_question: str
    mode: str
    expected_path: list[str]
    expected_notes: dict[str, str]

    @property
    def accepted_decisions(self) -> frozenset[str]:
        """Resoluções que o cenário aceita. Cai na derivação por trajetória se não mapeado
        (útil para cenários do holdout, que não estão na tabela)."""
        mapped = ACCEPTED_DECISIONS.get(self.case_id)
        return mapped if mapped else frozenset({self._decision_from_trajectory()})

    @property
    def is_ambiguous(self) -> bool:
        """O cenário admite mais de um desfecho correto?"""
        return len(self.accepted_decisions) > 1

    def _decision_from_trajectory(self) -> DecisionKind:
        """Fallback: infere a resolução pela ação que fecha a trajetória do gabarito."""
        for step in self.expected_path:
            if _ESCALATE_MARKER in step:
                return "escalar"
        for step in self.expected_path:
            if step.startswith("PATCH ") or any(m in step for m in _ACTION_MARKERS):
                return "agir"
        return "orientar"

    @property
    def expected_actions(self) -> list[str]:
        """Ações de impacto (POST/PATCH) que aparecem na trajetória do gabarito."""
        return [s for s in self.expected_path if s.startswith(("POST ", "PATCH "))]

    @property
    def required_actions(self) -> list[str]:
        """Ações que o agente PRECISA executar para o cenário ser considerado resolvido.

        Só são exigidas quando o cenário tem uma única resolução aceita e ela implica
        executar algo. Havendo mais de um desfecho válido, a ação passa a ser opcional —
        é o caso de CEN-09, onde o próprio cenário marca o retreinamento como opcional.
        """
        if self.is_ambiguous:
            return []
        return self.expected_actions

    @property
    def allowed_actions(self) -> set[str]:
        """Ações de impacto que NÃO devem ser contadas como indevidas.

        Inclui as da trajetória do gabarito e, quando o cenário aceita 'escalar', o
        escalonamento deste caso — que por definição não aparece numa trajetória de
        referência que optou por outro desfecho.
        """
        allowed = set(self.expected_actions)
        if "escalar" in self.accepted_decisions:
            allowed.add(f"POST /cases/{self.case_id}/escalate")
        return allowed

    @property
    def expected_queries(self) -> list[str]:
        """Passos de consulta (GET) esperados — a apuração de evidência."""
        return [s for s in self.expected_path if s.startswith("GET ")]


def load_golden(path: Path | None = None) -> dict[str, GoldenCase]:
    """Carrega o gabarito indexado por `case_id`."""
    raw: list[dict[str, Any]] = json.loads((path or GOLDEN_PATH).read_text(encoding="utf-8"))
    cases: dict[str, GoldenCase] = {}
    for entry in raw:
        steps = entry.get("expected_path", [])
        cases[entry["id"]] = GoldenCase(
            case_id=entry["id"],
            ticket_id=entry.get("ticket_id", ""),
            root_question=entry.get("root_question", ""),
            mode=entry.get("mode", ""),
            expected_path=[s["step"] for s in steps],
            expected_notes={s["step"]: s.get("note", "") for s in steps},
        )
    return cases
