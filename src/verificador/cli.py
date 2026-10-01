"""Ponto de entrada do verificador.

Entrega — o que o ``run.sh`` chama, com o CSV no formato das submissões::

    python -m verificador.cli --db <banco> --input <pasta_txt> --csv <submission.csv>
                              [--output <pasta_json>]

Desenvolvimento — um JSON do contrato por documento::

    python -m verificador.cli --input <pasta_txt> --output <pasta_json> --db <banco>

Tudo é determinístico e local: nenhuma chamada de rede, nenhum peso de modelo.
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
    """Constrói o índice do banco; o JSON pré-construído é só o reserva.

    No contrato de execução da organização só o banco é montado, e o índice sai
    dele. Preferir um JSON que estivesse no disco faria a execução local usar um
    índice possivelmente antigo — a submissão feita daqui divergiria da
    reexecução, e "não bater o score" desclassifica. Construir leva cerca de um
    segundo.

    O índice só vale passado explicitamente. Antes ele tinha um padrão em
    ``data/dev``, e com o banco ausente — um caminho errado na avaliação final —
    a execução caía em silêncio no índice da base antiga: código 0 e um CSV de
    aparência normal, resolvido contra a base errada.
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

    O contrato põe os documentos no primeiro nível da pasta. Sem nenhum ali,
    procura nas subpastas: uma pasta que passou por um zip costuma voltar com
    um nível a mais (``pasta/txt/*.txt``), e processar zero documentos daria um
    CSV só com o cabeçalho — sem linha para nenhum documento, rejeitado inteiro.
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
    """Dois arquivos com o mesmo nome em subpastas diferentes são um documento só.

    O ``documento_id`` é o nome sem extensão, e o CSV tem uma linha por id: fica
    o último, como na pasta de JSONs, em que a última escrita sobrescreve.
    """
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
        # Confere contra os documentos processados, não contra o que o CSV tem:
        # é assim que o avaliador acusa o documento sem linha.
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
