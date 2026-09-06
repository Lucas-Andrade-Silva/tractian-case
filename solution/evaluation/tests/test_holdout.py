"""Testes do holdout sintético (ADR 0006).

Verificam as propriedades que fazem o holdout ser um teste de generalização, e não uma
segunda passada pelos mesmos casos: ativos disjuntos dos originais, cenários íntegros e
auditados mecanicamente contra a API real.
"""
from __future__ import annotations

import httpx
import pytest

from runner.deterministic import evaluate_deterministic
from runner.golden import load_golden
from runner.holdout import audit_holdout, load_holdout, load_holdout_cases

BASE_URL = "http://localhost:8000"

HOLDOUT = load_holdout()
CASES = {c["id"]: c for c in load_holdout_cases()}
GOLDEN = load_golden()


def _api_is_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/docs", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


# -- integridade do conjunto ------------------------------------------------
def test_cases_and_expectations_are_paired():
    assert set(CASES) == set(HOLDOUT)
    assert len(HOLDOUT) == 8


def test_holdout_does_not_overlap_the_development_set():
    """Um holdout que reusa os casos de desenvolvimento não mede generalização."""
    assert set(HOLDOUT).isdisjoint(GOLDEN)


def test_holdout_uses_assets_untouched_by_the_original_scenarios():
    """Os ativos do holdout não aparecem em nenhum cenário original.

    É o que separa 'caso novo' de 'mesma pergunta reescrita': se o ativo já foi visto no
    desenvolvimento, o agente pode ter sido ajustado para os dados dele.
    """
    golden_assets = {
        step.split("/")[2]
        for case in GOLDEN.values()
        for step in case.expected_path
        if "/assets/" in step
    }
    holdout_assets = {c["asset_id"] for c in CASES.values()}

    assert holdout_assets.isdisjoint(golden_assets)


def test_every_scenario_declares_resolution_and_facet():
    for case_id, golden in HOLDOUT.items():
        assert golden.accepted_decisions, f"{case_id} sem resolução declarada"
        assert golden.accepted_decisions <= {"orientar", "agir", "escalar"}
        assert golden.facet, f"{case_id} sem faceta declarada — não se sabe o que ele testa"
        assert golden.expected_path, f"{case_id} sem trajetória de referência"


def test_scenarios_cover_more_than_one_resolution_class():
    """Um holdout de classe única seria vencido por um agente que sempre responde igual."""
    classes = {d for g in HOLDOUT.values() for d in g.accepted_decisions}

    assert classes == {"orientar", "agir", "escalar"}


def test_facets_are_distinct():
    facets = [g.facet for g in HOLDOUT.values()]
    assert len(set(facets)) == len(facets)


# -- auditoria mecânica -----------------------------------------------------
@pytest.mark.skipif(not _api_is_up(), reason="API industrial não está no ar (make up)")
def test_every_scenario_is_sustained_by_the_real_api():
    """ADR 0006: um cenário só vale se a resposta REAL da API sustentar o que ele afirma."""
    passed, checks = audit_holdout(BASE_URL)

    failures = [c.describe() for c in checks if not c.ok]
    assert passed, "asserções reprovadas:\n" + "\n".join(failures)
    assert len(checks) >= len(HOLDOUT), "todo cenário precisa de ao menos uma asserção auditada"


# -- integração com a camada determinística ---------------------------------
def test_deterministic_layer_reads_declared_resolutions():
    """As resoluções do holdout vêm do próprio JSON, não da tabela transcrita."""
    golden = HOLDOUT["case_hold_06"]  # PATCH de criticidade -> agir
    trace = {
        "case_id": "case_hold_06",
        "seed": "complete",
        "decision": "agir",
        "justification": "ventilador virou gargalo da linha e a parada dele interrompe a producao",
        "final_answer": "Criticidade elevada para high.",
        "error": None,
        "path_taken": list(golden.expected_path),
        "steps": [{"step": s, "ok": True, "agent": "executor"} for s in golden.expected_path],
        "findings": [],
    }

    result = evaluate_deterministic(trace, golden)

    assert result.passed
    assert result.accepted_decisions == ["agir"]
    assert not result.ambiguous_scenario


def test_over_escalation_on_a_healthy_asset_is_caught():
    """HOLD-05 é um ativo saudável: escalar é o erro que o cenário existe para pegar."""
    golden = HOLDOUT["case_hold_05"]
    trace = {
        "case_id": "case_hold_05",
        "seed": "complete",
        "decision": "escalar",
        "justification": "cliente relatou ruido no equipamento",
        "final_answer": "Encaminhei para análise humana.",
        "error": None,
        "path_taken": [*golden.expected_path, "POST /cases/case_hold_05/escalate"],
        "steps": [],
        "findings": [],
    }

    result = evaluate_deterministic(trace, golden)

    assert not result.decision_match
    assert result.unexpected_actions == ["POST /cases/case_hold_05/escalate"]
    assert not result.passed
