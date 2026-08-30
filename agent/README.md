# agent/ — Parte 1: o agente de suporte

Implementação própria do agente. Nada aqui veio da TRACTIAN.

## Fronteira com o material da TRACTIAN

| Pasta | De quem | Regra |
| :--- | :--- | :--- |
| `../api/`, `../data/`, `../docs/` | TRACTIAN | Consumidos; a API só por HTTP, nunca por import |
| `../agent-input/` | TRACTIAN | Única entrada de casos que o agente lê |
| `../eval/` | TRACTIAN (gabarito) | **O agente nunca lê.** Só `../evaluation/` acessa, após a execução |
| `agent/`, `../evaluation/` | Meu código | — |

O agente fala com o mundo exterior apenas por HTTP com a API industrial e por leitura de
`../agent-input/cases.json`. Nenhum módulo daqui importa de `../eval/`.

## Arquitetura

Multiagente com supervisor, em LangGraph ([ADR 0001](../docs/adr/0001-langgraph-multiagente-com-supervisor.md)):

```
START → supervisor ─┬→ investigador   ⇄ tools ─┐
                    ├→ contextualizador ⇄ tools ┼→ supervisor
                    └→ decisor ─┬→ (orientar) ─────────────→ END
                                └→ (agir|escalar) → executor ⇄ tools → END
```

| Papel | Responsabilidade | Tools |
| :--- | :--- | :--- |
| Supervisor | Roteia a cada turno; estabelece o contexto de autorização uma única vez (`GET /users/me`) | — |
| Investigador | Evidência técnica: ativo, análises, baseline, RMS, espectro, qualidade, modelo | 10 |
| Contextualizador | Evidência documental: procedimentos, glossário, orientações | 2 |
| Decisor | Pesa a evidência e resolve orientar/agir/escalar | nenhuma (por design) |
| Executor | Executa na plataforma a ação que o Decisor determinou | 5 |

**Roteamento híbrido** ([ADR 0002](../docs/adr/0002-roteamento-hibrido-transicao-fixa-para-executor.md)): o LLM
escolhe entre investigar, contextualizar e decidir; a transição Decisor → Executor é fixa
em código e só ocorre sobre uma decisão formal. Nenhuma ação de impacto pode acontecer
sem passar pelo Decisor — isso é garantido pela estrutura do grafo, não por prompt.

**Permissões** ([ADR 0003](../docs/adr/0003-enforcement-de-permissoes-via-api.md)): a política vive no
prompt; o enforcement é da API, que rejeita com 403. O agente não é bloqueado antes de
tentar — é assim que os cenários CEN-14/15/16 conseguem avaliar como ele reage a uma
recusa.

**Política de parada:** `MAX_SUPERVISOR_TURNS` e `MAX_WORKER_STEPS`. Ao estourar o
orçamento, o papel é chamado *sem tools*, o que o obriga a produzir texto e encerrar —
em vez de investigar indefinidamente sem nunca responder nem escalar.

## Módulos

| Arquivo | Papel |
| :--- | :--- |
| [`app/api_client.py`](app/api_client.py) | Único ponto de saída HTTP; grava o trace. Erros 4xx voltam como resultado, não exceção |
| [`app/tools.py`](app/tools.py) | Tools agrupadas por papel; descrições carregam o conhecimento de domínio |
| [`app/graph.py`](app/graph.py) | O grafo: nós, roteamento, orçamentos |
| [`app/prompts.py`](app/prompts.py) | Brief de domínio + prompt de cada papel + política de decisão |
| [`app/state.py`](app/state.py) | Estado do grafo e os contratos estruturados (`Route`, `Decision`) |
| [`app/trace.py`](app/trace.py) | Trace estruturado local, no formato do golden set |
| [`app/llm.py`](app/llm.py) | Binding do provedor — o único módulo que sabe qual LLM é usado |
| [`app/runner.py`](app/runner.py) | Executa um caso de ponta a ponta e salva o trace |

## Instalação e uso

```bash
make my-setup                        # cria .venv (raiz) e instala agent/ + evaluation/
cp agent/.env.example agent/.env     # e preencha LLM_PROVIDER / LLM_MODEL / LLM_API_KEY
uv pip install --python .venv/Scripts/python.exe -e "./agent[groq]"   # extra do provedor

make up                              # sobe a API industrial em :8000
make agent-list                      # lista os casos
make agent-run CASE=TKT-INV-04 SEED=complete
```

O `seed` torna o comportamento probabilístico da API determinístico — use-o sempre que
quiser reproduzir uma execução.

## Trace

Cada execução grava um JSON em `../evaluation/results/traces/`, com o campo `step` no
mesmo formato do golden set (`"GET /assets/asset_G501"`), qual papel fez cada chamada, o
`mode` do envelope, as decisões de roteamento, os achados de cada papel e a resolução
final. É esse arquivo — não o LangSmith — que a Parte 2 lê
([ADR 0004](../docs/adr/0004-trace-local-desacoplado-do-langsmith.md)).

## Testes

```bash
cd agent && ../.venv/Scripts/python.exe -m pytest -q
```

`tests/test_api_client.py` roda contra a API industrial real (pulado se ela não estiver
no ar); `tests/test_graph.py` usa um LLM roteirizado para verificar o cabeamento do grafo
sem depender de provedor.
