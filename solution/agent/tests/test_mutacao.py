"""Testes da mutação de evidência do EXP-07.

Cobrem o que o experimento não pode errar em silêncio: que o campo alvo de fato muda, que
o campo do placebo não toca em nada que o gabarito nomeia, que a mutação sobrevive ao cache
de consultas repetidas, e que uma execução sem bundle continua idêntica à de antes.

Nada aqui chama LLM nem a API real — a mutação é verificada contra respostas montadas à mão
e contra um transporte HTTP falso.
"""
from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.api_client import ApiClient
from app.mutacao import (
    BUNDLES,
    CASOS_EXP07,
    A_DECISIVO,
    A_PLACEBO,
    B_DECISIVO,
    C_DECISIVO,
    D_DECISIVO,
    hook_de,
)
from app.trace import Trace


# -- respostas de referência, com os valores reais de tractian/data/ -------------------
ESPECTRO_S420 = {
    "asset_id": "asset_S420",
    "collected_at": "2026-07-14T00:00:00+00:00",
    "peaks": [
        {"freq_hz": 200, "amplitude_mm_s": 1.6, "note": "1x"},
        {"freq_hz": 400, "amplitude_mm_s": 0.4, "note": "2x"},
        {"freq_hz": 300, "amplitude_mm_s": 0.7, "note": "subharmônico (looseness)"},
    ],
}

DQ_V301 = {
    "asset_id": "asset_V301",
    "completeness": 0.62,
    "snr_db": 8.4,
    "staleness_flag": True,
}

MODELO = {
    "id": "mdl_vib_v3",
    "version": "3.2.1",
    "coverage": [
        {"machine_type": "motor_dc", "supported": True, "can_learn_baseline": False,
         "note": "detecção apenas sintomática"},
        {"machine_type": "pump", "supported": True, "can_learn_baseline": True},
    ],
    "requirements": {"min_snr_db": 12.0, "min_completeness": 0.8},
}


def aplica(bundle, path: str, dados: Any) -> Any:
    return hook_de(bundle)("GET", path, dados)


# -- braço decisivo -------------------------------------------------------------------
def test_caso_a_sobe_o_pico_1x_e_derruba_o_subharmonico():
    d = aplica(A_DECISIVO, "/assets/asset_S420/spectrum", ESPECTRO_S420)
    picos = {p["note"]: p["amplitude_mm_s"] for p in d["peaks"]}
    assert picos["1x"] == 6.4
    assert picos["subharmônico (looseness)"] == 0.15
    # O 2x não é nomeado pelo gabarito deste caso e não pode ter se mexido.
    assert picos["2x"] == 0.4


def test_caso_a_move_o_baseline_junto_com_o_espectro():
    """O bundle é coerente: subir o 1x sem estabelecer o baseline deixaria o insight
    suspeito por outro motivo, e o agente mudaria de resposta pela incoerência."""
    d = aplica(A_DECISIVO, "/assets/asset_S420/baseline", {"state": "invalidated",
                                                           "invalidation_reason": "maintenance"})
    assert d["state"] == "established"
    assert d["invalidation_reason"] is None


def test_caso_b_cruza_o_limiar_declarado_pelo_modelo():
    d = aplica(B_DECISIVO, "/assets/asset_V301/data-quality", DQ_V301)
    assert d["snr_db"] == 16.5
    assert d["completeness"] == 0.94
    # A referência contra a qual o agente compara não pode mudar: se ela se mover junto,
    # o experimento deixa de medir a leitura do valor e passa a medir a do limiar.
    assert MODELO["requirements"]["min_snr_db"] == 12.0


def test_caso_c_inverte_qual_diagnostico_o_espectro_sustenta():
    espectro = {
        "peaks": [
            {"freq_hz": 4.0, "amplitude_mm_s": 1.3, "note": "2x"},
            {"freq_hz": 2.0, "amplitude_mm_s": 0.9, "note": "0.5x/subharmônico (looseness)"},
        ]
    }
    d = aplica(C_DECISIVO, "/assets/asset_M205/spectrum", espectro)
    picos = {p["note"]: p["amplitude_mm_s"] for p in d["peaks"]}
    assert picos["2x"] == 3.9
    assert picos["0.5x/subharmônico (looseness)"] == 0.10


def test_caso_d_liga_o_booleano_e_remove_a_nota():
    d = aplica(D_DECISIVO, "/models/mdl_vib_v3", MODELO)
    dc = next(c for c in d["coverage"] if c["machine_type"] == "motor_dc")
    assert dc["can_learn_baseline"] is True
    assert "note" not in dc
    # `supported` continua true: a pergunta do ticket ("atende?") tem a mesma resposta nos
    # dois braços, e o que muda é COMO atende.
    assert dc["supported"] is True
    # Cobertura de outro tipo de máquina não é alvo.
    assert next(c for c in d["coverage"] if c["machine_type"] == "pump")["can_learn_baseline"] is True


# -- braço placebo --------------------------------------------------------------------
def test_placebo_nao_toca_em_nenhum_campo_do_gabarito():
    d = aplica(A_PLACEBO, "/assets/asset_S420/spectrum", ESPECTRO_S420)
    assert d["collected_at"] == "2026-07-11T00:00:00+00:00"
    assert d["peaks"] == ESPECTRO_S420["peaks"]


@pytest.mark.parametrize("nome", [n for n in BUNDLES if BUNDLES[n].braco == "placebo"])
def test_todo_placebo_muda_exatamente_um_campo(nome):
    """Um placebo que mexesse em vários campos deixaria de ser comparável ao decisivo."""
    bundle = BUNDLES[nome]
    assert len(bundle.mutacoes) == 1


# -- integração com o ApiClient -------------------------------------------------------
def _client(trace: Trace, hook, resposta: dict[str, Any]) -> ApiClient:
    chamadas = {"n": 0}

    def transporte(request: httpx.Request) -> httpx.Response:
        chamadas["n"] += 1
        return httpx.Response(200, json={"mode": "complete", "notes": None, "data": resposta})

    client = ApiClient(
        base_url="http://api.local", user_id="usr_bruno", trace=trace, response_hook=hook
    )
    client._http = httpx.Client(
        base_url="http://api.local",
        transport=httpx.MockTransport(transporte),
        headers={"x-user-id": "usr_bruno"},
    )
    client._chamadas = chamadas
    return client


def test_mutacao_sobrevive_ao_cache_de_consulta_repetida():
    """O agente repete GETs. Se a mutação entrasse depois do cache, a segunda consulta
    devolveria o valor íntegro e a evidência ficaria incoerente na mesma execução."""
    trace = Trace(case_id="case_tkt_inv_06", ticket_id="TKT-INV-06", seed="seed-50",
                  user_id="usr_bruno", asset_id="asset_S420", message="x")
    with _client(trace, hook_de(A_DECISIVO), ESPECTRO_S420) as client:
        primeira = client.get("/assets/asset_S420/spectrum")
        segunda = client.get("/assets/asset_S420/spectrum")
        assert client._chamadas["n"] == 1, "a segunda consulta deve vir do cache"

    def pico_1x(r):
        return {p["note"]: p["amplitude_mm_s"] for p in r["data"]["peaks"]}["1x"]

    assert pico_1x(primeira) == 6.4
    assert pico_1x(segunda) == 6.4


def test_sem_bundle_a_resposta_chega_intacta():
    """Execução normal não pode mudar de comportamento por causa do hook."""
    trace = Trace(case_id="case_tkt_inv_06", ticket_id="TKT-INV-06", seed="seed-50",
                  user_id="usr_bruno", asset_id="asset_S420", message="x")
    with _client(trace, None, ESPECTRO_S420) as client:
        r = client.get("/assets/asset_S420/spectrum")
    assert r["data"] == ESPECTRO_S420
    assert trace.mutacao is None


def test_o_trace_registra_o_bundle_de_forma_serializavel():
    """Sem esta marca no trace, execução mutada e execução real ficam indistinguíveis."""
    trace = Trace(case_id="case_tkt_inv_06", ticket_id="TKT-INV-06", seed="seed-50",
                  user_id="usr_bruno", asset_id="asset_S420", message="x",
                  mutacao=A_DECISIVO.para_trace())
    serializado = json.loads(json.dumps(trace.to_dict(), ensure_ascii=False))
    assert serializado["mutacao"]["braco"] == "decisivo"
    assert serializado["mutacao"]["caso"] == "case_tkt_inv_06"
    assert len(serializado["mutacao"]["alvos"]) == 4


# -- coerência do desenho -------------------------------------------------------------
def test_cada_caso_tem_decisivo_e_placebo_do_mesmo_caso():
    for caso, decisivo, placebo in CASOS_EXP07:
        assert decisivo.caso == caso and placebo.caso == caso
        assert decisivo.braco == "decisivo" and placebo.braco == "placebo"


def test_placebo_nunca_mira_o_mesmo_campo_que_o_decisivo():
    """Um placebo que caísse sobre um alvo decisivo destruiria o controle do experimento."""
    for _, decisivo, placebo in CASOS_EXP07:
        alvos = {(m.path, m.descricao) for m in decisivo.mutacoes}
        for m in placebo.mutacoes:
            assert (m.path, m.descricao) not in alvos


def test_hook_ignora_acoes():
    """POST/PATCH têm efeito real na API; mutar a resposta deles falsearia o resultado de
    uma ação que de fato aconteceu."""
    assert hook_de(D_DECISIVO)("POST", "/models/mdl_vib_v3", MODELO) is MODELO
