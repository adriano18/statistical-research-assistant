"""Stage 34.5 (issue #31): the scientific import review wizard.

Source → shared scale → items → confirmations, with a footer that stays on
screen, counts, a filter for items that need attention, the selected item
edited right under itself, progress with Cancel, independent confirmations
and translated facts. Synthetic documents only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from workspace_harness import Workspace  # noqa: E402


def texts_in(ws, data: str) -> str:
    control = ws.find(data)
    return " ".join(c.value for c in ws.controls(control)
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


def order(ws, prefix: str) -> list[str]:
    return [c.data for c in ws.controls()
            if isinstance(getattr(c, "data", None), str) and c.data.startswith(prefix)]


class Base(unittest.TestCase):
    language = "en"

    def setUp(self):
        self.ws = Workspace(language=self.language)
        self.addCleanup(self.ws.close)
        self.page = self.ws.app.pages["import"]
        self.ws.app.navigate("import")

    def open(self, binary: bytes, name: str):
        self.ws.run(self.page.open_bytes(binary, name))


class PsqLikeWizardTests(Base):
    def setUp(self):
        super().setUp()
        from synthetic_documents import psq_like_pdf

        self.open(psq_like_pdf(), "synthetic_strain.pdf")

    def test_the_source_step_says_what_was_read_and_what_was_kept_out(self):
        ws = self.ws
        self.assertEqual(self.page.step, "source")
        self.assertIn("Found 30 of 30 expected items", texts_in(ws, "imp-fact-count_match"))
        self.assertIn("look like references", texts_in(ws, "imp-fact-references"))
        self.assertIn("local OCR", texts_in(ws, "imp-fact-ocr_read"))
        excluded = ws.find("imp-excluded")
        self.assertIn("(3)", texts_in(ws, "imp-excluded"))
        self.assertIsInstance(excluded, ft.ExpansionTile)

    def test_the_footer_stays_on_every_step_and_create_waits_for_everything(self):
        ws = self.ws
        for step in ("source", "scale", "items", "confirm"):
            with self.subTest(step=step):
                ws.click(f"imp-step-{step}")
                footer = ws.find("workspace-footer")
                self.assertNotIn(footer, ws.controls(ws.app.page_control),
                                 "the footer is outside the scrolling page")
                self.assertTrue(ws.find("imp-create-draft").disabled)
        self.assertIn("step 2", ws.find("imp-create-draft").tooltip)

    def test_confirmations_are_independent(self):
        ws, s = self.ws, self.page.session
        scheme = s.instrument.schemes[0]
        ws.click("imp-step-confirm")
        ws.check("imp-check-version")
        ws.check("imp-check-rights")
        ws.check("imp-check-items")
        ws.click("imp-step-scale")
        ws.check(f"scale-{scheme.id}-structure")
        ws.check(f"scale-{scheme.id}-numeric")
        ws.click(f"scale-{scheme.id}-apply")
        self.assertEqual(s.checks, {"version": True, "rights": True, "items": True},
                         "a scale review keeps the other confirmations")
        ws.click("imp-step-items")
        ws.click("imp-item-3")
        field = ws.find("imp-wording", ft.TextField)   # read when "Apply" is clicked
        field.value = s.instrument.questions[3].question["prompt"] + " (checked)"
        ws.click("imp-wording-apply")
        self.assertTrue(all(s.checks.values()), "a wording correction keeps them too")
        self.assertFalse(ws.find("imp-create-draft").disabled)


class LongFormTests(Base):
    def setUp(self):
        super().setUp()
        from synthetic_documents import numbered_items_pdf

        self.open(numbered_items_pdf(120), "synthetic_120.pdf")

    def test_the_selected_item_is_edited_right_under_itself(self):
        ws = self.ws
        self.assertEqual(len(self.page.session.instrument.questions), 120)
        self.assertIn("Found 120 of 120 expected items", texts_in(ws, "imp-fact-count_match"))
        ws.click("imp-step-items")
        ws.click("imp-item-59")                        # item 60
        sequence = order(ws, "imp-item-") + []
        controls = [c.data for c in ws.controls()
                    if getattr(c, "data", None) in ("imp-item-59", "imp-editor", "imp-item-60")]
        self.assertEqual(controls, ["imp-item-59", "imp-editor", "imp-item-60"])
        self.assertEqual(len(sequence), 120, "every item stays listed")
        self.assertEqual(self.page.page_number, self.page.session.instrument.questions[59].page,
                         "the source page follows the selected item")

    def test_rows_keep_stable_keys(self):
        ws = self.ws
        ws.click("imp-step-items")
        first = ws.find("imp-item-60")
        ws.click("imp-item-59")
        self.assertEqual(ws.find("imp-item-60").key, first.key)

    def test_the_filter_shows_only_items_that_need_attention(self):
        from dataclasses import replace

        ws, s = self.ws, self.page.session
        questions = list(s.instrument.questions)
        for index in (4, 77):
            questions[index] = replace(questions[index], confidence="low")
        s.review = replace(s.review, instruments=(replace(s.instrument, questions=tuple(questions)),))
        ws.click("imp-step-items")
        ws.segment("imp-filter", "attention")
        self.assertEqual(order(ws, "imp-item-"), ["imp-item-4", "imp-item-77"])
        ws.click("imp-item-4")
        ws.check("imp-item-reviewed", True)
        ws.click("imp-next-flag")
        self.assertEqual(self.page.selected, 77)
        self.assertIn("1 compared with the source", texts_in(ws, "imp-counts"))


class ProgressAndCancelTests(Base):
    def test_ocr_shows_progress_and_cancel_keeps_the_text_result(self):
        from ocr_runtime import OCRCancelled
        from synthetic_documents import psq_like_pdf

        ws, page = self.ws, self.page
        started = threading.Event()

        def slow_ocr(source, filename, pages, language, *, cancel=None, progress=None, **kw):
            if progress is not None:
                progress(0, len(pages))
            started.set()
            while not cancel.is_set():
                cancel.wait(0.05)
            raise OCRCancelled()

        async def journey():
            with mock.patch("visual_survey_review.ocr_scientific_pdf", side_effect=slow_ocr), \
                    mock.patch("visual_survey_review.tesseract_available", return_value=True):
                task = asyncio.create_task(page.open_bytes(psq_like_pdf(), "strain.pdf"))
                while not started.is_set():
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.1)
                shown = (ws.find("imp-progress").value, ws.find("imp-cancel"))
                page.cancel_reading()
                await task
                return shown

        progress, cancel = ws.run(journey())
        self.assertIn("Reading page 2 with local OCR (1 of 1)", progress)
        self.assertIsNotNone(cancel)
        facts = dict(page.session.facts)
        self.assertIn("ocr_cancelled", facts)
        self.assertFalse(page.busy)
        self.assertIn("cancelled", texts_in(ws, "imp-fact-ocr_cancelled"))


class TranslatedFactsTests(Base):
    language = "ru"

    def test_no_engine_english_reaches_a_russian_screen(self):
        from synthetic_documents import psq_like_pdf

        self.open(psq_like_pdf(), "synthetic_strain.pdf")
        text = " ".join(texts_in(self.ws, f"imp-fact-{key}") for key, _ in self.page.session.facts)
        self.assertIn("Найдено 30 из 30", text)
        self.assertIn("страница 2", text)
        self.assertNotIn("look like references", text)
        self.assertNotIn("Found", text)

    def test_pages_are_named_in_every_language(self):
        from workspace_questionnaires import pages_text

        self.assertEqual(pages_text("en", [5, 2, 3]), "pages 2, 3 and 5")
        self.assertEqual(pages_text("lv", [2]), "2. lappuse")
        self.assertEqual(pages_text("lv", [2, 3]), "2. un 3. lappuse")
        self.assertEqual(pages_text("ru", [2, 3]), "страницы 2 и 3")


if __name__ == "__main__":
    unittest.main()
