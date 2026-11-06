# Stage 34.5 findings: reproduced failures and root causes

Issues #30 and #31 list failures that the product owner found by testing the
packaged Windows application. Each one was reproduced **before** any code was
changed: either as a test that drives the real workspace controls through the
harness (`tests/workspace_harness.py`), or with a real browser that operates
the Flet web preview the way a person does (`tools/e2e_web_state.js`, run by
`tools/workspace_state_checks.py`). All of these checks were then run against
the unchanged code (commit `c840571`, the head of PR #29), and every one of
them failed there. Synthetic data only.

The scientific import engine part of #31 (PSQ-like bibliography, OCR of image
pages, stated item counts) is a separate pull request; it records its own
findings in `tests/test_import_integrity.py`.

## Summary

| # | Reported symptom | Root cause (confirmed) | Failing before the fix |
|---|---|---|---|
| 1 | Ticking a checkbox jumps the page to the top | Every `render()` put a **new** page tree into `Container.content`. Flet 1.x always replaces a single-child property whose object differs (`flet/controls/object_patch.py`), so Flutter dropped the scroll view and everything in it | browser: `results-scroll-then-check` moved the checkbox **1594 px** (= the scrolled distance); `StableRenderTests.test_the_page_container_keeps_its_key_across_renders` |
| 2 | Editing a field loses the caret and focus | Same replacement as 1; the Reports title also re-rendered the whole page on every keystroke | browser: `reports-type-title` focus on `FLUTTER-VIEW`, typed text lost; `test_typing_a_study_title_does_not_rebuild_the_page` (render called on each change) |
| 3 | Long questionnaires lose their place | Same as 1: selecting item 60 of 120 rebuilt the list from the top | browser: `questionnaire-120-item-60` the selected row left the viewport (`after_y: null`) |
| 4 | An opened section closes after a click inside it | `ExpansionTile` state lived only in Flutter and was discarded with the replaced tree | browser: `results-section-stays-open` (128 → 126 semantics nodes: collapsed again) |
| 5 | Opening or creating a project looks inert | **Open, Duplicate, Backup, Archive and Restore on Home did nothing at all** (found later by the packaged-EXE journeys, see below). Also `ProjectHub.open/create` re-rendered Home; only a small card above the project list changed | `ProjectWorkspaceTests` (2); with Flet's event dispatch, 6 project tests and the browser check `projects-open-from-home` |
| 6 | Save TXT/PNG/Word/backup gives no visible outcome | **The Save TXT, PNG and Word buttons did nothing at all** (found later by the packaged-EXE journeys, see below). Also: (a) a cancelled dialog returned silently; (b) the writers require the extension (`.txt`, `.png`, `.docx`) and fail when the dialog returns the name as typed; (c) the outcome was only a notice at the end of the page, off-screen after 1; the status bar kept saying "Result ready."; (d) report and backup paths used `with_suffix`, so `wave.2` became `wave.txt` | `SaveOutcomeTests` (5): status stayed "Result ready." after a successful Word save; `typed-docx.docx`, `typed-txt.txt`, `typed-png.png` not written; no "cancelled", no folder guidance |
| 7 | "Analyze responses" replaces the active dataset | `QuestionnairesPage._analyze` called `session.set_dataset()` directly and named the table after the questionnaire, so the source, the form and its responses were indistinguishable | `DataSourceTests` (2) |
| 8 | Raw `block.level_mismatch` on screen | `run_method` raised `ValueError("; ".join(keys))`, which the page showed verbatim; and Guided Analysis offered methods that the method's own role checks then refused | `MessageTests` (2): "The analysis did not run: block.level_mismatch"; **762** advice/level combinations of `sample_ancova.csv` offered a method that was then blocked |
| 9 | Data acceptance is confusing | "Use suggestions" was disabled until a checkbox was ticked, with no reason shown; no next step after the levels were confirmed | `test_a_disabled_accept_button_says_why` |
| 10 | Legacy DOC fails without useful guidance | The document was half-opened (`source` kept, viewer shown) with "install antiword or save as .docx" — not actionable on Windows, English only, nothing in the status bar | `UnreadableDocumentTests` (3) |
| 11 | An imported questionnaire mixes with the draft | `load_draft()` replaced the builder's draft without asking and **kept the previous draft's title** (`if title and not self.title`); loading a template also replaced it (its confirmation was dead code) | `DraftGuardTests` (2 of 3; the empty-builder case already worked) |

### Found while fixing

| # | Symptom | Root cause | Check |
|---|---|---|---|
| 12 | After the stable rendering (1–4), a button that changes kind — "In report" → "Add to report", "Create project" after closing a project, the import wizard's current step — is drawn as Flutter's grey error box | The rebuilt button is now *patched* instead of replaced. Flet 1.x breaks the control when a patch **adds a key** to a per-state colour map: secondary buttons had `{default, hovered}`, primary `{default, hovered, disabled}`. A minimal Flet page reproduces it; with equal key sets it draws correctly | browser: `results-add-report-twice` (42.8 % grey, the button gone); `StableRenderTests.test_buttons_that_change_kind_can_be_patched` |

### Found later by the packaged-EXE journeys (#36)

The journeys could not open a project from Home, even through UI
Automation's Invoke. Their root cause is the primary cause of symptoms 5 and
6.

**Root cause.** Flet 1.x awaits an event handler only when the handler itself
is a coroutine function (`flet/controls/base_control.py`). Every other
callable is called and its return value is dropped. So a button wired as
`lambda e: self._save(entry, "docx")`, around an `async def`, hands Flet a
coroutine that never runs, and the button silently does nothing.

**What it hit.** 15 handlers, 12 of them already on `c840571`:
- Results: Save TXT, Save PNG, Save Word and Post-hoc;
- Home: Open (also after a restore), Duplicate, Backup, Archive and Restore deleted;
- the current-project Backup on Home and on the project page;
- "Use" for a data source and the data-source selector on Data;
- the questionnaire responses export.

**Why the tests passed.** `tests/workspace_harness.py` awaited any coroutine a
handler returned, which hid the bug.

**Fix.**
- **Handlers:** `workspace_components.handler(fn, *args)` builds an awaitable handler when `fn` is a coroutine function; the data-source selector got an `async def` handler.
- **Harness:** it now dispatches events exactly as Flet does and refuses a handler that hands Flet a coroutine.
- **Regression guard:** `EventHandlerTests` checks every module for a lambda around a coroutine function.

**Failing before the fix.**
- **Tests:** with Flet's dispatch, 18 tests (the Results saves, the project actions, the data sources and the responses export).
- **Browser:** `projects-open-from-home`: Open on Home showed nothing.

**After the fix.** All tests pass and Open opens the project.

## Fixes

1–4. **Stable reconciliation.** The page sits in a list
   (`WorkspaceApp._page_stack.controls = [Column(key="workspace-page-<route>")]`).
   A keyed list item is diffed structurally and keeps the identities of the
   controls on screen, so scroll offset, keyboard focus, caret, selection and
   expanded sections survive a re-render; another route still gets a fresh
   page. Expanded sections are remembered by their pages (`wc.expansion`,
   `wc.expansion_handler`). The Reports title updates its preview in place.
5. **Project page** (`workspace_projects.ProjectPage`, route `project`). Create
   and Open go there. It shows the title, the automatic-save state, the next
   step, the data sources by kind with the one in use, the project's
   questionnaires (draft and published, with collected responses), results and
   the report. The sidebar and the context bar lead back to it.
6. **One save path** (`WorkspaceApp.save_file`, `workspace_files.py`) for
   Results (TXT, PNG, DOCX), Reports (TXT), project backups (SRA) and
   questionnaire responses (CSV + JSON codebook): cancel is announced; the
   extension is appended, never swapped; the file is written in a worker
   thread and checked on disk (exists, not empty); the full path is announced
   in the status bar and next to the buttons; failures are explained with
   what to do (missing folder, read-only folder, file open in another program,
   protected folder, full disk, invalid name) and never show `[Errno …]`. An
   empty placeholder the desktop dialog may leave at the name as typed is
   removed. The next dialog opens in the last folder used.
7. **Explicit response datasets.** Analyzing responses asks first when another
   dataset is in use and says what happens to it; the new table is named
   "Responses: <questionnaire>". In a project both stay as data sources and
   either can be used again (project page, or the selector on Data), with its
   confirmed levels. A questionnaire published while a project is open
   belongs to it; Questionnaires lists the project's forms first.
8. **Translated blockers.** `RoleProblems` carries the problem keys to the
   page, which shows them in the interface language
   (`block.level_for_role`: the variable, its level, the role and the levels it
   accepts). `advise()` keeps a question's own explanation first and never
   offers a method its role checks would refuse.
9. **Disabled buttons say why** (accept, run, publish, export PNG, export
   report, create draft, re-read, open archived project); Data shows the next
   step (confirm levels → choose an analysis).
10. **Unreadable documents** are checked before anything changes: unsupported
    formats and `.doc` without a converter get a localized explanation with
    Word/LibreOffice "Save As .docx" steps, a status message and "Choose
    another document"; a document already under review stays.
11. **Drafts are never mixed.** Importing or loading a template into a builder
    that holds an unsaved draft asks first; a confirmed replacement replaces
    questions, title and instructions together.
12. **Patch-safe button styles.** Every button kind uses the same keys in its
    per-state colour maps (`wc._states`), so a kind change is patched cleanly.

## Verification

* `python -m unittest tests.test_workspace_p0_blockers tests.test_workspace_files tests.test_workspace_import_guard`
  — 25 tests: 28 failures and errors on `c840571` (19 failures, 9 errors), all pass now.
* `python tools/workspace_state_checks.py <out>` — 4 real-browser checks; all
  fail on `c840571` and pass now (also run in CI, job *workspace-screenshots*):

  | Check | Before | After |
  |---|---|---|
  | results-scroll-then-check | moved 1594 px | moved 0 px |
  | reports-type-title | focus lost, text lost | all 22 characters kept, focus in the field |
  | questionnaire-120-item-60 | selected row left the view | row stayed (0 px), caret kept while editing |
  | results-section-stays-open | collapsed again | still open |
  | results-add-report-twice | (not applicable before the stable rendering) | grey error box without the style fix; draws correctly with it |

* The full suite runs on Linux and Windows CI; statistics are untouched (the
  engine, `analysis_runs` and the parity tests are unchanged).

## Still to confirm on the packaged Windows application

The tests above drive the workspace through Flet's Python controls and a
browser. Behaviour that only the native Windows client shows — the Win32
save dialog (does it append the filter's extension?), 125/150 % display
scaling and real UI Automation focus — is checked by the packaged-EXE GUI
end-to-end tests (Stage 34.5, Priority 1), not by these tests.

## Found by the packaged-EXE journeys

`tools/windows_gui_e2e.py` drives the distributed executable through Windows
UI Automation, the interface a screen reader uses. Its runs found three
defects that the Python-control tests could not see: those tests read each
control's value directly, cannot tell where a row ends up on screen, and
awaited every coroutine a button returned. The dropped coroutines are the
primary cause of symptoms 5 and 6 and are recorded with them above ("Found
later by the packaged-EXE journeys"); the other two follow.

| # | Symptom | Root cause (confirmed) | Failing before the fix |
|---|---|---|---|
| 13 | Several kinds of text are invisible to screen readers and to UI Automation: the status line ("Loaded …", "Saved to …"), every notice (for example "Published … on this computer." and error explanations), the dataset name, the row counts and the provenance values. A status change is never announced. | Flet renders `Text(selectable=True)` as Flutter's `SelectableText`, which stays out of the accessibility tree unless it has an explicit semantics label. The status line, the body of every notice, the stat values and the labelled values are all selectable. | **Packaged EXE (run 7):** the Data page showed the loaded dataset, but no element carried "Loaded sample_ancova.csv." or the published-questionnaire notice. **Browser:** the stat value `sample_scale.csv` had no node, and `data-status-announced` announced nothing (`[]`). **Tests:** `SelectableTextAccessibilityTests` had 3 failures (no accessible name). |
| 14 | Going through a long questionnaire in the import review, clicking the next item (61) while item 60 is open makes the clicked row jump up by about 560 px, away from the pointer. | The selected item's editor opens under its row. Selecting a row below it closes that editor *above* the clicked row, so the content above it shrinks by the editor's height. | **Packaged EXE (run 9):** item 61 moved −561 px. **Browser:** `import-120-next-item` moved −559 px. **Tests:** `test_the_next_row_clicked_stays_under_the_pointer` errored (no measured editor). |

**Fix (13).** `workspace_components.text(..., selectable=True)` gives the text
itself as the semantics label. `workspace_components.set_text` keeps the
label in step when a text changes in place, as the status line and the
report preview do.

**Fix (14).** The editor reports its laid-out height (`on_size_change`). When
a row below the open editor is clicked, the page scrolls up by exactly that
height (`WorkspaceApp.scroll_page`), so the clicked row stays where it was.
"Next item to check" keeps bringing the next item to where the editor was.

**After the fixes.**
- **Next item:** item 61 stays in place (0 px), both in the browser and in the test.
- **Selectable texts:** every selectable text on every page carries its text as its accessible name. Selection with the mouse is unchanged.
- **Announcements:** confirming the levels is announced as "5 levels confirmed from suggestions.".
- **Checks:** the 4 tests and the 2 browser checks pass.
