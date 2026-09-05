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

## O Decisor não tem tools — e isso é o comportamento correto

Decorre da decisão acima, mas vale registrar porque parece dado faltando quando se olha um trace: o
Decisor é o único papel **sem `ToolNode` no grafo** e sem `bind_tools`. Ele não consulta a API; decide
sobre a evidência que os workers já apuraram e que chega pelos `findings`. Nos 77 traces da bateria,
nenhuma chamada de API tem `agent="decisor"` — supervisor, investigador, contextualizador e executor
respondem por todas.

São duas razões, e a segunda é consequência mensurável da primeira:

1. **Separação de papéis.** Decidir sobre evidência é diferente de apurar evidência. Se o Decisor
   pudesse consultar, ele reabriria a investigação a cada dúvida e a fronteira entre "o que foi
   apurado" e "o que foi decidido" deixaria de existir — justamente a fronteira que a avaliação
   inspeciona quando compara `findings` com a justificativa.

2. **Custo.** Papel com tools entra em laço: chama, recebe, reavalia, chama de novo — e cada volta
   reenvia prompt e schemas inteiros. Sem tools não há laço, e o Decisor gasta **exatamente uma
   chamada de LLM por execução**. Medido na bateria de 77 execuções:

   | papel | chamadas de LLM | por execução |
   | :--- | ---: | ---: |
   | investigador | 180 | 2,3 |
   | contextualizador | 173 | 2,2 |
   | supervisor | 197 | 2,6 |
   | **decisor** | **77** | **1,0** |
   | executor | 55 | 0,7 |

   O Decisor usa o modelo mais capaz da configuração — é a saída que a avaliação de fato julga — e é
   justamente onde o custo por chamada mais pesaria. Não ter laço é o que torna essa escolha barata.

O painel exibe isso como legenda na timeline, e não como lacuna: a ausência da faixa do Decisor é
arquitetura funcionando, não instrumentação incompleta.
