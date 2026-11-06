"""End-to-end tests with a REAL local Tesseract engine on synthetic scans.

These tests run whenever a Tesseract binary can be resolved (bundled
runtime, ``TESSERACT_CMD`` or ``PATH``); CI installs one on Linux and uses
the bundled runtime on Windows. Without an engine they are skipped, and the
mocked-recognizer tests elsewhere still cover the logic.
"""

import os
import unittest

from matrix_reconstruction import geometric_matrices
from ocr_layout import OCR_CATEGORIES, question_ref
from ocr_runtime import ocr_readiness, tesseract_available
from synthetic_documents import image_pdf, questionnaire_image, text_lines_image
from visual_survey_review import (
    _render_pdf_page, ocr_scientific_pdf, recognize_page, recognize_page_layout,
)

REQUIRE = os.environ.get("SRA_REQUIRE_REAL_OCR") == "1"
AVAILABLE = tesseract_available()


def languages():
    return set(ocr_readiness(use_cache=False).languages) if AVAILABLE else set()


@unittest.skipUnless(AVAILABLE or REQUIRE, "No local Tesseract engine installed")
class RealTesseractTests(unittest.TestCase):
    def test_engine_reports_version_and_required_languages(self):
        ready = ocr_readiness(use_cache=False)
        self.assertTrue(ready.available, ready.summary())
        self.assertTrue(ready.version.lower().startswith("tesseract"))
        if REQUIRE:
            self.assertEqual(ready.missing_languages, (), ready.summary())

    def test_tsv_layout_has_boxes_and_real_word_confidence(self):
        pdf = image_pdf(questionnaire_image())
        png, dpi = _render_pdf_page(pdf, 1, scale=2.0, max_width=1800)
        page = recognize_page_layout(png, "eng", dpi=dpi)
        self.assertEqual(page.source, "tesseract_tsv")
        self.assertGreater(len(page.words), 30)
        scored = [w.confidence for w in page.words if w.confidence is not None]
        self.assertGreater(len(scored), 30)
        self.assertTrue(all(0 <= s <= 100 for s in scored))
        for word in page.words:
            x0, y0, x1, y1 = word.box
            self.assertTrue(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1)
        text = " ".join(l.text for l in page.lines)
        self.assertIn("Synthetic", text)
        self.assertIn("Never", text)
        plain = recognize_page(png, "eng")
        self.assertIn("Synthetic", plain)

    def test_scanned_pdf_review_links_regions_and_confidence(self):
        pdf = image_pdf(questionnaire_image(wrap_second=True))
        review = ocr_scientific_pdf(pdf, "synthetic_scan.pdf", [1], "eng")
        evidence = review.spatial
        self.assertIsNotNone(evidence)
        questions = review.instruments[0].questions
        self.assertGreaterEqual(len(questions), 3)
        linked = [question_ref(0, j) for j in range(len(questions))
                  if evidence.regions(question_ref(0, j))]
        self.assertGreaterEqual(len(linked), 3)
        for ref in linked:
            confidence = evidence.confidence(ref)
            self.assertIn(confidence.category, OCR_CATEGORIES)
            self.assertIsNotNone(confidence.mean)
        self.assertTrue(any("NOT a measure of reliability" in w for w in review.warnings))
        # Matrix columns come from the printed 0–4 codes.
        self.assertTrue(review.matrices)
        matrix = review.matrices[0]
        self.assertEqual(len(matrix.columns), 5)
        self.assertGreaterEqual(len(matrix.rows), 3)
        self.assertFalse(matrix.verified)

    def test_skewed_and_rotated_scans(self):
        skewed = image_pdf(questionnaire_image(skew=1.5))
        review = ocr_scientific_pdf(skewed, "skewed.pdf", [1], "eng")
        self.assertGreaterEqual(len(review.instruments[0].questions), 3)
        sideways = image_pdf(questionnaire_image(noise=False).rotate(90, expand=True))
        with self.assertRaises(ValueError):
            ocr_scientific_pdf(sideways, "sideways.pdf", [1], "eng")
        fixed = ocr_scientific_pdf(sideways, "sideways.pdf", [1], "eng", rotation=90)
        self.assertEqual(fixed.spatial.pages[0].rotation, 90)
        self.assertGreaterEqual(len(fixed.instruments[0].questions), 3)
        self.assertTrue(geometric_matrices(fixed.spatial.pages))

    def test_multilingual_latvian_and_russian(self):
        installed = languages()
        if not {"lav", "rus"} <= installed:
            if REQUIRE:
                self.fail(f"lav/rus language data missing: {sorted(installed)}")
            self.skipTest("lav/rus language data not installed")
        image = text_lines_image([
            "1. Cik bieži sintētiskā nedēļa bija mierīga?",
            "2. Как часто вымышленные задачи были простыми?",
            "3. How often did invented plans change?",
        ])
        pdf = image_pdf(image)
        png, dpi = _render_pdf_page(pdf, 1, scale=2.0, max_width=1800)
        seen = {}
        for language in ("lav", "lav+rus", "lav+rus+eng", "eng+lav+rus"):
            page = recognize_page_layout(png, language, dpi=dpi)
            seen[language] = " / ".join(line.text for line in page.lines)
        report = "; ".join(f"{k}: {v}" for k, v in seen.items())
        print("\nMultilingual OCR:", report)
        # The Latvian model alone must recover Latvian diacritics.
        self.assertIn("nedēļa", seen["lav"], report)
        # The UI's "All three · Latvian main" preset (Tesseract 5.5 favours
        # the first language; English-first loses ē/ļ on that engine).
        review = ocr_scientific_pdf(pdf, "multilingual.pdf", [1], "lav+rus+eng")
        text = " ".join(q.question["prompt"] for q in review.instruments[0].questions)
        self.assertIn("вымышленные", text, report)
        self.assertIn("nedēļa", text, report)


if __name__ == "__main__":
    unittest.main()
