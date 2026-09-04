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
    """Valor numérico de um custom property como `--t-corpo: 16px`."""
    achado = re.search(rf"{re.escape(nome)}:\s*([\d.]+)px", css)
    assert achado, f"token {nome} não encontrado no CSS"
    return float(achado.group(1))


def test_corpo_legivel_em_projetor(css_fonte):
    """A banca lê a 4 m: corpo de 13,5px morre no projetor."""
    assert _token(css_fonte, "--t-corpo") >= 16


def test_metrica_de_veredito_e_grande(css_fonte):
    """O 94,1% da batida ① é o objeto mais importante do painel."""
    assert _token(css_fonte, "--t-metrica") >= 58
