"""Fixtures compartilhadas.

Os dados do desafio não estão no repositório (ver docs/dados.md). Os testes que
dependem deles são pulados quando `data/dev/` não existe, para que a suíte rode
num clone limpo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
DEV = RAIZ / "data" / "dev"
BANCO = DEV / "desafio1_bracis.db"
GOLDENSET = DEV / "goldenset.csv"
INDICE = DEV / "indice_cabecalhos.json"


sem_dados = pytest.mark.skipif(
    not BANCO.exists(), reason="dados do desafio ausentes — rode `make dados`"
)
sem_indice = pytest.mark.skipif(
    not BANCO.exists() and not INDICE.exists(),
    reason="nem banco nem índice — rode `make dados`",
)


@pytest.fixture(scope="session")
def base_canonica():
    """A base carregada pelo mesmo caminho da execução da organização.

    O CLI constrói o índice do banco sempre que ele existe; o JSON é só reserva.
    Carregar o JSON aqui fazia a suíte testar um índice que podia estar velho —
    o de 24/09 tinha 2.001 chaves e nenhuma classe, contra 1.190 do banco — e o
    teste que guarda o score não medir o que é submetido.
    """
    from verificador.cli import _carregar_base

    return _carregar_base(INDICE, BANCO)


# A cobertura de súmulas e dispositivos do banco de desenvolvimento, como era
# curada à mão até 30/09/2026. Desde então a tabela é lida do banco recebido, e
# esta é a referência que ela precisa reproduzir no banco de dev — ver
# `tests/test_base_canonica.py`. Os testes de resolução a usam para saber o id
# esperado.
SUMULAS: dict[tuple[str, bool, int], int] = {
    ("STJ", False, 83): 1289710642,
    ("STJ", False, 211): 1289710776,
    ("STJ", False, 443): 1289711022,
    ("STF", True, 10): 1289712966,
    ("TST", False, 331): 1431369957,
}
DISPOSITIVOS: dict[tuple[str, int], int] = {
    ("CF", 5): 10641516,
    ("CF", 7): 10641213,
    ("CF", 93): 10626510,
    ("CPC", 373): 28893055,
    ("CC", 186): 10718759,
    ("CPP", 312): 10652044,
    ("CPM", 290): 10590194,
    ("CDC", 14): 10606184,
    ("CLT", 477): 10710324,
    ("CLT", 818): 10647746,
    ("CLT", 896): 10637358,
    ("ELEITORAL", 276): 10577194,
    ("LC64", 1): 11304039,
}
