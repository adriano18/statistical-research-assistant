"""Local page rendering, optional Tesseract OCR, and pre-publication edits.

No network calls, cloud OCR, or automatic verification of questionnaire
scoring. PDF pages are rendered via PDFium. Word previews reconstruct visible
paragraph/table blocks in an image; they are NOT pixel-identical Word pages.
"""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import re
import shutil
import subprocess
import textwrap
import threading
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from ocr_layout import (
    OCRPage, PSYCHOMETRIC_NOTICE, aggregate_confidence, link_candidates,
    page_from_plain_text, page_from_positioned_words, parse_tesseract_tsv,
)
from matrix_reconstruction import docx_matrices, geometric_matrices
from ocr_runtime import (
    OCRCancelled, OCRConfigurationError, resolve_tesseract, run_tesseract,
    tesseract_available as _runtime_available,
)

from scientific_survey_import import (
    Candidate, InstrumentCandidate, ScientificDocumentReview,
    MAX_BYTES, MAX_PAGES, parse_scientific_lines,
)
from survey_storage import validate_questions

MAX_BATCH_PAGES = 20
OCR_LANGUAGES = {"eng", "lav", "rus", "eng+lav", "eng+rus", "lav+rus", "eng+lav+rus"}
MAX_RENDER_PIXELS = 5_000_000
MAX_PNG_BYTES = 12_000_000
MAX_TEXT_LAYER_CHARS = 120_000
ROTATIONS = (0, 90, 180, 270)


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
    max_width: int = 1300, rotation: int = 0,
) -> bytes:
    """Render a bounded, real PDF page as PNG, using a 1-based page index.

    ``rotation`` (clockwise 0/90/180/270) is a *view* rotation for sideways
    scans; the source PDF is never modified.
    """
    return _render_pdf_page(
        source, page_number, scale=scale, max_width=max_width,
        rotation=rotation,
    )[0]


def _render_pdf_page(
    source: bytes, page_number: int, *, scale: float, max_width: int,
    rotation: int = 0,
) -> tuple[bytes, float]:
    if not 0.5 <= scale <= 3.0:
        raise ValueError("Page scale must be between 0.5 and 3.")
    if rotation not in ROTATIONS:
        raise ValueError("Rotation must be 0, 90, 180 or 270 degrees.")
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
            shown_width = height if rotation in (90, 270) else width
            safe_scale = min(
                scale, max_width / shown_width,
                (MAX_RENDER_PIXELS / (width * height)) ** 0.5,
            )
            if safe_scale <= 0:
                raise ValueError("Cannot render this oversized page.")
            image = page.render(scale=safe_scale, rotation=rotation).to_pil()
            try:
                out = BytesIO()
                image.convert("RGB").save(out, "PNG", optimize=True)
                data = out.getvalue()
                if len(data) > MAX_PNG_BYTES:
                    raise ValueError("Rendered page exceeds the image size limit.")
                return data, 72.0 * safe_scale
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
    # antiword is more reliable with a real filename, including on Windows.
    # The local temporary source is removed immediately after extraction.
    with TemporaryDirectory(prefix="word-review-") as folder:
        target = Path(folder) / "source.doc"
        target.write_bytes(source)
        proc = subprocess.run(
            [tesseract_independent, "-w", "110", str(target)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=15, check=False,
        )
    if proc.returncode:
        raise ValueError("Could not decode this .doc; convert to .docx.")
    return proc.stdout.decode("utf-8", errors="replace").splitlines()


WORD_LINES_PER_SEGMENT = 42


def _visual_word_lines(source: bytes, suffix: str) -> list[str]:
    if len(source) > MAX_BYTES:
        raise ValueError("Word file exceeds the import size limit.")
    lines = _word_text(source, suffix)
    if not lines:
        raise ValueError("Word document has no visible paragraphs or table cells.")
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=87) or [""])
        wrapped.append("")
        if len(wrapped) > WORD_LINES_PER_SEGMENT * MAX_PAGES:
            raise ValueError("Word document exceeds 80 visual preview segments.")
    return wrapped


def word_structure_page_count(source: bytes, suffix: str) -> int:
    """Count synthetic visual segments; NOT physical pages in the Word file."""
    length = len(_visual_word_lines(source, suffix))
    return (length + WORD_LINES_PER_SEGMENT-1) // WORD_LINES_PER_SEGMENT


def _word_font(size: int):
    for name in (
        "DejaVuSans.ttf", r"C:\Windows\Fonts\segoeui.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "LiberationSans-Regular.ttf",
    ):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_word_structure(
    source: bytes, suffix: str, page_number: int = 1,
) -> bytes:
    """Render a Word text segment as PNG, with honest pagination labeling."""
    lines = _visual_word_lines(source, suffix)
    segments = (len(lines) + WORD_LINES_PER_SEGMENT-1) // WORD_LINES_PER_SEGMENT
    if not 1 <= page_number <= segments:
        raise ValueError("Document page unavailable.")
    width, height = 1100, 1520
    image = Image.new("RGB", (width, height), "white")
    canvas = ImageDraw.Draw(image)
    font, hint = _word_font(19), _word_font(16)
    canvas.text(
        (50, 28),
        f"WORD STRUCTURE · segment {page_number}/{segments} "
        "— not original page layout",
        fill="#915E2C", font=hint,
    )
    canvas.line([(50, 65), (1050, 65)], fill="#CFD5DD", width=2)
    y = 100
    begin = (page_number-1) * WORD_LINES_PER_SEGMENT
    for line in lines[begin:begin+WORD_LINES_PER_SEGMENT]:
        if line.strip():
            canvas.text((54, y), line[:110], fill="#263748", font=font)
        y += 32
    if segments > 1:
        canvas.text(
            (54, height-45), "Use the segment selector for more source text.",
            fill="#915E2C", font=hint,
        )
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_document_page(
    source: bytes, filename: str, page_number: int, *, rotation: int = 0,
) -> bytes:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return render_pdf_page(source, page_number, rotation=rotation)
    if ext in {".docx", ".doc"}:
        return render_word_structure(source, ext, page_number)
    raise ValueError("Document page unavailable.")


def tesseract_available() -> bool:
    """True when a bundled, overridden or system Tesseract can be resolved."""
    return _runtime_available()


def _check_ocr_input(png: bytes, language: str) -> None:
    if language not in OCR_LANGUAGES:
        raise ValueError("Unsupported OCR language selection.")
    if not 0 < len(png) <= MAX_PNG_BYTES:
        raise ValueError("OCR input image exceeds the limit.")


def _run_ocr(png: bytes, language: str, extra: list[str], *, timeout: int,
             cancel: threading.Event | None, dpi: float | None) -> str:
    try:
        runtime = resolve_tesseract()
    except OCRConfigurationError as error:
        raise RuntimeError(
            f"{error} Alternatively select a document with a text layer."
        ) from error
    arguments = ["{image}", "stdout", "-l", language, "--psm", "6"]
    if dpi:
        arguments += ["--dpi", str(int(min(max(dpi, 70), 600)))]
    code, output, diagnostic = run_tesseract(
        runtime, arguments + extra, image=png, timeout=timeout, cancel=cancel,
    )
    if code:
        raise RuntimeError(
            "Local OCR failed. Confirm the Tesseract path and installed "
            f"language packs. {diagnostic[:350]}"
        )
    return output.decode("utf-8-sig", errors="replace")


def recognize_page(
    png: bytes, language: str = "eng", *, timeout: int = 60,
    cancel: threading.Event | None = None,
) -> str:
    """Call a LOCAL Tesseract engine for plain text; never a remote provider."""
    _check_ocr_input(png, language)
    text = _run_ocr(png, language, [], timeout=timeout, cancel=cancel,
                    dpi=None).strip()
    if not text:
        raise ValueError(
            "OCR found no selectable characters on this page. "
            "Try a clearer scan or edit the questionnaire manually."
        )
    return text


def recognize_page_layout(
    png: bytes, language: str = "eng", *, page_number: int = 1,
    dpi: float | None = None, rotation: int = 0, timeout: int = 90,
    cancel: threading.Event | None = None,
) -> OCRPage:
    """Local Tesseract TSV: words with boxes and raw confidence."""
    _check_ocr_input(png, language)
    tsv = _run_ocr(
        png, language,
        ["-c", "tessedit_create_tsv=1", "-c", "tessedit_create_txt=0"],
        timeout=timeout, cancel=cancel, dpi=dpi,
    )
    page = parse_tesseract_tsv(
        tsv, page_number, language=language, rotation=rotation,
        engine="tesseract",
    )
    if not page.words:
        raise ValueError(
            "OCR found no characters on this page. Try a clearer scan, "
            "another rotation or edit the questionnaire manually."
        )
    return page


def _rotate_point(x: float, y: float, rotation: int) -> tuple[float, float]:
    """Map a normalized unrotated point into the clockwise-rotated view."""
    if rotation == 90:
        return 1 - y, x
    if rotation == 180:
        return 1 - x, 1 - y
    if rotation == 270:
        return y, 1 - x
    return x, y


def pdf_text_layer_page(
    source: bytes, page_number: int, *, rotation: int = 0,
) -> OCRPage:
    """Selectable-text geometry from PDFium in rendered-page coordinates.

    Text-layer words have no OCR score (``confidence is None``).
    """
    import pypdfium2.raw as pdfium_c

    if rotation not in ROTATIONS:
        raise ValueError("Rotation must be 0, 90, 180 or 270 degrees.")
    pdf = _pdf(source)
    try:
        if not 1 <= page_number <= min(len(pdf), MAX_PAGES):
            raise ValueError("PDF page outside the permitted range.")
        page = pdf[page_number - 1]
        try:
            width, height = page.get_size()
            view = (page.get_rotation() + rotation) % 360
            textpage = page.get_textpage()
            try:
                count = min(textpage.count_chars(), MAX_TEXT_LAYER_CHARS)
                words: list[tuple[str, tuple]] = []
                current, box = [], None
                previous_right = None
                word_height = 0.0

                def flush():
                    nonlocal current, box
                    if current and box is not None:
                        words.append(("".join(current), box))
                    current, box = [], None

                for index in range(count):
                    char = chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, index) or 32)
                    if char.isspace() or char == "\x00":
                        flush()
                        previous_right = None
                        word_height = 0.0
                        continue
                    left, bottom, right, top = textpage.get_charbox(index)
                    if right <= left or top <= bottom:
                        continue
                    if previous_right is not None and (
                        left < previous_right - 2
                        or left > previous_right + 0.3 * max(top - bottom, word_height)
                    ):
                        flush()  # new line or a visible gap without a space
                        word_height = 0.0
                    corners = [
                        _rotate_point(left / width, 1 - top / height, view),
                        _rotate_point(right / width, 1 - bottom / height, view),
                    ]
                    char_box = (
                        min(c[0] for c in corners), min(c[1] for c in corners),
                        max(c[0] for c in corners), max(c[1] for c in corners),
                    )
                    box = char_box if box is None else (
                        min(box[0], char_box[0]), min(box[1], char_box[1]),
                        max(box[2], char_box[2]), max(box[3], char_box[3]),
                    )
                    current.append(char)
                    previous_right = right
                    word_height = max(word_height, top - bottom)
                flush()
            finally:
                textpage.close()
        finally:
            page.close()
    finally:
        pdf.close()
    shown = (height, width) if view in (90, 270) else (width, height)
    safe = []
    for text, (x0, y0, x1, y1) in words:
        if x1 - x0 < 0.002:
            x1 = min(1.0, x0 + 0.002)
        if y1 - y0 < 0.002:
            y1 = min(1.0, y0 + 0.002)
        safe.append((text, (x0, y0, x1, y1)))
    return page_from_positioned_words(
        page_number, safe, pixel_width=int(shown[0]), pixel_height=int(shown[1]),
        rotation=rotation,
    )


def attach_text_layer_geometry(
    review: ScientificDocumentReview, source: bytes,
) -> ScientificDocumentReview:
    """Link text-based PDF candidates to their positions (no OCR scores)."""
    pages = []
    for number in range(1, min(review.page_count, MAX_PAGES) + 1):
        try:
            layer = pdf_text_layer_page(source, number)
        except (ValueError, RuntimeError):
            continue
        if layer.words:
            pages.append(layer)
    if not pages:
        return review
    return replace(
        review, spatial=link_candidates(review, pages),
        matrices=geometric_matrices(pages),
    )


def attach_docx_matrices(
    review: ScientificDocumentReview, source: bytes,
) -> ScientificDocumentReview:
    """Attach native Word-table matrix proposals (preferred over geometry)."""
    try:
        found = docx_matrices(source)
    except Exception:  # damaged tables must not block ordinary import
        return review
    return replace(review, matrices=found) if found else review


def ocr_confidence_warning(review: ScientificDocumentReview) -> str | None:
    evidence = review.spatial
    if evidence is None:
        return None
    words = [w for page in evidence.pages for w in page.words
             if page.source == "tesseract_tsv"]
    if not words:
        return None
    overall = aggregate_confidence(words)
    return (
        f"Page OCR word confidence: {overall.describe()}. "
        + PSYCHOMETRIC_NOTICE
    )


def ocr_scientific_pdf(
    source: bytes, filename: str, selected_pages: list[int], language: str,
    *, recognizer: Callable[[bytes, str], str | OCRPage] | None = None,
    rotation: int = 0, cancel: threading.Event | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> ScientificDocumentReview:
    """Overlay approved local OCR output on selected pages, keeping source pages.

    All other pages retain their original selectable text; this allows a
    scanned second page in a partly searchable PDF to be reconstructed.
    A fresh candidate review is mandatory and prior approvals are reset.
    The result carries :class:`ocr_layout.SpatialEvidence` in ``spatial``.
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
    if rotation not in ROTATIONS:
        raise ValueError("Rotation must be 0, 90, 180 or 270 degrees.")
    reader = PdfReader(BytesIO(source))
    if reader.is_encrypted:
        raise ValueError("Cannot OCR an encrypted PDF.")
    lines = []
    geometry: list[OCRPage] = []
    done = 0
    for n in range(1, count + 1):
        if n in pages:
            if cancel is not None and cancel.is_set():
                raise OCRCancelled("OCR was cancelled. No results were applied.")
            png, dpi = _render_pdf_page(
                source, n, scale=2.0, max_width=1800, rotation=rotation,
            )
            if recognizer is None:
                result = recognize_page_layout(
                    png, language, page_number=n, dpi=dpi, rotation=rotation,
                    cancel=cancel,
                )
            else:
                result = recognizer(png, language)
            if isinstance(result, OCRPage):
                page_layout = replace(result, page_number=n) if (
                    result.page_number != n
                ) else result
            else:
                page_layout = page_from_plain_text(n, str(result))
            geometry.append(page_layout)
            lines.extend((n, line.text) for line in page_layout.lines)
            done += 1
            if progress is not None:
                progress(done, len(pages))
        else:
            extracted = reader.pages[n-1].extract_text() or ""
            lines.extend((n, line) for line in extracted.splitlines())
            if extracted.strip():
                try:
                    geometry.append(pdf_text_layer_page(source, n))
                except (ValueError, RuntimeError):
                    pass
    matrices = geometric_matrices(geometry)
    try:
        review = parse_scientific_lines(
            lines, filename, page_count=count,
        )
    except ValueError:
        if not matrices:
            raise
        # Grid rows without recognizable numbering: keep matrix proposals.
        review = ScientificDocumentReview(
            filename, (), (
                "No numbered question lines were recognized; only response-"
                "matrix proposals are available. Verify them manually.",
            ), count,
        )
    review = replace(
        review, spatial=link_candidates(review, geometry), matrices=matrices,
    )
    confidence_note = ocr_confidence_warning(review)
    return replace(
        review,
        warnings=(
            "Local OCR text may contain substitutions, missing rows or "
            "incorrect item boundaries. Compare EVERY question to the "
            "rendered source before approving version, scoring or publishing.",
            f"OCR pages: {', '.join(str(p) for p in pages)}. "
            f"Language: {language}. Results were processed locally.",
            *((confidence_note,) if confidence_note else ()),
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
