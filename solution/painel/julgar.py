"""Roda o comitê de juízes (camada 2) sobre execuções já gravadas, via OpenRouter.

A camada 2 nunca chegou a produzir nota: as tentativas anteriores morreram por cota, e
todo relatório em `evaluation/results/` tem `per_run_judges` vazio. Este script existe para
fechar essa lacuna sem depender de uma bateria inteira — julga **uma execução por vez**,
grava assim que o veredito chega, e nunca refaz o que já está salvo.

Julgar de a um importa com modelo gratuito: as cotas são baixas, e uma rodada que estoura
no meio sem gravar nada é o que produziu o estado atual. Aqui, o que foi julgado fica.

    python painel/julgar.py --listar                       # o que falta na fase padrão
    python painel/julgar.py --execucao case_tkt_inv_04__complete__pos-correcao
    python painel/julgar.py --limite 3                     # as 3 próximas da fase padrão
    python painel/julgar.py --fase baseline --limite 3     # a fase anterior, explicitamente
    python painel/julgar.py --fase todas                   # sem filtro de fase
    python painel/julgar.py --modelos                      # modelos gratuitos conhecidos

## Por que a fase padrão é `pos-correcao`

Sem filtro, a fila de pendentes mistura as fases e é servida na ordem do bundle — e como
`baseline` tem mais pendentes, a cota ia toda para a versão ANTERIOR do agente. Foi assim
que as 35 execuções já julgadas acabaram todas em `baseline` enquanto a fase que a página
exibe ficou sem nenhuma nota. O padrão agora é a fase de produção; julgar outra é escolha
explícita, não default.

As fases válidas são lidas do próprio bundle (`fases_de`), não de uma lista no código: uma
bateria nova (`RUN_PHASE=conditional make eval-politica`) passa a ser julgável sem editar
este arquivo. Antes, `--fase conditional` era recusado pelo argparse.

O modelo vem de `JUDGE_MODEL` no `agent/.env` e pode ser trocado com `--modelo`. A chave é
`JUDGE_API_KEY` (ou `LLM_API_KEY`) — nunca é escrita em arquivo do repositório nem chega ao
navegador: o painel lê o resultado já gravado.

As notas ficam em `painel/dados/juizes.json`, que o build incorpora ao bundle.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SOLUCAO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOLUCAO / "agent"))
sys.path.insert(0, str(SOLUCAO / "evaluation"))

NOTAS = Path(__file__).resolve().parent / "dados" / "juizes.json"
BUNDLE = Path(__file__).resolve().parent / "dados" / "bundle.json"

# A lista de modelos e a consulta ao vivo vivem em `runner/juiz_modelos.py`, que a aba
# Consulta do painel também usa. Duas listas divergiriam: um modelo sairia do plano
# gratuito e só um dos dois lugares saberia.
from runner.juiz_modelos import (  # noqa: E402 - depende do sys.path acima
    MODELOS_GRATUITOS,
    PADRAO,
    modelos_ao_vivo,
)

# A mesma função que o build usa para decidir quais fases existem. Importar em vez de
# repetir a lista é o que impede que uma bateria nova apareça no painel e continue
# invisível para o juiz.
from build_bundle import fases_de  # noqa: E402 - idem

# A fase de produção: a que a página de leitura exibe por padrão e sobre a qual as
# afirmações de resultado são feitas.
FASE_PADRAO = "pos-correcao"
# Valor especial de `--fase` que desliga o filtro. Não é nome de fase nenhuma.
TODAS = "todas"


def carrega_notas() -> dict:
    if NOTAS.exists():
        return json.loads(NOTAS.read_text(encoding="utf-8"))
    return {"modelo": None, "vereditos": {}}


def salva_notas(dados: dict) -> None:
    NOTAS.parent.mkdir(parents=True, exist_ok=True)
    NOTAS.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carrega_bundle() -> dict:
    if not BUNDLE.exists():
        raise SystemExit(
            "painel/dados/bundle.json não existe. Rode antes: python painel/build_bundle.py"
        )
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


def reconstroi_trace(execucao: dict) -> dict:
    """Devolve o trace no formato que `run_committee` espera.

    O bundle guarda a execução em duas seções (`operacao` e `avaliacao`) para manter o
    gabarito fora da aba de operação; o comitê precisa do formato original.
    """
    op = execucao["operacao"]
    passos = [
        {
            "step": evento["step"],
            "agent": evento["papel"],
            "mode": evento["mode"],
            "status_code": evento["status_code"],
        }
        for evento in op["timeline"]
        if evento["tipo"] == "chamada"
    ]
    return {
        "case_id": execucao["case_id"],
        "seed": execucao["seed"],
        "message": op["mensagem"],
        "decision": op["decisao"],
        "justification": op["justificativa"],
        "final_answer": op["resposta_final"],
        "error": op["erro"],
        "steps": passos,
        "findings": op["achados"],
    }


def pendentes(bundle: dict, notas: dict, fase: str | None) -> list[dict]:
    """Execuções que ainda não têm veredito. Execução quebrada não vai a julgamento:
    nota baixa ali seria lida como má decisão do agente, não como falha de execução."""
    julgadas = set(notas["vereditos"])
    return [
        execucao
        for execucao in bundle["execucoes"]
        if execucao["id"] not in julgadas
        and (fase is None or execucao["fase"] == fase)
        and not execucao["operacao"]["erro"]
        and execucao["operacao"]["resposta_final"]
    ]


def resolve_fase(bundle: dict, escolhida: str) -> str | None:
    """Traduz `--fase` no filtro de `pendentes`, validando contra o que existe.

    Devolve `None` para "sem filtro". A validação é contra `fases_de(execucoes)` e não
    contra uma tupla no código: fase é dado da bateria, não constante do programa, e
    uma lista fixa aqui já deixou `conditional` sem como ser julgada.
    """
    disponiveis = fases_de(bundle["execucoes"])
    if escolhida == TODAS:
        return None
    if escolhida not in disponiveis:
        raise SystemExit(
            f"Fase '{escolhida}' não existe no bundle.\n"
            f"Disponíveis: {', '.join(disponiveis)} (ou '{TODAS}' para não filtrar).\n"
            "Se a bateria é nova, rode antes: python painel/build_bundle.py --verify"
        )
    return escolhida


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Comitê de juízes via OpenRouter")
    parser.add_argument("--execucao", help="Id da execução (case__seed__fase)")
    parser.add_argument(
        "--fase",
        default=FASE_PADRAO,
        help=(
            f"Fase a julgar (padrão: {FASE_PADRAO}, a de produção). "
            f"'{TODAS}' desliga o filtro. Fases válidas: as presentes no bundle."
        ),
    )
    parser.add_argument("--limite", type=int, default=1, help="Quantas julgar (padrão 1)")
    parser.add_argument("--modelo", help=f"Modelo do juiz (padrão: JUDGE_MODEL ou {PADRAO})")
    parser.add_argument("--listar", action="store_true", help="Só lista o que falta julgar")
    parser.add_argument("--modelos", action="store_true", help="Lista modelos gratuitos conhecidos")
    args = parser.parse_args()

    if args.modelos:
        ao_vivo = modelos_ao_vivo()
        lista = ao_vivo or MODELOS_GRATUITOS
        origem = "consultados agora na API" if ao_vivo else "lista local (API indisponível)"
        print(f"Modelos gratuitos do OpenRouter com saída estruturada — {origem}:\n")
        for identificador, descricao in lista:
            marca = " (padrão)" if identificador == PADRAO else ""
            print(f"  {identificador}{marca}\n      {descricao}")
        print("\nQualquer outro id do OpenRouter também funciona: --modelo <id>")
        print("O comitê exige saída estruturada: modelos sem esse suporte falham ao julgar.")
        return 0

    bundle = carrega_bundle()
    notas = carrega_notas()
    fase = resolve_fase(bundle, args.fase)
    fila = pendentes(bundle, notas, fase)

    if args.execucao:
        alvo = next((e for e in bundle["execucoes"] if e["id"] == args.execucao), None)
        if alvo is None:
            raise SystemExit(f"Execução '{args.execucao}' não existe no bundle.")
        fila = [alvo]
    else:
        fila = fila[: max(1, args.limite)]

    if args.listar:
        todas = pendentes(bundle, notas, fase)
        escopo = f"fase {fase}" if fase else "todas as fases"
        print(f"{len(notas['vereditos'])} já julgadas no total.")
        print(f"{len(todas)} pendentes em {escopo}:")
        for execucao in todas[:30]:
            print(f"  {execucao['id']}")
        if len(todas) > 30:
            print(f"  ... e mais {len(todas) - 30}")
        return 0

    if not fila:
        escopo = f"da fase {fase}" if fase else "de todas as fases"
        print(f"Nada a julgar: as execuções elegíveis {escopo} já têm veredito.")
        if fase:
            print(f"Outra fase: --fase <nome>, ou --fase {TODAS} para não filtrar.")
        return 0

    # Carrega o agent/.env antes de ler as variáveis: é lá que a chave mora, e sem isto
    # só funcionaria com a chave exportada no ambiente.
    from app.config import AGENT_DIR  # noqa: PLC0415 - import tardio, como o resto

    from dotenv import load_dotenv

    load_dotenv(AGENT_DIR / ".env")

    modelo = args.modelo or os.getenv("JUDGE_MODEL") or PADRAO
    chave = os.getenv("JUDGE_API_KEY") or os.getenv("LLM_API_KEY")
    if not chave:
        raise SystemExit(
            "Sem chave: defina JUDGE_API_KEY (ou LLM_API_KEY) em agent/.env.\n"
            "Crie uma gratuita em https://openrouter.ai/keys"
        )

    # A chave precisa ser DO OPENROUTER, que é para onde este script sempre aponta. Cair na
    # LLM_API_KEY do agente (Groq, prefixo `gsk_`) manda uma credencial de um provedor para
    # o endereço de outro: o erro chega lá na frente como "modelo não produz saída
    # estruturada", que manda trocar de modelo quando o problema é a chave.
    if not chave.startswith("sk-or-"):
        raise SystemExit(
            "A chave configurada não é do OpenRouter (chaves de lá começam com `sk-or-`).\n"
            f"Encontrei uma que começa com `{chave[:4]}` — provavelmente a do agente.\n\n"
            "Defina JUDGE_API_KEY em agent/.env com uma chave do OpenRouter:\n"
            "  https://openrouter.ai/keys\n\n"
            "O juiz roda por OpenRouter de propósito: julgar a saída do agente com o mesmo\n"
            "provedor e família de modelo introduz viés de auto-preferência (ADR 0005)."
        )

    # Id de modelo da Groq (`qwen/qwen3.8-27b`) não existe no catálogo do OpenRouter, e o
    # 404 só apareceria depois de a sonda de saída estruturada já ter falhado por outro
    # motivo aparente.
    if modelo.startswith(("openai/gpt-oss", "qwen/qwen3.")) and ":free" not in modelo:
        print(
            f"  aviso: '{modelo}' parece um id da Groq, não do OpenRouter.\n"
            "         Veja os disponíveis com: python painel/julgar.py --modelos"
        )

    # O juiz roda por OpenRouter independentemente do provedor do agente — julgar a própria
    # saída com o mesmo modelo introduz viés de auto-preferência (ADR 0005).
    os.environ["JUDGE_PROVIDER"] = "openrouter"
    os.environ["JUDGE_MODEL"] = modelo
    os.environ["JUDGE_API_KEY"] = chave

    from app.llm import build_llm
    from runner.golden import load_golden
    from runner.judges import (
        COMMITTEE,
        CotaEsgotada,
        JudgeVerdict,
        SaidaEstruturadaIndisponivel,
        com_saida_estruturada,
        judge_settings,
        run_committee,
    )

    gabarito = load_golden()
    try:
        llm = com_saida_estruturada(build_llm(judge_settings()), JudgeVerdict, verboso=True)
    except (CotaEsgotada, SaidaEstruturadaIndisponivel) as erro:
        raise SystemExit(
            f"{erro}\nVeja alternativas com: python painel/julgar.py --modelos"
        ) from erro

    print(f"Juiz: {modelo}\n")
    julgadas = falhas = 0

    for indice, execucao in enumerate(fila, 1):
        print(f"  [{indice}/{len(fila)}] {execucao['id']} ...", end=" ", flush=True)
        golden = gabarito.get(execucao["case_id"])
        if golden is None:
            print("sem gabarito, pulada")
            continue
        try:
            veredito = run_committee(reconstroi_trace(execucao), golden, llm=llm)
        except Exception as erro:  # noqa: BLE001 - cota/rede não podem perder o já julgado
            print(f"ERRO: {type(erro).__name__}: {str(erro)[:90]}")
            falhas += 1
            continue

        notas["vereditos"][execucao["id"]] = {"modelo": modelo, "dimensoes": veredito}
        notas["modelo"] = modelo
        # Grava a cada execução: cota estourada no meio não pode perder o que já veio.
        salva_notas(notas)
        resumo = "  ".join(
            f"{j.key}={veredito.get(j.key, {}).get('score') or '—'}" for j in COMMITTEE
        )
        print(resumo)
        julgadas += 1

    print(f"\n{julgadas} julgadas, {falhas} falharam. Total acumulado: {len(notas['vereditos'])}.")
    print(f"Notas em {NOTAS.relative_to(SOLUCAO)} — rode build_bundle.py para o painel enxergar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
