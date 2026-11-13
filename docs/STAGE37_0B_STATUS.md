# Stage 37.0b — status: what is done, and the test that proves it

The 37.0b list of `docs/STAGE37_0A_STATUS.md` §7, in the coordinator's priority order, plus the review findings of the independent review of `2f9af71` (`docs/STAGE37_FABLE_NARROW_REVIEW.md` on `claude/stage37-review`) that the coordinator added. The specification is `docs/STAGE37_DESIGN.md` §7, §8 and §10.

- **Branch.** `claude/stage37-0b`, from `origin/stage37/master-acceptance-interoperability-spec` (`2f9af71`, owner PR #71 on #65 on #64). Not pushed; no PR.
- **Format.** Project format 6 stays. No new format: every addition is JSON in existing columns (`plan_versions.plan`, `runs.provenance`, `protocol_records.detail`, `events.detail`).
- **Not changed** (as instructed): the engines and `analysis_runs`, the installer, the updater, the workflows and the locks.
- **Tests.** The full suite (`SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 python -m unittest discover -s tests`) is green: **1389 tests, OK (10 skipped)**, against 1326 at `2f9af71`. The 63 new tests:
  - `tests/test_stage37_reports.py` (11), `tests/test_stage37_review_fixes.py` (14), `tests/test_stage37_journey.py` (2), `tests/test_stage37_plan_editor.py` (8), `tests/test_stage37_footer.py` (8), `tests/test_stage37_task_review.py` (7), `tests/test_stage37_formats.py` (9), `tests/test_stage37_ux.py` (2);
  - `tests/test_workspace_journey_strip.py::TaskStatusTests` (2).
- **Rule of this file.** An item is *done* only when a named test proves it. *Partly* says which part has no code or no test. *Not done* says why.
- **Red first.** Every test of `tests/test_stage37_review_fixes.py` and `tests/test_stage37_reports.py` was run against a clean export of `2f9af71`: all 25 fail or error there (23 failures and 14 errors counted per subtest), and pass on this branch.

## 1. The 37.0b list

| # | Item | Status | Proved by |
|---|---|---|---|
| 1 | **Hypothesis rows in the Word research report** (§7.10, AC-3, AC-8, AC-15). For every hypothesis one block whose every line names it: designation; direction, α and plan version; each analysis that tests it (task, method, number of tests, correction, current or stale, in the report or not); each result of the report that tests it with the engine's n and its estimates with CI *as saved*, and its review (ticks, note); every recorded decision with its reason (deviations with planned and used, acknowledgements, justifications, designation and plan changes, withdrawals); the checks that are open or disclosed. The editable Word table *Hypotheses and evidence*: one row per hypothesis × result (source result, data version, calculation, review, limitations). Never "supported" or "confirmed"; no number is computed. EN/LV/RU. | done | `tests/test_stage37_reports.py` (11): `PlanTests` (8) and `WorkspaceReportTests` (3); `tests/test_stage37_review_fixes.py::ReportByHypothesisTests`, `S14ReportRecordsTests` |
| 2 | **Native Windows journey `stage37-hypothesis`** (AC-16), appended after the 18 journeys | done in code and in the harness; **not run on Windows** | `tests/test_stage37_journey.py` (2): the order (19 journeys, the 18 unchanged) and the harness walk of every step with the journey's own texts and helpers. §4 lists the steps. |
| 3 | **Plan-card editor of the planned variables by role**; H-VARIABLES-DIFFER reachable from the interface | done | `tests/test_stage37_plan_editor.py::PlannedVariablesTests` (5), incl. `test_the_planned_variables_reach_the_analysis_and_the_check` |
| 4 | **Journey-strip statuses from `task_steps`** (AC-5) | done | `tests/test_workspace_journey_strip.py::TaskStatusTests` (2); `JourneyTests.test_the_strip_follows_the_research` **changed deliberately** (§6.4) |
| 5 | **The next-action bar in the footers of Data, Analyze, Results and Reports**, and the secondary plan link after results without a plan | done | `tests/test_stage37_footer.py` (8) |
| 6 | **Review ticks and note inside the batch result card**, bound to the result's saved state as on Results; **step 4's plan checks** | done for tasks that test a hypothesis (see §6.7 for the scope) | `tests/test_stage37_task_review.py::TaskReviewTests` (3), `StepFourChecksTests` (3), `ResultCardTests` (1) |
| 7 | **Measured 37.0 interaction counts** (AC-10) with `docs/stage37/measure_baseline.py`; before/after in the docs | done; **AC-10 partly met**: beginner 21 interactions (≤ 20 asked), 5 typed (≤ 5), 4 pages (≤ 4); professor 5 (≤ 6), 2 pages (≤ 2) | `tests/test_stage37_ux.py` (2); `docs/STAGE37_UX_RESULTS.md` |
| 8 | **Copy for an older version** (AC-11): an explicit format-5 copy for the RC; a warning that the protocol records are not carried into it; the original untouched | done | `tests/test_stage37_formats.py::OlderVersionCopyTests` (3), `CopyInTheInterfaceTests` (1) |
| 9 | **A 36.x plan shows its Q1 row by itself** | done | `tests/test_stage37_plan_editor.py::QuestionRowTests` (3); the journey walk starts from it |
| — | **Format-6 migration, backup and restore**, incl. a `.sra` round trip with records | done | `tests/test_stage37_formats.py::MigrationTests` (2: formats 1–5 → 6, each after a backup; a failed migration leaves the old format), `BackupTests` (3: a `.sra` round trip keeps every record field and the UPDATE/DELETE triggers; a restore beside the original is a copy with the records; a format-5 package is migrated with a backup) |

## 2. The review findings added by the coordinator

Each has a red test written before its fix (§0 above for the red run).

| ID | Finding | Status | Fix | Proved by (`tests/test_stage37_review_fixes.py`) |
|---|---|---|---|---|
| D3 | `H-DIR-SIGN` never fires for a single correlation | done | `rw.result_facts` takes the single pair's coefficient from the engine's `CorrelationResult` | `D3SingleCorrelationTests` |
| D4 | Only the first task of a hypothesis drives steps, latest result, next action | done | `HypothesisProgress.tasks`, `HypothesisView.progress`; `next_action` walks every task of a hypothesis in order; the row shows the first unfinished one | `D4EveryTaskTests` |
| D5 | A task keeps the first run's title; the report prints it over all its results | done | a task is named after what it runs now (`rw.task_title`, with the run's options: a Pearson correlation is no longer named "Spearman’s ρ"); in the report each result is headed by the title of its own saved specification | `D5OwnSpecificationTests` |
| D9 | Word on US Letter; Heading 3 unstyled | done | A4 (210 × 297 mm), Heading 3 = APA level 3 (Times New Roman 12, bold italic) in `interpretation_docx._style`, used by every Word export | `D9WordPageTests` |
| D12 | `protocol_records.run_id` never written | done | a decision about a check names the latest result of its task; a link names the task's latest result | `D12RunIdTests` |
| S8 | Wording, direction or α edited after results keep "confirmatory" silently | done | `save_plan` asks a reason for any substantive change after results (`DesignationReasonNeeded`), records it as a plan-change `deviation` (what, from, to); new check `H-PLAN-CHANGED` compares every result's snapshot with the plan; the plan card asks for the reason (`plan.change_reason_needed`) | `S8PlanChangeTests` (3) |
| S14 | Checks, acknowledgements, deviations (and open warnings) missing from the Word report | done | §1 item 1 | `S14ReportRecordsTests`; `test_stage37_reports` |
| S16 | Every run counts for "added after results" | done | only inferential results count; the detail shows the facts; default 3 changed in `docs/STAGE37_DESIGN.md` §13, owner-changeable | `S16InferentialResultsTests` (3: both cases and the facts) |
| S17 | The predict H0 draft is the omnibus null | done | H0 and the H1 hint are about one predictor with the others held constant | `S17PredictDraftTests` |
| #8 | Report by hypothesis: one block per hypothesis with designation, plan version, method, n, estimate with CI, review state and records; no duplicated paragraph | done for the tested scenario | three hypotheses tested by three methods; python-docx reads three blocks and finds no paragraph twice | `ReportByHypothesisTests` |

## 3. Acceptance criteria (design §10) after 37.0b

| AC | Status | Proved by / what is missing |
|---|---|---|
| AC-1 | done | 37.0a tests, and the Q1 row: `QuestionRowTests` |
| AC-2 | done | 37.0a; predict drafts: `S17PredictDraftTests` |
| AC-3 | done | the record in the Word report: `PlanTests.test_each_decision_is_listed_with_its_reason_and_a_withdrawal_stays`, `WorkspaceReportTests.test_the_word_report_names_the_test_the_decisions_and_the_evidence` |
| AC-4 | done | 37.0a |
| AC-5 | done | the strip: `TaskStatusTests`; another task's result: `test_without_an_open_task_the_first_hypothesis_task_counts` |
| AC-6 | done | 37.0a; the 16th check `H-PLAN-CHANGED`: `S8PlanChangeTests.test_the_check_compares_a_snapshot_with_the_plan`, `test_stage37_workflow.test_every_check_reads_in_three_languages` (all 16) |
| AC-7 | done | 37.0a |
| AC-8 | done | the result card: `ResultCardTests`; the Word report: `test_stage37_reports`, `S14ReportRecordsTests` |
| AC-9 | done | 37.0a; the footers: `test_stage37_footer` (no disabled button, the button does what it names); the plan link after results: `test_after_results_without_a_plan_the_plan_link_is_offered` |
| AC-10 | **partly** | beginner 21 > 20 (typed 5, pages 4 met); professor met; Stage 36 baselines unchanged: `test_stage37_ux`, `test_stage36_ux_baseline` |
| AC-11 | done | `test_stage37_formats` |
| AC-12 | done | 37.0a `AiContextTests` (unchanged: the AI plan preview keeps the 36.x fields) |
| AC-13 | done | `test_workspace_foundations.test_every_key_has_three_languages_with_the_same_placeholders`, `test_locale_audit` (missing 0, placeholder 0) |
| AC-14 | partly | labelled buttons and no re-render while typing (the role fields, the note in the task: `test_before_the_data_names_are_typed_and_typing_never_rebuilds_the_page`, `test_the_review_in_the_task_is_the_results_review`); the browser state check `plan-type-hypothesis` was not run |
| AC-15 | done | `test_stage37_reports` (EN/LV/RU; a report without linked hypotheses keeps its tables and numbers: `test_without_evidence_the_section_and_the_table_numbers_are_as_before`) |
| AC-16 | **partly** | the journey is written and its flow is walked in the harness; it has **not run on Windows** here (Linux). The negative case "a project of a newer format is refused" is proved by `test_stage37_store.FormatSixTests` and not driven in the journey. |
| AC-17 | not done | manual, the owner's |

## 4. The journey `stage37-hypothesis`

`tools/windows_gui_e2e.py::journey_stage37_hypothesis`, the 19th entry of `JOURNEYS`. Synthetic UCLA/SACS CSV of `tests/stage36_fixtures`.

1. Create the project (Home, title, *Create project*).
2. Q1 is there by itself (`plan.q.from_project`): type its text, choose its kind *Relationship between two variables*; the bar says *Add a hypothesis to Q1*.
3. *Add a hypothesis to Q1*; type H1; Direction *Less (one-sided)*; Priority stays *Primary*.
4. *Save plan version*; the database (read-only) has one version with the typed question and H1.
5. *Open CSV / Excel…* through the Windows Open dialog; accept the levels.
6. Project page (left and reopened to reach its top): *Create the analysis for H1*; Analyze opens at the variables; the database has the `link` record.
7. UCLA, all quantitative, untick Age, Spearman, Run; the result's provenance holds H1's snapshot (plan version 1, less).
8. Project page: *Next: decide on the checks of H1*; *Show the checks of H1*; the check text "H1 predicts a direction … two-sided p-values only" is on screen.
9. *Acknowledge…*, the reason, *Save the record*; the database has the acknowledgement with the reason.
10. Results: *Tests H1: …*; *Add to report*.
11. Reports: *Export Word report…* through the Windows Save dialog; the `.docx` holds the hypothesis rows (H1 line, direction/α/plan version, *H1 tested by “UCLA with 8 variables”: Spearman’s ρ; 8 tests; correction: Holm…*, the acknowledgement with its reason) and the table *Hypotheses and evidence* with H1's row.
12. Restart the program, open the project: the hypothesis line is back; *Show details* shows *Acknowledged: <reason>*; the records written before the restart are all there; Results still says *Tests H1*; a second Word export holds the same rows.
13. Negative: Priority *Secondary* and *Save plan version* without a reason: the message says why; the database still has one plan version.
14. At every step the protocol records are counted read-only: the count never decreases, and the final records are `link`, `acknowledgement`.

**What cannot be automated here, or was not.**
- The journey itself runs only on Windows (`windows-gui-e2e.yml`, `windows-installer.yml`); this session has no Windows, so it has not run. The harness walk proves the texts, names, labels, dropdown entries and states the journey relies on, not the UI Automation tree.
- UI Automation reports every button as enabled: the journey never asserts a disabled state; the database is the evidence.
- The mouse wheel over an inner list scrolls that list: the journey leaves a page and opens it again to reach its top (`to_top`).
- Not driven: Narrator, keyboard-only, display scales (the DPI journey is separate), a newer-format refusal on the installed program.

## 5. Data keys as built (37.0b)

- **Plan card.** Q1 shown by itself: `plan-q{i}-auto`. Planned variables: `plan-h{i}-role-{role}` (dropdown, or text field before data), `plan-h{i}-role-{role}-{name}` (checkbox of a multiple role), `plan-h{i}-roles-missing`.
- **Footer bar.** `footer-next-action`, `footer-next-label`, `footer-next-title`, `footer-next-here`, `footer-next-why`, `footer-next-why-{i}`; its buttons keep the `next-*` keys of the Project page bar (the two are never on the same page). The plan link: `next-plan-link`.
- **Analyze.** Step 4: `task-checks`, `task-check-{j}`, `task-checks-none`. Batch result card: `task-result-hypothesis`, `task-review-{i}`, `task-notes`, `task-skip-notes`, `task-notes-skipped`.
- **Results.** `result-hypothesis-open` (*Open H…*).
- **Project page.** `hyp-{n}-standing-facts`; `project-copy-older`, `project-copy-older-body`, `project-copy-older-confirm`, `project-copy-older-cancel`.

## 6. Changes to existing behaviour, and why

1. **The Word research report.** The Hypotheses section gains the blocks and the table (§1). Existing lines name their hypothesis so that no paragraph is written twice: *Null hypothesis of H1: …*, *H1 was planned before the results.*, *H1 was added after results… (post hoc)*. The data line of a result names it (*Data of “…”: …*). A task's results are headed by the title of their own specification (D5). Pages are A4 and Heading 3 is styled (D9), in every Word export. A report whose hypotheses no analysis tests has the tables and table numbers it had.
2. **Tasks.** A task is renamed after what it runs at every run (D5); a task's name uses the run's options. Nothing else of a task changes.
3. **The plan.** A plan without typed questions shows Q1 by itself (from the project's research question, kind not chosen); it starts the plan only once used; the first save writes it as Q1 and Q1's text is written through to the project's research question (the AI overview and the report's *Research question* read that row). A change of wording, direction or α after results now needs a reason, like a priority change (S8); before, it was saved silently. "Added after results" counts only inferential results (S16; before, every result). The predict drafts are about one predictor (S17).
4. **The journey strip** (AC-5, review U10). Design, Method, Result and Report follow the open task, else the first hypothesis's task. A result outside any task no longer ticks Design and Method. `tests/test_workspace_journey_strip.py::JourneyTests.test_the_strip_follows_the_research` was **changed deliberately**: its result has no task, so Method and Design are now *not done* (the old assertion was the defect U10).
5. **Footers.** Data, Analyze, Results and Reports show the next-action bar below the page while a project is open. The Windows driver's `Gui.footer_top` also finds this footer (its fixed label *Next step*), so page content scrolled under it is never clicked. Without a plan, after results, the bars also offer *Add the research question these analyses answer*.
6. **The next action** walks every task of a hypothesis (D4).
7. **Review in the task.** Only a task that tests a hypothesis gains the ticks and the note in its batch card. A task without one keeps the Stage 36 card unchanged, because the K1 journey `confirmations` and its harness test count every unnamed checkbox on that page as a confirmation.
8. **Records.** A deviation recorded from a check keeps what was planned and what was used (`detail.planned`, `detail.actual`); decisions about a check name the result (`run_id`, D12). The 37.0a test `test_stage37_ui.PlanEditorTests.test_the_planned_analysis_is_compared_with_the_one_run` now expects the richer detail.
9. **Checks.** 16 checks (new `H-PLAN-CHANGED`); `test_stage37_workflow.every_check` covers it ("all 16 checks").
10. **Journeys.** `JOURNEYS` has 19 entries; `test_stage368_review_journeys.JourneyOrderTests` expects 19, with the 18 in their order.
11. **Not changed:** every existing data key and the English texts journeys use; the Stage 36 interaction baselines (8, 2, 8, 8, 2, 1, 3) and today's measured flows (22 · 10 · 5, 14 · 0 · 6, 5 · 0 · 2).

## 7. LV and RU drafts: needs native review

All new texts have LV and RU written as drafts, marked in the code ("LV/RU drafts — needs native review" in `workspace_text.py`; "LV drafts" / "RU drafts" in `research_report.TEXT`).

- **`workspace_text.T` (33 new):** `plan.q.from_project`; `plan.h.roles`, `plan.h.roles_body`, `plan.h.roles_hint`, `plan.h.role_none`, `plan.h.role_missing`, `plan.h.roles_missing`; `footer.next_step`, `next.here`, `next.plan_link`, `next.plan_link_note`; `task.review`, `task.notes_skipped`, `task.checks`, `task.checks_body`, `task.checks_none`; `results.open_hypothesis`, `results.open_checks`, `results.decisions`; `check.plan_changed`, `check.field.priority`, `check.field.direction`, `check.field.alpha`, `check.field.wording`; `plan.change_reason_needed`, `plan.h.change_reason`; `hyp.standing_facts`; `project.copy_older`, `project.copy_older_title`, `project.copy_older_body`, `project.copy_older_confirm`, `project.copy_older_dialog`, `project.copy_older_saved`. **Changed (2):** `hyp.draft.h1.predict`, `hyp.draft.h0.predict` (S17).
- **`research_report.TEXT` (66 new per language):** the hypothesis rows (`hyp_direction`, `not_tested`, `tested_by`, `tested_by_none`, `result_line`, `estimate`, `estimate_ci`, `no_estimate`, `state.*`, `review_line`, `note.*`, `calc.*`), the records (`records_title`, `records_none`, `record.*`, `timing.*`, `what.*`, `about.*`), `limits_title`, `others`, and the table (`evidence`, `evidence_columns`, `evidence_none`, `evidence_note`, `cell.*`). **Changed (4):** `h0`, `post_hoc`, `planned`, `version_line`.

## 8. Not done, and where it belongs

- **The beginner's 20th interaction** (AC-10): see `docs/STAGE37_UX_RESULTS.md` (the kind of Q1 is a dropdown).
- **Running the journey on Windows** (AC-16): the owner's or CI's Windows runner.
- **From design §7.10, not in the 37.0b list:** the hypothesis list and detail side by side; *Show the evidence* inside the hypothesis detail.
- **The in-task review for tasks without a hypothesis** (§6.7): needs the `confirmations` journey to filter assumption boxes first.
- **"No duplicated paragraph"** is proved for hypotheses tested by different methods; two results of one method repeat their assumption lines, each under its own result title.
- **Review findings outside the coordinator's list:** D1, D2, D6, D7, D8, D10, D11, S1–S7, S9–S13, S15 (tamper evidence, note history), the usability and missing-feature items. Notes and review ticks are still overwritten without history (S15).
- **Native review** of the LV and RU texts (§7); **AC-17** (manual).
