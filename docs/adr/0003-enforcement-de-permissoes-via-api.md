# Enforcement de permissões via API, não bloqueado em código

O agente opera de forma autônoma, executando ações sozinho dentro do que a permissão do usuário da
sessão autoriza. A forma óbvia de garantir isso seria verificar as permissões no código do
orquestrador *antes* de deixar o agente tentar uma ação de impacto, bloqueando a chamada
preventivamente se faltar permissão.

Decidimos o oposto: a política de permissões vive apenas no prompt (orientando o agente sobre o que
cada perfil pode fazer), e o **enforcement real acontece na API**, que já rejeita com 403 quando a
permissão falta. O agente não é bloqueado antes de tentar.

Isso é contra-intuitivo à primeira vista — parece mais seguro bloquear cedo — mas bloquear em código
eliminaria exatamente o comportamento que vários cenários avaliam explicitamente: como o agente reage
a uma tentativa rejeitada por 403 (CEN-14, CEN-15, CEN-16). O mesmo raciocínio define o "escopo" do
agente autônomo: o escopo autorizado é exatamente o que a permissão do usuário permite, sem lista
adicional de ações sempre-proibidas em código — a API é a única fonte de verdade do limite.
