"""Stage 37 (Issue #66): the path-model engine against independent oracles.

``process_models`` fits structures equivalent to PROCESS Models 1, 4, 7 and
14 (Hayes, 2022). Every number is checked here against a computation that
does not use the engine's code:

* **statsmodels formula fits** (patsy-built designs, a different code path
  from the engine's arrays) and **numpy closed forms** of OLS and HC3 for
  every coefficient, standard error, R², F and p of every equation;
* **closed forms**: simple-mediation paths from correlations, the identity
  c = c′ + Σ a_j b_j, conditional effects as the slope of X after shifting
  W, ΔR² F = t², the index of moderated mediation, centring invariance;
* **Johnson–Neyman**: the closed-form roots against a root finder
  (scipy ``brentq``) on statsmodels ``t_test`` contrasts, and p = .05 at the
  roots;
* **bootstrap**: a numpy-only re-implementation (QR solves, its own design
  matrices, its own type-7 percentile) driven by the same resample indices;
* **sensitivity simulation**: type I error at 0 and the analytic power of
  the product term (noncentral t) for Model 1.

Tolerances
* EXACT = 1e-9 relative (abs 1e-12): the same estimator by independent
  code (observed differences are near 1e-13).
* BOOT = 1e-10 relative to the scale of the draws: the engine solves each
  resample with LAPACK ``gelsd`` (``numpy.linalg.lstsq``), the oracle with
  QR; with the same indices the draws and the percentile limits agree to
  floating-point rounding (observed ≤ 1e-13).
* Monte Carlo tolerances are stated next to the tests that use them.

The fixture sign check at the end only shows that the sample estimates have
the signs of the generator's latent coefficients; the latent coefficients
are not sample estimates and are never compared as numbers.
Only fictional, simulated data appear in this file.
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
from scipy import optimize, stats  # noqa: E402
import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from statsmodels.stats.outliers_influence import variance_inflation_factor  # noqa: E402

import process_models as pm  # noqa: E402
from process_models import ProcessSpec, fit_process  # noqa: E402

EXACT = 1e-9
BOOT = 1e-10
COVARIATES = ("age", "employed")


# ------------------------------------------------------------------ data
def synthetic(seed: int = 6601, n: int = 160, *, missing: bool = False) -> pd.DataFrame:
    """Fictional data with mediation and moderation built in (fixed seed)."""
    rng = np.random.default_rng(seed)
    x = rng.normal(50, 10, n)
    w = rng.normal(4, 1, n)
    age = rng.integers(18, 31, n).astype(float)
    employed = rng.integers(0, 2, n).astype(float)
    m1 = 1 + 0.03 * x + 0.012 * (x - 50) * (w - 4) + 0.02 * age + rng.normal(0, 0.6, n)
    m2 = 2 - 0.02 * x + 0.1 * employed + rng.normal(0, 0.5, n)
    y = (40 - 0.3 * x + 4 * m1 + 3 * m2 + 2 * w + 1.5 * (m1 - 2.5) * (w - 4)
         + 0.1 * (x - 50) * (w - 4) + rng.normal(0, 8, n))
    frame = pd.DataFrame({"x": x, "w": w, "m1": m1, "m2": m2, "y": y, "age": age,
                          "employed": employed})
    if missing:
        frame.loc[[3, 17, 40], "m1"] = np.nan
        frame.loc[[17, 90], "w"] = np.nan
        frame.loc[[120], "age"] = np.nan
    return frame


def complete(frame: pd.DataFrame, spec: ProcessSpec) -> pd.DataFrame:
    return frame[spec.variables()].dropna().reset_index(drop=True)


SPECS = {
    "4": ProcessSpec("4", "x", "y", ("m1", "m2"), covariates=COVARIATES, resamples=1000),
    "4-simple": ProcessSpec("4", "x", "y", ("m1",), resamples=1000),
    "1": ProcessSpec("1", "x", "y", w="w", covariates=COVARIATES),
    "1-centred-hc3": ProcessSpec("1", "x", "y", w="w", covariates=COVARIATES, center=True,
                                 hc3=True),
    "7": ProcessSpec("7", "x", "y", ("m1",), w="w", covariates=COVARIATES, resamples=1000),
    "7-two": ProcessSpec("7", "x", "y", ("m1", "m2"), w="w", resamples=1000, center=True),
    "14": ProcessSpec("14", "x", "y", ("m1",), w="w", covariates=COVARIATES, resamples=1000,
                      hc3=True),
    "14-two-centred": ProcessSpec("14", "x", "y", ("m1", "m2"), w="w", resamples=1000,
                                  center=True),
}


def formula_terms(spec: ProcessSpec, key: str, centring: dict) -> tuple[str, str, list[str]]:
    """(outcome, patsy formula, the engine's term keys) built independently."""
    def col(name):
        return f"{name}_c" if name in centring else name

    covs = list(spec.covariates)
    if spec.model == "4":
        if key.startswith("m"):
            j = int(key[1:])
            return spec.mediators[j], f"{spec.mediators[j]} ~ " + " + ".join(["x", *covs]), []
        if key == "total":
            return "y", "y ~ " + " + ".join(["x", *covs]), []
        return "y", "y ~ " + " + ".join(["x", *spec.mediators, *covs]), []
    if spec.model == "1":
        return "y", f"y ~ {col('x')} + {col('w')} + I({col('x')} * {col('w')})" + "".join(
            f" + {c}" for c in covs), []
    if spec.model == "7":
        if key.startswith("m"):
            j = int(key[1:])
            return spec.mediators[j], (f"{spec.mediators[j]} ~ {col('x')} + {col('w')} + "
                                       f"I({col('x')} * {col('w')})" + "".join(
                                           f" + {c}" for c in covs)), []
        return "y", f"y ~ {col('x')} + " + " + ".join([*spec.mediators, *covs]), []
    if key.startswith("m"):
        j = int(key[1:])
        return spec.mediators[j], f"{spec.mediators[j]} ~ " + " + ".join(["x", *covs]), []
    mediators = [col(m) for m in spec.mediators]
    products = [f"I({m} * {col('w')})" for m in mediators]
    return "y", "y ~ x + " + " + ".join([*mediators, col("w"), *products, *covs]), []


def centred_frame(frame: pd.DataFrame, spec: ProcessSpec) -> tuple[pd.DataFrame, dict]:
    data = complete(frame, spec)
    centring = {}
    if spec.center:
        names = ["x", "w"] if spec.model in ("1", "7") else [*spec.mediators, "w"]
        for name in names:
            centring[name] = float(data[name].mean())
            data[f"{name}_c"] = data[name] - centring[name]
    return data, centring


def numpy_ols(matrix: np.ndarray, outcome: np.ndarray):
    """β, classical and HC3 covariance, residuals and leverage, written out."""
    xtx_inv = np.linalg.inv(matrix.T @ matrix)
    beta = xtx_inv @ matrix.T @ outcome
    resid = outcome - matrix @ beta
    n, p = matrix.shape
    hat = np.einsum("ij,jk,ik->i", matrix, xtx_inv, matrix)
    classical = xtx_inv * (resid @ resid) / (n - p)
    meat = (matrix * (resid / (1 - hat))[:, None] ** 2).T @ matrix
    hc3 = xtx_inv @ meat @ xtx_inv
    return beta, classical, hc3, resid, hat


class Case(unittest.TestCase):
    _cache: dict = {}

    @classmethod
    def fit(cls, name: str, frame: pd.DataFrame | None = None) -> pm.ProcessResult:
        key = (name, id(frame))
        if frame is not None:
            return fit_process(frame, SPECS[name])
        if name not in cls._cache:
            cls._cache[name] = fit_process(synthetic(missing=True), SPECS[name])
        return cls._cache[name]

    def assertClose(self, actual, expected, rel=EXACT, abs_tol=1e-12, msg=""):
        self.assertTrue(math.isclose(float(actual), float(expected), rel_tol=rel,
                                     abs_tol=abs_tol), f"{msg}: {actual!r} != {expected!r}")


# ------------------------------------------------------------------ specification
class SpecificationTests(Case):
    def test_the_model_is_never_chosen_by_the_program(self):
        for bad in ("", None, "2", "auto", "best"):
            with self.assertRaises(ValueError) as caught:
                pm.check_spec(ProcessSpec(bad, "x", "y", ("m1",)))
            self.assertIn("does not choose", str(caught.exception))
        with self.assertRaises(ValueError):
            pm.check_spec(ProcessSpec("4", "x", "y"))              # no mediator named
        with self.assertRaises(ValueError):
            pm.check_spec(ProcessSpec("1", "x", "y", ("m1",), w="w"))
        with self.assertRaises(ValueError):
            pm.check_spec(ProcessSpec("4", "x", "y", ("m1",), w="w"))   # 7 or 14 must be stated
        with self.assertRaises(ValueError):
            pm.check_spec(ProcessSpec("7", "x", "y", ("m1",)))     # W missing
        with self.assertRaises(ValueError):
            pm.check_spec(ProcessSpec("4", "x", "y", ("x",)))      # a variable in two roles
        with self.assertRaises(ValueError):
            pm.check_spec(ProcessSpec("4", "x", "y", ("m1",), resamples=50))

    def test_the_defaults_are_5000_resamples_and_a_fixed_seed_both_reported(self):
        spec = ProcessSpec("4", "x", "y", ("m1",))
        self.assertEqual(spec.resamples, 5000)
        self.assertEqual(spec.seed, pm.DEFAULT_SEED)
        result = fit_process(synthetic(), spec)
        self.assertEqual(result.bootstrap.resamples, 5000)
        self.assertEqual(result.bootstrap.seed, pm.DEFAULT_SEED)
        self.assertEqual(result.spec.model, "4")
        from process_reporting import methods_text

        text = methods_text(result)
        self.assertIn("5000 resamples", text)
        self.assertIn(f"seed {pm.DEFAULT_SEED}", text)
        self.assertIn("structure equivalent to PROCESS Model 4", text.replace("Structure", "structure"))
        self.assertIn("not by the PROCESS macro", text)

    def test_identifiers_text_and_binary_outcomes_are_refused(self):
        frame = synthetic()
        frame["participant_id"] = range(len(frame))
        with self.assertRaises(ValueError):
            fit_process(frame, ProcessSpec("4", "participant_id", "y", ("m1",)))
        frame["y_text"] = frame["y"].astype(str)
        frame.loc[5, "y_text"] = "high"
        with self.assertRaises(ValueError):
            fit_process(frame, ProcessSpec("4", "x", "y_text", ("m1",)))
        frame["y01"] = (frame["y"] > frame["y"].median()).astype(float)
        with self.assertRaises(ValueError) as caught:
            fit_process(frame, ProcessSpec("4", "x", "y01", ("m1",)))
        self.assertIn("logistic", str(caught.exception))


# ------------------------------------------------------------------ OLS oracle
class EquationOracleTests(Case):
    """Every equation of every model against statsmodels formulas and numpy."""

    def check_model(self, name: str):
        spec = SPECS[name]
        result = self.fit(name)
        data, centring = centred_frame(synthetic(missing=True), spec)
        self.assertEqual(result.n, len(data))
        for equation in result.equations:
            outcome, formula, _ = formula_terms(spec, equation.key, centring)
            fit = smf.ols(formula, data=data).fit()
            ref = fit.get_robustcov_results(cov_type="HC3", use_t=True) if spec.hc3 else fit
            self.assertEqual(len(ref.params), len(equation.coefficients), formula)
            for c, b, se, p in zip(equation.coefficients, ref.params, ref.bse, ref.pvalues):
                self.assertClose(c.b, b, msg=f"{name} {equation.key} b {c.term}")
                self.assertClose(c.se, se, msg=f"{name} {equation.key} se {c.term}")
                self.assertClose(c.p, p, rel=1e-7, abs_tol=1e-14, msg=f"{name} p {c.term}")
            low, high = np.asarray(ref.conf_int(alpha=0.05)).T
            for c, lo, hi in zip(equation.coefficients, low, high):
                self.assertClose(c.ci_low, lo, msg=f"{name} ci low {c.term}")
                self.assertClose(c.ci_high, hi, msg=f"{name} ci high {c.term}")
            self.assertClose(equation.r_squared, fit.rsquared, msg="R2")
            self.assertClose(equation.adj_r_squared, fit.rsquared_adj, msg="adj R2")
            self.assertClose(equation.f_value, fit.fvalue, msg="F")
            self.assertEqual((equation.df_model, equation.df_resid),
                             (int(fit.df_model), int(fit.df_resid)))
            # numpy closed form: β = (X'X)⁻¹X'y, classical and HC3 covariance.
            matrix = np.asarray(fit.model.exog)
            beta, classical, hc3, resid, hat = numpy_ols(matrix, data[outcome].to_numpy())
            cov = hc3 if spec.hc3 else classical
            np.testing.assert_allclose([c.b for c in equation.coefficients], beta, rtol=1e-9,
                                       atol=1e-10)
            np.testing.assert_allclose([c.se for c in equation.coefficients],
                                       np.sqrt(np.diag(cov)), rtol=1e-9)
            np.testing.assert_allclose(equation.cov, cov, rtol=1e-8, atol=1e-14)
            # Diagnostics written out: leverage, Cook's D, Breusch–Pagan (Koenker),
            # Shapiro–Wilk of the residuals.
            n, p = matrix.shape
            s2 = resid @ resid / (n - p)
            cooks = resid ** 2 * hat / (p * s2 * (1 - hat) ** 2)
            np.testing.assert_allclose(equation.leverage, hat, rtol=1e-9)
            np.testing.assert_allclose(equation.cooks, cooks, rtol=1e-8)
            self.assertEqual(equation.cooks_over, int(np.sum(cooks > 4 / n)))
            self.assertEqual(equation.leverage_over, int(np.sum(hat > 2 * p / n)))
            aux = np.linalg.lstsq(matrix, resid ** 2, rcond=None)[0]
            fitted = matrix @ aux
            r2 = 1 - np.sum((resid ** 2 - fitted) ** 2) / np.sum((resid ** 2 - np.mean(resid ** 2)) ** 2)
            self.assertClose(equation.bp_p, stats.chi2.sf(n * r2, p - 1), rel=1e-7, msg="BP")
            self.assertClose(equation.shapiro_p, stats.shapiro(resid).pvalue, rel=1e-6,
                             msg="Shapiro")
            # VIF by statsmodels' own routine (1 / (1 - R²) of each column on the rest).
            for j, c in enumerate(equation.coefficients[1:], start=1):
                if len(equation.coefficients) > 2:
                    self.assertClose(c.vif, variance_inflation_factor(matrix, j), rel=1e-8,
                                     msg=f"VIF {c.term}")

    def test_model_4_parallel_with_covariates(self):
        self.check_model("4")

    def test_model_4_simple(self):
        self.check_model("4-simple")

    def test_model_1_and_centred_hc3(self):
        self.check_model("1")
        self.check_model("1-centred-hc3")

    def test_model_7_one_and_two_mediators(self):
        self.check_model("7")
        self.check_model("7-two")

    def test_model_14_hc3_and_two_centred_mediators(self):
        self.check_model("14")
        self.check_model("14-two-centred")

    def test_every_equation_uses_the_same_complete_cases(self):
        frame = synthetic(missing=True)
        for name in SPECS:
            result = self.fit(name)
            expected = len(complete(frame, SPECS[name]))
            self.assertEqual({e.n for e in result.equations}, {expected}, name)
            self.assertEqual(result.missing.n_complete, expected)
            self.assertEqual(result.missing.policy, "listwise")
            counts = dict(result.missing.by_variable)
            for variable in SPECS[name].variables():
                self.assertEqual(counts[variable], int(frame[variable].isna().sum()))

    def test_standardized_coefficients_match_a_regression_of_z_scores(self):
        spec = ProcessSpec("4", "x", "y", ("m1", "m2"), covariates=("age",), resamples=200)
        frame = synthetic()
        result = fit_process(frame, spec)
        z = (frame - frame.mean()) / frame.std(ddof=1)
        fit = smf.ols("y ~ x + m1 + m2 + age", data=z).fit()
        y_eq = result.equation("y")
        for name in ("x", "m1", "m2", "age"):
            coefficient = next(c for c in y_eq.coefficients if c.term == name)
            self.assertClose(coefficient.beta, fit.params[name], msg=f"beta {name}")
        # Not defined for the constant, products and 0/1 predictors.
        model1 = self.fit("1")
        betas = {c.key: c.beta for c in model1.equation("y").coefficients}
        self.assertIsNone(betas["const"])
        self.assertIsNone(betas["x*w"])
        self.assertIsNone(betas["c1"])          # employed is 0/1


# ------------------------------------------------------------------ closed forms
class ClosedFormTests(Case):
    def test_simple_mediation_paths_from_correlations(self):
        frame = synthetic()
        result = fit_process(frame, ProcessSpec("4", "x", "y", ("m1",), resamples=200))
        x, m, y = (frame[c].to_numpy() for c in ("x", "m1", "y"))
        sx, sm_, sy = (v.std(ddof=1) for v in (x, m, y))
        rxm, rxy, rmy = (np.corrcoef(u, v)[0, 1] for u, v in ((x, m), (x, y), (m, y)))
        a = rxm * sm_ / sx
        b = (rmy - rxy * rxm) / (1 - rxm ** 2) * sy / sm_
        c_prime = (rxy - rmy * rxm) / (1 - rxm ** 2) * sy / sx
        c = rxy * sy / sx
        self.assertClose(result.estimate("a:m0").value, a, msg="a")
        self.assertClose(result.estimate("b:m0").value, b, msg="b")
        self.assertClose(result.estimate("direct").value, c_prime, msg="c'")
        self.assertClose(result.estimate("total").value, c, msg="c")
        self.assertClose(result.estimate("indirect:m0").value, a * b, msg="ab")

    def test_total_equals_direct_plus_indirect_with_covariates(self):
        result = self.fit("4")
        indirect = sum(result.estimate(f"indirect:m{j}").value for j in range(2))
        self.assertClose(result.estimate("total").value,
                         result.estimate("direct").value + indirect, rel=1e-10, msg="c = c'+Σab")
        self.assertClose(result.estimate("indirect_total").value, indirect, msg="total indirect")
        x_sd, y_sd = result.sds["x"], result.sds["y"]
        self.assertClose(result.estimate("indirect_std:m0").value,
                         result.estimate("indirect:m0").value * x_sd / y_sd, msg="std")

    def test_conditional_effect_is_the_slope_of_x_after_shifting_w(self):
        """θ(w0) and its SE equal the coefficient of X (and its SE) in the same
        model refitted with W − w0 in place of W (classical and HC3)."""
        for name in ("1", "1-centred-hc3"):
            spec = SPECS[name]
            result = self.fit(name)
            data = complete(synthetic(missing=True), spec)
            for estimate in result.conditional:
                shifted = data.assign(ws=data["w"] - estimate.w)
                fit = smf.ols("y ~ x + ws + I(x * ws) + age + employed", data=shifted).fit()
                ref = fit.get_robustcov_results(cov_type="HC3", use_t=True) if spec.hc3 else fit
                self.assertClose(estimate.value, np.asarray(ref.params)[1], msg=f"theta {estimate.where}")
                self.assertClose(estimate.se, np.asarray(ref.bse)[1], msg=f"se {estimate.where}")
                self.assertClose(estimate.p, np.asarray(ref.pvalues)[1], rel=1e-7, msg="p")

    def test_the_interaction_test_and_effect_sizes(self):
        result = self.fit("1")
        data = complete(synthetic(missing=True), SPECS["1"])
        full = smf.ols("y ~ x + w + I(x * w) + age + employed", data=data).fit()
        reduced = smf.ols("y ~ x + w + age + employed", data=data).fit()
        test = result.interactions[0]
        delta = full.rsquared - reduced.rsquared
        self.assertClose(test.delta_r2, delta, msg="ΔR²")
        self.assertClose(test.f_value, np.asarray(full.tvalues)[3] ** 2, msg="F = t²")
        self.assertClose(test.p, np.asarray(full.pvalues)[3], rel=1e-7, msg="p")
        self.assertClose(test.f2, delta / (1 - full.rsquared), msg="f²")
        anova = sm.stats.anova_lm(reduced, full)
        self.assertClose(test.f_value, anova["F"].iloc[1], msg="anova F")
        robust = self.fit("1-centred-hc3").interactions[0]
        hc3 = smf.ols("y ~ x + w + I(x * w) + age + employed", data=data).fit(
            cov_type="HC3", use_t=True)
        self.assertClose(robust.robust_f, np.asarray(hc3.tvalues)[3] ** 2, msg="HC3 F = t²")
        self.assertClose(robust.delta_r2, test.delta_r2, msg="centring does not change ΔR²")

    def test_centring_changes_no_conditional_quantity(self):
        frame = synthetic(missing=True)
        for model, mediators in (("1", ()), ("7", ("m1",)), ("14", ("m1",))):
            plain = fit_process(frame, ProcessSpec(model, "x", "y", mediators, w="w",
                                                   covariates=COVARIATES, resamples=400))
            centred = fit_process(frame, ProcessSpec(model, "x", "y", mediators, w="w",
                                                     covariates=COVARIATES, resamples=400,
                                                     center=True))
            for a, b in zip(plain.conditional, centred.conditional):
                self.assertClose(a.value, b.value, rel=1e-8, msg=f"{model} {a.key}")
                self.assertClose(a.se, b.se, rel=1e-7, msg=f"{model} se {a.key}")
            for a, b in zip(plain.indirect, centred.indirect):
                self.assertClose(a.value, b.value, rel=1e-8, msg=f"{model} {a.key}")
                # The same resamples: the bootstrap limits agree as well.
                self.assertClose(a.ci_low, b.ci_low, rel=1e-7, abs_tol=1e-10, msg="ci low")
                self.assertClose(a.ci_high, b.ci_high, rel=1e-7, abs_tol=1e-10, msg="ci high")
            products = [e for e in plain.effects if e.key.startswith("interaction")]
            again = {e.key: e for e in centred.effects}
            for e in products:
                self.assertClose(e.value, again[e.key].value, rel=1e-8, msg="product")

    def test_model_7_and_14_conditional_indirect_effects_and_indices(self):
        for name in ("7", "14"):
            result = self.fit(name)
            m_eq, y_eq = result.equation("m0"), result.equation("y")
            centre = result.centering.get("w", 0.0)
            if name == "7":
                a1, a3 = m_eq.coefficient("x").b, m_eq.coefficient("x*w").b
                b = y_eq.coefficient("m0").b
                self.assertClose(result.estimate("index:m0").value, a3 * b, msg="index 7")
                for e in result.indirect:
                    if e.key.startswith("cond_indirect"):
                        self.assertClose(e.value, (a1 + a3 * (e.w - centre)) * b, msg=e.key)
                # The a path at w equals the analytic conditional effect.
                for e in result.conditional:
                    self.assertClose(e.value, a1 + a3 * (e.w - centre), msg="a(w)")
            else:
                a = m_eq.coefficient("x").b
                b1, b3 = y_eq.coefficient("m0").b, y_eq.coefficient("m0*w").b
                self.assertClose(result.estimate("index:m0").value, a * b3, msg="index 14")
                for e in result.indirect:
                    if e.key.startswith("cond_indirect"):
                        self.assertClose(e.value, a * (b1 + b3 * (e.w - centre)), msg=e.key)

    def test_conditioning_values_of_w(self):
        result = self.fit("1")
        w = complete(synthetic(missing=True), SPECS["1"])["w"].to_numpy()
        values = {p.where: p.value for p in result.w_points}
        self.assertClose(values["w.mean"], w.mean(), msg="mean")
        self.assertClose(values["w.minus"], w.mean() - w.std(ddof=1), msg="-1 SD")
        self.assertClose(values["w.plus"], w.mean() + w.std(ddof=1), msg="+1 SD")
        # Type 7 written out: h = (n − 1)p, interpolate between order statistics.
        ordered = np.sort(w)
        for key, q in (("w.p16", 0.16), ("w.p50", 0.5), ("w.p84", 0.84)):
            h = (len(w) - 1) * q
            lo = int(math.floor(h))
            expected = ordered[lo] + (h - lo) * (ordered[min(lo + 1, len(w) - 1)] - ordered[lo])
            self.assertClose(values[key], expected, msg=key)
        # A two-valued moderator is evaluated at its two values; no JN.
        frame = synthetic()
        frame["w2"] = (frame["w"] > 4).astype(float)
        binary = fit_process(frame, ProcessSpec("1", "x", "y", w="w2"))
        self.assertEqual([(p.where, p.value) for p in binary.w_points],
                         [("w.low", 0.0), ("w.high", 1.0)])
        self.assertIsNone(binary.johnson_neyman)
        # A value chosen by the researcher outside the data is kept and flagged.
        chosen = fit_process(frame, ProcessSpec("1", "x", "y", w="w", w_values=(99.0,)))
        self.assertTrue(chosen.w_points[-1].outside)
        self.assertTrue(any(k == "warn.w_outside" for k, _ in chosen.notes))


# ------------------------------------------------------------------ Johnson–Neyman
class JohnsonNeymanTests(Case):
    def jn_frame(self, seed=7):
        rng = np.random.default_rng(seed)
        n = 200
        x, w = rng.normal(0, 1, n), rng.normal(0, 1, n)
        y = 0.25 * x + 0.35 * x * w + 0.2 * w + rng.normal(0, 1, n)
        return pd.DataFrame({"x": x, "w": w, "y": y, "age": rng.normal(25, 4, n)})

    def reference_roots(self, frame, hc3):
        fit = smf.ols("y ~ x + w + I(x * w) + age", data=frame).fit()
        if hc3:
            fit = fit.get_robustcov_results(cov_type="HC3", use_t=True)
        t_crit = stats.t.ppf(0.975, fit.df_resid)

        def excess(w0):
            contrast = np.array([0.0, 1.0, 0.0, w0, 0.0])
            return abs(float(np.squeeze(fit.t_test(contrast).tvalue))) - t_crit

        grid = np.linspace(frame["w"].min(), frame["w"].max(), 2001)
        values = [excess(v) for v in grid]
        roots = [optimize.brentq(excess, grid[i], grid[i + 1], xtol=1e-13)
                 for i in range(len(grid) - 1) if np.sign(values[i]) != np.sign(values[i + 1])]
        return roots, fit, excess

    def test_closed_form_roots_match_a_root_finder_on_statsmodels_contrasts(self):
        for hc3 in (False, True):
            frame = self.jn_frame()
            result = fit_process(frame, ProcessSpec("1", "x", "y", w="w", covariates=("age",),
                                                    hc3=hc3))
            roots, fit, excess = self.reference_roots(frame, hc3)
            jn = result.johnson_neyman
            self.assertEqual(len(jn.points), len(roots), f"hc3={hc3}")
            self.assertGreaterEqual(len(roots), 1)
            for point, root, (effect, se, p) in zip(jn.points, roots, jn.effects):
                self.assertClose(point, root, rel=1e-8, abs_tol=1e-9, msg="JN point")
                self.assertAlmostEqual(p, 0.05, places=9)
                self.assertAlmostEqual(excess(point), 0.0, places=8)
            w = frame["w"].to_numpy()
            for point, below in zip(jn.points, jn.below):
                self.assertAlmostEqual(below, float(np.mean(w < point)))

    def test_centring_does_not_move_the_johnson_neyman_values(self):
        frame = self.jn_frame()
        plain = fit_process(frame, ProcessSpec("1", "x", "y", w="w")).johnson_neyman
        centred = fit_process(frame, ProcessSpec("1", "x", "y", w="w", center=True)).johnson_neyman
        np.testing.assert_allclose(plain.points, centred.points, rtol=1e-8)

    def test_no_root_in_range_reports_the_state_over_the_range(self):
        rng = np.random.default_rng(11)
        n = 150
        x, w = rng.normal(0, 1, n), rng.uniform(0, 1, n)
        frame = pd.DataFrame({"x": x, "w": w, "y": 0.8 * x + 0.01 * x * w + rng.normal(0, 1, n)})
        jn = fit_process(frame, ProcessSpec("1", "x", "y", w="w")).johnson_neyman
        fit = smf.ols("y ~ x + w + I(x * w)", data=frame).fit()
        grid = np.linspace(w.min(), w.max(), 401)
        p = [float(np.squeeze(fit.t_test(np.array([0, 1, 0, v])).pvalue)) for v in grid]
        self.assertEqual(jn.points, ())
        self.assertTrue(jn.significant_everywhere)
        self.assertTrue(all(value < 0.05 for value in p))


# ------------------------------------------------------------------ bootstrap
def oracle_draws(frame: pd.DataFrame, spec: ProcessSpec, indices: np.ndarray,
                 w_values=()) -> dict[str, np.ndarray]:
    """The bootstrap, re-implemented with numpy only: its own design
    matrices, QR solves, and the same resample indices."""
    data = complete(frame, spec)
    cols = {name: data[name].to_numpy(dtype=float) for name in data.columns}
    centre = {}
    if spec.center:
        names = ["x", "w"] if spec.model in ("1", "7") else [*spec.mediators, "w"]
        centre = {name: cols[name].mean() for name in names}

    def c(name, rows):
        return cols[name][rows] - centre.get(name, 0.0)

    def qr_solve(matrix, outcome):
        q, r = np.linalg.qr(matrix)
        return np.linalg.solve(r, q.T @ outcome)

    covs = list(spec.covariates)
    out: dict[str, list] = {}
    for rows in indices:
        one = np.ones(len(rows))
        cov_cols = [cols[v][rows] for v in covs]
        if spec.model == "4":
            y_coef = qr_solve(np.column_stack([one, cols["x"][rows],
                                               *[cols[m][rows] for m in spec.mediators],
                                               *cov_cols]), cols["y"][rows])
            sd_ratio = cols["x"][rows].std(ddof=1) / cols["y"][rows].std(ddof=1)
            total = 0.0
            for j, m in enumerate(spec.mediators):
                a = qr_solve(np.column_stack([one, cols["x"][rows], *cov_cols]), cols[m][rows])[1]
                value = a * y_coef[2 + j]
                out.setdefault(f"indirect:m{j}", []).append(value)
                out.setdefault(f"indirect_std:m{j}", []).append(value * sd_ratio)
                total += value
            if len(spec.mediators) > 1:
                out.setdefault("indirect_total", []).append(total)
                out.setdefault("indirect_std_total", []).append(total * sd_ratio)
        elif spec.model == "7":
            y_coef = qr_solve(np.column_stack([one, c("x", rows),
                                               *[cols[m][rows] for m in spec.mediators],
                                               *cov_cols]), cols["y"][rows])
            for j, m in enumerate(spec.mediators):
                xc, wc = c("x", rows), c("w", rows)
                a = qr_solve(np.column_stack([one, xc, wc, xc * wc, *cov_cols]), cols[m][rows])
                b = y_coef[2 + j]
                out.setdefault(f"index:m{j}", []).append(a[3] * b)
                for where, value in w_values:
                    out.setdefault(f"cond:{j}:{where}", []).append(
                        (a[1] + a[3] * (value - centre.get("w", 0.0))) * b)
        else:
            k = len(spec.mediators)
            wc = c("w", rows)
            mcs = [c(m, rows) for m in spec.mediators]
            y_coef = qr_solve(np.column_stack([one, cols["x"][rows], *mcs, wc,
                                               *[m * wc for m in mcs], *cov_cols]),
                              cols["y"][rows])
            for j, m in enumerate(spec.mediators):
                a = qr_solve(np.column_stack([one, cols["x"][rows], *cov_cols]), cols[m][rows])[1]
                b1, b3 = y_coef[2 + j], y_coef[2 + k + 1 + j]
                out.setdefault(f"index:m{j}", []).append(a * b3)
                for where, value in w_values:
                    out.setdefault(f"cond:{j}:{where}", []).append(
                        a * (b1 + b3 * (value - centre.get("w", 0.0))))
    return {key: np.asarray(values) for key, values in out.items()}


def type7(values: np.ndarray, q: float) -> float:
    ordered = np.sort(values)
    h = (len(ordered) - 1) * q
    lo = int(math.floor(h))
    hi = min(lo + 1, len(ordered) - 1)
    return float(ordered[lo] + (h - lo) * (ordered[hi] - ordered[lo]))


class BootstrapOracleTests(Case):
    def test_indices_come_from_one_seeded_draw(self):
        indices = pm.bootstrap_indices(160, 300, 99)
        expected = np.random.default_rng(99).integers(0, 160, size=(300, 160))
        np.testing.assert_array_equal(indices, expected)

    def compare(self, name):
        spec = SPECS[name]
        frame = synthetic(missing=True)
        result = self.fit(name)
        expected = np.random.default_rng(spec.seed).integers(0, result.n,
                                                             size=(spec.resamples, result.n))
        np.testing.assert_array_equal(result.indices, expected)
        points = [(p.where, p.value) for p in result.w_points]
        oracle = oracle_draws(frame, spec, expected, points)
        self.assertEqual(result.bootstrap.valid, spec.resamples)
        for estimate in result.indirect:
            key = estimate.key
            if key.startswith("cond_indirect:"):
                j = int(key.split(":m")[1].split("@")[0])
                oracle_key = f"cond:{j}:{estimate.where}"
                draws = oracle[oracle_key]
            else:
                draws = oracle[key]
            engine = result.samples[key]
            scale = max(1.0, float(np.max(np.abs(draws))))
            np.testing.assert_allclose(engine, draws, rtol=0, atol=BOOT * scale, err_msg=key)
            self.assertClose(estimate.ci_low, type7(draws, 0.025), rel=0, abs_tol=BOOT * scale,
                             msg=f"{name} {key} low")
            self.assertClose(estimate.ci_high, type7(draws, 0.975), rel=0, abs_tol=BOOT * scale,
                             msg=f"{name} {key} high")
            self.assertClose(estimate.se, np.std(draws, ddof=1), rel=1e-8, msg="boot SE")

    def test_model_4_parallel_with_covariates(self):
        self.compare("4")

    def test_model_7(self):
        self.compare("7")
        self.compare("7-two")

    def test_model_14(self):
        self.compare("14")
        self.compare("14-two-centred")

    def test_resamples_spot_checked_with_statsmodels(self):
        spec, result = SPECS["4"], self.fit("4")
        data = complete(synthetic(missing=True), spec)
        for r in (0, 17, 999):
            rows = data.iloc[result.indices[r]].reset_index(drop=True)
            a = smf.ols("m1 ~ x + age + employed", data=rows).fit().params["x"]
            b = smf.ols("y ~ x + m1 + m2 + age + employed", data=rows).fit().params["m1"]
            self.assertClose(result.samples["indirect:m0"][r], a * b, rel=1e-9, msg=f"r={r}")

    def test_the_same_seed_reproduces_and_another_seed_differs(self):
        frame = synthetic(missing=True)
        spec = SPECS["7"]
        first, again = fit_process(frame, spec), fit_process(frame, spec)
        self.assertEqual(first.bootstrap.indices_sha256, again.bootstrap.indices_sha256)
        for a, b in zip(first.indirect, again.indirect):
            self.assertEqual((a.ci_low, a.ci_high), (b.ci_low, b.ci_high))
        other = fit_process(frame, ProcessSpec(**{**spec.__dict__, "seed": spec.seed + 1}))
        self.assertNotEqual(first.bootstrap.indices_sha256, other.bootstrap.indices_sha256)
        self.assertNotEqual(first.estimate("index:m0").ci_low, other.estimate("index:m0").ci_low)
        # The point estimate does not depend on the seed.
        self.assertEqual(first.estimate("index:m0").value, other.estimate("index:m0").value)

    def test_singular_resamples_are_left_out_and_counted(self):
        rng = np.random.default_rng(5)
        n = 60
        frame = pd.DataFrame({"x": rng.normal(0, 1, n)})
        frame["m"] = 0.5 * frame["x"] + rng.normal(0, 1, n)
        frame["y"] = 0.5 * frame["m"] + rng.normal(0, 1, n)
        frame["rare"] = 0.0
        frame.loc[[4, 9], "rare"] = 1.0          # a covariate that many resamples miss
        spec = ProcessSpec("4", "x", "y", ("m",), covariates=("rare",), resamples=400)
        result = fit_process(frame, spec)
        indices = pm.bootstrap_indices(n, 400, spec.seed)
        varies = np.array([frame["rare"].to_numpy()[rows].std() > 0 for rows in indices])
        self.assertEqual(result.bootstrap.valid, int(varies.sum()))
        self.assertLess(result.bootstrap.valid, 400)
        self.assertIn("warn.boot_invalid", [k for k, _ in result.notes])
        oracle = oracle_draws(frame, spec, indices[varies])
        np.testing.assert_allclose(result.samples["indirect:m0"], oracle["indirect:m0"],
                                   rtol=0, atol=1e-10)

    def test_precomputed_indices_are_used_exactly(self):
        spec = SPECS["4-simple"]
        frame = synthetic()
        n = len(frame)
        indices = np.random.default_rng(123).integers(0, n, size=(1000, n))
        result = fit_process(frame, spec, indices=indices)
        oracle = oracle_draws(frame, spec, indices)
        np.testing.assert_allclose(result.samples["indirect:m0"], oracle["indirect:m0"],
                                   rtol=0, atol=1e-10)
        with self.assertRaises(ValueError):
            fit_process(frame, spec, indices=indices[:10])


# ------------------------------------------------------------------ missing data
class MissingDataTests(Case):
    def test_left_out_cases_are_compared_descriptively(self):
        frame = synthetic(missing=True)
        result = self.fit("7")
        names = SPECS["7"].variables()
        mask = frame[names].notna().all(axis=1)
        self.assertTrue(result.missing.comparison_meaningful)
        for name, n_in, m_in, sd_in, n_out, m_out, sd_out, smd in result.missing.comparison:
            inside, out = frame.loc[mask, name], frame.loc[~mask, name].dropna()
            self.assertEqual((n_in, n_out), (len(inside), len(out)))
            self.assertClose(m_in, inside.mean(), msg=f"mean in {name}")
            if len(out) >= 2:
                self.assertClose(m_out, out.mean(), msg=f"mean out {name}")
                self.assertClose(smd, (out.mean() - inside.mean()) / inside.std(ddof=1),
                                 msg=f"SMD {name}")
        self.assertIn("warn.listwise", [k for k, _ in result.notes])

    def test_one_left_out_case_is_not_compared(self):
        frame = synthetic()
        frame.loc[7, "m1"] = np.nan
        result = fit_process(frame, ProcessSpec("4", "x", "y", ("m1",), resamples=200))
        self.assertFalse(result.missing.comparison_meaningful)
        self.assertEqual(result.missing.comparison, ())
        self.assertIn("warn.excluded_few", [k for k, _ in result.notes])


# ------------------------------------------------------------------ sensitivity simulation
class SensitivitySimulationTests(Case):
    def test_model_1_type_one_error_and_analytic_power(self):
        """The simulated detection rate of the product term against the
        noncentral-t power of the same test at the analysis design.

        Tolerance: binomial Monte Carlo SE (≤ .011 at 2000 replications) times
        3, plus .02 for resampling the design rows (the analytic value holds
        the design fixed)."""
        frame = synthetic()
        result = fit_process(frame, ProcessSpec("1", "x", "y", w="w", covariates=COVARIATES))
        sim = pm.sensitivity_simulation(result, replications=2000, grid=(0.0, 0.15), seed=4)
        rows = {row.assumed: row for row in sim.rows}
        null = rows[0.0]
        self.assertLess(abs(null.power - 0.05), 3 * math.sqrt(0.05 * 0.95 / 2000) + 0.005)
        equation = result.equation("y")
        sds = result.sds
        b3 = 0.15 * sds["y"] / (sds["x"] * sds["w"])
        matrix = np.column_stack([np.ones(result.n), result.data["x"], result.data["w"],
                                  result.data["x"] * result.data["w"], result.data["age"],
                                  result.data["employed"]])
        se = math.sqrt(equation.mse * np.linalg.inv(matrix.T @ matrix)[3, 3])
        df = equation.df_resid
        t_crit = stats.t.ppf(0.975, df)
        power = stats.nct.sf(t_crit, df, b3 / se) + stats.nct.cdf(-t_crit, df, b3 / se)
        self.assertLess(abs(rows[0.15].power - power), 3 * rows[0.15].mc_se + 0.02,
                        (rows[0.15].power, power))

    def test_detection_grows_with_the_assumed_value_and_is_reproducible(self):
        result = self.fit("7")
        first = pm.sensitivity_simulation(result, replications=150, seed=8)
        again = pm.sensitivity_simulation(result, replications=150, seed=8)
        self.assertEqual(first, again)
        powers = [row.power for row in first.rows]
        self.assertLess(powers[0], powers[-1])
        self.assertEqual({row.n for row in first.rows}, {result.n})
        self.assertEqual(first.test, "mc")
        model4 = pm.sensitivity_simulation(self.fit("4"), replications=60, seed=3)
        self.assertEqual({row.focal_key for row in model4.rows},
                         {"indirect:m0", "indirect:m1"})
        with self.assertRaises(ValueError):
            pm.sensitivity_simulation(result, replications=5)

    def test_the_simulation_is_labelled_as_assumed_values_not_observed_power(self):
        from process_reporting import sensitivity_note, sensitivity_table

        result = self.fit("14")
        sim = pm.sensitivity_simulation(result, replications=40, seed=2)
        for language in ("en", "lv", "ru"):
            note = sensitivity_note(result, sim, language)
            self.assertIn("40", note)
            self.assertIn(str(sim.seed), note)
        self.assertIn("not ‘observed power’", sensitivity_note(result, sim, "en"))
        self.assertIn("not a result about these data", sensitivity_table(result, sim).title)


# ------------------------------------------------------------------ structured result
class StructuredResultTests(Case):
    def test_the_structured_result_round_trips_and_keeps_its_intervals(self):
        from result_store import from_json, to_json
        from stat_results import StructuredResult

        result = self.fit("4")
        structured = result.structured()
        again = StructuredResult.from_dict(json.loads(json.dumps(structured.to_dict())))
        self.assertEqual(again, structured)
        indirect = again.quantity("indirect:m0")
        estimate = result.estimate("indirect:m0")
        self.assertEqual((indirect.value, indirect.ci_low, indirect.ci_high),
                         (estimate.value, estimate.ci_low, estimate.ci_high))
        self.assertIn("percentile bootstrap", indirect.ci_method)
        self.assertEqual(again.provenance["seed"], pm.DEFAULT_SEED)
        self.assertEqual(again.provenance["resamples"], 1000)
        stored = to_json(result)
        self.assertEqual(stored["kind"], "structured")
        self.assertEqual(from_json(stored), structured)


# ------------------------------------------------------------------ fixture sign check
class FixtureSignTests(Case):
    """Sanity only: the generator's latent coefficients are not sample
    estimates; only their signs are compared."""

    def test_the_sample_estimates_have_the_generators_signs(self):
        sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "stage37"))
        import generate_master_fixture as fixture

        with tempfile.TemporaryDirectory() as folder:
            csv_path, spec_path = fixture.generate(Path(folder))
            frame = pd.read_csv(csv_path)
            model = json.loads(spec_path.read_text(encoding="utf-8"))
        x, m, w, y = (model[k].split()[0] for k in ("X", "M", "W", "Y"))
        mediation = fit_process(frame, ProcessSpec("4", x, y, (m,), resamples=500))
        self.assertGreater(mediation.estimate("a:m0").value, 0)    # +0.36·X in M
        self.assertGreater(mediation.estimate("b:m0").value, 0)    # +0.30·M in Y
        self.assertLess(mediation.estimate("direct").value, 0)     # −0.45·X in Y
        moderation = fit_process(frame, ProcessSpec("1", x, y, w=w))
        self.assertGreater(moderation.estimate("interaction").value, 0)   # +0.19·X·W in Y
        first_stage = fit_process(frame, ProcessSpec("7", x, y, (m,), w=w, resamples=500))
        self.assertGreater(first_stage.equation("m0").coefficient("x*w").b, 0)   # +0.18·X·W


if __name__ == "__main__":
    unittest.main()
