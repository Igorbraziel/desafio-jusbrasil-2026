"""O arnês de perturbação, que é o que valida todas as medições de robustez.

Sem estes testes o arnês era o único componente do repositório sem cobertura —
e ele é justamente o instrumento. Se o mapa de offsets regredir, toda tabela de
robustez passa a medir o arnês em vez do pipeline, e nada quebra para avisar.

A sanidade central está em `test_taxa_zero_*`: com taxa 0 o corpus perturbado
tem de ser byte a byte o original, e os offsets do gabarito têm de sobreviver
intactos. É a checagem que `scripts/medir_robustez.py` declara obrigatória; aqui
ela vira teste.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from perturbar import (  # noqa: E402
    _OCR_DIGITO,
    _OCR_LETRA,
    CLASSES,
    _aplicar,
    perturbar,
)

TEXTO = (
    "DO MÉRITO\n\n"
    "Ampara a pretensão o REsp nº 1.234.567/SP, de relatoria do Ministro "
    "Fulano de Tal, julgado em 2019 pela Terceira Turma desta Corte.\n"
)


# ── As duas invariantes que o gerador não pode violar ─────────────────────────


def test_digito_nunca_vira_digito():
    """Trocar dígito por dígito faria uma `real` ruidosa virar `inventada` de fato.

    A organização garante que isso não acontece nos dados do desafio; um arnês
    que o violasse mediria um problema que a tarefa não tem.
    """
    assert all(not letra.isdigit() for letras in _OCR_DIGITO.values() for letra in letras)


def test_o_reparo_cobre_tudo_que_o_gerador_produz():
    """O contrato entre o arnês e o normalizador, verificado nos dois sentidos.

    O gerador é escrito à parte de `OCR_PARA_DIGITO` de propósito — derivá-lo do
    reparo tornaria a medição circular. O preço dessa independência é que as duas
    tabelas podem divergir em silêncio, e foi o que aconteceu: `i` e `q` estavam
    no reparo e fora do gerador, e nenhuma medição de robustez exercitou esses
    caminhos. Este teste é o que torna a divergência barulhenta.
    """
    from verificador.normalizacao import OCR_PARA_DIGITO

    for digito, letras in _OCR_DIGITO.items():
        for letra in letras:
            assert letra in OCR_PARA_DIGITO, f"o gerador produz {letra!r}, que o reparo não desfaz"
            assert OCR_PARA_DIGITO[letra] == digito, (
                f"o gerador troca {digito!r} por {letra!r}, "
                f"mas o reparo devolve {OCR_PARA_DIGITO[letra]!r}"
            )


def test_ruido_de_prosa_nunca_cria_digito():
    """Letra->letra na prosa: criar sequência numérica inventaria citação."""
    assert all(not any(c.isdigit() for c in v) for v in _OCR_LETRA.values())


# ── O mapa de offsets ─────────────────────────────────────────────────────────


def test_mapa_e_identidade_sem_trocas():
    resultado = _aplicar(TEXTO, [], [])
    assert resultado.texto == TEXTO
    assert resultado.mapa == tuple(range(len(TEXTO) + 1))


def test_mapa_traduz_span_apos_troca_que_encurta():
    """`rn` -> `m` encurta: tudo depois anda para trás pelo mesmo delta."""
    original = "abcd RESP 123 efgh"
    alvo = original.index("efgh")
    resultado = _aplicar(original, [(0, 4, "ab")], [])
    inicio, fim = resultado.traduzir(alvo, alvo + 4)
    assert resultado.texto[inicio:fim] == "efgh"


def test_mapa_traduz_span_apos_troca_que_alonga():
    """`m` -> `rn` alonga, e é o caso que mais exercita o mapa."""
    original = "abcd RESP 123 efgh"
    alvo = original.index("efgh")
    resultado = _aplicar(original, [(0, 4, "abcdef")], [])
    inicio, fim = resultado.traduzir(alvo, alvo + 4)
    assert resultado.texto[inicio:fim] == "efgh"


def test_mapa_define_o_fim_exclusivo():
    """`mapa[len(original)]` precisa existir: é o fim exclusivo de um span final."""
    resultado = _aplicar(TEXTO, [(0, 2, "XYZ")], [])
    assert len(resultado.mapa) == len(TEXTO) + 1
    assert resultado.mapa[len(TEXTO)] == len(resultado.texto)


def test_troca_sobreposta_e_descartada_sem_corromper_o_mapa():
    """Descartar a segunda troca é o contrato; corromper o mapa não é."""
    original = "abcdefgh"
    resultado = _aplicar(original, [(0, 4, "XX"), (2, 6, "YY")], [])
    assert resultado.texto == "XXefgh"
    alvo = original.index("efgh")
    inicio, fim = resultado.traduzir(alvo, alvo + 4)
    assert resultado.texto[inicio:fim] == "efgh"


# ── Taxa zero: a sanidade que o arnês declara obrigatória ─────────────────────


@pytest.mark.parametrize("classe", CLASSES)
def test_taxa_zero_preserva_o_texto(classe):
    resultado = perturbar(TEXTO, [(0, len(TEXTO), "real")], [classe], 0.0, semente=7)
    assert resultado.texto == TEXTO


@pytest.mark.parametrize("classe", CLASSES)
def test_taxa_zero_preserva_os_offsets(classe):
    spans = [(11, 44, "real")]
    resultado = perturbar(TEXTO, spans, [classe], 0.0, semente=7)
    for inicio, fim, _ in spans:
        assert resultado.traduzir(inicio, fim) == (inicio, fim)


# ── Com ruído, o span traduzido ainda cobre a citação ─────────────────────────


@pytest.mark.parametrize("classe", CLASSES)
@pytest.mark.parametrize("semente", [0, 1, 2])
def test_span_traduzido_continua_ancorado(classe, semente):
    """O texto sob o span traduzido tem de ser o mesmo, módulo o ruído aplicado.

    A checagem possível sem reimplementar o ruído: o span traduzido é válido,
    não-vazio e cabe no texto novo. Um mapa corrompido viola alguma das três.
    """
    inicio, fim = 31, 55  # "REsp nº 1.234.567/SP, de"
    resultado = perturbar(TEXTO, [(inicio, fim, "real")], [classe], 0.4, semente=semente)
    novo_inicio, novo_fim = resultado.traduzir(inicio, fim)
    assert 0 <= novo_inicio < novo_fim <= len(resultado.texto)


# ── As classes que medem o ruído que o gerador do desafio já mostrou ──────────
#
# Três formas estão no nível 2 da amostra e o arnês não gerava: letra trocada por
# dígito dentro de palavra ("5úmula", "C0NTROVÉRSIA"), a sigla do tribunal
# corrompida ("5TJ") e a palavra curta corrompida ("dc", "dã" no lugar de "de",
# "da"). Sem elas, nenhuma medição exercitava esses caminhos.


def test_ocr_letra_digito_nunca_cria_numero():
    """O dígito entra sozinho, no meio de letras: nunca forma número citável."""
    import re

    texto = "Aplica-se a Súmula do Superior Tribunal, conforme a controvérsia posta nos autos. " * 5
    resultado = perturbar(texto, [], ["ocr_letra_digito"], 1.0, semente=3)
    assert resultado.texto != texto
    assert not re.search(r"\d{2}", resultado.texto)
    assert all(
        sum(c.isdigit() for c in palavra) <= 1 for palavra in re.findall(r"\w+", resultado.texto)
    )


def test_sigla_tribunal_corrompe_so_a_sigla():
    texto = "Súmula 83 do STJ e acórdão do TST, publicados."
    resultado = perturbar(texto, [], ["sigla_tribunal"], 1.0, semente=1)
    assert resultado.texto.replace("5", "S") == texto


def test_ocr_curta_corrompe_palavras_de_duas_e_tres_letras():
    texto = "art. 5º da Constituição e o art. 186 do Código Civil, de 2002."
    resultado = perturbar(texto, [], ["ocr_curta"], 1.0, semente=2)
    assert resultado.texto != texto
    longas = [p for p in texto.split() if len(p.strip(".,")) > 3]
    assert all(p in resultado.texto for p in longas)
