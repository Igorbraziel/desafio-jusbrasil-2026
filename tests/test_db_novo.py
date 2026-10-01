"""A avaliação final roda sobre outro banco: a cobertura precisa vir dele.

A organização avisou (30/09/2026) que o conjunto final usa um `.db` novo. Com a
tabela de súmulas e dispositivos fixa no código, a súmula que o banco novo tem
saía `inventada`, e a que só a tabela tinha saía `real` — o erro grave da
métrica. Aqui o banco de dev é copiado e alterado: súmulas e dispositivos saem e
entram, e as classes têm de acompanhar o banco, não o código.
"""

import shutil
import sqlite3

import pytest
from conftest import BANCO, sem_dados

from verificador.base_canonica import BaseCanonica
from verificador.pipeline import processar_texto

pytestmark = sem_dados

CABECALHO = "MINISTÉRIO PÚBLICO FEDERAL\n\nAutos nº 4309330-25.2016.3.05.9083\n\nPARECER\n\n"
INICIO = "Cuida-se de recurso especial, que ora se examina, interposto contra acórdão regional.\n"

NOVOS = [
    ("990000007", "STJ", "sumula", "Súmula n. 7 do STJ\nDIREITO PROCESSUAL CIVIL\nA pretensão."),
    (
        "990000927",
        None,
        "dispositivo",
        "Artigo 927 da Lei nº 13.105, de 16 de março de 2015\nArt. 927. Os juízes observarão:",
    ),
    (
        "990041001",
        None,
        "dispositivo",
        "Artigo 41-A da Lei nº 9.504, de 30 de setembro de 1997\nArt. 41-A. Ressalvado o disposto",
    ),
    (
        "990000312",
        None,
        "dispositivo",
        "Artigo 312 do Decreto-Lei nº 1.002, de 21 de outubro de 1969\nArt. 312. A prisão.",
    ),
    (
        "990000098",
        None,
        "dispositivo",
        "Artigo 98 da Lei nº 8.069, de 13 de julho de 1990\nArt. 98. As medidas de proteção.",
    ),
    (
        "990000066",
        None,
        "dispositivo",
        "Artigo 66 da Lei nº 7.210, de 11 de julho de 1984\nArt. 66. Compete ao Juiz.",
    ),
]


@pytest.fixture(scope="module")
def base_nova(tmp_path_factory):
    caminho = tmp_path_factory.mktemp("db") / "novo.db"
    shutil.copy(BANCO, caminho)
    conexao = sqlite3.connect(caminho)
    # saem a Súmula 83/STJ e o art. 14 do CDC
    conexao.execute(
        "DELETE FROM documentos WHERE natureza != 'acordao' AND "
        "(texto LIKE 'Súmula n. 83 do STJ%' OR texto LIKE 'Artigo 14 da Lei nº 8.078%')"
    )
    for id_canonico, tribunal, natureza, texto in NOVOS:
        conexao.execute(
            "INSERT INTO documentos (documento_id, id, tribunal, natureza, tipo, texto, texto_len) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                id_canonico,
                int(id_canonico),
                tribunal,
                natureza,
                "jurisprudencia" if natureza == "sumula" else "lei",
                texto,
                len(texto),
            ),
        )
    conexao.commit()
    conexao.close()
    return BaseCanonica.de_banco(caminho)


@pytest.mark.parametrize(
    ("citacao", "classe", "id_canonico"),
    [
        # entrou no banco: real, com o id do banco novo
        ("a Súmula 7 do STJ", "real", 990000007),
        ("o art. 927 do CPC", "real", 990000927),
        ("o art. 41-A da Lei nº 9.504/1997", "real", 990041001),
        ("o art. 312 do Código de Processo Penal Militar", "real", 990000312),
        # saiu do banco: inventada, mesmo estando na cobertura do dev
        ("a Súmula 83 do STJ", "inventada", None),
        ("o art. 14 do CDC", "inventada", None),
        # o que o banco novo não tem continua inventada
        ("o art. 41 da Lei nº 9.504/1997", "inventada", None),
        ("o art. 313 do CPPM", "inventada", None),
        # o CPPM no banco não vaza para o CPP, que continua com o próprio registro
        ("o art. 312 do CPP", "real", 10652044),
        # lei citada pelo nome ou pela sigla resolve contra o registro do número dela
        ("o art. 98 do Estatuto da Criança e do Adolescente", "real", 990000098),
        ("o art. 98 do ECA", "real", 990000098),
        ("o art. 66 da Lei de Execução Penal", "real", 990000066),
        ("o art. 66 da LEP", "real", 990000066),
        ("o art. 67 da Lei de Execução Penal", "inventada", None),
        # nome que contém "civil" não é o Código Civil, e código estrangeiro também não
        ("o art. 186 da Lei da Ação Civil Pública", "inventada", None),
        ("o art. 186 da Lei de Introdução ao Código Civil", "inventada", None),
        ("o art. 186 do Código Civil Português", "inventada", None),
        ("o art. 186 do Código Civil", "real", 10718759),
        # a Lei de Inelegibilidade é a LC 64/1990
        ("o art. 1º da Lei de Inelegibilidade", "real", 11304039),
    ],
)
def test_classe_acompanha_o_banco_recebido(base_nova, citacao, classe, id_canonico):
    texto = CABECALHO + INICIO + f"Nesse sentido, incide {citacao}, no ponto.\n"
    achados = processar_texto("x", texto, base_nova).citacoes
    assert [(c.classificacao, c.id_canonico) for c in achados] == [(classe, id_canonico)]
