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


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("Súmula 83/STJ", ("STJ", False, 83)),
        ("Súmula 83-STJ", ("STJ", False, 83)),
        ("Súmula 83 (STJ)", ("STJ", False, 83)),
        ("Súmula 331, I, do TST", ("TST", False, 331)),
        ("Súmula nº 331 do Tribunal Superior do Trabalho", ("TST", False, 331)),
        ("Súmula 211 do Superior Tribunal de Justiça", ("STJ", False, 211)),
        ("Súrnula 331 do Tribunal Supcrior do Trabalho", ("TST", False, 331)),
    ],
)
def test_sumula_com_tribunal_em_outras_formas(base_canonica, citacao, chave):
    """Sem o tribunal a súmula da cobertura não resolve e sai `inventada`."""
    assert _classificar(base_canonica, citacao) == [("real", SUMULAS[chave])]


@pytest.mark.parametrize(
    "citacao",
    ["Súmula 83/STF", "Súmula 331 do Supremo Tribunal Federal", "Súmula 443 (TST)"],
)
def test_sumula_em_outro_tribunal_continua_inventada(base_canonica, citacao):
    """O tribunal é conferido junto com o número: outra forma não abre o τ."""
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


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
        # o verbo da frase não é qualificador, e a sigla com ano é a CF/88
        ("art. 5º da Constituição garante a igualdade", ("CF", 5)),
        ("art. 5º, II, da Constituição consagra a legalidade", ("CF", 5)),
        ("art. 5º da CF de 1988", ("CF", 5)),
        ("artigo 5º, inciso XXXVI, da CF de 1988", ("CF", 5)),
        ("art. 93 da constituição federal", ("CF", 93)),
        # "Constituição Cidadã" é o apelido corrente da CF/88
        ("art. 5º da Constituição Cidadã", ("CF", 5)),
        ("art. 5º da constituição cidadã", ("CF", 5)),
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
        # o qualificador em minúscula continua capturado, e continua recusado
        "art. 5º da constituição estadual",
        "art. 5º da constituição mineira",
        "art. 5º da constituição portuguesa",
        "art. 93 da constituição do estado",
        "art. 5º da CF de 1967",
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


# ── O nome do diploma com ruído de letra do nível 2 ───────────────────────────
#
# A detecção passou a atravessar `Códlgo` e `Mllitar`, mas a resolução casava o
# nome do diploma por marcador literal: `penal militar` não está em
# `penal mllitar`, e a citação `real` virava `inventada`. Medido no arnês, era
# todo o `real` → `inventada` que sobrava em `ocr_palavra`.


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("art. 14 do Código de Dcfesa do Consumidor", ("CDC", 14)),
        ("art 312 do Código de Processo Pcnal", ("CPP", 312)),
        ("art 312 do Código de Processo Perial", ("CPP", 312)),
        ("art. 5º, LV, da Constltuição Federal", ("CF", 5)),
        ("artigo 186 do Código Civll", ("CC", 186)),
        ("artigo 186 do Código eivil", ("CC", 186)),
        ("artigo 7º, XXIX, da Constituição Fcdcral", ("CF", 7)),
        ("art. 290 do Código Penal Mllitar", ("CPM", 290)),
        ("art. 290 do Código Perial Militar", ("CPM", 290)),
        ("art. 818 da Consolldação das Leis do Trabalho", ("CLT", 818)),
    ],
)
def test_diploma_com_ruido_de_letra(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


@pytest.mark.parametrize(
    "citacao",
    [
        # o CPPM com ruído continua fora da cobertura — é o erro grave que a
        # ordem de `DIPLOMAS` existe para impedir, e a tolerância não pode abrir
        "art. 312 do Código de Processo Pcnal Militar",
        "art. 312 do Código de Processo Penal Mllitar",
        "art. 5º da Constltuição Estadual",
    ],
)
def test_diploma_fora_da_cobertura_com_ruido_continua_inventada(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


def test_sigla_curta_nao_casa_dentro_de_outra_palavra(base_canonica):
    """`cdc` dentro de `fcdcral` fazia a CF corrompida resolver para o CDC."""
    assert _classificar(base_canonica, "art. 7º da Constituição Fcdcral") == [
        ("real", DISPOSITIVOS[("CF", 7)])
    ]


# ── Os caminhos de τ achados na revisão de 24/09 ──────────────────────────────
#
# Cada caso aqui saía `real` apontando para um registro da cobertura, embora a
# citação fosse de outro diploma, outro tribunal ou outro artigo. É o erro que a
# métrica multiplica pelo nível inteiro.


@pytest.mark.parametrize(
    "citacao",
    [
        # a sigla sem fronteira à direita: "CPPM" casava "CPP" e sobrava o "M"
        "art. 312 do CPPM",
        # o conector corrompido e o nome longo cortavam "Militar" fora do diploma
        "art. 312 do Código dc Processo Penal Militar",
        "art. 312 do Código Brasileiro de Processo Penal Militar",
        # o qualificador estrangeiro depois do primeiro ficava fora do diploma
        "art. 5º da Constituição da República Portuguesa",
        "art. 5º da Constituição Federal Alemã",
        "art. 5º da Constituição da República de Angola",
        # artigo com sufixo é outro artigo: nenhum da cobertura tem sufixo
        "art. 896-A da CLT",
        "art. 373-A do CPC",
        # códigos por sigla fora da cobertura
        "art. 121 do CP",
        "art. 142 do CTN",
    ],
)
def test_diploma_ou_artigo_fora_da_cobertura_nao_vira_real(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        # as siglas correntes da CF e do CPC vigentes
        ("art. 5º, LV, da CRFB/88", ("CF", 5)),
        ("art. 93, IX, da CRFB", ("CF", 93)),
        ("art. 373 do NCPC", ("CPC", 373)),
        # "LC nº 64/90": o marcador era o literal "lc 64", sem a marca de número
        ("art. 1º, I, g, da LC nº 64/90", ("LC64", 1)),
        # o parágrafo com sufixo não é sufixo do artigo
        ("art. 896, § 1º-A, da CLT", ("CLT", 896)),
    ],
)
def test_siglas_correntes_da_cobertura_sao_real(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


def test_sumula_vinculante_de_outro_tribunal_e_inventada(base_canonica):
    """Súmula vinculante só existe no STF; "do STJ" é outra súmula."""
    assert _classificar(base_canonica, "Súmula Vinculante 10 do STJ") == [("inventada", None)]
    assert _classificar(base_canonica, "Súmula Vinculante 10 do STF") == [
        ("real", SUMULAS[("STF", True, 10)])
    ]


@pytest.mark.parametrize(
    "citacao",
    [
        # tema em outras grafias caía na família `processo`, e o número de um
        # tema citado na ementa de um acórdão resolvia para esse acórdão
        "Tema Repetitivo 1.046 do STJ",
        "tema repetitivo 1.148 do STJ",
        "Tema de Repercussão Geral nº 1.046",
        "Tema RG 1.046",
    ],
)
def test_tema_em_outras_grafias_e_inventada(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


@pytest.mark.parametrize(
    "citacao",
    [
        # lei citada pelo número, com ano de dois dígitos: não é processo
        "artigo 189 da Lei Federal nº 9.504/97",
        "art 189 da Lci nº 9.504/97",
    ],
)
def test_lei_com_ano_de_dois_digitos_nao_vira_processo(base_canonica, citacao):
    familias = {a.familia for a in detectar(f"Invoca-se o {citacao}, no ponto.")}
    assert "processo" not in familias
    assert all(classe != "real" for classe, _ in _classificar(base_canonica, citacao))


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        # a sigla do tribunal com o `S` lido como `5`
        ("Súmula 83 do 5TJ", ("STJ", False, 83)),
        ("Súmula 331 do T5T", ("TST", False, 331)),
        ("Súmula Vinculante 10 do 5TF", ("STF", True, 10)),
        # o conector curto corrompido
        ("Súmula 83 d0 STJ", ("STJ", False, 83)),
        ("Súmula 211 dc STJ", ("STJ", False, 211)),
    ],
)
def test_sumula_com_sigla_ou_conector_corrompido(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", SUMULAS[chave])]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("art. 93, IX, dã Constituição Federal", ("CF", 93)),
        ("art. 312 d0 Código de Processo Penal", ("CPP", 312)),
        ("art. 477 dã CLT", ("CLT", 477)),
        ("art. 1º dã Lei Complcmentar nº 64/1990", ("LC64", 1)),
    ],
)
def test_dispositivo_com_conector_corrompido(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


# ── Formas correntes que a amostra sintética não produziu ─────────────────────


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        # o inciso da súmula como "item" e o honorífico antes do tribunal
        ("Súmula 331, item IV, do TST", ("TST", False, 331)),
        ("Súmula 83 do C. STJ", ("STJ", False, 83)),
        ("Súmula 443 do E. STJ", ("STJ", False, 443)),
        ("Súmula 331 do col. TST", ("TST", False, 331)),
        # a sigla da súmula vinculante
        ("SV 10", ("STF", True, 10)),
        ("SV nº 10 do STF", ("STF", True, 10)),
        # "Enunciado" é como o TST chama as próprias súmulas
        ("Enunciado 331 do TST", ("TST", False, 331)),
    ],
)
def test_sumula_em_formas_correntes(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", SUMULAS[chave])]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("art. 373 do novo Código de Processo Civil", ("CPC", 373)),
        ("art. 373 do atual CPC", ("CPC", 373)),
        ("art. 93, IX, da Lei Maior", ("CF", 93)),
        ("art. 5º, LV, da Carta Política", ("CF", 5)),
        ("art. 5º, LV, da Carta da República", ("CF", 5)),
        # o diploma por sigla, sem o conector
        ("art. 5º, LV, CF", ("CF", 5)),
        ("art. 5º, LV, CF/88", ("CF", 5)),
    ],
)
def test_dispositivo_em_formas_correntes(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


def test_enunciado_de_outro_tribunal_nao_vira_sumula_do_tst(base_canonica):
    assert _classificar(base_canonica, "Enunciado 331 do STF") == [("inventada", None)]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        # a detecção atravessa o dígito no lugar da letra; a resolução também
        # precisa, senão a citação `real` sai `inventada`
        ("art. 93, IX, da Con5tituição da Repúb1ica", ("CF", 93)),
        ("art. 14 do Códig0 de Defesa do Con5umidor", ("CDC", 14)),
        ("art. 312 do Código de Processo Pena1", ("CPP", 312)),
        ("art. 290 do Código Penal Mi1itar", ("CPM", 290)),
        ("art. 186 do Código Civi1", ("CC", 186)),
        ("art. 1º, I, 'g', da Lei Comp1ementar nº 64/1990", ("LC64", 1)),
    ],
)
def test_diploma_com_digito_no_lugar_da_letra(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


@pytest.mark.parametrize(
    "citacao",
    [
        # o CPPM com dígito continua fora da cobertura
        "art. 312 do Código de Processo Penal Mi1itar",
        "art. 5º da Con5tituição Estadua1",
    ],
)
def test_diploma_fora_com_digito_continua_inventada(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


# ── Achados da revisão final ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        # a letra maiúscula que o OCR põe no número da lei: `G`→6, `B`→8
        ("art. 1º da Lei Complementar nº G4/1990", ("LC64", 1)),
        ("art. 14 da Lei nº B.078/1990", ("CDC", 14)),
        ("art. 312 do Decreto-Lei nº 3.G89/1941", ("CPP", 312)),
        ("art. 186 da Lei nº 10.40G/2002", ("CC", 186)),
        ("art. 276 da Lei nº 4.737/19G5", ("ELEITORAL", 276)),
    ],
)
def test_numero_da_lei_com_maiuscula_de_ocr(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


@pytest.mark.parametrize(
    "citacao",
    [
        # `B`→8: a lei 84 não é a LC 64, e a lei 10.408 não é o Código Civil
        "art. 1º da LC nº B4/1990",
        "art. 186 da Lei nº 1O.4OB/2002",
        # lei estadual, municipal ou distrital com o número de uma lei federal
        "art. 186 da Lei Estadual nº 10.406/2002",
        "art. 14 da Lei Municipal nº 8.078/1990",
        "art. 186 da Lei Estadual nº 10.406",
        # apelidos da Constituição com ano ou qualificador de outra carta
        "art. 5º da Lei Maior de 1969",
        "art. 5º da Carta Política de 1967",
        "art. 5º da Lei Maior do Estado",
        "art. 5º da Lei Maior mineira",
        "art. 5º da Carta da República Portuguesa",
        "art. 5º da Carta Magna de 1967",
    ],
)
def test_achados_da_revisao_continuam_inventada(base_canonica, citacao):
    assert _classificar(base_canonica, citacao) == [("inventada", None)]


@pytest.mark.parametrize(
    ("citacao", "chave"),
    [
        ("art. 5º da Lei Maior", ("CF", 5)),
        ("art. 5º da Carta Magna", ("CF", 5)),
        ("art. 5º da Carta Política de 1988", ("CF", 5)),
    ],
)
def test_apelidos_da_cf_88_continuam_real(base_canonica, citacao, chave):
    assert _classificar(base_canonica, citacao) == [("real", DISPOSITIVOS[chave])]


@pytest.mark.parametrize(
    ("diploma", "esperado"),
    [
        # o conector também sofre o ruído de letra, e o marcador o tem por extenso
        ("Código de Defesa d0 Consumidor", "CDC"),
        ("Código dc Defesa d0 Consumidor", "CDC"),
        ("Consolidação da5 Leis do Trabalho", "CLT"),
        # "Código do Consumidor" é como a prosa chama o CDC
        ("Código do Consumidor", "CDC"),
        # e nada disso abre a direção do τ
        ("Código dc Processo Penal Militar", None),
        ("Código Estadual do Consumidor", None),
    ],
)
def test_conector_corrompido_no_nome_do_diploma(diploma, esperado):
    from verificador.resolucao import _codigo_do_diploma

    assert _codigo_do_diploma(diploma) == esperado
