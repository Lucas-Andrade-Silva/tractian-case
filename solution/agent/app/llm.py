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

from .config import ROLES, Settings

_SUPPORTED = ("groq", "openai", "openrouter")

# OpenRouter fala o protocolo da OpenAI, então reaproveita o mesmo cliente — o que muda é
# só o endereço. Fica aqui, e não no .env, porque é característica do provedor e não
# configuração de quem usa.
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_llm(settings: Settings, **overrides: Any) -> BaseChatModel:
    """Instancia o chat model configurado.

    `temperature=0` por padrão: a Parte 2 mede estabilidade entre execuções, e
    variação amostral do próprio decoder confundiria essa medida com instabilidade do
    agente.
    """
    provider = (settings.llm_provider or "").strip().lower()
    # `model` pode vir por override (modelo de um papel específico); só então caímos no
    # LLM_MODEL geral, que numa configuração por papel pode nem estar definido.
    model = str(overrides.pop("model", "") or settings.llm_model or "").strip()

    if not provider:
        raise LlmNotConfigured(
            "LLM_PROVIDER não definido. Copie agent/.env.example para agent/.env e "
            f"escolha um provedor ({', '.join(_SUPPORTED)}) + LLM_MODEL."
        )
    if not model:
        raise LlmNotConfigured(
            f"Nenhum modelo definido para o provedor '{provider}'. Defina LLM_MODEL ou "
            "um MODEL_<PAPEL> para cada papel."
        )

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

    if provider in ("openai", "openrouter"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - depende de instalação opcional
            raise LlmNotConfigured(
                f"Provedor '{provider}' escolhido mas langchain-openai não está instalado. "
                'Rode: uv pip install -e ".[openai]"'
            ) from exc
        if settings.llm_api_key:
            params["api_key"] = settings.llm_api_key
        if provider == "openrouter":
            params.setdefault("base_url", _OPENROUTER_BASE_URL)
        return ChatOpenAI(**params)

    raise LlmNotConfigured(
        f"Provedor '{provider}' não suportado. Use um de: {', '.join(_SUPPORTED)}."
    )


class LlmNotConfigured(RuntimeError):
    """Configuração de LLM ausente ou incompleta."""


class RoleModels:
    """Resolve o modelo de cada papel, reaproveitando clientes já instanciados.

    Papéis diferentes têm exigências diferentes: quem chama tools em série se beneficia
    de um modelo que emita várias tool calls por resposta (corta voltas e, com elas, o
    custo fixo de prompt+schemas reenviado a cada volta); quem produz a decisão e a
    justificativa — o que a avaliação de fato julga — se beneficia do modelo mais capaz.

    Como os limites de cota da Groq são por modelo, distribuir papéis entre modelos
    também distribui o consumo entre pools separados.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, BaseChatModel] = {}

    def for_role(self, role: str) -> BaseChatModel:
        model = self._settings.model_for(role)
        if model not in self._cache:
            self._cache[model] = build_llm(self._settings, model=model)
        return self._cache[model]

    def describe(self) -> dict[str, str]:
        """Mapa papel → modelo efetivo, para registrar no trace do experimento."""
        return {role: self._settings.model_for(role) for role in ROLES}
