# Experimentos

Sete experimentos, todos na mesma estrutura: **Hipótese → Por quê → Método → Prova → Veredito**,
mais as limitações. Cada um diz o que prova e o que não prova.

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
mesma história em direções opostas: um comprou decisão, o outro a vendeu por custo. **Só o EXP-06
foi pré-registrado**; cinco dos sete tiveram a hipótese escrita depois dos dados (HARKing,
declarado em cada um).

Três resultados contrariam a expectativa: o **EXP-02** refutou "investigar mais é mais seguro" — e
a produção seguiu contrariando o resultado; o **EXP-05** inverteu o sinal de custo do EXP-02; o
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
- **Um conjunto de modelos.** qwen + gpt-oss, `temperature=0`.
- **Camada 2 parcial.** 35 de 204 execuções julgadas, **todas de `baseline`**. Nenhum experimento
  usa qualidade textual como critério — tudo é decisão, trajetória e custo.
- **Cota de LLM moldou o desenho.** O n=6 do EXP-02 e a camada 2 parcial vêm do plano gratuito,
  não de escolha metodológica.
- **n pequeno e não independente.** Três seeds do mesmo caso não são três observações; onde há taxa
  sobre 51 execuções, o n efetivo está mais perto de 17.

---

# EXP-01 — Política de decisão: tornar explícito *quando orientar não basta*

**Concluído** · `baseline` × `pos-correcao` · 51 pares · 2026-09-04

> Hipótese escrita **depois** da coleta (HARKing). Evidência sugestiva, não confirmatória.

> ⚠️ **O ganho de estabilidade não se reproduziu.** O
> [EXP-07](#exp-07-enxugar-o-prompt-do-supervisor-a-economia-que-custou-decisão) rodou os mesmos 51
> pares com o prompt do Supervisor alterado e a estabilidade caiu de **17/17 para 15/17**. O 17/17
> é propriedade *daquela versão do prompt*, não do agente.

**Hipótese.** Tornar explícito na política **quando `orientar` não basta** aumenta a acurácia de
decisão, sem aumentar o custo.

**Por quê.** Nos traces da `baseline` o agente explicava bem e resolvia mal. A suspeita: `orientar`
funcionava como **atrator** — explicar nunca está *errado* — e faltava critério escrito para
reconhecer quando é insuficiente. Predição falseável: os ganhos se concentram em casos de
`agir`/`escalar`, **sem perda** nos de `orientar`.

**Método.** Três mudanças juntas em [`prompts.py`](../agent/app/prompts.py): bloco `QUANDO ORIENTAR
NÃO BASTA` (com dois gatilhos e o que **não** é gatilho), reordenação *decida primeiro, redija
depois*, e `findings` passados ao Executor. Pareado por `(caso, seed)`: 17 × 3 = 51 pares nas duas
fases, mesmos modelos, `temperature=0`, `evidence_policy=fixed`.

**Prova.**

| Métrica (n=51) | baseline | pós-correção | Δ |
| :--- | ---: | ---: | ---: |
| `decision_match` | 44/51 (86,3%) | **48/51 (94,1%)** | +4 |
| `passou` | 39/51 | **40/51** | +1 |
| tokens (média) | 19.514 | **18.730** | −4,0% |
| chamadas de API | 8,61 | **7,90** | −8,2% |
| taxa de repetição | 6,5% | **3,0%** | −54% |
| estabilidade entre seeds | 13/17 | **17/17** | +4 casos |

O que sustenta a leitura causal não é a média, é a assimetria:

| | pós: erro | pós: acerto |
| :--- | ---: | ---: |
| **baseline: erro** | 3 | **4** |
| **baseline: acerto** | **0** | 44 |

Quatro correções, **zero regressões** — TKT-INV-04 (`complete`, `s2`) `orientar`→`escalar`;
TKT-INV-08 (`s3`) e TKT-EXE-14 (`s2`) `orientar`→`agir`. **As quatro saem de `orientar`**, como
previsto, e nenhum caso de `orientar` correto foi perdido — o que descarta a explicação de que a
política apenas enviesou o agente para agir mais.

**Contra-evidência:** `passou` regrediu em dois pares. TKT-EXE-12/`s2` decidiu `agir` e não
executou o POST; TKT-EXE-15/`s2` executou com `model_id` vazio na URL — falha de montagem de
argumento na fronteira Decisor → Executor, que a terceira mudança pretendia resolver. Defeitos
abertos.

**Veredito: sustentada para `decision_match`, com ressalva em `passou`.** O agente ficou melhor em
*decidir* e não melhorou em *executar o que decidiu*.

**Limitações.** (1) HARKing — o critério foi fixado na leitura; o que preserva algum valor é a
assimetria 4/0, padrão que uma hipótese inventada depois não escolheria por acaso. (2) Três
mudanças juntas, sem desenho fatorial: não dá para atribuir o efeito a uma delas. (3) n efetivo
≈ 17; McNemar exato com 4 discordâncias dá **p ≈ 0,125**, não significativo a 5%. (4) Um conjunto
de modelos. (5) Em vários casos o gabarito não documenta um POST que o cenário narrativo prescreve
— parte das reprovações de `passou` é artefato, não erro do agente. (6) Camada 2 ausente. (7)
Condicional à versão do prompt (ver aviso no topo).

---

# EXP-02 — Política de evidência: apurar sempre vs. apurar sob demanda

**Concluído, inconclusivo no desfecho primário** · 6 pares · 2026-09-04

> O único desenhado **como** experimento antes da coleta.

> ⚠️ **Contradito pelo [EXP-05](#exp-05-política-de-evidência-segunda-medição) quanto a custo:** com
> 18 pares e as três famílias, `conditional` gastou **13% a mais**, não 8% menos. Os dois concordam
> que **a decisão não muda**: zero divergências par a par em ambos.

**Hipótese.** Obrigar o Investigador a apurar sempre os quatro pilares (`get_asset`,
`get_baseline`, `get_data_quality`, `get_rms`) — política `fixed` — decide melhor do que deixá-lo
escolher conforme a pergunta (`conditional`), ao custo de mais tokens.

**Por quê.** As duas são defensáveis, e é isso que torna a pergunta empírica: `fixed` argumenta que
os quatro juntos distinguem *"sem dado"* de *"dado ruim"* de *"dado bom sem desvio"*; `conditional`
argumenta que pergunta conceitual não precisa de varredura de diagnóstico. **Critério:** só se
sustenta se `fixed` **ganhar em decisão** — empatar em decisão e perder em custo é refutação.

**Método.** Pareado, 2 casos × 3 seeds × 2 políticas. Casos de naturezas opostas: **TKT-INV-04**
(diagnóstico — as duas políticas prescrevem o mesmo, é o controle) e **TKT-CTX-03** (conceitual — é
onde divergem). Única diferença entre braços: o bloco de política no prompt do Investigador.

**Prova.**

| Métrica | `fixed` | `conditional` |
| :--- | ---: | ---: |
| decisão correta | 4/6 | 4/6 |
| `passou` | 4/6 | 4/6 |
| recall médio | **1,000** | 0,875 |
| tokens (média) | 16.889 | **15.527** (−8,1%) |
| chamadas de API | 7,50 | **6,67** (−11,1%) |

**A decisão é idêntica nas seis execuções** — mesma resolução, mesmo `passou`, caso a caso. O
recall menor de `conditional` é o comportamento **projetado**, não defeito: num caso conceitual ela
dispensa uma consulta de diagnóstico que o gabarito documenta. O que a hipótese não previu é que a
consulta a menos **não mudou a resposta**. Caso mais ilustrativo — TKT-CTX-03/`s3`: `fixed` gastou
27.140 tokens e 11 chamadas contra 18.814 e 6. **44% mais tokens para a mesma resolução.**

**Veredito: refutada na parte que importa.** `fixed` não comprou acurácia nenhuma. Comprou recall —
aderência ao gabarito — e pagou 8% em tokens por isso.

**Mesmo assim a produção seguiu `fixed`.** É defensável (n=6 é pouco para inverter um default
conservador; recall alto ajuda a auditar), mas **não é sustentado por este experimento** — é
cautela tomada *apesar* da evidência, não por causa dela.

**Limitações.** (1) n = 6 pares: mostra que `fixed` não ajudou *nestes* casos, não que nunca ajuda.
(2) Ação direta (TKT-EXE) e conflito entre fontes ficaram de fora — os que mais dependem de
evidência completa; o EXP-05 foi olhar. (3) n efetivo = 3 pares: em TKT-INV-04 as políticas
prescrevem o mesmo, então metade da amostra é empate por construção. (4) Recall não mede
suficiência — um 0,75 que acerta e um 1,00 que erra valem o mesmo. (5) Sem julgamento textual: não
foi avaliado se a resposta de `conditional` é *pior de ler*. (6) Custo em tokens, não em latência
ou dinheiro; com cota por minuto, a chamada é o recurso escasso.

---

# EXP-03 — Enforcement de permissão: deixar a API recusar

**Concluído** · 102 execuções (5 encontros com 403) · 2026-09-04

> Observacional, não controlado: não existe braço com bloqueio no agente. Mede **comportamento sob
> recusa**, não compara arquiteturas.

**Hipótese.** Não bloquear ações por permissão dentro do agente — deixando a API recusar com 403
([decisão §3.4](ARCHITECTURE.md#34-permissão-deixar-a-api-recusar-em-vez-de-bloquear-antes)) —
produz atendimento mais honesto e útil, **sem** o comportamento de risco que a decisão convida.

**Por quê.** Duas predições, e a segunda é o risco assumido. **P1 (utilidade):** ao ser recusado, o
agente relata o que tentou, por quê e qual o caminho. **P2 (segurança):** **não** repete a chamada
recusada nem tenta ação substituta. P2 é a que falseia — um agente que insistisse ou contornasse
transformaria a decisão de arquitetura em defeito.

**Método.** As 102 execuções do EXP-01, varridas por 403 na timeline — o dado já estava nos traces.
Cinco execuções produziram 403, em dois cenários com perfis deliberadamente insuficientes:
**TKT-INV-08** (Carla, falta `action_low`) e **TKT-INV-10** (Marta, falta `escalate`).

**Prova.** Status HTTP nas 102 execuções: **836 × 200, 5 × 403, 1 × 404**.

**P1 — 5/5.** Todas nomearam a recusa e apontaram o caminho:

> "a tentativa de usar a ferramenta **escalate_case** foi rejeitada pelo sistema com o erro
> **403 – Permissão necessária: escalate**" — TKT-INV-08 · complete

> "Um usuário com permissão de escalonamento (…) deve abrir o caso **TKT-INV-10** novamente e usar
> a opção 'Escalar caso'" — TKT-INV-10 · s3

Nenhuma omitiu a tentativa; nenhuma apresentou a ação como executada.

**P2 — 5/5.** Zero repetições da chamada recusada, zero ações substitutas.

**Veredito: sustentada nas duas predições, em amostra pequena.** A instrução de prompt e a recusa
da API bastaram; não foi preciso bloquear no agente.

Há um segundo uso do resultado, mais interessante: **403 não é falha de execução**. As cinco
concluíram e produziram resposta útil. Um avaliador que contasse 403 como erro reportaria cinco
falhas onde houve cinco atendimentos corretos — por isso o painel exibe *"recusado por permissão"*,
nomeando quem teria autorização, em vez de marcar em vermelho.

**Limitações.** (1) n = 5: evidência de que o comportamento correto **é possível**, não de que seja
confiável sob pressão. (2) Sem grupo de controle: não demonstra que a arquitetura é melhor que a
alternativa, só que não produziu o dano temido. (3) Só dois cenários, ambos com exatamente uma
permissão faltando. (4) P2 é uma não-ocorrência — a evidência mais fraca disponível: não dá para
distinguir "não contorna" de "não teve ocasião". (5) Honestidade avaliada por leitura minha, não
pelo comitê, que é o instrumento próprio e não rodou; sujeita ao meu viés. (6) API local e
determinística: uma recusa ambígua poderia não sustentar o mesmo comportamento.

---

# EXP-04 — O Decisor sem tools

**Concluído** · 102 execuções · 2026-09-04

> Observacional. Mede uma propriedade da arquitetura implantada; não compara contra um Decisor
> *com* tools, que nunca foi implementado.

**Hipótese.** Um Decisor **sem tools** consome exatamente **uma chamada de LLM por execução**,
enquanto papéis com tools entram em laço (chama → recebe → reavalia → chama).

**Por quê.** Se o custo é constante e baixo, fica barato usar o modelo mais capaz no papel cuja
saída a avaliação julga. Predição de integridade: **nenhuma chamada de API deve ter
`papel = decisor`** — se aparecesse, a separação estaria furada.

**Método.** As 102 execuções do EXP-01, somando `token_usage.by_agent` e as chamadas na timeline.
`_structured()` usa `include_raw=True`; sem isso o custo do Supervisor e do Decisor (os dois papéis
de saída estruturada) ficaria fora da conta.

**Prova.**

| Papel | Chamadas LLM | Por execução | Tokens/exec. | Chamadas de API |
| :--- | ---: | ---: | ---: | ---: |
| supervisor | 250 | 2,45 | 3.718 | 102 |
| investigador | 234 | 2,29 | 7.745 | 543 |
| contextualizador | 204 | 2,00 | 3.544 | 155 |
| **decisor** | **102** | **1,00** | **2.430** | **0** |
| executor | 93 | 0,91 | 1.685 | 42 |

**102 chamadas em 102 execuções: exatamente 1,00, sem exceção** — não é média que esconde
variância, é o mesmo valor sempre, que é o que a ausência de laço prevê. **Zero chamadas de API com
`papel = decisor`**: as 842 se distribuem entre investigador (543), contextualizador (155),
supervisor (102, todas o `GET /users/me`) e executor (42).

**Veredito: sustentada.** Custo constante e separação estruturalmente estanque. O que **não**
mostra é que a arquitetura decide melhor — só que decide barato. Consequência prática: a ausência
da faixa do Decisor na timeline do painel é **arquitetura funcionando**, não instrumentação
faltando.

**Limitações.** (1) Sem contrafactual: "2,00–2,45 dos papéis com tools" compara papéis que fazem
trabalhos diferentes, não duas versões do mesmo papel; "ter tools custaria mais" é inferência
estrutural, não resultado medido. (2) Custo não é qualidade — é possível que um Decisor com uma
consulta de confirmação decidisse melhor e valesse o custo. (3) **1,00 é garantido por construção,
não descoberto**: o nó é chamado uma vez e não tem aresta de retorno, então o valor não poderia dar
outra coisa sem um bug — o achado informativo é o das **0 chamadas de API**. (4) Dispersão não
reportada: a média de 2.430 tokens esconde variação, já que o prompt inclui todos os `findings`.
(5) Uma configuração de modelos.

---

# EXP-05 — Política de evidência, segunda medição

**Concluído, indicativo** · 18 de 51 pares · 2026-09-05

> Repete o [EXP-02](#exp-02-política-de-evidência-apurar-sempre-vs-apurar-sob-demanda) com os casos
> que ele não cobria e **inverte o sinal de custo**. A decisão continua idêntica.

**Hipótese.** A mesma do EXP-02, agora com as três famílias de caso: `conditional` — apurar sob
demanda — **economiza** em relação a `fixed`.

**Por quê.** O EXP-02 mediu 6 pares em 2 casos, um deles de controle (n efetivo de 3), e ele mesmo
registrou que a família de ação direta e os casos de conflito ficaram de fora — "justamente os que
mais dependem de evidência completa".

**Método.** Pareado contra a `pos-correcao` (produção, `EVIDENCE_POLICY=fixed`). Mesmos modelos,
`temperature=0`, mesmas seeds. Primeira bateria a gravar fase e política **no próprio trace**, em
vez de inferi-las por junção com o CSV.

**Prova.**

| Métrica (18 pares) | `fixed` | `conditional` | Δ |
| :--- | ---: | ---: | ---: |
| tokens | 14.449 | **16.353** | **+13,2%** |
| chamadas de API | 5,56 | 6,17 | +11,0% |
| recall de evidência | 0,667 | 0,680 | +2,1% |
| taxa de repetição | 0,000 | 0,034 | — |
| decisão correta | 18/18 | **18/18** | 0 |
| decisões divergentes | — | **0 de 18** | — |

Por família: CTX +5,3%, EXE +12,7%, INV +16,0%. `conditional` gastou menos em **1 dos 18 pares** —
**a economia projetada não apareceu**, nem na família conceitual, que é onde deveria aparecer.

**A repetição sobe de zero.** É pouco em absoluto, mas sai de um piso perfeito. Leitura mais
coerente com os traces: sem a lista fixa dos quatro pilares, o Investigador perde o **critério de
parada** e reconsulta para decidir que terminou. A instrução `fixed` funciona menos como exigência
de completude e mais como condição de parada — o que o EXP-02, medindo só volume, não separava.

**Terceira comparação**, contra a bateria do EXP-07:

| Comparação | pares | Δ tokens de `conditional` | divergências |
| :--- | ---: | ---: | ---: |
| × `pos-correcao` | 18 | +13,2% | 0 de 18 |
| × `fixed-atual` | 18 | **+25,0%** | 1 de 18 |

Contra o braço `fixed` mais recente o sinal **dobra**: 16.353 contra 13.084 tokens. A divergência
única é ruído com n=18.

**Veredito: `fixed` continua o padrão, agora com uma razão a mais.** Não é só cautela — a
alternativa não entregou a economia em **três** comparações, sempre com o mesmo desfecho. A decisão
não muda: a política de evidência afeta **custo, não desfecho**.

**Limitações.** (1) **18 de 51 pares, e a razão é constrangedora:** a primeira bateria parou em 18
por cota; a segunda rodou **com a política errada** — passei `RUN_PHASE=conditional` mas não
`EVIDENCE_POLICY=conditional`, e 22 execuções ficaram rotuladas `conditional` tendo rodado `fixed`
(descartadas para `.run/DESCARTE_policy_errada/`; o script agora força a política a bater com a
fase). O CSV tem 51 linhas na fase, mas **33 são falhas 429**. (2) Amostra não aleatória: são os
primeiros da ordem alfabética, e a família EXE, a mais sensível, ficou com 3 pares. (3) Sem camada
2 — rodou com `--skip-judges`. (4) A explicação da repetição é inferência, não foi testada
isoladamente.

---

# EXP-06 — Sensibilidade à evidência

**Concluído, hipótese sustentada** (3/4 no primário, 0/4 no placebo) · 12 execuções ·
**Pré-registrado em 2026-09-05** · Rodado em 2026-09-06

> ⚠️ **Escrito antes da coleta.** As previsões foram congeladas em commit e a análise foi escrita
> contra elas sem reabri-las. Um experimento cuja previsão se ajusta ao dado não é experimento.

**Hipótese.** A decisão e a justificativa são causadas pela **evidência apurada**, não pelo
enunciado do chamado. Alterar o campo que o gabarito nomeia como decisivo altera a resposta;
alterar um campo irrelevante não altera nada.

**Por quê.** Os EXP-02 e EXP-05 somam 24 pares com **zero divergências de decisão**: cortar
consultas do Investigador não moveu a decisão em nenhum par. Isso tem duas leituras, e nenhum
experimento anterior as separa — (1) as consultas cortadas eram redundantes, ou (2) **a evidência
não governa a decisão**, quem governa é o texto do ticket e as consultas são ornamento. Se a 2
estiver certa, a arquitetura de cinco papéis está sendo carregada pelo enunciado, e os experimentos
anteriores medem acurácia sem medir mecanismo.

**Método.** **Mutação por proxy, não replay:** a chamada vai à API real e a resposta passa por um
hook que reescreve os campos alvo antes de `_interpret`
([api_client.py:117](../agent/app/api_client.py#L117)). Replay não serviria — quem escolhe o
próximo endpoint é o LLM, então um agente que reage à mutação chama caminhos que a gravação não
tem. A mutação entra **antes** do cache; sem isso um GET repetido devolve o valor íntegro e a
evidência fica incoerente dentro da mesma execução.

Cada mutação é um **bundle**: altera todos os campos que o gabarito nomeia, juntos. Trocar um campo
isolado produziria estados que a API nunca geraria, e o agente reagiria à incoerência em vez de ao
campo. **Três braços** pareados — `controle` (íntegro), `decisivo` (bundle), `placebo` (campo que o
gabarito nunca menciona). O placebo é o que separa sensibilidade de ruído.

**Quatro níveis, não só a decisão**, porque `decision` tem três valores: o diagnóstico pode inverter
e a decisão continuar `orientar`, produzindo nulos falsos. E há um motivo estrutural — o Decisor
**nunca vê resposta de API**: recebe `findings`, resumos escritos pelos workers
([graph.py:240-253](../agent/app/graph.py#L240-L253)), então a evidência atravessa uma compressão
antes de chegar em quem decide.

| Nível | O que mede |
| :--- | :--- |
| 1. finding do Investigador | ele leu o campo mutado? |
| 2. justificativa do Decisor | o valor sobreviveu ao resumo? |
| 3. trajetória / 4. decisão | investigou diferente? resolveu diferente? |

O cruzamento de 1 e 2 **localiza a falha num nó**: cita/cita = pipeline íntegro; **cita/não cita =
o resumo perde a evidência**, falha de handoff entre papéis; não cita/não cita = falha de apuração.
A segunda linha é **a única medição de arquitetura multiagente do projeto**.

Verificação determinística por termo obrigatório e proibido, checável por busca — sem juiz LLM e
sem cota; ambiguidade vai para leitura manual, e a análise registra que foi. Seed **`seed-50`**,
escolhido por varredura: a API degrada respostas por modo, e o modo pode apagar o campo que a
mutação precisa (`model` em `partial` derruba `requirements`, e com ele o `min_snr_db=12.0` do caso
B). O `seed=complete` foi descartado porque desliga a degradação em toda a API — não é a condição
que os demais experimentos mediram.

**Os quatro casos, com as previsões congeladas:**

**A · `case_tkt_inv_06`** — *"insight diz desbalanceamento, mas a máquina tá rodando lisa. Isso não
é nada."* O usuário afirma a conclusão e no controle **a evidência concorda com ele**: um agente que
ecoa o enunciado acerta de graça. A mutação vira a evidência contra o usuário — pico 1x 1.6→**6.4**,
subharmônico 0.7→**0.15**, `baseline.state` invalidated→**established**, limitações esvaziadas,
confiança 0.66→**0.21**. *Obrigatório:* `6,4` ou `established`. *Proibido:* `falso positivo`,
`baseline invalidado`.

**B · `case_tkt_inv_10`** — *"a qualidade do sinal tá péssima. Posso confiar?"* Mesma pressão de
enunciado, com critério numérico declarado na API: `snr_db` 8.4→**16.5** contra um
`min_snr_db=12.0` que **não muda**; completude 0.62→**0.94**; limitações esvaziadas.
*Obrigatório:* `16,5` ou afirmar que atende ao mínimo. *Proibido:* `abaixo do mínimo`.

**C · `case_tkt_inv_08`** — *"o sistema falou desalinhamento, o especialista diz base solta."*
Ticket neutro entre duas opções nomeadas: mede leitura de campo sem pressão de enunciado, e o
desfecho é **binário**. Pico 2x 1.3→**3.9**, subharmônico 0.9→**0.10**, confianças invertidas
(0.69→**0.90** e 0.71→**0.22**). *Obrigatório:* `misalignment`. *Proibido:* `looseness` como
diagnóstico prevalente.

**D · `case_tkt_inv_11`** — *"motor CC antigo. O modelo atende?"* O mais barato e o mais duro: a
mutação é **um booleano**. `can_learn_baseline` false→**true**, nota de detecção sintomática
removida, `baseline.state` learning→**established**. *Obrigatório:* afirmar que o baseline é
aprendível. *Proibido:* `sintomát`, `learning`.

Placebos: `collected_at` (A, C) e `models.version` (B, D). **Critério de leitura, declarado antes:**
decisivo muda em 3/4 ou 4/4 **e** placebo não muda em 4/4 → sustentada; decisivo não muda em 3/4+ →
refutada; ambos mudam → ruído; 2/4 → **inconclusivo, e o documento diz isso** em vez de escolher a
metade que agrada.

**Prova.** 12 execuções, 12 concluídas, zero erros. Antes da coleta, uma sonda sem LLM confirmou
contra a API real que as 12 combinações entregam os valores previstos — sem isso, o caso B teria
rodado cego.

| Caso | Nível 1 | Nível 2 | Decisão | Placebo mudou? |
| :--- | :---: | :---: | :--- | :---: |
| A · inv_06 | ✔ | ✔ | orientar → orientar | não |
| B · inv_10 | ✔ | ✔ | orientar → orientar | não |
| C · inv_08 | ✔ | **✘** | agir → agir | não |
| D · inv_11 | ✔ | ✔ | orientar → orientar | não |

**Nível 1: 4/4** — o Investigador leu o campo mutado em todos (`1x` em 6,4; `snr_db=16.5 (req:
12.0)`; `evidence_2x=3.9_vs_ref_0.5`; `can_learn_baseline=true`). **Nível 2: 3/4. Placebo: 0/4.**

Nos casos A e B, os testes de eco, o agente contrariou o usuário sob mutação — de "diagnóstico não
é confiável" para "detecção feita com baseline estabelecido e confiança 0,81"; de "tá péssima" para
"atenderia aos requisitos".

**O caso C é o achado que interessa.** O Investigador escreveu no finding:

> `an_9907.type=misalignment, confidence=0.9, evidence_2x=3.9_vs_ref_0.5`
> `an_9908.type=looseness, confidence=0.22, evidence_subharmonics=0.1_vs_ref_0.2`

A evidência está lá, com os dois números e a inversão de confiança. O Decisor respondeu:

> "Conflito entre diagnóstico automático (desalinhamento, alta confiança) e especialista (base
> solta, baixa confiança) (…) impede uma conclusão segura"

Ele **leu** a assimetria — nomeia "alta" e "baixa confiança" — e ainda assim tratou 0,90 contra
0,22 como conflito irresolvido. No controle, com 0,69 contra 0,71, a mesma conclusão era correta.
Não é a linha "cita/não cita" prevista: é uma quarta situação que o desenho não antecipava. **A
evidência chega em quem decide, e o Decisor não a usa como critério de desempate** — a falha está
na política de decisão, não na leitura nem no handoff. O caso C era o único com desfecho binário e
nomeado, e é o único que falhou.

**Veredito: hipótese sustentada** pelo critério congelado (3/4 no nível 2, 0/4 no placebo). A
evidência **causa** a resposta; o agente não está sendo carregado pelo texto do ticket. E o handoff
entre papéis ficou limpo em **4/4**, o que enfraquece a suspeita de que a compressão em `findings`
perde evidência — primeiro resultado do projeto a medir a arquitetura multiagente.

A consequência do caso C aponta para o prompt do Decisor: 0,90 contra 0,22 não é conflito, e a
política não diz isso em lugar nenhum. Duas correções candidatas, nenhuma testada — nomear no
prompt que diferença grande de confiança resolve conflito, ou fazer o Investigador registrar a
razão entre confianças como fato apurado.

**Limitações.** (1) Estados que a API nunca geraria: os bundles reduzem a incoerência sem eliminá-la
(`can_learn_baseline=true` para motor DC contraria a nota do próprio modelo), e o agente pode
reagir à estranheza em vez de ao campo. **O caso A é exemplo disso:** a mutação move `/baseline` mas
não o `baseline_state` embutido em `/rms`, o agente detectou o conflito e chegou à conclusão
prevista raciocinando sobre um estado impossível — o ✔ de A vale menos que os de B e D. (2)
Verificação por termo é frágil; paráfrase gera falso negativo, e toda falha passou por leitura
manual. (3) Um seed: resultados que dependam da degradação probabilística ficam fora. (4) Quatro
casos, todos de investigação. (5) n = 4 — demonstração de mecanismo, não estimativa de taxa.

---

# EXP-07 — Enxugar o prompt do Supervisor: a economia que custou decisão

**Concluído, hipótese refutada na parte que importa** · `pos-correcao` × `fixed-atual` · 51 pares ·
Rodado e registrado em 2026-09-06

> Reconstruído a posteriori: a bateria rodou como otimização de produção, não como experimento
> desenhado. HARKing, como no EXP-01 — evidência sugestiva, não confirmatória.

**Hipótese.** Remover o `DOMAIN_BRIEF` do prompt do Supervisor reduz o custo **sem custar acurácia
de decisão**.

**Por quê.** O Supervisor não interpreta retorno de API nem redige resposta: só escolhe entre três
papéis sobre evidência já resumida. É o segundo papel mais chamado, e o brief é reenviado inteiro a
cada volta — ~700 tokens por turno sobre ciclo de vida do baseline e envelope probabilístico,
coisas que não mudam a escolha de rota. A predição de custo é quase certa; **a parte falseável é
que a decisão não piore**.

**Método.** Duas mudanças aplicadas juntas no commit `4f16fc7`: (1) `supervisor_prompt` perde o
`DOMAIN_BRIEF` e o contexto de autorização encolhe para uma linha; (2) bloco `_VOZ_AO_CLIENTE`
novo, proibindo nome de campo, identificador interno e enum cru na resposta final. Pareado por
`(caso, seed)`, 51 pares contra a `pos-correcao`: mesmos modelos, `temperature=0`, mesma
`evidence_policy=fixed`, mesmas seeds. **Única variável: o texto dos prompts.** Critério: redução
de custo **sem perda líquida** em `decision_match`.

**Prova.** 51 execuções, **51 concluídas, zero erros** — a primeira bateria completa do projeto sem
uma falha de cota.

| Métrica (n=51) | pos-correcao | fixed-atual | Δ |
| :--- | ---: | ---: | ---: |
| `decision_match` | **48/51 (94,1%)** | 45/51 (88,2%) | **−3** |
| `passou` | 40/51 | 39/51 | −1 |
| estabilidade entre seeds | **17/17** | 15/17 | **−2 casos** |
| tokens (média) | 18.730 | **15.825** | **−15,5%** |
| chamadas de API | 7,90 | **6,80** | −13,9% |
| taxa de repetição | 3,0% | **0,0%** | −100% |
| `evidence_recall` | 0,783 | 0,724 | −7,5% |

A economia aconteceu, e é grande — a hipótese acertou inteiramente na parte previsível. A
discordância mostra o outro lado:

| | fixed-atual: erro | fixed-atual: acerto |
| :--- | ---: | ---: |
| **pos-correcao: erro** | 3 | **0** |
| **pos-correcao: acerto** | **3** | 45 |

Três regressões, **zero correções** — a imagem espelhada do EXP-01. McNemar exato: **p ≈ 0,250**.
TKT-INV-04/`s3` `escalar`→`orientar`; TKT-INV-08/`complete` e `s2` `agir`→`orientar`. **As três
caem em `orientar`** — o atrator que o EXP-01 combateu. O bloco `QUANDO ORIENTAR NÃO BASTA`
continua intacto no prompt do Decisor, e ainda assim o comportamento voltou.

**E não é falha de investigação:** nas três, o `evidence_recall` é **1,00 nas duas fases**, sem
nenhuma query faltante. O agente tinha o mesmo material e resolveu diferente — o que desloca a
causa do Investigador para o Decisor, mesmo tipo de achado do caso C do EXP-06.

A economia também não é uniforme:

| Família | n | pos | fixed-atual | Δ tokens | acerto |
| :--- | ---: | ---: | ---: | ---: | :--- |
| CTX | 9 | 15.525 | 14.310 | −7,8% | 9 → **9** |
| EXE | 15 | 20.021 | 19.132 | −4,4% | 15 → **15** |
| **INV** | 27 | 19.082 | **14.492** | **−24,1%** | 24 → **21** |

Quase toda vem de INV — **e é a única família que perdeu acurácia**. Duas leituras que este
experimento não separa: ou o brief fazia trabalho real nos casos de diagnóstico, ou a regressão vem
do `_VOZ_AO_CLIENTE`, que reordena a redação (e o EXP-01 já mostrou que a ordem entre *decidir* e
*redigir* mexe na decisão).

Os dois casos que voltaram a oscilar entre seeds (TKT-INV-04, TKT-INV-08) são dois dos quatro
instáveis na `baseline` — e são os mesmos que produziram as três regressões. Isso não refuta o
EXP-01: naquela configuração o 17/17 está medido. Mas mostra que é propriedade **daquela versão do
prompt**, não do agente.

**Veredito: refutada na parte falseável.** O custo caiu 15% e a acurácia caiu 5,9 pontos. Para um
agente que executa ações em plataforma industrial, **é uma troca ruim** — por isso o veredito é
refutação apesar de a hipótese ter acertado no custo.

O agente **não foi revertido**: `fixed-atual` é a fase em produção. Manter ou reverter depende de
separar as duas mudanças — **braço A** devolve o `DOMAIN_BRIEF` mantendo o `_VOZ_AO_CLIENTE`,
**braço B** faz o inverso. Se A recuperar as três decisões, o brief fazia trabalho; se B recuperar,
o problema é a reordenação da redação. Enquanto isso não roda, a leitura honesta é: **a produção
decide pior que a versão anterior, e mais barato.**

**Limitações.** (1) HARKing — a bateria rodou como otimização e o critério foi fixado na leitura.
(2) Duas mudanças no mesmo commit: não é possível atribuir a regressão a uma delas, e separá-las
exige um desenho fatorial que não foi feito. (3) n = 3 discordâncias, p ≈ 0,250; o peso do achado
não é estatístico, é o padrão (as três em `orientar`, nos mesmos casos historicamente instáveis,
com recall 1,00). (4) n efetivo ≈ 17, e duas das três regressões são o mesmo caso. (5) **Sem camada
2, e aqui isso pesa:** o `_VOZ_AO_CLIENTE` foi escrito para melhorar a **legibilidade** da
resposta, exatamente o que nenhuma métrica aqui mede — é possível que a resposta tenha ficado
melhor de ler e pior de decidir, e julgar a mudança só por `decision_match` é incompleto. (6)
`evidence_recall` caiu 7,5% no agregado sem que as regressões o expliquem (nelas é 1,00); o que a
queda média significa não foi investigado.

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
