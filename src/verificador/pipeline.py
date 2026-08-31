"""Orquestra as etapas: texto → detecção → resolução → contrato."""

from __future__ import annotations

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
    """Processa todos os .txt de uma pasta. Devolve os JSONs escritos."""
    escritos: list[Path] = []
    for caminho in sorted(entrada.glob("*.txt")):
        escritos.append(processar_arquivo(caminho, base).escrever(saida))
    return escritos
