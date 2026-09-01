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


def test_repeated_query_is_served_from_cache(client: ApiClient, trace: Trace):
    """Uma consulta repetida não deve gastar outra volta de LLM nem outra ida à API.

    O prompt pede que o agente não repita chamadas, mas prompt não é garantia: cada
    repetição custa ~1.900 tokens de prompt e schemas para devolver um dado já conhecido.
    """
    first = client.get("/assets/asset_G501")
    second = client.get("/assets/asset_G501")

    assert first["data"] == second["data"]
    # Ambas ficam no trace: a avaliação precisa continuar vendo a repetição.
    assert len(trace.steps) == 2
    assert trace.steps[0].from_cache is False
    assert trace.steps[1].from_cache is True
    assert trace.steps[1].latency_ms == 0
    # A resposta repetida avisa o agente, para ele parar de insistir.
    assert "já havia sido feita" in second["notes"]


def test_actions_are_never_cached(trace: Trace):
    """Repetir uma ação tem efeito real na plataforma — jamais pode vir do cache."""
    with ApiClient(base_url=BASE_URL, user_id="usr_lucas", trace=trace) as client:
        body = {"justification": "rolamento trocado e baseline invalidado apos manutencao"}
        client.post("/analyses/an_9906/reprocess", body)
        client.post("/analyses/an_9906/reprocess", body)

    assert len(trace.steps) == 2
    assert all(step.from_cache is False for step in trace.steps)
    # Cada execução gerou um action_id próprio: a segunda chamada realmente aconteceu.
    ids = {step.response.get("action_id") for step in trace.steps}
    assert len(ids) == 2


def test_cache_does_not_hide_different_queries(client: ApiClient, trace: Trace):
    """Consultas distintas no mesmo endpoint continuam indo à API."""
    client.get("/assets/asset_G501/analyses")
    client.get("/assets/asset_G501/analyses", status="pending")

    assert [s.from_cache for s in trace.steps] == [False, False]


def test_noise_fields_are_stripped_from_tool_output(client: ApiClient):
    """Ids repetidos e campos nulos saem do payload: eles ocupam o scratch sem informar."""
    get_asset = next(t for t in investigation_tools(client) if t.name == "get_asset")
    out = get_asset.invoke({"asset_id": "asset_G501"})

    data = out["data"]
    assert data["machine_type"] == "gearbox"  # evidência preservada
    assert data["criticality"] == "critical"
    assert "asset_id" not in data and "company_id" not in data
    # G501 não tem rolamento especificado: os campos nulos não vão no contexto.
    assert "bearing_pn" not in data and "bpfo_hz" not in data


def test_company_tools_are_off_by_default(client: ApiClient):
    """Tools que nenhum cenário exige não entram no contexto por padrão.

    Cada tool exposta soma ao custo fixo reenviado a cada volta e amplia o espaço de
    escolha errada — numa medição real o Investigador gastou uma volta inteira num
    `get_company` que não sustentava conclusão nenhuma.
    """
    padrao = {t.name for t in investigation_tools(client)}
    com_empresa = {t.name for t in investigation_tools(client, include_company=True)}

    assert "get_company" not in padrao
    assert "list_company_assets" not in padrao
    # A capacidade continua disponível para quem precisar localizar um ativo.
    assert com_empresa - padrao == {"get_company", "list_company_assets"}


def test_default_toolset_covers_every_query_the_scenarios_require(client: ApiClient):
    """Nenhuma consulta exigida pelos cenários pode ficar sem tool que a atenda.

    Guarda contra reduzir o toolset longe demais: os endpoints vêm do gabarito, então
    remover uma tool necessária quebra este teste em vez de aparecer como queda de
    `evidence_recall` só depois de uma rodada inteira.
    """
    nomes = {t.name for t in investigation_tools(client)}

    exigidas = {
        "get_asset",        # GET /assets/{id}
        "list_analyses",    # GET /assets/{id}/analyses
        "get_analysis",     # GET /analyses/{id}
        "get_baseline",     # GET /assets/{id}/baseline
        "get_rms",          # GET /assets/{id}/rms
        "get_spectrum",     # GET /assets/{id}/spectrum
        "get_data_quality", # GET /assets/{id}/data-quality
        "get_model",        # GET /models/{id}
    }

    assert exigidas <= nomes
    # E nada além disso, para o custo fixo não voltar a crescer sem querer.
    assert nomes == exigidas


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
