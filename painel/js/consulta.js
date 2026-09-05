/* Consulta ao vivo — comunicação com o agente para a batida ④.
 *
 * Diferença essencial em relação às outras três batidas: elas leem o bundle estático
 * já gravado; esta fala com o agente ao vivo (`python server.py --serve`). Por isso é
 * a única que depende do servidor estar no ar, e trata a ausência dele como estado
 * previsto, não como erro. O desenho da batida vive em `batida-aovivo.js` — este
 * módulo é só o estado (`CONSULTA`) e a comunicação com o servidor.
 *
 * Duas regras de apresentação que não são estéticas, aplicadas em `batida-aovivo.js`:
 *
 * 1. O resultado sempre chega marcado como métrica sintética (ADR 0007). Nota de juiz
 *    contra gabarito escrito por LLM não é comparável com as notas dos 17 cenários.
 *
 * 2. O usuário é escolhido, nunca criado. O seletor lista quem já existe em
 *    `data/users.parquet`, porque é o `user_id` que determina a permissão real na API.
 *    Um 403 na timeline é resultado legítimo, e a UI o mostra como tal.
 */

import { el } from "./dados.js";

/* A origem do painel quando servido pelo próprio agente. Aberto direto do disco
 * (file://), cai no host padrão para que o desenvolvimento continue funcionando. */
const API = window.location.protocol.startsWith("http")
  ? ""
  : "http://127.0.0.1:8001";

export const CONSULTA = {
  usuarios: [],
  ativos: [],
  carregouCatalogo: false,
  erroCatalogo: null,
  saude: null,
  juizes: null,
  // Escolha de modelo por dimensao. Vazio = usa o padrao que /saude reporta; assim a
  // interface nao precisa repetir a configuracao do .env para funcionar.
  modelosJuizes: {},
  mostrarJuizes: false,
  form: { user_id: "", company_id: "", asset_id: "", mensagem: "", seed: "", julgar: true },
  enviando: false,
  erroEnvio: null,
  resultado: null,
  historico: [],
  // Papéis já vistos no trace em andamento (`trace.steps[].agent`) — acende os
  // rótulos da espera honesta da batida ④ conforme o agente avança.
  papeisVistos: [],
};

/* -- comunicação -------------------------------------------------------- */

async function pegaJson(rota, opcoes) {
  const resposta = await fetch(`${API}${rota}`, opcoes);
  if (!resposta.ok) {
    let detalhe = `HTTP ${resposta.status}`;
    try {
      const corpo = await resposta.json();
      if (corpo && corpo.detail) detalhe = corpo.detail;
    } catch {
      // resposta sem corpo JSON: o status já é a informação disponível
    }
    throw new Error(detalhe);
  }
  return resposta.json();
}

export async function carregaCatalogo(redesenha) {
  if (CONSULTA.carregouCatalogo) return;
  try {
    const [catalogo, saude, historico, juizes] = await Promise.all([
      pegaJson("/catalogo"),
      pegaJson("/saude").catch(() => null),
      pegaJson("/consultas").catch(() => ({ consultas: [] })),
      // A consulta ao OpenRouter pode demorar ou falhar; o formulario nao depende dela.
      pegaJson("/juiz/modelos").catch(() => null),
    ]);
    CONSULTA.usuarios = catalogo.usuarios || [];
    CONSULTA.saude = saude;
    CONSULTA.historico = historico.consultas || [];
    CONSULTA.juizes = juizes;
    CONSULTA.erroCatalogo = null;
  } catch (erro) {
    CONSULTA.erroCatalogo = erro.message;
  }
  CONSULTA.carregouCatalogo = true;
  redesenha();
}

async function carregaAtivos(companyId, redesenha) {
  CONSULTA.ativos = [];
  if (!companyId) return redesenha();
  try {
    const dados = await pegaJson(`/catalogo/${companyId}/ativos`);
    CONSULTA.ativos = dados.ativos || [];
  } catch {
    CONSULTA.ativos = [];
  }
  redesenha();
}

export async function envia(redesenha) {
  const { form } = CONSULTA;
  CONSULTA.enviando = true;
  CONSULTA.erroEnvio = null;
  CONSULTA.papeisVistos = [];
  redesenha();

  try {
    const ativo = CONSULTA.ativos.find((a) => a.id === form.asset_id);
    CONSULTA.resultado = await pegaJson("/consulta", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        user_id: form.user_id,
        company_id: form.company_id,
        asset_id: form.asset_id || null,
        mensagem: form.mensagem,
        seed: form.seed || null,
        julgar: form.julgar,
        // Só manda as dimensões efetivamente trocadas: dimensão ausente cai no padrão
        // do servidor, e mandar o padrão de volta duplicaria a fonte da verdade.
        modelos_juizes: Object.keys(CONSULTA.modelosJuizes).length
          ? CONSULTA.modelosJuizes
          : null,
        contexto_ativo: ativo
          ? {
              nome: ativo.name,
              tipo: ativo.machine_type,
              criticidade: ativo.criticality,
              // O agente descobre isso sozinho, mas o gerador de gabarito nao chama a
              // API: sem esta linha ele nao sabe que o sensor pode estar mudo.
              sensor: ativo.sensor_status,
            }
          : null,
      }),
    });
    const trace = CONSULTA.resultado.trace || {};
    CONSULTA.papeisVistos = [...new Set((trace.steps || []).map((s) => s.agent).filter(Boolean))];
    CONSULTA.historico = [CONSULTA.resultado, ...CONSULTA.historico];
  } catch (erro) {
    CONSULTA.erroEnvio = erro.message;
  }
  CONSULTA.enviando = false;
  redesenha();
}

/* -- diagnóstico de falha de execução -------------------------------------
 *
 * Exportadas: classificam a falha pelo que o leitor precisa fazer a seguir
 * (esperar, trocar de modelo, ou consertar o agente), e isso não sai de um
 * stack trace. A mensagem original continua disponível, recolhida — é ela
 * que serve para depurar. A batida ④ as usa no ramo de `erroEnvio`.
 */
export function blocoErroExecucao(erro) {
  const bruto = String(erro);
  const diagnostico = diagnosticaErro(bruto);

  return el("div", { class: "aviso aviso-erro" }, [
    el("div", {}, [
      el("strong", { text: `${diagnostico.titulo} ` }),
      diagnostico.explicacao,
    ]),
    el("details", { class: "erro-cru" }, [
      el("summary", { text: "mensagem do provedor" }),
      el("pre", { class: "cru", text: bruto }),
    ]),
  ]);
}

/** Classifica a falha pelo que o leitor precisa fazer a seguir, não pelo tipo do erro. */
export function diagnosticaErro(bruto) {
  if (/rate.?limit|429|too large for model|tokens per minute|TPM|OTPM/i.test(bruto)) {
    return {
      titulo: "Cota do provedor de LLM esgotada.",
      explicacao:
        "O agente não chegou a concluir — não é decisão errada nem falha de lógica. " +
        "O limite do plano gratuito é por minuto e por dia: se for por minuto, esperar " +
        "resolve; se for por dia, só renova no ciclo seguinte.",
    };
  }
  if (/timeout|timed out|ETIMEDOUT/i.test(bruto)) {
    return {
      titulo: "O provedor não respondeu no tempo.",
      explicacao: "A execução foi interrompida em trânsito. Reenviar a mesma consulta é seguro.",
    };
  }
  if (/connection|ECONNREFUSED|Failed to fetch|network/i.test(bruto)) {
    return {
      titulo: "Sem conexão com a API industrial.",
      explicacao: "Verifique se ela está no ar com `make up` antes de reenviar.",
    };
  }
  if (/401|403|api.?key|unauthorized|invalid.*key/i.test(bruto)) {
    return {
      titulo: "Credencial do provedor recusada.",
      explicacao: "A chave em `agent/.env` está ausente, expirada ou sem acesso ao modelo pedido.",
    };
  }
  return {
    titulo: "Falha de execução.",
    explicacao:
      "O agente parou antes de produzir resposta final. Isso é categoria própria: " +
      "não conta como decisão errada.",
  };
}

