"""Rows of a scanned questionnaire table, rebuilt from OCR word positions.

A scanned table prints the item number in its own column, the statement in
a second column (wrapped onto further lines) and the answer codes in a
column on the right. Read as plain text, a tick or speck before a number
(``"17.``) or answer digits glued together (``1283845``) end a numbered
sequence. This module works from Tesseract word boxes instead
(:class:`ocr_layout.OCRPage`, normalised 0..1 page coordinates):

1. **Visual lines.** A number or a run of answer digits that OCR put on a
   line of its own, at the height of a statement line, joins that line.
2. **Columns.** Lines that start with a clean number (``12.``) followed by a
   word give the number column; the left edges of those words give the
   statement column (fitted against the page height, so rotation does not
   matter). A number followed by its text at an ordinary word gap
   (``12. Text``) is NOT a column: such pages keep the line parser.
3. **Answer tokens** are removed from the END of a line only: a trailing
   run of tokens in the answer area made of digits and the glyphs OCR
   produces for them (``12375``, ``1—2``, ``[1``, ``|``, ``5”``, ``—``, one
   letter glued to digits such as ``a2345``, a single digit look-alike
   letter such as ``L`` or ``Z``, any other lone letter scored below 60).
   A token with two or more letters is never removed (OCR junk such as
   ``LZ`` for ``1 2`` therefore stays, flagged by its low OCR score).
4. **Rows**, in two passes with look-ahead. A line whose number-column text
   reads as the next number starts a row. A sequence starts only where the
   following rows confirm it (a bare ``5`` opening an instruction line, or
   legend lines ``1- …`` printed in another column, never start or advance
   it), and a number style differing from the page's (``5`` among ``12.``)
   cannot start one. OCR noise is normalised in the number column only:
   quotes, ticks and dashes are stripped; look-alike glyphs (A → 4,
   I l | ī í ì i ! [ ] → 1, S → 5, Z → 2, B → 8, G → 6, T → 7, O o → 0) are
   mapped only when the result is the expected next number, and a reading
   the next row contradicts is refused. A row whose number is unreadable
   or partial (``_4.`` for 49) gets the expected number when the next row
   reads the number after it, or when its statement and answer digits are
   in place. Every normalised or inferred number is flagged "check this
   number" — never silently accepted. Rows without answer digits count as
   long as their number fits the sequence.
5. **Continuations.** A line without a number whose text starts in the
   statement column, directly under a row, is appended to that row.
6. **Legend.** Lines such as ``1- …`` to ``5- …`` (also when repeated at
   the top of the next page) are the answer legend: evidence for ONE shared
   response scale, never items. Lines inside the table that look like noise
   from table rules or specks (no confidently read word) are dropped.

Every row keeps its page and box (number + statement words) as the source
region shown in review. OCR confidence stays Tesseract's per-word character
score; nothing here is a measure of item quality, reliability or validity.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from statistics import median
import re

from ocr_layout import (
    BBox, OCRLine, OCRPage, OCRWord, Region, SpatialEvidence, question_ref, union_box,
)
from response_scales import code_label_pairs, legend_run, line_code_label, normalize_tokens
from scientific_survey_import import (
    DocumentedScale, StructuredItemLine, is_reference_line, is_title_line,
)

MIN_ROWS = 3
MAX_JUMP = 3             # a printed number may skip at most this many missing rows
LOOKAHEAD = 3            # numbered lines read ahead to confirm or contradict a number
TEXT_CONFIDENCE = 60.0   # a word scored below this is no evidence of real text
REAL_CONFIDENCE = 40.0   # a word scored below this cannot anchor the statement column
SPECK_CONFIDENCE = 60.0  # a lone letter scored below this in the answer area is a speck
_NUMBER = re.compile(r"^(\d{1,3})([.)]?)$")
# Characters scan artifacts become around a number; they never stand for a digit.
_ARTIFACTS = "\"'`´‘’‚‛“”„‟«»‹›,:;_~^*°·•-–—/\\"
# Glyphs OCR reads instead of a digit; mapped only to reach the expected number.
_LOOKALIKES = str.maketrans({
    "I": "1", "l": "1", "|": "1", "ī": "1", "Ī": "1", "í": "1", "ì": "1", "i": "1",
    "!": "1", "]": "1", "[": "1", "O": "0", "o": "0", "A": "4", "S": "5", "Z": "2",
    "B": "8", "G": "6", "T": "7",
})
_DIGIT_GLYPHS = "0123456789Il|īĪíìi!][OoASZBGT"
# A single letter OCR reads instead of an answer digit (L for 1 as well).
_ANSWER_LOOKALIKES = set("IlīĪíìiOoASZBGTL")
_NUMBER_SHAPE = re.compile(
    rf"^[{re.escape(_ARTIFACTS + '.')}]{{0,3}}[{re.escape(_DIGIT_GLYPHS)}]{{1,3}}"
    rf"[.),]?[{re.escape(_ARTIFACTS)}]{{0,2}}$")


@dataclass(frozen=True)
class PageGeometry:
    """Columns of one scanned table page (x as page fractions)."""
    page: int
    statement_a: float          # statement column left edge: x = a + b * y
    statement_b: float
    number_reach: float         # how far left of the statement column numbers start
    answer_floor: float | None  # answer tokens are never stripped left of this
    line_height: float          # median text line height (y fraction)
    unit_x: float               # the line height as an x fraction
    rows: int = 0               # lines that start with a clean number in the column
    number_style: str = "dot"   # "dot" ("12.") or "bare" ("12") on this page

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
    answers: tuple[str, ...]  # tokens read in the answer area (not in the prompt)
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


@dataclass
class _Parts:
    """One visual line split into number column, statement and answer tokens."""
    page: int
    line: OCRLine
    number: list
    statement: list
    answers: list
    aligned: bool
    texty: bool
    real: bool

    @property
    def number_text(self) -> str:
        return "".join(w.text for w in self.number)

    @property
    def has_answers(self) -> bool:
        return any(ch.isdigit() for w in self.answers for ch in w.text)


# ---------------------------------------------------------------- tokens

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


def _scored(word: OCRWord, threshold: float) -> bool:
    return word.confidence is None or word.confidence >= threshold


def _real(word: OCRWord) -> bool:
    """A word OCR read with some confidence (evidence that a line holds text)."""
    return len(re.findall(r"[^\W_]", word.text)) >= 2 and _scored(word, REAL_CONFIDENCE)


def _speck(word: OCRWord) -> bool:
    """A tiny low-scored mark (``,`` ``'`` ``a``), never a word or a digit."""
    text = word.text.strip()
    return len(text) <= 2 and not any(ch.isdigit() for ch in text) \
        and not _scored(word, REAL_CONFIDENCE)


def _texty(words) -> bool:
    """Real text: at least one confidently read word (two, or one of 4+ letters)."""
    confident = [w for w in words if _letters(w.text) >= 2 and w.box[2] - w.box[0] <= 0.35
                 and _scored(w, TEXT_CONFIDENCE)]
    return len(confident) >= 2 or any(_letters(w.text) >= 4 for w in confident)


def answer_like(word: OCRWord) -> bool:
    """A token OCR makes of printed answer codes (shape only, no position).

    Digits with the glyphs OCR produces for them (``12375``, ``1—2``, ``[1``,
    ``|``, ``5”``, ``—``, ``-``), one letter glued to digits (``a2345``), a
    single digit look-alike letter (``L``, ``Z``, ``S`` …), or any other lone
    letter scored below 60 (a speck). Never a token with two letters.
    """
    text = word.text.strip()
    letters = [ch for ch in text if ch.isalpha()]
    if not text or len(letters) >= 2:
        return False
    if not letters or any(ch.isdigit() for ch in text) or letters[0] in _ANSWER_LOOKALIKES:
        return True
    return len(text) == 1 and word.confidence is not None and word.confidence < SPECK_CONFIDENCE


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


def _read_words(words, expected: int | None):
    """``(number, source, text read)`` from number-column words, or None.

    The whole column is read first; a speck left of the number does not
    hide it (the last word, then the last two words, are tried too).
    """
    texts = ["".join(w.text for w in words)]
    if len(words) > 1:
        texts += [words[-1].text, "".join(w.text for w in words[-2:])]
    for text in texts:
        found = read_number(text, expected)
        if found is not None:
            return found[0], found[1], text
    return None


def _strict(parts: _Parts) -> int | None:
    found = _read_words(parts.number, None)
    return found[0] if found is not None else None


def _partial(text: str, expected: int) -> bool:
    """Nothing readable, or digits that are part of the expected number (``_4.`` → 49)."""
    digits = re.sub(r"\D", "", text.translate(_LOOKALIKES))
    return not digits or digits in str(expected)


# ----------------------------------------------------------- visual lines

def _fragment(line: OCRLine) -> str | None:
    """"number" or "answers" for a piece OCR split off a table row, else None."""
    words = _words(line)
    text = "".join(w.text for w in words)
    if len(words) <= 2 and line.box[2] - line.box[0] <= 0.08 and _NUMBER_SHAPE.fullmatch(text):
        return "number"
    if all(answer_like(w) for w in words) and any(ch.isdigit() for ch in text):
        return "answers"
    return None


def _visual_lines(page: OCRPage) -> list[OCRLine]:
    """Tesseract lines, with split-off numbers and answer runs joined to their row."""
    lines = [line for line in page.lines if line.words]
    if not lines:
        return []
    heights = sorted(line.box[3] - line.box[1] for line in lines)
    height = heights[len(heights) // 2]
    kinds = {line.id: _fragment(line) for line in lines}
    hosts = [line for line in lines if kinds[line.id] is None]
    joined = {line.id: list(line.words) for line in hosts}
    alone = []
    for piece in (line for line in lines if kinds[line.id] is not None):
        best = None
        for host in hosts:
            dy = abs(_cy(host.box) - _cy(piece.box))
            side = (piece.box[2] <= host.box[0] if kinds[piece.id] == "number"
                    else piece.box[0] >= host.box[2])
            if side and dy <= 0.45 * height and (best is None or dy < best[0]):
                best = (dy, host)
        if best is None:
            alone.append(piece)
        else:
            joined[best[1].id].extend(piece.words)
    out = [OCRLine(host.id, host.block_id, tuple(sorted(joined[host.id], key=_x0)),
                   union_box(w.box for w in joined[host.id])) for host in hosts]
    return sorted(out + alone, key=lambda line: (line.box[1], line.box[0]))


# --------------------------------------------------------------- columns

def page_geometry(page: OCRPage) -> PageGeometry | None:
    """Number, statement and answer columns of a table page, or None."""
    if not page.has_geometry:
        return None
    return _geometry(page, _visual_lines(page))


def _geometry(page: OCRPage, lines) -> PageGeometry | None:
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
    dotted = sum(1 for _, words in inliers if _NUMBER.fullmatch(words[0].text.strip()).group(2))
    return PageGeometry(page.page_number, a, b, reach, _answer_floor(inliers), line_height,
                        unit_x, len(inliers), "dot" if dotted >= 0.6 * len(inliers) else "bare")


def _answer_floor(rows) -> float | None:
    """Left of this x, answer tokens are never stripped (None: no answer column).

    A row's answer run is its trailing run of answer-like tokens that ends
    near the right edge shared by most rows. The floor lies a little left of
    the earliest such runs, because skew and digits OCR lost move them.
    """
    right = median(words[-1].box[2] for _, words in rows)
    lefts = []
    for _line, words in rows:
        k = len(words)
        while k > 2 and answer_like(words[k - 1]):
            k -= 1
        run = words[k:]
        if run and any(ch.isdigit() for w in run for ch in w.text) \
                and run[-1].box[2] >= right - 0.06:
            lefts.append(run[0].box[0])
    if len(lefts) < max(MIN_ROWS, len(rows) // 3):
        return None
    lefts.sort()
    return lefts[len(lefts) // 10] - 0.03


def _split_answers(words, geo: PageGeometry):
    """(words, answer tokens): a trailing run of answer-like tokens right of
    the floor comes off the END of the line; nothing else is removed."""
    if geo.answer_floor is None:
        return list(words), []
    k = len(words)
    while k > 0 and words[k - 1].box[0] >= geo.answer_floor and answer_like(words[k - 1]):
        k -= 1
    return list(words[:k]), list(words[k:])


def _parts(line: OCRLine, page: int, geo: PageGeometry) -> _Parts:
    rest, answers = _split_answers(_words(line), geo)
    left = geo.statement_x(_cy(line.box))
    cut = left - 0.3 * geo.unit_x
    reach = left - geo.number_reach - 1.2 * geo.unit_x
    number, statement = [], []
    for word in rest:
        x = _cx(word)
        if x >= cut:
            if word.box[2] - word.box[0] <= 0.35:
                statement.append(word)
        elif x >= reach:
            number.append(word)
    while statement and _speck(statement[0]):
        statement.pop(0)   # a speck before the first word
    first = next((w for w in statement if len(re.findall(r"[^\W_]", w.text)) >= 2), None)
    tolerance = max(0.6 * geo.unit_x, 0.01)
    aligned = first is not None and abs(first.box[0] - left) <= tolerance
    return _Parts(page, line, number, statement, answers, aligned,
                  _texty(statement), any(_real(w) for w in statement))


# ---------------------------------------------------------------- legends

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


# ------------------------------------------------------------------- rows

def reconstruct_tables(pages) -> TableReconstruction | None:
    """Rebuild numbered table rows on OCR pages (in page order), or None."""
    pages = sorted((p for p in pages if p.has_geometry), key=lambda p: p.page_number)
    entries, geometries = [], {}
    for page in pages:
        lines = _visual_lines(page)
        geo = _geometry(page, lines)
        if geo is None:
            continue
        geometries[page.page_number] = geo
        entries += [_parts(line, page.page_number, geo) for line in lines]
    if not geometries:
        return None
    kinds, rows = _Sequence(entries, geometries).run()
    if len(rows) < MIN_ROWS:
        return None
    return _assemble(pages, entries, kinds, rows, geometries)


class _Sequence:
    """Second pass: the numbered sequence, with look-ahead over later lines."""

    def __init__(self, entries, geometries):
        self.entries, self.geometries = entries, geometries
        self.numbered = [i for i, p in enumerate(entries) if p.aligned and p.real and p.number]
        self.expected, self.group, self.current, self.started = 1, 0, None, False
        self.rows: list[dict] = []

    def upcoming(self, i: int) -> list[_Parts]:
        k = bisect_right(self.numbered, i)
        return [self.entries[j] for j in self.numbered[k:k + LOOKAHEAD]]

    def confirmed(self, i: int, value: int) -> bool:
        """A following numbered line reads value + 1 (or value + 2)."""
        for parts in self.upcoming(i):
            found = _read_words(parts.number, value + 1)
            if found is not None and found[0] in (value + 1, value + 2):
                return True
        return False

    def contradicted(self, i: int, value: int) -> bool:
        """The next numbered line prints this number, or an earlier one."""
        ahead = self.upcoming(i)
        strict = _strict(ahead[0]) if ahead else None
        return strict is not None and strict <= value

    def run(self):
        kinds = [self.classify(i, parts) for i, parts in enumerate(self.entries)]
        return kinds, self.rows

    def start(self, parts: _Parts, number: int, source: str, text: str, new_group: bool) -> str:
        if new_group:
            self.group += 1
        self.started, self.expected = True, number + 1
        self.current = {
            "page": parts.page, "number": number, "source": source, "number_text": text,
            "lines": [parts.line], "number_words": list(parts.number),
            "statement": list(parts.statement), "answers": list(parts.answers),
            "group": f"ocr-table-{self.group}", "bottom": parts.line.box[3],
        }
        self.rows.append(self.current)
        return "row"

    def classify(self, i: int, parts: _Parts) -> str:
        geo = self.geometries[parts.page]
        expected, current = self.expected, self.current
        statement_text = " ".join(w.text for w in parts.statement)
        row_like = parts.aligned and parts.real and not is_reference_line(statement_text)
        if row_like and parts.number:
            found = _read_words(parts.number, expected if self.started else 1)
            if found is not None:
                value, source, text = found
                style = (geo.number_style != "dot" or source != "printed"
                         or bool(_NUMBER.fullmatch(text.strip()).group(2)))
                if not self.started:
                    if style and self.confirmed(i, value):
                        return self.start(parts, value, source, text, True)
                elif value == 1 and expected > 1:
                    if style and self.confirmed(i, 1) and (
                            parts.has_answers or geo.answer_floor is None):
                        return self.start(parts, 1, source, text, True)   # another table
                elif value == expected and (source == "printed"
                                            or not self.contradicted(i, value)):
                    return self.start(parts, value, source, text, False)
                elif expected < value <= expected + MAX_JUMP \
                        and not self.contradicted(i, value - 1):
                    return self.start(parts, value, source, text, False)
            if self.started and parts.texty and _partial(parts.number_text, expected) \
                    and self.confirmed(i, expected) and not self.contradicted(i, expected):
                # Between rows n - 1 and n + 1: an unreadable or partial number.
                return self.start(parts, expected, "inferred", parts.number_text, False)
        if (self.started and current is not None and row_like and parts.texty
                and geo.answer_floor is not None and parts.has_answers
                and _has_answers(current) and not self.contradicted(i, expected)):
            # A visible row (statement and answer digits) whose number cannot be
            # read as the next one gets the expected number, flagged for checking.
            return self.start(parts, expected, "inferred", parts.number_text, False)
        if (current is not None and current["page"] == parts.page and parts.aligned
                and parts.texty and not any(ch.isdigit() for ch in parts.number_text)
                and (not parts.has_answers or not _has_answers(current))
                and parts.line.box[1] > current["lines"][0].box[1]
                and parts.line.box[1] - current["bottom"] <= 1.2 * geo.line_height):
            current["lines"].append(parts.line)
            current["number_words"].extend(parts.number)
            current["statement"].extend(parts.statement)
            current["answers"].extend(parts.answers)
            current["bottom"] = parts.line.box[3]
            return "continuation"
        words = [*parts.number, *parts.statement]
        return "text" if _texty(words) else "noise"


def _has_answers(row: dict) -> bool:
    return any(ch.isdigit() for w in row["answers"] for ch in w.text)


# ------------------------------------------------------------- assembling

def _assemble(pages, entries, kinds, rows, geometries) -> TableReconstruction:
    """Page text with one StructuredItemLine per row, plus evidence."""
    legends_by_group: dict[str, list[Legend]] = {}
    titles: dict[str, str] = {}
    first_row_top: dict[tuple[int, str], float] = {}
    for row in rows:
        first_row_top.setdefault((row["page"], row["group"]), row["lines"][0].box[1])
    plans: dict[int, list] = {}
    row_at = {id(row["lines"][0]): row for row in rows}
    for parts, kind in zip(entries, kinds):
        plans.setdefault(parts.page, []).append((parts.line, kind))
    all_legends = []
    for page in pages:
        plan = plans.get(page.page_number)
        if plan is None:
            continue
        text_lines = [line for line, kind in plan if kind == "text"]
        page_legends = _legends(text_lines, page.page_number)
        all_legends.extend(page_legends)
        for group in [g for (p, g) in first_row_top if p == page.page_number]:
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
    built = {id(row): _table_row(row) for row in rows}
    notes = _group_notes(list(built.values()), scales, legends_by_group)
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
        for line, kind in plan:
            if kind == "row":
                row = row_at[id(line)]
                out.append(_structured(built[id(row)], scales, titles, notes))
            elif kind == "continuation":
                continue
            elif kind == "noise" and band is not None and band[0] <= _cy(line.box) <= band[1]:
                dropped += 1
            else:
                out.append(line.text)
        lines[page.page_number] = out
    return TableReconstruction(lines, tuple(built[id(row)] for row in rows), tuple(all_legends),
                               tuple(geometries[p] for p in sorted(geometries)), dropped)


def _table_row(row: dict) -> TableRow:
    # Visual line first (a joined fragment keeps its own Tesseract line id),
    # then left to right.
    rank = {word.id: k for k, line in enumerate(row["lines"]) for word in line.words}
    ordered = sorted(row["statement"], key=lambda w: (rank.get(w.id, 0), w.box[0]))
    used_ids = {w.id for w in (*row["number_words"], *ordered)}
    lines_used: dict[str, None] = {}
    for line in row["lines"]:
        for word in line.words:
            if word.id in used_ids:
                lines_used[word.line_id] = None
    prompt = " ".join(" ".join(w.text for w in ordered).split())
    words = [*row["number_words"], *ordered]
    box = union_box(w.box for w in words) if words else row["lines"][0].box
    return TableRow(
        row["page"], row["number"], row["number_text"], row["source"], prompt,
        row["lines"][0].text, box, tuple(lines_used) or (row["lines"][0].id,),
        len(row["lines"]), tuple(w.text for w in row["answers"]), row["group"],
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
                + (f"; answer tokens printed in {answers} rows were left out of the statements "
                   "by their position and shape" if answers else "") + "."]
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
    "Legend", "PageGeometry", "TableReconstruction", "TableRow", "answer_like",
    "attach_row_regions", "page_geometry", "read_number", "reconstruct_tables",
]
