"""A saída no formato da submissão: um CSV com uma linha por documento.

A avaliação final pede um ponto de entrada que receba o banco e a pasta de
`.txt` e gere a saída "no mesmo formato usado nas submissões" — o CSV que o
`json_to_submission.py` da organização monta a partir dos JSONs do contrato:

    documento_id,citacoes
    gen_001,"1284,1302,real,2106313729,1.0000|3401,3445,incompleta,-,1.0000"
    gen_002,-

O conversor da organização fica em `data/`, fora do repositório, então a mesma
codificação é reproduzida aqui; `tests/test_submissao.py` confere, byte a byte,
que as duas saídas são iguais.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def codificar(documento: dict) -> str:
    """A célula `citacoes`: `inicio,fim,classe,id_canonico,confianca` separadas por `|`.

    `id_canonico` ausente vira "-", a confiança sai com quatro casas, e o
    documento sem citação vira "-" (o Kaggle rejeita a célula vazia).
    """
    partes = []
    for citacao in documento.get("citacoes", []):
        resolucao = citacao.get("resolucao") or {}
        id_canonico = str(resolucao.get("id_canonico", "") or "").strip() or "-"
        confianca = citacao.get("confianca")
        confianca_s = "-" if confianca is None else f"{float(confianca):.4f}"
        partes.append(
            f"{int(citacao['inicio'])},{int(citacao['fim'])},{citacao['classificacao']},"
            f"{id_canonico},{confianca_s}"
        )
    return "|".join(partes) if partes else "-"


def escrever_csv(jsons: list[Path], destino: Path) -> int:
    """Escreve o CSV a partir dos JSONs, na ordem dos nomes de arquivo. Devolve as linhas."""
    linhas = []
    for caminho in sorted(jsons):
        documento = json.loads(caminho.read_text(encoding="utf-8"))
        linhas.append((documento.get("documento_id") or caminho.stem, codificar(documento)))
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["documento_id", "citacoes"])
        escritor.writerows(linhas)
    return len(linhas)
