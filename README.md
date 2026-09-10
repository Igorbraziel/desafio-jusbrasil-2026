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
| [texto.fim_do_cabecalho](src/verificador/texto.py) | separa os metadados (distratores) do corpo | **a implementar** |
| [deteccao.py](src/verificador/deteccao.py) | acha os spans de citação, inclusive as vagas | **a implementar** |
| [normalizacao.py](src/verificador/normalizacao.py) | desfaz ruído de OCR, abreviações, formatação | **a implementar** |
| [base_canonica.py](src/verificador/base_canonica.py) | consulta à cobertura; tabelas de súmulas e leis | parcial |
| [resolucao.py](src/verificador/resolucao.py) | cardinalidade → classe, `id_canonico` e confiança | **a implementar** |
| [pipeline.py](src/verificador/pipeline.py) · [cli.py](src/verificador/cli.py) | orquestração e CLI no contrato exigido | pronto |

Os stubs trazem a assinatura, a documentação da etapa e as armadilhas
conhecidas. Os testes em [tests/](tests/) são a especificação: estão marcados
como falha esperada (`xfail`) e passam a valer conforme cada etapa é
implementada.

## Instalação

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Não há dependências de runtime — só biblioteca padrão. `pytest` e `ruff` estão
no grupo `dev`.

## Uso

Salve seu token da API do Kaggle em `~/.kaggle/kaggle.json` (Settings → API →
Create New Token) e rode:

```bash
make dados-kaggle  # baixa a competição do Kaggle para data/dev/ (ver docs/dados.md)
make indice     # constrói o índice da base canônica — uma vez, offline
make testar     # pytest
make rodar      # um JSON por documento em data/out/
make avaliar    # F1 macro por nível + score ponderado
make submissao  # empacota data/out/ em data/submissao.zip
```

`make ajuda` lista todos os alvos. Enquanto o pipeline estiver incompleto,
`make indice` e `make rodar` falham com `NotImplementedError` — é o esperado.

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

## Por onde começar

Antes de escrever código, leia **[docs/dados.md](docs/dados.md)** e
**[docs/investigacao.md](docs/investigacao.md)**. As armadilhas documentadas ali
(`documento_id` ≠ `id_canonico`; o FTS que não casa número sem pontuação; o FTS
que devolve quem *cita* e não quem *é*; o `id_canonico` gravado como float no
xlsx) custam horas a quem descobre sozinho.

Uma ordem de ataque que respeita as dependências:

1. **`normalizacao.py`** — não depende de nada e é o que mais pesa na nota, já
   que o nível 2 vale o dobro. `uv run pytest tests/test_normalizacao.py` é a
   especificação.
2. **`base_canonica.regiao_de_identificacao`** — define o que conta como número
   próprio de um acórdão. Depois, `make indice`.
3. **`texto.fim_do_cabecalho`** e **`deteccao.py`** — os spans. Sem eles não há o
   que classificar, e citação não detectada conta como erro de recall.
4. **`resolucao.py`** — com as três anteriores prontas, é quase só a regra de
   cardinalidade.
5. `make rodar && make avaliar` para ver o primeiro número.

Registre as decisões de projeto em [docs/decisoes/](docs/decisoes/) conforme
forem tomadas — o modelo está lá.

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/desafio.md](docs/desafio.md) | regras, cronograma, envelope de execução, o que é permitido |
| [docs/dados.md](docs/dados.md) | os 26 documentos, a base canônica, o goldenset, **as armadilhas** |
| [docs/investigacao.md](docs/investigacao.md) | o que medimos nos dados: distribuições, duplicatas, ruído |
| [docs/contrato.md](docs/contrato.md) | formato de entrada e saída, schema 1.2, encoding, offsets |
| [docs/avaliacao.md](docs/avaliacao.md) | métrica: IoU ≥ 0,5, F1 macro, penalidade dupla, calibração |
| [docs/decisoes/](docs/decisoes/) | registro das decisões de projeto e seus porquês |
| [MANIFESTO_MODELO.md](MANIFESTO_MODELO.md) | declaração de pesos usados (hoje: nenhum) |

## Dados

Os dados **não estão neste repositório** e `data/` inteiro está no `.gitignore`.
Foram enviados por e-mail apenas às equipes inscritas e não têm download
público; além disso, a base canônica tem 93 MB. Ver
[docs/dados.md](docs/dados.md) para obtenção e checksums.

## Estrutura

```
src/verificador/     o pipeline (ver a tabela em "Arquitetura")
scripts/             preparar_dados · construir_indice · avaliar
tests/               a especificação executável de cada etapa
docs/                desafio · dados · investigacao · contrato · avaliacao · decisoes/
Dockerfile           imagem de submissão, sem pesos e sem dados dentro
MANIFESTO_MODELO.md  declaração de pesos usados
data/                gitignored — ver docs/dados.md
```

## Próximos passos

1. **Feito (01/09/2026)** — a organização liberou a competição no Kaggle:
   <https://www.kaggle.com/t/b175ca36f02ce8d3a0422d3f7b339664>. Cada integrante
   entra na competição, e um integrante forma a equipe (até 4 pessoas) na aba
   *Team*. Ver [docs/desafio.md § A competição no Kaggle](docs/desafio.md#a-competição-no-kaggle).
2. Baixar da aba *Data* do Kaggle: o goldenset atualizado (o critério de
   `incompleta` mudou — ver
   [docs/dados.md § Atualização do goldenset](docs/dados.md#atualização-do-goldenset-01092026)),
   o conversor `json_to_submission.py` e o script oficial da métrica.
   Substituir [scripts/avaliar.py](scripts/avaliar.py) pelo oficial e comparar
   os dois: divergência indica que interpretamos alguma regra errado. Conferir
   também se `id_canonico` sai como string ou inteiro
   ([docs/contrato.md](docs/contrato.md)).
3. Implementar o pipeline na ordem sugerida em *Por onde começar*.
4. Gerar `submission.csv` com `json_to_submission.py` e submeter cedo e com
   frequência — o leaderboard do Kaggle nesta fase roda sobre a amostra de
   desenvolvimento (gabarito aberto) e é referencial, para validar o pipeline
   de ponta a ponta; o limite é 5 submissões/dia por **equipe**.
