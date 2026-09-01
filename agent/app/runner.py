"""Execução de um caso de ponta a ponta, com trace gravado.

Ponto de entrada tanto do uso manual (`python -m app.runner --case ...`) quanto da
Parte 2, que roda cenários em lote e lê os traces resultantes.

Só lê `agent-input/cases.json`. O gabarito (`eval/`) nunca é tocado aqui — se entrasse
no contexto do agente, a avaliação perderia validade.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .api_client import ApiClient
from .config import Settings, load_settings
from .graph import build_graph
from .llm import RoleModels
from .tools import action_tools, investigation_tools, knowledge_tools
from .trace import Trace


def load_cases(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or load_settings()
    return json.loads(settings.cases_path.read_text(encoding="utf-8"))


def get_case(case_id: str, settings: Settings | None = None) -> dict[str, Any]:
    for case in load_cases(settings):
        if case["id"] == case_id or case.get("ticket_id") == case_id:
            return case
    raise KeyError(f"Caso não encontrado em agent-input/cases.json: {case_id}")


def run_case(
    case: dict[str, Any],
    *,
    seed: str | None = None,
    settings: Settings | None = None,
    save_to: Path | None = None,
) -> Trace:
    """Roda o agente sobre um caso e devolve o trace da execução.

    Falhas de execução (LLM indisponível, erro inesperado) não são silenciadas: ficam
    registradas no próprio trace, para que a avaliação distinga "o agente decidiu mal"
    de "a execução quebrou".
    """
    settings = settings or load_settings()

    trace = Trace(
        case_id=case["id"],
        ticket_id=case.get("ticket_id", ""),
        seed=seed,
        user_id=case["user_id"],
        asset_id=case.get("asset_id"),
        message=case["message"],
        # Preenchido com o mapa papel->modelo depois de resolver os modelos.
        model=settings.llm_provider,
    )

    with ApiClient(
        base_url=settings.api_base_url,
        user_id=case["user_id"],
        trace=trace,
        seed=seed,
        timeout_s=settings.request_timeout_s,
    ) as client:
        try:
            models = RoleModels(settings)
            # Registra a configuração efetiva: sem ela, comparar duas rodadas depois
            # depende de lembrar o que estava no .env na hora.
            trace.model = json.dumps(
                {**models.describe(), "_evidence_policy": settings.evidence_policy},
                ensure_ascii=False,
            )
            graph = build_graph(
                models=models,
                client=client,
                settings=settings,
                case=case,
                trace=trace,
                investigation_tools=investigation_tools(client),
                knowledge_tools=knowledge_tools(client),
                action_tools=action_tools(client, case["id"]),
            )
            # Teto de segurança do próprio LangGraph, acima dos orçamentos do agente.
            recursion_limit = settings.max_supervisor_turns * (settings.max_worker_steps + 3) + 10
            final_state = graph.invoke(
                {
                    "case": case,
                    # A mensagem do cliente já vai no prompt de cada papel (bloco do
                    # caso); o scratch começa vazio e pertence ao papel que trabalhar.
                    "scratch": [],
                    "findings": [],
                    "supervisor_turns": 0,
                    "worker_steps": 0,
                },
                config={"recursion_limit": recursion_limit},
            )
            decision = final_state.get("decision") or {}
            trace.close(
                decision=decision.get("decision"),
                justification=decision.get("justification"),
                final_answer=final_state.get("final_answer"),
                stop_reason=final_state.get("stop_reason") or "concluido",
            )
        except Exception as exc:  # noqa: BLE001 - a falha precisa virar dado da avaliação
            trace.close(
                decision=None,
                justification=None,
                final_answer=None,
                stop_reason="erro_execucao",
                error=f"{type(exc).__name__}: {exc}",
            )

    destination = save_to or settings.traces_dir
    trace.save(destination)
    return trace


def main() -> None:
    parser = argparse.ArgumentParser(description="Roda o agente sobre um caso de agent-input/cases.json")
    parser.add_argument("--case", required=True, help="case_id ou ticket_id (ex.: case_tkt_inv_04 / TKT-INV-04)")
    parser.add_argument("--seed", default=None, help="Seed da API para tornar a execução reprodutível")
    args = parser.parse_args()

    settings = load_settings()
    trace = run_case(get_case(args.case, settings), seed=args.seed, settings=settings)

    print(f"\ncaso:      {trace.case_id} ({trace.ticket_id})")
    print(f"decisão:   {trace.decision}")
    print(f"parada:    {trace.stop_reason}")
    if trace.error:
        print(f"ERRO:      {trace.error}")
    print(f"chamadas:  {len(trace.steps)}")
    for step in trace.steps:
        flag = "" if step.ok else "  <-- FALHOU"
        print(f"  [{step.agent:<16}] {step.step}  (mode={step.mode}, {step.status_code}){flag}")
    print(f"\nresposta:\n{trace.final_answer}\n")


if __name__ == "__main__":
    main()
