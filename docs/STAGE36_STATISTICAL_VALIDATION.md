# Stage 36 — statistical validation

This document records how the Stage 36 statistics were validated:
the independent references (oracles), the tolerances and the
methodological decisions. All public tests use the synthetic fixtures
(`tests/fixtures/stage36/`); no participant data and no values derived
from private research material appear in the repository.

Tests: `tests/test_stage36_engine.py` (oracles), `tests/test_stage36_regressions.py`
(defects D2, D3, D4, D9, D10 now pass), `tests/test_omnibus_analysis.py`,
`tests/test_posthoc.py`. Stage 36.3 (item diagnostics, groups from scales,
defect D5): `tests/test_stage36_scales.py`, see the sections at the end.

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

Re-run at Stage 36.7 on the top of the stack (`claude/stage36-acceptance`), again
counts only (`correlate_many`, `compare_many` and pandas on the private
file, looked up among the numbers of the thesis's tables):

| Comparison | Result |
|---|---|
| Dataset | 55 rows × 13 columns, no missing cells; the same columns as the synthetic fixture |
| Spearman ρ and asymptotic p, UCLA with 8 scales | 8/8 and 8/8 found at 3 decimals (unchanged) |
| Kruskal–Wallis H (tie-corrected), 8 scales | 8/8 found at 3 decimals (the thesis reports them in three tables); H without the tie correction matches none, so both use the correction |
| Kruskal–Wallis asymptotic p | 7/8 found at 3 decimals; the eighth differs by 0.0001 (a rounding boundary) |
| Means and SDs of UCLA and the 8 scales | 9/9 and 9/9 (2 and 3 decimals) |
| Pearson r | 3/8 only: the thesis does not report Pearson coefficients for these pairs (it uses Spearman) |

## Chart Studio (36.4): charts never change a number

A result's charts are drawn from the values it was calculated on, stored
once with the result (`chart_studio.snapshot`, project format 5). Every
view (`ChartSpec`) is derived from those stored values (`chart_studio.derive`);
no view reads the dataset again and no view runs an analysis.

| Check | How it is verified | Result |
|---|---|---|
| Stored values equal the dataset | `snapshot` of UCLA, the 8 scales and UCLA_Level against the CSV columns | identical (NumPy `assert_allclose`, exact) |
| Heatmap coefficients from stored values | `derive` vs `prepare` on the dataset, Spearman, 9 × 9 | identical matrices (`assert_array_equal`); ρ(UCLA, first scale) equals SciPy `spearmanr` to 1e-12 |
| Changing the chart runs no analysis | every `analysis_runs.run_*` patched to fail while 10 chart types, 4 multi-boxplot layouts, points and palette are changed in the workspace | no call; the result object and its numbers unchanged; no new result |
| A view only uses what is stored | a variable that is not stored, or another group, is refused with an explanation | refused |
| Data changed after the result | the dataset's SHA-256 differs from the result's | charts are not prepared; the researcher is asked to recalculate |
| Restart | views, the active view and the report view restored from the project; drawn with the dataset removed from the session | identical PNG and SVG bytes |
| Ranges on one axis | two variables with spans 5 and 100 on one axis; panels; explicit z-scores | warning on one axis, none in panels, z-scores stated in the warning, note and alt text |

Display quantities (histogram bins, kernel density with the stated
bandwidth rule, box quartiles, display z-scores, means along a line, OLS
and LOWESS trend lines) are presentation only. They are computed while
drawing, labelled in the figure note, and never written into the result.
A line chart is offered only across the levels of a group the researcher
confirmed as ordinal, in an order the researcher can check and change.

## Research report (36.6): no number is computed for the report

`research_report.plan_report` writes the report from saved engine output and
the researcher's own entries only. Its tests check that the effects table
holds exactly the engine's rows with intervals; that a result calculated
twice with an identical report is written once (and says so) while results
from different data versions stay separate and are named; that a
reliability coefficient below .70 is reported with a methodological
warning, never changed; that hypotheses added after results were seen are
labelled exploratory (post hoc); and that small or very unequal groups and
missing values become stated limitations.

## Item diagnostics (36.3, `item_diagnostics.py`)

`diagnose_items` reuses the validated engines: `reliability.analyze_cronbach`
(α, its interval, α if item deleted), `omega_analysis.analyze_omega` (ω total,
loadings, refits without an item) and `omega_bootstrap.bootstrap_omega` (ω
interval). Oracles run on `synthetic_items_scale.csv` (200 invented
respondents, ten 1–5 items, 192 complete; two reverse-keyed items not
recoded, one item with a floor effect, nine missing answers).

| Quantity | Engine | Independent reference | Tolerance |
|---|---|---|---|
| Cronbach's α | `analyze_cronbach` (pingouin) | k/(k − 1)·(1 − Σs²ᵢ/s²ₜₒₜₐₗ) written out from sums; `pingouin.cronbach_alpha` called directly | 1e-12 |
| 95% interval of α | pingouin (Feldt 1965, F distribution) | 1 − (1 − α)·F⁻¹(.975 / .025; n − 1, (n − 1)(k − 1)) by hand | equal after rounding to 3 decimals (pingouin rounds; ≤ 5e-4) |
| Corrected item–total r | Pearson r of the item with the sum of the other items | r written out from sums; `analyze_omega`'s `corrected_item_rest_r` | 1e-12 |
| α if item deleted, Δα | `analyze_cronbach` on the same complete cases | the α formula recomputed on the k − 1 remaining columns | 1e-12 |
| ω total | `analyze_omega` | the engine called directly; (Σλ)² / ((Σλ)² + Σψ) from its loadings and uniquenesses | 1e-12 |
| ω if item deleted, Δω | `analyze_omega` refitted without the item on the SAME complete cases | `analyze_omega(complete[rest], rest)` called directly; a refit with its own listwise deletion uses 193 instead of 192 respondents and differs (checked) | 1e-12 |
| ω interval | `bootstrap_omega` (percentile, seed) | a direct call with the same seed and resamples; a second run | identical |
| Item M, SD (n − 1) | NumPy on the complete cases | sums written out | 1e-12 |
| Skewness G1, excess kurtosis G2 | `stat_results.describe_quantitative` | SciPy `skew` / `kurtosis` (`bias=False`) | 1e-10 |
| Floor / ceiling %, codes used | counts at the lowest / highest code | counted by hand | 1e-12 / exact |
| Reverse-key flags | sign of r and of the loading | the two items generated with negative loadings are exactly the flagged ones; recoded as 6 − x they "appear recoded" and α rises | exact |
| JSON | `to_dict` / `from_dict`, `structured()`, `result_store` | `json.dumps` → `json.loads` → equal objects | exact |

Decisions:

1. **One sample.** Every item statistic, α and ω use the listwise-complete respondents (as SPSS RELIABILITY); only the missing counts and percentages use all rows. ω if an item were deleted is refitted on the same complete cases, not on a new listwise selection of the remaining items, so Δω compares like with like.
2. **α interval.** Feldt's F-based interval as pingouin computes it; pingouin rounds the bounds to three decimals and the result says so. α if item deleted needs at least four items (the engine's rule); a three-item scale reports "Not applicable".
3. **ω model.** Every result lists the assumptions: one common factor (unidimensional), congeneric loadings, uncorrelated errors, maximum-likelihood one-factor analysis of the Pearson correlations of the complete cases, codes treated as interval numbers (no polychoric ω), and that obtaining ω does not test them. The largest residual correlation and the first two eigenvalues are reported. ω needs 3–12 items and at least max(30, 5k) complete respondents; otherwise it is "Not calculated" or "Unavailable" with the reason. ω if deleted is "Unavailable" with the reason when fewer than three items would remain or the refit fails (for example a Heywood solution).
4. **Non-convergence.** `analyze_omega` accepts an admissible solution even when statsmodels warns that the ML optimiser did not converge. The diagnostics keep the value, so they agree with the ω analysis, and say in the quantity's note and in the warnings that the fit did not report convergence.
5. **Reverse keying is flagged, never recoded.** A negative corrected item–total r or loading flags the item "possibly reverse-keyed and not recoded — check the scoring key". Items listed as reverse-keyed (from a confirmed definition) are reported as "appears recoded" (positive r), "appears not recoded" (negative r) or "unclear" (|r| < 0.10, or r and loading disagree). Directions are relative to the other items: when most items are unrecoded reverse-keyed items the signs flip.
6. **Confirmed definitions only.** `confirmed_reverse_keys` takes reverse keys from an imported scale whose reverse scoring the researcher confirmed (`reverse_confirmed`, which requires confirmed structure and codes) or from the `reverse_scored` flags of a saved questionnaire (set only by the researcher or from a confirmed review). Proposals, documented scoring groups and parser guesses never contribute; with nothing confirmed it returns nothing and says so. An unflagged questionnaire is not evidence that no item is reversed.
7. **No automatic deletion.** α and ω if an item were deleted, with Δα and Δω, are information. The result states that removing an item changes what the scale measures (content validity).
8. **Floor and ceiling.** Shares of answers at the lowest and highest possible code: given by the researcher, or else the smallest and largest code observed in any selected item (the result says which; the possible range may be wider). Effects are flagged at ≥ 15 %, a common convention, configurable (`floor_ceiling_percent`). Values outside given codes are counted and flagged (possible missing-value codes), not removed.

### Items versus totals (defect D5)

`item_response_problems(df, names)` reads values, not names. Heuristics:

| Rule | Item responses | Total or derived score |
|---|---|---|
| Whole numbers | all values | any value with decimals (`non_integer`, e.g. a mean score) |
| Distinct values | at most 11 (`MAX_ITEM_CATEGORIES`, e.g. 0–10) | more than 11 (`many_values`) |
| Range | largest − smallest code at most 10 (`MAX_ITEM_RANGE`) | wider (`wide_range`) |

A column breaking any rule "looks like a total"; non-numeric and empty columns are reported but are not called totals. The guided advice for "Check a questionnaire scale" then offers no coefficient (`block.totals_not_items` when every chosen column looks like a total, `block.total_among_items` for a mixed selection, in EN/LV/RU with the request to import item-level data), and `diagnose_items` refuses unless the researcher confirms the columns are item responses (`items_confirmed=True`, recorded in the result). On the 55-row fixture the eight scale totals, UCLA and Age look like totals; UCLA_Level (3 codes) and Sex (0/1) do not; all ten items of the item fixture pass and its total does not.

Among all methods (`total_score_problem`), the α, ω and item-diagnostics forms show the same explanation before Run and stay disabled until the researcher confirms "these columns hold answers to single items, not total or mean scores"; the confirmation is reset when the chosen columns change, listed with the result's confirmations and passed to `diagnose_items` as `items_confirmed`. It exists for the heuristic's false positives below; the guided advice never offers it. EFA/PCA are not reliability coefficients and are not checked. The engine entry point `run_method` is unchanged, so the ground-truth tests (continuous simulated items) run as before.

Limitations: a total of a few binary items (0–3) looks like an item; transformed item scores (0, 25, …, 100) and visual-analogue items look like totals.

## Groups from scales (36.3, `scale_groups.py`)

| Quantity | Engine | Independent reference | Tolerance |
|---|---|---|---|
| Quantile groups | type-7 sample quantiles at j/k with exactly computed positions (n − 1)·j/k; (a, b], first group [a, b] | `pandas.qcut` counts: k = 2–5 on the 55 UCLA values, k = 3–4 on the invented total with missing values; cut points against `numpy.quantile` | counts exact; cut points 1e-9 |
| Equal-width groups | `numpy.linspace(min, max, k + 1)` (or the stated range) | the same NumPy edges compared exactly; counts by hand and with `pandas.cut(x, k)` | exact |
| Bounds exactly on a cut point | explicit inclusivity flags | hand-made series: [0, 10] + (10, 20] vs [0, 10) + [10, 20]; median of 1–9 with `closed="right"`/`"left"`; equal width on 0, 10, 20, 30 | exact |
| Missing, non-numeric, out of range | counted, never grouped | a hand-made series with each case | exact |
| Source column, input frame | untouched | `assert_series_equal` / `assert_frame_equal` against copies | exact |
| History record | `kind`, `params` (rule, source, version, realised bounds, counts, statement), `output_columns` | stored with `Project.add_transformation` and read back; the derived ordered categorical survives `add_frame` / `load_frame` | exact |

Decisions:

1. **Four rules.** Documented thresholds (the researcher enters them and must name the source), custom ranges, quantiles (k groups) and equal-width intervals (k groups, observed minimum–maximum or a stated range). Rules are frozen, validated and versioned (`to_dict` / `from_dict`; unknown keys ignored, a newer version refused). Ranges are entered one by one (`range_rule`) or built from cut points without gaps or overlaps (`contiguous_rule`, a value on a cut point going to the lower or the upper group as stated).
2. **No hidden defaults.** Ranges carry explicit lower/upper inclusive flags; k-based rules carry `closed` ("right": (a, b] with the first group [a, b], as `qcut`; "left": [a, b) with the last group [a, b]). The preview lists every group's bounds and inclusivity.
3. **Exact quantile positions.** Cut points use exact rational positions so that a cut point that should fall on an observed value does. pandas ≥ 3 `qcut` nudges non-representable probabilities (1/3, 2/3, …) upward for the same reason and agrees; pandas 2 `qcut` uses the rounded probability, so when (n − 1)·j/k is a whole number its cut point can land just below that observed value and move it (and its ties) to the upper group.
4. **Nothing is put into a group silently.** Missing, non-numeric and out-of-range values become missing in the new variable and are counted in the preview, the message and the record. Overlapping ranges are reported by the preview and refused by `apply`. Gaps are reported unless no possible value (for whole-number data: no whole number) can fall into them.
5. **Warnings before anything is applied:** empty groups, groups under five values, quantile cut points on tied values when the groups differ by more than the one value that n/k allows, overlaps, gaps, thresholds that are not whole numbers when every value is (no value can equal them; check sum versus mean scoring) and ranges that cannot contain a whole number.
6. **Wording.** Documented cut points are described as "as entered by the researcher from <source>", not checked by the program, to be verified against the manual. Custom ranges are "researcher-defined … not clinical norms or validated cut-offs"; quantile and equal-width groups are "data-derived … not norms", and quantiles "depend on this sample". The test checks that "norm" never appears without a negation for these rules and not at all for documented thresholds.
7. **The derived variable** is a new ordered categorical column (labels in rule order); the source column is never changed, and an existing target name is refused.
8. **Existing groupings are proposed, never chosen.** `existing_groupings` proposes columns named like the scale plus a grouping word (level, group, cat, tertile, …; also Latvian and Russian words) with 2–10 categories, and says whether the categories cover separate, ordered ranges of the scale (UCLA_Level: 37–39, 40–59, 60–68 on the fixture).

Limitations: documented thresholds are as typed; the program cannot check them against an instrument's manual, edition or population. Proposals of existing groupings depend on column names.

## Scope

Stage 36.3 was validated on synthetic data only: no private acceptance
check was run for item diagnostics or groups from scales (the owner's data
hold scale totals, not item responses).
