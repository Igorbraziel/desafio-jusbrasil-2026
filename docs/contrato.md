# Contrato de entrada e saída

## Entrada

Um arquivo `.txt` por parecer. O nome do arquivo sem extensão é o
`documento_id`.

**Encoding (regra rígida):** UTF-8 sem BOM, quebra de linha LF, Unicode NFC. Os
arquivos são distribuídos já normalizados — **não os altere**.

**Offsets:** posições em **codepoints Unicode** a partir de 0, com fim
**exclusivo** (`texto[inicio:fim]`). São a base do alinhamento entre predição e
gabarito. Em Python, indexar uma `str` já opera em codepoints — o cuidado é não
passar por `bytes` no meio do caminho.

## Saída

Um JSON por parecer, com o mesmo nome-base.

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

Na entrega final o JSON completo é obrigatório, com **todos** os campos —
inclusive `trecho` e `tipo`, que não entram na métrica.

Não existe validador separado: as checagens de formato são feitas pelo próprio
script de avaliação. O conversor `json_to_submission.py`, fornecido pela
organização, agrupa os JSONs em `submission.csv`.

Neste repositório, [`contrato.py`](../src/verificador/contrato.py) implementa a
serialização e um validador local — `validar(saida, texto)` também confere que
`trecho == texto[inicio:fim]`.

## Os dois pontos que estavam em aberto — resolvidos

**1. `id_canonico`: string ou inteiro? — Resolvido: string de dígitos.** O que
pontua é o `submission.csv`, não o JSON. O conversor oficial
`json_to_submission.py` faz `str(resolucao["id_canonico"])` e escreve `-` quando
ausente; o `kaggle_metric.py` exige `id_canonico.isdigit()` em toda citação
`real` e normaliza os dois lados com `lstrip("0")` antes de comparar. Emitir
string de dígitos no JSON, como [`contrato.py`](../src/verificador/contrato.py)
já faz, atravessa os dois sem conversão. Emitir inteiro também funcionaria — o
conversor faz `str()` de qualquer jeito —, mas não há motivo para mudar.

> O JSON continua sendo o formato de trabalho e o exigido na entrega final, com
> todos os campos. O CSV é só o transporte do Kaggle.

**2. `id_canonico` passou a ser um único `doc_id`.** Até 28/08/2026 o campo era
um conjunto de candidatos, para acomodar duplicatas na base. Com `doc_0227` e
`doc_0461` removidos, cada citação real resolve para exatamente um registro, e o
gabarito já está assim — as 96 citações `real` têm um id cada.
