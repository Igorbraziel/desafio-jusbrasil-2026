# 01 — Parser de zonas dos acórdãos

**Data:** 15–16/09/2026 · **Estado:** ativado e em produção

## O que foi feito

Novo `src/verificador/estrutura.py`: segmenta um acórdão em zonas contíguas
(`cabecalho`, `identificacao`, `ementa`, `relatorio`, `voto`, `dispositivo`,
`corpo`), com uma estratégia de marcadores por tribunal.

`base_canonica.regiao_de_identificacao` ganhou o parâmetro `metodo`, com as duas
implementações lado a lado: `baseline` (janela de offset fixo, a que está em
produção) e `estrutural` (as zonas identificadoras). `scripts/medir_regiao.py`
mede as duas e imprime o comparativo.

## Por que uma estratégia por tribunal

Os marcadores de zona não são compartilhados. Medido nos 996 acórdãos:

| marca | STF | STJ | STM | TSE | TST |
|---|---|---|---|---|---|
| EMENTA | 86% | 99% | 100% | **8%** | 36% |
| RELATÓRIO | 86% | 98% | 100% | 97% | **3%** |
| VOTO | 92% | 98% | 100% | 99% | **2%** |
| `estes autos` | 97% | 55% | 100% | 26% | **100%** |

TSE quase não usa EMENTA; TST quase não usa RELATÓRIO nem VOTO. Um segmentador
único erraria nos dois, e a ordem de busca importa: procurar EMENTA primeiro no
TSE consumiria o RELATÓRIO em 92% dos casos, porque a varredura é sequencial.

## Inferência de tribunal: 71,3% → 98,6%

A primeira versão usava acrônimos (`\bSTF\b`, `\bTST\b`) e acertava **71,3%**,
com STF e TST se confundindo mutuamente 115 vezes — cada um **cita** o outro, e
a sigla solta não distingue identidade de citação.

A versão atual usa assinatura **estrutural** do cabeçalho:

| tribunal | assinatura | acerto |
|---|---|---|
| STJ | `RELATOR : MINISTRO` (por extenso) ou `(AAAA/NNNNNNN-N)` | 199/199 |
| STF | `RELATOR : MIN.` (abreviado) | 189/200 |
| TST | `A C Ó R D Ã O` espaçado, `SbDI` | 198/198 |
| STM | `Poder Judiciário STM` | 200/200 |
| TSE | `TRIBUNAL SUPERIOR ELEITORAL` | 196/199 |

**98,6% (982/996).** Sobram 10 STF lidos como TST e 3 TSE sem assinatura. No
caminho normal isso não é usado — o tribunal vem da coluna do banco; a
inferência serve a documento solto.

## O teto do cabeçalho, e por que ele existe

Sem teto, um documento onde nenhum marcador casa cedo tem "cabeçalho" até o
primeiro marcador que aparecer. Medido no STF: **p90 de 34.000 caracteres e
78.510 no pior caso** — o que enche o índice de números citados.

Com teto, a região de identificação fica em no máximo 1.900 caracteres
(`LIMITE_CABECALHO` + a janela de 400 da zona `identificacao`) em todos os
tribunais.

## A varredura do parâmetro

Comando: `uv run python scripts/medir_regiao.py --metodo ambos`

| `LIMITE_CABECALHO` | recall | FP | órfãos | ambíguos | números |
|---|---|---|---|---|---|
| 150 | 77/77 | 0 | 27 | 180 | 1.632 |
| 200 | 77/77 | 0 | 26 | 188 | 1.698 |
| **250** | 77/77 | 0 | **25** | **217** | 1.828 |
| **300** | 77/77 | 0 | **25** | **239** | 2.001 |
| 600 | 77/77 | 0 | 26 | 322 | 2.495 |
| 1500 | 77/77 | 0 | 24 | 397 | 2.900 |
| *baseline* | 77/77 | 0 | *26* | *282* | *2.231* |

**Recall e falso positivo não se movem em nenhum valor** — os dois portões da
fase passam em toda a faixa. O que varia é a troca entre órfãos (registro que
citação nenhuma alcança) e ambiguidade (citação que cai em ≥2 candidatos).

Entre 250 e 300 os órfãos empatam. A escolha é **300**, pela folga: a primeira
ocorrência do número próprio foi medida entre os caracteres 19 e 123, então 300
dá 2,4× de margem. Truncar cabeçalho num formato não visto custa mais caro que
ambiguidade — a ambiguidade afeta **uma** citação do gabarito, e o desempate por
`texto_len` já cobre esse caso (ADR 0003).

## O ganho, em uma frase

Contra a baseline, o estrutural a 300 entrega **1 órfão a menos e 43 números
ambíguos a menos**, com o mesmo recall e o mesmo zero de falso positivo.

É ganho de robustez, não de score: o score local já está saturado em F1 macro
1,0000 nos dois níveis, e nenhuma dessas mudanças o move.

## Ativação, e os portões que ela passou

`LIMITE_CABECALHO = 300` aplicado e `METODO_PADRAO = "estrutural"`. Índice
reconstruído: **2.001 números** contra 2.231 da baseline.

| portão | resultado |
|---|---|
| `uv run pytest -q` | 61 passed |
| recall no gabarito | 77/77 |
| falso positivo em `inventada` | 0 |
| `make rodar && make avaliar` | **1,0988** — preservado |

A baseline continua no código, selecionável por `--metodo`: sem ela o
comparativo deixa de existir, e a próxima troca de método viraria opinião.

## O que ficou aberto

1. As fases 3 (dataset estrutural) e 5 (endurecimento) não começaram.
2. Nenhuma estimativa de comportamento fora desta amostra — é o que a fase 4
   ataca.
