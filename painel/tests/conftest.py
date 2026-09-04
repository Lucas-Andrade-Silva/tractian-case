"""Fixtures para os testes de contrato do painel.

O painel é JS sem toolchain: não há como executar os módulos aqui. O que estes
testes protegem é o contrato que a leitura humana costuma deixar passar —
separação de import entre operação e avaliação, e números de tela que não podem
ser inventados no renderizador.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PAINEL = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def bundle() -> dict:
    return json.loads((PAINEL / "dados" / "bundle.json").read_text(encoding="utf-8"))


@pytest.fixture
def js_fonte():
    def _ler(nome: str) -> str:
        return (PAINEL / "js" / nome).read_text(encoding="utf-8")

    return _ler


def imports_de(fonte: str) -> set[str]:
    """Módulos importados por um arquivo JS, como aparecem no `from "..."`."""
    return set(re.findall(r'from\s+"\./([\w.]+)"', fonte))
