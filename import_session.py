"""UI-independent scientific-import session (stable interface for Stage 33).

Wraps the validated Stage 30–32 importer exactly as the classic
questionnaire builder uses it: read the document locally, attach PDF text
geometry or Word-table matrices, link shared response scales, and apply
the researcher's reviews. The Stage 33 import workspace and future
importer extensions (e.g. Brief COPE-style layouts, Issue #20) meet here:
``blockers()`` is the single list of reasons a draft cannot be created.

Import integrity (Issue #31): numbered bibliography entries never become
items, PDF pages that hold their questions only as an image are read with
local OCR automatically, and the item count the document states is
reported next to the count found (``notes``, ``expected_count``,
``ocr_pages_used``, ``non_items``). A scale or scoring method is never
inferred from the file name.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from scientific_survey_import import (
    InstrumentCandidate, LegacyDocUnavailable, NoQuestionsFound,
    ScientificDocumentReview, linked_questions, read_scientific_document,
    reviewed_draft, scheme_banner,
)

SUFFIXES = {".pdf", ".docx", ".doc"}
MAX_BYTES = 20_000_000
# The researcher's own confirmations, each given separately (Issue #31):
# the instrument version, the right to use it, and item count and order.
# Numeric codes and reverse keying are confirmed per shared scale.
CONFIRMATIONS = ("version", "rights", "items")


def fresh_checks() -> dict:
    return {key: False for key in CONFIRMATIONS}
# Automatic OCR reads pages whose placed images cover at least this share
# of the page (a scan or an item table), not pages with a logo or a stamp.
AUTO_OCR_MIN_IMAGE_SHARE = 0.08


def _pages_phrase(pages) -> tuple[str, bool]:
    """("Page 2", False) or ("Pages 2, 3 and 5", True)."""
    numbers = [str(page) for page in pages]
    if len(numbers) == 1:
        return f"Page {numbers[0]}", False
    return f"Pages {', '.join(numbers[:-1])} and {numbers[-1]}", True


@dataclass
class ImportSession:
    filename: str = ""
    source: bytes | None = None
    page_count: int = 0
    review: ScientificDocumentReview | None = None
    instrument_index: int = 0
    message: str = ""
    checks: dict = field(default_factory=fresh_checks)
    # Low-confidence items the researcher compared with the source (indices).
    reviewed: set = field(default_factory=set)
    # Import-integrity facts for the UI, refreshed by open() / ocr_pages():
    notes: list[str] = field(default_factory=list)     # English sentences
    ocr_pages_used: tuple[int, ...] = ()               # pages read with local OCR
    expected_count: int | None = None                  # item count the text states
    image_pages: tuple[int, ...] = ()                  # pages drawing a large image
    non_items: tuple[tuple[int, str], ...] = ()        # (page, line) kept out as references
    # The same facts as (key, values) for a translated interface: the keys
    # are "ocr_read", "ocr_unavailable", "ocr_cancelled", "ocr_failed",
    # "ocr_nothing", "ocr_limit", "references", "count_match",
    # "count_mismatch" and "unreadable".
    facts: list[tuple[str, dict]] = field(default_factory=list)

    # ------------------------------------------------------------ reading
    def open(self, binary: bytes, filename: str, *, progress=None, cancel=None,
             language: str | None = None) -> str:
        """Read ``binary`` locally (same steps as the classic builder).

        A PDF page that draws an image but gives no items in its text layer
        is read with local OCR automatically: ``progress(message)`` is
        called once per OCR page, ``cancel`` (a ``threading.Event``) stops
        OCR and keeps the text result, and ``language`` overrides the OCR
        language suggested by the document's text. Without a working OCR
        engine the text result is kept and ``notes`` names the pages that
        could not be read. Raises ``ValueError`` for unusable input,
        including a legacy ``.doc`` that cannot be converted here.
        """
        from ocr_profile import stage
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
        self.checks = fresh_checks()
        self.reviewed = set()
        self.notes, self.ocr_pages_used, self.image_pages = [], (), ()
        self.facts = []
        self.expected_count, self.non_items = None, ()
        try:
            with stage("pdf_loading"):
                self.page_count = (pdf_page_count(binary) if suffix == ".pdf"
                                   else word_structure_page_count(binary, suffix))
        except LegacyDocUnavailable as error:
            self._unreadable(error)
            raise
        parsed, failure = None, None
        try:
            with stage("pdf_loading"), TemporaryDirectory(prefix="workspace-survey-import-") as tmp:
                path = Path(tmp) / Path(filename).name
                path.write_bytes(binary)
                parsed = read_scientific_document(path)
        except LegacyDocUnavailable as error:
            self._unreadable(error)
            raise
        except ValueError as extraction:
            failure = extraction
            if suffix == ".docx":
                empty = ScientificDocumentReview(
                    filename, (), ("Only Word-table matrix proposals were found; "
                                   "verify them in the matrix editor.",), 1)
                matrices = attach_docx_matrices(empty, binary)
                if matrices.matrices:
                    parsed = matrices
        if failure is None:
            try:
                with stage("pdf_loading"):
                    if suffix == ".pdf":
                        parsed = attach_text_layer_geometry(parsed, binary)
                    elif suffix == ".docx":
                        parsed = attach_docx_matrices(parsed, binary)
            except Exception:
                pass  # spatial evidence is optional; never block import
        if suffix == ".pdf":
            parsed = self._read_image_pages(parsed, failure, progress=progress,
                                            cancel=cancel, language=language)
        with stage("review_model"):
            self.review = parsed
            self._take_evidence(parsed, failure)
            if self.instruments:
                head = (f"Read {len(self.instruments)} instrument(s), "
                        f"{sum(len(x.questions) for x in self.instruments)} candidate questions "
                        f"from {filename}.")
            elif self.non_items or failure is None:
                head = f"No questionnaire items were found in {filename}."
            else:
                head = f"No text-based questionnaire extracted: {failure}"
            return self._report(head)

    def ocr_pages(self, pages: list[int], language: str = "eng", rotation: int = 0,
                  cancel=None) -> str:
        from visual_survey_review import ocr_scientific_pdf

        if self.source is None or Path(self.filename).suffix.lower() != ".pdf":
            raise ValueError("Offline OCR is available for PDF sources.")
        self.review = ocr_scientific_pdf(self.source, self.filename, pages, language,
                                         rotation=rotation, cancel=cancel)
        self.instrument_index = 0
        self.checks = fresh_checks()
        self.reviewed = set()
        self.notes, self.ocr_pages_used = [], tuple(sorted(set(pages)))
        self.facts = []
        self._take_evidence(self.review, None)
        return self._report(f"Local OCR completed for {len(pages)} page(s).")

    # ---------------------------------------------------- import integrity
    def _unreadable(self, error: Exception) -> None:
        """Nothing usable was opened; keep the explicit reason for the UI."""
        self.source, self.page_count = None, 0
        self.notes, self.message = [str(error)], str(error)
        self.facts = [("unreadable", {"reason": str(error)})]

    def _read_image_pages(self, review, failure, *, progress, cancel, language):
        """Run local OCR on image pages whose text layer gave no items.

        Returns the OCR review when it finds items on those pages, else the
        text review unchanged; every outcome is recorded in ``notes``.
        """
        from ocr_profile import stage
        from ocr_runtime import OCRCancelled
        from visual_survey_review import (
            MAX_BATCH_PAGES, ocr_scientific_pdf, pdf_image_coverage, tesseract_available,
        )

        try:
            with stage("pdf_loading"):
                shares = pdf_image_coverage(self.source)
            self.image_pages = tuple(page for page, share in sorted(shares.items())
                                     if share >= AUTO_OCR_MIN_IMAGE_SHARE)
        except Exception:  # fall back to the pages pypdf lists with images
            self.image_pages = tuple(getattr(review, "image_only_pages", ())
                                     or getattr(failure, "image_pages", ()))
        with_items = {row.page for x in (review.instruments if review else ())
                      for row in x.questions}
        targets = [page for page in self.image_pages if page not in with_items]
        if not targets:
            return review
        if len(targets) > MAX_BATCH_PAGES:
            rest, targets = targets[MAX_BATCH_PAGES:], targets[:MAX_BATCH_PAGES]
            later, many = _pages_phrase(rest)
            self._note("ocr_limit", f"{later} {'are images' if many else 'is an image'} beyond "
                       f"the automatic OCR limit of {MAX_BATCH_PAGES} pages; run OCR on "
                       f"{'them' if many else 'it'} separately.", pages=list(rest),
                       limit=MAX_BATCH_PAGES)
        subject, many = _pages_phrase(targets)
        image = f"{subject} {'are images' if many else 'is an image'}"
        its, it = ("their", "them") if many else ("its", "it")
        pages = list(targets)
        if not tesseract_available():
            self._note("ocr_unavailable", f"{image}; local OCR is not available, so {its} "
                       "questions could not be read.", pages=pages)
            return review
        cancelled = (f"{image}; local OCR was cancelled, so {its} questions were not read. "
                     f"Run OCR on {'those pages' if many else 'that page'} to try again.")
        if cancel is not None and cancel.is_set():
            self._note("ocr_cancelled", cancelled, pages=pages)
            return review

        def announce(done: int, total: int) -> None:
            if progress is not None and done < total:
                progress(f"Reading page {targets[done]} with local OCR ({done + 1} of {total})…")

        announce(0, len(targets))
        try:
            ocr = ocr_scientific_pdf(self.source, self.filename, targets,
                                     self._ocr_language(language, review, failure),
                                     cancel=cancel, progress=announce)
        except OCRCancelled:
            self._note("ocr_cancelled", cancelled, pages=pages)
            return review
        except NoQuestionsFound:
            ocr = None
        except (RuntimeError, ValueError, OSError) as error:
            detail = " ".join(str(error).split())[:240].rstrip(". ")
            self._note("ocr_failed", f"{image}; local OCR failed, so {its} questions could not "
                       f"be read ({detail}).", pages=pages, detail=detail)
            return review
        found = [row for x in (ocr.instruments if ocr else ()) for row in x.questions]
        known = sum(len(x.questions) for x in (review.instruments if review else ()))
        if any(row.page in targets for row in found) and len(found) >= known:
            self.ocr_pages_used = tuple(targets)
            self._note("ocr_read", f"{image}; {its} questions were read with local OCR. "
                       "Compare every item with the source page.", pages=pages)
            return ocr
        self._note("ocr_nothing", f"{image}; local OCR found no numbered questions on {it}.",
                   pages=pages)
        return review

    def _note(self, key: str, english: str, **values) -> None:
        """One fact, as an English sentence and as (key, values) for the UI."""
        self.notes.append(english)
        self.facts.append((key, values))

    @staticmethod
    def _ocr_language(language, review, failure) -> str:
        """The caller's language, else the one the text suggests (installed)."""
        from visual_survey_review import OCR_LANGUAGES

        if language:
            return language
        wanted = (getattr(review, "ocr_language", "") or getattr(failure, "ocr_language", "")
                  or "eng")
        try:
            from ocr_runtime import ocr_readiness

            installed = set(ocr_readiness().languages)
        except Exception:
            installed = set()
        if installed:
            wanted = "+".join(code for code in wanted.split("+") if code in installed) or "eng"
        return wanted if wanted in OCR_LANGUAGES else "eng"

    def _take_evidence(self, review, failure) -> None:
        self.non_items = tuple(getattr(review, "non_items", ())
                               or getattr(failure, "non_items", ()))
        self.expected_count = getattr(review, "expected_count", None)
        if self.expected_count is None:
            self.expected_count = getattr(failure, "expected_count", None)

    def _found_count(self) -> int:
        """Questions of the instrument the stated count describes (or the largest)."""
        counts = [len(x.questions) for x in self.instruments]
        if self.expected_count in counts:
            return self.expected_count
        return max(counts, default=0)

    def _report(self, head: str) -> str:
        """Add the references and item-count facts to ``notes``; the message."""
        if self.non_items:
            count = len(self.non_items)
            pages = sorted({page for page, _ in self.non_items})
            where = _pages_phrase(pages)[0].lower()
            self._note(
                "references",
                f"The {count} numbered lines on {where} look like references (a bibliography), "
                "not questions; they were not imported." if count > 1 else
                f"The numbered line on {where} looks like a reference (a bibliography entry), "
                "not a question; it was not imported.", count=count, pages=pages)
        if self.expected_count is not None:
            found, expected = self._found_count(), self.expected_count
            if found == expected:
                self._note("count_match", f"Found {found} of {expected} expected questions.",
                           found=found, expected=expected)
            else:
                self._note("count_mismatch", f"Found {found} question{'' if found == 1 else 's'}; "
                           f"the text says {expected}.", found=found, expected=expected)
        self.message = " ".join([head, *self.notes])
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
            self.checks = fresh_checks()
            self.reviewed = set()

    def store(self, updated: InstrumentCandidate) -> None:
        collection = list(self.review.instruments)
        collection[self.instrument_index] = updated
        self.review = replace(self.review, instruments=tuple(collection))
        # Confirmations are independent: correcting an item or reviewing a
        # scale withdraws neither the version, rights and count confirmations
        # nor the items already compared with the source.

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

    def blocker_keys(self) -> list[tuple[str, dict]]:
        """Why a draft cannot be created yet, as (key, values) for the UI."""
        if self.instrument is None:
            return [("no_instrument", {})]
        problems = []
        if scheme_banner(self.instrument):
            problems.append(("scale", {}))
        unreviewed = [i for i in self.low_confidence() if i not in self.reviewed]
        if unreviewed:
            numbers = ", ".join(str(self.instrument.questions[i].number) for i in unreviewed[:12])
            problems.append(("unreviewed", {
                "count": len(unreviewed), "items": numbers + ("…" if len(unreviewed) > 12 else "")}))
        for key in CONFIRMATIONS:
            if not self.checks.get(key):
                problems.append((key, {}))
        return problems

    def blockers(self) -> list[str]:
        if self.instrument is None:
            return ["No instrument was extracted from this document."]
        english = {
            "rights": "Confirm that you may use this instrument (licence or permission).",
            "version": "Confirm the instrument version and wording against the source.",
            "items": "Confirm that item count and order match the source.",
        }
        problems = []
        for key, values in self.blocker_keys():
            if key == "scale":
                problems.append(scheme_banner(self.instrument))
            elif key == "unreviewed":
                problems.append(
                    f"{values['count']} low-confidence item(s) not yet compared with the source "
                    f"(items {values['items']}).")
            else:
                problems.append(english[key])
        return problems

    def draft(self) -> list[dict]:
        """Validated question dicts for the builder (raises while blocked)."""
        problems = self.blockers()
        if problems:
            raise ValueError(" ".join(problems))
        return reviewed_draft(self.instrument)
