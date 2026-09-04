import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaMatriz(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "os 17 × 3 — Task 8" })]),
    rodape(redesenha),
  ]);
}
