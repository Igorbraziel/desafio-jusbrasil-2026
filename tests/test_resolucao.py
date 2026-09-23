"""Da citação detectada à classe: a especificação de `resolucao.py`.

O módulo produz a classe final e o `id_canonico` — é o que a métrica pontua —, e
até esta suíte não tinha nenhum teste dedicado. Os cinco bugs `inventada` →
`real` do checkpoint 05 foram corrigidos reordenando uma tupla, sem rede: trocar
a ordem de `DIPLOMAS` não quebrava nada.

`inventada` → `real` é o único erro que a métrica pune multiplicativamente
(`s = macroF1 × (1 − 0,5·τ)`), cerca de sete vezes mais caro que um falso
positivo comum. Por isso a maior parte dos casos aqui é de citação **fora** da
cobertura que precisa continuar `inventada`.

Os 18 ids de súmula e dispositivo vêm da tabela curada, conferida contra o banco
em `test_base_canonica.py`. Os textos são sintéticos, como nas demais suítes.
"""

import pytest
from conftest import sem_indice

from verificador.base_canonica import DISPOSITIVOS, SUMULAS
from verificador.deteccao import detectar
from verificador.resolucao import resolver

pytestmark = sem_indice


def _classificar(base, citacao: str) -> list[tuple[str, int | None]]:
    """Detecta e resolve uma citação isolada, com prosa em volta."""
    texto = f"Invoca-se, no ponto, o {citacao}, como bem lembrado pela defesa."
    return [resolver(a, base)[:2] for a in detectar(texto)]


# ── A cobertura inteira resolve para `real` ───────────────────────────────────


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("art. 5º da Constituição Federal", ("CF", 5)),
        ("art. 7º da Constituição da República", ("CF", 7)),
        ("art. 93 da CF/88", ("CF", 93)),
        ("art. 373 do Código de Processo Civil", ("CPC", 373)),
        ("art. 373 da Lei nº 13.105/2015", ("CPC", 373)),
        ("art. 186 do Código Civil", ("CC", 186)),
        ("art. 312 do Código de Processo Penal", ("CPP", 312)),
        ("art. 290 do Código Penal Militar", ("CPM", 290)),
        ("art. 14 do Código de Defesa do Consumidor", ("CDC", 14)),
        ("art. 477 da CLT", ("CLT", 477)),
        ("art. 818 da Consolidação das Leis do Trabalho", ("CLT", 818)),
        ("art. 896 da CLT", ("CLT", 896)),
        ("art. 276 do Código Eleitoral", ("ELEITORAL", 276)),
        ("art. 1º da Lei Complementar nº 64/1990", ("LC64", 1)),
    ],
)
def test_dispositivo_da_cobertura_e_real(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("Súmula 83 do STJ", ("STJ", False, 83)),
        ("Súmula 211 do STJ", ("STJ", False, 211)),
        ("Súmula 443 do STJ", ("STJ", False, 443)),
        ("Súmula 331 do TST", ("TST", False, 331)),
        ("Súmula Vinculante 10", ("STF", True, 10)),
    ],
)
def test_sumula_da_cobertura_e_real(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", SUMULAS[chave])]


# ── Formas que a detecção passou a entregar, e que a resolução precisa ler ────
#
# Detectar `art. I86` não basta: o número que chega à base tem de ser `186`.
# `_inteiro` descartava as letras, então `I86` virava `86` — e, pior, `3l73`
# virava `373`, que é artigo da cobertura: uma `inventada` resolvida como
# `real`, o erro grave. O reparo de OCR tem de vir **antes** de extrair dígitos.


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("artigo I86 do Código Civil", ("CC", 186)),
        ("art. B96 da CLT", ("CLT", 896)),
        ("art. 29O do Código Penal Militar", ("CPM", 290)),
        ("art z7G do Código Eleitoral", ("ELEITORAL", 276)),
    ],
)
def test_artigo_com_ruido_resolve_para_o_numero_reparado(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("Súmula B3 do STJ", ("STJ", False, 83)),
        ("Súmula 33l do TST", ("TST", False, 331)),
        ("Súmula nº 211 do STJ", ("STJ", False, 211)),
        ("Súmula n. 443 do STJ", ("STJ", False, 443)),
    ],
)
def test_sumula_com_ruido_resolve_para_o_numero_reparado(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", SUMULAS[chave])]


def test_letra_no_meio_do_artigo_nao_encolhe_o_numero(base_canonica):
    """`3l73` é o artigo 3.173, não o 373 — que está na cobertura."""
    assert _classificar(base_canonica, "art. 3l73 do CPC") == [("inventada", None)]


# ── Diploma nomeado pela forma que a base usa ─────────────────────────────────


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        # a primeira linha autodeclarada dos registros traz o número da lei; a
        # CLT e o CC eram os dois que `DIPLOMAS` não reconhecia por ele
        ("art. 818 do Decreto-Lei nº 5.452/1943", ("CLT", 818)),
        ("art. 186 da Lei nº 10.406/2002", ("CC", 186)),
        ("art. 1º da LC 64/1990", ("LC64", 1)),
        # a Constituição pelos nomes que identificam a de 1988, com e sem ano
        ("art. 93 da Constituição Federal de 1988", ("CF", 93)),
        ("art. 5º da Constituição do Brasil", ("CF", 5)),
        ("art. 5º da Constituição da República Federativa do Brasil", ("CF", 5)),
        ("art. 7º, XXIX, da Constituição Fedcral", ("CF", 7)),
        ("art. 373 do Código de Processo Civil de 2015", ("CPC", 373)),
        # "5o" é o ordinal em texto simples, não um 50 corrompido
        ("art. 5o da Constituição Federal", ("CF", 5)),
        # os qualificadores que o inciso e o caput trazem não mudam o registro
        ("art. 5º, caput, da Constituição Federal", ("CF", 5)),
        ("art. 5º, LXXVIII, da Constituição Federal", ("CF", 5)),
        ("art. 373, incisos I e II, do CPC", ("CPC", 373)),
    ],
)
def test_diploma_pela_forma_da_base(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


# ── Fora da cobertura é `inventada` — o erro grave mora aqui ──────────────────


@pytest.mark.parametrize(
    "citacao",
    [
        # os cinco do checkpoint 05, que nunca viraram teste
        "art. 1º da Lei Complementar nº 123/2006",
        "art. 1º da Lei Complementar nº 101/2000",
        "art. 5º da Constituição Estadual",
        "art. 93 da Constituição do Estado",
        "art. 312 do Código de Processo Penal Militar",
        # a exclusão era uma lista de qualificadores ruins conhecidos, então
        # qualquer outro passava e resolvia para a CF/88
        "art. 5º da Constituição Portuguesa",
        "art. 5º da Constituição Espanhola",
        "art. 5º da Constituição de 1967",
        "art. 5º da Constituição do Brasil de 1967",
        "art. 5º da Constituição Mineira",
        # "5O" maiúsculo é a confusão de OCR documentada, não ordinal: lê-lo como
        # 5º levaria o art. 50 da CF, fora da cobertura, ao art. 5º
        "art. 5O da Constituição Federal",
        "art. 373 do CPC/73",
        # a versão revogada do código tem o mesmo artigo, mas não é o registro
        "art. 186 do Código Civil de 1916",
        "art. 373 do Código de Processo Civil de 1973",
        # artigo que o diploma da cobertura não tem
        "art. 999 do Código Civil",
        "art. 1.307 da Lei nº 13.105/2015",
        # o mesmo número sob outro código — o atalho que `dados.md` documenta
        "art. 14 do Código Civil",
        "art. 818 do Código de Processo Civil",
        # diploma fora da cobertura, nomeado pelo número
        "art. 173 da Lei nº 9.504/1997",
    ],
)
def test_dispositivo_fora_da_cobertura_e_inventada(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


@pytest.mark.parametrize(
    "citacao",
    [
        "Súmula 947 do STF",
        "Súmula 331 do STF",
        "Súmula 83 do TST",
        "Súmula Vinculante 174",
        "Súmula 147 do TSE",
    ],
)
def test_sumula_fora_da_cobertura_e_inventada(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


def test_tema_de_repercussao_geral_e_inventada(base_canonica):
    """A cobertura congelada não tem registro de tema."""
    assert _classificar(base_canonica, "Tema 1.102 da repercussão geral") == [("inventada", None)]


# ── Os demais caminhos de `resolver` ──────────────────────────────────────────


def test_vaga_e_incompleta_sem_consultar_a_base(base_canonica):
    citacao = "julgado do STF proferido em 2019 pela relatoria de Carlos Alberto"
    assert _classificar(base_canonica, citacao) == [("incompleta", None)]


def test_processo_ausente_do_indice_e_inventada(base_canonica):
    assert _classificar(base_canonica, "REsp 9.999.991/SP") == [("inventada", None)]


def test_toda_confianca_emitida_esta_no_intervalo(base_canonica):
    """O avaliador oficial rejeita a submissão inteira com confiança fora de [0, 1].

    A `vaga` vai numa frase própria: dividindo a frase com uma citação numerada,
    a contagem de constituintes a descarta de propósito — ver
    `_vagas_por_constituinte`.
    """
    texto = (
        "Invoca-se o art. 5º da Constituição Federal, a Súmula 947 do STF e o REsp "
        "9.999.991/SP, todos no mesmo sentido. Cita-se ainda o julgado do STF "
        "proferido em 2019 pela relatoria de Carlos Alberto."
    )
    confiancas = [resolver(a, base_canonica)[2] for a in detectar(texto)]
    assert len(confiancas) == 4
    assert all(0.0 <= c <= 1.0 for c in confiancas)


@pytest.mark.parametrize(
    ("citacao", "esperado"),
    [
        # o número da lei também passa pelo reparo antes de ser conferido
        ("art. 1º da Lei Complementar nº b4/1990", [("real", DISPOSITIVOS[("LC64", 1)])]),
        ("art. 4S da Lei Complementar nº b4/1990", [("inventada", None)]),
        ("art b0 da Lei nº l7.463/z0I4", [("inventada", None)]),
    ],
)
def test_numero_da_lei_com_ruido(base_canonica, citacao, esperado):
    assert _classificar(base_canonica, citacao) == esperado
