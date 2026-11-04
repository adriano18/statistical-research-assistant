"""Local renderer, OCR and scientific question editor regressions.

The PDF fixture is a real image-only PDF. OCR text is injected in tests;
the production path uses ONLY an installed local Tesseract CLI.
"""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from docx import Document
from PIL import Image, ImageDraw
from pypdf import PdfReader

from scientific_survey_import import parse_scientific_lines
from visual_survey_review import (
    render_pdf_page, render_word_structure, render_document_page,
    pdf_page_count, ocr_scientific_pdf, recognize_page,
    edit_candidate_question, tesseract_available,
)


def scanned_pdf():
    image = Image.new("RGB", (700, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.text((45, 75), "1. Fictional quality of service question?", fill="black")
    draw.text((45, 140), "2. Fictional helpfulness of staff question?", fill="black")
    draw.text((45, 210), "3. Fictional overall satisfaction question?", fill="black")
    stream = BytesIO()
    image.save(stream, "PDF")
    return stream.getvalue()


class VisualSourceTests(unittest.TestCase):
    def test_render_real_scanned_pdf_page_as_bounded_png(self):
        original = scanned_pdf()
        self.assertEqual(pdf_page_count(original), 1)
        self.assertFalse((PdfReader(BytesIO(original)).pages[0].extract_text() or "").strip())
        actual = render_pdf_page(original, 1, scale=2.2)
        self.assertTrue(actual.startswith(b"\x89PNG\r\n\x1a\n"))
        picture = Image.open(BytesIO(actual))
        self.assertLessEqual(picture.width * picture.height, 5_000_000)
        self.assertLessEqual(picture.width, 1300)
        with self.assertRaisesRegex(ValueError, "page outside"):
            render_pdf_page(original, 2)

    def test_word_view_is_an_image_not_false_native_page(self):
        doc = Document()
        doc.add_paragraph("1. Fictional employee satisfaction?")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "A) Good"
        table.cell(1, 0).text = "B) Poor"
        buffer = BytesIO()
        doc.save(buffer)
        image = render_word_structure(buffer.getvalue(), ".docx")
        self.assertTrue(image.startswith(b"\x89PNG"))
        self.assertEqual(
            render_document_page(buffer.getvalue(), "staff.docx", 1), image
        )
        with self.assertRaisesRegex(ValueError, "page unavailable"):
            render_document_page(buffer.getvalue(), "staff.docx", 2)

    def test_long_multilingual_word_preview_has_multiple_segments(self):
        from visual_survey_review import word_structure_page_count
        doc = Document()
        for i in range(1, 70):
            doc.add_paragraph(
                f"{i}. Как Вы оцениваете качество услуги? "
                "Это синтетический текст для проверки длинной анкеты."
            )
        output = BytesIO()
        doc.save(output)
        source = output.getvalue()
        parts = word_structure_page_count(source, ".docx")
        self.assertGreater(parts, 1)
        first = render_word_structure(source, ".docx", page_number=1)
        last = render_word_structure(source, ".docx", page_number=parts)
        self.assertTrue(first.startswith(bytes((137, 80, 78, 71))))
        self.assertNotEqual(first, last)
        with self.assertRaisesRegex(ValueError, "page unavailable"):
            render_word_structure(source, ".docx", page_number=parts+1)

    def test_local_ocr_overlays_selected_page_without_network(self):
        fixture = scanned_pdf()
        observed = []
        def fake_ocr(png, lang):
            self.assertTrue(png.startswith(b"\x89PNG"))
            observed.append(lang)
            return "\n".join(
                f"{i}. Fictional staff feedback question number {i}?"
                for i in range(1, 4)
            )
        result = ocr_scientific_pdf(
            fixture, "fictional_scan.pdf", [1], "eng",
            recognizer=fake_ocr,
        )
        self.assertEqual(observed, ["eng"])
        self.assertEqual(result.page_count, 1)
        self.assertEqual(len(result.instruments[0].questions), 3)
        self.assertEqual(result.instruments[0].questions[0].page, 1)
        self.assertTrue(any("OCR pages: 1" in w for w in result.warnings))
        self.assertTrue(any("may contain substitutions" in w
                            for w in result.warnings))

    def test_local_ocr_rejects_invalid_pages_and_langs(self):
        fixture = scanned_pdf()
        fake = lambda image, language: "1. A fictional survey question?"
        with self.assertRaisesRegex(ValueError, "1–20"):
            ocr_scientific_pdf(
                fixture, "scan.pdf", [0], "eng", recognizer=fake,
            )
        with self.assertRaisesRegex(ValueError, "OCR language"):
            ocr_scientific_pdf(
                fixture, "scan.pdf", [1], "malicious+name", recognizer=fake,
            )
        with patch.dict("os.environ", {"TESSERACT_CMD": ""}):
            with patch("visual_survey_review.shutil.which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "not installed"):
                    recognize_page(b"\x89PNGdummy", "eng")

    def test_edit_question_preserves_original_source_and_is_atomic(self):
        source = parse_scientific_lines(
            [(1,"1. Is your fictional study environment comfortable?"),
             (1,"A) Yes"), (1,"B) No"),
             (1,"2. How many days did you attend the workshop?")],
            "fictional.docx",
        )
        original = source.instruments[0]
        edited = edit_candidate_question(
            original, 0,
            prompt="How comfortable is your fictional working environment?",
            kind="single_choice",
            options_text="Very comfortable\nSomewhat comfortable\nUncomfortable",
            section="Workplace survey", required=True,
        )
        self.assertEqual(
            edited.questions[0].question["options"],
            ["Very comfortable", "Somewhat comfortable", "Uncomfortable"],
        )
        self.assertTrue(edited.questions[0].question["required"])
        self.assertEqual(edited.questions[0].page, original.questions[0].page)
        self.assertEqual(edited.questions[0].excerpt, original.questions[0].excerpt)
        self.assertEqual(original.questions[0].question["prompt"],
                         "Is your fictional study environment comfortable?")
        self.assertEqual(edited.questions[1], original.questions[1])
        with self.assertRaisesRegex(ValueError, "Choice questions"):
            edit_candidate_question(
                original, 0, prompt="Valid question?",
                kind="single_choice", options_text="Only one",
                section="Workplace", required=False,
            )
        with self.assertRaisesRegex(ValueError, "needs a prompt"):
            edit_candidate_question(
                original, 0, prompt=" ", kind="short_text",
                options_text="", section="", required=False,
            )


if __name__ == "__main__":
    unittest.main()
