"""Questionnaire forms in Word tables, read from the document structure.

A Word file keeps its paragraphs, headings and tables in document order, so
a DOCX questionnaire is read structure-first (paragraphs, tables, rows,
cells, headings) before any text heuristics:

* A table whose statement column holds statements and whose other columns
  print the same short answer codes or labels on most rows is a
  questionnaire FORM. Item numbers printed in the cells (or in a number
  column) are kept; without them the items are numbered by row order, the
  header row excluded.
* Each form is titled by the nearest heading before its table.
* Each form documents its OWN answer options: the labels of its header row
  ("Hardly ever | Now and then | ..."), the instruction just before the
  table ("1 = Not at all; 2 = Slightly; ...") or labels printed in every
  row's own cells. They become a
  :class:`scientific_survey_import.DocumentedScale` — evidence for a shared
  response scale that the researcher still has to confirm.

Binary answer cells (True/False), marker cells (○ □) and cells printing a
code with its label on two lines keep their established handling
(:mod:`binary_responses`, :mod:`matrix_reconstruction`,
:mod:`repeated_choices`). Pure data processing; no OCR, network or UI.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re

from binary_responses import match_header
from response_scales import code_label_pairs
from scientific_survey_import import DocumentedScale, is_title_line

MIN_FORM_ROWS = 3
MAX_ANSWER_COLUMNS = 11
# Share of statement rows that must print the same answer cells.
SIGNATURE_SHARE = 0.6
_NUMBER_CELL = re.compile(r"^\s*(\d{1,3})\s*[.)]?\s*\*?\s*$")
_INLINE_NUMBER = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(\S.*)$", re.S)
_MARKER_CHARS = set("○◯◦●□☐■▢◻◽⬜❍·•[]() ")
_COLUMN_TITLE_WORDS = {
    "statement", "statements", "item", "items", "question", "questions", "prompt",
    "no", "no.", "nr", "nr.", "#", "№", "apgalvojums", "apgalvojumi", "jautājums",
    "jautājumi", "utverždenie", "утверждение", "утверждения", "вопрос", "вопросы",
}


@dataclass(frozen=True)
class DocxBlock:
    """A paragraph or a table, in document order."""
    index: int
    kind: str                                   # "paragraph" | "table"
    text: str = ""                              # paragraph text
    style: str = ""                             # paragraph style name
    heading_level: int | None = None            # 0 = Title, 1 = Heading 1, ...
    rows: tuple[tuple[str, ...], ...] = ()      # table cell texts per row


@dataclass(frozen=True)
class FormRow:
    number: int
    printed: bool          # the number is printed in the source (cell or column)
    statement: str
    cell_text: str         # the statement cell exactly as printed (whitespace normalised)
    table_row: int         # 1-based row of the table
    answers: tuple[str, ...]


@dataclass(frozen=True)
class TableForm:
    id: str
    block_index: int
    table_number: int
    title: str
    instruction: str
    header: tuple[str, ...]
    rows: tuple[FormRow, ...]
    answer_columns: int
    scale: DocumentedScale | None
    numbered: bool
    issues: tuple[str, ...] = ()


def _clean(text: str) -> str:
    return " ".join(str(text).replace("\x00", " ").split())


def _heading_level(style: str) -> int | None:
    name = style.strip().casefold()
    if name in {"title", "nosaukums", "название"}:
        return 0
    match = re.match(r"(?:heading|virsraksts|заголовок)\s*(\d)$", name)
    return int(match.group(1)) if match else None


def read_docx_blocks(source) -> tuple[DocxBlock, ...]:
    """Paragraphs and tables of a DOCX file (path or bytes) in document order."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(BytesIO(source) if isinstance(source, (bytes, bytearray))
                        else str(Path(source)))
    blocks = []
    for index, part in enumerate(document.iter_inner_content()):
        if isinstance(part, Paragraph):
            try:
                style = part.style.name if part.style is not None else ""
            except (AttributeError, KeyError, ValueError):
                style = ""
            blocks.append(DocxBlock(index, "paragraph", part.text, style or "",
                                    _heading_level(style or "")))
        elif isinstance(part, Table):
            rows = tuple(tuple(cell.text for cell in row.cells) for row in part.rows)
            blocks.append(DocxBlock(index, "table", rows=rows))
    return tuple(blocks)


def _answer_cell(text: str) -> bool:
    """A short printed answer code or label (one line), not a marker."""
    clean = _clean(text)
    return (bool(clean) and "\n" not in text.strip() and len(clean) <= 30
            and len(clean.split()) <= 4 and not set(clean) <= _MARKER_CHARS)


def _column_title(text: str) -> bool:
    words = [w.strip(":.").casefold() for w in _clean(text).split()]
    return not words or (len(words) <= 4 and any(w in _COLUMN_TITLE_WORDS for w in words))


def _statement(text: str) -> bool:
    return len(re.findall(r"[^\W\d_]", text)) >= 3


def find_forms(blocks) -> tuple[TableForm, ...]:
    """Questionnaire forms among the tables of ``blocks`` (document order)."""
    forms = []
    previous_table = -1
    table_number = 0
    blocks = list(blocks)
    for position, block in enumerate(blocks):
        if block.kind != "table":
            continue
        table_number += 1
        before = [b for b in blocks[previous_table + 1:position] if b.kind == "paragraph"]
        previous_table = position
        form = _table_form(block, table_number, before)
        if form is not None:
            forms.append(form)
    return tuple(forms)


def _number_column(rows) -> bool:
    numbered = [r for r in rows if len(r) >= 3 and _NUMBER_CELL.match(r[0] or "")
                and _statement(r[1])]
    return len(numbered) >= max(MIN_FORM_ROWS, 0.8 * len(rows) - 1)


def _table_form(block: DocxBlock, table_number: int, before) -> TableForm | None:
    raw_rows = [tuple(block.rows[r]) for r in range(len(block.rows))]
    if len(raw_rows) < MIN_FORM_ROWS or max((len(r) for r in raw_rows), default=0) < 3:
        return None
    width = max(len(r) for r in raw_rows)
    raw_rows = [r + ("",) * (width - len(r)) for r in raw_rows]
    number_column = _number_column(raw_rows)
    stmt = 1 if number_column else 0
    answer_count = width - stmt - 1
    if not 2 <= answer_count <= MAX_ANSWER_COLUMNS:
        return None
    statements = [(k, r) for k, r in enumerate(raw_rows) if _statement(r[stmt])]
    signatures = Counter(tuple(_clean(c) for c in r[stmt + 1:]) for _, r in statements)
    if not signatures:
        return None
    dominant, count = signatures.most_common(1)[0]
    if count < max(MIN_FORM_ROWS, SIGNATURE_SHARE * len(statements)):
        return None
    sample = next(r for _, r in statements if tuple(_clean(c) for c in r[stmt + 1:]) == dominant)
    if not all(_answer_cell(cell) for cell in sample[stmt + 1:]):
        return None   # markers, blank boxes or code + label cells: other readers
    if match_header(" ".join(dominant)) is not None:
        return None   # True / False answer cells: binary_responses handles them
    first_body = next(k for k, r in statements if tuple(_clean(c) for c in r[stmt + 1:]) == dominant)
    inline = [_INLINE_NUMBER.match(_clean(r[stmt])) for _, r in statements]
    numbered = number_column or sum(1 for m in inline if m) >= 0.8 * len(statements)
    header_rows = list(range(first_body))
    if numbered and not number_column and not _INLINE_NUMBER.match(_clean(raw_rows[first_body][stmt])):
        header_rows.append(first_body)   # an unnumbered first row above numbered items
    elif not numbered and _column_title(raw_rows[first_body][stmt]) and first_body + 1 < len(raw_rows):
        header_rows.append(first_body)   # "Statement | 1 | 2 | 3 | 4"
    rows, issues, order = [], [], 0
    for k, raw in enumerate(raw_rows):
        if k in header_rows or k < first_body:
            continue
        cell = _clean(raw[stmt])
        answers = tuple(_clean(c) for c in raw[stmt + 1:])
        if not _statement(cell):
            continue
        if not any(answers):
            issues.append(f"Table row {k + 1} prints no answer cells; it was not counted as an item.")
            continue
        order += 1
        number, printed, statement = order, False, cell
        if number_column and _NUMBER_CELL.match(raw[0] or ""):
            number, printed = int(_NUMBER_CELL.match(raw[0]).group(1)), True
        elif numbered:
            match = _INLINE_NUMBER.match(cell)
            if match:
                number, printed, statement = int(match.group(1)), True, _clean(match.group(2))
        if answers != dominant:
            issues.append(f"Table row {k + 1} prints different answer cells ("
                          + " | ".join(a or "—" for a in answers) + ").")
        rows.append(FormRow(number, printed, statement, cell, k + 1, answers))
    if len(rows) < MIN_FORM_ROWS:
        return None
    header = tuple(_clean(c) for c in raw_rows[header_rows[-1]]) if header_rows else ()
    title, instruction = _title_and_instruction(before)
    scale = _documented_scale(raw_rows, header_rows, stmt, dominant, instruction)
    return TableForm(
        f"docx-table-{table_number}", block.index, table_number, title, instruction,
        header, tuple(rows), answer_count, scale, numbered, tuple(issues),
    )


def _title_and_instruction(before) -> tuple[str, str]:
    """The nearest heading before the table and the instruction after it."""
    paragraphs = [b for b in before if _clean(b.text)]
    heading_at = next((k for k in range(len(paragraphs) - 1, -1, -1)
                       if paragraphs[k].heading_level is not None), None)
    if heading_at is None:
        heading_at = next((k for k in range(len(paragraphs) - 1, -1, -1)
                           if is_title_line(paragraphs[k].text)), None)
    title = _clean(paragraphs[heading_at].text)[:120] if heading_at is not None else ""
    after = paragraphs[heading_at + 1:] if heading_at is not None else paragraphs[-2:]
    instruction = next((_clean(b.text) for b in reversed(after) if code_label_pairs(b.text)), "")
    return title, instruction


def _documented_scale(rows, header_rows, stmt, dominant, instruction) -> DocumentedScale | None:
    size = len(dominant)
    body_codes = dominant if all(re.fullmatch(r"-?\d{1,2}", c) for c in dominant) else None
    labels, header_codes = None, None
    for k in header_rows:
        cells = tuple(_clean(c) for c in rows[k][stmt + 1:])
        if all(re.fullmatch(r"-?\d{1,2}", c) for c in cells):
            header_codes = cells
        elif all(re.search(r"[^\W\d_]", c) for c in cells) and len(set(cells)) == size:
            labels = cells
    legend = code_label_pairs(instruction) if instruction else ()
    issues = []
    if legend and len(legend) != size:
        issues.append(f"The instruction lists {len(legend)} answer options but the table "
                      f"has {size} answer columns; check the source.")
        legend = ()
    if labels is not None:
        codes = body_codes or header_codes
        if legend:
            same = [_fold(l) for _, l in legend] == [_fold(l) for l in labels]
            if not same:
                issues.append("The instruction (" + "; ".join(f"{c} = {l}" for c, l in legend)
                              + ") names other answer options than the table header ("
                              + " / ".join(labels) + "); check which the form uses.")
            elif codes is None:
                codes = tuple(c for c, _ in legend)
        codes = tuple(codes) if codes else (None,) * size
        source = " · ".join(f"{c} {l}" if c else l for c, l in zip(codes, labels))
        return DocumentedScale(labels, codes, labels, "header", 1, source[:160], tuple(issues))
    if legend:
        codes = tuple(c for c, _ in legend)
        printed_codes = body_codes or header_codes
        if printed_codes and tuple(printed_codes) != codes:
            issues.append("The table cells print the codes " + " / ".join(printed_codes)
                          + " but the instruction numbers the options "
                          + " / ".join(codes) + "; check the source.")
        labels = tuple(label for _, label in legend)
        return DocumentedScale(labels, codes, labels, "instruction", 1, instruction[:160],
                               tuple(issues))
    if body_codes is None and all(re.search(r"[^\W\d_]{2}", c) for c in dominant) \
            and len({_fold(c) for c in dominant}) == size:
        # The answer labels are printed in every row's own cells.
        return DocumentedScale(tuple(dominant), (None,) * size, tuple(dominant), "row", 1,
                               " · ".join(dominant)[:160], tuple(issues))
    return None


def _fold(label: str) -> str:
    return re.sub(r"\s+", "", label).casefold()


__all__ = ["DocxBlock", "FormRow", "TableForm", "find_forms", "read_docx_blocks"]
