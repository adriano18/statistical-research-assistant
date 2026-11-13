"""Stage 37.0a: the hypothesis workflow in the workspace, through the real handlers.

Every test drives the controls a researcher uses (``workspace_harness``: a
click, a dropdown choice, typing) on synthetic data (tests/fixtures/stage36).
Covered: the next-action bar (the plan-less order kept, the plan rules, no
disabled button, *Why this step?*), the typed plan (questions, the H1 hint
and the drafted H0, the planned analysis, the reason for a changed
priority), *Create the analysis for H1* (linked, Analyze at step 2), the
link in step 1 and its records, the step row, the snapshot on the result
and the *Tests H1* line (also after a restart), the checks with
acknowledgement, deviation and withdrawal, and no re-render while typing.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import research_workflow as rw  # noqa: E402
from test_stage36_ux_baseline import CountingWorkspace, prepared_workspace  # noqa: E402
from workspace_text import T  # noqa: E402

QUESTION = "Is loneliness related to how students cope with stress?"
H1 = "Loneliness is negatively associated with the coping scales"


def title(ws) -> str:
    """The next-action card's title: its first text (as the Stage 34.5 tests read it)."""
    card = ws.find("project-next-action")
    return next(c.value for c in ws.controls(card) if isinstance(c, ft.Text))


def texts(ws, data: str) -> str:
    return " ".join(c.value for c in ws.controls(ws.find(data))
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


def disabled_buttons(ws, data: str) -> list:
    return [c.data for c in ws.controls(ws.find(data))
            if isinstance(c, (ft.Button, ft.TextButton)) and getattr(c, "disabled", False)]


def assert_page_ok(test, ws) -> None:
    test.assertFalse(ws.has_text(ws.app.t("page.failed")), "the page was built without an error")


def write_plan(ws, *, direction: str = "less") -> str:
    """The beginner writes Q1 and H1 in the plan card and saves it; the id of H1."""
    ws.app.navigate("project")
    ws.click("plan-add-question")
    ws.type("plan-q0-text", QUESTION)
    ws.choose("plan-q0-type", "relate")
    ws.click("plan-q0-add-hypothesis")
    ws.type("plan-h0-text", H1)
    ws.choose("plan-h0-direction", direction)
    ws.click("plan-save")
    return ws.app.projects.project.plan()["plan"]["hypotheses"][0]["id"]


def run_correlations(ws, method: str = "spearman") -> None:
    """The variables, the method and Run in the task on screen (Analyze at step 2)."""
    ws.choose("role-x", "UCLA")
    ws.click("role-y-all-scale")
    ws.check("role-y-Age", False)
    ws.click(f"alt-batch_correlation-{method}")
    if method == "pearson":
        ws.check("design-confirm-pearson")
    ws.click("guided-run")


def check_index(ws, key: str, number: int = 1) -> int:
    view = ws.app.pages["project"].hypotheses._view(
        ws.app.projects.project.plan()["plan"]["hypotheses"][number - 1]["id"])
    return next(i for i, c in enumerate(view.checks) if c.key == key)


def check_state(ws, key: str, number: int = 1) -> str:
    ws.app.navigate("project")
    view = ws.app.pages["project"].hypotheses._view(
        ws.app.projects.project.plan()["plan"]["hypotheses"][number - 1]["id"])
    return next(c.state for c in view.checks if c.key == key)


class Case(unittest.TestCase):
    def workspace(self, root=None) -> CountingWorkspace:
        ws = prepared_workspace(root)
        self.addCleanup(ws.close)
        return ws

    def planned(self, **kwargs):
        ws = self.workspace()
        return ws, write_plan(ws, **kwargs)

    def analysed(self, **kwargs):
        ws, hid = self.planned(**kwargs)
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        return ws, hid


class NextActionBarTests(Case):
    def test_without_a_plan_the_stage_34_card_stays_with_one_more_way_in(self):
        ws = CountingWorkspace()
        self.addCleanup(ws.close)
        ws.app.projects.create("Fictional journey")
        ws.app.navigate("project")
        self.assertEqual(title(ws), T["next.add_data"][0])
        for data in ("next-open-data", "next-sample", "next-questionnaire", "next-question"):
            self.assertTrue(ws.find(data), data)
        self.assertEqual(disabled_buttons(ws, "project-next-action"), [])
        ws.click("next-sample")
        self.assertEqual(ws.app.route, "data", "the button does what it names")

    def test_start_with_the_question_puts_the_projects_question_in_the_plan(self):
        ws = self.workspace()
        ws.app.projects.set_research_question(QUESTION)
        ws.app.navigate("project")
        self.assertEqual(title(ws), T["next.analyze"][0])
        ws.click("next-question")
        draft = ws.app.pages["project"].plan.draft
        self.assertEqual([q["text"] for q in draft["questions"]], [QUESTION])
        self.assertEqual(ws.find("plan-q0-text").value, QUESTION)
        # N1: the kind is missing; the card says so and offers no button to press.
        self.assertEqual(title(ws), ws.app.t("next.question", q=1))
        self.assertEqual([c for c in ws.controls(ws.find("project-next-action"))
                          if isinstance(c, ft.Button)], [])
        ws.click("next-why")
        self.assertIn(ws.app.t("next.why.question", q=1), texts(ws, "next-why-list"))

    def test_the_plan_comes_first_once_it_is_started(self):
        ws = self.workspace()
        ws.app.navigate("project")
        ws.click("plan-add-question")
        ws.type("plan-q0-text", QUESTION)
        ws.choose("plan-q0-type", "relate")
        self.assertEqual(title(ws), ws.app.t("next.add_hypothesis", q=1))
        ws.click("next-add-hypothesis")
        hypothesis = ws.app.pages["project"].plan.draft["hypotheses"][0]
        self.assertEqual((hypothesis["direction"], hypothesis["priority"], hypothesis["alpha"]),
                         ("two-sided", "primary", 0.05), "the defaults")
        self.assertEqual(hypothesis["h0"], T["hyp.draft.h0.relate"][0], "H0 is drafted")
        self.assertEqual(ws.find("plan-h0-text").hint_text, T["hyp.draft.h1.relate"][0])
        self.assertEqual(ws.find("plan-h0-text").value, "", "H1 is a hint, never prefilled")
        self.assertEqual(title(ws), ws.app.t("next.write_hypothesis", h=1))
        ws.type("plan-h0-text", H1)
        ws.app.navigate("project")
        self.assertEqual(title(ws), T["next.save_plan"][0])
        ws.click("next-save-plan")
        self.assertEqual(ws.app.projects.project.plan()["version"], 1)
        self.assertEqual(title(ws), ws.app.t("next.create_analysis", h=1))
        self.assertEqual(disabled_buttons(ws, "project-next-action"), [])

    def test_after_the_export_the_card_says_the_report_is_done(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-relate")
        run_correlations(ws)
        ws.app.session.toggle_report(ws.app.session.results[-1].id)
        ws.app.navigate("project")
        self.assertEqual(title(ws), T["next.export"][0])
        ws.run(ws.app.pages["reports"]._export_docx())
        self.assertTrue(ws.saved and ws.saved[-1].exists())
        exported = ws.app.projects.project.last_report_export()
        self.assertEqual(exported["runs"], [ws.app.session.results[-1].record_id])
        ws.app.navigate("project")
        self.assertEqual(title(ws), T["next.done"][0])
        ws.click("next-report")
        self.assertEqual(ws.app.route, "reports")


class HypothesisWorkflowTests(Case):
    def test_create_the_analysis_for_h1_links_it_and_opens_the_variables(self):
        ws, hid = self.planned()
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        self.assertEqual((ws.app.route, ws.app.section), ("analyze", "variables"))
        task = ws.app.session.tasks[-1]
        self.assertEqual((task.goal, task.hypothesis_id), ("relate", hid))
        self.assertEqual(ws.find("task-hypothesis").value, hid)
        self.assertIn("H1 · ", texts(ws, f"task-{task.id}"))
        self.assertIn(ws.app.t("steps.state.done"), texts(ws, "task-steps-hypothesis"))
        self.assertIn(ws.app.t("steps.state.current"), texts(ws, "task-steps-variables"))
        records = ws.app.projects.project.protocol_records(hypothesis_id=hid)
        self.assertEqual([(r["kind"], r["task_id"], r["detail"]) for r in records],
                         [("link", task.id, {"from": None, "to": hid})])

    def test_the_result_keeps_the_hypothesis_and_says_so_after_a_restart(self):
        ws, hid = self.analysed()
        entry = ws.app.session.results[-1]
        snapshot = entry.provenance["hypothesis"]
        self.assertEqual((snapshot["id"], snapshot["plan_version"], snapshot["direction"],
                          snapshot["standing"]), (hid, 1, "less", "confirmatory"))
        self.assertEqual(ws.app.session.tasks[-1].title,
                         ws.app.t("task.title_relate", x="UCLA", count=8),
                         "named after the analysis at its first run")
        ws.app.session.selected_result = entry.id
        ws.app.navigate("results")
        self.assertIn(ws.app.t("results.tests", h=1, text=H1), texts(ws, "result-hypothesis"))
        ws.app.navigate("project")
        view = ws.app.pages["project"].hypotheses._view(hid)
        before = (view.steps, [(c.key, c.state, c.fingerprint) for c in view.checks])
        root, project_id = ws.root, ws.app.projects.info().id
        ws.app.projects.close(clear=False)
        again = CountingWorkspace(root=root)
        self.addCleanup(again.close)
        again.click(f"project-open-{project_id}")
        restored = again.app.session.results[-1]
        self.assertEqual(restored.provenance["hypothesis"], snapshot)
        self.assertEqual(again.app.session.tasks[-1].hypothesis_id, hid, "the link is kept")
        view = again.app.pages["project"].hypotheses._view(hid)
        self.assertEqual((view.steps, [(c.key, c.state, c.fingerprint) for c in view.checks]),
                         before, "the same steps and checks after the restart")
        again.app.session.selected_result = restored.id
        again.app.navigate("results")
        self.assertIn(again.app.t("results.tests", h=1, text=H1),
                      texts(again, "result-hypothesis"))

    def test_checks_are_decided_with_a_reason_and_withdrawn(self):
        ws, hid = self.analysed()
        ws.app.navigate("project")
        self.assertEqual(title(ws), ws.app.t("next.decide", h=1))
        ws.click("next-show-check")
        self.assertIn(hid, ws.app.pages["project"].hypotheses.opened)
        index = check_index(ws, "H-DIR-TWOSIDED")
        self.assertIn("two-sided", texts(ws, f"hyp-1-check-{index}-text"))
        ws.click(f"hyp-1-check-{index}-acknowledge")
        ws.click("hyp-1-save")                       # no reason: nothing is written
        self.assertEqual(texts(ws, "hyp-1-message"), ws.app.t("hyp.reason_first"))
        project = ws.app.projects.project
        self.assertEqual([r["kind"] for r in project.protocol_records(hypothesis_id=hid)],
                         ["link"])
        self.assertEqual(disabled_buttons(ws, "project-hypotheses"), [])
        ws.type("hyp-1-reason", "Reported as two-sided tests; the direction is described.")
        ws.click("hyp-1-save")
        ack = project.protocol_records(hypothesis_id=hid)[-1]
        view = ws.app.pages["project"].hypotheses._view(hid)
        check = next(c for c in view.checks if c.key == "H-DIR-TWOSIDED")
        self.assertEqual((ack["kind"], ack["check_key"], ack["fingerprint"], check.state),
                         ("acknowledgement", "H-DIR-TWOSIDED", check.fingerprint, "acknowledged"))
        self.assertIn("Reported as two-sided", texts(ws, f"hyp-1-check-{index}-state"))
        # Withdraw the acknowledgement (a reason again): the check is open again.
        record = next(i for i, r in enumerate(project.protocol_records(hypothesis_id=hid))
                      if r["id"] == ack["id"])
        ws.click(f"hyp-1-record-{record}-withdraw")
        ws.type("hyp-1-reason", "Recorded for the wrong analysis.")
        ws.click("hyp-1-save")
        kinds = [r["kind"] for r in project.protocol_records(hypothesis_id=hid)]
        self.assertEqual(kinds, ["link", "acknowledgement", "withdrawal"])
        self.assertEqual(check_state(ws, "H-DIR-TWOSIDED"), "open")
        self.assertIn(ws.app.t("hyp.record.withdrawn"), texts(ws, f"hyp-1-record-{record}"))

    def test_an_acknowledgement_reopens_when_the_analysis_changes(self):
        ws, hid = self.analysed()
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click(f"hyp-1-check-{check_index(ws, 'H-DIR-TWOSIDED')}-acknowledge")
        ws.type("hyp-1-reason", "Two-sided, as reported.")
        ws.click("hyp-1-save")
        self.assertEqual(check_state(ws, "H-DIR-TWOSIDED"), "acknowledged")
        task = ws.app.session.tasks[-1]
        ws.click("nav-analyze")
        ws.click(f"task-{task.id}")
        ws.click("alt-batch_correlation-pearson")
        ws.check("design-confirm-pearson")
        ws.click("guided-run")
        self.assertEqual(ws.app.session.results[-1].options["method"], "pearson")
        self.assertEqual(check_state(ws, "H-DIR-TWOSIDED"), "open",
                         "acknowledged for Spearman's ρ, not for Pearson's r")
        self.assertEqual(check_state(ws, "H-SPEC-CHANGED"), "open")

    def test_open_checks_block_neither_a_run_nor_an_export(self):
        ws, hid = self.analysed()
        ws.app.navigate("project")
        self.assertIn("H-DIR-TWOSIDED", [c.key for c in rw.open_checks(
            ws.app.pages["project"].hypotheses._view(hid).checks)])
        ws.click("nav-analyze")
        ws.click(f"task-{ws.app.session.tasks[-1].id}")
        ws.click("task-rerun")
        self.assertEqual(len(ws.app.session.results), 2, "Run again with open checks")
        ws.click("task-add-report")
        ws.run(ws.app.pages["reports"]._export_docx())
        self.assertTrue(ws.saved and ws.saved[-1].exists(), "exported with open checks")

    def test_building_the_checks_runs_no_engine_and_opens_no_connection(self):
        import socket

        import workspace_analyze
        import workspace_methods

        ws, hid = self.analysed()
        ws.app.pages["project"].hypotheses.opened.add(hid)
        refuse = mock.Mock(side_effect=AssertionError("not while checking"))
        with mock.patch.object(workspace_methods, "run_method", refuse), \
                mock.patch.object(workspace_analyze, "run_method", refuse), \
                mock.patch.object(socket.socket, "connect", refuse):
            ws.app.navigate("project")
            assert_page_ok(self, ws)
            self.assertTrue(ws.find_all("hyp-1-check-"))
        refuse.assert_not_called()

    def test_a_free_deviation_is_recorded_with_what_and_why(self):
        ws, hid = self.analysed()
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click("hyp-1-record-deviation")
        ws.choose("hyp-1-what", "exclusions")
        ws.type("hyp-1-reason", "Two fictional respondents left the study.")
        ws.click("hyp-1-save")
        record = ws.app.projects.project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual((record["kind"], record["detail"], record["results_of_hypothesis"]),
                         ("deviation", {"what": "exclusions"}, 1))
        self.assertIn(T["hyp.what.exclusions"][0], texts(ws, "project-hypotheses"))

    def test_the_next_action_walks_through_the_steps_of_h1(self):
        ws, hid = self.analysed(direction="two-sided")
        ws.app.navigate("project")
        # Two-sided: nothing to decide; the assumptions are not reviewed yet.
        self.assertEqual(title(ws), ws.app.t("next.review", h=1))
        ws.click("next-review")
        self.assertEqual(ws.app.route, "results")
        for control in ws.find_all("review-"):
            ws.check(control.data)
        ws.app.navigate("project")
        self.assertEqual(title(ws), ws.app.t("next.note", h=1))
        ws.click("next-skip-note")
        self.assertEqual(ws.app.session.tasks[-1].state["skipped"], ["interpretation"])
        self.assertEqual(title(ws), ws.app.t("next.add_report", h=1))
        ws.click("next-add-report")
        self.assertTrue(ws.app.session.results[-1].in_report)
        self.assertEqual(title(ws), T["next.export"][0])
        view = ws.app.pages["project"].hypotheses._view(hid)
        self.assertEqual(rw.steps_complete(view.steps), 8)
        self.assertIn(ws.app.t("steps.count", done=8, total=8), texts(ws, "hyp-1-steps"))


class AnalyzeLinkTests(Case):
    def test_the_link_is_chosen_in_step_one_and_every_change_is_recorded(self):
        ws, hid = self.planned(direction="two-sided")
        ws.click("nav-analyze")
        ws.click("goal-relate")
        ws.choose("task-hypothesis", hid)           # before the task exists
        self.assertEqual(ws.app.pages["analyze"].pending_hypothesis, hid)
        run_correlations(ws)
        task = ws.app.session.tasks[-1]
        self.assertEqual(task.hypothesis_id, hid)
        self.assertIsNotNone(ws.app.session.results[-1].provenance.get("hypothesis"))
        ws.choose("task-hypothesis", "")             # unlink
        self.assertIsNone(ws.app.session.task(task.id).hypothesis_id)
        details = [r["detail"] for r in ws.app.projects.project.protocol_records(hypothesis_id=hid)]
        self.assertEqual(details, [{"from": None, "to": hid}, {"from": hid, "to": None}])
        ws.choose("task-hypothesis", hid)            # linked again, after the result
        ws.app.navigate("project")
        view = ws.app.pages["project"].hypotheses._view(hid)
        self.assertNotIn("H-LINKED-LATE", [c.key for c in view.checks],
                         "the result was calculated as a test of H1")

    def test_a_result_linked_after_it_was_calculated_says_so(self):
        ws, hid = self.planned(direction="two-sided")
        ws.click("nav-analyze")
        ws.click("goal-relate")
        run_correlations(ws)                         # not linked
        self.assertIsNone(ws.app.session.results[-1].provenance.get("hypothesis"))
        ws.choose("task-hypothesis", hid)
        ws.app.session.selected_result = ws.app.session.results[-1].id
        ws.app.navigate("results")
        self.assertIn(ws.app.t("results.linked_late", h=1), texts(ws, "result-hypothesis"))
        self.assertEqual(check_state(ws, "H-LINKED-LATE"), "info")

    def test_the_step_row_follows_the_analysis_on_screen(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-relate")
        self.assertIn(ws.app.t("steps.state.skipped"), texts(ws, "task-steps-hypothesis"))
        self.assertIn(ws.app.t("steps.state.current"), texts(ws, "task-steps-variables"))
        ws.choose("role-x", "UCLA")
        ws.click("role-y-all-scale")
        self.assertIn(ws.app.t("steps.state.done"), texts(ws, "task-steps-variables"))
        # Pearson's r is recommended and asks for a confirmation (K1): the design is next.
        self.assertTrue(ws.find_all("design-confirm-pearson"))
        self.assertIn(ws.app.t("steps.state.current"), texts(ws, "task-steps-design"))
        ws.click("alt-batch_correlation-spearman")
        self.assertIn(ws.app.t("steps.state.done"), texts(ws, "task-steps-design"))
        self.assertIn(ws.app.t("steps.state.current"), texts(ws, "task-steps-result"))


class PlanEditorTests(Case):
    def test_typing_never_rebuilds_the_page(self):
        ws, hid = self.analysed()
        ws.app.navigate("project")
        ws.click("plan-add-question")
        ws.choose("plan-h0-priority", "secondary")   # after results: a reason is asked for
        ws.click("hyp-1-toggle")
        ws.click("hyp-1-record-deviation")
        with mock.patch.object(ws.app, "render", wraps=ws.app.render) as render:
            ws.type("plan-objectives", "Fictional aims")
            ws.type("plan-q1-text", "A second fictional question")
            ws.type("plan-h0-text", H1 + ", in each scale")
            ws.type("plan-h0-h0", "No association")
            ws.type("plan-h0-alpha", "0.01")
            ws.type("plan-h0-reason", "The fictional supervisor asked for it.")
            ws.type("hyp-1-reason", "A fictional reason")
        self.assertEqual(render.call_count, 0, "typing changes only the draft")
        self.assertEqual(ws.app.pages["project"].plan.reasons[hid],
                         "The fictional supervisor asked for it.")

    def test_a_priority_changed_after_results_needs_a_reason(self):
        ws, hid = self.analysed()
        ws.app.navigate("project")
        project = ws.app.projects.project
        ws.choose("plan-h0-priority", "secondary")
        ws.click("plan-save")
        self.assertEqual(texts(ws, "plan-feedback"), ws.app.t("plan.reason_needed", h=1))
        self.assertEqual(project.plan()["version"], 1, "nothing was saved")
        self.assertEqual(disabled_buttons(ws, "project-plan"), [])
        ws.type("plan-h0-reason", "Fictional: the groups turned out very unequal.")
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 2)
        record = project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual((record["kind"], record["detail"], record["plan_version"]),
                         ("designation", {"from": "primary", "to": "secondary"}, 2))
        ws.click("hyp-1-toggle")
        index = check_index(ws, "H-DESIGNATION-CHANGED")
        self.assertIn("unequal", texts(ws, f"hyp-1-check-{index}-text"))
        self.assertIn(ws.app.t("hyp.history"), texts(ws, "project-hypotheses"))

    def test_the_planned_analysis_is_compared_with_the_one_run(self):
        ws, hid = self.planned()
        ws.app.navigate("project")
        ws.choose("plan-h0-method_key", "batch_correlation")
        ws.choose("plan-h0-variant", "pearson")
        ws.click("plan-save")
        saved = ws.app.projects.project.plan()["plan"]
        self.assertEqual(saved["plan_format"], 2)
        self.assertEqual((saved["hypotheses"][0]["method_key"],
                          saved["hypotheses"][0]["method_options"]),
                         ("batch_correlation", {"method": "pearson"}))
        ws.click("next-create-analysis")
        run_correlations(ws)                         # Spearman, not Pearson
        self.assertEqual(check_state(ws, "H-METHOD-DIFFERS"), "open")
        ws.click("hyp-1-toggle")
        index = check_index(ws, "H-METHOD-DIFFERS")
        self.assertIn("Pearson", texts(ws, f"hyp-1-check-{index}-text"))
        ws.click(f"hyp-1-check-{index}-deviation")
        ws.type("hyp-1-reason", "Fictional: the scales were skewed, so Spearman's ρ.")
        ws.click("hyp-1-save")
        self.assertEqual(check_state(ws, "H-METHOD-DIFFERS"), "recorded")
        record = ws.app.projects.project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual((record["kind"], record["detail"]), ("deviation", {"what": "method"}))


class StepIsolationTests(Case):
    def test_a_result_of_another_task_does_not_tick_this_tasks_steps(self):
        ws, hid = self.planned(direction="two-sided")
        ws.app.navigate("project")
        ws.click("next-create-analysis")            # H1's task, not run
        h1_task = ws.app.session.tasks[-1]
        ws.click("task-new")
        ws.click("goal-relate")
        run_correlations(ws)                         # another task, not linked
        self.assertEqual(len(ws.app.session.tasks), 2)
        ws.app.navigate("project")
        view = ws.app.pages["project"].hypotheses._view(hid)
        self.assertEqual([t.id for t in view.tasks], [h1_task.id])
        states = {s.key: s.state for s in view.steps}
        self.assertEqual((states["variables"], states["result"], states["checks"]),
                         ("current", "todo", "todo"), "the other task's result counts nowhere")
        self.assertEqual(title(ws), ws.app.t("next.run_analysis", h=1))


class AiContextTests(Case):
    def test_the_ai_plan_preview_keeps_the_stage_36_fields(self):
        """AC-12: typed questions, the planned analysis and the protocol records
        are not added to what the AI is sent about the plan."""
        import ai_context

        ws, hid = self.analysed()
        ws.app.navigate("project")
        ws.choose("plan-h0-method_key", "batch_correlation")
        ws.click("plan-save")
        project = ws.app.projects.project
        project.add_protocol_record("deviation", hypothesis_id=hid, detail={"what": "other"},
                                    reason="A fictional deviation")
        text = ai_context.preview("plan", project=project)
        self.assertIn("Hypothesis 1 (primary, less, alpha 0.05", text)
        for leak in (QUESTION, "batch_correlation", "question_id", "plan_format",
                     "A fictional deviation", hid):
            self.assertNotIn(leak, text)


class LanguageTests(Case):
    def test_the_hypothesis_workspace_reads_in_every_language(self):
        ws, hid = self.analysed()
        bare = re.compile(r"\b(hyp|check|next|steps|plan|task|results)\.[a-z_]+")
        for language in ("en", "lv", "ru"):
            with self.subTest(language=language):
                ws.app.session.language = language
                ws.app.pages["project"].hypotheses.opened.add(hid)
                ws.app.navigate("project")
                assert_page_ok(self, ws)
                ws.click("next-why")
                for text in ws.texts():
                    self.assertNotRegex(text, bare, text)
                ws.app.pages["project"].hypotheses.show_why = False
                ws.app.navigate("analyze")
                assert_page_ok(self, ws)
                ws.app.navigate("results")
                assert_page_ok(self, ws)


if __name__ == "__main__":
    unittest.main()
