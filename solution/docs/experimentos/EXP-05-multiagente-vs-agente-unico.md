# EXP-05 — Multiagente vs. agente único

**Estado:** ⏳ **braço de controle implementado e testado; bateria pendente de cota** ·
**Registrado em:** 2026-09-04

> Este é o experimento da hipótese central do projeto, declarada em `SOLUTION.md` desde o
> início e **nunca testada** — porque o braço de comparação não existia. Ele agora existe.
> O que falta é rodar, e o que impede é cota de LLM, não código.

## 1. Hipótese

> Separar investigação de decisão — o Decisor não tem tools e só recebe evidência já
> apurada — **reduz ações de impacto sem fundamento** e **reduz over-escalation**, ao custo
> de mais chamadas de LLM por caso.

A hipótese tem três predições, e a terceira é a que a torna honesta (prevê um custo, não só
benefícios):

| | Predição | Métrica |
| :--- | :--- | :--- |
| **P1** | o multiagente executa menos ações não previstas | `unexpected_actions` |
| **P2** | o multiagente escala menos quando escalar não era a resolução aceita | decisões `escalar` fora do conjunto aceito |
| **P3** | o multiagente custa mais chamadas de LLM por caso | chamadas de LLM por execução |

O mecanismo alegado para P1 é estrutural, não estatístico: no multiagente a transição
Decisor → Executor é **fixa em código** ([ADR 0002](../adr/0002-roteamento-hibrido-transicao-fixa-para-executor.md)),
logo nenhuma ação de impacto ocorre sem uma decisão formal antes. No agente único essa
garantia **não existe** — o mesmo papel que investiga também age, e pode agir no meio da
investigação. Se P1 falhar, a ADR 0002 perde a justificativa empírica e passa a ser só uma
preferência de desenho.

## 2. Método

**Braços.** Mesma API, mesmos casos, mesmas seeds, mesmo modelo. A única variável é a
arquitetura, selecionada por `AGENT_ARCHITECTURE` no `.env`:

| Braço | Arquitetura | Implementação |
| :--- | :--- | :--- |
| tratamento | multiagente (supervisor + 2 workers + decisor + executor) | [`agent/app/graph.py`](../../agent/app/graph.py) |
| **controle** | **agente único, todas as tools na mão** | [`agent/app/single_graph.py`](../../agent/app/single_graph.py) |

**O que foi mantido igual, de propósito.** O braço de controle reusa as *mesmas peças* —
não uma reescrita:

- as mesmas tools, das mesmas fábricas de `tools.py`;
- o mesmo `DOMAIN_BRIEF` e a **mesma `_DECISION_POLICY`**, montados em
  `single_agent_prompt()` a partir das mesmas constantes. Se o prompt do controle
  reescrevesse a política com outras palavras, o experimento mediria redação, não arquitetura;
- o mesmo schema `Decision`, o mesmo formato de trace, a mesma camada 1 de avaliação;
- orçamento equivalente: `max_worker_steps × 2`, que é o que os dois workers do multiagente
  poderiam gastar somados.

**O que muda, e é o objeto da medição:** sem Supervisor (o próprio agente escolhe a tool),
sem fronteira entre papéis (um único transcrito, sem `findings` atravessando), e **sem a
transição fixa Decisor → Executor**.

**Desenho.** Pareado por `(caso, seed)` contra as 51 execuções já existentes da fase
`pos-correcao`: 17 casos × 3 seeds. O braço multiagente **não será reexecutado** — já existe
com a mesma configuração de modelos, e rodá-lo de novo só gastaria cota.

**Critério de sucesso, fixado ANTES de rodar** (ao contrário de [EXP-01](EXP-01-politica-de-decisao.md)):
a hipótese se sustenta se o multiagente tiver **menos execuções com `unexpected_actions`**
(P1) e **menos over-escalation** (P2). Se as duas empatarem, a separação de papéis não se
justifica pelos seus próprios termos, e a conclusão honesta é que ela custa sem comprar —
resultado que este documento se compromete a registrar como refutação.

## 3. Execução

```bash
make up
make exp05-listar        # o que falta rodar
make exp05 N=3           # roda 3 execuções (cota curta)
make exp05               # roda tudo o que falta
make exp05-comparar      # comparação pareada
```

O runner ([`painel/rodar_exp05.py`](../../painel/rodar_exp05.py)) é **retomável**: grava cada
execução assim que termina e nunca refaz o que já está salvo. Bater na cota no meio não perde
o trabalho anterior — foi exatamente assim que a bateria original ficou pela metade. Ele
também força `AGENT_ARCHITECTURE=single` em vez de confiar no `.env`, para que um `.env`
esquecido em `multi` não produza silenciosamente 51 execuções do braço errado.

### 3.1 Estado atual

| Item | Estado |
| :--- | :--- |
| Grafo de agente único | ✅ implementado |
| Testes de cabeamento | ✅ 4 passando (`agent/tests/test_single_graph.py`) |
| Suíte completa do agente | ✅ 33 passando, sem regressão |
| Runner pareado + comparação | ✅ implementado |
| **Bateria (51 execuções)** | ⏳ **0/51 — bloqueada por cota** |

### 3.2 Dois defeitos encontrados ao implementar o braço de controle

Registrados porque são achados do experimento, não detalhes de implementação — e porque
ambos só aparecem na arquitetura de agente único:

1. **Transcrito com tool calls numa chamada sem tools.** A chamada final que formaliza a
   `Decision` não vincula tools (a saída é estruturada). Passar o transcrito da investigação
   nela faz o provedor **recusar a requisição inteira**: `attempted to call tool 'get_asset'
   which was not in request.tools`. Corrigido passando os `findings` em vez do transcrito —
   que é, não por acaso, exatamente o que o Decisor do multiagente já recebia.
2. **O mesmo problema no estouro de orçamento.** O multiagente força o encerramento chamando
   o worker *sem* tools, e ali funciona porque o scratch daquele papel é descartado junto. No
   agente único o transcrito permanece, então desvincular as tools quebraria pelo mesmo motivo.
   A parada passou a ser instrução explícita **mais um teto duro no roteamento** — política de
   parada no grafo, não só no prompt.

Ambos reforçam, de forma não planejada, o argumento da separação de papéis: a fronteira entre
papéis do multiagente é também o que mantém cada chamada de LLM com um contexto coerente.

## 4. Resultados

**Ainda não há resultados.** Nenhuma das 51 execuções do braço de controle foi concluída.

As duas tentativas de execução real terminaram em `RateLimitError` da Groq (429, TPM
excedido) — o mesmo limite que interrompeu a bateria original. As tentativas confirmaram que
o grafo **funciona de ponta a ponta** até o limite de cota: consultou `GET /users/me`,
`GET /assets/asset_M101`, `/baseline`, `/data-quality` e a base de conhecimento antes de
esbarrar no teto.

Um sinal qualitativo, ainda não quantificável com n=2: nas duas tentativas o agente único
**repetiu buscas de conhecimento quase idênticas** (`troca de rolamento motor procedimento
torque` reformulada três vezes) — comportamento que a instrução anti-reformulação do
Contextualizador existe para evitar no multiagente. Se isso persistir na bateria, aparecerá
como `repetition_rate` mais alta no braço de controle. **Não é resultado**; é hipótese
secundária a verificar.

## 5. Limitações

Declaradas **antes** de rodar, para que não sejam escolhidas depois em função do resultado:

1. **Uma arquitetura de controle entre muitas.** "Agente único" aqui é uma escolha concreta:
   todas as tools, um transcrito, decisão estruturada ao final. Um agente único com prompt
   diferente, ou com auto-crítica antes de agir, poderia ir melhor. O experimento compara
   **esta** implementação, não a classe inteira.
2. **O controle herda o modelo mais capaz.** Quando há modelo por papel, o braço único usa o
   do `decisor` (`gpt-oss-120b`), o mais forte da configuração — dar-lhe o modelo fraco
   tornaria a comparação injusta. Em compensação, o braço único **não** se beneficia da
   distribuição de cota entre pools de modelos diferentes, o que na prática o torna mais
   sujeito a 429.
3. **n = 51 pares, 17 casos.** As três seeds do mesmo caso não são independentes; o n efetivo
   está mais perto de 17. Com poucas discordâncias esperadas em `unexpected_actions`, o
   experimento provavelmente **não terá poder estatístico** para significância — vai
   descrever uma diferença, não prová-la. Um McNemar exato será reportado, mesmo se der
   não-significativo.
4. **A camada 2 não entra.** Sem juízes, a comparação não diz qual braço **responde melhor**,
   só qual decide e age melhor pelos critérios da camada 1. É plausível que o agente único
   escreva respostas igualmente boas com metade das chamadas.
5. **Custo medido em chamadas e tokens.** O recurso escasso real neste projeto é a cota por
   minuto, e o multiagente a distribui entre modelos — vantagem operacional que P3 não captura.
6. **Gabarito como fonte de verdade,** com os mesmos artefatos anotados em EXP-01: em vários
   casos o gabarito estruturado não documenta um POST que o cenário narrativo prescreve.
   Isso afeta os dois braços igualmente, mas infla `unexpected_actions` em ambos.

## 6. O que falta

Rodar `make exp05` até completar 51/51 e escrever a seção 4. A comparação já está
implementada: `make exp05-comparar` imprime a tabela pareada, as discordâncias caso a caso e
as contagens de ação indevida e faltante.
