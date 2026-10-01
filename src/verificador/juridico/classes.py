"""A classe processual como conjunto de marcas comparáveis.

Usada só para desempatar acórdãos com o mesmo número (incidentes do mesmo
processo): sigla da citação e nome por extenso do cabeçalho viram as mesmas marcas.
"""

from __future__ import annotations

import re

from ..normalizacao import chave_textual

# Padrões em `chave_textual`. A ordem importa: o nome mais longo vem antes do que
# ele contém ("recurso em habeas corpus" antes de "habeas corpus").
_MARCAS: tuple[tuple[str, str], ...] = (
    # incidentes, que são o que diferencia os pares
    (r"ag(?:ravo)?\s*int(?:erno)?|agint", "agint"),
    (r"ag(?:ravo)?\s*\.?\s*reg(?:imental)?|agrg|agr", "agrg"),
    (r"emb(?:argos)?\s*\.?\s*(?:de\s+)?decl(?:aracao)?|edcl|eds?", "edcl"),
    (r"emb(?:argos)?\s*\.?\s*(?:de\s+)?div(?:ergencia)?|edv|eresp", "edv"),
    (r"pedido\s+de\s+extensao|pext", "pext"),
    (r"embargos\s+infringentes(?:\s+e\s+de\s+nulidade)?|einf", "einf"),
    (r"quest[aã]o\s+de\s+ordem|qo", "qo"),
    # classes de origem
    (r"recurso\s+em\s+habeas\s+corpus|rhc", "rhc"),
    (r"recurso\s+em\s+mandado\s+de\s+seguranca|rms", "rms"),
    (r"agravo\s+em\s+recurso\s+especial(?:\s+eleitoral)?|aresp|arespe(?:l)?", "aresp"),
    (r"recurso\s+especial\s+eleitoral|respe", "respe"),
    (r"recurso\s+especial|r\.?\s*esp|resp", "resp"),
    (r"recurso\s+extraordinario\s+com\s+agravo|are", "are"),
    (r"recurso\s+extraordinario|re", "re"),
    (r"recurso\s+ordinario|ro", "ro"),
    (r"recurso\s+em\s+sentido\s+estrito|rse", "rse"),
    (r"recurso\s+de\s+revista|rr", "rr"),
    (r"habeas\s+corpus|h\.?\s*c|hc", "hc"),
    (r"mandado\s+de\s+seguranca|ms", "ms"),
    (r"reclamacao|rcl", "rcl"),
    (r"apelacao(?:\s+criminal)?|apl", "apl"),
    (r"acao\s+rescisoria|ar", "ar"),
)

# Aceita marca colada à preposição: o cabeçalho do STJ traz "AgInt nosEMBARGOS".
_INICIO = r"(?:(?<![a-z])|(?<=\bn[oa]s)|(?<=\bn[oa])|(?<=\bd[oa]s)|(?<=\bd[oa]))"

_EXPRESSAO = re.compile(
    "|".join(f"(?P<m{i}>{_INICIO}(?:{padrao})(?![a-z]))" for i, (padrao, _) in enumerate(_MARCAS))
)

INCIDENTES = frozenset({"agint", "agrg", "edcl", "edv", "pext", "einf", "qo"})


def marcas(trecho: str) -> frozenset[str]:
    """As marcas de classe processual de um trecho de citação ou de cabeçalho."""
    chave = chave_textual(trecho)
    saida = set()
    for casamento in _EXPRESSAO.finditer(chave):
        indice = int(casamento.lastgroup[1:])
        saida.add(_MARCAS[indice][1])
    return frozenset(saida)


def afinidade(da_citacao: frozenset[str], do_registro: frozenset[str]) -> int:
    """Marcas em comum menos incidentes presentes em só um dos lados.

    Marca de origem sobrando não desconta: a citação abrevia a cadeia de recursos.
    """
    comuns = len(da_citacao & do_registro)
    sobrando = len((da_citacao ^ do_registro) & INCIDENTES)
    return comuns - sobrando
