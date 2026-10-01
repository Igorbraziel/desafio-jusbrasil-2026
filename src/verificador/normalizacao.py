"""Normalização de superfície: ruído de documento (OCR, formatação, UF) → forma canônica.

O ruído nunca troca um dígito por outro, então toda citação real é recuperável.
Duas armadilhas de ordem: a UF sai antes da correção de OCR (senão o ``S`` de
``/SP`` vira ``5``), e letra só vira dígito quando colada a um dígito.
"""

from __future__ import annotations

import re
import unicodedata

# Conjunto fechado em vez de [A-Z]{2}, para não amputar sufixo que só parece UF.
UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

# Letra lida no lugar de dígito; só se aplica colada a um dígito.
OCR_PARA_DIGITO = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "i": "1",
    "S": "5",
    "s": "5",
    "g": "9",
    "q": "9",
    "G": "6",
    "b": "6",
    "B": "8",
    "Z": "2",
    "z": "2",
}

# Letra lida no lugar de letra. Só se aplicam às palavras-chave fixas das
# expressões, onde o custo em falso positivo é nulo; `u→ii` e `n→ri` são a
# mesma confusão de ligadura que `m→rn`.
CONFUSOES_DE_LETRA = {
    "a": "ã",
    "e": "c",
    "c": "e",
    "i": "l",
    "o": "0",
    "m": "rn",
    "u": "ii",
    "n": "ri",
}

# Candidato a "número com letras de OCR dentro".
_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-–—/]*[0-9A-Za-z]|[0-9A-Za-z]")

# Hífen ASCII, os traços U+2010–U+2015 e o sinal de menos.
_HIFENS = r"\-‐-―−"

# No documento o identificador pode vir partido por espaço ou quebra de linha.
_PONTUACAO_NO_DOCUMENTO = rf"[\s.{_HIFENS}/]"

# Na base não há espaço dentro do número; aceitá-lo colaria números vizinhos.
_PONTUACAO_NA_BASE = rf"[.{_HIFENS}/]"

_NUCLEO = re.compile(rf"\d(?:{_PONTUACAO_NO_DOCUMENTO}*\d)*")
_NUCLEO_LIMPO = re.compile(rf"\d(?:{_PONTUACAO_NA_BASE}*\d)*")

# Sufixo de UF com uma ou duas letras. Uma letra só é UF truncada pela detecção
# (que pode engolir o `S` de `/SP`); sem tirá-la, o `S` vira `5` no número.
_SUFIXO_UF = re.compile(rf"\s*[/({_HIFENS}]\s*([A-Za-z]{{1,2}})\s*\)?[\s.]*$")

# "GO" é a única UF que o OCR pode corromper nas duas letras (`G0`, `6O`), e lida
# como `60` ela entraria no número. Exige uma letra sobrevivente: `60` puro é
# indistinguível do último grupo de um número.
_GOIAS_CORROMPIDO = re.compile(rf"\s*[/({_HIFENS}]\s*(?:G0|6O)\s*\)?[\s.]*$")

_ESPACOS = re.compile(r"\s+")


def sem_acento(texto: str) -> str:
    """Remove diacríticos, inclusive os que o OCR põe na vogal errada."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def chave_textual(texto: str) -> str:
    """Forma comparável de um trecho: minúsculas, sem acento, espaços colapsados."""
    return _ESPACOS.sub(" ", sem_acento(texto).lower()).strip()


def separar_uf(trecho: str) -> tuple[str, str | None]:
    """Separa o sufixo de UF: ``"REsp 1.234.567/SP"`` → ``("REsp 1.234.567", "SP")``.

    Precisa rodar antes da correção de OCR.
    """
    casamento = _SUFIXO_UF.search(trecho)
    if casamento is None:
        goias = _GOIAS_CORROMPIDO.search(trecho)
        if goias is not None:
            return trecho[: goias.start()].strip(), "GO"
        return trecho.strip(), None
    uf = casamento.group(1).upper()
    # Duas letras só saem se forem UF; uma letra sai sempre (UF truncada).
    if len(uf) == 2 and uf not in UFS:
        return trecho.strip(), None
    return trecho[: casamento.start()].strip(), uf


_LETRAS_OCR = "".join(sorted(OCR_PARA_DIGITO))
_GRUPO = rf"[\d{_LETRAS_OCR}]"

# Grupo interior de um número estruturado (`4736-oS`, `2010.s`). Exige dígito
# antes do separador, então a sigla (`TST-ED-`) nunca casa.
_GRUPO_INTERIOR = re.compile(
    rf"(?<=\d[.{_HIFENS}/])(?P<letras>{_GRUPO}+)(?=[.{_HIFENS}/]|\s*$|\s+[^\w\s]|\s*[/(])"
)

# Primeiro grupo de milhar lido como letra solta (`l. 470.537`): só leituras de
# `1`. Exige dois grupos de três depois, para não pegar "I" de inciso.
_MILHAR_SOLTO = re.compile(
    rf"(?<![\w.])(?P<letras>[lIi])(?=\.?\s+{_GRUPO}{{3}}[.\s]\s?{_GRUPO}{{3}}\b)"
)


def _token_e_numero(token: str) -> bool:
    """O token é um número cujas letras são todas confusões de OCR?

    Exige um dígito (barra ``SOS``), toda letra mapeável (barra ``DO``, ``STJ``)
    e ao menos dois alfanuméricos (barra letra solta).
    """
    alfanumericos = [c for c in token if c.isalnum()]
    if len(alfanumericos) < 2 or not any(c.isdigit() for c in alfanumericos):
        return False
    return all(not c.isalpha() or c in OCR_PARA_DIGITO for c in alfanumericos)


def _corrigir_ocr(trecho: str) -> str:
    """Desfaz as trocas de letra por dígito dentro do identificador.

    A adjacência sozinha falha com corrupção consecutiva (``g.B7G.S43``), por
    isso a primeira passada converte tokens inteiros que são números; a segunda
    trata a letra isolada colada ao número (``12345l7``).
    """
    caracteres = list(trecho)

    for casamento in _TOKEN.finditer(trecho):
        if not _token_e_numero(casamento.group()):
            continue
        for i in range(casamento.start(), casamento.end()):
            substituto = OCR_PARA_DIGITO.get(trecho[i])
            if substituto is not None:
                caracteres[i] = substituto

    for i, caractere in enumerate(trecho):
        substituto = OCR_PARA_DIGITO.get(caractere)
        if substituto is None or caracteres[i] != caractere:
            continue
        anterior = trecho[i - 1] if i else ""
        seguinte = trecho[i + 1] if i + 1 < len(trecho) else ""
        if anterior.isdigit() or seguinte.isdigit():
            caracteres[i] = substituto

    # Terceira passada: grupo inteiro corrompido entre separadores (`4736-oS.Z013`),
    # que nenhuma letra encosta em dígito. Repete até estabilizar, porque cada
    # grupo convertido ancora o seguinte (`201O.s.04`).
    for _ in range(8):
        corrigido = "".join(caracteres)
        mudou = False
        for expressao in (_GRUPO_INTERIOR, _MILHAR_SOLTO):
            for grupo in expressao.finditer(corrigido):
                for i in range(grupo.start("letras"), grupo.end("letras")):
                    substituto = OCR_PARA_DIGITO.get(corrigido[i])
                    if substituto is not None and caracteres[i] != substituto:
                        caracteres[i] = substituto
                        mudou = True
        if not mudou:
            break

    return "".join(caracteres)


def digitos_do_identificador(trecho: str) -> str:
    """Número do processo de um trecho, só com dígitos ("" se não houver).

    O maior núcleo vence: em ``REsp 1.234.567 de 2020`` o ano perde.
    """
    sem_uf, _ = separar_uf(trecho)
    corrigido = _corrigir_ocr(sem_uf)
    nucleos = _NUCLEO.findall(corrigido)
    if not nucleos:
        return ""
    melhor = max(nucleos, key=lambda n: (sum(c.isdigit() for c in n), -corrigido.index(n)))
    return re.sub(r"\D", "", melhor)


def numeros_do_texto(texto: str) -> set[str]:
    """Todos os números de um texto da base canônica, só com dígitos.

    Emite as duas leituras do espaço: em geral ele separa números, mas há
    tribunais que gravam o número do processo com espaço no meio.
    """
    achados = _NUCLEO_LIMPO.findall(texto) + _NUCLEO.findall(texto)
    return {re.sub(r"\D", "", n) for n in achados} - {""}
