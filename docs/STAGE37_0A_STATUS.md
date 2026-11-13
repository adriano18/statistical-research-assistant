# Stage 37.0a — status: what is done, and the test that proves it

Issue #63. The specification is `docs/STAGE37_DESIGN.md` (§7, §8, §10). 37.0a is the first part of 37.0 (§13, default 14); the rest is 37.0b.

- **Branch.** `claude/stage37-research-workflow`, stacked on `claude/stage368-rc` (merge `e06736c` of the RC head `07c37f6`).
- **Commits.**
  1. `2176cec`: model (format 6, plan v2, protocol records, the result snapshot).
  2. `89625e7`: `research_workflow.py`, its unit tests and the texts.
  3. The commit that adds this file: the UI, its harness tests and this status.
- **Tests.**
  - `tests/test_stage37_store.py`: 18 tests.
  - `tests/test_stage37_workflow.py`: 38 tests.
  - `tests/test_stage37_ui.py`: 21 tests, harness through the real handlers.
  - The full suite is green: `python -m unittest discover -s tests`.
- **Rule of this file.** An item is *done* only when a named test proves it. *Partly* says which part has no test or no code. *Not done* items are listed with the stage they belong to.

## 1. The coordinator's 37.0a scope

### 1.1 Model (must)

| Item | Status | Proved by |
|---|---|---|
| Migration to format 6, with the pre-migration backup | done | `test_stage37_store.FormatSixTests.test_the_format_is_six_and_adds_only`, `…test_a_format_5_project_migrates_with_a_backup_and_keeps_everything` |
| A format-5 reader (the RC) refuses a format-6 project without writing | done | `…test_a_format_5_reader_refuses_a_format_6_project_without_writing` (simulated by patching `SCHEMA_VERSION` to 5: same bytes, no lock, "newer version (format 6)") |
| Plan JSON v2 in `normalise_plan`: typed questions; hypothesis question, intended method and options, variables by role. H1/H0, direction, designation, α and family as before. | done | `TypedPlanTests.test_typed_questions_and_hypotheses_round_trip`, `…test_question_ids_are_given_and_every_reference_is_checked`, `…test_invalid_typed_fields_are_refused_in_words` |
| A plan without typed content stays byte-identical (sparse) | done | `TypedPlanTests.test_a_plan_without_typed_fields_stays_as_before` |
| Append-only protocol records (designation, link, acknowledgement, deviation, justification, withdrawal): no update or delete API; database triggers refuse `UPDATE` and `DELETE` | done | `ProtocolRecordTests.test_records_cannot_be_changed_or_deleted`, `…test_a_withdrawal_points_to_a_record_and_withdraws_it_once`, `…test_a_reason_is_required_where_a_decision_is_recorded` |
| Records survive a restart, a `.sra` backup and a duplicate | done | `…test_records_keep_their_order_and_survive_a_restart`, `…test_records_travel_in_a_backup_and_a_duplicate` |
| A designation changed after results needs a reason and is recorded | done | `DesignationTests.test_a_change_after_results_needs_a_reason_and_is_recorded`, `…test_a_change_before_any_result_needs_no_reason` |
| `record_run(..., hypothesis=snapshot)` in the provenance, restored into `ResultEntry` | done | `SnapshotTests.test_a_run_keeps_the_hypothesis_it_was_calculated_for`, `…test_an_invalid_snapshot_is_refused`, `…test_the_snapshot_comes_back_into_the_session_after_a_restart` |
| The report export is remembered (`report_exported` event) | done | `ReportExportTests.test_the_last_export_is_remembered`, `test_stage37_ui.NextActionBarTests.test_after_the_export_the_card_says_the_report_is_done` |

### 1.2 `research_workflow.py` (must; pure, no Flet)

| Item | Status | Proved by |
|---|---|---|
| Question types (the guided goals) and the H1/H0 drafts as text keys in EN/LV/RU | done | `test_stage37_workflow.DraftTests.test_every_question_type_has_a_draft_in_three_languages`, `…test_h1_is_a_hint_and_h0_a_complete_statement` |
| `task_steps`: the 8 steps | done | `StepTests` (5 tests) |
| `fingerprint` | done | `RecordTests.test_the_fingerprint_is_canonical_and_follows_the_facts` |
| `designation_history` | done | `CheckTests.test_a_designation_changed_after_results` |
| `next_action`: N1–N8 | done | `NextActionTests` (6 tests). See the rule mapping below. |
| `hypothesis_checks`: all 15 checks, each with a case that produces it and one that does not | done | `CheckTests`: one test per check, plus the order, the texts and the placeholders (18 tests) |
| An acknowledgement is bound to the SHA-256 of the facts and reopens when they change | done | `AcknowledgementTests` (4 tests); in the UI, `test_stage37_ui.HypothesisWorkflowTests.test_an_acknowledgement_reopens_when_the_analysis_changes` |
| Checks never block Run or an export; no text says that a hypothesis is supported | done | `test_stage37_ui.HypothesisWorkflowTests.test_open_checks_block_neither_a_run_nor_an_export`, `CheckTests.test_checks_follow_one_order_and_never_say_supported` |

**N1–N8 as built.**
- N1 `next.question`, N2 `next.add_hypothesis` and `next.write_hypothesis`, N3 `next.save_plan`.
- N4: the Stage 34.5 *add data* card.
- N5 `next.levels`.
- N6a–g, per hypothesis in designation order: create, run, recalculate, decide, review, note (with *Skip*), add to the report.
- N7 `next.export`. It applies until the report, as composed now, has been exported.
- N8 `next.done`.
- Stale results and an empty report keep their Stage 34.5 cards.

### 1.3 UI (must, minimal)

| Item | Status | Proved by |
|---|---|---|
| The next-action bar replaces the Next step card. Its buttons do what they name. It never shows a disabled button, and it explains in text when it cannot act (N1, N2 without text). | done | `test_stage37_ui.NextActionBarTests` (4 tests), `HypothesisWorkflowTests.test_the_next_action_walks_through_the_steps_of_h1` |
| *Why this step?* lists what is done (✓) and what is not (○) | done | `NextActionBarTests.test_start_with_the_question_puts_the_projects_question_in_the_plan` |
| Hypothesis list: designation, direction, α, standing, *n of 8 steps*, open checks | done | `HypothesisWorkflowTests.test_the_next_action_walks_through_the_steps_of_h1` (`hyp-1-steps` reads 8 of 8), `…test_checks_are_decided_with_a_reason_and_withdrawn` |
| *Create the analysis for H1* creates a linked task with the goal of its question; Analyze opens at step 2 (variables) | done | `HypothesisWorkflowTests.test_create_the_analysis_for_h1_links_it_and_opens_the_variables` |
| Analyze step 1 *Tests hypothesis* (`task-hypothesis`); each change writes a `link` record | done | `AnalyzeLinkTests.test_the_link_is_chosen_in_step_one_and_every_change_is_recorded` |
| The task's step-status row (`task-steps`) | done | `AnalyzeLinkTests.test_the_step_row_follows_the_analysis_on_screen`, `StepIsolationTests.test_a_result_of_another_task_does_not_tick_this_tasks_steps` |
| Results: *Tests H1* from the snapshot (`result-hypothesis`), or *linked after it was calculated* | done | `HypothesisWorkflowTests.test_the_result_keeps_the_hypothesis_and_says_so_after_a_restart`, `AnalyzeLinkTests.test_a_result_linked_after_it_was_calculated_says_so` |
| Hypothesis detail: the checks; *Acknowledge…*, *Record a deviation…* and *Justify…*, each with a required reason; *Withdraw…* | done | `HypothesisWorkflowTests.test_checks_are_decided_with_a_reason_and_withdrawn`, `…test_a_free_deviation_is_recorded_with_what_and_why`, `PlanEditorTests.test_the_planned_analysis_is_compared_with_the_one_run` |
| No page rebuild while typing in the hypothesis editor | done | `PlanEditorTests.test_typing_never_rebuilds_the_page` (counts `app.render` while typing in the plan, question, H1, H0, α, reason and record-reason fields) |
| Typed questions in the plan card; the H1 hint and the drafted H0; the planned analysis | done | `NextActionBarTests.test_the_plan_comes_first_once_it_is_started`, `PlanEditorTests.test_the_planned_analysis_is_compared_with_the_one_run` |
| The designation reason in the plan card: a localized message, and nothing is saved without it | done | `PlanEditorTests.test_a_priority_changed_after_results_needs_a_reason` |
| EN/LV/RU: every page of the workflow builds, with no bare key | done | `LanguageTests.test_the_hypothesis_workspace_reads_in_every_language` |

### 1.4 Should

| Item | Status | Note |
|---|---|---|
| Journey-strip statuses from `task_steps` | not done | The strip keeps its Stage 36 statuses. 37.0b. |
| Report lines | not done | 37.0b (default 8). |

## 2. Design §7.1 scope, item by item

| §7 item | 37.0a | Proved by / note |
|---|---|---|
| Typed research questions | done | §1.1; `NextActionBarTests.test_the_plan_comes_first_once_it_is_started`. The Question card (`project-question`) stays. *Start with the research question* or *Add research question* copies its text into Q1. A 36.x plan is not shown with a Q1 row on its own. |
| H1/H0 with direction | done | H1 is a hint and is never prefilled; H0 is drafted for testable kinds. `DraftTests`, `NextActionBarTests.test_the_plan_comes_first_once_it_is_started` |
| Designation set before results, with an audit log | done | `DesignationTests`, `PlanEditorTests.test_a_priority_changed_after_results_needs_a_reason`. History in the hypothesis detail (`hyp-1-history-*`). |
| Task–hypothesis link with a result snapshot | done | §1.3 |
| Step status per task | done | §1.2, §1.3 |
| Deterministic checks with acknowledgements | done | §1.2, §1.3 |
| Protocol deviations | done | From a check (method, variables, spec), or free, with *what* and a reason. `…test_a_free_deviation_is_recorded_with_what_and_why`. |
| The next-action bar | partly | On the Project page only. The footers of Data, Analyze, Results and Reports, and the secondary link *Add the research question these analyses answer* after results without a plan, are 37.0b. |
| Hypotheses section of the Word report | not done | 37.0b (default 8) |
| The additive data model | done | §1.1 |
| A copy for an older version | not done | Not in 37.0a (default 2) |

Page changes of §7.10 that are **not** in 37.0a:
- an editor for the planned variables by role. The model stores them (`roles`); *Create the analysis* chooses the ones that exist in the data; `H-VARIABLES-DIFFER` compares them (`CheckTests.test_the_variables_differ_from_the_plan`). The plan card cannot set them yet, so in the interface this check stays silent;
- the list and detail side by side;
- *Show the evidence*;
- Analyze step 4's `task-checks`;
- the review ticks and the note in the batch result card (`task-review-{i}`, `task-notes`);
- the open checks and deviations on the result card.

## 3. Design §10 acceptance criteria

| AC | 37.0a | Proved by / what is missing |
|---|---|---|
| AC-1 | partly | Types from `GOALS` and an unknown type refused: `TypedPlanTests.test_invalid_typed_fields_are_refused_in_words`. A 36.x plan shown as Q1 *not chosen*: not built (see §2). |
| AC-2 | done | Drafts: `DraftTests`. Defaults two-sided, primary, α 0.05: `NextActionBarTests.test_the_plan_comes_first_once_it_is_started`. The α rule is unchanged: `test_workspace_plan.ResearchPlanCardTests.test_an_invalid_value_is_explained_and_nothing_is_saved`. |
| AC-3 | partly | Store and UI: `DesignationTests`, `PlanEditorTests.test_a_priority_changed_after_results_needs_a_reason`. The record in the Word report: 37.0b. |
| AC-4 | done | `test_create_the_analysis_for_h1_links_it_and_opens_the_variables`; after a restart: `test_the_result_keeps_the_hypothesis_and_says_so_after_a_restart` (link, snapshot); relinking: `AnalyzeLinkTests` (both) |
| AC-5 | partly | Step rules: `StepTests`. The same after a restart: `test_the_result_keeps_the_hypothesis_and_says_so_after_a_restart`. Another task's result: `StepIsolationTests`. The journey strip: not done. |
| AC-6 | done | `CheckTests`. No engine and no network: `HypothesisWorkflowTests.test_building_the_checks_runs_no_engine_and_opens_no_connection`. The same list after a restart: `test_the_result_keeps_the_hypothesis_and_says_so_after_a_restart`. |
| AC-7 | done | `AcknowledgementTests`, `test_an_acknowledgement_reopens_when_the_analysis_changes`, `test_checks_are_decided_with_a_reason_and_withdrawn` |
| AC-8 | partly | Reason, no update or delete, withdrawal as a new record, the deviation in the hypothesis detail: done (`ProtocolRecordTests`, the UI tests above). On the result card and in the Word report: 37.0b. |
| AC-9 | done | `NextActionTests`, `NextActionBarTests`, `test_the_next_action_walks_through_the_steps_of_h1`. Without a plan, a project with results gets the Stage 34.5 cards: `NextActionTests.test_without_a_plan_the_stage_34_order_stays`. |
| AC-10 | partly | The Stage 36 baselines are unchanged (`test_stage36_ux_baseline` passes: 8, 2, 8, 8, 2, 1, 3). The 37.0 flow counts are not measured; they are 37.0b with `STAGE37_UX_RESULTS.md`. |
| AC-11 | partly | Migration, backup and refusal by format 5: `FormatSixTests`. The copy for an older version: not in 37.0a. |
| AC-12 | done | `test_stage37_ui.AiContextTests.test_the_ai_plan_preview_keeps_the_stage_36_fields` |
| AC-13 | done | `test_workspace_foundations.test_every_key_has_three_languages_with_the_same_placeholders`, `test_locale_audit` (missing 0, placeholder 0; the audit counts are unchanged) |
| AC-14 | partly | Labelled buttons, and typing keeps every character (no re-render: `test_typing_never_rebuilds_the_page`). The hypothesis rows are containers: the keyboard reaches their *Show details* button, not the row. The browser state check `plan-type-hypothesis` was not run. |
| AC-15 | not done | 37.0b |
| AC-16 | not done | The Windows journey `stage37-hypothesis` is 37.0b. No workflow or journey file was changed. |
| AC-17 | not done | Manual, the owner's |

## 4. Data keys as built (for the harness and the journeys)

The design's §7.10 names are proposals. 37.0a uses these:

- **Project page.**
  - Next-action bar: `project-next-action` (kept), `next-body`, `next-why`, `next-why-list`, `next-why-{i}`.
  - Next-action buttons:
    - kept: `next-open-data`, `next-sample`, `next-questionnaire`, `next-draft`, `next-levels`, `next-analyze`, `next-results`, `next-report`;
    - new: `next-question`, `next-add-hypothesis`, `next-save-plan`, `next-create-analysis`, `next-open-task`, `next-show-check`, `next-review`, `next-note`, `next-skip-note`, `next-add-report`.
  - Plan card:
    - questions: `plan-add-question`, `plan-q{i}`, `plan-q{i}-text`, `plan-q{i}-type`, `plan-q{i}-add-hypothesis`, `plan-q{i}-remove`;
    - hypothesis fields: `plan-h{i}-question`, `plan-h{i}-method_key`, `plan-h{i}-variant`, `plan-h{i}-reason`;
    - every Stage 35 `plan-*` key is kept.
  - Hypotheses card `project-hypotheses`:
    - the row `hyp-{n}` (n = 1 for H1), with `hyp-{n}-line`, `-standing`, `-steps`, `-open` and `-toggle`;
    - tasks: `hyp-{n}-open-task-{k}`, `hyp-{n}-steps-{k}`, `hyp-{n}-create-task`;
    - checks: `hyp-{n}-check-{j}` with `-text`, `-state` and the decision buttons `-acknowledge`, `-deviation`, `-justify`, `-review`, `-recalculate`, `-create-task`;
    - the record form: `hyp-{n}-form`, `hyp-{n}-what`, `hyp-{n}-reason`, `hyp-{n}-save`, `hyp-{n}-cancel`, `hyp-{n}-message`;
    - free deviation: `hyp-{n}-record-deviation`;
    - records: `hyp-{n}-record-{r}` and its `-withdraw`;
    - history: `hyp-{n}-history-{v}`.
- **Analyze.** `task-hypothesis`, `task-hypothesis-note`, `task-steps`, `task-steps-{step}`. The task chips keep `task-{id}`.
- **Results.** `result-hypothesis`.

## 5. Changes to existing behaviour, and why

1. **Project format 5 → 6.** `SCHEMA_VERSION` is 6. Opening a format-5 project migrates it after a backup in `.backups/`. The RC (format 5) refuses a format-6 project and writes nothing (default 1). `tests/test_stage368_review.test_the_project_format_is_unchanged` now expects 6; its comment says that K2's entries still use format-5 storage.
2. **A priority changed after results needs a reason.** `save_plan` raises `DesignationReasonNeeded` and saves nothing. The plan card says so in the interface language and shows a reason field. Before, a silent change was possible.
3. **The project page's next card.**
   - It is now first on the page, above the Question card.
   - Without a plan it keeps the Stage 34.5 order, texts and keys, with two additions:
     - a secondary *Start with the research question* button (`next-question`) on the *add the data* and *choose an analysis* cards;
     - after the report is exported, *The report is exported* (`next.done`) with *Open the report* (before, *export* stayed).
   - With a started plan, the rules N1–N6 come first (default 3: the strict "added after results" rule is kept).
4. **Analyze.**
   - A task that tests a hypothesis shows `H1 · ` before its title.
   - Step 1 shows *Tests hypothesis* when the project's saved plan has hypotheses.
   - A step-status row sits above step 1.
   - A task made from a hypothesis is named *Analysis for H1* until its first run, then after the analysis, as before.
   - Choosing another goal for such a task, while it has never run, keeps the task and its link. Every other task still starts a new task, as before; the new analysis is offered the old task's hypothesis.
5. **Results.** The detail shows *Tests H1* for a result calculated as a test of a hypothesis.
6. **Reports.** A successful export is logged as `report_exported`. The documents themselves are unchanged.
7. **Not changed** (as instructed):
   - engines, `analysis_runs`, the installer, the updater, workflows and locks;
   - every existing text, which keeps its key and its English wording;
   - the Stage 36 interaction baselines.
   - Engines stay two-sided, and the plan's α is not passed to them (defaults 4, 5).

**A note on texts.** Every new interface text is a key. The store's new error messages are English, like the store's existing ones (for example "Give the reason: it is kept with the record."). The interface checks a reason before it calls the store, so these appear only through `hyp.not_recorded` or `plan.invalid`, after an input that the interface did not catch.

## 6. LV and RU drafts: needs native review

All 173 new keys have LV and RU texts written as drafts. They are marked in `workspace_text.py` ("LV/RU drafts — needs native review") and need a native speaker's review before a release (default 13). No existing text was changed. By group:

- `hyp.draft.h1.*` (6), `hyp.draft.h0.*` (5): the H1 hints and the H0 drafts per question type.
- `check.*` (20): the texts of the 15 checks.
- `steps.*` (9), `steps.state.*` (5): the step names and states.
- `next.*` (32), `next.why.*` (22): the next-action rules and *Why this step?*.
- `plan.questions`, `plan.questions_body`, `plan.reason_needed`, `plan.q.*` (5), `plan.h.*` (6): the typed plan.
- `hyp.*` (24), `hyp.check.*` (5), `hyp.form.*` (4), `hyp.what.*` (9), `hyp.record.*` (8): the hypothesis workspace.
- `task.tests_hypothesis`, `task.no_hypothesis`, `task.hypothesis_gone`, `task.title_for`, `task.steps`, `task.linked`: Analyze.
- `results.tests`, `results.tests_detail`, `results.tests_gone`, `results.linked_late`: Results.

## 7. 37.0b

**Built on `claude/stage37-0b`:** `docs/STAGE37_0B_STATUS.md` gives the status of each item below, the review findings added to it, and the test that proves each. The measured counts are in `docs/STAGE37_UX_RESULTS.md`.

- The plan card's editor for the planned variables by role.
- The Word report's hypothesis lines (§7.10, AC-3, AC-8, AC-15).
- The journey-strip statuses (AC-5).
- The next-action bar on the other pages, and the secondary plan link after results.
- The review and the note inside the batch result card.
- Step 4's plan checks.
- The Windows journey `stage37-hypothesis` (AC-16).
- The measured 37.0 counts (AC-10) and the copy for an older version (AC-11).
