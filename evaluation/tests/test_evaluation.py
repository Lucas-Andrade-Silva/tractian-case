"""Testes das camadas de avaliação, com traces sintéticos (sem LLM, sem API).

As camadas 1 e 3 são código puro: dá para verificá-las com traces montados à mão, o que
também documenta o que cada métrica considera acerto e erro.
"""
from __future__ import annotations

from typing import Any

import pytest

from runner.deterministic import evaluate_deterministic
from runner.golden import load_golden
from runner.report import build_report
from runner.stability import evaluate_stability

GOLDEN = load_golden()


def make_trace(
    case_id: str,
    *,
    decision: str | None,
    path: list[str],
    seed: str | None = "complete",
    error: str | None = None,
    justification: str = "justificativa suficientemente longa e ancorada em evidência",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "ticket_id": GOLDEN[case_id].ticket_id if case_id in GOLDEN else "",
        "seed": seed,
        "message": "mensagem do cliente",
        "decision": decision,
        "justification": justification,
        "final_answer": "resposta ao cliente",
        "error": error,
        "path_taken": path,
        "steps": steps or [{"step": s, "ok": True, "agent": "investigador"} for s in path],
        "findings": [],
    }


# -- golden set -------------------------------------------------------------
def test_golden_set_covers_every_ticket():
    """17 entradas para 16 cenários: CEN-07 cobre dois tickets (TKT-INV-09 → TKT-EXE-12)."""
    assert len(GOLDEN) == 17
    assert "case_tkt_inv_09" in GOLDEN and "case_tkt_exe_12" in GOLDEN


def test_every_golden_case_has_a_transcribed_resolution():
    """Nenhum caso do gabarito pode depender do fallback por trajetória."""
    from runner.golden import ACCEPTED_DECISIONS

    assert set(GOLDEN) == set(ACCEPTED_DECISIONS)


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        ("case_tkt_inv_04", {"escalar"}),
        ("case_tkt_exe_12", {"agir"}),
        ("case_tkt_exe_14", {"agir"}),
        ("case_tkt_ctx_02", {"orientar"}),
    ],
)
def test_unambiguous_scenarios_accept_a_single_resolution(case_id: str, expected: set[str]):
    assert set(GOLDEN[case_id].accepted_decisions) == expected
    assert not GOLDEN[case_id].is_ambiguous


@pytest.mark.parametrize(
    ("case_id", "expected"),
    [
        ("case_tkt_inv_06", {"orientar", "escalar"}),  # CEN-03
        ("case_tkt_inv_08", {"agir", "escalar"}),      # CEN-06
        ("case_tkt_inv_11", {"agir", "escalar"}),      # CEN-09, ação marcada "(Opcional)"
        ("case_tkt_inv_10", {"orientar", "escalar"}),  # CEN-08
    ],
)
def test_ambiguous_scenarios_accept_more_than_one_resolution(case_id: str, expected: set[str]):
    """A trajetória do gabarito sozinha diria 'orientar' nesses casos — e reprovaria
    um agente que agiu ou escalou, que é o que o cenário autoriza."""
    golden = GOLDEN[case_id]

    assert set(golden.accepted_decisions) == expected
    assert golden.is_ambiguous
    assert golden.required_actions == []  # ação não é exigida quando há mais de um desfecho


def test_ambiguous_scenario_accepts_either_resolution():
    """CEN-06 aceita agir OU escalar: nenhuma das duas pode ser reprovada."""
    golden = GOLDEN["case_tkt_inv_08"]
    base_path = list(golden.expected_path)

    escalated = evaluate_deterministic(
        make_trace(
            "case_tkt_inv_08",
            decision="escalar",
            path=[*base_path, "POST /cases/case_tkt_inv_08/escalate"],
        ),
        golden,
    )
    acted = evaluate_deterministic(
        make_trace(
            "case_tkt_inv_08",
            decision="agir",
            path=[*base_path, "POST /analyses/an_9908/request-specialist"],
        ),
        golden,
    )

    assert escalated.decision_match and not escalated.unexpected_actions
    assert acted.decision_match
    # Orientar, por outro lado, não está entre as resoluções aceitas deste cenário.
    oriented = evaluate_deterministic(
        make_trace("case_tkt_inv_08", decision="orientar", path=base_path), golden
    )
    assert not oriented.decision_match


# -- camada 1 ---------------------------------------------------------------
def test_perfect_run_passes_deterministic_layer():
    golden = GOLDEN["case_tkt_exe_12"]
    result = evaluate_deterministic(
        make_trace("case_tkt_exe_12", decision="agir", path=list(golden.expected_path)),
        golden,
    )

    assert result.passed
    assert result.decision_match
    assert result.evidence_recall == 1.0
    assert not result.missing_actions


def test_order_variation_is_not_penalized():
    """Trajetória é referência, não script: inverter a ordem não derruba o recall."""
    golden = GOLDEN["case_tkt_exe_12"]
    result = evaluate_deterministic(
        make_trace("case_tkt_exe_12", decision="agir", path=list(reversed(golden.expected_path))),
        golden,
    )

    assert result.evidence_recall == 1.0
    assert result.passed


def test_over_escalation_fails_the_layer():
    """Escalar um caso resolvível por reprocesso é erro, não cautela."""
    golden = GOLDEN["case_tkt_exe_12"]
    result = evaluate_deterministic(
        make_trace(
            "case_tkt_exe_12",
            decision="escalar",
            path=["GET /analyses/an_9906", "POST /cases/case_tkt_exe_12/escalate"],
        ),
        golden,
    )

    assert not result.passed
    assert not result.decision_match
    assert result.missing_actions == ["POST /analyses/an_9906/reprocess"]
    assert result.unexpected_actions == ["POST /cases/case_tkt_exe_12/escalate"]


def test_missing_evidence_lowers_recall_without_hiding_decision_match():
    golden = GOLDEN["case_tkt_inv_04"]
    result = evaluate_deterministic(
        make_trace(
            "case_tkt_inv_04",
            decision="escalar",
            path=["GET /assets/asset_G501", "POST /cases/case_tkt_inv_04/escalate"],
        ),
        golden,
    )

    assert result.decision_match
    assert result.evidence_recall < 1.0
    assert "GET /assets/asset_G501/baseline" in result.missing_queries


def test_retry_after_error_is_detected():
    """Repetir uma chamada já rejeitada é o padrão de falha que interessa medir."""
    path = ["POST /cases/case_tkt_inv_04/escalate", "POST /cases/case_tkt_inv_04/escalate"]
    steps = [
        {"step": path[0], "ok": False, "status_code": 403, "agent": "executor"},
        {"step": path[1], "ok": False, "status_code": 403, "agent": "executor"},
    ]
    result = evaluate_deterministic(
        make_trace("case_tkt_inv_04", decision="escalar", path=path, steps=steps),
        GOLDEN["case_tkt_inv_04"],
    )

    assert result.retried_after_error == ["POST /cases/case_tkt_inv_04/escalate"]
    assert result.repeated_calls == 1
    assert result.http_errors == 2


def test_broken_execution_is_marked_not_passed():
    result = evaluate_deterministic(
        make_trace("case_tkt_inv_04", decision=None, path=[], error="ConnectError: recusada"),
        GOLDEN["case_tkt_inv_04"],
    )

    assert not result.executed
    assert not result.passed


# -- camada 3 ---------------------------------------------------------------
def test_same_decision_across_seeds_is_stable():
    traces = [
        make_trace("case_tkt_exe_12", decision="agir", path=["GET /analyses/an_9906"], seed=s)
        for s in ("s1", "s2", "s3")
    ]
    result = evaluate_stability(traces)

    assert result.stable
    assert result.agreement_rate == 1.0


def test_diverging_decision_is_unstable():
    traces = [
        make_trace("case_tkt_exe_12", decision="agir", path=[], seed="s1"),
        make_trace("case_tkt_exe_12", decision="escalar", path=[], seed="s2"),
        make_trace("case_tkt_exe_12", decision="agir", path=[], seed="s3"),
    ]
    result = evaluate_stability(traces)

    assert not result.stable
    assert result.majority_decision == "agir"
    assert result.agreement_rate == pytest.approx(2 / 3, abs=0.01)


def test_trajectory_variation_alone_does_not_make_it_unstable():
    """Investigar em ordens/caminhos diferentes e concluir igual NÃO é instabilidade."""
    traces = [
        make_trace("case_tkt_exe_12", decision="agir", path=["GET /analyses/an_9906"], seed="s1"),
        make_trace("case_tkt_exe_12", decision="agir", path=["GET /assets/asset_B204/baseline"], seed="s2"),
        make_trace("case_tkt_exe_12", decision="agir", path=["GET /assets/asset_B204/rms"], seed="s3"),
    ]
    result = evaluate_stability(traces)

    assert result.stable
    assert result.trajectory_variation > 0


# -- relatório --------------------------------------------------------------
def test_report_keeps_layers_separate():
    golden = GOLDEN["case_tkt_exe_12"]
    deterministic = [
        evaluate_deterministic(
            make_trace("case_tkt_exe_12", decision="agir", path=list(golden.expected_path)), golden
        )
    ]
    stability = [
        evaluate_stability(
            [make_trace("case_tkt_exe_12", decision="agir", path=[], seed=s) for s in ("s1", "s2")]
        )
    ]
    judged = {
        "case_tkt_exe_12__s1": {
            "honestidade": {"score": 5, "reasoning": "ok"},
            "causa_raiz": {"score": 4, "reasoning": "ok"},
            "justificativa": {"score": 4, "reasoning": "ok"},
        }
    }

    report = build_report(
        deterministic=deterministic, judged=judged, stability=stability, meta={"suite": "teste"}
    )

    assert report["layer1_deterministic"]["decision_accuracy"] == 1.0
    assert report["layer2_judges"]["honestidade"]["mean_score"] == 5.0
    assert report["layer3_stability"]["stability_rate"] == 1.0
