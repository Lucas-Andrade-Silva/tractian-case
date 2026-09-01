"""Testes da configuração de modelo por papel.

Papéis diferentes têm exigências diferentes: quem chama tools em série se beneficia de um
modelo que emita várias tool calls por resposta; quem produz a decisão final se beneficia
do modelo mais capaz. Estes testes travam a resolução papel→modelo e o fallback, que é o
que permite comparar uma configuração multi-modelo contra o baseline single-model.
"""
from __future__ import annotations

from app.config import ROLES, Settings


def _settings(**over) -> Settings:
    base = dict(
        api_base_url="http://localhost:8000",
        llm_provider="groq",
        llm_model="modelo/geral",
        llm_api_key="k",
        llm_temperature=0.0,
        agent_port=8001,
        request_timeout_s=30,
        max_supervisor_turns=12,
        max_worker_steps=6,
        models_by_role={},
    )
    base.update(over)
    return Settings(**base)


def test_role_without_specific_model_falls_back_to_general():
    """Configuração single-model continua funcionando — é o baseline do experimento."""
    s = _settings()

    for role in ROLES:
        assert s.model_for(role) == "modelo/geral"


def test_specific_role_model_wins_over_general():
    s = _settings(models_by_role={"investigador": "qwen/paralelo"})

    assert s.model_for("investigador") == "qwen/paralelo"
    assert s.model_for("decisor") == "modelo/geral"  # não configurado → fallback


def test_every_role_can_have_its_own_model():
    mapping = {role: f"modelo/{role}" for role in ROLES}
    s = _settings(models_by_role=mapping)

    assert {role: s.model_for(role) for role in ROLES} == mapping


def test_empty_role_value_is_ignored_by_loader(monkeypatch):
    """`MODEL_DECISOR=` vazio no .env não deve virar um modelo chamado string vazia."""
    import app.config as config

    for role in ROLES:
        monkeypatch.delenv(f"MODEL_{role.upper()}", raising=False)
    monkeypatch.setenv("MODEL_INVESTIGADOR", "qwen/paralelo")
    monkeypatch.setenv("MODEL_DECISOR", "   ")
    monkeypatch.setenv("LLM_MODEL", "modelo/geral")
    monkeypatch.setenv("LLM_PROVIDER", "groq")

    s = config.load_settings()

    assert s.models_by_role == {"investigador": "qwen/paralelo"}
    assert s.model_for("decisor") == "modelo/geral"


def test_role_models_reuses_client_per_model(monkeypatch):
    """Papéis que compartilham modelo compartilham o cliente, sem instanciar duas vezes."""
    from app import llm as llm_module

    criados: list[str] = []

    def fake_build(settings, **over):  # noqa: ARG001
        criados.append(over["model"])
        return object()

    monkeypatch.setattr(llm_module, "build_llm", fake_build)

    s = _settings(
        models_by_role={
            "supervisor": "qwen/barato",
            "contextualizador": "qwen/barato",  # mesmo modelo do supervisor
            "investigador": "qwen/paralelo",
        }
    )
    models = llm_module.RoleModels(s)

    models.for_role("supervisor")
    models.for_role("contextualizador")
    models.for_role("investigador")
    models.for_role("supervisor")  # já em cache

    assert criados == ["qwen/barato", "qwen/paralelo"]


def test_describe_reports_effective_mapping():
    """O mapa efetivo vai para o trace: sem isso o experimento não é reprodutível."""
    from app.llm import RoleModels

    s = _settings(models_by_role={"investigador": "qwen/paralelo"})
    described = RoleModels(s).describe()

    assert described["investigador"] == "qwen/paralelo"
    assert described["decisor"] == "modelo/geral"
    assert set(described) == set(ROLES)
