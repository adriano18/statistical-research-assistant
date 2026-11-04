"""Tests for conservative Word/PDF questionnaire import (fictional documents)."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from docx import Document
from pypdf import PdfWriter

from survey_document_import import (
    parse_question_lines, read_survey_document,
)


class DocumentImportTests(unittest.TestCase):
    def test_option_ordering_required_flags_and_unscored_draft(self):
        imported = parse_question_lines([
            "Fictional customer interview, do not use in real research",
            "1. What was the quality of service?",
            "A) Very poor",
            "B) Fair",
            "C) Excellent",
            "2. Select all features that matter",
            "A. Speed",
            "B. Price",
            "C. Safety",
            "Q3: Describe your experience",
        ], "sample.docx")
        self.assertEqual(len(imported.questions), 3)
        self.assertEqual(imported.questions[0]["options"],
                         ["Very poor", "Fair", "Excellent"])
        self.assertEqual(imported.questions[0]["kind"], "single_choice")
        self.assertEqual(imported.questions[1]["kind"], "multiple_choice")
        self.assertEqual(imported.questions[2]["kind"], "short_text")
        self.assertFalse(any(q["required"] for q in imported.questions))
        self.assertTrue(all(q["key"].startswith("import_q") for q in imported.questions))
        self.assertTrue(any("NOT inferred" in x for x in imported.notes))

    def test_loads_actual_word_document_with_question_table(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "questionnaire.DOCX"
            doc = Document()
            doc.add_paragraph("1. Do you recommend this fictional service?")
            table = doc.add_table(rows=2, cols=1)
            table.cell(0, 0).text = "A) Yes"
            table.cell(1, 0).text = "B) No"
            doc.add_paragraph("2. What should be improved?")
            doc.save(path)
            parsed = read_survey_document(path)
            self.assertEqual(len(parsed.questions), 2)
            self.assertEqual(parsed.questions[0]["options"], ["Yes", "No"])
            self.assertEqual(parsed.questions[1]["kind"], "short_text")

    def test_reads_text_pdf_without_ocr(self):
        # pypdf does not provide text drawing APIs; reportlab builds a tiny
        # text-based synthetic fixture, which pypdf extracts.
        from reportlab.pdfgen import canvas
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "survey.pdf"
            page = canvas.Canvas(str(path))
            page.drawString(80, 750, "1. How would you describe this service?")
            page.drawString(80, 728, "A) Positive")
            page.drawString(80, 708, "B) Negative")
            page.drawString(80, 680, "2. Other comments?")
            page.save()
            parsed = read_survey_document(path)
            self.assertEqual(len(parsed.questions), 2)
            self.assertEqual(parsed.questions[0]["options"], ["Positive", "Negative"])

    def test_scanned_pdf_requires_external_ocr(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "scanned.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with path.open("wb") as handle:
                writer.write(handle)
            with self.assertRaisesRegex(ValueError, "Scanned PDFs"):
                read_survey_document(path)

    def test_invalid_source_does_not_invent_answers(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "not_a_document.csv"
            path.write_text("1. Choose a\nA) Yes\nB) No")
            with self.assertRaisesRegex(ValueError, "DOCX"):
                read_survey_document(path)
        with self.assertRaisesRegex(ValueError, "No numbered questions"):
            parse_question_lines(
                ["Employee satisfaction", "Answer the statements below"],
                "file.docx",
            )

    def test_large_docs_and_unvalidated_draft(self):
        with self.assertRaisesRegex(ValueError, "120-question"):
            parse_question_lines(
                [f"{i}. Fictional item {i}?" for i in range(1, 125)],
                "large.docx",
            )
        with self.assertRaisesRegex(ValueError, "too many lines"):
            parse_question_lines(["One"] * 30001, "huge.docx")


if __name__ == "__main__":
    unittest.main()
