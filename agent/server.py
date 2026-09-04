"""Ponto de entrada do agente: CLI por padrão, servidor HTTP sob demanda.

Uso:
    python -m app.runner --case TKT-INV-04 --seed complete   # roda um caso do conjunto
    python server.py --list                                  # lista os casos disponíveis
    python server.py --serve                                 # sobe a API da aba Consulta

## Por que existe um modo servidor

O contexto de uso do agente continua sendo autônomo com escopo, acionado por caso — não
é um chatbot. O que o modo `--serve` acrescenta é a porta de entrada que faltava: alguém
de fora (um usuário da plataforma, pela aba Consulta do painel) descrevendo em texto
livre o que observou, em vez de um caso pré-escrito em `agent-input/cases.json`.

O agente por trás é exatamente o mesmo: `executa_consulta` monta o dict de caso no
schema de sempre e chama `run_case`. Nada no grafo, nas tools ou nos prompts muda em
função de a entrada ter vindo por HTTP — se mudasse, as medidas dos 17 cenários não
valeriam para o que a aba Consulta executa.

O servidor não cria usuários: `GET /catalogo` devolve os que já existem em
`data/users.parquet`, e é o `user_id` escolhido que determina as permissões efetivas na
API industrial, via header `x-user-id`. Escopo do projeto preservado.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from app.config import load_settings
from app.runner import get_case, load_cases, run_case

REPO_ROOT = Path(__file__).resolve().parent.parent


class ConsultaRequest(BaseModel):
    """Uma observação de usuário, em texto livre, sobre um ativo que ele escolheu.

    Definido no escopo do módulo, e não dentro de `build_app`, por causa do
    `from __future__ import annotations` no topo: com ele a anotação do handler vira a
    string "ConsultaRequest", que o FastAPI resolve contra o namespace do MÓDULO. Uma
    classe local não estaria lá, e o corpo seria interpretado como query param — a
    requisição falha com "Field required" mesmo estando correta.
    """

    user_id: str = Field(description="Usuário existente da plataforma.")
    company_id: str = Field(description="Empresa do usuário.")
    asset_id: str | None = Field(default=None, description="Ativo escolhido na interface.")
    mensagem: str = Field(
        min_length=10, description="O que o usuário observou, com as palavras dele."
    )
    seed: str | None = Field(
        default=None, description="Seed da API, para reproduzir a mesma consulta."
    )
    julgar: bool = Field(
        default=True, description="Gerar gabarito sintético e rodar o comitê de juízes."
    )
    contexto_ativo: dict | None = Field(
        default=None, description="O que a UI já sabe do ativo (nome, tipo, criticidade)."
    )


def build_app():
    """Monta a aplicação FastAPI da aba Consulta.

    Importado aqui dentro, e não no topo do módulo, para que o CLI continue funcionando
    sem o extra `serve` instalado — quem só roda casos não precisa de FastAPI.
    """
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:  # pragma: no cover - depende de instalação opcional
        raise SystemExit(
            "Modo servidor exige FastAPI. Rode:\n"
            '  uv pip install -e "agent[serve]"'
        ) from exc

    # `evaluation/` não é pacote instalado do agente; entra no path para o servidor
    # poder orquestrar gabarito sintético + juízes. O agente em si nunca importa daqui
    # (ver runner.py) — é o servidor, camada de fora, que junta as duas coisas.
    evaluation_dir = REPO_ROOT / "evaluation"
    if str(evaluation_dir) not in sys.path:
        sys.path.insert(0, str(evaluation_dir))

    from runner.consulta import (  # noqa: E402 - depende do sys.path acima
        catalogo_ativos,
        catalogo_usuarios,
        executa_consulta,
        lista_consultas,
    )
    from runner.sintetico import ModelosIndistintos, gerador_settings  # noqa: E402
    from runner.judges import judge_settings  # noqa: E402

    app = FastAPI(
        title="Agente de suporte industrial — consulta livre",
        description="Recebe a observação de um usuário e devolve decisão + avaliação.",
    )

    # O painel é servido pela mesma origem (montado abaixo), mas abrir o HTML direto do
    # disco durante o desenvolvimento é comum o bastante para liberar o CORS local.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/saude", tags=["Infra"])
    def saude():
        """Diz se o par gerador/juiz está configurado — antes de gastar uma execução."""
        gerador = gerador_settings()
        juiz = judge_settings()
        try:
            from runner.sintetico import assert_modelos_distintos

            assert_modelos_distintos(gerador, juiz)
            avaliacao_ok, motivo = True, None
        except ModelosIndistintos as exc:
            avaliacao_ok, motivo = False, str(exc)

        return {
            "ok": True,
            "modelo_gerador": gerador.llm_model,
            "modelo_juiz": juiz.llm_model,
            "avaliacao_disponivel": avaliacao_ok,
            "motivo": motivo,
        }

    @app.get("/catalogo", tags=["Consulta"])
    def catalogo():
        """Usuários existentes. A interface escolhe entre eles; não cria nenhum."""
        return {"usuarios": catalogo_usuarios()}

    @app.get("/catalogo/{company_id}/ativos", tags=["Consulta"])
    def ativos(company_id: str):
        """Ativos da empresa, para o seletor que resolve o `asset_id`."""
        return {"ativos": catalogo_ativos(company_id)}

    @app.post("/consulta", tags=["Consulta"])
    def consulta(pedido: ConsultaRequest):
        try:
            return executa_consulta(
                user_id=pedido.user_id,
                company_id=pedido.company_id,
                asset_id=pedido.asset_id,
                mensagem=pedido.mensagem,
                contexto_ativo=pedido.contexto_ativo,
                seed=pedido.seed,
                julgar=pedido.julgar,
            )
        except ModelosIndistintos as exc:
            # 409: a requisição está correta; a configuração do ambiente é que não
            # permite um julgamento válido. Dizer isso é melhor do que devolver nota.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/consultas", tags=["Consulta"])
    def consultas():
        """Histórico das consultas livres já executadas, da mais recente à mais antiga."""
        return {"consultas": lista_consultas()}

    painel_dir = REPO_ROOT / "painel"
    if painel_dir.exists():
        app.mount("/", StaticFiles(directory=painel_dir, html=True), name="painel")

    return app


def serve(host: str, port: int) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            'Modo servidor exige uvicorn. Rode: uv pip install -e "agent[serve]"'
        ) from exc
    uvicorn.run(build_app(), host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente de suporte industrial Tractian")
    parser.add_argument("--list", action="store_true", help="Lista os casos de agent-input/cases.json")
    parser.add_argument("--case", help="case_id ou ticket_id a executar")
    parser.add_argument("--seed", default=None, help="Seed da API (reprodutibilidade)")
    parser.add_argument("--serve", action="store_true", help="Sobe a API HTTP + painel")
    parser.add_argument("--host", default="127.0.0.1", help="Host do servidor")
    parser.add_argument("--port", type=int, default=None, help="Porta (padrão: AGENT_PORT)")
    args = parser.parse_args()

    settings = load_settings()

    if args.serve:
        serve(args.host, args.port or settings.agent_port)
        return

    if args.list or not args.case:
        print(f"\nCasos disponíveis ({settings.cases_path}):\n")
        for case in load_cases(settings):
            print(f"  {case['ticket_id']:<14} {case['id']:<20} {case.get('asset_id', '-'):<12} {case['message'][:60]}")
        print("\nRode um caso:  python -m app.runner --case TKT-INV-04 --seed complete")
        print("Suba o painel: python server.py --serve\n")
        return

    trace = run_case(get_case(args.case, settings), seed=args.seed, settings=settings)
    print(f"decisão={trace.decision}  chamadas={len(trace.steps)}  parada={trace.stop_reason}")
    if trace.error:
        print(f"erro: {trace.error}")


if __name__ == "__main__":
    main()
