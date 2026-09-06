/* Cabeçalho, navegação entre batidas e o ciclo de redesenho.
 *
 * O painel antigo tinha três abas por audiência (operação, avaliação, consulta) e
 * seletores globais de seed e fase. A demonstração não é uma escolha de audiência:
 * é uma sequência. As quatro batidas são a sequência, e os seletores desceram para
 * a batida que precisa deles. */

import { ESTADO, el, limpa, carregaBundle } from "./dados.js";
import { desenhaNav, ligaTeclado } from "./batidas.js";
import { desenhaGaveta } from "./gaveta.js";
import { aviso } from "./componentes.js";
import { batidaVeredito } from "./batida-veredito.js";
import { batidaChamado } from "./batida-chamado.js";
import { batidaMatriz } from "./batida-matriz.js";
import { batidaAoVivo } from "./batida-aovivo.js";

const raiz = document.getElementById("app");

const TELAS = {
  veredito: batidaVeredito,
  chamado: batidaChamado,
  matriz: batidaMatriz,
  aovivo: batidaAoVivo,
};

function redesenha() {
  limpa(raiz);
  raiz.append(cabecalho());

  const tela = TELAS[ESTADO.batida] || TELAS.veredito;
  raiz.append(tela(redesenha));

  const gaveta = desenhaGaveta(redesenha);
  if (gaveta) raiz.append(gaveta);
}

function cabecalho() {
  return el("header", { class: "topo" }, [
    el("div", { class: "marca" }, [
      el("h1", { text: "Agente de suporte industrial" }),
    ]),
    desenhaNav(redesenha),
    el("div", { class: "controles" }, [
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

carregaBundle()
  .then(() => {
    const primeira = ESTADO.bundle.execucoes.find(
      (e) => e.ticket_id === "TKT-INV-09" && e.fase === ESTADO.fase && e.seed === ESTADO.seed
    );
    if (primeira) ESTADO.execucaoId = primeira.id;
    ligaTeclado(redesenha);
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
