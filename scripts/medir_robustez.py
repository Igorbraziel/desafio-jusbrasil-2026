"""Mede quanto o pipeline degrada sob cada classe de ruído.

O score de 1,0988 no conjunto de desenvolvimento é o teto do que essa amostra
consegue mostrar, e todas as regras de ``deteccao.py`` foram derivadas dela.
Este script responde à pergunta que a amostra não responde: **o que quebra
primeiro quando o ruído passa do que já vimos?**

Cada classe de ruído é medida isolada, e é isso que torna a saída acionável —
um agregado que cai de 1,09 para 0,90 não diz o que consertar.

A comparação é sempre contra o gabarito **traduzido** para o texto perturbado
(ver ``scripts/perturbar.py``), nunca contra o original: os offsets mudam, e
medir contra o gabarito antigo puniria o detector por acertar.

**Sanidade obrigatória.** Com ``--taxa 0`` o resultado tem de reproduzir o score
de referência exatamente. Se não reproduzir, o defeito está no mapa de offsets
do perturbador, e toda medição seguinte estaria medindo o arnês.

Uso:
    python scripts/medir_robustez.py --taxa 0      # sanidade
    python scripts/medir_robustez.py               # todas as classes
    python scripts/medir_robustez.py --classe ocr_numero --sementes 5
"""

from __future__ import annotations

import argparse
import json
import shutil
import signal
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from avaliar import avaliar  # noqa: E402
from perturbar import CLASSES, gerar_corpus  # noqa: E402

from verificador.base_canonica import BaseCanonica  # noqa: E402
from verificador.pipeline import processar_arquivo  # noqa: E402

# Backtracking catastrófico já aconteceu duas vezes neste código — 41 s na
# cadeia de prefixo e travamento no qualificador de dispositivo. Sob perturbação
# a superfície aumenta, e um arnês sem timeout trava em silêncio.
TIMEOUT_POR_DOCUMENTO = 20


class Estourou(Exception):
    pass


def _alarme(*_):
    raise Estourou()


def _processar_com_timeout(entrada: Path, saida: Path, base: BaseCanonica) -> list[str]:
    """Roda o pipeline documento a documento. Devolve os que estouraram o tempo."""
    saida.mkdir(parents=True, exist_ok=True)
    estourados: list[str] = []
    anterior = signal.signal(signal.SIGALRM, _alarme)
    try:
        for caminho in sorted(entrada.glob("*.txt")):
            signal.setitimer(signal.ITIMER_REAL, TIMEOUT_POR_DOCUMENTO)
            try:
                processar_arquivo(caminho, base).escrever(saida)
            except Estourou:
                estourados.append(caminho.stem)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    finally:
        signal.signal(signal.SIGALRM, anterior)
    return estourados


def medir_uma(
    classes: list[str],
    taxa: float,
    semente: int,
    base: BaseCanonica,
    trabalho: Path,
) -> dict:
    """Gera o corpus perturbado, roda o pipeline e pontua pela métrica oficial."""
    destino = trabalho / f"{'+'.join(classes)}-{semente}"
    if destino.exists():
        shutil.rmtree(destino)
    gerar_corpus(
        RAIZ / "data/dev/txt", RAIZ / "data/dev/goldenset.csv", destino, classes, taxa, semente
    )

    saida = destino / "out"
    estourados = _processar_com_timeout(destino / "txt", saida, base)
    resultado = avaliar(saida, destino / "goldenset.csv")

    return {
        "classes": classes,
        "taxa": taxa,
        "semente": semente,
        "score": resultado["score_final"],
        "niveis": {
            str(n): {"macro_f1": d["macro_f1"], "tau": d["tau"]}
            for n, d in resultado["niveis"].items()
        },
        "estourados": estourados,
        "diagnostico": resultado["diagnostico"],
    }


def _erros_principais(diagnostico: dict, quantos: int = 3) -> str:
    """Os erros mais frequentes, somados nos dois níveis."""
    from collections import Counter

    total: Counter = Counter()
    for acumulado in diagnostico.values():
        for par, n in acumulado.get("confusao", {}).items():
            if par[0] != par[1] and n > 0:
                total[par] += n
    if not total:
        return "—"
    return ", ".join(f"{a}→{b}: {n}" for (a, b), n in total.most_common(quantos))


def imprimir(resultados: list[dict], referencia: float) -> None:
    print(f"\n{'classe':<24}{'score':>8}{'Δ':>9}{'τ N1':>7}{'τ N2':>7}  erros principais")
    print("─" * 100)
    for r in sorted(resultados, key=lambda r: r["score"]):
        nome = "+".join(r["classes"]) if len(r["classes"]) < 3 else f"todas ({len(r['classes'])})"
        tau1 = r["niveis"].get("1", {}).get("tau", 0.0)
        tau2 = r["niveis"].get("2", {}).get("tau", 0.0)
        delta = r["score"] - referencia
        aviso = "  ⏱ " + ",".join(r["estourados"]) if r["estourados"] else ""
        print(
            f"{nome:<24}{r['score']:>8.4f}{delta:>+9.4f}{tau1:>7.2f}{tau2:>7.2f}  "
            f"{_erros_principais(r['diagnostico'])}{aviso}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--classe", action="append", choices=CLASSES, help="repetível; padrão: cada uma")
    p.add_argument("--taxa", type=float, default=0.4)
    p.add_argument("--sementes", type=int, default=1)
    p.add_argument("--indice", type=Path, default=RAIZ / "data/dev/indice_cabecalhos.json")
    p.add_argument("--trabalho", type=Path, default=RAIZ / "data/perturbado")
    p.add_argument("--json", type=Path, default=None, help="grava o resultado bruto")
    args = p.parse_args(argv)

    if not args.indice.exists():
        raise SystemExit(f"índice não encontrado: {args.indice} (rode `make indice`)")

    referencia = 0.0
    caminho_base = RAIZ / "data/dev/baseline.json"
    if caminho_base.exists():
        referencia = json.loads(caminho_base.read_text(encoding="utf-8"))["score_final"]

    base = BaseCanonica.de_arquivo(args.indice)
    # Cada classe sozinha, mais a combinação de todas — que é o cenário pessimista.
    grupos = [[c] for c in (args.classe or CLASSES)]
    if not args.classe:
        grupos.append(list(CLASSES))

    resultados = []
    for grupo in grupos:
        for semente in range(1, args.sementes + 1):
            resultado = medir_uma(grupo, args.taxa, semente, base, args.trabalho)
            resultados.append(resultado)
            print(f"  medido: {'+'.join(grupo):<40} semente {semente} -> {resultado['score']:.4f}")

    print(f"\nreferência (sem ruído): {referencia:.4f}   taxa: {args.taxa}")
    imprimir(resultados, referencia)

    if args.json:
        args.json.write_text(
            json.dumps(
                [{k: v for k, v in r.items() if k != "diagnostico"} for r in resultados],
                indent=2,
                default=float,
            ),
            encoding="utf-8",
        )
        print(f"resultado bruto -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
