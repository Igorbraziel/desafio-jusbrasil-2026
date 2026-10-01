"""Detecção dos spans de citação no texto do parecer.

O alinhamento com o gabarito é por sobreposição (IoU ≥ 0,5): a borda não precisa
ser exata, mas a citação inteira precisa aparecer. A família determina contra o
quê a citação é resolvida:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.234.567/PR``)
``sumula``       ``Súmula <n> do <tribunal>``, ``Súmula Vinculante <n>``
``tema``         ``Tema <n> da repercussão geral``
``dispositivo``  ``art. <n>, <inciso>, do <código>``
``vaga``         sem identificador suficiente para consultar a base

A âncora de ``processo`` é o número, não a sigla: as classes processuais não são
enumeráveis, e numa classe não vista o span fica curto mas o número que resolve
continua capturado. A ``vaga`` procura menção a relator sem número de processo
(tribunal + ano + relator). A detecção só começa em
:func:`verificador.texto.fim_do_cabecalho`, para não extrair os números do
cabeçalho (autos, protocolo, OAB, folhas), que seriam falsos positivos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..normalizacao import (
    CONFUSOES_DE_LETRA,
    OCR_PARA_DIGITO,
    UFS,
    _corrigir_ocr,
    chave_textual,
    sem_acento,
)
from ..texto import fim_do_cabecalho

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

FAMILIAS = ("processo", "sumula", "tema", "dispositivo", "vaga")

# Abaixo disso não há número de processo — só ano, inciso e página.
_MINIMO_DIGITOS = 4

# "nº" em todas as grafias, inclusive as de OCR (No, N°, n.).
_NUMERO = r"(?:n\s*[.ºo°]{0,2}|N\s*[.ºO°]{0,2})"

# Pontuação dentro de um número de processo, incluindo \xa0 e no máximo uma quebra
# de linha: duas quebras são fim de parágrafo, e o span engoliria o título seguinte.
_DENTRO = r"(?:[ \t\xa0.\-–—/]|\n(?![ \t]*\n))"

# Dígito ou letra que o OCR põe no lugar de um dígito. Derivada de
# `OCR_PARA_DIGITO` para que a detecção nunca divirja do reparo.
_DIGITOIDE = rf"[\d{re.escape(''.join(sorted(set(OCR_PARA_DIGITO))))}]"


def _tolerante(palavra: str) -> str:
    """Expressão que casa a palavra-chave com o ruído de OCR de uma letra.

    Cada letra aceita a própria forma, a forma sem acento, a confusão de
    `CONFUSOES_DE_LETRA` e o dígito de `OCR_PARA_DIGITO` (`Súrnula`, `Súmu1a`). Vale
    só para palavras-chave fixas, nunca para classes abertas, o que limita os falsos
    positivos.
    """
    partes = []
    for letra in palavra:
        base = sem_acento(letra)
        opcoes = {letra, base}
        confusao = CONFUSOES_DE_LETRA.get(base.lower())
        if confusao:
            opcoes.add(confusao)
        digito = OCR_PARA_DIGITO.get(base) or OCR_PARA_DIGITO.get(base.lower())
        if digito:
            opcoes.add(digito)
        simples = sorted(o for o in opcoes if len(o) == 1)
        classe = re.escape(simples[0]) if len(simples) == 1 else f"[{''.join(simples)}]"
        compostas = sorted(o for o in opcoes if len(o) > 1)
        partes.append(f"(?:{classe}|{'|'.join(compostas)})" if compostas else classe)
    return "".join(partes)


# Núcleo numérico, digitoide em todas as posições, inclusive a primeira: com `\d`
# no início, `REsp l.234.567` virava `234567`, um número diferente e
# silenciosamente errado. Palavras que casam por acaso (`Gols`) morrem em
# `_MINIMO_DIGITOS`; os lookarounds impedem começar ou terminar dentro de uma
# palavra (o `s` de "2024 sem" entraria no número).
_NUCLEO = rf"(?<![A-Za-zÀ-ÿ]){_DIGITOIDE}(?:{_DENTRO}*{_DIGITOIDE}){{3,}}(?![A-Za-zÀ-ÿ])"

# Sufixo de UF: /RJ, - PR, (SC), – MA. Conjunto fechado, e não `[A-Z]{2}`, para
# não anexar bigramas como o `- DE` de "- DE acordo".
_UF = re.compile(rf"\s*[/(\-–—]\s*(?:{'|'.join(sorted(UFS))})\s*\)?")

_NUMERO_PROCESSO = re.compile(_NUCLEO)

# Advérbios e conectores de prosa que, capitalizados, casariam o ramo de sigla e
# adiantariam o início do span ("Também na Rcl …"). É lista de exclusão de
# vocabulário fechado do português, para não enumerar siglas processuais.
_PALAVRA_DE_PROSA = frozenset(
    """
    tambem também ademais igualmente outrossim ainda assim ja já entao então
    porem porém contudo todavia entretanto alias aliás inclusive ali aqui
    confira confiram veja vejam vejase veja-se vide cita cita-se citese citamos
    conforme segundo consoante nesse neste nessa nesta naquele naquela
    destarte portanto logo pois tal tais este esta esse essa aquele aquela
    """.split()
)

# Um elo da cadeia de prefixo (fullmatch por token): sigla com inicial maiúscula,
# marca de número ou conector minúsculo conhecido. Restringir as minúsculas impede
# o prefixo de engolir a prosa; o ponto dentro da sigla cobre `H.C.` e `AG.REG`.
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

    Toda palavra capitalizada tem forma de sigla; o léxico de prosa filtra o resto.
    """
    if not token or _ELO.fullmatch(token) is None:
        return False
    return chave_textual(token.strip(".,;:")) not in _PALAVRA_DE_PROSA


# Órgão julgador e autoridade antes da citação ("do Superior Tribunal de Justiça
# Rcl …"): param a cadeia de prefixo para o span não perder o IoU. Só substantivos:
# "Federal" fica de fora porque também aparece em nome de classe. A sigla de
# tribunal só para a cadeia quando nua ("STF"), não colada à classe ("TST-RR").
_PALAVRA_INSTITUCIONAL = frozenset(
    """
    tribunal tribunais supremo superior justica ministro ministra min
    relator relatora rel desembargador desembargadora juiz juiza turma corte
    plenario pleno secao camara orgao egregio colendo
    """.split()
) | frozenset(t.lower() for t in TRIBUNAIS)

# Núcleos de classe por extenso: não detectam, só impedem que o nome da classe seja
# descartado com o do órgão ("Relator Gilmar Mendes Reclamação nº 1").
_NUCLEO_DE_CLASSE = frozenset(
    """
    recurso agravo embargos reclamacao habeas mandado acao apelacao peticao
    inquerito conflito suspensao extradicao revisao representacao consulta
    """.split()
)


# Preposição contraída com artigo: é o que abre a segunda de duas citações
# coordenadas, e nunca aparece depois do "e" dentro de um nome de classe.
_CONTRACAO = frozenset({"da", "do", "das", "dos", "na", "no", "nas", "nos"})

# Os conectores minúsculos de `_ELO`, que não podem abrir o span.
_CONECTOR_DE_BORDA = re.compile(r"n[oa]s?|d[oae]s?|em|e")


def _e_institucional(token: str) -> bool:
    return chave_textual(token.strip(".,;:()")) in _PALAVRA_INSTITUCIONAL


def _e_palavra_de_nome(token: str) -> bool:
    """Palavra por extenso com inicial maiúscula, sem nenhuma marca de sigla.

    Sigla tem ponto, hífen, dígito ou mais de uma maiúscula (`AG.REG`, `REsp`,
    `TST-RR`); as de três letras (`Rcl`, `Pet`) ficam de fora pelo tamanho.
    """
    limpo = token.strip(",;:()")
    return (
        len(limpo) >= 4
        and limpo[:1].isupper()
        and limpo[1:].isalpha()
        and limpo[1:].islower()
        and chave_textual(limpo) not in _NUCLEO_DE_CLASSE
    )


# Comporta prefixos como "Embargos de Declaração no Agravo Interno no Agravo em
# Recurso Especial nº" (11 palavras).
_MAXIMO_ELOS = 12

# Digitoide, como o núcleo de `processo`.
_NUMERO_DE_SUMULA = rf"{_DIGITOIDE}+"

# Sigla dos tribunais superiores, aceitando o `S` lido como `5` ("5TJ", "T5T");
# `sigla_do_tribunal` devolve a forma limpa.
_SIGLA_DE_TRIBUNAL = (
    r"(?:(?-i:[S5]TF|[S5]TJ|T[S5]T|T[S5]E|[S5]TM)|STF|STJ|TST|TSE|STM)(?![A-Za-zÀ-ÿ\d])"
)

# O conector curto antes do tribunal ou do diploma, com o ruído do nível 2:
# "d0", "dc", "dã" no lugar de "do", "de", "da".
_CONECTOR = r"d[oaeã0c]s?"

# As palavras do nome do tribunal atravessam uma quebra de linha: o texto vem
# quebrado em colunas, e sem isso a súmula perdia o tribunal.
_ENTRE_PALAVRAS_DO_NOME = r"(?:[ \t\xa0]+\n?[ \t\xa0]*|\n[ \t\xa0]*)"
_TRIBUNAL_POR_EXTENSO = "|".join(
    rf"(?P<ext_{sigla}>{_ENTRE_PALAVRAS_DO_NOME.join(_tolerante(p) for p in nome.split())})"
    for sigla, nome in (
        ("STF", "Supremo Tribunal Federal"),
        ("STJ", "Superior Tribunal de Justiça"),
        ("TST", "Tribunal Superior do Trabalho"),
        ("TSE", "Tribunal Superior Eleitoral"),
        ("STM", "Superior Tribunal Militar"),
    )
)

# Separador de nomes longos (diploma, tribunal regional). A quebra é um grupo à
# parte para evitar backtracking quadrático em trechos longos de espaços.
_NAME_SEPARATOR = r"(?:[ \t\xa0]+(?:\n[ \t\xa0]*)?|\n[ \t\xa0]*)"


def _tolerant_name(nome: str) -> str:
    """As palavras de um nome longo com o ruído de OCR, como as âncoras.

    Os conectores (de/da/do…) aceitam ruído e troca entre si, e o plural com `s`
    lido como `5`.
    """
    return _NAME_SEPARATOR.join(
        r"d[aeoc0ã][s5]?" if palavra in ("de", "da", "do", "das", "dos") else _tolerante(palavra)
        for palavra in nome.split()
    )


# Tribunal da súmula fora dos superiores: TRF1-6, TRT1-24, TJ/TRE/TJM com UF e TNU.
# Fica só na súmula, porque `_SIGLA_DE_TRIBUNAL` também ancora `tema` e `vaga`. A
# sigla exige maiúscula (em caixa baixa seria prosa) e não aceita espaço solto
# antes da UF ("TJ SE APLICA" não é Sergipe). Região inexistente ("TRF9") é aceita
# de propósito: não resolve e sai `inventada`, com o span inteiro.
_UFS_DA_SIGLA = ("DFT", *sorted(UFS))
_UNIDADES_DA_REGIAO = (
    "Primeira", "Segunda", "Terceira", "Quarta", "Quinta", "Sexta", "Sétima", "Oitava", "Nona",
)  # fmt: skip
_UNIDADE_DA_REGIAO = "|".join(_tolerante(u) for u in _UNIDADES_DA_REGIAO)
_ORDINAL_DA_REGIAO = (
    rf"(?:(?:{_tolerante('Décima')}|{_tolerante('Vigésima')})"
    rf"(?:{_NAME_SEPARATOR}(?:{_UNIDADE_DA_REGIAO}))?|{_UNIDADE_DA_REGIAO})"
)
_NUMERO_DA_REGIAO = r"\d{1,2}(?!\d)[ªºa°^]?"
_DA_REGIAO = (
    rf"d[aã]{_NAME_SEPARATOR}(?:{_NUMERO_DA_REGIAO}|{_ORDINAL_DA_REGIAO})"
    rf"{_NAME_SEPARATOR}{_tolerante('Região')}"
)
# Nada, espaço, ou sinal com espaço opcional: um caminho só por forma, para evitar
# backtracking quadrático.
_SEPARADOR_DA_SIGLA = r"(?:[ \t]*[-–/][ \t]*|[ \t]+)?"
_REGIONAL_DA_SUMULA = (
    r"(?:(?-i:TR[FT])"
    rf"(?:{_SEPARADOR_DA_SIGLA}{_NUMERO_DA_REGIAO}(?:{_NAME_SEPARATOR}{_tolerante('Região')})?"
    rf"|{_NAME_SEPARATOR}{_DA_REGIAO})?"
    rf"|(?-i:TJM|TRE|TJ)(?:[ \t]*[-–/][ \t]*)?"
    rf"(?-i:{'|'.join(_tolerante(uf) for uf in _UFS_DA_SIGLA)})"
    r"|(?-i:TJM|TRE|TJ|TNU)"
    r")(?![A-Za-zÀ-ÿ\d])"
)

# Regional pelo nome por extenso, só quando o estado ou a região o identificam
# ("Súmula <n> do Tribunal Regional" fica de fora). Do nome mais longo para o mais
# curto, para "Mato Grosso do Sul" não casar como "Mato Grosso".
_ESTADOS_POR_EXTENSO = {
    "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM", "Bahia": "BA",
    "Ceará": "CE", "Distrito Federal e dos Territórios": "DFT", "Distrito Federal": "DF",
    "Espírito Santo": "ES", "Goiás": "GO", "Maranhão": "MA", "Mato Grosso do Sul": "MS",
    "Mato Grosso": "MT", "Minas Gerais": "MG", "Pará": "PA", "Paraíba": "PB",
    "Paraná": "PR", "Pernambuco": "PE", "Piauí": "PI", "Rio de Janeiro": "RJ",
    "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS", "Rondônia": "RO",
    "Roraima": "RR", "Santa Catarina": "SC", "São Paulo": "SP", "Sergipe": "SE",
    "Tocantins": "TO",
}  # fmt: skip
_ESTADOS_EM_ORDEM = sorted(_ESTADOS_POR_EXTENSO, key=len, reverse=True)
_DO_ESTADO = (
    rf"d[aeoc0ã]{_NAME_SEPARATOR}"
    rf"(?:{_tolerante('Estado')}{_NAME_SEPARATOR}d[aeoc0ã]{_NAME_SEPARATOR})?"
    rf"(?:{'|'.join(_tolerant_name(e) for e in _ESTADOS_EM_ORDEM)})"
)
# (sigla, nome, o que vem depois do nome e identifica o tribunal)
_REGIONAIS_POR_EXTENSO = (
    ("TRF", "Tribunal Regional Federal", f"{_NAME_SEPARATOR}{_DA_REGIAO}"),
    ("TRT", "Tribunal Regional do Trabalho", f"{_NAME_SEPARATOR}{_DA_REGIAO}"),
    ("TRE", "Tribunal Regional Eleitoral", f"{_NAME_SEPARATOR}{_DO_ESTADO}"),
    ("TJM", "Tribunal de Justiça Militar", f"{_NAME_SEPARATOR}{_DO_ESTADO}"),
    ("TJ", "Tribunal de Justiça", f"{_NAME_SEPARATOR}{_DO_ESTADO}"),
    (
        "TNU",
        "Turma Nacional de Uniformização",
        f"(?:{_NAME_SEPARATOR}{_tolerant_name('dos Juizados Especiais Federais')})?",
    ),
)
_REGIONAL_POR_EXTENSO = (
    "(?:"
    + "|".join(_tolerant_name(nome) + resto for _, nome, resto in _REGIONAIS_POR_EXTENSO)
    + r")(?![\wÀ-ú])"
)
_SIGLA_DE_TRIBUNAL_DA_SUMULA = (
    rf"(?:{_SIGLA_DE_TRIBUNAL}|{_REGIONAL_DA_SUMULA}|{_REGIONAL_POR_EXTENSO})"
)

# As peças que `sigla_do_tribunal` lê para escrever a sigla do regional.
_REGIONAL_NAMES = tuple(
    (sigla, re.compile(_tolerant_name(nome), re.IGNORECASE))
    for sigla, nome, _ in _REGIONAIS_POR_EXTENSO
)
_STATE_NAMES = tuple(
    (
        _ESTADOS_POR_EXTENSO[nome],
        re.compile(rf"(?<![\wÀ-ú]){_tolerant_name(nome)}(?![\wÀ-ú])", re.IGNORECASE),
    )
    for nome in _ESTADOS_EM_ORDEM
)
_STATE_ACRONYMS = tuple((uf, re.compile(_tolerante(uf))) for uf in _UFS_DA_SIGLA)
_TENS_OF_REGION = (
    (10, re.compile(_tolerante("Décima"), re.IGNORECASE)),
    (20, re.compile(_tolerante("Vigésima"), re.IGNORECASE)),
)
_UNITS_OF_REGION = tuple(
    (valor, re.compile(rf"(?<![\wÀ-ú]){_tolerante(nome)}(?![\wÀ-ú])", re.IGNORECASE))
    for valor, nome in enumerate(_UNIDADES_DA_REGIAO, start=1)
)


def _region_number(texto: str) -> int | None:
    """A região, escrita com algarismo ("1ª", "15a") ou por extenso ("Quarta")."""
    algarismo = re.search(r"\d{1,2}", texto)
    if algarismo:
        return int(algarismo.group())
    dezena = next((valor for valor, expr in _TENS_OF_REGION if expr.search(texto)), 0)
    unidade = next((valor for valor, expr in _UNITS_OF_REGION if expr.search(texto)), 0)
    return (dezena + unidade) or None


def sigla_do_tribunal(texto: str) -> str:
    """A sigla do tribunal sem ruído de OCR nem separador: `5TJ` → `STJ`.

    O regional sai numa forma só (`TRF1`, `TJSP`, `TNU`), e nele o `5` da região não
    vira `S` ("TRT-5").
    """
    for sigla, nome in _REGIONAL_NAMES:
        inicio = nome.match(texto)
        if inicio is None:
            continue
        resto = texto[inicio.end() :]
        if sigla in ("TRF", "TRT"):
            return f"{sigla}{_region_number(resto) or ''}"
        return sigla + next((uf for uf, estado in _STATE_NAMES if estado.search(resto)), "")
    if texto[:3] in ("TRF", "TRT"):
        return f"{texto[:3]}{_region_number(texto[3:]) or ''}"
    # "TJMG" é o TJ de Minas, e "TJMSP" o TJM de São Paulo: a sigla mais longa só
    # fica se o que sobra depois dela for uma UF.
    for prefixo in ("TJM", "TRE", "TJ"):
        if texto.startswith(prefixo):
            resto = re.sub(r"^[ \t]*[-–/]?[ \t]*", "", texto[len(prefixo) :])
            uf = next((uf for uf, expr in _STATE_ACRONYMS if expr.fullmatch(resto)), None)
            if uf:
                return f"{prefixo}{uf}"
    return texto.upper().replace("5", "S")


# Súmula com as grafias correntes: "SV", "Enunciado" (como o TST chama as próprias
# súmulas; marcado para a resolução só aceitá-lo do TST), inciso ou item,
# honorífico ("do C. STJ") e tribunal por barra, parênteses, conector ou nome por
# extenso. Sem o tribunal a súmula não resolve e sai `inventada`.
_HONORIFICO = r"(?:(?:C|E|Col|Colendo|Egr[ée]gio|Eg)\.?\s+)"
_ITEM_DA_SUMULA = r"(?:\s*,\s*(?:item\s+|inciso\s+)?[IVXLC]{1,8}\s*,)"
_SUMULA = re.compile(
    r"\b(?:"
    rf"[S5](?:{_tolerante('úmula')}|[úuû]m\.)\s*(?P<vinculante>{_tolerante('Vinculante')})?"
    r"|(?P<sv>SV)(?=\s*(?:n|N|\d))"
    rf"|(?P<enunciado>{_tolerante('Enunciado')})"
    r")"
    rf"\s*(?:{_NUMERO}\s*)?(?P<numero>{_NUMERO_DE_SUMULA})"
    r"(?:"
    rf"\s*[/\-–]\s*(?P<tribunal>{_SIGLA_DE_TRIBUNAL_DA_SUMULA})"
    rf"|\s*\(\s*(?P<tribunal_par>{_SIGLA_DE_TRIBUNAL_DA_SUMULA})\s*\)"
    rf"|{_ITEM_DA_SUMULA}?\s*,?\s*{_CONECTOR}\s*{_HONORIFICO}?"
    rf"(?:(?P<tribunal_do>{_SIGLA_DE_TRIBUNAL_DA_SUMULA})|{_TRIBUNAL_POR_EXTENSO})"
    r")?",
    re.IGNORECASE,
)

_TEMA = re.compile(
    # Espécie opcional entre a palavra e o número ("Tema Repetitivo <n>") e plural
    # ("Temas"): sem elas o número cairia em `processo` e resolveria errado. Os
    # freios impedem que `temas` case como Tema `s`.
    rf"\b{_tolerante('Tema')}s?\s+"
    rf"(?:(?:d[ae]\s+)?(?:{_tolerante('Repercussão')}\s+{_tolerante('Geral')}"
    rf"|{_tolerante('Repetitivo')}|RG)\s+)?"
    rf"(?:{_NUMERO}\s*)?"
    rf"(?P<numero>{_DIGITOIDE}+(?:\.{_DIGITOIDE}{{3}})*)(?![A-Za-zÀ-ÿ])"
    rf"(?:\s*d[ae]\s*{_tolerante('repercussão')}\s*{_tolerante('geral')})?"
    # O tribunal depois do número faz parte do span, como na súmula.
    rf"(?:\s*(?:[/\-–]|,?\s*{_CONECTOR})\s*{_SIGLA_DE_TRIBUNAL})?",
    re.IGNORECASE,
)

# Diploma legal: código nomeado, Constituição, lei por número ou por nome. Cada
# alternativa é fechada (nada de `[\w\s]{0,40}`), por precisão e desempenho.
#
# O ano de versão faz parte do diploma: códigos revogados (`CPC/73`) têm a mesma
# numeração de artigos dos vigentes, e sem o ano a resolução cairia no vigente. Por
# isso o conector não pode ser a última palavra do nome.
_ANO_DE_VERSAO = r"(?:\s*/\s*\d{2,4}|\s+de\s+(?:19|20)\d{2})?"
# Palavra do nome do código: caixa de título (`(?-i:…)` porque `_DISPOSITIVO` é
# IGNORECASE) ou vocabulário fechado em qualquer caixa. Assim nem a prosa seguinte
# nem as ementas em caixa alta entram no diploma.
_PALAVRA_TITULO = r"(?-i:[A-ZÀ-Ú][a-zà-ú])[\wÀ-ú]*"
_PALAVRA_DE_CODIGO_MINUSCULA = (
    "(?:"
    + "|".join(
        _tolerante(palavra)
        for palavra in """
        processo civil penal militar defesa consumidor eleitoral tributário
        comercial trânsito brasileiro florestal nacional aeronáutico
        """.split()
    )
    + r")(?![\wÀ-ú])"
)
# Conector com ruído de OCR e até quatro palavras no nome: sem isso o "Militar" do
# CPPM ficava de fora e ele resolvia como CPP.
_CONECTOR_DE_NOME = r"d[aeoc0ã]"
_PALAVRA_DO_NOME = (
    rf"(?:\s+(?:{_CONECTOR_DE_NOME}\s+)?(?!{_CONECTOR_DE_NOME}\b)"
    rf"(?:{_PALAVRA_TITULO}|{_PALAVRA_DE_CODIGO_MINUSCULA}))"
)
_NOME_DE_CODIGO = rf"{_tolerante('Código')}{_PALAVRA_DO_NOME}{{0,4}}{_ANO_DE_VERSAO}"

# Diplomas federais citados pelo nome ("Lei de Execução Penal"). Lista fechada,
# para "Lei de regência" não virar citação; a resolução decide o que cada nome é.
#
# Os complementos que mudam a identidade do diploma ("Federais", "da Fazenda
# Pública") entram no span, do mais longo para o mais curto, porque a alternância
# fica com o primeiro que casa.
_STATUTE_NAMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Estatuto da Criança e do Adolescente", ()),
    ("Estatuto do Idoso", ()),
    ("Estatuto da Pessoa Idosa", ()),
    ("Estatuto da Advocacia", ("e da Ordem dos Advogados do Brasil", "e da OAB")),
    ("Estatuto da Ordem dos Advogados do Brasil", ()),
    ("Estatuto da OAB", ()),
    ("Estatuto do Desarmamento", ()),
    ("Estatuto da Pessoa com Deficiência", ()),
    ("Lei de Execução Penal", ()),
    ("Lei de Introdução às Normas do Direito Brasileiro", ()),
    ("Lei de Introdução ao Direito Brasileiro", ()),
    ("Lei de Introdução ao Código Civil", ()),
    ("Lei Maria da Penha", ()),
    ("Lei de Drogas", ()),
    ("Lei Antidrogas", ()),
    ("Lei das Eleições", ()),
    ("Lei de Improbidade", ("Administrativa",)),
    (
        "Lei dos Juizados Especiais",
        ("Cíveis e Criminais", "da Fazenda Pública", "Federais", "Criminais", "Cíveis"),
    ),
    ("Lei da Ação Civil Pública", ()),
    ("Lei do Mandado de Segurança", ()),
    ("Lei de Execução Fiscal", ()),
    ("Lei de Execuções Fiscais", ()),
    ("Lei dos Crimes Hediondos", ()),
    ("Nova Lei de Licitações", ("e Contratos Administrativos", "e Contratos")),
    ("Lei de Licitações", ("e Contratos Administrativos", "e Contratos")),
    ("Lei das Inelegibilidades", ()),
    ("Lei de Inelegibilidade", ()),
    ("Lei da Ficha Limpa", ()),
    ("Lei Orgânica da Magistratura Nacional", ()),
    ("Lei de Responsabilidade Fiscal", ()),
)


def _statute_pattern(nome: str, complementos: tuple[str, ...]) -> str:
    """Expressão de uma entrada de `_STATUTE_NAMES`, tolerante como as âncoras.

    A fronteira final impede o nome de parar no meio de uma palavra.
    """
    expressao = _tolerant_name(nome)
    if complementos:
        opcoes = "|".join(_tolerant_name(c) for c in complementos)
        expressao += f"(?:{_NAME_SEPARATOR}(?:{opcoes}))?"
    return expressao + r"(?![\wÀ-ú])"


# O ano separa versões com a mesma numeração de artigos (a Lei de Licitações
# antiga e a nova).
_NAMED_STATUTE = (
    "(?:"
    + "|".join(_statute_pattern(nome, extra) for nome, extra in _STATUTE_NAMES)
    + f"){_ANO_DE_VERSAO}"
)

# Siglas de diploma, inclusive as fora da cobertura (para a citação existir e sair
# `inventada`) e as abreviações dos diplomas de `_STATUTE_NAMES`. A mais longa vem
# antes da que ela contém (`CPPM` antes de `CPP`).
_DIPLOMA_ACRONYMS = (
    r"(?:CPPM|CPC|CPP|CPM|CLT|CDC|CRFB|NCPC|CTN|CTB|ECA"
    r"|LINDB|LIDB|LICC|LOMAN|LEP|LRF|LEF|CF|CC|CP)"
)
# Número da lei com digitoide; o lookahead impede terminar dentro de uma palavra
# ("Lei Orgânica" não é "Lei O"). A exigência de dígito real fica em `registrar`.
_NUMERO_DE_LEI = (
    # A marca aceita espaço entre o `n` e o símbolo (`n º`).
    rf"(?:\s*[nN]\s?[.ºo°]{{0,2}})?\s*{_DIGITOIDE}(?:[.]?{_DIGITOIDE})*"
    rf"(?:\s*/\s*{_DIGITOIDE}{{2,4}})?(?![A-Za-zÀ-ÿ])"
)

# Qualificadores de constituição em minúscula, os que identificam a CF/88 e os que
# a recusam ("constituição estadual" precisa ser capturada inteira). A palavra que
# faltar aqui apenas fica fora do diploma.
_QUALIFICADOR_MINUSCULO = (
    "(?:"
    + "|".join(
        _tolerante(palavra)
        for palavra in """
        federal república federativa brasileira brasil cidadã estadual estado portuguesa
        espanhola italiana francesa alemã americana estrangeira imperial mineira
        paulista fluminense gaúcha baiana catarinense paranaense pernambucana
        """.split()
    )
    + r")(?![\wÀ-ú])"
)

# "Lei" com ruído de OCR e qualificador antes do número ("Lei Federal nº"); sem
# isso o número sobrava para a família `processo`.
_QUALIFICADOR_DE_LEI = "|".join(
    _tolerante(p) for p in ("Complementar", "Federal", "Estadual", "Municipal", "Ordinária")
)

# Qualificadores da Constituição depois da primeira palavra ("da República
# Portuguesa"). Romanos ficam de fora (título de seção); âncoras de outras famílias,
# palavras institucionais e siglas processuais param a captura.
_NAO_QUALIFICA = (
    r"(?!(?:S[úu]mulas?|Enunciados?|Temas?|Arts?\b|Artigos?|Leis?\b|Decreto|C[óo]digo|"
    r"Rel\b|Relator|Relatora|Ministr[oa]|Min\b|Tribunal|Turma|Corte|Plen[áa]rio|"
    r"REsp|RE\b|ARE\b|AREsp|RHC|HC\b|MS\b|Rcl|ADI|ADPF|AgInt|AgRg|EDcl|RR\b|AI\b)(?![a-zà-ú]))"
)
_QUALIFICADOR_SEGUINTE = (
    r"(?:(?:[ \t\xa0]+d[aeo]s?)?[ \t\xa0]+(?!(?-i:[IVXLC]+)\b)"
    rf"(?-i:{_NAO_QUALIFICA})(?:{_PALAVRA_TITULO}|{_QUALIFICADOR_MINUSCULO})){{0,2}}"
)

_DIPLOMA = (
    r"(?:"
    rf"{_tolerante('Lei')}(?:\s+(?:{_QUALIFICADOR_DE_LEI}))?{_NUMERO_DE_LEI}"
    rf"|{_tolerante('Consolidação')}\s+d[aã0c][s5]\s+{_tolerante('Leis')}\s+{_CONECTOR_DE_NOME}\s+"
    rf"{_tolerante('Trabalho')}"
    rf"|{_NOME_DE_CODIGO}"
    rf"|{_NAMED_STATUTE}"
    # O qualificador da Constituição entra no diploma: é o que separa a Federal (a
    # única na cobertura) da Estadual ou estrangeira. Só entra palavra com forma de
    # qualificador, para o verbo da frase ("… garante") não reprovar a CF. O ano
    # identifica outra constituição; a primeira alternativa evita que o "de" do
    # conector engula o do ano.
    rf"|{_tolerante('Constituição')}(?:\s+de\s+(?:19|20)\d{{2}}"
    rf"|(?:\s+d[aeo]\s+)?(?:\s*(?-i:{_NAO_QUALIFICA})(?:(?-i:[A-ZÀ-Ú])[\wÀ-ú]+|{_QUALIFICADOR_MINUSCULO}))?"
    rf"{_QUALIFICADOR_SEGUINTE}{_ANO_DE_VERSAO})"
    # Apelidos da CF/88, com qualificador e ano como a Constituição ("Lei Maior de
    # 1969" é outra carta).
    r"|(?:Carta\s+Magna|Lei\s+Maior|Carta\s+Pol[íi]tica|Carta\s+da\s+Rep[úu]blica)"
    rf"(?:\s+de\s+(?:19|20)\d{{2}}|(?:\s+d[aeo]s?)?{_QUALIFICADOR_SEGUINTE}{_ANO_DE_VERSAO})"
    # `Decreto-Lei` é como a base nomeia a CLT; `LC` é a sigla de Lei Complementar.
    rf"|{_tolerante('Decreto')}[-‐\s]*{_tolerante('Lei')}{_NUMERO_DE_LEI}"
    rf"|LC{_NUMERO_DE_LEI}"
    # Siglas com ano (`CPC/73`, `CF/88`); a fronteira impede `CPPM` de casar `CPP`.
    rf"|{_DIPLOMA_ACRONYMS}(?![A-Za-zÀ-ÿ])"
    rf"{_ANO_DE_VERSAO}"
    r")"
)

# Incisos, parágrafos e alíneas entre o artigo e o diploma. Cada repetição precisa
# consumir uma vírgula: sem isso o grupo casa o vazio e o backtracking explode. O
# romano vai até oito caracteres (`LXXVIII`).
_ROMANO = r"[IVXLC]{1,8}"
# As palavras fixas toleram o ruído de OCR, como as âncoras.
_INCISO = (
    rf"(?:{_tolerante('inciso')}[s5]?|{_tolerante('inc')}[s5]?\.)\s+{_ROMANO}"
    rf"(?:\s+e\s+{_ROMANO})?"
)
_QUALIFICADORES = (
    rf"(?:\s*,\s*(?:§+\s*{_DIGITOIDE}+[ºo°]?(?:\s*-\s*[A-Z])?(?:\s+e\s+\d+[ºo°]?)?"
    rf"|(?:e\s+)?{_INCISO}"
    rf"|{_tolerante('parágrafo')}\s+(?:{_tolerante('único')}|{_DIGITOIDE}+[ºo°]?)"
    rf"|§\s*{_tolerante('único')}"
    rf"|{_tolerante('alínea')}\s+['\"]?[a-z]['\"]?\)?"
    rf"|{_tolerante('caput')}(?:\s+e\s+{_INCISO})?|{_ROMANO}(?:\s+e\s+{_ROMANO})?"
    r"|['\"]?[a-z]['\"]?\)?))"
    r"{0,5}"
)

# Número do artigo com separador de milhar (`art. 1.134`), digitoide como `_NUCLEO`
# e com no máximo uma quebra de linha depois do ponto. O contrapeso é
# `_tem_digito_real` em `registrar`: sem ele `art Iss` casaria.
_NUMERO_DE_ARTIGO = rf"{_DIGITOIDE}+(?:\.[ \t]*\n?[ \t]*{_DIGITOIDE}{{3}})*(?:[-ºo°][\w]{{0,3}})?"

# "novo"/"atual" antes do diploma distinguem o CPC vigente do revogado. A sigla pode
# vir só depois de vírgula, sem conector ("art. <n>, LV, CF"); nome por extenso sem
# conector seria prosa.
_ADJETIVO_DE_DIPLOMA = r"(?:(?:novo|atual|vigente)\s+)"
_SIGLA_DE_DIPLOMA = rf"{_DIPLOMA_ACRONYMS}(?![A-Za-zÀ-ÿ])" r"(?:\s*/\s*\d{2,4})?"
_DISPOSITIVO = re.compile(
    rf"\b{_tolerante('art')}(?:{_tolerante('igo')}|\.|\b)\s*\n?\s*(?P<artigo>{_NUMERO_DE_ARTIGO})"
    rf"{_QUALIFICADORES}"
    r"(?:"
    rf"\s*,?\s*\n?\s*{_CONECTOR}\s+{_ADJETIVO_DE_DIPLOMA}?(?P<diploma>{_DIPLOMA})"
    # O ano por extenso depois do número ("Lei nº 9.504, de 30 de setembro de 1997")
    # fica fora do span, mas é lido para que a resolução o confira.
    r"(?=,?\s+de\s+(?:\d{1,2}º?\s+de\s+[a-zç]+\s+de\s+)?(?P<ano_da_lei>(?:18|19|20)\d{2})\b)?"
    rf"|\s*,\s*(?P<diploma_sigla>(?-i:{_SIGLA_DE_DIPLOMA}))"
    r")",
    re.IGNORECASE,
)

# Família `vaga`: tribunal + ano + relator. O relator é a âncora que separa o
# padrão de uma menção solta a ano; as palavras toleram o ruído de OCR.
_RELATOR = (
    rf"(?:[Rr]{_tolerante('el')}(?:{_tolerante('at')}[0oaã]r[ilaã]?[aã]?)?\.?\s*"
    # "Min" aceita o ponto trocado por grau ("Min°").
    rf"(?:Mi[nN]\s?[.°º]?|{_tolerante('Ministr')}[ao])?\.?"
    rf"|{_tolerante('relatoria')}\s+d[eoc])"
)

# Cabeça: classe ou genérico ("julgado", "acórdão"), seguida de perto pelo
# tribunal ou pelo ano, para não começar em "Cita-se o julgado …".
_CABECA_VAGA = (
    rf"(?:{_tolerante('julgad')}[oaã0]|{_tolerante('acórdão')}|{_tolerante('precedente')}"
    rf"|{_tolerante('decisão')}"
    # Incidente antes da classe ("AgInt no AREsp") só com forma de sigla (duas
    # maiúsculas), para a prosa capitalizada não abrir o span.
    r"|(?:[A-ZÀ-Ú][a-zà-ú]*[A-ZÀ-Ú][\wÀ-ú.\-]*\s+n[oa]s?\s+)*"
    r"[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}"
    r"(?:\s+(?:em\s+|de\s+|do\s+|da\s+|com\s+)?[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}){0,3}"
    r")"
)

# Nome do relator: palavras capitalizadas, conector e inicial abreviada. O ponto
# vale só como inicial e cabe no máximo uma quebra de linha, para o nome não
# atravessar o fim da frase e engolir a citação seguinte.
_SEPARADOR_DE_NOME = r"(?:[ \t\xa0]+\n?[ \t\xa0]*|\n[ \t\xa0]*)"
# A inicial também sofre ruído ("rnAURO", "eARLOS" em caixa alta); só essas formas,
# para não admitir palavra de prosa minúscula.
_PALAVRA_DE_NOME = r"(?:[A-ZÀ-Ú]|rn(?=[\wÀ-ú])|[a-zà-ú](?=[A-ZÀ-Ú]{2}))(?:[\wÀ-ú']+|\.)"
_NOME_PROPRIO = (
    rf"{_PALAVRA_DE_NOME}"
    rf"(?:{_SEPARADOR_DE_NOME}(?:d[aeo]s?{_SEPARADOR_DE_NOME})?{_PALAVRA_DE_NOME}){{0,4}}"
)

# O ano é a única quantia numérica da `vaga`: tolera OCR e quebra de linha, ou a
# citação some inteira.
_ENTRE_DIGITOS = r"[ \t]*\n?[ \t]*"
_DIGITO_OU_OCR = rf"[\d{''.join(sorted(set(OCR_PARA_DIGITO)))}]"
_ANO_TOLERANTE = (
    rf"[12lIZz]{_ENTRE_DIGITOS}[90OoGgqb]{_ENTRE_DIGITOS}"
    rf"{_DIGITO_OU_OCR}{_ENTRE_DIGITOS}{_DIGITO_OU_OCR}"
)

_VAGA = re.compile(
    rf"{_CABECA_VAGA}"
    rf"(?:\s*,?\s*{_CONECTOR}\s+(?:{_SIGLA_DE_TRIBUNAL}|{_TRIBUNAL_POR_EXTENSO}))?"
    rf"\s*,?\s*(?:{_tolerante('proferid')}[oaã0]|{_tolerante('julgad')}[oaã0])?\s*(?:d[ec]|[ec]rn|[ec]m)\s*\n?\s*"
    rf"{_ANO_TOLERANTE}"
    r"[^.]{0,30}?"
    rf"{_RELATOR}\s*{_NOME_PROPRIO}",
)

# ---------------------------------------------------------------------------
# `vaga` por contagem de constituintes
#
# `_VAGA` exige cabeça -> tribunal -> ano -> relator nessa ordem. Este caminho
# reconhece os constituintes em qualquer ordem (relator e ano presentes, nenhum
# número de processo) e só roda onde `_VAGA` não casou.
# ---------------------------------------------------------------------------

# A janela é a sentença. Ponto de abreviação ("Rel.", "Min.", "n.") não encerra
# a sentença; senão "Rel. Min. Fulano" se partia e relator e ano nunca se juntavam.
_FIM_DE_SENTENCA = re.compile(r"(?<!\b[A-Z])(?<!\b[A-Za-z]{2})(?<!\b[A-Za-z]{3})[.!?](?=\s|$)")

# Relator em formas que `_RELATOR` não cobre: "relatado por X", "da lavra do
# Ministro X", "Ministro X" sem "Rel.". Sem relator nomeado não há `incompleta`.
_RELATOR_NOMEADO = re.compile(
    r"(?:"
    rf"{_RELATOR}"
    rf"|{_tolerante('relatad')}[oaã0]\s+(?:p[0o]r|p[ec]l[oaã0])"
    rf"|{_tolerante('lavra')}\s+d[eoac]s?"
    rf"|Min\.?|{_tolerante('Ministr')}[ao]s?|Des(?:embargador)?[ao]?\.?"
    r")"
    rf"\s*(?:d[eoa]s?\s+)?(?:Min\.?|Ministr[ao])?\.?\s*{_NOME_PROPRIO}"
)

# O lookahead rejeita só o ponto que estrutura número (`2019.7.00`), não o ponto
# final: o ano que fecha a sentença ("de 2019.") precisa continuar valendo.
_ANO_ISOLADO = re.compile(rf"(?<![\d./-]){_ANO_TOLERANTE}(?![-/]|\.?\d)")

_MENCAO_TRIBUNAL = re.compile(rf"\b{_SIGLA_DE_TRIBUNAL}")

# Cabeça opcional da referência; só estende o span à esquerda.
_CABECA_ISOLADA = re.compile(
    rf"\b(?:{_tolerante('julgad')}[oaã0]|{_tolerante('acórdão')}|{_tolerante('precedente')}"
    rf"|{_tolerante('decisão')}|{_tolerante('aresto')}"
    r"|voto|jurisprud[êe]ncia|entendimento|prec)[\wÀ-ú]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Achado:
    """Um span candidato a citação, antes de ser resolvido.

    ``dados`` leva os grupos já isolados na detecção (artigo, diploma, súmula),
    para a resolução não reparsear o trecho (``5úmula 211`` tem dois números).
    """

    inicio: int
    fim: int
    trecho: str
    familia: str  # um de FAMILIAS
    tipo: str  # jurisprudencia · lei
    dados: tuple[tuple[str, str], ...] = ()


def _digitos(texto: str) -> int:
    return sum(c.isdigit() for c in texto)


def _digitos_suficientes(numero: str, corpo: str, inicio: int) -> bool:
    """O núcleo tem dígitos bastantes para ser número de processo?

    Abaixo de `_MINIMO_DIGITOS` dígitos reais, aceita se o OCR pode ter comido
    os demais (`Rcl 4B.71B/RS`): o número reparado precisa chegar ao mínimo e o
    prefixo precisa nomear uma classe processual.
    """
    if _digitos(numero) >= _MINIMO_DIGITOS:
        return True
    # Com um dígito real só passam numeração de seção (`III.1`) e nome em caixa
    # alta (`3SSIL`); com dois, o ruído ainda é recuperável sem falso positivo.
    if _digitos(numero) < 2:
        return False
    if sum(c.isdigit() for c in _corrigir_ocr(numero)) < _MINIMO_DIGITOS:
        return False
    return _prefixo_nomeia_classe(corpo, inicio)


def _prefixo_nomeia_classe(corpo: str, inicio: int) -> bool:
    """Há uma sigla ou classe processual no prefixo que `_expandir_prefixo` aceita?"""
    comeco = _expandir_prefixo(corpo, inicio)
    tokens = corpo[comeco:inicio].split()
    return any(
        t[0].isupper() and _ELO.fullmatch(t) and not _NUMERO_MARCA.fullmatch(t) for t in tokens
    )


# A marca de número sozinha ("Nº", "No") tem forma de elo, mas não nomeia classe.
_NUMERO_MARCA = re.compile(r"[nN]\s*[.ºo°O]{0,2}")


def _numero_de_lei_plausivel(diploma: str) -> bool:
    """O número da lei citada por número tem dígito real? Evita "Lei Os" -> "Lei 05"."""
    # Fronteira de palavra: sem ela o `o` final de "Lei Maior do Estado" era lido
    # como número sem dígito real e a citação sumia.
    numero = re.search(rf"(?<![A-Za-zÀ-ÿ]){_DIGITOIDE}[{_DIGITOIDE[1:-1]}./]*$", diploma or "")
    if numero is None or not re.match(r"(?i)\s*(?:lei|lc|decreto)", diploma):
        return True
    return _digitos(numero.group()) >= 1


def _tem_digito_real(numero: str | None) -> bool:
    """O número tem ao menos um dígito real? Impede que `art Iss` vire artigo."""
    return bool(numero) and _digitos(numero) >= 1


# Ano solto ("de 2025") não é número de processo.
_ANO_SOLTO = re.compile(r"^(?:19|20)\d{2}$")

# `fls. <n>/<n>` — referência de página.
_PAGINAS = re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$")

# `<n>/<ano>` é protocolo ou lei: no CNJ o ano fica no meio, no STJ na frente.
_TERMINA_EM_ANO = re.compile(r"^\d{1,5}(?:\.\d{3})*\s*/\s*(?:19|20)\d{2}$")

# Centavos logo depois do número (`1.500.000,00`). A forma do número não
# distingue quantia de REsp; a vírgula com dois dígitos, fora do casamento, sim.
_CENTAVOS = re.compile(r"^,\d{2}(?!\d)")

# Data `dd/mm/aaaa` ou `dd.mm.aaaa`. Sem `$` porque o núcleo engole a hora
# seguinte ("05/08/2021 14"); com ponto, o ano precisa ter quatro dígitos.
_DATA = re.compile(
    r"^(?:\d{1,2}/\d{1,2}/(?:\d{2}|(?:19|20)\d{2})|\d{1,2}\.\d{1,2}\.(?:19|20)\d{2})(?!\d)"
)

# Rótulos que marcam o número seguinte como distrator (folhas, protocolo,
# documentos civis, valores), não como citação.
_ROTULO_DISTRATOR = re.compile(
    # `\b` evita casar `tel` dentro de "tutela nº"; `R$` termina em símbolo e
    # fica fora dela. `f[l1I]s?` tolera a letra do meio corrompida.
    r"(?:\b(?:f[l1I]s?|folhas?|protocolo|CPF|CNPJ|valor\s+da\s+causa"
    r"|telefone|tel|fone|celular|RG|CEP|PIS|PASEP|CNH|NIT"
    r"|matr[íi]cula|guia|precat[óo]rio|ag[êe]ncia|conta"
    # O DDD entre parênteses não pode quebrar a adjacência.
    r"|OAB\s*/?\s*[A-Z]{0,2})|R\$)\s*[.:]?\s*(?:\(\s*\d{2}\s*\)\s*)?"
    # Até duas palavras de ligação ("Inscrito na OAB sob o nº 123.456/SP").
    r"(?:\s*(?:sob|sob\s+o|[oa]s?|n[oa]s?|d[oae]s?|em|é)\b){0,2}\s*"
    rf"(?:{_NUMERO}\s*)?$",
    re.IGNORECASE,
)

# Ato normativo colado à esquerda do número ("Lei 8.112/90", "Informativo
# 1.046"). Só um qualificador curto entre a palavra e o número, para não apagar
# o processo vizinho em "A Lei 8.112/90 … no REsp 1.234.567/SP".
_ATO_NORMATIVO = re.compile(
    rf"\b(?:{_tolerante('Lei')}(?:\s+(?:{_tolerante('Complementar')}|{_tolerante('Federal')}"
    rf"|{_tolerante('Estadual')}|{_tolerante('Municipal')}|{_tolerante('Ordinária')}))?"
    r"|LC|Decreto(?:[-‐\s]*Lei)?|Medida\s+Provis[óo]ria|MP|Portaria|Resolu[çc][ãa]o"
    r"|Instru[çc][ãa]o\s+Normativa|IN|Emenda(?:\s+Constitucional)?|EC"
    r"|Informativo|Info|OJ|Enunciado|Provimento|Ato|Of[íi]cio|Parecer|Nota\s+T[ée]cnica)"
    rf"\s*[.:]?\s*(?:{_NUMERO}\s*)?$",
    re.IGNORECASE,
)

# ── Número da prosa que não é número de processo ──────────────────────────────
#
# Quantidade, prazo, pena e valor ("<n> dias-multa", "cerca de <n> eleitores")
# casam o núcleo de `processo`. Estes filtros valem só para a detecção;
# `_e_numero_de_processo` também alimenta o índice e a `vaga`, e não muda.

# Artigo, tema ou súmula que a família específica não reconheceu, inclusive a
# enumeração ("arts. 1.036 e 1.037", "Temas 1.046 e 1.191"). Os elementos são só
# número e separador, então "art. 5º e REsp 1.234.567" mantém o REsp.
_ENUMERATED_NUMBER = rf"(?=[^\s,]*\d){_DIGITOIDE}[{_DIGITOIDE[1:-1]}.]*[ºo°ª]?(?:[-‐][A-Za-z])?"
_NON_PROCESS_LABEL = re.compile(
    rf"\b(?:{_tolerante('art')}(?:{_tolerante('igo')})?|{_tolerante('Tema')}"
    rf"|{_tolerante('Súmula')})[s5]?\.?\s*(?:{_NUMERO}\s*)?"
    rf"(?:{_ENUMERATED_NUMBER}\s*(?:,|(?:,\s*)?(?:e|a|ao|ou|at[ée])(?![\wÀ-ú]))\s*)*$",
    re.IGNORECASE,
)

# Cabe uma enumeração de meia dúzia de artigos.
_LABEL_WINDOW = 120

# Unidade ou substantivo de quantidade logo depois do número. O começo cobre o
# dígito largado pela unidade colada ("12.500kg"), a faixa ("1.000 a 2.000") e o
# extenso entre parênteses. Letra única e "mg" só em minúscula ("MG" é UF), exceto
# "L". A vírgula só entra como decimal; solta, é pontuação da frase.
_QUANTITY_UNIT = re.compile(
    r"\d*(?:,\d+)?"
    r"(?:[ \t\xa0]*\n?[ \t\xa0]*(?:a|à|at[ée]|e|ou|[-–])[ \t\xa0]*\n?[ \t\xa0]*"
    r"\d[\d.]*(?:,\d+)?)?"
    r"(?:[ \t\xa0]*\([^()\d\n]{1,80}\))?"
    r"[ \t\xa0]*\n?[ \t\xa0]*"
    r"(?:dias(?:[-‐ ]multa)?|meses|anos|semanas|horas|minutos|segundos"
    r"|metros(?:[ \t\xa0]+(?:quadrados|c[úu]bicos))?|quil[ôo]metros|cent[íi]metros"
    r"|mil[íi]metros|hectares|alqueires|gramas|quilogramas|quilos|toneladas|litros"
    r"|mililitros|m[²³23]|km[²2]?|cm|mm|ha|kg|(?-i:mg)|ml|kwh|(?-i:m|g|l|L)"
    r"|reais|d[óo]lares|euros|sal[áa]rios(?:[-‐ ]m[íi]nimos?)?|mil|milh[õo]es|bilh[õo]es"
    r"|%|por[ \t\xa0]+cento|pontos[ \t\xa0]+percentuais"
    r"|pessoas|eleitores|votos|habitantes|vezes|unidades|p[áa]ginas|folhas|exemplares"
    r"|muni[çc][õo]es|cabe[çc]as|processos)"
    r"(?![A-Za-zÀ-ÿ0-9])",
    re.IGNORECASE,
)

# O grama abreviado que o núcleo engole (`g` é digitoide). Só depois de espaço
# ou de grupo de milhar completo: "1.234.56g" é um 9 corrompido. O `l` fica de
# fora porque o ruído repete a última letra ("Código Penal l").
_SWALLOWED_UNIT = re.compile(r"(?:\d[ \t\xa0]|\.\d{3})g$")

# Com dez dígitos ou mais o número é CNJ ou número único do STJ, e as regras de
# quantidade não valem ("suspensos até 0801234-56…").
_LONG_NUMBER_DIGITS = 10

# Quantificador colado ao número: não sobra lugar para classe entre os dois,
# então dispensa `_names_class_or_marker`.
_QUANTIFIER = re.compile(
    r"(?:\b(?:cerca\s+de|aproximadamente|mais\s+de|menos\s+de|at[ée]|entre|quase|apenas"
    r"|somente|total\s+de|pelo\s+menos|ao\s+menos|no\s+m[áa]ximo|no\s+m[íi]nimo"
    r"|acima\s+de|abaixo\s+de|superior(?:es)?\s+a|inferior(?:es)?\s+a"
    r"|em\s+torno\s+d[eoa]s?|por\s+volta\s+de)|US\$)\s*$",
    re.IGNORECASE,
)

# Marca de número de processo mesmo sem classe ("nº", "ns.", "processo",
# "autos"). "recurso" em minúscula não tem forma de elo e por isso está aqui.
_PROCESS_MARKER = re.compile(
    r"n\s*[.ºo°0]{0,2}|n[º°]?s\.?|[º°]|processos?|autos|recursos?|feitos?|n[úu]meros?",
    re.IGNORECASE,
)

# Palavras de ligação que encostam no número na prosa ("pena de <n>"). Em caixa
# alta ou abrindo frase ("DE", "Os") teriam forma de sigla. "se" fica de fora:
# "SE" é a classe Sentença Estrangeira.
_FUNCTION_WORDS = (
    frozenset(
        """
    a o as os ao aos um uma uns umas de da do das dos em na nas nos num numa
    e ou que com por pela pelo pelas pelos para sem sob sobre entre ate apos
    desde contra como cerca mais menos quase cada seu sua seus suas todos todas
    mas nem so foi foram sao era eram sera serao seria ha houve havia tem teve tinha
    """.split()
    )
    | _PALAVRA_DE_PROSA
)


def _looks_like_class(token: str) -> bool:
    """O token tem forma de sigla processual ou é núcleo de nome de classe?

    Mais estreito que `_e_elo`: palavra capitalizada que abre a frase
    ("Compareceram 5.130 pessoas") não conta. Sigla composta ("TST-E-ED-RR")
    é julgada pedaço a pedaço.
    """
    letras = [c for c in token if c.isalpha()]
    if not letras or not letras[0].isupper():
        return False
    if chave_textual(token.strip(".")) in _NUCLEO_DE_CLASSE:
        return True
    pedacos = [p for p in re.split(r"[-‐.]", token) if any(c.isalpha() for c in p)]
    return all(_is_acronym(p) for p in pedacos)


def _is_acronym(piece: str) -> bool:
    """Caixa mista (`REsp`, `AgInt`), caixa alta curta (`RESP`, `HC`) ou curta (`Rcl`)."""
    letras = [c for c in piece if c.isalpha()]
    maiusculas = sum(c.isupper() for c in letras)
    if 2 <= maiusculas < len(letras):
        return True
    if maiusculas == len(letras):
        return len(letras) <= 6
    return letras[0].isupper() and len(letras) <= 4


def _names_class_or_marker(before: str) -> bool:
    """A palavra colada à esquerda do número nomeia classe processual ou é marca?

    Decide o vizinho imediato; a cadeia inteira engoliria prosa capitalizada
    ("PENA DE 1.460"). Ela só entra quando o vizinho é palavra por extenso
    ("Recurso Especial"), e aí só o núcleo de classe conta.
    """
    recuo = len(before)
    quebras = 0
    while recuo > 0 and before[recuo - 1] in " \t\xa0\n":
        if before[recuo - 1] == "\n":
            quebras += 1
        recuo -= 1
    if quebras > 1:
        return False
    fim_token = recuo
    while recuo > 0 and not before[recuo - 1].isspace():
        recuo -= 1
    token = before[recuo:fim_token].strip("(),;:")
    if not token:
        return False
    if _PROCESS_MARKER.fullmatch(token):
        return True
    if chave_textual(token.rstrip(".")) in _FUNCTION_WORDS:
        return False
    if _looks_like_class(token):
        return True
    cadeia = before[_expandir_prefixo(before, len(before)) :].split()
    return any(chave_textual(t.strip(".,;:()")) in _NUCLEO_DE_CLASSE for t in cadeia)


def _is_prose_number(number: str, text: str, start: int, end: int) -> bool:
    """O número é quantidade da prosa, ou de artigo, e não número de processo?

    Só lê as janelas vizinhas a ``text[start:end]``.
    """
    before = text[max(0, start - _LABEL_WINDOW) : start]
    if _NON_PROCESS_LABEL.search(before):
        return True
    if _digitos(_corrigir_ocr(number)) >= _LONG_NUMBER_DIGITS:
        return False
    if _QUANTIFIER.search(before[-_JANELA_ROTULO:]):
        return True
    unit = _QUANTITY_UNIT.match(text, end) or _SWALLOWED_UNIT.search(number)
    return unit is not None and not _names_class_or_marker(before)


def _forma_canonica(numero: str) -> str:
    """O número sem espaço nem troca de dígito por letra, mantendo ``/`` e ``.``.

    Os filtros de forma (``_ANO_SOLTO``, ``_PAGINAS``) precisam sobreviver a
    quebras de linha e ruído de OCR no meio do número.
    """
    return re.sub(r"[\s]+", "", _corrigir_ocr(numero))


# Cabe "valor da causa" com folga para ruído que insere caractere (`m` -> `rn`).
_JANELA_ROTULO = 40


def _e_numero_de_processo(numero: str, antes: str, depois: str = "") -> bool:
    """Filtra o que tem forma de número mas não identifica processo.

    ``depois`` só serve ao filtro de centavos.
    """
    compacto = _forma_canonica(numero)
    if _ANO_SOLTO.match(compacto) or _PAGINAS.match(compacto):
        return False
    if _TERMINA_EM_ANO.match(compacto) or _DATA.match(compacto):
        return False
    # Data com hora: a forma canônica cola `05/08/2021 14` em `05/08/202114`.
    if _DATA.match(numero.lstrip()):
        return False
    if _CENTAVOS.match(depois):
        return False
    if _INSCRICAO_COM_UF.search(antes):
        return False
    janela = antes[-_JANELA_ROTULO:]
    return not (_ROTULO_DISTRATOR.search(janela) or _ATO_NORMATIVO.search(janela))


# Inscrição na OAB colada à UF ("ALINE SANTOS - DF043530", "(OAB SC50542)"). Exige
# travessão ou "OAB" antes: sem eles a UF colada é classe ("MS12345/DF").
_INSCRICAO_COM_UF = re.compile(
    rf"(?:[-–—]|\bOAB\b[ \t\xa0]*[:/]?)[ \t\xa0]*(?:{'|'.join(sorted(UFS))})\d*$"
)


def _aparar(texto: str, inicio: int, fim: int) -> tuple[int, int]:
    """Encolhe o span até que as bordas não sejam espaço ou pontuação solta."""
    while inicio < fim and (texto[inicio].isspace() or texto[inicio] in ",;:"):
        inicio += 1
    while fim > inicio and (texto[fim - 1].isspace() or texto[fim - 1] in ",;:."):
        fim -= 1
    return inicio, fim


def _expandir_prefixo(corpo: str, inicio: int) -> int:
    """Anda para a esquerda a partir do número, enquanto houver elos de prefixo.

    Em Python e não em regex: ``(?:elo\\s*){0,12}`` antes do número causa
    backtracking catastrófico quando o número falha.
    """
    aceitos: list[tuple[int, str]] = []
    posicao = inicio
    for _ in range(_MAXIMO_ELOS):
        recuo = posicao
        quebras = 0
        # Uma quebra de linha é atravessada; duas são fim de parágrafo.
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
        if _e_institucional(token):
            # O órgão julgador não faz parte da citação, nem o complemento do
            # nome dele ("Corte Especial", "Ministro Gilmar Mendes").
            while aceitos and _e_palavra_de_nome(aceitos[-1][1]):
                aceitos.pop()
            break
        if token == "e" and aceitos and aceitos[-1][1] in _CONTRACAO:
            # "do RE e da Rcl" coordena duas citações; nome de classe usa a
            # preposição nua ("Liminar e de Sentença").
            break
        if not _e_elo(token) and not _elo_corrompido(corpo, recuo, token):
            break
        aceitos.append((recuo, token))
        posicao = recuo
    # Conector é elo entre siglas ("AgInt no REsp"), nunca a borda do span.
    while aceitos and _CONECTOR_DE_BORDA.fullmatch(aceitos[-1][1]):
        aceitos.pop()
    return aceitos[-1][0] if aceitos else inicio


# Marca de número partida por espaço (`n º`). Só os símbolos: `o`/`O` e `n`
# soltos são prosa ("Ampara a pretensão o REsp").
_PEDACO_DE_MARCA = re.compile(r"[º°]")


def _elo_corrompido(corpo: str, inicio: int, token: str) -> bool:
    """O token é um elo que o ruído de OCR desfigurou?

    Cobre a marca partida (`n º`) e a sigla com maiúscula trocada por minúscula
    (`cspecial`, `eorpus`). Este segundo caso só vale se a palavra à esquerda
    também for elo, para a prosa minúscula continuar parando a cadeia.
    """
    if _PEDACO_DE_MARCA.fullmatch(token):
        return True
    # O `n` da marca partida só vale quando o símbolo vem logo depois.
    if token in ("n", "N") and _PEDACO_DE_MARCA.match(corpo[inicio + 1 :].lstrip()):
        return True
    if not token[:1].islower():
        return False
    desfeito = _DESFAZ_MAIUSCULA.get(token[0], "") + token[1:]
    if not desfeito or not _e_elo(desfeito):
        return False
    anterior = corpo[:inicio].rstrip().rsplit(None, 1)
    return bool(anterior) and _e_elo(anterior[-1])


# Inversa de `CONFUSOES_DE_LETRA` para trocas de uma letra que tiram a maiúscula.
_DESFAZ_MAIUSCULA = {
    confusao: original.upper()
    for original, confusao in CONFUSOES_DE_LETRA.items()
    if len(confusao) == 1 and confusao.isalpha() and confusao.islower()
}


def _sentencas(corpo: str) -> list[tuple[int, int]]:
    """Fronteiras de sentença, tolerantes ao ponto de abreviação."""
    limites = [0]
    for fim in _FIM_DE_SENTENCA.finditer(corpo):
        limites.append(fim.end())
    limites.append(len(corpo))
    return [(a, b) for a, b in zip(limites, limites[1:], strict=False) if b > a]


# O último pedaço do núcleo, depois de um espaço: `5ob` em "2020 5ob".
_PEDACO_FINAL = re.compile(rf"[ \t\xa0\n]+({_DIGITOIDE}+)$")

# Pedaço após ponto final e espaço: palavra da frase seguinte só com digitoides
# ("…567. O recurso").
_PEDACO_APOS_PONTO = re.compile(rf"\.[ \t\xa0\n]+({_DIGITOIDE}+)$")


def _sem_palavra_corrompida(numero: str) -> str:
    """O núcleo sem o pedaço final que é palavra com letra virada dígito.

    "de 2020 5ob a vigência" casava `2020 5ob`, que já não é ano. O pedaço sai
    se tem mais letra que dígito e o que vem antes é ano ou página; depois de
    ". ", sai sempre que não tem dígito real.
    """
    apos_ponto = _PEDACO_APOS_PONTO.search(numero)
    if apos_ponto is not None and not any(c.isdigit() for c in apos_ponto.group(1)):
        return numero[: apos_ponto.start()]
    pedaco = _PEDACO_FINAL.search(numero)
    if pedaco is None:
        return numero
    final = pedaco.group(1)
    letras = sum(c.isalpha() for c in final)
    if letras <= len(final) - letras:
        return numero
    resto = numero[: pedaco.start()]
    # Em qualquer outro caso o pedaço é o último grupo de um número corrompido
    # ("APL 7000380-08 2023 7 00 O0OO").
    canonico = _forma_canonica(resto)
    if not (_ANO_SOLTO.match(canonico) or _PAGINAS.match(canonico)):
        return numero
    return resto


def _tem_numero_de_processo(trecho: str) -> bool:
    """Há na janela um número que a base consegue resolver?

    Com número, a citação é `real` ou `inventada`; sem ele, é `incompleta`.
    """
    return any(
        _digitos(m.group()) >= _MINIMO_DIGITOS
        and _e_numero_de_processo(m.group(), trecho[: m.start()], trecho[m.end() :])
        for m in _NUMERO_PROCESSO.finditer(trecho)
    )


def _vagas_por_constituinte(corpo: str) -> list[tuple[int, int]]:
    """Spans de `vaga` por sentença: relator nomeado e ano, sem número de processo.

    O span vai do primeiro ao último constituinte, estendido até a cabeça
    ("julgado", "acórdão") quando ela abre a referência.
    """
    spans: list[tuple[int, int]] = []
    for inicio_sent, fim_sent in _sentencas(corpo):
        trecho = corpo[inicio_sent:fim_sent]
        if len(trecho.strip()) < 12:
            continue

        relator = _RELATOR_NOMEADO.search(trecho)
        if relator is None:
            continue
        # Dois dígitos reais no ano: `_ANO_TOLERANTE` aceita `logo` e `zoos`, mas
        # o ruído ainda deixa `2Ol9` passar.
        anos = [m for m in _ANO_ISOLADO.finditer(trecho) if _digitos(m.group()) >= 2]
        if not anos:
            continue

        if _tem_numero_de_processo(trecho):
            continue

        inicio = min(relator.start(), anos[0].start())
        fim = max(relator.end(), anos[-1].end())

        tribunal = _MENCAO_TRIBUNAL.search(trecho)
        if tribunal is not None:
            inicio = min(inicio, tribunal.start())
            fim = max(fim, tribunal.end())

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
        dados = tuple((k, v) for k, v in (m.groupdict() or {}).items() if v)
        achados.append(Achado(inicio, fim, texto[inicio:fim], familia, tipo, dados))

    for m in _SUMULA.finditer(corpo):
        if not _tem_digito_real(m.group("numero")):
            continue
        registrar(m, "sumula", "jurisprudencia")
    for m in _TEMA.finditer(corpo):
        if not _tem_digito_real(m.group("numero")):
            continue
        registrar(m, "tema", "jurisprudencia")
    for m in _DISPOSITIVO.finditer(corpo):
        if not _tem_digito_real(m.group("artigo")):
            continue
        if not _numero_de_lei_plausivel(m.group("diploma") or m.group("diploma_sigla")):
            continue
        registrar(m, "dispositivo", "lei")
    vagas: list[tuple[int, int]] = []
    for m in _VAGA.finditer(corpo):
        # Número de processo logo à esquerda torna a citação resolvível, e `vaga`
        # venceria `processo` na precedência. A janela é curta para não descartar
        # uma `incompleta` que só divide a frase com outra citação numerada.
        if _tem_numero_de_processo(corpo[max(0, m.start() - 24) : m.start()]):
            continue
        registrar(m, "vaga", "jurisprudencia")
        vagas.append((m.start(), m.end()))

    # Rede para as ordens que `_VAGA` não prevê; a expressão tem a borda mais justa.
    for inicio_vaga, fim_vaga in _vagas_por_constituinte(corpo):
        if any(not (fim_vaga <= i or inicio_vaga >= f) for i, f in vagas):
            continue
        inicio, fim = _aparar(texto, inicio_corpo + inicio_vaga, inicio_corpo + fim_vaga)
        if fim > inicio:
            achados.append(Achado(inicio, fim, texto[inicio:fim], "vaga", "jurisprudencia"))
            vagas.append((inicio_vaga, fim_vaga))

    for m in _NUMERO_PROCESSO.finditer(corpo):
        numero = _sem_palavra_corrompida(m.group())
        fim_numero = m.start() + len(numero)
        if not _digitos_suficientes(numero, corpo, m.start()):
            continue
        if not _e_numero_de_processo(numero, corpo[: m.start()], corpo[fim_numero:]):
            continue
        if _is_prose_number(numero, corpo, m.start(), fim_numero):
            continue
        inicio = _expandir_prefixo(corpo, m.start())
        fim = fim_numero
        uf = _UF.match(corpo, fim)
        if uf is not None:
            fim = uf.end()
        inicio, fim = _aparar(texto, inicio_corpo + inicio, inicio_corpo + fim)
        if fim > inicio:
            achados.append(Achado(inicio, fim, texto[inicio:fim], "processo", "jurisprudencia"))

    return achados


# Precedência em sobreposição: as famílias específicas vencem `processo`, cujo
# prefixo genérico casaria "Súmula 331" e "art. 373".
_PRECEDENCIA = {"dispositivo": 0, "sumula": 1, "tema": 2, "vaga": 3, "processo": 4}


def _resolver_sobreposicao(achados: list[Achado]) -> list[Achado]:
    """Mantém um span por região do texto.

    Duas predições com IoU >= 0,5 entre si invalidam a submissão inteira.
    """
    ordenados = sorted(
        achados,
        key=lambda a: (_PRECEDENCIA[a.familia], -(a.fim - a.inicio), a.inicio),
    )
    escolhidos: list[Achado] = []
    for achado in ordenados:
        conflitos = [
            e for e in escolhidos if not (achado.fim <= e.inicio or achado.inicio >= e.fim)
        ]
        if conflitos and achado.familia == "processo":
            achado = _sem_o_prefixo_alheio(achado, conflitos)
            if achado is not None:
                conflitos = []
        if conflitos:
            continue
        escolhidos.append(achado)
    return sorted(escolhidos, key=lambda a: a.inicio)


def _sem_o_prefixo_alheio(achado: Achado, vencedores: list[Achado]) -> Achado | None:
    """O span de processo que perdeu só pelo prefixo, cortado depois do vencedor.

    Em "art. 5º da CF e REsp 1.234.567/SP" o prefixo do REsp atravessa a citação
    anterior; se o número está todo depois do vencedor, o span recomeça ali.
    """
    fim_vencedor = max(e.fim for e in vencedores)
    if any(e.inicio >= achado.inicio + len(achado.trecho) for e in vencedores):
        return None
    deslocamento = fim_vencedor - achado.inicio
    resto = achado.trecho[deslocamento:]
    # Pontuação, conjunção e conector entre as duas citações ficam de fora.
    cortado = re.match(r"[\s.,;:]*(?:(?:e|o|a|os|as|n[oa]s?|d[oae]s?|em)\s+)*", resto)
    inicio_rel = deslocamento + (cortado.end() if cortado else 0)
    trecho = achado.trecho[inicio_rel:]
    # O resto precisa ser classe seguida de número; senão o rol de advogados
    # ("ALINE SANTOS - DF043530") ressuscitava.
    numero = _NUMERO_PROCESSO.search(trecho)
    if numero is None or not _prefixo_nomeia_classe(trecho, numero.start()):
        return None
    return Achado(
        achado.inicio + inicio_rel, achado.fim, trecho, achado.familia, achado.tipo, achado.dados
    )


def detectar(texto: str) -> list[Achado]:
    """Encontra as citações candidatas, ordenadas por posição e sem sobreposição."""
    return _resolver_sobreposicao(_candidatos(texto, fim_do_cabecalho(texto)))
