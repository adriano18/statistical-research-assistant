"""Stage 36: measured interaction cost of research workflows.

The workflows are driven through the real workspace controls (the test
harness calls the same handlers a click does) and every interaction a
researcher needs is counted. A dropdown choice counts as two interactions
(open, choose). Each test checks that the workflow produced its results.

Before Stage 36 (measured at 36.0, commit b8e123c, recorded in
docs/STAGE36_UX_AUDIT.md): 43 interactions and 16 page changes for eight
correlations; 5 to repeat an analysis; a group comparison by UCLA_Level
refused only after Run; 19 for a Word report from 8 results.
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


LEVELS = {"Code": "id", "Age": "scale", "Sex": "nominal", "UCLA": "scale",
          "UCLA_Level": "ordinal", **{name: "scale" for name in fx.SCALES}}


def prepared_workspace(root=None) -> CountingWorkspace:
    ws = CountingWorkspace(root=root)
    if not ws.app.projects.active:
        ws.app.projects.create("Fictional UX study")
    assert ws.run(ws.app.load_path(str(fx.fixture(fx.CSV))))
    for name, level in LEVELS.items():
        ws.app.session.confirm_level(name, level)
    ws.counts.clear()
    return ws


def eight_correlations(ws: CountingWorkspace) -> None:
    ws.click("nav-analyze")
    ws.click("goal-relate")
    ws.choose("role-x", "UCLA")
    ws.click("role-y-all-scale")                  # every quantitative variable but UCLA
    ws.check("role-y-Age", False)                 # Age is not a coping scale
    ws.click("alt-batch_correlation-spearman")
    ws.click("guided-run")


class Stage36Workflows(unittest.TestCase):
    def test_eight_correlations_in_one_batch(self):
        """Target (spec §4): goal, UCLA, the scales, Run — the researcher
        stays in the task and sees one table of 8 pairs."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        eight_correlations(ws)
        entries = ws.app.session.results
        self.assertEqual([e.method for e in entries], ["batch_correlation"])
        family = entries[0].run.result
        self.assertEqual([row.y for row in family.rows], list(fx.SCALES))
        self.assertEqual(family.method, "spearman")
        self.assertEqual(ws.app.route, "analyze", "the researcher stays in the task")
        self.assertTrue(ws.find_all("task-table"))
        self.assertEqual(ws.total, 8)
        self.assertEqual(ws.routes, ["analyze"])
        print(f"\n[ux] 8 correlations: {ws.total} interactions ({dict(ws.counts)}), "
              f"{len(ws.routes)} page change (before Stage 36: 43 and 16)")

    def test_return_to_the_task_and_run_it_again(self):
        """Target (spec §15): back to the earlier settings in 1–2 actions."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        eight_correlations(ws)
        ws.click("nav-results")
        ws.counts.clear()
        ws.click("nav-analyze")
        ws.click("task-rerun")
        entries = ws.app.session.results
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[1].task_id, entries[0].task_id, "a new run of the same task")
        self.assertEqual(entries[1].run.result.rows, entries[0].run.result.rows,
                         "the same selection, method and options")
        self.assertEqual(ws.total, 2)
        print(f"\n[ux] return and run again: {ws.total} interactions (before: 5)")

    def test_groups_on_the_same_eight_scales(self):
        """The second question reuses the first task's eight scales in one action."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        eight_correlations(ws)
        task = ws.app.session.tasks[0]
        ws.counts.clear()
        ws.click("task-new")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")
        ws.click(f"role-outcome-from-{task.id}")
        self.assertTrue(ws.has_text("fewer than five values"), "small groups explained before Run")
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "batch_groups")
        self.assertEqual([row.outcome for row in entry.run.result.rows], list(fx.SCALES))
        self.assertEqual(len(ws.app.session.tasks), 2)
        self.assertEqual(ws.total, 8)
        print(f"\n[ux] Kruskal–Wallis on the same 8 scales: {ws.total} interactions "
              "(before: refused after Run)")

    def test_a_single_group_comparison_by_a_small_level_variable(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")
        ws.check(f"role-outcome-{fx.SCALES[0]}")
        self.assertTrue(ws.has_text("fewer than five values"), "explained before Run")
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "omnibus")
        self.assertIn("permutation", entry.run.result.p_method)
        self.assertEqual(ws.total, 8)

    def test_tasks_and_results_return_after_a_restart(self):
        """Spec §3/§15: the project, its tasks and their results come back."""
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                eight_correlations(ws)
                project_id = ws.app.projects.info().id
                first = ws.app.session.results[0].run.result
            finally:
                ws.close()
            again = CountingWorkspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                tasks = again.app.session.tasks
                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0].selection["y"], list(fx.SCALES))
                restored = again.app.session.results[0]
                self.assertEqual(restored.task_id, tasks[0].id)
                self.assertEqual(restored.run.result, first, "numbers come back unchanged")
                again.click("nav-analyze")
                again.click(f"task-{tasks[0].id}")
                self.assertEqual(again.app.pages["analyze"].selection["y"], list(fx.SCALES))
                self.assertTrue(again.find_all("task-table"), "the result is shown in the task")
            finally:
                again.close()


if __name__ == "__main__":
    unittest.main()
