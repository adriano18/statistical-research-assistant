"""Compare binary logistic estimates with independent statsmodels references."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm

from logistic_analysis import binary_logistic_regression
from logistic_reporting import (
    format_logistic_report, logistic_main, logistic_brief
)
from logistic_charts import make_logistic_chart


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_logistic.csv"


class LogisticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(EXAMPLE)

    def fit_example(self, predictors):
        return binary_logistic_regression(
            self.data, "wellbeing_improved", predictors, True
        )

    def test_single_predictor_matches_statsmodels(self):
        result = self.fit_example(["sleep_hours"])
        complete = self.data[["wellbeing_improved", "sleep_hours"]].dropna()
        reference = sm.Logit(
            complete["wellbeing_improved"],
            sm.add_constant(complete[["sleep_hours"]]),
        ).fit(disp=False)
        self.assertEqual(result.n_total, 210)
        self.assertEqual(result.n_complete, 209)
        self.assertAlmostEqual(
            result.coefficients[1].b, float(reference.params.iloc[1]), places=9
        )
        self.assertAlmostEqual(result.llr, float(reference.llr), places=9)
        self.assertAlmostEqual(
            result.mcfadden_r2, float(reference.prsquared), places=9
        )
        self.assertAlmostEqual(
            result.coefficients[1].odds_ratio,
            float(np.exp(reference.params.iloc[1])), places=9
        )

    def test_multiple_predictors_odds_ratio_ci_and_auc(self):
        predictors = ["sleep_hours", "activity_hours"]
        result = self.fit_example(predictors)
        complete = self.data[["wellbeing_improved", *predictors]].dropna()
        ref = sm.Logit(
            complete["wellbeing_improved"],
            sm.add_constant(complete[predictors]),
        ).fit(disp=False)
        self.assertEqual(result.n_complete, 208)
        self.assertEqual(result.events + result.non_events, 208)
        self.assertEqual(len(result.coefficients), 3)
        self.assertAlmostEqual(result.llr_p, float(ref.llr_pvalue), places=9)
        self.assertAlmostEqual(result.aic, float(ref.aic), places=9)
        for index, c in enumerate(result.coefficients):
            self.assertAlmostEqual(c.b, float(ref.params.iloc[index]), places=9)
            self.assertAlmostEqual(c.se, float(ref.bse.iloc[index]), places=9)
            self.assertAlmostEqual(c.odds_ratio, np.exp(c.b), places=9)
            self.assertLess(c.or_low, c.odds_ratio)
            self.assertGreater(c.or_high, c.odds_ratio)
            self.assertTrue(0 <= c.p <= 1)
        ranks = stats.rankdata(result.probabilities, method="average")
        auc = (
            np.sum(ranks[result.actual == 1]) -
            result.events * (result.events + 1) / 2
        ) / (result.events * result.non_events)
        self.assertAlmostEqual(result.roc_auc, auc, places=10)
        self.assertGreater(result.roc_auc, 0.5)
        self.assertLessEqual(result.roc_auc, 1)
        self.assertIn("McFadden", logistic_main(result))
        self.assertIn("OR", format_logistic_report(result))
        self.assertIn("in-sample", logistic_brief(result))

    def test_report_and_diagnostic_figure(self):
        result = self.fit_example(["sleep_hours", "activity_hours"])
        report = format_logistic_report(result)
        png = make_logistic_chart(result)
        self.assertIn("likelihood", report.lower())
        self.assertIn("Wald", report)
        self.assertIn("risk ratio", report.lower())
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 5000)

    def test_confirmation_and_identifier_guards(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            binary_logistic_regression(
                self.data, "wellbeing_improved", ["sleep_hours"]
            )
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            binary_logistic_regression(
                self.data, "wellbeing_improved", ["participant_id"], True
            )
        with self.assertRaisesRegex(ValueError, "one and five"):
            binary_logistic_regression(
                self.data, "wellbeing_improved", [], True
            )
        with self.assertRaisesRegex(ValueError, "cannot also"):
            binary_logistic_regression(
                self.data, "wellbeing_improved", ["wellbeing_improved"], True
            )

    def test_only_01_outcome_is_accepted(self):
        changed = self.data.copy()
        changed.loc[0, "wellbeing_improved"] = 2
        with self.assertRaisesRegex(ValueError, "only 0 and 1"):
            binary_logistic_regression(
                changed, "wellbeing_improved", ["sleep_hours"], True
            )
        changed = self.data.copy()
        changed["wellbeing_improved"] = 1
        with self.assertRaisesRegex(ValueError, "both classes"):
            binary_logistic_regression(
                changed, "wellbeing_improved", ["sleep_hours"], True
            )

    def test_non_numeric_and_collinear_variables_rejected(self):
        changed = self.data.copy()
        changed["sleep_hours"] = changed["sleep_hours"].astype(object)
        changed.loc[0, "sleep_hours"] = "invalid"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            binary_logistic_regression(
                changed, "wellbeing_improved", ["sleep_hours"], True
            )
        changed = self.data.copy()
        changed["double_sleep"] = changed["sleep_hours"] * 2
        with self.assertRaisesRegex(ValueError, "collinear"):
            binary_logistic_regression(
                changed, "wellbeing_improved",
                ["sleep_hours", "double_sleep"], True
            )

    def test_separation_rejected_instead_of_reporting_bad_coefficients(self):
        n = 80
        separated = pd.DataFrame({
            "improved": [0] * 40 + [1] * 40,
            "score": list(np.linspace(0, 1, 40)) +
                     list(np.linspace(2, 3, 40)),
        })
        with self.assertRaisesRegex(ValueError, "Perfect separation"):
            binary_logistic_regression(
                separated, "improved", ["score"], True
            )

    def test_rare_event_and_small_dataset_guards(self):
        small = self.data.head(25)
        with self.assertRaisesRegex(ValueError, "Not enough complete"):
            binary_logistic_regression(
                small, "wellbeing_improved", ["sleep_hours"], True
            )
        rare = self.data.copy()
        rare["wellbeing_improved"] = [1] * 4 + [0] * 206
        with self.assertRaisesRegex(ValueError, "Too few"):
            binary_logistic_regression(
                rare, "wellbeing_improved", ["sleep_hours"], True
            )

    def test_missing_rows_excluded_and_no_source_mutation(self):
        before = self.data.copy(deep=True)
        result = self.fit_example(["sleep_hours", "activity_hours"])
        self.assertEqual(result.n_total - result.n_complete, 2)
        self.assertTrue(any("Excluded 2" in note for note in result.warnings))
        pd.testing.assert_frame_equal(self.data, before)


if __name__ == "__main__":
    unittest.main()
