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

## Execução na avaliação final

Ponto de entrada único: recebe o banco e a pasta de `.txt` e escreve o CSV no
formato da submissão (`documento_id,citacoes`).

```bash
bash run.sh <caminho_db> <pasta_txt> <arquivo_saida.csv>
```

Só usa a biblioteca padrão do Python (3.10 ou mais novo; medido em 3.12). Não
precisa de rede, GPU nem pesos de modelo, e o resultado é determinístico. O
mesmo comando no ambiente declarado (Docker):

```bash
docker build -t verificador-citacoes .
docker run --rm --network none \
  -v /caminho/base.db:/in/base.db:ro \
  -v /caminho/txt:/in/txt:ro \
  -v /caminho/saida:/out \
  verificador-citacoes /in/base.db /in/txt /out/submission.csv
```

**Toda a cobertura sai do banco recebido, a cada execução.** O índice dos
números próprios dos acórdãos é montado com o parser estrutural de cada
tribunal, e as tabelas de súmulas e dispositivos, da primeira linha de cada
registro. Esse é o "enriquecimento da base": é código do repositório, roda
sobre qualquer `.db` no formato original e leva cerca de um segundo. Nada
depende do banco de desenvolvimento.

## Arquitetura

```
.txt ──▶ deteccao ──▶ normalizacao ──▶ base_canonica ──▶ resolucao ──▶ JSON
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
| [base_canonica.py](src/verificador/base_canonica.py) | consulta à cobertura; tabelas de súmulas e leis | pronto |
| [resolucao.py](src/verificador/resolucao.py) | cardinalidade → classe, `id_canonico` e confiança | pronto |
| [pipeline.py](src/verificador/pipeline.py) · [cli.py](src/verificador/cli.py) | orquestração e CLI no contrato exigido | pronto |

O pipeline está completo. Os testes em [tests/](tests/) são a especificação de
cada etapa — 626 deles, todos passando.

**No conjunto de desenvolvimento, pela métrica oficial: F1 macro 1,0000 nos dois
níveis, τ = 0, IoU mínimo 1,000, score 1,1000** (com confiança 1,0 nos caminhos
que o dev exercita; ver o checkpoint 10). Leia esse número com a desconfiança que ele
merece: são os mesmos 26 documentos usados para construir a solução, e
[docs/dados.md](docs/dados.md#riscos-conhecidos-para-o-conjunto-cego) lista o que
essa amostra não consegue medir. O leaderboard sobre o conjunto final é a
primeira medida honesta.

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
- [tests/test_indice.py](tests/test_indice.py), que trava as propriedades do
  índice que valem também no conjunto cego, porque a base é a mesma: nenhuma
  chave que seja data, ano, OAB ou número citado na ementa.

Ver os checkpoints [09](docs/checkpoints/09-revisao-final.md),
[10](docs/checkpoints/10-validacao-final.md) e
[11](docs/checkpoints/11-banco-novo.md), com o que as revisões de 24/09 e 30/09
acharam e mediram.

## Instalação

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Não há dependências de runtime — só biblioteca padrão. `pytest` e `ruff` estão
no grupo `dev`.

## Uso

Salve seu token da API do Kaggle em `~/.kaggle/kaggle.json` (Settings → API →
Create New Token) e rode. **Cada pessoa da equipe baixa com a própria
credencial** — o dataset não pode ser redistribuído.

```bash
make dados      # baixa a competição do Kaggle para data/dev/ (ver docs/dados.md)
make indice     # constrói o índice da base canônica — uma vez, offline
make testar     # pytest
make rodar      # um JSON por documento em data/out/
make avaliar    # métrica OFICIAL do Kaggle, por nível + score ponderado
make submissao  # gera e confere data/submission.csv para enviar no Kaggle

make baseline   # grava o score limpo como referência do arnês
make robustez   # degrada o corpus por classe de ruído e repontua
make confianca  # mede a acurácia por caminho, para calibrar CONFIANCA
```

`make ajuda` lista todos os alvos. `make solution`,
`uv run python scripts/medir_regiao.py` e `uv run python scripts/medir_espurias.py`
são diagnósticos: o primeiro monta o `solution.csv` da métrica oficial, o
segundo mede a qualidade do índice de números próprios, e o terceiro conta os
spans por família nos acórdãos reais da base — rode antes e depois de mexer em
`deteccao.py` e compare.

Os checkpoints medem o arnês com **5 sementes**; `make robustez` usa 3 por
velocidade. Para comparar com um checkpoint, rode
`uv run python scripts/medir_robustez.py --taxa 0.15 --sementes 5`.

### No contrato de execução da organização

Ver [Execução na avaliação final](#execução-na-avaliação-final). Com os dados
de desenvolvimento:

```bash
bash run.sh data/dev/desafio1_bracis.db data/dev/txt data/submission.csv
```

Pesos e dados ficam fora da imagem, como exige o regulamento — a base canônica
entra por volume, e o container roda sem rede. O build não precisa de `uv` no
host: o `requirements.txt` versionado já é o que `make requirements` exporta do
`uv.lock` (`make docker` faz os dois passos). O CSV do container é idêntico,
byte a byte, ao de `bash run.sh` em Python 3.12, a versão fixada em
`.python-version` e na imagem.

## Por onde continuar

Antes de mexer no código, leia **[docs/dados.md](docs/dados.md)** e
**[docs/investigacao.md](docs/investigacao.md)**. As armadilhas documentadas ali
(`documento_id` ≠ `id_canonico`; o gabarito com BOM; o FTS que devolve quem
*cita* e não quem *é*) custam horas a quem descobre sozinho.

O ponto mais frágil é o que **não** dá para medir aqui: o conjunto cego pode
trazer classes processuais, formas de `incompleta` e ruídos de OCR que a amostra
não tem. Com o F1 saturado em 1,0, **medir acerto no dev set não informa mais
nada** — o que informa é o arnês e a suíte de generalização.

Frentes abertas, nessa ordem de valor:

1. **Submeter e ler o leaderboard do conjunto final.** `make submissao` gera e
   confere o CSV; o que falta saber só o conjunto cego diz.
2. **`ocr_curta` a taxa 0,30** é a classe que mais perde (1,0815; ver o cp
   10): palavra curta corrompida fora das âncoras. No simulador, o que resta no
   nível 2 é número de `real` com espaço e OCR juntos.
3. **O número sem nenhum dígito real** (`Rcl BB.gbG/RJ`), resíduo a taxa 0,30.
   Pela forma é indistinguível de palavra; ver o checkpoint 07.
4. **NER de pesos abertos: medido e descartado** — sobre as regras atuais ele
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
| [docs/desafio.md](docs/desafio.md) | regras, cronograma, envelope de execução, o que é permitido |
| [docs/dados.md](docs/dados.md) | os 26 documentos, a base canônica, o goldenset, **as armadilhas** |
| [docs/investigacao.md](docs/investigacao.md) | o que medimos nos dados: distribuições, duplicatas, ruído |
| [docs/contrato.md](docs/contrato.md) | formato de entrada e saída, schema 1.2, encoding, offsets |
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
src/verificador/     o pipeline (ver a tabela em "Arquitetura")
scripts/             preparar_dados · baixar_dados · construir_indice · avaliar
                     construir_solution · medir_regiao · medir_robustez · medir_confianca
                     medir_espurias · medir_cobertura · perturbar · simular_sigiloso
tests/               a especificação executável de cada etapa
docs/                desafio · dados · investigacao · contrato · avaliacao · referencias · decisoes/
Dockerfile           imagem de submissão, sem pesos e sem dados dentro
MANIFESTO_MODELO.md  declaração de pesos usados
data/                gitignored — ver docs/dados.md
```

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
4. **Feito (15/09/2026)** — pipeline completo, 47 testes passando.
5. Gerar `submission.csv` com `make submissao` e submeter cedo e com
   frequência — o leaderboard do Kaggle nesta fase roda sobre a amostra de
   desenvolvimento (gabarito aberto) e é referencial, para validar o pipeline
   de ponta a ponta; o limite é 5 submissões/dia por **equipe**.
