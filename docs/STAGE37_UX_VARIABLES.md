# Stage 37 — variable selection and repetition (Issue #68, review UX-3)

> **Scope.** Branch `claude/stage37-ux-vars`, from `claude/stage37-ux` (`b83567c`, the UX baseline). It covers the review's UX-3 (`docs/STAGE37_FABLE_NARROW_REVIEW.md` §8): U2 (item sets picked one box at a time) and D7 (role pickers list variables that cannot be used). It also covers the repetition part of Issue #68 (spec §3: "one-click reuse for analyses"). Synthetic data only. The measurements are in §6 and in `docs/STAGE37_UX_METRICS.md` §9.

## 1. The variable panel

Every role that takes several variables now has one panel (`workspace_variables.role_panel`). These roles are the items, the outcomes, the covariates, the variables related to one, the predictors and the repeated measurements. The panel appears in three places:

- guided step 2 (Analyze);
- the All-methods form;
- the item list of a scale score in Data → Prepare (`PreparationItems`, hosted in the classic panel through a new `item_picker` argument of `preparation_ui.build_preparation_workspace`; the classic interface keeps its plain list).

It offers:

| What | How | Cost |
|---|---|---|
| **Name group** | Numbered variables with one stem (`SYN_LON_01` … `SYN_LON_20`) are one button: "All SYN_LON_* (20)". Once all are selected it reads "Unselect SYN_LON_* (20)". | 1 click for a whole item set |
| **Search** | A part of a name (any case); a pattern with `*`, `?` or `[…]` (`SYN_COPE_0*`); a range in column order (`SYN_LON_01..SYN_LON_20`, also `–` or `to`, either way round); several of these separated by commas | 1 typed field |
| **Select all shown / Unselect shown** | Act on what the search shows. **Enter** in the search field selects what is shown. | 1 click (or Enter) |
| **Clear** | The existing `pick.clear` | 1 click |
| **Count** | "Selected: 20 of 96", with "· shown: 9" while searching (`{key}:count`) | — |
| **Not offered here** | Every variable the role does not list, named with its reason as text (`{key}:not-offered`). While searching, only the ones that match. | — |

The existing quick selections stay as they were, with the same names, keys and counts: all quantitative, all ordinal, the same variables as another task, and Clear.

Two more entry points cover reuse:

- **"Items of SYN_LON_MEAN (20)"** (`role-items:score:<score>`): for an item role, the items a scale score was made from in Data → Prepare. They are read from the session and from the project's transformation history of the dataset and the versions it came from, so they survive a restart. An item set is chosen once, not again for its reliability.
- **Long lists.** More than 40 offered variables are listed only after a search, a name group or *Show all* (`{key}:show-all`); until then the panel lists the chosen ones. On the 98-column master fixture, ~100 boxes were ~100 Tab stops and pushed the confirmation 1,550 px down the page (review §7, U2). Lists of 40 or fewer are shown in full as before, which covers every existing fixture and journey.

### 1.1 Only what a role can take (D7)

`workspace_variables.offered_variables` leaves a variable out, with its reason, when it is one of these:

- **identifier**: suggested or confirmed as one. Identifiers were left out before too, but silently.
- **already chosen for another role** of the same analysis. The grouping variable and the outcome are never offered as covariates, and the first variable is never offered as related to itself.
- **its confirmed level is not one the role takes**: "Sex — Nominal (categories); this role takes Quantitative".
- **not 0/1** for a binary role, or **not numeric** (Data → Prepare).

A variable whose level is not confirmed yet is still offered: it is confirmed inside the analysis, in step 3 or the form's level fixes. A variable chosen earlier that is no longer offered stays listed and ticked, so that it can be unticked. Nothing is left out silently.

**Not changed: single-choice dropdowns** still list every variable but identifiers. A refusal in words explains an unsuitable single choice; journey `blocked-design` relies on that refusal ("age is quantitative"). The Windows driver's keyboard fallback for dropdowns (`Gui.choose`) also counts entries in the full list, so filtering dropdowns would break existing journeys. D7's case is covered by the panels: the covariates, items, outcomes and predictors lists.

### 1.2 Keyboard and UI Automation

- The panel is made of ordinary focusable controls in reading order: the search field, the name groups, the actions, then the boxes. Tab follows that order.
- Buttons and boxes answer Enter and Space; Enter in the search field selects what is shown.
- Every control is named by its visible text: the field by its label, buttons by their text (with a tooltip), boxes by "name · level". The count and the reasons are plain text, so Windows exposes them as text.
- Keyboard focus is kept:
  - the search field, the buttons and the boxes carry explicit keys, so a re-render while typing or ticking keeps them in place (`tests/test_stage37_variable_panel.py` checks this with `ux_metrics.reconciliation_path`);
  - in Data → Prepare, which updates in place, the field and the list are the same objects across updates.
- The long-list rule above cuts the Tab stops of a 98-variable item role from ~100 to the chosen ones.

## 2. Reuse

| Entry point | Where | What it does |
|---|---|---|
| **Duplicate** (`task-duplicate-<id>`, icon, named "Duplicate “title”: a new task …") | Analyze, next to each task in the task bar | Opens a copy of the task: question, variables, method and options. |
| **Repeat with changes** (`result-repeat`) | Results, in a result's header | Opens a copy of the analysis of *that result*: the variables of that run (`selection_from_run`), even when its task was changed in place since (review D5). |
| **Repeat “title” with changes** (`result-repeat-<id>`, icon) | Results, each row of the results list | The same, without selecting the result first. |
| **Recently used** (`recent-<method>`) | All methods, above the catalog | The last four methods run in the project whose variables are in the data. The form opens with the variables and options of the last run. |
| **Other results** (`result-others`) | Results, at the end of a result | The five newest other results, where the reading of a long result ends. `result-other-<id>` opens one from its top, through the new section `("results", "detail")`; `result-other-repeat-<id>` repeats it with changes. The results list is above the whole result, and a 20-item analysis is ≈ 13,000 px long. |

### Rules every copy follows

- **Nothing confirmed is copied.** Confirmations stay bound to the scope they were given for (K1): the copy has none, every box is empty and Run waits for them. The notice "A copy of “…”" (`task-copy-notice`) says so.
- **No hypothesis link is copied.** The researcher chooses it again in step 1; a link is a statement about what the analysis tests.
- **A copy becomes a new task only at its first run.** Its state records `copied_from` (the original task's id). The original keeps its runs, choices and title, so review D5 does not occur on this path. A copy that is never run leaves nothing behind.
- **Method.** The copy keeps the original's method when it differs from the recommendation (shown as "Chosen"). Changing a variable falls back to the recommendation, as everywhere in guided mode.
- **Task title.** A generic task title with more than three variables now names the span and the count ("… SYN_LON_01 … SYN_LON_19 (19 variables)"). Otherwise a task and its copy with one item fewer had the same name.

**Not changed: running a task after "Change variables"** still stores a new version in the same task ("This task has 2 runs"). The design keeps it, and journey `confirmations` relies on it. The copy is the way to keep the original.

## 3. What does not change

- Every mandatory scientific confirmation is still asked, in every count; the panel only selects variables.
- Data keys:
  - existing keys, labels and texts the journeys use are kept: `role-<role>-<name>`, `role-<role>-all-<level>`, `role-<role>-from-<task>`, `role-<role>-clear`, `form-<role>-<name>`, and the box label "name · level";
  - the panel's own keys use `:` (`role-items:search`), which never follows a role key in a box's key, so no variable name can collide with them.
- The classic interface is unchanged. Its *Prepare data* panel keeps its plain list; only the workspace passes the panel.

## 4. Tests

`tests/test_stage37_variable_panel.py` (26 tests, ~40 s):

- **Logic:** name groups; the filter (part, pattern, range both ways, across groups, lists, unknown ends); the reasons, in three languages; every new text in EN/LV/RU with the same placeholders.
- **D7:** in the guided comparison, covariates offer neither the group nor the outcome, and the reasons are on screen; the ANCOVA form of review D7's screenshot; the quick selections keep their keys, labels and counts; a variable chosen before stays listed until unticked.
- **Master fixture (98 columns):**
  - the item role offers 96 variables and says why not the other three;
  - the long list is collapsed until Show all;
  - 20 items take 1 click by their name group;
  - search, pattern, range, select or unselect shown, and Enter;
  - the panel confirms nothing;
  - keyboard order and names, and focus kept while typing and ticking.
- **Reuse:**
  - "Other results" at the end of a result opens one from its top and repeats one;
  - a duplicated task has the variables and method and nothing confirmed;
  - its run is a new task with `copied_from`, and the original is unchanged;
  - Repeat with changes takes the variables of that run after the task was changed in place (D5);
  - `selection_from_run` for every question;
  - recent methods bring back variables and options, not confirmations;
  - the items of a score are offered for its reliability, also after a restart;
  - the Prepare panel's search keeps the same field object.
- **Windows journey walk:** see §5.

## 5. Windows journey `variable-picker`

`tools/windows_gui_e2e.py` appends `variable-picker` after the 18 existing journeys; their order is unchanged. On the 98-column master fixture, generated by its standard-library generator, the journey:

1. accepts the suggested levels, scrolling to the bulk acceptance below the 98-row dictionary;
2. checks that the item list names `participant_code` (identifier) and `employed_code` (nominal) as not offered;
3. selects the 20 `SYN_LON_` items with their name group, in one click;
4. confirms one construct and runs; α, k and n must equal the driver's own numpy α of the CSV;
5. presses **Repeat with changes**: a new task, 20 items, the confirmation box empty;
6. finds `SYN_LON_20` by typing, reaches its box with **Tab** (it records the names the focus passes) and unticks it with **Space**;
7. confirms again and runs; α of 19 items must equal numpy, and the first result's "α if deleted";
8. reads the project database (read-only): two tasks; the first still has 20 items; the copy has 19, `copied_from` the first, and `{"one_construct": true}`.

**Counts** (`PANEL_ACTIONS`, recorded in the result JSON and checked by the walk):

| Part | Clicks | Boxes | Typed |
|---|---:|---:|---:|
| The 20 items | 1 | 0 | 0 |
| Repeat, leave one item out, confirm again, Run | 2 | 2 | 1 |

`tests/test_stage37_variable_panel.py::VariablePickerJourneyTests` walks the same flow in the harness. At each step it checks every name the journey presses or waits for, with the journey's texts and helpers. It also checks the numbers against the driver's numpy α, the counts, and that Tab reaches the box after the field within the journey's 25 presses. The journey has **not been run on Windows** from this branch, because it was developed on Linux. The tooltip-bearing buttons are pressed by a regex that also accepts a tooltip appended to the name, as the existing journeys do for tiles.

## 6. Measured effect (`tools/ux_metrics.py`)

See `docs/STAGE37_UX_METRICS.md` §9 for the full before and after tables. Summary, at 1440 × 800:

- **T3**, define and score one 20-item scale and check its reliability: **51 → 13 interactions**, repeated selections 20 → 0.
  - Data → Prepare: the name group instead of 20 boxes.
  - Analyze: "Items of SYN_LON_MEAN (20)" instead of 20 boxes.
  - The mandatory confirmation `design-confirm-one_construct` is still in the count.
- **T5**, repeat a previous analysis with one variable changed: **5 → 4 interactions**.
  - The repeat is taken from "Other results" at the end of the result the supervisor read last in T7.
  - The batch task is no longer overwritten: the run is a new task, and the original keeps UCLA (`same_task: false`, `original_kept: true`).
  - The estimated scroll falls from 780 to 520 px.
- **T7**, reopen and review every result: 4 interactions as before. The estimated scroll falls from 19,550 to 16,962 px, because the second result is opened from the end of the first, not from the list ≈ 2,500 px above.

## 7. Texts: LV and RU drafts for native review

51 new keys, all with EN, LV and RU. The LV and RU texts are drafts: they are marked in `workspace_text.py` ("LV/RU drafts — needs native review") and need a native speaker's review before a release.

- **The panel:**
  - `vars.search`, `vars.search_hint`
  - `vars.group`, `vars.group_tip`, `vars.ungroup`, `vars.ungroup_tip`, `vars.more_groups`
  - `vars.select_shown`, `vars.unselect_shown`
  - `vars.count`, `vars.count_shown`
  - `vars.none_match`, `vars.none_offered`
  - `vars.show_all`, `vars.show_chosen`, `vars.collapsed`
- **Reasons:**
  - `vars.not_offered`, `vars.more`
  - `vars.why.identifier`, `vars.why.role`, `vars.why.level`, `vars.why.binary`, `vars.why.not_numeric`
- **Role names in "already …":** `vars.role.outcome`, `.outcomes`, `.group`, `.covariates`, `.measures`, `.before`, `.after`, `.x`, `.y`, `.ys`, `.a`, `.b`, `.predictors`, `.items`, `.variable`.
- **Reuse:**
  - `pick.score_items`, `pick.score_items_tip`
  - `task.duplicate_tip`, `task.copy_notice`
  - `results.repeat`, `results.repeat_tip`, `results.repeat_named`
  - `results.others`, `results.other_open_tip`
  - `catalog.recent`, `catalog.recent_last`, `catalog.recent_tip`, `analyze.recent_notice`

Points for the reviewer:

- `vars.why.role` combines a variable list with a role noun in the nominative: "jau izvēlēts: grupu mainīgais", "уже выбрано: группирующая переменная".
- `vars.role.outcomes` is "one outcome among several" in English. LV and RU use the plain noun.

## 8. Not done here

- **Restoring the last task of a project after a restart.** It changes what Analyze shows after a restart for seven test modules and several journeys, and it overlaps UX-1, which saves the last page.
- **Single-choice dropdowns** are not filtered (§1.1).
- **The sticky bulk bar of the data dictionary** (also listed under UX-3) is not done. T2 is unchanged.
- **The Windows journey** has not been run on Windows (§5).
