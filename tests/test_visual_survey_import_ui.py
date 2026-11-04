"""Exercise the real Flet survey builder's source preview and visual corrections."""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import flet as ft
from docx import Document
from PIL import Image

from scientific_survey_import import parse_scientific_lines
from survey_ui import build_survey_workspace
from survey_storage import list_surveys


class DummyPage:
    def __init__(self):
        self.services = []
        self.updates = 0
        self.web = False

    def update(self):
        self.updates += 1


def children(control, seen=None):
    if seen is None:
        seen = set()
    if control is None or isinstance(control, (str, bytes, int, bool, float)):
        return
    if isinstance(control, (list, tuple)):
        for item in control:
            yield from children(item, seen)
        return
    if id(control) in seen:
        return
    seen.add(id(control))
    yield control
    for name in ("controls", "content", "title"):
        yield from children(getattr(control, name, None), seen)


def find(root, cls, *, label=None):
    objects = [
        control for control in children(root) if isinstance(control, cls)
        and (label is None or (
            getattr(control, "label", None) == label
            or getattr(control, "content", None) == label
        ))
    ]
    if len(objects) != 1:
        raise AssertionError(f"Expected one {cls.__name__}/{label}: {len(objects)}")
    return objects[0]


class VisualImportUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.page = DummyPage()
        doc = Document()
        doc.add_paragraph("1. How was the fictional service?")
        doc.add_paragraph("A) Excellent")
        doc.add_paragraph("B) Poor")
        doc.add_paragraph("2. Do you have any fictional suggestions?")
        self.word = self.root / "practice.docx"
        doc.save(self.word)

        async def noop_import(frame):
            return True

        self.view = build_survey_workspace(
            self.page, root=self.root, load_dataframe=noop_import,
        )

    async def test_import_word_preview_and_correct_before_commit(self):
        await self.page.services[-1].on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(self.word), name=self.word.name)]
        ))
        image = find(self.view, ft.Image)
        self.assertTrue(image.visible)
        self.assertTrue(image.src.startswith(b"\x89PNG"))
        dropdown = find(
            self.view, ft.Dropdown, label="Question to review / edit",
        )
        self.assertFalse(dropdown.disabled)
        question = find(
            self.view, ft.TextField, label="Correct question wording",
        )
        question.value = "How satisfied are you with this fictional service?"
        options = find(
            self.view, ft.TextField, label="Choice labels · one per line",
        )
        options.value = "Very good\nAverage\nPoor"
        save = find(
            self.view, ft.Button, label="Apply correction to extracted question",
        )
        save.on_click(None)
        self.assertIn(
            "Correction saved", " ".join(x.value for x in children(self.view)
            if isinstance(x, ft.Text) and x.value),
        )
        approved = find(
            self.view, ft.Checkbox,
            label="I verified the instrument version, wording, permissions "
                  "and extracted question list against the source",
        )
        self.assertFalse(approved.value)
        approved.value = True
        find(self.view, ft.Button,
             label="Use extracted questions as editable draft").on_click(None)
        self.assertTrue(any(
            "Imported 2 editable questions" in item.value
            for item in children(self.view)
            if isinstance(item, ft.Text) and item.value
        ))
        self.assertEqual(list_surveys(self.root), [])
        self.assertTrue(any(
            "How satisfied are you" in item.value
            for item in children(self.view)
            if isinstance(item, ft.TextField) and item.value
        ) or any(
            "How satisfied are you" in item.content
            for item in children(self.view)
            if isinstance(item, ft.Button) and isinstance(item.content, str)
        ))

    async def test_scanned_pdf_can_be_viewed_and_locally_ocr_reviewed(self):
        image = Image.new("RGB", (600, 800), "white")
        stream = BytesIO()
        image.save(stream, "PDF")
        path = self.root / "scan.pdf"
        path.write_bytes(stream.getvalue())

        await self.page.services[-1].on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(path), name=path.name)]
        ))
        preview = find(self.view, ft.Image)
        self.assertTrue(preview.visible)
        self.assertTrue(preview.src.startswith(b"\x89PNG"))
        status = [item.value for item in children(self.view)
                  if isinstance(item, ft.Text) and item.value]
        self.assertTrue(any("No text-based questionnaire" in x for x in status))
        self.assertEqual(list_surveys(self.root), [])

        review = parse_scientific_lines(
            [(1, f"{i}. Fictional event number {i} happened this week?")
             for i in range(1, 4)],
            "scan.pdf",
        )
        with patch("survey_ui.tesseract_available", return_value=True):
            with patch("survey_ui.ocr_scientific_pdf", return_value=review):
                button = find(
                    self.view, ft.Button,
                    label="Run local OCR on this PDF page",
                )
                self.assertFalse(button.disabled)
                await button.on_click(None)
        status = [item.value for item in children(self.view)
                  if isinstance(item, ft.Text) and item.value]
        self.assertTrue(any("Local OCR completed" in x for x in status))
        approved = find(
            self.view, ft.Checkbox,
            label="I verified the instrument version, wording, permissions "
                  "and extracted question list against the source",
        )
        self.assertFalse(approved.value)
        self.assertEqual(
            len(find(self.view, ft.Dropdown,
                     label="Question to review / edit").options), 3,
        )


if __name__ == "__main__":
    unittest.main()
