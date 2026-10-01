# Verificador de Citações Jurídicas — Desafio Jusbrasil x BRACIS 2026

Sistema que lê um parecer jurídico em `.txt`, encontra todas as citações de
jurisprudência e de lei, e classifica cada uma em três classes:

| Classe | Quando | `resolucao` |
|---|---|---|
| `real` | resolve a **exatamente um** registro da base canônica | `id_canonico` obrigatório |
| `inventada` | identificadores suficientes para buscar, **nenhum** registro corresponde | `null` |
| `incompleta` | informação insuficiente para consultar, ou **dois ou mais** candidatos sem desempate | `null` |

A distinção entre `inventada` e `incompleta` é o ponto da tarefa: a inventada é
alucinação ativa de um LLM e deve ser bloqueada; a incompleta é evasiva e vai
para revisão humana.

## Execução da avaliação final

A nota oficial sai da execução deste repositório pela organização, sobre um
`.db` novo e documentos novos (e-mail de 29/09/2026; ver
[docs/desafio.md](docs/desafio.md#a-entrega-final-e-mail-de-29092026)). O ponto
de entrada é um só:

```bash
bash run.sh <caminho_db> <pasta_txt> <arquivo_saida> [pasta_json]
```

- **`<arquivo_saida>`** recebe o CSV no formato das submissões, byte a byte
  igual ao que o conversor oficial `json_to_submission.py` geraria: cabeçalho
  `documento_id,citacoes`, uma linha por documento, e na célula as citações
  `inicio,fim,classificacao,id_canonico,confianca` separadas por `|`, com `-`
  no id ausente e no documento sem citação, e a confiança com 4 casas. Ver
  [docs/contrato.md](docs/contrato.md).
- **`[pasta_json]`**, opcional, recebe também um JSON por documento, no schema
  1.2 do contrato.
- Antes de terminar, o `run.sh` confere o CSV com as mesmas checagens do
  avaliador oficial. Se o `.db` não existir, ele para com erro claro, em vez de
  cair num índice antigo.

**Requisitos.** Python ≥ 3.10, só com a biblioteca padrão: o `run.sh` usa o que
houver na máquina, ou o de `$PYTHON`. Sem Python, ou com `VERIFICADOR_DOCKER=1`,
ele roda via Docker e constrói a imagem se ela não existir. Não usa GPU, rede
nem arquivo nenhum de `data/`. O custo é da ordem de 1 s para preparar a base a
partir do `.db`, mais alguns milissegundos por documento.

**Via Docker**, o uso canônico (`$DB`, `$TXT` e `$SAIDA_DIR` são caminhos
absolutos no host):

```bash
docker build -t verificador-citacoes .
docker run --rm --network none \
  -v "$DB":/dados/base.db:ro \
  -v "$TXT":/dados/txt:ro \
  -v "$SAIDA_DIR":/saida \
  verificador-citacoes /dados/base.db /dados/txt /saida/submission.csv
```

**Com um `.db` novo, tudo o que é conteúdo da base sai dele**, em cada
execução e sem passo manual: o índice de números próprios dos acórdãos, as
súmulas e os dispositivos. Os dois últimos vêm da primeira linha autodeclarada
de cada registro (`Súmula n. <número> do <tribunal>`, `Artigo <número> da Lei nº
<número>, de <data>`). É o enriquecimento do `.db` que a regra permite, feito
pelo próprio `run.sh` sobre o banco no formato original: o banco é só lido, e o
que se deriva fica em memória. Fixo no código fica só conhecimento jurídico
público, um repertório de diplomas federais que leva do nome e da sigla ao
número e ao ano (CTN, ECA, LEP, LINDB, Lei Maria da Penha…). Um artigo que
exista no `.db` novo resolve para `real`; o que não existir sai `inventada`. Ver
a [ADR 0005](docs/decisoes/0005-base-nova-no-conjunto-cego.md).

A mesma entrada gera o mesmo CSV, byte a byte. Não há amostragem, o `run.sh`
fixa o `PYTHONHASHSEED`, e a confiança é uma constante por caminho de decisão,
que não varia com o hardware. A conferência em clone limpo, no container e em
Python 3.10, 3.11, 3.12 e 3.14 está no
[checkpoint 11](docs/checkpoints/11-entrega-final.md).

## Abordagem

Determinística, sem modelo e sem GPU: expressões regulares para achar as
citações, normalização para desfazer o ruído e uma consulta por chave à base
canônica ([ADR 0001](docs/decisoes/0001-baseline-deterministica.md)). O desenho
se apoia em quatro ideias:

1. **A classe é consequência da consulta, não de um classificador.** Uma
   citação com identificador suficiente é buscada na base: um registro é
   `real`, com o `id_canonico` dele; nenhum é `inventada`. A `incompleta` é a
   citação que aponta uma decisão concreta sem o número que a identificaria
   (tribunal, ano e relator), e nem chega a consultar a base. Dois registros
   com o mesmo número são desempatados pela classe processual em vez de
   rebaixados, porque a métrica cobra menos pelo link errado do que pela classe
   errada ([ADR 0003](docs/decisoes/0003-desempate-de-duplicatas.md)).
2. **A detecção ancora no número, não na sigla.** As classes processuais
   aparecem em dezenas de grafias, e o conjunto cego pode trazer outras; o
   número está sempre lá. O span nasce nele e cresce para a esquerda enquanto
   houver prefixo ([ADR 0002](docs/decisoes/0002-ancora-no-numero.md)). O que
   parece número e não é citação (autos do próprio documento, OAB, folhas,
   datas, ano, número solto na prosa) é filtrado por regra explícita, cada uma
   com o caso que a motivou nos testes.
3. **O ruído é desfeito antes da consulta.** A organização garante que um
   dígito nunca vira outro dígito; então toda confusão de OCR (`0↔O`, `1↔l`,
   `5↔S`…) é reversível, e o número com espaço, ponto, quebra de linha ou UF em
   outra forma volta à forma canônica.
4. **A base é lida, não embutida.** O índice guarda só o número **próprio** de
   cada acórdão, tirado do cabeçalho e das zonas que o identificam, e nunca os
   números que ele cita (armadilha 6 de [docs/dados.md](docs/dados.md)).
   Súmulas e dispositivos saem da primeira linha de cada registro. Tudo é
   construído do `.db` recebido, em cada execução.

A confiança é uma constante por caminho de decisão, medida em milhares de
citações do arnês de ruído e do simulador do conjunto sigiloso (checkpoints 07
a 10). Um NER de pesos abertos foi medido e descartado
([ADR 0004](docs/decisoes/0004-ner-de-pesos-abertos.md)).

## Arquitetura

```
.txt ──▶ deteccao ──▶ normalizacao ──▶ base_canonica ──▶ resolucao ──▶ CSV · JSON
        acha spans    ruído → forma     índice da        1 candidato → real
        de citação    canônica          cobertura        0 candidatos → inventada
                                                         ≥2 candidatos → incompleta
```

A classe não precisa ser predita por um classificador: ela é consequência da
cardinalidade da consulta à base canônica fechada.

| Arquivo | Responsabilidade | Estado |
|---|---|---|
| [contrato.py](src/verificador/contrato.py) | schema 1.2 de saída e validador de formato | pronto |
| [texto.py](src/verificador/texto.py) | carrega `.txt` em NFC, offsets em codepoints | pronto |
| [texto.fim_do_cabecalho](src/verificador/texto.py) | separa os metadados (distratores) do corpo | pronto |
| [deteccao.py](src/verificador/deteccao.py) | acha os spans de citação, inclusive as vagas | pronto |
| [normalizacao.py](src/verificador/normalizacao.py) | desfaz ruído de OCR, abreviações, formatação | pronto |
| [base_canonica.py](src/verificador/base_canonica.py) | consulta à base: acórdãos, súmulas e dispositivos, tudo derivado do `.db` | pronto |
| [resolucao.py](src/verificador/resolucao.py) | cardinalidade → classe, `id_canonico` e confiança | pronto |
| [pipeline.py](src/verificador/pipeline.py) · [cli.py](src/verificador/cli.py) | orquestração e CLI | pronto |
| [run.sh](run.sh) | ponto de entrada da avaliação final: `.db` + pasta de `.txt` → CSV | pronto |

O pipeline está completo. Os testes em [tests/](tests/) são a especificação de
cada etapa — 864 deles, todos passando.

**No conjunto de desenvolvimento, pela métrica oficial: F1 macro 1,0000 nos dois
níveis, τ = 0, IoU mínimo 1,000, score 1,1000** (com confiança 1,0 nos caminhos
que o dev exercita; ver o checkpoint 10). Leia esse número com a desconfiança que ele
merece: são os mesmos 26 documentos usados para construir a solução, e
[docs/dados.md](docs/dados.md#riscos-conhecidos-para-o-conjunto-cego) lista o que
essa amostra não consegue medir. A nota oficial, que sai da execução da
organização sobre o conjunto final, é a primeira medida honesta.

**Prazo da entrega: 01/10/2026, 23h59 (Brasília)** — o que enviar está em
[docs/desafio.md](docs/desafio.md#a-entrega-final-e-mail-de-29092026).

Com o F1 saturado, o que ainda se mede aqui é **robustez**, não acerto. Seis
instrumentos existem para isso e são os que importam para o conjunto cego:

- `scripts/simular_sigiloso.py`, que troca as citações do dev por outras da base
  — outros acórdãos, números inventados, relatores, artigos —, nas grafias do
  gabarito, e pontua pela métrica oficial: é o único que mede generalização de
  **conteúdo**, porque o arnês degrada sempre as mesmas 192 citações;

- [tests/test_generalizacao.py](tests/test_generalizacao.py), com as formas que
  a amostra não tem;
- `make robustez`, que degrada o corpus em dez classes de ruído e repontua — as
  três últimas (`ocr_letra_digito`, `sigla_tribunal`, `ocr_curta`) medem formas
  que o nível 2 da amostra mostra e que o arnês antes não gerava;
- `scripts/medir_espurias.py`, que roda a detecção sobre os 996 acórdãos reais
  da base e conta spans por família, para pegar falso positivo em texto que o
  gerador sintético não escreve;
- `scripts/medir_cobertura.py`, que cita cada acórdão pelo próprio cabeçalho e
  mede se ele volta resolvido — o índice visto do lado de quem cita;
- [tests/test_indice.py](tests/test_indice.py), que trava as propriedades da
  construção do índice: nenhuma chave que seja data, ano, OAB ou número citado
  na ementa. São regras sobre a forma do texto dos acórdãos, não sobre estes
  996 registros, e por isso valem para o `.db` novo do conjunto final; os casos
  travados é que são medidos na base do dev.

O conjunto final vem com um `.db` próprio, e isso exige uma medida que os seis
não fazem: rodar o pipeline sobre um banco **alterado** (registro removido, id
trocado) e conferir que a saída acompanha o banco, e não o que ficou no código.
Ver o [checkpoint 11](docs/checkpoints/11-entrega-final.md).

Ver os checkpoints [09](docs/checkpoints/09-revisao-final.md),
[10](docs/checkpoints/10-validacao-final.md) e
[11](docs/checkpoints/11-entrega-final.md), com o que as revisões de 24/09 e
30/09 acharam e mediram.

## Instalação

Para **executar** a avaliação basta o `run.sh` (seção acima): Python ≥ 3.10 ou
Docker, e nada mais. Para **desenvolver**, o projeto usa Python 3.12+ e
[uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Não há dependências de runtime — só biblioteca padrão. `pytest` e `ruff` estão
no grupo `dev`, com `numpy` e `pandas`, que a métrica oficial usa.

## Uso

Salve seu token da API do Kaggle em `~/.kaggle/kaggle.json` (Settings → API →
Create New Token) e rode. **Cada pessoa da equipe baixa com a própria
credencial** — o dataset não pode ser redistribuído.

```bash
make dados      # baixa a competição do Kaggle para data/dev/ (ver docs/dados.md)
make testar     # pytest
make entrega    # roda o run.sh sobre o dev e pontua o CSV pela métrica oficial
make rodar      # um JSON por documento em data/out/
make avaliar    # métrica OFICIAL do Kaggle, por nível + score ponderado
make submissao  # data/submission.csv pelo conversor oficial, a partir de data/out/
make indice     # grava o índice em JSON, para inspeção; a execução o refaz do .db

make baseline   # grava o score limpo como referência do arnês
make robustez   # degrada o corpus por classe de ruído e repontua
make confianca  # mede a acurácia por caminho, para calibrar CONFIANCA
```

Um CSV já gerado, pelo `run.sh` ou por outro caminho, é pontuado direto com
`uv run python scripts/avaliar.py --submissao <csv>`.

`make ajuda` lista todos os alvos. `make solution`,
`uv run python scripts/medir_regiao.py` e `uv run python scripts/medir_espurias.py`
são diagnósticos: o primeiro monta o `solution.csv` da métrica oficial, o
segundo mede a qualidade do índice de números próprios, e o terceiro conta os
spans por família nos acórdãos reais da base — rode antes e depois de mexer em
`deteccao.py` e compare.

Os checkpoints medem o arnês com **5 sementes**; `make robustez` usa 3 por
velocidade. Para comparar com um checkpoint, rode
`uv run python scripts/medir_robustez.py --taxa 0.15 --sementes 5`.

### O container

O uso canônico está em [Execução da avaliação final](#execução-da-avaliação-final):
o container recebe o `.db`, a pasta de `.txt` e o caminho do CSV, como o
`run.sh`. O contrato anterior, com `--input`/`--output` e um JSON por documento,
deixou de ser o da entrega; os JSONs continuam disponíveis pelo quarto argumento
do `run.sh`.

Pesos e dados ficam fora da imagem, como exige o regulamento — a base canônica
entra por volume, e o container roda sem rede. O build não precisa de `uv` no
host: o `requirements.txt` versionado já é o que `make requirements` exporta do
`uv.lock` (`make docker` faz os dois passos). A imagem fixa Python 3.12, a
versão de `.python-version`, e a saída dela é idêntica, byte a byte, à do
`run.sh` local (conferência no
[checkpoint 11](docs/checkpoints/11-entrega-final.md)).

## Por onde continuar

Antes de mexer no código, leia **[docs/dados.md](docs/dados.md)** e
**[docs/investigacao.md](docs/investigacao.md)**. As armadilhas documentadas ali
(`documento_id` ≠ `id_canonico`; o gabarito com BOM; o FTS que devolve quem
*cita* e não quem *é*) custam horas a quem descobre sozinho.

O ponto mais frágil é o que **não** dá para medir aqui: o conjunto cego pode
trazer classes processuais, formas de `incompleta` e ruídos de OCR que a amostra
não tem, e vem com uma base canônica própria. Com o F1 saturado em 1,0, **medir
acerto no dev set não informa mais nada** — o que informa é o arnês, o
simulador, a suíte de generalização e o banco alterado.

Frentes abertas, nessa ordem de valor:

1. **Entregar até 01/10/2026, 23h59.** Conferir a versão final em clone limpo
   (a lista está no [checkpoint 11](docs/checkpoints/11-entrega-final.md)) e
   enviar o hash do commit. A nota sai da execução da organização entre 01/10 e
   10/10; o leaderboard do Kaggle não entra no ranking.
2. **Diploma fora do repertório, citado só pelo nome**, sai `inventada` mesmo
   que o `.db` novo tenha o artigo; e acórdão de tribunal fora dos cinco
   superiores passa pela segmentação genérica. É o risco residual da base nova
   ([ADR 0005](docs/decisoes/0005-base-nova-no-conjunto-cego.md)).
3. **`ocr_curta` a taxa 0,30** é a classe que mais perde (1,0815; ver o cp
   10): palavra curta corrompida fora das âncoras. No simulador, o que resta no
   nível 2 é número de `real` com espaço e OCR juntos.
4. **O número sem nenhum dígito real** (`Rcl BB.gbG/RJ`), resíduo a taxa 0,30.
   Pela forma é indistinguível de palavra; ver o checkpoint 07.
5. **NER de pesos abertos: medido e descartado** — sobre as regras atuais ele
   baixa o score em todos os corpora. A
   [ADR 0004](docs/decisoes/0004-ner-de-pesos-abertos.md) diz quando revisitar.

Regra que vale para qualquer mudança: **o portão é o score limpo, as
propriedades imunes e o volume nos acórdãos reais.** Nada entra se derrubar o
F1 do dev, abrir τ, quebrar uma classe imune no arnês, ou fizer uma família saltar em
`medir_espurias.py` sem explicação. Toda regra nova em `deteccao.py` vem com o
caso que a motivou nos testes.

As decisões de projeto estão em [docs/decisoes/](docs/decisoes/).

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/desafio.md](docs/desafio.md) | regras, cronograma, envelope de execução, a entrega final |
| [docs/dados.md](docs/dados.md) | os 26 documentos, a base canônica, o goldenset, **as armadilhas** |
| [docs/investigacao.md](docs/investigacao.md) | o que medimos nos dados: distribuições, duplicatas, ruído |
| [docs/contrato.md](docs/contrato.md) | formato de entrada e saída: o CSV da entrega, o schema 1.2, encoding, offsets |
| [docs/avaliacao.md](docs/avaliacao.md) | métrica: IoU ≥ 0,5, F1 macro, penalidade dupla, calibração |
| [docs/referencias.md](docs/referencias.md) | literatura que ajuda, e o que dá para usar agora |
| [docs/decisoes/](docs/decisoes/) | registro das decisões de projeto e seus porquês |
| [docs/checkpoints/](docs/checkpoints/) | o que cada etapa mediu, em ordem cronológica |
| [MANIFESTO_MODELO.md](MANIFESTO_MODELO.md) | declaração de pesos usados (hoje: nenhum) |

## Dados

Os dados **não estão neste repositório** e `data/` inteiro está no `.gitignore`.
Foram liberados apenas às equipes inscritas e **não podem ser redistribuídos** —
nada de anexá-los a release, issue, gist ou bucket público. Cada pessoa da
equipe baixa do Kaggle com a própria credencial e confere os SHA-256
publicados; além disso, a base canônica tem 94 MB. Ver
[docs/dados.md](docs/dados.md) para obtenção e checksums.

## Estrutura

```
run.sh               ponto de entrada da avaliação final (.db + pasta de .txt → CSV)
src/verificador/     o pipeline (ver a tabela em "Arquitetura")
scripts/             preparar_dados · baixar_dados · construir_indice · avaliar
                     construir_solution · medir_regiao · medir_robustez · medir_confianca
                     medir_espurias · medir_cobertura · perturbar · simular_sigiloso
tests/               a especificação executável de cada etapa
docs/                desafio · dados · investigacao · contrato · avaliacao · referencias
                     decisoes/ · checkpoints/
Dockerfile           imagem de submissão, sem pesos e sem dados dentro
MANIFESTO_MODELO.md  declaração de pesos usados
data/                gitignored — ver docs/dados.md
```

O conversor oficial `json_to_submission.py` vem da aba *Data* e fica fora do git,
em `data/dev/ferramentas/`. O `run.sh` não depende dele: grava o mesmo CSV por
conta própria.

## Próximos passos

1. **Feito (01/09/2026)** — a organização liberou a competição no Kaggle:
   <https://www.kaggle.com/t/b175ca36f02ce8d3a0422d3f7b339664>. Cada integrante
   entra na competição, e um integrante forma a equipe (até 4 pessoas) na aba
   *Team*. Ver [docs/desafio.md § A competição no Kaggle](docs/desafio.md#a-competição-no-kaggle).
2. **Feito (15/09/2026)** — dados da distribuição de 15/09 em `data/dev/`. Ela
   mudou a base canônica, os 26 `.txt` e o gabarito (192 citações); ver
   [docs/dados.md § Atualização final](docs/dados.md#atualização-final-15092026).
   O script oficial da métrica está em `data/dev/ferramentas/kaggle_metric.py`.
3. **Feito (15/09/2026)** — `make avaliar` usa a métrica oficial, carregada de
   `data/dev/ferramentas/`. Ver [docs/avaliacao.md](docs/avaliacao.md), que
   documenta as três regras onde a nossa leitura anterior divergia.
4. **Feito (15/09/2026)** — pipeline completo, com os 47 testes da linha de
   base (checkpoint 00). A suíte chegou a 591 em 30/09.
5. **Encerrado (30/09/2026)** — o período de submissões ao Kaggle
   (`make submissao`). O leaderboard rodou sobre a amostra de desenvolvimento,
   de gabarito aberto, e serviu para validar o pipeline de ponta a ponta; ele
   **não entra no ranking final**.
6. **Feito (29/09/2026)** — o e-mail da organização mudou a entrega: a nota
   oficial sai da execução deste repositório sobre um `.db` novo e documentos
   novos, e não de um CSV enviado. Ver
   [docs/desafio.md](docs/desafio.md#a-entrega-final-e-mail-de-29092026).
7. **Feito (30/09/2026)** — ponto de entrada único (`run.sh`), súmulas e
   dispositivos derivados do `.db`, repertório de diplomas federais e leitura
   robusta do banco. Ver o [checkpoint 11](docs/checkpoints/11-entrega-final.md)
   e a [ADR 0005](docs/decisoes/0005-base-nova-no-conjunto-cego.md).
8. **Até 01/10/2026, 23h59 (Brasília)** — enviar a desafio-bracis@jusbrasil.com.br
   o nome da equipe e dos integrantes, o link do repositório (público, ou
   privado com leitura para os cinco usuários listados em
   [docs/desafio.md](docs/desafio.md#a-entrega-final-e-mail-de-29092026)) e o
   **hash do commit da versão final**.
   (pendente: hash do commit final e data do envio)
9. **01 a 10/10/2026** — a organização executa o código no conjunto final,
   verifica a reprodutibilidade e divulga o ranking. As melhores soluções são
   apresentadas no BRACIS 2026, de 19 a 22/10, em Cuiabá-MT.
