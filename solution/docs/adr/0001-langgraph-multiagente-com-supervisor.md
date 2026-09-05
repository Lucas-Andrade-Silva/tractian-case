# LangGraph multiagente com supervisor, em vez de agente único

O agente de suporte precisa investigar solicitações, buscar conhecimento documental, decidir entre
orientar/agir/escalar e executar ações — nenhum dos 16 cenários exige explicitamente múltiplos
agentes especializados (cada um é "uma solicitação → uma investigação → uma decisão final"), o que
tornaria um agente único com loop ReAct simples suficiente e mais barato de construir num prazo de 1
mês.

Decidimos, ainda assim, por uma arquitetura **multiagente com supervisor** em LangGraph: um
Supervisor roteia entre Investigador (consultas técnicas), Contextualizador (busca em knowledge
base), Decisor (pesa evidência e decide orientar/agir/escalar, sem tools) e Executor (ações de
impacto). Essa divisão foi uma escolha deliberada de explorar separação de responsabilidades como
parte do próprio experimento do projeto, não uma necessidade estrutural dos cenários.

**Consequência aceita**: mais superfície de instrumentação (o trace precisa capturar qual agente fez
qual chamada, não só a chamada) e mais complexidade de implementação do que um agente único
justificaria pelos cenários sozinhos.

## Considered Options

- **Servidor MCP**: descartado — o agente é o único consumidor da integração (projeto individual),
  então a padronização multi-client que o MCP oferece não se paga aqui.
- **Agente único com loop ReAct manual ou Pydantic AI**: era a opção mais simples e proporcional ao
  escopo dos 16 cenários; descartada em favor da divisão multiagente por escolha deliberada de
  design, não por exigência do domínio.
