"""Stage 36.2: the statistical result engine against independent oracles.

Oracles are computed here, not through the application's code paths:
hand formulas (Holm/BH, Fisher z, Kendall τ-b, tie-corrected H, effect
sizes), statsmodels ``multipletests``, SciPy functions called directly,
exact permutation enumeration and a coverage simulation. Tolerances are
recorded in docs/STAGE36_STATISTICAL_VALIDATION.md. Synthetic data only.
"""

from __future__ import annotations

from itertools import combinations, permutations
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from statsmodels.stats.multitest import multipletests  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from batch_correlation import bootstrap_ci, correlate_many, CorrelationFamily  # noqa: E402
from batch_groups import (GroupFamily, check_grouping, compare_many,  # noqa: E402
                          kruskal_permutation_p)
from multiple_comparisons import adjust  # noqa: E402
from stat_results import StructuredResult, describe_categorical, describe_quantitative  # noqa: E402

TIGHT = 1e-12


def frame() -> pd.DataFrame:
    return pd.read_csv(fx.fixture(fx.CSV))


class MultipleComparisonTests(unittest.TestCase):
    def test_holm_bh_bonferroni_match_statsmodels(self):
        rng = np.random.default_rng(1)
        for size in (1, 2, 5, 8, 20):
            for _ in range(20):
                p = rng.uniform(0, 0.2, size)
                p[rng.integers(0, size)] = p[0]            # ties
                for ours, theirs in (("holm", "holm"), ("bh", "fdr_bh"),
                                     ("bonferroni", "bonferroni")):
                    got = adjust(list(p), ours).adjusted
                    expected = multipletests(p, method=theirs)[1]
                    np.testing.assert_allclose(got, expected, rtol=0, atol=TIGHT)

    def test_missing_p_values_are_left_out_of_the_family(self):
        result = adjust([0.01, None, 0.04, float("nan")], "holm")
        self.assertEqual(result.family_size, 2)
        self.assertEqual(result.adjusted[1], None)
        self.assertEqual(result.adjusted[3], None)
        np.testing.assert_allclose([result.adjusted[0], result.adjusted[2]],
                                   multipletests([0.01, 0.04], method="holm")[1], atol=TIGHT)

    def test_raw_values_are_not_changed_and_invalid_input_is_refused(self):
        raw = [0.03, 0.2]
        adjust(raw, "bh")
        self.assertEqual(raw, [0.03, 0.2])
        with self.assertRaises(ValueError):
            adjust([1.2], "holm")
        with self.assertRaises(ValueError):
            adjust([0.1], "unknown")


class DescriptiveTests(unittest.TestCase):
    def test_quantities_match_numpy_and_scipy(self):
        values = frame()["UCLA"]
        result = describe_quantitative(values, "UCLA", ci_mean=True)
        x = values.to_numpy(dtype=float)
        q = {k: result.quantity(k) for k in ("n", "missing", "mean", "sd", "median", "q1", "q3",
                                              "iqr", "min", "max", "p5", "p95", "skewness",
                                              "kurtosis", "se_mean")}
        self.assertEqual(q["n"].value, 55)
        self.assertEqual(q["missing"].value, 0)
        self.assertAlmostEqual(q["mean"].value, x.sum() / x.size, places=12)
        self.assertAlmostEqual(q["sd"].value, math.sqrt(((x - x.mean()) ** 2).sum() / (x.size - 1)),
                               places=12)
        for key, pct in (("q1", 25), ("median", 50), ("q3", 75), ("p5", 5), ("p95", 95)):
            self.assertAlmostEqual(q[key].value, np.percentile(x, pct, method="linear"), places=12)
        self.assertAlmostEqual(q["iqr"].value, np.percentile(x, 75) - np.percentile(x, 25),
                               places=12)
        self.assertAlmostEqual(q["skewness"].value, stats.skew(x, bias=False), places=10)
        self.assertAlmostEqual(q["kurtosis"].value, stats.kurtosis(x, bias=False), places=10)
        low, high = stats.t.interval(0.95, x.size - 1, loc=x.mean(), scale=stats.sem(x))
        self.assertAlmostEqual(q["mean"].ci_low, low, places=10)
        self.assertAlmostEqual(q["mean"].ci_high, high, places=10)

    def test_missing_values_say_why(self):
        result = describe_quantitative(pd.Series([4.0, None, None]), "tiny")
        self.assertEqual(result.quantity("missing").value, 2)
        self.assertEqual(result.quantity("sd").status, "not_applicable")
        self.assertEqual(result.quantity("sd").text(), "Not applicable")
        self.assertEqual(result.quantity("skewness").status, "not_applicable")
        empty = describe_quantitative(pd.Series([None, None], dtype=float), "empty")
        self.assertEqual(empty.quantity("mean").text(), "Unavailable")

    def test_categorical_counts(self):
        result = describe_categorical(frame()["UCLA_Level"], "UCLA_Level", "ordinal")
        self.assertEqual([row[:2] for row in result.tables[0].rows],
                         [("1", "3"), ("2", "47"), ("3", "5")])
        self.assertEqual(result.quantity("categories").value, 3)

    def test_structured_results_survive_json(self):
        result = describe_quantitative(frame()["UCLA"], "UCLA", ci_mean=True)
        again = StructuredResult.from_dict(json.loads(json.dumps(result.to_dict())))
        self.assertEqual(again, result)


def kendall_tau_b(x, y) -> float:
    """O(n²) τ-b with tie corrections, written from the definition."""
    concordant = discordant = ties_x = ties_y = 0
    for i, j in combinations(range(len(x)), 2):
        dx, dy = np.sign(x[i] - x[j]), np.sign(y[i] - y[j])
        if dx == 0 and dy == 0:
            continue
        if dx == 0:
            ties_x += 1
        elif dy == 0:
            ties_y += 1
        elif dx == dy:
            concordant += 1
        else:
            discordant += 1
    return (concordant - discordant) / math.sqrt((concordant + discordant + ties_x) *
                                                 (concordant + discordant + ties_y))


class BatchCorrelationTests(unittest.TestCase):
    def test_pearson_coefficient_p_and_fisher_interval(self):
        df = frame()
        family = correlate_many(df, "UCLA", list(fx.SCALES), method="pearson",
                                pearson_assumptions_confirmed=True)
        for row in family.rows:
            x, y = df["UCLA"].to_numpy(float), df[row.y].to_numpy(float)
            r = np.corrcoef(x, y)[0, 1]
            n = x.size
            t = r * math.sqrt((n - 2) / (1 - r * r))
            z, se = math.atanh(r), 1 / math.sqrt(n - 3)
            crit = stats.norm.ppf(0.975)
            self.assertAlmostEqual(row.estimate, r, places=12)
            self.assertAlmostEqual(row.p_raw, 2 * stats.t.sf(abs(t), n - 2), places=10)
            self.assertAlmostEqual(row.ci_low, math.tanh(z - crit * se), places=10)
            self.assertAlmostEqual(row.ci_high, math.tanh(z + crit * se), places=10)
            self.assertEqual(row.ci_method, "Fisher z transformation")

    def test_spearman_rho_is_pearson_of_average_ranks_and_family_is_adjusted(self):
        df = frame()
        family = correlate_many(df, "UCLA", list(fx.SCALES), method="spearman")
        raw = []
        for row in family.rows:
            rx = df["UCLA"].rank(method="average").to_numpy()
            ry = df[row.y].rank(method="average").to_numpy()
            self.assertAlmostEqual(row.estimate, np.corrcoef(rx, ry)[0, 1], places=12)
            self.assertIn("permutation", row.p_method)
            self.assertIn("bootstrap", row.ci_method)
            self.assertNotIn("Fisher", row.ci_method)
            self.assertLessEqual(row.ci_low, row.estimate)
            self.assertGreaterEqual(row.ci_high, row.estimate)
            raw.append(row.p_raw)
        np.testing.assert_allclose([row.p_adjusted for row in family.rows],
                                   multipletests(raw, method="holm")[1], atol=TIGHT)
        bh = correlate_many(df, "UCLA", list(fx.SCALES), method="spearman", adjust="bh")
        np.testing.assert_allclose([row.p_adjusted for row in bh.rows],
                                   multipletests(raw, method="fdr_bh")[1], atol=TIGHT)
        self.assertEqual([row.p_raw for row in bh.rows], raw, "raw p never changes")
        self.assertEqual(family.family_size, 8)

    def test_spearman_asymptotic_p_is_the_t_approximation(self):
        df = frame()
        family = correlate_many(df, "UCLA", list(fx.SCALES[:3]), method="spearman",
                                spearman_p="asymptotic")
        for row in family.rows:
            rho, n = row.estimate, row.n
            t = rho * math.sqrt((n - 2) / (1 - rho * rho))
            self.assertAlmostEqual(row.p_raw, 2 * stats.t.sf(abs(t), n - 2), places=10)
            self.assertIn("t approximation", row.p_method)

    def test_kendall_tau_b_matches_the_definition(self):
        df = frame()
        family = correlate_many(df, "UCLA", list(fx.SCALES[:3]), method="kendall")
        for row in family.rows:
            x, y = df["UCLA"].to_numpy(float), df[row.y].to_numpy(float)
            self.assertAlmostEqual(row.estimate, kendall_tau_b(x, y), places=12)
            expected = stats.kendalltau(x, y, variant="b", method="asymptotic").pvalue
            self.assertAlmostEqual(row.p_raw, expected, places=12)
            self.assertIn("tie correction", row.p_method)
            self.assertEqual(row.magnitude, "", "no Cohen labels for τ")

    def test_bootstrap_is_reproducible_and_counts_failed_resamples(self):
        rng = np.random.default_rng(5)
        x = rng.normal(size=12)
        y = np.array([0.0] * 11 + [1.0])           # many resamples have no variation in y
        first = bootstrap_ci(x, y, "spearman", resamples=1000, seed=[36, 1, 2], level=0.95)
        second = bootstrap_ci(x, y, "spearman", resamples=1000, seed=[36, 1, 2], level=0.95)
        self.assertEqual(first, second)
        self.assertGreater(first[2], 0, "failed resamples are counted")
        self.assertIn("without variation", first[3])
        if first[2] > 100:
            self.assertIsNone(first[0], "too many failures: no interval")

    def test_percentile_bootstrap_coverage_of_spearman(self):
        """Simulation: bivariate normal, population ρ_s = 6/π·asin(ρ/2)."""
        rng = np.random.default_rng(2026)
        rho = 0.4
        target = 6 / math.pi * math.asin(rho / 2)
        cover, trials = 0, 200
        for trial in range(trials):
            data = rng.multivariate_normal([0, 0], [[1, rho], [rho, 1]], size=55)
            low, high, _failed, _text = bootstrap_ci(data[:, 0], data[:, 1], "spearman",
                                                     resamples=1000, seed=[trial, 1, 2],
                                                     level=0.95)
            cover += low <= target <= high
        self.assertGreaterEqual(cover / trials, 0.88)
        self.assertLessEqual(cover / trials, 0.99)

    def test_wording_never_claims_causation_or_proven_absence(self):
        family = correlate_many(frame(), "UCLA", list(fx.SCALES), method="spearman")
        for language in ("en", "lv", "ru"):
            for sentence in family.interpretation(language):
                self.assertNotIn("prove", sentence.replace("does not show", ""))
                self.assertNotIn("no effect", sentence)
        sentences = family.interpretation("en")
        for row, sentence in zip(family.rows, sentences):
            if row.p_adjusted >= family.alpha:
                self.assertIn("does not show that there is no association", sentence)
            else:
                self.assertIn("does not show causation", sentence)

    def test_failed_pairs_and_refusals(self):
        df = frame().copy()
        df["Constant"] = 3
        family = correlate_many(df, "UCLA", ["AssertiveAction", "Constant"], method="spearman")
        self.assertEqual(family.row("Constant").status, "failed")
        self.assertEqual(family.family_size, 1)
        self.assertEqual(family.row("AssertiveAction").p_adjusted,
                         family.row("AssertiveAction").p_raw)
        with self.assertRaises(ValueError):
            correlate_many(df, "UCLA", ["AssertiveAction"], method="pearson")
        with self.assertRaises(ValueError):
            correlate_many(df, "UCLA", ["UCLA"])
        with self.assertRaises(ValueError):
            correlate_many(df, "UCLA", ["Code"])

    def test_family_survives_json(self):
        family = correlate_many(frame(), "UCLA", list(fx.SCALES[:2]), method="spearman")
        again = CorrelationFamily.from_dict(json.loads(json.dumps(family.to_dict())))
        self.assertEqual(again, family)
        self.assertEqual(again.structured().quantity(f"ρ:{fx.SCALES[0]}").value,
                         family.rows[0].estimate)


def tie_corrected_h(samples) -> float:
    values = np.concatenate(samples)
    n = values.size
    ranks = stats.rankdata(values)
    start, total = 0, 0.0
    for s in samples:
        r = ranks[start:start + len(s)].sum()
        total += r * r / len(s)
        start += len(s)
    h = 12 / (n * (n + 1)) * total - 3 * (n + 1)
    _, counts = np.unique(values, return_counts=True)
    return h / (1 - (counts ** 3 - counts).sum() / (n ** 3 - n))


class BatchGroupTests(unittest.TestCase):
    def test_h_df_p_and_effect_sizes(self):
        df = frame()
        family = compare_many(df, "UCLA_Level", list(fx.SCALES))
        for row in family.rows:
            samples = [df.loc[df["UCLA_Level"] == g, row.outcome].to_numpy(float) for g in (1, 2, 3)]
            h = tie_corrected_h(samples)
            n, k = sum(len(s) for s in samples), 3
            self.assertAlmostEqual(row.statistic, h, places=10)
            self.assertAlmostEqual(row.statistic, stats.kruskal(*samples).statistic, places=10)
            self.assertEqual(row.df, 2)
            self.assertAlmostEqual(row.p_asymptotic, stats.chi2.sf(h, 2), places=12)
            self.assertAlmostEqual(row.eta2_h, max(0.0, (h - k + 1) / (n - k)), places=12)
            self.assertAlmostEqual(row.epsilon2_r, h / ((n * n - 1) / (n + 1)), places=12)
            self.assertEqual(row.ns, (3, 47, 5))
            self.assertEqual(row.p_primary, row.p_permutation, "a group of 3: permutation p")
            self.assertIn("permutation", row.p_method)
        np.testing.assert_allclose([row.p_adjusted for row in family.rows],
                                   multipletests([row.p_primary for row in family.rows],
                                                 method="holm")[1], atol=TIGHT)

    def test_permutation_p_against_exact_enumeration(self):
        samples = [np.array([1.0, 2.0]), np.array([3.0, 5.0]), np.array([4.0, 6.0])]
        observed = stats.kruskal(*samples).statistic
        values = np.concatenate(samples)
        exceed = total = 0
        seen = set()
        for order in permutations(range(6)):
            groups = (tuple(sorted(order[0:2])), tuple(sorted(order[2:4])), tuple(sorted(order[4:6])))
            if groups in seen:
                continue
            seen.add(groups)
            h = stats.kruskal(*[values[list(g)] for g in groups]).statistic
            exceed += h >= observed - 1e-12
            total += 1
        exact = exceed / total
        estimate = kruskal_permutation_p(samples, permutations=19999, seed=36, observed=observed)
        self.assertEqual(total, 90)
        self.assertAlmostEqual(estimate, exact, delta=0.01)

    def test_large_groups_use_the_chi_square_p_and_agree_with_permutation(self):
        rng = np.random.default_rng(3)
        df = pd.DataFrame({"g": np.repeat([1, 2, 3], 20),
                           "y": np.concatenate([rng.normal(m, 1, 20) for m in (0, 0.3, 0.6)])})
        row = compare_many(df, "g", ["y"]).rows[0]
        self.assertEqual(row.p_primary, row.p_asymptotic)
        self.assertAlmostEqual(row.p_permutation, row.p_asymptotic, delta=0.03)

    def test_dunn_pairs_match_the_validated_posthoc_module(self):
        from omnibus_analysis import analyze_omnibus
        from posthoc_analysis import analyze_posthoc

        rng = np.random.default_rng(4)
        df = pd.DataFrame({"g": np.repeat([1, 2, 3], 12),
                           "y": np.round(np.concatenate([rng.normal(m, 1, 12) for m in (0, 1, 1.5)]), 1)})
        row = compare_many(df, "g", ["y"]).rows[0]
        omnibus = analyze_omnibus(df, "g", "y", "kruskal", "scale", True, True)
        expected = analyze_posthoc(omnibus).pairs
        for ours, theirs in zip(row.pairs, expected):
            self.assertEqual((ours.first, ours.second), (theirs.first, theirs.second))
            self.assertAlmostEqual(ours.z, theirs.statistic, places=12)
            self.assertAlmostEqual(ours.p_adjusted, theirs.p_adjusted, places=12)

    def test_single_analysis_and_batch_agree_on_small_groups(self):
        from omnibus_analysis import analyze_omnibus

        df = frame()
        single = analyze_omnibus(df, "UCLA_Level", "AssertiveAction", "kruskal", "scale",
                                 True, True)
        row = compare_many(df, "UCLA_Level", ["AssertiveAction"]).rows[0]
        self.assertAlmostEqual(single.statistic, row.statistic, places=12)
        self.assertEqual(single.p_value, row.p_permutation)
        self.assertEqual(single.p_asymptotic, row.p_asymptotic)
        self.assertTrue(any("fewer than five" in w for w in single.warnings))
        with self.assertRaises(ValueError):
            analyze_omnibus(df, "UCLA_Level", "AssertiveAction", "welch", "scale", True, True)

    def test_problems_are_explained_before_the_run(self):
        df = frame()
        keys = [(p.key, p.blocking) for p in check_grouping(df, "Sex")]
        self.assertEqual(keys, [("block.two_groups_for_omnibus", True)])
        keys = [(p.key, p.blocking) for p in check_grouping(df, "UCLA_Level")]
        self.assertEqual(keys, [("warn.small_groups_permutation", False),
                                ("warn.unequal_groups", False)])
        keys = [p.key for p in check_grouping(df, "UCLA_Level", method="anova")]
        self.assertIn("block.small_groups_parametric", keys)
        with self.assertRaises(ValueError):
            compare_many(df, "Sex", ["UCLA"])

    def test_family_survives_json(self):
        family = compare_many(frame(), "UCLA_Level", list(fx.SCALES[:2]))
        again = GroupFamily.from_dict(json.loads(json.dumps(family.to_dict())))
        self.assertEqual(again, family)


if __name__ == "__main__":
    unittest.main()
