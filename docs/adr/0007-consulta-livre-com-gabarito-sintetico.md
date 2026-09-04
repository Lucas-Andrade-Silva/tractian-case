# Consulta de texto livre avaliada por gabarito sintético, em métrica separada

O sistema foi construído para um conjunto fechado: 17 casos pré-escritos em
`agent-input/cases.json`, cada um com trajetória de referência em `eval/expected-paths.json`. Falta
a porta de entrada que o contexto de uso real pressupõe — alguém da plataforma descrevendo com as
próprias palavras o que observou no equipamento, sem que ninguém tenha escrito um gabarito para
aquilo antes.

O obstáculo não é receber o texto. É que **as três camadas de avaliação (ADR 0005) dependem de
gabarito**, e um caso digitado na hora não tem nenhum:

- A camada 1 compara `path_taken` com `expected_path`. Sem trajetória de referência,
  `expected_path=[]` faria `recall = 1.0` sobre conjunto vazio e `_decision_from_trajectory()`
  derivaria `"orientar"` como resolução esperada — reprovando qualquer agente que agisse ou
  escalasse, e produzindo um número que *parece* excelente sem significar nada.
- A camada 2 exige `GoldenCase` na assinatura de `run_committee`, e a rubrica de causa-raiz é
  comparativa por construção: "comparada com a questão de referência do gabarito".

## Decisão

Uma camada **2-S** (sintética), com quatro restrições que a mantêm defensável.

**1. O gabarito é gerado por LLM, antes da execução.** `runner/sintetico.py` extrai da mensagem do
usuário uma `root_question`, um `mode` e o conjunto de `accepted_decisions`. A ordem é a
salvaguarda central: gerar depois faria o gerador ver a resposta do agente e descrever como
"esperado" exatamente o que o agente fez, tornando o julgamento uma tautologia. Como gerador e
agente são ambos LLMs, nada além da ordem impede isso.

**2. Modelo gerador ≠ modelo juiz, verificado em código.** `assert_modelos_distintos` levanta
`ModelosIndistintos` antes de qualquer chamada. Um juiz avaliando contra gabarito escrito por ele
mesmo mede auto-consistência, não acurácia — e a nota resultante é indistinguível de uma nota válida
quando chega ao painel. Por isso a verificação falha alto e cedo em vez de degradar em silêncio, e
por isso `GERADOR_*` é um bloco de configuração separado de `JUDGE_*`.

**3. A camada 1 é pulada, não adaptada.** O que dela sobrevive sem gabarito é apurado direto do
trace por `metricas_execucao`: se a execução concluiu, quantas chamadas foram repetidas, se o agente
insistiu numa chamada já recusada com 403. São propriedades do próprio trace — uma chamada idêntica
repetida é desperdício independentemente do que o gabarito dissesse. O que dependia de comparação
fica explicitamente `null`, com o motivo registrado no próprio JSON.

**4. Métrica separada, isolada por construção.** Consultas gravam em
`evaluation/results/consultas/`. `cli.py` lê `results/traces/<suite>/` e `build_bundle.py` varre
`.run/traces_*/` — nenhum dos dois alcança esse diretório. O isolamento não depende de disciplina ao
rodar comandos: depende de caminho, e há teste que falha se ele mudar.

## Consequências

O agente **não muda**. `executa_consulta` monta o dict de caso no schema de sempre e chama
`run_case`; grafo, tools e prompts são os mesmos. Se mudassem, as medidas dos 17 cenários não
valeriam para o que a aba Consulta executa. A única alteração em `agent/` foi `_case_block`: com
`asset_id` ausente o prompt renderizava `- ativo: None` e o agente passava a adivinhar ids a partir
do texto ("conveyor_line2", "belt_line2", …), gastando uma volta de LLM por 404. Todos os 17 casos
têm `asset_id`, então o prompt deles é byte-idêntico ao anterior.

A UI **não cria usuários**: o seletor lista quem já existe em `data/users.parquet`, porque é o
`user_id` que determina a permissão efetiva na API via `x-user-id`. Um 403 na trajetória é
resultado legítimo do enforcement (ADR 0003), e a interface o apresenta como tal.

O que esta camada **não** autoriza dizer: que uma consulta livre teve desempenho comparável ao de um
cenário com gabarito. A ordenação vale dentro do conjunto sintético e nada além disso — o painel
afirma essa ressalva acima das notas, não em rodapé.

Fica em aberto a calibração. A camada 2 original já carrega o aviso de que média de juiz não
validada contra conjunto anotado por humano não é verdade; a 2-S herda esse limite e acrescenta um
segundo, o de que a própria referência é sintética. Validar exigiria anotar um conjunto de consultas
livres à mão e medir a concordância — trabalho que não foi feito e cuja ausência é declarada em vez
de contornada.
