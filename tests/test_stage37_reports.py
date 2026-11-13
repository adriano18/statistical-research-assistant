"""Stage 37.0b: the hypothesis rows of the Word research report (design §7.10,
AC-3, AC-8, AC-15).

For every hypothesis the Hypotheses section names its designation, direction
and α; the analyses that test it (task, method, number of tests, correction),
whether each result is current and in the report, its review (assumption
ticks, note); the decisions recorded with their reasons (deviations,
acknowledgements, justifications, designation changes after results and their
withdrawals); and the checks that are open. The editable table *Hypotheses and
evidence* has one row per hypothesis and result. Numbers come only from saved
engine output and the researcher's records; nothing says that a hypothesis is
supported or confirmed. Synthetic data only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from docx import Document  # noqa: E402

import report_docx  # noqa: E402
import research_report as rr  # noqa: E402
import research_workflow as rw  # noqa: E402
from test_stage37_ui import (  # noqa: E402
    H1, Case, check_index, run_correlations, write_plan,
)

# Words a report must never use about a hypothesis (EN, LV, RU stems).
VERDICTS = {"en": re.compile(r"\b(support|confirmed|proven|proves)", re.I),
            "lv": re.compile(r"(apstiprināt|apstiprin[aā]j|pierādīt)", re.I),
            "ru": re.compile(r"(подтвержд|подтвердил|доказан|поддерж)", re.I)}
ACK_REASON = "Fictional: two-sided p-values are reported; each sign is compared."
DEVIATION_REASON = "Fictional: the scales were skewed, so Spearman's ρ."
DESIGNATION_REASON = "Fictional: the supervisor asked for a secondary hypothesis."


def ack(record_id="r1", **fields):
    return {"id": record_id, "kind": "acknowledgement", "at": "2026-01-02T03:04:00+00:00",
            "check_key": "H-DIR-TWOSIDED", "reason": ACK_REASON, "results_of_hypothesis": 1,
            "detail": {}, **fields}


def deviation(record_id="r2", **fields):
    return {"id": record_id, "kind": "deviation", "at": "2026-01-02T03:05:00+00:00",
            "check_key": "H-METHOD-DIFFERS", "reason": DEVIATION_REASON,
            "results_of_hypothesis": 0, "detail": {
                "what": "method",
                "planned": {"method": "batch_correlation", "options": {"method": "pearson"}},
                "actual": {"method": "batch_correlation", "options": {"method": "spearman"}}},
            **fields}


def evidence(**fields) -> rr.HypothesisEvidence:
    analysis = rr.AnalysisLine("UCLA with 8 variables", "batch_correlation",
                               {"method": "spearman", "adjust": "holm"}, "Spearman’s ρ", 8,
                               "holm", "current", (), True, "Spearman ρ: UCLA with 8 variables",
                               2, 3, "written")
    result = rr.EvidenceResult("Spearman ρ: UCLA with 8 variables", "fictional.csv", "c" * 64,
                               "batch_correlation", {"method": "spearman", "adjust": "holm"},
                               "Spearman’s ρ", 8, "holm", "current", (), 2, 3, "written", 1,
                               False, (), 55, 55, (), "55",
                               (("ρ: UCLA – CautiousAction", "-0.33", "[-0.57, -0.07]", "= .011"),))
    values = dict(number=1, direction="less", alpha=0.05, analyses=(analysis,),
                  results=(result,), records=(ack(), deviation()), plan_version=4)
    values.update(fields)
    return rr.HypothesisEvidence(**values)


def report(language="en", evidence_of=None, hypotheses=None, results=()):
    hypotheses = hypotheses if hypotheses is not None else [
        {"id": "0a1b2c3d4e5f", "text": H1, "h0": "No association", "priority": "primary",
         "standing": "confirmatory"}]
    return rr.plan_report(rr.ReportInputs(
        title="Fictional study", language=language, hypotheses=hypotheses,
        results=list(results), evidence=evidence_of if evidence_of is not None
        else {"0a1b2c3d4e5f": evidence()}))


def lines(section) -> list[str]:
    found = []
    for item in section.items:
        if item.kind == "table":
            found += [" | ".join(row) for row in item.rows]
        else:
            found += (item.text or "").splitlines()
    return found


def result(id, title="Result", method="groups", **fields):
    defaults = dict(dataset="fictional.csv", dataset_rows=60, dataset_sha="a" * 64,
                    complete=60, created=datetime(2026, 1, 2, 3, 4))
    defaults.update(fields)
    return rr.ResultInfo(id=id, title=title, method=method, report="Engine report.", **defaults)


class PlanTests(unittest.TestCase):
    def test_every_hypothesis_says_direction_alpha_analyses_and_review(self):
        section = report().section("hypotheses")
        text = "\n".join(lines(section))
        self.assertIn(f"H1 (primary): {H1}", text, "designation, as in Stage 36")
        self.assertIn("H1: direction Less (one-sided); α = 0.05; plan version 4.", text)
        self.assertIn("H1 tested by “UCLA with 8 variables”: Spearman’s ρ; 8 tests; correction: "
                      "Holm (familywise error); result current, in this report.", text)
        self.assertIn("Result for H1: “Spearman ρ: UCLA with 8 variables” (current; calculated "
                      "as a test of H1, plan version 1): n = 55; ρ: UCLA – CautiousAction = "
                      "-0.33, 95% CI [-0.57, -0.07], p = .011; 2 of 3 assumption checks reviewed, "
                      "researcher's note written.", text)

    def test_each_decision_is_listed_with_its_reason_and_a_withdrawal_stays(self):
        withdrawal = {"id": "r3", "kind": "withdrawal", "at": "2026-01-03T03:04:00+00:00",
                      "supersedes": "r1", "reason": "Recorded for the wrong task.",
                      "detail": {}}
        designation = {"id": "r4", "kind": "designation", "at": "2026-01-03T04:00:00+00:00",
                       "plan_version": 2, "results_in_project": 1, "reason": DESIGNATION_REASON,
                       "detail": {"from": "primary", "to": "secondary"}}
        justification = {"id": "r5", "kind": "justification", "at": "2026-01-03T05:00:00+00:00",
                         "check_key": "H-ADDED-AFTER", "reason": "Fictional: planned on paper.",
                         "results_of_hypothesis": 0, "detail": {}}
        records = (ack(), deviation(), withdrawal, designation, justification)
        text = "\n".join(lines(report(evidence_of={"0a1b2c3d4e5f": evidence(records=records)})
                               .section("hypotheses")))
        self.assertIn("Decisions recorded for H1:", text)
        self.assertRegex(text, r"Acknowledged \(a directional hypothesis, two-sided p-values\), "
                               r"recorded .+, after 1 result\(s\) of H1\. Reason: "
                         + re.escape(ACK_REASON) + r" Withdrawn on .+\. Reason for the withdrawal:"
                                                   r" Recorded for the wrong task\.")
        self.assertRegex(text, r"Deviation from the plan \(method\), recorded .+, before H1 had "
                               r"any result\. Planned: Pearson’s r; used: Spearman’s ρ\. Reason: "
                         + re.escape(DEVIATION_REASON))
        self.assertRegex(text, r"Designation of H1 changed after results: primary → secondary "
                               r"\(plan version 2; 1 result\(s\) in the project\), recorded .+\. "
                               r"Reason: " + re.escape(DESIGNATION_REASON))
        self.assertIn("Justification (added after results)", text)
        self.assertIn("Reason: Fictional: planned on paper.", text)

    def test_a_designation_changed_after_results_without_a_record_is_named(self):
        history = ({"version": 1, "priority": "primary", "previous": None, "runs_before": 0,
                    "changed": False, "record": None},
                   {"version": 2, "priority": "exploratory", "previous": "primary",
                    "runs_before": 3, "changed": True, "record": None})
        text = "\n".join(lines(report(evidence_of={"0a1b2c3d4e5f": evidence(
            records=(), history=history)}).section("hypotheses")))
        self.assertIn("Designation of H1 changed after results: primary → exploratory (plan "
                      "version 2; 3 result(s) in the project); no reason was recorded.", text)

    def test_a_stale_result_and_a_missing_analysis_are_said(self):
        stale = rr.AnalysisLine("Groups by level", "batch_groups", {"adjust": "none"},
                                "Kruskal–Wallis H", 8, "none", "stale",
                                ("data changed after this result",), False, "KW", 0, 2, "none")
        hypotheses = [{"id": "0a1b2c3d4e5f", "text": "H one", "priority": "primary"},
                      {"id": "1a1b2c3d4e5f", "text": "H two", "priority": "secondary"}]
        text = "\n".join(lines(report(hypotheses=hypotheses, evidence_of={
            "0a1b2c3d4e5f": evidence(analyses=(stale,), results=()),
            "1a1b2c3d4e5f": rr.HypothesisEvidence(2, "two-sided", 0.01)}).section("hypotheses")))
        self.assertIn("H1 tested by “Groups by level”: Kruskal–Wallis H; 8 tests; correction: "
                      "None (raw p only); result needs review (data changed after this result), "
                      "not in this report.", text)
        self.assertIn("No analysis in this project tests H2 yet.", text)
        self.assertIn("H2: direction Two-sided; α = 0.01; plan version —.", text)
        self.assertIn("H2 (secondary) | No result in this report", text)

    def test_the_table_has_one_row_per_hypothesis_and_result(self):
        second = rr.EvidenceResult("Spearman ρ: UCLA with 8 variables", "fictional.csv",
                                   "d" * 64, "batch_correlation", {"method": "spearman"},
                                   "Spearman’s ρ", 8, "holm", "stale",
                                   ("data changed after this result",), 3, 3, "skipped", None,
                                   True, (), 50, 55)
        section = report(evidence_of={"0a1b2c3d4e5f": evidence(
            results=evidence().results + (second,))}).section("hypotheses")
        table = next(item for item in section.items if item.kind == "table")
        self.assertEqual(table.title, "Hypotheses and evidence")
        self.assertEqual(table.columns, ("Hypothesis", "Source result", "Data version",
                                         "Calculation", "Review", "Limitations"))
        self.assertEqual(len(table.rows), 2)
        first, later = table.rows
        self.assertEqual(first[0], "H1 (primary)")
        self.assertEqual(first[1], "Spearman ρ: UCLA with 8 variables (current); calculated as a "
                                   "test of H1, plan version 1")
        self.assertEqual(first[2], "fictional.csv · cccccccccccc")
        self.assertEqual(first[3], "Spearman’s ρ; 8 tests; correction: Holm (familywise error)")
        self.assertEqual(first[4], "2 of 3 assumption checks reviewed; researcher's note written")
        self.assertEqual(first[5], "—")
        self.assertIn("(needs review); linked to H1 after it was calculated", later[1])
        self.assertEqual(later[4], "3 of 3 assumption checks reviewed; interpretation skipped "
                                   "by the researcher")
        self.assertEqual(later[5], "Needs review: data changed after this result. 50 of 55 rows "
                                   "complete.")

    def test_numbers_come_from_the_inputs_only(self):
        """Every number in the new rows is one the inputs carry: the engine's
        family size, the review counts, the plan's α, the plan version."""
        section = report(evidence_of={"0a1b2c3d4e5f": evidence(alpha=0.025)}).section(
            "hypotheses")
        given = {"1", "2", "3", "4", "8", "0.025", "55", "2026", "01", "02", "03", "04", "05",
                 "0.33", "0.57", "0.07", "011"}      # the engine's row, as saved
        for line in lines(section):
            for number in re.findall(r"\d+(?:\.\d+)?", line.replace(H1, "")):
                self.assertTrue(number in given or re.fullmatch(r"\d\d", number) or
                                number in ("0",), (number, line))

    def test_the_rows_read_in_three_languages_and_never_judge_the_hypothesis(self):
        records = (ack(), deviation())
        for language in ("en", "lv", "ru"):
            with self.subTest(language=language):
                plan = report(language, evidence_of={"0a1b2c3d4e5f": evidence(records=records)})
                section = plan.section("hypotheses")
                text = "\n".join(lines(section))
                self.assertIn(rr.text(language, "records_title", number=1), text)
                self.assertIn(rr.text(language, "evidence"), [i.title for i in section.items])
                new = [line for line in lines(section)
                       if rr.text(language, "post_hoc", number=1) != line]
                for line in new:
                    self.assertNotRegex(line, VERDICTS[language], line)
                    self.assertNotRegex(line, r"\{[a-z_]+\}", "a placeholder left in the text")
        lv = "\n".join(lines(report("lv").section("hypotheses")))
        self.assertIn("H1: virziens Mazāks (vienpusēja); α = 0.05; plāna versija 4.", lv)
        self.assertIn("H1 pārbauda “UCLA with 8 variables”: Spīrmena ρ; testu skaits: 8", lv)
        ru = "\n".join(lines(report("ru").section("hypotheses")))
        self.assertIn("H1: направленность Меньше (односторонняя); α = 0.05; версия плана 4.", ru)
        self.assertIn("H1 проверяется анализом «UCLA with 8 variables»: ρ Спирмена; проверок: 8",
                      ru)

    def test_without_evidence_the_section_and_the_table_numbers_are_as_before(self):
        """AC-15: a report whose hypotheses no analysis tests has the Stage 36
        items and tables; a report with linked hypotheses adds one table, and
        every table is still numbered in document order."""
        hypotheses = [{"id": "0a1b2c3d4e5f", "text": "Planned", "priority": "primary",
                       "standing": "confirmatory"}]
        results = [result(1, "Group comparison")]
        before = report(hypotheses=hypotheses, evidence_of={}, results=results)
        untested = report(hypotheses=hypotheses, results=results, evidence_of={
            "0a1b2c3d4e5f": rr.HypothesisEvidence(1)})
        self.assertEqual([i.kind for i in before.section("hypotheses").items], ["paragraph", "note"])
        tables = [[(i.title, i.columns) for s in plan.sections for i in s.items if i.kind == "table"]
                  for plan in (before, untested)]
        self.assertEqual(tables[0], tables[1], "no evidence table without a linked analysis")
        linked = report(hypotheses=hypotheses, results=results)
        titles = [i.title for s in linked.sections for i in s.items if i.kind == "table"]
        self.assertEqual(titles[0], "Hypotheses and evidence")
        self.assertEqual(titles[1:], [t for t, _ in tables[0]])
        document = report_docx.build_research_docx(linked, version="test")
        captions = [p.text for p in document.paragraphs if re.fullmatch(r"Table \d+", p.text)]
        self.assertEqual(captions, [f"Table {n}" for n in range(1, len(titles) + 1)])
        self.assertEqual(len(document.tables), len(titles))


class WorkspaceReportTests(Case):
    """Through the real handlers: a plan, H1's analysis, decisions, the Word report."""

    def decided(self):
        ws, hid = self.planned()
        ws.app.navigate("project")
        ws.choose("plan-h0-method_key", "batch_correlation")
        ws.choose("plan-h0-variant", "pearson")
        ws.click("plan-save")
        ws.click("next-create-analysis")
        run_correlations(ws)                          # Spearman, not the planned Pearson
        ws.app.navigate("project")
        ws.click("hyp-1-toggle")
        ws.click(f"hyp-1-check-{check_index(ws, 'H-METHOD-DIFFERS')}-deviation")
        ws.type("hyp-1-reason", DEVIATION_REASON)
        ws.click("hyp-1-save")
        ws.click(f"hyp-1-check-{check_index(ws, 'H-DIR-TWOSIDED')}-acknowledge")
        ws.type("hyp-1-reason", ACK_REASON)
        ws.click("hyp-1-save")
        return ws, hid

    def export(self, ws, language="en") -> Document:
        ws.app.session.update_report(language=language)
        ws.run(ws.app.pages["reports"]._export_docx())
        return Document(str(ws.saved[-1]))

    @staticmethod
    def text(document) -> str:
        return "\n".join(p.text for p in document.paragraphs)

    @staticmethod
    def hypotheses(document, language: str) -> str:
        """The paragraphs of the Hypotheses section only (other sections
        hold engine texts such as an assumption to "confirm")."""
        title, found, inside = rr.text(language, "hypotheses"), [], False
        for paragraph in document.paragraphs:
            if paragraph.style.name == "Heading 1":
                inside = paragraph.text.endswith(f". {title}")
                continue
            if inside:
                found.append(paragraph.text)
        assert found, "no Hypotheses section"
        return "\n".join(found).replace(rr.text(language, "post_hoc", number=1), "")

    def test_the_word_report_names_the_test_the_decisions_and_the_evidence(self):
        ws, hid = self.decided()
        entry = ws.app.session.results[-1]
        ws.app.session.set_reviewed(entry.id, entry.run.evidence().assumptions[0], True)
        ws.app.session.set_note(entry.id, "Fictional interpretation.")
        ws.app.session.toggle_report(entry.id)
        # A designation changed after the result, with its reason (AC-3).
        ws.app.navigate("project")
        ws.choose("plan-h0-priority", "secondary")
        ws.type("plan-h0-reason", DESIGNATION_REASON)
        ws.click("plan-save")
        document = self.export(ws)
        text = self.text(document)
        self.assertIn("H1 (secondary): " + H1, text)
        self.assertIn("H1: direction Less (one-sided); α = 0.05; plan version 3.", text)
        self.assertIn("H1 tested by “UCLA with 8 variables”: Spearman’s ρ; 8 tests; correction: "
                      "Holm (familywise error)", text)
        self.assertIn("result current, in this report.", text)
        self.assertIn("1 of 3 assumption checks reviewed, researcher's note written.", text)
        self.assertRegex(text, r"Deviation from the plan \(method\), recorded .+, after 1 result"
                               r"\(s\) of H1\. Planned: Pearson’s r; used: Spearman’s ρ\. Reason: "
                         + re.escape(DEVIATION_REASON))
        self.assertIn("Reason: " + ACK_REASON, text)
        self.assertRegex(text, r"Designation of H1 changed after results: primary → secondary "
                               r"\(plan version 3; 1 result\(s\) in the project\)")
        self.assertIn(DESIGNATION_REASON, text)
        self.assertNotRegex(self.hypotheses(document, "en"), VERDICTS["en"])
        # The editable table, its numbering and its row.
        tables = [[[c.text for c in row.cells] for row in table.rows] for table in document.tables]
        evidence_table = next(t for t in tables if tuple(t[0]) == rr.TEXT["en"]["evidence_columns"])
        self.assertEqual(len(evidence_table), 2, "one hypothesis × one result")
        row = evidence_table[1]
        self.assertEqual(row[0], "H1 (secondary)")
        self.assertTrue(row[1].startswith(f"{entry.title} (current); calculated as a test of H1"))
        self.assertTrue(row[2].endswith(entry.provenance["dataset_sha256"][:12]))
        self.assertEqual(row[4], "1 of 3 assumption checks reviewed; researcher's note written")
        captions = [p.text for p in document.paragraphs if re.fullmatch(r"Table \d+", p.text)]
        self.assertEqual(captions, [f"Table {n}" for n in range(1, len(document.tables) + 1)])
        # The same rows in Latvian and Russian.
        for language, fragment in (("lv", "Novirze no plāna (metode)"),
                                   ("ru", "Отклонение от плана (метод)")):
            document = self.export(ws, language)
            text = self.text(document)
            self.assertIn(fragment, text)
            self.assertIn(DEVIATION_REASON, text)
            self.assertNotRegex(self.hypotheses(document, language), VERDICTS[language])

    def test_a_stale_result_and_a_result_left_out_are_reported_as_such(self):
        ws, hid = self.decided()
        task = ws.app.session.tasks[-1]
        ws.click("nav-analyze")
        ws.click(f"task-{task.id}")
        ws.click("task-rerun")                        # a second result of the same task
        first, second = ws.app.session.task_results(task.id)
        ws.app.session.toggle_report(first.id)        # only the older one in the report
        ws.app.session.confirm_level("UCLA", "ordinal")     # both are stale now
        ws.app.projects._refresh_stale()
        self.assertTrue(first.stale_reasons and second.stale_reasons)
        project = ws.app.projects.project
        evidence = rr.hypothesis_evidence(ws.app.session, project)[hid]
        self.assertEqual(evidence.others, 1, "the later result is not in the report")
        self.assertEqual([a.state for a in evidence.analyses], ["stale"])
        self.assertFalse(evidence.analyses[0].in_report)
        text = self.text(self.export(ws)) if not ws.app.pages["reports"]._blocked() else None
        self.assertIsNone(text, "stale results are refused as before (the gate is unchanged)")
        ws.app.pages["reports"].include_stale = True
        text = self.text(self.export(ws))
        self.assertIn("result needs review (measurement level of UCLA changed", text)
        self.assertIn("not in this report.", text)
        self.assertIn("1 other result(s) of the analyses of H1 are not in this report.", text)

    def test_building_the_rows_runs_no_engine(self):
        from unittest import mock

        import workspace_methods

        ws, hid = self.decided()
        ws.app.session.toggle_report(ws.app.session.results[-1].id)
        refuse = mock.Mock(side_effect=AssertionError("no engine for the report rows"))
        with mock.patch.object(workspace_methods, "run_method", refuse):
            evidence = rr.hypothesis_evidence(ws.app.session, ws.app.projects.project)
            plan = rr.plan_report(ws.app.pages["reports"].report_inputs())
        refuse.assert_not_called()
        self.assertEqual(evidence[hid].analyses[0].tests,
                         ws.app.session.results[-1].run.result.family_size)
        self.assertIn("Hypotheses and evidence",
                      [i.title for i in plan.section("hypotheses").items])
        self.assertEqual([c.key for c in evidence[hid].checks],
                         [c.key for c in ws.app.pages["project"].hypotheses._view(hid).checks
                          if c.state in ("open", "info") and c.key not in rr._COVERED_CHECKS
                          and not (c.key == "H-ADDED-AFTER" and c.severity == "warning")])
        self.assertTrue(all(isinstance(c, rw.Check) for c in evidence[hid].checks))


if __name__ == "__main__":
    unittest.main()
