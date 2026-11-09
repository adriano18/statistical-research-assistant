"""Rows of a scanned questionnaire table, rebuilt from OCR word positions.

A scanned table prints the item number in its own column, the statement in
a second column (wrapped onto further lines) and the answer codes in a
column on the right. Read as plain text, a tick or speck before a number
(``"17.``) or answer digits glued together (``1283845``) end a numbered
sequence. This module works from Tesseract word boxes instead
(:class:`ocr_layout.OCRPage`, normalised 0..1 page coordinates):

1. **Columns.** Lines that start with a clean number (``12.``) followed by a
   word give the number column; the left edges of those words give the
   statement column (fitted against the page height, so a slight rotation
   does not matter) and the aligned code-like tokens at the line ends give
   the answer column. A number followed by its text at an ordinary word gap
   (``12. Text``) is NOT a column: such pages keep the line parser.
2. **Rows.** A line whose number-column text reads as the next number of
   the sequence starts a row. OCR noise is normalised in the number column
   only: quotes, ticks and dashes are stripped; look-alike glyphs (I l | ī →
   1, O o → 0) are mapped only when the result is the expected next number.
   A row whose number cannot be read but whose statement and answer digits
   are in place gets the expected number. Every normalised or inferred
   number is flagged "check this number" — never silently accepted.
3. **Continuations.** A line without a number whose text starts in the
   statement column, directly under a row, is appended to that row.
4. **Answer digits** are removed from the statement by position (the
   answer column), not by a pattern on the text.
5. **Legend.** Lines such as ``1- …`` to ``5- …`` (also when repeated at
   the top of the next page) are the answer legend: evidence for ONE shared
   response scale, never items. Lines that look like noise from table rules
   or specks (low OCR confidence, no letters) inside the table are dropped.

Every row keeps its page and box (number + statement words) as the source
region shown in review. OCR confidence stays Tesseract's per-word character
score; nothing here is a measure of item quality, reliability or validity.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from statistics import median
import re

from ocr_layout import (
    BBox, OCRLine, OCRPage, OCRWord, Region, SpatialEvidence, question_ref, union_box,
)
from response_scales import code_label_pairs, legend_run, line_code_label, normalize_tokens
from scientific_survey_import import DocumentedScale, StructuredItemLine, is_title_line

MIN_ROWS = 3
MAX_JUMP = 3            # a printed number may skip at most this many missing rows
NOISE_CONFIDENCE = 50.0  # mean word score below which a line inside the table is noise
_NUMBER = re.compile(r"^(\d{1,3})[.)]?$")
# Characters scan artifacts become around a number; they never stand for a digit.
_ARTIFACTS = "\"'`´‘’‚‛“”„‟«»‹›,:;_~^*°·•-–—/\\"
# Glyphs OCR reads instead of a digit; mapped only to reach the expected number.
_LOOKALIKES = str.maketrans({
    "I": "1", "l": "1", "|": "1", "ī": "1", "Ī": "1", "í": "1", "ì": "1", "i": "1",
    "!": "1", "]": "1", "[": "1", "O": "0", "o": "0",
})


@dataclass(frozen=True)
class PageGeometry:
    """Columns of one scanned table page (x as page fractions)."""
    page: int
    statement_a: float        # statement column left edge: x = a + b * y
    statement_b: float
    number_reach: float       # how far left of the statement column numbers start
    answer_left: float | None  # left edge of the answer-code column, if printed
    line_height: float        # median text line height (y fraction)
    unit_x: float             # the line height as an x fraction
    rows: int = 0             # lines that start with a clean number in the column

    def statement_x(self, y: float) -> float:
        return self.statement_a + self.statement_b * y


@dataclass(frozen=True)
class TableRow:
    page: int
    number: int
    number_text: str          # what OCR read in the number column ("" if nothing)
    number_source: str        # "printed" | "normalised" | "inferred"
    prompt: str
    excerpt: str              # the row's first line as OCR read it
    box: BBox                 # number and statement words of all its lines
    line_ids: tuple[str, ...]
    prompt_lines: int
    answers: tuple[str, ...]  # tokens read in the answer column (not in the prompt)
    group: str


@dataclass(frozen=True)
class Legend:
    page: int
    pairs: tuple[tuple[str, str], ...]
    text: str
    top: float


@dataclass(frozen=True)
class TableReconstruction:
    lines: dict               # page number → page text with StructuredItemLine rows
    rows: tuple[TableRow, ...]
    legends: tuple[Legend, ...]
    geometry: tuple[PageGeometry, ...]
    dropped_lines: int        # noise lines inside the table (rules, specks)


def _x0(word: OCRWord) -> float:
    return word.box[0]


def _cx(word: OCRWord) -> float:
    return (word.box[0] + word.box[2]) / 2


def _cy(box: BBox) -> float:
    return (box[1] + box[3]) / 2


def _letters(text: str) -> int:
    return len(re.findall(r"[^\W\d_]", text))


def _words(line: OCRLine) -> list[OCRWord]:
    return sorted(line.words, key=_x0)


def _fit(points) -> tuple[float, float]:
    """Least-squares x = a + b * y (b = 0 for one distinct y)."""
    points = list(points)
    ys = [y for y, _ in points]
    xs = [x for _, x in points]
    my, mx = sum(ys) / len(ys), sum(xs) / len(xs)
    var = sum((y - my) ** 2 for y in ys)
    if var < 1e-9:
        return mx, 0.0
    b = sum((y - my) * (x - mx) for y, x in points) / var
    return mx - b * my, b


def read_number(text: str, expected: int | None) -> tuple[int, str] | None:
    """``(number, "printed" | "normalised")`` of a number-column token, or None.

    A clean ``12.`` is printed. Noise is normalised only here: quotes,
    ticks and dashes are stripped (the result may continue the sequence or
    skip a few missing rows); look-alike glyphs are mapped only when the
    result is exactly the expected next number.
    """
    token = "".join(str(text).split())
    strict = _NUMBER.fullmatch(token)
    if strict:
        return int(strict.group(1)), "printed"
    if expected is None or not token or len(token) > 8:
        return None
    core = token.lstrip(_ARTIFACTS + ".").rstrip(_ARTIFACTS)
    stripped = _NUMBER.fullmatch(core)
    if stripped and expected <= int(stripped.group(1)) <= expected + MAX_JUMP:
        return int(stripped.group(1)), "normalised"
    mapped = _NUMBER.fullmatch(core.translate(_LOOKALIKES))
    if mapped and int(mapped.group(1)) == expected:
        return expected, "normalised"
    return None


def _codeish(text: str) -> bool:
    t = text.strip()
    digits = sum(ch.isdigit() for ch in t)
    return bool(t) and len(t) <= 9 and digits >= max(1, len(t) // 2)


def _mean_confidence(words) -> float | None:
    scores = [w.confidence for w in words if w.confidence is not None]
    return sum(scores) / len(scores) if scores else None


def _texty(words) -> bool:
    """Real text: mostly letters and, when OCR scored it, a fair score."""
    text = "".join(w.text for w in words)
    if _letters(text) < 2 or _letters(text) < 0.5 * len(text.replace(" ", "")):
        return False
    if any(w.box[2] - w.box[0] > 0.35 for w in words):
        return False   # one "word" across the page: a ruled line read as text
    score = _mean_confidence(words)
    return score is None or score >= NOISE_CONFIDENCE


def page_geometry(page: OCRPage) -> PageGeometry | None:
    """Number, statement and answer columns of a table page, or None."""
    if not page.has_geometry:
        return None
    lines = [line for line in page.lines if line.words]
    if len(lines) < MIN_ROWS:
        return None
    starts = []
    for line in lines:
        words = _words(line)
        if len(words) >= 2 and _NUMBER.fullmatch(words[0].text.strip()) \
                and _letters(words[1].text) >= 2:
            starts.append((line, words))
    if len(starts) < MIN_ROWS:
        return None
    heights = sorted(line.box[3] - line.box[1] for line, _ in starts)
    line_height = heights[len(heights) // 2]
    unit_x = line_height * page.pixel_height / max(page.pixel_width, 1)
    points = [(_cy(line.box), words[1].box[0]) for line, words in starts]
    a, b = _fit(points)
    inliers = [s for s, (y, x) in zip(starts, points) if abs(x - (a + b * y)) <= 0.012]
    if len(inliers) < max(MIN_ROWS, 0.6 * len(starts)):
        return None
    a, b = _fit((_cy(line.box), words[1].box[0]) for line, words in inliers)
    gaps = [words[1].box[0] - words[0].box[2] for _, words in inliers]
    spaces = [w2.box[0] - w1.box[2] for _, words in inliers
              for w1, w2 in zip(words[1:], words[2:]) if _letters(w1.text) and _letters(w2.text)]
    word_gap = median(spaces) if spaces else 0.0
    if median(gaps) < max(1.8 * word_gap, 0.010):
        return None   # "12. Text": a number inline with its text, not a column
    reach = max((a + b * _cy(line.box)) - words[0].box[0] for line, words in inliers)
    answer_left = _answer_column(inliers)
    return PageGeometry(page.page_number, a, b, reach, answer_left, line_height, unit_x,
                        len(inliers))


def _answer_column(rows) -> float | None:
    """Left edge of the code-like tokens aligned at the end of most rows."""
    lefts = []
    for _line, words in rows:
        tail = []
        for word in reversed(words[2:]):
            text = word.text.strip()
            if _codeish(text) or (len(text) <= 3 and _letters(text) <= 2):
                tail.append(word)
            else:
                break
        tail.reverse()
        if tail and any(ch.isdigit() for w in tail for ch in w.text):
            lefts.append(tail[0].box[0])
    need = max(MIN_ROWS, len(rows) // 2)
    if len(lefts) < need:
        return None
    middle = median(lefts)
    cluster = [x for x in lefts if abs(x - middle) <= 0.02]
    return min(cluster) - 0.004 if len(cluster) >= need else None


def _zones(line: OCRLine, geo: PageGeometry):
    """(number-column words, statement words, answer words) of one line."""
    left = geo.statement_x(_cy(line.box))
    cut = left - 0.3 * geo.unit_x
    reach = left - geo.number_reach - 1.2 * geo.unit_x
    number, statement, answer = [], [], []
    for word in _words(line):
        x = _cx(word)
        if geo.answer_left is not None and x >= geo.answer_left:
            answer.append(word)
        elif x >= cut:
            if word.box[2] - word.box[0] <= 0.35:
                statement.append(word)
        elif x >= reach:
            number.append(word)
    return number, statement, answer


def _aligned(words, geo: PageGeometry, line: OCRLine) -> bool:
    if not words:
        return False
    tolerance = max(0.6 * geo.unit_x, 0.01)
    return abs(words[0].box[0] - geo.statement_x(_cy(line.box))) <= tolerance


def _legends(lines, page: int) -> list[Legend]:
    """Answer legends among plain lines: one per line or all on one line."""
    found, run, texts, top = [], [], [], None
    for line in lines:
        pair = line_code_label(line.text)
        if pair is not None and (not run or int(pair[0]) == int(run[-1][0]) + 1):
            if not run:
                top = line.box[1]
            run.append(pair)
            texts.append(line.text)
            continue
        if legend_run(run):
            found.append(Legend(page, legend_run(run), " · ".join(texts), top))
        run, texts, top = ([pair], [line.text], line.box[1]) if pair is not None else ([], [], None)
        if pair is None:
            pairs = code_label_pairs(line.text)
            if pairs:
                found.append(Legend(page, pairs, line.text, line.box[1]))
    if legend_run(run):
        found.append(Legend(page, legend_run(run), " · ".join(texts), top))
    return found


def reconstruct_tables(pages) -> TableReconstruction | None:
    """Rebuild numbered table rows on OCR pages (in page order), or None."""
    pages = sorted((p for p in pages if p.has_geometry), key=lambda p: p.page_number)
    geometries = {p.page_number: g for p in pages if (g := page_geometry(p)) is not None}
    if not geometries:
        return None
    state = {"expected": 1, "group": 0, "current": None, "started": False}
    plans = {}            # page → list of (line, kind, row or None)
    rows: list[dict] = []
    for page in pages:
        geo = geometries.get(page.page_number)
        if geo is None:
            continue
        plan = []
        for line in sorted(page.lines, key=lambda l: (l.box[1], l.box[0])):
            if line.words:
                kind = _classify(line, page.page_number, geo, state, rows)
                plan.append((line, kind, state["current"] if kind == "row" else None))
        plans[page.page_number] = plan
    if len(rows) < MIN_ROWS:
        return None
    return _assemble(pages, plans, rows, geometries)


def _classify(line: OCRLine, page: int, geo: PageGeometry, state: dict, rows: list) -> str:
    """'row', 'continuation', 'noise' or 'text'; a row is appended to ``rows``."""
    number_words, statement, answer = _zones(line, geo)
    number_text = "".join(w.text for w in number_words)
    aligned = _aligned(statement, geo, line) and _texty(statement)
    has_answers = any(ch.isdigit() for w in answer for ch in w.text)
    started, expected, current = state["started"], state["expected"], state["current"]

    def start(number: int, source: str, new_group: bool) -> str:
        if new_group:
            state["group"] += 1
        state.update(started=True, expected=number + 1, current={
            "page": page, "number": number, "source": source, "number_text": number_text,
            "lines": [line], "number_words": number_words, "statement": list(statement),
            "answers": list(answer), "group": f"ocr-table-{state['group']}",
            "bottom": line.box[3]})
        rows.append(state["current"])
        return "row"

    if aligned and number_text:
        read = read_number(number_text, expected if started else 1)
        if read is not None:
            value, source = read
            if not started:
                return start(value, source, True)
            if value == 1 and expected > 1 and has_answers:
                return start(1, source, True)     # numbering restarts: another table
            if expected <= value <= expected + MAX_JUMP:
                return start(value, source, False)
    if (started and current is not None and geo.answer_left is not None and aligned
            and has_answers and current["answers"]):
        # A visible row (statement and answer digits) whose number cannot be
        # read as the next one gets the expected number, flagged for checking.
        return start(expected, "inferred", False)
    if (current is not None and current["page"] == page and aligned
            and not any(ch.isdigit() for ch in number_text)
            and (not has_answers or not current["answers"])
            and line.box[1] > current["lines"][0].box[1]
            and line.box[1] - current["bottom"] <= 1.2 * geo.line_height):
        current["lines"].append(line)
        current["statement"].extend(statement)
        current["answers"].extend(answer)
        current["bottom"] = line.box[3]
        return "continuation"
    texty = _texty([w for w in line.words if w.box[2] - w.box[0] <= 0.35])
    return "text" if texty else "noise"


def _assemble(pages, plans, rows, geometries) -> TableReconstruction:
    """Page text with one StructuredItemLine per row, plus evidence."""
    legends_by_group: dict[str, list[Legend]] = {}
    titles: dict[str, str] = {}
    first_row_top: dict[tuple[int, str], float] = {}
    for row in rows:
        first_row_top.setdefault((row["page"], row["group"]), row["lines"][0].box[1])
    all_legends = []
    for page in pages:
        plan = plans.get(page.page_number)
        if plan is None:
            continue
        text_lines = [line for line, kind, _ in plan if kind == "text"]
        page_legends = _legends(text_lines, page.page_number)
        all_legends.extend(page_legends)
        groups = [g for (p, g) in first_row_top if p == page.page_number]
        for group in groups:
            top = first_row_top[(page.page_number, group)]
            above = [legend for legend in page_legends if legend.top < top]
            if group not in titles and not above:
                above = page_legends  # a legend printed under the table's first page
            legends_by_group.setdefault(group, []).extend(above)
            if group not in titles:
                legend_text = {t for legend in page_legends for t in legend.text.split(" · ")}
                heading = [line.text for line in text_lines if line.box[3] <= top
                           and line.text not in legend_text and is_title_line(line.text)]
                titles[group] = heading[-1] if heading else ""
    scales = {group: _legend_scale(legends, rows, group)
              for group, legends in legends_by_group.items() if legends}
    built = [_table_row(row) for row in rows]
    notes = _group_notes(built, scales, legends_by_group)
    by_identity = {id(row): item for row, item in zip(rows, built)}
    lines, dropped = {}, 0
    for page in pages:
        plan = plans.get(page.page_number)
        if plan is None:
            continue
        rows_on_page = [r for r in rows if r["page"] == page.page_number]
        # Noise is dropped only inside the table (and the rule under its last row).
        height = geometries[page.page_number].line_height
        band = ((min(r["lines"][0].box[1] for r in rows_on_page) - 0.5 * height,
                 max(r["bottom"] for r in rows_on_page) + 1.5 * height)
                if rows_on_page else None)
        out = []
        for line, kind, payload in plan:
            if kind == "row":
                out.append(_structured(by_identity[id(payload)], scales, titles, notes))
            elif kind == "continuation":
                continue
            elif kind == "noise" and band is not None and band[0] <= _cy(line.box) <= band[1]:
                dropped += 1
            else:
                out.append(line.text)
        lines[page.page_number] = out
    return TableReconstruction(lines, tuple(built), tuple(all_legends),
                               tuple(geometries[p] for p in sorted(geometries)), dropped)


def _table_row(row: dict) -> TableRow:
    statement = row["statement"]
    rank = {line.id: k for k, line in enumerate(row["lines"])}
    ordered = sorted(statement, key=lambda w: (rank.get(w.line_id, 0), w.box[0]))
    prompt = " ".join(" ".join(w.text for w in ordered).split())
    words = [*row["number_words"], *ordered]
    box = union_box(w.box for w in words) if words else row["lines"][0].box
    used = [line.id for line in row["lines"] if any(w.line_id == line.id for w in words)]
    return TableRow(
        row["page"], row["number"], row["number_text"], row["source"], prompt,
        row["lines"][0].text, box, tuple(used or [row["lines"][0].id]),
        len({w.line_id for w in ordered}), tuple(w.text for w in row["answers"]), row["group"],
    )


def _legend_scale(legends, rows, group) -> DocumentedScale:
    first = legends[0]
    codes = tuple(code for code, _ in first.pairs)
    labels = tuple(label for _, label in first.pairs)
    issues = ["The answer legend was read by OCR; compare every label with the source page."]
    for other in legends[1:]:
        if not _same_labels(labels, tuple(label for _, label in other.pairs)):
            issues.append(f"The legend on page {other.page} reads differently ("
                          + " / ".join(label for _, label in other.pairs)
                          + "); check which one the form uses.")
    printed = [tuple(normalize_tokens(tuple(w.text for w in r["answers"])))
               for r in rows if r["group"] == group]
    clean = [tokens for tokens in printed
             if tokens and all(re.fullmatch(r"\d{1,2}", t) for t in tokens)]
    if len(clean) >= MIN_ROWS:
        common = max(set(clean), key=clean.count)
        if common != codes:
            issues.append("Most rows print the answer codes " + " ".join(common)
                          + " but the legend lists " + " / ".join(codes) + "; check the source.")
    return DocumentedScale(labels, codes, labels, "legend", first.page,
                           f"{first.text} ({_legend_pages(legends)})"[:160], tuple(issues))


def _same_labels(first, second) -> bool:
    """The same legend read twice: equal labels, allowing OCR spelling variants."""
    def key(label):
        return re.sub(r"\s+", "", label).casefold()

    return len(first) == len(second) and all(
        key(a) == key(b) or SequenceMatcher(None, key(a), key(b), autojunk=False).ratio() >= 0.8
        for a, b in zip(first, second))


def _legend_pages(legends) -> str:
    pages = sorted({legend.page for legend in legends})
    return f"page {pages[0]}" + (f", repeated on page(s) {', '.join(map(str, pages[1:]))}"
                                 if len(pages) > 1 else "")


def _group_notes(rows, scales, legends) -> dict[str, tuple[str, ...]]:
    notes = {}
    for group in dict.fromkeys(row.group for row in rows):
        mine = [row for row in rows if row.group == group]
        pages = ", ".join(str(p) for p in sorted({row.page for row in mine}))
        joined = sum(1 for row in mine if row.prompt_lines > 1)
        checked = [row.number for row in mine if row.number_source != "printed"]
        answers = sum(1 for row in mine if row.answers)
        text = [f"Table rows were rebuilt from OCR word positions on page(s) {pages}: "
                f"{len(mine)} rows from the item-number column and the statement column"
                + (f"; answer digits printed in {answers} rows were left out of the statements "
                   "by their position" if answers else "") + "."]
        if joined:
            text.append(f"{joined} wrapped statement(s) were joined from their lines.")
        if checked:
            text.append("Item number(s) " + ", ".join(map(str, checked[:15]))
                        + " were read through scan artifacts or inferred from the order; "
                        "each is flagged “check this number”.")
        if group in scales:
            text.append("The answer legend " + " / ".join(scales[group].labels) + " read by OCR ("
                        + _legend_pages(legends[group]) + ") is proposed as this table's shared "
                        "response scale — not confirmed; the legend lines are not items.")
        notes[group] = tuple(text)
    return notes


def _structured(row: TableRow, scales, titles, notes) -> StructuredItemLine:
    flags, remarks = [], []
    if row.number_source == "normalised":
        flags.append(f"check this number: OCR read “{row.number_text}”")
        remarks.append(f"OCR read the item number as “{row.number_text}”; it was taken as "
                       f"{row.number} because it continues the numbered sequence. Check this "
                       "number on the source page.")
    elif row.number_source == "inferred":
        read = row.number_text.strip()
        flags += ["item number inferred from order",
                  f"check this number: OCR read “{read}”" if read
                  else "check this number: no readable number"]
        remarks.append((f"OCR read “{read}” in the number column, which does not continue "
                        "the numbered sequence" if read else
                        "No readable item number in the number column")
                       + f"; {row.number} was inferred from the row order. Check this number "
                       "on the source page.")
    if row.prompt_lines > 1:
        flags.append(f"prompt joined from {row.prompt_lines} lines")
        remarks.append(f"Prompt joined from {row.prompt_lines} wrapped source lines.")
    tokens = normalize_tokens(row.answers)
    clean = tokens if tokens and all(re.fullmatch(r"\d{1,2}", t) for t in tokens) else ()
    return StructuredItemLine(
        f"{row.number}. {row.prompt}", number=row.number, prompt=row.prompt,
        excerpt=row.excerpt, group=row.group, title=titles.get(row.group, ""),
        number_source=row.number_source, flags=flags, notes=remarks,
        scale=scales.get(row.group), row_tokens=clean, group_notes=notes.get(row.group, ()),
    )


def attach_row_regions(evidence: SpatialEvidence | None, review, rows) -> SpatialEvidence | None:
    """Give every rebuilt row its own source region (page + box) for review."""
    if evidence is None or not rows:
        return evidence
    lookup = {(row.page, row.number, " ".join(row.prompt.split())[:300]): row for row in rows}
    old = dict(evidence.links)
    counter = evidence.next_region
    links = []
    for i, instrument in enumerate(review.instruments):
        for j, candidate in enumerate(instrument.questions):
            ref = question_ref(i, j)
            prompt = " ".join(candidate.question.get("prompt", "").split())[:300]
            row = lookup.get((candidate.page, candidate.number, prompt))
            if row is None:
                links.append((ref, old.get(ref, ())))
                continue
            links.append((ref, (Region(f"r{counter}", row.page, row.box, row.line_ids,
                                       "detected"),)))
            counter += 1
    frozen = tuple(links)
    return replace(evidence, links=frozen, original_links=frozen, next_region=counter)


__all__ = [
    "Legend", "PageGeometry", "TableReconstruction", "TableRow", "attach_row_regions",
    "page_geometry", "read_number", "reconstruct_tables",
]
