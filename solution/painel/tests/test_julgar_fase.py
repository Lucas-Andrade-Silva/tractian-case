"""A fase que o comitê de juízes julga por padrão.

Isto existe por causa de um erro que já aconteceu e não deu erro nenhum: `--fase` era
opcional e sem filtro, a fila de pendentes misturava as fases na ordem do bundle. Como
`baseline` tinha mais pendentes, `make painel-julgar` drenou a cota inteira julgando a
versão ANTERIOR do agente — as 35 execuções com veredito são todas de lá, enquanto a
fase que a página exibe ficou sem nota nenhuma. O script rodou certo o tempo todo.

O segundo teste trava a outra metade: as fases válidas vêm de `fases_de`, não de uma
tupla no código. A lista fixa recusava `--fase conditional` e deixava a bateria do
EXP-06 sem como ser julgada, mesmo já aparecendo no painel.
"""
from __future__ import annotations

import pytest

import julgar


def _bundle(*fases: str) -> dict:
    return {"execucoes": [{"id": f"e__{f}", "fase": f} for f in fases]}


def test_fase_padrao_e_a_de_producao():
    assert julgar.FASE_PADRAO == "pos-correcao"

    bundle = _bundle("baseline", "pos-correcao", "conditional")
    assert julgar.resolve_fase(bundle, julgar.FASE_PADRAO) == "pos-correcao"


def test_bateria_nova_e_julgavel_sem_editar_o_script():
    """Qualquer fase presente no bundle serve; nenhuma lista no código a autoriza."""
    bundle = _bundle("baseline", "pos-correcao", "conditional", "politica-x")

    assert julgar.resolve_fase(bundle, "conditional") == "conditional"
    assert julgar.resolve_fase(bundle, "politica-x") == "politica-x"


def test_fase_inexistente_para_o_script_em_vez_de_julgar_tudo():
    """Errar o nome não pode virar "sem filtro": seria a cota indo para a fase errada,
    que é exatamente o modo de falha que este arquivo existe para impedir."""
    with pytest.raises(SystemExit) as erro:
        julgar.resolve_fase(_bundle("baseline", "pos-correcao"), "pos-corecao")

    assert "não existe" in str(erro.value)
    assert "baseline, pos-correcao" in str(erro.value)


def test_sem_filtro_continua_possivel_mas_explicito():
    assert julgar.resolve_fase(_bundle("baseline", "pos-correcao"), julgar.TODAS) is None


def test_pendentes_respeitam_a_fase_e_pulam_execucao_quebrada():
    """Execução com erro não vai a julgamento: nota baixa ali seria lida como má
    decisão do agente, não como falha de execução."""
    bundle = {
        "execucoes": [
            {
                "id": "boa__pos-correcao",
                "fase": "pos-correcao",
                "operacao": {"erro": None, "resposta_final": "texto"},
            },
            {
                "id": "quebrada__pos-correcao",
                "fase": "pos-correcao",
                "operacao": {"erro": "timeout", "resposta_final": None},
            },
            {
                "id": "outra-fase__baseline",
                "fase": "baseline",
                "operacao": {"erro": None, "resposta_final": "texto"},
            },
        ]
    }
    notas = {"vereditos": {}}

    ids = [e["id"] for e in julgar.pendentes(bundle, notas, "pos-correcao")]
    assert ids == ["boa__pos-correcao"]

    todas = [e["id"] for e in julgar.pendentes(bundle, notas, None)]
    assert todas == ["boa__pos-correcao", "outra-fase__baseline"]
