"""Tests for one-factor McDonald's omega and item-rest diagnostics."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from statsmodels.multivariate.factor import Factor

from omega_analysis import analyze_omega
from omega_reporting import format_omega_report, omega_summary
from omega_charts import make_omega_chart


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_scale.csv"
ITEMS = ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]


class OmegaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(SAMPLE)
        generator = np.random.default_rng(2402)
        factor = generator.normal(size=240)
        cls.synthetic = pd.DataFrame({
            f"scale_q{j+1}": loading * factor
            + generator.normal(size=240) * np.sqrt(1 - loading**2)
            for j, loading in enumerate((.85, .77, .70, .62))
        })
        cls.names = list(cls.synthetic.columns)

    def test_synthetic_congeneric_factor_omega_matches_reference(self):
        estimate = analyze_omega(self.synthetic, self.names)
        x = self.synthetic.to_numpy()
        reference = Factor(
            corr=np.corrcoef(x, rowvar=False), n_factor=1,
            method="ml", nobs=len(x)
        ).fit()
        lam = reference.loadings.ravel()
        unique = reference.uniqueness
        expected = np.sum(lam)**2 / (np.sum(lam)**2 + np.sum(unique))
        self.assertAlmostEqual(estimate.omega, float(expected), places=6)
        self.assertGreater(estimate.omega, .75)
        self.assertLess(estimate.omega, 1.0)
        self.assertEqual(estimate.n_complete, 240)
        self.assertEqual(len(estimate.diagnostics), 4)

    def test_corrected_item_rest_excludes_current_item(self):
        result = analyze_omega(self.synthetic, self.names)
        col = self.names[0]
        expected = self.synthetic[col].corr(
            self.synthetic[self.names[1:]].sum(axis=1)
        )
        self.assertAlmostEqual(
            result.diagnostics[0].corrected_item_rest_r,
            expected, places=10,
        )

    def test_missing_cases_and_source_not_modified(self):
        prior = self.data.copy(deep=True)
        res = analyze_omega(self.data, ITEMS)
        self.assertEqual(res.n_total, 32)
        self.assertEqual(res.n_complete, 30)
        self.assertEqual(len(res.items), 4)
        self.assertTrue(any("excluded" in x.lower() for x in res.warnings))
        self.assertEqual(res.diagnostics[0].missing,
                         int(self.data[ITEMS[0]].isna().sum()))
        pd.testing.assert_frame_equal(self.data, prior)

    def test_report_and_figure(self):
        r = analyze_omega(self.synthetic, self.names)
        text = format_omega_report(r)
        self.assertIn("McDonald", text)
        self.assertIn("Corrected item-rest", text)
        self.assertIn("confidence interval", text)
        self.assertIn("NOT evidence", omega_summary(r))
        img = make_omega_chart(r)
        self.assertTrue(img.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(img), 3000)

    def test_identifier_and_non_numeric_rejected(self):
        bad = self.synthetic.copy()
        bad.insert(0, "participant_id", np.arange(len(bad)) + 1)
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_omega(bad, ["participant_id", *self.names[:3]])
        bad = self.synthetic.copy()
        bad[self.names[0]] = bad[self.names[0]].astype(object)
        bad.loc[0, self.names[0]] = "bad response"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_omega(bad, self.names)

    def test_insufficient_sample_and_constant_item_rejected(self):
        with self.assertRaisesRegex(ValueError, "At least"):
            analyze_omega(self.synthetic.head(18), self.names)
        bad = self.synthetic.copy()
        bad[self.names[1]] = 5
        with self.assertRaisesRegex(ValueError, "no variation"):
            analyze_omega(bad, self.names)

    def test_too_few_or_duplicate_items(self):
        for names in [
            self.names[:2],
            [self.names[0], self.names[0], self.names[2]],
        ]:
            with self.assertRaisesRegex(ValueError, "DISTINCT"):
                analyze_omega(self.synthetic, names)

    def test_negative_item_relation_is_flagged_without_autoflip(self):
        bad = self.synthetic.copy()
        bad[self.names[3]] *= -1
        result = analyze_omega(bad, self.names)
        self.assertTrue(any(
            d.corrected_item_rest_r < 0 for d in result.diagnostics
        ))
        self.assertTrue(any("NEGATIVE" in line for line in result.warnings))
        self.assertEqual(bad.iloc[0, 3],
                         -self.synthetic.iloc[0, 3])

    def test_near_singular_items_rejected(self):
        bad = self.synthetic.copy()
        bad[self.names[2]] = bad[self.names[1]] * 2
        with self.assertRaisesRegex(ValueError, "singular"):
            analyze_omega(bad, self.names)


if __name__ == "__main__":
    unittest.main()
