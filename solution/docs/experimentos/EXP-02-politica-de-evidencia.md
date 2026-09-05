# EXP-02 — Política de evidência: apurar sempre os quatro pilares vs. apurar sob demanda

**Estado:** concluído, inconclusivo quanto ao desfecho primário · **n = 12 execuções**
(6 pares) · **Dados:** [`.run/exp_evidence.json`](../../.run/exp_evidence.json) ·
**Registrado em:** 2026-09-04

> Este é o único experimento do projeto que foi desenhado **como** experimento: dois braços,
> pareados, variando uma única coisa. Ficou sem registro escrito até agora.

## 1. Hipótese

> Obrigar o Investigador a apurar sempre os quatro pilares do ativo (`get_asset`,
> `get_baseline`, `get_data_quality`, `get_rms`) — política `fixed` — produz decisão mais
> acurada do que deixá-lo escolher o que apurar conforme o tipo da pergunta — política
> `conditional` —, ao custo de mais tokens.

As duas políticas são defensáveis a priori, e é isso que torna a pergunta empírica em vez de
uma questão de opinião:

- `fixed` argumenta que os quatro juntos são o que distingue *"sem dado nenhum"* de *"dado
  ruim"* de *"dado bom sem desvio"* — três situações que levam a conclusões diferentes. Faltar
  um deixa a investigação ambígua.
- `conditional` argumenta que uma pergunta conceitual (*"de onde vem o limiar?"*) não precisa
  de varredura de diagnóstico: apurar o que a explicação vai citar basta, e o resto é
  desperdício de contexto e de cota.

Ambas estão implementadas em `EVIDENCE_POLICIES`
([`agent/app/prompts.py`](../../agent/app/prompts.py)) e são selecionáveis por `EVIDENCE_POLICY`
no `.env` — a variável de experimento é uma linha de configuração, sem tocar em código.

## 2. Método

**Desenho.** Pareado por `(caso, seed)`, 2 casos × 3 seeds × 2 políticas = 12 execuções. Os dois
casos foram escolhidos por serem de **naturezas opostas**, que é onde a hipótese deveria
discriminar:

| Caso | Natureza | Por que entra |
| :--- | :--- | :--- |
| TKT-INV-04 | diagnóstico (*"por que não recebi aviso?"*) | as duas políticas mandam apurar os quatro pilares — braço de controle |
| TKT-CTX-03 | conceitual (*"de onde vem o limiar de RMS?"*) | `conditional` manda apurar menos — é aqui que as políticas divergem |

**Controles.** Mesmos modelos por papel, `temperature=0`, mesmas seeds, mesma API local. A única
diferença entre braços é o bloco de texto da política de evidência no prompt do Investigador.

**Métricas.** `decisao_ok` (desfecho primário), `passou`, `recall` de evidência, `total` de
tokens, `api` (chamadas). Coletadas em `.run/exp_evidence.json`.

**Critério de sucesso.** A hipótese só se sustenta se `fixed` **ganhar em decisão**. Se empatar
em decisão e perder em custo, a hipótese é refutada na sua parte que importa — a de que a
varredura completa compra acurácia.

## 3. Execução

```bash
EVIDENCE_POLICY=fixed        # 6 execuções → .run/traces_exp_fixed/
EVIDENCE_POLICY=conditional  # 6 execuções → .run/traces_exp_conditional/
```

12 execuções, nenhuma falha. Resultados agregados em `.run/exp_evidence.json`.

## 4. Resultados

### 4.1 Pareado, execução a execução

| Caso | Seed | `fixed` decisão / passou / recall / tokens | `conditional` decisão / passou / recall / tokens |
| :--- | :--- | :--- | :--- |
| TKT-INV-04 | complete | orientar · ✘ · 1,00 · 13.310 | orientar · ✘ · 1,00 · 11.288 |
| TKT-INV-04 | s2 | orientar · ✘ · 1,00 · 9.923 | orientar · ✘ · 1,00 · 11.309 |
| TKT-INV-04 | s3 | escalar · ✔ · 1,00 · 13.156 | escalar · ✔ · 1,00 · 14.527 |
| TKT-CTX-03 | complete | orientar · ✔ · 1,00 · 18.796 | orientar · ✔ · 0,75 · 18.572 |
| TKT-CTX-03 | s2 | orientar · ✔ · 1,00 · 19.007 | orientar · ✔ · 0,75 · 18.654 |
| TKT-CTX-03 | s3 | orientar · ✔ · 1,00 · 27.140 | orientar · ✔ · 0,75 · 18.814 |

### 4.2 Agregado

| Métrica | `fixed` | `conditional` |
| :--- | ---: | ---: |
| decisão correta | 4/6 | 4/6 |
| `passou` | 4/6 | 4/6 |
| recall médio | **1,000** | 0,875 |
| tokens (média) | 16.889 | **15.527** (−8,1%) |
| chamadas de API (média) | 7,50 | **6,67** (−11,1%) |

### 4.3 Leitura

**A decisão é idêntica nas seis execuções pareadas** — mesma resolução, mesmo `passou`, caso a
caso, não apenas na média. `conditional` chegou às mesmas conclusões consultando menos.

O recall menor de `conditional` (0,75 em TKT-CTX-03, nas três seeds) é **exatamente o
comportamento projetado**, não um defeito: num caso conceitual, ela deixa de fazer uma das
consultas de diagnóstico que o gabarito documenta. O ponto que a hipótese não previu é que
essa consulta a menos **não mudou a resposta**. Recall de evidência, aqui, mediu aderência ao
caminho de referência — não qualidade do desfecho.

O caso TKT-CTX-03/s3 é o mais ilustrativo: `fixed` gastou 27.140 tokens e 11 chamadas de API
contra 18.814 e 6 de `conditional` — 44% mais tokens para produzir a mesma resolução, com a
mesma aprovação.

### 4.4 Veredito

**Hipótese refutada na parte que importa.** `fixed` não comprou acurácia nenhuma: 4/6 nos dois
braços, decisão idêntica par a par. Comprou apenas recall — aderência ao gabarito — e pagou
8% em tokens e 11% em chamadas por isso.

Um resultado negativo, e útil: a intuição de que "investigar mais é mais seguro" não se
sustentou nestes 6 pares. Ela custa, e não se traduziu em decisão melhor.

**Mesmo assim, a configuração em produção permaneceu `fixed`** — todas as 102 execuções de
[EXP-01](EXP-01-politica-de-decisao.md) rodaram com `_evidence_policy: fixed`. A decisão é
defensável (n=6 é pouco para inverter um default conservador; recall alto ajuda a auditar o
agente), mas ela **não é sustentada por este experimento**, e seria desonesto apresentá-la como
se fosse. É uma escolha de cautela tomada apesar da evidência, não por causa dela.

## 5. Limitações

1. **n = 6 pares.** Dois casos e três seeds. É pequeno demais para refutar de forma definitiva:
   o experimento mostra que `fixed` não ajudou *nestes* casos, não que nunca ajuda. Com 6 pares
   e zero discordâncias em decisão, o intervalo de confiança sobre a diferença é largo e cobre
   folgadamente tanto vantagem quanto desvantagem para qualquer dos braços.
2. **Só duas naturezas de caso.** Um diagnóstico e um conceitual. Casos de ação direta
   (família TKT-EXE) e casos de conflito entre fontes ficaram de fora — e são justamente os
   que mais dependem de evidência completa. É plausível que `fixed` ganhe ali, e o experimento
   não olhou.
3. **`fixed` só perde onde as políticas divergem.** Em TKT-INV-04 as duas políticas prescrevem
   a mesma coisa, então metade da amostra é, por construção, um empate garantido. O n efetivo
   para a pergunta é **3 pares**, não 6.
4. **Recall contra gabarito não é medida de suficiência.** Um recall de 0,75 que produz a
   decisão certa e um de 1,00 que produz a errada valem o mesmo aqui. A métrica mede aderência
   ao caminho de referência, e este experimento é um caso em que isso e qualidade divergem.
5. **Sem julgamento textual.** Não foi avaliado se a resposta de `conditional` é *pior de ler*
   — menos citação de número concreto, menos fundamentação — mesmo chegando à mesma resolução.
   A camada 2 responderia isso e não rodou.
6. **Custo medido em tokens, não em latência ou dinheiro.** Modelos gratuitos com cota por
   minuto tornam a chamada de API, não o token, o recurso escasso na prática.

## 6. Reprodução

```bash
make up
# braço A
EVIDENCE_POLICY=fixed        make agent-run CASE=TKT-CTX-03 SEED=complete
# braço B
EVIDENCE_POLICY=conditional  make agent-run CASE=TKT-CTX-03 SEED=complete
```

Comparar os traces resultantes, ou reler o agregado já coletado:

```bash
python -c "import json;[print(r) for r in json.load(open('.run/exp_evidence.json',encoding='utf-8'))]"
```
