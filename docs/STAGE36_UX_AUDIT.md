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

| Workflow | Current interactions (measured) | Stage 36 target | Improvement | Risks and safeguards |
|---|---:|---:|---|---|
| Correlate UCLA with 8 scales (Spearman) | **43** interactions, 16 page changes; 8 separate results, no shared table, no correction for 8 tests | goal, focal variable, scales (one multi-select), Run: **≤ 6** | one batch run with a family table, N per pair, CI, raw and adjusted p | eight tests are eight hypotheses: the family, its size and the correction (Holm by default) are shown, raw p is never altered |
| Repeat an analysis with another variable | **5** | **1–2** (re-run or edit the task in place) | the task keeps variables, method and options | a re-run on changed data is marked as a new version, never merged silently with the old one |
| Compare 3 groups (UCLA_Level 3/47/5) on 8 scales | refused **after** Run each time (9 interactions spent before the refusal) | group, outcomes (multi-select), Run: **≤ 6**, with small-group warnings shown **before** Run | batch Kruskal–Wallis that runs with small groups and says how p was obtained | a group of 3 makes the χ² approximation unreliable: a permutation p is reported and the warning stays in the result and report |
| Create groups from a scale (UCLA) | not available (only an existing column can be used) | scale, rule, preview, create: **≤ 5** | derived categorical variable with its rule and history | user thresholds are never presented as clinical norms; original scores stay unchanged |
| Two-category group for a 3–8 group test | technical refusal after Run | explanation and the two-group alternative **before** Run | — | — |
| Reliability with total scores only | ω/α offered on totals (fictitious) | explanation: item responses are needed | — | no coefficient is ever computed from totals |
| Change a chart type | not possible | **1–2** in Chart Studio, no re-run | figures are drawn from the stored result data | chart settings never change the statistics |
| Copy a chart to the clipboard | not possible (text copy only) | **1** (real image on the clipboard) | — | the clipboard is checked to hold an image, not a path |
| Word report from 8 results | **19** interactions + Save dialog | **2** (add the task's results, export) + Save dialog | — | results from different data versions are labelled, never merged silently |
| Review a 60-item table form without item numbers | blocked ("no numbered questions") | choose the form, review, confirm | both forms detected, each with its own options | wording and scoring keys are never approved automatically |
| Import a scanned 52-item table (OCR) | 16 of 52 items found; 36 must be typed in by hand | 52 candidates, each linked to its page region | — | OCR confidence is shown as character confidence only; every item is reviewed |
| Move between research steps | **Variables** opens Data; **Method** opens Design | each step opens itself (1 click) | — | — |
| Resume after a restart | project and results return; selections and settings do not | tasks, selections and chart settings return | — | — |

## Principles applied (spec §2)

- **Progressive disclosure:** guided and all-methods modes share one engine and one result store; options open on demand.
- **Persistent context:** a research task keeps variables, method, options, open sections and selected results across pages and restarts.
- **Contextual actions:** after a run the task offers change variables, re-run, compare with another method, add scales, edit the chart, add to report.
- **Batch first:** one method over many variables in one run; one question may hold several methods.
- **No confirmation fatigue — but never automatic approval** of recognised questionnaires, codes, reverse keying, contested methods or AI data transfer.
- **Clear feedback:** running, done, saved, needs review, not done (why and what next); no internal keys such as `block.level_mismatch` shown to the researcher.
