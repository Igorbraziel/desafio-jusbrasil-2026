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
cada etapa — 529 deles, todos passando.

**No conjunto de desenvolvimento, pela métrica oficial: F1 macro 1,0000 nos dois
níveis, τ = 0, score 1,1000.** Leia esse número com a desconfiança que ele
merece: são os mesmos 26 documentos usados para construir a solução, e
[docs/dados.md](docs/dados.md#riscos-conhecidos-para-o-conjunto-cego) lista o que
essa amostra não consegue medir. O leaderboard sobre o conjunto final é a
primeira medida honesta.

Com o F1 saturado, o que ainda se mede aqui é **robustez**, não acerto. Cinco
instrumentos existem para isso e são os que importam para o conjunto cego:

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

Ver o [checkpoint 09](docs/checkpoints/09-revisao-final.md), com o que a revisão
de 24/09 achou e mediu.

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

```bash
make docker

docker run --rm --network none \
  -v $PWD/data/dev/txt:/data/in:ro \
  -v $PWD/data/out:/data/out \
  -v $PWD/data/dev/desafio1_bracis.db:/data/base/desafio1_bracis.db:ro \
  verificador-citacoes:latest --input /data/in --output /data/out
```

Pesos e dados ficam fora da imagem, como exige o regulamento — a base canônica
entra por volume, e o container roda sem rede.

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
2. **`ocr_letra_digito` a taxa 0,30** é a classe que mais perde (ver o cp 09):
   letra trocada por dígito em palavra que não é âncora.
3. **O número sem nenhum dígito real** (`Rcl BB.gbG/RJ`), resíduo a taxa 0,30.
   Pela forma é indistinguível de palavra; ver o checkpoint 07.
4. **NER de pesos abertos: medido e descartado** — sobre as regras atuais ele
   baixa o score em todos os corpora. A
   [ADR 0004](docs/decisoes/0004-ner-de-pesos-abertos.md) diz quando revisitar.

Regra que vale para qualquer mudança: **o portão é o score limpo, as
propriedades imunes e o volume nos acórdãos reais.** Nada entra se derrubar
1,1000, quebrar uma classe imune no arnês, ou fizer uma família saltar em
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
                     medir_espurias · perturbar
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
