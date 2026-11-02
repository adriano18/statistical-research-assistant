"""Offline tests for two-independent-group comparisons and APA-style output."""

import unittest

import pandas as pd

from group_comparison import compare_independent_groups, recommend_group_test
from group_comparison_reporting import format_group_comparison
from group_comparison_charts import make_group_comparison_chart


class GroupComparisonTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "respondent_id": range(1, 19),
            "group": ["A"] * 9 + ["B"] * 9,
            "score": [
                12, 10, 9, 11, 8, 9, 12, 10, 11,
                5, 6, 7, 8, 9, 6, 5, 7, 8,
            ],
            "ordinal": [
                5, 5, 4, 4, 3, 5, 4, 4, 5,
                2, 1, 2, 3, 3, 1, 2, 3, 2,
            ],
        })

    def test_welch_estimate_ci_and_apa_output(self):
        result = compare_independent_groups(
            self.df, "group", "score", "welch", "scale", True, True
        )
        self.assertEqual((result.group_a, result.group_b), ("A", "B"))
        self.assertEqual((result.n_a, result.n_b), (9, 9))
        self.assertGreater(result.statistic, 0)
        self.assertLess(result.p_value, 0.05)
        self.assertGreater(result.effect_size, 0)
        self.assertLess(result.ci_low, result.mean_difference)
        self.assertGreater(result.ci_high, result.mean_difference)
        self.assertIn("Welch’s", format_group_comparison(result))
        self.assertIn("95% CI [", format_group_comparison(result))

    def test_mann_whitney_with_tied_responses(self):
        result = compare_independent_groups(
            self.df, "group", "ordinal", "mannwhitney", "ordinal", True
        )
        self.assertEqual((result.n_a, result.n_b), (9, 9))
        self.assertLess(result.p_value, 0.05)
        self.assertGreater(result.effect_size, 0)
        self.assertIn("tie-corrected", result.p_method)
        self.assertIsNone(result.ci_low)
        self.assertIn("rank/distribution", format_group_comparison(result))

    def test_missing_rows_are_excluded_and_reported(self):
        df = self.df.copy()
        df.loc[0, "score"] = float("nan")
        df.loc[15, "group"] = None
        result = compare_independent_groups(
            df, "group", "score", "welch", "scale", True, True
        )
        self.assertEqual(result.n_a + result.n_b, len(df) - 2)
        self.assertTrue(any("Excluded 2" in text for text in result.warnings))

    def test_requires_independent_group_confirmation(self):
        with self.assertRaisesRegex(ValueError, "independent"):
            compare_independent_groups(
                self.df, "group", "score", "welch", "scale"
            )

    def test_welch_requires_quantitative_scale_and_check(self):
        with self.assertRaisesRegex(ValueError, "quantitative"):
            compare_independent_groups(
                self.df, "group", "ordinal", "welch", "ordinal", True, True
            )
        with self.assertRaisesRegex(ValueError, "outliers"):
            compare_independent_groups(
                self.df, "group", "score", "welch", "scale", True
            )

    def test_ordinal_method_advice(self):
        self.assertIn("Mann–Whitney", recommend_group_test("ordinal", True))
        self.assertIn("Welch", recommend_group_test("scale", True))
        self.assertIn("paired", recommend_group_test("scale", False).lower())

    def test_reject_identifiers_more_than_two_groups_and_small_samples(self):
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            compare_independent_groups(
                self.df, "respondent_id", "score", "welch", "scale", True, True
            )
        df = self.df.copy()
        df.loc[0, "group"] = "C"
        with self.assertRaisesRegex(ValueError, "Exactly two"):
            compare_independent_groups(
                df, "group", "ordinal", "mannwhitney", "ordinal", True
            )
        df = pd.DataFrame({
            "group": ["A", "A", "B", "B", "B"],
            "outcome": [1, 2, 3, 4, 5],
        })
        with self.assertRaisesRegex(ValueError, "three observations"):
            compare_independent_groups(
                df, "group", "outcome", "mannwhitney", "ordinal", True
            )

    def test_non_numeric_and_no_variation_rejected(self):
        df = self.df.copy()
        df["score"] = df["score"].astype(object)
        df.loc[0, "score"] = "invalid"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            compare_independent_groups(
                df, "group", "score", "welch", "scale", True, True
            )
        df = self.df.copy()
        df["score"] = 7
        with self.assertRaisesRegex(ValueError, "no variation"):
            compare_independent_groups(
                df, "group", "score", "mannwhitney", "ordinal", True
            )

    def test_png_group_boxplot(self):
        result = compare_independent_groups(
            self.df, "group", "ordinal", "mannwhitney", "ordinal", True
        )
        png = make_group_comparison_chart(result)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 2000)


if __name__ == "__main__":
    unittest.main()
