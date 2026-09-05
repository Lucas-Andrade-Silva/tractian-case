"""Catálogo de modelos de juiz e construção de um juiz por dimensão.

O juiz é **sempre do OpenRouter**, e os papéis do agente sempre da Groq. Não é
preferência: separa as cotas (uma bateria de julgamento não come o orçamento diário que o
Investigador precisa) e garante de saída a regra do ADR 0007 — o gerador do gabarito
sintético roda na Groq, então nenhum modelo de juiz pode coincidir com ele.

Cada dimensão do comitê pode ter modelo próprio. As três medem coisas diferentes —
`causa_raiz` é raciocínio técnico sobre limiares e espectro, `honestidade` é leitura de
hedge no texto — e entre modelos gratuitos a competência varia muito de uma para outra.
Poder trocar uma sem mexer nas outras é o que torna útil ter o seletor na interface.

A lista de modelos é consultada ao vivo na API do OpenRouter, e só cai na lista local se a
consulta falhar. Uma lista fixa envelhece sozinha: o catálogo muda e um modelo sai do
plano gratuito sem aviso — a única pista seria um 404 no meio de uma rodada.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from app.config import Settings, load_settings
from app.llm import build_llm

from .judges import COMMITTEE, com_saida_estruturada

URL_MODELOS = "https://openrouter.ai/api/v1/models"

# Reserva usada quando a API do OpenRouter não responde. Todos declaram suporte a saída
# estruturada, que o comitê exige: o juiz precisa devolver raciocínio e nota separados.
MODELOS_GRATUITOS: list[tuple[str, str]] = [
    ("minimax/minimax-m3:free", "MiniMax M3 — contexto amplo, JSON estável"),
    ("nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 3 Super 120B — forte em análise"),
    ("z-ai/glm-5.2:free", "GLM 5.2 — bom raciocínio técnico"),
    ("google/gemma-4-31b-it:free", "Gemma 4 31B — rápido"),
    ("dots-studio/dots-3-note-preview:free", "Dots 3 Note — contexto muito amplo"),
]

PADRAO = MODELOS_GRATUITOS[0][0]

# As chaves das dimensões, na ordem em que o comitê as julga.
DIMENSOES = tuple(judge.key for judge in COMMITTEE)


def modelos_ao_vivo() -> list[tuple[str, str]] | None:
    """Modelos `:free` que o OpenRouter lista agora, com saída estruturada declarada."""
    try:
        with urllib.request.urlopen(URL_MODELOS, timeout=20) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))["data"]
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
        return None

    achados = []
    for modelo in dados:
        identificador = modelo.get("id", "")
        suportados = modelo.get("supported_parameters") or []
        if not identificador.endswith(":free"):
            continue
        if not ({"structured_outputs", "response_format"} & set(suportados)):
            continue
        contexto = modelo.get("context_length") or 0
        achados.append((identificador, f"contexto {contexto:,}".replace(",", ".")))
    return sorted(achados, key=lambda par: par[0]) or None


def catalogo_modelos() -> dict[str, Any]:
    """Catálogo para a interface: modelos disponíveis, dimensões e o padrão de cada uma."""
    ao_vivo = modelos_ao_vivo()
    lista = ao_vivo or MODELOS_GRATUITOS
    return {
        "provedor": "openrouter",
        "origem": "api" if ao_vivo else "lista_local",
        "modelos": [{"id": i, "descricao": d} for i, d in lista],
        "dimensoes": [
            {"chave": judge.key, "titulo": judge.title, "padrao": modelo_padrao(judge.key)}
            for judge in COMMITTEE
        ],
        "chave_configurada": bool(_chave_openrouter()),
    }


def modelo_padrao(dimensao: str) -> str:
    """Modelo de uma dimensão quando a interface não escolhe.

    Precedência: `JUDGE_MODEL_<DIMENSAO>` → `JUDGE_MODEL` → `PADRAO`. A variável por
    dimensão existe para que uma troca feita na interface possa ser fixada no `.env`
    depois de dar resultado.
    """
    especifico = os.getenv(f"JUDGE_MODEL_{dimensao.upper()}")
    if especifico and especifico.strip():
        return especifico.strip()
    geral = os.getenv("JUDGE_MODEL")
    if geral and geral.strip() and _parece_openrouter(geral.strip()):
        return geral.strip()
    # `JUDGE_MODEL` apontando para a Groq não serve aqui: o juiz é sempre OpenRouter, e
    # usá-lo mandaria a chave do OpenRouter para o provedor errado (401).
    return PADRAO


def settings_juiz(modelo: str) -> Settings:
    """`Settings` de um juiz OpenRouter, com a chave dessa conta.

    O provedor é fixado em `openrouter` e não herdado de `LLM_PROVIDER`: herdá-lo foi
    exatamente o defeito que produziu 401 antes — chave de um provedor enviada ao outro.
    """
    base = load_settings()
    chave = _chave_openrouter()
    if not chave:
        raise ChaveDeJuizAusente(
            "O juiz roda no OpenRouter e não há chave configurada. Defina "
            "JUDGE_API_KEY (ou OPENROUTER_API_KEY) em agent/.env — crie uma gratuita "
            "em https://openrouter.ai/keys"
        )
    return Settings(
        api_base_url=base.api_base_url,
        llm_provider="openrouter",
        llm_model=modelo,
        llm_api_key=chave,
        llm_temperature=0.0,  # juiz é sempre determinístico
        agent_port=base.agent_port,
        request_timeout_s=base.request_timeout_s,
        max_supervisor_turns=base.max_supervisor_turns,
        max_worker_steps=base.max_worker_steps,
    )


class ChaveDeJuizAusente(RuntimeError):
    """Não há chave do OpenRouter para o juiz."""


def constroi_juizes(
    escolhas: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Monta um LLM por dimensão e devolve `(llms, modelos_usados)`.

    `escolhas` é o que a interface mandou (`{"causa_raiz": "z-ai/glm-5.2:free"}`);
    dimensão ausente cai em `modelo_padrao`. Modelos repetidos entre dimensões são
    instanciados uma vez só — a sonda de saída estruturada custa uma chamada, e três
    sondas iguais gastariam cota à toa.
    """
    escolhas = escolhas or {}
    llms: dict[str, Any] = {}
    usados: dict[str, str] = {}
    cache: dict[str, Any] = {}

    for dimensao in DIMENSOES:
        modelo = (escolhas.get(dimensao) or "").strip() or modelo_padrao(dimensao)
        if modelo not in cache:
            cache[modelo] = com_saida_estruturada(build_llm(settings_juiz(modelo)))
        llms[dimensao] = cache[modelo]
        usados[dimensao] = modelo

    return llms, usados


def _parece_openrouter(modelo: str) -> bool:
    """O id tem cara de OpenRouter?

    Heurística deliberadamente estreita: `:free` é marca do plano gratuito do OpenRouter.
    Ids sem esse sufixo existem nos dois provedores (`openai/gpt-oss-120b` está na Groq),
    então tratá-los como OpenRouter é o que causaria o 401.
    """
    return modelo.endswith(":free")


def _chave_openrouter() -> str | None:
    for nome in ("JUDGE_API_KEY", "OPENROUTER_API_KEY"):
        valor = os.getenv(nome)
        if valor and valor.strip():
            return valor.strip()
    return None
