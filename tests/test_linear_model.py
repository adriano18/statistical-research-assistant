"""Stage 37 (Issue #66, review S3): the linear model with categorical covariates.

``linear_model.fit_linear_model`` against independent references:

* statsmodels **formula** fits with ``C(var, Treatment(reference=...))`` —
  patsy builds the dummy codes, a different code path from the engine's;
* numpy closed forms of OLS and HC3, leverage and Cook's distance;
* nested-model F tests (``anova_lm``) for every block of dummy codes or
  products, and statsmodels ``f_test`` for the HC3 Wald version;
* statsmodels' own ``variance_inflation_factor``;
* standardized β as the slope of a regression of z-scores;
* the independent reviewer's reference values on the Stage 37 fixture
  (``Y ~ X + M + W + age + C(sex) + C(employed)``, listwise n = 175):
  R² = .1708, b_X = −0.4443, b_M = 3.4586, b_W = 3.4881, to 1e-4 — a
  secondary cross-check; the statsmodels oracle is primary.

Tolerance: EXACT = 1e-9 relative (abs 1e-12), the same estimator by
independent code. Only fictional, simulated data appear in this file.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from statsmodels.stats.outliers_influence import variance_inflation_factor  # noqa: E402

from linear_model import LinearSpec, fit_linear_model  # noqa: E402

EXACT = 1e-9


def synthetic(seed=3708, n=150, missing=False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(50, 10, n)
    w = rng.normal(4, 1, n)
    age = rng.integers(18, 31, n).astype(float)
    group = rng.choice(["clinic", "school", "work"], n, p=[0.3, 0.45, 0.25])
    sex = rng.choice([0, 1, 2], n)
    employed = rng.integers(0, 2, n)
    y = (20 - 0.4 * x + 3 * w + 0.15 * (x - 50) * (w - 4) + 0.2 * age
         + np.select([group == "school", group == "work"], [4.0, -3.0], 0.0)
         + 2.0 * (sex == 1) - 1.0 * (sex == 2) + 1.5 * employed + rng.normal(0, 6, n))
    frame = pd.DataFrame({"x": x, "w": w, "age": age, "group": group, "sex": sex,
                          "employed": employed, "y": y})
    if missing:
        frame.loc[[2, 30], "x"] = np.nan
        frame.loc[[30, 41, 77], "group"] = np.nan
    return frame


class Case(unittest.TestCase):
    def assertClose(self, actual, expected, rel=EXACT, abs_tol=1e-12, msg=""):
        self.assertTrue(math.isclose(float(actual), float(expected), rel_tol=rel,
                                     abs_tol=abs_tol), f"{msg}: {actual!r} != {expected!r}")

    def compare(self, result, fit, names_in_order, robust=None):
        """Coefficients in the engine's order against the formula fit by name."""
        ref = robust if robust is not None else fit
        params = pd.Series(np.asarray(ref.params), index=fit.params.index)
        bse = pd.Series(np.asarray(ref.bse), index=fit.params.index)
        pvalues = pd.Series(np.asarray(ref.pvalues), index=fit.params.index)
        self.assertEqual(len(result.coefficients), len(names_in_order))
        for coefficient, name in zip(result.coefficients, names_in_order):
            self.assertClose(coefficient.b, params[name], msg=f"b {name}")
            self.assertClose(coefficient.se, bse[name], msg=f"se {name}")
            self.assertClose(coefficient.p, pvalues[name], rel=1e-7, abs_tol=1e-15,
                             msg=f"p {name}")
        self.assertClose(result.r_squared, fit.rsquared, msg="R²")
        self.assertClose(result.adj_r_squared, fit.rsquared_adj, msg="adjusted R²")
        self.assertClose(result.f_value, fit.fvalue, msg="F")
        self.assertEqual(result.n, int(fit.nobs))


class FormulaOracleTests(Case):
    def test_dummy_codes_with_each_reference_rule(self):
        frame = synthetic(missing=True)
        complete = frame.dropna()
        for rule, refs in (("first", ("clinic", 0)), ("last", ("work", 2)),
                           ("most_frequent", None)):
            result = fit_linear_model(frame, LinearSpec("y", ("x", "age"), ("group", "sex"),
                                                        reference=rule))
            if refs is None:
                refs = (complete["group"].value_counts().idxmax(),
                        int(complete["sex"].value_counts().idxmax()))
            g, s = refs
            fit = smf.ols(f"y ~ x + age + C(group, Treatment('{g}')) + C(sex, Treatment({s}))",
                          data=complete).fit()
            names = ["Intercept", "x", "age",
                     *[n for n in fit.params.index if n.startswith("C(group")],
                     *[n for n in fit.params.index if n.startswith("C(sex")]]
            self.compare(result, fit, names)
            self.assertEqual(result.references, {"group": str(g), "sex": str(s)}, rule)
            self.assertEqual(result.n, len(complete))

    def test_a_reference_named_by_the_researcher(self):
        frame = synthetic()
        result = fit_linear_model(frame, LinearSpec("y", ("x",), ("group",),
                                                    references=(("group", "school"),)))
        fit = smf.ols("y ~ x + C(group, Treatment('school'))", data=frame).fit()
        self.compare(result, fit, ["Intercept", "x", *fit.params.index[1:3]])
        self.assertIn("vs school", result.coefficients[2].term)
        with self.assertRaises(ValueError):
            fit_linear_model(frame, LinearSpec("y", ("x",), ("group",),
                                               references=(("group", "army"),)))

    def test_hc3_standard_errors_and_the_block_wald_test(self):
        frame = synthetic()
        result = fit_linear_model(frame, LinearSpec("y", ("x", "w"), ("group",), hc3=True))
        fit = smf.ols("y ~ x + w + C(group)", data=frame).fit()
        robust = fit.get_robustcov_results(cov_type="HC3", use_t=True)
        self.compare(result, fit, ["Intercept", "x", "w", "C(group)[T.school]", "C(group)[T.work]"],
                     robust=robust)
        block = next(b for b in result.blocks if b.kind == "factor")
        names = list(fit.params.index)
        rows = [names.index("C(group)[T.school]"), names.index("C(group)[T.work]")]
        test = robust.f_test(np.eye(len(names))[rows])
        self.assertClose(block.robust_f, float(np.squeeze(test.fvalue)), msg="HC3 Wald F")
        self.assertClose(block.robust_p, float(np.squeeze(test.pvalue)), rel=1e-7, msg="HC3 p")
        # The numpy sandwich: (X'X)⁻¹ X' diag(e²/(1−h)²) X (X'X)⁻¹.
        matrix = result.design.to_numpy()      # the engine's own column order
        xtx_inv = np.linalg.inv(matrix.T @ matrix)
        resid = result.observed - matrix @ np.linalg.lstsq(matrix, result.observed, rcond=None)[0]
        hat = np.einsum("ij,jk,ik->i", matrix, xtx_inv, matrix)
        hc3 = xtx_inv @ ((matrix * (resid / (1 - hat))[:, None] ** 2).T @ matrix) @ xtx_inv
        np.testing.assert_allclose([c.se for c in result.coefficients], np.sqrt(np.diag(hc3)),
                                   rtol=1e-9)

    def test_products_quantitative_and_categorical_with_centring(self):
        frame = synthetic()
        result = fit_linear_model(frame, LinearSpec(
            "y", ("x", "w", "age"), ("group",), products=(("x", "w"), ("x", "group")),
            center=True))
        data = frame.assign(xc=frame.x - frame.x.mean(), wc=frame.w - frame.w.mean())
        fit = smf.ols("y ~ xc + wc + age + C(group) + I(xc * wc) + xc:C(group)",
                      data=data).fit()
        order = ["Intercept", "xc", "wc", "age", "C(group)[T.school]", "C(group)[T.work]",
                 "I(xc * wc)", "xc:C(group)[T.school]", "xc:C(group)[T.work]"]
        self.compare(result, fit, order)
        self.assertEqual(set(result.centering), {"x"} if False else {"x", "w"})
        self.assertClose(result.centering["x"], frame.x.mean(), msg="centre x")
        # Blocks: each product against the model without it (nested F test).
        for block, formula in (
                ("x × w", "y ~ xc + wc + age + C(group) + xc:C(group)"),
                ("x × group", "y ~ xc + wc + age + C(group) + I(xc * wc)"),
                ("group (with its products)", "y ~ xc + wc + age + I(xc * wc)")):
            reduced = smf.ols(formula, data=data).fit()
            table = sm.stats.anova_lm(reduced, fit)
            test = next(b for b in result.blocks if b.name == block)
            self.assertClose(test.f_value, table["F"].iloc[1], msg=f"F {block}")
            self.assertClose(test.p, table["Pr(>F)"].iloc[1], rel=1e-7, msg=f"p {block}")
            self.assertClose(test.delta_r2, fit.rsquared - reduced.rsquared, msg=f"ΔR² {block}")
            self.assertClose(test.f2, (fit.rsquared - reduced.rsquared) / (1 - fit.rsquared),
                             msg=f"f² {block}")

    def test_standardized_beta_only_for_quantitative_predictors(self):
        frame = synthetic()
        result = fit_linear_model(frame, LinearSpec("y", ("x", "w", "age"), ("sex",),
                                                    products=(("x", "w"),)))
        z = frame[["x", "w", "age", "y"]].apply(lambda s: (s - s.mean()) / s.std(ddof=1))
        z["sex"] = frame["sex"]
        # β of a quantitative predictor in a model without products: the z-score slope.
        plain = fit_linear_model(frame, LinearSpec("y", ("x", "w", "age"), ("sex",)))
        fit = smf.ols("y ~ x + w + age + C(sex)", data=z).fit()
        for name in ("x", "w", "age"):
            self.assertClose(plain.coefficient(f"x:{name}").beta, fit.params[name],
                             msg=f"β {name}")
        kinds = {c.kind: c.beta for c in result.coefficients if c.kind != "quantitative"}
        self.assertEqual(set(kinds.values()), {None})        # constant, dummy, product

    def test_vif_leverage_cooks_and_residual_tests(self):
        from scipy import stats
        from statsmodels.stats.diagnostic import het_breuschpagan

        frame = synthetic()
        result = fit_linear_model(frame, LinearSpec("y", ("x", "w", "age"), ("group",)))
        fit = smf.ols("y ~ x + w + age + C(group)", data=frame).fit()
        matrix = result.design.to_numpy()
        for j, c in enumerate(result.coefficients[1:], start=1):
            self.assertClose(c.vif, variance_inflation_factor(matrix, j), rel=1e-8, msg=c.term)
        resid = np.asarray(fit.resid)
        n, p = matrix.shape
        hat = np.einsum("ij,jk,ik->i", matrix, np.linalg.inv(matrix.T @ matrix), matrix)
        cooks = resid ** 2 * hat / (p * (resid @ resid / (n - p)) * (1 - hat) ** 2)
        self.assertClose(result.cooks_max, cooks.max(), rel=1e-8, msg="Cook's D")
        self.assertEqual(result.cooks_over, int(np.sum(cooks > 4 / n)))
        self.assertClose(result.leverage_max, hat.max(), rel=1e-9, msg="leverage")
        self.assertClose(result.shapiro_p, stats.shapiro(resid).pvalue, rel=1e-6, msg="SW")
        self.assertClose(result.bp_p, het_breuschpagan(resid, matrix)[1], rel=1e-9, msg="BP")


class ReviewerReferenceTests(Case):
    def test_the_reviewers_values_on_the_stage37_fixture(self):
        sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "stage37"))
        import generate_master_fixture as fixture

        with tempfile.TemporaryDirectory() as folder:
            csv_path, spec_path = fixture.generate(Path(folder))
            frame = pd.read_csv(csv_path)
            model = json.loads(spec_path.read_text(encoding="utf-8"))
        x, m, w, y = (model[k].split()[0] for k in ("X", "M", "W", "Y"))
        result = fit_linear_model(frame, LinearSpec(
            y, (x, m, w, "age_years"), ("sex_code", "employed_code")))
        self.assertEqual(result.n, 175)
        self.assertAlmostEqual(result.r_squared, 0.1708, places=4)
        self.assertAlmostEqual(result.coefficient(f"x:{x}").b, -0.4443, places=4)
        self.assertAlmostEqual(result.coefficient(f"x:{m}").b, 3.4586, places=4)
        self.assertAlmostEqual(result.coefficient(f"x:{w}").b, 3.4881, places=4)
        self.assertEqual(result.references, {"sex_code": "0", "employed_code": "0"})
        fit = smf.ols(f"{y} ~ {x} + {m} + {w} + age_years + C(sex_code) + C(employed_code)",
                      data=frame.dropna(subset=[x, m, w, y])).fit()
        self.assertClose(result.r_squared, fit.rsquared, msg="primary oracle")


class RuleTests(Case):
    def test_a_category_variable_enters_only_as_dummy_codes(self):
        frame = synthetic()
        with self.assertRaises(ValueError) as caught:
            fit_linear_model(frame, LinearSpec("y", ("x", "group")))      # text as a number
        self.assertIn("categorical covariates", str(caught.exception))
        result = fit_linear_model(frame, LinearSpec("y", ("x",), ("group",)))
        self.assertEqual([c.kind for c in result.coefficients],
                         ["constant", "quantitative", "dummy", "dummy"])
        with self.assertRaises(ValueError):
            fit_linear_model(frame, LinearSpec("y", ("x",), ("x",)))       # two roles
        with self.assertRaises(ValueError):
            fit_linear_model(frame, LinearSpec("y", ("x",), products=(("x", "w"),)))
        with self.assertRaises(ValueError):
            fit_linear_model(frame, LinearSpec("y"))

    def test_missing_values_are_left_out_listwise_and_counted(self):
        frame = synthetic(missing=True)
        result = fit_linear_model(frame, LinearSpec("y", ("x",), ("group",)))
        self.assertEqual(result.n, len(frame.dropna(subset=["y", "x", "group"])))
        self.assertEqual(dict(result.missing), {"y": 0, "x": 2, "group": 3})
        self.assertTrue(any("listwise" in w for w in result.warnings))
        self.assertTrue(any("reference category" in w for w in result.warnings))

    def test_the_structured_result_round_trips(self):
        from result_store import from_json, to_json

        result = fit_linear_model(synthetic(), LinearSpec("y", ("x",), ("group",), hc3=True))
        stored = json.loads(json.dumps(to_json(result)))
        again = from_json(stored)
        self.assertEqual(again, result.structured())
        self.assertEqual(again.quantity("b:x:x").value, result.coefficient("x:x").b)


if __name__ == "__main__":
    unittest.main()
