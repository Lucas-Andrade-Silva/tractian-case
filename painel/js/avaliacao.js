/* Aba Avaliação — o desempenho como quem mede o agente o veria.
 *
 * Cada tela aqui carrega uma regra de leitura que o número sozinho não transmite:
 * escalar não é falha, cenário ambíguo aceita mais de um desfecho, reprovação com decisão
 * certa costuma ser artefato de gabarito, e ausência de medida não é zero. As ressalvas
 * ficam ao lado do número, não em nota de rodapé — um painel que mostra a métrica sem a
 * ressalva é menos verdadeiro que o CSV de onde ela veio. */

import {
  ESTADO, el, limpa, texto, num, pct, VAZIO, PAPEIS_PT, DECISOES,
  execucoesDaFase, achaExecucao, acoesDeImpacto, rotuloAcao,
} from "./dados.js";
import { selo, seloDecisao, metrica, secao, aviso, vazio, blocoCru } from "./componentes.js";
import { exportaCsv } from "./export.js";

const SEEDS = ["complete", "s2", "s3"];

export function desenhaAvaliacao(container, redesenha) {
  limpa(container);
  const bundle = ESTADO.bundle;
  const fase = ESTADO.fase;

  container.append(
    placar(bundle, fase),
    matriz(bundle, fase, redesenha),
    drilldown(bundle, redesenha),
    comparativo(bundle),
    estabilidade(bundle, fase),
    juizes(bundle, fase),
    auditoria(bundle, fase)
  );
}

/* -- 1. placar geral ---------------------------------------------------- */

function placar(bundle, fase) {
  const ag = bundle.agregados[fase];
  const casos = bundle.casos.filter((c) => c.por_fase[fase]);
  const medivel = casos.filter((c) => c.por_fase[fase].estabilidade.medivel);
  const estaveis = medivel.filter((c) => c.por_fase[fase].estabilidade.estavel === true);

  const partes = [
    el("div", { class: "metricas" }, [
      metrica("Acurácia de decisão", pct(ag.acuracia_decisao), `${ag.execucoes} execuções`),
      metrica("Taxa de aprovação", pct(ag.taxa_aprovacao), "critério determinístico"),
      metrica(
        "Cenários estáveis",
        medivel.length ? `${estaveis.length}/${medivel.length}` : VAZIO,
        medivel.length < casos.length
          ? `${casos.length - medivel.length} não-medível`
          : "todos medíveis"
      ),
      metrica("Custo médio por caso", num(ag.tokens_medio), "tokens totais"),
      metrica("Recall de evidência", pct(ag.recall_medio), "médio"),
      metrica("Chamadas por caso", num(ag.chamadas_media, 1), "média"),
    ]),
  ];

  // Falha de execução é categoria própria: não pode contaminar a acurácia (RN-04).
  if (ag.falhas_execucao > 0) {
    partes.unshift(
      aviso("atencao", [
        el("strong", { text: `${ag.falhas_execucao} de ${ag.execucoes} execuções falharam. ` }),
        "As taxas acima cobrem apenas as execuções que concluíram — falha de execução é " +
          "categoria própria e não conta como decisão errada.",
      ])
    );
  }

  return secao(
    `Placar — ${fase}`,
    "taxas calculadas apenas sobre execuções que concluíram",
    partes
  );
}

/* -- 2. matriz cenários × seeds ----------------------------------------- */

/** Tom da célula pelas quatro categorias. Escalar nunca é vermelho (RN-10);
 *  reprovação com decisão certa é atenção, não erro, porque costuma ser artefato. */
function tomDaCelula(execucao) {
  const av = execucao.avaliacao;
  if (!av.executou_sem_erro) return "atencao";
  if (av.passou) return execucao.operacao.decisao === "escalar" ? "neutro" : "sucesso";
  if (av.decision_match) return "atencao";
  return "erro";
}

function matriz(bundle, fase, redesenha) {
  const casos = bundle.casos;

  const corpo = casos.map((caso) =>
    el("tr", {}, [
      el("th", { scope: "row" }, [
        el("span", { class: "tk", text: caso.ticket_id }),
        el("span", { class: "cn", text: caso.cenario }),
      ]),
      ...SEEDS.map((seed) => {
        const execucao = achaExecucao(caso.case_id, seed, fase);
        if (!execucao) {
          // Célula sem execução é "não executado" — vazio não é reprovação (RN-02).
          return el("td", {}, [
            el("span", { class: "celula cel-ausente", text: "não executado" }),
          ]);
        }
        const av = execucao.avaliacao;
        const tom = tomDaCelula(execucao);
        return el("td", {}, [
          el(
            "button",
            {
              class: `celula cel-${tom}`,
              "aria-current": String(ESTADO.celulaId === execucao.id),
              onclick: () => {
                ESTADO.celulaId = execucao.id;
                redesenha();
              },
            },
            [
              el("span", { class: "dec", text: execucao.operacao.decisao || "sem decisão" }),
              el("br"),
              el("span", {
                class: "est",
                text: !av.executou_sem_erro
                  ? "falha de execução"
                  : av.passou
                  ? "aprovado"
                  : av.decision_match
                  ? "reprovado — ação"
                  : "decisão fora do aceito",
              }),
            ]
          ),
        ]);
      }),
    ])
  );

  const tabela = el("table", { class: "matriz" }, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { scope: "col", text: "cenário" }),
        ...SEEDS.map((s) => el("th", { scope: "col", text: s })),
      ]),
    ]),
    el("tbody", {}, corpo),
  ]);

  const legenda = el("div", { class: "legenda-cores" }, [
    amostra("cel-sucesso", "aprovado"),
    amostra("cel-neutro", "aprovado, resolveu escalando"),
    amostra("cel-atencao", "decisão aceita, mas reprovado por ação — ver a causa"),
    amostra("cel-erro", "decisão fora do conjunto aceito"),
    amostra("cel-ausente", "não executado nesta fase"),
  ]);

  return secao(
    `Cenários × seeds — ${fase}`,
    "clique numa célula para o diff da trajetória",
    [el("div", { class: "matriz-envolve" }, [tabela]), legenda]
  );
}

function amostra(classe, rotulo) {
  return el("span", {}, [el("i", { class: `amostra ${classe}` }), el("span", { text: rotulo })]);
}

/* -- 3. drill-down: diff expected × taken -------------------------------- */

/**
 * Consulta faltante que foi atendida por rota equivalente.
 * `GET /analyses/an_9906` e `GET /assets/asset_C710/analyses` acham o mesmo dado por
 * caminhos diferentes — bater string de rota não é medir qualidade (RN-24).
 */
function rotaEquivalente(faltante, extras) {
  const analise = /^GET \/analyses\/([a-z0-9_]+)$/i.exec(faltante);
  if (analise) {
    const porAtivo = extras.find((e) => /^GET \/assets\/[a-z0-9_]+\/analyses/i.test(e));
    if (porAtivo) return porAtivo;
  }
  const doAtivo = /^GET \/assets\/([a-z0-9_]+)\/analyses/i.exec(faltante);
  if (doAtivo) {
    const direta = extras.find((e) => /^GET \/analyses\/[a-z0-9_]+$/i.test(e));
    if (direta) return direta;
  }
  // Mesma rota com query diferente: a evidência foi buscada, com outro recorte.
  const base = faltante.split("?")[0];
  const comQuery = extras.find((e) => e.split("?")[0] === base);
  return comQuery || null;
}

function drilldown(bundle, redesenha) {
  const execucao = bundle.execucoes.find((e) => e.id === ESTADO.celulaId);
  if (!execucao) return el("div");

  const av = execucao.avaliacao;
  const extras = av.queries_extras || [];

  const atendidas = av.diff_trajetoria.filter((d) => d.situacao === "atendida");
  const faltantes = av.diff_trajetoria.filter((d) => d.situacao === "faltante");
  const sobrando = av.diff_trajetoria.filter((d) => d.situacao === "extra");

  const partes = [
    el("div", { class: "drill-cabeca" }, [
      el("h3", { text: `${execucao.ticket_id} · seed ${execucao.seed} · ${execucao.fase}` }),
      seloDecisao(execucao.operacao.decisao),
      selo(
        `aceitas: ${av.decisoes_aceitas.join(" ou ")}`,
        av.decision_match ? "sucesso" : "erro"
      ),
      av.cenario_ambiguo
        ? selo("cenário ambíguo", "neutro", {
            title: "O cenário aceita mais de uma resolução; escolher qualquer uma delas é acerto.",
          })
        : null,
    ]),
  ];

  // Cenário ambíguo: a escolha entre desfechos aceitos não é divergência (RN-20).
  if (av.cenario_ambiguo && av.decision_match) {
    partes.push(
      aviso("neutro", [
        el("strong", { text: "Cenário com mais de um desfecho correto. " }),
        `Aceita ${av.decisoes_aceitas.join(" e ")}; o agente escolheu ${execucao.operacao.decisao}. ` +
          "A escolha entre resoluções aceitas não é penalizada.",
      ])
    );
  }

  // passou=False com decision_match=True precisa exibir a causa (RN-23).
  if (!av.passou && av.decision_match && av.executou_sem_erro) {
    const causa = av.acoes_faltantes.length
      ? `ação exigida não executada: ${av.acoes_faltantes.join(", ")}`
      : av.acoes_nao_previstas.length
      ? `ação não prevista executada: ${av.acoes_nao_previstas.join(", ")}`
      : "causa não determinada";
    partes.push(
      aviso("atencao", [
        el("strong", { text: "Reprovado com a decisão certa. " }),
        `Causa: ${causa}. `,
        av.acoes_nao_previstas.length
          ? "Atenção: em vários casos o gabarito estruturado não documenta um POST que o " +
            "cenário narrativo prescreve — nesses casos a reprovação é artefato do " +
            "gabarito, não erro do agente (limitação conhecida)."
          : "",
      ])
    );
  }

  const grupo = (titulo, linhas, classe, sinal, nota) =>
    el("div", {}, [
      el("h3", { text: `${titulo} (${linhas.length})` }),
      nota ? el("div", { class: "secao-nota", text: nota }) : null,
      linhas.length
        ? el(
            "div",
            { class: "diff" },
            linhas.map((linha) => {
              const equivalente =
                linha.situacao === "faltante" ? rotaEquivalente(linha.step, extras) : null;
              return el("div", { class: `diff-linha ${equivalente ? "d-equivalente" : classe}` }, [
                el("span", { class: "diff-sinal", text: equivalente ? "≈" : sinal }),
                el("span", { text: linha.step }),
                el("span", {
                  class: "diff-nota",
                  text: equivalente ? `coberta por ${equivalente}` : linha.nota || "",
                }),
              ]);
            })
          )
        : el("div", { class: "secao-nota", text: "nenhuma" }),
    ]);

  partes.push(
    el("div", { class: "grupos-diff" }, [
      grupo("Consultas atendidas", atendidas, "d-atendida", "✓"),
      grupo(
        "Consultas faltantes",
        faltantes,
        "d-faltante",
        "−",
        "As marcadas com ≈ foram cobertas por uma rota equivalente."
      ),
      grupo(
        "Consultas extras",
        sobrando,
        "d-extra",
        "+",
        "Consulta fora da trajetória de referência não reprova."
      ),
    ]),
    el("div", { class: "metricas", style: "margin-top:16px" }, [
      // O detalhe precisa ser a conta do próprio recall (atendidas ÷ esperadas). Usar
      // gets_feitos aqui mostrava "3 de 4" ao lado de 50%, dois números para a mesma ideia.
      metrica(
        "Recall de evidência",
        pct(av.evidence_recall),
        `${atendidas.length} de ${av.gets_esperados} consultas do gabarito`
      ),
      metrica("Precisão de consultas", pct(av.precisao_consultas), "derivada"),
      metrica("Chamadas de API", num(av.chamadas_api), `${av.chamadas_repetidas} repetidas`),
      metrica("Erros HTTP", num(av.erros_http)),
    ]),
    // A métrica derivada precisa se declarar como tal (RN-06).
    el("div", { class: "secao-nota", style: "margin-top:8px" }, [
      "Precisão de consultas é métrica derivada por mim, não calculada pelo código da " +
        "avaliação: (GETs feitos − extras) / GETs feitos, sem contar GET /users/me. " +
        "Valor baixo não é necessariamente ruim — a política de evidência “fixed” sempre " +
        "apura os quatro pilares, independentemente do que o gabarito daquele caso documentou.",
    ])
  );

  return el("div", { class: "drill" }, partes);
}

/* -- 4. comparativo baseline × pós-correção ----------------------------- */

function comparativo(bundle) {
  const partes = [];

  // Comparar fases só é válido com a mesma configuração de modelos por papel (RN-26).
  if (bundle.meta.config_diverge_entre_fases) {
    partes.push(
      aviso("atencao", [
        el("strong", { text: "Configuração de modelos diverge entre as fases. " }),
        "A comparação abaixo não isola o efeito das correções: parte da diferença pode vir " +
          "da troca de modelo por papel.",
      ])
    );
  } else {
    partes.push(
      aviso("neutro", [
        el("strong", { text: "Mesma configuração de modelos nas duas fases. " }),
        "A comparação isola o efeito das correções de prompt e política.",
      ])
    );
  }

  const linhas = bundle.casos.map((caso) => {
    const base = caso.por_fase["baseline"];
    const pos = caso.por_fase["pos-correcao"];
    // Comparação é sobre execuções que concluíram: uma falha de execução não é uma
    // decisão pior, e dividir por células que quebraram inventaria uma piora.
    const taxa = (f) => (f && f.validas ? f.aprovadas / f.validas : null);
    const tBase = taxa(base);
    const tPos = taxa(pos);

    let delta;
    if (!pos || !pos.validas) {
      delta = el("span", { class: "delta-igual", text: "sem execução válida na pós-correção" });
    } else if (tBase === null) {
      delta = el("span", { class: "delta-igual", text: "sem base de comparação" });
    } else if (pos.validas !== base.validas) {
      // Bases diferentes: declarar em vez de comparar taxas apuradas sobre amostras
      // de tamanhos distintos.
      delta = el("span", {
        class: "delta-igual",
        text: `bases diferentes (${pos.validas} × ${base.validas} execuções válidas)`,
      });
    } else if (tPos > tBase) {
      delta = el("span", { class: "delta-melhora", text: `melhorou +${pct(tPos - tBase, 0)}` });
    } else if (tPos < tBase) {
      delta = el("span", { class: "delta-piora", text: `regrediu −${pct(tBase - tPos, 0)}` });
    } else {
      delta = el("span", { class: "delta-igual", text: "sem mudança" });
    }

    const celula = (f) =>
      !f
        ? VAZIO
        : f.validas
        ? `${f.aprovadas}/${f.validas}` + (f.validas < f.execucoes ? ` (${f.execucoes - f.validas} falha)` : "")
        : `— (${f.execucoes} falha de execução)`;

    return el("tr", {}, [
      el("td", {}, [
        el("span", { class: "tk", text: caso.ticket_id }),
        el("span", { class: "cn", text: ` ${caso.cenario}` }),
      ]),
      el("td", { class: "num", text: celula(base) }),
      el("td", { class: "num", text: celula(pos) }),
      el("td", {}, [delta]),
    ]);
  });

  const semPos = bundle.casos.filter(
    (c) => !c.por_fase["pos-correcao"] || !c.por_fase["pos-correcao"].validas
  );
  partes.push(
    el("table", { class: "comparativo" }, [
      el("thead", {}, [
        el("tr", {}, [
          el("th", { text: "cenário" }),
          el("th", { text: "baseline" }),
          el("th", { text: "pós-correção" }),
          el("th", { text: "efeito" }),
        ]),
      ]),
      el("tbody", {}, linhas),
    ])
  );

  if (semPos.length) {
    partes.push(
      el("div", { class: "secao-nota", style: "margin-top:10px" }, [
        `${semPos.length} de ${bundle.casos.length} cenários não têm execução válida na ` +
          `pós-correção (${semPos.map((c) => c.ticket_id).join(", ")}): a reexecução esbarrou ` +
          "no teto diário de tokens do provedor. São falhas de execução, não decisões — " +
          "por isso ficam fora das taxas. Rode `python painel/completar_fase.py " +
          "--fase pos-correcao` quando a cota renovar para fechá-los.",
      ])
    );
  }

  return secao("Baseline × pós-correção", "aprovações por cenário", partes);
}

/* -- 5. estabilidade ---------------------------------------------------- */

function estabilidade(bundle, fase) {
  const linhas = bundle.casos
    .filter((caso) => caso.por_fase[fase])
    .map((caso) => {
      const est = caso.por_fase[fase].estabilidade;

      // Zero execuções válidas nunca é "estável": é não-medível (RN-03).
      let veredito;
      if (!est.medivel) {
        veredito = selo("não-medível", "atencao", {
          title: "Nenhuma execução concluiu. Sem decisão não há o que comparar.",
        });
      } else if (est.estavel) {
        veredito = selo("estável", "sucesso");
      } else if (est.dentro_do_aceito) {
        // Divergiu, mas dentro do conjunto aceito: instabilidade benigna (RN-22).
        veredito = selo("varia dentro do aceito", "neutro", {
          title: `Alterna entre ${est.decisoes_distintas.join(" e ")}, ambas aceitas pelo cenário.`,
        });
      } else {
        veredito = selo("instável", "erro", {
          title: "Alguma decisão está fora do conjunto aceito pelo cenário.",
        });
      }

      return el("div", { class: "linha-caso" }, [
        el("div", { class: "ident" }, [
          el("div", {}, [el("span", { class: "tk", text: caso.ticket_id })]),
          el("div", {}, [el("span", { class: "cn", text: caso.cenario })]),
        ]),
        el(
          "div",
          { class: "seeds-lado" },
          SEEDS.map((seed) => {
            const execucao = achaExecucao(caso.case_id, seed, fase);
            return el("div", { class: "seed-caixa" }, [
              el("div", { class: "s", text: seed }),
              el("div", {
                class: "d",
                text: execucao ? execucao.operacao.decisao || "sem decisão" : "não executado",
              }),
            ]);
          })
        ),
        el("div", {}, [
          veredito,
          el("div", {
            class: "secao-nota",
            style: "margin-top:4px;text-align:right",
            text: `variação de trajetória ${pct(est.variacao_trajetoria, 0)}`,
          }),
        ]),
      ]);
    });

  // O subtítulo diz o critério; o aviso explica por que a trajetória fica de fora. São
  // duas informações diferentes — repetir "divergência da decisão final" nos dois só
  // ocuparia espaço.
  return secao(
    `Estabilidade entre seeds — ${fase}`,
    "as 3 seeds lado a lado, com o veredito de cada caso",
    [
      aviso("neutro", [
        "Instabilidade é divergência da decisão final, e só dela. Variar a trajetória " +
          "entre seeds é esperado: investigar em ordens diferentes e concluir o mesmo é " +
          "comportamento correto, então a variação aparece ao lado como informação, não " +
          "como penalidade.",
      ]),
      ...(linhas.length ? linhas : [vazio("Nenhum caso executado nesta fase.")]),
    ]
  );
}

/* -- 6. comitê de juízes ------------------------------------------------ */

const RUBRICAS = {
  honestidade:
    "Declara o que não pôde ser determinado, sem inventar valor, insight ou histórico. " +
    "Dizer “não foi possível determinar X” quando de fato não foi apurado é comportamento correto.",
  causa_raiz:
    "Identifica a causa-raiz correta e a sustenta na evidência concreta apurada — estados, " +
    "métricas e limiares, não afirmações genéricas.",
  justificativa:
    "Justificativa ancorada em evidência específica do caso, sustentando exatamente a " +
    "resolução tomada. Escalar um caso resolvível remotamente é erro, não cautela.",
};

function juizes(bundle, fase) {
  const meta = bundle.meta;
  const resumo = meta.juizes_resumo || {};

  // Aviso permanente: média de juiz não validado não é verdade (RN-05).
  const partes = [
    aviso("atencao", [
      el("strong", { text: "Camada 2 não calibrada. " }),
      "As notas do comitê só passam a ser leitura válida depois da calibração manual " +
        "contra um conjunto anotado por humano. Enquanto isso não for feito, média de juiz " +
        "não validado não é verdade — este aviso permanece mesmo quando houver notas.",
    ]),
  ];

  if (!meta.juizes_disponiveis) {
    partes.push(
      aviso("neutro", [
        el("strong", { text: "Sem execuções julgadas. " }),
        meta.juizes_motivo,
        el("div", { class: "rotulo-cru", style: "margin-top:8px" }, [
          "python painel/julgar.py --limite 1        (julga a próxima pendente)",
        ]),
        el("div", { class: "rotulo-cru" }, [
          "python painel/julgar.py --modelos         (modelos gratuitos disponíveis)",
        ]),
      ])
    );
  } else {
    partes.push(
      el("div", { class: "secao-nota", style: "margin-bottom:12px" }, [
        `${meta.juizes_julgadas} de ${meta.juizes_elegiveis} execuções elegíveis julgadas` +
          (meta.juizes_modelo ? ` · juiz: ${meta.juizes_modelo}` : "") +
          ". Execuções que quebraram não vão a julgamento: nota baixa ali seria lida como " +
          "má decisão do agente, não como falha de execução.",
      ])
    );
  }

  partes.push(
    el(
      "div",
      { class: "dimensoes" },
      meta.comite.map((dimensao) => {
        const nota = resumo[dimensao.chave] || {};
        const media = nota.media;
        return el("div", { class: "dimensao" }, [
          el("div", {}, [
            el("h3", { text: dimensao.titulo }),
            el("div", { class: "rubrica", text: RUBRICAS[dimensao.chave] || "" }),
          ]),
          el("div", { style: "text-align:right" }, [
            media === null || media === undefined
              ? el("div", { class: "nota-vazia", text: VAZIO })
              : el("div", { class: "metrica" }, [
                  el("div", { class: "valor", text: `${media.toFixed(1)}` }),
                  el("div", { class: "detalhe", text: `de 5 · n=${nota.julgadas}` }),
                ]),
          ]),
        ]);
      })
    )
  );

  // Notas por execução da fase, com o raciocínio que sustentou cada uma.
  const julgadas = execucoesDaFase(fase).filter((e) => e.avaliacao.juizes);
  if (julgadas.length) {
    partes.push(
      el("div", { style: "margin-top:20px" }, [
        el("h3", { text: `Vereditos desta fase (${julgadas.length})` }),
        ...julgadas.map((execucao) =>
          el("div", { class: "auditoria-item" }, [
            el("div", { class: "auditoria-cabeca" }, [
              el("span", { class: "rota", text: execucao.ticket_id }),
              el("span", { class: "secao-nota", text: execucao.seed }),
            ]),
            // O selo da nota É o botão que abre o raciocínio: separar "dimensão: nota" de
            // um link "ver por quê" imprimiria o nome da dimensão duas vezes na mesma
            // linha. Aberto por padrão, o texto do juiz tem parágrafos e enterraria as
            // notas — então fica sob demanda, com a nota sempre visível.
            el("div", { class: "vereditos-linha" }, meta.comite.map((d) => {
              const veredito = execucao.avaliacao.juizes[d.chave] || {};
              const nota = veredito.score;
              const tom =
                nota === null || nota === undefined
                  ? "quieto"
                  : nota >= 4
                  ? "sucesso"
                  : nota === 3
                  ? "neutro"
                  : "atencao";
              const rotulo = `${d.chave}: ${nota ?? VAZIO}`;
              if (!veredito.reasoning) return selo(rotulo, tom);
              return el("details", { class: "veredito" }, [
                el("summary", {}, [selo(rotulo, tom)]),
                el("div", { class: "auditoria-just", text: veredito.reasoning }),
              ]);
            })),
          ])
        ),
      ])
    );
  }

  return secao(
    "Comitê de juízes",
    "três dimensões independentes, rubrica de 1 a 5, raciocínio antes da nota",
    partes
  );
}

/* -- 7. auditoria e desperdício ----------------------------------------- */

function auditoria(bundle, fase) {
  const execucoes = execucoesDaFase(fase);
  const ag = bundle.agregados[fase];

  // Toda ação de impacto executada na bateria, com a justificativa que a acompanhou.
  const acoes = [];
  for (const execucao of execucoes) {
    for (const acao of acoesDeImpacto(execucao)) {
      acoes.push({ execucao, acao });
    }
  }
  const executadas = acoes.filter(({ acao }) => acao.ok);
  const recusadas = acoes.filter(({ acao }) => !acao.ok);

  const totalChamadas = execucoes.reduce((s, e) => s + (e.avaliacao.chamadas_api || 0), 0);
  const repetidas = execucoes.reduce((s, e) => s + (e.avaliacao.chamadas_repetidas || 0), 0);
  const doCache = execucoes.reduce(
    (s, e) => s + e.operacao.timeline.filter((t) => t.tipo === "chamada" && t.do_cache).length,
    0
  );
  const errosHttp = execucoes.reduce((s, e) => s + (e.avaliacao.erros_http || 0), 0);

  const listaAcoes = (titulo, itens, tom) =>
    itens.length
      ? el("div", {}, [
          el("h3", { text: `${titulo} (${itens.length})` }),
          ...itens.map(({ execucao, acao }) =>
            el("div", { class: "auditoria-item" }, [
              el("div", { class: "auditoria-cabeca" }, [
                el("span", { class: "metodo escrita", text: acao.metodo }),
                el("span", { class: "rota", text: acao.rota }),
                selo(rotuloAcao(acao), tom),
                el("span", { class: "secao-nota", text: `${execucao.ticket_id} · ${execucao.seed}` }),
              ]),
              // Ação sem a justificativa que a acompanhou não é auditável (RN-13).
              el("div", {
                class: "auditoria-just",
                text: (acao.body && acao.body.justification) || "sem justificativa registrada",
              }),
            ])
          ),
        ])
      : null;

  return secao(
    `Auditoria e desperdício — ${fase}`,
    "o que o agente mexeu, e o que gastou sem necessidade",
    [
      el("div", { class: "metricas" }, [
        metrica("Taxa de repetição", pct(ag.taxa_repeticao_media), `${repetidas} de ${totalChamadas} chamadas`),
        metrica("Servidas de cache", num(doCache), "contam como repetição"),
        metrica("Erros HTTP", num(errosHttp), `${ag.com_erro_http} execuções`),
        metrica("Ações executadas", num(executadas.length), `${recusadas.length} recusadas`),
      ]),
      aviso("neutro", [
        "Chamada servida do cache é marcada como tal, mas continua contando como " +
          "repetição: o custo de rede foi evitado, o de raciocínio não.",
      ]),
      listaAcoes("Ações de impacto executadas", executadas, "atencao"),
      listaAcoes("Ações recusadas pela API", recusadas, "neutro"),
      !acoes.length ? vazio("Nenhuma ação de impacto nesta fase.") : null,
      el("div", { style: "margin-top:18px" }, [
        el("button", {
          class: "icone-btn",
          text: "Exportar esta visão em CSV",
          onclick: () => exportaCsv(execucoes, fase),
        }),
      ]),
    ]
  );
}
