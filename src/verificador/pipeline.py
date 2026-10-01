"""Orquestra as etapas: texto → detecção → resolução → contrato."""

from __future__ import annotations

import signal
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from .base_canonica import BaseCanonica
from .contrato import Citacao, SaidaDocumento
from .deteccao import detectar
from .resolucao import resolver
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


# Tempo máximo por documento. O envelope da organização dá em média 60 s por
# documento e 4 h para o lote; o pipeline leva milissegundos. O teto só existe
# para o caso patológico — backtracking catastrófico já travou este código duas
# vezes —, em que um documento que não termina custaria o lote inteiro.
#
# O tempo cresce com o quadrado do tamanho: 0,7 s a 244 KB, e um arquivo de
# 1,26 MB estourava os 30 s de antes e saía vazio. Os documentos do gerador têm
# 3–4 KB, mas 120 s ainda cabem com folga nas 4 h do lote e só cortam o que de
# fato não termina.
TIMEOUT_POR_DOCUMENTO = 120.0


class _Estourou(Exception):
    pass


def _alarme(*_) -> None:
    raise _Estourou()


def _eh_txt(caminho: Path) -> bool:
    return caminho.is_file() and caminho.suffix.lower() == ".txt"


def processar_pasta(entrada: Path, saida: Path, base: BaseCanonica) -> list[Path]:
    """Processa todos os .txt de uma pasta. Devolve os JSONs escritos.

    Um documento que falha — ou que estoura `TIMEOUT_POR_DOCUMENTO` — sai
    **vazio**, e o lote segue. Sem isso, uma exceção num único arquivo
    interrompia o laço e os documentos seguintes ficavam sem JSON — e documento
    sem linha na submissão faz o avaliador oficial rejeitar a submissão
    **inteira**. Medido: um `.txt` em latin-1 no começo da pasta deixava 0 de 27
    JSONs escritos. Citação não extraída custa recall de um documento; submissão
    rejeitada custa todos.

    A extensão é conferida sem distinguir caixa: um `.TXT` ficaria sem JSON.
    """
    paths = sorted(p for p in entrada.iterdir() if _eh_txt(p))
    return [document.escrever(saida) for document in process_files(paths, base)]


def process_files(paths: Iterable[Path], base: BaseCanonica) -> Iterator[SaidaDocumento]:
    """Processa cada arquivo sob `TIMEOUT_POR_DOCUMENTO`; o que falha sai vazio.

    É a proteção de `processar_pasta` sem a varredura da pasta nem a escrita. A
    entrega (`cli`) coleta os arquivos do seu jeito e grava o CSV, e diante de um
    documento que falha ou trava as duas precisam do mesmo comportamento.

    Gerador: cada documento sai logo depois de processado, e quem consome decide
    se o grava antes do próximo — `processar_pasta` grava, como sempre gravou.
    """
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
