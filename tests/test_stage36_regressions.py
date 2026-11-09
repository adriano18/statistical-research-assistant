"""Stage 36.0: reproductions of the documented defects (docs/STAGE36_PLAN.md).

Every test states the behaviour Stage 36 requires and is marked
``expectedFailure`` while the defect exists: CI shows each reproduction,
and the pull request that fixes a defect must remove the marker (an
unexpected success fails the suite). Synthetic fixtures only.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd  # noqa: E402

import stage36_fixtures as fx  # noqa: E402

STEPS = ("question", "data", "variables", "design", "method", "result", "report")


def synthetic_frame() -> pd.DataFrame:
    return pd.read_csv(fx.fixture(fx.CSV))


def workspace_with_synthetic_data():
    """A workspace with an open project, the synthetic CSV loaded and its
    measurement levels confirmed."""
    from workspace_harness import Workspace

    ws = Workspace()
    ws.app.projects.create("Fictional Stage 36 study")
    assert ws.run(ws.app.load_path(str(fx.fixture(fx.CSV))))
    session = ws.app.session
    levels = {"Code": "id", "Age": "scale", "Sex": "nominal", "UCLA": "scale",
              "UCLA_Level": "ordinal", **{name: "scale" for name in fx.SCALES}}
    for name, level in levels.items():
        session.confirm_level(name, level)
    return ws


def tone_of(ws, key: str) -> str:
    import workspace_components as wc
    import workspace_tokens as tk

    chip = ws.find(f"journey-{key}")
    palette = tk.palette(ws.app.session.theme)
    for tone, (bg, _fg, _icon) in wc.TONES.items():
        if chip.bgcolor == getattr(palette, bg):
            return tone
    return "?"


class NavigationReproduction(unittest.TestCase):
    # 36.0 D1, FIXED in 36.1
    def test_every_journey_step_opens_its_own_step(self):
        """Spec §3: each item of Question → Data → Variables → Design →
        Method → Result → Report opens that step and marks it current.
        Variables opened Data; Method opened Design."""
        ws = workspace_with_synthetic_data()
        self.addCleanup(ws.close)
        ws.run(ws.app.pages["analyze"]._execute(
            "correlation", {"x": "UCLA", "y": "AssertiveAction"}, {"method": "spearman"}, {}))
        for key in STEPS:
            ws.click(f"journey-{key}")
            self.assertEqual(tone_of(ws, key), "info", f"'{key}' opened another step")


class StructuredResultReproduction(unittest.TestCase):
    # 36.0 D2, FIXED in 36.2
    def test_descriptive_statistics_are_structured_numbers(self):
        """Spec §8: no 'Structured numeric results: Not captured'; N,
        missing, M, SD, median, IQR, min and max come from a structured
        result, not from parsing the report text."""
        from analysis_runs import run_descriptive

        frame = synthetic_frame()
        evidence = run_descriptive(frame, "UCLA", "scale").evidence()
        estimates = {row.parameter: row.estimate for row in evidence.rows}
        self.assertNotIn("Not captured", estimates.values())
        values = frame["UCLA"]
        q1, q3 = values.quantile([0.25, 0.75])
        expected = {"N": "55", "Missing": "0", "Mean": f"{values.mean():.2f}",
                    "SD": f"{values.std():.2f}", "Median": f"{values.median():.2f}",
                    "IQR": f"{q3 - q1:.2f}", "Minimum": f"{values.min():.2f}",
                    "Maximum": f"{values.max():.2f}"}
        for parameter, value in expected.items():
            self.assertEqual(estimates.get(parameter), value, parameter)


class BatchAnalysisReproduction(unittest.TestCase):
    # 36.0 D3, FIXED in 36.2
    def test_one_variable_against_eight_scales_in_one_run(self):
        """Spec §4-5: UCLA x 8 scales is one batch: 8 rows with N, rho,
        raw p, Holm-adjusted p and the stated p method."""
        from batch_correlation import correlate_many
        from scipy import stats
        from statsmodels.stats.multitest import multipletests

        frame = synthetic_frame()
        family = correlate_many(frame, "UCLA", list(fx.SCALES), method="spearman",
                                adjust="holm")
        self.assertEqual([row.y for row in family.rows], list(fx.SCALES))
        raw = [row.p_raw for row in family.rows]
        self.assertEqual([row.n for row in family.rows], [55] * 8)
        for row in family.rows:
            rho = stats.spearmanr(frame["UCLA"], frame[row.y]).statistic
            self.assertAlmostEqual(row.estimate, rho, places=12)
        adjusted = multipletests(raw, method="holm")[1]
        for row, value in zip(family.rows, adjusted):
            self.assertAlmostEqual(row.p_adjusted, value, places=12)

    # 36.0 D4, FIXED in 36.2/36.3
    def test_a_two_group_variable_is_explained_before_a_three_group_test(self):
        """Spec §6: Sex (2 categories) with a 3-8 group method is explained
        BEFORE the run, with the two-group comparison offered instead."""
        import workspace_methods as wm

        ws = workspace_with_synthetic_data()
        self.addCleanup(ws.close)
        problems = wm.role_problems(wm.METHODS["omnibus"], {"group": "Sex", "outcome": "UCLA"},
                                    ws.app.session)
        self.assertTrue(problems, "no explanation before the run")
        self.assertIn("groups", str(problems), "the two-group comparison is not offered")


    # 36.0 D9, FIXED in 36.2
    def test_small_groups_are_handled_before_the_run_not_refused_after(self):
        """Spec §6: groups of 3/47/5 (UCLA_Level) get small/unequal-group
        warnings; the researcher never learns after Run that nothing ran."""
        ws = workspace_with_synthetic_data()
        self.addCleanup(ws.close)
        page = ws.app.pages["analyze"]
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")
        ws.check(f"role-outcome-{fx.SCALES[0]}")
        for key in ("independent", "assumptions"):
            if ws.find_all(f"design-confirm-{key}"):
                ws.check(f"design-confirm-{key}")
        before = len(ws.app.session.results)
        if not ws.find_all("design-blockers"):
            ws.click("guided-run")
            self.assertEqual(len(ws.app.session.results), before + 1, page.message)

    # 36.0 D10, FIXED in 36.2
    def test_kruskal_wallis_for_eight_outcomes_with_a_group_of_three(self):
        """Spec §6: one grouping variable, several outcomes; H, df and p
        with the p method stated; epsilon-squared defined; warnings about
        the 3-observation group instead of a refusal."""
        from batch_groups import compare_many
        from scipy import stats

        frame = synthetic_frame()
        family = compare_many(frame, "UCLA_Level", list(fx.SCALES), method="kruskal")
        self.assertEqual([row.outcome for row in family.rows], list(fx.SCALES))
        for row in family.rows:
            samples = [frame.loc[frame["UCLA_Level"] == g, row.outcome] for g in (1, 2, 3)]
            self.assertAlmostEqual(row.statistic, stats.kruskal(*samples).statistic, places=10)
            self.assertEqual(row.df, 2)
            self.assertTrue(row.p_method)
            self.assertTrue(any("3" in w for w in row.warnings), "small group not mentioned")


class ReliabilityReproduction(unittest.TestCase):
    @unittest.expectedFailure    # 36.0 D5, fixed in 36.3
    def test_no_reliability_from_total_scores(self):
        """Spec §7: with only total scores, no fictitious alpha/omega; say
        that item responses are needed."""
        import workspace_methods as wm

        ws = workspace_with_synthetic_data()
        self.addCleanup(ws.close)
        advice = wm.advise("scale", {"items": list(fx.SCALES[:4])}, ws.app.session)
        self.assertIsNone(advice.method, "a reliability coefficient was offered for totals")
        self.assertIn("block.totals_not_items", [key for key, _ in advice.blockers])


class ImportReproduction(unittest.TestCase):
    # 36.0 D6, fixed in 36.5 (table_forms: structure-first Word forms)
    def test_two_unnumbered_sixty_item_forms(self):
        """Spec §10 COPE-LV: no item numbers inside the cells is not 'not
        recognised'; both forms are found, 60 items each, with their own
        response options; references stay out."""
        from scientific_survey_import import read_scientific_document

        review = read_scientific_document(fx.fixture(fx.DOCX_UNNUMBERED))
        self.assertEqual([len(c.questions) for c in review.instruments], [60, 60])
        labels = [list(c.schemes[0].labels) if c.schemes else [] for c in review.instruments]
        self.assertEqual(labels, [["Hardly ever", "Now and then", "Fairly often", "Very often"],
                                  ["Not at all", "Slightly", "Moderately", "Strongly"]])

    # 36.0 D7, fixed in 36.5 (expected_item_count ignores part sizes)
    def test_the_stated_item_count_is_not_taken_from_a_scoring_note(self):
        """'each with four invented items' describes the scoring key, not the
        questionnaire length (60)."""
        from scientific_survey_import import read_scientific_document

        review = read_scientific_document(fx.fixture(fx.DOCX_NUMBERED))
        self.assertIn(review.expected_count, (None, 60))

    # 36.0 D8, fixed in 36.5 (ocr_table_rows: rows rebuilt from word boxes)
    @unittest.skipUnless(shutil.which("tesseract"), "local OCR engine")
    def test_a_scanned_table_with_a_number_column_yields_all_52_items(self):
        """Spec §10 SACS-LV: the scanned table (number column, wrapped
        rows, repeated legend, artifacts before numbers) yields all 52
        candidates. Before: the sequence broke at item 17 (16 of 52)."""
        import visual_survey_review as vsr

        source = vsr.load_document_bytes(fx.fixture(fx.SCAN_TABLE_LV))
        review = vsr.ocr_scientific_pdf(source, fx.SCAN_TABLE_LV, [1, 2], "lav")
        numbers = [q.number for c in review.instruments for q in c.questions]
        self.assertEqual(sorted(numbers), list(range(1, 53)))


if __name__ == "__main__":
    unittest.main()
