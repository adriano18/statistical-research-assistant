"""Offline tests for correlation decisions, reporting and PNG figures."""

import unittest

import pandas as pd

from correlation import analyze_correlation, recommend_method
from correlation_reporting import apa_p_value, format_correlation_report
from correlation_charts import make_correlation_chart


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "respondent_id": list(range(1, 9)),
            "age": [22, 25, 29, 31, 34, 38, 41, 45],
            "score": [3, 4, 5, 7, 8, 8, 10, 12],
            "ordinal": [1, 1, 2, 2, 3, 4, 4, 5],
            "group": ["A", "B"] * 4,
        })

    def test_method_advice_respects_scales(self):
        self.assertIn("Pearson", recommend_method("scale", "scale"))
        self.assertIn("Spearman", recommend_method("ordinal", "scale"))
        self.assertIn("Confirm", recommend_method("nominal", "scale"))

    def test_pearson_with_confidence_interval(self):
        res = analyze_correlation(
            self.df, "age", "score", "pearson", "scale", "scale", True
        )
        self.assertEqual(res.n_complete, 8)
        self.assertGreater(res.coefficient, 0.9)
        self.assertLessEqual(res.ci_low, res.coefficient)
        self.assertGreaterEqual(res.ci_high, res.coefficient)
        self.assertLess(res.p_value, 0.05)
        self.assertIn("Pearson", format_correlation_report(res))

    def test_spearman_ordinal_uses_permutation(self):
        res = analyze_correlation(
            self.df, "ordinal", "score",
            "spearman", "ordinal", "scale",
        )
        self.assertGreater(res.coefficient, 0)
        self.assertTrue(0 <= res.p_value <= 1)
        self.assertIn("permutation", res.p_method)
        self.assertIsNone(res.ci_low)
        self.assertIn("No confidence interval", format_correlation_report(res))

    def test_paired_missing_data_excluded(self):
        df = self.df.copy()
        df.loc[0, "score"] = float("nan")
        res = analyze_correlation(df, "age", "score", "pearson", "scale", "scale", True)
        self.assertEqual(res.n_complete, 7)
        self.assertTrue(any("excluded" in text for text in res.warnings))

    def test_pearson_assumptions_are_required(self):
        with self.assertRaisesRegex(ValueError, "Confirm the Pearson"):
            analyze_correlation(self.df, "age", "score", "pearson", "scale", "scale")

    def test_pearson_refuses_ordinal_scale(self):
        with self.assertRaisesRegex(ValueError, "both variables"):
            analyze_correlation(self.df, "ordinal", "score",
                                "pearson", "ordinal", "scale", True)

    def test_nominal_is_not_correlation_scale(self):
        with self.assertRaisesRegex(ValueError, "ordinal or quantitative"):
            analyze_correlation(self.df, "group", "score",
                                "spearman", "nominal", "scale")

    def test_identifiers_and_equal_variables_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_correlation(self.df, "respondent_id", "score",
                                "spearman", "scale", "scale")
        with self.assertRaisesRegex(ValueError, "different"):
            analyze_correlation(self.df, "age", "age",
                                "spearman", "scale", "scale")

    def test_non_numeric_and_constant_variables_rejected(self):
        df = self.df.copy()
        df["score"] = df["score"].astype(object)
        df.loc[0, "score"] = "invalid"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_correlation(df, "age", "score", "spearman", "scale", "scale")
        df = self.df.copy()
        df["score"] = 2
        with self.assertRaisesRegex(ValueError, "variation"):
            analyze_correlation(df, "age", "score", "spearman", "scale", "scale")

    def test_apa_p_value(self):
        self.assertEqual(apa_p_value(0.0004), "p < .001")
        self.assertEqual(apa_p_value(0.031), "p = .031")
        self.assertEqual(apa_p_value(0.5), "p = .500")

    def test_scatterplot_png(self):
        res = analyze_correlation(
            self.df, "age", "score", "pearson", "scale", "scale", True
        )
        png = make_correlation_chart(res)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 2500)


if __name__ == "__main__":
    unittest.main()
