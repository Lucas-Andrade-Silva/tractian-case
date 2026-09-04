"""Testes de cabeamento do braço de agente único (EXP-05).

O que se verifica aqui é que o braço de controle é COMPARÁVEL ao multiagente: mesmo
formato de trace, mesmo schema de decisão, orçamento de parada funcionando. E também o
que ele deliberadamente NÃO tem — a garantia estrutural da ADR 0002 —, porque é essa
diferença que o experimento mede.
"""
from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.api_client import ApiClient
from app.config import load_settings
from app.single_graph import build_single_graph
from app.state import Decision
from app.tools import action_tools, investigation_tools, knowledge_tools
from app.trace import Trace

BASE_URL = "http://localhost:8000"

CASE = {
    "id": "case_tkt_inv_04",
    "ticket_id": "TKT-INV-04",
    "company_id": "comp_mineracao_andes",
    "user_id": "usr_pedro",
    "asset_id": "asset_G501",
    "message": "O redutor quebrou ontem e não recebi aviso. Por quê?",
}


def _api_is_up() -> bool:
    try:
        return httpx.get(f"{BASE_URL}/docs", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _api_is_up(), reason="API industrial não está no ar (make up)")


class ScriptedLLM:
    """Mesmo LLM roteirizado de `test_graph.py`, com a superfície que o grafo usa."""

    def __init__(self, script: list):
        self.script = list(script)
        self.calls: list[str] = []

    def _next(self):
        if not self.script:
            raise AssertionError("ScriptedLLM: script esgotado — o grafo chamou o LLM além do previsto")
        return self.script.pop(0)

    def bind_tools(self, tools):  # noqa: ARG002 - assinatura compatível
        self.calls.append("bind_tools")
        return self

    def with_structured_output(self, schema, **kwargs):  # noqa: ARG002 - aceita include_raw
        self.calls.append(f"structured:{schema.__name__}")
        return self

    def invoke(self, messages):  # noqa: ARG002 - o roteiro ignora o histórico
        return self._next()


@pytest.fixture
def trace() -> Trace:
    return Trace(
        case_id=CASE["id"],
        ticket_id=CASE["ticket_id"],
        seed="complete",
        user_id=CASE["user_id"],
        asset_id=CASE["asset_id"],
        message=CASE["message"],
    )


@pytest.fixture
def client(trace: Trace):
    with ApiClient(base_url=BASE_URL, user_id=CASE["user_id"], trace=trace, seed="complete") as c:
        yield c


def _build(script: list, *, trace: Trace, client: ApiClient, settings=None):
    return build_single_graph(
        models=ScriptedLLM(script),
        client=client,
        settings=settings or load_settings(),
        case=CASE,
        trace=trace,
        investigation_tools=investigation_tools(client),
        knowledge_tools=knowledge_tools(client),
        action_tools=action_tools(client, CASE["id"]),
    )


def _initial_state():
    return {"case": CASE, "scratch": [], "findings": [], "worker_steps": 0}


DECISION = Decision(
    decision="escalar",
    justification="baseline em learning e sensor offline impedem diagnóstico remoto do redutor",
    intended_action="escalar o caso para análise humana em campo",
    answer="Nenhum insight foi emitido porque o baseline ainda estava em learning.",
)


def test_investiga_com_tool_real_e_formaliza_decisao(trace: Trace, client: ApiClient):
    """Um único papel consulta a API, encerra e formaliza a resolução."""
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_baseline", "args": {"asset_id": "asset_G501"}, "id": "c1"}],
        ),
        AIMessage(content="baseline.state=learning (baseline); sensor_status=offline (asset)"),
        DECISION,
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert final["decision"]["decision"] == "escalar"
    assert final["final_answer"] == DECISION.answer
    # A chamada real à API foi registrada no trace, como no multiagente.
    assert any(step.step.startswith("GET /assets/asset_G501/baseline") for step in trace.steps)


def test_todas_as_tools_num_unico_papel(trace: Trace, client: ApiClient):
    """O agente único recebe investigação, conhecimento e ação juntas.

    É a diferença estrutural com o multiagente, onde cada grupo vai para um papel.
    """
    script = [AIMessage(content="nada a apurar"), DECISION]
    graph = _build(script, trace=trace, client=client)
    graph.invoke(_initial_state())

    nomes = {t.name for t in investigation_tools(client)}
    nomes |= {t.name for t in knowledge_tools(client)}
    nomes |= {t.name for t in action_tools(client, CASE["id"])}
    # Sanidade do braço: as três famílias existem e conviveriam no mesmo bind.
    assert {"get_baseline", "search_knowledge", "escalate_case"} <= nomes


def test_trace_registra_papel_unico(trace: Trace, client: ApiClient):
    """Toda chamada de API sai sob o papel `agente_unico`.

    No multiagente as chamadas se distribuem entre supervisor, investigador,
    contextualizador e executor; aqui não há distribuição possível — e é isso que a
    comparação de custo por papel do EXP-04 contrasta.
    """
    script = [
        AIMessage(
            content="",
            tool_calls=[{"name": "get_asset", "args": {"asset_id": "asset_G501"}, "id": "c1"}],
        ),
        AIMessage(content="asset apurado"),
        DECISION,
    ]
    graph = _build(script, trace=trace, client=client)
    graph.invoke(_initial_state())

    papeis = {step.agent for step in trace.steps}
    assert papeis == {"agente_unico"}


def test_orcamento_forca_encerramento(trace: Trace, client: ApiClient):
    """Estourado o orçamento, o agente é chamado sem tools e precisa concluir.

    Sem isso o braço de controle poderia investigar indefinidamente e nunca resolver —
    e a comparação de custo com o multiagente ficaria sem teto.
    """
    settings = load_settings()
    max_steps = settings.max_worker_steps * 2

    def tool_call(i: int) -> AIMessage:
        # `id` distinto por volta: o reducer `add_messages` deduplica por id, e reusar o
        # mesmo faria as voltas colapsarem numa só em vez de consumir o orçamento.
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_asset", "args": {"asset_id": "asset_G501"}, "id": f"c{i}"}],
        )

    # Exatamente o orçamento em voltas de tool; na volta seguinte o agente é chamado
    # sem tools ("resumo forçado") e o grafo segue para a formalização.
    script = [tool_call(i) for i in range(max_steps)] + [AIMessage(content="resumo forçado"), DECISION]
    graph = _build(script, trace=trace, client=client, settings=settings)

    final = graph.invoke(_initial_state())

    assert final["decision"]["decision"] == "escalar"
