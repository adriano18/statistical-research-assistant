"""Offline reference tests for ANOVA, Welch and Kruskal–Wallis."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from omnibus_analysis import analyze_omnibus, recommend_omnibus_test
from omnibus_reporting import (
    format_omnibus_report, format_omnibus_summary, interpret_omnibus
)
from omnibus_charts import make_omnibus_chart


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_three_groups.csv"


class OmnibusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(SAMPLE)

    def run_method(self, method, scale="scale"):
        return analyze_omnibus(
            self.df, "group", "score",
            method, scale, True, True
        )

    def test_classical_anova_reference_statistic(self):
        result = self.run_method("anova")
        self.assertEqual((result.n_total, result.n_complete), (36, 36))
        self.assertEqual(result.labels, ["A", "B", "C"])
        self.assertEqual(result.df1, 2)
        self.assertEqual(result.df2, 33)
        self.assertAlmostEqual(result.statistic, 69.5086206897, places=5)
        self.assertLess(result.p_value, 0.001)
        self.assertGreater(result.effect_size, 0)
        self.assertLess(result.effect_size, 1)
        self.assertIn("F(2, 33)", format_omnibus_summary(result))

    def test_welch_anova_reference(self):
        result = self.run_method("welch")
        self.assertAlmostEqual(result.statistic, 61.8035940925, places=5)
        self.assertAlmostEqual(result.df2, 21.8217399837, places=5)
        self.assertLess(result.p_value, 0.001)
        self.assertIn("Welch", format_omnibus_report(result))
        self.assertIn("descriptive", "\n".join(result.warnings))

    def test_kruskal_reference_and_reporting(self):
        result = self.run_method("kruskal", "ordinal")
        self.assertAlmostEqual(result.statistic, 28.7231077432, places=5)
        self.assertLess(result.p_value, 0.001)
        self.assertEqual(result.df1, 2)
        self.assertIsNone(result.df2)
        self.assertGreater(result.effect_size, 0)
        self.assertIn("H(2)", format_omnibus_summary(result))
        self.assertIn("post-hoc", interpret_omnibus(result).lower())

    def test_requires_design_and_assumption_confirmation(self):
        with self.assertRaisesRegex(ValueError, "independent"):
            analyze_omnibus(self.df, "group", "score", "anova", "scale")
        with self.assertRaisesRegex(ValueError, "assumptions"):
            analyze_omnibus(
                self.df, "group", "score", "kruskal", "ordinal", True, False
            )

    def test_ordinal_rejected_by_anova_and_suitable_advice(self):
        with self.assertRaisesRegex(ValueError, "quantitative"):
            self.run_method("anova", "ordinal")
        self.assertIn("Kruskal", recommend_omnibus_test("ordinal", True))
        self.assertIn("Welch", recommend_omnibus_test("scale", True))
        self.assertIn("independent", recommend_omnibus_test("scale", False))

    def test_missing_outcome_rows_are_excluded(self):
        df = self.df.copy()
        df.loc[0, "score"] = float("nan")
        result = analyze_omnibus(
            df, "group", "score", "kruskal", "ordinal", True, True
        )
        self.assertEqual(result.n_complete, 35)
        self.assertTrue(any("Excluded 1" in msg for msg in result.warnings))

    def test_reject_invalid_group_counts_and_identifiers(self):
        df = self.df.copy()
        df["id"] = range(1, 37)
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_omnibus(df, "id", "score", "anova", "scale", True, True)
        df["single_group"] = "only one"
        with self.assertRaisesRegex(ValueError, "3 to 8"):
            analyze_omnibus(
                df, "single_group", "score", "anova", "scale", True, True
            )
        df["small"] = ["A"] * 2 + ["B"] * 17 + ["C"] * 17
        with self.assertRaisesRegex(ValueError, "five"):
            analyze_omnibus(df, "small", "score", "anova", "scale", True, True)
        # Stage 36 (spec §6): Kruskal–Wallis ranks a group of two; its p-value
        # is then a permutation estimate, and the small group is named.
        result = analyze_omnibus(df, "small", "score", "kruskal", "ordinal", True, True)
        self.assertIn("permutation", result.p_method)
        self.assertIsNotNone(result.p_asymptotic)
        self.assertTrue(any("A (2)" in w for w in result.warnings))
        df["tiny"] = ["A"] * 1 + ["B"] * 18 + ["C"] * 17
        with self.assertRaisesRegex(ValueError, "At least 2"):
            analyze_omnibus(df, "tiny", "score", "kruskal", "ordinal", True, True)

    def test_invalid_values_and_constant_groups(self):
        df = self.df.copy()
        df["score"] = df["score"].astype(object)
        df.loc[0, "score"] = "not numeric"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_omnibus(df, "group", "score", "welch", "scale", True, True)
        df = self.df.copy()
        df.loc[df["group"] == "A", "score"] = 3
        with self.assertRaisesRegex(ValueError, "nonzero"):
            analyze_omnibus(df, "group", "score", "welch", "scale", True, True)

    def test_figure_png_and_non_significant_wording(self):
        result = self.run_method("kruskal", "ordinal")
        png = make_omnibus_chart(result)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 2000)
        flat = self.df.copy()
        pattern = [2, 3, 4, 5] * 3
        for group in ("A", "B", "C"):
            flat.loc[flat["group"] == group, "score"] = pattern
        comparison = analyze_omnibus(
            flat, "group", "score", "kruskal", "ordinal", True, True
        )
        self.assertGreater(comparison.p_value, 0.05)
        self.assertIn("no statistically significant", interpret_omnibus(comparison).lower())


if __name__ == "__main__":
    unittest.main()
