"""Normalização de superfície: ruído de documento → forma canônica.

**A IMPLEMENTAR.** É aqui que o nível 2 se decide, e é a etapa que mais pesa na
nota — o nível 2 vale o dobro.

As citações do nível 2 apontam para registros tão válidos quanto as do nível 1;
o que muda é a escrita. A organização garante que **um dígito nunca é trocado
por outro dígito**: todo ruído aplicado a uma citação real é recuperável por
normalização. Ou seja, não há incerteza irredutível aqui — só trabalho.

O ruído observado na amostra de desenvolvimento (ver ``docs/investigacao.md``):

* variantes de abreviação — ``REsp`` / ``R.Esp.`` / ``Recurso Especial``;
* formatação do número — ``1.741.784`` / ``1741784`` / ``1.741. 784``;
* separador de UF — ``/PR``, ``- PR``, ``(PR)``, ``– PR``;
* confusões de OCR — ``0↔O``, ``1↔l``, ``5↔S``, ``m↔rn``, e também ``9↔g``,
  ``6↔G``;
* quebra de linha no meio do identificador.

Duas armadilhas que valem ser antecipadas:

1. O sufixo de UF precisa sair **antes** de qualquer correção de OCR. Do
   contrário o ``S`` de ``/SP`` vira ``5`` e entra no número.
2. Pelo mesmo motivo, converter letra em dígito indiscriminadamente corrompe
   identificadores: o ``I`` final de ``AREspEI`` viraria ``1``.

Os testes em ``tests/test_normalizacao.py`` são a especificação desta etapa.
"""

from __future__ import annotations


def sem_acento(texto: str) -> str:
    """Remove diacríticos, inclusive os corrompidos (``Magãlhães``)."""
    raise NotImplementedError


def chave_textual(texto: str) -> str:
    """Forma comparável de um trecho: minúsculas, sem acento, espaços colapsados."""
    raise NotImplementedError


def separar_uf(trecho: str) -> tuple[str, str | None]:
    """Separa o sufixo de UF do resto da citação.

    ``"REsp 1.234.567/SP"`` → ``("REsp 1.234.567", "SP")``.
    """
    raise NotImplementedError


def digitos_do_identificador(trecho: str) -> str:
    """Extrai o número do processo de um trecho de citação, só com dígitos.

    Devolve string vazia quando não há núcleo numérico plausível.
    """
    raise NotImplementedError


def numeros_do_texto(texto: str) -> set[str]:
    """Todos os números de um texto em forma canônica (só dígitos).

    Usado para indexar a base canônica. Diferente de
    :func:`digitos_do_identificador`, aqui não é preciso corrigir OCR: a base é
    limpa.
    """
    raise NotImplementedError
