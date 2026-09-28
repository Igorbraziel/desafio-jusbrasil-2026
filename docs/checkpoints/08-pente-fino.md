# 08 — Pente fino: o que as sondas fora da amostra mostraram

**Data:** 24/09/2026 · **Estado:** oito correções na branch `pente-fino-prefixo-e-constituicao`, para revisão antes do merge

## Por que esta etapa existe

Com o F1 saturado em 1,0 no dev, o arnês mede o ruído que sabemos gerar, sobre
a prosa que o gerador escreveu. Esta etapa fez outra pergunta: **o que acontece
com contextos que o gerador não escreve?** Foram três instrumentos:

1. **Sondas sintéticas**, com a mesma citação em contextos diferentes: o órgão
   julgador antes dela, verbo depois do diploma, o tribunal da súmula em outras
   grafias, qualificadores correntes do artigo, entradas patológicas.
2. **Diferencial nos 996 acórdãos.** O pipeline de duas árvores (`main` e a
   branch) roda sobre a base inteira, os spans são cruzados por IoU ≥ 0,5, e o
   resultado é contado e amostrado por tipo de mudança: novo, sumido, mudou de
   classe, só borda.
3. **Comparação com a árvore anterior ao cp 07**, que foi o que expôs a
   regressão da Constituição.

## O que as sondas acharam, e as correções

Cada correção é um commit, com o teste que a motivou.

| # | defeito | sonda | antes | agora |
|---|---|---|---|---|
| 1 | um arquivo com falha derruba o lote | `.txt` latin-1 no começo da pasta | **0 de 27** JSONs | 27 de 27; o ruim sai vazio |
| 2 | o órgão julgador entra no prefixo | "do Superior Tribunal de Justiça Rcl nº 12.345/SP" | IoU 0,33 | 1,00 |
| | | "Ministro Relator Gilmar Mendes Rcl…" | IoU 0,34 | 1,00 |
| | | "do Recurso Extraordinário e da Rcl…" | IoU 0,34 | a Rcl sozinha |
| 3 | o conector abre o span | "no REsp 1.234.567/RJ" (41 spans no dev) | IoU p5 0,854 | 1,000 |
| 4 | **regressão do cp 07**: a CF com verbo ou com ano | "art. 5º da Constituição garante" · "art. 5º da CF de 1988" | `inventada` | `real` |
| 5 | a prosa entra no nome do Código | "art. 186 do Código Civil trata do ato" | IoU 0,65 | 1,00 |
| 6 | o tribunal da súmula em outras formas | "Súmula 83/STJ" · "Súmula 331, I, do TST" · por extenso | `inventada` | `real` |
| 7 | qualificadores correntes do artigo | "parágrafo único" · "inc. LV" · "caput e inciso LV" | não detectado | detectado |
| 8 | a data com ponto vira processo | "Sessão Virtual de 20.6.2025" | processo `inventada` | nada |

A causa da regressão 4 foi o `IGNORECASE` de `_DISPOSITIVO`: o `[A-ZÀ-Ú]` do
qualificador da Constituição casava minúscula, e o verbo virava qualificador.
A regra de inclusão do cp 07, que é correta, então o recusava. As correções 4 e
5 usam o mesmo desenho: a palavra do nome precisa ter inicial maiúscula, com
`(?-i:…)`, ou pertencer a uma lista fechada de minúsculas. Essa lista inclui as
formas que precisam ser **recusadas** ("constituição estadual", "código de
processo penal militar"), para que a direção do τ não se abra.

A correção 2 usa um léxico fechado de quem julga (tribunal, ministro, turma,
corte…), da mesma natureza de `_PALAVRA_DE_PROSA`. Ela não enumera classes
processuais, então a ADR 0002 continua valendo.

## A medição

**Dev, pela métrica oficial:** 1,1000, F1 1,0000 nos dois níveis, τ = 0,
inalterado em cada um dos oito commits. O IoU mínimo foi de 0,8125 para 0,854,
e o portão do teste ponta a ponta subiu de 0,75 para 0,80.

**Arnês, 0,15 com 5 sementes e 0,30 com 3:** idêntico ao `main`, por classe e
por semente, nas duas taxas (re-medido lado a lado na revisão de 24/09).

| classe | `main` (0,15) | branch (0,15) | `main` (0,30) | branch (0,30) |
|---|---|---|---|---|
| **todas (7)** | 1,0969 | 1,0969 | 1,0854 | 1,0854 |
| `ocr_numero` | 1,0993 | 1,0993 | 1,0942 | 1,0942 |
| `ocr_palavra` | 1,1000 | 1,1000 | 1,0915 | 1,0915 |
| pior semente, todas (7) | 1,0943 | 1,0943 | 1,0719 | 1,0719 |

**Correção de registro:** a primeira versão deste checkpoint comparava a 0,30
com os números do cp 07 (1,0744 em todas) e atribuía a esta branch o ganho até
1,0854. Esse ganho já estava no `main`: o cp 07 mediu a 0,30 antes dos últimos
commits daquela etapa. As correções daqui não mexem no arnês; o ganho delas é
fora da amostra — sondas e acórdãos reais, abaixo.

**Confiança:** `medir_confianca.py` nas duas taxas. Todos os caminhos continuam
em 100%, exceto `inventada_processo`, que ficou em 417/423: pela regra de
Laplace, continua 0,98. A tabela `CONFIANCA` não muda.

**Diferencial nos 996 acórdãos** (texto inteiro, 196.485 spans no `main`):

- **597 `inventada` → `real`, todos da cobertura:** 573 súmulas (331/TST,
  83/STJ, 211/STJ) e 24 CF (arts. 5 e 7). Nenhum diploma ou tribunal fora
  da cobertura virou `real`.
- 48.712 mudanças só de borda, quase todas conector ou órgão julgador saindo do
  prefixo.
- 684 spans novos sem par no `main`, quase todos dispositivos com `inc.`,
  `parágrafo único` e `caput e inciso`. Numa amostra de 15, 14 estavam
  corretos. O outro é o número de uma lei numa ementa em caixa alta ("FATOS
  ANTERIORES À VIGÊNCIA DA LEI Nº 13.467/17") lido como processo, com o prefixo
  em caixa alta engolido: é uma forma de ementa, e o `main` já errava nela.

**Volume** (`medir_espurias.py --amostra 996`, janela de 4.000 caracteres):
`processo` 8.461 → 7.917. As 540 remoções foram conferidas uma a uma pela
forma, e todas são data. `dispositivo` 2.048 → 2.078; `sumula`, `tema` e
`vaga` inalterados.

**Testes:** 310 → 361.

## O que ficou aberto

1. **Hifenização silábica na quebra de linha** ("Consti-\ntuição", "Súmu-\nla")
   faz a citação sumir, e "Constituição Fe-\nderal" sai `inventada`. Não há
   evidência de que o gerador produza isso, e a correção mexe em todas as
   âncoras.
2. **Número partido por quebra de página** e **vírgula como milhar**
   ("68,244"): a citação some.
3. **Título em caixa alta na linha anterior** ("FUNDAMENTAÇÃO\nRcl nº…") entra
   no prefixo (IoU 0,53). Ainda casa; restringir a travessia da quebra de linha
   arriscaria as quebras do nível 2, que o gabarito anota.
4. **"Súmula 83 desta Corte"** continua sem tribunal: depende de quem escreve.
5. **A anotação manual de 20 a 30 acórdãos**, para medir precisão e recall em
   texto real, continua pendente. O diferencial daqui mede mudança, não acerto.
