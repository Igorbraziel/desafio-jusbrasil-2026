"""Roda o pipeline nos 26 documentos de desenvolvimento e pontua o resultado.

É o teste que guarda o score: se uma mudança quebrar a detecção ou a resolução,
ele cai aqui antes de virar submissão. Os limiares são propositalmente mais
baixos que o desempenho atual — o objetivo é pegar regressão, não travar o
número.
"""

import json
import sys

from conftest import DEV, GOLDENSET, INDICE, RAIZ, sem_dados, sem_indice

from verificador.contrato import validar
from verificador.pipeline import processar_pasta
from verificador.texto import carregar

sys.path.insert(0, str(RAIZ / "scripts"))

pytestmark = [sem_dados, sem_indice]

LIMIAR_F1 = 0.95


def test_pipeline_produz_saidas_validas(base_canonica, tmp_path):
    escritos = processar_pasta(DEV / "txt", tmp_path, base_canonica)
    assert len(escritos) == 26

    for caminho in escritos:
        saida = json.loads(caminho.read_text(encoding="utf-8"))
        texto = carregar(DEV / "txt" / f"{saida['documento_id']}.txt")
        assert validar(saida, texto) == [], caminho.name


def test_score_no_conjunto_de_desenvolvimento(base_canonica, tmp_path):
    from avaliar import avaliar

    processar_pasta(DEV / "txt", tmp_path, base_canonica)
    resultado = avaliar(tmp_path, GOLDENSET)

    for nivel, dados in resultado["niveis"].items():
        assert dados["f1_macro"] >= LIMIAR_F1, f"nível {nivel}: {dados['f1_macro']:.4f}"
        assert dados["criticos"] == 0, "nenhuma inventada pode ser classificada como real"
    assert resultado["score_final"] >= LIMIAR_F1


def test_indice_cobre_toda_a_base(base_canonica):
    assert INDICE.exists()
    assert len(base_canonica._registros) == 998
