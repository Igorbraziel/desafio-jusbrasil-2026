"""A detecção precisa achar a citação inteira e não achar o que não é citação."""

import pytest

from verificador.deteccao import detectar
from verificador.texto import fim_do_cabecalho

CABECALHO = (
    "EXCELENTÍSSIMO SENHOR MINISTRO RELATOR\n"
    "SUPERIOR TRIBUNAL DE JUSTIÇA\n"
    "\n"
    "Autos nº 4309330-25.2016.3.05.9083\n"
    "Impetrante: PAULO HENRIQUE VASCONCELOS\n"
    "\n"
    "AGRAVO REGIMENTAL EM HABEAS CORPUS\n"
    "\n"
)


def _detectar(corpo: str):
    return detectar(CABECALHO + corpo)


def test_numero_dos_autos_no_cabecalho_e_distrator():
    """O número do próprio processo não é citação; extraí-lo é falso positivo."""
    achados = _detectar("Nada a citar aqui, apenas prosa corrente sobre o mérito.")
    assert achados == []


def test_referencia_a_outro_processo_no_corpo_e_citacao():
    """Mesmo formato CNJ do cabeçalho, mas no corpo: é citação."""
    achados = _detectar("Ampara a pretensão o RSE nº 7000592-58.2025.7.00.0000/DF, citado.")
    assert [a.familia for a in achados] == ["processo"]
    assert achados[0].trecho == "RSE nº 7000592-58.2025.7.00.0000/DF"


@pytest.mark.parametrize(
    ("corpo", "familia", "trecho"),
    [
        ("Aplica-se a Súmula 331 do TST ao caso.", "sumula", "Súmula 331 do TST"),
        ("Conforme a Súmula Vinculante 10, a decisão cai.", "sumula", "Súmula Vinculante 10"),
        (
            "Nos termos do art. 373, I, do CPC, o ônus é do autor.",
            "dispositivo",
            "art. 373, I, do CPC",
        ),
        ("Ver o Tema 2.680 da repercussão geral.", "tema", "Tema 2.680 da repercussão geral"),
    ],
)
def test_familias(corpo, familia, trecho):
    achados = _detectar(corpo)
    assert len(achados) == 1
    assert achados[0].familia == familia
    assert achados[0].trecho == trecho


def test_citacao_vaga_sem_identificador():
    achados = _detectar("Invoca-se a jurisprudência pacífica desta Corte sobre o tema.")
    assert [a.familia for a in achados] == ["vaga"]
    assert achados[0].trecho == "jurisprudência pacífica desta Corte"


def test_citacao_vaga_com_ruido_de_ocr():
    """ "entendirnento" é "entendimento" com rn→m: o casamento tolera a troca."""
    achados = _detectar("Há entendirnento sumulado sobre a matéria.")
    assert [a.familia for a in achados] == ["vaga"]


def test_tribunal_ano_relator_e_vaga_nao_processo():
    """O ano não é número de processo: sem desempate, a citação é vaga."""
    corpo = "Cita-se o julgado do STF proferido em 2024 pela relatoria de Dias Toffoli."
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["vaga"]
    assert achados[0].trecho.startswith("julgado do STF")
    assert achados[0].trecho.endswith("Dias Toffoli")


def test_prefixo_nao_engole_a_prosa():
    achados = _detectar("Ao apreciar a RCL n° 33128 (GO), o colegiado consolidou entendimento.")
    assert achados[0].trecho == "RCL n° 33128 (GO)"


def test_sigla_composta_e_recuperada():
    achados = _detectar("Ver o processo nº TST-E-RR-173000-49.2008.5.15.0024, já julgado.")
    assert achados[0].trecho == "processo nº TST-E-RR-173000-49.2008.5.15.0024"


def test_fim_do_cabecalho_para_na_primeira_prosa():
    corte = fim_do_cabecalho(CABECALHO + "A defesa do paciente vem interpor o presente agravo.")
    assert corte == len(CABECALHO)
