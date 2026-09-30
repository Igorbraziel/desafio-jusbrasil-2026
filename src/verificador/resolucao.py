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
from .classe import afinidade, marcas
from .deteccao import Achado, sigla_do_tribunal
from .normalizacao import (
    CONFUSOES_DE_LETRA,
    OCR_PARA_DIGITO,
    _corrigir_ocr,
    chave_textual,
    digitos_do_identificador,
)

# Confiança por caminho de decisão, **medida** por
# ``scripts/medir_confianca.py`` (`make confianca`): acurácia do caminho sobre o
# corpus limpo mais as sementes de perturbação, contando só os pares casados com
# o gabarito — como o Brier oficial.
#
# Medir importa porque o bônus da métrica é ``b = 0,10·(1 − Brier)`` e o Brier é
# minimizado exatamente em ``p = acurácia``. Emitir 0,83 num caminho que acerta
# 0,98 joga bônus fora; emitir 0,99 num que acerta 0,67 é pior, porque a punição
# é quadrática.
#
# **Recalibrado no checkpoint 07**, porque as correções daquela etapa mudaram a
# acurácia dos caminhos. O maior salto foi `inventada_processo`: de 158/190 para
# 416/421 — era o caminho em que o número mal lido de uma `real` caía, e o
# reparo de OCR fechou quase todos. Os números abaixo juntam as duas taxas do
# arnês (0,15 com 5 sementes e 0,30 com 3), para não calibrar só no ponto de
# operação.
#
# Três regras, aplicadas a todos os caminhos:
#
# * **Laplace** — ``(acertos + 1) / (total + 2)`` —, arredondado para baixo, para
#   que um caminho com pouca evidência não reivindique 1,0.
# * **Teto de 0,99.** O arnês só mede o ruído que sabemos gerar; o conjunto cego
#   tem formas que ele não tem. O teto custa quase nada se a acurácia for 1,0 e
#   limita a punição quadrática se não for.
# * **A medição conta o que a métrica conta.** O Brier oficial só vê pares
#   casados; até o checkpoint 07 a predição sem par entrava aqui como erro, o que
#   puxava a acurácia para baixo de um valor que o bônus não vê.
#
# **Recalibrado na revisão de 24/09**, com as mesmas três regras, contando só
# pares casados (como o Brier oficial) e com o arnês de dez classes, que inclui
# as três novas de ruído de OCR. Os números abaixo são a soma de `make confianca`
# nas duas taxas (0,15 com 5 sementes e 0,30 com 3; cada execução inclui o corpus
# limpo), reproduzíveis pelo script do repositório. `inventada_processo` é o
# caminho que mais erra: as classes novas geram número de `real` corrompido que
# o reparo ainda não desfaz, e é nele que esse número cai.
#
# O desempate tem dois caminhos desde a mesma revisão. Com margem de classe
# (`real_desempate_classe`), a escolha é uma leitura do prefixo da citação
# contra o cabeçalho de cada candidato. Sem margem (`real_desempate`), sobram
# duplicatas exatas e classes que não distinguem, e a escolha é uma moeda: com
# dois candidatos, 0,5 é o valor que minimiza o Brier de um chute honesto.
#
# **Recalibrado em 30/09** com uma fonte de evidência a mais: o simulador do
# sigiloso (`scripts/simular_sigiloso.py`), que troca as citações do dev por
# outras da base — 3.840 por rodada, 20 sementes, limpo e com o arnês a 0,05 e
# 0,15 no nível 2. Os números abaixo somam o arnês nas duas taxas e o simulador
# nas três. Com essa evidência, o teto de 0,99 deixa de fazer sentido para os
# caminhos sem **nenhum** erro em nenhum instrumento: acima de alguns milhares de
# acertos, o próprio Laplace passa de 0,999. O teto vira 0,999, e o Laplace é
# arredondado para baixo em três casas em vez de duas. `inventada_tema` fica um
# milésimo abaixo de `inventada_processo` para que `medir_confianca.py` continue
# distinguindo os dois caminhos, que o script separa pelo valor.
CONFIANCA = {
    "real_unico": 0.999,  # 6.643/6.643 (junto com real_tabela)
    "real_desempate_classe": 0.916,  # 10/10, Laplace; o simulador não gera empate
    "real_desempate": 0.50,  # moeda entre cópias — ver acima
    "real_tabela": 0.999,  # 6.643/6.643 (junto com real_unico)
    "inventada_processo": 0.985,  # 2.936/2.978
    "inventada_tabela": 0.998,  # 1.460/1.461
    "inventada_tema": 0.984,  # 66/66, Laplace; a cobertura não tem tema
    "incompleta_vaga": 0.999,  # 2.239/2.239
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
#
# `cppm` é a sigla do CPPM e precisa vencer `cpp`, que a contém. `crfb` e `ncpc`
# são as siglas correntes da CF/88 e do CPC vigente. A Lei Complementar casa pelo
# marcador `lc` solto, e não mais pelo literal "lc 64": com a marca de número no
# meio ("LC nº 64/90") o literal não casava e a citação `real` virava `inventada`.
# O número e o ano continuam conferidos em `_diploma_confere`.
DIPLOMAS: tuple[tuple[tuple[str, ...], tuple[str, ...], str], ...] = (
    (("processo penal militar", "cppm"), (), "CPPM_FORA"),
    (("processo civil", "13.105", "13105", "cpc", "ncpc"), (), "CPC"),
    (("processo penal", "3.689", "3689", "cpp"), ("militar",), "CPP"),
    (("penal militar", "1.001", "1001", "cpm"), (), "CPM"),
    (("defesa do consumidor", "codigo do consumidor", "8.078", "8078", "cdc"), (), "CDC"),
    (("consolidacao das leis", "clt", "5.452", "5452"), (), "CLT"),
    (
        (
            "constituic",
            "carta magna",
            "lei maior",
            "carta politica",
            "carta da republica",
            "cf",
            "crfb",
        ),
        (),
        "CF",
    ),
    (("lei complementar", "lc", "64/1990"), (), "LC64"),
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
#
# "Cidadã" é o apelido corrente da CF/88 ("Constituição Cidadã").
_QUALIFICADORES_DA_CF = ("federal", "republica", "federativa", "brasileira", "brasil", "cidada")
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
    if re.fullmatch(r"(?:cf|crfb)(?:\s*/\s*\d{2,4})?", chave):
        return True
    # A sigla e os apelidos saem como o nome: "cf de 1988" sobrava como "cf", e
    # "lei maior de 1969" como "lei maior", palavras que não são qualificador.
    # O que vier depois deles passa pela mesma regra do nome por extenso — o
    # apelido sozinho não bastava, e "Carta da República Portuguesa" virava a CF.
    resto = re.sub(
        r"^(?:constitui\w*|cf|carta magna|lei maior|carta politica|carta da republica)\b",
        "",
        chave,
    )
    resto = _ANO_DE_VERSAO.sub(" ", resto)  # o ano já foi conferido
    palavras = [p for p in resto.split() if p not in _CONECTORES]
    # **Toda** palavra precisa ser qualificador da CF/88 — "República Federativa
    # do Brasil" é o nome oficial por extenso. Uma só que não seja, e é outro
    # diploma.
    return all(
        any(_distancia(p, q) <= (2 if len(q) >= 7 else 1) for q in _QUALIFICADORES_DA_CF)
        for p in palavras
    )


# As palavras que nomeiam os diplomas da cobertura e os que precisam ser
# recusados. É contra este vocabulário que o ruído de letra é desfeito: uma
# palavra do nome que não está aqui mas fica a uma confusão de OCR de uma que
# está é lida como ela. `militar` e `estadual` estão aqui de propósito — sem
# eles, `Mllitar` não voltaria a ser `militar` e o CPPM passaria por CPP, que é
# o erro grave.
#
# Os conectores entram porque também sofrem o ruído ("Defesa d0 Consumidor",
# "Consolidação da5 Leis"), e os marcadores de `DIPLOMAS` os têm por extenso: o
# dispositivo `real` era achado e saía `inventada`.
_VOCABULARIO_DE_DIPLOMA = frozenset(
    """
    codigo processo civil penal militar defesa consumidor consolidacao leis
    trabalho constituicao federal republica federativa brasil brasileira
    estadual estado eleitoral lei complementar decreto carta magna
    de do da das dos
    """.split()
)

# O inverso de `CONFUSOES_DE_LETRA`: cada forma corrompida e as letras que ela
# pode ter substituído. `c` pode ser `e` corrompido e `e` pode ser `c`.
#
# Entram também as trocas de letra por dígito (`Con5tituição`, `Civi1`,
# `Códig0`): a detecção passou a atravessá-las nas palavras-chave, e sem o
# inverso aqui a citação `real` era achada e saía `inventada`. A chave já vem em
# minúsculas, então cada dígito desfaz para a letra minúscula que ele imita.
_DESFAZER = (
    [(corrompida, original) for original, corrompida in CONFUSOES_DE_LETRA.items()]
    + [("ri", "n"), ("ii", "u"), ("rn", "m")]
    + [(digito, letra.lower()) for letra, digito in OCR_PARA_DIGITO.items()]
)


def _variantes(palavra: str) -> set[str]:
    """Todas as palavras a uma confusão de letra de distância, desfeita."""
    saida = set()
    for corrompida, original in _DESFAZER:
        inicio = palavra.find(corrompida)
        while inicio != -1:
            saida.add(palavra[:inicio] + original + palavra[inicio + len(corrompida) :])
            inicio = palavra.find(corrompida, inicio + 1)
    return saida


def _desfazer_ruido_de_letra(chave: str) -> str:
    """Devolve a chave com o ruído de letra do nível 2 desfeito no nome do diploma.

    A detecção já atravessa `Códlgo` e `Mllitar`, mas os marcadores de
    `DIPLOMAS` são literais: `penal militar` não está em `penal mllitar`, e a
    citação `real` virava `inventada`. Era todo o `real` → `inventada` que
    sobrava em `ocr_palavra`.

    Só a palavra **fora** do vocabulário é corrigida, e só para uma palavra
    **dentro** dele — nunca para qualquer coisa. Isso mantém o casamento fechado.
    """
    palavras = []
    for palavra in chave.split():
        if palavra not in _VOCABULARIO_DE_DIPLOMA:
            # Até duas confusões na mesma palavra: `Fcdcral` tem duas (`e`→`c`
            # duas vezes). O vocabulário é pequeno e fechado, então a segunda
            # rodada não abre casamento novo — só alcança o que já estava perto.
            vizinhas = _variantes(palavra)
            candidatas = vizinhas & _VOCABULARIO_DE_DIPLOMA
            if not candidatas:
                segundas = {v2 for v in vizinhas for v2 in _variantes(v)}
                candidatas = segundas & _VOCABULARIO_DE_DIPLOMA
            if len(candidatas) == 1:
                palavra = candidatas.pop()
        palavras.append(palavra)
    return " ".join(palavras)


def _contem_marcador(chave: str, marcador: str) -> bool:
    """O marcador aparece na chave como palavra, e não dentro de outra?

    Marcadores curtos casavam por substring: `cdc` dentro de `fcdcral` fazia a
    Constituição Federal corrompida resolver para o Código de Defesa do
    Consumidor. Os longos ("processo civil") continuam por contenção, porque o
    nome inteiro já é específico.
    """
    if len(marcador) > 4:
        return marcador in chave
    return re.search(rf"(?<![a-z0-9]){re.escape(marcador)}(?![a-z0-9])", chave) is not None


_LEI_DE_OUTRO_ENTE = re.compile(r"\blei\s+(?:complementar\s+)?(?:estadual|municipal|distrital)\b")


def _chave_do_diploma(diploma: str) -> str:
    """O nome do diploma com o ruído de letra desfeito e o número reparado.

    Os dois reparos precisam de lados diferentes do texto. O nome é desfeito
    palavra a palavra contra o vocabulário fechado, e antes do reparo do número:
    numa palavra com um dígito perdido ("Mi1itar") o reparo alastra, `m111tar`
    já não volta a `militar`, e o CPPM passava por CPP. O número da lei é
    reparado sobre o texto **original**, com a caixa preservada: a tabela de OCR
    distingue `G`→6 de `g`→9 e `B`→8 de `b`→6, e reparar depois de passar para
    minúsculas lia "Lei Complementar nº G4/1990" como a lei 94 e "LC nº B4/1990"
    (a lei 84) como a LC 64.
    """
    nomes = _desfazer_ruido_de_letra(chave_textual(diploma)).split()
    numeros = chave_textual(_corrigir_ocr(diploma)).split()
    if len(nomes) != len(numeros):
        return " ".join(numeros)

    def e_numero(palavra: str) -> bool:
        # Número da lei tem mais dígito que letra ("g4/1990", "b.078/1990");
        # palavra do nome com um dígito perdido ("con5tituicao") tem o contrário.
        return sum(c.isdigit() for c in palavra) > sum(c.isalpha() for c in palavra)

    return " ".join(
        numero if e_numero(numero) else nome for nome, numero in zip(nomes, numeros, strict=True)
    )


def _codigo_do_diploma(diploma: str | None) -> str | None:
    """Reduz o nome citado do diploma à chave da tabela curada.

    Devolve ``None`` quando o diploma está nomeado mas fora da cobertura — o que
    o chamador traduz em `inventada`, não em falta de informação.
    """
    if not diploma:
        return None
    chave = _chave_do_diploma(diploma)
    # Lei de outro ente federativo com o número de uma lei federal da cobertura
    # ("Lei Estadual nº 10.406/2002") é outro diploma: conferir só o número a
    # resolvia para o Código Civil — `inventada` → `real`.
    if _LEI_DE_OUTRO_ENTE.search(chave):
        return None
    for marcadores, exclusoes, codigo in DIPLOMAS:
        if not any(_contem_marcador(chave, marcador) for marcador in marcadores):
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


# Artigo com sufixo de letra (`896-A`, `373-A`) é outro artigo, acrescentado
# depois ao código. Nenhum dos 13 da cobertura tem sufixo, e descartar a letra
# fazia o `896-A` resolver para o art. 896 — `inventada` → `real`.
_SUFIXO_DE_ARTIGO = re.compile(r"\d\s*[-‐]\s*[A-Za-z]\s*$")

# Número que nenhum artigo tem: devolvido para o artigo com sufixo, ele passa
# pela consulta à tabela curada e sai `inventada`, que é a resposta certa.
ARTIGO_FORA_DA_COBERTURA = -1


def _numero_de_artigo(valor: str | None) -> int | None:
    if valor and _SUFIXO_DE_ARTIGO.search(valor):
        return ARTIGO_FORA_DA_COBERTURA
    if valor and (ordinal := _ORDINAL.match(valor)):
        return int(ordinal.group(1))
    return _inteiro(valor)


def _tribunal_da_sumula(dados: dict[str, str]) -> str | None:
    """A sigla do tribunal, venha ela como sigla ou pelo nome por extenso.

    A detecção tem um grupo por forma — `_SUMULA` não pode repetir o nome do
    grupo —, e o extenso já chega com a sigla no nome do grupo (`ext_STJ`).
    """
    for grupo in ("tribunal", "tribunal_par", "tribunal_do"):
        if dados.get(grupo):
            return sigla_do_tribunal(dados[grupo])
    for grupo in dados:
        if grupo.startswith("ext_"):
            return grupo.removeprefix("ext_")
    return None


def _resolver_sumula(dados: dict[str, str], base: BaseCanonica) -> tuple[str, int | None, float]:
    numero = _inteiro(dados.get("numero"))
    if numero is None:
        return "incompleta", None, CONFIANCA["incompleta_sem_numero"]
    vinculante = bool(dados.get("vinculante") or dados.get("sv"))
    tribunal = _tribunal_da_sumula(dados)
    if dados.get("enunciado") and tribunal != "TST":
        # "Enunciado" é como o TST chama as próprias súmulas; de outro tribunal,
        # ou sem tribunal, não identifica súmula da cobertura.
        return "inventada", None, CONFIANCA["inventada_tabela"]
    id_canonico = base.sumula(tribunal, vinculante, numero)
    if id_canonico is None:
        return "inventada", None, CONFIANCA["inventada_tabela"]
    return "real", id_canonico, CONFIANCA["real_tabela"]


def _resolver_dispositivo(
    dados: dict[str, str], base: BaseCanonica
) -> tuple[str, int | None, float]:
    artigo = _numero_de_artigo(dados.get("artigo"))
    diploma = dados.get("diploma") or dados.get("diploma_sigla")
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

    # Empate. Dois acórdãos distintos com o mesmo número próprio são incidentes
    # do mesmo processo — o recurso e o agravo interno nele, o recurso e os
    # embargos de declaração —, e o que os separa é a classe, que a citação traz
    # no prefixo. Ganha o candidato cuja classe mais concorda com a da citação
    # (ver `classe.afinidade`); só com margem sobre o segundo o desempate é
    # uma leitura, e não um chute.
    #
    # Sem margem — duplicata exata, ou classe que não distingue —, fica o
    # primeiro da ordem estável de `candidatos_por_numero`, que é arbitrária
    # (ADR 0003). O que continua valendo é a aritmética: chutar domina desistir.
    # Link errado num par `real`×`real` custa só `fp[real]`; rebaixar para
    # `incompleta` custaria o `fn[real]` **e** o `fp[incompleta]`.
    da_citacao = marcas(achado.trecho)
    pontos = [afinidade(da_citacao, c.classe) for c in candidatos]
    melhor = max(range(len(candidatos)), key=lambda i: pontos[i])
    segundo = max(p for i, p in enumerate(pontos) if i != melhor)
    if pontos[melhor] > segundo:
        return "real", candidatos[melhor].id_canonico, CONFIANCA["real_desempate_classe"]
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
