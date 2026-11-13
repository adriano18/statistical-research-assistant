"""Stage 37 (review S10): the Monte Carlo floor of the Spearman permutation p.

The default stays the validated 1,999-resample permutation estimate (n ≤ 500).
Its smallest two-sided p is 2/2000 = .001, and with Holm or Bonferroni over k
tests the adjusted p cannot fall below k × .001. These tests show that the
floor is now stated wherever it is reached, that it is not stated otherwise,
and that the t approximation (the SPSS convention, an option of the batch
analysis) has no floor. Only fictional, simulated data appear here.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from batch_correlation import PERMUTATION_FLOOR, correlate_many  # noqa: E402
from correlation import analyze_correlation  # noqa: E402


def frame(seed=1010, n=180):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame({"x": x, "strong": -0.6 * x + rng.normal(0, 0.8, n),
                         "weak": 0.05 * x + rng.normal(size=n),
                         "other": rng.normal(size=n)})


class SpearmanFloorTests(unittest.TestCase):
    def test_a_single_correlation_at_the_floor_says_so(self):
        data = frame()
        result = analyze_correlation(data, "x", "strong", "spearman", "scale", "scale", True)
        self.assertAlmostEqual(result.p_value, PERMUTATION_FLOOR)
        self.assertTrue(any("smallest a two-sided permutation estimate" in w
                            for w in result.warnings))
        # The t approximation of the same ρ is far below the floor.
        self.assertLess(stats.spearmanr(data.x, data.strong).pvalue, 1e-6)
        weak = analyze_correlation(data, "x", "weak", "spearman", "scale", "scale", True)
        self.assertGreater(weak.p_value, PERMUTATION_FLOOR)
        self.assertFalse(any("smallest a two-sided" in w for w in weak.warnings))

    def test_the_family_states_the_floor_and_the_adjusted_floor(self):
        data = frame()
        family = correlate_many(data, "x", ["strong", "weak", "other"], method="spearman",
                                adjust="holm", resamples=200)
        note = [w for w in family.warnings if "smallest p a two-sided" in w]
        self.assertEqual(len(note), 1)
        self.assertIn("(strong)", note[0])
        self.assertIn("cannot fall below 0.003", note[0])
        strong = next(row for row in family.rows if row.y == "strong")
        self.assertAlmostEqual(strong.p_adjusted, 3 * PERMUTATION_FLOOR)

    def test_the_t_approximation_has_no_floor_and_no_note(self):
        data = frame()
        family = correlate_many(data, "x", ["strong", "weak"], method="spearman",
                                adjust="holm", resamples=200, spearman_p="asymptotic")
        strong = next(row for row in family.rows if row.y == "strong")
        self.assertAlmostEqual(strong.p_raw, stats.spearmanr(data.x, data.strong).pvalue)
        self.assertLess(strong.p_raw, PERMUTATION_FLOOR)
        self.assertFalse(any("smallest p a two-sided" in w for w in family.warnings))

    def test_the_default_is_unchanged(self):
        family = correlate_many(frame(), "x", ["weak", "other"], resamples=200)
        self.assertEqual(family.method, "spearman")
        self.assertTrue(all("permutation" in row.p_method for row in family.rows))


if __name__ == "__main__":
    unittest.main()
