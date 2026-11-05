# Stage 33 — Research workspace UX/UI specification

Status: **proposal + working prototype, not an approved design.** The
workspace described here runs in the application as a clearly marked
*preview* next to the unchanged classic interface. Nothing in this document
is final until the product owner has evaluated it on a real Windows PC.

Related: Issue #19 (Stage 33 UX/UI), Issue #20 (Brief COPE import, separate
branch), `ROADMAP.md`, generated classic inventory
[`docs/stage33/CLASSIC_INVENTORY.md`](stage33/CLASSIC_INVENTORY.md),
route map [`workspace_routes.py`](../workspace_routes.py).

Contents

1. Goals and constraints
2. Audit of the current application
3. Users and jobs
4. Two UX concepts and a rejected third
5. Comparison for beginners and experienced researchers
6. Recommended combined design
7. Information architecture and routes
8. Key journeys
9. Screen specifications
10. Design system: tokens and components
11. Accessibility, responsive layout, high DPI and localization
12. Scientific safeguards in the interface
13. Desktop and web: secure respondent interface proposal
14. Brief COPE linkage (Issue #20)
15. Implementation plan
16. Verification evidence
17. Appendix A: feature parity matrix
18. Appendix B: critique of the reference screenshots

---

## 1. Goals and constraints

**Mission.** Help psychology, sociology, education and humanities students
and researchers investigate questions and hypotheses without SPSS
expertise. The application does the computation and makes decisions,
assumptions, uncertainty and results understandable.

**Hard constraints** (from Issues #19/#20 and the existing safeguards):

* Every statistical and psychometric feature stays available; no dead ends.
* Calculation modules are not rewritten; results must equal the validated
  engine exactly (enforced by `tests/test_analysis_runs.py`).
* No invented results, scoring rules, citations or project saving.
* Research data stays on the computer by default; no automatic uploads, no
  silent change of a published questionnaire.
* The old interface stays until replacements pass tests.
* Flet 1.x desktop remains the analysis client in Stage 33.

---

## 2. Audit of the current application

### 2.1 Method

1. **Generated inventory.** `tools/ux_inventory.py` builds the real classic
   workspace (`research_app.main`) on a fake page and walks the Flet control
   tree. It lists every screen, command, import/export, choice, input,
   confirmation and section, the top menu and the registered actions:
   17 screens, 8 menu groups with 22 commands, 34 actions (incl. the new
   preview entry). Output: `docs/stage33/CLASSIC_INVENTORY.md` and `.json`.
2. **Code review** of `interface_layout.py`, `research_app.py`,
   `survey_ui.py`, `preparation_ui.py`, `interpretation_ui.py`,
   `spatial_review_ui.py` and the reporting/export modules.
3. **Screenshot review** of the classic screens in Flet web mode
   (`docs/images/stage33/classic_*.png`).

### 2.2 Inventory summary

| Area | Classic screens | Notable controls |
|---|---|---|
| Start | Home | 3 start cards, sample data, privacy note |
| Data | Dataset, Data preparation | CSV/TSV/XLSX/XLSM import with sheet/header/data-start/separator/decimal/encoding/missing options, diagnostics, recent files, full-path fallback, 11 sample datasets; recode, reverse-score, missing codes, mean/sum scale scores with history and CSV + steps JSON export |
| Questionnaires | Questionnaires (4 tabs: Build, Preview, Fill, Responses) | 40 commands, 43 inputs: templates, sections/pages, 11 answer types, value labels, DK/PNA, conditions, reorder, scientific importer (source page, OCR, regions, shared scales, binary formats, matrix editor, review queue), publish, local responses, CSV + codebook |
| Analysis | 13 method screens | Descriptive/Explore, α, ω (+bootstrap), EFA/PCA, correlation, matrix, two groups, paired, χ², ANOVA/Welch/Kruskal + post-hoc, regression, logistic, ANCOVA/GLM, repeated measures; each with its own measurement-level confirmation and assumption checkboxes |
| Output | Global "OUTPUT" bar on analysis screens | Copy, Save TXT, Save PNG (APA 7 figure), APA 7 interpretation wizard (4 steps, Word export) |
| Chrome | Sidebar (4 collapsible groups), top menu bar, compact dropdown < 1060 px | Language, Windows/macOS corner style, OCR status, privacy, "AI assistant: not connected" |

### 2.3 Findings

Severity: **H** = blocks or misleads users, **M** = slows or confuses,
**L** = polish.

| # | Finding | Evidence | Severity |
|---|---|---|---|
| F1 | **Three navigation systems**: sidebar (17 entries in 4 groups), top menu (8 groups, 22 commands, partly duplicating the sidebar; "Analysis" lists only 5 of 13 methods), and a compact dropdown. Users must learn which one is complete. | `interface_layout.py` sidebar, `MenuBar`, `compact_navigation` | H |
| F2 | **Method-first navigation.** A beginner must already know that "group differences" + "Mann–Whitney vs Welch" is the right screen; the existing recommendation text appears only *after* picking the screen and the method. | `groups_screen`, `recommend_group_test` | H |
| F3 | **Measurement level re-confirmed on every screen** (descriptive, correlation X/Y, groups, paired, omnibus, repeated). The same variable can be "ordinal" on one screen and "quantitative" on another, and the user repeats the decision 6×. | `scale`, `corr_scale_x/y`, `group_outcome_scale`, `paired_scale`, … | H |
| F4 | **Only the last result per screen is kept.** Running Kruskal–Wallis after Welch ANOVA silently replaces the first result and its interpretation evidence; comparing methods requires exporting in between. | `output_cache[section]`, `evidence_cache[section]` | H |
| F5 | **Two different export paths.** Paired, χ² and omnibus screens have their own "Save figure PNG / Save APA report TXT" buttons that write fixed file names into the program folder (`reports/`) and overwrite earlier files; the global bar asks for a location. In a packaged build the program folder can be read-only or hard to find. | `report_export.save_apa_txt/save_figure_png`, inventory exports | H |
| F6 | **Long single-column screens**: setup, result, figure, full report, cautions and glossary are stacked; results appear far below the Run button; figures are fixed-size bitmaps (e.g. 1080×440) that overflow or shrink on laptops. | `ft.Image(width=1080, height=440)` | M |
| F7 | **Dense questionnaire build view**: the scientific importer (source, edit, shared scales, binary formats, confidence, regions, review queue, matrix editor) is an expansion tile *inside* the builder's step list — 33 commands in one scrolling column. Issue #19 asks for a focused task workspace. | `survey_ui.build_view` | H |
| F8 | **Small and all-caps text**: 83 occurrences of 11–12 px text in the four main UI modules; dense all-caps headers ("YOUR RESEARCH WORKSPACE", "CURRENT DATASET", "OUTPUT", "RESPONSE SCALE REVIEW · shared answer categories"). | grep of `size=11/12` | M |
| F9 | **Hard-coded colours** (~150 hex literals across UI modules) and no dark theme; "macOS" appearance changes only corner radius and switches the font to Arial (not the macOS system font). | `interface_layout.py`, `research_app.py` | M |
| F10 | **Significance dichotomies in tables**: post-hoc, repeated and ANCOVA pair tables add a "Sig. Yes/No" column from p < .05 — encourages dichotomous reading. | `research_app.py` table builders | M |
| F11 | **Import options before a file exists**: worksheet, header row, separator, encoding, decimals and missing markers are shown permanently on the Dataset screen; beginners see seven technical fields before their data. | `import_panel` | M |
| F12 | **Eleven sample buttons** in one row without saying which analysis each supports. | Dataset "Try a fictional example dataset" | L |
| F13 | **A top-level menu for a feature that does not exist** ("AI assistant" → status "not connected"). Honest, but noise in primary navigation. | `MenuBar` | L |
| F14 | **Language and style pickers occupy prime sidebar space** although they are rarely changed. | sidebar | L |
| F15 | **Raw exception text** shown as the result ("Regression error: …"). | callbacks | L |
| F16 | **The interpretation wizard is hidden** inside the output bar and tied to the last result of the visible screen. | `InterpretationWizardView` | M |
| F17 | **No keyboard shortcuts**; drag-and-drop reorder exists without a visible keyboard alternative next to it in the builder. | `ReorderableListView` | M |
| F18 | **Engine limits are discovered by failing** (ω: 3–12 items and ≥ 50 complete cases; EFA: 3–12 items; matrix: 2–8 variables; repeated: 3–8 columns; regression/logistic: 1–5 predictors; ANCOVA: 1–3 covariates, 2–6 groups). | engine `ValueError`s | M |

Good foundations to keep: conservative engine reports with explicit
cautions, separate scientific confirmations, local-first storage, the
validated importer pipeline, bundled offline OCR, and the startup splash.

---

## 3. Users and jobs

| Persona | Context | Needs | Risk to avoid |
|---|---|---|---|
| **Beginner (student)** | Thesis question, Google Forms/Qualtrics export or own questionnaire, little statistics | "Which test? Why? What do I check? How do I write it up?" | Choosing a test by habit or by one normality p; over-claiming significance |
| **Experienced researcher** | Knows methods, wants speed and control | Direct access to every method/option/diagnostic, comparison of methods, exports | Hand-holding that hides options; losing earlier results |
| **Supervisor / reader** | Reviews outputs | Provenance: data, variables, options, confirmations, time | Untraceable numbers |
| **Respondent** (future web) | Phone or laptop | Accessible, short, consent and privacy | Data exposure, silent changes |

Core jobs: J-Data (bring and understand data), J-Prepare (recode/reverse/
score without destroying the original), J-Ask (turn a question into a
method), J-Understand (estimate, uncertainty, cautions), J-Report (APA text,
tables, figures, Word), J-Build (questionnaire from scratch/template/
scientific PDF/DOCX), J-Collect (local responses → dataset).

---

## 4. Two UX concepts and a rejected third

### 4.1 Concept A — "Research journey" (guided, linear)

A study is a sequence of five stages shown as a horizontal stepper:
**Question → Data → Check → Analyze → Report.** Each stage is one focused
screen with one primary action; the app keeps a *decision log* (question,
variables, levels, design answers, chosen method and why).

* Question templates ("compare groups", "change over time", "relationship",
  "predict", "scale quality", "structure", "describe") drive variable roles.
* A deterministic advisor recommends a method from design + confirmed
  levels, with alternatives and the checks still to make.
* Results are a narrative page ending in "Add to report".

Wireframe (desktop ≥ 1280):

```
┌ Question ─ Data ─ Check ─ Analyze ─ Report ┐   ← stepper (current stage bold)
│                                            │
│  What do you want to find out?             │
│  [Compare groups] [Change] [Relationship]  │
│  [Predict] [Scale] [Structure] [Describe]  │
│                                            │
│                        [Back]   [Continue] │
└────────────────────────────────────────────┘
```

### 4.2 Concept B — "Research workbench" (object-centric, multi-pane)

A persistent three-pane workbench: left **project explorer** (data
sources, variables, questionnaires, analyses, outputs), centre **editor**
(data grid, method dialog, questionnaire editor), right **inspector**
(properties, assumptions, diagnostics, help), bottom **output log** with
every result. A command palette (Ctrl+K) opens any of the 15 analyses.

```
┌Explorer────┬ Editor ─────────────────────┬ Inspector ─┐
│ Data       │ Two independent groups      │ Outcome    │
│  survey.xlsx│ Outcome [stress ▾]         │  ordinal   │
│ Variables  │ Group   [gender ▾]          │ Checks     │
│ Analyses   │ Method  (•) Mann–Whitney    │  ☐ indep.  │
│ Outputs    │ [Run]                       │ Help …     │
├────────────┴─────────────────────────────┴────────────┤
│ Output log: 1. Mann–Whitney U … 2. Welch t …          │
└───────────────────────────────────────────────────────┘
```

### 4.3 Rejected Concept C — "Research notebook"

Cells (data, question, analysis, narrative) accumulate into a document,
like JASP's results pane or a Jupyter notebook. Rejected because it
implies project persistence (not implemented, not allowed to be claimed),
produces exactly the long scrolling pages users dislike, and mixes editing
with reading.

---

## 5. Comparison for beginners and experienced researchers

**Novice scenario** (Issue #19 acceptance): an Excel export with
`stress_q1` (1–5 answers) and `group` (A/B); "Do the groups differ?" →
APA result and Word report. Meaningful decisions are counted; required
scientific confirmations (measurement level, independence) are not.

| Step | Classic | Concept A | Concept B | Combined (prototype) |
|---|---|---|---|---|
| Open file | 1 | 1 | 1 | **1** |
| Find the analysis | 2 (expand "Group comparisons", choose screen) | 1 (question template) | 1 (palette search — needs a method name) | **1** (goal "Compare groups") |
| Variables | 2 | 2 | 2 (drag) | **2** |
| Method | 1 (Mann–Whitney vs Welch, needs knowledge) | 0 (recommended) | 1 | **0** (recommended, alternatives shown) |
| Run | 1 | 1 | 1 | **1** |
| Reach the answer | scroll + read | 0 | open output | **0** (Results opens) |
| Word report | 3 (open wizard, step through, export) | 1 | 2 | **1** |
| **Decisions to answer / to Word file** | **7 / 10** | **5 / 6** | **6 / 8** | **5 / 6** |

**Expert scenario**: Welch ANOVA with post-hoc on three groups, then
Kruskal–Wallis as a robustness check; export both.

| Criterion | Classic | A | B | Combined |
|---|---|---|---|---|
| Direct access to any method | ✓ (sidebar) | ✗ (through templates) | ✓✓ (palette) | ✓ ("All methods" catalog, search, form) |
| Both results kept side by side | ✗ (F4) | ✓ | ✓ | ✓ (results log) |
| All options and diagnostics | ✓ | partial | ✓ | ✓ (same options as classic) |
| Keyboard speed | ✗ | ✗ | ✓ | ✓ (Ctrl+1…6, Ctrl+Enter, Ctrl+O) |
| Cognitive load on first use | high | low | high | low (guided default) |
| Fits 1024 px laptops | ✗ | ✓ | ✗ (three panes) | ✓ (panes collapse) |
| Iterating back to data | ✓ | ✗ (linear) | ✓ | ✓ (areas, not a wizard) |

Conclusion: A is best for the first analysis but frustrates iteration and
experts; B is fast for experts but intimidating and too dense for laptops.

---

## 6. Recommended combined design — "Research workspace"

* **Areas, not a wizard.** A collapsible sidebar with six areas —
  **Home, Data, Questionnaires, Analyze, Results, Reports** — plus
  Settings and Help at the bottom. No top menu bar (removes F1/F13).
* **Analyze has two modes on one page** that share one engine and one
  variable dictionary: **Guided** (Concept A's four steps on a single
  screen: goal → variables → design check → recommended method) and
  **All methods** (Concept B's catalog with search and a full form for
  each of the 15 classic analyses).
* **One variable dictionary** in Data holds the researcher-confirmed
  measurement level, with provenance (*confirmed in Data / Analyze / bulk*).
  Every analysis reads it (fixes F3); the guided design step can confirm
  missing levels inline.
* **A results log** (Concept B's output log as its own area): every run is
  kept for the session, with estimates, figure, assumptions,
  interpretation, provenance and exports (fixes F4, F5, F16).
* **Reports collects results** in reading order and exports them together
  (plain text today; a combined Word document is planned and labelled so).
* **Questionnaires** is a three-pane list / editor / live respondent
  preview; **Scientific import** is a focused source / review / preview
  task workspace with a blocking checklist (fixes F7).
* **A context bar** shows the active dataset (rows, variables), how many
  measurement levels still need confirmation, a "Local only" privacy chip,
  theme and language.

---

## 7. Information architecture and routes

### 7.1 Sitemap

```
Home ─ start actions · current dataset · recent data files · saved questionnaires · how it works
Data ─ summary · variable dictionary · preview · import options · prepare data (classic tools hosted)
Questionnaires ─ builder (list | editor | preview) · published on this computer (collect · export · analyze)
   └ Scientific import ─ source | review (versions, shared scales, items) | preview · checklist
Analyze ─ Guided (goal → variables → design → method) | All methods (catalog → form)
Results ─ log | detail (summary · estimates · APA tables · figure · checks · interpretation · report · provenance · exports)
Reports ─ ordered results · study title · combined export
Settings ─ language · theme · corner style · offline OCR · classic interface
Help & privacy ─ shortcuts · privacy · AI status · prototype note
```

### 7.2 Global chrome

| Element | Size | Content | Behaviour |
|---|---|---|---|
| Sidebar | 232 px / 64 px collapsed | brand + "Preview", six areas with result/report counts, Settings, Help, Classic interface, collapse toggle | Ctrl+B; collapsed items keep tooltips (accessible names) |
| Context bar | 64 px | dataset chip (→ Data), "N to confirm" chip, "Local only" chip with privacy tooltip, theme button, EN/LV/RU switch | always visible |
| Status line | 32 px | last outcome with icon and text | `Semantics(live_region=True)` |

### 7.3 Old → new routes

`workspace_routes.py` maps **every** classic screen, menu command and
action to a destination with an honest status (`workspace`, `hosted`,
`partial`, `classic`, `retired`); `tests/test_workspace_routes` (in
`test_workspace_foundations.py`) fails when the live inventory contains a
command without a destination. See Appendix A.

### 7.4 State and persistence (what is *not* claimed)

The workspace session (dataset, dictionary, results, report order) lives in
memory. Questionnaires and responses persist in the existing SQLite
storage; recent data files in the existing preferences file. **There is no
project saving yet**; Results and Reports say so on screen. A future
`.sra` project format is listed in the roadmap and must ship with tests
before any screen mentions saving a project.

---

## 8. Key journeys

| # | Journey | Prototype status | Automated test |
|---|---|---|---|
| J1 | XLSX → dictionary → guided Mann–Whitney → APA table, figure → TXT/PNG/Word → report | complete | `XlsxToApaReportJourney` (5 decisions to the answer, values = engine) |
| J2 | Scientific PDF → version → shared-scale review → 20 structured items → preview → publish → responses → CSV + codebook → reverse-score → α (20 items) and ω (10 items) | complete | `PdfQuestionnaireToAnalysisJourney` |
| J3 | Data preparation → reverse-scored item → EFA through All methods | complete (preparation by the classic functions) | `PreparationToFactorJourney` |
| J4 | Expert: any classic method with all options, post-hoc, both results kept | complete | parity tests + catalog test (15 methods) |
| J5 | Build a questionnaire with a reusable scale, a condition and drag-and-drop | complete in the builder; page-wise sections still classic | `test_workspace_shell` + manual |

J1 in the prototype: *Open CSV/Excel* → (confirm suggested levels) →
*Compare groups* → *Outcome* → *Group* → (confirm independence) →
*Run Mann–Whitney U* → Results opens with summary, estimates, Table 1,
figure → *Save Word report…*.

---

## 9. Screen specifications

### Home
* Title "What would you like to do?" and a one-sentence promise.
* Four start tiles (equal height): Analyze a dataset (primary; native file
  dialog through a client gesture), Build a questionnaire, Import a
  questionnaire (PDF/Word), Try a sample study.
* Continue: current dataset card (if any) with "Review variables" /
  "Analyze"; recent data files (local preferences, genuinely supported);
  saved questionnaires with response counts (SQLite, genuinely supported).
* "How it works" (4 steps), dismissible. Privacy note.

### Data
* Header action "Open CSV / Excel…". Empty state with sample datasets and
  the full-path fallback (desktop dialog problems).
* Summary tiles: source, rows, variables, missing cells.
* **Variable dictionary**: variable, stored as, suggested level (heuristic,
  says so), *confirmed level* (dropdown), missing, distinct; bulk "use
  suggestions" only with an explicit "I checked these levels against the
  questionnaire or codebook".
* Data preview (12 rows, horizontal scroll). Import options collapsed by
  default (fixes F11) with the classic options and diagnostics.
* Prepare data: the classic non-destructive preparation tools hosted
  unchanged; "Use working copy in analysis" replaces the session dataset
  with a "(prepared)" copy.

### Analyze — Guided
Four step cards on one page; completed steps collapse to a summary state,
locked steps say what is missing.
1. **Goal** — eight plain-language goals.
2. **Variables** — role pickers showing each variable's confirmed level.
3. **Design check** — inline level confirmation (saved to the
   dictionary), data facts ("group has 2 groups: A, B"), and exactly the
   confirmations the engine requires for the proposed method (classic
   wording, verbatim).
4. **Recommended method** — method name with a "Recommended" or "Your
   choice" chip, reasons, alternatives with "Use instead", the note that
   assumptions are not tested automatically and that no normality test
   chooses the method, **Run**, and "Open with all options".

### Analyze — All methods
Search plus the 15 classic analyses grouped as Describe, Questionnaire
scales, Relationships, Differences and change, Models. The form shows
roles, options (classic labels and choices), confirmations, inline level
fixes and engine limits before running. Ctrl+Enter runs.

### Results
* Log (left, 300 px; a picker on compact widths) and detail (right).
* Detail: title + method + dataset, **Add to report**; Summary (engine
  text); Key estimates (verified `AnalysisEvidence` rows: N, statistic,
  effect, CI, p); APA-style tables (number, italic title, horizontal rules;
  "—" for not calculated; no "Sig." column); figure scaled to the pane
  with "Enlarge"; assumptions checklist + limitation + engine cautions;
  conservative interpretation draft (collapsed) with the researcher's own
  note; full report; method and provenance; exports (Copy, TXT, APA PNG,
  Word) through save dialogs only; post-hoc for omnibus results.

### Reports
Ordered list (move up/down, remove), study title, "Export combined TXT…"
(only the engine's report texts and provenance lines), the note that a
combined Word document is planned and that each result has its own Word
export.

### Questionnaires
* Header: Import PDF/Word…, **Publish locally…** (confirmation dialog:
  published wording and collected answers never change).
* Title and participant information; "Unsaved draft" and origin chips.
* List (drag-and-drop, plus move up/down buttons in the editor as the
  keyboard alternative), editor (text, variable name, answer type,
  choices, reusable scale library incl. scales found in the draft, apply to
  the whole section, section, required, "Show only when…"), live preview
  (desktop/phone width, conditions evaluated live, 340 px phone frame).
* Published on this computer: collect a response (dialog), export CSV +
  codebook, analyze responses (→ Data).

### Scientific import
* Source (rendered page, page navigation, "PDF text layer — OCR confidence
  does not apply" or OCR chip, offline OCR for the page, link to the full
  classic review for region edits, matrix grid, 20-page OCR batch).
* Review: instrument/version picker, warnings, shared response scales
  (labels as printed, printed codes, reverse items, three separate
  confirmations, "Not a shared scale"), extracted items with page, type and
  only real attention flags, item detail with source excerpt and wording
  correction.
* Preview of the proposed respondent controls.
* Checklist: version/wording/permissions, item count/order, all scales
  confirmed or declined; blockers listed; **Create editable draft** only
  when nothing blocks.

---

## 10. Design system: tokens and components

### 10.1 Principles
Calm surfaces, one accent, hierarchy by size and weight (not colour),
sentence case, numbers in APA style, status always icon + text, no
decoration that does not carry information.

### 10.2 Colour tokens (`workspace_tokens.py`)

| Token | Light | Dark | Use |
|---|---|---|---|
| canvas | `#F6F7F9` | `#14171C` | window |
| surface | `#FFFFFF` | `#1C2027` | cards, panes |
| surface_alt | `#F0F2F5` | `#232831` | sidebar, tiles, table headers |
| border / border_strong | `#E1E5EB` / `#767F8F` | `#323944` / `#78849A` | dividers / input outlines (≥ 3:1) |
| text / secondary / muted | `#1A202C` / `#404A5A` / `#5B6676` | `#E7EAF0` / `#C0C7D2` / `#9DA7B6` | all ≥ 4.5:1 |
| accent / on_accent | `#1F5BC4` / `#FFFFFF` | `#8AB0F7` / `#0E1830` | primary actions, selection |
| accent_subtle | `#E7EEFB` | `#22314D` | selected nav, info |
| success / warning / danger | `#1C7240` / `#8A5300` / `#B42318` | `#74C996` / `#E9B95C` / `#F2958B` | with subtle backgrounds |

All 25 text pairs meet WCAG 2.1 AA (4.5:1) and all UI pairs 3:1 in both
themes — enforced by `TokenTests`. The Material 3 colour scheme is built
from the same tokens, so stock controls match.

### 10.3 Type, spacing, shape, sizes

| Role | Size/line | Weight | Use |
|---|---|---|---|
| Display | 28/36 | 600 | reserved |
| Title L | 24/32 | 600 | page titles |
| Title M | 20/28 | 600 | method names, section titles |
| Title S | 16/24 | 600 | card titles |
| Body L | 15/24 | 400 | summaries, interpretations |
| Body | 14/20 | 400 | default |
| Label | 13/18 | 500 | controls, table headers |
| Caption | 12/16 | 400 | helper text (minimum size) |

Font: none set — Segoe UI on Windows and the system font on macOS via the
platform; no font files shipped. Spacing: 4-px base, 8-px layout steps
(8/16/24/32/48). Radius: 6 controls, 8 cards, 12 dialogs (+2 for the
"macOS · softer corners" preference). Controls ≥ 40 px high; sidebar
232/64 px; context bar 64 px; content max 1240 px, reading 760 px.

### 10.4 Components (`workspace_components.py`)

| Component | Notes |
|---|---|
| `button` (primary/secondary/quiet) | 40 px, state colours from tokens, PickFiles actions supported |
| `icon_button` | **refuses to build without a tooltip** |
| `chip` (neutral/info/success/warning/danger) | icon + text, clickable chips use ink (keyboard focusable) |
| `notice` | inline message with icon, optional title and actions |
| `card`, `page_header`, `section_label` | sentence-case headings |
| `empty_state` | icon, title, explanation, actions |
| `action_tile` | Home start actions |
| `stat` | key estimate tile (label, value, CI/p detail) |
| `apa_table` | numbered, italic title, horizontal rules only, hides "Sig." |
| `figure` | scales with the pane, white matte in dark mode, enlarge dialog |
| `step_card` | done / active / locked states for the guided flow |
| `segmented` | keyboard-focusable switch (modes, language, theme, preview width) |
| `dropdown`, `text_field`, `checkbox` | token outlines, labels or tooltips always set |
| `respondent_question` | the control a respondent will use, per answer type |

---

## 11. Accessibility, responsive layout, high DPI and localization

**Keyboard.** Ctrl+1…6 areas, Ctrl+B sidebar, Ctrl+O open data,
Ctrl+Enter run, Ctrl+Shift+L theme, F1 help. All interactive elements are
buttons, inputs or ink containers (focusable, Enter/Space). Drag-and-drop
reorder has move up/down buttons (WCAG 2.5.7).

**Screen readers.** Icon buttons and collapsed nav items carry names; the
status line is a live region; figures carry semantics labels; status is
never colour-only.

**Responsive.** ≥ 1280: three panes. 1024–1279: Results list becomes a
picker; builder panes switch with a segmented control. < 1024: single
column. Respondent preview offers a 340 px phone frame.

**High DPI.** Layouts use logical pixels; screenshots at 125 % and 150 %
(`home_ru_150`, `analyze_guided_lv_125`) are part of the suite.

**Localization.** All workspace strings exist in EN, LV and RU with
identical placeholders (`TextTests`); gettext plural rules for LV/RU
(`count_text`); no all-caps strings; long LV/RU text wraps (tiles compute a
common height from the longest text). Method names stay international.
Engine reports stay in English, as before. **LV/RU wording needs review by
native-speaking methodologists before release.**

---

## 12. Scientific safeguards in the interface

* **Same engine, same numbers.** `analysis_runs.py` reproduces the classic
  compositions; `tests/test_analysis_runs.py` drives the classic callbacks
  and requires identical reports and result values for all 15 areas and
  post-hoc (ω optimizer noise below 1e-6 is the only tolerance).
* **Deterministic advice.** `workspace_methods.advise` uses design,
  confirmed levels and group counts only; a test proves that transforming
  the data does not change the advice. Rank alternatives are always offered
  for quantitative outcomes.
* **Confirmations stay explicit** and use the classic wording; the engine
  still refuses missing confirmations.
* **Engine limits shown before running** (F18).
* **No significance theatre**: exact p and CIs, no "Sig." column, no stars,
  no "significant difference" callouts on figures.
* **Provenance** for every result; Word export includes the researcher's
  assumption review state (unchecked items are reported as unreviewed).
* **Questionnaires**: publication is an explicit confirmed step; published
  surveys are immutable; imported drafts stay blocked until scales and the
  checklist are confirmed; numeric codes and reverse keys need separate
  confirmations; no scoring recipe is inferred.

---

## 13. Desktop and web: secure respondent interface proposal

Stage 33 keeps the offline Flet desktop as the analysis client. A
respondent web interface is a **separate product surface**, never the
desktop app exposed through a server.

```
 Researcher PC (desktop app)              Hosted service (EU region)              Respondent
 ───────────────────────────              ──────────────────────────              ──────────
 Questionnaire draft ──(1) publish ──►  Publication API ──► Form store (versioned, signed)
                         signed package       │                   │
                                              ▼                   ▼
                                        Respondent web app ◄─── HTTPS ───── phone / browser
                                              │ (consent, answers)
                                              ▼
 Local SQLite ◄──(3) pull, verify ── Response store (encrypted at rest, retention timer)
            explicit researcher action, authenticated (2)
```

1. **Publish.** The desktop exports an immutable, versioned package
   (schema, consent text, retention policy, study contact) signed with the
   researcher's key; the service rejects unsigned or altered packages. A
   changed questionnaire is a new version; old responses stay attached to
   their version.
2. **Authentication.** Researchers: OAuth 2.0 device flow or passkeys,
   per-study roles. Respondents: anonymous links by default; closed studies
   use single-use invitation tokens; no respondent accounts.
3. **Synchronization** is an explicit action in the desktop ("Fetch new
   responses"), never automatic: TLS, token-scoped API, schema/version
   check, de-duplication by response ID, local SQLite import with an audit
   entry. Deletion on the server after successful import is selectable.
4. **Consent and privacy.** Consent screen first (required), purpose,
   controller, retention period, contact and withdrawal; data minimisation
   (no IP storage, no third-party analytics or fonts); EU hosting; DPIA
   template; processor agreement with the host; data-subject requests via
   response IDs.
5. **Retention.** Server-side automatic deletion at the study's retention
   date; deletion receipts; backups follow the same schedule.
6. **Security.** OWASP ASVS L2, rate limiting and abuse protection, CSP,
   no file uploads from respondents, dependency scanning, penetration test
   before first public study.
7. **Technology.** A small FastAPI/PostgreSQL service and a server-rendered
   or static accessible form app (WCAG 2.2 AA, mobile-first). A static Flet
   web build is *not* used for analytics or OCR in the browser; it could be
   evaluated only for the respondent form after accessibility testing.
8. **Non-goals for Stage 33**: no server, no account system, no remote
   collection; the desktop keeps working fully offline.

**Qt/PySide6** is not proposed. Measured prototype shortcomings to watch:
DataTable performance for > 1000 rows, missing equal-height grids
(`ResponsiveRow` cannot stretch children), and no native menu bar
accessibility audit yet. Revisit only if these block Phase C.

---

## 14. Brief COPE linkage (Issue #20)

The importer work for Brief COPE-style layouts (letter-spaced text layers,
standalone/circled numbers, repeated four-choice blocks, 28 items) is on its
own branch and PR. Both meet at **`import_session.ImportSession`**: the
Stage 33 import workspace renders `instruments`, `schemes`, `flags()` and
`blockers()`; Issue #20 adds its evidence (missing item numbers, documented
scoring statements requiring approval) to `blockers()`/flags without new
UI coupling.

---

## 15. Implementation plan

| PR | Scope | Exit criteria |
|---|---|---|
| **33-A (this PR)** | Audit, inventory, spec, tokens, components, shell, Home/Data/Analyze/Results/Reports/Questionnaires/Import prototypes on the real engine, route map, tests, screenshots, Windows build with the preview entry | parity + journey + a11y tests green; Windows GUI checks for classic and workspace; user evaluation |
| 33-B | Workspace becomes the default shell with "Classic interface" as fallback; theme/language persisted; dictionary levels shared with classic screens | parity unchanged; no classic test regressions |
| 33-C | Questionnaire parity: pages and page titles, DK/PNA, value-label editor, clone published, multi-page respondent flow, response table; scientific import: regions, matrix grid, OCR batch, binary formats inside the import workspace (incl. Brief COPE evidence) | `survey` route status `workspace`; classic survey tests mirrored |
| 33-D | Reports: combined Word document from multiple results (new engine-backed function with tests), figure numbering | DOCX round-trip tests |
| 33-E | Real-PC QA: 100/125/150 % DPI, Narrator/NVDA, keyboard-only, LV/RU native review, startup performance | checklist signed off by the owner |
| 33-F | Remove classic routes whose replacements passed tests | owner approval |

Risks: Flet layout limits (equal heights, large tables), translation
quality, scope growth in the builder, and users confusing the preview with
a finished product (mitigated by the "Preview/Prototype" labels).

---

## 16. Verification evidence

Automated (all synthetic data):

* `tests/test_analysis_runs.py` — classic callbacks vs `analysis_runs` for
  all analysis areas and post-hoc (7 tests).
* `tests/test_workspace_foundations.py` — contrast, type scale, themes, text
  completeness/placeholders/plurals, advisor decision table, value
  independence, engine limits, route map vs live inventory (17 tests).
* `tests/test_workspace_shell.py` — routes, navigation, shortcuts, theme,
  languages, accessibility rules on every page, 1100/900 px layouts, live
  region, classic ⇄ workspace switching with the dataset (10 tests).
* `tests/test_workspace_journeys.py` — J1–J3 end to end (3 tests).
* `tools/workspace_screenshot_suite.py` — 17 screenshots (light/dark,
  EN/LV/RU, 960–1600 px, 100/125/150 %), each checked for blank pages and
  Flutter error placeholders; before/after composites.
* Windows CI: packaged GUI startup check for the classic interface **and**
  for `SRA_UI=workspace`.

Screenshots: `docs/images/stage33/` (see the PR description).

---

## 17. Appendix A: feature parity matrix

Generated from `workspace_routes.py` (abridged; actions are listed in the
module and tested).

| Classic screen | Workspace destination | Status | Notes |
|---|---|---|---|
| `home` | `home` | workspace | Start actions, current dataset, recent files, saved questionnaires |
| `dataset` | `data` | workspace | Import, diagnostics, variable dictionary, preview, import options |
| `preparation` | `data#prepare` | hosted | Classic non-destructive preparation tools inside Data |
| `survey` | `questionnaires` | partial | Builder, scales, conditions, preview, publish, collect, export, scientific import; still classic: page titles/section reorder, DK/PNA, value-label editor, clone, multi-page fill, response table, matrix grid, region edits, OCR batch, binary bulk action |
| `descriptive` | `analyze/all/descriptive` | workspace | Also Explore distributions |
| `reliability` | `analyze/all/omega` | workspace | Cronbach α and McDonald ω (+ item analysis) |
| `factor` | `analyze/all/factor` | workspace | EFA / PCA |
| `correlation` | `analyze/all/correlation` | workspace | Pearson / Spearman |
| `matrix` | `analyze/all/matrix` | workspace | Correlation matrix |
| `groups` | `analyze/all/groups` | workspace | Welch t / Mann–Whitney U |
| `paired` | `analyze/all/paired` | workspace | Paired t / Wilcoxon |
| `chi` | `analyze/all/chi` | workspace | Chi-square |
| `omnibus` | `analyze/all/omnibus` | workspace | ANOVA / Welch ANOVA / Kruskal–Wallis + post-hoc in Results |
| `regression` | `analyze/all/regression` | workspace | Linear regression (HC3 option) |
| `logistic` | `analyze/all/logistic` | workspace | Binary logistic regression |
| `ancova` | `analyze/all/ancova` | workspace | ANCOVA / GLM |
| `repeated` | `analyze/all/repeated` | workspace | RM ANOVA / Friedman |

| Classic menu command | Workspace destination |
|---|---|
| File → Import CSV / Excel… | Data (Ctrl+O) |
| File → Import Word / PDF questionnaire… | Questionnaires → Scientific import |
| File → New questionnaire | Questionnaires |
| File/Data → Recent files / Dataset | Home → Recent data files |
| Data → Prepare data | Data → Prepare data (hosted) |
| Analysis → Descriptive / Scale reliability / EFA / Correlations / Regression | Analyze → All methods |
| Reports → APA report wizard | Results (assumptions, interpretation, Word) |
| Reports / AI → Methodology and references | Results (notes appended to copied/saved reports) |
| Database → Saved questionnaires and responses | Questionnaires → Published on this computer |
| Settings → Windows/macOS corners, Offline OCR | Settings |
| AI assistant / Help → status, privacy, OCR | Help & privacy, Settings |

Classic per-screen exports (fixed file names in `reports/`) are replaced by
the Results exports with a save dialog (F5).

---

## 18. Appendix B: critique of the reference screenshots

The attached references were used for understanding only; nothing was
copied.

| Reference | Adopted | Avoided |
|---|---|---|
| Light "PSYSTAT" Mann–Whitney | sidebar + content, APA table with figure | **reporting errors**: means/SDs for a rank test while the boxplot shows medians that contradict them; U, Z and p repeated on both group rows; two different effect sizes for one test; "p = 0.034 = 0.45" typo; bold "statistically significant" and a "Significant difference" callout on the figure; leading zeros in p |
| Dark "PSYSTAT" | settings beside the output; table + figure side by side | duplicated list entries, placeholder items, duplicated "Statistical Tests" navigation |
| Windows 11 demo app | calm navigation pane, card grid for start actions | decorative hero banner, search box without a command model |
| macOS Recipes | source list / list / detail pattern (used for Results and the builder) | photo-heavy layout |
| Questionnaire builder | list / editor / live preview, chips for scale labels | numeric codes editable next to labels without a source or confirmation; a "Scoring" toggle that implies validated scoring |
