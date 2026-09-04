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


def test_comite_de_juizes_e_lido_dos_campos_reais(bundle, js_fonte):
    """O comitê existe neste bundle: 20 execuções julgadas em três dimensões.

    Um teste que apenas procura a palavra "calibra" no fonte passa mesmo quando o
    ramo que a exibe é inalcançável — foi exatamente o que aconteceu. Este amarra o
    nome do campo, que é onde o erro estava.
    """
    assert bundle["meta"]["juizes_disponiveis"] is True
    assert bundle["meta"]["juizes_resumo"], "o resumo do comitê sumiu do bundle"

    fonte = js_fonte("gaveta.js")
    assert "juizes_resumo" in fonte, "a gaveta não lê meta.juizes_resumo"
    assert "juizes_disponiveis" in fonte, "a gaveta não lê meta.juizes_disponiveis"
    assert "calibra" in fonte.lower(), "a ressalva de calibração sumiu"


def test_juizes_nao_aparecem_em_nenhuma_batida(js_fonte):
    """Nota de juiz não calibrado não sobe para o veredito.

    A separação é o que mantém a manchete defensável: 94,1% é medida contra gabarito
    humano; 3,65 de honestidade é um LLM opinando sobre outro. Misturar as duas
    produziria um número que não significa nada.
    """
    import pytest
    for batida in ("batida-veredito.js", "batida-chamado.js",
                   "batida-matriz.js", "batida-aovivo.js"):
        try:
            fonte = js_fonte(batida)
        except FileNotFoundError:
            continue  # a batida ainda não existe nesta altura do plano
        assert "juizes" not in fonte, f"{batida} exibe nota de juiz — não deve"


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


def test_quatro_batidas_na_ordem_da_narrativa(js_fonte):
    """A ordem é o roteiro da demo: veredito, um caso, a matriz, ao vivo."""
    fonte = js_fonte("batidas.js")
    for chave in ("veredito", "chamado", "matriz", "aovivo"):
        assert f'"{chave}"' in fonte, f"batida {chave} ausente"
    assert fonte.index('"veredito"') < fonte.index('"chamado"')
    assert fonte.index('"chamado"') < fonte.index('"matriz"')
    assert fonte.index('"matriz"') < fonte.index('"aovivo"')


def test_painel_nao_tem_mais_abas_antigas(js_fonte):
    """Operação/Avaliação/Consulta eram audiências, não uma narrativa."""
    fonte = js_fonte("painel.js")
    assert 'botaoAba' not in fonte, "painel.js ainda usa o sistema de abas antigo"


def test_setas_nao_sequestram_campos_de_texto(js_fonte):
    """As batidas ② e ④ têm campo de texto.

    Sem o guarda, apertar ← para corrigir um typo troca de batida e o `limpa(raiz)`
    descarta o que estava sendo digitado. Num projetor, no meio da demo, isso não
    tem recuperação — e nenhum teste de renderização existe aqui para pegar.
    """
    fonte = js_fonte("batidas.js")
    assert "INPUT" in fonte and "TEXTAREA" in fonte and "SELECT" in fonte, (
        "ligaTeclado não protege campos de texto das setas"
    )
    assert "isContentEditable" in fonte, "ligaTeclado ignora campos contentEditable"
