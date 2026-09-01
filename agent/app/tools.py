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

# Pontos da série mantidos no retorno. A série bruta é o maior item de contexto que uma
# tool devolve, e ela fica no histórico do papel até ele encerrar: manter as 30 amostras
# custa ~400 tokens por chamada para uma informação que o `summary` já carrega.
_SAMPLES_KEPT = 6


def _summarize_rms(data: dict[str, Any]) -> dict[str, Any]:
    """Condensa a série de RMS sem esconder a evidência que decide o caso.

    O `summary` preserva o que os cenários realmente usam — tendência, extremos e se o
    limiar derivado do baseline foi ultrapassado. Os pontos individuais só entram em
    número suficiente para o agente perceber o formato da curva.
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
    if len(samples) > _SAMPLES_KEPT:
        stride = max(1, len(samples) // _SAMPLES_KEPT)
        kept = samples[::stride][:_SAMPLES_KEPT]
        # O último ponto é o estado atual do ativo: não pode cair na reamostragem.
        if kept[-1] is not samples[-1]:
            kept[-1] = samples[-1]
        out["samples"] = kept
        out["samples_note"] = (
            f"{len(kept)} de {len(samples)} pontos, amostrados ao longo da série "
            "(último ponto preservado). Extremos e limiar estão em `summary`."
        )
    return out


# Campos que não carregam evidência de diagnóstico e só ocupam espaço no scratch, onde
# cada resultado permanece até o papel encerrar a apuração. Os ids de ativo/ponto
# aparecem repetidos em toda resposta, e o agente já os conhece do bloco do caso.
_NOISE_FIELDS = frozenset(
    {"asset_id", "point_id", "company_id", "id", "plant", "line", "parent_asset_id"}
)


def _strip_noise(data: Any) -> Any:
    """Remove campos redundantes, preservando tudo que sustenta um diagnóstico.

    Aplicado só ao nível raiz: campos aninhados (evidência, features, picos do espectro,
    cobertura do modelo) são justamente a evidência e ficam intactos.
    """
    if not isinstance(data, dict):
        return data
    # Campos nulos também saem: "bearing_pn: null" não informa nada que a ausência do
    # campo já não diga, e um ativo sem rolamento especificado tem vários deles.
    return {
        k: v
        for k, v in data.items()
        if k not in _NOISE_FIELDS and v is not None
    }


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
    data = _strip_noise(data)
    return {
        "ok": True,
        "mode": result.get("mode"),
        "notes": result.get("notes"),
        "data": data,
    }


# ---------------------------------------------------------------------------
# Investigador — evidência técnica
# ---------------------------------------------------------------------------
def investigation_tools(client: ApiClient, *, include_company: bool = False) -> list[StructuredTool]:
    """Tools de apuração técnica. Nenhuma delas altera estado na plataforma.

    Por padrão as consultas de empresa ficam de fora. Elas não aparecem em nenhum dos 25
    cenários (golden + holdout) — o caso já informa empresa e ativo —, mas cada tool
    exposta soma ao custo fixo reenviado a cada volta e amplia o espaço de escolha errada:
    na medição por papel, o Investigador gastou uma volta inteira num `get_company` que
    não sustentava nada. `include_company=True` recupera a capacidade quando um caso
    precisar localizar um ativo não informado.
    """

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

    def get_baseline(asset_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/baseline"))

    def get_rms(asset_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/rms"), summarizer=_summarize_rms)

    def get_spectrum(asset_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/spectrum"))

    def get_data_quality(asset_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/assets/{asset_id}/data-quality"))

    def get_model(model_id: str) -> dict[str, Any]:
        return _unwrap(client.get(f"/models/{model_id}"))

    company_tools = [
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
    ]

    return [
        StructuredTool.from_function(
            get_asset,
            name="get_asset",
            description=(
                "Cadastro do ativo: criticidade, hierarquia, config técnica (machine_type, "
                "rotation_rpm, bearing_specs) e pontos com sensor_status. Comece por aqui: "
                "machine_type define a cobertura do modelo; sensor offline/degraded explica "
                "ausência de dados."
            ),
        ),
        *(company_tools if include_company else []),
        StructuredTool.from_function(
            list_analyses,
            name="list_analyses",
            description=(
                "Análises (insights) do ativo. `status` opcional: current, stale, pending, "
                "inconclusive. 'pending' = ainda não emitido (ver processing_state do modelo); "
                "'stale' = desatualizado, típico após manutenção."
            ),
        ),
        StructuredTool.from_function(
            get_analysis,
            name="get_analysis",
            description=(
                "Detalhe da análise: tipo, severidade, confiança, evidência, limitations, "
                "model_version, detection_mode e baseline_state_at_detection. Use para julgar "
                "se o insight é confiável."
            ),
        ),
        StructuredTool.from_function(
            get_baseline,
            name="get_baseline",
            description=(
                "Baseline do ativo/ponto: state (learning/established/invalidated), detection_mode, "
                "learnable, invalidation_reason e features (reference+tolerance). Inspecione "
                "ANTES de confiar num insight de detection_mode=baseline."
            ),
        ),
        StructuredTool.from_function(
            get_rms,
            name="get_rms",
            description=(
                "Série de RMS com baseline_reference, baseline_state e alarm_threshold (derivado "
                "do baseline do ativo, NÃO de norma ISO). Traz `summary` com máximo, tendência "
                "e se o limiar foi ultrapassado."
            ),
        ),
        StructuredTool.from_function(
            get_spectrum,
            name="get_spectrum",
            description=(
                "Espectro FFT: picos por frequência com anotação (1x, 2x, BPFO...). Em modo "
                "partial vem `bands_missing` — bandas ausentes podem impedir a conclusão."
            ),
        ),
        StructuredTool.from_function(
            get_data_quality,
            name="get_data_quality",
            description=(
                "Qualidade do sinal: completeness, snr_db, freshness_minutes, staleness_flag. "
                "Compare com os `requirements` do modelo (get_model) — é o que separa 'dados "
                "ruins' de 'modelo atrasado'."
            ),
        ),
        StructuredTool.from_function(
            get_model,
            name="get_model",
            description=(
                "Modelo: version, coverage por machine_type (supported, can_learn_baseline), "
                "requirements e processing_state. Id típico: mdl_vib_v3. "
                "processing_state=delayed explica insight ausente sem que os dados sejam ruins."
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
                "Busca na base de conhecimento por `q`. `type` opcional: procedure, glossary, "
                "guidance. Use quando a pergunta pede explicação, procedimento ou definição."
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
                "Reprocessa uma análise. Exige action_low. Use quando o insight está desatualizado "
                "ou não foi emitido por atraso do modelo — não por insatisfação genérica."
            ),
        ),
        StructuredTool.from_function(
            request_specialist_analysis,
            name="request_specialist_analysis",
            description=(
                "Solicita análise de especialista Tractian sobre a análise indicada. Exige "
                "action_low. É ação técnica interna ('agir'), NÃO é escalar para campo."
            ),
        ),
        StructuredTool.from_function(
            request_retraining,
            name="request_retraining",
            description=(
                "Solicita retreinamento do modelo. ALTO impacto: exige action_high e evidência de "
                "erro sistemático do modelo, não uma discordância pontual."
            ),
        ),
        StructuredTool.from_function(
            update_asset_config,
            name="update_asset_config",
            description=(
                "Altera config técnica ou criticidade do ativo. ALTO impacto: exige action_high. "
                "`changes` aceita {'criticality': low|medium|high|critical} e/ou {'config': {...}}."
            ),
        ),
        StructuredTool.from_function(
            escalate_case,
            name="escalate_case",
            description=(
                "Encaminha ESTE caso para análise humana. Exige permissão escalate. Use só quando o "
                "caso extrapola o remoto (ex.: intervenção física). Escalar demais é erro."
            ),
        ),
    ]
