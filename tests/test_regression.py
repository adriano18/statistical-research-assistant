"""Cross-check linear and multiple regression against statsmodels reference fits."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
import statsmodels.api as sm

from regression_analysis import analyze_regression
from regression_reporting import format_regression_report, regression_brief
from regression_charts import make_regression_chart


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_regression.csv"


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(EXAMPLE)

    def test_simple_matches_ols(self):
        result = analyze_regression(
            self.df, "stress_score", ["study_hours"], True
        )
        ref = sm.OLS(
            self.df["stress_score"],
            sm.add_constant(self.df[["study_hours"]]),
        ).fit()
        self.assertEqual(result.n_complete, 48)
        self.assertEqual(result.model_df, 1)
        self.assertEqual(len(result.coefficients), 2)
        self.assertAlmostEqual(result.r_squared, ref.rsquared, places=10)
        self.assertAlmostEqual(
            result.coefficients[1].b, ref.params["study_hours"], places=10
        )
        self.assertIsNone(result.coefficients[1].vif)
        self.assertIn("Simple", format_regression_report(result))

    def test_multiple_hc3_and_vif(self):
        result = analyze_regression(
            self.df, "stress_score", ["study_hours", "sleep_hours"],
            True, True,
        )
        ref = sm.OLS(
            self.df["stress_score"],
            sm.add_constant(self.df[["study_hours", "sleep_hours"]]),
        ).fit().get_robustcov_results(cov_type="HC3", use_t=True)
        self.assertEqual(result.model_df, 2)
        self.assertEqual(result.residual_df, 45)
        self.assertTrue(result.robust_hc3)
        for i, coef in enumerate(result.coefficients):
            self.assertAlmostEqual(coef.b, ref.params[i], places=10)
            self.assertAlmostEqual(coef.se, ref.bse[i], places=10)
            self.assertLess(coef.ci_low, coef.b)
            self.assertGreater(coef.ci_high, coef.b)
        self.assertGreaterEqual(result.coefficients[1].vif, 1)
        self.assertIn("HC3", format_regression_report(result))
        self.assertIn("explains", regression_brief(result))

    def test_missing_values_are_excluded(self):
        df = self.df.copy()
        df.loc[0, "stress_score"] = np.nan
        result = analyze_regression(
            df, "stress_score", ["study_hours", "sleep_hours"], True
        )
        self.assertEqual(result.n_complete, 47)
        self.assertTrue(any("Excluded 1" in msg for msg in result.warnings))

    def test_requires_confirmation_and_numeric_scales(self):
        with self.assertRaisesRegex(ValueError, "Review independence"):
            analyze_regression(self.df, "stress_score", ["study_hours"])
        with self.assertRaisesRegex(ValueError, "one and five"):
            analyze_regression(self.df, "stress_score", [], True)
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_regression(self.df, "stress_score", ["participant_id"], True)

    def test_reject_perfect_collinearity_and_invalid_text(self):
        df = self.df.copy()
        df["duplicate_hours"] = df["study_hours"] * 2
        with self.assertRaisesRegex(ValueError, "collinear"):
            analyze_regression(
                df, "stress_score", ["study_hours", "duplicate_hours"], True
            )
        df = self.df.copy()
        df["sleep_hours"] = df["sleep_hours"].astype(object)
        df.loc[0, "sleep_hours"] = "not numeric"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_regression(
                df, "stress_score", ["study_hours", "sleep_hours"], True
            )

    def test_reject_too_few_cases_and_nonvaried_predictors(self):
        with self.assertRaisesRegex(ValueError, "Not enough complete"):
            analyze_regression(
                self.df.head(10), "stress_score", ["study_hours"], True
            )
        df = self.df.copy()
        df["study_hours"] = 1
        with self.assertRaisesRegex(ValueError, "variation"):
            analyze_regression(df, "stress_score", ["study_hours"], True)

    def test_diagnostic_png(self):
        result = analyze_regression(
            self.df, "stress_score", ["study_hours", "sleep_hours"], True
        )
        figure = make_regression_chart(result)
        self.assertTrue(figure.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(figure), 3000)


if __name__ == "__main__":
    unittest.main()
