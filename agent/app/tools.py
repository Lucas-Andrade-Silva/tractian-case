"""Tools expostas ao LLM, agrupadas pelos papéis do agente.

Cada grupo corresponde a um papel do CONTEXT.md e é entregue só ao nó daquele papel:

- `investigation_tools`  → Investigador (evidência técnica: sensor, análise, modelo)
- `knowledge_tools`      → Contextualizador (evidência documental)
- `action_tools`         → Executor (ações de impacto na plataforma)

O Decisor não recebe tool alguma — ele pesa o que já foi apurado e resolve o caso
(ADR 0001). As descrições carregam o conhecimento de domínio necessário para o LLM
escolher a tool certa: são elas que ensinam, por exemplo, que o limiar de RMS deriva
do baseline e não de norma fixa.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from .api_client import ApiClient

# Séries longas viram ruído no contexto; acima disso reamostramos preservando extremos.
_MAX_SAMPLES_INLINE = 30


def _summarize_rms(data: dict[str, Any]) -> dict[str, Any]:
    """Condensa a série de RMS sem esconder a evidência que decide o caso.

    Mantém os campos originais e acrescenta um resumo — inclusive se o limiar de alarme
    (derivado do baseline) foi ultrapassado, que é a evidência central de vários cenários.
    """
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        return data

    values = [s.get("value") for s in samples if isinstance(s.get("value"), (int, float))]
    if not values:
        return data

    threshold = data.get("alarm_threshold")
    summary = {
        "count": len(values),
        "first": values[0],
        "last": values[-1],
        "min": min(values),
        "max": max(values),
        "trend": "subindo" if values[-1] > values[0] else "estável ou caindo",
    }
    if isinstance(threshold, (int, float)):
        summary["exceeds_alarm_threshold"] = max(values) > threshold

    out = {**data, "summary": summary}
    if len(samples) > _MAX_SAMPLES_INLINE:
        stride = len(samples) // _MAX_SAMPLES_INLINE + 1
        out["samples"] = samples[::stride]
        out["samples_note"] = (
            f"Série reamostrada para leitura: {len(out['samples'])} de {len(samples)} pontos "
            f"(1 a cada {stride}). Use `summary` para extremos e limiar."
        )
    return out


def _unwrap(result: dict[str, Any], *, summarizer=None) -> dict[str, Any]:
    """Achata o resultado do cliente no que o LLM precisa ver.

    Preserva sempre `mode` e `notes`: são eles que dizem se a resposta veio completa,
    parcial, inconclusiva, conflitante ou indisponível — e o agente precisa disso para
    ser honesto sobre incerteza em vez de tratar tudo como fato consolidado.
    """
    if not result.get("ok"):
        return {
            "ok": False,
            "status_code": result.get("status_code"),
            "error": result.get("error"),
            "error_kind": result.get("error_kind"),
        }

    data = result.get("data")
    if summarizer and isinstance(data, dict):
        data = summarizer(data)
    return {
        "ok": True,
        "mode": result.get("mode"),
        "notes": result.get("notes"),
        "data": data,
    }


# ---------------------------------------------------------------------------
# Investigador — evidência técnica
# ---------------------------------------------------------------------------
def investigation_tools(client: ApiClient) -> list[StructuredTool]:
    """Tools de apuração técnica. Nenhuma delas altera estado na plataforma."""

    def get_asset(asset_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}"))

    def get_company(company_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/companies/{company_id}"))

    def list_company_assets(company_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/companies/{company_id}/assets"))

    def list_analyses(asset_id: str, status: str | None = None) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/analyses", status=status))

    def get_analysis(analysis_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/analyses/{analysis_id}"))

    def get_baseline(asset_id: str, point_id: str | None = None) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/baseline", point_id=point_id))

    def get_rms(asset_id: str, point_id: str | None = None) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/rms", point_id=point_id), summarizer=_summarize_rms)

    def get_spectrum(asset_id: str, point_id: str | None = None) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/spectrum", point_id=point_id))

    def get_data_quality(asset_id: str, point_id: str | None = None) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/data-quality", point_id=point_id))

    def get_model(model_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/models/{model_id}"))

    return [
        StructuredTool.from_function(
            get_asset,
            name="get_asset",
            description=(
                "Cadastro do ativo: criticidade, hierarquia, configuração técnica "
                "(machine_type, rotation_rpm, bearing_specs, line_frequency_hz) e os pontos de "
                "medição com sensor_status (online/offline/degraded). Comece por aqui: o "
                "machine_type e o rotation_rpm definem o que o modelo consegue cobrir, e um "
                "sensor offline/degraded costuma explicar ausência de dados."
            ),
        ),
        StructuredTool.from_function(
            get_company,
            name="get_company",
            description="Dados da empresa do caso (nome, segmento, timezone).",
        ),
        StructuredTool.from_function(
            list_company_assets,
            name="list_company_assets",
            description="Lista os ativos de uma empresa. Use se precisar localizar um ativo não informado no caso.",
        ),
        StructuredTool.from_function(
            list_analyses,
            name="list_analyses",
            description=(
                "Análises (insights) do ativo. Filtro opcional `status`: current, stale, pending "
                "ou inconclusive. 'pending' indica insight ainda não emitido (ver processing_state "
                "do modelo); 'stale' indica insight desatualizado, típico após manutenção."
            ),
        ),
        StructuredTool.from_function(
            get_analysis,
            name="get_analysis",
            description=(
                "Detalhe de uma análise: tipo de falha, severidade, confiança, evidência métrica, "
                "limitations, model_version, detection_mode e baseline_state_at_detection. Use para "
                "julgar se um insight é confiável — um insight detectado com baseline em learning "
                "ou invalidated tem valor limitado quando detection_mode=baseline."
            ),
        ),
        StructuredTool.from_function(
            get_baseline,
            name="get_baseline",
            description=(
                "Baseline do ativo/ponto: o estado normal aprendido do próprio ativo. `state` é "
                "learning (histórico insuficiente), established (utilizável) ou invalidated (após "
                "manutenção/mudança de config, exige reaprendizado). `detection_mode` é baseline "
                "(detecção por desvio, exige established) ou symptom (detecção sintomática, ex.: "
                "lubrificação, independe de baseline). Inspecione ANTES de confiar num insight "
                "de detection_mode=baseline."
            ),
        ),
        StructuredTool.from_function(
            get_rms,
            name="get_rms",
            description=(
                "Série temporal de RMS de vibração, com baseline_reference, baseline_state e "
                "alarm_threshold. ATENÇÃO: o alarm_threshold é derivado do baseline do próprio "
                "ativo (referência + tolerância) — não é norma ISO nem tabela fixa por classe de "
                "máquina. Retorna também um `summary` com máximo, tendência e se o limiar foi "
                "ultrapassado."
            ),
        ),
        StructuredTool.from_function(
            get_spectrum,
            name="get_spectrum",
            description=(
                "Espectro FFT simplificado: picos por frequência com anotação. Frequências "
                "características: 1x = desbalanceamento, 2x = desalinhamento, BPFO/BPFI/BSF/FTF = "
                "falha de rolamento, 2x frequência de linha = falha elétrica. Em modo partial vem "
                "`bands_missing` — bandas ausentes podem impedir a conclusão."
            ),
        ),
        StructuredTool.from_function(
            get_data_quality,
            name="get_data_quality",
            description=(
                "Qualidade e frescor do sinal: completeness, snr_db, freshness_minutes e "
                "staleness_flag. Sempre compare com os `requirements` do modelo (get_model) em vez "
                "de julgar isoladamente — é isso que separa 'dados ruins' de 'modelo atrasado'."
            ),
        ),
        StructuredTool.from_function(
            get_model,
            name="get_model",
            description=(
                "Modelo de diagnóstico: version, coverage por machine_type (supported e "
                "can_learn_baseline), requirements (min_completeness, min_snr_db, min_rotation_rpm) "
                "e processing_state (idle/running/pending/delayed/failed). Use o model_version que "
                "aparece numa análise como id. processing_state=delayed explica insight ausente sem "
                "que os dados sejam ruins."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Contextualizador — evidência documental
# ---------------------------------------------------------------------------
def knowledge_tools(client: ApiClient) -> list[StructuredTool]:
    """Tools de conhecimento documental (procedimentos, glossário, orientações)."""

    def search_knowledge(q: str, type: str | None = None) -> dict[str, Any]:
        return _unwrap(client.get("/knowledge/search", q=q, type=type))

    def get_knowledge_doc(doc_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/knowledge/{doc_id}"))

    return [
        StructuredTool.from_function(
            search_knowledge,
            name="search_knowledge",
            description=(
                "Busca na base de conhecimento por texto livre `q`. Filtro opcional `type`: "
                "procedure (passo a passo de manutenção), glossary (definição de termo técnico, "
                "ex.: BPFO) ou guidance (orientação de suporte). Use quando a pergunta pede "
                "explicação, procedimento ou definição — não dados de sensor."
            ),
        ),
        StructuredTool.from_function(
            get_knowledge_doc,
            name="get_knowledge_doc",
            description="Recupera o documento completo pelo id retornado em search_knowledge.",
        ),
    ]


# ---------------------------------------------------------------------------
# Executor — ações de impacto
# ---------------------------------------------------------------------------
def action_tools(client: ApiClient, case_id: str) -> list[StructuredTool]:
    """Tools que alteram estado na plataforma.

    Toda ação exige `justification` (≥ 20 caracteres, validado pela própria API) e pode
    ser rejeitada com 403 se o perfil do usuário não tiver a permissão. A rejeição é
    devolvida ao agente, não bloqueada aqui (ADR 0003).
    """

    def reprocess_analysis(analysis_id: str, justification: str) -> dict[str, Any]:
        return _unwrap(client.post(f"/analyses/{analysis_id}/reprocess", {"justification": justification}))

    def request_specialist_analysis(analysis_id: str, justification: str) -> dict[str, Any]:
        return _unwrap(
            client.post(f"/analyses/{analysis_id}/request-specialist", {"justification": justification})
        )

    def request_retraining(model_id: str, justification: str) -> dict[str, Any]:
        return _unwrap(client.post(f"/models/{model_id}/request-retraining", {"justification": justification}))

    def update_asset_config(
        asset_id: str, justification: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        return _unwrap(
            client.patch(f"/assets/{asset_id}", {"justification": justification, "changes": changes})
        )

    def escalate_case(justification: str) -> dict[str, Any]:
        return _unwrap(client.post(f"/cases/{case_id}/escalate", {"justification": justification}))

    return [
        StructuredTool.from_function(
            reprocess_analysis,
            name="reprocess_analysis",
            description=(
                "Reprocessa uma análise. Exige permissão action_low. Use quando a evidência "
                "indicar que o insight está desatualizado ou não foi emitido por atraso do modelo "
                "— não para insatisfação genérica com o resultado."
            ),
        ),
        StructuredTool.from_function(
            request_specialist_analysis,
            name="request_specialist_analysis",
            description=(
                "Solicita análise de um especialista humano da Tractian sobre a análise indicada. "
                "Exige permissão action_low. É uma ação técnica interna (categoria 'agir'), NÃO é "
                "o mesmo que escalar o caso para atendimento em campo."
            ),
        ),
        StructuredTool.from_function(
            request_retraining,
            name="request_retraining",
            description=(
                "Solicita retreinamento do modelo. Ação de ALTO impacto: exige permissão "
                "action_high e justificativa forte, baseada em evidência de erro sistemático do "
                "modelo — não em uma única discordância pontual."
            ),
        ),
        StructuredTool.from_function(
            update_asset_config,
            name="update_asset_config",
            description=(
                "Altera configuração técnica ou criticidade do ativo. Ação de ALTO impacto: exige "
                "permissão action_high. `changes` aceita {'criticality': low|medium|high|critical} "
                "e/ou {'config': {...}}."
            ),
        ),
        StructuredTool.from_function(
            escalate_case,
            name="escalate_case",
            description=(
                "Encaminha ESTE caso para análise humana. Exige permissão escalate. Use quando o "
                "caso extrapola o atendimento remoto (ex.: exige intervenção física em campo). "
                "Não use como saída segura para casos resolvíveis remotamente — escalar demais é "
                "tratado como erro do agente."
            ),
        ),
    ]
