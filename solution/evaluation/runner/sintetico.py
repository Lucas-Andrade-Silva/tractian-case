"""Gabarito sintético para consultas de texto livre (camada 2-S).

## Por que este módulo existe separado de `golden.py`

`golden.py` carrega o gabarito da Tractian — trajetórias e questões de referência
escritas por humanos a partir de `docs/test-scenarios.md`. Uma consulta digitada por um
usuário na hora não tem nada disso: não há `root_question` revisada, não há
`expected_path`, não há resolução declarada. O comitê de juízes, porém, exige um
`GoldenCase` (`judges.run_committee`), e a rubrica de causa-raiz é comparativa por
construção ("comparada com a questão de referência do gabarito").

A saída aqui é um `GoldenCase` gerado por LLM a partir da mensagem do usuário — o que
torna o julgamento possível, mas com um estatuto epistêmico diferente do gabarito real.
Duas regras protegem essa diferença, e nenhuma das duas é opcional:

1. **Modelo gerador != modelo juiz.** Se o mesmo modelo escreve o gabarito e julga a
   resposta contra ele, o julgamento não mede acurácia: mede consistência do modelo
   consigo mesmo. `assert_modelos_distintos` levanta erro em vez de degradar em silêncio,
   porque uma nota produzida nessas condições parece válida e não é.

2. **Métrica separada, nunca agregada.** O `GoldenCase` sintético nasce com
   `expected_path` vazio, o que faria a camada 1 calcular `recall = 1.0` sobre conjunto
   vazio e derivar `"orientar"` como resolução esperada — número que parece bom e não
   significa nada. Por isso `origem="sintetico"` e a camada 1 é explicitamente pulada;
   quem agrega mantém estes casos numa seção própria.

O gabarito sintético serve para ordenar respostas entre si dentro do conjunto sintético.
Não é comparável com as notas dos 17 cenários com gabarito real, e o painel diz isso.
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

# Modos do envelope probabilístico da API industrial. O gerador escolhe entre eles para
# descrever o cenário de dados que a pergunta pressupõe.
MODOS_VALIDOS = ("complete", "partial", "inconclusive", "conflict", "unavailable")

RESOLUCOES_VALIDAS = ("orientar", "agir", "escalar")


class ModelosIndistintos(RuntimeError):
    """Gerador e juiz usam o mesmo modelo — o julgamento não teria validade."""


class ExpectativaSintetica(BaseModel):
    """O que o gerador extrai da mensagem livre, antes de qualquer execução do agente."""

    root_question: str = Field(
        description=(
            "A pergunta técnica de fundo, reescrita em uma frase objetiva. NÃO é um "
            "resumo da mensagem: é o que precisa ser determinado para respondê-la."
        )
    )
    mode: str = Field(
        description=(
            "Cenário de dados que a pergunta pressupõe, um de: "
            "complete, partial, inconclusive, conflict, unavailable."
        )
    )
    accepted_decisions: list[str] = Field(
        description=(
            "Resoluções aceitáveis para este caso: orientar, agir e/ou escalar. "
            "Liste MAIS DE UMA quando o caso admitir mais de um desfecho defensável."
        )
    )
    rationale: str = Field(
        description="Por que essas resoluções são aceitáveis, em 1 a 2 frases."
    )


_SISTEMA = """\
Você define o gabarito de avaliação de um caso de suporte industrial, ANTES de ver \
qualquer resposta de agente. Trabalhe apenas com a mensagem do usuário e o contexto do \
ativo informado.

Regras:
- A `root_question` é a questão técnica de fundo, não um resumo da mensagem.
- Escolha o `mode` que a pergunta pressupõe sobre a qualidade do dado disponível.
- Em `accepted_decisions`, liste TODAS as resoluções defensáveis, não só a mais \
provável. Um caso que admite orientar e escalar deve trazer as duas: punir a escolha \
entre desfechos igualmente válidos é erro de avaliação, não rigor.
- `agir` exige que exista ação concreta na plataforma que resolva o problema; `escalar` \
cabe quando a resolução depende de intervenção humana ou física; `orientar` cabe quando \
a resposta é informação suficiente.

Não presuma qual será a resposta do agente. Você está descrevendo o que o caso pede."""


@dataclass(frozen=True)
class GabaritoSintetico:
    """Um `GoldenCase` gerado por LLM, com a procedência que o torna auditável."""

    golden: GoldenCase
    modelo_gerador: str
    provedor_gerador: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.golden.case_id,
            "root_question": self.golden.root_question,
            "mode": self.golden.mode,
            "accepted_decisions": sorted(self.golden.accepted_decisions),
            "rationale": self.rationale,
            "modelo_gerador": self.modelo_gerador,
            "provedor_gerador": self.provedor_gerador,
            "origem": "sintetico",
        }


def gerador_settings() -> Settings:
    """Configuração do gerador de gabarito: `GERADOR_*`, caindo no LLM do agente.

    Separado de `judge_settings()` de propósito — são dois papéis que precisam poder
    apontar para modelos diferentes, e é essa separação que `assert_modelos_distintos`
    verifica.
    """
    base = load_settings()
    return Settings(
        api_base_url=base.api_base_url,
        llm_provider=os.getenv("GERADOR_PROVIDER") or base.llm_provider,
        llm_model=os.getenv("GERADOR_MODEL") or base.llm_model,
        llm_api_key=os.getenv("GERADOR_API_KEY") or base.llm_api_key,
        llm_temperature=0.0,  # gabarito é referência: não pode variar entre execuções
        agent_port=base.agent_port,
        request_timeout_s=base.request_timeout_s,
        max_supervisor_turns=base.max_supervisor_turns,
        max_worker_steps=base.max_worker_steps,
    )


def assert_modelos_distintos(gerador: Settings, juiz: Settings) -> None:
    """Impede que o mesmo modelo escreva o gabarito e julgue contra ele.

    Falha alto e cedo: uma nota gerada nessas condições é indistinguível de uma nota
    válida quando chega ao painel, então o erro tem de acontecer antes da chamada.
    """
    if not (gerador.llm_model or "").strip():
        raise ModelosIndistintos(
            "Modelo do gerador não definido. Defina GERADOR_MODEL em agent/.env."
        )
    if not (juiz.llm_model or "").strip():
        raise ModelosIndistintos(
            "Modelo do juiz não definido. Defina JUDGE_MODEL em agent/.env."
        )
    mesmo_modelo = gerador.llm_model.strip().lower() == juiz.llm_model.strip().lower()
    mesmo_provedor = (gerador.llm_provider or "").strip().lower() == (
        juiz.llm_provider or ""
    ).strip().lower()
    if mesmo_modelo and mesmo_provedor:
        raise ModelosIndistintos(
            f"Gerador e juiz usam o mesmo modelo ({gerador.llm_model} em "
            f"{gerador.llm_provider}). O juiz avaliaria a resposta contra um gabarito "
            "escrito por ele mesmo, o que mede auto-consistência e não acurácia. "
            "Defina GERADOR_MODEL diferente de JUDGE_MODEL em agent/.env."
        )


def gera_gabarito(
    case: dict[str, Any],
    *,
    contexto_ativo: dict[str, Any] | None = None,
    settings: Settings | None = None,
    llm: Any = None,
) -> GabaritoSintetico:
    """Gera o gabarito de um caso de texto livre, antes de o agente rodar.

    `contexto_ativo` é o que a UI já sabe do ativo escolhido (nome, tipo, criticidade) —
    o gerador não chama a API, para que o gabarito dependa só do que o usuário informou.
    """
    settings = settings or gerador_settings()
    llm = llm or build_llm(settings)

    resultado: ExpectativaSintetica = llm.with_structured_output(
        ExpectativaSintetica
    ).invoke(
        [
            SystemMessage(_SISTEMA),
            HumanMessage(_bloco_caso(case, contexto_ativo)),
        ]
    )

    return GabaritoSintetico(
        golden=GoldenCase(
            case_id=case["id"],
            ticket_id=case.get("ticket_id", ""),
            root_question=resultado.root_question.strip(),
            mode=_modo_valido(resultado.mode),
            # Vazio de propósito: não há trajetória de referência para um caso novo, e
            # inventar uma faria a camada 1 medir contra ficção. Ver docstring do módulo.
            expected_path=[],
            expected_notes={},
            declared_decisions=_decisoes_validas(resultado.accepted_decisions),
            facet="consulta_livre",
        ),
        modelo_gerador=settings.llm_model,
        provedor_gerador=settings.llm_provider,
        rationale=resultado.rationale.strip(),
    )


def _modo_valido(bruto: str) -> str:
    """Normaliza o modo; desconhecido vira `complete`, o mais conservador."""
    limpo = (bruto or "").strip().lower()
    return limpo if limpo in MODOS_VALIDOS else "complete"


def _decisoes_validas(brutas: list[str]) -> frozenset[str]:
    """Filtra as resoluções para o enum real.

    Vazio cai nas três: sem informação sobre o que o caso aceita, a avaliação não deve
    punir nenhum desfecho.
    """
    limpas = {
        d.strip().lower()
        for d in (brutas or [])
        if d.strip().lower() in RESOLUCOES_VALIDAS
    }
    return frozenset(limpas) if limpas else frozenset(RESOLUCOES_VALIDAS)


def _bloco_caso(case: dict[str, Any], contexto_ativo: dict[str, Any] | None) -> str:
    ativo = contexto_ativo or {}
    linhas = [
        f"MENSAGEM DO USUÁRIO:\n{case.get('message', '')}",
        "",
        f"EMPRESA: {case.get('company_id') or 'não informada'}",
        f"ATIVO: {case.get('asset_id') or 'não informado'}",
    ]
    if ativo:
        detalhe = ", ".join(
            f"{chave}={valor}"
            for chave, valor in ativo.items()
            if valor not in (None, "", [], {})
        )
        if detalhe:
            linhas.append(f"CONTEXTO DO ATIVO: {detalhe}")
    return "\n".join(linhas)
