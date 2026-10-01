"""Ponto de entrada do verificador: gera o CSV de submissão e/ou um JSON por documento.

Uso: ``python -m verificador.cli --db <banco> --input <pasta> [--csv <arq>] [--output <pasta>]``
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from .base import BaseCanonica

PADRAO_DB = Path("data/dev/desafio1_bracis.db")

# Ordem fixa das classes no resumo; `contrato.CLASSIFICACOES` é um conjunto.
LABELS = ("real", "inventada", "incompleta")


def _carregar_base(indice: Path | None, db: Path) -> BaseCanonica:
    """Constrói o índice a partir do banco; o JSON pré-construído é só reserva.

    Preferir o banco garante que a execução local e a reexecução usem a mesma
    base, e o JSON só vale passado explicitamente para nunca cair numa base antiga.
    """
    if db.is_file():
        return BaseCanonica.de_banco(db)
    if indice is not None and indice.is_file():
        return BaseCanonica.de_arquivo(indice)
    if indice is None:
        raise SystemExit(f"base canônica não encontrada: {db}")
    raise SystemExit(f"nem base canônica ({db}) nem índice ({indice}) encontrados")


def _load_base(indice: Path | None, db: Path) -> BaseCanonica:
    """`_carregar_base` com mensagem legível quando o arquivo existe mas não abre."""
    try:
        return _carregar_base(indice, db)
    except Exception as error:  # noqa: BLE001 — qualquer falha vira mensagem, não traceback
        raise SystemExit(f"não consegui ler a base canônica {db}: {error}") from None


def collect_texts(folder: Path) -> list[Path]:
    """Os ``.txt`` a processar, em ordem determinística.

    Sem nenhum no primeiro nível, procura nas subpastas (zip costuma criar um
    nível a mais), pois um CSV sem documentos seria rejeitado.
    """
    from .pipeline import _eh_txt

    top_level = sorted(path for path in folder.iterdir() if _eh_txt(path))
    if top_level:
        return top_level
    nested = sorted(path for path in folder.rglob("*") if _eh_txt(path))
    if nested:
        print(
            f"aviso: nenhum .txt no primeiro nível de {folder}; "
            f"processando {len(nested)} encontrados nas subpastas",
            file=sys.stderr,
        )
    return nested


def _warn_repeated_ids(paths: list[Path]) -> None:
    """Avisa de ``documento_id`` repetido em subpastas; no CSV fica o último."""
    from .texto import documento_id

    counts = Counter(documento_id(path) for path in paths)
    for repeated in sorted(key for key, count in counts.items() if count > 1):
        print(
            f"aviso: documento_id repetido {repeated!r} em {counts[repeated]} arquivos; "
            "fica o último",
            file=sys.stderr,
        )


def _summary(documents: list[dict], elapsed: float) -> str:
    labels = Counter(c["classificacao"] for d in documents for c in d["citacoes"])
    by_label = ", ".join(f"{label} {labels[label]}" for label in LABELS)
    total = sum(labels.values())
    return f"{len(documents)} documentos, {total} citações ({by_label}) em {elapsed:.1f} s"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Verificador de citações jurídicas")
    p.add_argument("--input", dest="entrada", type=Path, required=True, help="pasta com .txt")
    p.add_argument("--output", dest="saida", type=Path, help="pasta dos JSONs do contrato")
    p.add_argument("--csv", type=Path, help="submission.csv no formato das submissões")
    p.add_argument("--db", type=Path, default=PADRAO_DB, help="base canônica (SQLite)")
    p.add_argument(
        "--indice", type=Path, default=None, help="índice JSON pré-construído; só vale sem o banco"
    )
    args = p.parse_args(argv)
    if args.saida is None and args.csv is None:
        p.error("informe --csv, --output ou os dois")

    if not args.entrada.is_dir():
        raise SystemExit(f"pasta de entrada não encontrada: {args.entrada}")
    paths = collect_texts(args.entrada)
    if not paths:
        raise SystemExit(f"nenhum .txt em {args.entrada} nem nas subpastas")
    _warn_repeated_ids(paths)

    from .pipeline import process_files
    from .saida.submissao import check_submission, write_submission

    # O relógio inclui a construção do índice, que domina o tempo num lote pequeno.
    started = time.monotonic()
    base = _load_base(args.indice, args.db)
    documents: list[dict] = []
    for document in process_files(paths, base):
        if args.saida is not None:
            document.escrever(args.saida)
        documents.append(document.para_dicionario())
    elapsed = time.monotonic() - started

    problems: list[str] = []
    if args.csv is not None:
        write_submission(documents, args.csv)
        # Confere contra os documentos processados, como o avaliador faz.
        problems = check_submission(args.csv, {d["documento_id"] for d in documents})

    destination = args.csv if args.csv is not None else args.saida
    print(f"{_summary(documents, elapsed)} -> {destination}", file=sys.stderr)
    if args.csv is None:
        print(f"{len(documents)} documentos processados -> {args.saida}")

    for problem in problems:
        print(f"  ✗ {problem}", file=sys.stderr)
    if problems:
        print(
            f"a conferência de {args.csv} falhou com {len(problems)} problema(s); "
            "o CSV foi escrito, mas seria rejeitado",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
