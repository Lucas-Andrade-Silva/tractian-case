# Solução — Engenharia e Avaliação de Agentes Industriais

Documentação técnica da minha solução para o Challenge TRACTIAN × Inteli. O briefing do
parceiro está em [`STUDENT-GUIDE.md`](../tractian/STUDENT-GUIDE.md); este documento cobre o que eu
construí.

> **Estado atual:** agente, avaliação e painel implementados; **204 execuções** com
> modelo real, em quatro fases, e sete experimentos registrados em
> [`docs/EXPERIMENTOS.md`](./docs/EXPERIMENTOS.md). O comitê de juízes está parcial (35/204,
> 2026-09-05, todas de `baseline`), retomável, bloqueado por cota diária — ver
> [Pendências](#9-pendências).
>
> ⚠️ A fase em produção é a `fixed-atual`, e ela **decide pior que a anterior**: 45/51 contra
> 48/51, com 15,5% menos tokens. O EXP-07 mede a troca; a decisão de reverter está aberta.

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

Consolidadas em [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md), que substitui os sete ADRs
originais e traz o raciocínio completo de cada uma — inclusive o que foi descartado e por quê.

| # | Decisão | Ponto não-óbvio |
| :--- | :--- | :--- |
| [0001](./docs/ARCHITECTURE.md#31-multiagente-com-supervisor-em-vez-de-um-agente-só) | Multiagente com supervisor, não agente único | Nenhum cenário *exige* a divisão; foi escolha deliberada de explorar separação de responsabilidades, com custo aceito de mais instrumentação |
| [0002](./docs/ARCHITECTURE.md#33-roteamento-híbrido-o-llm-decide-o-meio-o-código-decide-o-fim) | Roteamento híbrido | Decisor → Executor é fixo em código: nenhuma ação de impacto sem decisão formal, garantido estruturalmente |
| [0003](./docs/ARCHITECTURE.md#34-permissão-deixar-a-api-recusar-em-vez-de-bloquear-antes) | Permissão só no prompt, enforcement na API | Bloquear cedo eliminaria o comportamento que CEN-14/15/16 avaliam |
| [0004](./docs/ARCHITECTURE.md#35-trace-local-não-langsmith) | Trace local, não LangSmith | A avaliação não pode depender de serviço externo para ser reprodutível |
| [0005](./docs/ARCHITECTURE.md#36-avaliação-em-três-camadas-em-vez-de-um-método-só) | Avaliação em 3 camadas | Um juiz multitarefa confundiria dimensões distintas numa nota só |
| [0006](./docs/ARCHITECTURE.md#37-holdout-sintético-novo-em-vez-de-dividir-os-16-cenários) | Holdout sintético auditado | Dividir os 16 originais cortaria facetas não-redundantes do domínio |
| [0007](./docs/ARCHITECTURE.md#38-consulta-livre-gabarito-gerado-por-llm-em-métrica-separada) | Consulta livre com gabarito sintético | Sem gabarito a camada 1 daria `recall = 1.0` sobre conjunto vazio — número ótimo e vazio; é pulada, não adaptada |

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
    ├── SOLUTION.md · docs/ (ARCHITECTURE.md, EXPERIMENTOS.md)
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
| Juiz (camada 2) | groq | `qwen/qwen3.8-27b` | **Família diferente** do agente, para evitar viés de auto-preferência (ver ARCHITECTURE.md §3.6) |

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

Os experimentos estão em [`docs/EXPERIMENTOS.md`](./docs/EXPERIMENTOS.md), cada um no formato
da seção 8 do guia: hipótese → método → execução → análise → limitações.

**Hipótese central do projeto:** *nomear explicitamente na política de decisão **quando
orientar não basta** — em vez de descrever só as três categorias — aumenta a acurácia de
decisão do agente.* É a de
[EXP-01](./docs/EXPERIMENTOS.md#exp-01-política-de-decisão-tornar-explícito-quando-orientar-não-basta), a única testada com a bateria
inteira (51 pares, as duas fases) e a que motivou a correção de política que separa o
baseline da fase `pos-correcao`.

Onde a hipótese foi escrita depois dos dados, o documento diz isso no topo — e é o caso da
central: EXP-01 foi reconstruído sobre execuções que já existiam. Só EXP-02 foi desenhado
antes da coleta. A seção 8 trata do que isso custa em força de inferência.

## 7. Resultados

| # | Hipótese | n | Veredito |
| :--- | :--- | ---: | :--- |
| [01](./docs/EXPERIMENTOS.md#exp-01-política-de-decisão-tornar-explícito-quando-orientar-não-basta) | Nomear *quando orientar não basta* aumenta a acurácia | 51 pares | **sustentada** — 86,3% → 94,1%, 4 correções e 0 regressões, mas p ≈ 0,125 |
| [02](./docs/EXPERIMENTOS.md#exp-02-política-de-evidência-apurar-sempre-vs-apurar-sob-demanda) | Apurar sempre os 4 pilares decide melhor | 6 pares | **refutada** — decisão idêntica par a par, custo 8% maior |
| [03](./docs/EXPERIMENTOS.md#exp-03-enforcement-de-permissão-deixar-a-api-recusar) | Deixar a API recusar é honesto e seguro | 5 × 403 | **sustentada** — 5/5 relataram a recusa, 0/5 insistiram |
| [04](./docs/EXPERIMENTOS.md#exp-04-o-decisor-sem-tools) | Decidir sem tools custa 1 chamada, constante | 102 exec. | **sustentada** — 1,00/execução, 0 chamadas de API |
| [05](./docs/EXPERIMENTOS.md#exp-05-política-de-evidência-segunda-medição) | `conditional` economiza tokens | 18 pares | **refutada** — gastou 13% a 25% **mais**, sem mudar desfecho |
| [06](./docs/EXPERIMENTOS.md#exp-06-sensibilidade-à-evidência) | A decisão vem do dado, não do enunciado | 12 (4 trios) | **sustentada** — 3/4 no primário, 0/4 no placebo |
| [07](./docs/EXPERIMENTOS.md#exp-07-enxugar-o-prompt-do-supervisor-a-economia-que-custou-decisão) | Cortar o brief do Supervisor reduz custo sem custar decisão | 51 pares | **refutada** — −15,5% tokens, mas 3 regressões e 0 correções |

Bateria executada: **204 execuções** (17 cenários × 3 seeds × 4 fases). As fases `baseline`,
`pos-correcao` e `fixed-atual` rodaram completas sem falha; a `conditional` tem 18 de 51
concluídas (33 falhas de cota 429).

Estabilidade entre seeds: 13/17 na `baseline`, **17/17** após a correção da política de
decisão — e **15/17** na `fixed-atual`, a fase em produção. O ganho não se reproduziu sob a
mudança de prompt do EXP-07, e os dois casos que voltaram a oscilar são os mesmos que
produziram as três regressões de decisão.

O que está verificado por teste, e não por execução:

| Verificação | Status |
| :--- | :--- |
| Testes da API do parceiro (não quebrei nada) | 39 passando |
| Suíte do agente (integração, grafo, orçamentos, decisões §3.3/§3.4) | 49 passando |
| Camadas 1 e 3 da avaliação + relatório | 55 passando |
| Holdout: integridade, disjunção e auditoria | 9 passando |
| Auditoria mecânica do holdout contra a API real | 41/41 asserções, 8/8 cenários |

## 8. Limitações

- **A camada 2 está parcial.** 35/204 execuções julgadas pelo comitê em 2026-09-05, **todas
  da fase `baseline`** (cota diária gratuita do OpenRouter esgotada, retomável). Toda
  afirmação de resultado das seções 6–7 é sobre decisão, trajetória e custo; qualidade
  textual — honestidade, causa-raiz, justificativa — não tem cobertura na fase em produção.
  Isso pesa especialmente no EXP-07: o bloco de prompt que ele avalia foi escrito para
  melhorar a legibilidade da resposta, que é exatamente o que nenhuma métrica atual mede.
- **Hipóteses formuladas após a coleta**, em EXP-01, 03, 04, 05 e 07 — inclusive a central.
  É HARKing, está declarado no topo de cada documento, e reduz a força da inferência: trate
  como evidência sugestiva, não confirmatória.
- **A configuração em produção não é a de melhor acurácia.** A fase `fixed-atual` decide
  45/51 contra os 48/51 da `pos-correcao`, e perdeu a estabilidade 17/17. Está em produção
  porque é a mais recente, não porque mediu melhor — e a mudança que causou isso agregou
  duas alterações de prompt num commit só, o que impede saber qual delas custou as três
  decisões. Ver EXP-07 §7.6.
- **A arquitetura multiagente não foi comparada com um agente único.** A decisão §3.1 é de
  desenho, justificada por argumento, não por experimento: nenhum dado deste
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
  parquets são majoritariamente saudáveis e a decisão §3.7 proíbe estendê-los. A acurácia de
  decisão no holdout não deve ser lida isoladamente — detalhes e mitigação em
  [`evaluation/holdout/README.md`](./evaluation/holdout/README.md).
- **Escalonamento bem-sucedido não é testável no holdout**: a API valida permissão antes
  de procurar o caso, e casos de holdout não existem em `data/cases.parquet` (404). Só o
  caminho 403 é observável.
- **`escalate_case` opera sobre o caso da sessão**, coerente com o contrato da API.

## 9. Pendências

1. **Separar as duas mudanças de prompt do EXP-07** — a pendência mais urgente, porque a
   configuração em produção decide pior que a anterior e não se sabe qual das duas alterações
   causou isso. Braço A devolve o `DOMAIN_BRIEF` ao Supervisor mantendo o `_VOZ_AO_CLIENTE`;
   braço B faz o inverso. 51 pares cada, mesma bateria. Ver EXP-07 §7.6.
2. **Rodar o comitê de juízes sobre a fase em produção** (`make painel-julgar`) — 51
   pendentes. As 35 já julgadas são **todas de `baseline`**, a versão anterior do agente:
   `julgar.py` não filtrava fase e servia a fila na ordem do bundle, onde `baseline` vem
   primeiro. O padrão agora é a fase de produção; `--fase baseline` é explícito. A fase
   `conditional` não precisa de juiz — o EXP-05 mede custo por contador. Retomar em lotes
   de 3–5 (`python solution/painel/julgar.py --limite 5 --modelo <id>`); lotes de ~20
   travaram sem erro nem progresso numa sessão de teste.
3. Calibrar o comitê: conferir à mão algumas notas antes de confiar nas médias. O veredito
   humano da página de leitura (⚙ Configuração → Retorno humano) grava exatamente esse
   rótulo, e é gratuito em tokens. Pesa mais agora: o EXP-07 mexeu num prompt escrito para
   melhorar a legibilidade da resposta, e nenhuma métrica atual sabe medir isso.
4. Rodar o holdout **uma única vez**, ao final, como teste de generalização.
5. Completar a bateria `conditional` — 18 de 51 concluídas, 33 falhas de cota 429. Sem ela,
   o EXP-05 continua indicativo.
6. Corrigir os defeitos abertos de EXP-01 §4.4, ainda presentes nas fases posteriores:
   ação exigida não executada (TKT-EXE-12, seeds `complete` e `s2`), `model_id` vazio na
   URL (TKT-EXE-15/s2) e ação não prevista nas três seeds de TKT-INV-05.

## 10. Possibilidades de evolução

Distinto da seção anterior: ali estão tarefas do escopo atual que ficaram por fazer; aqui,
extensões que o projeto não tentou.

- **Comparar a arquitetura com um agente único.** A decisão §3.1 escolheu multiagente por
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
