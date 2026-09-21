"""A detecção precisa achar a citação inteira e não achar o que não é citação.

Os números, nomes e enunciados aqui são **sintéticos**: reproduzem as formas
observadas na amostra sem copiar o gabarito, que não é público. Ver
``docs/dados.md``.
"""

import pytest

from verificador.deteccao import detectar
from verificador.texto import fim_do_cabecalho

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


@pytest.mark.parametrize(
    "corpo",
    [
        "Invoca-se a jurisprudência pacífica desta Corte sobre o tema.",
        "Aplicam-se as normas de regência da matéria ao caso concreto.",
        "Há entendirnento sumulado sobre a matéria.",
        "Observa-se o artigo correspondente do diploma de regência.",
    ],
)
def test_frase_generica_nao_e_citacao(corpo):
    """Frase difusa deixou de ser citação — detectá-la hoje é falso positivo.

    As revisões de 01/09 e 15/09 tiraram do gabarito as frases sem identificador,
    e hoje a classe `incompleta` é só o padrão tribunal + ano + relator. Extrair
    uma frase como as de baixo custa precisão sem ganhar recall. O terceiro caso
    mantém o ruído rn→m de propósito: o que mudou foi o alvo, não a tolerância a
    OCR. Ver docs/investigacao.md.
    """
    assert _detectar(corpo) == []


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


# ── Robustez a ruído fora das posições vistas na amostra ───────────────────────
#
# Os três casos abaixo vêm do arnês de perturbação, não de leitura do gabarito.
# Cada um custava score medido antes de virar teste.


# As confusões testadas são as documentadas em docs/investigacao.md
# (0<->O, 1<->l, 5<->S, 9<->g, 6<->G). Inventar outras aqui aumentaria a
# superfície de falso positivo sem nenhuma medição que a justifique.
@pytest.mark.parametrize("ano", ["2024", "20\n24", "2O24", "2o24", "l995"])
def test_incompleta_sobrevive_a_ano_ruidoso(ano):
    """O ano é o único número da família `vaga`: corrompê-lo apagava a citação.

    Antes desta tolerância, `20\\n24` virava família `processo` — classe errada e
    span espúrio — e `2O24` não era detectado. Media-se a perda de 25 das 32
    `incompleta` sob ruído de OCR em número.
    """
    corpo = f"Cita-se o julgado do STF proferido em {ano} pela relatoria de Fulano de Tal."
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["vaga"]


@pytest.mark.parametrize("distrator", ["de 20\n24", "em 2O25", "fls. 76\n2/872"])
def test_distrator_ruidoso_continua_sendo_distrator(distrator):
    """Ano e página seguem não sendo citação quando o ruído os parte.

    Os filtros comparavam a forma bruta, então uma quebra de linha no meio do
    ano bastava para ele escapar e virar `processo`.
    """
    achados = _detectar(f"O feito tramitou {distrator} sem outras intercorrências.")
    assert achados == []


@pytest.mark.parametrize("rotulo", ["Autos", "Aiitos", "Proccsso", "Prot0colo"])
def test_numero_do_proprio_processo_nao_vaza_com_rotulo_corrompido(rotulo):
    """O distrator canônico do desafio, com o rótulo corrompido em uma letra.

    A fronteira do cabeçalho era achada por lista de rótulos exatos: uma letra
    trocada derrubava o corte e o número dos próprios autos virava citação.
    Agora a linha é reconhecida pela estrutura `<rótulo> nº <número>`.
    """
    cabecalho = (
        "MINISTÉRIO PÚBLICO MILITAR\n\n"
        f"{rotulo} nº 9293337-24.2018.7.15.8725\n"
        "Apelante: FULANO DE TAL\n\nPARECER\n\n"
    )
    achados = detectar(cabecalho + "Trata-se de apelação interposta contra sentença.")
    assert achados == []
