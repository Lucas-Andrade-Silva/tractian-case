"""Configuração do agente, lida do ambiente (agent/.env).

O provedor de LLM é resolvido em `llm.py`; aqui só guardamos os valores brutos para
que nada mais no código precise ler `os.environ` diretamente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_DIR.parent

load_dotenv(AGENT_DIR / ".env")

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
    # Política de evidência do Investigador: `fixed` exige sempre as quatro consultas
    # básicas; `conditional` adapta ao tipo de pergunta do caso. É variável de
    # experimento — as duas são defensáveis, e qual rende melhor recall por token é
    # questão empírica, não de opinião.
    evidence_policy: str = "fixed"
    # Arquitetura do agente: `multi` (grafo de papéis, ADR 0001) ou `single` (agente
    # único com todas as tools). É a variável do EXP-05 — as duas rodam o mesmo material
    # e produzem o mesmo formato de trace, para que a comparação isole a arquitetura.
    architecture: str = "multi"

    def model_for(self, role: str) -> str:
        """Modelo do papel, caindo no modelo geral quando não há um específico."""
        return self.models_by_role.get(role) or self.llm_model

    @property
    def cases_path(self) -> Path:
        """`agent-input/cases.json` — única entrada de casos que o agente pode ler."""
        return REPO_ROOT / "agent-input" / "cases.json"

    @property
    def traces_dir(self) -> Path:
        return REPO_ROOT / "evaluation" / "results" / "traces"


def load_settings() -> Settings:
    return Settings(
        api_base_url=os.getenv("TRACTIAN_API_BASE_URL", "http://localhost:8000").rstrip("/"),
        llm_provider=os.getenv("LLM_PROVIDER", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        llm_api_key=os.getenv("LLM_API_KEY") or None,
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
        evidence_policy=(os.getenv("EVIDENCE_POLICY") or "fixed").strip().lower(),
        architecture=(os.getenv("AGENT_ARCHITECTURE") or "multi").strip().lower(),
    )
