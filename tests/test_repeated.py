"""Independent reference checks for Friedman and repeated-measures ANOVA."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
import pingouin as pg
from scipy import stats

from repeated_analysis import analyze_repeated
from repeated_reporting import repeated_main, format_repeated_report
from repeated_charts import make_repeated_chart


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_repeated.csv"
COLS = ["stress_before", "stress_mid", "stress_after"]


class RepeatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(SAMPLE)

    def run_method(self, method, scale):
        return analyze_repeated(
            self.df, COLS, method, scale, True, True
        )

    def test_friedman_matches_scipy(self):
        result = self.run_method("friedman", "ordinal")
        data = self.df[COLS].dropna()
        ref = stats.friedmanchisquare(*[data[c].to_numpy() for c in COLS])
        self.assertEqual(result.n_complete, 31)
        self.assertAlmostEqual(result.statistic, float(ref.statistic), places=9)
        self.assertAlmostEqual(result.p_primary, float(ref.pvalue), places=10)
        self.assertAlmostEqual(
            result.effect_size, result.statistic / (31 * 2), places=10
        )
        self.assertIn("Kendall", repeated_main(result))

    def test_repeated_anova_matches_pingouin(self):
        result = self.run_method("rm_anova", "scale")
        wide = self.df[COLS].dropna()
        ref = pg.rm_anova(data=wide, detailed=True, correction=True)
        self.assertAlmostEqual(result.statistic, float(ref.iloc[0]["F"]), places=7)
        self.assertAlmostEqual(
            result.p_uncorrected, float(ref.iloc[0]["p-unc"]), places=9
        )
        self.assertAlmostEqual(
            result.epsilon_gg, float(ref.iloc[0]["eps"]), places=7
        )
        self.assertTrue(0.5 <= result.epsilon_gg <= 1)
        self.assertGreaterEqual(result.p_primary, result.p_uncorrected - 1e-12)
        self.assertAlmostEqual(result.df2, 60)
        self.assertIn("Greenhouse", repeated_main(result))

    def test_all_pairwise_pvalues_holm_adjusted(self):
        for method, scale in (("friedman", "ordinal"), ("rm_anova", "scale")):
            result = self.run_method(method, scale)
            self.assertEqual(len(result.pairs), 3)
            for pair in result.pairs:
                self.assertGreaterEqual(pair.p_holm, pair.p_raw - 1e-12)
                self.assertLessEqual(pair.p_holm, 1)
            self.assertIn("Holm-adjusted", format_repeated_report(result))
            self.assertTrue(any("Holm" in note for note in result.warnings))

    def test_missing_values_excluded_listwise(self):
        result = self.run_method("friedman", "ordinal")
        self.assertEqual(result.n_total - result.n_complete, 1)
        self.assertTrue(any("excluded" in s.lower() for s in result.warnings))

    def test_confirmations_and_measurement_scale_guarded(self):
        with self.assertRaisesRegex(ValueError, "SAME"):
            analyze_repeated(self.df, COLS, "friedman", "ordinal")
        with self.assertRaisesRegex(ValueError, "assumptions"):
            analyze_repeated(self.df, COLS, "friedman", "ordinal", True)
        with self.assertRaisesRegex(ValueError, "quantitative"):
            analyze_repeated(self.df, COLS, "rm_anova", "ordinal", True, True)

    def test_duplicate_or_identifier_columns(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            analyze_repeated(
                self.df, [COLS[0], COLS[0], COLS[1]], "friedman", "ordinal", True, True
            )
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_repeated(
                self.df, ["participant_id", *COLS], "friedman", "ordinal", True, True
            )

    def test_non_numeric_or_too_few_participants_rejected(self):
        data = self.df.copy()
        data["stress_mid"] = data["stress_mid"].astype(object)
        data.loc[0, "stress_mid"] = "invalid"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_repeated(data, COLS, "friedman", "ordinal", True, True)
        with self.assertRaisesRegex(ValueError, "eight"):
            analyze_repeated(
                self.df.head(5), COLS, "rm_anova", "scale", True, True
            )

    def test_no_variation_rejected(self):
        data = self.df.copy()
        data[COLS] = 3
        with self.assertRaisesRegex(ValueError, "no variation"):
            analyze_repeated(data, COLS, "friedman", "ordinal", True, True)

    def test_png_chart(self):
        result = self.run_method("friedman", "ordinal")
        image = make_repeated_chart(result)
        self.assertTrue(image.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(image), 3000)


if __name__ == "__main__":
    unittest.main()
