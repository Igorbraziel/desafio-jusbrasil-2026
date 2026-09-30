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

As checagens moram em `verificador.submissao`, que o `run.sh` da entrega também
usa: a conferência daqui e a da entrega não têm como divergir.

Uso:
    python scripts/conferir_submissao.py data/submission.csv data/dev/sample_submission.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from verificador.submissao import check_submission  # noqa: E402


def conferir(submissao: Path, esperados: set[str]) -> list[str]:
    """Devolve a lista de problemas; vazia quando a submissão pode ser enviada."""
    return check_submission(submissao, esperados)


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
