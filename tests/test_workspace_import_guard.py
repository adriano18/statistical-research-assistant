"""Stage 34.5 (issue #31, P0 items 8 and 9): an imported questionnaire never
silently replaces or mixes with a draft, and documents that cannot be read
say so with what to do instead. Synthetic documents only."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from workspace_harness import Workspace  # noqa: E402

OWN_DRAFT = [
    {"key": "own_1", "kind": "likert5", "prompt": "Fictional own statement", "required": True,
     "options": []},
    {"key": "own_2", "kind": "short_text", "prompt": "Fictional own question", "required": False,
     "options": []},
]


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)

    def reviewed_import(self):
        """The synthetic two-version PDF, reviewed until a draft may be made."""
        from synthetic_documents import connectedness_text_pdf

        ws = self.ws
        page = ws.app.pages["import"]
        ws.app.navigate("import")
        ws.run(page.open_bytes(connectedness_text_pdf(), "synthetic_two_versions.pdf"))
        ws.click("imp-instrument-use-1")   # the researcher chooses the form
        scheme = page.session.instrument.schemes[0]
        ws.click("imp-step-scale")
        ws.check(f"scale-{scheme.id}-structure")
        ws.check(f"scale-{scheme.id}-numeric")
        ws.click(f"scale-{scheme.id}-apply")
        ws.click("imp-step-confirm")
        ws.check("imp-check-version")
        ws.check("imp-check-rights")
        ws.check("imp-check-items")
        return page


class DraftGuardTests(Base):
    def own_draft(self):
        builder = self.ws.app.pages["questionnaires"]
        builder.title = "Fictional own questionnaire"
        builder.description = "Fictional instructions"
        builder.draft = [dict(q) for q in OWN_DRAFT]
        return builder

    def test_an_import_asks_before_replacing_an_unsaved_draft(self):
        ws = self.ws
        builder = self.own_draft()
        page = self.reviewed_import()
        ws.click("imp-create-draft")
        self.assertIsNotNone(ws.page.dialog, "the researcher is asked first")
        self.assertEqual([q["key"] for q in builder.draft], ["own_1", "own_2"])
        ws.click("q-replace-cancel")
        self.assertIsNone(ws.page.dialog)
        self.assertEqual(builder.title, "Fictional own questionnaire", "cancel keeps everything")
        ws.click("imp-create-draft")
        ws.click("q-replace-confirm")
        self.assertEqual(ws.app.route, "questionnaires")
        keys = [q["key"] for q in builder.draft]
        self.assertEqual(len(keys), len(page.session.instrument.questions))
        self.assertFalse({"own_1", "own_2"} & set(keys), "the two drafts are never mixed")
        self.assertEqual(builder.title, page.session.instrument.title,
                         "the imported questionnaire does not inherit the old title")
        self.assertEqual(builder.description, "")

    def test_an_empty_builder_takes_the_import_directly(self):
        ws = self.ws
        self.reviewed_import()
        ws.click("imp-create-draft")
        self.assertIsNone(ws.page.dialog)
        self.assertEqual(ws.app.route, "questionnaires")

    def test_a_template_asks_before_replacing_an_unsaved_draft(self):
        ws = self.ws
        builder = self.own_draft()
        ws.app.navigate("questionnaires")
        ws.click("q-template-load")
        self.assertIsNotNone(ws.page.dialog)
        self.assertEqual([q["key"] for q in builder.draft], ["own_1", "own_2"])
        ws.click("q-replace-confirm")
        self.assertNotIn("own_1", [q["key"] for q in builder.draft])


class UnreadableDocumentTests(Base):
    def test_a_legacy_doc_without_a_converter_explains_what_to_do(self):
        ws = self.ws
        page = ws.app.pages["import"]
        ws.app.navigate("import")
        with mock.patch("workspace_questionnaires.shutil.which", return_value=None):
            ws.run(page.open_bytes(b"\xd0\xcf\x11\xe0fictional legacy word bytes", "inventory.doc"))
        message = ws.find("imp-status")      # the one processing status
        text = " ".join(c.value for c in ws.controls(message) if hasattr(c, "value")
                        and isinstance(c.value, str))
        self.assertIn(".docx", text)
        self.assertIn("Save As", text)
        self.assertIn("Nothing was imported", text)
        self.assertIsNone(page.session.source, "nothing half-opened")
        self.assertTrue(ws.find("imp-choose-other"))
        self.assertIn(".doc", ws.app.status_text.value)

    def test_a_failed_document_leaves_the_one_under_review(self):
        from synthetic_documents import connectedness_text_pdf

        ws = self.ws
        page = ws.app.pages["import"]
        ws.app.navigate("import")
        ws.run(page.open_bytes(connectedness_text_pdf(), "synthetic_two_versions.pdf"))
        ws.run(page.open_bytes(b"fictional", "notes.rtf"))
        self.assertEqual(page.session.filename, "synthetic_two_versions.pdf")
        self.assertIn("not a PDF or Word document", ws.app.status_text.value)

    def test_every_language_has_the_guidance(self):
        from workspace_text import T

        for key in ("imp.unsupported", "imp.doc_unavailable", "q.replace_body"):
            with self.subTest(key=key):
                self.assertTrue(all(T[key]))


if __name__ == "__main__":
    unittest.main()
