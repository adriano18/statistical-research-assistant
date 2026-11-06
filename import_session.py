"""UI-independent scientific-import session (stable interface for Stage 33).

Wraps the validated Stage 30–32 importer exactly as the classic
questionnaire builder uses it: read the document locally, attach PDF text
geometry or Word-table matrices, link shared response scales, and apply
the researcher's reviews. The Stage 33 import workspace and future
importer extensions (e.g. Brief COPE-style layouts, Issue #20) meet here:
``blockers()`` is the single list of reasons a draft cannot be created.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from scientific_survey_import import (
    InstrumentCandidate, ScientificDocumentReview, linked_questions,
    read_scientific_document, reviewed_draft, scheme_banner,
)

SUFFIXES = {".pdf", ".docx", ".doc"}
MAX_BYTES = 20_000_000


@dataclass
class ImportSession:
    filename: str = ""
    source: bytes | None = None
    page_count: int = 0
    review: ScientificDocumentReview | None = None
    instrument_index: int = 0
    message: str = ""
    checks: dict = field(default_factory=lambda: {"version": False, "items": False})
    # Low-confidence items the researcher compared with the source (indices).
    reviewed: set = field(default_factory=set)

    # ------------------------------------------------------------ reading
    def open(self, binary: bytes, filename: str) -> str:
        """Read ``binary`` locally (same steps as the classic builder)."""
        from visual_survey_review import (
            attach_docx_matrices, attach_text_layer_geometry, pdf_page_count,
            word_structure_page_count,
        )

        suffix = Path(filename).suffix.lower()
        if suffix not in SUFFIXES:
            raise ValueError("Choose a DOCX, DOC or PDF document.")
        if not isinstance(binary, bytes) or not 0 < len(binary) <= MAX_BYTES:
            raise ValueError("No readable file bytes or file over 20 MB.")
        self.filename, self.source = filename, binary
        self.review, self.instrument_index = None, 0
        self.checks = {"version": False, "items": False}
        self.reviewed = set()
        self.page_count = (pdf_page_count(binary) if suffix == ".pdf"
                           else word_structure_page_count(binary, suffix))
        try:
            with TemporaryDirectory(prefix="workspace-survey-import-") as tmp:
                path = Path(tmp) / Path(filename).name
                path.write_bytes(binary)
                parsed = read_scientific_document(path)
        except ValueError as extraction:
            if suffix == ".docx":
                empty = ScientificDocumentReview(
                    filename, (), ("Only Word-table matrix proposals were found; "
                                   "verify them in the matrix editor.",), 1)
                matrices = attach_docx_matrices(empty, binary)
                if matrices.matrices:
                    self.review = matrices
            self.message = f"No text-based questionnaire extracted: {extraction}"
            return self.message
        try:
            if suffix == ".pdf":
                parsed = attach_text_layer_geometry(parsed, binary)
            elif suffix == ".docx":
                parsed = attach_docx_matrices(parsed, binary)
        except Exception:
            pass  # spatial evidence is optional; never block import
        self.review = parsed
        self.message = (
            f"Read {len(parsed.instruments)} instrument(s), "
            f"{sum(len(x.questions) for x in parsed.instruments)} candidate questions "
            f"from {filename}."
        )
        return self.message

    def ocr_pages(self, pages: list[int], language: str = "eng", rotation: int = 0,
                  cancel=None) -> str:
        from visual_survey_review import ocr_scientific_pdf

        if self.source is None or Path(self.filename).suffix.lower() != ".pdf":
            raise ValueError("Offline OCR is available for PDF sources.")
        self.review = ocr_scientific_pdf(self.source, self.filename, pages, language,
                                         rotation=rotation, cancel=cancel)
        self.instrument_index = 0
        self.checks = {"version": False, "items": False}
        self.reviewed = set()
        self.message = f"Local OCR completed for {len(pages)} page(s)."
        return self.message

    def render_page(self, number: int, rotation: int = 0, *, zoom: float = 1.0) -> bytes:
        """The page as PNG; ``zoom`` > 1 renders a PDF page with more pixels
        (for the enlarged viewer) so small print stays sharp."""
        from visual_survey_review import render_document_page, render_pdf_page

        if zoom > 1.0 and self.filename.lower().endswith(".pdf"):
            return render_pdf_page(self.source, number, scale=min(3.0, 1.4 * zoom),
                                   max_width=int(1300 * zoom), rotation=rotation)
        return render_document_page(self.source, self.filename, number, rotation=rotation)

    @property
    def evidence_source(self) -> str:
        """'pdf_text_layer', 'tesseract_tsv', 'plain_text' or '' (no geometry)."""
        spatial = getattr(self.review, "spatial", None)
        sources = {getattr(page, "source", "") for page in getattr(spatial, "pages", ())}
        if "tesseract_tsv" in sources:
            return "tesseract_tsv"
        return next(iter(sorted(sources)), "")

    # --------------------------------------------------------- instrument
    @property
    def instruments(self) -> tuple[InstrumentCandidate, ...]:
        return self.review.instruments if self.review else ()

    @property
    def instrument(self) -> InstrumentCandidate | None:
        items = self.instruments
        if not items:
            return None
        return items[min(self.instrument_index, len(items) - 1)]

    def select(self, index: int) -> None:
        if 0 <= index < len(self.instruments):
            self.instrument_index = index
            self.checks = {"version": False, "items": False}
            self.reviewed = set()

    def store(self, updated: InstrumentCandidate) -> None:
        collection = list(self.review.instruments)
        collection[self.instrument_index] = updated
        self.review = replace(self.review, instruments=tuple(collection))
        self.checks = {"version": False, "items": False}  # every edit resets approvals
        self.reviewed = set()

    def linked(self, scheme_id: str) -> list[int]:
        return linked_questions(self.instrument, scheme_id)

    def review_scale(self, scheme_id: str, **kwargs) -> None:
        from shared_scales import review_scheme

        self.store(review_scheme(self.instrument, scheme_id, **kwargs))

    def not_shared(self, scheme_id: str) -> None:
        from shared_scales import unlink_scheme

        self.store(unlink_scheme(self.instrument, scheme_id))

    def correct_wording(self, index: int, prompt: str) -> None:
        from visual_survey_review import edit_candidate_question

        row = self.instrument.questions[index]
        self.store(edit_candidate_question(
            self.instrument, index, prompt=prompt, kind=row.question["kind"],
            options_text="\n".join(row.question.get("options", [])),
            section=row.question.get("section", ""),
            required=bool(row.question.get("required", False)),
        ))

    # ------------------------------------------------------------ gating
    def flags(self) -> list[tuple[int, str]]:
        """(question index, note) for items the researcher should look at."""
        found = []
        for index, row in enumerate(self.instrument.questions if self.instrument else ()):
            if row.confidence == "low":
                found.append((index, "low confidence"))
            for note in row.notes:
                # Scale-linkage notes are reviewed once per scale, not per item.
                if not note.startswith("Shared scale"):
                    found.append((index, note))
        return found

    def low_confidence(self) -> list[int]:
        return [i for i, row in enumerate(self.instrument.questions if self.instrument else ())
                if row.confidence == "low"]

    def mark_reviewed(self, index: int, value: bool = True) -> None:
        """The researcher compared a low-confidence item with the source."""
        (self.reviewed.add if value else self.reviewed.discard)(index)

    def blockers(self) -> list[str]:
        if self.instrument is None:
            return ["No instrument was extracted from this document."]
        problems = []
        banner = scheme_banner(self.instrument)
        if banner:
            problems.append(banner)
        unreviewed = [i for i in self.low_confidence() if i not in self.reviewed]
        if unreviewed:
            numbers = ", ".join(str(self.instrument.questions[i].number) for i in unreviewed[:12])
            problems.append(
                f"{len(unreviewed)} low-confidence item(s) not yet compared with the source "
                f"(items {numbers}{'…' if len(unreviewed) > 12 else ''}).")
        if not self.checks.get("version"):
            problems.append("Confirm the instrument version, wording and permissions.")
        if not self.checks.get("items"):
            problems.append("Confirm that item count and order match the source.")
        return problems

    def draft(self) -> list[dict]:
        """Validated question dicts for the builder (raises while blocked)."""
        problems = self.blockers()
        if problems:
            raise ValueError(" ".join(problems))
        return reviewed_draft(self.instrument)
