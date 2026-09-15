"""Baixa a distribuição final dos dados do desafio e organiza em ``data/dev/``.

⚠ **Os dados não podem ser redistribuídos.** Foram liberados apenas às equipes
inscritas e não têm download público. Não anexe o zip a release, issue, gist,
bucket público nem ao próprio repositório: cada pessoa da equipe baixa do
Kaggle com a própria credencial. Para conferir que duas máquinas estão com os
mesmos bytes, compare os SHA-256 da tabela em ``docs/dados.md`` — é para isso
que ela existe.

Duas fontes, ambas com o mesmo resultado em ``data/dev/``:

``--kaggle`` (padrão)
    Aba *Data* da competição. Exige credencial — ``~/.kaggle/kaggle.json``
    (Settings → API → Create New Token) ou as variáveis ``KAGGLE_USERNAME`` e
    ``KAGGLE_KEY``.

``--zip CAMINHO``
    Zip já baixado à mão da aba *Data*, para quando a credencial não está à mão.

O ``kagglehub`` **não** é dependência do projeto de propósito: a organização
roda a solução offline, e nada de rede pode entrar no bundle reproduzível. Por
isso o alvo do Makefile o injeta com ``uv run --with kagglehub``.

Ao final imprime o diff contra o que havia antes em ``data/dev/``: quais
citações saíram, entraram ou mudaram de campo, e o que mudou na base canônica e
nos documentos. A organização publica as revisões sem detalhar caso a caso,
então esse relatório é a única forma de saber o que precisa ser revisto.

Uso:
    uv run --with kagglehub python scripts/baixar_dados.py
    python scripts/baixar_dados.py --zip data/raw/desafio-jusbrasil-bracis-2026.zip
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

from preparar_dados import sha256, validar_offsets

COMPETICAO = "desafio-jusbrasil-bracis-2026"

# Os .py da organização ficam separados: são ferramentas de referência, não dados.
FERRAMENTAS = {"json_to_submission.py", "kaggle_metric.py"}

# A distribuição de 15/09 renomeou o gabarito. Normalizamos para goldenset.csv,
# que é o nome que o Makefile, os testes e scripts/avaliar.py esperam.
NOMES_GOLDENSET = ("goldenset_offsets.csv", "goldenset.csv")
GOLDENSET = "goldenset.csv"

# O arquivo de 15/09 vem com BOM; utf-8-sig lê com e sem, então é o padrão aqui.
ENCODING_CSV = "utf-8-sig"

CHAVE = ("documento_id", "citacao_id")


# --------------------------------------------------------------------------- #
# Aquisição
# --------------------------------------------------------------------------- #


def baixar_kaggle() -> Path:
    """Baixa a competição com kagglehub e devolve o diretório do cache."""
    try:
        import kagglehub
    except ModuleNotFoundError:
        raise SystemExit(
            "kagglehub não instalado — rode via "
            "`uv run --with kagglehub python scripts/baixar_dados.py` (ou `make dados`)."
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
        nome = GOLDENSET if item.name in NOMES_GOLDENSET else item.name
        alvo = destino / ("ferramentas" if item.name in FERRAMENTAS else ".") / nome
        shutil.copy2(item, alvo)
        rotulo = alvo.relative_to(destino).as_posix()
        if nome != item.name:
            rotulo += f"  (renomeado de {item.name})"
        copiados.append(rotulo)
    return copiados


# --------------------------------------------------------------------------- #
# Retrato e diff
# --------------------------------------------------------------------------- #


def ler_goldenset(caminho: Path) -> list[dict[str, str]] | None:
    if not caminho.exists():
        return None
    with caminho.open(encoding=ENCODING_CSV) as f:
        return list(csv.DictReader(f))


def _documentos_da_base(caminho: Path) -> dict[str, tuple]:
    """Lê a tabela documentos como {id: linha}, para diff linha a linha."""
    if not caminho.exists():
        return {}
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        colunas = [d[1] for d in con.execute("PRAGMA table_info(documentos)")]
        if not colunas:
            return {}
        campos = ", ".join('"' + c + '"' for c in colunas)
        pos_id = colunas.index("id")
        return {str(r[pos_id]): r for r in con.execute(f"SELECT {campos} FROM documentos")}
    finally:
        con.close()


def retrato(destino: Path) -> dict:
    """Fotografa data/dev/ antes de sobrescrever, para permitir o diff.

    Só é chamado com os bytes novos já em mãos: se o download falhar, nada é
    tocado e a base de comparação continua de pé.
    """
    db = destino / "desafio1_bracis.db"
    txt = destino / "txt"
    return {
        "goldenset": ler_goldenset(destino / GOLDENSET),
        "db_sha": sha256(db) if db.exists() else None,
        "db_docs": _documentos_da_base(db),
        "txt": {p.name: sha256(p) for p in sorted(txt.glob("*.txt"))} if txt.is_dir() else {},
    }


def _indexar(registros: list[dict[str, str]]) -> dict[tuple[str, ...], dict[str, str]]:
    return {tuple(r[c] for c in CHAVE): r for r in registros}


def _contar(registros: list[dict[str, str]], campo: str) -> str:
    contagem: dict[str, int] = {}
    for r in registros:
        contagem[r[campo]] = contagem.get(r[campo], 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(contagem.items()))


def relatar_goldenset(antes: list[dict[str, str]], depois: list[dict[str, str]]) -> None:
    """Imprime o que mudou no gabarito, citação a citação."""
    ia, ib = _indexar(antes), _indexar(depois)
    sairam = sorted(ia.keys() - ib.keys())
    entraram = sorted(ib.keys() - ia.keys())
    mudaram = []
    for chave in sorted(ia.keys() & ib.keys()):
        campos = sorted(c for c in ib[chave] if ia[chave].get(c) != ib[chave].get(c))
        if campos:
            mudaram.append((chave, campos))

    print(f"\n== goldenset: {len(antes)} → {len(depois)} citações ==")
    if not (sairam or entraram or mudaram):
        print("  sem mudanças")
        return

    if sairam:
        print(f"  saíram ({len(sairam)}):")
        for doc, cit in sairam:
            r = ia[(doc, cit)]
            print(f"    - {doc}/{cit} [{r['tipo']}/{r['classificacao']}] {r['trecho'][:70]!r}")
    if entraram:
        print(f"  entraram ({len(entraram)}):")
        for doc, cit in entraram:
            r = ib[(doc, cit)]
            print(f"    + {doc}/{cit} [{r['tipo']}/{r['classificacao']}] {r['trecho'][:70]!r}")
    if mudaram:
        # Deslocamento puro de offset é ruído derivado do .txt: agrupamos à parte
        # para que as correções de conteúdo não se percam no meio.
        offsets = [(k, c) for k, c in mudaram if set(c) <= {"inicio", "fim"}]
        conteudo = [(k, c) for k, c in mudaram if not set(c) <= {"inicio", "fim"}]
        if conteudo:
            print(f"  mudaram de conteúdo ({len(conteudo)}):")
            for (doc, cit), campos in conteudo:
                print(f"    ~ {doc}/{cit}")
                for c in campos:
                    print(f"        {c}: {ia[(doc, cit)].get(c)!r} → {ib[(doc, cit)].get(c)!r}")
        if offsets:
            nomes = ", ".join(f"{d}/{c}" for (d, c), _ in offsets)
            print(f"  só deslocaram offset ({len(offsets)}): {nomes}")

    for rotulo, registros in (("antes ", antes), ("depois", depois)):
        print(f"  {rotulo}: classes {_contar(registros, 'classificacao')}")
        print(f"          tipos   {_contar(registros, 'tipo')}")


def relatar_base(antes: dict, destino: Path) -> None:
    """Imprime o que mudou na base canônica e nos .txt."""
    db = destino / "desafio1_bracis.db"
    novo_sha = sha256(db) if db.exists() else None

    print("\n== base canônica ==")
    if antes["db_sha"] is None:
        print(f"  nova ({novo_sha})")
    elif antes["db_sha"] == novo_sha:
        print(f"  inalterada ({novo_sha})")
    else:
        print(f"  MUDOU\n    antes:  {antes['db_sha']}\n    depois: {novo_sha}")
        va, vb = antes["db_docs"], _documentos_da_base(db)
        removidos = sorted(va.keys() - vb.keys())
        incluidos = sorted(vb.keys() - va.keys())
        alterados = sorted(i for i in va.keys() & vb.keys() if va[i] != vb[i])
        print(f"    documentos: {len(va)} → {len(vb)}")
        if removidos:
            print(f"    removidos ({len(removidos)}): {', '.join(removidos)}")
        if incluidos:
            print(f"    incluídos ({len(incluidos)}): {', '.join(incluidos)}")
        if alterados:
            print(f"    alterados ({len(alterados)}): {', '.join(alterados[:20])}")
        print("    ⚠ rode `make indice` de novo — o índice foi construído da base velha.")

    txt = destino / "txt"
    novos = {p.name: sha256(p) for p in sorted(txt.glob("*.txt"))} if txt.is_dir() else {}
    velhos = antes["txt"]
    removidos = sorted(velhos.keys() - novos.keys())
    incluidos = sorted(novos.keys() - velhos.keys())
    alterados = sorted(n for n in velhos.keys() & novos.keys() if velhos[n] != novos[n])

    print(f"\n== documentos: {len(velhos)} → {len(novos)} arquivos ==")
    for rotulo, nomes in (
        ("removidos", removidos),
        ("incluídos", incluidos),
        ("alterados", alterados),
    ):
        if nomes:
            print(f"  {rotulo} ({len(nomes)}): {', '.join(nomes)}")
    if not (removidos or incluidos or alterados):
        print("  sem mudanças" if velhos else "  primeira carga")
    if alterados:
        print("  ⚠ .txt alterado desloca offsets — reveja análises presas a inicio/fim.")


# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--destino", type=Path, default=Path("data/dev"))
    fonte = p.add_mutually_exclusive_group()
    fonte.add_argument("--kaggle", action="store_true", help="baixa da aba Data do Kaggle (padrão)")
    fonte.add_argument("--zip", type=Path, default=None, help="usa um zip já baixado à mão")
    args = p.parse_args(argv)

    if args.zip is not None and not args.zip.exists():
        raise SystemExit(f"zip não encontrado: {args.zip}")

    with tempfile.TemporaryDirectory() as tmp:
        if args.zip is not None:
            print(f"extraindo {args.zip}")
            origem = Path(tmp) / "extraido"
            with zipfile.ZipFile(args.zip) as z:
                z.extractall(origem)
        else:
            origem = baixar_kaggle()

        # Só agora, com os bytes novos em mãos, mexemos em data/dev/. Fotografar
        # antes do download faria um download falho destruir a base do diff.
        antes = retrato(args.destino)
        if antes["goldenset"] is not None:
            anterior = args.destino / "goldenset_anterior.csv"
            shutil.copy2(args.destino / GOLDENSET, anterior)
            print(f"gabarito anterior preservado em {anterior.name}")

        for nome in sincronizar(origem, args.destino):
            print(f"  {nome}")

    goldenset = args.destino / GOLDENSET
    if not goldenset.exists():
        print(f"FALHA: nenhum de {NOMES_GOLDENSET} veio no download", file=sys.stderr)
        return 1

    registros = ler_goldenset(goldenset) or []
    if antes["goldenset"] is None:
        print(f"\n== goldenset: {len(registros)} citações (primeira carga, sem diff) ==")
        print(f"  classes {_contar(registros, 'classificacao')}")
        print(f"  tipos   {_contar(registros, 'tipo')}")
    else:
        relatar_goldenset(antes["goldenset"], registros)
    relatar_base(antes, args.destino)

    print(f"\nsha256 desafio1_bracis.db: {sha256(args.destino / 'desafio1_bracis.db')}")
    print(f"sha256 {GOLDENSET}:      {sha256(goldenset)}")

    problemas = validar_offsets(registros, args.destino / "txt")
    if problemas:
        print(f"\nFALHA: {len(problemas)} citações não batem com o texto:", file=sys.stderr)
        for linha in problemas[:10]:
            print(f"  {linha}", file=sys.stderr)
        return 1

    print("\noffsets: todas as citações batem com texto[inicio:fim]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
