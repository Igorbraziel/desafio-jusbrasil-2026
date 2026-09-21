"""Detecção dos spans de citação no texto do parecer.

Quem não entrega o span de uma citação não consegue classificá-la, e isso conta
como erro de recall. O alinhamento com o gabarito é por sobreposição com
IoU ≥ 0,5, então a borda exata não precisa ser perfeita — mas a citação inteira
precisa aparecer.

A organização é por família, porque a família determina contra o quê a citação
é resolvida:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.599.910/PR``)
``sumula``       ``Súmula <n> do <tribunal>``, ``Súmula Vinculante <n>``
``tema``         ``Tema 2.680 da repercussão geral``
``dispositivo``  ``art. <n>, <inciso>, do <código>``
``vaga``         sem identificador suficiente para consultar a base

**A âncora de ``processo`` é o número, não a sigla.** Medindo o gabarito, as
classes processuais aparecem em mais de 90 grafias distintas — de ``RR-`` a
``Embargos de Declaração no Agravo Interno no Agravo em Recurso Especial nº``.
Enumerá-las casa a amostra de desenvolvimento e falha no conjunto cego, onde o
material avisa que "as siglas processuais observadas não esgotam o domínio".
Ancorar no número e expandir para a esquerda degrada bem: numa classe não vista
o span fica curto, mas o número — que é o que resolve — continua capturado, e o
span costuma sobreviver ao IoU ≥ 0,5.

**A família ``vaga`` tem uma forma só.** Depois da revisão de 15/09/2026 as 32
citações ``incompleta`` do gabarito são todas do padrão tribunal + ano +
relator — ``julgado do <tribunal> proferido em <ano> pela relatoria de
<nome>``. As 32 nomeiam um relator, o único dígito é o ano e nenhuma traz
número de processo. As frases genéricas ("normas de regência da matéria") e as sem número
("reiterados precedentes do STJ") saíram do gabarito nas duas revisões. O sinal
a procurar é **menção a relator sem número de processo**, não um repertório de
frase vaga. Ver ``docs/investigacao.md``.

**Distratores.** Os cabeçalhos trazem números que parecem citação e não são:
número dos autos do próprio documento, protocolo, inscrição na OAB, ``fls.
234/567``, valor da causa. Nenhum está no gabarito, e extraí-los conta como
falso positivo. Daí a detecção rodar só a partir de
:func:`verificador.texto.fim_do_cabecalho`.

**A família ``vaga`` mudou de alvo.** Até 25/08 ela cobria um repertório de
frases difusas ("jurisprudência pacífica desta Corte"). As revisões de 01/09 e
15/09 removeram todas do gabarito: hoje as 32 ``incompleta`` são **um padrão
só**, tribunal + ano + relator. Detectar as frases difusas virou falso positivo.

Os testes em ``tests/test_deteccao.py`` são a especificação desta etapa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalizacao import OCR_PARA_DIGITO, UFS, _corrigir_ocr, chave_textual
from .texto import fim_do_cabecalho

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

FAMILIAS = ("processo", "sumula", "tema", "dispositivo", "vaga")

# Abaixo disso não há número de processo — só ano, inciso e página.
_MINIMO_DIGITOS = 4

# "nº" em todas as grafias que a amostra traz, inclusive as de OCR (No, N°, n.).
_NUMERO = r"(?:n\s*[.ºo°]{0,2}|N\s*[.ºO°]{0,2})"

# Pontuação que pode aparecer dentro de um número de processo, incluindo a
# quebra de linha e o espaço não-quebrável (`533-80. 2012` vem com \xa0).
#
# **No máximo uma quebra de linha.** Com `\s` solto o núcleo atravessava o fim do
# parágrafo e engolia o título da seção seguinte: em
# `Ag. Int. No 7001184-1520197000000.\n\nI — DA COMPETÊNCIA` o span ia até o `I`
# do título, e o IoU contra o gabarito caía a 0,73. É a mesma política que
# `_expandir_prefixo` já aplica do outro lado — uma quebra é continuação da
# citação, duas são fim de parágrafo.
_DENTRO = r"(?:[ \t\xa0.\-–—/]|\n(?![ \t]*\n))"

# A classe de "digitoide": dígito ou letra que o OCR põe no lugar de um dígito.
#
# **Derivada de `OCR_PARA_DIGITO`, não escrita à mão.** A versão literal
# (`[\dOolISsgGbBZz]`) omitia `i` e `q`, que a tabela de reparo conhece, e a
# divergência custava a citação inteira: `REsp 1737i8/SP` não casava o núcleo e
# o span sumia, mesmo com `digitos_do_identificador` sabendo devolver `173718`.
# A normalização consertava, mas a detecção nunca lhe entregava o trecho.
#
# `_ANO_TOLERANTE` já derivava a classe da mesma tabela; era a assimetria entre
# as duas construções que deixava a divergência passar. Derivar aqui também
# elimina a classe inteira de defeito, em vez de acrescentar `i` e `q` à mão.
_DIGITOIDE = rf"[\d{re.escape(''.join(sorted(set(OCR_PARA_DIGITO))))}]"

# O núcleo numérico: começa em dígito e admite letra de OCR no lugar de um
# dígito, para não cortar a citação ao meio (`21737l8`).
#
# O lookahead impede que ele termine dentro de uma palavra. Sem ele, em "de 2024
# sem outras", o `s` de "sem" — que é digitoide — entrava no número, a forma
# canônica virava `2024s` e o filtro de ano solto deixava passar: o ano virava
# citação `processo`.
_NUCLEO = rf"\d(?:{_DENTRO}*{_DIGITOIDE}){{3,}}(?![A-Za-zÀ-ÿ])"

# Sufixo de UF: /RJ, - PR, (SC), – MA.
#
# O conjunto é fechado, e não `[A-Z]{2}`, porque qualquer bigrama maiúsculo
# entrava no span: em "…REsp 1.234.567 - DE acordo com…", o `- DE` era anexado.
# `normalizacao.UFS` já é a lista validada; usá-la aqui alinha as duas camadas,
# que antes discordavam.
_UF = re.compile(rf"\s*[/(\-–—]\s*(?:{'|'.join(sorted(UFS))})\s*\)?")

_NUMERO_PROCESSO = re.compile(_NUCLEO)

# Palavras de prosa que abrem a frase antes de uma citação. Capitalizadas, elas
# casavam o ramo de sigla e o span começava dez caracteres cedo demais — medido
# em cinco casos do gabarito, com IoU entre 0,565 e 0,714 ("Também na Rcl
# 33.132/AC" onde o gabarito anota só "Rcl 33.132/AC").
#
# A lista é de exclusão e não de inclusão de propósito: enumerar as siglas
# processuais é o que a ADR 0002 refuta. Aqui enumeramos o advérbio de prosa, que
# é vocabulário fechado do português, não do domínio jurídico.
_PALAVRA_DE_PROSA = frozenset(
    """
    tambem também ademais igualmente outrossim ainda assim ja já entao então
    porem porém contudo todavia entretanto alias aliás inclusive ali aqui
    confira confiram veja vejam vejase veja-se vide cita cita-se citese citamos
    conforme segundo consoante nesse neste nessa nesta naquele naquela
    destarte portanto logo pois tal tais este esta esse essa aquele aquela
    """.split()
)

# Um elo da cadeia de prefixo, testado com fullmatch token a token. Três formas:
# sigla iniciada em maiúscula (REsp, AgR-REspe, H.C., TST-ED-E-ED-RR-), marca de
# número (nº, n°, No, n.) e um punhado de palavras minúsculas.
#
# A restrição às minúsculas é o que impede o prefixo de engolir a prosa: em
# "Ampara a pretensão o RSE nº 700…", o "o" não é conector conhecido e a cadeia
# para ali. Sem isso o span começaria em "Ampara".
#
# O ponto **dentro** da sigla é obrigatório no primeiro ramo: sem ele `H.C.`,
# `AG.REG`, `A.REsp` e `R.Esp.` falhavam o fullmatch e o prefixo era truncado —
# era a causa dos dois piores IoU do gabarito (0,519 em "AgRg no H.C. Nº 891369"
# e 0,543 em "Terceiro AG.REG na Rcl").
_ELO = re.compile(
    r"(?:"
    r"[A-ZÀ-Ú][\wÀ-ú.]*(?:[-‐][A-Za-zÀ-Ú0-9][\wÀ-ú.]*)*[-‐]?"
    r"|[nN]\s*[.ºo°O]{1,2}"
    r"|n[oa]s?|d[oae]s?|em|e|processo|autos"
    r"|[-‐]"
    r")",
    re.UNICODE,
)


def _e_elo(token: str) -> bool:
    """O token continua a cadeia de prefixo da citação?

    Separa duas perguntas que o `_ELO` sozinho confundia: *tem forma de elo* e
    *é palavra de prosa*. Qualquer palavra capitalizada tem forma de sigla, então
    a forma precisa ser filtrada pelo léxico — ver `_PALAVRA_DE_PROSA`.
    """
    if not token or _ELO.fullmatch(token) is None:
        return False
    return chave_textual(token.strip(".,;:")) not in _PALAVRA_DE_PROSA


# O maior prefixo do gabarito tem 11 palavras ("Embargos de Declaração no
# Agravo Interno no Agravo em Recurso Especial nº").
_MAXIMO_ELOS = 12

_SUMULA = re.compile(
    r"\b[S5][úuû]m(?:ula|\.)?\s*(?P<vinculante>Vinculante)?\s*(?P<numero>\d+)"
    rf"(?:\s*,?\s*d[oae]s?\s*(?P<tribunal>{'|'.join(TRIBUNAIS)}))?",
    re.IGNORECASE,
)

_TEMA = re.compile(
    r"\bTem[aã]\s*(?P<numero>[\d][\d.]*)(?:\s*d[ae]\s*repercuss[ãa]o\s*geral)?",
    re.IGNORECASE,
)

# Diploma legal: um código nomeado, a Constituição, ou "Lei nº X/ANO". Cada
# alternativa é fechada: nada de `[\w\s]{0,40}` solto, que além de impreciso
# custa caro quando o casamento falha adiante.
_NOME_DE_CODIGO = r"C[óo]digo(?:\s+(?:d[aeo]\s+)?[A-ZÀ-Úa-zà-ú][\wÀ-ú]*){0,3}"
_NUMERO_DE_LEI = r"(?:\s*n[.ºo°]{0,2})?\s*[\d][\d.]*(?:\s*/\s*\d{2,4})?"

_DIPLOMA = (
    r"(?:"
    rf"Lei\s+Complementar{_NUMERO_DE_LEI}"
    rf"|Lei{_NUMERO_DE_LEI}"
    r"|Consolida[çc][ãa]o\s+das\s+Leis\s+d[oe]\s+Trabalho"
    rf"|{_NOME_DE_CODIGO}"
    # O qualificador da Constituição precisa entrar no grupo `diploma`, e não
    # ficar de fora. Duas razões, medidas: (1) o gabarito anota o span inteiro
    # ("Constituição da República", "Constituição Fedcral"), e parar em
    # "Constituição" derrubava o IoU a 0,68; (2) é o qualificador que distingue
    # a Federal — a única na cobertura — da Estadual, e sem ele
    # `art. 5º da Constituição Estadual` resolvia para o art. 5º da CF, que é o
    # erro grave da métrica. Aceita "Federal", "Fedcral" (OCR), "da República"
    # e "do Estado".
    r"|Constitui[çc][ãa]o(?:\s+d[aeo]\s+)?(?:\s*[A-ZÀ-Ú][\wÀ-ú]+)?"
    r"|Carta\s+Magna"
    r"|CPC|CPP|CPM|CLT|CDC|CF(?:\s*/\s*88)?|CC"
    r")"
)

# Incisos, parágrafos e alíneas entre o número do artigo e o diploma. Cada
# repetição **precisa** consumir uma vírgula: sem isso o grupo casa o vazio e o
# motor testa todas as partições da prosa seguinte — era 41 s por documento.
_QUALIFICADORES = (
    r"(?:\s*,\s*(?:§+\s*\d+[ºo°]?(?:\s*-\s*[A-Z])?"
    r"|inciso\s+[IVXLC]+|al[íi]nea\s+[a-z]\)?|[IVXLC]{1,5}|['\"]?[a-z]['\"]?\)?))"
    r"{0,5}"
)

# O número do artigo pode ter separador de milhar: `art. 1.134`, `art. 1.105`.
# Ler só `\d+` para no primeiro ponto e o casamento inteiro falha.
_NUMERO_DE_ARTIGO = r"\d+(?:\.\d{3})*(?:[-ºo°][\w]{0,3})?"

_DISPOSITIVO = re.compile(
    rf"\bart(?:igo|\.|\b)\s*\n?\s*(?P<artigo>{_NUMERO_DE_ARTIGO})"
    rf"{_QUALIFICADORES}"
    rf"\s*,?\s*\n?\s*d[oae]s?\s+(?P<diploma>{_DIPLOMA})",
    re.IGNORECASE,
)

# A família `vaga`: tribunal + ano + relator, hoje a totalidade das `incompleta`.
# O relator é a âncora — é o que separa este padrão de uma menção solta a ano.
# `d[eoc]` e não `d[eo]`: o nível 2 corrompe letras isoladas, e a amostra traz
# o conector "de" aparece corrompido como "dc" (e→c) na amostra.
_RELATOR = r"(?:[Rr]el(?:at[oa]r[ai]?a?)?\.?\s*(?:Min\.?|Ministr[ao])?\.?|relatoria\s+d[eoc])"

#
# A cabeça é a classe ou o genérico ("julgado", "acórdão", "precedente"), com
# até três palavras a mais para as classes por extenso ("Recurso em Habeas
# Corpus"). Ela precisa ser seguida de perto pelo tribunal ou pelo ano — é o que
# impede a expressão de começar em "Cita-se" na frase "Cita-se o julgado do STF".
_CABECA_VAGA = (
    r"(?:julgad[oa]|ac[óo]rd[ãa]o|precedente|decis[ãa]o"
    r"|[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}(?:\s+(?:em\s+|de\s+|do\s+|da\s+)?[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}){0,3}"
    r")"
)

_NOME_PROPRIO = r"[A-ZÀ-Ú][\wÀ-ú.']*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ú][\wÀ-ú.']*){0,4}"

# O ano, tolerante ao ruído do nível 2. Esta é a única quantia numérica da
# família `vaga`, então exigir quatro dígitos limpos apaga a citação inteira
# quando o OCR troca um deles ou a quebra de linha cai no meio. Medido: era a
# causa de 25 das 32 `incompleta` sumirem sob ruído no número.
_ENTRE_DIGITOS = r"[ \t]*\n?[ \t]*"
_DIGITO_OU_OCR = rf"[\d{''.join(sorted(set(OCR_PARA_DIGITO)))}]"
_ANO_TOLERANTE = (
    rf"[12lIZz]{_ENTRE_DIGITOS}[90OoGgqb]{_ENTRE_DIGITOS}"
    rf"{_DIGITO_OU_OCR}{_ENTRE_DIGITOS}{_DIGITO_OU_OCR}"
)

_VAGA = re.compile(
    rf"{_CABECA_VAGA}"
    rf"(?:\s*,?\s*d[oa]\s+(?:{'|'.join(TRIBUNAIS)}))?"
    r"\s*,?\s*(?:proferid[oa]|julgad[oa]|profcrid[oa])?\s*(?:de|em)\s*\n?\s*"
    rf"{_ANO_TOLERANTE}"
    r"[^.]{0,30}?"
    rf"{_RELATOR}\s*{_NOME_PROPRIO}",
)

# ---------------------------------------------------------------------------
# `vaga` por contagem de constituintes
#
# `_VAGA` acima exige cabeça -> tribunal -> ano -> relator **nessa ordem**, que é
# a forma única das 32 `incompleta` do gabarito. Medindo oito reordenações
# plausíveis, sete não eram detectadas — e o próprio `docs/investigacao.md`
# ressalva que "nada garante que o cego use as mesmas frases". A classe de
# perturbação `ordem_incompleta` do arnês mede exatamente isso.
#
# O caminho abaixo é o que `docs/referencias.md` lista como usável agora sem
# custo de envelope (Harašta et al., 2020): reconhecer **constituintes** em vez
# da referência inteira. O critério deixa de ser o casamento de uma frase e vira
# uma contagem — relator e ano presentes, nenhum número de processo —, o que
# vale em qualquer ordem.
#
# Roda **depois** de `_VAGA` e só onde ela não casou: a ordem canônica continua
# produzindo o span que o gabarito anota, e esta é a rede para as demais.
# ---------------------------------------------------------------------------

# A sentença é a janela. `incompleta` é uma referência dentro de uma frase, e o
# ponto final é a fronteira natural — usá-la evita juntar duas citações vizinhas.
#
# O ponto de abreviação **não** encerra a sentença: `[^.!?]+` partia
# "Rel. Min. Carlos Alberto" em três pedaços e nenhum tinha relator e ano juntos.
# Fim de sentença é ponto seguido de espaço e maiúscula, ou de quebra de linha —
# não o ponto colado a uma abreviação curta ("Rel.", "Min.", "n.").
_FIM_DE_SENTENCA = re.compile(r"(?<!\b[A-Z])(?<!\b[A-Za-z]{2})(?<!\b[A-Za-z]{3})[.!?](?=\s|$)")

# O relator, em formas que `_RELATOR` não cobre porque `_VAGA` não precisava
# delas: "relatado por X", "da lavra do Ministro X", e o "Ministro X" sem o
# "Rel." na frente. É a âncora da família — sem relator nomeado não há citação
# `incompleta` — então vale reconhecê-la em qualquer das grafias correntes.
_RELATOR_NOMEADO = re.compile(
    r"(?:"
    rf"{_RELATOR}"
    r"|relatad[oa]\s+(?:por|pel[oa])"
    r"|lavra\s+d[eoa]s?"
    r"|Min\.?|Ministr[ao]s?|Des(?:embargador)?[ao]?\.?"
    r")"
    rf"\s*(?:d[eoa]s?\s+)?(?:Min\.?|Ministr[ao])?\.?\s*{_NOME_PROPRIO}"
)

# "no ano de 2019", "em 2019", "de 2019", ou o ano solto na enumeração
# "STF, 2019, Rel. Min. X".
#
# O `.` do lookahead precisa ser só o que **estrutura um número** (`2019.7.00`),
# nunca o ponto final da frase: `(?![\d./-])` rejeitava "de 2019." e a citação
# desaparecia quando o ano fechava a sentença.
_ANO_ISOLADO = re.compile(rf"(?<![\d./-]){_ANO_TOLERANTE}(?![-/]|\.?\d)")

_MENCAO_TRIBUNAL = re.compile(rf"\b(?:{'|'.join(TRIBUNAIS)})\b")

# A cabeça que abre a referência, quando presente. Só serve para estender o span
# à esquerda até o substantivo que nomeia a decisão — não é exigida.
_CABECA_ISOLADA = re.compile(
    r"\b(?:julgad[oa]|ac[óo]rd[ãa]o|ac[óo]rdao|precedente|decis[ãa]o|aresto"
    r"|voto|jurisprud[êe]ncia|entendimento|prec)[\wÀ-ú]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Achado:
    """Um span candidato a citação, antes de ser resolvido.

    ``dados`` leva os grupos que a detecção já isolou — número do artigo,
    diploma legal, número da súmula. Reaproveitá-los evita que a resolução tenha
    de reparsear o trecho e erre onde a detecção acertou (``5úmula 211`` tem dois
    números; só um deles é o da súmula).
    """

    inicio: int
    fim: int
    trecho: str
    familia: str  # um de FAMILIAS
    tipo: str  # jurisprudencia · lei
    dados: tuple[tuple[str, str], ...] = ()


def _digitos(texto: str) -> int:
    return sum(c.isdigit() for c in texto)


# Um ano solto não é número de processo. Sem este corte, "de 2025" e "em 2023"
# viram citação: eram 40% dos falsos positivos medidos.
_ANO_SOLTO = re.compile(r"^(?:19|20)\d{2}$")

# `fls. <n>/<n>` — referência de página, distrator documentado.
_PAGINAS = re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$")

# `<n>/<ano>` — protocolo ou lei. Número de processo não termina
# em ano: no padrão CNJ o ano fica no meio, e no número único do STJ, na frente.
_TERMINA_EM_ANO = re.compile(r"^\d{1,5}(?:\.\d{3})*\s*/\s*(?:19|20)\d{2}$")

# Data em `dd/mm/aaaa`. `_TERMINA_EM_ANO` exige que o número **inteiro** seja
# `<n>/<ano>`, então a data tem uma barra a mais e escapava dele: medido,
# "O período de 01/01/2020 a 31/12/2021" produzia dois spans `processo`.
#
# A amostra de desenvolvimento não tem nenhuma data nesse formato — contei zero
# nos 26 documentos —, mas 200 de 200 acórdãos reais da base têm, num total de
# 5.635 ocorrências. A ausência é artefato do gerador sintético, não propriedade
# do domínio, e "publicado em <data>" é frase corrente em peça jurídica.
_DATA = re.compile(r"^\d{1,2}/\d{1,2}/(?:\d{2}|(?:19|20)\d{2})$")

# Rótulos que marcam o número seguinte como distrator, não como citação. Os seis
# primeiros são os distratores que o material do desafio nomeia; os demais são
# identificadores civis que aparecem em qualquer peça e que o gerador sintético
# da amostra não produziu.
_ROTULO_DISTRATOR = re.compile(
    r"(?:fls?|folhas?|protocolo|CPF|CNPJ|valor\s+da\s+causa|R\$"
    r"|telefone|tel|fone|celular|RG|CEP|PIS|PASEP|CNH|NIT"
    r"|matr[íi]cula|guia|precat[óo]rio|ag[êe]ncia|conta"
    # O DDD entre parênteses separa o rótulo do número e quebrava a adjacência:
    # "Telefone (11) 98765-4321" escapava do filtro.
    r"|OAB\s*/?\s*[A-Z]{0,2})\s*[.:]?\s*(?:\(\s*\d{2}\s*\)\s*)?$",
    re.IGNORECASE,
)


def _forma_canonica(numero: str) -> str:
    """O número sem ruído de superfície, mas com a pontuação que o estrutura.

    Existe porque os filtros acima descrevem **formas**, e forma não sobrevive ao
    nível 2 sem normalização. Medido: um ano partido por quebra de linha escapava
    de ``_ANO_SOLTO`` e virava citação; uma referência de página com ``\\n`` no
    meio escapava de ``_PAGINAS``. Os dois viram falso positivo, e o segundo é um
    distrator que o material do desafio nomeia.

    Mantém ``/`` e ``.`` porque ``_PAGINAS`` e ``_TERMINA_EM_ANO`` dependem
    deles; tira espaço e quebra de linha, e desfaz a troca de dígito por letra.
    """
    return re.sub(r"[\s]+", "", _corrigir_ocr(numero))


# A janela de rótulo precisa caber o rótulo mais longo com folga para o ruído do
# nível 2: "valor da causa" já tem 14 caracteres, e uma corrupção que insira
# caractere (`m` -> `rn`) estoura os 24 originais.
_JANELA_ROTULO = 40


def _e_numero_de_processo(numero: str, antes: str) -> bool:
    """Filtra o que tem forma de número mas não identifica processo."""
    compacto = _forma_canonica(numero)
    if _ANO_SOLTO.match(compacto) or _PAGINAS.match(compacto):
        return False
    if _TERMINA_EM_ANO.match(compacto) or _DATA.match(compacto):
        return False
    return not _ROTULO_DISTRATOR.search(antes[-_JANELA_ROTULO:])


def _aparar(texto: str, inicio: int, fim: int) -> tuple[int, int]:
    """Encolhe o span até que as bordas não sejam espaço ou pontuação solta."""
    while inicio < fim and (texto[inicio].isspace() or texto[inicio] in ",;:"):
        inicio += 1
    while fim > inicio and (texto[fim - 1].isspace() or texto[fim - 1] in ",;:."):
        fim -= 1
    return inicio, fim


def _expandir_prefixo(corpo: str, inicio: int) -> int:
    """Anda para a esquerda a partir do número, enquanto houver elos de prefixo.

    Feito em Python e não em regex de propósito: uma cadeia ``(?:elo\\s*){0,12}``
    antes do número faz o motor testar todas as combinações quando o número
    falha, e a suíte passou de milissegundos para 41 segundos. Aqui o custo é
    linear e o limite é explícito.
    """
    posicao = inicio
    for _ in range(_MAXIMO_ELOS):
        recuo = posicao
        quebras = 0
        # Uma quebra de linha simples é atravessada — o nível 2 parte citações
        # no meio (`Recurso em Mandado de Segurança\nnº 67.101/RJ`). Duas
        # seguidas são fim de parágrafo, e aí a cadeia termina.
        while recuo > 0 and corpo[recuo - 1] in " \t\xa0\n":
            if corpo[recuo - 1] == "\n":
                quebras += 1
                if quebras > 1:
                    break
            recuo -= 1
        if recuo == 0 or quebras > 1:
            break
        fim_token = recuo
        while recuo > 0 and not corpo[recuo - 1].isspace():
            recuo -= 1
        token = corpo[recuo:fim_token]
        if not _e_elo(token):
            break
        posicao = recuo
    return posicao


def _sentencas(corpo: str) -> list[tuple[int, int]]:
    """Fronteiras de sentença, tolerantes ao ponto de abreviação."""
    limites = [0]
    for fim in _FIM_DE_SENTENCA.finditer(corpo):
        limites.append(fim.end())
    limites.append(len(corpo))
    return [(a, b) for a, b in zip(limites, limites[1:], strict=False) if b > a]


def _tem_numero_de_processo(trecho: str) -> bool:
    """Há na janela um número que a base consegue resolver?

    É o que tira uma citação da família `vaga`: com número, ela é `real` ou
    `inventada`, e quem decide é a cardinalidade da consulta. Sem número, não há
    o que consultar — é `incompleta` por construção.
    """
    return any(
        _digitos(m.group()) >= _MINIMO_DIGITOS
        and _e_numero_de_processo(m.group(), trecho[: m.start()])
        for m in _NUMERO_PROCESSO.finditer(trecho)
    )


def _vagas_por_constituinte(corpo: str) -> list[tuple[int, int]]:
    """Spans de `vaga` achados por contagem de constituintes, em qualquer ordem.

    O critério, por sentença: há **relator nomeado** e **ano**, e **não** há
    número de processo. Os dois primeiros são o que identifica uma decisão
    concreta; o terceiro é o que a torna inverificável — com número, a citação é
    `real` ou `inventada`, e quem decide é a base.

    O span vai do primeiro ao último constituinte, estendido à esquerda até a
    cabeça ("julgado", "acórdão", "precedente") quando ela abre a referência.
    """
    spans: list[tuple[int, int]] = []
    for inicio_sent, fim_sent in _sentencas(corpo):
        trecho = corpo[inicio_sent:fim_sent]
        if len(trecho.strip()) < 12:
            continue

        relator = _RELATOR_NOMEADO.search(trecho)
        if relator is None:
            continue
        anos = list(_ANO_ISOLADO.finditer(trecho))
        if not anos:
            continue

        # Número de processo na sentença tira a citação desta família: ela passa
        # a ser resolvível contra a base, e quem decide a classe é a cardinalidade.
        if _tem_numero_de_processo(trecho):
            continue

        inicio = min(relator.start(), anos[0].start())
        fim = max(relator.end(), anos[-1].end())

        # O tribunal, quando nomeado, faz parte da referência.
        tribunal = _MENCAO_TRIBUNAL.search(trecho)
        if tribunal is not None:
            inicio = min(inicio, tribunal.start())
            fim = max(fim, tribunal.end())

        # Estende à esquerda até a cabeça, se ela abrir a referência de perto.
        for cabeca in _CABECA_ISOLADA.finditer(trecho):
            if cabeca.start() < inicio and inicio - cabeca.end() <= 40:
                inicio = cabeca.start()
                break

        spans.append((inicio_sent + inicio, inicio_sent + fim))
    return spans


def _candidatos(texto: str, inicio_corpo: int) -> list[Achado]:
    """Todos os casamentos de todas as famílias, com sobreposição ainda possível."""
    achados: list[Achado] = []
    corpo = texto[inicio_corpo:]

    def registrar(m: re.Match, familia: str, tipo: str) -> None:
        inicio, fim = _aparar(texto, inicio_corpo + m.start(), inicio_corpo + m.end())
        if fim <= inicio:
            return
        # Os grupos que a expressão já isolou seguem junto: reparsear o trecho na
        # resolução erraria onde a detecção acertou — `5úmula 211` tem dois
        # números e só um é o da súmula.
        dados = tuple((k, v) for k, v in (m.groupdict() or {}).items() if v)
        achados.append(Achado(inicio, fim, texto[inicio:fim], familia, tipo, dados))

    for m in _SUMULA.finditer(corpo):
        registrar(m, "sumula", "jurisprudencia")
    for m in _TEMA.finditer(corpo):
        registrar(m, "tema", "jurisprudencia")
    for m in _DISPOSITIVO.finditer(corpo):
        registrar(m, "dispositivo", "lei")
    vagas: list[tuple[int, int]] = []
    for m in _VAGA.finditer(corpo):
        # Um número de processo **imediatamente à esquerda** do casamento torna a
        # citação resolvível, e `vaga` tem precedência sobre `processo`: em
        # "REsp 1.234.567/SP, de 2019, Rel. Min. Fulano" a expressão casa a partir
        # do `SP` — o número fica fora do próprio casamento — e roubaria o span da
        # família que sabe resolvê-lo. Classe errada custa duas vezes na métrica.
        #
        # A janela é curta de propósito. Olhar a sentença inteira derrubava cinco
        # `incompleta` do gabarito que apenas dividem a frase com outra citação
        # numerada: medido, o score caía de 1,0988 para 1,0518. O que desqualifica
        # a família é o número **desta** citação, não o de uma vizinha.
        if _tem_numero_de_processo(corpo[max(0, m.start() - 24) : m.start()]):
            continue
        registrar(m, "vaga", "jurisprudencia")
        vagas.append((m.start(), m.end()))

    # A contagem de constituintes é a rede para as ordens que `_VAGA` não prevê.
    # Só entra onde a forma canônica não casou — assim o span que o gabarito
    # anota continua vindo da expressão, que é mais justa na borda.
    for inicio_vaga, fim_vaga in _vagas_por_constituinte(corpo):
        if any(not (fim_vaga <= i or inicio_vaga >= f) for i, f in vagas):
            continue
        inicio, fim = _aparar(texto, inicio_corpo + inicio_vaga, inicio_corpo + fim_vaga)
        if fim > inicio:
            achados.append(Achado(inicio, fim, texto[inicio:fim], "vaga", "jurisprudencia"))
            vagas.append((inicio_vaga, fim_vaga))

    for m in _NUMERO_PROCESSO.finditer(corpo):
        if _digitos(m.group()) < _MINIMO_DIGITOS:
            continue
        if not _e_numero_de_processo(m.group(), corpo[: m.start()]):
            continue
        inicio = _expandir_prefixo(corpo, m.start())
        fim = m.end()
        uf = _UF.match(corpo, fim)
        if uf is not None:
            fim = uf.end()
        inicio, fim = _aparar(texto, inicio_corpo + inicio, inicio_corpo + fim)
        if fim > inicio:
            achados.append(Achado(inicio, fim, texto[inicio:fim], "processo", "jurisprudencia"))

    return achados


# Quando dois spans brigam pelo mesmo trecho, esta é a ordem de quem manda. As
# famílias específicas ganham de `processo`, cujo prefixo genérico casaria
# "Súmula 331" e "art. 373" como se fossem número de processo.
_PRECEDENCIA = {"dispositivo": 0, "sumula": 1, "tema": 2, "vaga": 3, "processo": 4}


def _resolver_sobreposicao(achados: list[Achado]) -> list[Achado]:
    """Mantém um span por região do texto.

    Não é preferência de estilo: duas citações preditas com IoU ≥ 0,5 entre si
    fazem o avaliador oficial **rejeitar a submissão inteira** (§8).
    """
    ordenados = sorted(
        achados,
        key=lambda a: (_PRECEDENCIA[a.familia], -(a.fim - a.inicio), a.inicio),
    )
    escolhidos: list[Achado] = []
    for achado in ordenados:
        if any(not (achado.fim <= e.inicio or achado.inicio >= e.fim) for e in escolhidos):
            continue
        escolhidos.append(achado)
    return sorted(escolhidos, key=lambda a: a.inicio)


def detectar(texto: str) -> list[Achado]:
    """Encontra todas as citações candidatas no documento.

    Devolve os achados ordenados por posição, sem sobreposição entre si.
    """
    return _resolver_sobreposicao(_candidatos(texto, fim_do_cabecalho(texto)))
