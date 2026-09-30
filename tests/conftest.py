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
