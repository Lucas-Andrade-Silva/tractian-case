/* As quatro batidas — o roteiro da demonstração.
 *
 * A ordem não é arbitrária: cada batida responde uma pergunta que a anterior
 * provoca. Funciona? Por quê? Sempre? De verdade? Trocar a ordem quebra o
 * argumento, não só o layout. */

import { el, ESTADO } from "./dados.js";
import { botaoGaveta } from "./gaveta.js";

export const BATIDAS = [
  { chave: "veredito", numero: "①", rotulo: "veredito" },
  { chave: "chamado", numero: "②", rotulo: "um chamado" },
  { chave: "matriz", numero: "③", rotulo: "os 17 × 3" },
  { chave: "aovivo", numero: "④", rotulo: "ao vivo" },
];

export function desenhaNav(redesenha) {
  return el(
    "nav",
    { class: "batidas-nav", role: "tablist" },
    BATIDAS.map((b) =>
      el("button", {
        role: "tab",
        "aria-selected": String(ESTADO.batida === b.chave),
        onclick: () => {
          ESTADO.batida = b.chave;
          redesenha();
        },
        text: `${b.numero} ${b.rotulo}`,
      })
    )
  );
}

/** Rodapé fixo: navegação sequencial à esquerda, gatilho da gaveta à direita. */
export function rodape(redesenha, gatilho = ["ⓘ método e ressalvas", "metodo"]) {
  const indice = BATIDAS.findIndex((b) => b.chave === ESTADO.batida);
  const anterior = BATIDAS[indice - 1];
  const proxima = BATIDAS[indice + 1];

  const passos = [];
  if (anterior) {
    passos.push(
      el("button", {
        class: "passo",
        text: `← ${anterior.rotulo}`,
        onclick: () => { ESTADO.batida = anterior.chave; redesenha(); },
      })
    );
  }
  if (proxima) {
    passos.push(
      el("button", {
        class: "passo",
        text: `${proxima.rotulo} →`,
        onclick: () => { ESTADO.batida = proxima.chave; redesenha(); },
      })
    );
  }

  return el("footer", { class: "batida-rodape" }, [
    el("div", { class: "passos" }, passos),
    el("div", {}, [botaoGaveta(gatilho[0], gatilho[1], redesenha)]),
  ]);
}

/** Setas do teclado avançam a narrativa — o autor conduz sem procurar o mouse. */
export function ligaTeclado(redesenha) {
  window.addEventListener("keydown", (ev) => {
    if (ESTADO.gaveta) {
      if (ev.key === "Escape") { ESTADO.gaveta = null; redesenha(); }
      return;
    }
    const indice = BATIDAS.findIndex((b) => b.chave === ESTADO.batida);
    if (ev.key === "ArrowRight" && BATIDAS[indice + 1]) {
      ESTADO.batida = BATIDAS[indice + 1].chave;
      redesenha();
    } else if (ev.key === "ArrowLeft" && BATIDAS[indice - 1]) {
      ESTADO.batida = BATIDAS[indice - 1].chave;
      redesenha();
    }
  });
}
