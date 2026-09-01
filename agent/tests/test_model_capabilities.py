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


def test_decider_escalates_when_evidence_is_physical_and_irreversible():
    """Trava a calibração de escalonamento do Decisor (TKT-INV-04).

    Evidência fixa e idêntica à observada no experimento real: sensor offline, baseline
    em learning, dados incompletos, RMS indisponível — causa física, nenhuma ação remota
    resolve. Antes da correção do prompt, o mesmo Decisor alternava orientar/orientar/escalar
    entre seeds com essa evidência inalterada; o critério de "quando escalar é a decisão
    certa" estava ausente da política. Roda 1x contra o modelo real do papel (não é
    determinístico por natureza — é o que este teste está verificando).
    """
    from app.prompts import decider_prompt
    from app.state import Decision

    settings = load_settings()
    model = settings.model_for("decisor")

    case = {
        "id": "case_tkt_inv_04",
        "ticket_id": "TKT-INV-04",
        "company_id": "cmp_mineracao_andes",
        "user_id": "usr_pedro",
        "asset_id": "asset_G501",
        "message": "O redutor da correia transportadora quebrou ontem e eu não recebi nenhum aviso. Por quê?",
    }
    user_context = {"role": "Coordenador de Manutenção", "permissions": ["read", "escalate"]}
    findings = [
        "sensor_status=offline (asset)\n"
        "baseline.state=learning (baseline)\n"
        "data_quality.completeness=0.18 (data_quality)\n"
        "data_quality.snr_db=3.1 (data_quality)\n"
        "data_quality.staleness_flag=true (data_quality)\n"
        "rms=unavailable (rms)\n"
        "analyses=inconclusive (list_analyses)\n"
        "Causa raiz: sensor offline impediu coleta de dados, impossibilitando geração de "
        "baseline e alertas."
    ]

    result = build_llm(_settings_for(model)).with_structured_output(
        Decision, include_raw=True
    ).invoke(
        [
            SystemMessage(decider_prompt(case, user_context, findings)),
            HumanMessage("Resolva o caso agora, com base apenas na evidência apurada."),
        ]
    )

    parsed = result.get("parsed") if isinstance(result, dict) else result
    assert parsed is not None, (
        f"O modelo '{model}' (papel decisor) não emitiu Decision válido: "
        f"{result.get('parsing_error') if isinstance(result, dict) else '—'}"
    )
    assert parsed.decision == "escalar", (
        "Causa física (sensor offline) sem ação remota disponível deveria escalar, não "
        f"'{parsed.decision}' — regressão na calibração de _DECISION_POLICY. "
        f"Justificativa emitida: {parsed.justification!r}"
    )
