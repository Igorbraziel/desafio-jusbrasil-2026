"""Número solto na prosa não é número de processo.

A organização avisou que a avaliação final roda sobre uma base nova. Até aqui, um
número de quatro ou cinco dígitos na prosa — prazo, pena, área, contagem de votos
— virava citação `processo`: falso positivo `inventada` em qualquer base, e
`real` espúrio quando coincidia com o número próprio curto de algum acórdão.
Medido por sonda no dev, "de <n> dias" e "<n> metros quadrados" resolviam para
acórdãos da base, e "art. <n> do Regimento Interno" também.

Os números são **sintéticos** e foram conferidos contra o índice e o gabarito do
dev: nenhum deles é chave de acórdão nem trecho de citação. O que se testa é a
forma da prosa em volta, não o número.
"""

import pytest

from verificador.deteccao import detectar

CABECALHO = (
    "EXCELENTÍSSIMO SENHOR MINISTRO RELATOR\n"
    "SUPERIOR TRIBUNAL DE JUSTIÇA\n"
    "\n"
    "Autos nº 4309330-25.2016.3.05.9083\n"
    "\n"
    "PARECER\n"
    "\n"
)


def _detectar(corpo: str):
    return detectar(CABECALHO + corpo)


def _trechos(corpo: str) -> list[str]:
    return [a.trecho for a in _detectar(corpo)]


# Linha toda em caixa alta logo depois do cabeçalho é lida como título dele
# (`fim_do_cabecalho`); a prosa na frente põe a ementa no corpo.
_EMENTA = "A ementa do julgado é a seguinte.\n"


# ── Unidade ou substantivo de quantidade depois do número ─────────────────────


@pytest.mark.parametrize(
    "corpo",
    [
        # os casos da sonda que motivou a regra, com números sintéticos
        "O prazo foi de 1750 dias até a sentença.",
        "A área tem 3.480 metros quadrados.",
        "Foram apreendidos 2.640 gramas de entorpecente.",
        "A pena foi fixada em 1960 dias-multa.",
        "O réu percorreu 13.570 km.",
        # as demais unidades e quantidades da lista fechada
        "A obra levou 1.235 horas de trabalho.",
        "O imóvel mede 5.130 m² de área construída.",
        "Foram 8.650 quilômetros percorridos pela frota.",
        "Apreenderam-se 6.240 kg de soja no depósito.",
        "Transportaram-se 9.870 toneladas de minério.",
        "Foram consumidos 2.417 litros de combustível.",
        "A multa chegou a 1.236 salários-mínimos.",
        "Compareceram 5.130 pessoas ao comício.",
        "O candidato obteve 8.650 votos no pleito.",
        "Visitou o local 1.236 vezes no período.",
        "Foram distribuídas 6.240 unidades do material.",
        "O laudo tem 2.417 páginas.",
        "O percentual subiu 3.480% no período.",
        "O índice subiu 3.480 por cento no período.",
        "Foram apreendidas 1.235 munições calibre .38.",
    ],
)
def test_numero_seguido_de_unidade_nao_vira_processo(corpo):
    assert _detectar(corpo) == []


@pytest.mark.parametrize(
    "corpo",
    [
        # caixa alta, como nas ementas
        _EMENTA + "PENA DE 1.960 DIAS-MULTA E REGIME FECHADO.",
        # o número por extenso entre parênteses, como a peça escreve pena e valor
        "A pena foi de 1.960 (mil novecentos e sessenta) dias-multa.",
        # a unidade colada ao número, e a de uma letra que o núcleo engolia
        "Foram apreendidos 12.640kg de soja.",
        "Foram apreendidos 2.640 g de cocaína.",
        "Foram apreendidos 2.640g de cocaína.",
        # a faixa, em que a unidade só vem depois do segundo número
        "Compareceram de 1.236 a 2.417 pessoas.",
        # o decimal com vírgula antes da unidade
        "Foram consumidos 2.417,5 litros de combustível.",
        # a unidade na linha seguinte
        "O imóvel tem área de 3.480\nmetros quadrados.",
        # a maiúscula que abre a frase não é sigla de classe
        "Foram 13.570 eleitores afetados.",
    ],
)
def test_quantidade_em_formas_correntes_nao_vira_processo(corpo):
    assert _detectar(corpo) == []


@pytest.mark.parametrize(
    "corpo",
    [
        "Cerca de 13.570 eleitores foram afetados.",
        "Aproximadamente 5.130 famílias foram atendidas.",
        "Foram distribuídas mais de 6.240 reclamações no ano.",
        "O prazo foi reduzido a menos de 1.235 horas.",
        "O dano chegou a quase 8.650 hectares de mata.",
        "O total de 9.870 cadastros foi revisto.",
        "A frota percorreu no máximo 2.417 trajetos.",
        "O prejuízo foi estimado em US$ 3.480 pelo perito.",
    ],
)
def test_numero_depois_de_quantificador_nao_vira_processo(corpo):
    """O quantificador encosta no número: não sobra lugar para classe entre os dois."""
    assert _detectar(corpo) == []


# ── Artigo que a família `dispositivo` não reconheceu ─────────────────────────


@pytest.mark.parametrize(
    "corpo",
    [
        # diploma fora da lista de `_DIPLOMA`: o número vazava para `processo`
        "Nos termos do art. 1.750 do Regimento Interno, o recurso não cabe.",
        "O artigo 1.750 do Regimento Interno trata da matéria.",
        "Nos termos do art. nº 1.750 do Regimento Interno, o recurso não cabe.",
        # o plural não casa `_DISPOSITIVO`, e a enumeração soltava o segundo número
        "Nos termos dos arts. 1.036 e 1.037 do CPC, o recurso foi afetado.",
        "Aplicam-se os arts. 1.036 a 1.041 do CPC ao caso.",
        "Violou os artigos 1.036, 1.037 e 1.041 do CPC, segundo a parte.",
        _EMENTA + "ARTIGOS 489 E 1.037 DO CPC/2015. INOCORRÊNCIA.",
    ],
)
def test_numero_de_artigo_nao_vira_processo(corpo):
    assert [a.familia for a in _detectar(corpo)] == []


def test_segundo_numero_da_enumeracao_de_temas_nao_vira_processo():
    """O primeiro tema é da família `tema`; o segundo vazava para `processo`."""
    achados = _detectar("Incidem os Temas 1.046 e 1.191 do STF.")
    assert [a.familia for a in achados] == ["tema"]


# ── O que não pode quebrar ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        ("Ampara a pretensão o HC 123.456/SP, citado.", "HC 123.456/SP"),
        ("Ampara a pretensão o REsp nº 1.234.567/SP, citado.", "REsp nº 1.234.567/SP"),
        ("Ampara a pretensão a Rcl 12.345, citada.", "Rcl 12.345"),
        (
            "Ampara a pretensão o processo 1234567-89.2020.8.26.0100, citado.",
            "processo 1234567-89.2020.8.26.0100",
        ),
        ("Ampara a pretensão o processo nº 1234, citado.", "processo nº 1234"),
        ("Ampara a pretensão o REsp 1.23g.456/SP, citado.", "REsp 1.23g.456/SP"),
        ("Ampara a pretensão o RO nº 1.662/SP, citado.", "RO nº 1.662/SP"),
    ],
)
def test_citacao_com_classe_ou_marca_continua_detectada(corpo, esperado):
    assert _trechos(corpo) == [esperado]


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        # a classe colada ao número vence a unidade que vem depois
        ("Ver a Rcl 12.345 dias depois do julgamento.", "Rcl 12.345"),
        ("Ver o processo nº 1234 dias depois do julgamento.", "processo nº 1234"),
        # o quantificador que não encosta no número não recusa a citação
        ("Cerca de dez dias depois, o REsp 1.234.567/SP foi julgado.", "REsp 1.234.567/SP"),
        # "até" e "entre" também introduzem processo: número longo não é quantia
        (
            "Ficam suspensos até 1234567-89.2020.8.26.0100, e os demais feitos seguem.",
            "1234567-89.2020.8.26.0100",
        ),
        # a classe por extenso termina em adjetivo ou complemento, e o núcleo que
        # a nomeia fica mais à esquerda na cadeia
        ("Ver o Habeas Corpus 123.456 dias depois.", "Habeas Corpus 123.456"),
        ("Ver o Mandado de Segurança 12.345 dias depois.", "Mandado de Segurança 12.345"),
        (
            "Ver o Recurso Especial 1.234.567 anos depois.",
            "Recurso Especial 1.234.567",
        ),
        # o 9 corrompido no fim do número não é a unidade "g"
        ("Ampara a pretensão o REsp 1.234.56g/SP, citado.", "REsp 1.234.56g/SP"),
        # a unidade na frase seguinte não alcança o número
        ("Ampara a pretensão o HC nº 123.456 - SP, com 3 votos.", "HC nº 123.456 - SP"),
    ],
)
def test_regra_de_quantidade_nao_apaga_a_citacao(corpo, esperado):
    assert _trechos(corpo) == [esperado]


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        # o artigo e o processo coordenados: o rótulo não alcança a classe
        (
            "Invoca-se o art. 5º da CF e REsp 1.234.567/SP, no ponto.",
            ["art. 5º da CF", "REsp 1.234.567/SP"],
        ),
        (
            "Viola o art. 1.750 do Regimento Interno e o REsp 1.234.567/SP.",
            ["REsp 1.234.567/SP"],
        ),
        # a quantidade e o processo na mesma frase
        (
            "Foram 2.417 votos, conforme o REsp 1.234.567/SP.",
            ["REsp 1.234.567/SP"],
        ),
    ],
)
def test_filtro_nao_derruba_a_citacao_vizinha(corpo, esperado):
    assert _trechos(corpo) == esperado


@pytest.mark.parametrize(
    "corpo",
    [
        # a enumeração com marca de número no plural continua citação
        "Nas Ações Diretas de Inconstitucionalidade ns. 3.480 e 9.870, processos nos quais.",
        # a Sentença Estrangeira em sigla, que tem a forma da palavra "se"
        "A SE 5.206 foi homologada no ponto.",
    ],
)
def test_numero_com_marca_ou_classe_antes_da_virgula_continua_citacao(corpo):
    assert [a.familia for a in _detectar(corpo)] and all(
        a.familia == "processo" for a in _detectar(corpo)
    )


def test_quantidade_vizinha_nao_impede_a_vaga():
    """A exclusão da `vaga` usa `_e_numero_de_processo`, que não mudou: a
    quantidade na mesma frase continua sem virar citação, e a `vaga` segue."""
    corpo = "Cita-se o julgado do STF proferido em 2019 pela relatoria de Fulano de Tal."
    assert [a.familia for a in _detectar(corpo)] == ["vaga"]
