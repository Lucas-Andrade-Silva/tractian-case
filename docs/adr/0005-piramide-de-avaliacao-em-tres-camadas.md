# Avaliação em pirâmide de três camadas

A Parte 2 precisa medir dimensões muito diferentes entre si: algumas são comparáveis por código puro
contra o golden set (decisão final bate? sequência de tools é razoável? erro HTTP foi tratado
certo?), outras são inerentemente qualitativas (a explicação foi honesta sobre a incerteza? a causa-
raiz citada está correta?). Um único método para tudo — só determinístico, ou só um juiz LLM
avaliando holisticamente — deixaria uma das duas categorias mal medida.

Decidimos por uma pirâmide de três camadas, executadas nessa ordem:

1. **Determinístico** (Pydantic + comparação de conjuntos): decisão final, sequência de tools vs.
   `expected_path`, tratamento de erro HTTP, número de chamadas, taxa de repetição/loop.
2. **Comitê de juízes LLM**, um por dimensão textual (honestidade sob incerteza, acurácia da
   causa-raiz, qualidade da justificativa) — não um juiz genérico multitarefa. Estilo G-Eval: rubrica
   explícita 1–5, chain-of-thought antes da nota, saída estruturada, `temperature=0.0`.
3. **Estabilidade entre seeds**: cada cenário roda em ≥3 seeds; um cenário é considerado instável
   apenas se a *decisão final* divergir entre execuções — variação de trajetória é esperada e não
   conta.

A ordem importa: a camada determinística roda primeiro porque é gratuita e instantânea, funcionando
como filtro antes de gastar chamadas de LLM nas camadas seguintes. Um único juiz multitarefa foi
descartado porque confundiria dimensões distintas numa única nota, dificultando calibração e
diagnóstico separado de cada uma.
