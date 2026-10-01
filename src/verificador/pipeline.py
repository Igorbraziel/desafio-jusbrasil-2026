"""Orquestra as etapas: texto → detecção → resolução → contrato."""

from __future__ import annotations

import signal
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from .base import BaseCanonica
from .deteccao import detectar
from .resolucao import resolver
from .saida.contrato import Citacao, SaidaDocumento
from .texto import carregar, documento_id


def processar_texto(doc_id: str, texto: str, base: BaseCanonica) -> SaidaDocumento:
    citacoes: list[Citacao] = []
    for indice, achado in enumerate(detectar(texto), start=1):
        classificacao, id_canonico, confianca = resolver(achado, base)
        citacoes.append(
            Citacao(
                id=f"c{indice}",
                inicio=achado.inicio,
                fim=achado.fim,
                trecho=achado.trecho,
                tipo=achado.tipo,
                classificacao=classificacao,
                id_canonico=id_canonico,
                confianca=confianca,
            )
        )
    return SaidaDocumento(documento_id=doc_id, citacoes=citacoes)


def processar_arquivo(caminho: Path, base: BaseCanonica) -> SaidaDocumento:
    return processar_texto(documento_id(caminho), carregar(caminho), base)


# Teto por documento contra o caso patológico (backtracking de regex), que
# travaria o lote inteiro. Folgado porque o tempo cresce com o quadrado do tamanho.
TIMEOUT_POR_DOCUMENTO = 120.0


class _Estourou(Exception):
    pass


def _alarme(*_) -> None:
    raise _Estourou()


def _eh_txt(caminho: Path) -> bool:
    return caminho.is_file() and caminho.suffix.lower() == ".txt"


def processar_pasta(entrada: Path, saida: Path, base: BaseCanonica) -> list[Path]:
    """Processa todos os .txt de uma pasta e devolve os JSONs escritos.

    Documento que falha sai vazio e o lote segue: documento sem linha faria a
    submissão inteira ser rejeitada.
    """
    paths = sorted(p for p in entrada.iterdir() if _eh_txt(p))
    return [document.escrever(saida) for document in process_files(paths, base)]


def process_files(paths: Iterable[Path], base: BaseCanonica) -> Iterator[SaidaDocumento]:
    """Processa cada arquivo sob `TIMEOUT_POR_DOCUMENTO`; o que falha sai vazio."""
    previous_handler = signal.signal(signal.SIGALRM, _alarme)
    try:
        for path in paths:
            yield _process_with_timeout(path, base)
    finally:
        signal.signal(signal.SIGALRM, previous_handler)


def _process_with_timeout(path: Path, base: BaseCanonica) -> SaidaDocumento:
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT_POR_DOCUMENTO)
    try:
        return processar_arquivo(path, base)
    except _Estourou:
        print(f"tempo esgotado em {path.name}; saída vazia", file=sys.stderr)
    except Exception as error:  # noqa: BLE001 — qualquer falha, o lote segue
        print(f"falha em {path.name}: {error!r}; saída vazia", file=sys.stderr)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return SaidaDocumento(documento_id=documento_id(path), citacoes=[])
