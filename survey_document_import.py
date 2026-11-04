"""Offline, conservative conversion of existing DOCX/PDF questions to drafts.

Never interpret a document as a validated questionnaire. No OCR, LLM, network,
or automatic scale coding. A researcher must review the resulting draft.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from survey_storage import validate_questions

MAX_FILE_BYTES = 20_000_000
MAX_PDF_PAGES = 80
MAX_QUESTIONS = 120
QUESTION = re.compile(
    r"^\s*(?:(?:Q|Question|Вопрос|Jautājums)\s*\d{1,3}|"
    r"\d{1,3})\s*[.):\-]\s*(.{2,})\s*$", re.I
)
OPTION = re.compile(
    r"^\s*(?:[A-Ha-h][.)]|[□☐◯○●•]|[-–])\s+(.{1,120})\s*$"
)
MULTI = re.compile(
    r"(?:choose|select|tick)\s+all|multiple answers|"
    r"выберите все|несколько вариантов|atzīmējiet visus",
    re.I,
)


@dataclass(frozen=True)
class DocumentSurveyDraft:
    source_name: str
    questions: tuple[dict, ...]
    notes: tuple[str, ...]
    lines_read: int


def _docx_lines(path: Path) -> list[str]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    doc = Document(path)
    lines = []
    for item in doc.iter_inner_content():
        if isinstance(item, Paragraph):
            lines.extend(item.text.splitlines())
        elif isinstance(item, Table):
            # Table cells often hold questionnaires: one question or option
            # per row. Keep order, but never infer a scoring scale from cells.
            for row in item.rows:
                values = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                lines.extend(values)
    return lines


def _pdf_lines(path: Path) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDF cannot be imported.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError("PDF exceeds the 80-page import limit.")
    lines = []
    for page in reader.pages:
        lines.extend((page.extract_text() or "").splitlines())
    return lines


def parse_question_lines(lines: list[str], source_name: str) -> DocumentSurveyDraft:
    if len(lines) > 30_000:
        raise ValueError("Document contains too many lines.")
    cleaned = [" ".join(line.strip().split()) for line in lines if line.strip()]
    if not cleaned:
        raise ValueError(
            "No selectable text found. Scanned PDFs need external OCR "
            "and a manual review before importing."
        )
    found = []
    active = None
    unrecognized = 0

    def finish():
        nonlocal active
        if active is not None:
            found.append(active)
        active = None

    for line in cleaned:
        match = QUESTION.match(line)
        if match:
            finish()
            prompt = match.group(1).strip()
            if len(prompt) > 300:
                raise ValueError("A question exceeds the 300-character editor limit.")
            active = {"prompt": prompt, "options": []}
            if len(found) + 1 > MAX_QUESTIONS:
                raise ValueError("Document exceeds the 120-question import limit.")
            continue
        if active is None:
            unrecognized += 1
            continue
        answer = OPTION.match(line)
        if answer and len(active["options"]) < 12:
            active["options"].append(answer.group(1).strip())
        elif line.endswith("?") and not active["options"]:
            # A wrapped question, only when it is clearly a continuation.
            revised = active["prompt"] + " " + line
            if len(revised) <= 300:
                active["prompt"] = revised
            else:
                unrecognized += 1
        else:
            unrecognized += 1
    finish()

    if not found:
        raise ValueError(
            "No numbered questions detected. Number each question "
            "('1. Question?', 'Q2: ...') and import again, or add it manually."
        )
    candidates = []
    warnings = [
        "Imported questions are an UNVALIDATED editable draft. Check every "
        "prompt, choice, consent rule, scoring key, page and conditional rule.",
        "Question numbers were converted to neutral variable keys; "
        "required flags default to False.",
    ]
    if unrecognized:
        warnings.append(
            f"{unrecognized} non-question/option lines were not converted. "
            "Compare the draft with the original document."
        )
    for i, item in enumerate(found, 1):
        opts = list(dict.fromkeys(item["options"]))
        if len(opts) >= 2:
            kind = "multiple_choice" if MULTI.search(item["prompt"]) else "single_choice"
        else:
            kind = "short_text"
            if opts:
                warnings.append(
                    f"Question {i}: only one answer choice found. "
                    "Imported as text; review the omitted choice."
                )
        entry = {
            "key": f"import_q{i:03d}", "prompt": item["prompt"],
            "kind": kind, "required": False,
            "page": 1, "section": "Imported questions",
        }
        if kind in {"single_choice", "multiple_choice"}:
            entry["options"] = opts
        candidates.append(entry)
    validated = validate_questions(candidates)
    warnings.append(
        "Printed Likert values and reverse-scored items are NOT inferred. "
        "Set numeric scale codes and any conditions manually."
    )
    return DocumentSurveyDraft(
        source_name, tuple(validated), tuple(warnings), len(cleaned),
    )


def read_survey_document(path: str | Path) -> DocumentSurveyDraft:
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() not in {".docx", ".pdf"}:
        raise ValueError("Choose a DOCX or text-based PDF questionnaire.")
    size = source.stat().st_size
    if not 0 < size <= MAX_FILE_BYTES:
        raise ValueError("Document must be non-empty and at most 20 MB.")
    try:
        lines = (
            _docx_lines(source) if source.suffix.lower() == ".docx"
            else _pdf_lines(source)
        )
    except (OSError, ValueError):
        raise
    except Exception as error:
        raise ValueError(
            f"Could not read this document: {type(error).__name__}"
        ) from error
    return parse_question_lines(lines, source.name)
