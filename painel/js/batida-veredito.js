import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaVeredito(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "veredito — Task 6" })]),
    rodape(redesenha),
  ]);
}
