# Research projects, researcher profile and AI permissions — architecture (Stage 34, issue #24)

Status: **storage layer implemented** (`project_store.py`, `tests/test_project_store.py`);
interface, profile and AI-permission screens follow in separate pull requests.
Nothing here uploads anything; there is no account and no server.

## 1. Goals and non-goals

Goals
- Independent, persistent research projects that survive restarts and can be
  created, opened, switched, duplicated, archived, deleted (recoverably), backed
  up and restored.
- Each project links its research questions, datasets, variable decisions,
  preparation steps, questionnaires, analysis history, charts and report.
- Statistical provenance for every saved result, and an explicit **stale**
  state when the data or a measurement decision changes afterwards.
- Existing questionnaires and published responses stay exactly where and as
  they are.

Non-goals (this stage)
- Cloud sync, accounts, sharing between users, concurrent multi-user editing.
- Encryption at rest (see §11 — not implemented, not claimed).
- Any change to the statistical engine. Projects store what the engine
  produced; they never recompute differently.

## 2. Concepts

| Concept | Meaning |
|---|---|
| Project | A study: title (only required field), description, research area, population notes, language, design, status (active/archived), timestamps, active dataset. |
| Research question | Ordered list of questions or hypotheses (free text). |
| Dataset | A table used in the project. Four origins: **copy** (bytes of an imported file stored in the project), **link** (reference to the researcher's original file, re-checked on use), **derived** (prepared data stored as CSV), **survey** (responses exported from a linked questionnaire). |
| Dataset version | Every content change gets a row: SHA-256, size, rows/columns, reason. Old copies stay on disk. |
| Variable decision | Confirmed measurement level per variable and where it was confirmed. |
| Preparation step | A recorded, non-destructive transformation (kind, parameters, output columns). |
| Questionnaire link | Survey id + title; the questionnaire itself stays in the survey storage. |
| Analysis run | One saved result: method, variable roles, options, confirmations, levels used, dataset version, report text + SHA-256, summary, interpretation, warnings, tables, chart, software versions, time. |
| Report | Ordered selection of runs. |
| Activity log | Append-only events (created, dataset added/changed, run saved, exported, restored, recovered …) for a supervisor review view. |

## 3. Where data lives

`project_data_root()` places projects next to the questionnaire storage
(`startup_diagnostics.survey_data_root`), with one deliberate difference: a
packaged build that still reads older questionnaires from an unpacked preview
folder keeps its projects in the per-user data folder anyway.

| Situation | Questionnaires | Projects |
|---|---|---|
| `SRA_DATA_DIR` set | `$SRA_DATA_DIR/surveys` | `$SRA_DATA_DIR/projects` |
| Source checkout | `<repo>/data/surveys` (git-ignored) | `<repo>/data/projects` |
| Packaged build | Flet's per-user data folder `/surveys` | same folder `/projects` |

Never the install folder: a new version extracted elsewhere keeps every project.

```
projects/
  <project-id>/                 one self-contained folder per project
    project.sqlite3             everything structured (schema below)
    datasets/<sha256><ext>      imported copies, content-addressed, immutable
    datasets/<sha256>.schema.json  column types of a table the project wrote as CSV
    figures/<run-id>.png        chart of each saved run
    project.lock                while an app instance has it open
  .trash/<id>-<timestamp>/      deleted projects (restorable)
  .backups/                     database copies taken before a migration
  .new-<id>/                    staging during create/duplicate/restore
```

**Stored tables read back identically.** A table that exists only in memory
(the loaded table with its import options applied, prepared data, questionnaire
responses) is written as plain CSV plus a small JSON schema with each column's
type, the categories of categorical columns and which text cells were missing
rather than empty. CSV text alone would not survive a reopen: `"01"` would
become `1`, the text `"NA"` would become missing, integers would become floats
and `0.1 + 0.2` would be rounded. With the schema the reopened table is equal
to the original (`test_stored_copies_read_back_as_exactly_the_same_table`);
the only documented loss is a column mixing numbers and text in one object
column, which is read back as text. Original files the researcher imported keep
their own format and are read with the normal importer.

**No separate catalog.** The project list is the set of folders; each
`project.sqlite3` describes itself. A catalog database would be a second
source of truth that can disagree with the folders after a crash or a manual
copy. Listing reads one small row per project (milliseconds each), and search
filters titles, descriptions and research areas.

## 4. Schema (format 2, `PRAGMA user_version = 2`)

`project` (one row) · `research_questions` · `datasets` · `dataset_versions` ·
`variables` · `transformations` · `questionnaires` · `runs` · `report_items` ·
`events` (format 1), plus `ai_permissions` and `project.data_anonymous`
(format 2, §12). Foreign keys are enforced; deleting a dataset keeps its runs (their
`dataset_id` becomes NULL, which makes them stale, never silently gone).

**The researcher's entries (Stage 36.8, no new format).** They use storage
that format 5 already has, so `user_version` stays 5 and no migration runs:

| Entry | Stored in | A format-5 program (e.g. 36.7) |
|---|---|---|
| Interpretation note of a result | `runs.note` (a format-1 column, unused until now) | opens the project, does not show the note |
| Assumption checks marked as reviewed | `runs.provenance` JSON, key `reviewed` | ignores the key |
| Report title, sections left out, report language | the latest `events` entry of kind `report_settings` | ignores the entry; shows its defaults and cannot save them |
| What each design-step confirmation was given for | `research_tasks.state` JSON, key `confirm_scopes` | ignores the key and ticks the task's confirmations as before |

When such a program recalculates an omnibus result with post-hoc tests it
stores a new run without the note and the reviewed checks, so those two are
lost for that result. A confirmation without a recorded scope (any task saved
before Stage 36.8) is asked again: nothing says which data, variables and
method it was given for.

**Format 6 (Stage 37.0a): the research protocol.** One additive table and
optional JSON keys (docs/STAGE37_DESIGN.md §8); nothing existing is altered.

| Entry | Stored in |
|---|---|
| The researcher's decisions about the plan: a priority changed after results (with its reason), a task linked to a hypothesis, a check acknowledged, a deviation from the plan, a justification, the withdrawal of one of them | `protocol_records` (append-only: triggers refuse `UPDATE` and `DELETE`; a withdrawal is a new record naming the one it withdraws) |
| Typed research questions; a hypothesis's question, intended method, planned variables and expected group | the plan JSON in `plan_versions` (`plan_format: 2`, kept only when used) |
| The hypothesis a result was calculated for (plan version, priority, direction, α) | `runs.provenance` JSON, key `hypothesis` |
| Which hypothesis a task tests | `research_tasks.hypothesis_id` (a format-4 column, filled from 37.0a on) |
| Steps of a task skipped by the researcher | `research_tasks.state` JSON, key `skipped` |
| The last export of the report | the latest `events` entry of kind `report_exported` |

A format-5 program (the 36.8 release candidate) lists a format-6 project but
refuses to open it without writing anything (`migrate` reads the format
through a read-only connection first). A format-5 project opens in 37.0a
after its copy in `.backups/<id>-v5-<time>.sqlite3` (tests in
`tests/test_stage37_store.py`).

## 5. Integrity

- **Transactions.** Every change is one SQLite transaction (WAL journal,
  `synchronous=FULL`); a crash leaves the previous consistent state.
- **Atomic files.** Dataset copies, figures and backups are written to a
  temporary file, flushed, `fsync`ed and renamed into place.
- **Staging.** Create, duplicate and restore build the whole project in
  `.new-<id>` and rename it at the end; a half-finished folder is ignored.
- **Locks.** `project.lock` records process id, host and time. A second
  instance gets *ProjectLocked* (it may open the project read-only). A lock
  whose process no longer exists is replaced and logged as *recovered*, and the
  interface shows "the project was not closed properly". Archive, delete and
  move are refused while a project is open.
- **Recoverable delete.** Delete moves the folder to `.trash`; restore moves it
  back. Permanent removal will be a separate, explicitly confirmed action (planned).

## 6. Migrations

- On open the lock is taken first, then `migrate()` compares `user_version`
  with `SCHEMA_VERSION`.
- Older: the database is copied to `.backups/<id>-v<old>-<time>.sqlite3` with
  the SQLite backup API, then all migrations run in **one explicit
  transaction** (`BEGIN IMMEDIATE` … `COMMIT`, `ROLLBACK` on any error).
  Python's `sqlite3` does not open a transaction before `CREATE`/`ALTER`, so
  without the explicit `BEGIN` a failure halfway left a half-changed database
  still marked with the old format, which then could not be opened again
  (found by `test_a_failed_migration_leaves_the_old_format_untouched`).
- Format 1 → 2 is a real migration (`_migrate_v2`): it adds the AI permission
  table and the anonymity statement, all off; a project written by format 1
  opens with its data unchanged (`test_a_format_1_project_is_migrated_to_format_2_with_everything_off`).
  A format-1 application refuses a format-2 project with the message above.
- Newer (saved by a later version): refused with a clear message; nothing is
  changed. Read-only opening stays possible.
- Rule for future versions: a migration is a function `(db) -> None` using
  `execute()` only (`executescript()` would commit the transaction); tests
  simulate the next format and verify the backup and the data.

## 7. Provenance, staleness, reproduction

- A run stores the dataset's SHA-256 at calculation time, the measurement
  levels it relied on, roles, options and confirmations, the report text and
  its SHA-256, and Python/library versions (`app_build` from `SRA_BUILD_ID`).
- **Stale** = the dataset's current SHA-256 differs, the dataset was removed,
  or a relied-on measurement level changed. The reasons are listed; the run is
  kept.
- Linked files are re-hashed on use (`check_source`): *unchanged*, *changed*
  (new version recorded → dependent runs stale), *missing* (the interface asks
  the researcher to locate the file; `relink` compares content).
- **Reproduction**: because the exact data version and inputs are stored, a
  saved run can be recalculated with `workspace_methods.run_method`; the test
  suite checks that the recalculated report has the same SHA-256 after a
  restart.
- **On opening a project** saved results appear at once from their stored
  report, tables and chart. A background check (`ProjectBinding.verify_restored`)
  then recalculates each one on the exact dataset version it used. When the
  report SHA-256 matches, the full engine result object is restored; when it
  does not, the result is marked "recalculating it gives a different report"
  and is never silently replaced. Word export and post-hoc tests need that
  object, so they run the same check first; an unreproducible result can still
  be copied or saved as text, but no Word file is built from it.
- A follow-up of a saved result (post-hoc pairs of an omnibus test) is stored
  with the data version of the result it extends, not the current one.
- A calculation that finishes after the researcher switched project or loaded
  other data is discarded with a message, so a result is never filed against
  data it was not calculated on.
- `report_text()` refuses stale runs unless the caller explicitly allows them,
  in which case each one is labelled STALE with its reasons.
- `reproducibility_appendix()` lists dataset version, variables, options,
  levels, confirmations, report hash, software versions and status per run.

## 8. Backups (`.sra`)

A ZIP with `manifest.json` and:

| Path | Content |
|---|---|
| `project/project.sqlite3` | consistent snapshot (SQLite backup API) |
| `project/datasets/*`, `project/figures/*` | stored copies and charts |
| `surveys/survey_<id>.sqlite3` | linked questionnaires with their responses (optional; the interface asks) |

The manifest lists format, format version, schema version, project id/title,
included questionnaires, software versions and **size + SHA-256 of every
file**.

Import checks, in this order, and stops without touching anything on failure:
not a ZIP, more than 20 000 files, more than 4 GiB uncompressed, duplicate
names, absolute/`..`/backslash/drive-letter paths, symlink entries, compression
ratio above 250 on large entries (archive bombs), missing or foreign manifest,
newer format, invalid project id, files not exactly matching the manifest,
size or checksum mismatch, missing database. Restore never overwrites:
- an existing project id → restored as a separate copy titled "(restored)";
- an existing questionnaire with other content (e.g. newer responses) → the
  existing file is kept and a warning names it; an identical one is accepted.

## 9. Existing questionnaires (migration)

The survey storage (`survey_<id>.sqlite3` per questionnaire: definition and
responses) is not migrated, moved or rewritten. Projects **link** survey ids.
The first-run experience offers, explicitly, "Link your existing questionnaires
to a project"; nothing happens automatically. Tests verify byte-identical
survey files after linking, exporting, duplicating and deleting projects.

## 10. Researcher profile (`researcher_profile.py`, Settings)

A single optional local file, `profile/profile.json` beside `projects/`
(`{"format": 1, "profile": {...}}`, written atomically). Fields, all optional:
name to show, study level (bachelor/master/doctoral/academic staff/other/
prefer not to say), research field, experience with statistics
(new/some/experienced), preferred language, explanations
(brief/standard/detailed). An empty profile keeps no file. Values outside the
offered choices, line breaks, more than 80/120 characters and anything that
looks like an e-mail address are refused with a message; it never stores
institution or student IDs or sensitive demographics. A damaged or newer file
is read as far as it is understood and never stops the application.

What it changes — and nothing else:

| Field | Effect |
|---|---|
| experience = experienced | Home starts without the "How it works" introduction (still in Help) |
| explanations = detailed | each result's interpretation section starts open |
| language | the interface language; the language switch keeps it equal |
| study level, research field | stored only; never used to judge work, choose a method or change a result |

Deleting the profile changes no project, and projects never write into it
(`test_deleting_the_profile_leaves_every_project_untouched`). Reporting style
and accessibility preferences (text size, reduced motion) are not in this
version.

## 11. Privacy and security

- Local only: no network calls in the project layer, no telemetry.
- Encryption at rest is **not** provided and not claimed. Researchers handling
  sensitive data should keep the data folder on an encrypted disk (BitLocker /
  FileVault). A later option could add passphrase-protected `.sra` exports with
  an authenticated cipher (AES-GCM) — that needs a vetted crypto dependency, a
  recovery story (a lost passphrase loses the data) and review; not in scope.
- Backups may contain personal response data; the export dialog must say so.

## 12. AI context permissions (`ai_context.py`)

Settings → AI assistance shows whether a provider is connected, the context
sources with their state for the open project (all "Off" by default), a
switch for each, the statement that the project's data rows identify nobody
and, for each source, a preview of exactly what it would contain now, built
locally (the test blocks every socket while building it). Until Stage 36 a
global `AI_AVAILABLE = False` refused every request; since Stage 36.6
`check_request()` refuses unless the assistant is set up (a provider, a model
and the researcher's key in the OS store, `ai_context.readiness`), and the
assistant itself is described in [STAGE36_AI_ASSISTANT.md](STAGE36_AI_ASSISTANT.md).
Decisions are stored per project (format 2: `ai_permissions`,
`project.data_anonymous`), travel with `.sra` backups and are logged in the
activity log. Stage 36 added a seventh source, the research plan (design and
hypotheses with whether each was planned before results were seen). The
contract:

| Context source | Default | Notes |
|---|---|---|
| Project title, research questions | off | free text the researcher wrote |
| Variable dictionary (names, levels) | off | no values |
| Aggregated results (reports, tables) | off | numbers already in reports |
| Questionnaire wording | off | may be copyrighted; licence reminder |
| Raw data rows | off, cannot be enabled together with any remote provider unless the project's privacy note says the data is anonymous | |
| Profile fields | off | explanations, experience and language only — never the name or study level, never used to infer ability |

Rules: nothing is sent without a visible, editable context preview and a
confirmation per request; the provider and region are shown; every transfer
is logged in the project's activity log; switching projects clears the
context; no model inference from the profile's education level alone.

## 13. Interface

Implemented (`workspace_projects.py`, `project_session.py`):

- **Home** shows the current project (title, counts, "Saved automatically ·
  last change", results to review, *Back up…*, *Close project*) and the list
  of projects: **create** (title → *Create project*: two actions), *Open*,
  *Duplicate*, *Back up…*, *Archive* / *Return from the archive*, *Delete…*
  (asks first; moves to **Recently deleted**, restorable), *Show archived
  projects* and *Restore a backup…* (`.sra`, desktop path or browser upload).
- Work done before any project exists moves into the first project created;
  creating or opening another project starts from that project's own state.
- **Context bar**: "Project: <title>" (warning tone while results need review)
  or "No project" with the explanation that work is kept for this session only.
- **No save step.** Every session event is written at once: datasets (with
  their origin: file, sample, upload, questionnaire responses, prepared data,
  classic interface), confirmed levels, results with roles, effective options
  and confirmations, and the report selection. Loading the same file or the
  same questionnaire again records a new version of the same dataset. The
  researcher's note and reviewed checks of each result are saved as they
  change; the report's sections and language at once and its study title
  when the field is left, before an export and when the project closes or
  the program ends (Stage 36.8). Data → Prepare stores the prepared table as
  a derived dataset with its steps in `transformations`; the columns that are
  still there keep their confirmed levels.
- **Results**: stale results carry a "Review needed" badge and a notice with
  the translated reasons and *Recalculate with current data*, which opens the
  analysis form with the same method, variables and options but **without**
  the earlier confirmations — the researcher confirms the checks again for the
  changed data. The earlier result is kept.
- **Reports**: while selected results need review, export waits until they are
  recalculated or removed, or the researcher includes them explicitly; each is
  then labelled "Needs review: calculated before these changes: …".
- The project is closed (its lock released) when the application exits; only
  a real interruption shows the recovery message on the next start.
- Projects live in Flet's per-user data folder in a packaged build (§3); if
  that folder cannot be written, Home says so and the workspace keeps working
  without projects.

Planned: search across projects, a **supervisor review mode** (read-only view
of decisions, confirmations, provenance and the activity log — a view, not an
account or role), and novice/advanced explanations from the profile.

## 14. Acceptance mapping (issue #24)

| Criterion | Evidence |
|---|---|
| Two projects survive restart and switching, no mixing | `test_two_projects_survive_restart_and_switching_without_mixing` |
| Changed data makes results stale, never deletes them | `test_changed_source_data_marks_results_stale_without_deleting_them`, `test_new_version_of_a_copied_dataset_or_a_changed_level_makes_results_stale` |
| Recovery, backup/restore on a clean machine, migration, large data, missing paths | `test_an_abandoned_lock_is_recovered_and_logged`, `test_backup_restores_on_a_clean_machine_with_questionnaires`, `test_migration_backs_up_the_old_database_and_keeps_data`, `test_large_dataset_round_trip`, `test_missing_linked_file_can_be_relinked` |
| Existing questionnaires intact | `test_existing_questionnaires_are_untouched_by_project_operations`, `test_restoring_twice_never_overwrites_a_project_or_newer_responses` |
| Reproducibility | `test_saved_run_reproduces_the_same_report_from_the_project` |
| Create in two actions, reopen after restart, switch without mixing (interface) | `test_a_project_is_created_in_two_actions_and_saves_without_a_save_step`, `test_reopening_after_a_restart_restores_data_levels_results_and_report`, `test_switching_projects_from_home_keeps_their_work_apart` |
| Duplicate, archive, back up, delete, restore (interface) | `test_duplicate_archive_backup_delete_and_restore_from_home`, `test_a_backup_from_the_browser_arrives_as_bytes`, `test_a_damaged_backup_is_refused_with_a_message` |
| Stale warnings, recalculation with renewed confirmations, report gate | `test_changed_data_marks_results_and_holds_the_report_until_decided`, `test_recalculating_opens_the_analysis_and_asks_for_the_checks_again`, `test_loading_the_changed_file_again_keeps_old_results_reproducible` |
| Questionnaire responses as a versioned dataset; questionnaires untouched | `test_questionnaire_responses_are_one_dataset_with_versions` |
| Exact table round trip; unreproducible results never become Word files | `test_stored_copies_read_back_as_exactly_the_same_table`, `test_a_result_that_cannot_be_reproduced_is_not_exported_as_word` |
| No result filed against the wrong data | `test_a_result_finished_after_switching_projects_is_not_filed_in_the_new_one`, `test_work_started_without_a_project_moves_into_the_first_one_created` |
| Optional local profile, independent of projects | `test_the_profile_is_optional_and_round_trips`, `test_values_outside_the_offered_choices_or_personal_identifiers_are_refused`, `test_deleting_the_profile_leaves_every_project_untouched`, `test_the_profile_is_filled_saved_and_applied_after_a_restart` |
| AI permissions: project-scoped, off, nothing sent | `test_every_source_is_off_and_no_request_can_be_made_without_a_provider`, `test_readiness_needs_a_model_and_a_key_in_the_os_store`, `test_rules_a_future_assistant_must_pass`, `test_the_ai_card_allows_sources_per_project_and_rows_need_the_statement`, `test_permissions_travel_with_the_project_backup`, `test_previews_show_exactly_what_would_be_shared_and_use_no_network` |
| Accessibility, packaged smoke | screenshot suite (`home_projects`, `settings_profile`); Windows CI runs `test_project_*.py` |

The project tests also run on the Windows CI runner (locks, renames, file URIs).
