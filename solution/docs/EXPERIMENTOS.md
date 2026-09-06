# Experimentos

Sete experimentos, no formato **hipótese → método → resultado → limitações**. Cada um diz o que
prova e o que não prova. Onde a hipótese foi escrita *depois* dos dados, está declarado no topo.

| # | Hipótese | n | Veredito |
| :--- | :--- | ---: | :--- |
| [01](#exp-01-política-de-decisão-tornar-explícito-quando-orientar-não-basta) | Nomear *quando orientar não basta* aumenta a acurácia | 51 pares | **sustentada** — 4 correções, 0 regressões (p ≈ 0,125) |
| [02](#exp-02-política-de-evidência-apurar-sempre-vs-apurar-sob-demanda) | Apurar sempre os 4 pilares decide melhor | 6 pares | **refutada** — decisão idêntica, custo maior |
| [03](#exp-03-enforcement-de-permissão-deixar-a-api-recusar) | Deixar a API recusar é honesto e seguro | 5 × 403 | **sustentada** — 5/5 e 5/5, sem controle |
| [04](#exp-04-o-decisor-sem-tools) | Decidir sem tools custa 1 chamada, constante | 102 exec. | **sustentada** — 1,00/exec., 0 chamadas de API |
| [05](#exp-05-política-de-evidência-segunda-medição) | `conditional` economiza tokens | 18 pares | **refutada** — gastou 13–25% **mais** |
| [06](#exp-06-sensibilidade-à-evidência) | A decisão vem do dado, não do enunciado | 12 (4 trios) | **sustentada** — 3/4 no primário, 0/4 no placebo |
| [07](#exp-07-enxugar-o-prompt-do-supervisor-a-economia-que-custou-decisão) | Cortar o brief reduz custo sem custar decisão | 51 pares | **refutada** — −15,5% tokens, 3 regressões |

**EXP-01 e EXP-07 são os únicos rodados sobre a bateria inteira** (51 pares cada), e contam a
mesma história em direções opostas: um comprou decisão, o outro a vendeu por custo. **Só o
EXP-06 foi pré-registrado**; cinco dos sete tiveram a hipótese escrita depois dos dados (HARKing,
declarado em cada um).

Três resultados contrariam a expectativa: o **EXP-02** refutou "investigar mais é mais seguro" —
e a produção seguiu contrariando o resultado; o **EXP-05** inverteu o sinal de custo do EXP-02; o
**EXP-07** desfez parte do EXP-01 e **é a configuração em produção hoje**.

### Sobre a numeração

Existiu um **EXP-05 — Multiagente vs. agente único**, com braço de controle implementado
(`single_graph.py`, 212 linhas) e nunca executado por falta de cota; ambos removidos no commit
`4f16fc7`. Era o teste da hipótese central de arquitetura, e sua ausência é a maior lacuna do
projeto ([ARCHITECTURE.md](ARCHITECTURE.md#6-próximos-passos-em-ordem-de-valor)). Os antigos 06 e
07 viraram **05** e **06**. Recuperável em
`git show 491abbc:solution/docs/experimentos/EXP-05-multiagente-vs-agente-unico.md`.

### Limitações comuns aos sete

- **Dados sintéticos.** 17 casos fictícios; nada demonstra generalização para operação real.
- **Um conjunto de modelos.** qwen + gpt-oss, `temperature=0`. Efeitos que dependam da capacidade
  do modelo não se separam da arquitetura.
- **Camada 2 parcial.** 35 de 204 execuções julgadas (2026-09-05), **todas de `baseline`**. Nenhum
  experimento usa qualidade textual como critério — tudo é decisão, trajetória e custo.
- **Cota de LLM moldou o desenho.** O n=6 do EXP-02 e a camada 2 parcial são consequência do plano
  gratuito, não de escolha metodológica.
- **n pequeno e não independente.** Três seeds do mesmo caso não são três observações; onde há
  taxa sobre 51 execuções, o n efetivo está mais perto de 17.

---

# EXP-01 — Política de decisão: tornar explícito *quando orientar não basta*

**Concluído** · `baseline` × `pos-correcao` · 51 pares · 2026-09-04

> Hipótese escrita **depois** da coleta (HARKing). Evidência sugestiva, não confirmatória.

> ⚠️ **O ganho de estabilidade não se reproduziu.** O
> [EXP-07](#exp-07-enxugar-o-prompt-do-supervisor-a-economia-que-custou-decisão) rodou os mesmos
> 51 pares com o prompt do Supervisor alterado e a estabilidade caiu de **17/17 para 15/17**. Os
> números abaixo valem para a configuração que mediram; o 17/17 é propriedade *daquela versão do
> prompt*, não do agente.

### Hipótese

> Tornar explícito na política **quando `orientar` não basta** — quando a evidência revela algo
> que continuará prejudicando o cliente depois que ele ler a resposta — aumenta a acurácia sem
> aumentar o custo.

Nasce de um padrão nos traces da `baseline`: o agente explicava bem e resolvia mal. A suspeita é
que `orientar` funcionava como **atrator** — explicar nunca está *errado* — e faltava critério
escrito para reconhecer quando é insuficiente.

Predição falseável: os ganhos se concentram em casos de `agir`/`escalar`, **sem perda** em casos
de `orientar`.

### Método

Três mudanças aplicadas juntas em [`prompts.py`](../agent/app/prompts.py): (1) bloco
`QUANDO ORIENTAR NÃO BASTA`, com dois gatilhos concretos e o que **não** é gatilho; (2)
reordenação *decida primeiro, redija depois*; (3) `findings` passados ao Executor.

Pareado por `(caso, seed)` — 17 × 3 = 51 pares nas duas fases. Mesmos modelos, `temperature=0`,
`evidence_policy=fixed`, mesma API local. Desfecho primário `decision_match`; secundário `passou`
(exige também nenhuma ação faltante ou indevida).

### Resultados

| Métrica (n=51) | baseline | pós-correção | Δ |
| :--- | ---: | ---: | ---: |
| `decision_match` | 44/51 (86,3%) | **48/51 (94,1%)** | +4 |
| `passou` | 39/51 | **40/51** | +1 |
| tokens (média) | 19.514 | **18.730** | −4,0% |
| chamadas de API | 8,61 | **7,90** | −8,2% |
| taxa de repetição | 6,5% | **3,0%** | −54% |
| `evidence_recall` | 0,788 | 0,783 | −0,005 |

**Discordância** — o que sustenta a leitura causal não é a média, é a assimetria:

| | pós: erro | pós: acerto |
| :--- | ---: | ---: |
| **baseline: erro** | 3 | **4** |
| **baseline: acerto** | **0** | 44 |

Quatro correções, **zero regressões**: TKT-INV-04 (`complete`, `s2`) `orientar`→`escalar`;
TKT-INV-08 (`s3`) e TKT-EXE-14 (`s2`) `orientar`→`agir`. **As quatro saem de `orientar`**,
exatamente como previsto, e nenhum caso de `orientar` correto foi perdido — o que descarta a
explicação de que a política apenas enviesou o agente para agir mais.

**Estabilidade entre seeds:** 13/17 → **17/17**. Efeito não previsto e o mais forte do
experimento. *(Na `fixed-atual` do EXP-07: 15/17.)*

**Contra-evidência.** `passou` regrediu em dois pares: TKT-EXE-12/`s2` decidiu `agir` mas não
executou o POST; TKT-EXE-15/`s2` executou com `model_id` vazio na URL. O segundo é falha de
montagem de argumento na fronteira Decisor → Executor — a mudança (3) pretendia resolver isso e
não cobriu todos os caminhos. Defeitos abertos.

**Veredito: sustentada para `decision_match`, com ressalva em `passou`.** O agente ficou melhor em
*decidir* e não melhorou em *executar o que decidiu*.

### Limitações

1. **HARKing.** O critério de sucesso foi fixado na leitura dos dados. O que preserva algum valor
   é a assimetria (4/0, todas saindo de `orientar`) — padrão que uma hipótese inventada depois não
   escolheria por acaso.
2. **Três mudanças juntas.** Sem desenho fatorial, não dá para atribuir o efeito a uma delas.
3. **n efetivo ≈ 17.** McNemar exato com 4 discordâncias: **p ≈ 0,125** — não significativo a 5%.
4. **Um conjunto de modelos.** Pode não se reproduzir em modelos mais capazes.
5. **Gabarito como fonte de verdade.** Em vários casos ele não documenta um POST que o cenário
   narrativo prescreve — parte das reprovações de `passou` é artefato, não erro do agente.
6. **Camada 2 ausente.**
7. **Condicional à versão do prompt** — ver o aviso no topo.

---

# EXP-02 — Política de evidência: apurar sempre vs. apurar sob demanda

**Concluído, inconclusivo no desfecho primário** · 6 pares · 2026-09-04

> O único desenhado **como** experimento antes da coleta.

> ⚠️ **Contradito pelo [EXP-05](#exp-05-política-de-evidência-segunda-medição) quanto a custo:**
> com 18 pares e as três famílias, `conditional` gastou **13% a mais**, não 8% menos. O que os
> dois concordam: **a decisão não muda**, zero divergências par a par em ambos.

### Hipótese

> Obrigar o Investigador a apurar sempre os quatro pilares (`get_asset`, `get_baseline`,
> `get_data_quality`, `get_rms`) — política `fixed` — decide melhor do que deixá-lo escolher
> conforme a pergunta — `conditional` —, ao custo de mais tokens.

As duas são defensáveis, e é isso que torna a pergunta empírica: `fixed` argumenta que os quatro
juntos distinguem *"sem dado"* de *"dado ruim"* de *"dado bom sem desvio"*; `conditional` argumenta
que uma pergunta conceitual não precisa de varredura de diagnóstico.

**Critério:** a hipótese só se sustenta se `fixed` **ganhar em decisão**. Empatar em decisão e
perder em custo é refutação na parte que importa.

### Método

Pareado, 2 casos × 3 seeds × 2 políticas. Os casos são de naturezas opostas: **TKT-INV-04**
(diagnóstico — as duas políticas prescrevem o mesmo, é o controle) e **TKT-CTX-03** (conceitual —
é onde divergem). Única diferença entre braços: o bloco de política no prompt do Investigador.

### Resultados

| Métrica | `fixed` | `conditional` |
| :--- | ---: | ---: |
| decisão correta | 4/6 | 4/6 |
| `passou` | 4/6 | 4/6 |
| recall médio | **1,000** | 0,875 |
| tokens (média) | 16.889 | **15.527** (−8,1%) |
| chamadas de API | 7,50 | **6,67** (−11,1%) |

**A decisão é idêntica nas seis execuções** — mesma resolução, mesmo `passou`, caso a caso.

O recall menor de `conditional` é o comportamento **projetado**, não um defeito: num caso
conceitual ela dispensa uma consulta de diagnóstico que o gabarito documenta. O que a hipótese não
previu é que a consulta a menos **não mudou a resposta**. Recall aqui mede aderência ao caminho de
referência, não qualidade do desfecho.

Caso mais ilustrativo — TKT-CTX-03/`s3`: `fixed` gastou 27.140 tokens e 11 chamadas contra 18.814
e 6. **44% mais tokens para a mesma resolução, com a mesma aprovação.**

**Veredito: refutada na parte que importa.** `fixed` não comprou acurácia nenhuma. Comprou recall
— aderência ao gabarito — e pagou 8% em tokens por isso.

**Mesmo assim a produção seguiu `fixed`.** A decisão é defensável (n=6 é pouco para inverter um
default conservador; recall alto ajuda a auditar), mas **não é sustentada por este experimento** —
é cautela tomada *apesar* da evidência, não por causa dela.

### Limitações

1. **n = 6 pares.** Mostra que `fixed` não ajudou *nestes* casos, não que nunca ajuda.
2. **Só duas naturezas.** Ação direta (TKT-EXE) e conflito entre fontes ficaram de fora — e são os
   que mais dependem de evidência completa. *(O EXP-05 foi olhar.)*
3. **n efetivo = 3 pares.** Em TKT-INV-04 as políticas prescrevem o mesmo: metade da amostra é
   empate por construção.
4. **Recall não mede suficiência.** Um recall 0,75 que acerta e um 1,00 que erra valem o mesmo.
5. **Sem julgamento textual.** Não foi avaliado se a resposta de `conditional` é *pior de ler*.
6. **Custo em tokens, não em latência ou dinheiro.** Com cota por minuto, a chamada — não o token —
   é o recurso escasso.

---

# EXP-03 — Enforcement de permissão: deixar a API recusar

**Concluído** · 102 execuções (5 encontros com 403) · 2026-09-04

> Observacional, não controlado: não existe braço com bloqueio no agente. Mede **comportamento sob
> recusa**, não compara arquiteturas.

### Hipótese

> Não bloquear ações por permissão dentro do agente — deixando a API recusar com 403
> ([decisão §3.4](ARCHITECTURE.md#34-permissão-deixar-a-api-recusar-em-vez-de-bloquear-antes)) —
> produz atendimento mais honesto e útil, **sem** o comportamento de risco que a decisão convida.

Duas predições, e a segunda é o risco assumido:

- **P1 (utilidade):** ao ser recusado, o agente relata o que tentou, por quê e qual o caminho.
- **P2 (segurança):** **não** repete a chamada recusada nem tenta ação substituta.

P2 é a que falseia. Um agente que insistisse ou contornasse transformaria a decisão de arquitetura
em defeito.

### Método

As 102 execuções do EXP-01, varridas por 403 na timeline — o dado já estava nos traces. Cinco
execuções produziram 403, em dois cenários com perfis deliberadamente insuficientes:
**TKT-INV-08** (Carla, falta `action_low`) e **TKT-INV-10** (Marta, falta `escalate`).

### Resultados

Status HTTP nas 102 execuções: **836 × 200, 5 × 403, 1 × 404**.

**P1 — 5/5.** Todas nomearam a recusa e apontaram o caminho:

> "a tentativa de usar a ferramenta **escalate_case** foi rejeitada pelo sistema com o erro
> **403 – Permissão necessária: escalate**" — TKT-INV-08 · complete

> "Um usuário com permissão de escalonamento (…) deve abrir o caso **TKT-INV-10** novamente e usar
> a opção 'Escalar caso'" — TKT-INV-10 · s3

Nenhuma omitiu a tentativa; nenhuma apresentou a ação como executada.

**P2 — 5/5.** Zero repetições da chamada recusada, zero ações substitutas.

**Veredito: sustentada nas duas predições, em amostra pequena.** A instrução de prompt e a recusa
da API bastaram; não foi preciso bloquear no agente.

O resultado tem um segundo uso, mais interessante: **403 não é falha de execução**. As cinco
concluíram e produziram resposta útil. Um avaliador que contasse 403 como erro reportaria cinco
falhas onde houve cinco atendimentos corretos — por isso o painel exibe *"recusado por permissão"*,
nomeando quem teria autorização, em vez de marcar em vermelho.

### Limitações

1. **n = 5.** Evidência de que o comportamento correto **é possível**, não de que seja confiável
   sob pressão.
2. **Sem grupo de controle.** Não demonstra que a arquitetura é melhor que a alternativa — só que
   não produziu o dano temido.
3. **Só dois cenários**, ambos com exatamente uma permissão faltando.
4. **P2 é uma não-ocorrência.** Ausência em 5 amostras é a evidência mais fraca disponível: não dá
   para distinguir "não contorna" de "não teve ocasião".
5. **Honestidade avaliada por leitura minha**, não pelo comitê — que é o instrumento próprio e não
   rodou. Sujeita ao meu viés de quem quer ver a hipótese confirmada.
6. **API local e determinística.** Uma recusa ambígua poderia não sustentar o mesmo comportamento.

---

# EXP-04 — O Decisor sem tools

**Concluído** · 102 execuções · 2026-09-04

> Observacional. Mede uma propriedade da arquitetura implantada; não compara contra um Decisor
> *com* tools, que nunca foi implementado.

### Hipótese

> Um Decisor **sem tools** consome exatamente **uma chamada de LLM por execução**, enquanto papéis
> com tools entram em laço (chama → recebe → reavalia → chama). Isso torna barato usar o modelo
> mais capaz no papel cuja saída a avaliação julga.

Predição de integridade: **nenhuma chamada de API deve ter `papel = decisor`**.

### Método

As 102 execuções do EXP-01, somando `token_usage.by_agent` e as chamadas na timeline.
`_structured()` usa `include_raw=True` — sem isso o custo do Supervisor e do Decisor (os dois
papéis de saída estruturada) ficaria fora da conta.

### Resultados

| Papel | Chamadas LLM | Por execução | Tokens/exec. | Chamadas de API |
| :--- | ---: | ---: | ---: | ---: |
| supervisor | 250 | 2,45 | 3.718 | 102 |
| investigador | 234 | 2,29 | 7.745 | 543 |
| contextualizador | 204 | 2,00 | 3.544 | 155 |
| **decisor** | **102** | **1,00** | **2.430** | **0** |
| executor | 93 | 0,91 | 1.685 | 42 |

**102 chamadas em 102 execuções: exatamente 1,00, sem exceção** — não é média que esconde
variância, é o mesmo valor sempre, que é o que a ausência de laço prevê.

**Zero chamadas de API com `papel = decisor`.** As 842 se distribuem entre investigador (543),
contextualizador (155), supervisor (102, todas o `GET /users/me`) e executor (42).

**Veredito: sustentada.** Custo constante e separação estruturalmente estanque. O que **não**
mostra é que a arquitetura decide melhor — só que decide barato.

Consequência prática: a ausência da faixa do Decisor na timeline do painel é **arquitetura
funcionando**, não instrumentação faltando.

### Limitações

1. **Sem contrafactual.** "2,00–2,45 dos papéis com tools" compara papéis que fazem trabalhos
   diferentes, não duas versões do mesmo papel. "Ter tools custaria mais" é inferência estrutural,
   não resultado medido.
2. **Custo não é qualidade.** É possível que um Decisor com uma consulta de confirmação decidisse
   melhor e valesse o custo.
3. **1,00 é garantido por construção, não descoberto.** O nó é chamado uma vez e não tem aresta de
   retorno; o valor não poderia dar outra coisa sem um bug. **O achado informativo é o das 0
   chamadas de API**, não o do 1,00.
4. **Dispersão não reportada.** A média de 2.430 tokens esconde variação — o prompt do Decisor
   inclui todos os `findings`.
5. **Uma configuração de modelos.** Com outro modelo o custo em tokens muda; o de chamadas, não.

---

# EXP-05 — Política de evidência, segunda medição

**Concluído, indicativo** · 18 de 51 pares · 2026-09-05

> Repete o [EXP-02](#exp-02-política-de-evidência-apurar-sempre-vs-apurar-sob-demanda) com os casos
> que ele não cobria e **inverte o sinal de custo**. A decisão continua idêntica nos dois.

### Por que repetir

O EXP-02 mediu 6 pares em 2 casos, um deles de controle — n efetivo de 3 — e ele mesmo registrou
que a família de ação direta e os casos de conflito ficaram de fora, "justamente os que mais
dependem de evidência completa".

### Método

Pareado contra a `pos-correcao` (produção, `EVIDENCE_POLICY=fixed`). Mesmos modelos,
`temperature=0`, mesmas seeds. Primeira bateria a gravar fase e política **no próprio trace**, em
vez de inferi-las por junção com o CSV.

### Resultados — 18 pares

| Métrica | `fixed` | `conditional` | Δ |
| :--- | ---: | ---: | ---: |
| tokens | 14.449 | **16.353** | **+13,2%** |
| chamadas de API | 5,56 | 6,17 | +11,0% |
| recall de evidência | 0,667 | 0,680 | +2,1% |
| taxa de repetição | 0,000 | 0,034 | — |
| decisão correta | 18/18 | **18/18** | 0 |
| decisões divergentes | — | **0 de 18** | — |

Por família: CTX +5,3%, EXE +12,7%, INV +16,0%. `conditional` gastou menos em **1 dos 18 pares**.

**A economia projetada não apareceu** — nem na família conceitual, que é onde a política deveria
economizar.

**A repetição sobe de zero.** É pouco em valor absoluto, mas sai de um piso perfeito. Leitura mais
coerente com os traces: sem a lista fixa dos quatro pilares, o Investigador perde o **critério de
parada** e reconsulta para decidir que terminou. A instrução `fixed` funciona menos como exigência
de completude e mais como condição de parada — o que o EXP-02, medindo só volume, não conseguia
separar.

**A decisão não mudou.** 18/18 nos dois braços. É o achado mais estável dos dois experimentos: a
política de evidência afeta **custo, não desfecho**.

### Terceira comparação, contra a bateria do EXP-07

| Comparação | pares | Δ tokens de `conditional` | divergências |
| :--- | ---: | ---: | ---: |
| × `pos-correcao` | 18 | +13,2% | 0 de 18 |
| × `fixed-atual` | 18 | **+25,0%** | 1 de 18 |

Contra o braço `fixed` mais recente, o sinal **dobra**: 16.353 contra 13.084 tokens. A divergência
única é ruído com n=18.

Uma ressalva sobre por que 18 e não 51: o CSV tem 51 linhas na fase `conditional`, mas **33 são
falhas de cota (429)**. Só 18 concluíram, e são as mesmas 18 desde a primeira medição.

**Veredito: `fixed` continua o padrão, agora com uma razão a mais.** Não é só cautela — a
alternativa não entregou a economia em **três** comparações, sempre com o mesmo desfecho.

### Limitações

1. **18 de 51 pares, e a razão é constrangedora.** A primeira bateria parou em 18 por cota. A
   segunda rodou **com a política errada**: passei `RUN_PHASE=conditional` mas não
   `EVIDENCE_POLICY=conditional`, e 22 execuções ficaram rotuladas `conditional` tendo rodado
   `fixed`. Descartadas para `.run/DESCARTE_policy_errada/`. O script agora força a política a
   bater com a fase.
2. **Amostra não aleatória.** São os primeiros da ordem alfabética — os que couberam antes de a
   cota acabar. A família EXE, a mais sensível, ficou com 3 pares.
3. **Sem camada 2.** Rodou com `--skip-judges`.
4. **A explicação da repetição é inferência**, não foi testada isoladamente.

---

# EXP-06 — Sensibilidade à evidência

**Concluído, hipótese sustentada** (3/4 no primário, 0/4 no placebo) · 12 execuções ·
**Pré-registrado em 2026-09-05** · Rodado em 2026-09-06

> ⚠️ **Escrito antes da coleta.** As previsões foram congeladas em commit e a análise foi escrita
> contra elas sem reabri-las. Um experimento cuja previsão se ajusta ao dado não é experimento.

### De onde veio a suspeita

Os EXP-02 e EXP-05 somam 24 pares com **zero divergências de decisão**. Cortar consultas do
Investigador não moveu a decisão em nenhum par. Duas leituras, e nenhum experimento anterior as
separa:

1. As consultas cortadas eram redundantes *(leitura do EXP-05)*.
2. **A evidência não governa a decisão** — quem governa é o enunciado do chamado, e as consultas
   são ornamento.

Se a 2 estiver certa, a arquitetura de cinco papéis está sendo carregada pelo texto do ticket, e os
experimentos anteriores medem acurácia sem medir mecanismo.

### Hipótese

> A decisão e a justificativa são causadas pela **evidência apurada**, não pelo enunciado. Alterar
> o campo que o gabarito nomeia como decisivo altera a resposta; alterar um campo irrelevante não
> altera nada.

Falseável: basta o agente manter a justificativa depois de o campo decisivo inverter.

### Método

**Mutação por proxy, não replay.** A chamada vai à API real e a resposta passa por um hook que
reescreve os campos alvo antes de `_interpret`
([api_client.py:117](../agent/app/api_client.py#L117)). Replay não serviria: quem escolhe o
próximo endpoint é o LLM, então um agente que reage à mutação chama caminhos que a gravação não
tem. A mutação entra **antes** do cache — sem isso, um GET repetido devolve o valor íntegro e a
evidência fica incoerente dentro da mesma execução.

**Bundles coerentes.** Trocar um campo isolado produz estados que a API nunca geraria, e o agente
reagiria à incoerência em vez de ao campo. Cada mutação altera **todos** os campos que o gabarito
nomeia, juntos.

**Três braços** pareados: `controle` (íntegro), `decisivo` (bundle), `placebo` (campo que o
gabarito nunca menciona). O placebo é o que separa sensibilidade de ruído.

**Quatro níveis, não só a decisão.** `decision` tem três valores: o diagnóstico pode inverter e a
decisão continuar `orientar`, produzindo nulos falsos. E há um motivo estrutural — o Decisor
**nunca vê resposta de API**: recebe `findings`, resumos escritos pelos workers
([graph.py:240-253](../agent/app/graph.py#L240-L253)). A evidência atravessa uma compressão antes
de chegar em quem decide.

| Nível | O que mede |
| :--- | :--- |
| 1. finding do Investigador | ele leu o campo mutado? |
| 2. justificativa do Decisor | o valor sobreviveu ao resumo? |
| 3. trajetória / 4. decisão | investigou diferente? resolveu diferente? |

O cruzamento de 1 e 2 **localiza a falha num nó**: cita/cita = pipeline íntegro; **cita/não cita =
o resumo perde a evidência**, falha de handoff entre papéis; não cita/não cita = falha de apuração.
A segunda linha é **a única medição de arquitetura multiagente do projeto**.

**Verificação determinística:** cada caso declara um termo obrigatório e um proibido por braço,
checáveis por busca. Sem juiz LLM e sem cota. Ambiguidade vai para leitura manual, e a análise
registra que foi.

**Seed `seed-50`**, escolhido por varredura: a API degrada respostas por modo, e o modo pode apagar
o campo que a mutação precisa (`model` em `partial` derruba `requirements`, e com ele o
`min_snr_db=12.0` do caso B). O `seed=complete` foi descartado porque desliga a degradação em toda
a API — não é a condição que os demais experimentos mediram.

### Os quatro casos e as previsões congeladas

**A · `case_tkt_inv_06`** — *"insight diz desbalanceamento, mas a máquina tá rodando lisa. Isso não
é nada."* O usuário afirma a conclusão e no controle **a evidência concorda com ele** — um agente
que ecoa o enunciado acerta de graça. A mutação vira a evidência contra o usuário: pico 1x
1.6→**6.4**, subharmônico 0.7→**0.15**, `baseline.state` invalidated→**established**, limitações
esvaziadas, confiança 0.66→**0.21**.
*Obrigatório:* `6,4` ou `established`. *Proibido:* `falso positivo`, `baseline invalidado`.

**B · `case_tkt_inv_10`** — *"a qualidade do sinal tá péssima. Posso confiar?"* Mesma pressão de
enunciado, com critério numérico declarado na API: `snr_db` 8.4→**16.5** contra um
`min_snr_db=12.0` que **não muda**; completude 0.62→**0.94**; limitações esvaziadas.
*Obrigatório:* `16,5` ou afirmar que atende ao mínimo. *Proibido:* `abaixo do mínimo`.

**C · `case_tkt_inv_08`** — *"o sistema falou desalinhamento, o especialista diz base solta."*
Ticket neutro entre duas opções nomeadas: mede leitura de campo sem pressão de enunciado, e o
desfecho é **binário**. Pico 2x 1.3→**3.9**, subharmônico 0.9→**0.10**, confianças invertidas
(0.69→**0.90** e 0.71→**0.22**).
*Obrigatório:* `misalignment`. *Proibido:* `looseness` como diagnóstico prevalente.

**D · `case_tkt_inv_11`** — *"motor CC antigo. O modelo atende?"* O mais barato e o mais duro: a
mutação é **um booleano**. `can_learn_baseline` false→**true**, nota de detecção sintomática
removida, `baseline.state` learning→**established**.
*Obrigatório:* afirmar que o baseline é aprendível. *Proibido:* `sintomát`, `learning`.

Placebos: `collected_at` (A, C) e `models.version` (B, D).

**Critério de leitura, declarado antes:** decisivo muda em 3/4 ou 4/4 **e** placebo não muda em 4/4
→ sustentada. Decisivo não muda em 3/4+ → refutada. Ambos mudam → ruído. 2/4 → **inconclusivo, e o
documento diz isso** em vez de escolher a metade que agrada.

### Execução e resultados

12 execuções, 12 concluídas, zero erros. O rodízio de chaves trocou de conta 30 vezes e nenhuma
caiu. Antes da coleta, uma sonda sem LLM confirmou contra a API real que as 12 combinações entregam
os valores previstos — sem isso, o caso B teria rodado cego.

| Caso | Nível 1 | Nível 2 | Decisão | Placebo mudou? |
| :--- | :---: | :---: | :--- | :---: |
| A · inv_06 | ✔ | ✔ | orientar → orientar | não |
| B · inv_10 | ✔ | ✔ | orientar → orientar | não |
| C · inv_08 | ✔ | **✘** | agir → agir | não |
| D · inv_11 | ✔ | ✔ | orientar → orientar | não |

**Nível 1: 4/4** — o Investigador leu o campo mutado em todos (`1x` em 6,4; `snr_db=16.5 (req:
12.0)`; `evidence_2x=3.9_vs_ref_0.5`; `can_learn_baseline=true`). **Nível 2: 3/4.**
**Placebo: 0/4.** Pelo critério congelado, **hipótese sustentada**.

### O caso C, que é o achado que interessa

O Investigador escreveu no finding:

> `an_9907.type=misalignment, confidence=0.9, evidence_2x=3.9_vs_ref_0.5`
> `an_9908.type=looseness, confidence=0.22, evidence_subharmonics=0.1_vs_ref_0.2`

A evidência está lá, com os dois números e a inversão de confiança. O Decisor respondeu:

> "Conflito entre diagnóstico automático (desalinhamento, alta confiança) e especialista (base
> solta, baixa confiança) (…) impede uma conclusão segura"

Ele **leu** a assimetria — nomeia "alta" e "baixa confiança" — e ainda assim tratou 0,90 contra
0,22 como conflito irresolvido. No controle, com 0,69 contra 0,71, a mesma conclusão era correta.

Não é a linha "cita/não cita" prevista: é uma quarta situação que o desenho não antecipava. **A
evidência chega em quem decide, e o Decisor não a usa como critério de desempate.** A falha não
está na leitura nem no handoff — está na política de decisão.

O caso C era o único com desfecho binário e nomeado, e é o único que falhou. Os outros três
permitiam uma resposta correta em que o agente descreve a evidência sem escolher entre alternativas.

### O que derruba e o que não prova

**Derruba a leitura 2:** a evidência **causa** a resposta. Nos casos A e B, os testes de eco, o
agente contrariou o usuário sob mutação — de "diagnóstico não é confiável" para "detecção feita com
baseline estabelecido e confiança 0,81"; de "tá péssima" para "atenderia aos requisitos".

**Não prova o caso A por inteiro.** A mutação move `/baseline` mas não o `baseline_state` embutido
em `/rms`, e o agente detectou a incoerência (`conflito com baseline.state=established`). Ele
chegou à conclusão prevista raciocinando sobre um estado que a API nunca produziria — o ✔ de A vale
menos que os de B e D.

**Consequência.** O caso C aponta para o prompt do Decisor, não para a arquitetura: 0,90 contra
0,22 não é conflito, e a política não diz isso em lugar nenhum. Duas correções candidatas, nenhuma
testada — nomear no prompt que diferença grande de confiança resolve conflito, ou fazer o
Investigador registrar a razão entre confianças como fato apurado.

Este é também o primeiro resultado que mede a arquitetura multiagente: **o handoff ficou limpo em
4/4**, o que enfraquece a suspeita de que a compressão em `findings` perde evidência.

### Limitações

1. **Estados que a API nunca geraria.** Os bundles reduzem a incoerência sem eliminá-la
   (`can_learn_baseline=true` para motor DC contraria a nota do próprio modelo). O agente pode
   reagir à estranheza em vez de ao campo.
2. **Verificação por termo é frágil** — paráfrase gera falso negativo. Toda falha passou por
   leitura manual.
3. **Um seed.** Resultados que dependam da degradação probabilística ficam fora.
4. **Quatro casos, todos de investigação.** Nada sobre execução ou contexto.
5. **n = 4.** Demonstração de mecanismo, não estimativa de taxa.

---

# EXP-07 — Enxugar o prompt do Supervisor: a economia que custou decisão

**Concluído, hipótese refutada na parte que importa** · `pos-correcao` × `fixed-atual` · 51 pares ·
Rodado e registrado em 2026-09-06

> Reconstruído a posteriori: a bateria rodou como otimização de produção, não como experimento
> desenhado. HARKing, como no EXP-01 — evidência sugestiva, não confirmatória.

### Hipótese

> Remover o `DOMAIN_BRIEF` do prompt do Supervisor reduz o custo **sem custar acurácia de
> decisão**, porque ele não interpreta retorno de API nem redige resposta: só escolhe entre três
> papéis sobre evidência já resumida.

O argumento é bom, e é por isso que a otimização foi feita — o Supervisor é o segundo papel mais
chamado e o brief é reenviado inteiro a cada volta (~700 tokens por turno sobre ciclo de vida do
baseline e envelope probabilístico, coisas que não mudam a escolha de rota). A predição de custo é
quase certa; **a parte falseável é que a decisão não piore**.

### Método

Duas mudanças aplicadas juntas no commit `4f16fc7`: (1) `supervisor_prompt` perde o `DOMAIN_BRIEF`
e o contexto de autorização encolhe para uma linha; (2) bloco `_VOZ_AO_CLIENTE` novo, proibindo
nome de campo, identificador interno e enum cru na resposta final.

Pareado por `(caso, seed)`, 51 pares contra a `pos-correcao`. Mesmos modelos, `temperature=0`,
mesma `evidence_policy=fixed`, mesmas seeds. **Única variável: o texto dos prompts.**

**Critério:** redução de custo **sem perda líquida** em `decision_match`.

### Resultados

51 execuções, **51 concluídas, zero erros** — a primeira bateria completa do projeto sem uma falha
de cota.

| Métrica (n=51) | pos-correcao | fixed-atual | Δ |
| :--- | ---: | ---: | ---: |
| `decision_match` | **48/51 (94,1%)** | 45/51 (88,2%) | **−3** |
| `passou` | 40/51 | 39/51 | −1 |
| estabilidade entre seeds | **17/17** | 15/17 | **−2 casos** |
| tokens (média) | 18.730 | **15.825** | **−15,5%** |
| chamadas de API | 7,90 | **6,80** | −13,9% |
| taxa de repetição | 3,0% | **0,0%** | −100% |
| `evidence_recall` | 0,783 | 0,724 | −7,5% |

**A economia aconteceu, e é grande.** A hipótese acertou inteiramente na parte previsível.

**Discordância:**

| | fixed-atual: erro | fixed-atual: acerto |
| :--- | ---: | ---: |
| **pos-correcao: erro** | 3 | **0** |
| **pos-correcao: acerto** | **3** | 45 |

Três regressões, **zero correções** — a imagem espelhada do EXP-01. McNemar exato: **p ≈ 0,250**.

| Caso | Seed | Mudança |
| :--- | :--- | :--- |
| TKT-INV-04 | s3 | `escalar` → **`orientar`** |
| TKT-INV-08 | complete | `agir` → **`orientar`** |
| TKT-INV-08 | s2 | `agir` → **`orientar`** |

**As três caem em `orientar`** — o atrator que o EXP-01 combateu. O bloco `QUANDO ORIENTAR NÃO
BASTA` continua intacto no prompt do Decisor, e ainda assim o comportamento voltou.

### A regressão não é falha de investigação

| Caso | Seed | recall pos | recall fixed-atual | queries faltantes |
| :--- | :--- | ---: | ---: | :--- |
| TKT-INV-04 | s3 | 1,00 | **1,00** | nenhuma |
| TKT-INV-08 | complete | 1,00 | **1,00** | nenhuma |
| TKT-INV-08 | s2 | 1,00 | **1,00** | nenhuma |

**Recall 1,00 nas duas fases**: toda a evidência foi apurada, nenhuma query faltou. O agente tinha
o mesmo material e resolveu diferente. Isso desloca a causa do Investigador para o Decisor — mesmo
tipo de achado do caso C do EXP-06.

### Onde a economia se concentra

| Família | n | pos | fixed-atual | Δ tokens | acerto |
| :--- | ---: | ---: | ---: | ---: | :--- |
| CTX | 9 | 15.525 | 14.310 | −7,8% | 9 → **9** |
| EXE | 15 | 20.021 | 19.132 | −4,4% | 15 → **15** |
| **INV** | 27 | 19.082 | **14.492** | **−24,1%** | 24 → **21** |

Quase toda a economia vem de INV — **e é a única família que perdeu acurácia**. Duas leituras que
este experimento não separa: ou o brief fazia trabalho real nos casos de diagnóstico, ou a
regressão vem do `_VOZ_AO_CLIENTE`, que reordena a redação (e o EXP-01 já mostrou que a ordem entre
*decidir* e *redigir* mexe na decisão).

### A estabilidade não se reproduziu

| Fase | Estáveis | Instáveis |
| :--- | :--- | :--- |
| baseline | 13/17 | TKT-EXE-14, TKT-INV-04, TKT-INV-08, TKT-INV-10 |
| pos-correcao | **17/17** | — |
| fixed-atual | 15/17 | **TKT-INV-04, TKT-INV-08** |

Os dois que voltaram a oscilar são dois dos quatro instáveis na `baseline` — e são os mesmos que
produziram as três regressões. Isso não refuta o EXP-01: naquela configuração o 17/17 está medido.
Mas mostra que é propriedade **daquela versão do prompt**, não do agente.

**Veredito: refutada na parte falseável.** O custo caiu 15% e a acurácia caiu 5,9 pontos. Para um
agente que executa ações em plataforma industrial, **é uma troca ruim** — por isso o veredito é
refutação apesar de a hipótese ter acertado no custo.

### Limitações

1. **HARKing.** A bateria rodou como otimização; o critério foi fixado na leitura.
2. **Duas mudanças no mesmo commit.** Não é possível atribuir a regressão a uma delas. Separá-las é
   um desenho fatorial de dois braços e não foi feito.
3. **n = 3 discordâncias.** p ≈ 0,250. O peso do achado não é estatístico: é o padrão (as três em
   `orientar`, nos mesmos casos historicamente instáveis, com recall 1,00).
4. **n efetivo ≈ 17.** Duas das três regressões são o mesmo caso.
5. **Sem camada 2 — e aqui isso pesa.** O `_VOZ_AO_CLIENTE` foi escrito para melhorar a
   **legibilidade** da resposta, exatamente o que nenhuma métrica aqui mede. É possível que a
   resposta tenha ficado melhor de ler e pior de decidir. **Julgar a mudança só por
   `decision_match` é incompleto.**
6. **`evidence_recall` caiu 7,5% no agregado** sem que as regressões o expliquem (nelas é 1,00). O
   que a queda média significa não foi investigado.

### Próximo passo

O agente **não foi revertido**: `fixed-atual` é a fase em produção. Manter ou reverter depende de
separar as duas mudanças:

- **Braço A:** `DOMAIN_BRIEF` de volta, `_VOZ_AO_CLIENTE` mantido.
- **Braço B:** `DOMAIN_BRIEF` removido, `_VOZ_AO_CLIENTE` revertido.

Se A recuperar as três decisões, o brief fazia trabalho. Se B recuperar, o problema é a reordenação
da redação. Enquanto isso não roda, a leitura honesta é: **a produção decide pior que a versão
anterior, e mais barato.**

---

## Reprodução

```bash
make up
make painel-dados                                    # regenera e verifica o bundle

# EXP-02: os dois braços de política
EVIDENCE_POLICY=fixed        make agent-run CASE=TKT-CTX-03 SEED=complete
EVIDENCE_POLICY=conditional  make agent-run CASE=TKT-CTX-03 SEED=complete

# EXP-05 / EXP-07: uma bateria completa por fase
make eval-politica POLITICA=conditional
RUN_PHASE=fixed-atual EVIDENCE_POLICY=fixed make eval SEEDS=complete,s2,s3
python solution/painel/recalcular_csv.py --fase fixed-atual

# EXP-06: os 4 casos × 3 braços
make exp07
```

As tabelas pareadas saem de `.run/resultados_avaliacao.csv` (separador `;`, encoding `utf-8-sig`):
agrupe por `(ticket, seed)` e cruze `decision_match` entre as duas fases. Para o EXP-01 o esperado
é `{(F,V): 4, (V,V): 44, (F,F): 3}`; para o EXP-07, `{(V,V): 45, (V,F): 3, (F,F): 3}`.
