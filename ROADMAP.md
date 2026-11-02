# Development roadmap

Statistical Research Assistant is a learning-oriented, local-first research tool for psychology, marketing and other fields. The goal is transparent statistical calculations, methodological safeguards, readable interpretation and reusable reports, not a full clone of SPSS.

## Phase 1 — Data and descriptive analysis
- [x] Import CSV and Excel locally
- [x] Inspect variables and missing values
- [x] Confirm measurement scales rather than trusting numeric data types
- [x] Descriptives and distribution charts
- [ ] Variable metadata: labels, value labels, missing-value codes, reverse scoring, scale totals
- [ ] Import SPSS .sav with privacy-safe handling

## Phase 2 — Statistical methods (finish before AI)
- [x] Cronbach's alpha with CI and item-deletion diagnostics
- [x] Pearson and Spearman correlations
- [x] Exploratory correlation matrix with pairwise N
- [x] Independent-group Welch t-test and Mann–Whitney U
- [x] Paired t-test and Wilcoxon signed-rank
- [x] Pearson chi-square test of independence, Cramér's V, expected-count checks and Fisher exact result for sparse 2×2 tables
- [ ] Chi-square goodness-of-fit when theoretically needed
- [x] One-way ANOVA, Welch ANOVA and Kruskal–Wallis omnibus tests (3–8 groups), descriptive effect estimates and plots
- [ ] Post-hoc comparisons (Tukey / Games–Howell / Dunn as appropriate) with multiplicity correction
- [ ] Repeated-measures ANOVA and Friedman with multiple-comparison control
- [ ] Assumption diagnostics: Q–Q plots, Shapiro–Wilk, variance checks, outliers, paired-difference diagnostics
- [ ] Regression (linear, multiple, logistic) and related diagnostics
- [ ] Effect sizes, uncertainty intervals and multiplicity correction wherever appropriate
- [ ] Further psychometrics: dimensionality, exploratory factor analysis, omega reliability
- [ ] Cross-check critical computations against SciPy, jamovi/JASP and published reference cases

## Phase 3 — Explanations and research assistant
- [ ] Rule-based method advisor based on research question, variable roles, measurement scale and independent/paired design
- [ ] Assistant asks for missing design details rather than guessing
- [ ] Clear interpretation with assumptions, effect size, CI and study limitations
- [ ] Integrate AI for conversational explanations only after deterministic statistics and tests are stable
- [ ] Do not let AI invent computed statistics, infer causality or treat p < .05 as practical importance
- [ ] Send only user-approved, minimized or de-identified summaries to external AI services; local-only mode remains available

## Phase 4 — Reporting, export and reproducibility
- [x] Short/main results, descriptives and separate cautions for paired measurements
- [x] Save paired APA-style report as local UTF-8 TXT
- [x] Save paired figure as local PNG
- [ ] Apply structured results and local export to all analysis modules
- [ ] Export tables and reports to XLSX, DOCX and PDF with manuscript-specific APA 7 details
- [ ] Save analysis settings and data-cleaning decisions for reproducibility
- [ ] Allow user-selected report destination and safe filenames
- [ ] Add sources and references for interpretation thresholds and test recommendations

## Phase 5 — Languages and UI/UX
- [ ] Internationalization system with message keys, no hard-coded UI strings
- [ ] **English (EN)** as the current default language
- [ ] **Latvian (LV)** localization for research and university use
- [ ] **Russian (RU)** localization for convenient everyday use
- [ ] Language selector in Settings; translations must cover help, limitations, errors and report explanations
- [ ] Consistent terminology and APA symbols in every language
- [ ] Refine responsive Flet layout, readable cards, navigation, plots and accessibility
- [ ] User-friendly data preview, column search, help tips and research workflow guidance

## Phase 6 — Verification and release
- [ ] Offline unit tests for every test, assumption guard and reporting formatter
- [ ] Integration/UI smoke tests on Windows desktop
- [ ] Compare results against trusted statistics software for representative datasets
- [ ] Test missing, tied, constant, sparse, extreme and invalid observations
- [ ] Packaging, instructions, versioned releases and backup/restore options

## Current scope and limitations

The application is not a validated clinical tool. The reported APA-style sentences are templates and need verification against the actual research context and manuscript requirements. Statistical tests must be chosen using study design, assumptions and construct meaning. The local `reports/` and `data/` folders are Git-ignored; identifiable participant records should not be published or sent to AI services.

### Next concrete milestone
Finish the remaining common statistical tests and diagnostic aids, then build the rule-based/AI research assistant. Complete multilingual UI/UX polish after the statistical core is tested, while keeping the current layout functional.
