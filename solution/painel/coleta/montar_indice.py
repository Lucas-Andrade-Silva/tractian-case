"""Cruza a leitura de vibracao (ativos.json) com o que o agente fez (bundle.json).

A juncao e por `operacao.asset_id`: cada execucao do agente aconteceu sobre um ativo
concreto, na mesma seed em que a API degradou aquele ativo. E o que permite dizer, na
tela do ativo, "o cenario que este ativo reproduziu".

Nem todo ativo tem cenario — 10 dos 26 tem. Os demais recebem uma entrada vazia
explicita, porque esconde-los faria a lista mentir sobre a cobertura da bateria.

Saida: dados/agente.json, consumido por leitura.html.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

PAINEL = Path(__file__).resolve().parent.parent
BUNDLE = PAINEL / "dados" / "bundle.json"
ATIVOS = PAINEL / "dados" / "ativos.json"
SAIDA = PAINEL / "dados" / "agente.json"

# A fase que a página apresenta como resultado corrente, e aquela contra a qual o custo
# é comparado. Ambas configuráveis: rodar uma bateria numa política nova não deve exigir
# editar código para vê-la (`FASE=conditional make leitura-dados`).
FASE = os.getenv("FASE", "").strip() or "pos-correcao"
FASE_ANTERIOR = os.getenv("FASE_ANTERIOR", "").strip() or "baseline"

# Contra qual fase cada uma compara o custo. `pos-correcao` mede o efeito da correcao
# sobre o baseline; uma bateria de politica mede o efeito sobre a producao, que e
# `pos-correcao` — comparar com o baseline misturaria dois efeitos.
ANTERIOR_DE = {
    "baseline": "baseline",
    "pos-correcao": "baseline",
    "conditional": "pos-correcao",
}
# Fase que não está no mapa compara contra a produção: é o que uma bateria de
# experimento quer medir — o efeito sobre o que roda hoje.
PADRAO_ANTERIOR = "pos-correcao"


def enxuga_execucao(e: dict) -> dict:
    """So o que a tela do ativo mostra — o bundle inteiro tem 1,6 MB."""
    o, av = e["operacao"], e["avaliacao"]
    consumo = o.get("consumo") or {}
    timeline = o.get("timeline") or []

    chamadas = [
        {
            "papel": t.get("papel"),
            "step": t.get("step"),
            "status": t.get("status_code"),
            "ok": t.get("ok"),
            "mode": t.get("mode"),
            "ms": t.get("latencia_ms"),
        }
        for t in timeline
        if t.get("tipo") == "chamada"
    ]

    return {
        "id": e["id"],
        "case_id": e["case_id"],
        "ticket": e["ticket_id"],
        "cenario": e["cenario"],
        "seed": e["seed"],
        "mensagem": o.get("mensagem"),
        "solicitante": o.get("solicitante"),
        "decisao": o.get("decisao"),
        "justificativa": o.get("justificativa"),
        "resposta": o.get("resposta_final"),
        "duracao_ms": o.get("duracao_ms"),
        "achados": [
            {"agent": a.get("agent"), "summary": a.get("summary")}
            for a in (o.get("achados") or [])
        ],
        "roteamento": [
            {"de": r.get("from"), "para": r.get("to"), "motivo": r.get("reason")}
            for r in (o.get("roteamento") or [])
        ],
        "consumo": {
            "llm_calls": consumo.get("llm_calls"),
            "tokens": consumo.get("total_tokens"),
            "por_papel": {
                k: v.get("total_tokens")
                for k, v in (consumo.get("by_agent") or {}).items()
            },
        },
        "chamadas": chamadas,
        "avaliacao": {
            "passou": av.get("passou"),
            "decision_match": av.get("decision_match"),
            "executou_sem_erro": av.get("executou_sem_erro"),
            "aceitas": av.get("decisoes_aceitas") or [],
            "gets_feitos": av.get("gets_feitos"),
            "gets_esperados": av.get("gets_esperados"),
            "faltantes": av.get("queries_faltantes") or [],
            "extras": av.get("queries_extras") or [],
            "repeticao": av.get("taxa_repeticao"),
            "erros_http": av.get("erros_http"),
            "chamadas_api": av.get("chamadas_api"),
        },
    }


def monta_fase(bundle: dict, ativos: dict, fase: str, fase_anterior: str) -> dict:
    """Indice de uma fase, com o custo comparado contra `fase_anterior`."""
    casos = {c["case_id"]: c for c in bundle["casos"]}

    por_ativo: dict[str, dict] = defaultdict(lambda: {"cenarios": {}})
    for e in bundle["execucoes"]:
        if e["fase"] != fase:
            continue
        aid = e["operacao"].get("asset_id")
        if not aid:
            continue
        # Chaveia por case_id, nao por cenario: CEN-07 tem dois casos (TKT-EXE-12 e
        # TKT-INV-09) e agrupar por cenario faria um sobrescrever o outro.
        alvo = por_ativo[aid]["cenarios"].setdefault(
            e["case_id"],
            {
                "cenario": e["cenario"],
                "case_id": e["case_id"],
                "ticket": e["ticket_id"],
                "questao": (casos.get(e["case_id"]) or {}).get("questao_raiz"),
                "aceitas": (casos.get(e["case_id"]) or {}).get("decisoes_aceitas") or [],
                "ambiguo": (casos.get(e["case_id"]) or {}).get("cenario_ambiguo"),
                "expected_path": (casos.get(e["case_id"]) or {}).get("expected_path") or [],
                "por_seed": {},
            },
        )
        alvo["por_seed"][e["seed"]] = enxuga_execucao(e)

    # Custo da mesma combinacao caso x seed na fase anterior. E o que permite mostrar,
    # no hover, quanto a correcao economizou naquela execucao especifica — a media
    # agregada esconde que o ganho nao foi uniforme.
    antes: dict[tuple[str, str], dict] = {}
    for e in bundle["execucoes"]:
        if e["fase"] != fase_anterior:
            continue
        consumo = e["operacao"].get("consumo") or {}
        antes[(e["case_id"], e["seed"])] = {
            "tokens": consumo.get("total_tokens"),
            "llm_calls": consumo.get("llm_calls"),
            "chamadas_api": e["avaliacao"].get("chamadas_api"),
            "decisao": e["operacao"].get("decisao"),
            "passou": e["avaliacao"].get("passou"),
            "decision_match": e["avaliacao"].get("decision_match"),
        }
    # Vereditos do comite. Hoje as 35 execucoes julgadas sao TODAS da fase baseline —
    # nenhuma da fase que a pagina exibe. Anexa-los assim mesmo, marcados com a fase de
    # origem, e mais honesto que omitir: a nota existe e vale para a versao anterior do
    # agente. A UI diz de qual fase ela veio.
    juizes_por_chave: dict[tuple[str, str], dict] = {}
    for e in bundle["execucoes"]:
        vereditos = e["avaliacao"].get("juizes")
        if not vereditos:
            continue
        juizes_por_chave[(e["case_id"], e["seed"])] = {
            "fase": e["fase"],
            "dimensoes": {
                dim: {"nota": v.get("score"), "porque": v.get("reasoning")}
                for dim, v in vereditos.items()
                if isinstance(v, dict)
            },
        }

    for reg in por_ativo.values():
        for caso in reg["cenarios"].values():
            for seed, ex in caso["por_seed"].items():
                ex["baseline"] = antes.get((caso["case_id"], seed))
                ex["juizes"] = juizes_por_chave.get((caso["case_id"], seed))

    ids_ativos = {a["id"] for a in ativos["ativos"]}
    cobertos = set(por_ativo) & ids_ativos

    agregados = bundle.get("agregados", {}).get(fase, {})
    meta = bundle.get("meta", {})

    return {
        "por_ativo": {k: v for k, v in por_ativo.items() if k in ids_ativos},
        "cobertura": {
            "ativos_com_cenario": len(cobertos),
            "ativos_total": len(ids_ativos),
            # Casos, nao cenarios: a bateria tem 17 casos sobre 16 cenarios.
            "casos": len({c for v in por_ativo.values() for c in v["cenarios"]}),
            "casos_total": len(casos),
        },
        "agregados": agregados,
        # A fase de comparacao, para a pagina mostrar o delta sem recalcular.
        "agregados_baseline": bundle.get("agregados", {}).get(fase_anterior, {}),
        "fase_anterior": fase_anterior,
        "juizes_meta": {
            "julgadas": meta.get("juizes_julgadas"),
            "elegiveis": meta.get("juizes_elegiveis"),
            "modelo": meta.get("juizes_modelo"),
            "comite": meta.get("comite"),
            "resumo": meta.get("juizes_resumo"),
        },
        "meta": {
            "gerado_em": meta.get("gerado_em"),
            "arquivos_varridos": meta.get("arquivos_varridos"),
            # Total do bundle (todas as fases) e o desta fase — o segundo é o que a
            # tela deve citar ao falar "N execuções medidas".
            "execucoes": meta.get("execucoes"),
            "execucoes_da_fase": (agregados or {}).get("execucoes"),
            "falhas_da_fase": (agregados or {}).get("falhas_execucao"),
            "fase": fase,
            "modelos": (meta.get("modelos_por_fase") or {}).get(fase, {}),
        },
    }


def main() -> None:
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    ativos = json.loads(ATIVOS.read_text(encoding="utf-8"))
    fases = [f for f in (bundle.get("meta", {}).get("fases") or []) ]

    # Um arquivo por fase, mais o `agente.json` da fase padrao. A pagina alterna
    # entre eles no clique, sem precisar de outro comando no terminal.
    indices = {}
    for fase in fases:
        anterior = ANTERIOR_DE.get(fase, PADRAO_ANTERIOR)
        if anterior not in fases:
            anterior = fases[0]
        indices[fase] = monta_fase(bundle, ativos, fase, anterior)
        destino = PAINEL / "dados" / f"agente-{fase}.json"
        destino.write_text(json.dumps(indices[fase], ensure_ascii=False), encoding="utf-8")
        cob = indices[fase]["cobertura"]
        print(f"  {fase:14} {cob['ativos_com_cenario']:2} ativos -> {destino.name}")

    padrao = FASE if FASE in indices else (fases[1] if len(fases) > 1 else fases[0])
    SAIDA.write_text(json.dumps(indices[padrao], ensure_ascii=False), encoding="utf-8")
    # A pagina precisa saber quais fases existem antes de carregar qualquer uma.
    (PAINEL / "dados" / "fases.json").write_text(
        json.dumps(
            {
                "fases": [
                    {
                        "nome": f,
                        "politica": ((bundle.get("meta", {}).get("modelos_por_fase") or {}).get(f) or {}).get("_evidence_policy"),
                        "execucoes": (bundle.get("agregados", {}).get(f) or {}).get("execucoes"),
                        "falhas": (bundle.get("agregados", {}).get(f) or {}).get("falhas_execucao"),
                        "arquivo": f"agente-{f}.json",
                    }
                    for f in fases
                ],
                "padrao": padrao,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"padrao: {padrao} -> {SAIDA.name}")


if __name__ == "__main__":
    main()
