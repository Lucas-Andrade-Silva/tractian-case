# Solução — Engenharia e Avaliação de Agentes Industriais

Documentação técnica da minha solução para o Challenge TRACTIAN × Inteli. O briefing do
parceiro está em [`STUDENT-GUIDE.md`](./STUDENT-GUIDE.md); este documento cobre o que eu
construí.

> **Estado atual:** agente, avaliação e painel implementados; **102 execuções** com
> modelo real, em duas fases, e cinco experimentos registrados em
> [`docs/experimentos/`](./docs/experimentos/). Faltam a bateria de EXP-05 (a hipótese
> central) e o comitê de juízes — ambos bloqueados por cota, ver
> [Pendências](#9-pendências).

## 1. Problema e recorte

Uma solicitação de suporte sobre uma máquina industrial pode exigir dados do ativo,
análises anteriores, qualidade dos sinais, cobertura do modelo e ações na plataforma. O
agente recebe a solicitação, investiga usando a API industrial e decide entre
**orientar**, **agir** ou **escalar**.

**Contexto de uso declarado:** autônomo com escopo. O agente decide e executa sozinho,
mas o teto do que pode fazer é a permissão do usuário da sessão, imposta pela própria API
(403), não por uma lista de bloqueios em código.

## 2. Arquitetura

```
agent-input/cases.json
        │
        ▼
┌─────────────────────────────────────────────┐
│  Grafo LangGraph (agent/app/graph.py)       │
│                                             │
│  supervisor ─┬→ investigador   ⇄ tools ─┐   │
│              ├→ contextualizador ⇄ tools ┼──┘
│              └→ decisor ─┬→ orientar → END  │
│                          └→ agir|escalar    │
│                              → executor ⇄ tools → END
└──────────────────┬──────────────────────────┘
                   │ HTTP (agent/app/api_client.py)
                   ▼
       API industrial Tractian (:8000)
                   │
                   ▼
        trace JSON (evaluation/results/traces/)
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Avaliação em 3 camadas (evaluation/)       │
│  1. determinística  vs eval/expected-paths  │
│  2. comitê de 3 juízes LLM (G-Eval)         │
│  3. estabilidade entre seeds                │
└──────────────────┬──────────────────────────┘
                   ▼
          relatório agregado (JSON)
```

Detalhes de cada parte: [`agent/README.md`](./agent/README.md) e
[`evaluation/README.md`](./evaluation/README.md).

### Decisões de arquitetura

Registradas como ADRs em [`docs/adr/`](./docs/adr/):

| ADR | Decisão | Ponto não-óbvio |
| :--- | :--- | :--- |
| [0001](./docs/adr/0001-langgraph-multiagente-com-supervisor.md) | Multiagente com supervisor, não agente único | Nenhum cenário *exige* a divisão; foi escolha deliberada de explorar separação de responsabilidades, com custo aceito de mais instrumentação |
| [0002](./docs/adr/0002-roteamento-hibrido-transicao-fixa-para-executor.md) | Roteamento híbrido | Decisor → Executor é fixo em código: nenhuma ação de impacto sem decisão formal, garantido estruturalmente |
| [0003](./docs/adr/0003-enforcement-de-permissoes-via-api.md) | Permissão só no prompt, enforcement na API | Bloquear cedo eliminaria o comportamento que CEN-14/15/16 avaliam |
| [0004](./docs/adr/0004-trace-local-desacoplado-do-langsmith.md) | Trace local, não LangSmith | A avaliação não pode depender de serviço externo para ser reprodutível |
| [0005](./docs/adr/0005-piramide-de-avaliacao-em-tres-camadas.md) | Avaliação em 3 camadas | Um juiz multitarefa confundiria dimensões distintas numa nota só |
| [0006](./docs/adr/0006-holdout-sintetico-auditado.md) | Holdout sintético auditado | Dividir os 16 originais cortaria facetas não-redundantes do domínio |

## 3. Separação entre material do parceiro e solução própria

| Pasta | De quem | Regra |
| :--- | :--- | :--- |
| `api/`, `data/`, `docs/` | TRACTIAN | Não editados. A API é consumida só por HTTP |
| `agent-input/` | TRACTIAN | Única entrada de casos do agente |
| `eval/` | TRACTIAN (gabarito) | Lido exclusivamente por `evaluation/runner/golden.py`, após a execução |
| `agent/` | Minha | Parte 1 |
| `evaluation/` | Minha | Parte 2 |
| `painel/` | Minha | Parte 3 — painel de operação/avaliação sobre os traces já gravados. Somente leitura; a aba Operação não lê gabarito |

Dois ambientes virtuais: `api/.venv` (do parceiro) e `.venv` na raiz (minha solução).

## 4. Instalação e execução

Requisitos: Python ≥ 3.10, [`uv`](https://docs.astral.sh/uv/).

```bash
make setup                 # material da Tractian: venv da API + dados
make my-setup              # minha solução: .venv na raiz com agent/ + evaluation/

cp agent/.env.example agent/.env      # preencher LLM_PROVIDER / LLM_MODEL / LLM_API_KEY
uv pip install --python .venv/Scripts/python.exe -e "./agent[groq]"

make up                                        # API industrial em :8000
make agent-run CASE=TKT-INV-04 SEED=complete   # um caso
make eval SEEDS=complete,s2,s3                 # avaliação completa
make eval-fast                                 # sem os juízes LLM
make my-test                                   # testes da minha solução
```

## 5. Modelos e configurações

O provedor é isolado em [`agent/app/llm.py`](./agent/app/llm.py) — trocar de modelo, ou
comparar dois no experimento, é mudar `.env` sem tocar em mais nada. Suportados: `groq`,
`openai` (extras opcionais no `pyproject.toml`).

| Papel | Provedor | Modelo | Por quê |
| :--- | :--- | :--- | :--- |
| Agente | groq | `openai/gpt-oss-120b` | Maior modelo disponível na conta com tool calling + structured output, ambos exigidos pelo grafo |
| Juiz (camada 2) | groq | `qwen/qwen3.8-27b` | **Família diferente** do agente, para evitar viés de auto-preferência (ADR 0005) |

Ambos validados por smoke test: structured output e tool calling confirmados contra a API
da Groq antes de qualquer execução de caso.

`temperature=0.0` por padrão, no agente e nos juízes: a camada 3 mede estabilidade entre
execuções, e variação amostral do decoder seria confundida com instabilidade do agente.

| Config | Padrão | Efeito |
| :--- | :--- | :--- |
| `MAX_SUPERVISOR_TURNS` | 12 | Teto de turnos de roteamento |
| `MAX_WORKER_STEPS` | 6 | Teto de rodadas de tool-calling por papel |
| `JUDGE_PROVIDER` / `JUDGE_MODEL` | herda do agente | Permite juiz diferente do agente |

## 6. Metodologia experimental

Os experimentos estão em [`docs/experimentos/`](./docs/experimentos/), cada um no formato
da seção 8 do guia: hipótese → método → execução → análise → limitações.

**Hipótese central do projeto:** *separar investigação de decisão — o Decisor não tem tools
e só recebe evidência já apurada — reduz ações de impacto sem fundamento e reduz
over-escalation, ao custo de mais chamadas por caso.* É a de
[EXP-05](./docs/experimentos/EXP-05-multiagente-vs-agente-unico.md), o único ainda pendente:
o braço de agente único está implementado e testado, e falta cota de LLM para rodar as 51
execuções.

Onde a hipótese foi escrita depois dos dados, o documento diz isso no topo. Quatro dos cinco
experimentos foram reconstruídos sobre execuções que já existiam; só EXP-02 e EXP-05 foram
desenhados antes da coleta.

## 7. Resultados

| # | Hipótese | n | Veredito |
| :--- | :--- | ---: | :--- |
| [01](./docs/experimentos/EXP-01-politica-de-decisao.md) | Nomear *quando orientar não basta* aumenta a acurácia | 51 pares | **sustentada** — 86,3% → 94,1%, 4 correções e 0 regressões, mas p ≈ 0,125 |
| [02](./docs/experimentos/EXP-02-politica-de-evidencia.md) | Apurar sempre os 4 pilares decide melhor | 6 pares | **refutada** — decisão idêntica par a par, custo 8% maior |
| [03](./docs/experimentos/EXP-03-enforcement-de-permissoes.md) | Deixar a API recusar é honesto e seguro | 5 × 403 | **sustentada** — 5/5 relataram a recusa, 0/5 insistiram |
| [04](./docs/experimentos/EXP-04-decisor-sem-tools.md) | Decidir sem tools custa 1 chamada, constante | 102 exec. | **sustentada** — 1,00/execução, 0 chamadas de API |
| [05](./docs/experimentos/EXP-05-multiagente-vs-agente-unico.md) | Separar papéis reduz ação indevida | 0/51 | ⏳ pendente de cota |

Bateria executada: **102 execuções** (17 cenários × 3 seeds × 2 fases), sem falha de
execução. Estabilidade entre seeds passou de 13/17 para **17/17** casos após a correção da
política de decisão.

O que está verificado por teste, e não por execução:

| Verificação | Status |
| :--- | :--- |
| Testes da API do parceiro (não quebrei nada) | 39 passando |
| Suíte do agente (integração, grafo, orçamentos, ADR 0002/0003) | 33 passando |
| Braço de agente único (EXP-05) | 4 passando |
| Camadas 1 e 3 da avaliação + relatório | 21 passando |
| Holdout: integridade, disjunção e auditoria | 9 passando |
| Auditoria mecânica do holdout contra a API real | 41/41 asserções, 8/8 cenários |

## 8. Limitações

- **A camada 2 nunca rodou.** 0 de 81 execuções elegíveis foram julgadas pelo comitê.
  Nada aqui mede qualidade textual — honestidade, causa-raiz, justificativa. Toda
  afirmação de resultado é sobre decisão, trajetória e custo.
- **Hipóteses formuladas após a coleta**, em EXP-01, 03 e 04. É HARKing, está declarado no
  topo de cada documento, e reduz a força da inferência: trate como evidência sugestiva,
  não confirmatória.
- **n pequeno e não independente.** Três seeds do mesmo caso não são três observações
  independentes: onde há taxas sobre 51 execuções, o n efetivo está mais perto de 17.
  Nenhum resultado atinge significância a 5% (EXP-01: p ≈ 0,125).
- **Cota de LLM moldou o desenho.** O n=6 de EXP-02 e a pendência de EXP-05 são
  consequência do limite do plano gratuito, não de escolha metodológica.
- **Dados sintéticos.** Os 17 casos vêm de material fictício; generalização para
  operação real não está demonstrada.
- **Resoluções aceitas transcritas à mão.** A tabela `ACCEPTED_DECISIONS` foi lida de
  `docs/test-scenarios.md`; um erro de transcrição vira erro de medição. Está coberta por
  teste que exige uma entrada por caso do gabarito.
- **Camada 2 depende de LLM** — juízes LLM têm variância e viés próprios; a rubrica e o
  `temperature=0` mitigam, não eliminam.
- **Holdout desbalanceado** (5 orientar · 2 agir · 1 escalar): os ativos livres nos
  parquets são majoritariamente saudáveis e o ADR 0006 proíbe estendê-los. A acurácia de
  decisão no holdout não deve ser lida isoladamente — detalhes e mitigação em
  [`evaluation/holdout/README.md`](./evaluation/holdout/README.md).
- **Escalonamento bem-sucedido não é testável no holdout**: a API valida permissão antes
  de procurar o caso, e casos de holdout não existem em `data/cases.parquet` (404). Só o
  caminho 403 é observável.
- **`escalate_case` opera sobre o caso da sessão**, coerente com o contrato da API.

## 9. Pendências

1. **Rodar EXP-05** (`make exp05`) — braço de agente único, 51 execuções. Implementado e
   testado; falta cota. É a hipótese central do projeto.
2. **Rodar o comitê de juízes** (`make painel-julgar`) — 0 de 81 julgadas. Sem isso, a
   camada 2 da pirâmide de avaliação existe em código mas não produziu nenhum dado.
3. Calibrar o comitê: conferir à mão algumas notas antes de confiar nas médias.
4. Rodar o holdout **uma única vez**, ao final, como teste de generalização.
5. Gravar `fase` no trace (`agent/app/trace.py`) — hoje a fase é recuperada por junção de
   tokens, garantia empírica e não estrutural (ver `painel/README.md`).
6. Corrigir os dois defeitos abertos de EXP-01 §4.4: ação exigida não executada
   (TKT-EXE-12/s2) e `model_id` vazio na URL (TKT-EXE-15/s2).
