"""Segmentação estrutural de um acórdão em zonas (cabeçalho, ementa, relatório, voto...).

O número do próprio processo só aparece em algumas zonas; nas outras, todo número é
citação. Cada tribunal tem estrutura própria, então cada um tem sua ordem de marcadores.
As zonas ladrilham o documento, ``texto[z.inicio:z.fim] == z.texto`` e, sem marcador,
o documento inteiro vira ``cabecalho``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TRIBUNAIS = ("STF", "STJ", "TSE", "TST", "STM")

# Zonas onde o número do próprio processo aparece; fora delas, número é citação.
ZONAS_IDENTIFICADORAS = frozenset({"cabecalho", "identificacao"})

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
    # Tamanho máximo: a fórmula de abertura identifica o processo logo no início e
    # depois emenda na lista de partes, que não identifica nada.
    limite: int | None = None


def _p(padrao: str, *, i: bool = False) -> re.Pattern[str]:
    return re.compile(padrao, re.IGNORECASE if i else 0)


# Fórmula de abertura do voto: "estes autos" distingue o processo próprio dos citados.
# A forma solta exige fronteira de palavra e a classe em seguida, para não casar
# "destes autos" ou "nestes autos" na ementa.
_ESTES_AUTOS = _p(
    r"(?:Vistos,?\s+relatados\s+e\s+discutidos|\b[Ee]st[eo]s\s+autos\s+de\s+(?=[A-ZÀ-Ú]))"
)

_EMENTA = _p(r"\bEMENTA\b")
_RELATORIO = _p(r"\bRELAT[ÓO]RIO\b")
_VOTO = _p(r"\bV\s?O\s?T\s?O\b")
_ACORDAM = _p(r"\bACORDAM\b|\bAcordam\b")

# Ordem das zonas por tribunal. A busca é sequencial (cada marcador depois do
# anterior), e marcador ausente não abre zona.
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
    # TSE quase não marca EMENTA: procurá-la primeiro consumiria o RELATÓRIO.
    "TSE": (
        Marcador("relatorio", _RELATORIO),
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("voto", _VOTO),
    ),
    # TST quase não usa RELATÓRIO nem VOTO; a fórmula de abertura é o marcador confiável.
    "TST": (
        Marcador("identificacao", _ESTES_AUTOS, limite=400),
        Marcador("ementa", _EMENTA),
        Marcador("dispositivo", _ACORDAM),
    ),
}

# Tribunal desconhecido: a união dos marcadores comuns.
_ORDEM_GENERICA: tuple[Marcador, ...] = (
    Marcador("identificacao", _ESTES_AUTOS, limite=400),
    Marcador("ementa", _EMENTA),
    Marcador("relatorio", _RELATORIO),
    Marcador("voto", _VOTO),
    Marcador("dispositivo", _ACORDAM),
)

# Assinaturas estruturais, não siglas soltas (um acórdão cita outros tribunais): o STF
# abrevia "MIN.", o STJ escreve "MINISTRO", o TST espaça "A C Ó R D Ã O".
_ASSINATURAS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TST", _p(r"A\s+C\s+[ÓO]\s+R\s+D\s+[ÃA]\s+O|\bSbDI\b|\bTST-[A-Z]")),
    ("STM", _p(r"Poder\s+Judici[áa]rio\s+STM|SUPERIOR\s+TRIBUNAL\s+MILITAR", i=True)),
    ("TSE", _p(r"TRI[EB]UNAL\s+SUPERIOR\s+ELEITORAL", i=True)),
    ("STJ", _p(r"RELATOR[A]?\s*:\s*MINISTR|\(\d{4}/\d{6,8}-\d\)")),
    ("STF", _p(r"RELATOR[A]?\s*:\s*MIN\.|SUPREMO\s+TRIBUNAL\s+FEDERAL", i=True)),
)

# A assinatura tem de estar no cabeçalho; mais adiante o documento cita outros tribunais.
_JANELA_ASSINATURA = 1500

# Teto do cabeçalho: sem ele, documento sem marcador cedo teria "cabeçalho" enorme,
# cheio de números citados. Folga ampla sobre a posição do número próprio, porque
# truncar um cabeçalho de formato não visto custa mais que ambiguidade.
LIMITE_CABECALHO = 300


def tribunal_do_texto(texto: str) -> str | None:
    """Infere o tribunal pela forma do cabeçalho, ou ``None``.

    Best-effort: no caminho normal o tribunal vem da coluna do banco.
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

    Sem ``tribunal``, ele é inferido do texto; se não der, usa a ordem genérica.
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
        """Trecho antes de uma fronteira: cabeçalho (limitado) na primeira vez, corpo depois."""
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
