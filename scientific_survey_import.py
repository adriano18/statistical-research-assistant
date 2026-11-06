"""Conservative scientific Word/PDF questionnaire import with version isolation.

This module does NOT validate a published instrument, score respondents,
contact external services, run OCR, or distribute copyrighted test content.
The reader produces candidate instruments with source context and a *proposed*
scoring key that requires explicit researcher approval before draft use.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
import re
import shutil
import subprocess

from binary_responses import (
    BinaryScale, expand_with_legend, legend_labels, match_header,
    match_instruction, split_row, strip_noisy_row_pair,
)
from response_scales import (
    codes_line, match_legend_header, match_scale_header,
    normalize_tokens, parse_code_legend, parse_legend, split_row_tokens,
    strip_trailing_scale_tokens,
)
from survey_storage import validate_questions

MAX_BYTES = 20_000_000
MAX_PAGES = 80
MAX_QUESTIONS = 200
MAX_NON_ITEMS = 500

LEGACY_DOC_ADVICE = ("Open the file in Word or LibreOffice and save it as .docx or PDF, "
                     "then import that file.")
LEGACY_DOC_UNREADABLE = "Legacy Word .doc files cannot be read on this computer. " + LEGACY_DOC_ADVICE
LEGACY_DOC_FAILED = ("This legacy Word .doc file could not be converted on this computer. "
                     + LEGACY_DOC_ADVICE)


class LegacyDocUnavailable(ValueError):
    """A legacy Word .doc cannot be converted to text here (no converter,
    typical for a packaged Windows build, or the converter failed)."""


class NoQuestionsFound(ValueError):
    """No numbered questionnaire items; carries what the document showed."""

    def __init__(self, message: str, *, non_items=(), expected_count: int | None = None,
                 image_pages=(), ocr_language: str = ""):
        super().__init__(message)
        self.non_items = tuple(non_items)
        self.expected_count = expected_count
        self.image_pages = tuple(image_pages)
        self.ocr_language = ocr_language

NUMBERED = re.compile(
    r"^\s*(?:[_\s]*)(\*?)\s*(\d{1,3}|[lI])\s*([.):]|(?=\s{2,}))\s*(.+)$"
)
CHOICE = re.compile(
    r"^\s*(?:[A-Ha-h][.)]|[□☐◯○●•]|[-–]|\[\s*\])\s*(.{1,120})$"
)
NUMBER_LABEL = re.compile(
    r"(?<!\w)(-?\d{1,2})\s*[-–]\s*([A-Za-z][A-Za-z ]{1,35}?)"
    r"(?=\s+-?\d{1,2}\s*[-–]|\s*$)"
)
MULTIPLE = re.compile(
    r"(?:choose|select|tick)\s+all|multiple answers|"
    r"выберите все|несколько вариантов|atzīmējiet visus", re.I
)
SECTION = re.compile(r"^Section\s+([A-Z])\s*[:.-]\s*(.+)", re.I)
STOP = re.compile(
    r"^(?:scoring|figuring your .* score|references|"
    r"abstracts of selected related articles|"
    r"representative studies using scale|"
    r"tips to help improve|your score)\s*:?\s*$", re.I
)
SCALE_START = re.compile(r"^(?:scale|the perceived stress questionnaire)\s*:\s*$", re.I)
VALID_HEADINGS = (
    (re.compile(r"^UCLA LONELINESS SCALE VERSION 3$", re.I),
     "UCLA Loneliness Scale — Version 3"),
    (re.compile(r"^REVISED UCLA LONELINESS SCALE$", re.I),
     "Revised UCLA Loneliness Scale"),
    (re.compile(r"^UCLA LONELINESS SCALE$", re.I),
     "UCLA Loneliness Scale — original"),
    (re.compile(r"^DIFFERENTIAL LONELINESS SCALE(?:\s*\(DLS\))?$", re.I),
     "Differential Loneliness Scale"),
    (re.compile(r"^INVENTORY OF INTERPERSONAL PROBLEMS(?:\s*\(IIP\))?$", re.I),
     "Inventory of Interpersonal Problems"),
    (re.compile(r"^INVENTORY OF INTERPERSONAL PROBLEMS CIRCUMPLEX SCALES(?:\s*\(IIP-C\))?$", re.I),
     "Inventory of Interpersonal Problems — Circumplex"),
    (re.compile(r"^UCLA Loneliness Scale\s*[–—-]\s*Questionnaire.*$", re.I),
     "UCLA Loneliness Scale — short questionnaire (version unverified)"),
    (re.compile(r"^Perceived Stress Questionnaire\s*\(PSQ\)$", re.I),
     "Perceived Stress Questionnaire"),
    (re.compile(r"^Perceived Stress Scale$", re.I),
     "Perceived Stress Scale — version unverified"),
    (re.compile(r"^Stress Questionnaire$", re.I),
     "Stress Questionnaire — version unverified"),
    (re.compile(r"^RESEARCH QUESTIONNAIRE$", re.I),
     "Research questionnaire — version unverified"),
)


@dataclass(frozen=True)
class Candidate:
    number: int
    question: dict
    page: int
    excerpt: str
    confidence: str  # "review", "low"
    notes: tuple[str, ...] = ()
    # Stable link to the instrument's shared response scale (ResponseScheme.id)
    # and to the reconstructed matrix row ("<matrix id>:<row id>"), if any.
    scheme_id: str | None = None
    matrix_row: str | None = None


@dataclass(frozen=True)
class ProposedScoring:
    code_labels: tuple[tuple[str, str], ...] = ()
    reverse_numbers: tuple[int, ...] = ()
    formula_hint: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResponseFormat:
    """Source evidence for a shared binary answer format (no scoring)."""
    kind: str                       # "true_false" | "yes_no"
    labels: tuple[str, str]         # as printed, e.g. ("T", "F")
    printed: str                    # source text, e.g. "T / F"
    evidence: str                   # "row" | "header" | "instruction"
    page: int
    applied_to: tuple[int, ...] = ()    # item numbers converted on import
    candidates: tuple[int, ...] = ()    # text items a reviewer may convert


@dataclass(frozen=True)
class ResponseScheme:
    """A response scale shared by several items of ONE instrument version.

    Labels are as documented; ``codes`` only as printed (``None`` if not).
    Nothing is scored until the researcher confirms the structure, then
    (separately) the numeric codes and the reverse-keyed items.
    """
    id: str
    labels: tuple[str, ...]
    printed: tuple[str, ...]
    codes: tuple[str | None, ...]
    evidence: str                  # "header" | "row" | "matrix" | "codebook"
    page: int
    source_text: str
    items: tuple[int, ...]         # item numbers detected on this scale
    reverse_items: tuple[int, ...] = ()
    reverse_evidence: str = ""
    matrix_id: str | None = None
    issues: tuple[str, ...] = ()
    structure_confirmed: bool = False
    codes_confirmed: bool = False
    reverse_confirmed: bool = False

    @property
    def size(self) -> int:
        return len(self.labels)

    def label_problems(self) -> tuple[str, ...]:
        problems = []
        if not 2 <= len(self.labels) <= 11:
            problems.append("A shared scale needs 2–11 categories.")
        if any(not label.strip() for label in self.labels):
            problems.append("Every category needs a label.")
        if any(re.fullmatch(r"-?\d+", label.strip()) for label in self.labels if label.strip()):
            problems.append("Category labels are only numbers; enter the documented wording.")
        if self.printed and self.labels == self.printed and any(
            re.fullmatch(r"[A-ZА-Я]{1,3}", p) for p in self.printed
        ):
            problems.append("Abbreviations are not defined in this document; enter the labels.")
        if len({label.strip().casefold() for label in self.labels}) != len(self.labels):
            problems.append("Category labels must be distinct.")
        return tuple(problems)

    @property
    def has_codes(self) -> bool:
        return bool(self.codes) and all(code not in (None, "") for code in self.codes)


@dataclass(frozen=True)
class InstrumentCandidate:
    title: str
    questions: tuple[Candidate, ...]
    scoring: ProposedScoring
    warnings: tuple[str, ...]
    first_page: int
    response_formats: tuple[ResponseFormat, ...] = ()
    schemes: tuple[ResponseScheme, ...] = ()
    # Abbreviation legend printed for THIS instrument (e.g. O = Often).
    scale_legend: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ScientificDocumentReview:
    source_name: str
    instruments: tuple[InstrumentCandidate, ...]
    warnings: tuple[str, ...]
    page_count: int
    image_only_pages: tuple[int, ...] = ()
    # Optional Stage 32 evidence (ocr_layout.SpatialEvidence) and matrix
    # proposals (matrix_reconstruction.MatrixProposal). Both are review
    # aids only; they never approve scoring, rights or wording.
    spatial: object | None = None
    matrices: tuple = ()
    # Import integrity: numbered lines kept out because they look like
    # bibliography entries ((page, text)), the item count the document's
    # own text states, and the OCR language its letters suggest.
    non_items: tuple[tuple[int, str], ...] = ()
    expected_count: int | None = None
    ocr_language: str = ""


def _title(line: str) -> str | None:
    for expression, label in VALID_HEADINGS:
        if expression.fullmatch(line.strip()):
            return label
    return None


def _clean(line: str) -> str:
    return " ".join(str(line).replace("\x00", " ").split()).strip()


def _numbered(line: str, expected: int | None) -> tuple[int, str, bool] | None:
    """(number, item text, starred) of a numbered item line, or None.

    A numbered bibliography entry is never an item, wherever it appears.
    """
    found = _numbered_line(line, expected)
    if found is not None and _reference_like(found[1]):
        return None
    return found


def _numbered_line(line: str, expected: int | None) -> tuple[int, str, bool] | None:
    # Table cells from antiword: |14 | Question? | [ ] Yes |
    if line.lstrip().startswith("|"):
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and re.fullmatch(r"\d{1,3}\*?", cells[0]) and len(cells) >= 2:
            text = cells[1]
            if len(text) >= 5:
                num = int(cells[0].rstrip("*"))
                return num, text, cells[0].endswith("*")
    match = NUMBERED.match(line)
    if not match and expected is not None and expected >= 2:
        # OCR often reads "4." as "4," inside a running sequence.
        comma = re.match(r"^\s*(\d{1,3}),\s+(\S.{2,})$", line)
        if comma and int(comma.group(1)) == expected:
            return expected, comma.group(2)[:300], False
    if not match:
        # Historical UCLA scans contain 4 How often... and 17, How
        # often..., while DLS item labels sometimes use "1.*".
        alternate = re.match(
            r"^\s*(\d{1,3})(?:\.\*|,|\s)\s*"
            r"(How often\b.{5,})$",
            line, re.I,
        )
        if alternate and (
            expected is None or int(alternate.group(1)) == expected
        ):
            return int(alternate.group(1)), alternate.group(2)[:300], (
                ". *" in line or ".*" in line
            )
        return None
    raw = match.group(2)
    n = 1 if raw in ("l", "I") and expected == 1 else (
        int(raw) if raw.isdigit() else -1
    )
    if n < 1 or n > MAX_QUESTIONS:
        return None
    # Avoid references, page numbers, scale-option keys (1- Never). Inside a
    # running sequence (item 2 onwards) short items such as "Divorce" are kept.
    label = match.group(4).strip()
    in_sequence = expected is not None and expected >= 2 and n == expected
    if not in_sequence and (len(label) < 5 or (
        len(label.split()) < 3 and not label.endswith("?")
    )):
        return None
    if in_sequence and (len(label) < 3 or not re.search(r"[^\W\d_]{3}", label)):
        return None
    if expected is not None and n != expected:
        return None
    label = re.sub(r"\s+(?:[0-4]\s+){3,}[0-4]\s*$", "", label)
    label = re.sub(r"\s+(?:[OSRN]\s+){2,}[OSRN]\s*$", "", label)
    label = re.sub(r"\s+[Tt]\s+[Ff](?:\s+\S+)?\s*$", "", label)
    return n, label[:300], bool(match.group(1))


def _heading_like(line: str) -> bool:
    """A title-like line (e.g. "REVISED SYNTHETIC CONNECTEDNESS INVENTORY")."""
    words = line.split()
    if not 2 <= len(words) <= 12 or len(line) > 90:
        return False
    if line.endswith((".", "?", ":", ",", ";")) or re.match(r"^\W*\d", line):
        return False
    letters = [w for w in words if re.search(r"[^\W\d_]", w)]
    if len(letters) < 2:
        return False
    capitals = sum(1 for w in letters if w[:1].isupper())
    return line.upper() == line or capitals >= max(2, round(0.6 * len(letters)))


def _scale_or_legend_line(line: str, legend: dict | None = None) -> bool:
    return bool(
        match_scale_header(line, legend) or parse_legend(line)
        or parse_code_legend(line) or match_header(line)
    )


def _title_line(line: str) -> bool:
    return _heading_like(line) and not _scale_or_legend_line(line) and "=" not in line


# Shapes of a bibliography entry; any one of them is enough because
# questionnaire items do not carry them: a year in parentheses (not one
# that ends a question: "… election (2022)?"), a DOI, "et al.", page
# numbers, journal volume (issue) pages, Vancouver "1993;37(1):19",
# "(Eds.)", ISBN, and GOST "//" or "С. 19–32".
_REFERENCE_SHAPES = re.compile(
    r"\(\s*\d{4}[a-z]?\s*\)(?!\s*\?)"
    r"|\bdoi\b|\b10\.\d{4,9}/\S"
    r"|\bet\s+al\b|\bи\s+др\."
    r"|\bpp?\.\s*\d|\blpp\.\s*\d"
    r"|\b\d{1,4}\s*\(\s*\d{1,4}(?:\s*[-–—/]\s*\d{1,4})?\s*\)\s*[,:.]?\s*\d{1,5}\s*[-–—]\s*\d{1,5}"
    r"|\b\d{4}\s*;\s*\d{1,4}\s*(?:\(\s*[\d-]{1,9}\s*\))?\s*:\s*\d{1,5}"
    r"|\((?:eds?|hrsg|red)\.?\)|\bISBN\b|\s//\s|\bС\.\s*\d{1,5}\s*[-–—]\s*\d{1,5}",
    re.I,
)
_SURNAME = r"[A-ZÀ-ÖØ-ÞĀ-ŽА-ЯЁ][^\W\d_]+(?:[-'’][^\W\d_]+)*"
_INITIALS = r"(?:[A-ZÀ-ÖØ-ÞĀ-ŽА-ЯЁ]\.\s*(?:-\s*[A-ZÀ-ÖØ-ÞĀ-ŽА-ЯЁ]\.\s*)?){1,3}"
_ENTRY_NUMBER = r"^\W*(?:\[\d{1,3}\]|\d{1,3}[.)])?\s*"
# Author lists at the start of an entry: APA "Surname, A. B., & …" or
# "Surname, A. (2000)", GOST "Surname A. B., Other C." and Vancouver
# "Surname AB, Other C." (initials end the author list with a period).
_AUTHOR_LIST = re.compile(
    rf"{_ENTRY_NUMBER}{_SURNAME},\s+{_INITIALS}(?:,|&|\band\b|\bun\b|\bи\b|\(|$)"
    rf"|{_ENTRY_NUMBER}{_SURNAME}\s+{_INITIALS},\s*{_SURNAME}\s+{_INITIALS}"
    rf"|{_ENTRY_NUMBER}{_SURNAME}\s+[A-Z]{{1,3}}(?:,\s*{_SURNAME}\s+[A-Z]{{1,3}})+\.(?:\s|$)"
)
# A numbered entry as printed in a list: "1.", "1)", "1:", "[1]" or "1   ".
_NUMBERED_ENTRY = re.compile(r"^\s*(?:\[\d{1,3}\]|\d{1,3}\s*[.):]|\d{1,3}(?=\s{2,}))\s*\S")
_REFERENCES_HEADING = re.compile(
    r"(?:(?:list\s+of|cited|notes\s+and)\s+)?(?:references?|bibliography|literature|sources)"
    r"(?:\s+(?:cited|list|and\s+notes))?|works\s+cited"
    r"|(?:izmantot[āa]\s+|citēt[āa]\s+)?literat[ūu]r(?:a|as\s+saraksts)(?:\s+un\s+avoti)?"
    r"|(?:izmantotie\s+)?avoti"
    r"|(?:список\s+(?:использованной\s+|цитируемой\s+)?)?литератур[аы]"
    r"|использованная\s+литература|библиография|(?:список\s+)?источник(?:и|ов)",
    re.I,
)


def _reference_like(line: str) -> bool:
    """True for a bibliography-shaped line (citation, not a question)."""
    return bool(_REFERENCE_SHAPES.search(line) or _AUTHOR_LIST.search(line))


def _references_heading(line: str) -> bool:
    """A references section heading, also decorated ("— References —",
    "6. REFERENCES:", "R E F E R E N C E S") and in Latvian or Russian."""
    text = _clean(line)
    if not text or len(text) > 60:
        return False
    text = re.sub(r"\s*\(\s*(?:continued|cont\.?)\s*\)\W*$", "", text, flags=re.I)
    core = re.sub(r"^[\W_]*(?:(?:\d{1,2}(?:\.\d{1,2})*|[IVX]{1,4})[.)]?\s+)?|[\W_]+$", "", text)
    if re.fullmatch(r"(?:[^\W\d_]\s){3,}[^\W\d_]", core):
        core = core.replace(" ", "")
    return bool(_REFERENCES_HEADING.fullmatch(core))


def _resumes_questionnaire(line: str, numbered_text: str, legend: dict | None) -> bool:
    """Evidence that a references section has ended: instructions, a
    section, a response header or legend, or a numbered QUESTION that is
    not shaped like a citation."""
    if (SCALE_START.match(line) or re.match(r"instructions?\b", line, re.I)
            or SECTION.match(line) or _scale_or_legend_line(line, legend)
            or (legend and match_legend_header(line, legend))
            or len(NUMBER_LABEL.findall(line)) >= 2):
        return True
    return bool(re.match(r"\s*\d{1,3}\s*[.):]\s*\S.*\?\s*$", numbered_text)
                and not _reference_like(numbered_text))


_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100, "one": 1,
}
_COUNT = (r"(\d{1,3}|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
          r"(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine)\b)?"
          r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen"
          r"|nineteen|two|three|four|five|six|seven|eight|nine|(?:one\s+)?hundred)")
_COUNTED = (r"(?:items?|statements?|questions?|apgalvojum\w*|jautājum\w*"
            r"|пункт\w*|вопрос\w*|утверждени\w*)")
_COUNT_STATED = re.compile(
    r"\b(?:consists?|consisting|comprises?|comprising|composed|contains?|containing"
    r"|includes?|including|made\s+up|sastāv|satur|ietver|состоит|содержит|включает)"
    rf"\s+(?:of\s+|no\s+|из\s+)?(?:a\s+total\s+of\s+|kopā\s+|всего\s+)?\b{_COUNT}"
    rf"\s+(?:[\w-]+\s+){{0,2}}?{_COUNTED}(?!\w)", re.I)
_COUNT_HYPHENATED = re.compile(rf"\b{_COUNT}\s*[-‐–]\s*(?:items?|questions?|statements?)\b", re.I)
_COUNT_MENTIONED = re.compile(rf"\b{_COUNT}\s+(?:[\w-]+\s+)?{_COUNTED}(?!\w)", re.I)
# "these 4 questions" in scoring notes ("On these 4 questions, change the
# scores ...") refers to a subset just named, not to the whole form.
_SUBSET_BEFORE = re.compile(r"\b(?:first|last|next|remaining|other|additional|extra|further"
                            r"|these|those|such|šiem|šo|šie|этих|эти|этим)\s+$", re.I)
_SUBSET_AFTER = re.compile(r"\s*(?:\(|(?:are|were|is)\s+(?:reverse|reversed|positively|negatively|keyed)"
                           r"|reverse|each\b|per\b)", re.I)


def _count_value(text: str) -> int:
    if text.isdigit():
        return int(text)
    words = re.split(r"[-\s]+", text.lower())
    return 100 if "hundred" in words else sum(_NUMBER_WORDS.get(word, 0) for word in words)


def expected_item_count(texts) -> int | None:
    """The number of items the document's text says the form has, or None.

    Reads statements such as "consists of 30 items", "a 30-item scale" or
    "30 statements" (also Latvian and Russian). Sub-counts such as "the
    first 10 items", "8 items are reverse scored" or "15 items each" are
    ignored. Different counts resolve by weight (a "consists of" phrase
    counts most, then "N-item", then a plain mention), ties to the
    earliest. The file name is never used.
    """
    text = " ".join(_clean(t) for t in texts)[:400_000]
    found = [(match.start(), match.group(1), 2)
             for pattern in (_COUNT_STATED, _COUNT_HYPHENATED) for match in pattern.finditer(text)]
    found += [(match.start(), match.group(1), 1) for match in _COUNT_MENTIONED.finditer(text)
              if not _SUBSET_BEFORE.search(text[max(0, match.start() - 20):match.start()])
              and not _SUBSET_AFTER.match(text, match.end())]
    weight, first = Counter(), {}
    for position, number, points in sorted(found):
        value = _count_value(number)
        if 2 <= value <= MAX_QUESTIONS:
            weight[value] += points
            first.setdefault(value, position)
    if not weight:
        return None
    best = max(weight.values())
    return min((first[value], value) for value in weight if weight[value] == best)[1]


def _ocr_language_hint(texts) -> str:
    """Tesseract languages suggested by the letters of the document's text."""
    sample = " ".join(texts)[:200_000]
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", sample))
    latin = len(re.findall(r"[A-Za-zĀ-ž]", sample))
    latvian = len(re.findall(r"[āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ]", sample))
    if cyrillic >= 20 and cyrillic >= 0.3 * (cyrillic + latin):
        return "rus+eng"
    if latvian >= 10 and latvian >= 0.02 * latin:
        return "lav+eng"
    return "eng"


def _count_evidence(lines) -> list[str]:
    """Document text for the stated item count without the bibliography
    (prose that cites a source, "… et al. (2001) …", is kept)."""
    kept, references = [], False
    for _, raw in lines:
        line = _clean(raw)
        if not line:
            continue
        if _references_heading(line):
            references = True
            continue
        if references and not _resumes_questionnaire(line, line, None):
            continue
        references = False
        if not (_NUMBERED_ENTRY.match(line) and _reference_like(line)):
            kept.append(line)
    return kept


def _stem_title(source_name: str, preamble_lines: list[str]) -> str:
    """A heading printed just before the items, else the file name stem."""
    for line in reversed(preamble_lines[-6:]):
        if _title_line(line):
            return line[:75]
    return Path(source_name).stem[:75]


def _scoring_from_lines(
    context: list[str], codes: dict[str, str], explicit_reverse: set[int],
    star_reverse: set[int], count: int,
) -> ProposedScoring:
    # Never infer scores from instrument names (PSS, UCLA etc.).
    notes = []
    combined = " ".join(context)
    reverse = set(explicit_reverse) | set(star_reverse)
    for m in re.finditer(
        r"(?:reverse\s+(?:your\s+)?scores?\s+for\s+(?:questions|items)|"
        r"items?)\s+((?:\d{1,3}\s*[,;]?\s*(?:and\s+)?)+)"
        r"(?:\s+are\s+(?:all\s+)?reverse\s+scored)?",
        combined, re.I,
    ):
        nearby = combined[m.start():m.end()+60]
        if "reverse" in nearby.lower():
            reverse.update(int(x) for x in re.findall(r"\d{1,3}", m.group(1)))
    # "Score 5 - circled number for items 1, 7, 10" is a reverse rule too.
    for m in re.finditer(
        r"score\s+(\d{1,2})\s*[-–]\s*(?:the\s+)?circled\s+(?:number|answer)\s+"
        r"for\s+(?:items?|questions?)\s+((?:\d{1,3}\s*(?:,|and)?\s*)+)",
        combined, re.I,
    ):
        reverse.update(int(x) for x in re.findall(r"\d{1,3}", m.group(2)))
        notes.append(
            f"The source scores some items as {m.group(1)} minus the circled "
            "number (reverse keying); confirm it before applying."
        )
    if reverse and (min(reverse) < 1 or max(reverse) > count):
        notes.append("Scoring text refers to items outside this candidate; "
                     "reverse-key proposal has been suppressed.")
        reverse = set()
    if "reverse" in combined.lower() and not reverse:
        notes.append("Reverse coding is mentioned but could not be bound "
                     "safely to item numbers; review the original.")
    if "index" in combined.lower() and "raw score" in combined.lower():
        notes.append("Source discusses a transformed index; verify the "
                     "formula and version manually, do not infer cutoffs.")
    return ProposedScoring(
        code_labels=tuple(sorted(codes.items(), key=lambda x: int(x[0]))),
        reverse_numbers=tuple(sorted(reverse)),
        warnings=tuple(notes),
    )


def _read_pdf(path: Path) -> tuple[list[tuple[int, str]], int, tuple[int, ...]]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDF cannot be imported.")
    if len(reader.pages) > MAX_PAGES:
        raise ValueError("PDF exceeds the 80-page limit.")
    lines = []
    image_pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        lines += [(i, s) for s in text.splitlines()]
        # An image-backed page with no question text may hide its scale table
        # even when it has a readable footer/bibliography.
        try:
            if len(page.images):
                image_pages.append(i)
        except (ValueError, KeyError):
            pass
    return lines, len(reader.pages), tuple(image_pages)


def _read_docx(path: Path) -> tuple[list[tuple[int, str]], int, tuple[int, ...]]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    document = Document(path)
    lines = []
    for part in document.iter_inner_content():
        if isinstance(part, Paragraph):
            lines.extend((1, line) for line in part.text.splitlines())
        elif isinstance(part, Table):
            for row in part.rows:
                values = [cell.text.strip() for cell in row.cells]
                nonempty = [v for v in values if v]
                # Native table structure: a header row "No. | Statement |
                # T | F" or an item row ending in its own T / F cells.
                joined = " ".join(nonempty)
                if nonempty and match_header(joined):
                    lines.append((1, joined))
                    continue
                if len(nonempty) >= 3 and match_header(" ".join(nonempty[-2:])):
                    head = nonempty[:-2]
                    if len(head) >= 2 and re.fullmatch(r"\d{1,3}", head[0]):
                        lines.append((1, f"{head[0]}. {head[1]}"))
                        lines.extend((1, v) for v in head[2:])
                    else:
                        lines.extend((1, v) for v in head)
                    lines.append((1, " ".join(nonempty[-2:])))
                    continue
                if len(values) >= 2 and re.fullmatch(r"\d{1,3}", values[0]):
                    lines.append((1, f"{values[0]}. {values[1]}"))
                    for value in values[2:]:
                        if value:
                            lines.append((1, value))
                else:
                    for value in values:
                        if value:
                            lines.append((1, value))
    return lines, 1, ()


def _read_legacy_doc(path: Path) -> tuple[list[tuple[int, str]], int, tuple[int, ...]]:
    # The only converter is a locally installed antiword; packaged Windows
    # builds have none, so the error must say how to continue.
    binary = shutil.which("antiword")
    if not binary:
        raise LegacyDocUnavailable(LEGACY_DOC_UNREADABLE)
    try:
        result = subprocess.run(
            [binary, "-w", "140", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", timeout=12,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LegacyDocUnavailable(LEGACY_DOC_FAILED) from error
    if result.returncode or not result.stdout.strip():
        raise LegacyDocUnavailable(LEGACY_DOC_FAILED)
    return [(1, line) for line in result.stdout.splitlines()], 1, ()


def read_scientific_document(path: str | Path) -> ScientificDocumentReview:
    file = Path(path).expanduser().resolve()
    ext = file.suffix.lower()
    if ext not in (".docx", ".doc", ".pdf"):
        raise ValueError("Choose a PDF, DOCX or legacy DOC questionnaire.")
    size = file.stat().st_size
    if size < 1 or size > MAX_BYTES:
        raise ValueError("Source must be nonempty and at most 20 MB.")
    if ext == ".pdf":
        lines, pages, images = _read_pdf(file)
    elif ext == ".docx":
        lines, pages, images = _read_docx(file)
    else:
        lines, pages, images = _read_legacy_doc(file)
    return parse_scientific_lines(
        lines, file.name, page_count=pages, image_pages=images,
    )


def proposed_scheme_question(question: dict, scheme: ResponseScheme) -> dict:
    """Proposal shown for an item on a shared scale (never scored)."""
    q = dict(question)
    for name in ("options", "value_labels", "scale_id"):
        q.pop(name, None)
    q["reverse_scored"] = False
    labels = [label.strip() for label in scheme.labels]
    if not scheme.label_problems() and len(labels) <= 12:
        q["kind"] = "single_choice"
        q["options"] = labels
    else:
        q["kind"] = "short_text"  # labels still missing — blocked until reviewed
    return q


def _majority(values):
    values = [v for v in values if v]
    if not values:
        return None, 0
    best = max(set(values), key=values.count)
    return best, values.count(best)


def _build_schemes(current: dict, scoring: "ProposedScoring"):
    """Shared scales from header / legend / row-token evidence of ONE instrument."""
    schemes, assignments = [], {}
    legend = current["scale_legend"]
    codebook = current["codes"]
    rows = current["rows"]
    for key, group in current["scale_groups"].items():
        indices = [i for i, k in current["links"] if k == key]
        if len(indices) < 2:
            continue
        header = group["header"]
        tokens, agreeing = _majority([tuple(t) for t in group["tokens"]])
        issues = []
        if header is not None:
            printed = header.printed
            if header.abbreviated:
                defined = all(p in legend for p in printed)
                labels = tuple(legend[p] for p in printed) if defined else printed
                if not defined:
                    issues.append("Abbreviations " + " / ".join(printed)
                                  + " are not defined in this document; enter the labels.")
            else:
                labels = printed
            if header.uncertain and header.abbreviated:
                issues.append("OCR read the header as “" + header.text + "”; it was matched to "
                              "this document's legend (" + " / ".join(printed) + ") — verify.")
            elif header.uncertain:
                issues.append("Header label(s) " + ", ".join(f"“{u}”" for u in header.uncertain)
                              + " may be incomplete (two-line header?); check the source.")
            size = len(printed)
            source = header.text
            evidence = "header"
        else:
            printed = tokens or ()
            size = len(printed)
            source = " ".join(printed)
            evidence = "row"
            if all(re.fullmatch(r"-?\d{1,2}", t) for t in printed):
                labels = tuple(codebook.get(t, "") for t in printed)
            elif all(t in legend for t in printed):
                labels = tuple(legend[t] for t in printed)
            elif all(t in "○◯□☐●" for t in printed):
                labels = ("",) * size
            else:
                labels = printed
                issues.append("Answer letters " + " / ".join(printed)
                              + " are not defined in this document; enter the labels.")
            if not all(labels):
                issues.append("Category labels were not printed in a header; enter them.")
        codes: tuple = (None,) * size
        scale = group.get("scale")
        if scale is not None and scale.get("codes"):
            codes = tuple(scale["codes"])
        elif tokens and len(tokens) == size and all(re.fullmatch(r"-?\d{1,2}", t) for t in tokens):
            codes = tuple(tokens)
        elif codebook and len(codebook) == size:
            by_label = {v.strip().casefold(): k for k, v in codebook.items()}
            if all(l.strip().casefold() in by_label for l in labels):
                codes = tuple(by_label[l.strip().casefold()] for l in labels)
        numbers = tuple(rows[i].number for i in indices)
        odd = [rows[i].number for i, t in zip(indices, group["tokens"])
               if t and tokens and tuple(t) != tokens]
        if odd:
            issues.append("Printed answer cells differ on item(s) "
                          + ", ".join(map(str, odd[:12])) + "; check them on the source page.")
        reverse = tuple(n for n in scoring.reverse_numbers if n in numbers)
        reverse_text = next((line for line in current["context"]
                             if re.search(r"revers|circled number", line, re.I)), "")
        scheme = ResponseScheme(
            f"s{len(schemes) + 1}", tuple(labels), tuple(printed), codes, evidence,
            group["page"], source[:160], numbers, reverse, reverse_text[:200],
            issues=tuple(issues),
        )
        schemes.append(scheme)
        for i in indices:
            assignments[i] = scheme
    return schemes, assignments


def parse_scientific_lines(
    lines: list[tuple[int, str]], source_name: str, *,
    page_count: int = 1, image_pages: tuple[int, ...] = (),
) -> ScientificDocumentReview:
    if len(lines) > 30000:
        raise ValueError("Document has too many text lines.")
    instruments: list[InstrumentCandidate] = []
    document_notes = [
        "Unvalidated source: check instrument name/version, rights, "
        "translation, item wording, scoring and respondent consent.",
    ]
    if image_pages:
        document_notes.append(
            "Image-backed content on PDF page(s) "
            + ", ".join(map(str, image_pages))
            + " may include table questions the text layer does not contain; "
            "read those pages with local OCR and compare them with the source."
        )
    current = None
    # A references section: from its heading until the questionnaire
    # visibly resumes, numbered lines are bibliography, never items.
    # "title" is the zone's last title-like line (a new form may follow).
    references = {"page": None, "title": None}
    non_items: list[tuple[int, str]] = []
    # Binary answer evidence seen before the first numbered item (headers,
    # instructions and legends usually precede the items).
    preamble = {"binary": None, "hint": None, "legend": {}, "scale": None,
                "scale_legend": {}, "lines": [], "codes": {}}
    parts = 1

    def non_item(page: int, line: str) -> None:
        if len(non_items) < MAX_NON_ITEMS:
            non_items.append((page, line[:240]))

    def begin(title: str, page: int, collection=False):
        state = {
            "title": title, "page": page, "rows": [], "codes": dict(preamble["codes"]),
            "reverse": set(), "context": [], "pending": None,
            "section": "Imported questions", "capture": not collection,
            "collection": collection, "warnings": [],
            "binary": preamble["binary"], "hint": preamble["hint"],
            "legend": dict(preamble["legend"]), "formats": {},
            "scale": preamble["scale"], "scale_legend": dict(preamble["scale_legend"]),
            "buffer": [], "links": [], "scale_groups": {},
        }
        preamble.update({"binary": None, "hint": None, "legend": {}, "scale": None,
                         "scale_legend": {}, "lines": [], "codes": {}})
        return state

    def scale_link(pending):
        """Key of the shared scale this text item belongs to, or None."""
        tokens = normalize_tokens(tuple(pending.get("row_tokens") or ()))
        markers = bool(tokens) and all(t in "○◯□☐●" for t in tokens)
        scale = current["scale"]
        header = scale["header"] if scale else None
        if header is not None:
            size = len(header.printed)
            fits = not tokens or len(tokens) == size and (
                markers or [t.casefold() for t in tokens] == [p.casefold() for p in header.printed]
                or all(re.fullmatch(r"-?\d{1,2}", t) for t in tokens)
            )
            trusted = not header.abbreviated or header.defined or (
                tokens and [t.casefold() for t in tokens] == [p.casefold() for p in header.printed]
            )
            if fits and trusted:
                key = ("header", id(scale))
                current["scale_groups"].setdefault(key, {
                    "header": header, "page": scale["page"], "scale": scale,
                    "tokens": [],
                })["tokens"].append(tokens)
                return key
        if len(tokens) >= 3:
            digits = all(re.fullmatch(r"-?\d{1,2}", t) for t in tokens)
            shape = ("markers" if markers else "digits" if digits else tokens, len(tokens))
            key = ("row", shape)
            current["scale_groups"].setdefault(key, {
                "header": None, "page": pending["page"], "scale": None, "tokens": [],
            })["tokens"].append(tokens)
            return key
        return None

    def record_format(scale: BinaryScale, evidence: str, page: int, number=None):
        key = (scale.kind, scale.labels, evidence)
        entry = current["formats"].setdefault(key, {
            "scale": scale, "page": page, "applied": [], "candidates": [],
        })
        if number is not None:
            entry["applied"].append(number)
        return entry

    def binary_options(pending):
        """Options from row/shared evidence, or None. Never numeric codes."""
        scale = pending.get("binary")
        evidence = "row"
        if scale is None and current["binary"] is not None:
            scale, evidence = current["binary"]["scale"], "header"
        if scale is None:
            return None
        scale = expand_with_legend(scale, current["legend"])
        page = pending["page"] if evidence == "row" else current["binary"]["page"]
        record_format(scale, evidence, page, pending["number"])
        pending["notes"].append(
            f"Binary answers {scale.description} from "
            + ("this item's own row" if evidence == "row" else
               f"the shared header “{current['binary']['scale'].printed}” on page {page}")
            + "; labels kept as printed, no codes assigned."
        )
        return list(scale.labels)

    def finish_question():
        if current is None or current["pending"] is None:
            return
        pending = current["pending"]
        prompt = pending["prompt"].strip()
        if not prompt or len(prompt) > 300:
            current["warnings"].append(
                f"Question {pending['number']} is empty or too long and was not imported."
            )
            current["pending"] = None
            return
        opts = list(dict.fromkeys(pending["options"]))[:12]
        link = None
        if len(opts) < 2:
            binary = binary_options(pending)
            if binary:
                opts = binary
            else:
                link = scale_link(pending)
        kind = (
            "multiple_choice" if MULTIPLE.search(prompt)
            else "single_choice"
        ) if len(opts) >= 2 else "short_text"
        if len(opts) == 1:
            current["warnings"].append(
                f"Question {pending['number']} has only one detected option."
            )
        question = {
            "key": f"import_q{len(current['rows'])+1:03d}",
            "prompt": prompt, "kind": kind, "required": False,
            "section": current["section"][:80], "page": 1,
        }
        if kind in ("single_choice", "multiple_choice"):
            question["options"] = opts
        if link is not None:
            current["links"].append((len(current["rows"]), link))
        current["rows"].append(
            Candidate(pending["number"], question, pending["page"],
                      pending["excerpt"], pending["confidence"],
                      tuple(pending["notes"]))
        )
        current["pending"] = None

    def finish_instrument():
        nonlocal current
        if current is None:
            return
        finish_question()
        if current["rows"]:
            if len(current["rows"]) > MAX_QUESTIONS:
                raise ValueError("One instrument exceeds the 200-item limit.")
            # Reject bibliographic runs and numbering far from 1.
            if current["rows"][0].number != 1:
                current["warnings"].append(
                    "Candidate sequence does not begin at item 1. "
                    "It may be incomplete; verify the source."
                )
            scoring = _scoring_from_lines(
                current["context"], current["codes"],
                current["reverse"], set(), len(current["rows"]),
            )
            formats = []
            for (kind, labels, evidence), entry in current["formats"].items():
                formats.append(ResponseFormat(
                    kind, labels, entry["scale"].printed, evidence,
                    entry["page"], tuple(entry["applied"]),
                ))
            converted = {n for f in formats for n in f.applied_to}
            if converted:
                described = "; ".join(
                    f"{len(f.applied_to)} item(s) {f.labels[0]} / {f.labels[1]} "
                    f"from {'their own rows' if f.evidence == 'row' else 'a shared header'}"
                    for f in formats
                )
                current["warnings"].append(
                    f"Binary answer columns converted to labelled choices ({described}). "
                    "Labels are kept as printed; numeric 1/0 codes, answer keys "
                    "and reverse scoring are NOT applied automatically."
                )
                keyed = set(scoring.reverse_numbers) & converted
                if keyed:
                    scoring = replace(
                        scoring,
                        reverse_numbers=tuple(sorted(set(scoring.reverse_numbers) - converted)),
                        warnings=(*scoring.warnings,
                                  "Marked binary items may indicate keyed answers; "
                                  "keying is not applied — use the official manual."),
                    )
            text_items = tuple(
                r.number for r in current["rows"]
                if r.question["kind"] == "short_text"
            )
            if current["hint"] is not None and text_items and not converted:
                hint = current["hint"]["scale"]
                formats.append(ResponseFormat(
                    hint.kind, expand_with_legend(hint, current["legend"]).labels,
                    hint.printed, "instruction", current["hint"]["page"],
                    (), text_items,
                ))
                current["warnings"].append(
                    f"The instructions mention {hint.description} answers, but no "
                    f"answer columns were found. {len(text_items)} item(s) stay text "
                    "until you review and apply the binary format."
                )
            schemes, assignments = _build_schemes(current, scoring)
            rows = []
            safe_homogeneous_scale = (
                len(current["rows"]) >= 3
                and all(q.question["kind"] == "short_text"
                        for q in current["rows"])
                and not schemes
            )
            if scoring.code_labels and not safe_homogeneous_scale:
                current["warnings"].append(
                    "Numeric anchors were found in a mixed or short "
                    "questionnaire; automatic rating conversion disabled."
                )
            for index, row in enumerate(current["rows"]):
                question = dict(row.question)
                notes, scheme_id = row.notes, None
                if index in assignments:
                    scheme = assignments[index]
                    scheme_id = scheme.id
                    question = proposed_scheme_question(question, scheme)
                    notes = (*notes, f"Shared scale {scheme.id} ({' / '.join(scheme.labels) or 'labels missing'}) "
                             f"from {scheme.evidence} evidence on page {scheme.page} — "
                             "proposed, not verified.")
                elif (
                    safe_homogeneous_scale
                    and len(scoring.code_labels) >= 2
                    and question["kind"] == "short_text"
                ):
                    # Numeric rating is a *candidate* in the review.
                    question["kind"] = "rating_scale"
                    question["value_labels"] = dict(scoring.code_labels)
                    question["scale_id"] = "import_scale"
                    question["reverse_scored"] = False
                rows.append(Candidate(
                    row.number, question, row.page, row.excerpt,
                    row.confidence, notes, scheme_id,
                ))
            if schemes:
                current["warnings"].append(
                    "Shared response scale(s) detected and proposed for the linked "
                    "questions — NOT verified. Confirm each scale in Response scale "
                    "review before importing; numeric codes and reverse keys need "
                    "separate confirmation."
                )
            try:
                validate_questions([r.question for r in rows])
            except ValueError as error:
                current["warnings"].append(
                    f"Candidates must be edited before publishing: {error}"
                )
            instruments.append(InstrumentCandidate(
                current["title"], tuple(rows), scoring,
                tuple(current["warnings"]), current["page"], tuple(formats),
                tuple(schemes), tuple(sorted(current["scale_legend"].items())),
            ))
        current = None

    def item_text(raw):
        """Item text with printed answer tokens removed (binary or scale)."""
        row_text, row_scale = split_row(raw)
        if row_scale is None:
            row_text, row_scale = strip_noisy_row_pair(raw)
        numbered_text = row_text if row_scale is not None else raw
        tokens = ()
        if row_scale is None:
            header = current["scale"]["header"] if current and current["scale"] else None
            size = len(header.printed) if header else None
            if header is not None and header.abbreviated:
                stripped, removed = strip_trailing_scale_tokens(numbered_text, header.printed)
                if removed:  # tolerant copy of the header letters (OCR noise)
                    return stripped, row_scale, tuple(header.printed)
            rest, tokens = split_row_tokens(numbered_text)
            if tokens and size and len(tokens) > size:
                # "… number 2 1 2 3 4": the item's own number is text, not a code.
                rest = rest + " " + " ".join(tokens[:-size])
                tokens = tokens[-size:]
            if tokens:
                numbered_text = rest
            elif header is not None:
                stripped, removed = strip_trailing_scale_tokens(numbered_text, header.printed)
                if removed:
                    numbered_text = stripped
        return numbered_text, row_scale, tokens

    def expected_number():
        return (
            current["pending"]["number"] + 1 if current["pending"] else
            current["rows"][-1].number + 1 if current["rows"] else 1
        )

    def handle(page, raw):
        """Process one non-title line inside the current instrument."""
        line = _clean(raw)
        numbered_text, row_scale, row_tokens = item_text(raw)
        current["context"].append(line)
        if len(current["context"]) > 10000:
            raise ValueError("Document text exceeds safety limit.")
        if _references_heading(line):
            finish_question()
            references.update(page=page, title=None)
            if current["collection"]:
                current["capture"] = False
            return
        if references["page"] is not None:
            if not _resumes_questionnaire(line, numbered_text, current["scale_legend"]):
                if _NUMBERED_ENTRY.match(numbered_text):
                    non_item(page, line)
                return
            references["page"] = None
        if _NUMBERED_ENTRY.match(numbered_text) and _reference_like(numbered_text):
            finish_question()  # its wrapped lines must not join the last item
            non_item(page, line)
            return
        if current["collection"] and (
            SCALE_START.match(line) or line.lower().startswith("instructions:")
        ):
            current["capture"] = True
            return
        if STOP.match(line):
            finish_question()
            current["capture"] = False
            return
        sect = SECTION.match(line)
        if sect:
            finish_question()
            current["section"] = (
                "Section " + sect.group(1) + ": " + sect.group(2)
            )[:80]
            current["capture"] = True
            return
        if current["collection"] and not current["capture"]:
            return

        labels = NUMBER_LABEL.findall(line)
        if labels and len(labels) >= 2:
            maybe = {code: label.strip() for code, label in labels}
            nums = sorted(map(int, maybe))
            if nums == list(range(nums[0], nums[-1]+1)) and 2 <= len(nums) <= 11:
                current["codes"] = maybe
                current["binary"] = None  # a numeric scale replaces it
                return
        code_legend = parse_code_legend(line)
        if code_legend and all(re.search(r"[^\W\d_]{3}", v) for v in code_legend.values()):
            nums = sorted(map(int, code_legend))
            if nums == list(range(nums[0], nums[-1] + 1)) and 2 <= len(nums) <= 11:
                current["codes"] = dict(code_legend)
                current["binary"] = None
                return
        # A short UCLA form writes anchors one per line: 1- Never.
        single_code = re.fullmatch(
            r"([0-9]|10)\s*[-–]\s*([A-Za-z][A-Za-z ]{2,25})", line
        )
        if single_code:
            current["codes"][single_code.group(1)] = single_code.group(2)
            return
        legend = parse_legend(line)
        if legend:
            current["scale_legend"].update(legend)
        header = match_header(line)
        if header is not None:
            pending = current["pending"]
            repeated = (
                current["binary"] is not None
                and current["binary"]["scale"].labels == header.labels
            )
            if repeated:
                return  # the same header printed again on a new page
            if pending is not None and not pending["options"] and not pending["lines"]:
                # Directly under its item (a table row's own answer cells).
                pending["binary"] = header
            else:
                finish_question()  # earlier items never inherit a later header
            current["binary"] = {"scale": header, "page": page}
            current["scale"] = None
            return
        scale_header = match_scale_header(line, current["scale_legend"])
        if scale_header is None and current["scale_legend"] and not current["rows"]:
            scale_header = match_legend_header(line, current["scale_legend"])
        if scale_header is not None:
            previous = current["scale"]
            if previous is not None and previous["header"].printed == scale_header.printed:
                return  # repeated header on a continuation page
            finish_question()  # earlier items never inherit a later header
            current["scale"] = {"header": scale_header, "page": page, "codes": None,
                                "fresh": True}
            current["binary"] = None
            return
        scale = current["scale"]
        if scale is not None and scale["fresh"] and scale["codes"] is None:
            printed_codes = codes_line(line, len(scale["header"].printed))
            if printed_codes:
                scale["codes"] = printed_codes
                return
        hint = match_instruction(line)
        if hint is not None and current["hint"] is None:
            current["hint"] = {"scale": hint, "page": page}
        current["legend"].update(legend_labels(line))
        if re.search(r"copyright|for researchers only|purchase only", line, re.I):
            current["warnings"].append(
                "Review copyright/licensing before reproducing this scale."
            )
        if re.search(
            r"\bif\s+yes\s+to\s+question\s+\d+", line, re.I
        ):
            current["warnings"].append(
                "A conditional instruction was detected. "
                "Its skip logic must be configured manually."
            )
        if "reverse" in line.lower() or re.search(
            r"\bitems?\s+\d+(?:\s*,\s*\d+)+\s+are", line, re.I
        ):
            current["context"].append(line)

        expected = expected_number()
        detected = _numbered(numbered_text, expected)
        if detected is None and (current["rows"] or (expected == 1 and current["pending"] is None)):
            # One unreadable item must not hide every following item.
            skipped = _numbered(numbered_text, expected + 1)
            if skipped is not None and len(skipped[1].split()) >= 3:
                detected = skipped
                current["warnings"].append(
                    f"Item {expected} was not recognized; check the source page."
                )
        if detected:
            finish_question()
            n, prompt, starred = detected
            if starred:
                current["reverse"].add(n)
            if current["scale"] is not None:
                current["scale"]["fresh"] = False
            current["pending"] = {
                "number": n, "prompt": prompt, "page": page,
                "excerpt": line[:300], "confidence": "review",
                "options": [], "notes": [], "binary": row_scale, "lines": 0,
                "row_tokens": row_tokens,
            }
            # Inline checkbox on antiword table row.
            if "|" in raw and "[ " in raw:
                labels = re.findall(r"\[\s*\]\s*([^|]+)", raw)
                current["pending"]["options"].extend(
                    x.strip() for x in labels if x.strip()
                )
            return
        if current["pending"] is None:
            return
        current["pending"]["lines"] += 1
        answer = CHOICE.match(line)
        if answer:
            if len(current["pending"]["options"]) < 12:
                current["pending"]["options"].append(answer.group(1).strip())
            return
        if line.lstrip().startswith("|") and "[ " in line:
            labels = re.findall(r"\[\s*\]\s*([^|]+)", line)
            current["pending"]["options"].extend(
                x.strip() for x in labels if x.strip()
            )
            return
        # Conservative continuation: question is visibly wrapped and still
        # incomplete. Do not attach scoring instructions to the last item.
        if (
            not current["pending"]["prompt"].endswith(("?", ".", "!"))
            and len(line.split()) >= 2
            and not line.lower().startswith((
                "score", "instructions", "the following",
                "scoring", "your score", "copyright",
            ))
            and not _reference_like(line)
        ):
            combined = current["pending"]["prompt"] + " " + line
            if len(combined) <= 300:
                current["pending"]["prompt"] = combined
            else:
                current["pending"]["notes"].append(
                    "Possible wrapped text omitted: question exceeded limit."
                )

    def flush():
        while current is not None and current["buffer"]:
            page_, raw_ = current["buffer"].pop(0)
            handle(page_, raw_)

    def restart_split(page):
        """Index where a NEW instrument version starts in the buffer, or None.

        Numbering restarting at 1 after a heading (or a new response-scale
        header/legend, or a new page) starts a separate instrument, so the
        original and a revised version are never merged.
        """
        buffer = current["buffer"]
        last_page = current["rows"][-1].page if current["rows"] else (
            current["pending"]["page"] if current["pending"] else page)
        headings = [i for i, (_, r) in enumerate(buffer) if _title_line(_clean(r))]
        if any(STOP.match(_clean(buffer[i][1])) or _references_heading(buffer[i][1]) or re.search(
                r"referenc|bibliograph|studies using", _clean(buffer[i][1]), re.I)
               for i in headings):
            return None  # references / scoring notes, not a new instrument
        if headings:
            return headings[-1]
        for i, (p, r) in enumerate(buffer):
            text = _clean(r)
            if (match_scale_header(text, current["scale_legend"]) or parse_legend(text)
                    or match_header(text)):
                return i
        if page != last_page:
            moved = [i for i, (p, _) in enumerate(buffer) if p == page]
            return moved[0] if moved else len(buffer)
        return None

    for page, raw in lines:
        line = _clean(raw)
        if not line:
            continue
        title = _title(line)
        if title:
            if current is not None and current["title"] == title:
                continue
            flush()
            finish_instrument()
            references.update(page=None, title=None)  # a known instrument begins
            collection = "Self_Measures" in source_name or (
                "LONELINESS_AND_INTERPERSONAL" in source_name.upper()
            )
            current = begin(title, page, collection=collection)
            continue
        numbered_text, _row_scale, _tokens = item_text(raw)
        if current is None:
            if _references_heading(line):
                references.update(page=page, title=None)
                continue
            if references["page"] is not None:
                # A titled form numbered from 1 after the bibliography.
                titled = references["title"] is not None and _numbered(numbered_text, 1)
                if not (titled or _resumes_questionnaire(
                        line, numbered_text, preamble["scale_legend"])):
                    if _NUMBERED_ENTRY.match(numbered_text):
                        non_item(page, line)
                    references["title"] = (line if _title_line(line) and not _reference_like(line)
                                           else None)
                    continue
                if titled:
                    preamble["lines"].append(references["title"])
                references.update(page=None, title=None)
            header = match_header(line)
            if header is not None:
                preamble["binary"] = {"scale": header, "page": page}
                continue
            legend = parse_legend(line)
            if legend:
                preamble["scale_legend"].update(legend)
            anchors = dict(NUMBER_LABEL.findall(line)) if len(NUMBER_LABEL.findall(line)) >= 2 else {}
            anchors = anchors or parse_code_legend(line)
            single = re.fullmatch(r"([0-9]|10)\s*[-–]\s*([A-Za-z][A-Za-z ]{2,25})", line)
            if anchors or single:
                preamble["codes"].update(anchors or {single.group(1): single.group(2)})
                continue
            scale_header = match_scale_header(line, preamble["scale_legend"])
            if scale_header is None and preamble["scale_legend"]:
                scale_header = match_legend_header(line, preamble["scale_legend"])
            if scale_header is not None:
                preamble["scale"] = {"header": scale_header, "page": page,
                                     "codes": None, "fresh": True}
                continue
            if preamble["scale"] is not None and preamble["scale"]["codes"] is None:
                printed_codes = codes_line(line, len(preamble["scale"]["header"].printed))
                if printed_codes:
                    preamble["scale"]["codes"] = printed_codes
                    continue
            hint = match_instruction(line)
            if hint is not None:
                preamble["hint"] = {"scale": hint, "page": page}
            preamble["legend"].update(legend_labels(line))
            if _NUMBERED_ENTRY.match(numbered_text) and _reference_like(numbered_text):
                non_item(page, line)  # a citation never opens a candidate
                continue
            preamble["lines"].append(line)
            if re.match(r"^\s*(?:\d{1,3}[.):]\s+.+|\d{1,3}\s{2,}.+)", numbered_text):
                current = begin(
                    _stem_title(source_name, preamble["lines"]), page,
                )
                handle(page, raw)
            continue
        if not (current["rows"] or current["pending"]):
            handle(page, raw)
            continue
        expected = expected_number()
        continues = _numbered(numbered_text, expected) or (
            _numbered(numbered_text, expected + 1)
        )
        restart = None
        if not continues and expected > 3 and _numbered(numbered_text, 1) and not _reference_like(line):
            restart = restart_split(page)
        if restart is not None:
            buffer = current["buffer"]
            before, after = buffer[:restart], buffer[restart:]
            heading = _clean(after[0][1]) if after and _title_line(_clean(after[0][1])) else None
            current["buffer"] = before
            flush()
            finish_instrument()
            parts += 1
            if heading:
                references.update(page=None, title=None)  # a new titled form
            current = begin(heading[:75] if heading else
                            f"{Path(source_name).stem[:60]} — part {parts}", page)
            for page_, raw_ in (after[1:] if heading else after):
                handle(page_, raw_)
            handle(page, raw)
            continue
        if continues:
            flush()
            handle(page, raw)
        else:
            current["buffer"].append((page, raw))
    flush()
    finish_instrument()

    expected = expected_item_count(_count_evidence(lines))
    language = _ocr_language_hint(text for _, text in lines)
    if non_items:
        pages = ", ".join(str(p) for p in sorted({p for p, _ in non_items}))
        document_notes.append(
            f"Non-item material: {len(non_items)} numbered line(s) on page(s) {pages} "
            "look like bibliography references, not questions, and were not imported."
        )
    if not instruments:
        if non_items:
            reason = (
                f"No numbered questions found: the {len(non_items)} numbered lines look like "
                "references (a bibliography), not questionnaire items."
                if len(non_items) > 1 else
                "No numbered questions found: the numbered line looks like a reference "
                "(a bibliography entry), not a questionnaire item."
            )
            if image_pages:
                reason += (" Image-backed page(s) " + ", ".join(map(str, image_pages))
                           + " may hold the questionnaire; read them with local OCR.")
        else:
            reason = ("No numbered questions found in selectable text. "
                      "Image-only forms need OCR and manual review.")
        raise NoQuestionsFound(reason, non_items=non_items, expected_count=expected,
                               image_pages=image_pages, ocr_language=language)

    if len(instruments) > 1:
        document_notes.append(
            f"Found {len(instruments)} different candidate instruments. "
            "Select ONE instrument/version; never merge them automatically."
        )
    return ScientificDocumentReview(
        source_name, tuple(instruments), tuple(document_notes),
        page_count, image_pages, non_items=tuple(non_items),
        expected_count=expected, ocr_language=language,
    )


def linked_questions(candidate: InstrumentCandidate, scheme_id: str) -> list[int]:
    """Indices of questions currently linked to a shared scale."""
    return [i for i, row in enumerate(candidate.questions) if row.scheme_id == scheme_id]


def unconfirmed_schemes(candidate: InstrumentCandidate) -> list[ResponseScheme]:
    return [
        s for s in candidate.schemes
        if linked_questions(candidate, s.id) and not s.structure_confirmed
    ]


def scheme_banner(candidate: InstrumentCandidate) -> str | None:
    """Blocking message for unverified shared scales, or None."""
    pending = unconfirmed_schemes(candidate)
    if not pending:
        return None
    parts = []
    for scheme in pending:
        count = len(linked_questions(candidate, scheme.id))
        labels = " / ".join(scheme.labels) if not scheme.label_problems() else "labels missing"
        parts.append(f"{count} questions use an unverified {scheme.size}-choice scale ({labels})")
    return "; ".join(parts) + ". Review and confirm the response scale before importing."


def reviewed_draft(
    candidate: InstrumentCandidate, *,
    accept_numeric: bool = False,
    accept_reverse: bool = False,
) -> list[dict]:
    """Only apply a scoring proposal with explicit confirmation.

    Items on a shared response scale (``Candidate.scheme_id``) follow THAT
    scale's separate confirmations; an unconfirmed scale blocks the draft
    instead of silently producing free-text questions.
    ``accept_numeric``/``accept_reverse`` apply to the remaining items with
    a parsed text codebook.
    """
    from copy import deepcopy
    if accept_reverse and not accept_numeric:
        raise ValueError(
            "Confirm numeric response codes before applying reverse keys."
        )
    banner = scheme_banner(candidate)
    if banner:
        raise ValueError(banner)
    schemes = {s.id: s for s in candidate.schemes}
    reversed_numbers = set(candidate.scoring.reverse_numbers)
    raw = []
    for row in candidate.questions:
        q = deepcopy(row.question)
        scheme = schemes.get(row.scheme_id) if row.scheme_id else None
        if scheme is not None:
            for name in ("options", "value_labels", "scale_id"):
                q.pop(name, None)
            labels = [label.strip() for label in scheme.labels]
            if scheme.codes_confirmed:
                q["kind"] = "rating_scale"
                q["value_labels"] = dict(zip(scheme.codes, labels))
                q["scale_id"] = f"import_{scheme.id}"
                q["reverse_scored"] = bool(
                    scheme.reverse_confirmed and row.number in scheme.reverse_items
                )
            else:
                q["kind"] = "single_choice"
                q["options"] = labels
                q["reverse_scored"] = False
        elif q["kind"] == "rating_scale" and not accept_numeric:
            q["kind"] = "single_choice"
            q["options"] = [
                f"{code}: {label}"
                for code, label in candidate.scoring.code_labels
            ]
            q.pop("value_labels", None)
            q.pop("scale_id", None)
            q["reverse_scored"] = False
        elif q["kind"] == "rating_scale" and accept_reverse:
            q["reverse_scored"] = row.number in reversed_numbers
        raw.append(q)
    return validate_questions(raw)
