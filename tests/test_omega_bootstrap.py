"""Nonparametric omega bootstrap uncertainty and reporting safeguards."""

import unittest

import numpy as np
import pandas as pd

from omega_analysis import analyze_omega
from omega_bootstrap import bootstrap_omega
from omega_reporting import format_omega_report, omega_summary
from omega_charts import make_omega_chart


class OmegaBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(1207)
        latent = rng.normal(size=180)
        cls.items = [f"scale_item_{i}" for i in range(1, 5)]
        cls.df = pd.DataFrame({
            col: loading*latent + rng.normal(
                size=len(latent), scale=np.sqrt(1-loading**2)
            )
            for col, loading in zip(
                cls.items, (.90, .81, .75, .69)
            )
        })

    def test_reproducible_complete_case_percentile_ci(self):
        prior = self.df.copy(deep=True)
        a = bootstrap_omega(self.df, self.items, n_resamples=100, seed=42)
        b = bootstrap_omega(self.df, self.items, n_resamples=100, seed=42)
        self.assertAlmostEqual(a.lower, b.lower, places=5)
        self.assertAlmostEqual(a.upper, b.upper, places=5)
        self.assertTrue(0 <= a.lower <= a.upper <= 1)
        self.assertEqual(a.requested, 100)
        self.assertEqual(a.successful + a.failed, 100)
        self.assertEqual(a.level, .95)
        pd.testing.assert_frame_equal(prior, self.df)

    def test_interleaved_factor_analysis_does_not_change_seeded_ci(self):
        first = bootstrap_omega(
            self.df, self.items, n_resamples=100, seed=817,
        )
        # Replicate the factor model between two identical bootstrap runs,
        # as happens when users open and close different analysis screens.
        analyze_omega(self.df, self.items)
        second = bootstrap_omega(
            self.df, self.items, n_resamples=100, seed=817,
        )
        # Numerical ML optimizers may differ at floating-point noise
        # levels. Reproducibility must hold to reportable precision,
        # without pretending that their internal bits are identical.
        self.assertAlmostEqual(first.lower, second.lower, places=5)
        self.assertAlmostEqual(first.upper, second.upper, places=5)
        self.assertEqual(first.successful, second.successful)

    def test_bootstrap_ignores_incomplete_participants(self):
        incomplete = self.df.copy()
        incomplete.loc[0, self.items[0]] = np.nan
        out = bootstrap_omega(
            incomplete, self.items, n_resamples=100, seed=15
        )
        self.assertGreater(out.successful, 90)

    def test_apa_and_png_include_interval_when_requested(self):
        result = analyze_omega(self.df, self.items)
        ci = bootstrap_omega(self.df, self.items, n_resamples=100, seed=99)
        report = format_omega_report(result, ci)
        self.assertIn("bootstrap percentile CI", report)
        self.assertIn("Spearman item-rest", report)
        self.assertIn(f"{ci.successful}/100", report)
        self.assertIn("95% bootstrap CI", omega_summary(result, ci))
        png = make_omega_chart(result, ci)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_rank_correlation_matches_scipy(self):
        from scipy.stats import spearmanr
        result = analyze_omega(self.df, self.items)
        current = self.items[0]
        rest = self.df[self.items[1:]].sum(axis=1)
        reference = spearmanr(self.df[current], rest).statistic
        self.assertAlmostEqual(
            result.diagnostics[0].rank_item_rest_r,
            reference, places=10,
        )

    def test_invalid_resample_arguments(self):
        for reps in (-1, 0, 99, 3001, 100.2):
            with self.subTest(reps=reps), self.assertRaisesRegex(
                ValueError, "100–3000"
            ):
                bootstrap_omega(self.df, self.items, n_resamples=reps)
        with self.assertRaisesRegex(ValueError, "Seed"):
            bootstrap_omega(
                self.df, self.items, n_resamples=100, seed=-1
            )


if __name__ == "__main__":
    unittest.main()
