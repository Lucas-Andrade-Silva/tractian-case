"""Execução do holdout ao vivo, transmitida passo a passo (ADR 0006).

A bateria normal (`runner.cli --suite holdout`) roda tudo e grava o resultado; quem lê o
número depois precisa confiar em quem rodou. Aqui o objetivo é outro: **mostrar o agente
trabalhando**. Cada consulta à API industrial, cada troca de papel e cada achado viram um
evento assim que acontecem, e a página desenha o progresso em tempo real.

O comitê de juízes (camada 2) entra como etapa própria, DEPOIS do veredito
determinístico. São três chamadas a modelos do OpenRouter, e elas levam alguns segundos:
emiti-las junto atrasaria a comparação com o gabarito, que é instantânea. A página recebe
o `veredito` na hora e as notas quando chegarem.

A regra que estrutura o módulo: **o gabarito só aparece depois**. Durante a execução, o
que sai é o que o agente de fato fez — as mesmas informações que ele teve. O
`expected_path` e as `accepted_decisions` são emitidos num evento final `veredito`, junto
da comparação. Vazar o esperado antes transformaria a demonstração em teatro: quem assiste
leria a trajetória "certa" antes de o agente escolher a dele, e não haveria como
distinguir acerto de encenação.

O agente NÃO sabe que está no holdout. Recebe o caso pelo mesmo `run_case` da bateria, com
os mesmos prompts e as mesmas tools — o que ele vê é indistinguível de um caso do golden.

## Como o streaming funciona

`graph.invoke()` é bloqueante e não expõe callbacks por passo. Em vez de reescrever o
grafo para transmitir (o que mudaria o código medido, e a medida deixaria de valer), a
execução vai para uma thread e o `Trace` — que já acumula `steps`, `routing`, `findings` e
`llm_calls` em tempo real — é lido em intervalos curtos. O que apareceu desde a última
leitura vira evento. É polling sobre estrutura em memória, não sobre disco: o custo é
desprezível perto de uma chamada de LLM, e o agente roda exatamente como na bateria.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from app.config import Settings, load_settings
from app.runner import run_case
from app.trace import Trace

from .deterministic import evaluate_deterministic
from .holdout import load_holdout, load_holdout_cases
from .judges import COMMITTEE, run_committee
from .juiz_modelos import constroi_juizes

# Seed da demonstração. `complete` é o mesmo da auditoria do holdout: o cenário foi
# verificado contra a API real com ele, então a evidência que o agente encontra é a que
# sustenta a resolução esperada. Outra seed degradaria os dados e mediria robustez a
# envelope — que é o que a bateria de três seeds já faz, e não é o ponto aqui.
SEED_DEMO = "complete"

# Intervalo de leitura do trace. Curto o bastante para o passo aparecer como
# acontecendo, longo o bastante para não girar em falso: uma chamada de LLM leva
# segundos, e nada muda entre duas leituras de 150 ms na maior parte do tempo.
_INTERVALO_S = 0.15

# Destino dos traces desta aba, separado da bateria. Uma execução de demonstração no
# mesmo diretório da avaliação entraria nas médias do painel sem ter sido pedida.
DESTINO = Path(__file__).resolve().parent.parent / "results" / "traces" / "holdout-ao-vivo"


def cenarios_disponiveis() -> list[dict[str, Any]]:
    """Os 8 cenários, com o que pode ser mostrado ANTES de rodar.

    Só a mensagem do cliente e o ativo — o que o agente vê. `root_question`, `facet` e
    `expected_path` ficam de fora de propósito: são gabarito.
    """
    return [
        {
            "id": caso["id"],
            "ticket_id": caso.get("ticket_id", ""),
            "asset_id": caso.get("asset_id"),
            "user_id": caso.get("user_id"),
            "company_id": caso.get("company_id"),
            "message": caso.get("message", ""),
        }
        for caso in load_holdout_cases()
    ]


def _evento(tipo: str, **dados: Any) -> dict[str, Any]:
    return {"tipo": tipo, "em": time.time(), **dados}


def _passo_evento(passo: dict[str, Any]) -> dict[str, Any]:
    """Uma chamada à API industrial, como o observador precisa vê-la."""
    return _evento(
        "consulta",
        step=passo.get("step"),
        metodo=passo.get("method"),
        caminho=passo.get("path"),
        agente=passo.get("agent"),
        status=passo.get("status_code"),
        ok=passo.get("ok"),
        # `mode` é o envelope probabilístico da API: dizer que veio `partial` enquanto
        # acontece é metade da história que esta aba conta.
        mode=passo.get("mode"),
        notes=passo.get("notes"),
        do_cache=passo.get("from_cache", False),
    )


def _drena(trace: Trace, vistos: dict[str, int]) -> list[dict[str, Any]]:
    """Eventos novos desde a última leitura, na ordem em que aconteceram.

    `vistos` guarda quantos itens de cada lista já viraram evento. As listas do trace só
    crescem (nada é removido durante a execução), então o corte por índice é suficiente e
    não exige comparar conteúdo.
    """
    novos: list[dict[str, Any]] = []

    passos = trace.steps
    if len(passos) > vistos["steps"]:
        for passo in passos[vistos["steps"]:]:
            novos.append(_passo_evento(passo.to_dict()))
        vistos["steps"] = len(passos)

    rotas = trace.routing
    if len(rotas) > vistos["routing"]:
        for rota in rotas[vistos["routing"]:]:
            novos.append(
                _evento("papel", turno=rota.get("turn"), para=rota.get("to"), motivo=rota.get("reason"))
            )
        vistos["routing"] = len(rotas)

    achados = trace.findings
    if len(achados) > vistos["findings"]:
        for achado in achados[vistos["findings"]:]:
            novos.append(_evento("achado", agente=achado.get("agent"), resumo=achado.get("summary")))
        vistos["findings"] = len(achados)

    chamadas = trace.llm_calls
    if len(chamadas) > vistos["llm"]:
        for chamada in chamadas[vistos["llm"]:]:
            novos.append(
                _evento(
                    "llm",
                    agente=chamada.agent,
                    entrada=chamada.input_tokens,
                    saida=chamada.output_tokens,
                    total=chamada.total_tokens,
                )
            )
        vistos["llm"] = len(chamadas)

    return novos


def _compara_com_gabarito(trace: Trace, case_id: str) -> dict[str, Any]:
    """A comparação com o holdout, montada só depois que o agente terminou."""
    gabarito = load_holdout().get(case_id)
    if gabarito is None:
        return {"erro": f"cenário {case_id} não está no gabarito do holdout"}

    resultado = evaluate_deterministic(trace.to_dict(), gabarito)
    consultas_feitas = {p for p in trace.path_taken if p.startswith("GET ")}

    return {
        "case_id": case_id,
        "ticket_id": gabarito.ticket_id,
        # O que o cenário cobra, revelado agora — nunca antes.
        "pergunta_raiz": gabarito.root_question,
        "faceta": gabarito.facet,
        "decisoes_aceitas": sorted(gabarito.accepted_decisions),
        "cenario_ambiguo": gabarito.is_ambiguous,
        "decisao": resultado.decision,
        "decisao_correta": resultado.decision_match,
        "passou": resultado.passed,
        "recall_evidencia": resultado.evidence_recall,
        "consultas_esperadas": [
            {
                "step": esperado,
                "nota": gabarito.expected_notes.get(esperado, ""),
                "feita": esperado in consultas_feitas,
            }
            for esperado in gabarito.expected_queries
        ],
        "consultas_faltantes": resultado.missing_queries,
        "consultas_extras": resultado.extra_queries,
        "acoes_exigidas": resultado.required_actions,
        "acoes_executadas": resultado.executed_actions,
        "acoes_faltantes": resultado.missing_actions,
        "acoes_nao_previstas": resultado.unexpected_actions,
        "chamadas": resultado.num_calls,
        "repeticoes": resultado.repeated_calls,
        "erros_http": resultado.http_errors,
        "justificativa_len": resultado.justification_length,
    }


def executa_ao_vivo(
    case_id: str,
    *,
    seed: str | None = None,
    settings: Settings | None = None,
    julgar: bool = False,
    modelos_juizes: dict[str, str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Roda um cenário do holdout, gerando eventos conforme o agente trabalha.

    `julgar=True` acrescenta a camada 2 (comitê de juízes) depois do veredito
    determinístico. Fica desligado por padrão: são três chamadas a um provedor externo
    por execução, e quem só quer ver o agente trabalhar não deveria pagar por elas.

    O último evento é `veredito` (sem juízes), `juizes` (com), ou `erro` — a página usa
    isso para saber que pode parar de escutar.
    """
    settings = settings or load_settings()
    casos = {c["id"]: c for c in load_holdout_cases()}
    caso = casos.get(case_id)
    if caso is None:
        yield _evento("erro", mensagem=f"cenário '{case_id}' não existe no holdout")
        return

    seed = seed or SEED_DEMO

    yield _evento(
        "inicio",
        case_id=case_id,
        ticket_id=caso.get("ticket_id", ""),
        asset_id=caso.get("asset_id"),
        user_id=caso.get("user_id"),
        mensagem=caso.get("message", ""),
        seed=seed,
        modelos=_modelos_por_papel(settings),
    )

    resultado: queue.Queue = queue.Queue(maxsize=1)
    # O trace é criado pelo `run_case`, então não dá para lê-lo antes de a thread
    # começar. Esta caixa recebe a referência assim que ela existe.
    caixa: dict[str, Trace] = {}

    def trabalha() -> None:
        try:
            trace = run_case(
                caso,
                seed=seed,
                settings=settings,
                save_to=DESTINO,
                trace_hook=caixa.__setitem__,
            )
            resultado.put(("ok", trace))
        except Exception as exc:  # noqa: BLE001 - a falha vira evento, não derruba a aba
            resultado.put(("erro", exc))

    thread = threading.Thread(target=trabalha, daemon=True, name=f"holdout-{case_id}")
    thread.start()

    vistos = {"steps": 0, "routing": 0, "findings": 0, "llm": 0}
    while True:
        trace = caixa.get("trace")
        if trace is not None:
            for evento in _drena(trace, vistos):
                yield evento

        try:
            estado, carga = resultado.get(timeout=_INTERVALO_S)
        except queue.Empty:
            continue
        break

    # A thread terminou: drena o que entrou entre a última leitura e o fim.
    trace = caixa.get("trace")
    if trace is not None:
        for evento in _drena(trace, vistos):
            yield evento

    if estado == "erro":
        yield _evento("erro", mensagem=f"{type(carga).__name__}: {carga}")
        return

    trace = carga
    if trace.error:
        yield _evento("erro", mensagem=trace.error, parada=trace.stop_reason)
        return

    yield _evento(
        "resposta",
        decisao=trace.decision,
        justificativa=trace.justification,
        resposta=trace.final_answer,
        parada=trace.stop_reason,
        tokens=trace.token_usage,
    )
    yield _evento("veredito", **_compara_com_gabarito(trace, case_id))

    if not julgar:
        return

    # A camada 2 avalia o que a camada 1 não alcança: se a resposta é honesta sobre o que
    # não pôde ser determinado, se a causa raiz está tecnicamente certa, e se a
    # justificativa sustenta a decisão. Nada disso sai de comparar trajetórias.
    yield _evento("juizes_iniciou", dimensoes=[j.key for j in COMMITTEE])
    try:
        llms, modelos = constroi_juizes(modelos_juizes)
        vereditos = run_committee(
            trace.to_dict(), load_holdout()[case_id], llm_por_dimensao=llms
        )
        yield _evento("juizes", vereditos=vereditos, modelos=modelos)
    except Exception as exc:  # noqa: BLE001 - o comitê é opcional; falhar nele não anula
        # a execução do agente, que já foi medida pela camada 1 e continua válida.
        yield _evento("juizes_erro", mensagem=f"{type(exc).__name__}: {exc}")


def _modelos_por_papel(settings: Settings) -> dict[str, str]:
    """Configuração efetiva, para a página dizer com que modelos rodou."""
    from app.config import ROLES  # noqa: PLC0415 - evita ciclo na carga do módulo

    return {papel: settings.model_for(papel) for papel in ROLES}
