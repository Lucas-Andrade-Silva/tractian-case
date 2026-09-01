"""Verifica que cada modelo configurado suporta o que seu papel exige.

Um modelo que não emite structured output quebra o grafo inteiro no meio da execução —
foi o que aconteceu com `qwen3.6-27b` no Supervisor, que falhava com `tool_use_failed`
de forma reprodutível. O custo de descobrir isso numa rodada de 51 execuções é alto;
aqui custa uma chamada por modelo.

Requer rede e cota (marcado `llm`). Rode com `-m llm` quando quiser validar uma troca
de modelo:  pytest -m llm
"""
from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ROLES, Settings, load_settings
from app.llm import build_llm
from app.state import Decision, Route

pytestmark = pytest.mark.llm

# Papéis que dependem de saída estruturada para o grafo transitar.
STRUCTURED_ROLES = {"supervisor": Route, "decisor": Decision}
# Papéis que precisam chamar tools.
TOOL_ROLES = ("investigador", "contextualizador", "executor")


def _settings_for(model: str) -> Settings:
    base = load_settings()
    return Settings(
        api_base_url=base.api_base_url,
        llm_provider=base.llm_provider,
        llm_model=model,
        llm_api_key=base.llm_api_key,
        llm_temperature=0.0,
        agent_port=base.agent_port,
        request_timeout_s=60,
        max_supervisor_turns=base.max_supervisor_turns,
        max_worker_steps=base.max_worker_steps,
        models_by_role={},
    )


@pytest.mark.parametrize("role", sorted(STRUCTURED_ROLES))
def test_structured_output_roles_can_emit_their_schema(role: str):
    """Supervisor e Decisor dependem de structured output: sem isso o grafo não transita."""
    settings = load_settings()
    model = settings.model_for(role)
    schema = STRUCTURED_ROLES[role]

    result = build_llm(_settings_for(model)).with_structured_output(
        schema, include_raw=True
    ).invoke(
        [
            SystemMessage(
                "Você faz parte de um agente de suporte industrial. Responda apenas no "
                "formato estruturado pedido."
            ),
            HumanMessage(
                "Caso: o redutor quebrou e o cliente não recebeu aviso. Já foi apurado "
                "que o baseline está em learning e o sensor está offline. Responda."
            ),
        ]
    )

    parsed = result.get("parsed") if isinstance(result, dict) else result
    assert parsed is not None, (
        f"O modelo '{model}' (papel {role}) não emitiu {schema.__name__} válido: "
        f"{result.get('parsing_error') if isinstance(result, dict) else '—'}"
    )


@pytest.mark.parametrize("role", TOOL_ROLES)
def test_tool_calling_roles_can_call_a_tool(role: str):
    """Investigador, Contextualizador e Executor precisam emitir tool call válida."""
    from langchain_core.tools import StructuredTool

    settings = load_settings()
    model = settings.model_for(role)

    def consultar_ativo(asset_id: str) -> str:
        """Consulta a configuração técnica de um ativo."""
        return f"ok {asset_id}"

    tool = StructuredTool.from_function(
        consultar_ativo,
        name="consultar_ativo",
        description="Consulta a configuração técnica de um ativo industrial.",
    )

    response = build_llm(_settings_for(model)).bind_tools([tool]).invoke(
        [
            SystemMessage("Use as tools disponíveis para apurar o que for pedido."),
            HumanMessage("Qual a configuração técnica do ativo asset_G501?"),
        ]
    )

    assert getattr(response, "tool_calls", None), (
        f"O modelo '{model}' (papel {role}) não emitiu tool call."
    )


def test_every_role_resolves_to_a_model():
    """Papel sem modelo resolvido faria o grafo estourar só na execução."""
    settings = load_settings()

    for role in ROLES:
        assert settings.model_for(role), f"papel {role} sem modelo"
