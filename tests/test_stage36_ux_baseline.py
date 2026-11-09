"""Stage 36.0: measured interaction cost of research workflows (UX baseline).

The workflows are driven through the real workspace controls (the test
harness calls the same handlers a click does) and every interaction a
researcher needs is counted. A dropdown choice counts as two interactions
(open, choose). The numbers are recorded in docs/STAGE36_UX_AUDIT.md;
later Stage 36 changes add the improved workflows next to these, so the
before/after comparison stays measured, not estimated.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import stage36_fixtures as fx  # noqa: E402
from workspace_harness import Workspace  # noqa: E402


class CountingWorkspace(Workspace):
    """The workspace harness, counting what a researcher does."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counts: Counter = Counter()
        self.routes: list[str] = []

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def click(self, data: str):
        self.counts["click"] += 1
        before = self.app.route
        result = super().click(data)
        if self.app.route != before:
            self.routes.append(self.app.route)
        return result

    def choose(self, data: str, value):
        self.counts["choose"] += 2          # open the list, pick the entry
        return super().choose(data, value)

    def check(self, data: str, value: bool = True):
        self.counts["check"] += 1
        return super().check(data, value)


def prepared_workspace() -> CountingWorkspace:
    ws = CountingWorkspace()
    ws.app.projects.create("Fictional UX baseline")
    assert ws.run(ws.app.load_path(str(fx.fixture(fx.CSV))))
    levels = {"Code": "id", "Age": "scale", "Sex": "nominal", "UCLA": "scale",
              "UCLA_Level": "ordinal", **{name: "scale" for name in fx.SCALES}}
    for name, level in levels.items():
        ws.app.session.confirm_level(name, level)
    ws.counts.clear()
    return ws


class BaselineWorkflows(unittest.TestCase):
    """Stage 34.5/35 workflows as they are before Stage 36 (measured)."""

    def test_eight_spearman_correlations_one_pair_at_a_time(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        before = len(ws.app.session.results)
        ws.click("nav-analyze")
        ws.click("goal-relate")
        ws.choose("role-x", "UCLA")
        for index, scale in enumerate(fx.SCALES):
            if index:
                ws.click("nav-analyze")          # the run leaves the analysis page
            ws.choose("role-y", scale)
            ws.click("alt-correlation-spearman")  # a new choice resets the method
            ws.click("guided-run")
        self.assertEqual(len(ws.app.session.results) - before, 8, "eight results")
        self.assertEqual(ws.total, 43)
        self.assertEqual(len(ws.routes), 16, "page changes: analysis and results, 8 times")
        print(f"\n[ux-baseline] 8 correlations: {ws.total} interactions "
              f"({dict(ws.counts)}), {len(ws.routes)} page changes; "
              "no shared table, no multiple-comparison correction")

    def test_repeat_an_analysis_with_another_variable(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-relate")
        ws.choose("role-x", "UCLA")
        ws.choose("role-y", fx.SCALES[0])
        ws.click("alt-correlation-spearman")
        ws.click("guided-run")
        ws.counts.clear()
        ws.routes.clear()
        ws.click("nav-analyze")
        ws.choose("role-y", fx.SCALES[1])
        ws.click("alt-correlation-spearman")
        ws.click("guided-run")
        self.assertEqual(ws.total, 5)
        print(f"\n[ux-baseline] repeat with another variable: {ws.total} interactions")

    def test_group_comparison_by_an_existing_level_variable_is_refused_after_run(self):
        """UCLA_Level has groups of 3, 47 and 5: every omnibus method needs
        five per group, and the researcher learns it only after Run."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        before = len(ws.app.session.results)
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")
        ws.choose("role-outcome", fx.SCALES[0])
        self.assertFalse(ws.find_all("design-blockers"), "nothing is said before the run")
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        page = ws.app.pages["analyze"]
        self.assertEqual(len(ws.app.session.results), before)
        self.assertIn("At least five complete observations per group", page.message[0])
        self.assertEqual(ws.total, 9)
        print(f"\n[ux-baseline] group comparison by UCLA_Level: refused after Run, "
              f"{ws.total} interactions spent; 8 scales would need 8 such attempts")

    def test_a_word_report_from_eight_results(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        page = ws.app.pages["analyze"]
        for scale in fx.SCALES:
            ws.run(page._execute("correlation", {"x": "UCLA", "y": scale},
                                 {"method": "spearman"}, {}))
        ws.counts.clear()
        ws.click("nav-results")
        for entry in ws.app.session.results:
            ws.click(f"result-{entry.id}")
            ws.click("result-add-report")
        ws.click("nav-reports")
        ws.click("reports-export-docx")
        self.assertTrue(any(path.suffix == ".docx" for path in ws.saved))
        self.assertEqual(ws.total, 19)
        print(f"\n[ux-baseline] Word report from 8 results: {ws.total} interactions "
              "(plus the Save dialog)")


if __name__ == "__main__":
    unittest.main()
