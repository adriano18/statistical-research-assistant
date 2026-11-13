"""Stage 37 (#67): the flow of the packaged-program journey `export-data`,
through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. This test walks the same flow in the workspace harness
with the journey's own texts and helpers: at each point the text it waits
for and the button it presses (named by its label) are there; the file the
Save dialog gives is written, and the journey's own check (`check_export`:
openpyxl, pyreadstat, pandas, every cell against the fixture as the driver
reads it with the csv module) accepts it. The program cannot show a
disabled button as disabled on Windows (UI Automation reports every button
as enabled), so nothing here relies on one. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

from test_stage368_acceptance import T, create_project_in_ui, label, on_screen, open_csv  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402

THE_EIGHTEEN = [
    "stage36-tasks", "stage36-charts", "stage36-groups", "project-a", "project-b", "import-30",
    "review-120", "responses", "blocked-design", "import-cope-docx", "import-scan-lv",
    "stage36-report", "import-damaged", "psychometrics", "import-resume", "negative-paths",
    "confirmations", "report-composition"]


def save_to(ws, target: Path):
    """The Save dialog of the journey: the file name typed is ``target``."""
    async def dialog(title, file_name, extension):
        ws.saved.append(target)
        return str(target)

    ws.app.save_dialog = dialog


class JourneyOrderTests(unittest.TestCase):
    def test_export_data_follows_the_eighteen_unchanged(self):
        self.assertEqual(list(e2e.JOURNEYS)[:18], THE_EIGHTEEN)
        self.assertEqual(list(e2e.JOURNEYS)[18:], ["export-data"])
        self.assertIs(e2e.JOURNEYS["export-data"], e2e.journey_export_data)
        self.assertNotIn("export-data", e2e.STARTS_ITSELF)


class ExportDataJourneyTests(unittest.TestCase):
    """Journey `export-data`: .xlsx, .sav and .csv from the Data page."""

    def test_the_journey_flow_and_its_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work = root / "work"
            work.mkdir()
            csv_path = e2e.master_fixture(work / "stage37-master")
            source = e2e.master_source(csv_path)
            self.assertEqual((len(source["rows"]), len(source["header"])), (180, 98))
            ws = Workspace(root=root)
            try:
                create_project_in_ui(ws, e2e.EXPORT_PROJECT)
                open_csv(ws, csv_path)
                ws.click("nav-data")
                self.assertTrue(on_screen(ws, T("export.title.data")))
                self.assertEqual(label(ws, "export-save-data"), T("export.save.xlsx"))
                dropdown = ws.find("export-format-data", ft.Dropdown)
                self.assertEqual(dropdown.label, T("export.format"))
                self.assertEqual([o.text for o in dropdown.options], e2e.export_options())
                saved_prefix = T("export.saved", path="", rows="", columns="",
                                 signature="").split(":")[0]
                for kind, name in e2e.EXPORT_FILES:
                    target = work / name
                    if kind != "xlsx":
                        option = T(f"export.format.{kind}")
                        key = next(o.key for o in dropdown.options if o.text == option)
                        ws.choose("export-format-data", key)
                        dropdown = ws.find("export-format-data", ft.Dropdown)
                    if kind == "sav":
                        self.assertTrue(on_screen(ws, T("export.sav.limits")[:60]))
                    self.assertEqual(label(ws, "export-save-data"), T(f"export.save.{kind}"))
                    save_to(ws, target)
                    ws.click("export-save-data")
                    self.assertTrue(on_screen(ws, target.name), "wait_text(target.name)")
                    self.assertTrue(on_screen(ws, saved_prefix))
                    facts = e2e.check_export(target, kind, source)
                    self.assertEqual(facts["rows"], 180)
                    self.assertEqual(facts["cells"], 180 * 98)
                self.assertEqual(e2e.remembered_export(root / "preferences.json"), "csv")
            finally:
                ws.close()
            again = Workspace(root=root)
            try:
                project = next(p for p in again.app.projects.projects()
                               if p.title == e2e.EXPORT_PROJECT)
                again.app.projects.open(project.id)
                again.click("nav-data")
                self.assertEqual(again.find("export-format-data", ft.Dropdown).value, "csv",
                                 "the last format is remembered after a restart")
                self.assertEqual(label(again, "export-save-data"), T("export.save.csv"))
            finally:
                again.close()

    def test_the_journey_check_finds_a_changed_cell(self):
        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            csv_path = e2e.master_fixture(root / "fixture")
            source = e2e.master_source(csv_path)
            ws = Workspace(root=root)
            try:
                open_csv(ws, csv_path)
                ws.click("nav-data")
                target = root / "changed.xlsx"
                save_to(ws, target)
                ws.click("export-save-data")
            finally:
                ws.close()
            e2e.check_export(target, "xlsx", source)
            book = load_workbook(target)
            book["Data"]["C2"] = 99
            book.save(target)
            with self.assertRaises(e2e.StepFailure):
                e2e.check_export(target, "xlsx", source)


if __name__ == "__main__":
    unittest.main()
