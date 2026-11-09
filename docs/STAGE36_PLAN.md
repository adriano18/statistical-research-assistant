# Stage 36 — implementation plan and defect matrix

The full requirements are in [STAGE36_SPEC.md](STAGE36_SPEC.md). This
document records how they are delivered: the pull requests, the defects
found by the 36.0 audit, the tests that reproduce them and the rules for
private research material.

## Base and branches

Stage 36 builds on the integrated Stage 35 state (#47 → #48 → #49 → #50 → #51),
through the specification PR #52 (`stage36/spec-and-safe-fixtures`, base
`claude/stage35-ai`). Nothing is merged into `main`; every PR is a draft.

| Sub-stage | PR | Branch | Scope (spec sections) |
|---|---|---|---|
| 36.0 Audit and failing tests | #53 | `claude/stage36-audit` | fixtures (README), defect matrix, UX baseline (§2, §15), reproductions |
| 36.2 Statistical result engine | #54 | `claude/stage36-engine` | typed results (§8), batch correlations with CI, Holm/BH (§5), batch Kruskal–Wallis (§6) |
| 36.1 Research tasks and navigation | #55 | `claude/stage36-tasks` | Research Task model and persistence (§4), batch selection, persistent context (§2B), journey navigation (§3); the window guard |
| 36.5 Scientific import | #56 | `claude/stage36-import` | two-form DOCX, scanned tables with OCR, review wizard (§10) |
| 36.4 Chart Studio | #57 | `claude/stage36-charts` | chart types, multi-boxplots, settings, PNG/SVG/PDF, image clipboard (§9) |
| 36.6 Research report | #58 | `claude/stage36-reports` | report builder (§11) |
| 36.3 Scales and psychometrics | #59 | `claude/stage36-scales` | Create Groups from Scale (§6), item diagnostics, no reliability from totals (§7) |
| 36.6 AI assistant | #60 | `claude/stage36-ai` | AI assistant with consent (§12) |
| 36.7 Windows EXE acceptance | #61 | `claude/stage36-acceptance` | packaged EXE journeys 1–10, installer and update regression (§14), final documents (§18) |

The engine (36.2) comes before the task model (36.1) because a research
task stores and re-runs the structured batch results. Each PR is stacked
on the previous one and carries its own tests and Windows E2E journeys.
The import engine (36.5, D6–D8) was ready first, so it is stacked directly
on 36.1; its review wizard was added to the same PR (#56). 36.4 (Chart
Studio) is stacked on 36.5 and the research report (36.6, #58) on 36.4;
36.3 (#59), the AI assistant (#60) and the acceptance PR (#61) follow on
top. Fixes found lower in the stack are merged upward, so the top branch
(#61) holds everything and its Windows CI runs every journey on it.

## Defect matrix (36.0 audit)

Each defect has a reproduction in `tests/test_stage36_regressions.py`,
marked `expectedFailure` until fixed; the fixing PR removes the marker,
so an unexpected success fails CI.

| ID | Symptom | Root cause | Reproduction | Fix |
|---|---|---|---|---|
| D1 | Journey items open the wrong step: **Variables** opens Data, **Method** opens Design; the current step is always "Design" on the analysis page | `workspace_shell.JOURNEY` maps 7 steps onto 5 routes; `JOURNEY_ROUTES["analyze"] = "design"` | `test_every_journey_step_opens_its_own_step` | 36.1 ✔ |
| D2 | Descriptive statistics show "Structured numeric results: Not captured" | `analysis_runs.run_descriptive` keeps no result object; `build_analysis_evidence` only knows Shapiro–Wilk/Levene rows for this section | `test_descriptive_statistics_are_structured_numbers` | 36.2 ✔ |
| D3 | One variable against eight scales needs eight separate runs; no shared table, no multiple-comparison correction | correlation engine and guided roles take one pair | `test_one_variable_against_eight_scales_in_one_run` | 36.2 ✔ |
| D4 | A two-category group (Sex) for a 3–8 group method is not explained before Run | `role_problems` does not count the categories of the group | `test_a_two_group_variable_is_explained_before_a_three_group_test` | 36.2 ✔ |
| D5 | Reliability (ω/α) is offered for total scores | the guided advice cannot tell item responses from totals | `test_no_reliability_from_total_scores` | 36.3 ✔ |
| D6 | A Word document with two 60-item table forms **without numbers in the cells** is "not recognised" | `parse_scientific_lines` needs numbered lines; table structure is flattened first | `test_two_unnumbered_sixty_item_forms` | 36.5 ✔ |
| D7 | The stated item count is read from a scoring note ("each with four items" → 4) | `expected_item_count` takes the first count phrase in the document | `test_the_stated_item_count_is_not_taken_from_a_scoring_note` | 36.5 ✔ |
| D8 | A scanned table with a number column yields 16 of 52 items | line parser needs a clean number at the line start; a scan artifact (`"17.`) ends the sequence; no column geometry | `test_a_scanned_table_with_a_number_column_yields_all_52_items` | 36.5 ✔ |
| D9 | Groups of 3/47/5 are refused only after Run ("At least five complete observations per group") | no pre-run check of group sizes | `test_small_groups_are_handled_before_the_run_not_refused_after` | 36.2 ✔ |
| D10 | Kruskal–Wallis refuses any group under five observations, so no batch comparison by an imbalanced level variable is possible | omnibus engine minimum of five per group for every method | `test_kruskal_wallis_for_eight_outcomes_with_a_group_of_three` | 36.2 ✔ |

Further audit observations, handled in the listed sub-stage:

- An identifier column of text codes (`fictional_001`, …) was suggested as "unknown", not "identifier": one more confirmation for every dataset (fixed in 36.1).
- Spearman ρ has no confidence interval; no Kendall τ (36.2).
- No chart can be changed without re-running the analysis; no SVG/PDF export and no image clipboard (fixed in 36.4: Chart Studio, project format 5).
- The importer finds no response options for the table forms (both DOCX forms and both scans: zero response schemes) (36.5).

## Fixtures

`tests/fixtures/stage36/generate_fixtures.py` writes invented content only:

| File | Tests |
|---|---|
| `synthetic_ucla_sacs_55.csv` | 55 × 13, groups 3/47/5 (batch correlations, groups, KW) |
| `synthetic_cope_two_forms_60.docx` | two numbered 60-item table forms, scoring note, references |
| `synthetic_cope_two_forms_60_unnumbered.docx` | two 60-item table forms **without numbers in the cells**, each with its own response options (added in 36.0; reproduces D6) |
| `synthetic_sacs_scanned_52.pdf` | two image-only pages, numbers inline with the text |
| `synthetic_lv_table_scan_52.pdf` | two image-only pages of a table: number column, wrapped rows, Latvian letters, repeated legend, slight rotation and tick artifacts before numbers (added in 36.0; reproduces D8 exactly: 16 of 52) |
| `synthetic_items_scale.csv` | 200 × 12: ten invented 1–5 items of one invented construct, two reverse-keyed items not recoded, a floor effect, nine missing answers and an invented total (added in 36.3; item diagnostics, D5) |

`tests/test_stage36_fixtures.py` checks the README's minimal verification
(shape, group sizes, two 60-item forms, image-only pages, determinism).
`tests/stage36_fixtures.py` generates them once per test run.

## Private research material

The owner's dataset, thesis and questionnaires are **never** committed,
attached, uploaded as CI artifacts or quoted. They are read only in a
local, authorized session, from a folder outside the repository, and only
counts and discrepancies are reported (README "LOCAL ONLY").

Local baseline (36.0): the owner's scanned questionnaire yields **16 of 52**
items with the current importer (the sequence breaks at item 17 because
of a scan artifact before the number); the synthetic table scan
reproduces the same failure, so CI can test the fix without the original.

## Test layers

1. Unit — engine, results contract, corrections, derived variables, scoring, item diagnostics, import parsing (Linux CI, `python-tests.yml`).
2. Integration — dataset → task → analysis → result, import → scale, reliability → correlation → report, chart → export, save → restart → restore (workspace harness on Linux CI).
3. UX regression — interaction counts (`tests/test_stage36_ux_baseline.py` and its successors), RU/LV/EN, light/dark, compact widths.
4. Packaged Windows EXE — `tools/windows_gui_e2e.py` journeys with UI Automation and the real Open/Save dialogs, on the portable bundle and on the installed program (`windows-gui-e2e.yml`, `windows-installer.yml`, `windows-update-e2e.yml`).
