"""Contratos da aba Experimentos.

O risco aqui não é a página quebrar — é ela continuar abrindo e passar a mostrar número
errado. A aba afirma um veredito por experimento, e um veredito errado numa página que uma
banca vai ler é pior que uma página fora do ar.

O que estes testes travam:

1. Os números do EXP-07 na página batem com os traces em disco. Se alguém mexer nos
   critérios e o placar mudar sem que os traces mudem, isto falha.
2. Nenhum experimento é apresentado como derivado sem ter dado derivado junto.
3. Todo experimento aponta para um documento que existe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PAINEL = Path(__file__).resolve().parent.parent
SOLUTION = PAINEL.parent
sys.path.insert(0, str(PAINEL / "coleta"))


@pytest.fixture(scope="module")
def dados():
    caminho = PAINEL / "dados" / "experimentos.json"
    if not caminho.exists():
        pytest.skip("dados/experimentos.json não gerado (rode `make experimentos`)")
    return json.loads(caminho.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def exp07(dados):
    for e in dados["experimentos"]:
        if e["id"] == "EXP-07":
            return e
    pytest.fail("EXP-07 ausente do experimentos.json")


def test_todo_experimento_aponta_para_um_documento_existente(dados):
    docs = SOLUTION / "docs" / "experimentos"
    for e in dados["experimentos"]:
        assert (docs / e["arquivo"]).exists(), f"{e['id']}: documento {e['arquivo']} não existe"


def test_experimento_derivado_traz_o_dado_derivado(dados):
    """`fonte: derivado` promete ao leitor que o número veio de disco, não do texto."""
    for e in dados["experimentos"]:
        if e["fonte"] == "derivado":
            assert e.get("derivado"), f"{e['id']}: marcado como derivado e sem dado derivado"


def test_veredito_e_um_dos_valores_que_a_pagina_sabe_pintar(dados):
    # A página mapeia veredito → cor. Um valor fora desta lista cairia no fallback
    # cinza e apresentaria uma hipótese refutada como indefinida.
    for e in dados["experimentos"]:
        assert e["veredito"] in {"sustentada", "refutada", "parcial"}, e["id"]


def test_exp07_tem_os_quatro_casos_com_os_tres_bracos(exp07):
    d = exp07["derivado"]
    assert d["total"] == 4
    assert d["execucoes"] == 12
    for caso in d["casos"]:
        assert set(caso["bracos"]) == {"controle", "decisivo", "placebo"}, caso["caso"]


def test_exp07_o_placar_bate_com_os_traces_em_disco(exp07):
    """Recalcula do zero e compara. É o teste que impede a página de divergir do dado."""
    from montar_experimentos import exp07 as recalcula

    atual = recalcula()
    publicado = exp07["derivado"]
    assert (atual["n1"], atual["n2"], atual["placebo"]) == (
        publicado["n1"], publicado["n2"], publicado["placebo"]
    ), "experimentos.json está desatualizado — rode `make experimentos`"


def test_exp07_nenhum_placebo_mudou_a_conclusao(exp07):
    """O placebo é o controle do experimento. Se um deles passar a mudar a conclusão, a
    afirmação de sensibilidade à evidência deixa de se sustentar e a página não pode
    continuar dizendo 'sustentada' sem alguém olhar."""
    assert exp07["derivado"]["placebo"] == 0


def test_exp07_o_caso_que_falhou_continua_marcado_como_falha(exp07):
    """O caso C é o achado do experimento: o Decisor leu a evidência e não a usou como
    critério de desempate. Se ele passar a marcar ✔ sem uma nova coleta, algum critério
    foi afrouxado — e é exatamente o tipo de mudança que precisa doer."""
    c = next(x for x in exp07["derivado"]["casos"] if x["letra"] == "C")
    assert c["nivel1"] is True, "o Investigador leu; se isso mudou, o trace mudou"
    assert c["nivel2"] is False, "o Decisor não usou; um ✔ aqui exige nova coleta"


def test_exp04_conta_zero_consultas_de_api_pelo_decisor(dados):
    """A hipótese do EXP-04 é que o Decisor não toca a API. É medido, não declarado."""
    e = next(x for x in dados["experimentos"] if x["id"] == "EXP-04")
    assert e["derivado"]["consultas_api"] == 0
    assert e["derivado"]["chamadas_por_execucao"] == 1.0
