# 07 — As famílias que o reparo de OCR não alcançava

**Data:** 23/09/2026 · **Estado:** nove correções em produção · NER medido e descartado

## Por que esta etapa existe

Com o F1 saturado em 1,0 no dev, o checkpoint 06 deixou `ocr_numero` como "o
ponto fraco" e a família `processo` como alvo. Antes de atacar, esta etapa mediu
**onde** as citações sumiam sob ruído, por família — medição que nenhum
checkpoint anterior tinha feito:

| classe de ruído, 5 sementes | `disp/súm/tema` perdidos | `processo` perdidos | `vaga` |
|---|---|---|---|
| `ocr_numero` | **40** | 22 | 0 |
| `ocr_palavra` | **17** | 22 | 4 |
| todas (7) | **57** | 43 | 3 |

**A família que mais perdia não era a que tinha sido atacada.** O cp 06 ensinou
`processo` a atravessar o digitoide; `dispositivo` e `sumula` continuavam
exigindo dígito puro e palavra-chave literal. `_corrigir_ocr` já reparava todos
esses casos (`I86`→`186`, `B96`→`896`) — a detecção nunca lhe entregava o trecho.
É a mesma forma de defeito do cp 06, repetida em duas famílias.

Um segundo instrumento entrou nesta etapa: `scripts/medir_espurias.py`, que roda
a detecção sobre os **996 acórdãos reais** da base e conta spans por família.
Sem gabarito não é precisão, mas é volume comparável entre versões — e foi o que
pegou quatro falsos positivos que as correções abriam antes de entrarem.

## As correções

Cada uma veio com o caso que a motivou nos testes.

1. **Digitoide no número do artigo, da súmula, do tema, do parágrafo e da lei**,
   com o contrapeso de ao menos um dígito real (`art Iss` não casa).
2. **Palavra-chave tolerante ao ruído de letra** (`Súrnula`, `Códlgo`,
   `rclatoria`), só nas âncoras fixas das expressões. As confusões vieram
   medidas do nível 2 da amostra contra o vocabulário do nível 1: `e→c` 33,
   `a→ã` 31, `c→e` 15, `i→l` 11, `m→rn` 11.
3. **Formas correntes que a amostra não tem**: `Súmula nº 83` (a grafia da
   própria base canônica), romano de até oito caracteres (`LXXVIII`), `caput`
   (424 dos 996 acórdãos reais), `incisos I e II`, `LC`, `Decreto-Lei` (como a
   base nomeia a CLT).
4. **O erro grave da Constituição.** A regra excluía uma lista de qualificadores
   ruins (`estadual`, `do estado`); qualquer outro passava:
   `art. 5º da Constituição Portuguesa` resolvia para o art. 5º da CF/88. Virou
   inclusão — só os qualificadores da CF/88 —, e o ano de versão passou a ser
   conferido (`Código Civil de 1916`, `CPC/73` são `inventada`).
5. **O número lido antes de consultar.** `_inteiro` descartava as letras:
   `3l73` virava 373, artigo da cobertura — `inventada` → `real`. O reparo vem
   antes. O ordinal `5o` é lido como 5; o `5O` maiúsculo, confusão documentada,
   não.
6. **Número de processo com poucos dígitos reais.** Sob ruído, `Rcl 4B.71B/RS`
   fica com três. Aceito com dois ou mais, quando o número reparado tem quatro e
   o prefixo nomeia uma classe processual. O limite de dois saiu dos acórdãos
   reais: com um, passavam `III.3` e `3SSIL`.
7. **Grupo inteiro corrompido dentro de número estruturado** (`4736-oS.Z011`):
   nenhuma letra encosta num dígito, e o número era partido ao meio. Era quase
   todo o `real` → `inventada` restante, concentrado no TST.
8. **A cadeia de prefixo atravessa o elo desfigurado** (`n º`, `cspecial`).
   Eram os cinco `(espúria) → real`, a forma de erro mais próxima de τ.
9. **O nome do diploma com ruído de letra**, desfeito contra o vocabulário
   fechado dos diplomas. `militar` e `estadual` estão nele para que o CPPM e a
   constituição estadual corrompidos continuem recusados.

Mais quatro falsos positivos fechados: `logo` lido como ano, `OAB sob o nº`,
centavos (`1.500.000,00`), e `tel` casando dentro de "tutela nº".

## A medição

Mesmo arnês, taxa 0,15, 5 sementes — comparável ao cp 06.

| classe | main (cp 06) | agora | pior main | pior agora |
|---|---|---|---|---|
| **todas (7)** | 1,0093 | **1,0969** | 0,9764 | **1,0943** |
| `ocr_numero` | 1,0455 | **1,0993** | 1,0162 | 1,0966 |
| `ocr_palavra` | 1,0384 | **1,1000** | 1,0232 | **1,1000** |
| `marca_numero` | 1,0965 | **1,1000** | 1,0916 | 1,1000 |
| `quebra_identificador` | 1,0977 | **1,1000** | 1,0916 | 1,1000 |
| `separador_uf` · `sigla_nao_vista` · `ordem_incompleta` | 1,0992 | 1,1000 | — | imunes |

**Seis das sete classes imunes nas cinco sementes.** τ = 0 em todas as
execuções. A referência limpa passou de 1,0992 para **1,1000** pela recalibração
da confiança (abaixo).

Fora do ponto calibrado, a taxa 0,30 (o dobro), 3 sementes:

| classe | main | agora |
|---|---|---|
| todas (7) | 0,8974 | **1,0744** |
| `ocr_numero` | 0,9721 | **1,0829** |
| `ocr_palavra` | 0,9896 | **1,0908** |

A perda de recall residual a 0,30 é de 48 em 4.608 citações (1,0%).

## A confiança

As correções mudaram a acurácia dos caminhos, e a tabela calibrada no cp 05
ficou do lado errado do ótimo do Brier. O maior salto: `inventada_processo`
foi de 158/190 para 416/421 — era onde o número mal lido de uma `real` caía.
Recalibrada nas duas taxas do arnês, com Laplace e teto de 0,99; `real_desempate`
fica em 0,83 porque suas observações são um caso só, repetido.

A recalibração vence sempre que a acurácia real do caminho no conjunto cego
ficar acima de ~0,90. No pior caso plausível (0,80), custa 0,0007 no score do
nível.

## O NER de pesos abertos

Pedido explicitamente, medido com o desenho mais favorável, e descartado. Ver a
[ADR 0004](../decisoes/0004-ner-de-pesos-abertos.md). Resumo: sobre a detecção do
meio desta etapa ele ganhava até +0,013 a taxa 0,30; cada citação que ele achava
virou teste e regra, e sobre a detecção final ele **perde** em todos os corpora.

## Números

- Score limpo **1,1000** (era 1,0992), F1 macro 1,0000, τ = 0.
- Testes: **161 → 310**. `resolucao.py` ganhou a primeira suíte dedicada.
- `test_ponta_a_ponta.py` passou a travar F1 em 1,0 e IoU mínimo em 0,75.
- Volume nos 996 acórdãos reais (`medir_espurias.py --amostra 996`): `processo`
  8.601 → 8.461; `sumula` 613 → 1.208 e `tema` 504 → 609, conferidos à mão —
  são `Súmula nº N` e `Tema nº N` que antes não eram detectados.

## Correção de registro

O README e o cp 06 diziam que só `quebra_identificador` perdia a imunidade. Na
mesma medição, `marca_numero` também perdia, em duas sementes, com o mesmo
mínimo (1,0916) — era a mesma citação. As duas estão imunes agora.

## O que ficou aberto

1. **O número sem nenhum dígito real** (`RHC nº 7s.soB/RS`, `Rcl BB.gbG/RJ`).
   Pela forma, é indistinguível de uma palavra — nos acórdãos reais, o limite de
   dois dígitos é o que separa citação de `3SSIL`. É o resíduo a taxa 0,30.
2. **O conjunto cego não é o arnês.** O arnês mede o ruído que sabemos gerar; o
   leaderboard sobre o conjunto final é a primeira medida honesta.
3. **Desempate de duplicatas** (ADR 0003) segue arbitrário.
