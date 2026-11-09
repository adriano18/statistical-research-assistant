# Stage 36 — statistical validation

This document records how the Stage 36 statistics were validated:
the independent references (oracles), the tolerances and the
methodological decisions. All public tests use the synthetic fixtures
(`tests/fixtures/stage36/`); no participant data and no values derived
from private research material appear in the repository.

Tests: `tests/test_stage36_engine.py` (oracles), `tests/test_stage36_regressions.py`
(defects D2, D3, D4, D9, D10 now pass), `tests/test_omnibus_analysis.py`,
`tests/test_posthoc.py`.

## Oracles and tolerances

| Quantity | Engine | Independent reference | Tolerance |
|---|---|---|---|
| Holm, Benjamini–Hochberg, Bonferroni | `multiple_comparisons.adjust` (hand-written step-down/step-up) | statsmodels `multipletests` (`holm`, `fdr_bh`, `bonferroni`), 100 random families including ties | 1e-12 |
| Mean, SD (n − 1), quartiles, percentiles, IQR | `stat_results.describe_quantitative` | sums written out; NumPy `percentile(method="linear")` | 1e-12 |
| Skewness G1, excess kurtosis G2 | pandas `skew`/`kurt` | SciPy `skew(bias=False)`, `kurtosis(bias=False)` | 1e-10 |
| 95% CI of the mean | t distribution | SciPy `t.interval` with `sem` | 1e-10 |
| Pearson r, p, 95% CI | validated single-pair engine (`correlation.py`) | NumPy `corrcoef`; t = r√((n−2)/(1−r²)) with Student t; Fisher z by hand (atanh, 1/√(n−3), tanh) | 1e-12 (r), 1e-10 (p, CI) |
| Spearman ρ | same engine | Pearson correlation of average ranks (pandas `rank`) | 1e-12 |
| Spearman asymptotic p (option) | SciPy `spearmanr` | t approximation with n − 2 df by hand | 1e-10 |
| Kendall τ-b | SciPy `kendalltau(variant="b")` | O(n²) count of concordant/discordant pairs with tie corrections, written from the definition | 1e-12 |
| Kendall p | SciPy, method chosen and stated (exact without ties and n < 50, else asymptotic) | SciPy `kendalltau(method="asymptotic")` called directly | 1e-12 |
| Spearman/Kendall bootstrap CI | `batch_correlation.bootstrap_ci` | reproducibility (same seed → identical interval); coverage simulation: 200 bivariate-normal samples, n = 55, ρ = .4, population ρ_s = 6/π·asin(ρ/2) | coverage **0.95** observed; test accepts 0.88–0.99 |
| Kruskal–Wallis H (tie-corrected), df, χ² p | SciPy `kruskal` | H written out from rank sums with the tie correction; `chi2.sf(H, k − 1)` | 1e-10 (H), 1e-12 (p) |
| Permutation p of H | vectorised permutation of labels with fixed ranks | exact enumeration of all 90 assignments for groups of 2/2/2 | ±0.01 (19,999 permutations) |
| Permutation vs χ² p with large groups | — | 3 × 20 observations | ±0.03 |
| η²_H, ε²_R | `batch_groups` | (H − k + 1)/(N − k) truncated at 0; H/((N² − 1)/(N + 1)) | 1e-12 |
| Dunn pairwise z, Holm p | `posthoc_analysis.dunn_pairs` (extracted, unchanged formulas) | the validated `analyze_posthoc` on the same data (≥ 5 per group) | 1e-12 |
| Single analysis vs batch | `omnibus_analysis` (Kruskal–Wallis with a group under five) | `batch_groups.compare_many` | H 1e-12; identical p |

## Methodological decisions

1. **Raw p-values are never changed.** Adjusted p-values are stored next to them with the procedure and the family size. Tests that could not be computed are left out of the family and keep no adjusted value.
2. **Pearson CI by Fisher z only.** Spearman ρ and Kendall τ get a percentile bootstrap over paired resamples (default 2,000; seed per pair [seed, crc32(x), crc32(y)], so a pair's interval does not depend on the order of the pairs). Resamples without variation are counted, reported and left out. With more than 10% failed resamples no interval is given ("Unavailable").
3. **Spearman p.** The default is the single-pair engine's permutation p (1,999 resamples, fixed seed, n ≤ 500), so a batch never contradicts a single analysis. The option `spearman_p="asymptotic"` gives the t approximation SPSS reports, so published results can be reproduced; the method is stated in every row either way.
4. **Magnitude labels.** The coefficient is the effect size. Labels follow a named, configurable rule (Cohen's 1988 benchmarks for r and ρ, described as conventions). No labels for τ, because the r benchmarks do not transfer to τ.
5. **Kruskal–Wallis with small groups.** The single and batch analyses now rank groups of at least two values. When a group has fewer than five values the χ² approximation of H is unreliable, so the primary p is a Monte Carlo permutation p (9,999 permutations, seed 36; p = (exceedances + 1)/(B + 1)) and the small groups are named in the warnings. ANOVA and Welch keep five per group. The two-category case (e.g. Sex) is explained before the run, with the two-group comparison offered instead.
6. **Effect-size names.** The single Kruskal–Wallis analysis reports (H − k + 1)/(N − k) under the label "Rank ε² (truncated at 0)". Tomczak & Tomczak (2014) call this η²_H and reserve ε²_R for H/((N² − 1)/(N + 1)). The formula is unchanged. The batch analysis reports both, each with its definition. Renaming the single-analysis label is left to a separate, reviewed change, because saved reports carry it.
7. **No fictitious statistics.** A value the engine did not compute has a status (not applicable, not calculated, unavailable, calculation failed) and the reason, never a zero, a dash or "Not captured". Descriptive statistics now carry these quantities (defect D2).

## Private, authorized acceptance check (counts only)

In an authorized local session, the engine was run on the owner's
private 55-participant dataset and compared with the results reported in
the owner's thesis. No values, rows or text from those materials are in
this repository; only agreement counts:

| Comparison | Result |
|---|---|
| Spearman ρ, UCLA with 8 scales | **8/8 identical** to 3 decimals |
| Reported p-values | 8/8 equal the asymptotic t approximation (now available as `spearman_p="asymptotic"`); the default permutation p differs by at most 0.026 (7/8 within 0.02) |
| Reported 95% intervals | all 16 bounds within 0.03 of the engine's percentile bootstrap bounds (consistent with a bootstrap interval in the original analysis; exact agreement is not expected) |
| Kruskal–Wallis by UCLA level (groups 3/47/5), 8 scales | all 8 reported p-values equal the engine's asymptotic p; the engine's primary p is the permutation p because of the group of 3 |

## Not yet validated here

Item-level psychometrics (36.3) and charts (36.4) are validated in their own
pull requests; this document will gain their sections.
