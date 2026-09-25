"""A classe processual como conjunto de marcas comparáveis.

Serve a uma decisão só: o desempate entre acórdãos distintos que dividem o mesmo
número próprio. Na base eles são incidentes do mesmo processo — o recurso
especial e o agravo interno nele, o recurso e os embargos de declaração, o
habeas corpus e o pedido de extensão —, e o que os separa é a classe. A citação
traz a classe no prefixo ("AgInt no REsp", "PExt no RHC"), o cabeçalho do
acórdão também ("AgInt no RECURSO ESPECIAL", "PExt no RECURSO EM HABEAS
CORPUS"), só que um em sigla e o outro por extenso.

Os dois lados viram o mesmo vocabulário de marcas: `agint`, `edcl`, `resp`,
`rhc`… A marca é da **espécie do incidente**, não do tribunal nem do recurso de
origem: o que desempata é "este é o agravo interno" contra "este é o recurso".
Nada aqui decide classe de citação; a detecção continua ancorada no número
(ADR 0002).
"""

from __future__ import annotations

import re

from .normalizacao import chave_textual

# Siglas e nomes por extenso das classes que aparecem nos cabeçalhos da base, já
# em `chave_textual` (minúsculas, sem acento). A ordem importa: o nome mais
# longo vem antes do que ele contém ("recurso em habeas corpus" antes de
# "habeas corpus"), porque cada trecho casado é consumido.
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

# A marca começa em fronteira de palavra ou logo depois de uma preposição colada
# a ela: o cabeçalho do STJ traz "AgInt nosEMBARGOS DE DIVERGÊNCIA", e sem isso o
# `edv` do registro não aparecia — o desempate não via o que separa o agravo
# interno no recurso especial do agravo interno nos embargos de divergência.
_INICIO = r"(?:(?<![a-z])|(?<=\bn[oa]s)|(?<=\bn[oa])|(?<=\bd[oa]s)|(?<=\bd[oa]))"

_EXPRESSAO = re.compile(
    "|".join(f"(?P<m{i}>{_INICIO}(?:{padrao})(?![a-z]))" for i, (padrao, _) in enumerate(_MARCAS))
)

# Os incidentes, que são as marcas que de fato separam os pares da base.
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
    """Quanto a classe do registro concorda com a da citação.

    Conta as marcas em comum e desconta os **incidentes** que só um dos lados
    tem: "AgInt no REsp" contra "AgInt nos EDv nos EREsp" empata no `agint` e
    no `resp`, e o `edv` que só o registro tem é o que o afasta. Marca de
    origem sobrando não desconta — a citação abrevia a cadeia de recursos.
    """
    comuns = len(da_citacao & do_registro)
    sobrando = len((da_citacao ^ do_registro) & INCIDENTES)
    return comuns - sobrando
