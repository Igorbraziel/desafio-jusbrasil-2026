"""O CLI escolhe a base do mesmo jeito que a execução da organização.

No contrato de execução só o banco é montado; o índice é construído dele. Se a
execução local lesse um índice JSON antigo que estivesse no disco, a submissão
feita daqui poderia divergir da reexecução — e "não bater o score"
desclassifica. Com o banco à mão, o índice sai sempre dele.

O modo de entrega (`--csv`) é o que a avaliação final roda, sem ninguém nosso
olhando: banco ou pasta errados precisam parar com mensagem e código ≠ 0, e um
documento que falha não pode derrubar os outros.
"""

import csv
import json

import pytest

from verificador import cli, pipeline
from verificador.base_canonica import BaseCanonica
from verificador.contrato import Citacao, SaidaDocumento

BASE_VAZIA = BaseCanonica({"numeros": {}, "registros": {}})


def test_com_banco_o_indice_vem_do_banco(tmp_path, monkeypatch):
    velho = tmp_path / "indice.json"
    velho.write_text(json.dumps({"numeros": {"999": ["x"]}, "registros": {}}), encoding="utf-8")
    banco = tmp_path / "base.db"
    banco.write_bytes(b"")

    chamadas = []
    monkeypatch.setattr(cli.BaseCanonica, "de_banco", classmethod(lambda c, p: chamadas.append(p)))
    cli._carregar_base(velho, banco)
    assert chamadas == [banco]


def test_sem_banco_usa_o_indice_passado(tmp_path):
    indice = tmp_path / "indice.json"
    indice.write_text(json.dumps({"numeros": {}, "registros": {}}), encoding="utf-8")
    base = cli._carregar_base(indice, tmp_path / "nao-existe.db")
    assert base.candidatos_por_numero("12345") == []


def test_sem_banco_e_sem_indice_para_com_o_caminho_na_mensagem(tmp_path):
    ausente = tmp_path / "nao-existe.db"
    with pytest.raises(SystemExit) as erro:
        cli._carregar_base(None, ausente)
    assert str(ausente) in str(erro.value.code)


def _pasta_com_textos(tmp_path, nomes=("a.txt", "b.txt")):
    entrada = tmp_path / "txt"
    entrada.mkdir()
    for nome in nomes:
        (entrada / nome).write_text("Parecer sem citação alguma.\n", encoding="utf-8")
    return entrada


@pytest.fixture
def banco_falso(tmp_path, monkeypatch):
    """Um banco que existe, com a leitura trocada pela base vazia."""
    banco = tmp_path / "base.db"
    banco.write_bytes(b"")
    monkeypatch.setattr(cli.BaseCanonica, "de_banco", classmethod(lambda c, p: BASE_VAZIA))
    return banco


def _linhas(caminho):
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return {linha["documento_id"]: linha["citacoes"] for linha in csv.DictReader(arquivo)}


def test_banco_ausente_nao_cai_no_indice_antigo(tmp_path, monkeypatch):
    # O índice do dev no lugar do antigo padrão não pode ser usado em silêncio.
    padrao = tmp_path / "data" / "dev" / "indice_cabecalhos.json"
    padrao.parent.mkdir(parents=True)
    padrao.write_text(json.dumps({"numeros": {}, "registros": {}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    entrada = _pasta_com_textos(tmp_path)
    saida = tmp_path / "saida" / "submission.csv"

    with pytest.raises(SystemExit) as erro:
        cli.main(["--db", "nao-existe.db", "--input", str(entrada), "--csv", str(saida)])
    assert erro.value.code not in (0, None)
    assert "nao-existe.db" in str(erro.value.code)
    assert not saida.exists()


def test_banco_que_nao_abre_vira_mensagem(tmp_path):
    banco = tmp_path / "base.db"
    banco.write_bytes(b"isto nao e sqlite" * 100)
    entrada = _pasta_com_textos(tmp_path)
    with pytest.raises(SystemExit) as erro:
        cli.main(["--db", str(banco), "--input", str(entrada), "--csv", str(tmp_path / "s.csv")])
    assert "não consegui ler a base canônica" in str(erro.value.code)


def test_entrega_grava_csv_json_e_resumo(tmp_path, banco_falso, capsys):
    entrada = _pasta_com_textos(tmp_path, ("b.txt", "a.TXT"))
    saida = tmp_path / "saida" / "submission.csv"
    codigo = cli.main(
        ["--db", str(banco_falso), "--input", str(entrada), "--csv", str(saida)]
        + ["--output", str(tmp_path / "json")]
    )
    assert codigo == 0
    assert _linhas(saida) == {"a": "-", "b": "-"}
    assert sorted(p.name for p in (tmp_path / "json").iterdir()) == ["a.json", "b.json"]
    assert "2 documentos, 0 citações" in capsys.readouterr().err


def test_sem_txt_no_primeiro_nivel_procura_nas_subpastas(tmp_path, banco_falso, capsys):
    entrada = tmp_path / "entrada"
    (entrada / "txt").mkdir(parents=True)
    (entrada / "txt" / "a.txt").write_text("Parecer.\n", encoding="utf-8")
    (entrada / "leia-me.md").write_text("não é documento\n", encoding="utf-8")
    saida = tmp_path / "submission.csv"

    assert cli.main(["--db", str(banco_falso), "--input", str(entrada), "--csv", str(saida)]) == 0
    assert _linhas(saida) == {"a": "-"}
    assert "subpastas" in capsys.readouterr().err


def test_txt_no_primeiro_nivel_ignora_as_subpastas(tmp_path):
    entrada = _pasta_com_textos(tmp_path, ("a.txt",))
    (entrada / "velhos").mkdir()
    (entrada / "velhos" / "b.txt").write_text("Parecer.\n", encoding="utf-8")
    assert [p.name for p in cli.collect_texts(entrada)] == ["a.txt"]


def test_pasta_sem_nenhum_txt_para(tmp_path, banco_falso):
    entrada = tmp_path / "vazia"
    (entrada / "sub").mkdir(parents=True)
    (entrada / "sub" / "nota.md").write_text("x\n", encoding="utf-8")
    saida = tmp_path / "submission.csv"
    with pytest.raises(SystemExit) as erro:
        cli.main(["--db", str(banco_falso), "--input", str(entrada), "--csv", str(saida)])
    assert erro.value.code not in (0, None)
    assert not saida.exists()


def test_documento_que_falha_sai_vazio_e_os_outros_seguem(tmp_path, banco_falso, monkeypatch):
    def falha_em_a(doc_id, texto, base):
        if doc_id == "a":
            raise RuntimeError("quebrou")
        return SaidaDocumento(
            documento_id=doc_id,
            citacoes=[Citacao("c1", 0, 7, "Parecer", "jurisprudencia", "inventada", None, 0.5)],
        )

    monkeypatch.setattr(pipeline, "processar_texto", falha_em_a)
    entrada = _pasta_com_textos(tmp_path)
    saida = tmp_path / "submission.csv"
    assert cli.main(["--db", str(banco_falso), "--input", str(entrada), "--csv", str(saida)]) == 0
    assert _linhas(saida) == {"a": "-", "b": "0,7,inventada,-,0.5000"}


def test_conferencia_que_falha_da_codigo_1_e_mantem_o_csv(tmp_path, banco_falso, monkeypatch):
    def duplicadas(doc_id, texto, base):
        citacoes = [
            Citacao("c1", 0, 10, "x" * 10, "jurisprudencia", "inventada", None, 0.5),
            Citacao("c2", 1, 10, "x" * 9, "jurisprudencia", "inventada", None, 0.5),
        ]
        return SaidaDocumento(documento_id=doc_id, citacoes=citacoes)

    monkeypatch.setattr(pipeline, "processar_texto", duplicadas)
    entrada = _pasta_com_textos(tmp_path, ("a.txt",))
    saida = tmp_path / "submission.csv"
    assert cli.main(["--db", str(banco_falso), "--input", str(entrada), "--csv", str(saida)]) == 1
    assert saida.exists()


def test_modo_de_desenvolvimento_continua_gravando_so_os_json(tmp_path, banco_falso):
    entrada = _pasta_com_textos(tmp_path)
    saida = tmp_path / "out"
    assert (
        cli.main(["--input", str(entrada), "--output", str(saida), "--db", str(banco_falso)]) == 0
    )
    assert sorted(p.name for p in saida.iterdir()) == ["a.json", "b.json"]


def test_sem_csv_nem_output_e_erro_de_uso(tmp_path):
    with pytest.raises(SystemExit) as erro:
        cli.main(["--input", str(tmp_path)])
    assert erro.value.code == 2
