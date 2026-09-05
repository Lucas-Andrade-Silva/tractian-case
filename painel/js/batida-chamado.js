/* Batida ② — por quê?
 *
 * REGRA INEGOCIÁVEL (RN-01): esta tela nunca exibe gabarito, decisão aceita ou
 * status de aprovação. Nem em texto, nem em cor, nem em tooltip. A regra é
 * estrutural: este módulo lê apenas `execucao.operacao` e não importa nada do
 * módulo de avaliação nem de `batida-matriz.js`. Verificável por leitura de import. */

import {
  ESTADO, el, texto, num, duracao, VAZIO,
  PAPEIS_PT, filaVisivel, DECISOES,
} from "./dados.js";
import { selo, seloDecisao, vazio } from "./componentes.js";
import { faixasPorPapel } from "./faixas.js";
import { rodape } from "./batidas.js";

/** Markdown mínimo da resposta ao cliente. Escapa antes de formatar: veio de um LLM. */
function markdownSimples(bruto) {
  if (!bruto || !String(bruto).trim()) return "não determinado";
  return String(bruto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function kpi(valor, rotulo) {
  return el("div", { class: "kpi-item" }, [
    el("span", { text: valor }),
    el("em", { text: rotulo }),
  ]);
}

/** Seletor de caso: a fila antiga vira gaveta lateral desta batida. */
function seletorCaso(execucao, redesenha) {
  const aberta = ESTADO.filaAberta;
  const gatilho = el("button", {
    class: "seletor-caso mono",
    "aria-expanded": String(aberta),
    text: `${execucao.ticket_id} ⌄`,
    onclick: () => {
      ESTADO.filaAberta = !aberta;
      redesenha();
    },
  });

  if (!aberta) return gatilho;

  const lista = filaVisivel().map((e) =>
    el("button", {
      class: "fila-item",
      "aria-current": String(e.id === ESTADO.execucaoId),
      onclick: () => {
        ESTADO.execucaoId = e.id;
        ESTADO.filaAberta = false;
        redesenha();
      },
    }, [
      el("span", { class: "ticket mono", text: e.ticket_id }),
      el("span", { class: "cenario", text: e.cenario }),
      seloDecisao(e.operacao.decisao),
    ])
  );

  return el("div", { class: "seletor-wrap" }, [
    gatilho,
    el("div", { class: "fila-gaveta" }, [
      el("input", {
        type: "search",
        placeholder: "Buscar ticket, ativo, empresa ou mensagem",
        value: ESTADO.busca,
        "aria-label": "Buscar chamado",
        oninput: (ev) => {
          ESTADO.busca = ev.target.value;
          redesenha();
        },
      }),
      el("div", { class: "fila" }, lista.length ? lista : [vazio("Nenhum chamado corresponde.")]),
    ]),
  ]);
}

export function batidaChamado(redesenha) {
  const execucao = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.execucaoId);

  if (!execucao) {
    return el("main", { class: "batida" }, [
      el("div", { class: "batida-corpo" }, [vazio("Selecione um chamado.")]),
      rodape(redesenha),
    ]);
  }

  const op = execucao.operacao;
  const solicitante = op.solicitante || {};
  const ativo = op.ativo || {};
  const consumo = op.consumo || {};
  const chamadasApi = op.timeline.filter((e) => e.tipo === "chamada").length;

  const corpo = el("div", { class: "batida-corpo" }, [
    el("div", { class: "chamado-cabeca" }, [
      seletorCaso(execucao, redesenha),
      selo(execucao.cenario, "quieto", { class: "selo selo-quieto mono" }),
      seloDecisao(op.decisao),
      selo(
        `${texto(ativo.name)} · criticidade ${texto(ativo.criticality)}`,
        ativo.criticality === "high" ? "atencao" : "quieto"
      ),
      selo(
        `${texto(solicitante.name)} · ${PAPEIS_PT[solicitante.role] || texto(solicitante.role)}`,
        "quieto"
      ),
    ]),

    // Mensagem íntegra do cliente. Borda lateral aqui significa citação literal —
    // e é o único lugar do painel onde ela significa isso.
    el("blockquote", { class: "mensagem", text: texto(op.mensagem) }),

    el("div", { class: "kpis" }, [
      kpi(num(consumo.llm_calls), "chamadas de LLM"),
      kpi(num(chamadasApi), "chamadas de API"),
      kpi(num(consumo.total_tokens), "tokens"),
      kpi(duracao(op.duracao_ms), "duração"),
      kpi(texto(op.stop_reason), "parada"),
    ]),

    faixasPorPapel(execucao, ESTADO, redesenha),

    el("div", { class: "bloco-resposta" }, [
      el("div", { class: "rotulo-cru", text: "resposta entregue ao cliente" }),
      // RN-16: íntegra, sem truncar.
      el("div", { class: "resposta-final", html: markdownSimples(op.resposta_final) }),
    ]),
  ]);

  return el("main", { class: "batida" }, [
    corpo,
    rodape(redesenha, ["ⓘ arquitetura dos papéis", "arquitetura"]),
  ]);
}
