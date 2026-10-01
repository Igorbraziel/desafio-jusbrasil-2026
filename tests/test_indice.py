"""O índice de números próprios, construído do banco, sem chave que não seja própria.

Cada chave do índice é um número que faz um registro responder como `real`. Uma
chave que não é o número do próprio processo — data da sessão, inscrição na
OAB, lei citada, tema ou ADI mencionados na ementa — transforma em `real` uma
citação `inventada` que por acaso use aquele número. É o erro que a métrica
multiplica pelo nível inteiro, e o gerador de `inventada` tira números
justamente dos que aparecem citados na base.

Como a base é a mesma no conjunto cego (cobertura congelada), estas
propriedades valem lá também: verificá-las aqui é verificá-las por inteiro.
Os números das sondas vêm dos acórdãos da base, não do gabarito.
"""

import re

import pytest
from conftest import BANCO, sem_dados

from verificador.base.canonica import BaseCanonica, construir_indice
from verificador.pipeline import processar_texto

pytestmark = sem_dados

CABECALHO = "PODER JUDICIÁRIO\nProcesso nº 1234567-89.2020.5.14.1391\n\nPARECER\n\n"


@pytest.fixture(scope="module")
def indice():
    return construir_indice(BANCO)


@pytest.fixture(scope="module")
def base(indice):
    return BaseCanonica(indice)


def _classes(base, citacao: str) -> list[str]:
    texto = CABECALHO + f"Invoca-se {citacao}, no ponto. Ainda que assim não fosse.\n"
    return [c.classificacao for c in processar_texto("x", texto, base).citacoes]


def test_todo_acordao_responde_por_algum_numero(indice):
    """Só um acórdão da base não tem número próprio nenhum: uma ata de sessão."""
    alcancados = {d for documentos in indice["numeros"].values() for d in documentos}
    orfaos = set(indice["registros"]) - alcancados
    assert len(orfaos) <= 1, sorted(orfaos)


def test_nenhuma_chave_e_data_ou_ano(indice):
    datas = [
        n
        for n in indice["numeros"]
        if re.fullmatch(r"(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(19|20)\d\d", n)
        or re.fullmatch(r"(19|20)\d\d", n)
    ]
    assert not datas, datas[:10]


@pytest.mark.parametrize(
    "citacao",
    [
        # números que aparecem na zona de identificação de algum acórdão sem
        # serem o número dele: data da sessão, ano, ementa, rol de partes, lei
        "a AR nº 2.019/DF",
        "o MS nº 1.969/DF",
        "a ADI nº 1.717/DF",
        "a ADI nº 1.988/DF",
        "a ADI nº 2.135/DF",
        "o RE nº 638.115/CE",
        "o MS nº 25.763/DF",
        "a Rcl nº 57.861/SP",
        "a Rcl nº 44.025/RO",
        "a Pet nº 1.990/DF",
        "o REsp nº 27.112.024/SP",
        "a Rcl nº 11.231/SP",
        "a Rcl nº 11.166/GO",
        "a Rcl nº 22.271/DF",
        "o HC nº 604.005/RJ",
    ],
)
def test_numero_citado_na_zona_de_identificacao_nao_e_chave(base, citacao):
    assert _classes(base, citacao) == ["inventada"]


@pytest.mark.parametrize(
    "citacao",
    [
        # o número próprio de acórdãos que ficavam fora do índice
        "o processo nº TST-E-ED-AIRR-74240-33.2006.5.04.0027",
        "o processo nº TST-E-ED-RR-373-84.2014.5.02.0446",
        "o REspe nº 222-25.2012.6.26.0095/SP",
        # e o de acórdãos que continuam, com o número completo
        "a AR nº 2.690/DF",
        "a AR nº 2.614/DF",
    ],
)
def test_numero_proprio_continua_chave(base, citacao):
    assert _classes(base, citacao) == ["real"]


# ── Desempate por classe processual ───────────────────────────────────────────
#
# Quando dois acórdãos distintos têm o mesmo número próprio, é porque um é
# incidente do outro: o agravo interno e os embargos de divergência no mesmo
# recurso especial, o recurso e o pedido de extensão, o recurso e os embargos de
# declaração. O que os separa é a classe no cabeçalho — e a citação traz a
# classe. O desempate antigo (maior texto) acertava metade desses casos.


@pytest.mark.parametrize(
    ("citacao", "documento_esperado"),
    [
        # os números vêm dos cabeçalhos da base; nenhum é citação do gabarito
        ("o RHC nº 90.861/RS", "doc_0214"),
        ("o PExt no RHC nº 90.861/RS", "doc_0217"),
        ("o AgInt no REsp nº 1.599.372/PR", "doc_0210"),
        ("o AgInt nos EDv nos EREsp nº 1.599.372/PR", "doc_0288"),
        ("o AgRg no REsp nº 2.015.694/SP", "doc_0328"),
        ("os EDcl no AgRg no REsp nº 2.015.694/SP", "doc_0306"),
        ("o REspe nº 281-60.2012.6.06.0033", "doc_0428"),
        ("os ED no REspe nº 281-60.2012.6.06.0033", "doc_0469"),
    ],
)
def test_desempate_escolhe_pela_classe(base, indice, citacao, documento_esperado):
    texto = CABECALHO + f"Invoca-se {citacao}, no ponto. Ainda que assim não fosse.\n"
    citacoes = processar_texto("x", texto, base).citacoes
    assert len(citacoes) == 1
    esperado = indice["registros"][documento_esperado]["id"]
    assert (citacoes[0].classificacao, citacoes[0].id_canonico) == ("real", esperado)
