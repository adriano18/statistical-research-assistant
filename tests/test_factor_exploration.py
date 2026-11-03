"""Reference invariants for PCA, principal-axis EFA and factorability guards."""

from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.multivariate.factor import Factor

from factor_exploration import analyze_factor_exploration
from factor_reporting import factor_main, format_factor_report
from factor_charts import make_factor_chart


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_factor.csv"


class FactorExplorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = pd.read_csv(SAMPLE)
        cls.items = [x for x in cls.df if x != "participant_id"]

    def run_analysis(self, method="pca", number=2, rotation="none"):
        return analyze_factor_exploration(
            self.df, self.items, method=method,
            n_components=number, rotation=rotation,
            assumptions_confirmed=True,
        )

    def test_pca_eigenvalues_match_numpy(self):
        result = self.run_analysis()
        complete = self.df[self.items].dropna()
        reference = np.linalg.eigvalsh(
            np.corrcoef(complete.to_numpy(), rowvar=False)
        )[::-1]
        np.testing.assert_allclose(result.eigenvalues, reference, rtol=1e-12)
        self.assertEqual(result.n_complete, 223)
        self.assertEqual(result.n_total, 225)
        self.assertEqual(result.loadings.shape, (6, 2))
        np.testing.assert_allclose(
            result.component_variance_share,
            reference[:2]/len(self.items),
        )
        self.assertGreater(result.kmo, 0)
        self.assertLessEqual(result.kmo, 1)
        self.assertLess(result.bartlett_p, .05)

    def test_parallel_analysis_is_deterministic(self):
        a = self.run_analysis()
        b = self.run_analysis()
        np.testing.assert_array_equal(
            a.parallel_threshold, b.parallel_threshold
        )
        self.assertGreaterEqual(a.parallel_count, 1)
        self.assertTrue(np.all(a.parallel_threshold > 0))

    def test_principal_axis_two_factor_loadings(self):
        result = self.run_analysis(method="efa", rotation="varimax")
        self.assertEqual(result.loadings.shape, (6, 2))
        self.assertIsNone(result.component_variance_share)
        self.assertEqual(result.rotation, "varimax")
        self.assertTrue((result.uniqueness > 0).all())
        self.assertTrue((result.uniqueness < 1).all())
        # Compare reproduced common structure using an independent
        # principal-axis factor fitting call; factor signs are arbitrary.
        cleaned = self.df[self.items].dropna().to_numpy()
        reference = Factor(
            corr=np.corrcoef(cleaned, rowvar=False),
            n_factor=2, method="pa", nobs=len(cleaned)
        ).fit()
        reference.rotate("varimax")
        np.testing.assert_allclose(
            result.loadings @ result.loadings.T,
            reference.loadings @ reference.loadings.T,
            rtol=1e-5, atol=1e-5,
        )

    def test_oblimin_factor_correlations_and_structure(self):
        result = self.run_analysis(method="efa", rotation="oblimin")
        self.assertEqual(result.factor_correlations.shape, (2, 2))
        self.assertEqual(result.structure_loadings.shape, (6, 2))
        np.testing.assert_allclose(
            np.diag(result.factor_correlations),
            np.ones(2), atol=1e-4,
        )
        np.testing.assert_allclose(
            result.factor_correlations,
            result.factor_correlations.T,
            atol=1e-8,
        )
        np.testing.assert_allclose(
            result.structure_loadings,
            result.loadings @ result.factor_correlations,
            atol=1e-8,
        )
        reference = Factor(
            corr=np.corrcoef(
                self.df[self.items].dropna().to_numpy(), rowvar=False
            ),
            n_factor=2, method="pa", nobs=result.n_complete,
        ).fit()
        # Both the unrotated and oblimin EFA model reproduce the
        # same common covariance: Lrot @ Phi @ Lrot.T = L @ L.T.
        np.testing.assert_allclose(
            result.loadings @ result.factor_correlations @ result.loadings.T,
            reference.loadings @ reference.loadings.T,
            rtol=1e-5, atol=1e-5,
        )
        report = format_factor_report(result)
        self.assertIn("Oblique factor correlations", report)
        self.assertIn("Structure matrix", report)
        png = make_factor_chart(result)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_oblimin_requires_multiple_factors(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            analyze_factor_exploration(
                self.df, self.items, method="efa",
                n_components=1, rotation="oblimin",
                assumptions_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "without rotation"):
            analyze_factor_exploration(
                self.df, self.items, method="pca",
                n_components=2, rotation="oblimin",
                assumptions_confirmed=True,
            )

    def test_report_and_chart(self):
        a = self.run_analysis(method="efa", rotation="varimax")
        report = format_factor_report(a)
        self.assertIn("KMO", report)
        self.assertIn("Bartlett", report)
        self.assertIn("Principal-axis", report)
        self.assertIn("parallel", factor_main(a).lower())
        png = make_factor_chart(a)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 3000)

    def test_analysis_requires_confirmation(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            analyze_factor_exploration(
                self.df, self.items, method="pca",
            )

    def test_invalid_ordinal_content_and_identifiers(self):
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            analyze_factor_exploration(
                self.df, ["participant_id", *self.items[:3]],
                assumptions_confirmed=True,
            )
        broken = self.df.copy()
        broken[self.items[0]] = broken[self.items[0]].astype(object)
        broken.loc[0, self.items[0]] = "not numeric"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            analyze_factor_exploration(
                broken, self.items, assumptions_confirmed=True,
            )

    def test_reject_constant_item_and_collinearity(self):
        constant = self.df.copy()
        constant[self.items[0]] = 2
        with self.assertRaisesRegex(ValueError, "Constant"):
            analyze_factor_exploration(
                constant, self.items, assumptions_confirmed=True
            )
        duplicated = self.df.copy()
        duplicated[self.items[1]] = duplicated[self.items[0]]
        with self.assertRaisesRegex(ValueError, "singular"):
            analyze_factor_exploration(
                duplicated, self.items, assumptions_confirmed=True
            )

    def test_reject_insufficient_sample_and_bad_configuration(self):
        with self.assertRaisesRegex(ValueError, "Need at least"):
            analyze_factor_exploration(
                self.df.head(10), self.items,
                assumptions_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "without rotation"):
            analyze_factor_exploration(
                self.df, self.items, method="pca",
                rotation="varimax", assumptions_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "1–5"):
            analyze_factor_exploration(
                self.df, self.items, n_components=0,
                assumptions_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "distinct"):
            analyze_factor_exploration(
                self.df, [self.items[0], self.items[0], self.items[2]],
                assumptions_confirmed=True,
            )

    def test_input_unchanged(self):
        before = self.df.copy(deep=True)
        self.run_analysis(method="efa", rotation="none")
        pd.testing.assert_frame_equal(self.df, before)


if __name__ == "__main__":
    unittest.main()
