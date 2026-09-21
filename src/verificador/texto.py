"""Leitura de documentos de entrada.

Regra rígida do desafio: UTF-8 sem BOM, quebra de linha LF, Unicode NFC, e
offsets em **codepoints Unicode** a partir de 0, com fim exclusivo
(``texto[inicio:fim]``). Os arquivos são distribuídos já normalizados; aplicamos
NFC de novo apenas por segurança — em texto já normalizado a operação é
idempotente e não desloca nenhum offset.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def carregar(caminho: Path) -> str:
    """Lê um .txt de entrada e devolve o texto em NFC."""
    return unicodedata.normalize("NFC", caminho.read_text(encoding="utf-8"))


def documento_id(caminho: Path) -> str:
    """O nome do arquivo sem extensão é o ``documento_id`` do contrato."""
    return caminho.stem


# Rótulos de metadado. A lista não precisa ser exaustiva: uma linha "Rótulo:
# valor" já é reconhecida pela forma, e estes cobrem os que vêm sem dois-pontos.
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

# "Rótulo: valor" — o rótulo é curto e a linha tem dois-pontos cedo.
_LINHA_ROTULADA = re.compile(r"^[^\s:][^:]{0,40}:\s")

# "<rótulo> nº <número>", sem dois-pontos — a forma de `Autos nº 123…`.
#
# Reconhecer pela **estrutura** e não pelo léxico é o que torna isto robusto: o
# nível 2 corrompe uma letra por palavra, e uma lista de rótulos exatos não
# sobrevive a isso. Medido, com o rótulo corrompido em uma letra a fronteira do
# cabeçalho caía de 90 para 28 e o número do **próprio** processo — o distrator
# canônico do desafio — passava a ser extraído como citação.
_LINHA_NUMERADA = re.compile(
    # O rótulo começa em letra mas admite dígito no meio: o OCR troca letra por
    # dígito também (`Protocolo` -> `Prot0colo`), e exigir só letras reabre a
    # brecha que esta expressão fecha.
    r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.0-9]{2,19}(?:\s+[A-Za-zÀ-ÿ.0-9]{1,15}){0,2}"
    r"\s+[nN]\s*[.ºo°O]{0,2}\s*[\w][\w.\-/ ]*$"
)


def _e_linha_de_cabecalho(linha: str) -> bool:
    """Metadado, título ou linha em branco — qualquer coisa que não seja prosa."""
    despida = linha.strip()
    if not despida:
        return True
    if _LINHA_ROTULADA.match(despida) or _LINHA_NUMERADA.match(despida):
        return True
    minusculo = despida.lower()
    if any(minusculo.startswith(rotulo) for rotulo in _ROTULOS):
        return True
    # Título: sem minúsculas próprias (ignorando conectivos curtos como "de").
    letras = [c for c in despida if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) / len(letras) >= 0.8:
        return True
    return False


def fim_do_cabecalho(texto: str) -> int:
    """Offset onde termina o bloco de metadados e começa o corpo do documento.

    O cabeçalho de um parecer é um bloco de metadados — número dos autos,
    partes, protocolo, valor da causa — que vem antes da primeira linha de
    prosa. Nada dali é citação: são justamente os distratores.

    A fronteira importa porque o mesmo formato CNJ muda de natureza conforme a
    posição: o número dos autos do *próprio* documento, no cabeçalho, é
    distrator; a referência a *outro* processo, no corpo, é citação.

    Devolve o offset do início da primeira linha de prosa. Se o documento for só
    cabeçalho — ou só prosa — devolve 0, que é o conservador: perder uma citação
    custa recall, e recall é o que não se recupera depois.
    """
    posicao = 0
    for linha in texto.splitlines(keepends=True):
        if not _e_linha_de_cabecalho(linha):
            return posicao
        posicao += len(linha)
    return 0
