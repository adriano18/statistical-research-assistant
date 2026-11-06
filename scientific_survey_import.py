"""Conservative scientific Word/PDF questionnaire import with version isolation.

This module does NOT validate a published instrument, score respondents,
contact external services, run OCR, or distribute copyrighted test content.
The reader produces candidate instruments with source context and a *proposed*
scoring key that requires explicit researcher approval before draft use.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
import shutil
import subprocess

from binary_responses import (
    BinaryScale, expand_with_legend, legend_labels, match_header,
    match_instruction, split_row, strip_noisy_row_pair,
)
from letter_spacing import SpacingRepair, repair_pdf_text, repair_summary
from repeated_choices import (
    BlockItemLine, ChoiceBlock, printed_label, segment_repeated_choices,
)
from response_scales import (
    codes_line, match_legend_header, match_scale_header,
    normalize_tokens, parse_code_legend, parse_legend, split_row_tokens,
    strip_trailing_scale_tokens,
)
from scoring_evidence import (
    ReviewEvidence, ScoringGroup, ScoringStatement, parse_scoring_evidence,
    referenced_missing, sequence_gaps,
)
from survey_storage import validate_questions

MAX_BYTES = 20_000_000
MAX_PAGES = 80
MAX_QUESTIONS = 200

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
    # Review-only evidence for Stage 33: documented scoring groups/statements
    # (never applied), missing item numbers and per-item flags.
    evidence: ReviewEvidence = ReviewEvidence()


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
    # Whitespace repairs of a letter-spaced PDF text layer (original text kept).
    spacing_repairs: tuple[SpacingRepair, ...] = ()
    # repeated_choices.ChoiceLayout when answer choices follow every item:
    # the common block and every item's own printed block (review evidence).
    choice_layout: object | None = None


def _title(line: str) -> str | None:
    for expression, label in VALID_HEADINGS:
        if expression.fullmatch(line.strip()):
            return label
    return None


def _clean(line: str) -> str:
    return " ".join(str(line).replace("\x00", " ").split()).strip()


def _numbered(line: str, expected: int | None) -> tuple[int, str, bool] | None:
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


def _reference_like(line: str) -> bool:
    return bool(re.search(r"\(\d{4}[a-z]?\)|\bdoi\b|\bet al\.?|\bpp?\.\s*\d", line, re.I))


FORM_FIELD_WORDS = {
    "name", "date", "clinician", "respondent", "participant", "patient", "client",
    "signature", "id", "age", "sex", "gender", "dob", "birth", "examiner",
    "therapist", "rater", "vārds", "uzvārds", "datums", "vecums", "dzimums",
    "имя", "фамилия", "дата", "возраст", "пол",
}


def _form_field_line(line: str) -> bool:
    """Respondent name / date / clinician fields printed above the items."""
    words = [w.strip(":_.·|").casefold() for w in line.split()]
    words = [w for w in words if w and not set(w) <= set("_-")]
    return bool(words) and sum(w in FORM_FIELD_WORDS for w in words) >= max(2, round(0.6 * len(words)))


def _stem_title(source_name: str, preamble_lines: list[str]) -> str:
    """A heading printed just before the items, else the file name stem."""
    for line in reversed(preamble_lines[-6:]):
        if _title_line(line) and not _form_field_line(line):
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


def _read_pdf_pages(path: Path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDF cannot be imported.")
    if len(reader.pages) > MAX_PAGES:
        raise ValueError("PDF exceeds the 80-page limit.")
    pages = []
    image_pages = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        pages.append((i, text.splitlines()))
        # An image-backed page with no question text may hide its scale table
        # even when it has a readable footer/bibliography.
        try:
            if len(page.images):
                image_pages.append(i)
        except (ValueError, KeyError):
            pass
    # Letter-spaced text layers ("sched ule", "s c h e d u l e") are
    # repaired conservatively from PDFium glyph geometry (whitespace only).
    with_text = [(i, page_lines) for i, page_lines in pages if any(s.strip() for s in page_lines)]
    fixed, repairs = repair_pdf_text(path, with_text)
    by_page = dict(fixed)
    lines = [(i, s) for i, page_lines in pages for s in by_page.get(i, page_lines)]
    return lines, len(reader.pages), tuple(image_pages), repairs


def _read_pdf(path: Path) -> tuple[list[tuple[int, str]], int, tuple[int, ...]]:
    lines, pages, images, _repairs = _read_pdf_pages(path)
    return lines, pages, images


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
                            lines.extend((1, v) for v in _cell_lines(value))
                else:
                    for value in values:
                        if value:
                            lines.extend((1, v) for v in _cell_lines(value))
    return lines, 1, ()


def _cell_lines(value: str) -> list[str]:
    """A choice cell printed as ``1`` + ``NOT AT ALL`` keeps its code line."""
    parts = [p.strip() for p in value.splitlines() if p.strip()]
    if len(parts) >= 2 and re.fullmatch(r"[(\[]?\d{1,2}[)\].]?|[①-⑳]", parts[0]):
        return parts
    return [value]


def _read_legacy_doc(path: Path) -> tuple[list[tuple[int, str]], int, tuple[int, ...]]:
    binary = shutil.which("antiword")
    if not binary:
        raise ValueError(
            "Legacy .doc requires locally installed antiword. "
            "Save the document as .docx in Word or LibreOffice and reimport."
        )
    result = subprocess.run(
        [binary, "-w", "140", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace", timeout=12,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise ValueError("Legacy .doc could not be decoded; convert to .docx.")
    return [(1, line) for line in result.stdout.splitlines()], 1, ()


def read_scientific_document(path: str | Path) -> ScientificDocumentReview:
    file = Path(path).expanduser().resolve()
    ext = file.suffix.lower()
    if ext not in (".docx", ".doc", ".pdf"):
        raise ValueError("Choose a PDF, DOCX or legacy DOC questionnaire.")
    size = file.stat().st_size
    if size < 1 or size > MAX_BYTES:
        raise ValueError("Source must be nonempty and at most 20 MB.")
    repairs: tuple[SpacingRepair, ...] = ()
    if ext == ".pdf":
        lines, pages, images, repairs = _read_pdf_pages(file)
        source = "pdf_text_layer"
    elif ext == ".docx":
        lines, pages, images = _read_docx(file)
        source = "docx"
    else:
        lines, pages, images = _read_legacy_doc(file)
        source = "doc"
    review = parse_scientific_lines(
        lines, file.name, page_count=pages, image_pages=images, text_source=source,
    )
    return with_spacing_repairs(review, repairs)


def with_spacing_repairs(
    review: ScientificDocumentReview, repairs,
) -> ScientificDocumentReview:
    """Record whitespace repairs (provenance) and flag the affected items."""
    repairs = tuple(repairs)
    if not repairs:
        return review
    changed: dict[int, list[str]] = {}
    for repair in repairs:
        changed.setdefault(repair.page, []).append(" ".join(repair.repaired.split()))
    instruments = []
    for instrument in review.instruments:
        rows, flagged = [], []
        for row in instrument.questions:
            prompt = " ".join(row.question.get("prompt", "").split())
            excerpt = " ".join(row.excerpt.split())
            hit = sum(1 for text in changed.get(row.page, ())
                      if len(text) >= 3 and (text in prompt or text in excerpt))
            if hit:
                flagged.append(row.number)
                row = replace(row, notes=(*row.notes, (
                    f"Letter-spacing of the PDF text layer was repaired in {hit} "
                    "source line(s) of this item (whitespace only); the original "
                    "text is kept in the import review.")))
            rows.append(row)
        evidence = instrument.evidence
        if flagged:
            flags = dict(evidence.item_flags)
            for number in flagged:
                flags[number] = (*flags.get(number, ()), "spacing repaired")
            evidence = replace(evidence, item_flags=tuple(sorted(flags.items())))
        instruments.append(replace(instrument, questions=tuple(rows), evidence=evidence))
    return replace(
        review, instruments=tuple(instruments), spacing_repairs=repairs,
        warnings=(*review.warnings, repair_summary(repairs)),
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


def _block_scheme(scheme_id: str, group: dict, rows, scoring, context,
                  codebook=None, header=None) -> ResponseScheme:
    """Shared scale from answer choices printed after every linked item.

    When the blocks print codes only, a code legend (``1 = …``) or a scale
    header of THIS instrument supplies the labels; a legend that disagrees
    with printed labels is reported.
    """
    template: ChoiceBlock = group["template"]
    labels = tuple(template.labels)
    numbers = tuple(row.number for row in rows)
    issues = []
    evidence = "item_block"
    legend = {str(code): printed_label(label) for code, label in (codebook or {}).items()}
    covered = bool(legend) and all(code in legend for code in template.codes)
    if not any(labels) and covered:
        labels, evidence = tuple(legend[code] for code in template.codes), "item_block+legend"
    elif not any(labels) and header is not None and len(header.labels) == template.size:
        labels, evidence = tuple(printed_label(l) for l in header.labels), "item_block+header"
    elif covered and [re.sub(r"\s+", "", legend[c]).casefold() for c in template.codes] != [
            re.sub(r"\s+", "", l).casefold() for l in labels]:
        issues.append(
            "The code legend printed for this instrument ("
            + " / ".join(f"{c} = {legend[c]}" for c in template.codes)
            + ") differs from the answer choices printed after every item; "
            "check which labels the source uses."
        )
    differing = [(n, d) for n, d in group["deviations"] if d]
    if differing:
        detail = "; ".join(f"item {n}: {d[0]}" for n, d in differing[:4])
        issues.append(
            "Printed answer choices differ on item(s) "
            + ", ".join(str(n) for n, _ in differing[:15])
            + f" ({detail}); check them on the source page before confirming."
        )
    if not all(labels):
        issues.append("Some answer choices have no printed label; enter the labels.")
    if group.get("fuzzy"):
        issues.append("Answer choices were read by OCR; compare every label with the source.")
    pages = sorted({row.page for row in rows})
    source = " · ".join(f"{c} {l}".strip() for c, l in zip(template.codes, labels))
    reverse = tuple(n for n in scoring.reverse_numbers if n in numbers)
    reverse_text = next((line for line in context
                         if re.search(r"revers|circled number", line, re.I)), "")
    return ResponseScheme(
        scheme_id, labels, tuple(template.labels) if any(template.labels) else tuple(template.codes),
        tuple(template.codes), evidence,
        pages[0] if pages else template.page, source[:160],
        numbers, reverse, reverse_text[:200], issues=tuple(issues),
    )


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
        if key[0] == "block":
            scale = current["scale"]
            scheme = _block_scheme(f"s{len(schemes) + 1}", group, [rows[i] for i in indices],
                                   scoring, current["context"], codebook,
                                   scale["header"] if scale else None)
            schemes.append(scheme)
            for i in indices:
                assignments[i] = scheme
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


def _review_evidence(current: dict, rows, evidence_for) -> ReviewEvidence:
    """Documented scoring, missing item numbers and per-item flags (review only)."""
    numbers = [row.number for row in rows]
    groups, statements, issues = parse_scoring_evidence(
        current["evidence_lines"], numbers, evidence_for=evidence_for,
    )
    top = max(numbers) if numbers else 0
    missing = set(sequence_gaps(numbers)) | {
        n for n in referenced_missing(groups, numbers) if n <= top + 5
    }
    flags: dict[int, list[str]] = {n: list(v) for n, v in current["flags"].items()}
    for row in rows:
        if evidence_for(row.page) == "ocr":
            flags.setdefault(row.number, []).append("read by OCR")
    item_flags = tuple(
        (number, tuple(dict.fromkeys(values)))
        for number, values in sorted(flags.items()) if values
    )
    return ReviewEvidence(groups, statements, tuple(sorted(missing)), item_flags, issues)


def parse_scientific_lines(
    lines: list[tuple[int, str]], source_name: str, *,
    page_count: int = 1, image_pages: tuple[int, ...] = (),
    ocr_pages: tuple[int, ...] = (), text_source: str = "text",
) -> ScientificDocumentReview:
    """Candidate instruments from ``(page, line)`` text.

    ``ocr_pages`` marks pages whose text came from local OCR (evidence is
    labelled as OCR-only and repeated answer labels are compared tolerantly);
    ``text_source`` names the source of the other pages ("pdf_text_layer",
    "docx", "doc" or "text").
    """
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
            + " may include unseen table questions. OCR is not automatic."
        )
    ocr_set = set(ocr_pages)

    def evidence_for(page: int) -> str:
        return "ocr" if page in ocr_set else text_source

    # Answer choices repeated after every item (coping-inventory layouts):
    # each item becomes ONE line carrying its parsed block of choices.
    lines, choice_layout = segment_repeated_choices(list(lines), fuzzy_pages=ocr_pages)
    if choice_layout is not None:
        document_notes.append(
            f"Answer choices printed after every item were recognized "
            f"({len(choice_layout.items)} items, {choice_layout.template.size} choices "
            "each); item numbers were joined with their prompts. Verify against the source."
        )
    current = None
    bibliography_zone = False
    # Binary answer evidence seen before the first numbered item (headers,
    # instructions and legends usually precede the items).
    preamble = {"binary": None, "hint": None, "legend": {}, "scale": None,
                "scale_legend": {}, "lines": [], "codes": {}}
    parts = 1

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
            "evidence_lines": [], "flags": {},
        }
        preamble.update({"binary": None, "hint": None, "legend": {}, "scale": None,
                         "scale_legend": {}, "lines": [], "codes": {}})
        return state

    # A differing block printed identically after two or more items is a
    # different scale; a one-off difference stays on the common scale and is
    # reported as an issue of that scale (never silently replaced).
    other_scales = {}
    if choice_layout is not None:
        counts: dict = {}
        for item in choice_layout.items:
            if (item.block.size == choice_layout.template.size
                    and any("OCR variant" not in d for d in item.deviations)):
                counts[item.block.key] = counts.get(item.block.key, 0) + 1
        other_scales = {key for key, count in counts.items() if count >= 2}

    def block_link(pending):
        """Shared-scale key for an item whose answer choices follow it."""
        item = pending["block_item"]
        own = item.block.key in other_scales
        template = item.block if own else choice_layout.template
        key = ("block", template.key)
        group = current["scale_groups"].setdefault(key, {
            "header": None, "page": pending["page"], "scale": None, "tokens": [],
            "template": template, "deviations": [], "fuzzy": choice_layout.fuzzy,
        })
        group["deviations"].append((item.number, () if own else item.deviations))
        return key

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
        if pending.get("block_item") is not None:
            link = block_link(pending)
        elif len(opts) < 2:
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
            evidence = _review_evidence(current, rows, evidence_for)
            if evidence.missing_items:
                numbers = [r.number for r in rows]
                current["warnings"].append(
                    "Item number(s) " + ", ".join(map(str, evidence.missing_items))
                    + f" missing from the numbered sequence {min(numbers)}–"
                    f"{max([*numbers, *evidence.missing_items])}; check the source page."
                )
            current["warnings"].extend(evidence.issues)
            instruments.append(InstrumentCandidate(
                current["title"], tuple(rows), scoring,
                tuple(current["warnings"]), current["page"], tuple(formats),
                tuple(schemes), tuple(sorted(current["scale_legend"].items())),
                evidence,
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

    def handle_block_item(page, raw: BlockItemLine):
        """An item whose answer choices were printed right after it."""
        item = raw.item
        current["context"].append(_clean(raw))
        finish_question()
        current["capture"] = True
        if current["scale"] is not None:
            current["scale"]["fresh"] = False
        flags = current["flags"].setdefault(item.number, [])
        if item.number_source == "inferred":
            flags.append("item number inferred from order")
        if item.deviations:
            flags.append("answer choices differ from the common scale")
        if item.prompt_lines > 1:
            flags.append(f"prompt joined from {item.prompt_lines} lines")
        notes = list(item.notes)
        if item.deviations:
            notes.append("Printed answer choices differ: " + "; ".join(item.deviations) + ".")
        current["pending"] = {
            "number": item.number, "prompt": item.prompt[:300], "page": item.page,
            "excerpt": item.excerpt[:300], "confidence": "review",
            "options": [], "notes": notes, "binary": None, "lines": 0,
            "row_tokens": (), "block_item": item,
        }
        finish_question()  # the printed choices end the item: no wrapped text follows

    def handle(page, raw):
        """Process one non-title line inside the current instrument."""
        if isinstance(raw, BlockItemLine):
            handle_block_item(page, raw)
            return
        line = _clean(raw)
        numbered_text, row_scale, row_tokens = item_text(raw)
        current["context"].append(line)
        if len(current["context"]) > 10000:
            raise ValueError("Document text exceeds safety limit.")
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
        if not detected:
            current["evidence_lines"].append((page, line))
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
        if any(STOP.match(_clean(buffer[i][1])) or re.search(
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
            collection = "Self_Measures" in source_name or (
                "LONELINESS_AND_INTERPERSONAL" in source_name.upper()
            )
            current = begin(title, page, collection=collection)
            continue
        block = isinstance(raw, BlockItemLine)
        numbered_text = str(raw) if block else item_text(raw)[0]
        if current is None and block:
            current = begin(_stem_title(source_name, preamble["lines"]), page)
            handle(page, raw)
            continue
        if current is None:
            if re.match(r"^references\s*:?\s*$", line, re.I):
                bibliography_zone = True
            if not bibliography_zone:
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
                preamble["lines"].append(line)
            if (
                not bibliography_zone
                and re.match(
                    r"^\s*(?:\d{1,3}[.):]\s+.+|\d{1,3}\s{2,}.+)",
                    numbered_text,
                )
            ):
                current = begin(
                    _stem_title(source_name, preamble["lines"]), page,
                )
                handle(page, raw)
            continue
        if not (current["rows"] or current["pending"]):
            handle(page, raw)
            continue
        expected = expected_number()
        if block:
            # Items with printed choices continue the instrument (gaps are
            # reported); numbering restarting at 1 starts another version.
            continues = raw.item.number != 1
        else:
            continues = _numbered(numbered_text, expected) or (
                _numbered(numbered_text, expected + 1)
            )
        restart = None
        if block and not continues:
            restart = restart_split(page)
            if restart is None:
                restart = len(current["buffer"])
        elif not continues and expected > 3 and _numbered(numbered_text, 1) and not _reference_like(line):
            restart = restart_split(page)
        if restart is not None:
            buffer = current["buffer"]
            before, after = buffer[:restart], buffer[restart:]
            heading = _clean(after[0][1]) if after and _title_line(_clean(after[0][1])) else None
            current["buffer"] = before
            flush()
            finish_instrument()
            parts += 1
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

    if not instruments:
        reason = ("No numbered questions found in selectable text. "
                  "Image-only forms need OCR and manual review.")
        raise ValueError(reason)

    if len(instruments) > 1:
        document_notes.append(
            f"Found {len(instruments)} different candidate instruments. "
            "Select ONE instrument/version; never merge them automatically."
        )
    return ScientificDocumentReview(
        source_name, tuple(instruments), tuple(document_notes),
        page_count, image_pages, choice_layout=choice_layout,
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


def missing_items_banner(candidate: InstrumentCandidate) -> str | None:
    """Blocking message for item numbers missing from the sequence, or None."""
    evidence = candidate.evidence
    if not evidence.missing_items or evidence.missing_acknowledged:
        return None
    numbers = [row.number for row in candidate.questions]
    last = max([*numbers, *evidence.missing_items]) if numbers else max(evidence.missing_items)
    first = min([*numbers, *evidence.missing_items])
    missing = ", ".join(map(str, evidence.missing_items))
    return (
        f"Item {missing} {'is' if len(evidence.missing_items) == 1 else 'are'} missing "
        f"from the numbered sequence {first}–{last}. Check the source page, add the "
        "item(s) or confirm that the source omits them before importing."
    )


def review_banner(candidate: InstrumentCandidate) -> str | None:
    """Every blocking review message of a candidate (scale, then sequence)."""
    parts = [text for text in (scheme_banner(candidate), missing_items_banner(candidate)) if text]
    return " ".join(parts) or None


def acknowledge_missing_items(candidate: InstrumentCandidate) -> InstrumentCandidate:
    """Researcher decision: the reported item numbers are absent in the source."""
    if not candidate.evidence.missing_items:
        raise ValueError("No item numbers are missing from this candidate.")
    return replace(candidate, evidence=replace(candidate.evidence, missing_acknowledged=True))


def approve_scoring_evidence(
    candidate: InstrumentCandidate, group_ids=None, *, ocr_checked: bool = False,
) -> InstrumentCandidate:
    """Mark documented scoring groups as checked by the researcher.

    Approval is review metadata for a later scoring step: it NEVER changes a
    question, a code or a reverse key, and :func:`reviewed_draft` ignores it.
    Every listed item must already be on a shared scale whose numeric codes
    were confirmed; OCR-only evidence additionally needs ``ocr_checked``.
    """
    evidence = candidate.evidence
    if not evidence.scoring_groups:
        raise ValueError("This candidate has no documented scoring groups.")
    wanted = set(group_ids) if group_ids is not None else {g.id for g in evidence.scoring_groups}
    unknown = wanted - {g.id for g in evidence.scoring_groups}
    if unknown:
        raise KeyError("Unknown scoring group: " + ", ".join(sorted(unknown)))
    confirmed = {
        row.number for row in candidate.questions
        if row.scheme_id and any(s.id == row.scheme_id and s.codes_confirmed
                                 for s in candidate.schemes)
    }
    groups = []
    for group in evidence.scoring_groups:
        if group.id in wanted:
            if group.ocr_only and not ocr_checked:
                raise ValueError(f"Scoring group “{group.name}” was read by OCR only; "
                                 "compare it with the source page first.")
            missing = [n for n in group.items if n not in confirmed]
            if missing:
                raise ValueError(
                    f"Confirm the numeric codes of the shared scale before approving "
                    f"“{group.name}” (item(s) {', '.join(map(str, missing[:10]))} not confirmed)."
                )
            group = replace(group, approved=True)
        groups.append(group)
    return replace(candidate, evidence=replace(evidence, scoring_groups=tuple(groups)))


def reviewed_draft(
    candidate: InstrumentCandidate, *,
    accept_numeric: bool = False,
    accept_reverse: bool = False,
) -> list[dict]:
    """Only apply a scoring proposal with explicit confirmation.

    Items on a shared response scale (``Candidate.scheme_id``) follow THAT
    scale's separate confirmations; an unconfirmed scale blocks the draft
    instead of silently producing free-text questions, and so do item numbers
    missing from the sequence until they are added or acknowledged.
    ``accept_numeric``/``accept_reverse`` apply to the remaining items with
    a parsed text codebook. Documented scoring groups are never applied.
    """
    if accept_reverse and not accept_numeric:
        raise ValueError(
            "Confirm numeric response codes before applying reverse keys."
        )
    banner = scheme_banner(candidate)
    if banner:
        raise ValueError(banner)
    missing = missing_items_banner(candidate)
    if missing:
        raise ValueError(missing)
    return draft_questions(candidate, accept_numeric=accept_numeric,
                           accept_reverse=accept_reverse)


def draft_questions(
    candidate: InstrumentCandidate, *,
    accept_numeric: bool = False,
    accept_reverse: bool = False,
) -> list[dict]:
    """The validated draft WITHOUT the review gates of :func:`reviewed_draft`.

    Used to check a partial review (one confirmed scale of several, a
    sequence that still has a gap). Unconfirmed scales keep their proposal.
    """
    from copy import deepcopy
    schemes = {s.id: s for s in candidate.schemes}
    reversed_numbers = set(candidate.scoring.reverse_numbers)
    raw = []
    for row in candidate.questions:
        q = deepcopy(row.question)
        scheme = schemes.get(row.scheme_id) if row.scheme_id else None
        if scheme is not None and not scheme.structure_confirmed:
            raw.append(q)
            continue
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
