"""Roda o EXP-07 — sensibilidade à evidência.

Três braços por caso (controle, decisivo, placebo), pareados por `(caso, seed)`, gravados em
`evaluation/results/traces/exp07/`. O diretório é próprio de propósito: um trace mutado não é
medida de referência e não pode entrar em média nenhuma junto com os 17 cenários.

    python solution/painel/rodar_exp07.py                 # os 4 casos, 12 execuções
    python solution/painel/rodar_exp07.py --casos A D      # só a metade prioritária
    python solution/painel/rodar_exp07.py --continuar      # pula o que já tem trace

Cada execução grava assim que termina. Se a cota acabar no meio, o que rodou está salvo e
`--continuar` retoma de onde parou.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "agent"))

from app.config import load_settings  # noqa: E402
from app.mutacao import CASOS_EXP07, SEED_EXP07, Bundle  # noqa: E402
from app.runner import get_case, run_case  # noqa: E402

DESTINO = RAIZ / "evaluation" / "results" / "traces" / "exp07"

# Letra do caso na seção 5 do EXP-07, na ordem de prioridade de CASOS_EXP07.
LETRAS = ("A", "D", "B", "C")


def nome_do_arquivo(caso: str, braco: str) -> str:
    """Um arquivo por (caso, braço). Reexecutar sobrescreve em vez de acumular duplicata."""
    return f"{caso}__{braco}__seed-{SEED_EXP07}.json"


def rodar(caso_id: str, braco: str, bundle: Bundle | None, *, continuar: bool) -> str:
    alvo = DESTINO / nome_do_arquivo(caso_id, braco)
    if continuar and alvo.exists():
        print(f"  [pulado] {caso_id} · {braco} (trace já existe)")
        return "pulado"

    settings = load_settings()
    trace = run_case(
        get_case(caso_id, settings),
        seed=SEED_EXP07,
        settings=settings,
        save_to=DESTINO,
        mutacao=bundle,
    )
    # O nome canônico substitui o timestamp de `Trace.save`: a análise endereça o trace por
    # (caso, braço), e um nome com hora obrigaria a varrer o diretório para achar o par.
    for gerado in DESTINO.glob(f"{caso_id}__seed-{SEED_EXP07}__*.json"):
        gerado.replace(alvo)

    estado = "ERRO" if trace.error else "ok"
    print(
        f"  [{estado}] {caso_id} · {braco:<9} decisão={trace.decision} "
        f"passos={len(trace.steps)} tokens={trace.token_usage['total_tokens']}"
    )
    if trace.error:
        print(f"          {trace.error[:160]}")
    return estado


def main() -> None:
    p = argparse.ArgumentParser(description="EXP-07 — sensibilidade à evidência")
    p.add_argument("--casos", nargs="*", default=list(LETRAS), help="letras: A B C D")
    p.add_argument("--continuar", action="store_true", help="pula execuções já gravadas")
    args = p.parse_args()

    escolhidos = [l.upper() for l in args.casos]
    DESTINO.mkdir(parents=True, exist_ok=True)

    print(f"EXP-07 · seed={SEED_EXP07} · destino={DESTINO.relative_to(RAIZ.parent)}")
    resultados: list[str] = []
    for letra, (caso_id, decisivo, placebo) in zip(LETRAS, CASOS_EXP07):
        if letra not in escolhidos:
            continue
        print(f"\ncaso {letra} — {caso_id}")
        # Ordem deliberada: o controle primeiro. Se a cota acabar no meio de um caso, o que
        # sobra é um par incompleto com o controle presente, que ainda é legível.
        for braco, bundle in (("controle", None), ("decisivo", decisivo), ("placebo", placebo)):
            resultados.append(rodar(caso_id, braco, bundle, continuar=args.continuar))

    erros = resultados.count("ERRO")
    print(f"\n{len(resultados)} execuções · {resultados.count('ok')} ok · {erros} com erro")
    if erros:
        print("Execuções com erro não entram na análise. Rode de novo com --continuar.")


if __name__ == "__main__":
    main()
