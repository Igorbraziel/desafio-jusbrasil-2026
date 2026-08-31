"""Da citação detectada à classe, consultando a base canônica.

A classe não é predita por um classificador — é consequência da cardinalidade da
consulta, exatamente como descreve o material do desafio:

===========================================  ============  ==========================
candidatos encontrados                        classe        saída
===========================================  ============  ==========================
exatamente 1                                  real          ``id_canonico`` do registro
0                                             inventada     ``resolucao: null``
2 ou mais, sem critério de desempate          incompleta    ``resolucao: null``
===========================================  ============  ==========================

Uma citação sem identificadores para sequer formular a consulta é ``incompleta``
sem passar pelo banco.
"""

from __future__ import annotations

from .base_canonica import SUMULAS, BaseCanonica
from .deteccao import Achado
from .normalizacao import chave_textual, digitos_do_identificador

# Como reconhecer o diploma legal citado. A ordem importa: "código de processo
# penal" precisa ser testado antes de qualquer coisa que case "código de
# processo". Cada entrada casa contra o trecho sem acento e em minúsculas.
CODIGOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CPC", ("codigo de processo civil", "cpc", "13.105/2015", "13105/2015")),
    ("CPP", ("codigo de processo penal", "cpp", "3.689", "3689/1941")),
    ("CPM", ("codigo penal militar", "cpm", "1.001/1969")),
    ("CDC", ("codigo de defesa do consumidor", "cdc", "8.078/1990")),
    ("CLT", ("consolidacao das leis do trabalho", "clt", "5.452")),
    ("ELEITORAL", ("codigo eleitoral", "4.737")),
    ("LC64", ("lei complementar n 64/1990", "complementar", "64/1990", "64/90")),
    ("CF", ("constituicao", "carta magna", "cf/88", "cf")),
    ("CC", ("codigo civil", "cc")),
)

# Confianças por caminho de decisão, medidas na amostra de desenvolvimento
# (`make calibrar`). Um caminho que acertou tudo nos 26 documentos ainda não
# merece 1.0: o conjunto cego é maior, e o Brier pune excesso de certeza mais do
# que recompensa acerto.
CONFIANCA = {
    "processo_real": 0.95,
    "processo_inventada": 0.92,
    "processo_ambiguo": 0.60,
    "sumula_real": 0.95,
    "sumula_inventada": 0.92,
    "sumula_ambigua": 0.55,
    "tema": 0.85,
    "dispositivo_real": 0.95,
    "dispositivo_inventada": 0.90,
    "dispositivo_desconhecido": 0.80,
    "vaga": 0.93,
}


def _codigo_do_diploma(diploma: str) -> str | None:
    chave = chave_textual(diploma)
    for codigo, marcas in CODIGOS:
        if any(marca in chave for marca in marcas):
            return codigo
    return None


def _resolver_processo(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    numero = digitos_do_identificador(achado.trecho)
    candidatos = base.candidatos_por_numero(numero)
    if not candidatos:
        return "inventada", None, CONFIANCA["processo_inventada"]
    if len(candidatos) == 1:
        return "real", candidatos[0].id_canonico, CONFIANCA["processo_real"]
    # Mais de um registro reivindica o número: são duplicatas do mesmo julgado.
    # `candidatos_por_numero` já devolve a versão mais completa primeiro.
    return "real", candidatos[0].id_canonico, CONFIANCA["processo_ambiguo"]


def _resolver_sumula(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    dados = dict(achado.dados)
    if not dados.get("numero"):
        return "incompleta", None, CONFIANCA["sumula_ambigua"]
    numero = int(dados["numero"])
    vinculante = "vinculante" in chave_textual(achado.trecho)
    tribunal = dados["tribunal"].upper() or None

    id_canonico = base.sumula(tribunal, vinculante, numero)
    if id_canonico is not None:
        return "real", id_canonico, CONFIANCA["sumula_real"]
    if tribunal is None and not vinculante:
        # Sem o tribunal, "Súmula 83" pode ser de qualquer corte. Se um único
        # registro da cobertura tem esse número, resolve; senão, é ambígua.
        possiveis = {v for (_, vinc, n), v in SUMULAS.items() if n == numero and not vinc}
        if len(possiveis) == 1:
            return "real", possiveis.pop(), CONFIANCA["sumula_real"]
        if possiveis:
            return "incompleta", None, CONFIANCA["sumula_ambigua"]
    return "inventada", None, CONFIANCA["sumula_inventada"]


def _resolver_dispositivo(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    dados = dict(achado.dados)
    if not dados.get("artigo"):
        return "incompleta", None, CONFIANCA["dispositivo_desconhecido"]
    artigo = int(dados["artigo"].replace(".", ""))
    codigo = _codigo_do_diploma(dados.get("diploma", ""))
    if codigo is None:
        # O diploma está nomeado ("Lei nº 9.504/1997"), então há identificadores
        # suficientes para consultar — só não existe registro correspondente na
        # cobertura congelada. Isso é `inventada`, não `incompleta`.
        return "inventada", None, CONFIANCA["dispositivo_inventada"]
    id_canonico = base.dispositivo(codigo, artigo)
    if id_canonico is None:
        return "inventada", None, CONFIANCA["dispositivo_inventada"]
    return "real", id_canonico, CONFIANCA["dispositivo_real"]


def resolver(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    """Classifica um achado e, quando `real`, devolve o ``id_canonico``."""
    if achado.familia == "vaga":
        return "incompleta", None, CONFIANCA["vaga"]
    if achado.familia == "processo":
        return _resolver_processo(achado, base)
    if achado.familia == "sumula":
        return _resolver_sumula(achado, base)
    if achado.familia == "dispositivo":
        return _resolver_dispositivo(achado, base)
    if achado.familia == "tema":
        # A cobertura congelada não tem registros de tema de repercussão geral:
        # o identificador é suficiente para buscar e nada corresponde.
        return "inventada", None, CONFIANCA["tema"]
    raise ValueError(f"família desconhecida: {achado.familia}")
