# Roteamento híbrido: LLM entre investigação, transição fixa para o Executor

O Supervisor precisa decidir, a cada turno, para qual agente rotear. Uma opção seria delegar 100% ao
LLM (flexível, mas cada rota custa uma chamada extra e um erro de roteamento poderia, em tese, pular
a etapa de decisão formal e ir direto para uma ação de impacto). A outra seria uma máquina de estados
fixa em código (previsível e barata, mas os 16 cenários não seguem uma sequência única entre
Investigador e Contextualizador — forçar uma ordem fixa exigiria tantas condicionais que
reimplementaria um classificador de intenção à mão).

Decidimos por um modelo híbrido: o **LLM decide dinamicamente** o roteamento entre Investigador e
Contextualizador, e quando considerar que já há evidência suficiente para parar de investigar (isso
é comportamento que os cenários de over-escalation avaliam, então não pode ser fixo). Mas a
**transição Decisor → Executor é fixa por código**: só ocorre quando o Decisor formalmente concluiu
"agir" ou "escalar" — nunca por decisão do roteador.

Essa segunda parte é a peça não-óbvia: existe para garantir, estruturalmente e não por disciplina de
prompt, que uma ação de impacto na plataforma industrial jamais aconteça sem ter passado pela decisão
formal e auditável do Decisor.
