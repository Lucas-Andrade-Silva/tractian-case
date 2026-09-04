/* A gaveta — onde vive tudo que é verdadeiro e quase nunca urgente.
 *
 * O painel antigo punha a ressalva metodológica ao lado do número que ela
 * ressalva, no mesmo peso visual. Isso é honesto e ilegível ao mesmo tempo. Aqui
 * a prosa continua inteira, a um gesto de distância, sempre no mesmo lugar.
 *
 * Nada foi apagado na migração: se um texto existia no painel antigo e não está
 * numa destas abas, é bug. */

import { el, ESTADO, num, pct, texto, rotuloAcao, acoesDeImpacto, execucoesDaFase } from "./dados.js";
import { selo, metrica } from "./componentes.js";
import { exportaCsv } from "./export.js";

const ABAS = [
  ["metodo", "Método"],
  ["ressalvas", "Ressalvas"],
  ["auditoria", "Auditoria"],
  ["arquitetura", "Arquitetura"],
];

export function abreGaveta(aba, redesenha) {
  ESTADO.gaveta = aba;
  redesenha();
}

export function botaoGaveta(rotulo, aba, redesenha) {
  return el("button", {
    class: "gaveta-gatilho",
    text: rotulo,
    onclick: () => abreGaveta(aba, redesenha),
  });
}

function corpoMetodo() {
  return el("div", { class: "gaveta-corpo" }, [
    el("h3", { text: "Como cada número é calculado" }),
    el("dl", { class: "campos" }, [
      el("dt", { text: "acurácia de decisão" }),
      el("dd", { text: "execuções cuja decisão final bate com a do gabarito, sobre as execuções que concluíram." }),
      el("dt", { text: "taxa de aprovação" }),
      el("dd", { text: "critério determinístico do runner: decisão certa e trajetória dentro do esperado." }),
      el("dt", { text: "recall de evidência" }),
      el("dd", { text: "fração dos pilares de evidência do gabarito que a execução apurou." }),
      el("dt", { text: "precisão de consultas" }),
      el("dd", {
        text:
          "métrica derivada por mim, não calculada pelo código da avaliação: " +
          "(GETs feitos − extras) / GETs feitos, sem contar GET /users/me. Valor baixo não é " +
          "necessariamente ruim — a política de evidência “fixed” sempre apura os quatro pilares, " +
          "independentemente do que o gabarito daquele caso documentou.",
      }),
      el("dt", { text: "taxa de repetição" }),
      el("dd", {
        text:
          "chamadas repetidas sobre chamadas totais. Chamada servida do cache é marcada como tal, " +
          "mas continua contando como repetição: o custo de rede foi evitado, o de raciocínio não.",
      }),
    ]),
  ]);
}

function corpoRessalvas(bundle) {
  const partes = [
    el("h3", { text: "O que estes números não dizem" }),
    el("p", {}, [
      el("strong", { text: "Reprovação com decisão certa costuma ser artefato. " }),
      "Em vários casos o gabarito estruturado não documenta um POST que o cenário narrativo " +
        "prescreve — nesses casos a reprovação é artefato da medição, não erro do agente.",
    ]),
    el("p", {}, [
      el("strong", { text: "Falha de execução é categoria própria. " }),
      "Execução interrompida por limite de provedor não é decisão errada e não entra na acurácia.",
    ]),
    el("p", {}, [
      el("strong", { text: "Cenário ambíguo aceita mais de um desfecho. " }),
      "Onde o cenário admite mais de uma resolução, escolher qualquer uma delas é acerto.",
    ]),
    el("p", {}, [
      el("strong", { text: "Escalar não é falha. " }),
      "Encaminhar para análise humana quando o caso extrapola o atendimento remoto é desfecho correto.",
    ]),
  ];

  // O comitê só aparece se o bundle o trouxer. Quando aparece, vem com a ressalva
  // de calibração — nota de juiz não validado contra conjunto anotado por humano
  // não é verdade, e não sobe para nenhuma batida.
  if (bundle.juizes) {
    partes.push(
      el("h3", { text: "Comitê de juízes" }),
      el("p", {}, [
        el("strong", { text: "Não calibrado. " }),
        "As notas do comitê só passam a ser leitura válida depois da calibração manual contra um " +
          "conjunto anotado por humano. Enquanto isso não for feito, média de juiz não validado não " +
          "é verdade — este aviso permanece mesmo quando houver notas.",
      ])
    );
  }

  return el("div", { class: "gaveta-corpo" }, partes);
}

function corpoAuditoria(bundle, redesenha) {
  const fase = ESTADO.fase;
  const execucoes = execucoesDaFase(fase);
  const ag = bundle.agregados[fase];

  const acoes = [];
  for (const execucao of execucoes) {
    for (const acao of acoesDeImpacto(execucao)) acoes.push({ execucao, acao });
  }
  const executadas = acoes.filter(({ acao }) => acao.ok);
  const recusadas = acoes.filter(({ acao }) => !acao.ok);

  const lista = (titulo, itens, tom) =>
    itens.length
      ? el("div", {}, [
          el("h3", { text: `${titulo} (${itens.length})` }),
          ...itens.map(({ execucao, acao }) =>
            el("div", { class: "auditoria-item" }, [
              el("div", { class: "auditoria-cabeca" }, [
                el("span", { class: "metodo escrita", text: acao.metodo }),
                el("span", { class: "rota mono", text: acao.rota }),
                selo(rotuloAcao(acao), tom),
                el("span", { class: "gaveta-meta", text: `${execucao.ticket_id} · ${execucao.seed}` }),
              ]),
              // Ação sem a justificativa que a acompanhou não é auditável (RN-13).
              el("div", {
                class: "auditoria-just",
                text: (acao.body && acao.body.justification) || "sem justificativa registrada",
              }),
            ])
          ),
        ])
      : null;

  return el("div", { class: "gaveta-corpo" }, [
    el("h3", { text: `Auditoria e desperdício — ${fase}` }),
    el("div", { class: "metricas" }, [
      metrica("Taxa de repetição", pct(ag.taxa_repeticao_media)),
      metrica("Erros HTTP", num(ag.com_erro_http), "execuções"),
      metrica("Ações executadas", num(executadas.length), `${recusadas.length} recusadas`),
    ]),
    lista("Ações de impacto executadas", executadas, "atencao"),
    lista("Ações recusadas pela API", recusadas, "neutro"),
    el("button", {
      class: "icone-btn",
      text: "Exportar esta visão em CSV",
      onclick: () => exportaCsv(execucoes, fase),
    }),
  ]);
}

function corpoArquitetura() {
  return el("div", { class: "gaveta-corpo" }, [
    el("h3", { text: "Decisões de arquitetura" }),
    el("p", {}, [
      el("strong", { text: "ADR 0002 — o Decisor não tem tools. " }),
      "É o único papel sem ferramentas: decide sobre a evidência que os workers já apuraram, em vez " +
        "de consultar a API. Sem tools não há laço de chamada, e ele gasta exatamente uma chamada de " +
        "LLM por atendimento — contra 2 a 3 dos papéis que investigam. Como é ele que usa o modelo mais " +
        "capaz, é aí que o laço custaria mais. A faixa vazia dele na trajetória é isso, visível.",
    ]),
    el("p", {}, [
      el("strong", { text: "ADR 0003 — enforcement de permissão pela API. " }),
      "Um 403 na trajetória é o enforcement funcionando, não falha do agente.",
    ]),
    el("p", {}, [
      el("strong", { text: "ADR 0007 — consulta livre com gabarito sintético. " }),
      "A questão de referência da aba ao vivo é escrita por um LLM, não por humano. As notas ordenam " +
        "consultas livres entre si e nunca entram nas métricas dos 17 cenários.",
    ]),
  ]);
}

export function desenhaGaveta(redesenha) {
  if (!ESTADO.gaveta) return null;
  const bundle = ESTADO.bundle;

  const corpos = {
    metodo: () => corpoMetodo(),
    ressalvas: () => corpoRessalvas(bundle),
    auditoria: () => corpoAuditoria(bundle, redesenha),
    arquitetura: () => corpoArquitetura(),
  };

  return el("div", { class: "gaveta-fundo", onclick: () => { ESTADO.gaveta = null; redesenha(); } }, [
    el(
      "div",
      {
        class: "gaveta",
        role: "dialog",
        "aria-label": "Método e ressalvas",
        onclick: (ev) => ev.stopPropagation(),
      },
      [
        el("div", { class: "gaveta-abas" }, [
          ...ABAS.map(([chave, rotulo]) =>
            el("button", {
              text: rotulo,
              "aria-selected": String(ESTADO.gaveta === chave),
              onclick: () => { ESTADO.gaveta = chave; redesenha(); },
            })
          ),
          el("button", {
            class: "gaveta-fechar",
            text: "fechar",
            onclick: () => { ESTADO.gaveta = null; redesenha(); },
          }),
        ]),
        (corpos[ESTADO.gaveta] || corpos.metodo)(),
      ]
    ),
  ]);
}
