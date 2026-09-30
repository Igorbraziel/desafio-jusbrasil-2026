"""O `run.sh` da entrega, rodado como a organização vai rodá-lo.

A avaliação final executa `bash run.sh <db> <pasta_txt> <saida>` num ambiente
que não controlamos, sobre uma base e pareceres novos. Estes testes fazem o
mesmo: copiam para uma pasta temporária só o que um clone traz — `run.sh` e
`src/`, sem `data/` —, montam uma base sintética com o esquema da tabela
`documentos` e chamam o script por subprocess, de outra pasta, com caminhos
relativos e espaço no nome.

Súmulas e dispositivos ficam de fora de propósito: a resolução deles está em
mudança, e este teste guarda a entrada, não a classificação.
"""

from __future__ import annotations

import csv
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import RAIZ

from verificador.base_canonica import BaseCanonica
from verificador.submissao import check_submission

# O esquema de `documentos` como a organização o distribui. É estrutura, não
# conteúdo: a base da avaliação final terá outras linhas nessa mesma tabela.
DDL_DOCUMENTOS = """
CREATE TABLE documentos (
    documento_id      TEXT PRIMARY KEY,
    id                INTEGER NOT NULL UNIQUE,  -- doc_id do Jusbrasil
    -- súmulas têm tribunal; dispositivos de lei, não
    tribunal          TEXT,
    ano               INTEGER,
    relator           TEXT,
    natureza          TEXT NOT NULL CHECK (natureza IN
                          ('acordao', 'sumula', 'dispositivo')),
    tipo              TEXT NOT NULL CHECK (tipo IN ('jurisprudencia', 'lei')),
    texto             TEXT NOT NULL,
    texto_len         INTEGER NOT NULL
)
"""

# Um acórdão inventado, com número e id que não existem em base nenhuma.
NUMERO = "7654321"
ID_SINTETICO = "900000001"
ACORDAO = (
    "SUPERIOR TRIBUNAL DE JUSTIÇA\n"
    "RECURSO ESPECIAL Nº 7.654.321 - SP (2020/0000000-0)\n"
    "RELATOR : MINISTRO FULANO DE TAL\n"
    "RECORRENTE : EMPRESA FICTÍCIA S.A\n"
    "RECORRIDO : FULANO DE TAL\n"
    "EMENTA\n"
    "PROCESSUAL CIVIL. RECURSO ESPECIAL. TESE FICTÍCIA.\n"
    "ACÓRDÃO\n"
    "Vistos, relatados e discutidos estes autos, acordam os Ministros da Turma.\n"
)

CITA = (
    "PARECER\n\n"
    "Trata-se de consulta sobre a matéria. Conforme decidido no REsp 7.654.321/SP, "
    "a tese se aplica. Em sentido diverso, o REsp 1.357.913/RJ não socorre o consulente.\n"
)
SEM_CITACAO = "PARECER\n\nTrata-se de consulta sobre matéria de fato, sem precedente algum.\n"
LATIN1 = "PARECER\n\nA ação é improcedente e não há citação a conferir.\n"


def _base_sintetica(caminho: Path) -> Path:
    conexao = sqlite3.connect(caminho)
    conexao.execute(DDL_DOCUMENTOS)
    conexao.execute(
        "INSERT INTO documentos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "stj-sintetico-1",
            int(ID_SINTETICO),
            "STJ",
            2020,
            "FULANO DE TAL",
            "acordao",
            "jurisprudencia",
            ACORDAO,
            len(ACORDAO),
        ),
    )
    conexao.commit()
    conexao.close()
    return caminho


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    """Um clone mínimo, a base sintética e a pasta de pareceres com espaço."""
    raiz = tmp_path_factory.mktemp("entrega")
    clone = raiz / "clone"
    clone.mkdir()
    shutil.copy2(RAIZ / "run.sh", clone / "run.sh")
    shutil.copytree(RAIZ / "src", clone / "src", ignore=shutil.ignore_patterns("__pycache__"))

    chamador = raiz / "chamador"
    textos = chamador / "pareceres do lote"
    textos.mkdir(parents=True)
    (textos / "cita.txt").write_text(CITA, encoding="utf-8")
    (textos / "sem_citacao.txt").write_text(SEM_CITACAO, encoding="utf-8")
    (textos / "latin1.txt").write_bytes(LATIN1.encode("latin-1"))

    banco = _base_sintetica(chamador / "base.db")
    return clone, chamador, banco


def _rodar(clone: Path, cwd: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    ambiente = {**os.environ, "PYTHON": sys.executable, **env}
    ambiente.pop("PYTHONPATH", None)
    return subprocess.run(
        ["bash", str(clone / "run.sh"), *args],
        cwd=cwd,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _linhas(caminho: Path) -> dict[str, str]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return {linha["documento_id"]: linha["citacoes"] for linha in csv.DictReader(arquivo)}


def test_numero_sintetico_entra_no_indice(ambiente):
    _, _, banco = ambiente
    candidatos = BaseCanonica.de_banco(banco).candidatos_por_numero(NUMERO)
    assert [str(c.id_canonico) for c in candidatos] == [ID_SINTETICO]


def test_entrega_gera_uma_linha_por_documento_no_formato(ambiente):
    clone, chamador, _ = ambiente
    resultado = _rodar(
        clone, chamador, "base.db", "pareceres do lote", "saida/submission.csv", "saida/json"
    )
    assert resultado.returncode == 0, resultado.stderr

    saida = chamador / "saida" / "submission.csv"
    linhas = _linhas(saida)
    assert sorted(linhas) == ["cita", "latin1", "sem_citacao"]
    assert check_submission(saida, set(linhas)) == []
    assert linhas["sem_citacao"] == "-"
    assert sorted(p.name for p in (chamador / "saida" / "json").iterdir()) == [
        "cita.json",
        "latin1.json",
        "sem_citacao.json",
    ]

    citacoes = [bloco.split(",") for bloco in linhas["cita"].split("|")]
    reais = [c for c in citacoes if c[2] == "real"]
    inventadas = [c for c in citacoes if c[2] == "inventada"]
    assert [c[3] for c in reais] == [ID_SINTETICO]
    assert CITA[int(reais[0][0]) : int(reais[0][1])].startswith("REsp 7.654.321")
    assert len(inventadas) == 1
    assert "1.357.913" in CITA[int(inventadas[0][0]) : int(inventadas[0][1])]


def test_duas_execucoes_dao_os_mesmos_bytes(ambiente):
    clone, chamador, _ = ambiente
    for nome in ("a.csv", "b.csv"):
        resultado = _rodar(clone, chamador, "base.db", "pareceres do lote", nome)
        assert resultado.returncode == 0, resultado.stderr
    assert (chamador / "a.csv").read_bytes() == (chamador / "b.csv").read_bytes()


def test_prefixo_do_entrypoint_e_descartado(ambiente):
    # `docker run <imagem> bash run.sh a b c` chega ao script assim.
    clone, chamador, _ = ambiente
    resultado = _rodar(
        clone, chamador, "bash", "run.sh", "base.db", "pareceres do lote", "prefixo.csv"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert sorted(_linhas(chamador / "prefixo.csv")) == ["cita", "latin1", "sem_citacao"]


def test_chamado_pelo_sh_reexecuta_no_bash(ambiente):
    # `sh run.sh` usa o sh do sistema, que pode não ter arrays; o script se
    # reexecuta no bash em vez de quebrar no meio.
    clone, chamador, _ = ambiente
    resultado = subprocess.run(
        ["sh", str(clone / "run.sh"), "base.db", "pareceres do lote", "via_sh.csv"],
        cwd=chamador,
        env={**os.environ, "PYTHON": sys.executable},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert sorted(_linhas(chamador / "via_sh.csv")) == ["cita", "latin1", "sem_citacao"]


def test_pacote_homonimo_na_pasta_de_quem_chama_nao_toma_o_lugar(ambiente, tmp_path):
    # Com `-m`, a pasta de quem chama vem antes do PYTHONPATH; um `verificador`
    # ali seria importado no lugar do nosso sem o PYTHONSAFEPATH.
    clone, chamador, banco = ambiente
    impostor = tmp_path / "verificador"
    impostor.mkdir()
    (impostor / "__init__.py").write_text("", encoding="utf-8")
    (impostor / "cli.py").write_text("raise SystemExit('impostor')\n", encoding="utf-8")
    resultado = _rodar(clone, tmp_path, str(banco), str(chamador / "pareceres do lote"), "s.csv")
    assert resultado.returncode == 0, resultado.stderr
    assert (tmp_path / "s.csv").exists()


@pytest.mark.parametrize("saida", ["pareceres do lote", "saida_nova/"])
def test_saida_que_nao_e_arquivo_para(ambiente, saida):
    clone, chamador, _ = ambiente
    resultado = _rodar(clone, chamador, "base.db", "pareceres do lote", saida)
    assert resultado.returncode != 0
    assert "caminho do CSV" in resultado.stderr


def test_pasta_de_entrada_inexistente_para(ambiente):
    clone, chamador, _ = ambiente
    resultado = _rodar(clone, chamador, "base.db", "nao-existe", "x.csv")
    assert resultado.returncode != 0
    assert "nao-existe" in resultado.stderr


def test_banco_inexistente_para_sem_escrever_csv(ambiente):
    clone, chamador, _ = ambiente
    resultado = _rodar(clone, chamador, "nao-existe.db", "pareceres do lote", "sem_banco.csv")
    assert resultado.returncode != 0
    assert "nao-existe.db" in resultado.stderr
    assert not (chamador / "sem_banco.csv").exists()


def test_pasta_sem_txt_para(ambiente):
    clone, chamador, _ = ambiente
    vazia = chamador / "vazia"
    vazia.mkdir(exist_ok=True)
    (vazia / "leia-me.md").write_text("não é parecer\n", encoding="utf-8")
    resultado = _rodar(clone, chamador, "base.db", "vazia", "vazia.csv")
    assert resultado.returncode != 0
    assert not (chamador / "vazia.csv").exists()


@pytest.mark.parametrize("args", [[], ["base.db"], ["a", "b", "c", "d", "e"], ["--help"]])
def test_uso_errado_mostra_o_uso_com_codigo_2(ambiente, args):
    clone, chamador, _ = ambiente
    resultado = _rodar(clone, chamador, *args)
    assert resultado.returncode == 2
    assert "uso: bash run.sh" in resultado.stderr


def test_python_indicado_invalido_para_com_mensagem(ambiente):
    clone, chamador, _ = ambiente
    resultado = _rodar(
        clone, chamador, "base.db", "pareceres do lote", "x.csv", PYTHON="/nao/existe/python"
    )
    assert resultado.returncode != 0
    assert "PYTHON=/nao/existe/python" in resultado.stderr


def test_sem_python_nem_docker_para_com_mensagem(ambiente, tmp_path):
    # PATH só com o bash: nenhum Python e nenhum Docker à vista.
    clone, chamador, _ = ambiente
    so_bash = tmp_path / "bin"
    so_bash.mkdir()
    (so_bash / "bash").symlink_to(shutil.which("bash"))
    ambiente_minimo = {"PATH": str(so_bash), "HOME": str(tmp_path)}
    resultado = subprocess.run(
        [str(so_bash / "bash"), str(clone / "run.sh"), "base.db", "pareceres do lote", "x.csv"],
        cwd=chamador,
        env=ambiente_minimo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert resultado.returncode != 0
    assert "Docker" in resultado.stderr
    assert not (chamador / "x.csv").exists()
