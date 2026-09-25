"""A conferência do submission.csv antes de ir para o Kaggle.

Documento sem linha, citação real sem id ou duas citações com IoU ≥ 0,5 no
mesmo documento fazem o avaliador oficial rejeitar a submissão inteira. A
conferência roda as mesmas checagens localmente, antes de gastar uma das cinco
submissões diárias da equipe.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from conferir_submissao import conferir  # noqa: E402


def _csv(tmp_path, linhas):
    caminho = tmp_path / "submission.csv"
    caminho.write_text("documento_id,citacoes\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def test_submissao_completa_passa(tmp_path):
    sub = _csv(tmp_path, ['a,"10,20,real,123,0.99|30,40,inventada,-,0.98"', "b,-"])
    assert conferir(sub, {"a", "b"}) == []


def test_documento_sem_linha_e_problema(tmp_path):
    sub = _csv(tmp_path, ["a,-"])
    assert any("b" in p for p in conferir(sub, {"a", "b"}))


def test_real_sem_id_e_problema(tmp_path):
    sub = _csv(tmp_path, ['a,"10,20,real,-,0.99"'])
    assert conferir(sub, {"a"})


def test_spans_sobrepostos_sao_problema(tmp_path):
    sub = _csv(tmp_path, ['a,"10,20,real,123,0.99|11,20,inventada,-,0.98"'])
    assert conferir(sub, {"a"})
