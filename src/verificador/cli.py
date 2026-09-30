"""Ponto de entrada no contrato de execução da organização.

    bash run.sh <caminho_db> <pasta_txt> <arquivo_saida.csv>

que chama

    python -m verificador.cli --db <caminho_db> --input <pasta_txt> --csv <arquivo_saida.csv>

A saída é o CSV no formato da submissão (ver :mod:`verificador.submissao`); com
`--output`, os JSONs do contrato também ficam gravados. Tudo é determinístico e
local: nenhuma chamada de rede, nenhum peso de modelo.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from .base_canonica import BaseCanonica

# Fora do container os caminhos são os do repositório; dentro, os volumes que o
# Dockerfile declara em VERIFICADOR_DB e VERIFICADOR_INDICE.
PADRAO_INDICE = Path(os.environ.get("VERIFICADOR_INDICE", "data/dev/indice_cabecalhos.json"))
PADRAO_DB = Path(os.environ.get("VERIFICADOR_DB", "data/dev/desafio1_bracis.db"))


def _carregar_base(indice: Path, db: Path) -> BaseCanonica:
    """Constrói o índice do banco; o JSON pré-construído é só o reserva.

    No contrato de execução da organização só o banco é montado, e o índice sai
    dele. Preferir um JSON que estivesse no disco faria a execução local usar um
    índice possivelmente antigo — a submissão feita daqui divergiria da
    reexecução, e "não bater o score" desclassifica. Construir leva cerca de um
    segundo.
    """
    if db.exists():
        return BaseCanonica.de_banco(db)
    if indice.exists():
        return BaseCanonica.de_arquivo(indice)
    raise SystemExit(
        f"nem índice ({indice}) nem base canônica ({db}) encontrados.\n"
        "Rode `make dados && make indice`."
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verificador de citações jurídicas")
    p.add_argument("--input", dest="entrada", type=Path, required=True, help="pasta com .txt")
    p.add_argument("--output", dest="saida", type=Path, help="pasta dos JSONs")
    p.add_argument("--csv", type=Path, help="arquivo da saída no formato da submissão")
    p.add_argument("--indice", type=Path, default=PADRAO_INDICE)
    p.add_argument("--db", type=Path, default=PADRAO_DB)
    args = p.parse_args(argv)

    if not args.entrada.is_dir():
        raise SystemExit(f"pasta de entrada não encontrada: {args.entrada}")
    if args.saida is None and args.csv is None:
        raise SystemExit("informe --output (JSONs), --csv (submissão) ou os dois")

    from .pipeline import processar_pasta
    from .submissao import escrever_csv

    base = _carregar_base(args.indice, args.db)
    with tempfile.TemporaryDirectory() as temporaria:
        pasta = args.saida or Path(temporaria)
        escritos = processar_pasta(args.entrada, pasta, base)
        print(f"{len(escritos)} documentos processados -> {pasta if args.saida else 'CSV'}")
        if args.csv is not None:
            escrever_csv(escritos, args.csv)
            print(f"submissão -> {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
