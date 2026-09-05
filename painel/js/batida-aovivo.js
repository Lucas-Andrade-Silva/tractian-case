/* Batida ④ — de verdade?
 *
 * Executa o agente ao vivo. A espera é honesta: 15 a 25 segundos ditos em voz alta,
 * com os papéis acendendo conforme avançam. Sem streaming incremental — isso exigiria
 * emitir eventos de `agent/server.py`, e a decisão foi manter o redesenho contido em
 * `painel/`. Quando termina, reusa o desenho da batida ②.
 *
 * O selo de avaliação sintética (ADR 0007) é permanente: é a fronteira que impede a
 * nota da consulta livre de ser lida junto com as métricas dos 17 cenários.
 *
 * ADAPTADOR DE FORMATO — leia antes de tocar em `resultado()`.
 *
 * O `/consulta` devolve um trace num formato diferente de `execucao.operacao` do
 * bundle (verificado contra evaluation/results/consultas/consulta_20260904T131539.json):
 *
 *   bundle (operacao)        trace da consulta ao vivo
 *   ------------------------ --------------------------------------------
 *   timeline (unificada)     steps[] + routing[], listas separadas
 *   achados[].summary        findings[] (pode vir [{}] — objetos vazios)
 *   consumo (+ by_agent)     token_usage (mesma forma, inclusive by_agent)
 *   duracao_ms               started_at / finished_at (ISO)
 *   chamada: metodo,rota,    step: method,path,latency_ms
 *     latencia_ms,do_cache
 *   roteamento: turno,de,    routing: turn,from,to,reason
 *     para,motivo
 *
 * `faixasPorPapel` (faixas.js) só entende o formato do bundle e é compartilhado com
 * a batida ②, que funciona contra dado real — por isso a conversão mora aqui, não lá.
 * Cada `step` já traz `agent`, então o agrupamento por papel não exige inferência de
 * turno: usamos o próprio campo. */

import { ESTADO, el, texto, num, duracao } from "./dados.js";
import { selo, aviso, vazio } from "./componentes.js";
import { faixasPorPapel } from "./faixas.js";
import { rodape } from "./batidas.js";
// `envia` é o nome real da função em consulta.js:97 — agora exportada.
import { CONSULTA, carregaCatalogo, envia, blocoErroExecucao } from "./consulta.js";

const PAPEIS_ESPERADOS = ["supervisor", "investigador", "decisor", "executor"];

/**
 * Converte o `trace` do endpoint `/consulta` para o formato de `execucao.operacao`
 * que `faixasPorPapel` espera. Ver nota de formato no topo do arquivo.
 */
function operacaoDoTrace(trace) {
  const t = trace || {};

  const timeline = [];
  for (const r of t.routing || []) {
    timeline.push({
      tipo: "roteamento",
      turno: r.turn,
      de: r.from,
      para: r.to,
      motivo: r.reason,
      _at: r.at,
    });
  }
  for (const s of t.steps || []) {
    timeline.push({
      tipo: "chamada",
      papel: s.agent,
      metodo: s.method,
      rota: s.path,
      query: s.query,
      status_code: s.status_code,
      ok: s.ok,
      mode: s.mode,
      notes: s.notes,
      erro: s.error,
      latencia_ms: s.latency_ms,
      body: s.body,
      response: s.response,
      do_cache: s.from_cache,
      _at: s.at,
    });
  }
  // Ordem cronológica: routing e steps chegam em listas separadas (cada uma já em
  // ordem interna), mas intercaladas na timeline é o que faixasPorPapel percorre para
  // saber "quem está em cena" a cada chamada. Ambas as formas de evento trazem `at`
  // (ISO), o mesmo relógio — por isso é a chave de ordenação, não o número do turno.
  timeline.sort((a, b) => Date.parse(a._at || 0) - Date.parse(b._at || 0));

  // `findings` pode vir como `[]`, ou como `[{}]` (objetos vazios) — ambos são
  // "nenhum achado", nunca erro. Só entram achados com `agent` e `summary` reais.
  const achados = (t.findings || []).filter(
    (f) => f && f.agent && f.summary
  );

  return {
    timeline,
    achados,
    consumo: t.token_usage || {},
    duracao_ms:
      t.started_at && t.finished_at
        ? Date.parse(t.finished_at) - Date.parse(t.started_at)
        : null,
  };
}

function formulario(redesenha) {
  const { form } = CONSULTA;
  const pronto = form.user_id && form.mensagem.trim().length >= 10 && !CONSULTA.enviando;

  return el("div", { class: "aovivo-form" }, [
    el(
      "select",
      {
        "aria-label": "Quem está perguntando",
        onchange: (ev) => { form.user_id = ev.target.value; redesenha(); },
      },
      [
        el("option", { value: "", text: "quem pergunta…" }),
        ...CONSULTA.usuarios.map((u) =>
          el("option", {
            value: u.user_id,
            text: `${u.name} · ${u.role}`,
            selected: form.user_id === u.user_id,
          })
        ),
      ]
    ),
    el(
      "select",
      {
        "aria-label": "Qual ativo",
        onchange: (ev) => { form.asset_id = ev.target.value; redesenha(); },
      },
      [
        el("option", { value: "", text: "qual ativo…" }),
        ...CONSULTA.ativos.map((a) =>
          el("option", { value: a.asset_id, text: a.name, selected: form.asset_id === a.asset_id })
        ),
      ]
    ),
    el("input", {
      type: "text",
      class: "aovivo-mensagem",
      placeholder: "o que a pessoa observou, com as palavras dela",
      value: form.mensagem,
      oninput: (ev) => { form.mensagem = ev.target.value; },
    }),
    el("button", {
      class: "botao-primario",
      text: CONSULTA.enviando ? "investigando…" : "perguntar",
      disabled: !pronto,
      onclick: () => envia(redesenha),
    }),
  ]);
}

function esperando() {
  const feitos = new Set(CONSULTA.papeisVistos || []);
  return el("div", { class: "aovivo-espera" }, [
    el("div", { class: "girando" }),
    el("div", { class: "espera-titulo", text: "O agente está investigando…" }),
    el("div", {
      class: "espera-nota",
      text: "costuma levar 15 a 25 segundos · mesmo grafo dos 17 cenários",
    }),
    el(
      "div",
      { class: "espera-papeis" },
      PAPEIS_ESPERADOS.map((p) =>
        el("span", {
          class: `fato ${feitos.has(p) ? "fato-sucesso" : "fato-quieto"}`,
          text: feitos.has(p) ? `${p} ✓` : p,
        })
      )
    ),
  ]);
}

function resultado(registro, redesenha) {
  const execucao = {
    id: registro.id,
    operacao: operacaoDoTrace(registro.trace),
  };

  return el("div", {}, [
    faixasPorPapel(execucao, ESTADO, redesenha),
    el("div", { class: "bloco-resposta" }, [
      el("div", { class: "rotulo-cru", text: "resposta entregue" }),
      el("div", { class: "resposta-final", text: texto((registro.trace || {}).final_answer) }),
    ]),
  ]);
}

export function batidaAoVivo(redesenha) {
  if (!CONSULTA.carregouCatalogo) {
    carregaCatalogo(redesenha);
    return el("main", { class: "batida" }, [
      el("div", { class: "batida-corpo" }, [vazio("Carregando catálogo…")]),
      rodape(redesenha),
    ]);
  }

  const partes = [formulario(redesenha)];

  if (CONSULTA.erroCatalogo) {
    partes.push(
      aviso("atencao", [
        el("strong", { text: "O agente não está no ar. " }),
        "Esta batida executa o agente ao vivo. Suba com `make consulta`.",
      ])
    );
  } else if (CONSULTA.enviando) {
    partes.push(esperando());
  } else if (CONSULTA.erroEnvio) {
    partes.push(blocoErroExecucao(CONSULTA.erroEnvio));
  } else if (CONSULTA.resultado) {
    partes.push(resultado(CONSULTA.resultado, redesenha));
  }

  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, partes),
    el("footer", { class: "batida-rodape" }, [
      el("div", { class: "passos" }, [
        el("button", {
          class: "passo",
          text: "← os 17 × 3",
          onclick: () => { ESTADO.batida = "matriz"; redesenha(); },
        }),
      ]),
      el("div", { class: "rodape-direita" }, [
        selo("avaliação sintética — ADR 0007", "atencao", {
          title:
            "A questão de referência é escrita por um LLM, não por humano. As notas ordenam " +
            "consultas livres entre si e nunca entram nas métricas dos 17 cenários.",
        }),
      ]),
    ]),
  ]);
}
