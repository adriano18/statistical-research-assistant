# Stage 37 — Fable 5.2 independent narrow review

> **Provenance.** Independent, read-only review by Claude Fable 5.2 at high effort, on a fixed snapshot (`2f9af71`: PR #71 on #65 on #64), commissioned for Issue #70. The reviewer was given the code, the packaged-program screenshots of two Windows runs and the synthetic scenario only; no private thesis, instrument or participant documents, and no conclusions of the developer. It made no edits. The text below is the reviewer's report as delivered; local scratch paths were shortened to repository-relative paths. Interaction counts in §2.2 are analytic estimates (the reviewer did not run the harness) and are labelled so. Follow-up work starts with reproducible red tests (Issue #70).

Reviewer: Fable 5.2 (read-only). Reviewed checkout: a read-only checkout, detached at `2f9af71` (PR #71 on #65 on #64). Every `file:line` below is relative to that root. `git status --short` was empty before and after the review.

## 1. Method and evidence base

**Read (code).** `app.py`, `app_preferences.py`, `app_paths.py`, `research_app.py` (start-up, bridge), `workspace_shell.py`, `workspace_tokens.py`, `workspace_components.py`, `workspace_methods.py`, `workspace_analyze.py`, `workspace_plan.py`, `workspace_hypotheses.py`, `workspace_state.py`, `research_workflow.py`, `project_store.py`, `project_session.py`, `regression_analysis.py`, `batch_correlation.py`, `correlation.py`, `reliability.py`, `item_diagnostics.py` (parts), `data_preparation.py`, `preparation_ui.py`, `data_loader.py`, `survey_storage.py` (export), `import_session.py`, `scientific_survey_import.py` (scoring parts), `research_report.py`, `report_docx.py`, `interpretation_docx.py` (style), `chart_studio.py` (model), `ai_providers.py`, `ai_context.py`, `ai_assist.py`, `secret_store.py`, `tests/workspace_harness.py`, `docs/stage37/measure_baseline.py`, `tools/workspace_scenarios.py`, `tests/test_stage36_ux_baseline.py`, `tests/test_stage37_ui.py` (parts), the fixture generator.

**Read (documents, treated as claims).** `docs/STAGE37_NEXT_SPEC.md`, `STAGE37_0A_STATUS.md`, `STAGE37_DESIGN.md` (structure, §12, Appendix A), `STAGE368_A11Y_AND_LOCALE.md`, `STAGE368_LOCALE_REVIEW.md` §6, `BUNDLED_OCR.md`, `packaging/windows_ocr_runtime.lock.json`.

**Windows evidence.** Both `gui-e2e-result.json` files (18 journeys each, all `ok`). I opened 9 of the 278 PNGs, all from `screenshots-37a-519b1ec`: `004-nav-home`, `009-confirm-the-measurement-levels`, `010/011-…eight-correlations…`, `028-title-typed-in-appearance`, `052-choose-outcome-group-and-covariate`, `111-both-datasets-stay-in-the-project`, `159/160-…alpha-and-omega`, `248-the-word-report…`. The other files were used by name only. I ran no Windows program.

**Limits of the Windows evidence.**
- Both sets hold the same 18 journeys. Neither has a journey for the 37.0a hypothesis workspace, for Settings, for keyboard-only use or for Narrator.
- All journeys start with `SRA_UI=workspace` (`tools/windows_gui_e2e.py:232`), so the real first start is not in any screenshot.

**Ran.** Python 3.12 from `venv-lock`, with `PYTHONDONTWRITEBYTECODE=1`, `SRA_DATA_DIR=/tmp/fable-review/data`, `MPLBACKEND=Agg`, `-B`, scripts on stdin, synthetic CSV only. Nothing was written to disk; matplotlib and pingouin were never imported.
- App engines in memory: `data_loader.load_dataset_with_report`, `workspace_state.build_dictionary`, `regression_analysis.analyze_regression`, `batch_correlation.correlate_many`, `item_diagnostics.item_response_problems`.
- Independent references (statsmodels, SciPy, NumPy): Pearson r, Cronbach's α, Model 4 with 5,000 percentile bootstrap resamples, moderation with simple slopes and Johnson–Neyman, a-path moderation, full covariate model, the tercile workaround.
- An in-memory SQLite FTS5 probe.

**Not run: the Linux harness.** This review session was held to a stricter rule than the brief: no file creation anywhere, including `/tmp`. `tests/workspace_harness.py:46` creates a `TemporaryDirectory` with project stores, so I did not execute it. Interaction counts in §2.2 are derived by tracing the handlers and applying the repository's counting rule. They are estimates and are labelled as such. The private folders were not opened.

## 2. Measured baseline

**Counting rule** (`tests/test_stage36_ux_baseline.py:31-56`, `docs/stage37/measure_baseline.py:48-104`): a click or a checkbox is 1, a dropdown is 2. Typed fields, page changes and system dialogs are counted apart. Scrolling is not counted.

### 2.1 Recorded by the repository (script read, not re-run)

| Flow (13-variable totals-only fixture) | Interactions | Typed | Page changes | Dialogs | Source |
|---|---:|---:|---:|---:|---|
| Beginner, before 37.0a | 22 | 10 | 5 | 2 | `STAGE37_DESIGN.md` App. A |
| Professor, before 37.0a | 14 | 0 | 6 | 0 | same |
| Scale quality, 10 items, one scale in the file | 5 | 0 | 2 | 0 | same |
| 37.0a flows | not measured | | | | `STAGE37_0A_STATUS.md` AC-10 "partly" |

That fixture hides the cost that dominates a master's study: it has 13 columns and no items.

### 2.2 Master's scenario at `2f9af71` (98 columns), analytic count

**Assumptions.**
- One question and one hypothesis per H1–H6.
- The four scores in the file are used; seven coping dimensions are scored in the program.
- Reliability is checked for 11 scales (20, 12, 5, 7, 7, 7, 7, 6, 6, 6, 6 items).
- Descriptives for 12 variables.
- 3 review ticks per result (the batch-correlation value; assumed for other methods).
- Interpretation notes skipped.

| Segment (novice) | Interactions | Typed | Page changes | Basis |
|---|---:|---:|---:|---|
| First start: classic interface, *Open the preview* | 1 | 0 | 1 | `research_app.py:3052-3061`, `interface_layout.py:152` |
| Create project | 1 | 1 | 1 | `workspace_projects.py:271-287` |
| Plan: 6 × (add question 1, kind 2, add hypothesis 1), H1 direction 2, save 1 | 27 | 12 | 0 | `workspace_plan.py:153-242` |
| Data: open (+ dialog), tick, accept, correct `sex_code` | 5 | 0 | 1 | `workspace_shell.py:1068-1135` |
| Scores for 7 dimensions: open 1, kind 2, 45 item ticks, 7 Apply, use copy 1, accept levels 2 | 58 | 7 | 0 | `preparation_ui.py:104-166` |
| Reliability, 11 scales: 89 item ticks, plus goal, confirmation, Run and navigation per scale | 143 | 0 | 22 | `workspace_analyze.py:292-316`, `:875-880` |
| Descriptives, 12 variables, one at a time | 50–72 | 0 | 24 | `workspace_methods.py:226-229` |
| H1–H3: create, variables, confirmation, Run, acknowledge direction, review, skip note, add to report | 56 | 1 | ≈ 13 | `workspace_hypotheses.py:163-199` |
| H4–H6: nearest available analyses only (regression; tercile groups with group × covariate) | 57 | 0 | ≈ 15 | §3.2 S1–S3 |
| Report: open, title, export (+ dialog) | 4 | 1 | 1 | `workspace_analyze.py:1858` |
| **Total** | **≈ 400–425** | **≈ 22** | **≈ 80** | 2 system dialogs |

Of these, **134 are single item ticks**: 89 for reliability and 45 for scoring, for the same item sets. H4–H6 end without the planned test.

**Scroll.** The dictionary has one 56-px row per variable and the bulk-accept controls sit below it (`workspace_shell.py:1100`, `:1119`; seen in `009-confirm-the-measurement-levels.png`). For 98 variables that is about 5,500 px.

**Professor, reviewing that finished project after a restart: ≈ 40 interactions, ≈ 19 page changes.**
- Open the project (1).
- Six hypothesis toggles (6).
- Open each analysis and return (≈ 20). Results of non-batch methods are not shown in the task (`workspace_analyze.py:617-621`), so they are found in Results by title.
- Eleven reliability results in a flat log of about 36 entries (12) (`workspace_analyze.py:1181-1203`).
- Report preview (2).

## 3. Findings

Classes: **D** verified defect, **S** scientific risk, **U** usability, **M** missing feature, **H** hypothesis (not verified). Sections 3.1–3.4 are confirmed in code, by an in-memory run or in a named screenshot. Section 3.5 holds ideas and unverified points only.

### 3.1 Verified defects

| ID | Finding | Evidence |
|---|---|---|
| D1 | A language chosen in the workspace is not saved unless a researcher profile already holds a language. `ClassicBridge.store_language` is never passed, so `preferences.json` keeps the old value. Language lives in three places (preferences, profile, session). | `workspace_shell.py:785-802`; `research_app.py:2838-2847`; `workspace_shell.py:149-150` |
| D2 | Theme and window size are not kept. Only the accent is written, and the window is set to 1200 × 720 at every start. | `workspace_shell.py:778-783`, `:816`; `app.py:174-175` |
| D3 | `H-DIR-SIGN` can never appear for a single correlation. The check covers `correlation`, but estimates are extracted only for `batch_correlation`. H1 (one X–Y pair, direction "less") gets no note when r is positive. | `research_workflow.py:49`, `:753` |
| D4 | Only the first task of a hypothesis drives its steps, latest result and next action. A second analysis is ignored by the next-action bar. | `research_workflow.py:910`, `:913`, `:954` |
| D5 | Changing variables inside a task overwrites the task's selection, method and options in place, and its title stays that of the first run. The Word report then prints that stale title as the heading of all its results. | `workspace_analyze.py:582-611`; `research_report.py:340-356` |
| D6 | The hosted *Prepare data* panel is English only and uses caption colour `#A8B6C9`, which is 2.06:1 on white (my calculation with the repository's own formula). | `preparation_ui.py:216`; `STAGE368_LOCALE_REVIEW.md` §6 |
| D7 | Role pickers list variables that cannot be used: the grouping variable and the outcome itself are offered as covariates. | `052-choose-outcome-group-and-covariate.png`; `workspace_analyze.py:292-316` |
| D8 | CSV exports write text cells unescaped and comma-separated. A text answer that starts with `=`, `+`, `-` or `@` becomes a formula in Excel. | `survey_storage.py:574`; `data_preparation.py:240` |
| D9 | Word output: page size is fixed to US Letter, and *Heading 3* (used for every result title) is not styled, while Title and Headings 1–2 are. | `interpretation_docx.py:34-35`, `:48`; `report_docx.py` (`level=3`) |
| D10 | Number formats differ within one result: table "[-0.50, 0.07]" against sentence "[-.50, .07]"; summary "α = 0.57" against table ".72"; two rows shown as "-.10" carry different magnitude labels. | `011-…spearman-run.png`; `160-alpha-and-omega.png` |
| D11 | The Reports page mixes languages and has a plural error: "2. Pētījuma jautājums · 1 parts". | `248-the-word-report….png` |
| D12 | `protocol_records.run_id` is never written; the interface passes only hypothesis, task and fingerprint. | `workspace_hypotheses.py:460-463` |

### 3.2 Scientific risks

| ID | Finding | Evidence |
|---|---|---|
| S1 | No engine for mediation, bootstrap indirect effects, continuous moderation, simple slopes, Johnson–Neyman or Models 4/7/14. H4–H6 cannot be tested. Nothing is auto-selected, because nothing exists. | grep over all `*.py`; method list `workspace_methods.py:222-447` |
| S2 | The nearest workaround is scientifically poor: the moderator is cut into groups and a group × covariate model is run. On the fixture the continuous interaction gives b = 0.2139, p = .041, ΔR² = .021; the tercile version gives p = .198. | in-memory reference run, listwise n = 175 |
| S3 | Regression takes 1–5 quantitative predictors only. A 0/1 covariate is refused; a nominal code with three values is accepted if it was confirmed as quantitative. ANCOVA takes one factor and at most 3 covariates. Age, sex and employment cannot enter one model with X. | `regression_analysis.py:67`, `:99`; `workspace_methods.py:380`, `:401`, `:929-957`; run: "Each quantitative predictor needs meaningful variation." |
| S4 | Mediators must not be chosen by p-values. On the fixture r(M, Y) = +.072 (Holm p = 1.0), yet the reference indirect effect is ab = +0.0716, 95 % CI [0.0061, 0.1574]. A "significant correlates only" gate would drop this mediator. | app `correlate_many`, plus reference run |
| S5 | The fixture cannot show "partial mediation". a = +0.0195, b = +3.680, c = −0.408, c′ = −0.480: the indirect effect has the opposite sign to the total effect (suppression). Any text that calls this partial mediation is wrong. | reference run; `generate_master_fixture.py:30-31` |
| S6 | Other fixture limits: only DIM1 is tied to Y; no dimension is negatively tied to Y (H3); the a-path interaction is p = .24 (H6); no reverse-keyed items; 5 missing cells; covariates have no effect. Acceptance tests should assert numbers against an oracle, never significance. | generator `:38-63`; reference run |
| S7 | `sex_code` (0/1/2) is suggested as *ordinal*, and one tick plus one button confirms all 98 suggestions. | `workspace_state.py:57`; in-memory run: 90 ordinal, 6 scale, 1 nominal, 1 id |
| S8 | A hypothesis whose wording, direction or α is edited after results keeps the standing "confirmatory". Only a changed priority needs a reason. No check compares a result's snapshot with the current plan. | `project_store.py:1327`, `:1363-1385`; `research_workflow.py:52-55` |
| S9 | The plan's α is not used. `correlate_many` accepts `alpha`, but `run_batch_correlation` does not pass it, and sentences say "at α = .05". All tests are two-sided. `H-ALPHA` and `H-DIR-*` warn about this, by design. | `analysis_runs.py:581-583`; `batch_correlation.py:432-436` |
| S10 | The default Spearman p is a permutation estimate with 1,999 resamples, so the smallest p is .001. On the fixture ρ = −.297, n = 180 gives p = .001, where the t approximation is about 5 × 10⁻⁵ (hand calculation). Holm in a family of 40 cannot go below .04. | `correlation.py:108-117`; in-memory run |
| S11 | Scale scoring: the default "minimum answered items" is 3 for any scale length and is reset to 3 after every step. A 20-item mean can rest on 3 answers. | `preparation_ui.py:55-57`, `:114` |
| S12 | Missing data: listwise or pairwise deletion with counts. There is no missingness summary, no MCAR test, no imputation and no sensitivity re-run. | engines read; grep |
| S13 | Psychometrics: ω for 3–12 items only, so the 20-item scale gets α alone; EFA/PCA for at most 12 items and 5 factors, so the 52-item, 8-dimension structure cannot be examined; no CFA. Reverse keys reach the analysis only for datasets collected in the program. | `workspace_methods.py:245`, `:267`, `:976`, `:117-131` |
| S14 | Checks, acknowledgements and deviations are not in the Word report. A report can be exported with open warnings and shows no trace of them. | `research_report.py` (no protocol input); status file §1.4 |
| S15 | The audit trail is protected against the program's own interface, not against edits. The database is plain SQLite; triggers can be dropped; `.sra` hashes prove integrity, not authorship. Notes and review ticks are overwritten without history. | `project_store.py:302-331`, `:1755-1774` |
| S16 | "Added after results" counts every run in the project, including descriptives and reliability. A student who checks reliability first gets every hypothesis flagged post hoc. | `project_store.py:1326`, `:1378-1383` |
| S17 | The drafted H0 for a *predict* question is the omnibus null ("every coefficient is 0"), which does not match a hypothesis about one predictor. | `workspace_text.py:2809-2812` |

**What works and was checked.** App Pearson r equals SciPy to 4 decimals on 10 pairs (for example r(X, Y) = −.2840, n = 180). The regression engine reports CI, VIF, Breusch–Pagan, residual Shapiro–Wilk and Cook's D (Y on X, M, W, age: n = 175, R² = .147). Causal wording is careful in the texts I read (`regression_analysis.py:153`, `ai_assist.py:52`).

### 3.3 Usability (verified)

| ID | Finding | Evidence |
|---|---|---|
| U1 | The classic interface opens first; the workspace needs *Open the preview*. The workspace still shows the labels "Preview" and "Prototype". | `research_app.py:3052-3061`; `004-nav-home.png` |
| U2 | Item sets are picked one tick at a time among all variables. Quick selection works only by level or by copying another task. There is no search, prefix or range. | `workspace_analyze.py:341-376`; `preparation_ui.py:47`, `:111` (170-px list) |
| U3 | Descriptives take one variable per analysis. The correlation matrix takes at most 8 variables and gives no p-values. | `workspace_methods.py:226-229`, `:294-297` |
| U4 | Every non-batch run moves to Results. The next-action bar exists on the Project page only, so each hypothesis costs 4–5 page changes. | `workspace_analyze.py:875-880`; status file §2 |
| U5 | The Project page becomes very long. Each hypothesis has 8 text fields and 5 selectors in the plan card, and appears again in the hypotheses card. | `workspace_plan.py:46-48`, `:186-242`; `workspace_projects.py:476-477` |
| U6 | The Results log is flat: no hypothesis label, grouping or search, and time without date. | `workspace_analyze.py:1181-1203` |
| U7 | The inline figure is too small to read; *Enlarge figure* is needed. | `160-alpha-and-omega.png` |
| U8 | The Word report is ordered by kind of statistic. One hypothesis is spread over sections 9–13 and figures are collected in section 12. The engine report, the effects table and the interpretation repeat the same numbers. | `research_report.py:444-500` |
| U9 | Report language changes headings only. Engine text stays English, or stays in the interface language used at the run. | `analysis_runs.py:596`; `STAGE368_LOCALE_REVIEW.md` §6 |
| U10 | The research-question field is about 300 px wide in a 1,240-px card. | `111-both-datasets-stay-in-the-project.png` |
| U11 | No focus management: no `autofocus` or `.focus()` call in any `workspace_*.py`. After *Create the analysis* the page scrolls but focus does not move. | grep |
| U12 | The top bar shows EN, LV and RU. There is no text-size or density setting. The chart font defaults to DejaVu Sans and Segoe UI is not in the list. | `workspace_shell.py:737`; `workspace_tokens.py:44-51`; `chart_studio.py:160`; `workspace_charts.py:27`; `028-…png` |

### 3.4 Missing features (verified absent)

- **M1.** Data export to `.xlsx` and `.sav`, results as `.xlsx`, and `.sav` import (`data_loader.py:20`).
- **M2.** Variable labels, value labels and user-missing codes in the data model. `VariableInfo` has none (`workspace_state.py:27-36`); the `variables.label` column is unused.
- **M3.** Scoring keys from an imported questionnaire applied to data. Documented scoring groups are evidence only (`scientific_survey_import.py:2105`).
- **M4.** Roles X, M, Y, W in the plan. Plan roles are the guided goals' roles, and the role editor is not built (`project_store.py:604-622`; status file §2).
- **M5.** A local AI endpoint and any library or retrieval code (`ai_providers.py:48-55`; grep).
- **M6.** A copy for an older version (format 6 cannot be opened by the RC); a Windows journey for the hypothesis workspace; a native review of the 173 new LV/RU texts; a keyboard-only walk; a Narrator session. All are stated in the repository's own documents.
- **M7.** A LICENSE file.

### 3.5 Hypotheses and ideas (not verified)

- **H1.** A full page rebuild on every tick (`app.render()`), with about 100 checkboxes on screen, may be slow on Windows.
- **H2.** Excel under a Latvian or Russian locale opens a comma-separated CSV in one column.
- **H3.** Segoe UI is used only through Flutter's platform default. The screenshots look consistent with it, but nothing sets it.
- **H4.** The Windows "Make text bigger" setting may not reach the fixed pixel sizes.
- **H5.** Removing pingouin should shorten the first reliability run (`reliability.py:54-56` calls it the largest start-up cost).
- **H6.** Goal tiles and hypothesis rows may not be reachable by keyboard on Windows. The status file says this of hypothesis rows.

## 4. Top 10 prioritized improvements

Effort: S ≤ 2 days, M 3–7, L 8–18. "Gain" is against §2.2.

| # | Improvement | Impact | Effort | Risk | Gain in counted interactions |
|---|---|---|---|---|---|
| 1 | Replace pingouin's α with an own implementation; owner's licence decision; LICENSE and notices | Removes a release blocker | S, 1.5–2 d | Low | 0 |
| 2 | Scales register: define a scale once (items by search, prefix or range; reverse items; scoring rule), score all, check all | Largest UX gain; ends S11 | L, 9–12 d | Medium (format 7) | ≈ −150, −20 page changes |
| 3 | Linear model: categorical covariates with a stated reference category, product terms, standardized β | H1 with covariates; base for #4 | M, 5–7 d | Medium | Enables |
| 4 | Mediation, moderation, Johnson–Neyman, Models 4/7/14, chosen by the researcher | H4–H6 | L, 12–18 d | High | From impossible to ≈ 8 each |
| 5 | Descriptives for many variables; correlation matrix with CI and adjusted p | Tables 1 and 2 of a thesis | M, 4–6 d | Low | ≈ −45 to −65, −22 page changes |
| 6 | Finish the hypothesis workflow: next action on every page, every result stays in its task, role editor, all tasks tracked (D4) | Orientation | M, 5–7 d | Low | ≈ −18, −20 page changes |
| 7 | Audit hardening: S8, D3, D12, note history, hash chain | Trust of supervisors | M, 4–5 d | Low | 0 |
| 8 | Report by hypothesis, with checks and deviations, figures beside results, one language, A4 | Less editing in Word | M–L, 6–9 d | Medium | 0 in the program |
| 9 | Export: one button, `.xlsx`, `.sav`, CSV options, codebook, injection guard | Interoperability | L, 10–14 d | Medium (new binary dependency) | New: ≤ 3 + 1 dialog |
| 10 | Settings: workspace first, EN/LV switch with RU in Settings, one settings file, text size, density, window | Owner's stated wishes; D1, D2 | M, 5–7 d | Low | −1 and −1 page change per start |

**Acceptance tests and metrics.**

1. **pingouin.**
   - A unit test compares the new α and Feldt interval with pingouin as a test-only oracle to 1e-12 on three fixtures.
   - On the master fixture α = .914, .903, .812, .802 (LON, SUP, WELL, DIM1; my NumPy values).
   - Metric: `pingouin` absent from `requirements.txt` and the SBOM.
2. **Scales.**
   - Harness test on the master CSV: 11 scales defined, scored and checked in ≤ 50 interactions and ≤ 2 page changes.
   - Scores equal a NumPy oracle exactly; α equals it to 1e-9.
   - No default for "minimum answered"; a reverse key is applied only after its own confirmation.
   - Windows journey `stage37-scales` reads 11 α rows through UI Automation.
3. **Linear model.**
   - Oracle `Y ~ X + M + W + age + C(sex) + C(employed)`: n = 175, R² = .1708, b_X = −0.4443, b_M = 3.4586, b_W = 3.4881, to 1e-4.
   - A nominal variable can enter only as dummy codes.
4. **Mediation and moderation.** Oracle on listwise n = 175, to 4 decimals:
   - Model 4: a = 0.0195, b = 3.6799, c′ = −0.4800, c = −0.4084, ab = 0.0716; the bootstrap interval reproduces with its seed.
   - Moderation: b3 = 0.2139; slopes −0.6446, −0.4351, −0.2257 at −1 SD, mean, +1 SD; Johnson–Neyman boundary at centred W = 0.860.
   - `advise()` never returns Model 7 or 14.
   - With ab and c of opposite sign the text says "inconsistent (suppression)" and never "partial mediation"; a scan of EN/LV/RU output finds no causal verb.
5. **Descriptives and matrix.**
   - Harness: 12 variables described in ≤ 6 interactions and 1 page change.
   - Values equal pandas and SciPy.
6. **Workflow.**
   - `STAGE37_DESIGN.md` AC-10: beginner ≤ 20 interactions, ≤ 5 typed, ≤ 4 page changes; professor ≤ 6 and ≤ 2.
   - Master scenario: ≤ 1 page change per hypothesis.
   - Windows journey `stage37-hypothesis`.
7. **Audit.** Red tests first:
   - direction changed after a result opens a check and changes the standing;
   - a single correlation against the stated direction shows `H-DIR-SIGN`;
   - a second task is reached by the next action;
   - a row edited with raw SQL fails chain verification.
8. **Report.** `python-docx` reads the exported report of the master scenario:
   - six hypothesis blocks, each with designation, plan version, method, n, estimate with CI, review state and records;
   - 0 duplicated paragraphs;
   - with language LV, 0 unmarked English engine sentences;
   - page size A4 when chosen.
9. **Export.** Round trips in CI on Linux and Windows:
   - `.xlsx` read by openpyxl and pandas, `.sav` by pyreadstat: values, names, labels, levels and missing codes are equal;
   - cells `=1+1`, `+x`, `-2+3`, `@SUM(A1)` are strings;
   - `007` stays `007`;
   - a preview lists every renamed or truncated field.
10. **Settings.** Harness:
    - with `{"language": "ru"}` the workspace starts in Russian, the top bar has EN and LV only, and Settings shows Russian;
    - LV chosen, restart, LV;
    - an unknown stored value is never rewritten;
    - text size 125 % scales every `wc.text`;
    - screenshot suite at 1097 × 617 shows nothing clipped; Windows journey at 100, 150 and 175 %.

**Not in the ten: the local research library.** It reduces no counted interaction and closes no scientific gap of the scenario. It should follow, as its own PRs (§8).

## 5. Two alternative interface architectures

`STAGE37_DESIGN.md` already compares a protocol view and an analysis desk on the 13-variable fixture. On the 98-variable scenario the result changes: the cost sits in item sets and page changes, which that comparison does not measure. Counts below are estimates for the master scenario with improvements 2–6 in place. They need a prototype and a harness test.

| | Today (`2f9af71`) | A. Study outline | B. Statistics desk |
|---|---|---|---|
| Layout | Sidebar pages; plan and hypotheses on the Project page | One outline (Study, Measures, H1…H6, Report); the chosen node shows plan, analysis, result and checks in place | Menu bar, variable panel with search and multi-select, analysis pane, cumulative output; hypotheses as a side panel |
| Novice | ≈ 400–425 interactions, ≈ 80 page changes | ≈ 150, ≈ 6 | ≈ 185, 0 page changes, 6–20 dialogs |
| Novice guidance | Next action on one page | Next action at every node | Little; order is free |
| Link to hypothesis | Automatic from the plan | Automatic | Manual, often after the result ("linked late") |
| Professor | ≈ 40, ≈ 19 | ≈ 10, 1–2 | ≈ 12, 0; checks found by reading |
| Statistical choices | Visible | Visible inside the node | Visible in the pane |
| Cost and risk | — | Medium; reuses the 37.0a model and data keys | High; a new shell and all 18 journeys rewritten |

**Recommendation: A, built step by step inside the present shell, with B's variable panel.**
- Keep the sidebar, the pages and the data keys.
- Turn the Project page's hypotheses card into the outline, with the analysis opened in place.
- Add a persistent variable-and-scale panel with search, prefix and range selection to Analyze and Prepare.

Reasons:
1. The measured cost comes from item picking (134 ticks) and page changes (≈ 80), not from the visual style.
2. The 37.0a model (plan, tasks, checks, records) maps one-to-one onto outline nodes.
3. The 18 Windows journeys stay valid.
4. Method, options and confirmations stay explicit choices; nothing is chosen for the researcher.

Typography and density belong to Settings (#10), not to a redesign.

## 6. Architecture review

**Schema 6.** Sound parts:
- additive migration in one transaction;
- a backup before migrating;
- a read-only version probe that refuses a newer format without writing (`project_store.py:347-390`);
- append-only triggers (`:325-329`);
- versioned plans.

Weak parts:
- no copy for older versions;
- `runs.provenance` holds both the immutable hypothesis snapshot and the mutable review ticks, and `set_reviewed` rewrites the whole JSON (`:1761-1774`);
- no foreign keys on protocol records;
- the `events` log is unprotected;
- JSON columns carry no version except `plan_format`.

Scales, variable metadata and a library will each want a migration: plan one format 7 for measurement metadata instead of several.

**Numbering conflict.** `STAGE37_DESIGN.md` §12 and `STAGE37_NEXT_SPEC.md` §7 both use 37.1–37.4, for different content. Neither gives mediation and moderation a stage.

**Importer.**
- `import_session.py` is a clean, interface-free seam with one list of blockers. The review survives a restart (journey `import-resume`).
- The parsers are large: `scientific_survey_import.py` 2,168 lines, `matrix_reconstruction.py` 1,202.
- Messages exist twice, as English sentences and as keys (`import_session.py:63-75`).
- The work ends at an editable draft: scoring evidence never reaches the data (M3).

**Word report.**
- `plan_report` is pure data and testable. Saving is atomic, and each export gets a new file name (`report_docx.py:400-420`).
- Weak parts are U8, U9, S14 and D9.

**State retention.**
- Per project: tasks, results, notes, review ticks, report settings, chart views, levels and the import review are kept.
- Application settings sit in four files in two folders: `~/.statistical_research_assistant/preferences.json` and `workspace.json`, the profile beside the projects, and the AI settings under the data folder.
- Not kept: language without a profile, theme, window, sidebar state, opened hypothesis rows, last page.

**Module size and coupling.**
- `research_app.py` is 3,066 lines in one closure; `survey_ui.py` 2,824; `workspace_questionnaires.py` 2,456; `workspace_analyze.py` 1,915 with three page classes.
- Two interfaces are maintained, and the workspace still hosts a classic panel (D6).
- `workspace_text.py` stores texts as (EN, LV, RU) tuples by position. Hiding Russian in the top bar must not touch these tables or `LANGUAGES`: `app_preferences.py:36-38` resets any unknown language to English.

## 7. Privacy, licensing and accessibility notes

**Privacy and AI.**
- The present design is careful: own key in the Windows credential store, per-project permission for each source, an exact preview, metadata-only logs, and `<data>` wrapping whose closing tag cannot be forged (`ai_assist.py:54-55`, `:170-171`).
- Gap 1: "data rows" sends the first 5 rows with all columns, including an identifier column and free text, on the researcher's own statement of anonymity (`ai_context.py:271`). Exclude columns confirmed as identifiers and text columns by default.
- Gap 2: `.sra` backups and the data folder are unencrypted and hold participant answers. Say so where a backup is made.
- Gap 3: only three remote hosts exist. A local endpoint needs the already present `remote` flag carried through.

**Local library.** It needs:
- a project-scoped SQLite FTS5 index, with chunks that carry file hash, page and section;
- snippets with a link to the local source;
- deletion that also purges the index.

FTS5 is compiled into this Linux Python (SQLite 3.45.1, in-memory probe); check the packaged Windows runtime too. The `unicode61` tokenizer folds Latvian diacritics but does not stem: "одиночества" did not match "одиночество", and "lonely" did not match "loneliness". Benchmark prefix or trigram search before any embedding model.

**Prompt injection.**
- Offline search has no model and no injection risk.
- For AI use, retrieved text is untrusted: show the snippets before sending, send only approved ones, and verify every quoted span against the source, as numbers are verified today.
- The assistant must stay without actions.

**GDPR.** Papers are not participant data. Notes and transcripts may be, so the library needs the same project isolation and an explicit choice of whether library files travel in a backup.

**Licensing.**
- pingouin (GPL-3.0) is imported in-process for one function (`reliability.py:56-58`), and the project has no LICENSE. The owner must choose: GPL-compatible distribution, or replacement (#1). Take legal advice before any commercial distribution.
- OCR: Tesseract runs as a separate program. Its bundle includes GPL parts (jbigkit, GCC runtime with exception) and LGPL parts, with licence texts and source package names recorded (`BUNDLED_OCR.md:45-59`). Keep the source offer with every release.
- pyreadstat (Apache-2.0, ReadStat MIT) is acceptable for `.sav`, but is a new compiled dependency for the package audit.
- No WHO-5, MSPSS, UCLA or SACS item text is in the code (grep). The NC-SA terms of WHO-5 exclude bundling it in a commercial product.

**Accessibility.** The repository's own statements, which I confirm in code where possible:
- UI Automation reports every button as enabled (Flutter bridge), so Narrator would announce a disabled Run as available;
- no keyboard-only walk and no Narrator session has been done;
- display scales were checked for Home and the sidebar only.

New points:
- no focus management (U11);
- contrast failure in the hosted panel (D6);
- about 100 checkbox tab stops in a role picker (U2);
- fixed text sizes (U12).

Icon buttons must have a name (`workspace_components.py:180`), and the status line is a live region. Both are good.

## 8. Implementation split

Each line is one draft PR with red tests first.

**Research methods**
- RM-1: own Cronbach α and interval; licence decision; LICENSE.
- RM-2: scales register, scoring, reverse keys, reliability for all scales (format 7).
- RM-3: linear model with categorical covariates, product terms, β.
- RM-4: mediation, moderation, Johnson–Neyman, Models 4/7/14, with oracles and wording guards.
- RM-5: descriptives table; correlation matrix with inference.
- RM-6: audit hardening (S8, D3, D4, D12, hash chain, note history).
- RM-7: fixture v2: reverse items, patterned missingness, covariate effects, a consistent-mediation variant, a negative coping dimension.

**Export**
- EX-1: escape formula-like text in existing CSV exports; separator option (small; do first).
- EX-2: variable metadata: labels, value labels, user-missing codes (same format step as RM-2).
- EX-3: `.xlsx` with Data, Codebook, Scales, Results and Provenance sheets; text identifiers as text cells.
- EX-4: `.sav` through pyreadstat, with a rename and truncation preview and a round-trip check; `.sav` import.
- EX-5: one Export button with the last-used format; results workbook; manifest.

A correct `.sav` needs:
- names of at most 64 bytes, unique without regard to case, and not reserved words;
- labels within SPSS limits;
- confirmed levels mapped to measure;
- at most three discrete missing codes or one range;
- identifiers as string variables.

**UX and settings**
- UX-1: one settings file; workspace first; EN/LV quick switch with RU in Settings; D1, D2.
- UX-2: text size and density through `Ui` and `wc.text`; Segoe UI as chart default with fallback.
- UX-3: variable panel with search, prefix and range; eligible variables only; sticky bulk bar in the dictionary.
- UX-4: next action on every page; results stay in the task; outline on the Project page.
- UX-5: report by hypothesis; records in the report; A4; report language.
- UX-6: Windows journeys for hypotheses and settings; keyboard-only walk.

**Local library**
- RAG-1: project library store with FTS5; import of PDF and DOCX with page and section.
- RAG-2: offline search with cited snippets and "open source".
- RAG-3: approved-snippet payload for the optional assistant, with preview and quote verification.
- RAG-4: evaluation set (EN/LV/RU recall, citation accuracy); only then optional embeddings.

**Order.** RM-1 and EX-1 first (small, remove risk). Then RM-2 with UX-3 (largest measured gain), then RM-3 to RM-5, UX-4, RM-6, UX-5, EX-2 to EX-5, UX-1 and UX-2, then the library.

### Critical Files for Implementation

- `workspace_methods.py`
- `workspace_analyze.py`
- `research_workflow.py`
- `project_store.py`
- `preparation_ui.py`
