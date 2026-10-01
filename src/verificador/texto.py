"""Leitura dos documentos de entrada e detecção do fim do cabeçalho.

Offsets são em codepoints sobre o texto NFC, com fim exclusivo (``texto[inicio:fim]``).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def carregar(caminho: Path) -> str:
    """Lê um .txt de entrada e devolve o texto em NFC.

    Byte inválido vira U+FFFD em vez de exceção, e `newline=""` evita que a
    tradução de CRLF desloque os offsets.
    """
    with caminho.open(encoding="utf-8", errors="replace", newline="") as arquivo:
        return unicodedata.normalize("NFC", arquivo.read())


def documento_id(caminho: Path) -> str:
    """O nome do arquivo sem extensão é o ``documento_id`` do contrato."""
    return caminho.stem


# Rótulos que aparecem sem dois-pontos; "Rótulo: valor" já é reconhecido pela forma.
_ROTULOS = (
    "autos",
    "processo",
    "protocolo",
    "recurso",
    "origem",
    "refer",
    "ref.",
    "classe",
    "valor da causa",
    "oab",
    "fls",
)

# A linha precisa *ser* o rótulo (com no máximo um complemento curto), não só
# começar com ele: "Recurso especial interposto contra…" é prosa, e lida como
# cabeçalho empurraria a fronteira e perderia a citação daquela linha.
_APOS_ROTULO = re.compile(r"^[\s:\-–—]*(?:[\wÀ-ÿ.ºo°/\-]+\s*){0,2}$")

_LINHA_ROTULADA = re.compile(r"^[^\s:][^:]{0,40}:\s")

# "<rótulo> nº <número>" (`Autos nº 123…`), reconhecido pela estrutura e não
# pelo léxico, para sobreviver à corrupção de OCR no rótulo.
_LINHA_NUMERADA = re.compile(
    # O rótulo admite dígito no meio porque o OCR troca letra por dígito (`Prot0colo`).
    r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.0-9]{2,19}(?:\s+[A-Za-zÀ-ÿ.0-9]{1,15}){0,2}"
    r"\s+[nN]\s*[.ºo°O]{0,2}\s*"
    # Valor sem palavra minúscula de 4+ letras: barra prosa como "decidido no
    # REsp 1.234.567. O recurso…", em que o "no" seria lido como "nº".
    r"(?!.*(?<![\wÀ-ÿ])[a-zà-ÿ]{4,}(?![\wÀ-ÿ]))"
    r"[\w][\w.\-/ ]*$"
)


def _e_linha_de_cabecalho(linha: str) -> bool:
    """Metadado, título ou linha em branco — qualquer coisa que não seja prosa."""
    despida = linha.strip()
    if not despida:
        return True
    if _LINHA_ROTULADA.match(despida) or _LINHA_NUMERADA.match(despida):
        return True
    minusculo = despida.lower()
    if any(
        minusculo.startswith(rotulo) and _APOS_ROTULO.match(despida[len(rotulo) :])
        for rotulo in _ROTULOS
    ):
        return True
    # Título: sem minúsculas próprias (ignorando conectivos curtos como "de").
    letras = [c for c in despida if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) / len(letras) >= 0.8:
        return True
    return _e_titulo_corrompido(despida)


# Título corrompido por OCR (`MErn0RIAL`) perde a proporção de maiúsculas; as
# trocas são desfeitas antes de medir, só em linha curta sem pontuação de prosa.
_TROCAS_DE_TITULO = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "6": "G", "2": "Z"})
_LIGADURAS_DE_OCR = re.compile(r"rn|ri|ii")


def _e_titulo_corrompido(linha: str) -> bool:
    if len(linha) > 80 or re.search(r"[,;:.!?]", linha):
        return False
    palavras = linha.split()
    if not palavras or len(palavras) > 8:
        return False
    desfeito = _LIGADURAS_DE_OCR.sub("M", linha.translate(_TROCAS_DE_TITULO))
    letras = [c for c in desfeito if c.isalpha()]
    return bool(letras) and sum(c.isupper() for c in letras) / len(letras) >= 0.8


def fim_do_cabecalho(texto: str) -> int:
    """Offset da primeira linha de prosa, onde termina o bloco de metadados.

    O número dos autos do próprio documento, no cabeçalho, é distrator, não
    citação. Sem fronteira clara devolve 0, o conservador para o recall.
    """
    posicao = 0
    for linha in texto.splitlines(keepends=True):
        if not _e_linha_de_cabecalho(linha):
            return posicao
        posicao += len(linha)
    return 0
