# 0004 — Casamento de palavras por esqueleto

**Data:** 31/08/2026 · **Situação:** vigente

## Contexto

O nível 2 corrompe letras isoladas dentro das palavras: `entendirnento`,
`jurisprudêneia`, `profcrido`, `recentc`, `Fedcral`, `Magãlhães`, `assirn`. As
citações vagas — 65 das 225 do gabarito — são frases fixas, e comparar strings
exatas perde todas as versões corrompidas.

Enumerar as corrupções não funciona: o gerador aplica ruído aleatório, e o
conjunto cego terá outras.

## Decisão

Casar cada palavra pelo seu **esqueleto**: as duas primeiras letras, mais o
comprimento com folga de um caractere para cada lado. `recente` vira
`re\w{4,6}`, que absorve `recentc`, `recentê` e `recnte`.

Ancorar também a última letra seria mais restritivo e mais seguro contra falso
positivo — mas perde `recentc`, onde é justamente a última letra que foi
corrompida. Escolhemos o recall.

## Consequências

- As 65 citações vagas do gabarito são detectadas, incluindo todas as versões
  ruidosas.
- Zero falsos positivos no dev set — mas isso é medido em 26 documentos. O padrão
  `re\w{4,6}` também casa `recurso`, e só o resto da frase impede a confusão.
- Para números o critério é outro e mais estrito: uma letra só vira dígito se
  estiver cercada por dígitos de verdade, ou colada a um deles na ponta. Sem
  isso, o `I` final de `AREspEI` e o `S` de um sufixo `/SP` entram no
  identificador e o corrompem — dois bugs que efetivamente cometemos antes de
  chegar nessa regra.
