<div align="center">
  <img src="Assets/tractianLogo1.png" alt="TRACTIAN" height="52">
  <h1>Agente de Suporte Industrial</h1>
  <p><b>Challenge TRACTIAN × Inteli</b> — um agente que investiga chamados sobre máquinas industriais,
  decide o que fazer, e um sistema separado que mede se ele decidiu certo.</p>
</div>

---

## O que é

Alguém que opera uma planta abre um chamado: *"o motor da esteira está vibrando mais que o
normal desde ontem"*.

O agente recebe esse chamado, investiga usando a API industrial — dados do ativo, análises
anteriores, qualidade do sinal, cobertura do modelo — e termina em uma de três decisões:

| Decisão | O que significa |
| :--- | :--- |
| **orientar** | explicar, sem alterar nada na plataforma |
| **agir** | executar uma ação justificada (reprocessar análise, pedir retreinamento) |
| **escalar** | encaminhar para análise humana |

E um segundo sistema, independente, mede se essa decisão estava correta.

**Contexto de uso:** autônomo com escopo. O agente decide e executa sozinho, mas o teto do que
pode fazer é a permissão do usuário da sessão — imposta pela própria API com um `403`, não por
uma lista de bloqueios em código.

**Estado atual:** 102 execuções com modelo real, em duas fases, 4 experimentos registrados.
Estabilidade entre seeds em 17/17 casos. O comitê de juízes está parcial (35/102) — ver as
[limitações](solution/SOLUTION.md#8-limitações), que estão declaradas e não maquiadas.

---

## Colocando para rodar

Requisitos: **Python ≥ 3.10** e [`uv`](https://docs.astral.sh/uv/).

```bash
# 1. Instalar as duas metades (ambientes virtuais separados)
make setup       # material do parceiro: venv da API + geração dos dados
make my-setup    # minha solução: .venv na raiz

# 2. Configurar a chave de LLM
cp .env.example .env      # preencher LLM_PROVIDER / LLM_MODEL / LLM_API_KEY

# 3. Subir a API industrial
make up                   # http://localhost:8000  (Swagger em /docs)
```

Com isso no ar:

```bash
make agent-run CASE=TKT-INV-04 SEED=complete   # roda um caso e grava o trace
make eval-fast                                 # avaliação sem os juízes LLM (grátis)
make eval SEEDS=complete,s2,s3                 # avaliação completa
make painel                                    # painel de leitura em :8001
make my-test                                   # testes da solução
```

`make help` lista todos os alvos.

---

## Stack

| Camada | Tecnologia | Por quê |
| :--- | :--- | :--- |
| Orquestração | **LangGraph** | grafo explícito de papéis; permite fixar transições críticas em código, não em prompt |
| LLM | **Groq** (agentes) + **OpenRouter** (juízes) | provedores separados isolam as cotas e impedem que um juiz coincida com o gerador |
| Validação | **Pydantic** | schemas das ferramentas e saída estruturada dos juízes |
| API industrial | **FastAPI** | material do parceiro, consumido só por HTTP |
| Dados | **Parquet** + pandas | material do parceiro |
| Testes | **pytest** | 152 testes passando entre as suítes |
| Observabilidade | **LangSmith** (dev) + trace JSON local (avaliação) | inspeção humana e medição reproduzível têm requisitos diferentes |
| Painel | HTML/CSS/JS sem framework | página de leitura sobre traces já gravados; não precisa de build |

---

## A solução, em resumo

```
chamado → SUPERVISOR ─┬→ INVESTIGADOR      (dados do ativo)      ⇄ tools
                      ├→ CONTEXTUALIZADOR  (documentação)        ⇄ tools
                      └→ DECISOR           (decide — SEM tools)
                              │
                     orientar ┴ agir/escalar → EXECUTOR ⇄ tools
                              │
                              ▼
                        trace JSON local
                              │
                              ▼
              AVALIAÇÃO EM 3 CAMADAS
              1. determinística (código puro, grátis)
              2. comitê de 3 juízes LLM (um por dimensão)
              3. estabilidade entre seeds
```

Três decisões explicam a maior parte do desenho:

- **O Decisor não tem ferramentas.** Decidir é separado de apurar. Sem ferramentas não há laço,
  e ele custa exatamente 1 chamada de LLM por execução — constante, medida em 102 execuções.
- **A transição Decisor → Executor é fixa em código.** Nenhuma ação de impacto acontece sem
  decisão formal. É garantia estrutural, não confiança no prompt.
- **A permissão é imposta pela API, não bloqueada antes.** Bloquear cedo eliminaria justamente o
  comportamento avaliado: como o agente reage quando é recusado. Resultado: 5/5 relataram a
  recusa, 0/5 insistiram.

**O raciocínio completo — o que foi descartado e por quê — está em
[`ARCHITECTURE.md`](solution/docs/ARCHITECTURE.md).**

---

## Organização

O repositório tem **duas metades, e a separação é física** — não convenção:

```
inteli-tractian-project/
│
├── README.md                    você está aqui
├── Makefile                     alvos das duas metades (SOL vs TRAC)
├── .env.example                 variáveis necessárias
│
├── tractian/                    ══ DO PARCEIRO — nada editado ══
│   ├── STUDENT-GUIDE.md         o briefing do desafio
│   ├── api/                     API industrial (FastAPI)
│   ├── data/                    dados sintéticos (parquet)
│   ├── agent-input/             casos — única entrada do agente
│   ├── eval/                    gabarito — lido só APÓS a execução
│   └── docs/                    contrato, chamados, cenários
│
└── solution/                    ══ MINHA SOLUÇÃO ══
    ├── SOLUTION.md              documentação técnica e resultados
    ├── docs/
    │   ├── ARCHITECTURE.md      as decisões e o porquê de cada uma
    │   └── experimentos/        EXP-01 a EXP-07
    ├── agent/                   Parte 1 — o agente (LangGraph)
    ├── evaluation/              Parte 2 — avaliação em 3 camadas
    └── painel/                  Parte 3 — painel de leitura dos traces
```

**A regra que sustenta a separação:** nada em `tractian/` foi editado. A API é consumida só por
HTTP, e o gabarito é lido **depois** que o agente terminou — nunca durante. Se o agente visse o
gabarito, deixaria de raciocinar e passaria a procurá-lo, e toda a medição perderia o sentido.

No código a fronteira aparece como constantes distintas (`SOLUTION_DIR` e `TRACTIAN_DIR`); no
Makefile, como `SOL` e `TRAC`. São quatro os pontos que a cruzam.

| Quero... | Leio |
| :--- | :--- |
| entender o desafio proposto | [`tractian/STUDENT-GUIDE.md`](tractian/STUDENT-GUIDE.md) |
| entender as decisões de arquitetura | [`solution/docs/ARCHITECTURE.md`](solution/docs/ARCHITECTURE.md) |
| ver resultados e limitações | [`solution/SOLUTION.md`](solution/SOLUTION.md) |
| ver os experimentos | [`solution/docs/experimentos/`](solution/docs/experimentos/) |

---

## Desafios e aprendizados

**Fixar no código o que não pode depender do prompt.** A tentação inicial foi resolver tudo com
instrução: escrever no prompt que o agente não deve agir sem decidir antes. Prompt é
recomendação — um LLM pode ignorá-lo. A transição Decisor → Executor virou uma aresta do grafo,
e aí a garantia deixou de depender de boa vontade do modelo. Onde o risco é mexer numa máquina
industrial, a diferença entre "pedi para não fazer" e "não é possível fazer" é tudo.

**Deixar o sistema falhar é o que torna a falha mensurável.** Bloquear a ação sem permissão
parecia mais seguro, e teria destruído os três cenários que medem a coisa mais importante sobre
um agente autônomo: como ele reage quando é recusado. Admite, ou insiste e inventa que deu certo?
Segurança que apaga a evidência do próprio funcionamento não é segurança — é cegueira.

**Uma métrica sem gabarito pode dar um número ótimo e vazio.** Ao abrir a consulta de texto
livre, a camada determinística compararia o caminho tomado contra uma lista vazia e devolveria
`recall = 1.0`. Um número que parece excelente e não mede nada — pior do que não medir, porque
engana. A saída foi pular a camada explicitamente e gravar `null` com o motivo, em vez de
adaptá-la para produzir algo apresentável.

**Escrever a hipótese depois dos dados enfraquece a conclusão.** Três dos quatro experimentos
foram formulados sobre execuções que já existiam. Isso tem nome — HARKing — e o caminho honesto
foi declarar no topo de cada documento em vez de apresentar como se tivesse sido planejado. Foi o
aprendizado mais desconfortável: a diferença entre um resultado que sugere e um que demonstra
está no que veio antes, não em quão bom parece o número.

**A restrição de recurso apareceu no desenho, e admitir isso é parte do método.** O n=6 de um
experimento e a cobertura parcial do comitê são consequência da cota gratuita esgotada, não de
escolha metodológica. Racionalizar seria fácil; registrar como limitação é o que mantém o resto
confiável.

---

## Autoria

**Lucas Andrade Silva** — estudante do Inteli e membro do **Inteli Academy**, liga voltada a
Inteligência Artificial.

[LinkedIn](https://www.linkedin.com/in/lucas-andrade-sva/) · [GitHub](https://github.com/Lucas-Andrade-Silva)

Projeto individual desenvolvido para o Challenge TRACTIAN × Inteli. Todo o material em
`tractian/` é do parceiro e foi consumido sem edição; tudo em `solution/` é de minha autoria.
