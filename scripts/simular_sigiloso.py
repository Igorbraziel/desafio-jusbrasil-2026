"""Simula o conjunto sigiloso: os moldes do dev preenchidos com outras citações.

O arnês (`perturbar.py`) degrada as **mesmas** 192 citações do dev. O conjunto
sigiloso vem do mesmo gerador, mas cita outras coisas: outros acórdãos dos 996
da base, outros números inventados, outros relatores nas vagas, outros artigos.
Nenhum instrumento media isso — o dev satura em 1,0 e o arnês só troca o ruído.

Este script troca o **conteúdo** e mantém o contexto. Cada documento do dev vira
um molde: cada citação do gabarito é substituída por outra da mesma família e da
mesma classe, sorteada de um catálogo montado da base canônica, e escrita numa
das grafias que o gabarito mostra (sigla, extenso, abreviação com ponto, caixa
alta; nº, n., No, N°; número com ponto, sem ponto, com espaço, CNJ corrido; UF
com barra, hífen, travessão ou parênteses; quebra de linha dentro). O texto em
volta é o do dev, então os conectores, o cabeçalho e o ruído de prosa são reais.

O gabarito da simulação é conhecido por construção, e a pontuação é a da
métrica oficial. Com ``--ruido`` os documentos do nível 2 passam também pelo
arnês, todas as classes juntas.

**O limite do instrumento:** só gera as formas que o catálogo conhece. Ele mede
generalização de conteúdo, não de forma; formas nunca vistas continuam sendo
trabalho das sondas de `tests/test_generalizacao.py`. E o gabarito da simulação
segue a convenção de borda do dev — onde o dev não mostra a convenção (o
tribunal depois do tema, por exemplo), a escolha daqui é uma hipótese.

Acórdãos cujo número próprio pertence a mais de um registro ficam fora do
catálogo: ali o desempate entre cópias é uma moeda (ADR 0003), e misturá-los
esconderia os erros que dá para consertar.

Uso:
    python scripts/simular_sigiloso.py --sementes 20
    python scripts/simular_sigiloso.py --sementes 10 --ruido 0.15 --exemplos 5
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "src"))

from avaliar import avaliar  # noqa: E402
from medir_cobertura import UFS_POR_EXTENSO  # noqa: E402
from perturbar import CLASSES, gerar_corpus  # noqa: E402

from verificador.base.canonica import BaseCanonica  # noqa: E402
from verificador.cli import _carregar_base  # noqa: E402
from verificador.pipeline import processar_pasta  # noqa: E402

CAMPOS = ("nivel", "documento_id", "citacao_id", "inicio", "fim", "trecho", "tipo")
CAMPOS += ("classificacao", "id_canonico")

# --------------------------------------------------------------------------- classes

# marca -> (sigla, extenso, gênero/número do extenso: "m", "f" ou "mp")
NOMES: dict[str, tuple[str, str, str]] = {
    "agint": ("AgInt", "Agravo Interno", "m"),
    "agrg": ("AgRg", "Agravo Regimental", "m"),
    "edcl": ("EDcl", "Embargos de Declaração", "mp"),
    "edv": ("EDv", "Embargos de Divergência", "mp"),
    "pext": ("PExt", "Pedido de Extensão", "m"),
    "einf": ("EInf", "Embargos Infringentes", "mp"),
    "qo": ("QO", "Questão de Ordem", "f"),
    "resp": ("REsp", "Recurso Especial", "m"),
    "aresp": ("AREsp", "Agravo em Recurso Especial", "m"),
    "rhc": ("RHC", "Recurso em Habeas Corpus", "m"),
    "rms": ("RMS", "Recurso em Mandado de Segurança", "m"),
    "respe": ("REspe", "Recurso Especial Eleitoral", "m"),
    "are": ("ARE", "Recurso Extraordinário com Agravo", "m"),
    "re": ("RE", "Recurso Extraordinário", "m"),
    "ro": ("RO", "Recurso Ordinário", "m"),
    "rse": ("RSE", "Recurso em Sentido Estrito", "m"),
    "rr": ("RR", "Recurso de Revista", "m"),
    "hc": ("HC", "Habeas Corpus", "m"),
    "ms": ("MS", "Mandado de Segurança", "m"),
    "rcl": ("Rcl", "Reclamação", "f"),
    "apl": ("APL", "Apelação", "f"),
    "ar": ("AR", "Ação Rescisória", "f"),
}
INCIDENTES = ("edcl", "agint", "agrg", "edv", "pext", "einf", "qo")
ORIGEM_PADRAO = {"STJ": "resp", "STF": "rcl", "TSE": "respe", "STM": "apl", "TST": "rr"}
# Sigla própria do TSE e do STF para o agravo regimental.
SIGLA_DO_TRIBUNAL = {("TSE", "agrg"): "AgR", ("STF", "agrg"): "AgR", ("TSE", "edcl"): "ED"}
# Abreviações com ponto e variantes que o nível 2 do gabarito mostra.
ABREVIADAS = {
    "resp": ("Rec. Esp.", "R.Esp.", "RESP"),
    "aresp": ("A.REsp", "AgREsp", "ARESP"),
    "hc": ("H.C.", "HC"),
    "agint": ("Ag. Int.", "AGINT"),
    "rcl": ("Recl.", "RCL"),
    "respe": ("RESPE", "REspe."),
}
CONECTOR = {"m": "no", "f": "na", "mp": "nos"}

TRIBUNAL_POR_EXTENSO = {
    "STF": "Supremo Tribunal Federal",
    "STJ": "Superior Tribunal de Justiça",
    "TST": "Tribunal Superior do Trabalho",
    "TSE": "Tribunal Superior Eleitoral",
    "STM": "Superior Tribunal Militar",
}


@dataclass(frozen=True)
class Acordao:
    documento_id: str
    id_canonico: int
    tribunal: str
    marcas: tuple[str, ...]
    digitos: str
    uf: str | None
    classe_tst: str | None  # a cadeia "E-ED-RR" do número do TST, lida do cabeçalho
    relator: str
    ano: int | None


# --------------------------------------------------------------------------- catálogo


def _uf_do_cabecalho(tribunal: str, texto: str, digitos: str) -> str | None:
    inicio = re.sub(r"\s+", " ", texto[:3000])
    if tribunal == "STF":
        for nome, sigla in UFS_POR_EXTENSO.items():
            if re.search(rf"\b{nome}\b", inicio[:600]):
                return sigla
        return None
    m = re.search(r"\d[\d.\-]*\d\s*/\s*([A-Z]{2})\b", inicio[:1500])
    return m.group(1) if m else None


def _relator(bruto: str | None) -> str:
    nome = re.sub(r"^(?:Min(?:istr[oa])?\.?|Des\.?)\s+", "", (bruto or "").strip())
    return re.sub(r"\s+", " ", nome)


def montar_catalogo(caminho_db: Path, base: BaseCanonica) -> list[Acordao]:
    """Os acórdãos que o gerador poderia citar, com o número próprio de cada um."""
    donos: dict[str, list[str]] = defaultdict(list)
    for numero, documentos in base._numeros.items():
        for documento in documentos:
            donos[documento].append(numero)

    conexao = sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)
    linhas = conexao.execute(
        "SELECT documento_id, id, tribunal, relator, ano, texto FROM documentos "
        "WHERE natureza = 'acordao' ORDER BY documento_id"
    ).fetchall()
    conexao.close()

    catalogo = []
    for documento_id, id_canonico, tribunal, relator, ano, texto in linhas:
        # Só números com um dono: ver a docstring.
        proprios = [n for n in donos.get(documento_id, []) if len(base._numeros[n]) == 1]
        if tribunal in ("STF", "STJ"):
            proprios = [n for n in proprios if 4 <= len(n) <= 7]
        else:
            proprios = [n for n in proprios if len(n) >= 13]
        if not proprios or not _relator(relator):
            continue
        digitos = max(proprios, key=len)
        classe_tst = None
        if tribunal == "TST":
            m = re.search(r"TST\s*-\s*((?:[A-Za-z]+\s*-\s*)+)\d", re.sub(r"\s+", " ", texto[:8000]))
            if not m:
                continue
            classe_tst = re.sub(r"\s", "", m.group(1)).strip("-")
        registro = base._registros[documento_id]
        catalogo.append(
            Acordao(
                documento_id=documento_id,
                id_canonico=id_canonico,
                tribunal=tribunal,
                marcas=tuple(sorted(registro.classe)),
                digitos=digitos,
                uf=_uf_do_cabecalho(tribunal, texto, digitos),
                classe_tst=classe_tst,
                relator=_relator(relator),
                ano=ano,
            )
        )
    return catalogo


# --------------------------------------------------------------------------- grafias


def _cadeia(marcas: tuple[str, ...], tribunal: str, estilo: str, rng: random.Random) -> str:
    incidentes = [m for m in INCIDENTES if m in marcas]
    origem = [m for m in NOMES if m in marcas and m not in INCIDENTES]
    partes = incidentes + [origem[0] if origem else ORIGEM_PADRAO[tribunal]]
    if estilo == "extenso":
        texto = NOMES[partes[0]][1]
        for parte in partes[1:]:
            texto += f" {CONECTOR[NOMES[parte][2]]} {NOMES[parte][1]}"
        return texto
    siglas = []
    for parte in partes:
        sigla = SIGLA_DO_TRIBUNAL.get((tribunal, parte), NOMES[parte][0])
        if estilo == "abreviada" and parte in ABREVIADAS:
            sigla = rng.choice(ABREVIADAS[parte])
        elif estilo == "caixa":
            sigla = sigla.upper()
        siglas.append(sigla)
    if tribunal == "TSE" and len(siglas) > 1 and rng.random() < 0.5:
        return "-".join(siglas)  # AgR-REspe
    texto = siglas[0]
    for parte, sigla in zip(partes[1:], siglas[1:], strict=True):
        texto += f" {CONECTOR[NOMES[parte][2]]} {sigla}"
    return texto


def _numero(digitos: str, estilo: str, rng: random.Random) -> str:
    if len(digitos) >= 13:
        n, dd, aaaa = digitos[:-13], digitos[-13:-11], digitos[-11:-7]
        j, tr, oooo = digitos[-7], digitos[-6:-4], digitos[-4:]
        return {
            "canonico": f"{n}-{dd}.{aaaa}.{j}.{tr}.{oooo}",
            "corrido": f"{n}-{dd}{aaaa}{j}{tr}{oooo}",
            "digitos": digitos,
            "espacos": f"{n}-{dd} {aaaa} {j} {tr} {oooo}",
        }.get(estilo, f"{n}-{dd}.{aaaa}.{j}.{tr}.{oooo}")
    pontuado = f"{int(digitos):,}".replace(",", ".")
    return {
        "canonico": pontuado,
        "corrido": digitos,
        "digitos": digitos,
        "espacos": pontuado.replace(".", " "),
        "ponto_espaco": pontuado.replace(".", ". ", 1),
    }.get(estilo, pontuado)


MARCAS_N1 = ("nº", "nº", "n.", "")
MARCAS_N2 = ("nº", "n°", "No", "N°", "Nº", "n.", "", "nº ", "n° ")
UF_N1 = ("/{u}",)
UF_N2 = ("/{u}", "/ {u}", " - {u}", " – {u}", "-{u}", " ({u})")


def _quebrar(citacao: str, rng: random.Random, probabilidade: float) -> str:
    """Troca um espaço interno por quebra de linha, como o texto quebrado do dev."""
    espacos = [i for i, c in enumerate(citacao) if c == " "]
    if espacos and rng.random() < probabilidade:
        i = rng.choice(espacos)
        return citacao[:i] + "\n" + citacao[i + 1 :]
    return citacao


def citar_acordao(
    a: Acordao, nivel: int, rng: random.Random, digitos: str | None = None
) -> tuple[str, str]:
    """A citação e o nome do estilo."""
    digitos = digitos or a.digitos
    estilos_classe = (
        ("sigla", "extenso") if nivel == 1 else ("sigla", "extenso", "abreviada", "caixa")
    )
    estilos_numero = (
        ("canonico", "corrido")
        if nivel == 1
        else ("canonico", "corrido", "espacos", "ponto_espaco", "digitos")
    )
    estilo_classe = rng.choice(estilos_classe)
    estilo_numero = rng.choice(estilos_numero)
    marca = rng.choice(MARCAS_N1 if nivel == 1 else MARCAS_N2)
    numero = _numero(digitos, estilo_numero, rng)

    if a.tribunal == "TST":
        forma = rng.choice(
            ("processo nº TST-{c}-{n}", "TST-{c}-{n}", "{c}-{n}", "Processo n° TST- {c}-{n}")
        )
        return forma.format(c=a.classe_tst, n=numero), f"TST/{estilo_numero}"

    classe = _cadeia(a.marcas, a.tribunal, estilo_classe, rng)
    citacao = f"{classe} {marca} {numero}" if marca else f"{classe} {numero}"
    citacao = citacao.replace("  ", " ")
    if a.uf and rng.random() < 0.8:
        citacao += rng.choice(UF_N1 if nivel == 1 else UF_N2).format(u=a.uf)
    return citacao, f"{a.tribunal}/{estilo_classe}/{estilo_numero}"


def inventar_numero(a: Acordao, chaves: set[str], rng: random.Random) -> str:
    """Um número com a forma do de `a` que não é chave do índice."""
    while True:
        if len(a.digitos) >= 13:
            novo = a.digitos[:-13]
            novo = "".join(rng.choice("0123456789") for _ in novo) + a.digitos[-13:]
            novo = str(rng.randint(1, 9)) + novo[1:]
        else:
            novo = str(rng.randint(10 ** (len(a.digitos) - 1), 10 ** len(a.digitos) - 1))
        if novo not in chaves:
            return novo


# A cobertura de súmulas e dispositivos vem da base carregada em `main` — é lida
# do banco, como na execução. (tribunal, vinculante, número) -> id e
# (código, artigo) -> id; só artigos sem sufixo entram no sorteio.
SUMULAS: dict[tuple[str, bool, int], int] = {}
DISPOSITIVOS: dict[tuple[str, int], int] = {}


def citar_sumula(
    tribunal: str, numero: int, vinculante: bool, nivel: int, rng: random.Random
) -> str:
    if vinculante:
        return rng.choice(
            (
                f"Súmula Vinculante {numero}",
                f"Súmula Vinculante nº {numero}",
                f"SV {numero}",
                f"Súmula Vinculante {numero} do STF",
                f"Súmula Vinculante n. {numero}",
            )
        )
    formas = [
        f"Súmula {numero} do {tribunal}",
        f"Súmula nº {numero} do {tribunal}",
        f"Súmula {numero}/{tribunal}",
    ]
    if tribunal == "TST":
        formas += [f"Súmula {numero}, IV, do TST", f"Súmula nº {numero}, item V, do TST"]
    if nivel == 2:
        formas += [
            f"Súm. {numero} do {tribunal}",
            f"SÚMULA {numero} do {tribunal}",
            f"Súmula {numero} do {TRIBUNAL_POR_EXTENSO[tribunal]}",
            f"Súmula n. {numero} do {tribunal}",
        ]
    return rng.choice(formas)


# código -> (artigos reais na cobertura, nomes do diploma)
DIPLOMAS: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "CF": (
        (5, 7, 93),
        (
            "da Constituição Federal",
            "da CF",
            "da CF/88",
            "da Constituição da República",
            "da Constituição Federal de 1988",
            "da CF/1988",
        ),
    ),
    "CLT": (
        (477, 818, 896),
        ("da CLT", "da Consolidação das Leis do Trabalho", "do Decreto-Lei nº 5.452/1943"),
    ),
    "CPC": (
        (373,),
        ("do CPC", "do Código de Processo Civil", "da Lei nº 13.105/2015", "do CPC/2015"),
    ),
    "CPP": ((312,), ("do CPP", "do Código de Processo Penal", "do Decreto-Lei nº 3.689/1941")),
    "CPM": ((290,), ("do Código Penal Militar", "do CPM", "do Decreto-Lei nº 1.001/1969")),
    "ELEITORAL": ((276,), ("do Código Eleitoral", "da Lei nº 4.737/1965")),
    "CDC": ((14,), ("do Código de Defesa do Consumidor", "do CDC", "da Lei nº 8.078/1990")),
    "CC": ((186,), ("do Código Civil", "do CC", "da Lei nº 10.406/2002", "do CC/2002")),
    "LC64": ((1,), ("da Lei Complementar nº 64/1990", "da LC 64/90", "da LC nº 64/1990")),
}
# Diplomas fora da cobertura: qualquer artigo deles é `inventada`.
FORA_DA_COBERTURA = (
    "da Lei nº 9.504/1997",
    "da Lei nº 13.467/2017",
    "da Lei nº 8.112/1990",
    "da Lei nº 9.099/1995",
    "da Lei nº 8.429/1992",
    "da Lei nº 11.343/2006",
    "do Código Tributário Nacional",
    "do Código Penal",
    "da Lei nº 8.069/1990",
    "da Lei nº 7.347/1985",
)
QUALIFICADORES = (
    "",
    "",
    "",
    ", I,",
    ", II,",
    ", LV,",
    ", caput,",
    ", § 1º,",
    ", inciso II,",
    ", parágrafo único,",
)


def _artigo(numero: int, rng: random.Random) -> str:
    rotulo = rng.choice(("art.", "art.", "artigo", "art"))
    valor = (
        f"{numero}º"
        if numero < 10
        else (f"{numero:,}".replace(",", ".") if numero >= 1000 else str(numero))
    )
    return f"{rotulo} {valor}"


def citar_dispositivo(real: bool, nivel: int, rng: random.Random) -> tuple[str, str]:
    """A citação e o id canônico ("" quando inventada)."""
    if real:
        codigo, numero = rng.choice(sorted(k for k in DISPOSITIVOS if k[0] in DIPLOMAS))
    else:
        codigo = rng.choice(sorted(DIPLOMAS))
    nomes = DIPLOMAS[codigo][1]
    artigos = {n for c, n in DISPOSITIVOS if c == codigo}
    if real:
        diploma = rng.choice(nomes)
    elif rng.random() < 0.5:
        limite = 250 if codigo == "CF" else 1200
        numero = rng.choice([n for n in range(2, limite) if n not in artigos])
        diploma = rng.choice(nomes)
    else:
        numero, diploma = rng.randint(1, 400), rng.choice(FORA_DA_COBERTURA)
    qualificador = rng.choice(QUALIFICADORES)
    if codigo == "LC64" and real:
        qualificador = rng.choice(("", ", I,", ", I, 'g',", ", inciso I, alínea g,"))
    separador = f"{qualificador} " if qualificador else " "
    id_canonico = str(DISPOSITIVOS[(codigo, numero)]) if real else ""
    return f"{_artigo(numero, rng)}{separador}{diploma}", id_canonico


def citar_tema(rng: random.Random) -> str:
    numero = rng.randint(1, 1300)
    valor = f"{numero:,}".replace(",", ".") if rng.random() < 0.5 else str(numero)
    return rng.choice(
        (
            f"Tema {valor} da repercussão geral",
            f"Tema {valor} da Repercussão Geral",
            f"Tema nº {valor} da repercussão geral",
            f"Tema {valor} do STF",
            f"Tema Repetitivo {valor} do STJ",
        )
    )


def citar_vaga(a: Acordao, nivel: int, rng: random.Random) -> str:
    t, ano, relator = a.tribunal, a.ano, a.relator
    origem = [m for m in NOMES if m in a.marcas and m not in INCIDENTES]
    marca = origem[0] if origem else ORIGEM_PADRAO[t]
    formas = [
        f"julgado do {t} proferido em {ano} pela relatoria de {relator}",
        f"precedente do {t} de {ano}, da relatoria de {relator}",
        f"acórdão do {t} julgado em {ano} sob relatoria de {relator}",
        f"{NOMES[marca][1]} do {t}, de {ano}, Rel. Min. {relator}",
        f"{NOMES[marca][0]} de {ano}, Rel. Min. {relator}",
    ]
    return rng.choice(formas)


# --------------------------------------------------------------------------- moldes


def _familia(linha: dict[str, str]) -> str:
    trecho = linha["trecho"].lower()
    if linha["tipo"] == "lei":
        return "dispositivo"
    if linha["classificacao"] == "incompleta":
        return "vaga"
    if re.search(r"s[uú5]m|\bsv\b|enunciado", trecho):
        return "sumula"
    if re.search(r"\bt[e3]m[aã]", trecho):
        return "tema"
    return "processo"


def gerar(
    semente: int,
    catalogo: list[Acordao],
    chaves: set[str],
    pasta_dev: Path,
    goldenset: Path,
    destino: Path,
) -> list[dict[str, str]]:
    """Escreve `destino/txt/*.txt` e devolve as linhas do gabarito simulado."""
    rng = random.Random(semente)
    por_documento: dict[str, list[dict[str, str]]] = defaultdict(list)
    with goldenset.open(encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f):
            por_documento[linha["documento_id"]].append(linha)

    (destino / "txt").mkdir(parents=True, exist_ok=True)
    saida = []
    for documento, linhas in sorted(por_documento.items()):
        original = (pasta_dev / f"{documento}.txt").read_text(encoding="utf-8")
        novo_id = f"{documento}_s{semente}"
        partes, cursor = [], 0
        tamanho = 0
        for indice, linha in enumerate(sorted(linhas, key=lambda x: int(x["inicio"])), start=1):
            nivel, classe, familia = int(linha["nivel"]), linha["classificacao"], _familia(linha)
            inicio, fim = int(linha["inicio"]), int(linha["fim"])
            id_canonico, estilo = "", familia
            if familia == "processo":
                a = rng.choice(catalogo)
                if classe == "real":
                    citacao, estilo = citar_acordao(a, nivel, rng)
                    id_canonico = str(a.id_canonico)
                else:
                    citacao, estilo = citar_acordao(a, nivel, rng, inventar_numero(a, chaves, rng))
            elif familia == "sumula":
                if classe == "real":
                    t, v, n = rng.choice(sorted(SUMULAS))
                else:
                    t = rng.choice(("STF", "STJ", "STJ", "TST", "TSE", "STM"))
                    v = t == "STF" and rng.random() < 0.3
                    n = rng.choice([x for x in range(1, 999) if (t, v, x) not in SUMULAS])
                citacao = citar_sumula(t, n, v, nivel, rng)
                id_canonico = str(SUMULAS[(t, v, n)]) if classe == "real" else ""
                estilo = f"sumula/{t}"
            elif familia == "dispositivo":
                citacao, id_canonico = citar_dispositivo(classe == "real", nivel, rng)
            elif familia == "tema":
                citacao = citar_tema(rng)
            else:
                a = rng.choice(catalogo)
                citacao = citar_vaga(a, nivel, rng)
                estilo = f"vaga/{a.tribunal}"
            citacao = _quebrar(citacao, rng, 0.12)

            partes.append(original[cursor:inicio])
            tamanho += inicio - cursor
            novo_inicio = tamanho
            partes.append(citacao)
            tamanho += len(citacao)
            cursor = fim
            saida.append(
                {
                    "nivel": str(nivel),
                    "documento_id": novo_id,
                    "citacao_id": f"c{indice}",
                    "inicio": str(novo_inicio),
                    "fim": str(novo_inicio + len(citacao)),
                    "trecho": citacao.replace("\n", "\\n"),
                    "tipo": linha["tipo"],
                    "classificacao": classe,
                    "id_canonico": id_canonico,
                    "_familia": familia,
                    "_estilo": estilo,
                }
            )
        partes.append(original[cursor:])
        (destino / "txt" / f"{novo_id}.txt").write_text("".join(partes), encoding="utf-8")
    return saida


# --------------------------------------------------------------------------- diagnóstico


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    return inter / ((a[1] - a[0]) + (b[1] - b[0]) - inter) if inter else 0.0


def diagnosticar(linhas: list[dict[str, str]], pasta_saida: Path) -> tuple[Counter, dict]:
    """Desfecho de cada citação simulada, pelo casamento da métrica (IoU ≥ 0,5)."""
    por_documento: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in linhas:
        por_documento[linha["documento_id"]].append(linha)

    contagem: Counter = Counter()
    exemplos: dict = defaultdict(list)
    for documento, esperadas in por_documento.items():
        preditas = json.loads((pasta_saida / f"{documento}.json").read_text(encoding="utf-8"))[
            "citacoes"
        ]
        usadas: set[int] = set()
        for e in esperadas:
            span = (int(e["inicio"]), int(e["fim"]))
            candidatos = [
                (_iou(span, (p["inicio"], p["fim"])), i)
                for i, p in enumerate(preditas)
                if i not in usadas
            ]
            iou, i = max(candidatos, default=(0.0, -1))
            chave = (e["nivel"], e["_familia"], e["classificacao"])
            if iou < 0.5:
                desfecho = "não detectada"
            else:
                usadas.add(i)
                p = preditas[i]
                if p["classificacao"] != e["classificacao"]:
                    desfecho = f"→ {p['classificacao']}"
                elif (
                    e["classificacao"] == "real"
                    and str((p["resolucao"] or {}).get("id_canonico")) != e["id_canonico"]
                ):
                    desfecho = "link errado"
                else:
                    desfecho = "certa" if iou >= 0.8 else "certa, IoU < 0,8"
            contagem[(*chave, desfecho)] += 1
            if desfecho != "certa":
                trecho = preditas[i]["trecho"] if iou >= 0.5 else None
                exemplos[(*chave, desfecho)].append(
                    (e["_estilo"], e["trecho"], trecho, round(iou, 2))
                )
        for i, p in enumerate(preditas):
            if i not in usadas:
                dentro = any(
                    _iou((p["inicio"], p["fim"]), (int(e["inicio"]), int(e["fim"]))) > 0
                    for e in esperadas
                )
                chave = (
                    "*",
                    p["tipo"],
                    p["classificacao"],
                    "espúria" + (" (sobreposta)" if dentro else ""),
                )
                contagem[chave] += 1
                exemplos[chave].append(("", "", p["trecho"], 0.0))
    return contagem, exemplos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sementes", type=int, default=10)
    p.add_argument(
        "--ruido", type=float, default=0.0, help="taxa do arnês no nível 2 (todas as classes)"
    )
    p.add_argument("--db", type=Path, default=RAIZ / "data/dev/desafio1_bracis.db")
    p.add_argument("--indice", type=Path, default=RAIZ / "data/dev/indice_cabecalhos.json")
    p.add_argument("--trabalho", type=Path, default=RAIZ / "data/tmp/simulacao")
    p.add_argument("--exemplos", type=int, default=3)
    p.add_argument("--json", type=Path, default=None)
    args = p.parse_args(argv)

    base = _carregar_base(args.indice, args.db)
    SUMULAS.update(base.sumulas)
    DISPOSITIVOS.update({(c, int(a)): i for (c, a), i in base.dispositivos.items() if a.isdigit()})
    catalogo = montar_catalogo(args.db, base)
    chaves = set(base._numeros)
    if args.trabalho.exists():
        shutil.rmtree(args.trabalho)

    linhas: list[dict[str, str]] = []
    for semente in range(1, args.sementes + 1):
        linhas += gerar(
            semente,
            catalogo,
            chaves,
            RAIZ / "data/dev/txt",
            RAIZ / "data/dev/goldenset.csv",
            args.trabalho / "limpo",
        )

    corpus = args.trabalho / "limpo"
    with (corpus / "goldenset.csv").open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(CAMPOS), extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas)

    if args.ruido > 0:
        # Só o nível 2 recebe o arnês; o nível 1 segue limpo, como no dev.
        n2 = args.trabalho / "n2"
        (n2 / "txt").mkdir(parents=True)
        linhas_n2 = [x for x in linhas if x["nivel"] == "2"]
        for documento in {x["documento_id"] for x in linhas_n2}:
            shutil.copy(corpus / "txt" / f"{documento}.txt", n2 / "txt")
        with (n2 / "goldenset.csv").open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(CAMPOS), extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(linhas_n2)
        ruidoso = args.trabalho / "ruidoso"
        gerar_corpus(n2 / "txt", n2 / "goldenset.csv", ruidoso, list(CLASSES), args.ruido, 1)
        traduzidas = {
            (r["documento_id"], r["citacao_id"]): r
            for r in csv.DictReader((ruidoso / "goldenset.csv").open(encoding="utf-8"))
        }
        for linha in linhas_n2:
            r = traduzidas[(linha["documento_id"], linha["citacao_id"])]
            linha["inicio"], linha["fim"], linha["trecho"] = r["inicio"], r["fim"], r["trecho"]
        for documento in {x["documento_id"] for x in linhas if x["nivel"] == "1"}:
            shutil.copy(corpus / "txt" / f"{documento}.txt", ruidoso / "txt")
        corpus = ruidoso
        with (corpus / "goldenset.csv").open("w", encoding="utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=list(CAMPOS), extrasaction="ignore")
            escritor.writeheader()
            escritor.writerows(linhas)

    saida = args.trabalho / "saida"
    processar_pasta(corpus / "txt", saida, base)
    resultado = avaliar(saida, corpus / "goldenset.csv")
    contagem, exemplos = diagnosticar(linhas, saida)

    print(f"\n{len(linhas)} citações simuladas em {args.sementes} sementes, ruído {args.ruido}")
    for nivel, dados in sorted(resultado["niveis"].items()):
        f1 = " ".join(f"{c}={v:.4f}" for c, v in dados["f1_por_classe"].items())
        print(
            f"  nível {nivel}: F1 macro {dados['macro_f1']:.4f} ({f1})"
            f"  τ {dados['tau']:.4f}  score {dados['score']:.4f}"
        )
    print(f"  SCORE FINAL {resultado['score_final']:.4f}\n")

    totais: Counter = Counter()
    for (nivel, familia, classe, _), n in contagem.items():
        totais[(nivel, familia, classe)] += n
    for chave in sorted(totais):
        desfechos = {d: n for (a, b, c, d), n in contagem.items() if (a, b, c) == chave}
        certas = desfechos.get("certa", 0)
        resto = ", ".join(
            f"{d} {n}" for d, n in sorted(desfechos.items(), key=lambda kv: -kv[1]) if d != "certa"
        )
        print(f"  N{chave[0]} {chave[1]:<12}{chave[2]:<11}{certas:>5}/{totais[chave]:<5} {resto}")

    if args.exemplos:
        print()
        for chave, lista in sorted(exemplos.items(), key=lambda kv: -len(kv[1])):
            print(f"── {' · '.join(chave)} ({len(lista)})")
            for estilo, esperado, predito, iou in lista[: args.exemplos]:
                print(f"     {estilo:<24} {esperado!r} -> {predito!r} ({iou})")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "score_final": resultado["score_final"],
                    "niveis": {
                        n: {k: d[k] for k in ("macro_f1", "tau", "score")}
                        for n, d in resultado["niveis"].items()
                    },
                    "desfechos": {" · ".join(k): n for k, n in contagem.items()},
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
