"""Engine ground truth (issue #32): workspace numbers vs independent references.

``test_analysis_runs.py`` proves that the workspace path reproduces the
classic screens. This file checks the numbers themselves. Every analysis
runs through ``workspace_methods.run_method`` -- the workspace's entry
point, on a ``ResearchSession`` whose measurement levels are confirmed the
way a researcher confirms them -- on synthetic data drawn from fixed
``numpy.random.default_rng`` seeds. The engine's result object (and the
interpretation evidence built from it) is compared with an INDEPENDENT
computation: a closed-form formula written out here, numpy linear algebra,
or a different statsmodels routine than the one the engine calls. Only
fictional, simulated data appear in this file.

Where several conventions are legitimate (zero and tie handling, Monte
Carlo p-values, which sums of squares, a library's rounding), each test
names the engine's convention and matches it; where it is cheap, the test
also shows that the alternative convention gives a different number, so a
silent change of convention fails here.

Tolerances
* EXACT (relative 1e-9): the same estimator computed by independent code.
  Floating-point reordering leaves relative differences near 1e-13, while
  every change of convention probed here (ddof, degrees of freedom, tie or
  continuity correction, zero handling, type I vs II sums of squares,
  pairwise vs listwise deletion) moves the result by at least 1e-3
  relative on these data -- the assertGreater checks next to the matches.
* SHOWN (5e-4): evidence rows display three decimals, so a displayed value
  may differ from the full-precision reference by half a unit in the third
  decimal (SHOWN_2DP: tables that display two decimals).
* Sampling tolerances (omega, factor loadings, Monte Carlo p-values) are
  justified next to the test that uses them.
"""

from __future__ import annotations

from itertools import combinations, permutations, product
import math
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import linalg, stats  # noqa: E402
import statsmodels.api as sm  # noqa: E402
import statsmodels.formula.api as smf  # noqa: E402
from statsmodels.stats.anova import AnovaRM, anova_lm  # noqa: E402
from statsmodels.stats.multitest import multipletests  # noqa: E402
from statsmodels.stats.oneway import anova_oneway  # noqa: E402

from analysis_runs import run_posthoc  # noqa: E402
from posthoc_analysis import analyze_posthoc  # noqa: E402
from workspace_methods import (  # noqa: E402
    METHODS, default_options, required_confirmations, run_method,
)
from workspace_state import ResearchSession  # noqa: E402

EXACT = 1e-9
SHOWN = 5e-4 + 1e-12
SHOWN_2DP = 5e-3 + 1e-12


# ------------------------------------------------------------------ helpers
def workspace_run(key, frame, levels, roles, **options):
    """Run ``key`` exactly as the workspace does: a session holding the
    dataset, researcher-confirmed levels, and every confirmation the chosen
    options require (``required_confirmations``)."""
    session = ResearchSession()
    session.set_dataset(frame, "synthetic_ground_truth.csv")
    for name, level in levels.items():
        session.confirm_level(name, level)
    spec = METHODS[key]
    chosen = {**default_options(spec), **options}
    confirms = {c.key: True for c in required_confirmations(spec, chosen)}
    return run_method(key, session, roles, chosen, confirms)


def holm(pvalues):
    return multipletests(list(pvalues), method="holm")[1]


def group_samples(frame, group, outcome):
    """Groups in the engine's order (labels sorted as text)."""
    labels = sorted(frame[group].map(str).unique())
    return labels, [frame.loc[frame[group].map(str) == g, outcome].to_numpy(float)
                    for g in labels]


def shuffled(frame, rng):
    return frame.iloc[rng.permutation(len(frame))].reset_index(drop=True)


def treatment_contrast(fit, first, second, factor="C(group)"):
    """Parameter vector of (second - first) between two levels of a
    treatment-coded factor (the reference level has no coefficient)."""
    names = list(fit.params.index)
    vector = np.zeros(len(names))
    for label, sign in ((second, 1.0), (first, -1.0)):
        name = f"{factor}[T.{label}]"
        if name in names:
            vector[names.index(name)] += sign
    return vector


def welch_anova_reference(samples):
    """Welch (1951) heteroscedastic one-way ANOVA, written out."""
    k = len(samples)
    n = np.array([s.size for s in samples], dtype=float)
    means = np.array([s.mean() for s in samples])
    weights = n / np.array([s.var(ddof=1) for s in samples])
    weighted_mean = np.sum(weights * means) / weights.sum()
    between = np.sum(weights * (means - weighted_mean) ** 2) / (k - 1)
    lam = np.sum((1 - weights / weights.sum()) ** 2 / (n - 1))
    f_value = between / (1 + 2 * (k - 2) / (k ** 2 - 1) * lam)
    df2 = (k ** 2 - 1) / (3 * lam)
    return f_value, float(k - 1), df2, stats.f.sf(f_value, k - 1, df2)


def kruskal_reference(samples):
    """Tie-corrected Kruskal-Wallis H from average ranks, the uncorrected H,
    and Kelley's epsilon-squared of a one-way ANOVA on those ranks."""
    values = np.concatenate(samples)
    total, k = values.size, len(samples)
    ranks = stats.rankdata(values)
    bounds = np.cumsum([0, *[s.size for s in samples]])
    by_group = [ranks[a:b] for a, b in zip(bounds[:-1], bounds[1:])]
    uncorrected = (12 / (total * (total + 1))
                   * sum(r.sum() ** 2 / r.size for r in by_group) - 3 * (total + 1))
    _, ties = np.unique(values, return_counts=True)
    h = uncorrected / (1 - np.sum(ties ** 3 - ties) / (total ** 3 - total))
    grand = ranks.mean()
    ss_between = sum(r.size * (r.mean() - grand) ** 2 for r in by_group)
    ss_total = np.sum((ranks - grand) ** 2)
    ms_within = (ss_total - ss_between) / (total - k)
    kelley = (ss_between - (k - 1) * ms_within) / ss_total
    return h, uncorrected, stats.chi2.sf(h, k - 1), kelley


def dunn_reference(samples):
    """Dunn (1964) z for every pair of groups (first minus second mean rank)
    with the global tie correction; raw two-sided normal p-values."""
    values = np.concatenate(samples)
    total = values.size
    ranks = stats.rankdata(values)
    _, ties = np.unique(values, return_counts=True)
    variance = total * (total + 1) / 12 - np.sum(ties ** 3 - ties) / (12 * (total - 1))
    bounds = np.cumsum([0, *[s.size for s in samples]])
    mean_ranks = [ranks[a:b].mean() for a, b in zip(bounds[:-1], bounds[1:])]
    out = []
    for i, j in combinations(range(len(samples)), 2):
        difference = mean_ranks[i] - mean_ranks[j]
        z = difference / math.sqrt(variance * (1 / samples[i].size + 1 / samples[j].size))
        out.append((difference, z, 2 * stats.norm.sf(abs(z))))
    return out


def studentized_range_pairs(samples, equal_var):
    """Tukey-Kramer (pooled MSE) or Games-Howell (Welch SE and df) pairwise
    p-values and simultaneous 95% intervals, from the studentized range."""
    k = len(samples)
    n = np.array([s.size for s in samples], dtype=float)
    means = np.array([s.mean() for s in samples])
    var = np.array([s.var(ddof=1) for s in samples])
    mse = np.sum((n - 1) * var) / (n.sum() - k)
    out = []
    for i, j in combinations(range(k), 2):
        if equal_var:
            se = math.sqrt(mse / 2 * (1 / n[i] + 1 / n[j]))
            dof = n.sum() - k
        else:
            a, b = var[i] / n[i], var[j] / n[j]
            se = math.sqrt((a + b) / 2)
            dof = (a + b) ** 2 / (a ** 2 / (n[i] - 1) + b ** 2 / (n[j] - 1))
        difference = means[i] - means[j]
        p = stats.studentized_range.sf(abs(difference) / se, k, dof)
        half = stats.studentized_range.ppf(0.95, k, dof) * se
        out.append((difference, p, difference - half, difference + half))
    return out


def signed_rank_exact(d):
    """Exact two-sided Wilcoxon signed-rank p for distinct nonzero
    differences: the null distribution of W+ over all 2**n equally likely
    sign patterns, built by dynamic programming over the ranks 1..n."""
    n = d.size
    ranks = stats.rankdata(np.abs(d))
    w_plus, w_minus = ranks[d > 0].sum(), ranks[d < 0].sum()
    counts = np.zeros(n * (n + 1) // 2 + 1)
    counts[0] = 1.0
    for rank in range(1, n + 1):
        moved = np.zeros_like(counts)
        moved[rank:] = counts[:-rank]
        counts = counts + moved
    pmf = counts / 2.0 ** n
    w = int(round(w_plus))
    p = min(1.0, 2 * min(pmf[:w + 1].sum(), pmf[w:].sum()))
    return w_plus, w_minus, p


def signed_rank_normal(d, zero_method="wilcox", continuity=False):
    """Normal approximation of the signed-rank test. ``wilcox`` drops zero
    differences before ranking; ``pratt`` ranks them and then drops their
    ranks. Tied |d| receive average ranks and the variance is tie-corrected.
    Returns (W+, W-, two-sided p)."""
    if zero_method == "wilcox":
        d = d[d != 0]
    ranks = stats.rankdata(np.abs(d))
    w_plus, w_minus = ranks[d > 0].sum(), ranks[d < 0].sum()
    n, zeros = d.size, int(np.count_nonzero(d == 0))
    mean = n * (n + 1) / 4 - zeros * (zeros + 1) / 4
    var = n * (n + 1) * (2 * n + 1) / 24 - zeros * (zeros + 1) * (2 * zeros + 1) / 24
    _, ties = np.unique(np.abs(d[d != 0]), return_counts=True)
    var -= np.sum(ties ** 3 - ties) / 48
    z = (w_plus - mean) / math.sqrt(var)
    if continuity:
        z -= np.sign(z) * 0.5 / math.sqrt(var)
    return w_plus, w_minus, 2 * stats.norm.sf(abs(z))


def signed_rank_sign_flips(d):
    """Permutation p of W+ by enumerating every sign pattern of the nonzero
    differences (zeros carry no rank and cannot change W+)."""
    nonzero = d[d != 0]
    ranks = stats.rankdata(np.abs(nonzero))
    observed = ranks[nonzero > 0].sum()
    null = np.array(list(product((0.0, 1.0), repeat=nonzero.size))) @ ranks
    lower = np.mean(null <= observed + 1e-9)
    upper = np.mean(null >= observed - 1e-9)
    return observed, ranks[nonzero < 0].sum(), min(1.0, 2 * min(lower, upper))


def friedman_reference(values):
    """Tie-corrected Friedman chi-square from within-row average ranks, the
    uncorrected statistic, and Kendall's W with its own tie correction
    (12 S / (n^2 (k^3 - k) - n sum(t^3 - t)))."""
    n, k = values.shape
    ranks = np.vstack([stats.rankdata(row) for row in values])
    rank_sums = ranks.sum(axis=0)
    ties = sum(float(np.sum(c ** 3 - c))
               for c in (np.unique(row, return_counts=True)[1] for row in values))
    uncorrected = 12 / (n * k * (k + 1)) * np.sum(rank_sums ** 2) - 3 * n * (k + 1)
    q = uncorrected / (1 - ties / (n * (k ** 3 - k)))
    spread = np.sum((rank_sums - n * (k + 1) / 2) ** 2)
    kendall_w = 12 * spread / (n ** 2 * (k ** 3 - k) - n * ties)
    return q, uncorrected, stats.chi2.sf(q, k - 1), kendall_w


def greenhouse_geisser(values):
    """Box/Greenhouse-Geisser epsilon from orthonormal (Helmert) contrasts:
    tr(S_c)^2 / ((k - 1) tr(S_c^2)), S_c = C S C'."""
    k = values.shape[1]
    contrasts = linalg.helmert(k)          # (k-1) x k, orthonormal, sums to 0
    s_c = contrasts @ np.cov(values, rowvar=False) @ contrasts.T
    return np.trace(s_c) ** 2 / ((k - 1) * np.trace(s_c @ s_c))


def cronbach_alpha(values):
    """k / (k - 1) * (1 - sum of item variances / variance of the total)."""
    k = values.shape[1]
    return k / (k - 1) * (1 - values.var(axis=0, ddof=1).sum()
                          / values.sum(axis=1).var(ddof=1))


def pearson_reference(x, y):
    """r from centred cross-products, t test on n - 2 df, Fisher-z 95% CI."""
    n = x.size
    xc, yc = x - x.mean(), y - y.mean()
    r = np.sum(xc * yc) / math.sqrt(np.sum(xc ** 2) * np.sum(yc ** 2))
    t = r * math.sqrt((n - 2) / (1 - r ** 2))
    half = stats.norm.ppf(0.975) / math.sqrt(n - 3)
    return (r, 2 * stats.t.sf(abs(t), n - 2),
            math.tanh(math.atanh(r) - half), math.tanh(math.atanh(r) + half))


def rank_correlation(x, y):
    """Spearman's rho as Pearson's r of average ranks (ties share a rank)."""
    return pearson_reference(stats.rankdata(x), stats.rankdata(y))[0]


def spearman_permutation_p(x, y, resamples, seed):
    """Independent Monte Carlo permutation p for Spearman's rho: shuffle one
    variable's ranks; two-sided as twice the smaller tail, counting the
    observed pairing once in each tail."""
    rx, ry = stats.rankdata(x), stats.rankdata(y)
    rx = (rx - rx.mean()) / np.linalg.norm(rx - rx.mean())
    ry = (ry - ry.mean()) / np.linalg.norm(ry - ry.mean())
    observed = rx @ ry
    null = np.random.default_rng(seed).permuted(np.tile(rx, (resamples, 1)), axis=1) @ ry
    greater = (np.sum(null >= observed - 1e-12) + 1) / (resamples + 1)
    less = (np.sum(null <= observed + 1e-12) + 1) / (resamples + 1)
    return min(1.0, 2 * min(greater, less))


def factor_items(rng, pattern, n, phi=None):
    """Standardized items from a common-factor model x = Lf + e with
    correlated (phi) or uncorrelated factors and unit item variances."""
    m = pattern.shape[1]
    phi = np.eye(m) if phi is None else phi
    factors = rng.multivariate_normal(np.zeros(m), phi, size=n)
    communality = np.einsum("ij,jk,ik->i", pattern, phi, pattern)
    noise = rng.standard_normal((n, pattern.shape[0])) * np.sqrt(1 - communality)
    return pd.DataFrame(factors @ pattern.T + noise,
                        columns=[f"item{j + 1}" for j in range(pattern.shape[0])])


def aligned_loadings(estimated, true):
    """Factors are identified only up to order and sign: return the largest
    absolute loading error after the best column order and signs, and the
    chosen order and signs."""
    best = None
    for order in permutations(range(true.shape[1])):
        candidate = estimated[:, order]
        signs = np.where(np.sum(candidate * true, axis=0) < 0, -1.0, 1.0)
        error = float(np.max(np.abs(candidate * signs - true)))
        if best is None or error < best[0]:
            best = (error, list(order), signs)
    return best


def kmo_by_regression(values):
    """Kaiser's KMO from partial correlations obtained as correlations of
    least-squares residuals (each pair regressed on all other items)."""
    n, k = values.shape
    corr = np.corrcoef(values, rowvar=False)
    partial = np.zeros((k, k))
    for i, j in combinations(range(k), 2):
        others = np.column_stack([np.ones(n), np.delete(values, [i, j], axis=1)])
        res_i = values[:, i] - others @ np.linalg.lstsq(others, values[:, i], rcond=None)[0]
        res_j = values[:, j] - others @ np.linalg.lstsq(others, values[:, j], rcond=None)[0]
        partial[i, j] = partial[j, i] = np.corrcoef(res_i, res_j)[0, 1]
    raw = corr ** 2
    np.fill_diagonal(raw, 0.0)
    part = partial ** 2
    item = raw.sum(axis=0) / (raw.sum(axis=0) + part.sum(axis=0))
    return raw.sum() / (raw.sum() + part.sum()), item


# ---------------------------------------------------------------- base case
class GroundTruthCase(unittest.TestCase):
    def assertClose(self, actual, expected, rel=EXACT, abs_tol=1e-12, msg="value"):
        actual, expected = float(actual), float(expected)
        if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_tol):
            self.fail(f"{msg}: engine {actual!r} vs reference {expected!r} "
                      f"(rel {rel:g}, abs {abs_tol:g})")

    def assertAllClose(self, actual, expected, rel=EXACT, abs_tol=1e-12, msg="values"):
        actual, expected = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
        self.assertEqual(actual.shape, expected.shape, msg)
        for index in np.ndindex(actual.shape):
            self.assertClose(actual[index], expected[index], rel, abs_tol,
                             f"{msg}{list(index)}")

    def evidence_row(self, run, parameter):
        for row in run.evidence().rows:
            if row.parameter == parameter:
                return row
        self.fail(f"{parameter!r} is missing from the interpretation evidence")

    def assertShown(self, run, parameter, expected, *, ci=None, p=None):
        """The evidence row displays the reference value (three decimals)."""
        row = self.evidence_row(run, parameter)
        self.assertLessEqual(abs(float(row.estimate) - expected), SHOWN,
                             f"{parameter}: shown {row.estimate}, reference {expected}")
        if ci is not None:
            low, high = (float(v) for v in row.ci.strip("[]").split(","))
            self.assertLessEqual(abs(low - ci[0]), SHOWN, f"{parameter} CI low {row.ci}")
            self.assertLessEqual(abs(high - ci[1]), SHOWN, f"{parameter} CI high {row.ci}")
        if p is not None:
            if p < 0.001:
                self.assertEqual(row.p, "< .001", parameter)
            else:
                self.assertTrue(row.p.startswith("= "), row.p)
                self.assertLessEqual(abs(float(row.p[2:]) - p), SHOWN,
                                     f"{parameter}: shown p {row.p}, reference {p}")

    def assertTableP(self, cell, p):
        """Post-hoc tables show p with three decimals or '< .001'."""
        if p < 0.001:
            self.assertEqual(cell, "< .001")
        else:
            self.assertLessEqual(abs(float(cell) - p), SHOWN, f"table p {cell} vs {p}")


# ------------------------------------------------------------------- ANCOVA
ANCOVA_LEVELS = {"wellbeing": "scale", "group": "nominal", "baseline": "scale", "age": "scale"}


def ancova_levels(frame):
    return {name: level for name, level in ANCOVA_LEVELS.items() if name in frame.columns}


def ancova_groups(rng):
    """Three unequal groups whose covariate levels differ, with one common
    slope: group and covariate are correlated, so the sequential (type I)
    and the covariate-adjusted (type II) group tests disagree."""
    parts = []
    for label, size, centre, shift in (("control", 34, 45.0, 0.0),
                                       ("coaching", 22, 50.0, 2.5),
                                       ("workshop", 28, 56.0, 4.0)):
        baseline = rng.normal(centre, 8.0, size)
        wellbeing = 5.0 + 0.6 * baseline + shift + rng.normal(0.0, 4.0, size)
        parts.append(pd.DataFrame({"group": label, "baseline": baseline,
                                   "wellbeing": wellbeing}))
    return shuffled(pd.concat(parts, ignore_index=True), rng)


class AncovaGroundTruth(GroundTruthCase):
    def check_groups_and_pairs(self, result, fit, grid, labels, raw):
        """Adjusted means = OLS predictions on ``grid``; pairs = contrasts
        (second minus first, as the engine's "first -> second" rows) with
        Holm-adjusted p-values from multipletests."""
        prediction = fit.get_prediction(grid)
        interval = np.asarray(prediction.conf_int(alpha=0.05))
        self.assertEqual([g.label for g in result.groups], labels)
        for i, group in enumerate(result.groups):
            self.assertClose(group.adjusted_mean, prediction.predicted_mean[i], msg="adj mean")
            self.assertClose(group.se, prediction.se_mean[i], msg="adj mean SE")
            self.assertClose(group.ci_low, interval[i, 0], msg="adj mean CI low")
            self.assertClose(group.ci_high, interval[i, 1], msg="adj mean CI high")
            self.assertClose(group.raw_mean, raw.loc[group.label].mean(), msg="raw mean")
            self.assertEqual(group.n, raw.loc[group.label].size)
        pairs = list(combinations(labels, 2))
        tests = [fit.t_test(treatment_contrast(fit, a, b)) for a, b in pairs]
        raw_p = [float(np.squeeze(t.pvalue)) for t in tests]
        for pair, (a, b), t, p, p_holm in zip(result.pairs, pairs, tests, raw_p, holm(raw_p)):
            low, high = np.squeeze(np.asarray(t.conf_int(alpha=0.05)))
            self.assertEqual((pair.first, pair.second), (a, b))
            self.assertClose(pair.difference, np.squeeze(t.effect), msg="pair difference")
            self.assertClose(pair.t, np.squeeze(t.tvalue), msg="pair t")
            self.assertClose(pair.p_raw, p, msg="pair raw p")
            self.assertClose(pair.p_holm, p_holm, msg="pair Holm p")
            self.assertClose(pair.ci_low, low, msg="pair CI low")
            self.assertClose(pair.ci_high, high, msg="pair CI high")

    def test_common_slope_ancova_matches_type_ii_ols_and_adjusted_predictions(self):
        frame = ancova_groups(np.random.default_rng(3201))
        run = workspace_run("ancova", frame, ancova_levels(frame),
                            {"outcome": "wellbeing", "group": "group",
                             "covariates": ["baseline"]}, mode="ancova")
        result = run.result
        fit = smf.ols("wellbeing ~ C(group) + baseline", data=frame).fit()
        table = anova_lm(fit, typ=2)
        group_row, ss_error = table.loc["C(group)"], table.loc["Residual", "sum_sq"]
        self.assertEqual((result.n_total, result.n_complete), (84, 84))
        self.assertEqual((result.df_group, result.df_error), (2, int(fit.df_resid)))
        self.assertClose(result.f_group, group_row["F"], msg="adjusted group F")
        self.assertClose(result.p_group, group_row["PR(>F)"], msg="adjusted group p")
        self.assertClose(result.eta_squared_partial,
                         group_row["sum_sq"] / (group_row["sum_sq"] + ss_error), msg="partial eta2")
        self.assertClose(result.r_squared, fit.rsquared, msg="R2")
        # The match is specific to adjusted (type II) sums of squares: the
        # sequential group-first F of the same model is far away.
        sequential = anova_lm(fit, typ=1).loc["C(group)", "F"]
        self.assertGreater(abs(sequential - result.f_group), 1.0)
        # Homogeneity-of-slopes check = the group x covariate term (type II)
        # of the full model; it is not significant, so ANCOVA is reported.
        slopes = anova_lm(smf.ols("wellbeing ~ C(group) * baseline", data=frame).fit(),
                          typ=2).loc["C(group):baseline"]
        self.assertEqual(result.df_interaction, int(slopes["df"]))
        self.assertClose(result.f_interaction, slopes["F"], msg="slopes F")
        self.assertClose(result.p_interaction, slopes["PR(>F)"], msg="slopes p")
        self.assertGreaterEqual(result.p_interaction, 0.05)
        # Adjusted means are predictions at the covariate's grand mean.
        labels = sorted(frame.group.unique())
        self.assertClose(result.reference_values["baseline"], frame.baseline.mean())
        grid = pd.DataFrame({"group": labels, "baseline": frame.baseline.mean()})
        self.check_groups_and_pairs(result, fit, grid, labels,
                                    frame.groupby("group").wellbeing.apply(np.asarray))
        self.assertShown(run, "Adjusted group F", group_row["F"], p=group_row["PR(>F)"])
        self.assertShown(run, "Partial η²", result.eta_squared_partial)
        self.assertShown(run, "Model R²", fit.rsquared)
        for group in result.groups:
            self.assertShown(run, f"Adjusted mean: {group.label}", group.adjusted_mean,
                             ci=(group.ci_low, group.ci_high))

    def test_two_covariates_adjust_at_complete_case_means(self):
        rng = np.random.default_rng(3202)
        parts = []
        for label, shift in (("control", 0.0), ("coaching", 1.5), ("workshop", 3.0)):
            baseline, age = rng.normal(50.0, 10.0, 30), rng.normal(40.0, 12.0, 30)
            wellbeing = 10.0 + 0.5 * baseline - 0.2 * age + shift + rng.normal(0.0, 3.0, 30)
            parts.append(pd.DataFrame({"group": label, "baseline": baseline, "age": age,
                                       "wellbeing": wellbeing}))
        frame = shuffled(pd.concat(parts, ignore_index=True), rng)
        frame.loc[[4, 37], "baseline"] = np.nan
        frame.loc[[61], "age"] = np.nan
        frame.loc[[12], "wellbeing"] = np.nan
        complete = frame.dropna()
        run = workspace_run("ancova", frame, ancova_levels(frame),
                            {"outcome": "wellbeing", "group": "group",
                             "covariates": ["baseline", "age"]}, mode="ancova")
        result = run.result
        # Listwise: one complete-case sample for the whole model.
        self.assertEqual((result.n_total, result.n_complete), (90, len(complete)))
        self.assertIn(f"{90 - len(complete)} rows excluded listwise", " ".join(result.warnings))
        fit = smf.ols("wellbeing ~ C(group) + baseline + age", data=complete).fit()
        table = anova_lm(fit, typ=2)
        group_row, ss_error = table.loc["C(group)"], table.loc["Residual", "sum_sq"]
        self.assertClose(result.f_group, group_row["F"], msg="adjusted group F")
        self.assertClose(result.p_group, group_row["PR(>F)"], msg="adjusted group p")
        self.assertClose(result.eta_squared_partial,
                         group_row["sum_sq"] / (group_row["sum_sq"] + ss_error), msg="partial eta2")
        self.assertClose(result.r_squared, fit.rsquared, msg="R2")
        # The reference is the COMPLETE-CASE mean of each covariate, which
        # differs from each column's own available-case mean here.
        for name in ("baseline", "age"):
            self.assertClose(result.reference_values[name], complete[name].mean(), msg=name)
            self.assertGreater(abs(frame[name].mean() - complete[name].mean()), 1e-3)
        labels = sorted(complete.group.unique())
        grid = pd.DataFrame({"group": labels, "baseline": complete.baseline.mean(),
                             "age": complete.age.mean()})
        self.check_groups_and_pairs(result, fit, grid, labels,
                                    complete.groupby("group").wellbeing.apply(np.asarray))

    def test_interaction_glm_matches_centred_statsmodels_model(self):
        rng = np.random.default_rng(3203)
        parts = []
        for label, shift, slope in (("control", 0.0, 0.3), ("coaching", 1.5, 0.6),
                                    ("workshop", 3.0, 0.9)):
            baseline = rng.normal(50.0, 10.0, 30)
            wellbeing = 20.0 + shift + slope * (baseline - 50.0) + rng.normal(0.0, 3.0, 30)
            parts.append(pd.DataFrame({"group": label, "baseline": baseline,
                                       "wellbeing": wellbeing}))
        frame = shuffled(pd.concat(parts, ignore_index=True), rng)
        roles = {"outcome": "wellbeing", "group": "group", "covariates": ["baseline"]}
        # Non-parallel slopes: common-slope ANCOVA is refused, not reported.
        with self.assertRaisesRegex(ValueError, "interaction"):
            workspace_run("ancova", frame, ancova_levels(frame), roles, mode="ancova")
        run = workspace_run("ancova", frame, ancova_levels(frame), roles, mode="interaction")
        result = run.result
        centred = frame.assign(centred=frame.baseline - frame.baseline.mean())
        fit = smf.ols("wellbeing ~ C(group) * centred", data=centred).fit()
        slopes = anova_lm(fit, typ=2).loc["C(group):centred"]
        self.assertEqual(result.df_interaction, int(slopes["df"]))
        self.assertClose(result.f_interaction, slopes["F"], msg="slopes F")
        self.assertClose(result.p_interaction, slopes["PR(>F)"], msg="slopes p")
        self.assertLess(result.p_interaction, 0.05)
        # Group effect is CONDITIONAL on the covariate grand mean: with a
        # centred covariate it is the joint test of the group dummies, i.e.
        # the type III group row of the centred interaction model.
        type3 = anova_lm(fit, typ=3)
        group_row, ss_error = type3.loc["C(group)"], type3.loc["Residual", "sum_sq"]
        self.assertEqual((result.df_group, result.df_error), (2, int(fit.df_resid)))
        self.assertClose(result.f_group, group_row["F"], msg="conditional group F")
        self.assertClose(result.p_group, group_row["PR(>F)"], msg="conditional group p")
        self.assertClose(result.eta_squared_partial,
                         group_row["sum_sq"] / (group_row["sum_sq"] + ss_error), msg="partial eta2")
        self.assertClose(result.r_squared, fit.rsquared, msg="R2")
        labels = sorted(frame.group.unique())
        grid = pd.DataFrame({"group": labels, "centred": 0.0})
        self.check_groups_and_pairs(result, fit, grid, labels,
                                    frame.groupby("group").wellbeing.apply(np.asarray))


# ------------------------------------------------- omnibus and post-hoc tests
OMNIBUS_ROLES = {"outcome": "score", "group": "arm"}


def unequal_groups(rng, decimals=None):
    """Four groups with unequal sizes, means and spreads."""
    spec = {"A": (18, 10.0, 1.0), "B": (25, 11.0, 2.5), "C": (31, 12.5, 4.0),
            "D": (22, 10.5, 1.5)}
    frame = pd.DataFrame(
        [(label, value) for label, (size, mean, sd) in spec.items()
         for value in rng.normal(mean, sd, size)], columns=["arm", "score"])
    if decimals is not None:
        frame["score"] = frame.score.round(decimals)
    return shuffled(frame, rng)


class OmnibusGroundTruth(GroundTruthCase):
    def test_one_way_anova_matches_f_oneway_closed_form_and_ols(self):
        frame = unequal_groups(np.random.default_rng(3211))
        run = workspace_run("omnibus", frame, {"arm": "nominal", "score": "scale"},
                            OMNIBUS_ROLES, method="anova")
        result = run.result
        labels, samples = group_samples(frame, "arm", "score")
        k, n = len(samples), np.array([s.size for s in samples])
        grand = np.concatenate(samples).mean()
        ss_between = np.sum(n * (np.array([s.mean() for s in samples]) - grand) ** 2)
        ss_within = sum(np.sum((s - s.mean()) ** 2) for s in samples)
        f_value = (ss_between / (k - 1)) / (ss_within / (n.sum() - k))
        p_value = stats.f.sf(f_value, k - 1, n.sum() - k)
        self.assertEqual(result.labels, labels)
        self.assertEqual((result.df1, result.df2), (k - 1, n.sum() - k))
        self.assertClose(result.statistic, f_value, msg="F")
        self.assertClose(result.p_value, p_value, msg="p")
        scipy_result = stats.f_oneway(*samples)
        self.assertClose(result.statistic, scipy_result.statistic, msg="F vs f_oneway")
        self.assertClose(result.p_value, scipy_result.pvalue, msg="p vs f_oneway")
        ols = anova_lm(smf.ols("score ~ C(arm)", data=frame).fit()).loc["C(arm)"]
        self.assertClose(result.statistic, ols["F"], msg="F vs OLS")
        self.assertClose(result.p_value, ols["PR(>F)"], msg="p vs OLS")
        self.assertEqual(result.effect_name, "Descriptive η²")
        self.assertClose(result.effect_size, ss_between / (ss_between + ss_within), msg="eta2")
        self.assertShown(run, "Overall statistic", f_value, p=p_value)
        self.assertShown(run, "Descriptive η²", ss_between / (ss_between + ss_within))

    def test_welch_anova_matches_formula_and_statsmodels(self):
        frame = unequal_groups(np.random.default_rng(3212))
        run = workspace_run("omnibus", frame, {"arm": "nominal", "score": "scale"},
                            OMNIBUS_ROLES, method="welch")
        result = run.result
        _, samples = group_samples(frame, "arm", "score")
        f_value, df1, df2, p_value = welch_anova_reference(samples)
        self.assertEqual(result.df1, df1)
        self.assertClose(result.df2, df2, msg="Welch df2")
        self.assertClose(result.statistic, f_value, msg="Welch F")
        self.assertClose(result.p_value, p_value, msg="Welch p")
        welch = anova_oneway(samples, use_var="unequal", welch_correction=True)
        self.assertClose(result.statistic, welch.statistic, msg="F vs statsmodels")
        self.assertClose(result.df2, welch.df_denom, msg="df2 vs statsmodels")
        self.assertClose(result.p_value, welch.pvalue, msg="p vs statsmodels")
        # Heteroscedastic groups: Welch differs from the classical F here.
        self.assertGreater(abs(stats.f_oneway(*samples).statistic - f_value), 0.1)
        # eta² stays the descriptive between-group share (documented).
        values = np.concatenate(samples)
        ss_between = sum(s.size * (s.mean() - values.mean()) ** 2 for s in samples)
        self.assertClose(result.effect_size,
                         ss_between / np.sum((values - values.mean()) ** 2), msg="eta2")
        self.assertShown(run, "Overall statistic", f_value, p=p_value)

    def test_kruskal_wallis_with_ties_matches_tie_corrected_h(self):
        frame = unequal_groups(np.random.default_rng(3213), decimals=0)   # many ties
        run = workspace_run("omnibus", frame, {"arm": "nominal", "score": "ordinal"},
                            OMNIBUS_ROLES, method="kruskal")
        result = run.result
        _, samples = group_samples(frame, "arm", "score")
        h, uncorrected, p_value, kelley = kruskal_reference(samples)
        self.assertEqual((result.df1, result.df2), (len(samples) - 1, None))
        self.assertClose(result.statistic, h, msg="H")
        self.assertClose(result.p_value, p_value, msg="p")
        scipy_result = stats.kruskal(*samples)
        self.assertClose(result.statistic, scipy_result.statistic, msg="H vs scipy")
        self.assertClose(result.p_value, scipy_result.pvalue, msg="p vs scipy")
        # The tie correction is applied (it changes H by far more than EXACT).
        self.assertGreater(abs(h - uncorrected) / h, 1e-3)
        # Convention: "Rank ε²" = (H - k + 1) / (n - k), which equals Kelley's
        # epsilon-squared of a one-way ANOVA on the average ranks (Tomczak &
        # Tomczak, 2014, call the same number eta²_H); it is not H / (n - 1).
        self.assertEqual(result.effect_name, "Rank ε² (truncated at 0)")
        self.assertGreater(kelley, 0)
        self.assertClose(result.effect_size, kelley, msg="rank epsilon2")
        self.assertShown(run, "Overall statistic", h, p=p_value)
        self.assertShown(run, "Rank ε² (truncated at 0)", kelley)

    def test_dunn_posthoc_holm_matches_multipletests(self):
        frame = unequal_groups(np.random.default_rng(3213), decimals=0)
        omnibus = workspace_run("omnibus", frame, {"arm": "nominal", "score": "ordinal"},
                                OMNIBUS_ROLES, method="kruskal")
        _, samples = group_samples(frame, "arm", "score")
        reference = dunn_reference(samples)
        adjusted = holm(p for _, _, p in reference)
        # run_posthoc (the workspace's post-hoc step) shows the pairs in a
        # table; its AnalysisRun keeps the omnibus result object, so the full-
        # precision pairs come from posthoc_analysis.analyze_posthoc, the
        # function run_posthoc calls.
        posthoc = run_posthoc(omnibus)
        self.assertEqual(posthoc.inputs["posthoc"], "Dunn–Holm")
        pairs = analyze_posthoc(omnibus.result).pairs
        rows = posthoc.tables[0].rows
        labels = omnibus.result.labels
        self.assertEqual(len(pairs), len(reference))
        for pair, row, (first, second), (difference, z, p), p_holm in zip(
                pairs, rows, combinations(labels, 2), reference, adjusted):
            self.assertEqual((pair.first, pair.second), (first, second))
            self.assertClose(pair.estimate, difference, msg="mean-rank difference")
            self.assertClose(pair.statistic, z, msg="Dunn z")
            self.assertClose(pair.p_raw, p, msg="Dunn raw p")
            self.assertClose(pair.p_adjusted, p_holm, msg="Holm p")
            self.assertEqual(row[0], f"{first} - {second}")
            self.assertLessEqual(abs(float(row[1]) - difference), SHOWN_2DP)
            self.assertLessEqual(abs(float(row[2]) - z), SHOWN_2DP)
            self.assertTableP(row[3], p_holm)
            self.assertEqual(row[4], "Yes" if p_holm < 0.05 else "No")
        self.assertGreater(max(abs(a - p) for (_, _, p), a in zip(reference, adjusted)), 0)

    def test_tukey_and_games_howell_posthoc_match_studentized_range(self):
        frame = unequal_groups(np.random.default_rng(3214))
        for method, equal_var, name in (("anova", True, "Tukey HSD / Tukey–Kramer"),
                                        ("welch", False, "Games–Howell")):
            with self.subTest(method=method):
                omnibus = workspace_run("omnibus", frame, {"arm": "nominal", "score": "scale"},
                                        OMNIBUS_ROLES, method=method)
                _, samples = group_samples(frame, "arm", "score")
                reference = studentized_range_pairs(samples, equal_var)
                posthoc = run_posthoc(omnibus)
                self.assertEqual(posthoc.inputs["posthoc"], name)
                pairs = analyze_posthoc(omnibus.result).pairs
                for pair, row, (difference, p, low, high) in zip(
                        pairs, posthoc.tables[0].rows, reference):
                    # Estimates are first minus second; intervals simultaneous.
                    self.assertClose(pair.estimate, difference, msg="mean difference")
                    self.assertClose(pair.p_adjusted, p, msg="familywise p")
                    self.assertClose(pair.ci_low, low, msg="CI low")
                    self.assertClose(pair.ci_high, high, msg="CI high")
                    self.assertLessEqual(abs(float(row[1]) - difference), SHOWN_2DP)
                    shown_low, shown_high = (float(v) for v in row[2].strip("[]").split(","))
                    self.assertLessEqual(abs(shown_low - low), SHOWN_2DP)
                    self.assertLessEqual(abs(shown_high - high), SHOWN_2DP)
                    self.assertTableP(row[3], p)


# --------------------------------------------------- paired and repeated data
PAIRED_ROLES = {"before": "pre", "after": "post"}


def continuous_pairs(seed, n=30):
    rng = np.random.default_rng(seed)
    before = rng.normal(20.0, 4.0, n)
    after = before + rng.normal(1.0, 2.0, n)
    return pd.DataFrame({"pre": before, "post": after})


class PairedGroundTruth(GroundTruthCase):
    def test_paired_t_matches_ttest_rel_and_closed_form(self):
        frame = continuous_pairs(3221)
        run = workspace_run("paired", frame, {"pre": "scale", "post": "scale"},
                            PAIRED_ROLES, method="paired_t")
        result = run.result
        d = (frame.post - frame.pre).to_numpy()
        n, mean, sd = d.size, d.mean(), d.std(ddof=1)
        t = mean / (sd / math.sqrt(n))
        p = 2 * stats.t.sf(abs(t), n - 1)
        half = stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n)
        self.assertEqual(result.df, n - 1)
        self.assertClose(result.statistic, t, msg="t (after minus before)")
        self.assertClose(result.p_value, p, msg="p")
        self.assertClose(result.ci_low, mean - half, msg="CI low")
        self.assertClose(result.ci_high, mean + half, msg="CI high")
        self.assertClose(result.mean_change, mean, msg="mean change")
        self.assertEqual(result.effect_name, "Cohen’s dz")
        self.assertClose(result.effect_size, mean / sd, msg="dz")
        reference = stats.ttest_rel(frame.post, frame.pre)
        self.assertClose(result.statistic, reference.statistic, msg="t vs ttest_rel")
        self.assertClose(result.p_value, reference.pvalue, msg="p vs ttest_rel")
        self.assertShown(run, "Test statistic", t, p=p)
        self.assertShown(run, "Cohen’s dz", mean / sd)
        self.assertShown(run, "Mean change", mean, ci=(mean - half, mean + half))

    def test_wilcoxon_without_ties_uses_the_exact_null_distribution(self):
        frame = continuous_pairs(3221)
        run = workspace_run("paired", frame, {"pre": "scale", "post": "scale"},
                            PAIRED_ROLES, method="wilcoxon")
        result = run.result
        d = (frame.post - frame.pre).to_numpy()
        # Convention: SciPy "auto" with zero_method="wilcox". With n <= 50
        # distinct nonzero differences that is the exact distribution.
        self.assertEqual(np.unique(np.abs(d)).size, d.size)
        self.assertFalse(np.any(d == 0))
        w_plus, w_minus, p = signed_rank_exact(d)
        self.assertClose(result.statistic, min(w_plus, w_minus), msg="W = min(W+, W-)")
        self.assertClose(result.p_value, p, msg="exact p")
        self.assertClose(result.effect_size, (w_plus - w_minus) / (w_plus + w_minus),
                         msg="rank-biserial r")
        self.assertClose(result.p_value,
                         stats.wilcoxon(d, method="exact").pvalue, msg="p vs scipy exact")
        # ... and not the normal approximation, which differs here.
        self.assertGreater(abs(signed_rank_normal(d)[2] - p), 1e-4)
        self.assertShown(run, "Test statistic", min(w_plus, w_minus), p=p)

    def test_wilcoxon_with_zeros_and_ties_drops_zeros_and_corrects_ties(self):
        rng = np.random.default_rng(3223)
        pre = rng.integers(1, 6, 60)
        post = np.clip(pre + rng.choice([-1, 0, 0, 1, 1, 2], 60), 1, 7)
        frame = pd.DataFrame({"pre": pre, "post": post})
        run = workspace_run("paired", frame, {"pre": "ordinal", "post": "ordinal"},
                            PAIRED_ROLES, method="wilcoxon")
        result = run.result
        d = (post - pre).astype(float)
        zeros = int(np.count_nonzero(d == 0))
        # Convention: zero_method="wilcox" (zero differences are discarded
        # before ranking), average ranks for tied |d| with the tie-corrected
        # variance, and -- with ties/zeros and n > 50 -- the normal
        # approximation WITHOUT continuity correction (SciPy defaults).
        self.assertGreater(zeros, 0)
        self.assertGreater(d.size, 50)
        w_plus, w_minus, p = signed_rank_normal(d, "wilcox")
        self.assertEqual(result.n_unchanged, zeros)
        self.assertIn(f"{zeros} unchanged pairs were excluded", " ".join(result.warnings))
        self.assertClose(result.statistic, min(w_plus, w_minus), msg="W")
        self.assertClose(result.p_value, p, msg="p")
        self.assertClose(result.effect_size, (w_plus - w_minus) / (w_plus + w_minus),
                         msg="rank-biserial r")
        explicit = stats.wilcoxon(d, zero_method="wilcox", correction=False,
                                  method="asymptotic")
        self.assertClose(result.p_value, explicit.pvalue, msg="p vs scipy asymptotic")
        # Pratt's zero handling or a continuity correction would differ.
        self.assertGreater(abs(signed_rank_normal(d, "pratt")[2] - p), 1e-6)
        self.assertGreater(abs(signed_rank_normal(d, "wilcox", continuity=True)[2] - p), 1e-6)

    def test_small_wilcoxon_with_ties_enumerates_all_sign_flips(self):
        # Eleven fictional pairs with zeros and tied |d|: SciPy "auto" then
        # runs an exhaustive sign-flip permutation (n <= 13), not the normal
        # approximation.
        pre = np.array([3, 4, 2, 5, 3, 4, 3, 2, 4, 5, 3], dtype=float)
        post = np.array([4, 4, 3, 5, 5, 3, 4, 4, 5, 5, 2], dtype=float)
        frame = pd.DataFrame({"pre": pre, "post": post})
        run = workspace_run("paired", frame, {"pre": "ordinal", "post": "ordinal"},
                            PAIRED_ROLES, method="wilcoxon")
        w_plus, w_minus, p = signed_rank_sign_flips(post - pre)
        self.assertEqual(run.result.n_unchanged, 3)
        self.assertClose(run.result.statistic, min(w_plus, w_minus), msg="W")
        self.assertClose(run.result.p_value, p, msg="permutation p")
        self.assertGreater(abs(signed_rank_normal(post - pre)[2] - p), 1e-3)


class RepeatedGroundTruth(GroundTruthCase):
    def test_rm_anova_matches_anovarm_and_greenhouse_geisser(self):
        rng = np.random.default_rng(3231)
        n, shifts, spread = 24, (0.0, 0.8, 1.5, 1.2), (1.0, 1.5, 2.5, 3.0)
        person = rng.normal(0.0, 3.0, n)
        frame = pd.DataFrame({f"t{j + 1}": 20 + person + shifts[j] + rng.normal(0, spread[j], n)
                              for j in range(4)})
        columns = list(frame.columns)
        run = workspace_run("repeated", frame, dict.fromkeys(columns, "scale"),
                            {"measures": columns}, method="rm_anova")
        result = run.result
        long = frame.assign(subject=np.arange(n)).melt(
            id_vars="subject", var_name="occasion", value_name="score")
        anova = AnovaRM(long, "score", "subject", within=["occasion"]).fit()
        row = anova.anova_table.loc["occasion"]
        self.assertEqual((result.df1, result.df2), (row["Num DF"], row["Den DF"]))
        self.assertClose(result.statistic, row["F Value"], msg="F vs AnovaRM")
        self.assertClose(result.p_uncorrected, row["Pr > F"], msg="uncorrected p")
        table = anova_lm(smf.ols("score ~ C(subject) + C(occasion)", data=long).fit(), typ=2)
        ss_occasion, ss_error = table.loc["C(occasion)", "sum_sq"], table.loc["Residual", "sum_sq"]
        self.assertEqual(result.effect_name, "Partial η²")
        self.assertClose(result.effect_size, ss_occasion / (ss_occasion + ss_error),
                         msg="partial eta2")
        epsilon = greenhouse_geisser(frame.to_numpy())
        self.assertLess(epsilon, 0.99)   # the sample departs from sphericity
        self.assertClose(result.epsilon_gg, epsilon, msg="GG epsilon")
        p_gg = stats.f.sf(row["F Value"], epsilon * row["Num DF"], epsilon * row["Den DF"])
        self.assertClose(result.p_primary, p_gg, msg="GG-corrected p")
        # Pairwise paired t tests (later minus earlier) with Holm.
        values = frame.to_numpy()
        raw = []
        for i, j in combinations(range(4), 2):
            d = values[:, j] - values[:, i]
            t = d.mean() / (d.std(ddof=1) / math.sqrt(n))
            raw.append((d.mean(), t, 2 * stats.t.sf(abs(t), n - 1), d.mean() / d.std(ddof=1)))
        for pair, (i, j), (mean, t, p, dz), p_holm in zip(
                result.pairs, combinations(range(4), 2), raw, holm(r[2] for r in raw)):
            self.assertEqual((pair.before, pair.after), (columns[i], columns[j]))
            self.assertClose(pair.estimate, mean, msg="mean change")
            self.assertClose(pair.statistic, t, msg="pair t")
            self.assertClose(pair.p_raw, p, msg="pair p")
            self.assertClose(pair.p_holm, p_holm, msg="pair Holm p")
            self.assertClose(pair.effect_size, dz, msg="pair dz")
        self.assertShown(run, "Overall statistic", row["F Value"], p=p_gg)

    def test_friedman_with_ties_matches_tie_corrected_formula(self):
        rng = np.random.default_rng(3232)
        n = 30
        latent = (3.0 + rng.normal(0.0, 1.0, n)[:, None] + np.array([0.0, 0.3, 0.6, 0.9])
                  + rng.normal(0.0, 0.8, (n, 4)))
        frame = pd.DataFrame(np.clip(np.round(latent), 1, 5),
                             columns=["week1", "week2", "week3", "week4"])
        columns = list(frame.columns)
        run = workspace_run("repeated", frame, dict.fromkeys(columns, "ordinal"),
                            {"measures": columns}, method="friedman")
        result = run.result
        values = frame.to_numpy()
        q, uncorrected, p, kendall_w = friedman_reference(values)
        self.assertEqual((result.df1, result.df2), (3.0, None))
        self.assertClose(result.statistic, q, msg="Friedman chi2")
        self.assertClose(result.p_primary, p, msg="p")
        self.assertGreater(abs(q - uncorrected) / q, 1e-3)    # ties matter here
        scipy_result = stats.friedmanchisquare(*values.T)
        self.assertClose(result.statistic, scipy_result.statistic, msg="chi2 vs scipy")
        self.assertEqual(result.effect_name, "Kendall’s W")
        self.assertClose(result.effect_size, kendall_w, msg="Kendall W")
        # Pairwise Wilcoxon (later minus earlier), Holm over all six pairs.
        # Every pair has zeros/ties and n > 13, so SciPy "auto" uses the
        # normal approximation with zeros dropped and no continuity correction.
        raw = []
        for i, j in combinations(range(4), 2):
            d = values[:, j] - values[:, i]
            nonzero = d[d != 0]
            self.assertTrue(nonzero.size < d.size
                            or np.unique(np.abs(nonzero)).size < nonzero.size)
            w_plus, w_minus, p_pair = signed_rank_normal(d)
            raw.append((np.median(d), min(w_plus, w_minus), p_pair,
                        (w_plus - w_minus) / (w_plus + w_minus)))
        for pair, (i, j), (median, w, p_pair, r), p_holm in zip(
                result.pairs, combinations(range(4), 2), raw, holm(r[2] for r in raw)):
            self.assertEqual((pair.before, pair.after), (columns[i], columns[j]))
            self.assertClose(pair.estimate, median, msg="median change")
            self.assertClose(pair.statistic, w, msg="pair W")
            self.assertClose(pair.p_raw, p_pair, msg="pair p")
            self.assertClose(pair.p_holm, p_holm, msg="pair Holm p")
            self.assertClose(pair.effect_size, r, msg="pair rank-biserial r")
        self.assertShown(run, "Overall statistic", q, p=p)
        self.assertShown(run, "Kendall’s W", kendall_w)


# -------------------------------------------------------------- reliability
class ReliabilityGroundTruth(GroundTruthCase):
    def test_alpha_matches_closed_form_and_feldt_interval(self):
        rng = np.random.default_rng(3241)
        trait = rng.normal(size=200)
        frame = pd.DataFrame({
            f"q{j}": np.clip(np.round(3 + 0.9 * trait + rng.normal(0, 1, 200)), 1, 5)
            for j in range(1, 6)})
        items = list(frame.columns)
        run = workspace_run("alpha", frame, dict.fromkeys(items, "ordinal"), {"items": items})
        result = run.result
        values = frame.to_numpy()
        alpha = cronbach_alpha(values)
        self.assertClose(result.alpha, alpha, msg="alpha")
        for j, name in enumerate(items):
            self.assertClose(result.alpha_if_deleted[name],
                             cronbach_alpha(np.delete(values, j, axis=1)),
                             msg=f"alpha without {name}")
        # Feldt (1965) F-based interval, df (n - 1, (n - 1)(k - 1)).
        # Convention: pingouin returns the bounds rounded to three decimals,
        # so they can differ from the full-precision bounds by 5e-4.
        df1, df2 = len(values) - 1, (len(values) - 1) * (len(items) - 1)
        low = 1 - (1 - alpha) * stats.f.isf(0.025, df1, df2)
        high = 1 - (1 - alpha) * stats.f.isf(0.975, df1, df2)
        self.assertLessEqual(abs(result.ci_low - low), SHOWN)
        self.assertLessEqual(abs(result.ci_high - high), SHOWN)
        self.assertShown(run, "Cronbach’s α", alpha, ci=(low, high))

    def test_identical_items_give_alpha_of_one(self):
        rng = np.random.default_rng(3242)
        answers = np.clip(np.round(3 + rng.normal(0.0, 1.0, 40)), 1, 5)
        frame = pd.DataFrame({"q1": answers, "q2": answers, "q3": answers})
        run = workspace_run("alpha", frame, dict.fromkeys(frame.columns, "ordinal"),
                            {"items": list(frame.columns)})
        # k/(k-1) * (1 - k v / (k^2 v)) = 1 exactly; the Feldt bounds
        # 1 - (1 - alpha) F collapse to 1 as well.
        self.assertClose(run.result.alpha, 1.0, msg="alpha")
        self.assertClose(run.result.ci_low, 1.0, msg="CI low")
        self.assertClose(run.result.ci_high, 1.0, msg="CI high")
        self.assertIn("redundant items", " ".join(run.result.warnings))
        self.assertShown(run, "Cronbach’s α", 1.0, ci=(1.0, 1.0))

    def test_contradictory_items_report_a_negative_alpha(self):
        rng = np.random.default_rng(3243)
        trait = rng.normal(size=60)
        frame = pd.DataFrame({"q1": trait + rng.normal(0, 0.5, 60),
                              "q2": -trait + rng.normal(0, 0.5, 60),
                              "q3": rng.normal(0, 1, 60)})
        run = workspace_run("alpha", frame, dict.fromkeys(frame.columns, "scale"),
                            {"items": list(frame.columns)})
        alpha = cronbach_alpha(frame.to_numpy())
        self.assertLess(alpha, 0)
        # Reported (not hidden or clipped to 0) with an explicit warning.
        self.assertClose(run.result.alpha, alpha, msg="negative alpha")
        self.assertIn("Negative alpha", " ".join(run.result.warnings))
        self.assertShown(run, "Cronbach’s α", alpha)

    # Omega: one-factor data with KNOWN standardized loadings. Sampling
    # tolerance, from 200 synthetic replications at n = 3000 run while
    # writing this test: the engine's omega had SD 0.005 (largest deviation
    # from the true value 0.015) and the largest loading error over the six
    # items had a 99th percentile of 0.050 (maximum 0.055). So omega must be
    # within 0.02 (about 4 SD) and every loading within 0.07. The loadings
    # are heterogeneous so that omega (0.790) and the population alpha
    # (0.761) differ by more than the tolerance.
    OMEGA_N = 3000
    LOADINGS = np.array([0.9, 0.85, 0.8, 0.4, 0.35, 0.3])

    @staticmethod
    def true_omega(loadings):
        uniqueness = 1 - loadings ** 2
        return loadings.sum() ** 2 / (loadings.sum() ** 2 + uniqueness.sum())

    def check_omega(self, loadings, seed, tolerance):
        frame = factor_items(np.random.default_rng(seed), loadings[:, None], self.OMEGA_N)
        items = list(frame.columns)
        run = workspace_run("omega", frame, dict.fromkeys(items, "scale"), {"items": items})
        result = run.result
        estimated = np.array([d.standardized_loading for d in result.diagnostics])
        uniqueness = np.array([d.uniqueness for d in result.diagnostics])
        # The point estimate is the omega formula applied to the fitted
        # loadings and uniquenesses ...
        self.assertClose(result.omega, estimated.sum() ** 2
                         / (estimated.sum() ** 2 + uniqueness.sum()), msg="omega identity")
        # ... and recovers the generating values within sampling error.
        self.assertLessEqual(abs(result.omega - self.true_omega(loadings)), tolerance)
        self.assertLessEqual(np.max(np.abs(estimated - loadings)), 0.07)
        eigen = np.linalg.eigvalsh(np.corrcoef(frame.to_numpy(), rowvar=False))
        self.assertClose(result.first_eigenvalue, eigen[-1], msg="first eigenvalue")
        self.assertClose(result.second_eigenvalue, eigen[-2], msg="second eigenvalue")
        self.assertShown(run, "McDonald’s ω", result.omega)
        return result

    def test_omega_recovers_true_one_factor_reliability(self):
        corr = np.outer(self.LOADINGS, self.LOADINGS)
        np.fill_diagonal(corr, 1.0)
        k = self.LOADINGS.size
        population_alpha = k / (k - 1) * (1 - k / corr.sum())
        self.assertGreater(self.true_omega(self.LOADINGS) - population_alpha, 0.02)
        self.check_omega(self.LOADINGS, 3244, tolerance=0.02)

    def test_omega_keeps_a_reverse_keyed_item_signed(self):
        # An item that was not reverse-coded keeps its negative loading and
        # lowers omega to (sum of SIGNED loadings)^2 / (... + sum theta);
        # the engine warns instead of flipping it. Sampling SD of omega here
        # is 0.006 at n = 3000 (largest deviation 0.022 in 200 replications),
        # hence 0.03.
        loadings = self.LOADINGS * np.array([1, 1, 1, -1, 1, 1])
        result = self.check_omega(loadings, 3245, tolerance=0.03)
        self.assertLess(result.diagnostics[3].standardized_loading, 0)
        self.assertIn("opposite the main factor", " ".join(result.warnings))


# ----------------------------------------------------------------- EFA / PCA
TWO_FACTORS = np.array([[0.8, 0.0], [0.7, 0.0], [0.6, 0.0],
                        [0.0, 0.8], [0.0, 0.7], [0.0, 0.6]])


def factor_run(frame, **options):
    items = list(frame.columns)
    return workspace_run("factor", frame, dict.fromkeys(items, "scale"), {"items": items},
                         **options)


class FactorGroundTruth(GroundTruthCase):
    def test_pca_eigenvalues_variance_and_loadings_match_svd(self):
        frame = factor_items(np.random.default_rng(3251), TWO_FACTORS, 500)
        run = factor_run(frame, method="pca", count="2", rotation="none")
        result = run.result
        values = frame.to_numpy()
        n, k = values.shape
        # Independent route: SVD of the standardized data matrix.
        z = (values - values.mean(axis=0)) / values.std(axis=0, ddof=1)
        _, singular, vt = np.linalg.svd(z, full_matrices=False)
        eigen = singular ** 2 / (n - 1)
        self.assertAllClose(result.eigenvalues, eigen, msg="eigenvalues")
        self.assertAllClose(result.component_variance_share, eigen[:2] / k, msg="variance share")
        loadings = vt[:2].T * singular[:2] / math.sqrt(n - 1)
        # Convention: each component's sign makes its loadings sum >= 0.
        loadings *= np.where(loadings.sum(axis=0) < 0, -1.0, 1.0)
        self.assertAllClose(result.loadings, loadings, msg="PCA loadings")
        self.assertAllClose((result.loadings ** 2).sum(axis=0), eigen[:2], msg="sum of squares")
        # Factorability: KMO from regression-residual partial correlations,
        # Bartlett from the eigenvalue product (= determinant).
        kmo, item_kmo = kmo_by_regression(values)
        self.assertClose(result.kmo, kmo, msg="KMO")
        self.assertAllClose(result.item_kmo, item_kmo, msg="item KMO")
        chi2 = -(n - 1 - (2 * k + 5) / 6) * np.sum(np.log(eigen))
        self.assertEqual(result.bartlett_df, k * (k - 1) // 2)
        self.assertClose(result.bartlett_chi2, chi2, msg="Bartlett chi2")
        self.assertClose(result.bartlett_p, stats.chi2.sf(chi2, k * (k - 1) // 2),
                         abs_tol=1e-300, msg="Bartlett p")
        self.assertShown(run, "Overall KMO", kmo)
        self.assertShown(run, "Bartlett χ²", chi2, p=stats.chi2.sf(chi2, k * (k - 1) // 2))
        self.assertEqual(self.evidence_row(run, "Extracted factors/components").estimate, "2")

    # EFA sampling tolerance, from 200 synthetic replications per design at
    # n = 3000 run while writing these tests: per-loading SDs were at most
    # 0.014 (one factor), 0.017 (two factors, varimax) and 0.019 (oblimin,
    # factor correlation 0.4), and the largest absolute error over all
    # loadings (after matching factor order/sign) never exceeded 0.041,
    # 0.052 and 0.060. Each tolerance is about 4 SD of the most variable
    # loading: 0.06, 0.07 and 0.08. On the data below, the wrong solution
    # would miss by far more: PCA loadings by 0.11 (one factor) and > 0.5
    # (two factors), the unrotated EFA by > 0.45, varimax on the correlated
    # factors by 0.16.

    def test_one_factor_efa_recovers_generating_loadings(self):
        loadings = np.array([[0.8], [0.7], [0.6], [0.5], [0.75], [0.65]])
        frame = factor_items(np.random.default_rng(3252), loadings, 3000)
        result = factor_run(frame, method="efa", count="1", rotation="none").result
        error, _, _ = aligned_loadings(result.loadings, loadings)
        self.assertLessEqual(error, 0.06)
        # Principal-axis uniqueness is 1 - communality of the fitted loadings.
        self.assertAllClose(result.uniqueness, 1 - (result.loadings ** 2).sum(axis=1),
                            msg="uniqueness")

    def test_two_factor_varimax_recovers_simple_structure(self):
        frame = factor_items(np.random.default_rng(3253), TWO_FACTORS, 3000)
        result = factor_run(frame, method="efa", count="2", rotation="varimax").result
        error, _, _ = aligned_loadings(result.loadings, TWO_FACTORS)
        self.assertLessEqual(error, 0.07)            # includes cross-loadings near 0
        self.assertIsNone(result.factor_correlations)
        self.assertAllClose(result.uniqueness, 1 - (result.loadings ** 2).sum(axis=1),
                            msg="uniqueness")

    def test_two_factor_oblimin_recovers_pattern_and_factor_correlation(self):
        phi = np.array([[1.0, 0.4], [0.4, 1.0]])
        frame = factor_items(np.random.default_rng(3254), TWO_FACTORS, 3000, phi)
        result = factor_run(frame, method="efa", count="2", rotation="oblimin").result
        error, order, signs = aligned_loadings(result.loadings, TWO_FACTORS)
        self.assertLessEqual(error, 0.08)
        # Factor correlation: SD 0.02 over 100 replications (largest
        # deviation 0.06), so 0.08 = 4 SD, after the same order/sign alignment.
        recovered = result.factor_correlations[np.ix_(order, order)] * np.outer(signs, signs)
        self.assertLessEqual(abs(recovered[0, 1] - 0.4), 0.08)
        # Pins the documented Phi = T'T convention: oblique communalities are
        # diag(P Phi P') and must equal 1 - uniqueness exactly (the inverse
        # convention misses by > 0.1 on these data).
        communality = np.diag(result.loadings @ result.factor_correlations @ result.loadings.T)
        self.assertAllClose(result.uniqueness, 1 - communality, msg="oblique uniqueness")
        self.assertAllClose(result.structure_loadings,
                            result.loadings @ result.factor_correlations, msg="structure")


# ------------------------------------------------------------- correlations
def correlation_run(frame, method, level="scale", x="x", y="y"):
    return workspace_run("correlation", frame, {x: level, y: level}, {"x": x, "y": y},
                         method=method)


class CorrelationGroundTruth(GroundTruthCase):
    def test_pearson_matches_closed_form_t_test_and_fisher_interval(self):
        rng = np.random.default_rng(3261)
        x = rng.normal(size=80)
        frame = pd.DataFrame({"x": x, "y": 0.3 * x + rng.normal(size=80)})
        run = correlation_run(frame, "pearson")
        result = run.result
        r, p, low, high = pearson_reference(frame.x.to_numpy(), frame.y.to_numpy())
        self.assertClose(result.coefficient, r, msg="r")
        self.assertClose(result.p_value, p, msg="p")
        self.assertClose(result.ci_low, low, msg="Fisher CI low")
        self.assertClose(result.ci_high, high, msg="Fisher CI high")
        reference = stats.pearsonr(frame.x, frame.y)
        self.assertClose(result.coefficient, reference.statistic, msg="r vs pearsonr")
        self.assertClose(result.p_value, reference.pvalue, msg="p vs pearsonr")
        self.assertShown(run, "Pearson r", r, ci=(low, high), p=p)

    def test_spearman_with_ties_uses_average_ranks_and_a_permutation_p(self):
        rng = np.random.default_rng(3262)
        x = np.round(rng.normal(0.0, 1.5, 80))
        frame = pd.DataFrame({"x": x, "y": np.round(0.2 * x + rng.normal(0.0, 1.0, 80))})
        self.assertLess(np.unique(frame.x).size, 20)      # heavily tied
        run = correlation_run(frame, "spearman", level="ordinal")
        result = run.result
        rho = rank_correlation(frame.x.to_numpy(), frame.y.to_numpy())
        self.assertClose(result.coefficient, rho, msg="rho")
        self.assertClose(result.coefficient, stats.spearmanr(frame.x, frame.y).statistic,
                         msg="rho vs spearmanr")
        # Convention (n <= 500): Monte Carlo permutation p with 1,999
        # resamples and a fixed seed, not the asymptotic t. Reference: an
        # independent permutation estimate with 20,000 resamples. Both are
        # Monte Carlo estimates of the same p, so they may differ by
        # 4 SE = 4 sqrt(p(1-p)(1/1999 + 1/20000)).
        self.assertIn("permutation", result.p_method)
        p = spearman_permutation_p(frame.x.to_numpy(), frame.y.to_numpy(), 20_000, seed=3262)
        self.assertGreater(p, 0.01)
        tolerance = 4 * math.sqrt(p * (1 - p) * (1 / 1999 + 1 / 20_000))
        self.assertLessEqual(abs(result.p_value - p), tolerance)
        # spearmanr's asymptotic t p (accurate to about 0.003 at n = 80 on
        # these data) falls inside the same band.
        self.assertLessEqual(abs(result.p_value - stats.spearmanr(frame.x, frame.y).pvalue),
                             tolerance)
        self.assertShown(run, "Spearman ρ", rho)

    def test_large_sample_spearman_uses_the_asymptotic_t_test(self):
        rng = np.random.default_rng(3263)
        x = rng.normal(size=600)
        frame = pd.DataFrame({"x": np.round(2 * x),
                              "y": np.round(2 * (0.1 * x + rng.normal(size=600)))})
        run = correlation_run(frame, "spearman", level="ordinal")
        rho = rank_correlation(frame.x.to_numpy(), frame.y.to_numpy())
        t = rho * math.sqrt((600 - 2) / (1 - rho ** 2))
        self.assertIn("asymptotic", run.result.p_method)
        self.assertClose(run.result.coefficient, rho, msg="rho")
        self.assertClose(run.result.p_value, 2 * stats.t.sf(abs(t), 598), msg="asymptotic p")

    def test_perfect_linear_relation_gives_r_of_one(self):
        x = np.arange(20) * 0.5 + 3.0
        frame = pd.DataFrame({"x": x, "y": 2.0 * x - 1.0})
        run = correlation_run(frame, "pearson")
        result = run.result
        # r = 1: t is infinite, so p = 0 and the Fisher interval is [1, 1].
        self.assertClose(result.coefficient, 1.0, msg="r")
        self.assertLess(result.p_value, 1e-12)
        self.assertClose(result.ci_low, 1.0, msg="CI low")
        self.assertClose(result.ci_high, 1.0, msg="CI high")
        self.assertShown(run, "Pearson r", 1.0, ci=(1.0, 1.0), p=0.0)
        spearman = correlation_run(frame, "spearman").result
        self.assertClose(spearman.coefficient, 1.0, msg="rho")
        # Only the observed pairing reaches rho = 1 (1 of 20! orderings), so
        # the p is the smallest a two-sided 1,999-resample permutation test
        # can give, counting the observed pairing once: 2 * 1/2000.
        self.assertClose(spearman.p_value, 2 / 2000, msg="permutation p floor")

    def test_correlation_uses_complete_pairs_only(self):
        rng = np.random.default_rng(3264)
        x = rng.normal(size=60)
        frame = pd.DataFrame({"x": x, "y": 0.5 * x + rng.normal(size=60)})
        frame.loc[[2, 9, 15], "x"] = np.nan
        frame.loc[[9, 30], "y"] = np.nan
        complete = frame.dropna()
        result = correlation_run(frame, "pearson").result
        self.assertEqual((result.n_total, result.n_complete), (60, 56))
        r, p, _, _ = pearson_reference(complete.x.to_numpy(), complete.y.to_numpy())
        self.assertClose(result.coefficient, r, msg="r on complete pairs")
        self.assertClose(result.p_value, p, msg="p on complete pairs")
        self.assertIn("excluded 4 records", " ".join(result.warnings))

    def test_constant_variable_is_refused_with_a_clear_error(self):
        rng = np.random.default_rng(3265)
        frame = pd.DataFrame({"x": np.full(30, 3.0), "y": rng.normal(size=30)})
        for method in ("pearson", "spearman"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(ValueError, "must have variation"):
                    correlation_run(frame, method)

    def test_matrix_is_pairwise_complete(self):
        rng = np.random.default_rng(3266)
        a = rng.normal(size=50)
        frame = pd.DataFrame({"a": a, "b": a + rng.normal(size=50),
                              "c": np.round(rng.normal(size=50)), "d": -a + rng.normal(size=50)})
        frame.loc[[0, 1, 2], "a"] = np.nan
        frame.loc[[3, 4], "b"] = np.nan
        frame.loc[[5], "c"] = np.nan
        names = list(frame.columns)
        listwise = frame.dropna()
        for method in ("pearson", "spearman"):
            with self.subTest(method=method):
                run = workspace_run("matrix", frame, dict.fromkeys(names, "scale"),
                                    {"items": names}, method=method)
                result = run.result
                # Convention: PAIRWISE deletion -- every cell uses the rows
                # where both of its variables are present, and records its N.
                for i, j in combinations(range(len(names)), 2):
                    pair = frame[[names[i], names[j]]].dropna()
                    x, y = pair.iloc[:, 0].to_numpy(), pair.iloc[:, 1].to_numpy()
                    expected = (pearson_reference(x, y)[0] if method == "pearson"
                                else rank_correlation(x, y))
                    self.assertEqual(result.pair_counts[i, j], len(pair))
                    self.assertClose(result.coefficients[i, j], expected, msg=f"{i},{j}")
                    self.assertClose(result.coefficients[j, i], expected, msg=f"{j},{i}")
                for i, name in enumerate(names):
                    self.assertEqual(result.pair_counts[i, i], frame[name].notna().sum())
                    self.assertEqual(result.coefficients[i, i], 1.0)
                # ... which is not listwise deletion.
                listwise_ab = (pearson_reference(listwise.a.to_numpy(), listwise.b.to_numpy())[0]
                               if method == "pearson"
                               else rank_correlation(listwise.a.to_numpy(), listwise.b.to_numpy()))
                self.assertGreater(abs(result.coefficients[0, 1] - listwise_ab), 1e-4)
                self.assertEqual(run.tables[0].rows[0][2], f"{result.coefficients[0, 1]:.3f}")

    def test_matrix_constant_variable_cells_are_not_available(self):
        rng = np.random.default_rng(3267)
        a = rng.normal(size=40)
        frame = pd.DataFrame({"a": a, "b": a + rng.normal(size=40), "k": np.full(40, 2.0)})
        names = list(frame.columns)
        run = workspace_run("matrix", frame, dict.fromkeys(names, "scale"), {"items": names},
                            method="pearson")
        result = run.result
        self.assertClose(result.coefficients[0, 1],
                         pearson_reference(frame.a.to_numpy(), frame.b.to_numpy())[0], msg="a,b")
        # Every cell involving the constant variable is undefined: shown as
        # "N/A" with an explanation, never as a number or "nan".
        self.assertTrue(np.isnan(result.coefficients[2]).all())
        self.assertTrue(np.isnan(result.coefficients[:, 2]).all())
        table = run.tables[0]
        self.assertEqual(table.rows[2][1:], ("N/A", "N/A", "N/A"))
        self.assertEqual([row[3] for row in table.rows], ["N/A"] * 3)
        self.assertNotIn("nan", run.report.lower())
        self.assertIn("N/A cells", " ".join(result.warnings))


# --------------------------------------------------------------- regression
def regression_frame(seed):
    """Three correlated predictors, heteroscedastic errors, a few missing
    values (excluded listwise)."""
    rng = np.random.default_rng(seed)
    n = 120
    x1 = rng.normal(size=n)
    x2 = 0.5 * x1 + rng.normal(size=n)
    x3 = rng.uniform(0.0, 3.0, n)
    y = 1.0 + 0.6 * x1 - 0.4 * x2 + 0.2 * x3 + rng.normal(size=n) * (0.5 + np.abs(x1))
    frame = pd.DataFrame({"y": y, "x1": x1, "x2": x2, "x3": x3})
    frame.loc[[7], "y"] = np.nan
    frame.loc[[11, 50], "x2"] = np.nan
    return frame


REGRESSION_LEVELS = {"y": "scale", "x1": "scale", "x2": "scale", "x3": "scale"}
REGRESSION_ROLES = {"outcome": "y", "predictors": ["x1", "x2", "x3"]}


class RegressionGroundTruth(GroundTruthCase):
    def setUp(self):
        self.frame = regression_frame(3271)
        complete = self.frame.dropna()
        self.y = complete.y.to_numpy()
        self.predictors = complete[["x1", "x2", "x3"]].to_numpy()
        self.x = np.column_stack([np.ones(len(complete)), self.predictors])
        self.beta = np.linalg.lstsq(self.x, self.y, rcond=None)[0]
        self.resid = self.y - self.x @ self.beta
        self.df_resid = len(complete) - 4

    def test_ols_matches_least_squares_closed_form(self):
        run = workspace_run("regression", self.frame, REGRESSION_LEVELS, REGRESSION_ROLES,
                            hc3="no")
        result = run.result
        n = len(self.y)
        rss = self.resid @ self.resid
        tss = np.sum((self.y - self.y.mean()) ** 2)
        se = np.sqrt(np.diag(rss / self.df_resid * np.linalg.inv(self.x.T @ self.x)))
        crit = stats.t.ppf(0.975, self.df_resid)
        r2 = 1 - rss / tss
        f_value = (r2 / 3) / ((1 - r2) / self.df_resid)
        self.assertEqual((result.n_total, result.n_complete), (120, n))
        self.assertEqual((result.model_df, result.residual_df), (3, self.df_resid))
        self.assertClose(result.r_squared, r2, msg="R2")
        self.assertClose(result.adjusted_r_squared, 1 - (1 - r2) * (n - 1) / self.df_resid,
                         msg="adjusted R2")
        self.assertClose(result.f_value, f_value, msg="F")
        self.assertClose(result.f_p, stats.f.sf(f_value, 3, self.df_resid), msg="F p")
        # VIF_j is the j-th diagonal element of the inverse predictor
        # correlation matrix (independent of the engine's auxiliary fits).
        vif = np.diag(np.linalg.inv(np.corrcoef(self.predictors, rowvar=False)))
        for j, coef in enumerate(result.coefficients):
            t = self.beta[j] / se[j]
            self.assertEqual(coef.name, ["Intercept", "x1", "x2", "x3"][j])
            self.assertClose(coef.b, self.beta[j], msg=f"b {coef.name}")
            self.assertClose(coef.se, se[j], msg=f"se {coef.name}")
            self.assertClose(coef.t, t, msg=f"t {coef.name}")
            self.assertClose(coef.p, 2 * stats.t.sf(abs(t), self.df_resid), msg=f"p {coef.name}")
            self.assertClose(coef.ci_low, self.beta[j] - crit * se[j], msg=f"CI {coef.name}")
            self.assertClose(coef.ci_high, self.beta[j] + crit * se[j], msg=f"CI {coef.name}")
            if j:
                self.assertClose(coef.vif, vif[j - 1], msg=f"VIF {coef.name}")
            self.assertShown(run, f"B: {coef.name}", self.beta[j],
                             ci=(self.beta[j] - crit * se[j], self.beta[j] + crit * se[j]),
                             p=2 * stats.t.sf(abs(t), self.df_resid))
        self.assertShown(run, "Model R²", r2)
        self.assertShown(run, "Model F", f_value, p=stats.f.sf(f_value, 3, self.df_resid))

    def test_hc3_standard_errors_match_sandwich_formula_and_statsmodels(self):
        plain = workspace_run("regression", self.frame, REGRESSION_LEVELS, REGRESSION_ROLES,
                              hc3="no").result
        result = workspace_run("regression", self.frame, REGRESSION_LEVELS, REGRESSION_ROLES,
                               hc3="yes").result
        # HC3 sandwich: (X'X)^-1 X' diag(e_i^2 / (1 - h_ii)^2) X (X'X)^-1.
        bread = np.linalg.inv(self.x.T @ self.x)
        leverage = np.einsum("ij,jk,ik->i", self.x, bread, self.x)
        meat = (self.x * (self.resid / (1 - leverage))[:, None] ** 2).T @ self.x
        se = np.sqrt(np.diag(bread @ meat @ bread))
        # Convention: t-based inference on n - p - 1 df (use_t=True); the
        # statsmodels default for cov_type="HC3" would use the normal.
        robust = sm.OLS(self.y, self.x).fit(cov_type="HC3", use_t=True)
        normal = sm.OLS(self.y, self.x).fit(cov_type="HC3")
        crit = stats.t.ppf(0.975, self.df_resid)
        self.assertTrue(result.robust_hc3)
        for j, coef in enumerate(result.coefficients):
            t = self.beta[j] / se[j]
            p = 2 * stats.t.sf(abs(t), self.df_resid)
            self.assertClose(coef.b, self.beta[j], msg="b unchanged")
            self.assertClose(coef.se, se[j], msg=f"HC3 se {coef.name}")
            self.assertClose(coef.se, robust.bse[j], msg=f"HC3 se vs statsmodels {coef.name}")
            self.assertClose(coef.t, t, msg=f"robust t {coef.name}")
            self.assertClose(coef.p, p, msg=f"robust p {coef.name}")
            self.assertClose(coef.p, robust.pvalues[j], msg=f"p vs statsmodels {coef.name}")
            self.assertClose(coef.ci_low, self.beta[j] - crit * se[j], msg=f"CI {coef.name}")
            self.assertClose(coef.ci_high, self.beta[j] + crit * se[j], msg=f"CI {coef.name}")
            self.assertGreater(abs(coef.p - normal.pvalues[j]), 1e-7)
        self.assertGreater(max(abs(c.se - d.se) for c, d in zip(result.coefficients,
                                                                 plain.coefficients)), 1e-3)
        # Model fit statistics remain the conventional OLS ones.
        self.assertEqual((result.r_squared, result.f_value, result.f_p),
                         (plain.r_squared, plain.f_value, plain.f_p))


if __name__ == "__main__":
    unittest.main()
