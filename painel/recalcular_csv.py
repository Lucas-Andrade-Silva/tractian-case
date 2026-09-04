"""Recalcula `.run/resultados_avaliacao.csv` a partir dos traces em disco.

O CSV é a tabela de métricas por execução, e é ele que dá a fase a cada trace. Quando a
bateria ganha execuções novas — por `painel/completar_fase.py`, por exemplo — os traces
existem mas não aparecem no painel até o CSV ser refeito.

Aplica a camada 1 de `evaluation/runner/deterministic.py` a cada trace, em vez de reescrever
as fórmulas: se a definição de `passou` ou de `evidence_recall` mudar lá, muda aqui junto.
A única métrica calculada localmente é `precisao_consultas`, que não existe no código da
avaliação — é derivada, e o painel a rotula como tal.

    python painel/recalcular_csv.py --fase pos-correcao   # refaz só essa fase
    python painel/recalcular_csv.py --conferir            # não grava, só compara

Traces mais novos vencem quando há mais de um para o mesmo (caso, seed) na mesma fase: as
reexecuções foram feitas justamente para substituir as anteriores.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(REPO / "evaluation"))

CSV_EXECUCOES = REPO / ".run" / "resultados_avaliacao.csv"
RAIZES_TRACE = [REPO / ".run", REPO / "agent" / ".run"]

# Qual diretório de trace pertence a qual fase. É a informação que o trace não grava; a
# correção de fundo seria gravá-la em agent/app/trace.py.
FASE_POR_PASTA = {
    "traces_restantes": "baseline",
    "traces_exp_fixed": "baseline",
    "traces_2_mais": "baseline",
    "traces_fix_executor": "baseline",
    "traces_2_novos": "baseline",
    "traces_fix_policy": "pos-correcao",
    "traces_fix_policy2": "pos-correcao",
}

COLUNAS = [
    "fase", "cenario", "ticket", "seed", "case_id", "ativo", "usuario",
    "decisao", "decisoes_aceitas", "cenario_ambiguo", "decision_match", "passou",
    "evidence_recall", "precisao_consultas", "gets_feitos", "gets_esperados",
    "queries_faltantes", "queries_extras", "acoes_exigidas", "acoes_executadas",
    "acoes_faltantes", "acoes_nao_previstas", "tokens_input", "tokens_output",
    "tokens_total", "chamadas_api", "chamadas_repetidas", "taxa_repeticao",
    "erros_http", "justificativa_len", "executou_sem_erro", "erro_execucao",
]


def ler_csv_atual() -> list[dict[str, str]]:
    with CSV_EXECUCOES.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def fracao(valor: float | None) -> str:
    """Fração com casa decimal — o CSV grava 1.0 e 0.0, não 1 e 0."""
    if valor is None:
        return ""
    return f"{valor:.1f}" if float(valor).is_integer() else str(round(valor, 3))


def precisao_consultas(gets_feitos: int, extras: list[str]) -> float | None:
    """Métrica derivada, ausente do código da avaliação.

    (GETs feitos − GETs extras) / GETs feitos, sem contar `GET /users/me`, que é contexto
    de sessão e não apuração de evidência.
    """
    if not gets_feitos:
        return None
    fora = [q for q in extras if q != "GET /users/me"]
    return round((gets_feitos - len(fora)) / gets_feitos, 3)


def traces_por_fase() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Trace mais recente de cada (fase, case_id, seed)."""
    escolhidos: dict[tuple[str, str, str], dict[str, Any]] = {}
    for raiz in RAIZES_TRACE:
        if not raiz.exists():
            continue
        for arquivo in sorted(raiz.glob("traces_*/*.json")):
            fase = FASE_POR_PASTA.get(arquivo.parent.name)
            if fase is None:
                continue  # pasta de experimento, fora das duas fases
            trace = json.loads(arquivo.read_text(encoding="utf-8"))
            chave = (fase, trace.get("case_id"), trace.get("seed"))
            anterior = escolhidos.get(chave)
            if anterior is None or trace.get("started_at", "") > anterior.get("started_at", ""):
                escolhidos[chave] = trace
    return escolhidos


def linha_para(fase: str, trace: dict[str, Any], cenario: str, golden) -> dict[str, str]:
    from runner.deterministic import evaluate_deterministic

    resultado = evaluate_deterministic(trace, golden)
    consumo = trace.get("token_usage") or {}
    gets = [s for s in trace.get("path_taken", []) if s.startswith("GET ")]

    return {
        "fase": fase,
        "cenario": cenario,
        "ticket": trace.get("ticket_id", ""),
        "seed": trace.get("seed") or "",
        "case_id": trace.get("case_id", ""),
        "ativo": trace.get("asset_id") or "",
        "usuario": trace.get("user_id") or "",
        "decisao": trace.get("decision") or "",
        "decisoes_aceitas": "|".join(resultado.accepted_decisions),
        "cenario_ambiguo": str(resultado.ambiguous_scenario),
        "decision_match": str(resultado.decision_match),
        "passou": str(resultado.passed),
        "evidence_recall": fracao(resultado.evidence_recall),
        "precisao_consultas": fracao(precisao_consultas(len(gets), resultado.extra_queries)),
        "gets_feitos": str(len(gets)),
        "gets_esperados": str(len(golden.expected_queries)),
        "queries_faltantes": "|".join(resultado.missing_queries),
        "queries_extras": "|".join(resultado.extra_queries),
        "acoes_exigidas": "|".join(resultado.required_actions),
        "acoes_executadas": "|".join(resultado.executed_actions),
        "acoes_faltantes": "|".join(resultado.missing_actions),
        "acoes_nao_previstas": "|".join(resultado.unexpected_actions),
        "tokens_input": str(consumo.get("input_tokens", "")),
        "tokens_output": str(consumo.get("output_tokens", "")),
        "tokens_total": str(consumo.get("total_tokens", "")),
        "chamadas_api": str(resultado.num_calls),
        "chamadas_repetidas": str(resultado.repeated_calls),
        "taxa_repeticao": fracao(resultado.repetition_rate),
        "erros_http": str(resultado.http_errors),
        "justificativa_len": str(resultado.justification_length),
        "executou_sem_erro": str(resultado.executed),
        "erro_execucao": (trace.get("error") or "")[:200],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Recalcula o CSV de execuções")
    parser.add_argument("--fase", choices=("baseline", "pos-correcao"), help="Refaz só esta fase")
    parser.add_argument("--conferir", action="store_true", help="Não grava; só compara")
    args = parser.parse_args()

    from runner.golden import load_golden

    gabarito = load_golden()
    atuais = ler_csv_atual()
    # `cenario` (CEN-xx) não existe em nenhum JSON: vem do CSV e é preservado.
    cenarios = {l["case_id"]: l["cenario"] for l in atuais}

    escolhidos = traces_por_fase()
    novas: list[dict[str, str]] = []
    for (fase, case_id, seed), trace in sorted(escolhidos.items()):
        if args.fase and fase != args.fase:
            continue
        golden = gabarito.get(case_id)
        if golden is None:
            continue
        novas.append(linha_para(fase, trace, cenarios.get(case_id, ""), golden))

    # Fases não recalculadas ficam como estão.
    preservadas = [l for l in atuais if args.fase and l["fase"] != args.fase]
    saida = sorted(preservadas + novas, key=lambda l: (l["fase"], l["cenario"], l["seed"]))

    antes = {(l["fase"], l["case_id"], l["seed"]) for l in atuais}
    depois = {(l["fase"], l["case_id"], l["seed"]) for l in saida}
    print(f"execuções: {len(atuais)} → {len(saida)}")
    for chave in sorted(depois - antes):
        print(f"  + {chave[0]} {chave[1]} {chave[2]}")
    for chave in sorted(antes - depois):
        print(f"  − {chave[0]} {chave[1]} {chave[2]}")

    if args.conferir:
        print("\n(--conferir: nada gravado)")
        return 0

    with CSV_EXECUCOES.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUNAS, delimiter=";", lineterminator="\r\n")
        escritor.writeheader()
        escritor.writerows(saida)

    print(f"\ngravado: {CSV_EXECUCOES.relative_to(REPO)}")
    print("Depois: python painel/resumir_csv.py && python painel/build_bundle.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
