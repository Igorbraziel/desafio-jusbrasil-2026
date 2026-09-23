"""Conta os spans que a detecção produz em texto jurídico real, por família.

O arnês de `medir_robustez.py` degrada os 26 documentos sintéticos, e por isso só
mede o ruído que o gerador sabe produzir sobre a prosa que o gerador escreveu.
Esta é a outra metade: os 996 acórdãos da base canônica são texto de tribunal de
verdade, muito mais heterogêneo, e nenhuma regra de `deteccao.py` foi derivada
deles.

Não há gabarito para eles, então o número aqui não é precisão — é **volume por
família**, comparável entre versões do código. Uma mudança que afrouxe uma
expressão aparece como salto numa família; uma mudança neutra deixa a tabela
igual. Foi assim que apareceram os falsos positivos do checkpoint 07 (`logo`
lido como ano, inscrição na OAB lida como processo).

Só o começo de cada acórdão entra — o tamanho de um parecer do desafio —, e a
amostra é fixa por semente, para que duas execuções comparem o mesmo texto.

Uso:
    python scripts/medir_espurias.py                 # 200 acórdãos, semente 0
    python scripts/medir_espurias.py --amostra 996   # a base inteira
    python scripts/medir_espurias.py --exemplos vaga # mostra os spans de uma família
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from verificador.deteccao import FAMILIAS, detectar  # noqa: E402

# O tamanho médio de um documento do desafio é de ~3.400 caracteres.
JANELA = 4000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", type=Path, default=RAIZ / "data/dev/desafio1_bracis.db")
    parser.add_argument("--amostra", type=int, default=200)
    parser.add_argument("--semente", type=int, default=0)
    parser.add_argument("--exemplos", choices=FAMILIAS, help="lista os spans desta família")
    args = parser.parse_args()

    conexao = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        linhas = conexao.execute(
            "SELECT documento_id, tribunal, texto FROM documentos "
            "WHERE natureza = 'acordao' ORDER BY documento_id"
        ).fetchall()
    finally:
        conexao.close()

    amostra = random.Random(args.semente).sample(linhas, min(args.amostra, len(linhas)))
    por_familia: Counter[str] = Counter()
    por_tribunal: Counter[str] = Counter()
    for documento_id, tribunal, texto in amostra:
        for achado in detectar(texto[:JANELA]):
            por_familia[achado.familia] += 1
            por_tribunal[tribunal] += 1
            if args.exemplos == achado.familia:
                print(f"  {documento_id} {tribunal}  {achado.trecho[:90]!r}")

    print(f"\n{len(amostra)} acórdãos, {JANELA} caracteres cada, semente {args.semente}\n")
    for familia in FAMILIAS:
        print(f"  {familia:12s} {por_familia[familia]:5d}")
    print(f"  {'total':12s} {sum(por_familia.values()):5d}\n")
    for tribunal, n in sorted(por_tribunal.items()):
        print(f"  {tribunal:12s} {n:5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
