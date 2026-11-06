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
(`startup_diagnostics.survey_data_root`):

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
    figures/<run-id>.png        chart of each saved run
    project.lock                while an app instance has it open
  .trash/<id>-<timestamp>/      deleted projects (restorable)
  .backups/                     database copies taken before a migration
  .new-<id>/                    staging during create/duplicate/restore
```

**No separate catalog.** The project list is the set of folders; each
`project.sqlite3` describes itself. A catalog database would be a second
source of truth that can disagree with the folders after a crash or a manual
copy. Listing reads one small row per project (milliseconds each), and search
filters titles, descriptions and research areas.

## 4. Schema (version 1, `PRAGMA user_version = 1`)

`project` (one row) · `research_questions` · `datasets` · `dataset_versions` ·
`variables` · `transformations` · `questionnaires` · `runs` · `report_items` ·
`events`. Foreign keys are enforced; deleting a dataset keeps its runs (their
`dataset_id` becomes NULL, which makes them stale, never silently gone).

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
  back. Permanent removal is a separate, explicitly confirmed action (UI PR).

## 6. Migrations

- On open the lock is taken first, then `migrate()` compares `user_version`
  with `SCHEMA_VERSION`.
- Older: the database is copied to `.backups/<id>-v<old>-<time>.sqlite3` with
  the SQLite backup API, then all migrations run in **one** transaction.
- Newer (saved by a later version): refused with a clear message; nothing is
  changed. Read-only opening stays possible.
- Rule for future versions: a migration is a function `(db) -> None` using
  `execute()` only (so it stays inside the transaction); tests simulate a v2
  migration and verify the backup and the data.

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
  restart. Word export of a saved run uses this path (UI PR), so a Word file is
  never built from stale numbers.
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

## 10. Researcher profile (separate PR)

A single optional local file (`profile/profile.json` beside `projects/`):
display name, study level (bachelor/master/doctoral/faculty/other/not said),
research field, methodological experience (new/some/experienced), preferred
language, explanation depth (brief/standard/detailed), reporting style,
accessibility preferences (theme, text size, reduced motion). Every field is
optional and the profile may stay empty. It never stores institution IDs,
e-mail addresses or sensitive demographics. Deleting it does not touch any
project; projects never write into it. A project's own language/design fields
override profile preferences for that project.

## 11. Privacy and security

- Local only: no network calls in the project layer, no telemetry.
- Encryption at rest is **not** provided and not claimed. Researchers handling
  sensitive data should keep the data folder on an encrypted disk (BitLocker /
  FileVault). A later option could add passphrase-protected `.sra` exports with
  an authenticated cipher (AES-GCM) — that needs a vetted crypto dependency, a
  recovery story (a lost passphrase loses the data) and review; not in scope.
- Backups may contain personal response data; the export dialog must say so.

## 12. AI context permissions (design only — AI is not connected)

The interface will show "AI assistance: not available in this version". The
data model prepares explicit, project-scoped, per-transfer consent:

| Context source | Default | Notes |
|---|---|---|
| Project title, research questions | off | free text the researcher wrote |
| Variable dictionary (names, levels) | off | no values |
| Aggregated results (reports, tables) | off | numbers already in reports |
| Questionnaire wording | off | may be copyrighted; licence reminder |
| Raw data rows | off, cannot be enabled together with any remote provider unless the project's privacy note says the data is anonymous | |
| Profile fields | off | explanation preferences only, never used to infer ability |

Rules: nothing is sent without a visible, editable context preview and a
confirmation per request; the provider and region are shown; every transfer
is logged in the project's activity log; switching projects clears the
context; no model inference from the profile's education level alone.

## 13. Interface (next PR)

- **Project Hub** becomes Home: New project (title → Create: two actions),
  Recent, Open/restore backup, Archived, Samples, search.
- **Active project bar**: project title, active dataset, save state ("Saved"
  after each change — every action is persisted), switch project, back up.
- Switching is refused while a calculation or OCR job runs (or asks to wait).
- Results and Reports read runs from the project; stale runs carry a badge with
  reasons and a *Recalculate* action; the combined report blocks stale runs.
- **Supervisor review mode**: a read-only view of decisions, confirmations,
  provenance and the activity log — a view, not an account or role.
- Novice/advanced explanations come from the profile, overridable per project.

## 14. Acceptance mapping (issue #24)

| Criterion | Evidence |
|---|---|
| Two projects survive restart and switching, no mixing | `test_two_projects_survive_restart_and_switching_without_mixing` |
| Changed data makes results stale, never deletes them | `test_changed_source_data_marks_results_stale_without_deleting_them`, `test_new_version_of_a_copied_dataset_or_a_changed_level_makes_results_stale` |
| Recovery, backup/restore on a clean machine, migration, large data, missing paths | `test_an_abandoned_lock_is_recovered_and_logged`, `test_backup_restores_on_a_clean_machine_with_questionnaires`, `test_migration_backs_up_the_old_database_and_keeps_data`, `test_large_dataset_round_trip`, `test_missing_linked_file_can_be_relinked` |
| Existing questionnaires intact | `test_existing_questionnaires_are_untouched_by_project_operations`, `test_restoring_twice_never_overwrites_a_project_or_newer_responses` |
| Reproducibility | `test_saved_run_reproduces_the_same_report_from_the_project` |
| Profile independence, EN/LV/RU, accessibility, packaged smoke | profile and UI pull requests |

The project tests also run on the Windows CI runner (locks, renames, file URIs).
