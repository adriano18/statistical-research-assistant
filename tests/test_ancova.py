"""Reference checks for ANCOVA and Gaussian interaction GLM.

Independent cross-checks use statsmodels' formula interface, which builds
design matrices differently from the application's explicit numpy matrices.
"""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm

from ancova_analysis import analyze_ancova
from ancova_reporting import ancova_main, ancova_brief, format_ancova_report
from ancova_charts import make_ancova_chart


ROOT = Path(__file__).resolve().parents[1] / "examples"
SAMPLE = ROOT / "sample_ancova.csv"
INTERACTION_SAMPLE = ROOT / "sample_ancova_interaction.csv"


class AncovaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(SAMPLE)
        cls.interactive = pd.read_csv(INTERACTION_SAMPLE)
        cls.covs = ["age", "baseline_score"]

    def analyze(self, df=None, mode="ancova"):
        return analyze_ancova(
            self.data if df is None else df,
            "wellbeing", "group", self.covs,
            mode=mode, assumptions_confirmed=True,
        )

    def test_ancova_group_f_matches_formula_reference(self):
        result = self.analyze()
        reference = smf.ols(
            "wellbeing ~ C(group) + age + baseline_score",
            data=self.data.dropna(),
        ).fit()
        anova = anova_lm(reference, typ=2)
        self.assertEqual(result.n_total, 180)
        self.assertEqual(result.n_complete, 179)
        self.assertEqual(result.df_group, 2)
        self.assertAlmostEqual(result.f_group, float(anova.loc["C(group)", "F"]), places=8)
        self.assertAlmostEqual(result.p_group, float(anova.loc["C(group)", "PR(>F)"]), places=10)
        self.assertAlmostEqual(result.r_squared, float(reference.rsquared), places=10)
        self.assertTrue(0 <= result.eta_squared_partial <= 1)
        self.assertLess(result.p_group, .05)
        self.assertIn("ANCOVA", ancova_main(result))

    def test_adjusted_means_and_pair_differences(self):
        result = self.analyze()
        self.assertEqual(len(result.groups), 3)
        self.assertEqual([g.label for g in result.groups], ["A", "B", "C"])
        self.assertEqual(sum(g.n for g in result.groups), 179)
        self.assertEqual(len(result.pairs), 3)
        self.assertTrue(all(g.ci_low < g.adjusted_mean < g.ci_high for g in result.groups))
        self.assertAlmostEqual(
            result.pairs[0].difference,
            result.groups[1].adjusted_mean - result.groups[0].adjusted_mean,
            places=10,
        )
        self.assertTrue(all(p.p_holm >= p.p_raw - 1e-12 for p in result.pairs))
        self.assertIn("Holm-adjusted", format_ancova_report(result))
        self.assertIn("difference", ancova_brief(result).lower())

    def test_nonparallel_slopes_block_standard_ancova(self):
        with self.assertRaisesRegex(ValueError, "interaction detected"):
            self.analyze(self.interactive, mode="ancova")

    def test_interaction_glm_matches_centered_formula(self):
        result = self.analyze(self.interactive, mode="interaction")
        df = self.interactive.dropna().copy()
        df["age_c"] = df.age - df.age.mean()
        df["base_c"] = df.baseline_score - df.baseline_score.mean()
        formula = "wellbeing ~ C(group) * (age_c + base_c)"
        reference = smf.ols(formula, data=df).fit()
        additive = smf.ols(
            "wellbeing ~ C(group) + age_c + base_c", data=df
        ).fit()
        group_test = reference.f_test(
            "C(group)[T.B] = 0, C(group)[T.C] = 0"
        )
        self.assertAlmostEqual(
            result.f_group, float(np.asarray(group_test.fvalue).item()),
            places=8,
        )
        self.assertAlmostEqual(
            result.p_group, float(np.asarray(group_test.pvalue).item()),
            places=9,
        )
        self.assertAlmostEqual(
            result.f_interaction, float(reference.compare_f_test(additive)[0]),
            places=8,
        )
        self.assertLess(result.p_interaction, .05)
        self.assertIn("CONDITIONAL", ancova_brief(result))
        self.assertEqual(result.df_interaction, 4)
        self.assertAlmostEqual(result.r_squared, reference.rsquared, places=10)

    def test_sample_missingness_and_source_not_mutated(self):
        prior = self.data.copy(deep=True)
        result = self.analyze()
        self.assertTrue(any("excluded" in msg.lower() for msg in result.warnings))
        pd.testing.assert_frame_equal(self.data, prior)

    def test_requires_independence_and_rejects_identifiers(self):
        with self.assertRaisesRegex(ValueError, "Confirm independent"):
            analyze_ancova(
                self.data, "wellbeing", "group", self.covs,
            )
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_ancova(
                self.data, "wellbeing", "participant_id", self.covs,
                assumptions_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "different variables"):
            analyze_ancova(
                self.data, "wellbeing", "group",
                ["wellbeing"], assumptions_confirmed=True,
            )

    def test_invalid_numeric_data_and_low_n(self):
        bad = self.data.copy()
        bad["age"] = bad["age"].astype(object)
        bad.loc[0, "age"] = "not a number"
        with self.assertRaisesRegex(ValueError, "quantitative numeric"):
            self.analyze(bad)
        with self.assertRaisesRegex(ValueError, "eight complete"):
            self.analyze(self.data.iloc[:64].copy())
        with self.assertRaisesRegex(ValueError, "one to three"):
            analyze_ancova(
                self.data, "wellbeing", "group", [],
                assumptions_confirmed=True,
            )

    def test_rank_deficient_and_no_factor_rejected(self):
        bad = self.data.copy()
        bad["twice_age"] = bad["age"] * 2
        with self.assertRaisesRegex(ValueError, "rank deficient"):
            analyze_ancova(
                bad, "wellbeing", "group",
                ["age", "twice_age"], assumptions_confirmed=True,
            )
        bad = self.data.copy()
        bad["group"] = "A"
        with self.assertRaisesRegex(ValueError, "2–6"):
            self.analyze(bad)

    def test_figure_png(self):
        result = self.analyze()
        figure = make_ancova_chart(result)
        self.assertTrue(figure.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(figure), 4000)


if __name__ == "__main__":
    unittest.main()
