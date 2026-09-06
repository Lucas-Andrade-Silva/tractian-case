"""Contratos do bundle que falham em silêncio se quebrarem.

O painel de quatro batidas foi aposentado (`_legado/painel/`), mas o pipeline que
gera `dados/bundle.json` continua vivo: é dele que `coleta/montar_indice.py` deriva
o `dados/agente.json` consumido pela página de leitura. O que estes testes protegem
são os campos desse bundle — o sintoma de uma quebra aqui não é um erro, é uma
leitura por ativo que continua abrindo e passa a mostrar número errado.

Os contratos da UI antiga (imports entre batidas, tokens de CSS, RN-01 na tela de
operação) foram para `_legado/painel/tests/test_contrato_ui.py`.
"""
from __future__ import annotations

import re


def test_bundle_tem_as_fases_da_comparacao_principal(bundle):
    """As duas fases da comparação existem e vêm primeiro.

    Baterias de experimento (uma política de evidência diferente, por exemplo) entram
    como fases adicionais — por isso a asserção é de contenção, não de igualdade. A
    ORDEM é que precisa ser travada: o painel lê "antes → depois", e ordenação
    alfabética colocaria `conditional` na frente de `baseline`.
    """
    fases = bundle["meta"]["fases"]
    assert fases[:2] == ["baseline", "pos-correcao"]
    assert bundle["agregados"]["pos-correcao"]["execucoes"] == 51
    assert bundle["agregados"]["baseline"]["execucoes"] == 51


def test_toda_fase_declara_a_politica_de_evidencia_que_rodou(bundle):
    """Comparar fases exige saber o que variou entre elas.

    Uma fase cujos traces divergem na política internamente mediu duas coisas ao mesmo
    tempo — foi o que aconteceu quando `completar_fase.py` repôs execuções sem herdar
    `EVIDENCE_POLICY` da fase, e é o que este teste impede de voltar em silêncio.
    """
    for fase, config in (bundle["meta"].get("modelos_por_fase") or {}).items():
        assert config, f"fase '{fase}' sem configuração registrada"
        assert "_divergente" not in config, (
            f"fase '{fase}' tem execuções com configurações diferentes: "
            "ela não mede uma coisa só."
        )
        assert config.get("_evidence_policy"), (
            f"fase '{fase}' não declara a política de evidência que rodou"
        )


def test_achados_do_bundle_sao_parseaveis(bundle):
    """As tags de fato da batida ② vêm de achados[].summary.

    O formato é `chave=valor (origem)` por linha. Se o formato mudar no
    build_bundle e ninguém notar, a batida ② fica sem tags e volta a ser uma
    lista de endpoints — exatamente o que o redesenho removeu.
    """
    execucao = next(
        e for e in bundle["execucoes"]
        if e["ticket_id"] == "TKT-INV-09"
        and e["fase"] == "pos-correcao"
        and e["seed"] == "complete"
    )
    achados = execucao["operacao"]["achados"]
    assert achados, "TKT-INV-09 perdeu os achados"

    linhas = [l for l in achados[0]["summary"].splitlines() if l.strip()]
    assert len(linhas) >= 5, "esperado ao menos 5 fatos apurados"
    assert any("baseline.state=invalidated" in l for l in linhas)
    assert any("status=stale" in l for l in linhas)
    assert all("=" in l for l in linhas), "toda linha de achado tem chave=valor"


def test_achados_empacotados_por_virgula(bundle):
    """Uma linha de achado pode carregar vários fatos separados por vírgula.

    `analysis.id=an_9906, status=stale, created_at=2026-07-09` é um caso real. Se o
    parser não separar, a tag vira uma frase longa e ilegível a quatro metros — que é
    exatamente o defeito que este redesenho existe para remover.
    """
    execucao = next(
        e for e in bundle["execucoes"]
        if e["ticket_id"] == "TKT-INV-09"
        and e["fase"] == "pos-correcao"
        and e["seed"] == "complete"
    )
    linhas = execucao["operacao"]["achados"][0]["summary"].splitlines()
    empacotadas = [l for l in linhas if l.count("=") > 1]
    assert empacotadas, "o caso exemplar perdeu as linhas com vários fatos"

    duplo = [l for l in linhas if l.rstrip().endswith(")") and l.count("(") > 1]
    assert duplo, "o caso exemplar perdeu a linha com dois parênteses finais"


def test_comite_de_juizes_esta_no_bundle(bundle):
    """O comitê existe neste bundle: execuções julgadas em três dimensões.

    A metade deste teste que checava a gaveta foi para `_legado/` junto com a UI
    antiga; o contrato do bundle continua valendo porque `build_bundle.py` continua
    gerando o `agente.json` que a página de leitura consome.
    """
    assert bundle["meta"]["juizes_disponiveis"] is True
    assert bundle["meta"]["juizes_resumo"], "o resumo do comitê sumiu do bundle"


def test_comparabilidade_entre_fases_e_declarada(bundle):
    """As duas fases só são comparáveis enquanto rodarem com a mesma configuração
    de modelo por papel. O flag precisa existir no bundle: um bundle futuro que
    troque um modelo sem dizer faria a leitura creditar o ganho ao lugar errado.
    """
    assert "config_diverge_entre_fases" in bundle["meta"]


def test_delta_entre_fases_vem_das_duas_fases(bundle):
    """A seta baseline → pós-correção substitui o dropdown de fase."""
    base = bundle["agregados"]["baseline"]["acuracia_decisao"]
    pos = bundle["agregados"]["pos-correcao"]["acuracia_decisao"]
    assert pos > base, "a narrativa da batida ① depende do ganho entre fases"


def test_estabilidade_virou_selo_e_nao_secao(bundle):
    """17/17 estáveis é um selo, não uma seção.

    Se algum dia deixar de ser 17/17, o selo passa a mentir e a batida ③ precisa
    de revisão — por isso o teste falha em vez de o painel exibir um número errado.
    """
    casos = [c for c in bundle["casos"] if c["por_fase"].get("pos-correcao")]
    mediveis = [c for c in casos if c["por_fase"]["pos-correcao"]["estabilidade"]["medivel"]]
    estaveis = [c for c in mediveis if c["por_fase"]["pos-correcao"]["estabilidade"]["estavel"]]
    assert len(estaveis) == len(mediveis), "a premissa do selo mudou — revisar a batida ③"


def test_campos_do_diff_existem_no_bundle(bundle):
    """A gaveta lateral da batida ③ lê estes campos; nomes inventados renderizam vazio."""
    av = bundle["execucoes"][0]["avaliacao"]
    for campo in ("decisoes_aceitas", "queries_faltantes", "queries_extras",
                  "acoes_faltantes", "diff_trajetoria"):
        assert campo in av, f"campo {campo} ausente — a batida ③ contava com ele"


