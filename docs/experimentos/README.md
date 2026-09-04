# docs/experimentos/ — metodologia experimental

Registro dos experimentos, no formato da seção 8 do
[`STUDENT-GUIDE.md`](../../STUDENT-GUIDE.md): **hipótese → método → execução → análise →
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
| [05](EXP-05-multiagente-vs-agente-unico.md) | Multiagente × agente único | Separar papéis reduz ação indevida e over-escalation | 0/51 | ⏳ **pendente de cota** |

## Como ler esta tabela

**EXP-05 é o experimento central** — é a hipótese que `SOLUTION.md` declara desde o início.
Os outros quatro foram reconstruídos sobre execuções que já existiam; só EXP-02 e EXP-05
foram desenhados como experimento antes da coleta.

Dois resultados merecem destaque porque contrariam a expectativa:

- **EXP-02 refutou uma intuição confortável** ("investigar mais é mais seguro") e a
  configuração em produção seguiu contrariando o resultado. O documento diz isso
  explicitamente em vez de omitir a incoerência.
- **EXP-01 melhorou a acurácia mas piorou duas execuções** em ação executada. O ganho não
  cobre tudo, e a seção 4.4 mostra as duas regressões em vez de reportar só a média.

## Limitações que atravessam todos

Valem para os cinco e não se repetem em cada documento:

- **Dados sintéticos.** 17 casos de material fictício; nada aqui demonstra generalização para
  operação real.
- **Um conjunto de modelos.** Toda a bateria roda com a mesma combinação qwen + gpt-oss, a
  `temperature=0`. Efeitos que dependam da capacidade do modelo não se separam da arquitetura.
- **Camada 2 nunca rodou.** 0 de 81 execuções elegíveis julgadas pelo comitê. Nenhum
  experimento aqui mede **qualidade textual** — honestidade, causa-raiz, justificativa.
  Toda afirmação é sobre decisão, trajetória e custo.
- **Cota de LLM como restrição de desenho.** O plano gratuito da Groq limita por minuto e por
  dia. Isso moldou o tamanho das amostras — n=6 em EXP-02 é consequência de cota, não de
  escolha metodológica — e é a razão de EXP-05 seguir pendente.
- **n pequeno e não independente.** Três seeds do mesmo caso não são três observações
  independentes. Onde reportei taxas sobre 51 execuções, o n efetivo está mais perto de 17.
