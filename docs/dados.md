# Os dados

> Os dados **não estão neste repositório**. Foram enviados por e-mail apenas às
> equipes inscritas e não têm download público. `data/` inteiro está no
> `.gitignore`.

> ✅ **Atualizado em 10/09/2026** com a distribuição da aba *Data* do Kaggle
> (arquivos de 04/09). O gabarito passou de 225 para **195 citações**; a base
> canônica e os 26 `.txt` são bit a bit os mesmos de 28/08. Detalhes abaixo.

## Atualização do goldenset (01/09/2026)

A organização removeu do gabarito citações da classe `incompleta` que eram, na
prática, referências difusas — trechos que não apontam para nenhuma fonte
específica, só remetem de forma vaga à matéria ou à orientação de um tribunal.
Exemplos que **saíram** do gabarito:

- "normas de regência da matéria"
- "jurisprudência pacífica desta Corte"

O que **continua** sendo `incompleta`: citações que apontam uma fonte
específica e trazem contexto de identificação — tribunal, relator, ano, classe
processual — mas sem os identificadores mínimos para confirmar ou refutar a
existência do registro na base canônica. Exemplos:

- "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli"
- "Reclamação do STF, de 2025, Rel. Min. CRISTIANO ZANIN"
- "acórdão do TSE julgado em 2016 sob relatoria de HENRIQUE NEVES DA SILVA"

Critério, em uma frase: existe uma decisão concreta por trás da citação, mas os
dados fornecidos não permitem chegar a um registro único na base canônica —
isso a distingue de uma citação vaga demais para sequer contar como citação.

Medido contra o arquivo novo: saíram **30 citações**, todas `incompleta`,
nenhuma entrou e nenhuma mudou de classe. O gabarito foi de 225 para 195, e as
`incompleta` de 65 para 35 — de 29% para **18%** do total.

Das 35 que restaram, **32 são do padrão tribunal + ano + relator** e apenas
**3 são frases sem número**, e mesmo essas nomeiam uma fonte concreta:
"artigo correspondente do Código de Processo Civil" (2×) e "reiterados
precedentes do Superior Tribunal de Justiça". As genéricas ("normas de regência
da matéria", "jurisprudência pacífica desta Corte") sumiram por completo.

Consequência para a detecção: o repertório de frase vaga deixou de ser o
caminho principal para `incompleta` — o padrão tribunal + ano + relator agora
responde por 91% da classe. O texto de
[`deteccao.py`](../src/verificador/deteccao.py) sobre citações vagas foi escrito
contra o gabarito antigo e precisa ser revisto.

## Como obter

Fonte atual: a aba *Data* da competição no Kaggle
(<https://www.kaggle.com/t/b175ca36f02ce8d3a0422d3f7b339664>) — inclui os
documentos, a base canônica, o goldenset atualizado, o conversor de submissão e
o script oficial da métrica. O zip enviado por e-mail em 25/08 continua
funcionando para os documentos e a base canônica, mas o `goldenset.xlsx` dele é
o antigo.

### Caminho recomendado — `make dados-kaggle`

1. Gere um token da API em <https://www.kaggle.com/settings> → *API* →
   *Create New Token* e salve como `~/.kaggle/kaggle.json` (ou exporte
   `KAGGLE_USERNAME` e `KAGGLE_KEY`).
2. Rode `make dados-kaggle`. O script baixa a competição inteira com
   `kagglehub` e organiza em `data/dev/`: `txt/`, `desafio1_bracis.db`,
   `goldenset.csv`, `sample_submission.csv` e, em `data/dev/ferramentas/`, o
   `json_to_submission.py` e o `kaggle_metric.py` oficiais. Um `goldenset.csv`
   pré-existente é preservado como `goldenset_anterior.csv` para o diff.
3. Rode `make indice` para construir o índice de números próprios.

`kagglehub` **não** é dependência do projeto — a solução roda offline no
ambiente da organização, e nada de rede pode entrar no bundle reproduzível. O
alvo o injeta com `uv run --with kagglehub`.

### Caminho legado — zip do e-mail

1. Coloque o zip em `data/raw/dados_desafio_jusbrasil.zip` e o `goldenset.xlsx`
   em `data/dev/goldenset.xlsx`.
2. Rode `make dados`. O script extrai para `data/dev/`, descarta o lixo de macOS,
   imprime os checksums e converte o gabarito para CSV.

Este caminho continua servindo para os documentos e a base canônica, mas o
`goldenset.xlsx` do e-mail é o de 25/08.

Como `data/` não é versionado, são estes checksums que garantem que dois clones
estão olhando para os mesmos bytes. Confira depois de `make dados-kaggle`.

Distribuição atual — Kaggle, arquivos de 04/09/2026:

| Arquivo | SHA-256 |
|---|---|
| `desafio-jusbrasil-bracis-2026.zip` | `de2b4f308b4c01636ea285eaeb52ec170cbf8d6e3044ead595564ebe7dddae1a` |
| `desafio1_bracis.db` | `d759681be82ee00f383b49a5c76c42dd475564e042272e00730252468dcb6e71` |
| `goldenset.csv` | `3e28218c9e92974e006db520762113a96aab158320e97a1b584f5bc83263c8d1` |
| `ferramentas/kaggle_metric.py` | `3c4d30e70971144afbd0ae73c6d4ac887faf0f5926de986170de32f72544fc3f` |
| `ferramentas/json_to_submission.py` | `c6ec4963e884c7fc19939816d7398e512cc8f7d60af472fb1a3bd723f1fee05c` |

Distribuição anterior — e-mail de 28/08/2026 (o `.db` é o mesmo):

| Arquivo | SHA-256 |
|---|---|
| `dados_desafio_jusbrasil.zip` | `2a3716eb688e56e0c6c43823ab789099af50eae376ee01c29e795bf6484b5d02` |
| `goldenset.xlsx` | `496af2b3271a2872d21cb2a2fe110bf0f37130623904895cd8747db7b23735db` |

## Os documentos de entrada

Vinte e seis peças jurídicas sintéticas — petições, pareceres, decisões
monocráticas e memoriais fictícios que citam acórdãos reais do acervo. Cada
documento tem uma matéria coerente (cível, penal, trabalhista, eleitoral ou
militar) que amarra o cabeçalho, os tribunais citados e as normas invocadas.

O nome do arquivo entrega o nível: `gen_n1_001`…`gen_n1_013` são nível 1 e
`gen_n2_001`…`gen_n2_013`, nível 2.

| | Nível 1 (1×) | Nível 2 (2×) |
|---|---|---|
| documentos | 13 | 13 |
| citações | 101 | 94 |
| tamanho médio | 3.372 chars | 3.276 chars |
| `real` / `inventada` / `incompleta` | 52 / 32 / 17 | 44 / 32 / 18 |

Esta é a **amostra de desenvolvimento**. O conjunto final é cego, tem o mesmo
formato, os mesmos níveis e distribuição de classes equivalente. Ele não é
distribuído: ao fim da janela, a organização executa o código submetido sobre
ele, e é dele que sai o ranking oficial.

### A mesma citação, escrita de dois jeitos

As citações do nível 2 apontam para registros igualmente válidos — o que muda é
a superfície. Todas as amostras abaixo são `real`:

| Nível 1 | Nível 2 |
|---|---|
| `AREsp nº 1.996.496/RJ` | `AgRg no Rec. Esp. n. 1.522.200 (SC)` |
| `Recurso em Habeas Corpus nº 57.763/PR` | `Recurso em Habeas Corpus nº 93967 - SC` |
| `RSE nº 7000592-58.2025.7.00.0000/DF` | `Rec. Esp. No 1.880.529\n- SP` |
| `Súmula Vinculante 10` | `5úmula 211 do STJ` |

O ruído combina variantes de abreviação (`REsp` / `R.Esp.` / `Recurso
Especial`), formatação do número (`1.741.784` / `1741784` / `1.741. 784`),
separador de UF (`/PR`, `- PR`, `(PR)`), confusões de OCR (`0↔O`, `1↔l`,
`5↔S`, `m↔rn`, e observamos também `9↔g` e `6↔G`) e quebras de linha no meio
do identificador.

> **Garantia do ruído:** um dígito nunca é trocado por outro dígito. Isso mudaria
> a identidade da citação e transformaria uma `real` ruidosa numa `inventada` de
> fato. Todo ruído aplicado a uma citação real é recuperável por normalização —
> que é exatamente o que o nível 2 mede.

### Distratores

Os cabeçalhos trazem números que parecem citação e não são: número dos autos em
formato CNJ, protocolo, inscrição na OAB, `fls. 234/567`, valor da causa.
Nenhum está no gabarito, e extraí-los conta como falso positivo.

Atenção à distinção no formato CNJ: o número dos autos do **próprio documento**,
no cabeçalho, é distrator; a referência a **outro processo** em formato CNJ, no
corpo do texto, é citação. É por isso que
[`texto.fim_do_cabecalho`](../src/verificador/texto.py) existe.

## A base canônica

Um SQLite de 93 MB com os 1.016 registros que definem o universo do desafio. É
contra ele que uma citação é `real` ou `inventada`. É a **cobertura congelada**:
se um acórdão existe no mundo mas não está aqui, para efeito do desafio ele não
existe — e, por construção, isso nunca prejudica ninguém, porque toda citação
real dos documentos resolve dentro da cobertura.

```sql
CREATE TABLE documentos (
    documento_id  TEXT PRIMARY KEY,   -- chave interna; doc_0201 para acórdãos
    id            INTEGER NOT NULL UNIQUE,  -- doc_id do Jusbrasil -> id_canonico
    tribunal      TEXT,               -- STF, STJ, TSE, TST, STM; nulo em lei
    ano           INTEGER,            -- só acórdãos
    relator       TEXT,               -- só acórdãos
    natureza      TEXT NOT NULL,      -- acordao · sumula · dispositivo
    tipo          TEXT NOT NULL,      -- jurisprudencia · lei
    texto         TEXT NOT NULL,      -- inteiro teor
    texto_len     INTEGER NOT NULL
)
```

| natureza | registros | o que são |
|---|---|---|
| `acordao` | 998 | acórdãos de STF, STJ, TSE, TST e STM (≈200 de cada) |
| `sumula` | 5 | súmulas do STJ, STF e TST, incluindo vinculante |
| `dispositivo` | 13 | artigos de CPC, CC, CLT, CF/88, CPP, CPM, CDC, Código Eleitoral e LC 64/1990 |

`natureza` existe porque `tipo` sozinho não separa acórdão de súmula — os dois
são `jurisprudencia`.

Há ainda uma tabela virtual `documentos_fts` (FTS5, external content,
`unicode61 remove_diacritics 2`) indexando o texto integral. Ela não duplica o
conteúdo — aponta para `documentos` pelo `rowid`. Ver a armadilha 4 abaixo antes
de usá-la.

### Atualizações de 28/08/2026

- `gen_n2_010.txt` foi corrigido; os offsets do gabarito já refletem o texto novo.
- `doc_0227` e `doc_0461` foram removidos: eram duplicatas exatas, o mesmo
  julgado indexado duas vezes sob doc_ids diferentes, o que criava duas
  respostas certas para a mesma citação. A base passou de 1.018 para 1.016.
- Existem **outras duplicatas** no acervo. A organização informou que nenhuma
  citação do gabarito aponta para elas; medindo, encontramos três casos em que
  aponta — ver
  [investigacao.md § Três pares de duplicatas](investigacao.md#três-pares-de-duplicatas-com-id-diferentes).

## O gabarito

`goldenset.csv` — uma linha por citação esperada, 195 no total, nos 26
documentos. Vem pronto na aba *Data*; `make dados-kaggle` o copia para
`data/dev/goldenset.csv`. (O `goldenset.xlsx` do e-mail é o gabarito antigo, de
225 linhas; `make dados` ainda o converte, para efeito de comparação.)

| Coluna | Descrição |
|---|---|
| `nivel` | 1 ou 2 — define o peso na nota |
| `documento_id`, `citacao_id` | identificam a citação (`gen_n1_004` + `g3`) |
| `inicio`, `fim` | span em codepoints Unicode, fim exclusivo |
| `trecho` | cópia literal de `texto[inicio:fim]` |
| `tipo` | `lei` ou `jurisprudencia` |
| `classificacao` | a classe esperada — é o que se pontua |
| `id_canonico` | o doc_id do registro que resolve a citação; só nas `real` |

## Armadilhas

Cada uma destas custou tempo. Elas estão aqui para não custarem de novo.

### 1. `documento_id` não é `id_canonico`

`documento_id` (`doc_0201`) é a chave interna do acervo e o nome do arquivo.
`id` é o doc_id do Jusbrasil, e é **ele** que vai em `resolucao.id_canonico`.
Entregar `doc_0201` onde se espera `2566535283` derruba a citação para erro,
mesmo com a classe certa.

### 2. `id_canonico` vem como float no xlsx

No `goldenset.xlsx` o campo está gravado como número de ponto flutuante:
`5.665364632E9`. Ler com pandas ou openpyxl sem cast devolve `5665364632.0`, que
não casa com nenhum `id`. Vale o mesmo para `nivel`, `inicio` e `fim`.
[`preparar_dados.py`](../scripts/preparar_dados.py) converte para inteiro.

### 3. `trecho` traz `\n` escapado

As quebras de linha aparecem no gabarito como a sequência de dois caracteres
`\\n`, não como LF. Comparar direto com `texto[inicio:fim]` falha até
desescapar.

### 4. O FTS não casa número sem pontuação

O tokenizador `unicode61` quebra em qualquer caractere não alfanumérico:
`1.741.784` vira três tokens (`1`, `741`, `784`).

```sql
-- funciona: a busca por frase reproduz a sequência de tokens
WHERE documentos_fts MATCH '"1.741.784"';   -- 1 resultado
-- não funciona: sem separadores é um token só, que não existe no índice
WHERE documentos_fts MATCH '1741784';       -- 0 resultados
```

Como o nível 2 entrega números sem pontuação com frequência, o pipeline precisa
reconstruir a forma canônica. Nós resolvemos isso normalizando **os dois lados**
para dígitos puros e indexando por eles, o que dispensa o FTS.

### 5. O FTS devolve quem cita, não só quem é

Esta é a armadilha que mais custa precisão. Acórdãos citam uns aos outros o
tempo todo: uma busca por `"1.276.977"` devolve seis documentos do STF, e
**nenhum deles** é o RE 1.276.977 — todos apenas o citam. O sinal que separa os
dois casos é a posição: no documento que *é* o processo, o número está no
cabeçalho; nos que apenas citam, ele aparece no corpo.

O TST é a exceção que quebra o limiar de posição ingênuo: o número não está no
cabeçalho, e sim na fórmula `… estes autos de <classe> nº TST-RR-…`, por volta
do caractere 1.000. Ver
[investigacao.md § Onde o número aparece](investigacao.md#onde-o-número-do-processo-aparece-na-base).

### 6. Leis e súmulas resolvem por registro próprio

Buscar "Súmula 83 do STJ" no texto dos acórdãos devolve dezenas de documentos
que a mencionam — nenhum deles é a súmula. Os 18 registros de natureza `sumula`
e `dispositivo` existem para isso: são o alvo da resolução, não o texto que
cita. E o texto deles é o **enunciado**: não contém o número da súmula nem o nome
do código. Daí a tabela curada em
[`base_canonica.py`](../src/verificador/base_canonica.py), conferida contra o
banco por [`tests/test_base_canonica.py`](../tests/test_base_canonica.py).

### 7. O número do artigo não basta para identificar o dispositivo

`art. 290 do Código Penal Militar` é `real`; `art 290 da Constituição Federal`
é `inventada`. Os 13 artigos da cobertura têm números distintos entre si, o que
tenta o atalho de casar só pelo número — e o atalho erra exatamente nos casos
que o gabarito construiu para pegá-lo.

## Riscos conhecidos para o conjunto cego

Coisas que a amostra de desenvolvimento **não** consegue medir, e que valem
cautela ao construir a solução:

- **As frases vagas podem ser outras.** As 35 citações `incompleta` do dev set
  usam um repertório fechado de formas — 32 do padrão tribunal + ano + relator e
  3 frases sem número. Uma solução que dependa de casar essa lista específica não
  generaliza — e as `incompleta` são 18% do gabarito.
- **O ruído do nível 2 é amostrado.** As confusões de OCR observadas são um
  subconjunto do que o gerador sabe produzir.
- **As siglas processuais observadas não esgotam o domínio.** Uma classe
  processual não vista faz a citação perder o prefixo; com sorte o span ainda
  casa por IoU ≥ 0,5, mas fica curto.
- **Qualquer score medido nos 26 documentos é otimista**, porque é a mesma
  amostra usada para construir a solução. O leaderboard público (40% do teste) é
  a primeira medida honesta, e mesmo ele não é o ranking final.
