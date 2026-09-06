# Arquitetura — Agente de Suporte Industrial

Este documento explica **como o sistema é feito por dentro e por que foi feito assim**.

Cada decisão aqui foi tomada com uma alternativa mais óbvia em cima da mesa. O que interessa
não é a decisão isolada, é o motivo de ter descartado a outra. Onde a escolha foi discutível,
está escrito que foi discutível.

Contexto do problema e resultados numéricos estão em [`SOLUTION.md`](../SOLUTION.md).
Aqui é só arquitetura.

---

## 1. O que o sistema faz

Alguém que opera uma planta industrial abre um chamado: *"o motor da esteira está vibrando
mais que o normal desde ontem"*. Esse chamado chega ao agente.

O agente investiga — puxa dados do ativo, análises anteriores, qualidade do sinal — e termina
em **uma de três decisões**:

| Decisão | Significado | Exemplo |
| :--- | :--- | :--- |
| **orientar** | explicar, sem mexer em nada | "a vibração está dentro do baseline, é variação normal de carga" |
| **agir** | executar uma ação na plataforma | reprocessar uma análise, pedir retreinamento do modelo |
| **escalar** | mandar para humano | o caso extrapola o que dá para resolver remotamente |

E um segundo sistema, separado, mede se essa decisão estava certa.

São duas metades independentes, e a separação é proposital:

```
        PARTE 1                          PARTE 2
    ┌─────────────┐                  ┌─────────────┐
    │   AGENTE    │ ── trace JSON ─→ │  AVALIAÇÃO  │
    │   decide    │                  │    mede     │
    └─────────────┘                  └─────────────┘
```

O agente **não sabe** que está sendo avaliado, e não tem como saber: ele nunca vê o gabarito.
A avaliação lê o rastro depois que tudo acabou. Se as duas metades se conversassem durante a
execução, a medição não valeria nada — o agente estaria sendo medido contra uma resposta à
qual teve acesso.

---

## 2. O desenho em uma imagem

```
   chamado (cases.json)
           │
           ▼
  ┌────────────────────────────────────────────────────────┐
  │                    GRAFO LANGGRAPH                     │
  │                                                        │
  │   ┌────────────┐                                       │
  │   │ SUPERVISOR │ ◄─── decide quem trabalha agora       │
  │   └─────┬──────┘      (roteamento por LLM)             │
  │         │                                              │
  │    ┌────┼─────────────────┐                            │
  │    ▼    ▼                 ▼                            │
  │  ┌──────────────┐  ┌──────────────────┐                │
  │  │ INVESTIGADOR │  │ CONTEXTUALIZADOR │  ⇄ tools       │
  │  │ dados do     │  │ documentação,    │                │
  │  │ ativo        │  │ procedimentos    │                │
  │  └──────┬───────┘  └────────┬─────────┘                │
  │         └────────┬──────────┘                          │
  │                  ▼                                     │
  │            ┌───────────┐                               │
  │            │  DECISOR  │  ◄── SEM tools. Só decide.    │
  │            └─────┬─────┘                               │
  │                  │                                     │
  │        orientar ─┴─ agir / escalar                     │
  │           │              │                             │
  │           ▼              ▼                             │
  │          FIM       ┌──────────┐                        │
  │                    │ EXECUTOR │ ⇄ tools → FIM          │
  │                    └──────────┘                        │
  └───────────────────────────┬────────────────────────────┘
                              │ HTTP
                              ▼
                  API industrial (:8000)
                              │
                              ▼
                      trace JSON local
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │              AVALIAÇÃO EM 3 CAMADAS                    │
  │  1. determinística   — código puro, grátis, instantânea│
  │  2. comitê de juízes — 3 LLMs, um por dimensão         │
  │  3. estabilidade     — mesmo caso em 3 seeds           │
  └────────────────────────────────────────────────────────┘
```

Cinco papéis. Cada um com um trabalho e um conjunto de ferramentas próprio — **exceto o
Decisor, que não tem ferramenta nenhuma**. Essa exceção é a decisão mais importante do
desenho, e a seção 3.2 explica por quê.

---

## 3. As decisões, uma a uma

Cada seção segue a mesma estrutura: **o problema → o que era óbvio fazer → o que eu fiz →
por quê → o que isso custou**.

### 3.1 Multiagente com supervisor, em vez de um agente só

**O problema.** O agente precisa investigar, buscar documentação, decidir e executar ações.

**O óbvio.** Um agente único num loop ReAct. Nenhum dos 16 cenários *exige* especialização —
todos são "um chamado → uma investigação → uma decisão". Um agente só teria funcionado, e
teria sido mais barato de construir em um mês.

**O que fiz.** Cinco papéis separados num grafo LangGraph, com um Supervisor roteando entre eles.

**Por quê.** Escolha deliberada de explorar separação de responsabilidades como parte do
experimento do projeto. Não foi exigência do domínio — **e isso está admitido, não escondido**.

**O que custou.** Mais complexidade de implementação, e muito mais superfície de instrumentação:
o trace precisa registrar *qual papel* fez cada chamada, não só que a chamada aconteceu.

> **Honestidade sobre esta decisão:** nenhuma medição do projeto compara o multiagente com um
> agente único. Ela se sustenta em argumento, não em dado. É o experimento mais informativo que
> falta — e ele pode refutar a decisão central em vez de confirmá-la.

**Também descartei:** servidor MCP. O MCP existe para padronizar integração entre múltiplos
clientes; aqui há um consumidor só. A padronização não se pagaria.

### 3.2 O Decisor não tem ferramentas

Esta é a decisão que mais parece um bug quando se olha um trace pela primeira vez.

Nos 77 traces da bateria, **nenhuma chamada de API tem `agent="decisor"`**. Zero. Parece
instrumentação quebrada. Não é — é o desenho funcionando.

**Duas razões, e a segunda é consequência medível da primeira:**

**1. Separar apurar de decidir.** Se o Decisor pudesse consultar a API, ele reabriria a
investigação a cada dúvida. A fronteira entre "o que foi apurado" e "o que foi decidido"
deixaria de existir — e é exatamente essa fronteira que a avaliação inspeciona quando compara
as evidências coletadas com a justificativa dada.

**2. Custo.** Um papel com ferramentas entra em laço: chama, recebe, reavalia, chama de novo.
Cada volta reenvia o prompt inteiro e os schemas inteiros. Sem ferramentas não existe laço.

Medido nas 77 execuções:

| papel | chamadas de LLM | por execução |
| :--- | ---: | ---: |
| supervisor | 197 | 2,6 |
| investigador | 180 | 2,3 |
| contextualizador | 173 | 2,2 |
| **decisor** | **77** | **1,0** ← constante |
| executor | 55 | 0,7 |

O Decisor usa o modelo mais capaz da configuração — é a saída que a avaliação de fato julga, e
seria onde o custo por chamada mais pesaria. Não ter laço é o que torna essa escolha barata.

### 3.3 Roteamento híbrido: o LLM decide o meio, o código decide o fim

**O problema.** Quem escolhe qual papel trabalha a cada turno?

**As duas opções puras, e por que nenhuma serve sozinha:**

| Opção | A favor | Contra |
| :--- | :--- | :--- |
| 100% LLM | flexível | cada rota custa uma chamada; um erro de roteamento poderia pular a decisão formal e ir direto para uma ação de impacto |
| 100% código | previsível, grátis | os 16 cenários não seguem uma ordem única entre Investigador e Contextualizador; forçar uma exigiria tantas condicionais que viraria um classificador de intenção escrito à mão |

**O que fiz — o híbrido:**

```
Investigador ⇄ Contextualizador ......... LLM decide (flexível)
Decisor ──→ Executor .................... CÓDIGO decide (fixo)
```

**A parte não-óbvia é a segunda linha.** A transição Decisor → Executor só acontece quando o
Decisor formalmente concluiu "agir" ou "escalar". Nunca por escolha do roteador.

Isso garante — **estruturalmente, não por disciplina de prompt** — que nenhuma ação de impacto
na plataforma industrial aconteça sem ter passado por uma decisão formal e auditável.

A diferença importa: um prompt pode ser ignorado por um LLM num dia ruim. Uma aresta de grafo
não. Onde o risco é mexer numa máquina industrial de verdade, a garantia precisa estar no
código.

E o roteamento entre investigação continua livre porque **parar de investigar é comportamento
avaliado** — os cenários de over-escalation medem exatamente se o agente sabe quando já tem
evidência suficiente. Fixar isso em código seria dar a resposta de graça.

### 3.4 Permissão: deixar a API recusar, em vez de bloquear antes

**O problema.** O agente age sozinho. Como impedir que faça algo que o usuário da sessão não
pode fazer?

**O óbvio.** Checar a permissão no código antes de deixar o agente tentar. Bloqueia cedo,
parece mais seguro.

**O que fiz — o oposto.** A política de permissões vive **só no prompt**. O enforcement real
acontece na API, que devolve **403** quando falta permissão. O agente não é bloqueado: ele
tenta, e leva o 403 na cara.

**Por quê.** Bloquear em código eliminaria justamente o comportamento que três cenários avaliam
(CEN-14, CEN-15, CEN-16): **como o agente reage quando é recusado**. Ele admite a recusa e
explica? Ou insiste, tenta contornar, inventa que deu certo?

Isso não é detalhe de teste. É a pergunta de segurança mais importante sobre um agente
autônomo — e um bloqueio preventivo tornaria a pergunta impossível de responder.

Resultado medido: **5/5 execuções relataram a recusa honestamente, 0/5 insistiram.**

Consequência: o escopo do agente autônomo é **exatamente** o que a permissão do usuário
autoriza. Sem lista extra de proibições em código. A API é a única fonte de verdade do limite —
uma fonte de verdade, não duas que podem divergir.

### 3.5 Trace local, não LangSmith

**O problema.** A avaliação precisa ler o que o agente fez. De onde?

**O óbvio.** LangSmith. É a integração nativa do LangGraph, captura tudo automaticamente, sem
instrumentação manual. Bastaria exportar de lá.

**O que fiz.** O agente grava, em paralelo, um trace estruturado próprio em JSON local — **no
mesmo formato do gabarito**. É esse arquivo que a avaliação lê.

**Por quê.** Duas razões:

1. **Reprodutibilidade.** A avaliação não pode depender da disponibilidade de um serviço
   externo. Se o LangSmith cair, ou mudar a API, ou a conta expirar, os resultados do projeto
   deixam de ser reproduzíveis.
2. **Formato.** Gravando no formato do gabarito, a comparação é direta. Exportando do
   LangSmith, seria preciso traduzir a estrutura de terceiros a cada execução — trabalho extra
   e mais um lugar onde se introduz bug.

**O LangSmith continua no projeto** — é a ferramenta certa para inspeção humana durante o
desenvolvimento. Só não é a fonte de verdade da medição. Cada ferramenta no papel em que é boa.

### 3.6 Avaliação em três camadas, em vez de um método só

**O problema.** As dimensões a medir são de naturezas incompatíveis:

- *A decisão final bate com o gabarito?* → comparação exata, código puro resolve
- *A explicação foi honesta sobre a incerteza?* → julgamento, código nenhum resolve

**O óbvio.** Escolher um método. Ou só determinístico (e perder tudo que é qualitativo), ou só
um juiz LLM holístico (e medir mal o que é objetivo, gastando LLM à toa).

**O que fiz — a pirâmide:**

```
        ┌──────────────────────────────────┐
   3    │  ESTABILIDADE entre seeds        │  mesmo caso, 3 execuções
        ├──────────────────────────────────┤
   2    │  COMITÊ DE JUÍZES LLM            │  3 juízes, 1 por dimensão
        ├──────────────────────────────────┤
   1    │  DETERMINÍSTICA                  │  grátis, instantânea
        └──────────────────────────────────┘
                  roda de baixo para cima
```

**Camada 1 — determinística.** Decisão final, sequência de ferramentas contra o caminho
esperado, tratamento de erro HTTP, número de chamadas, taxa de repetição.

**Camada 2 — comitê de juízes.** Três juízes LLM, **um por dimensão**: honestidade sob
incerteza, acurácia da causa-raiz, qualidade da justificativa. Estilo G-Eval — rubrica explícita
de 1 a 5, raciocínio antes da nota, saída estruturada, `temperature=0`.

**Camada 3 — estabilidade.** Cada cenário roda em pelo menos 3 seeds. Um cenário só é instável
se a **decisão final** divergir; trajetória diferente é esperada e não conta.

**Por que nessa ordem.** A camada 1 é grátis e instantânea. Ela roda primeiro e funciona como
filtro — não faz sentido gastar chamadas de LLM julgando a qualidade textual de uma execução
que já falhou no básico.

**Por que três juízes e não um.** Um juiz multitarefa confundiria dimensões distintas numa nota
só. Se a nota cai, você não sabe se foi a honestidade ou a causa-raiz que piorou — e não tem
como calibrar nem diagnosticar separadamente.

### 3.7 Holdout sintético novo, em vez de dividir os 16 cenários

**O problema.** Avaliar o agente só nos casos usados durante o desenvolvimento mede "quanto ele
decorou", não se ele generaliza. É a Lei de Goodhart: quando a métrica vira alvo, ela deixa de
ser boa métrica.

**O óbvio.** Dividir os 16 em dois grupos — 8 para desenvolver, 8 para testar.

**Por que rejeitei.** Os 16 cenários **não são intercambiáveis**. Cada um cobre uma faceta que
nenhum outro cobre:

- CEN-04 é o **único** caso de detecção sintomática
- CEN-05 é o **único** com espectro parcial
- CEN-15 e CEN-16 são os **únicos** que exercitam ações de alto impacto

Dividir ao meio não reduz volume — **corta facetas inteiras do domínio** de um dos dois lados.
O conjunto de desenvolvimento perderia a capacidade de exercitar o agente em situações reais, e
o de teste mediria um recorte enviesado.

**O que fiz.** Mantive os 16 originais **inteiros** como desenvolvimento, e gerei um holdout com
cenários **sintéticos novos**, reaproveitando ativos que já existem nos dados (sem estender os
parquets do parceiro).

**A salvaguarda — auditoria mecânica.** Cada cenário sintético só entra no holdout depois de
rodar de fato contra a API local com seed fixa e confirmar que a resposta real sustenta a
resolução esperada. É o mesmo processo que a Tractian usou para corrigir CEN-05 e CEN-08.

Resultado: 41/41 asserções, 8/8 cenários auditados.

**Isso não invalida o teste**, e vale explicar por quê: os 16 originais **também** são sintéticos
e fictícios. A diferença entre eles e o meu holdout não é "real vs. inventado" — é *curadoria por
especialista Tractian* vs. *curadoria própria verificada mecanicamente contra o sistema real*.

### 3.8 Consulta livre: gabarito gerado por LLM, em métrica separada

**O problema.** O sistema foi construído para um conjunto fechado: 17 casos pré-escritos, cada
um com trajetória de referência. Falta a porta de entrada que o uso real pressupõe — **alguém
digitando com as próprias palavras o que viu na máquina**, sem gabarito nenhum.

Receber o texto é trivial. O problema é que **as três camadas de avaliação dependem de
gabarito**, e um caso digitado agora não tem.

**E aqui mora uma armadilha.** Sem gabarito, a camada 1 compararia o caminho tomado com uma
lista vazia — o que dá `recall = 1.0` sobre conjunto vazio e derivaria "orientar" como resposta
esperada. Um número que **parece excelente e não significa nada**. Pior que não medir.

**O que fiz — a camada 2-S (sintética)**, com quatro restrições que a mantêm defensável:

**1. O gabarito é gerado por LLM ANTES da execução.** A ordem é a salvaguarda central. Gerar
depois faria o gerador ver a resposta do agente e descrever como "esperado" exatamente o que o
agente fez — julgamento virando tautologia. Como gerador e agente são ambos LLMs, **nada além
da ordem impede isso**.

**2. Modelo gerador ≠ modelo juiz, verificado em código.** Um juiz avaliando contra gabarito
escrito por ele mesmo mede auto-consistência, não acurácia — e a nota resultante é
**indistinguível de uma nota válida** quando chega ao painel. Por isso a verificação levanta
exceção antes de qualquer chamada, em vez de degradar em silêncio.

**3. Separação de provedores.** Juiz sempre OpenRouter, agentes sempre Groq. Faz duas coisas ao
mesmo tempo: separa as cotas (uma bateria de julgamento não consome o orçamento que o
Investigador precisa) e torna a regra do item 2 **estrutural** — o gerador roda na Groq, então
nenhum juiz pode coincidir com ele.

**4. A camada 1 é pulada, não adaptada.** O que sobrevive sem gabarito é apurado direto do
trace: a execução concluiu? quantas chamadas foram repetidas? o agente insistiu depois de um
403? São propriedades do próprio trace — uma chamada idêntica repetida é desperdício
independentemente do que o gabarito dissesse. O resto fica explicitamente `null`, com o motivo
gravado no JSON.

**5. Isolamento por caminho, não por disciplina.** Consultas gravam num diretório que nem o CLI
de avaliação nem o construtor do painel alcançam. Não depende de lembrar de rodar o comando
certo — depende de caminho, e há teste que falha se ele mudar.

**O agente não muda.** Mesmo grafo, mesmas ferramentas, mesmos prompts. Se mudassem, as medidas
dos 17 cenários não valeriam para o que a aba de consulta executa.

> **O que esta camada não autoriza dizer:** que uma consulta livre teve desempenho comparável a
> um cenário com gabarito real. A ordenação vale dentro do conjunto sintético e nada além disso.
> O painel afirma essa ressalva **acima** das notas, não em rodapé.

---

## 4. O que vem antes e o que vem depois

Esta é a pergunta que quase nunca é respondida em documento de arquitetura acadêmico, e é a que
separa um protótipo de um sistema: **onde isso se encaixa num mundo real?**

```
   ┌──── ANTES (não construído) ────┐  ┌── ESTE SISTEMA ──┐  ┌──── DEPOIS (não construído) ────┐

   sensores no equipamento              ┌──────────────┐      execução da ação na planta
            │                           │              │              │
            ▼                           │   AGENTE     │              ▼
   coleta e processamento               │              │      confirmação humana
            │                           │  investiga   │       (ações de impacto)
            ▼                           │  decide      │              │
   modelos de detecção                  │  age         │              ▼
            │                           │              │      resposta ao cliente
            ▼                           └──────┬───────┘              │
   plataforma / API industrial ─────────────→  │                      ▼
            │                                  │              retorno para o modelo
            ▼                                  ▼              (o diagnóstico estava certo?)
   chamado aberto por uma pessoa ──────→  ┌──────────────┐            │
                                          │  AVALIAÇÃO   │            ▼
                                          │  mede        │      histórico do ativo
                                          └──────────────┘
   └────────────────────────────────┘  └──────────────────┘  └────────────────────────────────┘
```

### O que vem antes (existe, e eu consumo por HTTP)

| Camada | O que faz | Meu contato |
| :--- | :--- | :--- |
| Sensores | medem vibração, temperatura | nenhum |
| Processamento de sinal | transformam em RMS e espectro | nenhum |
| Modelos de detecção | produzem os diagnósticos automáticos | leio o resultado |
| Baseline | estado normal aprendido do ativo | leio o estado e a validade |
| Plataforma / API | expõe tudo por HTTP | **é a minha fronteira** |
| Pessoa | abre o chamado descrevendo o problema | é a minha entrada |

**Onde eu entro exatamente:** depois que o chamado existe e os dados estão disponíveis. Eu não
gero dado nenhum. Consumo dados de terceiros e produzo *decisão sobre eles* — o que significa
que **a qualidade do meu sistema tem um teto imposto pela qualidade do que chega**. Um baseline
inválido ou um espectro faltando limita a decisão por mais bem construído que o agente esteja.
Vários cenários existem justamente para testar se o agente **reconhece** esse limite em vez de
decidir mesmo assim.

### O que vem depois (não construído — e por que faltar importa)

| O que faltaria | Por que importa | Custo de não ter |
| :--- | :--- | :--- |
| **Confirmação humana antes de agir** | hoje o agente executa sozinho; o único teto é a permissão da API | uma decisão errada vira ação errada sem revisão |
| **Entrega ao cliente** | o agente produz o texto, ninguém o entrega | o sistema para antes do usuário final |
| **Retorno de acerto** | ninguém registra se o diagnóstico se confirmou na prática | o sistema não aprende com o próprio erro |
| **Histórico entre interações** | cada execução é isolada, sem memória | o cliente responde e a conversa recomeça do zero |
| **Latência e custo monetário** | hoje mede-se chamadas e tokens | não dá para dizer se é viável em produção |

**A ausência mais séria é a terceira.** Sem retorno de acerto, o sistema opera em ciclo aberto:
decide, entrega, e nunca descobre se acertou. As três camadas de avaliação medem contra um
gabarito escrito por humanos — o que é bom, mas é uma foto, não um termômetro. Em operação real,
a verdade vem da máquina que quebrou ou não quebrou depois.

---

## 5. Onde o desenho é frágil

Nenhuma destas é surpresa; todas foram aceitas conscientemente. Registrá-las é o que separa
documentação de propaganda.

**A arquitetura central não foi testada contra a alternativa.** A escolha multiagente (3.1) se
apoia em argumento. Um agente único com as mesmas ferramentas poderia decidir igual ou melhor,
mais barato. Não sei — não medi.

**A qualidade da decisão depende do texto dos prompts mais do que o desenho sugere.** O EXP-07
cortou o brief de domínio do prompt do Supervisor — um papel que só roteia e não interpreta
dado, onde o corte parecia seguro. O custo caiu 15,5% e **três decisões voltaram ao atrator
`orientar`**, junto com a instabilidade entre seeds que a política de decisão tinha eliminado.
Nas três, toda a evidência havia sido apurada (recall 1,00): não foi falta de dado, foi a
decisão mudando. Isso significa que as garantias estruturais deste documento — a transição fixa
Decisor → Executor, a separação de papéis — protegem contra a **ordem** das ações, não contra a
**qualidade** do julgamento. Essa continua dependendo de prompt, e é frágil a mudanças que
parecem inofensivas.

**Hipóteses formuladas depois dos dados.** Cinco dos sete experimentos, incluindo o central,
foram escritos sobre execuções que já existiam. Isso tem nome (HARKing) e está declarado no topo
de cada documento. Trate como evidência sugestiva, não confirmatória.

**Amostra pequena e não independente.** Três seeds do mesmo caso não são três observações
independentes. Onde há taxa sobre 51 execuções, o número efetivo está mais perto de 17. Nenhum
resultado atinge significância a 5% — o principal fica em p ≈ 0,125.

**Os juízes não foram calibrados.** Média de juiz LLM que nunca foi conferida contra anotação
humana não é verdade estabelecida. A rubrica e o `temperature=0` reduzem a variância, não o viés.

**Tudo é sintético.** Os 17 casos vêm de material fictício. Nada aqui demonstra transferência
para operação real — é a limitação que mais restringe as conclusões.

**A cota moldou o desenho.** O n=6 de um experimento e a cobertura parcial da camada 2 vêm do
limite do plano gratuito, não de escolha metodológica. É restrição de recurso apresentada como
tal, não racionalizada.

---

## 6. Próximos passos, em ordem de valor

Ordenados por **quanto cada um mudaria o que se pode afirmar** — não por facilidade.

**1. Comparar com um agente único.** O experimento mais informativo que falta, porque pode
**refutar** a decisão de arquitetura central. Mesmas ferramentas, mesma política, um papel só.
Se decidir igual, o multiagente não se paga.

**2. Calibrar o comitê de juízes.** Anotar à mão algumas dezenas de execuções e medir a
concordância com as notas dos juízes. Sem isso, toda a camada 2 é um número sem denominador.
É barato — custa tempo, não tokens.

**3. Completar a camada 2.** 35 de 102 execuções julgadas, e as 35 são todas da versão anterior
do agente. Enquanto isso não fechar, nenhuma afirmação sobre qualidade textual cobre a versão
atual.

**4. Rodar o holdout — uma única vez, no fim.** É teste de generalização; rodar mais de uma vez
e ajustar entre as rodadas o transformaria em mais um conjunto de desenvolvimento, exatamente o
problema que ele existe para evitar.

**5. Confirmação humana antes de ações de impacto.** Muda o perfil de risco do sistema e é
medível com as métricas que já existem.

**6. Mais casos distintos, não mais seeds.** Um caso novo vale mais que uma seed a mais: seeds
do mesmo caso são correlacionadas, casos distintos não.

**7. Medir latência e custo monetário.** É o que decide viabilidade em atendimento real, e hoje
não está medido.

**8. Memória entre interações.** O briefing lista contexto multi-turno como ponto relevante; o
agente atende um caso por execução, sem histórico. É a extensão natural do escopo.

---

## 7. Mapa rápido do código

| Quero entender... | Abro |
| :--- | :--- |
| como os papéis se conectam | [`agent/app/graph.py`](../agent/app/graph.py) |
| o que o agente pode fazer | [`agent/app/tools.py`](../agent/app/tools.py) |
| como cada papel é instruído | [`agent/app/prompts.py`](../agent/app/prompts.py) |
| como o rastro é gravado | [`agent/app/trace.py`](../agent/app/trace.py) |
| a camada determinística | [`evaluation/runner/deterministic.py`](../evaluation/runner/deterministic.py) |
| o comitê de juízes | [`evaluation/runner/judges.py`](../evaluation/runner/judges.py) |
| o gabarito sintético | [`evaluation/runner/sintetico.py`](../evaluation/runner/sintetico.py) |
| a estabilidade entre seeds | [`evaluation/runner/stability.py`](../evaluation/runner/stability.py) |

---

*Este documento consolida os sete ADRs originais (`docs/adr/0001`–`0007`), agora substituídos por
ele. Resultados numéricos e limitações completas: [`SOLUTION.md`](../SOLUTION.md).*
