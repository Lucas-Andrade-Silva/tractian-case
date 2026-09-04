/* Aba Consulta — entrada de texto livre de um usuário da plataforma.
 *
 * Diferença essencial em relação às outras duas abas: Operação e Avaliação leem o
 * bundle estático já gravado; esta fala com o agente ao vivo (`python server.py
 * --serve`). Por isso ela é a única que depende do servidor estar no ar, e trata a
 * ausência dele como estado previsto, não como erro.
 *
 * Duas regras de apresentação que não são estéticas:
 *
 * 1. O resultado sempre chega marcado como métrica sintética. Nota de juiz contra
 *    gabarito escrito por LLM não é comparável com as notas dos 17 cenários — a UI
 *    afirma isso onde a nota aparece, não num rodapé que ninguém lê.
 *
 * 2. O usuário é escolhido, nunca criado. O seletor lista quem já existe em
 *    `data/users.parquet`, porque é o `user_id` que determina a permissão real na API.
 *    Um 403 na timeline é resultado legítimo, e a UI o mostra como tal.
 */

import { el, pct, num, texto, VAZIO, DECISOES, PAPEIS_PT } from "./dados.js";
import { selo, seloDecisao, secao, aviso, vazio } from "./componentes.js";

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

async function envia(redesenha) {
  const { form } = CONSULTA;
  CONSULTA.enviando = true;
  CONSULTA.erroEnvio = null;
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
    CONSULTA.historico = [CONSULTA.resultado, ...CONSULTA.historico];
  } catch (erro) {
    CONSULTA.erroEnvio = erro.message;
  }
  CONSULTA.enviando = false;
  redesenha();
}

/* -- desenho ------------------------------------------------------------ */

export function desenhaConsulta(raiz, redesenha) {
  if (!CONSULTA.carregouCatalogo) {
    carregaCatalogo(redesenha);
    raiz.append(vazio("Carregando catálogo…"));
    return;
  }

  if (CONSULTA.erroCatalogo) {
    raiz.append(painelOffline());
    return;
  }

  raiz.append(formulario(redesenha));
  if (CONSULTA.saude && CONSULTA.saude.avaliacao_disponivel === false) {
    raiz.append(avisoAvaliacaoIndisponivel());
  }
  if (CONSULTA.erroEnvio) {
    raiz.append(aviso("erro", [el("strong", { text: "Falha na consulta. " }), CONSULTA.erroEnvio]));
  }
  if (CONSULTA.resultado) raiz.append(resultado(CONSULTA.resultado));
  // `> 1` escondia o histórico justamente quando ele tinha a primeira consulta: com um
  // único registro gravado a lista existia e não aparecia.
  if (CONSULTA.historico.length) raiz.append(historico(redesenha));
  // Sem resultado e sem histórico a aba terminava numa tela vazia que não dizia o que
  // ia acontecer ao enviar — e o que vai acontecer aqui consome cota de LLM.
  if (!CONSULTA.resultado && !CONSULTA.historico.length) raiz.append(primeiraVez());
}

/** Estado de primeira execução: diz o que a aba faz antes de existir resultado. */
function primeiraVez() {
  return el("div", { class: "consulta-primeira" }, [
    el("h3", { text: "O que acontece ao enviar" }),
    el("ol", { class: "consulta-etapas" }, [
      el("li", {}, [
        el("strong", { text: "O agente investiga. " }),
        "O mesmo grafo dos 17 cenários, com as permissões do usuário escolhido — " +
          "sem atalho e sem nada especial para esta aba.",
      ]),
      el("li", {}, [
        el("strong", { text: "A trajetória fica visível. " }),
        "Cada chamada à API industrial na ordem em que aconteceu, inclusive as recusadas " +
          "por permissão.",
      ]),
      el("li", {}, [
        el("strong", { text: "A avaliação vem marcada como sintética. " }),
        "A questão de referência é escrita por um LLM, não por humano: as notas ordenam " +
          "consultas livres entre si e nunca entram nas métricas dos cenários com gabarito.",
      ]),
    ]),
  ]);
}

function painelOffline() {
  return el("div", { class: "secao" }, [
    aviso("atencao", [
      el("strong", { text: "O agente não está no ar. " }),
      "Esta aba executa o agente ao vivo, diferente das outras duas, que leem o bundle já gravado.",
    ]),
    el("p", { class: "secao-nota" }, [
      "Suba o servidor com ",
      el("code", { text: "make consulta" }),
      " (ou ",
      el("code", { text: "python agent/server.py --serve" }),
      ") e recarregue. A API industrial também precisa estar no ar: ",
      el("code", { text: "make up" }),
      ".",
    ]),
  ]);
}

function avisoAvaliacaoIndisponivel() {
  return aviso("atencao", [
    el("strong", { text: "Avaliação indisponível: " }),
    CONSULTA.saude.motivo || "gerador e juiz precisam ser modelos diferentes.",
    " A consulta ainda roda, mas sem nota — desmarque ",
    el("em", { text: "avaliar a resposta" }),
    " para executar sem tentar julgar.",
  ]);
}

function formulario(redesenha) {
  const { form } = CONSULTA;
  const usuario = CONSULTA.usuarios.find((u) => u.user_id === form.user_id);
  const pronto = form.user_id && form.mensagem.trim().length >= 10 && !CONSULTA.enviando;

  return secao(
    "Nova consulta",
    "O usuário descreve o que observou com as próprias palavras. O ativo é escolhido na lista para que o agente saiba onde olhar.",
    el("div", { class: "consulta-form" }, [
      el("div", { class: "consulta-linha" }, [
        campo("Usuário", el("select", {
          onchange: (ev) => {
            const escolhido = CONSULTA.usuarios.find((u) => u.user_id === ev.target.value);
            form.user_id = ev.target.value;
            form.company_id = escolhido ? escolhido.company_id : "";
            form.asset_id = "";
            carregaAtivos(form.company_id, redesenha);
          },
        }, [
          el("option", { value: "", text: "selecione…", selected: !form.user_id }),
          ...CONSULTA.usuarios.map((u) =>
            el("option", {
              value: u.user_id,
              text: `${u.name} — ${PAPEIS_PT[u.role] || u.role}`,
              selected: form.user_id === u.user_id,
            })
          ),
        ])),
        campo("Ativo", el("select", {
          disabled: !CONSULTA.ativos.length,
          onchange: (ev) => {
            form.asset_id = ev.target.value;
            redesenha();
          },
        }, [
          el("option", {
            value: "",
            text: CONSULTA.ativos.length ? "sem ativo específico" : "escolha o usuário primeiro",
            selected: !form.asset_id,
          }),
          ...CONSULTA.ativos.map((a) =>
            el("option", {
              value: a.id,
              text: `${a.id} — ${a.name || "sem nome"}`,
              selected: form.asset_id === a.id,
            })
          ),
        ])),
      ]),

      usuario ? fichaPermissoes(usuario) : null,

      campo(
        "O que está acontecendo",
        el("textarea", {
          rows: 4,
          placeholder:
            "Ex.: a bomba está com um ruído diferente desde ontem e a vibração parece ter subido, mas não recebi nenhum alerta.",
          value: form.mensagem,
          oninput: (ev) => {
            form.mensagem = ev.target.value;
          },
        })
      ),

      form.julgar ? seletorJuizes(redesenha) : null,

      el("div", { class: "consulta-acoes" }, [
        el("label", { class: "controle" }, [
          el("input", {
            type: "checkbox",
            checked: form.julgar,
            onchange: (ev) => {
              form.julgar = ev.target.checked;
              redesenha();
            },
          }),
          el("span", { text: "avaliar a resposta (gabarito sintético + juízes)" }),
        ]),
        el("button", {
          class: "botao-primario",
          disabled: !pronto,
          text: CONSULTA.enviando ? "executando…" : "Enviar consulta",
          onclick: () => envia(redesenha),
        }),
      ]),

      CONSULTA.enviando
        ? el("div", { class: "consulta-executando" }, [
            el("span", { class: "pulso", "aria-hidden": "true" }),
            el("span", {}, [
              el("strong", { text: "O agente está investigando. " }),
              "Leva alguns segundos e consome cota de LLM" +
                (form.julgar ? ", mais o gerador do gabarito e o comitê de juízes." : "."),
            ]),
          ])
        : null,
    ])
  );
}

/* Seletor de modelo por dimensão do comitê.
 *
 * Recolhido por padrão: quem só quer a resposta não precisa decidir isso, e o padrão do
 * `.env` já funciona. Aberto, mostra as três dimensões porque elas medem coisas
 * diferentes — `causa_raiz` é raciocínio técnico sobre limiares e espectro,
 * `honestidade` é leitura de hedge no texto — e entre modelos gratuitos a competência
 * varia muito de uma para outra. Trocar uma sem mexer nas outras é o ponto.
 *
 * Só OpenRouter: o juiz nunca roda no provedor dos agentes (Groq). Isso separa as cotas
 * e garante que nenhum juiz coincida com o gerador do gabarito, que é da Groq.
 */
function seletorJuizes(redesenha) {
  const catalogo = CONSULTA.juizes;

  if (!catalogo) {
    return el("div", { class: "consulta-juizes-config" }, [
      el("span", {
        class: "secao-nota",
        text:
          "Não foi possível listar os modelos do OpenRouter agora — a avaliação usará os " +
          "modelos padrão do agent/.env.",
      }),
    ]);
  }

  const trocadas = Object.keys(CONSULTA.modelosJuizes).length;
  const cabeca = el("button", {
    class: "consulta-disclosure",
    "aria-expanded": String(CONSULTA.mostrarJuizes),
    onclick: () => {
      CONSULTA.mostrarJuizes = !CONSULTA.mostrarJuizes;
      redesenha();
    },
    text: `${CONSULTA.mostrarJuizes ? "▾" : "▸"} Modelos do comitê de juízes${
      trocadas ? ` — ${trocadas} alterado${trocadas > 1 ? "s" : ""}` : ""
    }`,
  });

  if (!CONSULTA.mostrarJuizes) {
    return el("div", { class: "consulta-juizes-config" }, [cabeca]);
  }

  const semChave = catalogo.chave_configurada === false;

  return el("div", { class: "consulta-juizes-config aberta" }, [
    cabeca,
    el("p", { class: "secao-nota" }, [
      `Juiz roda sempre no OpenRouter (${catalogo.modelos.length} modelos gratuitos`,
      catalogo.origem === "api" ? ", listados agora" : ", lista local — API indisponível",
      "); os agentes seguem na Groq.",
    ]),
    semChave
      ? aviso("atencao", [
          el("strong", { text: "Sem chave do OpenRouter. " }),
          "Defina JUDGE_API_KEY em agent/.env para que o comitê possa rodar.",
        ])
      : null,
    el("div", { class: "consulta-juizes-grade" },
      catalogo.dimensoes.map((dim) =>
        el("label", { class: "consulta-campo" }, [
          el("span", { text: dim.titulo }),
          el(
            "select",
            {
              onchange: (ev) => {
                const valor = ev.target.value;
                // Voltar ao padrão remove a chave, em vez de gravar o id do padrão:
                // assim uma troca posterior do .env passa a valer sem reabrir a aba.
                if (valor) CONSULTA.modelosJuizes[dim.chave] = valor;
                else delete CONSULTA.modelosJuizes[dim.chave];
                redesenha();
              },
            },
            [
              el("option", {
                value: "",
                text: `padrão — ${dim.padrao}`,
                selected: !CONSULTA.modelosJuizes[dim.chave],
              }),
              ...catalogo.modelos.map((m) =>
                el("option", {
                  value: m.id,
                  text: m.descricao ? `${m.id} · ${m.descricao}` : m.id,
                  selected: CONSULTA.modelosJuizes[dim.chave] === m.id,
                })
              ),
            ]
          ),
        ])
      )
    ),
    trocadas
      ? el("button", {
          class: "consulta-link-btn",
          text: "restaurar os padrões",
          onclick: () => {
            CONSULTA.modelosJuizes = {};
            redesenha();
          },
        })
      : null,
  ]);
}

function campo(rotulo, controle) {
  return el("label", { class: "consulta-campo" }, [
    el("span", { text: rotulo }),
    controle,
  ]);
}

function fichaPermissoes(usuario) {
  const permissoes = usuario.permissions || [];
  return el("div", { class: "consulta-permissoes" }, [
    el("div", { class: "consulta-permissoes-topo" }, [
      el("span", { class: "rotulo-cru", text: "permissões deste usuário" }),
      el("span", { class: "permissoes" },
        permissoes.length
          ? permissoes.map((p) => selo(p, "quieto", { class: "selo selo-quieto mono" }))
          : [selo("nenhuma", "atencao")]
      ),
    ]),
    el("p", {
      class: "consulta-permissoes-nota",
      text: "O agente só executa o que elas autorizam. Um 403 na trajetória é resultado, não falha.",
    }),
  ]);
}

/* -- resultado ---------------------------------------------------------- */

function resultado(registro) {
  const trace = registro.trace || {};
  const avaliacao = registro.avaliacao || {};

  return el("div", {}, [
    secao(
      "Resposta do agente",
      `${registro.id} · ${trace.ticket_id || ""}`,
      el("div", {}, [
        el("div", { class: "chamado-topo" }, [
          seloDecisao(trace.decision),
          el("span", { class: "secao-nota", text: `${(trace.steps || []).length} chamadas · ${num((trace.token_usage || {}).total_tokens)} tokens` }),
        ]),
        // Sem resposta final o bloco de leitura viraria uma caixa grande com "não
        // determinado" dentro: a ausência é dita em tom de ausência, não emoldurada.
        (trace.final_answer || "").trim()
          ? el("div", { class: "mensagem", text: trace.final_answer })
          : el("p", {
              class: "consulta-sem-resposta",
              text: "A execução não produziu resposta final.",
            }),
        el("dl", { class: "campos" }, [
          el("dt", { text: "justificativa" }),
          el("dd", { text: texto(trace.justification) }),
          el("dt", { text: "parada" }),
          el("dd", { text: texto(trace.stop_reason) }),
        ]),
        trace.error ? blocoErroExecucao(trace.error) : null,
      ])
    ),

    secao(
      "Trajetória",
      "As chamadas que o agente fez à API industrial, na ordem.",
      (trace.steps || []).length
        ? el("ul", { class: "consulta-passos" },
            trace.steps.map((passo) =>
              el("li", { class: passo.ok ? "" : "passo-falhou" }, [
                el("code", { text: passo.step }),
                selo(passo.mode || String(passo.status_code), passo.ok ? "quieto" : "erro"),
                passo.from_cache ? selo("repetida", "atencao") : null,
              ])
            )
          )
        : vazio("Nenhuma chamada registrada.")
    ),

    secaoAvaliacao(registro, avaliacao),
  ]);
}

/**
 * Falha de execução com a causa nomeada antes do texto cru do provedor.
 *
 * O erro do provedor chega como uma linha só, com JSON aninhado e link de billing no
 * meio — quem lê precisa decidir se espera, se troca de modelo ou se o agente está
 * quebrado, e essa distinção não sai de um stack trace. A mensagem original continua
 * aí embaixo, recolhida: é ela que serve para depurar.
 */
function blocoErroExecucao(erro) {
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
function diagnosticaErro(bruto) {
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

function secaoAvaliacao(registro, avaliacao) {
  const gabarito = registro.gabarito_sintetico;
  const juizes = avaliacao.juizes;
  const execucao = avaliacao.execucao || {};

  const corpo = el("div", {}, [
    /* O aviso vem ANTES das notas, de propósito: quem lê a nota primeiro já a ancorou
     * antes de chegar à ressalva. */
    aviso("atencao", [
      el("strong", { text: "Métrica sintética, não comparável. " }),
      "Este caso não tem gabarito humano: a questão de referência foi escrita por um LLM " +
        "a partir da mensagem. As notas ordenam consultas livres entre si e não entram nas " +
        "métricas dos cenários com gabarito da Tractian.",
    ]),

    el("dl", { class: "campos" }, [
      el("dt", { text: "camada 1" }),
      el("dd", { text: "não aplicável" }),
      el("dt", { text: "por quê" }),
      el("dd", { text: avaliacao.camada1_motivo || VAZIO }),
      el("dt", { text: "chamadas repetidas" }),
      el("dd", { text: `${num(execucao.chamadas_repetidas)} (${pct(execucao.taxa_repeticao)})` }),
      el("dt", { text: "insistiu após negativa" }),
      el("dd", { text: execucao.insistiu_apos_negativa ? "sim" : "não" }),
    ]),

    gabarito ? blocoGabarito(gabarito) : null,
    registro.erro_gabarito
      ? aviso("erro", [el("strong", { text: "Gabarito não gerado: " }), registro.erro_gabarito])
      : null,
    avaliacao.erro_juiz
      ? aviso("erro", [el("strong", { text: "Juízes não concluíram: " }), avaliacao.erro_juiz])
      : null,
    juizes ? blocoJuizes(juizes) : null,
  ]);

  return secao("Avaliação sintética", "Camada 2-S — gabarito gerado por LLM distinto do juiz.", corpo);
}

function blocoGabarito(gabarito) {
  return el("div", { class: "consulta-gabarito" }, [
    el("h3", { text: "Gabarito sintético" }),
    el("dl", { class: "campos" }, [
      el("dt", { text: "questão de referência" }),
      el("dd", { text: texto(gabarito.root_question) }),
      el("dt", { text: "modo de dados" }),
      el("dd", { text: texto(gabarito.mode) }),
      el("dt", { text: "resoluções aceitas" }),
      el("dd", { text: (gabarito.accepted_decisions || []).join(", ") || VAZIO }),
      el("dt", { text: "por quê" }),
      el("dd", { text: texto(gabarito.rationale) }),
      el("dt", { text: "modelo gerador" }),
      el("dd", { text: texto(gabarito.modelo_gerador) }),
    ]),
  ]);
}

function blocoJuizes(juizes) {
  const linhas = Object.entries(juizes);
  const notas = linhas.map(([, v]) => v.score).filter((n) => typeof n === "number");
  const media = notas.length ? notas.reduce((a, b) => a + b, 0) / notas.length : null;

  // Cada dimensão pode ter sido julgada por um modelo diferente. Se foram, a média das
  // três não tem denominador comum — dizer isso importa mais do que exibir o número.
  const modelos = new Set(linhas.map(([, v]) => v.modelo).filter(Boolean));
  const modelosMistos = modelos.size > 1;

  return el("div", { class: "consulta-juizes" }, [
    el("h3", { text: `Comitê de juízes${media !== null ? ` — média ${media.toFixed(1)}/5` : ""}` }),
    modelosMistos
      ? el("p", {
          class: "secao-nota",
          text:
            "As dimensões foram julgadas por modelos diferentes: a média serve de resumo " +
            "visual, não de medida comparável. Compare dimensão por dimensão.",
        })
      : null,
    ...linhas.map(([dimensao, veredito]) => {
      // "sem nota" é ausência de medida, não nota baixa: cai no tom quieto, nunca em
      // vermelho. Pintar de erro faria a falha de execução parecer mau julgamento.
      const semNota = veredito.score === null || veredito.score === undefined;
      return el("div", { class: "consulta-veredito" }, [
        el("div", { class: "consulta-veredito-topo" }, [
          el("strong", { text: (dimensao || "").replace(/_/g, " ") }),
          semNota
            ? selo("sem nota", "quieto")
            : selo(`${veredito.score}/5`,
                   veredito.score >= 4 ? "sucesso" : veredito.score >= 3 ? "atencao" : "erro"),
          // Procedência ao lado da nota, não em rodapé: é o que a torna interpretável.
          veredito.modelo ? el("code", { class: "consulta-modelo", text: veredito.modelo }) : null,
        ]),
        el("p", { class: "secao-nota", text: texto(veredito.reasoning) }),
      ]);
    }),
  ]);
}

/* -- histórico ---------------------------------------------------------- */

function historico(redesenha) {
  return secao(
    "Consultas anteriores",
    `${CONSULTA.historico.length} registradas em evaluation/results/consultas/`,
    el("ul", { class: "consulta-historico" },
      CONSULTA.historico.slice(0, 20).map((registro) => {
        const trace = registro.trace || {};
        return el("li", {}, [
          el("button", {
            class: "consulta-historico-item",
            onclick: () => {
              CONSULTA.resultado = registro;
              redesenha();
              window.scrollTo({ top: 0, behavior: "smooth" });
            },
          }, [
            el("code", { text: registro.id }),
            el("span", { text: (registro.entrada || {}).mensagem?.slice(0, 70) || "" }),
            selo((DECISOES[trace.decision] || {}).texto || "sem decisão",
                 (DECISOES[trace.decision] || {}).tom || "quieto"),
          ]),
        ]);
      })
    )
  );
}
