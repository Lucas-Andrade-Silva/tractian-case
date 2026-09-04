"""EXP-05 — roda o braço de agente único e compara com o multiagente.

A hipótese do projeto ("separar investigação de decisão reduz ação sem fundamento e
over-escalation, ao custo de mais chamadas") nunca foi testada porque o braço de controle
não existia. Ele agora existe (`agent/app/single_graph.py`), e este script executa a
bateria desse braço sobre os MESMOS casos e seeds da fase `pos-correcao`, para que a
comparação seja pareada.

    python painel/rodar_exp05.py --listar          # o que falta rodar
    python painel/rodar_exp05.py                   # roda tudo o que falta
    python painel/rodar_exp05.py --limite 3        # roda 3 (cota curta)
    python painel/rodar_exp05.py --comparar        # só compara o que já existe

Retomável de propósito: cada execução é gravada assim que termina, e o que já está
gravado não se refaz. Bater na cota no meio não perde o trabalho anterior — foi
exatamente assim que a bateria original ficou pela metade.

O braço multiagente NÃO é reexecutado: as 51 execuções de `pos-correcao` já existem e
foram feitas com a mesma configuração de modelos. Rodar de novo só gastaria cota.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "agent"))

SEEDS = ("complete", "s2", "s3")
DESTINO = REPO / ".run" / "traces_exp05_single"
BUNDLE = REPO / "painel" / "dados" / "bundle.json"

# Braço de comparação: a fase mais recente do multiagente, mesma configuração de modelos.
FASE_MULTI = "pos-correcao"


def _segundos_sugeridos(erro: str, padrao: int) -> int:
    """Quanto esperar após um 429 — a própria API informa ('try again in 19.5s')."""
    achado = re.search(r"try again in ([\d.]+)s", erro)
    return int(float(achado.group(1))) + 5 if achado else padrao


def _casos_do_bundle() -> dict[str, str]:
    """Universo de casos da bateria multiagente: case_id → ticket_id."""
    dados = json.loads(BUNDLE.read_text(encoding="utf-8"))
    return {
        e["case_id"]: e["ticket_id"]
        for e in dados["execucoes"]
        if e["fase"] == FASE_MULTI
    }


def _ja_rodadas() -> set[tuple[str, str]]:
    """(case_id, seed) que já têm trace VÁLIDO do braço único.

    Um trace com `error` conta como pendente, não como preenchido: ele ocupa a célula sem
    produzir decisão, e uma bateria "completa" só de falhas pareceria medida.
    """
    if not DESTINO.exists():
        return set()
    feitas: set[tuple[str, str]] = set()
    for arquivo in DESTINO.glob("*.json"):
        try:
            t = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not t.get("error") and t.get("decision"):
            feitas.add((t["case_id"], t.get("seed") or ""))
    return feitas


def pendentes() -> list[tuple[str, str, str]]:
    casos = _casos_do_bundle()
    feitas = _ja_rodadas()
    return [
        (case_id, ticket, seed)
        for case_id, ticket in sorted(casos.items())
        for seed in SEEDS
        if (case_id, seed) not in feitas
    ]


# ---------------------------------------------------------------------------
# Comparação
# ---------------------------------------------------------------------------
def comparar() -> int:
    """Compara os dois braços, pareado por (caso, seed).

    Reaplica a camada 1 de `evaluation/runner/deterministic.py` aos traces do braço
    único, em vez de reimplementar as fórmulas: se a definição de `passou` mudar lá,
    muda aqui junto.
    """
    sys.path.insert(0, str(REPO / "evaluation"))
    from runner.deterministic import evaluate_deterministic  # type: ignore
    from runner.golden import load_golden  # type: ignore

    gabarito = load_golden()
    dados = json.loads(BUNDLE.read_text(encoding="utf-8"))

    multi = {
        (e["case_id"], e["seed"]): e["avaliacao"]
        for e in dados["execucoes"]
        if e["fase"] == FASE_MULTI and e["avaliacao"].get("executou_sem_erro")
    }

    single: dict[tuple[str, str], dict] = {}
    for arquivo in sorted(DESTINO.glob("*.json")) if DESTINO.exists() else []:
        t = json.loads(arquivo.read_text(encoding="utf-8"))
        if t.get("error") or not t.get("decision"):
            continue
        caso = gabarito.get(t["case_id"])
        if caso is None:
            continue
        r = evaluate_deterministic(t, caso)
        # Normaliza para o mesmo vocabulário do bundle, que é o do braço multiagente.
        single[(t["case_id"], t.get("seed") or "")] = {
            "decision_match": r.decision_match,
            "passou": r.passed,
            "evidence_recall": r.evidence_recall,
            "num_calls": r.num_calls,
            "repetition_rate": r.repetition_rate,
            "unexpected_actions": r.unexpected_actions,
            "missing_actions": r.missing_actions,
        }

    pares = sorted(set(multi) & set(single))
    if not pares:
        print("Nenhum par comparável ainda. Rode o braço único primeiro.")
        return 1

    def taxa(d: dict, campo: str) -> float:
        vals = [bool(d[k].get(campo)) for k in pares]
        return sum(vals) / len(vals)

    print(f"\nEXP-05 — comparação pareada, n = {len(pares)} pares (caso × seed)\n")
    print(f"{'métrica':28}{'multiagente':>14}{'agente único':>15}")
    print("-" * 57)
    for campo, rotulo in (("decision_match", "decisão correta"), ("passou", "aprovação (camada 1)")):
        print(f"{rotulo:28}{taxa(multi, campo):>13.1%}{taxa(single, campo):>15.1%}")

    # O bundle nomeia em português o que `DeterministicResult` nomeia em inglês.
    for campo_multi, campo_single, rotulo, fmt in (
        ("evidence_recall", "evidence_recall", "recall de evidência", ".1%"),
        ("chamadas_api", "num_calls", "chamadas de API", ".2f"),
        ("taxa_repeticao", "repetition_rate", "taxa de repetição", ".1%"),
    ):
        m = statistics.mean(multi[k].get(campo_multi) or 0 for k in pares)
        u = statistics.mean(single[k].get(campo_single) or 0 for k in pares)
        print(f"{rotulo:28}{m:>13{fmt}}{u:>15{fmt}}")

    # Ações indevidas: o desfecho central da hipótese. O multiagente afirma que a
    # transição fixa Decisor → Executor (ADR 0002) as previne.
    for campo_multi, campo_single, rotulo in (
        ("acoes_nao_previstas", "unexpected_actions", "c/ ação não prevista"),
        ("acoes_faltantes", "missing_actions", "c/ ação faltante"),
    ):
        m = sum(1 for k in pares if multi[k].get(campo_multi))
        u = sum(1 for k in pares if single[k].get(campo_single))
        print(f"{rotulo:28}{m:>13}{u:>15}")

    print()
    print("Discordâncias em decisão (multi → único):")
    houve = False
    for k in pares:
        a, b = multi[k].get("decision_match"), single[k].get("decision_match")
        if a != b:
            houve = True
            print(f"  {k[0]:20}{k[1]:10} {'✔' if a else '✘'} → {'✔' if b else '✘'}")
    if not houve:
        print("  (nenhuma)")
    print("\nEscreva a análise em docs/experimentos/EXP-05-multiagente-vs-agente-unico.md")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="EXP-05: braço de agente único")
    parser.add_argument("--listar", action="store_true", help="Só lista o que falta")
    parser.add_argument("--comparar", action="store_true", help="Só compara o que já existe")
    parser.add_argument("--limite", type=int, default=0, help="Executa no máximo N (0 = todas)")
    parser.add_argument("--pausa", type=int, default=45, help="Segundos entre execuções")
    parser.add_argument("--tentativas", type=int, default=2, help="Novas tentativas após 429")
    args = parser.parse_args()

    if args.comparar:
        return comparar()

    falta = pendentes()
    if not falta:
        print("Braço de agente único completo: 17 cenários × 3 seeds.")
        return comparar()

    print(f"Faltam {len(falta)} execuções do braço ÚNICO:")
    for _, ticket, seed in falta:
        print(f"  {ticket} · {seed}")
    if args.listar:
        return 0

    if args.limite:
        falta = falta[: args.limite]

    # A arquitetura é lida de `Settings`; forçamos aqui para que rodar este script não
    # dependa de lembrar de editar o .env — e para que um .env com `multi` não produza
    # silenciosamente 51 execuções do braço errado.
    os.environ["AGENT_ARCHITECTURE"] = "single"

    from app.config import load_settings
    from app.runner import load_cases, run_case

    settings = load_settings()
    if settings.architecture != "single":
        print("ERRO: a arquitetura não ficou em 'single'. Abortando para não medir o braço errado.")
        return 1

    casos = {c["id"]: c for c in load_cases(settings)}
    DESTINO.mkdir(parents=True, exist_ok=True)
    print(f"\nArquitetura: {settings.architecture} · gravando em {DESTINO.relative_to(REPO)}\n")

    concluidas = falhas = 0
    for indice, (case_id, ticket, seed) in enumerate(falta, 1):
        caso = casos.get(case_id)
        if caso is None:
            print(f"  [{indice}/{len(falta)}] {ticket} · {seed}: caso ausente em cases.json")
            falhas += 1
            continue

        if indice > 1 and args.pausa:
            time.sleep(args.pausa)

        print(f"  [{indice}/{len(falta)}] {ticket} · {seed} ...", end=" ", flush=True)

        trace = None
        for tentativa in range(1, args.tentativas + 2):
            try:
                trace = run_case(caso, seed=seed, settings=settings, save_to=DESTINO)
            except Exception as erro:  # noqa: BLE001 - uma falha não pode parar a bateria
                print(f"ERRO: {type(erro).__name__}")
                trace = None
                break
            if not trace.error or "rate_limit" not in str(trace.error).lower():
                break
            if tentativa <= args.tentativas:
                espera = _segundos_sugeridos(str(trace.error), args.pausa)
                print(f"429, aguardando {espera}s ...", end=" ", flush=True)
                time.sleep(espera)

        if trace is None or trace.error:
            motivo = str(trace.error)[:60] if trace else "sem trace"
            print(f"falhou ({motivo})")
            falhas += 1
        else:
            print(f"decisão={trace.decision} chamadas={len(trace.steps)}")
            concluidas += 1

    print(f"\n{concluidas} concluídas, {falhas} falharam.")
    if falhas:
        print("Rode de novo para retomar: execuções já gravadas não são refeitas.")
    if not pendentes():
        return comparar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
