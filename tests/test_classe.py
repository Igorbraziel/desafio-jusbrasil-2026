"""As marcas de classe processual, dos dois lados do desempate.

A citação escreve a classe em sigla ("AgInt nos EDv nos EREsp"); o cabeçalho do
acórdão, por extenso e às vezes colado ("AgInt nosEMBARGOS DE DIVERGÊNCIA EM
RESP"). As duas formas precisam dar as mesmas marcas.
"""

import pytest

from verificador.classe import afinidade, marcas


@pytest.mark.parametrize(
    ("trecho", "esperado"),
    [
        ("RHC nº 12.345/RS", {"rhc"}),
        ("PExt no RECURSO EM HABEAS CORPUS", {"pext", "rhc"}),
        ("AgInt no Recurso Especial nº 1.234.567 - PR", {"agint", "resp"}),
        ("AgInt nos EDv nos EREsp nº 1.234.567/PR", {"agint", "edv"}),
        # a preposição colada ao nome da classe, como vem no cabeçalho
        ("AgInt nosEMBARGOS DE DIVERGÊNCIA EM RESP", {"agint", "edv", "resp"}),
        ("EDcl no AgRg no REsp nº 1.234.567/SP", {"edcl", "agrg", "resp"}),
        ("EMBARGOS DE DECLARAÇÃO NO RECURSO ESPECIAL ELEITORAL", {"edcl", "respe"}),
    ],
)
def test_marcas_da_classe(trecho, esperado):
    assert marcas(trecho) == esperado


def test_incidente_que_so_um_lado_tem_afasta():
    citacao = marcas("AgInt no REsp nº 1.234.567/PR")
    recurso = marcas("AgInt no RECURSO ESPECIAL")
    divergencia = marcas("AgInt nosEMBARGOS DE DIVERGÊNCIA EM RESP")
    assert afinidade(citacao, recurso) > afinidade(citacao, divergencia)
