"""O identificador precisa sobreviver ao ruído do nível 2.

Todos os casos abaixo são citações reais do goldenset — a forma da esquerda
aparece no documento, o número da direita é o que a base canônica indexa.
"""

import pytest

from verificador.normalizacao import (
    chave_textual,
    digitos_do_identificador,
    numeros_do_texto,
    separar_uf,
)

# Estes testes são a **especificação** da etapa: descrevem o comportamento
# esperado antes de ele existir. Enquanto o módulo for um stub, ficam marcados
# como falha esperada para que `make testar` continue verde. Vá removendo o
# marcador conforme implementar.
pytestmark = pytest.mark.xfail(raises=NotImplementedError, reason="a implementar", strict=False)


CASOS = [
    # nível 1: forma canônica
    ("REsp 1.234.567/SP", "1234567"),
    ("AgInt no AREsp nº 1.996.496/RJ", "1996496"),
    ("RSE nº 7000592-58.2025.7.00.0000/DF", "70005925820257000000"),
    ("Súmula Vinculante 10", "10"),
    # nível 2: pontuação irregular e separador de UF variado
    ("AgRg no Rec. Esp. n. 1.522.200 (SC)", "1522200"),
    ("Recurso em Habeas Corpus nº 93967 - SC", "93967"),
    ("Rec. Esp. No 1.880.529\n- SP", "1880529"),
    ("RESP n. 1 307 026/BA", "1307026"),
    ("Reclamação n° 33.- 474 (MA)", "33474"),
    ("APL 7000761-84 2021 7 00 0000/BA", "70007618420217000000"),
    # nível 2: confusões de OCR dentro do número
    ("AgInt no RESP 21737l8 - SP", "2173718"),
    ("R.Esp. n° 1.45g.779-MA", "1459779"),
    ("EDcl no AgInt no Recurso Especial Nº 170076O (SP)", "1700760"),
    ("AgRg no RESP 1.528.4S5/ RJ", "1528455"),
    # quebra de linha no meio do identificador
    ("TST-ED-E-ED-ARR-1099-66.2011.5.02.\n0251", "10996620115020251"),
]


@pytest.mark.parametrize(("trecho", "esperado"), CASOS)
def test_digitos_do_identificador(trecho, esperado):
    assert digitos_do_identificador(trecho) == esperado


def test_uf_nao_entra_no_numero():
    """O "S" de "/SP" é uma letra de OCR: sem separar a UF antes, vira um 5."""
    assert separar_uf("AREsp 1576933/SP") == ("AREsp 1576933", "SP")
    assert digitos_do_identificador("AREsp 1576933/SP") == "1576933"


def test_letra_so_vira_digito_colada_a_um_digito():
    assert digitos_do_identificador("REsp 1.234.567 DO STJ") == "1234567"


def test_chave_textual_remove_acento_e_caixa():
    assert chave_textual("Constituição  Federal\n") == "constituicao federal"


def test_numeros_do_texto_normaliza_pontuacao():
    texto = "RECURSO ESPECIAL Nº 1.741.784 - PR (2018/0116304-1)"
    assert "1741784" in numeros_do_texto(texto)
