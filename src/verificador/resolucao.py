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
from .normalizacao import OCR_PARA_DIGITO, _corrigir_ocr, chave_textual, digitos_do_identificador

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
    # **Inalcançável hoje**, e por invariante, não por falta de dados na amostra.
    # Os três caminhos que o retornam exigem uma citação detectada *sem* número,
    # e nenhuma das quatro famílias produz isso: `_SUMULA` exige `(?P<numero>\d+)`,
    # `_DISPOSITIVO` exige `(?P<artigo>\d+…)`, e a família `processo` só nasce
    # depois de `_digitos(m.group()) >= _MINIMO_DIGITOS` — quatro dígitos que a
    # normalização nunca remove, porque só troca letra por dígito.
    #
    # Fica como defesa em profundidade: se a detecção um dia afrouxar um desses
    # grupos, o guarda já está no lugar. O valor não é medido porque não há o que
    # medir; não é palpite pendente de calibração.
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
# da cobertura — hoje só o CPP, que não pode casar o CPPM. A cobertura é
# congelada: fora dela, a resposta certa é `inventada`, não um link plausível.
#
# A Constituição **não** usa mais exclusão. A lista era de qualificadores ruins
# conhecidos ("estadual", "do estado"), e qualquer um que não estivesse nela
# passava: `art. 5º da Constituição Portuguesa` resolvia para o art. 5º da CF/88.
# Uma lista de exclusão só fecha os casos que alguém lembrou de sondar; o erro
# grave (``s = macroF1·(1−0,5·τ)``, ~7x um falso positivo comum) pede o
# contrário — aceitar só o que identifica a CF/88. Ver `_diploma_confere`.
#
# Os números 5.452 (CLT) e 10.406 (CC) são como a primeira linha autodeclarada
# dos registros nomeia esses dois diplomas. `NUMERO_DA_LEI` já os conhecia; sem
# eles aqui, `art. 186 da Lei nº 10.406/2002` não achava diploma e virava
# `inventada`.
DIPLOMAS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("processo penal militar",), (), "CPPM_FORA"),
    (("processo civil", "13.105", "13105", "cpc"), (), "CPC"),
    (("processo penal", "3.689", "3689", "cpp"), ("militar",), "CPP"),
    (("penal militar", "1.001", "1001", "cpm"), (), "CPM"),
    (("defesa do consumidor", "8.078", "8078", "cdc"), (), "CDC"),
    (("consolidacao das leis", "clt", "5.452", "5452"), (), "CLT"),
    (("constituic", "carta magna", "cf"), (), "CF"),
    (("lei complementar", "lc 64", "64/1990"), (), "LC64"),
    (("eleitoral", "4.737", "4737"), (), "ELEITORAL"),
    (("civil", "cc", "10.406", "10406"), (), "CC"),
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

# Ano de cada diploma da cobertura, da mesma primeira linha autodeclarada
# ("Artigo 186 da Lei nº 10.406, de 10 de janeiro de 2002"). Serve para recusar
# a versão revogada: `Código Civil de 1916` e `CPC/73` têm os mesmos números de
# artigo da versão vigente, e sem conferir o ano resolviam para ela.
# `tests/test_base_canonica.py` confere as duas tabelas contra o banco.
ANO_DA_LEI: dict[str, int] = {
    "CF": 1988,
    "CPC": 2015,
    "CPP": 1941,
    "CPM": 1969,
    "CDC": 1990,
    "CLT": 1943,
    "LC64": 1990,
    "ELEITORAL": 1965,
    "CC": 2002,
}

# O número de uma lei citada pelo número — "lei no 13.105/2015", "lc 64/90",
# "decreto-lei no 5.452/1943" —, com o ano opcional depois da barra.
#
# A âncora na palavra "lei" é o que separa número de lei de ano. A versão
# anterior pegava o **primeiro** número da chave, e com o ano de versão agora
# capturado pela detecção isso quebrava: em "codigo de processo civil de 2015"
# o primeiro número é 2015, que não é 13.105, e a citação `real` virava
# `inventada`.
_LEI_NUMERADA = re.compile(r"\b(?:lei|lc|decreto)\b\D{0,24}?(\d(?:[\d.]*\d)?)(?:\s*/\s*(\d{2,4}))?")

# O ano de versão depois do nome ou da sigla: "de 1916", "cpc/73", "cf/88".
_ANO_DE_VERSAO = re.compile(r"(?:\bde\s+|/\s*)(\d{2,4})\b")

# O que identifica a CF/88 depois de "Constituição". A lista é de **inclusão**:
# qualquer outro qualificador — Estadual, Portuguesa, "do Estado" — é outro
# diploma, fora da cobertura.
#
# "do Brasil" entra porque, sem ano, é como a prosa corrente chama a CF/88. A
# Constituição de 1967 também se chamava "do Brasil", mas quem a cita põe o ano,
# e o ano é conferido antes contra `ANO_DA_LEI`.
_QUALIFICADORES_DA_CF = ("federal", "republica", "federativa", "brasileira", "brasil")
_CONECTORES = frozenset({"da", "do", "de", "das", "dos"})


def _ano(texto: str) -> int | None:
    """Ano com quatro dígitos, ou com dois como em "CPC/73". Outra forma não é ano."""
    if len(texto) == 4:
        return int(texto)
    if len(texto) == 2:
        ano = int(texto)
        return ano + (2000 if ano <= 30 else 1900)
    return None


def _distancia(a: str, b: str) -> int:
    """Distância de edição, para o qualificador corrompido pelo nível 2."""
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        atual = [i]
        for j, cb in enumerate(b, start=1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _qualificador_da_cf_confere(chave: str) -> bool:
    """A Constituição citada é a de 1988?

    Aceita a forma nua ("Constituição", "CF"), "Carta Magna", e um qualificador
    que identifique a Federal. O nível 2 corrompe uma letra por palavra
    ("Constituição Fedcral", no gabarito), então o qualificador é comparado com
    tolerância de edição. A tolerância é segura porque os qualificadores que
    levariam ao erro grave — Estadual, Portuguesa, Mineira — estão longe dos
    três aceitos.
    """
    if "carta magna" in chave or re.fullmatch(r"cf(?:\s*/\s*\d{2,4})?", chave):
        return True
    resto = re.sub(r"^constitui\w*", "", chave)
    resto = _ANO_DE_VERSAO.sub(" ", resto)  # o ano já foi conferido
    palavras = [p for p in resto.split() if p not in _CONECTORES]
    # **Toda** palavra precisa ser qualificador da CF/88 — "República Federativa
    # do Brasil" é o nome oficial por extenso. Uma só que não seja, e é outro
    # diploma.
    return all(
        any(_distancia(p, q) <= (2 if len(q) >= 7 else 1) for q in _QUALIFICADORES_DA_CF)
        for p in palavras
    )


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
        return codigo if _diploma_confere(chave, codigo) else None
    return None


def _diploma_confere(chave: str, codigo: str) -> bool:
    """O número e o ano citados, quando houver, são os do diploma da cobertura?

    Sem o número, "Lei Complementar nº 123/2006" resolvia para a LC 64/1990 só
    por conter "lei complementar". Sem o ano, "Código Civil de 1916" resolvia
    para o de 2002. Um diploma citado **sem** número nem ano continua valendo
    pelo nome — é assim que "art. 373 do CPC" resolve.

    Na dúvida, recusa: link errado em par `real`×`real` custa só precisão, mas
    `inventada` → `real` entra em τ.
    """
    ano: str | None = None
    lei = _LEI_NUMERADA.search(chave)
    if lei is not None:
        if lei.group(1).replace(".", "") != NUMERO_DA_LEI.get(codigo):
            return False
        ano = lei.group(2)
    if ano is None:
        versao = _ANO_DE_VERSAO.search(chave)
        ano = versao.group(1) if versao else None
    if ano is not None and _ano(ano) != ANO_DA_LEI.get(codigo):
        return False
    if codigo == "CF":
        return _qualificador_da_cf_confere(chave)
    return True


def _inteiro(valor: str | None) -> int | None:
    """O número da súmula ou do artigo, com o ruído de OCR desfeito.

    O reparo vem **antes** de extrair os dígitos. Descartar as letras direto
    encolhia o número: `I86` virava 86, e `3l73` virava 373 — artigo da
    cobertura, uma `inventada` resolvida como `real`, o erro grave.
    """
    if not valor:
        return None
    digitos = "".join(c for c in _corrigir_ocr(valor) if c.isdigit())
    return int(digitos) if digitos else None


# Ordinal de artigo: "art. 5º", "art. 5o", "art. 1°". Pela convenção da técnica
# legislativa, só os artigos 1 a 9 são ordinais — do 10 em diante é cardinal. O
# "o" minúsculo depois de um dígito isolado é a grafia do ordinal em texto
# simples, e não um zero corrompido: sem isto "art. 5o da CF" viraria o art. 50.
#
# O "O" maiúsculo fica de fora de propósito. Ele é a confusão de OCR que a
# amostra documenta (`240073O`), e lê-lo como ordinal troca o erro barato pelo
# caro: se a citação for do art. 50 da CF, fora da cobertura, o ordinal a
# resolveria para o art. 5º — `inventada` → `real`.
_ORDINAL = re.compile(rf"^([1-9])\s*[ºo°ª](?![\d{''.join(sorted(set(OCR_PARA_DIGITO)))}])")


def _numero_de_artigo(valor: str | None) -> int | None:
    if valor and (ordinal := _ORDINAL.match(valor)):
        return int(ordinal.group(1))
    return _inteiro(valor)


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
    artigo = _numero_de_artigo(dados.get("artigo"))
    diploma = dados.get("diploma")
    codigo = _codigo_do_diploma(diploma)

    if artigo is None or not diploma:
        # Sem artigo ou sem diploma nomeado não dá para formular a consulta.
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]
    if codigo is None:
        # O diploma está nomeado, só não pertence à cobertura — e a cobertura é
        # congelada, então isso é `inventada`, não falta de informação. Era o
        # caso de "art. 173 da Lei nº 9.504/1997": a citação é específica o
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
