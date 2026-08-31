"""Ponto de entrada no contrato de execução da organização.

    docker run <img> --input /data/in --output /data/out

Tudo é determinístico e local: nenhuma chamada de rede, nenhum peso de modelo.
O container roda offline.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .base_canonica import BaseCanonica

# Fora do container os caminhos são os do repositório; dentro, os volumes que o
# Dockerfile declara em VERIFICADOR_DB e VERIFICADOR_INDICE.
PADRAO_INDICE = Path(os.environ.get("VERIFICADOR_INDICE", "data/dev/indice_cabecalhos.json"))
PADRAO_DB = Path(os.environ.get("VERIFICADOR_DB", "data/dev/desafio1_bracis.db"))


def _carregar_base(indice: Path, db: Path) -> BaseCanonica:
    """Usa o índice pré-construído; se não existir, constrói a partir do banco."""
    if indice.exists():
        return BaseCanonica.de_arquivo(indice)
    if db.exists():
        return BaseCanonica.de_banco(db)
    raise SystemExit(
        f"nem índice ({indice}) nem base canônica ({db}) encontrados.\n"
        "Rode `make dados && make indice`."
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verificador de citações jurídicas")
    p.add_argument("--input", dest="entrada", type=Path, required=True, help="pasta com .txt")
    p.add_argument("--output", dest="saida", type=Path, required=True, help="pasta dos JSONs")
    p.add_argument("--indice", type=Path, default=PADRAO_INDICE)
    p.add_argument("--db", type=Path, default=PADRAO_DB)
    args = p.parse_args(argv)

    if not args.entrada.is_dir():
        raise SystemExit(f"pasta de entrada não encontrada: {args.entrada}")

    from .pipeline import processar_pasta

    base = _carregar_base(args.indice, args.db)
    escritos = processar_pasta(args.entrada, args.saida, base)
    print(f"{len(escritos)} documentos processados -> {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
