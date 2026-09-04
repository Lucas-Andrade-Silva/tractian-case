/* Aba Operação — o atendimento como quem responde o chamado o veria.
 *
 * REGRA INEGOCIÁVEL (RN-01): esta tela nunca exibe gabarito, decisão aceita ou status de
 * aprovação. Nem em texto, nem em cor, nem em tooltip. A separação agente/avaliação é o
 * que dá sentido à Parte 2 do projeto; se a visão de operação for construída sobre o
 * gabarito, ela deixa de ser a visão de quem atende.
 *
 * A regra é estrutural, não disciplina: este módulo lê apenas `execucao.operacao`, e não
 * importa nada de `avaliacao.js`. Dá para verificar por leitura de import. */

import {
  ESTADO, el, limpa, texto, num, pct, duracao, VAZIO,
  STOP_REASON, PAPEIS_PT, filaVisivel, acoesDeImpacto, temAcaoExecutada, rotuloAcao,
} from "./dados.js";
import {
  selo, seloDecisao, seloStatus, metrica, secao, aviso, vazio, blocoCru,
  timeline, legendaTimeline,
} from "./componentes.js";

/* -- fila --------------------------------------------------------------- */

export function desenhaFila(container, redesenha) {
  const bundle = ESTADO.bundle;
  const lista = filaVisivel();
  limpa(container);

  container.append(
    el("div", { class: "filtros" }, [
      el("div", { class: "busca" }, [
        el("input", {
          type: "search",
          placeholder: "Buscar ticket, ativo, empresa ou mensagem",
          value: ESTADO.busca,
          "aria-label": "Buscar",
          oninput: (ev) => {
            ESTADO.busca = ev.target.value;
            redesenha();
          },
        }),
      ]),
      el("div", { class: "filtros-linha" }, [
        seletorFiltro("empresa", "Empresa", bundle.facetas.empresas.map((e) => [e.id, e.id]), redesenha),
        seletorFiltro("ativo", "Ativo", bundle.facetas.ativos.map((a) => [a.id, a.id]), redesenha),
      ]),
      el("div", { class: "filtros-linha" }, [
        seletorFiltro(
          "papel",
          "Papel",
          bundle.facetas.papeis.map((p) => [p.id, PAPEIS_PT[p.id] || p.id]),
          redesenha
        ),
        seletorFiltro("decisao", "Resolução", bundle.facetas.decisoes.map((d) => [d, d]), redesenha),
      ]),
    ]),
    el("div", {
      class: "contagem",
      text: `${lista.length} ${lista.length === 1 ? "chamado" : "chamados"}`,
    })
  );

  const fila = el("div", { class: "fila" });
  if (!lista.length) {
    fila.append(vazio("Nenhum chamado corresponde aos filtros."));
  }

  for (const execucao of lista) {
    const solicitante = execucao.operacao.solicitante || {};
    const acaoExecutada = temAcaoExecutada(execucao);
    fila.append(
      el(
        "button",
        {
          class: "fila-item",
          "aria-current": String(execucao.id === ESTADO.execucaoId),
          onclick: () => {
            ESTADO.execucaoId = execucao.id;
            redesenha();
          },
        },
        [
          el("div", { class: "fila-topo" }, [
            el("span", { class: "ticket", text: execucao.ticket_id }),
            el("span", { class: "cenario", text: execucao.cenario }),
          ]),
          el("div", { class: "fila-meta" }, [
            el("span", { text: execucao.operacao.asset_id || VAZIO }),
            el("span", { class: "sep", text: "·" }),
            el("span", { text: solicitante.company_id || VAZIO }),
          ]),
          el("div", { class: "fila-meta" }, [
            el("span", { text: solicitante.name || VAZIO }),
            el("span", { class: "sep", text: "·" }),
            el("span", { text: PAPEIS_PT[solicitante.role] || solicitante.role || VAZIO }),
          ]),
          el("div", { class: "fila-rodape" }, [
            seloDecisao(execucao.operacao.decisao),
            acaoExecutada
              ? el("span", {
                  class: "marca-acao impacto",
                  title: "Executou ação de impacto na plataforma",
                })
              : null,
          ]),
        ]
      )
    );
  }
  container.append(fila);
}

function seletorFiltro(chave, rotulo, opcoes, redesenha) {
  return el(
    "select",
    {
      "aria-label": rotulo,
      onchange: (ev) => {
        ESTADO.filtros[chave] = ev.target.value;
        redesenha();
      },
    },
    [
      el("option", { value: "", text: rotulo, selected: ESTADO.filtros[chave] === "" }),
      ...opcoes.map(([valor, nome]) =>
        el("option", { value: valor, text: nome, selected: ESTADO.filtros[chave] === valor })
      ),
    ]
  );
}

/* -- detalhe ------------------------------------------------------------ */

export function desenhaDetalhe(container, redesenha) {
  limpa(container);
  const execucao = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.execucaoId);

  if (!execucao) {
    container.append(vazio("Selecione um chamado na fila para ver o atendimento."));
    return;
  }

  const op = execucao.operacao;
  const solicitante = op.solicitante || {};
  const ativo = op.ativo || {};

  container.append(
    el("div", { class: "chamado-topo" }, [
      el("h1", { text: execucao.ticket_id }),
      selo(execucao.cenario, "quieto", { class: "selo selo-quieto mono" }),
      seloDecisao(op.decisao),
      seloStopReason(op.stop_reason),
    ]),
    // O nome do ativo já está na ficha logo abaixo; aqui fica só o que identifica a
    // execução exibida, que é o que o cabeçalho ainda não diz.
    el("div", {
      class: "chamado-sub",
      text: `seed ${execucao.seed} · fase ${execucao.fase}`,
    }),
    // Mensagem íntegra do cliente: é o que foi pedido, sem resumo.
    el("blockquote", { class: "mensagem", text: texto(op.mensagem) }),
    fichas(solicitante, ativo, op),
    secao(
      "Timeline do atendimento",
      "roteamento do Supervisor e chamadas do papel ativo",
      [timeline(execucao, ESTADO, redesenha, ESTADO.bundle), legendaTimeline()]
    ),
    secaoEvidencia(op),
    secaoResolucao(execucao, op, solicitante),
    secaoCusto(op)
  );
}

function seloStopReason(motivo) {
  const info = STOP_REASON[motivo];
  if (!info) return selo(texto(motivo), "quieto");
  return selo(info.texto, info.tom);
}

function fichas(solicitante, ativo, op) {
  const politica = op.modelo && op.modelo._evidence_policy;
  const papeis = Object.entries(op.modelo || {}).filter(([chave]) => !chave.startsWith("_"));

  return el("div", { class: "fichas" }, [
    el("div", { class: "ficha" }, [
      el("h3", { text: "Solicitante" }),
      el("dl", { class: "campos" }, [
        el("dt", { text: "nome" }),
        el("dd", { text: texto(solicitante.name) }),
        el("dt", { text: "cargo" }),
        el("dd", { text: PAPEIS_PT[solicitante.role] || texto(solicitante.role) }),
        el("dt", { text: "empresa" }),
        el("dd", { text: texto(solicitante.company_id) }),
        el("dt", { text: "permissões" }),
        el("dd", {}, [
          el(
            "span",
            { class: "permissoes" },
            (solicitante.permissions || []).length
              ? solicitante.permissions.map((p) => selo(p, "quieto", { class: "selo selo-quieto mono" }))
              : [el("span", { text: "não determinado" })]
          ),
        ]),
      ]),
    ]),
    el("div", { class: "ficha" }, [
      el("h3", { text: "Ativo" }),
      el("dl", { class: "campos" }, [
        el("dt", { text: "id" }),
        el("dd", { text: texto(op.asset_id) }),
        el("dt", { text: "nome" }),
        el("dd", { text: texto(ativo.name) }),
        el("dt", { text: "criticidade" }),
        el("dd", { text: texto(ativo.criticality) }),
        el("dt", { text: "planta / linha" }),
        el("dd", { text: `${texto(ativo.plant)} / ${texto(ativo.line)}` }),
        el("dt", { text: "sensor" }),
        el("dd", { text: texto(ativo.sensor_status) }),
      ]),
    ]),
    el("div", { class: "ficha" }, [
      el("h3", { text: "Configuração da execução" }),
      el("dl", { class: "campos" }, [
        ...papeis.flatMap(([papel, modelo]) => [
          el("dt", { text: papel }),
          el("dd", { text: modelo }),
        ]),
        el("dt", { text: "política de evidência" }),
        el("dd", { text: texto(politica) }),
      ]),
    ]),
  ]);
}

/* -- evidência apurada -------------------------------------------------- */

function secaoEvidencia(op) {
  const achados = op.achados || [];
  const conteudo = achados.length
    ? achados.map((achado) =>
        el("div", { class: "achado-bloco" }, [
          el("h3", { text: achado.agent }),
          el("pre", { text: texto(achado.summary) }),
        ])
      )
    : [vazio("Nenhum papel registrou apuração nesta execução.")];

  return secao(
    "Evidência apurada",
    "o resumo de cada papel — é isto que atravessou para o Decisor",
    conteudo
  );
}

/* -- resolução ---------------------------------------------------------- */

function secaoResolucao(execucao, op, solicitante) {
  const acoes = acoesDeImpacto(execucao);

  const partes = [
    el("div", { class: "resolucao-topo" }, [
      seloDecisao(op.decisao),
      // O que era possível fazer delimita o que era certo fazer (RN-14).
      el("span", { class: "secao-nota", text: "permissões do solicitante:" }),
      ...((solicitante.permissions || []).length
        ? solicitante.permissions.map((p) => selo(p, "quieto", { class: "selo selo-quieto mono" }))
        : [el("span", { class: "secao-nota", text: "não determinado" })]),
    ]),
    el("div", { class: "bloco-rotulado" }, [
      el("div", { class: "rotulo-cru", text: "justificativa" }),
      el("div", { class: "justificativa", text: texto(op.justificativa) }),
    ]),
  ];

  // Ação de impacto e justificativa formam um objeto só — nunca uma sem a outra (RN-13).
  for (const acao of acoes) {
    partes.push(
      el("div", { class: "acao-impacto" }, [
        el("div", { class: "acao-cabeca" }, [
          el("span", { class: `metodo escrita`, text: acao.metodo }),
          el("span", { class: "rota", text: acao.rota }),
          seloStatus(acao, ESTADO.bundle),
          el("span", { class: "secao-nota", text: rotuloAcao(acao) }),
        ]),
        acao.body && acao.body.justification
          ? el("div", { class: "bloco-rotulado" }, [
              el("div", { class: "rotulo-cru", text: "justificativa enviada com a ação" }),
              el("div", { class: "justificativa", text: acao.body.justification }),
            ])
          : aviso("atencao", "Ação executada sem justificativa registrada no corpo da requisição."),
        // O corpo cru só acrescenta algo quando leva mais que a justificativa — que já
        // está acima, redigida. Na maioria das ações ele é só `{justification: ...}`, e
        // exibi-lo repetiria o mesmo texto duas vezes na mesma tela.
        acao.body && Object.keys(acao.body).some((k) => k !== "justification")
          ? blocoCru("alterações enviadas", omitir(acao.body, "justification"))
          : null,
        acao.response ? blocoCru("resultado", acao.response) : null,
      ])
    );
  }

  // A resposta ao cliente é o produto entregue: íntegra, sem truncar (RN-16).
  partes.push(
    el("div", { class: "bloco-rotulado" }, [
      el("div", { class: "rotulo-cru", text: "resposta final ao cliente" }),
      el("div", { class: "resposta-final", html: markdownSimples(op.resposta_final) }),
    ])
  );

  if (op.erro) {
    partes.push(aviso("atencao", [el("strong", { text: "Falha de execução: " }), texto(op.erro)]));
  }

  return secao("Resolução", null, el("div", { class: "resolucao" }, partes));
}

/** Copia um objeto sem as chaves indicadas. */
function omitir(objeto, ...chaves) {
  return Object.fromEntries(Object.entries(objeto).filter(([k]) => !chaves.includes(k)));
}

/** Markdown mínimo (negrito e código) que os modelos usam na resposta ao cliente.
 *  Escapa antes de formatar — o texto vem de um LLM, não é HTML confiável. */
function markdownSimples(bruto) {
  if (!bruto || !String(bruto).trim()) return "não determinado";
  return String(bruto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/* -- custo -------------------------------------------------------------- */

function secaoCusto(op) {
  const consumo = op.consumo || {};
  const porPapel = consumo.by_agent || {};
  const chamadasApi = op.timeline.filter((e) => e.tipo === "chamada").length;

  // A tabela responde "quem gastou", não "quanto no total" — esse número já está no
  // cartão acima. Repetir entrada/saída/total por papel triplicava a mesma leitura; a
  // fatia de cada papel no total é o que a divisão de papéis torna interessante.
  const totalGeral = consumo.total_tokens || 0;
  const tabela = el("table", { class: "tabela-papeis" }, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { text: "papel" }),
        el("th", { text: "chamadas" }),
        el("th", { text: "tokens" }),
        el("th", { text: "do total" }),
      ]),
    ]),
    el(
      "tbody",
      {},
      Object.entries(porPapel)
        .sort((a, b) => b[1].total_tokens - a[1].total_tokens)
        .map(([papel, uso]) =>
          el("tr", {}, [
            el("td", { text: papel }),
            el("td", { text: num(uso.calls) }),
            el("td", { text: num(uso.total_tokens) }),
            el("td", {
              text: totalGeral ? pct(uso.total_tokens / totalGeral, 0) : VAZIO,
            }),
          ])
        )
    ),
  ]);

  // Papel com tools entra em laço (chama, recebe, reavalia); o Decisor não tem tools e
  // por isso fecha em uma chamada só. Explicar a assimetria evita ler a linha dele como
  // subutilização — é o desenho que a mantém barata.
  const decisor = porPapel.decisor;
  const nota =
    decisor && decisor.calls === 1
      ? "O Decisor fecha em uma única chamada porque não tem tools: decide sobre a " +
        "evidência já apurada, sem laço de consulta (ADR 0002)."
      : null;

  return secao("Custo do atendimento", null, [
    el("div", { class: "metricas" }, [
      metrica("Tokens de entrada", num(consumo.input_tokens)),
      metrica("Tokens de saída", num(consumo.output_tokens)),
      metrica("Total", num(consumo.total_tokens)),
      metrica("Chamadas de API", num(chamadasApi)),
      metrica("Chamadas de LLM", num(consumo.llm_calls)),
      metrica("Duração", duracao(op.duracao_ms)),
    ]),
    Object.keys(porPapel).length ? tabela : vazio("Consumo por papel não registrado."),
    nota ? el("div", { class: "secao-nota", style: "margin-top:8px" }, [nota]) : null,
  ]);
}
