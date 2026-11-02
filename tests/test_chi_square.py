"""Chi-square independence, Fisher fallback and APA-style figure tests."""

from pathlib import Path
import unittest

import pandas as pd

from chi_square import analyze_chi_square
from chi_square_reporting import (
    format_chi_square_report, summarize_chi_square, interpret_chi_square
)
from chi_square_charts import make_chi_square_chart


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_categorical.csv"


class ChiSquareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(SAMPLE)

    def test_2x2_independence_and_effect(self):
        res = analyze_chi_square(self.data, "group", "outcome", True)
        self.assertEqual(res.observed.shape, (2, 2))
        self.assertEqual(res.df, 1)
        self.assertEqual(res.n_complete, 40)
        self.assertAlmostEqual(res.chi2, 6.66666667, places=5)
        self.assertLess(res.p_value, 0.05)
        self.assertAlmostEqual(res.cramers_v, 0.40824829, places=5)
        self.assertFalse(res.sparse)
        self.assertIsNone(res.fisher_p)
        self.assertIn("χ²", format_chi_square_report(res))
        self.assertIn("association", interpret_chi_square(res))
        self.assertIn("Cramér", summarize_chi_square(res))

    def test_small_expected_counts_offer_fisher_2x2(self):
        data = pd.DataFrame({
            "group": ["A"] * 8 + ["B"] * 8,
            "answer": ["Yes"] * 7 + ["No"] + ["Yes"] + ["No"] * 7,
        })
        res = analyze_chi_square(data, "group", "answer", True)
        self.assertTrue(res.sparse)
        self.assertIsNotNone(res.fisher_p)
        self.assertTrue(any("below 5" in w for w in res.warnings))
        self.assertIn("Fisher", format_chi_square_report(res))

    def test_more_categories_without_fisher(self):
        df = pd.DataFrame({
            "q1": ["a"] * 10 + ["b"] * 10 + ["c"] * 10,
            "q2": ["x", "y"] * 15,
        })
        res = analyze_chi_square(df, "q1", "q2", True)
        self.assertEqual(res.observed.shape, (3, 2))
        self.assertEqual(res.df, 2)
        self.assertIsNone(res.fisher_p)

    def test_missing_values_excluded(self):
        df = self.data.copy()
        df.loc[0, "group"] = None
        res = analyze_chi_square(df, "group", "outcome", True)
        self.assertEqual(res.n_complete, 39)
        self.assertTrue(any("Excluded 1" in w for w in res.warnings))

    def test_confirmation_and_wrong_variables(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            analyze_chi_square(self.data, "group", "outcome")
        with self.assertRaisesRegex(ValueError, "different"):
            analyze_chi_square(self.data, "group", "group", True)
        df = self.data.copy()
        df["participant_id"] = range(1, len(df)+1)
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_chi_square(df, "participant_id", "group", True)

    def test_reject_one_category_or_too_few_rows(self):
        df = self.data.copy()
        df["only"] = "one"
        with self.assertRaisesRegex(ValueError, "2 to 10"):
            analyze_chi_square(df, "group", "only", True)
        with self.assertRaisesRegex(ValueError, "ten"):
            analyze_chi_square(df.iloc[:6], "group", "outcome", True)

    def test_figure_png(self):
        res = analyze_chi_square(self.data, "group", "outcome", True)
        image = make_chi_square_chart(res)
        self.assertTrue(image.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(image), 3000)


if __name__ == "__main__":
    unittest.main()
