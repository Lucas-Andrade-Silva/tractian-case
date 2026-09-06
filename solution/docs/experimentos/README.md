# docs/experimentos/ — metodologia experimental

Registro dos experimentos, no formato da seção 8 do
[`STUDENT-GUIDE.md`](../../../tractian/STUDENT-GUIDE.md): **hipótese → método → execução → análise →
limitações**.

Cada arquivo é um experimento, e cada um declara honestamente o que prova e o que não prova.
Onde a hipótese foi escrita **depois** dos dados, isso está dito no topo do documento em vez
de escondido — é a diferença entre um experimento e uma narrativa construída sobre resultados
que já se tinha.

| # | Experimento | Hipótese em uma linha | n | Veredito |
| :--- | :--- | :--- | ---: | :--- |
| [01](EXP-01-politica-de-decisao.md) | Política de decisão | Nomear *quando orientar não basta* aumenta a acurácia de decisão | 51 pares | **sustentada** (4 correções, 0 regressões) — mas p ≈ 0,125 |
| [02](EXP-02-politica-de-evidencia.md) | Política de evidência | Apurar sempre os 4 pilares decide melhor que apurar sob demanda | 6 pares | **refutada** — decisão idêntica, custo 8% maior |
| [03](EXP-03-enforcement-de-permissoes.md) | Enforcement de permissão | Deixar a API recusar produz atendimento honesto sem insistência | 5 casos de 403 | **sustentada** (5/5 e 5/5), sem grupo de controle |
| [04](EXP-04-decisor-sem-tools.md) | Decisor sem tools | Decidir sem tools custa 1 chamada de LLM, constante | 102 execuções | **sustentada** — 1,00/execução, 0 chamadas de API |
| [07](EXP-07-sensibilidade-a-evidencia.md) | Sensibilidade à evidência | A decisão é causada pela evidência, não pelo enunciado do chamado | 12 (4 trios) | **sustentada** — 3/4 no desfecho primário, 0/4 no placebo |

## Como ler esta tabela

**EXP-01 é o experimento central** — é a hipótese que `SOLUTION.md` declara, e o único
rodado sobre a bateria inteira (as duas fases, 51 pares). Três dos quatro foram
reconstruídos sobre execuções que já existiam, a central inclusive; só EXP-02 foi desenhado
como experimento antes da coleta.

O que **não** está aqui: nenhum experimento compara a arquitetura multiagente com um agente
único. A ADR 0001 é decisão de desenho por argumento, não por medição — está registrado como
possibilidade de evolução em `SOLUTION.md` §10. O EXP-07 mede uma consequência dela sem
comparar arquiteturas: se o resumo em `findings` perde evidência no caminho do Investigador
para o Decisor. Não perdeu, em 4 de 4.

**EXP-07 é o único pré-registrado.** As previsões foram escritas e commitadas antes da
coleta, e a análise foi escrita contra elas sem reabrir a seção 5. É também o único que
separa *o agente acerta* de *o agente acerta pelo motivo certo*.

Dois resultados merecem destaque porque contrariam a expectativa:

- **EXP-02 refutou uma intuição confortável** ("investigar mais é mais seguro") e a
  configuração em produção seguiu contrariando o resultado. O documento diz isso
  explicitamente em vez de omitir a incoerência.
- **EXP-01 melhorou a acurácia mas piorou duas execuções** em ação executada. O ganho não
  cobre tudo, e a seção 4.4 mostra as duas regressões em vez de reportar só a média.

## Limitações que atravessam todos

Valem para os quatro e não se repetem em cada documento:

- **Dados sintéticos.** 17 casos de material fictício; nada aqui demonstra generalização para
  operação real.
- **Um conjunto de modelos.** Toda a bateria roda com a mesma combinação qwen + gpt-oss, a
  `temperature=0`. Efeitos que dependam da capacidade do modelo não se separam da arquitetura.
- **Camada 2 é parcial.** 35 de 102 execuções elegíveis julgadas pelo comitê (2026-09-05).
  Nenhum experimento aqui usa **qualidade textual** — honestidade, causa-raiz,
  justificativa — como critério: toda afirmação é sobre decisão, trajetória e custo.
- **Cota de LLM como restrição de desenho.** O plano gratuito da Groq limita por minuto e por
  dia. Isso moldou o tamanho das amostras — n=6 em EXP-02 é consequência de cota, não de
  escolha metodológica — e é a razão de a camada 2 seguir parcial.
- **n pequeno e não independente.** Três seeds do mesmo caso não são três observações
  independentes. Onde reportei taxas sobre 51 execuções, o n efetivo está mais perto de 17.
