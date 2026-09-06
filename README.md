# Challenge TRACTIAN × Inteli

Agente de suporte industrial que investiga chamados sobre ativos monitorados, decide entre
**orientar**, **agir** ou **escalar**, e é avaliado contra um conjunto de cenários curados.

O repositório tem duas metades, e a separação é física:

| Pasta | De quem | Começe por |
| :--- | :--- | :--- |
| [`solution/`](./solution/) | **Minha solução** — agente, avaliação e painel | [`solution/SOLUTION.md`](./solution/SOLUTION.md) |
| [`tractian/`](./tractian/) | Material do parceiro — API, dados, gabarito, briefing | [`tractian/README.md`](./tractian/README.md) |

Nada em `tractian/` foi editado: a API é consumida só por HTTP, e o gabarito
(`tractian/eval/`) é lido depois da execução do agente, nunca durante. No código, a
fronteira aparece como constantes distintas (`SOLUTION_DIR` e `TRACTIAN_DIR`); no
`Makefile`, como `SOL` e `TRAC`.

## Rodar

Requisitos: Python ≥ 3.10 e [`uv`](https://docs.astral.sh/uv/).

```bash
make setup      # material do parceiro: venv da API + geração dos dados
make my-setup   # minha solução: .venv na raiz

cp .env.example .env   # preencher a chave de LLM

make up                                        # API industrial em :8000
make agent-run CASE=TKT-INV-04 SEED=complete   # um caso
make eval-fast                                 # avaliação sem os juízes LLM
make painel                                    # painel em :8001
```

`make help` lista todos os alvos.
