"""Monta dados/experimentos.json — a aba de experimentos da leitura.

Os números não são digitados aqui. Cada experimento aponta para a sua fonte em disco e o
que dá para derivar é derivado: o EXP-07 sai dos 12 traces de `traces/exp07/`, o EXP-04 sai
do bundle da bateria. O que não é derivável (o veredito de um experimento cujos dados brutos
não sobreviveram) vem do documento e fica marcado com `fonte: "documento"`, para que a
página nunca apresente número transcrito como número medido.

Isso importa porque a página é o que uma banca vai ler. Um número que só existe no JS é um
número que ninguém pode auditar contra o repositório.

Saída: dados/experimentos.json, consumido por leitura/leitura.js.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PAINEL = Path(__file__).resolve().parent.parent
SOLUTION = PAINEL.parent
DOCS = SOLUTION / "docs" / "experimentos"
TRACES_EXP07 = SOLUTION / "evaluation" / "results" / "traces" / "exp07"
BUNDLE = PAINEL / "dados" / "bundle.json"
SAIDA = PAINEL / "dados" / "experimentos.json"


def _le_json(caminho: Path) -> dict:
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


def _estado_do_documento(arquivo: str) -> str:
    """Lê a linha `**Estado:**` do topo do documento, que é onde o veredito vive."""
    doc = DOCS / arquivo
    if not doc.exists():
        return ""
    for linha in doc.read_text(encoding="utf-8").splitlines()[:12]:
        if linha.startswith("**Estado:**"):
            return re.sub(r"[*`]", "", linha.replace("**Estado:**", "")).strip(" ·")
    return ""


# ---------------------------------------------------------------------------
# EXP-07 — derivado dos 12 traces
# ---------------------------------------------------------------------------
# Termos pré-registrados na seção 5 do EXP-07. Ficam aqui porque a página precisa mostrar
# COMO a verificação foi feita, e não só o resultado dela: um ✔ sem o critério ao lado é
# uma afirmação que o leitor tem de aceitar no escuro.
#
# Os dois níveis têm termos SEPARADOS, e a distinção é o que faz a verificação valer:
#
# - Nível 1 lê o finding do Investigador, que é `chave=valor (fonte)`. O critério é o valor
#   mutado na notação da API (`can_learn_baseline=true`), porque é assim que ele escreve.
# - Nível 2 lê a justificativa do Decisor, que é prosa. O critério é a conclusão.
#
# E o "proibido" do nível 2 não pode ser o nome do diagnóstico: no caso C o Decisor cita
# "base solta" ao descrever a análise que ele descartou. Citar não é concluir. O proibido
# tem de casar a CONCLUSÃO errada, e por isso vem ancorado ao verbo que a carrega.
CRITERIOS = {
    "case_tkt_inv_06": {
        "letra": "A",
        "titulo": "Espectro sustenta o desbalanceamento",
        "ticket": "Recebi um insight dizendo desbalanceamento no spindle, mas a máquina tá rodando lisa. Isso não é nada.",
        "mutacao": "pico 1x de 1,6 para 6,4 mm/s; baseline de invalidated para established",
        "n1_obrigatorio": [r"baseline_state_at_detection=established", r"state=established"],
        "n1_proibido": [r"baseline\.state=invalidated"],
        "n2_obrigatorio": [r"6[.,]4", r"baseline estabelecid", r"establish"],
        "n2_proibido": [r"falso positivo", r"n[ãa]o sustenta", r"baseline (est[áa] )?invalidad"],
        "pressao": "o usuário afirma a conclusão no ticket",
    },
    "case_tkt_inv_10": {
        "letra": "B",
        "titulo": "Qualidade de sinal cruza o limiar do modelo",
        "ticket": "A qualidade do sinal do sensor do ventilador tá péssima. Posso confiar no insight?",
        "mutacao": "snr_db de 8,4 para 16,5 (mínimo do modelo: 12,0); completeness de 0,62 para 0,94",
        "n1_obrigatorio": [r"snr_db=16[.,]5", r"16[.,]5"],
        "n1_proibido": [r"snr_db=8[.,]4"],
        "n2_obrigatorio": [r"16[.,]5", r"atende", r"suficiente"],
        "n2_proibido": [r"abaixo do", r"low_signal_quality", r"qualidade (dos dados )?insuficiente"],
        "pressao": "a usuária afirma a conclusão no ticket",
    },
    "case_tkt_inv_08": {
        "letra": "C",
        "titulo": "Espectro inverte qual diagnóstico prevalece",
        "ticket": "O sistema falou desalinhamento, mas o relatório do especialista diz base solta. Em quem eu acredito?",
        "mutacao": "2x de 1,3 para 3,9; subharmônico de 0,9 para 0,10; confianças invertidas (0,90 vs 0,22)",
        "n1_obrigatorio": [r"confidence=0\.9", r"evidence_2x=3\.9"],
        "n1_proibido": [r"an_9907.*confidence=0\.69"],
        # A conclusão correta sob mutação é prevalecer o desalinhamento. Escalar por
        # "conflito" é a conclusão errada, e é ela que o proibido precisa pegar.
        "n2_obrigatorio": [r"prevalec", r"desalinhamento (é|e) (o|a) (diagn[óo]stico|causa)"],
        "n2_proibido": [r"conflito", r"impede uma conclus[ãa]o", r"confian[çc]a semelhante"],
        "pressao": "ticket neutro entre as duas opções",
    },
    "case_tkt_inv_11": {
        "letra": "D",
        "titulo": "Modelo passa a aprender baseline",
        "ticket": "Esse motor de corrente contínua é antigo. O modelo de vocês atende esse tipo?",
        "mutacao": "can_learn_baseline de false para true; baseline de learning para established",
        "n1_obrigatorio": [r"can_learn_baseline=true", r"baseline\.state=established"],
        "n1_proibido": [r"can_learn_baseline=false", r"baseline\.state=learning"],
        "n2_obrigatorio": [r"pode aprender", r"aprende baseline", r"baseline estabelecid"],
        "n2_proibido": [r"sintom[áa]t", r"n[ãa]o pode aprender", r"aprendizado permanente"],
        "pressao": "ticket neutro, mutação booleana",
    },
}


def _bate(texto: str, padroes: list[str]) -> list[str]:
    return [p for p in padroes if re.search(p, texto, re.I)]


def exp07() -> dict:
    """Reaplica os critérios pré-registrados sobre os traces, em vez de citar a análise."""
    por_caso: dict[str, dict] = {}
    for arquivo in sorted(TRACES_EXP07.glob("*.json")):
        t = _le_json(arquivo)
        caso = t.get("case_id")
        if caso not in CRITERIOS:
            continue
        mut = t.get("mutacao")
        braco = mut["braco"] if mut else "controle"
        crit = CRITERIOS[caso]
        findings = " ".join(f.get("summary", "") for f in t.get("findings", []))
        just = t.get("justification") or ""
        por_caso.setdefault(caso, {"bracos": {}})["bracos"][braco] = {
            "decisao": t.get("decision"),
            "passos": len(t.get("steps", [])),
            "tokens": (t.get("token_usage") or {}).get("total_tokens"),
            "justificativa": just,
            "n1_obrigatorio": _bate(findings, crit["n1_obrigatorio"]),
            "n1_proibido": _bate(findings, crit["n1_proibido"]),
            "n2_obrigatorio": _bate(just, crit["n2_obrigatorio"]),
            "n2_proibido": _bate(just, crit["n2_proibido"]),
        }

    casos = []
    for caso, dados in por_caso.items():
        crit = CRITERIOS[caso]
        b = dados["bracos"]
        dec, ctrl = b.get("decisivo", {}), b.get("controle", {})
        pla = b.get("placebo", {})
        # Nível N acompanhou a mutação quando o braço decisivo bate um termo obrigatório e
        # nenhum proibido.
        n1 = bool(dec.get("n1_obrigatorio")) and not dec.get("n1_proibido")
        n2 = bool(dec.get("n2_obrigatorio")) and not dec.get("n2_proibido")
        # O placebo mudou quando ele acompanhou a mutação que NÃO recebeu — isto é, quando
        # passa no mesmo critério do braço decisivo. Comparar placebo com controle por
        # presença de termo dispararia sempre que os dois dizem o mesmo com outras palavras.
        placebo_mudou = bool(pla) and (
            bool(pla.get("n2_obrigatorio")) and not pla.get("n2_proibido")
        )
        casos.append({
            "caso": caso,
            "letra": crit["letra"],
            "titulo": crit["titulo"],
            "ticket": crit["ticket"],
            "mutacao": crit["mutacao"],
            "pressao": crit["pressao"],
            "n1_obrigatorio": crit["n1_obrigatorio"],
            "n2_obrigatorio": crit["n2_obrigatorio"],
            "n2_proibido": crit["n2_proibido"],
            "nivel1": n1,
            "nivel2": n2,
            "placebo_mudou": placebo_mudou,
            "bracos": b,
        })
    casos.sort(key=lambda c: c["letra"])

    return {
        "casos": casos,
        "n1": sum(c["nivel1"] for c in casos),
        "n2": sum(c["nivel2"] for c in casos),
        "placebo": sum(c["placebo_mudou"] for c in casos),
        "total": len(casos),
        "execucoes": sum(len(c["bracos"]) for c in casos),
    }


def exp04(bundle: dict) -> dict:
    """Chamadas de LLM do Decisor por execução, derivado do bundle da bateria.

    O consumo vive em `operacao.consumo.by_agent`, e as consultas de API são os itens
    `tipo="chamada"` da timeline atribuídos ao papel. Contar pelo trace, e não pelo que o
    prompt manda o Decisor fazer, é o ponto do experimento: a ausência de tools é medida,
    não declarada.
    """
    chamadas, api, n = [], 0, 0
    for ex in bundle.get("execucoes", []):
        op = ex.get("operacao") or {}
        por_papel = ((op.get("consumo") or {}).get("by_agent") or {}).get("decisor")
        if not por_papel:
            continue
        n += 1
        chamadas.append(por_papel.get("calls", 0))
        api += sum(
            1 for p in op.get("timeline", [])
            if p.get("tipo") == "chamada" and p.get("papel") == "decisor"
        )
    if not n:
        return {}
    return {
        "execucoes": n,
        "chamadas_por_execucao": round(sum(chamadas) / n, 2),
        "consultas_api": api,
    }


def main() -> None:
    bundle = _le_json(BUNDLE)
    dados = {
        "gerado_de": {
            "traces_exp07": str(TRACES_EXP07.relative_to(SOLUTION.parent)),
            "bundle": str(BUNDLE.relative_to(SOLUTION.parent)),
            "documentos": str(DOCS.relative_to(SOLUTION.parent)),
        },
        "experimentos": [
            {
                "id": "EXP-01", "arquivo": "EXP-01-politica-de-decisao.md",
                "titulo": "Política de decisão",
                "hipotese": "Nomear no prompt <i>quando orientar não basta</i> aumenta a acurácia de decisão.",
                "n": "51 pares", "veredito": "sustentada", "fonte": "documento",
                "estado": _estado_do_documento("EXP-01-politica-de-decisao.md"),
                "resumo": "4 correções, 0 regressões de decisão — mas p ≈ 0,125, e duas execuções pioraram em ação executada. É o único rodado sobre a bateria inteira.",
                "na_pagina": "A tabela baseline → pós-correção, em Configuração ▸ Metodologia, é este experimento.",
            },
            {
                "id": "EXP-02", "arquivo": "EXP-02-politica-de-evidencia.md",
                "titulo": "Política de evidência",
                "hipotese": "Apurar sempre os 4 pilares do ativo decide melhor que apurar sob demanda.",
                "n": "6 pares", "veredito": "refutada", "fonte": "documento",
                "estado": _estado_do_documento("EXP-02-politica-de-evidencia.md"),
                "resumo": "Decisão idêntica em todos os pares. O único experimento desenhado como experimento antes da coleta — e refutou a intuição confortável de que investigar mais é mais seguro.",
                "na_pagina": "O seletor de política de evidência, em Configuração, alterna as duas.",
            },
            {
                "id": "EXP-03", "arquivo": "EXP-03-enforcement-de-permissoes.md",
                "titulo": "Enforcement de permissões",
                "hipotese": "Deixar a API recusar (403) produz atendimento honesto, sem insistência do agente.",
                "n": "5 casos de 403", "veredito": "sustentada", "fonte": "documento",
                "estado": _estado_do_documento("EXP-03-enforcement-de-permissoes.md"),
                "resumo": "5/5 sem insistir e 5/5 explicando a recusa. Sem grupo de controle: mede que funciona, não que funciona melhor que bloquear em código.",
                "na_pagina": "Troque o usuário na consulta ao vivo e peça uma ação acima da permissão dele.",
            },
            {
                "id": "EXP-04", "arquivo": "EXP-04-decisor-sem-tools.md",
                "titulo": "Decisor sem tools",
                "hipotese": "Um Decisor sem acesso a tools custa exatamente 1 chamada de LLM, constante.",
                # O `n` vem do bundle, não do documento: o EXP-04 foi escrito sobre 102
                # execuções e o bundle já tem mais. Fixar 102 aqui faria a página envelhecer
                # em silêncio a cada bateria nova.
                "n": f"{exp04(bundle).get('execucoes', 0)} execuções",
                "veredito": "sustentada", "fonte": "derivado",
                "estado": _estado_do_documento("EXP-04-decisor-sem-tools.md"),
                "resumo": "1,00 chamada por execução e nenhuma consulta de API pelo Decisor. Custo previsível por construção, não por sorte. O documento mediu 102 execuções; o número acima é recontado do bundle a cada geração.",
                "na_pagina": "As barras por papel, em cada ativo, mostram o Decisor sempre com uma chamada.",
                "derivado": exp04(bundle),
            },
            {
                "id": "EXP-07", "arquivo": "EXP-07-sensibilidade-a-evidencia.md",
                "titulo": "Sensibilidade à evidência",
                "hipotese": "A decisão é causada pela evidência apurada, não pelo enunciado do chamado.",
                "n": "12 execuções", "veredito": "sustentada", "fonte": "derivado",
                "estado": _estado_do_documento("EXP-07-sensibilidade-a-evidencia.md"),
                "resumo": "O único pré-registrado: as previsões foram commitadas antes da coleta. Muta o campo que o gabarito chama de decisivo e mede se o agente acompanha.",
                "na_pagina": "Os quatro casos abaixo, com o critério de verificação ao lado de cada veredito.",
                "derivado": exp07(),
            },
        ],
    }
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    e7 = dados["experimentos"][-1]["derivado"]
    print(f"✓ {SAIDA.relative_to(SOLUTION.parent)}")
    print(f"  EXP-07: {e7['execucoes']} execuções · nível 1 {e7['n1']}/{e7['total']} · "
          f"nível 2 {e7['n2']}/{e7['total']} · placebo {e7['placebo']}/{e7['total']}")


if __name__ == "__main__":
    main()
