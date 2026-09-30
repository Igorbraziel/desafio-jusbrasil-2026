"""O CSV da entrega sai no formato exato do conversor da organização.

A avaliação final roda o nosso código numa base nova e pede a saída "no mesmo
formato das submissões". O formato de referência é o que o
``json_to_submission.py`` oficial escreve; qualquer byte diferente — um
arredondamento, um fim de linha, uma ordem — deixa de ser esse formato. As
regras são fixadas aqui uma a uma, e, quando as ferramentas da organização
estão no disco, o CSV inteiro do dev é comparado com o do conversor.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest
from conftest import DEV, RAIZ, sem_dados

from verificador import submissao
from verificador.contrato import Citacao, SaidaDocumento
from verificador.submissao import (
    check_submission,
    encode_cell,
    submission_rows,
    write_submission,
)

CONVERSOR = DEV / "ferramentas" / "json_to_submission.py"


def _citacao(inicio, fim, classificacao, id_canonico=None, confianca=None):
    return Citacao(
        id=f"c{inicio}",
        inicio=inicio,
        fim=fim,
        trecho="x" * (fim - inicio),
        tipo="jurisprudencia",
        classificacao=classificacao,
        id_canonico=id_canonico,
        confianca=confianca,
    )


def _documento(documento_id, *citacoes):
    return SaidaDocumento(documento_id=documento_id, citacoes=list(citacoes)).para_dicionario()


def test_documento_sem_citacoes_vira_hifen():
    assert encode_cell(_documento("a")) == "-"


def test_citacao_sem_resolucao_tem_id_hifen():
    celula = encode_cell(_documento("a", _citacao(10, 20, "inventada", confianca=0.5)))
    assert celula == "10,20,inventada,-,0.5000"


def test_confianca_com_quatro_casas_e_ausente_vira_hifen():
    documento = _documento(
        "a",
        _citacao(10, 20, "real", id_canonico=123, confianca=0.9),
        _citacao(30, 40, "incompleta"),
    )
    assert encode_cell(documento) == "10,20,real,123,0.9000|30,40,incompleta,-,-"


def test_id_passa_por_str_e_strip_como_no_conversor():
    documento = {
        "documento_id": "a",
        "citacoes": [
            {"inicio": 1, "fim": 2, "classificacao": "real", "resolucao": {"id_canonico": 7}},
            {"inicio": 3, "fim": 4, "classificacao": "real", "resolucao": {"id_canonico": " 8 "}},
            {"inicio": 5, "fim": 6, "classificacao": "inventada", "resolucao": None},
        ],
    }
    assert encode_cell(documento) == "1,2,real,7,-|3,4,real,8,-|5,6,inventada,-,-"


def test_ordem_e_a_do_nome_do_json_e_nao_a_do_id():
    # "a-b.json" < "a.json" porque "-" < "."; pela ordem do id seria o inverso.
    linhas = submission_rows([_documento("b"), _documento("a"), _documento("a-b")])
    assert [documento_id for documento_id, _ in linhas] == ["a-b", "a", "b"]


def test_arquivo_tem_cabecalho_crlf_e_aspas_so_quando_preciso(tmp_path):
    documentos = [
        _documento("b"),
        _documento("a", _citacao(10, 20, "real", id_canonico=123, confianca=0.91)),
    ]
    destino = write_submission(documentos, tmp_path / "submission.csv")
    assert destino.read_bytes() == (
        b'documento_id,citacoes\r\na,"10,20,real,123,0.9100"\r\nb,-\r\n'
    )


def test_escrita_cria_a_pasta_e_nao_deixa_temporario(tmp_path):
    destino = tmp_path / "nova" / "funda" / "submission.csv"
    write_submission([_documento("a")], destino)
    assert destino.exists()
    assert os.listdir(destino.parent) == ["submission.csv"]


def test_falha_na_escrita_preserva_o_arquivo_anterior(tmp_path, monkeypatch):
    destino = tmp_path / "submission.csv"
    destino.write_text("anterior", encoding="utf-8")

    def falha(*_):
        raise OSError("disco cheio")

    monkeypatch.setattr(submissao.os, "replace", falha)
    with pytest.raises(OSError):
        write_submission([_documento("a")], destino)
    assert destino.read_text(encoding="utf-8") == "anterior"
    assert os.listdir(tmp_path) == ["submission.csv"]


def test_csv_escrito_passa_na_conferencia(tmp_path):
    documentos = [
        _documento("a", _citacao(10, 20, "real", id_canonico=123, confianca=1.0)),
        _documento("b", _citacao(10, 20, "inventada", confianca=0.0)),
        _documento("c"),
    ]
    destino = write_submission(documentos, tmp_path / "submission.csv")
    assert check_submission(destino, {"a", "b", "c"}) == []


def test_conferencia_acusa_documento_processado_sem_linha(tmp_path):
    destino = write_submission([_documento("a")], tmp_path / "submission.csv")
    assert check_submission(destino, {"a", "b"}) == ["documento sem linha: b"]


def test_avaliar_le_o_csv_na_ordem_do_gabarito_e_acusa_ausente(tmp_path):
    # `avaliar.py --submissao` pontua o CSV da entrega; documento do gabarito
    # sem linha entra como "-" e é reportado, e linha repetida fica com a
    # primeira, como no drop_duplicates do oficial.
    sys.path.insert(0, str(RAIZ / "scripts"))
    from avaliar import ler_submission

    caminho = tmp_path / "submission.csv"
    caminho.write_text(
        '﻿documento_id,citacoes\r\nb,-\r\na,"1,2,inventada,-,-"\r\na,-\r\n',
        encoding="utf-8",
    )
    linhas, ausentes = ler_submission(caminho, ["a", "b", "c"])
    assert linhas == [
        {"documento_id": "a", "citacoes": "1,2,inventada,-,-"},
        {"documento_id": "b", "citacoes": "-"},
        {"documento_id": "c", "citacoes": "-"},
    ]
    assert ausentes == ["c"]


def _carregar_conversor():
    spec = importlib.util.spec_from_file_location("json_to_submission", CONVERSOR)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@sem_dados
@pytest.mark.skipif(not CONVERSOR.exists(), reason="ferramentas da organização ausentes")
def test_csv_do_dev_e_identico_ao_do_conversor_oficial(tmp_path, monkeypatch, base_canonica):
    from verificador.pipeline import processar_arquivo

    pasta_json = tmp_path / "json"
    documentos = []
    for caminho in sorted((DEV / "txt").glob("*.txt")):
        documento = processar_arquivo(caminho, base_canonica)
        documento.escrever(pasta_json)
        documentos.append(documento.para_dicionario())

    nosso = write_submission(documentos, tmp_path / "nosso.csv")
    oficial = tmp_path / "oficial.csv"
    monkeypatch.setattr(sys, "argv", ["json_to_submission.py", str(pasta_json), str(oficial)])
    _carregar_conversor().main()

    assert nosso.read_bytes() == oficial.read_bytes()
