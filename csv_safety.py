"""Formula protection of CSV text cells (Stage 37, issue #67).

A spreadsheet program that opens a CSV file treats a cell that begins with
``=``, ``+``, ``-`` or ``@`` as a formula, and a tab or a carriage return at
the start of a cell can hide one (OWASP, "CSV Injection"). The CSV export
therefore writes such a *text* cell with a leading apostrophe, as OWASP
recommends; the csv module quotes every cell that holds a separator, a quote
or a line break, so no text can start a new cell. Numbers are never changed:
``-5`` in a numeric column is written as ``-5``.

The rule is reversible, so the program's own importer gives back exactly the
text that was exported:

* :func:`protect` adds one apostrophe to a text that begins with one of the
  characters above, and also to a text that already begins with apostrophes
  followed by one of them (``'=x`` is written ``''=x``);
* :func:`restore` removes one apostrophe from a text that begins with
  apostrophes followed by one of the characters, and leaves every other
  text alone.

``restore(protect(text)) == text`` for every text. A text that begins with an
apostrophe followed by anything else (``'quoted'``) is written unchanged.

The importer (``data_loader``) applies :func:`restore` only when the file
written next to the CSV says that the program exported exactly this file
(its SHA-256): the codebook ``<name>_codebook.json`` (data and questionnaire
exports) or the transformation log ``<name>_steps.json`` (Data → Prepare).
In a CSV from anywhere else an apostrophe is the researcher's own text and
stays.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

TRIGGERS = ("=", "+", "-", "@", "\t", "\r")
RULE = "owasp-leading-apostrophe-v1"
CODEBOOK_FORMAT = "statistical-research-assistant-codebook"
CODEBOOK_SUFFIX = "_codebook.json"
PREPARATION_FORMAT = "statistical-research-assistant-prep-v1"
PREPARATION_SUFFIX = "_steps.json"
SIDECARS = ((CODEBOOK_SUFFIX, CODEBOOK_FORMAT), (PREPARATION_SUFFIX, PREPARATION_FORMAT))
MAX_CODEBOOK_BYTES = 50 * 1024 * 1024

_PROTECTED = re.compile(r"'+[=+\-@\t\r]")


def needs_protection(text: str) -> bool:
    return bool(text) and (text[0] in TRIGGERS or _PROTECTED.match(text) is not None)


def protect(text: str) -> str:
    """``text`` as a CSV cell that no spreadsheet evaluates."""
    return "'" + text if needs_protection(text) else text


def restore(text: str) -> str:
    """The text :func:`protect` was given."""
    return text[1:] if _PROTECTED.match(text) else text


def codebook_path(csv_path: Path) -> Path:
    """Where the CSV export writes its codebook: ``<stem>_codebook.json``."""
    csv_path = Path(csv_path)
    return csv_path.with_name(csv_path.stem + CODEBOOK_SUFFIX)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def exported_codebook(csv_path: Path, data: bytes | None = None) -> dict | None:
    """The codebook (or transformation log) of a CSV this program exported,
    when it vouches for exactly this file (SHA-256 and the protection rule);
    otherwise None."""
    csv_path = Path(csv_path)
    digest = None
    for suffix, expected in SIDECARS:
        sidecar = csv_path.with_name(csv_path.stem + suffix)
        try:
            if not sidecar.is_file() or sidecar.stat().st_size > MAX_CODEBOOK_BYTES:
                continue
            book = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(book, dict) or book.get("format") != expected:
            continue
        info = book.get("data_file")
        protection = info.get("formula_protection") if isinstance(info, dict) else None
        if not isinstance(protection, dict) or protection.get("rule") != RULE:
            continue
        if digest is None:
            digest = (hashlib.sha256(data).hexdigest() if data is not None
                      else sha256_file(csv_path))
        if info.get("sha256") == digest:
            return book
    return None


def protect_frame(frame):
    """A copy of ``frame`` whose text cells and column names are protected
    (numbers, dates and missing values untouched), and how many cells changed."""
    copy = frame.copy()
    changed = 0
    for position in range(copy.shape[1]):
        values = copy.iloc[:, position]
        if values.dtype.kind in "biufcmM":       # numbers, booleans and dates
            continue
        needs = values.map(lambda v: isinstance(v, str) and needs_protection(v)).astype(bool)
        count = int(needs.sum())
        if count:
            protected = values.astype(object).where(
                ~needs, values[needs].map(protect).reindex(values.index))
            copy.isetitem(position, protected)
            changed += count
    names = [protect(str(c)) for c in copy.columns]
    changed += sum(1 for name, column in zip(names, copy.columns) if name != str(column))
    copy.columns = names
    return copy, changed


def protected_cells(path: Path) -> int:
    """How many cells of a CSV carry the protection: exactly the cells that
    :func:`protect` changed, since only they begin with apostrophes followed
    by one of the characters."""
    import csv
    import io

    text = Path(path).read_text(encoding="utf-8-sig")
    return sum(1 for row in csv.reader(io.StringIO(text, newline=""))
               for cell in row if _PROTECTED.match(cell))


def data_file(path: Path, cells: int | None = None) -> dict:
    """What a codebook says about the CSV it describes (``data_file``)."""
    path = Path(path)
    cells = protected_cells(path) if cells is None else cells
    return {"name": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size,
            "format": "csv", "encoding": "utf-8",
            "formula_protection": {"rule": RULE, "cells": int(cells)}}


def sidecar_name(csv_path: Path, book: dict) -> str:
    """The file name of the codebook or log that vouched for ``csv_path``."""
    csv_path = Path(csv_path)
    suffix = next((s for s, f in SIDECARS if f == book.get("format")), CODEBOOK_SUFFIX)
    return csv_path.stem + suffix
