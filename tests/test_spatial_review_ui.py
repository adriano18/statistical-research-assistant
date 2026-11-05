"""Flet spatial review: overlays, zoom sync, region edits, queue and matrix grid.

Uses the real survey workspace with synthetic documents. OCR output is
injected (mocked) except in the final test, which uses a real local engine
when one is available.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import flet as ft

from ocr_layout import link_candidates, parse_tesseract_tsv
from ocr_runtime import OCRCancelled, tesseract_available
from scientific_survey_import import parse_scientific_lines
from survey_ui import build_survey_workspace
from survey_storage import list_surveys
from synthetic_documents import (
    docx_matrix, image_pdf, matrix_text_pdf, questionnaire_image,
)
from test_ocr_layout import SAMPLE
from test_visual_survey_import_ui import DummyPage, children, find
from dataclasses import replace

CONFIRM = ("I verified the instrument version, wording, permissions "
           "and extracted question list against the source")


def texts(view):
    return " ".join(
        c.value for c in children(view) if isinstance(c, ft.Text) and isinstance(c.value, str)
    )


def overlays(view, kind="region"):
    stack = find(view, ft.Stack)
    return [c for c in stack.controls
            if isinstance(getattr(c, "data", None), tuple) and c.data[0] == kind]


class SpatialReviewUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.page = DummyPage()

        async def noop_import(frame):
            return True

        self.view = build_survey_workspace(
            self.page, root=self.root, load_dataframe=noop_import,
        )

    async def pick(self, path: Path):
        picker = self.page.services[-1]
        await picker.on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(path), name=path.name)]
        ))

    async def test_text_pdf_overlays_follow_zoom_and_select_questions(self):
        path = self.root / "synthetic_matrix.pdf"
        path.write_bytes(matrix_text_pdf())
        await self.pick(path)
        regions = overlays(self.view)
        self.assertEqual(len(regions), 4)
        first = regions[0]
        position = (first.left, first.top, first.width)
        zoom = next(c for c in children(self.view) if isinstance(c, ft.Slider))
        zoom.value = 200
        zoom.on_change(None)
        zoomed = overlays(self.view)[0]
        self.assertEqual(zoomed.data, first.data)
        for before, after in zip(position, (zoomed.left, zoomed.top, zoomed.width)):
            self.assertAlmostEqual(after, before * 2, places=4)
        image = find(self.view, ft.Image)
        self.assertAlmostEqual(image.width, 1120)
        # Selecting a box focuses its question in the editor.
        third = overlays(self.view)[2]
        await third.on_click(None)
        picker = find(self.view, ft.Dropdown, label="Question to review / edit")
        self.assertEqual(picker.value, "2")
        prompt = find(self.view, ft.TextField, label="Correct question wording")
        self.assertIn("rely on fictional colleagues", prompt.value)
        status = texts(self.view)
        self.assertIn("OCR confidence (raw Tesseract word scores)", status)
        self.assertIn("unknown", status)  # text layer: no OCR scores
        self.assertIn("not a percentage", status)
        # Matrix proposal from text geometry is offered for review.
        tile = next(c for c in children(self.view) if isinstance(c, ft.ExpansionTile)
                    and getattr(c.title, "value", "").startswith("MATRIX EDITOR"))
        self.assertTrue(tile.visible)
        self.assertEqual(list_surveys(self.root), [])

    async def test_unlinked_text_never_creates_a_question_and_link_mode(self):
        path = self.root / "synthetic_matrix.pdf"
        path.write_bytes(matrix_text_pdf())
        await self.pick(path)
        lines = overlays(self.view, "line")
        self.assertTrue(lines)
        picker = find(self.view, ft.Dropdown, label="Question to review / edit")
        before = len(picker.options)
        lines[0].on_click(None)
        self.assertIn("No question was created", texts(self.view))
        self.assertEqual(len(picker.options), before)
        link = find(self.view, ft.Checkbox,
                    label="Link mode: clicking unlinked text attaches it to the selected question")
        link.value = True
        approved = find(self.view, ft.Checkbox, label=CONFIRM)
        approved.value = True
        overlays(self.view, "line")[0].on_click(None)
        self.assertIn("Linked", texts(self.view))
        self.assertFalse(approved.value)  # any spatial edit resets approval

    async def test_ocr_confidence_queue_and_region_edits(self):
        image = questionnaire_image(noise=False)
        path = self.root / "scan.pdf"
        path.write_bytes(image_pdf(image))
        await self.pick(path)
        layout = parse_tesseract_tsv(SAMPLE, 1, language="eng")
        review = parse_scientific_lines([(1, l.text) for l in layout.lines], "scan.pdf")
        review = replace(review, spatial=link_candidates(review, [layout]))
        with patch("survey_ui.tesseract_available", return_value=True):
            with patch("survey_ui.ocr_scientific_pdf", return_value=review) as ocr:
                await find(self.view, ft.Button, label="Run local OCR on this PDF page").on_click(None)
        self.assertEqual(ocr.call_args.kwargs["rotation"], 0)
        self.assertIn("cancel", ocr.call_args.kwargs)
        self.assertIn("Local OCR completed", texts(self.view))
        self.assertEqual(len(overlays(self.view)), 3)
        queue = find(self.view, ft.Dropdown, label="Review queue filter")
        queue.value = "low_unknown"
        queue.on_select(None)
        entries = [c for c in children(self.view) if isinstance(c, ft.TextButton)
                   and isinstance(c.content, str) and "OCR low" in c.content]
        self.assertEqual(len(entries), 1)
        await entries[0].on_click(None)
        self.assertEqual(find(self.view, ft.Dropdown, label="Question to review / edit").value, "1")
        self.assertIn("OCR low", texts(self.view))
        # Split, merge and revert regions of the low-confidence question.
        approved = find(self.view, ft.Checkbox, label=CONFIRM)
        approved.value = True
        find(self.view, ft.Button, label="Split region").on_click(None)
        self.assertFalse(approved.value)
        self.assertEqual(len(overlays(self.view)), 4)
        find(self.view, ft.Button, label="Merge this question's regions").on_click(None)
        self.assertEqual(len(overlays(self.view)), 3)
        fields = [find(self.view, ft.TextField, label=n) for n in ("Left %", "Top %", "Right %", "Bottom %")]
        fields[2].value = "60"
        find(self.view, ft.Button, label="Apply region box").on_click(None)
        self.assertIn("Region box adjusted", texts(self.view))
        find(self.view, ft.Button, label="Revert all regions").on_click(None)
        self.assertIn("All detected regions restored", texts(self.view))
        # Rotating the view hides stale overlays instead of misplacing them.
        rotation = find(self.view, ft.Dropdown, label="Page view rotation")
        rotation.value = "90"
        await rotation.on_select(None)
        self.assertEqual(overlays(self.view), [])
        self.assertIn("Overlay hidden", texts(self.view))

    async def test_cancelled_ocr_keeps_existing_proposal(self):
        path = self.root / "scan.pdf"
        path.write_bytes(image_pdf(questionnaire_image(noise=False)))
        await self.pick(path)
        with patch("survey_ui.tesseract_available", return_value=True):
            with patch("survey_ui.ocr_scientific_pdf", side_effect=OCRCancelled("x")):
                await find(self.view, ft.Button, label="OCR first 20 PDF pages").on_click(None)
        self.assertIn("OCR cancelled", texts(self.view))
        self.assertTrue(find(self.view, ft.Button, label="Cancel OCR").disabled)

    async def test_docx_matrix_grid_edit_verify_and_scoring_confirmation(self):
        path = self.root / "team_climate.docx"
        path.write_bytes(docx_matrix())
        await self.pick(path)
        self.assertIn("response-matrix proposal", texts(self.view))
        commit = find(self.view, ft.Button, label="Use verified matrix rows as editable draft")
        self.assertTrue(commit.disabled)
        # Edit the first column label in the grid and apply.
        label = next(c for c in children(self.view) if isinstance(c, ft.TextField)
                     and c.hint_text == "label" and c.value == "Never")
        label.value = "Not at all"
        find(self.view, ft.Button, label="Apply grid edits").on_click(None)
        self.assertIn("NOT verified", texts(self.view))
        find(self.view, ft.Button, label="Verify grid against source").on_click(None)
        self.assertIn("VERIFIED grid mapping", texts(self.view))
        commit = find(self.view, ft.Button, label="Use verified matrix rows as editable draft")
        self.assertFalse(commit.disabled)
        codes = find(self.view, ft.Checkbox,
                     label="Apply printed numeric codes as scale values (reviewed by researcher)")
        codes.value = True
        commit.on_click(None)
        self.assertIn("scientific review confirmation", texts(self.view))
        find(self.view, ft.Checkbox, label=CONFIRM).value = True
        find(self.view, ft.Checkbox, label="Replace existing unsaved draft questions").value = True
        commit.on_click(None)
        self.assertIn("Imported 4 editable matrix questions", texts(self.view))
        self.assertEqual(list_surveys(self.root), [])

    @unittest.skipUnless(tesseract_available(), "No local Tesseract engine installed")
    async def test_real_ocr_produces_overlays_in_the_app(self):
        path = self.root / "real_scan.pdf"
        path.write_bytes(image_pdf(questionnaire_image()))
        await self.pick(path)
        await find(self.view, ft.Button, label="Run local OCR on this PDF page").on_click(None)
        self.assertIn("Local OCR completed", texts(self.view))
        self.assertGreaterEqual(len(overlays(self.view)), 3)
        self.assertRegex(texts(self.view), r"OCR (high|review|low)")


if __name__ == "__main__":
    unittest.main()
