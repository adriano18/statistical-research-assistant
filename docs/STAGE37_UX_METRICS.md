# Stage 37 — UX metrics: the baseline of eight tasks (Issue #68)

> **Status: baseline only.** No interface code changes here. The numbers below were measured on the application code of `2f9af71` (`stage37/master-acceptance-interoperability-spec`) with `tools/ux_metrics.py`, which this branch adds. Synthetic data only: the Stage 37 master fixture and the Stage 36 UCLA/SACS-shaped CSV, both generated into a temporary folder. Scroll distances are **estimates**, not measurements (§4.5).

## 1. Command

```bash
# from the repository root, locked environment (Python 3.12, Flet 1.1.2)
MPLBACKEND=Agg PYTHONUTF8=1 python tools/ux_metrics.py --json ux-metrics.json --markdown ux-metrics.md
# the window the program opens with at every start (app.py, review D2)
MPLBACKEND=Agg PYTHONUTF8=1 python tools/ux_metrics.py --width 1200 --height 720
```

- One run takes about 25 seconds on Linux.
- Two runs give byte-identical JSON and Markdown: project and task ids are replaced by `<id>` in the step log.
- `--keep DIR` keeps the generated fixtures and the project folder for inspection.
- `tests/test_stage37_ux_metrics.py` runs the tool once and checks its output for consistency. It also checks the counter, the focus-loss detector and the layout estimate. It does not pin the baseline numbers, because the UX work is meant to change them.

## 2. Baseline

Window 1440 × 800 (the harness default, as in the Stage 36 and 37.0 baselines). The estimated scroll viewport is 658 px.

| # | Persona | Task | Fixture | Interactions (click · box · dropdown) | Typed | Pages | Dialogs | Repeated selections | Focus losses | Scroll px (estimate) |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| T1 | novice | First start to an open project with data | master (180 × 98) | 3 (3 · 0 · 0) | 1 | 3 | 1 | 0 | 0 | ≈ 162 |
| T2 | novice | Confirm the measurement levels of the 98 variables | master (180 × 98) | 4 (1 · 1 · 1) | 0 | 0 | 0 | 0 | 0 | ≈ 5,440 |
| T3 | novice | Define and score one 20-item scale, check its reliability | master, `SYN_LON_01`–`20` | 51 (6 · 41 · 2) | 1 | 2 | 0 | 20 | 0 | ≈ 5,312 |
| T4 | novice | Eight correlations in one batch, add them to the report | Stage 36 (55 × 13) | 10 (7 · 1 · 1) | 0 | 1 | 0 | 0 | 0 | ≈ 1,146 |
| T5 | supervisor | Repeat a previous analysis with one variable changed | Stage 36: UCLA → UCLA_Level | 5 (3 · 0 · 1) | 0 | 1 | 0 | 0 | 0 | ≈ 780 |
| T6 | supervisor | Export the Word report | the project's report | 2 (2 · 0 · 0) | 0 | 1 | 1 | 0 | 0 | ≈ 0 |
| T7 | supervisor | Reopen the project after a restart, review every result | the project of T1–T4 | 4 (4 · 0 · 0) | 0 | 3 | 0 | 0 | 0 | ≈ 19,550 |
| T8 | supervisor | Change the language and the text size, continue | settings | 5 (5 · 0 · 0), text size **not available** | 0 | 3 | 0 | 0 | 0 | ≈ 210 |
| | **novice** | **total** | | **68** | **2** | **6** | **1** | **20** | **0** | **≈ 12,060** |
| | **supervisor** | **total** | | **16** | **0** | **8** | **1** | **0** | **0** | **≈ 20,540** |

Columns:
- **Interactions** follow the Stage 36 rule: a click or a checkbox is 1, a dropdown choice is 2. The breakdown counts dropdown choices, not their interactions.
- **Typed**, **Pages** (page changes) and **Dialogs** (Windows Open and Save dialogs) are counted apart from interactions, as in the Stage 37.0 design baseline.
- In scroll screens (scroll ÷ viewport) the estimate is 0.2 · 8.3 · 8.1 · 1.7 · 1.2 · 0 · 29.7 · 0.3 for T1 to T8.
- Full-page re-renders per task (in the JSON): 2 · 2 · 27 · 10 · 5 · 2 · 3 · 4.

### 2.1 At the start window, 1200 × 720

The program opens at 1200 × 720 at every start (`app.py`; the size is not kept, review D2). Below 1280 px the workspace uses its compact layout, and the estimated viewport is 578 px. The counts are the same as above except for one task:

| Task | 1440 × 800 | 1200 × 720 | Why |
|---|---:|---:|---|
| T7 | 4 interactions | **5** (3 · 0 · 1) | In the compact layout, Results lists the results in a dropdown (`results-picker`, 2) instead of the log (`result-<id>`, 1). |
| Scroll, novice / supervisor (estimate) | ≈ 12,060 / 20,540 | ≈ 13,436 / 21,520 | The window is smaller. |

Supervisor total at 1200 × 720: 17 interactions.

### 2.2 The order of the tasks

The eight tasks are one chain in one project. Each task starts where the previous one ended. This is what lets the tool count variables selected again, and what a restart loses.

| Session | Tasks, in run order | Start |
|---|---|---|
| 1, novice (first start) | T1 → T2 → T3 → *set-up* → T4 | `research_app.main`: the classic interface |
| 2, supervisor (a restart, same data folder) | T7 → T5 → T6 → T8 | the classic interface again |
| 3 (the next start) | T8, second part: back to the same language, project and page | the classic interface again |

- **Set-up (not counted).** As in `tests/test_stage36_ux_baseline.py`, the Stage 36 CSV is opened in the same project through the real `load_path`. Its 13 levels are then confirmed.
- **Personas.** T1–T4 are the novice's tasks and T5–T8 the supervisor's. The supervisor works on the student's project after a restart: they review the results first (T7), then ask for a variant (T5), export (T6) and switch language (T8).

## 3. What each task does

Controls are named by their `data` key. ⟨…⟩ marks what is counted apart.

- **T1, first start.**
  - Classic interface: *Open the preview* (`open-workspace-preview`, 1 click, 1 page change).
  - Home: `project-new-title` ⟨typed⟩, then `project-create`.
  - Project page: the next action *Open CSV / Excel…* (`next-open-data`) ⟨Open dialog⟩. The picker's real `on_result` handler receives `synthetic_master_research_n180.csv`, and Data opens.
  - Check: the project is open and the data is 180 × 98.
- **T2, measurement levels.**
  - The suggestions are 90 ordinal, 6 scale, 1 nominal and 1 id. One differs from the levels a careful researcher confirms: `sex_code` (0/1/2) is suggested as ordinal (review S7).
  - `level-sex_code` → Nominal (dropdown). The researcher then reads the dictionary to its last row, ticks `data-accept-confirm` and clicks `data-accept`.
  - Check: no level pending, and every level as intended.
- **T3, one 20-item scale.**
  - Data: `data-prepare` opens the hosted classic *Prepare data* panel. It has no `data` keys and English labels only (review D6), so the tool finds its controls by those labels.
  - In the panel: *Transformation* → *Create mean/sum scale score* (dropdown). Then 20 item boxes, ticked one by one in a 170-px inner list that offers 97 numeric columns.
  - *New variable name* `SYN_LON_MEAN` ⟨typed⟩, *Apply transformation*, *Use working copy in analysis*.
  - `level-SYN_LON_MEAN` → Scale (dropdown, row 99 of the dictionary).
  - Analyze: `nav-analyze`, `goal-scale`, then 20 boxes `role-items-SYN_LON_01…20` among 98 offered.
  - `design-confirm-one_construct`, then `guided-run`. Results opens, and the researcher reads the summary.
  - Check: the score equals the item mean (to 1e-9), and the result is item diagnostics of exactly these 20 items with α = 0.91.
  - The defaults are kept, including *Minimum answered items* = 3 (review S11).
- **T4, eight correlations.**
  - `nav-analyze`, then `task-new`: the reliability analysis of T3 is still on screen, which costs one click more than the Stage 36 flow.
  - `goal-relate`, `role-x` → UCLA (dropdown), `role-y-all-scale`, untick `role-y-Age`, `alt-batch_correlation-spearman`, `guided-run`. The researcher stays in the task.
  - `task-add-report`.
  - Check: a Spearman batch of UCLA with the 8 scales, in the report.
- **T7, reopen and review** (session 2).
  - *Open the preview*, `project-open-<id>` on Home, `nav-results`.
  - Read the result shown (the batch). Then `result-1`, and read it.
  - The 20-item item-diagnostics result is the long one: its "verified estimates" table has **282 rows** (14 values per item), followed by the 20-row item table. Reading it to its end is ≈ 13,100 px of the estimate.
- **T5, one variable changed.**
  - `nav-analyze`, then `task-<id>` (the batch task), `role-x` → UCLA_Level (dropdown), `guided-run`.
  - Spearman stays the recommendation for the ordinal variable, and the eight scales stay selected.
  - The run is stored **in the same task** (review D5: the task's variables are overwritten in place).
- **T6, Word report.**
  - `nav-reports`, then `reports-export-docx` ⟨Save dialog⟩.
  - The file is read back with python-docx: 4 tables, with the eight scales present.
- **T8, language and text size.**
  - The top bar's `context-language` → LV (1 click).
  - **There is no text-size control** (review U12), so nothing is counted for that step. The page (Reports) and the selected result stay.
  - Next start: *Open the preview* (review U1). The workspace starts **in English again** (review D1; recorded as `language_at_start: en`), on Home with no project open.
  - So the supervisor clicks `context-language` → LV, `project-open-<id>` and `nav-reports`.

## 4. Method

### 4.1 The real program, the real handlers

The tool starts the program as the packaged program does after its splash: `research_app.main` runs on the harness's fake page. If the classic interface opens, its *Open the preview* button is the first click.

From then on, `Meter` drives the workspace. `Meter` is a subclass of the Stage 36 `CountingWorkspace`, and through it of `tests/workspace_harness.py`. Every click, tick, choice and typed text calls the handler the control carries, dispatched as Flet 1.x does.

- **System dialogs.** A button whose action is the system Open dialog (`ft.PickFiles`) is clicked, and the chosen file goes to the picker's real `on_result` handler. The Save dialog is the harness's: it answers with a path in the temporary folder.
- **Checks.** Each task checks that it produced what it names. A shortcut that skips a needed step therefore fails the run instead of lowering a count.
- **Same rule as the earlier baselines.** The counter reproduces the Stage 36 count of the same controls. `test_the_stage36_flow_counts_as_in_the_stage36_baseline` gives eight correlations: 8 interactions and 1 page change, as in `tests/test_stage36_ux_baseline.py`.

### 4.2 Interactions, typed fields, page changes, dialogs

The rule is the one of `tests/test_stage36_ux_baseline.py` and `docs/stage37/measure_baseline.py`.

- **Interactions.** A click or a checkbox counts 1, and a dropdown choice 2 (open the list, pick). One segment of a segmented switch is a click, and so is the classic *Open the preview* button.
- **Typed fields.** Each text field typed into counts once.
- **Page changes.** Every change of page counts, also one a handler makes (loading a file opens Data, a run opens Results). So does the switch from the classic interface to the workspace.
- **System dialogs.** The Windows Open and Save dialogs are counted.
- **Not counted.** Reading and scrolling are not interactions.

### 4.3 Repeated variable selections

A tick or a dropdown choice that puts a variable into a role is a selection. It counts as **repeated** when that variable had already been put into a role earlier in the chain.

- Variables that a quick-select button adds (*All quantitative*, *same variables as task…*) are remembered but not counted. Such a button costs one click, whatever it selects.
- In T3, the 20 items ticked for the reliability analysis had been ticked for the score a few steps before. So the 20 repeated selections are those 20 items.

### 4.4 Focus losses

A focus loss is a text field or dropdown the researcher is operating that a re-render rebuilds on the same page.

- **When Flet keeps focus.** Flet 1.x keeps a control's Flutter widget, and with it the keyboard focus and the caret, when the control keeps its place in the tree on a re-render. The place is the same type at the same position among its unkeyed siblings, or the same explicit key (`flet/controls/object_patch.py`, `_compare_lists`). The workspace page is a keyed column, so its content is reconciled in that positional way.
- **What the tool compares.** It records the field's place before the interaction (`reconciliation_path`). If the interaction re-rendered the page, it compares the field's place afterwards, found again by its `data` key.
- **When a loss is counted.** A different place, or no field at all, is one focus loss.
- **The detector is tested.**
  - A field rebuilt in the same place keeps its path.
  - A control inserted above moves it.
  - An explicit key keeps it.
  - End to end on the real Home page, typing that inserts a notice above the field is counted. Typing that appends one below is not.

**Result: 0 in all eight tasks.** No typed field or dropdown of these tasks is re-rendered out of its place: the Stage 34.5 (#30) rule *no re-render while typing* holds here. Two things are not counted here:
- keyboard focus after a click or a page change;
- focus that is never moved to new content (review U11).

### 4.5 Scroll (estimate)

The harness has no Flutter client, so nothing is laid out and scrolling cannot be measured. The tool **estimates** it instead.

- **Layout model.** `Layout` lays the page on screen out from control counts and nominal heights:
  - the design tokens of `workspace_tokens`;
  - 40 px for a button or checkbox, 56 px for a text field or dropdown;
  - table rows at their declared heights, with the text of a cell not wrapped (every table sits in a horizontally scrolling row);
  - wrapped rows of checkboxes laid out by label width, at 0.52 em per glyph for Segoe UI;
  - ResponsiveRow columns chosen by the window width.
- **Distance moved.** Before each interaction, the page moves the shortest distance that brings the control into the viewport. The viewport is the window height less the context bar, the status line and the page padding.
- **Reading.** For content a task reads (the 98-row dictionary, a result), the page moves on to its end; what was already scrolled past counts as read.
- **Page changes.** A new page starts at its top, or at the section the program scrolls to (`navigate(section=…)`); that scroll costs nothing.
- **Inner lists.** A list with its own height scrolls apart from the page: the mouse wheel over it moves the list, not the page. About 970 px of T3's estimate is inside the 170-px item list of the *Prepare data* panel.
- **Not modelled.** Images, collapsed sections, horizontal scrolling and the time a researcher takes are not part of the estimate.
- **Cross-check.** The review's analytic estimate for the dictionary was "about 5,500 px" for 98 variables (§2.2). This model gives ≈ 5,440 px for T2.

### 4.6 Fixtures

- **Master fixture.** `tests/fixtures/stage37/generate_master_fixture.py` (standard library only) writes `synthetic_master_research_n180.csv`: 180 invented cases, 98 columns, and 20/12/5/52 invented items.
- **Stage 36 fixture.** `stage36_fixtures.generator().create_csv` writes `synthetic_ucla_sacs_55.csv`.
- Both are generated into the run's temporary folder and never into the repository.

### 4.7 Isolation

During a run, everything the program writes goes to the temporary folder:
- the data folder (`SRA_DATA_DIR`);
- `preferences.json` and `workspace.json`.

The run also keeps the program away from the user's system:
- `SRA_UI` is empty, so the default start is measured.
- The credential store is never read: the program sees a computer without one. No AI key is used and nothing goes to the network.
- The splash and the daily update check of `app.py` run before `research_app.main` and are not part of the measurement. On a clean first start they need no interaction.

## 5. What the baseline shows, finding by finding

The findings are those of `docs/STAGE37_FABLE_NARROW_REVIEW.md`.

| Finding | Measured here |
|---|---|
| **U1**: the classic interface opens first | +1 click and +1 page change at each of the 3 starts (T1, T7, the next start of T8) |
| **D1**: the language chosen in the workspace is not kept | The next start of T8 is in English, so LV is chosen again: +1 |
| **D2**: 1200 × 720 at every start | At that size the workspace is compact, and T7 takes 5 instead of 4 (§2.1) |
| State not kept (review §6: last page, project) | The next start of T8 opens Home with no project: +2 (open the project, return to Reports) |
| **U12**: no text-size setting; EN/LV/RU in the top bar | T8: text size not available. The language took 1 click in the top bar. |
| **U2**: item sets are picked one tick at a time | T3: 40 item ticks for one 20-item scale, of which 20 are repeated selections. The interactions are 51 in all. |
| **D6**: the hosted *Prepare data* panel | T3 uses it. Its controls have English labels only and no `data` keys. Its items sit in a 170-px inner list (≈ 970 px of inner scrolling, estimated). |
| **D7**: role pickers list variables that do not fit | T3: the item picker offers 98 variables (the scale needs 20). Getting from the items to the confirmation is ≈ 1,180 px (estimate). |
| **S7**: `sex_code` suggested as ordinal | T2's one correction (2 interactions) |
| **H1**: a full re-render on every tick | T3: 27 full-page re-renders, 20 of them one per tick in the 98-box item picker (the time is not measured) |
| **D5**: a changed analysis overwrites its task | T5: the run with UCLA_Level is stored in the batch task (`same_task: true`) |
| **U11**: no focus management | 0 focus losses. What U11 describes (focus never moved to new content) is not what §4.4 counts. |
| **D10, D11, U10** | Not visible in counts: number formats, the Reports page mixing languages, and the width of the question field |

The review's per-step costs for the master scenario (§2.2, analytic) agree with the measured ones:
- **Data and levels.** The review gives 5. Here, opening the data (T1) is 1 and T2 is 4.
- **Scoring one scale.** The review prices it as open 1, kind 2, one tick per item, Apply 1, use the copy 1, levels 2. Measured: 27 for 20 items, plus the typed name.
- **Reliability.** The review prices it as one tick per item plus the goal, the confirmation, Run and navigation. Measured: 24 for 20 items.

## 6. Where the planned UX work should move these numbers (expected, not measured)

These are expectations for re-measuring with the same command. They are not results.

- **UX-1.** One settings file, the workspace first, EN/LV quick choices with RU in Settings, D1 and D2.
  - Each start should lose 1 click and 1 page change: T1, T7 and the next start of T8.
  - T8's next start should lose the second LV click.
  - If the last project and page are restored, it should also lose up to 2 more.
  - With a kept window of 1280 px or more, T7 should take a click again rather than a dropdown.
- **UX-2.** Text size and density: T8's text size becomes a counted step instead of *not available*.
- **UX-3.** A variable panel with search, prefix and range, eligible variables only, and a sticky bulk bar.
  - T3's 40 item ticks should become a few range or prefix selections, and its 20 repeated selections should drop.
  - D7's 98 offered variables should shrink, and T2's ≈ 5,400 px should shrink with a sticky accept bar.
- **Must stay true.** Mandatory scientific confirmations stay in every count: `data-accept-confirm` in T2 and `design-confirm-one_construct` in T3. A lower number must never come from skipping them.

## 7. Limits

- **Not the Windows program.** This is the harness, not the packaged Windows program. UI Automation, keyboard-only use, Narrator and display scaling are not covered; the Windows journeys in `tools/windows_gui_e2e.py` cover those.
- **Shortest path.** Each task follows the shortest path of a researcher who knows where things are. A real novice also searches, reads help and makes mistakes, so the counts are lower bounds.
- **Scroll.** Every scroll number is an estimate from a layout model (§4.5).
- **Not measured.** Time, mouse travel and reading effort.
- **Focus losses** cover typed fields and dropdowns only (§4.4).
- **Set-up.** The set-up between T3 and T4 is not counted, as in the Stage 36 baseline.

## 8. Re-measuring after a change

Run the same command on the changed branch and compare it with §2. The tool adapts where the planned changes would otherwise break it:
- **Start.** When the program opens the workspace first, there is no *Open the preview* click and no classic page change.
- **Restored state.** A project and a page the program reopens at start are not clicked again.
- **Text size.** A text-size control is used when it appears, at 125 %. It is found by a `data` key that contains `text-size`, in the top bar or in Settings (then back to the page).
- **Compact layout.** The Results dropdown of the compact layout is handled.

Other changes of `data` keys need the task scripts in `tools/ux_metrics.py` updated. Keep the English texts and data keys the journeys use.
