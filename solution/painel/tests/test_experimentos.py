"""Contratos da aba Experimentos.

O risco aqui não é a página quebrar — é ela continuar abrindo e passar a mostrar número
errado. A aba afirma um veredito por experimento, e um veredito errado numa página que uma
banca vai ler é pior que uma página fora do ar.

O que estes testes travam:

1. Os números do EXP-06 na página batem com os traces em disco. Se alguém mexer nos
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
        if e["id"] == "EXP-06":
            return e
    pytest.fail("EXP-06 ausente do experimentos.json")


def test_todo_experimento_aponta_para_uma_secao_existente(dados):
    """Os seis experimentos moram num documento só, cada um sob um cabeçalho `# EXP-NN`.

    O `arquivo` de cada entrada é `EXPERIMENTOS.md#ancora`, e checar só o arquivo deixaria
    passar uma âncora quebrada — que é o modo de falha real depois da consolidação: o
    documento existe, o link leva ao topo e o leitor não encontra a seção.
    """
    import re

    doc = SOLUTION / "docs" / "EXPERIMENTOS.md"
    assert doc.exists(), "docs/EXPERIMENTOS.md não existe"

    ancoras = set()
    for linha in doc.read_text(encoding="utf-8").splitlines():
        if m := re.match(r"^#{1,6}\s+(.*)", linha):
            t = re.sub(r"[`*_\[\]()]", "", m.group(1).strip().lower())
            t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
            ancoras.add(re.sub(r"\s+", "-", t.strip()))

    for e in dados["experimentos"]:
        arquivo, _, frag = e["arquivo"].partition("#")
        assert arquivo == "EXPERIMENTOS.md", f"{e['id']}: aponta para {arquivo}"
        assert frag in ancoras, f"{e['id']}: âncora #{frag} não existe em EXPERIMENTOS.md"


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
    from montar_experimentos import exp07_sensibilidade as recalcula

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


# --------------------------------------------------------------------------------------
# Exploradores — a amostra que a aba deixa o leitor abrir
# --------------------------------------------------------------------------------------
# A aba deixou de afirmar o veredito em prosa e passou a mostrar as execuções que o
# produziram. Isso move o risco: agora o placar e a amostra podem discordar entre si, e a
# contradição fica visível numa página que uma banca vai ler. Os testes abaixo travam a
# coerência dos dois.


@pytest.fixture(scope="module")
def bundle():
    caminho = PAINEL / "dados" / "bundle.json"
    if not caminho.exists():
        pytest.skip("dados/bundle.json não gerado (rode `make painel-dados`)")
    return json.loads(caminho.read_text(encoding="utf-8"))


def test_exp07_prompt_o_placar_bate_com_o_bundle(dados):
    """Recalcula o pareado pos-correcao x fixed-atual e compara com o publicado.

    O EXP-07 é o único experimento cujo veredito é uma troca — custo por acurácia — então
    os dois lados têm de bater: se `regrediu` ou `delta_tokens` divergirem do bundle, a
    página conta uma história diferente do dado.
    """
    from montar_experimentos import BUNDLE, exp07 as recalcula

    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    atual = recalcula(bundle)
    pub = _exp(dados, "EXP-07")["derivado"]
    for chave in ("total", "corrigiu", "regrediu", "acertos_a", "acertos_b", "delta_tokens"):
        assert atual[chave] == pub[chave], (
            f"{chave} divergiu — rode `make experimentos`"
        )


def test_exp07_prompt_regrediu_e_nao_corrigiu(dados):
    """O achado do EXP-07: 3 regressões, 0 correções, e a economia de custo real.

    Trava a direção do resultado, não só a consistência. Se uma bateria futura corrigir
    alguma decisão, este teste falha e o documento precisa ser reescrito — que é
    exatamente o que deve acontecer.
    """
    d = _exp(dados, "EXP-07")["derivado"]
    assert d["corrigiu"] == 0, "houve correção: EXP-07 §7.4.2 precisa ser refeito"
    assert d["regrediu"] > 0, "não houve regressão: EXP-07 perdeu seu objeto"
    assert d["acertos_b"] < d["acertos_a"], "a acurácia não caiu — reveja o veredito"
    assert d["delta_tokens"] < 0, "a economia não aconteceu — reveja a hipótese"


def test_a_primeira_amostra_do_exp07_e_uma_regressao(dados):
    """No EXP-07 a regressão é o achado; abrir num par idêntico esconderia o resultado."""
    assert _exp(dados, "EXP-07")["explorador"]["linhas"][0]["efeito"] == "regrediu"


def _exp(dados, id_):
    return next(x for x in dados["experimentos"] if x["id"] == id_)


def test_todo_explorador_tem_amostra(dados):
    """Um explorador vazio deixaria o experimento sem nenhuma evidência na tela."""
    for e in dados["experimentos"]:
        x = e.get("explorador")
        if not x:
            continue
        assert x.get("linhas") or x.get("casos"), f"{e['id']}: explorador sem amostra"


def test_o_n_do_cabecalho_bate_com_o_placar(dados):
    """O cabeçalho diz `n = 19 pares` e o placar diz `19`. Os dois saem do mesmo número;
    este teste impede que voltem a ser digitados em lugares diferentes."""
    for id_, chave in [("EXP-01", "total"), ("EXP-02", "total"), ("EXP-03", "total")]:
        e = _exp(dados, id_)
        n = int(e["n"].split()[0])
        assert n == e["explorador"][chave], f"{id_}: cabeçalho {n} ≠ placar"


def test_exp01_o_placar_bate_com_as_linhas(dados):
    """O placar é recontado das próprias linhas que a página mostra. Se ele passar a ser
    escrito à mão, a soma das linhas deixa de fechar e isto falha."""
    d = _exp(dados, "EXP-01")["explorador"]
    assert d["corrigiu"] == sum(l["efeito"] == "corrigiu" for l in d["linhas"])
    assert d["regrediu"] == sum(l["efeito"] == "regrediu" for l in d["linhas"])
    assert d["total"] == len(d["linhas"])
    # O achado do experimento: corrigiu sem regredir. Uma regressão nova precisa de olhos.
    assert d["regrediu"] == 0, "apareceu regressão: o veredito do EXP-01 precisa ser revisto"
    assert d["corrigiu"] > 0


def test_exp02_nenhuma_decisao_divergiu_entre_as_politicas(dados):
    """É o achado mais estável dos EXP-02 e EXP-06: a política de evidência muda o custo,
    não o desfecho. Uma divergência derruba o 'refutada' que a página exibe."""
    d = _exp(dados, "EXP-02")["explorador"]
    assert d["divergiu"] == 0
    assert d["divergiu"] == sum(l["efeito"] == "divergiu" for l in d["linhas"])
    # E o custo continua subindo em `conditional`, que é o que sobrou do efeito.
    assert d["tokens_b"] > d["tokens_a"]


def test_exp03_toda_recusa_foi_403_e_ninguem_insistiu(dados):
    """As duas afirmações da aba são medidas, não transcritas — e ambas são 5/5."""
    d = _exp(dados, "EXP-03")["explorador"]
    assert d["sem_insistir"] == d["total"], "o agente repetiu uma rota recusada"
    assert d["explicaram"] == d["total"], "uma resposta não mencionou a recusa"
    for c in d["casos"]:
        assert c["tentou_de_novo"] == 0, c["caso"]
        assert c["exigida"], f"{c['caso']}: 403 sem a permissão exigida no corpo"


def test_exp04_nenhuma_execucao_foge_da_constante(dados):
    """A hipótese é uma constante, então basta um contraexemplo para derrubá-la. O
    explorador ordena pelo pior caso justamente para que ele não se esconda."""
    d = _exp(dados, "EXP-04")["explorador"]
    for l in d["linhas"]:
        assert l["decisor"] == 1, f"{l['caso']}/{l['seed']}: {l['decisor']} chamadas"
        assert l["api_decisor"] == 0, f"{l['caso']}/{l['seed']}: tocou a API"


def test_a_primeira_amostra_carrega_o_efeito_medido(dados):
    """A primeira amostra é a que decide se o leitor navega ou desiste. Nos pareados ela
    tem de ser um par com efeito, e no EXP-06 tem de ser o caso que falhou — enterrar a
    falha atrás de dois ✔ é o tipo de ordenação que embeleza resultado."""
    assert _exp(dados, "EXP-01")["explorador"]["linhas"][0]["efeito"] == "corrigiu"
    assert _exp(dados, "EXP-06")["derivado"]["casos"][0]["nivel2"] is False


def test_os_exploradores_sao_recontados_do_bundle(dados, bundle):
    """Recalcula do zero contra o bundle e compara com o publicado — o mesmo contrato que
    já vale para o EXP-06, agora para os quatro exploradores derivados do bundle."""
    from montar_experimentos import exp01, exp02, exp03

    for id_, fn, chaves in [
        ("EXP-01", exp01, ("total", "corrigiu", "regrediu")),
        ("EXP-02", exp02, ("total", "divergiu", "delta_tokens")),
        ("EXP-03", exp03, ("total", "sem_insistir", "explicaram")),
    ]:
        atual, publicado = fn(bundle), _exp(dados, id_)["explorador"]
        for k in chaves:
            assert atual[k] == publicado[k], (
                f"{id_}.{k}: experimentos.json desatualizado — rode `make experimentos`")
