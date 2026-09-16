"""Detecção dos spans de citação no texto do parecer.

Quem não entrega o span de uma citação não consegue classificá-la, e isso conta
como erro de recall. O alinhamento com o gabarito é por sobreposição com
IoU ≥ 0,5, então a borda exata não precisa ser perfeita — mas a citação inteira
precisa aparecer.

A organização é por família, porque a família determina contra o quê a citação
é resolvida:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.599.910/PR``)
``sumula``       ``Súmula 331 do TST``, ``Súmula Vinculante 10``
``tema``         ``Tema 2.680 da repercussão geral``
``dispositivo``  ``art. 373, I, do CPC``
``vaga``         sem identificador suficiente para consultar a base

**A âncora de ``processo`` é o número, não a sigla.** Medindo o gabarito, as
classes processuais aparecem em mais de 90 grafias distintas — de ``RR-`` a
``Embargos de Declaração no Agravo Interno no Agravo em Recurso Especial nº``.
Enumerá-las casa a amostra de desenvolvimento e falha no conjunto cego, onde o
material avisa que "as siglas processuais observadas não esgotam o domínio".
Ancorar no número e expandir para a esquerda degrada bem: numa classe não vista
o span fica curto, mas o número — que é o que resolve — continua capturado, e o
span costuma sobreviver ao IoU ≥ 0,5.

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

from .texto import fim_do_cabecalho

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

FAMILIAS = ("processo", "sumula", "tema", "dispositivo", "vaga")

# Abaixo disso não há número de processo — só ano, inciso e página.
_MINIMO_DIGITOS = 4

# "nº" em todas as grafias que a amostra traz, inclusive as de OCR (No, N°, n.).
_NUMERO = r"(?:n\s*[.ºo°]{0,2}|N\s*[.ºO°]{0,2})"

# Pontuação que pode aparecer dentro de um número de processo, incluindo a
# quebra de linha e o espaço não-quebrável (`533-80. 2012` vem com \xa0).
_DENTRO = r"[\s.\-–—/]"

# O núcleo numérico: começa e termina em dígito. As letras de OCR coladas a
# dígito entram no span para não cortar a citação ao meio (`21737l8`).
_NUCLEO = rf"\d(?:{_DENTRO}*[\dOolISsgGbBZz]){{3,}}"

# Sufixo de UF: /RJ, - PR, (SC), – MA.
_UF = re.compile(r"\s*[/(\-–—]\s*[A-Z]{2}\s*\)?")

_NUMERO_PROCESSO = re.compile(_NUCLEO)

# Um elo da cadeia de prefixo, testado com fullmatch token a token. Três formas:
# sigla iniciada em maiúscula (REsp, AgR-REspe, H.C., TST-ED-E-ED-RR-), marca de
# número (nº, n°, No, n.) e um punhado de palavras minúsculas.
#
# A restrição às minúsculas é o que impede o prefixo de engolir a prosa: em
# "Ampara a pretensão o RSE nº 700…", o "o" não é conector conhecido e a cadeia
# para ali. Sem isso o span começaria em "Ampara".
_ELO = re.compile(
    r"(?:"
    r"[A-ZÀ-Ú][\wÀ-ú]*\.?(?:[-‐][A-Za-zÀ-Ú0-9][\wÀ-ú]*\.?)*[-‐]?"
    r"|[nN]\s*[.ºo°O]{1,2}"
    r"|n[oa]s?|d[oae]s?|em|e|processo|autos"
    r"|[-‐]"
    r")",
    re.UNICODE,
)

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
    r"|Constitui[çc][ãa]o(?:\s+Federal)?"
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
# "relatoria dc Sérgio Kukinã" — e→c. Era a última citação não detectada.
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

_VAGA = re.compile(
    rf"{_CABECA_VAGA}"
    rf"(?:\s*,?\s*d[oa]\s+(?:{'|'.join(TRIBUNAIS)}))?"
    r"\s*,?\s*(?:proferid[oa]|julgad[oa]|profcrid[oa])?\s*(?:de|em)\s*\n?\s*"
    r"(?:19|20)\d{2}"
    r"[^.]{0,30}?"
    rf"{_RELATOR}\s*{_NOME_PROPRIO}",
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

# `fls. 762/872`, `143/925` — referência de página, distrator documentado.
_PAGINAS = re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$")

# `255/2021`, `13.105/2015` — protocolo ou lei. Número de processo não termina
# em ano: no padrão CNJ o ano fica no meio, e no número único do STJ, na frente.
_TERMINA_EM_ANO = re.compile(r"^\d{1,5}(?:\.\d{3})*\s*/\s*(?:19|20)\d{2}$")

# Rótulos que marcam o número seguinte como distrator, não como citação.
_ROTULO_DISTRATOR = re.compile(
    r"(?:fls?|folhas?|protocolo|CPF|CNPJ|valor\s+da\s+causa|R\$"
    r"|OAB\s*/?\s*[A-Z]{0,2})\s*\.?\s*$",
    re.IGNORECASE,
)


def _e_numero_de_processo(numero: str, antes: str) -> bool:
    """Filtra o que tem forma de número mas não identifica processo."""
    compacto = numero.strip()
    if _ANO_SOLTO.match(compacto) or _PAGINAS.match(compacto):
        return False
    if _TERMINA_EM_ANO.match(compacto):
        return False
    return not _ROTULO_DISTRATOR.search(antes[-24:])


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
        if not token or not _ELO.fullmatch(token):
            break
        posicao = recuo
    return posicao


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
    for m in _VAGA.finditer(corpo):
        registrar(m, "vaga", "jurisprudencia")
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
