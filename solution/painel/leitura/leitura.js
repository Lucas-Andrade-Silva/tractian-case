/* Leitura de Vibracao + Agente de Suporte
 *
 * A funcao grafico() e a interacao de hover vieram do artefato de referencia sem
 * redesenho: mesma geometria (760x250, margens 46/84/16/30), mesmos rotulos na margem
 * direita, mesmo crosshair. O que mudou e o entorno — tres seeds em vez de uma, e a
 * secao do agente abaixo das analises do modelo.
 *
 * Fonte dos dados:
 *   dados/ativos.json  — coleta/coletar_ativos.py (API industrial, 3 seeds)
 *   dados/agente.json  — coleta/montar_indice.py  (bundle da bateria, cruzado por asset_id)
 */

import { marcaTractian } from "./marca.js";

const SEEDS = ["complete", "s2", "s3"];
const API_AGENTE = ""; // mesma origem: server.py monta o painel em / e expoe POST /consulta

let DATA = [];
let AGENTE = { por_ativo: {}, cobertura: {}, meta: {} };
let EMPRESAS = {};
// Catálogo das baterias disponíveis, para o painel de configuração alternar entre elas
// sem passar por outro comando no terminal.
let FASES = { fases: [], padrao: "pos-correcao" };

const MAQUINA = {
  motor_induction: "Motor de indução", motor_dc: "Motor CC", pump: "Bomba",
  fan: "Ventilador", compressor: "Compressor", gearbox: "Redutor",
  mill: "Moinho", spindle: "Fuso",
};
const CRIT = { critical: "Crítica", high: "Alta", medium: "Média", low: "Baixa" };
const FALHA = {
  bearing_fault: "Falha de rolamento", imbalance: "Desbalanceamento",
  looseness: "Folga mecânica", misalignment: "Desalinhamento",
  lubrication: "Lubrificação", none: "Sem falha detectada",
};
const SEV = { high: "Alta", medium: "Média", low: "Baixa", none: "Nenhuma" };
const ESTADO = { established: "Estabelecido", learning: "Em aprendizado", invalidated: "Invalidado" };
const MODO_DET = { baseline: "por baseline", symptom: "sintomática" };
const LIMIT = {
  processing_delayed: "processamento atrasado", low_snr: "relação sinal-ruído baixa",
  partial_data: "dados parciais", stale_data: "dados desatualizados",
};
/* As tres decisoes que o Decisor emite. Conferidas contra o bundle: nao ha outras. */
const DECISAO = { agir: "Agir", orientar: "Orientar", escalar: "Escalar" };
const PAPEL = {
  supervisor: "Supervisor", contextualizador: "Contextualizador",
  investigador: "Investigador", decisor: "Decisor", executor: "Executor",
};
/* Papeis das pessoas na planta — nao confundir com os papeis do agente acima. */
const PAPEL_USUARIO = {
  maintenance_manager: "gestor de manutenção", mechanic: "mecânico",
  reliability_analyst: "analista de confiabilidade", coordinator: "coordenador",
  operator: "operador", engineer: "engenheiro", electrician: "eletricista",
  technician: "técnico", planner: "planejador",
};

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------------- dica: o tooltip proprio da pagina ----------------
   O `title` nativo espera ~1 s, some sozinho, ignora o tema e quebra linha onde quer.
   Aqui o conteudo e HTML montado por quem chama, guardado num Map por elemento — nunca
   num atributo, para nao reescapar markup a cada leitura. */
const DICAS = new WeakMap();
let dicaEl = null;

function mostraDica(alvo) {
  const html = DICAS.get(alvo);
  if (!html || !dicaEl) return;
  dicaEl.innerHTML = html;
  dicaEl.setAttribute("aria-hidden", "false");
  dicaEl.classList.add("on");

  // Posiciona acima do alvo; se nao couber, desce. Nunca sai da janela na horizontal.
  const r = alvo.getBoundingClientRect();
  const d = dicaEl.getBoundingClientRect();
  const margem = 8;
  let x = r.left + r.width / 2 - d.width / 2;
  x = Math.max(margem, Math.min(x, innerWidth - d.width - margem));
  let y = r.top - d.height - 9;
  if (y < margem) y = r.bottom + 9;
  dicaEl.style.left = `${Math.round(x)}px`;
  dicaEl.style.top = `${Math.round(y)}px`;
}

function escondeDica() {
  if (!dicaEl) return;
  dicaEl.classList.remove("on");
  dicaEl.setAttribute("aria-hidden", "true");
}

/** Registra o conteudo de uma dica num elemento ja no DOM. */
function ligaDica(el, html) {
  if (!el || !html) return;
  DICAS.set(el, html);
  el.setAttribute("data-dica", "");
  // Botao e link ja recebem foco; forcar tabindex neles so duplicaria a parada de tab.
  if (!el.matches("button, a, input, select, textarea, [tabindex]")) {
    el.setAttribute("tabindex", "0");
  }
}

/* Delegacao: um par de listeners para a pagina toda, em vez de um por elemento.
   Foco tambem abre — quem navega por teclado precisa da mesma informacao. */
function ligarDicas(raiz) {
  raiz.querySelectorAll("[data-dica]").forEach((el) => {
    el.addEventListener("mouseenter", () => mostraDica(el));
    el.addEventListener("focus", () => mostraDica(el));
    el.addEventListener("mouseleave", escondeDica);
    el.addEventListener("blur", escondeDica);
  });
}

/* A resposta ao cliente vem com o Markdown leve que o modelo escreve (**negrito**,
   *italico*, `codigo`). Escapa primeiro, converte depois: o HTML gerado aqui so contem
   as tags que esta funcao produz, nunca as do texto de origem. */
function textoRico(s) {
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`\n]+)`/g, '<code class="mono">$1</code>');
}

/* `solicitante` no bundle e o registro inteiro do usuario, nao uma string. */
function quemPediu(s) {
  if (!s) return "solicitante";
  if (typeof s === "string") return s;
  const papel = PAPEL_USUARIO[s.role] || s.role;
  return papel ? `${s.name} · ${papel}` : s.name || "solicitante";
}
const num = (v, d = 2) => (v === null || v === undefined ? "—" : Number(v).toFixed(d));
const dia = (iso) => { const [, m, d] = iso.split("-"); return `${d}/${m}`; };
const mil = (v) => (v == null ? "—" : v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v));

/* Situacao de leitura na seed de referencia: onde o RMS mais recente esta em relacao
   ao limiar do proprio ativo. Ordena a lista lateral. */
function situacao(a, seed = "complete") {
  const r = a.seeds[seed].rms;
  if (r.mode === "unavailable" || !r.samples.length) return { key: "sem", rotulo: "Sem leitura", cls: "sev-none" };
  const ultimo = r.samples[r.samples.length - 1][1];
  if (r.alarm == null) return { key: "sem-limiar", rotulo: "Sem limiar", cls: "sev-none" };
  if (ultimo >= r.alarm) return { key: "acima", rotulo: "Acima do alarme", cls: "sev-crit" };
  if (ultimo >= r.ref + (r.alarm - r.ref) * 0.6) return { key: "elevado", rotulo: "Elevado", cls: "sev-warn" };
  return { key: "normal", rotulo: "Dentro da faixa", cls: "sev-good" };
}
const ORDEM = { acima: 0, elevado: 1, sem: 2, "sem-limiar": 3, normal: 4 };

function chipModo(mode, notes) {
  const cls = mode === "complete" ? "ok" : mode === "unavailable" || mode === "conflict" ? "bad" : "warn";
  const t = notes ? ` title="${esc(notes)}"` : "";
  return `<span class="chip ${cls}"${t}><span class="dot"></span>${esc(mode || "—")}</span>`;
}

/* ---------------- grafico de serie temporal (do artefato, intacto) ---------------- */
function grafico(r, nome, idx) {
  const S = r.samples;
  const W = 760, H = 250, L = 46, R = 84, T = 16, B = 30;
  const pw = W - L - R, ph = H - T - B;

  const vals = S.map((s) => s[1]);
  const cand = vals.concat([r.ref, r.alarm].filter((v) => v != null));
  let lo = Math.min(...cand), hi = Math.max(...cand);
  const pad = (hi - lo) * 0.18 || 0.4;
  lo = Math.max(0, lo - pad); hi = hi + pad;

  const X = (i) => L + (S.length === 1 ? pw / 2 : (i / (S.length - 1)) * pw);
  const Y = (v) => T + ph - ((v - lo) / (hi - lo)) * ph;

  const bruto = (hi - lo) / 4;
  const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= bruto) || mag * 10;
  const ticks = [];
  for (let v = Math.ceil(lo / passo) * passo; v <= hi + 1e-9; v += passo) ticks.push(+v.toFixed(6));

  const linha = S.map((s, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(s[1]).toFixed(1)}`).join(" ");
  const area = `${linha} L${X(S.length - 1).toFixed(1)},${(T + ph).toFixed(1)} L${X(0).toFixed(1)},${(T + ph).toFixed(1)} Z`;

  let g = "";
  g += ticks.map((v) => `<line class="grid" x1="${L}" y1="${Y(v).toFixed(1)}" x2="${L + pw}" y2="${Y(v).toFixed(1)}"/>`).join("");
  g += ticks.map((v) => `<text x="${L - 8}" y="${(Y(v) + 3.2).toFixed(1)}" text-anchor="end">${num(v, passo < 1 ? 1 : 0)}</text>`).join("");

  if (r.ref != null && r.alarm != null) {
    const y1 = Y(r.alarm), y2 = Y(Math.max(lo, r.ref - (r.alarm - r.ref)));
    g += `<rect x="${L}" y="${y1.toFixed(1)}" width="${pw}" height="${Math.max(0, y2 - y1).toFixed(1)}" fill="var(--band)"/>`;
  }
  if (r.alarm != null && r.alarm < hi) {
    g += `<rect x="${L}" y="${T}" width="${pw}" height="${Math.max(0, Y(r.alarm) - T).toFixed(1)}" fill="var(--alarm-band)"/>`;
  }

  g += `<path d="${area}" fill="var(--band)" opacity=".55"/>`;
  g += `<path d="${linha}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;

  const ref = (v, cor, texto) => {
    if (v == null) return "";
    const y = Y(v);
    return `<line x1="${L}" y1="${y.toFixed(1)}" x2="${L + pw}" y2="${y.toFixed(1)}" stroke="${cor}" stroke-width="2" stroke-dasharray="5 4"/>` +
      `<text class="lbl-on-line" x="${L + pw + 7}" y="${(y - 3).toFixed(1)}" fill="${cor}">${texto}</text>` +
      `<text class="lbl-on-line" x="${L + pw + 7}" y="${(y + 9).toFixed(1)}" fill="${cor}" font-weight="400">${num(v)}</text>`;
  };
  g += ref(r.alarm, "var(--crit)", "ALARME");
  g += ref(r.ref, "var(--s3)", "BASELINE");

  const li = S.length - 1;
  g += `<circle cx="${X(li).toFixed(1)}" cy="${Y(S[li][1]).toFixed(1)}" r="4.5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/>`;
  g += `<line class="base-axis" x1="${L}" y1="${T + ph}" x2="${L + pw}" y2="${T + ph}"/>`;

  const cada = Math.max(1, Math.ceil(S.length / 8));
  const minGap = 34;
  S.forEach((s, i) => {
    if (i % cada && i !== li) return;
    if (i !== li && X(li) - X(i) < minGap) return;
    g += `<text x="${X(i).toFixed(1)}" y="${T + ph + 15}" text-anchor="middle">${dia(s[0])}</text>`;
  });
  g += `<text class="ax-title" x="${L}" y="${T - 4}" text-anchor="start">mm/s</text>`;

  g += `<g class="cross" style="opacity:0"><line class="cx" y1="${T}" y2="${T + ph}" stroke="var(--ink-3)" stroke-width="1" stroke-dasharray="3 3"/><circle class="cd" r="5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/></g>`;
  const passoX = pw / Math.max(1, S.length - 1);
  g += S.map((s, i) => `<rect class="hit" data-i="${i}" x="${(X(i) - passoX / 2).toFixed(1)}" y="${T}" width="${passoX.toFixed(1)}" height="${ph}" fill="transparent"/>`).join("");

  const meta = { X: S.map((_, i) => X(i)), Y: S.map((s) => Y(s[1])), S, alarm: r.alarm, ref: r.ref, W, H };
  return {
    svg: `<svg class="plot" viewBox="0 0 ${W} ${H}" role="img" aria-label="Série de RMS de ${esc(nome)} ao longo de 30 dias">${g}</svg>`,
    meta, idx,
  };
}

/* ---------------- leitura tecnica de uma seed ---------------- */
const METAS = {};

/* Tudo que o card de RMS desenha, num valor comparavel. `point` fica de fora de
   proposito: ele aparece na ficha do ativo, nao neste card. */
function assinaturaRms(r) {
  return JSON.stringify([r.mode, r.notes, r.state, r.ref, r.alarm, r.samples]);
}

/* As seeds agrupadas por leitura identica, na ordem em que aparecem em SEEDS.
 *
 * O eixo do card e a LEITURA, nao a seed. A seed decide a disponibilidade do recurso,
 * nao os valores — que vem do historico do ativo e sao os mesmos sempre. Entao duas
 * seeds em modo `complete` devolvem a mesma serie, e desenhar o mesmo grafico duas
 * vezes so gasta tela sem acrescentar informacao.
 *
 * Onde a leitura difere — parcial, inconclusiva, indisponivel — o grupo se separa
 * sozinho e cada card volta a dizer o que aquela seed entregou. E o que importa
 * preservar: a degradacao continua visivel, so a repeticao e que sai.
 */
function gruposDeSeeds(a) {
  const grupos = [];
  const porAssinatura = new Map();
  for (const seed of SEEDS) {
    const chave = assinaturaRms(a.seeds[seed].rms);
    const existente = porAssinatura.get(chave);
    if (existente) {
      existente.push(seed);
    } else {
      const novo = [seed];
      porAssinatura.set(chave, novo);
      grupos.push(novo);
    }
  }
  return grupos;
}

function cardRms(a, seeds, i) {
  const s = a.seeds[seeds[0]];
  const r = s.rms;
  const juntas = seeds.length > 1;
  const ultimo = r.samples.length ? r.samples[r.samples.length - 1][1] : null;
  let html = `<section class="card"><div class="card-hd">
    <h2>RMS &middot; 30 dias <span class="seed-tag">&middot; ${juntas ? "seeds" : "seed"} ${seeds.map(esc).join(" &middot; ")}</span></h2>
    <div class="chips">${chipModo(r.mode, r.notes)}<span class="chip">baseline ${esc(ESTADO[r.state] || r.state || "—")}</span></div>
  </div>`;

  /* Sem esta linha, um card com tres seeds no titulo pareceria uma seed so tendo virado
     tres — ou pior, duas seeds tendo sumido. */
  if (juntas) {
    html += `<p class="note">Estas ${seeds.length} seeds devolveram exatamente a mesma leitura,
      então são um card só.</p>`;
  }

  if (r.mode === "unavailable" || !r.samples.length) {
    html += `<div class="empty"><b>Sem série para desenhar</b>${esc(r.notes || "A API não devolveu amostras nesta seed.")} Não há o que plotar &mdash; a ausência é o dado, e foi o que o agente encontrou nesta execução.</div>`;
  } else {
    const { svg, meta } = grafico(r, a.name, i);
    METAS[i] = meta;
    html += `<div class="plot-wrap" data-plot="${i}">${svg}<div class="tip"></div></div>`;
    html += `<div class="legend">
      <span><i class="key" style="border-top-color:var(--s1)"></i>RMS medido</span>
      ${r.ref != null ? `<span><i class="key dash" style="border-top-color:var(--s3)"></i>Baseline ${num(r.ref)} mm/s</span>` : ""}
      ${r.alarm != null ? `<span><i class="key dash" style="border-top-color:var(--crit)"></i>Alarme ${num(r.alarm)} mm/s</span>` : ""}
    </div>`;
    if (r.alarm == null) {
      html += `<p class="note">Baseline em <b>${esc(ESTADO[r.state] || r.state)}</b>: sem <code>reference + tolerance</code>, a API não devolve <code>alarm_threshold</code> e o gráfico não desenha linha de alarme. A série sozinha não diz se está alta.</p>`;
    } else if (ultimo >= r.alarm) {
      html += `<p class="note">Última leitura <b>${num(ultimo)} mm/s</b> cruzou o limiar de <b>${num(r.alarm)}</b> &mdash; ${num(((ultimo / r.alarm) - 1) * 100, 0)}% acima.</p>`;
    }
    html += `<details class="data"><summary>Ver as ${r.samples.length} amostras como tabela</summary><div class="scroll">
      <table class="tbl"><thead><tr><th class="l">Data</th><th>RMS (mm/s)</th><th>vs. baseline</th></tr></thead><tbody>
      ${r.samples.slice().reverse().map(([ts, v]) => `<tr><td class="l mono">${esc(ts)}</td><td>${num(v, 3)}</td><td>${r.ref == null ? "—" : (v >= r.ref ? "+" : "") + num(v - r.ref)}</td></tr>`).join("")}
      </tbody></table></div></details>`;
  }
  return html + `</section>`;
}

function cardEspectro(a, seed) {
  const sp = a.seeds[seed].spectrum;
  const picos = (sp.peaks || []).slice().sort((x, y) => y.amplitude_mm_s - x.amplitude_mm_s);
  const maxA = picos.length ? Math.max(...picos.map((p) => p.amplitude_mm_s)) : 1;
  let html = `<section class="card"><div class="card-hd">
    <h2>Espectro &middot; picos <span class="seed-tag">&middot; seed ${esc(seed)}</span></h2>
    <div class="chips">${chipModo(sp.mode, sp.notes)}${a.bpfo ? `<span class="chip">BPFO ${num(a.bpfo, 1)} Hz</span>` : ""}</div>
  </div>`;
  if (!picos.length) {
    html += `<div class="empty"><b>Nenhum pico</b>${esc(sp.notes || "A API não devolveu picos para este ponto nesta seed.")}</div>`;
  } else {
    html += `<div class="spec-rows">${picos.map((p, i) => {
      const alto = a.bpfo && Math.abs(p.freq_hz - a.bpfo) < 1.5;
      return `<div class="srow${i === 0 ? " first" : ""}">
        <div class="fq mono"><b>${num(p.freq_hz, 1)}</b> Hz <span class="note-tag">${esc(p.note || "")}</span></div>
        <div class="bar-track"><div class="bar${alto ? " hi" : ""}" style="width:${Math.max(2, (p.amplitude_mm_s / maxA) * 100).toFixed(1)}%"></div></div>
        <div class="amp mono">${num(p.amplitude_mm_s)}</div>
      </div>`;
    }).join("")}</div>
    <div class="legend"><span>Amplitude em mm/s &middot; barra em laranja marca o pico na frequência de BPFO do rolamento</span></div>`;
  }
  if (sp.missing && sp.missing.length) {
    html += `<p class="note">Bandas ausentes na coleta: <code>${sp.missing.map(esc).join(", ")}</code>. O espectro está incompleto.</p>`;
  }
  return html + `</section>`;
}

function cardQualidade(a, seed) {
  const dq = a.seeds[seed].dq;
  const campos = [
    ["Completude", dq.completeness == null ? "—" : `${num(dq.completeness * 100, 0)}<small>%</small>`],
    ["SNR", dq.snr == null ? "—" : `${num(dq.snr, 1)}<small> dB</small>`],
    ["Frescor", dq.fresh == null ? "—" : `${dq.fresh}<small> min</small>`],
    ["Desatualizado", dq.stale == null ? "—" : dq.stale ? "sim" : "não"],
  ];
  return `<section class="card"><div class="card-hd">
    <h2>Qualidade do dado <span class="seed-tag">&middot; seed ${esc(seed)}</span></h2>
    <div class="chips">${chipModo(dq.mode, dq.notes)}</div></div>
    <dl class="dq">${campos.map(([k, v], i) => `<div${i === 0 ? ' class="first"' : ""}><dt>${k}</dt><dd>${v}</dd></div>`).join("")}</dl>
    ${dq.notes ? `<p class="note">${esc(dq.notes)}</p>` : ""}
  </section>`;
}

function cardAnalises(a, seed) {
  const s = a.seeds[seed];
  const bl = s.baseline;
  if (!s.analyses.length) {
    return `<section class="card"><div class="card-hd">
      <h2>Análises do modelo <span class="seed-tag">&middot; seed ${esc(seed)}</span></h2>
      <div class="chips">${chipModo(s.analyses_mode, null)}</div></div>
      <div class="empty"><b>Nenhuma análise</b>O modelo não publicou análise para este ativo nesta seed.</div></section>`;
  }
  return `<section class="card"><div class="card-hd">
    <h2>Análises do modelo <span class="seed-tag">&middot; seed ${esc(seed)}</span></h2>
    <div class="chips"><span class="chip">detecção ${esc(MODO_DET[bl.detection_mode] || bl.detection_mode || "—")}</span></div></div>
    <div class="analysis">${s.analyses.map((an, i) => {
      const sevCls = an.severity === "high" ? "bad" : an.severity === "medium" ? "warn" : an.severity === "none" ? "ok" : "";
      return `<div class="an${i === 0 ? " first" : ""}">
        <div class="an-hd"><b>${esc(FALHA[an.type] || an.type)}</b>
          <span class="chip ${sevCls}"><span class="dot"></span>severidade ${esc(SEV[an.severity] || an.severity)}</span>
          ${an.conf != null ? `<span class="chip">confiança ${num(an.conf * 100, 0)}%</span>` : ""}</div>
        ${an.evidence.map((e) => `<div class="ev">Evidência: <code>${esc(e.metric)}</code> = <b>${num(e.value)}</b> contra referência ${num(e.reference)}${e.note ? ` &mdash; ${esc(e.note)}` : ""}</div>`).join("")}
        ${an.limitations.length ? `<div class="ev">Limitações: ${an.limitations.map((l) => esc(LIMIT[l] || l)).join(", ")}</div>` : ""}
      </div>`;
    }).join("")}</div></section>`;
}

/* ================= secao do agente ================= */

/* Trajetoria esperada x percorrida, derivada por comparacao de strings de step.
   O gabarito lista os GETs que o cenario exige; a avaliacao ja traz faltantes e extras. */
function trajetoria(cen, ex) {
  const av = ex.avaliacao;
  const faltantes = new Set(av.faltantes);
  const esperados = (cen.expected_path || []).map((p) => p.step);
  const linhas = [];
  esperados.forEach((step, i) => {
    const perdido = faltantes.has(step);
    linhas.push(`<div class="tstep ${perdido ? "miss" : "hit"}${i === 0 ? " first" : ""}">
      <span class="mk">${perdido ? "✕" : "✓"}</span>
      <span class="st">${esc(step)}</span>
      <span class="rt">${perdido ? "não consultou" : "consultou"}</span>
    </div>`);
  });
  /* `GET /users/me` aparece como extra em 51 de 51 execucoes, e nao e desperdicio: o
     grafo o chama uma vez para estabelecer o contexto de autorizacao. O gabarito, que
     descreve a investigacao tecnica, nunca o lista. Rotular os dois casos igual faria a
     tela acusar de gasto o que e pre-requisito de permissao. */
  (av.extras || []).forEach((step) => {
    const autorizacao = step === "GET /users/me";
    linhas.push(`<div class="tstep extra${linhas.length === 0 ? " first" : ""}">
      <span class="mk">${autorizacao ? "·" : "+"}</span>
      <span class="st">${esc(step)}</span>
      <span class="rt">${autorizacao ? "contexto de permissão" : "além do gabarito"}</span>
    </div>`);
  });
  if (!linhas.length) return `<p class="note">Este cenário não tem trajetória documentada no gabarito.</p>`;
  return `<div class="traj">${linhas.join("")}</div>`;
}

function papeis(ex) {
  const pp = ex.consumo.por_papel || {};
  const entradas = Object.entries(pp).filter(([, v]) => v != null);
  if (!entradas.length) return "";
  const max = Math.max(...entradas.map(([, v]) => v));
  const total = entradas.reduce((s, [, v]) => s + v, 0);
  return `<div class="roles">${entradas
    .sort((a, b) => b[1] - a[1])
    .map(([k, v], i) => `<div class="role${i === 0 ? " first" : ""}" data-papel="${esc(ex.id)}|${esc(k)}">
      <span class="role-n">${esc(PAPEL[k] || k)}</span>
      <span class="role-b"><i style="width:${((v / max) * 100).toFixed(1)}%"></i></span>
      <span class="role-t">${mil(v)} &middot; ${num((v / total) * 100, 0)}%</span>
    </div>`).join("")}
    <p class="roles-dica">Passe o mouse sobre um papel para ver o que ele apurou e quais rotas consultou.</p></div>`;
}

/* O que este papel apurou e quanto custou. O achado do Investigador vem como uma
   sequencia de `chave=valor (fonte)`; quebra-los em linhas com o valor destacado torna
   legivel o que era um paragrafo de simbolos. */
function dicaPapel(ex, papel) {
  const tokens = (ex.consumo.por_papel || {})[papel];
  const achado = (ex.achados || []).find((f) => f.agent === papel);
  const chamadas = (ex.chamadas || []).filter((c) => c.papel === papel);
  const rotas = chamadas.map((c) => c.step).filter(Boolean);

  let corpo = "";
  if (achado?.summary) {
    const s = achado.summary;
    // `chave=valor (fonte)` repetido e o formato do Investigador; prosa e dos demais.
    const pares = [...s.matchAll(/([\w.]+)=([^\s(]+)\s*(?:\(([^)]+)\))?/g)];
    corpo = pares.length >= 3
      ? `<div class="dica-f">${pares.slice(0, 9).map((m) =>
          `<span>${esc(m[1].split(".").pop())}: <b>${esc(m[2])}</b>${m[3] ? ` <i>${esc(m[3])}</i>` : ""}</span>`
        ).join("")}${pares.length > 9 ? `<span><i>e mais ${pares.length - 9}</i></span>` : ""}</div>`
      : `<p>${esc(s.length > 320 ? `${s.slice(0, 320)}…` : s)}</p>`;
  }

  return `<span class="dica-t">${esc(PAPEL[papel] || papel)}</span>
    ${corpo || `<p>Este papel não registrou achado próprio nesta execução.</p>`}
    <div class="dica-g" style="margin-top:7px">
      <span class="k">tokens</span><span class="a"></span><span class="s"></span><span class="d">${mil(tokens)}</span>
      <span class="k">consultas de API</span><span class="a"></span><span class="s"></span><span class="d">${chamadas.length}</span>
    </div>
    ${rotas.length ? `<div class="dica-f" style="margin-top:6px">${rotas.slice(0, 5).map((r) =>
      `<span><i>${esc(r)}</i></span>`).join("")}${rotas.length > 5 ? `<span><i>e mais ${rotas.length - 5}</i></span>` : ""}</div>` : ""}`;
}

const DIMENSAO = {
  honestidade: "Honestidade sob incerteza",
  causa_raiz: "Acurácia da causa-raiz",
  justificativa: "Qualidade da justificativa",
};

/* Delta contra a mesma combinacao caso x seed na fase anterior. Sinal invertido de
   proposito: menos token e menos chamada e ganho, entao a economia aparece em verde. */
function delta(agora, antes, sufixo = "") {
  if (antes == null || agora == null) return "";
  const d = agora - antes;
  if (d === 0) return ` <span style="color:var(--ink-3)">=</span>`;
  const pct = antes ? Math.abs((d / antes) * 100) : 0;
  const cor = d < 0 ? "var(--good)" : "var(--crit)";
  // Percentual so quando o movimento e material: "+2 (0%)" e ruido tipografico.
  return ` <span style="color:${cor}">${d < 0 ? "−" : "+"}${pct >= 5 ? `${pct.toFixed(0)}%` : mil(Math.abs(d)) + sufixo}</span>`;
}

/* O que o hover mostra: a mesma execucao antes da correcao. A media agregada esconde
   que o ganho nao foi uniforme — CEN-14 caiu 40%, outros subiram. */
function dicaComparativo(ex) {
  const b = ex.baseline;
  if (!b) {
    return `<span class="dica-t">custo</span>
      <p>Sem execução correspondente na fase <code>baseline</code>: não há o que comparar.</p>`;
  }
  const linha = (k, antes, agora, menorEhMelhor = true) => {
    if (antes == null || agora == null) {
      return `<span class="k">${k}</span><span class="a">—</span><span class="s">→</span><span class="d">${agora ?? "—"}</span>`;
    }
    const d = agora - antes;
    const cls = d === 0 ? "d" : (d < 0) === menorEhMelhor ? "g" : "r";
    return `<span class="k">${k}</span><span class="a">${antes}</span><span class="s">→</span><span class="${cls}">${agora}</span>`;
  };
  return `<span class="dica-t">baseline → pós-correção · mesmo caso, mesma seed</span>
    <div class="dica-g">
      ${linha("tokens", mil(b.tokens), mil(ex.consumo.tokens))}
      ${linha("chamadas de LLM", b.llm_calls, ex.consumo.llm_calls)}
      ${linha("consultas de API", b.chamadas_api, ex.avaliacao.chamadas_api)}
      ${linha("decisão", DECISAO[b.decisao] || b.decisao || "—", DECISAO[ex.decisao] || ex.decisao || "—", false)}
    </div>
    ${b.passou !== ex.avaliacao.passou
      ? `<p>${ex.avaliacao.passou ? "Passou a cumprir" : "Deixou de cumprir"} a trajetória do gabarito nesta seed.</p>`
      : ""}`;
}

/* As quatro categorias de desfecho, com a mesma regra de dominio do painel de origem:
   escalar e desfecho correto e nunca cai em vermelho; decisao certa com trajetoria
   incompleta e atencao, nao erro — o gabarito estruturado costuma ser mais estrito
   que o cenario narrativo. */
function veredito(ex) {
  const av = ex.avaliacao;
  if (!av.executou_sem_erro) {
    // Consumo zerado com decisão vazia é execução que nem chegou a rodar — na prática,
    // cota do provedor esgotada. Chamar isso de "não concluiu" sugere falha do agente.
    const nemComecou = !ex.consumo.tokens && !ex.decisao;
    return nemComecou
      ? { cor: "var(--ink-3)", rotulo: "não executada (cota do provedor)", cls: "warn" }
      : { cor: "var(--warn)", rotulo: "não concluiu a execução", cls: "warn" };
  }
  if (av.passou) {
    return { cor: "var(--good)", rotulo: "passou", cls: "ok" };
  }
  if (av.decision_match) {
    const n = (av.faltantes || []).length;
    return {
      cor: "var(--warn)",
      rotulo: `decisão certa, ${n} ${n === 1 ? "consulta esperada não feita" : "consultas esperadas não feitas"}`,
      cls: "warn",
    };
  }
  return { cor: "var(--crit)", rotulo: "decisão divergente do gabarito", cls: "bad" };
}

/* Notas do comite de juizes desta execucao. Duas ressalvas viajam junto e nao sao
   decorativas: (a) hoje so a fase baseline foi julgada, entao a nota costuma se referir
   a versao ANTERIOR do agente; (b) o comite nao foi calibrado contra anotacao humana,
   entao a nota ordena execucoes entre si, nao mede acerto. Sem isso, um "4,6" ao lado
   de "94,1% de acuracia" se le como se fossem a mesma classe de evidencia. */
function juizes(ex) {
  const j = ex.juizes;
  if (!j || !j.dimensoes) return "";
  const dims = Object.entries(j.dimensoes).filter(([, v]) => v.nota != null);
  if (!dims.length) return "";
  const outraFase = j.fase && j.fase !== (AGENTE.meta?.fase || "pos-correcao");
  return `<div class="juiz">
    <div class="juiz-hd">Comitê de juízes${outraFase ? ` <span class="juiz-fase">fase ${esc(j.fase)}</span>` : ""}</div>
    ${dims.map(([dim, v]) => `<div class="juiz-l" data-juiz="${esc(ex.id)}|${esc(dim)}">
      <span>${esc(DIMENSAO[dim] || dim)}</span>
      <span class="juiz-n">${v.nota}<small>/5</small></span>
    </div>`).join("")}
    <p class="juiz-nota">Juiz não calibrado contra anotação humana: ordena execuções, não mede acerto.${
      outraFase ? " Esta nota é da fase anterior." : ""}</p>
  </div>`;
}

/* Uma coluna por seed: a decisao que o agente tomou com o dado daquela seed. */
function colunasSeeds(cen) {
  const cols = SEEDS.map((seed, i) => {
    const ex = cen.por_seed[seed];
    if (!ex) {
      return `<div class="sd${i === 0 ? " first" : ""}">
        <div class="sd-hd"><span class="sd-seed">${esc(seed)}</span></div>
        <p class="sd-dec" style="color:var(--ink-3)">—</p>
        <p class="sd-meta">sem execução nesta seed</p>
      </div>`;
    }
    const v = veredito(ex);
    /* A trajetoria e contada em passos DO GABARITO cumpridos, nao em total de consultas:
       "7 de 4" lia como erro, quando 7 e o total feito e 4 o que o gabarito previa. */
    const av = ex.avaliacao;
    const previstos = av.gets_esperados ?? 0;
    const cumpridos = Math.max(0, previstos - (av.faltantes || []).length);
    const b = ex.baseline;
    return `<div class="sd${i === 0 ? " first" : ""}">
      <div class="sd-hd"><span class="sd-seed">${esc(seed)}</span>
        <span class="sd-meta custo" data-custo="${esc(ex.id)}">${mil(ex.consumo.tokens)} tok${delta(ex.consumo.tokens, b?.tokens)}
          &middot; ${ex.consumo.llm_calls} chamadas${delta(ex.consumo.llm_calls, b?.llm_calls)}</span></div>
      <p class="sd-dec" style="color:${v.cor}">${esc(DECISAO[ex.decisao] || ex.decisao || "—")}</p>
      <p class="sd-meta">${esc(v.rotulo)}</p>
      <p class="sd-meta">${cumpridos} de ${previstos} passos do gabarito &middot; ${num((ex.duracao_ms || 0) / 1000, 1)}s</p>
      ${ex.justificativa ? `<p class="sd-why">${esc(ex.justificativa.slice(0, 190))}${ex.justificativa.length > 190 ? "…" : ""}</p>` : ""}
      ${juizes(ex)}
    </div>`;
  });
  return `<div class="seeds3">${cols.join("")}</div>`;
}

function barraConcordancia(cen) {
  const decisoes = SEEDS.map((s) => cen.por_seed[s]?.decisao).filter(Boolean);
  const distintas = new Set(decisoes);
  const marcas = SEEDS.map((s) => {
    const ex = cen.por_seed[s];
    if (!ex) return `<i></i>`;
    return `<i class="${veredito(ex).cls}"></i>`;
  }).join("");
  const texto = distintas.size <= 1
    ? `Mesma decisão nas ${decisoes.length} seeds &mdash; o desfecho não dependeu de qual dado a API entregou.`
    : `Decisões divergentes entre seeds: ${[...distintas].map((d) => esc(DECISAO[d] || d)).join(", ")}. A diferença está no dado disponível, não no acaso.`;
  return `<div class="agree"><span class="agree-bar">${marcas}</span><span>${texto}</span></div>`;
}

function secaoAgente(a) {
  const reg = AGENTE.por_ativo[a.id];
  const cenarios = reg ? Object.values(reg.cenarios) : [];

  /* Quando a página exibe uma fase que não é a produção, ela precisa dizer isso alto:
     os números abaixo são de um experimento, e lê-los como resultado corrente seria o
     erro mais caro que esta tela pode induzir. */
  const m = AGENTE.meta || {};
  const experimento = m.fase && m.fase !== "pos-correcao";
  let html = `<div class="divider">A solução &mdash; agente de suporte${
    experimento ? ` <span class="fase-tag">fase ${esc(m.fase)}</span>` : ""}</div>`;
  if (experimento) {
    html += `<p class="fase-aviso">Esta página está exibindo a bateria
      <code>${esc(m.fase)}</code>, não a produção. Os deltas de custo comparam contra
      <code>${esc(AGENTE.fase_anterior || "pos-correcao")}</code>.
      Rode <code>make leitura-dados</code> sem variáveis para voltar ao padrão.</p>`;
  }

  if (!cenarios.length) {
    html += `<section class="card">
      <div class="card-hd"><h2>Cenários da bateria</h2>
      <div class="chips"><span class="chip">sem cobertura</span></div></div>
      <div class="empty"><b>Nenhum cenário cobre este ativo</b>
      A bateria de avaliação tem ${AGENTE.cobertura.casos_total ?? 17} casos escritos à mão sobre
      ${AGENTE.cobertura.ativos_com_cenario ?? 10} dos ${AGENTE.cobertura.ativos_total ?? 26} ativos.
      Este não é um deles &mdash; o que não impede perguntar ao agente sobre ele agora.</div>
    </section>`;
    return html + cardRegistrados() + cardConsulta(a);
  }

  /* Quais recursos deste ativo realmente degradaram entre seeds. Sem isso, tres decisoes
     iguais parecem contaminacao entre execucoes; com isso, ficam sendo o que sao —
     estabilidade sob dado degradado, que e o que a Camada 3 mede. */
  const degradou = ["rms", "spectrum", "dq", "baseline"].filter((rec) => {
    const modos = SEEDS.map((s) => a.seeds[s][rec].mode);
    return new Set(modos).size > 1;
  });
  const NOME_REC = { rms: "RMS", spectrum: "espectro", dq: "qualidade do dado", baseline: "baseline" };
  html += `<section class="card">
    <div class="card-hd"><h2>Como ler as três seeds</h2>
    <div class="chips"><span class="chip ${degradou.length ? "warn" : ""}">${
      degradou.length ? `${degradou.length} de 4 recursos degradam` : "dado idêntico nas 3 seeds"}</span></div></div>
    <p class="cen-q">${degradou.length
      ? `Neste ativo, a API entrega <b>${degradou.map((r) => NOME_REC[r]).join(", ")}</b> em modos
         diferentes conforme a seed &mdash; o agente enfrentou dados distintos em cada execução.
         Quando as três decisões coincidem, é estabilidade sob degradação, não repetição:
         as execuções são independentes (custo e trajetória variam entre elas).`
      : `Neste ativo os quatro recursos vêm no mesmo modo nas três seeds, então as três
         execuções viram o mesmo dado. A repetição aqui mede variação do próprio modelo,
         não robustez a dado faltante.`}</p>
    <p class="note">Os <b>valores</b> de RMS nunca mudam por seed &mdash; vêm do histórico do ativo.
      A seed decide a <b>disponibilidade</b>: completo, parcial, inconclusivo ou indisponível.
      Por isso seeds que caem no mesmo modo devolvem a mesma série &mdash; e a página as junta
      num card só, com as seeds no título, em vez de repetir o gráfico. Onde a leitura
      difere, o card se separa e diz o que aquela seed entregou.</p>
  </section>`;

  for (const cen of cenarios) {
    const ref = cen.por_seed.complete || Object.values(cen.por_seed)[0];
    html += `<section class="card">
      <div class="cen-hd">
        <div>
          <h3>${esc(cen.cenario)} &middot; ${esc(cen.ticket)}</h3>
          ${cen.questao ? `<p class="cen-q">${esc(cen.questao)}</p>` : ""}
        </div>
        <div class="chips">
          <span class="chip">esperado: ${cen.aceitas.map((d) => esc(DECISAO[d] || d)).join(" ou ") || "—"}</span>
          ${cen.ambiguo ? `<span class="chip warn"><span class="dot"></span>ambíguo</span>` : ""}
        </div>
      </div>
      ${ref?.mensagem ? `<blockquote class="msg">${esc(ref.mensagem)}<cite>${esc(quemPediu(ref.solicitante))}</cite></blockquote>` : ""}
      ${colunasSeeds(cen)}
      ${barraConcordancia(cen)}
    </section>`;

    if (ref) {
      html += `<section class="card">
        <div class="card-hd"><h2>Trajetória &middot; ${esc(cen.cenario)}</h2>
        <div class="chips"><span class="chip">seed complete</span>
        <span class="chip">${ref.avaliacao.gets_feitos ?? "—"} consultas feitas</span>
        <span class="chip ${veredito(ref).cls}"><span class="dot"></span>${esc(veredito(ref).rotulo)}</span></div></div>
        ${trajetoria(cen, ref)}
        ${papeis(ref)}
        ${ref.resposta ? `<div class="answer">${textoRico(ref.resposta)}</div>` : ""}
      </section>`;
    }
  }
  return html + cardConsulta(a);
}

/* ---------------- consulta ao vivo, no proprio ativo ---------------- */
function sugestoes(a) {
  const s = a.seeds.complete;
  const r = s.rms;
  const out = [];
  const ultimo = r.samples.length ? r.samples[r.samples.length - 1][1] : null;
  if (ultimo != null && r.alarm != null && ultimo >= r.alarm) {
    out.push(`O ${a.name} está com RMS ${num(ultimo)} mm/s, acima do alarme de ${num(r.alarm)}. O que faço?`);
  }
  if (r.state === "invalidated") {
    out.push(`O baseline do ${a.name} está invalidado. Posso confiar na análise atual?`);
  }
  if (r.state === "learning") {
    out.push(`O ${a.name} está sem limiar de alarme. Como avalio se a vibração está alta?`);
  }
  if (s.dq.stale) {
    out.push(`Os dados do ${a.name} estão desatualizados. Isso invalida o diagnóstico?`);
  }
  if (s.analyses.some((x) => x.type && x.type !== "none")) {
    const f = s.analyses.find((x) => x.type && x.type !== "none");
    out.push(`O modelo acusou ${(FALHA[f.type] || f.type).toLowerCase()} no ${a.name}. Qual o procedimento?`);
  }
  if (!out.length) {
    out.push(`Qual é o estado atual do ${a.name}?`);
    out.push(`O ${a.name} precisa de manutenção preventiva?`);
  }
  return out.slice(0, 3);
}

/* Veredito do comite sobre a consulta livre, quando pedido. A nota e sintetica: o
   gabarito contra o qual ela e medida foi escrito por um LLM a partir da propria
   mensagem, nao por um humano antes da execucao. */
function vereditoAoVivo(r) {
  const av = r.avaliacao || {};
  if (av.juizes === undefined && !r.erro_juiz) return "";
  if (r.erro_gabarito || r.erro_juiz) {
    return `<p class="note">O comitê não pôde julgar esta resposta:
      <code>${esc(r.erro_juiz || r.erro_gabarito)}</code>. A execução do agente acima não é afetada.</p>`;
  }
  const dims = Object.entries(av.juizes || {}).filter(([, v]) => v && v.score != null);
  if (!dims.length) return "";
  const media = dims.reduce((s, [, v]) => s + v.score, 0) / dims.length;
  return `<div class="juiz" style="margin-top:12px">
    <div class="juiz-hd">Comitê de juízes <span class="juiz-fase">sintético</span></div>
    ${dims.map(([dim, v]) => `<div class="juiz-l" data-dica-html="1" data-vivo="${esc(dim)}">
      <span>${esc(DIMENSAO[dim] || dim)}</span>
      <span class="juiz-n">${v.score}<small>/5</small></span>
    </div>`).join("")}
    <p class="juiz-nota">Média ${num(media, 1)}/5 contra um gabarito que um LLM escreveu a
      partir desta mensagem &mdash; não contra gabarito humano. Nunca entra nas métricas dos
      ${AGENTE.cobertura?.casos_total ?? 17} casos (ADR 0007).</p>
  </div>`;
}

function cardConsulta(a) {
  return `<section class="card" id="consulta">
    <div class="card-hd"><h2>Perguntar ao agente sobre este ativo</h2>
    <div class="chips"><span class="chip">execução ao vivo</span></div></div>
    <p class="cen-q">O mesmo grafo dos cenários da bateria, sobre a API real.
      Medido nas execuções já registradas: <b>mediana de ~75 s</b>, e uma em cada dez passa de 3 minutos.</p>
    <div class="ask">
      <input id="q" type="text" placeholder="O que você observou neste ativo?" aria-label="Pergunta sobre ${esc(a.name)}">
      <select id="quem" aria-label="Quem está perguntando"></select>
      <button class="btn" id="go">Perguntar</button>
    </div>
    <label class="ask-juiz"><input type="checkbox" id="julgar">
      <span>Julgar a resposta com o comitê <b>·</b> soma ~30 s e três chamadas de LLM</span></label>
    <div class="hints">${sugestoes(a).map((s) => `<button class="hint" type="button">${esc(s)}</button>`).join("")}</div>
    <div id="saida"></div>
    <p class="synth">A resposta desta consulta é avaliada como <b>sintética</b> (ADR 0007) e nunca entra nas métricas dos ${AGENTE.cobertura.casos_total ?? 17} casos da bateria &mdash; um caso tem gabarito escrito à mão, uma pergunta livre não.</p>
  </section>`;
}

/* ---------------- cenarios registrados e veredito humano ---------------- */
/* Um cenario registrado e uma consulta livre que alguem nomeou para os outros verem.
 * Continua sendo metrica sintetica (ADR 0007) e continua gravada em
 * `evaluation/results/consultas/` — registrar muda a visibilidade, nao a classe de
 * evidencia. O degrau seguinte, virar caso de referencia, exige um humano escrevendo
 * `expected_path` a mao, e isso nao acontece por um clique.
 *
 * O veredito humano fica atras de uma chave em ⚙ Configuracao. Ele e a unica nota
 * deste sistema que nao vem de LLM, e por isso a unica que poderia calibrar o comite —
 * mas so faz sentido para quem esta usando a pagina para avaliar, nao para quem so
 * quer a leitura do ativo. Ligado por escolha, nao por padrao.
 */
const RETORNO_ON = () => guarda.ler("retorno") === "on";

/* A ultima consulta executada nesta tela: `{a, r}`. Existe para que ligar/desligar o
   veredito na configuracao possa reconstruir so o rodape, sem redesenhar o painel — o
   redesenho apagaria um resultado que levou ~75 s para chegar. */
let ULTIMA = null;

/* Cache do que o servidor devolveu por ativo. Evita refazer o GET a cada redesenho,
   e mantem a lista quando so o tema mudou. Invalidado ao registrar ou desregistrar. */
const REGISTRADOS = {};

function cardRegistrados() {
  /* Nasce escondido: sem agente no ar, ou sem nenhum cenario registrado, um card
     vazio anunciando uma funcionalidade que nao esta ali e pior que card nenhum. */
  return `<section class="card" id="registrados" hidden></section>`;
}

function desenhaRegistrados(a, lista) {
  const alvo = document.getElementById("registrados");
  if (!alvo) return;
  if (!lista || !lista.length) {
    alvo.hidden = true;
    alvo.innerHTML = "";
    return;
  }
  alvo.hidden = false;
  alvo.innerHTML = `
    <div class="card-hd"><h2>Cenários registrados neste ativo</h2>
      <div class="chips"><span class="chip">${lista.length} ${lista.length === 1 ? "registrado" : "registrados"}</span>
        <span class="chip warn"><span class="dot"></span>sintético</span></div></div>
    <p class="cen-q">Consultas livres que alguém nomeou para ficarem visíveis aqui. Não têm
      <code>expected_path</code> escrito à mão, então <b>não entram</b> nas métricas dos
      ${AGENTE.cobertura?.casos_total ?? 17} casos da bateria (ADR 0007).</p>
    ${lista.map((c) => cartaoRegistrado(c)).join("")}`;

  alvo.querySelectorAll("[data-desreg]").forEach((el) => {
    el.addEventListener("click", () => desregistrar(a, el.dataset.desreg));
  });
  ligarDicas(alvo);
}

function cartaoRegistrado(c) {
  const vh = c.veredito_humano;
  const notas = c.notas_juiz ? Object.entries(c.notas_juiz) : [];
  const media = notas.length ? notas.reduce((s, [, n]) => s + n, 0) / notas.length : null;
  return `<div class="cen-reg">
    <div class="cen-reg-hd">
      <div>
        <h3>${esc(c.cenario?.nome || "sem nome")}</h3>
        <div class="id mono">${esc(c.id)}${c.criado_em ? ` &middot; ${esc(String(c.criado_em).slice(0, 16).replace("T", " "))}` : ""}</div>
      </div>
      <div class="chips">
        <span class="chip">${esc(DECISAO[c.decisao] || c.decisao || "sem decisão")}</span>
        ${media != null ? `<span class="chip">juiz ${num(media, 1)}/5</span>` : ""}
        ${vh ? `<span class="chip ${vh.decisao_correta ? "ok" : "bad"}"><span class="dot"></span>humano: ${vh.decisao_correta ? "correta" : "incorreta"}</span>` : ""}
        <button class="hint" type="button" data-desreg="${esc(c.id)}">remover da lista</button>
      </div>
    </div>
    ${c.mensagem ? `<blockquote class="msg">${esc(c.mensagem)}</blockquote>` : ""}
    ${c.justificativa ? `<p class="sd-why">${esc(c.justificativa)}</p>` : ""}
    <div class="sd-meta">${mil(c.tokens)} tok &middot; ${c.chamadas ?? "—"} chamadas de API${c.seed ? ` &middot; seed ${esc(c.seed)}` : ""}</div>
    ${vh?.comentario ? `<p class="note">Veredito humano: &ldquo;${esc(vh.comentario)}&rdquo;</p>` : ""}
  </div>`;
}

async function carregaRegistrados(a) {
  const alvo = document.getElementById("registrados");
  if (!alvo) return;
  if (REGISTRADOS[a.id]) return desenhaRegistrados(a, REGISTRADOS[a.id]);
  try {
    const r = await fetch(
      `${API_AGENTE}/consultas?asset_id=${encodeURIComponent(a.id)}&registradas=true&resumido=true`
    );
    if (!r.ok) throw new Error(String(r.status));
    const dados = await r.json();
    REGISTRADOS[a.id] = dados.consultas || [];
  } catch {
    /* Sem o agente no ar a pagina continua servindo a leitura do ativo, que e o que
       ela faz sem servidor nenhum. Cenario registrado e recurso do modo `make consulta`. */
    REGISTRADOS[a.id] = [];
  }
  /* O usuario pode ter trocado de ativo enquanto o GET ia e voltava. */
  if (atual === a.id) desenhaRegistrados(a, REGISTRADOS[a.id]);
}

async function desregistrar(a, id) {
  try {
    const r = await fetch(`${API_AGENTE}/consultas/${encodeURIComponent(id)}/cenario`, {
      method: "DELETE",
    });
    if (!r.ok) throw new Error(String(r.status));
    delete REGISTRADOS[a.id];
    carregaRegistrados(a);
  } catch (e) {
    console.error("não foi possível remover o registro", e);
  }
}

/* Rodape do resultado de uma consulta: registrar como cenario e, se ligado, o veredito
   humano. Vem depois da resposta de proposito — julgar antes de ler nao e julgar. */
function rodapeConsulta(r) {
  const podeRegistrar = !!r.id;
  if (!podeRegistrar) return "";
  return `<div class="reg">
    <div class="ask">
      <input id="cen-nome" type="text" maxlength="80" placeholder="Nome do cenário, se valer a pena guardar" aria-label="Nome do cenário">
      <button class="btn ghost" id="cen-go">Registrar como cenário</button>
    </div>
    <p class="note">Fica visível na lista deste ativo, para quem abrir a página. Continua
      <b>sintético</b>: não entra nas métricas dos ${AGENTE.cobertura?.casos_total ?? 17} casos.</p>
    ${RETORNO_ON() ? blocoVeredito() : ""}
    <div id="reg-msg"></div>
  </div>`;
}

function blocoVeredito() {
  return `<div class="vh">
    <div class="vh-hd">A decisão do agente está correta?</div>
    <div class="ask">
      <button class="btn ghost" data-vh="1">Sim</button>
      <button class="btn ghost" data-vh="0">Não</button>
      <input id="vh-txt" type="text" maxlength="600" placeholder="Por quê? (opcional)" aria-label="Justificativa do veredito">
    </div>
    <p class="note">É a única nota deste sistema que não vem de um LLM &mdash; e por isso a
      única que poderia calibrar o comitê, que hoje ordena execuções sem estar aferido
      contra anotação humana. <b>Não volta para o agente</b>: uma nota que realimenta o
      sistema que ela mede deixa de medi-lo.</p>
  </div>`;
}

/* Reconstroi o rodape da consulta aberta quando a chave do veredito muda. Trocar o
   `outerHTML` descarta os listeners junto com os nos antigos, e `ligarRodapeConsulta`
   religa os novos — sem isso, cada troca empilharia um listener a mais no botao. */
function aplicaRetorno() {
  const reg = document.querySelector("#saida .reg");
  if (!reg || !ULTIMA) return;
  const digitado = document.getElementById("cen-nome")?.value || "";
  reg.outerHTML = rodapeConsulta(ULTIMA.r);
  const campo = document.getElementById("cen-nome");
  if (campo) campo.value = digitado;
  ligarRodapeConsulta(ULTIMA.a, ULTIMA.r);
}

/* Liga os controles do rodape. Recebe o ativo para poder recarregar a lista de
   registrados do proprio ativo depois de um registro bem-sucedido. */
function ligarRodapeConsulta(a, r) {
  const msg = document.getElementById("reg-msg");
  const aviso = (texto, erro) => {
    if (msg) msg.innerHTML = `<p class="note"${erro ? ' style="color:var(--crit)"' : ""}>${esc(texto)}</p>`;
  };

  const go = document.getElementById("cen-go");
  if (go) {
    go.addEventListener("click", async () => {
      const nome = document.getElementById("cen-nome").value.trim();
      if (!nome) return aviso("Dê um nome ao cenário antes de registrar.", true);
      go.disabled = true;
      try {
        const resp = await fetch(`${API_AGENTE}/consultas/${encodeURIComponent(r.id)}/cenario`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome }),
        });
        if (!resp.ok) throw new Error(`${resp.status}: ${(await resp.text()).slice(0, 140)}`);
        aviso(`Registrado como “${nome}”. Aparece na lista deste ativo.`);
        delete REGISTRADOS[a.id];
        carregaRegistrados(a);
      } catch (e) {
        aviso(`Não foi possível registrar. ${e.message || e}`, true);
      } finally {
        go.disabled = false;
      }
    });
  }

  document.querySelectorAll("[data-vh]").forEach((b) => {
    b.addEventListener("click", async () => {
      const correta = b.dataset.vh === "1";
      const comentario = document.getElementById("vh-txt")?.value.trim() || null;
      try {
        const resp = await fetch(`${API_AGENTE}/consultas/${encodeURIComponent(r.id)}/veredito`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decisao_correta: correta, comentario }),
        });
        if (!resp.ok) throw new Error(`${resp.status}`);
        document.querySelectorAll("[data-vh]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        aviso(`Veredito gravado: decisão ${correta ? "correta" : "incorreta"}.`);
        delete REGISTRADOS[a.id];
        carregaRegistrados(a);
      } catch (e) {
        aviso(`Não foi possível gravar o veredito. ${e.message || e}`, true);
      }
    });
  });
}

/* ---------------- painel completo do ativo ---------------- */
function painel(a) {
  const sit = situacao(a);
  const specs = [
    ["Empresa", EMPRESAS[a.company] || a.company],
    ["Máquina", MAQUINA[a.mtype] || a.mtype],
    ["Rotação", a.rpm == null ? "—" : `${a.rpm} rpm`],
    ["Criticidade", CRIT[a.crit] || a.crit],
    ["Ponto", a.seeds.complete.rms.point || "—"],
  ];

  let html = `<section class="card"><div class="ident">
    <div><h3>${esc(a.name)}</h3><div class="id mono">${esc(a.id)} &middot; ${esc(a.plant)} / ${esc(a.line)}</div></div>
    <div class="chips">
      <span class="chip ${sit.cls === "sev-crit" ? "bad" : sit.cls === "sev-warn" ? "warn" : sit.cls === "sev-good" ? "ok" : ""}"><span class="dot"></span>${sit.rotulo}</span>
      <span class="chip">sensor ${esc(a.sensor)}</span>
    </div></div>
    <dl class="specs">${specs.map(([k, v], i) => `<div class="spec${i === specs.length - 1 ? " last" : ""}"><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
  </section>`;

  /* Um card por leitura distinta, nao por seed: tres seeds que devolveram a mesma coisa
     viram um grafico com as tres no titulo. Ver `gruposDeSeeds`. */
  gruposDeSeeds(a).forEach((grupo, i) => { html += cardRms(a, grupo, i); });

  /* espectro, qualidade e analises da seed de referencia; as demais ficam recolhidas */
  html += cardEspectro(a, "complete");
  html += cardQualidade(a, "complete");
  html += cardAnalises(a, "complete");

  html += secaoAgente(a);
  return html;
}

/* ---------------- interacao ---------------- */
let atual = null;

function ligarHover(root) {
  root.querySelectorAll(".plot-wrap").forEach((wrap) => {
    const meta = METAS[wrap.dataset.plot];
    if (!meta) return;
    const svg = wrap.querySelector("svg"), tip = wrap.querySelector(".tip");
    const cross = svg.querySelector(".cross"), cx = svg.querySelector(".cx"), cd = svg.querySelector(".cd");

    const mostrar = (i) => {
      const [ts, v] = meta.S[i];
      cx.setAttribute("x1", meta.X[i]); cx.setAttribute("x2", meta.X[i]);
      cd.setAttribute("cx", meta.X[i]); cd.setAttribute("cy", meta.Y[i]);
      cross.style.opacity = "1";
      let estado = "", cor = "var(--ink-3)";
      if (meta.alarm != null) {
        if (v >= meta.alarm) { estado = "acima do alarme"; cor = "var(--crit)"; }
        else if (meta.ref != null && v >= meta.ref) { estado = `+${num(v - meta.ref)} do baseline`; cor = "var(--accent)"; }
        else if (meta.ref != null) { estado = `${num(v - meta.ref)} do baseline`; cor = "var(--good)"; }
      }
      tip.innerHTML = `<i>${esc(ts)}</i><b>${num(v, 3)} mm/s</b>${estado ? `<span class="st" style="color:${cor}">${estado}</span>` : ""}`;
      tip.classList.add("on");
      const rect = svg.getBoundingClientRect(), k = rect.width / meta.W;
      const px = meta.X[i] * k, py = meta.Y[i] * k;
      const tw = tip.offsetWidth;
      tip.style.left = Math.max(0, Math.min(rect.width - tw, px - tw / 2)) + "px";
      tip.style.top = Math.max(0, py - tip.offsetHeight - 12) + "px";
    };
    const esconder = () => { cross.style.opacity = "0"; tip.classList.remove("on"); };

    svg.querySelectorAll(".hit").forEach((h) => {
      const i = +h.dataset.i;
      h.addEventListener("mouseenter", () => mostrar(i));
      h.addEventListener("touchstart", (e) => { e.preventDefault(); mostrar(i); }, { passive: false });
    });
    wrap.addEventListener("mouseleave", esconder);
    /* O artefato abria o tooltip da ultima amostra porque tinha um grafico so. Com tres
       empilhados, tres tooltips abertos de saida viram ruido: aqui eles so aparecem sob
       o cursor. O ponto final ja fica destacado no proprio SVG. */
  });
}

async function consultar(a) {
  const q = document.getElementById("q");
  const quem = document.getElementById("quem");
  const go = document.getElementById("go");
  const saida = document.getElementById("saida");
  const texto = q.value.trim();
  // O servidor exige mensagem com 10 caracteres ou mais; avisar aqui evita um 422 cru.
  if (texto.length < 10) {
    saida.innerHTML = `<div class="empty"><b>Escreva um pouco mais</b>A consulta precisa de pelo menos 10 caracteres &mdash; descreva o que foi observado no ativo.</div>`;
    q.focus();
    return;
  }

  go.disabled = true;
  go.textContent = "Executando…";
  // As sugestoes ja cumpriram o papel de partida; mante-las competiria com a resposta.
  const dicas = document.querySelector("#consulta .hints");
  if (dicas) dicas.hidden = true;
  const t0 = Date.now();
  const papeisOrdem = ["supervisor", "contextualizador", "investigador", "decisor", "executor"];
  saida.innerHTML = `<div class="live">${papeisOrdem
    .map((p, i) => `<span class="pip${i === 0 ? " on" : ""}" data-p="${p}"><span class="dot"></span>${esc(PAPEL[p])}</span>`)
    .join("")}<span class="elapsed" id="el">0,0s</span></div>`;

  const el = document.getElementById("el");
  /* O contador diz quanto ja passou e, depois da mediana medida, admite que esta longo.
     Silencio por tres minutos e indistinguivel de travamento. */
  const timer = setInterval(() => {
    const s = (Date.now() - t0) / 1000;
    el.textContent = s > 180 ? `${s.toFixed(0)}s — acima do usual, ainda executando`
      : s > 90 ? `${s.toFixed(0)}s — mais longa que a mediana`
      : `${s.toFixed(1)}s`;
  }, 100);
  /* Sem streaming do servidor (decisao registrada na spec): os papeis acendem em
     cadencia estimada a partir da mediana medida (~75 s para cinco papeis), e o
     resultado real substitui tudo ao chegar. */
  let etapa = 0;
  const avanco = setInterval(() => {
    etapa += 1;
    const pips = saida.querySelectorAll(".pip");
    if (etapa < pips.length) {
      pips[etapa - 1].classList.remove("on");
      pips[etapa - 1].classList.add("done");
      pips[etapa].classList.add("on");
    }
  }, 15000);

  try {
    const opt = quem.selectedOptions[0];
    /* Teto de 6 minutos: o maximo ja registrado foi 275 s, entao o dobro da mediana nao
       serviria de corte. Sem AbortController, uma execucao travada prende a UI para
       sempre — o usuario nao tem como saber se ainda vale esperar. */
    const corte = new AbortController();
    const estouro = setTimeout(() => corte.abort(), 360000);
    const resp = await fetch(`${API_AGENTE}/consulta`, {
      method: "POST",
      signal: corte.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mensagem: texto,
        asset_id: a.id,
        user_id: quem.value,
        company_id: opt ? opt.dataset.company : a.company,
        julgar: !!document.getElementById("julgar")?.checked,
        contexto_ativo: { nome: a.name, tipo: a.mtype, criticidade: a.crit },
      }),
    });
    clearTimeout(estouro);
    if (!resp.ok) {
      const corpo = await resp.text();
      throw new Error(`servidor respondeu ${resp.status}: ${corpo.slice(0, 180)}`);
    }
    const r = await resp.json();
    clearInterval(timer); clearInterval(avanco);

    const t = r.trace || {};
    const tk = t.token_usage || {};
    const passos = t.steps || [];
    /* Um 403 na trajetoria e o enforcement de permissao funcionando (ADR 0003),
       nao falha: o operador pediu uma acao que o papel dele nao autoriza. */
    const negados = passos.filter((p) => p.status_code === 403);
    /* Uma execucao pode terminar sem decisao (o grafo parou antes do Decisor, por erro
       ou por limite de passos). Mostrar "—" em silencio esconderia isso: o motivo de
       parada e o dado mais util quando nao houve decisao. */
    const semDecisao = !t.decision;
    saida.innerHTML = `
      <div class="seeds3" style="grid-template-columns:1fr">
        <div class="sd first">
          <div class="sd-hd"><span class="sd-seed">ao vivo</span>
            <span class="sd-meta">${mil(tk.total_tokens)} tok &middot; ${passos.length} chamadas de API &middot; ${((Date.now() - t0) / 1000).toFixed(1)}s</span></div>
          <p class="sd-dec"${semDecisao ? ' style="color:var(--ink-3)"' : ""}>${esc(DECISAO[t.decision] || t.decision || "sem decisão")}</p>
          ${t.justification ? `<p class="sd-why">${esc(t.justification)}</p>` : ""}
          ${semDecisao ? `<p class="sd-meta">o grafo encerrou antes do Decisor${t.stop_reason ? ` &middot; ${esc(t.stop_reason)}` : ""}</p>` : ""}
        </div>
      </div>
      ${t.error ? `<p class="note">A execução terminou com erro: <code>${esc(t.error)}</code></p>` : ""}
      ${negados.length ? `<p class="note">${negados.length} ${negados.length === 1 ? "chamada recusada" : "chamadas recusadas"} com <b>403</b>:
        <code>${negados.map((p) => esc(p.step)).join("</code>, <code>")}</code>.
        O papel deste usuário não autoriza a ação &mdash; é o enforcement da API funcionando, não erro do agente.</p>` : ""}
      ${(t.findings || []).length ? `<div class="finds">${t.findings.map((f) => `<div class="find"><b>${esc(PAPEL[f.agent] || f.agent)}</b><p>${esc(f.summary)}</p></div>`).join("")}</div>` : ""}
      ${passos.length ? `<div class="traj">${passos.map((p, i) => `<div class="tstep ${p.status_code === 403 ? "miss" : "hit"}${i === 0 ? " first" : ""}">
        <span class="mk">${p.status_code === 403 ? "✕" : "✓"}</span>
        <span class="st">${esc(p.step)}</span>
        <span class="rt">${esc(String(p.status_code ?? ""))}${p.papel ? ` &middot; ${esc(PAPEL[p.papel] || p.papel)}` : ""}</span>
      </div>`).join("")}</div>` : ""}
      ${t.final_answer ? `<div class="answer">${textoRico(t.final_answer)}</div>` : ""}
      ${vereditoAoVivo(r)}
      ${rodapeConsulta(r)}`;
    // O raciocinio de cada dimensao vira dica, como nos cenarios da bateria.
    saida.querySelectorAll("[data-vivo]").forEach((el) => {
      const v = (r.avaliacao?.juizes || {})[el.dataset.vivo];
      if (!v) return;
      ligaDica(el, `<span class="dica-t">${esc(DIMENSAO[el.dataset.vivo] || el.dataset.vivo)} · nota ${v.score}/5</span>
        <p>${esc(v.reasoning || "O juiz não registrou raciocínio.")}</p>`);
    });
    ligarDicas(saida);
    // Registrar e dar veredito só existem depois que há resultado — e o `r.id` é o
    // que endereça o registro em disco.
    ULTIMA = { a, r };
    ligarRodapeConsulta(a, r);
  } catch (e) {
    clearInterval(timer); clearInterval(avanco);
    const s = ((Date.now() - t0) / 1000).toFixed(0);
    /* Abortar no cliente nao cancela a execucao no servidor: ela termina e fica gravada
       em evaluation/results/consultas/. Dizer isso evita a leitura de que o trabalho
       se perdeu. */
    saida.innerHTML = e.name === "AbortError"
      ? `<div class="empty"><b>A consulta passou de 6 minutos e a página parou de esperar</b>
         A execução continua no servidor e será gravada em
         <code>evaluation/results/consultas/</code> quando terminar &mdash; nada se perdeu.
         Vale conferir a cota do provedor: uma chamada de LLM enfileirada é a causa usual.</div>`
      : `<div class="empty"><b>A consulta não pôde ser executada</b>
         ${esc(String(e.message || e))} <span class="mono">(${s}s)</span>.
         Esta página exige o agente no ar: <code>make consulta</code>, com a API industrial
         já rodando (<code>make up</code>).</div>`;
  } finally {
    go.disabled = false;
    go.textContent = "Perguntar";
    if (dicas) dicas.hidden = false;
  }
}

/* Depois de renderizar, resolve os marcadores `data-custo`/`data-juiz`/`data-papel` em
   conteudo de dica. O HTML fica no Map, nao no atributo: assim nao ha markup escapado
   dentro de markup, e a montagem acontece uma vez so. */
function ligarDicasDoPainel(raiz, ativo) {
  const porId = {};
  const reg = AGENTE.por_ativo[ativo.id];
  for (const caso of Object.values(reg?.cenarios || {})) {
    for (const ex of Object.values(caso.por_seed)) porId[ex.id] = ex;
  }

  raiz.querySelectorAll("[data-custo]").forEach((el) => {
    const ex = porId[el.dataset.custo];
    if (ex) ligaDica(el, dicaComparativo(ex));
  });
  raiz.querySelectorAll("[data-juiz]").forEach((el) => {
    const [id, dim] = el.dataset.juiz.split("|");
    const v = porId[id]?.juizes?.dimensoes?.[dim];
    if (!v) return;
    ligaDica(el, `<span class="dica-t">${esc(DIMENSAO[dim] || dim)} · nota ${v.nota}/5</span>
      <p>${esc(v.porque || "O juiz não registrou raciocínio para esta dimensão.")}</p>`);
  });
  raiz.querySelectorAll("[data-papel]").forEach((el) => {
    const [id, papel] = el.dataset.papel.split("|");
    const ex = porId[id];
    if (ex) ligaDica(el, dicaPapel(ex, papel));
  });
  ligarDicas(raiz);
}

function desenhar() {
  const a = DATA.find((x) => x.id === atual);
  Object.keys(METAS).forEach((k) => delete METAS[k]);
  const panel = document.getElementById("panel");
  panel.innerHTML = painel(a);
  document.querySelectorAll(".item").forEach((el) => el.setAttribute("aria-current", String(el.dataset.id === atual)));
  ligarHover(panel);
  ligarDicasDoPainel(panel, a);
  // Depende do agente no ar; falha em silêncio e deixa o card escondido.
  carregaRegistrados(a);
  // `desenhar` sempre troca o `innerHTML` do painel, então o `#saida` com o resultado
  // da consulta anterior deixou de existir — trocando de ativo ou de fase.
  ULTIMA = null;

  const quem = document.getElementById("quem");
  if (quem) {
    // Quem e da empresa do ativo vem primeiro: e o user_id que determina a permissao
    // real na API, e um usuario de outra empresa nao enxerga este ativo.
    const daCasa = USUARIOS.filter((u) => u.company_id === a.company);
    const resto = USUARIOS.filter((u) => u.company_id !== a.company);
    const opcao = (u) =>
      `<option value="${esc(u.id)}" data-company="${esc(u.company_id)}">${esc(u.name)} &middot; ${esc(PAPEL_USUARIO[u.role] || u.role)}</option>`;
    quem.innerHTML =
      (daCasa.length ? `<optgroup label="Desta empresa">${daCasa.map(opcao).join("")}</optgroup>` : "") +
      (resto.length ? `<optgroup label="De outra empresa (a API deve negar)">${resto.map(opcao).join("")}</optgroup>` : "");
  }
  const go = document.getElementById("go");
  if (go) go.addEventListener("click", () => consultar(a));
  const q = document.getElementById("q");
  if (q) q.addEventListener("keydown", (e) => { if (e.key === "Enter") consultar(a); });
  panel.querySelectorAll(".hint").forEach((h) => {
    h.addEventListener("click", () => {
      document.getElementById("q").value = h.textContent;
      document.getElementById("q").focus();
    });
  });
}

function lista() {
  const ordenado = DATA.slice().sort((x, y) => {
    const d = ORDEM[situacao(x).key] - ORDEM[situacao(y).key];
    return d || x.name.localeCompare(y.name, "pt-BR");
  });
  let html = "", grupo = null, primeiro = true;
  for (const a of ordenado) {
    const s = situacao(a);
    if (s.key !== grupo) {
      grupo = s.key;
      html += `<div class="plant-lbl${primeiro ? " first" : ""}">${s.rotulo}</div>`;
      primeiro = false;
    }
    const r = a.seeds.complete.rms;
    const u = r.samples.length ? r.samples[r.samples.length - 1][1] : null;
    const reg = AGENTE.por_ativo[a.id];
    const nCen = reg ? Object.keys(reg.cenarios).length : 0;
    html += `<button class="item" role="listitem" data-id="${esc(a.id)}" aria-current="false">
      <span class="stripe ${s.cls}"></span>
      <span class="i-name"><b>${esc(a.name)}</b><span class="mono">${esc(a.id.replace("asset_", ""))} &middot; ${esc(MAQUINA[a.mtype] || a.mtype)}${nCen ? `<span class="i-cen">${nCen} cen.</span>` : ""}</span></span>
      <span class="i-val mono">${u == null ? "—" : num(u)}<small>${r.alarm != null ? `de ${num(r.alarm)}` : "sem limiar"}</small></span>
    </button>`;
  }
  const box = document.getElementById("items");
  box.innerHTML = html;
  box.addEventListener("click", (e) => {
    const b = e.target.closest(".item");
    if (!b) return;
    atual = b.dataset.id;
    desenhar();
    document.getElementById("panel").scrollIntoView({ block: "start", behavior: "smooth" });
  });
}

/* ---------------- temas ---------------- */
const guarda = {
  ler(k) { try { return localStorage.getItem(`leitura:${k}`); } catch { return null; } },
  escrever(k, v) { try { localStorage.setItem(`leitura:${k}`, v); } catch { /* sem storage */ } },
};

function aplicaTema() {
  const raiz = document.documentElement;
  if (guarda.ler("brand") === "tractian") raiz.dataset.brand = "tractian";
  const t = guarda.ler("theme");
  if (t === "dark" || t === "light") raiz.dataset.theme = t;
}

/* Metricas das duas fases, lado a lado. Sao os numeros que o experimento produziu —
   nao uma promessa do que `conditional` faria. */
function blocoExperimento() {
  const pos = AGENTE.agregados || {};
  const base = AGENTE.agregados_baseline || {};
  const linha = (k, a, d, dec = 1, menorMelhor = true, suf = "") => {
    if (a == null || d == null) return "";
    const dif = d - a;
    const cls = Math.abs(dif) < 1e-9 ? "exp-d" : (dif < 0) === menorMelhor ? "exp-d exp-g" : "exp-d exp-r";
    return `<div class="exp-l">
      <span class="exp-k">${k}</span><span class="exp-a">${a.toFixed(dec)}${suf}</span>
      <span></span><span class="exp-s">→</span><span class="${cls}">${d.toFixed(dec)}${suf}</span>
    </div>`;
  };
  return `<div class="exp">
    <div class="exp-l first">
      <span class="exp-k" style="color:var(--ink-3);font-size:10px;letter-spacing:.08em;text-transform:uppercase">métrica</span>
      <span class="exp-a">baseline</span><span></span><span class="exp-s"></span>
      <span class="exp-d" style="font-size:11px">pós-correção</span>
    </div>
    ${linha("acurácia de decisão", (base.acuracia_decisao ?? 0) * 100, (pos.acuracia_decisao ?? 0) * 100, 1, false, "%")}
    ${linha("tokens por execução", base.tokens_medio, pos.tokens_medio, 0)}
    ${linha("consultas de API", base.chamadas_media, pos.chamadas_media, 1)}
    ${linha("taxa de repetição", (base.taxa_repeticao_media ?? 0) * 100, (pos.taxa_repeticao_media ?? 0) * 100, 1, true, "%")}
    ${linha("falhas de execução", base.falhas_execucao, pos.falhas_execucao, 0)}
  </div>`;
}

/* Troca a bateria exibida. Cada fase tem seu próprio índice em disco, gerado por
   `montar_indice.py`; aqui é só buscar o arquivo certo e redesenhar. A escolha persiste,
   como tema e paleta — quem abriu o experimento não quer perdê-lo ao recarregar. */
async function trocaFase(nome, aoTerminar) {
  const entrada = FASES.fases.find((f) => f.nome === nome);
  if (!entrada || nome === AGENTE.meta?.fase) return;
  try {
    AGENTE = await fetch(`../dados/${entrada.arquivo}`).then((r) => r.json());
    guarda.escrever("fase", nome);
    atualizaProcedencia();
    lista();
    desenhar();
    aoTerminar?.();
  } catch (e) {
    console.error("não foi possível carregar a fase", nome, e);
  }
}

function corpoConfiguracao() {
  const raiz = document.documentElement;
  const tractian = raiz.dataset.brand === "tractian";
  const escuro = raiz.dataset.theme === "dark"
    || (!raiz.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
  const m = AGENTE.meta || {};
  const jm = AGENTE.juizes_meta || {};
  const retorno = RETORNO_ON();

  return `
    <div class="eng-s">
      <h3>Aparência</h3>
      <div class="eng-lin">
        <button class="sw" id="sw-brand" aria-pressed="${tractian}">Paleta Tractian</button>
        <button class="sw" id="sw-theme" aria-pressed="${escuro}">${escuro ? "Tema claro" : "Tema escuro"}</button>
      </div>
    </div>

    <div class="eng-s">
      <h3>Retorno humano</h3>
      <p>Depois de cada consulta ao vivo, perguntar se a decisão do agente estava certa.
        A resposta fica gravada com a consulta e <b>não volta para o agente</b> &mdash;
        uma nota que realimenta o sistema que ela mede deixa de medi-lo.</p>
      <p>Serve a quem está usando a página para avaliar, não a quem só quer a leitura do
        ativo. Por isso é uma escolha, e vem desligada. É também o único rótulo não-LLM
        deste sistema: sem ele, o comitê de juízes continua ordenando execuções sem estar
        aferido contra ninguém.</p>
      <div class="eng-lin">
        <button class="sw" id="sw-retorno" aria-pressed="${retorno}">${retorno ? "Pedindo veredito" : "Pedir veredito nas consultas"}</button>
      </div>
    </div>

    <div class="eng-s">
      <h3>Política de evidência</h3>
      <p>O que o Investigador apura antes de encerrar. É variável de experimento: as duas
        são defensáveis, e qual rende melhor recall por token é medição, não opinião.</p>
      <div class="pol">${["fixed", "conditional"].map((pol, i) => {
        // A fase que roda esta política. `baseline` e `pos-correcao` rodam as duas
        // `fixed`; o card deve levar à produção, não à versão anterior do agente.
        const candidatas = FASES.fases.filter((f) => f.politica === pol);
        const alvo = candidatas.find((f) => f.nome === FASES.padrao) || candidatas[0];
        // "Ativa" é a fase exibida, não a política: estando em `baseline`, o card
        // `fixed` continua clicável e leva à produção, senão não haveria volta.
        const ativa = alvo && alvo.nome === AGENTE.meta?.fase;
        const desc = pol === "fixed"
          ? `Sempre os quatro: <code>get_asset</code>, <code>get_baseline</code>,
             <code>get_data_quality</code>, <code>get_rms</code> &mdash; inclusive em pergunta
             procedimental. Protege contra investigação incompleta.`
          : `Os quatro só em diagnóstico; em pergunta conceitual ou procedimental, apenas
             <code>baseline</code> e <code>rms</code>. Gasta menos e arrisca faltar evidência
             num caso que parecia procedimental.`;
        const medida = pol === "fixed"
          ? `${AGENTE.meta?.execucoes_da_fase ?? 51} execuções · ${num(AGENTE.agregados?.chamadas_media, 1)} consultas por execução`
          : `EXP-06 · 18 pares · <b style="color:var(--crit)">+13% tokens, +11% chamadas</b>`;
        const rodape = alvo
          ? (ativa
              ? `<div class="pol-x">exibindo esta bateria</div>`
              : `<div class="pol-x pol-ir">ver esta bateria &rarr;</div>`)
          : `<div class="pol-x pol-off">sem bateria registrada</div>`;
        return `<div class="pol-c${i === 0 ? " first" : ""}${alvo && !ativa ? " pol-clic" : ""}"
             aria-current="${ativa}"${alvo && !ativa ? ` data-fase="${esc(alvo.nome)}" role="button" tabindex="0"` : ""}>
          <div class="pol-n">${pol}</div>
          <p class="pol-d">${desc}</p>
          <div class="pol-m">${medida}</div>
          ${rodape}
        </div>`;
      }).join("")}</div>
      <p style="margin-top:9px"><b>Duas medições, sinais opostos de custo</b>. O EXP-02
        (6 pares) viu <code>conditional</code> gastando 8% <i>menos</i>; o EXP-06 (18 pares,
        as três famílias de caso) vê <b>13% mais</b> — e mais chamadas, mais GETs, em todas
        as famílias, inclusive a conceitual, que era onde ela deveria economizar.</p>
      <p>A repetição de chamadas sai de <b>zero</b> em <code>fixed</code> para 3,4%: sem a
        lista fixa dos quatro pilares, o Investigador perde o critério de parada e reconsulta
        para decidir que terminou.</p>
      <p><b>A decisão não muda</b> — 18/18 nos dois braços, zero divergências par a par. É o
        achado que se repete nos dois experimentos: a política afeta custo, não desfecho.
        Detalhes e limitações em <code>solution/docs/experimentos/EXP-06-*.md</code>.</p>
    </div>

    <div class="eng-s">
      <h3>Metodologia</h3>
      <p><b>Três camadas.</b> A camada 1 mede a trajetória contra o <code>expected_path</code>
        escrito à mão; a camada 2 compara a decisão com as <code>decisoes_aceitas</code>;
        a camada 3 mede estabilidade entre as três seeds da mesma execução.</p>
      <p><b>Duas fases.</b> <code>baseline</code> e <code>pos-correcao</code> rodaram os mesmos
        ${AGENTE.agregados?.execucoes ?? 51} pares caso × seed, com a mesma configuração de
        modelos &mdash; o que mudou foram os prompts. A tabela abaixo é sempre essa comparação,
        independente da bateria exibida.</p>
      ${blocoExperimento()}
      <p style="margin-top:10px"><b>Comitê de juízes.</b> ${jm.julgadas ?? 0} de
        ${jm.elegiveis ?? 0} execuções julgadas, todas da fase <code>baseline</code>, por
        <code>${esc(jm.modelo || "—")}</code> no OpenRouter. O juiz roda sempre em provedor
        diferente do gerador do gabarito, para que nenhum modelo julgue a si mesmo.
        Não é calibrado contra anotação humana: ordena execuções, não mede acerto.</p>
      <p><b>Fronteira sintética (ADR 0007).</b> Consultas livres nunca entram nas métricas
        dos ${AGENTE.cobertura?.casos_total ?? 17} casos: um caso tem gabarito escrito à mão,
        uma pergunta livre tem uma questão de referência que um LLM escreveu depois.</p>
    </div>`;
}

/* ---------------- aba de experimentos ----------------
   Os números vêm de dados/experimentos.json, gerado por coleta/montar_experimentos.py a
   partir dos traces em disco. Nada é digitado aqui: um número que só existisse no JS seria
   um número que ninguém pode auditar contra o repositório. */
let EXPERIMENTOS = null;

const VEREDITO = {
  sustentada: ["ok", "sustentada"],
  refutada: ["no", "refutada"],
  parcial: ["pend", "parcial"],
};

function marcaNivel(passou, rotulo) {
  return `<span class="xp-lv ${passou ? "ok" : "no"}">${passou ? "✔" : "✘"} ${rotulo}</span>`;
}

/* Os quatro casos do EXP-07, cada um com o critério que o julgou. Mostrar o veredito sem o
   critério ao lado obrigaria o leitor a acreditar; com ele, dá para discordar. */
function casosExp07(d) {
  return `<div class="xp-c">${d.casos.map((c) => {
    const falhou = !c.nivel2;
    const dec = c.bracos?.decisivo || {};
    return `<div class="xp-cl${falhou ? " fail" : ""}">
      <div class="xp-ch">
        <span class="xp-cn">${esc(c.letra)}</span>
        <span class="xp-ct">${esc(c.titulo)}</span>
        <span class="xp-cb">
          ${marcaNivel(c.nivel1, "leu")}
          ${marcaNivel(c.nivel2, "usou")}
          ${marcaNivel(!c.placebo_mudou, "placebo")}
        </span>
      </div>
      <p class="xp-cm"><b>Mutação:</b> ${esc(c.mutacao)} &middot; <i>${esc(c.pressao)}</i></p>
      <p class="xp-cm" style="color:var(--ink-3)">Decisor, braço mutado:
        &ldquo;${esc((dec.justificativa || "").slice(0, 210))}${(dec.justificativa || "").length > 210 ? "…" : ""}&rdquo;</p>
    </div>`;
  }).join("")}</div>`;
}

function blocoExp07(d) {
  const falhou = d.n2 < d.total;
  return `
    <dl class="xp-sc">
      <div><dt>Investigador leu o campo</dt><dd>${d.n1}<small> / ${d.total}</small></dd></div>
      <div class="${falhou ? "fail" : ""}"><dt>Decisor usou como critério</dt><dd>${d.n2}<small> / ${d.total}</small></dd></div>
      <div><dt>Placebo mudou a conclusão</dt><dd>${d.placebo}<small> / ${d.total}</small></dd></div>
    </dl>
    ${casosExp07(d)}`;
}

function corpoExperimentos() {
  if (!EXPERIMENTOS) {
    return `<div class="eng-s"><p>Os dados dos experimentos não foram gerados.
      Rode <code>make experimentos</code> para montar
      <code>dados/experimentos.json</code> a partir dos traces em disco.</p></div>`;
  }

  const itens = EXPERIMENTOS.experimentos.map((e) => {
    const [cls, rotulo] = VEREDITO[e.veredito] || VEREDITO.parcial;
    const d = e.derivado;
    const derivado = e.fonte === "derivado";
    return `<div class="xp-i">
      <div class="xp-hd">
        <span class="xp-id">${esc(e.id)}</span>
        <h3 class="xp-t">${esc(e.titulo)}</h3>
        <span class="xp-n"><span class="xp-v ${cls}">${rotulo}</span> &middot; n = ${esc(e.n)}</span>
      </div>
      <p class="xp-h">${e.hipotese}</p>
      ${e.id === "EXP-04" && d ? `<p class="xp-r"><b>${d.chamadas_por_execucao}</b>
        chamadas de LLM por execução em ${d.execucoes} execuções, e
        <b>${d.consultas_api}</b> consultas de API pelo Decisor.</p>` : ""}
      <p class="xp-r">${esc(e.resumo)}</p>
      <p class="xp-go"><b>Nesta página:</b> ${esc(e.na_pagina)}</p>
      ${/* O detalhe do EXP-07 vem depois da prosa: o texto anuncia "os quatro casos
            abaixo", e com o bloco antes a referência apontaria para trás. */ ""}
      ${e.id === "EXP-07" && d ? blocoExp07(d) : ""}
      <p class="xp-r" style="font-size:11px; color:var(--ink-3)">
        Documento: <code>solution/docs/experimentos/${esc(e.arquivo)}</code> &middot;
        ${derivado ? "números derivados dos traces em disco" : "veredito transcrito do documento"}
      </p>
    </div>`;
  }).join("");

  return `
    <div class="eng-s">
      <h3>Como ler</h3>
      <p>Cada experimento declara <b>hipótese → método → veredito → limitações</b>. Um
        experimento refutado vale tanto quanto um sustentado: o EXP-02 derrubou a intuição
        de que investigar mais é sempre mais seguro, e está aqui do mesmo jeito.</p>
      <p><b>Só o EXP-07 foi pré-registrado.</b> As previsões foram escritas e commitadas
        antes da coleta, e a análise foi feita contra elas sem reabrir a previsão. Os outros
        quatro foram reconstruídos sobre execuções que já existiam, o que é mais fraco e
        está dito em cada documento.</p>
    </div>
    <div class="eng-s"><div class="xp">${itens}</div></div>
    <div class="eng-s">
      <h3>O que nenhum deles prova</h3>
      <p>Dados sintéticos, 17 casos de material fictício. Um único conjunto de modelos, a
        <code>temperature=0</code>: efeitos que dependam da capacidade do modelo não se
        separam da arquitetura. E as amostras são pequenas — o EXP-01 convive com
        p&nbsp;≈&nbsp;0,125, e o EXP-07 tem quatro casos. São demonstrações de mecanismo,
        não estimativas de taxa.</p>
    </div>`;
}

function ligarExperimentos() {
  const cx = document.getElementById("exp");
  const corpo = document.getElementById("exp-corpo");
  const abrir = document.getElementById("sw-exp");

  let antes = null;
  const abre = () => {
    antes = document.activeElement;
    corpo.innerHTML = corpoExperimentos();
    ligarDicas(corpo);
    cx.setAttribute("open", "");
    document.getElementById("exp-x").focus();
  };
  const fecha = () => {
    cx.removeAttribute("open");
    if (antes) antes.focus();
  };

  ligaDica(abrir, `<span class="dica-t">experimentos</span>
    <p>As cinco hipóteses testadas, com o veredito de cada uma e como reproduzi-la nesta
    página. Os números vêm dos traces em disco, não do texto dos documentos.</p>`);
  abrir.addEventListener("click", abre);
  document.getElementById("exp-x").addEventListener("click", fecha);
  cx.addEventListener("click", (e) => { if (e.target === cx) fecha(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && cx.hasAttribute("open")) fecha();
  });
}

function ligarConfiguracao() {
  const raiz = document.documentElement;
  const cx = document.getElementById("eng");
  const corpo = document.getElementById("eng-corpo");
  const abrir = document.getElementById("sw-eng");

  const sincroniza = () => {
    corpo.innerHTML = corpoConfiguracao();
    corpo.querySelector("#sw-brand").addEventListener("click", () => {
      const on = raiz.dataset.brand === "tractian";
      if (on) delete raiz.dataset.brand; else raiz.dataset.brand = "tractian";
      guarda.escrever("brand", on ? "" : "tractian");
      sincroniza();
    });
    corpo.querySelector("#sw-retorno").addEventListener("click", () => {
      const on = RETORNO_ON();
      guarda.escrever("retorno", on ? "" : "on");
      sincroniza();
      // Só o rodapé: `desenhar()` aqui apagaria o resultado da consulta aberta.
      aplicaRetorno();
    });
    corpo.querySelector("#sw-theme").addEventListener("click", () => {
      const escuro = raiz.dataset.theme === "dark"
        || (!raiz.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
      raiz.dataset.theme = escuro ? "light" : "dark";
      guarda.escrever("theme", escuro ? "light" : "dark");
      sincroniza();
    });
    // Clicar no card de uma política carrega a bateria que a rodou.
    corpo.querySelectorAll("[data-fase]").forEach((el) => {
      const ir = () => trocaFase(el.dataset.fase, sincroniza);
      el.addEventListener("click", ir);
      el.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ir(); }
      });
    });
  };

  let antes = null;
  const abre = () => {
    antes = document.activeElement;
    sincroniza();
    cx.setAttribute("open", "");
    document.getElementById("eng-x").focus();
  };
  const fecha = () => {
    cx.removeAttribute("open");
    if (antes) antes.focus();
  };

  ligaDica(abrir, `<span class="dica-t">configuração</span>
    <p>Tema e paleta, a política de evidência que a bateria usou, e a metodologia das três
    camadas com os números das duas fases.</p>`);
  ligarDicas(abrir.parentElement);
  abrir.addEventListener("click", abre);
  document.getElementById("eng-x").addEventListener("click", fecha);
  // Clique no fundo esmaecido fecha; clique dentro da caixa, não.
  cx.addEventListener("click", (e) => { if (e.target === cx) fecha(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && cx.hasAttribute("open")) fecha();
  });
}

/* ---------------- carga ---------------- */
let USUARIOS = [
  { id: "usr_ana", name: "Ana Mantovani", role: "maintenance_manager", company_id: "comp_forja_br" },
];

/* Cabeçalho e rodapé de procedência. Fora de `carregar` porque trocar de bateria muda o
   que eles dizem — e um cabeçalho que continua anunciando a fase antiga é pior que
   nenhum. `origem` fica guardada: só o `ativos.json` a conhece, e ele não recarrega. */
let ORIGEM_API = "127.0.0.1:8000";

function atualizaProcedencia(origem) {
  if (origem) ORIGEM_API = origem;
  const m = AGENTE.meta || {};
  const cob = AGENTE.cobertura || {};
  // Execuções DESTA fase, não o total do bundle: com três baterias, o total (153) não
  // descreve nada que a tela esteja mostrando.
  const nesta = m.execucoes_da_fase ?? m.execucoes ?? 0;
  const falhas = m.falhas_da_fase ?? 0;

  document.getElementById("src").innerHTML =
    `<b>${DATA.length} ativos</b> &middot; ${Object.keys(EMPRESAS).length} empresas<br>` +
    `${SEEDS.length} seeds &middot; janela de 30 dias<br>` +
    `<b>${cob.ativos_com_cenario ?? 0}</b> com cenário &middot; ${nesta} execuções` +
    (falhas ? ` <span style="color:var(--accent)">(${falhas} não rodaram)</span>` : "");

  document.getElementById("foot").innerHTML =
    `Leitura coletada de <code>${esc(ORIGEM_API)}</code> nas seeds ` +
    `<code>${SEEDS.join("</code>, <code>")}</code>. ` +
    `Resultados do agente: bateria <code>${esc(m.fase || "pos-correcao")}</code>, ` +
    `${nesta} execuções${falhas ? ` (${falhas} interrompidas por cota do provedor)` : ""}` +
    `${m.gerado_em ? `, indexadas em ${esc(String(m.gerado_em).slice(0, 16).replace("T", " "))}` : ""}.<br>` +
    `Cada seed é uma condição de dado diferente: a API decide o modo de resposta por ` +
    `<code>hash(seed | recurso | categoria)</code>, então o mesmo ativo pode vir completo numa ` +
    `seed e indisponível noutra. É essa variação que o agente enfrentou.`;
}

async function carregar() {
  const [ativos, agente, fases, experimentos] = await Promise.all([
    fetch("../dados/ativos.json").then((r) => r.json()),
    fetch("../dados/agente.json").then((r) => r.json()).catch(() => ({ por_ativo: {}, cobertura: {}, meta: {} })),
    fetch("../dados/fases.json").then((r) => r.json()).catch(() => null),
    // Ausente quando `montar_experimentos.py` não rodou: a aba explica como gerar em vez
    // de desaparecer, porque um botão que abre um modal vazio é pior que um aviso.
    fetch("../dados/experimentos.json").then((r) => r.json()).catch(() => null),
  ]);
  EXPERIMENTOS = experimentos;
  DATA = ativos.ativos;
  EMPRESAS = ativos.empresas || {};
  AGENTE = agente;
  if (fases) FASES = fases;

  // Bateria escolhida numa visita anterior. Só vale se ainda existir em disco: um
  // `montar_indice.py` que não gerou aquela fase deixaria a página em branco.
  const salva = guarda.ler("fase");
  const entrada = FASES.fases.find((f) => f.nome === salva);
  if (entrada && salva !== AGENTE.meta?.fase) {
    try {
      AGENTE = await fetch(`../dados/${entrada.arquivo}`).then((r) => r.json());
    } catch { /* fase salva sumiu: segue com o padrão */ }
  }

  try {
    const us = await fetch("../dados/usuarios.json").then((r) => r.json());
    if (Array.isArray(us) && us.length) USUARIOS = us;
  } catch { /* sem lista de usuarios: mantem o padrao */ }

  atualizaProcedencia(ativos.origem);

  document.getElementById("marca").innerHTML = marcaTractian(15);
  dicaEl = document.getElementById("dica");
  ligarConfiguracao();
  ligarExperimentos();
  atual = DATA.slice().sort((x, y) => ORDEM[situacao(x).key] - ORDEM[situacao(y).key])[0].id;
  lista();
  desenhar();
}

// Antes de qualquer fetch: senao a pagina pisca no tema errado enquanto os dados chegam.
aplicaTema();
carregar();
/* O tooltip se posiciona a partir de getBoundingClientRect() no momento do hover, entao
   redimensionar a janela nao exige religar nada — reanexar aqui so empilharia listeners. */
// Rolar com uma dica aberta a deixaria orfa: ela e `position:fixed`, o alvo nao.
addEventListener("scroll", escondeDica, { passive: true });
