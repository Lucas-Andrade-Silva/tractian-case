"""Testes do cliente HTTP e das tools contra a API industrial real.

Não usam LLM: exercitam a camada de integração de ponta a ponta contra
`http://localhost:8000`. Se a API não estiver no ar, os testes são pulados.
"""
from __future__ import annotations

import httpx
import pytest

from app.api_client import ApiClient
from app.tools import action_tools, investigation_tools, knowledge_tools
from app.trace import Trace

BASE_URL = "http://localhost:8000"


def _api_is_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/docs", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _api_is_up(), reason="API industrial não está no ar (make up)")


@pytest.fixture
def trace() -> Trace:
    return Trace(
        case_id="case_tkt_inv_04",
        ticket_id="TKT-INV-04",
        seed="complete",
        user_id="usr_pedro",
        asset_id="asset_G501",
        message="teste",
    )


@pytest.fixture
def client(trace: Trace):
    with ApiClient(base_url=BASE_URL, user_id="usr_pedro", trace=trace, seed="complete") as c:
        yield c


def test_get_asset_returns_envelope_and_records_trace(client: ApiClient, trace: Trace):
    result = client.get("/assets/asset_G501")

    assert result["ok"] is True
    assert result["mode"] == "complete"
    assert result["data"]["machine_type"] == "gearbox"

    assert len(trace.steps) == 1
    step = trace.steps[0]
    # Formato do golden set — é isso que a Parte 2 compara.
    assert step.step == "GET /assets/asset_G501"
    assert step.agent == "supervisor"
    assert step.status_code == 200


def test_seed_is_sent_but_excluded_from_step_label(client: ApiClient, trace: Trace):
    """O seed é artefato de reprodutibilidade, não escolha de investigação do agente."""
    client.get("/assets/asset_G501/analyses", status="inconclusive")

    step = trace.steps[0]
    assert step.step == "GET /assets/asset_G501/analyses?status=inconclusive"
    assert "seed" not in step.query


def test_scenario_override_survives_seed_complete(client: ApiClient):
    """G501 tem override fixo de cenário: rms=unavailable mesmo com seed=complete."""
    result = client.get("/assets/asset_G501/rms")

    assert result["ok"] is True
    assert result["mode"] == "unavailable"
    assert result["notes"]


def test_http_error_is_returned_not_raised(trace: Trace):
    """ADR 0003: o 403 tem que chegar ao agente como resultado legível, não como exceção.

    usr_pedro (Coordenador) não tem action_high — a API rejeita o retreinamento.
    """
    with ApiClient(base_url=BASE_URL, user_id="usr_pedro", trace=trace) as client:
        result = client.post(
            "/models/mdl_vib_v3/request-retraining",
            {"justification": "justificativa suficientemente longa para passar na validação"},
        )

    assert result["ok"] is False
    assert result["status_code"] == 403
    assert "action_high" in result["error"]
    assert trace.steps[-1].ok is False


def test_weak_justification_is_rejected_by_api(trace: Trace):
    """A validação de justificativa vive na API (mínimo 20 chars), não em código nosso."""
    with ApiClient(base_url=BASE_URL, user_id="usr_pedro", trace=trace) as client:
        result = client.post("/cases/case_tkt_inv_04/escalate", {"justification": "curta"})

    assert result["ok"] is False
    assert result["status_code"] == 400


def test_investigation_tools_are_exposed_with_descriptions(client: ApiClient):
    tools = investigation_tools(client)
    names = {t.name for t in tools}

    assert {"get_asset", "get_baseline", "get_rms", "get_data_quality", "get_model"} <= names
    assert all(t.description for t in tools)


def test_rms_tool_summarizes_series(trace: Trace):
    """C710 tem override rms=complete: a série existe e deve vir resumida."""
    with ApiClient(base_url=BASE_URL, user_id="usr_sofia", trace=trace, seed="complete") as client:
        get_rms = next(t for t in investigation_tools(client) if t.name == "get_rms")
        out = get_rms.invoke({"asset_id": "asset_C710"})

    assert out["ok"] is True
    summary = out["data"]["summary"]
    assert summary["count"] > 0
    assert summary["max"] >= summary["min"]
    assert "exceeds_alarm_threshold" in summary


def test_knowledge_and_action_tool_groups(client: ApiClient):
    assert {t.name for t in knowledge_tools(client)} == {"search_knowledge", "get_knowledge_doc"}
    assert {t.name for t in action_tools(client, "case_tkt_inv_04")} == {
        "reprocess_analysis",
        "request_specialist_analysis",
        "request_retraining",
        "update_asset_config",
        "escalate_case",
    }


def test_trace_serializes_with_path_taken(client: ApiClient, trace: Trace):
    client.get("/assets/asset_G501")
    client.get("/assets/asset_G501/baseline")
    trace.close(
        decision="escalar",
        justification="baseline em learning e gap de dados impedem diagnóstico remoto",
        final_answer="resposta ao cliente",
        stop_reason="decisor",
    )

    payload = trace.to_dict()
    assert payload["path_taken"] == ["GET /assets/asset_G501", "GET /assets/asset_G501/baseline"]
    assert payload["decision"] == "escalar"
    assert payload["finished_at"]
