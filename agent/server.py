"""Ponto de entrada do agente pela linha de comando.

Uso:
    python -m app.runner --case TKT-INV-04 --seed complete   # roda um caso
    python server.py --list                                  # lista os casos disponíveis

O `make up-agent` do Makefile aponta para este arquivo. Ele não sobe um servidor HTTP:
o contexto de uso declarado é autônomo com escopo (o agente decide e executa dentro do
que a permissão do usuário autoriza), acionado por caso, não por conversa interativa.
"""
from __future__ import annotations

import argparse

from app.config import load_settings
from app.runner import get_case, load_cases, run_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de suporte industrial Tractian")
    parser.add_argument("--list", action="store_true", help="Lista os casos de agent-input/cases.json")
    parser.add_argument("--case", help="case_id ou ticket_id a executar")
    parser.add_argument("--seed", default=None, help="Seed da API (reprodutibilidade)")
    args = parser.parse_args()

    settings = load_settings()

    if args.list or not args.case:
        print(f"\nCasos disponíveis ({settings.cases_path}):\n")
        for case in load_cases(settings):
            print(f"  {case['ticket_id']:<14} {case['id']:<20} {case.get('asset_id', '-'):<12} {case['message'][:60]}")
        print("\nRode um caso:  python -m app.runner --case TKT-INV-04 --seed complete\n")
        return

    trace = run_case(get_case(args.case, settings), seed=args.seed, settings=settings)
    print(f"decisão={trace.decision}  chamadas={len(trace.steps)}  parada={trace.stop_reason}")
    if trace.error:
        print(f"erro: {trace.error}")


if __name__ == "__main__":
    main()
