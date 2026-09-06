"""Fixtures para os testes de contrato do bundle.

O painel de quatro batidas foi aposentado (`_legado/painel/`); as fixtures de fonte
JS e CSS foram junto. O que sobrou é o bundle, que continua sendo gerado por
`build_bundle.py` e continua alimentando a página de leitura por ativo.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PAINEL = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def bundle() -> dict:
    return json.loads((PAINEL / "dados" / "bundle.json").read_text(encoding="utf-8"))
