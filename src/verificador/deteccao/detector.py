"""Detecção dos spans de citação no texto do parecer.

Quem não entrega o span de uma citação não consegue classificá-la, e isso conta
como erro de recall. O alinhamento com o gabarito é por sobreposição com
IoU ≥ 0,5, então a borda exata não precisa ser perfeita — mas a citação inteira
precisa aparecer.

A organização é por família, porque a família determina contra o quê a citação
é resolvida:

``processo``     sigla ou classe processual + número (``AgInt no REsp 1.234.567/PR``)
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

# "nº" em todas as grafias que a amostra traz, inclusive as de OCR (No, N°, n.).
_NUMERO = r"(?:n\s*[.ºo°]{0,2}|N\s*[.ºO°]{0,2})"

# Pontuação que pode aparecer dentro de um número de processo, incluindo a
# quebra de linha e o espaço não-quebrável (`421-37. 2012` vem com \xa0).
#
# **No máximo uma quebra de linha.** Com `\s` solto o núcleo atravessava o fim do
# parágrafo e engolia o título da seção seguinte: em
# `Ag. Int. No 7000123-4520197000000.\n\nI — DA COMPETÊNCIA` o span ia até o `I`
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

    Aceita também o dígito que o OCR põe no lugar da letra — `Súmu1a`, `Re1.`,
    `Con5tituição`, `julgad0` —, que o nível 2 da amostra mostra na prosa
    ("5úmula", "C0NTROVÉRSIA") e que apagava a citação inteira. O dígito vem da
    inversa de `OCR_PARA_DIGITO`, a mesma tabela do reparo do número.
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


# O núcleo numérico: admite letra de OCR no lugar de um dígito, para não cortar
# a citação ao meio (`12345l7`).
#
# **O primeiro caractere também pode ser digitoide.** Ele era `\d` literal, e o
# OCR corrompe a primeira posição como qualquer outra: em `REsp l.234.567/PR` o
# núcleo começava no `5` e devolvia `234567`, um número *diferente*, que não
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
# 12.345/AC" onde o gabarito anota só "Rcl 12.345/AC").
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
# era a causa dos dois piores IoU do gabarito (0,519 em "AgRg no H.C. Nº 123456"
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
# nº 12.345/SP" saía inteiro, com IoU 0,33 contra "Rcl nº 12.345/SP" — abaixo de
# 0,5, a citação vira FN **e** FP. Medido nos 996 acórdãos reais: cerca de 2%
# dos spans de processo carregavam um desses no prefixo. A amostra sintética não
# tem esse contexto, e o arnês não o gera.
#
# Como `_PALAVRA_DE_PROSA`, é léxico fechado do português jurídico — quem julga,
# não o que se julga —, então não contraria a ADR 0002. A sigla de tribunal
# entra só **nua** ("STF"): colada à classe, "TST-RR-79500", continua elo.
#
# Só substantivos. "Federal" ficou de fora de propósito: é adjetivo, aparece
# também no nome da classe ("Intervenção Federal nº …"), e ali cortava o span
# em "nº …". Nos órgãos o substantivo vem antes ("Tribunal Federal", "Justiça
# Federal") e é ele que para a cadeia; o "Federal" à direita sai como nome.
_PALAVRA_INSTITUCIONAL = frozenset(
    """
    tribunal tribunais supremo superior justica ministro ministra min
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
#
# A sigla aceita o `S` lido como `5` ("5TJ", "T5T"), a troca que o nível 2 da
# amostra faz com a letra maiúscula ("DO5", "PIRE5"). Sem isso a súmula perdia o
# tribunal e saía `inventada`, e a `vaga` começava no meio da sigla.
# `sigla_do_tribunal` devolve a forma limpa.
_SIGLA_DE_TRIBUNAL = (
    r"(?:(?-i:[S5]TF|[S5]TJ|T[S5]T|T[S5]E|[S5]TM)|STF|STJ|TST|TSE|STM)(?![A-Za-zÀ-ÿ\d])"
)

# O conector curto antes do tribunal ou do diploma, com o ruído do nível 2:
# "d0", "dc", "dã" no lugar de "do", "de", "da".
_CONECTOR = r"d[oaeã0c]s?"

# As palavras do nome atravessam uma quebra de linha, como o resto da citação: o
# texto do gerador é quebrado em ~100 colunas, e "Súmula 345 do Superior
# Tribunal\nde Justiça" perdia o tribunal inteiro — o span parava em "Súmula
# 345" (IoU 0,24 contra o gabarito) e a súmula da cobertura saía `inventada`.
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

# O separador dos nomes longos — o do diploma citado pelo nome e o do tribunal
# regional da súmula —, com a mesma quebra de linha de `_ENTRE_PALAVRAS_DO_NOME`.
# A quebra é um grupo à parte, e não um `\n?` entre dois `[ \t]*`: com essa
# ambiguidade, um trecho longo de espaços depois de "art. 5º da Lei" custava
# tempo quadrático em cada um dos nomes que começam por "Lei".
_NAME_SEPARATOR = r"(?:[ \t\xa0]+(?:\n[ \t\xa0]*)?|\n[ \t\xa0]*)"


def _tolerant_name(nome: str) -> str:
    """As palavras de um nome longo com o ruído do nível 2, como as âncoras.

    A palavra passa por `_tolerante` ("Lci", "Execucão", "Rcgião"). O conector
    aceita o ruído e a troca entre si, como o de `_NOME_DE_CODIGO` ("dc", "d0";
    "Normas de Direito" ao lado de "Normas do Direito"), e o plural com o `s`
    lido como `5` ("da5").
    """
    return _NAME_SEPARATOR.join(
        r"d[aeoc0ã][s5]?" if palavra in ("de", "da", "do", "das", "dos") else _tolerante(palavra)
        for palavra in nome.split()
    )


# O tribunal da súmula fora dos cinco superiores: TRF1 a TRF6, TRT1 a TRT24, TJ,
# TRE e TJM com a UF, e a TNU. Sem ele, "Súmula 7 do TJSP" saía com o span
# "Súmula 7" e sem tribunal — `inventada` mesmo que a base tivesse o registro —,
# e com o nome por extenso ("Súmula 7 do Tribunal de Justiça de São Paulo") o IoU
# contra o span da citação caía a 0,18, abaixo do corte: FN e FP de uma vez. A
# base do conjunto de avaliação é nova e pode ter súmula de tribunal regional.
#
# Fica num padrão só da súmula: `_SIGLA_DE_TRIBUNAL` é também a âncora de `tema`
# e `vaga`, que continuam nos cinco superiores.
#
# A sigla é a maiúscula, fora do IGNORECASE de `_SUMULA`: em caixa baixa ela
# seria prosa. O separador entre a sigla e a UF ou a região vem nas grafias dos
# acórdãos da base: "TRE/SP" (a forma mais comum do regional eleitoral, 170
# ocorrências), "TJ-MS", "TJSP", "TRF-1", "TRT/<n>ª Região", "TRT da <n>a Região",
# "TRT <n>". Entre a sigla e a UF não cabe espaço solto: em caixa alta, "SÚMULA 7
# DO TJ SE APLICA" leria "TJ SE" como o tribunal de Sergipe.
#
# A UF é o conjunto fechado de `UFS`, mais o `DFT` do TJDFT, tolerante ao ruído
# como as palavras-chave ("TJ5P"). A região é o número, ou o ordinal por extenso
# ("da Sexta Região"), a forma dos cabeçalhos de peça. Aceitar a região que não
# existe ("TRF9") é de propósito: ela não resolve e sai `inventada`, que é a
# resposta certa, com o span inteiro.
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
# O separador entre a sigla e a UF ou a região: nada, espaço, ou um sinal com
# espaço opcional dos dois lados. Cada forma tem um caminho só — com `[ \t]*`
# dos dois lados de um sinal opcional, "TRF" seguido de um trecho longo de
# espaços custava tempo quadrático.
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

# O regional pelo nome por extenso, que a prosa usa tanto quanto a sigla: "Tribunal
# de Justiça de São Paulo", "Tribunal Regional Federal da 1ª Região", "Turma
# Nacional de Uniformização". Só com o que identifica o tribunal — o estado ou a
# região: "Súmula 21 do Tribunal Regional" não diz qual, e fica de fora como antes.
#
# Do nome mais longo para o mais curto: com "Mato Grosso" antes, o "do Sul" de
# "Mato Grosso do Sul" ficaria fora do span, e o tribunal seria o de outro estado.
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
    """A sigla do tribunal sem o ruído de OCR: `5TJ` → `STJ`.

    O tribunal regional da súmula chega como o texto o escreveu ("TRF-1", "TJ/SP",
    "TJ5P", "TRF da 1ª Região", "Tribunal de Justiça de São Paulo") e sai numa
    forma só, sem separador: `TRF1`, `TJSP`, `TREMG`, `TNU`. A troca do `5` por
    `S` vale só para a letra — no regional o número é a região, e "TRT-5" não
    pode virar "TRT-S".
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


#
# Formas correntes que a amostra não tem e o texto jurídico usa: a sigla da
# súmula vinculante ("SV 10"), "Enunciado" (como o TST chama as próprias
# súmulas), o inciso como "item" ("Súmula 331, item IV, do TST") e o honorífico
# antes do tribunal ("do C. STJ", "do E. STJ", "do col. TST"). Sem elas a súmula
# da cobertura sumia ou saía sem tribunal — `inventada`. O "Enunciado" é marcado
# no grupo `enunciado` para a resolução só o aceitar do TST.
#
# O tribunal regional vem nos mesmos grupos da sigla (`tribunal`,
# `tribunal_par`, `tribunal_do`), o nome por extenso inclusive, e
# `sigla_do_tribunal` o devolve na forma canônica.
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
    # O número atravessa o digitoide, mas não pode começar colado à palavra nem
    # terminar dentro de outra: sem os freios, `temas` casava como Tema `s`.
    #
    # A espécie do tema pode vir entre a palavra e o número ("Tema Repetitivo
    # 1.046", "Tema de Repercussão Geral nº 1.046", "Tema RG 1.046"), e o plural
    # abre a enumeração ("Temas 1.046 e 1.191"). Sem essas formas a citação caía
    # na família `processo`, e o número de um tema mencionado na ementa de um
    # acórdão resolvia para esse acórdão — `inventada` → `real`.
    rf"\b{_tolerante('Tema')}s?\s+"
    rf"(?:(?:d[ae]\s+)?(?:{_tolerante('Repercussão')}\s+{_tolerante('Geral')}"
    rf"|{_tolerante('Repetitivo')}|RG)\s+)?"
    rf"(?:{_NUMERO}\s*)?"
    rf"(?P<numero>{_DIGITOIDE}+(?:\.{_DIGITOIDE}{{3}})*)(?![A-Za-zÀ-ÿ])"
    rf"(?:\s*d[ae]\s*{_tolerante('repercussão')}\s*{_tolerante('geral')})?"
    # O tribunal depois do número faz parte da citação, como na súmula: "Tema
    # 1.046 do STF", "Tema Repetitivo 1.076 do STJ". Sem ele o span parava no
    # número e o IoU ficava entre 0,53 e 0,59 — na beira do corte, onde qualquer
    # ruído a mais derruba o casamento e custa FN e FP de uma vez.
    rf"(?:\s*(?:[/\-–]|,?\s*{_CONECTOR})\s*{_SIGLA_DE_TRIBUNAL})?",
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
# A palavra do nome está em caixa de título — maiúscula seguida de minúscula, com
# `(?-i:…)` porque `_DISPOSITIVO` é IGNORECASE — ou é uma das palavras do
# vocabulário fechado de `_PALAVRA_DE_CODIGO_MINUSCULA`, em qualquer caixa. Antes
# qualquer palavra servia, e a prosa entrava no span: "art. 186 do Código Civil
# trata do ato" (IoU 0,65). `militar` está na lista para que o CPPM escrito em
# minúscula continue capturado inteiro e recusado.
#
# Caixa de título, e não só inicial maiúscula: em caixa alta — ementas inteiras
# são escritas assim — toda palavra tem inicial maiúscula, e a prosa entrava no
# diploma ("ART. 290 DO CÓDIGO PENAL MILITAR SE ENCONTRA"). Ali só entra palavra
# do vocabulário fechado.
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
#
# O conector aceita o ruído do nível 2 (`dc`, `d0`, `dã`) e o nome vai até quatro
# palavras. Com o conector literal e o teto de três, "Código dc Processo Penal
# Militar" e "Código Brasileiro de Processo Penal Militar" perdiam o "Militar":
# o CPPM, fora da cobertura, chegava à resolução como CPP — o erro grave.
_CONECTOR_DE_NOME = r"d[aeoc0ã]"
_PALAVRA_DO_NOME = (
    rf"(?:\s+(?:{_CONECTOR_DE_NOME}\s+)?(?!{_CONECTOR_DE_NOME}\b)"
    rf"(?:{_PALAVRA_TITULO}|{_PALAVRA_DE_CODIGO_MINUSCULA}))"
)
_NOME_DE_CODIGO = rf"{_tolerante('Código')}{_PALAVRA_DO_NOME}{{0,4}}{_ANO_DE_VERSAO}"

# Os diplomas federais citados pelo nome, e não pelo número: "art. 5º da Lei de
# Execução Penal", "art. 98 do Estatuto da Criança e do Adolescente". Nenhuma
# outra alternativa de `_DIPLOMA` casa "Lei de …" ou "Estatuto …", e a citação
# sumia inteira. O conjunto de avaliação roda sobre uma base nova, que pode ter
# o artigo de qualquer lei federal; nos 996 acórdãos da base de hoje, "Lei de
# Introdução" aparece em 72, "Lei das Eleições" em 70 e "Lei de Licitações" em 51.
#
# A lista é **fechada**, pelo mesmo motivo de `_PALAVRA_DE_CODIGO_MINUSCULA`:
# "Lei de <qualquer coisa>" faria de "art. 5º da Lei de regência" uma citação. A
# detecção só entrega o nome inteiro no grupo `diploma`; quem o leva a (tipo,
# número, ano), ou o recusa, é a resolução.
#
# Cada entrada é o nome e os complementos que podem vir depois dele. O
# complemento que muda a identidade do diploma precisa entrar no span para
# chegar à resolução, como o qualificador da Constituição: "Federais" e "da
# Fazenda Pública" nomeiam outras duas leis de juizados, e sem eles `art. 3º da
# Lei dos Juizados Especiais Federais` chegaria como a lei dos juizados
# estaduais. "Nova" antes de "Lei de Licitações" separa a de 2021 da de 1993.
#
# Os complementos vão do mais longo para o mais curto: a alternância fica com o
# primeiro que casa, e "Cíveis" antes de "Cíveis e Criminais" deixaria o "e
# Criminais" fora do diploma.
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
    """A expressão de uma entrada de `_STATUTE_NAMES`, tolerante como as âncoras.

    A fronteira no fim impede que o nome termine dentro de uma palavra — "Lei de
    Inelegibilidade" não pode parar antes do "s" de "Inelegibilidades".
    """
    expressao = _tolerant_name(nome)
    if complementos:
        opcoes = "|".join(_tolerant_name(c) for c in complementos)
        expressao += f"(?:{_NAME_SEPARATOR}(?:{opcoes}))?"
    return expressao + r"(?![\wÀ-ú])"


# O ano entra pelo mesmo motivo que em `_NOME_DE_CODIGO`: "Lei de Licitações de
# 1993" e a Nova Lei de Licitações têm os mesmos números de artigo, e só com o ano
# no diploma a resolução consegue separá-las.
_NAMED_STATUTE = (
    "(?:"
    + "|".join(_statute_pattern(nome, extra) for nome, extra in _STATUTE_NAMES)
    + f"){_ANO_DE_VERSAO}"
)

# As siglas de diploma, dentro de `_DIPLOMA` e depois de vírgula
# (`_SIGLA_DE_DIPLOMA`). `CRFB` e `NCPC` são grafias correntes da CF/88 e do CPC
# vigente; `CP`, `CTN`, `CTB`, `ECA` e `CPPM` estão fora da cobertura de hoje e
# entram para que a citação exista.
#
# `LEP`, `LINDB`, `LICC`, `LOMAN`, `LRF` e `LEF` são as siglas dos diplomas de
# `_STATUTE_NAMES` que a prosa usa sozinhas depois do artigo ("art. 47 da LEF"):
# nos 996 acórdãos da base, as seis aparecem nessa forma. `LIDB` também — é a
# abreviação da Lei de Introdução em 46 deles.
#
# A mais longa vem antes da que ela contém (`CPPM` antes de `CPP`), e quem
# termina a sigla é a fronteira que cada uso põe depois dela: sem isso `CPPM`
# casava `CPP` e o "M" ficava de fora.
_DIPLOMA_ACRONYMS = (
    r"(?:CPPM|CPC|CPP|CPM|CLT|CDC|CRFB|NCPC|CTN|CTB|ECA"
    r"|LINDB|LIDB|LICC|LOMAN|LEP|LRF|LEF|CF|CC|CP)"
)
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
        federal república federativa brasileira brasil cidadã estadual estado portuguesa
        espanhola italiana francesa alemã americana estrangeira imperial mineira
        paulista fluminense gaúcha baiana catarinense paranaense pernambucana
        """.split()
    )
    + r")(?![\wÀ-ú])"
)

# A palavra "Lei" também sofre o ruído de letra (`Lci`), e o número pode vir
# depois de um qualificador ("Lei Federal nº 9.504/97"). Sem as duas coisas o
# dispositivo não casava, e o número da lei sobrava para a família `processo`.
_QUALIFICADOR_DE_LEI = "|".join(
    _tolerante(p) for p in ("Complementar", "Federal", "Estadual", "Municipal", "Ordinária")
)

# Palavras de qualificador da Constituição depois da primeira, na mesma linha:
# "Constituição da República Portuguesa", "Constituição Federal Alemã". Só a
# primeira palavra entrava no diploma, e o qualificador estrangeiro que vinha
# depois nunca chegava à regra de inclusão da CF. O algarismo romano fica de
# fora para que o título da seção seguinte não entre no diploma.
#
# Nem toda palavra capitalizada é qualificador: sem pontuação entre as duas, a
# âncora de outra citação ("… Constituição Federal Súmula 83 do STJ") ou o nome
# de quem julga ("… Federal Relator Ministro Fulano") entrava no diploma — a CF
# saía `inventada` e a citação vizinha sumia. Palavra-âncora de família,
# palavra institucional e sigla de classe processual param a captura.
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
    rf"|(?:\s+d[aeo]\s+)?(?:\s*(?-i:{_NAO_QUALIFICA})(?:(?-i:[A-ZÀ-Ú])[\wÀ-ú]+|{_QUALIFICADOR_MINUSCULO}))?"
    rf"{_QUALIFICADOR_SEGUINTE}{_ANO_DE_VERSAO})"
    # "Lei Maior", "Carta Política" e "Carta da República" são como a prosa
    # jurídica chama a CF/88, tanto quanto "Carta Magna".
    # O apelido leva o qualificador e o ano que vierem depois, como a
    # Constituição: "Lei Maior de 1969", "Carta da República Portuguesa" são
    # outra carta, e só com o qualificador no diploma a resolução pode recusá-la.
    r"|(?:Carta\s+Magna|Lei\s+Maior|Carta\s+Pol[íi]tica|Carta\s+da\s+Rep[úu]blica)"
    rf"(?:\s+de\s+(?:19|20)\d{{2}}|(?:\s+d[aeo]s?)?{_QUALIFICADOR_SEGUINTE}{_ANO_DE_VERSAO})"
    # `Decreto-Lei nº 5.452/1943` é **como a base canônica nomeia a CLT** na
    # primeira linha autodeclarada dos registros `dispositivo`, e `LC` é a sigla
    # corrente da Lei Complementar. Sem as duas alternativas a citação sumia — e
    # os marcadores "lc 64" em `resolucao.DIPLOMAS` eram inalcançáveis.
    # As duas palavras toleram o ruído de letra ("Deereto-Lci", "Decret0-Lei").
    rf"|{_tolerante('Decreto')}[-‐\s]*{_tolerante('Lei')}{_NUMERO_DE_LEI}"
    rf"|LC{_NUMERO_DE_LEI}"
    # `CPC/73` e `CC/16` são os códigos revogados; o ano vai junto para a
    # resolução decidir. `CF/88` é o caso particular que já existia.
    #
    # A sigla precisa terminar ali: sem a fronteira, `CPPM` casava `CPP` e o "M"
    # ficava de fora — o Código de Processo Penal Militar, fora da cobertura,
    # resolvia para o art. 312 do CPP. As siglas fora da cobertura entram para que
    # a citação exista e saia `inventada`. Ver `_DIPLOMA_ACRONYMS`.
    rf"|{_DIPLOMA_ACRONYMS}(?![A-Za-zÀ-ÿ])"
    rf"{_ANO_DE_VERSAO}"
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
#
# As palavras do qualificador sofrem o mesmo ruído de letra que as âncoras
# ("iriciso", "eaput", "parágraf0 únic0", "alínca"), e com a palavra escrita
# literal o dispositivo inteiro sumia: no simulador do sigiloso eram 5% dos
# dispositivos do nível 2 a taxa 0,05, e 16% a 0,15 — a maior perda medida.
# Mesma política de `_tolerante`: vale só para as palavras fixas.
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

# "novo" ou "atual" antes do diploma ("art. 373 do novo Código de Processo
# Civil", "do atual CPC") é como a prosa distingue o CPC/2015 do de 1973; o
# adjetivo ficava entre o conector e o diploma e a citação sumia.
#
# O diploma por sigla pode vir só depois de vírgula, sem conector ("art. 5º, LV,
# CF"), forma corrente em peça jurídica. Só a sigla, e só com vírgula: nome por
# extenso sem conector seria prosa.
_ADJETIVO_DE_DIPLOMA = r"(?:(?:novo|atual|vigente)\s+)"
_SIGLA_DE_DIPLOMA = rf"{_DIPLOMA_ACRONYMS}(?![A-Za-zÀ-ÿ])" r"(?:\s*/\s*\d{2,4})?"
_DISPOSITIVO = re.compile(
    rf"\b{_tolerante('art')}(?:{_tolerante('igo')}|\.|\b)\s*\n?\s*(?P<artigo>{_NUMERO_DE_ARTIGO})"
    rf"{_QUALIFICADORES}"
    r"(?:"
    rf"\s*,?\s*\n?\s*{_CONECTOR}\s+{_ADJETIVO_DE_DIPLOMA}?(?P<diploma>{_DIPLOMA})"
    rf"|\s*,\s*(?P<diploma_sigla>(?-i:{_SIGLA_DE_DIPLOMA}))"
    r")",
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
    # "Min" aceita o ponto trocado por grau ("Min°", "Min º"), como a marca de
    # número; sem isso o "Min" virava o nome do relator e o nome ficava de fora.
    rf"(?:Mi[nN]\s?[.°º]?|{_tolerante('Ministr')}[ao])?\.?"
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
    # O incidente antes da classe ("AgInt no AREsp", "EDcl nos EDcl") só entra
    # quando tem forma de sigla — duas maiúsculas —, para que a prosa capitalizada
    # ("Como no REsp") não abra o span. "com" liga a classe por extenso
    # ("Recurso Extraordinário com Agravo"), que antes começava em "Agravo".
    r"|(?:[A-ZÀ-Ú][a-zà-ú]*[A-ZÀ-Ú][\wÀ-ú.\-]*\s+n[oa]s?\s+)*"
    r"[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}"
    r"(?:\s+(?:em\s+|de\s+|do\s+|da\s+|com\s+)?[A-ZÀ-Ú][\wÀ-ú.\-]{1,24}){0,3}"
    r")"
)

# O nome do relator: palavras capitalizadas, com conector ("Celso de Mello") e
# inicial abreviada ("J. Otávio Noronha"). O ponto só vale **como inicial** — uma
# letra e o ponto —, e entre as palavras cabe no máximo uma quebra de linha.
# Com o ponto solto e `\s+`, o nome atravessava o fim da frase e engolia a
# primeira palavra da seguinte ("… Celso De Mello. Antes") ou o título da seção
# depois da linha em branco ("… LÚCIA.\n\nIII"), e roubava a sobreposição da
# citação que viesse logo depois ("… LÚCIA. REsp 1.234.567/SP" perdia o REsp).
_SEPARADOR_DE_NOME = r"(?:[ \t\xa0]+\n?[ \t\xa0]*|\n[ \t\xa0]*)"
# A inicial também sofre o ruído: "rnAURO" (M→rn) e, em nome todo em caixa
# alta, a maiúscula lida como minúscula confundível ("eARLOS", "eRISTIANO").
# Só nessas duas formas — minúscula seguida de duas maiúsculas, ou o "rn" —,
# para que a palavra de prosa minúscula não entre no nome.
_PALAVRA_DE_NOME = r"(?:[A-ZÀ-Ú]|rn(?=[\wÀ-ú])|[a-zà-ú](?=[A-ZÀ-Ú]{2}))(?:[\wÀ-ú']+|\.)"
_NOME_PROPRIO = (
    rf"{_PALAVRA_DE_NOME}"
    rf"(?:{_SEPARADOR_DE_NOME}(?:d[aeo]s?{_SEPARADOR_DE_NOME})?{_PALAVRA_DE_NOME}){{0,4}}"
)

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
    rf"(?:\s*,?\s*{_CONECTOR}\s+(?:{_SIGLA_DE_TRIBUNAL}|{_TRIBUNAL_POR_EXTENSO}))?"
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

_MENCAO_TRIBUNAL = re.compile(rf"\b{_SIGLA_DE_TRIBUNAL}")

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
    # O número é o último token inteiro, não a cauda de uma palavra: sem a
    # fronteira, o `o` final de "Lei Maior do Estado" era lido como número sem
    # dígito real, e a citação — que precisa existir para sair `inventada` — sumia.
    numero = re.search(rf"(?<![A-Za-zÀ-ÿ]){_DIGITOIDE}[{_DIGITOIDE[1:-1]}./]*$", diploma or "")
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
#
# A data com ponto ("Sessão Virtual de 20.6.2025") passava como processo: o
# separador de milhar do núcleo aceita o ponto. Com ponto, o ano precisa ter
# quatro dígitos — "1.23.45" não é data, e grupo de milhar tem sempre três.
_DATA = re.compile(
    r"^(?:\d{1,2}/\d{1,2}/(?:\d{2}|(?:19|20)\d{2})|\d{1,2}\.\d{1,2}\.(?:19|20)\d{2})(?!\d)"
)

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
    # `f[l1I]s?` e não `fls?`: com a letra do meio corrompida (`f1s.`, `fIs.`) o
    # rótulo sumia e a folha virava processo.
    r"(?:\b(?:f[l1I]s?|folhas?|protocolo|CPF|CNPJ|valor\s+da\s+causa"
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

# Ato normativo ou referência que não é decisão, logo à esquerda do número:
# "Lei 8.112/90", "Decreto 3.048/99", "Medida Provisória nº 2.200-2/2001",
# "Informativo 1.046". O número casava o núcleo da família `processo` e virava
# citação `inventada` que o gabarito não anota; com ano de dois dígitos
# ("Lei nº 9.504/97") ele ainda escapava de `_TERMINA_EM_ANO` e, se o índice o
# tivesse, virava `real`. Conferido: nenhuma citação de processo do gabarito
# tem uma dessas palavras nos 40 caracteres à esquerda.
#
# A palavra precisa estar colada ao número, admitido só um qualificador curto
# ("Lei Federal", "Lei Complementar") e a marca de número: é o que impede a
# regra de apagar o processo vizinho em "A Lei 8.112/90 … no REsp 1.234.567/SP".
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
# O núcleo da família `processo` casa qualquer número de quatro dígitos, e o
# gerador dos pareceres escreve prosa com quantidade, prazo, pena e valor: "pena
# de <n> dias-multa", "<n> gramas", "cerca de <n> eleitores". Medido por sonda,
# cada uma dessas frases virava citação `inventada` — e "de <n> dias" e "<n>
# metros quadrados" viravam `real` quando o número coincidia com o número próprio
# curto de um acórdão do dev (o índice tem 15 chaves de quatro dígitos e 221 de
# cinco). É a forma do erro que chega mais perto de τ, e com base nova o conjunto
# das coincidências muda: não há como conferir número a número. O que dá para
# reconhecer é a prosa em volta.
#
# Os filtros daqui valem só para a detecção. `_e_numero_de_processo` continua
# sendo o que o índice (`base_canonica.numeros_proprios`) e a exclusão da `vaga`
# usam, e fica como estava: mudá-lo mexeria nas chaves do índice e na contagem de
# constituintes da `vaga`, que nenhuma medição daqui cobre.

# O número de artigo, tema ou súmula que a família específica não reconheceu:
# "art. <n> do Regimento Interno" (o diploma não está em `_DIPLOMA`) e "arts.
# 1.036 e 1.037 do CPC" (o plural não casa `_DISPOSITIVO`). Sem este rótulo o
# número vazava para `processo`, e na sonda o artigo do regimento resolvia para
# um acórdão do dev. Tema e súmula nus já perdiam para a própria família pela
# precedência; o que escapava era o segundo número da enumeração ("Temas 1.046 e
# 1.191"). É o mesmo rótulo que `base_canonica._ROTULO_NAO_PROPRIO` recusa ao
# montar o índice, com a enumeração a mais.
#
# Os elementos da enumeração são só número e separador, então o rótulo não
# alcança a citação vizinha que tem classe: em "art. 5º e REsp 1.234.567" o
# "REsp" interrompe a lista, e o REsp continua citação.
_ENUMERATED_NUMBER = rf"(?=[^\s,]*\d){_DIGITOIDE}[{_DIGITOIDE[1:-1]}.]*[ºo°ª]?(?:[-‐][A-Za-z])?"
_NON_PROCESS_LABEL = re.compile(
    rf"\b(?:{_tolerante('art')}(?:{_tolerante('igo')})?|{_tolerante('Tema')}"
    rf"|{_tolerante('Súmula')})[s5]?\.?\s*(?:{_NUMERO}\s*)?"
    rf"(?:{_ENUMERATED_NUMBER}\s*(?:,|(?:,\s*)?(?:e|a|ao|ou|at[ée])(?![\wÀ-ú]))\s*)*$",
    re.IGNORECASE,
)

# A janela do rótulo cabe uma enumeração de meia dúzia de artigos ("arts. 1.036,
# 1.037, 1.038, 1.039, 1.040 e 1.041" tem 50 caracteres).
_LABEL_WINDOW = 120

# A unidade ou o substantivo de quantidade logo **depois** do número. Lista
# fechada, sem distinção de caixa, com as quantidades que o gerador e os
# acórdãos da base escrevem (medido nos 996: votos, litros, munições, pessoas,
# eleitores, kWh e hectares são as mais frequentes).
#
# O começo da expressão cobre três vícios do núcleo. O dígito que ele larga para
# trás quando a unidade vem colada: em "12.500kg" o freio contra letra no fim
# devolve só `12.50`, e o `0` fica aqui. A faixa ("1.000 a 2.000 pessoas"), em
# que a unidade só aparece depois do segundo número. E o número por extenso
# entre parênteses, que é como a peça escreve pena e valor ("1.460 (mil
# quatrocentos e sessenta) dias-multa").
#
# As unidades de uma letra só valem em minúscula, menos o "L" de litro:
# maiúscula solta depois de número é mais provável que seja sigla. O "mg" também
# só vale em minúscula — "MG" é a UF de Minas Gerais ("ARE 123456 MG", forma
# medida nos acórdãos da base), e o miligrama em caixa alta é raro demais para
# pagar esse risco.
#
# A vírgula só entra como decimal, seguida de dígito ("2.000,5 litros"). Solta,
# ela é pontuação da frase, e atravessá-la levava a unidade para longe do
# número: em "Ações Diretas de Inconstitucionalidade ns. <n> e <n>, processos nos
# quais…" (medido nos acórdãos da base) o número da ADI era recusado.
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

# O grama abreviado, que o núcleo engole porque `g` é digitoide: "2.500 g" e
# "2.500g" chegam aqui inteiros, e o `g` virava o dígito 9 no reparo. Só depois
# de espaço ou de um grupo de milhar completo — "1.234.56g" é o 9 corrompido de
# um número de processo, e continua número. O `l` de litro fica de fora: a base
# tem o ruído que repete a última letra ("Código Penal l"), e depois de um número
# ele apagaria a citação.
_SWALLOWED_UNIT = re.compile(r"(?:\d[ \t\xa0]|\.\d{3})g$")

# Quantidade não tem dez dígitos. Acima disso o número é CNJ ou número único do
# STJ, e nenhuma das duas regras de quantidade vale para ele: "até" e "entre"
# também introduzem processo ("suspensos até 0801234-56…"), e perder uma citação
# de número completo custa mais do que qualquer quantia que passasse.
_LONG_NUMBER_DIGITS = 10

# O quantificador **imediatamente antes** do número. Quando ele encosta no
# número não sobra lugar para classe entre os dois, então esta regra dispensa o
# teste de `_names_class_or_marker`. "R$" já está em `_ROTULO_DISTRATOR`.
_QUANTIFIER = re.compile(
    r"(?:\b(?:cerca\s+de|aproximadamente|mais\s+de|menos\s+de|at[ée]|entre|quase|apenas"
    r"|somente|total\s+de|pelo\s+menos|ao\s+menos|no\s+m[áa]ximo|no\s+m[íi]nimo"
    r"|acima\s+de|abaixo\s+de|superior(?:es)?\s+a|inferior(?:es)?\s+a"
    r"|em\s+torno\s+d[eoa]s?|por\s+volta\s+de)|US\$)\s*$",
    re.IGNORECASE,
)

# A marca que antecede o número de processo mesmo sem classe: "nº 1234",
# "processo 1234", "autos nº", e o plural "ns." / "nºs" da enumeração ("ADIs ns.
# <n> e <n>"). O "no" fica aqui e não entre as palavras de ligação: é a
# grafia de "nº" que a própria base usa, e na dúvida o número continua citação.
# "recurso" em minúscula não tem forma de elo, e por isso precisa estar na lista.
_PROCESS_MARKER = re.compile(
    r"n\s*[.ºo°0]{0,2}|n[º°]?s\.?|[º°]|processos?|autos|recursos?|feitos?|n[úu]meros?",
    re.IGNORECASE,
)

# Palavra de ligação que encosta no número na prosa: "pena de <n>", "PENA DE
# <n>", "eleito com <n> votos", "Foram <n> eleitores". Nome de classe não
# termina nela — o conector fica **dentro** do nome ("Mandado de Segurança"), e o
# que encosta no número é o substantivo, a sigla ou a marca. A lista existe
# porque as curtas, em caixa alta ou abrindo a frase ("DE", "Os", "Com"), têm a
# forma de uma sigla de três letras como "Rcl".
#
# "se" fica de fora de propósito: em caixa alta é a sigla da Sentença
# Estrangeira ("SE 5.206"), e ali a palavra nomeia a classe.
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

    Mais estreito que `_e_elo`, de propósito. Na cadeia de prefixo, qualquer
    palavra capitalizada é elo, e a palavra que abre a frase também é —
    "Compareceram 5.130 pessoas", "Apreenderam-se 6.240 kg". Aqui o que conta
    como classe é a sigla (caixa mista, como `REsp` e `AgInt`; caixa alta curta,
    como `RESP` e `HC`; ou curta com ponto, como `Rcl` e `Recl.`) e o núcleo do
    nome por extenso ("Recurso", "Reclamação"). `_elo_corrompido` também fica de
    fora: ele lê o `c` inicial como `E` corrompido, e "Foram consumidos 2.417
    litros" passava por "Eonsumidos".

    A sigla composta ("TST-E-ED-RR-", "AGR-RESPE", "EMB.DECL.") é julgada pedaço
    a pedaço, porque o tamanho do todo não diz nada sobre ela.
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

    É a exceção da regra de unidade: "Rcl 12.345" e "processo nº 1234" continuam
    citação mesmo com uma unidade depois. Quem decide é o vizinho imediato, com
    a mesma política de quebra de linha de `_expandir_prefixo` — uma quebra é
    continuação, duas são fim de parágrafo. A cadeia inteira não serve como
    primeiro teste: ela engole prosa capitalizada ("Cerca de 30.000", "PENA DE
    1.460"), e aí qualquer número da frase teria "classe".

    A cadeia só entra quando o vizinho é uma palavra por extenso que não é de
    ligação: "Recurso Especial 1.234.567", "Habeas Corpus 123.456", "Mandado de
    Segurança 12.345" terminam num adjetivo ou complemento, e o que nomeia a
    classe é o núcleo mais à esquerda. Ali só o núcleo conta, não qualquer
    palavra capitalizada — é o que mantém "Compareceram 5.130 pessoas" recusado.
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

    ``start`` e ``end`` delimitam o número em ``text``. Só as janelas vizinhas
    são lidas, para o custo não crescer com o tamanho do documento.
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
    if _INSCRICAO_COM_UF.search(antes):
        return False
    janela = antes[-_JANELA_ROTULO:]
    return not (_ROTULO_DISTRATOR.search(janela) or _ATO_NORMATIVO.search(janela))


# A inscrição na OAB colada à sigla da UF, como o rol de advogados do STJ a
# escreve ("ALINE SANTOS - DF043530", "LUCAS TIEPPO - SP413475"). O núcleo não
# pode começar colado à letra, então casa a partir do segundo caractere — e o
# rótulo "DF" nunca chegava à janela do filtro.
#
# O sinal é a UF colada ao dígito **depois do travessão** que separa o nome do
# advogado da inscrição, ou depois do rótulo "OAB" (a forma do STM: "(OAB
# SC50542)"). Sem nenhum dos dois, a UF colada é sigla de classe que por acaso
# coincide com uma UF ("MS12345/DF", "REsp nº SP1234567"), e a citação não pode
# sumir.
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
        # no meio (`Recurso em Mandado de Segurança\nnº 12.345/RJ`). Duas
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


# O último pedaço do núcleo, depois de um espaço: `5ob` em "2020 5ob".
_PEDACO_FINAL = re.compile(rf"[ \t\xa0\n]+({_DIGITOIDE}+)$")

# O pedaço depois de um ponto final e de espaço: `O` em "REsp 1.234.567. O
# recurso", `Isso` em "…567. Isso basta". São palavras que abrem a frase seguinte
# e só têm letra que o OCR confunde com dígito.
_PEDACO_APOS_PONTO = re.compile(rf"\.[ \t\xa0\n]+({_DIGITOIDE}+)$")


def _sem_palavra_corrompida(numero: str) -> str:
    """O núcleo sem o pedaço final que é palavra com uma letra virada dígito.

    O núcleo atravessa espaço e aceita digitoide, então "de 2020 5ob a vigência"
    (o "sob" com o `s` corrompido) casava `2020 5ob`, cuja forma canônica
    `2020506` já não é ano, e virava processo `inventada`.

    O pedaço só sai quando tem mais letra do que dígito **e** o que vem antes
    dele é um número completo — ano ou página —, não um número em andamento.
    Grupo de milhar corrompido no fim ("1 B21 bb3", "1.234 S6O") também tem mais
    letra que dígito, mas vem depois de outro grupo e tem exatamente três
    caracteres: ali o pedaço é número, e cortá-lo encurtava o identificador.

    Depois de ponto final e espaço, o pedaço sem **nenhum** dígito real sai
    sempre, com o ponto: é a primeira palavra da frase seguinte ("O", "Os",
    "Isso"), que o núcleo engolia quando a citação fecha a frase. O grupo legítimo
    depois de ". " (`1. 234.567`, `123-45. 2012`) tem dígito real.
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
    # Só sai quando o que fica antes é um número completo que não é processo —
    # ano ou página. Em qualquer outro caso o pedaço é o último grupo de um
    # número corrompido, em qualquer tamanho: "APL 7000380-08 2023 7 00 O0OO"
    # perdia o `O0OO` e virava `inventada`.
    canonico = _forma_canonica(resto)
    if not (_ANO_SOLTO.match(canonico) or _PAGINAS.match(canonico)):
        return numero
    return resto


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
        if not _numero_de_lei_plausivel(m.group("diploma") or m.group("diploma_sigla")):
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

    A cadeia de prefixo atravessa o fim de outra citação quando as duas vêm
    coordenadas: em "art. 5º da CF e REsp 1.234.567/SP" o prefixo do REsp começa
    em "CF", e "… CÁRMEN LÚCIA. REsp 1.234.567/SP" puxa o nome do relator. O REsp
    perdia a sobreposição e sumia inteiro. Se o número está todo depois do
    vencedor, basta começar o span no primeiro token depois dele, pulando a
    conjunção e a pontuação que as ligam.
    """
    fim_vencedor = max(e.fim for e in vencedores)
    if any(e.inicio >= achado.inicio + len(achado.trecho) for e in vencedores):
        return None
    deslocamento = fim_vencedor - achado.inicio
    resto = achado.trecho[deslocamento:]
    # A pontuação, a conjunção e o conector que ligam as duas citações ficam de
    # fora — o conector nunca é a borda do span (ver `_expandir_prefixo`).
    cortado = re.match(r"[\s.,;:]*(?:(?:e|o|a|os|as|n[oa]s?|d[oae]s?|em)\s+)*", resto)
    inicio_rel = deslocamento + (cortado.end() if cortado else 0)
    trecho = achado.trecho[inicio_rel:]
    # O que sobra precisa ser uma citação inteira: uma classe processual e, logo
    # depois dela, o número. Sem isso o resgate ressuscitava candidatos que só
    # se anulavam por sobreposição — o rol de advogados ("ALINE SANTOS -
    # DF043530"), onde cada inscrição puxa o nome anterior como prefixo.
    numero = _NUMERO_PROCESSO.search(trecho)
    if numero is None or not _prefixo_nomeia_classe(trecho, numero.start()):
        return None
    return Achado(
        achado.inicio + inicio_rel, achado.fim, trecho, achado.familia, achado.tipo, achado.dados
    )


def detectar(texto: str) -> list[Achado]:
    """Encontra todas as citações candidatas no documento.

    Devolve os achados ordenados por posição, sem sobreposição entre si.
    """
    return _resolver_sobreposicao(_candidatos(texto, fim_do_cabecalho(texto)))
