"""Import integrity (Issue #31): bibliography entries never become items,
image-only questionnaire pages are read with local OCR, and the item count
stated in the document is reported next to the count that was found.

Every fixture is synthetic (``tests/synthetic_documents.py``); no published
questionnaire wording, citation or scoring rule is reproduced here.
"""

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from import_session import ImportSession
from ocr_layout import page_from_plain_text
from ocr_runtime import tesseract_available
from scientific_survey_import import parse_scientific_lines, read_scientific_document
from synthetic_documents import (
    FICTIONAL_CITATIONS, SSQ_SCORING_NOTE, STRAIN_LABELS, numbered_items_pdf,
    psq_like_pdf, references_only_pdf, strain_statements,
)

REQUIRE = os.environ.get("SRA_REQUIRE_REAL_OCR") == "1"
AVAILABLE = tesseract_available()
CITATION_MARKS = ("(2001)", "(2015)", "(1999)", "et al", "doi:", "Journal of Fictional")
NO_OCR_NOTE = "Page 2 is an image; local OCR is not available, so its questions could not be read."
LEGACY_DOC = ("Legacy Word .doc files cannot be read on this computer. Open the file in Word "
              "or LibreOffice and save it as .docx or PDF, then import that file.")


def on_page(page, texts):
    return [(page, text) for text in texts]


def questions(session):
    return [row for instrument in session.instruments for row in instrument.questions]


def form_page_ocr_text() -> str:
    """What a clean OCR pass reads on the PSQ-like page 2 (deterministic)."""
    rows = ["SSQ response form (synthetic)", " ".join(STRAIN_LABELS)]
    rows += [f"{n}. {text} 1 2 3 4" for n, text in enumerate(strain_statements(30), 1)]
    rows += [SSQ_SCORING_NOTE, "References"]
    rows += [line for citation in FICTIONAL_CITATIONS for line in citation]
    return "\n".join(rows)


class StubRecognizer:
    """Stands in for Tesseract: records the pages it was asked to read."""

    def __init__(self, text=None, error=None):
        self.text, self.error, self.pages = text, error, []

    def __call__(self, png, language, *, page_number=1, dpi=None, rotation=0, cancel=None):
        self.pages.append(page_number)
        if self.error is not None:
            raise self.error
        return page_from_plain_text(page_number, self.text)


class CitationTestCase(unittest.TestCase):
    def assert_no_citations(self, rows):
        for row in rows:
            for mark in CITATION_MARKS:
                self.assertNotIn(mark, row.question["prompt"], row.number)


class CitationParsingTests(CitationTestCase):
    PREAMBLE = on_page(1, ["Synthetic reading notes",
                           "A fictional overview paragraph without any questions."])

    def test_citation_shaped_numbered_lines_are_never_items(self):
        lines = self.PREAMBLE + on_page(1, [
            "1. Fictional, A., & Placeholder, B. (2001). Invented strain in synthetic samples.",
            "2. Sample C, Example D. Pretend moods in made-up towns. Fict Rev. 2003;7(1):1-9.",
            "3. Example, D. Synthetic sleep and work. Journal of Pretend Health, 12 (3), 33–47.",
            "4. Placeholder, E. et al. Invented diaries of imaginary days. doi:10.0000/fict.2004",
        ])
        with self.assertRaisesRegex(ValueError, "look like references") as caught:
            parse_scientific_lines(lines, "reading_notes.pdf")
        self.assertEqual(len(getattr(caught.exception, "non_items", ())), 4)

    def test_references_heading_in_any_language_marks_non_item_material(self):
        entries = ["1. Fictional handbook of invented moods for testing.",
                   "2. Pretend atlas of synthetic towns and villages."]
        for heading in ("References", "REFERENCES:", "Bibliography", "— Literature —",
                        "Literatūra", "Izmantotā literatūra", "Avoti", "Литература",
                        "Список литературы", "6. References", "R E F E R E N C E S",
                        "References (continued)"):
            with self.subTest(heading=heading):
                lines = self.PREAMBLE + on_page(2, [heading, *entries])
                with self.assertRaisesRegex(ValueError, "look like references") as caught:
                    parse_scientific_lines(lines, "notes.pdf", page_count=2)
                self.assertEqual(getattr(caught.exception, "non_items", ()),
                                 ((2, entries[0]), (2, entries[1])))

    def test_recognized_title_followed_by_a_bibliography_gives_no_items(self):
        # The reported failure: an instrument heading opens a candidate and
        # the numbered bibliography on the next page became its "items".
        lines = on_page(1, ["RESEARCH QUESTIONNAIRE", "A fictional description of the form."])
        lines += on_page(2, ["References",
                             "1. Fictional handbook of invented moods for testing.",
                             "2. Pretend atlas of synthetic towns and villages."])
        with self.assertRaisesRegex(ValueError, "look like references"):
            parse_scientific_lines(lines, "form.pdf", page_count=2)

    def test_unnumbered_citation_is_not_glued_to_the_last_item(self):
        lines = on_page(1, [
            "1. Fictional neighbours leave me feeling rested.",
            "2. Synthetic coworkers leave me feeling hurried.",
            "3. Pretend classmates leave me feeling calm",
            "Fictional, A. (2001). Invented strain. Journal of Fictional Studies, 4 (2), 101–119.",
        ])
        rows = parse_scientific_lines(lines, "form.pdf").instruments[0].questions
        self.assertEqual(rows[2].question["prompt"], "Pretend classmates leave me feeling calm")

    def test_items_with_numbers_and_brackets_stay_items(self):
        prompts = ["How many days (0–7) did you walk last week?",
                   "I slept 6-8 hours on 5 of 7 nights.",
                   "Rate your mood today (1 = low, 5 = high).",
                   "Since the move in 2019, how settled do you feel?",
                   "Did you vote in the fictional election (2022)?",
                   "Watch TV, Use PC and read before sleeping.",
                   "Yes, I agree with my fictional neighbours."]
        lines = on_page(1, [f"{n}. {text}" for n, text in enumerate(prompts, 1)])
        rows = parse_scientific_lines(lines, "form.pdf").instruments[0].questions
        self.assertEqual([row.question["prompt"] for row in rows], prompts)

    def test_a_second_form_after_the_references_is_still_found(self):
        lines = on_page(1, [f"{n}. {text}" for n, text in enumerate(strain_statements(5), 1)])
        lines += on_page(1, ["References", *FICTIONAL_CITATIONS[0], *FICTIONAL_CITATIONS[1]])
        lines += on_page(2, ["SYNTHETIC FOLLOW-UP FORM"])
        lines += on_page(2, [f"{n}. {text}" for n, text in enumerate(strain_statements(5), 1)])
        review = parse_scientific_lines(lines, "two_forms.pdf", page_count=2)
        self.assertEqual([len(x.questions) for x in review.instruments], [5, 5])
        self.assert_no_citations(row for x in review.instruments for row in x.questions)

    def test_stated_item_count_is_read_from_the_text_only(self):
        from scientific_survey_import import expected_item_count

        cases = {
            "The form consists of 30 items.": 30,
            "A 24-item synthetic inventory.": 24,
            "Answer all 12 questions below.": 12,
            "It comprises twenty statements.": 20,
            "Anketa sastāv no 18 apgalvojumiem.": 18,
            "Опросник состоит из 16 вопросов.": 16,
            "Items 1, 4 and 9 are reverse scored on a 4-point scale.": None,
            "In the last 30 days you rested on a 1–4 scale.": None,
            "The form has 2 subscales with 15 items each.": None,
            "Developed by Fictional et al. (2001), the form consists of 30 items.": 30,
            "30 items; a short 10-item form also exists; the 30 items take 5 minutes.": 30,
            # Scoring notes name a subset, not the length of the form.
            "Reverse items 4, 5, 7 and 8. On these 4 questions, change the scores.": None,
            "Šiem 3 apgalvojumiem punktus skaita pretēji.": None,
            "Для этих 3 вопросов баллы считаются в обратном порядке.": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected_item_count([text]), expected)
        lines = on_page(1, ["The synthetic form consists of 4 items."])
        lines += on_page(1, [f"{n}. {t}" for n, t in enumerate(strain_statements(4), 1)])
        self.assertEqual(parse_scientific_lines(lines, "form.pdf").expected_count, 4)


class ReferencesOnlyPdfTests(unittest.TestCase):
    def test_a_reading_list_gives_zero_questions_and_says_why(self):
        for heading in ("References", "Bibliography", "Literature", None):
            with self.subTest(heading=heading):
                session = ImportSession()
                message = session.open(references_only_pdf(heading), "reading_list.pdf")
                self.assertEqual(questions(session), [])
                self.assertIn("look like references", message)
                self.assertEqual(len(session.non_items), 3)
                self.assertIsNone(session.instrument)

    def test_the_file_name_never_sets_a_count_or_a_scale(self):
        session = ImportSession()
        session.open(references_only_pdf(), "SSQ_30_items_4-point_scale_1-4.pdf")
        self.assertIsNone(session.expected_count)
        self.assertEqual(session.instruments, ())
        self.assertFalse(any("30" in note for note in session.notes))

    def test_a_small_logo_does_not_trigger_ocr(self):
        recognizer = StubRecognizer(error=AssertionError("OCR must not run for a logo"))
        with patch("visual_survey_review.tesseract_available", return_value=True), \
                patch("visual_survey_review.recognize_page_layout", recognizer):
            session = ImportSession()
            session.open(references_only_pdf(logo=True), "reading_list.pdf")
        self.assertEqual(recognizer.pages, [])
        self.assertEqual(session.ocr_pages_used, ())
        self.assertEqual(questions(session), [])


class PsqLikeImportTests(CitationTestCase):
    """The Issue #31 shape: description page + image-only item table page."""

    @classmethod
    def setUpClass(cls):
        cls.pdf = psq_like_pdf()

    def test_without_ocr_the_bibliography_is_not_imported_and_the_gap_is_explained(self):
        with patch.dict(os.environ, {"SRA_DISABLE_OCR": "1"}):
            session = ImportSession()
            message = session.open(psq_like_pdf(references_heading="Literature"),
                                   "synthetic_ssq.pdf")
        self.assertEqual(questions(session), [])
        self.assertIn(NO_OCR_NOTE, session.notes)
        self.assertIn(NO_OCR_NOTE, message)
        self.assertEqual(session.expected_count, 30)
        self.assertIn("Found 0 questions; the text says 30.", message)
        self.assertEqual([page for page, _ in session.non_items], [2, 2, 2])
        self.assertEqual(session.ocr_pages_used, ())

    def test_image_page_is_read_automatically_with_local_ocr(self):
        recognizer, messages = StubRecognizer(form_page_ocr_text()), []
        with patch("visual_survey_review.tesseract_available", return_value=True), \
                patch("visual_survey_review.recognize_page_layout", recognizer):
            session = ImportSession()
            message = session.open(self.pdf, "synthetic_ssq.pdf", progress=messages.append)
        self.assertEqual(recognizer.pages, [2])  # page 1 has no placed image
        rows = questions(session)
        self.assertEqual([row.number for row in rows], list(range(1, 31)))
        self.assertEqual([row.question["prompt"] for row in rows], strain_statements(30))
        self.assert_no_citations(rows)
        schemes = session.instrument.schemes
        self.assertEqual([scheme.labels for scheme in schemes], [STRAIN_LABELS])
        self.assertEqual(len(session.linked(schemes[0].id)), 30)
        self.assertEqual(session.ocr_pages_used, (2,))
        self.assertEqual(session.expected_count, 30)
        self.assertIn("Found 30 of 30 expected questions.", message)
        self.assertEqual(len(messages), 1)
        self.assertIn("page 2", messages[0].lower())
        self.assertEqual([page for page, _ in session.non_items], [2, 2, 2])

    def test_ocr_failure_keeps_the_text_result_and_explains(self):
        recognizer = StubRecognizer(error=RuntimeError(
            "Local OCR failed. Confirm the Tesseract path and installed language packs."))
        with patch("visual_survey_review.tesseract_available", return_value=True), \
                patch("visual_survey_review.recognize_page_layout", recognizer):
            session = ImportSession()
            message = session.open(self.pdf, "synthetic_ssq.pdf")
        self.assertEqual(recognizer.pages, [2])
        self.assertEqual(questions(session), [])
        failed = [note for note in session.notes
                  if note.startswith("Page 2 is an image; local OCR failed")]
        self.assertEqual(len(failed), 1, session.notes)
        self.assertIn(failed[0], message)
        self.assertEqual(session.ocr_pages_used, ())
        self.assertEqual(session.expected_count, 30)

    def test_cancelled_ocr_keeps_the_text_result(self):
        cancel = threading.Event()
        cancel.set()
        recognizer = StubRecognizer(error=AssertionError("cancelled OCR must not run"))
        with patch("visual_survey_review.tesseract_available", return_value=True), \
                patch("visual_survey_review.recognize_page_layout", recognizer):
            session = ImportSession()
            session.open(self.pdf, "synthetic_ssq.pdf", cancel=cancel)
        self.assertEqual(recognizer.pages, [])
        self.assertEqual(questions(session), [])
        self.assertTrue(any("cancelled" in note for note in session.notes), session.notes)
        self.assertEqual(session.ocr_pages_used, ())

    def test_manual_ocr_reports_pages_and_the_stated_count(self):
        with patch.dict(os.environ, {"SRA_DISABLE_OCR": "1"}):
            session = ImportSession()
            session.open(self.pdf, "synthetic_ssq.pdf")
        with patch("visual_survey_review.recognize_page_layout",
                   StubRecognizer(form_page_ocr_text())):
            message = session.ocr_pages([2])
        self.assertTrue(message.startswith("Local OCR completed for 1 page(s)."), message)
        self.assertIn("Found 30 of 30 expected questions.", message)
        self.assertEqual(session.ocr_pages_used, (2,))
        self.assertEqual(len(questions(session)), 30)
        self.assertNotIn(NO_OCR_NOTE, session.notes)


@unittest.skipUnless(AVAILABLE or REQUIRE, "No local Tesseract engine installed")
class RealOcrPsqLikeTests(CitationTestCase):
    def test_the_image_table_is_read_with_real_local_ocr(self):
        messages = []
        session = ImportSession()
        message = session.open(psq_like_pdf(), "synthetic_ssq.pdf", progress=messages.append)
        rows = questions(session)
        self.assertEqual([row.number for row in rows], list(range(1, 31)))
        self.assert_no_citations(rows)
        schemes = session.instrument.schemes
        self.assertEqual([scheme.labels for scheme in schemes], [STRAIN_LABELS])
        self.assertEqual(len(session.linked(schemes[0].id)), 30)
        self.assertEqual(session.ocr_pages_used, (2,))
        self.assertEqual(session.evidence_source, "tesseract_tsv")
        self.assertIn("Found 30 of 30 expected questions.", message)
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(session.non_items), 3)


class LongFormTests(CitationTestCase):
    def test_long_forms_keep_every_item_and_report_the_stated_count(self):
        for count in (60, 120):
            with self.subTest(count=count):
                session = ImportSession()
                message = session.open(numbered_items_pdf(count, references=count == 120),
                                       f"synthetic_{count}.pdf")
                self.assertEqual(len(session.instruments), 1)
                rows = session.instrument.questions
                self.assertEqual([row.number for row in rows], list(range(1, count + 1)))
                self.assertEqual([row.question["prompt"] for row in rows],
                                 strain_statements(count))
                self.assert_no_citations(rows)
                schemes = session.instrument.schemes
                self.assertEqual([scheme.labels for scheme in schemes], [STRAIN_LABELS])
                self.assertEqual(len(session.linked(schemes[0].id)), count)
                self.assertEqual(session.expected_count, count)
                self.assertIn(f"Found {count} of {count} expected questions.", message)
                self.assertEqual(len(session.non_items), 3 if count == 120 else 0)
                self.assertEqual(session.ocr_pages_used, ())


class LegacyDocTests(unittest.TestCase):
    SOURCE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 synthetic legacy word bytes"

    def test_doc_without_a_converter_fails_with_actionable_advice(self):
        with patch("shutil.which", return_value=None):
            session = ImportSession()
            with self.assertRaises(ValueError) as caught:
                session.open(self.SOURCE, "old_form.doc")
            self.assertEqual(str(caught.exception), LEGACY_DOC)
            self.assertEqual(session.notes, [LEGACY_DOC])
            self.assertIsNone(session.source)
            with TemporaryDirectory() as folder:
                path = Path(folder) / "old_form.doc"
                path.write_bytes(self.SOURCE)
                with self.assertRaises(ValueError) as direct:
                    read_scientific_document(path)
            self.assertEqual(str(direct.exception), LEGACY_DOC)

    def test_a_failing_converter_is_explicit_too(self):
        failed = subprocess.CompletedProcess(["antiword"], 1, b"", b"not a Word document")
        with patch("shutil.which", return_value="/usr/bin/antiword"), \
                patch("subprocess.run", return_value=failed):
            with self.assertRaises(ValueError) as caught:
                ImportSession().open(self.SOURCE, "old_form.doc")
        self.assertIn("save it as .docx or PDF, then import that file", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
