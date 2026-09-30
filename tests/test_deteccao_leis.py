"""Diplomas citados pelo nome e súmulas de tribunal fora dos cinco superiores.

A avaliação final roda sobre uma base nova, e nada garante que ela se limite
aos 13 artigos e às 5 súmulas da base de desenvolvimento. Estes testes afirmam
só a **detecção** — o span, a família e o grupo que leva o diploma ou o tribunal
à resolução. A classe fica de fora de propósito: é a resolução que decide se o
nome leva a um registro, e uma citação que não é detectada não chega até ela.

Os artigos e os números de súmula são **sintéticos**, como nas demais suítes.
"""

import pytest

from verificador.deteccao import detectar, sigla_do_tribunal

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


def _unico(corpo: str, trecho: str, familia: str):
    """O único achado do corpo, conferido pelo span inteiro e pela família."""
    achados = _detectar(corpo)
    assert [(a.trecho, a.familia) for a in achados] == [(trecho, familia)]
    achado = achados[0]
    inicio = len(CABECALHO) + corpo.index(trecho)
    assert (achado.inicio, achado.fim) == (inicio, inicio + len(trecho))
    return dict(achado.dados)


# ── Diploma pelo nome ─────────────────────────────────────────────────────────
#
# Nenhuma alternativa de `_DIPLOMA` casava "Lei de …" ou "Estatuto …", e a
# citação sumia inteira. O nome entra no grupo `diploma` com o complemento que
# o identifica, e o span para no fim do nome, antes da prosa.


@pytest.mark.parametrize(
    "diploma",
    [
        "Estatuto da Criança e do Adolescente",
        "Estatuto do Idoso",
        "Estatuto da Pessoa Idosa",
        "Estatuto da Advocacia",
        "Estatuto da Advocacia e da OAB",
        "Estatuto da Advocacia e da Ordem dos Advogados do Brasil",
        "Estatuto da OAB",
        "Estatuto do Desarmamento",
        "Estatuto da Pessoa com Deficiência",
        "Lei de Execução Penal",
        "Lei de Introdução às Normas do Direito Brasileiro",
        "Lei de Introdução ao Código Civil",
        "Lei Maria da Penha",
        "Lei de Drogas",
        "Lei Antidrogas",
        "Lei das Eleições",
        "Lei de Improbidade Administrativa",
        "Lei de Improbidade",
        "Lei dos Juizados Especiais",
        "Lei dos Juizados Especiais Cíveis e Criminais",
        "Lei dos Juizados Especiais Federais",
        "Lei da Ação Civil Pública",
        "Lei do Mandado de Segurança",
        "Lei de Execução Fiscal",
        "Lei de Execuções Fiscais",
        "Lei dos Crimes Hediondos",
        "Lei de Licitações",
        "Lei de Licitações e Contratos",
        "Nova Lei de Licitações e Contratos",
        "Lei de Inelegibilidade",
        "Lei das Inelegibilidades",
        "Lei da Ficha Limpa",
        "Lei Orgânica da Magistratura Nacional",
        "Lei de Responsabilidade Fiscal",
    ],
)
def test_diploma_pelo_nome_entra_inteiro_no_span(diploma):
    conector = "do" if diploma.startswith("Estatuto") else "da"
    trecho = f"art. 47 {conector} {diploma}"
    dados = _unico(f"Viola o {trecho} no ponto controvertido.", trecho, "dispositivo")
    assert dados["diploma"] == diploma
    assert dados["artigo"] == "47"


@pytest.mark.parametrize(
    ("corpo", "trecho", "diploma"),
    [
        # os qualificadores e a quebra de linha que o gerador põe no meio
        (
            "Viola o art. 58, § 3º, da Lei de Drogas no ponto.",
            "art. 58, § 3º, da Lei de Drogas",
            "Lei de Drogas",
        ),
        (
            "Viola o art. 4º da Lei de Introdução\nàs Normas do Direito Brasileiro, no ponto.",
            "art. 4º da Lei de Introdução\nàs Normas do Direito Brasileiro",
            "Lei de Introdução\nàs Normas do Direito Brasileiro",
        ),
        # o ruído de letra do nível 2 nas palavras-chave e nos conectores
        (
            "Viola o art. 5º da Lci dc Execucão Penal no ponto.",
            "art. 5º da Lci dc Execucão Penal",
            "Lci dc Execucão Penal",
        ),
        (
            "Viola o art. 98 d0 Estatuto dã Criança e d0 Adolescente no ponto.",
            "art. 98 d0 Estatuto dã Criança e d0 Adolescente",
            "Estatuto dã Criança e d0 Adolescente",
        ),
        (
            "Viola o art. 1º da Lei das Elcições no ponto.",
            "art. 1º da Lei das Elcições",
            "Lei das Elcições",
        ),
        # o ano de versão entra, como no nome dos códigos
        (
            "Viola o art. 87 da Lei de Licitações de 1993 no ponto.",
            "art. 87 da Lei de Licitações de 1993",
            "Lei de Licitações de 1993",
        ),
        # "nova" antes do nome muda o diploma e vai junto
        (
            "Viola o art. 87 da nova Lei de Licitações no ponto.",
            "art. 87 da nova Lei de Licitações",
            "nova Lei de Licitações",
        ),
    ],
)
def test_diploma_pelo_nome_com_ruido_e_qualificadores(corpo, trecho, diploma):
    assert _unico(corpo, trecho, "dispositivo")["diploma"] == diploma


def test_nome_do_diploma_em_caixa_alta():
    corpo = "A ementa do julgado é a seguinte.\nVIOLOU O ART. 58 DA LEI DE DROGAS NO PONTO."
    achados = _detectar(corpo)
    assert [(a.trecho, dict(a.dados)["diploma"]) for a in achados] == [
        ("ART. 58 DA LEI DE DROGAS", "LEI DE DROGAS")
    ]


def test_codigo_por_extenso_continua_inteiro():
    trecho = "art. 14 do Código de Defesa do Consumidor"
    dados = _unico(f"Viola o {trecho} no ponto.", trecho, "dispositivo")
    assert dados["diploma"] == "Código de Defesa do Consumidor"


# ── Siglas novas ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sigla", ["LEP", "LINDB", "LIDB", "LICC", "LOMAN", "LRF", "LEF"])
def test_sigla_nova_depois_do_conector(sigla):
    trecho = f"art. 47 da {sigla}"
    assert _unico(f"Viola o {trecho} no ponto.", trecho, "dispositivo")["diploma"] == sigla


@pytest.mark.parametrize("sigla", ["LEP", "LINDB", "LRF", "CF"])
def test_sigla_depois_de_virgula_vai_no_grupo_da_sigla(sigla):
    trecho = f"art. 5º, LV, {sigla}"
    dados = _unico(f"Viola o {trecho} no ponto.", trecho, "dispositivo")
    assert dados["diploma_sigla"] == sigla
    assert "diploma" not in dados


# ── O que não pode virar citação ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "corpo",
    [
        # a lista de nomes é fechada: "Lei de <qualquer coisa>" não é diploma
        "Viola o art. 5º da Lei de regência no ponto.",
        "Viola o art. 5º da Lei do Estado no ponto.",
        "Viola o art. 5º da Lei Orgânica do Município no ponto.",
        "Viola o art. 82 do Estatuto dos Militares no ponto.",
        # o nome sem o artigo não é dispositivo
        "A Lei de Drogas é severa com o tráfico.",
        "O Estatuto não trata da matéria.",
        "Viola o art. 5º do Estatuto no ponto.",
        # o nome não termina dentro de uma palavra
        "Viola o art. 5º da Lei de Drogasx no ponto.",
        # a sigla não casa dentro de palavra
        "Viola o art. 5º da LEPRA no ponto.",
        "Viola o art. 5º da COLEP no ponto.",
        "Viola o art. 5º, LEPX, no ponto.",
        "Viola o art. 5º da LRFs no ponto.",
    ],
)
def test_nome_ou_sigla_fora_da_lista_nao_vira_citacao(corpo):
    assert _detectar(corpo) == []


def test_sigla_mais_longa_nao_perde_a_letra_final():
    """`CPPM` continua inteiro: a fronteira de palavra não deixa casar `CPP`."""
    trecho = "art. 5º, CPPM"
    assert _unico(f"Viola o {trecho}, no ponto.", trecho, "dispositivo")["diploma_sigla"] == "CPPM"


def test_prosa_depois_do_nome_nao_entra_no_diploma():
    trecho = "art. 64 da Lei de Execução Penal"
    corpo = f"O {trecho} Assegura a progressão de regime."
    assert _unico(corpo, trecho, "dispositivo")["diploma"] == "Lei de Execução Penal"


@pytest.mark.parametrize(
    ("expressao", "texto"),
    [
        ("_DISPOSITIVO", "Viola o art. 5º da Lei"),
        ("_DISPOSITIVO", "Viola o art. 5º do Estatuto"),
        ("_REGIONAL_POR_EXTENSO", "Tribunal"),
        ("_REGIONAL_POR_EXTENSO", "Tribunal de Justiça"),
        ("_REGIONAL_DA_SUMULA", "TRF"),
    ],
)
def test_nome_longo_nao_explode_em_espaco_longo(expressao, texto):
    """O separador entre as palavras não é ambíguo: o custo continua linear.

    Mede a expressão nova, e não `detectar`: a da família `vaga` e o nome por
    extenso dos cinco superiores já custavam tempo quadrático nesse texto antes
    destes nomes.
    """
    import re
    import time

    from verificador import deteccao

    padrao = getattr(deteccao, expressao)
    expr = padrao if isinstance(padrao, re.Pattern) else re.compile(padrao, re.IGNORECASE)
    inicio = time.perf_counter()
    list(expr.finditer(texto + " " * 20000 + "x"))
    assert time.perf_counter() - inicio < 2


# ── Súmula de tribunal fora dos cinco superiores ──────────────────────────────
#
# Antes, "Súmula 7 do TJSP" saía com o span "Súmula 7" e sem tribunal. O
# tribunal agora entra no span e no grupo, e `sigla_do_tribunal` o devolve numa
# forma só, sem separador.


@pytest.mark.parametrize(
    ("tribunal", "sigla"),
    [
        ("TJSP", "TJSP"),
        ("TJ/SP", "TJSP"),
        ("TJ-SP", "TJSP"),
        ("TJDFT", "TJDFT"),
        ("TRF1", "TRF1"),
        ("TRF-1", "TRF1"),
        ("TRF 1ª Região", "TRF1"),
        ("TRF da 1ª Região", "TRF1"),
        ("TRT da 17ª Região", "TRT17"),
        ("TRT/22ª Região", "TRT22"),
        ("TRT-5", "TRT5"),
        ("TRE/SP", "TRESP"),
        ("TRE-MG", "TREMG"),
        ("TJMSP", "TJMSP"),
        ("TJM/MG", "TJMMG"),
        ("TJMG", "TJMG"),
        ("Tribunal de Justiça de São Paulo", "TJSP"),
        ("Tribunal de Justiça do Estado de São Paulo", "TJSP"),
        ("Tribunal de Justiça de Mato Grosso do Sul", "TJMS"),
        ("Tribunal Regional Federal da 1ª Região", "TRF1"),
        ("Tribunal Regional do Trabalho da Décima Sétima Região", "TRT17"),
        ("Tribunal Regional Eleitoral de Minas Gerais", "TREMG"),
    ],
)
def test_sumula_de_tribunal_regional_leva_o_tribunal(tribunal, sigla):
    trecho = f"Súmula 7 do {tribunal}"
    dados = _unico(f"Aplica-se a {trecho} ao caso.", trecho, "sumula")
    assert dados["numero"] == "7"
    assert sigla_do_tribunal(dados["tribunal_do"]) == sigla


@pytest.mark.parametrize(
    ("corpo", "trecho", "grupo", "sigla"),
    [
        ("Aplica-se a Súmula 7/TJSP ao caso.", "Súmula 7/TJSP", "tribunal", "TJSP"),
        ("Aplica-se a Súmula 7 (TJSP) ao caso.", "Súmula 7 (TJSP)", "tribunal_par", "TJSP"),
        ("Aplica-se a Súmula 7 da TNU ao caso.", "Súmula 7 da TNU", "tribunal_do", "TNU"),
        (
            "Aplica-se a Súmula 7 da Turma Nacional de Uniformização ao caso.",
            "Súmula 7 da Turma Nacional de Uniformização",
            "tribunal_do",
            "TNU",
        ),
        # a UF com a letra trocada por dígito e o nome partido pela quebra
        ("Aplica-se a Súmula 7 do TJ5P ao caso.", "Súmula 7 do TJ5P", "tribunal_do", "TJSP"),
        (
            "Aplica-se a Súmula 7 do Tribunal\nde Justiça de São Paulo ao caso.",
            "Súmula 7 do Tribunal\nde Justiça de São Paulo",
            "tribunal_do",
            "TJSP",
        ),
    ],
)
def test_sumula_regional_nas_demais_formas(corpo, trecho, grupo, sigla):
    assert sigla_do_tribunal(_unico(corpo, trecho, "sumula")[grupo]) == sigla


@pytest.mark.parametrize(
    "corpo",
    [
        # sem o estado ou a região, o nome não diz qual tribunal é
        "Aplica-se a Súmula 7 do Tribunal de Justiça ao caso.",
        "Aplica-se a Súmula 7 do Tribunal Regional ao caso.",
        "Aplica-se a Súmula 7 do Tribunal de origem ao caso.",
        # a sigla em minúscula é prosa, e a UF é o conjunto fechado
        "Aplica-se a Súmula 7 do tjsp ao caso.",
        "Aplica-se a Súmula 7 do TJX ao caso.",
        "Aplica-se a Súmula 7 do TJSPX ao caso.",
    ],
)
def test_tribunal_que_nao_se_identifica_fica_fora_do_span(corpo):
    _unico(corpo, "Súmula 7", "sumula")


def test_sigla_do_tj_nao_leva_a_prosa_em_caixa_alta():
    """Entre a sigla e a UF não cabe espaço: "TJ SE" seria o TJ de Sergipe."""
    corpo = "A ementa do julgado é a seguinte.\nAPLICA-SE A SÚMULA 7 DO TJ SE COUBER."
    assert [a.trecho for a in _detectar(corpo)] == ["SÚMULA 7 DO TJ"]


@pytest.mark.parametrize(
    ("corpo", "trecho", "sigla"),
    [
        ("Aplica-se a Súmula 83 do STJ ao caso.", "Súmula 83 do STJ", "STJ"),
        ("Aplica-se a Súmula 83 do 5TJ ao caso.", "Súmula 83 do 5TJ", "STJ"),
        ("Aplica-se a Súmula 331, item IV, do TST ao caso.", "Súmula 331, item IV, do TST", "TST"),
    ],
)
def test_sumula_dos_superiores_nao_muda(corpo, trecho, sigla):
    assert sigla_do_tribunal(_unico(corpo, trecho, "sumula")["tribunal_do"]) == sigla


@pytest.mark.parametrize(
    ("corpo", "trecho"),
    [
        # `tema` e `vaga` continuam nos cinco superiores
        ("Incide o Tema 1.046 do TJSP no caso.", "Tema 1.046"),
        (
            "Cita-se o julgado do STF proferido em 2024 pela relatoria de Fulano de Tal.",
            "julgado do STF proferido em 2024 pela relatoria de Fulano de Tal",
        ),
    ],
)
def test_tribunal_regional_nao_entra_nas_outras_familias(corpo, trecho):
    assert [a.trecho for a in _detectar(corpo)] == [trecho]
