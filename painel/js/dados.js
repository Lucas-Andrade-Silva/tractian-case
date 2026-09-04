/* Carregamento do bundle, índice das execuções e os primitivos de formatação.
 *
 * O ponto mais importante deste módulo é `pct`: métrica sem base devolve "—", nunca "0%".
 * A avaliação inteira distingue "não concluiu nada" de "concluiu e errou" — se a UI
 * imprimir 0% onde a medida não existe, ela desfaz essa distinção na última etapa. */

export const ESTADO = {
  bundle: null,
  aba: "operacao",
  fase: "baseline",
  seed: "complete",
  execucaoId: null,
  celulaId: null,
  filtros: { empresa: "", ativo: "", papel: "", decisao: "" },
  busca: "",
  expandidas: new Set(),
};

export async function carregaBundle() {
  const resposta = await fetch("dados/bundle.json");
  if (!resposta.ok) {
    throw new Error(
      `Não foi possível ler dados/bundle.json (HTTP ${resposta.status}). ` +
        "Gere o arquivo com: python painel/build_bundle.py"
    );
  }
  ESTADO.bundle = await resposta.json();
  return ESTADO.bundle;
}

/* -- formatação --------------------------------------------------------- */

export const VAZIO = "—";

/** Percentual. `null`/`undefined` viram "—": ausência de medida não é zero. */
export function pct(valor, casas = 1) {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return VAZIO;
  return `${(valor * 100).toFixed(casas)}%`;
}

export function num(valor, casas = 0) {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return VAZIO;
  return Number(valor).toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}

/** Campo textual ausente. RN-02: a UI declara que não sabe, não preenche. */
export function texto(valor) {
  const limpo = typeof valor === "string" ? valor.trim() : valor;
  return limpo === null || limpo === undefined || limpo === "" ? "não determinado" : limpo;
}

export function duracao(ms) {
  if (ms === null || ms === undefined) return VAZIO;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/* -- vocabulário do domínio --------------------------------------------- */

/** `stop_reason` legível (RF-20) — o enum cru não é para o leitor. */
export const STOP_REASON = {
  concluido: { texto: "Concluído", tom: "sucesso" },
  budget_supervisor: { texto: "Orçamento de turnos esgotado", tom: "atencao" },
  budget_worker: { texto: "Orçamento de investigação esgotado", tom: "atencao" },
  erro_execucao: { texto: "Erro de execução", tom: "atencao" },
};

/** Os 5 modos do envelope probabilístico, com o que cada um muda na conclusão (RN-12). */
export const MODOS = {
  complete: { texto: "completo", tom: "sucesso", ajuda: "Dado íntegro, sem campos faltando." },
  partial: { texto: "parcial", tom: "atencao", ajuda: "Campos ausentes na resposta — as `notes` dizem quais." },
  inconclusive: { texto: "inconclusivo", tom: "atencao", ajuda: "A consulta respondeu, mas não sustenta conclusão." },
  conflict: { texto: "conflito", tom: "atencao", ajuda: "Fontes divergem entre si; exige desempate por evidência." },
  unavailable: { texto: "indisponível", tom: "erro", ajuda: "O recurso não pôde ser recuperado." },
};

/** Decisão: escalar é desfecho correto, nunca vermelho (RN-10). */
export const DECISOES = {
  orientar: { texto: "orientar", tom: "sucesso" },
  agir: { texto: "agir", tom: "sucesso" },
  escalar: { texto: "escalar", tom: "neutro" },
};

export const PAPEIS_PT = {
  maintenance_manager: "Gerente de manutenção",
  reliability_analyst: "Analista de confiabilidade",
  engineer: "Engenheiro",
  mechanic: "Mecânico",
  operator: "Operador",
  coordinator: "Coordenador",
  electrician: "Eletricista",
};

/** Quais perfis detêm cada permissão — usado para responder "quem poderia?" num 403.
 *  Derivado dos solicitantes presentes nos próprios traces, não de tabela externa. */
export function perfisComPermissao(bundle, permissao) {
  const perfis = new Set();
  for (const execucao of bundle.execucoes) {
    const solicitante = execucao.operacao.solicitante;
    if (solicitante && (solicitante.permissions || []).includes(permissao)) {
      perfis.add(solicitante.role);
    }
  }
  return [...perfis].sort();
}

/** Permissão exigida, extraída da mensagem de erro 403 da API. */
export function permissaoExigida(passo) {
  const fonte = passo.erro || (passo.response && passo.response.message) || "";
  const achado = /Permiss[ãa]o necess[áa]ria:\s*([a-z_]+)/i.exec(fonte);
  return achado ? achado[1] : null;
}

export const ACAO_ROTULO = {
  reprocess: "reprocessar análise",
  "request-specialist": "solicitar análise especializada",
  "request-retraining": "solicitar retreinamento do modelo",
  escalate: "escalar para humano",
};

/** Nome legível de uma ação de impacto a partir da rota. */
export function rotuloAcao(passo) {
  if (passo.metodo === "PATCH") return "alterar configuração do ativo";
  const fim = (passo.rota || "").split("/").pop();
  return ACAO_ROTULO[fim] || "ação de impacto";
}

/* -- seleção ------------------------------------------------------------ */

export function execucoesDaFase(fase) {
  return ESTADO.bundle.execucoes.filter((e) => e.fase === fase);
}

export function achaExecucao(caseId, seed, fase) {
  return ESTADO.bundle.execucoes.find(
    (e) => e.case_id === caseId && e.seed === seed && e.fase === fase
  );
}

/** Fila da aba Operação: fase + seed + filtros + busca. */
export function filaVisivel() {
  const { fase, seed, filtros, busca } = ESTADO;
  const alvo = busca.trim().toLowerCase();

  return execucoesDaFase(fase)
    .filter((e) => e.seed === seed)
    .filter((e) => {
      const solicitante = e.operacao.solicitante || {};
      if (filtros.empresa && solicitante.company_id !== filtros.empresa) return false;
      if (filtros.ativo && e.operacao.asset_id !== filtros.ativo) return false;
      if (filtros.papel && solicitante.role !== filtros.papel) return false;
      if (filtros.decisao && e.operacao.decisao !== filtros.decisao) return false;
      if (!alvo) return true;
      // Busca por ticket, ativo, empresa ou conteúdo da mensagem (RF-05).
      const campos = [
        e.ticket_id,
        e.cenario,
        e.operacao.asset_id,
        (e.operacao.ativo || {}).name,
        solicitante.company_id,
        solicitante.name,
        e.operacao.mensagem,
      ];
      return campos.some((c) => c && String(c).toLowerCase().includes(alvo));
    })
    .sort((a, b) => a.ticket_id.localeCompare(b.ticket_id));
}

/** Chamadas de impacto de uma execução (POST/PATCH) — sempre com o body enviado. */
export function acoesDeImpacto(execucao) {
  return execucao.operacao.timeline.filter(
    (evento) => evento.tipo === "chamada" && evento.metodo !== "GET"
  );
}

export function temAcaoExecutada(execucao) {
  return acoesDeImpacto(execucao).some((a) => a.ok);
}

/* -- utilidades de DOM -------------------------------------------------- */

export function el(tag, props = {}, filhos = []) {
  const node = document.createElement(tag);
  for (const [chave, valor] of Object.entries(props)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (chave === "class") node.className = valor;
    else if (chave === "text") node.textContent = valor;
    else if (chave === "html") node.innerHTML = valor;
    else if (chave.startsWith("on")) node.addEventListener(chave.slice(2), valor);
    else node.setAttribute(chave, valor === true ? "" : valor);
  }
  for (const filho of [].concat(filhos)) {
    if (filho === null || filho === undefined || filho === false) continue;
    node.append(filho.nodeType ? filho : document.createTextNode(String(filho)));
  }
  return node;
}

export function limpa(node) {
  while (node.firstChild) node.firstChild.remove();
  return node;
}
