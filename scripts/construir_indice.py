"""Constrói o índice de números próprios dos acórdãos, uma vez, offline.

O PDF do desafio recomenda explicitamente isso em vez de varrer o FTS a cada
citação: 1.016 registros varridos uma vez custam segundos, e a consulta em
runtime vira um acesso a dicionário.

Uso:
    python scripts/construir_indice.py --db data/dev/desafio1_bracis.db \
        --saida data/dev/indice_cabecalhos.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from verificador.base_canonica import construir_indice, salvar_indice  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=Path, default=Path("data/dev/desafio1_bracis.db"))
    p.add_argument("--saida", type=Path, default=Path("data/dev/indice_cabecalhos.json"))
    args = p.parse_args(argv)

    if not args.db.exists():
        raise SystemExit(f"base canônica não encontrada: {args.db} (rode `make dados`)")

    indice = construir_indice(args.db)
    salvar_indice(indice, args.saida)
    print(f"{len(indice['registros'])} acórdãos, {len(indice['numeros'])} números -> {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
