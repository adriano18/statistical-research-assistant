"""Exercise the actual Word draft import picker and explicit review gate."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import flet as ft
from docx import Document

from survey_ui import build_survey_workspace
from survey_storage import list_surveys


class DummyPage:
    def __init__(self):
        self.services = []
        self.updates = 0
        self.web = False

    def update(self):
        self.updates += 1


def descendants(control, seen=None):
    if seen is None:
        seen = set()
    if control is None or isinstance(control, (str, bytes, int, float, bool)):
        return
    if isinstance(control, (tuple, list)):
        for child in control:
            yield from descendants(child, seen)
        return
    if id(control) in seen:
        return
    seen.add(id(control))
    yield control
    for prop in ("controls", "content", "title"):
        yield from descendants(getattr(control, prop, None), seen)


def button(root, label):
    matches = [
        node for node in descendants(root)
        if isinstance(node, ft.Button)
        and (node.content == label or
             getattr(node.content, "value", None) == label)
    ]
    if len(matches) != 1:
        raise AssertionError(f"Expected one button {label}: {len(matches)}")
    return matches[0]


class DocumentDraftUIRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        doc = Document()
        doc.add_paragraph("1. Rate this imaginary service?")
        doc.add_paragraph("A) Excellent")
        doc.add_paragraph("B) Poor")
        doc.add_paragraph("2. Optional comments?")
        self.document = self.path / "practice.docx"
        doc.save(self.document)
        self.page = DummyPage()

        async def loader(frame):
            return True

        self.view = build_survey_workspace(
            self.page, load_dataframe=loader, root=self.path,
        )

    async def _import(self):
        picker = self.page.services[-1]
        await picker.on_result(SimpleNamespace(files=[
            SimpleNamespace(path=str(self.document), name="practice.docx")
        ]))

    def _status(self):
        return [node.value for node in descendants(self.view)
                if isinstance(node, ft.Text) and isinstance(node.value, str)]

    async def test_word_import_requires_explicit_draft_action(self):
        self.assertEqual(list_surveys(self.path), [])
        commit = button(self.view, "Use extracted questions as editable draft")
        self.assertTrue(commit.disabled)
        await self._import()
        self.assertFalse(commit.disabled)
        self.assertTrue(any("2 candidate questions" in x
                            for x in self._status()))
        self.assertEqual(list_surveys(self.path), [])
        commit.on_click(None)
        self.assertTrue(any("scientific review confirmation" in x
                            for x in self._status()))
        reviewed = next(
            node for node in descendants(self.view)
            if isinstance(node, ft.Checkbox)
            and node.label.startswith("I verified the instrument version")
        )
        reviewed.value = True
        commit.on_click(None)
        self.assertTrue(any("Imported 2 editable questions" in x
                            for x in self._status()))
        self.assertEqual(list_surveys(self.path), [])
        self.assertTrue(any("2 question(s)" in x for x in self._status()))

    async def test_existing_draft_requires_overwrite_confirmation(self):
        load_template = button(self.view, "Load template")
        load_template.on_click(None)
        await self._import()
        reviewed = next(
            node for node in descendants(self.view)
            if isinstance(node, ft.Checkbox)
            and node.label.startswith("I verified the instrument version")
        )
        reviewed.value = True
        commit = button(self.view, "Use extracted questions as editable draft")
        commit.on_click(None)
        self.assertTrue(any("unsaved questions" in x for x in self._status()))
        confirm = next(
            node for node in descendants(self.view)
            if isinstance(node, ft.Checkbox)
            and node.label == "Replace existing unsaved draft questions"
        )
        confirm.value = True
        commit.on_click(None)
        self.assertTrue(any("Imported 2 editable questions" in x
                            for x in self._status()))
        self.assertEqual(list_surveys(self.path), [])


if __name__ == "__main__":
    unittest.main()
