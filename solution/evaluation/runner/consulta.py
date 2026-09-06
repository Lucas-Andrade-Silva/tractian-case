"""Consulta de texto livre: da mensagem do usuário até a avaliação sintética.

Orquestra o ciclo que o painel expõe na aba Consulta. A ordem dos passos não é
arbitrária:

    1. gabarito sintético  (modelo GERADOR)
    2. execução do agente  (modelos do agente)
    3. comitê de juízes    (modelo JUDGE)

O gabarito é gerado ANTES da execução e a partir apenas da mensagem — nunca do trace.
Se fosse gerado depois, o gerador veria a resposta do agente e tenderia a descrever como
"esperado" exatamente aquilo que o agente fez, transformando o julgamento em tautologia.
Essa ordem é a única salvaguarda contra isso, já que gerador e agente são LLMs.

A camada 1 (determinística) é deliberadamente pulada: sem `expected_path` real ela
calcularia recall sobre conjunto vazio (= 1.0) e derivaria "orientar" como resolução
esperada. Ver `sintetico.py`. O que sobra dela e continua válido — se a execução
concluiu, se houve repetição de chamada, se o agente insistiu após um 403 — é apurado
aqui direto do trace, sem gabarito nenhum.

## Isolamento das métricas

Consultas livres gravam em `evaluation/results/consultas/`, nunca em
`evaluation/results/traces/`. `cli.py` lê apenas o segundo diretório, então uma consulta
nunca entra num relatório dos 17 cenários com gabarito real, mesmo por engano.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, load_settings
from app.runner import run_case

from .judges import run_committee
from .juiz_modelos import DIMENSOES, constroi_juizes, modelo_padrao, settings_juiz
from .sintetico import GabaritoSintetico, assert_modelos_distintos, gera_gabarito

# `data/` é material da Tractian, em `tractian/`; `evaluation/` é meu, em `solution/`.
SOLUTION_DIR = Path(__file__).resolve().parent.parent.parent
TRACTIAN_DIR = SOLUTION_DIR.parent / "tractian"
CONSULTAS_DIR = SOLUTION_DIR / "evaluation" / "results" / "consultas"

# Sinaliza um 403 da API no passo, sem depender da mensagem exata em português.
_STATUS_NEGADO = 403

# O id de consulta vira nome de arquivo, e chega pela URL (`POST /consultas/{id}/...`).
# Sem esta trava, `..%2F..%2Fetc` escreveria fora de CONSULTAS_DIR. O formato é o que
# `_novo_id` produz, e nada além disso é aceito.
_ID_VALIDO = re.compile(r"^consulta_\d{8}T\d{6}$")

# Um cenário registrado é uma consulta que alguém achou que valia a pena guardar para
# os outros verem. Continua sendo métrica sintética (ADR 0007): o que muda é a
# visibilidade, não a classe de evidência. Só um humano escrevendo `expected_path` à
# mão promoveria isto a caso de referência, e isso não acontece aqui.
_NOME_MAX = 80


def executa_consulta(
    *,
    user_id: str,
    company_id: str,
    asset_id: str | None,
    mensagem: str,
    contexto_ativo: dict[str, Any] | None = None,
    seed: str | None = None,
    settings: Settings | None = None,
    julgar: bool = True,
    modelos_juizes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Roda uma consulta livre de ponta a ponta e devolve o registro completo.

    `julgar=False` executa o agente e pula o comitê — útil para ver a resposta sem
    gastar chamadas de LLM adicionais quando a cota está apertada.

    `modelos_juizes` escolhe o modelo OpenRouter de cada dimensão
    (`{"causa_raiz": "z-ai/glm-5.2:free"}`); dimensão ausente usa o padrão do `.env`.
    """
    settings = settings or load_settings()
    mensagem = (mensagem or "").strip()
    if not mensagem:
        raise ValueError("A mensagem da consulta está vazia.")

    caso = monta_caso(
        user_id=user_id,
        company_id=company_id,
        asset_id=asset_id,
        mensagem=mensagem,
    )

    # Gerador e juiz precisam ser modelos distintos, e a verificação vem antes de
    # qualquer chamada: descobrir isso depois de rodar o agente desperdiçaria a execução.
    # Verifica cada dimensão contra o gerador, porque o modelo é escolhido por dimensão —
    # checar só um deixaria passar o caso em que apenas uma delas colide.
    gabarito: GabaritoSintetico | None = None
    erro_gabarito: str | None = None
    if julgar:
        gerador = _gerador_settings()
        for dimensao in DIMENSOES:
            escolhido = (modelos_juizes or {}).get(dimensao) or modelo_padrao(dimensao)
            assert_modelos_distintos(gerador, settings_juiz(escolhido))
        try:
            gabarito = gera_gabarito(caso, contexto_ativo=contexto_ativo)
        except Exception as exc:  # noqa: BLE001 - vira dado do registro, não interrompe
            erro_gabarito = f"{type(exc).__name__}: {exc}"

    trace = run_case(caso, seed=seed, settings=settings, save_to=CONSULTAS_DIR)
    dados_trace = trace.to_dict()

    vereditos: dict[str, Any] | None = None
    erro_juiz: str | None = None
    modelos_juiz: dict[str, str] | None = None
    if gabarito is not None:
        try:
            # Um LLM por dimensão, todos no OpenRouter. `constroi_juizes` já aplica a
            # sonda de saída estruturada: sem ela, um modelo que devolve a nota em
            # Markdown ("**Nota: 5**") derruba o comitê depois de já ter raciocinado.
            llms, modelos_juiz = constroi_juizes(modelos_juizes)
            vereditos = run_committee(
                dados_trace, gabarito.golden, llm_por_dimensao=llms
            )
        except Exception as exc:  # noqa: BLE001 - idem
            erro_juiz = f"{type(exc).__name__}: {exc}"

    registro = {
        "id": caso["id"],
        "criado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origem": "consulta_livre",
        "entrada": {
            "user_id": user_id,
            "company_id": company_id,
            "asset_id": asset_id,
            "mensagem": mensagem,
            "seed": seed,
        },
        "gabarito_sintetico": gabarito.to_dict() if gabarito else None,
        "erro_gabarito": erro_gabarito,
        # Preenchidos depois, por quem registra o cenário e por quem dá o veredito.
        # Nascem explícitos para que a ausência seja `None`, e não chave faltando.
        "cenario": None,
        "veredito_humano": None,
        "trace": dados_trace,
        "avaliacao": {
            # Camada 1 NÃO se aplica: sem trajetória de referência não há o que comparar.
            "camada1": None,
            "camada1_motivo": (
                "Não aplicável a consulta livre: não existe trajetória de referência. "
                "Comparar contra um expected_path vazio produziria recall=1.0 sem "
                "significado."
            ),
            "execucao": metricas_execucao(dados_trace),
            "juizes": vereditos,
            "modelos_juiz": modelos_juiz,
            "erro_juiz": erro_juiz,
            "comparavel_com_cenarios": False,
        },
    }

    salva_consulta(registro)
    return registro


def monta_caso(
    *,
    user_id: str,
    company_id: str,
    asset_id: str | None,
    mensagem: str,
) -> dict[str, Any]:
    """Constrói o dict de caso no schema que `run_case` já aceita.

    `run_case` nunca lê `tractian/agent-input/cases.json` — recebe o dict pronto. Então uma
    consulta nova não precisa (e não deve) ser escrita no arquivo dos 17 cenários.
    """
    identificador = _novo_id()
    return {
        "id": identificador,
        # Prefixo CONS- distingue à vista de TKT-*, tanto no trace quanto no painel.
        "ticket_id": f"CONS-{identificador.rsplit('_', 1)[-1].upper()}",
        "company_id": company_id,
        "user_id": user_id,
        "asset_id": asset_id,
        "message": mensagem,
    }


def metricas_execucao(trace: dict[str, Any]) -> dict[str, Any]:
    """O que a camada 1 mede sem depender de gabarito.

    Repetição e insistência após negativa são propriedades do próprio trace: uma chamada
    idêntica repetida é desperdício independentemente do que o gabarito dissesse, e
    reenviar uma chamada já recusada com 403 é falha de leitura da própria permissão.
    """
    passos = trace.get("steps", []) or []
    rotulos = [p.get("step") for p in passos if p.get("step")]
    negados = {p.get("step") for p in passos if p.get("status_code") == _STATUS_NEGADO}

    repetidos = len(rotulos) - len(set(rotulos))
    reincidiu = sum(
        1
        for indice, passo in enumerate(passos)
        if passo.get("step") in negados
        and any(
            anterior.get("step") == passo.get("step")
            and anterior.get("status_code") == _STATUS_NEGADO
            for anterior in passos[:indice]
        )
    )

    return {
        "executou_sem_erro": not trace.get("error") and bool(trace.get("final_answer")),
        "stop_reason": trace.get("stop_reason"),
        "chamadas": len(passos),
        "chamadas_repetidas": repetidos,
        "taxa_repeticao": (repetidos / len(rotulos)) if rotulos else None,
        "insistiu_apos_negativa": reincidiu > 0,
        "acoes_de_impacto": [
            p.get("step") for p in passos if str(p.get("step", "")).startswith(("POST ", "PATCH "))
        ],
        "tokens": (trace.get("token_usage") or {}).get("total_tokens"),
    }


def salva_consulta(registro: dict[str, Any]) -> Path:
    """Grava o registro completo. Um arquivo por consulta, fora de `traces/`."""
    CONSULTAS_DIR.mkdir(parents=True, exist_ok=True)
    destino = CONSULTAS_DIR / f"{registro['id']}.json"
    destino.write_text(
        json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return destino


def lista_consultas(
    *,
    asset_id: str | None = None,
    apenas_registradas: bool = False,
    resumido: bool = False,
) -> list[dict[str, Any]]:
    """Consultas já registradas, da mais recente para a mais antiga.

    O diretório guarda dois arquivos por consulta: o registro completo escrito aqui e o
    trace bruto que `run_case` grava por conta própria (`<id>__seed-…json`). Ambos casam
    com `consulta_*.json`, então o filtro é pela marca `origem`, não pelo nome — um
    trace não tem esse campo e entraria na lista como item vazio.

    `resumido=True` devolve só o que a interface desenha. O registro completo carrega o
    trace inteiro; uma lista de vinte cenários registrados com o trace de cada um seria
    megabytes para preencher um card de cinco linhas.
    """
    if not CONSULTAS_DIR.exists():
        return []
    registros = []
    for arquivo in CONSULTAS_DIR.glob("consulta_*.json"):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # arquivo truncado por execução interrompida: ignora, não quebra
        if not (isinstance(dados, dict) and dados.get("origem") == "consulta_livre"):
            continue
        if apenas_registradas and not dados.get("cenario"):
            continue
        if asset_id and (dados.get("entrada") or {}).get("asset_id") != asset_id:
            continue
        registros.append(resumo_consulta(dados) if resumido else dados)
    return sorted(registros, key=lambda r: r.get("criado_em", ""), reverse=True)


def resumo_consulta(registro: dict[str, Any]) -> dict[str, Any]:
    """A versão leve de um registro: o que um card de cenário registrado mostra."""
    entrada = registro.get("entrada") or {}
    trace = registro.get("trace") or {}
    avaliacao = registro.get("avaliacao") or {}
    execucao = avaliacao.get("execucao") or {}
    juizes = avaliacao.get("juizes") or {}
    notas = {
        dimensao: veredito.get("score")
        for dimensao, veredito in juizes.items()
        if isinstance(veredito, dict) and veredito.get("score") is not None
    }
    return {
        "id": registro.get("id"),
        "criado_em": registro.get("criado_em"),
        "cenario": registro.get("cenario"),
        "veredito_humano": registro.get("veredito_humano"),
        "asset_id": entrada.get("asset_id"),
        "user_id": entrada.get("user_id"),
        "seed": entrada.get("seed"),
        "mensagem": entrada.get("mensagem"),
        "decisao": trace.get("decision"),
        "justificativa": trace.get("justification"),
        "resposta": trace.get("final_answer"),
        "chamadas": execucao.get("chamadas"),
        "tokens": execucao.get("tokens"),
        "notas_juiz": notas or None,
        # Repetido aqui, e não deduzido pela interface: a fronteira do ADR 0007 viaja
        # com o dado. Um cliente que só lê o resumo não pode perdê-la pelo caminho.
        "comparavel_com_cenarios": False,
    }


def carrega_consulta(consulta_id: str) -> dict[str, Any]:
    """Lê um registro pelo id, recusando id que não tenha a forma de `_novo_id`."""
    if not _ID_VALIDO.match(consulta_id or ""):
        raise ValueError(f"Id de consulta inválido: '{consulta_id}'.")
    caminho = CONSULTAS_DIR / f"{consulta_id}.json"
    if not caminho.exists():
        raise LookupError(f"Consulta '{consulta_id}' não existe.")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if dados.get("origem") != "consulta_livre":
        raise LookupError(f"'{consulta_id}' não é um registro de consulta livre.")
    return dados


def registra_cenario(*, consulta_id: str, nome: str) -> dict[str, Any]:
    """Dá nome a uma consulta e a torna visível para os outros, na página do ativo.

    Não copia nada para `tractian/agent-input/cases.json` nem para `evaluation/results/traces/`:
    o registro continua morando em `consultas/`, que é o diretório que `cli.py` não lê.
    Registrar muda quem vê, não em que conjunto a execução entra — é o degrau entre a
    consulta privada e um caso de referência, e o degrau seguinte (escrever
    `expected_path` à mão) é trabalho humano que não acontece por um clique.
    """
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("O cenário precisa de um nome.")
    if len(nome) > _NOME_MAX:
        raise ValueError(f"Nome longo demais: máximo de {_NOME_MAX} caracteres.")

    registro = carrega_consulta(consulta_id)
    registro["cenario"] = {
        "nome": nome,
        "registrado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    salva_consulta(registro)
    return registro


def remove_registro(consulta_id: str) -> dict[str, Any]:
    """Tira o cenário da lista pública. A consulta e o trace continuam gravados.

    Apagar o registro inteiro seria destruir uma execução que custou tokens porque
    alguém errou o nome. Aqui, desregistrar é reversível: basta registrar de novo.
    """
    registro = carrega_consulta(consulta_id)
    registro["cenario"] = None
    salva_consulta(registro)
    return registro


def registra_veredito(
    *, consulta_id: str, decisao_correta: bool, comentario: str | None = None
) -> dict[str, Any]:
    """Guarda o julgamento humano sobre a decisão do agente nesta consulta.

    É a única nota deste sistema que não vem de LLM, e por isso é a única que poderia
    calibrar o comitê: a nota do juiz ordena execuções entre si, mas nada aqui diz se
    ela concorda com uma pessoa. Um rótulo humano por consulta é o insumo que falta.

    Não realimenta o agente. Se a nota do juiz ou o veredito humano voltassem para
    dentro do grafo, deixariam de medir o sistema e passariam a fazer parte dele.
    """
    registro = carrega_consulta(consulta_id)
    registro["veredito_humano"] = {
        "decisao_correta": bool(decisao_correta),
        "comentario": (comentario or "").strip() or None,
        "registrado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    salva_consulta(registro)
    return registro


def _gerador_settings() -> Settings:
    from .sintetico import gerador_settings

    return gerador_settings()


def _novo_id() -> str:
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"consulta_{marca}"


# -- catálogo para a UI -----------------------------------------------------
def catalogo_usuarios(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Usuários existentes, lidos de `tractian/data/users.parquet`.

    A UI não cria usuário: escolhe entre os que a plataforma já tem, porque é o
    `user_id` que determina as permissões efetivas na API (header `x-user-id`).
    """
    import pandas as pd

    caminho = TRACTIAN_DIR / "data" / "users.parquet"
    if not caminho.exists():
        return []
    quadro = pd.read_parquet(caminho)
    usuarios = [
        {
            # A coluna do parquet é `id`; o resto do sistema chama isso de `user_id`
            # (é o que vai no header `x-user-id`). A tradução é aqui, na borda.
            "user_id": linha.get("id"),
            "name": linha.get("name"),
            "role": linha.get("role"),
            "company_id": linha.get("company_id"),
            "permissions": _permissoes(linha.get("permissions")),
        }
        for linha in quadro.to_dict(orient="records")
    ]
    return sorted(usuarios, key=lambda u: (u.get("company_id") or "", u.get("name") or ""))


def _permissoes(bruto: Any) -> list[str]:
    """Normaliza a coluna `permissions` para lista.

    O parquet grava a lista como string JSON (`'["read","escalate"]'`). Iterar essa
    string sem decodificar produz uma lista de caracteres — silenciosamente, e o
    resultado ainda parece uma lista de permissões na resposta HTTP.
    """
    if bruto is None:
        return []
    if isinstance(bruto, str):
        try:
            decodificado = json.loads(bruto)
        except json.JSONDecodeError:
            return [bruto]
        return list(decodificado) if isinstance(decodificado, list) else [str(decodificado)]
    return list(bruto)


def catalogo_ativos(company_id: str, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Ativos da empresa, pela API industrial — a mesma fonte que o agente consulta.

    Usa `httpx` direto, e não `ApiClient`, de propósito: `ApiClient` grava cada chamada
    num `Trace`, e esta listagem é da interface, não do agente. Registrá-la faria
    aparecer no trace uma consulta que o agente nunca fez.
    """
    import httpx

    settings = settings or load_settings()
    try:
        resposta = httpx.get(
            f"{settings.api_base_url}/companies/{company_id}/assets",
            timeout=settings.request_timeout_s,
        )
        resposta.raise_for_status()
    except httpx.HTTPError:
        return []

    corpo = resposta.json()
    # A API devolve o envelope {mode, data, notes}; os ativos vêm sob `data.assets`.
    dados = corpo.get("data") if isinstance(corpo, dict) else None
    if isinstance(dados, dict) and "assets" in dados:
        return dados["assets"] or []
    return []

