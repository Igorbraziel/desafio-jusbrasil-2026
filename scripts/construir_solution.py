"""Converte o goldenset no `solution.csv` que a métrica oficial espera.

O `kaggle_metric.py` da organização não lê o goldenset linha a linha: ele espera
o formato de transporte do Kaggle, com **uma linha por documento** e as citações
empacotadas numa célula só::

    documento_id, nivel, citacoes
    <documento>, <nivel>, "<inicio>,<fim>,<classe>,<doc_ids>|..."

Cada bloco é ``inicio,fim,classe,doc_ids``, separados por ``|``. ``doc_ids`` é o
conjunto de ids aceitos, separados por ``:`` — o gabarito distribuído traz um id
só por citação, mas o parser oficial aceita vários, e é por isso que um par de
duplicatas na base pode não custar nada (ver docs/investigacao.md).

Duas pré-condições do parser oficial, conferidas aqui em vez de estourar lá
dentro com uma mensagem críptica:

* citações do mesmo documento **não podem se sobrepor** — o alinhamento guloso
  da métrica só é ótimo com os spans do gabarito disjuntos;
* toda citação ``real`` precisa de ``id_canonico``.

Uso:
    python scripts/construir_solution.py --goldenset data/dev/goldenset.csv \
        --saida data/dev/solution.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

COLUNAS = ["documento_id", "nivel", "citacoes"]

# Ausência de id, no formato do Kaggle, é "-" e não célula vazia.
VAZIO = "-"


def _ler_goldenset(caminho: Path) -> list[dict[str, str]]:
    # utf-8-sig: o gabarito de 15/09 vem com BOM; sem isso a primeira coluna se
    # chama "﻿nivel" e o nivel sai None em toda linha. Ver docs/dados.md.
    with caminho.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def linhas_solution(caminho_goldenset: Path) -> list[dict[str, str]]:
    """Devolve as linhas do solution.csv, uma por documento, ordenadas."""
    registros = _ler_goldenset(caminho_goldenset)
    if not registros:
        raise SystemExit(f"goldenset vazio: {caminho_goldenset}")

    por_documento: dict[str, list[dict[str, str]]] = defaultdict(list)
    niveis: dict[str, str] = {}
    for r in registros:
        documento = r["documento_id"]
        por_documento[documento].append(r)
        nivel = r["nivel"]
        if niveis.setdefault(documento, nivel) != nivel:
            raise SystemExit(f"{documento}: nível inconsistente entre as citações")

    linhas: list[dict[str, str]] = []
    for documento in sorted(por_documento):
        citacoes = sorted(por_documento[documento], key=lambda r: int(r["inicio"]))
        _conferir(documento, citacoes)
        blocos = []
        for c in citacoes:
            ids = c["id_canonico"].strip() or VAZIO
            blocos.append(f"{int(c['inicio'])},{int(c['fim'])},{c['classificacao']},{ids}")
        linhas.append(
            {
                "documento_id": documento,
                "nivel": niveis[documento],
                "citacoes": "|".join(blocos) if blocos else VAZIO,
            }
        )
    return linhas


def _conferir(documento: str, citacoes: list[dict[str, str]]) -> None:
    """As duas pré-condições do parser oficial, com erro legível."""
    for anterior, atual in zip(citacoes, citacoes[1:], strict=False):
        if int(anterior["fim"]) > int(atual["inicio"]):
            raise SystemExit(
                f"{documento}: citações {anterior['citacao_id']} e {atual['citacao_id']} "
                f"se sobrepõem — o alinhamento da métrica exige spans disjuntos."
            )
    for c in citacoes:
        if c["classificacao"] == "real" and not c["id_canonico"].strip():
            raise SystemExit(f"{documento}/{c['citacao_id']}: citação real sem id_canonico.")


def escrever(linhas: list[dict[str, str]], saida: Path) -> None:
    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--goldenset", type=Path, default=Path("data/dev/goldenset.csv"))
    p.add_argument("--saida", type=Path, default=Path("data/dev/solution.csv"))
    args = p.parse_args(argv)

    if not args.goldenset.exists():
        raise SystemExit(f"gabarito não encontrado: {args.goldenset} (rode `make dados-kaggle`)")

    linhas = linhas_solution(args.goldenset)
    escrever(linhas, args.saida)
    total = sum(len(linha["citacoes"].split("|")) for linha in linhas if linha["citacoes"] != VAZIO)
    print(f"{len(linhas)} documentos, {total} citações -> {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
