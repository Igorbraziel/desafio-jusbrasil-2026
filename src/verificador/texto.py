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

# O cabeçalho de um parecer é um bloco de metadados — número dos autos, partes,
# protocolo, valor da causa — que vem antes da primeira linha de prosa. Nada dali
# é citação: são justamente os distratores. Reconhecemos essas linhas pela forma.
ROTULO = re.compile(r"^\s*[\wÀ-ÿ][\wÀ-ÿ .º°/()-]{0,40}:")
CAMPO = re.compile(
    r"^\s*(?:Processo|Autos|Memorial|Parecer|Protocolo|Of[íi]cio|Refer[êe]ncia"
    r"|Peti[çc][ãa]o|Inscri[çc][ãa]o|Valor)\b",
    re.IGNORECASE,
)
# Se nada parecer prosa, desistimos depois deste número de linhas.
MAXIMO_LINHAS_DE_CABECALHO = 20


def carregar(caminho: Path) -> str:
    """Lê um .txt de entrada e devolve o texto em NFC."""
    return unicodedata.normalize("NFC", caminho.read_text(encoding="utf-8"))


def _e_linha_de_cabecalho(linha: str) -> bool:
    nu = linha.strip()
    if not nu:
        return True
    letras = [c for c in nu if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) / len(letras) > 0.8:
        return True  # título ou nome de órgão em caixa alta
    return bool(ROTULO.match(nu) or CAMPO.match(nu))


def fim_do_cabecalho(texto: str) -> int:
    """Offset onde termina o bloco de metadados e começa o corpo do documento.

    O número dos autos do próprio documento, o protocolo, a inscrição na OAB e o
    valor da causa aparecem no cabeçalho e contam como falso positivo se
    extraídos. Já uma referência a *outro* processo, no corpo do texto, é
    citação — daí a fronteira importar.
    """
    posicao = 0
    for numero, linha in enumerate(texto.splitlines(keepends=True)):
        if numero >= MAXIMO_LINHAS_DE_CABECALHO:
            break
        if not _e_linha_de_cabecalho(linha):
            return posicao
        posicao += len(linha)
    return posicao


def documento_id(caminho: Path) -> str:
    """O nome do arquivo sem extensão é o ``documento_id`` do contrato."""
    return caminho.stem
