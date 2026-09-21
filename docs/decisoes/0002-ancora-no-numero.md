# 0002 — Ancorar a detecção de processo no número, não na sigla

**Data:** 15/09/2026 · **Situação:** vigente

## Contexto

As citações de processo começam por uma classe processual. Medindo o gabarito,
essas classes aparecem em **mais de 90 grafias distintas** — de `RR-` a
`Embargos de Declaração no Agravo Interno no Agravo em Recurso Especial nº`,
passando por abreviações com ruído de OCR (`R.Esp.`, `Ag. Int. No`, `AGINT`).

Enumerá-las numa alternância de regex casa a amostra de desenvolvimento e falha
no conjunto cego, onde o material avisa explicitamente que "as siglas
processuais observadas não esgotam o domínio".

## Decisão

A expressão ancora no **núcleo numérico** e expande para a esquerda token a
token, aceitando elos de prefixo (sigla iniciada em maiúscula, marca de número,
um punhado de conectores minúsculos) até 12 elos.

A expansão é feita em Python, não em regex: uma cadeia `(?:elo\s*){0,12}` antes
do número faz o motor testar todas as combinações quando o número falha, e a
suíte passou de milissegundos para **41 segundos por documento**.

## Consequências

Degrada bem. Numa classe processual não vista o span fica curto, mas o número —
que é o que resolve — continua capturado, e o span costuma sobreviver ao
IoU ≥ 0,5. Medido no dev set: recall e precisão de span em 100%.

O preço é que números que não são processo precisam ser filtrados por regra
explícita: ano solto (`de <ano>`), página (`fls. <n>/<n>`), inscrição na OAB
(`OAB/<UF> <n>`) e referência a lei (`<lei>/<ano>`). Cada um desses foi um
falso positivo medido antes do filtro correspondente.

## Quando revisitar

Se aparecer uma citação sem número algum que ainda assim resolva — hoje não
existe na cobertura.
