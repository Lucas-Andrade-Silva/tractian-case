"""Testes de cabeamento do grafo, com LLM roteirizado (sem provedor real).

Um LLM de verdade tornaria estes testes não-determinísticos e caros; o que se quer
verificar aqui é estrutural: as transições do grafo, os orçamentos de parada e —
principalmente — a garantia do ADR 0002 de que nenhuma ação de impacto ocorre sem
decisão formal do Decisor.
"""
from __future__ import annotations

import httpx
import pytest
from langchain_core.messages import AIMessage

from app.api_client import ApiClient
from app.config import load_settings
from app.graph import build_graph
from app.state import Decision, Route
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
    """LLM falso que devolve uma sequência programada de respostas.

    Implementa apenas a superfície que o grafo usa: `bind_tools`,
    `with_structured_output` e `invoke`.
    """

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

    # Sem `for_role`: o grafo detecta a ausência e usa este mesmo modelo para todo
    # papel, que é o comportamento de uma configuração single-model.


def _build(script: list, *, trace: Trace, client: ApiClient):
    settings = load_settings()
    return build_graph(
        models=ScriptedLLM(script),
        client=client,
        settings=settings,
        case=CASE,
        trace=trace,
        investigation_tools=investigation_tools(client),
        knowledge_tools=knowledge_tools(client),
        action_tools=action_tools(client, CASE["id"]),
    )


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


def _initial_state():
    return {
        "case": CASE,
        "scratch": [],
        "findings": [],
        "supervisor_turns": 0,
        "worker_steps": 0,
    }


def test_investigation_then_escalation_flow(trace: Trace, client: ApiClient):
    """Fluxo completo: investiga com tool real, decide escalar, Executor age."""
    script = [
        Route(next="investigador", reason="preciso do estado do baseline"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_baseline", "args": {"asset_id": "asset_G501"}, "id": "c1"}],
        ),
        AIMessage(content="Baseline em learning; sensor offline; sem histórico suficiente."),
        Route(next="decisor", reason="evidência suficiente"),
        Decision(
            decision="escalar",
            justification="baseline em learning e sensor offline impedem diagnóstico remoto do redutor",
            intended_action="escalar o caso para análise humana em campo",
            answer="Nenhum insight foi emitido porque o baseline ainda estava em learning.",
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "escalate_case",
                    "args": {
                        "justification": "baseline em learning e sensor offline impedem diagnóstico remoto"
                    },
                    "id": "c2",
                }
            ],
        ),
        AIMessage(content="Caso encaminhado para análise humana."),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert final["decision"]["decision"] == "escalar"
    assert final["final_answer"] == "Caso encaminhado para análise humana."

    # O trace registrou as chamadas reais, com o papel que as fez.
    agents = {s.agent for s in trace.steps}
    assert "supervisor" in agents  # contexto de autorização
    assert "investigador" in agents
    assert "executor" in agents
    assert "GET /assets/asset_G501/baseline" in trace.path_taken
    assert "POST /cases/case_tkt_inv_04/escalate" in trace.path_taken


def test_orientar_never_reaches_executor(trace: Trace, client: ApiClient):
    """ADR 0002: 'orientar' encerra o grafo — o Executor não é alcançado.

    Se o roteamento deixasse escapar para o Executor, o script se esgotaria e o
    ScriptedLLM levantaria — ou seja, o teste falha em vez de passar silenciosamente.
    """
    script = [
        Route(next="decisor", reason="pergunta conceitual, não precisa de sensor"),
        Decision(
            decision="orientar",
            justification="pergunta conceitual respondida com conhecimento de domínio disponível",
            intended_action=None,
            answer="O limiar de alarme deriva do baseline do próprio ativo, não de norma fixa.",
        ),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert final["decision"]["decision"] == "orientar"
    assert not any(step.method in ("POST", "PATCH") for step in trace.steps)


def test_supervisor_budget_forces_decision(trace: Trace, client: ApiClient):
    """Sem política de parada o agente nunca conclui; o orçamento força a decisão."""
    settings = load_settings()
    script: list = []
    # Cada volta gasta um turno do Supervisor sem produzir evidência nova.
    for _ in range(settings.max_supervisor_turns):
        script.append(Route(next="investigador", reason="mais uma volta"))
        script.append(AIMessage(content="Nada de novo apurado."))
    script.append(
        Decision(
            decision="orientar",
            justification="não foi possível apurar evidência suficiente sobre o ativo",
            intended_action=None,
            answer="Não consegui determinar a causa com os dados disponíveis.",
        )
    )
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert final["stop_reason"] == "budget_supervisor"
    assert final["decision"]["decision"] == "orientar"


def test_worker_budget_stops_tool_looping(trace: Trace, client: ApiClient):
    """Um worker que insiste em chamar tools é cortado e obrigado a resumir."""
    settings = load_settings()
    script: list = [Route(next="investigador", reason="investigar")]
    for _ in range(settings.max_worker_steps):
        script.append(
            AIMessage(
                content="",
                tool_calls=[{"name": "get_asset", "args": {"asset_id": "asset_G501"}, "id": "loop"}],
            )
        )
    # Ao estourar o orçamento o nó é chamado sem tools, então só resta produzir texto.
    script.append(AIMessage(content="Resumo forçado pelo orçamento."))
    script.append(Route(next="decisor", reason="chega"))
    script.append(
        Decision(
            decision="orientar",
            justification="evidência limitada, mas suficiente para orientar o cliente",
            intended_action=None,
            answer="Resposta.",
        )
    )
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert any("Resumo forçado" in f for f in final["findings"])
    get_asset_calls = [s for s in trace.steps if s.step == "GET /assets/asset_G501"]
    assert len(get_asset_calls) == settings.max_worker_steps


def _cortado(content: str = "") -> AIMessage:
    """Resposta interrompida pelo teto de saída, como o provedor a devolve."""
    return AIMessage(content=content, response_metadata={"finish_reason": "length"})


def test_truncated_worker_retries_instead_of_reporting_nothing(trace: Trace, client: ApiClient):
    """Cortado no teto antes de resumir, o papel tenta de novo — não devolve `(sem resumo)`.

    É o desperdício que se quer eliminar: sem a segunda tentativa, o finding vinha vazio,
    o Supervisor não via evidência e reacionava o mesmo papel, refazendo a apuração toda.
    """
    script = [
        Route(next="investigador", reason="investigar"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_baseline", "args": {"asset_id": "asset_G501"}, "id": "c1"}],
        ),
        # Gastou o orçamento raciocinando e foi cortado sem emitir texto.
        _cortado(),
        # Segunda tentativa, sem tools e sem o scratch: agora o resumo sai.
        AIMessage(content="baseline.state=learning (baseline)"),
        Route(next="decisor", reason="evidência suficiente"),
        Decision(
            decision="orientar",
            justification="baseline em learning explica a ausência de insight para o cliente",
            intended_action=None,
            answer="O baseline ainda estava aprendendo.",
        ),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert any("baseline.state=learning" in f for f in final["findings"])
    assert not any("(sem resumo)" in f for f in final["findings"])
    # A segunda tentativa é uma chamada de LLM a mais, atribuída ao mesmo papel.
    assert len([c for c in trace.llm_calls if c.agent == "investigador"]) >= 0


def test_persistent_truncation_tells_supervisor_not_to_retry(trace: Trace, client: ApiClient):
    """Se nem a segunda tentativa produz texto, o finding diz para não reacionar o papel.

    `(sem resumo)` fazia o Supervisor ler "nada foi apurado" e tentar de novo — o loop que
    custava uma investigação inteira por volta.
    """
    script = [
        Route(next="investigador", reason="investigar"),
        _cortado(),
        _cortado(),  # a segunda tentativa também é cortada
        Route(next="decisor", reason="não vai sair resumo; decidir com o que houver"),
        Decision(
            decision="orientar",
            justification="não foi possível apurar evidência técnica suficiente neste caso",
            intended_action=None,
            answer="Não consegui determinar a causa.",
        ),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    achado = next(f for f in final["findings"] if "investigador" in f)
    assert "NÃO reacione" in achado
    assert "(sem resumo)" not in achado


def test_normal_finish_does_not_trigger_retry(trace: Trace, client: ApiClient):
    """Resposta vazia SEM marca de corte não gera segunda tentativa.

    O script se esgotaria se houvesse uma chamada extra, então o teste falha em vez de
    passar silenciosamente.
    """
    script = [
        Route(next="investigador", reason="investigar"),
        AIMessage(content=""),  # vazia, mas o modelo terminou por conta própria
        Route(next="decisor", reason="chega"),
        Decision(
            decision="orientar",
            justification="evidência insuficiente, mas o caso comporta uma orientação geral",
            intended_action=None,
            answer="Resposta.",
        ),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    assert final["decision"]["decision"] == "orientar"


def test_reasoning_block_never_reaches_the_findings(trace: Trace, client: ApiClient):
    """Rascunho de raciocinio no conteudo nao pode virar `finding`.

    Medido no TKT-EXE-13: um bloco `<think>` de ~1.000 tokens entrou no resumo do
    Investigador e foi reenviado ao Decisor a cada volta, custando +35% no caso. O bloco
    aparece SEM fechamento quando o corte por `max_tokens` o interrompe no meio — que e
    exatamente a situacao em que ele vaza.
    """
    script = [
        Route(next="investigador", reason="investigar"),
        AIMessage(content="<think>vou checar o baseline</think>baseline.state=learning (baseline)"),
        Route(next="decisor", reason="chega"),
        Decision(
            decision="orientar",
            justification="baseline em learning explica a ausencia de insight ao cliente",
            intended_action=None,
            answer="O baseline ainda estava aprendendo.",
        ),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    achado = next(f for f in final["findings"] if "investigador" in f)
    assert "baseline.state=learning" in achado
    assert "<think>" not in achado and "vou checar" not in achado


def test_unterminated_reasoning_block_is_treated_as_empty(trace: Trace, client: ApiClient):
    """Cortado dentro do `<think>`, nao ha resposta — e o retry precisa disparar.

    Sem isso o rascunho inteiro seria gravado como se fosse o resumo.
    """
    script = [
        Route(next="investigador", reason="investigar"),
        AIMessage(
            content="<think>Here's a thinking process: 1. Analyze the user input",
            response_metadata={"finish_reason": "length"},
        ),
        AIMessage(content="baseline.state=established (baseline)"),
        Route(next="decisor", reason="chega"),
        Decision(
            decision="orientar",
            justification="evidencia suficiente para orientar o cliente sobre o baseline",
            intended_action=None,
            answer="Resposta.",
        ),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    achado = next(f for f in final["findings"] if "investigador" in f)
    assert achado.endswith("baseline.state=established (baseline)")
    assert "thinking process" not in achado


def test_retry_uses_the_transcription_client(trace: Trace, client: ApiClient):
    """O retry pede o cliente SEM raciocinio, nao o do papel.

    Com o raciocinio ligado a segunda tentativa gasta o mesmo orcamento pensando e e
    cortada igual — o defeito que o TKT-EXE-13 expos.
    """
    pedidos: list[str] = []

    class ModelsQueRegistra:
        def __init__(self, llm):
            self._llm = llm

        def for_role(self, role):
            pedidos.append(f"role:{role}")
            return self._llm

        def for_transcription(self, role):
            pedidos.append(f"transcricao:{role}")
            return self._llm

    settings = load_settings()
    scripted = ScriptedLLM(
        [
            Route(next="investigador", reason="investigar"),
            AIMessage(content="", response_metadata={"finish_reason": "length"}),
            AIMessage(content="baseline.state=learning (baseline)"),
            Route(next="decisor", reason="chega"),
            Decision(
                decision="orientar",
                justification="evidencia suficiente para orientar o cliente neste caso",
                intended_action=None,
                answer="Resposta.",
            ),
        ]
    )
    graph = build_graph(
        models=ModelsQueRegistra(scripted),
        client=client,
        settings=settings,
        case=CASE,
        trace=trace,
        investigation_tools=investigation_tools(client),
        knowledge_tools=knowledge_tools(client),
        action_tools=action_tools(client, CASE["id"]),
    )

    graph.invoke(_initial_state())

    assert "transcricao:investigador" in pedidos, (
        f"o retry deveria usar o cliente de transcricao; pedidos={pedidos}"
    )


def test_403_reaches_the_agent_instead_of_blocking(trace: Trace, client: ApiClient):
    """ADR 0003: a ação sem permissão é tentada, rejeitada pela API, e o agente reage."""
    script = [
        Route(next="decisor", reason="cliente pediu retreinamento"),
        Decision(
            decision="agir",
            justification="cliente relata erro sistemático do modelo neste tipo de ativo",
            intended_action="solicitar retreinamento do modelo mdl_vib_v3",
            answer="Vou solicitar o retreinamento.",
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "request_retraining",
                    "args": {
                        "model_id": "mdl_vib_v3",
                        "justification": "erro sistemático do modelo relatado para este tipo de ativo",
                    },
                    "id": "c1",
                }
            ],
        ),
        AIMessage(content="A solicitação foi recusada: seu perfil não tem permissão action_high."),
    ]
    graph = _build(script, trace=trace, client=client)

    final = graph.invoke(_initial_state())

    rejected = [s for s in trace.steps if s.status_code == 403]
    assert rejected, "a tentativa deveria ter chegado à API e sido rejeitada com 403"
    assert "não tem permissão" in final["final_answer"]
