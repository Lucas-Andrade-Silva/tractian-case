"""Testes do registro de fase e política no próprio trace.

Antes deste campo, a fase de uma execução era inferida depois, juntando
`(case_id, seed, token_usage.total_tokens)` contra o CSV de resultados. A junção é
empírica: duas execuções do mesmo caso e seed que empatem em tokens ficam indistinguíveis,
e o `build_bundle` aborta. Gravar a fase na origem elimina a inferência — e estes testes
travam o caminho `RUN_PHASE` → `Settings` → `Trace`, que é o que torna comparável uma
bateria rodada com outra política de evidência.
"""
from __future__ import annotations

from app.config import load_settings
from app.trace import Trace


def _trace(**over) -> Trace:
    base = dict(
        case_id="case_x",
        ticket_id="TKT-X-01",
        seed="s2",
        user_id="usr_ana",
        asset_id="asset_M101",
        message="mensagem do cliente",
    )
    base.update(over)
    return Trace(**base)


def test_fase_e_politica_entram_no_dicionario_do_trace():
    d = _trace(fase="conditional", evidence_policy="conditional").to_dict()
    assert d["fase"] == "conditional"
    assert d["evidence_policy"] == "conditional"


def test_trace_sem_fase_grava_none_e_nao_omite_a_chave():
    # A chave precisa existir mesmo vazia: `build_bundle` decide o caminho de junção
    # por `trace.get("fase")`, e uma chave ausente e um valor None significam a mesma
    # coisa lá — mas só se a chave estiver sempre presente no formato gravado.
    d = _trace().to_dict()
    assert "fase" in d and d["fase"] is None
    assert "evidence_policy" in d and d["evidence_policy"] is None


def test_run_phase_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("RUN_PHASE", "conditional")
    monkeypatch.setenv("LLM_API_KEY", "k")
    assert load_settings().run_phase == "conditional"


def test_run_phase_ausente_ou_vazia_vira_none(monkeypatch):
    # String vazia no .env não pode virar a fase "" — ela desligaria a junção direta
    # sem cair no caminho antigo, e nenhuma execução casaria.
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("RUN_PHASE", raising=False)
    assert load_settings().run_phase is None
    monkeypatch.setenv("RUN_PHASE", "   ")
    assert load_settings().run_phase is None


def test_evidence_policy_default_e_fixed(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("EVIDENCE_POLICY", raising=False)
    assert load_settings().evidence_policy == "fixed"
