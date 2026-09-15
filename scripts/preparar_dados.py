"""Prepara os dados do desafio a partir do zip enviado pela organização.

Faz três coisas, nesta ordem:

1. Extrai o zip para ``data/dev/``, descartando o lixo de macOS (``__MACOSX/``,
   ``.DS_Store``) e achatando o diretório-raiz ``dados_desafio_jusbrasil/``.
2. Registra o SHA-256 dos artefatos, para conferir contra o documentado em
   ``docs/dados.md`` — a base canônica é um snapshot congelado e mudanças nela
   invalidam qualquer índice construído antes.
3. Converte ``goldenset.xlsx`` em ``goldenset.csv`` com os campos numéricos como
   inteiros. Isso não é cosmético: no xlsx, ``id_canonico`` está gravado como
   float (``5.665364632E9``); ler sem cast produz ``5665364632.0``, que não casa
   com nenhum ``id`` da base.

Ao final, valida que ``trecho == texto[inicio:fim]`` em cada citação. Essa
checagem é o teste de fumaça de que estamos lendo offsets em codepoints Unicode
do mesmo jeito que a organização.

**Caminho legado.** O zip do e-mail traz o ``goldenset.xlsx`` de 25/08, com 225
citações — duas revisões atrás. Para a distribuição final use
``scripts/baixar_dados.py`` (``make dados``); este módulo continua aqui porque
``sha256`` e ``validar_offsets`` são compartilhados com ele.

Uso:
    python scripts/preparar_dados.py --zip data/raw/dados_desafio_jusbrasil.zip --destino data/dev
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

COLUNAS_GOLDENSET = [
    "nivel",
    "documento_id",
    "citacao_id",
    "inicio",
    "fim",
    "trecho",
    "tipo",
    "classificacao",
    "id_canonico",
]
COLUNAS_INTEIRAS = {"nivel", "inicio", "fim", "id_canonico"}


def extrair(caminho_zip: Path, destino: Path) -> None:
    """Extrai o zip achatando o diretório-raiz e ignorando artefatos do macOS."""
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho_zip) as z:
        for info in z.infolist():
            nome = info.filename
            if nome.startswith("__MACOSX/") or Path(nome).name in {".DS_Store", ""}:
                continue
            partes = Path(nome).parts
            if partes and partes[0] == "dados_desafio_jusbrasil":
                partes = partes[1:]
            if not partes:
                continue
            alvo = destino.joinpath(*partes)
            if info.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as origem, alvo.open("wb") as saida:
                shutil.copyfileobj(origem, saida)


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _texto_celula(celula: ET.Element, compartilhadas: list[str]) -> str:
    tipo = celula.get("t")
    if tipo == "inlineStr":
        return "".join(t.text or "" for t in celula.iter(NS + "t"))
    valor = celula.find(NS + "v")
    if valor is None:
        return ""
    bruto = valor.text or ""
    if tipo == "s":
        return compartilhadas[int(bruto)]
    return bruto


def ler_xlsx(caminho: Path) -> list[dict[str, str]]:
    """Lê a primeira planilha de um .xlsx usando só a biblioteca padrão.

    Evitamos openpyxl de propósito: manter as dependências de runtime em zero
    simplifica o Dockerfile exigido na submissão.
    """
    with zipfile.ZipFile(caminho) as z:
        compartilhadas: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
            compartilhadas = [
                "".join(t.text or "" for t in si.iter(NS + "t")) for si in raiz.findall(NS + "si")
            ]
        planilha = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    linhas: list[dict[str, str]] = []
    dados = planilha.find(NS + "sheetData")
    if dados is None:
        return linhas
    for linha in dados.findall(NS + "row"):
        celulas: dict[str, str] = {}
        for celula in linha.findall(NS + "c"):
            ref = re.match(r"[A-Z]+", celula.get("r", "A")).group()
            celulas[ref] = _texto_celula(celula, compartilhadas)
        linhas.append(celulas)
    return linhas


def converter_goldenset(entrada: Path, saida: Path) -> list[dict[str, str]]:
    """Converte o goldenset .xlsx em .csv, com os campos numéricos inteiros."""
    linhas = ler_xlsx(entrada)
    if not linhas:
        raise SystemExit(f"planilha vazia: {entrada}")

    cabecalho = linhas[0]
    posicao = {nome: ref for ref, nome in cabecalho.items() if nome}
    faltando = [c for c in COLUNAS_GOLDENSET if c not in posicao]
    if faltando:
        raise SystemExit(f"colunas ausentes no goldenset: {faltando}")

    registros: list[dict[str, str]] = []
    for bruta in linhas[1:]:
        registro: dict[str, str] = {}
        for coluna in COLUNAS_GOLDENSET:
            valor = bruta.get(posicao[coluna], "").strip()
            if coluna in COLUNAS_INTEIRAS and valor:
                valor = str(int(float(valor)))
            registro[coluna] = valor
        if registro["documento_id"]:
            registros.append(registro)

    saida.parent.mkdir(parents=True, exist_ok=True)
    with saida.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS_GOLDENSET)
        escritor.writeheader()
        escritor.writerows(registros)
    return registros


def validar_offsets(registros: list[dict[str, str]], pasta_txt: Path) -> list[str]:
    """Confere que trecho == texto[inicio:fim] em cada citação do gabarito."""
    cache: dict[str, str] = {}
    problemas: list[str] = []
    for r in registros:
        doc = r["documento_id"]
        if doc not in cache:
            caminho = pasta_txt / f"{doc}.txt"
            if not caminho.exists():
                problemas.append(f"{doc}: .txt ausente")
                cache[doc] = ""
                continue
            cache[doc] = unicodedata.normalize("NFC", caminho.read_text(encoding="utf-8"))
        texto = cache[doc]
        if not texto:
            continue
        fatia = texto[int(r["inicio"]) : int(r["fim"])]
        # No gabarito as quebras de linha vêm escapadas como "\n" literal.
        esperado = r["trecho"].replace("\\n", "\n")
        if fatia != esperado:
            problemas.append(f"{doc}/{r['citacao_id']}: esperado {esperado!r}, obtido {fatia!r}")
    return problemas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--zip", type=Path, default=Path("data/raw/dados_desafio_jusbrasil.zip"))
    p.add_argument("--destino", type=Path, default=Path("data/dev"))
    args = p.parse_args(argv)

    if not args.zip.exists():
        raise SystemExit(
            f"zip não encontrado: {args.zip}\n"
            "Os dados são enviados por e-mail aos inscritos — ver docs/dados.md."
        )

    print(f"extraindo {args.zip} -> {args.destino}")
    extrair(args.zip, args.destino)

    for nome in ("desafio1_bracis.db", "goldenset.xlsx"):
        caminho = args.destino / nome
        if caminho.exists():
            print(f"  sha256 {nome}: {sha256(caminho)}")

    txts = sorted((args.destino / "txt").glob("*.txt"))
    print(f"  documentos: {len(txts)}")

    csv_saida = args.destino / "goldenset.csv"
    registros = converter_goldenset(args.destino / "goldenset.xlsx", csv_saida)
    print(f"  goldenset: {len(registros)} citações -> {csv_saida}")

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
