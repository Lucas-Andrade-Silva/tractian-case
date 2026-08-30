# agent/ — meu código

Esta pasta é **minha implementação** do agente de suporte. Tudo que está aqui foi escrito por mim
para o desafio; nada aqui veio da TRACTIAN.

## O que NÃO é meu (não editar)

- `../api/`, `../data/`, `../docs/` — API industrial, dados sintéticos e documentação entregues
  prontos pela TRACTIAN.
- `../agent-input/` — o único material de entrada que meu agente pode ler (`cases.json` + contrato
  da API). Consumido, nunca modificado.
- `../eval/` — gabarito (`expected-paths.json`, `test-scenarios.md`). **Meu agente nunca importa ou
  lê nada desta pasta.** Só o código em `../evaluation/` (também meu, mas separado) tem permissão de
  ler `../eval/`, e só depois que o agente já rodou.

## O que é meu

- `app/` — código do agente (tools HTTP, grafo/loop, prompts, trace logger).
- `tests/` — testes do agente.
- `.env.example` → copiar para `.env` (API key, modelo, URL da API industrial). `.env` nunca é
  commitado.
- `pyproject.toml` — dependências próprias do agente (LLM/orquestração), independentes das
  dependências da API em `../api/pyproject.toml`.
- `server.py` — ponto de entrada, sobe em `:8001` (ver `../Makefile`, alvo `up-agent`).

## Regra de ouro

O agente fala com o mundo exterior **apenas por HTTP com a API industrial** (`http://localhost:8000`)
e por leitura de `../agent-input/`. Nunca por import direto de código da API (`../api/app/...`) nem
por leitura de `../eval/` ou `../docs/test-scenarios.md`. Isso preserva a validade da avaliação em
`../evaluation/`.
