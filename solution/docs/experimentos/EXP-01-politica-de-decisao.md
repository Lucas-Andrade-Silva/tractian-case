# EXP-01 — Tornar explícito na política *quando orientar não basta*

**Estado:** concluído · **Fase dos dados:** `baseline` × `pos-correcao` · **n = 102 execuções**
(51 pareadas) · **Registrado em:** 2026-09-04

> Experimento reconstruído a posteriori sobre execuções que já existiam. A hipótese não foi
> escrita antes da coleta — ver [Limitações](#5-limitações), item 1. Isso enfraquece a
> inferência causal e está declarado em vez de omitido.

## 1. Hipótese

> Tornar explícito na política de decisão **quando `orientar` não basta** — isto é, quando a
> evidência revela algo que continuará prejudicando o cliente depois que ele ler a resposta —
> aumenta a acurácia de decisão do agente, sem aumentar o custo da trajetória.

A hipótese nasce de um padrão observado nos traces da fase `baseline`: o agente produzia
explicações tecnicamente corretas e, ainda assim, reprovava. Ele diagnosticava bem e resolvia
mal. A suspeita é que `orientar` funcionava como atrator — a resolução que sempre parece
defensável, porque explicar nunca está *errado* — e que o modelo não tinha critério escrito
para reconhecer os casos em que explicar é insuficiente.

Predição que torna a hipótese falseável: se ela vale, os ganhos se concentram em casos cuja
resolução aceita é `agir` ou `escalar`, e **não** deve haver perda em casos de `orientar`. Se
a acurácia subisse uniformemente, ou subisse trocando erros de um tipo por erros de outro, a
explicação seria outra.

## 2. Método

**Intervenção.** Três mudanças aplicadas juntas, entre as duas fases:

1. bloco `QUANDO ORIENTAR NÃO BASTA` acrescentado a `_DECISION_POLICY`
   ([`agent/app/prompts.py`](../../agent/app/prompts.py)), nomeando dois gatilhos concretos —
   pedido direto de ação pelo cliente, e conflito entre fontes sobre o mesmo ativo — e
   delimitando o que **não** é gatilho (dado parcial, baseline inválido, inferência incerta);
2. reordenação `decida primeiro, redija depois` no `decider_prompt`, para que a escolha da
   resolução não fosse subproduto da redação da resposta;
3. passagem dos `findings` ao Executor, para que ele resolvesse IDs já apurados em vez de
   pedi-los de volta.

**Desenho.** Comparação **pareada** por `(caso, seed)`: 17 casos × 3 seeds = 51 pares, cada um
executado nas duas fases. O pareamento é o que permite atribuir a diferença à intervenção e
não à composição da amostra — os dois braços veem exatamente os mesmos casos e as mesmas
seeds, portanto os mesmos modos de resposta da API.

**Controles.** Modelos por papel idênticos nas duas fases (`config_diverge_entre_fases: false`
no bundle), `temperature=0`, mesma `evidence_policy=fixed`, mesmos orçamentos, mesma API local.

**Métricas** (camada 1, [`evaluation/runner/deterministic.py`](../../evaluation/runner/deterministic.py)):

| Métrica | Papel no experimento |
| :--- | :--- |
| `decision_match` | desfecho primário — a resolução está entre as aceitas pelo cenário |
| `passou` | desfecho secundário, mais rigoroso: exige também nenhuma ação exigida faltando e nenhuma ação indevida |
| `chamadas_api`, `total_tokens` | custo — a hipótese prevê que não piora |
| `evidence_recall` | controle de sanidade: a intervenção não deveria mexer na investigação |

**Critério de sucesso, fixado na leitura:** ganho líquido em `decision_match` com as trocas
concentradas em casos de `agir`/`escalar`, e custo não superior ao da `baseline`.

## 3. Execução

51 pares completos, sem falha de execução em nenhuma das fases. Os dados vêm de
`painel/dados/bundle.json` (gerado em 2026-09-04T01:39), que junta traces e CSV pela chave
`(case_id, seed, total_tokens)`.

```bash
make painel-dados      # regenera e verifica o bundle
```

## 4. Resultados

### 4.1 Desfechos

| Métrica (pareada, n=51) | baseline | pós-correção | Δ |
| :--- | ---: | ---: | ---: |
| `decision_match` | 44/51 (86,3%) | **48/51 (94,1%)** | +4 execuções |
| `passou` | 39/51 (76,5%) | **40/51 (78,4%)** | +1 execução |
| tokens (média) | 19.514 | **18.730** | −4,0% |
| chamadas de API (média) | 8,61 | **7,90** | −8,2% |
| taxa de repetição | 6,5% | **3,0%** | −54% |
| `evidence_recall` | 0,788 | 0,783 | −0,005 |

### 4.2 Tabela de discordância — `decision_match`

O que sustenta a leitura causal não é a média, é a assimetria das trocas:

| | pós: erro | pós: acerto |
| :--- | ---: | ---: |
| **baseline: erro** | 3 | **4** |
| **baseline: acerto** | **0** | 44 |

Quatro execuções corrigiram, **nenhuma regrediu**. As quatro:

| Caso | Seed | Mudança |
| :--- | :--- | :--- |
| TKT-INV-04 | complete | `orientar` → `escalar` ✔ |
| TKT-INV-04 | s2 | `orientar` → `escalar` ✔ |
| TKT-INV-08 | s3 | `orientar` → `agir` ✔ |
| TKT-EXE-14 | s2 | `orientar` → `agir` ✔ |

**As quatro saem de `orientar`.** É exatamente a predição da seção 1: o atrator era `orientar`,
e o bloco novo é o que dá ao modelo critério para sair dele. Nenhum caso cuja resolução correta
era `orientar` foi perdido — o que descarta a explicação alternativa de que a política apenas
enviesou o agente para agir mais.

### 4.3 Estabilidade entre seeds (camada 3)

| Fase | Casos estáveis nas 3 seeds |
| :--- | :--- |
| baseline | 13/17 — instáveis: TKT-EXE-14, TKT-INV-04, TKT-INV-08, TKT-INV-10 |
| pós-correção | **17/17** |

Efeito colateral não previsto pela hipótese, e o mais forte do experimento: a política não só
melhorou a decisão média, como eliminou a variação de resolução entre seeds. Na `baseline`,
TKT-INV-08 chegou a produzir três resoluções diferentes em três seeds (`escalar`/`agir`/`orientar`)
— sinal de decisão sem critério estável, não de sensibilidade legítima ao dado.

### 4.4 Contra-evidência: duas regressões em `passou`

`decision_match` não regrediu em nenhum par, mas `passou` regrediu em dois. Ambos merecem
registro porque contradizem a leitura otimista:

| Caso | Seed | O que aconteceu |
| :--- | :--- | :--- |
| TKT-EXE-12 | s2 | Decidiu `agir` corretamente, mas **não executou** `POST /analyses/an_9906/reprocess`. Decisão certa, ação faltante |
| TKT-EXE-15 | s2 | Executou `POST /models//request-retraining` — **`model_id` vazio na URL**. Ação indevida por bug de construção de argumento |

O segundo não é erro de decisão: é falha na montagem do argumento, na fronteira Decisor →
Executor. A mudança (3) — passar `findings` ao Executor — pretendia resolver justamente isso e
claramente não cobriu todos os caminhos. Fica como defeito aberto, não como ruído.

### 4.5 Veredito

**Hipótese sustentada para `decision_match`, com ressalva em `passou`.** O ganho de decisão é
consistente (4 correções, 0 regressões, todas na direção prevista) e veio com custo menor, não
maior. Mas a intervenção introduziu duas falhas de execução de ação que a métrica mais rigorosa
captura — o agente ficou melhor em *decidir* e não melhorou em *executar o que decidiu*.

## 5. Limitações

1. **Hipótese formulada após a coleta.** As execuções existiam antes do experimento ser escrito.
   Isso é HARKing e reduz a força da inferência: o critério de sucesso da seção 2 foi fixado na
   leitura dos dados, não antes. O que preserva algum valor é a tabela 4.2 — a assimetria
   (4 correções / 0 regressões / todas saindo de `orientar`) é um padrão que uma hipótese
   inventada depois não escolheria por acaso. Ainda assim, trate como **evidência sugestiva, não
   confirmatória**.
2. **Três mudanças aplicadas juntas.** Não é possível atribuir o efeito ao bloco de política, à
   reordenação do prompt ou à passagem de findings isoladamente. Seria necessário um desenho
   fatorial (uma mudança por braço) para separar. Como as três agem em pontos diferentes do
   fluxo, a atribuição ao bloco de política é plausível mas não demonstrada.
3. **n pequeno e não independente.** 51 pares, mas 17 casos × 3 seeds — as três seeds do mesmo
   caso não são observações independentes. O n efetivo está mais perto de 17. Não apliquei
   teste de significância: com 4 discordâncias, um McNemar exato daria p ≈ 0,125, ou seja, **o
   resultado não seria significativo a 5%**. Registro isso em vez de omitir o teste.
4. **Um único conjunto de modelos.** Todo o experimento roda com a mesma combinação qwen +
   gpt-oss. Se o efeito depende de o modelo ter dificuldade específica com o atrator `orientar`,
   ele pode não se reproduzir em modelos mais capazes.
5. **Gabarito como fonte de verdade.** `decision_match` compara contra `eval/expected-paths.json`.
   A legenda em `.run/legenda_seeds_e_metricas.csv` registra que, em vários casos, o gabarito
   estruturado não documenta um POST que o cenário narrativo prescreve — parte das reprovações
   de `passou` é artefato do gabarito, não erro do agente.
6. **Camada 2 ausente.** Nenhuma das 102 execuções foi julgada pelo comitê. Qualidade textual da
   resposta — honestidade, causa-raiz, justificativa — não entrou neste experimento.

## 6. Reprodução

```bash
make up
make painel-dados
python - <<'PY'
import json, collections
d = json.load(open('painel/dados/bundle.json', encoding='utf-8'))
pares = collections.defaultdict(dict)
for e in d['execucoes']:
    pares[(e['case_id'], e['seed'])][e['fase']] = e['avaliacao']
completos = [v for v in pares.values() if len(v) == 2]
tab = collections.Counter(
    (v['baseline']['decision_match'], v['pos-correcao']['decision_match'])
    for v in completos
)
print('pares:', len(completos))
print('(baseline, pos) ->', dict(tab))
PY
```
