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
sem_indice = pytest.mark.skipif(not INDICE.exists(), reason="índice ausente — rode `make indice`")


@pytest.fixture(scope="session")
def base_canonica():
    from verificador.base_canonica import BaseCanonica

    return BaseCanonica.de_arquivo(INDICE)
