# Stage 37 — synthetic master's acceptance scenario (H1–H6)

> **SYNTHETIC.** Every number on this page comes from the invented fixture of `tests/fixtures/stage37/generate_master_fixture.py` (180 fictional cases). The constructs are fictional labels, not the UCLA, SACS, WHO-5 or MSPSS instruments, and use no validated scoring keys. Nothing here is an empirical finding about loneliness, coping, support or well-being. The owner's real study has a plan and instruments, not participant responses (spec §7).

Issue #66. Test: `tests/test_stage37_master_acceptance.py` (12 tests). Mapping: `tests/fixtures/stage37/synthetic_construct_mapping.json`. Methods and validation: [`STAGE37_METHODS.md`](STAGE37_METHODS.md).

## 1. What the scenario does

The test runs the scenario headless, the way a researcher would run it in the workspace:

1. **Fixture.** It generates the fixture with the owner's v1 generator, unchanged.
2. **Constructs.** It reads X, M, W and Y from the generator's spec JSON (`SYN_LON_TOTAL`, `SYN_COPE_DIM1_MEAN`, `SYN_SUP_MEAN`, `SYN_WELL_0_100`) and scores the two further coping dimensions from the mapping file.
3. **Project and plan.** It creates a project titled *SYNTHETIC — Stage 37 master's acceptance (invented data)* and saves a typed plan with three questions and the hypotheses H1–H8. H7 and H8 are exploratory. Every hypothesis states its question type, its intended method (with the model option for 7 and 14) and its planned variables by role.
4. **Analyses.** Every analysis runs through `workspace_methods.run_method` with the researcher's confirmations. Each one tests its hypothesis through a task created with `hypothesis_id` (37.0a API); `record_run(..., hypothesis=snapshot)` keeps the hypothesis snapshot; a `link` protocol record names the task and the run.
5. **Labels.** Every run carries the note *[SYNTHETIC] Output of the invented Stage 37 fixture; not an empirical finding.* Every hypothesis starts with *[SYNTHETIC]*.
6. **Report.** It builds the 15-section research report and the Word document, and reads the document back with `python-docx`.
7. **Reproducibility.** It runs the whole scenario a second time in a new folder. The report plan and the SHA-256 of every run report must be identical. Only the calculation times and the run ids differ.

Set `SRA_ACCEPTANCE_OUT=<folder>` to keep the Word report and a text summary.

## 2. The synthetic mapping

| Role | Column | Items | Score |
|---|---|---|---|
| X, loneliness-like | `SYN_LON_TOTAL` | `SYN_LON_01..20` | sum |
| M, coping-like (generator group 0) | `SYN_COPE_DIM1_MEAN` | `SYN_COPE_01..07` | mean |
| W, support-like | `SYN_SUP_MEAN` | `SYN_SUP_01..12` | mean |
| Y, well-being-like | `SYN_WELL_0_100` | `SYN_WELL_01..05` | sum × 4 |
| avoidance-like (groups 2 and 5) | `SYN_COPE_AVOID_LIKE` | `SYN_COPE_15..21`, `SYN_COPE_35..40` | mean |
| assertive-like (groups 3 and 6) | `SYN_COPE_ASSERT_LIKE` | `SYN_COPE_22..28`, `SYN_COPE_41..46` | mean |

In the generator, each coping group's latent factor is `N(0, 0.9) + ((g mod 3) − 1)·0.15·x`. Groups 2 and 5 therefore carry +0.15·x, groups 3 and 6 carry −0.15·x, and group 0 is M itself.

The covariates are:

- age (quantitative);
- sex (nominal 0/1/2). The linear model dummy-codes it against category 0. The path models use the derived 0/1 columns `SYN_SEX_1` and `SYN_SEX_2`.
- employment (0/1).

## 3. Hypotheses and analyses

| H | Synthetic hypothesis | Analysis (method key) |
|---|---|---|
| H1 | X is associated with Y, alone and with age, sex and employment in the model | Pearson correlation (`correlation`); linear model Y ~ X + age + C(sex) + C(employed) (`linear_model`) |
| H2 | X with the avoidance-like and assertive-like dimensions | `batch_correlation`, Pearson, Holm |
| H3 | the coping dimensions with Y | `batch_correlation`, Pearson, Holm: Y with M, avoidance-like, assertive-like |
| H4 | X → Y through M and the avoidance-like dimension, with covariates | `mediation`, PROCESS-equivalent Model 4, parallel mediators, B = 5000, seed 37066 |
| H5 | X × W → Y | `moderation`, Model 1, simple slopes, Johnson–Neyman |
| H6 | X × W → the avoidance-like dimension | `moderation`, Model 1 |
| H7 (exploratory) | W moderates X → M | `conditional_process`, **Model 7 chosen explicitly**, Monte Carlo sensitivity simulation (500 replications) |
| H8 (exploratory) | W moderates M → Y | `conditional_process`, **Model 14 chosen explicitly** |

**Model 7 vs Model 14.** They are two separate analyses, and each records its own design confirmation.

- *I chose Model 7 (W moderates X → M) from theory, before seeing results.* In Model 7, W multiplies X in the M equation: the index of moderated mediation is a3·b.
- *I chose Model 14 (W moderates M → Y) from theory, before seeing results.* In Model 14, W multiplies M in the Y equation: the index is a·b3.

H6 (X × W → avoidance-like) is a moderation of another outcome. It is neither model.

**Supporting analyses.**

- Item diagnostics (Cronbach's α, ω where validated, every item) for all six scales.
- Descriptives of the six scores.
- Residual diagnostics, VIF and missing-data tables inside each model.
- The missing-data sensitivity re-runs of H4 and H5 with prorated scores.

## 4. What the test asserts

The test asserts numbers against independent oracles, never significance (review S6).

- **Scores.** They equal numpy means of the mapped items. The fixture's own sums, means and ×4 scores agree with its items. The mapped item lists equal the generator's group boundaries (7, 7, 7, 7, 6, 6, 6, 6 items).
- **Reliability.** α of each scale equals the closed form k/(k−1)·(1 − Σs²ᵢ/s²ₜ) to 1e-9. The reviewer's values .914, .903, .812 and .802 (X, W, Y, M) hold to three decimals. ω is "not calculated" for the 13- and 20-item scales: the validated ω takes 3–12 items (S13).
- **H1.** r equals `np.corrcoef`. The linear model equals a statsmodels formula with `C()` coding (R², every b). VIF equals `variance_inflation_factor`. The reference categories are stated: sex 0, employed 0.
- **H2, H3.** Each r equals `np.corrcoef` on the complete pairs. Holm equals `multipletests`.
- **H4.**
  - a₁, a₂, b, c′ and c equal separate statsmodels fits.
  - c = c′ + Σaⱼbⱼ to 1e-10.
  - B = 5000 and seed 37066, with 5000 valid resamples, are in the run's inputs. The SHA-256 of the resample indices is stored with the run.
  - The wording guard applies (§5).
- **H5, H6.** b3 equals statsmodels. Every simple slope and its SE equal a statsmodels `t_test` contrast. p = .05 at every Johnson–Neyman value.
- **H7, H8.** The index equals a3·b (Model 7) and a·b3 (Model 14) from separate statsmodels fits. The model option and the model's own confirmation are recorded. The sensitivity table has 500 replications and says that it is not "observed power".
- **Missing data.**
  - Listwise n per analysis: H4 177, H5 and H6 178, H7 and H8 175. The prorated re-runs have 180.
  - A missing-data table is in every model.
  - `compare_estimates` lists every shared estimate with its difference.
  - H1–H3 use complete scores, so no comparison is needed there.
- **Links.**
  - Every linked run's snapshot names its hypothesis and the plan version.
  - Each task carries its `hypothesis_id`.
  - Nine `link` records name their run (H1 has two analyses).
- **Report.** The Word report contains H1–H8, the PROCESS-equivalent titles, the methods sentence "not by the PROCESS macro", the synthetic note and more than 20 tables. Each stored run report equals the computed one.
- **Reproducibility.** A second full run gives the same report plan and the same run reports.
- **Reviewer's values (secondary).** These are on the listwise n = 175, without covariates:
  - Model 4: a = 0.0195, b = 3.6799, c′ = −0.4800, c = −0.4084, ab = 0.0716.
  - Model 1, centred: b3 = 0.2139; slopes −0.6446, −0.4351 and −0.2257 at W −1 SD, mean and +1 SD; Johnson–Neyman at centred W = 0.860.
  - Linear model Y ~ X + M + W + age + C(sex) + C(employed): R² = .1708.

  All agree to 4 decimals (Johnson–Neyman to 3).

## 5. Synthetic output (for orientation only)

These values come from one run of the scenario (fixture v1, generator seed 37012026; bootstrap seed 37066). They are synthetic and are not findings.

| Analysis | n | Synthetic result |
|---|---|---|
| α: X, M, W, Y, avoidance-like, assertive-like | 180 / 177 / 178 / 180 / 180 / 180 | .914, .802, .903, .812, .691, .733 |
| H1 r(X, Y) | 180 | −.284 |
| H1 linear model | 180 | R² = .117; b_X = −0.396, 95% CI [−0.609, −0.183] |
| H2 r with avoidance-like, assertive-like | 180 | .106 (Holm p = .156), −.187 (Holm p = .024) |
| H3 r of Y with M, avoidance-like, assertive-like | 177 / 180 / 180 | .072, .047, .142 |
| H4 indirect via M; via avoidance-like; total | 177 | 0.066 [−0.005, 0.152]; 0.013 [−0.022, 0.048]; 0.079 [0.001, 0.165]; c′ = −0.480, c = −0.402 |
| H4, prorated scores | 180 | via M 0.074 [0.002, 0.165] |
| H5 X × W → Y | 178 | b3 = 0.220 [0.015, 0.425], ΔR² = .022; slopes −0.621, −0.405, −0.190; Johnson–Neyman W = 4.593 |
| H6 X × W → avoidance-like | 178 | b3 = −0.0004 [−0.007, 0.006]; no Johnson–Neyman value in range |
| H7 Model 7 index | 175 | 0.017 [−0.024, 0.076] |
| H8 Model 14 index | 175 | −0.040 [−0.106, 0.032] |

Two things the synthetic output shows about the program, not about any population:

- **H4 is inconsistent mediation (suppression).** Each indirect effect is positive while c′ and c are negative. The interpretation says *inconsistent mediation (suppression; MacKinnon, Krull & Lockwood, 2000)*. It never says "partial" or "full" mediation (review S5).
- **The missing-data decision can move an interval across zero.** The interval of the indirect effect via M includes zero with listwise deletion (n = 177) and excludes it with prorated scores (n = 180). This is why the comparison is part of the scenario. The program reports both and decides nothing.

## 6. Fixture limits (review S6)

- Only DIM1 is tied to Y.
- No dimension is tied negatively to Y.
- The a-path interaction is weak.
- There are no reverse-keyed items, and the covariates have no effect.
- 5 cells are missing.

The acceptance therefore checks computation, provenance and wording, not the power of the design. A separate fixture v2 (`tests/fixtures/stage37/generate_master_fixture_v2.py`, 240 cases) adds consistent mediation, a dimension tied negatively to Y, covariate effects, reverse-keyed items with a stated scoring key and missingness that depends on age and employment. `tests/test_stage37_fixture_v2.py` shows what the program does with it: no suppression note when a·b and c′ share their sign, exactly the reverse-keyed items flagged, and the left-out cases younger. The owner's v1 generator is unchanged.
