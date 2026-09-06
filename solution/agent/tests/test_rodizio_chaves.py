"""Testes do rodízio de chaves de API.

A cota da Groq no plano gratuito é por dia e por CONTA: 200k tokens no menor modelo, o
que cobre cerca de dez execuções da bateria. Uma bateria de 51 execuções para no meio e
o resto do dia é perdido. Com chaves de contas diferentes em `LLM_API_KEY2`/`3`, a
execução continua na conta seguinte.

O que estes testes travam: (a) que só cota DIÁRIA dispara a troca — limite por minuto
reabre sozinho e migrar por causa dele queimaria a cota da próxima conta à toa; (b) que
tools e saída estruturada sobrevivem à troca, senão o papel perderia a capacidade de
consultar a API no meio do atendimento.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.llm import _ChatComRodizio, _e_cota_diaria


def _settings(**over) -> Settings:
    base = dict(
        api_base_url="http://localhost:8000",
        llm_provider="groq",
        llm_model="modelo/geral",
        llm_api_key="k1",
        llm_temperature=0.0,
        agent_port=8001,
        request_timeout_s=30,
        max_supervisor_turns=12,
        max_worker_steps=6,
        models_by_role={},
    )
    base.update(over)
    return Settings(**base)


# -- detecção do tipo de cota ---------------------------------------------


@pytest.mark.parametrize(
    "mensagem",
    [
        "Error code: 429 ... rate limit ... on tokens per day (TPD): Limit 200000",
        "429 requests per day (RPD) reached",
        "RateLimitError: limit reached, TPD exceeded",
    ],
)
def test_cota_diaria_dispara_troca(mensagem):
    assert _e_cota_diaria(Exception(mensagem)) is True


@pytest.mark.parametrize(
    "mensagem",
    [
        # Por minuto: a janela reabre sozinha em segundos. Trocar de conta aqui gastaria
        # a cota diária da chave seguinte sem necessidade.
        "Error code: 429 ... on tokens per minute (TPM): Limit 8000",
        "429 requests per minute (RPM) reached",
        "500 Internal Server Error",
        "Connection timeout",
    ],
)
def test_outros_erros_nao_trocam_de_chave(mensagem):
    assert _e_cota_diaria(Exception(mensagem)) is False


# -- chaves em Settings ----------------------------------------------------


def test_chaves_llm_ordena_principal_primeiro():
    s = _settings(llm_api_key="k1", llm_api_keys_extras=("k2", "k3"))
    assert s.chaves_llm == ("k1", "k2", "k3")


def test_chaves_llm_ignora_vazias():
    s = _settings(llm_api_key=None, llm_api_keys_extras=("k2",))
    assert s.chaves_llm == ("k2",)


# -- rodízio ---------------------------------------------------------------


class _Falso:
    """Cliente que estoura cota nas primeiras `falhas` chamadas."""

    def __init__(self, marca: str, falhas: int) -> None:
        self.marca = marca
        self.falhas = falhas
        self.ligadas: list[str] = []

    def invoke(self, *a, **k):
        if self.falhas > 0:
            self.falhas -= 1
            raise RuntimeError("429 ... on tokens per day (TPD): Limit 200000, Used 199999")
        return f"ok:{self.marca}"

    def bind_tools(self, tools, **k):
        self.ligadas.append("tools")
        return self


def _rodizio(monkeypatch, por_chave: dict[str, _Falso]) -> _ChatComRodizio:
    def fake_build(settings, *, api_key=None, **kw):
        return por_chave[api_key]

    monkeypatch.setattr("app.llm.build_llm", fake_build)
    return _ChatComRodizio(
        settings_=_settings(),
        modelo="m",
        extras={},
        chaves=tuple(por_chave),
    )


def test_troca_para_a_proxima_chave_quando_a_cota_acaba(monkeypatch):
    clientes = {"k1": _Falso("k1", falhas=1), "k2": _Falso("k2", falhas=0)}
    r = _rodizio(monkeypatch, clientes)
    assert r.invoke("oi") == "ok:k2"
    assert r.indice == 1


def test_percorre_todas_as_chaves_antes_de_desistir(monkeypatch):
    clientes = {
        "k1": _Falso("k1", falhas=1),
        "k2": _Falso("k2", falhas=1),
        "k3": _Falso("k3", falhas=0),
    }
    r = _rodizio(monkeypatch, clientes)
    assert r.invoke("oi") == "ok:k3"
    assert r.indice == 2


def test_esgotadas_todas_as_chaves_o_erro_sobe(monkeypatch):
    # Sem isto, a bateria registraria "concluída" uma execução que nunca rodou.
    clientes = {"k1": _Falso("k1", falhas=9), "k2": _Falso("k2", falhas=9)}
    r = _rodizio(monkeypatch, clientes)
    with pytest.raises(RuntimeError, match="TPD"):
        r.invoke("oi")


def test_erro_que_nao_e_cota_sobe_sem_gastar_chave(monkeypatch):
    class Quebrado:
        def invoke(self, *a, **k):
            raise ValueError("payload inválido")

    monkeypatch.setattr("app.llm.build_llm", lambda s, *, api_key=None, **kw: Quebrado())
    r = _ChatComRodizio(settings_=_settings(), modelo="m", extras={}, chaves=("k1", "k2"))
    with pytest.raises(ValueError):
        r.invoke("oi")
    assert r.indice == 0


def test_tools_sobrevivem_a_troca_de_chave(monkeypatch):
    clientes = {"k1": _Falso("k1", falhas=1), "k2": _Falso("k2", falhas=0)}
    r = _rodizio(monkeypatch, clientes).bind_tools(["get_asset"])
    assert r.invoke("oi") == "ok:k2"
    # A ligação foi reaplicada ao construir o cliente da chave nova — sem isso o papel
    # continuaria a execução sem tools, incapaz de consultar a API.
    assert "tools" in clientes["k2"].ligadas


def test_bind_tools_nao_muta_o_rodizio_original(monkeypatch):
    # `bind_tools` no LangChain devolve um objeto novo; o grafo conta com isso para
    # ligar conjuntos de tools diferentes ao mesmo modelo base.
    clientes = {"k1": _Falso("k1", falhas=0), "k2": _Falso("k2", falhas=0)}
    base = _rodizio(monkeypatch, clientes)
    com_tools = base.bind_tools(["get_asset"])
    assert com_tools is not base
    assert base.ligacoes_ == ()
    assert len(com_tools.ligacoes_) == 1
