"""The research library of a project (Stage 37.3, Issue #69).

Papers, plans, manuals and notes the researcher adds explicitly (PDF, DOCX,
TXT, Markdown) are read on this computer, cut into page- and section-aware
passages and indexed for offline lexical search. Nothing here opens a
network connection; there is no interface code either (``workspace_library``
draws the page).

One library per project, inside the project folder::

    <project folder>/library/
        library.sqlite3          documents, their extracted text, passages,
                                 the search index and the AI transfer log;
                                 its own schema version (PRAGMA user_version)
        sources/<sha256><ext>    the imported files, content-addressed and
                                 never changed after writing

The project database (``project.sqlite3``, format 6) is not touched: the
library is a separate file, so a project written by an older version opens
unchanged, and switching project switches the library.

**Reading.** PDF: the text layer per page (pypdf); a page whose text layer
holds almost nothing but draws an image can be read with the bundled local
Tesseract (``ocr_runtime``) when the researcher asks for it. DOCX: paragraphs
and tables in document order; heading styles start sections. Markdown: ``#``
and underlined headings. TXT: paragraphs; numbered, all-capital and common
section titles start sections.

**Passages.** A passage never crosses a page (PDF) or a section; its text is
an exact slice of the extracted text of its page (``start_offset`` …
``end_offset``), so a citation points to a place that can be shown. Each
passage has a stable cite ID: the document key (from the file's SHA-256)
and a locator, ``D3F9A1B2C-p4.2`` (page 4, second passage) or
``D3F9A1B2C-s3.1`` (section 3 of a document without pages). Reading the
same bytes with the same chunker version gives the same IDs.

**Search.** SQLite FTS5 with BM25 ranking and ``snippet()``; the tokenizer,
the query form and the ё→е folding were chosen on a labelled EN/LV/RU
benchmark (``tools/library_benchmark.py``, docs/STAGE37_RAG.md §4). Where
FTS5 is not compiled in, a pure-Python BM25 over the same tokens, the same
formula and the same constants (k1 = 1.2, b = 0.75, IDF floor 1e-6) ranks
the passages; ``tests/test_research_library.py`` shows both give the same
order.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import unicodedata

SCHEMA_VERSION = 1
FOLDER = "library"
DB_NAME = "library.sqlite3"
SOURCES = "sources"
# Parser and chunker version: a document indexed by another one is listed by
# ``outdated()`` and read again by ``reindex``.
CHUNKER = "passages-1"
SUFFIX_TYPES = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "md", ".markdown": "md"}
TYPES = ("pdf", "docx", "txt", "md")
LANGUAGES = ("en", "lv", "ru", "other")
MAX_BYTES = 64 * 1024 * 1024
MAX_PAGES = 2000
MAX_CHARS = 4_000_000              # extracted text of one document
MAX_OCR_PAGES = 60
OCR_MIN_LETTERS = 25               # a page with fewer letters in its text layer is an image page
OCR_MIN_IMAGE_SHARE = 0.08         # ... when its placed images cover this share of it
OCR_TIMEOUT = 180
TARGET_CHARS = 900                 # a passage grows to about this size
MAX_PASSAGE_CHARS = 1400           # and is split (at sentences) above this one
SMALL_PASSAGE = 160                # a short last passage joins the one before it
# Chosen on the benchmark (docs/STAGE37_RAG.md §4): unicode61 with every Latin
# diacritic removed, light-stem prefix queries without stopwords, ё read as е.
DEFAULT_TOKENIZER = "unicode61 remove_diacritics 2"
DEFAULT_QUERY_MODE = "stem"
DEFAULT_FOLD_YO = True
QUERY_MODES = ("exact", "prefix", "stem", "stem-lang")
SNIPPET_TOKENS = 28
MARK_OPEN, MARK_CLOSE = "\x02", "\x03"     # around matched words in a snippet
ELLIPSIS = "…"
K1, B = 1.2, 0.75                         # the FTS5 bm25() defaults
MAX_QUERY_TERMS = 24
MAX_QUERY_CHARS = 500
OCR_LANGUAGE = re.compile(r"^(eng|lav|rus)(\+(eng|lav|rus)){0,2}$")


class LibraryError(Exception):
    """Something the library cannot do as asked. ``reason`` is a stable key
    for the interface (``library.error.<reason>``), ``values`` fill its text."""

    def __init__(self, reason: str, message: str = "", **values):
        super().__init__(message or reason)
        self.reason = reason
        self.values = values


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ================================================================ SQLite
@dataclass(frozen=True)
class Capabilities:
    """What the SQLite of this Python offers the library."""

    sqlite: str
    fts5: bool
    trigram: bool
    trigram_diacritics: bool

    def tokenizer_works(self, tokenizer: str) -> bool:
        return _creates(f"CREATE VIRTUAL TABLE temp.probe USING fts5(a, tokenize='{tokenizer}')")


def _creates(sql: str) -> bool:
    try:
        with closing(sqlite3.connect(":memory:")) as db:
            db.execute(sql)
        return True
    except sqlite3.Error:
        return False


@lru_cache(maxsize=1)
def capabilities() -> Capabilities:
    """FTS5, its trigram tokenizer and trigram's ``remove_diacritics`` (SQLite
    3.34 / 3.45) in the SQLite this Python was built with (the packaged
    Windows runtime: SQLite 3.49.1 with FTS5, docs/STAGE37_RAG.md §3)."""
    fts5 = _creates("CREATE VIRTUAL TABLE temp.probe USING fts5(a)")
    trigram = fts5 and _creates(
        "CREATE VIRTUAL TABLE temp.probe USING fts5(a, tokenize='trigram')")
    diacritics = trigram and _creates(
        "CREATE VIRTUAL TABLE temp.probe USING fts5(a, tokenize='trigram remove_diacritics 1')")
    return Capabilities(sqlite3.sqlite_version, fts5, trigram, diacritics)


# ============================================================ tokenizing
# The Python mirror of FTS5's unicode61 tokenizer (fallback search, "why this
# source?", snippets without FTS5): runs of letters and digits, lower case,
# Latin diacritics removed (remove_diacritics 1: one diacritic per letter;
# 2: all). Cyrillic й and ё stay as they are, as in unicode61; ё is folded to
# е before tokenizing, in the index and in queries alike (``fold_yo``).
_TOKEN = re.compile(r"[^\W_]+")
_LATIN_LETTERS_LV = "āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ"


@lru_cache(maxsize=4096)
def _fold_char(char: str, remove_diacritics: int) -> str:
    lower = char.lower()
    if len(lower) != 1:
        lower = char
    if not remove_diacritics or lower.isascii():
        return lower
    try:
        latin = unicodedata.name(lower).startswith("LATIN")
    except ValueError:
        latin = False
    if not latin:
        return lower
    decomposed = unicodedata.normalize("NFD", lower)
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    marks = len(decomposed) - len(base)
    if len(base) != 1 or (remove_diacritics == 1 and marks > 1):
        return lower
    return base


def fold_token(token: str, remove_diacritics: int = 2) -> str:
    lower = token.lower()
    if lower.isascii() or not remove_diacritics:
        return lower if len(lower) == len(token) else "".join(
            _fold_char(c, remove_diacritics) for c in token)
    return "".join(_fold_char(c, remove_diacritics) for c in token)


def fold_yo(text: str) -> str:
    """ё → е (length-preserving): Russian is mostly written without ё."""
    return text.replace("ё", "е").replace("Ё", "Е")


def token_spans(text: str, remove_diacritics: int = 2) -> list[tuple[int, int, str]]:
    """(start, end, folded token) of every token, as unicode61 cuts them."""
    return [(m.start(), m.end(), fold_token(m.group(), remove_diacritics))
            for m in _TOKEN.finditer(text)]


def tokens(text: str, remove_diacritics: int = 2) -> list[str]:
    return [token for _, _, token in token_spans(text, remove_diacritics)]


def _diacritics_option(tokenizer: str) -> int:
    match = re.search(r"remove_diacritics\s+(\d)", tokenizer)
    if match:
        return int(match.group(1))
    return 0 if tokenizer.startswith("trigram") else 1


# Function words of English, Latvian and Russian, left out of prefix queries
# (negations stay: "no effect" and "не отличаются" mean something).
STOPWORDS = frozenset("""
a an and are as at be been by for from has have how if in into is it its of on or
that the their there these this those to was were what when where which who why with
does do did can could should would will may might about between than then so such
un ir ar kas ka par no uz pie vai bet arī kā kur kad ja jo lai tas tā tie tās to tos
šis šī šie šīs ko kam kuru kura kuri kuras pēc līdz starp vēl tikai jau gan
и в во на с со что как по к ко у о об обо из за для от до при это этот эта эти а но
же ли бы был была было были быть есть его её их ему ей им или то так также где когда
чтобы который которая которые которого какой какая какие
""".split())
# Endings removed before a prefix query (the longest that leaves 4 letters):
# English, Latvian and Russian inflection, so "students" finds "student",
# "lonely" finds "loneliness", "vientulības" finds "vientulība" and
# "одиночества" finds "одиночество".
SUFFIXES_BY_LANGUAGE = {
    "en": tuple("ing ed es s ly".split()),
    "lv": tuple("iem ām ās ēm ēs īm īs os as es is us ai ei ie a u i e o s š ā ē ī ū".split()),
    "ru": tuple("ами ями ого его ому ему ыми ими ах ях ов ев ей ой ый ий ая яя ое ее ые ие "
                "ом ем ам ям ую юю ть а я о е ы и у ю ь й".split()),
}
SUFFIXES = tuple(sorted({s for group in SUFFIXES_BY_LANGUAGE.values() for s in group},
                        key=len, reverse=True))


def stem(token: str, suffixes=SUFFIXES) -> str:
    """A light stem for a prefix query: the longest listed ending that
    leaves four letters is removed (``suffixes`` longest first)."""
    if len(token) < 5 or token.isdigit():
        return token
    for suffix in sorted(suffixes, key=len, reverse=True):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[:-len(suffix)]
    return token


@dataclass(frozen=True)
class QueryTerm:
    text: str          # what is matched: a token, or a stem with ``prefix``
    prefix: bool

    @property
    def shown(self) -> str:
        return self.text + ("…" if self.prefix else "")


def query_terms(query: str, *, mode: str = DEFAULT_QUERY_MODE, fold: bool = DEFAULT_FOLD_YO,
                trigram: bool = False) -> tuple[QueryTerm, ...]:
    """The terms a typed query searches for (benchmarked in
    docs/STAGE37_RAG.md §4):

    * ``exact``: every word as typed;
    * ``prefix``: function words left out, every other word a prefix (``word*``);
    * ``stem``: function words left out, the others stemmed with the English,
      Latvian and Russian endings together and matched as prefixes;
    * ``stem-lang``: the same with the endings of the query's language only.

    Query syntax is never passed to FTS5: every term is quoted, so quotes,
    ``*``, ``NOT`` or ``NEAR`` in a query are plain words."""
    if mode not in QUERY_MODES:
        raise ValueError(f"Unknown query mode {mode!r}")
    text = str(query or "")[:MAX_QUERY_CHARS]
    if fold:
        text = fold_yo(text)
    suffixes = SUFFIXES
    if mode == "stem-lang":
        suffixes = SUFFIXES_BY_LANGUAGE.get(detect_language(text), SUFFIXES)
    found: list[QueryTerm] = []
    for raw in _TOKEN.findall(text):
        token = raw.lower()
        if mode == "exact":
            term = QueryTerm(token, False)
        else:
            if token in STOPWORDS:
                continue
            base = token if mode == "prefix" else stem(token, suffixes)
            term = QueryTerm(base, len(base) >= 3 and not base.isdigit())
        if trigram:
            if len(term.text) < 3:
                continue
            term = QueryTerm(term.text, False)        # trigram matches substrings anyway
        if term not in found:
            found.append(term)
    return tuple(found[:MAX_QUERY_TERMS])


def match_expression(terms) -> str:
    return " OR ".join('"' + term.text.replace('"', '""') + '"' + ("*" if term.prefix else "")
                       for term in terms)


# ======================================================== language, text
_EN_HINTS = frozenset("the and of to in is are was were that with for this from".split())
_LV_HINTS = frozenset("un ir ar kas par no uz vai arī tiek kā pēc jo nav ka".split())


def detect_language(text: str) -> str:
    """en, lv, ru or other: Cyrillic letters; Latvian letters and words; English words."""
    sample = text[:200_000]
    letters = [c for c in sample if c.isalpha()]
    if not letters:
        return "other"
    cyrillic = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    if cyrillic / len(letters) > 0.3:
        return "ru"
    words = [w.lower() for w in _TOKEN.findall(sample)]
    marks = sum(1 for c in letters if c in _LATIN_LETTERS_LV)
    english = sum(1 for w in words if w in _EN_HINTS)
    latvian = sum(1 for w in words if w in _LV_HINTS)
    if marks / len(letters) > 0.01 or latvian > english:
        return "lv"
    ascii_letters = sum(1 for c in letters if c.isascii())
    if english or ascii_letters / len(letters) > 0.9:
        return "en"
    return "other"


_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(text: str) -> str:
    """NFC (a decomposed ā would split a word), no control characters (the
    snippet marks), no carriage returns."""
    text = unicodedata.normalize("NFC", str(text or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    return _CONTROL.sub("", text)


def _letters(text: str) -> int:
    return sum(1 for c in text if c.isalpha())


# ============================================================ extraction
@dataclass(frozen=True)
class Paragraph:
    start: int
    end: int
    level: int = 0            # a heading's level (1 = top); 0 = body text


@dataclass(frozen=True)
class Segment:
    """The extracted text of one PDF page (``page``) or of a whole document
    without pages (``page`` None), with its paragraphs and headings."""

    page: int | None
    text: str
    paragraphs: tuple[Paragraph, ...]


@dataclass
class Extracted:
    segments: list[Segment]
    page_count: int = 0
    title: str = ""
    ocr_pages: tuple[int, ...] = ()
    notes: list[tuple[str, dict]] = field(default_factory=list)


def _assemble(blocks, page: int | None) -> Segment:
    """Blocks of (text, heading level) as one segment: blocks separated by a
    blank line, offsets of every paragraph exact."""
    parts, paragraphs, position = [], [], 0
    for text, level in blocks:
        text = text.strip()
        if not text:
            continue
        if parts:
            parts.append("\n\n")
            position += 2
        parts.append(text)
        paragraphs.append(Paragraph(position, position + len(text), level))
        position += len(text)
    return Segment(page, "".join(parts), tuple(paragraphs))


_HEADING_WORDS = frozenset("""
abstract introduction background method methods methodology materials participants
procedure measures results findings discussion conclusion conclusions limitations
references appendix acknowledgements summary
kopsavilkums ievads metode metodes metodoloģija dalībnieki procedūra rezultāti diskusija
secinājumi ierobežojumi literatūra pielikums anotācija
аннотация введение метод методы методология участники процедура результаты обсуждение
выводы заключение ограничения литература приложение
""".split())
_NUMBERED_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+\S")


def heading_level(line: str) -> int:
    """A likely section title in plain or PDF text (0 = not a heading):
    "2.1 Sample", "Results", "RESULTS". Conservative: a sentence is not one."""
    line = line.strip()
    if not 2 <= len(line) <= 90 or _letters(line) < 3:
        return 0
    if line.endswith((".", ",", ";")) and not _NUMBERED_HEADING.match(line):
        return 0
    match = _NUMBERED_HEADING.match(line)
    if match and len(line) <= 80 and not line.rstrip().endswith((".", ",", ";", ":")):
        words = line[match.end(1):].split()
        if 1 <= len(words) <= 10 and _letters(line[match.end(1):]) >= 3:
            return min(4, match.group(1).count(".") + 1)
    word = line.rstrip(":").strip().lower()
    if word in _HEADING_WORDS:
        return 1
    letters = [c for c in line if c.isalpha()]
    if (len(letters) >= 4 and len(line) <= 60 and len(line.split()) <= 8
            and sum(1 for c in letters if c.isupper()) / len(letters) > 0.9):
        return 1
    return 0


def _dehyphenate(lines: list[str]) -> list[str]:
    """Join a word broken over two lines ("investi-" + "gation")."""
    joined: list[str] = []
    for line in lines:
        if (joined and re.search(r"[^\W\d_]-$", joined[-1]) and line[:1].islower()
                and not joined[-1].endswith("--")):
            head, _, tail = line.partition(" ")
            joined[-1] = joined[-1][:-1] + head
            if tail:
                joined.append(tail)
            continue
        joined.append(line)
    return joined


_PAGE_NUMBER = re.compile(r"(?i)^(?:[\s\-–—|]*\d{1,4}[\s\-–—|]*|(?:page|p\.|lpp\.|стр\.?|"
                          r"страница)\s*\d{1,4}(?:\s*(?:of|no|из|/)\s*\d{1,4})?)$")
HEADING_SIZE_RATIO = 1.15          # a heading line is set this much larger than the body


def _heading_shape(line: str) -> bool:
    """Short enough and not ending a sentence: may be a title or a heading."""
    return (2 <= len(line) <= 150 and _letters(line) >= 2 and len(line.split()) <= 20
            and not line.endswith((".", ",", ";")))


def _pdf_lines(page) -> list[tuple[str, float]]:
    """(line, font size) of a page's text layer: pypdf's text visitor gives
    every piece of text with its font size and matrices."""
    pieces: list[tuple[str, float]] = []

    def visit(text, cm, tm, font, size):
        if not text:
            return
        try:
            scale = (abs(tm[0] * tm[3] - tm[1] * tm[2]) * abs(cm[0] * cm[3] - cm[1] * cm[2])) ** 0.5
        except Exception:
            scale = 1.0
        pieces.append((text, round(abs(float(size or 0.0)) * (scale or 1.0), 1)))

    plain = page.extract_text(visitor_text=visit) or ""
    if not pieces:
        return [(line, 0.0) for line in plain.split("\n")]
    lines: list[tuple[str, float]] = []
    current: list[str] = []
    weights: dict[float, int] = {}

    def flush():
        lines.append(("".join(current), max(weights, key=weights.get) if weights else 0.0))
        current.clear()
        weights.clear()

    for text, size in pieces:
        for index, part in enumerate(text.split("\n")):
            if index:
                flush()
            current.append(part)
            if part.strip():
                weights[size] = weights.get(size, 0) + len(part.strip())
    flush()
    return lines


def _size_levels(pages: list[list[tuple[str, float]]]) -> tuple[float, dict[float, int]]:
    """The body font size (the one with most characters) and a heading level
    for every larger size that short lines use (largest = level 1)."""
    weights: dict[float, int] = {}
    for lines in pages:
        for text, size in lines:
            if size:
                weights[size] = weights.get(size, 0) + len(text.strip())
    if not weights:
        return 0.0, {}
    body = max(weights, key=weights.get)
    larger = sorted({size for lines in pages for text, size in lines
                     if size >= body * HEADING_SIZE_RATIO
                     and _heading_shape(" ".join(clean_text(text).split()))}, reverse=True)
    return body, {size: min(index + 1, 4) for index, size in enumerate(larger)}


def _pdf_blocks(lines: list[tuple[str, float]], levels: dict[float, int] | None = None
                ) -> list[tuple[str, int]]:
    """The text of a PDF page as blocks: a heading alone (set larger than the
    body, or numbered, a common section title or all capitals), body lines
    joined into paragraphs (a short line ending a sentence ends a paragraph).
    Bare page numbers are left out."""
    levels = levels or {}
    rows: list[tuple[str, int]] = []
    for text, size in lines:
        text = " ".join(clean_text(text).split())
        if not text or _PAGE_NUMBER.match(text):
            continue
        level = levels.get(size, 0) if _heading_shape(text) else 0
        rows.append((text, level or heading_level(text)))
    long_lines = sorted(len(text) for text, level in rows if not level and len(text) >= 40)
    typical = long_lines[len(long_lines) // 2] if long_lines else 80
    blocks: list[tuple[str, int]] = []
    run: list[str] = []

    def paragraphs():
        current: list[str] = []
        for line in _dehyphenate(run):
            current.append(line)
            if re.search(r"[.!?…:]['\"”»)]?$", line) and len(line) < 0.8 * typical:
                blocks.append((" ".join(current), 0))
                current = []
        if current:
            blocks.append((" ".join(current), 0))
        run.clear()

    previous_heading = False
    for text, level in rows:
        if not level:
            run.append(text)
            previous_heading = False
            continue
        paragraphs()
        if previous_heading and blocks and blocks[-1][1] == level:
            blocks[-1] = (blocks[-1][0] + " " + text, level)      # a heading on two lines
        else:
            blocks.append((text, level))
        previous_heading = True
    paragraphs()
    return blocks


def _plain_blocks(text: str, *, markdown: bool) -> list[tuple[str, int]]:
    """TXT or Markdown: paragraphs separated by blank lines; ``#`` and
    underlined headings (Markdown) or likely titles (TXT) start sections."""
    blocks: list[tuple[str, int]] = []
    paragraph: list[str] = []
    fence = False

    def flush():
        if paragraph:
            joined = " ".join(" ".join(line.split()) for line in paragraph)
            level = heading_level(joined) if not markdown and len(paragraph) == 1 else 0
            blocks.append((joined, level))
            paragraph.clear()

    lines = clean_text(text).split("\n")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if markdown:
            if stripped.startswith(("```", "~~~")):
                fence = not fence
                flush()
                continue
            atx = None if fence else re.match(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if atx and atx.group(2).strip():
                flush()
                blocks.append((atx.group(2).strip(), len(atx.group(1))))
                continue
            if (not fence and paragraph and len(paragraph) == 1 and stripped
                    and re.fullmatch(r"=+|-+", stripped)):
                title = " ".join(paragraph[0].split())
                paragraph.clear()
                blocks.append((title, 1 if stripped[0] == "=" else 2))
                continue
        if not stripped:
            flush()
            continue
        paragraph.append(line)
    flush()
    return blocks


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            if encoding == "utf-16" and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    high = sum(1 for byte in data if byte >= 0xC0)
    return data.decode("cp1251" if high > len(data) * 0.3 else "cp1257", errors="replace")


def _heading_style_level(paragraph) -> int:
    style = getattr(paragraph, "style", None)
    names = [str(getattr(style, "name", "") or ""), str(getattr(style, "style_id", "") or "")]
    for name in names:
        if re.fullmatch(r"(?i)title", name.strip()):
            return 1
        match = re.fullmatch(r"(?i)(?:heading|virsraksts|заголовок)\s*(\d)", name.strip())
        if match:
            return max(1, min(6, int(match.group(1))))
    try:
        values = paragraph._p.xpath("./w:pPr/w:outlineLvl/@w:val")
        if values and int(values[0]) < 9:
            return int(values[0]) + 1
    except Exception:
        pass
    return 0


def _docx_blocks(data: bytes) -> tuple[list[tuple[str, int]], str]:
    from docx import Document
    from docx.table import Table

    document = Document(io.BytesIO(data))
    blocks: list[tuple[str, int]] = []
    title = ""
    for item in document.iter_inner_content():
        if isinstance(item, Table):
            for row in item.rows:
                cells: list[str] = []
                for cell in row.cells:
                    value = " ".join(cell.text.split())
                    if value and (not cells or cells[-1] != value):
                        cells.append(value)
                if cells:
                    blocks.append((" | ".join(cells), 0))
            continue
        value = " ".join(clean_text(item.text).split())
        if not value:
            continue
        level = _heading_style_level(item)
        if level and not title and str(getattr(item.style, "name", "")).lower() == "title":
            title = value
        blocks.append((value, level))
    try:
        title = (document.core_properties.title or "").strip() or title
    except Exception:
        pass
    return blocks, title


def _pdf_image_share(data: bytes, pages: list[int]) -> dict[int, float]:
    """Share of each page covered by the images it draws (PDFium)."""
    try:
        import pypdfium2 as pdfium
        import pypdfium2.raw as pdfium_c
    except Exception:
        return {page: 1.0 for page in pages}
    shares: dict[int, float] = {}
    pdf = pdfium.PdfDocument(data)
    try:
        for number in pages:
            page = pdf[number - 1]
            try:
                width, height = page.get_size()
                area = 0.0
                for image in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
                    bounds = getattr(image, "get_bounds", None) or image.get_pos
                    left, bottom, right, top = bounds()
                    area += max(0.0, right - left) * max(0.0, top - bottom)
                shares[number] = min(1.0, area / (width * height)) if width and height else 0.0
            finally:
                page.close()
    finally:
        pdf.close()
    return shares


def render_pdf_page(data: bytes, page_number: int, *, scale: float = 1.4,
                    max_width: int = 1300, max_pixels: int = 5_000_000) -> tuple[bytes, float]:
    """A PDF page as PNG (bounded size) and the DPI it was drawn at."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        if not 1 <= page_number <= len(pdf):
            raise LibraryError("no_page", page=page_number)
        page = pdf[page_number - 1]
        try:
            width, height = page.get_size()
            if not (0 < width <= 20000 and 0 < height <= 20000):
                raise LibraryError("unreadable")
            safe = min(scale, max_width / width, (max_pixels / (width * height)) ** 0.5)
            image = page.render(scale=safe).to_pil().convert("RGB")
            try:
                out = io.BytesIO()
                image.save(out, "PNG", compress_level=3)
                return out.getvalue(), 72.0 * safe
            finally:
                image.close()
        finally:
            page.close()
    finally:
        pdf.close()


def ocr_page(data: bytes, page_number: int, language: str, *, cancel=None,
             timeout: int = OCR_TIMEOUT) -> str:
    """One PDF page read with the LOCAL Tesseract (``ocr_runtime``)."""
    from ocr_runtime import OCRCancelled, resolve_tesseract, run_tesseract

    if not OCR_LANGUAGE.match(language or ""):
        raise LibraryError("ocr_language", language=language)
    png, dpi = render_pdf_page(data, page_number, scale=2.0, max_width=1800)
    runtime = resolve_tesseract()
    try:
        code, output, diagnostic = run_tesseract(
            runtime, ["{image}", "stdout", "-l", language, "--psm", "3",
                      "--dpi", str(int(min(max(dpi, 70), 600)))],
            image=png, timeout=timeout, cancel=cancel)
    except OCRCancelled as error:
        raise LibraryError("cancelled") from error
    if code:
        raise RuntimeError(f"local OCR failed: {diagnostic[:200]}")
    return output.decode("utf-8", errors="replace")


def ocr_available() -> tuple[bool, tuple[str, ...]]:
    """Whether the local OCR engine runs here, and its installed languages."""
    try:
        from ocr_runtime import ocr_readiness, tesseract_available

        if not tesseract_available():
            return False, ()
        return True, tuple(ocr_readiness().languages)
    except Exception:
        return False, ()


def _check(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise LibraryError("cancelled")


@contextmanager
def _quiet_pypdf():
    """pypdf logs every repair of a damaged file; the outcome is reported instead."""
    import logging

    logger = logging.getLogger("pypdf")
    level = logger.level
    logger.setLevel(logging.ERROR + 10)
    try:
        yield
    finally:
        logger.setLevel(level)


def _read_pdf(data: bytes, *, ocr: bool, ocr_language: str, progress, cancel) -> Extracted:
    with _quiet_pypdf():
        return _read_pdf_pages(data, ocr=ocr, ocr_language=ocr_language, progress=progress,
                               cancel=cancel)


def _read_pdf_pages(data: bytes, *, ocr: bool, ocr_language: str, progress,
                    cancel) -> Extracted:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise LibraryError("encrypted")
        count = len(reader.pages)
    except LibraryError:
        raise
    except Exception as error:
        raise LibraryError("unreadable", str(error)) from error
    if count > MAX_PAGES:
        raise LibraryError("too_many_pages", pages=count, limit=MAX_PAGES)
    pages: list[list[tuple[str, float]]] = []
    for number, page in enumerate(reader.pages, start=1):
        _check(cancel)
        try:
            pages.append(_pdf_lines(page))
        except Exception:
            try:
                pages.append([(line, 0.0) for line in (page.extract_text() or "").split("\n")])
            except Exception:
                pages.append([])
        if progress is not None:
            progress("read", number, count)
    texts = ["\n".join(text for text, _ in lines) for lines in pages]
    extracted = Extracted([], count)
    try:
        title = str((reader.metadata or {}).get("/Title") or "").strip()
        placeholder = re.search(r"(?i)\.(pdf|docx?)$|^untitled|^microsoft", title)
        if 3 <= len(title) <= 200 and not placeholder:
            extracted.title = title
    except Exception:
        pass
    low = [n for n, text in enumerate(texts, start=1) if _letters(text) < OCR_MIN_LETTERS]
    if low:
        shares = _pdf_image_share(data, low)
        images = [n for n in low if shares.get(n, 0.0) >= OCR_MIN_IMAGE_SHARE]
        if images and not ocr:
            extracted.notes.append(("ocr_off", {"pages": images}))
        elif images:
            available, _languages = ocr_available()
            if not available:
                extracted.notes.append(("ocr_unavailable", {"pages": images}))
            else:
                chosen, later = images[:MAX_OCR_PAGES], images[MAX_OCR_PAGES:]
                if later:
                    extracted.notes.append(("ocr_limit", {"pages": later, "limit": MAX_OCR_PAGES}))
                done, failed = [], []
                for index, number in enumerate(chosen, start=1):
                    _check(cancel)
                    if progress is not None:
                        progress("ocr", index, len(chosen))
                    try:
                        recognised = ocr_page(data, number, ocr_language, cancel=cancel)
                        pages[number - 1] = [(line, 0.0) for line in recognised.split("\n")]
                        done.append(number)
                    except LibraryError:
                        raise
                    except Exception as error:
                        failed.append(number)
                        detail = " ".join(str(error).split())[:200]
                if done:
                    extracted.ocr_pages = tuple(done)
                    extracted.notes.append(("ocr_read", {"pages": done}))
                if failed:
                    extracted.notes.append(("ocr_failed", {"pages": failed, "detail": detail}))
    body, levels = _size_levels(pages)
    if not extracted.title and pages and levels:
        # The largest line of page 1 set above the body size is the title.
        candidates = [(size, " ".join(clean_text(text).split())) for text, size in pages[0]
                      if size in levels]
        if candidates:
            largest = max(size for size, _ in candidates)
            extracted.title = next(text for size, text in candidates if size == largest)[:200]
    extracted.segments = [_assemble(_pdf_blocks(lines, levels), number)
                          for number, lines in enumerate(pages, start=1)]
    return extracted


def extract(data: bytes, kind: str, *, ocr: bool = False, ocr_language: str = "eng",
            progress=None, cancel=None) -> Extracted:
    """The text of a document, in segments (one per PDF page)."""
    if kind == "pdf":
        extracted = _read_pdf(data, ocr=ocr, ocr_language=ocr_language, progress=progress,
                              cancel=cancel)
    elif kind == "docx":
        try:
            blocks, title = _docx_blocks(data)
        except Exception as error:
            raise LibraryError("unreadable", str(error)) from error
        extracted = Extracted([_assemble(blocks, None)], 0, title)
    elif kind in ("txt", "md"):
        blocks = _plain_blocks(_decode_text(data), markdown=kind == "md")
        title = ""
        if kind == "md":
            title = next((text for text, level in blocks if level == 1), "")
        elif (len(blocks) > 1 and not blocks[0][1] and len(blocks[0][0]) <= 120
              and _heading_shape(blocks[0][0])):
            title = blocks[0][0]                # a short first line is the title
            blocks[0] = (title, 1)
        extracted = Extracted([_assemble(blocks, None)], 0, title)
    else:
        raise LibraryError("unsupported", kind=kind)
    if sum(len(s.text) for s in extracted.segments) > MAX_CHARS:
        raise LibraryError("too_much_text", limit=MAX_CHARS)
    return extracted


# ============================================================== passages
@dataclass(frozen=True)
class Draft:
    """A passage before it is stored."""

    ordinal: int
    segment: int
    page: int | None
    section: str
    start: int
    end: int
    text: str
    locator: str


_SENTENCE_END = re.compile(r"[.!?…]['\"”»)\]]*\s+")


def _pieces(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """[start, end) of ``text`` cut at sentence ends into pieces of at most
    MAX_PASSAGE_CHARS (a longer sentence at a space)."""
    cuts = [start] + [m.end() for m in _SENTENCE_END.finditer(text, start, end)] + [end]
    sentences = [(a, b) for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]
    pieces: list[tuple[int, int]] = []
    current: list[int] | None = None
    for a, b in sentences:
        while b - a > MAX_PASSAGE_CHARS:                    # one very long sentence
            limit = a + MAX_PASSAGE_CHARS
            space = text.rfind(" ", a + MAX_PASSAGE_CHARS // 2, limit)
            cut = space + 1 if space > a else limit
            if current is not None:
                pieces.append((current[0], current[1]))
                current = None
            pieces.append((a, cut))
            a = cut
        if current is not None and b - current[0] <= TARGET_CHARS:
            current[1] = b
        else:
            if current is not None:
                pieces.append((current[0], current[1]))
            current = [a, b]
    if current is not None:
        pieces.append((current[0], current[1]))
    trimmed = []
    for a, b in pieces:
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if b > a:
            trimmed.append((a, b))
    return trimmed


def chunk(segments: list[Segment], title: str = "") -> list[Draft]:
    """Section- and page-aware passages: a passage starts at a heading (which
    it includes) or continues its section, grows to about TARGET_CHARS, never
    crosses a page or a section and is cut at sentences above
    MAX_PASSAGE_CHARS. The document's own title heading is not repeated in
    every section name. Deterministic: the same segments give the same
    passages and the same locators."""
    drafts: list[Draft] = []
    path: list[tuple[int, str]] = []
    section_number = 0
    own_title = " ".join(title.split()).casefold()
    for index, segment in enumerate(segments):
        text = segment.text
        spans: list[tuple[int, int, str, int]] = []      # start, end, section, section number
        pending: list | None = None
        heading_start: int | None = None
        heading_end = 0

        def flush():
            nonlocal pending
            if pending is not None:
                for a, b in _pieces(text, pending[0], pending[1]):
                    spans.append((a, b, pending[2], pending[3]))
                pending = None

        for paragraph in segment.paragraphs:
            if paragraph.level:
                flush()
                heading = text[paragraph.start:paragraph.end]
                while path and path[-1][0] >= paragraph.level:
                    path.pop()
                if not (own_title and not path and section_number == 0
                        and heading.casefold() == own_title):
                    path.append((paragraph.level, heading))
                section_number += 1
                if heading_start is None:
                    heading_start = paragraph.start
                heading_end = paragraph.end
                continue
            section = " › ".join(title for _, title in path)
            start = heading_start if heading_start is not None else paragraph.start
            heading_start = None
            if (pending is not None and pending[2] == section
                    and paragraph.end - pending[0] <= TARGET_CHARS):
                pending[1] = paragraph.end
            else:
                flush()
                pending = [start, paragraph.end, section, section_number]
        flush()
        if heading_start is not None:              # headings with no text after them here
            spans.append((heading_start, heading_end, " › ".join(t for _, t in path),
                          section_number))
        merged: list[tuple[int, int, str, int]] = []
        for span in spans:
            if (merged and span[1] - span[0] < SMALL_PASSAGE and merged[-1][2] == span[2]
                    and merged[-1][3] == span[3] and span[1] - merged[-1][0] <= MAX_PASSAGE_CHARS):
                previous = merged.pop()
                merged.append((previous[0], span[1], previous[2], previous[3]))
            else:
                merged.append(span)
        counts: dict[str, int] = {}
        for start, end, section, number in merged:
            place = f"p{segment.page}" if segment.page is not None else f"s{number}"
            counts[place] = counts.get(place, 0) + 1
            drafts.append(Draft(len(drafts) + 1, index, segment.page, section, start, end,
                                text[start:end], f"{place}.{counts[place]}"))
    return drafts


# ================================================================ records
@dataclass(frozen=True)
class Document:
    id: int
    key: str                  # cite prefix from the SHA-256 ("D3F9A1B2C")
    title: str
    file_name: str
    sha256: str
    size: int
    type: str
    language: str
    version_label: str
    page_count: int
    imported_at: str
    source_path: str
    stored_name: str
    ocr_pages: tuple[int, ...]
    ocr_language: str
    chunker: str
    indexed_at: str
    passages: int = 0


@dataclass(frozen=True)
class Passage:
    id: int
    document_id: int
    ordinal: int
    segment: int
    page: int | None
    section: str
    text: str
    start: int
    end: int
    cite_id: str


@dataclass(frozen=True)
class Hit:
    rank: int
    passage: Passage
    document: Document
    score: float             # BM25, higher is better
    snippet: str             # with MARK_OPEN / MARK_CLOSE around matched words
    terms: tuple[QueryTerm, ...]

    @property
    def cite_id(self) -> str:
        return self.passage.cite_id


@dataclass(frozen=True)
class SearchResult:
    query: str
    terms: tuple[QueryTerm, ...]
    hits: tuple[Hit, ...]
    total: int               # passages that match, before the limit
    backend: str
    filters: dict


@dataclass(frozen=True)
class AddOutcome:
    document: Document
    duplicate: bool
    passages: int
    notes: tuple[tuple[str, dict], ...] = ()


@dataclass(frozen=True)
class Explanation:
    """Why a passage was found ("why this source?"), worked out locally."""

    rank: int
    total: int
    score: float
    backend: str
    matched: tuple[tuple[str, int], ...]      # (term as shown, occurrences)
    missing: tuple[str, ...]
    filters: dict


def _document(row: sqlite3.Row) -> Document:
    return Document(row["id"], row["doc_key"], row["title"], row["file_name"], row["sha256"],
                    row["size"], row["type"], row["language"], row["version_label"],
                    row["page_count"], row["imported_at"], row["source_path"],
                    row["stored_name"], tuple(json.loads(row["ocr_pages"] or "[]")),
                    row["ocr_language"], row["chunker"], row["indexed_at"],
                    row["passages"] if "passages" in row.keys() else 0)


def _passage(row: sqlite3.Row) -> Passage:
    return Passage(row["id"], row["document_id"], row["ordinal"], row["segment"], row["page"],
                   row["section"], row["text"], row["start_offset"], row["end_offset"],
                   row["cite_id"])


def _title_from(file_name: str) -> str:
    stem = Path(file_name).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(stem.split()) or file_name


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ================================================================= schema
_SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE documents ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, doc_key TEXT NOT NULL UNIQUE, title TEXT NOT NULL,"
    " file_name TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, size INTEGER NOT NULL,"
    " type TEXT NOT NULL CHECK (type IN ('pdf', 'docx', 'txt', 'md')),"
    " language TEXT NOT NULL, version_label TEXT NOT NULL DEFAULT '',"
    " page_count INTEGER NOT NULL DEFAULT 0, imported_at TEXT NOT NULL,"
    " source_path TEXT NOT NULL DEFAULT '', stored_name TEXT NOT NULL,"
    " ocr_pages TEXT NOT NULL DEFAULT '[]', ocr_language TEXT NOT NULL DEFAULT '',"
    " chunker TEXT NOT NULL, indexed_at TEXT NOT NULL)",
    # The extracted text of every page (or document), with its paragraphs and
    # headings: passages are slices of it, and OCR text is kept for reindexing.
    "CREATE TABLE segments ("
    " document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,"
    " segment INTEGER NOT NULL, page INTEGER, text TEXT NOT NULL,"
    " paragraphs TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (document_id, segment))",
    "CREATE TABLE chunks ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,"
    " ordinal INTEGER NOT NULL, segment INTEGER NOT NULL, page INTEGER,"
    " section TEXT NOT NULL DEFAULT '', text TEXT NOT NULL,"
    " start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL,"
    " cite_id TEXT NOT NULL UNIQUE, tokens INTEGER NOT NULL DEFAULT 0,"
    " UNIQUE (document_id, ordinal))",
    "CREATE INDEX chunks_document ON chunks (document_id)",
    # The pure-Python index (used only where FTS5 is missing).
    "CREATE TABLE postings ("
    " term TEXT NOT NULL, chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,"
    " tf INTEGER NOT NULL, PRIMARY KEY (term, chunk_id)) WITHOUT ROWID",
    "CREATE INDEX postings_chunk ON postings (chunk_id)",
    # What went to an AI provider from this library (cite IDs, never the text).
    "CREATE TABLE ai_transfers ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, provider TEXT NOT NULL,"
    " model TEXT NOT NULL, cite_ids TEXT NOT NULL, tokens INTEGER NOT NULL,"
    " outcome TEXT NOT NULL)",
)


def library_folder(project_folder: Path) -> Path:
    return Path(project_folder) / FOLDER


# ------------------------------------------------- backups and copies
# Whether a project's library travels in its ``.sra`` backups and in a copy
# of the project is the researcher's explicit choice, off by default: notes
# and transcripts in a library may hold personal data, and papers may not be
# the researcher's to pass on (GDPR data minimisation; independent review §7).
# The choice is a file of the library, so it travels with it when on.
CHOICE_FILE = "backup.json"


def travels(project_folder: Path) -> bool:
    """True only when the researcher chose to include the library in backups
    and project copies (a missing or unreadable choice means no)."""
    try:
        value = json.loads((library_folder(project_folder) / CHOICE_FILE).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(value, dict) and value.get("include_in_backups") is True


def set_travels(project_folder: Path, include: bool) -> None:
    folder = library_folder(project_folder)
    folder.mkdir(parents=True, exist_ok=True)
    _atomic_write(folder / CHOICE_FILE, json.dumps(
        {"include_in_backups": bool(include), "chosen_at": now()}).encode("utf-8"))


def travelling_files(project_folder: Path) -> list[tuple[str, bytes]]:
    """(path inside the project folder, bytes) of the library for a backup or
    a copy: a consistent snapshot of its database, the choice and the stored
    documents. Empty unless the researcher chose to include the library."""
    if not travels(project_folder):
        return []
    folder = library_folder(project_folder)
    files: list[tuple[str, bytes]] = []
    database = folder / DB_NAME
    if database.is_file():
        with tempfile.TemporaryDirectory(prefix="sra-library-") as temp:
            copy = Path(temp) / DB_NAME
            with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db, \
                    closing(sqlite3.connect(copy)) as out:
                db.backup(out)
            files.append((f"{FOLDER}/{DB_NAME}", copy.read_bytes()))
    files.append((f"{FOLDER}/{CHOICE_FILE}", (folder / CHOICE_FILE).read_bytes()))
    sources = folder / SOURCES
    for path in sorted(sources.iterdir()) if sources.is_dir() else []:
        if path.is_file() and not path.name.startswith("."):
            files.append((f"{FOLDER}/{SOURCES}/{path.name}", path.read_bytes()))
    return files


def peek(project_folder: Path) -> tuple[int, int]:
    """(documents, passages) of a project's library, read-only; (0, 0) when
    it has none. Never creates the library."""
    path = library_folder(project_folder) / DB_NAME
    if not path.is_file():
        return 0, 0
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] > SCHEMA_VERSION:
                return 0, 0
            return (db.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                    db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    except sqlite3.Error:
        return 0, 0


# ================================================================ library
class Library:
    """The research library in ``folder`` (``<project>/library``).

    Every operation opens its own connection, so a document can be indexed
    in a worker thread while the interface searches; writes are serialised.
    ``tokenizer``, ``query_mode`` and ``fold`` exist for the benchmark; the
    application uses the defaults. ``backend`` "python" forces the fallback
    (tests); by default FTS5 is used where it exists.
    """

    def __init__(self, folder: Path, *, tokenizer: str = DEFAULT_TOKENIZER,
                 query_mode: str = DEFAULT_QUERY_MODE, fold: bool = DEFAULT_FOLD_YO,
                 backend: str | None = None):
        if query_mode not in QUERY_MODES:
            raise ValueError(f"Unknown query mode {query_mode!r}")
        if not re.fullmatch(r"[a-z0-9_ ]{1,80}", tokenizer):
            raise ValueError(f"Unsupported tokenizer {tokenizer!r}")
        self.folder = Path(folder)
        self.path = self.folder / DB_NAME
        self.tokenizer, self.query_mode, self.fold = tokenizer, query_mode, bool(fold)
        self.trigram = tokenizer.startswith("trigram")
        self.diacritics = _diacritics_option(tokenizer)
        caps = capabilities()
        if backend is None:
            backend = "fts5" if caps.fts5 and caps.tokenizer_works(tokenizer) else "python"
        if backend not in ("fts5", "python"):
            raise ValueError(f"Unknown backend {backend!r}")
        if backend == "python" and (self.trigram or tokenizer.startswith("porter")):
            raise LibraryError("tokenizer_unavailable", tokenizer=tokenizer)
        if backend == "fts5" and not (caps.fts5 and caps.tokenizer_works(tokenizer)):
            raise LibraryError("fts5_unavailable", tokenizer=tokenizer)
        self.backend = backend
        self._lock = threading.RLock()
        self._prepare()

    @classmethod
    def for_project(cls, project_folder: Path, **options) -> "Library":
        return cls(library_folder(project_folder), **options)

    # ---------------------------------------------------------- database
    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True,
                                 isolation_level=None, timeout=15)
        else:
            db = sqlite3.connect(self.path, isolation_level=None, timeout=15)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def _transaction(self):
        with self._lock, closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @contextmanager
    def _reading(self):
        with closing(self._connect()) as db:
            yield db

    def _prepare(self) -> None:
        """Create or check the database; build the index the backend needs."""
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / SOURCES).mkdir(exist_ok=True)
        if self.path.exists():
            with closing(self._connect(read_only=True)) as db:
                found = db.execute("PRAGMA user_version").fetchone()[0]
            if found > SCHEMA_VERSION:
                raise LibraryError("newer_format", found=found, supported=SCHEMA_VERSION)
        with self._transaction() as db:
            found = db.execute("PRAGMA user_version").fetchone()[0]
            if found == 0:
                for statement in _SCHEMA:
                    db.execute(statement)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                db.execute("INSERT INTO meta VALUES ('created_at', ?)", (now(),))
            meta = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM meta")}
            wanted = {"backend": self.backend, "tokenizer": self.tokenizer,
                      "fold": "yo" if self.fold else ""}
            if any(meta.get(key) != value for key, value in wanted.items()):
                self._build_index(db)
                for key, value in wanted.items():
                    db.execute("INSERT INTO meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE"
                               " SET value = excluded.value", (key, value))

    def _view_sql(self) -> str:
        text = "replace(replace(text, 'ё', 'е'), 'Ё', 'Е')" if self.fold else "text"
        return f"CREATE VIEW chunk_search AS SELECT id, document_id, {text} AS text FROM chunks"

    def _build_index(self, db: sqlite3.Connection) -> None:
        """(Re)build the search index of every stored passage for this backend."""
        db.execute("DELETE FROM postings")
        if self.backend == "fts5":
            db.execute("DROP TABLE IF EXISTS chunk_index")
            db.execute("DROP VIEW IF EXISTS chunk_search")
            db.execute(self._view_sql())
            db.execute("CREATE VIRTUAL TABLE chunk_index USING fts5(text, content='chunk_search',"
                       f" content_rowid='id', tokenize='{self.tokenizer}')")
            db.execute("INSERT INTO chunk_index(chunk_index) VALUES ('rebuild')")
            return
        # The FTS5 table of a library made elsewhere cannot be touched without
        # the module; it is left as it is and rebuilt when FTS5 is back.
        rows = db.execute("SELECT id, text FROM chunks").fetchall()
        for row in rows:
            self._post(db, row["id"], row["text"])

    def _search_text(self, text: str) -> str:
        return fold_yo(text) if self.fold else text

    def _post(self, db: sqlite3.Connection, chunk_id: int, text: str) -> None:
        counts: dict[str, int] = {}
        found = tokens(self._search_text(text), self.diacritics)
        for token in found:
            counts[token] = counts.get(token, 0) + 1
        db.executemany("INSERT INTO postings (term, chunk_id, tf) VALUES (?, ?, ?)",
                       [(term, chunk_id, tf) for term, tf in counts.items()])
        db.execute("UPDATE chunks SET tokens = ? WHERE id = ?", (len(found), chunk_id))

    def _index_document(self, db: sqlite3.Connection, document_id: int) -> None:
        if self.backend == "fts5":
            db.execute("INSERT INTO chunk_index (rowid, text) SELECT id, text FROM chunk_search"
                       " WHERE document_id = ?", (document_id,))
            return
        for row in db.execute("SELECT id, text FROM chunks WHERE document_id = ?",
                              (document_id,)).fetchall():
            self._post(db, row["id"], row["text"])

    def _unindex_document(self, db: sqlite3.Connection, document_id: int) -> None:
        if self.backend == "fts5":
            db.execute("INSERT INTO chunk_index (chunk_index, rowid, text)"
                       " SELECT 'delete', id, text FROM chunk_search WHERE document_id = ?",
                       (document_id,))
        else:
            db.execute("DELETE FROM postings WHERE chunk_id IN"
                       " (SELECT id FROM chunks WHERE document_id = ?)", (document_id,))

    # ------------------------------------------------------------ queries
    _DOCUMENTS = ("SELECT d.*, (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id)"
                  " AS passages FROM documents d")

    def documents(self) -> list[Document]:
        with self._reading() as db:
            return [_document(r) for r in db.execute(
                self._DOCUMENTS + " ORDER BY d.imported_at DESC, d.id DESC")]

    def document(self, document_id: int) -> Document:
        with self._reading() as db:
            row = db.execute(self._DOCUMENTS + " WHERE d.id = ?", (int(document_id),)).fetchone()
        if row is None:
            raise LibraryError("no_document", document=document_id)
        return _document(row)

    def passages(self, document_id: int) -> list[Passage]:
        with self._reading() as db:
            return [_passage(r) for r in db.execute(
                "SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal", (int(document_id),))]

    def passage(self, cite_id: str) -> Passage | None:
        with self._reading() as db:
            row = db.execute("SELECT * FROM chunks WHERE cite_id = ?", (str(cite_id),)).fetchone()
        return _passage(row) if row is not None else None

    def segments(self, document_id: int) -> list[Segment]:
        """The stored extracted text of a document, page by page."""
        with self._reading() as db:
            return [Segment(r["page"], r["text"],
                            tuple(Paragraph(*p) for p in json.loads(r["paragraphs"])))
                    for r in db.execute("SELECT page, text, paragraphs FROM segments"
                                        " WHERE document_id = ? ORDER BY segment",
                                        (int(document_id),))]

    def counts(self) -> tuple[int, int]:
        with self._reading() as db:
            return (db.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                    db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def source_file(self, document: Document) -> Path:
        """The stored copy of the document (the file the researcher added)."""
        return self.folder / SOURCES / document.stored_name

    def outdated(self) -> list[Document]:
        """Documents read by another chunker version (``reindex`` them)."""
        return [d for d in self.documents() if d.chunker != CHUNKER]

    # ----------------------------------------------------------- adding
    def add_document(self, path: Path | str | None = None, *, data: bytes | None = None,
                     file_name: str | None = None, title: str | None = None,
                     version_label: str = "", language: str | None = None, ocr: bool = False,
                     ocr_language: str = "eng", progress=None, cancel=None) -> AddOutcome:
        """Add one document the researcher chose (a path, or ``data`` with its
        ``file_name``). The same bytes are never added twice (SHA-256): the
        document already in the library is returned with ``duplicate``.
        Nothing is stored unless the whole document was read and indexed."""
        if data is None:
            if path is None:
                raise LibraryError("unreadable")
            source = Path(path)
            file_name = file_name or source.name
            try:
                size = source.stat().st_size
            except OSError as error:
                raise LibraryError("missing", str(error), name=source.name) from error
            if size > MAX_BYTES:
                raise LibraryError("too_large", size=size, limit=MAX_BYTES)
            data = source.read_bytes()
            source_path = str(source)
        else:
            file_name = file_name or "document"
            source_path = file_name
        file_name = Path(str(file_name)).name
        kind = SUFFIX_TYPES.get(Path(file_name).suffix.lower())
        if kind is None:
            raise LibraryError("unsupported", name=file_name)
        if not data:
            raise LibraryError("empty", name=file_name)
        if len(data) > MAX_BYTES:
            raise LibraryError("too_large", size=len(data), limit=MAX_BYTES)
        digest = sha256_bytes(data)
        with self._reading() as db:
            row = db.execute(self._DOCUMENTS + " WHERE d.sha256 = ?", (digest,)).fetchone()
        if row is not None:
            existing = _document(row)
            return AddOutcome(existing, True, existing.passages)
        if language is not None and language not in LANGUAGES:
            raise LibraryError("language", language=language)
        extracted = extract(data, kind, ocr=ocr, ocr_language=ocr_language, progress=progress,
                            cancel=cancel)
        drafts = chunk(extracted.segments, extracted.title)
        if not drafts:
            raise LibraryError("no_text", name=file_name,
                               pages=[n for key, v in extracted.notes for n in v.get("pages", [])])
        _check(cancel)
        stored_name = digest + Path(file_name).suffix.lower()
        target = self.folder / SOURCES / stored_name
        written = False
        if not target.exists():
            _atomic_write(target, data)
            written = True
        detected = language or detect_language(" ".join(s.text for s in extracted.segments))
        notes = list(extracted.notes)
        try:
            with self._transaction() as db:
                label = version_label.strip()[:40]
                same = db.execute("SELECT id, version_label FROM documents WHERE file_name = ?"
                                  " ORDER BY id", (file_name,)).fetchall()
                if same and not label:
                    label = f"v{len(same) + 1}"
                    for earlier in same:
                        if not earlier["version_label"]:
                            db.execute("UPDATE documents SET version_label = 'v1' WHERE id = ?",
                                       (earlier["id"],))
                    notes.append(("versioned", {"label": label, "earlier": len(same)}))
                key = self._key(db, digest)
                stamp = now()
                cursor = db.execute(
                    "INSERT INTO documents (doc_key, title, file_name, sha256, size, type,"
                    " language, version_label, page_count, imported_at, source_path,"
                    " stored_name, ocr_pages, ocr_language, chunker, indexed_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, (title or "").strip()[:200] or extracted.title or _title_from(file_name),
                     file_name, digest, len(data), kind, detected, label, extracted.page_count,
                     stamp, source_path, stored_name, json.dumps(list(extracted.ocr_pages)),
                     ocr_language if extracted.ocr_pages else "", CHUNKER, stamp))
                document_id = cursor.lastrowid
                self._store(db, document_id, key, extracted.segments, drafts, progress)
        except BaseException:
            if written:
                target.unlink(missing_ok=True)
            raise
        return AddOutcome(self.document(document_id), False, len(drafts), tuple(notes))

    def _key(self, db: sqlite3.Connection, digest: str) -> str:
        for length in (8, 10, 12, 16, 64):
            key = "D" + digest[:length].upper()
            if db.execute("SELECT 1 FROM documents WHERE doc_key = ?", (key,)).fetchone() is None:
                return key
        raise LibraryError("unreadable")

    def _store(self, db, document_id: int, key: str, segments: list[Segment],
               drafts: list[Draft], progress=None) -> None:
        db.executemany(
            "INSERT INTO segments (document_id, segment, page, text, paragraphs)"
            " VALUES (?, ?, ?, ?, ?)",
            [(document_id, i, s.page, s.text,
              json.dumps([[p.start, p.end, p.level] for p in s.paragraphs]))
             for i, s in enumerate(segments)])
        db.executemany(
            "INSERT INTO chunks (document_id, ordinal, segment, page, section, text,"
            " start_offset, end_offset, cite_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(document_id, d.ordinal, d.segment, d.page, d.section, d.text, d.start, d.end,
              f"{key}-{d.locator}") for d in drafts])
        if progress is not None:
            progress("index", len(drafts), len(drafts))
        self._index_document(db, document_id)

    # ------------------------------------------------------- maintenance
    def remove_document(self, document_id: int) -> Document:
        """Remove a document: its passages, their index rows, its extracted
        text and its stored copy. One action; the file the researcher added
        from stays where it was."""
        document = self.document(document_id)
        with self._transaction() as db:
            self._unindex_document(db, document.id)
            db.execute("DELETE FROM documents WHERE id = ?", (document.id,))
        self.source_file(document).unlink(missing_ok=True)
        return document

    def reindex(self, document_id: int, *, progress=None, cancel=None,
                ocr: bool | None = None, ocr_language: str | None = None) -> Document:
        """Read one document again from its stored copy (a new chunker, or OCR
        wanted now). Pages read with OCR before keep their recognised text
        unless ``ocr`` asks for OCR again. Same text, same cite IDs."""
        document = self.document(document_id)
        try:
            data = self.source_file(document).read_bytes()
        except OSError as error:
            raise LibraryError("missing", str(error), name=document.file_name) from error
        if sha256_bytes(data) != document.sha256:
            raise LibraryError("changed", name=document.file_name)
        previous = {segment.page: segment for segment in self.segments(document.id)}
        redo_ocr = bool(ocr)
        extracted = extract(data, document.type, ocr=redo_ocr,
                            ocr_language=ocr_language or document.ocr_language or "eng",
                            progress=progress, cancel=cancel)
        ocr_pages = set(extracted.ocr_pages)
        if not redo_ocr:
            for number in document.ocr_pages:
                if number in previous and 1 <= number <= len(extracted.segments):
                    extracted.segments[number - 1] = previous[number]
                    ocr_pages.add(number)
        drafts = chunk(extracted.segments, extracted.title)
        if not drafts:
            raise LibraryError("no_text", name=document.file_name, pages=[])
        _check(cancel)
        with self._transaction() as db:
            self._unindex_document(db, document.id)
            db.execute("DELETE FROM chunks WHERE document_id = ?", (document.id,))
            db.execute("DELETE FROM segments WHERE document_id = ?", (document.id,))
            db.execute("UPDATE documents SET page_count = ?, ocr_pages = ?, ocr_language = ?,"
                       " chunker = ?, indexed_at = ? WHERE id = ?",
                       (extracted.page_count, json.dumps(sorted(ocr_pages)),
                        (ocr_language or document.ocr_language) if ocr_pages else "",
                        CHUNKER, now(), document.id))
            self._store(db, document.id, document.key, extracted.segments, drafts, progress)
        return self.document(document.id)

    def reindex_all(self, *, progress=None, cancel=None, only_outdated: bool = False) -> int:
        """Read every document again (or only ``outdated()`` ones); the count."""
        targets = self.outdated() if only_outdated else self.documents()
        for index, document in enumerate(targets, start=1):
            _check(cancel)
            self.reindex(document.id, cancel=cancel)
            if progress is not None:
                progress("document", index, len(targets))
        return len(targets)

    def rebuild_index(self) -> None:
        with self._transaction() as db:
            self._build_index(db)

    def integrity(self) -> list[str]:
        """Problems of the index against the stored passages (empty = none)."""
        problems = []
        with self._transaction() as db:
            if self.backend == "fts5":
                try:
                    db.execute("INSERT INTO chunk_index (chunk_index, rank)"
                               " VALUES ('integrity-check', 1)")
                except sqlite3.DatabaseError as error:
                    problems.append(f"fts5: {error}")
            else:
                orphans = db.execute("SELECT COUNT(*) FROM postings WHERE chunk_id NOT IN"
                                     " (SELECT id FROM chunks)").fetchone()[0]
                if orphans:
                    problems.append(f"{orphans} postings without a passage")
                for row in db.execute("SELECT id, text, tokens FROM chunks").fetchall():
                    expected = len(tokens(self._search_text(row["text"]), self.diacritics))
                    if expected != row["tokens"]:
                        problems.append(f"passage {row['id']} is not indexed")
        return problems

    def index_rows(self, document_id: int | None = None) -> int:
        """Index rows of a document's passages (or of all): FTS5 rows that a
        search can reach, or posting lists."""
        with self._reading() as db:
            if self.backend == "fts5":
                if document_id is None:
                    return db.execute("SELECT COUNT(*) FROM chunk_index").fetchone()[0]
                ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE document_id = ?",
                                                (int(document_id),))]
                # Rows of the index itself (not of the content view): the
                # docsize shadow table has one row per indexed passage.
                return sum(db.execute("SELECT COUNT(*) FROM chunk_index_docsize WHERE id = ?",
                                      (i,)).fetchone()[0] for i in ids)
            if document_id is None:
                return db.execute("SELECT COUNT(DISTINCT chunk_id) FROM postings").fetchone()[0]
            return db.execute("SELECT COUNT(DISTINCT p.chunk_id) FROM postings p JOIN chunks c"
                              " ON c.id = p.chunk_id WHERE c.document_id = ?",
                              (int(document_id),)).fetchone()[0]

    # ------------------------------------------------------------ search
    def terms(self, query: str) -> tuple[QueryTerm, ...]:
        return query_terms(query, mode=self.query_mode, fold=self.fold, trigram=self.trigram)

    def search(self, query: str, *, types=(), language: str | None = None,
               since: str | None = None, until: str | None = None,
               limit: int = 10) -> SearchResult:
        """Passages matching ``query``, best first (BM25). Filters: document
        ``types``, ``language``, and the date it was added (``since``
        inclusive, ``until`` exclusive, ISO dates). Offline: no network."""
        terms = self.terms(query)
        filters = {key: value for key, value in (("types", tuple(types or ())),
                                                 ("language", language), ("since", since),
                                                 ("until", until)) if value}
        if not terms:
            return SearchResult(query, terms, (), 0, self.backend, filters)
        where, args = self._filters(types, language, since, until)
        limit = max(1, min(int(limit), 200))
        with self._reading() as db:
            if self.backend == "fts5":
                rows, total = self._fts_search(db, terms, where, args, limit)
            else:
                rows, total = self._python_search(db, terms, where, args, limit)
        hits = tuple(Hit(rank, _passage(row), _hit_document(row), score, snippet, terms)
                     for rank, (row, score, snippet) in enumerate(rows, start=1))
        return SearchResult(query, terms, hits, total, self.backend, filters)

    @staticmethod
    def _filters(types, language, since, until) -> tuple[str, list]:
        clauses, args = [], []
        types = [t for t in (types or ()) if t in TYPES]
        if types:
            clauses.append("d.type IN (%s)" % ",".join("?" * len(types)))
            args += types
        if language:
            clauses.append("d.language = ?")
            args.append(language)
        if since:
            clauses.append("d.imported_at >= ?")
            args.append(str(since))
        if until:
            clauses.append("d.imported_at < ?")
            args.append(str(until))
        return (" AND " + " AND ".join(clauses)) if clauses else "", args

    _COLUMNS = ("c.*, d.doc_key, d.title, d.file_name, d.sha256, d.size, d.type, d.language,"
                " d.version_label, d.page_count, d.imported_at, d.source_path, d.stored_name,"
                " d.ocr_pages, d.ocr_language, d.chunker, d.indexed_at")

    def _fts_search(self, db, terms, where, args, limit):
        expression = match_expression(terms)
        sql = (f"SELECT {self._COLUMNS}, d.id AS doc_id, bm25(chunk_index) AS score,"
               f" snippet(chunk_index, 0, ?, ?, ?, {SNIPPET_TOKENS}) AS snip"
               " FROM chunk_index JOIN chunks c ON c.id = chunk_index.rowid"
               " JOIN documents d ON d.id = c.document_id"
               f" WHERE chunk_index MATCH ?{where} ORDER BY score, c.id LIMIT ?")
        rows = db.execute(sql, [MARK_OPEN, MARK_CLOSE, ELLIPSIS, expression, *args,
                                limit]).fetchall()
        total = db.execute("SELECT COUNT(*) FROM chunk_index JOIN chunks c ON c.id ="
                           " chunk_index.rowid JOIN documents d ON d.id = c.document_id"
                           f" WHERE chunk_index MATCH ?{where}", [expression, *args]).fetchone()[0]
        found = []
        for row in rows:
            snippet = row["snip"] or ""
            if self.fold:
                snippet = _restore_snippet(snippet, row["text"])
            found.append((row, -float(row["score"]), snippet))
        return found, total

    def _python_search(self, db, terms, where, args, limit):
        """BM25 exactly as FTS5 computes it (``fts5_aux.c``): IDF from all
        passages, floored at 1e-6; k1 = 1.2, b = 0.75; a prefix term counts
        every token it begins."""
        total_rows, total_tokens = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(tokens), 0) FROM chunks").fetchone()
        if not total_rows:
            return [], 0
        average = total_tokens / total_rows
        scores: dict[int, float] = {}
        for term in terms:
            text = fold_token(term.text, self.diacritics)
            if term.prefix:
                upper = text[:-1] + chr(ord(text[-1]) + 1)
                rows = db.execute("SELECT chunk_id, SUM(tf) FROM postings WHERE term >= ?"
                                  " AND term < ? GROUP BY chunk_id", (text, upper)).fetchall()
            else:
                rows = db.execute("SELECT chunk_id, tf FROM postings WHERE term = ?",
                                  (text,)).fetchall()
            if not rows:
                continue
            idf = math.log((total_rows - len(rows) + 0.5) / (len(rows) + 0.5))
            if idf <= 0.0:
                idf = 1e-6
            lengths = dict(db.execute(
                "SELECT id, tokens FROM chunks WHERE id IN (%s)" % ",".join("?" * len(rows)),
                [r[0] for r in rows]).fetchall())
            for chunk_id, frequency in rows:
                length = lengths.get(chunk_id, 0)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + idf * (
                    frequency * (K1 + 1.0) / (frequency + K1 * (1 - B + B * length / average)))
        if not scores:
            return [], 0
        ids = list(scores)
        allowed = {r[0] for r in db.execute(
            "SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id"
            " WHERE c.id IN (%s)%s" % (",".join("?" * len(ids)), where), [*ids, *args])}
        ranked = sorted((i for i in ids if i in allowed), key=lambda i: (-scores[i], i))
        found = []
        for chunk_id in ranked[:limit]:
            row = db.execute(f"SELECT {self._COLUMNS}, d.id AS doc_id FROM chunks c JOIN"
                             " documents d ON d.id = c.document_id WHERE c.id = ?",
                             (chunk_id,)).fetchone()
            found.append((row, scores[chunk_id],
                          python_snippet(row["text"], terms, diacritics=self.diacritics,
                                         fold=self.fold)))
        return found, len(ranked)

    def explain(self, hit: Hit, result: SearchResult) -> Explanation:
        """Why ``hit`` is in ``result``: the query words it contains, how
        often, the ones it lacks, its rank and score, the filters."""
        counts = term_counts(hit.passage.text, hit.terms, diacritics=self.diacritics,
                             fold=self.fold, trigram=self.trigram)
        matched = tuple((term.shown, n) for term, n in counts if n)
        missing = tuple(term.shown for term, n in counts if not n)
        return Explanation(hit.rank, result.total, hit.score, result.backend, matched, missing,
                           dict(result.filters))

    # ---------------------------------------------------------- viewing
    def render_page(self, document: Document, page: int, **options) -> bytes:
        if document.type != "pdf":
            raise LibraryError("no_page", page=page)
        try:
            data = self.source_file(document).read_bytes()
        except OSError as error:
            raise LibraryError("missing", str(error), name=document.file_name) from error
        return render_pdf_page(data, int(page), **options)[0]

    # -------------------------------------------------------- AI audit
    def record_transfer(self, *, provider: str, model: str, cite_ids, tokens: int,
                        outcome: str) -> None:
        """Which passages went to an AI provider (cite IDs, never the text)."""
        with self._transaction() as db:
            db.execute("INSERT INTO ai_transfers (at, provider, model, cite_ids, tokens, outcome)"
                       " VALUES (?, ?, ?, ?, ?, ?)",
                       (now(), str(provider)[:40], str(model)[:200],
                        json.dumps(sorted(map(str, cite_ids))), int(tokens), str(outcome)[:40]))

    def transfers(self) -> list[dict]:
        with self._reading() as db:
            return [dict(r) | {"cite_ids": json.loads(r["cite_ids"])} for r in db.execute(
                "SELECT * FROM ai_transfers ORDER BY id")]


def _hit_document(row: sqlite3.Row) -> Document:
    """The document of a search row (passage columns joined with its document's)."""
    return Document(row["doc_id"], row["doc_key"], row["title"], row["file_name"], row["sha256"],
                    row["size"], row["type"], row["language"], row["version_label"],
                    row["page_count"], row["imported_at"], row["source_path"],
                    row["stored_name"], tuple(json.loads(row["ocr_pages"] or "[]")),
                    row["ocr_language"], row["chunker"], row["indexed_at"])


# ============================================================= snippets
def term_counts(text: str, terms, *, diacritics: int = 2, fold: bool = True,
                trigram: bool = False) -> list[tuple[QueryTerm, int]]:
    """How often each query term occurs in ``text`` (as the index matches it)."""
    source = fold_yo(text) if fold else text
    if trigram:
        lowered = source.lower()
        return [(term, lowered.count(term.text.lower())) for term in terms]
    found = tokens(source, diacritics)
    result = []
    for term in terms:
        wanted = fold_token(term.text, diacritics)
        result.append((term, sum(1 for t in found if (t.startswith(wanted) if term.prefix
                                                      else t == wanted))))
    return result


def python_snippet(text: str, terms, *, diacritics: int = 2, fold: bool = True,
                   size: int = SNIPPET_TOKENS) -> str:
    """The window of ``size`` words with the most distinct query terms, the
    matched words marked (the fallback's snippet)."""
    spans = token_spans(fold_yo(text) if fold else text, diacritics)
    if not spans:
        return text[:240]
    wanted = [(fold_token(t.text, diacritics), t.prefix) for t in terms]

    def which(token: str) -> int:
        for index, (term, prefix) in enumerate(wanted):
            if (token.startswith(term) if prefix else token == term):
                return index
        return -1

    matches = [which(token) for _, _, token in spans]
    best, best_key = 0, (-1, -1)
    for start in range(max(1, len(spans) - size + 1)):
        window = matches[start:start + size]
        key = (len({m for m in window if m >= 0}), sum(1 for m in window if m >= 0))
        if key > best_key:
            best, best_key = start, key
    last = min(len(spans), best + size) - 1
    a, b = spans[best][0], spans[last][1]
    out, position = [], a
    for index in range(best, last + 1):
        start, end, _ = spans[index]
        if matches[index] >= 0:
            out += [text[position:start], MARK_OPEN, text[start:end], MARK_CLOSE]
            position = end
    out.append(text[position:b])
    return (ELLIPSIS if best > 0 else "") + "".join(out) + (ELLIPSIS if last < len(spans) - 1
                                                             else "")


def _restore_snippet(snippet: str, original: str) -> str:
    """FTS5 reads the ё-folded text; put the passage's own letters back
    (folding keeps every position)."""
    if "ё" not in original and "Ё" not in original:
        return snippet
    folded = fold_yo(original)
    body, head, tail = snippet, "", ""
    if body.startswith(ELLIPSIS) and not folded.startswith(ELLIPSIS):
        head, body = ELLIPSIS, body[len(ELLIPSIS):]
    if body.endswith(ELLIPSIS) and not folded.endswith(ELLIPSIS):
        tail, body = ELLIPSIS, body[:-len(ELLIPSIS)]
    plain = body.replace(MARK_OPEN, "").replace(MARK_CLOSE, "")
    at = folded.find(plain)
    if at < 0:
        return snippet
    out, index = [], at
    for char in body:
        if char in (MARK_OPEN, MARK_CLOSE):
            out.append(char)
        else:
            out.append(original[index])
            index += 1
    return head + "".join(out) + tail


def snippet_parts(snippet: str) -> list[tuple[str, bool]]:
    """A snippet as (text, matched) pieces for the interface."""
    parts: list[tuple[str, bool]] = []
    for piece in re.split(f"({re.escape(MARK_OPEN)}.*?{re.escape(MARK_CLOSE)})", snippet):
        if not piece:
            continue
        if piece.startswith(MARK_OPEN) and piece.endswith(MARK_CLOSE):
            parts.append((piece[1:-1], True))
        else:
            parts.append((piece.replace(MARK_OPEN, "").replace(MARK_CLOSE, ""), False))
    return parts


def plain_snippet(snippet: str) -> str:
    return " ".join(snippet.replace(MARK_OPEN, "").replace(MARK_CLOSE, "").split())


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
