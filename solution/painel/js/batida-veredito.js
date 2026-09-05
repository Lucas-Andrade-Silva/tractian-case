/* Batida ① — funciona?
 *
 * Uma tela, um número. O ganho entre fases vira uma seta em vez de um dropdown
 * que a banca teria de descobrir sozinha. Tudo aqui vem de `bundle.agregados`:
 * nenhum número desta tela é calculado neste arquivo. */

import { el, ESTADO, pct, num } from "./dados.js";
import { rodape } from "./batidas.js";
import { aviso } from "./componentes.js";
import { botaoGaveta } from "./gaveta.js";

/** Delta em pontos percentuais, com sinal e separador pt-BR. */
function deltaPp(depois, antes) {
  const d = (depois - antes) * 100;
  const formatado = d.toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return `${d >= 0 ? "+" : ""}${formatado} pp`;
}

/** Variação relativa de um custo — negativa é boa. */
function deltaCusto(depois, antes) {
  if (!antes) return "—";
  const d = ((depois - antes) / antes) * 100;
  return `${d >= 0 ? "+" : ""}${d.toFixed(0)}%`;
}

function tile(valor, rotulo, tom = "") {
  return el("div", { class: "tile" }, [
    el("span", { class: tom, text: valor }),
    el("em", { text: rotulo }),
  ]);
}

export function batidaVeredito(redesenha) {
  const bundle = ESTADO.bundle;
  const base = bundle.agregados["baseline"];
  const pos = bundle.agregados["pos-correcao"];

  // Contagem direta, não reconstruída de uma porcentagem arredondada. A acurácia é
  // medida sobre execuções que concluíram, então `acuracia × execucoes` usa um
  // denominador que não é o dela — hoje bate porque não houve falha, e passaria a
  // mentir no dia em que houver. Contar é auditável contra o bundle; reconstruir não.
  const daFase = bundle.execucoes.filter((e) => e.fase === "pos-correcao");
  const acertos = daFase.filter((e) => e.avaliacao.decision_match).length;

  const corpo = el("div", { class: "batida-corpo veredito" }, [
    el("div", { class: "veredito-numero" }, [
      el("b", { text: pct(pos.acuracia_decisao) }),
      el("small", { text: `acurácia de decisão · pós-correção · ${pos.execucoes} execuções` }),
    ]),

    el("div", { class: "veredito-seta" }, [
      el("span", { text: "baseline " }),
      el("b", { text: pct(base.acuracia_decisao) }),
      el("span", { class: "seta", text: "───▶" }),
      el("span", { text: "pós-correção " }),
      el("b", { text: pct(pos.acuracia_decisao) }),
      el("span", {
        class: "ganho",
        text: deltaPp(pos.acuracia_decisao, base.acuracia_decisao),
      }),
    ]),

    // A seta credita todo o ganho às correções. Isso só é honesto enquanto as duas
    // fases rodarem com o mesmo modelo por papel — e se algum dia não rodarem, a
    // ressalva não pode ficar atrás de um clique: ela invalida a manchete.
    bundle.meta.config_diverge_entre_fases
      ? aviso("atencao", [
          el("strong", { text: "Configuração de modelos diverge entre as fases. " }),
          "Parte desta diferença pode vir da troca de modelo, não das correções.",
          botaoGaveta("ver a configuração", "ressalvas", redesenha),
        ])
      : el("p", { class: "veredito-licenca" }, [
          "Mesma configuração de modelo nos cinco papéis nas duas fases — a diferença isola o efeito das correções. ",
          botaoGaveta("ver a configuração", "ressalvas", redesenha),
        ]),

    el("div", { class: "veredito-tiles" }, [
      tile(num(pos.falhas_execucao), "falhas de execução"),
      tile(deltaCusto(pos.tokens_medio, base.tokens_medio), "tokens por caso", "baixa"),
      tile(deltaCusto(pos.chamadas_media, base.chamadas_media), "chamadas por caso", "baixa"),
      tile(deltaCusto(pos.taxa_repeticao_media, base.taxa_repeticao_media), "consultas repetidas", "baixa"),
    ]),

    el("p", { class: "veredito-frase" }, [
      "Decidiu certo em ",
      el("b", { text: `${acertos} de ${daFase.length}` }),
      " execuções — e ficou mais barato no caminho.",
    ]),
  ]);

  return el("main", { class: "batida" }, [corpo, rodape(redesenha)]);
}
