# Solução — Engenharia e Avaliação de Agentes Industriais

Documentação técnica da minha solução para o Challenge TRACTIAN × Inteli. O briefing do
parceiro está em [`STUDENT-GUIDE.md`](./STUDENT-GUIDE.md); este documento cobre o que eu
construí.

> **Estado atual:** agente e avaliação implementados e testados. Falta escolher o
> provedor de LLM (`agent/.env`) para rodar de ponta a ponta com um modelo real — ver
> [Pendências](#pendências).

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

**Hipótese** (a testar quando o provedor estiver configurado): *separar investigação de
decisão — o Decisor não tem tools e só recebe evidência já apurada — reduz ações de
impacto sem fundamento e reduz over-escalation, ao custo de mais chamadas por caso.*

**Método:** rodar os 17 casos com ≥3 seeds; camada 1 mede decisão, ações indevidas e
custo; camada 2 mede honestidade, causa-raiz e justificativa; camada 3 mede estabilidade.
A comparação natural é contra uma variante de agente único (mesmas tools, sem separação
de papéis), mantendo modelo e seeds fixos.

**Execução, análise e limitações:** pendentes da configuração do provedor.

## 7. Resultados

Ainda não há resultados com modelo real. O que já está verificado:

| Verificação | Status |
| :--- | :--- |
| Testes da API do parceiro (não quebrei nada) | 39 passando |
| Integração HTTP + tools contra a API real | 9 passando |
| Cabeamento do grafo, orçamentos, ADR 0002 e ADR 0003 | 5 passando |
| Camadas 1 e 3 da avaliação + relatório | 21 passando |
| Holdout: integridade, disjunção e auditoria | 9 passando |
| Auditoria mecânica do holdout contra a API real | 41/41 asserções, 8/8 cenários |
| Pipeline de avaliação de ponta a ponta | verificado com traces reais do grafo |

## 8. Limitações

- **Sem execução com LLM real ainda** — nenhuma afirmação sobre qualidade do agente pode
  ser feita antes disso. Os testes verificam estrutura e integração, não comportamento.
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

1. Rodar os 17 casos × ≥3 seeds e produzir o primeiro relatório real (golden set).
2. Calibrar o comitê de juízes: conferir à mão algumas notas antes de confiar nas médias.
3. Rodar o experimento da hipótese (multiagente × agente único) e escrever a análise.
4. Rodar o holdout **uma única vez**, ao final, como teste de generalização.
