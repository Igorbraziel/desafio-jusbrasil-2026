"""As formas que o conjunto cego pode trazer e a amostra de desenvolvimento não tem.

Os testes das outras suítes descrevem o que a amostra mostra. Estes descrevem o
que ela **não** mostra — e por isso são os únicos que medem generalização, que é
o que decide o ranking: o leaderboard da fase de desenvolvimento roda sobre os
mesmos 26 documentos usados para construir a solução, e um F1 de 1,0 ali não é
evidência de nada.

Cada caso aqui foi um defeito medido no pipeline antes de virar teste. A
proveniência importa: nenhum deles vem de leitura do gabarito.

Os números e nomes são **sintéticos**, como nas demais suítes.
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


# ── Distratores numéricos que o gerador sintético não produziu ────────────────
#
# Contei `dd/mm/aaaa` nos 26 documentos da amostra: zero ocorrências. Nos
# acórdãos reais da base canônica: 200 de 200 documentos têm, 5.635 ocorrências
# no total. A ausência é artefato do gerador, não propriedade do domínio — e
# "publicado em <data>" é frase corrente em peça jurídica.


@pytest.mark.parametrize(
    "corpo",
    [
        "O período de 01/01/2020 a 31/12/2021 foi considerado pelo juízo.",
        "Publicado no DJe de 12/03/2021, o acórdão transitou em julgado.",
        "A sessão de 05/08/2019 confirmou o entendimento da Corte sobre o tema.",
        "Telefone (11) 98765-4321 consta dos autos do feito em análise.",
        "O fone (21) 91234-5678 foi informado pela parte na petição inicial.",
        "CEP 01310-100, endereço da parte recorrente indicado nos autos.",
        "O RG 12.345.678-9 foi juntado aos autos pela defesa técnica.",
        "A matrícula 987654-32 do imóvel foi averbada no cartório competente.",
    ],
)
def test_numero_que_nao_e_processo_nao_vira_citacao(corpo):
    """Identificador civil e data não são citação; extraí-los é falso positivo.

    `_TERMINA_EM_ANO` exigia que o número **inteiro** fosse `<n>/<ano>`, então a
    data tinha uma barra a mais e escapava de todos os filtros.
    """
    assert _detectar(corpo) == []


def test_data_no_meio_da_frase_nao_impede_a_citacao_vizinha():
    """O filtro de data não pode apagar a citação que divide a frase com ela."""
    achados = _detectar("Em 12/03/2021 firmou-se o REsp 1.234.567/SP sobre a matéria.")
    assert [a.trecho for a in achados] == ["REsp 1.234.567/SP"]


# ── `incompleta` em ordens que a amostra não usa ──────────────────────────────
#
# As 32 `incompleta` do gabarito são todas da forma tribunal + ano + relator,
# nessa ordem. `docs/investigacao.md` ressalva que "nada garante que o cego use
# as mesmas frases". Medindo estas oito reordenações antes da mudança: só duas
# eram detectadas.


@pytest.mark.parametrize(
    "corpo",
    [
        # a forma canônica da amostra, que precisa continuar valendo
        "Cita-se julgado do STF proferido em 2019 pela relatoria de Carlos Alberto.",
        # e as sete que ela não prevê
        "Cita-se acórdão, Rel. Min. Carlos Alberto, STF, 2019, sobre a matéria.",
        "Cita-se STF, 2019, Rel. Min. Carlos Alberto (acórdão) sobre a matéria.",
        "Cita-se precedente de 2019 do STF, relatado por Carlos Alberto, no ponto.",
        "Cita-se julgado relatado pelo Ministro Carlos Alberto no ano de 2019.",
        "Cita-se decisão da lavra do Ministro Carlos Alberto, de 2019, do STF.",
        "Cita-se aresto do STF de 2019, sob relatoria do Min. Carlos Alberto.",
        "Cita-se voto condutor do Min. Carlos Alberto no STF em 2019 a respeito.",
    ],
)
def test_incompleta_em_qualquer_ordem_dos_constituintes(corpo):
    """Relator + ano, sem número de processo, é `vaga` em qualquer ordem.

    O critério deixou de ser o casamento de uma frase e virou uma contagem de
    constituintes — ver `docs/referencias.md`, Harašta et al. (2020).
    """
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["vaga"]


def test_relator_sem_ano_nao_e_citacao():
    """A contagem exige os dois constituintes: relator sozinho não basta."""
    assert _detectar("O Ministro Carlos Alberto presidiu a sessão de julgamento.") == []


def test_ano_sem_relator_nao_e_citacao():
    """Simétrico ao anterior — ano solto continua sendo distrator."""
    assert _detectar("O feito tramitou desde 2019 sem outras intercorrências.") == []


def test_citacao_com_numero_nao_cai_na_familia_vaga():
    """Com número de processo a citação é resolvível: quem decide é a base.

    Sem esta exclusão a contagem de constituintes capturaria a frase inteira e
    roubaria o span da família `processo`.
    """
    corpo = "Ver o REsp 1.234.567/SP, de 2019, Rel. Min. Carlos Alberto, no ponto."
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["processo"]


# ── Ruído de OCR que a tabela de reparo conhece mas o núcleo não atravessava ───
#
# `OCR_PARA_DIGITO` mapeia 14 letras; a classe do núcleo era literal e listava 12,
# faltando `i` e `q`. O span sumia inteiro — recall, que não se recupera — mesmo
# com a normalização sabendo devolver o número certo. O gerador de perturbação
# tinha o mesmo buraco, então nenhuma medição de robustez via o defeito.


@pytest.mark.parametrize("corrompido", ["1737l8", "1737i8", "1737q8", "1737o8", "1737I8"])
def test_nucleo_atravessa_toda_confusao_que_o_reparo_desfaz(corrompido):
    """Se a tabela de reparo conhece a letra, a detecção tem de atravessá-la."""
    achados = _detectar(f"Ampara a pretensão o REsp {corrompido}/SP, citado nos autos.")
    assert [a.familia for a in achados] == ["processo"]


def test_numero_corrompido_resolve_para_os_digitos_certos():
    """Detectar não basta: o número recuperado tem de ser o mesmo das variantes."""
    from verificador.normalizacao import digitos_do_identificador

    recuperados = {
        digitos_do_identificador(_detectar(f"Ampara o REsp {c}/SP, citado.")[0].trecho)
        for c in ("173718", "1737l8", "1737i8", "1737I8")
    }
    assert recuperados == {"173718"}


@pytest.mark.parametrize("primeiro", ["1", "l", "I", "i"])
def test_primeiro_digito_corrompido_nao_muda_o_numero(primeiro):
    """A falha silenciosa: span válido, IoU bom, número errado.

    O núcleo abria com `\\d` literal, então `REsp l.599.910/PR` começava no `5` e
    devolvia `599910` — um número diferente, que não resolve na base e vira
    `inventada` com confiança alta. Medido, 79% das falhas de `ocr_numero`
    tinham o primeiro dígito corrompido.
    """
    from verificador.normalizacao import digitos_do_identificador

    achados = _detectar(f"Ampara o REsp {primeiro}.599.910/PR, citado nos autos.")
    assert len(achados) == 1
    assert digitos_do_identificador(achados[0].trecho) == "1599910"


@pytest.mark.parametrize(
    "prosa",
    [
        "Os Gols marcados no campeonato não interessam ao feito em análise.",
        "Isso posto, a defesa requer a improcedência total da demanda ali.",
        "O pedido de SOS foi registrado pela autoridade policial competente.",
        "As Obras do imóvel foram embargadas pela municipalidade no local.",
    ],
)
def test_palavra_digitoide_na_prosa_nao_vira_numero(prosa):
    """O contrapeso do núcleo tolerante, que foi o motivo da rejeição no cp 02.

    Palavras feitas só de letras confundíveis casam a forma do núcleo. Quem as
    barra são o lookbehind (letra antes de letra) e `_MINIMO_DIGITOS`, que exige
    quatro dígitos **reais** no casamento.
    """
    assert _detectar(prosa) == []


# ── A fronteira do cabeçalho não pode engolir a primeira linha do corpo ───────
#
# `_ROTULOS` era testado com `startswith`, então "Recurso especial interposto…"
# era classificado como cabeçalho. Como `fim_do_cabecalho` para na primeira linha
# que não é cabeçalho, uma dessas abrindo o corpo empurrava a fronteira para
# depois dela e a citação naquela linha era perdida.

_CABECALHO_CURTO = "PARECER Nº 10\nAutos nº 0801234-56.2021.8.19.0001\n\n"


@pytest.mark.parametrize(
    "primeira_linha",
    [
        "Recurso especial conhecido, cita-se o REsp 1.234.567/SP no ponto.",
        "Refere-se ao REsp 1.234.567/SP que a parte invoca nos autos.",
        "Processo eletrônico analisado conforme o REsp 1.234.567/SP citado.",
        "Autos conclusos, invoca-se o REsp 1.234.567/SP quanto à matéria.",
        "Origem da controvérsia é o REsp 1.234.567/SP, conforme a defesa.",
        "Classe recursal definida pelo REsp 1.234.567/SP, segundo a parte.",
    ],
)
def test_citacao_na_primeira_linha_do_corpo_nao_e_perdida(primeira_linha):
    """Prosa que apenas começa com um rótulo de metadado é prosa, não cabeçalho."""
    achados = detectar(_CABECALHO_CURTO + primeira_linha + "\nSegue a fundamentação.\n")
    assert [a.trecho for a in achados] == ["REsp 1.234.567/SP"]


@pytest.mark.parametrize(
    "linha",
    ["Autos", "Origem", "Classe", "Protocolo", "Autos 123456", "Valor da causa"],
)
def test_rotulo_sozinho_na_linha_continua_sendo_cabecalho(linha):
    """O contrapeso: a regra fica, para o rótulo que de fato é só rótulo."""
    from verificador.texto import _e_linha_de_cabecalho

    assert _e_linha_de_cabecalho(linha)
