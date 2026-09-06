"""Testes da aba de holdout ao vivo.

O que precisa ser garantido por teste, e não por disciplina de quem edita:

1. **O gabarito não vaza antes da hora.** A lista de cenários alimenta a tela ANTES de o
   agente rodar. Se um dia alguém acrescentar `expected_path` ali "para facilitar", a aba
   inteira perde o sentido — quem assiste veria a resposta certa antes da pergunta. Este
   é o teste que mais importa neste arquivo.
2. **A ordem dos eventos.** A página desenha em cima do fluxo: `inicio` primeiro,
   `veredito` por último. Inverter isso quebraria a tela sem quebrar nada no Python.
"""
from __future__ import annotations

import pytest

from runner.holdout import load_holdout_cases
from runner.holdout_ao_vivo import cenarios_disponiveis

# Chaves de gabarito. Nenhuma pode aparecer no que a tela recebe antes da execução.
CHAVES_DE_GABARITO = (
    "expected_path",
    "expected_queries",
    "accepted_decisions",
    "decisoes_aceitas",
    "root_question",
    "pergunta_raiz",
    "facet",
    "faceta",
    "required_actions",
)


def test_lista_cobre_os_oito_cenarios():
    """A aba mostra o holdout inteiro — um cenário omitido seria invisível na tela."""
    assert len(cenarios_disponiveis()) == len(load_holdout_cases()) == 8


def test_a_lista_nunca_entrega_gabarito():
    """O que vai para a tela antes de rodar é só o que o agente também vê.

    Falhar aqui significa que a demonstração passou a mostrar a resposta certa antes de o
    agente escolher a dele — e não haveria como distinguir acerto de encenação.
    """
    for cenario in cenarios_disponiveis():
        vazadas = [chave for chave in CHAVES_DE_GABARITO if chave in cenario]
        assert not vazadas, f"{cenario['id']} expôs gabarito na listagem: {vazadas}"


def test_a_lista_traz_o_que_a_tela_precisa():
    """Sem mensagem e ativo não há o que desenhar antes da execução."""
    for cenario in cenarios_disponiveis():
        assert cenario["id"] and cenario["ticket_id"]
        assert cenario["message"].strip(), f"{cenario['id']} sem mensagem do cliente"


def test_cenario_inexistente_vira_evento_de_erro():
    """Id errado não pode subir exceção: a página só sabe ler eventos."""
    from runner.holdout_ao_vivo import executa_ao_vivo

    eventos = list(executa_ao_vivo("case_que_nao_existe"))

    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "erro"
    assert "não existe" in eventos[0]["mensagem"]


def test_run_case_avisa_quem_observa_antes_de_comecar():
    """`trace_hook` recebe o trace ANTES do grafo — é o que permite acompanhar ao vivo.

    Chamado depois, o observador só veria a execução terminada, e a aba viraria o que ela
    existe para não ser: um resultado pronto exibido como se fosse ao vivo.
    """
    import app.runner as runner_mod

    recebidos: list[tuple[str, object]] = []
    caso = load_holdout_cases()[0]

    class GrafoQueFalha:
        """Interrompe logo no início: aqui só interessa QUANDO o hook foi chamado."""

        def invoke(self, *_a, **_k):
            raise RuntimeError("parada proposital")

    original = runner_mod.build_graph
    runner_mod.build_graph = lambda **_k: GrafoQueFalha()
    try:
        trace = runner_mod.run_case(
            caso,
            seed="complete",
            save_to=None,
            trace_hook=lambda nome, tr: recebidos.append((nome, tr)),
        )
    finally:
        runner_mod.build_graph = original

    assert recebidos, "o hook não foi chamado"
    nome, observado = recebidos[0]
    assert nome == "trace"
    # Mesmo objeto: é lendo ESTE trace que o streaming acompanha a execução.
    assert observado is trace


@pytest.mark.parametrize("case_id", [c["id"] for c in load_holdout_cases()])
def test_todo_cenario_tem_gabarito_para_comparar(case_id: str):
    """Sem gabarito, o evento final não teria com o que comparar a decisão."""
    from runner.holdout import load_holdout

    assert case_id in load_holdout()


def test_o_comite_fica_desligado_por_padrao():
    """`julgar` precisa ser pedido: três chamadas a um provedor externo não são grátis.

    Quem só quer ver o agente trabalhar não deveria pagar pela camada 2 sem escolher.
    """
    import inspect

    from runner.holdout_ao_vivo import executa_ao_vivo

    assert inspect.signature(executa_ao_vivo).parameters["julgar"].default is False


def test_falha_do_comite_nao_apaga_o_veredito(monkeypatch):
    """Se o comitê cair, a camada 1 continua valendo — ela não depende de LLM.

    O contrário seria perder a medição determinística por causa de um provedor externo
    fora do ar, que é justamente o risco de acoplar as duas camadas.
    """
    from runner import holdout_ao_vivo as mod

    monkeypatch.setattr(
        mod, "constroi_juizes", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("sem cota"))
    )

    caso = load_holdout_cases()[0]

    class TraceFalso:
        error = None
        stop_reason = "concluido"
        decision = "orientar"
        justification = "justificativa suficientemente longa para o teste"
        final_answer = "resposta"
        token_usage = {"total_tokens": 1}
        path_taken: list[str] = []

        def to_dict(self):
            return {
                "case_id": caso["id"],
                "path_taken": [],
                "steps": [],
                "decision": "orientar",
                "justification": self.justification,
                "final_answer": self.final_answer,
                "error": None,
            }

    monkeypatch.setattr(mod, "run_case", lambda *_a, **_k: TraceFalso())

    tipos = [ev["tipo"] for ev in mod.executa_ao_vivo(caso["id"], julgar=True)]

    assert "veredito" in tipos, "a camada 1 sumiu quando o comitê falhou"
    assert "juizes_erro" in tipos
    assert tipos[-1] == "juizes_erro"
