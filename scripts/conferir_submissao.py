"""Confere o submission.csv antes de enviá-lo ao Kaggle.

O avaliador oficial não tira pontos por erro de formato: ele rejeita a
submissão inteira (`ParticipantVisibleError`). Esta conferência roda as mesmas
checagens que o `kaggle_metric.py` faz, com a lista de documentos esperados
lida do `sample_submission.csv` — o único arquivo que diz quais documentos o
conjunto em avaliação tem.

- todo documento esperado tem linha;
- cada citação tem cinco campos, span válido e classe conhecida;
- citação `real` tem `id_canonico` só com dígitos;
- confiança, quando presente, está em [0, 1];
- nenhum par de citações do mesmo documento tem IoU ≥ 0,5.

Uso:
    python scripts/conferir_submissao.py data/submission.csv data/dev/sample_submission.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

CLASSES = {"real", "inventada", "incompleta"}
IOU_MIN = 0.5


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    return inter / ((a[1] - a[0]) + (b[1] - b[0]) - inter) if inter else 0.0


def _conferir_celula(documento: str, celula: str) -> list[str]:
    problemas: list[str] = []
    celula = (celula or "").strip()
    if celula in ("", "-"):
        return problemas
    spans: list[tuple[int, int]] = []
    for i, bloco in enumerate(celula.split("|"), start=1):
        campos = [c.strip() for c in bloco.split(",")]
        onde = f"{documento} citação {i}"
        if len(campos) != 5:
            problemas.append(f"{onde}: {len(campos)} campos, esperados 5")
            continue
        inicio, fim, classe, id_canonico, confianca = campos
        if not (inicio.isdigit() and fim.isdigit()) or int(fim) <= int(inicio):
            problemas.append(f"{onde}: span inválido ({inicio}, {fim})")
            continue
        if classe not in CLASSES:
            problemas.append(f"{onde}: classe inválida {classe!r}")
        if classe == "real" and not id_canonico.isdigit():
            problemas.append(f"{onde}: real sem id_canonico numérico ({id_canonico!r})")
        if confianca not in ("", "-"):
            try:
                valor = float(confianca)
            except ValueError:
                problemas.append(f"{onde}: confiança não numérica {confianca!r}")
            else:
                if not 0.0 <= valor <= 1.0:
                    problemas.append(f"{onde}: confiança fora de [0, 1] ({valor})")
        spans.append((int(inicio), int(fim)))
    for a in range(len(spans)):
        for b in range(a + 1, len(spans)):
            if _iou(spans[a], spans[b]) >= IOU_MIN:
                problemas.append(f"{documento}: citações {a + 1} e {b + 1} com IoU ≥ {IOU_MIN}")
    return problemas


def conferir(submissao: Path, esperados: set[str]) -> list[str]:
    """Devolve a lista de problemas; vazia quando a submissão pode ser enviada."""
    with submissao.open(encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    presentes = {linha["documento_id"] for linha in linhas}
    problemas = [f"documento sem linha: {d}" for d in sorted(esperados - presentes)]
    for linha in linhas:
        problemas.extend(_conferir_celula(linha["documento_id"], linha["citacoes"]))
    return problemas


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print(__doc__.split("Uso:")[1].strip(), file=sys.stderr)
        return 2
    submissao, amostra = Path(args[0]), Path(args[1])
    with amostra.open(encoding="utf-8", newline="") as arquivo:
        esperados = {linha["documento_id"] for linha in csv.DictReader(arquivo)}
    problemas = conferir(submissao, esperados)
    for problema in problemas:
        print(f"  ✗ {problema}")
    if problemas:
        print(f"{len(problemas)} problema(s): a submissão seria rejeitada.")
        return 1
    print(f"{submissao}: {len(esperados)} documentos, formato conferido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
