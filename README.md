# Statistical Research Assistant

A Python project for exploring research datasets and, later, selecting and interpreting statistical methods.

**Goal:** a small, transparent alternative to common SPSS workflows for psychology, marketing and business research. The program will calculate statistics using established Python libraries. A future assistant may explain results, but it must not invent numbers or choose tests without checking their assumptions.

**[Full development roadmap](ROADMAP.md)** — finish essential statistics, validate results, maintain usable copy/save workflows, then add optional AI and multilingual UI/UX.

## Development plan
1. **v0.1 Data inspection** — import CSV/XLSX, review variables, missing values and their inferred data types.
2. **v0.2 Descriptive statistics** (in progress) — N, mean, median, SD, distributions and plots.
3. **v0.3 Research methods** (in progress) — reliability, correlations, independent/paired tests, χ², three omnibus methods and their post-hoc comparisons; linear/multiple regression now implemented; repeated-measure tests and more advanced models remain planned.
4. **v0.4 Method advisor / AI** — after statistical validation, recommend candidate tests from study design; optionally explain results with AI, without inventing calculations.
5. **v0.5 Reports and localization** — local TXT/PNG export currently available for paired analyses; expand to APA tables, DOCX/PDF and English, Latvian and Russian.

## Desktop interface

The Flet application uses a left navigation menu instead of one long scrolling page:

- **Dataset**: load a local CSV/Excel file or a sample, inspect variables and missing values.
- **Descriptive**: choose a variable, confirm its scale, and view statistics and a graph.
- **Scale reliability**: select questionnaire items, compute Cronbach’s α and view an APA-style report.
- **Correlations**: analyze two variables with Pearson or Spearman and view the scatterplot.
- **Correlation matrix**: compare up to eight variables in a heatmap with pairwise N.
- **Compare groups**: compare two independent groups with Welch’s t or Mann–Whitney U, APA-style results and boxplots.
- **Paired measures**: analyze repeated before/after observations with paired t or Wilcoxon, plus a participant-level change plot, compact results and local exports.
- **Chi-square**: analyze two categorical variables, inspect observed/expected counts, Cramér’s V and sparse-table cautions.
- **ANOVA / Kruskal**: compare 3–8 independent groups, review effect estimates, group distributions and omnibus cautions.
- **Linear regression**: fit a model with one to five quantitative predictors, inspect coefficients, residuals, multicollinearity, influence and optional robust standard errors.
- **Repeated measures**: Friedman or Greenhouse–Geisser-adjusted repeated-measures ANOVA, paired Holm comparisons and individual trajectories.

Use **Dataset** first. Switching between sections preserves analysis results until a new dataset is loaded. The calculation modules and the local-data privacy approach have not changed.

## What changed in the current interface

The desktop workspace now keeps **Copy report**, **Save TXT as...** and **Save PNG as...** above the scrolling analysis panel. After completing an analysis, use these buttons to copy its APA-style text or choose a destination in the Windows Save dialog. **Nothing is uploaded to a cloud service.** The toolbar applies to descriptive statistics, reliability, correlation, correlation matrix, independent/paired tests, chi-square and ANOVA/post-hoc.

After loading a fresh dataset the previous output buttons are cleared. Switching sections preserves the last completed result for each analysis. For ANOVA, run **post-hoc comparisons** before exporting to include the updated pairwise table in the APA TXT file.

**Explore boxplots:** Open **Descriptive → Explore**. Choose a quantitative outcome and optionally a grouping variable (for example `score` and `group` from **Load three-group example**). Click **Explore distributions** to display group boxplots, individual observations, a normal Q–Q plot and Shapiro–Wilk. With groups selected, it also computes a median-centered Levene/Brown–Forsythe variance check. Review the caveats; **a nonsignificant Shapiro test does not prove normality**.

The menu is grouped by purpose, the export controls stay visible while scrolling, ANOVA figures are above long explanations, methodological notes can be collapsed, and the post-hoc comparisons display in a table. See [ROADMAP.md](ROADMAP.md) for remaining SPSS-style methods, planned localization (EN, LV, RU) and the Flet versus PySide6 decision.

## Quick start

Requires Python 3.12 or newer. In PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python inspect_data.py examples/sample_survey.csv
python -m unittest discover -s tests -v
flet run app.py
```

The Flet app has **Open CSV / Excel** and **Load example** buttons. Select a variable and confirm its measurement scale before using **Analyze selected variable**. Columns named like `participant_id` are flagged as identifiers and excluded from score statistics. Quantitative variables show N, mean, median, SD and a histogram; nominal and ordinal variables show frequency counts and a bar chart. Brief guidance explains what these descriptive results do and do not establish. Real data is processed locally, not uploaded.

## Scale reliability demo

In the desktop app, click **Load scale example**. Select `stress_q1`, `stress_q2`, `stress_q3` and `stress_q4`. Confirm that the selected items measure a single construct and any reverse-coded items have already been recoded, then click **Calculate Cronbach's alpha**.

The separate `examples/sample_scale.csv` contains 32 invented respondents and two missing answers, so 30 complete cases are analyzed. The result includes Cronbach’s α, a 95% confidence interval, alpha-if-item-deleted and warnings. The UI now shows a copyable APA 7-style sentence with Greek α and decimal notation (e.g., `α = .94, 95% CI [.89, .97]`), plus a PNG figure with the full-scale confidence interval and individual item-deletion estimates.

**Interpretive ranges are not APA 7 rules.** Approximate thresholds (< .60 low; .60–.69 questionable; .70–.79 often acceptable; .80–.89 good; .90–.95 very high; > .95 investigate redundancy) are contextual guidelines, not tests of scale validity. Compare scales with the relevant literature and study design. The figure number `Figure 1` is a placeholder to renumber if inserted into a manuscript. This synthetic dataset is not evidence for the reliability of any real instrument.

Alpha is not a test of scale validity or unidimensionality. Numerical column types alone are not grounds to treat variables as questionnaire items. The prototype uses listwise deletion and does not perform reverse scoring for you.

The sample dataset is fictional and is **not suitable for scientific conclusions**.

## Correlation demo

In the desktop app, click **Load scale example**. Under **CORRELATION ANALYSIS**, choose the two items `stress_q1` and `stress_q2`. Confirm **Ordinal** for both, keep **Spearman’s ρ**, then click **Calculate correlation**.

For Pearson, choose two genuinely quantitative measurements, confirm their scales, inspect whether a linear association and the study assumptions are appropriate, then select **Pearson’s r** and check its separate assumptions box. Numeric column storage alone does not justify Pearson. Do not include IDs or nominal groups.

Both methods report the correlation coefficient, a two-sided p-value, paired N, a scatterplot and a brief interpretation in APA 7-style notation. Pearson additionally reports a Fisher-transformation 95% CI. Spearman's CI is **not calculated** in this prototype; do not invent one. For datasets with up to 500 complete pairs, Spearman uses a seeded, 1,999-resample permutation p-value because SciPy warns its asymptotic p approximation is inaccurate for small datasets. This is a Monte Carlo estimate, not an exact test.

Plots show associations, not causality. The Figure 2 number is a placeholder and should be renumbered in a manuscript. The app does not choose the method automatically from the column data type; it supplies conditional guidance. For scientific analysis, consider dependence, outliers, monotonicity/linearity, sample design, effect interpretation and multiple testing.

## Exploratory correlation matrix (Step 6)

Use **Load scale example**. Under **CORRELATION MATRIX**, tick `stress_q1`, `stress_q2`, `stress_q3` and `stress_q4`. Select **Spearman’s ρ** for these numeric-coded ordinal items, confirm the measurement scales and choose **Calculate correlation matrix**.

The figure displays coefficients and the number of complete pairs (N) in each cell. Unlike the two-variable correlation analysis, this is deliberately **descriptive only**, with no p-values, confidence intervals or significance stars. Values can be N/A if there are fewer than five pairs or no variation. Selecting many correlations for significance testing requires a separate plan for multiple testing and appropriate assumptions.

The earlier two-variable scatterplot now shows a small reproducible **display-only jitter** for overlapping ordinal points. Calculations still use the unmodified values. Figure notes wrap instead of being cut off. Figure numbers are manuscript placeholders, not final APA numbering.

## Compare two independent groups (Step 7)

1. Open the desktop app and choose **Dataset → Load scale example**.
2. In the sidebar choose **Compare groups**.
3. Choose **group** for the grouping variable and **stress_q1** for the outcome.
4. Confirm **Ordinal** for the outcome, choose **Mann–Whitney U**, and check that the observations are independent. Click **Compare groups**.
5. For a Welch example, load **survey example**, choose **group** and **age**, confirm **Quantitative**, select **Welch’s independent t**, and confirm both independent observations and assumption review.

The report includes group means, SDs, medians, sample sizes, test statistic, two-sided p-value, effect estimate and an APA 7-style boxplot with individual points. Welch additionally reports fractional degrees of freedom, the 95% CI of the **mean difference (first group minus second)** and a pooled-SD Hedges g. Mann–Whitney reports U and rank-biserial r (positive means the first group tends to have higher ranks); no confidence interval for this rank effect is currently implemented. When there are ties, Mann–Whitney uses SciPy's tie-corrected asymptotic method.

**Research caveats:** this module is only for two **independent** groups. Paired samples require another method. Mann–Whitney is not universally a median test, and unequal group shapes complicate interpretation. The checkbox does not test assumptions. The included examples are artificial and too small for substantive generalization. Figure numbering is a placeholder for a manuscript.

## Paired measurements (Step 8)

1. In **Dataset**, choose **Load paired example** (`examples/sample_paired.csv`).
2. Open **Paired measures**. The example preselects `before_score` and `after_score`.
3. For an ordinal example, choose **Ordinal** and **Wilcoxon signed-rank**. Check that every row contains both measurements from the same participant. Review the paired differences, their approximate symmetry, outliers and independence *between* participants, then click **Compare paired scores**.
4. For a mean-change analysis, confirm **Quantitative** and select **Paired-samples t-test** after reviewing the distribution of differences.

The example contains 24 fictional participants, 22 with both scores present. The updated paired screen separates **A. Main result**, **B. Descriptives**, **C. Notes / assumptions**, followed by full APA 7-style text and a before/after plot. Use **Save figure PNG** or **Save APA report TXT** to write local files into the ignored `reports/` directory. These filenames are overwritten by the next export; there is no cloud upload. Both tests analyze only complete pairs. Results include sample sizes, descriptives, a two-sided p-value, appropriate effect estimates and a graph connecting paired observations. For the t-test, **mean change = after − before**, its 95% confidence interval, fractional-free df (N−1), and Cohen's *dz* are shown. Wilcoxon reports **W**, the matched-pairs rank-biserial correlation, and the number of zero differences; it does not report an invented CI.

**Important:** a paired t-test examines mean differences, not whether the before and after distributions are individually normal. Wilcoxon uses ranks of nonzero differences and is not always a simple median-change test. Do not use either test for independent groups. The sample is synthetic and is not evidence of intervention effectiveness. Figure numbering is illustrative, not final manuscript numbering.

## Chi-square independence (Step 9)

In **Dataset**, choose **Load categorical example** (`examples/sample_categorical.csv`). Open **Chi-square** and select `group` and `outcome`. Confirm independent observations and categorical measurement scales, then click **Calculate χ²**.

The report includes the uncorrected Pearson χ² statistic, degrees of freedom, two-sided asymptotic p-value, N, observed and expected frequencies, Cramér's V and a contingency-table figure. If any expected cell count is below 5, the app warns that the asymptotic p-value may be unreliable. For sparse **2×2** tables, it also displays a separate two-sided Fisher exact p-value. **These tests do not prove causation**, and sparse tables beyond 2×2 need other exact or resampling approaches.

Use **Save figure PNG** or **Save APA report TXT** to export the Chi-square chart and findings to the local ignored `reports/` folder. Files are overwritten on re-export with the same name. The example uses fabricated category counts and is not evidence of intervention effectiveness. Figure 6 is a placeholder manuscript figure number.

## ANOVA and Kruskal–Wallis (Step 10)

In **Dataset**, click **Load three-group example** (`examples/sample_three_groups.csv`). Select **ANOVA / Kruskal** in the sidebar.

For the default rank-based example, select `group` and `score`, confirm **Ordinal**, choose **Kruskal–Wallis H**, then confirm that observations are independent and you reviewed the assumptions. Click **Run group comparison**. To try classical one-way ANOVA or Welch ANOVA, select **Quantitative** before switching to the corresponding method. The synthetic example has three groups with 12 observations in each.

The output contains the omnibus F or H statistic, degrees of freedom, two-sided asymptotic p-value, sample sizes and an appropriate effect estimate. Classical ANOVA and Welch ANOVA show a descriptive η² (the Welch value is **not a Welch-weighted effect size**). Kruskal–Wallis shows a nonnegative rank ε² estimate. The boxplot displays group distributions and individual observations. The **Save figure PNG** and **Save APA report TXT** buttons save to the local Git-ignored `reports/` directory.

**Post-hoc comparisons:** after calculating an omnibus test, use **Run post-hoc comparisons**. The selection follows the method automatically: Tukey HSD (or Tukey–Kramer with unequal group sizes) for ordinary ANOVA, Games–Howell for Welch, and tie-corrected Dunn with Holm-adjusted p-values for Kruskal–Wallis. The resulting table shows every group pair, its signed mean or rank difference, and multiplicity-adjusted p-values. Tukey and Games–Howell also show 95% simultaneous confidence intervals; Dunn does not currently provide them. Running post-hoc tests updates the APA TXT export; use **Save APA report TXT** afterward.

**Important:** omnibus significance does *not* identify which groups differ without a suitable post-hoc procedure. Even with adjusted p-values, assumptions and substantive effect sizes must be reviewed. For nonsignificant omnibus tests, pairwise comparisons are labelled exploratory. Kruskal–Wallis is a rank/distribution test, not necessarily a test of median differences. For Welch ANOVA this project requires **SciPy 1.16 or newer** (the `equal_var=False` option was introduced in that release). The example is fictional and cannot support substantive research conclusions.

## Linear and multiple regression (Step 12)

In **Dataset**, click **Load regression example** (`examples/sample_regression.csv`). Open the **Linear regression** sidebar section. The fictional study contains 48 rows with `stress_score` as the dependent variable and `study_hours`, `sleep_hours` as predictors. Leave one predictor selected for a simple linear regression, or select both for multiple regression.

Confirm you reviewed the measurement scales, **independence between observations**, linear relationship, outliers and study design. Choose **Fit linear model**. The report provides model F, R², adjusted R², unstandardized coefficient B with SE, t and 95% CI, along with residual Shapiro–Wilk p, Breusch–Pagan p, Cook's D count and VIF for multiple predictors. The figure shows observed vs fitted, residuals vs fitted, and normal Q–Q plots.

The **HC3** option changes *coefficient* standard errors, t statistics, p-values and 95% confidence intervals to heteroskedasticity-robust estimates; the displayed model F remains the **conventional OLS F** (not a robust Wald F). Use the top **Copy report**, **Save TXT as...** or **Save PNG as...** buttons to export the result.

**Research cautions:** predictors must represent meaningful **quantitative** measurements, not arbitrary nominal codes; categorical factors require dummy coding, which is not automatic here. Missing cases are removed listwise. These associations do not establish causality. Shapiro and Breusch–Pagan results are diagnostics, not assumption guarantees. Do not interpret a significant coefficient before checking the study design and potential confounders.

The implementation uses [statsmodels](https://www.statsmodels.org/) for OLS estimation. Repeated-measure comparisons (**Friedman** and **repeated-measures ANOVA**) are still a separate upcoming stage, because the subjects/rows and assumptions differ substantially.

## Friedman and repeated-measures ANOVA (Step 13)

In **Dataset**, choose **Load repeated example** (`examples/sample_repeated.csv`). Open **Repeated measures** from the sidebar.

The example represents 32 fictional participants measured on three occasions, with 31 complete sets of scores. Each selected column is one occasion of the **same construct**; the application assumes **one participant per row**. Choose `stress_before`, `stress_mid` and `stress_after` in the intended chronological order.

For ordinal responses, confirm **Ordinal** and select **Friedman test**. For suitable quantitative scores, confirm **Quantitative** and select **Repeated-measures ANOVA**. Check both the same-participants/design confirmation and the assumptions confirmation, then choose **Analyze repeated scores**.

Outputs include the omnibus statistic and sample size, Kendall’s W (Friedman) or partial η² (RM ANOVA), the occasion descriptives, a participant-trajectory figure and all paired comparisons with **Holm-adjusted** p-values. Friedman uses tie-corrected SciPy χ² and Wilcoxon signed-rank post-hoc. RM ANOVA uses Greenhouse–Geisser-corrected degrees of freedom for its **primary** p-value, and paired t tests for post-hoc comparisons. The uncorrected RM ANOVA p-value is shown separately.

Use the shared **Copy report**, **Save TXT as...** and **Save PNG as...** toolbar.

**Limitations:** no Mauchly sphericity test, no adjusted simultaneous confidence intervals and no mixed-effects handling of incomplete repeated observations. Participants with any missing selected occasion are excluded. Paired tests assume the selected timepoints describe the same people; choose other analyses for independent groups. These are synthetic examples, not evidence of treatment effects.

## Interface languages

The application currently uses **English (EN)**. **Latvian (LV)** and **Russian (RU)** are explicitly planned in [ROADMAP.md](ROADMAP.md). A future language selector should translate menus, messages, cautions and report narratives, not just button labels. APA 7 statistical symbols remain unchanged across languages.

## Privacy and analysis notes
- Keep actual participants' data in the ignored `data/` folder. Do not commit identifiable research data.
- Numeric codes such as 1–5 can represent ordinal Likert responses or categorical groups. A numeric data type is not enough to determine the measurement scale or justify a statistical test.
- The current version inspects datasets and calculates selected statistics and correlation tests. It does **not** automatically validate assumptions, establish causality or replace professional interpretation.

Developed as a learning project, with AI assistance for code explanations, documentation and debugging.
