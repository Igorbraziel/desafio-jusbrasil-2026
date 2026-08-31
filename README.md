# Verificador de Citações Jurídicas — Desafio Jusbrasil x BRACIS 2026

Sistema que lê um parecer jurídico em `.txt`, encontra todas as citações de jurisprudência e de
lei, e classifica cada uma em três classes:

| Classe | Quando | `resolucao` |
|---|---|---|
| `real` | resolve a **exatamente um** registro da base canônica | `id_canonico` obrigatório |
| `inventada` | identificadores suficientes para buscar, **nenhum** registro corresponde | `null` |
| `incompleta` | informação insuficiente para consultar, ou **dois ou mais** candidatos sem desempate | `null` |

A distinção entre `inventada` e `incompleta` é o ponto da tarefa: a inventada é alucinação ativa
de um LLM e deve ser bloqueada; a incompleta é evasiva e vai para revisão humana.

## Como funciona

A baseline é **determinística e sem pesos de modelo**. A classe não é predita por um classificador
— é uma consequência da cardinalidade da consulta à base canônica:

```
.txt ──▶ deteccao ──▶ normalizacao ──▶ base_canonica ──▶ resolucao ──▶ JSON
        acha spans    ruído → forma     índice dos       1 candidato → real
        de citação    canônica          cabeçalhos       0 candidatos → inventada
                                                         ≥2 candidatos → incompleta
```

Módulos em [src/verificador/](src/verificador/):

| Arquivo | Responsabilidade |
|---|---|
| [texto.py](src/verificador/texto.py) | carrega `.txt` em NFC; offsets em codepoints Unicode |
| [deteccao.py](src/verificador/deteccao.py) | acha os spans de citação, inclusive as vagas |
| [normalizacao.py](src/verificador/normalizacao.py) | desfaz ruído de OCR, abreviações, formatação de número |
| [base_canonica.py](src/verificador/base_canonica.py) | índice dos cabeçalhos + súmulas e dispositivos |
| [resolucao.py](src/verificador/resolucao.py) | cardinalidade → classe, e a confiança |
| [contrato.py](src/verificador/contrato.py) | schema 1.2 de saída e validador de formato |
| [pipeline.py](src/verificador/pipeline.py) · [cli.py](src/verificador/cli.py) | orquestração e CLI |

## Instalação

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Não há dependências de runtime — só biblioteca padrão. `pytest` e `ruff` estão no grupo `dev`.

## Uso

Coloque o zip recebido por e-mail em `data/raw/dados_desafio_jusbrasil.zip` e rode:

```bash
make dados      # extrai, confere SHA-256, gera data/dev/goldenset.csv (ids inteiros)
make indice     # constrói o índice de números próprios — uma vez, offline (0,5 s)
make testar     # pytest
make rodar      # um JSON por documento em data/out/
make avaliar    # F1 macro por nível + score ponderado
make submissao  # empacota data/out/ em data/submissao.zip
```

`make ajuda` lista todos os alvos.

### No contrato de execução da organização

```bash
make docker

docker run --rm --network none \
  -v $PWD/data/dev/txt:/data/in:ro \
  -v $PWD/data/out:/data/out \
  -v $PWD/data/dev/desafio1_bracis.db:/data/base/desafio1_bracis.db:ro \
  verificador-citacoes:latest --input /data/in --output /data/out
```

Verificado: roda com `--network none` e produz saída byte a byte idêntica à
execução local. Pesos e dados ficam fora da imagem, como exige o regulamento — a
base canônica entra por volume.

## Resultados

Nos 26 documentos de desenvolvimento (`make rodar && make avaliar`):

| Nível | F1 macro | Brier | `inventada`→`real` |
|---|---|---|---|
| 1 (peso 1×) | 1,0000 | 0,0071 | 0 |
| 2 (peso 2×) | 1,0000 | 0,0077 | 0 |

225 de 225 citações detectadas e classificadas corretamente, incluindo todos os
`id_canonico`. Custo: **~9 ms por documento** em CPU, contra um teto de 60 s.

> **Leia este número com desconfiança.** É o score sobre a mesma amostra em que a
> solução foi construída — várias decisões do pipeline foram tomadas olhando para
> os erros nela. O que provavelmente não generaliza está listado em
> [docs/dados.md § Onde isto provavelmente cai](docs/dados.md#onde-isto-provavelmente-cai).

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/desafio.md](docs/desafio.md) | regras, cronograma, envelope de execução, o que é permitido |
| [docs/dados.md](docs/dados.md) | os 26 documentos, a base canônica, o goldenset, **as armadilhas** |
| [docs/contrato.md](docs/contrato.md) | formato de entrada e saída, schema 1.2, encoding, offsets |
| [docs/avaliacao.md](docs/avaliacao.md) | métrica: IoU ≥ 0,5, F1 macro, penalidade dupla, calibração |
| [docs/decisoes/](docs/decisoes/) | registro das decisões de projeto e seus porquês |
| [MANIFESTO_MODELO.md](MANIFESTO_MODELO.md) | declaração de pesos usados (hoje: nenhum) |

Se você vai mexer no código, leia **[docs/dados.md](docs/dados.md)** antes — as armadilhas
documentadas ali (`documento_id` ≠ `id_canonico`, o FTS que não casa número sem pontuação, o
`id_canonico` gravado como float no xlsx) custam horas a quem descobre sozinho.

## Dados

Os dados **não estão neste repositório** e `data/` inteiro está no `.gitignore`. Foram enviados por
e-mail apenas às equipes inscritas e não têm download público; além disso, a base canônica tem
93 MB. Ver [docs/dados.md](docs/dados.md) para obtenção e checksums.

## Estado

Baseline determinística funcionando ponta a ponta. O script oficial de avaliação da organização
sai em 01/09/2026 — até lá, [scripts/avaliar.py](scripts/avaliar.py) é a nossa leitura da métrica
descrita no PDF, e deve ser substituído assim que o oficial chegar.
