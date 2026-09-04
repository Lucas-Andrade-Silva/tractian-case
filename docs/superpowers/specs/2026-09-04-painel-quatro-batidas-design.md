# Painel em quatro batidas — redesenho da interface

**Data:** 2026-09-04
**Status:** aprovado para planejamento
**Escopo:** `painel/` (JS + CSS). Nenhuma mudança em `agent/`, `evaluation/` ou no formato do bundle.

## Problema

O painel tem três abas que empilham 7, 7 e 4 blocos na vertical, todos abertos, todos no
mesmo peso visual. Não há como saber onde olhar. Três causas estruturais, não estéticas:

1. **Nada colapsa.** `desenhaAvaliacao` (`avaliacao.js:24`) e `desenhaDetalhe`
   (`operacao.js:158`) despejam todas as seções de uma vez. O único disclosure do painel
   inteiro são as linhas de chamada da timeline (`componentes.js:99`).
2. **O subtítulo é obrigatório por assinatura.** `secao(titulo, nota, conteudo)`
   (`componentes.js:59`) pede uma nota; toda seção ganhou uma porque o parâmetro existia.
3. **Prosa metodológica no mesmo plano do dado.** As ressalvas — precisão derivada, juiz
   não calibrado, artefato de gabarito, Decisor sem tools — são carga real e não podem
   ser apagadas, mas estão renderizadas como parágrafo permanente ao lado do número que
   ressalvam.

A base visual **não** é o problema: os tokens de `painel.css:5-77` (quatro categorias
semânticas independentes do acento, contraste corrigido à mão, escala tipográfica com
degraus reais, tema escuro completo) são bons e sobrevivem ao redesenho.

## Leitor e contexto de uso

Decidido com o autor:

- **Leitor:** banca do Inteli, 10-15 minutos, nunca viu o sistema.
- **Entrega:** projetor, com o autor narrando ao vivo. O autor é a legenda —
  descobribilidade importa menos que legibilidade a distância e ordem de apresentação.
- **Consequência tipográfica:** corpo sobe de 13,5px para ~16px; números de veredito a
  58-76px.
- **Consequência de conteúdo:** a prosa sai do estado inicial e vira gaveta, mas tem de
  voltar em um gesto quando a banca desafiar.

O painel **não é entregável obrigatório** (`STUDENT-GUIDE.md:215-229` lista código do
agente, código da avaliação, experimento e README). É a vitrine que torna os itens 2, 3 e
4 tangíveis. Os códigos `RN-XX`/`RF-XX` no código-fonte são regras auto-impostas pelo
autor, não requisito externo — renegociáveis, com uma exceção tratada abaixo.

## Dados que decidiram o desenho

Verificados contra `painel/dados/bundle.json` nesta sessão:

| fato | valor | efeito no desenho |
|---|---|---|
| acurácia de decisão | 86,3% → 94,1% (44 → 48 de 51) | vira a batida ① |
| falhas de execução | 0 em ambas as fases | selo, não seção |
| custo | 19,5k → 18,7k tokens; 8,6 → 7,9 chamadas | três deltas subordinados |
| repetição | 6,5% → 3,0% | idem |
| estabilidade | **17/17 cenários estáveis** nas 3 seeds | elimina a seção Estabilidade |
| taxa de aprovação | 78,4%, praticamente parada | fica fora do veredito (decisão do autor) |
| comitê de juízes | **ausente do bundle** (`juizes: false`) | não entra em nenhuma batida |
| desfechos das 51 células | 42 passaram · 8 artefatos · 1 erro real (CEN-09) | legenda de 4 categorias da matriz |

## Arquitetura: quatro batidas

As três abas viram quatro telas navegáveis livremente (← →, clique, ou teclado). Cada uma
responde **uma** pergunta e cabe numa tela sem rolagem em 1920×1080.

### ① Veredito — "funciona?"

`94,1%` ocupa a tela. Abaixo, uma seta única `baseline 86,3% ──▶ 94,1% (+7,8 pp)` —
substitui o dropdown de fase, que a banca não precisa descobrir. Depois, quatro deltas
pequenos: 0 falhas, −4% tokens, −8% chamadas, −54% repetição. Uma frase de fecho:
"Decidiu certo em 48 de 51 execuções — e ficou mais barato no caminho."

Nenhum filtro nesta tela: não há o que filtrar num veredito.

**Absorve:** `placar()` e `comparativo()` de `avaliacao.js`.

### ② Um chamado — "por quê?"

Caso fixo de abertura: `TKT-INV-09 / CEN-07` (mecânico trocou o rolamento, insight
continua acusando falha; o agente descobre baseline invalidado + análise stale e
reprocessa).

**Navegação entre casos.** A fila de `operacao.js:22-113` — com busca e quatro filtros —
não cabe no estado inicial desta batida: ela é o oposto de "uma tela, uma pergunta". Vira
gaveta lateral, aberta por um controle no cabeçalho (`TKT-INV-09 ⌄`), com a mesma busca e
os mesmos filtros de hoje. Fecha ao escolher um caso. A batida ③ também entra aqui, pelo
link "ver este chamado na batida ②" da célula.

Layout, de cima para baixo:

- Cabeçalho: ticket, cenário, decisão, ativo + criticidade, solicitante.
- Mensagem íntegra do cliente, em citação.
- **KPIs grandes:** chamadas de LLM · chamadas de API · tokens · duração · parada.
- **Faixas por papel** — uma faixa por papel na ordem de entrada. Cada `●` é uma chamada
  de LLM. No lugar dos endpoints, as **tags de fato apurado**, lidas do campo `achados`
  do bundle: `baseline invalidado`, `causa: manutenção`, `análise stale`, `sensor online`,
  `rms 1,945 < alarme 3,4`. Coloridas pelas quatro categorias existentes.
- Coluna direita de cada faixa: custo do papel (`6,2k · 40% do caso`).
- Entre as faixas, a passagem de bastão com o motivo real do Supervisor.
- **Resposta final ao cliente**, íntegra, em lugar fixo.

**Endpoints não aparecem por padrão.** Vivem atrás de `5 consultas ⌄` em cada faixa, ou
todos de uma vez pelo botão `⌄ mostrar chamadas cruas` do rodapé. Expandido, é o
comportamento atual (response cru), mas em gaveta lateral — não empurra a página.

**Duas coisas que isto elimina:**
- A prosa de `componentes.js:186-195` defendendo a ausência do Decisor: a faixa do
  decisor tem um `●` e a legenda "zero consultas — não tem tools (ADR 0002)". O argumento
  vira geometria.
- A tabela de custo por papel (`operacao.js:352-379`): vira a coluna direita das faixas.

**RN-01 permanece intacto.** Esta tela não mostra gabarito, decisão aceita nem status de
aprovação. É a separação agente/avaliação que sustenta a Parte 2 do projeto, e é a única
regra auto-imposta que o redesenho preserva sem renegociar. Continua verificável por
leitura de import: o módulo desta batida não importa nada de `avaliacao.js`.

### ③ Os 17 × 3 — "sempre?"

A matriz lidera e ocupa a tela: 17 linhas de cenário × 3 colunas de seed, cada célula
rotulada com a decisão tomada. Cabeçalho com três selos: `17/17 estáveis`,
`0 falhas de execução`, `1 erro real · 8 artefatos de gabarito`.

Legenda de quatro categorias, reusando as cores existentes:
passou · escalou (desfecho correto) · decisão certa mas gabarito não documenta o POST ·
decisão errada.

Clicar numa célula abre **gaveta lateral** com o diff (esperado × percorrido, o que faltou
apurar, o que sobrou), e um link "ver este chamado na batida ②".

**Dívida assumida:** a matriz sozinha não explica os 8 artefatos, e a banca pode lê-los
como desculpa. Mitigação: clicar numa célula amarela abre a gaveta **já na explicação do
artefato**, e o rodapé tem `ⓘ como a aprovação é calculada`. A explicação existe, sob
demanda — que é a regra geral deste redesenho.

**Absorve:** `matriz()` e `drilldown()`.
**Elimina:** `estabilidade()` (~85 linhas) — 17/17 é um selo, não uma seção.

### ④ Ao vivo — "de verdade?"

Formulário de **uma linha**: quem · qual ativo · o que observou. O resto do formulário
atual (`consulta.js:222-433`: subtítulo explicativo, ficha de permissões, seletor de
juízes) vai para a gaveta.

Durante a execução, **estado de espera honesto**: spinner, "costuma levar 15 a 25
segundos · mesmo grafo dos 17 cenários", e quatro selos de papel que acendem conforme
avançam. Ao terminar, reusa **exatamente** o desenho da batida ② — faixas, fatos, KPIs,
resposta final.

Selo `avaliação sintética — ADR 0007` fixo no rodapé: é a fronteira que impede a nota da
consulta livre de se misturar com as métricas dos 17 cenários.

**Decisão explícita de risco:** não haverá streaming incremental. Ele seria melhor de
assistir, mas exigiria emitir eventos de `agent/server.py` — a única peça do plano que
sairia de `painel/`. Rejeitado para manter o refactor contido e sem risco de véspera.
Fica possível como incremento posterior: as faixas são as mesmas, muda só quem as alimenta.

## A gaveta única

Uma gaveta, sempre no mesmo canto do rodapé, alcançável de qualquer batida. Abre por cima,
não empurra a página. Quatro abas internas:

1. **Método** — como cada métrica é calculada, incluindo que precisão de consultas é
   derivada pelo autor e não pelo código da avaliação, e a fórmula.
2. **Ressalvas** — artefato de gabarito, juiz não calibrado, política de evidência `fixed`,
   falha de execução como categoria própria.
3. **Auditoria** — toda ação de escrita da bateria com a justificativa que a acompanhou
   (RN-13: ação sem justificativa não é auditável), ações recusadas pela API, e as métricas
   de desperdício. Mantém o botão de exportar CSV.
4. **Arquitetura** — as ADRs relevantes, incluindo a 0002 que a batida ② já mostrou
   visualmente.

Toda prosa hoje inline migra para cá. Nada é apagado.

## Mudanças estruturais no código

- **`secao(titulo, nota, conteudo)` → `secao(titulo, conteudo, opcoes)`.** A nota deixa de
  ser posicional e obrigatória. Onde a nota era ressalva metodológica, vira entrada na
  gaveta; onde era redundante com o título, morre.
- **Novo módulo de navegação** entre batidas, substituindo o sistema de abas de
  `painel.js:38-108`. Os seletores de seed/fase saem do cabeçalho global (a batida ①
  não filtra; a ③ tem as 3 seeds na própria matriz).
- **Novo módulo de faixas por papel**, consumido pelas batidas ② e ④.
- **Novo módulo de gaveta**, consumido por todas.
- `operacao.js` perde `fichas()` (vira cabeçalho compacto) e `secaoCusto()` (vira coluna).
- `avaliacao.js` perde `estabilidade()` e `comparativo()` (absorvidas por selo e por seta);
  `auditoria()` migra para a gaveta.
- **`juizes()` fica no código, sem chamador.** O comitê está ausente deste bundle
  (`juizes: false`), então nenhuma batida o desenha — mas ele volta a rodar por
  `make painel-julgar`, e apagar a função obrigaria a reescrevê-la. Passa a ser renderizado
  pela aba **Ressalvas** da gaveta, condicionado a `bundle.juizes` existir, com o aviso de
  calibração de `avaliacao.js:538` preservado: nota de juiz não calibrado não é verdade, e
  por isso não sobe para nenhuma batida.

### Convenção visual estabelecida nesta sessão

**Borda lateral = citação literal, e nada mais.** Durante os mockups apareceram duas
bordas laterais a uma linha de distância significando coisas diferentes (uma marcando fala
do cliente, outra decorando o bloco de justificativa). Duas convenções concorrentes é pior
que nenhuma. O bloco de justificativa passa a se identificar por rótulo.

A régua de 1px colorida carregando semântica de categoria (`painel.css:45-47`) é
**deliberada e permanece** — é sistemática, tem quatro categorias definidas, e não é
decorativa. Se o hook de design apontá-la na implementação, discutir antes de suprimir.

## Verificação

- `RN-01`: o módulo da batida ② não importa de `avaliacao.js` — verificável por leitura de
  import, como hoje.
- `RN-16`: a resposta final ao cliente aparece íntegra, sem truncar.
- Nenhum número exibido pode ser derivado de aritmética não verificada contra o bundle.
  (Durante o brainstorm eu escrevi "48 de 51" por dedução e só depois confirmei; na
  implementação, todo agregado vem do bundle ou é calculado no `build_bundle.py`.)
- As quatro batidas cabem sem rolagem em 1920×1080; corpo ≥ 16px.
- Tema claro e escuro mantidos nas quatro batidas.

## Fora de escopo

- `agent/server.py`, `evaluation/`, formato do bundle.
- Streaming incremental na batida ④.
- Rodar o comitê de juízes ou calibrá-lo contra conjunto anotado por humano. A gaveta o
  exibe se o bundle o trouxer; produzir esse dado é outro trabalho.
