"""Testes da consulta livre e do gabarito sintético.

O que estes testes protegem não é o formato da saída — é o que torna a nota sintética
defensável. Se `assert_modelos_distintos` deixar passar um gerador igual ao juiz, ou se
uma consulta livre vazar para o diretório dos traces avaliados contra gabarito real, o
sistema continua rodando e produzindo números: só que números sem significado. Falha
silenciosa é exatamente o caso em que um teste paga o próprio custo.

Nenhum teste aqui chama LLM: o gerador é dublado.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "agent"))

from app.config import Settings  # noqa: E402

from runner.consulta import CONSULTAS_DIR, metricas_execucao, monta_caso  # noqa: E402
from runner.sintetico import (  # noqa: E402
    ExpectativaSintetica,
    ModelosIndistintos,
    _decisoes_validas,
    _modo_valido,
    assert_modelos_distintos,
    gera_gabarito,
)


def _settings(modelo: str, provedor: str = "groq") -> Settings:
    return Settings(
        api_base_url="http://localhost:8000",
        llm_provider=provedor,
        llm_model=modelo,
        llm_api_key=None,
        llm_temperature=0.0,
        agent_port=8001,
        request_timeout_s=30.0,
        max_supervisor_turns=12,
        max_worker_steps=6,
    )


class _LlmFalso:
    """Dublê do gerador: devolve a expectativa combinada, sem rede."""

    def __init__(self, resposta: ExpectativaSintetica) -> None:
        self._resposta = resposta

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _mensagens):
        return self._resposta


# -- a regra que sustenta a validade da nota --------------------------------
def test_gerador_igual_ao_juiz_e_recusado():
    """Mesmo modelo nos dois papéis mede auto-consistência, não acurácia."""
    with pytest.raises(ModelosIndistintos, match="mesmo modelo"):
        assert_modelos_distintos(_settings("modelo-x"), _settings("modelo-x"))


def test_gerador_igual_ao_juiz_ignora_caixa_e_espaco():
    """`Modelo-X ` e `modelo-x` são o mesmo modelo — comparar cru deixaria passar."""
    with pytest.raises(ModelosIndistintos):
        assert_modelos_distintos(_settings("  Modelo-X  "), _settings("modelo-x"))


def test_mesmo_modelo_em_provedores_diferentes_e_aceito():
    """Um modelo servido por dois provedores continua sendo dois pesos distintos na
    prática (quantização, versão, roteamento) — não é o caso que a regra veda."""
    assert_modelos_distintos(
        _settings("llama-3", provedor="groq"), _settings("llama-3", provedor="openrouter")
    )


def test_modelos_distintos_passa():
    assert_modelos_distintos(_settings("gerador-a"), _settings("juiz-b"))


@pytest.mark.parametrize("faltando", ["gerador", "juiz"])
def test_modelo_ausente_e_recusado(faltando):
    """Modelo vazio não pode ser tratado como 'diferente de tudo'."""
    gerador = _settings("" if faltando == "gerador" else "gerador-a")
    juiz = _settings("" if faltando == "juiz" else "juiz-b")
    with pytest.raises(ModelosIndistintos):
        assert_modelos_distintos(gerador, juiz)


# -- gabarito sintético -----------------------------------------------------
def test_gabarito_nasce_sem_trajetoria():
    """`expected_path` vazio é a marca de que a camada 1 não se aplica.

    Se algum dia este teste falhar porque alguém preencheu a trajetória, a camada 1
    passará a comparar contra uma sequência inventada por LLM — que é o erro que o
    módulo inteiro existe para evitar.
    """
    llm = _LlmFalso(
        ExpectativaSintetica(
            root_question="O sensor está offline desde quando?",
            mode="partial",
            accepted_decisions=["orientar", "escalar"],
            rationale="Depende de intervenção física.",
        )
    )
    caso = monta_caso(
        user_id="usr_pedro",
        company_id="comp_x",
        asset_id="asset_G501",
        mensagem="O sensor parou de mandar dado.",
    )

    gabarito = gera_gabarito(caso, settings=_settings("gerador-a"), llm=llm)

    assert gabarito.golden.expected_path == []
    assert gabarito.golden.required_actions == []
    assert gabarito.golden.accepted_decisions == frozenset({"orientar", "escalar"})
    assert gabarito.golden.is_ambiguous
    assert gabarito.to_dict()["origem"] == "sintetico"
    assert gabarito.modelo_gerador == "gerador-a"


def test_modo_invalido_cai_em_complete():
    assert _modo_valido("inventado") == "complete"
    assert _modo_valido("PARTIAL") == "partial"
    assert _modo_valido("") == "complete"


def test_decisao_invalida_nao_entra():
    assert _decisoes_validas(["agir", "explodir"]) == frozenset({"agir"})


def test_sem_decisao_valida_aceita_todas():
    """Sem informação, a avaliação não pode punir nenhum desfecho."""
    assert _decisoes_validas(["explodir"]) == frozenset({"orientar", "agir", "escalar"})
    assert _decisoes_validas([]) == frozenset({"orientar", "agir", "escalar"})


# -- montagem do caso -------------------------------------------------------
def test_caso_montado_tem_o_schema_do_agente():
    """`run_case` acessa `id`, `user_id` e `message` direto — faltar qualquer um quebra."""
    caso = monta_caso(
        user_id="usr_ana",
        company_id="comp_y",
        asset_id="asset_B100",
        mensagem="Vibração alta na bomba.",
    )
    assert set(caso) == {"id", "ticket_id", "company_id", "user_id", "asset_id", "message"}
    assert caso["ticket_id"].startswith("CONS-")
    assert caso["message"] == "Vibração alta na bomba."


def test_consultas_ficam_fora_dos_traces_avaliados():
    """Isolamento das métricas: `cli.py` lê `results/traces/<suite>/`, e nada mais.

    Se este caminho passar a cair dentro de `traces/`, uma consulta livre entraria nos
    relatórios dos 17 cenários com gabarito real — misturando métrica sintética com
    métrica de referência, que é justamente o que não pode acontecer.
    """
    assert CONSULTAS_DIR.name == "consultas"
    assert CONSULTAS_DIR.parent.name == "results"
    assert "traces" not in CONSULTAS_DIR.parts


# -- métricas sem gabarito --------------------------------------------------
def test_repeticao_e_insistencia_sao_medidas_sem_gabarito():
    trace = {
        "final_answer": "resposta",
        "stop_reason": "concluido",
        "steps": [
            {"step": "GET /assets/a", "status_code": 200},
            {"step": "GET /assets/a", "status_code": 200},
            {"step": "POST /cases/c/escalate", "status_code": 403},
            {"step": "POST /cases/c/escalate", "status_code": 403},
        ],
        "token_usage": {"total_tokens": 1234},
    }
    metricas = metricas_execucao(trace)

    assert metricas["executou_sem_erro"] is True
    assert metricas["chamadas_repetidas"] == 2
    assert metricas["taxa_repeticao"] == 0.5
    assert metricas["insistiu_apos_negativa"] is True
    assert metricas["acoes_de_impacto"] == [
        "POST /cases/c/escalate",
        "POST /cases/c/escalate",
    ]
    assert metricas["tokens"] == 1234


def test_negativa_unica_nao_conta_como_insistencia():
    """Levar um 403 uma vez é ler a permissão; repetir é que é falha."""
    trace = {
        "final_answer": "resposta",
        "steps": [{"step": "POST /cases/c/escalate", "status_code": 403}],
    }
    assert metricas_execucao(trace)["insistiu_apos_negativa"] is False


def test_execucao_quebrada_nao_conta_como_valida():
    trace = {"error": "Boom", "final_answer": None, "steps": []}
    metricas = metricas_execucao(trace)
    assert metricas["executou_sem_erro"] is False
    assert metricas["taxa_repeticao"] is None


def test_lista_ignora_o_trace_bruto_da_propria_consulta(tmp_path, monkeypatch):
    """Cada consulta deixa DOIS arquivos no diretório e só um é um registro.

    `run_case` grava o trace por conta própria como `<id>__seed-….json`, que casa com o
    mesmo glob. Sem filtrar por `origem`, a listagem devolveria o dobro de itens, metade
    deles vazios — e o histórico do painel mostraria linhas em branco.
    """
    import json as _json

    from runner import consulta as mod

    registro = {
        "id": "consulta_20260101T000000",
        "criado_em": "2026-01-01T00:00:00+00:00",
        "origem": "consulta_livre",
        "trace": {},
    }
    (tmp_path / "consulta_20260101T000000.json").write_text(
        _json.dumps(registro), encoding="utf-8"
    )
    # O trace bruto que run_case grava ao lado: mesmo prefixo, sem `origem`.
    (tmp_path / "consulta_20260101T000000__seed-complete__20260101T000001.json").write_text(
        _json.dumps({"case_id": "consulta_20260101T000000", "steps": []}), encoding="utf-8"
    )

    monkeypatch.setattr(mod, "CONSULTAS_DIR", tmp_path)
    listadas = mod.lista_consultas()

    assert len(listadas) == 1
    assert listadas[0]["id"] == "consulta_20260101T000000"
