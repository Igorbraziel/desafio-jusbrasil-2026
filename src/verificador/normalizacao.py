"""Normalização de superfície: ruído de documento → forma canônica.

É aqui que o nível 2 se decide, e é a etapa que mais pesa na nota — o nível 2
vale o dobro.

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

A ordem das operações é o que decide a corretude, e as duas armadilhas são
simétricas:

1. O sufixo de UF sai **antes** de qualquer correção de OCR. Do contrário o
   ``S`` de ``/SP`` vira ``5`` e entra no número.
2. Letra só vira dígito quando está **colada** a um dígito. Sem essa restrição,
   ``REsp 1.234.567 DO STJ`` absorveria o ``O`` de ``DO``, e o ``I`` final de
   ``AREspEI`` viraria ``1``.

Os testes em ``tests/test_normalizacao.py`` são a especificação desta etapa.
"""

from __future__ import annotations

import re
import unicodedata

# As 27 unidades da federação. Usamos o conjunto fechado em vez de [A-Z]{2}
# para não amputar um sufixo que apenas se pareça com UF.
UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

# Confusões de OCR que trocam letra por dígito. Só se aplicam coladas a um
# dígito — ver a armadilha 2 no topo do módulo.
OCR_PARA_DIGITO = {
    "O": "0",
    "o": "0",
    "D": "0",
    "l": "1",
    "I": "1",
    "i": "1",
    "S": "5",
    "s": "5",
    "g": "9",
    "q": "9",
    "G": "6",
    "b": "6",
    "B": "8",
    "Z": "2",
    "z": "2",
}

# Todas as formas de hífen que aparecem nos documentos: ASCII, os seis traços do
# bloco de pontuação geral (‐ ‑ ‒ – — ―) e o sinal de menos.
_HIFENS = r"\-‐-―−"

# Pontuação que pode aparecer *dentro* de um número de processo no documento.
# Inclui espaço e quebra de linha, porque o nível 2 parte identificadores.
_PONTUACAO_NO_DOCUMENTO = rf"[\s.{_HIFENS}/]"

# Na base canônica o texto é limpo e não há espaço dentro do número. Manter o
# espaço fora daqui evita colar dois números vizinhos num só.
_PONTUACAO_NA_BASE = rf"[.{_HIFENS}/]"

# Um núcleo numérico começa e termina em dígito, com pontuação no meio.
_NUCLEO = re.compile(rf"\d(?:{_PONTUACAO_NO_DOCUMENTO}*\d)*")
_NUCLEO_LIMPO = re.compile(rf"\d(?:{_PONTUACAO_NA_BASE}*\d)*")

# Sufixo de UF: separador, duas letras e um fecha-parênteses opcional.
_SUFIXO_UF = re.compile(rf"\s*[/({_HIFENS}]\s*([A-Za-z]{{2}})\s*\)?[\s.]*$")

_ESPACOS = re.compile(r"\s+")


def sem_acento(texto: str) -> str:
    """Remove diacríticos, inclusive os corrompidos (``Magãlhães``)."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def chave_textual(texto: str) -> str:
    """Forma comparável de um trecho: minúsculas, sem acento, espaços colapsados."""
    return _ESPACOS.sub(" ", sem_acento(texto).lower()).strip()


def separar_uf(trecho: str) -> tuple[str, str | None]:
    """Separa o sufixo de UF do resto da citação.

    ``"REsp 1.234.567/SP"`` → ``("REsp 1.234.567", "SP")``.

    Precisa rodar antes da correção de OCR: sem isso o ``S`` de ``/SP`` vira
    ``5`` e entra no número.
    """
    casamento = _SUFIXO_UF.search(trecho)
    if casamento is None:
        return trecho.strip(), None
    uf = casamento.group(1).upper()
    if uf not in UFS:
        return trecho.strip(), None
    return trecho[: casamento.start()].strip(), uf


def _corrigir_ocr(trecho: str) -> str:
    """Troca letra por dígito **apenas** quando ela encosta num dígito.

    ``21737l8`` → ``2173718`` e ``170076O`` → ``1700760``, sem que
    ``REsp 1.234.567 DO STJ`` perca o ``DO`` para o número.
    """
    caracteres = list(trecho)
    for i, caractere in enumerate(caracteres):
        substituto = OCR_PARA_DIGITO.get(caractere)
        if substituto is None:
            continue
        anterior = trecho[i - 1] if i else ""
        seguinte = trecho[i + 1] if i + 1 < len(trecho) else ""
        if anterior.isdigit() or seguinte.isdigit():
            caracteres[i] = substituto
    return "".join(caracteres)


def digitos_do_identificador(trecho: str) -> str:
    """Extrai o número do processo de um trecho de citação, só com dígitos.

    Devolve string vazia quando não há núcleo numérico plausível.

    O maior núcleo vence: em ``REsp 1.234.567 de 2020`` o ano perde para o
    número do processo, porque a prosa entre os dois quebra a sequência.
    """
    sem_uf, _ = separar_uf(trecho)
    corrigido = _corrigir_ocr(sem_uf)
    nucleos = _NUCLEO.findall(corrigido)
    if not nucleos:
        return ""
    melhor = max(nucleos, key=lambda n: (sum(c.isdigit() for c in n), -corrigido.index(n)))
    return re.sub(r"\D", "", melhor)


def numeros_do_texto(texto: str) -> set[str]:
    """Todos os números de um texto em forma canônica (só dígitos).

    Usado para indexar a base canônica. Diferente de
    :func:`digitos_do_identificador`, aqui não é preciso corrigir OCR — a base
    não tem ruído de OCR.

    O espaço é ambíguo e por isso emitimos **as duas granularidades**: na maior
    parte da base ele separa dois números, mas o STM grava o número do processo
    com espaço no meio (``Nº 7000380- 08.2023.7.00.0000/DF``). Ler só a forma
    conservadora perderia esse registro; ler só a permissiva colaria números
    vizinhos. A união custa algumas entradas a mais no índice e não perde
    nenhuma — e o custo real de uma entrada sobrando é medido por
    ``scripts/medir_regiao.py``.
    """
    achados = _NUCLEO_LIMPO.findall(texto) + _NUCLEO.findall(texto)
    return {re.sub(r"\D", "", n) for n in achados} - {""}
