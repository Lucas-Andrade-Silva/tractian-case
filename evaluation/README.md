# evaluation/ — minha implementação da Parte 2 (avaliação)

Código próprio que roda o agente contra os cenários e mede qualidade/confiabilidade — independente
do código do agente em `../agent/`.

## O que é meu

- `runner/` — executa cenários (lê `../agent-input/cases.json`, chama o agente, captura o trace).
- `results/` — traces e relatórios gerados pelas execuções (não versionar resultados grandes/sensíveis
  sem necessidade).

## O que consome, sem editar

- `../eval/expected-paths.json`, `../eval/test-scenarios.md` — gabarito. **Só o código desta pasta
  lê isso**, e só depois que o agente já produziu um trace — nunca antes ou durante a execução do
  agente.
- `../docs/test-scenarios.md` — mesma regra.

## Regra de ouro (a mesma do `../agent/README.md`, na direção oposta)

Este código roda **depois** do agente, sobre o trace já produzido. Ele pode ler o gabarito; o
agente, nunca. Se algum dia este código precisar *chamar* o agente diretamente (em vez de só ler um
trace salvo), cuidado para não vazar `../eval/` para dentro do processo do agente (ex.: variável de
ambiente, import compartilhado).
