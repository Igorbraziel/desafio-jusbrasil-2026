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

# Um pedaço sem espaço, feito só de alfanuméricos e pontuação de número. É o
# candidato a "isto é um número com letras dentro".
_TOKEN = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-–—/]*[0-9A-Za-z]|[0-9A-Za-z]")

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

# Sufixo de UF: separador, uma ou duas letras, e um fecha-parênteses opcional.
#
# Uma letra só parece estranho e é necessário: a detecção ancora o número num
# núcleo que aceita letras de OCR como continuação, então num span terminado em
# `/SP` ela engole o `S` e deixa o `P` de fora. Número de
# processo não termina em barra mais letra — isso é UF truncada, e deixá-la
# passar faz o `S` virar `5` e corromper o identificador.
_SUFIXO_UF = re.compile(rf"\s*[/({_HIFENS}]\s*([A-Za-z]{{1,2}})\s*\)?[\s.]*$")

_ESPACOS = re.compile(r"\s+")


def sem_acento(texto: str) -> str:
    """Remove diacríticos, inclusive os que o OCR põe na vogal errada."""
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
    # Duas letras só saem se formarem UF de verdade; uma letra sai sempre, por
    # ser UF truncada pela detecção (ver o comentário em _SUFIXO_UF).
    if len(uf) == 2 and uf not in UFS:
        return trecho.strip(), None
    return trecho[: casamento.start()].strip(), uf


def _token_e_numero(token: str) -> bool:
    """O token é um número cujas letras são todas confusões de OCR?

    Três exigências, e cada uma barra um falso positivo concreto:

    * **pelo menos um dígito** — senão ``SOS`` e ``Gols``, que são só letras
      confundíveis, virariam números;
    * **toda letra mapeável** — ``DO`` tem o ``D`` e ``STJ`` tem o ``J``, que
      não são confusões de dígito; os dois ficam de fora;
    * **pelo menos dois alfanuméricos**, para não converter letra solta.
    """
    alfanumericos = [c for c in token if c.isalnum()]
    if len(alfanumericos) < 2 or not any(c.isdigit() for c in alfanumericos):
        return False
    return all(not c.isalpha() or c in OCR_PARA_DIGITO for c in alfanumericos)


def _corrigir_ocr(trecho: str) -> str:
    """Desfaz as trocas de letra por dígito dentro do identificador.

    Duas passadas, e a primeira existe porque a segunda não basta.

    A regra de adjacência sozinha — converter a letra só quando ela encosta num
    dígito — falha quando o ruído corrompe posições **consecutivas**. Num número
    sintético, ``9.876.543`` corrompido para ``g.B7G.S43``: o ``g`` inicial e o
    ``B`` seguinte não encostam em nenhum dígito sobrevivente, ficam como letra,
    e o núcleo resultante perde os dígitos da frente.

    Medido sob perturbação, essa era a causa de quase metade das citações
    ``real`` ficarem irrecuperáveis quando o ruído saía das posições vistas na
    amostra.

    A primeira passada olha o **token inteiro**: se ele é feito só de dígitos e
    letras confundíveis, é um número, e todas as letras convertem de uma vez. A
    segunda mantém a adjacência para o que sobrou, que é o caso de uma letra
    isolada colada ao número (``21737l8``, ``170076O``).
    """
    caracteres = list(trecho)

    for casamento in _TOKEN.finditer(trecho):
        if not _token_e_numero(casamento.group()):
            continue
        for i in range(casamento.start(), casamento.end()):
            substituto = OCR_PARA_DIGITO.get(trecho[i])
            if substituto is not None:
                caracteres[i] = substituto

    for i, caractere in enumerate(trecho):
        substituto = OCR_PARA_DIGITO.get(caractere)
        if substituto is None or caracteres[i] != caractere:
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
