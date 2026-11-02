"""Offline checks for exploratory correlation matrices and their figure."""

import unittest

import numpy as np
import pandas as pd

from correlation_matrix import analyze_correlation_matrix
from correlation_matrix_charts import make_correlation_matrix_chart


class CorrelationMatrixTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({
            "participant_id": range(1, 9),
            "q1": [1, 2, 3, 4, 5, 6, 7, 8],
            "q2": [2, 4, 6, 8, 10, 12, 14, 16],
            "q3": [8, 7, 6, 5, 4, 3, 2, 1],
            "q4": [3, 3, 3, None, 4, 4, 4, 5],
            "group": ["A", "B"] * 4,
        })

    def test_pearson_symmetric_and_pairwise_counts(self):
        res = analyze_correlation_matrix(
            self.data, ["q1", "q2", "q3", "q4"],
            "pearson", scales_confirmed=True
        )
        np.testing.assert_allclose(res.coefficients, res.coefficients.T)
        np.testing.assert_array_equal(res.pair_counts, res.pair_counts.T)
        self.assertAlmostEqual(res.coefficients[0, 1], 1.0)
        self.assertAlmostEqual(res.coefficients[0, 2], -1.0)
        self.assertEqual(res.pair_counts[0, 1], 8)
        self.assertEqual(res.pair_counts[0, 3], 7)
        self.assertEqual(res.pair_counts[3, 3], 7)

    def test_spearman(self):
        res = analyze_correlation_matrix(
            self.data, ["q1", "q3"], "spearman", True
        )
        self.assertAlmostEqual(res.coefficients[0, 1], -1.0)
        self.assertTrue(any("No p-values" in msg for msg in res.warnings))

    def test_confirmation_required(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            analyze_correlation_matrix(self.data, ["q1", "q2"], "pearson")

    def test_ids_and_invalid_selections(self):
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_correlation_matrix(
                self.data, ["participant_id", "q1"], "spearman", True
            )
        with self.assertRaisesRegex(ValueError, "between two and eight"):
            analyze_correlation_matrix(self.data, ["q1"], "spearman", True)
        with self.assertRaisesRegex(ValueError, "only once"):
            analyze_correlation_matrix(self.data, ["q1", "q1"], "spearman", True)
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_correlation_matrix(self.data, ["q1", "group"], "spearman", True)

    def test_constant_or_insufficient_data_is_na(self):
        data = self.data.copy()
        data["constant"] = 1
        data["short"] = [1, 2, None, None, None, None, None, None]
        res = analyze_correlation_matrix(
            data, ["q1", "constant", "short"], "spearman", True
        )
        self.assertTrue(np.isnan(res.coefficients[0, 1]))
        self.assertTrue(np.isnan(res.coefficients[0, 2]))
        self.assertEqual(res.pair_counts[0, 2], 2)
        self.assertTrue(any("N/A" in msg for msg in res.warnings))

    def test_matrix_chart_png(self):
        res = analyze_correlation_matrix(
            self.data, ["q1", "q2", "q3", "q4"], "spearman", True
        )
        png = make_correlation_matrix_chart(res)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 5000)


if __name__ == "__main__":
    unittest.main()
