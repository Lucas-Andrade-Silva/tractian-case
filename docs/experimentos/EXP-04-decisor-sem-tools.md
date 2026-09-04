# EXP-04 — O Decisor sem tools: separação de papéis com custo previsível

**Estado:** concluído · **n = 102 execuções** · **Dados:** `painel/dados/bundle.json` ·
**Registrado em:** 2026-09-04

> Observacional. Mede uma propriedade da arquitetura implantada; não compara contra a
> alternativa (um Decisor com tools), que nunca foi implementada. Ver
> [Limitações](#5-limitações), item 1.

## 1. Hipótese

> Um Decisor **sem tools** — que resolve o caso apenas sobre a evidência que os workers já
> apuraram, chegando pelos `findings` — consome exatamente **uma chamada de LLM por execução**,
> enquanto papéis com tools entram em laço (chama → recebe → reavalia → chama de novo) e
> consomem várias. Isso torna barato usar o modelo mais capaz justamente no papel cuja saída a
> avaliação de fato julga.

O argumento é estrutural antes de ser empírico: sem tools não há o que fazer voltar ao nó, logo
não há laço. A hipótese testável é que isso se traduz em **custo constante e previsível** — 1,00
chamada por execução, sem variância — e que a diferença em relação aos papéis com tools é
grande o bastante para justificar alocar ali o modelo caro.

Predição adicional, que serve de verificação da integridade da arquitetura: **nenhuma chamada
de API deve ter `papel = decisor`**. Se aparecesse alguma, a separação estaria furada.

## 2. Método

**Fonte.** As 102 execuções de [EXP-01](EXP-01-politica-de-decisao.md), somando por papel as
chamadas de LLM registradas em `token_usage.by_agent` e as chamadas de API registradas na
timeline do trace.

**Instrumentação.** `_structured()` usa `include_raw=True` para chegar ao `usage_metadata` —
sem isso, o custo do Supervisor e do Decisor (os dois papéis de saída estruturada) ficaria fora
da conta, e seriam justamente os mais chamados por caso.

**Métricas.** Chamadas de LLM por papel e por execução; tokens por papel; chamadas de API por
papel.

## 3. Execução

```bash
python - <<'PY'
import json, collections
d = json.load(open('painel/dados/bundle.json', encoding='utf-8'))
calls, api = collections.Counter(), collections.Counter()
for e in d['execucoes']:
    for papel, v in e['operacao']['consumo'].get('by_agent', {}).items():
        calls[papel] += v.get('calls', 0)
    for ev in e['operacao']['timeline']:
        if ev.get('tipo') == 'chamada':
            api[ev.get('papel')] += 1
n = len(d['execucoes'])
for papel in ('supervisor', 'investigador', 'contextualizador', 'decisor', 'executor'):
    print(f'{papel:18} {calls[papel]/n:5.2f} chamadas/exec   {api[papel]:4} chamadas de API')
PY
```

## 4. Resultados

### 4.1 Custo por papel, 102 execuções

| Papel | Chamadas de LLM | Por execução | Tokens/execução | Chamadas de API |
| :--- | ---: | ---: | ---: | ---: |
| supervisor | 250 | 2,45 | 3.718 | 102 |
| investigador | 234 | 2,29 | 7.745 | 543 |
| contextualizador | 204 | 2,00 | 3.544 | 155 |
| **decisor** | **102** | **1,00** | **2.430** | **0** |
| executor | 93 | 0,91 | 1.685 | 42 |

### 4.2 Leitura

**102 chamadas em 102 execuções: exatamente 1,00, sem uma única exceção.** Não é uma média que
esconde variância — é o mesmo valor em toda execução, que é o que a ausência de laço prevê. Os
papéis com tools ficam entre 2,00 e 2,45 por execução; o Investigador, que é quem mais consulta,
é também quem mais gasta em tokens (7.745/execução, 3,2× o Decisor).

**Zero chamadas de API com `papel = decisor`.** A predição de integridade se confirma nas 102
execuções: o Decisor nunca tocou a API. As 842 chamadas se distribuem entre investigador (543),
contextualizador (155), supervisor (102, todas o `GET /users/me` de contexto de autorização) e
executor (42).

O Decisor é, portanto, o papel **mais barato e mais previsível** do grafo — e é o que produz a
resolução e a justificativa, ou seja, exatamente o que a camada 1 compara contra o gabarito e o
que a camada 2 julgaria. Alocar ali o modelo mais capaz (`gpt-oss-120b`, enquanto os workers
rodam qwen) custa uma chamada por caso.

### 4.3 Veredito

**Hipótese sustentada.** O custo é constante em 1,00 chamada/execução, e a separação é
estruturalmente estanque (0 chamadas de API). O que o experimento **não** mostra é que essa
arquitetura decide melhor — só que ela decide barato. A pergunta sobre qualidade é a de
[EXP-05](EXP-05-multiagente-vs-agente-unico.md), que ainda não rodou.

Consequência prática registrada: a ausência da faixa do Decisor na timeline do painel é
**arquitetura funcionando**, não instrumentação faltando — e o painel a declara como legenda
em vez de deixar parecer lacuna.

## 5. Limitações

1. **Sem contrafactual.** Não existe braço com Decisor *com* tools. O número "2,00–2,45 chamadas
   dos papéis com tools" é uma comparação entre papéis que fazem trabalhos diferentes, não
   entre duas versões do mesmo papel. A afirmação "ter tools custaria mais" é uma inferência
   estrutural razoável, não um resultado medido.
2. **Custo não é qualidade.** O experimento mede consumo, e consumo baixo não é virtude se a
   decisão for pior. É inteiramente possível que um Decisor com acesso a uma consulta de
   confirmação decidisse melhor e valesse o custo — isto aqui não responde.
3. **1,00 é garantido por construção, não descoberto.** O nó do Decisor é chamado uma vez pelo
   grafo e não tem aresta de retorno. Confirmar 1,00 em 102 execuções valida a **instrumentação**
   e a ausência de caminho inesperado, mas o valor não poderia ter dado outra coisa sem um bug.
   O achado informativo aqui é o das 0 chamadas de API, não o do 1,00.
4. **Tokens por execução variam com o caso.** A média de 2.430 tokens do Decisor esconde
   dispersão: o prompt dele inclui todos os `findings`, que crescem com o quanto foi investigado.
   Não reportei o desvio.
5. **Uma configuração de modelos.** Com outro modelo no papel de Decisor, o custo em tokens
   mudaria; o número de chamadas, não.
