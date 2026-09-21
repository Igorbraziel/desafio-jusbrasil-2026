# 05 — Endurecimento para o conjunto cego

**Data:** 21/09/2026 · **Estado:** cinco correções em produção

## Por que esta etapa existe

A primeira submissão marcou **1,09879** no leaderboard. Decompondo o número
local, que o reproduz:

| nível | macro F1 | τ | bônus Brier | score |
|---|---|---|---|---|
| 1 | 1,0000 | 0,0000 | 0,098964 | 1,098964 |
| 2 | 1,0000 | 0,0000 | 0,098705 | 1,098705 |

**F1 saturado em 1,0 nos dois níveis.** Todo o gap para 1,1 era calibração. Não
havia o que ganhar no conjunto de desenvolvimento, e perseguir o resto seria
otimizar ruído.

O leaderboard desta fase roda sobre os mesmos 26 documentos usados para
construir a solução, e suas submissões não contam para o ranking. A pergunta
útil deixou de ser "como tirar mais 0,001" e passou a ser **onde a solução
quebra em texto que nunca viu**. Sondando o pipeline com formas plausíveis fora
da amostra, apareceram quatro defeitos — medidos, não hipotéticos.

## O que estava quebrado

### 1. `inventada` → `real` por casamento de diploma por substring

O pior, porque é o erro grave da métrica: `s = macroF1 × (1 − 0,5·τ)`.

| citação (fora da cobertura) | resolvia para | correto |
|---|---|---|
| `art. 1º da Lei Complementar nº 123/2006` | `real` 11304039 | `inventada` |
| `art. 1º da Lei Complementar nº 101/2000` | `real` 11304039 | `inventada` |
| `art. 5º da Constituição Estadual` | `real` 10641516 | `inventada` |
| `art. 93 da Constituição do Estado` | `real` 10626510 | `inventada` |
| `art. 312 do Código de Processo Penal Militar` | `real` 10652044 (CPP!) | `inventada` |

`"lei complementar"` casava qualquer LC; `"constituic"`, qualquer constituição;
e `"processo penal"` era testado antes de `"penal militar"`. Custo modelado no
nível 2: 3 erros derrubam o nível a 1,0185 (−0,080); 8 erros, a 0,8889 (−0,210).
Os mesmos 8 como FP comum custariam ~−0,03 — a penalidade multiplicativa é ~7×.

### 2. Distratores numéricos ausentes da amostra

| entrada | detectava como |
|---|---|
| `O período de 01/01/2020 a 31/12/2021` | 2 spans `processo` |
| `Publicado no DJe de 12/03/2021` | 1 span `processo` |
| `Telefone (11) 98765-4321` · `CEP 01310-100` · `RG 12.345.678-9` | 1 span cada |

`_TERMINA_EM_ANO` exige que o número **inteiro** seja `<n>/<ano>`; a data tem uma
barra a mais e escapava.

O número que justifica a correção: `dd/mm/aaaa` aparece **0 vezes** nos 26
documentos da amostra e em **200 de 200** acórdãos reais da base, num total de
5.635 ocorrências. A ausência é artefato do gerador sintético, não propriedade
do domínio.

### 3. Três bugs de fronteira de span

Mesmo com F1 = 1,0, o IoU mínimo era **0,519** — a quatro caracteres de virar
FN + FP.

- `_DENTRO` incluía `\s`, então o núcleo atravessava o fim do parágrafo e engolia
  o título da seção seguinte.
- `_ELO` rejeitava sigla com ponto interno (`H.C.`, `AG.REG`, `A.REsp`), truncando
  o prefixo — era a causa dos dois piores IoU.
- `_ELO` aceitava qualquer palavra capitalizada, então `Também`, `Ademais` e
  `Vide` estendiam o span para dentro da prosa.

### 4. `incompleta` reconhecida em uma ordem só

`_VAGA` exigia cabeça → tribunal → ano → relator nessa ordem. Das oito
reordenações plausíveis testadas, **duas** eram detectadas.

## O ganho

### Fronteira de span, contra o gabarito

| | antes | depois |
|---|---|---|
| IoU mínimo | 0,519 | **0,8125** |
| predições abaixo de 0,7 | 8 | **0** |
| casamentos exatos (IoU 1,0) | 138/192 | **144/192** |

### Ordem dos constituintes de `incompleta`

Detectadas: **2/8 → 8/8**.

### Arnês, taxa 0,15 com 3 sementes

| classe de ruído | antes | depois | Δ |
|---|---|---|---|
| **as sete juntas** | 0,9538 | **0,9751** | **+0,021** |
| ordem do padrão `incompleta` | 1,0737 | **1,0992** | **+0,026 (vira imune)** |
| OCR na prosa | 1,0274 | 1,0311 | +0,004 |
| OCR no número | 1,0269 | 1,0285 | +0,002 |
| marca de número | 1,0943 | 1,0947 | +0,000 |
| quebra no identificador | 1,0988 | **1,0992** | imune |
| separador de UF | 1,0988 | **1,0992** | imune |
| sigla processual não vista | 1,0988 | **1,0992** | imune |

**`ordem_incompleta` passou a ser a terceira propriedade imune.** Nenhuma classe
piorou, e o score limpo subiu de 1,0988 para **1,0992**.

## A calibração, que era o único ganho disponível no dev

Os oito valores de `CONFIANCA` eram palpite declarado. O bônus é
`b = 0,10·(1 − Brier)` e o Brier é minimizado **exatamente em `p = acurácia`**,
então palpite custa nos dois sentidos — e os dois existiam.

`scripts/medir_confianca.py` mede a acurácia por caminho sobre o corpus limpo
mais três sementes a taxa 0,15, com predição sem par contando como erro:

| caminho | acertos | acurácia | era | virou |
|---|---|---|---|---|
| `real_unico` | 273/274 | 0,996 | 0,93 | **0,99** |
| `inventada_processo` | 158/190 | 0,832 | 0,85 | **0,83** |
| `incompleta_vaga` | 114/114 | 1,000 | 0,90 | **0,99** |
| `inventada_tabela` | 60/62 | 0,968 | 0,88 | **0,95** |
| `real_tabela` | 61/61 | 1,000 | 0,95 | **0,98** |
| `real_desempate` | 4/4 | 1,000 | 0,55 | **0,83** |
| `inventada_tema` | 2/3 | 0,667 | 0,80 | **0,60** |

Os valores emitidos passam por **Laplace** — `(acertos+1)/(total+2)` —, não pela
taxa bruta. É o que impede `real_desempate`, com quatro observações e o critério
declarado refutado pela ADR 0003, de reivindicar 1,0: encolhe para 0,83.

Medir **sob perturbação** e não no conjunto limpo é o ponto do método. No limpo
todo caminho acerta 100% e a calibração mandaria emitir 1,0 em tudo.

`incompleta_sem_numero` não é exercido nem pelo dev nem pelo arnês. Fica no valor
conservador de 0,70 — é o único palpite que restou, e está declarado como tal.

## Uma decisão de escopo: casamento aproximado, não

Medi a distância de edição de cada `inventada` do gabarito ao número real mais
próximo do índice:

| distância | citações `inventada` |
|---|---|
| 1 | 12 |
| 2 | 41 |
| 3 ou mais | 11 |

**83% das citações inventadas estão a distância ≤ 2 de uma verdadeira** — o que é
esperado, porque uma alucinação plausível *é* um quase-acerto. Habilitar busca
aproximada converteria essas em `real`, direto no caminho do τ:

| lookup | τ | score N2 |
|---|---|---|
| exato (hoje) | 0,000 | 1,0992 |
| aproximado d ≤ 1 | 0,188 | 0,9402 |
| aproximado d ≤ 2 | 0,844 | 0,4310 |

Fica registrado porque é a sugestão que naturalmente ocorre a quem olha o
problema. A organização garante que dígito nunca vira dígito, então todo ruído é
recuperável por normalização e **não há incerteza residual** para a aproximação
resolver. O casamento aproximado que fazemos já está no lugar certo: reparo de
OCR (letra → dígito) **antes** de um lookup exato.

## O que ficou aberto

1. `ocr_numero` continua sendo o ponto fraco (1,0285 contra 1,0992 limpo). Os
   erros restantes são `inventada→(não detectada)` e `real→(não detectada)`: o
   ruído destrói o número a ponto de a normalização não o recuperar.
2. `incompleta_sem_numero` segue sem medição.
3. O arnês ainda não gera corrupção da sigla do tribunal nem do rótulo de
   cabeçalho — as duas classes que o checkpoint 04 já listava.
4. O desempate de duplicatas continua arbitrário (ADR 0003). Com um par ambíguo
   na base, não há evidência para inferir critério.
