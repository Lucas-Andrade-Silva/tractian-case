# Makefile — Challenge TRACTIAN x Inteli
# Sobe tudo que você precisa para testar o agente de ponta a ponta.
#
# Uso típico:
#   make setup           # 1x: cria venv e instala deps (api + agente)
#   make data            # 1x: gera tractian/{data,agent-input,eval}
#   make agent-env       # 1x: cria solution/agent/.env a partir do example (edite a key)
#   make up              # sobe API industrial (:8000) + agente/UI (:8001) em background
#   make stop            # para os dois
#   make logs            # vê logs dos dois
#
# Variáveis (override: make VAR=val ...):
PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)
API_PORT ?= 8000
AGENT_PORT ?= 8001
ROOT := $(abspath $(dir $(MAKEFILE_LIST)))
# As duas metades do repositório, cada uma com seu dono: `TRAC` é o material do parceiro
# (api/, data/, eval/, agent-input/, docs/) e `SOL` é a minha solução. Nenhum alvo deve
# escrever do outro lado da fronteira.
TRAC := $(ROOT)/tractian
SOL := $(ROOT)/solution
VENV := $(TRAC)/api/.venv
PY := $(shell test -f "$(VENV)/Scripts/python.exe" && echo "$(VENV)/Scripts/python.exe" || echo "$(VENV)/bin/python")
PID_DIR := $(SOL)/.run
MAKEFLAGS += --no-print-directory

.DEFAULT_GOAL := help

.PHONY: help setup deps data agent-env up up-api up-agent up-all stop logs test clean clean-data \
	my-setup agent-list agent-run eval eval-fast eval-report holdout-audit holdout my-test \
	painel-dados painel-completar painel-julgar painel-modelos consulta leitura leitura-dados \
	experimentos exp07

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup (1x)
# ---------------------------------------------------------------------------
setup: deps data ## Tudo que o aluno precisa: venv+deps e dados (API + pacotes)

deps: ## Cria o venv e instala dependências da API
	@command -v uv >/dev/null 2>&1 || { echo "Instale o uv: https://docs.astral.sh/uv/"; exit 1; }
	@cd $(TRAC)/api && uv venv --python $(PYTHON) && uv pip install -e ".[dev]"
	@echo "✓ dependências instaladas em $(VENV)"

# ---------------------------------------------------------------------------
# Dados (1x, ou ao mudar seed_data.py / package_material.py)
# ---------------------------------------------------------------------------
data: ## Gera data/*.parquet, agent-input/, eval/
	@cd $(TRAC)/api && $(PY) -m seed_data
	@cd $(TRAC)/api && $(PY) -m package_material
	@echo "✓ dados gerados (data/, agent-input/, eval/)"

agent-env: ## Cria agent/.env a partir do .env.example (edite a API key depois)
	@if [ ! -f $(SOL)/agent/.env ]; then cp $(SOL)/agent/.env.example $(SOL)/agent/.env && echo "✓ solution/agent/.env criado — edite OPENAI_API_KEY/BASE_URL/MODEL"; else echo "✓ solution/agent/.env já existe (não sobrescrito)"; fi

# ---------------------------------------------------------------------------
# Rodar (background)
# ---------------------------------------------------------------------------
# `up` sobe só a API industrial.
# `up-all` sobe também o seu agente/UI (agent/), quando você o tiver criado.
up: up-api ## Sobe a API industrial (:8000) em background
	@echo ""
	@echo "✓ API no ar:"
	@echo "   Swagger UI: http://localhost:$(API_PORT)/docs"
	@echo "(make stop para parar · make logs para ver saída)"

up-all: up-api up-agent ## Sobe API + seu agente/UI (:8001)
	@echo ""
	@echo "✓ Tudo no ar:"
	@echo "   API industrial (Swagger): http://localhost:$(API_PORT)/docs"
	@echo "   Agente / UI de chat:      http://localhost:$(AGENT_PORT)"
	@echo "(make stop para parar · make logs para ver saída)"

# Espera até ~10s por uma porta responder HTTP 200 (evita falsos negativos de "sleep fixo").
define wait_up
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		curl -s -o /dev/null http://localhost:$(1) && break; sleep 1; \
	done
endef

up-api: ## Só a API industrial (:8000) em background
	@mkdir -p $(PID_DIR)
	@cd $(TRAC)/api && $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT) \
		> $(PID_DIR)/api.log 2>&1 & echo $$! > $(PID_DIR)/api.pid
	$(call wait_up,$(API_PORT))
	@curl -s -o /dev/null -w "✓ API industrial em :$(API_PORT) (HTTP %{http_code})\n" http://localhost:$(API_PORT)/docs \
		|| echo "✗ API não subiu — veja $(PID_DIR)/api.log"

up-agent: up-api ## (n/a) O agente desta solução é CLI, não servidor — use `make agent-run`
	@echo ""
	@echo "O agente implementado aqui roda por caso (contexto autônomo com escopo), não como"
	@echo "servidor HTTP em :$(AGENT_PORT). Use:"
	@echo "   make agent-list              # lista os casos"
	@echo "   make agent-run CASE=TKT-INV-04 SEED=complete"

stop: ## Para API industrial e agente
	@for f in $(PID_DIR)/api.pid $(PID_DIR)/agent.pid; do \
		if [ -f $$f ]; then kill $$(cat $$f) 2>/dev/null && echo "✓ parado $$(basename $$f .pid)"; rm -f $$f; fi; \
	done
	@# mata sobras por nome (caso os pids tenham sumido)
	@-pkill -f "uvicorn app.main:app --host 127.0.0.1 --port $(API_PORT)" 2>/dev/null || true
	@-pkill -f "solution/agent/server.py" 2>/dev/null || true

logs: ## Mostra logs da API e do agente (tail -f)
	@echo "== API ==		== Agente =="
	@tail -f $(PID_DIR)/api.log $(PID_DIR)/agent.log 2>/dev/null || echo "Sem logs — nada rodando? (make up)"

# ---------------------------------------------------------------------------
# Minha solução — agent/ (Parte 1) e evaluation/ (Parte 2)
#
# Venv próprio em .venv (raiz), separado do venv da API em api/.venv: as duas partes
# têm dependências diferentes, e o material da Tractian não deve carregar as minhas.
# ---------------------------------------------------------------------------
MY_VENV := $(ROOT)/.venv
MY_PY := $(shell test -f "$(MY_VENV)/Scripts/python.exe" && echo "$(MY_VENV)/Scripts/python.exe" || echo "$(MY_VENV)/bin/python")

my-setup: ## Cria .venv e instala agent/ + evaluation/ (+ extra do provedor de LLM)
	@command -v uv >/dev/null 2>&1 || { echo "Instale o uv: https://docs.astral.sh/uv/"; exit 1; }
	@cd $(ROOT) && uv venv --python $(PYTHON) .venv
	@cd $(ROOT) && VIRTUAL_ENV= uv pip install --python "$(MY_PY)" -e ./solution/agent -e ./solution/evaluation pytest
	@echo "✓ minha solução instalada em $(MY_VENV)"
	@echo "  falta escolher o provedor de LLM:  uv pip install --python \"$(MY_PY)\" -e \"./solution/agent[groq]\""

agent-list: ## Lista os casos de agent-input/cases.json
	@cd $(SOL)/agent && $(MY_PY) server.py --list

agent-run: ## Roda o agente num caso (ex.: make agent-run CASE=TKT-INV-04 SEED=complete)
	@if [ -z "$(CASE)" ]; then echo "Uso: make agent-run CASE=TKT-INV-04 [SEED=complete]"; exit 1; fi
	@cd $(SOL)/agent && $(MY_PY) -m app.runner --case $(CASE) $(if $(SEED),--seed $(SEED),)

eval: ## Avaliação completa, 3 camadas (ex.: make eval SEEDS=s1,s2,s3 FASE=pos-correcao)
	@cd $(SOL)/evaluation && RUN_PHASE=$(FASE) $(MY_PY) -m runner.cli --seeds $(if $(SEEDS),$(SEEDS),complete,s2,s3)

eval-politica: ## Bateria numa política de evidência, gravando a fase (POLITICA=conditional)
	@if [ -z "$(POLITICA)" ]; then echo "Uso: make eval-politica POLITICA=conditional [SEEDS=complete,s2,s3]"; exit 1; fi
	@echo "→ bateria com EVIDENCE_POLICY=$(POLITICA), gravada como fase '$(POLITICA)'"
	@cd $(SOL)/evaluation && EVIDENCE_POLICY=$(POLITICA) RUN_PHASE=$(POLITICA) \
		$(MY_PY) -m runner.cli --seeds $(if $(SEEDS),$(SEEDS),complete,s2,s3) --skip-judges

eval-fast: ## Avaliação sem os juízes LLM (camadas 1 e 3 apenas — não gasta LLM)
	@cd $(SOL)/evaluation && $(MY_PY) -m runner.cli --seeds $(if $(SEEDS),$(SEEDS),complete,s2,s3) --skip-judges

eval-report: ## Reavalia os traces já gravados, sem rodar o agente de novo
	@cd $(SOL)/evaluation && $(MY_PY) -m runner.cli --from-traces --skip-judges

holdout-audit: ## Auditoria mecânica do holdout contra a API real (ADR 0006)
	@cd $(SOL)/evaluation && $(MY_PY) -m runner.holdout

holdout: ## Avalia o agente no holdout (teste final — não usar durante o ajuste)
	@cd $(SOL)/evaluation && $(MY_PY) -m runner.cli --suite holdout --seeds $(if $(SEEDS),$(SEEDS),complete,s2,s3)

painel-dados: ## Regenera o bundle da bateria (fonte do agente.json da leitura por ativo)
	@$(MY_PY) $(SOL)/painel/build_bundle.py --verify

painel-completar: ## Reexecuta as combinações caso×seed que faltam numa fase (FASE=pos-correcao)
	@$(MY_PY) $(SOL)/painel/completar_fase.py --fase $(if $(FASE),$(FASE),pos-correcao)
	@$(MY_PY) $(SOL)/painel/recalcular_csv.py --fase $(if $(FASE),$(FASE),pos-correcao)
	@$(MY_PY) $(SOL)/painel/resumir_csv.py
	@$(MY_PY) $(SOL)/painel/build_bundle.py --verify

painel-julgar: ## Comitê de juízes, uma execução por vez (N=1, FASE=pos-correcao, MODELO=<id>)
	@$(MY_PY) $(SOL)/painel/julgar.py --limite $(if $(N),$(N),1) $(if $(MODELO),--modelo $(MODELO),) $(if $(FASE),--fase $(FASE),)
	@$(MY_PY) $(SOL)/painel/build_bundle.py

painel-modelos: ## Lista os modelos gratuitos do OpenRouter conhecidos pelo juiz
	@$(MY_PY) $(SOL)/painel/julgar.py --modelos

leitura-dados: experimentos ## Coleta os 3 seeds por ativo e cruza com a bateria (FASE=conditional troca a fase exibida)
	@echo "→ coletando os ativos nas 3 seeds (exige 'make up')"
	@$(MY_PY) $(SOL)/painel/coleta/coletar_ativos.py
	@FASE=$(FASE) FASE_ANTERIOR=$(FASE_ANTERIOR) $(MY_PY) $(SOL)/painel/coleta/montar_indice.py

experimentos: ## Monta dados/experimentos.json a partir dos traces (aba Experimentos da leitura)
	@$(MY_PY) $(SOL)/painel/coleta/montar_experimentos.py

exp07: ## Roda o EXP-07 — sensibilidade à evidência (12 execuções; CASOS="A D" roda só a metade)
	@RUN_PHASE=exp07 $(MY_PY) $(SOL)/painel/rodar_exp07.py --continuar $(if $(CASOS),--casos $(CASOS),)

leitura: leitura-dados ## Recoleta e sobe a página de leitura por ativo (:$(AGENT_PORT))
	@echo "   Leitura por ativo: http://localhost:$(AGENT_PORT)/leitura/"
	@echo "   (a consulta ao vivo exige o agente: use 'make consulta' e abra /leitura/)"
	@cd $(SOL)/painel && $(MY_PY) -m http.server $(AGENT_PORT)

consulta: ## Sobe a leitura por ativo COM consulta ao vivo — executa o agente (:$(AGENT_PORT))
	@echo "   Leitura por ativo + consulta: http://localhost:$(AGENT_PORT)/leitura/"
	@echo "   Exige a API industrial no ar (make up) e o extra: uv pip install --python \"$(MY_PY)\" -e \"./solution/agent[serve]\""
	@cd $(SOL)/agent && $(MY_PY) server.py --serve --port $(AGENT_PORT)

my-test: ## Roda os testes da minha solução (agente + avaliação)
	@cd $(SOL)/agent && $(MY_PY) -m pytest -q
	@cd $(SOL)/evaluation && $(MY_PY) -m pytest -q

# ---------------------------------------------------------------------------
# Dev
# ---------------------------------------------------------------------------
test: ## Roda os testes da API industrial
	@cd $(TRAC)/api && $(PY) -m pytest -q

clean-data: ## Apaga dados gerados (data/, agent-input/, eval/) — regenere com make data
	@rm -rf $(TRAC)/data $(TRAC)/agent-input $(TRAC)/eval
	@echo "✓ dados apagados (rode make data para regenerar)"

clean: stop clean-data ## Para tudo e apaga dados + venv
	@# Só pid/log: `solution/.run/` também guarda os traces e os CSVs das baterias, que
	@# custaram cota de LLM e não são regeneráveis por `make`.
	@rm -rf $(VENV)
	@rm -f $(PID_DIR)/*.pid $(PID_DIR)/*.log
	@echo "✓ limpo (traces e CSVs de .run preservados)"
