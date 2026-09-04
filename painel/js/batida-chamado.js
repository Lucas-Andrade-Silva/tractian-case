import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaChamado(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "um chamado — Task 7" })]),
    rodape(redesenha),
  ]);
}
