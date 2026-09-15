"""As tabelas curadas de súmulas e dispositivos precisam bater com o banco.

São 18 registros escritos à mão em `base_canonica.py`, de quando o texto deles
era só o enunciado e não dizia qual súmula era nem de que código vinha o artigo.
Desde 15/09/2026 a base traz essa identificação na primeira linha de cada um, o
que torna a tabela derivável — ver docs/dados.md. Até que se derive, estes
testes são a rede de segurança da curadoria: se a base mudar, eles quebram.
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
    # utf-8-sig: o gabarito passou a vir com BOM em 15/09 — ver docs/dados.md.
    with GOLDENSET.open(encoding="utf-8-sig") as arquivo:
        esperados = {
            int(linha["id_canonico"])
            for linha in csv.DictReader(arquivo)
            if linha["classificacao"] == "real"
            and linha["id_canonico"]
            and int(linha["id_canonico"]) in conhecidos
        }
    # Os 13 dispositivos e as 5 súmulas da cobertura são todos citados no dev.
    assert len(esperados) == len(conhecidos)
