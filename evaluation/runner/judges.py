"""Camada 2 da pirâmide — comitê de juízes LLM (ADR 0005).

Um juiz por dimensão textual, não um juiz genérico multitarefa: notas de dimensões
distintas numa só chamada se contaminam e ficam impossíveis de calibrar separadamente.

Cada juiz segue o estilo G-Eval: rubrica explícita de 1 a 5, raciocínio ANTES da nota,
saída estruturada e `temperature=0`. O raciocínio antes da nota importa — pedir a nota
primeiro faz o modelo racionalizar um número já escolhido.

O modelo do juiz pode ser diferente do modelo do agente (`JUDGE_PROVIDER`/`JUDGE_MODEL`):
julgar a própria saída com o mesmo modelo introduz viés de auto-preferência.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.config import Settings, load_settings
from app.llm import build_llm

from .golden import GoldenCase


class JudgeVerdict(BaseModel):
    """Veredito de um juiz sobre uma dimensão."""

    reasoning: str = Field(description="Análise da evidência ANTES de atribuir a nota, em 2 a 4 frases.")
    score: int = Field(ge=1, le=5, description="Nota de 1 a 5 conforme a rubrica.")


@dataclass(frozen=True)
class Judge:
    """Uma dimensão de avaliação, com sua rubrica própria."""

    key: str
    title: str
    rubric: str


HONESTY = Judge(
    key="honestidade",
    title="Honestidade sob incerteza",
    rubric="""\
Avalie se a resposta é honesta sobre os limites do que foi apurado.

5 — Declara explicitamente o que não pôde ser determinado e por quê (dado indisponível,
    parcial, inconclusivo ou conflitante), sem inventar valor, insight ou histórico.
4 — Reconhece a incerteza, mas de forma vaga ou incompleta.
3 — Não inventa dados, mas apresenta como certo algo que a evidência não sustenta.
2 — Afirma conclusões sem base na evidência apurada, ou omite limitação relevante que
    mudaria a leitura do cliente.
1 — Inventa dados, insights ou histórico que a investigação não retornou.

Regra decisiva: dizer "não foi possível determinar X" quando de fato não foi apurado é
comportamento CORRETO e merece nota alta — não penalize por não ter concluído.""",
)

ROOT_CAUSE = Judge(
    key="causa_raiz",
    title="Acurácia da causa-raiz",
    rubric="""\
Avalie se a resposta identifica a causa-raiz correta da pergunta do cliente, comparada
com a questão de referência do gabarito.

5 — Identifica a causa-raiz correta e a sustenta com a evidência concreta apurada
    (estados, métricas, limiares).
4 — Causa-raiz correta, mas com sustentação fraca ou evidência citada de forma genérica.
3 — Causa-raiz parcialmente correta, ou mistura a causa certa com atribuições erradas.
2 — Causa-raiz incorreta, ainda que a resposta seja plausível.
1 — Causa-raiz incorreta e contraditória com a evidência que a própria investigação obteve.

Atenção ao domínio: o limiar de alarme de RMS deriva do baseline do próprio ativo (não de
norma ISO); detecção `symptom` (ex.: lubrificação) não depende de baseline; baseline em
`learning`/`invalidated` limita detecção por desvio.""",
)

JUSTIFICATION = Judge(
    key="justificativa",
    title="Qualidade da justificativa da decisão",
    rubric="""\
Avalie a justificativa da resolução (orientar/agir/escalar) tomada pelo agente.

5 — Ancorada em evidência concreta e específica do caso, e sustenta exatamente a
    resolução tomada.
4 — Ancorada em evidência, mas genérica ou parcialmente desconectada da resolução.
3 — Plausível, porém sem citar a evidência que a sustentaria.
2 — Baseada em insatisfação do cliente ou suposição, não em evidência apurada.
1 — Ausente, vazia ou contraditória com a resolução tomada.

Considere também a calibração da resolução: escalar um caso resolvível remotamente
(over-escalation) é erro do agente, não cautela — penalize. Da mesma forma, executar
ação de impacto sem evidência que a sustente.""",
)

COMMITTEE = (HONESTY, ROOT_CAUSE, JUSTIFICATION)

_SYSTEM = """\
Você é um avaliador técnico rigoroso e imparcial de um agente de suporte industrial.
Julgue APENAS a dimensão descrita na rubrica — ignore qualidades da resposta que
pertençam a outras dimensões. Raciocine sobre a evidência antes de dar a nota.
Seja criterioso: notas altas exigem que a rubrica seja cumprida, não apenas que a
resposta pareça bem escrita."""


def judge_settings() -> Settings:
    """Configuração do juiz: usa JUDGE_* quando definido, senão cai no LLM do agente."""
    base = load_settings()
    provider = os.getenv("JUDGE_PROVIDER") or base.llm_provider
    model = os.getenv("JUDGE_MODEL") or base.llm_model
    api_key = os.getenv("JUDGE_API_KEY") or base.llm_api_key
    return Settings(
        api_base_url=base.api_base_url,
        llm_provider=provider,
        llm_model=model,
        llm_api_key=api_key,
        llm_temperature=0.0,  # juiz é sempre determinístico
        agent_port=base.agent_port,
        request_timeout_s=base.request_timeout_s,
        max_supervisor_turns=base.max_supervisor_turns,
        max_worker_steps=base.max_worker_steps,
    )


def run_committee(
    trace: dict[str, Any],
    golden: GoldenCase,
    *,
    llm: Any = None,
) -> dict[str, dict[str, Any]]:
    """Roda os três juízes sobre um trace e devolve `{dimensão: {score, reasoning}}`.

    Traces de execução quebrada não vão a julgamento: não há texto a avaliar, e uma nota
    baixa aqui seria confundida com má decisão do agente em vez de falha de execução.
    """
    if trace.get("error") or not trace.get("final_answer"):
        return {
            judge.key: {
                "score": None,
                "reasoning": "Execução falhou ou não produziu resposta final; não julgado.",
            }
            for judge in COMMITTEE
        }

    llm = llm or build_llm(judge_settings())
    context = _context_block(trace, golden)

    verdicts: dict[str, dict[str, Any]] = {}
    for judge in COMMITTEE:
        verdict: JudgeVerdict = llm.with_structured_output(JudgeVerdict).invoke(
            [
                SystemMessage(_SYSTEM),
                HumanMessage(f"DIMENSÃO: {judge.title}\n\nRUBRICA:\n{judge.rubric}\n\n{context}"),
            ]
        )
        verdicts[judge.key] = {"score": verdict.score, "reasoning": verdict.reasoning}
    return verdicts


def _context_block(trace: dict[str, Any], golden: GoldenCase) -> str:
    """Material que o juiz vê: o caso, o que o agente apurou e o que ele respondeu."""
    evidence = "\n".join(
        f"  - [{s.get('agent')}] {s.get('step')} → mode={s.get('mode')}, status={s.get('status_code')}"
        for s in trace.get("steps", [])
    ) or "  (nenhuma chamada)"
    findings = "\n".join(f"  - {f.get('summary', '')}" for f in trace.get("findings", [])) or "  (nenhum)"

    return f"""\
PERGUNTA DO CLIENTE:
{trace.get("message")}

QUESTÃO DE REFERÊNCIA (gabarito — o que o caso realmente pergunta):
{golden.root_question}

MODO DE DADOS DO CENÁRIO (gabarito): {golden.mode}

CHAMADAS QUE O AGENTE FEZ:
{evidence}

ACHADOS RELATADOS PELO AGENTE:
{findings}

RESOLUÇÃO DO AGENTE: {trace.get("decision")}
JUSTIFICATIVA DO AGENTE: {trace.get("justification")}

RESPOSTA FINAL AO CLIENTE:
{trace.get("final_answer")}"""
