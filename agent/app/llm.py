"""Binding do provedor de LLM — o único ponto do código que sabe qual provedor é usado.

Isolado de propósito: o grafo, as tools e o trace não dependem de provedor. Trocar de
provedor (ou comparar dois no experimento) é mudar `LLM_PROVIDER`/`LLM_MODEL` no
`.env`, sem tocar em mais nada.

O pacote do provedor é uma dependência opcional — instale só o que for usar:
    uv pip install -e ".[groq]"
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from .config import Settings

_SUPPORTED = ("groq", "openai")


def build_llm(settings: Settings, **overrides: Any) -> BaseChatModel:
    """Instancia o chat model configurado.

    `temperature=0` por padrão: a Parte 2 mede estabilidade entre execuções, e
    variação amostral do próprio decoder confundiria essa medida com instabilidade do
    agente.
    """
    provider = (settings.llm_provider or "").strip().lower()
    model = (settings.llm_model or "").strip()

    if not provider:
        raise LlmNotConfigured(
            "LLM_PROVIDER não definido. Copie agent/.env.example para agent/.env e "
            f"escolha um provedor ({', '.join(_SUPPORTED)}) + LLM_MODEL."
        )
    if not model:
        raise LlmNotConfigured(f"LLM_MODEL não definido para o provedor '{provider}'.")

    params: dict[str, Any] = {
        "model": model,
        "temperature": settings.llm_temperature,
        **overrides,
    }

    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:  # pragma: no cover - depende de instalação opcional
            raise LlmNotConfigured(
                "Provedor 'groq' escolhido mas langchain-groq não está instalado. "
                'Rode: uv pip install -e ".[groq]"'
            ) from exc
        if settings.llm_api_key:
            params["api_key"] = settings.llm_api_key
        return ChatGroq(**params)

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - depende de instalação opcional
            raise LlmNotConfigured(
                "Provedor 'openai' escolhido mas langchain-openai não está instalado. "
                'Rode: uv pip install -e ".[openai]"'
            ) from exc
        if settings.llm_api_key:
            params["api_key"] = settings.llm_api_key
        return ChatOpenAI(**params)

    raise LlmNotConfigured(
        f"Provedor '{provider}' não suportado. Use um de: {', '.join(_SUPPORTED)}."
    )


class LlmNotConfigured(RuntimeError):
    """Configuração de LLM ausente ou incompleta."""
