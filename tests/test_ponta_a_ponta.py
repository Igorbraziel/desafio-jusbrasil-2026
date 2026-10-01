"""Roda o pipeline nos 26 documentos de desenvolvimento e pontua o resultado.

É o teste que guarda o score: se uma mudança quebrar a detecção ou a resolução,
ele cai aqui antes de virar submissão. Os limiares são propositalmente mais
baixos que o desempenho atual — o objetivo é pegar regressão, não travar o
número.
"""

import json
import sys

from conftest import DEV, GOLDENSET, RAIZ, sem_dados, sem_indice

from verificador.pipeline import processar_pasta
from verificador.saida.contrato import validar
from verificador.texto import carregar

sys.path.insert(0, str(RAIZ / "scripts"))


pytestmark = [sem_dados, sem_indice]

# O pipeline mede 1,0000 de F1 macro nos dois níveis do conjunto de
# desenvolvimento. O limiar antigo, 0,95, deixava passar em silêncio uma
# regressão de até cinco citações: é o portão que o README declara ("nada entra
# se derrubar o score limpo"), então ele precisa ser executável.
LIMIAR_F1 = 1.0

# O menor IoU entre predição e gabarito no dev é 0,854 (era 0,8125 antes de o
# conector deixar de abrir o span). Um span que encolhe não move o F1 até cruzar
# 0,5 — e aí quebra duas vezes de uma vez (FN e FP). Esta guarda pega o
# encolhimento antes, com folga para ajuste legítimo de borda.
LIMIAR_IOU = 0.80


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
        assert dados["macro_f1"] >= LIMIAR_F1, f"nível {nivel}: {dados['macro_f1']:.4f}"
        # τ é a fração das `inventada` preditas como `real`. É o único erro que a
        # métrica oficial pune multiplicativamente, sobre o score do nível todo.
        assert dados["tau"] == 0.0, "nenhuma inventada pode ser classificada como real"
    assert resultado["score_final"] >= LIMIAR_F1


def test_nenhum_span_do_gabarito_fica_perto_do_corte_de_iou(base_canonica, tmp_path):
    import csv

    processar_pasta(DEV / "txt", tmp_path, base_canonica)
    preditos: dict[str, list[tuple[int, int]]] = {}
    for caminho in tmp_path.glob("*.json"):
        saida = json.loads(caminho.read_text(encoding="utf-8"))
        preditos[saida["documento_id"]] = [(c["inicio"], c["fim"]) for c in saida["citacoes"]]

    def iou(a: int, b: int, c: int, d: int) -> float:
        inter = max(0, min(b, d) - max(a, c))
        return inter / ((b - a) + (d - c) - inter)

    with GOLDENSET.open(encoding="utf-8-sig") as arquivo:
        for linha in csv.DictReader(arquivo):
            gi, gf = int(linha["inicio"]), int(linha["fim"])
            melhor = max(
                (iou(a, b, gi, gf) for a, b in preditos[linha["documento_id"]]), default=0.0
            )
            onde = f"{linha['documento_id']} {linha['citacao_id']}"
            assert melhor >= LIMIAR_IOU, f"{onde}: {melhor:.3f}"


def test_indice_cobre_toda_a_base(base_canonica):
    assert len(base_canonica._registros) == 996
