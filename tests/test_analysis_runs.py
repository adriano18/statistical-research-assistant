"""Stage 33 parity: the new workspace runs exactly the classic calculations.

The classic workspace is built on a fake page and its real callbacks are
driven with the bundled synthetic example datasets. Every report string and
key result value captured from the classic callback must be identical to the
corresponding ``analysis_runs`` function on the same data and options.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("MPLBACKEND", "Agg")

import analysis_runs as runs  # noqa: E402
from data_loader import load_dataset  # noqa: E402

EXAMPLES = ROOT / "examples"


class ClassicHarness:
    """The real classic workspace with a spy on its output cache."""

    def __init__(self):
        import ux_inventory
        import research_app

        self.research_app = research_app
        self.captured: dict = {}
        self.page, self.root = ux_inventory.build_classic(captured=self.captured)
        self.controls = self.captured["controls"]
        self.actions = self.captured["actions"]
        self.outputs: list[tuple] = []

    def act(self, name: str):
        from flet.controls.context import _context_page
        from interpretation_wizard import build_analysis_evidence as real

        def spy(section, title, report, png, result=None):
            self.outputs.append((section, title, report, png, result))
            return real(section, title, report, png, result)

        token = _context_page.set(self.page)
        try:
            with patch.object(self.research_app, "build_analysis_evidence", spy):
                asyncio.run(self.actions[name](None))
        finally:
            _context_page.reset(token)
        if not self.outputs:
            raise AssertionError(f"classic action {name} produced no output")
        return self.outputs[-1]

    def check(self, control: str, labels):
        for box in self.controls[control].controls:
            box.value = box.label in labels


def assert_same(test, classic, run, *fields):
    section, title, report, png, result = classic
    test.assertEqual(run.section, section)
    test.assertEqual(run.title, title)
    test.assertEqual(run.report, report)
    test.assertTrue(bool(run.png) and bool(png))
    for name in fields:
        mine, theirs = getattr(run.result, name), getattr(result, name)
        if isinstance(theirs, float):
            # The one-factor omega optimizer differs in the 8th decimal between
            # two identical calls; reports (rounded) must still be identical.
            test.assertAlmostEqual(mine, theirs, places=6, msg=name)
        else:
            test.assertEqual(mine, theirs, name)


class ClassicParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ClassicHarness()

    def load(self, action: str, file: str) -> pd.DataFrame:
        from flet.controls.context import _context_page

        token = _context_page.set(self.app.page)
        try:
            asyncio.run(self.app.actions[action](None))
        finally:
            _context_page.reset(token)
        return load_dataset(EXAMPLES / file)

    def test_independent_groups_and_descriptives(self):
        df = self.load("load_scale_example", "sample_scale.csv")
        c = self.app.controls
        c["group_variable"].value = "group"
        c["group_outcome"].value = "stress_q1"
        c["group_outcome_scale"].value = "ordinal"
        c["group_method"].value = "mannwhitney"
        c["group_independent"].value = True
        c["group_assumptions"].value = False
        classic = self.app.act("calculate_groups")
        run = runs.run_groups(df, "group", "stress_q1", "mannwhitney", "ordinal", True, False)
        assert_same(self, classic, run, "statistic", "p_value", "n_a", "n_b")
        c["group_method"].value = "welch"
        c["group_outcome_scale"].value = "scale"
        c["group_assumptions"].value = True
        classic = self.app.act("calculate_groups")
        run = runs.run_groups(df, "group", "stress_q1", "welch", "scale", True, True)
        assert_same(self, classic, run, "statistic", "p_value")

        c["variable"].value = "stress_q2"
        c["scale"].value = "ordinal"
        classic = self.app.act("analyze_variable")
        assert_same(self, classic, runs.run_descriptive(df, "stress_q2", "ordinal"))
        c["explore_variable"].value = "stress_q1"
        c["explore_group"].value = "group"
        classic = self.app.act("run_explore")
        assert_same(self, classic, runs.run_explore(df, "stress_q1", "group"))

    def test_reliability_alpha_and_omega(self):
        df = self.load("load_scale_example", "sample_scale.csv")
        items = ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]
        self.app.check("reliability_items", items)
        self.app.controls["reliability_confirm"].value = True
        classic = self.app.act("calculate_alpha")
        assert_same(self, classic, runs.run_alpha(df, items, True), "alpha")
        self.app.controls["omega_ci_reps"].value = "0"
        classic = self.app.act("calculate_omega")
        assert_same(self, classic, runs.run_omega(df, items, True, 0), "omega")
        with self.assertRaises(ValueError):
            runs.run_alpha(df, items, False)

    def test_factor_and_matrix(self):
        df = self.load("load_factor_example", "sample_factor.csv")
        items = [c for c in df.columns if c != "participant_id"]
        c = self.app.controls
        self.app.check("factor_items", items)
        c["factor_method"].value = "efa"
        c["factor_count"].value = "2"
        c["factor_rotation"].value = "oblimin"
        c["factor_confirm"].value = True
        classic = self.app.act("calculate_factor_exploration")
        run = runs.run_factor(df, items, "efa", 2, "oblimin", True)
        assert_same(self, classic, run)
        self.assertTrue((run.result.loadings == classic[4].loadings).all())
        self.app.check("matrix_items", items)
        c["matrix_method"].value = "spearman"
        c["matrix_confirm"].value = True
        classic = self.app.act("calculate_matrix")
        assert_same(self, classic, runs.run_matrix(df, items, "spearman", True))

    def test_correlation_and_regression(self):
        df = self.load("load_regression_example", "sample_regression.csv")
        c = self.app.controls
        c["corr_x"].value = "study_hours"
        c["corr_y"].value = "stress_score"
        c["corr_scale_x"].value = "scale"
        c["corr_scale_y"].value = "scale"
        c["corr_method"].value = "pearson"
        c["corr_confirm"].value = True
        classic = self.app.act("calculate_correlation")
        run = runs.run_correlation(df, "study_hours", "stress_score", "pearson",
                                   "scale", "scale", True)
        assert_same(self, classic, run, "coefficient", "p_value", "ci_low", "ci_high")
        c["reg_outcome"].value = "stress_score"
        self.app.check("reg_predictors", ["study_hours", "sleep_hours"])
        c["reg_confirm"].value = True
        c["reg_hc3"].value = False
        classic = self.app.act("run_regression")
        run = runs.run_regression(df, "stress_score", ["study_hours", "sleep_hours"], True)
        assert_same(self, classic, run, "r_squared", "f_value", "f_p")

    def test_paired_and_repeated(self):
        df = self.load("load_paired_example", "sample_paired.csv")
        c = self.app.controls
        c["paired_before"].value = "before_score"
        c["paired_after"].value = "after_score"
        c["paired_scale"].value = "scale"
        c["paired_method"].value = "wilcoxon"
        c["paired_confirm"].value = True
        c["paired_assumptions"].value = True
        classic = self.app.act("calculate_paired")
        run = runs.run_paired(df, "before_score", "after_score", "wilcoxon", "scale",
                              True, True)
        assert_same(self, classic, run, "statistic", "p_value")
        df = self.load("load_repeated_example", "sample_repeated.csv")
        items = ["stress_before", "stress_mid", "stress_after"]
        self.app.check("rep_items", items)
        c["rep_method"].value = "rm_anova"
        c["rep_scale"].value = "scale"
        c["rep_same_people"].value = True
        c["rep_assumptions"].value = True
        classic = self.app.act("run_repeated")
        assert_same(self, classic, runs.run_repeated(df, items, "rm_anova", "scale",
                                                     True, True))

    def test_chi_square_omnibus_and_posthoc(self):
        df = self.load("load_categorical_example", "sample_categorical.csv")
        c = self.app.controls
        c["chi_a"].value = "group"
        c["chi_b"].value = "outcome"
        c["chi_confirm"].value = True
        classic = self.app.act("calculate_chi_square")
        assert_same(self, classic, runs.run_chi_square(df, "group", "outcome", True),
                    "chi2", "p_value")
        df = self.load("load_three_groups_example", "sample_three_groups.csv")
        c["omnibus_group"].value = "group"
        c["omnibus_outcome"].value = "score"
        c["omnibus_scale"].value = "ordinal"
        c["omnibus_method"].value = "kruskal"
        c["omnibus_independent"].value = True
        c["omnibus_assumptions"].value = True
        classic = self.app.act("calculate_omnibus")
        omnibus = runs.run_omnibus(df, "group", "score", "kruskal", "ordinal", True, True)
        assert_same(self, classic, omnibus)
        from flet.controls.context import _context_page
        from interpretation_wizard import build_analysis_evidence as real

        token = _context_page.set(self.app.page)
        try:
            with patch.object(self.app.research_app, "build_analysis_evidence",
                              lambda *a, **k: (self.app.outputs.append(
                                  (*a, k.get("result"))), real(*a, **k))[1]):
                asyncio.run(c["posthoc_button"].on_click(None))
        finally:
            _context_page.reset(token)
        classic = self.app.outputs[-1]
        posthoc = runs.run_posthoc(omnibus)
        self.assertEqual(posthoc.title, classic[1])
        self.assertEqual(posthoc.report, classic[2])

    def test_logistic_and_ancova(self):
        df = self.load("load_logistic_example", "sample_logistic.csv")
        c = self.app.controls
        c["log_outcome"].value = "wellbeing_improved"
        self.app.check("log_predictors", ["sleep_hours", "activity_hours"])
        c["log_confirm"].value = True
        classic = self.app.act("run_logistic")
        assert_same(self, classic, runs.run_logistic(
            df, "wellbeing_improved", ["sleep_hours", "activity_hours"], True))
        df = self.load("load_ancova_example", "sample_ancova.csv")
        c["ac_outcome"].value = "wellbeing"
        c["ac_group"].value = "group"
        self.app.check("ac_covariates", ["baseline_score"])
        c["ac_mode"].value = "ancova"
        c["ac_confirm"].value = True
        classic = self.app.act("run_ancova")
        assert_same(self, classic, runs.run_ancova(
            df, "wellbeing", "group", ["baseline_score"], "ancova", True))


if __name__ == "__main__":
    unittest.main()
