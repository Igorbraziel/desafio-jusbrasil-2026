"""O submission.csv do Kaggle, escrito direto dos documentos processados.

A avaliação final roda o nosso código sobre uma base e pareceres novos, sem
acesso nosso, e pede a saída "no mesmo formato das submissões". Esse formato é o
que o conversor da organização (``json_to_submission.py``) produz a partir dos
JSONs do contrato, e este módulo o reproduz **byte a byte**:

- ``csv.writer`` no dialeto padrão: fim de linha ``\\r\\n``, aspas só quando a
  célula tem vírgula;
- cabeçalho ``documento_id,citacoes`` e uma linha por documento, na ordem do
  nome do JSON;
- a célula junta as citações com ``|``, cada uma ``inicio,fim,classe,id,conf``,
  com ``-`` no id ou na confiança ausentes e ``-`` no documento sem citações.

A entrada são os mesmos dicionários que viram JSON
(``SaidaDocumento.para_dicionario``): com uma fonte só, CSV e JSON não têm como
divergir.

A conferência roda as checagens que o ``kaggle_metric.py`` faz antes de
pontuar. Nele, erro de formato não custa pontos: rejeita a submissão
**inteira**.
"""

from __future__ import annotations

import contextlib
import csv
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .contrato import CLASSIFICACOES

HEADER = ("documento_id", "citacoes")
# Célula e campo ausentes. O Kaggle rejeita célula vazia, por isso o hífen.
MISSING = "-"
# Duas citações do mesmo documento com IoU a partir daqui são duplicata, e o
# oficial rejeita a submissão (§8 do regulamento).
MIN_IOU = 0.5


def encode_cell(document: dict) -> str:
    """A célula de um documento, com a regra do conversor oficial campo a campo.

    O id passa por ``str(...).strip() or "-"`` e a confiança por
    ``f"{float(c):.4f}"``, como lá: qualquer diferença de arredondamento ou de
    espaço mudaria bytes do CSV e deixaria de ser "o mesmo formato".
    """
    parts: list[str] = []
    for citation in document.get("citacoes", []):
        resolution = citation.get("resolucao") or {}
        canonical_id = str(resolution.get("id_canonico", "") or "").strip() or MISSING
        confidence = citation.get("confianca")
        confidence_text = MISSING if confidence is None else f"{float(confidence):.4f}"
        parts.append(
            f"{int(citation['inicio'])},{int(citation['fim'])},"
            f"{citation['classificacao']},{canonical_id},{confidence_text}"
        )
    return "|".join(parts) if parts else MISSING


def submission_rows(documents: Iterable[dict]) -> list[tuple[str, str]]:
    """Uma linha por documento, na ordem em que o conversor oficial as escreve.

    O conversor lê ``sorted(pasta.glob("*.json"))``: a ordem é a do **nome do
    arquivo**, não a do id. As duas divergem quando um id é prefixo de outro —
    ``a-b.json`` vem antes de ``a.json`` (``-`` < ``.``), embora ``a`` venha
    antes de ``a-b``.

    Id repetido fica com o último documento, que é o que sobra na pasta de JSONs
    depois que a última escrita sobrescreve as anteriores.
    """
    cells = {document["documento_id"]: encode_cell(document) for document in documents}
    return sorted(cells.items(), key=lambda row: f"{row[0]}.json")


def write_submission(documents: Iterable[dict], destination: Path) -> Path:
    """Grava o CSV de forma atômica: ou o arquivo inteiro, ou o anterior intacto.

    Escreve num temporário do mesmo diretório e troca com ``os.replace``. Um
    processo interrompido no meio da escrita não deixa um CSV truncado que
    passaria por completo — documento sem linha rejeita a submissão inteira.
    """
    rows = submission_rows(documents)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(HEADER)
            writer.writerows(rows)
        # O `mkstemp` cria com 0600. No container rodado sem `--user` o CSV
        # nasce com dono root, e com 0600 quem chamou nem conseguiria lê-lo. Um
        # volume que não aceita chmod não é motivo para perder a saída.
        with contextlib.suppress(OSError):
            os.chmod(temporary, _creation_mode())
        os.replace(temporary, destination)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    return destination


def _creation_mode() -> int:
    """A permissão que um ``open()`` comum daria ao arquivo, pela umask atual."""
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    intersection = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    if not intersection:
        return 0.0
    return intersection / ((a[1] - a[0]) + (b[1] - b[0]) - intersection)


def check_cell(document_id: str, cell: str | None) -> list[str]:
    """Os problemas de uma célula; vazia quando o oficial a aceitaria."""
    problems: list[str] = []
    cell = (cell or "").strip()
    if cell in ("", MISSING):
        return problems
    spans: list[tuple[int, int]] = []
    for position, block in enumerate(cell.split("|"), start=1):
        fields = [field.strip() for field in block.split(",")]
        where = f"{document_id} citação {position}"
        if len(fields) != 5:
            problems.append(f"{where}: {len(fields)} campos, esperados 5")
            continue
        start, end, label, canonical_id, confidence = fields
        if not (start.isdigit() and end.isdigit()) or int(end) <= int(start):
            problems.append(f"{where}: span inválido ({start}, {end})")
            continue
        if label not in CLASSIFICACOES:
            problems.append(f"{where}: classe inválida {label!r}")
        if label == "real" and not canonical_id.isdigit():
            problems.append(f"{where}: real sem id_canonico numérico ({canonical_id!r})")
        if confidence not in ("", MISSING):
            try:
                value = float(confidence)
            except ValueError:
                problems.append(f"{where}: confiança não numérica {confidence!r}")
            else:
                if not 0.0 <= value <= 1.0:
                    problems.append(f"{where}: confiança fora de [0, 1] ({value})")
        spans.append((int(start), int(end)))
    for a in range(len(spans)):
        for b in range(a + 1, len(spans)):
            if _iou(spans[a], spans[b]) >= MIN_IOU:
                problems.append(f"{document_id}: citações {a + 1} e {b + 1} com IoU ≥ {MIN_IOU}")
    return problems


def check_submission(path: Path, expected: Iterable[str]) -> list[str]:
    """Confere o CSV inteiro. Devolve os problemas; vazia quando pode ser enviado.

    ``expected`` são os documentos que precisam de linha: no Kaggle, os do
    ``sample_submission.csv``; na entrega, os ``.txt`` processados.
    """
    # utf-8-sig: um CSV salvo de novo por planilha ganha BOM, e sem isso a
    # primeira coluna passaria a se chamar "﻿documento_id".
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing_columns = [column for column in HEADER if column not in (reader.fieldnames or [])]
        if missing_columns:
            return [f"cabeçalho sem a coluna {column}" for column in missing_columns]
        rows = list(reader)
    present = {row["documento_id"] for row in rows}
    problems = [f"documento sem linha: {document}" for document in sorted(set(expected) - present)]
    for row in rows:
        problems.extend(check_cell(row["documento_id"], row["citacoes"]))
    return problems
