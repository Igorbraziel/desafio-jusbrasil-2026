"""Leitura de documentos de entrada.

Regra rígida do desafio: UTF-8 sem BOM, quebra de linha LF, Unicode NFC, e
offsets em **codepoints Unicode** a partir de 0, com fim exclusivo
(``texto[inicio:fim]``). Os arquivos são distribuídos já normalizados; aplicamos
NFC de novo apenas por segurança — em texto já normalizado a operação é
idempotente e não desloca nenhum offset.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path


def carregar(caminho: Path) -> str:
    """Lê um .txt de entrada e devolve o texto em NFC."""
    return unicodedata.normalize("NFC", caminho.read_text(encoding="utf-8"))


def documento_id(caminho: Path) -> str:
    """O nome do arquivo sem extensão é o ``documento_id`` do contrato."""
    return caminho.stem


def fim_do_cabecalho(texto: str) -> int:
    """Offset onde termina o bloco de metadados e começa o corpo do documento.

    **A IMPLEMENTAR.**

    O cabeçalho de um parecer é um bloco de metadados — número dos autos,
    partes, protocolo, valor da causa — que vem antes da primeira linha de
    prosa. Nada dali é citação: são justamente os distratores.

    A fronteira importa porque o mesmo formato CNJ muda de natureza conforme a
    posição: o número dos autos do *próprio* documento, no cabeçalho, é
    distrator; a referência a *outro* processo, no corpo, é citação.
    """
    raise NotImplementedError
