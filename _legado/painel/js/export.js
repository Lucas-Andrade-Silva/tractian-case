/* Exportação em CSV da visão atual.
 *
 * Mesmos campos, mesma ordem e mesmas convenções de `.run/resultados_avaliacao.csv`:
 * separador `;`, `|` para multivalor, `True`/`False` para booleanos e BOM no início.
 * O arquivo exportado precisa abrir no mesmo lugar e casar com o já gerado — se as
 * colunas divergirem, ele deixa de ser comparável com a bateria de origem. */

const COLUNAS = [
  "fase", "cenario", "ticket", "seed", "case_id", "ativo", "usuario",
  "decisao", "decisoes_aceitas", "cenario_ambiguo", "decision_match", "passou",
  "evidence_recall", "precisao_consultas", "gets_feitos", "gets_esperados",
  "queries_faltantes", "queries_extras", "acoes_exigidas", "acoes_executadas",
  "acoes_faltantes", "acoes_nao_previstas", "tokens_input", "tokens_output",
  "tokens_total", "chamadas_api", "chamadas_repetidas", "taxa_repeticao",
  "erros_http", "justificativa_len", "executou_sem_erro", "erro_execucao",
];

function bool(valor) {
  return valor ? "True" : "False";
}

function lista(valores) {
  return (valores || []).join("|");
}

function vazioSeNulo(valor) {
  return valor === null || valor === undefined ? "" : String(valor);
}

/** Fração com casa decimal preservada.
 *  O JS imprime 1.0 como "1" e 0.0 como "0"; o CSV da bateria grava "1.0" e "0.0".
 *  Sem isto o arquivo exportado deixa de bater com o de origem numa comparação célula
 *  a célula, que é justamente o uso que ele precisa suportar. */
function fracao(valor) {
  if (valor === null || valor === undefined) return "";
  return Number.isInteger(valor) ? valor.toFixed(1) : String(valor);
}

/** Escapa um campo. O separador é `;`, então aspas só entram quando necessário. */
function campo(valor) {
  const texto = String(valor ?? "");
  if (/[;"\n\r]/.test(texto)) return `"${texto.replace(/"/g, '""')}"`;
  return texto;
}

function linhaDe(execucao) {
  const op = execucao.operacao;
  const av = execucao.avaliacao;
  const consumo = op.consumo || {};

  return [
    execucao.fase,
    execucao.cenario,
    execucao.ticket_id,
    execucao.seed,
    execucao.case_id,
    vazioSeNulo(op.asset_id),
    vazioSeNulo(op.user_id),
    vazioSeNulo(op.decisao),
    lista(av.decisoes_aceitas),
    bool(av.cenario_ambiguo),
    bool(av.decision_match),
    bool(av.passou),
    fracao(av.evidence_recall),
    fracao(av.precisao_consultas),
    vazioSeNulo(av.gets_feitos),
    vazioSeNulo(av.gets_esperados),
    lista(av.queries_faltantes),
    lista(av.queries_extras),
    lista(av.acoes_exigidas),
    lista(av.acoes_executadas),
    lista(av.acoes_faltantes),
    lista(av.acoes_nao_previstas),
    vazioSeNulo(consumo.input_tokens),
    vazioSeNulo(consumo.output_tokens),
    vazioSeNulo(consumo.total_tokens),
    vazioSeNulo(av.chamadas_api),
    vazioSeNulo(av.chamadas_repetidas),
    fracao(av.taxa_repeticao),
    vazioSeNulo(av.erros_http),
    vazioSeNulo(av.justificativa_len),
    bool(av.executou_sem_erro),
    vazioSeNulo(av.erro_execucao),
  ].map(campo).join(";");
}

export function exportaCsv(execucoes, fase) {
  const linhas = [COLUNAS.join(";"), ...execucoes.map(linhaDe)];
  // BOM para o Excel reconhecer UTF-8, como nos arquivos da bateria.
  const conteudo = "﻿" + linhas.join("\r\n") + "\r\n";
  const blob = new Blob([conteudo], { type: "text/csv;charset=utf-8" });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `painel_${fase}_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
