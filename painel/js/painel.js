/* Cabeçalho, abas e o ciclo de redesenho.
 *
 * Os seletores de seed e fase são compartilhados pelas duas abas (RF-02, RF-03): trocar a
 * execução exibida não pode custar a seleção do caso. Por isso a troca de seed tenta
 * manter o mesmo caso e só limpa a seleção se aquele caso não existir na combinação nova. */

import { ESTADO, el, limpa, carregaBundle, achaExecucao } from "./dados.js";
import { desenhaFila, desenhaDetalhe } from "./operacao.js";
import { desenhaAvaliacao } from "./avaliacao.js";
import { desenhaConsulta } from "./consulta.js";
import { aviso } from "./componentes.js";

const raiz = document.getElementById("app");

function redesenha() {
  limpa(raiz);
  raiz.append(cabecalho());

  if (ESTADO.aba === "consulta") {
    // A aba Consulta executa o agente ao vivo; nao depende de seed/fase do bundle.
    const conteudo = el("main", { class: "aba-avaliacao" });
    desenhaConsulta(conteudo, redesenha);
    raiz.append(conteudo);
  } else if (ESTADO.aba === "operacao") {
    const lista = el("aside", { class: "coluna-lista" });
    const conteudo = el("main", { class: "coluna-conteudo" });
    desenhaFila(lista, redesenha);
    desenhaDetalhe(conteudo, redesenha);
    raiz.append(el("div", { class: "painel" }, [lista, conteudo]));
  } else {
    const conteudo = el("main", { class: "aba-avaliacao" });
    desenhaAvaliacao(conteudo, redesenha);
    raiz.append(conteudo);
  }
}

function cabecalho() {
  const meta = ESTADO.bundle.meta;

  return el("header", { class: "topo" }, [
    el("div", { class: "marca" }, [
      el("h1", { text: "Atendimento e avaliação" }),
      el("span", { text: `${meta.execucoes} execuções` }),
    ]),
    el("nav", { class: "abas" }, [
      botaoAba("operacao", "Operação"),
      botaoAba("avaliacao", "Avaliação"),
      botaoAba("consulta", "Consulta"),
    ]),
    el("div", { class: "controles" }, [
      ESTADO.aba === "operacao"
        ? el("label", { class: "controle" }, [
            el("span", { text: "seed" }),
            el(
              "select",
              {
                onchange: (ev) => {
                  trocaSeed(ev.target.value);
                  redesenha();
                },
              },
              meta.seeds.map((s) =>
                el("option", { value: s, text: s, selected: ESTADO.seed === s })
              )
            ),
          ])
        : null,
      ESTADO.aba === "consulta"
        ? null
        : el("label", { class: "controle" }, [
            el("span", { text: "fase" }),
            el(
              "select",
              {
                onchange: (ev) => {
                  trocaFase(ev.target.value);
                  redesenha();
                },
              },
              meta.fases.map((f) =>
                el("option", { value: f, text: f, selected: ESTADO.fase === f })
              )
            ),
          ]),
      el("button", {
        class: "icone-btn",
        text: temaEscuro() ? "tema claro" : "tema escuro",
        onclick: () => {
          document.documentElement.dataset.tema = temaEscuro() ? "claro" : "escuro";
          redesenha();
        },
      }),
    ]),
  ]);
}

function temaEscuro() {
  const marcado = document.documentElement.dataset.tema;
  if (marcado) return marcado === "escuro";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function botaoAba(chave, rotulo) {
  return el("button", {
    text: rotulo,
    role: "tab",
    "aria-selected": String(ESTADO.aba === chave),
    onclick: () => {
      ESTADO.aba = chave;
      redesenha();
    },
  });
}

/** Troca a seed mantendo o caso selecionado, se ele existir na combinação nova. */
function trocaSeed(seed) {
  const atual = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.execucaoId);
  ESTADO.seed = seed;
  if (!atual) return;
  const equivalente = achaExecucao(atual.case_id, seed, ESTADO.fase);
  ESTADO.execucaoId = equivalente ? equivalente.id : null;
}

/** Troca a fase mantendo caso e seed. Nem todo caso foi reexecutado na pós-correção,
 *  então a seleção pode não ter equivalente — nesse caso é limpa, não substituída. */
function trocaFase(fase) {
  const atual = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.execucaoId);
  const celula = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.celulaId);
  ESTADO.fase = fase;

  if (atual) {
    const equivalente = achaExecucao(atual.case_id, atual.seed, fase);
    ESTADO.execucaoId = equivalente ? equivalente.id : null;
  }
  if (celula) {
    const equivalente = achaExecucao(celula.case_id, celula.seed, fase);
    ESTADO.celulaId = equivalente ? equivalente.id : null;
  }
}

carregaBundle()
  .then(() => {
    // Abre já com um caso aberto: um painel vazio não mostra o que ele faz.
    const primeira = ESTADO.bundle.execucoes.find(
      (e) => e.fase === ESTADO.fase && e.seed === ESTADO.seed
    );
    if (primeira) ESTADO.execucaoId = primeira.id;
    redesenha();
  })
  .catch((erro) => {
    limpa(raiz);
    raiz.append(
      el("div", { style: "padding:32px;max-width:70ch" }, [
        aviso("atencao", [
          el("strong", { text: "Não foi possível carregar os dados. " }),
          erro.message,
        ]),
        el("p", { class: "secao-nota" }, [
          "O painel lê um bundle gerado a partir dos traces já gravados. Rode " +
            "`python painel/build_bundle.py` e sirva a pasta por HTTP (o navegador bloqueia " +
            "fetch em file://): `make painel`.",
        ]),
      ])
    );
  });
