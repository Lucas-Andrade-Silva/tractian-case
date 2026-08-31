"""Estado compartilhado do grafo e os contratos estruturados entre papéis.

`Route` e `Decision` são saídas estruturadas de LLM (não texto livre) porque delas
dependem transições do grafo: a rota do Supervisor e — principalmente — a transição
fixa Decisor → Executor, que só pode ocorrer sobre uma decisão formal (ADR 0002).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Role = Literal["investigador", "contextualizador", "decisor"]
DecisionKind = Literal["orientar", "agir", "escalar"]


class Route(BaseModel):
    """Escolha do Supervisor sobre qual papel deve agir em seguida."""

    next: Role = Field(
        description=(
            "Próximo papel. 'investigador' para apurar evidência técnica (sensor, análise, "
            "baseline, modelo); 'contextualizador' para buscar procedimento, glossário ou "
            "orientação documental; 'decisor' quando a evidência já basta para resolver o caso."
        )
    )
    reason: str = Field(description="Por que este papel agora, em uma frase, citando o que falta ou o que já se sabe.")


class Decision(BaseModel):
    """Resolução formal do caso pelo Decisor. Única porta de entrada para o Executor."""

    decision: DecisionKind = Field(
        description=(
            "'orientar' = explicar sem alterar nada na plataforma; 'agir' = executar ação "
            "justificada (reprocessar, solicitar especialista, retreinar, alterar config); "
            "'escalar' = encaminhar para análise humana porque extrapola o suporte remoto."
        )
    )
    justification: str = Field(
        description=(
            "Justificativa fundamentada na evidência apurada, com no mínimo 20 caracteres. "
            "Vai junto com a ação na plataforma e é validada pela API."
        )
    )
    intended_action: str | None = Field(
        default=None,
        description=(
            "Se decision for 'agir' ou 'escalar': qual ação executar e sobre qual recurso "
            "(ex.: 'reprocessar a análise an_9901'). Nulo quando decision for 'orientar'."
        ),
    )
    answer: str = Field(
        description=(
            "Resposta ao cliente, em português, citando a evidência que sustenta a conclusão e "
            "sendo explícita sobre o que não pôde ser determinado."
        )
    )


class CaseState(TypedDict, total=False):
    """Estado que atravessa o grafo durante o atendimento de um caso.

    A separação entre `scratch` e `findings` é o que mantém o custo de contexto sob
    controle. O transcrito bruto de tool calls (`scratch`) pertence ao papel que está
    trabalhando e é descartado quando o Supervisor troca de papel; o que atravessa
    fronteiras é o resumo (`findings`). Compartilhar o transcrito entre todos os papéis
    faria cada chamada carregar o trabalho de todos os anteriores — crescimento que
    estoura o limite de tokens por requisição e ainda dilui o que importa.
    """

    case: dict[str, Any]
    # Contexto de autorização, estabelecido uma única vez pelo Supervisor.
    user_context: dict[str, Any] | None
    # Janela de trabalho do papel atual: suas próprias tool calls e observações.
    scratch: Annotated[list[AnyMessage], add_messages]
    # Resumo que cada worker deixa ao encerrar sua apuração — o que atravessa papéis.
    findings: list[str]
    next_role: str | None
    # Papel que ocupou o scratch por último, para saber quando limpá-lo.
    scratch_owner: str | None
    decision: dict[str, Any] | None
    final_answer: str | None
    supervisor_turns: int
    worker_steps: int
    stop_reason: str | None
