# Tractian × Inteli — Agente de Suporte Industrial

Agente de IA que investiga solicitações de suporte sobre ativos industriais (vibração, manutenção
preditiva) via uma API industrial simplificada, decide entre orientar, agir ou escalar, e é avaliado
sistematicamente contra um conjunto de cenários curados.

## Language

### Domínio industrial (dado, herdado do STUDENT-GUIDE)

**Baseline**:
Estado normal aprendido de um ativo a partir de histórico sadio. Ciclo de vida: `learning` (dados
insuficientes) → `established` (utilizável) → `invalidated` (após manutenção ou mudança de
configuração; exige reaprendizado). O limiar de alarme de RMS deriva do baseline
(`reference + tolerance`), nunca de norma fixa.
_Avoid_: threshold fixo, norma ISO (não é como o limiar é calculado neste domínio).

**Detecção por baseline** (`detection_mode=baseline`):
Falha identificada por desvio em relação ao baseline do ativo (desbalanceamento, desalinhamento,
falha de rolamento, falha elétrica). Exige baseline `established` para ser confiável.

**Detecção sintomática** (`detection_mode=symptom`):
Falha identificada pela mera presença de um sintoma (ex.: lubrificação), independente do estado do
baseline — pode ser detectada mesmo com baseline em `learning`.
_Avoid_: confundir com detecção por baseline; são modos de detecção distintos com requisitos
diferentes.

**Análise (insight)**:
Diagnóstico automático do modelo sobre um ativo: tipo de falha, severidade, confiança, evidência,
limitações e modo de detecção usado.
_Avoid_: "resultado", "output do modelo" — o termo do domínio é "análise" ou "insight".

**Qualidade e frescor dos dados**:
Completude, relação sinal-ruído (SNR) e atualidade de uma leitura. Afeta diretamente a
confiabilidade de uma análise e de um baseline — sempre comparar contra os requisitos mínimos do
modelo, não julgar isoladamente.

### Papéis do agente

O agente de suporte é composto por cinco papéis especializados, cada um responsável por uma fatia
distinta do processo de atendimento de um caso.

**Supervisor**:
Papel que decide, a cada passo, qual dos demais papéis deve agir em seguida — com base no que já foi
apurado até aquele ponto. Também é responsável por estabelecer o contexto de autorização do caso
(identidade e permissões do usuário) uma única vez, no início do atendimento.
_Avoid_: "orquestrador" — no domínio deste projeto, orquestrador é o mecanismo de implementação; o
Supervisor é o papel que ele desempenha.

**Investigador**:
Papel que reúne evidência técnica quantitativa sobre um ativo (configuração, análises, baseline,
vibração, espectro, cobertura de modelo). Nunca decide a resolução do caso, apenas apura fatos.

**Contextualizador**:
Papel que recupera conhecimento documental aplicável ao caso (procedimentos, glossário, orientações)
e o relaciona à evidência técnica já apurada. Distinto do Investigador porque a fonte é documental,
não sensor ou análise.

**Decisor**:
Papel que pesa toda a evidência apurada (técnica e documental) junto com a permissão do usuário, e
resolve o caso entre orientar, agir ou escalar, produzindo a justificativa correspondente. É o único
papel que toma essa resolução — Investigador e Contextualizador apenas apuram, não decidem.

**Executor**:
Papel que realiza, na plataforma, a ação que o Decisor determinou. Só atua depois de uma resolução
formal do Decisor — nunca decide por conta própria executar algo.

### Decisão do agente

**Orientar**:
O agente explica a situação ao cliente sem alterar nada na plataforma.

**Agir**:
O agente executa uma ação justificada na plataforma (reprocessar análise, solicitar análise
especializada, alterar configuração técnica, solicitar retreinamento de modelo).

**Escalar**:
O agente encaminha o caso para análise humana porque ele extrapola o que pode ser resolvido
remotamente.
_Avoid_: usar "escalar" para "solicitar análise especializada" — isso é uma ação interna/técnica
(`agir`), diferente de escalonamento para humano em campo.

**Over-escalation**:
Escalar um caso que na verdade era resolvível remotamente (ex.: por reprocesso). É tratado como má
conduta do agente, não como comportamento seguro por padrão — os cenários testam explicitamente essa
calibração.

**Justificativa**:
Explicação textual, fundamentada em evidência concreta, exigida para toda ação de impacto na
plataforma (mínimo de 20 caracteres, imposto pela API). Uma justificativa fraca ou ausente é
rejeitada pela própria plataforma. Não é um campo burocrático: distingue uma ação embasada
("insights sistematicamente incorretos sobre baseline invalidated") de uma pedida por achismo ou
insatisfação isolada.

**Ação comum vs. ação de alto impacto** (`action_low` / `action_high`):
Duas classes de ação na plataforma, cada uma exigindo uma permissão distinta do usuário. Ação comum
(`action_low`) cobre intervenções de menor risco, como reprocessar uma análise. Ação de alto impacto
(`action_high`) cobre intervenções de maior consequência, como alterar a criticidade de um ativo ou
solicitar retreinamento de um modelo — por isso exige evidência mais forte e justificativa mais
robusta, não apenas a permissão em si.

**Escopo de uso autônomo**:
O agente decide e executa ações por conta própria, mas apenas dentro do que a permissão do usuário
da sessão autoriza — o teto é imposto pela própria API (rejeição com 403), não por uma lista
adicional de restrições. Diferente de "copiloto" (que exigiria confirmação humana antes de agir) e
de "atendimento direto" (conversa com cliente final, não com um analista/técnico interno).

### Avaliação (Parte 2)

**Golden set**:
O conjunto de cenários curados manualmente (por especialista Tractian) que definem o comportamento
esperado do agente, usado como referência de desenvolvimento — os 16 cenários originais do projeto.
_Avoid_: "gabarito" isoladamente é aceitável como sinônimo coloquial, mas "golden set" é o termo
técnico preferido na documentação.

**Holdout**:
Um conjunto de casos reservado para o teste final, deliberadamente não usado durante o
desenvolvimento/ajuste do agente — protege a avaliação de medir apenas "quão bem o agente decorou os
cenários de desenvolvimento" em vez de generalização real.

**Auditoria mecânica**:
Verificar um cenário executando de fato os passos contra a API rodando localmente e comparando a
resposta literal com o que o cenário afirma — não é julgamento por leitura do schema, é confirmação
reproduzível contra o sistema real.

**Trajetória**:
A sequência de chamadas à API feita pelo agente ao investigar um caso. É tratada como referência, não
como script rígido — variação na ordem é aceitável desde que justificável.

**Instabilidade** (entre execuções/seeds):
Ocorre quando a decisão final (orientar/agir/escalar) diverge entre execuções do mesmo cenário.
Variação na trajetória entre execuções não conta como instabilidade.

**Rubrica**:
Tabela de critérios explícitos que define o que cada nível de nota significa, usada para guiar uma
avaliação de forma reproduzível — em vez de pedir uma nota sem critério declarado.

### Mecânica da API (dada, herdada do contrato)

**Seed**:
Parâmetro que torna o comportamento probabilístico da API determinístico — a mesma chamada com o
mesmo seed sempre retorna o mesmo modo de resposta (`complete`, `partial`, `inconclusive`,
`conflict`, `unavailable`). Sem seed, o modo é sorteado por uma distribuição fixa.

**Tool**:
Uma função exposta a um agente de LLM, com nome, parâmetros tipados e descrição — o mecanismo pelo
qual o agente aciona um endpoint real da API industrial (function calling).
