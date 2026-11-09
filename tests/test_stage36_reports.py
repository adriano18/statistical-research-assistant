"""Stage 36.6: the research report as one scientific document (spec §11).

The plan is checked as data (sections, merging, labels, limitations) and
the Word document is opened and read back. Only saved engine output and
the researcher's entries are used; synthetic data only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from docx import Document  # noqa: E402

import report_docx  # noqa: E402
import research_report as rr  # noqa: E402
from interpretation_wizard import EvidenceRow  # noqa: E402

NOTE = "Group differences do not establish causation."


def result(id, title="Result", method="groups", report="Engine report.", **fields):
    defaults = dict(dataset="fictional.csv", dataset_rows=60, dataset_sha="a" * 64,
                    complete=60, created=datetime(2026, 1, 2, 3, 4))
    defaults.update(fields)
    return rr.ResultInfo(id=id, title=title, method=method, report=report, **defaults)


def plan(results, **fields):
    return rr.plan_report(rr.ReportInputs(title="Fictional study", results=list(results),
                                          **fields))


def texts(section) -> str:
    return "\n".join(item.text or item.title for item in section.items)


class PlanTests(unittest.TestCase):
    def test_sections_follow_the_write_up_and_empty_ones_are_left_out(self):
        report = plan([result(1, "Group comparison"),
                       result(2, "Wellbeing", method="descriptive", report="M = 3.1.")],
                      question="Do the fictional groups differ?")
        self.assertEqual([s.key for s in report.sections],
                         ["question", "data", "descriptives", "assumptions", "tests",
                          "appendix"])
        self.assertEqual(report.section("question").items[0].text,
                         "Do the fictional groups differ?")
        self.assertIn("Wellbeing", texts(report.section("descriptives")))
        self.assertNotIn("Wellbeing", texts(report.section("tests")))

    def test_the_researcher_can_leave_sections_out(self):
        sections = frozenset(rr.SECTIONS) - {"assumptions", "appendix"}
        report = plan([result(1)], sections=sections)
        self.assertNotIn("assumptions", [s.key for s in report.sections])
        self.assertNotIn("appendix", [s.key for s in report.sections])

    def test_a_task_has_one_heading_and_a_repeated_paragraph_is_written_once(self):
        report = plan([result(1, "First outcome", report=f"First.\n\n{NOTE}", task_id="t1",
                              task_title="Fictional task"),
                       result(2, "Second outcome", report=f"Second.\n\n{NOTE}", task_id="t1",
                              task_title="Fictional task")])
        items = report.section("tests").items
        self.assertEqual([i.text for i in items if i.kind == "heading"],
                         ["Research task: Fictional task"])
        self.assertEqual(sum(1 for i in items if i.text == NOTE), 1)

    def test_an_identical_result_calculated_twice_is_written_once(self):
        report = plan([result(1, "Same"), result(2, "Same")])
        items = report.section("tests").items
        self.assertEqual([i.text for i in items if i.kind == "subheading"], ["Same"])
        self.assertIn("Calculated 2 times with an identical result", texts(report.section("tests")))
        self.assertEqual(report.results, 1)

    def test_different_data_versions_are_named_and_never_combined(self):
        report = plan([result(1, "Before", dataset_sha="a" * 64),
                       result(2, "After", dataset_sha="b" * 64)])
        self.assertEqual(len(report.versions), 2)
        self.assertIn("2 versions of the data", texts(report.section("data")))
        self.assertIn("2 versions of the data", texts(report.section("limitations")))
        lines = [i.text for i in report.section("tests").items if i.kind == "note"]
        self.assertTrue(any("aaaaaaaaaaaa" in line for line in lines))
        self.assertTrue(any("bbbbbbbbbbbb" in line for line in lines))

    def test_a_hypothesis_added_after_the_results_is_exploratory(self):
        report = plan([result(1)], hypotheses=[
            {"text": "Planned", "priority": "primary", "standing": "confirmatory"},
            {"text": "Added later", "priority": "secondary", "standing": "added_after_results"}])
        hypotheses = report.section("hypotheses").items
        self.assertEqual([i.kind for i in hypotheses], ["paragraph", "note", "paragraph", "warning"])
        self.assertIn("post hoc", hypotheses[3].text)
        self.assertIn("1 hypothesis(es) were added after results", texts(report.section("limitations")))

    def test_low_reliability_is_a_methodological_warning(self):
        low = result(1, "Fictional scale", method="alpha",
                     rows=(EvidenceRow("Cronbach's α", "0.62", "[0.51, 0.71]"),))
        good = result(2, "Other scale", method="omega", report="Other.",
                      rows=(EvidenceRow("McDonald's ω", "0.84", "[0.80, 0.88]"),))
        report = plan([low, good])
        reliability = texts(report.section("reliability"))
        self.assertIn("Cronbach's α = 0.62", reliability)
        self.assertNotIn("0.84 for", reliability)
        self.assertIn("Reliability below .70: Fictional scale", texts(report.section("limitations")))

    def test_small_unequal_groups_and_missing_values_are_limitations(self):
        report = plan([result(1, "KW", warnings=("Small groups in G: 1 (3).",
                                                 "Very unequal group sizes in G (3, 47, 5)."),
                              complete=55, dataset_rows=60)])
        limits = texts(report.section("limitations"))
        self.assertIn("Small groups: KW", limits)
        self.assertIn("Very unequal group sizes: KW", limits)
        self.assertIn("KW uses 55 of 60 rows", limits)

    def test_effects_are_the_engine_rows_with_intervals(self):
        rows = (EvidenceRow("ρ", "-0.33", "[-0.57, -0.07]", ".011"),
                EvidenceRow("N", "55"))
        report = plan([result(1, "Pair", method="correlation", rows=rows),
                       result(2, "Descriptive", method="descriptive",
                              rows=(EvidenceRow("Mean", "3.1", "[2.9, 3.3]"),))])
        table = report.section("effects").items[0]
        self.assertEqual(table.rows, (("Pair", "ρ", "-0.33", "[-0.57, -0.07]", ".011"),))

    def test_section_titles_in_latvian_and_russian(self):
        for language, word in (("lv", "Hipotēžu pārbaude"), ("ru", "Проверка гипотез")):
            report = plan([result(1)], language=language)
            self.assertEqual(report.section("tests").title, word)


class WordTests(unittest.TestCase):
    def test_the_document_has_numbered_sections_tables_and_figures(self):
        from PIL import Image
        from io import BytesIO

        buffer = BytesIO()
        Image.new("RGB", (400, 300), "white").save(buffer, format="PNG")
        report = plan([result(1, "Group comparison", figure=buffer.getvalue(),
                              figure_title="Fictional chart", figure_note="Note. Fictional.",
                              figure_from_studio=True,
                              rows=(EvidenceRow("d", "0.40", "[0.10, 0.70]", ".010"),))],
                      question="Q?", language="ru")
        document = report_docx.build_research_docx(report, version="test")
        headings = [p.text for p in document.paragraphs if p.style.name == "Heading 1"]
        self.assertEqual(headings[0], "1. Исследовательский вопрос")
        self.assertTrue(all(h.split(".")[0].isdigit() for h in headings))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("Рисунок 1", text)
        self.assertIn("Fictional chart", text)
        self.assertIn("Примечание. Fictional.", text)
        self.assertEqual(len(document.inline_shapes), 1)
        self.assertGreaterEqual(len(document.tables), 3)    # data, effects, appendix


class ReportsPageTests(unittest.TestCase):
    def test_the_reports_page_writes_the_research_report(self):
        from test_stage36_ux_baseline import eight_correlations, prepared_workspace

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        project = ws.app.projects.project
        project.save_plan({"objectives": "Fictional aims", "hypotheses": [
            {"text": "UCLA relates to coping", "priority": "primary"}]})
        eight_correlations(ws)
        plan_now = project.plan()["plan"]
        plan_now["hypotheses"].append({"text": "Levels differ (added later)",
                                       "priority": "secondary"})
        project.save_plan(plan_now)
        entry = ws.app.session.results[0]
        ws.click("task-add-report")
        ws.click("nav-reports")
        self.assertTrue(ws.find("reports-structure"))
        ws.check("reports-section-appendix", False)
        ws.choose("reports-language", "lv")
        ws.click("reports-export-docx")
        document = Document(str(ws.saved[-1]))
        headings = [p.text for p in document.paragraphs if p.style.name == "Heading 1"]
        self.assertIn("Hipotēzes", " ".join(headings))
        self.assertFalse(any("Pielikums" in h for h in headings), "appendix left out")
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("UCLA relates to coping", text)
        self.assertIn("post hoc", text)
        self.assertIn(entry.run.title, text)


if __name__ == "__main__":
    unittest.main()
