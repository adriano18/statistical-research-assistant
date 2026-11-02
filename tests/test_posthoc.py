"""Regression tests for Tukey, Games–Howell and tie-corrected Dunn–Holm."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from scipy import stats

from omnibus_analysis import analyze_omnibus
from posthoc_analysis import analyze_posthoc, holm_adjust
from posthoc_reporting import format_posthoc_report


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_three_groups.csv"


class PosthocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(SAMPLE)

    def run_test(self, method):
        outcome_scale = "ordinal" if method == "kruskal" else "scale"
        omnibus = analyze_omnibus(
            self.data, "group", "score",
            method, outcome_scale, True, True
        )
        return analyze_posthoc(omnibus)

    def test_holm_adjustment(self):
        self.assertEqual(
            [round(x, 5) for x in holm_adjust([0.02, 0.01, 0.04])],
            [0.04, 0.03, 0.04],
        )
        with self.assertRaises(ValueError):
            holm_adjust([-0.1])

    def test_tukey_matches_scipy(self):
        report = self.run_test("anova")
        self.assertEqual(len(report.pairs), 3)
        self.assertIn("Tukey", report.method)
        samples = [
            self.data.loc[self.data.group == group, "score"].to_numpy()
            for group in ("A", "B", "C")
        ]
        reference = stats.tukey_hsd(*samples, equal_var=True)
        self.assertAlmostEqual(
            report.pairs[0].p_adjusted, reference.pvalue[0, 1], places=10
        )
        self.assertAlmostEqual(
            report.pairs[0].estimate, reference.statistic[0, 1], places=10
        )
        self.assertLess(report.pairs[0].ci_low, report.pairs[0].estimate)
        self.assertGreater(report.pairs[0].ci_high, report.pairs[0].estimate)
        self.assertIn("simultaneous CI", format_posthoc_report(report))

    def test_games_howell_matches_scipy(self):
        report = self.run_test("welch")
        self.assertEqual(len(report.pairs), 3)
        self.assertEqual(report.method, "Games–Howell")
        samples = [
            self.data.loc[self.data.group == group, "score"].to_numpy()
            for group in ("A", "B", "C")
        ]
        reference = stats.tukey_hsd(*samples, equal_var=False)
        self.assertAlmostEqual(
            report.pairs[1].p_adjusted, reference.pvalue[0, 2], places=10
        )
        self.assertIn("Games", format_posthoc_report(report))

    def test_dunn_holm_corrects_all_pairs_and_ties(self):
        report = self.run_test("kruskal")
        self.assertEqual(report.method, "Dunn–Holm")
        self.assertEqual(len(report.pairs), 3)
        for pair in report.pairs:
            self.assertGreaterEqual(pair.p_adjusted, pair.p_raw)
            self.assertLessEqual(pair.p_adjusted, 1.0)
            self.assertIsNone(pair.ci_low)
            self.assertIsNotNone(pair.statistic)
        self.assertLess(report.pairs[1].p_adjusted, 0.05)
        self.assertIn("Holm", format_posthoc_report(report))
        self.assertTrue(any("tie correction" in s for s in report.warnings))

    def test_non_significant_omnibus_warns_exploratory(self):
        flat = self.data.copy()
        pattern = [2, 3, 4, 5] * 3
        for group in ("A", "B", "C"):
            flat.loc[flat.group == group, "score"] = pattern
        omnibus = analyze_omnibus(
            flat, "group", "score", "kruskal", "ordinal", True, True
        )
        report = analyze_posthoc(omnibus)
        self.assertTrue(any("exploratory" in s for s in report.warnings))
        self.assertTrue(all(p.p_adjusted > 0.05 for p in report.pairs))


if __name__ == "__main__":
    unittest.main()
