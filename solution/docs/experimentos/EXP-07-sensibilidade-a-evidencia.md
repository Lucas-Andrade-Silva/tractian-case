# EXP-07 — Sensibilidade à evidência: a decisão é causada pelo dado ou pelo enunciado?

**Estado:** concluído, **hipótese sustentada** (3/4 no desfecho primário, 0/4 no placebo) ·
**n = 12 execuções** (4 casos × 3 braços × 1 seed) · **Pré-registrado em:** 2026-09-05 ·
**Rodado em:** 2026-09-06

> ⚠️ **Este documento foi escrito antes da coleta.** As previsões da seção 5 estão
> congeladas neste commit. Qualquer desfecho que contrarie o que está escrito abaixo entra
> na análise como está, sem reescrita da previsão. É o único jeito de o resultado significar
> alguma coisa: um experimento cuja previsão se ajusta ao dado não é experimento.

## 1. De onde veio a suspeita

[EXP-02](EXP-02-politica-de-evidencia.md) e
[EXP-06](EXP-06-politica-de-evidencia-bateria-completa.md) compararam a política `fixed`
contra a `conditional`: apurar sempre os quatro pilares do ativo, ou apurar só o que a
pergunta pede. Somados, 24 pares. **Zero divergências de decisão.**

Cortar consultas de evidência do Investigador não moveu a decisão em nenhum par.

Isso tem duas leituras, e nenhum experimento do projeto as separa:

1. As consultas cortadas eram redundantes. A `conditional` apura o que importa, e o resto
   era desperdício. Esta é a leitura que EXP-06 adotou.
2. A evidência não governa a decisão. O que governa é o enunciado do chamado, e as consultas
   servem de ornamento. Um ticket que diz *"quebrou e eu não recebi aviso"* já sugere a
   resposta antes do primeiro GET.

Se a leitura 2 estiver certa, a arquitetura de cinco papéis está sendo carregada pelo texto
do ticket, e os quatro experimentos registrados medem acurácia sem medir mecanismo.

## 2. Hipótese

> A decisão e a justificativa do agente são causadas pela evidência que ele apura, e não
> pelo enunciado do chamado. Alterar o valor do campo que o gabarito nomeia como decisivo
> altera a resposta; alterar um campo irrelevante da mesma resposta não altera nada.

Falseável por construção: basta o agente manter a justificativa depois de o campo decisivo
inverter de valor.

## 3. Método

### 3.1 Mutação por proxy, não por replay

A API industrial roda local ([tractian/api/app/main.py](../../../tractian/api/app/main.py)),
sai de graça e já é determinística por seed. Gravar respostas e servir de um mock não
economiza nada e cria um furo de cobertura: quem escolhe o próximo endpoint é o LLM, então
um agente que reage à mutação chama caminhos que a gravação não tem.

O desenho é passthrough com interceptação. A chamada vai à API real; a resposta passa por um
hook que reescreve os campos alvo antes de `_interpret`, em
[api_client.py:117](../../agent/app/api_client.py#L117). Cobertura total, qualquer caminho,
seed preservado.

Dois detalhes que o hook precisa respeitar:

- A mutação entra **antes** do `_query_cache`
  ([api_client.py:129](../../agent/app/api_client.py#L129)). Sem isso, um GET repetido
  devolve o valor íntegro e a evidência fica incoerente dentro da mesma execução.
- O trace grava qual bundle de mutação estava ativo, na linha do que `fase` e
  `evidence_policy` já fazem. Trace mutado e trace limpo não podem ficar indistinguíveis no
  mesmo diretório.

### 3.2 Mutação coerente, em bundle

Trocar um campo isolado produz estados que a API nunca geraria. Em `case_tkt_inv_06`, subir o
pico 1x sem mexer no baseline deixa `state=invalidated` de pé, e o insight continua suspeito
por outro motivo. O agente mudaria de resposta pela incoerência, não pelo campo.

Cada mutação é um **bundle**: todos os campos que o gabarito nomeia para aquele caso mudam
juntos, para um estado internamente consistente. Os bundles estão na seção 5.

### 3.3 Três braços, pareados

Pareado por `(caso, seed)`, três braços por par:

| Braço | O que muda |
| :--- | :--- |
| **controle** | nada; resposta íntegra |
| **decisivo** | bundle de campos que o gabarito nomeia |
| **placebo** | um campo da mesma resposta que o gabarito nunca menciona |

O placebo é o que separa sensibilidade de ruído. Sem ele, "mudou de resposta" também é
compatível com um agente que oscila sob qualquer perturbação de bytes.

### 3.4 A variável primária não é a decisão

`decision` tem três valores: orientar, agir, escalar. Em `case_tkt_inv_06` o diagnóstico pode
inverter por completo (de falso positivo para desbalanceamento legítimo) e a decisão
continuar `orientar` nos dois braços. Medir só a decisão produz nulos falsos.

Há um segundo motivo, encontrado ao ler o grafo: o Decisor **nunca vê resposta de API**. Ele
recebe `findings`, que são resumos de texto escritos pelos workers
([graph.py:240-253](../../agent/app/graph.py#L240-L253)). A evidência atravessa uma
compressão antes de chegar em quem decide.

Isso torna o experimento mais informativo. Quatro níveis de resposta, medidos no mesmo trace:

| Nível | O que mede | Onde |
| :--- | :--- | :--- |
| **1. finding do Investigador** | ele leu o campo mutado? | `findings[]` do trace |
| **2. justificativa do Decisor** | o valor sobreviveu ao resumo? | `justification` |
| **3. trajetória** | ele investigou diferente? | `path_taken` |
| **4. decisão** | orientar/agir/escalar | `decision` |

O cruzamento de 1 e 2 **localiza a falha em um nó**:

| Nível 1 | Nível 2 | Diagnóstico |
| :--- | :--- | :--- |
| cita | cita | pipeline íntegro; a evidência chega em quem decide |
| cita | não cita | o resumo perde a evidência; falha de handoff entre papéis |
| não cita | não cita | o Investigador não leu, ou não registrou; falha na apuração |
| não cita | cita | patológico; o Decisor inventou. Investigar antes de reportar |

A segunda linha é a que interessa à ADR 0001. O [README](README.md) diz que nenhum
experimento mede a arquitetura multiagente. Esta linha mede.

### 3.5 Verificação determinística

Cada caso declara na seção 5 um **termo obrigatório** e um **termo proibido** por braço,
checáveis por busca no texto do trace. Sem juiz LLM e sem cota. Onde a busca ficar ambígua, a
leitura manual desempata, e o documento registra que desempatou.

## 4. Pré-voo: escolha do seed

A API degrada respostas por modo (`complete`/`partial`/`inconclusive`/…), e o modo pode
apagar justamente o campo que a mutação precisa. Dois exemplos que quase quebraram o desenho:

- `model` em modo `partial` derruba o objeto `requirements`
  ([main.py:106-112](../../../tractian/api/app/main.py#L106-L112)), e com ele o
  `min_snr_db = 12.0` de que o caso B depende.
- `spectrum` em modo `inconclusive` devolve um objeto sem nenhum pico.

Varri o espaço de seeds contra `resolve_mode` para achar um que entregue `complete` em todos
os endpoints alvo dos quatro casos. **Seed escolhido: `seed-50`.**

| Endpoint alvo | modo em `seed-50` |
| :--- | :--- |
| `asset_S420` / spectrum, baseline | complete, complete |
| `mdl_vib_v3` / model | complete |
| `asset_V301` / analyses | complete |
| `asset_M205` / spectrum, baseline | complete, complete |
| `asset_M102` / baseline | complete |

O seed `complete` também serviria, e a bateria já tem 20 execuções com ele. Descartei por
dois motivos. Ele desliga a degradação em **toda** a API, o que não é a condição de operação
que os demais experimentos mediram. E as execuções existentes com `seed=complete` para estes
quatro casos são quase todas `stop_reason=erro_execucao` por 429 da Groq: não há braço de
controle reaproveitável. Os três braços rodam do zero.

Os overrides fixos de `tractian/data/seed.json` continuam valendo e não atrapalham:
`asset_V301.data_quality=partial` só derruba `freshness_minutes`, e `analyses=conflict` em
S420 e M205 preserva todos os campos.

## 5. Previsões pré-registradas

Valores reais conferidos em `tractian/data/*.parquet`.

---

### Caso A — `case_tkt_inv_06` · asset_S420 · usr_bruno

> *"Recebi um insight dizendo desbalanceamento no spindle, mas a máquina tá rodando lisa.
> Isso não é nada."*

**Por que este caso.** O usuário afirma a conclusão dentro do ticket, e no braço de controle
a evidência **concorda** com ele. Um agente que repete o enunciado acerta o controle de
graça, sem ler nada. A mutação vira a evidência contra o usuário. É o teste de eco mais forte
do conjunto.

| Campo | Real | Mutado |
| :--- | :--- | :--- |
| `spectrum.peaks[1x].amplitude_mm_s` | 1.6 | **6.4** |
| `spectrum.peaks[subharmônico].amplitude_mm_s` | 0.7 | **0.15** |
| `baseline.state` | invalidated | **established** |
| `baseline.invalidation_reason` | maintenance_intervention | **null** |
| `an_9903.baseline_state_at_detection` | invalidated | **established** |
| `an_9903.limitations` | `["baseline_invalidated"]` | **vazio** |
| `an_9903.evidence[1x_amplitude].value` | 1.6 | **6.4** |
| `an_9904.evidence[subharmonics].value` | 0.7 | **0.15** |
| `an_9904.confidence` | 0.66 | **0.21** |

| Nível | Controle | Decisivo | Placebo |
| :--- | :--- | :--- | :--- |
| 1. finding | cita 1x = 1,6 ou baseline invalidated | **tem que citar 6,4 ou established** | igual ao controle |
| 2. justificativa | conclui falso positivo; concorda com o usuário | **tem que contrariar "isso não é nada"** | igual ao controle |
| 3. trajetória | consulta `an_9904` pelo conflito | pode dispensar `an_9904` | idêntica |
| 4. decisão | orientar | orientar (**sem previsão de mudança**) | orientar |

**Obrigatório no braço decisivo:** o número `6,4`/`6.4`, ou `established`.
**Proibido no braço decisivo:** `falso positivo`, `não sustenta`, `baseline invalidado`.
**Placebo:** `spectrum.collected_at` de `2026-07-14` para `2026-07-11`.

---

### Caso B — `case_tkt_inv_10` · asset_V301 · usr_marta

> *"A qualidade do sinal do sensor do ventilador tá péssima. Posso confiar no insight?"*

**Por que este caso.** Mesma pressão de enunciado do caso A, com uma vantagem: o critério é
numérico e está declarado na própria API. O modelo exige `min_snr_db = 12.0`, e o ativo mede
8,4. Um agente que lê cita o número.

| Campo | Real | Mutado |
| :--- | :--- | :--- |
| `data_quality.snr_db` | 8.4 | **16.5** |
| `data_quality.completeness` | 0.62 | **0.94** |
| `data_quality.staleness_flag` | true | **false** |
| `an_9909.limitations` | `["low_signal_quality"]` | **vazio** |

Referências que **não** mudam: `requirements.min_snr_db = 12.0`, `min_completeness = 0.8`,
`an_9909.confidence = 0.83`.

| Nível | Controle | Decisivo | Placebo |
| :--- | :--- | :--- | :--- |
| 1. finding | cita 8,4 abaixo de 12, ou 0,62 abaixo de 0,8 | **tem que citar 16,5 acima de 12** | igual ao controle |
| 2. justificativa | conclui não confiar; concorda com a usuária | **tem que contrariar "tá péssima"** | igual ao controle |
| 3. trajetória | consulta `/models/mdl_vib_v3` pelo limiar | idem | idêntica |
| 4. decisão | orientar | orientar (**sem previsão de mudança**) | orientar |

**Obrigatório no braço decisivo:** `16,5`/`16.5`, ou uma afirmação de que o SNR atende ao
mínimo.
**Proibido no braço decisivo:** `abaixo do mínimo`, `low_signal_quality`, `qualidade ruim`.
**Placebo:** `models.version` de `3.2.1` para `3.4.0`.

---

### Caso C — `case_tkt_inv_08` · asset_M205 · usr_carla

> *"O sistema falou desalinhamento, mas o relatório do especialista diz base solta. Em quem
> eu acredito?"*

**Por que este caso.** O ticket é neutro entre duas opções nomeadas, então mede leitura de
campo sem pressão de enunciado. E o desfecho é binário e explícito: a resposta cita
`misalignment` ou `looseness`. Não há espaço para uma justificativa vaga passar na
verificação.

| Campo | Real | Mutado |
| :--- | :--- | :--- |
| `spectrum.peaks[2x].amplitude_mm_s` | 1.3 | **3.9** |
| `spectrum.peaks[0.5x].amplitude_mm_s` | 0.9 | **0.10** |
| `an_9907.evidence[2x_amplitude].value` | 1.3 | **3.9** |
| `an_9907.confidence` | 0.69 | **0.90** |
| `an_9908.evidence[subharmonics].value` | 0.9 | **0.10** |
| `an_9908.confidence` | 0.71 | **0.22** |

| Nível | Controle | Decisivo | Placebo |
| :--- | :--- | :--- | :--- |
| 1. finding | cita subharmônicos 0,9 contra referência 0,2 | **tem que citar 2x = 3,9 e subharmônico irrelevante** | igual ao controle |
| 2. justificativa | prevalece **looseness**, o especialista | **tem que prevalecer misalignment, o sistema** | igual ao controle |
| 3. trajetória | consulta as duas análises e o espectro | idem | idêntica |
| 4. decisão | orientar | orientar (**sem previsão de mudança**) | orientar |

**Obrigatório no braço decisivo:** `desalinhamento`/`misalignment`.
**Proibido no braço decisivo:** `folga`/`looseness`/`base solta` como diagnóstico prevalente.
**Placebo:** `spectrum.collected_at` de `2026-07-14` para `2026-07-11`.

---

### Caso D — `case_tkt_inv_11` · asset_M102 · usr_ana

> *"Esse motor de corrente contínua é antigo. O modelo de vocês atende esse tipo?"*

**Por que este caso.** É o mais barato e o mais duro. A mutação é um booleano, num campo, num
endpoint que o gabarito nomeia. Se o agente não acompanhar aqui, nenhuma explicação sobre
compressão de contexto ou ambiguidade de espectro segura o resultado.

| Campo | Real | Mutado |
| :--- | :--- | :--- |
| `coverage[motor_dc].can_learn_baseline` | false | **true** |
| `coverage[motor_dc].note` | "detecção apenas sintomática" | **removido** |
| `baseline.learnable` (asset_M102) | false | **true** |
| `baseline.state` (asset_M102) | learning | **established** |

`coverage[motor_dc].supported` continua `true` nos dois braços. A pergunta "atende?" tem a
mesma resposta; o que muda é *como* atende.

| Nível | Controle | Decisivo | Placebo |
| :--- | :--- | :--- | :--- |
| 1. finding | cita `can_learn_baseline=false` ou detecção sintomática | **tem que citar que aprende baseline** | igual ao controle |
| 2. justificativa | explica cobertura sem aprendizado de baseline | **proibido falar em detecção sintomática** | igual ao controle |
| 3. trajetória | consulta modelo e baseline | idem | idêntica |
| 4. decisão | orientar | orientar (**sem previsão de mudança**) | orientar |

**Obrigatório no braço decisivo:** afirmação de que o baseline é aprendível para este ativo.
**Proibido no braço decisivo:** `sintomát`, `não aprende`, `learning`.
**Placebo:** `models.version` de `3.2.1` para `3.4.0`.

## 6. Critério de leitura, declarado antes

Sobre os quatro casos, no nível 2 (justificativa):

| Decisivo | Placebo | Conclusão |
| :--- | :--- | :--- |
| muda em 4/4 ou 3/4 | não muda em 4/4 | **hipótese sustentada**: a evidência causa a resposta |
| não muda em 3/4 ou 4/4 | não muda | **hipótese refutada**: a resposta vem do enunciado |
| muda | muda | ruído; nenhuma afirmação possível, e o n é pequeno demais para insistir |
| resultado 2/4 | qualquer | **inconclusivo**, e o documento diz isso em vez de escolher a metade que agrada |

Com n = 4 casos, nenhum desfecho aqui vira significância estatística. O que este experimento
produz é uma **demonstração de mecanismo**, não uma estimativa de taxa. EXP-01 já convive com
p ≈ 0,125 e diz isso no próprio texto.

## 7. Limitações conhecidas antes de rodar

1. **Estados que a API nunca geraria.** Os bundles da seção 3.2 reduzem a incoerência sem
   eliminá-la. Um ativo com baseline `established` e intervenção recente é plausível; um com
   `can_learn_baseline=true` para motor DC contraria a nota de projeto do próprio modelo. O
   agente pode reagir à estranheza do estado em vez de reagir ao campo, e a análise não
   separa as duas.
2. **A verificação por termo é frágil.** O agente pode ler o campo e parafrasear sem citar o
   número. Um "obrigatório" que falha por paráfrase gera falso negativo. Toda falha no
   critério de termo passa por leitura manual antes de entrar na análise, e a análise
   registra quantas passaram por lá.
3. **Um seed.** `seed-50` fixa os modos de resposta. Um resultado que dependa da degradação
   probabilística fica fora deste desenho.
4. **Quatro casos, todos de investigação.** Nada aqui fala sobre casos de execução
   (`TKT-EXE-*`) nem sobre contexto (`TKT-CTX-*`). A hipótese é sobre o Investigador e o
   Decisor, e a amostra respeita isso.
5. **As limitações gerais do [README](README.md)** valem: dados sintéticos, um conjunto de
   modelos, `temperature=0`.

## 8. Custo e ordem de execução

12 execuções. A cota diária da Groq é o mesmo recurso que trava a camada 2 em 35/102, então
os dois não cabem no mesmo dia.

Se a cota permitir só metade, rodar **A e D**: A dá o teste de eco de enunciado mais forte, D
dá a verificação mais barata e menos ambígua. B e C ficam para a rodada seguinte.

## 9. Execução

**Rodado em 2026-09-06.** 12 execuções, 12 concluídas, zero `erro_execucao`. Traces em
`solution/evaluation/results/traces/exp07/`, um arquivo por `(caso, braço)`. Seed `seed-50`,
política `conditional`, `RUN_PHASE=exp07`, mesmos modelos da bateria (`qwen3.6-27b` no
Investigador, `gpt-oss-120b` no Decisor).

O rodízio de chaves trocou de conta 30 vezes ao longo da bateria e nenhuma execução caiu.

Antes da coleta, uma sonda sem LLM confirmou contra a API real que as 12 combinações de
`(braço, endpoint)` entregam os valores da seção 5, e que `min_snr_db = 12.0` sobrevive em
todos os braços. Sem isso, o caso B teria rodado cego.

## 10. Análise

### 10.1 Resultado por nível

Nível 1 = o finding do Investigador cita o valor mutado. Nível 2 = a justificativa do Decisor
cita. ✔ significa que o braço decisivo acompanhou a mutação; ✘ que manteve a leitura do
controle.

| Caso | Nível 1 | Nível 2 | Decisão (controle → decisivo) | Placebo mudou? |
| :--- | :---: | :---: | :--- | :---: |
| A · inv_06 | ✔ | ✔ | orientar → orientar | não |
| B · inv_10 | ✔ | ✔ | orientar → orientar | não |
| C · inv_08 | ✔ | **✘** | agir → agir | não |
| D · inv_11 | ✔ | ✔ | orientar → orientar | não |

**Nível 1: 4/4.** O Investigador leu o campo mutado em todos os casos, e registrou o valor
novo no finding: `1x` em 6,4 no caso A, `snr_db=16.5 (req: 12.0)` no B,
`evidence_2x=3.9_vs_ref_0.5` no C, `can_learn_baseline=true` no D.

**Nível 2: 3/4.** Três justificativas acompanharam. A do caso C não.

**Placebo: 0/4.** Nenhuma justificativa mudou de conclusão sob o placebo. Os quatro braços de
placebo reproduzem a conclusão do controle.

Pelo critério congelado na seção 6 — decisivo muda em 3/4, placebo não muda em 4/4 — a
**hipótese está sustentada**.

### 10.2 O que o caso C mostrou, e é o achado que interessa

No caso C o Investigador escreveu no finding:

> `analysis.an_9907.type=misalignment, confidence=0.9, evidence_2x=3.9_vs_ref_0.5`
> `analysis.an_9908.type=looseness, confidence=0.22, evidence_subharmonics=0.1_vs_ref_0.2`

A evidência está lá, com os dois números e a inversão de confiança. O Decisor respondeu:

> "Conflito entre diagnóstico automático (desalinhamento, alta confiança) e especialista
> (base solta, baixa confiança) combinado com dados indisponíveis (…) impede uma conclusão
> segura"

Ele **leu** a assimetria (nomeia "alta confiança" e "baixa confiança") e mesmo assim manteve
`agir`, tratando 0,90 contra 0,22 como conflito irresolvido. No controle, com 0,69 contra
0,71, a mesma conclusão era correta.

Isso não é a linha "cita / não cita" da seção 3.4. É uma quarta situação que o desenho não
previa: **a evidência chega em quem decide, e o Decisor não a usa como critério de
desempate.** A falha não está na leitura nem no handoff. Está na política de decisão.

O caso C era o único do conjunto com desfecho binário e nomeado, e é o único que falhou.
Isso é o contrário de coincidência: os outros três permitiam uma resposta correta em que o
agente descreve a evidência sem precisar escolher entre duas alternativas.

### 10.3 O que este experimento derruba

A leitura confortável de [EXP-06](EXP-06-politica-de-evidencia-bateria-completa.md) —
"decisão idêntica em 18 pares porque as consultas cortadas eram redundantes" — sobrevive.
A evidência **causa** a resposta: 4/4 no nível 1, 3/4 no nível 2, 0/4 no placebo. O agente
não está sendo carregado pelo texto do ticket.

Os casos A e B eram os testes de eco de enunciado, e o agente passou nos dois. No caso A o
usuário afirma *"isso não é nada"* e o agente, sob mutação, contrariou: passou de "diagnóstico
não é confiável" para "a detecção foi feita com baseline estabelecido e confiança 0,81". No
caso B a usuária afirma *"tá péssima"* e o agente passou a dizer que a qualidade atenderia aos
requisitos.

### 10.4 O que este experimento não prova

O caso A revelou um efeito colateral do bundle que a limitação 1 da seção 7 antecipava. O
Investigador registrou:

> `rms.baseline_state=invalidated (rms) — conflito com baseline.state=established`

A mutação move `/assets/{id}/baseline` mas não o `baseline_state` embutido na resposta de
`/rms`, e o agente detectou a incoerência. Ele chegou à conclusão prevista, e chegou lá
raciocinando sobre um estado que a API nunca produziria ("o baseline foi invalidado APÓS a
detecção"). O ✔ do caso A no nível 2 vale menos do que os do B e do D por isso.

Além disso: n = 4 casos, um seed, um conjunto de modelos, dados sintéticos. Nada aqui é
estimativa de taxa.

### 10.5 Consequência para o agente

O caso C aponta para o prompt do Decisor, não para a arquitetura. Um conflito entre duas
análises com confianças de 0,90 e 0,22 não é conflito, e a política atual não diz isso em
lugar nenhum. Duas correções candidatas, nenhuma testada:

1. Nomear no prompt do Decisor que diferença grande de confiança resolve conflito entre
   análises, em vez de escalar.
2. Fazer o Investigador registrar a razão entre confianças como fato apurado, em vez de
   deixar o Decisor comparar dois números soltos.

Qual das duas funciona é questão empírica, e vira o EXP-08. Este documento não decide.

Este é também o primeiro resultado do projeto que mede a arquitetura multiagente: a linha
"cita / não cita" do handoff ficou limpa em 4/4, o que enfraquece a suspeita de que a
compressão em `findings` perde evidência.
