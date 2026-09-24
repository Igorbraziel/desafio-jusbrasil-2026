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


# ── O mesmo ruído de OCR, nas famílias que não o atravessavam ─────────────────
#
# O checkpoint 06 ensinou a família `processo` a atravessar o digitoide — a letra
# que o OCR põe no lugar de um dígito — e ganhou +0,019 em `ocr_numero`. As
# famílias `dispositivo` e `sumula` ficaram para trás: `_NUMERO_DE_ARTIGO` e o
# grupo `numero` de `_SUMULA` exigiam **dígito puro**.
#
# Medindo os corpora de `data/perturbado/`, essa assimetria é hoje a maior perda
# de recall do pipeline — maior que a da família que foi corrigida:
#
#     classe de ruído        disp/súm/tema   processo
#     ocr_numero (5 sem.)         40            22
#     ocr_palavra (5 sem.)        17            22
#     todas (7) (5 sem.)          57            43
#
# `_corrigir_ocr` já repara todos estes casos (`I86`→`186`, `B96`→`896`). Era a
# detecção que nunca lhe entregava o trecho — a mesma forma de defeito do cp 06.


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        ("Incide na espécie o artigo I86 do Código Civil, como se vê.", "186"),
        ("Aplica-se o art z7G do Código Eleitoral ao caso em análise.", "276"),
        ("Invoca-se o art 3I2 do Código de Processo Penal na hipótese.", "312"),
        ("Violou o acórdão o art. B96, § 1º-A, da CLT, segundo a parte.", "896"),
        ("Cita-se o art. l.307 da Lei nº 13.105/2015 quanto à matéria.", "1307"),
        ("Aplica-se o artigo 5º da Constituição Federal, sem divergência.", "5"),
    ],
)
def test_artigo_atravessa_o_ruido_que_o_reparo_desfaz(corpo, esperado):
    """Se a tabela de reparo conhece a letra, a detecção tem de atravessá-la.

    Vale para o número do artigo tanto quanto para o número de processo: a
    citação sumia inteira, que é erro de recall e não se recupera depois.
    """
    from verificador.normalizacao import _corrigir_ocr

    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["dispositivo"]
    artigo = dict(achados[0].dados)["artigo"]
    assert "".join(c for c in _corrigir_ocr(artigo) if c.isdigit()) == esperado


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        ("Aplica-se a Súmula B3 do STJ, de resto pacífica no tribunal.", "83"),
        ("Incide a 5úmula 2ll do STJ quanto ao ponto ora controvertido.", "211"),
        ("Invoca-se a Súmula 33l do TST, que trata de caso equivalente.", "331"),
    ],
)
def test_sumula_atravessa_o_ruido_que_o_reparo_desfaz(corpo, esperado):
    """Mesma assimetria, na família `sumula`."""
    from verificador.normalizacao import _corrigir_ocr

    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["sumula"]
    numero = dict(achados[0].dados)["numero"]
    assert "".join(c for c in _corrigir_ocr(numero) if c.isdigit()) == esperado


@pytest.mark.parametrize(
    "prosa",
    [
        "A arte do Código de Processo Civil é matéria de doutrina apenas.",
        "O art. do Código Civil não foi indicado pela parte recorrente.",
    ],
)
def test_artigo_sem_digito_real_nao_vira_dispositivo(prosa):
    """O contrapeso do artigo tolerante, na lógica de `_MINIMO_DIGITOS`.

    Sem exigir **um dígito real**, `art Iss` casaria: `I` e `s` são digitoides, e
    o número resultante sairia do nada.
    """
    assert _detectar(prosa) == []


# ── Formas de súmula e dispositivo que a amostra não traz ─────────────────────
#
# Súmulas e dispositivos são 22% do gabarito (14 + 28 de 192). As formas abaixo
# são correntes em peça jurídica e nenhuma era detectada. A frequência foi medida
# nos 996 acórdãos reais da base: `caput` em 424, `inciso(s)` em 497, `art. N, I
# e II` em 109, romano com 6+ caracteres em 49.


@pytest.mark.parametrize(
    "corpo",
    [
        # a marca de número entre a palavra e o dígito — e é a forma que a
        # própria base canônica usa na primeira linha dos 5 registros de súmula
        "Aplica-se a Súmula nº 83 do STJ ao caso ora em julgamento.",
        "Aplica-se a Súmula n. 83 do STJ ao caso ora em julgamento.",
        "Aplica-se a Súmula No 83 do STJ ao caso ora em julgamento.",
        "Aplica-se a Súm. nº 83 do STJ ao caso ora em julgamento.",
    ],
)
def test_sumula_com_marca_de_numero(corpo):
    """`Súmula nº 83` é a grafia da base canônica, e não era detectada."""
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["sumula"]
    assert dict(achados[0].dados)["numero"] == "83"


@pytest.mark.parametrize(
    "corpo",
    [
        # romano com mais de 5 caracteres — o limite antigo era {1,5}
        "Invoca-se o art. 5º, LXXVIII, da Constituição Federal no ponto.",
        "Invoca-se o art. 5º, LXXVII, da Constituição Federal no ponto.",
        # o `caput`, presente em 424 dos 996 acórdãos reais
        "Invoca-se o art. 5º, caput, da Constituição Federal no ponto.",
        # inciso no plural e a conjunção entre dois romanos
        "Invoca-se o art. 373, incisos I e II, do CPC quanto ao ônus.",
        "Invoca-se o art. 373, I e II, do CPC quanto ao ônus da prova.",
        # a sigla LC e o Decreto-Lei, que é como a base nomeia a CLT
        "Invoca-se o art. 1º da LC 64/1990 quanto à inelegibilidade.",
        "Invoca-se o art. 818 do Decreto-Lei nº 5.452/1943 no ponto.",
    ],
)
def test_dispositivo_em_formas_correntes_fora_da_amostra(corpo):
    """Cada uma destas formas perdia a citação inteira."""
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["dispositivo"]


# ── Falsos positivos que o texto jurídico real produz ─────────────────────────


def test_prosa_com_ministro_nao_vira_incompleta():
    """`_ANO_ISOLADO` aceitava digitoide em toda posição, então `logo` era "ano".

    Como a contagem de constituintes não exigia nenhum dígito **real**, prosa com
    "Ministro <Nome>" virava `incompleta`. Medido: 4 spans espúrios em 80
    acórdãos reais da base.
    """
    assert (
        _detectar("O recurso é intempestivo e, logo, o Ministro Carlos Alberto o inadmitiu.") == []
    )


@pytest.mark.parametrize(
    "corpo",
    [
        "Inscrito na OAB sob o nº 123.456/SP, o advogado subscreve a peça.",
        "A causa vale 1.500.000,00 segundo a inicial protocolada nos autos.",
    ],
)
def test_distrator_com_rotulo_afastado_nao_vira_citacao(corpo):
    """`_ROTULO_DISTRATOR` exigia o rótulo colado ao número e escapava."""
    assert _detectar(corpo) == []


def test_rotulo_dentro_de_palavra_nao_apaga_a_citacao():
    """`tel` casava dentro de "tutela nº", e a referência a outro processo sumia.

    Apareceu ao aceitar a marca de número depois do rótulo: a fronteira de
    palavra na frente é o que separa o rótulo `tel` da palavra "tutela". Medido
    nos 996 acórdãos reais da base.
    """
    corpo = "Na suspensão de tutela nº 4037431-74.2019.4.01.0000 decidiu-se o contrário."
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == ["processo"]


# ── Número de processo com poucos dígitos reais depois do ruído ───────────────
#
# `_MINIMO_DIGITOS` conta só dígitos **reais**. Sob `ocr_numero` um número de
# cinco dígitos fica com três — `Rcl 4B.71B/RS` — e a citação sumia, embora o
# reparo devolva `48718`. Era o maior bloco das perdas restantes no arnês.
#
# A regra afrouxada tem dois freios, e cada um barra uma forma de falso
# positivo: o número **reparado** precisa ter quatro dígitos (só letra colada a
# dígito é reparada, então `BO 12` não passa), e com menos de quatro reais o
# prefixo precisa nomear uma classe processual.


@pytest.mark.parametrize(
    ("citacao", "esperado"),
    [
        ("Rcl 4B.71B/RS", "48718"),
        ("AgInt na Rcl 24.b3O/SP", "24630"),
        ("AgREsp Nº 72Gq4 - MG", "72694"),
        ("Reclamação nº 7l.3z4/SP", "71324"),
        ("AgRg no Rec. Esp. n. 3.sz4.zo7 (SC)", "3524207"),
        ("Recl. n° 7G.84B/ BA", "76848"),
    ],
)
def test_processo_com_poucos_digitos_reais_e_detectado(citacao, esperado):
    from verificador.normalizacao import digitos_do_identificador

    achados = _detectar(f"Ampara a pretensão o {citacao}, citado nos autos.")
    assert [a.familia for a in achados] == ["processo"]
    assert digitos_do_identificador(achados[0].trecho) == esperado


@pytest.mark.parametrize(
    "prosa",
    [
        "O boletim BO 12 foi lavrado pela autoridade policial no local.",
        "Foram ouvidas 12 Os testemunhas arroladas pela defesa técnica.",
        "a quantia de 4B.71B não consta de nenhum documento dos autos.",
    ],
)
def test_poucos_digitos_reais_sem_classe_nao_vira_processo(prosa):
    """Os dois freios da regra afrouxada."""
    assert _detectar(prosa) == []


@pytest.mark.parametrize(
    ("corpo", "familia"),
    [
        ("Incide o Temã 3.b40 da repercussão geral, como se vê.", "tema"),
        ("Violou o acórdão o art. 896, § Iº-A, da CLT, segundo a parte.", "dispositivo"),
        ("Violou o acórdão o art. 1.021, §§ 4º e 5º, do CPC no ponto.", "dispositivo"),
        ("Cita-se o art b0 da Lei nº l7.463/z0I4 quanto à matéria.", "dispositivo"),
        ("Cita-se o art. 4S da Lei Complementar nº b4/1990 no ponto.", "dispositivo"),
    ],
)
def test_digitoide_no_tema_no_paragrafo_e_no_numero_da_lei(corpo, familia):
    achados = _detectar(corpo)
    assert [a.familia for a in achados] == [familia]


def test_lei_seguida_de_palavra_nao_vira_numero_de_lei():
    """`O` é digitoide: sem o freio, "Lei Orgânica" casaria "Lei O"."""
    assert _detectar("Aplica-se o art. 5º da Lei Orgânica do Município ao caso.") == []


@pytest.mark.parametrize(
    "prosa",
    [
        "Os temas debatidos no recurso já foram enfrentados pela Corte.",
        "O tema o qual se discute foi afetado ao rito dos repetitivos.",
    ],
)
def test_palavra_tema_sem_numero_nao_vira_citacao(prosa):
    """O número do tema atravessa o digitoide, e por isso precisa de dígito real.

    Apareceu nos 996 acórdãos reais ao afrouxar o número: `temas` casava como
    Tema `s`, 119 spans espúrios.
    """
    assert _detectar(prosa) == []


@pytest.mark.parametrize(
    "prosa",
    [
        "III. RAZÕES DE DECIDIR III.1. O acórdão recorrido não merece reparo.",
        "Assinado eletronicamente por MINISTRO FULANO DE TAL 05/08/2021 14:30.",
    ],
)
def test_numeracao_de_secao_e_carimbo_de_data_nao_viram_processo(prosa):
    """Os falsos positivos que o afrouxamento abriu nos 996 acórdãos reais."""
    assert _detectar(prosa) == []


# ── O prefixo não pode parar no ruído ─────────────────────────────────────────
#
# Um prefixo truncado deixa o span com só o número. O IoU cai abaixo de 0,5, o
# gold fica sem par (FN) e a predição vira espúria (FP) — e, quando o número
# resolve, é um `real` espúrio, que é a forma que chega mais perto de τ.
# Medido no arnês: os cinco `(espúria) → real` restantes tinham esta causa.


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        # a marca de número com espaço, que `marca_numero` produz
        (
            "Ampara a pretensão o Recurso em Habeas Corpus n º 43974 - SC, citado.",
            "Recurso em Habeas Corpus n º 43974 - SC",
        ),
        # a maiúscula corrompida em minúscula pelo OCR (`E`→`c`, `C`→`e`)
        (
            "Ampara a pretensão o AgInt no Recurso cspecial Nº 240073O (SP), citado.",
            "AgInt no Recurso cspecial Nº 240073O (SP)",
        ),
        (
            "Ampara a pretensão o Recurso em Habeas eorpus nº 43974 - SC, citado.",
            "Recurso em Habeas eorpus nº 43974 - SC",
        ),
    ],
)
def test_prefixo_atravessa_o_ruido(corpo, esperado):
    assert [a.trecho for a in _detectar(corpo)] == [esperado]


def test_minuscula_de_prosa_continua_parando_o_prefixo():
    """O contrapeso: a palavra corrompida só continua a cadeia se vier entre elos."""
    achados = _detectar("A parte cita especial REsp 1.234.567/SP no ponto.")
    assert [a.trecho for a in achados] == ["REsp 1.234.567/SP"]


@pytest.mark.parametrize(
    "corpo",
    [
        # quebra de linha no separador de milhar do artigo (`quebra_identificador`)
        "Violou o acórdão o art. 1.\n307 do Código de Processo Civil no ponto.",
        # a marca de número partida por espaço (`marca_numero`)
        "Violou o acórdão o art. 47 da Lei Complementar n º 64/1990 no ponto.",
    ],
)
def test_dispositivo_sob_quebra_e_marca_partida(corpo):
    """As duas perdas que sobravam nas classes estruturais do arnês."""
    assert [a.familia for a in _detectar(corpo)] == ["dispositivo"]


@pytest.mark.parametrize(
    ("citacao", "esperado"),
    [
        # dois dígitos reais sobreviventes — os casos que só o NER de pesos
        # abertos achava a taxa 0,30 (ADR 0004)
        ("Recl. n° 7G.B4B/ BA", "76848"),
        ("Reclamação nº b7.s4b (RO)", "67546"),
        ("Reclamação nº Zz.4s3/PE", "22453"),
        ("RCL nº B4go7-DF", "84907"),
    ],
)
def test_processo_com_dois_digitos_reais_e_detectado(citacao, esperado):
    from verificador.normalizacao import digitos_do_identificador

    achados = _detectar(f"Ampara a pretensão o {citacao}, citado nos autos.")
    assert [a.familia for a in achados] == ["processo"]
    assert digitos_do_identificador(achados[0].trecho) == esperado


def test_nome_em_caixa_alta_com_um_digito_nao_vira_processo():
    """O limite de dois reais existe por este caso, medido nos acórdãos reais.

    O preço é que `RHC nº 7s.soB/RS`, com um dígito real só, continua perdido.
    Na base real não há como separar os dois pela forma.
    """
    assert _detectar("Brasília, 26 de abril de 2016. MSTF 3SSIL - RELATOR do feito.") == []


# ── O órgão julgador antes da citação ─────────────────────────────────────────
#
# Capitalizados, "Tribunal", "Ministro" e o nome que os segue têm forma de sigla,
# e a cadeia de prefixo os engolia: IoU entre 0,33 e 0,39 contra o span da
# citação, que vira FN e FP. Nos acórdãos reais, ~2% dos spans de processo.


@pytest.mark.parametrize(
    "corpo",
    [
        "Conforme entendimento do Superior Tribunal de Justiça Rcl nº 68.244/SP, negou-se.",
        "Como decidiu o Supremo Tribunal Federal Rcl nº 68.244/SP, não cabe o recurso.",
        "Nesse sentido, o Ministro Relator Gilmar Mendes Rcl nº 68.244/SP afastou a tese.",
        "Em Brasília, a Corte Especial Rcl nº 68.244/SP pacificou o tema em debate.",
        "Vide jurisprudência do STF Rcl nº 68.244/SP sobre o tema em debate.",
    ],
)
def test_orgao_julgador_nao_entra_no_prefixo(corpo):
    assert [a.trecho for a in _detectar(corpo)] == ["Rcl nº 68.244/SP"]


def test_orgao_julgador_nao_leva_o_nome_da_classe_junto():
    """O descarte do complemento para no núcleo do nome da classe."""
    achados = _detectar("O Relator Gilmar Mendes Reclamação nº 68.244/SP afastou a tese.")
    assert [a.trecho for a in achados] == ["Reclamação nº 68.244/SP"]


def test_citacoes_coordenadas_nao_se_fundem():
    achados = _detectar("No julgamento do Recurso Extraordinário e da Rcl nº 68.244/SP, decidiu.")
    assert achados[-1].trecho.endswith("Rcl nº 68.244/SP")
    assert "Extraordinário" not in achados[-1].trecho


def test_e_dentro_do_nome_da_classe_continua_elo():
    achados = _detectar(
        "Cita-se o Agravo Interno na Suspensão de Liminar e de Sentença nº 2.883/MA no ponto."
    )
    assert [a.trecho for a in achados] == [
        "Agravo Interno na Suspensão de Liminar e de Sentença nº 2.883/MA"
    ]


def test_sigla_de_tribunal_colada_continua_elo():
    achados = _detectar("Conforme o processo nº TST-RR-79500-16.2009.5.15.0001, julgado.")
    assert achados[0].trecho.startswith("processo nº TST-RR-")


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        ("Conforme decidido no REsp 1.234.567/SP, o pedido procede.", "REsp 1.234.567/SP"),
        ("A tese foi fixada na Reclamação nº 22.357/PE, citada.", "Reclamação nº 22.357/PE"),
        ("A tese foi fixada no AgInt no REsp 1.944.552/RS, citado.", "AgInt no REsp 1.944.552/RS"),
    ],
)
def test_conector_nao_abre_o_span(corpo, esperado):
    """O conector é elo entre siglas, nunca a borda esquerda da citação."""
    assert [a.trecho for a in _detectar(corpo)] == [esperado]


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        ("O art. 5º da Constituição garante a igualdade.", "art. 5º da Constituição"),
        ("O art. 5º, II, da Constituição consagra a legalidade.", "art. 5º, II, da Constituição"),
        ("Viola o art. 5º da constituição estadual no ponto.", "art. 5º da constituição estadual"),
    ],
)
def test_verbo_depois_da_constituicao_nao_entra_no_diploma(corpo, esperado):
    assert [a.trecho for a in _detectar(corpo)] == [esperado]


@pytest.mark.parametrize(
    ("corpo", "esperado"),
    [
        ("O art. 186 do Código Civil trata do ato ilícito.", "art. 186 do Código Civil"),
        ("O art. 276 do Código Eleitoral trata do recurso.", "art. 276 do Código Eleitoral"),
        # a minúscula da lista fechada continua entrando — o CPPM precisa dela
        (
            "Viola o art. 312 do código de processo penal militar no ponto.",
            "art. 312 do código de processo penal militar",
        ),
    ],
)
def test_prosa_depois_do_nome_do_codigo_nao_entra_no_diploma(corpo, esperado):
    assert [a.trecho for a in _detectar(corpo)] == [esperado]


@pytest.mark.parametrize(
    "qualificador",
    [
        "parágrafo único",
        "§ único",
        "inc. LV",
        "incs. LIV e LV",
        "caput e inciso LV",
        "caput, e inciso II",
        "parágrafo 2º",
    ],
)
def test_dispositivo_com_qualificadores_correntes(qualificador):
    corpo = f"Conforme o art. 5º, {qualificador}, da Constituição Federal, todos."
    assert [a.trecho for a in _detectar(corpo)] == [
        f"art. 5º, {qualificador}, da Constituição Federal"
    ]


def test_qualificadores_nao_explodem_em_texto_longo():
    """Cada repetição consome texto literal: o custo continua linear."""
    import time

    inicio = time.perf_counter()
    _detectar("art. 5º, " + "caput e inciso, " * 20000)
    _detectar("art. 5º" + ", parágrafo" * 20000)
    assert time.perf_counter() - inicio < 2
