# Holdout sintético auditado, em vez de dividir os 16 cenários originais

Avaliar o agente apenas contra os cenários usados durante o desenvolvimento arrisca medir "quão bem
o agente decorou esses casos" em vez de generalização real (Lei de Goodhart) — por isso a Parte 2
precisa de um holdout: casos não vistos durante o ajuste do agente.

A abordagem óbvia seria dividir os 16 cenários originais em dois grupos (ex.: 8 para desenvolvimento,
8 para teste). Rejeitamos essa opção: os 16 cenários não são intercambiáveis — cada um cobre uma
faceta não-redundante do domínio (ex.: CEN-04 é o único caso `detection_mode=symptom`; CEN-05 é o
único com espectro parcial; CEN-15/16 são os únicos que exercitam ações `action_high`). Dividir ao
meio corta cobertura de facetas inteiras do domínio em um dos dois lados, não apenas reduz volume.

Decidimos manter os 16 originais **inteiros** como conjunto de desenvolvimento, e gerar um holdout
com cenários **sintéticos novos e adicionais**, reaproveitando ativos e dados já existentes nos
parquets (sem estender `data/*.parquet`). Cada cenário sintético só entra no holdout depois de
**auditoria mecânica**: rodar de fato contra a API local com um `seed` fixo e confirmar que a
resposta real sustenta a resolução esperada do cenário — o mesmo processo já documentado na seção
"Auditoria dos cenários" de `docs/test-scenarios.md`, que corrigiu CEN-05 e CEN-08 dessa forma.

Isso não compromete a legitimidade do teste: os 16 originais também são dados sintéticos e fictícios
(não dados reais de clientes), então a diferença entre eles e o holdout não é "real vs. inventado" —
é curadoria por especialista Tractian vs. curadoria própria verificada mecanicamente contra o sistema
real.
