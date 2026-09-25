"""O identificador precisa sobreviver ao ruído do nível 2.

Os casos abaixo reproduzem os **padrões de ruído** observados na amostra — cada
linha exercita uma transformação real (pontuação irregular, separador de UF,
quebra de linha, troca de OCR). Os números são sintéticos de propósito: o
gabarito não é público e não pode ser reproduzido aqui. Ver ``docs/dados.md``.
"""

import pytest

from verificador.normalizacao import (
    chave_textual,
    digitos_do_identificador,
    numeros_do_texto,
    separar_uf,
)

CASOS = [
    # nível 1: forma canônica
    ("REsp 1.234.567/SP", "1234567"),
    ("AgInt no AREsp nº 2.345.678/RJ", "2345678"),
    ("RSE nº 1234567-89.2025.7.00.0000/DF", "12345678920257000000"),
    ("Súmula Vinculante 99", "99"),
    # nível 2: pontuação irregular e separador de UF variado
    ("AgRg no Rec. Esp. n. 3.456.789 (SC)", "3456789"),
    ("Recurso em Habeas Corpus nº 45678 - SC", "45678"),
    ("Rec. Esp. No 4.567.890\n- SP", "4567890"),
    ("RESP n. 5 678 901/BA", "5678901"),
    ("Reclamação n° 56.- 789 (MA)", "56789"),
    ("APL 1234567-89 2021 7 00 0000/BA", "12345678920217000000"),
    # nível 2: confusões de OCR dentro do número
    ("AgInt no RESP 34567l9 - SP", "3456719"),
    ("R.Esp. n° 2.34g.567-MA", "2349567"),
    ("EDcl no AgInt no Recurso Especial Nº 345678O (SP)", "3456780"),
    ("AgRg no RESP 2.639.5S6/ RJ", "2639556"),
    # quebra de linha no meio do identificador
    ("TST-ED-E-ED-ARR-1234-56.2011.5.02.\n0251", "12345620115020251"),
    # OCR no meio de um número estruturado: a letra está entre separadores, e
    # não colada a dígito — a regra de adjacência não a alcançava e o núcleo
    # era partido ali. Os casos são os que sobravam como `real` → `inventada`
    # no arnês depois do checkpoint 07.
    ("TST-ED-E-ED-RR-4736-oS.Z013.5.23.0047", "47360520135230047"),
    ("TST-ED-E-ED-RR-4736-05.2013.S.23.0047", "47360520135230047"),
    ("RR-4B37-o6.20iO.5.13.0074", "48370620105130074"),
    ("TST-RR-43700-1G.2007.5.is.o04G", "437001620075150046"),
    ("ED-E-ED-RR-b7-43.201O.s.04.0073", "674320105040073"),
    # o primeiro grupo reduzido a uma letra solta, separado do resto por espaço
    ("Rec. Esp. nº l. 470.s37 – CE", "1470537"),
    ("EDcl no AgInt no ARESP l 74i 3b7/ SC", "1741367"),
]


@pytest.mark.parametrize(("trecho", "esperado"), CASOS)
def test_digitos_do_identificador(trecho, esperado):
    assert digitos_do_identificador(trecho) == esperado


def test_uf_nao_entra_no_numero():
    """O "S" de "/SP" é uma letra de OCR: sem separar a UF antes, vira um 5."""
    assert separar_uf("AREsp 1234567/SP") == ("AREsp 1234567", "SP")
    assert digitos_do_identificador("AREsp 1234567/SP") == "1234567"


def test_letra_so_vira_digito_colada_a_um_digito():
    assert digitos_do_identificador("REsp 1.234.567 DO STJ") == "1234567"


def test_chave_textual_remove_acento_e_caixa():
    assert chave_textual("Constituição  Federal\n") == "constituicao federal"


def test_numeros_do_texto_normaliza_pontuacao():
    texto = "RECURSO ESPECIAL Nº 1.234.567 - PR (2018/0116304-1)"
    assert "1234567" in numeros_do_texto(texto)


@pytest.mark.parametrize("uf", ["G0", "6O"])
def test_goias_corrompido_nao_entra_no_numero(uf):
    """GO é a única UF feita de duas letras que o OCR confunde com dígito.

    Corrompida, ela não era reconhecida como UF, o reparo a lia como `60` e o
    número ganhava dois dígitos: `REsp 1.234.567/G0` virava `123456760`.
    """
    assert digitos_do_identificador(f"REsp 1.234.567/{uf}") == "1234567"
    assert separar_uf(f"REsp 1.234.567/{uf}") == ("REsp 1.234.567", "GO")


def test_ultimo_grupo_60_continua_no_numero():
    """`60` puro é grupo de número, não Goiás corrompido."""
    assert digitos_do_identificador("REspe nº 281-60") == "28160"
