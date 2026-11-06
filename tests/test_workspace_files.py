"""Stage 34.5: one save path for every export (workspace_files.py)."""

from __future__ import annotations

import errno
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import workspace_files as wf  # noqa: E402
from workspace_text import T  # noqa: E402


def t(key, **values):
    return T[key][0].format(**values)


class ExtensionTests(unittest.TestCase):
    def test_the_extension_is_appended_never_swapped(self):
        cases = {
            "results": "results.docx",
            "results.docx": "results.docx",
            "results.DOCX": "results.DOCX",
            "wave.2": "wave.2.docx",          # not "wave.docx"
            "results.": "results.docx",       # Windows drops trailing dots
            "results.docx ": "results.docx",
            ".docx": ".docx.docx",
        }
        for typed, expected in cases.items():
            with self.subTest(typed=typed):
                self.assertEqual(wf.with_extension(Path("/x") / typed, "docx").name, expected)
        self.assertEqual(wf.with_extension(Path("/x/report"), ".txt").name, "report.txt")


class WriteTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def test_a_written_file_is_checked_on_disk(self):
        target = self.base / "a.txt"
        self.assertEqual(wf.write_verified(target, lambda p: p.write_text("x")), target)

    def test_a_writer_that_writes_nothing_is_a_failure(self):
        with self.assertRaises(wf.NotWritten):
            wf.write_verified(self.base / "a.txt", lambda p: None)
        with self.assertRaises(wf.NotWritten):
            wf.write_verified(self.base / "b.txt", lambda p: p.write_bytes(b""))

    def test_the_path_a_writer_returns_is_the_one_checked(self):
        other = self.base / "other.sra"
        self.assertEqual(wf.write_verified(self.base / "a.sra",
                                           lambda p: (other.write_bytes(b"1"), other)[1]), other)

    def test_a_missing_folder_is_reported_before_writing(self):
        writer = mock.Mock()
        with self.assertRaises(FileNotFoundError):
            wf.write_verified(self.base / "missing" / "a.txt", writer)
        writer.assert_not_called()

    def test_only_an_empty_file_left_by_the_dialog_is_removed(self):
        since = time.time()
        typed = self.base / "results"
        typed.write_bytes(b"")
        wf.remove_placeholder(typed, self.base / "results.docx", since)
        self.assertFalse(typed.exists(), "the dialog's empty placeholder is gone")
        kept = self.base / "notes"
        kept.write_text("researcher notes")
        wf.remove_placeholder(kept, self.base / "notes.docx", since)
        self.assertTrue(kept.exists(), "a file with content is never touched")
        same = self.base / "same.docx"
        same.write_bytes(b"")
        wf.remove_placeholder(same, same, since)
        self.assertTrue(same.exists())


class ExplainTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)

    def message(self, error, path=None):
        text = wf.explain(error, path or self.base / "results.docx", t)
        self.assertNotIn("Errno", text)
        self.assertNotIn("Traceback", text)
        return text

    def test_every_failure_says_what_to_do(self):
        locked = self.base / "open.docx"
        locked.write_bytes(b"1")
        cases = [
            (PermissionError(errno.EACCES, "Permission denied"), locked, "open in another program"),
            (PermissionError(errno.EACCES, "Permission denied"), None, "cannot be written to"),
            (FileNotFoundError(errno.ENOENT, "No such file"), self.base / "gone" / "a.docx",
             "does not exist"),
            (FileNotFoundError(errno.ENOENT, "No such file"), None, "did not allow"),
            (OSError(errno.ENOSPC, "No space left on device"), None, "not enough space"),
            (OSError(errno.EINVAL, "Invalid argument"), None, "cannot be used as a file name"),
            (IsADirectoryError(errno.EISDIR, "Is a directory"), None, "is a folder"),
            (wf.NotWritten(errno.EIO, "not written"), None, "was not written"),
            (ValueError("No valid PNG chart available for export."), None,
             "No valid PNG chart available for export. Choose"),
        ]
        for error, path, expected in cases:
            with self.subTest(error=type(error).__name__, expected=expected):
                self.assertIn(expected, self.message(error, path))

    def test_the_messages_exist_in_every_language(self):
        for key in [k for k in T if k.startswith("save.")]:
            with self.subTest(key=key):
                self.assertEqual(len(T[key]), 3)
                self.assertTrue(all(T[key]))


class QuestionnaireExportTests(unittest.TestCase):
    def test_responses_export_writes_the_csv_and_its_codebook(self):
        from survey_storage import create_survey, submit_response
        from workspace_harness import Workspace

        ws = Workspace()
        self.addCleanup(ws.close)
        survey = create_survey(ws.app.survey_root, "Fictional export check", "Fictional", [
            {"key": "q1", "kind": "likert5", "prompt": "Fictional statement", "required": True,
             "options": []}])
        submit_response(ws.app.survey_root, survey.survey_id, {"q1": "3"})
        typed = ws.root / "responses"

        async def dialog(title, file_name, extension):
            return str(typed)

        ws.app.save_dialog = dialog
        ws.app.navigate("questionnaires")
        ws.click(f"export-responses-{survey.survey_id}")
        csv_file = typed.with_name("responses.csv")
        self.assertTrue(csv_file.is_file())
        self.assertIn("q1", csv_file.read_text(encoding="utf-8-sig"))
        self.assertTrue(typed.with_name("responses_codebook.json").is_file())
        self.assertIn("responses_codebook.json", ws.app.status_text.value)


if __name__ == "__main__":
    unittest.main()
