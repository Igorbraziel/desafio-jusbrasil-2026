# 02 — Arnês de perturbação

**Data:** 16/09/2026 · **Estado:** em produção, com uma correção adotada e uma rejeitada

## O que foi feito

`scripts/perturbar.py` gera variantes ruidosas dos 26 documentos e **traduz o
gabarito junto**, por mapa de offsets. `scripts/medir_robustez.py` roda o
pipeline sobre cada variante e pontua pela métrica oficial.

Sete classes de ruído, cada uma isolável — atribuir a degradação é o ponto, e um
agregado que cai de 1,09 para 0,76 não diz o que consertar.

## Por que ele existe

Todas as regras de `deteccao.py` nasceram de um caso concreto **desta** amostra:
o filtro de `fls. <n>/<n>`, o de `OAB/<UF> <n>`, o `d[eoc]` que cobre
"relatoria **dc** <nome>" (e→c no conector). Isso dá 1,0988 aqui e não diz nada sobre o
conjunto cego.

## Validação do arnês, antes de confiar nele

| checagem | resultado |
|---|---|
| taxa 0 reproduz o texto original | 26/26 documentos idênticos |
| taxa 0 reproduz os offsets | 192/192 |
| taxa 0 reproduz o score | **1,0988, Δ +0,0000** |
| offsets válidos a taxa 0,6, por classe | **192/192 nas 7 classes** |

Sem isso, toda medição seguinte estaria medindo o arnês em vez do pipeline.

## O resultado, a taxa 0,15

A taxa 0,15 é o ponto de operação realista: dá cerca de uma corrupção por
identificador de sete dígitos, que é o que a amostra de desenvolvimento mostra.

| classe | score | Δ |
|---|---|---|
| `separador_uf` | 1,0988 | **0,0000** |
| `sigla_nao_vista` | 1,0988 | **0,0000** |
| `marca_numero` | 1,0912 | −0,008 |
| `ordem_incompleta` | 1,0827 | −0,016 |
| `quebra_identificador` | 1,0452 | −0,054 |
| `ocr_palavra` | 0,9998 | −0,099 |
| **`ocr_numero`** | **0,8395** | **−0,259** |
| todas juntas | 0,7616 | −0,337 |

**O zero em `sigla_nao_vista` confirma a ADR 0002** por caminho independente:
ancorar a detecção no número em vez da sigla processual realmente generaliza
para classes fora do vocabulário observado.

**`ocr_numero` é o ponto fraco**, com folga. E note o que ele significa: o dev
set tem esse mesmo nível de ruído e marcamos 1,0988 nele. A diferença é que lá o
ruído está em posições que as regexes foram ajustadas para pegar; aqui ele cai
em posição aleatória. É o sobreajuste que o arnês foi feito para expor.

## Correção adotada: OCR por token, não por adjacência

`normalizacao._corrigir_ocr` convertia letra em dígito **só quando ela encostava
num dígito**, testando contra a string original. Corrupções consecutivas não se
resgatavam. Num número sintético, `9.876.543` corrompido para `g.B7G.S43`: as
letras da frente não encostam em dígito sobrevivente, ficam como letra, e o
núcleo perde os dígitos iniciais.

A regra nova olha o **token inteiro**: se ele é feito só de dígitos e letras
confundíveis, é um número, e todas as letras convertem. A adjacência continua
como segunda passada, para letra isolada colada ao número.

| | antes | depois |
|---|---|---|
| citações `real` irrecuperáveis sob `ocr_numero` (taxa 0,4) | 44% | **9%** |

**Efeito colateral que custou uma regressão.** A primeira versão derrubou o score
para 1,0561, com 11 `real→inventada`. Causa: o núcleo da detecção aceita letra de
OCR como continuação do número, então num span terminado em `/SP` ele engole o
`S` e deixa o `P` de fora — e a regra de token converte esse `S` em `5`.

Conserto: `separar_uf` passou a aceitar **uma** letra depois do separador, não só
duas. Número de processo não termina em barra mais letra; isso é UF truncada.

## Correção rejeitada: detecção tolerante a dígito inicial corrompido

O núcleo exigia começar em dígito real. Sob ruído o primeiro caractere é
corrompido como qualquer outro, e o número inteiro se perdia. A tentativa foi
deixar o núcleo começar em "digitoide" (dígito ou letra que o OCR põe no lugar).

**Não entrou.** Medido com três sementes:

| taxa | sem a mudança | com a mudança |
|---|---|---|
| **0,15** (realista) | **0,8908** | 0,8802 |
| 0,30 (extrema) | 0,6999 | **0,7321** |

Ela só ganha em ruído mais agressivo do que o desafio tem, e perde no ponto de
operação. Trocaria detecção por espúrias: a versão tolerante lia prosa corrompida
como número — foram 31 falsos positivos na base limpa, todos `fls. <n>/<n>`, até
adicionar um lookbehind que rejeita letra precedida de letra.

Fica registrada porque a medição tem valor: se algum dia o ruído do conjunto cego
se mostrar mais forte que o da amostra, a mudança está desenhada e medida.

## O que ficou aberto

1. **`ocr_numero` segue sendo o ponto fraco** (−0,259 no ponto realista). Os 9
   casos irrecuperáveis que restam são todos de um mesmo tribunal, cujo prefixo
   de classe é composto: as letras dele não são mapeáveis e a regra de token recusa
   o pedaço inteiro.
2. `ocr_palavra` cria espúrias (−0,099): prosa corrompida virando citação.
3. A fase 3 (dataset estrutural dos 996 acórdãos) não começou.
4. **Nada foi submetido ao Kaggle.** `data/submission.csv` está gerado e
   validado contra a métrica oficial, aguardando envio manual.

## Limite honesto

O arnês mede robustez ao ruído que **sabemos imaginar** — as sete classes saíram
de `docs/investigacao.md`, que descreve o que a amostra mostra. O conjunto cego
pode trazer outro tipo. Isso reduz a chance de surpresa, não a elimina.
