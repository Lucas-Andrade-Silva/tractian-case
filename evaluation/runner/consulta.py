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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings, load_settings
from app.llm import build_llm
from app.runner import run_case

from .judges import com_saida_estruturada, judge_settings, run_committee
from .sintetico import GabaritoSintetico, assert_modelos_distintos, gera_gabarito

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONSULTAS_DIR = REPO_ROOT / "evaluation" / "results" / "consultas"

# Sinaliza um 403 da API no passo, sem depender da mensagem exata em português.
_STATUS_NEGADO = 403


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
) -> dict[str, Any]:
    """Roda uma consulta livre de ponta a ponta e devolve o registro completo.

    `julgar=False` executa o agente e pula o comitê — útil para ver a resposta sem
    gastar duas chamadas de LLM adicionais quando a cota está apertada.
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
    gabarito: GabaritoSintetico | None = None
    erro_gabarito: str | None = None
    if julgar:
        assert_modelos_distintos(_gerador_settings(), judge_settings())
        try:
            gabarito = gera_gabarito(caso, contexto_ativo=contexto_ativo)
        except Exception as exc:  # noqa: BLE001 - vira dado do registro, não interrompe
            erro_gabarito = f"{type(exc).__name__}: {exc}"

    trace = run_case(caso, seed=seed, settings=settings, save_to=CONSULTAS_DIR)
    dados_trace = trace.to_dict()

    vereditos: dict[str, Any] | None = None
    erro_juiz: str | None = None
    if gabarito is not None:
        try:
            # A sonda descobre qual método de saída estruturada o modelo do juiz aceita.
            # Sem ela, um modelo que devolve a nota em Markdown ("**Nota: 5**") derruba
            # o comitê depois de já ter feito o raciocínio — nota perdida por formato.
            llm_juiz = com_saida_estruturada(build_llm(judge_settings()))
            vereditos = run_committee(dados_trace, gabarito.golden, llm=llm_juiz)
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

    `run_case` nunca lê `agent-input/cases.json` — recebe o dict pronto. Então uma
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


def lista_consultas() -> list[dict[str, Any]]:
    """Consultas já registradas, da mais recente para a mais antiga.

    O diretório guarda dois arquivos por consulta: o registro completo escrito aqui e o
    trace bruto que `run_case` grava por conta própria (`<id>__seed-…json`). Ambos casam
    com `consulta_*.json`, então o filtro é pela marca `origem`, não pelo nome — um
    trace não tem esse campo e entraria na lista como item vazio.
    """
    if not CONSULTAS_DIR.exists():
        return []
    registros = []
    for arquivo in CONSULTAS_DIR.glob("consulta_*.json"):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # arquivo truncado por execução interrompida: ignora, não quebra
        if isinstance(dados, dict) and dados.get("origem") == "consulta_livre":
            registros.append(dados)
    return sorted(registros, key=lambda r: r.get("criado_em", ""), reverse=True)


def _gerador_settings() -> Settings:
    from .sintetico import gerador_settings

    return gerador_settings()


def _novo_id() -> str:
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"consulta_{marca}"


# -- catálogo para a UI -----------------------------------------------------
def catalogo_usuarios(settings: Settings | None = None) -> list[dict[str, Any]]:
    """Usuários existentes, lidos de `data/users.parquet`.

    A UI não cria usuário: escolhe entre os que a plataforma já tem, porque é o
    `user_id` que determina as permissões efetivas na API (header `x-user-id`).
    """
    import pandas as pd

    caminho = REPO_ROOT / "data" / "users.parquet"
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

