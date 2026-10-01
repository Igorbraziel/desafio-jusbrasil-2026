"""Leitura da primeira linha de súmulas e dispositivos em variações de formato.

O banco da avaliação final é outro; uma variação pequena na linha de
identificação não pode tirar o registro da cobertura.
"""

import pytest

from verificador.base.canonica import dispositivo_do_registro, sumula_do_registro


@pytest.mark.parametrize(
    ("texto", "tribunal", "esperado"),
    [
        ("Súmula n. 83 do STJ", None, ("STJ", False, 83)),
        ("Súmula n.º 600 do STJ", None, ("STJ", False, 600)),
        ("Súmula nº 600 do STJ", None, ("STJ", False, 600)),
        ("﻿Súmula n. 83 do STJ", None, ("STJ", False, 83)),
        ("SÚMULA 12 DO TST", None, ("TST", False, 12)),
        ("Súmula n. 77 do TRF1", None, ("TRF1", False, 77)),
        ("Súmula 12 do TJSP", None, ("TJSP", False, 12)),
        ("Súmula n. 5 do Superior Tribunal de Justiça", None, ("STJ", False, 5)),
        ("Súmula Vinculante n. 10", None, ("STF", True, 10)),
        ("Súmula n. 7", "stj", ("STJ", False, 7)),
    ],
)
def test_sumula(texto, tribunal, esperado):
    assert sumula_do_registro(texto, tribunal) == esperado


def test_sumula_sem_tribunal_fica_fora():
    assert sumula_do_registro("Súmula n. 7", None) is None


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Artigo 186 da Lei nº 10.406, de 10 de janeiro de 2002", ("CC", "186", "10406", 2002)),
        ("Artigo 186 da Lei n.º 10.406, de 10 de janeiro de 2002", ("CC", "186", "10406", 2002)),
        ("Art. 186 da Lei 10.406/2002", ("CC", "186", "10406", 2002)),
        ("Artigo 1º da Lei n. 9.999/1999", ("LEI_9999", "1", "9999", 1999)),
        ("Artigo 37, caput, da Constituição Federal", ("CF", "37", None, 1988)),
        ("Artigo 5º, inciso LV, da Constituição Federal de 1988", ("CF", "5", None, 1988)),
        ("Artigo 10 da CF", ("CF", "10", None, 1988)),
        ("Artigo 10 da CF/88", ("CF", "10", None, 1988)),
        ("﻿Artigo 896-A da Lei nº 13.105, de 2015", ("CPC", "896-A", "13105", 2015)),
    ],
)
def test_dispositivo(texto, esperado):
    assert dispositivo_do_registro(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Artigo 5 da Constituição do Estado de São Paulo",
        "Artigo 10 da Constituição Federal de 1967",
        "Artigo 1º da Emenda Constitucional nº 45",
    ],
)
def test_dispositivo_fora_do_repertorio(texto):
    assert dispositivo_do_registro(texto) is None


def _citacoes(texto, base):
    from verificador.pipeline import processar_texto

    return [(c.trecho, c.classificacao) for c in processar_texto("x", texto, base).citacoes]


def test_ano_por_extenso_da_lei_numerada_e_conferido(tmp_path):
    import sqlite3

    from verificador.base import BaseCanonica

    banco = tmp_path / "base.db"
    with sqlite3.connect(banco) as con:
        con.execute(
            "CREATE TABLE documentos (documento_id TEXT, id INTEGER, tribunal TEXT, "
            "natureza TEXT, tipo TEXT, texto TEXT, texto_len INTEGER)"
        )
        texto = "Artigo 5 da Lei nº 9.999, de 1 de janeiro de 1999\nArt. 5. Texto."
        con.execute(
            "INSERT INTO documentos VALUES ('d1', 990000001, NULL, 'dispositivo', 'lei', ?, ?)",
            (texto, len(texto)),
        )
    base = BaseCanonica.de_banco(banco)
    assert _citacoes("PARECER\n\nO art. 5º da Lei nº 9.999, de 1999, aplica-se.\n", base) == [
        ("art. 5º da Lei nº 9.999", "real")
    ]
    assert _citacoes("PARECER\n\nO art. 5º da Lei nº 9.999, de 2000, aplica-se.\n", base) == [
        ("art. 5º da Lei nº 9.999", "inventada")
    ]
    assert _citacoes(
        "PARECER\n\nO art. 5º da Lei nº 9.999, de 1º de janeiro de 1999, aplica-se.\n", base
    ) == [("art. 5º da Lei nº 9.999", "real")]
