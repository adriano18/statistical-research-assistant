"""Conservative repair of letter-spaced PDF text layers.

Designed forms often position every glyph individually (tracking, Type 3
fonts, glyph-by-glyph kerning). Text extractors then produce two opposite
artefacts:

* **spurious spaces inside words** (``sched ule``, ``m arked``): an extractor
  inserted a space at a positioning gap that is visually not a word gap;
* **letter-spaced lines** (``s c h e d u l e  f o r``): a space between
  EVERY glyph, the real word gaps then showing as two spaces.

The repair is deliberately conservative:

* two fragments are re-joined only when BOTH neighbouring characters are
  letters on the same baseline and the horizontal gap between their glyph
  advance boxes is small compared with the advance widths of the line and
  with the real word gaps of lines set in a similar font size;
* a gap that looks like a word gap, a column gap or a line break is never
  closed, and geometry alone never splits a word;
* every changed line keeps its original text in a :class:`SpacingRepair`
  record, so the source wording stays auditable.

Without geometry (PDFium unavailable, or text that cannot be aligned with the
glyphs) a text-only rule handles lines in which an extractor separated every
glyph: single spaces join glyphs, runs of two or more spaces separate words.

No network access, OCR or wording changes beyond whitespace happen here.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
import re
import unicodedata

MAX_CHARS = 120_000
#: gap / median advance width below which a PDFium-generated space between
#: two letters is spurious when no real word gap of a similar font is known.
SPLIT_RATIO_NO_REFERENCE = 0.16
#: Fraction of the real word gap below which a generated space is spurious.
SPLIT_FRACTION_OF_WORD_GAP = 0.7
#: Never join across a gap of at least this ratio (≈ a narrow word space).
JOIN_CEILING = 0.45
#: A gap at least this ratio is a word / column gap that is never closed.
WIDE_RATIO = 0.3


@dataclass(frozen=True)
class SpacingRepair:
    """Provenance of one repaired text line (whitespace only)."""
    page: int
    original: str
    repaired: str
    joins: int            # spaces removed inside words
    splits: int           # word gaps restored (e.g. a glued item number)
    method: str           # "geometry" | "text"


@dataclass(frozen=True)
class Glyph:
    char: str
    box: tuple[float, float, float, float]  # loose (left, bottom, right, top), PDF units
    before: str = ""      # whitespace before it on the same line: "" | "generated" | "real"
    index: int = -1       # PDFium character index
    spaces: tuple[int, ...] = ()  # PDFium indices of the whitespace before it


# Boundary classes (between a glyph and its predecessor on the same line):
#   start  – first glyph of a line
#   join   – no whitespace in the text layer
#   tight  – no whitespace and a narrow gap between two letters: whitespace
#            another extractor puts there is spurious (joined by the repair)
#   split  – spurious whitespace inside a word (joined by the repair)
#   space  – whitespace kept, but the gap is narrow (punctuation, tracking)
#   word   – a real word / column gap (never joined)
@dataclass(frozen=True)
class GlyphLine:
    glyphs: tuple[Glyph, ...]
    classes: tuple[str, ...]

    @property
    def text(self) -> str:
        """Repaired text: spurious splits joined, every other gap kept."""
        out = []
        for glyph, kind in zip(self.glyphs, self.classes):
            if kind in ("space", "word"):
                out.append(" ")
            out.append(glyph.char)
        return "".join(out)

    @property
    def raw_text(self) -> str:
        return "".join((" " if g.before else "") + g.char for g in self.glyphs)

    @property
    def joins(self) -> int:
        return sum(1 for kind in self.classes if kind == "split")


def _norm_char(char: str) -> str:
    """One-to-one comparison form (circled digits → digits, quote variants)."""
    folded = unicodedata.normalize("NFKC", char)
    if len(folded) != 1:
        folded = char
    return {"’": "'", "ʼ": "'", "‘": "'", "`": "'", "“": '"', "”": '"'}.get(folded, folded)


# --------------------------------------------------------------- PDFium side

def _charbox(textpage, index: int):
    try:
        return textpage.get_charbox(index, loose=True)
    except TypeError:  # very old pypdfium2: tight boxes only
        return textpage.get_charbox(index)


def pdfium_glyph_lines(textpage, *, max_chars: int = MAX_CHARS) -> list[list[Glyph]]:
    """Glyphs of one PDFium text page grouped into text lines.

    A new line starts at a line break reported by PDFium or when the next
    glyph clearly moves back to the left or to another baseline.
    """
    import pypdfium2.raw as pdfium_c

    generated = getattr(pdfium_c, "FPDFText_IsGenerated", None)
    count = min(textpage.count_chars(), max_chars)
    lines: list[list[Glyph]] = []
    current: list[Glyph] = []
    pending, spaces = "", []
    for index in range(count):
        char = chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, index) or 32)
        if char in "\r\n":
            if current:
                lines.append(current)
            current, pending, spaces = [], "", []
            continue
        if char.isspace() or char == "\x00":
            real = generated is not None and generated(textpage.raw, index) == 0
            pending = "real" if real or pending == "real" else "generated"
            spaces.append(index)
            continue
        left, bottom, right, top = _charbox(textpage, index)
        if right < left or top < bottom:
            continue
        if current:
            last = current[-1].box
            height = max(top - bottom, last[3] - last[1], 0.1)
            moved_back = left < last[0] - 0.5 * height
            other_line = (abs(bottom - last[1]) > 0.6 * height
                          and abs(top - last[3]) > 0.6 * height)
            if moved_back or other_line:
                lines.append(current)
                current, pending, spaces = [], "", []
        current.append(Glyph(char, (left, bottom, right, top),
                             pending if current else "", index, tuple(spaces)))
        pending, spaces = "", []
    if current:
        lines.append(current)
    return lines


def _advance_scale(glyphs) -> float | None:
    letters = [g.box[2] - g.box[0] for g in glyphs if g.char.isalpha() and g.box[2] > g.box[0]]
    if len(letters) >= 3:
        return median(letters)
    widths = [g.box[2] - g.box[0] for g in glyphs if g.box[2] > g.box[0]]
    return median(widths) if len(widths) >= 2 else None


def _same_baseline(a: Glyph, b: Glyph) -> bool:
    height = max(a.box[3] - a.box[1], b.box[3] - b.box[1], 0.1)
    return (abs(a.box[1] - b.box[1]) <= 0.35 * height
            or abs(a.box[3] - b.box[3]) <= 0.35 * height)


def classify_lines(lines: list[list[Glyph]]) -> list[GlyphLine]:
    """Label every glyph boundary (see the class list above :class:`GlyphLine`)."""
    prepared = []
    for glyphs in lines:
        scale = _advance_scale(glyphs)
        ratios: list[float | None] = [None]
        for prev, glyph in zip(glyphs, glyphs[1:]):
            ratios.append((glyph.box[0] - prev.box[2]) / scale if scale else None)
        real = [r for g, r in zip(glyphs, ratios) if g.before == "real" and r is not None]
        prepared.append((glyphs, scale, ratios, real))
    result = []
    for glyphs, scale, ratios, line_real in prepared:
        # Only real space characters of the SAME line are a word-gap
        # reference: other lines may use another font or justification.
        word_gap = median(line_real) if line_real else None
        wide = max(WIDE_RATIO, 0.7 * word_gap) if word_gap is not None else WIDE_RATIO
        limit = (SPLIT_FRACTION_OF_WORD_GAP * word_gap if word_gap is not None
                 else SPLIT_RATIO_NO_REFERENCE)
        limit = min(limit, JOIN_CEILING)
        classes = ["start"]
        for k in range(1, len(glyphs)):
            prev, glyph, ratio = glyphs[k - 1], glyphs[k], ratios[k]
            if glyph.before == "real":
                classes.append("word")
            elif ratio is None or not _same_baseline(prev, glyph):
                classes.append("word" if glyph.before else "join")
            elif ratio >= wide:
                classes.append("word" if glyph.before or ratio >= 1.5 else "join")
            elif not glyph.before:
                # PDFium's own space threshold differs from other extractors':
                # a letter gap it keeps closed may still get a space from pypdf.
                letters = prev.char.isalpha() and glyph.char.isalpha()
                classes.append("tight" if letters and -0.3 <= ratio <= limit else "join")
            elif prev.char.isalpha() and glyph.char.isalpha() and -0.3 <= ratio <= limit:
                classes.append("split")
            else:
                classes.append("space")
        result.append(GlyphLine(tuple(glyphs), tuple(classes)))
    return result


def pdf_page_glyph_lines(pdf, page_number: int) -> list[GlyphLine]:
    """Classified glyph lines of one page of an open ``pypdfium2.PdfDocument``."""
    page = pdf[page_number - 1]
    try:
        textpage = page.get_textpage()
        try:
            return classify_lines(pdfium_glyph_lines(textpage))
        finally:
            textpage.close()
    finally:
        page.close()


def spurious_space_indices(textpage, *, max_chars: int = MAX_CHARS) -> set[int]:
    """PDFium indices of whitespace characters that split a word spuriously.

    The positioned-word builder skips them, so ``sched ule`` becomes one
    word with one box.
    """
    found: set[int] = set()
    for line in classify_lines(pdfium_glyph_lines(textpage, max_chars=max_chars)):
        for glyph, kind in zip(line.glyphs, line.classes):
            if kind == "split":
                found.update(glyph.spaces)
    return found


# ------------------------------------------------------------ text-only rule

def letter_spaced_page(text: str) -> bool:
    """An extractor put a space between most glyphs of this page."""
    words = text.split()
    if len(words) < 40:
        return False
    singles = sum(1 for w in words if len(w) == 1 and w.isalpha())
    return singles / len(words) >= 0.35


def letter_spaced_line(line: str) -> bool:
    words = line.split()
    singles = sum(1 for w in words if len(w) == 1 and w.isalpha())
    if "  " in line.strip() and singles >= 2:
        return True
    return len(words) >= 3 and singles >= 2 and singles / len(words) >= 0.5


def repair_letter_spaced_line(line: str) -> tuple[str, int, int]:
    """Text-only rule: single spaces join glyphs, two or more separate words.

    A digit next to a letter keeps its space (``1 8 D u r i n g`` → ``18 During``).
    Returns ``(text, joins, kept_spaces)``.
    """
    joins = kept = 0
    chunks = []
    for chunk in re.split(r" {2,}|\t", line.strip()):
        parts = [p for p in chunk.split(" ") if p]
        if not parts:
            continue
        out = parts[0]
        for part in parts[1:]:
            if (out[-1].isdigit() and part[0].isalpha()
                    or out[-1].isalpha() and part[0].isdigit()):
                out += " " + part
                kept += 1
            else:
                out += part
                joins += 1
        chunks.append(out)
    return " ".join(chunks), joins, kept


# --------------------------------------------------- extractor text + glyphs

def _segments(line: str) -> tuple[str, list[int]]:
    """Non-space characters of a line and the whitespace run before each."""
    chars, runs = [], []
    run = 0
    for char in line:
        if char.isspace():
            run += 1
            continue
        runs.append(run if chars else 0)
        chars.append(char)
        run = 0
    return "".join(chars), runs


class _PageGeometry:
    """Classified glyphs of a page, searchable by their non-space characters."""

    def __init__(self, glyph_lines: list[GlyphLine]):
        chars, classes = [], []
        for line in glyph_lines:
            for k, (glyph, kind) in enumerate(zip(line.glyphs, line.classes)):
                chars.append(_norm_char(glyph.char))
                classes.append("break" if k == 0 else kind)
        self.text = "".join(chars)
        self.classes = classes
        self.cursor = 0

    def align(self, needle: str) -> int | None:
        if len(needle) < 2:
            return None
        key = "".join(_norm_char(c) for c in needle)
        found = self.text.find(key, self.cursor)
        if found < 0:
            found = self.text.find(key)
        if found < 0:
            return None
        self.cursor = found + len(key)
        return found

    def _find(self, key: str) -> int:
        found = self.text.find(key, self.cursor)
        return found if found >= 0 else self.text.find(key)

    def classes_for(self, needle: str) -> list[str] | None:
        """Geometry class of every character of an extractor line, or None.

        Normally the line is one contiguous run of the page's glyph order.
        When an extractor merged physical lines in a different order (e.g.
        on rotated pages), the line is covered by the longest matching runs
        instead, and the start of every further run counts as a line change.
        """
        start = self.align(needle)
        if start is not None:
            return list(self.classes[start:start + len(needle)])
        if len(needle) < 2:
            return None
        key = "".join(_norm_char(c) for c in needle)
        classes: list[str] = []
        offset = runs = 0
        while offset < len(key):
            low, high, best = 1, len(key) - offset, None
            while low <= high:  # longest prefix of the remainder on this page
                middle = (low + high) // 2
                found = self._find(key[offset:offset + middle])
                if found >= 0:
                    best, low = (middle, found), middle + 1
                else:
                    high = middle - 1
            runs += 1
            if best is None or runs > 40:  # not this page's text: leave it alone
                return None
            length, found = best
            end = found + length
            if (offset + length < len(key) and end < len(self.classes)
                    and self.classes[end] != "break"):
                # The run ran on into another glyph line and stopped inside
                # it: repeated wording ("During the invented week I kept")
                # matched there by coincidence. Keep it to its last complete
                # line, so the remainder is matched where it really continues.
                starts = [i for i in range(1, length) if self.classes[found + i] == "break"]
                if starts:
                    length = starts[-1]
            run = list(self.classes[found:found + length])
            if classes:
                run[0] = "break"
            classes += run
            offset += length
            self.cursor = found + length
        return classes


def repair_page_lines(
    page: int, lines: list[str], geometry: list[GlyphLine] | None,
) -> tuple[list[str], list[SpacingRepair]]:
    """Repair an extractor's lines of one page; returns lines and provenance.

    ``geometry`` (classified PDFium glyph lines) may be ``None``; then only the
    text-only rule for letter-spaced lines applies. Lines that need no change
    are returned exactly as given.
    """
    spaced_page = letter_spaced_page("\n".join(lines))
    reference = _PageGeometry(geometry) if geometry else None
    repaired, repairs = [], []
    for line in lines:
        if not line.strip():
            repaired.append(line)
            continue
        chars, runs = _segments(line)
        classes = reference.classes_for(chars) if reference is not None else None
        if classes is None:
            if spaced_page and letter_spaced_line(line):
                text, joins, kept = repair_letter_spaced_line(line)
                if joins:
                    repairs.append(SpacingRepair(page, line, text, joins, 0, "text"))
                    repaired.append(text)
                    continue
            repaired.append(line)
            continue
        # Some extractor versions merge physically separate lines (wrapped
        # prompt lines, answer cells beside a prompt) without ANY whitespace,
        # e.g. "invented" + "garden" -> "inventedgarden". PDFium's glyph lines
        # show where the baseline really changes; when the extractor glued
        # text across such a change, restore every line change of that line.
        # On a letter-spaced page a single space is only a letter gap, so it
        # counts as "no word gap" there as well.
        breaks = [k for k in range(1, len(chars)) if classes[k] == "break"]
        glued = any(runs[k] == 0 or (spaced_page and runs[k] == 1) for k in breaks)
        cuts = breaks if glued else []
        bounds = [0, *cuts, len(chars)]
        pieces = [_repair_piece(chars[a:b], runs[a:b], classes[a:b], spaced_page)
                  for a, b in zip(bounds, bounds[1:])]
        if cuts:
            for index, (text, joins, splits) in enumerate(pieces):
                repairs.append(SpacingRepair(page, line, text, joins,
                                             splits + (len(cuts) if index == 0 else 0),
                                             "geometry"))
                repaired.append(text)
            continue
        text, joins, splits = pieces[0]
        if joins or splits:
            repairs.append(SpacingRepair(page, line, text, joins, splits, "geometry"))
            repaired.append(text)
        else:
            repaired.append(line)
    return repaired, repairs


def _repair_piece(chars: str, runs: list[int], classes: list[str],
                  spaced_page: bool) -> tuple[str, int, int]:
    """Whitespace of one physical line: (text, spaces removed, gaps restored)."""
    out, joins, splits = [], 0, 0
    for k, char in enumerate(chars):
        if k:
            kind = classes[k]
            gap = runs[k]
            if spaced_page:
                # Real word gaps: two spaces from the extractor, or a wide
                # gap / line change in the glyph geometry.
                if gap >= 2 or kind in ("word", "break"):
                    out.append(" ")
                    splits += int(gap == 0)
                else:
                    joins += int(gap == 1)
            elif gap == 1 and kind in ("split", "tight"):
                joins += 1
            else:
                out.append(" " * gap)
        out.append(char)
    text = "".join(out)
    if spaced_page:
        text = " ".join(text.split())
    return text, joins, splits


def repair_pdf_text(source, pages: list[tuple[int, list[str]]]) -> tuple[
    list[tuple[int, list[str]]], tuple[SpacingRepair, ...]
]:
    """Repair the extracted lines of PDF pages using PDFium glyph geometry.

    ``source`` is a path or bytes; ``pages`` holds ``(page number, lines)``.
    If PDFium cannot read the document, the text-only rule is used for
    letter-spaced pages and nothing else changes.
    """
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(source)
    except Exception:  # missing engine or unreadable file: text-only rule
        pdf = None
    out, repairs = [], []
    try:
        for number, lines in pages:
            geometry = None
            if pdf is not None and 1 <= number <= len(pdf):
                try:
                    geometry = pdf_page_glyph_lines(pdf, number)
                except Exception:
                    geometry = None
            fixed, found = repair_page_lines(number, lines, geometry)
            out.append((number, fixed))
            repairs += found
    finally:
        if pdf is not None:
            pdf.close()
    return out, tuple(repairs)


def repair_summary(repairs) -> str:
    """One-line description for document warnings (no source wording)."""
    repairs = tuple(repairs)
    if not repairs:
        return ""
    pages = sorted({r.page for r in repairs})
    joins = sum(r.joins for r in repairs)
    methods = sorted({r.method for r in repairs})
    return (
        f"Letter-spacing in the PDF text layer was repaired on page(s) "
        f"{', '.join(map(str, pages))}: {len(repairs)} line(s), {joins} split(s) "
        f"inside words joined ({' + '.join(methods)} evidence). Only whitespace was "
        "changed; compare the wording with the source page."
    )


__all__ = [
    "SpacingRepair", "Glyph", "GlyphLine", "classify_lines", "letter_spaced_line",
    "letter_spaced_page", "pdf_page_glyph_lines", "pdfium_glyph_lines",
    "repair_letter_spaced_line", "repair_page_lines", "repair_pdf_text",
    "repair_summary", "spurious_space_indices",
]
