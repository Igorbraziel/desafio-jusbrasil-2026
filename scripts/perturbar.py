"""Gera variantes ruidosas dos documentos, com o gabarito traduzido junto.

O pipeline mede 1,0988 no conjunto de desenvolvimento — e cada regra de
``deteccao.py`` nasceu de um caso concreto **desta** amostra: o filtro de
referência de página, o de inscrição na OAB, o ``d[eoc]`` que cobre o conector
"de" corrompido para "dc". Isso dá 100% aqui e não diz nada sobre o conjunto cego.

Este módulo ataca a lacuna do único jeito disponível sem ter o conjunto cego:
aplicando o ruído **documentado** com intensidade maior que a da amostra e
medindo a queda. Cada classe é isolável, porque atribuir a degradação é o ponto
— um agregado que cai de 1,09 para 0,90 não diz o que consertar.

**O mapa de offsets é o núcleo.** Perturbação que insere ou remove caractere
desloca todos os spans seguintes; sem reescrever o gabarito junto, a medição
viraria ruído e puniria o detector por acertar. ``mapa[i]`` é o offset novo do
caractere original ``i``, definido também em ``len(original)`` para traduzir o
fim exclusivo de um span.

**Duas invariantes que o gerador não pode violar:**

1. **Dígito nunca vira outro dígito.** A organização garante isso nos dados do
   desafio. Quebrar a garantia transformaria uma citação ``real`` ruidosa numa
   ``inventada`` de fato, e mediríamos um problema que a tarefa não tem.
2. **Ruído de prosa é letra→letra.** Nunca cria sequência numérica nova, senão
   o gerador inventa citações que o gabarito não anota.

Uso:
    python scripts/perturbar.py --classe ocr_numero --taxa 0.3 --semente 1
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import unicodedata
import zlib
from dataclasses import dataclass
from pathlib import Path

# Dígito -> letra confundível. Só nesta direção: o inverso trocaria a identidade
# da citação. Ver a invariante 1 no topo.
_OCR_DIGITO = {"0": "O", "1": "l", "5": "S", "9": "g", "6": "G", "8": "B", "2": "Z"}

# Letra -> letra, para a prosa. `m -> rn` muda o tamanho, e é justamente o caso
# que exercita o mapa de offsets.
_OCR_LETRA = {
    "m": "rn",
    "e": "c",
    "i": "l",
    "o": "0",  # nunca aplicado: filtrado abaixo por gerar dígito
    "c": "e",
    "u": "ii",
    "n": "ri",
}
_OCR_LETRA = {k: v for k, v in _OCR_LETRA.items() if not any(c.isdigit() for c in v)}

_SEPARADORES_UF = ("/{uf}", " - {uf}", " ({uf})", " – {uf}", "-{uf}", " / {uf}")
_MARCAS_NUMERO = ("nº", "n°", "No", "n.", "Nº", "N°", "n º")

# Siglas plausíveis e **fora** do vocabulário observado no gabarito. Medir com
# elas é medir o risco que docs/dados.md aponta: "as siglas processuais
# observadas não esgotam o domínio".
_SIGLAS_INVENTADAS = ("RExt", "AgAp", "REJ", "AIRR-Ext", "PetAvC", "MSCol", "RvCr")

_UF_FINAL = re.compile(r"\s*[/(\-–—]\s*([A-Z]{2})\s*\)?\s*$")
_MARCA_NUMERO = re.compile(r"[nN]\s*[.ºo°O]{1,2}")
_SIGLA_INICIAL = re.compile(r"^([A-Z][A-Za-z.\-]{1,12})(?=[\s ])")
_CORRIDA_DIGITOS = re.compile(r"\d[\d.\-/ ]*\d")
_PALAVRA = re.compile(r"[A-Za-zÀ-ÿ]{4,}")

CLASSES = (
    "ocr_numero",
    "ocr_palavra",
    "quebra_identificador",
    "separador_uf",
    "marca_numero",
    "sigla_nao_vista",
    "ordem_incompleta",
)


@dataclass(frozen=True)
class Perturbado:
    """Texto ruidoso mais o mapa que traduz offsets do original para ele."""

    texto: str
    mapa: tuple[int, ...]
    aplicadas: tuple[str, ...]

    def traduzir(self, inicio: int, fim: int) -> tuple[int, int]:
        """Converte um span do original para o texto perturbado."""
        return self.mapa[inicio], self.mapa[fim]


def _aplicar(original: str, trocas: list[tuple[int, int, str]], classes: list[str]) -> Perturbado:
    """Monta o texto novo e o mapa, a partir de trocas disjuntas e ordenadas."""
    trocas = sorted(trocas, key=lambda t: t[0])
    partes: list[str] = []
    mapa = [0] * (len(original) + 1)
    cursor_original = 0
    cursor_novo = 0

    for inicio, fim, substituto in trocas:
        if inicio < cursor_original:
            continue  # troca sobreposta: descarta em vez de corromper o mapa
        for i in range(cursor_original, inicio):
            mapa[i] = cursor_novo + (i - cursor_original)
        partes.append(original[cursor_original:inicio])
        cursor_novo += inicio - cursor_original
        # Todo caractere do trecho trocado aponta para o começo do substituto: o
        # interior de uma troca não tem correspondência 1-para-1, e só as bordas
        # precisam ser exatas.
        for i in range(inicio, fim):
            mapa[i] = cursor_novo
        partes.append(substituto)
        cursor_novo += len(substituto)
        cursor_original = fim

    for i in range(cursor_original, len(original) + 1):
        mapa[i] = cursor_novo + (i - cursor_original)
    partes.append(original[cursor_original:])

    return Perturbado("".join(partes), tuple(mapa), tuple(classes))


# --------------------------------------------------------------------------- ruídos


def _ocr_numero(texto: str, spans, rng: random.Random, taxa: float) -> list[tuple[int, int, str]]:
    """Dígito vira letra confundível, só dentro das citações."""
    trocas = []
    for inicio, fim, _ in spans:
        for i in range(inicio, fim):
            if texto[i] in _OCR_DIGITO and rng.random() < taxa:
                trocas.append((i, i + 1, _OCR_DIGITO[texto[i]]))
    return trocas


def _ocr_palavra(texto: str, spans, rng: random.Random, taxa: float) -> list[tuple[int, int, str]]:
    """Uma letra por palavra, na prosa inteira. Nunca gera dígito."""
    trocas = []
    for casamento in _PALAVRA.finditer(texto):
        if rng.random() >= taxa:
            continue
        palavra = casamento.group()
        candidatos = [i for i, c in enumerate(palavra) if c.lower() in _OCR_LETRA]
        if not candidatos:
            continue
        i = rng.choice(candidatos)
        posicao = casamento.start() + i
        trocas.append((posicao, posicao + 1, _OCR_LETRA[palavra[i].lower()]))
    return trocas


def _quebra_identificador(texto, spans, rng, taxa) -> list[tuple[int, int, str]]:
    """Insere quebra de linha no meio do número do processo."""
    trocas = []
    for inicio, fim, _ in spans:
        if rng.random() >= taxa:
            continue
        casamento = _CORRIDA_DIGITOS.search(texto, inicio, fim)
        if casamento is None or casamento.end() - casamento.start() < 4:
            continue
        corte = rng.randrange(casamento.start() + 2, casamento.end() - 1)
        trocas.append((corte, corte, "\n"))
    return trocas


def _separador_uf(texto, spans, rng, taxa) -> list[tuple[int, int, str]]:
    """Troca /PR por - PR, (PR), – PR."""
    trocas = []
    for inicio, fim, _ in spans:
        if rng.random() >= taxa:
            continue
        casamento = _UF_FINAL.search(texto[inicio:fim])
        if casamento is None:
            continue
        uf = casamento.group(1)
        novo = rng.choice(_SEPARADORES_UF).format(uf=uf)
        trocas.append((inicio + casamento.start(), inicio + casamento.end(), novo))
    return trocas


def _marca_numero(texto, spans, rng, taxa) -> list[tuple[int, int, str]]:
    """Alterna entre as grafias de "número"."""
    trocas = []
    for inicio, fim, _ in spans:
        if rng.random() >= taxa:
            continue
        casamento = _MARCA_NUMERO.search(texto, inicio, fim)
        if casamento is None:
            continue
        trocas.append((casamento.start(), casamento.end(), rng.choice(_MARCAS_NUMERO)))
    return trocas


def _sigla_nao_vista(texto, spans, rng, taxa) -> list[tuple[int, int, str]]:
    """Troca a classe processual por uma plausível e fora do vocabulário visto."""
    trocas = []
    for inicio, fim, classificacao in spans:
        if classificacao == "incompleta" or rng.random() >= taxa:
            continue
        casamento = _SIGLA_INICIAL.match(texto[inicio:fim])
        if casamento is None:
            continue
        trocas.append(
            (inicio + casamento.start(1), inicio + casamento.end(1), rng.choice(_SIGLAS_INVENTADAS))
        )
    return trocas


def _ordem_incompleta(texto, spans, rng, taxa) -> list[tuple[int, int, str]]:
    """Reescreve o padrão tribunal + ano + relator numa ordem diferente.

    Hoje as 32 `incompleta` do gabarito são todas da mesma forma, e casá-la é
    fácil demais. Esta classe mede o que acontece quando ela varia.
    """
    padrao = re.compile(
        r"(?P<cabeca>julgad[oa]|ac[óo]rd[ãa]o|precedente|decis[ãa]o)"
        r"\s+d[oa]\s+(?P<tribunal>STF|STJ|TSE|TST|STM)"
        r"[^.]{0,30}?(?P<ano>(?:19|20)\d{2})"
        r"[^.]{0,30}?relatoria\s+d[eoc]\s+(?P<relator>[A-ZÀ-Ú][^.]{2,60})"
    )
    modelos = (
        "{cabeca}, Rel. {relator}, {tribunal}, {ano}",
        "{tribunal}, {ano}, Rel. Min. {relator} ({cabeca})",
        "{cabeca} de {ano} do {tribunal}, relatado por {relator}",
    )
    trocas = []
    for inicio, fim, classificacao in spans:
        if classificacao != "incompleta" or rng.random() >= taxa:
            continue
        casamento = padrao.search(texto[inicio:fim])
        if casamento is None:
            continue
        trocas.append((inicio, fim, rng.choice(modelos).format(**casamento.groupdict()).strip()))
    return trocas


_GERADORES = {
    "ocr_numero": _ocr_numero,
    "ocr_palavra": _ocr_palavra,
    "quebra_identificador": _quebra_identificador,
    "separador_uf": _separador_uf,
    "marca_numero": _marca_numero,
    "sigla_nao_vista": _sigla_nao_vista,
    "ordem_incompleta": _ordem_incompleta,
}


def perturbar(
    texto: str,
    spans: list[tuple[int, int, str]],
    classes: list[str],
    taxa: float,
    semente: int,
) -> Perturbado:
    """Aplica as classes pedidas e devolve texto novo mais mapa de offsets."""
    rng = random.Random(semente)
    trocas: list[tuple[int, int, str]] = []
    for classe in classes:
        trocas.extend(_GERADORES[classe](texto, spans, rng, taxa))
    # Trocas de classes diferentes podem colidir; `_aplicar` descarta as
    # sobrepostas, mantendo a primeira em ordem de posição.
    return _aplicar(texto, trocas, classes)


# --------------------------------------------------------------------------- corpus


def _ler_goldenset(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def gerar_corpus(
    pasta_txt: Path,
    caminho_goldenset: Path,
    destino: Path,
    classes: list[str],
    taxa: float,
    semente: int,
) -> tuple[int, int]:
    """Escreve os .txt perturbados e o goldenset traduzido. Devolve (docs, citações)."""
    registros = _ler_goldenset(caminho_goldenset)
    por_documento: dict[str, list[dict[str, str]]] = {}
    for r in registros:
        por_documento.setdefault(r["documento_id"], []).append(r)

    (destino / "txt").mkdir(parents=True, exist_ok=True)
    saida: list[dict[str, str]] = []

    for documento, citacoes in sorted(por_documento.items()):
        original = unicodedata.normalize(
            "NFC", (pasta_txt / f"{documento}.txt").read_text(encoding="utf-8")
        )
        spans = [
            (int(c["inicio"]), int(c["fim"]), c["classificacao"])
            for c in sorted(citacoes, key=lambda c: int(c["inicio"]))
        ]
        # crc32 e não hash(): o hash de str é aleatorizado por processo quando
        # PYTHONHASHSEED não está fixo, e a semente precisa ser estável entre
        # execuções para a medição ser reproduzível.
        desvio = zlib.crc32(documento.encode("utf-8")) % 1000
        resultado = perturbar(original, spans, classes, taxa, semente + desvio)
        (destino / "txt" / f"{documento}.txt").write_text(resultado.texto, encoding="utf-8")

        for citacao in sorted(citacoes, key=lambda c: int(c["inicio"])):
            inicio, fim = resultado.traduzir(int(citacao["inicio"]), int(citacao["fim"]))
            novo = dict(citacao)
            novo["inicio"], novo["fim"] = str(inicio), str(fim)
            # O trecho é recomputado do texto novo: o gabarito guarda a quebra de
            # linha escapada, como na distribuição original.
            novo["trecho"] = resultado.texto[inicio:fim].replace("\n", "\\n")
            saida.append(novo)

    with (destino / "goldenset.csv").open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(registros[0].keys()))
        escritor.writeheader()
        escritor.writerows(saida)

    return len(por_documento), len(saida)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--txt", type=Path, default=Path("data/dev/txt"))
    p.add_argument("--goldenset", type=Path, default=Path("data/dev/goldenset.csv"))
    p.add_argument("--destino", type=Path, default=Path("data/perturbado/manual"))
    p.add_argument("--classe", action="append", choices=CLASSES, help="repetível; padrão: todas")
    p.add_argument("--taxa", type=float, default=0.3)
    p.add_argument("--semente", type=int, default=1)
    args = p.parse_args(argv)

    classes = args.classe or list(CLASSES)
    docs, citacoes = gerar_corpus(
        args.txt, args.goldenset, args.destino, classes, args.taxa, args.semente
    )
    print(f"{docs} documentos, {citacoes} citações -> {args.destino}")
    print(f"  classes: {', '.join(classes)}  taxa: {args.taxa}  semente: {args.semente}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
