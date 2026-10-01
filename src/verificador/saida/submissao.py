"""O submission.csv do Kaggle, escrito direto dos documentos processados.

Reproduz byte a byte o conversor oficial (``json_to_submission.py``) a partir dos
mesmos dicionários que viram JSON, e confere o CSV com as checagens da métrica
oficial, onde erro de formato rejeita a submissão inteira.
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
# O Kaggle rejeita célula vazia, por isso o hífen.
MISSING = "-"
# IoU a partir do qual duas citações do mesmo documento são duplicata.
MIN_IOU = 0.5


def encode_cell(document: dict) -> str:
    """A célula de um documento, com a mesma formatação do conversor oficial."""
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
    """Uma linha por documento, na ordem do conversor oficial.

    A ordem é a do nome do JSON, não a do id (``a-b.json`` < ``a.json``); id
    repetido fica com o último documento.
    """
    cells = {document["documento_id"]: encode_cell(document) for document in documents}
    return sorted(cells.items(), key=lambda row: f"{row[0]}.json")


def write_submission(documents: Iterable[dict], destination: Path) -> Path:
    """Grava o CSV de forma atômica: ou o arquivo inteiro, ou o anterior intacto."""
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
        # `mkstemp` cria com 0600, ilegível para quem chamou se o container rodar
        # como root; volume sem chmod não deve custar a saída.
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
    """Confere o CSV inteiro; ``expected`` são os documentos que precisam de linha."""
    # utf-8-sig tolera o BOM que uma planilha acrescenta ao salvar.
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
