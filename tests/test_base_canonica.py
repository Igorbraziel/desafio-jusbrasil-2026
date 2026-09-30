"""A tabela de súmulas e dispositivos sai do banco recebido, e reproduz a curada.

Até 30/09/2026 eram 18 registros escritos à mão em `base_canonica.py`. A
avaliação final usa outro banco, então a tabela passou a ser lida da primeira
linha de cada registro ("Súmula n. 83 do STJ", "Artigo 186 da Lei nº 10.406, de
10 de janeiro de 2002"). No banco de desenvolvimento, a tabela lida tem de ser
idêntica à curada — que continua aqui como referência (`conftest.py`).
"""

import csv
import sqlite3

import pytest
from conftest import BANCO, DISPOSITIVOS, GOLDENSET, SUMULAS, sem_dados

from verificador.base_canonica import dispositivo_do_registro, sumula_do_registro


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


@sem_dados
def test_tabela_lida_do_banco_reproduz_a_curada(base_canonica):
    assert base_canonica.sumulas == SUMULAS
    assert base_canonica.dispositivos == {(c, str(a)): i for (c, a), i in DISPOSITIVOS.items()}


@sem_dados
def test_tabela_de_sumulas_cobre_a_base():
    assert set(SUMULAS.values()) == _ids_por_natureza("sumula")


@sem_dados
def test_tabela_de_dispositivos_cobre_a_base():
    assert set(DISPOSITIVOS.values()) == _ids_por_natureza("dispositivo")


@sem_dados
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


@pytest.mark.parametrize(
    ("texto", "tribunal", "esperado"),
    [
        ("Súmula n. 83 do STJ\nDIREITO PROCESSUAL CIVIL", "STJ", ("STJ", False, 83)),
        ("Súmula Vinculante n. 10 do STF\nPROCESSUAL CIVIL", "STF", ("STF", True, 10)),
        ("Súmula nº 7 do STJ\nRECURSO ESPECIAL", None, ("STJ", False, 7)),
        # sem a sigla na linha, vale a coluna `tribunal`
        ("Súmula 126\nTexto do enunciado", "TST", ("TST", False, 126)),
        ("Enunciado qualquer sem identificação", "STJ", None),
    ],
)
def test_sumula_lida_do_registro(texto, tribunal, esperado):
    assert sumula_do_registro(texto, tribunal) == esperado


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "Artigo 276 da Lei nº 4.737, de 15 de julho de 1965\nArt. 276.",
            ("ELEITORAL", "276", "4737", 1965),
        ),
        ("Artigo 93 da Constituição Federal de 1988\nArt. 93.", ("CF", "93", None, 1988)),
        (
            "Artigo 1º da Lei Complementar nº 64, de 18 de maio de 1990\nArt. 1º",
            ("LC64", "1", "64", 1990),
        ),
        (
            "Artigo 896 do Decreto-Lei nº 5.452, de 1º de maio de 1943\nArt. 896",
            ("CLT", "896", "5452", 1943),
        ),
        # lei sem nome conhecido ganha código genérico; o sufixo vai na chave
        (
            "Artigo 41-A da Lei nº 9.504, de 30 de setembro de 1997\nArt. 41-A.",
            ("LEI_9504", "41-A", "9504", 1997),
        ),
        (
            "Artigo 1.021 da Lei nº 13.105, de 16 de março de 2015\nArt. 1.021.",
            ("CPC", "1021", "13105", 2015),
        ),
        (
            "Artigo 312 do Decreto-Lei nº 1.002, de 21 de outubro de 1969\nArt. 312.",
            ("CPPM", "312", "1002", 1969),
        ),
        # constituição que não é a federal de 1988 fica fora: é o lado seguro
        ("Artigo 5º da Constituição do Estado de São Paulo\nArt. 5º", None),
        ("Artigo 5º da Constituição Federal de 1967\nArt. 5º", None),
    ],
)
def test_dispositivo_lido_do_registro(texto, esperado):
    assert dispositivo_do_registro(texto) == esperado
