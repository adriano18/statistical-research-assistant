"""Stage 33 end-to-end journeys through the new workspace (synthetic data only).

1. XLSX → variable checks → guided Mann–Whitney → APA table, boxplot,
   TXT/PNG/Word export — in at most five meaningful decisions.
2. Scientific PDF → shared-scale review → 20 items → respondent preview →
   publish → responses → CSV + codebook → reverse-scoring → α and ω.
3. Data preparation → reverse-scored items → EFA through "All methods".

Every reported value is compared with a direct ``analysis_runs`` call on
the same data: the workspace must not change validated results.
"""

from __future__ import annotations

import os
import unittest
import zipfile

os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402
import pandas as pd  # noqa: E402

import analysis_runs as runs  # noqa: E402
from workspace_harness import ROOT, Workspace  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n"


class XlsxToApaReportJourney(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)

    def test_novice_reaches_an_exported_apa_report_in_five_decisions(self):
        ws = self.ws
        source = pd.read_csv(ROOT / "examples" / "sample_scale.csv")
        xlsx = ws.root / "anxiety_study.xlsx"
        source.to_excel(xlsx, index=False)
        decisions = []

        # Decision 1: open the data file.
        self.assertTrue(ws.run(ws.app.load_path(str(xlsx))))
        decisions.append("open file")
        self.assertEqual(ws.app.route, "data")
        self.assertTrue(ws.find("data-dictionary"))
        # Scientific confirmation (not a decision): accept checked suggestions.
        ws.check("data-accept-confirm")
        ws.click("data-accept")
        self.assertEqual(ws.app.session.level("stress_q1"), "ordinal")
        self.assertEqual(ws.app.session.level("group"), "nominal")
        self.assertEqual(ws.app.session.variables["stress_q1"].confirmed_in, "data-bulk")

        ws.key("4", ctrl=True)  # navigation, not a research decision
        ws.click("goal-compare")
        decisions.append("goal: compare groups")
        ws.check("role-outcome-stress_q1")
        decisions.append("outcome")
        ws.choose("role-group", "group")
        decisions.append("group")
        self.assertTrue(ws.has_text("Mann–Whitney U"))
        self.assertTrue(ws.has_text("group has 2 groups in the data: A, B"))
        ws.check("design-confirm-independent")  # required scientific confirmation
        ws.click("guided-run")
        decisions.append("run recommended method")
        self.assertLessEqual(len(decisions), 5)

        self.assertEqual(ws.app.route, "results")
        entry = ws.app.session.results[-1]
        expected = runs.run_groups(ws.app.session.df, "group", "stress_q1", "mannwhitney",
                                   "ordinal", True, False)
        self.assertEqual(entry.run.report, expected.report)
        self.assertEqual(entry.run.result.statistic, expected.result.statistic)
        self.assertEqual(entry.run.result.p_value, expected.result.p_value)
        self.assertIn("I confirm that the two groups contain independent observations",
                      entry.confirmations)
        self.assertTrue(ws.find("result-table"))
        self.assertTrue(ws.find("result-figure"))
        self.assertTrue(ws.has_text("Table 1"))
        self.assertTrue(ws.has_text(f"{expected.result.statistic:.3f}"))
        # Exact p and CI only; the "Sig." dichotomy is never rendered.
        self.assertFalse(ws.has_text("Sig."))

        ws.click("export-txt")
        ws.click("export-png")
        ws.click("export-docx")
        txt, png, docx = ws.saved
        self.assertIn(expected.report.splitlines()[0], txt.read_text(encoding="utf-8"))
        self.assertTrue(png.read_bytes().startswith(PNG))
        with zipfile.ZipFile(docx) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("Mann", document)
        self.assertIn(f"{expected.result.statistic:.3f}"[:-1], document)
        self.assertTrue(ws.has_text("Saved:"))

        ws.click("result-add-report")
        self.assertEqual(ws.app.session.report_order, [entry.id])
        ws.app.navigate("reports")
        ws.click("reports-export")
        combined = ws.saved[-1].read_text(encoding="utf-8")
        self.assertIn(expected.report.strip().splitlines()[0], combined)


class PdfQuestionnaireToAnalysisJourney(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)

    def test_scientific_pdf_to_responses_and_reliability(self):
        from synthetic_documents import REVISED_LABELS, connectedness_text_pdf
        from survey_storage import list_surveys, submit_response

        ws = self.ws
        page = ws.app.pages["import"]
        ws.app.navigate("import")
        ws.run(page.open_bytes(connectedness_text_pdf(), "synthetic_two_versions.pdf"))
        self.assertEqual(len(page.session.instruments), 2)
        ws.choose("imp-instrument", "1")
        instrument = page.session.instrument
        self.assertEqual(len(instrument.questions), 20)
        scheme = instrument.schemes[0]
        self.assertEqual(tuple(scheme.labels), REVISED_LABELS)
        # Blocked until the researcher confirms the scale and the checklist,
        # step by step in the review wizard (the footer stays on screen).
        self.assertTrue(ws.find("imp-create-draft").disabled)
        ws.click("imp-step-scale")
        ws.check(f"scale-{scheme.id}-structure")
        ws.check(f"scale-{scheme.id}-numeric")
        ws.click(f"scale-{scheme.id}-apply")
        self.assertTrue(page.session.instrument.schemes[0].codes_confirmed)
        ws.click("imp-next")
        self.assertEqual(page.step, "items")
        ws.click("imp-step-confirm")
        ws.check("imp-check-version")
        ws.check("imp-check-rights")
        self.assertTrue(ws.find("imp-create-draft").disabled, "every confirmation is its own")
        ws.check("imp-check-items")
        ws.click("imp-create-draft")
        self.assertEqual(ws.app.route, "questionnaires")
        builder = ws.app.pages["questionnaires"]
        self.assertEqual(len(builder.draft), 20)
        self.assertTrue(all(q["kind"] == "rating_scale" for q in builder.draft))
        radios = [c for c in ws.controls() if isinstance(c, ft.RadioGroup)]
        self.assertEqual(len(radios), 20)
        self.assertFalse(ws.has_text("Your answer"))

        builder.title = "Synthetic connectedness study"
        survey = builder._publish()
        self.assertIsNotNone(survey)
        self.assertEqual([s.survey_id for s in list_surveys(ws.app.survey_root)],
                         [survey.survey_id])
        keys = [q["key"] for q in survey.questions]
        import numpy as np

        generator = np.random.default_rng(20261105)  # fictional respondents
        reverse_numbers = set(scheme.reverse_items)
        for person in range(60):
            trait = generator.normal()
            answers = {}
            for row, key in zip(instrument.questions, keys):
                value = int(np.clip(round(2.5 + 0.9 * trait + generator.normal(0, 0.7)), 1, 4))
                answers[key] = str(5 - value if row.number in reverse_numbers else value)
            submit_response(ws.app.survey_root, survey.survey_id, answers)
        ws.app.navigate("questionnaires")
        ws.click(f"analyze-{survey.survey_id}")
        self.assertEqual(ws.app.route, "data")
        df = ws.app.session.df
        self.assertEqual(len(df), 60)
        ws.app.navigate("questionnaires")
        ws.run(builder._export(survey))
        csv_path = [p for p in ws.saved if p.suffix == ".csv"][-1]
        self.assertTrue(csv_path.is_file())
        self.assertTrue(csv_path.with_name(csv_path.stem + "_codebook.json").is_file())

        # Reverse-score the documented reverse items, then α and ω (guided).
        from data_preparation import reverse_item

        prepared = df.copy()
        items = []
        for row, key in zip(instrument.questions, keys):
            if row.number in reverse_numbers:
                prepared = reverse_item(prepared, key, f"{key}_r", 1, 4).frame
                items.append(f"{key}_r")
            else:
                items.append(key)
        ws.app.session.set_dataset(prepared, "connectedness (prepared)")
        for item in items:
            ws.app.session.confirm_level(item, "ordinal")
        analyze = ws.app.pages["analyze"]
        ws.app.navigate("analyze")
        ws.click("goal-scale")
        for item in items:
            ws.check(f"role-items-{item}")
        # 20 items: the validated ω accepts 3–12, so the advisor proposes α for
        # the whole set and says so before anything runs.
        self.assertTrue(ws.has_text("Cronbach’s α"))
        self.assertTrue(ws.has_text("3–12 items"))
        ws.check("design-confirm-construct")
        ws.click("guided-run")
        alpha = ws.app.session.results[-1].run
        self.assertEqual(alpha.report, runs.run_alpha(prepared, items, True).report)
        # ω for a documented 10-item subset, through the same guided steps.
        subset = items[:10]
        ws.app.navigate("analyze")  # the guided selections are kept
        for item in items[10:]:
            ws.check(f"role-items-{item}", False)
        self.assertTrue(ws.has_text("McDonald’s ω + item analysis"))
        ws.check("design-confirm-construct")
        ws.click("guided-run")
        omega = ws.app.session.results[-1].run
        expected = runs.run_omega(prepared, subset, True, 0)
        self.assertEqual(omega.report, expected.report)
        self.assertAlmostEqual(omega.result.omega, expected.result.omega, places=6)
        self.assertEqual(analyze.mode, "guided")


class PreparationToFactorJourney(unittest.TestCase):
    def test_reverse_scored_items_then_efa_from_all_methods(self):
        from data_preparation import reverse_item

        ws = Workspace()
        self.addCleanup(ws.close)
        df = pd.read_csv(ROOT / "examples" / "sample_factor.csv")
        prepared = reverse_item(df, "workstress_q1", "workstress_q1_r", 1, 5).frame
        ws.app.session.set_dataset(prepared, "factor (prepared)")
        items = ["wellbeing_q1", "wellbeing_q2", "wellbeing_q3",
                 "workstress_q1_r", "workstress_q2", "workstress_q3"]
        for item in items:
            ws.app.session.confirm_level(item, "ordinal")
        ws.app.navigate("analyze")
        ws.segment("analyze-mode", "all")
        self.assertEqual(len(ws.find_all("method-")), 17)   # 15 classic + 2 batch (Stage 36)
        ws.click("method-factor")
        for item in items:
            ws.check(f"form-items-{item}")
        ws.choose("form-option-count", "2")
        ws.choose("form-option-rotation", "oblimin")
        ws.check("form-confirm-design")
        ws.click("form-run")
        run = ws.app.session.results[-1].run
        expected = runs.run_factor(prepared, items, "efa", 2, "oblimin", True)
        self.assertEqual(run.report, expected.report)
        self.assertTrue((run.result.loadings == expected.result.loadings).all())
        self.assertTrue(ws.has_text("Component / factor loading matrix"))


if __name__ == "__main__":
    unittest.main()
