# leitura/ — a leitura de vibração e o agente, por ativo

Uma página por ativo: primeiro o que a API industrial devolve sobre ele, depois o que o
agente decidiu sobre esse mesmo ativo. O eixo é o **ativo**, não o cenário — é assim que
um técnico da planta pensa, e é o que permite dizer, na própria tela, qual cenário aquele
ativo reproduziu.

```bash
make up             # API industrial (:8000) — obrigatória para coletar
make leitura        # recoleta as 3 seeds e serve em :8001/leitura/
make consulta       # o mesmo, com o agente no ar (habilita a consulta ao vivo)
```

## O sistema visual não foi redesenhado

Tokens, escala tipográfica, paddings (`.wrap` = `28px 22px 56px`, `.card` = `16px 18px`),
a geometria do gráfico (760×250, margens 46/84/16/30) e o crosshair vieram do artefato de
referência e estão intactos. As seções novas reusam `.card`, `.chip` e `.spec` — nenhuma
família tipográfica, raio ou padding novo foi introduzido.

Duas exceções deliberadas, ambas registradas em comentário no CSS/JS:

- **`--ink-3` escurecido** nos temas claros (`#84867a` → `#6d6f65`) e um passo no escuro.
  O tom original dava 3.2–3.5:1 sobre as superfícies claras, abaixo dos 4.5:1 de AA, e é
  a cor que carrega rodapé, rótulos de seed e metadados. Mesmo matiz, um passo mais escuro.
- **Tooltip não abre sozinho.** O artefato abria o da última amostra porque tinha um
  gráfico só; com três empilhados, três tooltips abertos viram ruído. O ponto final
  continua destacado no próprio SVG.

## Experimentos

O botão **🧪 Experimentos**, ao lado da configuração, abre as cinco hipóteses que o projeto
testou: o que cada uma afirmou, o veredito, e onde reproduzi-la nesta mesma página.

Os números **não estão no JS**. `coleta/montar_experimentos.py` gera
`dados/experimentos.json` a partir dos traces em disco, e o que não é derivável fica marcado
como *veredito transcrito do documento*. A distinção é visível na tela porque um número que
só existisse no JS seria um número que ninguém pode auditar contra o repositório.

```bash
make experimentos   # regenera dados/experimentos.json (roda junto com make leitura)
make exp07          # roda o EXP-06 (alvo mantém o nome exp07): 12 execuções (CASOS="A D" roda só a metade prioritária)
```

O EXP-06 é o único pré-registrado, e a aba mostra o detalhe dele: o placar de três números
(o Investigador leu, o Decisor usou, o placebo mudou) e os quatro casos com a mutação
aplicada, o critério que julgou cada um e a justificativa que o Decisor escreveu no braço
mutado. O caso C aparece destacado porque falhou — e o teste
[`tests/test_experimentos.py`](../tests/test_experimentos.py) trava esse ✘: transformá-lo em
✔ exige nova coleta, não um critério mais frouxo.

## Configuração, temas e dicas

O cabeçalho tem um botão só — **⚙ Configuração** —, que abre um painel sobre a página com
o fundo desfocado. Três seções: aparência, política de evidência e metodologia. Tema e
paleta estavam disputando o canto superior com a procedência dos dados; aqui convivem com
o que explicam.

O padrão é a paleta do artefato (bege/terracota); `Paleta Tractian` troca para o azul da
marca (`#1461b8`) sobre branco/cinza-frio, sem mudar a geometria. Claro/escuro é eixo
independente. As duas escolhas persistem em `localStorage`, e os quatro cruzamentos passam
AA. A marca no topo é SVG inline, não imagem: herda `currentColor` e não carrega o fundo
branco que o arquivo original traz — num tema escuro ele viraria um retângulo aceso.

**Nenhum `title` do navegador.** Todo hover usa a dica própria da página, com o mesmo
desenho dos cards. O `title` nativo espera ~1 s, some sozinho, ignora o tema e quebra
linha onde quer. Abrem dica: o custo de cada seed (comparação completa com o baseline), as
notas do comitê (o raciocínio do juiz), e **as barras de papel** — ali cada papel mostra o
que apurou, quantos tokens gastou e quais rotas consultou. O achado do Investigador vem
como `chave=valor (fonte)` repetido; a dica quebra isso em linhas com o valor destacado,
em vez de um parágrafo de símbolos.

## As três seeds são o argumento, não decoração

`s2` e `s3` não são repetição cosmética. A API decide o modo de resposta por
`hash(seed | recurso | categoria)`, então **o mesmo ativo vem completo numa seed e
indisponível noutra**. No `asset_M101`, por exemplo: `complete` devolve 30 amostras, `s2`
devolve `unavailable`, `s3` devolve `partial` sem série. Dos 26 ativos, **19 mudam de modo
entre seeds**; entre os 10 que têm cenário, **9 degradam em pelo menos um recurso**.

Quando não há série, o card diz o que faltou em vez de desenhar um gráfico vazio — a
ausência é o dado.

### Um card por leitura, não por seed

Os **valores** de RMS vêm do histórico do ativo (`rms.parquet`) e nunca mudam por seed —
`_apply_mode` devolve o payload intacto quando o modo é `complete`. A seed decide a
**disponibilidade**, não o conteúdo. Duas seeds em modo `complete` devolvem, por
construção, exatamente a mesma série.

E `complete` é o resultado mais provável: a distribuição de modos da API é 60% `complete`,
15% `partial`, 10% `inconclusive`, 8% `conflict`, 7% `unavailable`. Então empilhar três
gráficos por ativo desenhava o mesmo gráfico duas ou três vezes na maioria dos casos.

Por isso o eixo do card é a **leitura**, não a seed: `gruposDeSeeds` junta as seeds cuja
resposta é idêntica (modo, notas, estado do baseline, referência, alarme e amostras) e o
título traz todas elas — `seeds complete · s2 · s3`. Uma linha no card diz que as seeds
foram agrupadas, para que três nomes no título não se leiam como três execuções perdidas.

Onde a leitura difere, o grupo se separa sozinho e cada card volta a dizer o que aquela
seed entregou — `partial`, `inconclusive`, `unavailable`, com o motivo no lugar do
gráfico. **A degradação continua visível; o que sai é só a repetição.**

Sobre os 26 ativos, isso leva os cards de RMS de 78 para **47**: 7 ativos têm uma leitura
só nas três seeds, 17 têm duas, e 2 mantêm as três separadas. O `asset_M101` é o caso
extremo — `complete`, `unavailable` e `partial`, um card cada.

O RMS é o único recurso agrupado assim, porque é o único desenhado três vezes. Espectro,
qualidade e análises seguem exibidos na seed de referência, e o card "Como ler as três
seeds" continua dizendo quais dos quatro recursos degradam neste ativo.

O card "Como ler as três seeds" diz, por ativo, quais dos quatro recursos degradam.

### E as decisões iguais também não

Os 17 casos decidem igual nas 3 seeds. Isso **não** é contaminação — três evidências:

1. O agente nunca vê o gabarito. `run_case` recebe só `id`, `ticket_id`, `company_id`,
   `user_id`, `asset_id` e `message`; `expected_path` e `decisoes_aceitas` ficam fora.
2. O cache de consultas (`_query_cache`) nasce no `ApiClient` de cada `run_case`, dentro de
   um `with`. Não atravessa execuções.
3. Custo e trajetória **variam** entre seeds — CEN-02 gastou 18.892 / 32.825 / 18.990
   tokens em 8 / 15 / 8 chamadas. Execuções idênticas não fariam isso.

Decidir igual com dado degradado é o resultado que a Camada 3 existe para medir.

## Cobertura é explícita

A bateria tem **17 casos sobre 16 cenários** (CEN-07 tem dois tickets: TKT-EXE-12 e
TKT-INV-09) e cobre **10 dos 26 ativos**. Os outros 16 aparecem na lista normalmente, com
a leitura técnica completa e um vazio honesto na seção do agente — mais o botão de
consulta ao vivo. Esconder os não cobertos faria a lista mentir sobre a cobertura.

Na lista lateral, `N cen.` marca quantos casos passaram por aquele ativo.

## Como um desfecho é lido

Quatro categorias, com a mesma regra de domínio do painel de origem — escalar é desfecho
correto e nunca cai em vermelho:

| leitura | quando |
|---|---|
| passou | decisão aceita e trajetória do gabarito cumprida |
| decisão certa, N consultas esperadas não feitas | a decisão bate, o caminho não |
| decisão divergente do gabarito | decisão fora das aceitas |
| não concluiu a execução | o grafo parou antes do fim |

A contagem de passos usa **passos do gabarito cumpridos**, não total de consultas: "7 de 4"
lia como erro quando 7 era o total feito e 4 o previsto.

## Consulta ao vivo, no próprio ativo

O formulário pergunta ao agente sobre o ativo aberto, com sugestões derivadas do estado
real dele (RMS acima do alarme, baseline invalidado, dado desatualizado). O seletor de
usuário lista primeiro quem é da empresa do ativo — é o `user_id` que determina a permissão
real na API, e um usuário de outra empresa não enxerga o ativo.

Se o papel do usuário não autoriza a ação, o **403 aparece na trajetória** com a explicação
de que é o enforcement funcionando (ADR 0003), não falha do agente.

A nota da consulta é **sintética** (ADR 0007) e nunca entra nas métricas dos 17 casos: um
caso tem gabarito escrito à mão, uma pergunta livre não. O comitê de juízes vai desligado
(`julgar: false`) para não gastar chamadas de LLM extras numa demonstração.

Terminada a execução, o resultado traz um rodapé com duas coisas: registrar aquela
consulta como cenário do ativo e — se a chave estiver ligada — o veredito humano sobre a
decisão. As duas seções abaixo cobrem cada uma.

Não há streaming: o servidor devolve a execução inteira ao terminar. Os selos de papel
acendem em cadência estimada e o resultado real substitui tudo ao chegar — a mesma decisão
registrada na spec das quatro batidas.

### Quanto tempo isso leva de verdade

Medido sobre as consultas já gravadas: **mediana de 74 s, p90 de 179 s, máximo de 275 s**.
A bateria dos cenários é mais rápida (mediana 44 s, p90 90 s), porque as perguntas são mais
estreitas. A página declara a mediana e avisa quando a execução passa dela.

O `fetch` tem corte em 6 minutos. Abortar no cliente **não** cancela a execução no servidor:
ela termina e fica gravada em `evaluation/results/consultas/`. A mensagem de timeout diz isso
— quem esperou três minutos precisa saber que o trabalho não se perdeu.

## Cenários registrados: os 16 ativos sem gabarito param de ser um vazio

Dos 26 ativos, 10 têm cenário da bateria. Nos outros 16 a seção do agente é um vazio
honesto — e um botão de consulta. **Registrar um cenário** é o que faz esse botão deixar
rastro: quem executa uma consulta pode dar um nome a ela, e a partir daí ela aparece na
página daquele ativo para quem abrir depois.

São três degraus, e a diferença entre eles é quem escreveu o gabarito:

| degrau | onde mora | quem vê | gabarito | entra nas métricas |
|---|---|---|---|---|
| consulta livre | `evaluation/results/consultas/` | quem executou | LLM, a partir da mensagem | não |
| **cenário registrado** | o mesmo arquivo, com `cenario.nome` | quem abre o ativo | LLM | **não** |
| caso de referência | `tractian/agent-input/cases.json` + `eval/` | todos | humano, antes da execução | sim |

Registrar move do primeiro para o segundo degrau — muda **quem vê**, não a classe de
evidência. O terceiro degrau exige alguém escrevendo `root_question` e `expected_path` à
mão, e isso não acontece por um clique. É a fronteira do ADR 0007, e é estrutural: o
registro continua no diretório que `runner/cli.py` não lê, `resumo_consulta` carrega
`comparavel_com_cenarios: false` no próprio payload, e
`tests/test_consulta.py::test_registrar_cenario_nao_escreve_fora_do_diretorio_de_consultas`
falha se registrar passar a criar arquivo em outro lugar.

Remover da lista é reversível e não apaga nada: `DELETE .../cenario` zera o nome, o trace
continua gravado. Apagar uma execução que custou tokens porque alguém errou o nome seria
caro pelo motivo errado.

Isto é também o caminho pelo qual o conjunto de casos cresce pelo uso, em vez de crescer
por alguém escrever cenário à mão — que é a resposta direta à limitação de *n* pequeno
declarada em [`SOLUTION.md`](../../SOLUTION.md) §8.

## Retorno humano: a única nota que não vem de LLM

Em **⚙ Configuração → Retorno humano** há uma chave, desligada por padrão. Ligada, cada
consulta ao vivo termina com a pergunta *a decisão do agente está correta?* — sim/não, mais
uma justificativa opcional. Fica gravada junto da consulta, em `veredito_humano`.

Três decisões que não são de layout:

- **Vem depois da resposta**, nunca antes. Julgar antes de ler não é julgar.
- **Não volta para o agente.** No instante em que uma nota realimenta o sistema que ela
  mede, deixa de medi-lo — vale para o veredito humano e vale para o comitê de juízes.
  Nota baixa aqui é achado para investigar, não gatilho de reexecução.
- **É uma escolha, não um padrão.** Quem abre a página para ler a vibração de um ativo não
  está avaliando agente nenhum, e um formulário de avaliação depois de cada resposta seria
  ruído. Quem está avaliando liga a chave.

O motivo de existir é a segunda ressalva da seção seguinte: o comitê ordena execuções entre
si sem estar aferido contra ninguém. Um rótulo humano por consulta é o insumo que falta
para calibrá-lo — e é gratuito em tokens, ao contrário de tudo o mais nesta página.

## Comitê de juízes: o que a página mostra, e o que ela ressalva

As notas por dimensão (honestidade, causa-raiz, justificativa) aparecem na coluna de cada
seed, com o raciocínio do juiz no `title`. Duas ressalvas viajam junto, e não são decorativas:

- **Hoje só a fase `baseline` foi julgada.** As 35 execuções com veredito são todas da
  versão anterior do agente; a `pos-correcao`, que é a fase exibida, ainda não passou pelo
  comitê. Cada nota carrega a marca `fase baseline`. Isso não foi escolha: `julgar.py`
  não filtrava fase e a fila, na ordem do bundle, servia `baseline` primeiro. Corrigido —
  `make painel-julgar` agora julga `pos-correcao` por padrão, e `FASE=baseline` é
  explícito (ver [`../README.md`](../README.md#comitê-de-juízes-camada-2-via-openrouter)).
- **O juiz não foi calibrado contra anotação humana.** A nota ordena execuções entre si;
  não mede acerto. Colocá-la ao lado dos 94,1% de acurácia sem essa ressalva sugeriria que
  são a mesma classe de evidência — e não são: a acurácia é medida contra gabarito escrito
  à mão.

## Custo: o delta contra a fase anterior

Cada coluna de seed mostra o custo com o delta contra **a mesma combinação caso × seed** na
fase `baseline`, em verde quando economizou. O `title` abre a comparação completa (tokens,
chamadas de LLM, consultas de API, decisão antes e depois).

A média agregada esconde que o ganho não foi uniforme: CEN-14 caiu de 33.872 para 20.143
tokens (−40%), enquanto vários casos subiram alguns por cento.

## Consultas além do gabarito: o que os números dizem

Medido na fase `pos-correcao`: **7,5 GETs por execução contra 2,9 previstos** pelo gabarito
— 251 consultas extras em 51 execuções (4,9 por execução). Vale separar três causas antes
de tratar tudo como desperdício:

| causa | volume | é desperdício? |
|---|---|---|
| `GET /users/me` | 51 de 51 | **não** — o grafo o chama uma vez para estabelecer o contexto de autorização. O gabarito descreve a investigação técnica e não o lista. A trajetória o marca como "contexto de permissão", não como extra. |
| política de evidência `fixed` | ~4 por execução | **por desenho** — `_EVIDENCE_FIXED` manda apurar sempre os quatro (`get_asset`, `get_baseline`, `get_data_quality`, `get_rms`), inclusive quando a pergunta é procedimental. |
| repetições | 19 no total | **sim** — chamada idêntica repetida é desperdício puro. É o único item dos três que não tem defesa. |

O caminho óbvio para reduzir já existe e está implementado: `EVIDENCE_POLICY=conditional`
faz o Investigador apurar os quatro só em perguntas de diagnóstico, e apenas
`baseline`+`rms` em perguntas conceituais ou procedimentais.

**E já foi medido duas vezes, com resultados opostos.**

O [EXP-02](../../docs/EXPERIMENTOS.md#exp-02-política-de-evidência-apurar-sempre-vs-apurar-sob-demanda) comparou as duas em 6
pares e viu `conditional` gastando 8% menos, com decisão idêntica. O
[EXP-06](../../docs/EXPERIMENTOS.md#exp-05-política-de-evidência-segunda-medição) repetiu
com 18 pares e as três famílias de caso — e **inverteu o sinal de custo**:

| | `fixed` | `conditional` |
|---|---:|---:|
| tokens | 14.449 | **16.353** (+13%) |
| chamadas de API | 5,56 | 6,17 (+11%) |
| taxa de repetição | **0,000** | 0,034 |
| decisão correta | 18/18 | **18/18** |
| decisões divergentes | — | **0 de 18** |

A causa aparente é a repetição, que sai de zero: sem a lista fixa dos quatro pilares, o
Investigador perde o critério de parada e reconsulta a mesma rota para decidir que
terminou. A instrução `fixed` funciona menos como exigência de completude e mais como
**condição de parada** — o que o EXP-02, medindo só volume em 2 casos, não separava.

O que os dois experimentos concordam: **a política afeta custo, não desfecho**. `fixed`
continua sendo o padrão, e a conclusão firme depende da bateria completa (51 pares), que
a cota diária da Groq ainda não permitiu fechar.

## Rodar a bateria inteira em `conditional`

O EXP-02 usou 2 casos × 3 seeds. Para as 51 execuções da bateria completa na outra
política, com a comparação aparecendo na página como uma terceira fase:

```bash
make up                                       # API industrial no ar
make eval-politica POLITICA=conditional       # 17 casos × 3 seeds, fase gravada
python solution/painel/recalcular_csv.py --fase conditional
make painel-dados
FASE=conditional make leitura-dados           # a página passa a exibir essa fase
```

`make eval-politica` define `EVIDENCE_POLICY` e `RUN_PHASE` juntos, e roda com
`--skip-judges` (o comitê gasta LLM à parte; use `make painel-julgar` depois, se quiser).

### A fase agora é gravada no trace

Antes, a fase era **inferida** juntando `(case_id, seed, token_usage.total_tokens)` contra
`resultados_avaliacao.csv` — uma assinatura empírica que quebra quando duas execuções do
mesmo caso e seed empatam em tokens, e obrigava a editar `FASES` no `build_bundle.py` a
cada bateria nova.

Agora `RUN_PHASE` no ambiente vira o campo `fase` do trace
([`agent/app/trace.py`](../../agent/app/trace.py)), junto com `evidence_policy`. O
`build_bundle` casa direto por `(case_id, seed, fase)` quando o campo existe, e só cai na
junção por tokens para os traces gravados antes disso. As fases deixaram de ser uma tupla
fixa: `fases_de()` lê o que está presente e mantém `baseline` e `pos-correcao` na frente,
para que a leitura "antes → depois" não dependa de ordenação alfabética.

O script continua **abortando** em ambiguidade em vez de escolher uma — mascarar isso
produziria um painel confiante e errado.

### Alternar entre as baterias na própria página

`montar_indice.py` gera **um índice por fase** (`agente-<fase>.json`) mais um
`fases.json` com o catálogo. No painel **⚙ Configuração → Política de evidência**, clicar
num card carrega a bateria que rodou aquela política — sem comando no terminal. A escolha
persiste em `localStorage`.

Quando a fase exibida não é a produção, a página diz isso em dois lugares: uma etiqueta
`fase <nome>` no divisor da seção do agente e um aviso logo abaixo. Sem eles, um
experimento incompleto se leria como resultado corrente.

Execuções que não chegaram a rodar (cota do provedor esgotada) aparecem como **"não
executada (cota do provedor)"**, não como falha do agente — a distinção importa: das 51
da fase `conditional`, 33 são disso.

O padrão exibido continua sendo `pos-correcao`; `FASE` e `FASE_ANTERIOR` seguem valendo
para escolher qual índice vira o `agente.json` padrão:

```bash
make leitura-dados                       # padrão: pos-correcao
FASE=conditional make leitura-dados      # abre já na bateria conditional
```

## Arquivos

| arquivo | papel |
|---|---|
| `index.html` | esqueleto: cabeçalho, lista lateral, painel, rodapé |
| `leitura.css` | tokens dos dois temas + classes da seção do agente |
| `leitura.js` | gráfico (do artefato), seções, consulta ao vivo |
| `../coleta/coletar_ativos.py` | busca os 26 ativos nas 3 seeds → `dados/ativos.json` |
| `../coleta/montar_indice.py` | cruza o bundle por `asset_id` → `dados/agente.json` |

A junção entre os dois lados é `operacao.asset_id`: cada execução do agente aconteceu
sobre um ativo concreto, na mesma seed em que a API degradou aquele ativo.
