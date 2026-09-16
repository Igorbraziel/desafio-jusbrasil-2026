"""Da citação detectada à classe, consultando a base canônica.

A classe não precisa ser predita por um classificador — ela é consequência da
cardinalidade da consulta, como descreve o material do desafio:

===========================================  ============  ==========================
candidatos encontrados                        classe        saída
===========================================  ============  ==========================
exatamente 1                                  real          ``id_canonico`` do registro
0                                             inventada     ``resolucao: null``
2 ou mais, sem critério de desempate          incompleta    ``resolucao: null``
===========================================  ============  ==========================

Uma citação sem identificadores para sequer formular a consulta é ``incompleta``
sem passar pelo banco. E uma referência como "acórdão do STF de 2024, relatado
pelo Ministro Fulano" é buscável, mas casa com dezenas de candidatos: também
``incompleta``, por falta de critério de desempate.

**Empate: desempatar, não rebaixar — mas sem critério defensável.** A assimetria
da métrica é real e continua valendo: link errado num par ``real``×``real`` custa
só precisão (``fp[real]``, sem FN), enquanto rebaixar para ``incompleta`` custa o
FN da ``real`` **e** o FP da ``incompleta``. Chutar domina desistir.

O que **não** vale é o critério. Uma versão anterior desempatava pelo maior
``texto_len``, apoiada em três observações da distribuição de 04/09. A revisão de
15/09 reapontou o único par ambíguo que sobrou para o candidato **mais curto**, e
com isso a regra perdeu a evidência que tinha. Seguimos pegando o primeiro
candidato da ordenação, que é determinística mas arbitrária, e a ``confianca``
desse caminho reflete isso. Ver ``docs/investigacao.md``.

Cuidado com ``lei``: o número do artigo sozinho não identifica o dispositivo. O
gabarito traz o mesmo número de artigo sob dois códigos diferentes, um dentro e
outro fora da cobertura — só o código decide entre ``real`` e ``inventada``.

``confianca`` é opcional, mas alimenta o bônus de calibração de até 10%. No
avaliador oficial o bônus é ``max(0, 0,10·(1 − Brier))``: confiança mal
calibrada rende zero, igual a não enviar, e não há cenário em que enviar piore o
score. Por isso emitimos sempre, com um valor por caminho de decisão.
"""

from __future__ import annotations

from .base_canonica import BaseCanonica
from .deteccao import Achado
from .normalizacao import chave_textual, digitos_do_identificador

# Confiança por caminho de decisão. Os valores saem da taxa medida em
# scripts/medir_regiao.py e da detecção no conjunto de desenvolvimento, com
# desconto deliberado: um caminho que acertou tudo em 26 documentos ainda não
# merece 1,0, porque o conjunto cego tem formas que a amostra não tem.
CONFIANCA = {
    "real_unico": 0.93,
    "real_desempate": 0.55,
    "real_tabela": 0.95,
    "inventada_processo": 0.85,
    "inventada_tabela": 0.88,
    "inventada_tema": 0.80,
    "incompleta_vaga": 0.90,
    "incompleta_sem_numero": 0.70,
}

# Diploma legal citado -> chave da tabela DISPOSITIVOS. A ordem importa: a
# entrada mais específica precisa ser testada antes da que a contém, senão
# "Código de Processo Civil" casaria em "civil" e viraria Código Civil.
#
# O casamento é por conteúdo e não por igualdade porque o nível 2 corrompe uma
# letra por palavra: a amostra traz "Constituição Fedcral", que precisa resolver
# para CF do mesmo jeito que "Constituição da República".
DIPLOMAS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("processo civil", "13.105", "13105", "cpc"), "CPC"),
    (("processo penal", "3.689", "3689", "cpp"), "CPP"),
    (("penal militar", "1.001", "1001", "cpm"), "CPM"),
    (("defesa do consumidor", "8.078", "8078", "cdc"), "CDC"),
    (("consolidacao das leis", "clt"), "CLT"),
    (("constituic", "carta magna", "cf/88", "cf"), "CF"),
    (("lei complementar", "lc 64", "64/1990"), "LC64"),
    (("eleitoral", "4.737", "4737"), "ELEITORAL"),
    (("civil", "cc"), "CC"),
)


def _codigo_do_diploma(diploma: str | None) -> str | None:
    """Reduz o nome citado do diploma à chave da tabela curada."""
    if not diploma:
        return None
    chave = chave_textual(diploma)
    for marcadores, codigo in DIPLOMAS:
        if any(marcador in chave for marcador in marcadores):
            return codigo
    return None


def _inteiro(valor: str | None) -> int | None:
    if not valor:
        return None
    digitos = "".join(c for c in valor if c.isdigit())
    return int(digitos) if digitos else None


def _resolver_sumula(dados: dict[str, str], base: BaseCanonica) -> tuple[str, int | None, float]:
    numero = _inteiro(dados.get("numero"))
    if numero is None:
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]
    vinculante = bool(dados.get("vinculante"))
    tribunal = (dados.get("tribunal") or "").upper() or None
    id_canonico = base.sumula(tribunal, vinculante, numero)
    if id_canonico is None:
        return "inventada", None, CONFIANCA["inventada_tabela"]
    return "real", id_canonico, CONFIANCA["real_tabela"]


def _resolver_dispositivo(
    dados: dict[str, str], base: BaseCanonica
) -> tuple[str, int | None, float]:
    artigo = _inteiro(dados.get("artigo"))
    diploma = dados.get("diploma")
    codigo = _codigo_do_diploma(diploma)

    if artigo is None or not diploma:
        # Sem artigo ou sem diploma nomeado não dá para formular a consulta.
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]
    if codigo is None:
        # O diploma está nomeado, só não pertence à cobertura — e a cobertura é
        # congelada, então isso é `inventada`, não falta de informação. Era o
        # caso de "art. 172 da Lei nº 9.504/1997": a citação é específica o
        # bastante para ser refutada.
        return "inventada", None, CONFIANCA["inventada_tabela"]

    id_canonico = base.dispositivo(codigo, artigo)
    if id_canonico is None:
        return "inventada", None, CONFIANCA["inventada_tabela"]
    return "real", id_canonico, CONFIANCA["real_tabela"]


def _resolver_processo(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    numero = digitos_do_identificador(achado.trecho)
    if not numero:
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]

    candidatos = base.candidatos_por_numero(numero)
    if not candidatos:
        return "inventada", None, CONFIANCA["inventada_processo"]
    if len(candidatos) == 1:
        return "real", candidatos[0].id_canonico, CONFIANCA["real_unico"]

    # Empate: `candidatos_por_numero` já ordena por maior texto_len. Ver a nota
    # sobre desempate no topo do módulo — chutar domina desistir na métrica.
    return "real", candidatos[0].id_canonico, CONFIANCA["real_desempate"]


def resolver(achado: Achado, base: BaseCanonica) -> tuple[str, int | None, float]:
    """Classifica um achado e, quando ``real``, devolve o ``id_canonico``.

    Returns:
        ``(classificacao, id_canonico, confianca)`` — ``id_canonico`` é ``None``
        em tudo que não for ``real``.
    """
    dados = dict(achado.dados)

    if achado.familia == "vaga":
        # Tribunal + ano + relator: identifica uma decisão concreta, mas não
        # chega a um registro único. É `incompleta` por construção do gabarito,
        # e não por cardinalidade — por isso não consulta a base.
        return "incompleta", None, CONFIANCA["incompleta_vaga"]

    if achado.familia == "sumula":
        return _resolver_sumula(dados, base)

    if achado.familia == "dispositivo":
        return _resolver_dispositivo(dados, base)

    if achado.familia == "tema":
        # A cobertura congelada não tem registro de tema de repercussão geral:
        # qualquer tema é, por definição, inverificável contra ela.
        return "inventada", None, CONFIANCA["inventada_tema"]

    return _resolver_processo(achado, base)
