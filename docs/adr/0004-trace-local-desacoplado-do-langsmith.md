# Trace estruturado local, desacoplado do LangSmith

O agente usa LangSmith para observabilidade e depuração durante o desenvolvimento — é a integração
nativa do LangGraph, e captura automaticamente cada nó, tool call e transição sem instrumentação
manual. Seria natural também usar o LangSmith como fonte de dados para a Parte 2 (avaliação),
exportando os traces de lá via API.

Decidimos não fazer isso. O agente grava, em paralelo e via callback do próprio LangGraph, um trace
estruturado próprio em JSON local, no mesmo formato do golden set (`eval/expected-paths.json`). É
esse arquivo local — não o LangSmith — que a Parte 2 lê.

Motivo: a Parte 2 precisa rodar de forma reprodutível, sem depender da disponibilidade ou da API de
um serviço externo, e sem precisar mapear a estrutura de trace de terceiros para o formato do golden
set a cada execução. LangSmith continua sendo a ferramenta certa para inspeção humana durante o
desenvolvimento; o trace local é a fonte de verdade para avaliação automatizada.
