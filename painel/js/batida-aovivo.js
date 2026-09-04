import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaAoVivo(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "ao vivo — Task 9" })]),
    rodape(redesenha),
  ]);
}
