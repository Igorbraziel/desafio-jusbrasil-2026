"""Detecção dos spans de citação no texto do parecer.

Quem não entrega o span de uma citação não consegue classificá-la, e isso conta
como erro de recall. O alinhamento com o gabarito é por sobreposição com
IoU ≥ 0,5, então a borda exata não precisa ser perfeita — mas a citação inteira
precisa aparecer.

São cinco famílias, e a classe da citação depende de qual delas casou:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.599.910/PR``)
``sumula``       ``Súmula 331 do TST``, ``Súmula Vinculante 10``
``tema``         ``Tema 2.680 da repercussão geral``
``dispositivo``  ``art. 373, I, do CPC``
``vaga``         sem identificador suficiente para consultar a base

As duas primeiras famílias resolvem contra a base; ``vaga`` é ``incompleta``
sem passar pelo banco.

**Distratores.** Os cabeçalhos trazem números que parecem citação e não são:
número dos autos do próprio documento, protocolo, inscrição na OAB, ``fls.
234/567``, valor da causa. Nenhum está no gabarito, e extraí-los conta como
falso positivo — por isso a detecção começa depois do bloco de metadados
(:func:`verificador.texto.fim_do_cabecalho`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .normalizacao import SEPARADORES, chave_textual
from .texto import fim_do_cabecalho

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")


@dataclass(frozen=True)
class Achado:
    """Um span candidato a citação, antes de ser resolvido.

    ``dados`` leva os grupos que a expressão regular já isolou — o número do
    artigo, o diploma legal, o número da súmula. Reaproveitá-los evita que a
    resolução tenha de reparsear o trecho e errar onde a detecção acertou
    (``5úmula 211`` tem dois números; só um deles é o da súmula).
    """

    inicio: int
    fim: int
    trecho: str
    familia: str  # processo · sumula · tema · dispositivo · vaga
    tipo: str  # jurisprudencia · lei
    dados: tuple[tuple[str, str], ...] = ()


# ---------------------------------------------------------------------------
# Casamento tolerante a ruído
# ---------------------------------------------------------------------------
# O nível 2 corrompe letras isoladas dentro das palavras: "entendirnento",
# "jurisprudêneia", "profcrido", "recentc", "Fedcral". Comparar strings exatas
# perde todas elas. Em vez de enumerar as corrupções, casamos cada palavra por
# seu esqueleto — as duas primeiras letras mais o comprimento, com folga de um
# caractere. Absorve uma substituição, uma inserção ou uma remoção em qualquer
# posição a partir da terceira letra, que é onde o ruído aparece. Ancorar
# também a última letra seria mais restritivo, mas perderia "recentc".


def palavra_tolerante(palavra: str) -> str:
    if len(palavra) <= 3:
        return re.escape(palavra)
    prefixo = re.escape(palavra[:2])
    resto = len(palavra) - 2
    return rf"{prefixo}\w{{{max(0, resto - 1)},{resto + 1}}}"


def frase_tolerante(frase: str) -> re.Pattern[str]:
    """Compila uma frase em regex que absorve ruído de OCR e quebra de linha."""
    corpo = r"\s+".join(palavra_tolerante(p) for p in frase.split())
    return re.compile(corpo, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Família "vaga": citações sem identificador
# ---------------------------------------------------------------------------
# Estas frases são evasivas por construção — "jurisprudência pacífica desta
# Corte" não permite sequer formular a consulta. São sempre `incompleta`.

FRASES_VAGAS_JURISPRUDENCIA = (
    "jurisprudência pacífica desta Corte",
    "jurisprudência consolidada dos tribunais superiores",
    "entendimento sumulado sobre a matéria",
    "verbete sumular aplicável à espécie",
    "orientação jurisprudencial da Corte Superior",
    "precedentes desta Casa em situações análogas",
    "precedente firmado em sede de recurso repetitivo",
    "reiterados precedentes do Superior Tribunal de Justiça",
    "recente acórdão da Segunda Turma",
)
FRASES_VAGAS_LEI = (
    "normas de regência da matéria",
    "dispositivo constitucional invocado na origem",
    "artigo correspondente do Código de Processo Civil",
    "legislação de regência da matéria",
    "lei que disciplina a prescrição no caso",
    "dispositivo legal de regência",
)

_VAGAS = [(frase_tolerante(f), "jurisprudencia") for f in FRASES_VAGAS_JURISPRUDENCIA] + [
    (frase_tolerante(f), "lei") for f in FRASES_VAGAS_LEI
]

# A outra forma de citação vaga tem identificadores, mas insuficientes para
# desempatar: tribunal + ano + relator casa com dezenas de acórdãos.
# Ex.: "julgado do STF proferido em 2024 pela relatoria de Dias Toffoli".
NOME_PROPRIO = r"[A-ZÀ-Ý][^\s,.;:]*(?:\s+(?:de|da|do|dos|das|e)\b|\s+[A-ZÀ-Ý][^\s,.;:]*)*"
ANO_E_RELATOR = re.compile(
    r"(?:\b(?:proferid|julgad)\w{0,3}\s+)?"
    r"(?:,\s*)?\b(?:de|em)\s+(?:19|20)\d{2}\s*,?\s*"
    r"(?:Rel\.?\s*Min\.?\s*|(?:pel\w|d\w|sob)\s+relatoria\s+d\w\s+|relatoria\s+d\w\s+)"
    rf"(?:{NOME_PROPRIO})",
    re.IGNORECASE | re.MULTILINE,
)
# Palavras de ligação: sozinhas não caracterizam citação nenhuma.
LIGACAO = {"em", "de", "do", "da", "no", "na", "nos", "nas", "e", "n", "no."}

# Classes processuais e siglas. Uma citação de processo precisa de pelo menos
# uma destas à esquerda do número — é o que separa "AR n. 2785" de "de 2025".
VOCABULARIO_CLASSE = {
    "julgado",
    "precedente",
    "precedentes",
    "acordao",
    "acordaos",
    "decisao",
    "reclamacao",
    "rcl",
    "apl",
    "rse",
    "resp",
    "aresp",
    "respe",
    "rhc",
    "hc",
    "recurso",
    "recursos",
    "em",
    "de",
    "do",
    "da",
    "no",
    "na",
    "especial",
    "eleitoral",
    "habeas",
    "corpus",
    "agravo",
    "extraordinario",
    "mandado",
    "seguranca",
    "apelacao",
    "embargos",
    "declaracao",
    "interno",
    "regimental",
    "instrumento",
    "suspensao",
    "liminar",
    "sentenca",
    "acao",
    "rescisoria",
    "sumula",
    "vinculante",
    "processo",
    "autos",
    *(t.lower() for t in TRIBUNAIS),
} | LIGACAO

# ---------------------------------------------------------------------------
# Família "processo": número + classe processual
# ---------------------------------------------------------------------------
NUCLEO = re.compile(rf"\d[\dOolIiSsgGBZzq{re.escape(SEPARADORES)}]*\d[OolIiSsgGBZzq]?")
SUFIXO_UF = re.compile(r"\s*[/\-‐-—(]\s*[A-Z]{2}\s*\)?")
# Palavras que fazem parte de uma citação de processo, à esquerda do número.
VOCABULARIO_PROCESSO = VOCABULARIO_CLASSE | {
    "agint",
    "agrg",
    "agr",
    "ag",
    "agreg",
    "agregado",
    "edcl",
    "eds",
    "ed",
    "e",
    "esp",
    "rr",
    "arr",
    "airr",
    "agarr",
    "ms",
    "rms",
    "ar",
    "ai",
    "re",
    "recl",
    "arespei",
    "agresp",
    "tst",
    "r",
    "rp",
    "int",
    "terceiro",
    "segundo",
    "primeiro",
    "quarto",
    "n",
    "num",
    "numero",
    "rec",
    "aresps",
}
# "nº", "n.", "n°", "No", "Nº" — o marcador de número, em todas as variantes.
MARCADOR_NUMERO = re.compile(r"^n[.ºo°]*$", re.IGNORECASE)
MAXIMO_TOKENS_PREFIXO = 14

# Contextos que denunciam um distrator mesmo fora do cabeçalho.
DISTRATORES = re.compile(
    r"\b(?:fls?\.|folhas?|OAB|protocolo|R\$|valor da causa|inscri\w+)\b", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Famílias "sumula", "tema" e "dispositivo"
# ---------------------------------------------------------------------------
SUMULA = re.compile(
    r"\b[S5][úùuû]m(?:ula|\.)\s*(?:Vinculante\s*)?(?:n?[.ºo°]\s*)?(\d{1,4})"
    r"(?:\s*d[eo]\s*(STF|STJ|TST|TSE|STM))?",
    re.IGNORECASE,
)
TEMA = re.compile(r"\bTem[aã]\s*(?:n?[.ºo°]\s*)?[\d.]{1,8}(?:\s+d\w\s+repercuss\w+\s+geral)?")

ARTIGO = re.compile(
    r"\bart(?:\.|igo)?\s*\n?\s*(\d{1,3}(?:\.\d{3})*)\s*[ºo°ª]?"  # o número do artigo
    # incisos, parágrafos e alíneas: ", I", ", § 1º-A", ", 'g'"
    r"((?:\s*,?\s*(?:[IVXLC]+|§\s*\d+\s*[ºo°]?(?:\s*-\s*[A-Z])?|['\"][a-z]['\"]|[a-z]\)))*)"
    r"\s*,?\s*(?:d[aeo]s?\s+)?"
    r"(Constitui\w+(?:\s+\w+){0,2}|Consolida\w+\s+das\s+Leis\s+do\s+Trabalho"
    r"|C[óo]digo(?:\s+\w+){0,5}|Lei\s+Complementar\s*n?[.ºo°]*\s*[\d.]+/\d{2,4}"
    r"|Lei\s*n?[.ºo°]*\s*[\d.]+/\d{2,4}|CPC|CPP|CPM|CLT|CDC|CF|CC)\b",
    re.IGNORECASE,
)


def _tokens_a_esquerda(texto: str, posicao: int, vocabulario: set[str]) -> int:
    """Recua sobre as palavras que ainda fazem parte da citação.

    Devolve o offset onde a citação começa. Paramos na primeira palavra fora do
    vocabulário — é o que impede a citação de engolir a prosa em volta
    ("Ao apreciar a RCL n° 33128" começa em "RCL", não em "Ao").
    """
    inicio = posicao
    for _ in range(MAXIMO_TOKENS_PREFIXO):
        anterior = texto[:inicio]
        m = re.search(r"([\wÀ-ÿ][\wÀ-ÿ.'ºo°-]*)\s*$", anterior)
        if not m:
            break
        palavra = m.group(1)
        if not _no_vocabulario(palavra, vocabulario):
            break
        inicio = m.start(1)
    return inicio


def _no_vocabulario(palavra: str, vocabulario: set[str]) -> bool:
    """Uma palavra pertence à citação se todas as suas partes pertencem.

    Compostos como ``TST-E-RR-`` e ``A.REsp`` são uma palavra só para o
    tokenizador, mas várias siglas encadeadas para o leitor.
    """
    chave = chave_textual(palavra).strip(".-'")
    if not chave:
        return False
    if chave in vocabulario or MARCADOR_NUMERO.match(chave):
        return True
    partes = [p for p in re.split(r"[.\-]", chave) if p]
    # Iniciais de uma letra só valem dentro de um composto ("H.C.", "A.REsp").
    # Soltas, seriam o artigo da frase — e a citação engoliria o "o" antes dela.
    return len(partes) > 1 and all(
        len(p) == 1 or p in vocabulario or MARCADOR_NUMERO.match(p) for p in partes
    )


ANO = re.compile(r"^(?:19|20)\d{2}$")
PREPOSICAO_DE_DATA = re.compile(r"\b(?:de|em)\s*$", re.IGNORECASE)


def _e_ano_em_data(texto: str, m: re.Match[str]) -> bool:
    """Um ano de quatro dígitos precedido de "de"/"em" é data, não identificador."""
    return bool(ANO.match(m.group().strip()) and PREPOSICAO_DE_DATA.search(texto[: m.start()]))


def _tem_classe_processual(prefixo: str) -> bool:
    """O prefixo traz alguma sigla ou classe processual, e não só preposições?"""
    for palavra in re.findall(r"[\wÀ-ÿ][\wÀ-ÿ.'-]*", prefixo):
        chave = chave_textual(palavra).strip(".-'")
        partes = [p for p in re.split(r"[.\-]", chave) if p] or [chave]
        if any(p in VOCABULARIO_PROCESSO and p not in LIGACAO for p in partes):
            return True
    return False


def _sem_sobreposicao(achados: list[Achado]) -> list[Achado]:
    """Resolve spans concorrentes: vence o mais específico, depois o mais longo."""
    prioridade = {"dispositivo": 0, "sumula": 1, "tema": 2, "processo": 3, "vaga": 4}
    ordenados = sorted(achados, key=lambda a: (prioridade[a.familia], -(a.fim - a.inicio)))
    aceitos: list[Achado] = []
    for a in ordenados:
        if any(a.inicio < b.fim and b.inicio < a.fim for b in aceitos):
            continue
        aceitos.append(a)
    return sorted(aceitos, key=lambda a: a.inicio)


def detectar(texto: str) -> list[Achado]:
    """Encontra todas as citações candidatas no documento."""
    corte = fim_do_cabecalho(texto)
    achados: list[Achado] = []

    def registrar(inicio: int, fim: int, familia: str, tipo: str, **dados: str) -> None:
        if inicio < corte:
            return
        trecho = texto[inicio:fim]
        if not trecho.strip():
            return
        achados.append(Achado(inicio, fim, trecho, familia, tipo, tuple(dados.items())))

    for m in ARTIGO.finditer(texto):
        registrar(m.start(), m.end(), "dispositivo", "lei", artigo=m.group(1), diploma=m.group(3))

    for m in SUMULA.finditer(texto):
        registrar(
            m.start(),
            m.end(),
            "sumula",
            "jurisprudencia",
            numero=m.group(1),
            tribunal=m.group(2) or "",
        )

    for m in TEMA.finditer(texto):
        registrar(m.start(), m.end(), "tema", "jurisprudencia")

    for m in ANO_E_RELATOR.finditer(texto):
        inicio = _tokens_a_esquerda(texto, m.start(), VOCABULARIO_CLASSE)
        registrar(inicio, m.end(), "vaga", "jurisprudencia")

    for padrao, tipo in _VAGAS:
        for m in padrao.finditer(texto):
            registrar(m.start(), m.end(), "vaga", tipo)

    for m in NUCLEO.finditer(texto):
        digitos = re.sub(r"\D", "", m.group())
        if len(digitos) < 4:
            continue
        if _e_ano_em_data(texto, m):
            continue  # "de 2025" é data de julgamento, não número de processo
        inicio = _tokens_a_esquerda(texto, m.start(), VOCABULARIO_PROCESSO)
        if not _tem_classe_processual(texto[inicio : m.start()]):
            # Número solto ou precedido só de preposição ("de 2025"): não é citação.
            continue
        contexto = texto[max(0, inicio - 40) : inicio]
        if DISTRATORES.search(contexto):
            continue
        fim = m.end()
        uf = SUFIXO_UF.match(texto, fim)
        if uf:
            fim = uf.end()
        registrar(inicio, fim, "processo", "jurisprudencia")

    return _sem_sobreposicao(achados)
