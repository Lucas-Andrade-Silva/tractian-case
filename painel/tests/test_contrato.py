"""Contratos do painel que falham em silêncio se quebrarem.

RN-01 é o mais importante: se a tela de operação passar a ler o gabarito, ela
deixa de ser a visão de quem atende e a Parte 2 do projeto perde o sentido. O
sintoma não é um erro — é uma tela que continua funcionando e passa a mentir.
"""
from __future__ import annotations

import re

from .conftest import imports_de


def test_bundle_tem_as_fases_esperadas(bundle):
    assert set(bundle["meta"]["fases"]) == {"baseline", "pos-correcao"}
    assert bundle["agregados"]["pos-correcao"]["execucoes"] == 51


def test_operacao_nao_importa_avaliacao(js_fonte):
    """RN-01 estrutural: a visão de quem atende não pode ler o gabarito."""
    for modulo in ("operacao.js",):
        assert "avaliacao.js" not in imports_de(js_fonte(modulo)), (
            f"{modulo} importou avaliacao.js — RN-01 quebrado"
        )


def _token(css: str, nome: str) -> float:
    """Valor de um custom property no bloco `:root` base.

    Ancorado no primeiro `:root` de propósito: um override por tema definido mais
    abaixo no arquivo não pode ser lido no lugar do valor base sem ninguém notar.
    """
    raiz = css.split(":root", 1)[1].split("}", 1)[0]
    achado = re.search(rf"{re.escape(nome)}:\s*([\d.]+)px", raiz)
    assert achado, f"token {nome} não encontrado no bloco :root do CSS"
    return float(achado.group(1))


def test_corpo_legivel_em_projetor(css_fonte):
    """A banca lê a 4 m: corpo de 13,5px morre no projetor."""
    assert _token(css_fonte, "--t-corpo") >= 16


def test_metrica_de_veredito_e_grande(css_fonte):
    """O 94,1% da batida ① é o objeto mais importante do painel."""
    assert _token(css_fonte, "--t-metrica") >= 58


def test_titulos_se_destacam_do_corpo(css_fonte):
    """Hierarquia de título é o que a batida ① e a ③ usam para dizer onde olhar.

    O painel antigo tinha h1 a 15px contra corpo de 14px. Um degrau de 1px não é
    hierarquia, e a 4 m de distância não é nada — por isso o passo mínimo aqui é
    testado em vez de combinado.
    """
    corpo = _token(css_fonte, "--t-corpo")
    assert _token(css_fonte, "--t-h2") >= corpo * 1.15, "h2 perto demais do corpo"
    assert _token(css_fonte, "--t-h1") >= _token(css_fonte, "--t-h2") * 1.2, "h1 perto demais do h2"
    assert _token(css_fonte, "--t-h3") >= corpo, "título de seção menor que o corpo lê como legenda"


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


def test_gaveta_cobre_as_quatro_abas(js_fonte):
    """A gaveta é o único destino da prosa: se uma aba sumir, a ressalva some junto."""
    fonte = js_fonte("gaveta.js")
    for aba in ("metodo", "ressalvas", "auditoria", "arquitetura"):
        assert f'"{aba}"' in fonte, f"gaveta.js não define a aba {aba}"


def test_ressalva_de_juiz_nao_calibrado_sobreviveu(js_fonte):
    """Nota de juiz não calibrado não é verdade — a ressalva não pode se perder no refactor."""
    fonte = js_fonte("gaveta.js")
    assert "calibra" in fonte.lower(), "a ressalva de calibração do juiz sumiu"


def test_comparabilidade_entre_fases_e_declarada(bundle, js_fonte):
    """A seta da batida ① credita todo o ganho às correções.

    Isso só é honesto enquanto as duas fases rodarem com a mesma configuração de
    modelo por papel. O flag existe no bundle e a gaveta precisa lê-lo: se um bundle
    futuro trocar um modelo e ninguém disser, o painel passa a dar crédito ao lugar
    errado sem nenhum sintoma visível.
    """
    assert "config_diverge_entre_fases" in bundle["meta"]
    assert "config_diverge_entre_fases" in js_fonte("gaveta.js"), (
        "a gaveta não lê o flag de comparabilidade — RN-26"
    )
