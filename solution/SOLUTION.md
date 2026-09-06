# Solução — Engenharia e Avaliação de Agentes Industriais

Documentação técnica da minha solução para o Challenge TRACTIAN × Inteli. O briefing do
parceiro está em [`STUDENT-GUIDE.md`](../tractian/STUDENT-GUIDE.md); este documento cobre o que eu
construí.

> **Estado atual:** agente, avaliação e painel implementados; **102 execuções** com
> modelo real, em duas fases, e quatro experimentos registrados em
> [`docs/experimentos/`](./docs/experimentos/). O comitê de juízes está parcial (35/102,
> 2026-09-05), retomável, bloqueado por cota diária — ver [Pendências](#9-pendências).

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

A separação é física, não convenção: duas pastas irmãs, uma para cada dono.

```
inteli-tractian-project/
├── README.md                                  porta de entrada, aponta os dois lados
├── Makefile                                   compartilhado (TRAC vs SOL)
├── tractian/                                  DO PARCEIRO — nada editado
│   ├── README.md · STUDENT-GUIDE.md · QUICKSTART.md
│   ├── api/ · data/ · agent-input/ · eval/
│   └── docs/                                  contrato, chamados, cenários
└── solution/                                  MINHA
    ├── SOLUTION.md · docs/ (adr, experimentos)
    ├── agent/ · evaluation/ · painel/
    └── .run/                                  traces e CSVs das baterias
```

| Pasta | De quem | Regra |
| :--- | :--- | :--- |
| `tractian/api/`, `tractian/data/`, `tractian/docs/` | TRACTIAN | Não editados. A API é consumida só por HTTP |
| `tractian/agent-input/` | TRACTIAN | Única entrada de casos do agente |
| `tractian/eval/` | TRACTIAN (gabarito) | Lido exclusivamente por `solution/evaluation/runner/golden.py`, após a execução |
| `solution/agent/` | Minha | Parte 1 |
| `solution/evaluation/` | Minha | Parte 2 |
| `solution/painel/` | Minha | Parte 3 — painel de operação/avaliação sobre os traces já gravados. Somente leitura; a aba Operação não lê gabarito |

`api/` acompanha `data/`, `eval/` e `agent-input/` dentro de `tractian/` porque os
geradores do parceiro (`seed_data.py`, `package_material.py`) e a própria API resolvem
esses diretórios subindo um nível a partir de `api/`. Movê-los separadamente exigiria
editar código da Tractian — precisamente o que a primeira linha desta tabela proíbe.

No código, a fronteira aparece como constantes nomeadas — `SOLUTION_DIR`/`SOLUCAO` e
`TRACTIAN_DIR`/`TRACTIAN` — em vez de uma raiz única e ambígua. São quatro os pontos que a
cruzam (`cases.json`, `users.parquet` e o gabarito, lido em dois lugares); no Makefile, os
equivalentes são `SOL` e `TRAC`.

Dois ambientes virtuais: `tractian/api/.venv` (do parceiro) e `.venv` na raiz (minha solução).

## 4. Instalação e execução

Requisitos: Python ≥ 3.10, [`uv`](https://docs.astral.sh/uv/).

```bash
make setup                 # material da Tractian: venv da API + dados
make my-setup              # minha solução: .venv na raiz com solution/agent + evaluation

cp .env.example .env   # LLM_PROVIDER / LLM_MODEL / LLM_API_KEY
uv pip install --python .venv/Scripts/python.exe -e "./solution/agent[groq]"

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

**Hipótese central do projeto:** *nomear explicitamente na política de decisão **quando
orientar não basta** — em vez de descrever só as três categorias — aumenta a acurácia de
decisão do agente.* É a de
[EXP-01](./docs/experimentos/EXP-01-politica-de-decisao.md), a única testada com a bateria
inteira (51 pares, as duas fases) e a que motivou a correção de política que separa o
baseline da fase `pos-correcao`.

Onde a hipótese foi escrita depois dos dados, o documento diz isso no topo — e é o caso da
central: EXP-01 foi reconstruído sobre execuções que já existiam. Só EXP-02 foi desenhado
antes da coleta. A seção 8 trata do que isso custa em força de inferência.

## 7. Resultados

| # | Hipótese | n | Veredito |
| :--- | :--- | ---: | :--- |
| [01](./docs/experimentos/EXP-01-politica-de-decisao.md) | Nomear *quando orientar não basta* aumenta a acurácia | 51 pares | **sustentada** — 86,3% → 94,1%, 4 correções e 0 regressões, mas p ≈ 0,125 |
| [02](./docs/experimentos/EXP-02-politica-de-evidencia.md) | Apurar sempre os 4 pilares decide melhor | 6 pares | **refutada** — decisão idêntica par a par, custo 8% maior |
| [03](./docs/experimentos/EXP-03-enforcement-de-permissoes.md) | Deixar a API recusar é honesto e seguro | 5 × 403 | **sustentada** — 5/5 relataram a recusa, 0/5 insistiram |
| [04](./docs/experimentos/EXP-04-decisor-sem-tools.md) | Decidir sem tools custa 1 chamada, constante | 102 exec. | **sustentada** — 1,00/execução, 0 chamadas de API |

Bateria executada: **102 execuções** (17 cenários × 3 seeds × 2 fases), sem falha de
execução. Estabilidade entre seeds passou de 13/17 para **17/17** casos após a correção da
política de decisão.

O que está verificado por teste, e não por execução:

| Verificação | Status |
| :--- | :--- |
| Testes da API do parceiro (não quebrei nada) | 39 passando |
| Suíte do agente (integração, grafo, orçamentos, ADR 0002/0003) | 49 passando |
| Camadas 1 e 3 da avaliação + relatório | 55 passando |
| Holdout: integridade, disjunção e auditoria | 9 passando |
| Auditoria mecânica do holdout contra a API real | 41/41 asserções, 8/8 cenários |

## 8. Limitações

- **A camada 2 está parcial.** 35/102 execuções elegíveis julgadas pelo comitê em
  2026-09-05 (cota diária gratuita do OpenRouter esgotada, retomável). Toda afirmação de
  resultado das seções 6–7 é sobre decisão, trajetória e custo; qualidade textual —
  honestidade, causa-raiz, justificativa — só tem cobertura parcial até aqui.
- **Hipóteses formuladas após a coleta**, em EXP-01, 03 e 04 — inclusive a central. É
  HARKing, está declarado no topo de cada documento, e reduz a força da inferência: trate
  como evidência sugestiva, não confirmatória.
- **A arquitetura multiagente não foi comparada com um agente único.** A ADR 0001 é uma
  decisão de desenho justificada por argumento, não por experimento: nenhum dado deste
  projeto mostra que separar papéis decide melhor do que um agente único com as mesmas
  tools. Ver [Possibilidades de evolução](#10-possibilidades-de-evolução).
- **n pequeno e não independente.** Três seeds do mesmo caso não são três observações
  independentes: onde há taxas sobre 51 execuções, o n efetivo está mais perto de 17.
  Nenhum resultado atinge significância a 5% (EXP-01: p ≈ 0,125).
- **Cota de LLM moldou o desenho.** O n=6 de EXP-02 e a cobertura parcial da camada 2 são
  consequência do limite do plano gratuito, não de escolha metodológica.
- **Dados sintéticos.** Os 17 casos vêm de material fictício; generalização para
  operação real não está demonstrada.
- **Resoluções aceitas transcritas à mão.** A tabela `ACCEPTED_DECISIONS` foi lida de
  `tractian/docs/test-scenarios.md`; um erro de transcrição vira erro de medição. Está coberta por
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

1. **Rodar o comitê de juízes sobre `pos-correcao`** (`make painel-julgar`) — 51
   pendentes. As 35 já julgadas são **todas de `baseline`**, a versão anterior do agente:
   `julgar.py` não filtrava fase e servia a fila na ordem do bundle, onde `baseline` vem
   primeiro. O padrão agora é a fase de produção; `--fase baseline` é explícito. A fase
   `conditional` não precisa de juiz — o EXP-06 mede custo por contador. Retomar em lotes
   de 3–5 (`python solution/painel/julgar.py --limite 5 --modelo <id>`); lotes de ~20
   travaram sem erro nem progresso numa sessão de teste.
2. Calibrar o comitê: conferir à mão algumas notas antes de confiar nas médias. O veredito
   humano da página de leitura (⚙ Configuração → Retorno humano) grava exatamente esse
   rótulo, e é gratuito em tokens.
3. Rodar o holdout **uma única vez**, ao final, como teste de generalização.
4. Gravar `fase` no trace (`agent/app/trace.py`) — hoje a fase é recuperada por junção de
   tokens, garantia empírica e não estrutural (ver `painel/README.md`).
5. Corrigir os defeitos abertos de EXP-01 §4.4, ainda presentes na fase `pos-correcao`:
   ação exigida não executada (TKT-EXE-12, seeds `complete` e `s2`), `model_id` vazio na
   URL (TKT-EXE-15/s2) e ação não prevista nas três seeds de TKT-INV-05.

## 10. Possibilidades de evolução

Distinto da seção anterior: ali estão tarefas do escopo atual que ficaram por fazer; aqui,
extensões que o projeto não tentou.

- **Comparar a arquitetura com um agente único.** A ADR 0001 escolheu multiagente por
  argumento, e nenhuma medição deste projeto a confronta com o desenho alternativo mais
  óbvio: um agente só, com as mesmas tools e a mesma política de decisão. É o experimento
  mais informativo que falta, porque o resultado pode refutar a decisão de arquitetura
  central em vez de confirmá-la.
- **Validar fora do material sintético.** Os 17 casos são fictícios. Sem chamados reais
  (mesmo anonimizados), nada aqui demonstra transferência para operação — é a limitação
  que mais restringe as conclusões.
- **Ampliar o n e a independência.** Três seeds do mesmo caso não são três observações;
  mais casos distintos valem mais do que mais seeds, e é o que separaria as tendências
  observadas de resultado com significância.
- **Human-in-the-loop nas ações de impacto.** O contexto declarado é autônomo com escopo,
  e o teto é a permissão da API. Uma etapa de confirmação humana antes de `POST` mudaria o
  perfil de risco e é medível com as mesmas métricas de camada 1.
- **Medir latência e custo por caso.** Hoje o custo é contado em chamadas e tokens; tempo
  de resposta e custo monetário são o que decide viabilidade em atendimento real.
- **Juízes de famílias diferentes, com concordância entre eles.** O comitê atual usa um
  modelo por rodada. Rodar dois juízes independentes e reportar a concordância diria
  quanto da nota é sinal e quanto é idiossincrasia do juiz.
- **Memória entre interações.** O agente atende um caso por execução, sem histórico. O
  briefing lista memória e contexto entre interações como ponto relevante; atendimento
  multi-turno é a extensão natural.
