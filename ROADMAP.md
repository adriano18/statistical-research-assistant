# Roadmap — Statistical Research Assistant

## Project goal

A **local-first, reproducible statistical workbench** for psychology and marketing research, with correct calculations, practical guidance, APA-style output and later optional AI interpretation. This is a focused SPSS-like assistant, **not a promise to reproduce all IBM SPSS procedures**.

**Current development sequence**: complete the essential statistical core and data preparation → validate against reference cases → make output and workflow usable → integrate a method advisor and optional AI → finish EN/LV/RU localization and UI polish. Usability problems that prevent testing, copying or saving are fixed immediately, not postponed.

## 1. Implemented statistical core

- [x] CSV/XLSX import and variable/missingness overview
- [x] Descriptive summaries, categorical frequencies, histogram and bar chart
- [x] **Explore**: overall or group boxplots, individual observations, normal Q–Q plot, Shapiro–Wilk and median-centered Levene/Brown–Forsythe (added)
- [x] Cronbach's α, confidence interval and α-if-item-deleted
- [x] Pearson r, Spearman ρ, scatterplot and exploratory correlation matrix
- [x] Independent Welch t and Mann–Whitney U with effect size and graph
- [x] Paired t and Wilcoxon signed-rank with within-person change plot
- [x] Pearson χ² independence, Cramér's V, observed/expected cells and 2×2 Fisher exact option
- [x] One-way ANOVA, Welch ANOVA and Kruskal–Wallis, with effect estimates
- [x] Tukey / Tukey–Kramer, Games–Howell and Dunn with Holm-adjusted post-hoc p-values
- [x] PNG generation for every statistical chart; configurable local folder saving and copyable text through shared toolbar (added)
- [x] Automatic Python unit tests via GitHub Actions

## 2. Statistics to complete before AI — in priority order

### P0. Essential research methods
- [x] **Simple and multiple linear regression (OLS)**, model summary, B/SE/t/p, 95% CI, R², residual plots, VIF, Cook's distance, HC3 robust coefficient inference
- [x] **Friedman test** for 3–8 related ordinal measurements with Kendall’s W and Holm-adjusted paired Wilcoxon comparisons
- [x] **One-factor repeated-measures ANOVA** with Greenhouse–Geisser-adjusted inference, partial η² and Holm-adjusted paired t comparisons
- [ ] Mauchly sphericity test, multilevel/mixed-effects repeated models and optional planned contrasts
- [x] **One-factor ANCOVA / Gaussian General Linear Model** with 1–3 quantitative covariates, joint common-slope interaction check, conditional GLM, adjusted group means, Holm pair comparisons, group-fit plot and OLS diagnostics
- [ ] ANCOVA/GLM expansion: factorial designs, custom covariate references, estimated marginal mean contrasts with simultaneous intervals, robust group tests and model diagnostics for nonlinear covariate effects
- [x] **Binary logistic regression** for 0/1 outcomes, MLE, OR and Wald 95% CI, likelihood-ratio test, convergence/separation safeguards and in-sample ROC/calibration
- [ ] Logistic regression improvements: categorical factor encoding, penalized/Firth estimates for sparse samples, external validation and classification diagnostics
- [ ] More complete diagnostics: residual vs fitted plots, outliers/influence, variance inflation factors, distribution checks of **paired differences**
- [ ] Confidence intervals for important effect sizes; control of multiplicity
- [ ] Independent reference checks against SciPy, statsmodels and jamovi/JASP

### P1. Data preparation and psychometrics
- [ ] Variable labels, value labels, nominal/ordinal/quantitative metadata and manual designation of ID/group/scale
- [x] Non-destructive explicit missing codes, recoding, reverse-scored items, sum/mean scale variables with minimum-completeness rules
- [x] Safe working-copy preparation; new columns only, protected source file and new CSV + JSON transformation log
- [ ] Reuse or import existing transformation recipes and manually audit all steps before reuse
- [ ] Import SPSS `.sav` (optional `pyreadstat`) without remote uploads
- [ ] McNemar for paired binary classifications; chi-square goodness-of-fit for one categorical variable
- [ ] Partial correlations
- [ ] **McDonald's ω**, scale item diagnostics
- [ ] EFA / PCA with loading matrices, scree plot, suitability checks and explained variance
- [ ] Sensitivity/sample-size and power interpretation, confidence intervals and multiple-testing policy

### Local questionnaire collection

- [x] **Local questionnaire builder (MVP)**: required/optional questions, 1–5 Likert, single choice, numeric, text and required consent checkbox
- [x] Immutable survey definitions; transactional local SQLite responses in Git-ignored `data/surveys/`
- [x] Load response dataframe directly into the existing analysis tools and optionally export a CSV
- [ ] Research-ready consent information, configurable study information, retention and withdrawal policies, permissions and encryption at rest
- [ ] Separate respondent-facing design optimized for phones, navigation, accessible scales and multilingual survey text
- [ ] **Self-hosted web distribution** (NOT IMPLEMENTED): dedicated HTTPS server, privacy/legal review, per-survey access links, authentication for researchers, anti-abuse controls, backups and secure deployment
- [ ] Surveys with pages, branching, randomization, validation rules, preview, questionnaire revisions/version control and data dictionary
- [ ] Data entry editing and controlled withdrawal/deletion for participants, plus explicit deletion of a study

### P2. Advanced / only if research needs it
- [ ] MANOVA, repeated-measures mixed models and generalized linear models
- [ ] Mediation/moderation with appropriately interpreted uncertainty
- [ ] Clustering, discriminant analysis and advanced dimensionality reduction
- [ ] Time series, survival analysis, classification and other domain-specific methods
- [ ] Structural equation modeling / confirmatory factor analysis (may be better delegated to dedicated packages)

**Scope checkpoint:** P0 + selected P1 establishes a credible master's-level analysis assistant for many designs. P2 is not a requirement for a useful first release.

## 3. Graphs and output

- [x] Histograms, bar charts, scatterplots, correlations heatmap, grouped boxplots, paired change, contingency figures, reliability figure
- [x] Dedicated **Explore** boxplots and Q–Q plots with Shapiro/Levene results
- [x] Copy APA report text; save report TXT and PNG through a native *Save as* dialog (desktop)
- [x] Per-analysis output cache in memory; no upload; explicit output location
- [ ] APA-style **editable** tables, suitable DOCX and PDF with headings, numbered tables/figures and sources
- [ ] Export full analysis workbooks as Excel and CSV including metadata, decisions and reproducible method settings
- [ ] Combined report containing several selected analyses, not only one active panel
- [ ] High-resolution SVG/PDF vector chart option and configurable graphical style
- [ ] Store reproducible analysis history, seeds, library versions and input file hashes
- [ ] Audit/verify export on Windows and ensure report text can be selected/copied accessibly

## 4. Research method advisor, then AI

- [ ] Deterministic method advisor: research question, variables, measurement scales, independent/paired design, outcomes, N and missing data
- [ ] Explain assumptions, alternatives, effect sizes and appropriate caution
- [ ] **Optional AI** after calculation: interpret a strictly structured summary; never fabricate p-values, results or references
- [ ] User approval before sharing any research data with external AI; local-only remains default
- [ ] Track the exact analysis, assumptions and code version backing every explanation

## 5. Languages and product interface

- [x] Sidebar split into datasets, descriptives, reliability, associations and group comparisons
- [x] Reusable copy/save buttons accessible above results; main outcome and figures prioritized; lengthy cautions collapsible
- [ ] Separate **result table / data preview / variable dictionary** from the analysis setup
- [ ] Sortable/exportable post-hoc and descriptive tables, improved compactness and keyboard navigation
- [ ] EN / LV / RU localization using translation keys for menus, errors, notes, reports and accessibility strings
- [ ] English default; Latvian and Russian selectable in Settings
- [ ] Polish Flet desktop and responsive layout after core stability

### GUI platform decision

**Stay with Flet for now.** The statistical functions live in independent Python files and can be reused in a future PySide6 (Qt) desktop client. Rebuilding every current workspace immediately would take time away from statistics, testing and reports. Review migration **after P0**, if scientific data editing, very large tables, menus, drag-and-drop or accessibility still cannot be implemented satisfactorily.

Alternatives to evaluate later:
- **PySide6 / Qt**: richer native desktop tables, dialogs and docking, more frontend code.
- **NiceGUI / Streamlit**: fast web-style applications but local server/browser distribution and privacy/deployment trade-offs.
- Flet: keep the current tested desktop workflow, improve its reusable UI components.

## 6. Testing, privacy and release

- [x] Offline core tests and GitHub Actions check on pushes
- [ ] Validate exported copy/TXT/PNG and Windows save dialogs manually
- [ ] Cross-check named datasets and extreme cases against trusted scientific tools
- [ ] Confirm that repeated, nested and missing-data structures are not silently misclassified
- [ ] Package an offline Windows executable
- [ ] Clear privacy and limitation documentation; never put participant data in public GitHub

## Limitations

Boxplots and Shapiro/Levene diagnostics are exploratory, not an automatic decision tree. Shapiro p > .05 does not prove normality; for ANOVA, residuals rather than raw scores matter, and for paired t-tests it is the **differences** that matter. APA-style format is a reporting aid, not an APA 7 certification or a proof of valid study design. Figures are numbered as manuscript placeholders. Many advanced SPSS methods remain outside the first-release scope.
