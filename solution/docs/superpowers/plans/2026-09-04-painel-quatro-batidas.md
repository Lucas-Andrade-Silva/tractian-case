# Painel em Quatro Batidas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir as três abas verticais do painel por quatro telas narrativas, cada uma respondendo uma pergunta, com toda a prosa metodológica movida para uma gaveta única.

**Architecture:** O painel é JS puro com ES modules, sem framework e sem build step — `el()` em `painel/js/dados.js:184` é o construtor de DOM. A navegação por abas de `painel.js` vira navegação por batidas; três módulos novos (`faixas.js`, `gaveta.js`, `batidas.js`) são criados e consumidos pelas telas; `avaliacao.js` e `operacao.js` encolhem por absorção. O CSS mantém os tokens existentes e sobe a escala tipográfica.

**Tech Stack:** JavaScript ES modules (sem toolchain, sem Node), CSS custom properties, Python 3 + pytest para os testes de contrato.

**Spec:** `docs/superpowers/specs/2026-09-04-painel-quatro-batidas-design.md`

## Global Constraints

- **Sem toolchain JS.** O projeto não tem `package.json` e não vai ter. Nada de npm, bundler ou transpilação. Os módulos são carregados nativamente por `<script type="module">`.
- **Nada fora de `painel/`.** `agent/`, `evaluation/`, `api/` e o formato de `bundle.json` não mudam.
- **RN-01:** o módulo da batida ② não pode importar de `avaliacao.js`. É verificável por leitura de import e há teste para isso.
- **RN-16:** a resposta final ao cliente aparece íntegra, nunca truncada.
- **Nenhum número exibido pode vir de aritmética escrita à mão no JS de renderização.** Todo agregado vem de `bundle.agregados` ou é calculado em `build_bundle.py`.
- **Corpo ≥ 16px**; as quatro batidas cabem sem rolagem vertical em 1920×1080.
- **Tema claro e escuro** funcionam nas quatro batidas.
- **Convenção visual:** borda lateral (`border-left`) significa citação literal e nada mais. Blocos que não são citação se identificam por rótulo.
- Testes rodam com: `cd painel && python -m pytest tests/ -q`

---

### Task 1: Infraestrutura de teste do painel

Cria o alicerce de teste que as tarefas seguintes usam. Sem isto, nenhuma outra tarefa tem ciclo de teste.

**Files:**
- Create: `painel/tests/__init__.py`
- Create: `painel/tests/conftest.py`
- Create: `painel/tests/test_contrato.py`
- Create: `painel/pytest.ini`

**Interfaces:**
- Consumes: nada.
- Produces: fixture `bundle` (dict do `painel/dados/bundle.json`), fixture `js_fonte(nome)` (retorna o texto de `painel/js/<nome>`), helper `imports_de(fonte) -> set[str]`.

- [ ] **Step 1: Write the failing test**

Crie `painel/tests/conftest.py`:

```python
"""Fixtures para os testes de contrato do painel.

O painel é JS sem toolchain: não há como executar os módulos aqui. O que estes
testes protegem é o contrato que a leitura humana costuma deixar passar —
separação de import entre operação e avaliação, e números de tela que não podem
ser inventados no renderizador.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PAINEL = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def bundle() -> dict:
    return json.loads((PAINEL / "dados" / "bundle.json").read_text(encoding="utf-8"))


@pytest.fixture
def js_fonte():
    def _ler(nome: str) -> str:
        return (PAINEL / "js" / nome).read_text(encoding="utf-8")

    return _ler


def imports_de(fonte: str) -> set[str]:
    """Módulos importados por um arquivo JS, como aparecem no `from "..."`."""
    return set(re.findall(r'from\s+"\./([\w.]+)"', fonte))
```

Crie `painel/tests/__init__.py` vazio e `painel/pytest.ini`:

```ini
[pytest]
testpaths = tests
```

Crie `painel/tests/test_contrato.py`:

```python
"""Contratos do painel que falham em silêncio se quebrarem.

RN-01 é o mais importante: se a tela de operação passar a ler o gabarito, ela
deixa de ser a visão de quem atende e a Parte 2 do projeto perde o sentido. O
sintoma não é um erro — é uma tela que continua funcionando e passa a mentir.
"""
from __future__ import annotations

from .conftest import imports_de


def test_bundle_tem_as_fases_esperadas(bundle):
    assert set(bundle["meta"]["fases"]) == {"baseline", "pos-correcao"}
    assert bundle["agregados"]["pos-correcao"]["execucoes"] == 51
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — `painel/tests/` não existe ainda, ou `ModuleNotFoundError` na primeira execução antes de criar os arquivos. Depois de criados, este teste passa: ele valida o alicerce.

- [ ] **Step 3: Rodar de novo para confirmar verde**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 1 passed.

- [ ] **Step 4: Commit**

```bash
git add painel/tests painel/pytest.ini
git commit -m "test: alicerce de teste de contrato do painel"
```

---

### Task 2: Teste de RN-01 e escala tipográfica

Fixa as duas regras globais antes de qualquer refactor, para que as tarefas seguintes não possam violá-las sem o teste apontar.

**Files:**
- Modify: `painel/tests/test_contrato.py`
- Modify: `painel/css/painel.css:52-62` (escala tipográfica)

**Interfaces:**
- Consumes: `imports_de` da Task 1.
- Produces: garantia testada de que `operacao.js` (e depois `batida-chamado.js`) nunca importa `avaliacao.js`; tokens `--t-corpo: 16px` e `--t-metrica: 76px`.

- [ ] **Step 1: Adicionar a fixture do CSS**

Em `painel/tests/conftest.py`, adicione:

```python
@pytest.fixture(scope="session")
def css_fonte() -> str:
    return (PAINEL / "css" / "painel.css").read_text(encoding="utf-8")
```

- [ ] **Step 2: Write the failing tests**

Adicione a `painel/tests/test_contrato.py`:

```python
import re


def test_operacao_nao_importa_avaliacao(js_fonte):
    """RN-01 estrutural: a visão de quem atende não pode ler o gabarito."""
    for modulo in ("operacao.js",):
        assert "avaliacao.js" not in imports_de(js_fonte(modulo)), (
            f"{modulo} importou avaliacao.js — RN-01 quebrado"
        )


def _token(css: str, nome: str) -> float:
    """Valor numérico de um custom property como `--t-corpo: 16px`."""
    achado = re.search(rf"{re.escape(nome)}:\s*([\d.]+)px", css)
    assert achado, f"token {nome} não encontrado no CSS"
    return float(achado.group(1))


def test_corpo_legivel_em_projetor(css_fonte):
    """A banca lê a 4 m: corpo de 13,5px morre no projetor."""
    assert _token(css_fonte, "--t-corpo") >= 16


def test_metrica_de_veredito_e_grande(css_fonte):
    """O 94,1% da batida ① é o objeto mais importante do painel."""
    assert _token(css_fonte, "--t-metrica") >= 58
```

Nota: `test_operacao_nao_importa_avaliacao` já passa hoje — ele trava o comportamento
atual para o refactor não o perder. Os dois de CSS falham.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — `--t-corpo` é 13.5px e `--t-metrica` é 30px.

- [ ] **Step 4: Subir a escala tipográfica**

Em `painel/css/painel.css`, substitua o bloco de escala (linhas ~52-62):

```css
  /* Escala tipográfica para projetor: corpo a 16px, ancorada em passo ~1.2.
     A escala anterior (corpo 13,5px) era de leitura em monitor a 60 cm; a banca
     lê a 4 m de distância. Números de veredito a 76px. */
  --t-micro: 12px;
  --t-mini:  13px;
  --t-meta:  14px;
  --t-corpo: 16px;
  --t-leitura: 17.5px;
  --t-h3:    15px;
  --t-h2:    19px;
  --t-h1:    24px;
  --t-metrica: 76px;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 4 passed.

- [ ] **Step 6: Verificar no navegador**

Run: `make painel`
Abra `http://localhost:8001`. As três abas ainda existem (ainda não refatoramos), mas o texto está maior. Confirme que nada quebrou de layout a ponto de sobrepor.

- [ ] **Step 7: Commit**

```bash
git add painel/tests painel/css/painel.css
git commit -m "feat: escala tipografica de projetor e teste de RN-01"
```

---

### Task 3: Módulo de faixas por papel

O componente central do redesenho: consumido pela batida ② e reusado pela ④. Substitui a timeline linear e a tabela de custo por papel.

**Files:**
- Create: `painel/js/faixas.js`
- Modify: `painel/tests/test_contrato.py`

**Interfaces:**
- Consumes: `el`, `num`, `pct` de `dados.js`; `selo` de `componentes.js`.
- Produces:
  - `faixasPorPapel(execucao, estado, redesenha) -> HTMLElement` — desenha as faixas.
  - `fatosDoAchado(resumoTexto) -> Array<{chave, valor, tom}>` — parseia o texto de `achados[].summary` em tags.

- [ ] **Step 1: Write the failing test**

O parser de fatos é a única lógica não-visual, e é onde um erro vira tag errada na tela. Adicione a `painel/tests/test_contrato.py`:

```python
def test_achados_do_bundle_sao_parseaveis(bundle):
    """As tags de fato da batida ② vêm de achados[].summary.

    O formato é `chave=valor (origem)` por linha. Se o formato mudar no
    build_bundle e ninguém notar, a batida ② fica sem tags e volta a ser uma
    lista de endpoints — exatamente o que o redesenho removeu.
    """
    execucao = next(
        e for e in bundle["execucoes"]
        if e["ticket_id"] == "TKT-INV-09"
        and e["fase"] == "pos-correcao"
        and e["seed"] == "complete"
    )
    achados = execucao["operacao"]["achados"]
    assert achados, "TKT-INV-09 perdeu os achados"

    linhas = [l for l in achados[0]["summary"].splitlines() if l.strip()]
    assert len(linhas) >= 5, "esperado ao menos 5 fatos apurados"
    assert any("baseline.state=invalidated" in l for l in linhas)
    assert any("status=stale" in l for l in linhas)
    assert all("=" in l for l in linhas), "toda linha de achado tem chave=valor"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — o formato já é esse; o teste trava o contrato para o refactor.

- [ ] **Step 3: Criar `painel/js/faixas.js`**

```javascript
/* Faixas por papel — a trajetória do atendimento como geometria.
 *
 * Este módulo existe para não precisar da prosa que ele substitui. A faixa do
 * Decisor tem um ponto de LLM e nenhuma chamada de API: a assimetria da ADR 0002
 * fica visível, em vez de explicada em quatro linhas de texto.
 *
 * Endpoints não aparecem por padrão (decisão do redesenho): o que ocupa o lugar
 * deles são os fatos que eles produziram, lidos de `achados[].summary`. */

import { el, num, pct, texto, PAPEIS_PT } from "./dados.js";

/** Tom da tag pelo teor do fato. Neutro é o padrão: só o que é anômalo colore. */
const PADROES_TOM = [
  [/invalidated|stale|exceeds_alarm|=true/, "atencao"],
  [/online|ok|=false/, "sucesso"],
];

/** Quebra `achados[].summary` em tags. Formato: `chave=valor (origem)` por linha. */
export function fatosDoAchado(resumo) {
  const linhas = String(resumo || "").split("\n").map((l) => l.trim()).filter(Boolean);
  return linhas.map((linha) => {
    const semOrigem = linha.replace(/\s*\([^)]*\)\s*$/, "");
    const corte = semOrigem.indexOf("=");
    const chave = corte === -1 ? semOrigem : semOrigem.slice(0, corte);
    const valor = corte === -1 ? "" : semOrigem.slice(corte + 1);
    const tom = (PADROES_TOM.find(([re]) => re.test(semOrigem)) || [null, "quieto"])[1];
    return { chave, valor, tom };
  });
}

function tagFato(fato) {
  const rotulo = fato.valor ? `${fato.chave} ${fato.valor}` : fato.chave;
  return el("span", { class: `fato fato-${fato.tom} mono`, text: rotulo });
}

/** Uma faixa: nome do papel, o que ele fez, e quanto custou. */
function faixa(papel, conteudoMeio, consumoPapel, totalTokens, extras = {}) {
  const tokens = consumoPapel ? consumoPapel.total_tokens : 0;
  return el("div", { class: `faixa${extras.destaque ? " faixa-destaque" : ""}` }, [
    el("div", { class: "faixa-nome" }, [
      el("span", { text: PAPEIS_PT[papel] || papel }),
      el("em", { text: extras.subtitulo || "" }),
    ]),
    el("div", { class: "faixa-meio" }, conteudoMeio),
    el("div", { class: "faixa-custo" }, [
      el("b", { text: consumoPapel ? num(tokens) : "—" }),
      el("span", {
        text: totalTokens && tokens ? `${pct(tokens / totalTokens, 0)} do caso` : "",
      }),
    ]),
  ]);
}

function pontoLlm() {
  return el("span", { class: "ponto-llm", title: "uma chamada de LLM" });
}

/**
 * Desenha a trajetória em faixas por papel.
 * `estado.faixasAbertas` é um Set de chaves `execucaoId:papel` para as rotas cruas.
 */
export function faixasPorPapel(execucao, estado, redesenha) {
  const op = execucao.operacao;
  const consumo = op.consumo || {};
  const porPapel = consumo.by_agent || {};
  const total = consumo.total_tokens || 0;
  const achadosPorPapel = new Map((op.achados || []).map((a) => [a.agent, a.summary]));

  // Ordem de entrada em cena, deduzida da timeline — não uma lista fixa.
  const ordem = [];
  for (const evento of op.timeline) {
    const papel = evento.tipo === "roteamento" ? evento.para : evento.papel;
    if (papel && !ordem.includes(papel)) ordem.push(papel);
  }
  for (const papel of Object.keys(porPapel)) {
    if (!ordem.includes(papel)) ordem.push(papel);
  }

  const chamadasPorPapel = new Map();
  let papelCorrente = null;
  for (const evento of op.timeline) {
    if (evento.tipo === "roteamento") papelCorrente = evento.para;
    else if (evento.tipo === "chamada" && papelCorrente) {
      if (!chamadasPorPapel.has(papelCorrente)) chamadasPorPapel.set(papelCorrente, []);
      chamadasPorPapel.get(papelCorrente).push(evento);
    }
  }

  const motivos = new Map(
    op.timeline
      .filter((e) => e.tipo === "roteamento")
      .map((e) => [e.para, e.motivo])
  );

  const nodes = [];
  for (const papel of ordem) {
    const motivo = motivos.get(papel);
    if (motivo) {
      nodes.push(
        el("div", { class: "faixa-bastao" }, [
          el("span", { text: "↳ " }),
          el("span", { text: texto(motivo) }),
          el("span", { text: ` → ${PAPEIS_PT[papel] || papel}` }),
        ])
      );
    }

    const chamadas = chamadasPorPapel.get(papel) || [];
    const fatos = fatosDoAchado(achadosPorPapel.get(papel));
    const meio = [pontoLlm()];

    if (fatos.length) meio.push(...fatos.map(tagFato));
    if (chamadas.length) {
      const chave = `${execucao.id}:${papel}`;
      const aberta = estado.faixasAbertas.has(chave);
      meio.push(
        el("button", {
          class: "faixa-rotas",
          "aria-expanded": String(aberta),
          text: `${chamadas.length} ${chamadas.length === 1 ? "consulta" : "consultas"} ⌄`,
          onclick: () => {
            if (aberta) estado.faixasAbertas.delete(chave);
            else estado.faixasAbertas.add(chave);
            redesenha();
          },
        })
      );
    }
    if (!fatos.length && !chamadas.length) {
      meio.push(
        el("span", {
          class: "faixa-vazia",
          text: papel === "decisor"
            ? "zero consultas — não tem tools (ADR 0002)"
            : "não consulta a plataforma",
        })
      );
    }

    nodes.push(
      faixa(papel, meio, porPapel[papel], total, {
        destaque: papel === "decisor",
        subtitulo: fatos.length ? `apurou ${fatos.length} fatos` : "",
      })
    );

    const chave = `${execucao.id}:${papel}`;
    if (estado.faixasAbertas.has(chave) && chamadas.length) {
      nodes.push(
        el(
          "div",
          { class: "faixa-cruas" },
          chamadas.map((c) =>
            el("div", { class: "crua-linha mono" }, [
              el("span", { class: `metodo${c.metodo === "GET" ? "" : " escrita"}`, text: c.metodo }),
              el("span", { class: "rota", text: c.rota }),
              el("span", { text: `${c.status_code}` }),
              el("span", { text: `${num(c.latencia_ms)} ms` }),
            ])
          )
        )
      );
    }
  }

  return el("div", { class: "faixas" }, nodes);
}
```

- [ ] **Step 4: Adicionar o CSS das faixas**

Ao final de `painel/css/painel.css`:

```css
/* -- faixas por papel ---------------------------------------------------- */
.faixas { border-top: 1px solid var(--regua); }

.faixa {
  display: grid;
  grid-template-columns: 132px 1fr 104px;
  border-bottom: 1px solid var(--faixa);
}
.faixa-destaque { background: var(--tonal-neutro); }

.faixa-nome {
  padding: 10px 12px;
  background: var(--superficie);
  border-right: 1px solid var(--regua);
  font-size: var(--t-meta);
}
.faixa-nome em { display: block; font-style: normal; color: var(--texto-fraco); font-size: var(--t-mini); }

.faixa-meio {
  padding: 10px 12px;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  min-height: 38px;
}

.faixa-custo {
  padding: 10px 12px;
  border-left: 1px solid var(--faixa);
  text-align: right;
  font-size: var(--t-mini);
  color: var(--texto-fraco);
}
.faixa-custo b { display: block; font-size: var(--t-corpo); color: var(--texto); font-weight: 500; }

.ponto-llm {
  width: 15px; height: 15px; border-radius: 50%;
  background: var(--acento); flex: none;
}

.fato {
  font-size: var(--t-mini);
  padding: 2px 8px; border-radius: var(--r);
  border: 1px solid; white-space: nowrap;
}
.fato-quieto  { color: var(--texto-fraco);   background: var(--faixa);          border-color: var(--regua); }
.fato-sucesso { color: var(--verde-exec);    background: var(--verde-fundo);    border-color: var(--verde-exec); }
.fato-atencao { color: var(--ambar-atencao); background: var(--ambar-fundo);    border-color: var(--ambar-atencao); }
.fato-erro    { color: var(--vermelho-erro); background: var(--vermelho-fundo); border-color: var(--vermelho-erro); }

.faixa-vazia { color: var(--texto-ausente); font-size: var(--t-meta); font-style: italic; }

.faixa-rotas {
  font-size: var(--t-mini);
  color: var(--texto-fraco);
  background: var(--faixa);
  border: 1px solid var(--regua);
  border-radius: 10px;
  padding: 2px 10px;
  cursor: pointer;
}
.faixa-rotas:hover { color: var(--texto); }

.faixa-bastao {
  padding: 6px 12px 6px 144px;
  font-size: var(--t-meta);
  color: var(--azul-neutro);
  background: var(--fundo);
  border-bottom: 1px solid var(--faixa);
}

.faixa-cruas { padding: 6px 12px 8px 144px; background: var(--fundo); border-bottom: 1px solid var(--faixa); }
.crua-linha { display: flex; gap: 10px; align-items: center; font-size: var(--t-mini); padding: 2px 0; }
```

- [ ] **Step 5: Registrar `faixasAbertas` no estado**

Em `painel/js/dados.js`, no objeto `ESTADO` (linha 7), adicione a chave junto de `expandidas`:

```javascript
  faixasAbertas: new Set(),
```

- [ ] **Step 6: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 5 passed.

- [ ] **Step 7: Commit**

```bash
git add painel/js/faixas.js painel/js/dados.js painel/css/painel.css painel/tests
git commit -m "feat: modulo de faixas por papel com tags de fato apurado"
```

---

### Task 4: Módulo da gaveta

O destino de toda a prosa metodológica. Precisa existir antes das batidas, porque elas apontam para ela.

**Files:**
- Create: `painel/js/gaveta.js`
- Modify: `painel/css/painel.css`
- Modify: `painel/js/dados.js` (estado)

**Interfaces:**
- Consumes: `el`, `ESTADO` de `dados.js`.
- Produces:
  - `abreGaveta(aba, redesenha)` — abre na aba nomeada (`"metodo" | "ressalvas" | "auditoria" | "arquitetura"`).
  - `desenhaGaveta(redesenha) -> HTMLElement | null` — o painel sobreposto, ou `null` se fechada.
  - `botaoGaveta(rotulo, aba, redesenha) -> HTMLElement` — o gatilho de rodapé.

- [ ] **Step 1: Write the failing test**

Adicione a `painel/tests/test_contrato.py`:

```python
def test_gaveta_cobre_as_quatro_abas(js_fonte):
    """A gaveta é o único destino da prosa: se uma aba sumir, a ressalva some junto."""
    fonte = js_fonte("gaveta.js")
    for aba in ("metodo", "ressalvas", "auditoria", "arquitetura"):
        assert f'"{aba}"' in fonte, f"gaveta.js não define a aba {aba}"


def test_ressalva_de_juiz_nao_calibrado_sobreviveu(js_fonte):
    """Nota de juiz não calibrado não é verdade — a ressalva não pode se perder no refactor."""
    fonte = js_fonte("gaveta.js")
    assert "calibra" in fonte.lower(), "a ressalva de calibração do juiz sumiu"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — `FileNotFoundError: painel/js/gaveta.js`.

- [ ] **Step 3: Criar `painel/js/gaveta.js`**

```javascript
/* A gaveta — onde vive tudo que é verdadeiro e quase nunca urgente.
 *
 * O painel antigo punha a ressalva metodológica ao lado do número que ela
 * ressalva, no mesmo peso visual. Isso é honesto e ilegível ao mesmo tempo. Aqui
 * a prosa continua inteira, a um gesto de distância, sempre no mesmo lugar.
 *
 * Nada foi apagado na migração: se um texto existia no painel antigo e não está
 * numa destas abas, é bug. */

import { el, ESTADO, num, pct, texto, rotuloAcao, acoesDeImpacto, execucoesDaFase } from "./dados.js";
import { selo, metrica } from "./componentes.js";
import { exportaCsv } from "./export.js";

const ABAS = [
  ["metodo", "Método"],
  ["ressalvas", "Ressalvas"],
  ["auditoria", "Auditoria"],
  ["arquitetura", "Arquitetura"],
];

export function abreGaveta(aba, redesenha) {
  ESTADO.gaveta = aba;
  redesenha();
}

export function botaoGaveta(rotulo, aba, redesenha) {
  return el("button", {
    class: "gaveta-gatilho",
    text: rotulo,
    onclick: () => abreGaveta(aba, redesenha),
  });
}

function corpoMetodo() {
  return el("div", { class: "gaveta-corpo" }, [
    el("h3", { text: "Como cada número é calculado" }),
    el("dl", { class: "campos" }, [
      el("dt", { text: "acurácia de decisão" }),
      el("dd", { text: "execuções cuja decisão final bate com a do gabarito, sobre as execuções que concluíram." }),
      el("dt", { text: "taxa de aprovação" }),
      el("dd", { text: "critério determinístico do runner: decisão certa e trajetória dentro do esperado." }),
      el("dt", { text: "recall de evidência" }),
      el("dd", { text: "fração dos pilares de evidência do gabarito que a execução apurou." }),
      el("dt", { text: "precisão de consultas" }),
      el("dd", {
        text:
          "métrica derivada por mim, não calculada pelo código da avaliação: " +
          "(GETs feitos − extras) / GETs feitos, sem contar GET /users/me. Valor baixo não é " +
          "necessariamente ruim — a política de evidência “fixed” sempre apura os quatro pilares, " +
          "independentemente do que o gabarito daquele caso documentou.",
      }),
      el("dt", { text: "taxa de repetição" }),
      el("dd", {
        text:
          "chamadas repetidas sobre chamadas totais. Chamada servida do cache é marcada como tal, " +
          "mas continua contando como repetição: o custo de rede foi evitado, o de raciocínio não.",
      }),
    ]),
  ]);
}

function corpoRessalvas(bundle) {
  const partes = [
    el("h3", { text: "O que estes números não dizem" }),
    el("p", {}, [
      el("strong", { text: "Reprovação com decisão certa costuma ser artefato. " }),
      "Em vários casos o gabarito estruturado não documenta um POST que o cenário narrativo " +
        "prescreve — nesses casos a reprovação é artefato da medição, não erro do agente.",
    ]),
    el("p", {}, [
      el("strong", { text: "Falha de execução é categoria própria. " }),
      "Execução interrompida por limite de provedor não é decisão errada e não entra na acurácia.",
    ]),
    el("p", {}, [
      el("strong", { text: "Cenário ambíguo aceita mais de um desfecho. " }),
      "Onde o cenário admite mais de uma resolução, escolher qualquer uma delas é acerto.",
    ]),
    el("p", {}, [
      el("strong", { text: "Escalar não é falha. " }),
      "Encaminhar para análise humana quando o caso extrapola o atendimento remoto é desfecho correto.",
    ]),
  ];

  // O comitê só aparece se o bundle o trouxer. Quando aparece, vem com a ressalva
  // de calibração — nota de juiz não validado contra conjunto anotado por humano
  // não é verdade, e não sobe para nenhuma batida.
  if (bundle.juizes) {
    partes.push(
      el("h3", { text: "Comitê de juízes" }),
      el("p", {}, [
        el("strong", { text: "Não calibrado. " }),
        "As notas do comitê só passam a ser leitura válida depois da calibração manual contra um " +
          "conjunto anotado por humano. Enquanto isso não for feito, média de juiz não validado não " +
          "é verdade — este aviso permanece mesmo quando houver notas.",
      ])
    );
  }

  return el("div", { class: "gaveta-corpo" }, partes);
}

function corpoAuditoria(bundle, redesenha) {
  const fase = ESTADO.fase;
  const execucoes = execucoesDaFase(fase);
  const ag = bundle.agregados[fase];

  const acoes = [];
  for (const execucao of execucoes) {
    for (const acao of acoesDeImpacto(execucao)) acoes.push({ execucao, acao });
  }
  const executadas = acoes.filter(({ acao }) => acao.ok);
  const recusadas = acoes.filter(({ acao }) => !acao.ok);

  const lista = (titulo, itens, tom) =>
    itens.length
      ? el("div", {}, [
          el("h3", { text: `${titulo} (${itens.length})` }),
          ...itens.map(({ execucao, acao }) =>
            el("div", { class: "auditoria-item" }, [
              el("div", { class: "auditoria-cabeca" }, [
                el("span", { class: "metodo escrita", text: acao.metodo }),
                el("span", { class: "rota mono", text: acao.rota }),
                selo(rotuloAcao(acao), tom),
                el("span", { class: "gaveta-meta", text: `${execucao.ticket_id} · ${execucao.seed}` }),
              ]),
              // Ação sem a justificativa que a acompanhou não é auditável (RN-13).
              el("div", {
                class: "auditoria-just",
                text: (acao.body && acao.body.justification) || "sem justificativa registrada",
              }),
            ])
          ),
        ])
      : null;

  return el("div", { class: "gaveta-corpo" }, [
    el("h3", { text: `Auditoria e desperdício — ${fase}` }),
    el("div", { class: "metricas" }, [
      metrica("Taxa de repetição", pct(ag.taxa_repeticao_media)),
      metrica("Erros HTTP", num(ag.com_erro_http), "execuções"),
      metrica("Ações executadas", num(executadas.length), `${recusadas.length} recusadas`),
    ]),
    lista("Ações de impacto executadas", executadas, "atencao"),
    lista("Ações recusadas pela API", recusadas, "neutro"),
    el("button", {
      class: "icone-btn",
      text: "Exportar esta visão em CSV",
      onclick: () => exportaCsv(execucoes, fase),
    }),
  ]);
}

function corpoArquitetura() {
  return el("div", { class: "gaveta-corpo" }, [
    el("h3", { text: "Decisões de arquitetura" }),
    el("p", {}, [
      el("strong", { text: "ADR 0002 — o Decisor não tem tools. " }),
      "É o único papel sem ferramentas: decide sobre a evidência que os workers já apuraram, em vez " +
        "de consultar a API. Sem tools não há laço de chamada, e ele gasta exatamente uma chamada de " +
        "LLM por atendimento — contra 2 a 3 dos papéis que investigam. Como é ele que usa o modelo mais " +
        "capaz, é aí que o laço custaria mais. A faixa vazia dele na trajetória é isso, visível.",
    ]),
    el("p", {}, [
      el("strong", { text: "ADR 0003 — enforcement de permissão pela API. " }),
      "Um 403 na trajetória é o enforcement funcionando, não falha do agente.",
    ]),
    el("p", {}, [
      el("strong", { text: "ADR 0007 — consulta livre com gabarito sintético. " }),
      "A questão de referência da aba ao vivo é escrita por um LLM, não por humano. As notas ordenam " +
        "consultas livres entre si e nunca entram nas métricas dos 17 cenários.",
    ]),
  ]);
}

export function desenhaGaveta(redesenha) {
  if (!ESTADO.gaveta) return null;
  const bundle = ESTADO.bundle;

  const corpos = {
    metodo: () => corpoMetodo(),
    ressalvas: () => corpoRessalvas(bundle),
    auditoria: () => corpoAuditoria(bundle, redesenha),
    arquitetura: () => corpoArquitetura(),
  };

  return el("div", { class: "gaveta-fundo", onclick: () => { ESTADO.gaveta = null; redesenha(); } }, [
    el(
      "div",
      {
        class: "gaveta",
        role: "dialog",
        "aria-label": "Método e ressalvas",
        onclick: (ev) => ev.stopPropagation(),
      },
      [
        el("div", { class: "gaveta-abas" }, [
          ...ABAS.map(([chave, rotulo]) =>
            el("button", {
              text: rotulo,
              "aria-selected": String(ESTADO.gaveta === chave),
              onclick: () => { ESTADO.gaveta = chave; redesenha(); },
            })
          ),
          el("button", {
            class: "gaveta-fechar",
            text: "fechar",
            onclick: () => { ESTADO.gaveta = null; redesenha(); },
          }),
        ]),
        (corpos[ESTADO.gaveta] || corpos.metodo)(),
      ]
    ),
  ]);
}
```

- [ ] **Step 4: Adicionar `gaveta` ao estado**

Em `painel/js/dados.js`, no objeto `ESTADO`, adicione:

```javascript
  gaveta: null,
```

- [ ] **Step 5: Adicionar o CSS da gaveta**

Ao final de `painel/css/painel.css`:

```css
/* -- gaveta -------------------------------------------------------------- */
.gaveta-fundo {
  position: fixed; inset: 0;
  background: color-mix(in oklab, var(--ardosia-900) 42%, transparent);
  display: flex; align-items: flex-end; justify-content: center;
  z-index: 50;
}

.gaveta {
  background: var(--superficie);
  border: 1px solid var(--regua);
  border-bottom: none;
  border-radius: var(--r) var(--r) 0 0;
  width: min(980px, 94vw);
  max-height: 78vh;
  display: flex; flex-direction: column;
  box-shadow: 0 -8px 28px color-mix(in oklab, var(--ardosia-900) 18%, transparent);
}

.gaveta-abas {
  display: flex; gap: 0;
  border-bottom: 1px solid var(--regua);
  background: var(--fundo);
}
.gaveta-abas button {
  padding: 11px 18px;
  font-size: var(--t-meta);
  color: var(--texto-fraco);
  background: none; border: none; border-right: 1px solid var(--faixa);
  cursor: pointer;
}
.gaveta-abas button[aria-selected="true"] { background: var(--sel-fundo); color: var(--sel-texto); }
.gaveta-abas .gaveta-fechar { margin-left: auto; border-right: none; }

.gaveta-corpo { padding: 20px 22px 26px; overflow-y: auto; }
.gaveta-corpo h3 { font-size: var(--t-h3); margin: 18px 0 8px; }
.gaveta-corpo h3:first-child { margin-top: 0; }
.gaveta-corpo p { font-size: var(--t-corpo); line-height: 1.55; max-width: 78ch; margin: 0 0 11px; }
.gaveta-meta { font-size: var(--t-mini); color: var(--texto-fraco); }

.gaveta-gatilho {
  border: 1px dashed var(--tenue-forte);
  border-radius: var(--r);
  background: none;
  color: var(--azul-neutro);
  font-size: var(--t-meta);
  padding: 4px 11px;
  cursor: pointer;
}
.gaveta-gatilho:hover { border-style: solid; }
```

- [ ] **Step 6: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 7 passed.

- [ ] **Step 7: Commit**

```bash
git add painel/js/gaveta.js painel/js/dados.js painel/css/painel.css painel/tests
git commit -m "feat: gaveta unica com metodo, ressalvas, auditoria e arquitetura"
```

---

### Task 5: Navegação por batidas

Substitui o sistema de abas. Depois desta tarefa o painel muda de forma visivelmente — as três abas viram quatro batidas, ainda que ② ③ ④ mostrem conteúdo provisório.

**Files:**
- Create: `painel/js/batidas.js`
- Modify: `painel/js/painel.js:1-165` (reescrita do ciclo de redesenho)
- Modify: `painel/js/dados.js` (estado)
- Modify: `painel/css/painel.css`

**Interfaces:**
- Consumes: `desenhaGaveta`, `botaoGaveta` de `gaveta.js`.
- Produces:
  - `BATIDAS` — array `[{chave, numero, rotulo}]` na ordem de apresentação.
  - `desenhaNav(redesenha) -> HTMLElement`.
  - `rodape(esquerda, direita) -> HTMLElement`.

- [ ] **Step 1: Write the failing test**

Adicione a `painel/tests/test_contrato.py`:

```python
def test_quatro_batidas_na_ordem_da_narrativa(js_fonte):
    """A ordem é o roteiro da demo: veredito, um caso, a matriz, ao vivo."""
    fonte = js_fonte("batidas.js")
    for chave in ("veredito", "chamado", "matriz", "aovivo"):
        assert f'"{chave}"' in fonte, f"batida {chave} ausente"
    assert fonte.index('"veredito"') < fonte.index('"chamado"')
    assert fonte.index('"chamado"') < fonte.index('"matriz"')
    assert fonte.index('"matriz"') < fonte.index('"aovivo"')


def test_painel_nao_tem_mais_abas_antigas(js_fonte):
    """Operação/Avaliação/Consulta eram audiências, não uma narrativa."""
    fonte = js_fonte("painel.js")
    assert 'botaoAba' not in fonte, "painel.js ainda usa o sistema de abas antigo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — `batidas.js` não existe.

- [ ] **Step 3: Criar `painel/js/batidas.js`**

```javascript
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
```

- [ ] **Step 4: Adicionar `batida` ao estado**

Em `painel/js/dados.js`, no `ESTADO`, adicione (e mantenha `aba` por ora — a Task 9 a remove):

```javascript
  batida: "veredito",
```

- [ ] **Step 5: Reescrever `painel/js/painel.js`**

Substitua o arquivo inteiro:

```javascript
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
            "`python painel/build_bundle.py` e sirva a pasta por HTTP: `make painel`.",
        ]),
      ])
    );
  });
```

- [ ] **Step 6: Criar stubs das quatro batidas**

As Tasks 6-9 preenchem cada uma. Crie os quatro arquivos agora para o módulo carregar:

`painel/js/batida-veredito.js`:
```javascript
import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaVeredito(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "veredito — Task 6" })]),
    rodape(redesenha),
  ]);
}
```

`painel/js/batida-chamado.js`:
```javascript
import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaChamado(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "um chamado — Task 7" })]),
    rodape(redesenha),
  ]);
}
```

`painel/js/batida-matriz.js`:
```javascript
import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaMatriz(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "os 17 × 3 — Task 8" })]),
    rodape(redesenha),
  ]);
}
```

`painel/js/batida-aovivo.js`:
```javascript
import { el } from "./dados.js";
import { rodape } from "./batidas.js";
export function batidaAoVivo(redesenha) {
  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, [el("p", { text: "ao vivo — Task 9" })]),
    rodape(redesenha),
  ]);
}
```

- [ ] **Step 7: Adicionar o CSS de layout das batidas**

Ao final de `painel/css/painel.css`:

```css
/* -- layout das batidas -------------------------------------------------- */
.batidas-nav { display: flex; gap: 0; }
.batidas-nav button {
  padding: 10px 16px;
  font-size: var(--t-meta);
  color: var(--texto-fraco);
  background: none; border: none; border-right: 1px solid var(--faixa);
  cursor: pointer;
}
.batidas-nav button[aria-selected="true"] { background: var(--sel-fundo); color: var(--sel-texto); }

.batida {
  display: flex; flex-direction: column;
  min-height: calc(100vh - 58px);
}
.batida-corpo { flex: 1; padding: 26px 30px; overflow-y: auto; }

.batida-rodape {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 30px;
  background: var(--superficie);
  border-top: 1px solid var(--regua);
  font-size: var(--t-meta);
  color: var(--texto-fraco);
}
.passos { display: flex; gap: 12px; }
.passo {
  background: none; border: none; cursor: pointer;
  color: var(--texto-fraco); font-size: var(--t-meta);
}
.passo:hover { color: var(--texto); }
```

- [ ] **Step 8: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 9 passed.

- [ ] **Step 9: Verificar no navegador**

Run: `make painel`
Confirme: quatro batidas na barra; clicar navega; setas ← → do teclado navegam; o botão `ⓘ método e ressalvas` abre a gaveta com as quatro abas; `Esc` fecha.

- [ ] **Step 10: Commit**

```bash
git add painel/js/batidas.js painel/js/painel.js painel/js/batida-*.js painel/js/dados.js painel/css/painel.css painel/tests
git commit -m "feat: navegacao por quatro batidas substituindo o sistema de abas"
```

---

### Task 6: Batida ① — veredito

**Files:**
- Modify: `painel/js/batida-veredito.js` (substitui o stub)
- Modify: `painel/css/painel.css`
- Modify: `painel/tests/test_contrato.py`

**Interfaces:**
- Consumes: `rodape` de `batidas.js`; `bundle.agregados` do bundle.
- Produces: `batidaVeredito(redesenha) -> HTMLElement`.

- [ ] **Step 1: Write the failing test**

O risco aqui é número inventado no renderizador. Adicione a `painel/tests/test_contrato.py`:

```python
def test_veredito_nao_faz_aritmetica_a_mao(js_fonte):
    """Todo agregado da batida ① vem do bundle.

    Durante o desenho eu escrevi "48 de 51" por dedução antes de conferir. Bateu,
    mas o hábito é a falha: um número derivado no renderizador não é auditável
    contra o bundle e ninguém percebe quando fica errado.
    """
    fonte = js_fonte("batida-veredito.js")
    assert "agregados" in fonte, "a batida ① precisa ler bundle.agregados"
    # Nenhum literal percentual escrito na mão.
    import re
    assert not re.search(r'"\d{1,3},\d%"', fonte), "percentual literal no código"


def test_delta_entre_fases_vem_das_duas_fases(bundle):
    """A seta baseline → pós-correção substitui o dropdown de fase."""
    base = bundle["agregados"]["baseline"]["acuracia_decisao"]
    pos = bundle["agregados"]["pos-correcao"]["acuracia_decisao"]
    assert pos > base, "a narrativa da batida ① depende do ganho entre fases"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — o stub não contém `"agregados"`.

- [ ] **Step 3: Escrever `painel/js/batida-veredito.js`**

```javascript
/* Batida ① — funciona?
 *
 * Uma tela, um número. O ganho entre fases vira uma seta em vez de um dropdown
 * que a banca teria de descobrir sozinha. Tudo aqui vem de `bundle.agregados`:
 * nenhum número desta tela é calculado neste arquivo. */

import { el, ESTADO, pct, num } from "./dados.js";
import { rodape } from "./batidas.js";

/** Delta em pontos percentuais, formatado com sinal. */
function deltaPp(depois, antes) {
  const d = (depois - antes) * 100;
  return `${d >= 0 ? "+" : ""}${d.toFixed(1)} pp`;
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

    el("div", { class: "veredito-tiles" }, [
      tile(num(pos.falhas_execucao), "falhas de execução"),
      tile(deltaCusto(pos.tokens_medio, base.tokens_medio), "tokens por caso", "baixa"),
      tile(deltaCusto(pos.chamadas_media, base.chamadas_media), "chamadas por caso", "baixa"),
      tile(deltaCusto(pos.taxa_repeticao_media, base.taxa_repeticao_media), "consultas repetidas", "baixa"),
    ]),

    el("p", { class: "veredito-frase" }, [
      "Decidiu certo em ",
      el("b", { text: `${Math.round(pos.acuracia_decisao * pos.execucoes)} de ${pos.execucoes}` }),
      " execuções — e ficou mais barato no caminho.",
    ]),
  ]);

  return el("main", { class: "batida" }, [corpo, rodape(redesenha)]);
}
```

- [ ] **Step 4: Adicionar o CSS da batida ①**

Ao final de `painel/css/painel.css`:

```css
/* -- batida ① veredito --------------------------------------------------- */
.veredito { display: flex; flex-direction: column; justify-content: center; gap: 26px; }

.veredito-numero b {
  display: block;
  font-size: var(--t-metrica);
  font-weight: 500;
  letter-spacing: -0.03em;
  line-height: 0.94;
}
.veredito-numero small {
  display: block;
  font-size: var(--t-leitura);
  color: var(--texto-fraco);
  margin-top: 10px;
}

.veredito-seta { font-size: var(--t-leitura); color: var(--texto-fraco); }
.veredito-seta b { color: var(--texto); font-size: 26px; font-weight: 500; margin: 0 4px; }
.veredito-seta .seta { color: var(--verde-exec); margin: 0 12px; }
.veredito-seta .ganho { color: var(--verde-exec); font-weight: 500; margin-left: 10px; }

.veredito-tiles {
  display: flex; gap: 40px;
  padding-top: 22px;
  border-top: 1px solid var(--regua);
}
.veredito-tiles .tile span { display: block; font-size: 30px; font-weight: 500; line-height: 1.1; }
.veredito-tiles .tile span.baixa { color: var(--azul-neutro); }
.veredito-tiles .tile em { font-style: normal; font-size: var(--t-meta); color: var(--texto-fraco); }

.veredito-frase { font-size: 21px; line-height: 1.45; max-width: 36ch; color: var(--texto); }
```

- [ ] **Step 5: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 11 passed.

- [ ] **Step 6: Verificar no navegador**

Run: `make painel`
Confirme: `94,1%` grande; seta `86,3% ──▶ 94,1% +7,8 pp`; quatro tiles com `0 falhas`, `−4%`, `−8%`, `−54%`; a frase diz `48 de 51`. Alterne o tema e confirme que a seta e o ganho continuam legíveis.

- [ ] **Step 7: Commit**

```bash
git add painel/js/batida-veredito.js painel/css/painel.css painel/tests
git commit -m "feat: batida 1 veredito com delta entre fases"
```

---

### Task 7: Batida ② — um chamado

**Files:**
- Modify: `painel/js/batida-chamado.js` (substitui o stub)
- Modify: `painel/css/painel.css`
- Modify: `painel/tests/test_contrato.py`

**Interfaces:**
- Consumes: `faixasPorPapel` de `faixas.js`; `filaVisivel` de `dados.js`.
- Produces: `batidaChamado(redesenha) -> HTMLElement`.

- [ ] **Step 1: Write the failing test**

Adicione a `painel/tests/test_contrato.py` (e atualize o teste de RN-01 da Task 2 para cobrir o módulo novo):

```python
def test_batida_chamado_respeita_rn01(js_fonte):
    """A batida ② é a visão de quem atende: não pode ler o gabarito."""
    fonte = js_fonte("batida-chamado.js")
    assert "avaliacao.js" not in imports_de(fonte), "RN-01 quebrado na batida ②"
    for proibido in ("passou", "decision_match", "aprovacao"):
        assert proibido not in fonte, f"batida ② expôs `{proibido}` — RN-01"


def test_resposta_final_nao_e_truncada(js_fonte):
    """RN-16: a resposta ao cliente é o produto entregue, e vai íntegra."""
    fonte = js_fonte("batida-chamado.js")
    assert ".slice(" not in fonte, "truncamento na batida ② — RN-16"
    assert "substring" not in fonte, "truncamento na batida ② — RN-16"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — o stub não importa `faixas.js` e os asserts de conteúdo falham por ausência do arquivo real.

- [ ] **Step 3: Escrever `painel/js/batida-chamado.js`**

```javascript
/* Batida ② — por quê?
 *
 * REGRA INEGOCIÁVEL (RN-01): esta tela nunca exibe gabarito, decisão aceita ou
 * status de aprovação. Nem em texto, nem em cor, nem em tooltip. A regra é
 * estrutural: este módulo lê apenas `execucao.operacao` e não importa nada de
 * `avaliacao.js` nem de `batida-matriz.js`. Verificável por leitura de import. */

import {
  ESTADO, el, texto, num, duracao, VAZIO,
  PAPEIS_PT, filaVisivel, DECISOES,
} from "./dados.js";
import { selo, seloDecisao, vazio } from "./componentes.js";
import { faixasPorPapel } from "./faixas.js";
import { rodape } from "./batidas.js";

/** Markdown mínimo da resposta ao cliente. Escapa antes de formatar: veio de um LLM. */
function markdownSimples(bruto) {
  if (!bruto || !String(bruto).trim()) return "não determinado";
  return String(bruto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function kpi(valor, rotulo) {
  return el("div", { class: "kpi-item" }, [
    el("span", { text: valor }),
    el("em", { text: rotulo }),
  ]);
}

/** Seletor de caso: a fila antiga vira gaveta lateral desta batida. */
function seletorCaso(execucao, redesenha) {
  const aberta = ESTADO.filaAberta;
  const gatilho = el("button", {
    class: "seletor-caso mono",
    "aria-expanded": String(aberta),
    text: `${execucao.ticket_id} ⌄`,
    onclick: () => {
      ESTADO.filaAberta = !aberta;
      redesenha();
    },
  });

  if (!aberta) return gatilho;

  const lista = filaVisivel().map((e) =>
    el("button", {
      class: "fila-item",
      "aria-current": String(e.id === ESTADO.execucaoId),
      onclick: () => {
        ESTADO.execucaoId = e.id;
        ESTADO.filaAberta = false;
        redesenha();
      },
    }, [
      el("span", { class: "ticket mono", text: e.ticket_id }),
      el("span", { class: "cenario", text: e.cenario }),
      seloDecisao(e.operacao.decisao),
    ])
  );

  return el("div", { class: "seletor-wrap" }, [
    gatilho,
    el("div", { class: "fila-gaveta" }, [
      el("input", {
        type: "search",
        placeholder: "Buscar ticket, ativo, empresa ou mensagem",
        value: ESTADO.busca,
        "aria-label": "Buscar chamado",
        oninput: (ev) => {
          ESTADO.busca = ev.target.value;
          redesenha();
        },
      }),
      el("div", { class: "fila" }, lista.length ? lista : [vazio("Nenhum chamado corresponde.")]),
    ]),
  ]);
}

export function batidaChamado(redesenha) {
  const execucao = ESTADO.bundle.execucoes.find((e) => e.id === ESTADO.execucaoId);

  if (!execucao) {
    return el("main", { class: "batida" }, [
      el("div", { class: "batida-corpo" }, [vazio("Selecione um chamado.")]),
      rodape(redesenha),
    ]);
  }

  const op = execucao.operacao;
  const solicitante = op.solicitante || {};
  const ativo = op.ativo || {};
  const consumo = op.consumo || {};
  const chamadasApi = op.timeline.filter((e) => e.tipo === "chamada").length;

  const corpo = el("div", { class: "batida-corpo" }, [
    el("div", { class: "chamado-cabeca" }, [
      seletorCaso(execucao, redesenha),
      selo(execucao.cenario, "quieto", { class: "selo selo-quieto mono" }),
      seloDecisao(op.decisao),
      selo(
        `${texto(ativo.name)} · criticidade ${texto(ativo.criticality)}`,
        ativo.criticality === "high" ? "atencao" : "quieto"
      ),
      selo(
        `${texto(solicitante.name)} · ${PAPEIS_PT[solicitante.role] || texto(solicitante.role)}`,
        "quieto"
      ),
    ]),

    // Mensagem íntegra do cliente. Borda lateral aqui significa citação literal —
    // e é o único lugar do painel onde ela significa isso.
    el("blockquote", { class: "mensagem", text: texto(op.mensagem) }),

    el("div", { class: "kpis" }, [
      kpi(num(consumo.llm_calls), "chamadas de LLM"),
      kpi(num(chamadasApi), "chamadas de API"),
      kpi(num(consumo.total_tokens), "tokens"),
      kpi(duracao(op.duracao_ms), "duração"),
      kpi(texto(op.stop_reason), "parada"),
    ]),

    faixasPorPapel(execucao, ESTADO, redesenha),

    el("div", { class: "bloco-resposta" }, [
      el("div", { class: "rotulo-cru", text: "resposta entregue ao cliente" }),
      // RN-16: íntegra, sem truncar.
      el("div", { class: "resposta-final", html: markdownSimples(op.resposta_final) }),
    ]),
  ]);

  return el("main", { class: "batida" }, [
    corpo,
    rodape(redesenha, ["ⓘ arquitetura dos papéis", "arquitetura"]),
  ]);
}
```

- [ ] **Step 4: Adicionar `filaAberta` ao estado**

Em `painel/js/dados.js`, no `ESTADO`:

```javascript
  filaAberta: false,
```

- [ ] **Step 5: Adicionar o CSS da batida ②**

Ao final de `painel/css/painel.css`:

```css
/* -- batida ② um chamado ------------------------------------------------- */
.chamado-cabeca { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }

.seletor-wrap { position: relative; }
.seletor-caso {
  font-size: var(--t-h1);
  font-weight: 500;
  background: none; border: none; cursor: pointer;
  color: var(--texto);
  padding: 0;
}
.fila-gaveta {
  position: absolute; top: 100%; left: 0; z-index: 20;
  width: 420px; max-height: 60vh; overflow-y: auto;
  background: var(--superficie);
  border: 1px solid var(--regua);
  border-radius: var(--r);
  box-shadow: 0 6px 20px color-mix(in oklab, var(--ardosia-900) 16%, transparent);
  padding: 10px;
}
.fila-gaveta input { width: 100%; margin-bottom: 8px; }

.kpis {
  display: flex; gap: 30px;
  padding: 14px 0 15px;
  border-bottom: 1px solid var(--regua);
  margin-bottom: 0;
}
.kpi-item span { display: block; font-size: 26px; font-weight: 500; line-height: 1.1; }
.kpi-item em { font-style: normal; font-size: var(--t-meta); color: var(--texto-fraco); }

.bloco-resposta { margin-top: 18px; }
.resposta-final {
  background: var(--superficie);
  border: 1px solid var(--regua);
  border-radius: var(--r);
  padding: 14px 16px;
  font-size: var(--t-corpo);
  line-height: 1.6;
  max-width: 88ch;
}
```

- [ ] **Step 6: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 13 passed.

- [ ] **Step 7: Verificar no navegador**

Run: `make painel`
Na batida ②, confirme: abre em `TKT-INV-09`; a faixa do **decisor** mostra "zero consultas — não tem tools (ADR 0002)"; as tags do investigador incluem `baseline.state invalidated` e `analysis.id ... status=stale`; **nenhum endpoint visível** até clicar em `5 consultas ⌄`; a resposta final aparece inteira; clicar no ticket abre a fila com busca.

- [ ] **Step 8: Commit**

```bash
git add painel/js/batida-chamado.js painel/js/dados.js painel/css/painel.css painel/tests
git commit -m "feat: batida 2 um chamado com faixas por papel e endpoints sob demanda"
```

---

### Task 8: Batida ③ — a matriz

**Files:**
- Modify: `painel/js/batida-matriz.js` (substitui o stub)
- Modify: `painel/css/painel.css`
- Modify: `painel/tests/test_contrato.py`

**Interfaces:**
- Consumes: `tomDaCelula` e `drilldown` (movidos de `avaliacao.js`); `abreGaveta` de `gaveta.js`.
- Produces: `batidaMatriz(redesenha) -> HTMLElement`.

- [ ] **Step 1: Write the failing test**

Adicione a `painel/tests/test_contrato.py`:

```python
def test_matriz_usa_quatro_categorias(js_fonte):
    """Escalar nunca é vermelho, e reprovação com decisão certa é atenção, não erro."""
    fonte = js_fonte("batida-matriz.js")
    for tom in ("sucesso", "neutro", "atencao", "erro"):
        assert f'"{tom}"' in fonte, f"categoria {tom} ausente na matriz"


def test_estabilidade_virou_selo_e_nao_secao(bundle):
    """17/17 estáveis é um selo, não uma seção.

    Se algum dia deixar de ser 17/17, o selo passa a mentir e a batida ③ precisa
    de revisão — por isso o teste falha em vez de o painel exibir um número errado.
    """
    casos = [c for c in bundle["casos"] if c["por_fase"].get("pos-correcao")]
    mediveis = [c for c in casos if c["por_fase"]["pos-correcao"]["estabilidade"]["medivel"]]
    estaveis = [c for c in mediveis if c["por_fase"]["pos-correcao"]["estabilidade"]["estavel"]]
    assert len(estaveis) == len(mediveis), "a premissa do selo mudou — revisar a batida ③"


def test_campos_do_diff_existem_no_bundle(bundle):
    """A gaveta lateral da batida ③ lê estes campos; nomes inventados renderizam vazio."""
    av = bundle["execucoes"][0]["avaliacao"]
    for campo in ("decisoes_aceitas", "queries_faltantes", "queries_extras",
                  "acoes_faltantes", "diff_trajetoria"):
        assert campo in av, f"campo {campo} ausente — a batida ③ contava com ele"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — o stub não tem as categorias, e `avaliacao.js` ainda define `estabilidade`.

- [ ] **Step 3: Escrever `painel/js/batida-matriz.js`**

```javascript
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
```

- [ ] **Step 4: Adicionar o CSS da batida ③**

Ao final de `painel/css/painel.css`:

```css
/* -- batida ③ matriz ----------------------------------------------------- */
.matriz-layout { display: grid; grid-template-columns: 1fr 300px; gap: 22px; align-items: start; }

.matriz-cabeca { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.matriz-cabeca h2 { font-size: var(--t-h2); margin: 0; }

.matriz { border-collapse: collapse; width: 100%; }
.matriz th {
  font-size: var(--t-mini); font-weight: 500; color: var(--texto-fraco);
  text-align: left; padding: 5px 7px; border-bottom: 1px solid var(--regua);
}
.matriz td { padding: 0; border-bottom: 1px solid var(--faixa); }
.mx-cen { font-size: var(--t-meta); padding: 5px 8px; white-space: nowrap; }

.celula {
  display: block; width: 100%; height: 27px;
  font-size: var(--t-mini);
  border: 1px solid; border-radius: var(--r);
  margin: 2px; cursor: pointer;
}
.celula-sucesso { background: var(--verde-fundo);    border-color: var(--verde-exec);    color: var(--verde-exec); }
.celula-neutro  { background: var(--azul-fundo);     border-color: var(--azul-neutro);   color: var(--azul-neutro); }
.celula-atencao { background: var(--ambar-fundo);    border-color: var(--ambar-atencao); color: var(--ambar-atencao); }
.celula-erro    { background: var(--vermelho-fundo); border-color: var(--vermelho-erro); color: var(--vermelho-erro); }
.celula[aria-current="true"] { outline: 2px solid var(--acento); outline-offset: 1px; }
.celula.vazia { background: none; border-color: var(--faixa); color: var(--texto-ausente); cursor: default; }

.legenda { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 12px; font-size: var(--t-meta); color: var(--texto-fraco); }
.legenda i {
  display: inline-block; width: 11px; height: 11px;
  border-radius: 2px; border: 1px solid;
  margin-right: 5px; vertical-align: -1px;
}

.matriz-lateral {
  background: var(--superficie);
  border: 1px solid var(--regua);
  border-radius: var(--r);
  padding: 14px 15px;
  position: sticky; top: 20px;
}
.matriz-lateral h3 { font-size: var(--t-h3); margin: 0 0 10px; }
.lateral-bloco { margin-top: 12px; }
.lateral-bloco ul { margin: 4px 0 0; padding-left: 18px; font-size: var(--t-mini); }
.lateral-nota {
  margin-top: 14px; padding: 10px 11px;
  background: var(--tonal-atencao);
  border: 1px solid var(--ambar-atencao);
  border-radius: var(--r);
  font-size: var(--t-meta); line-height: 1.5;
}
.lateral-nota .gaveta-gatilho { margin-top: 8px; display: inline-block; }

.diff-lista { list-style: none; padding: 0; margin: 4px 0 0; }
.diff-lista li {
  font-size: var(--t-mini);
  padding: 3px 0 3px 14px;
  position: relative;
}
/* O marcador carrega a situação do passo; a cor sozinha não bastaria. */
.diff-lista li::before { position: absolute; left: 0; }
.diff-atendida::before { content: "✓"; color: var(--verde-exec); }
.diff-faltante::before { content: "×"; color: var(--ambar-atencao); }
.diff-lista em { display: block; font-style: normal; color: var(--texto-fraco); }
```

- [ ] **Step 5: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 16 passed.

- [ ] **Step 6: Verificar no navegador**

Run: `make painel`
Na batida ③, confirme: 17 linhas × 3 colunas; selos `17/17 estáveis`, `0 falhas de execução`, `1 erro real · 8 artefatos de gabarito`; CEN-09 em vermelho nas três seeds; clicar numa célula amarela mostra a nota do artefato com o botão para a gaveta; o link "ver este chamado na batida ②" navega e carrega o caso certo.

- [ ] **Step 7: Commit**

```bash
git add painel/js/batida-matriz.js painel/css/painel.css painel/tests
git commit -m "feat: batida 3 matriz com diff lateral da trajetoria"
```

---

### Task 9: Batida ④ — ao vivo, e limpeza final

**Files:**
- Modify: `painel/js/batida-aovivo.js` (substitui o stub)
- Modify: `painel/js/consulta.js` (encolhe o formulário)
- Delete: `painel/js/operacao.js`, `painel/js/avaliacao.js`
- Modify: `painel/js/dados.js` (remove `aba` do estado)
- Modify: `painel/README.md`
- Modify: `painel/tests/test_contrato.py`

**Interfaces:**
- Consumes: `faixasPorPapel` de `faixas.js`; `CONSULTA` e `enviaConsulta` de `consulta.js`.
- Produces: `batidaAoVivo(redesenha) -> HTMLElement`.

- [ ] **Step 1: Write the failing test**

Adicione a `painel/tests/test_contrato.py`:

```python
def test_selo_sintetico_e_permanente(js_fonte):
    """ADR 0007: a nota da consulta livre nunca se mistura com as dos 17 cenários.

    O selo é a fronteira visível dessa separação. Se ele sair da tela, um leitor
    passa a somar duas medidas que não são a mesma coisa.
    """
    fonte = js_fonte("batida-aovivo.js")
    assert "sintética" in fonte or "sintetica" in fonte, "selo de avaliação sintética ausente"
    assert "0007" in fonte, "referência à ADR 0007 ausente"


def test_modulos_antigos_removidos(js_fonte):
    """operacao.js e avaliacao.js foram absorvidos pelas batidas."""
    import pytest
    for morto in ("operacao.js", "avaliacao.js"):
        with pytest.raises(FileNotFoundError):
            js_fonte(morto)


def test_nenhuma_batida_importa_modulo_morto(js_fonte):
    for modulo in ("painel.js", "batida-veredito.js", "batida-chamado.js",
                   "batida-matriz.js", "batida-aovivo.js"):
        fonte = js_fonte(modulo)
        assert "operacao.js" not in fonte
        assert "avaliacao.js" not in fonte
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd painel && python -m pytest tests/ -q`
Expected: FAIL — os módulos antigos ainda existem e o stub não tem o selo.

- [ ] **Step 3: Escrever `painel/js/batida-aovivo.js`**

```javascript
/* Batida ④ — de verdade?
 *
 * Executa o agente ao vivo. A espera é honesta: 15 a 25 segundos ditos em voz alta,
 * com os papéis acendendo conforme avançam. Sem streaming incremental — isso exigiria
 * emitir eventos de `agent/server.py`, e a decisão foi manter o redesenho contido em
 * `painel/`. Quando termina, reusa o desenho da batida ②.
 *
 * O selo de avaliação sintética (ADR 0007) é permanente: é a fronteira que impede a
 * nota da consulta livre de ser lida junto com as métricas dos 17 cenários. */

import { ESTADO, el, texto, num, duracao } from "./dados.js";
import { selo, aviso, vazio } from "./componentes.js";
import { faixasPorPapel } from "./faixas.js";
import { rodape } from "./batidas.js";
// `envia` é o nome real da função em consulta.js:97 — hoje sem `export`.
import { CONSULTA, carregaCatalogo, envia } from "./consulta.js";

const PAPEIS_ESPERADOS = ["supervisor", "investigador", "decisor", "executor"];

function formulario(redesenha) {
  const { form } = CONSULTA;
  const pronto = form.user_id && form.mensagem.trim().length >= 10 && !CONSULTA.enviando;

  return el("div", { class: "aovivo-form" }, [
    el(
      "select",
      {
        "aria-label": "Quem está perguntando",
        onchange: (ev) => { form.user_id = ev.target.value; redesenha(); },
      },
      [
        el("option", { value: "", text: "quem pergunta…" }),
        ...CONSULTA.usuarios.map((u) =>
          el("option", {
            value: u.user_id,
            text: `${u.name} · ${u.role}`,
            selected: form.user_id === u.user_id,
          })
        ),
      ]
    ),
    el(
      "select",
      {
        "aria-label": "Qual ativo",
        onchange: (ev) => { form.asset_id = ev.target.value; redesenha(); },
      },
      [
        el("option", { value: "", text: "qual ativo…" }),
        ...CONSULTA.ativos.map((a) =>
          el("option", { value: a.asset_id, text: a.name, selected: form.asset_id === a.asset_id })
        ),
      ]
    ),
    el("input", {
      type: "text",
      class: "aovivo-mensagem",
      placeholder: "o que a pessoa observou, com as palavras dela",
      value: form.mensagem,
      oninput: (ev) => { form.mensagem = ev.target.value; },
    }),
    el("button", {
      class: "botao-primario",
      text: CONSULTA.enviando ? "investigando…" : "perguntar",
      disabled: !pronto,
      onclick: () => envia(redesenha),
    }),
  ]);
}

function esperando() {
  const feitos = new Set(CONSULTA.papeisVistos || []);
  return el("div", { class: "aovivo-espera" }, [
    el("div", { class: "girando" }),
    el("div", { class: "espera-titulo", text: "O agente está investigando…" }),
    el("div", {
      class: "espera-nota",
      text: "costuma levar 15 a 25 segundos · mesmo grafo dos 17 cenários",
    }),
    el(
      "div",
      { class: "espera-papeis" },
      PAPEIS_ESPERADOS.map((p) =>
        el("span", {
          class: `fato ${feitos.has(p) ? "fato-sucesso" : "fato-quieto"}`,
          text: feitos.has(p) ? `${p} ✓` : p,
        })
      )
    ),
  ]);
}

function resultado(registro, redesenha) {
  // O servidor devolve um trace no mesmo formato do bundle: as faixas funcionam igual.
  const execucao = {
    id: registro.id,
    operacao: registro.operacao || registro.trace,
  };

  return el("div", {}, [
    faixasPorPapel(execucao, ESTADO, redesenha),
    el("div", { class: "bloco-resposta" }, [
      el("div", { class: "rotulo-cru", text: "resposta entregue" }),
      el("div", { class: "resposta-final", text: texto((registro.trace || {}).final_answer) }),
    ]),
  ]);
}

export function batidaAoVivo(redesenha) {
  if (!CONSULTA.carregouCatalogo) {
    carregaCatalogo(redesenha);
    return el("main", { class: "batida" }, [
      el("div", { class: "batida-corpo" }, [vazio("Carregando catálogo…")]),
      rodape(redesenha),
    ]);
  }

  const partes = [formulario(redesenha)];

  if (CONSULTA.erroCatalogo) {
    partes.push(
      aviso("atencao", [
        el("strong", { text: "O agente não está no ar. " }),
        "Esta batida executa o agente ao vivo. Suba com `make consulta`.",
      ])
    );
  } else if (CONSULTA.enviando) {
    partes.push(esperando());
  } else if (CONSULTA.erroEnvio) {
    partes.push(aviso("erro", [el("strong", { text: "Falha na consulta. " }), CONSULTA.erroEnvio]));
  } else if (CONSULTA.resultado) {
    partes.push(resultado(CONSULTA.resultado, redesenha));
  }

  return el("main", { class: "batida" }, [
    el("div", { class: "batida-corpo" }, partes),
    el("footer", { class: "batida-rodape" }, [
      el("div", { class: "passos" }, [
        el("button", {
          class: "passo",
          text: "← os 17 × 3",
          onclick: () => { ESTADO.batida = "matriz"; redesenha(); },
        }),
      ]),
      el("div", { class: "rodape-direita" }, [
        selo("avaliação sintética — ADR 0007", "atencao", {
          title:
            "A questão de referência é escrita por um LLM, não por humano. As notas ordenam " +
            "consultas livres entre si e nunca entram nas métricas dos 17 cenários.",
        }),
      ]),
    ]),
  ]);
}
```

- [ ] **Step 4: Expor o que a batida ④ consome de `consulta.js`**

Estado atual verificado: `consulta.js` exporta apenas `CONSULTA` (linha 28), `carregaCatalogo` (63) e `desenhaConsulta` (142). A função de envio chama-se **`envia`** (linha 97) e **não** está exportada.

Faça três coisas:

1. Adicione `export` a `async function envia(redesenha)`. Não renomeie — `envia(redesenha)` já é claro no ponto de uso, e renomear espalha churn por um ganho nulo.
2. Adicione `papeisVistos: []` ao objeto `CONSULTA`, e em `envia`, ao receber a resposta, popule-o com os papéis presentes no trace (`[...new Set(trace.steps.map(s => s.agent).filter(Boolean))]`, ou equivalente conforme o formato real da resposta).
3. Remova `desenhaConsulta` e as funções de layout que a batida ④ substitui: `primeiraVez`, `painelOffline`, `avisoAvaliacaoIndisponivel`, `formulario`, `seletorJuizes`, `campo`, `fichaPermissoes`, `resultado`, `secaoAvaliacao`, `blocoGabarito`, `blocoJuizes`, `historico`.

**Mantenha** `blocoErroExecucao` e `diagnosticaErro`: classificam a falha pelo que o leitor precisa fazer a seguir (esperar, trocar de modelo, ou consertar o agente), e isso não sai de um stack trace. Se após a remoção elas ficarem sem chamador, exporte-as — a batida ④ as usa no ramo de `erroEnvio`.

- [ ] **Step 5: Apagar os módulos absorvidos e limpar o estado**

```bash
git rm painel/js/operacao.js painel/js/avaliacao.js
```

Em `painel/js/dados.js`, remova a chave `aba` do `ESTADO` (a navegação agora é `batida`).

- [ ] **Step 6: Adicionar o CSS da batida ④**

Ao final de `painel/css/painel.css`:

```css
/* -- batida ④ ao vivo ---------------------------------------------------- */
.aovivo-form { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 18px; }
.aovivo-mensagem { flex: 1; min-width: 320px; }

.aovivo-espera {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 14px; padding: 60px 20px;
}
.girando {
  width: 36px; height: 36px;
  border: 3px solid var(--regua);
  border-top-color: var(--acento);
  border-radius: 50%;
  animation: girar 0.9s linear infinite;
}
@keyframes girar { to { transform: rotate(360deg); } }

.espera-titulo { font-size: var(--t-leitura); }
.espera-nota { font-size: var(--t-meta); color: var(--texto-fraco); }
.espera-papeis { display: flex; gap: 8px; margin-top: 4px; }

.rodape-direita { display: flex; gap: 10px; align-items: center; }

@media (prefers-reduced-motion: reduce) {
  .girando { animation-duration: 3s; }
}
```

- [ ] **Step 7: Atualizar o README do painel**

Em `painel/README.md`, substitua a seção "Três abas, três leitores" por:

```markdown
## Quatro batidas, uma narrativa

O painel é um roteiro de demonstração, não um conjunto de abas por audiência. A ordem
importa: cada batida responde a pergunta que a anterior provoca.

**① Veredito** — funciona? A acurácia de decisão da pós-correção, e o ganho sobre o
baseline como uma seta. Tudo vem de `bundle.agregados`.

**② Um chamado** — por quê? Um atendimento ponta a ponta em faixas por papel. As tags
mostram os fatos apurados; os endpoints ficam atrás de `N consultas ⌄`. Esta tela nunca
exibe gabarito nem aprovação (RN-01), e a regra é estrutural: `batida-chamado.js` não
importa nada de avaliação.

**③ Os 17 × 3** — sempre? A matriz de cenários por seed. Clicar numa célula abre o diff
entre a trajetória esperada e a percorrida.

**④ Ao vivo** — de verdade? Executa o agente. A avaliação volta marcada como sintética
(ADR 0007) e nunca entra nas métricas dos 17 cenários.

Setas ← → do teclado avançam a narrativa. O botão do rodapé abre a gaveta com método,
ressalvas, auditoria e arquitetura — é onde vive toda a prosa que antes disputava espaço
com os números.
```

- [ ] **Step 8: Run tests**

Run: `cd painel && python -m pytest tests/ -q`
Expected: PASS — 18 passed.

- [ ] **Step 9: Verificar as quatro batidas no navegador**

Run: `make consulta`

Percorra o roteiro inteiro como na banca:
- ① mostra `94,1%`, a seta e os quatro tiles.
- → vai para ②, `TKT-INV-09`, faixa do decisor vazia, nenhum endpoint visível.
- → vai para ③, CEN-09 vermelho nas 3 seeds, célula amarela abre a nota do artefato.
- → vai para ④, formulário de uma linha, envia uma consulta e confirma a espera honesta e o selo sintético.
- A gaveta abre nas quatro e o `Esc` fecha.
- Alterne o tema em cada batida.
- Nenhuma batida rola verticalmente em 1920×1080.

- [ ] **Step 10: Commit**

```bash
git add -A painel/
git commit -m "feat: batida 4 ao vivo; remove operacao.js e avaliacao.js absorvidos"
```

---

## Self-Review

**Cobertura da spec:** as quatro batidas têm tarefa (6, 7, 8, 9); a gaveta tem a Task 4 com as quatro abas; as faixas por papel têm a Task 3; a navegação tem a Task 5; a escala tipográfica tem a Task 2. `secao()` com nota obrigatória deixa de ser usada quando `operacao.js` e `avaliacao.js` saem na Task 9 — a assinatura antiga fica em `componentes.js` sem chamador nas batidas, o que é aceitável porque `componentes.js` mantém `selo`, `metrica` e `vazio`, que continuam em uso. A fila de chamados vira gaveta lateral na Task 7. A auditoria e o CSV migram na Task 4. `juizes()` fica sem chamador, renderizado condicionalmente pela gaveta.

**Placeholders:** nenhum. A primeira versão da Task 2 tinha um teste deliberadamente quebrado para o executor consertar; foi substituído por testes completos, porque um passo que pede para escrever código errado é um placeholder disfarçado.

**Consistência de tipos:** `faixasPorPapel(execucao, estado, redesenha)` tem a mesma assinatura nas Tasks 3, 7 e 9. `rodape(redesenha, gatilho)` idem nas Tasks 5-9. `ESTADO` ganha `faixasAbertas` (Task 3), `gaveta` (Task 4), `batida` (Task 5) e `filaAberta` (Task 7), e perde `aba` (Task 9).

**Risco conhecido:** a Task 9 assume que o trace devolvido pelo servidor da consulta tem o mesmo formato de `execucao.operacao` (campos `timeline`, `achados`, `consumo`). Se divergir, `faixasPorPapel` renderiza vazio em vez de quebrar. O executor deve confirmar isso no Step 9 e, se divergir, adaptar em `resultado()` — não em `faixas.js`, que é compartilhado com a batida ②.
