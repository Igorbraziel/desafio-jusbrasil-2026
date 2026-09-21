"""Segmentação estrutural de um acórdão em zonas.

Um acórdão não é texto corrido: tem cabeçalho de identificação, ementa,
relatório, voto e dispositivo, e **o número do próprio processo só aparece em
algumas dessas zonas**. Nas outras, todo número é citação de outro processo —
a armadilha que mais custa precisão (``docs/dados.md``, armadilha 5).

Este módulo existe para que essa distinção seja estrutural em vez de posicional.
A alternativa que ele substitui era uma janela de offset fixo, que funciona nos
tribunais regulares e quebra no TST, onde o número próprio fica por volta do
caractere 1.000 em vez do cabeçalho.

**Uma espécie, um parser.** Medindo a presença de marcadores nos 996 acórdãos da
base, os cinco tribunais não compartilham estrutura:

======  ======  =========  ======  ==============  =========
marca     STF      STJ       STM        TSE          TST
======  ======  =========  ======  ==============  =========
EMENTA    86%      99%      100%        **8%**       36%
RELATÓRIO 86%      98%      100%        97%          **3%**
VOTO      92%      98%      100%        99%          **2%**
======  ======  =========  ======  ==============  =========

TSE quase não usa EMENTA; TST quase não usa RELATÓRIO nem VOTO, e no lugar
deles traz a fórmula ``Vistos, relatados e discutidos estes autos de … nº TST-…``.
Um segmentador único erraria nos dois.

**Invariantes**, verificados em ``tests/test_estrutura.py``:

1. as zonas **ladrilham** o documento, sem buraco nem sobreposição;
2. ``texto[z.inicio:z.fim] == z.texto`` para toda zona — ancoragem, o que separa
   extração de invenção;
3. a saída nunca é vazia: sem marcador nenhum, o documento inteiro vira
   ``cabecalho``, que é o degradado seguro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

# As zonas onde o número do **próprio** processo aparece. Fora daqui, número é
# citação de outro julgado — indexá-lo faz o registro errado responder por ele.
ZONAS_IDENTIFICADORAS = frozenset({"cabecalho", "identificacao"})

# Ordem canônica, para relatório e ordenação estável.
ZONAS = ("cabecalho", "identificacao", "ementa", "relatorio", "voto", "dispositivo", "corpo")


@dataclass(frozen=True)
class Zona:
    """Um trecho contíguo do documento, ancorado por offset."""

    tipo: str
    inicio: int
    fim: int
    texto: str

    @property
    def n_chars(self) -> int:
        return self.fim - self.inicio


@dataclass(frozen=True)
class Marcador:
    """Uma fronteira de zona: onde ela começa e até onde pode ir."""

    zona: str
    padrao: re.Pattern[str]
    # Tamanho máximo. Só a `identificacao` usa: a fórmula de abertura do voto
    # identifica o processo nos primeiros ~200 caracteres e depois emenda na
    # lista de partes, que não identifica nada.
    limite: int | None = None


def _p(padrao: str, *, i: bool = False) -> re.Pattern[str]:
    return re.compile(padrao, re.IGNORECASE if i else 0)


# A fórmula de abertura do voto. "estes autos" quer dizer *estes*: é o que
# distingue o processo próprio dos que o acórdão apenas cita.
_ESTES_AUTOS = _p(r"(?:Vistos,?\s+relatados|[Ee]st[eo]s\s+autos)")

_EMENTA = _p(r"\bEMENTA\b")
_RELATORIO = _p(r"\bRELAT[ÓO]RIO\b")
_VOTO = _p(r"\bV\s?O\s?T\s?O\b")
_ACORDAM = _p(r"\bACORDAM\b|\bAcordam\b")

# Ordem em que as zonas aparecem, por tribunal. A busca é sequencial: cada
# marcador só é procurado depois do anterior, então a ordem da tupla é a ordem
# no documento — e um marcador ausente simplesmente não abre zona.
_ORDEM: dict[str, tuple[Marcador, ...]] = {
    "STF": (
        Marcador("ementa", _EMENTA),
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("relatorio", _RELATORIO),
        Marcador("voto", _VOTO),
        Marcador("dispositivo", _ACORDAM),
    ),
    "STJ": (
        Marcador("ementa", _EMENTA),
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("relatorio", _RELATORIO),
        Marcador("voto", _VOTO),
    ),
    "STM": (
        Marcador("ementa", _EMENTA),
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("relatorio", _RELATORIO),
        Marcador("voto", _VOTO),
    ),
    # TSE quase não marca EMENTA (8%): procurá-la primeiro consumiria o
    # RELATÓRIO em 92% dos casos, porque a busca é sequencial.
    "TSE": (
        Marcador("relatorio", _RELATORIO),
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("voto", _VOTO),
    ),
    # TST não usa RELATÓRIO nem VOTO (3% e 2%); a fórmula de abertura é o único
    # marcador confiável, e é onde o número próprio mora.
    "TST": (
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("ementa", _EMENTA),
        Marcador("dispositivo", _ACORDAM),
    ),
}

# Ordem genérica, para tribunal desconhecido: a união dos marcadores comuns.
_ORDEM_GENERICA: tuple[Marcador, ...] = (
    Marcador("identificacao", _ESTES_AUTOS, limite=400),
    Marcador("ementa", _EMENTA),
    Marcador("relatorio", _RELATORIO),
    Marcador("voto", _VOTO),
    Marcador("dispositivo", _ACORDAM),
)

# Assinaturas de tribunal. São **estruturais**, não acrônimos: `\bSTF\b` aparece
# em acórdão do TST que cita o STF, e medindo isso a inferência por sigla solta
# acertava só 71%. O que distingue de verdade é a forma do cabeçalho — STF
# abrevia "MIN." onde o STJ escreve "MINISTRO", e o TST espaça as letras de
# "A C Ó R D Ã O".
_ASSINATURAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TST", _p(r"A\s+C\s+[ÓO]\s+R\s+D\s+[ÃA]\s+O|\bSbDI\b|\bTST-[A-Z]")),
    ("STM", _p(r"Poder\s+Judici[áa]rio\s+STM|SUPERIOR\s+TRIBUNAL\s+MILITAR", i=True)),
    ("TSE", _p(r"TRI[EB]UNAL\s+SUPERIOR\s+ELEITORAL", i=True)),
    ("STJ", _p(r"RELATOR[A]?\s*:\s*MINISTR|\(\d{4}/\d{6,8}-\d\)")),
    ("STF", _p(r"RELATOR[A]?\s*:\s*MIN\.|SUPREMO\s+TRIBUNAL\s+FEDERAL", i=True)),
)

# A assinatura tem de estar no cabeçalho. Mais adiante o documento cita outros
# tribunais, e a inferência passa a ler a citação em vez da identidade.
_JANELA_ASSINATURA = 1500

# Teto do cabeçalho. Sem ele, um documento onde nenhum marcador casa cedo tem
# "cabeçalho" até o primeiro marcador que aparecer — medido no STF, isso levava
# a região de identificação a 34.000 caracteres no p90 e a 78.510 no pior caso,
# o que enche o índice de números citados.
#
# O valor sai de varredura, não de escolha: nos quatro tribunais que põem o
# número no cabeçalho, a primeira ocorrência dele cai entre os caracteres 19 e
# 123, então 300 dá 2,4x de folga sobre o pior caso observado.
#
#   limite   órfãos   ambíguos      (recall 77/77 e FP 0 em toda a faixa)
#      150       27        180
#      250       25        217
#      300       25        239   <- aqui
#     1500       24        397
#
# Órfão é registro que citação nenhuma alcança; ambíguo é número que dois ou
# mais registros reivindicam. Entre 250 e 300 os órfãos empatam, e 300 leva a
# folga: truncar cabeçalho num formato não visto custa mais caro que
# ambiguidade, que afeta uma única citação do gabarito e já tem desempate
# definido (docs/decisoes/0003).
LIMITE_CABECALHO = 300


def tribunal_do_texto(texto: str) -> str | None:
    """Infere o tribunal pela forma do cabeçalho. ``None`` quando não dá.

    Best-effort: no caminho normal o tribunal vem da coluna do banco, e esta
    função serve a documento solto. A precisão medida está em
    ``docs/checkpoints/01-parser-de-zonas.md``.
    """
    cabecalho = texto[:_JANELA_ASSINATURA]
    for tribunal, assinatura in _ASSINATURAS:
        if assinatura.search(cabecalho):
            return tribunal
    return None


def _fronteiras(texto: str, ordem: tuple[Marcador, ...]) -> list[tuple[int, Marcador]]:
    """Posição de cada marcador, em ordem, sem voltar atrás."""
    encontradas: list[tuple[int, Marcador]] = []
    posicao = 0
    for marcador in ordem:
        casamento = marcador.padrao.search(texto, posicao)
        if casamento is None:
            continue
        encontradas.append((casamento.start(), marcador))
        posicao = casamento.end()
    return encontradas


def segmentar(texto: str, tribunal: str | None = None) -> list[Zona]:
    """Divide o acórdão em zonas contíguas que ladrilham o documento.

    ``tribunal`` escolhe a estratégia; quando ``None``, é inferido do texto e,
    se nem isso funcionar, cai na ordem genérica.
    """
    if not texto:
        return []

    escolhido = (tribunal or tribunal_do_texto(texto) or "").upper()
    ordem = _ORDEM.get(escolhido, _ORDEM_GENERICA)

    zonas: list[Zona] = []
    cursor = 0

    def emitir(tipo: str, inicio: int, fim: int) -> None:
        if fim > inicio:
            zonas.append(Zona(tipo, inicio, fim, texto[inicio:fim]))

    def emitir_preambulo(inicio: int, fim: int) -> None:
        """O trecho antes de uma fronteira: cabeçalho na primeira vez, corpo depois.

        O cabeçalho é limitado; o que passar do teto vira corpo, para o
        ladrilhamento continuar íntegro sem inchar a zona identificadora.
        """
        if fim <= inicio:
            return
        if zonas:
            emitir("corpo", inicio, fim)
            return
        corte = min(fim, inicio + LIMITE_CABECALHO)
        emitir("cabecalho", inicio, corte)
        emitir("corpo", corte, fim)

    fronteiras = _fronteiras(texto, ordem)
    for indice, (inicio, marcador) in enumerate(fronteiras):
        # O que vem antes da primeira fronteira é cabeçalho; entre fronteiras, o
        # resto da zona anterior já foi emitido no passo anterior.
        emitir_preambulo(cursor, inicio)

        proxima = fronteiras[indice + 1][0] if indice + 1 < len(fronteiras) else len(texto)
        fim = min(inicio + marcador.limite, proxima) if marcador.limite else proxima
        emitir(marcador.zona, inicio, fim)
        cursor = fim

    emitir_preambulo(cursor, len(texto))
    return zonas


def zonas_de_identificacao(texto: str, tribunal: str | None = None) -> list[Zona]:
    """Só as zonas onde o número do próprio processo pode aparecer."""
    return [z for z in segmentar(texto, tribunal) if z.tipo in ZONAS_IDENTIFICADORAS]
