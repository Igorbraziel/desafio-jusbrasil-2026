"""Cita cada acórdão da base pelo próprio cabeçalho e mede se ele volta resolvido.

O gabarito só alcança os 77 acórdãos que o dev cita, e `medir_regiao.py` mede o
índice do lado dele. Este script mede do lado de quem cita, sobre a base
inteira: monta, para cada acórdão, a citação que o gerador escreveria — classe,
número próprio e UF, lidos do cabeçalho — e passa pelo pipeline.

O resultado é contado em quatro saídas: `real` com o registro certo, `real` com
outro registro (link errado), `inventada` (o número próprio não está no índice)
e nenhum span. Acórdãos com texto idêntico a outro (duplicatas exatas) são
contados à parte: a organização diz que nenhuma citação aponta para eles, e o
desempate entre cópias é arbitrário por construção.

O cabeçalho é lido por expressões simples, uma por tribunal; os poucos acórdãos
em que elas não acham a citação aparecem como "sem citação montada".

Uso:
    python scripts/medir_cobertura.py
    python scripts/medir_cobertura.py --detalhar   # lista os que não voltam certos
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from verificador.base_canonica import BaseCanonica  # noqa: E402
from verificador.cli import _carregar_base  # noqa: E402
from verificador.pipeline import processar_texto  # noqa: E402

UFS_POR_EXTENSO = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPÁ": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARÁ": "CE", "DISTRITO FEDERAL": "DF", "ESPÍRITO SANTO": "ES", "GOIÁS": "GO",
    "MARANHÃO": "MA", "MATO GROSSO DO SUL": "MS", "MATO GROSSO": "MT", "MINAS GERAIS": "MG",
    "PARÁ": "PA", "PARAÍBA": "PB", "PARANÁ": "PR", "PERNAMBUCO": "PE", "PIAUÍ": "PI",
    "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS",
    "RONDÔNIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC", "SÃO PAULO": "SP",
    "SERGIPE": "SE", "TOCANTINS": "TO",
}  # fmt: skip

CABECALHO = "PODER JUDICIÁRIO\nProcesso nº 1234567-89.2020.5.14.1391\n\nPARECER\n\n"

_STF = re.compile(
    r"(?:TURMA|PLEN[ÁA]RIO)\s+(.{2,200}?)\s(\d{1,3}(?:\.\d{3})+|\d{2,7})\s+"
    r"([A-ZÁÂÃÉÊÍÓÔÕÚÇ ]{4,25}?)\s+RELATOR"
)
_TST = re.compile(
    r"est[eo]s\s+autos\s+de\s+.{3,220}?\s+n?[º°o.]?\s*"
    r"(TST\s*-\s*[A-Za-z]+(?:\s*-\s*[A-Za-z]+)*\s*-\s*\d[\d.\-]*\d)",
    re.IGNORECASE,
)
_NUMERO_COM_MARCA = re.compile(
    r"N\s?[º°o.]?\s*(\d[\d.\-]*\d(?:\s?-\s?\d[\d.\-]*\d)?(?:\. ?\d[\d.\-]*\d)?)"
    r"(?:\s*/\s*([A-Z]{2}))?"
)
_CLASSE_PADRAO = {"STJ": "o REsp", "TSE": "o REspe", "STM": "a APL"}


def citacao_do_cabecalho(tribunal: str, texto: str) -> str | None:
    """A citação que o gerador escreveria para este acórdão, ou None."""
    inicio = re.sub(r"\s+", " ", texto[:8000])
    if tribunal == "STF":
        m = _STF.search(inicio[:600])
        if not m:
            return None
        uf = next(
            (s for nome, s in UFS_POR_EXTENSO.items() if m.group(3).strip().startswith(nome)), None
        )
        return f"a Rcl nº {m.group(2)}" + (f"/{uf}" if uf else "")
    if tribunal == "TST":
        m = _TST.search(inicio)
        return f"o processo nº {re.sub(r'\s+', '', m.group(1))}" if m else None
    m = _NUMERO_COM_MARCA.search(inicio[:700])
    if not m:
        return None
    uf = f"/{m.group(2)}" if m.group(2) else ""
    return f"{_CLASSE_PADRAO[tribunal]} nº {m.group(1)}{uf}"


def medir(caminho_db: Path, base: BaseCanonica) -> tuple[Counter, dict]:
    conexao = sqlite3.connect(f"file:{caminho_db}?mode=ro", uri=True)
    registros = conexao.execute(
        "SELECT documento_id, id, tribunal, texto FROM documentos "
        "WHERE natureza = 'acordao' ORDER BY documento_id"
    ).fetchall()
    conexao.close()

    assinatura = lambda texto: re.sub(r"\s+", " ", texto[:3000])  # noqa: E731
    copias = Counter(assinatura(texto) for *_, texto in registros)

    contagem: Counter = Counter()
    falhas: dict = defaultdict(list)
    for documento_id, id_canonico, tribunal, texto in registros:
        grupo = "duplicata" if copias[assinatura(texto)] > 1 else "unico"
        citacao = citacao_do_cabecalho(tribunal, texto)
        if citacao is None:
            desfecho = "sem citação montada"
        else:
            documento = CABECALHO + f"Invoca-se {citacao}, no ponto. Ainda assim.\n"
            achados = processar_texto("x", documento, base).citacoes
            if len(achados) != 1:
                desfecho = f"{len(achados)} spans"
            elif achados[0].classificacao != "real":
                desfecho = achados[0].classificacao
            elif achados[0].id_canonico == id_canonico:
                desfecho = "real, registro certo"
            else:
                desfecho = "real, link errado"
        contagem[(grupo, desfecho)] += 1
        if desfecho != "real, registro certo":
            falhas[(grupo, tribunal, desfecho)].append((documento_id, citacao))
    return contagem, falhas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", type=Path, default=RAIZ / "data/dev/desafio1_bracis.db")
    p.add_argument("--indice", type=Path, default=RAIZ / "data/dev/indice_cabecalhos.json")
    p.add_argument("--detalhar", action="store_true", help="lista os que não voltam certos")
    args = p.parse_args(argv)

    # O mesmo carregamento do CLI: banco primeiro, JSON só de reserva.
    contagem, falhas = medir(args.db, _carregar_base(args.indice, args.db))
    for grupo in ("unico", "duplicata"):
        total = sum(n for (g, _), n in contagem.items() if g == grupo)
        print(f"\n── acórdãos {'únicos' if grupo == 'unico' else 'com cópia exata'} ({total})")
        for (g, desfecho), n in sorted(contagem.items(), key=lambda kv: -kv[1]):
            if g == grupo:
                print(f"   {desfecho:<22}{n:5d}")
    if args.detalhar:
        for (grupo, tribunal, desfecho), casos in sorted(falhas.items()):
            if grupo != "unico":
                continue
            print(f"\n{tribunal} · {desfecho}")
            for documento_id, citacao in casos:
                print(f"   {documento_id}  {citacao}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
