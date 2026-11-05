# Statistical Research Assistant

A Python project for exploring research datasets and, later, selecting and interpreting statistical methods.

**Goal:** a small, transparent alternative to common SPSS workflows for psychology, marketing and business research. The program will calculate statistics using established Python libraries. A future assistant may explain results, but it must not invent numbers or choose tests without checking their assumptions.

**[Full development roadmap](ROADMAP.md)** — finish essential statistics, validate results, maintain usable copy/save workflows, then add optional AI and multilingual UI/UX.

## Development plan
1. **v0.1 Data inspection** — import CSV/XLSX, review variables, missing values and their inferred data types.
2. **v0.2 Descriptive statistics** (in progress) — N, mean, median, SD, distributions and plots.
3. **v0.3 Research methods** (in progress) — reliability, correlations, chi-square, independent and repeated designs, group omnibus/post-hoc tests, linear/logistic regression and ANCOVA; local preparation/forms added; advanced psychometrics and data dictionaries remain planned.
4. **v0.4 Method advisor / AI** — after statistical validation, recommend candidate tests from study design; optionally explain results with AI, without inventing calculations.
5. **v0.5 Reports and localization** — TXT/PNG export and copying are available across analysis screens; next are structured APA tables, DOCX/PDF, and EN/LV/RU translations.

## Stage 32 — spatial OCR review, OCR confidence, questionnaire matrices and bundled Windows OCR

The scientific importer is now a **split-screen review**: the rendered source page on the left with highlighted question regions, and the question editor, confidence panel, region tools, review queue and **matrix editor** on the right. See the [Stage 31–32 user guide](docs/VISUAL_OCR_IMPORT.md) and the [bundled OCR developer guide](docs/BUNDLED_OCR.md).

* **Spatial OCR:** local Tesseract TSV output keeps every word's box and raw confidence (typed `OCRWord/OCRLine/OCRBlock/OCRPage`, normalized page coordinates). Text-based PDFs get the same positions from the PDF text layer. Boxes stay aligned through zoom (50–300 %), page switching and view rotation; click a box to open its question. Unlinked text is shown but never turned into a question. Regions can be adjusted, split, merged, linked, unlinked and reverted; the source file is never modified.
* **OCR confidence ≠ structure ≠ validity:** OCR confidence is the mean raw Tesseract word score (≥ 85 high, 60–84 or any word < 60 review, < 60 low, unknown without scores). Reconstruction problems are reported by a separate rule-based *structure* status, never as a percentage. Neither is evidence of reliability or validity.
* **Matrices:** Likert-type row × column grids are reconstructed from native Word tables (merged group headers, numeric code rows, multi-line cells, missing cells), PDF text geometry and OCR boxes (printed codes, page-break continuation, descending codes, overlapping headers). The original grid is preserved; the editable grid must be verified, and numeric codes and reverse-keyed rows apply only after separate confirmation. Every edit resets approvals.
* **Offline OCR included on Windows:** the Windows build bundles Tesseract 5.5.4 (MSYS2 UCRT64) with `eng`, `lav`, `rus` and `osd` data, its exact DLL closure, licence texts and pinned SHA-256 hashes. No Tesseract, Python or language pack installation is needed. `TESSERACT_CMD` still overrides the bundled engine for development. **Settings → Offline OCR engine…** shows version, languages and integrity.

### Installing the Windows desktop preview

1. Open the latest successful run of **Windows desktop bundle with offline OCR** under the repository's *Actions* tab (it runs on pull requests touching the importer/OCR and can be started manually).
2. Download the `StatisticalResearchAssistant-Windows-x64-unsigned-preview` artifact and extract `StatisticalResearchAssistant-Windows-x64.zip` to a folder you can write to (for example `C:\Users\<you>\Apps\StatisticalResearchAssistant`).
3. Run `StatisticalResearchAssistant.exe`. The build is **unsigned**, so Windows SmartScreen may ask you to confirm ("More info → Run anyway").
4. Optional check: **Settings → Offline OCR engine…** should say "bundled with this application", list `eng, lav, osd, rus` and "bundle integrity verified".

From source on any OS, install Tesseract 5 with `eng`/`lav`/`rus` data (or set `TESSERACT_CMD`) — see the user guide.

## Stage 31 — local OCR and in-app visual editing

The Scientific Questionnaire Importer now displays actual **PDF pages in-app** and a clearly labeled **Word paragraph/table reconstruction** alongside editable extracted questions. A researcher can change wording, response type, choice labels, section and requiredness **before** accepting the source into the editable questionnaire draft. Corrections never alter the source document, published schema or respondent data. Separate source/version and scoring approvals remain mandatory.

For image-only PDFs, use local Tesseract OCR (bundled in the Windows package since Stage 32; installed separately when running from source, with the appropriate ENG/LAV/RUS languages), either one page at a time or for the first 20 pages in a bounded batch. PDFium is included as a Python dependency and renders the visual page from bytes. If text extraction fails, the scanned source still opens for preview and the user may run OCR. The selected file stays in memory during review. OCR runs locally in the **desktop** application; browser/server mode is disabled for this local-only OCR workflow. See the [Stage 31 setup and operating guide](docs/VISUAL_OCR_IMPORT.md).

Scientific caution: OCR mistakes and complex rating matrices require visual verification; the importer never guesses psychometric validity, test norms or consent. Automated tests use synthetic scans with real local Tesseract (and mocked output for edge cases), not the user's private copyrighted test files.

## Stage 30 — Scientific Questionnaire Importer

The questionnaire builder can now review existing PDF/DOCX questionnaires and optional legacy DOC sources (local antiword required, otherwise convert DOC to DOCX). Rather than blindly scanning for all numbers, it separates recognized instruments/versions in multi-scale collections, shows extracted source lines next to proposed items, warns about invisible image-based pages, and never treats a bibliography as an instrument. The imported form is **a draft**, not a validated instrument.

Numeric response anchors and reverse-scoring directions are **untrusted proposals**. Every import requires the researcher to confirm the exact version, source, license, wording and candidate list. Numeric labels and reverse-item flags require separate approvals, and published survey versions/answers are unchanged. Complex matrix tables, scanned PSQ pages, incomplete scoring, consent and skip logic still need manual reconstruction or future local OCR. Source filenames are retained as candidate-provenance descriptions without copying source documents to the repository.

Synthetic tests cover structures from the six privately uploaded examples, but **do not include copyrighted question banks** in public CI. To run your own private documents locally and inspect just candidate counts/warnings, see the [Scientific Importer guide](docs/SCIENTIFIC_IMPORTER.md) and local audit script. Published scoring validity, diagnostic thresholds, native-window behavior and clinical interpretations remain outside this importer's remit.

## Stage 29 — desktop redesign, local document questionnaires and AI roadmap

The interface uses a **Windows-style desktop shell by default**: squared panels and command buttons, a wider 288-pixel navigation area, greater vertical space for sidebar items, and a horizontal **File / Data / Analysis / Reports / Database / Settings / AI assistant / Help** menu. In **Appearance** select Windows (square corners) or a softer macOS-inspired treatment. The preference is saved locally; language selection remains English by default, with Latvian and Russian available. These are visual treatments of the same Flet app, not native WinUI/AppKit renderers. Some forms retained within statistical modules still require a second design pass.

**Top menus are functional:** File opens data/draft import workspaces, Data opens inspection/preparation, Analysis opens actual statistical screens, Reports opens the APA-report workflow, Database opens locally saved questionnaires and answers, Settings changes appearance, Help explains privacy and the current AI status. Full project file save/open, database backup/restore and a dedicated AI conversation UI are **not implemented**.

**Import existing Word/PDF questionnaire:** Under Questionnaires → Build, expand **Import questionnaire from Word / PDF**, select a local DOCX or text-based PDF, inspect extracted candidates and warnings, then explicitly choose **Use extracted questions as editable draft**. Existing unsaved draft questions require separate replacement confirmation. Extraction recognizes numbered question labels and clearly marked single/multiple choice options; all imported questions default to **not required**, and scoring, Likert numeric codes, reverse-keying, conditions, consent language and section/page formatting must be manually reviewed. **Nothing is published automatically**. Scanned PDF files require separate OCR, and many table/matrix layouts cannot yet be reconstructed reliably. Supported files are at most 20 MB; PDF reading is bounded to 80 pages.

**AI helper status:** The project's Roadmap always included an optional research AI assistant. The current method guides and evidence-grounded interpretation wizard are deterministic/offline functions, **not a connected AI model**. The top Help menu communicates that fact. Future AI work requires explicit consent, local-first defaults, verified computational inputs, source citations and a separate privacy audit before an optional external provider is offered.

**Design-reference files:** WindowsX widget library (.jpl) and macOS Sketch UI Kit (.sketch) were inspected as user-provided references. Their code/assets/fonts were **not** copied into the repository; third-party file formats and licensing must be checked before reuse.

## Stage 28 — reliable questionnaire → Dataset → statistics → APA Word workflow

The **Load responses into Dataset** action on the Questionnaires → Responses & export tab now checks that the main data loader explicitly accepted the responses. A failed load stays in Questionnaires and displays a diagnostic; a successful load opens **Dataset** automatically. The current dataset banner identifies the real originating questionnaire by title. The origin is stored only as DataFrame metadata—not as a false analytical column or participant response. Existing response identifiers, missing answers and raw Likert ratings are unchanged.

The automated end-to-end integration tests generate fictional data at runtime, not hard-coded production results. One scenario publishes a Marketing / Feedback questionnaire with conditional screening, saves Yes/No submissions into SQLite, verifies that skipped values remain missing, exports CSV plus a JSON codebook and reimports CSV through the actual loader. Another creates a four-item scale with 64 synthetic respondents, exports and imports their raw answers, non-destructively reverse-scores a keyed item, computes real Cronbach α with its confidence interval, renders the calculated plot, and exports an editable APA 7-style Word report. The test checks that the DOCX table matches the computed reliability result. No real participant records or fabricated statistics are included.

The Windows CI now exercises the whole questionnaire-to-report sequence with the actual application dependencies and checks Flet preview regressions. For the remaining native-window and Microsoft Word visual validation, follow the [Windows desktop smoke-test checklist](docs/WINDOWS_SMOKE_TEST.md). Automated Python tests do **not** replace a human test of the actual Windows GUI, scaling, keyboard navigation, native file dialog or Word print layout.

## File import reliability fix — use real CSV/Excel research files

**The statistical calculations are not hard-coded.** Automated unit tests use small synthetic datasets with known results as fixtures; production calculations always use the currently loaded DataFrame. For an end-to-end regression test, `tests/test_import_workflow.py` generates two different CSV questionnaire exports with the same column names but different participant responses; their calculated Pearson correlations have opposite signs.

**Open a file:** Select **Open CSV / Excel** from Home or Dataset. Both buttons now use Flet's client-side `PickFiles` action with one central `on_result` handler, so the native file selector runs as part of the original user gesture and file-selection errors are visible. Supported extensions: CSV, TSV, XLSX, XLSM. On success the app automatically opens **Dataset**, where you see the row count, column names, missingness, variable types and import diagnostics. Cancelling selection never reports a successful import; malformed inputs keep the previous DataFrame.

**Desktop fallback:** If the OS dialog still fails, open **Dataset → Import settings**, paste the absolute path into **Full local file path**, and click **Open file by full path**. The path must point to a file on the computer running the desktop application. Files selected in a browser may have no file path; the app reads up to 25 MB of transferred file bytes via a temporary file and removes it after processing. Re-select the file to change browser import settings; browser uploads are not saved as local recent-file paths. **When running against a remote web server, participant data is transferred to that server**; only the desktop mode is suitable when a study requires strict local-only storage.

**Validation:** Unit tests cover actual CSV/XLSX loading from temporary folders, bytes-only selections, cancellations, unsupported extensions, missing files, failure propagation, both UI button actions, successful Dataset navigation, and recomputing statistics from changed source data. A graphical Windows desktop file-dialog smoke test is still required in addition to GitHub Actions.

## Stage 26 — interpretation wizard and editable Word reports

Run an analysis, then expand **Interpretation wizard · Editable APA 7 Word report** in the shared **OUTPUT** area. The four steps are: (1) inspect the actually selected method and its rationale, (2) manually review study assumptions, (3) review numerically verified effect sizes, estimates, confidence intervals and p-values, and (4) edit a draft interpretation and export a Word report.

**Integrity:** Numeric results come from the live calculation result object, NOT from text parsing. A CI for a mean difference is explicitly labelled as such and never passed off as a standardized effect-size CI. Missing intervals and uncaptured structured statistics display **Not calculated** or **Not captured**. Marking an assumption as reviewed documents human review, not statistical proof it holds. Loading a different dataset clears cached estimates and interpretations.

**Editable APA 7-style report:** Choose the destination of a local Word .docx file. The document includes a method/limitations narrative, assumption checklist, editable Word table with minimal horizontal rules, manuscript figure number/title/note, embedded PNG plot if one exists, full original calculation text in an appendix and a bibliography specific to the method. The figure is a replaceable raster image (its plotted points are not individually editable). Never assume the template is automatically ready for journal publication. The default report text is English; wizard navigation has EN/LV/RU alternatives.

**Formatting and review:** The draft uses Times New Roman 12 pt, 1-inch margins and double-spaced narrative, with editable bold table/figure numbers and italic titles. Verify statistical design, interpretation and published references as well as editor/journal-specific formatting. See the [official APA figures and tables guidance](https://apastyle.apa.org/style-grammar-guidelines/tables-figures) and [Purdue OWL guidance](https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/apa_tables_and_figures.html). Synthetic tests inspect evidence extraction, explicit warnings and editable Word tables and image structure; real Word/LibreOffice visual review is an outstanding QA task.

## Stage 25 — multilingual statistical screens, scientific help & APA 7 figures

**Language and terminology.** The English-first desktop application now contains a substantially expanded Latvian and Russian catalog for all 17 workspaces, their main buttons, analysis-selection labels, the questionnaire builder, and instructional warnings. New 5- and 7-point agreement/quality/frequency Likert drafts and the −3…+3 semantic-differential example use respondent labels in the chosen language; Yes/No is translated for display while retaining its existing storage codes. Previously published scales and response data are never retranslated automatically. Switch language through the existing **Language** selector. Static UI text updates without clearing the loaded dataset or editing a published questionnaire. Numeric variable IDs, survey response codes, user-entered text, and the original English calculation reports are **never translated silently**. Some contextual status/errors, third-party chart internals, long generated report paragraphs and less-common Flet labels remain in English; complete editorial and native-speaker validation is still pending.

**Understand each statistic.** Every workspace has a collapsible **Understanding the statistics · Sources** guide (Latvian: **Statistikas skaidrojumi · Avoti**; Russian: **Объяснение показателей · Источники**). It defines the main parameters for that method, explains the assumptions or misuse risks and provides a bibliographic reference with a stable DOI or scholarly source URL. Among the covered concepts: N, missing responses, mean/median/SD/SE, confidence intervals, p-values, effect sizes, Shapiro–Wilk, Levene/Brown–Forsythe, Cronbach's α, McDonald's ω, item–rest correlations, α-if-deleted, EFA/PCA loadings/eigenvalues/parallel analysis, Pearson/Spearman, t, Cohen's d, Mann–Whitney U, Friedman/Kendall W, F, η², Holm, χ², Cramér's V, regression B/β/R²/VIF, logistic OR/ROC and ANCOVA adjusted means. The current **Copy report** and **Save TXT as...** actions append these sourced explanations to the existing numerical output in the selected language. Definitions are educational, not automatic decisions about validity, causality or significance. The original statistical computation remains unchanged. The source list is in [statistical_guide.py](statistical_guide.py).

**APA 7-style figure export.** For an analysis that produced a PNG, open **APA 7 figure export settings** near the shared results toolbar. Choose a manuscript **Figure number**, optional **Figure title** and **Figure note**, then **Save PNG as...**. The export creates a new white PNG with a bold figure number, italic title, source chart and figure note, at 300 dpi, preserving the original calculated values. Existing older plots often have fixed figure numbers printed in their top margin; the export removes these obsolete top/bottom caption margins so the new image has only one number and one note. The chart axes and plotted data remain intact. The export supplies a method-specific cautionary Note by default, which can be edited before export. The image includes caption metadata. The app does **not** claim that upsampling a small original graph improves its underlying raster detail, nor that the template automatically satisfies every journal's submission requirements. Researchers must check legends, axis labels, units, accessibility, figure numbering and the journal's own resolution specifications. The base styling follows *Publication Manual of the American Psychological Association*, 7th ed., Chapter 7, and [Purdue OWL's APA tables and figures reference](https://owl.purdue.edu/owl/research_and_citation/apa_style/apa_formatting_and_style_guide/apa_tables_and_figures.html).

**Verified scientific citations include** Cronbach (1951), DOI [10.1007/BF02310555](https://doi.org/10.1007/BF02310555); Hayes & Coutts (2020), DOI [10.1080/19312458.2020.1718629](https://doi.org/10.1080/19312458.2020.1718629); Fabrigar et al. (1999), DOI [10.1037/1082-989X.4.3.272](https://doi.org/10.1037/1082-989X.4.3.272); Lakens (2013), DOI [10.3389/fpsyg.2013.00863](https://doi.org/10.3389/fpsyg.2013.00863); Cumming (2014), DOI [10.1177/0956797613504966](https://doi.org/10.1177/0956797613504966); and Wasserstein & Lazar (2016), DOI [10.1080/00031305.2016.1154108](https://doi.org/10.1080/00031305.2016.1154108).

**Quality checks** exercise all 17 guides and source links, preserve unmodified user answers on live language switching, check scientific cautions, and validate APA PNG numbering, metadata, dimensions, 300-dpi export and error handling. Statistical reports are templates to be reviewed and edited by the researcher; they do not invent sample sizes, effects or conclusions.

## Stage 24 — English default, optional Latvian/Russian, survey-file import

**Language:** A fresh installation opens in **English**. In the sidebar, choose **Language → English / Latviešu / Русский**; compact-window navigation has the same selector. The choice is saved locally in `~/.statistical_research_assistant/preferences.json` and reused next launch. This first localization pass translates the start screen, navigation, and selected workspace headings. **Statistical-method controls, long methodological explanations, questionnaire editor internals, and APA reports are not fully translated yet**; untranslated strings remain English so that technical terminology is not mistranslated.

**Working with external questionnaires:** Open a CSV, TSV, XLSX, or XLSM file. The app supports comma, semicolon, tab and pipe-separated CSV/TSV; UTF-8 with BOM, UTF-16 with BOM, and selectable CP1257/CP1251/CP1252 legacy encodings. For an Excel workbook, choose the appropriate worksheet; for a questionnaire exported under a cover/title row, set **Header row** to the row containing column names. If the export has another row with full question wording or Qualtrics-style ImportId metadata, set **Data begins at row** to the first actual respondent row (e.g. header 1 and data 4). Skipped rows are reported explicitly. Use **Apply import settings** to reread the original file. The original CSV/Excel file is **never overwritten**. Imported data can also come from manually revised Excel tables.

**Decimals and missing values:** The default decimal parser converts clear `1,25` or `1.234,50` examples, but leaves ambiguous `1,234` values as text and reports why. Choose **Dot decimal** or **Comma decimal** explicitly if you know the source convention. Empty cells and explicitly configured missing markers (default NA, N/A, NULL) become missing values, with a warning. Text choices such as Strongly agree, Yes/No, multi-select responses and IDs like 001 stay text. To analyze questionnaire scores, use **Data preparation** to recode labels into justified numeric scores. Numeric storage does not make an ordinal rating continuous.

**Import diagnostics:** The Dataset screen reports encoding, delimiter, worksheet, skipped blank rows, converted numeric variables, mixed-format columns and other warnings. Blank or duplicated headers, malformed nonempty extra CSV cells, unreadable files and empty datasets show actionable errors; a failed import leaves the existing dataset unchanged. `.xls`, `.ods`, JSON, password-protected workbooks, nested survey exports and automatic decoding of all possible legacy encodings are not supported. CSV files are treated as data, never executed. Spreadsheet formulas are not evaluated; export calculated values from Excel if you need numeric results.

**Recent files:** Up to eight recently opened local file paths are stored only in the local preferences file, never in the repository or cloud. A missing recent file is skipped. A **Clear recent history** button removes saved paths from preferences. Recent-file history is not a saved research project: workbooks, analysis selections and reports are not yet bundled into a restorable project file.

**Windows executable preview:** A manually triggered GitHub Actions workflow, `.github/workflows/windows-package.yml`, can attempt an **unsigned portable Windows bundle** using the official `flet build windows` command on a Windows runner. The bundle must be validated on a real Windows machine, and **is not a signed installer or an automatic release**. Packaging depends on Flet/Flutter and the Visual Studio C++ workload. Until this build has been executed successfully, launch the source app using `flet run app.py`. See the [official Flet Windows packaging guide](https://flet.dev/docs/publish/windows/).

**Test matrix:** `python -m unittest discover -s tests -v` includes generated synthetic Google/Microsoft-Forms-like worksheet patterns, mixed survey exports, CSV delimiters, encodings, header offsets, missing values, decimal styles, duplicate headings, bad rows, and malicious-looking cell text. Tests confirm ingestion behavior, not the validity of a real questionnaire, translation accuracy of all statistical prose, or real Windows GUI rendering.

## Desktop-first experience (Stage 23)

The Windows desktop app opens in a **centered, resizable 1200 × 720 window** with a light Material 3 theme, readable Segoe UI typography and white panel surfaces. The new **Home** dashboard offers three beginner-friendly starting paths: open CSV/Excel data, create a local questionnaire, or explore a fictional dataset. A four-step workflow describes what to do after collecting data. Advanced statistical tools are tucked into **expandable navigation groups**, while screens narrower than 980 pixels use a compact navigation dropdown. The current analysis results stay in place when switching workspaces.

Questionnaire **Build → Preview → Fill survey → Responses & export** is displayed as four clearly numbered stages. In Preview and Fill, Likert 1–5/1–7 and custom numeric/semantic-differential questions now show **visible radio-card choices**, not dropdown menus. All numeric and DK/PNA response codes are unchanged in SQLite and exported datasets. No response is pre-selected. Required-answer and conditional checks continue to apply on each page, which now has a visual progress indicator. Missing-answer choices are visually separated from scored choices.

For a first tour, launch the app, click **Explore sample data**, review the variable overview, then use the sidebar to open **Descriptive**. For survey authoring, click **Create questionnaire** and load a fictional practice template. The same interface is used for respondents only on this local machine; no public survey link is created.

**Desktop limitation:** CI tests check widget structure and calculations, not visual fidelity on actual Windows displays. A manual UX pass on 1366×768, 1920×1080, high-DPI scaling and keyboard-only operation is still required. The app is not yet packaged as a standalone Windows installer or executable; use the Python/Flet launch command below.

## Desktop interface

The Flet application uses a left navigation menu instead of one long scrolling page:

- **Home**: choose a simple beginner-friendly route and see how the research workflow fits together.
- **Dataset**: load a local CSV/Excel file or choose a sample from a collapsed example gallery, inspect variables and missing values.
- **Data preparation**: create new recoded variables, mark missing codes, reverse-score questionnaire items, calculate sums/means, export a working CSV and transformation log without changing source files.
- **Questionnaires**: use Build/Preview/Fill/Responses to create multi-page questionnaires grouped by topic, label Likert choices with readable text while storing numeric scores, drag questions to reorder, preview skip logic and export responses with a codebook.
- **Descriptive**: choose a variable, confirm its scale, and view statistics and a graph.
- **Scale reliability**: calculate Cronbach’s α and one-factor standardized McDonald’s ω, inspect corrected item-rest correlations, item loadings and diagnostic plots.
- **EFA / PCA**: compare principal components with principal-axis exploratory factors, KMO/Bartlett checks, scree/parallel analysis and loading matrices.
- **Correlations**: analyze two variables with Pearson or Spearman and view the scatterplot.
- **Correlation matrix**: compare up to eight variables in a heatmap with pairwise N.
- **Compare groups**: compare two independent groups with Welch’s t or Mann–Whitney U, APA-style results and boxplots.
- **Paired measures**: analyze repeated before/after observations with paired t or Wilcoxon, plus a participant-level change plot, compact results and local exports.
- **Chi-square**: analyze two categorical variables, inspect observed/expected counts, Cramér’s V and sparse-table cautions.
- **ANOVA / Kruskal**: compare 3–8 independent groups, review effect estimates, group distributions and omnibus cautions.
- **Linear regression**: fit a model with one to five quantitative predictors, inspect coefficients, residuals, multicollinearity, influence and optional robust standard errors.
- **Logistic regression**: model a binary 0/1 outcome, inspect odds ratios with 95% CIs, likelihood-ratio test and in-sample ROC/calibration diagnostics.
- **ANCOVA / GLM**: compare 2–6 independent groups controlling for quantitative covariates, inspect group-by-covariate interactions, adjusted means and Holm-adjusted group contrasts.
- **Repeated measures**: Friedman or Greenhouse–Geisser-adjusted repeated-measures ANOVA, paired Holm comparisons and individual trajectories.

Use **Dataset** first. Switching between sections preserves analysis results until a new dataset is loaded. The calculation modules and the local-data privacy approach have not changed.

## What changed in the current interface

The desktop workspace now keeps **Copy report**, **Save TXT as...** and **Save PNG as...** above the scrolling analysis panel. After completing an analysis, use these buttons to copy its APA-style text or choose a destination in the Windows Save dialog. **Nothing is uploaded to a cloud service.** The toolbar applies to descriptive statistics, reliability, correlation, correlation matrix, independent/paired tests, chi-square and ANOVA/post-hoc.

After loading a fresh dataset the previous output buttons are cleared. Switching sections preserves the last completed result for each analysis. For ANOVA, run **post-hoc comparisons** before exporting to include the updated pairwise table in the APA TXT file.

**Explore boxplots:** Open **Descriptive → Explore**. Choose a quantitative outcome and optionally a grouping variable (for example `score` and `group` from **Load three-group example**). Click **Explore distributions** to display group boxplots, individual observations, a normal Q–Q plot and Shapiro–Wilk. With groups selected, it also computes a median-centered Levene/Brown–Forsythe variance check. Review the caveats; **a nonsignificant Shapiro test does not prove normality**.

The menu is grouped by purpose, the export controls stay visible while scrolling, ANOVA figures are above long explanations, methodological notes can be collapsed, and the post-hoc comparisons display in a table. See [ROADMAP.md](ROADMAP.md) for remaining SPSS-style methods, planned localization (EN, LV, RU) and the Flet versus PySide6 decision.

## Questionnaire builder: pages and labeled scales

In **Questionnaires → Build**, load the fictional Psychology template to see a three-page example (Introduction, Background, Stress scale). Edit each question's **Topic / section**, **Page number** (consecutive starting at 1) and **Page title**. Repeated questions on a page share its heading. Respondents navigate with **Previous / Next**; the next page is only shown after current-page required and conditional answers are valid. Preview does not store answers. The desktop app still collects responses only on the local computer; it does **not** produce a public survey link.

For a Likert 1–5 or 1–7 item, select Agreement, Quality or Frequency and click **Use preset labels**, or type one line per response code, such as:

```text
1 = Очень плохо
2 = Плохо
3 = Средне
4 = Хорошо
5 = Очень хорошо
```

Every score needs a nonempty distinct text label. Participants see **1 — Очень плохо** etc.; the stored CSV and Dataset column still contain **1, 2, 3, 4, 5** as numeric values. The JSON codebook preserves all visible labels, page/section names, ordinal measurement metadata and reverse-key marks. For older saved questionnaires without full labels, numeric choices and any existing endpoint anchors remain usable.

Drag the question list handle to reorder questions, or use **Move up / Move down** for keyboard accessibility. To move **whole topic sections**, use **Reorder entire topic sections**, select a page and drag a section (or use the ↑/↓ buttons); moves violating page order or conditional dependencies are rejected. The question editor now uses responsive columns and stacks beneath the question list in narrower windows. Existing published questionnaires and responses are not modified; use **Clone** to make a revised draft.

**Custom numeric / semantic differential scales:** Choose **Custom numeric / semantic differential**, enter 2–11 labeled integer codes such as `-3 = Very difficult`, `0 = Neutral`, `3 = Very easy`. The **Use bipolar example −3…3** button provides a fictional demonstration. Codes may be nonconsecutive, but they are treated as **ordinal**, not automatically interval-level measurements; never assume the differences between codes are psychologically equal.

**Explicit non-scored answers:** On Likert or custom numeric items, enable **Don't know** (code `DK`) and/or **Prefer not to answer** (code `PNA`) and edit their respondent-facing labels. These codes are **not scale scores**. Raw SQLite answers preserve `DK`/`PNA` for audit. Exported CSV/Dataset instead has a numeric score column containing missing values (`NaN`) and a separate `<variable>__missing_reason` column containing `DK` or `PNA`. The JSON codebook records codes, labels and the reason-column name. Even for a required question, selecting a documented explicit missing option satisfies the response requirement but does not contribute a scale score. Hidden conditional answers remain null. Do not replace missing options with arbitrary extreme numeric scores.

**Scope:** sections and pages, custom integer-coded ordinal ratings and explicit missing reasons are implemented; hosted respondent links, multi-language per-answer switching, advanced page randomization and HR CV/file uploads are not. CV uploads would require separate access, consent, storage/retention and deletion safeguards. Research data continues to stay local.

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

The implementation uses [statsmodels](https://www.statsmodels.org/) for OLS estimation. Friedman and one-factor repeated-measures ANOVA are available separately in the **Repeated measures** workspace.

## Friedman and repeated-measures ANOVA (Step 13)

In **Dataset**, choose **Load repeated example** (`examples/sample_repeated.csv`). Open **Repeated measures** from the sidebar.

The example represents 32 fictional participants measured on three occasions, with 31 complete sets of scores. Each selected column is one occasion of the **same construct**; the application assumes **one participant per row**. Choose `stress_before`, `stress_mid` and `stress_after` in the intended chronological order.

For ordinal responses, confirm **Ordinal** and select **Friedman test**. For suitable quantitative scores, confirm **Quantitative** and select **Repeated-measures ANOVA**. Check both the same-participants/design confirmation and the assumptions confirmation, then choose **Analyze repeated scores**.

Outputs include the omnibus statistic and sample size, Kendall’s W (Friedman) or partial η² (RM ANOVA), the occasion descriptives, a participant-trajectory figure and all paired comparisons with **Holm-adjusted** p-values. Friedman uses tie-corrected SciPy χ² and Wilcoxon signed-rank post-hoc. RM ANOVA uses Greenhouse–Geisser-corrected degrees of freedom for its **primary** p-value, and paired t tests for post-hoc comparisons. The uncorrected RM ANOVA p-value is shown separately.

Use the shared **Copy report**, **Save TXT as...** and **Save PNG as...** toolbar.

**Limitations:** no Mauchly sphericity test, no adjusted simultaneous confidence intervals and no mixed-effects handling of incomplete repeated observations. Participants with any missing selected occasion are excluded. Paired tests assume the selected timepoints describe the same people; choose other analyses for independent groups. These are synthetic examples, not evidence of treatment effects.

## Binary logistic regression (Step 14)

In **Dataset**, choose **Load logistic example** (`examples/sample_logistic.csv`). Open the new **Logistic regression** section. The example has 210 fictional participants, of whom 208 have complete information. The dependent variable is `wellbeing_improved`, explicitly coded **0 = no event** and **1 = event**. Select `sleep_hours` and `activity_hours` as quantitative predictors.

Confirm that you reviewed independent observations, event coding, whether the predictors really are quantitative, the linearity of continuous predictors on the **log-odds** scale and the study design. Click **Fit logistic model**. A single checked predictor fits a one-predictor model; multiple checked predictors fit a multivariable model (maximum five).

**Results** include an overall likelihood-ratio χ² and p-value, sample/event counts, McFadden pseudo-R², AIC, and each coefficient's B, SE, z, Wald p-value, **odds ratio (OR)** and **95% OR confidence interval**. The ROC curve, fitted-probability distribution and descriptive calibration plot are calculated on the *same training observations*. Use **Copy report**, **Save TXT as...** and **Save PNG as...** in the common toolbar.

**Limitations and safeguards:**

- OR is an odds ratio, **not** a relative risk or probability change. One-unit increments use the original predictor units.
- McFadden pseudo-R² does not represent the fraction of outcome variance explained.
- In-sample ROC AUC and calibration are optimistic. **No external validation, cross-validation, threshold optimization or clinical decision accuracy** is claimed.
- Predictors must be meaningful quantitative measurements; integer codes for nominal categories must first be properly encoded. Only binary outcome values 0 and 1 are accepted; no automatic category guessing.
- A row represents an independent observation. Repeated/clustered observations need other methods. Listwise missing-value deletion applies.
- The program checks convergence, obvious perfect separation, nonsensical outcomes, singular predictors and extreme coefficients. **Quasi-separation and model misspecification may still occur.** Researcher review is required.

This example is synthetic and cannot establish psychological or behavioral causal effects. The report is an APA 7-style draft, not a certified publication-ready output.

## ANCOVA and General Linear Model (Step 15)

In **Dataset**, select **Load ANCOVA example** (`examples/sample_ancova.csv`). Open the new **ANCOVA / GLM** screen. Use `wellbeing` as the quantitative outcome, `group` as a categorical factor (A, B or C), and `age` plus `baseline_score` as quantitative covariates. The example has 180 fictional records, 179 complete cases. Confirm independent observations, valid measurement scales, covariate timing, plausible linearity and outlier review. Click **Run ANCOVA / GLM**.

**Mode 1: ANCOVA (common slopes).** Fits an additive ordinary least squares model. Before reporting an adjusted group F-test, the program fits a group × covariate model and performs a joint F-test for differences in slopes. If the interaction is significant at the .05 threshold, **the common-slope ANCOVA is blocked**. Switch modes and interpret the conditional interaction model instead; do not treat a nonsignificant interaction as proof of identical slopes.

**Mode 2: GLM (group × covariate interactions).** Fits a **Gaussian General Linear Model** with each covariate's interaction with the group factor. This is not a *generalized* linear model such as logistic or Poisson regression. Because slopes may differ, the displayed group F-test, adjusted means, and pairwise contrasts describe differences **only at the observed complete-case grand mean of each covariate**; they are not constant effects across all covariate values.

The output includes a group F-test and p-value, partial η², R², a slope-interaction F-test, the complete-case sample size, adjusted means with individual 95% confidence intervals, all group comparisons with **Holm-adjusted p-values**, a fitted-lines figure, and residual Shapiro–Wilk, median-centered Levene and Cook's D summaries. Pairwise **95% confidence intervals are unadjusted**, unlike the adjusted p-values. For multiple covariates the graph holds all but the first covariate at the observed reference mean. Use the shared **Copy report**, **Save TXT as...**, and **Save PNG as...** controls.

To check the guard against invalid common-slope inference, choose **Load interaction example** (`examples/sample_ancova_interaction.csv`) and try common-slope ANCOVA. The dataset intentionally has differing age slopes. Switch to **GLM (group × covariate interactions)** to estimate conditional contrasts.

**Important limitations:** All analyses use listwise-complete cases and ordinary OLS model assumptions. Adjusted predictions may extrapolate if the groups have little overlapping covariate range; the program reports a warning. Covariates are assumed to be quantitative and selected deliberately: a numeric storage type alone does not establish scale. Covariates measured after a treatment may introduce bias. This first version supports **one** group factor and **one to three** covariates, not factorial ANOVA, multivariate outcomes, repeated observations, or generalized GLMs. The results do not demonstrate causation. The report is an APA-style draft requiring researcher review.

## Data preparation and locally collected questionnaires (Step 16)

### Data preparation

1. Open **Dataset → Load scale example** (`examples/sample_scale.csv`), then click **Data preparation** in the sidebar.
2. Choose **Reverse-score an item** and select `stress_q2`; name the new variable `stress_q2_reverse`. Confirm a scale minimum of **1** and maximum of **5**, then click **Apply transformation**. For 1–5, the formula is `6 - response`. **Reverse a real instrument item only when its scoring key requires it**; the fictional example is for practicing the interface.
3. Choose **Create mean/sum scale score**, select `stress_q1`, `stress_q2_reverse`, `stress_q3`, `stress_q4`. Name the variable `stress_mean` and select **Mean** with a minimum of **3 answered items**. A person with fewer than 3 valid responses receives a missing scale score. **Sum** requires all selected items to be observed.
4. For imported surveys that code missing values as `99` or `-9`, use **Mark missing-value codes** before reverse scoring or summing. To recode categories, choose **Recode values** and enter exact pairs such as `No=0;Yes=1` separated by semicolons. Select explicitly whether unmatched values remain unchanged or become missing.
5. Choose **Use working copy in analysis** to send the prepared table to the existing statistics screens. Choose **Save prepared CSV + steps JSON** to select a new CSV destination. A matching `_steps.json` file documents the exact transformation rules.

**Important:** Operations add new columns and never modify the existing source columns. The original CSV/XLSX is not changed. The program blocks export to the exact original file path. It does not silently infer reverse-coded items, scoring rules, or why a value is missing. Always verify the questionnaire manual and sample characteristics before scientific analysis.

### Questionnaire builder: focused four-view editor (Step 17)

The questionnaire section now has **four tabs** rather than one long page.

1. **Build.** Choose a study title and introduction, then start from a **Psychology/Likert**, **Demographics**, **HR/Workplace** or **Marketing/Feedback** fictional template, or add questions manually. Use the left-hand question list and right-hand properties panel to **edit, duplicate, reorder, delete** and save questions to a draft. Changing a question's key can invalidate conditions in later questions; the editor prevents saving an inconsistent draft.
2. **Preview.** Inspect how the respondent will see sections, instructions, answer scales and conditional questions. Preview answers are **not saved**.
3. **Fill survey.** Choose an already published local questionnaire, enter responses and submit them into the same on-device SQLite survey database. Saved questionnaire definitions are immutable to protect collected response data. **Clone** an existing questionnaire to create and edit a new version without altering the original.
4. **Responses / Export.** Preview the first ten rows and first seven columns, transfer the full response table directly to **Dataset** or export the complete **CSV + JSON codebook**. The codebook records prompts, response types, option labels, scale IDs and reverse-key flags.

Available response types: **Likert 1–5, Likert 1–7, single choice, multiple choice, Yes/No, numeric answer, short/long text, ISO date and required consent checkbox**. Questions can be assigned to named sections such as *Consent*, *Demographics*, *Stress* or *Feedback*. Optional lower/upper response anchors clarify Likert interpretation.

**Simple conditional logic:** For a question, select an **earlier** single-choice, Yes/No, Likert or numeric response, choose *equals*, *not equals*, *greater than* or *less than*, and enter a valid value. For example, ask `work_years` only when `employed` equals `Yes`. Hidden required questions are automatically skipped; responses to hidden questions are saved as **null**, never as zeros or stale values. There is no arbitrary code or executable formula in conditions. Complex AND/OR, pages, randomization and clinical triage are **not implemented**.

**Reverse-scored items:** Mark a Likert question as reverse-scored and assign its scale/subscale ID, such as `stress`. The mark is included in the JSON codebook; **raw answers are not modified or scored automatically**. Researchers must check the official test scoring key and then use **Data preparation** to create a reverse-coded column and construct a validated scale score. The fictional templates are not validated psychological tests.

**Quick smoke test:** In **Questionnaires → Build**, select **Psychology / Likert**, click **Load template**, inspect `stress_q2` as a reverse-keyed item, and inspect `work_years`, which depends on `employed = Yes`. Click **Preview draft** and change `employed` from `Yes` to `No`; the `work_years` question should disappear. Publish the draft using **Create local questionnaire**, fill a couple of *fictional* responses in **Fill survey**, then use **Responses / Export**.

**Privacy and scope:** The builder and respondent form work locally on the current computer; there is still **no public survey link or remote multi-user hosting**. Data are in SQLite under Git-ignored `data/surveys/`, not encrypted at rest. No automatic IP logging or third-party survey account is used, but the presence of random response IDs does **not automatically make personal or sensitive responses anonymous**. Collecting health-related or identifiable research data requires a legal basis, data-protection controls and potentially ethics approval. The exact requirements depend on the research and institution. The next major milestones are secure deployment, EN/LV/RU respondent-facing language support, more complete consent/withdrawal controls, and **AI-assisted photo/PDF-to-draft import with human review**.

## Scale psychometrics: omega, item diagnostics, EFA and PCA (Steps 18–20)

### McDonald's omega and corrected item-rest analysis

In **Dataset**, click **Load scale example** (`examples/sample_scale.csv`). Open **Scale reliability**. Select `stress_q1`, `stress_q2`, `stress_q3`, `stress_q4`, confirm that all items measure one construct and the direction of any reverse-keyed item has been checked, and select **Calculate McDonald’s ω + item analysis**.

The original **Cronbach’s α** button remains available. Omega is calculated from a **single-factor maximum-likelihood factor model on the Pearson correlation matrix**, using standardized loadings and item uniquenesses:

`ω = (Σ standardized loadings)² / [(Σ standardized loadings)² + Σ uniquenesses]`.

The output shows standardized **one-factor ω**, N and listwise exclusions, per-item M/SD, missing counts, observed category counts, both **Pearson and Spearman corrected item-rest correlations** (each item compared with the sum of the *other* items), standardized factor loadings, uniquenesses and a two-panel PNG. The two item-rest coefficients share the same listwise-complete sample. Spearman is rank-based and supports ordinal exploration, but it is **not a polychoric correlation**. Report export uses the common Copy/TXT/PNG toolbar.

**Optional omega 95% CI.** For a more stable illustration, open the fictional **`examples/sample_omega_bootstrap.csv`** (240 rows, four related `wellbeing_q` items) through **Dataset → Open CSV / Excel** rather than relying only on the 30-complete-case scale example. In the Scale reliability panel choose **Omega 95% bootstrap CI → 200 (exploratory)** or **500 (more stable)** before calculating. The program resamples **whole participants with replacement**, refits the one-factor maximum-likelihood model on each resample, and displays the two-sided **percentile** 95% CI. The sampling seed is fixed for reproducibility. If fewer than 90% of refits produce acceptable estimates, it refuses to report a CI; the point estimate and item results are retained. These are *percentile bootstrap intervals*, not BCa or model-based likelihood intervals, and they depend on the model and an independent-sample design. Allow additional time for the fits. For publication, evaluate bootstrap precision and model assumptions independently; 200 resamples is intended for testing and exploration.

**Method limitations:** This is NOT a multifactor omega hierarchical estimate, and raw ordinal Likert categories are approximated as numeric Pearson variables. Omega cannot itself establish factor model fit, unidimensionality, validity or clinical reliability. An optional bootstrap percentile CI is supported, but not automatically enabled; the default point estimate alone has no CI. Reversed questions must be recoded deliberately using **Data preparation** and an authorized questionnaire scoring key. The application flags negative item-rest associations but does not remove or flip items automatically. For this pilot model, at least 3 selected items, 30 complete cases and approximately 5 complete observations per item are required.

### Exploratory EFA / PCA

In **Dataset**, choose **Load factor example** (`examples/sample_factor.csv`), then open **EFA / PCA**. The six item variables are preselected; choose **2** components/factors and confirm the measurement assumptions.

- **PCA** decomposes the standardized Pearson **total variance** into orthogonal components. Its loading matrix and the fraction of total standardized variance explained are provided. PCA is not latent factor analysis.
- **EFA** fits a **principal-axis common-factor model** on the same Pearson correlations, with one to five researcher-selected factors, fewer than the number of items. Optional **varimax** assumes orthogonal factors; **oblimin** allows correlated factors and requires at least two factors. It reports factor loadings and item uniquenesses, not the same total-variance percentages used for PCA. Under oblimin it additionally shows the **factor correlation matrix (Phi)** and the **structure matrix**; pattern and structure coefficients should not be interpreted as interchangeable.
- Both methods provide **Kaiser–Meyer–Olkin** overall/item measures, **Bartlett's test of sphericity**, a correlation-matrix scree plot and a reproducible **PCA parallel-analysis reference** (150 independently simulated normal datasets, fixed random seed, 95th-percentile eigenvalues). The heuristic is **not an automatic EFA factor-retention rule**.
- The chart and full exploratory report can be copied/saved with the existing toolbar. EFA is exploratory, not a substitute for confirmatory factor analysis and independent sample validation.

**Cautions:** For the current implementation, 3–12 variables and at least max(60, 8 × number of items) listwise complete cases are required. Standard Pearson correlations may be inappropriate for strongly ordinal or skewed items; a future polychoric option is planned. KMO/Bartlett significance does not prove that an interpreted factor structure is stable or meaningful. Multidimensionality, polychoric EFA for ordinal scales, uncertainty intervals for factor estimates and subgroup measurement invariance still need further research-method support. The sample file is synthetic and cannot establish the properties of a real psychological scale.

### Survey editor follow-ups

The current local questionnaire editor still needs **drag-and-drop ordering**, better responsive spacing and **custom labeled rating anchors/options**, so respondents can choose readable answer text such as *Очень плохо, Плохо, Средне, Хорошо, Очень хорошо* while the research dataset stores stable numeric codes `1–5`. These are **planned**, not yet available. Reverse-keyed metadata is already supported; it does not change raw responses.

## Interface languages

The application currently uses **English (EN)**. **Latvian (LV)** and **Russian (RU)** are explicitly planned in [ROADMAP.md](ROADMAP.md). A future language selector should translate menus, messages, cautions and report narratives, not just button labels. APA 7 statistical symbols remain unchanged across languages.

## Privacy and analysis notes
- Keep actual participants' data in the ignored `data/` folder. Do not commit identifiable research data.
- Numeric codes such as 1–5 can represent ordinal Likert responses or categorical groups. A numeric data type is not enough to determine the measurement scale or justify a statistical test.
- The current version inspects datasets and calculates selected statistics and correlation tests. It does **not** automatically validate assumptions, establish causality or replace professional interpretation.

Developed as a learning project, with AI assistance for code explanations, documentation and debugging.
