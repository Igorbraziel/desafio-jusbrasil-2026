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

import re

from .base_canonica import BaseCanonica
from .deteccao import Achado
from .normalizacao import chave_textual, digitos_do_identificador

# Confiança por caminho de decisão, **medida** por
# ``scripts/medir_confianca.py``: acurácia do caminho sobre o corpus limpo mais
# três sementes de perturbação a taxa 0,15, com predição sem par contando como
# erro. Antes eram palpite, e o comentário aqui dizia isso.
#
# Medir importa porque o bônus da métrica é ``b = 0,10·(1 − Brier)`` e o Brier é
# minimizado exatamente em ``p = acurácia``. Emitir 0,93 num caminho que acerta
# 0,996 joga bônus fora; emitir 0,80 num que acerta 0,67 é pior, porque a
# punição é quadrática. Os dois casos existiam.
#
# Os valores passam por Laplace — ``(acertos + 1) / (total + 2)`` — e não pela
# taxa bruta. É o que impede um caminho com quatro observações de reivindicar
# 1,0: `real_desempate` acertou 4 de 4, e a ADR 0003 registra que o critério de
# desempate está refutado. Laplace encolhe esse caminho para 0,83 em vez de 1,0,
# que é a humildade que a evidência comporta.
#
# Medido sob perturbação, e não no conjunto limpo, de propósito: no limpo todo
# caminho acerta 100% e a calibração mandaria emitir 1,0 em tudo. O conjunto
# cego tem formas que a amostra não tem, e o arnês é a única aproximação dessa
# diferença que temos.
CONFIANCA = {
    "real_unico": 0.99,  # 273/274
    "real_desempate": 0.83,  # 4/4, encolhido pelo suporte baixo
    "real_tabela": 0.98,  # 61/61
    "inventada_processo": 0.83,  # 158/190 — o caminho mais errático
    "inventada_tabela": 0.95,  # 60/62
    "inventada_tema": 0.60,  # 2/3, encolhido pelo suporte baixo
    "incompleta_vaga": 0.99,  # 114/114
    # Não exercido pelo arnês nem pelo conjunto de desenvolvimento: sem medição,
    # fica o valor conservador. É o único palpite que sobrou, e está declarado.
    "incompleta_sem_numero": 0.70,
}

# Diploma legal citado -> chave da tabela DISPOSITIVOS. A ordem importa: a
# entrada mais específica precisa ser testada antes da que a contém, senão
# "Código de Processo Civil" casaria em "civil" e viraria Código Civil. Por isso
# "processo penal militar" vem antes de "processo penal", que vem antes de
# "penal militar": o CPPM não está na cobertura, e sem essa ordem ele casava o
# CPP e o artigo 312 do CPPM resolvia para o 312 do CPP.
#
# O casamento é por conteúdo e não por igualdade porque o nível 2 corrompe uma
# letra por palavra: a amostra traz "Constituição Fedcral", que precisa resolver
# para CF do mesmo jeito que "Constituição da República".
#
# ``excluir`` é o que impede o marcador genérico de capturar um diploma de fora
# da cobertura. Um marcador como "constituic" casa a Constituição Estadual tanto
# quanto a Federal, e "lei complementar" casa qualquer LC — os dois produziam
# `inventada` -> `real`, que é o erro grave da métrica (``s = macroF1·(1−0,5·τ)``,
# ~7x mais caro que um falso positivo comum). A cobertura é congelada: fora dela,
# a resposta certa é `inventada`, não um link plausível.
DIPLOMAS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("processo penal militar", "processo penal militar"), (), "CPPM_FORA"),
    (("processo civil", "13.105", "13105", "cpc"), (), "CPC"),
    (("processo penal", "3.689", "3689", "cpp"), ("militar",), "CPP"),
    (("penal militar", "1.001", "1001", "cpm"), (), "CPM"),
    (("defesa do consumidor", "8.078", "8078", "cdc"), (), "CDC"),
    (("consolidacao das leis", "clt"), (), "CLT"),
    (
        ("constituic", "carta magna", "cf/88", "cf"),
        ("estadual", "do estado", "estado de"),
        "CF",
    ),
    (("lei complementar", "lc 64", "64/1990"), (), "LC64"),
    (("eleitoral", "4.737", "4737"), (), "ELEITORAL"),
    (("civil", "cc"), (), "CC"),
)

# Número da lei que cada chave da tabela curada aceita. Quando a citação nomeia o
# número — "Lei Complementar nº 123/2006" —, ele é conferido contra esta tabela em
# vez de se confiar só no nome do diploma. Os números saem da primeira linha
# autodeclarada dos 13 registros de natureza `dispositivo`, desde 15/09/2026.
NUMERO_DA_LEI: dict[str, str] = {
    "CPC": "13105",
    "CPP": "3689",
    "CPM": "1001",
    "CDC": "8078",
    "CLT": "5452",
    "LC64": "64",
    "ELEITORAL": "4737",
    "CC": "10406",
}

# O número que acompanha o nome do diploma: "Lei nº 13.105", "LC 64/1990".
_NUMERO_CITADO = re.compile(r"(\d[\d.]*)(?:\s*/\s*(\d{2,4}))?")


def _codigo_do_diploma(diploma: str | None) -> str | None:
    """Reduz o nome citado do diploma à chave da tabela curada.

    Devolve ``None`` quando o diploma está nomeado mas fora da cobertura — o que
    o chamador traduz em `inventada`, não em falta de informação.
    """
    if not diploma:
        return None
    chave = chave_textual(diploma)
    for marcadores, exclusoes, codigo in DIPLOMAS:
        if not any(marcador in chave for marcador in marcadores):
            continue
        if any(exclusao in chave for exclusao in exclusoes):
            return None
        if codigo.endswith("_FORA"):
            # Diploma reconhecido e sabidamente fora da cobertura. Existe como
            # entrada para vencer o marcador mais genérico que o capturaria.
            return None
        return codigo if _numero_confere(chave, codigo) else None
    return None


def _numero_confere(chave: str, codigo: str) -> bool:
    """O número citado, quando houver, é o do diploma que a chave resolve?

    Sem isto, "Lei Complementar nº 123/2006" resolvia para a LC 64/1990 só por
    conter "lei complementar". Um diploma citado **sem** número continua valendo
    pelo nome — é assim que "art. 373 do CPC" resolve.
    """
    esperado = NUMERO_DA_LEI.get(codigo)
    if esperado is None:
        return True
    achado = _NUMERO_CITADO.search(chave)
    if achado is None:
        return True
    return achado.group(1).replace(".", "") == esperado


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

    # Empate. Pegamos o primeiro da ordenação de `candidatos_por_numero`, que é
    # determinística mas **arbitrária**: ela ordena por maior `texto_len`, e a
    # ADR 0003 registra que esse critério foi refutado pela distribuição de
    # 15/09 — o único par ambíguo que sobrou resolve para o candidato mais curto.
    # A ordem serve para estabilidade, não como preferência.
    #
    # O que continua valendo é a aritmética: chutar domina desistir. Link errado
    # num par `real`×`real` custa só `fp[real]`; rebaixar para `incompleta`
    # custaria o `fn[real]` **e** o `fp[incompleta]`. Ver a nota no topo do módulo.
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
