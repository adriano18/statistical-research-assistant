"""Offline tests for paired t, Wilcoxon and individual-change graphs."""

from pathlib import Path
import unittest

import pandas as pd

from paired_analysis import analyze_paired, recommend_paired_test
from paired_reporting import format_paired_report
from paired_charts import make_paired_chart


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_paired.csv"


class PairedAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(SAMPLE)

    def test_paired_t_has_ci_effect_size_and_df(self):
        res = analyze_paired(
            self.df, "before_score", "after_score",
            "paired_t", "scale", True, True
        )
        self.assertEqual((res.n_total, res.n_complete), (24, 22))
        self.assertEqual(res.df, 21)
        self.assertLess(res.mean_change, 0)
        self.assertLess(res.p_value, 0.05)
        self.assertLess(res.ci_low, res.mean_change)
        self.assertGreater(res.ci_high, res.mean_change)
        self.assertLess(res.effect_size, 0)
        self.assertIn("Cohen’s dz", format_paired_report(res))

    def test_wilcoxon_reports_matched_rank_effect(self):
        res = analyze_paired(
            self.df, "before_score", "after_score",
            "wilcoxon", "ordinal", True, True
        )
        self.assertLess(res.p_value, 0.05)
        self.assertLess(res.effect_size, 0)
        self.assertGreater(res.n_unchanged, 0)
        self.assertIn("rank-biserial", format_paired_report(res))
        self.assertIsNone(res.ci_low)

    def test_pairing_confirmation_is_required(self):
        with self.assertRaisesRegex(ValueError, "same participant"):
            analyze_paired(
                self.df, "before_score", "after_score", "wilcoxon",
                "ordinal", False, True
            )

    def test_assumption_review_is_required(self):
        with self.assertRaisesRegex(ValueError, "assumptions"):
            analyze_paired(
                self.df, "before_score", "after_score", "paired_t",
                "scale", True, False
            )

    def test_paired_t_rejects_ordinal_scales(self):
        with self.assertRaisesRegex(ValueError, "quantitative"):
            analyze_paired(
                self.df, "before_score", "after_score", "paired_t",
                "ordinal", True, True
            )

    def test_invalid_variables(self):
        with self.assertRaisesRegex(ValueError, "different"):
            analyze_paired(self.df, "before_score", "before_score",
                           "wilcoxon", "ordinal", True, True)
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_paired(self.df, "participant_id", "after_score",
                           "wilcoxon", "ordinal", True, True)

    def test_all_zero_differences_are_rejected(self):
        data = self.df.copy()
        data["after_score"] = data["before_score"]
        with self.assertRaisesRegex(ValueError, "five nonzero"):
            analyze_paired(data, "before_score", "after_score",
                           "wilcoxon", "ordinal", True, True)

    def test_non_numeric_value_is_rejected(self):
        data = self.df.copy()
        data["before_score"] = data["before_score"].astype(object)
        data.loc[0, "before_score"] = "wrong"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_paired(data, "before_score", "after_score",
                           "wilcoxon", "ordinal", True, True)

    def test_method_advice(self):
        self.assertIn("Wilcoxon", recommend_paired_test("ordinal", True))
        self.assertIn("paired t", recommend_paired_test("scale", True))
        self.assertIn("SAME", recommend_paired_test("scale", False))

    def test_png_chart(self):
        res = analyze_paired(self.df, "before_score", "after_score",
                             "wilcoxon", "ordinal", True, True)
        png = make_paired_chart(res)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 2000)


if __name__ == "__main__":
    unittest.main()
