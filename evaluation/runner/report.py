"""Agregação dos resultados das três camadas num relatório único.

Mantém as camadas separadas no resultado final de propósito: uma nota agregada única
esconderia justamente o diagnóstico que interessa — um agente pode acertar toda decisão
(camada 1) e ainda assim explicar mal (camada 2), ou acertar os dois e ser instável
(camada 3). São modos de falha diferentes, com correções diferentes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .deterministic import DeterministicResult
from .judges import COMMITTEE
from .stability import StabilityResult


def build_report(
    *,
    deterministic: list[DeterministicResult],
    judged: dict[str, dict[str, dict[str, Any]]],
    stability: list[StabilityResult],
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Monta o relatório completo a partir das três camadas."""
    executed = [d for d in deterministic if d.executed]

    layer1 = {
        "runs": len(deterministic),
        "execution_failures": len(deterministic) - len(executed),
        "decision_accuracy": _rate([d.decision_match for d in executed]),
        "deterministic_pass_rate": _rate([d.passed for d in executed]),
        "evidence_recall_mean": _mean([d.evidence_recall for d in executed]),
        "calls_mean": _mean([float(d.num_calls) for d in executed]),
        "repetition_rate_mean": _mean([d.repetition_rate for d in executed]),
        "runs_with_missing_actions": sum(1 for d in executed if d.missing_actions),
        "runs_with_unexpected_actions": sum(1 for d in executed if d.unexpected_actions),
        "runs_retrying_after_error": sum(1 for d in executed if d.retried_after_error),
    }

    layer2 = {}
    for judge in COMMITTEE:
        scores = [
            v[judge.key]["score"]
            for v in judged.values()
            if v.get(judge.key, {}).get("score") is not None
        ]
        layer2[judge.key] = {
            "title": judge.title,
            "judged_runs": len(scores),
            "mean_score": _mean([float(s) for s in scores]),
            "distribution": {str(n): scores.count(n) for n in range(1, 6)},
        }

    layer3 = {
        "cases": len(stability),
        "stable_cases": sum(1 for s in stability if s.stable),
        "stability_rate": _rate([s.stable for s in stability]),
        "agreement_rate_mean": _mean([s.agreement_rate for s in stability]),
        "trajectory_variation_mean": _mean([s.trajectory_variation for s in stability]),
        "unstable": [
            {"case_id": s.case_id, "decisions": s.distinct_decisions} for s in stability if not s.stable
        ],
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta,
        "layer1_deterministic": layer1,
        "layer2_judges": layer2,
        "layer3_stability": layer3,
        "per_run": [d.model_dump() for d in deterministic],
        "per_run_judges": judged,
        "per_case_stability": [s.model_dump() for s in stability],
    }


def save_report(report: dict[str, Any], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report["generated_at"].replace(":", "").replace("-", "")[:15]
    target = directory / f"report__{stamp}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def print_summary(report: dict[str, Any]) -> None:
    """Resumo legível no terminal — o JSON completo fica no arquivo."""
    l1, l2, l3 = report["layer1_deterministic"], report["layer2_judges"], report["layer3_stability"]

    print("\n" + "=" * 66)
    print("RELATÓRIO DE AVALIAÇÃO DO AGENTE")
    print("=" * 66)
    print(f"conjunto: {report['meta'].get('suite')}   modelo: {report['meta'].get('model')}")
    print(f"casos: {report['meta'].get('cases')}   seeds: {report['meta'].get('seeds')}")

    print("\n-- Camada 1 — determinística " + "-" * 37)
    print(f"  execuções:                    {l1['runs']} ({l1['execution_failures']} falharam)")
    print(f"  acurácia da decisão:          {_pct(l1['decision_accuracy'])}")
    print(f"  aprovação determinística:     {_pct(l1['deterministic_pass_rate'])}")
    print(f"  recall de evidência (médio):  {_pct(l1['evidence_recall_mean'])}")
    print(f"  chamadas por caso (média):    {l1['calls_mean']}")
    print(f"  repetição de chamadas:        {_pct(l1['repetition_rate_mean'])}")
    print(f"  ação esperada não executada:  {l1['runs_with_missing_actions']} execuções")
    print(f"  ação não prevista executada:  {l1['runs_with_unexpected_actions']} execuções")
    print(f"  insistiu após erro da API:    {l1['runs_retrying_after_error']} execuções")

    print("\n-- Camada 2 — comitê de juízes " + "-" * 35)
    for key, data in l2.items():
        score = data["mean_score"]
        print(f"  {data['title']:<32} {score if score is not None else '—'}/5  (n={data['judged_runs']})")

    print("\n-- Camada 3 — estabilidade entre seeds " + "-" * 27)
    print(f"  casos estáveis:               {l3['stable_cases']}/{l3['cases']}  ({_pct(l3['stability_rate'])})")
    print(f"  concordância média:           {_pct(l3['agreement_rate_mean'])}")
    print(f"  variação de trajetória:       {_pct(l3['trajectory_variation_mean'])} (reportada, não penalizada)")
    for unstable in l3["unstable"]:
        print(f"    instável: {unstable['case_id']} → {unstable['decisions']}")
    print("=" * 66 + "\n")


def _rate(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "—"
