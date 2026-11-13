# Stage 37 — research methods increment (Issue #66)

Branch `claude/stage37-methods`, from `stage37/master-acceptance-interoperability-spec` (`2f9af71`).

This increment adds:

- the path models of the master's plan: mediation, moderation and conditional process, with structures equivalent to PROCESS Models 4, 1, 7 and 14;
- a linear model with categorical covariates (independent review S3);
- their diagnostics, the missing-data policy and a sensitivity simulation;
- their place in the guided workspace, in EN/LV/RU;
- the synthetic H1–H6 acceptance scenario ([`STAGE37_MASTER_ACCEPTANCE.md`](STAGE37_MASTER_ACCEPTANCE.md)).

All data used are synthetic. **No result of this increment is an empirical finding.**

**Rule of this file.** An item is *done* only when a named test proves it.

## 1. Models

Every model is computed by this program (`process_models.py`), **not by the PROCESS macro**. Every methods text says so: "Structure equivalent to PROCESS Model N (Hayes, 2022); computed by this program, not by the PROCESS macro." Each equation is an ordinary least squares regression (statsmodels). The researcher's covariates enter every equation.

| Model | Equations | Reported |
|---|---|---|
| **4**: simple or parallel mediation (1–4 mediators) | Mⱼ = a0ⱼ + aⱼX + C; Y = b0 + c′X + Σ bⱼMⱼ + C; total: Y = c0 + cX + C | a, b, c′, c; each indirect effect aⱼbⱼ and the total indirect effect with percentile bootstrap intervals; completely standardized indirect effects (partially standardized when X is 0/1) |
| **1**: moderation | Y = b0 + b1X + b2W + b3XW + C | b3 with t test; ΔR² of XW with F test; f²; conditional effects of X at W values; Johnson–Neyman values |
| **7**: W moderates X → M | Mⱼ = a0 + a1X + a2W + a3XW + C; Y = b0 + c′X + Σ bⱼMⱼ + C | index of moderated mediation a3·b; conditional indirect effects (a1 + a3w)·b; conditional effects of X on M; ΔR²; direct effect |
| **14**: W moderates M → Y | Mⱼ = a0 + aX + C; Y = b0 + c′X + Σ b1ⱼMⱼ + b2W + Σ b3ⱼMⱼW + C | index a·b3; conditional indirect effects a·(b1 + b3w); conditional effects of M on Y; ΔR² of the product(s); direct effect |

**Bootstrap.**

- Percentile bootstrap. The default is **B = 5000** with a **fixed seed (37066)**; B, the seed and the number of valid resamples are reported in the methods text, the run's inputs and the stored provenance.
- Resample indices come from `numpy.random.default_rng(seed).integers(0, n, (B, n))` in one call. Their SHA-256 is stored with the run.
- Every resample is re-estimated with numpy least squares (LAPACK `gelsd`). A resample whose design is singular is left out and counted.
- The limits are the 2.5th and 97.5th percentiles with linear interpolation (Hyndman–Fan type 7, numpy's default).
- Conditioning values of W stay fixed at their analysis-sample values.
- No p-value is given for an indirect effect.

**Conditioning values of W.**

- mean − 1 SD, mean and mean + 1 SD (sample SD, n − 1);
- the 16th, 50th and 84th percentiles (type 7);
- values the researcher chooses (engine option `w_values`).

A W with two values is evaluated at both. A value outside the observed range is kept and flagged as an extrapolation.

**Options.**

- **HC3.** Optional HC3 path standard errors, with t-based p-values and intervals as in `regression_analysis.py`. Model F and the ΔR² F tests stay classical; with HC3 the HC3 Wald F of each product is added.
- **Mean-centring.** Optional. It applies to the variables that form products, wherever they are predictors. Conditional effects are always given at W values in the original metric, so they do not depend on centring (tested).
- **Johnson–Neyman (Model 1).** The values of W where p = .05 are the roots of (b1 + b3u)² = t²(v11 + 2u·v13 + u²·v33), with u = W − centre. Only roots in the observed range are kept, with the share of the sample below and above each. Without a root the result states whether the effect is or is not different from zero over the whole range. **Validated** (§4).

**Effect sizes.**

- R² and adjusted R² of every equation.
- ΔR² of the product(s), its F test and Cohen's f² = ΔR²/(1 − R²).
- Standardized coefficients β = b·SD(predictor)/SD(outcome) for quantitative predictors. β is not defined for the constant, products and 0/1 predictors.

**Linear model with categorical covariates (`linear_model.py`, review S3).**

- Y on quantitative predictors.
- Nominal (or ordinal-as-categories) variables enter **only as dummy codes** against a **stated reference category**. The rule is first, last or most frequent, or a category the researcher names. The result's coding table states each reference.
- An optional product term: quantitative × quantitative, quantitative × categorical (one column per dummy) or categorical × categorical, with optional mean-centring.
- Block tests (ΔR², F, f²) for each categorical variable and each product. A factor that forms a product is tested together with its products, and the block says so.
- β for quantitative predictors only, HC3 as an option, and the same diagnostics as the path models.
- `regression_analysis.py` is unchanged.

## 2. Diagnostics, missing data, sensitivity

**Residual diagnostics.** For every equation:

- Shapiro–Wilk p, with a Q–Q panel in the figure;
- Breusch–Pagan (Koenker) p;
- Cook's distance (maximum, count above 4/N);
- leverage (maximum, count above 2p/N), with the residuals-vs-leverage panel;
- the VIF of every column.

Products of uncentred variables get a note: their high VIF is structural.

**Missing data.**

- **Listwise deletion** over every model variable. All equations of a model use the same complete cases.
- A missingness table gives the count and % per variable.
- When at least 2 cases are left out, a table compares the analysed and the left-out cases on every variable they have: n, M (SD) and the standardized difference. It is labelled descriptive: it cannot show whether values are missing at random. With fewer cases, a note says the comparison is not meaningful.
- **Sensitivity comparison.** `compare_estimates(first, second)` sets two fits side by side. The acceptance scenario uses it for complete cases against prorated scores (the mean of the answered items), which keeps the cases with a missing item.

**Monte Carlo sensitivity simulation** (`sensitivity_simulation`, option *500 replications*). It is labelled in every language as *assumed population values; not a result about these data* and *not "observed power"*.

- **Design.** The same model at the given N. Exogenous rows (X, W, covariates) are resampled from the data. The non-focal coefficients and the residual variances are the sample estimates. The focal coefficient takes a grid of assumed standardized values:
  - Model 1: the product, standardized b3·SD(X)·SD(W)/SD(Y), 0–.25;
  - Model 4: every aⱼ and bⱼ, .10, .14, .26 and .39;
  - Model 7: a3, with b at its estimate;
  - Model 14: b3, with a at its estimate.
- **Detection.** For Model 1, a two-sided p < .05 for the product. For the others, a 95% Monte Carlo interval (2000 draws) of the product of coefficients that excludes zero.
- B, the seed and the replications are reported.
- **Validated** for Model 1 against the noncentral-t power and the type I error (§4).

## 3. The workspace

**Methods** (`workspace_methods.METHODS`, family "models"):

| Method key | Title | Roles |
|---|---|---|
| `linear_model` | Linear model with categorical covariates | outcome; quantitative predictors (0–10); categorical covariates (0–4, dummy codes); product term: two predictors of the model |
| `mediation` | Mediation (PROCESS-equivalent Model 4) | X; M (1–4, the researcher's); Y; covariates (0–8) |
| `moderation` | Moderation (PROCESS-equivalent Model 1) | X; W; Y; covariates |
| `conditional_process` | Conditional process (PROCESS-equivalent Model 7 or 14) | X; M; W; Y; covariates; option *which path W moderates* (7 or 14) **without a default** |

X, W and the covariates are quantitative or coded 0/1. A nominal variable with more categories is refused with an explanation (dummy codes first). M and Y are quantitative.

**Confirmations.**

- Design:
  - *mediators named from theory or the plan before seeing results, not by their p-values*;
  - *cross-sectional data cannot establish causal mediation*;
  - *moderator named before seeing results*;
  - *I chose Model 7 (W moderates X → M) from theory, before seeing results*, or the same sentence for Model 14. Each is asked only when its model is chosen.
- Data: *linearity, residuals, influential cases, measurement scales and missing data reviewed*.

The runner refuses to run without every confirmation the method asks for.

**Nothing is chosen for the researcher.**

- The engine refuses an unstated model.
- The new guided goal *Test a mediation or moderation model* (`process`) follows the researcher's roles:
  - mediators only give Model 4;
  - W only gives Model 1;
  - both give a conditional process model with **no model chosen**. Model 7 and Model 14 are both offered as alternatives. Run stays disabled, and a notice says what to choose (`guided-choose-option`, `form-choose-option`).
- `advise()` never returns Model 7 or 14.
- Mediators are never suggested or screened by p-values. No text proposes it, and the advice says that a significant total effect is not required (Hayes, 2022).

**Guided "predict".** Categorical predictors now lead to the linear model with dummy codes. They used to be refused: *block.categorical_predictors*. One category variable with up to three quantitative covariates stays ANCOVA, as before.

**Texts.**

- Engine and report texts in `process_text.TEXT` (EN/LV/RU, audited by `tools/locale_audit.py`): tables, summary, interpretation, methods text and notes.
- Interface texts in `workspace_text` (`goal.process*`, `role.process_*`, `role.mediators`, `role.moderator`, `role.factors`, `role.product_*`, `block.process_*`, `block.choose_option`, `option.moderated_path`, `block.linear_no_predictor`, `block.product_*`, `why.mediation`, `why.moderation`, `why.conditional_process`, `why.process_stated`, `why.linear_model*`, `alt.model7`, `alt.model14`, `hyp.draft.h1.process`, `hyp.draft.h0.process`), plus 27 labels.
- The interpretation profiles, with LV/RU, in `interpretation_wizard` and `interpretation_i18n`.
- **LV/RU are drafts and need a native methodologist's review.**
- The linear model's report is English, like the regression engine's.

**Wording.**

- No causal verb in any language. EN, LV and RU outputs are scanned (`TextTests.test_no_causal_wording_and_no_mediation_labels_in_any_language`).
- "Effect" is used only as the conventional name of a model quantity, and every result says so.
- **Review S5 guard:** when an indirect effect has the opposite sign to c′ or c, the text says *inconsistent mediation (suppression; MacKinnon, Krull & Lockwood, 2000)*. Models 7 and 14 get the same note at the W values where the sign differs. No text uses "partial", "full" or "complete" mediation in any language.

**Figures** (`process_charts.py`):

- Model 1: simple slopes at mean ± 1 SD, and the conditional effect of X across W with its 95% band and the Johnson–Neyman values.
- Model 4: a path diagram and the bootstrap intervals of the indirect effects.
- Models 7 and 14: simple slopes of the moderated path, the index and the conditional indirect effects.
- Every model: the residual Q–Q panel and the residuals-vs-leverage panel.

**Reports and storage.**

- The runs reach the 15-section report: tests, effects with bootstrap intervals, assumption checks, figures and the appendix with the options.
- They reach the Word report.
- The structured result is stored with the run (`result_store` stores any result that has `structured()`) and comes back after a restart with its intervals.

**Data keys.** `goal-process`, `role-x`, `role-y`, `role-w`, `role-mediators-<name>`, `role-covariates-<name>`, `alt-conditional_process-7`, `alt-conditional_process-14`, `design-confirm-<key>`, `guided-choose-option`, `form-choose-option`.

**Question types.** The plan's question types gain `process` (`research_workflow.QUESTION_TYPES`, `project_store.QUESTION_TYPES`, both equal to `GOALS`). It has drafted H1/H0 texts.

## 4. Validation evidence

**Tolerances.**

- EXACT = 1e-9 relative (absolute 1e-12): the same estimator by independent code.
- BOOT = 1e-10 relative to the scale of the draws.
- Monte Carlo tolerances are stated per test.

"Observed" is the largest difference measured on the test data.

| Quantity | Independent oracle | Tolerance | Observed | Test |
|---|---|---|---|---|
| Every coefficient, SE, p, CI, R², adj. R², F, df of every equation (Models 4 simple/parallel, 1, 1 centred+HC3, 7 one/two mediators, 14 HC3/two centred) | statsmodels **formula** fits (patsy design, a different path from the engine's arrays) | 1e-9 (p 1e-7) | b 0, SE 2.6e-16 | `test_process_models.EquationOracleTests` |
| The same, OLS and HC3 covariance | numpy closed form (X′X)⁻¹X′y, σ²(X′X)⁻¹, (X′X)⁻¹X′diag(e²/(1−h)²)X(X′X)⁻¹ | 1e-9 / 1e-8 | — | same |
| Leverage, Cook's D, counts > 4/N and > 2p/N; Breusch–Pagan; Shapiro–Wilk; VIF | closed forms; auxiliary regression nR²; `scipy.stats.shapiro`; `variance_inflation_factor` | 1e-8 … 1e-6 | — | same |
| Simple mediation a, b, c′, c, ab | correlations: a = r_xm·s_m/s_x; b and c′ from the two-predictor formulas | 1e-9 | — | `ClosedFormTests` |
| c = c′ + Σaⱼbⱼ (with covariates) | identity | 1e-10 | — | `ClosedFormTests` |
| Conditional effects θ(w) and SE (OLS and HC3) | the slope of X after refitting with W − w | 1e-9 | — | `ClosedFormTests` |
| ΔR², F = t², p, f², HC3 F = t²_HC3 | separate full/reduced fits, `anova_lm` | 1e-9 | — | `ClosedFormTests` |
| Centring invariance (conditional effects, indirect effects and their bootstrap limits, products) | uncentred fit | 1e-8 / 1e-7 | — | `ClosedFormTests` |
| Index and conditional indirect effects (7, 14) | products of separately fitted coefficients | 1e-9 | — | `ClosedFormTests` |
| Conditioning values (mean ± SD, P16/50/84 type 7) | written-out formulas | 1e-9 | — | `ClosedFormTests` |
| **Johnson–Neyman** values (OLS and HC3) | scipy `brentq` on \|t\|−t_crit from statsmodels `t_test` contrasts, after a 2001-point scan; p = .05 at each root | 1e-8 | — | `JohnsonNeymanTests` |
| **Bootstrap** draws and percentile limits (Models 4 parallel+covariates, 7, 7-two, 14, 14-two-centred) | numpy-only re-implementation: its own design matrices, QR solves, type-7 percentile, **the same resample indices** | BOOT | draws 4.0e-14, limits 4.0e-15 | `BootstrapOracleTests` |
| Resample indices | `default_rng(seed).integers(0, n, (B, n))` | exact | exact | same |
| Single resamples | statsmodels on the resampled rows | 1e-9 | — | same |
| Singular resamples left out and counted | count of resamples where the rare covariate varies | exact | exact | same |
| Missing-data comparison | pandas means/SD of the masked rows | 1e-9 | — | `MissingDataTests` |
| Sensitivity simulation, Model 1 | type I error at 0 (2000 replications); **noncentral-t power** of the product at the analysis design | 3 MC SE (+.005 / +.02) | — | `SensitivitySimulationTests` |
| Structured result | JSON round trip, `result_store` | exact | exact | `StructuredResultTests` |
| Generator sign pattern (a > 0, b > 0, c′ < 0, XW > 0 in Y and in M) | signs only: **the latent coefficients are not sample estimates** | sign | — | `FixtureSignTests` |
| **R cross-check** (optional): Model 4 paths and SEs, Model 1 b3 and θ(+1 SD) with SE; bootstrap limits with `lm.fit` on the same indices and `quantile(type = 7)`; lavaan path model and the defined a·b | base R 4.3.3, lavaan 0.6-17 | 1e-8; lavaan 1e-5 | ~1e-16; lavaan ~1e-15 | `test_process_models_r` (skipped without R) |
| Linear model: every b, SE, p, R², F with first/last/most-frequent/named references; HC3 and the block Wald F; products with centring; block F/ΔR²/f²; β; VIF, Cook's D, leverage, Shapiro, BP | statsmodels formula with `C(var, Treatment(reference))`, `anova_lm`, `f_test`, numpy sandwich, z-score regression | 1e-9 | — | `test_linear_model` |
| **Reviewer's values** on the fixture, n = 175 (secondary). Model 4: a .0195, b 3.6799, c′ −.4800, c −.4084, ab .0716. Model 1 centred: b3 .2139; slopes −.6446/−.4351/−.2257; JN centred .860. Linear model: R² .1708, b_X −.4443, b_M 3.4586, b_W 3.4881 | independent reviewer's NumPy run | 4 decimals (JN 3) | agree | `test_linear_model.ReviewerReferenceTests`, `test_stage37_master_acceptance` |

**What is not independently validated.**

- The PROCESS macro itself. No PROCESS output was available, and none is claimed.
- The percentile bootstrap against another program's random numbers: Monte Carlo error makes such comparisons approximate. The R check uses the same indices instead.
- The sensitivity simulation for Models 4, 7 and 14. Its detection rule (a Monte Carlo interval of a product of normal draws) is tested for reproducibility and monotonicity only.

## 5. Independent review items (Fable narrow review of `2f9af71`)

| Item | Status | Proved by |
|---|---|---|
| S1: no engine for mediation and moderation | done | §1–§4 |
| S2: the moderator cut into groups | done: a continuous X × W with simple slopes and Johnson–Neyman | `JohnsonNeymanTests`, acceptance H5/H6 |
| S3: no 0/1 or categorical covariate in one model with X | done: the linear model with dummy codes and a stated reference | `test_linear_model`, acceptance H1 |
| S4: mediators chosen by p-values | done: never suggested; a design confirmation | `GuidedAdviceTests`, `CatalogTests` |
| S5: the fixture's suppression | done: the "inconsistent mediation (suppression)" guard; no "partial mediation"; no causal verb in EN/LV/RU | `TextTests` |
| S6: fixture limits | done: the tests assert numbers against oracles, never significance; a separate fixture v2 (`generate_master_fixture_v2.py`; v1 unchanged) adds consistent mediation, a dimension tied negatively to Y, covariate effects, reverse-keyed items with a stated key and value-dependent missingness | acceptance; `test_stage37_fixture_v2` |
| S10: Spearman permutation floor | done: the default is unchanged, the floor is stated (p = .001; Holm/Bonferroni k × .001) and the t-approximation option is named | `test_spearman_floor` |
| S12: no missingness summary or sensitivity re-run | done for the new models (summary, left-out comparison, `compare_estimates`) | `MissingDataTests`, acceptance |
| S13: ω for more than 12 items | **not done**: ω stays validated for 3–12 items; a 13- or 20-item scale gets α and "not calculated" for ω | acceptance |

**S10 in detail.** For n ≤ 500, Spearman's p is a two-sided permutation estimate with 1,999 resamples and a fixed seed. Its smallest value is 2/2000 = .001, and Holm over k tests cannot go below k × .001. The program now says so wherever the floor is reached. The t approximation with n − 2 df (the SPSS convention) has no floor. It is the existing option *Spearman p-value* of *Correlations: one variable with several*. The single-pair method has no such option, and its warning names the batch method.

## 6. Limitations

- **Causality.** Cross-sectional data cannot establish temporal order or causal mediation. Every mediation result says so, and the researcher confirms it before a run.
- **Missing data.** Listwise deletion only: no multiple imputation, FIML or MCAR test. The left-out comparison is descriptive.
- **Model scope.** Models 1, 4, 7 and 14 only, with up to 4 parallel mediators and 8 covariates.
  - No serial mediation (Model 6), no multicategorical X or W (dummy-code a 0/1 W instead), no binary Y (logistic paths) and no latent variables or SEM.
  - Johnson–Neyman is given for Model 1 only.
  - The bootstrap is percentile only: no bias-corrected interval.
- **Conditioning values.** The percentiles are type 7. PROCESS may define percentiles differently, so values at P16/P50/P84 can differ slightly from a PROCESS output with tied data.
- **Sensitivity simulation.** It anchors the non-focal coefficients at the sample estimates. Within each replication, the indirect effects use the Monte Carlo interval rather than a bootstrap, for speed.
- **ω.** Not for more than 12 items (S13). No CFA. EFA/PCA stays at 12 items.
- **Language.** The LV/RU texts are drafts. The linear model's report is English. As before, the report body of a run stays in the language it was calculated in (review U9).
- **Synthetic data only.** The fixture cannot show consistent mediation, a negative coping dimension or covariate effects (S6).

## 7. Done / not done

| Item | Status | Proved by |
|---|---|---|
| Model 4, simple and parallel, with covariates; a, b, c, c′, each and total indirect effect; percentile bootstrap, B = 5000, fixed seed, both reported; optional HC3 | done | `test_process_models`, `test_process_workspace`, acceptance H4 |
| Model 1 with optional centring; simple slopes at mean ± 1 SD and P16/50/84 | done | `ClosedFormTests`, acceptance H5/H6 |
| Johnson–Neyman, validated against an independent computation | done | `JohnsonNeymanTests`, reviewer's value |
| Models 7 and 14: conditional indirect effects, index of moderated mediation with its bootstrap CI | done | `ClosedFormTests`, `BootstrapOracleTests`, acceptance H7/H8 |
| No automatic choice of the model, the moderated path or a mediator; the choice is recorded | done | `CatalogTests`, `GuidedAdviceTests`, `GuidedFlowTests` |
| R², ΔR², f², standardized coefficients | done | `EquationOracleTests`, `ClosedFormTests` |
| Residual normality and Q–Q, Breusch–Pagan, Cook's distance, leverage | done | `EquationOracleTests` |
| Listwise policy with a missingness summary; sensitivity comparison | done | `MissingDataTests`, acceptance |
| Monte Carlo power/sensitivity simulation, clearly labelled | done | `SensitivitySimulationTests`, acceptance H7 |
| Workspace methods, roles X, M (1+), Y, W, covariates; the design and data confirmations | done | `CatalogTests` |
| Tables and texts in EN/LV/RU (LV/RU drafts); the methods text | done | `TextTests`, `test_locale_audit` |
| Simple-slopes chart | done | the figures are drawn in every run (`test_process_workspace`) |
| Report integration (plan, Word, storage) | done | `ReportTests` |
| No causal wording; no mediator screening by p-values | done | `TextTests`, `GuidedAdviceTests` |
| Oracles: statsmodels per path, numpy bootstrap on the same indices, closed forms, generator signs, optional R | done | §4 |
| H1–H6 acceptance with Models 7 and 14, the public mapping file, links to the plan, a reproducible report | done | `test_stage37_master_acceptance` |
| Linear model with dummy-coded covariates (review S3) | done | `test_linear_model` |
| Suppression wording guard (review S5) | done | `TextTests` |
| Spearman floor visible (review S10) | done | `test_spearman_floor` |
| ω for more than 12 items (review S13) | not done | limitation |
| Fixture v2 (consistent mediation, negative dimension, covariate effects, reverse items, patterned missingness), separate from the owner's v1 | done | `test_stage37_fixture_v2` (7 tests) |
| Windows GUI journey for the new methods; native LV/RU review | not done | owner / 37.x |
