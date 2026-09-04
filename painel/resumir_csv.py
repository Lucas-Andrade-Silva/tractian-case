"""Recalcula `.run/resumo_por_cenario.csv` a partir do CSV de execuções.

O resumo agrega por (fase, cenário) e é a referência contra a qual `build_bundle.py
--verify` confere os agregados do painel. Quando o CSV de execuções muda — porque a
bateria ganhou execuções novas —, o resumo precisa acompanhar, senão a verificação passa a
comparar contra um retrato antigo e acusa divergência que não existe.

    python painel/resumir_csv.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parent.parent
CSV_EXECUCOES = REPO / ".run" / "resultados_avaliacao.csv"
CSV_RESUMO = REPO / ".run" / "resumo_por_cenario.csv"

COLUNAS = [
    "fase", "cenario", "ticket", "execucoes", "execucoes_validas", "decision_match",
    "passou", "acuracia_decisao", "taxa_aprovacao", "decisoes_observadas",
    "estavel_entre_seeds", "decisoes_aceitas", "recall_medio", "recall_min", "recall_max",
    "precisao_media", "tokens_input_medio", "tokens_output_medio", "tokens_total_medio",
]


def numero(valor: str) -> float | None:
    return float(valor) if valor not in ("", None) else None


def arredonda(valor: float | None, casas: int = 3) -> str:
    """Média vazia vira campo vazio, não 0 — ausência de medida não é zero."""
    if valor is None:
        return ""
    arredondado = round(valor, casas)
    return f"{arredondado:.1f}" if float(arredondado).is_integer() and casas == 3 else str(arredondado)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    with CSV_EXECUCOES.open(encoding="utf-8-sig", newline="") as fh:
        linhas = list(csv.DictReader(fh, delimiter=";"))

    # Agrupa por (fase, TICKET), não por cenário: CEN-07 cobre dois tickets
    # (TKT-INV-09 investiga → TKT-EXE-12 executa), e juntá-los somaria execuções de
    # casos distintos numa linha só.
    grupos: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for linha in linhas:
        grupos[(linha["fase"], linha["ticket"])].append(linha)

    saida = []
    for (fase, ticket), do_grupo in sorted(grupos.items()):
        cenario = do_grupo[0]["cenario"]
        # Só execuções que concluíram entram nas taxas, como em report.py.
        validas = [l for l in do_grupo if l["executou_sem_erro"] == "True"]
        acertos = sum(1 for l in validas if l["decision_match"] == "True")
        aprovadas = sum(1 for l in validas if l["passou"] == "True")

        decisoes = sorted({l["decisao"] for l in validas if l["decisao"]})
        recalls = [numero(l["evidence_recall"]) for l in validas]
        recalls = [r for r in recalls if r is not None]
        precisoes = [numero(l["precisao_consultas"]) for l in validas]
        precisoes = [p for p in precisoes if p is not None]

        def media_tokens(coluna: str) -> str:
            valores = [numero(l[coluna]) for l in validas]
            valores = [v for v in valores if v is not None]
            return str(int(mean(valores))) if valores else ""

        saida.append(
            {
                "fase": fase,
                "cenario": cenario,
                "ticket": ticket,
                "execucoes": str(len(do_grupo)),
                "execucoes_validas": str(len(validas)),
                "decision_match": str(acertos),
                "passou": str(aprovadas),
                "acuracia_decisao": arredonda(acertos / len(validas) if validas else None),
                "taxa_aprovacao": arredonda(aprovadas / len(validas) if validas else None),
                "decisoes_observadas": "|".join(decisoes),
                # Estável = uma única decisão entre as execuções que concluíram. Sem
                # nenhuma execução válida não há o que comparar: fica vazio, não False.
                "estavel_entre_seeds": str(len(decisoes) <= 1) if validas else "",
                "decisoes_aceitas": do_grupo[0]["decisoes_aceitas"],
                "recall_medio": arredonda(mean(recalls) if recalls else None),
                "recall_min": arredonda(min(recalls) if recalls else None),
                "recall_max": arredonda(max(recalls) if recalls else None),
                "precisao_media": arredonda(mean(precisoes) if precisoes else None),
                "tokens_input_medio": media_tokens("tokens_input"),
                "tokens_output_medio": media_tokens("tokens_output"),
                "tokens_total_medio": media_tokens("tokens_total"),
            }
        )

    with CSV_RESUMO.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=COLUNAS, delimiter=";", lineterminator="\r\n")
        escritor.writeheader()
        escritor.writerows(saida)

    print(f"{len(saida)} linhas de resumo a partir de {len(linhas)} execuções")
    for fase in ("baseline", "pos-correcao"):
        do_fase = [l for l in saida if l["fase"] == fase]
        execucoes = sum(int(l["execucoes"]) for l in do_fase)
        print(f"  {fase:14} {len(do_fase):2} cenários, {execucoes:3} execuções")
    print(f"gravado: {CSV_RESUMO.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
