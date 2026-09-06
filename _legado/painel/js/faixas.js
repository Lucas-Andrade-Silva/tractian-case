/* Faixas por papel — a trajetória do atendimento como geometria.
 *
 * Este módulo existe para não precisar da prosa que ele substitui. A faixa do
 * Decisor tem um ponto de LLM e nenhuma chamada de API: a assimetria da ADR 0002
 * fica visível, em vez de explicada em quatro linhas de texto.
 *
 * Endpoints não aparecem por padrão (decisão do redesenho): o que ocupa o lugar
 * deles são os fatos que eles produziram, lidos de `achados[].summary`. */

import { el, num, pct, texto, PAPEIS_PT } from "./dados.js";

/* Um fato é "notável" quando o valor denuncia um estado, não quando a chave
 * contém uma palavra alarmante: `baseline.invalidated_at=2026-07-11` é uma data,
 * e pintá-la de âmbar porque a chave diz "invalidated" é alarme falso. */
const VALOR_ATENCAO = /^(invalidated|stale|offline|failed|degraded|missing|unknown)$/i;
const VALOR_BOM = /^(online|ok|healthy|valid|active|complete)$/i;

/** Tom de um fato já separado. Booleano só é notável quando a chave diz o que ele mede. */
function tomDoFato(chave, valor) {
  if (/^exceeds|_exceeded$/i.test(chave)) return valor === "true" ? "atencao" : "sucesso";
  if (VALOR_ATENCAO.test(valor)) return "atencao";
  if (VALOR_BOM.test(valor)) return "sucesso";
  return "quieto";
}

/**
 * Quebra `achados[].summary` em fatos individuais.
 *
 * Cada linha é `chave=valor (origem)`, mas uma linha pode empacotar vários fatos
 * separados por vírgula — `analysis.id=an_9906, status=stale, created_at=2026-07-09` —
 * e pode trazer mais de um parêntese no fim. Sem separar, a tag vira uma frase longa
 * que ninguém lê a quatro metros; sem remover todos os parênteses, sobra `(histórico)`
 * pendurado no valor.
 */
export function fatosDoAchado(resumo) {
  const linhas = String(resumo || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const fatos = [];

  for (const linha of linhas) {
    // Remove todos os parênteses finais, não só o último.
    const semOrigem = linha.replace(/(\s*\([^)]*\))+\s*$/, "").trim();

    for (const pedaco of semOrigem.split(",")) {
      const bruto = pedaco.trim();
      if (!bruto) continue;
      const corte = bruto.indexOf("=");
      if (corte === -1) continue;
      const chave = bruto.slice(0, corte).trim();
      const valor = bruto.slice(corte + 1).trim();
      if (!chave || !valor) continue;
      fatos.push({ chave, valor, tom: tomDoFato(chave, valor) });
    }
  }

  // Notáveis primeiro: é a ordem em que a banca deve ler, e a que sobrevive ao corte.
  return fatos.sort((a, b) => (a.tom === "quieto" ? 1 : 0) - (b.tom === "quieto" ? 1 : 0));
}

function tagFato(fato) {
  // A chave já diz o que o valor significa; repetir "chave=valor" dobra o texto sem
  // acrescentar leitura. `baseline.state invalidated` lê melhor que `baseline.state=invalidated`.
  const nome = fato.chave.split(".").pop();
  return el("span", {
    class: `fato fato-${fato.tom} mono`,
    text: `${nome} ${fato.valor}`,
    title: `${fato.chave}=${fato.valor}`,
  });
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

    const LIMITE_FATOS = 6;
    if (fatos.length) {
      const chaveFatos = `${execucao.id}:${papel}:fatos`;
      const todos = estado.faixasAbertas.has(chaveFatos);
      const visiveis = todos ? fatos : fatos.slice(0, LIMITE_FATOS);
      meio.push(...visiveis.map(tagFato));
      if (fatos.length > LIMITE_FATOS) {
        meio.push(
          el("button", {
            class: "faixa-rotas",
            "aria-expanded": String(todos),
            text: todos ? "menos" : `+${fatos.length - LIMITE_FATOS} ⌄`,
            onclick: () => {
              if (todos) estado.faixasAbertas.delete(chaveFatos);
              else estado.faixasAbertas.add(chaveFatos);
              redesenha();
            },
          })
        );
      }
    }
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
