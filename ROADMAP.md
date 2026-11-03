# Roadmap — Statistical Research Assistant

## Project goal

A **local-first, reproducible statistical workbench** for psychology and marketing research, with correct calculations, practical guidance, APA-style output and later optional AI interpretation. This is a focused SPSS-like assistant, **not a promise to reproduce all IBM SPSS procedures**.

**Next development sequence**: validate omega bootstrap CI and oblique EFA with independent statistical tools → improve questionnaire response labeling / navigation → add optional ordinal/polychoric modeling and more psychometric diagnostics → build researcher method guidance / optional AI → complete EN/LV/RU UX and secure respondent-facing distribution. English/Latvian/Russian localization and reporting remain cross-cutting priorities. Do not delay blockers in data collection or export.

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
- [x] **One-factor standardized McDonald's ω**, ML Pearson factor loadings, uniqueness, corrected item-rest r, item mean/SD/missingness, PNG and cautious APA report
- [x] Optional 95% case-resampling percentile bootstrap CI for one-factor omega, deterministic seed and inadequate-fit rejection; Pearson/Spearman item-rest diagnostics
- [ ] Omega extensions: BCa/model-based intervals, polychoric/ordinal reliability, multi-factor ω total/hierarchical and formal fit assessment
- [x] **Exploratory PCA and principal-axis EFA**, loading matrices, PCA explained variance, scree plot, KMO overall/item, Bartlett χ², fixed-seed PCA parallel analysis, optional varimax rotation
- [x] Oblique EFA oblimin rotation with factor correlation (Phi), pattern/structure matrix distinction and cross-loading warnings
- [ ] EFA extensions: polychoric correlations, oblique rotation variants, factor scores, alternative extraction criteria and stronger dimensionality validation
- [ ] Sensitivity/sample-size and power interpretation, confidence intervals and multiple-testing policy

### Immediate priority: questionnaire usability before expanding forms

- [x] **P0 - Split the crowded Questionnaire screen** into focused **Build**, **Preview**, **Fill survey**, **Responses / Export** views
- [x] **P0 - Visual form editor**: editable list and question properties side by side; dedicated live-logic Preview tab
- [ ] Add optional simultaneous split-pane original-source/preview mode and mobile/narrow-window layout review
- [x] **P0 - Reduce visual clutter**: consistent field widths, compact panels, constrained content width and separate workflows
- [ ] Verify final survey spacing, keyboard focus and accessibility manually on Windows
- [x] **P0 - Basic editing**: reorder, duplicate, remove and edit draft questions; preview without storing responses; clone published survey to a new draft
- [x] **P0 - Response usability**: submission confirmation, response count, first-ten-rows table, direct Dataset loading and CSV + JSON codebook export
- [ ] Keep the statistical/data-processing engine independent of Flet so a future dedicated browser-based respondent interface remains feasible

**Priority decision:** test the rebuilt editor manually on Windows, fix confirmed UI blockers, then resume **McDonald's ω, item-level reliability checks and EFA/PCA**. Keep public survey hosting, clinical triage and complex logic outside this phase.

### Questionnaire editor: deferred usability improvements

- [ ] **Drag and drop** to reorder individual questions and whole sections, with keyboard-accessible move-up/move-down controls retained as a fallback
- [ ] **Value-label mappings for all Likert and rating choices**: display a readable localized label (e.g. `1 = Ļoti slikti / Очень плохо`, `3 = Vidēji / Средне`, `5 = Ļoti labi / Очень хорошо`) while storing **stable numeric scores 1–5** in the dataset
- [ ] Support fully custom and unequal-endpoint scales, semantic differentials and optional `Don't know / Prefer not to answer` missing-value codes without pretending the categories are continuous
- [ ] Keep response labels, raw codes, ordinal metadata and reverse-key flags in the codebook; require the researcher to confirm reverse scoring before creating transformed columns
- [ ] Responsive layout for smaller windows, text wrapping, compact item cards, keyboard navigation, accessible contrast and previews showing real respondent-visible labels
- [ ] Usability test builder on Windows with several participants creating/previewing a real **licensed** questionnaire (no actual sensitive participant data during development)

### Future: questionnaire import from a photo or document (AI-assisted)

- [ ] Accept an **image/photo, scanned PDF or digital PDF**; prefer extracting text directly from digital PDFs and use OCR/vision on scanned pages
- [ ] Detect question blocks, item wording, numbering, Likert anchors, choices, required fields and possible reversed-key markers, then generate a **draft survey schema (JSON)** rather than publishing a form automatically
- [ ] Open a **side-by-side source image/PDF and editable questionnaire draft** with uncertain items highlighted; researcher must review and approve each question, coding and skip rule
- [ ] Check for omitted/duplicated questions, broken page order, wrong answer scales, ambiguous instructions and inconsistent key names before finalizing
- [ ] Offer an optional local OCR/vision pathway; any cloud AI document processing requires explicit consent and clear disclosure of what is uploaded, with **local-only as the default**
- [ ] Respect permissions and copyright/licensing of published psychological instruments; a photograph does **not** establish the right to reproduce or deploy a questionnaire
- [ ] Test with clean scans, skewed phone photos, multilingual EN/LV/RU forms, tables, multi-page instruments and deliberately ambiguous layouts
- [ ] Do not infer scale validity, reliability or scoring/reverse coding from an image alone. Require the official scoring manual or researcher confirmation.

### Local questionnaire collection

- [x] **Local questionnaire builder**: Likert 1–5/1–7, single/multiple choice, Yes/No, numeric, short/long text, date and required consent
- [x] Immutable survey definitions; transactional local SQLite responses in Git-ignored `data/surveys/`
- [x] Load response dataframe directly into the existing analysis tools and optionally export a CSV
- [ ] Research-ready consent information, configurable study information, retention and withdrawal policies, permissions and encryption at rest
- [ ] Separate respondent-facing design optimized for phones, navigation, accessible scales and multilingual survey text
- [ ] **Self-hosted web distribution** (NOT IMPLEMENTED): dedicated HTTPS server, privacy/legal review, per-survey access links, authentication for researchers, anti-abuse controls, backups and secure deployment
- [x] Named sections, one-condition-per-question branching with earlier valid choice/numeric fields, cascading hidden-as-null logic, metadata-only reverse-key marks and scale IDs
- [x] Preview without saving answers, published-form cloning into a draft and machine-readable JSON codebook
- [ ] Pages, full AND/OR logic, randomization/balancing, response timers and advanced validation
- [ ] Real study version history, controlled edit/delete and a complete data dictionary with coded value labels
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
- [ ] Fix questionnaire editor layout and navigation now; reserve broader Flet polish for after the next psychometrics milestone

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
