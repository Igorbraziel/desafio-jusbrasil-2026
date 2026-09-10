"""Baixa os arquivos da competição no Kaggle e organiza em ``data/dev/``.

Substitui o caminho manual (zip do e-mail em ``data/raw/``) pela fonte atual: a
aba *Data* da competição, que traz também o ``goldenset.csv`` oficial, o
conversor de submissão e o script da métrica.

Requer credencial do Kaggle — ``~/.kaggle/kaggle.json`` (Settings → API → Create
New Token) ou as variáveis ``KAGGLE_USERNAME``/``KAGGLE_KEY``.

O ``kagglehub`` **não** é dependência do projeto de propósito: a organização
roda a solução offline, e nada de rede pode entrar no bundle reproduzível. Por
isso o alvo do Makefile o injeta com ``uv run --with kagglehub``.

Aceita também um zip já baixado da aba *Data* (``--zip``), caso a credencial
não esteja à mão — o resultado em ``data/dev/`` é o mesmo.

Uso:
    uv run --with kagglehub python scripts/baixar_dados.py --destino data/dev
    python scripts/baixar_dados.py --zip data/raw/desafio-jusbrasil-bracis-2026.zip
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from preparar_dados import sha256, validar_offsets

COMPETICAO = "desafio-jusbrasil-bracis-2026"

# Os .py da organização ficam separados: são ferramentas de referência, não dados.
FERRAMENTAS = {"json_to_submission.py", "kaggle_metric.py"}


def sincronizar(origem: Path, destino: Path) -> list[str]:
    """Copia o conteúdo baixado para data/dev/, separando as ferramentas."""
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "ferramentas").mkdir(exist_ok=True)
    copiados: list[str] = []
    for item in sorted(origem.iterdir()):
        if item.name.startswith((".", "__MACOSX")):
            continue
        if item.is_dir():
            alvo = destino / item.name
            shutil.copytree(item, alvo, dirs_exist_ok=True)
            copiados.append(f"{item.name}/ ({len(list(alvo.iterdir()))} arquivos)")
            continue
        alvo = destino / ("ferramentas" if item.name in FERRAMENTAS else ".") / item.name
        shutil.copy2(item, alvo)
        copiados.append(alvo.relative_to(destino).as_posix())
    return copiados


def baixar() -> Path:
    """Baixa a competição com kagglehub e devolve o diretório do cache."""
    try:
        import kagglehub
    except ModuleNotFoundError:
        raise SystemExit(
            "kagglehub não instalado — rode via "
            "`uv run --with kagglehub python scripts/baixar_dados.py` (ou `make dados-kaggle`)."
        ) from None

    print(f"baixando a competição {COMPETICAO} do Kaggle…")
    try:
        cache = Path(kagglehub.competition_download(COMPETICAO))
    except kagglehub.exceptions.UnauthenticatedError:
        raise SystemExit(
            "credencial do Kaggle ausente. Gere um token em "
            "https://www.kaggle.com/settings → API → Create New Token e salve como "
            "~/.kaggle/kaggle.json (ou exporte KAGGLE_USERNAME e KAGGLE_KEY)."
        ) from None
    print(f"  cache: {cache}")
    return cache


def preservar_anterior(goldenset: Path) -> Path | None:
    """Guarda o goldenset atual antes de sobrescrever, para permitir o diff.

    O gabarito foi revisado pela organização em 01/09/2026 e o que temos local
    veio do xlsx de 25/08. Comparar os dois é a única forma de saber se o que
    está documentado em docs/dados.md ainda vale.
    """
    if not goldenset.exists():
        return None
    anterior = goldenset.with_name("goldenset_anterior.csv")
    shutil.copy2(goldenset, anterior)
    return anterior


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--destino", type=Path, default=Path("data/dev"))
    p.add_argument(
        "--zip",
        type=Path,
        default=None,
        help="zip já baixado da aba Data; se ausente, baixa do Kaggle com kagglehub",
    )
    args = p.parse_args(argv)

    if args.zip is not None and not args.zip.exists():
        raise SystemExit(f"zip não encontrado: {args.zip}")

    anterior = preservar_anterior(args.destino / "goldenset.csv")

    with tempfile.TemporaryDirectory() as tmp:
        if args.zip is not None:
            print(f"extraindo {args.zip}")
            origem = Path(tmp)
            with zipfile.ZipFile(args.zip) as z:
                z.extractall(origem)
        else:
            origem = baixar()

        for nome in sincronizar(origem, args.destino):
            print(f"  {nome}")

    for nome in ("desafio1_bracis.db", "goldenset.csv"):
        caminho = args.destino / nome
        if caminho.exists():
            print(f"  sha256 {nome}: {sha256(caminho)}")

    goldenset = args.destino / "goldenset.csv"
    if not goldenset.exists():
        print("FALHA: goldenset.csv não veio no download", file=sys.stderr)
        return 1

    import csv

    registros = list(csv.DictReader(goldenset.open(encoding="utf-8")))
    print(f"  goldenset: {len(registros)} citações")

    if anterior is not None:
        igual = anterior.read_bytes() == goldenset.read_bytes()
        veredito = "idêntico" if igual else "DIFERENTE do novo"
        print(f"  gabarito anterior preservado em {anterior.name} — {veredito}")

    problemas = validar_offsets(registros, args.destino / "txt")
    if problemas:
        print(f"\nFALHA: {len(problemas)} citações não batem com o texto:", file=sys.stderr)
        for linha in problemas[:10]:
            print(f"  {linha}", file=sys.stderr)
        return 1

    print("  offsets: todas as citações batem com texto[inicio:fim]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
