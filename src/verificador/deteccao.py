"""Detecção dos spans de citação no texto do parecer.

Quem não entrega o span de uma citação não consegue classificá-la, e isso conta
como erro de recall. O alinhamento com o gabarito é por sobreposição com
IoU ≥ 0,5, então a borda exata não precisa ser perfeita — mas a citação inteira
precisa aparecer.

A organização é por família, porque a família determina contra o quê a citação
é resolvida:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.599.910/PR``)
``sumula``       ``Súmula <n> do <tribunal>``, ``Súmula Vinculante <n>``
``tema``         ``Tema 2.680 da repercussão geral``
``dispositivo``  ``art. <n>, <inciso>, do <código>``
``vaga``         sem identificador suficiente para consultar a base

**A âncora de ``processo`` é o número, não a sigla.** Medindo o gabarito, as
classes processuais aparecem em mais de 90 grafias distintas — de ``RR-`` a
``Embargos de Declaração no Agravo Interno no Agravo em Recurso Especial nº``.
Enumerá-las casa a amostra de desenvolvimento e falha no conjunto cego, onde o
material avisa que "as siglas processuais observadas não esgotam o domínio".
Ancorar no número e expandir para a esquerda degrada bem: numa classe não vista
o span fica curto, mas o número — que é o que resolve — continua capturado, e o
span costuma sobreviver ao IoU ≥ 0,5.

**A família ``vaga`` tem uma forma só.** Depois da revisão de 15/09/2026 as 32
citações ``incompleta`` do gabarito são todas do padrão tribunal + ano +
relator — ``julgado do <tribunal> proferido em <ano> pela relatoria de
<nome>``. As 32 nomeiam um relator, o único dígito é o ano e nenhuma traz
número de processo. As frases genéricas ("normas de regência da matéria") e as sem número
("reiterados precedentes do STJ") saíram do gabarito nas duas revisões. O sinal
a procurar é **menção a relator sem número de processo**, não um repertório de
frase vaga. Ver ``docs/investigacao.md``.

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

from .normalizacao import (
    CONFUSOES_DE_LETRA,
    OCR_PARA_DIGITO,
    UFS,
    _corrigir_ocr,
    chave_textual,
    sem_acento,
)
from .texto import fim_do_cabecalho

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

FAMILIAS = ("processo", "sumula", "tema", "dispositivo", "vaga")

# Abaixo disso não há número de processo — só ano, inciso e página.
_MINIMO_DIGITOS = 4

# "nº" em todas as grafias que a amostra traz, inclusive as de OCR (No, N°, n.).
_NUMERO = r"(?:n\s*[.ºo°]{0,2}|N\s*[.ºO°]{0,2})"

# Pontuação que pode aparecer dentro de um número de processo, incluindo a
# quebra de linha e o espaço não-quebrável (`533-80. 2012` vem com \xa0).
#
# **No máximo uma quebra de linha.** Com `\s` solto o núcleo atravessava o fim do
# parágrafo e engolia o título da seção seguinte: em
# `Ag. Int. No 7001184-1520197000000.\n\nI — DA COMPETÊNCIA` o span ia até o `I`
# do título, e o IoU contra o gabarito caía a 0,73. É a mesma política que
# `_expandir_prefixo` já aplica do outro lado — uma quebra é continuação da
# citação, duas são fim de parágrafo.
_DENTRO = r"(?:[ \t\xa0.\-–—/]|\n(?![ \t]*\n))"

# A classe de "digitoide": dígito ou letra que o OCR põe no lugar de um dígito.
#
# **Derivada de `OCR_PARA_DIGITO`, não escrita à mão.** A versão literal
# (`[\dOolISsgGbBZz]`) omitia `i` e `q`, que a tabela de reparo conhece, e a
# divergência custava a citação inteira: `REsp 1737i8/SP` não casava o núcleo e
# o span sumia, mesmo com `digitos_do_identificador` sabendo devolver `173718`.
# A normalização consertava, mas a detecção nunca lhe entregava o trecho.
#
# `_ANO_TOLERANTE` já derivava a classe da mesma tabela; era a assimetria entre
# as duas construções que deixava a divergência passar. Derivar aqui também
# elimina a classe inteira de defeito, em vez de acrescentar `i` e `q` à mão.
_DIGITOIDE = rf"[\d{re.escape(''.join(sorted(set(OCR_PARA_DIGITO))))}]"


def _tolerante(palavra: str) -> str:
    """Expressão que casa a palavra-chave com o ruído de OCR de letra do nível 2.

    O nível 2 corrompe uma letra por palavra, inclusive nas palavras que as
    expressões usam como âncora: `Súrnula`, `Códlgo`, `rclatoria`, `jiilgado`.
    Com a âncora escrita literal, a citação sumia inteira — medido nos corpora de
    `ocr_palavra`, era a maior parte das 43 perdas restantes, e em
    `Código de Processo Penal Mllitar` produzia o erro grave (CPPM lido como CPP).

    Cada letra aceita a própria forma, a forma sem acento e a confusão de
    `CONFUSOES_DE_LETRA`. A tolerância vale **só** para as palavras-chave fixas,
    nunca para classes abertas — é o que mantém a superfície de falso positivo
    onde estava: a âncora continua exigindo a palavra inteira, e o resto da
    expressão (número, diploma, tribunal) continua exigido.
    """
    partes = []
    for letra in palavra:
        base = sem_acento(letra)
        opcoes = {letra, base}
        confusao = CONFUSOES_DE_LETRA.get(base.lower())
        if confusao:
            opcoes.add(confusao)
        simples = sorted(o for o in opcoes if len(o) == 1)
        classe = re.escape(simples[0]) if len(simples) == 1 else f"[{''.join(simples)}]"
        compostas = sorted(o for o in opcoes if len(o) > 1)
        partes.append(f"(?:{classe}|{'|'.join(compostas)})" if compostas else classe)
    return "".join(partes)


# O núcleo numérico: admite letra de OCR no lugar de um dígito, para não cortar
# a citação ao meio (`21737l8`).
#
# **O primeiro caractere também pode ser digitoide.** Ele era `\d` literal, e o
# OCR corrompe a primeira posição como qualquer outra: em `REsp l.599.910/PR` o
# núcleo começava no `5` e devolvia `599910`, um número *diferente*, que não
# resolve na base. Essa é a pior forma de erro — silenciosa: o span existe, o IoU
# passa, e a citação vira `inventada` com confiança alta. Medindo 4.000
# perturbações de um identificador sintético a taxa 0,4, **79% de todas as
# falhas de `ocr_numero` tinham o primeiro dígito corrompido**.
#
# Esta mudança foi **rejeitada** no checkpoint 02 por produzir 31 falsos
# positivos na base limpa, todos em `fls. <n>/<n>`, e por perder no ponto de
# operação (0,8908 -> 0,8802 a taxa 0,15). O que mudou desde então: o lookbehind
# que rejeita letra precedida de letra — que o próprio checkpoint indicava como
# a correção faltante —, o filtro `_DATA`, a janela de rótulo de 40 caracteres e
# `_PAGINAS` comparando a forma canônica. Remedido agora com 5 sementes:
#
#     ocr_numero    1,0266 -> 1,0455   (+0,019)
#     todas (7)     0,9917 -> 1,0093   (+0,018), pior semente +0,030
#     ocr_palavra   1,0384 -> 1,0384   (0,000 — sem espúrias na prosa corrompida)
#
# O `_MINIMO_DIGITOS` em `_candidatos` é o que barra a palavra que casa por
# acidente: `Gols` e `Isso` casam o núcleo, mas têm zero dígitos reais e morrem
# no filtro. O lookbehind cobre `SOS` e `Obras`.
#
# O lookahead impede que ele termine dentro de uma palavra. Sem ele, em "de 2024
# sem outras", o `s` de "sem" — que é digitoide — entrava no número, a forma
# canônica virava `2024s` e o filtro de ano solto deixava passar: o ano virava
# citação `processo`.
_NUCLEO = rf"(?<![A-Za-zÀ-ÿ]){_DIGITOIDE}(?:{_DENTRO}*{_DIGITOIDE}){{3,}}(?![A-Za-zÀ-ÿ])"

# Sufixo de UF: /RJ, - PR, (SC), – MA.
#
# O conjunto é fechado, e não `[A-Z]{2}`, porque qualquer bigrama maiúsculo
# entrava no span: em "…REsp 1.234.567 - DE acordo com…", o `- DE` era anexado.
# `normalizacao.UFS` já é a lista validada; usá-la aqui alinha as duas camadas,
# que antes discordavam.
_UF = re.compile(rf"\s*[/(\-–—]\s*(?:{'|'.join(sorted(UFS))})\s*\)?")

_NUMERO_PROCESSO = re.compile(_NUCLEO)

# Palavras de prosa que abrem a frase antes de uma citação. Capitalizadas, elas
# casavam o ramo de sigla e o span começava dez caracteres cedo demais — medido
# em cinco casos do gabarito, com IoU entre 0,565 e 0,714 ("Também na Rcl
# 33.132/AC" onde o gabarito anota só "Rcl 33.132/AC").
#
# A lista é de exclusão e não de inclusão de propósito: enumerar as siglas
# processuais é o que a ADR 0002 refuta. Aqui enumeramos o advérbio de prosa, que
# é vocabulário fechado do português, não do domínio jurídico.
_PALAVRA_DE_PROSA = frozenset(
    """
    tambem também ademais igualmente outrossim ainda assim ja já entao então
    porem porém contudo todavia entretanto alias aliás inclusive ali aqui
    confira confiram veja vejam vejase veja-se vide cita cita-se citese citamos
    conforme segundo consoante nesse neste nessa nesta naquele naquela
    destarte portanto logo pois tal tais este esta esse essa aquele aquela
    """.split()
)

# Um elo da cadeia de prefixo, testado com fullmatch token a token. Três formas:
# sigla iniciada em maiúscula (REsp, AgR-REspe, H.C., TST-ED-E-ED-RR-), marca de
# número (nº, n°, No, n.) e um punhado de palavras minúsculas.
#
# A restrição às minúsculas é o que impede o prefixo de engolir a prosa: em
# "Ampara a pretensão o RSE nº 700…", o "o" não é conector conhecido e a cadeia
# para ali. Sem isso o span começaria em "Ampara".
#
# O ponto **dentro** da sigla é obrigatório no primeiro ramo: sem ele `H.C.`,
# `AG.REG`, `A.REsp` e `R.Esp.` falhavam o fullmatch e o prefixo era truncado —
# era a causa dos dois piores IoU do gabarito (0,519 em "AgRg no H.C. Nº 891369"
# e 0,543 em "Terceiro AG.REG na Rcl").
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

    Separa duas perguntas que o `_ELO` sozinho confundia: *tem forma de elo* e
    *é palavra de prosa*. Qualquer palavra capitalizada tem forma de sigla, então
    a forma precisa ser filtrada pelo léxico — ver `_PALAVRA_DE_PROSA`.
    """
    if not token or _ELO.fullmatch(token) is None:
        return False
    return chave_textual(token.strip(".,;:")) not in _PALAVRA_DE_PROSA


# O órgão julgador e a autoridade que antecedem a citação. Capitalizados, eles
# têm forma de sigla e a cadeia os engolia: "do Superior Tribunal de Justiça Rcl
# nº 68.244/SP" saía inteiro, com IoU 0,33 contra "Rcl nº 68.244/SP" — abaixo de
# 0,5, a citação vira FN **e** FP. Medido nos 996 acórdãos reais: cerca de 2%
# dos spans de processo carregavam um desses no prefixo. A amostra sintética não
# tem esse contexto, e o arnês não o gera.
#
# Como `_PALAVRA_DE_PROSA`, é léxico fechado do português jurídico — quem julga,
# não o que se julga —, então não contraria a ADR 0002. A sigla de tribunal
# entra só **nua** ("STF"): colada à classe, "TST-RR-79500", continua elo.
_PALAVRA_INSTITUCIONAL = frozenset(
    """
    tribunal tribunais supremo superior federal justica ministro ministra min
    relator relatora rel desembargador desembargadora juiz juiza turma corte
    plenario pleno secao camara orgao egregio colendo
    """.split()
) | frozenset(t.lower() for t in TRIBUNAIS)

# Núcleos de nome de classe por extenso. Não servem para detectar — a detecção
# ancora no número (ADR 0002) —, só para frear o descarte do complemento do nome
# do órgão: em "Relator Gilmar Mendes Reclamação nº 1", "Reclamação" fica.
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


# O maior prefixo do gabarito tem 11 palavras ("Embargos de Declaração no
# Agravo Interno no Agravo em Recurso Especial nº").
_MAXIMO_ELOS = 12

# O número da súmula, tolerante ao mesmo ruído que o núcleo de `processo` já
# atravessa. Ver a nota em `_NUMERO_DE_ARTIGO` — a assimetria era a mesma.
_NUMERO_DE_SUMULA = rf"{_DIGITOIDE}+"

# A marca de número entre a palavra e o dígito. `_NUMERO` já descreve todas as
# grafias, e **é a que a própria base canônica usa**: desde 15/09/2026 os cinco
# registros de natureza `sumula` abrem com `Súmula n. <número> do <tribunal>`.
# Sem esta alternativa a citação sumia inteira.
#
# O tribunal vem em mais formas do que "do STJ", e sem ele a súmula da cobertura
# não resolve — `base.sumula` exige o par tribunal e número — e sai `inventada`:
# a barra ou o hífen (`Súmula 83/STJ`, a grafia corrente dos acórdãos), os
# parênteses, o inciso intercalado (`Súmula 331, I, do TST`) e o nome por
# extenso. O extenso tem um grupo por tribunal (`ext_STJ`…), para a resolução
# saber qual casou sem reler o texto corrompido. "desta Corte" fica de fora: o
# tribunal depende de quem escreve.
_SIGLA_DE_TRIBUNAL = rf"(?:{'|'.join(TRIBUNAIS)})(?![A-Za-zÀ-ÿ])"
_TRIBUNAL_POR_EXTENSO = "|".join(
    rf"(?P<ext_{sigla}>{r'[ \t]+'.join(_tolerante(p) for p in nome.split())})"
    for sigla, nome in (
        ("STF", "Supremo Tribunal Federal"),
        ("STJ", "Superior Tribunal de Justiça"),
        ("TST", "Tribunal Superior do Trabalho"),
        ("TSE", "Tribunal Superior Eleitoral"),
        ("STM", "Superior Tribunal Militar"),
    )
)
_SUMULA = re.compile(
    rf"\b[S5](?:{_tolerante('úmula')}|[úuû]m\.)\s*(?P<vinculante>{_tolerante('Vinculante')})?"
    rf"\s*(?:{_NUMERO}\s*)?(?P<numero>{_NUMERO_DE_SUMULA})"
    r"(?:"
    rf"\s*[/\-–]\s*(?P<tribunal>{_SIGLA_DE_TRIBUNAL})"
    rf"|\s*\(\s*(?P<tribunal_par>{_SIGLA_DE_TRIBUNAL})\s*\)"
    rf"|(?:\s*,\s*[IVXLC]{{1,8}}\s*,)?\s*,?\s*d[oae]s?\s*"
    rf"(?:(?P<tribunal_do>{_SIGLA_DE_TRIBUNAL})|{_TRIBUNAL_POR_EXTENSO})"
    r")?",
    re.IGNORECASE,
)

_TEMA = re.compile(
    # O número atravessa o digitoide, mas não pode começar colado à palavra nem
    # terminar dentro de outra: sem os freios, `temas` casava como Tema `s`.
    rf"\b{_tolerante('Tema')}\s+(?:{_NUMERO}\s*)?"
    rf"(?P<numero>{_DIGITOIDE}+(?:\.{_DIGITOIDE}{{3}})*)(?![A-Za-zÀ-ÿ])"
    rf"(?:\s*d[ae]\s*{_tolerante('repercussão')}\s*{_tolerante('geral')})?",
    re.IGNORECASE,
)

# Diploma legal: um código nomeado, a Constituição, ou "Lei nº X/ANO". Cada
# alternativa é fechada: nada de `[\w\s]{0,40}` solto, que além de impreciso
# custa caro quando o casamento falha adiante.
#
# O ano de versão faz parte do diploma: `Código Civil de 1916` e `CPC/73` são
# diplomas revogados, fora da cobertura, com os mesmos números de artigo da versão
# vigente. Sem capturar o ano, `art. 186 do Código Civil de 1916` chegava à
# resolução como "Código Civil de" e resolvia para o art. 186 do CC/2002 — o
# erro grave da métrica. Por isso o conector solto não pode ser a última palavra
# do nome (`(?!d[aeo]\b)`): se fosse, ele engoliria o "de" e o ano ficaria fora.
_ANO_DE_VERSAO = r"(?:\s*/\s*\d{2,4}|\s+de\s+(?:19|20)\d{2})?"
#
# A palavra do nome tem inicial maiúscula — `(?-i:…)`, porque `_DISPOSITIVO` é
# IGNORECASE — ou é uma das minúsculas de `_PALAVRA_DE_CODIGO_MINUSCULA`. Antes
# qualquer palavra servia, e a prosa entrava no span: "art. 186 do Código Civil
# trata do ato" (IoU 0,65). `militar` está na lista para que o CPPM escrito em
# minúscula continue capturado inteiro e recusado.
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
_PALAVRA_DO_NOME = (
    r"(?:\s+(?:d[aeo]\s+)?(?!d[aeo]\b)"
    rf"(?:(?-i:[A-ZÀ-Ú])[\wÀ-ú]*|{_PALAVRA_DE_CODIGO_MINUSCULA}))"
)
_NOME_DE_CODIGO = rf"{_tolerante('Código')}{_PALAVRA_DO_NOME}{{0,3}}{_ANO_DE_VERSAO}"
# O número da lei também atravessa o digitoide (`Lei nº l7.463/z0I4`). O
# lookahead no fim impede que ele termine dentro de uma palavra: `O` é digitoide,
# e sem o freio "Lei Orgânica" casaria "Lei O". A exigência de dígito real fica
# em `registrar`, como no número do artigo.
_NUMERO_DE_LEI = (
    # A marca aceita espaço entre o `n` e o símbolo (`n º`), que `marca_numero`
    # produz; sem isso a citação da Lei Complementar sumia inteira.
    rf"(?:\s*[nN]\s?[.ºo°]{{0,2}})?\s*{_DIGITOIDE}(?:[.]?{_DIGITOIDE})*"
    rf"(?:\s*/\s*{_DIGITOIDE}{{2,4}})?(?![A-Za-zÀ-ÿ])"
)

# Os qualificadores de constituição que aparecem em minúscula na prosa. Os que
# identificam a CF/88 e os que a recusam entram juntos: "constituição estadual"
# precisa continuar capturado inteiro para virar `inventada`. Uma lista de
# inclusão de palavras minúsculas é segura na direção do τ — a palavra que falta
# nela fica **fora** do diploma, e aí quem decide é a maiúscula ou o ano.
_QUALIFICADOR_MINUSCULO = (
    "(?:"
    + "|".join(
        _tolerante(palavra)
        for palavra in """
        federal república federativa brasileira brasil estadual estado portuguesa
        espanhola italiana francesa alemã americana estrangeira imperial mineira
        paulista fluminense gaúcha baiana catarinense paranaense pernambucana
        """.split()
    )
    + r")(?![\wÀ-ú])"
)

_DIPLOMA = (
    r"(?:"
    rf"Lei\s+Complementar{_NUMERO_DE_LEI}"
    rf"|Lei{_NUMERO_DE_LEI}"
    rf"|{_tolerante('Consolidação')}\s+das\s+{_tolerante('Leis')}\s+d[oe]\s+{_tolerante('Trabalho')}"
    rf"|{_NOME_DE_CODIGO}"
    # O qualificador da Constituição precisa entrar no grupo `diploma`, e não
    # ficar de fora. Duas razões, medidas: (1) o gabarito anota o span inteiro
    # ("Constituição da República", "Constituição Fedcral"), e parar em
    # "Constituição" derrubava o IoU a 0,68; (2) é o qualificador que distingue
    # a Federal — a única na cobertura — da Estadual, e sem ele
    # `art. 5º da Constituição Estadual` resolvia para o art. 5º da CF, que é o
    # erro grave da métrica. Aceita "Federal", "Fedcral" (OCR), "da República"
    # e "do Estado".
    #
    # O ano entra pelo mesmo motivo que em `_NOME_DE_CODIGO`: `Constituição de
    # 1967` é outra constituição. A primeira alternativa existe porque o "de" do
    # conector engoliria o "de" do ano, e o casamento terminaria antes dele.
    #
    # A palavra depois de "Constituição" só entra se tiver **forma de
    # qualificador**: inicial maiúscula — o `(?-i:…)` desliga o IGNORECASE de
    # `_DISPOSITIVO`, sem o que `[A-Z]` casava minúscula — ou uma das palavras
    # minúsculas de `_QUALIFICADOR_MINUSCULO`. Antes, o verbo da frase entrava no
    # diploma ("art. 5º da Constituição garante") e reprovava o qualificador da
    # CF: `real` virava `inventada`. Medido nos 996 acórdãos, eram 98 citações.
    rf"|{_tolerante('Constituição')}(?:\s+de\s+(?:19|20)\d{{2}}"
    rf"|(?:\s+d[aeo]\s+)?(?:\s*(?:(?-i:[A-ZÀ-Ú])[\wÀ-ú]+|{_QUALIFICADOR_MINUSCULO}))?"
    rf"{_ANO_DE_VERSAO})"
    r"|Carta\s+Magna"
    # `Decreto-Lei nº 5.452/1943` é **como a base canônica nomeia a CLT** na
    # primeira linha autodeclarada dos registros `dispositivo`, e `LC` é a sigla
    # corrente da Lei Complementar. Sem as duas alternativas a citação sumia — e
    # os marcadores "lc 64" em `resolucao.DIPLOMAS` eram inalcançáveis.
    rf"|Decreto[-‐\s]*Lei{_NUMERO_DE_LEI}"
    rf"|LC{_NUMERO_DE_LEI}"
    # `CPC/73` e `CC/16` são os códigos revogados; o ano vai junto para a
    # resolução decidir. `CF/88` é o caso particular que já existia.
    rf"|(?:CPC|CPP|CPM|CLT|CDC|CF|CC){_ANO_DE_VERSAO}"
    r")"
)

# Incisos, parágrafos e alíneas entre o número do artigo e o diploma. Cada
# repetição **precisa** consumir uma vírgula: sem isso o grupo casa o vazio e o
# motor testa todas as partições da prosa seguinte — era 41 s por documento.
#
# O romano vai até **oito** caracteres, e não cinco: `LXXVIII` tem sete, e com o
# limite antigo `art. 5º, LXXVIII, da Constituição Federal` não casava e a
# citação sumia. Medido nos 996 acórdãos reais da base, romano com seis ou mais
# caracteres aparece em 49 deles.
#
# `caput` e o inciso no plural entram pelo mesmo motivo — medindo a mesma base,
# `caput` aparece em **424 de 996** e `inciso(s)` em 497. A conjunção entre dois
# romanos ("incisos I e II") aparece em 109. Nenhuma das três é forma exótica; a
# amostra sintética é que não as produziu.
_ROMANO = r"[IVXLC]{1,8}"
#
# `parágrafo único`, a abreviação `inc.` e o `caput` coordenado com inciso
# (`caput e inciso LV`, `caput, e inciso II`) são formas correntes que faziam a
# citação sumir inteira. Continuam dentro da mesma regra: toda alternativa
# consome texto literal, e cada repetição começa por vírgula.
_INCISO = rf"(?:incisos?|incs?\.)\s+{_ROMANO}(?:\s+e\s+{_ROMANO})?"
_QUALIFICADORES = (
    rf"(?:\s*,\s*(?:§+\s*{_DIGITOIDE}+[ºo°]?(?:\s*-\s*[A-Z])?(?:\s+e\s+\d+[ºo°]?)?"
    rf"|(?:e\s+)?{_INCISO}"
    rf"|par[áa]grafo\s+(?:[úu]nico|{_DIGITOIDE}+[ºo°]?)|§\s*[úu]nico"
    rf"|al[íi]nea\s+[a-z]\)?|caput(?:\s+e\s+{_INCISO})?|{_ROMANO}(?:\s+e\s+{_ROMANO})?"
    r"|['\"]?[a-z]['\"]?\)?))"
    r"{0,5}"
)

# O número do artigo pode ter separador de milhar: `art. 1.134`, `art. 1.105`.
# Ler só `\d+` para no primeiro ponto e o casamento inteiro falha.
#
# **Os dígitos são digitoides**, pela mesma razão que `_NUCLEO` — e esta era a
# maior perda de recall do pipeline. O checkpoint 06 ensinou a família
# `processo` a atravessar a letra que o OCR põe no lugar do dígito; as famílias
# `dispositivo` e `sumula` ficaram exigindo dígito puro. Medindo os corpora de
# `data/perturbado/`, a assimetria custava mais que o defeito já corrigido:
#
#     classe de ruído        disp/súm/tema   processo
#     ocr_numero (5 sem.)         40            22
#     ocr_palavra (5 sem.)        17            22
#
# `_corrigir_ocr` repara todos esses casos (`I86`→`186`, `B96`→`896`); era a
# detecção que nunca lhe entregava o trecho.
#
# O contrapeso é `_tem_digito_real`, exigido em `registrar`: sem ele `art Iss`
# casaria, porque `I` e `s` são digitoides e o número sairia do nada. É a mesma
# política de `_MINIMO_DIGITOS` na família `processo`.
#
# O separador de milhar admite **uma** quebra de linha logo depois do ponto
# (`art. 1.\n105`): o nível 2 parte identificadores no meio, e o número do
# artigo não é exceção. Medido: era a citação que `quebra_identificador` perdia
# na quinta semente, desde o checkpoint 06.
_NUMERO_DE_ARTIGO = rf"{_DIGITOIDE}+(?:\.[ \t]*\n?[ \t]*{_DIGITOIDE}{{3}})*(?:[-ºo°][\w]{{0,3}})?"

_DISPOSITIVO = re.compile(
    rf"\b{_tolerante('art')}(?:{_tolerante('igo')}|\.|\b)\s*\n?\s*(?P<artigo>{_NUMERO_DE_ARTIGO})"
    rf"{_QUALIFICADORES}"
    rf"\s*,?\s*\n?\s*d[oae]s?\s+(?P<diploma>{_DIPLOMA})",
    re.IGNORECASE,
)

# A família `vaga`: tribunal + ano + relator, hoje a totalidade das `incompleta`.
# O relator é a âncora — é o que separa este padrão de uma menção solta a ano.
# `d[eoc]` e não `d[eo]`: o nível 2 corrompe letras isoladas, e a amostra traz
# o conector "de" aparece corrompido como "dc" (e→c) na amostra.
#
# A palavra-chave é tolerante ao ruído de letra — `rclatoria`, `relatorla` e
# `pcla` sumiam sob `ocr_palavra`: era a causa das 20 `incompleta` não detectadas
# medidas no checkpoint 06, o maior bloco daquela classe. Ver `_tolerante`.
_RELATOR = (
    rf"(?:[Rr]{_tolerante('el')}(?:{_tolerante('at')}[0oaã]r[ilaã]?[aã]?)?\.?\s*"
    rf"(?:Min\.?|{_tolerante('Ministr')}[ao])?\.?"
    rf"|{_tolerante('relatoria')}\s+d[eoc])"
)

#
# A cabeça é a classe ou o genérico ("julgado", "acórdão", "precedente"), com
# até três palavras a mais para as classes por extenso ("Recurso em Habeas
# Corpus"). Ela precisa ser seguida de perto pelo tribunal ou pelo ano — é o que
# impede a expressão de começar em "Cita-se" na frase "Cita-se o julgado do STF".
_CABECA_VAGA = (
    rf"(?:{_tolerante('julgad')}[oaã0]|{_tolerante('acórdão')}|{_tolerante('precedente')}"
    rf"|{_tolerante('decisão')}"
    r"|[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}(?:\s+(?:em\s+|de\s+|do\s+|da\s+)?[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}){0,3}"
    r")"
)

_NOME_PROPRIO = r"[A-ZÀ-Ú][\wÀ-ú.']*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ú][\wÀ-ú.']*){0,4}"

# O ano, tolerante ao ruído do nível 2. Esta é a única quantia numérica da
# família `vaga`, então exigir quatro dígitos limpos apaga a citação inteira
# quando o OCR troca um deles ou a quebra de linha cai no meio. Medido: era a
# causa de 25 das 32 `incompleta` sumirem sob ruído no número.
_ENTRE_DIGITOS = r"[ \t]*\n?[ \t]*"
_DIGITO_OU_OCR = rf"[\d{''.join(sorted(set(OCR_PARA_DIGITO)))}]"
_ANO_TOLERANTE = (
    rf"[12lIZz]{_ENTRE_DIGITOS}[90OoGgqb]{_ENTRE_DIGITOS}"
    rf"{_DIGITO_OU_OCR}{_ENTRE_DIGITOS}{_DIGITO_OU_OCR}"
)

_VAGA = re.compile(
    rf"{_CABECA_VAGA}"
    rf"(?:\s*,?\s*d[oa]\s+(?:{'|'.join(TRIBUNAIS)}))?"
    rf"\s*,?\s*(?:{_tolerante('proferid')}[oaã0]|{_tolerante('julgad')}[oaã0])?\s*(?:d[ec]|[ec]rn|[ec]m)\s*\n?\s*"
    rf"{_ANO_TOLERANTE}"
    r"[^.]{0,30}?"
    rf"{_RELATOR}\s*{_NOME_PROPRIO}",
)

# ---------------------------------------------------------------------------
# `vaga` por contagem de constituintes
#
# `_VAGA` acima exige cabeça -> tribunal -> ano -> relator **nessa ordem**, que é
# a forma única das 32 `incompleta` do gabarito. Medindo oito reordenações
# plausíveis, sete não eram detectadas — e o próprio `docs/investigacao.md`
# ressalva que "nada garante que o cego use as mesmas frases". A classe de
# perturbação `ordem_incompleta` do arnês mede exatamente isso.
#
# O caminho abaixo é o que `docs/referencias.md` lista como usável agora sem
# custo de envelope (Harašta et al., 2020): reconhecer **constituintes** em vez
# da referência inteira. O critério deixa de ser o casamento de uma frase e vira
# uma contagem — relator e ano presentes, nenhum número de processo —, o que
# vale em qualquer ordem.
#
# Roda **depois** de `_VAGA` e só onde ela não casou: a ordem canônica continua
# produzindo o span que o gabarito anota, e esta é a rede para as demais.
# ---------------------------------------------------------------------------

# A sentença é a janela. `incompleta` é uma referência dentro de uma frase, e o
# ponto final é a fronteira natural — usá-la evita juntar duas citações vizinhas.
#
# O ponto de abreviação **não** encerra a sentença: `[^.!?]+` partia
# "Rel. Min. Carlos Alberto" em três pedaços e nenhum tinha relator e ano juntos.
# Fim de sentença é ponto seguido de espaço e maiúscula, ou de quebra de linha —
# não o ponto colado a uma abreviação curta ("Rel.", "Min.", "n.").
_FIM_DE_SENTENCA = re.compile(r"(?<!\b[A-Z])(?<!\b[A-Za-z]{2})(?<!\b[A-Za-z]{3})[.!?](?=\s|$)")

# O relator, em formas que `_RELATOR` não cobre porque `_VAGA` não precisava
# delas: "relatado por X", "da lavra do Ministro X", e o "Ministro X" sem o
# "Rel." na frente. É a âncora da família — sem relator nomeado não há citação
# `incompleta` — então vale reconhecê-la em qualquer das grafias correntes.
_RELATOR_NOMEADO = re.compile(
    r"(?:"
    rf"{_RELATOR}"
    rf"|{_tolerante('relatad')}[oaã0]\s+(?:p[0o]r|p[ec]l[oaã0])"
    rf"|{_tolerante('lavra')}\s+d[eoac]s?"
    rf"|Min\.?|{_tolerante('Ministr')}[ao]s?|Des(?:embargador)?[ao]?\.?"
    r")"
    rf"\s*(?:d[eoa]s?\s+)?(?:Min\.?|Ministr[ao])?\.?\s*{_NOME_PROPRIO}"
)

# "no ano de 2019", "em 2019", "de 2019", ou o ano solto na enumeração
# "STF, 2019, Rel. Min. X".
#
# O `.` do lookahead precisa ser só o que **estrutura um número** (`2019.7.00`),
# nunca o ponto final da frase: `(?![\d./-])` rejeitava "de 2019." e a citação
# desaparecia quando o ano fechava a sentença.
_ANO_ISOLADO = re.compile(rf"(?<![\d./-]){_ANO_TOLERANTE}(?![-/]|\.?\d)")

_MENCAO_TRIBUNAL = re.compile(rf"\b(?:{'|'.join(TRIBUNAIS)})\b")

# A cabeça que abre a referência, quando presente. Só serve para estender o span
# à esquerda até o substantivo que nomeia a decisão — não é exigida.
_CABECA_ISOLADA = re.compile(
    rf"\b(?:{_tolerante('julgad')}[oaã0]|{_tolerante('acórdão')}|{_tolerante('precedente')}"
    rf"|{_tolerante('decisão')}|{_tolerante('aresto')}"
    r"|voto|jurisprud[êe]ncia|entendimento|prec)[\wÀ-ú]*",
    re.IGNORECASE,
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


def _digitos_suficientes(numero: str, corpo: str, inicio: int) -> bool:
    """O núcleo tem dígitos bastantes para ser número de processo?

    Com quatro dígitos **reais**, sim — é a regra de `_MINIMO_DIGITOS`. Abaixo
    disso, o ruído de OCR pode ter comido os demais: sob `ocr_numero`, um número
    de cinco dígitos fica com três (`Rcl 4B.71B/RS`) e a citação sumia, embora o
    reparo devolva `48718`. Era o maior bloco das perdas restantes no arnês.

    A regra afrouxada tem dois freios, e cada um barra uma forma de falso
    positivo que o afrouxamento abriria:

    * o número **reparado** precisa ter quatro dígitos, e ao menos um real — o
      reparo só converte letra colada a dígito, então `BO 12` não chega lá;
    * o prefixo precisa nomear uma **classe processual**: um elo com letra
      maiúscula imediatamente antes do número, que é o que `_expandir_prefixo`
      já reconhece. Sem classe, `a quantia de 4B.71B` não é citação.
    """
    if _digitos(numero) >= _MINIMO_DIGITOS:
        return True
    # Dois reais, e não um. Medido nos 996 acórdãos reais: os únicos núcleos que
    # passam os outros dois freios com menos de três dígitos reais são numeração
    # de seção (`III.1`, `III.3`) e nome em caixa alta (`3SSIL`) — os três com
    # **um** dígito real. Com dois, nenhum texto real passa, e o ruído a taxa
    # 0,30 recupera `RHC nº 7s.soB/RS` e `Recl. n° 7G.B4B/ BA`, que eram as
    # únicas citações que o NER de pesos abertos achava e a regra não (ADR 0004).
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
    """O número da lei, quando o diploma é citado por número, tem dígito real?

    `_NUMERO_DE_LEI` aceita digitoide pelo mesmo motivo que o número do artigo, e
    precisa do mesmo contrapeso: sem ele "Lei Os" seria "Lei 05".
    """
    numero = re.search(rf"{_DIGITOIDE}[{_DIGITOIDE[1:-1]}./]*$", diploma or "")
    if numero is None or not re.match(r"(?i)\s*(?:lei|lc|decreto)", diploma):
        return True
    return _digitos(numero.group()) >= 1


def _tem_digito_real(numero: str | None) -> bool:
    """O número tem ao menos um dígito que não veio de digitoide?

    É o contrapeso de `_NUMERO_DE_ARTIGO` e `_NUMERO_DE_SUMULA` aceitarem letra
    no lugar de dígito: sem ele `art Iss` casaria — `I` e `s` são digitoides — e
    o artigo sairia do nada. Mesma política de `_MINIMO_DIGITOS` na família
    `processo`, com o limiar em um porque artigo e súmula têm um dígito só
    ("art. 5º", "Súmula 7").
    """
    return bool(numero) and _digitos(numero) >= 1


# Um ano solto não é número de processo. Sem este corte, "de 2025" e "em 2023"
# viram citação: eram 40% dos falsos positivos medidos.
_ANO_SOLTO = re.compile(r"^(?:19|20)\d{2}$")

# `fls. <n>/<n>` — referência de página, distrator documentado.
_PAGINAS = re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$")

# `<n>/<ano>` — protocolo ou lei. Número de processo não termina
# em ano: no padrão CNJ o ano fica no meio, e no número único do STJ, na frente.
_TERMINA_EM_ANO = re.compile(r"^\d{1,5}(?:\.\d{3})*\s*/\s*(?:19|20)\d{2}$")

# Centavos logo **depois** do número: `1.500.000,00`.
#
# O sinal de quantia não pode ser a forma do número — `1.500.000` é indistinguível
# de `1.234.567`, que é número de REsp legítimo. O que denuncia a quantia é a
# vírgula seguida de exatamente dois dígitos, e ela cai fora do casamento porque
# a vírgula não está em `_DENTRO`. Por isso este filtro olha o texto à direita,
# não o número.
_CENTAVOS = re.compile(r"^,\d{2}(?!\d)")

# Data em `dd/mm/aaaa`. `_TERMINA_EM_ANO` exige que o número **inteiro** seja
# `<n>/<ano>`, então a data tem uma barra a mais e escapava dele: medido,
# "O período de 01/01/2020 a 31/12/2021" produzia dois spans `processo`.
#
# A amostra de desenvolvimento não tem nenhuma data nesse formato — contei zero
# nos 26 documentos —, mas 200 de 200 acórdãos reais da base têm, num total de
# 5.635 ocorrências. A ausência é artefato do gerador sintético, não propriedade
# do domínio, e "publicado em <data>" é frase corrente em peça jurídica.
#
# O `$` final fica de fora de propósito: o núcleo atravessa espaço e engole a
# hora que vem depois da data ("05/08/2021 14:30" chega aqui como
# `05/08/2021 14`). Número de processo nunca começa por `dd/mm/aaaa`, então
# casar só o começo é seguro. Medido nos acórdãos reais, na linha de assinatura
# eletrônica.
_DATA = re.compile(r"^\d{1,2}/\d{1,2}/(?:\d{2}|(?:19|20)\d{2})(?!\d)")

# Rótulos que marcam o número seguinte como distrator, não como citação. Os seis
# primeiros são os distratores que o material do desafio nomeia; os demais são
# identificadores civis que aparecem em qualquer peça e que o gerador sintético
# da amostra não produziu.
_ROTULO_DISTRATOR = re.compile(
    # A fronteira de palavra na frente é obrigatória desde que a marca de número
    # passou a ser aceita no fim: sem ela `tel` casava dentro de "tutela nº", e
    # a referência a outro processo em "suspensão de tutela nº <número CNJ>"
    # sumia. Medido nos 996 acórdãos reais. `R$` fica de fora da fronteira
    # porque começa em letra mas termina em símbolo.
    r"(?:\b(?:fls?|folhas?|protocolo|CPF|CNPJ|valor\s+da\s+causa"
    r"|telefone|tel|fone|celular|RG|CEP|PIS|PASEP|CNH|NIT"
    r"|matr[íi]cula|guia|precat[óo]rio|ag[êe]ncia|conta"
    # O DDD entre parênteses separa o rótulo do número e quebrava a adjacência:
    # "Telefone (11) 98765-4321" escapava do filtro.
    r"|OAB\s*/?\s*[A-Z]{0,2})|R\$)\s*[.:]?\s*(?:\(\s*\d{2}\s*\)\s*)?"
    # Palavras curtas de ligação entre o rótulo e o número. A adjacência estrita
    # deixava passar "Inscrito na OAB sob o nº 123.456/SP", que é a forma
    # corrente em peça jurídica — o rótulo está lá, só não colado. Duas palavras
    # bastam para "sob o"; a marca de número vem por último e é opcional.
    r"(?:\s*(?:sob|sob\s+o|[oa]s?|n[oa]s?|d[oae]s?|em|é)\b){0,2}\s*"
    rf"(?:{_NUMERO}\s*)?$",
    re.IGNORECASE,
)


def _forma_canonica(numero: str) -> str:
    """O número sem ruído de superfície, mas com a pontuação que o estrutura.

    Existe porque os filtros acima descrevem **formas**, e forma não sobrevive ao
    nível 2 sem normalização. Medido: um ano partido por quebra de linha escapava
    de ``_ANO_SOLTO`` e virava citação; uma referência de página com ``\\n`` no
    meio escapava de ``_PAGINAS``. Os dois viram falso positivo, e o segundo é um
    distrator que o material do desafio nomeia.

    Mantém ``/`` e ``.`` porque ``_PAGINAS`` e ``_TERMINA_EM_ANO`` dependem
    deles; tira espaço e quebra de linha, e desfaz a troca de dígito por letra.
    """
    return re.sub(r"[\s]+", "", _corrigir_ocr(numero))


# A janela de rótulo precisa caber o rótulo mais longo com folga para o ruído do
# nível 2: "valor da causa" já tem 14 caracteres, e uma corrupção que insira
# caractere (`m` -> `rn`) estoura os 24 originais.
_JANELA_ROTULO = 40


def _e_numero_de_processo(numero: str, antes: str, depois: str = "") -> bool:
    """Filtra o que tem forma de número mas não identifica processo.

    ``depois`` é o texto à direita do casamento, e só serve ao filtro de centavos
    — o único sinal que não está no número nem no que vem antes dele.
    """
    compacto = _forma_canonica(numero)
    if _ANO_SOLTO.match(compacto) or _PAGINAS.match(compacto):
        return False
    if _TERMINA_EM_ANO.match(compacto) or _DATA.match(compacto):
        return False
    # A data com a hora colada: a forma canônica tira o espaço, e `05/08/2021 14`
    # vira `05/08/202114`, que já não é data. O começo cru do casamento ainda é.
    if _DATA.match(numero.lstrip()):
        return False
    if _CENTAVOS.match(depois):
        return False
    return not _ROTULO_DISTRATOR.search(antes[-_JANELA_ROTULO:])


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
    # Os elos aceitos, da direita para a esquerda, como (início, token).
    aceitos: list[tuple[int, str]] = []
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
        if _e_institucional(token):
            # O órgão ou a autoridade que proferiu a decisão não faz parte da
            # citação, e o que vem logo à direita dele é o complemento do nome
            # ("Corte Especial", "Ministro Gilmar Mendes") — sai junto.
            while aceitos and _e_palavra_de_nome(aceitos[-1][1]):
                aceitos.pop()
            break
        if token == "e" and aceitos and aceitos[-1][1] in _CONTRACAO:
            # "do Recurso Extraordinário e da Rcl nº 1" coordena duas citações;
            # o nome de classe usa a preposição nua ("Liminar e de Sentença").
            break
        if not _e_elo(token) and not _elo_corrompido(corpo, recuo, token):
            break
        aceitos.append((recuo, token))
        posicao = recuo
    # O conector é elo **entre** siglas ("AgInt no REsp"), nunca a borda: o
    # "no" de "decidido no REsp" é a prosa que introduz a citação. Medido no
    # dev: 41 spans abriam assim, e o IoU do 5º percentil subiu de 0,854 para 1.
    while aceitos and _CONECTOR_DE_BORDA.fullmatch(aceitos[-1][1]):
        aceitos.pop()
    return aceitos[-1][0] if aceitos else inicio


# Os pedaços da marca de número separados por espaço: `n º`, `N °`. O arnês
# `marca_numero` produz essa grafia, e o `º` sozinho não tinha forma de elo — a
# cadeia parava nele e o prefixo inteiro ficava de fora.
#
# Só os símbolos, nunca `o` ou `O` sozinhos: esses são o artigo "o" da prosa
# ("Ampara a pretensão o REsp…"), e aceitá-los levava a cadeia para dentro da
# frase. O `n` sozinho também fica de fora pelo mesmo motivo; ele entra pelo
# `_ELO`, que já o aceita colado ao símbolo.
_PEDACO_DE_MARCA = re.compile(r"[º°]")


def _elo_corrompido(corpo: str, inicio: int, token: str) -> bool:
    """O token é um elo que o ruído de OCR desfigurou?

    Duas formas, medidas como causa dos `(espúria) → real` restantes no arnês:

    * a marca de número partida por espaço (`n º`);
    * a sigla cuja maiúscula o OCR trocou por minúscula — `E`→`c` em
      `cspecial`, `C`→`e` em `eorpus`. Desfeita a troca, ela volta a ter forma
      de elo.

    O segundo caso só vale **entre elos**: a palavra à esquerda também precisa
    ser elo. Uma minúscula de prosa ("cita especial REsp") continua parando a
    cadeia, porque o que vem antes dela é prosa. É o que mantém a exclusão de
    `_PALAVRA_DE_PROSA` funcionando.
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


# A inversa de `CONFUSOES_DE_LETRA` para as trocas que tiram a maiúscula: o OCR
# lê `E` como `c` e `C` como `e`. Só as de uma letra entram.
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


def _tem_numero_de_processo(trecho: str) -> bool:
    """Há na janela um número que a base consegue resolver?

    É o que tira uma citação da família `vaga`: com número, ela é `real` ou
    `inventada`, e quem decide é a cardinalidade da consulta. Sem número, não há
    o que consultar — é `incompleta` por construção.
    """
    return any(
        _digitos(m.group()) >= _MINIMO_DIGITOS
        and _e_numero_de_processo(m.group(), trecho[: m.start()], trecho[m.end() :])
        for m in _NUMERO_PROCESSO.finditer(trecho)
    )


def _vagas_por_constituinte(corpo: str) -> list[tuple[int, int]]:
    """Spans de `vaga` achados por contagem de constituintes, em qualquer ordem.

    O critério, por sentença: há **relator nomeado** e **ano**, e **não** há
    número de processo. Os dois primeiros são o que identifica uma decisão
    concreta; o terceiro é o que a torna inverificável — com número, a citação é
    `real` ou `inventada`, e quem decide é a base.

    O span vai do primeiro ao último constituinte, estendido à esquerda até a
    cabeça ("julgado", "acórdão", "precedente") quando ela abre a referência.
    """
    spans: list[tuple[int, int]] = []
    for inicio_sent, fim_sent in _sentencas(corpo):
        trecho = corpo[inicio_sent:fim_sent]
        if len(trecho.strip()) < 12:
            continue

        relator = _RELATOR_NOMEADO.search(trecho)
        if relator is None:
            continue
        # O ano precisa de **dois dígitos reais**. `_ANO_TOLERANTE` aceita
        # digitoide em toda posição — é o que faz a citação sobreviver ao nível 2
        # —, mas aqui, onde nenhum outro constituinte é numérico, isso deixava
        # palavras de prosa valerem como ano: `logo`, `lobo` e `zoos` satisfazem
        # a classe inteira. Com um "Ministro <Nome>" na mesma frase, a prosa
        # virava `incompleta`. Medido: 4 spans espúrios em 80 acórdãos reais.
        #
        # Dois e não quatro porque o ruído corrompe: `2Ol9` tem dois reais e é
        # ano legítimo. É o mesmo desenho de `_MINIMO_DIGITOS` — exigir dígito
        # real onde a classe tolerante abriria a porta para a prosa.
        anos = [m for m in _ANO_ISOLADO.finditer(trecho) if _digitos(m.group()) >= 2]
        if not anos:
            continue

        # Número de processo na sentença tira a citação desta família: ela passa
        # a ser resolvível contra a base, e quem decide a classe é a cardinalidade.
        if _tem_numero_de_processo(trecho):
            continue

        inicio = min(relator.start(), anos[0].start())
        fim = max(relator.end(), anos[-1].end())

        # O tribunal, quando nomeado, faz parte da referência.
        tribunal = _MENCAO_TRIBUNAL.search(trecho)
        if tribunal is not None:
            inicio = min(inicio, tribunal.start())
            fim = max(fim, tribunal.end())

        # Estende à esquerda até a cabeça, se ela abrir a referência de perto.
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
        # Os grupos que a expressão já isolou seguem junto: reparsear o trecho na
        # resolução erraria onde a detecção acertou — `5úmula 211` tem dois
        # números e só um é o da súmula.
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
        if not _numero_de_lei_plausivel(m.group("diploma")):
            continue
        registrar(m, "dispositivo", "lei")
    vagas: list[tuple[int, int]] = []
    for m in _VAGA.finditer(corpo):
        # Um número de processo **imediatamente à esquerda** do casamento torna a
        # citação resolvível, e `vaga` tem precedência sobre `processo`: em
        # "REsp 1.234.567/SP, de 2019, Rel. Min. Fulano" a expressão casa a partir
        # do `SP` — o número fica fora do próprio casamento — e roubaria o span da
        # família que sabe resolvê-lo. Classe errada custa duas vezes na métrica.
        #
        # A janela é curta de propósito. Olhar a sentença inteira derrubava cinco
        # `incompleta` do gabarito que apenas dividem a frase com outra citação
        # numerada: medido, o score caía de 1,0988 para 1,0518. O que desqualifica
        # a família é o número **desta** citação, não o de uma vizinha.
        if _tem_numero_de_processo(corpo[max(0, m.start() - 24) : m.start()]):
            continue
        registrar(m, "vaga", "jurisprudencia")
        vagas.append((m.start(), m.end()))

    # A contagem de constituintes é a rede para as ordens que `_VAGA` não prevê.
    # Só entra onde a forma canônica não casou — assim o span que o gabarito
    # anota continua vindo da expressão, que é mais justa na borda.
    for inicio_vaga, fim_vaga in _vagas_por_constituinte(corpo):
        if any(not (fim_vaga <= i or inicio_vaga >= f) for i, f in vagas):
            continue
        inicio, fim = _aparar(texto, inicio_corpo + inicio_vaga, inicio_corpo + fim_vaga)
        if fim > inicio:
            achados.append(Achado(inicio, fim, texto[inicio:fim], "vaga", "jurisprudencia"))
            vagas.append((inicio_vaga, fim_vaga))

    for m in _NUMERO_PROCESSO.finditer(corpo):
        if not _digitos_suficientes(m.group(), corpo, m.start()):
            continue
        if not _e_numero_de_processo(m.group(), corpo[: m.start()], corpo[m.end() :]):
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
