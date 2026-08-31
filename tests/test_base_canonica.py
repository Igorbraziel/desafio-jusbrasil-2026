"""As tabelas curadas de súmulas e dispositivos precisam bater com o banco.

São 18 registros escritos à mão em `base_canonica.py`, porque o texto deles é o
enunciado e não contém o número da súmula nem o nome do código. Estes testes são
a rede de segurança dessa curadoria: se a base mudar, eles quebram.
"""

import csv
import sqlite3

from conftest import BANCO, GOLDENSET, sem_dados

from verificador.base_canonica import DISPOSITIVOS, SUMULAS

pytestmark = sem_dados


def _ids_por_natureza(natureza: str) -> set[int]:
    conexao = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    try:
        return {
            linha[0]
            for linha in conexao.execute(
                "SELECT id FROM documentos WHERE natureza = ?", (natureza,)
            )
        }
    finally:
        conexao.close()


def test_tabela_de_sumulas_cobre_a_base():
    assert set(SUMULAS.values()) == _ids_por_natureza("sumula")


def test_tabela_de_dispositivos_cobre_a_base():
    assert set(DISPOSITIVOS.values()) == _ids_por_natureza("dispositivo")


def test_tabelas_conferem_com_o_gabarito():
    """Toda citação `real` de lei ou súmula do gabarito resolve pelas tabelas."""
    conhecidos = set(SUMULAS.values()) | set(DISPOSITIVOS.values())
    esperados = {
        int(linha["id_canonico"])
        for linha in csv.DictReader(GOLDENSET.open(encoding="utf-8"))
        if linha["classificacao"] == "real"
        and linha["id_canonico"]
        and int(linha["id_canonico"]) in conhecidos
    }
    assert len(esperados) >= 15  # 14 dispositivos + 5 súmulas citados no dev
