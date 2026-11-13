"""Stage 37.0b: the findings of the independent review of 2f9af71
(docs/STAGE37_FABLE_NARROW_REVIEW.md on claude/stage37-review), each written
as a red test before its fix.

* D3  H-DIR-SIGN for a single correlation.
* D4  every task of a hypothesis drives its steps and the next action.
* D5  every result keeps its own specification and title in the report.
* D9  Word reports on A4, with a styled Heading 3.
* D12 a protocol record names the result it was made about (run_id).
* S8  a substantive change of a hypothesis after results needs a reason, is
      recorded, and a check compares each result's snapshot with the plan.
* S14 open checks, acknowledgements and deviations reach the Word report.
* S16 only inferential results make a later hypothesis "added after results".
* S17 the drafted H0 of a *predict* question is about one predictor.
* #8  the report by hypothesis: one block per hypothesis with designation,
      plan version, method, n, estimate with CI, review state and records,
      and no duplicated paragraph.

Synthetic data only.
"""

from __future__ import annotations

from collections import Counter
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from docx import Document  # noqa: E402
from docx.shared import Mm  # noqa: E402

import project_store as ps  # noqa: E402
import report_docx  # noqa: E402
import research_report as rr  # noqa: E402
import research_workflow as rw  # noqa: E402
import stage36_fixtures as fx  # noqa: E402
from test_stage37_ui import (  # noqa: E402
    H1, Case, check_index, check_state, run_correlations, title, write_plan,
)
from workspace_text import T  # noqa: E402

EXAMPLES = ROOT / "examples"


def single_correlation(ws, y: str = "Age") -> None:
    """Relate UCLA with one variable: the guided analysis is a single
    correlation (Pearson's r, confirmed)."""
    ws.choose("role-x", "UCLA")
    ws.check(f"role-y-{y}")
    for box in ws.find_all("design-confirm-"):
        ws.check(box.data)
    ws.click("guided-run")


class D3SingleCorrelationTests(Case):
    def test_a_single_correlation_against_the_predicted_direction_is_disclosed(self):
        ws, hid = self.planned(direction="less")       # UCLA and Age: r = +.020
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        single_correlation(ws)
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "correlation")
        facts = rw.result_facts(entry)
        self.assertEqual(len(facts.estimates), 1, "the coefficient of the single pair")
        self.assertGreater(facts.estimates[0][1], 0)
        self.assertEqual(check_state(ws, "H-DIR-SIGN"), "info")
        message = rw.check_message(next(
            c for c in ws.app.pages["project"].hypotheses._view(hid).checks
            if c.key == "H-DIR-SIGN"), "en")
        self.assertIn("1 of 1 coefficients point against the predicted direction", message)


class D4EveryTaskTests(Case):
    def test_a_second_analysis_of_a_hypothesis_is_reached_by_the_next_action(self):
        ws, hid = self.planned(direction="two-sided")
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        first = ws.app.session.tasks[-1]
        entry = ws.app.session.results[-1]
        for assumption in entry.run.evidence().assumptions:
            ws.app.session.set_reviewed(entry.id, assumption, True)
        ws.app.session.set_note(entry.id, "Fictional note.")
        ws.app.session.toggle_report(entry.id)
        ws.app.navigate("project")
        self.assertEqual(title(ws), T["next.export"][0], "the first analysis is complete")
        # A second analysis of H1 (one pair, as a robustness check), linked in
        # step 1 and run, not yet reviewed.
        ws.click("nav-analyze")
        ws.click("task-new")
        ws.click("goal-relate")
        ws.choose("task-hypothesis", hid)
        single_correlation(ws, "CautiousAction")
        second = ws.app.session.tasks[-1]
        self.assertNotEqual(second.id, first.id)
        self.assertEqual(second.hypothesis_id, hid)
        ws.app.navigate("project")
        view = ws.app.pages["project"].hypotheses._view(hid)
        self.assertEqual([t.id for t in view.tasks], [first.id, second.id])
        self.assertEqual(title(ws), ws.app.t("next.review", h=1),
                         "the second analysis is the next step")
        self.assertEqual({s.key: s.state for s in view.steps}["checks"], "attention",
                         "the row shows the analysis that is not done")
        ws.click("next-review")
        self.assertEqual(ws.app.session.selected_result,
                         ws.app.session.task_results(second.id)[-1].id)


class D5OwnSpecificationTests(Case):
    def test_every_result_keeps_its_own_title_in_the_report(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-relate")
        run_correlations(ws)                           # UCLA with 8 scales
        task = ws.app.session.tasks[-1]
        ws.click("task-change-variables")
        ws.check(f"role-y-{fx.SCALES[0]}", False)
        ws.click("alt-batch_correlation-spearman")
        ws.click("guided-run")                         # UCLA with 7 scales, the same task
        first, second = ws.app.session.task_results(task.id)
        self.assertEqual(len(first.roles["ys"]), 8)
        self.assertEqual(len(second.roles["ys"]), 7)
        self.assertEqual(ws.app.session.task(task.id).title,
                         ws.app.t("task.title_relate", x="UCLA", count=7),
                         "the task is named after what it runs now")
        ws.app.session.toggle_report(first.id)
        ws.app.session.toggle_report(second.id)
        plan = rr.plan_report(ws.app.pages["reports"].report_inputs())
        headings = [i.text for i in plan.section("tests").items if i.kind == "heading"]
        self.assertEqual(headings, [rr.text("en", "task", title=ws.app.t(
            "task.title_relate", x="UCLA", count=n)) for n in (8, 7)])


class D9WordPageTests(unittest.TestCase):
    def test_reports_are_a4_with_a_styled_heading_3(self):
        report = rr.plan_report(rr.ReportInputs(title="Fictional", question="Q?"))
        for document in (report_docx.build_research_docx(report, version="t"),):
            section = document.sections[0]
            self.assertLess(abs(section.page_width - Mm(210)), Mm(1))
            self.assertLess(abs(section.page_height - Mm(297)), Mm(1))
            heading = document.styles["Heading 3"]
            self.assertEqual(heading.font.name, "Times New Roman")
            self.assertTrue(heading.font.bold)
            self.assertTrue(heading.font.italic)
            self.assertEqual(heading.font.size.pt, 12)


class D12RunIdTests(Case):
    def test_a_record_names_the_result_it_was_made_about(self):
        ws, hid = self.analysed()
        entry = ws.app.session.results[-1]
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click(f"hyp-1-check-{check_index(ws, 'H-DIR-TWOSIDED')}-acknowledge")
        ws.type("hyp-1-reason", "Fictional: two-sided p-values are reported.")
        ws.click("hyp-1-save")
        records = ws.app.projects.project.protocol_records(hypothesis_id=hid)
        self.assertEqual([(r["kind"], r["run_id"]) for r in records],
                         [("link", None), ("acknowledgement", entry.record_id)])


class S8PlanChangeTests(Case):
    def test_a_direction_changed_after_results_needs_a_reason_and_is_checked(self):
        ws, hid = self.analysed(direction="less")
        project = ws.app.projects.project
        ws.app.navigate("project")
        ws.choose("plan-h0-direction", "two-sided")
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 1, "nothing saved without a reason")
        self.assertIn(ws.app.t("plan.change_reason_needed", h=1),
                      " ".join(c.value for c in ws.controls(ws.find("plan-feedback"))
                               if hasattr(c, "value") and isinstance(c.value, str)))
        ws.type("plan-h0-reason", "Fictional: the theory predicts no sign.")
        ws.click("plan-save")
        self.assertEqual(project.plan()["version"], 2)
        record = project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual((record["kind"], record["detail"], record["reason"]), (
            "deviation", {"what": "direction", "from": "less", "to": "two-sided"},
            "Fictional: the theory predicts no sign."))
        self.assertEqual(check_state(ws, "H-PLAN-CHANGED"), "recorded",
                         "the result was calculated for plan version 1")

    def test_the_store_refuses_a_silent_change_of_wording_or_alpha(self):
        with TemporaryDirectory() as folder:
            store = ps.ProjectStore(Path(folder))
            info = store.create("Fictional")
            with store.open(info.id) as project:
                project.save_plan({"hypotheses": [{"text": "Group B reports more stress",
                                                   "priority": "primary"}]})
                dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
                import analysis_runs as runs

                frame = project.load_frame(dataset.id)
                run = runs.run_groups(frame, "group", "stress_q1", "mannwhitney", "ordinal",
                                      True, False)
                project.record_run(run, method="groups", dataset_id=dataset.id,
                                   roles={"group": "group", "outcome": "stress_q1"},
                                   options={}, confirms={})
                plan = project.plan()["plan"]
                hid = plan["hypotheses"][0]["id"]
                for change in ({"text": "Group B reports less stress"}, {"alpha": 0.01}):
                    edited = {**plan, "hypotheses": [{**plan["hypotheses"][0], **change}]}
                    with self.subTest(change=change), \
                            self.assertRaises(ps.DesignationReasonNeeded):
                        project.save_plan(edited)
                edited = {**plan, "hypotheses": [{**plan["hypotheses"][0], "alpha": 0.01,
                                                  "text": "Group B reports less stress"}]}
                project.save_plan(edited, reasons={hid: "Fictional reason."})
                details = sorted((r["detail"]["what"], str(r["detail"]["from"]),
                                  str(r["detail"]["to"]))
                                 for r in project.protocol_records(hypothesis_id=hid))
        self.assertEqual(details, [("alpha", "0.05", "0.01"),
                                   ("wording", "Group B reports more stress",
                                    "Group B reports less stress")])

    def test_the_check_compares_a_snapshot_with_the_plan(self):
        h = rw.HypothesisFacts(id="0a1b2c3d4e5f", text="Now", direction="two-sided",
                               alpha=0.05, priority="primary", standing="confirmatory")
        snapshot = {"id": h.id, "plan_version": 1, "priority": "primary", "direction": "less",
                    "alpha": 0.05}
        result = rw.ResultFacts(key="1", method="batch_correlation", snapshot=snapshot)
        analysis = rw.AnalysisFacts(task_id="t1", method="batch_correlation", results=(result,))
        history = ({"version": 1, "priority": "primary", "previous": None, "runs_before": 0,
                    "changed": False, "record": None, "text": "Then", "direction": "less",
                    "alpha": 0.05},
                   {"version": 2, "priority": "primary", "previous": "primary", "runs_before": 1,
                    "changed": False, "record": None, "text": "Now", "direction": "two-sided",
                    "alpha": 0.05})
        found = [c for c in rw.hypothesis_checks(h, (analysis,), history=history)
                 if c.key == "H-PLAN-CHANGED"]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].severity, found[0].state), ("warning", "open"))
        self.assertIn("direction", found[0].facts["changed"])
        self.assertIn("wording", found[0].facts["changed"])
        same = rw.HypothesisFacts(id=h.id, text="Then", direction="less", alpha=0.05)
        self.assertNotIn("H-PLAN-CHANGED", [c.key for c in rw.hypothesis_checks(
            same, (analysis,), history=history[:1])])


class S14ReportRecordsTests(Case):
    def test_open_warnings_acknowledgements_and_deviations_reach_the_word_report(self):
        ws, hid = self.analysed(direction="less")
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click("hyp-1-record-deviation")
        ws.choose("hyp-1-what", "sample")
        ws.type("hyp-1-reason", "Fictional: collection stopped at n = 55.")
        ws.click("hyp-1-save")
        ws.app.session.toggle_report(ws.app.session.results[-1].id)
        ws.run(ws.app.pages["reports"]._export_docx())
        text = "\n".join(p.text for p in Document(str(ws.saved[-1])).paragraphs)
        two_sided = next(c for c in ws.app.pages["project"].hypotheses._view(hid).checks
                         if c.key == "H-DIR-TWOSIDED")
        self.assertEqual(two_sided.state, "open")
        self.assertIn(rw.check_message(two_sided, "en"), text, "an open warning")
        self.assertIn("Deviation from the plan (sample)", text)
        self.assertIn("Fictional: collection stopped at n = 55.", text)
        ws.app.navigate("project")
        ws.click(f"hyp-1-check-{check_index(ws, 'H-DIR-TWOSIDED')}-acknowledge")
        ws.type("hyp-1-reason", "Fictional: reported as two-sided.")
        ws.click("hyp-1-save")
        ws.run(ws.app.pages["reports"]._export_docx())
        text = "\n".join(p.text for p in Document(str(ws.saved[-1])).paragraphs)
        self.assertIn("Acknowledged (a directional hypothesis, two-sided p-values)", text)
        self.assertIn("Reason: Fictional: reported as two-sided.", text)


class S16InferentialResultsTests(unittest.TestCase):
    def planned_after(self, method: str) -> dict:
        with TemporaryDirectory() as folder:
            store = ps.ProjectStore(Path(folder))
            info = store.create("Fictional")
            with store.open(info.id) as project:
                dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
                import analysis_runs as runs

                frame = project.load_frame(dataset.id)
                run = runs.run_groups(frame, "group", "stress_q1", "mannwhitney", "ordinal",
                                      True, False)
                project.record_run(run, method=method, dataset_id=dataset.id,
                                   roles={"group": "group", "outcome": "stress_q1"},
                                   options={}, confirms={})
                project.save_plan({"hypotheses": [{"text": "Group B reports more stress",
                                                   "priority": "primary"}]})
                return next(iter(project.hypothesis_status().values()))

    def test_a_descriptive_or_reliability_result_first_keeps_the_plan_confirmatory(self):
        for method in ("descriptive", "item_diagnostics", "alpha", "omega", "explore"):
            with self.subTest(method=method):
                status = self.planned_after(method)
                self.assertEqual(status["standing"], "confirmatory")
                self.assertEqual((status["inferential_before"], status["runs_before"]), (0, 1))

    def test_an_inferential_result_first_makes_it_added_after_results(self):
        status = self.planned_after("groups")
        self.assertEqual(status["standing"], "added_after_results")
        self.assertEqual(status["inferential_before"], 1)

    def test_the_detail_shows_what_existed_when_the_hypothesis_was_planned(self):
        from test_stage36_ux_baseline import prepared_workspace

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-describe")
        ws.choose("role-variable", "UCLA")
        ws.click("guided-run")
        hid = write_plan(ws)
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        facts = ws.find("hyp-1-standing-facts").value
        self.assertIn("1", facts)
        self.assertEqual(facts, ws.app.t("hyp.standing_facts", version=1, total=1, counted=0))
        self.assertEqual(ws.app.projects.project.hypothesis_status()[hid]["standing"],
                         "confirmatory")


class S17PredictDraftTests(unittest.TestCase):
    def test_the_predict_null_is_about_the_predictor_named_in_h1(self):
        _, key = rw.draft_keys("predict")
        english, latvian, russian = T[key]
        self.assertIn("predictor named in H1", english)
        self.assertIn("held constant", english)
        for text, omnibus in ((english, "every coefficient"), (latvian, "katrs koeficients"),
                              (russian, "каждый коэффициент")):
            self.assertNotIn(omnibus, text, "not the omnibus null")


class ReportByHypothesisTests(Case):
    """Review acceptance test #8, on the synthetic UCLA/SACS data: three
    hypotheses tested by three methods; python-docx reads one block per
    hypothesis and no paragraph twice."""

    PLAN = (("relate", "Loneliness is negatively associated with the coping scales", "less"),
            ("relate", "Loneliness is positively associated with age", "greater"),
            ("predict", "Loneliness predicts cautious action", "two-sided"))

    def test_one_block_per_hypothesis_and_no_duplicated_paragraph(self):
        ws = self.workspace()
        ws.app.navigate("project")
        plan = ws.app.pages["project"].plan
        for index, (kind, text, direction) in enumerate(self.PLAN):
            ws.click("plan-add-question")
            ws.type(f"plan-q{index}-text", f"Fictional question {index + 1}?")
            ws.choose(f"plan-q{index}-type", kind)
            ws.click(f"plan-q{index}-add-hypothesis")
            ws.type(f"plan-h{index}-text", text)
            ws.choose(f"plan-h{index}-direction", direction)
        ws.click("plan-save")
        self.assertEqual(len(plan.draft["hypotheses"]), 3)
        ids = [h["id"] for h in ws.app.projects.project.plan()["plan"]["hypotheses"]]
        page = ws.app.pages["analyze"]
        page.create_for_hypothesis(ids[0])
        run_correlations(ws)
        page.create_for_hypothesis(ids[1])
        single_correlation(ws)
        page.create_for_hypothesis(ids[2])
        ws.choose("role-outcome", "CautiousAction")
        ws.check("role-predictors-UCLA")
        for box in ws.find_all("design-confirm-"):
            ws.check(box.data)
        ws.click("guided-run")
        for entry in ws.app.session.results:
            ws.app.session.set_reviewed(entry.id, entry.run.evidence().assumptions[0], True)
            ws.app.session.toggle_report(entry.id)
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click(f"hyp-1-check-{check_index(ws, 'H-DIR-TWOSIDED')}-acknowledge")
        ws.type("hyp-1-reason", "Fictional: reported as two-sided.")
        ws.click("hyp-1-save")
        ws.run(ws.app.pages["reports"]._export_docx())
        document = Document(str(ws.saved[-1]))
        section, inside = [], False
        for paragraph in document.paragraphs:
            if paragraph.style.name == "Heading 1":
                inside = paragraph.text.endswith(". " + rr.text("en", "hypotheses"))
            elif inside:
                section.append(paragraph.text)
        blocks, current = [], None
        for text in section:
            if re.match(r"^H\d \((primary|secondary|exploratory)\): ", text):
                current = [text]
                blocks.append(current)
            elif current is not None:
                current.append(text)
        self.assertEqual(len(blocks), 3, "one block per hypothesis")
        for number, block in enumerate(blocks, start=1):
            body = "\n".join(block)
            with self.subTest(hypothesis=number):
                self.assertTrue(block[0].startswith(f"H{number} (primary): "), "designation")
                self.assertIn(f"H{number}: direction", body)
                self.assertRegex(body, r"plan version \d")
                self.assertRegex(body, r"H\d tested by “.+”: (Spearman’s ρ|Pearson’s r|Linear "
                                       r"regression)")
                self.assertRegex(body, r"n = \d+")
                self.assertRegex(body, r"= -?\d*\.\d+, 95% CI \[")
                self.assertIn("assumption checks reviewed", body)
                self.assertRegex(body, rf"(Decisions recorded for H{number}:|No decision is "
                                       rf"recorded for H{number}\.)")
        body = [p.text.strip() for p in document.paragraphs
                if p.text.strip() and not p.style.name.startswith(("Heading", "Title"))
                and not re.fullmatch(r"(Table|Figure) \d+", p.text.strip())]
        captions = {document.paragraphs[i + 1].text.strip()
                    for i, p in enumerate(document.paragraphs[:-1])
                    if re.fullmatch(r"(Table|Figure) \d+", p.text.strip())}
        repeated = [text for text, count in Counter(t for t in body if t not in captions).items()
                    if count > 1]
        self.assertEqual(repeated, [], "no paragraph is written twice")


if __name__ == "__main__":
    unittest.main()
