"""Conservative reconstruction of row/column (Likert-type) questionnaire grids.

Sources:

* native DOCX tables (preferred — cell structure is explicit),
* positioned words from a PDF text layer or Tesseract OCR
  (:class:`ocr_layout.OCRPage`).

A :class:`MatrixProposal` keeps the *original* detected grid
(``source_grid``) untouched, while an editable copy (rows, columns, cells)
is corrected by the researcher. Nothing is scored from visual order: numeric
codes and reverse-keyed items become question metadata only through an
explicit verification + confirmation step, and every edit resets it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from io import BytesIO
import re
from statistics import median
from typing import Iterable

from ocr_layout import BBox, OCRPage, OCRWord, box_center, union_box
from survey_storage import validate_questions

MAX_MATRIX_ROWS = 200
MAX_MATRIX_COLUMNS = 11
MIN_MATRIX_COLUMNS = 2
MARKERS = set("○◯◦●□☐■▢◻◽⬜❍OoQ0DXx✓✔·•[]()")
ITEM_NUMBER = re.compile(r"^(\d{1,3})(?:[.):,]|\*)?$")
GLUED_NUMBER = re.compile(r"^(\d{1,3})[.):,](\S.*)$")
CODE_LABEL = re.compile(r"^\s*(-?\d{1,3})\s*(?:=|-|–|:|\.)\s*(.+?)\s*$")
INTEGER = re.compile(r"^-?\d{1,3}$")
CELL_STATES = ("filled", "empty", "missing", "ambiguous")


@dataclass(frozen=True)
class MatrixColumn:
    id: str
    label: str
    code: str | None = None
    group: str = ""
    box: BBox | None = None
    ambiguous: bool = False  # header text overlapped several columns


@dataclass(frozen=True)
class MatrixCell:
    text: str
    state: str  # filled | empty | missing | ambiguous
    box: BBox | None = None
    provenance: str = "detected"  # detected | manual | reviewed


@dataclass(frozen=True)
class MatrixRow:
    id: str
    number: int | None
    prompt: str
    cells: tuple[MatrixCell, ...]
    page: int
    box: BBox | None = None
    provenance: str = "detected"
    reverse_proposed: bool = False
    multiline: bool = False


@dataclass(frozen=True)
class MatrixProposal:
    id: str
    title: str
    source_kind: str  # docx_table | pdf_text_layer | tesseract_tsv
    pages: tuple[int, ...]
    columns: tuple[MatrixColumn, ...]
    rows: tuple[MatrixRow, ...]
    source_grid: tuple[tuple[str, ...], ...]
    issues: tuple[str, ...] = ()
    verified: bool = False
    edited: bool = False
    next_id: int = 1

    @property
    def unresolved_cells(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (r, c) for r, row in enumerate(self.rows)
            for c, cell in enumerate(row.cells)
            if cell.state in {"missing", "ambiguous"}
        )

    @property
    def codes(self) -> tuple[str | None, ...]:
        return tuple(column.code for column in self.columns)

    def blocking_problems(self) -> tuple[str, ...]:
        """Reasons the grid cannot be verified yet (empty = verifiable)."""
        problems = []
        if not self.rows:
            problems.append("The matrix has no rows.")
        if not MIN_MATRIX_COLUMNS <= len(self.columns) <= MAX_MATRIX_COLUMNS:
            problems.append("A rating matrix needs 2–11 response columns.")
        labels = [c.label.strip() for c in self.columns]
        if any(not label for label in labels):
            problems.append("Every response column needs a label.")
        for k, column in enumerate(self.columns, 1):
            if column.ambiguous:
                problems.append(f"Column {k} header overlaps another column; edit its label.")
        if len(set(labels)) != len(labels):
            problems.append("Response column labels must be distinct.")
        codes = [c.code for c in self.columns if c.code not in (None, "")]
        if codes and len(codes) != len(self.columns):
            problems.append("Either every column has a numeric code or none does.")
        if codes and (
            len(set(codes)) != len(codes)
            or any(not INTEGER.fullmatch(code) for code in codes)
        ):
            problems.append("Numeric codes must be unique integers.")
        for n, row in enumerate(self.rows, 1):
            if len(row.prompt.strip()) < 2:
                problems.append(f"Row {n} has no question text.")
            if len(row.cells) != len(self.columns):
                problems.append(f"Row {n} does not match the column count.")
        if self.unresolved_cells:
            problems.append(
                f"{len(self.unresolved_cells)} missing/ambiguous cell(s) must "
                "be corrected or accepted."
            )
        return tuple(problems)


# ---------------------------------------------------------------- helpers

def _clean(text: str) -> str:
    return " ".join(str(text).replace("\x00", " ").split())


def _is_marker_or_code(text: str) -> bool:
    t = text.strip()
    return bool(t) and (INTEGER.fullmatch(t) is not None or all(ch in MARKERS for ch in t))


def _split_code_label(text: str) -> tuple[str | None, str]:
    match = CODE_LABEL.match(text)
    if match and re.search(r"[^\W\d_]", match.group(2)):
        return match.group(1), match.group(2).strip()
    return None, text.strip()


def _cell_state(text: str, column_code: str | None) -> str:
    t = text.strip()
    if not t:
        return "empty"
    if INTEGER.fullmatch(t):
        return "filled" if column_code in (None, t) else "ambiguous"
    if all(ch in MARKERS for ch in t.replace(" ", "")):
        return "filled"
    return "ambiguous"


def _finalize_cells(rows: list[MatrixRow], columns: list[MatrixColumn]) -> list[MatrixRow]:
    """Mark empty cells as *missing* when the column is filled elsewhere."""
    filled_columns = {
        c for c in range(len(columns))
        if sum(1 for row in rows if row.cells[c].state == "filled") >= max(1, len(rows) // 2)
    }
    out = []
    for row in rows:
        cells = tuple(
            replace(cell, state="missing")
            if cell.state == "empty" and c in filled_columns else cell
            for c, cell in enumerate(row.cells)
        )
        out.append(replace(row, cells=cells))
    return out


def _infer_codes(rows: list[MatrixRow], columns: list[MatrixColumn]) -> list[MatrixColumn]:
    """Use a printed integer only when it repeats consistently in a column."""
    out = []
    for c, column in enumerate(columns):
        if column.code is not None:
            out.append(column)
            continue
        values = [row.cells[c].text.strip() for row in rows if INTEGER.fullmatch(row.cells[c].text.strip())]
        if values and values.count(max(set(values), key=values.count)) >= max(2, (len(rows) + 1) // 2):
            out.append(replace(column, code=max(set(values), key=values.count)))
        else:
            out.append(column)
    return out


def _issues(columns, rows, extra=()) -> tuple[str, ...]:
    issues = list(extra)
    codes = [c.code for c in columns]
    if all(code is not None for code in codes) and len(codes) >= 2:
        numbers = [int(code) for code in codes]
        if numbers == sorted(numbers, reverse=True):
            issues.append(
                "Printed codes DEScend from left to right. Verify the scale "
                "direction; visual order never implies scoring."
            )
        elif numbers != sorted(numbers):
            issues.append("Printed codes are not monotonic; verify the codebook.")
    elif any(code is not None for code in codes):
        issues.append("Only some columns show numeric codes; verify the codebook.")
    else:
        issues.append(
            "No numeric codes were printed; the rows can be imported as "
            "labelled choices, or you may enter codes manually."
        )
    numbers = [row.number for row in rows if row.number is not None]
    if numbers and numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        issues.append("Item numbering has gaps or repeats; check for missed rows.")
    if any(row.number is None for row in rows):
        issues.append("Some rows have no item number.")
    if any(row.reverse_proposed for row in rows):
        issues.append("Reverse-key marks were detected; they need explicit confirmation.")
    unresolved = sum(1 for row in rows for cell in row.cells if cell.state in {"missing", "ambiguous"})
    if unresolved:
        issues.append(f"{unresolved} missing or ambiguous cell(s) need review.")
    return tuple(dict.fromkeys(issues))


def _grid(columns, rows) -> tuple[tuple[str, ...], ...]:
    header = ("#", "Question", *(
        (f"{c.group} / " if c.group else "") + c.label + (f" [{c.code}]" if c.code is not None else "")
        for c in columns
    ))
    body = tuple(
        (str(row.number or ""), row.prompt, *(cell.text for cell in row.cells))
        for row in rows
    )
    return (header, *body)


def _build(pid, title, kind, pages, columns, rows, extra_issues=()) -> MatrixProposal:
    rows = _finalize_cells(rows, columns)
    columns = _infer_codes(rows, columns)
    rows = [
        replace(row, cells=tuple(
            replace(cell, state=_cell_state(cell.text, columns[c].code))
            if cell.state in {"filled", "ambiguous"} else cell
            for c, cell in enumerate(row.cells)
        ))
        for row in rows
    ]
    issues = _issues(columns, rows, extra_issues)
    return MatrixProposal(
        pid, title[:120], kind, tuple(sorted(set(pages))), tuple(columns),
        tuple(rows), _grid(columns, rows), issues,
        next_id=len(rows) + len(columns) + 1,
    )


# ------------------------------------------------------------------ DOCX

def docx_matrices(source: bytes) -> tuple[MatrixProposal, ...]:
    """Detect rating matrices in native DOCX tables (merged cells aware)."""
    from docx import Document

    document = Document(BytesIO(source))
    found = []
    title = ""
    table_index = 0
    for block in document.iter_inner_content():
        if block.__class__.__name__ == "Paragraph":
            if block.text.strip():
                title = _clean(block.text)
            continue
        table_index += 1
        proposal = _docx_table_matrix(block, table_index, title)
        if proposal is not None:
            found.append(proposal)
    return tuple(found)


def _docx_grid(table) -> list[list[tuple[str, int]]]:
    """Cell text with a span-identity token per grid position."""
    grid = []
    for row in table.rows[:MAX_MATRIX_ROWS + 10]:
        cells = []
        for cell in row.cells[:MAX_MATRIX_COLUMNS + 3]:
            cells.append((cell.text.strip(), id(cell._tc)))
        grid.append(cells)
    return grid


def _docx_table_matrix(table, index: int, title: str) -> MatrixProposal | None:
    grid = _docx_grid(table)
    if len(grid) < 3:
        return None
    width = max(len(r) for r in grid)
    # Prompt column: first column whose body cells are mostly long text.
    def is_item(row):
        texts = [t for t, _ in row]
        if not texts or len(texts) < 3:
            return False
        prompt_col = 1 if ITEM_NUMBER.fullmatch(texts[0] or "-") and len(texts) > 3 else 0
        prompt = texts[prompt_col]
        rest = texts[prompt_col + 1:]
        return (
            len(prompt.split()) >= 2
            and sum(1 for t in rest if not t or _is_marker_or_code(t)) >= len(rest) - 1
        )

    first_item = next((i for i, row in enumerate(grid) if is_item(row)), None)
    if first_item is None or first_item == 0:
        return None
    sample = [t for t, _ in grid[first_item]]
    prompt_col = 1 if ITEM_NUMBER.fullmatch(sample[0] or "-") and len(sample) > 3 else 0
    response_cols = list(range(prompt_col + 1, width))
    if not MIN_MATRIX_COLUMNS <= len(response_cols) <= MAX_MATRIX_COLUMNS:
        return None
    header_rows = grid[:first_item]
    labels = [""] * len(response_cols)
    groups = [""] * len(response_cols)
    codes: list[str | None] = [None] * len(response_cols)
    issues = []
    for hr in header_rows:
        cells = [hr[c] if c < len(hr) else ("", -c) for c in response_cols]
        spans: dict[int, list[int]] = {}
        for k, (_text, token) in enumerate(cells):
            spans.setdefault(token, []).append(k)
        texts = [t for t, _ in cells]
        merged = any(len(v) > 1 for v in spans.values())
        if texts and all(INTEGER.fullmatch(t) for t in texts if t) and any(texts):
            for k, t in enumerate(texts):
                codes[k] = t or None
            continue
        if merged:
            for token, positions in spans.items():
                text = cells[positions[0]][0]
                if len(positions) > 1 and text:
                    for k in positions:
                        groups[k] = text
                elif text:
                    labels[positions[0]] = text
            issues.append("Merged header cells were treated as a column group label.")
            continue
        for k, text in enumerate(texts):
            if text:
                labels[k] = (labels[k] + " " + text).strip() if labels[k] and labels[k] != text else text
    for k, label in enumerate(labels):
        code, plain = _split_code_label(label)
        if code is not None:
            codes[k] = codes[k] or code
            labels[k] = plain
    columns = [
        MatrixColumn(f"c{k+1}", labels[k], codes[k], groups[k])
        for k in range(len(response_cols))
    ]
    rows = []
    number_seen = 0
    for i, raw in enumerate(grid[first_item:], first_item):
        texts = [t for t, _ in raw] + [""] * (width - len(raw))
        prompt_text = texts[prompt_col]
        if not prompt_text and not any(texts[c] for c in response_cols):
            continue
        number = None
        if prompt_col == 1 and ITEM_NUMBER.fullmatch(texts[0] or "-"):
            number = int(re.match(r"\d+", texts[0]).group())
        multiline = "\n" in prompt_text
        prompt = _clean(prompt_text)
        reverse = False
        glued = re.match(r"^(\d{1,3})\s*(\*?)\s*[.):]\s*(.+)$", prompt)
        if glued and number is None:
            number, reverse, prompt = int(glued.group(1)), bool(glued.group(2)), glued.group(3)
        if prompt.endswith("*") or "(R)" in prompt:
            reverse = True
            prompt = prompt.rstrip("*").replace("(R)", "").strip()
        if not prompt and rows:
            # Continuation row: text only in response area is ambiguous.
            issues.append(f"Table row {i+1} has cells but no question text.")
        cells = tuple(
            MatrixCell(_clean(texts[c]), "filled" if texts[c].strip() else "empty",
                       None, f"DOCX table {index}, row {i+1}, column {c+1}")
            for c in response_cols
        )
        if len(raw) < width:
            issues.append(f"Table row {i+1} has fewer cells than the header.")
            cells = tuple(
                replace(cell, state="missing") if c + prompt_col + 1 >= len(raw) else cell
                for c, cell in enumerate(cells)
            )
        number_seen += 1
        rows.append(MatrixRow(
            f"r{number_seen}", number, prompt[:300], cells, 1, None,
            f"DOCX table {index}, row {i+1}", reverse, multiline,
        ))
    if len(rows) < 2:
        return None
    if any(row.multiline for row in rows):
        issues.append("Multi-line question cells were joined into one prompt.")
    return _build(f"docx-t{index}", title or f"Word table {index}",
                  "docx_table", (1,), columns, rows[:MAX_MATRIX_ROWS], issues)


# ----------------------------------------------------- geometric (PDF/OCR)

def _item_start(line) -> tuple[int, bool, list[OCRWord]] | None:
    """Detect a leading item number on a positioned line."""
    words = list(line.words)
    if not words:
        return None
    first = words[0].text.strip()
    match = ITEM_NUMBER.fullmatch(first)
    if match and len(words) >= 2:
        return int(match.group(1)), first.endswith("*"), words[1:]
    glued = GLUED_NUMBER.match(first)
    if glued:
        rest = glued.group(2)
        # "3.1" (OCR of "3. I") keeps the trailing token as prompt text.
        replacement = replace(words[0], text=rest)
        return int(glued.group(1)), False, [replacement, *words[1:]]
    return None


def _cluster(values: list[float], gap: float) -> list[list[float]]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= gap:
            groups[-1].append(value)
        else:
            groups.append([value])
    return groups


def _row_band_words(page: OCRPage, top: float, bottom: float) -> list[OCRWord]:
    return [w for w in page.words if top <= box_center(w.box)[1] < bottom]


def _page_layout(page: OCRPage):
    """Find numbered rows and token columns on one page."""
    lines = sorted(page.lines, key=lambda l: (l.box[1], l.box[0]))
    if not lines:
        return None
    left_margin = min(l.box[0] for l in lines)
    starts = []
    for k, line in enumerate(lines):
        detected = _item_start(line)
        if detected and line.box[0] <= left_margin + 0.06:
            starts.append((k, *detected))
    if len(starts) < 2:
        return None
    heights = [w.box[3] - w.box[1] for w in page.words] or [0.01]
    unit = median(heights)
    # Response tokens: short codes/markers right of the prompt start.
    tokens = []
    for k, _n, _r, words in starts:
        for word in words:
            if _is_marker_or_code(word.text) and word.box[0] > lines[k].box[0] + 0.15:
                tokens.append(box_center(word.box)[0])
    columns = []
    for group in _cluster(tokens, max(unit * 1.5, 0.015)):
        if len(group) >= max(2, len(starts) // 2):
            columns.append(sum(group) / len(group))
    return lines, starts, columns, unit


def _header_columns(lines, first_row_top: float, prompt_left: float, unit: float):
    """Header labels above the first row: clusters of words right of prompts."""
    above = [l for l in lines if l.box[3] <= first_row_top + unit * 0.2]
    candidates = [l for l in above[-3:] if l.box[0] > prompt_left + 0.25 or (
        len(l.words) >= 2 and sum(1 for w in l.words if w.box[0] > prompt_left + 0.3) >= 2
    )]
    return candidates


def _assign_header(header_lines, centers: list[float], bounds: list[tuple[float, float]], unit):
    labels = [""] * len(centers)
    groups = [""] * len(centers)
    codes: list[str | None] = [None] * len(centers)
    ambiguous = [False] * len(centers)
    issues = []
    for line in header_lines:
        words = [w for w in line.words if w.box[2] > bounds[0][0]]
        if words and all(INTEGER.fullmatch(w.text) for w in words):
            for w in words:
                k = _nearest(box_center(w.box)[0], centers)
                codes[k] = w.text
            continue
        for word in words:
            covered = [k for k, (lo, hi) in enumerate(bounds)
                       if word.box[0] < hi - unit * 0.3 and word.box[2] > lo + unit * 0.3]
            covered = [k for k in covered if word.box[0] <= centers[k] <= word.box[2]] or covered
            if not covered:
                continue
            if len(covered) > 1 and (word.box[2] - word.box[0]) > 1.6 * (bounds[0][1] - bounds[0][0]):
                for k in covered:
                    groups[k] = (groups[k] + " " + word.text).strip()
                continue
            if len(covered) > 1:
                issues.append(
                    f"Header text '{word.text}' spans columns "
                    f"{covered[0]+1}–{covered[-1]+1}; correct the labels."
                )
                for k in covered:
                    labels[k] = (labels[k] + " " + word.text).strip()
                    ambiguous[k] = True
                continue
            k = covered[0]
            labels[k] = (labels[k] + " " + word.text).strip()
    for k, label in enumerate(labels):
        code, plain = _split_code_label(label)
        if code is not None:
            codes[k], labels[k] = codes[k] or code, plain
    return labels, groups, codes, ambiguous, issues


def _nearest(x: float, centers: list[float]) -> int:
    return min(range(len(centers)), key=lambda k: abs(centers[k] - x))


def geometric_matrices(pages: Iterable[OCRPage]) -> tuple[MatrixProposal, ...]:
    """Reconstruct matrices from positioned words (OCR or PDF text layer)."""
    proposals: list[MatrixProposal] = []
    previous = None  # (proposal index, centers, bounds, last_number)
    for page in sorted(pages, key=lambda p: p.page_number):
        if not page.has_geometry:
            continue
        layout = _page_layout(page)
        if layout is None:
            continue
        lines, starts, centers, unit = layout
        prompt_left = min(lines[k].box[0] for k, *_ in starts)
        first_top = lines[starts[0][0]].box[1]
        header_lines = _header_columns(lines, first_top, prompt_left, unit)
        carried = False
        extra = []
        if not centers and header_lines:
            words = [w for l in header_lines for w in l.words if w.box[0] > prompt_left + 0.25]
            groups = []
            for word in sorted(words, key=lambda w: w.box[0]):
                if groups and word.box[0] - groups[-1][-1].box[2] <= unit * 1.2:
                    groups[-1].append(word)
                else:
                    groups.append([word])
            centers = [box_center(union_box(w.box for w in g))[0] for g in groups]
            extra.append("Columns were inferred from header labels only; no printed codes or markers were read.")
        continuation = (
            previous is not None and (not header_lines or not centers)
            and starts[0][1] == previous[3] + 1
        )
        if continuation or (
            previous is not None and centers and len(centers) == len(previous[1])
            and starts[0][1] == previous[3] + 1
            and all(abs(a - b) < 0.03 for a, b in zip(centers, previous[1]))
        ):
            centers, bounds = previous[1], previous[2]
            carried = True
        if not MIN_MATRIX_COLUMNS <= len(centers) <= MAX_MATRIX_COLUMNS:
            previous = None
            continue
        if not carried:
            bounds = []
            for k, center in enumerate(centers):
                lo = (centers[k-1] + center) / 2 if k else center - (centers[1] - centers[0]) / 2
                hi = (centers[k+1] + center) / 2 if k + 1 < len(centers) else center + (center - centers[k-1]) / 2
                bounds.append((lo, hi))
        prompt_right = bounds[0][0]
        line_rank = {line.id: rank for rank, line in enumerate(lines)}
        # Row bands: from each numbered line to the next numbered line.
        row_tops = [lines[k].box[1] for k, *_ in starts]
        rows = []
        for idx, (k, number, starred, words) in enumerate(starts):
            top = lines[k].box[1] - unit * 0.3
            bottom = (row_tops[idx + 1] - unit * 0.3) if idx + 1 < len(starts) else (
                lines[k].box[3] + unit * 2.6
            )
            band = _row_band_words(page, top, bottom)
            number_word = lines[k].words[0]
            pure_number = ITEM_NUMBER.fullmatch(number_word.text.strip()) is not None
            prompt_words = []
            for w in band:
                if box_center(w.box)[0] >= prompt_right:
                    continue
                if w.id == number_word.id:
                    if pure_number:
                        continue
                    w = words[0]  # glued "3.I" → keep the text after the number
                prompt_words.append(w)
            prompt_words.sort(key=lambda w: (line_rank.get(w.line_id, 0), w.box[0]))
            line_ids = {w.line_id for w in prompt_words}
            prompt = _clean(" ".join(w.text for w in prompt_words))
            reverse = starred or prompt.endswith("*") or "(R)" in prompt
            prompt = prompt.rstrip("*").replace("(R)", "").strip()
            cells = []
            for lo, hi in bounds:
                inside = [w for w in band if lo <= box_center(w.box)[0] < hi]
                text = _clean(" ".join(w.text for w in sorted(inside, key=lambda w: w.box[0])))
                cell_box = union_box(w.box for w in inside) if inside else (
                    lo, max(0.0, top), hi, min(1.0, lines[k].box[3])
                )
                cells.append(MatrixCell(
                    text, "filled" if text else "empty", cell_box,
                    f"page {page.page_number} ({page.source})",
                ))
            row_box = union_box([lines[k].box, *(w.box for w in prompt_words)]) if prompt_words else lines[k].box
            rows.append(MatrixRow(
                f"r{len(rows)+1}", number, prompt[:300], tuple(cells),
                page.page_number, row_box, f"page {page.page_number} line {lines[k].id}",
                reverse, len(line_ids) > 1,
            ))
        if carried and previous is not None:
            index = previous[0]
            old = proposals[index]
            merged_rows = list(old.rows) + [
                replace(r, id=f"r{len(old.rows)+n+1}") for n, r in enumerate(rows)
            ]
            proposals[index] = _build(
                old.id, old.title, old.source_kind, (*old.pages, page.page_number),
                list(old.columns), merged_rows,
                (*old.issues, f"Rows on page {page.page_number} reuse the column "
                 f"layout of page {old.pages[0]}; verify the page break."),
            )
            previous = (index, centers, bounds, rows[-1].number or previous[3])
            continue
        labels, group_labels, codes, ambiguous, header_issues = _assign_header(
            header_lines, centers, bounds, unit,
        )
        title_line = next((l for l in lines if l.box[3] < (header_lines[0].box[1] if header_lines else first_top)), None)
        columns = [
            MatrixColumn(f"c{k+1}", labels[k], codes[k], group_labels[k],
                         (bounds[k][0], header_lines[0].box[1], bounds[k][1], header_lines[-1].box[3]) if header_lines else None,
                         ambiguous[k])
            for k in range(len(centers))
        ]
        if any(r.multiline for r in rows):
            extra.append("Wrapped question text was joined across lines.")
        proposal = _build(
            f"{page.source}-p{page.page_number}",
            title_line.text if title_line else f"Matrix on page {page.page_number}",
            page.source, (page.page_number,), columns, rows[:MAX_MATRIX_ROWS],
            (*extra, *header_issues),
        )
        proposals.append(proposal)
        previous = (len(proposals) - 1, centers, bounds, rows[-1].number or 0)
    return tuple(proposals)


# --------------------------------------------------------------- editing

def _edited(proposal: MatrixProposal, **changes) -> MatrixProposal:
    """Every edit invalidates verification (and therefore any approval)."""
    return replace(proposal, verified=False, edited=True, **changes)


def _check_row(proposal, index):
    if not 0 <= index < len(proposal.rows):
        raise IndexError("Select a valid matrix row.")


def _check_column(proposal, index):
    if not 0 <= index < len(proposal.columns):
        raise IndexError("Select a valid matrix column.")


def set_cell(proposal: MatrixProposal, row: int, column: int, text: str) -> MatrixProposal:
    _check_row(proposal, row)
    _check_column(proposal, column)
    clean = _clean(text)[:40]
    target = proposal.rows[row]
    cells = list(target.cells)
    cells[column] = replace(
        cells[column], text=clean,
        state=_cell_state(clean, proposal.columns[column].code) if clean else "empty",
        provenance="manual",
    )
    rows = list(proposal.rows)
    rows[row] = replace(target, cells=tuple(cells))
    return _edited(proposal, rows=tuple(rows))


def accept_cell(proposal: MatrixProposal, row: int, column: int) -> MatrixProposal:
    """Researcher confirms a flagged cell as it is (e.g. a legitimately blank box)."""
    _check_row(proposal, row)
    _check_column(proposal, column)
    target = proposal.rows[row]
    cells = list(target.cells)
    cell = cells[column]
    cells[column] = replace(
        cell, state="filled" if cell.text else "empty", provenance="reviewed",
    )
    rows = list(proposal.rows)
    rows[row] = replace(target, cells=tuple(cells))
    return _edited(proposal, rows=tuple(rows))


def set_row(proposal: MatrixProposal, row: int, *, prompt: str | None = None,
            number: int | None | str = "", reverse_proposed: bool | None = None) -> MatrixProposal:
    _check_row(proposal, row)
    target = proposal.rows[row]
    changes = {"provenance": "manual"}
    if prompt is not None:
        clean = _clean(prompt)
        if len(clean) > 300:
            raise ValueError("Question text must be at most 300 characters.")
        changes["prompt"] = clean
    if number != "":
        if number is not None and (not isinstance(number, int) or not 1 <= number <= 999):
            raise ValueError("Item numbers must be 1–999.")
        changes["number"] = number
    if reverse_proposed is not None:
        changes["reverse_proposed"] = bool(reverse_proposed)
    rows = list(proposal.rows)
    rows[row] = replace(target, **changes)
    return _edited(proposal, rows=tuple(rows))


def add_row(proposal: MatrixProposal, index: int | None = None, prompt: str = "") -> MatrixProposal:
    if len(proposal.rows) >= MAX_MATRIX_ROWS:
        raise ValueError("The matrix already has the maximum number of rows.")
    index = len(proposal.rows) if index is None else max(0, min(index, len(proposal.rows)))
    page = proposal.rows[index - 1].page if index and proposal.rows else (proposal.pages or (1,))[0]
    row = MatrixRow(
        f"r{proposal.next_id}", None, _clean(prompt)[:300],
        tuple(MatrixCell("", "empty", None, "manual") for _ in proposal.columns),
        page, None, "added manually",
    )
    rows = list(proposal.rows)
    rows.insert(index, row)
    return _edited(proposal, rows=tuple(rows), next_id=proposal.next_id + 1)


def delete_row(proposal: MatrixProposal, row: int) -> MatrixProposal:
    _check_row(proposal, row)
    return _edited(proposal, rows=tuple(r for k, r in enumerate(proposal.rows) if k != row))


def move_row(proposal: MatrixProposal, row: int, delta: int) -> MatrixProposal:
    _check_row(proposal, row)
    target = max(0, min(len(proposal.rows) - 1, row + delta))
    rows = list(proposal.rows)
    rows.insert(target, rows.pop(row))
    return _edited(proposal, rows=tuple(rows))


def set_column(proposal: MatrixProposal, column: int, *, label: str | None = None,
               code: str | None = "") -> MatrixProposal:
    _check_column(proposal, column)
    target = proposal.columns[column]
    changes = {}
    if label is not None:
        clean = _clean(label)
        if len(clean) > 100:
            raise ValueError("Column labels must be at most 100 characters.")
        changes["label"] = clean
        changes["ambiguous"] = False
    if code != "":
        if code is not None:
            code = code.strip()
            if code and not INTEGER.fullmatch(code):
                raise ValueError("A numeric code must be an integer such as 0, 1 or -2.")
            code = code or None
        changes["code"] = code
    columns = list(proposal.columns)
    columns[column] = replace(target, **changes)
    return _edited(proposal, columns=tuple(columns))


def add_column(proposal: MatrixProposal, index: int | None = None, label: str = "",
               code: str | None = None) -> MatrixProposal:
    if len(proposal.columns) >= MAX_MATRIX_COLUMNS:
        raise ValueError("A rating matrix supports at most 11 columns.")
    index = len(proposal.columns) if index is None else max(0, min(index, len(proposal.columns)))
    columns = list(proposal.columns)
    columns.insert(index, MatrixColumn(f"c{proposal.next_id}", _clean(label), code))
    rows = []
    for row in proposal.rows:
        cells = list(row.cells)
        cells.insert(index, MatrixCell("", "empty", None, "manual"))
        rows.append(replace(row, cells=tuple(cells)))
    return _edited(proposal, columns=tuple(columns), rows=tuple(rows),
                   next_id=proposal.next_id + 1)


def delete_column(proposal: MatrixProposal, column: int) -> MatrixProposal:
    _check_column(proposal, column)
    return _edited(
        proposal,
        columns=tuple(c for k, c in enumerate(proposal.columns) if k != column),
        rows=tuple(
            replace(r, cells=tuple(c for k, c in enumerate(r.cells) if k != column))
            for r in proposal.rows
        ),
    )


def move_column(proposal: MatrixProposal, column: int, delta: int) -> MatrixProposal:
    _check_column(proposal, column)
    target = max(0, min(len(proposal.columns) - 1, column + delta))
    columns = list(proposal.columns)
    columns.insert(target, columns.pop(column))
    rows = []
    for row in proposal.rows:
        cells = list(row.cells)
        cells.insert(target, cells.pop(column))
        rows.append(replace(row, cells=tuple(cells)))
    return _edited(proposal, columns=tuple(columns), rows=tuple(rows))


def verify_matrix(proposal: MatrixProposal) -> MatrixProposal:
    """Researcher confirms the grid mapping (not scoring) matches the source."""
    problems = proposal.blocking_problems()
    if problems:
        raise ValueError("Cannot verify the matrix: " + " ".join(problems))
    return replace(proposal, verified=True)


def matrix_to_questions(
    proposal: MatrixProposal, *, accept_codes: bool = False,
    accept_reverse: bool = False, scale_id: str = "matrix_scale",
    key_prefix: str = "matrix_q", section: str = "",
) -> list[dict]:
    """Turn verified rows into survey questions sharing one response scale.

    Without ``accept_codes`` the rows become *labelled single-choice*
    questions; numeric scale values and reverse keys are never implied.
    """
    if not proposal.verified:
        raise ValueError("Verify the matrix grid against the source first.")
    if accept_reverse and not accept_codes:
        raise ValueError("Confirm numeric response codes before applying reverse keys.")
    codes = proposal.codes
    if accept_codes and any(code is None for code in codes):
        raise ValueError("Every column needs a numeric code before codes can be applied.")
    questions = []
    for n, row in enumerate(proposal.rows, 1):
        question = {
            "key": f"{key_prefix}{n:03d}", "prompt": row.prompt, "required": False,
            "page": 1, "section": (section or proposal.title)[:80],
        }
        if accept_codes:
            question.update({
                "kind": "rating_scale",
                "value_labels": {code: column.label for code, column in zip(codes, proposal.columns)},
                "scale_id": scale_id,
                "reverse_scored": bool(accept_reverse and row.reverse_proposed),
            })
        else:
            question.update({
                "kind": "single_choice",
                "options": [column.label for column in proposal.columns],
            })
        questions.append(question)
    return validate_questions(questions)
