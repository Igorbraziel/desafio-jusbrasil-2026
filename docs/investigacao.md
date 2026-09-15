# Investigação da amostra de desenvolvimento

O que foi medido nos 26 documentos e na base canônica, com o comando que produz
cada número. São observações sobre os dados — não decisões de implementação, que
vão em [decisoes/](decisoes/).

Tudo aqui foi re-medido contra a **distribuição final de 15/09/2026**
(checksums em [dados.md](dados.md#como-obter)), que mexeu nas três frentes: 192
citações no gabarito, 1.014 registros na base e três `.txt` corrigidos. Ver
[dados.md § Atualização final](dados.md#atualização-final-15092026).

## Composição do gabarito

192 citações em 26 documentos:

| | `real` | `inventada` | `incompleta` | total |
|---|---|---|---|---|
| nível 1 | 52 | 32 | 15 | 99 |
| nível 2 | 44 | 32 | 17 | 93 |

Por tipo: 164 `jurisprudencia`, 28 `lei`. Todas as 96 `real` têm `id_canonico`;
nenhuma não-`real` tem.

As duas revisões do gabarito só mexeram em `incompleta`: 30 citações difusas
saíram em 01/09 e mais 3 em 15/09. As contagens de `real` (96) e `inventada`
(64) não mudaram em nenhuma das duas.

## As `incompleta` são hoje uma forma só

Depois da revisão de 15/09 a classe ficou homogênea. As 32 citações
`incompleta` seguem todas o padrão **tribunal + ano + relator**: "julgado do STF
proferido em 2024 pela relatoria de Dias Toffoli", "Rcl de 2021, Rel. Min. Rosa
Weber". Medindo:

| propriedade | vale para |
|---|---|
| o único dígito é o ano | 32 / 32 |
| nenhum número de processo (5+ dígitos seguidos) | 32 / 32 |
| nomeiam o relator | 32 / 32 |
| nomeiam o tribunal explicitamente | 26 / 32 |

As duas revisões esvaziaram as outras formas por etapas: 01/09 tirou as 30
frases genéricas ("normas de regência da matéria", "jurisprudência pacífica
desta Corte") e 15/09 tirou as 3 últimas frases sem número ("artigo
correspondente do Código de Processo Civil" 2×, "reiterados precedentes do
Superior Tribunal de Justiça"). O critério da organização é o mesmo nas duas:
sai o que não aponta para uma fonte específica.

Para a detecção isso significa que **o repertório de frase vaga não tem mais
papel nenhum** nesta classe — o sinal é a menção a relator sem número.

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

## Duplicatas: dois pares resolvidos, e a heurística caiu

Até 04/09, três números eram o número próprio de dois registros distintos, e o
gabarito escolhia um. A distribuição de 15/09 mexeu exatamente aqui.

| número | candidatos | `texto_len` | escolha até 04/09 | agora |
|---|---|---|---|---|
| `213-85.2010.5.02.0030` | doc_0662, doc_0670 | 95.386 vs 95.622 | doc_0670 | doc_0662 **removido** — sem ambiguidade |
| `79500-16.2009.5.15.0016` | doc_0640, doc_0657 | 99.783 vs 99.546 | doc_0640 | doc_0657 **removido** — sem ambiguidade |
| `25823-78.2015.5.24.0091` | doc_0710, doc_0729 | 95.681 vs 60.988 | doc_0710 | **doc_0729** — o gabarito mudou de lado |

Os dois registros que a organização apagou da base são precisamente os dois que
o gabarito **não** escolhia. Esses dois casos deixaram de ser ambíguos.

O terceiro é o resultado que importa. A versão anterior deste documento
observava que, nos três pares, o gabarito escolhia o de maior `texto_len`, e
ressalvava que era pouca evidência para uma regra. A revisão de 15/09 mudou
`gen_n2_005/g6` de `2813052232` (doc_0710, 95.681 chars) para `1974934139`
(doc_0729, 60.988 chars) — **o mais curto**. A heurística de `texto_len` está
refutada: era coincidência nas três observações, e o único par que sobrou a
contradiz.

Não há substituto à vista. Com um par ambíguo restante não dá para inferir
critério nenhum, e a alternativa de tratar cardinalidade ≥ 2 como `incompleta`
erraria esse caso. Fica como risco assumido para o conjunto cego.

## Os 18 registros que não são acórdão

Até 04/09 o texto de súmulas e dispositivos era só o **enunciado**: não continha
o número da súmula nem o nome do código, e o mapeamento sigla → `id_canonico`
teve de ser levantado à mão.

Em 15/09 a organização deu a esses mesmos 18 registros — a totalidade das
naturezas `sumula` e `dispositivo` — uma primeira linha que se autodeclara:

```
Súmula n. 331 do TST
As reclamações trabalhistas…

Artigo 14 da Lei nº 8.078, de 11 de setembro de 1990
Art. 14. O fornecedor de serviços responde…
```

O mapeamento passou a ser **derivável da base**, e o cabeçalho traz de brinde a
lei por extenso e datada, que o repertório de siglas não cobria — útil para
casar "Lei nº 8.078/90" tanto quanto "CDC". A cobertura continua congelada, então
o mapeamento segue completo por construção: qualquer súmula ou artigo fora dele
é, por definição, `inventada`.

As tabelas curadas continuam em
[`base_canonica.py`](../src/verificador/base_canonica.py) e
[`tests/test_base_canonica.py`](../tests/test_base_canonica.py) confere as duas
contra o banco — agora com a opção de derivá-las em vez de mantê-las à mão.

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

- Varrer os 996 acórdãos e indexar seus números: **~0,5 s**, resultando em
  ~136 KB de índice.
- A base inteira tem 94 MB e cabe folgadamente nos 32 GB de RAM do envelope.

Um pipeline determinístico opera três ordens de grandeza abaixo do teto. Se a
equipe optar por um modelo de pesos abertos, é esse orçamento que ele consome.
