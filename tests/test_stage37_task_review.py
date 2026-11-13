"""Stage 37.0b: the review inside the batch result card of a task that tests a
hypothesis, and step 4's checks against the plan (design §7.10).

The assumption ticks and the note in the task are the result's own (K2): the
same state as on Results, saved with the project and back after a restart.
Step 4 lists the checks that apply before Run; they never stop a run. A task
without a hypothesis keeps its Stage 36 card. Synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from test_stage36_ux_baseline import CountingWorkspace  # noqa: E402
from test_stage37_ui import H1, Case, run_correlations, title, write_plan  # noqa: E402
from workspace_text import T  # noqa: E402

NOTE = "Fictional: no pair reaches p (Holm) < .05; the intervals are wide."


def texts(ws, data: str) -> str:
    return " ".join(c.value for c in ws.controls(ws.find(data))
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


class TaskReviewTests(Case):
    def test_the_review_in_the_task_is_the_results_review(self):
        ws, hid = self.planned(direction="two-sided")
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        entry = ws.app.session.results[-1]
        self.assertEqual(ws.app.route, "analyze", "the beginner stays in the task")
        self.assertIn(ws.app.t("results.tests", h=1, text=H1),
                      texts(ws, "task-result-hypothesis"))
        boxes = [c for c in ws.find_all("task-review-") if isinstance(c, ft.Checkbox)]
        self.assertEqual([b.label for b in boxes], list(entry.run.evidence().assumptions))
        for box in boxes:
            ws.check(box.data)
        with mock.patch.object(ws.app, "render", wraps=ws.app.render) as render:
            ws.type("task-notes", NOTE)
        self.assertEqual(render.call_count, 0, "typing the note never rebuilds the page")
        self.assertEqual(entry.reviewed, frozenset(entry.run.evidence().assumptions))
        self.assertEqual(entry.note, NOTE)
        ws.app.session.selected_result = entry.id
        ws.app.navigate("results")
        self.assertTrue(all(c.value for c in ws.find_all("review-")
                            if isinstance(c, ft.Checkbox)), "ticked on Results too")
        self.assertEqual(ws.find("result-notes").value, NOTE)
        ws.app.navigate("project")
        self.assertEqual(title(ws), ws.app.t("next.add_report", h=1),
                         "reviewed and interpreted in the task")
        # Saved in the project and back after a restart.
        ws.app.projects.flush()
        root, project_id = ws.root, ws.app.projects.info().id
        ws.app.projects.close(clear=False)
        again = CountingWorkspace(root=root)
        self.addCleanup(again.close)
        again.click(f"project-open-{project_id}")
        restored = again.app.session.results[-1]
        self.assertEqual((restored.note, restored.reviewed), (entry.note, entry.reviewed))
        again.click("nav-analyze")
        again.click(f"task-{again.app.session.tasks[-1].id}")
        self.assertEqual(again.find("task-notes").value, NOTE)
        self.assertTrue(all(c.value for c in again.find_all("task-review-")
                            if isinstance(c, ft.Checkbox)))

    def test_the_interpretation_can_be_skipped_in_the_task(self):
        ws, hid = self.planned(direction="two-sided")
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        self.assertEqual(ws.find("task-skip-notes").content, T["next.skip_note"][0])
        ws.click("task-skip-notes")
        self.assertEqual(ws.app.session.tasks[-1].state["skipped"], ["interpretation"])
        self.assertEqual(ws.find("task-notes-skipped").value, T["task.notes_skipped"][0])

    def test_a_task_without_a_hypothesis_keeps_its_stage_36_card(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-relate")
        run_correlations(ws)
        self.assertTrue(ws.find_all("task-result"))
        self.assertEqual(ws.find_all("task-review-") + ws.find_all("task-notes"), [],
                         "no checkbox is added to an unlinked task (journey confirmations)")


class ResultCardTests(Case):
    def test_the_result_card_names_the_decisions_and_the_open_checks(self):
        """AC-8: a deviation appears on the result card, with Open H1."""
        ws, hid = self.analysed(direction="less")
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click("hyp-1-record-deviation")
        ws.choose("hyp-1-what", "sample")
        ws.type("hyp-1-reason", "Fictional: collection stopped at n = 55.")
        ws.click("hyp-1-save")
        ws.app.session.selected_result = ws.app.session.results[-1].id
        ws.app.navigate("results")
        card = texts(ws, "result-hypothesis")
        self.assertIn(ws.app.t("results.decisions", h=1), card)
        self.assertIn("Fictional: collection stopped at n = 55.", card)
        self.assertIn(ws.app.t("results.open_checks", count=1), card, "H-DIR-TWOSIDED waits")
        self.assertEqual(ws.find("result-hypothesis-open").content,
                         ws.app.t("results.open_hypothesis", h=1))
        ws.click("result-hypothesis-open")
        self.assertEqual((ws.app.route, ws.app.section), ("project", "hypotheses"))
        self.assertIn(hid, ws.app.pages["project"].hypotheses.opened)


class StepFourChecksTests(Case):
    def test_the_checks_before_run_name_direction_method_and_alpha(self):
        ws, hid = self.planned(direction="less")
        ws.app.navigate("project")
        ws.choose("plan-h0-method_key", "batch_correlation")
        ws.choose("plan-h0-variant", "pearson")
        ws.type("plan-h0-alpha", "0.01")
        ws.click("plan-save")
        ws.click("next-create-analysis")
        ws.choose("role-x", "UCLA")
        ws.click("role-y-all-scale")
        ws.check("role-y-Age", False)
        ws.click("alt-batch_correlation-spearman")
        text = texts(ws, "task-checks")
        self.assertIn("reports two-sided p-values only", text)          # H-DIR-TWOSIDED
        self.assertIn("The plan names Pearson’s r; the analysis runs Spearman’s ρ.", text)
        self.assertIn("The plan sets α = 0.01", text)                      # H-ALPHA
        self.assertFalse(ws.find("guided-run").disabled, "checks never stop a run")
        ws.click("guided-run")
        self.assertEqual(len(ws.app.session.results), 1)

    def test_building_the_checks_runs_no_engine(self):
        import workspace_analyze

        ws, hid = self.planned(direction="less")
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        ws.choose("role-x", "UCLA")
        refuse = mock.Mock(side_effect=AssertionError("no engine before Run"))
        with mock.patch.object(workspace_analyze, "run_method", refuse):
            ws.click("role-y-all-scale")
            ws.click("alt-batch_correlation-spearman")
            self.assertTrue(ws.find_all("task-check-"))
        refuse.assert_not_called()

    def test_no_checks_for_an_analysis_without_a_hypothesis(self):
        ws = self.workspace()
        write_plan(ws)
        ws.click("nav-analyze")
        ws.click("goal-relate")
        ws.choose("role-x", "UCLA")
        ws.click("role-y-all-scale")
        self.assertEqual(ws.find_all("task-checks"), [])


if __name__ == "__main__":
    unittest.main()
