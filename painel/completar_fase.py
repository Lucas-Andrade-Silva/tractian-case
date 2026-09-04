"""Reexecuta as combinações caso × seed que faltam numa fase.

A bateria de pós-correção parou no meio por limite de cota, e o resultado é uma comparação
entre fases com bases diferentes: o baseline tem 17 cenários × 3 seeds, a pós-correção tem
menos. Comparar taxas apuradas sobre conjuntos diferentes de cenários não mede o efeito da
correção — mede a diferença entre as amostras.

Este script fecha essa lacuna executando **apenas o que falta**. É retomável de propósito:
cada execução é gravada assim que termina, então bater na cota no meio não perde o que já
foi feito — basta rodar de novo depois. Foi exatamente assim que a lacuna surgiu.

    python painel/completar_fase.py --fase pos-correcao          # o que falta
    python painel/completar_fase.py --fase pos-correcao --listar # só mostra, não roda

Depois: `python painel/build_bundle.py --verify` para o painel enxergar as novas execuções.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agent"))

SEEDS = ("complete", "s2", "s3")
CSV_EXECUCOES = REPO / ".run" / "resultados_avaliacao.csv"

# Cada fase tem seu diretório de destino. Os traces novos precisam cair num lugar que o
# build varre, e separados dos da fase anterior.
DESTINO = {
    "pos-correcao": REPO / ".run" / "traces_fix_policy2",
    "baseline": REPO / ".run" / "traces_restantes",
}


def _segundos_sugeridos(erro: str, padrao: int) -> int:
    """Quanto esperar após um 429. A própria API informa ('try again in 19.5s')."""
    achado = re.search(r"try again in ([\d.]+)s", erro)
    return int(float(achado.group(1))) + 5 if achado else padrao


def le_csv() -> list[dict[str, str]]:
    with CSV_EXECUCOES.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def faltantes(fase: str, incluir_falhas: bool = True) -> list[tuple[str, str, str]]:
    """Combinações (case_id, ticket_id, seed) que ainda não têm resultado nesta fase.

    Uma execução que quebrou por cota conta como pendente, não como preenchida: ela ocupa a
    célula na matriz mas não produz decisão, e o painel a exibe como falha de execução. Uma
    fase "completa" só de falhas seria pior que a lacuna original — pareceria medida.
    """
    linhas = le_csv()
    presentes = {
        (l["case_id"], l["seed"])
        for l in linhas
        if l["fase"] == fase and (not incluir_falhas or l["executou_sem_erro"] == "True")
    }
    # O universo de casos vem do CSV inteiro: são os cenários que a bateria cobre.
    casos = {l["case_id"]: l["ticket"] for l in linhas}

    return [
        (case_id, ticket, seed)
        for case_id, ticket in sorted(casos.items())
        for seed in SEEDS
        if (case_id, seed) not in presentes
    ]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Completa as execuções faltantes de uma fase")
    parser.add_argument("--fase", default="pos-correcao", choices=sorted(DESTINO))
    parser.add_argument("--listar", action="store_true", help="Só lista o que falta")
    parser.add_argument("--limite", type=int, default=0, help="Executa no máximo N (0 = todas)")
    # O limite da Groq no plano gratuito é por MINUTO (8000 TPM no menor modelo), e uma
    # execução consome ~20k tokens somando os papéis. Sem pausa entre execuções a segunda
    # já bate no teto — foi o que interrompeu a bateria original. A pausa custa tempo e
    # evita perder a execução inteira por 429.
    parser.add_argument("--pausa", type=int, default=45, help="Segundos entre execuções")
    parser.add_argument("--tentativas", type=int, default=2, help="Novas tentativas após 429")
    args = parser.parse_args()

    pendentes = faltantes(args.fase)
    if not pendentes:
        print(f"Fase '{args.fase}' já está completa: 17 cenários × 3 seeds.")
        return 0

    print(f"Faltam {len(pendentes)} execuções em '{args.fase}':")
    for _, ticket, seed in pendentes:
        print(f"  {ticket} · {seed}")
    if args.listar:
        return 0

    if args.limite:
        pendentes = pendentes[: args.limite]

    # Import tardio: `--listar` não deve exigir LLM configurado.
    from app.config import load_settings
    from app.runner import load_cases, run_case

    settings = load_settings()
    casos = {c["id"]: c for c in load_cases(settings)}
    destino = DESTINO[args.fase]

    print(f"\nGravando em {destino.relative_to(REPO)}\n")
    concluidas = falhas = 0

    for indice, (case_id, ticket, seed) in enumerate(pendentes, 1):
        caso = casos.get(case_id)
        if caso is None:
            print(f"  [{indice}/{len(pendentes)}] {ticket} · {seed}: caso ausente em cases.json")
            falhas += 1
            continue

        if indice > 1 and args.pausa:
            time.sleep(args.pausa)

        print(f"  [{indice}/{len(pendentes)}] {ticket} · {seed} ...", end=" ", flush=True)

        trace = None
        for tentativa in range(1, args.tentativas + 2):
            try:
                trace = run_case(caso, seed=seed, settings=settings, save_to=destino)
            except Exception as erro:  # noqa: BLE001 - uma falha não pode parar a bateria
                print(f"ERRO: {type(erro).__name__}")
                trace = None
                break

            if not trace.error or "rate_limit" not in str(trace.error).lower():
                break
            # 429 por minuto: a janela reabre sozinha, então esperar e repetir recupera a
            # execução em vez de deixar um buraco na fase.
            if tentativa <= args.tentativas:
                espera = _segundos_sugeridos(str(trace.error), args.pausa)
                print(f"429, aguardando {espera}s ...", end=" ", flush=True)
                time.sleep(espera)

        if trace is None:
            falhas += 1
        elif trace.error:
            # Execução que quebrou: fica gravada, mas não conta como preenchida — o painel
            # a trataria como falha de execução, não como decisão.
            print(f"falhou ({str(trace.error)[:60]})")
            falhas += 1
        else:
            print(f"decisão={trace.decision} chamadas={len(trace.steps)}")
            concluidas += 1

    print(f"\n{concluidas} concluídas, {falhas} falharam.")
    if falhas:
        print("Rode de novo para retomar: execuções já gravadas não são refeitas.")
    print("Depois: python painel/build_bundle.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
