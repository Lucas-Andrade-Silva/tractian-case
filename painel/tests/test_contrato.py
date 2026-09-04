"""Contratos do painel que falham em silêncio se quebrarem.

RN-01 é o mais importante: se a tela de operação passar a ler o gabarito, ela
deixa de ser a visão de quem atende e a Parte 2 do projeto perde o sentido. O
sintoma não é um erro — é uma tela que continua funcionando e passa a mentir.
"""
from __future__ import annotations

from .conftest import imports_de


def test_bundle_tem_as_fases_esperadas(bundle):
    assert set(bundle["meta"]["fases"]) == {"baseline", "pos-correcao"}
    assert bundle["agregados"]["pos-correcao"]["execucoes"] == 51
