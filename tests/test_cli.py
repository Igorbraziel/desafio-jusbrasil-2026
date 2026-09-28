"""O CLI escolhe a base do mesmo jeito que a execução da organização.

No contrato de execução só o banco é montado (`/data/base/desafio1_bracis.db`);
o índice é construído dele. Se a execução local lesse um índice JSON antigo que
estivesse no disco, a submissão feita daqui poderia divergir da reexecução — e
"não bater o score" desclassifica. Com o banco à mão, o índice sai sempre dele.
"""

import json

from verificador import cli


def test_com_banco_o_indice_vem_do_banco(tmp_path, monkeypatch):
    velho = tmp_path / "indice.json"
    velho.write_text(json.dumps({"numeros": {"999": ["x"]}, "registros": {}}), encoding="utf-8")
    banco = tmp_path / "base.db"
    banco.write_bytes(b"")

    chamadas = []
    monkeypatch.setattr(cli.BaseCanonica, "de_banco", classmethod(lambda c, p: chamadas.append(p)))
    cli._carregar_base(velho, banco)
    assert chamadas == [banco]


def test_sem_banco_usa_o_indice(tmp_path):
    indice = tmp_path / "indice.json"
    indice.write_text(json.dumps({"numeros": {}, "registros": {}}), encoding="utf-8")
    base = cli._carregar_base(indice, tmp_path / "nao-existe.db")
    assert base.candidatos_por_numero("12345") == []
