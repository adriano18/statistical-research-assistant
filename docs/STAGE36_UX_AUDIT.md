# Stage 36 — UX and interaction-cost audit

## Method

The baseline numbers are **measured**, not estimated:
`tests/test_stage36_ux_baseline.py` drives the real workspace controls
(the handlers a click runs) on the synthetic 55-row dataset and counts
every interaction a researcher needs. A dropdown choice counts as two
interactions (open the list, choose the entry). Each test checks that the
workflow actually produced its results, so a shortcut that skips a needed
step cannot hide in the count.

The "Stage 36" column is the target; it is filled with measured numbers
by the PR that implements the improvement (each adds its own measured
test next to the baseline one), and the final numbers are collected in
`docs/STAGE36_E2E_RESULTS.md`.

## Workflows

| Workflow | Before Stage 36 (measured, 36.0) | Stage 36 target → **measured** | Improvement | Risks and safeguards |
|---|---:|---:|---|---|
| Correlate UCLA with 8 scales (Spearman) | **43** interactions, 16 page changes; 8 separate results, no shared table, no correction for 8 tests | 4 main actions (goal, UCLA, the scales, Run) → **8 interactions, 1 page change** (36.1): the dropdown counts 2, "All quantitative" 1, clearing Age 1, choosing Spearman over the recommended Pearson 1 | one batch run with a family table, N per pair, CI, raw and adjusted p | eight tests are eight hypotheses: the family, its size and the correction (Holm by default) are shown, raw p is never altered |
| Repeat an analysis with another variable | **5** | 1–2 → **2** (36.1: Analyze, Run again) | the task keeps variables, method and options | a re-run on changed data is marked as a new version, never merged silently with the old one |
| Compare 3 groups (UCLA_Level 3/47/5) on 8 scales | refused **after** Run each time (9 interactions spent before the refusal) | ≤ 6 → **8 interactions** for all 8 scales (36.1: new task, goal, group, the first task's 8 scales in one action, two design confirmations, Run); the small groups are explained before Run (36.2) | batch Kruskal–Wallis that runs with small groups and says how p was obtained | a group of 3 makes the χ² approximation unreliable: a permutation p is reported and the warning stays in the result and report |
| Create groups from a scale (UCLA) | not available (only an existing column can be used) | scale, rule, preview, create: **≤ 5** → **4 interactions** (36.3: Data, the scale, Create; quantiles in three groups are the default rule) | derived ordered categorical variable with its rule in the project's history; an existing grouping (UCLA_Level) is offered for use instead | user thresholds are never presented as clinical norms (documented cut points need their source); original scores stay unchanged |
| Two-category group for a 3–8 group test | technical refusal after Run | explanation and the two-group alternative **before** Run → **done** (36.2) | — | — |
| Reliability with total scores only | ω/α offered on totals (fictitious) | explanation: item responses are needed → **done** (36.3: the guided advice offers no coefficient; among all methods the same explanation appears before Run and Run stays disabled until the researcher confirms the columns are item responses) | α, ω and every item's statistics in one result for item data | the guided path never computes a coefficient from totals; the expert path only after an explicit, recorded confirmation |
| Change a chart type | not possible | **1–2** in Chart Studio, no re-run → **2 interactions** (36.4: Edit chart, choose the type; no analysis runs) | figures are drawn from the stored result data | chart settings never change the statistics (every analysis runner fails the test if it is called) |
| Copy a chart to the clipboard | not possible (text copy only) | **1** (real image on the clipboard) → **1 interaction** (36.4), from Chart Studio or from the result's figure | — | the clipboard is checked to hold an image, not a path: a bitmap (CF_DIB, plus PNG) of the announced size, read back in the EXE journey `stage36-charts` |
| Word report from 8 results | **19** interactions + Save dialog | **2** (add the task's results, export) + Save dialog → **3 interactions** + Save dialog (36.6: add the task's result, open Reports, export) | one research report in fifteen sections (question, hypotheses, data, … limitations, reproducibility); a task's results under one heading, repeated paragraphs written once | results from different data versions are labelled, never merged silently; post hoc hypotheses are marked exploratory |
| Review a 60-item table form without item numbers | blocked ("no numbered questions") | choose the form, review, confirm → **9 interactions** after the Open dialog (36.5 UI): "Review this form" on the second form's card (1, opens its scale step), structure and codes (2), apply (1), step 4 (1), the three confirmations (3), create (1); a draft of exactly 60 | both forms detected and shown as cards, each with its own options and their evidence; the researcher chooses, nothing is chosen silently | wording and scoring keys are never approved automatically; the scale, the codes and the three confirmations stay separate clicks |
| Import a scanned 52-item table (OCR) | 16 of 52 items found; 36 must be typed in by hand | 52 candidates, each linked to its page region → **12 interactions** after the Open dialog in the English interface (36.5 UI): the OCR language dropdown (2), "Read with local OCR" (1), Next (1), structure and codes (2), apply (1), step 4 (1), the three confirmations (3), create (1); **10** in the Latvian interface, which proposes Latvian; 52 candidates, the legend as one scale | the scan is detected before OCR, which runs in the language the researcher chooses; the OCR stays a visible fact | OCR confidence is shown as character confidence only; the legend scale is proposed, never confirmed; items needing attention are listed (F8 / F9) |
| Move between research steps | **Variables** opens Data; **Method** opens Design | each step opens itself (1 click) → **done** (36.1): every step opens and marks itself; the page scrolls to it | — | — |
| Resume after a restart | project and results return; selections and settings do not | tasks, selections and chart settings return → **tasks, selections and the structured result return** (36.1, project format 4); **chart views and the report view return** (36.4, format 5), drawn without the dataset | — | — |

## Principles applied (spec §2)

- **Progressive disclosure:** guided and all-methods modes share one engine and one result store; options open on demand.
- **Persistent context:** a research task keeps variables, method, options, open sections and selected results across pages and restarts.
- **Contextual actions:** after a run the task offers change variables, re-run, compare with another method, add scales, edit the chart, add to report.
- **Batch first:** one method over many variables in one run; one question may hold several methods.
- **No confirmation fatigue — but never automatic approval** of recognised questionnaires, codes, reverse keying, contested methods or AI data transfer.
- **Clear feedback:** running, done, saved, needs review, not done (why and what next); no internal keys such as `block.level_mismatch` shown to the researcher.

## Measured after 36.1

`tests/test_stage36_ux_baseline.py` now measures the Stage 36 workflows on
the same synthetic data; the numbers above come from it. The Windows EXE
journey `stage36-tasks` (`tools/windows_gui_e2e.py`) performs the same
steps through UI Automation on the packaged program.

The eight-correlation workflow meets the spec's four main actions; its raw
count is 8 because a dropdown counts twice, Age has to be cleared from
"All quantitative", and the researcher chose Spearman over the recommended
Pearson. Selecting a variable range in one gesture would remove one more
interaction; Flet's checkboxes give no modifier keys, so it is not offered.

## Measured after 36.5 UI (review wizard)

`tests/test_stage36_import_ui.py` (`ImportInteractionCounts`) counts the
review of the two synthetic documents with the same `CountingWorkspace`
(a dropdown counts as two), from the moment the document is chosen in the
Open dialog (one more click opens that dialog) to the created draft, and
checks the draft: 60 items of the chosen situational form, or 52 items of
the scan. The scan needs real local OCR (Tesseract with `lav`), so its
count is skipped where that is not installed.

| Workflow | Interactions | Of which |
|---|---:|---|
| Two unnumbered 60-item Word forms → draft of the second form | **9** | choose the form 1, scale 3, step 4 1, confirmations 3, create 1 |
| Scanned Latvian 52-item table → draft (English interface) | **12** | OCR language 2, read 1, Next 1, scale 3, step 4 1, confirmations 3, create 1 |
| The same in the Latvian interface | **10** | Latvian is proposed: the dropdown is not needed |

Before 36.5 the Word document could not be imported at all and the scan
gave 16 of 52 items, so there is no earlier count to compare with; the
36.5 import engine made them readable and the wizard keeps every scientific
decision (form, scale, codes, version, rights, item count) with the
researcher. Packaged-EXE journeys: `import-cope-docx` and `import-scan-lv`
in `tools/windows_gui_e2e.py`.

## Measured after 36.4

`test_change_the_chart_type_without_running_the_analysis` and
`test_copy_a_chart_as_an_image` measure the two chart workflows on the same
synthetic data: from the task's result, **Edit chart** and one chart type
(2 interactions); in Chart Studio, **Copy image** (1 interaction). Chart
types are chips, not a dropdown, so a change of type is one interaction.
The EXE journey `stage36-charts` performs the same steps on the packaged
program and reads the bitmap back from the Windows clipboard.

## Measured after 36.6

`test_a_word_report_from_eight_results` counts 3 interactions and the Save
dialog for the Word report of the eight-correlation task. The target was 2;
opening the Reports page is kept as a step on purpose: it shows the report
structure (which of the fifteen sections have content, which the researcher
left out, and whether results come from several data versions) before the
document is written.

## Measured after 36.3

`test_create_groups_from_a_scale_in_at_most_five_interactions` creates three
quantile groups of UCLA in 4 interactions (open Data, choose the scale,
Create). The preview shows every group's bounds, inclusivity, N and percent
before anything is created. The EXE journey `stage36-groups` creates the
groups on the packaged program and runs the eight-scale Kruskal–Wallis batch
by them.
