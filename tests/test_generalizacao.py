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
