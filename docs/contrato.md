# Contrato de entrada e saída

Na entrega final (e-mail de 29/09/2026; ver
[desafio.md](desafio.md#a-entrega-final-e-mail-de-29092026)), o contrato é o do
ponto de entrada único:

```bash
bash run.sh <caminho_db> <pasta_txt> <arquivo_saida> [pasta_json]
```

Entram a base canônica em `.db` e a pasta com os `.txt`; sai o **CSV no formato
das submissões**, que é o que o avaliador oficial pontua. O JSON do schema 1.2
continua definido e sai na `pasta_json`, quando ela é dada.

## Entrada

**A base canônica:** um SQLite no formato da amostra de desenvolvimento, com a
tabela `documentos` descrita em [dados.md](dados.md#a-base-canônica). Na
avaliação final é um `.db` novo, que a organização monta no momento da
execução. Ele é só lido; tudo o que o pipeline precisa sai dele em memória.

**Os documentos:** um arquivo `.txt` por parecer. O nome do arquivo sem
extensão é o `documento_id`.

**Encoding (regra rígida):** UTF-8 sem BOM, quebra de linha LF, Unicode NFC. Os
arquivos são distribuídos já normalizados — **não os altere**.

**Offsets:** posições em **codepoints Unicode** a partir de 0, com fim
**exclusivo** (`texto[inicio:fim]`). São a base do alinhamento entre predição e
gabarito. Em Python, indexar uma `str` já opera em codepoints — o cuidado é não
passar por `bytes` no meio do caminho.

## Saída da entrega: o CSV de submissão

Um arquivo só, com uma linha por documento:

```
documento_id,citacoes
doc_0042,"1284,1302,real,2106313729,0.9100|3401,3445,incompleta,-,0.8000"
doc_sem_citacao,-
```

(A primeira linha é o exemplo de JSON mais abaixo, convertido.)

| Regra | Valor |
|---|---|
| cabeçalho | `documento_id,citacoes` |
| linhas | uma por `.txt` da pasta de entrada, em ordem de nome |
| célula `citacoes` | blocos `inicio,fim,classificacao,id_canonico,confianca` separados por `\|` |
| `id_canonico` | string de dígitos quando `real`; `-` nas demais classes |
| `confianca` | quatro casas decimais (`1.0000`); `-` se ausente |
| documento sem citação | `-` na célula — célula vazia faz o avaliador rejeitar a submissão |
| aspas e quebra de linha | as do módulo `csv` do Python: a célula com vírgula vai entre aspas, e as linhas terminam em CRLF |

É **byte a byte** o CSV que o conversor oficial `json_to_submission.py` gera a
partir dos JSONs abaixo. O `run.sh` não depende do conversor, que vem da aba
*Data* e fica fora do git: grava o mesmo arquivo por conta própria e, antes de
terminar, confere o resultado com as checagens que o avaliador oficial aplica
(ver [avaliacao.md](avaliacao.md#erros-que-invalidam-a-submissão-inteira)).

Um documento que falha ou estoura o tempo máximo sai com `-`, e o lote segue:
documento sem linha faria o avaliador rejeitar a submissão inteira.

## O JSON do contrato (schema 1.2)

Disponível com o quarto argumento do `run.sh` (ou pela CLI, `python -m
verificador.cli --input <pasta_txt> --output <pasta_json> --db <caminho_db>`):
um JSON por parecer, com o mesmo nome-base. É o formato de trabalho do pipeline
e a origem do CSV; traz também `trecho` e `tipo`, que o CSV não carrega.

```json
{
  "schema_version": "1.2",
  "documento_id": "doc_0042",
  "citacoes": [
    {
      "id": "c1",
      "inicio": 1284,
      "fim": 1302,
      "trecho": "REsp 1.234.567/SP",
      "tipo": "jurisprudencia",
      "classificacao": "real",
      "resolucao": { "fonte": "jusbrasil", "id_canonico": "2106313729" },
      "confianca": 0.91
    },
    {
      "id": "c2",
      "inicio": 3401,
      "fim": 3445,
      "trecho": "jurisprudência pacífica do tribunal",
      "tipo": "jurisprudencia",
      "classificacao": "incompleta",
      "resolucao": null,
      "confianca": 0.80
    }
  ]
}
```

| Campo | Regra |
|---|---|
| `schema_version` | `"1.2"` |
| `documento_id` | nome do `.txt` sem extensão |
| `id` | identificador da citação dentro do documento (`c1`, `c2`, …) |
| `inicio`, `fim` | codepoints Unicode, fim exclusivo |
| `trecho` | cópia literal de `texto[inicio:fim]` |
| `tipo` | `jurisprudencia` ou `lei` |
| `classificacao` | `real`, `inventada` ou `incompleta` |
| `resolucao` | `{"fonte", "id_canonico"}` quando `real`; `null` nas demais |
| `confianca` | opcional, em [0, 1]; alimenta o bônus de calibração |

Pelas regras originais, o JSON completo, com **todos** os campos, seria a
entrega final. O e-mail de 29/09 trocou isso pela saída no formato das
submissões, que é o CSV acima. O JSON continua sendo gerado com todos os
campos, inclusive `trecho` e `tipo`, que não entram na métrica.

Não existe validador separado: as checagens de formato são feitas pelo próprio
script de avaliação. O conversor `json_to_submission.py`, fornecido pela
organização, agrupa os JSONs em `submission.csv`.

Neste repositório, [`contrato.py`](../src/verificador/contrato.py) implementa a
serialização e um validador local — `validar(saida, texto)` também confere que
`trecho == texto[inicio:fim]`.
<!-- PREENCHER: citar o módulo que grava o CSV no run.sh (nome definido pelo agente A) -->

## Execução

`run.sh` usa o Python ≥ 3.10 que houver na máquina, ou o de `$PYTHON`; sem
Python, ou com `VERIFICADOR_DOCKER=1`, roda pela imagem Docker. Se o `.db` não
existir, para com erro, em vez de cair num índice antigo. O passo a passo, com o
uso canônico via Docker, está no [README](../README.md#execução-da-avaliação-final).

## Os dois pontos que estavam em aberto — resolvidos

**1. `id_canonico`: string ou inteiro? — Resolvido: string de dígitos.** O que
pontua é o `submission.csv`, não o JSON. O conversor oficial
`json_to_submission.py` faz `str(resolucao["id_canonico"])` e escreve `-` quando
ausente; o `kaggle_metric.py` exige `id_canonico.isdigit()` em toda citação
`real` e normaliza os dois lados com `lstrip("0")` antes de comparar. Emitir
string de dígitos no JSON, como [`contrato.py`](../src/verificador/contrato.py)
já faz, atravessa os dois sem conversão. Emitir inteiro também funcionaria — o
conversor faz `str()` de qualquer jeito —, mas não há motivo para mudar.

> O JSON continua sendo o formato de trabalho do pipeline, com todos os campos.
> O que a organização executa e pontua, desde 29/09, é o CSV que o `run.sh`
> grava; o id sai nele como string de dígitos, igual ao do JSON.

**2. `id_canonico` passou a ser um único `doc_id`.** Até 28/08/2026 o campo era
um conjunto de candidatos, para acomodar duplicatas na base. Com `doc_0227` e
`doc_0461` removidos, cada citação real resolve para exatamente um registro, e o
gabarito já está assim — as 96 citações `real` têm um id cada.
