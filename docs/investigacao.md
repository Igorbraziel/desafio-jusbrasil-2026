# Investigação da amostra de desenvolvimento

O que foi medido nos 26 documentos e na base canônica, com o comando que produz
cada número. São observações sobre os dados — não decisões de implementação, que
vão em [decisoes/](decisoes/).

Tudo aqui vale para a distribuição de 28/08/2026 (checksums em
[dados.md](dados.md#como-obter)).

## Composição do gabarito

225 citações em 26 documentos:

| | `real` | `inventada` | `incompleta` | total |
|---|---|---|---|---|
| nível 1 | 52 | 32 | 32 | 116 |
| nível 2 | 44 | 32 | 33 | 109 |

Por tipo: 186 `jurisprudencia`, 39 `lei`. Todas as 96 `real` têm `id_canonico`;
nenhuma não-`real` tem.

## As `incompleta` são duas formas fixas

Nenhuma das 65 citações `incompleta` tem número de processo. Elas se dividem em:

- **33 frases vagas**, sem identificador nenhum: "jurisprudência pacífica desta
  Corte", "normas de regência da matéria", "verbete sumular aplicável à espécie",
  "dispositivo legal de regência".
- **32 do padrão tribunal + ano + relator**: "julgado do STF proferido em 2024
  pela relatoria de Dias Toffoli", "Rcl de 2021, Rel. Min. Rosa Weber". Os únicos
  dígitos são o ano.

Isso simplifica a resolução: se a citação carrega número de processo, ela é
`real` ou `inventada`; a decisão de `incompleta` é tomada na detecção.

**Ressalva:** isso vale para a amostra de desenvolvimento. O conjunto cego tem
"distribuição de classes equivalente", mas nada garante que use as mesmas frases.

## Onde o número do processo aparece na base

O material do desafio avisa que o FTS devolve quem cita, não só quem é. Medindo
onde o número da citação aparece no documento que o gabarito aponta:

| tribunal | onde está o número próprio |
|---|---|
| STF, STJ, TSE, STM | no cabeçalho, nas primeiras centenas de caracteres |
| TST | **não está no cabeçalho** — aparece na fórmula `… estes autos de <classe> nº TST-RR-…`, por volta do caractere 1.000, e de novo no rodapé |

O TST é o que quebra um limiar de posição ingênuo.

Contraexemplo do porquê a posição importa: o número `22357` aparece em nove
lugares da base — todos citando `MS 22.357` dentro do texto de outros acórdãos.
A citação `Reclamação nº 22.357/PE` é anotada como `inventada`: não existe
Reclamação com esse número na cobertura. Resolver por contenção erraria.

## Três pares de duplicatas com `id` diferentes

A organização removeu `doc_0227` e `doc_0461` e informou que as duplicatas
remanescentes não têm par no gabarito. Na prática, três números são o número
próprio de dois registros distintos, e o gabarito escolhe um:

| número | candidatos | gabarito escolhe | `texto_len` |
|---|---|---|---|
| `213-85.2010.5.02.0030` | doc_0662, doc_0670 | doc_0670 | 95.386 vs **95.622** |
| `79500-16.2009.5.15.0016` | doc_0640, doc_0657 | doc_0640 | **99.783** vs 99.546 |
| `25823-78.2015.5.24.0091` | doc_0710, doc_0729 | doc_0710 | **95.681** vs 60.988 |

Nos três, o escolhido é o de maior `texto_len`. Não sabemos *por quê* — só que
foi assim nas três vezes observáveis. É pouca evidência para uma regra, e a
alternativa (tratar cardinalidade ≥ 2 como `incompleta`) erra os três.

## Os 18 registros que não são acórdão

O texto de súmulas e dispositivos é o **enunciado**: não contém o número da
súmula nem o nome do código. Resolver `Súmula 331 do TST` ou `art. 373, I, do
CPC` exige um mapeamento levantado à mão. São 18 registros, e a cobertura é
congelada — então o mapeamento é completo por construção: qualquer súmula ou
artigo fora dele é, por definição, `inventada`.

As tabelas estão em [`base_canonica.py`](../src/verificador/base_canonica.py) e
[`tests/test_base_canonica.py`](../tests/test_base_canonica.py) confere as duas
contra o banco.

Os 13 artigos têm números distintos entre si, o que tenta o atalho de casar só
pelo número. O atalho erra: `art. 290 do Código Penal Militar` é `real`,
`art 290 da Constituição Federal` é `inventada`.

## Ruído de OCR observado no nível 2

Além dos `0↔O`, `1↔l`, `5↔S`, `m↔rn` que o material menciona, a amostra também
traz `9↔g` (`1.45g.779`), `6↔G` (`6G.838`) e `0↔O` em posição final (`170076O`).

Nas palavras, o ruído é uma substituição por palavra e pode cair em qualquer
posição, inclusive a última letra: `entendirnento`, `jurisprudêneia`,
`profcrido`, `Fedcral`, `recentc`, `Magãlhães`, `assirn`.

## Ordem de grandeza do custo

Para calibrar expectativa contra o envelope (≤ 60 s/documento, teto de 4 h):

- Varrer os 998 acórdãos e indexar seus números: **~0,5 s**, resultando em
  ~136 KB de índice.
- A base inteira tem 93 MB e cabe folgadamente nos 32 GB de RAM do envelope.

Um pipeline determinístico opera três ordens de grandeza abaixo do teto. Se a
equipe optar por um modelo de pesos abertos, é esse orçamento que ele consome.
