# 0001 — Manter o pipeline determinístico, sem pesos de modelo

**Data:** 15/09/2026 · **Situação:** vigente

## Contexto

O regulamento permite modelos de pesos abertos e o envelope oferece uma GPU de
24 GB. A tentação é usar NER ou um LLM local para detectar e classificar.

Três medidas pesam contra, todas disponíveis antes de escrever código:

1. No projeto `parsing-tests` (EstatCamp), num problema análogo de extração de
   estrutura em documento jurídico-regulatório, a via por LLM entregou 22,5% dos
   artigos com **60% de texto inventado em 36 minutos**, contra 0% de alucinação
   em 0,2 s no determinístico.
2. A resolução aqui é **lookup exato por chave numérica**, não busca semântica.
   A organização garante que um dígito nunca é trocado por outro dígito, então
   todo ruído é recuperável por normalização — não há incerteza residual para um
   modelo resolver.
3. A métrica precisa de cardinalidade exata (`0 → inventada`, `1 → real`,
   `≥2 → incompleta`). Um recuperador denso sempre devolve top-k com score e
   estruturalmente não sabe dizer "zero", que é 33% do gabarito.

## Decisão

Pipeline 100% determinístico, só biblioteca padrão em runtime.
`MANIFESTO_MODELO.md` declara ausência de pesos.

## Consequências

Reprodutibilidade trivial (sem seed, sem amostragem, sem download de pesos), e
0,5 ms/documento — cinco ordens de grandeza abaixo do teto de 60 s. Em troca,
qualquer forma de citação que as expressões não descrevam é perdida em silêncio,
e o conjunto cego pode trazer formas que a amostra não tem.

## Quando revisitar

Se o score do leaderboard sobre o conjunto final ficar muito abaixo do medido
localmente, o diagnóstico separa as duas causas: queda de **recall de span**
aponta para detecção, e aí um NER de pesos abertos na detecção (nunca na
resolução) é a resposta — com as obrigações de declaração que isso aciona.
