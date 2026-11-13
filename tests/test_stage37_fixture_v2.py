"""Stage 37 (review S6): the synthetic fixture v2 and what it shows.

``tests/fixtures/stage37/generate_master_fixture_v2.py`` is a separate
generator; the owner's v1 is unchanged. v2 adds consistent mediation, a
coping dimension tied negatively to Y, covariate effects, reverse-keyed
items with a stated key, and missingness that depends on observed values.

Numbers are compared with independent oracles (statsmodels, numpy,
pandas); signs are compared with the generator's structure only as a
sanity check (latent coefficients are not sample estimates). Only fictional
data appear here.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "stage37"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FIXTURES))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402

import generate_master_fixture as v1  # noqa: E402
import generate_master_fixture_v2 as v2  # noqa: E402


class FixtureV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        csv_path, spec_path = v2.generate(Path(cls.temp.name) / "a")
        cls.csv_bytes = csv_path.read_bytes()
        cls.frame = pd.read_csv(csv_path)
        cls.spec = json.loads(spec_path.read_text(encoding="utf-8"))
        cls.X, cls.M, cls.W, cls.Y = (cls.spec[k].split()[0] for k in ("X", "M", "W", "Y"))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assertClose(self, actual, expected, rel=1e-9, msg=""):
        self.assertTrue(math.isclose(float(actual), float(expected), rel_tol=rel,
                                     abs_tol=1e-12), f"{msg}: {actual!r} != {expected!r}")

    def test_v2_is_separate_deterministic_and_stdlib_only(self):
        self.assertEqual((v1.N, v1.SEED), (180, 37012026))          # v1 unchanged
        self.assertNotEqual(v2.SEED, v1.SEED)
        with tempfile.TemporaryDirectory() as folder:
            again = v2.generate(Path(folder))[0].read_bytes()
        self.assertEqual(hashlib.sha256(again).hexdigest(),
                         hashlib.sha256(self.csv_bytes).hexdigest())
        tree = ast.parse((FIXTURES / "generate_master_fixture_v2.py").read_text("utf-8"))
        modules = {alias.name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in (node.names if isinstance(node, ast.Import) else [node])
                   if isinstance(node, ast.Import)} | {
            node.module.split(".")[0] for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module}
        self.assertLessEqual(modules, {"__future__", "argparse", "csv", "json", "random",
                                       "pathlib"})
        self.assertEqual(self.frame.shape[0], 240)
        self.assertTrue(self.frame["participant_code"].is_unique)

    def test_scores_follow_the_stated_scoring_key(self):
        key = self.spec["scoring_key"]["SYN2_LON_TOTAL"]
        items = self.frame[key["items"]].copy()
        for column in key["reverse"]:
            items[column] = 5 - items[column]
        np.testing.assert_array_equal(self.frame[self.X], items.sum(axis=1))
        key = self.spec["scoring_key"]["SYN2_AVOID_MEAN"]
        items = self.frame[key["items"]].copy()
        for column in key["reverse"]:
            items[column] = 6 - items[column]
        expected = items.mean(axis=1, skipna=False).round(6)
        pd.testing.assert_series_equal(self.frame[self.M], expected, check_names=False)

    def test_reverse_keyed_items_are_flagged_and_recoding_raises_alpha(self):
        from item_diagnostics import diagnose_items

        key = self.spec["scoring_key"]["SYN2_LON_TOTAL"]
        with warnings.catch_warnings():         # the omega engine's library chatter
            warnings.simplefilter("ignore")
            raw = diagnose_items(self.frame, key["items"], resamples=0)
        self.assertEqual([row.name for row in raw.rows if row.possibly_reverse], key["reverse"])
        recoded = self.frame.copy()
        for column in key["reverse"]:
            recoded[column] = 5 - recoded[column]
        documented = diagnose_items(recoded, key["items"], resamples=0,
                                    reverse_keyed=key["reverse"], reverse_source="spec v2")
        self.assertEqual([row.recoding for row in documented.rows if row.documented_reverse],
                         ["appears_recoded", "appears_recoded"])
        self.assertGreater(documented.alpha.value, raw.alpha.value)
        values = recoded[key["items"]].dropna().to_numpy(float)
        k = values.shape[1]
        alpha = k / (k - 1) * (1 - values.var(axis=0, ddof=1).sum()
                               / values.sum(axis=1).var(ddof=1))
        self.assertClose(documented.alpha.value, alpha, msg="alpha")

    def test_consistent_mediation_has_no_suppression_note(self):
        from process_models import ProcessSpec, fit_process
        from process_reporting import process_interpretation

        covariates = ("age_years", "employed_code")
        result = fit_process(self.frame, ProcessSpec("4", self.X, self.Y, (self.M,),
                                                     covariates=covariates, resamples=1000))
        rows = self.frame[[self.X, self.M, self.Y, *covariates]].dropna()
        a = smf.ols(f"{self.M} ~ {self.X} + age_years + employed_code", rows).fit()
        y = smf.ols(f"{self.Y} ~ {self.X} + {self.M} + age_years + employed_code", rows).fit()
        self.assertClose(result.estimate("a:m0").value, a.params[self.X], msg="a")
        self.assertClose(result.estimate("b:m0").value, y.params[self.M], msg="b")
        self.assertClose(result.estimate("direct").value, y.params[self.X], msg="c'")
        indirect = result.estimate("indirect:m0").value
        # The generator's structure (sanity): a > 0, b < 0, so a·b < 0, like c′ and c.
        self.assertLess(indirect, 0)
        self.assertLess(result.estimate("direct").value, 0)
        self.assertLess(result.estimate("total").value, 0)
        for language in ("en", "lv", "ru"):
            text = "\n".join(process_interpretation(result, language))
            for word in ("inconsistent", "nekonsekventa", "несогласованная"):
                self.assertNotIn(word, text, language)

    def test_a_dimension_tied_negatively_and_one_positively_to_y(self):
        from batch_correlation import correlate_many

        others = [self.M, "SYN2_ASSERT_MEAN"]
        family = correlate_many(self.frame, self.Y, others, method="pearson",
                                pearson_assumptions_confirmed=True, resamples=200)
        for row, other in zip(family.rows, others):
            pair = self.frame[[self.Y, other]].dropna()
            self.assertClose(row.estimate, np.corrcoef(pair[self.Y], pair[other])[0, 1],
                             msg=other)
        self.assertLess(family.rows[0].estimate, 0)
        self.assertGreater(family.rows[1].estimate, 0)

    def test_covariates_enter_the_linear_model_with_dummy_codes(self):
        from linear_model import LinearSpec, fit_linear_model

        result = fit_linear_model(self.frame, LinearSpec(self.Y, (self.X, "age_years"),
                                                         ("sex_code", "employed_code")))
        fit = smf.ols(f"{self.Y} ~ {self.X} + age_years + C(sex_code) + C(employed_code)",
                      data=self.frame).fit()
        self.assertClose(result.r_squared, fit.rsquared, msg="R²")
        self.assertClose(result.coefficient("x:age_years").b, fit.params["age_years"],
                         msg="age")
        self.assertClose(result.coefficient("d:employed_code=1").b,
                         fit.params["C(employed_code)[T.1]"], msg="employed")

    def test_missingness_depends_on_observed_values(self):
        from process_models import ProcessSpec, fit_process

        self.assertEqual(int(self.frame["SYN2_AVOID_02"].isna().sum()),
                         int(self.frame[self.M].isna().sum()))
        result = fit_process(self.frame, ProcessSpec("4", self.X, self.Y, (self.M,),
                                                     covariates=("age_years",), resamples=200))
        rows = {row[0]: row for row in result.missing.comparison}
        mask = self.frame[[self.X, self.M, self.Y, "age_years"]].notna().all(axis=1)
        inside = self.frame.loc[mask, "age_years"]
        out = self.frame.loc[~mask, "age_years"]
        smd = (out.mean() - inside.mean()) / inside.std(ddof=1)
        self.assertClose(rows["age_years"][7], smd, msg="SMD age")
        self.assertLess(smd, 0)         # the generator makes younger cases miss more (sanity)


if __name__ == "__main__":
    unittest.main()
