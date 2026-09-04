/* Batida ③ — sempre?
 *
 * A matriz lidera e ocupa a tela: 17 cenários × 3 seeds. Clicar numa célula abre a
 * gaveta lateral com o diff entre a trajetória esperada e a percorrida.
 *
 * As quatro categorias de cor são as do painel inteiro, e a regra que as governa é
 * de domínio, não estética: escalar é desfecho correto e nunca cai em vermelho;
 * reprovação com decisão certa é atenção, porque costuma ser artefato do gabarito. */

import { ESTADO, el, pct, num, texto, VAZIO, achaExecucao } from "./dados.js";
import { selo, vazio } from "./componentes.js";
import { rodape } from "./batidas.js";
import { abreGaveta } from "./gaveta.js";

const SEEDS = ["complete", "s2", "s3"];

/** Tom da célula pelas quatro categorias (RN-10). */
export function tomDaCelula(execucao) {
  const av = execucao.avaliacao;
  if (!av.executou_sem_erro) return "atencao";
  if (av.passou) return execucao.operacao.decisao === "escalar" ? "neutro" : "sucesso";
  if (av.decision_match) return "atencao";
  return "erro";
}

/** Contagem por categoria — alimenta os selos do cabeçalho. */
function contagens(bundle, fase) {
  const execucoes = bundle.execucoes.filter((e) => e.fase === fase);
  let passou = 0;
  let artefato = 0;
  let erro = 0;
  for (const e of execucoes) {
    const tom = tomDaCelula(e);
    if (tom === "sucesso" || tom === "neutro") passou += 1;
    else if (tom === "atencao") artefato += 1;
    else erro += 1;
  }
  return { passou, artefato, erro, total: execucoes.length };
}

function celula(execucao, redesenha) {
  if (!execucao) return el("td", {}, [el("span", { class: "celula vazia", text: VAZIO })]);
  const tom = tomDaCelula(execucao);
  return el("td", {}, [
    el("button", {
      class: `celula celula-${tom}`,
      "aria-current": String(execucao.id === ESTADO.celulaId),
      text: execucao.operacao.decisao || "—",
      onclick: () => {
        ESTADO.celulaId = execucao.id;
        redesenha();
      },
    }),
  ]);
}

/** Painel lateral: o diff da célula escolhida. */
function lateral(redesenha) {
  const execucao = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.celulaId);
  if (!execucao) {
    return el("aside", { class: "matriz-lateral" }, [
      vazio("Clique numa célula para ver o diff entre o esperado e o percorrido."),
    ]);
  }

  const av = execucao.avaliacao;
  const tom = tomDaCelula(execucao);
  // Nomes reais do bundle — conferidos contra dados/bundle.json.
  const aceitas = av.decisoes_aceitas || [];
  const faltantes = av.queries_faltantes || [];
  const extras = av.queries_extras || [];
  const acoesFaltantes = av.acoes_faltantes || [];
  const diff = av.diff_trajetoria || [];

  const partes = [
    el("h3", { class: "mono", text: `${execucao.cenario} · ${execucao.seed}` }),
    el("dl", { class: "campos" }, [
      // Cenário ambíguo aceita mais de uma resolução: é uma lista, não um valor.
      el("dt", { text: aceitas.length > 1 ? "aceitas" : "esperado" }),
      el("dd", { text: aceitas.length ? aceitas.join(" ou ") : VAZIO }),
      el("dt", { text: "decidiu" }),
      el("dd", { text: texto(execucao.operacao.decisao) }),
    ]),
    el("div", { class: "lateral-bloco" }, [
      el("div", { class: "rotulo-cru", text: "trajetória esperada" }),
      diff.length
        ? el(
            "ul",
            { class: "diff-lista" },
            diff.map((passo) =>
              el("li", { class: `diff-${passo.situacao || "atendida"}` }, [
                el("span", { class: "mono", text: passo.step }),
                passo.nota ? el("em", { text: passo.nota }) : null,
              ])
            )
          )
        : el("p", { class: "gaveta-meta", text: "sem trajetória documentada" }),
    ]),
    el("div", { class: "lateral-bloco" }, [
      el("div", { class: "rotulo-cru", text: "consultas extras" }),
      extras.length
        ? el("ul", {}, extras.map((f) => el("li", { class: "mono", text: f })))
        : el("p", { class: "gaveta-meta", text: "nenhuma" }),
    ]),
  ];

  if (faltantes.length || acoesFaltantes.length) {
    partes.push(
      el("div", { class: "lateral-bloco" }, [
        el("div", { class: "rotulo-cru", text: "o que faltou" }),
        el(
          "ul",
          {},
          [...faltantes, ...acoesFaltantes].map((f) => el("li", { class: "mono", text: f }))
        ),
      ])
    );
  }

  // Célula de artefato abre já na explicação: sem isso, um amarelo sem contexto
  // se lê como desculpa.
  if (tom === "atencao" && av.decision_match) {
    partes.push(
      el("div", { class: "lateral-nota" }, [
        el("strong", { text: "Decisão certa, aprovação negada. " }),
        "O gabarito estruturado não documenta o POST que o cenário narrativo prescreve.",
        el("button", {
          class: "gaveta-gatilho",
          text: "ⓘ como a aprovação é calculada",
          onclick: () => abreGaveta("ressalvas", redesenha),
        }),
      ])
    );
  }

  partes.push(
    el("button", {
      class: "passo",
      text: "→ ver este chamado na batida ②",
      onclick: () => {
        ESTADO.execucaoId = execucao.id;
        ESTADO.batida = "chamado";
        redesenha();
      },
    })
  );

  return el("aside", { class: "matriz-lateral" }, partes);
}

export function batidaMatriz(redesenha) {
  const bundle = ESTADO.bundle;
  const fase = ESTADO.fase;
  const c = contagens(bundle, fase);

  const casos = bundle.casos.filter((caso) => caso.por_fase[fase]);
  const mediveis = casos.filter((caso) => caso.por_fase[fase].estabilidade.medivel);
  const estaveis = mediveis.filter((caso) => caso.por_fase[fase].estabilidade.estavel === true);

  const linhas = casos.map((caso) =>
    el("tr", {}, [
      el("td", { class: "mx-cen mono", text: caso.cenario || caso.case_id }),
      ...SEEDS.map((seed) => celula(achaExecucao(caso.case_id, seed, fase), redesenha)),
    ])
  );

  const corpo = el("div", { class: "batida-corpo matriz-layout" }, [
    el("div", {}, [
      el("div", { class: "matriz-cabeca" }, [
        el("h2", { text: `${casos.length} cenários × ${SEEDS.length} seeds` }),
        selo(`${estaveis.length}/${mediveis.length} estáveis`, "sucesso"),
        selo(`${num(bundle.agregados[fase].falhas_execucao)} falhas de execução`, "sucesso"),
        selo(
          `${c.erro} ${c.erro === 1 ? "erro real" : "erros reais"} · ${c.artefato} artefatos de gabarito`,
          "atencao"
        ),
      ]),
      el("table", { class: "matriz" }, [
        el("thead", {}, [
          el("tr", {}, [el("th", { text: "cenário" }), ...SEEDS.map((s) => el("th", { text: s }))]),
        ]),
        el("tbody", {}, linhas),
      ]),
      el("div", { class: "legenda" }, [
        el("span", {}, [el("i", { class: "celula-sucesso" }), "passou"]),
        el("span", {}, [el("i", { class: "celula-neutro" }), "escalou — desfecho correto"]),
        el("span", {}, [el("i", { class: "celula-atencao" }), "decisão certa, gabarito não documenta o POST"]),
        el("span", {}, [el("i", { class: "celula-erro" }), "decisão errada"]),
      ]),
    ]),
    lateral(redesenha),
  ]);

  return el("main", { class: "batida" }, [
    corpo,
    rodape(redesenha, ["ⓘ como a aprovação é calculada", "ressalvas"]),
  ]);
}
