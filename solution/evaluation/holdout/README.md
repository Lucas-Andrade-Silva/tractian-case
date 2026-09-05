# Holdout sintético auditado

Conjunto reservado para o **teste final** do agente, conforme
[ADR 0006](../../docs/adr/0006-holdout-sintetico-auditado.md). Os 16 cenários originais ficam
inteiros como conjunto de desenvolvimento; este holdout mede generalização.

> **Não use este conjunto durante o ajuste do agente.** Um holdout visto durante o
> desenvolvimento deixa de ser holdout.

| Arquivo | Conteúdo | Quem lê |
| :--- | :--- | :--- |
| `cases.json` | Mensagem + contexto (empresa, usuário, ativo) | Passado ao agente |
| `expected-paths.json` | Gabarito: trajetória, resolução aceita, faceta e asserções de auditoria | Só a avaliação |

## Por que cenários novos, e não uma divisão dos 16

Dividir os originais cortaria facetas inteiras do domínio: CEN-04 é o único caso
`detection_mode=symptom`, CEN-05 o único com espectro parcial, CEN-15/16 os únicos com
`action_high`. A perda seria de cobertura, não só de volume.

Os cenários aqui são novos, sobre **ativos que nenhum cenário original toca** — garantido
por teste (`test_holdout_uses_assets_untouched_by_the_original_scenarios`) — e usam apenas
dados já presentes nos parquets, sem estendê-los.

## Os 8 cenários

| # | Ativo | Usuário | Faceta que testa | Resolução |
| :-- | :--- | :--- | :--- | :--- |
| HOLD-01 | C-510 britador | pedro (read, escalate) | Cobertura do **tipo** ≠ capacidade **no ativo**: modelo diz `can_learn_baseline=true` para mill, mas o ativo tem `learnable=false` + qualidade abaixo dos requisitos | orientar |
| HOLD-02 | B-211 bomba | lucas (read, action_low) | Baseline invalidado por **`config_change`** (originais só cobrem manutenção) + pedido de reprocesso sobre ativo **sem nenhuma análise** | orientar |
| HOLD-03 | F-215 ventilador | carla (read, action_high) | **Armadilha da norma ISO** com número concreto: limiar real é 4.9 (3.4+1.5) e o RMS máximo é 3.589 — abaixo | orientar |
| HOLD-04 | M-428 motor | bruno (read) | Baseline `learning` por ativo **novo**, com qualidade **boa** — culpar sensor/dados aqui é erro (contraste direto com HOLD-01) | orientar |
| HOLD-05 | S-425 spindle | bruno (read) | Ativo **saudável** com o cliente sugerindo falha por analogia — inventar falha é o erro medido | orientar |
| HOLD-06 | F-115 ventilador | ana (action_high) | Ação de alto impacto **autorizada**, com justificativa de negócio legítima | agir |
| HOLD-07 | X-216 misturador | carla (action_high) | Mesma ação na **direção oposta** (rebaixar), usuária **sem** `escalate` | agir |
| HOLD-08 | B-211 bomba | lucas (**sem** `escalate`) | **403 na permissão `escalate`** — os originais só exercitam 403 em `action_high` | escalar |

## Auditoria mecânica

Nenhum cenário entra sem ser executado contra a API real com `seed=complete`, confirmando
que a resposta sustenta o que ele afirma:

```bash
make holdout-audit
```

Estado atual: **41/41 asserções confirmadas, 8/8 cenários auditados**.

A auditoria já pagou por si: a primeira execução reprovou HOLD-06 e HOLD-07, porque eu
havia escrito a asserção como `data.accepted` — mas endpoints de ação retornam
`ActionResult` **cru**, sem o envelope `{mode, notes, data}` dos GETs. O campo correto é
`accepted` na raiz. Um erro que a leitura do schema não pegaria.

## Uso

```bash
make holdout-audit                 # confirma que os dados sustentam os cenários
make holdout SEEDS=complete,s2,s3  # avalia o agente no holdout (teste final)
```

Os traces vão para `../results/traces/holdout/`, separados dos do golden set — misturá-los
falsearia as métricas agregadas.

## Limitações conhecidas

- **Distribuição de resoluções desbalanceada** (5 orientar · 2 agir · 1 escalar). Os
  ativos livres nos parquets são, em sua maioria, saudáveis (`type=none, severity=none`),
  e o ADR 0006 proíbe estender `data/*.parquet` — então cenários legítimos de `agir` são
  escassos. Consequência prática: **a acurácia de decisão no holdout não deve ser lida
  isoladamente**, porque um agente que sempre responde "orientar" acertaria 5/8. Leia
  junto com `unexpected_actions` e com as notas do comitê de juízes.
- **Escalonamento bem-sucedido não é testável.** `POST /cases/{id}/escalate` valida a
  permissão *antes* de procurar o caso, e os casos do holdout não existem em
  `data/cases.parquet` — logo um usuário **com** permissão receberia 404, não 200. Só o
  caminho 403 (HOLD-08) é observável. Por isso nenhum cenário aceita escalonamento
  bem-sucedido como resolução correta.
- **Envelope sempre `complete`.** Os ativos do holdout não têm override em `seed.json`,
  e a auditoria usa `seed=complete`. A dificuldade aqui é de **domínio** (baseline,
  cobertura, qualidade), não de degradação de envelope — que os cenários originais já
  exercitam. Um holdout complementar com seeds degradados é uma evolução possível.
- **Curadoria própria**, não de especialista Tractian. A mitigação é a auditoria
  mecânica: cada afirmação é verificada contra o sistema real, e não contra minha leitura
  do schema.
