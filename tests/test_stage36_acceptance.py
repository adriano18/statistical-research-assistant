"""Stage 36.7: the flows of the new packaged-EXE journeys, through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts
UI Automation exposes. These tests walk the same flows in the workspace
harness and check, at each point, that the text or button name the journey
waits for is really there (a button is named by its label). They do not
replace the EXE journeys; they keep the journeys honest between Windows
runs. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

from docx import Document  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from test_stage36_ux_baseline import prepared_workspace  # noqa: E402
from workspace_text import T as TABLE  # noqa: E402


def T(key: str, **values) -> str:
    text = TABLE[key][0]
    return text.format(**values) if values else text


def label(ws, data_id: str) -> str:
    """The name UI Automation gives a button: its label."""
    content = ws.find(data_id).content
    return content if isinstance(content, str) else getattr(content, "value", "")


def on_screen(ws, fragment: str) -> bool:
    """Like the journeys' wait_text: texts and button names both count."""
    import flet as ft

    names = list(ws.texts())
    names += [c.content for c in ws.controls()
              if isinstance(c, (ft.Button, ft.TextButton)) and isinstance(c.content, str)]
    return any(fragment in name for name in names)


class WordReportJourneyTests(unittest.TestCase):
    """Journey `stage36-report` (spec §14 journey 8, and D5 as a refusal)."""

    def test_two_results_into_one_word_report_and_no_coefficient_from_totals(self):
        from research_report import TEXT as REPORT_TEXT

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        app = ws.app
        # The end of journey stage36-groups: groups created, the batch run.
        ws.click("nav-data")
        ws.choose("groups-source", "UCLA")
        ws.click("groups-create")
        ws.click("groups-use-UCLA_groups")
        for scale in fx.SCALES:
            ws.check(f"role-outcome-{scale}")
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        batch = app.session.results[-1]
        kw_title = T("task.title_compare", group="UCLA_groups", count=8)
        self.assertTrue(ws.has_text(kw_title), "the task the journey clicks by its title")

        # The batch result goes into the report from its task.
        self.assertEqual(label(ws, "task-rerun"), T("task.rerun"))
        self.assertEqual(label(ws, "task-add-report"), T("results.add_report"))
        ws.click("task-add-report")
        self.assertEqual(label(ws, "task-add-report"), T("results.in_report"))

        # A second result: describe UCLA (a new task; it opens in Results).
        self.assertEqual(label(ws, "task-new"), T("task.new"))
        ws.click("task-new")
        self.assertTrue(ws.has_text(T("goal.describe")))
        ws.click("goal-describe")
        options = [o.text for o in ws.find("role-variable").options]
        self.assertEqual(options, e2e.stage36_options_with_groups(),
                         "the journey's keyboard fallback needs this exact list")
        ws.choose("role-variable", "UCLA")
        self.assertTrue(label(ws, "guided-run").startswith(T("rec.run", method="")))
        ws.click("guided-run")
        describe = app.session.results[-1]
        self.assertEqual((describe.method, describe.run.title), ("descriptive", "Descriptive: UCLA"))
        self.assertEqual(app.route, "results")
        self.assertTrue(ws.has_text("Descriptive: UCLA"))
        self.assertEqual(label(ws, "result-add-report"), T("results.add_report"))
        ws.click("result-add-report")
        self.assertEqual(label(ws, "result-add-report"), T("results.in_report"))

        # D5 on the EXE: a scale check on totals offers no coefficient.
        ws.click("nav-analyze")
        ws.click("task-new")
        self.assertTrue(ws.has_text(T("goal.scale")))
        ws.click("goal-scale")
        for scale in fx.SCALES[:3]:
            ws.check(f"role-items-{scale}")
        self.assertTrue(ws.has_text("Only a total score is available now"))
        self.assertFalse(ws.find_all("guided-run"), "no Run button is offered on totals")
        self.assertEqual(len(app.session.results), 2, "nothing was calculated")

        # One Word report from both results.
        ws.click("nav-reports")
        self.assertEqual(label(ws, "reports-export-docx"), T("reports.export_docx"))
        ws.click("reports-export-docx")
        document = Document(str(ws.saved[-1]))
        text = "\n".join(p.text for p in document.paragraphs)
        for table in document.tables:
            for row in table.rows:
                text += "\n" + " ".join(cell.text for cell in row.cells)
        self.assertIn(batch.run.title, text)
        for fragment in e2e.stage36_report_fragments():
            self.assertIn(fragment, text)
        self.assertIn(REPORT_TEXT["en"]["descriptives"], text)


class GroupWordingTests(unittest.TestCase):
    def test_a_comparison_of_three_groups_never_speaks_of_two_groups(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")            # 3 groups (3 / 47 / 5)
        for scale in fx.SCALES:
            ws.check(f"role-outcome-{scale}")
        box = ws.find("design-confirm-independent")
        self.assertEqual(box.label, "I confirm the groups contain independent participants")
        self.assertNotIn("two groups", box.label)
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "batch_groups")
        self.assertIn("I confirm the groups contain independent participants",
                      entry.confirmations)


class DamagedDocumentJourneyTests(unittest.TestCase):
    """Journey `import-damaged` (spec §14 journey 10: damaged documents)."""

    def test_a_damaged_document_is_explained_and_the_review_under_way_is_kept(self):
        from workspace_harness import Workspace

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ws = Workspace(root=root)
            try:
                page = ws.app.pages["import"]
                ws.app.navigate("import")
                generator = fx.generator()
                docx = generator.create_docx_unnumbered(root)
                broken = root / "fictional_broken_scan.pdf"
                broken.write_bytes(e2e.DAMAGED_PDF)
                ws.run(page.open_bytes(docx.read_bytes(), docx.name, path=str(docx)))
                self.assertTrue(ws.has_text(T("imp.read_ok", instruments=2, items=120,
                                              name=docx.name)))
                ws.run(page.open_bytes(broken.read_bytes(), broken.name, path=str(broken)))
                found = page.processing_state()
                state, title = found[0], found[1]
                lines = " ".join(line for _, line in found[2])
                self.assertEqual((state, title), ("error", T("imp.state.error")))
                self.assertTrue(ws.has_text(T("imp.state.error")))
                self.assertIn(f"{broken.name} could not be read", lines)
                self.assertIn(f"The document under review, {docx.name} (120 items), is "
                              "unchanged.", lines)
                for fragment in e2e.damaged_document_fragments(broken.name, docx.name):
                    self.assertTrue(ws.has_text(fragment), fragment)
                # The researcher goes on with the document under review.
                self.assertEqual(label(ws, "imp-instrument-use-1"), T("imp.form.use"))
                ws.click("imp-instrument-use-1")
                self.assertEqual(page.processing_state()[0], "review")
                self.assertTrue(on_screen(ws, T("imp.status.form_of", number=2, total=2)),
                                "review_form waits for this step label")
            finally:
                ws.close()



if __name__ == "__main__":
    unittest.main()
