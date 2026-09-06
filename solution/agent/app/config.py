"""Configuração do agente, lida do ambiente (.env na raiz do repositório).

O provedor de LLM é resolvido em `llm.py`; aqui só guardamos os valores brutos para
que nada mais no código precise ler `os.environ` diretamente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent.parent
# Duas raízes, deliberadamente separadas: `solution/` é o que eu construí e `tractian/` é o
# material do parceiro (`agent-input/`, `eval/`, `data/`). Uma constante só para as duas
# voltaria a confundir os donos assim que uma delas mudar de lugar.
SOLUTION_DIR = AGENT_DIR.parent
REPO_DIR = SOLUTION_DIR.parent
TRACTIAN_DIR = REPO_DIR / "tractian"

# O .env fica na raiz, e não em agent/: agente, painel e evaluation leem as mesmas
# chaves, e um arquivo por subprojeto significaria manter a mesma chave em três lugares.
load_dotenv(REPO_DIR / ".env")

# Papéis que podem ter modelo próprio, via MODEL_<PAPEL> no .env.
ROLES = ("supervisor", "investigador", "contextualizador", "decisor", "executor")


@dataclass(frozen=True)
class Settings:
    """Configuração efetiva de uma execução do agente."""

    api_base_url: str
    llm_provider: str
    llm_model: str
    llm_api_key: str | None
    llm_temperature: float
    agent_port: int
    request_timeout_s: float
    # Teto de turnos do Supervisor: política de parada, evita loop infinito de investigação.
    max_supervisor_turns: int
    # Teto de rodadas de tool-calling dentro de um mesmo papel worker.
    max_worker_steps: int
    # Modelo por papel. Papel ausente usa `llm_model`, para que uma configuração
    # single-model continue funcionando e sirva de baseline no experimento.
    models_by_role: dict[str, str] = field(default_factory=dict)
    # Teto de tokens de saída por papel. A Groq recusa a requisição pelo `max_tokens`
    # DECLARADO, antes de gerar: um papel sem teto herda o padrão do cliente e estoura o
    # limite por minuto do modelo (`qwen3.6-27b` permite 1.000 OTPM) mesmo quando a
    # resposta real caberia. Instrução de brevidade no prompt não resolve — ela governa o
    # que o modelo escreve, não o número que a requisição declara.
    max_tokens_by_role: dict[str, int] = field(default_factory=dict)
    # Esforço de raciocínio por papel (`REASONING_EFFORT_<PAPEL>`: none|low|medium|high).
    # Num papel com teto de saída baixo, o raciocínio compete com a resposta pelo MESMO
    # orçamento: o Investigador gastava os 950 tokens pensando e era cortado antes de
    # escrever o resumo. Como o teto não pode subir (o modelo tem 1.000 OTPM), a saída é
    # reduzir o raciocínio. Papel ausente mantém o padrão do modelo.
    reasoning_effort_by_role: dict[str, str] = field(default_factory=dict)
    # Política de evidência do Investigador: `fixed` exige sempre as quatro consultas
    # básicas; `conditional` adapta ao tipo de pergunta do caso. É variável de
    # experimento — as duas são defensáveis, e qual rende melhor recall por token é
    # questão empírica, não de opinião.
    evidence_policy: str = "fixed"
    # Rótulo da bateria corrente, gravado em cada trace. Sem ele, a fase precisa ser
    # inferida depois por junção com o CSV de resultados — que falha quando duas
    # execuções do mesmo caso e seed empatam em tokens.
    run_phase: str | None = None
    # Chaves adicionais do mesmo provedor (`LLM_API_KEY2`, `LLM_API_KEY3`, …). A cota da
    # Groq no plano gratuito é por dia e por CONTA: 200k tokens/dia no menor modelo, o
    # que dá ~10 execuções da bateria inteira. Com chaves de contas diferentes, esgotar
    # uma não interrompe a bateria — o cliente troca para a próxima e segue.
    llm_api_keys_extras: tuple[str, ...] = ()

    @property
    def chaves_llm(self) -> tuple[str, ...]:
        """Todas as chaves disponíveis, na ordem de uso. Vazia quando não há nenhuma."""
        return tuple(k for k in (self.llm_api_key, *self.llm_api_keys_extras) if k)
    def model_for(self, role: str) -> str:
        """Modelo do papel, caindo no modelo geral quando não há um específico."""
        return self.models_by_role.get(role) or self.llm_model

    def max_tokens_for(self, role: str) -> int | None:
        """Teto de saída do papel. `None` deixa o padrão do provedor valer."""
        return self.max_tokens_by_role.get(role)

    def reasoning_effort_for(self, role: str) -> str | None:
        """Esforço de raciocínio do papel. `None` deixa o padrão do modelo valer."""
        return self.reasoning_effort_by_role.get(role)

    @property
    def cases_path(self) -> Path:
        """`tractian/agent-input/cases.json` — única entrada de casos que o agente pode ler."""
        return TRACTIAN_DIR / "agent-input" / "cases.json"

    @property
    def traces_dir(self) -> Path:
        return SOLUTION_DIR / "evaluation" / "results" / "traces"


def load_settings() -> Settings:
    return Settings(
        api_base_url=os.getenv("TRACTIAN_API_BASE_URL", "http://localhost:8000").rstrip("/"),
        llm_provider=os.getenv("LLM_PROVIDER", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_key=os.getenv("LLM_API_KEY") or None,
        # `LLM_API_KEY2` … `LLM_API_KEY9`. Buracos na numeração são ignorados: definir
        # só a 2 e a 4 é uma escolha legítima de quem tem duas contas extras.
        llm_api_keys_extras=tuple(
            chave
            for n in range(2, 10)
            if (chave := (os.getenv(f"LLM_API_KEY{n}") or "").strip())
        ),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        agent_port=int(os.getenv("AGENT_PORT", "8001")),
        request_timeout_s=float(os.getenv("REQUEST_TIMEOUT_S", "30")),
        max_supervisor_turns=int(os.getenv("MAX_SUPERVISOR_TURNS", "12")),
        max_worker_steps=int(os.getenv("MAX_WORKER_STEPS", "6")),
        models_by_role={
            role: value
            for role in ROLES
            if (value := (os.getenv(f"MODEL_{role.upper()}") or "").strip())
        },
        max_tokens_by_role={
            role: int(value)
            for role in ROLES
            if (value := (os.getenv(f"MAX_TOKENS_{role.upper()}") or "").strip())
        },
        reasoning_effort_by_role={
            role: value.lower()
            for role in ROLES
            if (value := (os.getenv(f"REASONING_EFFORT_{role.upper()}") or "").strip())
        },
        evidence_policy=(os.getenv("EVIDENCE_POLICY") or "fixed").strip().lower(),
        run_phase=(os.getenv("RUN_PHASE") or "").strip() or None,
    )
