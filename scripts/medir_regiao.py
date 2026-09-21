"""Mede a qualidade de ``base_canonica.regiao_de_identificacao``.

A função decide o que entra no índice de números próprios, e é a etapa mais
delicada do pipeline: o texto de um acórdão cita outros acórdãos o tempo todo, e
indexar um número citado faz o registro errado responder por ele — a armadilha 5
de ``docs/dados.md``.

Este script existe para que trocar a implementação seja uma decisão medida, e
não uma opinião. É o análogo do ``comparativo_metodos`` do projeto
``parsing-tests``, com a diferença de que aqui há gabarito de verdade.

Três medidas:

**Recall (gabarito).** Das citações ``real``/``jurisprudencia`` do goldenset, em
quantas o número normalizado aparece no índice **apontando para o registro que o
gabarito indica**. É a única medida com verdade externa — e cobre só os
registros que o gabarito aponta.

**Ambiguidade (base inteira).** Quantos números do índice apontam para mais de
um registro. Cada um desses é uma citação que vira ``incompleta`` por empate, ou
um desempate arriscado. Duplicata real da base conta aqui e é esperada; o resto
é vazamento.

**Volume (base inteira).** Números por registro. Subir muito sem ganhar recall é
sinal de que a região está engolindo texto que cita outros processos.

Uso:
    python scripts/medir_regiao.py
    python scripts/medir_regiao.py --detalhar   # lista os casos que falham
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from verificador.base_canonica import (  # noqa: E402
    METODOS,
    MINIMO_DIGITOS,
    construir_indice,
)
from verificador.normalizacao import digitos_do_identificador  # noqa: E402


def _ler_goldenset(caminho_goldenset: Path) -> list[dict[str, str]]:
    with caminho_goldenset.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def medir(caminho_db: Path, caminho_goldenset: Path, metodo: str) -> dict:
    indice = construir_indice(caminho_db, metodo)
    numeros: dict[str, list[str]] = indice["numeros"]
    registros: dict[str, dict] = indice["registros"]

    # documento_id -> id_canonico, para comparar com o que o gabarito aponta
    id_por_documento = {d: dados["id"] for d, dados in registros.items()}

    conexao = sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)
    tribunal_por_id = dict(conexao.execute("SELECT id, tribunal FROM documentos"))
    natureza_por_id = dict(conexao.execute("SELECT id, natureza FROM documentos"))
    conexao.close()

    goldenset = _ler_goldenset(caminho_goldenset)

    acertos: list[dict] = []
    erros: list[dict] = []
    for citacao in goldenset:
        if citacao["classificacao"] != "real" or citacao["tipo"] != "jurisprudencia":
            continue
        esperado = int(citacao["id_canonico"])
        # Súmula é jurisprudência, mas não resolve por número de processo: o
        # alvo dela são os 5 registros de natureza `sumula`, pela tabela curada
        # de base_canonica.py. Medir aqui só confundiria o número.
        if natureza_por_id.get(esperado) != "acordao":
            continue
        trecho = citacao["trecho"].replace("\\n", "\n")
        numero = digitos_do_identificador(trecho)
        candidatos = [id_por_documento[d] for d in numeros.get(numero, [])]
        caso = {
            "documento": citacao["documento_id"],
            "citacao": citacao["citacao_id"],
            "trecho": trecho,
            "numero": numero,
            "tribunal": tribunal_por_id.get(esperado, "?"),
            "candidatos": len(candidatos),
        }
        (acertos if esperado in candidatos else erros).append(caso)

    # A medida que mais importa: uma `inventada` que encontra candidato vira
    # `real`, e é o único erro que a métrica oficial penaliza de forma
    # multiplicativa (τ). Cada caso aqui é vazamento da região custando caro.
    falsos: list[dict] = []
    for citacao in goldenset:
        # Só `jurisprudencia`: citação de lei resolve pela tabela curada de
        # súmulas e dispositivos, sem passar pelo índice de números próprios.
        if citacao["classificacao"] != "inventada" or citacao["tipo"] != "jurisprudencia":
            continue
        trecho = citacao["trecho"].replace("\\n", "\n")
        numero = digitos_do_identificador(trecho)
        documentos = numeros.get(numero, [])
        if documentos:
            falsos.append(
                {
                    "documento": citacao["documento_id"],
                    "citacao": citacao["citacao_id"],
                    "trecho": trecho,
                    "numero": numero,
                    "candidatos": len(documentos),
                }
            )

    ambiguos = {n: d for n, d in numeros.items() if len(d) > 1}
    por_registro = Counter()
    for documentos in numeros.values():
        for documento in documentos:
            por_registro[documento] += 1

    return {
        "metodo": metodo,
        "registros": len(registros),
        "numeros": len(numeros),
        "acertos": acertos,
        "erros": erros,
        "falsos": falsos,
        "ambiguos": ambiguos,
        "por_registro": por_registro,
    }


def imprimir(resultado: dict, detalhar: bool) -> None:
    acertos, erros = resultado["acertos"], resultado["erros"]
    total = len(acertos) + len(erros)

    print(f"\nregistros indexados : {resultado['registros']}")
    print(f"números no índice   : {resultado['numeros']}")

    contagens = list(resultado["por_registro"].values())
    if contagens:
        faltando = resultado["registros"] - len(contagens)
        print(
            f"números por registro: mediana {statistics.median(contagens):.0f}, "
            f"máx {max(contagens)}, sem nenhum número: {faltando}"
        )

    print(f"\n── Recall no gabarito ({total} citações real/jurisprudencia)")
    print(f"   resolve para o registro certo : {len(acertos)}/{total}")
    if total:
        print(f"   taxa                          : {len(acertos) / total:.1%}")

    por_tribunal = Counter(c["tribunal"] for c in erros)
    if por_tribunal:
        print(
            "   falhas por tribunal           : "
            + ", ".join(f"{t} {n}" for t, n in sorted(por_tribunal.items()))
        )

    empatados = [c for c in acertos if c["candidatos"] > 1]
    print(f"   acertos com empate (≥2 cand.) : {len(empatados)}")

    falsos = resultado["falsos"]
    print("\n── Falso positivo nas `inventada`  (o erro que a métrica pune com τ)")
    print(f"   inventada que acha candidato  : {len(falsos)}")
    for caso in falsos[:8]:
        print(
            f"     {caso['documento']}/{caso['citacao']}  numero={caso['numero']!r}"
            f"  -> {caso['candidatos']} registro(s)"
        )

    ambiguos = resultado["ambiguos"]
    print("\n── Ambiguidade na base inteira")
    print(f"   números com ≥2 registros      : {len(ambiguos)}")
    if ambiguos:
        maiores = sorted(ambiguos.items(), key=lambda kv: -len(kv[1]))[:5]
        for numero, documentos in maiores:
            print(f"     {numero:<24} {len(documentos)} registros")

    if detalhar and erros:
        print(f"\n── Os {len(erros)} casos que falham")
        for caso in erros:
            print(
                f"   [{caso['tribunal']}] {caso['documento']}/{caso['citacao']}"
                f"  numero={caso['numero']!r}  candidatos={caso['candidatos']}"
            )
            print(f"       trecho: {caso['trecho']!r}")
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=Path, default=Path("data/dev/desafio1_bracis.db"))
    p.add_argument("--goldenset", type=Path, default=Path("data/dev/goldenset.csv"))
    p.add_argument("--detalhar", action="store_true", help="lista os casos que falham")
    p.add_argument(
        "--metodo",
        choices=(*METODOS, "ambos"),
        default="ambos",
        help="qual extração da região medir (padrão: ambos, lado a lado)",
    )
    args = p.parse_args(argv)

    for caminho in (args.db, args.goldenset):
        if not caminho.exists():
            raise SystemExit(f"não encontrado: {caminho} (rode `make dados-kaggle`)")

    print(f"(mínimo de {MINIMO_DIGITOS} dígitos para entrar no índice)")
    metodos = list(METODOS) if args.metodo == "ambos" else [args.metodo]
    resultados = [medir(args.db, args.goldenset, m) for m in metodos]

    for resultado in resultados:
        print(f"\n{'═' * 62}\n  MÉTODO: {resultado['metodo']}\n{'═' * 62}")
        imprimir(resultado, args.detalhar)

    if len(resultados) > 1:
        comparar(resultados)
    return 0


def comparar(resultados: list[dict]) -> None:
    """O quadro lado a lado — é o que torna a troca uma decisão medida."""
    linhas = (
        (
            "recall no gabarito",
            lambda r: f"{len(r['acertos'])}/{len(r['acertos']) + len(r['erros'])}",
        ),
        ("falso positivo (inventada)", lambda r: str(len(r["falsos"]))),
        ("acórdãos sem número", lambda r: str(r["registros"] - len(r["por_registro"]))),
        ("números ambíguos (≥2)", lambda r: str(len(r["ambiguos"]))),
        ("números no índice", lambda r: str(r["numeros"])),
    )
    largura = max(len(nome) for nome, _ in linhas)
    print(f"\n{'═' * 62}\n  COMPARATIVO\n{'═' * 62}\n")
    print(f"{'':<{largura}}" + "".join(f"{r['metodo']:>16}" for r in resultados))
    for nome, extrair in linhas:
        print(f"{nome:<{largura}}" + "".join(f"{extrair(r):>16}" for r in resultados))
    print()


if __name__ == "__main__":
    raise SystemExit(main())
