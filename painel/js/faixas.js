/* Faixas por papel — a trajetória do atendimento como geometria.
 *
 * Este módulo existe para não precisar da prosa que ele substitui. A faixa do
 * Decisor tem um ponto de LLM e nenhuma chamada de API: a assimetria da ADR 0002
 * fica visível, em vez de explicada em quatro linhas de texto.
 *
 * Endpoints não aparecem por padrão (decisão do redesenho): o que ocupa o lugar
 * deles são os fatos que eles produziram, lidos de `achados[].summary`. */

import { el, num, pct, texto, PAPEIS_PT } from "./dados.js";

/** Tom da tag pelo teor do fato. Neutro é o padrão: só o que é anômalo colore. */
const PADROES_TOM = [
  [/invalidated|stale|exceeds_alarm|=true/, "atencao"],
  [/online|ok|=false/, "sucesso"],
];

/** Quebra `achados[].summary` em tags. Formato: `chave=valor (origem)` por linha. */
export function fatosDoAchado(resumo) {
  const linhas = String(resumo || "").split("\n").map((l) => l.trim()).filter(Boolean);
  return linhas.map((linha) => {
    const semOrigem = linha.replace(/\s*\([^)]*\)\s*$/, "");
    const corte = semOrigem.indexOf("=");
    const chave = corte === -1 ? semOrigem : semOrigem.slice(0, corte);
    const valor = corte === -1 ? "" : semOrigem.slice(corte + 1);
    const tom = (PADROES_TOM.find(([re]) => re.test(semOrigem)) || [null, "quieto"])[1];
    return { chave, valor, tom };
  });
}

function tagFato(fato) {
  const rotulo = fato.valor ? `${fato.chave} ${fato.valor}` : fato.chave;
  return el("span", { class: `fato fato-${fato.tom} mono`, text: rotulo });
}

/** Uma faixa: nome do papel, o que ele fez, e quanto custou. */
function faixa(papel, conteudoMeio, consumoPapel, totalTokens, extras = {}) {
  const tokens = consumoPapel ? consumoPapel.total_tokens : 0;
  return el("div", { class: `faixa${extras.destaque ? " faixa-destaque" : ""}` }, [
    el("div", { class: "faixa-nome" }, [
      el("span", { text: PAPEIS_PT[papel] || papel }),
      el("em", { text: extras.subtitulo || "" }),
    ]),
    el("div", { class: "faixa-meio" }, conteudoMeio),
    el("div", { class: "faixa-custo" }, [
      el("b", { text: consumoPapel ? num(tokens) : "—" }),
      el("span", {
        text: totalTokens && tokens ? `${pct(tokens / totalTokens, 0)} do caso` : "",
      }),
    ]),
  ]);
}

function pontoLlm() {
  return el("span", { class: "ponto-llm", title: "uma chamada de LLM" });
}

/**
 * Desenha a trajetória em faixas por papel.
 * `estado.faixasAbertas` é um Set de chaves `execucaoId:papel` para as rotas cruas.
 */
export function faixasPorPapel(execucao, estado, redesenha) {
  const op = execucao.operacao;
  const consumo = op.consumo || {};
  const porPapel = consumo.by_agent || {};
  const total = consumo.total_tokens || 0;
  const achadosPorPapel = new Map((op.achados || []).map((a) => [a.agent, a.summary]));

  // Ordem de entrada em cena, deduzida da timeline — não uma lista fixa.
  const ordem = [];
  for (const evento of op.timeline) {
    const papel = evento.tipo === "roteamento" ? evento.para : evento.papel;
    if (papel && !ordem.includes(papel)) ordem.push(papel);
  }
  for (const papel of Object.keys(porPapel)) {
    if (!ordem.includes(papel)) ordem.push(papel);
  }

  const chamadasPorPapel = new Map();
  let papelCorrente = null;
  for (const evento of op.timeline) {
    if (evento.tipo === "roteamento") papelCorrente = evento.para;
    else if (evento.tipo === "chamada" && papelCorrente) {
      if (!chamadasPorPapel.has(papelCorrente)) chamadasPorPapel.set(papelCorrente, []);
      chamadasPorPapel.get(papelCorrente).push(evento);
    }
  }

  const motivos = new Map(
    op.timeline
      .filter((e) => e.tipo === "roteamento")
      .map((e) => [e.para, e.motivo])
  );

  const nodes = [];
  for (const papel of ordem) {
    const motivo = motivos.get(papel);
    if (motivo) {
      nodes.push(
        el("div", { class: "faixa-bastao" }, [
          el("span", { text: "↳ " }),
          el("span", { text: texto(motivo) }),
          el("span", { text: ` → ${PAPEIS_PT[papel] || papel}` }),
        ])
      );
    }

    const chamadas = chamadasPorPapel.get(papel) || [];
    const fatos = fatosDoAchado(achadosPorPapel.get(papel));
    const meio = [pontoLlm()];

    if (fatos.length) meio.push(...fatos.map(tagFato));
    if (chamadas.length) {
      const chave = `${execucao.id}:${papel}`;
      const aberta = estado.faixasAbertas.has(chave);
      meio.push(
        el("button", {
          class: "faixa-rotas",
          "aria-expanded": String(aberta),
          text: `${chamadas.length} ${chamadas.length === 1 ? "consulta" : "consultas"} ⌄`,
          onclick: () => {
            if (aberta) estado.faixasAbertas.delete(chave);
            else estado.faixasAbertas.add(chave);
            redesenha();
          },
        })
      );
    }
    if (!fatos.length && !chamadas.length) {
      meio.push(
        el("span", {
          class: "faixa-vazia",
          text: papel === "decisor"
            ? "zero consultas — não tem tools (ADR 0002)"
            : "não consulta a plataforma",
        })
      );
    }

    nodes.push(
      faixa(papel, meio, porPapel[papel], total, {
        destaque: papel === "decisor",
        subtitulo: fatos.length ? `apurou ${fatos.length} fatos` : "",
      })
    );

    const chave = `${execucao.id}:${papel}`;
    if (estado.faixasAbertas.has(chave) && chamadas.length) {
      nodes.push(
        el(
          "div",
          { class: "faixa-cruas" },
          chamadas.map((c) =>
            el("div", { class: "crua-linha mono" }, [
              el("span", { class: `metodo${c.metodo === "GET" ? "" : " escrita"}`, text: c.metodo }),
              el("span", { class: "rota", text: c.rota }),
              el("span", { text: `${c.status_code}` }),
              el("span", { text: `${num(c.latencia_ms)} ms` }),
            ])
          )
        )
      );
    }
  }

  return el("div", { class: "faixas" }, nodes);
}
