"""Offline tests for the first reliability analysis module."""

from pathlib import Path
import unittest

import pandas as pd

from reliability import analyze_cronbach


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_scale.csv"
ITEMS = ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]


class CronbachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(SAMPLE)

    def test_alpha_on_fictional_scale(self):
        result = analyze_cronbach(self.data, ITEMS)
        self.assertEqual(result.n_total, 32)
        self.assertEqual(result.n_complete, 30)
        self.assertGreater(result.alpha, 0.8)
        self.assertLess(result.alpha, 1.0)
        self.assertLessEqual(result.ci_low, result.alpha)
        self.assertGreaterEqual(result.ci_high, result.alpha)
        self.assertEqual(len(result.alpha_if_deleted), 4)

    def test_requires_three_items(self):
        with self.assertRaisesRegex(ValueError, "at least three"):
            analyze_cronbach(self.data, ITEMS[:2])

    def test_identifier_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_cronbach(self.data, ["participant_id", *ITEMS[:2]])

    def test_unknown_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            analyze_cronbach(self.data, ["wrong_name", *ITEMS[:2]])

    def test_non_numeric_item_is_rejected(self):
        df = self.data.copy()
        df.loc[0, "stress_q1"] = "missing_text"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_cronbach(df, ITEMS)

    def test_constant_item_is_rejected(self):
        df = self.data.copy()
        df["stress_q2"] = 3
        with self.assertRaisesRegex(ValueError, "no variation"):
            analyze_cronbach(df, ITEMS)


if __name__ == "__main__":
    unittest.main()
