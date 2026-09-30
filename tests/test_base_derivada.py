"""A base lida de um banco que não vimos: leitura robusta e tabelas derivadas.

A avaliação final roda o nosso código sobre um banco **novo**, no formato do
dev, sem acesso nosso. Até aqui o projeto supunha que a base do cego seria a do
dev, e as súmulas e os dispositivos saíam de uma tabela escrita à mão: com outro
banco, o registro que saiu continuava ``real``, o id que mudou saía com o valor
antigo e o artigo novo saía ``inventada``.

Todos os bancos daqui são sintéticos — mesmo esquema do dev, ids e textos
inventados —, para que a suíte rode num clone limpo, sem ``data/``, e para que
nada do dataset entre no repositório.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from verificador import base_canonica
from verificador.base_canonica import BaseCanonica, construir_indice

# O esquema da tabela `documentos` do banco do dev. A tabela virtual de FTS e os
# gatilhos dela ficam de fora: o verificador nunca a lê.
DDL = """
CREATE TABLE documentos (
    documento_id      TEXT PRIMARY KEY,
    id                INTEGER NOT NULL UNIQUE,
    tribunal          TEXT,
    ano               INTEGER,
    relator           TEXT,
    natureza          TEXT NOT NULL CHECK (natureza IN
                          ('acordao', 'sumula', 'dispositivo')),
    tipo              TEXT NOT NULL CHECK (tipo IN ('jurisprudencia', 'lei')),
    texto             TEXT NOT NULL,
    texto_len         INTEGER NOT NULL
);
CREATE INDEX idx_documentos_tribunal ON documentos(tribunal);
CREATE INDEX idx_documentos_ano ON documentos(ano);
CREATE INDEX idx_documentos_natureza ON documentos(natureza);
"""

# O mesmo esquema sem as restrições, para simular um banco mais sujo que o do
# dev: texto e tamanho nulos, natureza fora do vocabulário exato.
DDL_FROUXO = """
CREATE TABLE documentos (
    documento_id TEXT PRIMARY KEY, id INTEGER, tribunal TEXT, ano INTEGER,
    relator TEXT, natureza TEXT, tipo TEXT, texto TEXT, texto_len INTEGER
);
"""

# Um acórdão sintético mínimo, com o número próprio no cabeçalho, onde o índice
# o procura. O número citado na ementa não pode virar chave.
ACORDAO = (
    "RECURSO ESPECIAL Nº {numero} - RS (2021/0123456-7)\n"
    "RELATOR : MINISTRO FULANO DE TAL\n"
    "RECORRENTE : EMPRESA SINTÉTICA\n"
    "EMENTA\nPROCESSUAL CIVIL. Texto sintético da ementa.\n"
    "ACÓRDÃO\nVistos e relatados estes autos.\n"
    "RELATÓRIO\nTexto sintético.\nVOTO\nTexto sintético do voto.\n"
)


def acordao(documento_id: str, id_canonico: int, numero: str, tribunal: str = "STJ") -> tuple:
    texto = ACORDAO.format(numero=numero)
    return (documento_id, id_canonico, tribunal, 2021, "Fulano", "acordao", "jurisprudencia",
            texto, len(texto))  # fmt: skip


def sumula(documento_id: str, id_canonico: int, primeira_linha: str, tribunal: str) -> tuple:
    texto = f"{primeira_linha}\nTEMA SINTÉTICO\nEnunciado sintético da súmula.\n"
    return (documento_id, id_canonico, tribunal, None, None, "sumula", "jurisprudencia",
            texto, len(texto))  # fmt: skip


def dispositivo(documento_id: str, id_canonico: int, primeira_linha: str) -> tuple:
    texto = f"{primeira_linha}\nArt. 1. Texto sintético do dispositivo.\n"
    return (documento_id, id_canonico, None, None, None, "dispositivo", "lei",
            texto, len(texto))  # fmt: skip


def criar_banco(
    caminho: Path, registros: list[tuple], *, wal: bool = False, ddl: str = DDL
) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    try:
        if wal:
            conexao.execute("PRAGMA journal_mode=WAL")
        conexao.executescript(ddl)
        conexao.executemany("INSERT INTO documentos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", registros)
        conexao.commit()
    finally:
        conexao.close()
    return caminho


BASICO = [
    acordao("doc_a", 990000101, "7.654.321"),
    acordao("doc_b", 990000102, "7.654.399"),
]


# ── Leitura robusta ───────────────────────────────────────────────────────────


def test_banco_wal_em_diretorio_somente_leitura_abre(tmp_path):
    """Reproduzido: "attempt to write a readonly database" derrubava o lote.

    Banco em modo WAL precisa criar o ``-shm`` ao lado para ser lido, e num
    volume somente leitura não pode. A leitura repete com ``immutable=1``.
    """
    pasta = tmp_path / "somente-leitura"
    banco = criar_banco(pasta / "base.db", BASICO, wal=True)
    os.chmod(pasta, 0o555)
    try:
        base = BaseCanonica.de_banco(banco)
    finally:
        os.chmod(pasta, 0o755)
    assert [r.id_canonico for r in base.candidatos_por_numero("7654321")] == [990000101]


def test_falha_de_leitura_repete_com_immutable(tmp_path, monkeypatch, capsys):
    """A mesma recuperação, sem depender de o sistema respeitar o chmod.

    Rodando como root o chmod não impede nada, e o teste acima passa sem
    exercitar a segunda tentativa. Aqui a primeira falha por construção.
    """
    banco = criar_banco(tmp_path / "base.db", BASICO)
    original = base_canonica._iter_rows
    tentativas = []

    def falha_sem_immutable(caminho, immutable):
        tentativas.append(immutable)
        if not immutable:
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return original(caminho, immutable)

    monkeypatch.setattr(base_canonica, "_iter_rows", falha_sem_immutable)
    indice = construir_indice(banco)
    assert tentativas == [False, True]
    assert sorted(indice["registros"]) == ["doc_a", "doc_b"]
    assert "immutable=1" in capsys.readouterr().err


def test_caminho_com_caractere_de_uri_abre(tmp_path):
    """O caminho cru na URI: `#` e `?` no nome do diretório mudavam o significado."""
    banco = criar_banco(tmp_path / "dados #1 ?x" / "base.db", BASICO)
    assert sorted(construir_indice(banco)["registros"]) == ["doc_a", "doc_b"]


def test_registro_sujo_e_pulado_ou_normalizado(tmp_path, capsys):
    """Texto nulo ou vazio fica fora; tamanho nulo vira o do texto; caixa e espaço saem."""
    texto = ACORDAO.format(numero="7.654.321")
    registros = [
        ("doc_a", 990000101, " stj ", 2021, "F", " Acordao ", "jurisprudencia", texto, None),
        ("doc_b", 990000102, "STJ", 2021, "F", "acordao", "jurisprudencia", None, 0),
        ("doc_c", 990000103, "STJ", 2021, "F", "acordao", "jurisprudencia", "  \n", 3),
    ]
    banco = criar_banco(tmp_path / "base.db", registros, ddl=DDL_FROUXO)
    indice = construir_indice(banco)
    assert sorted(indice["registros"]) == ["doc_a"]
    registro = indice["registros"]["doc_a"]
    assert (registro["tribunal"], registro["texto_len"]) == ("STJ", len(texto))
    assert indice["numeros"]["7654321"] == ["doc_a"]
    assert "2 registro(s)" in capsys.readouterr().err


def test_byte_invalido_no_texto_nao_derruba_o_indice(tmp_path):
    """UTF-8 inválido num registro levantava exceção no meio da varredura."""
    banco = criar_banco(tmp_path / "base.db", BASICO)
    conexao = sqlite3.connect(banco)
    conexao.execute(
        "UPDATE documentos SET texto = CAST(? AS TEXT) WHERE documento_id = 'doc_b'",
        (ACORDAO.format(numero="7.654.399").encode("latin-1", "replace") + b"\xff\xfe",),
    )
    conexao.commit()
    conexao.close()
    assert sorted(construir_indice(banco)["registros"]) == ["doc_a", "doc_b"]
