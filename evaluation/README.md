# evaluation/ — Parte 2: avaliação do agente

Implementação própria da metodologia de avaliação. Roda **depois** do agente, sobre o
trace que ele produziu.

## Regra de separação

Este é o único lugar autorizado a ler o gabarito (`../eval/`), e a leitura está
concentrada em um único módulo — [`runner/golden.py`](runner/golden.py). Isso torna a
regra verificável: um vazamento do gabarito para o agente apareceria como um import
desse módulo dentro de `../agent/`.

## Pirâmide de três camadas

Da [ADR 0005](../docs/adr/0005-piramide-de-avaliacao-em-tres-camadas.md). A ordem importa: a camada 1 é
gratuita e instantânea, e funciona como filtro antes de gastar LLM nas seguintes.

### Camada 1 — determinística ([`deterministic.py`](runner/deterministic.py))

Comparação por código contra o golden set:

| Métrica | O que mede |
| :--- | :--- |
| `decision_match` | A resolução está entre as aceitas pelo cenário |
| `evidence_recall` | Fração das consultas do gabarito que o agente também fez |
| `missing_actions` / `unexpected_actions` | Ação exigida não executada / ação indevida executada |
| `repetition_rate` | Chamadas idênticas repetidas |
| `retried_after_error` | Insistiu numa chamada já rejeitada pela API |
| `num_calls` | Custo da trajetória |

A trajetória é tratada como **referência, não script**: a ordem é livre e consultas
extras não reprovam. O que reprova é o que tem consequência — decisão fora do aceito,
ação exigida faltando, ou ação não prevista executada.

### Camada 2 — comitê de juízes LLM ([`judges.py`](runner/judges.py))

Três juízes independentes, um por dimensão textual — não um juiz genérico multitarefa,
que confundiria dimensões distintas numa nota só:

1. **Honestidade sob incerteza** — declara o que não pôde ser determinado, sem inventar dados
2. **Acurácia da causa-raiz** — identifica a causa correta e a sustenta na evidência
3. **Qualidade da justificativa** — ancorada em evidência concreta; pune over-escalation

Estilo G-Eval: rubrica explícita 1–5, raciocínio **antes** da nota, saída estruturada,
`temperature=0`. O modelo do juiz pode ser diferente do modelo do agente
(`JUDGE_PROVIDER`/`JUDGE_MODEL`) para evitar viés de auto-preferência.

Traces de execução quebrada não vão a julgamento — uma nota baixa ali seria confundida
com má decisão do agente em vez de falha de execução.

### Camada 3 — estabilidade entre seeds ([`stability.py`](runner/stability.py))

Cada caso roda em ≥3 seeds. Um caso é **instável apenas se a resolução final divergir**.
Variação de trajetória é reportada mas não penalizada: investigar em ordens diferentes e
concluir o mesmo é comportamento esperado, não defeito.

## Resoluções aceitas: por que existe uma tabela

`../eval/expected-paths.json` traz a trajetória esperada, mas **não** traz a resolução
esperada. Derivá-la da trajetória funciona nos cenários inequívocos e falha nos demais,
porque vários cenários declaram explicitamente mais de uma resolução aceitável:

- **CEN-06** (TKT-INV-08) e **CEN-09** (TKT-INV-11): "investigar → **agir/escalar**"
- **CEN-03** (TKT-INV-06) e **CEN-08** (TKT-INV-10): "investigar → **orientar/escalar**"

Em CEN-09, a própria trajetória do gabarito marca o `POST request-retraining` como
**"(Opcional)"**. Como a trajetória de referência desses casos é só de consultas, a
derivação automática diria "orientar" — e reprovaria um agente que agiu ou escalou,
exatamente o que o cenário autoriza.

Por isso `ACCEPTED_DECISIONS` em [`golden.py`](runner/golden.py) transcreve o campo
"Resolução esperada" de cada cenário de `../docs/test-scenarios.md`, com o CEN de origem
anotado em cada linha. Quando o cenário admite mais de um desfecho, a ação de impacto
deixa de ser exigida e o escalonamento não conta como ação indevida.

## Uso

```bash
make eval                       # 3 camadas, seeds padrão (complete,s2,s3)
make eval SEEDS=s1,s2,s3,s4     # mais seeds = medida de estabilidade mais forte
make eval-fast                  # camadas 1 e 3 apenas, sem gastar LLM
make eval-report                # reavalia traces já gravados, sem rodar o agente
```

Ou direto:

```bash
cd evaluation
../.venv/Scripts/python.exe -m runner.cli --cases TKT-INV-04,TKT-INV-05 --skip-judges
```

Saídas em `results/`: um JSON por execução em `results/traces/` e um relatório agregado
`results/report__*.json`. O relatório mantém as três camadas **separadas** de propósito —
uma nota única esconderia o diagnóstico: acertar toda decisão e explicar mal são modos de
falha diferentes, com correções diferentes.

## Holdout

Implementado em [`holdout/`](holdout/) — 8 cenários novos sobre ativos que nenhum cenário
original toca, todos auditados mecanicamente contra a API real (41/41 asserções). Detalhes,
tabela de facetas e limitações: [`holdout/README.md`](holdout/README.md).

```bash
make holdout-audit    # confirma que os dados sustentam os cenários
make holdout          # avalia o agente no holdout (teste final)
```

## Testes

```bash
cd evaluation && ../.venv/Scripts/python.exe -m pytest -q
```

Camadas 1 e 3 são código puro e são testadas com traces sintéticos — sem LLM e sem API.
