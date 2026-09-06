"""Mutação de evidência para o EXP-07 — reescreve a resposta da API antes do agente ler.

O experimento pergunta se a decisão do agente é causada pela evidência apurada ou pelo
enunciado do chamado. Para separar as duas, um braço da execução recebe a resposta íntegra
da API e outro recebe a mesma resposta com o campo que o gabarito
(`tractian/eval/expected-paths.json`) nomeia como decisivo invertido de valor.

**Por que interceptar em vez de gravar e reproduzir.** A API industrial roda local e já é
determinística por seed; um mock de replay não economizaria nada e teria furo de cobertura,
porque quem escolhe o próximo endpoint é o LLM: um agente que reage à mutação chama caminhos
que a gravação não tem. Aqui a chamada vai à API real e só a resposta é reescrita, então
qualquer trajetória continua servida.

**Por que bundle e não campo isolado.** Trocar um campo sozinho produz estados que a API
nunca geraria. Em `case_tkt_inv_06`, subir o pico 1x sem mexer no baseline deixa
`state=invalidated` de pé e o insight segue suspeito por outro motivo — o agente mudaria de
resposta pela incoerência, não pelo campo. Cada bundle move junto todos os campos que o
gabarito nomeia para o caso, para um estado internamente consistente.

O desenho completo, com as previsões congeladas antes da coleta, está em
`solution/docs/EXPERIMENTOS.md` (EXP-06 — Sensibilidade à evidência).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# Braços do experimento. `controle` não é um bundle: é a ausência de mutação, e existe como
# nome para que o trace do braço de controle diga explicitamente qual braço rodou em vez de
# deixar o campo nulo e obrigar quem lê a inferir.
CONTROLE = "controle"


@dataclass(frozen=True)
class Mutacao:
    """Uma reescrita de resposta, endereçada por método e caminho.

    `path` casa o caminho exato da requisição (sem query string), que é como
    `ApiClient.request` já o recebe. `aplicar` recebe o `data` do envelope da API e devolve
    a versão reescrita.
    """

    path: str
    aplicar: Callable[[Any], Any]
    descricao: str


@dataclass(frozen=True)
class Bundle:
    """Conjunto coerente de mutações de um caso, aplicado como uma unidade."""

    nome: str
    caso: str
    braco: str  # "decisivo" ou "placebo"
    resumo: str
    mutacoes: tuple[Mutacao, ...] = field(default_factory=tuple)

    def para_trace(self) -> dict[str, Any]:
        """Descrição legível do que foi mutado, gravada no trace da execução."""
        return {
            "bundle": self.nome,
            "caso": self.caso,
            "braco": self.braco,
            "resumo": self.resumo,
            "alvos": [{"path": m.path, "efeito": m.descricao} for m in self.mutacoes],
        }


# ---------------------------------------------------------------------------
# Auxiliares de reescrita
#
# Trabalham sobre o `data` do envelope, que é o que o agente enxerga. São tolerantes a
# ausência: um modo de resposta degradado pode ter removido o campo alvo, e nesse caso a
# execução precisa seguir e o pré-voo do seed (seção 4 do EXP-07) é que responde por isso.
# ---------------------------------------------------------------------------
def _pico(dados: Any, nota_contem: str, amplitude: float) -> Any:
    """Reescreve a amplitude do pico cuja `note` contém o texto dado."""
    if not isinstance(dados, dict):
        return dados
    picos = dados.get("peaks")
    if not isinstance(picos, list):
        return dados
    novos = []
    for p in picos:
        if isinstance(p, dict) and nota_contem.lower() in str(p.get("note", "")).lower():
            p = {**p, "amplitude_mm_s": amplitude}
        novos.append(p)
    return {**dados, "peaks": novos}


def _campos(dados: Any, **valores: Any) -> Any:
    """Sobrescreve campos de primeiro nível do `data`."""
    if not isinstance(dados, dict):
        return dados
    return {**dados, **valores}


def _remove(dados: Any, *campos: str) -> Any:
    if not isinstance(dados, dict):
        return dados
    return {k: v for k, v in dados.items() if k not in campos}


def _evidencia(dados: Any, metrica: str, valor: float) -> Any:
    """Reescreve o `value` da entrada de `evidence` cuja `metric` casa."""
    if not isinstance(dados, dict):
        return dados
    ev = dados.get("evidence")
    if not isinstance(ev, list):
        return dados
    novas = []
    for e in ev:
        if isinstance(e, dict) and str(e.get("metric", "")) == metrica:
            e = {**e, "value": valor}
        novas.append(e)
    return {**dados, "evidence": novas}


def _cobertura(dados: Any, tipo: str, **valores: Any) -> Any:
    """Reescreve a entrada de `coverage` do tipo de máquina dado."""
    if not isinstance(dados, dict):
        return dados
    cob = dados.get("coverage")
    if not isinstance(cob, list):
        return dados
    novas = []
    for c in cob:
        if isinstance(c, dict) and str(c.get("machine_type", "")) == tipo:
            c = {**{k: v for k, v in c.items() if k != "note"}, **valores}
        novas.append(c)
    return {**dados, "coverage": novas}


# ---------------------------------------------------------------------------
# Caso A — case_tkt_inv_06 · asset_S420
#
# Controle: 1x baixo (1,6) sobre baseline invalidado, especialista aponta folga. O insight
# de desbalanceamento é falso positivo, e a evidência CONCORDA com o usuário, que já diz no
# ticket que "isso não é nada". Um agente que repete o enunciado acerta o controle sem ler.
# Mutado: 1x alto sobre baseline estabelecido, subharmônico irrelevante. O desbalanceamento
# passa a se sustentar, e a evidência CONTRARIA o usuário.
# ---------------------------------------------------------------------------
A_DECISIVO = Bundle(
    nome="A-inv06-desbalanceamento-legitimo",
    caso="case_tkt_inv_06",
    braco="decisivo",
    resumo="1x sobe de 1.6 para 6.4, subharmônico cai, baseline passa a established",
    mutacoes=(
        Mutacao(
            "/assets/asset_S420/spectrum",
            lambda d: _pico(_pico(d, "1x", 6.4), "subharm", 0.15),
            "peaks[1x]=6.4; peaks[subharmônico]=0.15",
        ),
        Mutacao(
            "/assets/asset_S420/baseline",
            lambda d: _campos(d, state="established", invalidation_reason=None),
            "state=established; invalidation_reason=None",
        ),
        Mutacao(
            "/analyses/an_9903",
            lambda d: _evidencia(
                _campos(d, baseline_state_at_detection="established", limitations=[]),
                "1x_amplitude",
                6.4,
            ),
            "baseline_state_at_detection=established; limitations=[]; evidence[1x]=6.4",
        ),
        Mutacao(
            "/analyses/an_9904",
            lambda d: _evidencia(_campos(d, confidence=0.21), "subharmonics", 0.15),
            "confidence=0.21; evidence[subharmonics]=0.15",
        ),
    ),
)

A_PLACEBO = Bundle(
    nome="A-inv06-placebo",
    caso="case_tkt_inv_06",
    braco="placebo",
    resumo="collected_at do espectro recua 3 dias; nenhum campo do gabarito muda",
    mutacoes=(
        Mutacao(
            "/assets/asset_S420/spectrum",
            lambda d: _campos(d, collected_at="2026-07-11T00:00:00+00:00"),
            "collected_at=2026-07-11",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Caso B — case_tkt_inv_10 · asset_V301
#
# Controle: snr 8,4 contra um mínimo de 12,0 declarado pelo próprio modelo, completeness
# 0,62 contra 0,8. A confiança de 0,83 do insight é mal calibrada, e a usuária já afirma no
# ticket que a qualidade "tá péssima".
# Mutado: snr e completeness acima dos mínimos. A limitação sai da análise. O critério é
# numérico e a referência (min_snr_db) não muda, então um agente que lê cita o número.
# ---------------------------------------------------------------------------
B_DECISIVO = Bundle(
    nome="B-inv10-sinal-bom",
    caso="case_tkt_inv_10",
    braco="decisivo",
    resumo="snr sobe de 8.4 para 16.5 (mínimo 12.0), completeness de 0.62 para 0.94",
    mutacoes=(
        Mutacao(
            "/assets/asset_V301/data-quality",
            lambda d: _campos(d, snr_db=16.5, completeness=0.94, staleness_flag=False),
            "snr_db=16.5; completeness=0.94; staleness_flag=False",
        ),
        Mutacao(
            "/analyses/an_9909",
            lambda d: _campos(d, limitations=[]),
            "limitations=[]",
        ),
    ),
)

B_PLACEBO = Bundle(
    nome="B-inv10-placebo",
    caso="case_tkt_inv_10",
    braco="placebo",
    resumo="version do modelo muda de 3.2.1 para 3.4.0; requirements ficam intactos",
    mutacoes=(
        Mutacao(
            "/models/mdl_vib_v3",
            lambda d: _campos(d, version="3.4.0"),
            "version=3.4.0",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Caso C — case_tkt_inv_08 · asset_M205
#
# Controle: subharmônicos em 0,9 contra referência 0,2 sustentam folga, e o especialista
# (an_9908) prevalece sobre o desalinhamento do sistema (an_9907).
# Mutado: 2x dominante e subharmônico irrelevante. O sistema passa a prevalecer.
# O ticket é neutro entre as duas opções, então este caso mede leitura de campo sem pressão
# de enunciado, e o desfecho é binário e nomeado.
# ---------------------------------------------------------------------------
C_DECISIVO = Bundle(
    nome="C-inv08-desalinhamento-prevalece",
    caso="case_tkt_inv_08",
    braco="decisivo",
    resumo="2x sobe de 1.3 para 3.9, subharmônico cai de 0.9 para 0.10",
    mutacoes=(
        Mutacao(
            "/assets/asset_M205/spectrum",
            lambda d: _pico(_pico(d, "2x", 3.9), "subharm", 0.10),
            "peaks[2x]=3.9; peaks[subharmônico]=0.10",
        ),
        Mutacao(
            "/analyses/an_9907",
            lambda d: _evidencia(_campos(d, confidence=0.90), "2x_amplitude", 3.9),
            "confidence=0.90; evidence[2x]=3.9",
        ),
        Mutacao(
            "/analyses/an_9908",
            lambda d: _evidencia(_campos(d, confidence=0.22), "subharmonics", 0.10),
            "confidence=0.22; evidence[subharmonics]=0.10",
        ),
    ),
)

C_PLACEBO = Bundle(
    nome="C-inv08-placebo",
    caso="case_tkt_inv_08",
    braco="placebo",
    resumo="collected_at do espectro recua 3 dias; nenhum campo do gabarito muda",
    mutacoes=(
        Mutacao(
            "/assets/asset_M205/spectrum",
            lambda d: _campos(d, collected_at="2026-07-11T00:00:00+00:00"),
            "collected_at=2026-07-11",
        ),
    ),
)

# ---------------------------------------------------------------------------
# Caso D — case_tkt_inv_11 · asset_M102
#
# Controle: o modelo cobre motor DC mas não aprende baseline; a detecção é sintomática.
# Mutado: passa a aprender. `supported` continua true nos dois braços, então a resposta à
# pergunta do ticket ("atende?") não muda — muda só COMO atende.
# É a mutação mais barata de verificar do conjunto: um booleano, num campo, num endpoint
# que o gabarito nomeia.
# ---------------------------------------------------------------------------
D_DECISIVO = Bundle(
    nome="D-inv11-aprende-baseline",
    caso="case_tkt_inv_11",
    braco="decisivo",
    resumo="motor_dc passa a aprender baseline; a nota de detecção sintomática sai",
    mutacoes=(
        Mutacao(
            "/models/mdl_vib_v3",
            lambda d: _cobertura(d, "motor_dc", can_learn_baseline=True),
            "coverage[motor_dc].can_learn_baseline=True; note removida",
        ),
        Mutacao(
            "/assets/asset_M102/baseline",
            lambda d: _campos(d, learnable=True, state="established"),
            "learnable=True; state=established",
        ),
    ),
)

D_PLACEBO = Bundle(
    nome="D-inv11-placebo",
    caso="case_tkt_inv_11",
    braco="placebo",
    resumo="version do modelo muda de 3.2.1 para 3.4.0; coverage fica intacto",
    mutacoes=(
        Mutacao(
            "/models/mdl_vib_v3",
            lambda d: _campos(d, version="3.4.0"),
            "version=3.4.0",
        ),
    ),
)


BUNDLES: dict[str, Bundle] = {
    b.nome: b
    for b in (
        A_DECISIVO,
        A_PLACEBO,
        B_DECISIVO,
        B_PLACEBO,
        C_DECISIVO,
        C_PLACEBO,
        D_DECISIVO,
        D_PLACEBO,
    )
}

# Casos do experimento, na ordem de prioridade da seção 8 do EXP-07: se a cota só permitir
# metade, A e D são os que rodam. A dá o teste de eco de enunciado mais forte; D dá a
# verificação menos ambígua.
CASOS_EXP07: tuple[tuple[str, Bundle, Bundle], ...] = (
    ("case_tkt_inv_06", A_DECISIVO, A_PLACEBO),
    ("case_tkt_inv_11", D_DECISIVO, D_PLACEBO),
    ("case_tkt_inv_10", B_DECISIVO, B_PLACEBO),
    ("case_tkt_inv_08", C_DECISIVO, C_PLACEBO),
)

# Seed escolhido no pré-voo (EXP-07 §4): entrega mode=complete em todos os endpoints alvo
# dos quatro casos. Sem isso, `model` em modo `partial` derrubaria `requirements` — e com
# ele o `min_snr_db=12.0` de que o caso B depende inteiro.
SEED_EXP07 = "seed-50"


def hook_de(bundle: Bundle | None) -> Callable[[str, str, Any], Any] | None:
    """Constrói o `response_hook` do ApiClient para um bundle. `None` no braço de controle."""
    if bundle is None:
        return None

    def hook(method: str, path: str, data: Any) -> Any:
        if method != "GET":
            return data
        for m in bundle.mutacoes:
            if m.path == path:
                data = m.aplicar(data)
        return data

    return hook
