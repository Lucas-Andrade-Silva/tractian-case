"""Binding do provedor de LLM — o único ponto do código que sabe qual provedor é usado.

Isolado de propósito: o grafo, as tools e o trace não dependem de provedor. Trocar de
provedor (ou comparar dois no experimento) é mudar `LLM_PROVIDER`/`LLM_MODEL` no
`.env`, sem tocar em mais nada.

O pacote do provedor é uma dependência opcional — instale só o que for usar:
    uv pip install -e ".[groq]"
"""
from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel

from .config import ROLES, Settings

_SUPPORTED = ("groq", "openai", "openrouter")

# OpenRouter fala o protocolo da OpenAI, então reaproveita o mesmo cliente — o que muda é
# só o endereço. Fica aqui, e não no .env, porque é característica do provedor e não
# configuração de quem usa.
_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def build_llm(settings: Settings, *, api_key: str | None = None, **overrides: Any) -> BaseChatModel:
    """Instancia o chat model configurado.

    `temperature=0` por padrão: a Parte 2 mede estabilidade entre execuções, e
    variação amostral do próprio decoder confundiria essa medida com instabilidade do
    agente.

    `api_key` sobrepõe a chave do `.env` — é o que permite ao rodízio de cota instanciar
    o mesmo modelo em outra conta sem tocar no resto da configuração.
    """
    provider = (settings.llm_provider or "").strip().lower()
    # `model` pode vir por override (modelo de um papel específico); só então caímos no
    # LLM_MODEL geral, que numa configuração por papel pode nem estar definido.
    model = str(overrides.pop("model", "") or settings.llm_model or "").strip()

    if not provider:
        raise LlmNotConfigured(
            "LLM_PROVIDER não definido. Copie .env.example para .env e "
            f"escolha um provedor ({', '.join(_SUPPORTED)}) + LLM_MODEL."
        )
    if not model:
        raise LlmNotConfigured(
            f"Nenhum modelo definido para o provedor '{provider}'. Defina LLM_MODEL ou "
            "um MODEL_<PAPEL> para cada papel."
        )

    params: dict[str, Any] = {
        "model": model,
        "temperature": settings.llm_temperature,
        **overrides,
    }

    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:  # pragma: no cover - depende de instalação opcional
            raise LlmNotConfigured(
                "Provedor 'groq' escolhido mas langchain-groq não está instalado. "
                'Rode: uv pip install -e ".[groq]"'
            ) from exc
        escolhida = api_key or settings.llm_api_key
        if escolhida:
            params["api_key"] = escolhida
        return ChatGroq(**params)

    if provider in ("openai", "openrouter"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - depende de instalação opcional
            raise LlmNotConfigured(
                f"Provedor '{provider}' escolhido mas langchain-openai não está instalado. "
                'Rode: uv pip install -e ".[openai]"'
            ) from exc
        escolhida = api_key or settings.llm_api_key
        if escolhida:
            params["api_key"] = escolhida
        if provider == "openrouter":
            params.setdefault("base_url", _OPENROUTER_BASE_URL)
        return ChatOpenAI(**params)

    raise LlmNotConfigured(
        f"Provedor '{provider}' não suportado. Use um de: {', '.join(_SUPPORTED)}."
    )


class LlmNotConfigured(RuntimeError):
    """Configuração de LLM ausente ou incompleta."""


def _e_cota_diaria(erro: Exception) -> bool:
    """Distingue cota do DIA esgotada de limite por minuto.

    Só a primeira justifica trocar de chave: o limite por minuto reabre sozinho em
    segundos, e migrar de conta por causa dele gastaria a cota diária da chave seguinte
    sem necessidade. A mensagem da Groq nomeia qual dos dois foi.
    """
    texto = str(erro).lower()
    if "429" not in texto and "rate limit" not in texto and "ratelimit" not in texto:
        return False
    return "per day" in texto or "tpd" in texto or "rpd" in texto


class _ChatComRodizio(BaseChatModel):
    """Chat model que troca de chave de API quando a cota diária de uma conta acaba.

    A cota da Groq no plano gratuito é por dia e por conta — 200k tokens no menor modelo,
    cerca de dez execuções da bateria. Com uma chave só, uma bateria de 51 execuções para
    no meio e o resto do dia é perdido. Aqui as chaves extras entram em sequência: a
    execução continua na conta seguinte, e o trace nem registra a troca, porque do ponto
    de vista do agente nada mudou.

    Delegação explícita em vez de herança dinâmica: `BaseChatModel` é um modelo Pydantic,
    e sobrescrever `__getattr__` num campo dele produz recursão na validação.
    """

    settings_: Any
    modelo: str
    extras: dict
    chaves: tuple
    indice: int = 0
    atual_: Any = None
    # Tools e structured output ligados depois da construção. Guardados para poder
    # reaplicá-los ao cliente da chave seguinte: sem isso, a troca de conta devolveria
    # um modelo sem as tools, e o papel perderia a capacidade de consultar a API.
    ligacoes_: tuple = ()

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **dados: Any) -> None:
        super().__init__(**dados)
        self.atual_ = self._constroi()

    def _constroi(self):
        """Cliente da chave corrente, com as ligações já aplicadas."""
        cliente = build_llm(
            self.settings_,
            model=self.modelo,
            api_key=self.chaves[self.indice],
            **self.extras,
        )
        for metodo, args, kwargs in self.ligacoes_:
            cliente = getattr(cliente, metodo)(*args, **kwargs)
        return cliente

    @property
    def _llm_type(self) -> str:
        return f"rodizio:{getattr(self.atual_, '_llm_type', 'chat')}"

    def _proxima_chave(self) -> bool:
        """Troca para a chave seguinte. False quando não há mais nenhuma."""
        if self.indice + 1 >= len(self.chaves):
            return False
        self.indice += 1
        self.atual_ = self._constroi()
        return True

    def _tentando_cada_chave(self, chamada):
        """Roda `chamada(cliente)`, avançando de chave a cada cota diária esgotada."""
        while True:
            try:
                return chamada(self.atual_)
            except Exception as erro:  # noqa: BLE001 - reerguido quando não é cota
                if not _e_cota_diaria(erro) or not self._proxima_chave():
                    raise
                print(
                    f"    [cota diária esgotada — usando chave {self.indice + 1}"
                    f"/{len(self.chaves)}]",
                    flush=True,
                )

    # -- interface do BaseChatModel ---------------------------------------
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._tentando_cada_chave(
            lambda c: c._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        )

    def invoke(self, input, config=None, **kwargs):
        return self._tentando_cada_chave(lambda c: c.invoke(input, config, **kwargs))

    def _com_ligacao(self, metodo: str, args: tuple, kwargs: dict) -> "_ChatComRodizio":
        """Novo rodízio com mais uma ligação registrada, preservando a chave em uso."""
        return _ChatComRodizio(
            settings_=self.settings_,
            modelo=self.modelo,
            extras=self.extras,
            chaves=self.chaves,
            indice=self.indice,
            ligacoes_=(*self.ligacoes_, (metodo, args, kwargs)),
        )

    def bind_tools(self, tools, **kwargs):
        """O grafo liga tools ao modelo; o rodízio precisa sobreviver a isso."""
        return self._com_ligacao("bind_tools", (tools,), kwargs)

    def with_structured_output(self, schema, **kwargs):
        """O Decisor pede saída estruturada; idem."""
        return self._com_ligacao("with_structured_output", (schema,), kwargs)


class RoleModels:
    """Resolve o modelo de cada papel, reaproveitando clientes já instanciados.

    Papéis diferentes têm exigências diferentes: quem chama tools em série se beneficia
    de um modelo que emita várias tool calls por resposta (corta voltas e, com elas, o
    custo fixo de prompt+schemas reenviado a cada volta); quem produz a decisão e a
    justificativa — o que a avaliação de fato julga — se beneficia do modelo mais capaz.

    Como os limites de cota da Groq são por modelo, distribuir papéis entre modelos
    também distribui o consumo entre pools separados.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[tuple[str, int | None, str | None], BaseChatModel] = {}

    def for_role(self, role: str) -> BaseChatModel:
        model = self._settings.model_for(role)
        teto = self._settings.max_tokens_for(role)
        esforco = self._settings.reasoning_effort_for(role)
        # A chave inclui o teto e o esforço de raciocínio: dois papéis podem compartilhar
        # o modelo e pedir limites diferentes, e indexar só pelo modelo entregaria ao
        # segundo o cliente configurado para o primeiro.
        chave = (model, teto, esforco)
        if chave not in self._cache:
            extras: dict[str, Any] = {"max_tokens": teto} if teto else {}
            if esforco:
                extras["reasoning_effort"] = esforco
            chaves = self._settings.chaves_llm
            # Com uma chave só, o cliente direto: nada a alternar, e envolvê-lo num
            # wrapper só acrescentaria uma camada entre o grafo e o provedor.
            self._cache[chave] = (
                _ChatComRodizio(
                    settings_=self._settings, modelo=model, extras=extras, chaves=chaves
                )
                if len(chaves) > 1
                else build_llm(self._settings, model=model, **extras)
            )
        return self._cache[chave]

    def for_transcription(self, role: str) -> BaseChatModel:
        """Cliente do papel com o raciocinio DESLIGADO, para tarefas de transcricao.

        Usado na segunda tentativa depois de um corte por `max_tokens`: ali a evidencia ja
        esta na mensagem e o trabalho e so redigi-la. Com o raciocinio ligado, o retry
        gasta o mesmo orcamento pensando e e cortado igual — foi o que aconteceu no
        TKT-EXE-13, onde o rascunho vazou para dentro do `finding`.

        `none` e o unico valor que os dois modelos qwen aceitam em comum (o 3.6 recusa
        `low` com HTTP 400). Provedor que nao conhece o parametro cai no `except` e
        recebe o cliente normal — comportamento de antes, sem quebrar a execucao.
        """
        model = self._settings.model_for(role)
        chave = (model, self._settings.max_tokens_for(role), "__transcricao__")
        if chave not in self._cache:
            extras: dict[str, Any] = {"reasoning_effort": "none"}
            if teto := self._settings.max_tokens_for(role):
                extras["max_tokens"] = teto
            chaves = self._settings.chaves_llm
            try:
                self._cache[chave] = (
                    _ChatComRodizio(
                        settings_=self._settings, modelo=model, extras=extras, chaves=chaves
                    )
                    if len(chaves) > 1
                    else build_llm(self._settings, model=model, **extras)
                )
            except TypeError:
                self._cache[chave] = self.for_role(role)
        return self._cache[chave]

    def describe(self) -> dict[str, str]:
        """Mapa papel → modelo efetivo, para registrar no trace do experimento."""
        return {role: self._settings.model_for(role) for role in ROLES}
