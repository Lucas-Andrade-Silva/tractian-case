"""Ponto de entrada da avaliação (Parte 2).

    python -m runner.cli --seeds complete,s1,s2          # roda o agente e avalia
    python -m runner.cli --from-traces                   # só reavalia traces já gravados
    python -m runner.cli --cases TKT-INV-04,TKT-INV-05   # subconjunto
    python -m runner.cli --skip-judges                   # só a camada determinística

As camadas rodam na ordem da pirâmide (ADR 0005): a determinística é gratuita e roda
sempre; o comitê de juízes custa chamadas de LLM e pode ser desligado enquanto se itera
na camada de baixo.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import load_settings
from app.runner import load_cases, run_case

from .deterministic import evaluate_deterministic
from .golden import load_golden
from .judges import build_llm, judge_settings, run_committee
from .report import build_report, print_summary, save_report
from .stability import evaluate_stability

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
TRACES_DIR = RESULTS_DIR / "traces"


def _execute_runs(cases: list[dict[str, Any]], seeds: list[str | None], settings) -> list[dict[str, Any]]:
    """Roda o agente em cada combinação caso × seed e devolve os traces."""
    traces: list[dict[str, Any]] = []
    total = len(cases) * len(seeds)
    done = 0
    for case in cases:
        for seed in seeds:
            done += 1
            print(f"  [{done}/{total}] {case['ticket_id']} (seed={seed or 'none'}) ...", end=" ", flush=True)
            trace = run_case(case, seed=seed, settings=settings, save_to=TRACES_DIR)
            print(f"decisão={trace.decision or 'ERRO'} chamadas={len(trace.steps)}")
            traces.append(trace.to_dict())
    return traces


def _load_saved_traces() -> list[dict[str, Any]]:
    if not TRACES_DIR.exists():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(TRACES_DIR.glob("*.json"))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação do agente (3 camadas)")
    parser.add_argument("--seeds", default="complete", help="Seeds separadas por vírgula (>=3 para medir estabilidade)")
    parser.add_argument("--cases", default=None, help="Subconjunto de casos (ticket_id ou case_id), separados por vírgula")
    parser.add_argument("--from-traces", action="store_true", help="Não roda o agente; avalia traces já gravados")
    parser.add_argument("--skip-judges", action="store_true", help="Pula a camada 2 (não gasta LLM)")
    args = parser.parse_args()

    settings = load_settings()
    golden = load_golden()

    if args.from_traces:
        traces = _load_saved_traces()
        if not traces:
            raise SystemExit(f"Nenhum trace encontrado em {TRACES_DIR}. Rode sem --from-traces primeiro.")
        seeds_used = sorted({t.get("seed") or "none" for t in traces})
        print(f"\nAvaliando {len(traces)} traces já gravados em {TRACES_DIR}")
    else:
        seeds_used = [s.strip() or None for s in args.seeds.split(",")]
        wanted = {c.strip() for c in args.cases.split(",")} if args.cases else None
        cases = [
            c for c in load_cases(settings)
            # Só casos com gabarito: sem referência não há o que comparar na camada 1.
            if c["id"] in golden and (wanted is None or c["id"] in wanted or c["ticket_id"] in wanted)
        ]
        if not cases:
            raise SystemExit("Nenhum caso selecionado (verifique --cases e o gabarito).")
        print(f"\nExecutando {len(cases)} casos × {len(seeds_used)} seeds:")
        traces = _execute_runs(cases, seeds_used, settings)

    # -- Camada 1 ---------------------------------------------------------
    print("\nCamada 1 — determinística ...")
    deterministic = [
        evaluate_deterministic(trace, golden[trace["case_id"]])
        for trace in traces
        if trace.get("case_id") in golden
    ]

    # -- Camada 2 ---------------------------------------------------------
    judged: dict[str, dict[str, Any]] = {}
    if args.skip_judges:
        print("Camada 2 — comitê de juízes ... PULADA (--skip-judges)")
    else:
        print("Camada 2 — comitê de juízes ...")
        judge_llm = build_llm(judge_settings())
        for trace in traces:
            case_id = trace.get("case_id")
            if case_id not in golden:
                continue
            key = f"{case_id}__{trace.get('seed') or 'none'}"
            judged[key] = run_committee(trace, golden[case_id], llm=judge_llm)

    # -- Camada 3 ---------------------------------------------------------
    print("Camada 3 — estabilidade entre seeds ...")
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        by_case[trace["case_id"]].append(trace)
    stability = [evaluate_stability(runs) for runs in by_case.values()]
    if len(seeds_used) < 3:
        print("  aviso: estabilidade medida com menos de 3 seeds — indicativa, não conclusiva.")

    report = build_report(
        deterministic=deterministic,
        judged=judged,
        stability=stability,
        meta={
            "suite": "golden-set-16" if not args.cases else f"subset:{args.cases}",
            "model": f"{settings.llm_provider}:{settings.llm_model}",
            "judge_model": None if args.skip_judges else f"{judge_settings().llm_provider}:{judge_settings().llm_model}",
            "cases": len(by_case),
            "seeds": seeds_used,
        },
    )
    path = save_report(report, RESULTS_DIR)
    print_summary(report)
    print(f"relatório completo: {path}\n")


if __name__ == "__main__":
    main()
