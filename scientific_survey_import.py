"""Conservative scientific Word/PDF questionnaire import with version isolation.

This module does NOT validate a published instrument, score respondents,
contact external services, run OCR, or distribute copyrighted test content.
The reader produces candidate instruments with source context and a *proposed*
scoring key that requires explicit researcher approval before draft use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess

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
    (re.compile(r"^UCLA Loneliness Scale\s*[–-]\s*Questionnaire.*$", re.I),
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


@dataclass(frozen=True)
class ProposedScoring:
    code_labels: tuple[tuple[str, str], ...] = ()
    reverse_numbers: tuple[int, ...] = ()
    formula_hint: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class InstrumentCandidate:
    title: str
    questions: tuple[Candidate, ...]
    scoring: ProposedScoring
    warnings: tuple[str, ...]
    first_page: int


@dataclass(frozen=True)
class ScientificDocumentReview:
    source_name: str
    instruments: tuple[InstrumentCandidate, ...]
    warnings: tuple[str, ...]
    page_count: int
    image_only_pages: tuple[int, ...] = ()


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
    if not match:
        return None
    raw = match.group(2)
    n = 1 if raw in ("l", "I") and expected == 1 else (
        int(raw) if raw.isdigit() else -1
    )
    if n < 1 or n > MAX_QUESTIONS:
        return None
    # Avoid references, page numbers, scale-option keys (1- Never).
    label = match.group(4).strip()
    if len(label) < 5 or (
        len(label.split()) < 3 and not label.endswith("?")
    ):
        return None
    if expected is not None and n != expected:
        return None
    label = re.sub(r"\s+(?:[0-4]\s+){3,}[0-4]\s*$", "", label)
    label = re.sub(r"\s+(?:[OSRN]\s+){2,}[OSRN]\s*$", "", label)
    label = re.sub(r"\s+[Tt]\s+[Ff](?:\s+\S+)?\s*$", "", label)
    return n, label[:300], bool(match.group(1))


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
    if ext == ".pdf":
        lines, pages, images = _read_pdf(file)
    elif ext == ".docx":
        lines, pages, images = _read_docx(file)
    else:
        lines, pages, images = _read_legacy_doc(file)
    return parse_scientific_lines(
        lines, file.name, page_count=pages, image_pages=images,
    )


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
            + " may include unseen table questions. OCR is not automatic."
        )
    current = None
    bibliography_zone = False

    def begin(title: str, page: int, collection=False):
        return {
            "title": title, "page": page, "rows": [], "codes": {},
            "reverse": set(), "context": [], "pending": None,
            "section": "Imported questions", "capture": not collection,
            "collection": collection, "warnings": [],
        }

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
            rows = []
            safe_homogeneous_scale = (
                len(current["rows"]) >= 3
                and all(q.question["kind"] == "short_text"
                        for q in current["rows"])
            )
            if scoring.code_labels and not safe_homogeneous_scale:
                current["warnings"].append(
                    "Numeric anchors were found in a mixed or short "
                    "questionnaire; automatic rating conversion disabled."
                )
            for row in current["rows"]:
                question = dict(row.question)
                if (
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
                    row.confidence, row.notes,
                ))
            try:
                validate_questions([r.question for r in rows])
            except ValueError as error:
                current["warnings"].append(
                    f"Candidates must be edited before publishing: {error}"
                )
            instruments.append(InstrumentCandidate(
                current["title"], tuple(rows), scoring,
                tuple(current["warnings"]), current["page"],
            ))
        current = None

    for page, raw in lines:
        line = _clean(raw)
        if not line:
            continue
        title = _title(line)
        if title:
            if current is not None and current["title"] == title:
                continue
            finish_instrument()
            collection = "Self_Measures" in source_name or (
                "LONELINESS_AND_INTERPERSONAL" in source_name.upper()
            )
            current = begin(title, page, collection=collection)
            continue
        if current is None:
            if re.match(r"^references\s*:?\s*$", line, re.I):
                bibliography_zone = True
            if (
                not bibliography_zone
                and re.match(
                    r"^\s*(?:\d{1,3}[.):]\s+.+|\d{1,3}\s{2,}.+)",
                    raw,
                )
            ):
                current = begin(
                    Path(source_name).stem[:75], page,
                )
            else:
                continue

        current["context"].append(line)
        if len(current["context"]) > 10000:
            raise ValueError("Document text exceeds safety limit.")
        if current["collection"] and (
            SCALE_START.match(line) or line.lower().startswith("instructions:")
        ):
            current["capture"] = True
            continue
        if STOP.match(line):
            finish_question()
            current["capture"] = False
            continue
        sect = SECTION.match(line)
        if sect:
            finish_question()
            current["section"] = (
                "Section " + sect.group(1) + ": " + sect.group(2)
            )[:80]
            current["capture"] = True
            continue
        if current["collection"] and not current["capture"]:
            continue

        labels = NUMBER_LABEL.findall(line)
        if labels and len(labels) >= 2:
            maybe = {code: label.strip() for code, label in labels}
            nums = sorted(map(int, maybe))
            if nums == list(range(nums[0], nums[-1]+1)) and 2 <= len(nums) <= 11:
                current["codes"] = maybe
                continue
        # A short UCLA form writes anchors one per line: 1- Never.
        single_code = re.fullmatch(
            r"([0-9]|10)\s*[-–]\s*([A-Za-z][A-Za-z ]{2,25})", line
        )
        if single_code:
            current["codes"][single_code.group(1)] = single_code.group(2)
            continue
        if line.lower() in ("yes no", "yes / no", "yes  no"):
            current["warnings"].append(
                "Yes/No column headers found; answer semantics require review."
            )
            continue
        if re.search(r"copyright|for researchers only|purchase only", line, re.I):
            current["warnings"].append(
                "Review copyright/licensing before reproducing this scale."
            )
        if "reverse" in line.lower() or re.search(
            r"\bitems?\s+\d+(?:\s*,\s*\d+)+\s+are", line, re.I
        ):
            current["context"].append(line)

        expected = (
            current["pending"]["number"] + 1
            if current["pending"] else
            current["rows"][-1].number + 1
            if current["rows"] else 1
        )
        detected = _numbered(raw, expected)
        if detected:
            finish_question()
            n, prompt, starred = detected
            if starred:
                current["reverse"].add(n)
            current["pending"] = {
                "number": n, "prompt": prompt, "page": page,
                "excerpt": line[:300], "confidence": "review",
                "options": [], "notes": [],
            }
            # Inline checkbox on antiword table row.
            if "|" in raw and "[ " in raw:
                labels = re.findall(r"\[\s*\]\s*([^|]+)", raw)
                current["pending"]["options"].extend(
                    x.strip() for x in labels if x.strip()
                )
            continue
        if current["pending"] is None:
            continue
        answer = CHOICE.match(line)
        if answer:
            if len(current["pending"]["options"]) < 12:
                current["pending"]["options"].append(answer.group(1).strip())
            continue
        if line.lstrip().startswith("|") and "[ " in line:
            labels = re.findall(r"\[\s*\]\s*([^|]+)", line)
            current["pending"]["options"].extend(
                x.strip() for x in labels if x.strip()
            )
            continue
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
        page_count, image_pages,
    )


def reviewed_draft(
    candidate: InstrumentCandidate, *,
    accept_numeric: bool = False,
    accept_reverse: bool = False,
) -> list[dict]:
    """Only apply a scoring proposal with explicit confirmation."""
    from copy import deepcopy
    raw = [deepcopy(row.question) for row in candidate.questions]
    if not accept_numeric:
        for q in raw:
            if q["kind"] == "rating_scale":
                q["kind"] = "single_choice"
                q["options"] = [
                    f"{code}: {label}"
                    for code, label in candidate.scoring.code_labels
                ]
                q.pop("value_labels", None)
                q.pop("scale_id", None)
                q["reverse_scored"] = False
    elif accept_reverse:
        reversed_numbers = set(candidate.scoring.reverse_numbers)
        for row, question in zip(candidate.questions, raw):
            question["reverse_scored"] = (
                question["kind"] == "rating_scale" and
                row.number in reversed_numbers
            )
    return validate_questions(raw)
