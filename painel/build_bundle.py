"""Gera o bundle de dados do painel a partir dos traces e do CSV da bateria.

O painel é somente-leitura e não executa o agente: ele lê o que já foi gravado. Este
script é a fronteira entre os arquivos crus e a UI, e resolve o problema que impede a
leitura direta — **o trace não grava em que fase foi executado**.

## A junção que atribui a fase

Os arquivos de trace não têm campo `fase`, e 33 pares `(case_id, seed)` têm mais de um
arquivo (reexecuções durante o ajuste). Nem o nome da pasta nem o timestamp resolvem: as
pastas são nomes de experimento (`traces_fix_policy`, `traces_restantes`) e o corte por
horário erra em 21 casos.

O que resolve é juntar por `(case_id, seed, token_usage.total_tokens)` contra
`resultados_avaliacao.csv`: o total de tokens é uma assinatura da execução, e a junção é
1:1 para as 77 linhas do CSV. A garantia é empírica, não estrutural — duas execuções do
mesmo caso e seed poderiam empatar em tokens —, então o script **aborta** ao encontrar
ambiguidade em vez de escolher uma. Mascarar isso produziria um painel confiante e errado.

A correção de fundo é gravar `fase` no trace, no runner; enquanto isso não existe, esta
junção é a fonte da verdade e precisa falhar alto.

## Duas seções irmãs, não um objeto achatado

O bundle separa `operacao` de `avaliacao` por execução. A aba Operação nunca pode exibir
gabarito, decisão aceita ou status de aprovação — se exibisse, a separação agente/avaliação
que o projeto inteiro sustenta perderia sentido. Mantendo as seções irmãs, a regra vira
propriedade estrutural: `operacao` simplesmente não contém esses campos, e dá para
verificar isso lendo o bundle, do mesmo jeito que `evaluation/runner/golden.py` torna
verificável a regra equivalente no Python.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

REPO = Path(__file__).resolve().parent.parent
SAIDA = Path(__file__).resolve().parent / "dados" / "bundle.json"

# Os dois diretórios de trace. `agent/.run` não é sobra: as 3 execuções de baseline de
# case_tkt_exe_16 só existem lá, e varrer só a raiz as perderia em silêncio.
RAIZES_TRACE = [REPO / ".run", REPO / "agent" / ".run"]

CSV_EXECUCOES = REPO / ".run" / "resultados_avaliacao.csv"
CSV_RESUMO = REPO / ".run" / "resumo_por_cenario.csv"
CSV_LEGENDA = REPO / ".run" / "legenda_seeds_e_metricas.csv"
GABARITO = REPO / "eval" / "expected-paths.json"
# Notas do comitê, gravadas por painel/julgar.py. Opcional: sem elas o painel mostra o
# estado vazio, que é a leitura honesta enquanto a camada 2 não rodou.
JUIZES = Path(__file__).resolve().parent / "dados" / "juizes.json"

SEEDS = ("complete", "s2", "s3")
FASES = ("baseline", "pos-correcao")

# As três dimensões do comitê, iguais às de `evaluation/runner/judges.py`.
COMITE = [
    {"chave": "honestidade", "titulo": "Honestidade sob incerteza"},
    {"chave": "causa_raiz", "titulo": "Acurácia da causa-raiz"},
    {"chave": "justificativa", "titulo": "Qualidade da justificativa da decisão"},
]

# Colunas do CSV que são listas separadas por "|".
COLUNAS_LISTA = (
    "decisoes_aceitas",
    "queries_faltantes",
    "queries_extras",
    "acoes_exigidas",
    "acoes_executadas",
    "acoes_faltantes",
    "acoes_nao_previstas",
)
COLUNAS_BOOL = (
    "cenario_ambiguo",
    "decision_match",
    "passou",
    "executou_sem_erro",
)
COLUNAS_INT = (
    "gets_feitos",
    "gets_esperados",
    "tokens_input",
    "tokens_output",
    "tokens_total",
    "chamadas_api",
    "chamadas_repetidas",
    "erros_http",
    "justificativa_len",
)
COLUNAS_FLOAT = ("evidence_recall", "precisao_consultas", "taxa_repeticao")


class ErroDeDados(Exception):
    """Falha que invalida o bundle. Sempre aborta — nunca degrada em silêncio."""


# -- leitura ---------------------------------------------------------------


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    """Lê um CSV da bateria: BOM, `;` como separador."""
    if not caminho.exists():
        raise ErroDeDados(
            f"Arquivo não encontrado: {caminho}\n"
            "O painel lê a bateria já executada. Restaure `.run/` ou rode a avaliação."
        )
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def _converte(linha: dict[str, str]) -> dict[str, Any]:
    """Tipa uma linha do CSV. Campo vazio vira None, não 0 nem ''."""
    saida: dict[str, Any] = {}
    for chave, bruto in linha.items():
        if chave is None:
            continue
        valor = (bruto or "").strip()
        if chave in COLUNAS_LISTA:
            saida[chave] = [p for p in valor.split("|") if p]
        elif chave in COLUNAS_BOOL:
            saida[chave] = valor == "True"
        elif chave in COLUNAS_INT:
            saida[chave] = int(valor) if valor else None
        elif chave in COLUNAS_FLOAT:
            saida[chave] = float(valor) if valor else None
        else:
            saida[chave] = valor or None
    return saida


def carrega_traces() -> list[tuple[Path, dict[str, Any]]]:
    """Carrega todo trace dos dois diretórios `.run`."""
    achados: list[tuple[Path, dict[str, Any]]] = []
    for raiz in RAIZES_TRACE:
        if not raiz.exists():
            raise ErroDeDados(
                f"Diretório de traces não encontrado: {raiz}\n"
                "Os dois diretórios são obrigatórios: 3 execuções de baseline de "
                "case_tkt_exe_16 só existem em agent/.run/."
            )
        for arquivo in sorted(raiz.glob("traces_*/*.json")):
            achados.append((arquivo, json.loads(arquivo.read_text(encoding="utf-8"))))
    if not achados:
        raise ErroDeDados("Nenhum trace encontrado nos diretórios .run.")
    return achados


def parse_modelo(bruto: Any) -> dict[str, Any]:
    """Decodifica o campo `model`, que o trace grava como string JSON.

    Traces antigos gravavam uma string simples ("groq:openai/gpt-oss-120b"). O painel não
    lê essa pasta, mas o parse tolera o formato para não quebrar se alguém apontar para lá.
    """
    if isinstance(bruto, dict):
        return bruto
    if not isinstance(bruto, str) or not bruto.strip():
        return {}
    try:
        decodificado = json.loads(bruto)
        return decodificado if isinstance(decodificado, dict) else {"_bruto": bruto}
    except (json.JSONDecodeError, ValueError):
        return {"_bruto": bruto}


# -- junção ----------------------------------------------------------------


def junta_por_tokens(
    linhas: list[dict[str, Any]], traces: list[tuple[Path, dict[str, Any]]]
) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Casa cada linha do CSV com seu arquivo de trace e atribui a fase.

    A chave é `(case_id, seed, total_tokens)`. Aborta em ambiguidade ou ausência: uma
    fase errada contamina a comparação entre fases, que é justamente o que o painel
    existe para mostrar.
    """
    indice: dict[tuple[str, str, Any], list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    for caminho, trace in traces:
        tokens = (trace.get("token_usage") or {}).get("total_tokens")
        indice[(trace.get("case_id"), trace.get("seed"), tokens)].append((caminho, trace))

    # Execuções que quebraram por cota consomem 0 token, então várias tentativas do mesmo
    # caso ficam indistinguíveis pela assinatura de tokens. Nesse caso o desempate é o
    # trace mais recente: as tentativas posteriores existem para substituir as anteriores.
    for chave, candidatos in indice.items():
        if len(candidatos) > 1 and all(
            (t.get("token_usage") or {}).get("total_tokens") in (0, None) or t.get("error")
            for _, t in candidatos
        ):
            indice[chave] = [max(candidatos, key=lambda par: par[1].get("started_at", ""))]

    casados: dict[str, tuple[Path, dict[str, Any]]] = {}
    faltantes: list[str] = []
    ambiguos: list[str] = []

    for linha in linhas:
        chave = (linha["case_id"], linha["seed"], linha["tokens_total"])
        candidatos = indice.get(chave, [])
        rotulo = f"{linha['fase']}/{linha['case_id']}/{linha['seed']}"
        if len(candidatos) == 1:
            casados[id_execucao(linha)] = candidatos[0]
        elif not candidatos:
            faltantes.append(f"  {rotulo} (tokens={linha['tokens_total']})")
        else:
            arquivos = "\n      ".join(str(c.relative_to(REPO)) for c, _ in candidatos)
            ambiguos.append(f"  {rotulo} casa com {len(candidatos)} arquivos:\n      {arquivos}")

    if faltantes or ambiguos:
        partes = ["A junção CSV × trace não é 1:1 — o bundle não pode ser gerado."]
        if ambiguos:
            partes.append(
                "\nAMBÍGUAS (mesmo caso, seed e total de tokens em mais de um arquivo):\n"
                + "\n".join(ambiguos)
                + "\n  A junção por tokens deixou de distinguir estas execuções. A correção "
                "de fundo é gravar `fase` no trace, em agent/app/trace.py."
            )
        if faltantes:
            partes.append("\nSEM TRACE correspondente:\n" + "\n".join(faltantes))
        raise ErroDeDados("\n".join(partes))

    return casados


def id_execucao(linha: dict[str, Any]) -> str:
    return f"{linha['case_id']}__{linha['seed']}__{linha['fase']}"


# -- extração por execução -------------------------------------------------


def acha_resposta(trace: dict[str, Any], caminho: str) -> Any:
    """Primeira resposta bem-sucedida de uma rota. None quando não foi consultada."""
    for passo in trace.get("steps", []):
        if passo.get("path") == caminho and passo.get("ok") and passo.get("response"):
            return passo["response"]
    return None


def monta_timeline(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Intercala roteamento, chamadas e achados numa sequência cronológica.

    O trace guarda os três em arrays separados, cada um com seu próprio `at`. A timeline
    do painel precisa deles entrelaçados — a transição do Supervisor e as chamadas que
    ela provocou lado a lado. `offset_ms` é pré-calculado para a barra de latência ser
    aritmética na UI, não parsing de data.
    """
    inicio = parse_instante(trace.get("started_at"))
    eventos: list[dict[str, Any]] = []

    def offset(quando: str | None) -> int | None:
        instante = parse_instante(quando)
        if instante is None or inicio is None:
            return None
        return int((instante - inicio).total_seconds() * 1000)

    for rota in trace.get("routing", []):
        eventos.append(
            {
                "tipo": "roteamento",
                "at": rota.get("at"),
                "offset_ms": offset(rota.get("at")),
                "turno": rota.get("turn"),
                "de": rota.get("from"),
                "para": rota.get("to"),
                "motivo": rota.get("reason"),
            }
        )

    for indice, passo in enumerate(trace.get("steps", [])):
        eventos.append(
            {
                "tipo": "chamada",
                "at": passo.get("at"),
                "offset_ms": offset(passo.get("at")),
                "indice": indice,
                "papel": passo.get("agent"),
                "step": passo.get("step"),
                "metodo": passo.get("method"),
                "rota": passo.get("path"),
                "query": passo.get("query") or {},
                "status_code": passo.get("status_code"),
                "ok": passo.get("ok"),
                "mode": passo.get("mode"),
                "notes": passo.get("notes"),
                "erro": passo.get("error"),
                "latencia_ms": passo.get("latency_ms"),
                "body": passo.get("body"),
                "response": passo.get("response"),
                "do_cache": bool(passo.get("from_cache")),
            }
        )

    for achado in trace.get("findings", []):
        eventos.append(
            {
                "tipo": "achado",
                "at": achado.get("at"),
                "offset_ms": offset(achado.get("at")),
                "papel": achado.get("agent"),
                "resumo": achado.get("summary"),
            }
        )

    # Ordena por instante mantendo a ordem original no empate: vários passos podem
    # compartilhar o mesmo timestamp, e reordená-los inventaria uma sequência.
    eventos.sort(key=lambda e: (e.get("at") or "", 0))
    return eventos


def parse_instante(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def duracao_ms(trace: dict[str, Any]) -> int | None:
    inicio = parse_instante(trace.get("started_at"))
    fim = parse_instante(trace.get("finished_at"))
    if inicio is None or fim is None:
        return None
    return int((fim - inicio).total_seconds() * 1000)


def secao_operacao(trace: dict[str, Any]) -> dict[str, Any]:
    """O que o atendente veria. Nenhum campo de gabarito entra aqui (RN-01)."""
    return {
        "mensagem": trace.get("message"),
        "solicitante": acha_resposta(trace, "/users/me"),
        "ativo": acha_resposta(trace, f"/assets/{trace.get('asset_id')}"),
        "asset_id": trace.get("asset_id"),
        "user_id": trace.get("user_id"),
        "modelo": parse_modelo(trace.get("model")),
        "iniciado_em": trace.get("started_at"),
        "encerrado_em": trace.get("finished_at"),
        "duracao_ms": duracao_ms(trace),
        "decisao": trace.get("decision"),
        "justificativa": trace.get("justification"),
        "resposta_final": trace.get("final_answer"),
        "stop_reason": trace.get("stop_reason"),
        "erro": trace.get("error"),
        "consumo": trace.get("token_usage") or {},
        "roteamento": trace.get("routing", []),
        "achados": trace.get("findings", []),
        "timeline": monta_timeline(trace),
    }


def diff_trajetoria(esperado: list[dict[str, str]], feito: list[str]) -> list[dict[str, Any]]:
    """Diff entre trajetória do gabarito e a percorrida.

    Usa a mesma semântica de `evaluation/runner/deterministic.py`: comparação por
    conjunto (a ordem é livre por design) e igualdade exata de string de rota. As notas do
    gabarito acompanham cada passo esperado — explicam o que aquela consulta apuraria.
    """
    passos_esperados = [p["step"] for p in esperado]
    consultas_feitas = {s for s in feito if s.startswith("GET ")}
    conjunto_esperado = set(passos_esperados)

    linhas = [
        {
            "step": passo["step"],
            "nota": passo.get("note") or None,
            "situacao": "atendida" if passo["step"] in set(feito) else "faltante",
        }
        for passo in esperado
    ]
    linhas.extend(
        {"step": consulta, "nota": None, "situacao": "extra"}
        for consulta in sorted(consultas_feitas - conjunto_esperado)
    )
    return linhas


def secao_avaliacao(
    linha: dict[str, Any], trace: dict[str, Any], gabarito: dict[str, Any] | None
) -> dict[str, Any]:
    """Métricas e gabarito. Só a aba Avaliação lê esta seção."""
    esperado = (gabarito or {}).get("expected_path", [])
    return {
        "decisoes_aceitas": linha["decisoes_aceitas"],
        "cenario_ambiguo": linha["cenario_ambiguo"],
        "decision_match": linha["decision_match"],
        "passou": linha["passou"],
        "evidence_recall": linha["evidence_recall"],
        # Derivada por mim, não existe em deterministic.py — a UI rotula como tal (RN-06).
        "precisao_consultas": linha["precisao_consultas"],
        "precisao_consultas_derivada": True,
        "gets_feitos": linha["gets_feitos"],
        "gets_esperados": linha["gets_esperados"],
        "queries_faltantes": linha["queries_faltantes"],
        "queries_extras": linha["queries_extras"],
        "acoes_exigidas": linha["acoes_exigidas"],
        "acoes_executadas": linha["acoes_executadas"],
        "acoes_faltantes": linha["acoes_faltantes"],
        "acoes_nao_previstas": linha["acoes_nao_previstas"],
        "chamadas_api": linha["chamadas_api"],
        "chamadas_repetidas": linha["chamadas_repetidas"],
        "taxa_repeticao": linha["taxa_repeticao"],
        "erros_http": linha["erros_http"],
        "justificativa_len": linha["justificativa_len"],
        "executou_sem_erro": linha["executou_sem_erro"],
        "erro_execucao": linha["erro_execucao"],
        "questao_raiz": (gabarito or {}).get("root_question"),
        "modo_gabarito": (gabarito or {}).get("mode"),
        "expected_path": esperado,
        "path_taken": trace.get("path_taken", []),
        "diff_trajetoria": diff_trajetoria(esperado, trace.get("path_taken", [])),
    }


# -- agregados -------------------------------------------------------------


def taxa(valores: list[bool]) -> float | None:
    """Fração de verdadeiros. None (não 0) para conjunto vazio — como `report.py:141`."""
    return round(sum(valores) / len(valores), 3) if valores else None


def media(valores: list[float]) -> float | None:
    """Média. None (não 0) para conjunto vazio — como `report.py:145`."""
    limpos = [v for v in valores if v is not None]
    return round(mean(limpos), 3) if limpos else None


def agrega_fase(execucoes: list[dict[str, Any]]) -> dict[str, Any]:
    """Agregados de uma fase.

    As taxas cobrem apenas execuções que concluíram, como faz `report.py:29`: uma falha de
    execução (um 429 de cota) não é uma decisão errada, e misturá-las contamina a acurácia.
    """
    validas = [e for e in execucoes if e["avaliacao"]["executou_sem_erro"]]
    aval = [e["avaliacao"] for e in validas]

    return {
        "execucoes": len(execucoes),
        "falhas_execucao": len(execucoes) - len(validas),
        "acuracia_decisao": taxa([a["decision_match"] for a in aval]),
        "taxa_aprovacao": taxa([a["passou"] for a in aval]),
        "recall_medio": media([a["evidence_recall"] for a in aval]),
        "precisao_media": media([a["precisao_consultas"] for a in aval]),
        "chamadas_media": media([float(a["chamadas_api"] or 0) for a in aval]),
        "taxa_repeticao_media": media([a["taxa_repeticao"] for a in aval]),
        "tokens_medio": media([float(e["operacao"]["consumo"].get("total_tokens") or 0) for e in validas]),
        "com_acao_faltante": sum(1 for a in aval if a["acoes_faltantes"]),
        "com_acao_nao_prevista": sum(1 for a in aval if a["acoes_nao_previstas"]),
        "com_erro_http": sum(1 for a in aval if (a["erros_http"] or 0) > 0),
    }


def estabilidade(execucoes: list[dict[str, Any]]) -> dict[str, Any]:
    """Veredito de estabilidade de um caso, sobre as seeds de uma fase.

    Espelha `evaluation/runner/stability.py`. Dois pontos que a UI depende:
    instabilidade é divergência da DECISÃO FINAL e só dela — variação de trajetória é
    esperada e fica reportada sem penalizar; e sem nenhuma execução bem-sucedida o
    resultado é `None`, não `True`. Tratar "não concluiu nada" como estável reportaria
    100% de estabilidade num agente que só falhou.
    """
    decisoes = [e["operacao"]["decisao"] for e in execucoes]
    contagem = Counter(d for d in decisoes if d)
    concluidas = sum(contagem.values())

    trajetorias = {tuple(sorted(set(e["avaliacao"]["path_taken"]))) for e in execucoes}
    variacao = (len(trajetorias) - 1) / (len(execucoes) - 1) if len(execucoes) > 1 else 0.0

    aceitas = set()
    for execucao in execucoes:
        aceitas.update(execucao["avaliacao"]["decisoes_aceitas"])
    distintas = sorted(contagem)

    return {
        "execucoes": len(execucoes),
        "execucoes_validas": concluidas,
        "decisoes": decisoes,
        "decisoes_distintas": distintas,
        "decisoes_aceitas": sorted(aceitas),
        "medivel": concluidas > 0,
        "estavel": (len(contagem) <= 1) if concluidas else None,
        # Divergiu, mas todas as decisões estão no conjunto aceito: instabilidade benigna
        # (TKT-INV-10 varia entre orientar e escalar, ambos aceitos). Sinalizada em tom
        # diferente da que sai do conjunto, que é erro de verdade.
        "dentro_do_aceito": bool(distintas) and set(distintas).issubset(aceitas),
        "variacao_trajetoria": round(variacao, 3),
    }


def facetas(execucoes: list[dict[str, Any]]) -> dict[str, Any]:
    """Valores presentes nos dados, para os filtros da fila."""
    empresas: Counter = Counter()
    ativos: Counter = Counter()
    papeis: Counter = Counter()
    usuarios: dict[str, str] = {}

    for execucao in execucoes:
        solicitante = execucao["operacao"]["solicitante"] or {}
        if solicitante.get("company_id"):
            empresas[solicitante["company_id"]] += 1
        if solicitante.get("role"):
            papeis[solicitante["role"]] += 1
        if solicitante.get("id"):
            usuarios[solicitante["id"]] = solicitante.get("name") or solicitante["id"]
        if execucao["operacao"]["asset_id"]:
            ativos[execucao["operacao"]["asset_id"]] += 1

    return {
        "empresas": [{"id": k, "execucoes": v} for k, v in sorted(empresas.items())],
        "ativos": [{"id": k, "execucoes": v} for k, v in sorted(ativos.items())],
        "papeis": [{"id": k, "execucoes": v} for k, v in sorted(papeis.items())],
        "usuarios": [{"id": k, "nome": v} for k, v in sorted(usuarios.items())],
        "decisoes": ["orientar", "agir", "escalar"],
        "modos": ["complete", "partial", "inconclusive", "conflict", "unavailable"],
    }


def config_por_fase(execucoes: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    """Configuração de modelos por fase, e se ela diverge entre as fases.

    Comparar fases só é válido com a mesma configuração por papel: se o modelo do Decisor
    mudou junto com o prompt, o efeito medido não é o da correção. A UI avisa quando isso
    acontece — e o aviso precisa existir mesmo quando hoje não dispara.
    """
    por_fase: dict[str, Any] = {}
    for fase in FASES:
        configs = {
            json.dumps(e["operacao"]["modelo"], sort_keys=True, ensure_ascii=False)
            for e in execucoes
            if e["fase"] == fase
        }
        if len(configs) == 1:
            por_fase[fase] = json.loads(next(iter(configs)))
        elif configs:
            # Mais de uma configuração dentro da própria fase: também é divergência.
            por_fase[fase] = {"_divergente": [json.loads(c) for c in sorted(configs)]}
        else:
            por_fase[fase] = None

    presentes = [c for c in por_fase.values() if c]
    diverge = len(presentes) > 1 and any(c != presentes[0] for c in presentes[1:])
    return por_fase, diverge


# -- verificação -----------------------------------------------------------


def verifica(execucoes: list[dict[str, Any]], resumo: list[dict[str, str]]) -> list[str]:
    """Confere os agregados recalculados contra `resumo_por_cenario.csv`.

    Torna a fidelidade das métricas testável em vez de afirmada: divergência aqui indica
    junção errada ou porte de fórmula errado.
    """
    problemas: list[str] = []
    por_chave: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for execucao in execucoes:
        por_chave[(execucao["fase"], execucao["ticket_id"])].append(execucao)

    for linha in resumo:
        chave = (linha["fase"], linha["ticket"])
        nossas = por_chave.get(chave, [])
        esperadas = int(linha["execucoes"])
        if len(nossas) != esperadas:
            problemas.append(
                f"{chave[0]}/{chave[1]}: {len(nossas)} execuções no bundle, "
                f"{esperadas} no resumo"
            )
            continue

        aprovadas_csv = int(linha["passou"])
        aprovadas = sum(1 for e in nossas if e["avaliacao"]["passou"])
        if aprovadas != aprovadas_csv:
            problemas.append(
                f"{chave[0]}/{chave[1]}: {aprovadas} aprovações no bundle, "
                f"{aprovadas_csv} no resumo"
            )

        acertos_csv = int(linha["decision_match"])
        acertos = sum(1 for e in nossas if e["avaliacao"]["decision_match"])
        if acertos != acertos_csv:
            problemas.append(
                f"{chave[0]}/{chave[1]}: {acertos} decision_match no bundle, "
                f"{acertos_csv} no resumo"
            )
    return problemas


# -- montagem --------------------------------------------------------------


def carrega_juizes() -> dict[str, Any]:
    """Notas do comitê já gravadas. Vazio quando a camada 2 ainda não rodou."""
    if not JUIZES.exists():
        return {"modelo": None, "vereditos": {}}
    try:
        return json.loads(JUIZES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return {"modelo": None, "vereditos": {}}


def agrega_juizes(vereditos: dict[str, Any], comite: list[dict[str, str]]) -> dict[str, Any]:
    """Média e distribuição por dimensão, como em `evaluation/runner/report.py`.

    Nota ausente não entra na média — `None` para conjunto vazio, nunca 0.
    """
    resumo: dict[str, Any] = {}
    for dimensao in comite:
        chave = dimensao["chave"]
        notas = [
            v["dimensoes"][chave]["score"]
            for v in vereditos.values()
            if v.get("dimensoes", {}).get(chave, {}).get("score") is not None
        ]
        resumo[chave] = {
            "julgadas": len(notas),
            "media": round(mean(notas), 2) if notas else None,
            "distribuicao": {str(n): notas.count(n) for n in range(1, 6)},
        }
    return resumo


def monta_bundle() -> tuple[dict[str, Any], list[dict[str, str]]]:
    linhas = [_converte(l) for l in ler_csv(CSV_EXECUCOES)]
    resumo = ler_csv(CSV_RESUMO)
    legenda = ler_csv(CSV_LEGENDA)
    traces = carrega_traces()

    gabarito = {
        item["id"]: item for item in json.loads(GABARITO.read_text(encoding="utf-8"))
    }
    casados = junta_por_tokens(linhas, traces)

    juizes = carrega_juizes()

    execucoes: list[dict[str, Any]] = []
    for linha in linhas:
        chave = id_execucao(linha)
        caminho, trace = casados[chave]
        avaliacao = secao_avaliacao(linha, trace, gabarito.get(linha["case_id"]))
        veredito = juizes["vereditos"].get(chave)
        if veredito:
            # A nota é material de avaliação: fica na seção que a aba Operação não lê.
            avaliacao["juizes"] = veredito["dimensoes"]
            avaliacao["juizes_modelo"] = veredito.get("modelo")
        execucoes.append(
            {
                "id": chave,
                "case_id": linha["case_id"],
                "ticket_id": linha["ticket"],
                "cenario": linha["cenario"],
                "seed": linha["seed"],
                "fase": linha["fase"],
                "arquivo": str(caminho.relative_to(REPO)).replace("\\", "/"),
                "operacao": secao_operacao(trace),
                "avaliacao": avaliacao,
            }
        )

    # Execução quebrada não vai a julgamento: nota baixa ali seria lida como má decisão do
    # agente em vez de falha de execução (ADR 0005).
    elegiveis = sum(
        1 for e in execucoes if not e["operacao"]["erro"] and e["operacao"]["resposta_final"]
    )

    # Casos: identidade do cenário + veredito de estabilidade por fase.
    por_caso: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for execucao in execucoes:
        por_caso[execucao["case_id"]].append(execucao)

    casos = []
    for case_id, do_caso in sorted(por_caso.items()):
        primeiro = do_caso[0]
        gab = gabarito.get(case_id, {})
        por_fase: dict[str, Any] = {}
        for fase in FASES:
            da_fase = [e for e in do_caso if e["fase"] == fase]
            por_fase[fase] = (
                {
                    "execucoes": len(da_fase),
                    # Execuções que concluíram: é a base sobre a qual as taxas valem.
                    "validas": sum(1 for e in da_fase if e["avaliacao"]["executou_sem_erro"]),
                    "seeds": sorted(e["seed"] for e in da_fase),
                    "aprovadas": sum(1 for e in da_fase if e["avaliacao"]["passou"]),
                    "acertos_decisao": sum(1 for e in da_fase if e["avaliacao"]["decision_match"]),
                    "estabilidade": estabilidade(da_fase),
                }
                if da_fase
                else None
            )
        casos.append(
            {
                "case_id": case_id,
                "ticket_id": primeiro["ticket_id"],
                "cenario": primeiro["cenario"],
                "questao_raiz": gab.get("root_question"),
                "modo_gabarito": gab.get("mode"),
                "decisoes_aceitas": primeiro["avaliacao"]["decisoes_aceitas"],
                "cenario_ambiguo": primeiro["avaliacao"]["cenario_ambiguo"],
                "expected_path": gab.get("expected_path", []),
                "por_fase": por_fase,
            }
        )

    modelos, diverge = config_por_fase(execucoes)
    traces_usados = {e["arquivo"] for e in execucoes}

    bundle = {
        "meta": {
            "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
            "arquivos_varridos": len(traces),
            "execucoes": len(execucoes),
            "traces_sem_linha_no_csv": len(traces) - len(traces_usados),
            "chave_juncao": ["case_id", "seed", "token_usage.total_tokens"],
            "seeds": list(SEEDS),
            "fases": list(FASES),
            "modelos_por_fase": modelos,
            "config_diverge_entre_fases": diverge,
            # A camada 2 só tem nota do que `painel/julgar.py` já julgou. Sem isso, a tela
            # mostra estado vazio em vez de inventar número.
            "juizes_disponiveis": bool(juizes["vereditos"]),
            "juizes_modelo": juizes.get("modelo"),
            "juizes_julgadas": len(juizes["vereditos"]),
            "juizes_elegiveis": elegiveis,
            "juizes_motivo": (
                "Nenhuma execução julgada ainda. Rode `python painel/julgar.py` para "
                "julgar uma execução por vez com um modelo gratuito do OpenRouter."
            ),
            "comite": COMITE,
            "juizes_resumo": agrega_juizes(juizes["vereditos"], COMITE),
        },
        "execucoes": execucoes,
        "casos": casos,
        "agregados": {
            fase: agrega_fase([e for e in execucoes if e["fase"] == fase]) for fase in FASES
        },
        "facetas": facetas(execucoes),
        "glossario": [
            {
                "categoria": l["categoria"],
                "item": l["item"],
                "significado": l["significado"],
            }
            for l in legenda
        ],
    }
    return bundle, resumo


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Gera o bundle de dados do painel")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Confere os agregados recalculados contra resumo_por_cenario.csv",
    )
    args = parser.parse_args()

    try:
        bundle, resumo = monta_bundle()
    except ErroDeDados as erro:
        print(f"\nERRO: {erro}\n", file=sys.stderr)
        return 1

    meta = bundle["meta"]
    print(f"  arquivos de trace varridos: {meta['arquivos_varridos']}")
    print(f"  execuções com fase atribuída: {meta['execucoes']}")
    print(f"  traces sem linha no CSV: {meta['traces_sem_linha_no_csv']} (não entram no painel)")
    for fase in FASES:
        agregado = bundle["agregados"][fase]
        print(f"  {fase:14} {agregado['execucoes']:3} execuções, {agregado['falhas_execucao']} falhas")

    if meta["config_diverge_entre_fases"]:
        print("  AVISO: a configuração de modelos diverge entre as fases comparadas.")

    if args.verify:
        problemas = verifica(bundle["execucoes"], resumo)
        if problemas:
            print("\nVERIFICAÇÃO FALHOU — agregados divergem do resumo:", file=sys.stderr)
            for problema in problemas:
                print(f"  {problema}", file=sys.stderr)
            return 1
        print(f"  verificação: agregados batem com {CSV_RESUMO.name} ({len(resumo)} linhas)")

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  bundle: {SAIDA.relative_to(REPO)} ({SAIDA.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
