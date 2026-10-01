"""Identidade dos diplomas legais (ex.: Lei 10.406/2002 é o Código Civil).

São fatos de direito, válidos para qualquer base; lei sem nome conhecido ganha
um código genérico pelo tipo e número (`LEI_9504`, `DL_1234`, `LC_135`).
"""

from __future__ import annotations

# (tipo, número sem pontos) -> código. A CF não tem número e fica fora daqui.
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

# Leis citadas pelo nome, levadas ao mesmo código da citação pelo número. Nomes
# em `chave_textual`, conferidos por contenção na ordem da tabela; sem ela, "Lei
# da Ação Civil Pública" cairia no marcador "civil" e viraria o Código Civil.
LEIS_POR_NOME: tuple[tuple[str, tuple[str, str], int], ...] = (
    ("estatuto da crianca e do adolescente", ("lei", "8069"), 1990),
    ("estatuto da pessoa idosa", ("lei", "10741"), 2003),
    ("estatuto do idoso", ("lei", "10741"), 2003),
    ("estatuto da pessoa com deficiencia", ("lei", "13146"), 2015),
    ("estatuto do desarmamento", ("lei", "10826"), 2003),
    ("estatuto da advocacia", ("lei", "8906"), 1994),
    ("estatuto da ordem dos advogados", ("lei", "8906"), 1994),
    ("estatuto da oab", ("lei", "8906"), 1994),
    ("lei de execucao penal", ("lei", "7210"), 1984),
    ("lei de introducao as normas do direito brasileiro", ("decreto-lei", "4657"), 1942),
    ("lei de introducao ao direito brasileiro", ("decreto-lei", "4657"), 1942),
    ("lei de introducao ao codigo civil", ("decreto-lei", "4657"), 1942),
    ("lei maria da penha", ("lei", "11340"), 2006),
    ("lei de drogas", ("lei", "11343"), 2006),
    ("lei antidrogas", ("lei", "11343"), 2006),
    ("lei das eleicoes", ("lei", "9504"), 1997),
    ("lei de improbidade", ("lei", "8429"), 1992),
    ("lei dos juizados especiais federais", ("lei", "10259"), 2001),
    ("lei dos juizados especiais da fazenda publica", ("lei", "12153"), 2009),
    ("lei dos juizados especiais", ("lei", "9099"), 1995),
    ("lei da acao civil publica", ("lei", "7347"), 1985),
    ("lei do mandado de seguranca", ("lei", "12016"), 2009),
    ("lei de execucao fiscal", ("lei", "6830"), 1980),
    ("lei de execucoes fiscais", ("lei", "6830"), 1980),
    ("lei dos crimes hediondos", ("lei", "8072"), 1990),
    ("nova lei de licitacoes", ("lei", "14133"), 2021),
    ("lei de licitacoes", ("lei", "8666"), 1993),
    ("lei das inelegibilidades", ("lei complementar", "64"), 1990),
    ("lei de inelegibilidade", ("lei complementar", "64"), 1990),
    ("lei da ficha limpa", ("lei complementar", "135"), 2010),
    ("lei organica da magistratura nacional", ("lei complementar", "35"), 1979),
    ("lei de responsabilidade fiscal", ("lei complementar", "101"), 2000),
)

# As siglas desses diplomas, que a detecção aceita sozinhas ("art. 47 da LEF").
SIGLAS_DE_LEI: dict[str, tuple[tuple[str, str], int]] = {
    "lep": (("lei", "7210"), 1984),
    "lindb": (("decreto-lei", "4657"), 1942),
    "lidb": (("decreto-lei", "4657"), 1942),
    "licc": (("decreto-lei", "4657"), 1942),
    "loman": (("lei complementar", "35"), 1979),
    "lrf": (("lei complementar", "101"), 2000),
    "lef": (("lei", "6830"), 1980),
}

# Ano de cada diploma, para recusar a versão revogada (`Código Civil de 1916`).
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

NUMERO_DA_LEI: dict[str, str] = {codigo: numero for (_, numero), codigo in LEIS_NOMEADAS.items()}

_PREFIXO_GENERICO = {"lei": "LEI", "decreto-lei": "DL", "lei complementar": "LC"}


def lei_pelo_nome(chave: str) -> tuple[str, int] | None:
    """O código e o ano da lei citada pelo nome ou pela sigla, se ela for conhecida."""
    for nome, (tipo, numero), ano in LEIS_POR_NOME:
        if nome in chave:
            return codigo_da_lei(tipo, numero), ano
    for sigla, ((tipo, numero), ano) in SIGLAS_DE_LEI.items():
        if chave == sigla or chave.startswith(sigla + " ") or chave.startswith(sigla + "/"):
            return codigo_da_lei(tipo, numero), ano
    return None


def codigo_da_lei(tipo: str, numero: str) -> str:
    """O código do diploma pelo tipo e pelo número, nomeado ou genérico."""
    numero = numero.replace(".", "").lstrip("0") or "0"
    return LEIS_NOMEADAS.get((tipo, numero)) or f"{_PREFIXO_GENERICO[tipo]}_{numero}"
