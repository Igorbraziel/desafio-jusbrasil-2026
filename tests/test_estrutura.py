"""Os invariantes da segmentação em zonas.

São três, e não dependem de gabarito: qualquer texto tem de sair ladrilhado,
ancorado e não-vazio. É o que separa extração de invenção — uma zona cujo texto
não está no documento é alucinação, e aqui isso é verificável a custo zero.
"""

import sqlite3

import pytest
from conftest import BANCO, sem_dados

from verificador.estrutura import (
    ZONAS,
    ZONAS_IDENTIFICADORAS,
    Zona,
    segmentar,
    tribunal_do_texto,
    zonas_de_identificacao,
)

CABECALHO_STJ = (
    "RECURSO ESPECIAL Nº 9.876.543 - PR (2018/0000000-0) "
    "RELATOR : MINISTRO FULANO DE TAL "
    "RECORRENTE : EMPRESA FICTÍCIA S.A "
)
CORPO = (
    "EMENTA PROCESSUAL PENAL. RECURSO ESPECIAL. "
    "RELATÓRIO Trata-se de recurso especial interposto com fundamento no art. 105. "
    "VOTO O recurso não merece prosperar, pelas razões que seguem. "
)


def _conferir_invariantes(texto: str, zonas: list[Zona]) -> None:
    """Ladrilhamento e ancoragem, que valem para qualquer entrada."""
    assert zonas, "a segmentação nunca devolve vazio para texto não-vazio"
    assert zonas[0].inicio == 0, "a primeira zona começa em 0"
    assert zonas[-1].fim == len(texto), "a última zona termina no fim do texto"
    for anterior, atual in zip(zonas, zonas[1:], strict=False):
        assert anterior.fim == atual.inicio, "sem buraco nem sobreposição entre zonas"
    for zona in zonas:
        assert zona.fim > zona.inicio, "zona vazia não é emitida"
        assert zona.texto == texto[zona.inicio : zona.fim], "ancoragem"
        assert zona.tipo in ZONAS, f"tipo desconhecido: {zona.tipo}"


def test_ladrilha_e_ancora():
    texto = CABECALHO_STJ + CORPO
    _conferir_invariantes(texto, segmentar(texto, "STJ"))


def test_texto_sem_marcador_vira_cabecalho_inteiro():
    """Degradado seguro: sem marcador, tudo é cabeçalho — nunca lista vazia."""
    texto = "Prosa corrente sem nenhum marcador estrutural reconhecível."
    zonas = segmentar(texto, "STJ")
    _conferir_invariantes(texto, zonas)
    assert [z.tipo for z in zonas] == ["cabecalho"]


def test_texto_vazio_devolve_lista_vazia():
    assert segmentar("") == []


def test_cabecalho_vem_antes_do_primeiro_marcador():
    texto = CABECALHO_STJ + CORPO
    zonas = segmentar(texto, "STJ")
    assert zonas[0].tipo == "cabecalho"
    assert "RECURSO ESPECIAL Nº 9.876.543" in zonas[0].texto
    assert "EMENTA" not in zonas[0].texto


def test_zona_de_identificacao_limita_o_tamanho():
    """A fórmula de abertura identifica nos primeiros caracteres; depois emenda
    na lista de partes, que não identifica nada."""
    texto = (
        "A C Ó R D Ã O SbDI-1 "
        + "Vistos, relatados e discutidos estes autos de Recurso de Revista "
        "nº TST-RR-9999-99.2011.5.02.0251, em que é Recorrente FULANO " + "x" * 2000
    )
    zonas = segmentar(texto, "TST")
    _conferir_invariantes(texto, zonas)
    identificacao = [z for z in zonas if z.tipo == "identificacao"]
    assert len(identificacao) == 1
    assert identificacao[0].n_chars <= 400
    assert "TST-RR-9999-99.2011.5.02.0251" in identificacao[0].texto


def test_zonas_de_identificacao_filtra():
    texto = CABECALHO_STJ + CORPO
    assert {z.tipo for z in zonas_de_identificacao(texto, "STJ")} <= ZONAS_IDENTIFICADORAS


@pytest.mark.parametrize(
    ("trecho", "esperado"),
    [
        ("RELATOR : MINISTRO FULANO DE TAL", "STJ"),
        ("RELATOR : MIN. FULANO DE TAL", "STF"),
        ("A C Ó R D Ã O SbDI-1 GMJRP", "TST"),
        ("Poder Judiciário STM EXTRATO DE ATA", "STM"),
        ("O TRIEUNAL SUPERIOR ELEITORAL ACÓRDÃO", "TSE"),
        ("Prosa sem assinatura nenhuma", None),
    ],
)
def test_inferencia_de_tribunal(trecho, esperado):
    assert tribunal_do_texto(trecho) == esperado


def test_sigla_citada_no_corpo_nao_confunde_a_inferencia():
    """`\\bSTF\\b` aparece em acórdão do TST que cita o STF: a assinatura tem de
    ser estrutural, não acrônimo solto."""
    texto = "A C Ó R D Ã O SbDI-1 " + "x" * 200 + " conforme decidiu o STF no RE 9.876.543"
    assert tribunal_do_texto(texto) == "TST"


@sem_dados
def test_invariantes_valem_na_base_inteira():
    """Ladrilhamento e ancoragem nos 996 acórdãos, não só nos exemplos."""
    conexao = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    try:
        consulta = "SELECT tribunal, texto FROM documentos WHERE natureza = 'acordao'"
        for tribunal, texto in conexao.execute(consulta):
            _conferir_invariantes(texto, segmentar(texto, tribunal))
    finally:
        conexao.close()
