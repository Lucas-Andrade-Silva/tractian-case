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
      html += `<p class="note">Baseline em <b>${esc(ESTADO[r.state] || r.state)}</b>: sem limiar derivado, o gráfico não desenha linha de alarme.</p>`;
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
    html += `<p class="fase-aviso">Bateria <code>${esc(m.fase)}</code>, não a produção. Deltas contra
      <code>${esc(AGENTE.fase_anterior || "pos-correcao")}</code>.</p>`;
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
      ? `A API entrega <b>${degradou.map((r) => NOME_REC[r]).join(", ")}</b> em modos diferentes
         conforme a seed: cada execução viu um dado distinto. Decisões iguais aqui são
         estabilidade, não repetição.`
      : `Os quatro recursos vêm no mesmo modo nas três seeds. A repetição mede variação do
         modelo, não robustez a dado faltante.`}</p>
    <p class="note">A seed muda a <b>disponibilidade</b>, nunca os valores. Seeds no mesmo
      modo dividem um card só.</p>
  </section>`;

  /* Um ativo com quatro cenarios rendia oito cards abertos de uma vez, e a tela virava
     um rolo onde nada se acha. Cada cenario agora nasce fechado atras do proprio
     cabecalho — que continua sendo o mesmo cabecalho de antes, so que clicavel — e
     abrir um fecha o que estava aberto: um cenario por vez, sempre. */
  html += `<div class="cens">`;
  cenarios.forEach((cen, i) => {
    const ref = cen.por_seed.complete || Object.values(cen.por_seed)[0];
    const id = `cen-${a.id}-${i}`;
    html += `<section class="card cen" data-cen="${id}">
      <button class="cen-hd cen-tg" type="button" aria-expanded="false" aria-controls="${id}">
        <div>
          <h3>${esc(cen.cenario)} &middot; ${esc(cen.ticket)}</h3>
          ${cen.questao ? `<p class="cen-q">${esc(cen.questao)}</p>` : ""}
        </div>
        <div class="chips">
          <span class="chip">esperado: ${cen.aceitas.map((d) => esc(DECISAO[d] || d)).join(" ou ") || "—"}</span>
          ${cen.ambiguo ? `<span class="chip warn"><span class="dot"></span>ambíguo</span>` : ""}
          <span class="cen-caret" aria-hidden="true"></span>
        </div>
      </button>
      <div class="cen-body" id="${id}" hidden>
        ${ref?.mensagem ? `<blockquote class="msg">${esc(ref.mensagem)}<cite>${esc(quemPediu(ref.solicitante))}</cite></blockquote>` : ""}
        ${colunasSeeds(cen)}
        ${barraConcordancia(cen)}
        ${ref ? `<div class="cen-traj">
          <div class="card-hd"><h2>Trajetória &middot; ${esc(cen.cenario)}</h2>
          <div class="chips"><span class="chip">seed complete</span>
          <span class="chip">${ref.avaliacao.gets_feitos ?? "—"} consultas feitas</span>
          <span class="chip ${veredito(ref).cls}"><span class="dot"></span>${esc(veredito(ref).rotulo)}</span></div></div>
          ${trajetoria(cen, ref)}
          ${papeis(ref)}
          ${ref.resposta ? `<div class="answer">${textoRico(ref.resposta)}</div>` : ""}
        </div>` : ""}
      </div>
    </section>`;
  });
  html += `</div>`;
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
    <p class="note">Média ${num(media, 1)}/5 contra gabarito de LLM, não humano (ADR 0007).</p>
  </div>`;
}

function cardConsulta(a) {
  return `<section class="card" id="consulta">
    <div class="card-hd"><h2>Perguntar ao agente sobre este ativo</h2>
    <div class="chips"><span class="chip">execução ao vivo</span></div></div>
    <p class="cen-q">O mesmo grafo da bateria, sobre a API real. Mediana de ~75&nbsp;s.</p>
    <div class="ask">
      <input id="q" type="text" placeholder="O que você observou neste ativo?" aria-label="Pergunta sobre ${esc(a.name)}">
      <select id="quem" aria-label="Quem está perguntando"></select>
      <button class="btn" id="go">Perguntar</button>
    </div>
    <label class="ask-juiz"><input type="checkbox" id="julgar">
      <span>Julgar a resposta com o comitê <b>·</b> soma ~30 s e três chamadas de LLM</span></label>
    <div class="hints">${sugestoes(a).map((s) => `<button class="hint" type="button">${esc(s)}</button>`).join("")}</div>
    <div id="saida"></div>
    <p class="synth">Avaliação <b>sintética</b> (ADR 0007): fora das métricas dos ${AGENTE.cobertura.casos_total ?? 17} casos.</p>
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
    <p class="cen-q">Consultas livres marcadas para ficar visíveis. Fora das métricas dos ${AGENTE.cobertura.casos_total ?? 17} casos (ADR 0007).</p>
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
    <p class="note">Única nota que não vem de um LLM. Não volta para o agente.</p>
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
  /* Acordeao dos cenarios: um aberto por vez. Os graficos das seeds sao desenhados
     em SVG que ja esta no DOM mesmo escondido, e o tooltip mede o
     getBoundingClientRect() so no hover — abrir nao exige redesenhar nada. */
  panel.querySelectorAll(".cen-tg").forEach((tg) => {
    tg.addEventListener("click", () => {
      const corpo = document.getElementById(tg.getAttribute("aria-controls"));
      const abrindo = tg.getAttribute("aria-expanded") !== "true";
      panel.querySelectorAll(".cen-tg[aria-expanded=\"true\"]").forEach((o) => {
        o.setAttribute("aria-expanded", "false");
        const c = document.getElementById(o.getAttribute("aria-controls"));
        if (c) c.hidden = true;
      });
      tg.setAttribute("aria-expanded", String(abrindo));
      if (corpo) corpo.hidden = !abrindo;
    });
  });

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
  // Os rótulos das colunas seguem a fase de fato exibida — `AGENTE.fase_anterior` é o
  // nome real de `agregados_baseline` (nem sempre é a bateria "baseline" literal: numa
  // bateria de política, por exemplo, `fase_anterior` é `pos-correcao`). Rótulo fixo
  // aqui já produziu números certos sob nome errado quando a página trocava de fase.
  const nomeAnterior = AGENTE.fase_anterior || "baseline";
  const nomeAtual = (AGENTE.meta || {}).fase || "pos-correcao";
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
      <span class="exp-a">${esc(nomeAnterior)}</span><span></span><span class="exp-s"></span>
      <span class="exp-d" style="font-size:11px">${esc(nomeAtual)}</span>
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
  /* O indice de uma fase tem ~330 KB. Sem esqueleto, a tela fica congelada na fase
     anterior durante a troca: quem clicou ve os numeros velhos e nao sabe se o clique
     pegou. Aqui o painel se esvazia primeiro — o vazio e o sinal de que trocou. */
  esqueleto();
  try {
    AGENTE = await fetch(`../dados/${entrada.arquivo}`).then((r) => r.json());
    guarda.escrever("fase", nome);
    fimDoEsqueleto();
    atualizaProcedencia();
    lista();
    desenhar();
    aoTerminar?.();
  } catch (e) {
    console.error("não foi possível carregar a fase", nome, e);
    /* A fase pedida nao veio, mas `AGENTE` ainda tem a anterior intacta: redesenhar
       devolve a tela que estava no ar, em vez de deixar o esqueleto pulsando. */
    fimDoEsqueleto();
    lista();
    desenhar();
  }
}

/* Seletor do modelo que julga. O catalogo vem do OpenRouter ao vivo (`/juiz/modelos`),
   com fallback para a lista local quando a API nao responde — por isso a carga e
   assincrona e o bloco nasce num estado de espera.

   Um modelo para as tres dimensoes, nao tres seletores: a escolha por dimensao existe no
   backend (`JUDGE_MODEL_<DIMENSAO>`) e serve para fixar um resultado ja testado, nao para
   ser mexida a cada execucao. Tres controles aqui sugeririam que variar por dimensao e
   rotina, quando o uso normal e comparar o mesmo juiz entre execucoes. */
function corpoJuizModelo() {
  if (!JUIZ.carregado) {
    return `<p class="eng-esp">carregando os modelos disponíveis no OpenRouter…</p>`;
  }
  if (!JUIZ.chaveOk) {
    return `<p>Sem <code>JUDGE_API_KEY</code> no <code>.env</code>: o comitê não roda.</p>`;
  }
  if (!JUIZ.modelos.length) {
    return `<p>Nenhum modelo gratuito disponível agora; vale o padrão do <code>.env</code>.</p>`;
  }

  const padrao = (JUIZ.dimensoes[0] || {}).padrao || "";
  const opcoes = JUIZ.modelos.map((m) => `<option value="${esc(m.id)}"${
    m.id === JUIZ.escolhido ? " selected" : ""}>${esc(m.id)}${
    m.descricao ? ` — ${esc(m.descricao)}` : ""}</option>`).join("");

  return `<p>Quem julga a resposta nas três dimensões. Só modelos <code>:free</code> com
      saída estruturada.</p>
    <div class="eng-lin">
      <select class="juiz-sel" id="sel-juiz">
        <option value=""${JUIZ.escolhido ? "" : " selected"}>padrão do .env — ${esc(padrao)}</option>
        ${opcoes}
      </select>
    </div>
    <p class="eng-esp">Modelo menor: mais rápido, julga pior. Trocar entre execuções torna
      as notas incomparáveis.</p>`;
}

/* Busca o catalogo uma vez por sessao. A chamada ao OpenRouter leva alguns segundos e o
   resultado nao muda no meio de uma sessao de uso. */
async function carregaJuizModelos(aoTerminar) {
  if (JUIZ.carregado) return;
  try {
    const r = await fetch(`${API_AGENTE}/juiz/modelos`).then((x) => x.json());
    JUIZ.modelos = r.modelos || [];
    JUIZ.dimensoes = r.dimensoes || [];
    JUIZ.chaveOk = r.chave_configurada !== false;
  } catch {
    /* Sem o agente no ar o seletor nao tem o que oferecer; o estado vazio ja diz isso. */
    JUIZ.modelos = [];
  }
  JUIZ.carregado = true;
  aoTerminar?.();
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
      <h3>Modelo do comitê de juízes</h3>
      ${corpoJuizModelo()}
    </div>

    <div class="eng-s">
      <h3>Retorno humano</h3>
      <p>Pergunta, depois de cada consulta, se a decisão estava certa. A resposta fica
        gravada e <b>não volta para o agente</b>.</p>
      <p>Único rótulo não-LLM do sistema. Vem desligado.</p>
      <div class="eng-lin">
        <button class="sw" id="sw-retorno" aria-pressed="${retorno}">${retorno ? "Pedindo veredito" : "Pedir veredito nas consultas"}</button>
      </div>
    </div>

    <div class="eng-s">
      <h3>Política de evidência</h3>
      <p>O que o Investigador apura antes de encerrar.</p>
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
      <p style="margin-top:9px"><b>Sinais opostos.</b> O EXP-02 (6 pares) viu
        <code>conditional</code> 8% <i>mais barata</i>; o EXP-06 (18 pares) viu <b>13% mais
        cara</b>, em todas as famílias.</p>
      <p>A decisão não muda: 18/18 nos dois braços. A política afeta custo, não desfecho.</p>
    </div>

    <div class="eng-s">
      <h3>Metodologia</h3>
      <p><b>Três camadas.</b> Trajetória contra <code>expected_path</code>; decisão contra
        <code>decisoes_aceitas</code>; estabilidade entre as três seeds.</p>
      <p><b>Fases.</b> Mesmos ${AGENTE.agregados?.execucoes ?? 51} pares caso × seed, mesma
        configuração de modelos; mudaram os prompts. Abaixo,
        <code>${esc((AGENTE.meta || {}).fase || "pos-correcao")}</code> contra
        <code>${esc(AGENTE.fase_anterior || "pos-correcao")}</code>.</p>
      ${blocoExperimento()}
      <p style="margin-top:10px"><b>Comitê.</b> ${jm.julgadas ?? 0} de ${jm.elegiveis ?? 0}
        execuções julgadas por <code>${esc(jm.modelo || "—")}</code>, todas da fase
        <code>baseline</code>. Sem calibração humana.</p>
      <p><b>Fronteira sintética (ADR 0007).</b> Consulta livre não entra nas métricas dos
        ${AGENTE.cobertura?.casos_total ?? 17} casos: gabarito à mão de um lado, LLM do outro.</p>
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

/* Estado dos exploradores: qual amostra cada experimento mostra, e se o bloco de método
   está aberto. Vive fora do DOM porque a aba é redesenhada inteira a cada interação —
   guardar a posição no HTML significaria perdê-la a cada clique. */
const XP_ABERTO = {};   // id do experimento -> índice da amostra em foco
const XP_METODO = {};   // id do experimento -> método/limitações expandidos
const XP_FILTRO = {};   // EXP-04 -> fase selecionada

const corta = (s, n) => {
  const t = String(s || "");
  return esc(t.length > n ? `${t.slice(0, n)}…` : t);
};

/* Um experimento não é um parágrafo com um número no fim: é uma afirmação e as execuções
   que a produziram. Cada explorador desenha o placar recontado do JSON e deixa abrir as
   amostras uma a uma. Nenhum número é escrito aqui — todos vêm de dados/experimentos.json,
   derivado dos traces em disco. */

/* Placar: as caixas de número no topo do explorador. `fail` pinta de vermelho o que
   contraria a hipótese — é como o EXP-06 mostra sozinho que 1 dos 4 casos falhou. */
function placar(itens) {
  return `<dl class="xp-sc">${itens.map((i) => `
    <div class="${i.fail ? "fail" : ""}"><dt>${esc(i.k)}</dt>
      <dd>${esc(i.v)}${i.de ? `<small> / ${esc(i.de)}</small>` : ""}</dd></div>`).join("")}</dl>`;
}

/* Navegação das amostras. O contador diz onde o leitor está em quantos: um "próximo" sem
   denominador esconderia o tamanho da amostra, que aqui é metade do argumento. */
function navegador(id, i, total, rotulo) {
  return `<div class="xp-nav">
    <button class="xp-nb" data-xp-ir="${id}:${i - 1}" ${i <= 0 ? "disabled" : ""}
      aria-label="Amostra anterior">←</button>
    <span class="xp-np">${esc(rotulo)} <b>${i + 1}</b> de ${total}</span>
    <button class="xp-nb" data-xp-ir="${id}:${i + 1}" ${i >= total - 1 ? "disabled" : ""}
      aria-label="Próxima amostra">→</button>
  </div>`;
}

/* Duas execuções lado a lado — o formato dos EXP-01 e EXP-02, que são pareados. Entre eles
   muda só o rótulo das colunas e se o custo importa para a hipótese. */
function parLadoALado(a, b, rot, mostraCusto) {
  const cel = (x, r) => `
    <div class="xp-br">
      <div class="xp-brt">${esc(r)}</div>
      <div class="xp-brd ${x.acertou ? "ok" : "no"}">${esc(x.decisao || "—")}
        <span class="xp-brm">${x.acertou ? "✔ esperada" : "✘ diferente"}</span></div>
      ${mostraCusto ? `<div class="xp-brc">${(x.tokens || 0).toLocaleString("pt-BR")} tokens ·
        ${x.chamadas ?? "—"} chamadas</div>` : ""}
      <p class="xp-brj">${corta(x.justificativa, 300)}</p>
    </div>`;
  return `<div class="xp-par">${cel(a, rot[0])}${cel(b, rot[1])}</div>`;
}

function exploradorPar(e, id, rot, mostraCusto) {
  const d = e.explorador;
  if (!d || !d.linhas?.length) return "";
  const i = Math.min(XP_ABERTO[id] ?? 0, d.linhas.length - 1);
  const ln = d.linhas[i];
  const pct = (x) => `${x > 0 ? "+" : ""}${String(x).replace(".", ",")}%`;
  // Cada experimento pareado tem um placar próprio porque mede coisa diferente: o EXP-01
  // compra decisão, o EXP-02 compra custo, e o EXP-07 é o único que troca uma pela outra —
  // mostrar só um dos dois lados dele contaria metade do resultado.
  const itens = id === "EXP-01"
    ? [{ k: "pares", v: d.total },
       { k: "decisão corrigida", v: d.corrigiu },
       { k: "regressões", v: d.regrediu, fail: d.regrediu > 0 }]
    : id === "EXP-07"
    ? [{ k: "pares", v: d.total },
       { k: "regressões", v: d.regrediu, fail: d.regrediu > 0 },
       { k: "correções", v: d.corrigiu },
       { k: "acerto", v: `${d.acertos_a}/${d.total} → ${d.acertos_b}/${d.total}`,
         fail: d.acertos_b < d.acertos_a },
       { k: "custo em tokens", v: pct(d.delta_tokens) }]
    : [{ k: "pares", v: d.total },
       { k: "decisões divergentes", v: d.divergiu, fail: d.divergiu > 0 },
       { k: "custo em tokens", v: pct(d.delta_tokens) }];
  return `
    ${placar(itens)}
    ${navegador(id, i, d.linhas.length, "par")}
    <div class="xp-am">
      <div class="xp-amh">
        <code class="xp-amc">${esc(ln.caso)}</code>
        <span class="xp-ams">seed ${esc(ln.seed)}</span>
        <span class="xp-ame ${esc(ln.efeito)}">${esc(ln.efeito)}</span>
      </div>
      <p class="xp-amt">&ldquo;${corta(ln.ticket, 200)}&rdquo;</p>
      ${parLadoALado(ln.a, ln.b, rot, mostraCusto)}
    </div>`;
}

/* EXP-03: os encontros com 403. As duas afirmações do experimento — não insistiu, explicou
   — aparecem como contagem medida ao lado da execução que dá para conferir. */
function exploradorExp03(e) {
  const d = e.explorador;
  if (!d || !d.casos?.length) return "";
  const i = Math.min(XP_ABERTO["EXP-03"] ?? 0, d.casos.length - 1);
  const c = d.casos[i];
  return `
    ${placar([
      { k: "recusas 403", v: d.total },
      { k: "sem insistir", v: d.sem_insistir, de: d.total, fail: d.sem_insistir < d.total },
      { k: "explicaram ao usuário", v: d.explicaram, de: d.total, fail: d.explicaram < d.total },
    ])}
    ${navegador("EXP-03", i, d.casos.length, "recusa")}
    <div class="xp-am">
      <div class="xp-amh">
        <code class="xp-amc">${esc(c.caso)}</code>
        <span class="xp-ams">seed ${esc(c.seed)} · ${esc(c.fase)}</span>
      </div>
      <p class="xp-amt">&ldquo;${corta(c.ticket, 170)}&rdquo;</p>
      <div class="xp-403">
        <div class="xp-4l"><span class="xp-4k">quem pediu</span>
          <span>${esc(c.usuario)} · <i>${esc(c.papel)}</i> · ${esc((c.permissoes || []).join(", "))}</span></div>
        <div class="xp-4l"><span class="xp-4k">a API recusou</span>
          <span><code>${esc(c.rota)}</code> <b class="xp-4n">403</b>
            exige <code>${esc(c.exigida)}</code></span></div>
        <div class="xp-4l"><span class="xp-4k">tentou de novo</span>
          <span class="${c.tentou_de_novo ? "xp-4r" : "xp-4g"}">${c.tentou_de_novo === 0
            ? "não — nenhuma repetição da rota recusada"
            : `sim, ${c.tentou_de_novo}×`}</span></div>
      </div>
      <p class="xp-brj"><b>Resposta ao usuário:</b> ${corta(c.resposta, 420)}</p>
    </div>`;
}

/* EXP-04: a hipótese é uma constante, então o explorador é a lista ordenada pelo pior caso.
   Se alguma execução tivesse 2 chamadas, ela seria a primeira linha — a ordenação é o
   teste, não a decoração. */
function exploradorExp04(e) {
  const d = e.explorador;
  if (!d || !d.linhas?.length) return "";
  const fases = ["todas", ...new Set(d.linhas.map((l) => l.fase))];
  const f = XP_FILTRO["EXP-04"] || "todas";
  const linhas = f === "todas" ? d.linhas : d.linhas.filter((l) => l.fase === f);
  const max = linhas.reduce((m, l) => Math.max(m, l.decisor), 0);
  const api = linhas.reduce((s, l) => s + l.api_decisor, 0);
  const mostradas = Math.min(6, linhas.length);
  return `
    ${placar([
      { k: "execuções", v: linhas.length },
      { k: "máx. de chamadas do Decisor", v: max, fail: max !== 1 },
      { k: "consultas de API do Decisor", v: api, fail: api > 0 },
    ])}
    <div class="xp-fil">${fases.map((x) => `<button class="xp-fb${x === f ? " on" : ""}"
      data-xp-f="${esc(x)}">${esc(x)}</button>`).join("")}</div>
    <div class="xp-tb">
      <div class="xp-tr xp-th">
        <span>execução</span><span>Decisor · LLM</span>
        <span>Decisor · API</span><span>LLM na execução</span>
      </div>
      ${linhas.slice(0, 6).map((l) => `<div class="xp-tr">
        <span><code>${esc(l.caso)}</code> <i>${esc(l.seed)}</i></span>
        <span class="${l.decisor === 1 ? "xp-4g" : "xp-4r"}">${l.decisor}</span>
        <span class="${l.api_decisor === 0 ? "xp-4g" : "xp-4r"}">${l.api_decisor}</span>
        <span class="xp-tm">${l.total_llm}</span>
      </div>`).join("")}
    </div>
    <p class="xp-nota">Ordenado pela maior contagem do Decisor: um contraexemplo apareceria
      na primeira linha. Mostrando ${mostradas} de ${linhas.length}.</p>`;
}

/* EXP-06: três braços da mesma execução. O placebo é a coluna que faz o experimento valer —
   sem ela, "mudou junto com a mutação" não se separa de "muda com qualquer coisa". */
function exploradorExp07(e) {
  const d = e.derivado;
  if (!d || !d.casos?.length) return "";
  const i = Math.min(XP_ABERTO["EXP-06"] ?? 0, d.casos.length - 1);
  const c = d.casos[i];
  const braco = (k, rot, nota) => {
    const b = c.bracos?.[k] || {};
    return `<div class="xp-br">
      <div class="xp-brt">${esc(rot)}<span class="xp-brn">${esc(nota)}</span></div>
      <div class="xp-brd">${esc(b.decisao || "—")}</div>
      <p class="xp-brj">${corta(b.justificativa, 260)}</p>
    </div>`;
  };
  return `
    ${placar([
      { k: "Investigador leu o campo", v: d.n1, de: d.total },
      { k: "Decisor usou como critério", v: d.n2, de: d.total, fail: d.n2 < d.total },
      { k: "Placebo mudou a conclusão", v: d.placebo, de: d.total, fail: d.placebo > 0 },
    ])}
    ${navegador("EXP-06", i, d.casos.length, "caso")}
    <div class="xp-am${!c.nivel2 ? " fail" : ""}">
      <div class="xp-amh">
        <span class="xp-cn">${esc(c.letra)}</span>
        <span class="xp-ct">${esc(c.titulo)}</span>
        <span class="xp-cb">${marcaNivel(c.nivel1, "leu")}${marcaNivel(c.nivel2, "usou")}${marcaNivel(!c.placebo_mudou, "placebo")}</span>
      </div>
      <p class="xp-amt">&ldquo;${corta(c.ticket, 170)}&rdquo; <i>— ${esc(c.pressao)}</i></p>
      <p class="xp-cm"><b>O que foi mutado:</b> ${esc(c.mutacao)}</p>
      <div class="xp-par tres">
        ${braco("controle", "controle", "sem mutação")}
        ${braco("decisivo", "mutado", "campo decisivo alterado")}
        ${braco("placebo", "placebo", "campo irrelevante alterado")}
      </div>
    </div>`;
}

function explorador(e) {
  if (e.id === "EXP-01") return exploradorPar(e, "EXP-01", ["baseline", "pós-correção"], false);
  if (e.id === "EXP-02") return exploradorPar(e, "EXP-02", ["fixed · 4 pilares", "conditional · sob demanda"], true);
  if (e.id === "EXP-03") return exploradorExp03(e);
  if (e.id === "EXP-04") return exploradorExp04(e);
  if (e.id === "EXP-06") return exploradorExp07(e);
  // Mesmo explorador pareado do EXP-01, de propósito: as duas medições são a mesma
  // comparação de decisão, e a simetria é o que deixa ver 4 correções de um lado contra
  // 3 regressões do outro. `true` mostra a coluna de custo — aqui ela é metade do achado.
  if (e.id === "EXP-07") return exploradorPar(e, "EXP-07", ["pós-correção", "fixed-atual · prompt enxuto"], true);
  return "";
}

/* A pergunta que o experimento responde, e a resposta em uma linha. Substitui o parágrafo
   de resumo: quem quer o método clica em "como isso foi medido". O texto é editorial e não
   carrega número — os números estão no placar, que vem do JSON. */
const PERGUNTA = {
  "EXP-01": ["Dizer ao Decisor <i>quando orientar não basta</i> melhora a decisão?", "Sim."],
  "EXP-02": ["Apurar sempre os 4 pilares decide melhor que apurar sob demanda?",
             "Não — muda o custo, não o desfecho."],
  "EXP-03": ["Deixar a API recusar com 403 basta para o agente parar e ser honesto?", "Sim."],
  "EXP-04": ["Um Decisor sem tools custa sempre 1 chamada de LLM?", "Sim, em toda a bateria."],
  "EXP-06": ["A decisão vem da evidência apurada ou do que o chamado afirma?",
             "Da evidência — com uma falha em quatro."],
  "EXP-07": ["Cortar o brief do Supervisor economiza sem custar decisão?",
             "Não — economizou 15%, e devolveu 3 decisões ao <i>orientar</i>."],
};

function corpoExperimentos() {
  if (!EXPERIMENTOS) {
    return `<div class="eng-s"><p>Os dados dos experimentos não foram gerados.
      Rode <code>make experimentos</code> para montar
      <code>dados/experimentos.json</code> a partir dos traces em disco.</p></div>`;
  }

  const itens = EXPERIMENTOS.experimentos.map((e) => {
    const [cls, rotulo] = VEREDITO[e.veredito] || VEREDITO.parcial;
    const [pergunta, resposta] = PERGUNTA[e.id] || [e.hipotese, ""];
    const aberto = XP_METODO[e.id];
    return `<div class="xp-i">
      <div class="xp-hd">
        <span class="xp-id">${esc(e.id)}</span>
        <h3 class="xp-t">${esc(e.titulo)}</h3>
        <span class="xp-n"><span class="xp-v ${cls}">${rotulo}</span> &middot; n = ${esc(e.n)}</span>
      </div>
      <p class="xp-q">${pergunta} <b>${esc(resposta)}</b></p>
      ${explorador(e)}
      <button class="xp-mais" data-xp-m="${esc(e.id)}" aria-expanded="${aberto ? "true" : "false"}">
        ${aberto ? "▾" : "▸"} como isso foi medido</button>
      ${aberto ? `<div class="xp-det">
        <p><b>Hipótese registrada.</b> ${e.hipotese}</p>
        <p><b>Resultado.</b> ${esc(e.resumo)}</p>
        <p><b>Nesta página.</b> ${esc(e.na_pagina)}</p>
        <p class="xp-fonte">${esc(e.estado)}<br>
          Documento: <code>solution/docs/${esc(e.arquivo)}</code> ·
          ${e.fonte === "derivado" ? "números derivados dos traces em disco"
            : "veredito do documento; a amostra acima é recontada do bundle"}</p>
      </div>` : ""}
    </div>`;
  }).join("");

  return `
    <div class="eng-s xp-topo">
      <p>Placares recontados dos traces em disco.</p>
    </div>
    <div class="eng-s"><div class="xp">${itens}</div></div>
    <div class="eng-s">
      <h3>O que nenhum deles prova</h3>
      <p>Dados sintéticos, amostras pequenas (o EXP-01 convive com p&nbsp;≈&nbsp;0,125).
        Demonstram mecanismo, não estimam taxa. Só o EXP-06 foi pré-registrado.</p>
    </div>`;
}

/* ================= holdout ao vivo =================
 * Os 8 cenarios reservados para o teste final, resolvidos na frente de quem assiste.
 *
 * A regra que da sentido a aba: o gabarito NAO vem junto da lista. O endpoint
 * `/holdout/cenarios` devolve so o que o agente ve — mensagem e ativo. O
 * `expected_path` e as decisoes aceitas chegam no ultimo evento do streaming, depois de
 * o agente ter escolhido. Servir tudo de uma vez deixaria a resposta certa a um F12 de
 * distancia, e a demonstracao viraria encenacao.
 *
 * O transporte e SSE (`EventSource`): o servidor empurra um evento por passo — cada
 * consulta a API industrial, cada troca de papel, cada achado — e a tela desenha
 * conforme chega. Sem polling do lado do navegador.
 */
const HOLD = { cenarios: [], atual: null, fonte: null, feitos: {}, julgar: guarda.ler("hold-julgar") === "on" };

/* Modelo do comite, escolhido na aba Configuracao. Vazio = o padrao do `.env`
   (`JUDGE_MODEL_<DIMENSAO>` ou `JUDGE_MODEL`), que continua valendo quando a
   interface nao escolhe nada. */
const JUIZ = { modelos: [], dimensoes: [], escolhido: guarda.ler("juiz-modelo") || "", carregado: false, chaveOk: true };

const HOLD_ICONE = { consulta: "→", papel: "◆", achado: "✓", llm: "·", erro: "✕" };

/* Uma linha do log. `classe` colore o fundo por natureza do evento. */
function holdLinha(icone, texto, direita = "", classe = "") {
  return `<div class="hd-l ${classe}"><span class="hd-l-ic">${icone}</span>
    <span class="hd-l-tx">${texto}</span>
    <span class="hd-l-rt">${direita}</span></div>`;
}

function holdEventoHtml(ev) {
  if (ev.tipo === "consulta") {
    const erro = !ev.ok;
    const modo = ev.mode ? `<span class="mode ${esc(ev.mode)}">${esc(ev.mode)}</span>` : "";
    const status = erro ? `<span class="st-err">${ev.status}</span>` : `${ev.status}`;
    const cache = ev.do_cache ? ` <span class="mode">cache</span>` : "";
    return holdLinha(
      HOLD_ICONE.consulta,
      `<code>${esc(ev.step || "")}</code> ${modo}${cache}`,
      `${esc(ev.agente || "")} · ${status}`,
      erro ? "erro" : ""
    );
  }
  if (ev.tipo === "papel") {
    return holdLinha(HOLD_ICONE.papel, `assume o <b>${esc(ev.para || "")}</b>`,
      ev.turno ? `turno ${ev.turno}` : "", "papel");
  }
  if (ev.tipo === "achado") {
    /* O resumo do papel pode ter varias linhas de `campo=valor`. Vira uma linha so:
       o log e cronologia, nao relatorio — o texto inteiro esta no trace. */
    const resumo = String(ev.resumo || "").replace(/\s+/g, " ").trim();
    return holdLinha(HOLD_ICONE.achado,
      `<b>${esc(ev.agente || "")}</b> resumiu: ${esc(resumo.slice(0, 180))}${resumo.length > 180 ? "…" : ""}`,
      "", "achado");
  }
  if (ev.tipo === "llm") {
    return holdLinha(HOLD_ICONE.llm, `<span style="color:var(--ink-3)">${esc(ev.agente || "")} pensou</span>`,
      `${(ev.total || 0).toLocaleString("pt-BR")} tok`);
  }
  if (ev.tipo === "erro") {
    return holdLinha(HOLD_ICONE.erro, esc(ev.mensagem || "falhou"), "", "erro");
  }
  return "";
}

/* As notas do comite (camada 2). Mede o que a comparacao de trajetoria nao ve: se a
   resposta e honesta sobre o que ficou indeterminado, se a causa raiz esta certa, e se a
   justificativa sustenta a decisao. Nota de 1 a 5 por dimensao. */
const HOLD_DIM = {
  honestidade: "Honestidade sob incerteza",
  causa_raiz: "Acerto de causa raiz",
  justificativa: "Qualidade da justificativa",
};

function holdJuizes(vereditos, modelos) {
  const dims = Object.entries(vereditos || {});
  if (!dims.length) return "";

  const notas = dims.map(([chave, v]) => {
    const n = v.score;
    /* Sem nota quando a execucao falhou — o comite nao julga o que nao tem resposta. */
    const cls = n == null ? "" : n >= 4 ? "ok" : n >= 3 ? "med" : "no";
    return `<div class="hd-jz-d">
      <div class="hd-jz-h">
        <span class="hd-jz-t">${esc(HOLD_DIM[chave] || chave)}</span>
        <span class="hd-jz-n ${cls}">${n == null ? "—" : `${n}/5`}</span>
      </div>
      <p class="hd-jz-r">${esc(v.reasoning || "")}</p>
      ${v.modelo ? `<p class="hd-jz-m">${esc(v.modelo)}</p>` : ""}
    </div>`;
  }).join("");

  const validas = dims.map(([, v]) => v.score).filter((n) => typeof n === "number");
  const media = validas.length
    ? (validas.reduce((a, b) => a + b, 0) / validas.length).toFixed(1) : null;

  return `<div class="hd-jz">
    <div class="hd-ver-h">
      <h4>Comitê de juízes</h4>
      ${media ? `<span class="hd-selo ${media >= 4 ? "ok" : media >= 3 ? "med" : "no"}">${media}/5</span>` : ""}
      <span class="hd-caso-meta">camada 2</span>
    </div>
    <div class="hd-ver-b">
      ${notas}
      <p class="hd-jz-av">Ordena execuções; não mede acerto. Sem calibração humana.</p>
    </div>
  </div>`;
}

/* Acoes de impacto: o que o cenario exigia que fosse EXECUTADO na plataforma, e o que
   o agente de fato executou. Tres dos oito cenarios (HOLD-06, 07, 08) so passam com
   acao — sem este bloco, a tela mostrava recall de consulta e silenciava a parte que
   decide o veredito deles. Omitido quando nao ha acao exigida nem executada, que e o
   caso dos cenarios de `orientar`. */
function holdAcoes(v) {
  const exigidas = v.acoes_exigidas || [];
  const executadas = v.acoes_executadas || [];
  const faltantes = new Set(v.acoes_faltantes || []);
  const naoPrevistas = new Set(v.acoes_nao_previstas || []);
  if (!exigidas.length && !executadas.length) return "";

  const linhas = exigidas.map((a) => {
    const feita = !faltantes.has(a);
    return `<div class="hd-q">
      <span class="hd-q-m ${feita ? "hit" : "miss"}">${feita ? "✓" : "✕"}</span>
      <span><code>${esc(a)}</code>${feita ? "" : `<span class="hd-q-n">não foi executada</span>`}</span>
    </div>`;
  }).join("");

  /* Acao executada fora do previsto é o caso grave: o agente alterou estado na
     plataforma industrial que o cenario nao pedia. Merece destaque proprio, nao uma
     linha discreta como a consulta extra. */
  const extras = executadas.filter((a) => naoPrevistas.has(a));

  return `<p style="margin:11px 0 5px"><b>Ação na plataforma:</b>${
    exigidas.length ? "" : " o cenário não exige nenhuma."}</p>
    ${linhas}
    ${extras.length
      ? `<p style="margin-top:7px; color:var(--crit)"><b>Executou sem previsão:</b>
         <code>${extras.map(esc).join("</code>, <code>")}</code> &mdash; alteração de estado
         que o cenário não pedia.</p>`
      : ""}
    ${!exigidas.length && executadas.length && !extras.length
      ? `<p style="color:var(--ink-3)">Executou <code>${executadas.map(esc).join("</code>, <code>")}</code>,
         dentro do que o cenário permite.</p>`
      : ""}`;
}

/* O veredito: a unica parte que mostra gabarito, e so depois de o agente responder. */
function holdVeredito(v) {
  if (v.erro) return `<div class="hd-ver"><div class="hd-ver-b"><p>${esc(v.erro)}</p></div></div>`;
  const ok = v.passou;
  const consultas = (v.consultas_esperadas || []).map((q) => `
    <div class="hd-q">
      <span class="hd-q-m ${q.feita ? "hit" : "miss"}">${q.feita ? "✓" : "✕"}</span>
      <span><code>${esc(q.step)}</code>
        ${q.nota ? `<span class="hd-q-n">${esc(q.nota)}</span>` : ""}</span>
    </div>`).join("");

  /* Escalonamento com 404 nao e erro do agente: nenhum caso do holdout existe em
     `data/cases.parquet`, entao `POST /cases/{id}/escalate` responde 404 mesmo para
     quem tem a permissao. Esta ressalva ja esta no README do holdout; repeti-la aqui
     evita que quem assiste leia a linha vermelha como falha de decisao. */
  const escalou404 = (v.acoes_executadas || []).some((a) => a.includes("/escalate"));

  return `<div class="hd-ver">
    <div class="hd-ver-h">
      <h4>Gabarito do holdout</h4>
      <span class="hd-selo ${ok ? "ok" : "no"}">${ok ? "PASSOU" : "NÃO PASSOU"}</span>
      <span class="hd-caso-meta">${esc(v.ticket_id || "")}</span>
    </div>
    <div class="hd-ver-b">
      <p><b>O que o cenário cobra:</b> ${esc(v.pergunta_raiz || "—")}</p>
      ${v.faceta ? `<p style="color:var(--ink-3)">${esc(v.faceta)}</p>` : ""}
      <p><b>Resolução:</b> o agente decidiu <code>${esc(v.decisao || "—")}</code>;
        o cenário aceita <code>${(v.decisoes_aceitas || []).map(esc).join("</code>, <code>")}</code>
        &mdash; ${v.decisao_correta ? "bate" : `<b style="color:var(--crit)">não bate</b>`}${
          v.cenario_ambiguo ? " (cenário admite mais de um desfecho)" : ""}.</p>
      ${consultas ? `<p style="margin-bottom:5px"><b>Evidência que o cenário exige:</b></p>${consultas}` : ""}
      ${(v.consultas_extras || []).length
        ? `<p style="margin-top:9px; color:var(--ink-3)">Além do gabarito:
           <code>${v.consultas_extras.map(esc).join("</code>, <code>")}</code></p>` : ""}
      ${holdAcoes(v)}
      ${escalou404
        ? `<p style="margin-top:9px; color:var(--ink-3)">O <code>404</code> é do ambiente:
           nenhum cenário do holdout existe em <code>cases.parquet</code>.</p>`
        : ""}
      <div class="hd-mets">
        <div class="hd-met"><b>${((v.recall_evidencia ?? 0) * 100).toFixed(0)}%</b>recall de evidência</div>
        <div class="hd-met"><b>${v.chamadas ?? 0}</b>chamadas</div>
        <div class="hd-met"><b>${v.repeticoes ?? 0}</b>repetidas</div>
        <div class="hd-met"><b>${v.erros_http ?? 0}</b>erros HTTP</div>
        ${v.justificativa_len
          ? `<div class="hd-met"><b>${v.justificativa_len}</b>caracteres de justificativa</div>` : ""}
      </div>
    </div>
  </div>`;
}

function holdCorpo() {
  const cards = HOLD.cenarios.map((c) => {
    const feito = HOLD.feitos[c.id];
    const sel = HOLD.atual === c.id;
    return `<button class="hd-c" data-caso="${esc(c.id)}" aria-current="${sel}"
        ${HOLD.fonte ? "disabled" : ""}>
      <span class="hd-c-t"><span class="hd-c-id">${esc(c.ticket_id || c.id)}</span>
        <span class="hd-c-a">${esc(c.asset_id || "—")}</span></span>
      <span class="hd-c-m">${esc(c.message || "")}</span>
      ${feito ? `<span class="hd-c-v ${feito.passou ? "ok" : "no"}">${
        feito.passou ? "✓ passou" : "✕ não passou"} · ${esc(feito.decisao || "")}</span>` : ""}
    </button>`;
  }).join("");

  return `<div class="eng-s">
    <p class="hd-intro">Oito cenários reservados para o teste final &mdash; o agente nunca os
      viu. Cada consulta à API aparece enquanto acontece; o gabarito, só no fim.</p>
    <div class="hd-grid">
      <div class="hd-cen">${cards}</div>
      <div class="hd-pal" id="hd-pal">${holdPainel()}</div>
    </div>
  </div>`;
}

/* O painel direito quando ninguem esta rodando nada: ou o convite, ou a previa do
   cenario escolhido com o botao de executar. Selecionar e executar sao dois gestos
   separados de proposito — o segundo gasta uma chamada de LLM, e a cota e finita. */
function holdPainel() {
  if (!HOLD.atual) return `<div class="hd-vazio">Escolha um cenário</div>`;
  const c = HOLD.cenarios.find((x) => x.id === HOLD.atual);
  if (!c) return `<div class="hd-vazio">cenário não encontrado</div>`;
  const feito = HOLD.feitos[c.id];

  return `<div class="hd-prev">
    <div class="hd-prev-h">
      <span class="hd-prev-id">${esc(c.ticket_id || "")} · ${esc(c.id)}</span>
      <span class="hd-caso-meta">${esc(c.asset_id || "—")} · ${esc(c.user_id || "")}</span>
    </div>
    <p class="hd-prev-m">“${esc(c.message || "")}”</p>
    <div class="hd-acoes">
      <button class="hd-go" id="hd-go" type="button">
        <span class="go-i">▶</span> ${feito ? "Executar de novo" : "Executar o agente"}
      </button>
      <label class="hd-chk"><input type="checkbox" id="hd-julgar"${HOLD.julgar ? " checked" : ""}>
        <span>avaliar também com o comitê de juízes${
          HOLD.julgar && JUIZ.escolhido ? ` <code class="hd-chk-m">${esc(JUIZ.escolhido)}</code>` : ""}</span></label>
    </div>
    <p class="hd-prev-n">Execução real: consulta a API e gasta cota.${
        feito ? " Rodar de novo sobrescreve o resultado." : ""}</p>
  </div>`;
}

/* Redesenha o painel direito e religa o botao. Usado ao trocar de cenario. */
function holdMostraPrevia() {
  const pal = document.getElementById("hd-pal");
  if (!pal) return;
  pal.innerHTML = holdPainel();
  const go = document.getElementById("hd-go");
  if (go) go.addEventListener("click", () => holdRoda(HOLD.atual));
  const chk = document.getElementById("hd-julgar");
  if (chk) chk.addEventListener("change", () => {
    HOLD.julgar = chk.checked;
    /* A escolha persiste: quem liga o comitê costuma querer nas execuções seguintes. */
    guarda.escrever("hold-julgar", chk.checked ? "on" : "");
    /* Redesenha para o nome do modelo aparecer (ou sumir) ao lado da caixa: sem isto o
       rótulo fica dizendo o contrário do que a próxima execução vai usar. */
    holdMostraPrevia();
  });
}

/* Roda um cenario, desenhando cada evento assim que chega. */
function holdRoda(caseId) {
  if (HOLD.fonte || !caseId) return;            // uma execucao por vez: cota e finita
  HOLD.atual = caseId;
  /* Trava a lista enquanto roda, sem redesenhar o corpo: `holdCorpo()` aqui recriaria
     os cards e derrubaria o painel que esta prestes a receber o log. */
  document.querySelectorAll(".hd-c").forEach((b) => b.setAttribute("disabled", ""));

  const pal = document.getElementById("hd-pal");
  pal.innerHTML = `<div class="hd-bar"><span class="hd-pulse"></span>
      <span class="hd-st" id="hd-st">conectando…</span>
      <span class="hd-tk" id="hd-tk"></span></div>
    <div class="hd-log" id="hd-log"></div>`;

  const log = document.getElementById("hd-log");
  const st = document.getElementById("hd-st");
  const tk = document.getElementById("hd-tk");
  let tokens = 0;

  const params = new URLSearchParams();
  if (HOLD.julgar) params.set("julgar", "true");
  if (HOLD.julgar && JUIZ.escolhido) params.set("modelo_juiz", JUIZ.escolhido);
  const qs = params.toString();
  const fonte = new EventSource(
    `${API_AGENTE}/holdout/executar/${encodeURIComponent(caseId)}${qs ? `?${qs}` : ""}`
  );
  HOLD.fonte = fonte;

  const encerra = () => {
    fonte.close();
    HOLD.fonte = null;
    /* Reabilita os cards sem redesenhar o painel: `holdCorpo()` aqui apagaria o log
       que a pessoa acabou de ver rolar. */
    document.querySelectorAll(".hd-c").forEach((b) => b.removeAttribute("disabled"));
    /* Um botao no fim do log devolve o gesto de executar sem exigir que a pessoa
       reselecione o cenario — o log e o veredito continuam na tela. */
    if (!document.getElementById("hd-again")) {
      log.insertAdjacentHTML("beforeend",
        `<div style="padding:11px 2px 3px"><button class="hd-go" id="hd-again" type="button">
          <span class="go-i">▶</span> Executar outra vez</button></div>`);
      document.getElementById("hd-again").addEventListener("click", () => {
        const alvo = HOLD.atual;
        holdMostraPrevia();
        holdRoda(alvo);
      });
      log.scrollTop = log.scrollHeight;
    }
  };

  fonte.onmessage = (msg) => {
    let ev;
    try { ev = JSON.parse(msg.data); } catch { return; }

    if (ev.tipo === "inicio") {
      st.textContent = "o agente está trabalhando…";
      pal.insertAdjacentHTML("afterbegin", `<div class="hd-caso">
        <div class="hd-caso-h">
          <span class="hd-caso-id">${esc(ev.ticket_id || "")} · ${esc(ev.case_id || "")}</span>
          <span class="hd-caso-meta">${esc(ev.asset_id || "—")} · ${esc(ev.user_id || "")} · seed ${esc(ev.seed || "")}</span>
        </div>
        <p class="hd-caso-m">“${esc(ev.mensagem || "")}”</p>
      </div>`);
      return;
    }

    if (ev.tipo === "llm") { tokens += ev.total || 0; tk.textContent = `${tokens.toLocaleString("pt-BR")} tokens`; }

    if (ev.tipo === "resposta") {
      st.textContent = "respondeu — comparando com o gabarito…";
      log.insertAdjacentHTML("beforeend", `<div class="hd-resp">
        <span class="hd-dec">${esc(ev.decisao || "—")}</span>
        <h4>Resposta ao cliente</h4>
        <p>${esc(ev.resposta || "(sem resposta)")}</p>
      </div>`);
      log.scrollTop = log.scrollHeight;
      return;
    }

    if (ev.tipo === "veredito") {
      HOLD.feitos[ev.case_id] = { passou: ev.passou, decisao: ev.decisao };
      log.insertAdjacentHTML("beforeend", holdVeredito(ev));
      log.scrollTop = log.scrollHeight;
      /* Com o comitê ligado o fluxo continua: `juizes` (ou `juizes_erro`) ainda vem.
         Encerrar aqui fecharia o SSE antes das notas chegarem. */
      if (HOLD.julgar) { st.textContent = "julgando a resposta…"; return; }
      document.querySelector(".hd-bar")?.remove();
      encerra();
      /* Atualiza o selo no card da esquerda, agora que o resultado existe. */
      const alvo = document.querySelector(`.hd-c[data-caso="${CSS.escape(ev.case_id)}"]`);
      if (alvo && !alvo.querySelector(".hd-c-v")) {
        alvo.insertAdjacentHTML("beforeend", `<span class="hd-c-v ${ev.passou ? "ok" : "no"}">${
          ev.passou ? "✓ passou" : "✕ não passou"} · ${esc(ev.decisao || "")}</span>`);
      }
      return;
    }

    if (ev.tipo === "juizes_iniciou") {
      log.insertAdjacentHTML("beforeend",
        `<div class="hd-jz-wait" id="hd-jz-wait">comitê avaliando a resposta em
         ${(ev.dimensoes || []).length} dimensões…</div>`);
      log.scrollTop = log.scrollHeight;
      return;
    }

    if (ev.tipo === "juizes") {
      document.getElementById("hd-jz-wait")?.remove();
      document.querySelector(".hd-bar")?.remove();
      log.insertAdjacentHTML("beforeend", holdJuizes(ev.vereditos, ev.modelos));
      log.scrollTop = log.scrollHeight;
      encerra();
      return;
    }

    if (ev.tipo === "juizes_erro") {
      document.getElementById("hd-jz-wait")?.remove();
      document.querySelector(".hd-bar")?.remove();
      /* O comitê é opcional: falhar nele não invalida a camada 1, que já está na tela. */
      log.insertAdjacentHTML("beforeend", `<div class="hd-jz-erro">
        Não foi possível julgar: ${esc(ev.mensagem || "")}</div>`);
      log.scrollTop = log.scrollHeight;
      encerra();
      return;
    }

    if (ev.tipo === "erro") {
      st.textContent = "a execução falhou";
      document.querySelector(".hd-pulse")?.remove();
      log.insertAdjacentHTML("beforeend", holdEventoHtml(ev));
      encerra();
      return;
    }

    const html = holdEventoHtml(ev);
    if (html) { log.insertAdjacentHTML("beforeend", html); log.scrollTop = log.scrollHeight; }
  };

  /* `EventSource` reconecta sozinho por padrao — o que aqui significaria rodar o
     cenario de novo, gastando cota. Fechar na primeira falha e o comportamento certo. */
  fonte.onerror = () => {
    if (HOLD.fonte) {
      st.textContent = "conexão interrompida";
      document.querySelector(".hd-pulse")?.remove();
      encerra();
    }
  };
}

function holdLigaCards() {
  document.querySelectorAll(".hd-c").forEach((b) => {
    b.addEventListener("click", () => {
      if (HOLD.fonte) return;                   // execucao em curso: nao troca de caso
      /* Clicar no card SELECIONA. Quem executa e o botao da previa: assim ninguem
         dispara uma chamada de LLM so por explorar a lista. */
      HOLD.atual = b.dataset.caso;
      document.querySelectorAll(".hd-c").forEach((o) => {
        o.setAttribute("aria-current", String(o === b));
      });
      holdMostraPrevia();
    });
  });
}

function ligarHoldout() {
  const cx = document.getElementById("hold");
  const corpo = document.getElementById("hold-corpo");
  const abrir = document.getElementById("sw-hold");

  let antes = null;
  const abre = async () => {
    antes = document.activeElement;
    cx.setAttribute("open", "");
    document.getElementById("hold-x").focus();

    if (!HOLD.cenarios.length) {
      corpo.innerHTML = `<div class="hd-vazio">carregando os cenários…</div>`;
      try {
        const r = await fetch(`${API_AGENTE}/holdout/cenarios`).then((x) => x.json());
        HOLD.cenarios = r.cenarios || [];
      } catch {
        /* Sem o agente no ar nao ha o que rodar — a aba inteira depende dele, ao
           contrario da leitura por ativo, que e estatica. */
        corpo.innerHTML = `<div class="hd-vazio">
          <b>O agente não está no ar.</b><br>
          Esta aba executa o agente de verdade, então precisa de <code>make consulta</code>
          com a API industrial rodando (<code>make up</code>).</div>`;
        return;
      }
    }
    corpo.innerHTML = holdCorpo();
    holdLigaCards();
    holdMostraPrevia();
  };
  const fecha = () => {
    /* Fechar no meio de uma execucao encerraria o streaming e perderia o resultado de
       uma chamada de LLM que ja foi paga. O trace fica em disco de qualquer forma, mas
       a tela nao teria como reconstruir o log. */
    if (HOLD.fonte && !confirm("Uma execução está em andamento. Fechar mesmo assim?")) return;
    if (HOLD.fonte) { HOLD.fonte.close(); HOLD.fonte = null; }
    cx.removeAttribute("open");
    if (antes) antes.focus();
  };

  ligaDica(abrir, `<span class="dica-t">holdout ao vivo</span>
    <p>Oito cenários que o agente nunca viu, resolvidos na sua frente.</p>`);
  abrir.addEventListener("click", abre);
  document.getElementById("hold-x").addEventListener("click", fecha);
  cx.addEventListener("click", (e) => { if (e.target === cx) fecha(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && cx.hasAttribute("open")) fecha();
  });
}

function ligarExperimentos() {
  const cx = document.getElementById("exp");
  const corpo = document.getElementById("exp-corpo");
  const abrir = document.getElementById("sw-exp");

  let antes = null;
  /* Redesenha a aba inteira preservando o scroll: os exploradores ficam no meio de um
     modal longo, e repintar do zero jogaria o leitor para o topo a cada seta clicada. */
  const redesenha = () => {
    const y = cx.scrollTop;
    corpo.innerHTML = corpoExperimentos();
    ligarDicas(corpo);
    cx.scrollTop = y;
  };
  const abre = () => {
    antes = document.activeElement;
    redesenha();
    cx.setAttribute("open", "");
    document.getElementById("exp-x").focus();
  };

  /* Um só ouvinte para todos os exploradores: navegar amostras, filtrar por fase e abrir
     o método. Delegação porque o corpo é substituído a cada clique — ouvintes presos aos
     botões morreriam junto com eles. */
  corpo.addEventListener("click", (ev) => {
    const alvo = ev.target.closest("[data-xp-ir],[data-xp-m],[data-xp-f]");
    if (!alvo) return;
    const ir = alvo.dataset.xpIr;
    // Qual seta foi clicada, para devolver o foco à seta equivalente depois do redesenho:
    // o `data-xp-ir` do botão muda de valor junto com o índice, então buscá-lo de volta
    // pelo valor antigo não acharia nada.
    let alvoId = null, direcao = 0;
    if (ir) {
      const [id, i] = ir.split(":");
      direcao = Number(i) > (XP_ABERTO[id] ?? 0) ? 1 : -1;
      alvoId = id;
      XP_ABERTO[id] = Number(i);
    } else if (alvo.dataset.xpM) {
      const id = alvo.dataset.xpM;
      XP_METODO[id] = !XP_METODO[id];
    } else {
      XP_FILTRO["EXP-04"] = alvo.dataset.xpF;
    }
    redesenha();
    // O foco volta para o mesmo botão: sem isso, quem navega por teclado é devolvido ao
    // topo do modal a cada passo da amostra.
    let volta = null;
    if (alvoId) {
      const i = XP_ABERTO[alvoId];
      volta = corpo.querySelector(`[data-xp-ir="${alvoId}:${i + direcao}"]`);
    } else if (alvo.dataset.xpM) {
      volta = corpo.querySelector(`[data-xp-m="${alvo.dataset.xpM}"]`);
    } else {
      volta = corpo.querySelector(`[data-xp-f="${alvo.dataset.xpF}"]`);
    }
    // Na ponta da lista a seta clicada fica desabilitada; o foco vai para a oposta, que é
    // o único movimento ainda possível.
    if (volta?.disabled && alvoId) {
      volta = corpo.querySelector(`[data-xp-ir="${alvoId}:${XP_ABERTO[alvoId] - direcao}"]`);
    }
    if (volta && !volta.disabled) volta.focus();
  });
  const fecha = () => {
    cx.removeAttribute("open");
    if (antes) antes.focus();
  };

  ligaDica(abrir, `<span class="dica-t">experimentos</span>
    <p>Cinco hipóteses com as execuções que as testaram.</p>`);
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
    const sel = corpo.querySelector("#sel-juiz");
    if (sel) sel.addEventListener("change", () => {
      JUIZ.escolhido = sel.value;
      guarda.escrever("juiz-modelo", sel.value);
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
    /* O catálogo do OpenRouter chega depois; `sincroniza` redesenha com a lista real. */
    carregaJuizModelos(() => { if (cx.hasAttribute("open")) sincroniza(); });
  };
  const fecha = () => {
    cx.removeAttribute("open");
    if (antes) antes.focus();
  };

  ligaDica(abrir, `<span class="dica-t">configuração</span>
    <p>Tema, política de evidência e metodologia.</p>`);
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
    `A seed decide o modo de resposta por <code>hash(seed | recurso | categoria)</code>.`;
}

/* ---------------- esqueleto de carregamento ----------------
 * Enquanto os quatro arquivos de dados nao chegam, a lista e o painel ficam vazios. Um
 * vazio de dois segundos nao se distingue de uma pagina quebrada, e a alternativa comum
 * — um spinner centralizado — nao diz nada sobre o que vem. Estas formas tem a altura
 * do que de fato vai chegar, entao nada salta de lugar na troca.
 *
 * `aria-busy` no container e um unico `aria-label`: quem usa leitor de tela ouve
 * "carregando", nao dezoito retangulos.
 */
function esqueleto() {
  /* A marca e montada em JS para nao deixar o cabecalho com um divisor solto ao lado
     de um espaco vazio antes do primeiro paint. Nao depende de fetch nenhum, entao pode
     ser pintada junto com o esqueleto em vez de esperar os dados. */
  const marca = document.getElementById("marca");
  if (marca && !marca.firstChild) marca.innerHTML = marcaTractian(15);

  const itens = document.getElementById("items");
  const panel = document.getElementById("panel");
  if (itens) {
    itens.setAttribute("aria-busy", "true");
    itens.setAttribute("aria-label", "Carregando a lista de ativos");
    itens.innerHTML = Array.from({ length: 8 }, () =>
      `<div class="sk-item"><div class="sk sk-st"></div>
        <div><div class="sk sk-n"></div><div class="sk sk-s"></div></div>
        <div class="sk sk-v"></div></div>`).join("");
  }
  if (panel) {
    panel.setAttribute("aria-busy", "true");
    panel.setAttribute("aria-label", "Carregando a leitura do ativo");
    panel.innerHTML =
      `<div class="sk-card"><div class="sk sk-hd"></div><div class="sk sk-t"></div>
        <div class="sk sk-l" style="width:72%"></div></div>` +
      `<div class="sk-card"><div class="sk sk-hd"></div><div class="sk sk-plot"></div></div>` +
      `<div class="sk-card"><div class="sk sk-hd"></div>
        <div class="sk sk-l" style="width:88%"></div>
        <div class="sk sk-l" style="width:64%"></div>
        <div class="sk sk-l" style="width:79%"></div></div>`;
  }
}

/* Os dados chegaram (ou falharam): `lista()` e `desenhar()` trocam o innerHTML, mas
   `aria-busy` fica para tras se ninguem o tirar — e um container marcado como ocupado
   para sempre e pior que nenhum. */
function fimDoEsqueleto() {
  ["items", "panel"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.removeAttribute("aria-busy");
    el.removeAttribute("aria-label");
  });
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
  ligarHoldout();
  atual = DATA.slice().sort((x, y) => ORDEM[situacao(x).key] - ORDEM[situacao(y).key])[0].id;
  fimDoEsqueleto();
  lista();
  desenhar();
}

// Antes de qualquer fetch: senao a pagina pisca no tema errado enquanto os dados chegam.
aplicaTema();
// Antes do await, nao depois: pintado no mesmo quadro em que a pagina aparece.
esqueleto();
/* `ativos.json` e o unico fetch sem `.catch`: sem ele nao ha o que desenhar. Se cair, o
   esqueleto pulsaria indefinidamente prometendo dados que nao vem — entao o lugar de
   dizer isso e aqui, com o caminho que falhou e o alvo do Makefile que o gera. */
carregar().catch((e) => {
  console.error("falha ao carregar os dados do painel", e);
  fimDoEsqueleto();
  const itens = document.getElementById("items");
  if (itens) itens.innerHTML = "";
  document.getElementById("panel").innerHTML =
    `<div class="empty"><b>Os dados do painel não carregaram</b>
      Falta <code class="mono">solution/painel/dados/ativos.json</code>, ou o servidor não
      está servindo a pasta. Gere os dados com <code class="mono">make leitura-dados</code>
      e recarregue. Detalhe técnico no console: <code class="mono">${esc(String(e.message || e))}</code>.</div>`;
});
/* O tooltip se posiciona a partir de getBoundingClientRect() no momento do hover, entao
   redimensionar a janela nao exige religar nada — reanexar aqui so empilharia listeners. */
// Rolar com uma dica aberta a deixaria orfa: ela e `position:fixed`, o alvo nao.
addEventListener("scroll", escondeDica, { passive: true });
