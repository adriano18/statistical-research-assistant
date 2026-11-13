"""Stage 37 (#67): the Export card in the workspace, through the real handlers.

One card on the Data, Results and Reports pages: the format (remembered),
one button to the Save dialog, the advanced options folded away, the .sav
preview of every renamed or cut field, the participant warning, and an
outcome that names the verified file. Synthetic data only.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

import flet as ft
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_stage37_export import (  # noqa: E402
    LV_NAME, RU_NAME, SYNTAX_ANALYSES, generate_master, master_session)
from workspace_harness import Workspace  # noqa: E402
from workspace_text import T as TABLE  # noqa: E402


def T(key: str, **values) -> str:
    text = TABLE[key][0]
    return text.format(**values) if values else text


def texts(ws, data: str) -> list[str]:
    return [c.value for c in ws.controls(ws.find(data)) if isinstance(c, ft.Text)]


class WorkspaceCase(unittest.TestCase):
    language = "en"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = Workspace(root=self.root, language=self.language)
        self.addCleanup(self.ws.close)

    def open_master(self, *, adversarial: bool = False):
        session = master_session(self.root / "fixture", adversarial=adversarial)
        app = self.ws.app
        app.session.set_dataset(session.df, session.source_name)
        for name, info in session.variables.items():
            app.session.confirm_level(name, info.confirmed)
        app.session.set_metadata(session.metadata())
        self.ws.click("nav-data")


class DataExportTests(WorkspaceCase):
    def test_one_click_gives_a_verified_lossless_copy_with_its_codebook(self):
        self.open_master()
        self.assertEqual(self.ws.find("export-format-data").value, "xlsx")
        self.assertEqual(self.ws.find("export-save-data").content, T("export.save.xlsx"))
        self.assertFalse(self.ws.find("export-advanced-data").expanded,
                         "the advanced options are folded away")
        self.ws.click("export-save-data")
        saved = self.ws.saved[-1]
        self.assertEqual(saved.name, "synthetic_master_research_n180.xlsx")
        feedback = " ".join(texts(self.ws, "export-feedback-data"))
        self.assertIn(str(saved), feedback)
        self.assertIn("180 rows, 98 variables", feedback)
        from openpyxl import load_workbook

        book = load_workbook(saved, read_only=True)
        self.assertEqual(book.sheetnames, ["Data", "Codebook", "Scales"])
        book.close()
        self.assertEqual(json.loads((self.root / "preferences.json").read_text())["export"]
                         ["formats"]["data"], "xlsx")

    def test_participant_codes_are_flagged_and_nothing_is_uploaded(self):
        self.open_master()
        warning = " ".join(texts(self.ws, "export-sensitive"))
        self.assertIn("participant_code (participant code)", warning)
        self.assertIn(T("export.not_uploaded"), warning)

    def test_the_sav_preview_lists_every_renamed_or_cut_field_before_saving(self):
        self.open_master(adversarial=True)
        self.ws.choose("export-format-data", "sav")
        self.assertIn(T("export.sav.limits"), texts(self.ws, "export-sav-limits"))
        changes = "\n".join(texts(self.ws, "export-sav-changes"))
        book = self.ws.app.pages["data"].export.codebook()
        for original, spss in book.renamed.items():
            self.assertIn(T("export.sav.renamed", name=original, spss=spss), changes)
        self.assertIn(LV_NAME, changes)
        self.assertIn(RU_NAME, changes)
        self.assertNotIn("code_lz", changes, "a text identifier is a string already")
        self.assertIn("rating: the label is cut to 256 bytes", changes)
        self.ws.click("export-save-data")
        self.assertTrue(self.ws.saved[-1].is_file())
        self.assertIn("($FL2)", " ".join(texts(self.ws, "export-feedback-data")))

    def test_csv_separator_and_byte_order_mark_are_offered_and_remembered(self):
        self.open_master()
        self.ws.choose("export-format-data", "csv")
        self.assertTrue(texts(self.ws, "export-csv-note")[0].startswith("A text cell"))
        self.assertEqual(self.ws.find("export-csv-layout").value, "comma")
        self.ws.choose("export-csv-layout", "semicolon")
        self.ws.check("export-csv-bom", False)
        self.ws.click("export-save-data")
        saved = self.ws.saved[-1]
        self.assertFalse(saved.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertIn(";", saved.read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue((saved.parent / (saved.stem + "_codebook.json")).is_file())
        export = json.loads((self.root / "preferences.json").read_text())["export"]
        self.assertEqual((export["csv_layout"], export["csv_bom"]), ("semicolon", False))

    def test_a_save_that_fails_says_why_and_leaves_nothing(self):
        self.open_master()
        missing = self.root / "no such folder" / "data.xlsx"

        async def dialog(title, file_name, extension):
            return str(missing)

        self.ws.app.save_dialog = dialog
        self.ws.click("export-save-data")
        notice = self.ws.find("export-feedback-data")
        self.assertEqual(notice.bgcolor, self.ws.app.ui.p.danger_subtle)
        self.assertIn("no such folder", " ".join(texts(self.ws, "export-feedback-data")))
        self.assertFalse(missing.exists())

    def test_an_spss_file_opens_with_its_labels_and_its_missing_option(self):
        import pyreadstat

        source = self.root / "labelled.sav"
        pyreadstat.write_sav(pd.DataFrame({"q1": [1.0, -9.0, 3.0], "q2": [3.0, 2.0, 1.0]}),
                             str(source), column_labels={"q1": "Fictional item one"},
                             variable_value_labels={"q1": {1: "Never", 3: "Often"}},
                             missing_ranges={"q1": [-9]})
        from types import SimpleNamespace

        # As the Open dialog's result arrives (import_workflow checks the extension).
        picked = [SimpleNamespace(name=source.name, path=str(source))]
        self.assertTrue(self.ws.run(self.ws.app.import_files(picked)))
        self.ws.click("nav-data")
        self.assertEqual(self.ws.find("label-q1").value, "Fictional item one")
        self.assertTrue(pd.isna(self.ws.app.session.df["q1"].iloc[1]))
        option = self.ws.find("data-opt-user-missing")
        self.assertEqual(option.label, T("data.opt.user_missing"))
        self.ws.choose("data-opt-user-missing", "codes")
        self.ws.click("data-reimport")
        self.assertEqual(self.ws.app.session.df["q1"].iloc[1], -9.0)


class LanguageTests(WorkspaceCase):
    def test_the_card_reads_in_latvian_and_russian(self):
        for language in ("lv", "ru"):
            self.ws.app.set_language(language)
            self.open_master()
            for fmt in ("xlsx", "sav", "csv", "bundle"):
                self.ws.choose("export-format-data", fmt)
                shown = texts(self.ws, "export-data") + [self.ws.find("export-save-data").content]
                self.assertFalse([t for t in shown if t and "export." in t], (language, fmt))
                self.assertIn(TABLE[f"export.save.{fmt}"][1 if language == "lv" else 2], shown)
            self.ws.choose("export-format-data", "csv")
            self.assertEqual(self.ws.find("export-csv-layout").value, "semicolon",
                             "Latvian or Russian: semicolon by default")
            (self.root / "preferences.json").unlink(missing_ok=True)
            self.ws.app.pages["data"].export._layout = None


class ResultsAndReportsTests(WorkspaceCase):
    def run_analyses(self):
        from workspace_methods import run_method

        self.open_master()
        session = self.ws.app.session
        for key, roles, options, confirms in SYNTAX_ANALYSES[:3]:
            run = run_method(key, session, roles, options, confirms)
            session.add_result(run, method=key, roles=roles, options=options, confirms=confirms)

    def test_the_results_workbook_for_all_results_or_the_one_on_screen(self):
        self.run_analyses()
        self.ws.click("nav-results")
        self.assertEqual(self.ws.find("export-format-results").value, "results")
        self.assertEqual(self.ws.find("export-save-results").content, T("export.save.results"))
        self.ws.click("export-save-results")
        from openpyxl import load_workbook

        book = load_workbook(self.ws.saved[-1], read_only=True)
        self.assertEqual(len(book.sheetnames), 2 + 3)
        book.close()
        self.ws.choose("export-scope", "selected")
        self.ws.click("export-save-results")
        book = load_workbook(self.ws.saved[-1], read_only=True)
        self.assertEqual(len(book.sheetnames), 2 + 1)
        book.close()
        self.assertIn(T("export.saved_results", path=self.ws.saved[-1], sheets=3),
                      texts(self.ws, "export-feedback-results"))

    def test_the_bundle_from_the_reports_page_holds_the_word_report(self):
        self.run_analyses()
        session = self.ws.app.session
        for entry in session.results:
            session.toggle_report(entry.id)
        self.ws.click("nav-reports")
        self.assertEqual(self.ws.find("export-format-reports").value, "bundle")
        self.assertTrue(self.ws.find("export-bundle-report").value)
        self.ws.click("export-save-reports")
        saved = self.ws.saved[-1]
        with zipfile.ZipFile(saved) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
        self.assertTrue(any(n.startswith("report/") and n.endswith(".docx") for n in names))
        self.assertEqual(len(manifest["analyses"]), 3)
        self.assertEqual(sum(1 for n in names if n.startswith("syntax/")), 3)
        self.assertIn(T("export.saved_bundle", path=saved, files=len(names), rows=180, syntax=3),
                      texts(self.ws, "export-feedback-reports"))

    def test_exporting_the_data_needs_no_report(self):
        generate_master(self.root / "plain")
        self.open_master()
        self.assertFalse(self.ws.app.session.report_order)
        self.ws.choose("export-format-data", "bundle")
        self.ws.click("export-save-data")
        with zipfile.ZipFile(self.ws.saved[-1]) as archive:
            self.assertFalse(any(n.startswith("report/") for n in archive.namelist()))


if __name__ == "__main__":
    unittest.main()
