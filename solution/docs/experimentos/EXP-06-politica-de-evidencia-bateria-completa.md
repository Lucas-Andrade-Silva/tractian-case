# EXP-06 — Política de evidência, segunda medição: `conditional` não economizou

**Estado:** concluído, indicativo (amostra parcial) · **n = 18 pares** (de 51 planejados) ·
**Dados:** `.run/resultados_avaliacao.csv`, fase `conditional` ·
**Registrado em:** 2026-09-05

> Repete o [EXP-02](EXP-02-politica-de-evidencia.md) com casos que ele não cobria, e
> **inverte o sinal**: onde o EXP-02 mediu `conditional` gastando 8% menos, aqui ela gasta
> **13% mais**. A decisão continua idêntica nos dois experimentos.

## 1. Por que repetir

O EXP-02 comparou `fixed` e `conditional` em 2 casos × 3 seeds e concluiu que `fixed` não
comprava acurácia, só recall, e custava 8% em tokens. Ele mesmo registrava por que isso
era pouco:

> **n = 6 pares.** […] Casos de ação direta (família TKT-EXE) e casos de conflito entre
> fontes ficaram de fora — e são justamente os que mais dependem de evidência completa.
> É plausível que `fixed` ganhe ali, e o experimento não olhou.

Esta bateria tentou cobrir os 17 casos. Chegou a 18 pares — as razões estão na seção 5.

## 2. Método

**Desenho.** Pareado por `(caso, seed)` contra a fase `pos-correcao`, que é a produção
atual e roda `EVIDENCE_POLICY=fixed`. Mesmos modelos por papel, `temperature=0`, mesmas
seeds, mesma API local. A única diferença é o bloco de política no prompt do Investigador.

**Registro.** Primeira bateria a gravar a fase e a política no próprio trace
(`RUN_PHASE` e `evidence_policy` em `agent/app/trace.py`), em vez de inferi-las depois por
junção com o CSV.

```bash
make eval-politica POLITICA=conditional
python solution/painel/recalcular_csv.py --fase conditional
```

## 3. Resultados

### 3.1 Agregado, 18 pares

| métrica | `fixed` | `conditional` | delta |
| :--- | ---: | ---: | ---: |
| tokens | 14.449 | **16.353** | **+13,2%** |
| chamadas de API | 5,56 | 6,17 | +11,0% |
| GETs feitos | 5,06 | 5,67 | +12,1% |
| recall de evidência | 0,667 | 0,680 | +2,1% |
| taxa de repetição | 0,000 | 0,034 | — |
| decisão correta | 18/18 | **18/18** | 0 |
| passou (trajetória) | 15/18 | **15/18** | 0 |
| decisões divergentes | — | **0 de 18** | — |

### 3.2 Por família de caso

| família | n | `fixed` | `conditional` | delta |
| :--- | ---: | ---: | ---: | ---: |
| CTX (conceitual) | 5 | 10.573 | 11.132 | +5,3% |
| EXE (ação direta) | 3 | 16.797 | 18.936 | +12,7% |
| INV (diagnóstico) | 10 | 15.682 | 18.187 | +16,0% |

`conditional` gastou menos em **1 dos 18 pares**.

## 4. Leitura

**A economia projetada não apareceu.** `conditional` instrui o Investigador a apurar menos
quando a pergunta é conceitual ou procedimental. O efeito medido é o contrário: mais
tokens, mais chamadas, mais GETs — nas três famílias, inclusive a conceitual, que é onde a
política deveria economizar.

**A repetição sobe de zero.** Em `fixed`, nenhuma execução repetiu uma chamada; em
`conditional`, a taxa média é 3,4%. É pouco em valor absoluto, mas sai de um piso perfeito.
A leitura mais coerente com os traces: sem a lista fixa dos quatro pilares, o Investigador
perde o critério de parada e reconsulta para decidir que terminou. A instrução `fixed`
funciona menos como exigência de completude e mais como **condição de parada** — o que o
EXP-02, medindo só volume, não conseguia separar.

**A decisão não mudou.** 18/18 nos dois braços, zero divergências par a par. Isso replica
o EXP-02 e é o achado mais estável dos dois experimentos: a política de evidência afeta
custo, não desfecho.

**O EXP-02 não estava errado no que mediu.** Ele viu 6 pares em 2 casos, um deles de
controle (onde as políticas prescrevem o mesmo), o que dava n efetivo de 3. Com 18 pares e
as três famílias, o sinal de custo inverte. Nenhum dos dois n sustenta uma conclusão forte
sozinho — mas os dois juntos afastam a hipótese de que `conditional` economize de forma
confiável.

## 5. Limitações

1. **18 de 51 pares — e a razão é constrangedora.** A bateria rodou duas vezes. A primeira
   parou em 18 execuções por cota da Groq (200k tokens/dia por conta). A segunda, feita
   por `completar_fase.py`, rodou **com a política errada**: eu passei `RUN_PHASE=conditional`
   mas não `EVIDENCE_POLICY=conditional`, e 22 execuções ficaram rotuladas `conditional`
   tendo rodado `fixed`. Foram descartadas para `.run/DESCARTE_policy_errada/`. O script
   agora força a política a bater com a fase, e avisa quando corrige.
2. **A amostra não é aleatória.** Os 18 pares são os primeiros da ordem alfabética dos
   casos — os que couberam antes de a cota acabar. A família EXE, a mais sensível, ficou
   com 3 pares.
3. **Sem camada 2.** Rodou com `--skip-judges`. Não foi avaliado se a resposta de
   `conditional` é pior de ler, só se é mais cara.
4. **A explicação da repetição é inferência.** Que a lista fixa funcione como condição de
   parada é a leitura mais coerente com os traces, mas não foi testada isoladamente. Um
   experimento que mantivesse `conditional` e acrescentasse um critério de parada explícito
   separaria as duas coisas.

## 6. Veredito

**`fixed` continua sendo o padrão, e agora com uma razão a mais.** Não é mais só cautela: é
que a alternativa não entregou a economia que prometia, em duas medições independentes com
sinais opostos de custo e o mesmo resultado de desfecho.

A conclusão firme exige a bateria completa nas mesmas condições — 51 pares, mesma política
do início ao fim. O procedimento está corrigido e documentado; falta a cota.

## 7. Reprodução

```bash
make up
make eval-politica POLITICA=conditional                        # bateria completa
python solution/painel/completar_fase.py --fase conditional \
       --politica conditional                                  # retoma o que a cota cortou
python solution/painel/recalcular_csv.py --fase conditional
make painel-dados
FASE=conditional FASE_ANTERIOR=pos-correcao make leitura-dados
```

O `--politica` da segunda linha é obrigatório na prática: sem ele a reposição herda o
`.env` e pode rodar a política errada — foi o que aconteceu aqui.
