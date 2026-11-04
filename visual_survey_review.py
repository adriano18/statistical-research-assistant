"""Local page rendering, optional Tesseract OCR, and pre-publication edits.

No network calls, cloud OCR, or automatic verification of questionnaire
scoring. PDF pages are rendered via PDFium. Word previews reconstruct visible
paragraph/table blocks in an image; they are NOT pixel-identical Word pages.
"""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import os
import re
import shutil
import subprocess
import textwrap
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from scientific_survey_import import (
    Candidate, InstrumentCandidate, ScientificDocumentReview,
    MAX_BYTES, MAX_PAGES, parse_scientific_lines,
)
from survey_storage import validate_questions

MAX_BATCH_PAGES = 20
OCR_LANGUAGES = {"eng", "lav", "rus", "eng+lav", "eng+rus", "lav+rus", "eng+lav+rus"}
MAX_RENDER_PIXELS = 5_000_000
MAX_PNG_BYTES = 12_000_000


def load_document_bytes(path: str | Path) -> bytes:
    source = Path(path)
    if source.suffix.lower() not in {".pdf", ".docx", ".doc"}:
        raise ValueError("Open a PDF, DOCX or DOC document.")
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_BYTES:
        raise ValueError("Source must exist and be at most 20 MB.")
    return source.read_bytes()


def _pdf(source: bytes):
    import pypdfium2 as pdfium

    if not source or len(source) > MAX_BYTES:
        raise ValueError("PDF is empty or over the 20 MB limit.")
    return pdfium.PdfDocument(source)


def pdf_page_count(source: bytes) -> int:
    pdf = _pdf(source)
    try:
        n = len(pdf)
        if n > MAX_PAGES:
            raise ValueError("PDF exceeds the 80-page review limit.")
        return n
    finally:
        pdf.close()


def render_pdf_page(
    source: bytes, page_number: int, *, scale: float = 1.4,
    max_width: int = 1300,
) -> bytes:
    """Render a bounded, real PDF page as PNG, using a 1-based page index."""
    if not 0.5 <= scale <= 3.0:
        raise ValueError("Page scale must be between 0.5 and 3.")
    pdf = _pdf(source)
    try:
        n = len(pdf)
        if n > MAX_PAGES or not 1 <= page_number <= n:
            raise ValueError("PDF page outside the permitted range.")
        page = pdf[page_number - 1]
        try:
            width, height = page.get_size()
            if not 0 < width <= 20000 or not 0 < height <= 20000:
                raise ValueError("Invalid PDF page size.")
            safe_scale = min(
                scale, max_width / width,
                (MAX_RENDER_PIXELS / (width * height)) ** 0.5,
            )
            if safe_scale <= 0:
                raise ValueError("Cannot render this oversized page.")
            image = page.render(scale=safe_scale).to_pil()
            try:
                out = BytesIO()
                image.convert("RGB").save(out, "PNG", optimize=True)
                data = out.getvalue()
                if len(data) > MAX_PNG_BYTES:
                    raise ValueError("Rendered page exceeds the image size limit.")
                return data
            finally:
                image.close()
        finally:
            page.close()
    finally:
        pdf.close()


def _word_text(source: bytes, suffix: str) -> list[str]:
    if suffix.lower() == ".docx":
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(BytesIO(source))
        lines = []
        for block in doc.iter_inner_content():
            if isinstance(block, Paragraph) and block.text.strip():
                lines.append(block.text.strip())
            elif isinstance(block, Table):
                for row in block.rows:
                    text = "  |  ".join(
                        c.text.strip() for c in row.cells if c.text.strip()
                    )
                    if text:
                        lines.append(text)
        return lines
    if suffix.lower() != ".doc":
        raise ValueError("Unsupported Word document.")
    tesseract_independent = shutil.which("antiword")
    if tesseract_independent is None:
        raise ValueError("For .doc visual review, install antiword or save as .docx.")
    # Avoid writing a confidential temporary document: antiword reads stdin.
    proc = subprocess.run(
        [tesseract_independent, "-w", "110", "-"],
        input=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15, check=False,
    )
    if proc.returncode:
        raise ValueError("Could not decode this .doc; convert to .docx.")
    return proc.stdout.decode("utf-8", errors="replace").splitlines()


def render_word_structure(source: bytes, suffix: str) -> bytes:
    """Read-only visual reconstruction; physical Word pagination is unknown."""
    if len(source) > MAX_BYTES:
        raise ValueError("Word file exceeds the import size limit.")
    lines = _word_text(source, suffix)
    if not lines:
        raise ValueError("Word document has no visible paragraphs or table cells.")
    width, height = 1100, 1520
    image = Image.new("RGB", (width, height), "white")
    canvas = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=19)
    hint = ImageFont.load_default(size=16)
    canvas.text((50, 28), "WORD STRUCTURE PREVIEW — not original page layout",
                fill="#915E2C", font=hint)
    canvas.line([(50, 65), (1050, 65)], fill="#CFD5DD", width=2)
    y = 100
    for source_line in lines[:500]:
        for line in textwrap.wrap(source_line, width=87) or [""]:
            if y > height - 60:
                break
            canvas.text((54, y), line[:110], fill="#263748", font=font)
            y += 26
        y += 10
        if y > height - 60:
            break
    if y > height - 100 or len(lines) > 55:
        canvas.text((54, height-46), "Additional content is in the editable question list.",
                    fill="#9B4C32", font=hint)
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_document_page(source: bytes, filename: str, page_number: int) -> bytes:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return render_pdf_page(source, page_number)
    if ext in {".docx", ".doc"} and page_number == 1:
        return render_word_structure(source, ext)
    raise ValueError("Document page unavailable.")


def tesseract_available() -> bool:
    return bool(os.environ.get("TESSERACT_CMD") or shutil.which("tesseract"))


def recognize_page(
    png: bytes, language: str = "eng", *, timeout: int = 60,
) -> str:
    """Call an installed LOCAL Tesseract CLI; never transmit to a provider."""
    if language not in OCR_LANGUAGES:
        raise ValueError("Unsupported OCR language selection.")
    if not 0 < len(png) <= MAX_PNG_BYTES:
        raise ValueError("OCR input image exceeds the limit.")
    binary = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
    if not binary:
        raise RuntimeError(
            "Local Tesseract OCR is not installed. Install Tesseract and "
            "the chosen language packs, restart the application, or select "
            "a document with a text layer."
        )
    try:
        result = subprocess.run(
            [binary, "stdin", "stdout", "-l", language, "--psm", "6"],
            input=png, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Local OCR failed or exceeded its time limit.") from error
    if result.returncode:
        diagnostic = result.stderr.decode("utf-8", "replace").strip()[:350]
        raise RuntimeError(
            "Local OCR failed. Confirm the Tesseract path and installed "
            f"language packs. {diagnostic}"
        )
    text = result.stdout.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise ValueError(
            "OCR found no selectable characters on this page. "
            "Try a clearer scan or edit the questionnaire manually."
        )
    return text


def ocr_scientific_pdf(
    source: bytes, filename: str, selected_pages: list[int], language: str,
    *, recognizer: Callable[[bytes, str], str] = recognize_page,
) -> ScientificDocumentReview:
    """Overlay approved local OCR output on selected pages, keeping source pages.

    All other pages retain their original selectable text; this allows a
    scanned second page in a partly searchable PDF to be reconstructed.
    A fresh candidate review is mandatory and prior approvals are reset.
    """
    from pypdf import PdfReader

    count = pdf_page_count(source)
    pages = sorted(set(selected_pages))
    if not pages or len(pages) > MAX_BATCH_PAGES or any(
        not isinstance(page, int) or not 1 <= page <= count for page in pages
    ):
        raise ValueError("Choose 1–20 valid PDF pages for local OCR.")
    if language not in OCR_LANGUAGES:
        raise ValueError("Choose an installed OCR language.")
    reader = PdfReader(BytesIO(source))
    if reader.is_encrypted:
        raise ValueError("Cannot OCR an encrypted PDF.")
    lines = []
    for n in range(1, count + 1):
        if n in pages:
            png = render_pdf_page(source, n, scale=2.0, max_width=1800)
            extracted = recognizer(png, language)
        else:
            extracted = reader.pages[n-1].extract_text() or ""
        lines.extend((n, line) for line in extracted.splitlines())
    review = parse_scientific_lines(
        lines, filename, page_count=count,
    )
    return replace(
        review,
        warnings=(
            "Local OCR text may contain substitutions, missing rows or "
            "incorrect item boundaries. Compare EVERY question to the "
            "rendered source before approving version, scoring or publishing.",
            f"OCR pages: {', '.join(str(p) for p in pages)}. "
            f"Language: {language}. Results were processed locally.",
            *review.warnings,
        ),
    )


def edit_candidate_question(
    candidate: InstrumentCandidate, index: int, *,
    prompt: str, kind: str, options_text: str, section: str,
    required: bool = False,
) -> InstrumentCandidate:
    """Apply an atomic local edit to a selected candidate, preserving source."""
    if not 0 <= index < len(candidate.questions):
        raise IndexError("Select a valid question.")
    allowed = {
        "short_text", "long_text", "single_choice", "multiple_choice",
        "yes_no", "number", "rating_scale",
    }
    if kind not in allowed:
        raise ValueError("Choose a supported response type.")
    q = dict(candidate.questions[index].question)
    q.update({
        "prompt": prompt.strip(), "kind": kind, "section": section.strip(),
        "required": bool(required),
    })
    if kind in {"single_choice", "multiple_choice"}:
        options = [x.strip() for x in options_text.splitlines() if x.strip()]
        q["options"] = options
        q.pop("value_labels", None)
        q.pop("scale_id", None)
        q["reverse_scored"] = False
    elif kind == "rating_scale":
        # Numeric labels must already be an explicitly detected proposal.
        if not candidate.scoring.code_labels:
            raise ValueError(
                "No numeric codebook was detected. Set scale values "
                "later in the questionnaire editor."
            )
        q["value_labels"] = dict(candidate.scoring.code_labels)
        q["scale_id"] = q.get("scale_id") or "import_scale"
        q["reverse_scored"] = False
        q.pop("options", None)
    else:
        for name in ("options", "value_labels", "scale_id"):
            q.pop(name, None)
        q["reverse_scored"] = False
    # Validate the entire draft BEFORE replacing a single immutable candidate.
    proposal = list(candidate.questions)
    row = proposal[index]
    proposal[index] = replace(
        row, question=q, confidence="review",
        notes=(*row.notes, "Edited manually; verify against source."),
    )
    validate_questions([item.question for item in proposal])
    return replace(candidate, questions=tuple(proposal))
