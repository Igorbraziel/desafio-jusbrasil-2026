"""A calibração conta o que o Brier oficial conta: só pares casados.

O bônus de calibração da métrica só considera predições casadas com o gabarito.
Contar a predição sem par como erro puxava a acurácia medida para baixo, e a
tabela `CONFIANCA` deixava de ser reproduzível por `make confianca`.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import medir_confianca  # noqa: E402

from verificador.base.canonica import BaseCanonica  # noqa: E402

BASE_VAZIA = BaseCanonica({"numeros": {}, "registros": {}})


def test_predicao_sem_par_nao_entra_na_acuracia(tmp_path):
    pasta = tmp_path / "txt"
    pasta.mkdir()
    texto = (
        "PARECER\n\nA defesa invoca o REsp 9.999.991/SP no ponto, e ainda o REsp "
        "8.888.881/RJ, que não está no gabarito.\n"
    )
    (pasta / "d.txt").write_text(texto, encoding="utf-8")
    inicio = texto.index("REsp 9.999.991/SP")
    gabarito = tmp_path / "goldenset.csv"
    gabarito.write_text(
        "nivel,documento_id,citacao_id,inicio,fim,trecho,tipo,classificacao,id_canonico\n"
        f"1,d,g1,{inicio},{inicio + len('REsp 9.999.991/SP')},REsp 9.999.991/SP,"
        "jurisprudencia,inventada,\n",
        encoding="utf-8",
    )
    contagem = medir_confianca.medir(BASE_VAZIA, pasta, gabarito)
    assert contagem == {"inventada_processo": (1, 1)}
