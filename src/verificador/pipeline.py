"""Orquestra as etapas: texto → detecção → resolução → contrato."""

from __future__ import annotations

import sys
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


def processar_pasta(entrada: Path, saida: Path, base: BaseCanonica) -> list[Path]:
    """Processa todos os .txt de uma pasta. Devolve os JSONs escritos.

    Um documento que falha sai **vazio**, e o lote segue. Sem isso, uma exceção
    num único arquivo interrompia o laço e os documentos seguintes ficavam sem
    JSON — e documento sem linha na submissão faz o avaliador oficial rejeitar
    a submissão **inteira**. Medido: um `.txt` em latin-1 no começo da pasta
    deixava 0 de 27 JSONs escritos. Citação não extraída custa recall de um
    documento; submissão rejeitada custa todos.
    """
    escritos: list[Path] = []
    for caminho in sorted(entrada.glob("*.txt")):
        try:
            documento = processar_arquivo(caminho, base)
        except Exception as erro:  # noqa: BLE001 — qualquer falha, o lote segue
            print(f"falha em {caminho.name}: {erro!r}; saída vazia", file=sys.stderr)
            documento = SaidaDocumento(documento_id=documento_id(caminho), citacoes=[])
        escritos.append(documento.escrever(saida))
    return escritos
