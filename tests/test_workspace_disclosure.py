"""Stage 34 UX refinements (part D): progressive disclosure in Guided
Analysis, the primary result first, and a preview of the exported report.
Fictional data only; drives the real controls through the test harness."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from workspace_harness import Workspace  # noqa: E402
from workspace_methods import GOALS  # noqa: E402


def data_order(ws: Workspace, names: list[str]) -> list[str]:
    """The given data names in the order they appear on screen."""
    seen = []
    for control in ws.controls():
        data = getattr(control, "data", None)
        if data in names and data not in seen:
            seen.append(data)
    return seen


class GuidedDisclosureTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)
        self.ws.run(self.ws.app.load_sample("sample_scale.csv"))
        self.ws.app.navigate("analyze")

    def test_the_chosen_question_collapses_to_one_line_and_can_be_changed(self):
        ws = self.ws
        for goal in GOALS:                      # every question is offered at first
            self.assertTrue(ws.find(f"goal-{goal}"))
        ws.click("goal-compare")
        self.assertEqual(ws.find("goal-summary").value, "Compare groups")
        with self.assertRaises(AssertionError):
            ws.find("goal-relate")              # the other questions are folded away
        self.assertTrue(ws.find("step-variables"))
        ws.click("goal-change")
        for goal in GOALS:                      # ... and come back with one click
            self.assertTrue(ws.find(f"goal-{goal}"))
        ws.click("goal-relate")
        self.assertEqual(ws.app.pages["analyze"].goal, "relate")
        self.assertTrue(ws.find("goal-summary"))

    def test_changing_the_view_keeps_the_answers_given_so_far(self):
        ws = self.ws
        ws.click("goal-compare")
        ws.check("role-outcome-stress_q1")
        ws.click("goal-change")
        ws.click("goal-compare")                # the same question again
        # Stage 36: outcomes are a multiple choice (one or more).
        self.assertEqual(ws.app.pages["analyze"].selection.get("outcome"), ["stress_q1"])

    def test_all_methods_and_their_options_stay_available(self):
        ws = self.ws
        ws.click("goal-compare")
        ws.segment("analyze-mode", "all")
        self.assertTrue(ws.find("method-omnibus"))


class PrimaryResultTests(unittest.TestCase):
    def run_groups(self, width: int) -> Workspace:
        ws = Workspace(width)
        self.addCleanup(ws.close)
        ws.run(ws.app.load_sample("sample_scale.csv"))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        ws.run(ws.app.pages["analyze"]._execute(
            "groups", {"outcome": "stress_q1", "group": "group"}, {}, {"independent": True}))
        self.assertEqual(ws.app.route, "results")
        return ws

    def test_the_figure_follows_the_summary_before_estimates_and_tables(self):
        ws = self.run_groups(1440)
        order = data_order(ws, ["result-summary", "result-figure", "result-estimates",
                                "result-table"])
        self.assertEqual(order, ["result-summary", "result-figure", "result-estimates",
                                 "result-table"])
        with self.assertRaises(AssertionError):
            ws.find("result-primary")            # 1440 px: one column

    def test_wide_windows_show_the_summary_and_figure_side_by_side(self):
        ws = self.run_groups(1920)
        row = ws.find("result-primary", ft.Row)
        inside = [getattr(c, "data", None) for c in ws.controls(row)]
        self.assertIn("result-summary", inside)
        self.assertIn("result-figure", inside)


class ReportPreviewTests(unittest.TestCase):
    def test_the_preview_is_exactly_the_exported_text_and_results_open_from_the_report(self):
        ws = Workspace()
        self.addCleanup(ws.close)
        ws.run(ws.app.load_sample("sample_scale.csv"))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        entry = ws.run(ws.app.pages["analyze"]._execute(
            "groups", {"outcome": "stress_q1", "group": "group"}, {}, {"independent": True}))
        ws.click("result-add-report")
        ws.app.navigate("reports")
        ws.type("reports-study-title", "Fictional stress study")
        preview = ws.find("reports-preview-text").value
        self.assertEqual(preview, ws.app.session.combined_report("Fictional stress study"))
        self.assertTrue(preview.startswith("Fictional stress study"))
        ws.click("reports-export")
        self.assertEqual(ws.saved[-1].read_text(encoding="utf-8"), preview)
        ws.click(f"report-open-{entry.id}")
        self.assertEqual(ws.app.route, "results")
        self.assertEqual(ws.app.session.selected_result, entry.id)


if __name__ == "__main__":
    unittest.main()


class ImportViewerTests(unittest.TestCase):
    def test_the_source_page_opens_large_with_zoom_and_page_turning(self):
        import io

        from PIL import Image
        from synthetic_documents import connectedness_text_pdf

        ws = Workspace()
        self.addCleanup(ws.close)
        page = ws.app.pages["import"]
        ws.app.navigate("import")
        ws.run(page.open_bytes(connectedness_text_pdf(), "synthetic_two_versions.pdf"))
        ws.click("imp-enlarge")
        self.assertIsNotNone(ws.page.dialog)
        fit = ws.find("imp-viewer-image")

        def pixels(src) -> int:
            with Image.open(io.BytesIO(src)) as image:
                return image.width

        ws.segment("imp-zoom", "200")
        zoomed = ws.find("imp-viewer-image")
        self.assertGreater(pixels(zoomed.src), pixels(fit.src), "rendered sharper, not stretched")
        self.assertGreater(zoomed.width, fit.width)
        if page.session.page_count > 1:
            ws.click("imp-viewer-next")
            self.assertEqual(page.page_number, 2)
            self.assertEqual(ws.find("imp-viewer-page").value, f"Page 2 of {page.session.page_count}")
        ws.click("imp-viewer-close")
        self.assertIsNone(ws.page.dialog)
        self.assertEqual(page.zoom, "200", "the chosen zoom is kept for the next look")
