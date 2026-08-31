# 0003 — Desempate de duplicatas pelo maior `texto_len`

**Data:** 31/08/2026 · **Situação:** vigente, com ressalva

## Contexto

A organização removeu `doc_0227` e `doc_0461` da base por serem duplicatas
exatas, e informou que **existem outras duplicatas no acervo**, mas que nenhuma
citação do gabarito aponta para elas.

Na prática, aponta. Encontramos três números que são o número próprio de **dois**
registros distintos, com `id` canônicos diferentes, e o gabarito escolhe um
deles:

| número | candidatos | gabarito escolhe | `texto_len` |
|---|---|---|---|
| `213-85.2010.5.02.0030` | doc_0662, doc_0670 | doc_0670 | 95.386 vs **95.622** |
| `79500-16.2009.5.15.0016` | doc_0640, doc_0657 | doc_0640 | **99.783** vs 99.546 |
| `25823-78.2015.5.24.0091` | doc_0710, doc_0729 | doc_0710 | **95.681** vs 60.988 |

Nos três casos, o registro escolhido é o de **maior `texto_len`** — a versão mais
completa do par.

## Decisão

Quando mais de um registro reivindica o mesmo número próprio, ordenar por
`texto_len` decrescente (desempate final por `documento_id`, para determinismo) e
devolver o primeiro, classificando como `real`.

Note que a alternativa — tratar cardinalidade ≥ 2 como `incompleta`, seguindo a
regra geral — **erra os três casos**, porque o gabarito os anota como `real`.

## Consequências e ressalva

- Acerta 3 de 3 nos casos observados.
- **São três exemplos.** Esta é a regra com menos evidência por trás em todo o
  pipeline. Não temos explicação de *por que* a organização escolheu a versão
  mais longa — apenas que escolheu, nas três vezes que pudemos observar.
- Se no conjunto cego a escolha for outra, cada caso vira um erro de `real`.
  São poucos casos, então o custo é limitado.
- A confiança reportada nesse caminho é 0,60, contra 0,95 do caminho sem
  ambiguidade. Se estivermos errados, o Brier absorve parte do dano.
