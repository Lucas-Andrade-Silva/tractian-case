"""Grafo multiagente do agente de suporte (ADR 0001 e ADR 0002).

    START → supervisor ─┬→ investigador ⇄ tools ─┐
                        ├→ contextualizador ⇄ tools ─┤→ supervisor
                        └→ decisor ─┬→ (orientar) ──────────────→ END
                                    └→ (agir|escalar) → executor ⇄ tools → END

Roteamento híbrido: o LLM escolhe entre investigar, contextualizar e decidir; a
transição Decisor → Executor é fixa em código e só ocorre sobre uma decisão formal.
Isso garante estruturalmente — não por disciplina de prompt — que nenhuma ação de
impacto aconteça sem ter passado pelo Decisor.

Orçamentos (`max_supervisor_turns`, `max_worker_steps`) são a política de parada: sem
eles um agente pode investigar indefinidamente e nunca responder nem escalar. Ao estourar
o orçamento, o papel é chamado SEM tools, o que o obriga a produzir texto e encerrar.
"""
from __future__ import annotations

from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .api_client import ApiClient
from .config import Settings
from .prompts import (
    contextualizer_prompt,
    decider_prompt,
    executor_prompt,
    investigator_prompt,
    supervisor_prompt,
)
from .state import CaseState, Decision, Route
from .trace import Trace


def _text(message: AnyMessage) -> str:
    """Extrai texto de uma mensagem, tolerando provedores que devolvem blocos."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


def _clear(messages: list[AnyMessage]) -> list[RemoveMessage]:
    """Instruções para esvaziar o scratch — o reducer `add_messages` aplica as remoções."""
    return [RemoveMessage(id=m.id) for m in messages if getattr(m, "id", None)]


def _findings_block(findings: list[str]) -> str:
    """Evidência já apurada, no formato compacto que atravessa papéis."""
    if not findings:
        return "EVIDÊNCIA JÁ APURADA: (nenhuma ainda)"
    return "EVIDÊNCIA JÁ APURADA:\n" + "\n".join(f"- {f}" for f in findings)


def build_graph(
    *,
    llm: BaseChatModel,
    client: ApiClient,
    settings: Settings,
    case: dict[str, Any],
    trace: Trace,
    investigation_tools: list,
    knowledge_tools: list,
    action_tools: list,
):
    """Compila o grafo para um caso. As dependências entram por parâmetro para manter
    o grafo testável e sem estado global."""

    # -- Supervisor -------------------------------------------------------
    def supervisor(state: CaseState) -> dict[str, Any]:
        client.current_agent = "supervisor"
        updates: dict[str, Any] = {}

        # Contexto de autorização: estabelecido uma única vez, no início do atendimento.
        user_context = state.get("user_context")
        if user_context is None:
            result = client.request("GET", "/users/me", with_seed=False)
            user_context = result.get("data") if result.get("ok") else {"erro": result.get("error")}
            updates["user_context"] = user_context

        turn = state.get("supervisor_turns", 0) + 1
        updates["supervisor_turns"] = turn

        # Política de parada: esgotado o orçamento, a decisão é forçada.
        if turn > settings.max_supervisor_turns:
            trace.add_routing(
                turn=turn,
                source="supervisor",
                target="decisor",
                reason="orçamento de turnos esgotado — decisão forçada",
            )
            return {**updates, "next_role": "decisor", "stop_reason": "budget_supervisor"}

        # O Supervisor decide sobre a evidência resumida, não sobre o transcrito bruto:
        # é o que ele precisa para rotear, e mantém o custo do roteamento constante.
        route = llm.with_structured_output(Route).invoke(
            [
                SystemMessage(supervisor_prompt(case, user_context)),
                HumanMessage(
                    f"{_findings_block(state.get('findings', []))}\n\n"
                    "Qual papel deve agir agora? Responda apenas com a rota."
                ),
            ]
        )
        trace.add_routing(turn=turn, source="supervisor", target=route.next, reason=route.reason)
        return {**updates, "next_role": route.next}

    def route_from_supervisor(state: CaseState) -> str:
        return state.get("next_role") or "decisor"

    # -- Workers (Investigador / Contextualizador) ------------------------
    def make_worker(role: str, tools: list, prompt_fn: Callable[[dict[str, Any]], str]):
        """Nó de papel que apura evidência com tools e encerra com um resumo."""

        def worker(state: CaseState) -> dict[str, Any]:
            client.current_agent = role
            scratch = state.get("scratch", [])
            reset: list[Any] = []

            # Assumindo o scratch de outro papel: descarta o transcrito dele e começa
            # limpo. O que o papel anterior apurou chega pelos `findings`.
            if state.get("scratch_owner") != role:
                reset = _clear(scratch)
                scratch = []

            steps = state.get("worker_steps", 0)
            # Estourou o orçamento: chama sem tools para forçar o encerramento em texto.
            over_budget = steps >= settings.max_worker_steps
            model = llm if over_budget else llm.bind_tools(tools)

            messages: list[AnyMessage] = [
                SystemMessage(prompt_fn(case)),
                HumanMessage(_findings_block(state.get("findings", []))),
                *scratch,
            ]
            if over_budget:
                messages.append(
                    HumanMessage(
                        "Orçamento de investigação esgotado. Não chame mais tools: "
                        "resuma agora os achados obtidos até aqui."
                    )
                )
            response = model.invoke(messages)

            if getattr(response, "tool_calls", None):
                return {
                    "scratch": [*reset, response],
                    "scratch_owner": role,
                    "worker_steps": steps + 1,
                }

            summary = _text(response) or "(sem resumo)"
            trace.add_finding(agent=role, summary=summary)
            return {
                "scratch": [*reset, response],
                # Libera o scratch: o resumo já está em `findings`, e o próximo papel a
                # assumir descarta o transcrito em vez de carregá-lo adiante.
                "scratch_owner": None,
                "findings": [*state.get("findings", []), f"[{role}] {summary}"],
                "worker_steps": 0,
            }

        return worker

    def route_from_worker(state: CaseState) -> str:
        scratch = state.get("scratch") or []
        last = scratch[-1] if scratch else None
        return "tools" if getattr(last, "tool_calls", None) else "supervisor"

    # -- Decisor ----------------------------------------------------------
    def decisor(state: CaseState) -> dict[str, Any]:
        client.current_agent = "decisor"
        decision: Decision = llm.with_structured_output(Decision).invoke(
            [
                SystemMessage(
                    decider_prompt(case, state.get("user_context"), state.get("findings", []))
                ),
                HumanMessage("Resolva o caso agora, com base apenas na evidência apurada."),
            ]
        )
        payload = decision.model_dump()
        return {
            "decision": payload,
            "final_answer": decision.answer,
            "findings": [
                *state.get("findings", []),
                f"[decisor] resolução={decision.decision}; ação={decision.intended_action}",
            ],
        }

    def route_from_decision(state: CaseState) -> str:
        """Transição fixa por código (ADR 0002): só uma decisão formal abre o Executor."""
        decision = (state.get("decision") or {}).get("decision")
        return "executor" if decision in ("agir", "escalar") else END

    # -- Executor ---------------------------------------------------------
    def executor(state: CaseState) -> dict[str, Any]:
        client.current_agent = "executor"
        scratch = state.get("scratch", [])
        reset: list[Any] = []
        if state.get("scratch_owner") != "executor":
            reset = _clear(scratch)
            scratch = []

        steps = state.get("worker_steps", 0)
        over_budget = steps >= settings.max_worker_steps
        model = llm if over_budget else llm.bind_tools(action_tools)

        messages: list[AnyMessage] = [
            SystemMessage(executor_prompt(case, state.get("decision") or {})),
            *scratch,
        ]
        if over_budget:
            messages.append(
                HumanMessage("Não chame mais tools. Escreva a resposta final ao cliente.")
            )
        response = model.invoke(messages)

        if getattr(response, "tool_calls", None):
            return {
                "scratch": [*reset, response],
                "scratch_owner": "executor",
                "worker_steps": steps + 1,
            }

        return {
            "scratch": [*reset, response],
            "scratch_owner": None,
            "final_answer": _text(response) or state.get("final_answer"),
            "worker_steps": 0,
        }

    def route_from_executor(state: CaseState) -> str:
        scratch = state.get("scratch") or []
        last = scratch[-1] if scratch else None
        return "tools" if getattr(last, "tool_calls", None) else END

    # -- Montagem ---------------------------------------------------------
    graph = StateGraph(CaseState)

    graph.add_node("supervisor", supervisor)
    graph.add_node("investigador", make_worker("investigador", investigation_tools, investigator_prompt))
    graph.add_node("investigador_tools", ToolNode(investigation_tools, messages_key="scratch"))
    graph.add_node("contextualizador", make_worker("contextualizador", knowledge_tools, contextualizer_prompt))
    graph.add_node("contextualizador_tools", ToolNode(knowledge_tools, messages_key="scratch"))
    graph.add_node("decisor", decisor)
    graph.add_node("executor", executor)
    graph.add_node("executor_tools", ToolNode(action_tools, messages_key="scratch"))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "investigador": "investigador",
            "contextualizador": "contextualizador",
            "decisor": "decisor",
        },
    )
    graph.add_conditional_edges(
        "investigador",
        route_from_worker,
        {"tools": "investigador_tools", "supervisor": "supervisor"},
    )
    graph.add_edge("investigador_tools", "investigador")
    graph.add_conditional_edges(
        "contextualizador",
        route_from_worker,
        {"tools": "contextualizador_tools", "supervisor": "supervisor"},
    )
    graph.add_edge("contextualizador_tools", "contextualizador")
    graph.add_conditional_edges("decisor", route_from_decision, {"executor": "executor", END: END})
    graph.add_conditional_edges("executor", route_from_executor, {"tools": "executor_tools", END: END})
    graph.add_edge("executor_tools", "executor")

    return graph.compile()
