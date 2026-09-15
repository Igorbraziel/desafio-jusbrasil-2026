"""A detecção precisa achar a citação inteira e não achar o que não é citação.

Os números, nomes e enunciados aqui são **sintéticos**: reproduzem as formas
observadas na amostra sem copiar o gabarito, que não é público. Ver
``docs/dados.md``.
"""

import pytest

from verificador.deteccao import detectar
from verificador.texto import fim_do_cabecalho

# Estes testes são a **especificação** da etapa: descrevem o comportamento
# esperado antes de ele existir. Enquanto o módulo for um stub, ficam marcados
# como falha esperada para que `make testar` continue verde. Vá removendo o
# marcador conforme implementar.
pytestmark = pytest.mark.xfail(raises=NotImplementedError, reason="a implementar", strict=False)


CABECALHO = (
    "EXCELENTÍSSIMO SENHOR MINISTRO RELATOR\n"
    "SUPERIOR TRIBUNAL DE JUSTIÇA\n"
    "\n"
    "Autos nº 4309330-25.2016.3.05.9083\n"
    "Impetrante: FULANO DE TAL\n"
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
    achados = _detectar("Ampara a pretensão o RSE nº 1234567-89.2025.7.00.0000/DF, citado.")
    assert [a.familia for a in achados] == ["processo"]
    assert achados[0].trecho == "RSE nº 1234567-89.2025.7.00.0000/DF"


@pytest.mark.parametrize(
    ("corpo", "familia", "trecho"),
    [
        ("Aplica-se a Súmula 99 do TST ao caso.", "sumula", "Súmula 99 do TST"),
        ("Conforme a Súmula Vinculante 99, a decisão cai.", "sumula", "Súmula Vinculante 99"),
        (
            "Nos termos do art. 999, I, do CPC, o ônus é do autor.",
            "dispositivo",
            "art. 999, I, do CPC",
        ),
        ("Ver o Tema 1.234 da repercussão geral.", "tema", "Tema 1.234 da repercussão geral"),
    ],
)
def test_familias(corpo, familia, trecho):
    achados = _detectar(corpo)
    assert len(achados) == 1
    assert achados[0].familia == familia
    assert achados[0].trecho == trecho


def test_citacao_vaga_sem_identificador():
    """⚠ Revisar: o gabarito não anota mais frase genérica.

    Desde a revisão de 01/09/2026 as frases difusas saíram do gabarito, e desde
    15/09 a classe `incompleta` é 100% tribunal + ano + relator. Detectar uma
    frase como a de baixo hoje produz **falso positivo**, que custa precisão.
    Este caso continua aqui como registro do comportamento antigo; decida se a
    família `vaga` deve mesmo disparar nele. Ver docs/investigacao.md.
    """
    achados = _detectar("Invoca-se a jurisprudência pacífica desta Corte sobre o tema.")
    assert [a.familia for a in achados] == ["vaga"]
    assert achados[0].trecho == "jurisprudência pacífica desta Corte"


def test_citacao_vaga_com_ruido_de_ocr():
    """ "entendirnento" é "entendimento" com rn→m: o casamento tolera a troca."""
    achados = _detectar("Há entendirnento sumulado sobre a matéria.")
    assert [a.familia for a in achados] == ["vaga"]


def test_tribunal_ano_relator_e_vaga_nao_processo():
    """O ano não é número de processo: sem desempate, a citação é vaga."""
    corpo = "Cita-se o julgado do STF proferido em 2024 pela relatoria de Fulano de Tal."
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["vaga"]
    assert achados[0].trecho.startswith("julgado do STF")
    assert achados[0].trecho.endswith("Fulano de Tal")


def test_prefixo_nao_engole_a_prosa():
    achados = _detectar("Ao apreciar a RCL n° 45678 (GO), o colegiado consolidou entendimento.")
    assert achados[0].trecho == "RCL n° 45678 (GO)"


def test_sigla_composta_e_recuperada():
    achados = _detectar("Ver o processo nº TST-E-RR-123456-78.2008.5.15.0024, já julgado.")
    assert achados[0].trecho == "processo nº TST-E-RR-123456-78.2008.5.15.0024"


def test_fim_do_cabecalho_para_na_primeira_prosa():
    corte = fim_do_cabecalho(CABECALHO + "A defesa do paciente vem interpor o presente agravo.")
    assert corte == len(CABECALHO)
