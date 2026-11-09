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
import shutil
import subprocess
import textwrap
import threading
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from letter_spacing import repair_pdf_text, spurious_space_indices
from ocr_layout import (
    OCRPage, PSYCHOMETRIC_NOTICE, aggregate_confidence, link_candidates,
    page_from_plain_text, page_from_positioned_words, parse_tesseract_tsv,
)
from matrix_reconstruction import (
    choice_cell_grid, choice_grid_lines, docx_matrices, geometric_matrices,
)
from ocr_table_rows import attach_row_regions, page_geometry, reconstruct_tables
from ocr_runtime import (
    OCRCancelled, OCRConfigurationError, resolve_tesseract, run_tesseract,
    tesseract_available as _runtime_available,
)

from scientific_survey_import import (
    InstrumentCandidate, LEGACY_DOC_FAILED, LEGACY_DOC_UNREADABLE,
    LegacyDocUnavailable, ScientificDocumentReview, MAX_BYTES, MAX_PAGES,
    parse_scientific_lines, with_spacing_repairs,
)
from survey_storage import validate_questions

MAX_BATCH_PAGES = 20
# Tesseract 5.5 strongly prefers the FIRST language of a combination: with
# "eng+lav" Latvian diacritics are replaced by English look-alikes (ē → é).
# The UI therefore offers the document's main language first; the older
# English-first strings stay accepted for compatibility.
OCR_LANGUAGES = {
    "eng", "lav", "rus", "lav+eng", "rus+eng", "lav+rus", "rus+lav",
    "lav+rus+eng", "rus+lav+eng",
    "eng+lav", "eng+rus", "eng+lav+rus",
}
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


def pdf_image_coverage(source: bytes) -> dict[int, float]:
    """Share of each page's area covered by the raster images it DRAWS.

    1-based page → share in (0, 1]; pages without images are absent.
    Unlike pypdf's ``page.images``, which lists every image of a resource
    dictionary that several pages may share, this measures placed images,
    so a page-sized scan and a small logo can be told apart.
    """
    import pypdfium2.raw as pdfium_c

    pdf = _pdf(source)
    try:
        if len(pdf) > MAX_PAGES:
            raise ValueError("PDF exceeds the 80-page review limit.")
        shares = {}
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                width, height = page.get_size()
                area = 0.0
                for image in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
                    # pypdfium2 5 renamed PdfObject.get_pos() to get_bounds().
                    bounds = getattr(image, "get_bounds", None) or image.get_pos
                    left, bottom, right, top = bounds()
                    area += max(0.0, right - left) * max(0.0, top - bottom)
                if area > 0 and width > 0 and height > 0:
                    shares[index + 1] = min(1.0, area / (width * height))
            finally:
                page.close()
        return shares
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
    # The only converter is a locally installed antiword; packaged Windows
    # builds have none, so the error must say how to continue.
    tesseract_independent = shutil.which("antiword")
    if tesseract_independent is None:
        raise LegacyDocUnavailable(LEGACY_DOC_UNREADABLE)
    # antiword is more reliable with a real filename, including on Windows.
    # The local temporary source is removed immediately after extraction.
    with TemporaryDirectory(prefix="word-review-") as folder:
        target = Path(folder) / "source.doc"
        target.write_bytes(source)
        try:
            proc = subprocess.run(
                [tesseract_independent, "-w", "110", str(target)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=15, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise LegacyDocUnavailable(LEGACY_DOC_FAILED) from error
    if proc.returncode:
        raise LegacyDocUnavailable(LEGACY_DOC_FAILED)
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
    dpi: float | None = None, rotation: int = 0, timeout: int = 180,
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
            page_rotation = page.get_rotation()
            if page_rotation in (90, 270):
                # get_size() is the displayed size; character boxes use the
                # page's unrotated user space.
                width, height = height, width
            view = (page_rotation + rotation) % 360
            textpage = page.get_textpage()
            try:
                count = min(textpage.count_chars(), MAX_TEXT_LAYER_CHARS)
                # Whitespace that splits a word spuriously ("sched ule" in a
                # letter-spaced text layer) does not end the word.
                try:
                    spurious = spurious_space_indices(textpage, max_chars=count)
                except Exception:
                    spurious = set()
                words: list[tuple[str, tuple]] = []
                current, box = [], None
                previous_right = previous_loose_right = None
                word_height = 0.0
                rejoined = False

                def flush():
                    nonlocal current, box
                    if current and box is not None:
                        words.append(("".join(current), box))
                    current, box = [], None

                for index in range(count):
                    char = chr(pdfium_c.FPDFText_GetUnicode(textpage.raw, index) or 32)
                    if char.isspace() or char == "\x00":
                        if index in spurious and current:
                            rejoined = True
                            continue
                        flush()
                        previous_right = None
                        word_height = 0.0
                        continue
                    left, bottom, right, top = textpage.get_charbox(index)
                    if right <= left or top <= bottom:
                        continue
                    # Advance ("loose") boxes measure the gap between glyph
                    # positions; ink boxes of narrow glyphs (', i, l) leave
                    # wide gaps inside a word.
                    try:
                        loose_left, _, loose_right, _ = textpage.get_charbox(index, loose=True)
                    except TypeError:
                        loose_left, loose_right = left, right
                    if previous_right is not None and not rejoined and (
                        left < previous_right - 2
                        or loose_left > previous_loose_right + 0.3 * max(top - bottom, word_height)
                    ):
                        flush()  # new line or a visible gap without a space
                        word_height = 0.0
                    rejoined = False
                    previous_loose_right = loose_right
                    # Unrotated page fractions: lines are grouped in reading
                    # orientation first and rotated into the view afterwards.
                    char_box = (left / width, 1 - top / height,
                                right / width, 1 - bottom / height)
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
        x0, y0, x1, y1 = (min(1.0, max(0.0, v)) for v in (x0, y0, x1, y1))
        if x1 - x0 < 0.002:
            x0, x1 = (x0, x0 + 0.002) if x0 <= 0.998 else (0.998, 1.0)
        if y1 - y0 < 0.002:
            y0, y1 = (y0, y0 + 0.002) if y0 <= 0.998 else (0.998, 1.0)
        safe.append((text, (x0, y0, x1, y1)))
    layer = page_from_positioned_words(
        page_number, safe, pixel_width=int(shown[0]), pixel_height=int(shown[1]),
        rotation=rotation,
    )
    return _rotated_layer(layer, view) if view else layer


def _rotate_box(box, view: int):
    a = _rotate_point(box[0], box[1], view)
    b = _rotate_point(box[2], box[3], view)
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def _rotated_layer(layer: OCRPage, view: int) -> OCRPage:
    """Map every box of an upright text layer into the rotated page view."""
    blocks = []
    for block in layer.blocks:
        lines = []
        for line in block.lines:
            words = tuple(replace(word, box=_rotate_box(word.box, view)) for word in line.words)
            lines.append(replace(line, words=words, box=_rotate_box(line.box, view)))
        blocks.append(replace(block, lines=tuple(lines), box=_rotate_box(block.box, view)))
    return replace(layer, blocks=tuple(blocks))


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
    from shared_scales import link_matrices

    return link_matrices(replace(
        review, spatial=link_candidates(review, pages),
        matrices=geometric_matrices(pages),
    ))


def attach_docx_matrices(
    review: ScientificDocumentReview, source: bytes,
) -> ScientificDocumentReview:
    """Attach native Word-table matrix proposals (preferred over geometry)."""
    try:
        found = docx_matrices(source)
    except Exception:  # damaged tables must not block ordinary import
        return review
    from shared_scales import link_matrices

    return link_matrices(replace(review, matrices=found)) if found else review


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
    page_lines: list[tuple[int, list[str]]] = []
    text_pages: list[tuple[int, list[str]]] = []
    geometry: list[OCRPage] = []
    table_pages: list[OCRPage] = []
    grid_overridden: set[int] = set()
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
            # OCR reads a row of labelled answer cells together with the item
            # text; restore "item, then its printed choices" from the boxes.
            grid = choice_cell_grid(page_layout)
            if grid is not None:
                columns = page_geometry(page_layout)
                if columns is not None and 2 * len(grid.rows) < columns.rows:
                    # A few rows whose "labels" are table-rule noise: the
                    # number column describes this table better.
                    grid = None
                    grid_overridden.add(n)
            page_lines.append((n, choice_grid_lines(page_layout, grid) if grid is not None
                               else [line.text for line in page_layout.lines]))
            if grid is None:
                table_pages.append(page_layout)
            done += 1
            if progress is not None:
                progress(done, len(pages))
        else:
            extracted = reader.pages[n-1].extract_text() or ""
            page_lines.append((n, extracted.splitlines()))
            if extracted.strip():
                text_pages.append((n, extracted.splitlines()))
                try:
                    geometry.append(pdf_text_layer_page(source, n))
                except (ValueError, RuntimeError):
                    pass
    repairs = ()
    if text_pages:
        fixed, repairs = repair_pdf_text(source, text_pages)
        repaired = dict(fixed)
        page_lines = [(n, repaired.get(n, text)) for n, text in page_lines]
    # A scanned table (number column, statement column, answer digits) is
    # rebuilt row by row from the word boxes instead of the text order.
    tables = reconstruct_tables(table_pages)
    if tables is not None:
        page_lines = [(n, tables.lines.get(n, text)) for n, text in page_lines]
    lines = [(n, line) for n, text in page_lines for line in text]
    matrices = geometric_matrices([g for g in geometry if g.page_number not in grid_overridden])
    try:
        review = parse_scientific_lines(
            lines, filename, page_count=count, ocr_pages=tuple(pages),
            text_source="pdf_text_layer",
        )
        review = with_spacing_repairs(review, repairs)
    except ValueError as error:
        if not matrices:
            raise
        # Grid rows without recognizable numbering: keep matrix proposals.
        review = ScientificDocumentReview(
            filename, (), (
                "No numbered question lines were recognized; only response-"
                "matrix proposals are available. Verify them manually.",
            ), count, non_items=getattr(error, "non_items", ()),
            expected_count=getattr(error, "expected_count", None),
        )
    from shared_scales import link_matrices

    spatial = link_candidates(review, geometry)
    if tables is not None:
        spatial = attach_row_regions(spatial, review, tables.rows)
    review = link_matrices(replace(review, spatial=spatial, matrices=matrices))
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
    edited = replace(candidate, questions=tuple(proposal))
    old = candidate.questions[index].question
    if row.scheme_id and (kind != old.get("kind") or q.get("options") != old.get("options")):
        from shared_scales import detach_question
        edited = detach_question(edited, index)
    return edited


def apply_response_format(
    candidate: InstrumentCandidate, format_index: int,
    labels: tuple[str, str] | list[str],
) -> InstrumentCandidate:
    """Reviewed bulk action: give one evidenced binary format explicit choices.

    Applies to the format's text items awaiting review and to the items it
    already converted (so ``T / F`` can be renamed ``True / False`` for all
    60 items at once). Only items still plain text, or still carrying the
    format's previous labels, are changed; manual edits are never
    overwritten. No numeric codes, answer key or reverse scoring are set.
    """
    if not 0 <= format_index < len(candidate.response_formats):
        raise IndexError("Select a detected answer format.")
    fmt = candidate.response_formats[format_index]
    clean = tuple(" ".join(str(x).split()) for x in labels)
    if len(clean) != 2 or not all(1 <= len(x) <= 120 for x in clean) or clean[0] == clean[1]:
        raise ValueError("Enter two different answer labels (1–120 characters).")
    targets = set(fmt.candidates) | set(fmt.applied_to)
    old = list(fmt.labels)
    proposal, changed = [], []
    for row in candidate.questions:
        q = row.question
        eligible = row.number in targets and (
            q["kind"] == "short_text"
            or (q["kind"] == "single_choice" and q.get("options") == old)
        )
        if not eligible:
            proposal.append(row)
            continue
        question = dict(q)
        question.update({"kind": "single_choice", "options": list(clean),
                         "reverse_scored": False})
        for name in ("value_labels", "scale_id"):
            question.pop(name, None)
        proposal.append(replace(
            row, question=question, confidence="review",
            notes=(*row.notes, f"Binary answers {clean[0]} / {clean[1]} applied "
                   "after review; no numeric codes assigned."),
        ))
        changed.append(row.number)
    if not changed:
        raise ValueError("No matching text or binary items are left to update.")
    validate_questions([item.question for item in proposal])
    formats = list(candidate.response_formats)
    formats[format_index] = replace(
        fmt, labels=clean, applied_to=tuple(sorted(set(fmt.applied_to) | set(changed))),
        candidates=(),
    )
    note = (
        f"Binary answers {clean[0]} / {clean[1]} were applied to {len(changed)} item(s) "
        "after researcher review. Numeric 1/0 codes, answer keys and reverse "
        "scoring are NOT applied automatically."
    )
    return replace(
        candidate, questions=tuple(proposal), response_formats=tuple(formats),
        warnings=(*candidate.warnings, note),
    )
