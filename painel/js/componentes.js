/* Peças compartilhadas pelas duas abas: selos, métricas, timeline e blocos de dado cru.
 *
 * A regra de cor está concentrada aqui: quatro categorias, e "escalado" ou "recusado por
 * permissão" são neutros — nunca erro. O instinto de pintar uma interrupção de vermelho é
 * exatamente o que este domínio não admite. */

import { el, pct, num, texto, VAZIO, MODOS, DECISOES, permissaoExigida, perfisComPermissao, PAPEIS_PT } from "./dados.js";

export function selo(rotulo, tom = "quieto", extras = {}) {
  return el("span", { class: `selo selo-${tom}`, ...extras }, [rotulo]);
}

export function seloDecisao(decisao) {
  if (!decisao) return selo("sem decisão", "atencao");
  const d = DECISOES[decisao] || { texto: decisao, tom: "quieto" };
  return selo(d.texto, d.tom);
}

/** Selo do `mode`. Evidência, não metadado técnico — sempre visível (RN-12). */
export function seloModo(modo) {
  if (!modo) {
    // Ação e /users/me não passam pelo envelope probabilístico. Não é dado faltando.
    return selo("sem modo", "quieto", { title: "Resposta fora do envelope probabilístico (ação ou sessão)." });
  }
  const m = MODOS[modo] || { texto: modo, tom: "quieto", ajuda: "" };
  return selo(m.texto, m.tom, { title: `mode=${modo} — ${m.ajuda}` });
}

/** Status HTTP. 403 é enforcement funcionando, não bug (RN-11). */
export function seloStatus(passo, bundle) {
  const codigo = passo.status_code;
  if (passo.ok) return selo(String(codigo), "quieto", { class: "selo selo-quieto mono" });

  if (codigo === 403) {
    const permissao = permissaoExigida(passo);
    const perfis = permissao ? perfisComPermissao(bundle, permissao) : [];
    const quem = perfis.length
      ? ` Teriam autorização: ${perfis.map((p) => PAPEIS_PT[p] || p).join(", ")}.`
      : "";
    return selo("recusado por permissão", "neutro", {
      title: `403 — exige ${permissao || "permissão não identificada"}.${quem}`,
    });
  }
  if (codigo === 404) return selo(`${codigo} não encontrado`, "atencao");
  if (codigo === 400) return selo(`${codigo} inválido`, "atencao");
  return selo(String(codigo), "erro");
}

export function metrica(rotulo, valor, detalhe) {
  const ausente = valor === VAZIO;
  return el("div", { class: "metrica" }, [
    el("div", { class: "rotulo", text: rotulo }),
    el("div", { class: `valor${ausente ? " vazio" : ""}`, text: valor }),
    detalhe ? el("div", { class: "detalhe", text: detalhe }) : null,
  ]);
}

export function secao(titulo, nota, conteudo) {
  return el("section", { class: "secao" }, [
    el("div", { class: "secao-cabeca" }, [
      el("h2", { text: titulo }),
      nota ? el("span", { class: "secao-nota", text: nota }) : null,
    ]),
    ...[].concat(conteudo),
  ]);
}

export function aviso(tom, conteudo) {
  return el("div", { class: `aviso aviso-${tom}` }, [].concat(conteudo));
}

export function vazio(mensagem) {
  return el("div", { class: "vazio-estado", text: mensagem });
}

export function blocoCru(rotulo, valor) {
  const corpo = typeof valor === "string" ? valor : JSON.stringify(valor, null, 2);
  return el("div", {}, [
    el("div", { class: "rotulo-cru", text: rotulo }),
    el("pre", { class: "cru", text: corpo }),
  ]);
}

/* -- timeline ----------------------------------------------------------- */

/** Uma chamada: linha compacta expansível para o response real (RF-14, RF-15). */
function linhaChamada(evento, chaveExpansao, estado, redesenha, bundle, maiorLatencia) {
  const aberta = estado.expandidas.has(chaveExpansao);
  const latencia = evento.latencia_ms ?? 0;
  const proporcao = maiorLatencia > 0 ? Math.max(2, (latencia / maiorLatencia) * 100) : 2;

  const cabeca = el(
    "button",
    {
      class: "chamada-linha",
      "aria-expanded": String(aberta),
      onclick: () => {
        if (aberta) estado.expandidas.delete(chaveExpansao);
        else estado.expandidas.add(chaveExpansao);
        redesenha();
      },
    },
    [
      el("span", { class: `metodo${evento.metodo === "GET" ? "" : " escrita"}`, text: evento.metodo }),
      el("span", { class: "rota", text: evento.rota + queryEmTexto(evento.query) }),
      el("span", { class: "chamada-selos" }, [
        seloModo(evento.mode),
        seloStatus(evento, bundle),
        // Cache poupou rede, não raciocínio: continua contando como repetição (RN-15).
        evento.do_cache
          ? selo("cache", "quieto", { title: "Servida do cache da execução. Conta como repetição no desperdício." })
          : null,
      ]),
      el("span", { class: "barra" }, [
        el("i", { class: latencia > 1500 ? "lenta" : "", style: `width:${proporcao}%` }),
      ]),
      el("span", { class: "latencia", text: `${num(latencia)} ms` }),
    ]
  );

  const partes = [cabeca];
  if (aberta) {
    const corpo = el("div", { class: "chamada-corpo" }, [
      evento.notes ? el("div", { class: "notas", text: evento.notes }) : null,
      evento.body ? blocoCru("corpo enviado", evento.body) : null,
      evento.response
        ? blocoCru(evento.ok ? "response" : "resposta de erro", evento.response)
        : el("div", { class: "notas", text: "Sem corpo de resposta registrado." }),
    ]);
    partes.push(corpo);
  }
  return el("div", { class: "chamada" }, partes);
}

function queryEmTexto(query) {
  const entradas = Object.entries(query || {});
  if (!entradas.length) return "";
  return "?" + entradas.map(([k, v]) => `${k}=${v}`).join("&");
}

/**
 * Timeline do atendimento (RF-13): cada transição do Supervisor com o motivo do
 * roteamento, intercalada com as chamadas do papel que assumiu.
 */
export function timeline(execucao, estado, redesenha, bundle) {
  const eventos = execucao.operacao.timeline;
  const maiorLatencia = Math.max(
    1,
    ...eventos.filter((e) => e.tipo === "chamada").map((e) => e.latencia_ms || 0)
  );

  const nodes = eventos.map((evento, indice) => {
    if (evento.tipo === "roteamento") {
      return el("div", { class: "tl-roteamento" }, [
        el("div", { class: "tl-turno", text: `t${evento.turno}` }),
        el("div", {}, [
          el("div", { class: "tl-transicao" }, [
            el("span", { text: evento.de }),
            el("span", { class: "tl-seta", text: "→" }),
            el("span", { text: evento.para }),
          ]),
          el("div", { class: "tl-motivo", text: texto(evento.motivo) }),
        ]),
      ]);
    }
    if (evento.tipo === "achado") {
      return el("div", { class: "tl-achado" }, [
        el("div", { class: "quem", text: `resumo de ${evento.papel}` }),
        el("pre", { text: texto(evento.resumo) }),
      ]);
    }
    return linhaChamada(evento, `${execucao.id}:${indice}`, estado, redesenha, bundle, maiorLatencia);
  });

  return el("div", { class: "timeline" }, nodes);
}

/** Legenda dos 5 modos + a nota sobre o Decisor não chamar a API. */
export function legendaTimeline() {
  const itens = Object.entries(MODOS).map(([chave, m]) =>
    el("span", {}, [seloModo(chave), el("span", { text: m.ajuda })])
  );
  return el("div", {}, [
    el("div", { class: "legenda-cores" }, itens),
    // Sem esta nota a faixa ausente do Decisor é lida como instrumentação incompleta.
    // É o oposto: é a arquitetura funcionando, e é o que mantém o papel barato.
    el("div", { class: "secao-nota", style: "margin-top:8px;max-width:80ch" }, [
      el("strong", { text: "O Decisor não aparece na timeline — por desenho. " }),
      "É o único papel sem tools (ADR 0002): decide sobre a evidência que os workers já " +
        "apuraram, em vez de consultar a API. Sem tools não há laço de chamada, e ele " +
        "gasta exatamente uma chamada de LLM por atendimento — contra 2 a 3 dos papéis " +
        "que investigam. Como é ele que usa o modelo mais capaz, é aí que o laço custaria mais.",
    ]),
  ]);
}
