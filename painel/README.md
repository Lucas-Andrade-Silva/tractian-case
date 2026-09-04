# painel/ — Parte 3: visualização

Duas abas **somente-leitura** sobre os traces e as métricas já gravados (Operação e
Avaliação) e uma terceira que executa o agente ao vivo (Consulta). As duas primeiras não
chamam a API industrial nem alteram arquivo de dado: leem o bundle gerado por
[`build_bundle.py`](build_bundle.py).

```bash
make painel            # regenera o bundle, verifica, e serve em :8001 (sem a aba Consulta)
make consulta          # painel + aba Consulta: sobe o agente como servidor (:8001)
make painel-completar  # reexecuta o que falta numa fase (FASE=pos-correcao)
make painel-julgar     # roda o comitê numa execução (N=1, MODELO=<id>)
make painel-modelos    # modelos gratuitos do OpenRouter
```

Precisa ser servido por HTTP — o navegador bloqueia `fetch` em `file://`. A aba Consulta
exige `make up` (API industrial) e o extra do servidor:
`uv pip install --python .venv/Scripts/python.exe -e "./agent[serve]"`.

## Três abas, três leitores

**Operação** é o atendimento como quem responde o chamado o veria: a mensagem íntegra do
cliente, quem pediu e o que essa pessoa podia fazer, a ficha do ativo, a timeline com cada
transição do Supervisor e as chamadas que ela provocou (expansíveis até o response cru), a
evidência que chegou ao Decisor, a resolução e o custo.

**Avaliação** é o desempenho como quem mede o agente o veria: placar, matriz cenários ×
seeds, diff entre trajetória esperada e percorrida, comparativo entre as fases,
estabilidade, comitê de juízes e auditoria de ações e desperdício.

**Consulta** é a porta de entrada que faltava: um usuário da plataforma escolhe quem ele é,
escolhe o ativo e descreve com as próprias palavras o que observou. O agente roda ao vivo —
o mesmo `run_case` dos 17 cenários, sem nada especial no grafo — e a resposta volta com uma
avaliação **sintética**, marcada como tal (ADR 0007).

A aba não cria usuários: lista os que já existem em `data/users.parquet`, porque é o
`user_id` que determina a permissão real na API. Se um operador pedir uma ação que não pode
executar, o 403 aparece na trajetória — é o enforcement funcionando (ADR 0003), não falha.

## Métrica sintética nunca se mistura com métrica de referência

As notas da aba Consulta e as notas dos 17 cenários **não são a mesma medida** e nunca são
agregadas juntas. Um cenário tem `root_question` e `expected_path` escritos por humano; uma
consulta livre tem uma questão de referência que um LLM escreveu a partir da mensagem.
Somar as duas produziria uma média que não significa nada.

O isolamento é por caminho, não por disciplina de uso:

| o quê | onde grava | quem lê |
|---|---|---|
| cenários com gabarito | `evaluation/results/traces/<suite>/` | `runner/cli.py` |
| bateria do painel | `.run/traces_*/` | `build_bundle.py` |
| consultas livres | `evaluation/results/consultas/` | só a aba Consulta |

Nenhum dos dois primeiros leitores alcança o terceiro diretório, e
`tests/test_consulta.py::test_consultas_ficam_fora_dos_traces_avaliados` falha se esse
caminho mudar.

Duas garantias adicionais, ambas em código:

- **gerador ≠ juiz.** O modelo que escreve o gabarito sintético (`GERADOR_MODEL`) não pode
  ser o que julga a resposta (`JUDGE_MODEL`). Igual, o juiz mediria a própria
  auto-consistência. `assert_modelos_distintos` recusa a consulta antes de gastar execução,
  e `GET /saude` diz de antemão se o par está válido.
- **camada 1 desligada.** Sem trajetória de referência ela calcularia `recall = 1.0` sobre
  conjunto vazio. Fica `null`, com o motivo no próprio JSON. O que não depende de gabarito
  — repetição de chamada, insistência após 403, execução concluída — continua medido.

## A regra que organiza o código

A aba Operação **nunca** exibe gabarito, decisão aceita ou status de aprovação. Não é
preferência de layout: a Parte 2 só faz sentido se a visão de operação não for construída
sobre o gabarito — senão o painel estaria mostrando um atendimento que já sabe a resposta.

A regra é estrutural, e por isso verificável:

- o bundle separa `operacao` de `avaliacao` em seções irmãs por execução, e `operacao` não
  contém nenhum campo de gabarito;
- [`js/operacao.js`](js/operacao.js) lê apenas `execucao.operacao` e não importa nada de
  `js/avaliacao.js`.

```bash
grep -n "avaliacao" painel/js/operacao.js        # só comentários
grep -nE "expected|passou|decision_match" painel/js/operacao.js
```

É a mesma estratégia de `evaluation/runner/golden.py`, que concentra num único módulo a
leitura de `eval/` para que um vazamento apareça como um import.

## Como a fase é recuperada

O trace **não grava em que fase foi executado**, e 33 pares `(case_id, seed)` têm mais de um
arquivo. O nome da pasta não resolve (são nomes de experimento) e o corte por horário erra
em 21 casos.

A junção que resolve é `(case_id, seed, token_usage.total_tokens)` contra
`resultados_avaliacao.csv`: o total de tokens funciona como assinatura da execução, e a
junção é 1:1. A garantia é empírica, não estrutural — duas execuções do mesmo caso e seed
poderiam empatar em tokens —, então o build **aborta** ao encontrar ambiguidade em vez de
escolher uma. A única exceção é entre execuções que quebraram: elas consomem 0 token e
ficam indistinguíveis pela assinatura, então aí vence o trace mais recente, porque as
tentativas posteriores existem para substituir as anteriores. A correção de fundo é gravar
`fase` no trace, em `agent/app/trace.py`.

Os dois diretórios de trace são obrigatórios: as 3 execuções de baseline de
`case_tkt_exe_16` só existem em `agent/.run/`.

## Comitê de juízes (camada 2) via OpenRouter

A camada 2 nunca tinha produzido nota: as tentativas anteriores morreram por cota. O
[`julgar.py`](julgar.py) fecha isso julgando **uma execução por vez**, gravando cada
veredito assim que chega e nunca refazendo o que já está salvo — julgar em lote com modelo
gratuito é o que produziu o estado anterior.

```bash
python painel/julgar.py --modelos            # consulta a API e lista os :free de agora
python painel/julgar.py --limite 1           # julga a próxima pendente
python painel/julgar.py --modelo z-ai/glm-5.2:free
python painel/julgar.py --execucao case_tkt_inv_04__complete__baseline
```

`--modelos` consulta o catálogo do OpenRouter ao vivo, e não uma lista fixa: modelos saem
do plano gratuito sem aviso (o DeepSeek V3.1 saiu durante este trabalho), e uma lista
embutida vira armadilha — a única pista seria um 404 no meio da rodada. Só entram os que
declaram saída estruturada, que o comitê exige.

O suporte a saída estruturada varia entre os modelos gratuitos: uns só respondem por
`function_calling`, outros por `json_schema`, e alguns anunciam suporte que devolve prosa.
O script sonda o modelo uma vez, fixa o método que funcionou e segue — sem que
`evaluation/runner/judges.py`, que é código avaliado da Parte 2, precise mudar. Um 429 na
sonda é reportado como cota, não como incompatibilidade: são diagnósticos diferentes.

O modelo sai de `JUDGE_MODEL` no `agent/.env` e pode ser trocado a cada chamada com
`--modelo`; qualquer id do OpenRouter serve, e os de sufixo `:free` não consomem crédito. A
chave é `JUDGE_API_KEY` (gratuita em https://openrouter.ai/keys) e fica só no `.env` — não
chega ao navegador, porque o painel lê a nota já gravada em `dados/juizes.json`.

O juiz roda sempre por OpenRouter, independentemente do provedor do agente: julgar a
própria saída com o mesmo modelo introduz viés de auto-preferência (ADR 0005). Execuções
que quebraram não vão a julgamento — nota baixa ali seria lida como má decisão do agente em
vez de falha de execução. E o aviso de "não calibrado" permanece mesmo com notas na tela:
média de juiz não validado contra um conjunto anotado por humano não é verdade.

## Completar uma fase

O trace não grava a fase, e a bateria de pós-correção tinha parado no meio por cota — o que
deixava a comparação entre fases apoiada em bases diferentes.

```bash
make painel-completar FASE=pos-correcao
```

Executa **só o que falta**, com pausa entre execuções e novas tentativas após 429. É
retomável: o que já foi gravado não se refaz. Uma execução que quebrou conta como pendente,
não como preenchida — uma fase "completa" só de falhas pareceria medida e seria pior que a
lacuna original.

A Groq no plano gratuito tem dois tetos, e eles pedem respostas diferentes: o **por minuto**
(8.000 tokens no menor modelo) se resolve com a pausa, e o **por dia** (200.000) não se
resolve com espera nenhuma — só renovando. A mensagem do 429 diz qual dos dois foi.

Estado atual: as duas fases estão completas, 51 execuções cada (17 cenários × 3 seeds), sem
falha de execução.

Depois de executar, o pipeline de dados precisa acompanhar:

```
completar_fase.py → recalcular_csv.py → resumir_csv.py → build_bundle.py --verify
```

O `painel-completar` já encadeia os quatro. O `recalcular_csv.py` aplica a camada 1 de
`evaluation/runner/deterministic.py` a cada trace em vez de reescrever as fórmulas — se a
definição de `passou` mudar lá, muda aqui junto.

## O que o painel declara em vez de esconder

Boa parte do trabalho aqui é não deixar um número parecer mais sólido do que é:

| Situação | Como aparece |
| :--- | :--- |
| Métrica sem base | `—`, nunca `0%` — ausência de medida não é zero |
| Campo ausente no trace | "não determinado" |
| Escalonamento | desfecho correto, em tom neutro — nunca vermelho |
| 403 | "recusado por permissão", nomeando quem teria autorização |
| Célula sem execução | "não executado", visualmente distinta de reprovação |
| Zero execução válida | "não-medível", nunca "estável" |
| Divergência dentro do conjunto aceito | "varia dentro do aceito", tom distinto de instabilidade real |
| Reprovado com a decisão certa | exibe a causa, e sinaliza quando é artefato do gabarito |
| Precisão de consultas | rotulada como derivada — não existe em `deterministic.py` |
| Chamada de cache | marcada, e ainda contada como repetição no desperdício |
| Comitê de juízes | notas quando existirem, com o raciocínio; aviso de "não calibrado" sempre |
| Decisor ausente da timeline | declarado como desenho (ADR 0002), com o custo que isso evita |
| Falha de execução | categoria própria, fora das taxas — nunca "decidiu errado" |
| Comparação entre bases diferentes | declarada em vez de calculada como melhora/piora |

As ressalvas de `precisao_consultas` e `acoes_nao_previstas` vêm de
`.run/legenda_seeds_e_metricas.csv` e aparecem ao lado do número, não em nota de rodapé: o
painel não pode reportar o agente como pior do que a evidência sustenta.

## Fidelidade das métricas

O CSV é autoritativo para todo valor por execução — o painel não recalcula nada por
execução. Os agregados espelham `evaluation/runner/report.py`: taxas apenas sobre execuções
que concluíram, `None` (não `0`) para conjunto vazio, e `stable` ternário
(`true`/`false`/`null`) como em `stability.py`.

```bash
python painel/build_bundle.py --verify
```

confere os agregados recalculados contra `resumo_por_cenario.csv` e falha se divergirem.

A exportação em CSV reproduz exatamente o cabeçalho e as convenções de
`resultados_avaliacao.csv` (`;`, `|` para multivalor, `True`/`False`, BOM), para que o
arquivo exportado seja comparável célula a célula com o da bateria.

## Arquivos

| Arquivo | Papel |
| :--- | :--- |
| `build_bundle.py` | varre traces + CSV + gabarito, junta, agrega, emite o bundle |
| `completar_fase.py` | reexecuta as combinações caso×seed que faltam numa fase |
| `recalcular_csv.py` | refaz o CSV de execuções aplicando a camada 1 aos traces |
| `resumir_csv.py` | refaz o resumo por cenário, referência do `--verify` |
| `julgar.py` | roda o comitê via OpenRouter, uma execução por vez |
| `dados/juizes.json` | notas do comitê, gravadas incrementalmente |
| `dados/bundle.json` | gerado; versionado porque `.run/` é gitignored |
| `js/dados.js` | carregamento, estado, filtros e os primitivos de formatação |
| `js/componentes.js` | selos, métricas, timeline e blocos de dado cru |
| `js/operacao.js` | telas da aba Operação — não importa de `avaliacao.js` |
| `js/avaliacao.js` | telas da aba Avaliação |
| `js/export.js` | exportação em CSV |
| `js/painel.js` | cabeçalho, abas e ciclo de redesenho |

Sem dependências de front-end: HTML, CSS e ES modules. O bundle tem ~1,1 MB, e o build usa
só a stdlib do Python.
