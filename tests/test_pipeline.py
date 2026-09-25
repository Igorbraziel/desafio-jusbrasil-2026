"""O lote sobrevive a um documento ruim.

Documento sem linha na submissão faz o avaliador oficial rejeitar a submissão
inteira, então uma falha isolada não pode custar os documentos seguintes.
"""

import json

import pytest

from verificador import pipeline
from verificador.base_canonica import BaseCanonica

BASE_VAZIA = BaseCanonica({"numeros": {}, "registros": {}})
CORPO = "PARECER\n\nConforme o art. 5º da Constituição Federal, o pedido procede.\n"


def _pasta(tmp_path):
    entrada = tmp_path / "in"
    entrada.mkdir()
    (entrada / "a.txt").write_text(CORPO, encoding="utf-8")
    (entrada / "b.txt").write_bytes("Ação no art. 5º da Constituição Federal".encode("latin-1"))
    (entrada / "c.txt").write_text(CORPO, encoding="utf-8")
    return entrada


def test_arquivo_fora_do_utf8_nao_derruba_o_lote(tmp_path):
    escritos = pipeline.processar_pasta(_pasta(tmp_path), tmp_path / "out", BASE_VAZIA)
    assert sorted(p.stem for p in escritos) == ["a", "b", "c"]


def test_documento_que_falha_sai_vazio_e_o_lote_segue(tmp_path, monkeypatch):
    original = pipeline.processar_texto

    def falha_em_b(doc_id, texto, base):
        if doc_id == "b":
            raise RuntimeError("defeito simulado")
        return original(doc_id, texto, base)

    monkeypatch.setattr(pipeline, "processar_texto", falha_em_b)
    escritos = pipeline.processar_pasta(_pasta(tmp_path), tmp_path / "out", BASE_VAZIA)

    saidas = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in escritos}
    assert set(saidas) == {"a", "b", "c"}
    assert saidas["b"]["citacoes"] == []
    assert saidas["c"]["citacoes"], "o documento depois da falha também é processado"


@pytest.mark.parametrize("nome", ["a", "c"])
def test_bytes_invalidos_nao_mudam_o_texto_valido(tmp_path, nome):
    from verificador.texto import carregar

    assert carregar(_pasta(tmp_path) / f"{nome}.txt") == CORPO


def test_documento_que_estoura_o_tempo_sai_vazio(tmp_path, monkeypatch):
    """Backtracking catastrófico já travou este código duas vezes.

    No ambiente da organização o teto é de 4 h para o lote; um documento que
    trava tem de sair vazio e deixar o lote seguir, como uma falha qualquer.
    """
    import time

    original = pipeline.processar_texto

    def trava_em_b(doc_id, texto, base):
        if doc_id == "b":
            time.sleep(5)
        return original(doc_id, texto, base)

    monkeypatch.setattr(pipeline, "processar_texto", trava_em_b)
    monkeypatch.setattr(pipeline, "TIMEOUT_POR_DOCUMENTO", 0.2)
    inicio = time.perf_counter()
    escritos = pipeline.processar_pasta(_pasta(tmp_path), tmp_path / "out", BASE_VAZIA)
    assert time.perf_counter() - inicio < 3
    saidas = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in escritos}
    assert set(saidas) == {"a", "b", "c"}
    assert saidas["b"]["citacoes"] == []
    assert saidas["c"]["citacoes"]


def test_extensao_em_maiuscula_tambem_e_processada(tmp_path):
    entrada = tmp_path / "in"
    entrada.mkdir()
    (entrada / "d.TXT").write_text(CORPO, encoding="utf-8")
    escritos = pipeline.processar_pasta(entrada, tmp_path / "out", BASE_VAZIA)
    assert [p.stem for p in escritos] == ["d"]


def test_quebra_de_linha_crlf_nao_desloca_offsets(tmp_path):
    """O offset é contado no arquivo como ele é: `\\r\\n` não pode virar `\\n`."""
    from verificador.texto import carregar

    caminho = tmp_path / "e.txt"
    caminho.write_bytes("PARECER\r\n\r\nConforme o art. 5º da CF.\r\n".encode())
    assert carregar(caminho) == "PARECER\r\n\r\nConforme o art. 5º da CF.\r\n"
