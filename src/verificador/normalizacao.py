"""Normalização de superfície: ruído de documento → forma canônica.

É aqui que o nível 2 se decide. As citações do nível 2 apontam para registros
tão válidos quanto as do nível 1 — o que muda é a escrita. A organização garante
que **um dígito nunca é trocado por outro dígito**: todo ruído aplicado a uma
citação real é recuperável por normalização.

Três frentes:

* ``digitos_do_identificador`` extrai o número do processo desfazendo confusões
  de OCR (``170076O`` → ``1700760``, ``1.45g.779`` → ``1459779``), pontuação
  irregular e quebras de linha no meio do identificador.
* ``reparar_palavra`` desfaz o ruído tipográfico das citações vagas
  (``entendirnento`` → ``entendimento``).
* ``chave_textual`` produz uma forma comparável (sem acento, sem caixa) para
  casar nomes de códigos e tribunais.
"""

from __future__ import annotations

import re
import unicodedata

# Letras que o OCR troca por dígitos. Só são aplicadas no *interior* de um número
# — entre dois dígitos de verdade. Sem essa restrição, o "I" final de "AREspEI" e
# o "S" de um sufixo "/SP" entrariam no identificador e o corromperiam.
OCR_PARA_DIGITO = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "i": "1",
    "|": "1",
    "Z": "2",
    "z": "2",
    "G": "6",
    "S": "5",
    "s": "5",
    "B": "8",
    "g": "9",
    "q": "9",
}

# Separadores tolerados dentro de um identificador: ponto, hífen, espaço comum,
# espaço não-quebrável e quebra de linha.
SEPARADORES = ".-‐‑‒–— \t\n\r "

_LETRAS_OCR = "".join(OCR_PARA_DIGITO)
# Um núcleo começa num dígito de verdade e pode terminar numa letra de OCR
# colada a um dígito (``170076O``).
NUCLEO_NUMERICO = re.compile(
    rf"\d[\d{re.escape(_LETRAS_OCR)}{re.escape(SEPARADORES)}]*\d[{re.escape(_LETRAS_OCR)}]?"
)

# Sufixo de unidade federativa: /PR, - PR, (PR), – CE.
SUFIXO_UF = re.compile(r"\s*[/\-‐-—(]\s*([A-Z]{2})\s*\)?\s*$")

# Confusões de OCR entre letras, aplicadas quando comparamos palavras.
SUBSTITUICOES_PALAVRA = (("rn", "m"), ("vv", "w"), ("ii", "n"))


def sem_acento(texto: str) -> str:
    """Remove diacríticos — inclusive os corrompidos (``Magãlhães``)."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def chave_textual(texto: str) -> str:
    """Forma comparável de um trecho: minúsculas, sem acento, espaços colapsados."""
    return re.sub(r"\s+", " ", sem_acento(texto).lower()).strip()


def reparar_palavra(texto: str) -> str:
    """Desfaz o ruído tipográfico mais comum antes de comparar palavras."""
    reparado = chave_textual(texto)
    for ruim, bom in SUBSTITUICOES_PALAVRA:
        reparado = reparado.replace(ruim, bom)
    return reparado


def _traduzir_interior(nucleo: str) -> str:
    """Troca por dígito apenas as letras cercadas por dígitos de verdade."""
    caracteres = list(nucleo)
    for i, c in enumerate(caracteres):
        if c not in OCR_PARA_DIGITO:
            continue
        cercado = any(d.isdigit() for d in caracteres[:i]) and any(
            d.isdigit() for d in caracteres[i + 1 :]
        )
        # Letra final só conta se estiver colada a um dígito: "170076O" sim,
        # "1.234.567 DO STJ" não.
        na_ponta = i == len(caracteres) - 1 and i > 0 and caracteres[i - 1].isdigit()
        if cercado or na_ponta:
            caracteres[i] = OCR_PARA_DIGITO[c]
    return "".join(caracteres)


def separar_uf(trecho: str) -> tuple[str, str | None]:
    """Separa o sufixo de UF do resto da citação.

    ``"REsp 1.234.567/SP"`` → ``("REsp 1.234.567", "SP")``. Fazemos isso antes de
    qualquer correção de OCR: sem separar, o ``S`` de ``/SP`` vira ``5`` e entra
    no número.
    """
    m = SUFIXO_UF.search(trecho)
    if not m:
        return trecho, None
    return trecho[: m.start()], m.group(1)


def digitos_do_identificador(trecho: str) -> str:
    """Extrai o número do processo de um trecho de citação, só com dígitos.

    Devolve string vazia quando não há núcleo numérico plausível.
    """
    texto = re.sub(r"\s+", " ", trecho.replace("\\n", "\n")).strip()
    texto, _ = separar_uf(texto)
    melhor = ""
    for m in NUCLEO_NUMERICO.finditer(texto):
        digitos = re.sub(r"\D", "", _traduzir_interior(m.group()))
        if len(digitos) > len(melhor):
            melhor = digitos
    return melhor


def numeros_do_texto(texto: str) -> set[str]:
    """Todos os números presentes num texto, em forma canônica (só dígitos).

    Usado para indexar a base canônica. Diferente de
    ``digitos_do_identificador``, aqui não corrigimos OCR: a base é limpa.
    """
    padrao = re.compile(r"\d+(?:[.\-\s ]+\d+)*")
    return {re.sub(r"\D", "", m.group()) for m in padrao.finditer(texto)}
