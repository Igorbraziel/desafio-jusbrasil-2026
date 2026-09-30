"""Identidade dos diplomas legais: fatos de direito, não da base.

A tabela de dispositivos da cobertura é construída do banco recebido em
execução (ver :func:`verificador.base_canonica.construir_indice`), e cada
registro se autodeclara na primeira linha ("Artigo 186 da Lei nº 10.406, de 10
de janeiro de 2002"). Para ligar essa linha ao nome com que a prosa cita o
diploma ("Código Civil", "CC"), é preciso saber que a Lei 10.406/2002 **é** o
Código Civil. Isso é fato de direito brasileiro e vale para qualquer base; o que
a base decide é só quais artigos estão na cobertura.

Lei que não tem nome conhecido aqui não fica de fora: ganha um código genérico
pelo tipo e pelo número (`LEI_9504`, `DL_1234`, `LC_135`), e a citação que a
nomeia pelo número resolve contra ela do mesmo jeito.
"""

from __future__ import annotations

# (tipo, número sem pontos) -> código. O tipo é "lei", "decreto-lei" ou
# "lei complementar". A CF não tem número e fica fora desta tabela: é "CF".
LEIS_NOMEADAS: dict[tuple[str, str], str] = {
    ("lei", "13105"): "CPC",
    ("decreto-lei", "3689"): "CPP",
    ("decreto-lei", "1001"): "CPM",
    ("decreto-lei", "1002"): "CPPM",
    ("decreto-lei", "2848"): "CP",
    ("decreto-lei", "5452"): "CLT",
    ("lei", "8078"): "CDC",
    ("lei", "10406"): "CC",
    ("lei", "4737"): "ELEITORAL",
    ("lei complementar", "64"): "LC64",
    ("lei", "5172"): "CTN",
    ("lei", "8069"): "ECA",
    ("lei", "9503"): "CTB",
}

# Ano de cada diploma nomeado. Serve para recusar a versão revogada, que tem os
# mesmos números de artigo: `Código Civil de 1916`, `CPC/73`.
ANO_DA_LEI: dict[str, int] = {
    "CF": 1988,
    "CPC": 2015,
    "CPP": 1941,
    "CPM": 1969,
    "CPPM": 1969,
    "CP": 1940,
    "CDC": 1990,
    "CLT": 1943,
    "LC64": 1990,
    "ELEITORAL": 1965,
    "CC": 2002,
    "CTN": 1966,
    "ECA": 1990,
    "CTB": 1997,
}

# Número de cada diploma nomeado, o inverso de `LEIS_NOMEADAS`.
NUMERO_DA_LEI: dict[str, str] = {codigo: numero for (_, numero), codigo in LEIS_NOMEADAS.items()}

_PREFIXO_GENERICO = {"lei": "LEI", "decreto-lei": "DL", "lei complementar": "LC"}


def codigo_da_lei(tipo: str, numero: str) -> str:
    """O código do diploma pelo tipo e pelo número, nomeado ou genérico."""
    numero = numero.replace(".", "").lstrip("0") or "0"
    return LEIS_NOMEADAS.get((tipo, numero)) or f"{_PREFIXO_GENERICO[tipo]}_{numero}"
