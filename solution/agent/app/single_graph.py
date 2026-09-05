"""Variante de agente ÚNICO — braço de controle do EXP-05.

    START → agente ⇄ tools (investigação + conhecimento + ação) → decisão → END

Um só papel, com TODAS as tools na mão, decidindo quando parar de investigar e resolvendo
o caso ele mesmo. É a arquitetura que o multiagente de `graph.py` substituiu, reconstruída
aqui para servir de comparação — sem ela, a hipótese de que separar papéis melhora alguma
coisa não é testável, só afirmável.

O QUE MUDA em relação ao multiagente, e só isso:

- não há Supervisor: nenhuma decisão de roteamento, o próprio agente escolhe a tool;
- não há fronteira entre papéis: um único transcrito acumula tudo (não há `findings`
  resumindo o que atravessa papéis, porque não há travessia);
- não há transição fixa Decisor → Executor: o mesmo agente que investigou também age.
  A garantia estrutural da ADR 0002 não existe neste braço — é justamente parte do que
  o experimento mede.

O QUE NÃO MUDA, para que a comparação isole a arquitetura:

- as mesmas tools, das mesmas fábricas de `tools.py`;
- o mesmo `DOMAIN_BRIEF` e a mesma `_DECISION_POLICY` de `prompts.py` — o texto da
  política de decisão é idêntico, não uma reescrita;
- o mesmo schema `Decision`, a mesma API, os mesmos orçamentos e o mesmo trace.

A decisão final sai por saída estruturada numa última chamada sem tools. Isso mantém o
trace comparável (o campo `decision` significa a mesma coisa nos dois braços) e é o
mínimo de estrutura que o braço de controle precisa para ser avaliável pela camada 1.
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .api_client import ApiClient
from .config import Settings
from .prompts import single_agent_prompt
from .state import CaseState, Decision
from .trace import Trace


def _text(message: AnyMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


def _bind(llm, tools: list):
    """Mesma vinculação com chamadas paralelas do multiagente (ver `graph._bind`)."""
    try:
        return llm.bind_tools(tools, parallel_tool_calls=True)
    except TypeError:
        return llm.bind_tools(tools)


def build_single_graph(
    *,
    models: Any,
    client: ApiClient,
    settings: Settings,
    case: dict[str, Any],
    trace: Trace,
    investigation_tools: list,
    knowledge_tools: list,
    action_tools: list,
):
    """Compila o grafo de agente único.

    `models` aceita tanto um `RoleModels` quanto um chat model direto, como em
    `build_graph`. Quando for `RoleModels`, usa-se o modelo do papel `decisor`: é o mais
    capaz da configuração, e aqui um só modelo faz tudo — dar ao braço de controle o
    modelo fraco tornaria a comparação injusta com ele.
    """
    all_tools = [*investigation_tools, *knowledge_tools, *action_tools]

    getter = getattr(models, "for_role", None)
    llm = getter("decisor") if getter else models

    # Orçamento total de voltas de tool. No multiagente o teto é por papel
    # (`max_worker_steps` por worker, sob `max_supervisor_turns` turnos); aqui não há
    # papéis, então o equivalente justo é a soma do que os dois workers poderiam gastar.
    max_steps = settings.max_worker_steps * 2

    def agente(state: CaseState) -> dict[str, Any]:
        client.current_agent = "agente_unico"
        scratch = state.get("scratch", [])
        steps = state.get("worker_steps", 0)

        # Contexto de autorização: mesma consulta única do Supervisor no multiagente,
        # para que os dois braços partam da mesma informação de permissão.
        updates: dict[str, Any] = {}
        user_context = state.get("user_context")
        if user_context is None:
            result = client.request("GET", "/users/me", with_seed=False)
            user_context = result.get("data") if result.get("ok") else {"erro": result.get("error")}
            updates["user_context"] = user_context

        over_budget = steps >= max_steps
        # As tools continuam vinculadas mesmo no estouro de orçamento. No multiagente o
        # worker é chamado SEM tools para forçar o encerramento, e ali isso funciona
        # porque o scratch daquele papel é descartado junto; aqui o transcrito com tool
        # calls permanece, e desvincular as tools faz o provedor recusar a requisição
        # inteira ("attempted to call tool X which was not in request.tools"). O corte
        # passa a ser a instrução explícita abaixo mais o roteamento para `resolver`.
        model = _bind(llm, all_tools)

        messages: list[AnyMessage] = [
            SystemMessage(single_agent_prompt(case, user_context, settings.evidence_policy)),
            *scratch,
        ]
        if over_budget:
            messages.append(
                HumanMessage(
                    "Orçamento de investigação esgotado. NÃO chame mais nenhuma tool: "
                    "responda apenas com texto, resumindo o que já foi apurado."
                )
            )

        response = model.invoke(messages)
        trace.add_llm_call(agent="agente_unico", response=response)

        if getattr(response, "tool_calls", None):
            return {**updates, "scratch": [response], "worker_steps": steps + 1}

        # Encerrou a investigação: o texto livre vira achado, para que o trace do braço
        # de controle tenha a mesma estrutura de evidência que a avaliação já lê.
        summary = _text(response)
        if summary:
            trace.add_finding(agent="agente_unico", summary=summary)
        return {
            **updates,
            "scratch": [response],
            "findings": [*state.get("findings", []), f"[agente_unico] {summary}"],
            "worker_steps": 0,
        }

    def route_from_agente(state: CaseState) -> str:
        # Teto duro: como as tools seguem vinculadas no estouro de orçamento, um modelo
        # que ignore a instrução de parar continuaria pedindo consultas indefinidamente.
        # A política de parada precisa estar no grafo, não só no prompt.
        if state.get("worker_steps", 0) > max_steps:
            return "resolver"
        scratch = state.get("scratch") or []
        last = scratch[-1] if scratch else None
        return "tools" if getattr(last, "tool_calls", None) else "resolver"

    def resolver(state: CaseState) -> dict[str, Any]:
        """Formaliza a resolução do caso em `Decision`, sem tools.

        Não é um segundo papel: é a mesma cabeça produzindo saída estruturada para que o
        trace seja comparável ao do multiagente. O agente já pode ter executado ações
        durante a investigação — diferentemente do multiagente, aqui nada garante que a
        ação veio depois de uma decisão formal.
        """
        client.current_agent = "agente_unico"

        # O transcrito NÃO entra aqui. Esta chamada não vincula tools (a saída é
        # estruturada), e um histórico contendo tool calls faz o provedor recusar a
        # requisição inteira: "attempted to call tool X which was not in request.tools".
        # O que a decisão precisa é a evidência apurada, que já está em `findings` — é a
        # mesma coisa que o Decisor do multiagente recebe, o que mantém os braços
        # comparáveis neste ponto.
        findings = state.get("findings", [])
        apurado = "\n".join(f"- {f}" for f in findings) if findings else "(nada foi apurado)"

        result = llm.with_structured_output(Decision, include_raw=True).invoke(
            [
                SystemMessage(single_agent_prompt(case, state.get("user_context"), settings.evidence_policy)),
                HumanMessage(
                    f"EVIDÊNCIA APURADA POR VOCÊ:\n{apurado}\n\n"
                    "Formalize agora a resolução do caso: a categoria (orientar/agir/escalar), "
                    "a justificativa ancorada na evidência apurada, a ação executada ou "
                    "pretendida, e a resposta ao cliente."
                ),
            ]
        )

        if not isinstance(result, dict):
            decision = result
        else:
            trace.add_llm_call(agent="agente_unico", response=result.get("raw"))
            decision = result.get("parsed")
            if decision is None:
                raise ValueError(
                    f"O modelo não produziu um Decision válido: {result.get('parsing_error')}"
                )

        return {
            "decision": decision.model_dump(),
            "final_answer": decision.answer,
        }

    graph = StateGraph(CaseState)
    graph.add_node("agente", agente)
    graph.add_node("tools", ToolNode(all_tools, messages_key="scratch"))
    graph.add_node("resolver", resolver)

    graph.add_edge(START, "agente")
    graph.add_conditional_edges("agente", route_from_agente, {"tools": "tools", "resolver": "resolver"})
    graph.add_edge("tools", "agente")
    graph.add_edge("resolver", END)

    return graph.compile()
