"""O ponto de entrada da avaliação final escreve o CSV no formato da submissão.

A organização roda `bash run.sh <caminho_db> <pasta_txt> <arquivo_saida>` e pontua
o CSV com os scripts dela. O conversor oficial (`json_to_submission.py`) fica em
`data/`, fora do repositório; aqui se confere que a codificação própria é igual à
dele, byte a byte, e que o `run.sh` funciona a partir de outro diretório.
"""

import importlib.util
import subprocess

import pytest
from conftest import BANCO, DEV, RAIZ, sem_dados

from verificador.submissao import codificar, escrever_csv

DOCUMENTO = {
    "documento_id": "d1",
    "citacoes": [
        {
            "inicio": 10,
            "fim": 30,
            "classificacao": "real",
            "resolucao": {"fonte": "jusbrasil", "id_canonico": "123"},
            "confianca": 1.0,
        },
        {
            "inicio": 40,
            "fim": 60,
            "classificacao": "inventada",
            "resolucao": None,
            "confianca": 0.5,
        },
    ],
}


def test_codificacao_da_celula():
    assert codificar(DOCUMENTO) == "10,30,real,123,1.0000|40,60,inventada,-,0.5000"
    assert codificar({"documento_id": "d2", "citacoes": []}) == "-"


def _conversor_oficial():
    caminho = DEV / "ferramentas" / "json_to_submission.py"
    if not caminho.exists():
        pytest.skip("conversor oficial ausente — rode `make dados`")
    especificacao = importlib.util.spec_from_file_location("json_to_submission", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    return modulo


def test_codificacao_igual_a_do_conversor_oficial():
    assert codificar(DOCUMENTO) == _conversor_oficial().encode(DOCUMENTO)


@sem_dados
def test_run_sh_gera_o_mesmo_csv_do_conversor_oficial(tmp_path):
    saida = tmp_path / "saida" / "submission.csv"
    # roda de outro diretório: nada de caminho relativo à raiz do repositório
    subprocess.run(
        ["bash", str(RAIZ / "run.sh"), str(BANCO), str(DEV / "txt"), str(saida)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    jsons = tmp_path / "jsons"
    from verificador.cli import main

    main(["--db", str(BANCO), "--input", str(DEV / "txt"), "--output", str(jsons)])
    oficial = tmp_path / "oficial.csv"
    subprocess.run(
        ["python3", str(DEV / "ferramentas" / "json_to_submission.py"), str(jsons), str(oficial)],
        check=True,
        capture_output=True,
    )
    assert saida.read_bytes() == oficial.read_bytes()
    linhas = saida.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "documento_id,citacoes"
    assert len(linhas) == 27


def test_run_sh_recusa_argumentos_faltando(tmp_path):
    processo = subprocess.run(
        ["bash", str(RAIZ / "run.sh"), "so-um-argumento"], capture_output=True, text=True
    )
    assert processo.returncode == 2
    assert "uso:" in processo.stderr


def test_csv_de_pasta_vazia_tem_so_o_cabecalho(tmp_path):
    destino = tmp_path / "s.csv"
    assert escrever_csv([], destino) == 0
    assert destino.read_text(encoding="utf-8").strip() == "documento_id,citacoes"
