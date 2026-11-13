# Stage 37 — Research Productivity 2.0: interface design and the 37.0 increment

Issue #63, **Phase D**: architecture and UX design with a clickable prototype. No product code is changed in this phase; the Stage 37.0 functional increment comes in its own PR.

- Base: `55f94b1`, the head of the Stage 36.8 release-candidate branch. Branch: `claude/stage37-research-workflow`.
- Updated for Stage 37.0a: the branch merges the RC head `07c37f6` (K1–K3 fixed, format 5 kept). §13 records the architect's defaults for the owner's questions, and `docs/STAGE37_0A_STATUS.md` lists what 37.0a implements and which test proves each item.
- Companion files:
  - `docs/stage37/prototype.html`: the clickable prototype (approach A, approach B, the hybrid; a beginner flow and a professor flow; a built-in self-test).
  - `docs/stage37/README.md`: how to use the prototype, and the open questions.
  - `docs/stage37/measure_baseline.py`: the measurement of today's flows.

---

## 0. Summary

**Decision: a hybrid.** Navigation, hypotheses and statuses come from approach A, the research protocol. The task surface comes from approach B, the analysis desk: set-up on the left, result and checks on the right, stacked on narrow windows. A deterministic next action is shown on every page of the journey.
- Kept from A: the project page as the study's protocol; analyses linked to their hypothesis; one next action.
- Rejected from A: removing Analyze as an area; forcing descriptive and exploratory work through a hypothesis.
- Kept from B: a task surface where Run and the result stay in view; reuse of a variable set.
- Rejected from B: the three-pane desk, its manual hypothesis link and its dense first screen.

**Stage 37.0** is the first slice of the hybrid. It is the hypothesis and research workflow, built on today's page layout:
- typed research questions;
- H1 and H0 drafted from the question type, with a direction;
- a designation (primary, secondary or exploratory) set before results, with an audit log of changes;
- research tasks linked to hypotheses (`ResearchTask.hypothesis_id` is filled at last), and each result keeps a snapshot of the hypothesis it was calculated for;
- a step status for each task;
- 15 deterministic hypothesis–analysis checks;
- protocol deviations;
- a next-action bar.

The data change is additive: one new table and optional JSON fields, as project format F+1, with the existing backup before migration and a copy that an older version can open. The two-panel layout is 37.4; 37.0 does not depend on it.

**Measured today (55f94b1) and expected after 37.0.** Today's numbers are measured with `CountingWorkspace`. The 37.0 numbers are estimates: they are the click paths of the prototype, replayed mechanically.

| Flow | Today, measured | After 37.0, estimate |
|---|---|---|
| Beginner: question → hypothesis → data → scales → analysis → interpretation → report | 22 interactions, 10 typed fields, 5 page changes, 2 system dialogs. The analysis **cannot be linked** to the hypothesis. | 20 interactions, 5 typed fields, 4 page changes, 2 system dialogs. The link is made automatically. |
| Professor: methodology, measurement quality and provenance of H1, then the status of H2, then the report | 14 interactions, 6 page changes. Analyses are matched to hypotheses **by title**; the consistency check is done by reading; deviations and their history are **not stored**. At `55f94b1` the note, the review ticks and the study title were **lost** after a restart (K2); since the RC fix (`23f4f4a`, re-measured at `07c37f6`) they come back, and the counts are the same. | 6 interactions, 2 page changes. Link, checks, deviations and history are on one page. |

The owner's questions are listed in §13, each with the default that 37.0a was built on (the owner may change it).

---

## 1. Inputs, method and the status of every number

**Read.**
- Issue #63, and #62 for the release-candidate context.
- The independent review (`FABLE_REVIEW.md`, in Russian): §3 U1–U13, §4, §5 AI2, §7 (the two workspace concepts), the ten recommendations, the Stage 37 roadmap.
- The code: `workspace_plan.py`, `workspace_state.py`, `workspace_analyze.py`, `workspace_shell.py`, `workspace_projects.py`, `workspace_methods.py`, `workspace_charts.py`, `workspace_questionnaires.py`, `research_report.py`, `project_store.py`, `project_session.py`, `ai_context.py`.
- The documents `docs/STAGE36_SPEC.md`, `docs/STAGE36_UX_AUDIT.md`, `docs/STAGE368_*.md`, `docs/IN_APP_UPDATES.md`, `docs/WINDOWS_INSTALLER.md`.
- The screenshots of the packaged program, `exe-screenshots` 001–153.

**Measured (today).** `docs/stage37/measure_baseline.py` drives the real workspace controls with the Stage 36 `CountingWorkspace`: a click or a checkbox counts 1, a dropdown 2. It adds three counts, kept apart so that the Stage 36 number stays comparable:
- **typed fields:** each text field typed into, counted once;
- **page changes:** every change of route, including one made by a handler (loading a file opens Data);
- **system dialogs:** the Windows Open and Save dialogs.

Fixtures are synthetic: `synthetic_ucla_sacs_55.csv` and `synthetic_items_scale.csv`. The harness runs on Linux and calls the same handlers a click calls; Windows itself was not used. Appendix A lists every control and the output.

**Estimated (the three designs).** The counts for A, B and the hybrid are the click paths of `docs/stage37/prototype.html`. They were checked in two ways:
- the page's own self-test (`prototype.html#selftest`) replays each path through the page's handlers;
- a headless-Chromium run clicked each highlighted control at 100 % and at 125 % device scale.

All six paths reproduce the counts in this document. They are **estimates of a design, not measurements of an implementation**. The 37.0 PR must measure its own flows with `CountingWorkspace`; acceptance criterion AC-10 sets the thresholds.

**Not done.**
- No test with users, so there are no completion rates or timings yet. §5.4 gives a ready test protocol on the prototype.
- No Windows run.
- No native-speaker review of new LV/RU text (none exists yet; see `docs/STAGE368_A11Y_AND_LOCALE.md` §6).

**State of the release candidate that matters here.**
- Review findings K4 and K5 are fixed (`f193df2`).
- K1, K2 and K3 were fixed on the RC branch in `23f4f4a` (merged into this branch with the RC head `07c37f6`). They kept project format 5: notes in `runs.note`, review ticks in the run's provenance, report settings in the activity log, confirmation scopes in the task state. At `55f94b1` the researcher's note, the review ticks and the report title were lost after a restart; re-measured at `07c37f6`, nothing is lost and the interaction counts are unchanged.
- 37.0 depends on K1 (confirmations bound to the data and the variables) and on K2 (notes and review ticks saved in the project); both are in place.

---

## 2. What exists today (55f94b1)

### 2.1 Navigation

- **Sidebar.** `AREAS = ("home", "data", "questionnaires", "analyze", "results", "reports")`, with Ctrl+1…6. "Project" appears under Home only while a project is open and has no shortcut. Settings, Help & privacy and Classic interface sit at the bottom.
- **Journey strip.** Seven chips on the journey pages: `1. Question · 2. Data · 3. Variables · 4. Design · 5. Method · 6. Result · 7. Report`. Their status is global. `journey_status()` sets Design, Method and Result to `bool(session.results)`, so any result ticks all three (review U10). `tests/test_workspace_journey_strip.py::test_the_strip_follows_the_research` asserts exactly that behaviour.
- **Project page** (`workspace_projects.ProjectPage`), in this order: header; "Saved automatically"; the **Question** card (the first row of the `research_questions` table); the **Research plan** card; the **Next step** card (`next_step()`: add data → levels → analyze → stale results → report → export); data sources; questionnaires; results; report.
- **Analyze.** Guided mode and All-methods mode. The task bar lists the tasks as chips. Guided mode has four step cards: *What do you want to find out?*, *Which variables?*, *Check the design*, *Recommended method*. A batch result appears as step 5 in the task. A single analysis opens Results instead (U13).

### 2.2 The research plan

`workspace_plan.ResearchPlanCard`:
- **Plan fields:** objectives, design, population, ethics, preregistration.
- **Each hypothesis:**
  - free text: H1, H0, outcome, predictors, covariates, intended method, multiplicity family, exclusion policy;
  - direction: `two-sided`, `greater` or `less`;
  - priority: `primary`, `secondary` or `exploratory`;
  - α, with 0 < α ≤ .2.

**Save plan version** appends a row to `plan_versions` (format 3); nothing is overwritten. `normalise_plan` keeps only the known fields; any other key is dropped when the plan is saved.

The *standing* of a hypothesis is derived from the first version that contains it (`hypothesis_status`):
- *planned before any result*;
- *added after N results were calculated: exploratory unless justified*;
- *exploratory*.

`runs_before` is the number of results in the whole project, so one unrelated descriptive result already makes a later hypothesis "added after results".

### 2.3 Research tasks and results

- **Task.** `ResearchTask(id, title, goal, selection, method, options, confirms, hypothesis_id, state)`, stored in `research_tasks` (format 4).
  - **`hypothesis_id` is never filled.** The only constructor in the interface, `workspace_analyze.py:377`, does not pass it; `project_session` only saves and restores it. The baseline confirms it: both tasks have `hypothesis_id = None`.
  - The task is saved after its run (`_execute` → `_remember_task`).
- **Result.** `ResultEntry` keeps the run, method, roles, options, confirmations and provenance: the dataset SHA-256, levels, complete cases and where each level was confirmed. The `runs` table also stores the report SHA-256, the structured result, the charts and `task_id`. `run_status` marks a run stale when its data or a level it relied on changes.
- **Review state.** At `55f94b1` the review ticks and the researcher's note lived in `ResultsPage.reviewed` and `ResultsPage.notes` and were not persisted. Since the RC fix of K2 (`23f4f4a`) they are `ResultEntry.reviewed` and `ResultEntry.note`, saved with the run.

### 2.4 Engine facts that decide the hypothesis checks

- **Every p-value is two-sided.** The engines call SciPy with `alternative="two-sided"` or its default, and no method has a sidedness option. A one-sided hypothesis is therefore never tested one-sided; the plan's direction has no effect today.
- **α is fixed at .05 in the results.** The batch engines accept `alpha=` (`batch_correlation.correlate_many`, `batch_groups.compare_many`), but the workspace passes the default. The plan's α has no effect either.
- **Corrections stay inside a batch.** A multiple-comparison correction applies within one batch family (Holm by default). Two tasks that test one family are corrected separately.
- **Reliability from totals is refused.** α and ω are refused for scale totals before Run (D5).

### 2.5 Report, AI context, compatibility

- **Report.** `research_report` has 15 sections. In *Hypotheses* it prints `H1 (primary): …`, `Null hypothesis: …` and *Planned before the results* or the post hoc warning. Nothing connects a hypothesis to the result that tests it.
- **AI context.** `ai_context._plan` sends a fixed list of plan fields. New plan fields do not reach a prompt unless that list changes.
- **Compatibility mechanics.**
  - `SCHEMA_VERSION = 5`.
  - `migrate()` reads the format through a read-only connection and refuses a newer format without writing. Before it migrates, it copies the database to `.backups/`, and it migrates in one transaction.
  - `ProjectStore.open(read_only=True)` exists.
  - The updater never offers an older version (`docs/IN_APP_UPDATES.md`).
  - The installer keeps projects in `%LOCALAPPDATA%\StatisticalResearchAssistant` (`docs/WINDOWS_INSTALLER.md`).
  - `docs/` is excluded from the bundle (`pyproject.toml` `[tool.flet.app] exclude`).
- **Accessibility constraint.** Flutter's Windows accessibility bridge reports every button as enabled (`docs/STAGE368_A11Y_AND_LOCALE.md` §1). A disabled button is announced as available, so new primary actions must not rely on the disabled state.

### 2.6 The measured baseline

Beginner flow (Appendix A gives every control):

| Segment | Interactions | Typed fields | Page changes |
|---|---:|---:|---:|
| 1 Project: title, *Create project* | 1 | 1 | 1 |
| 2 Research question (Question card) | 0 | 1 | 0 |
| 3 Hypothesis: *Add hypothesis*; H1, H0, outcome, predictors, method, family; *Save plan version* | 2 | 6 | 0 |
| 4 Data: *Open CSV / Excel…* (+ system Open dialog) | 1 | 0 | 1 |
| 5 Measurement levels: tick, *Use suggestions…*; 0 corrections | 2 | 0 | 0 |
| 6 Scales: totals only (α/ω refused, D5) | 0 | 0 | 0 |
| 7 Analysis: 8 Spearman correlations (Stage 36 batch) | 8 | 0 | 1 |
| 8 Link the analysis to H1 | — not possible — | | |
| 9 Interpretation: open the result, expand, note, 3 review ticks | 5 | 1 | 1 |
| 10 Report: *Add to report*, Reports, study title, *Export Word report…* (+ Save dialog) | 3 | 1 | 1 |
| **Total** | **22** | **10** | **5** (+2 system dialogs) |

Professor flow, after a restart: **14 interactions, 6 page changes**. The route is Project → Results → Analyze → Data → Results → Reports.
- The analysis of H1 is found by its title.
- The comparison of the plan's direction and method with the analysis is done by reading two pages.
- At `55f94b1`, the student's note, the three review ticks and the study title were gone after the restart (K2). K2 is fixed on the RC (`23f4f4a`). Re-measured at the RC head `07c37f6` (this branch's merge `e06736c`), all three come back, and every count in this section is unchanged (Appendix A).

Scale quality on the 10-item fixture, for reference: 5 interactions, 2 page changes.

---

## 3. Approach A — "Research protocol" (from the question)

**Concept.** The study is the main object. The project page becomes the protocol, the study's table of contents. Every analysis lives inside the hypothesis it tests, as a sequence of steps.

**Navigation.**
- Sidebar: `Home · Study · Data & instruments · Results log · Report`.
- *Analyze* is no longer an area; its guided steps move into the hypothesis.
- *Data* and *Questionnaires* merge into one area. *Results* becomes a log.
- The journey strip disappears: the Study page is the journey. Ctrl+1…6 are remapped.

**Page hierarchy.**
```
Study (protocol)
├─ Next step                                   one action, top of the page
├─ Q1 · Relationship between two variables · "Is loneliness related to …?"
│  ├─ H1 · Primary · Two-sided · α .05 · Planned before any result
│  │  ├─ 1 Data and scales      dataset, H1's variables, their levels, D5 note
│  │  ├─ 2 Analysis             recommendation, alternatives, Run, result, provenance
│  │  ├─ 3 Checks               assumption ticks, checks against the plan, deviations
│  │  ├─ 4 Interpretation and report   note, Add to report
│  │  └─ History                plan versions, deviations, acknowledgements
│  └─ Add hypothesis to Q1
├─ Q2 …
├─ Save plan version · Plan history
└─ Other analyses (not linked to a hypothesis)
```
**Primary actions:** *Next step* (Study); *Run …* inside the open hypothesis; *Export Word report…* (Report). One step is open at a time. The next step opens after an explicit completion: Run, the last review tick, the confirmed levels.

**Flows.** Prototype paths; the full lists are in Appendix B.
- **Beginner:** 19 interactions, 5 typed fields, 2 page changes (Study, Report), 2 system dialogs. H1's variables and levels are chosen inside the hypothesis.
- **Professor:** 8 interactions, 2 page changes. The path is open → H1 *Analysis* → H1 *Checks* → H1 *History* → H2 *Checks* → H2 *History* → Report → preview.

**Strengths.**
- A beginner always sees what comes next.
- Hypothesis, evidence and standing are on one page.
- It has the fewest page changes.

**Weaknesses.**
- Work without a hypothesis is pushed into "Other analyses": a Table 1 (U1), an exploratory batch, a reliability check of a new questionnaire. In psychology theses that is a large share of the analyses.
- The Study page grows with every hypothesis. With 3 hypotheses and their open steps it becomes several screens of scrolling; that cost is not counted above.
- The professor's quick method check goes through question → hypothesis → step.
- Removing Analyze as an area changes `AREAS`, the shortcuts, the help texts and most UI Automation selectors of the 13 packaged GUI journeys.

**Cost.** Large in the shell and the journeys. The engine and the store are unchanged.

## 4. Approach B — "Analysis desk" (from the data)

**Concept.** The analysis task is the main object, and one screen holds everything needed to set it up, run it and inspect it.

**Navigation.**
- Sidebar: `Home · Project · Data · Questionnaires · Analysis desk · Results · Reports`. *Analysis desk* replaces Analyze.
- The project page keeps today's plan card with typed fields and today's *Next step* card.
- The journey strip stays as it is.

**Page hierarchy.**
```
┌ Variables and scales ┐┌ Task ──────────────────────────────┐┌ Inspector ──────────────────┐
│ search               ││ Correlations · Group comparisons … ││ Hypothesis | Assumptions |  │
│ UCLA      Quant.     ││ roles (first variable, others)     ││ Provenance | Chart | Report │
│ SACS ▸ 8 scales      ││ Pearson · Spearman · Kendall       ││ link: Tests hypothesis [H1] │
│ UCLA_Level Ordinal   ││ adjustment [Holm]   [Run] ← always ││ checks for the link         │
└──────────────────────┘│ result table                       │└─────────────────────────────┘
                        └────────────────────────────────────┘
Analysis plan (all tasks): task · tests · method · steps · result · [Open]   [Re-run on a new data version…]
```
**Primary actions:** *Run* (always visible); *Tests hypothesis* (Inspector); *Re-run on a new data version…*.

**Flows.** Prototype paths:
- **Beginner:** 26 interactions, 5 typed fields, 4 page changes, 2 system dialogs. The hypothesis is linked from the inspector, after the result, so the result is marked "linked after calculation".
- **Professor:** 12 interactions, 4 page changes: plan strip → inspector tabs → back to Project for the plan history.

**Strengths.**
- No scrolling between set-up and result.
- A variable set and a method stay in view while another analysis is set up.
- The fastest re-run.
- The professor reads method, assumptions and provenance as tabs.

**Weaknesses.**
- It is the most expensive path for the beginner.
- The link between hypothesis and analysis is an afterthought: a separate control, usually used after the result, which is exactly the sequence the plan is meant to prevent.
- The next step is implicit.
- Three panes do not fit below about 1,200 logical pixels. At 175 % on a 1080p display the program has 1,097 × 617 (`docs/STAGE368_A11Y_AND_LOCALE.md` §4), so the panes become tabs and the advantage is gone.
- The professor still has no protocol view (designation history, deviations) beyond the plan's version list.

**Cost.** A new layout for Analyze, Results detail and Chart Studio access; the largest risk to the existing E2E selectors (`scroll_key` anchors, compact mode).

**Considered and set aside: "manuscript first".** The report's 15-section outline is the hub, and each section shows which evidence is missing. Its task surface would be today's. It postpones the plan-before-results guarantee to the writing stage and overlaps with 37.3, so it is not a distinct third interface for this decision.

---

## 5. Comparison

### 5.1 Numbers

| | Today (measured) | A | B | Hybrid / 37.0 |
|---|---:|---:|---:|---:|
| Beginner: interactions | 22 | 19 | 26 | **20** |
| Beginner: typed fields | 10 | 5 | 5 | **5** |
| Beginner: page changes | 5 | 2 | 4 | **4** |
| Beginner: system dialogs | 2 | 2 | 2 | 2 |
| Beginner: analysis linked to H1 | not possible | built in | manual, after the result (3 interactions) | **automatic** |
| Professor: interactions | 14 | 8 | 12 | **6** |
| Professor: page changes | 6 | 2 | 4 | **2** |
| Professor: hypothesis checks, deviations, history | not available | on the Study page | checks in the inspector; history only as version notes | **on the hypothesis** |

Two notes on these numbers:
- The beginner count does not fall much in any design: the scientific decisions stay separate clicks (no automatic approval, `STAGE36_SPEC` §2E). The hybrid saves 2 interactions, 5 typed fields and 1 page change; the gain is mostly correctness and orientation.
- **Scrolling is not counted.** A's Study page and today's vertical Analyze page need the most scrolling; B and the hybrid's two-panel task need the least. The 37.4 layout removes scrolling, not interactions.

### 5.2 Criteria (review §7, sharpened)

| Criterion | A | B | Hybrid |
|---|---|---|---|
| Beginner: is the next step clear? | high | low | high (one next action on every page) |
| Professor: speed of checking method and provenance | medium (steps to expand) | high (tabs) | high (one hypothesis detail, the evidence inline) |
| Hypothesis → analysis → report link | built in | separate control | built in, with a snapshot in each result |
| Work without a hypothesis (Table 1, exploratory, reliability) | pushed aside | natural | natural ("No hypothesis" is a task state) |
| Narrow windows, 150–175 % | good | poor | good (panels stack) |
| Change to `AREAS`, shortcuts, E2E selectors | large | large | small in 37.0, moderate in 37.4 |
| Reuse of existing code | plan card, guided steps moved | new layout | plan card, guided steps, `ResultsPage`, `research_report` |

### 5.3 What each flow gives the user (beyond the count)

- **Today.** The beginner finishes, but the plan and the analysis are unrelated records. The professor rebuilds the relation from titles. (At `55f94b1` the student's interpretation and review ticks were also gone after a restart; K2 is fixed in the RC.)
- **Hybrid.** The beginner's H1 is planned before any result, and the analysis created from it carries the link. Every result records which plan version and designation it was calculated for. The professor sees on one page:
  - that H1 is one-sided while the test is two-sided, and the student's acknowledgement;
  - that Spearman was used where Pearson was planned, recorded as a deviation before the first result;
  - that H2 was demoted after results, with the reason;
  - that one assumption check of H2 is open.

### 5.4 The user test the issue asks for (not yet run)

Issue #63 asks to compare task completion rates and actions on a clickable prototype before widgets are expanded. The prototype supports a moderated test: the **Show the guide** switch hides the coaching, and the counter keeps counting.

- **Participants.** 4–5 bachelor students who have not used the app, and 2 supervisors.
- **Order.** Each participant does the variants in a counterbalanced order (A/B/H, B/H/A, H/A/B).
- **Beginner tasks.** Write the question and H1 so that they count as planned before results, run the eight correlations, review the checks, put the result into the report.
- **Supervisor tasks.** Which analysis tests H2, and were its assumptions reviewed? Is there a deviation from the plan, and when was it recorded? Which hypotheses are exploratory, and why?
- **Measures.** Completion; time; interactions and page changes (the counter); wrong turns (pages off the path); answer correctness for the supervisors; a confidence rating after each task.

This test is the input for the 37.4 layout decision. 37.0 does not wait for it: its scope is the same in A and the hybrid.

---

## 6. The hybrid decision

**Kept from A.**
- The project page as the study's protocol: questions, hypotheses, their standing, analysis and checks.
- Analyses created from a hypothesis, with the link set at creation.
- One deterministic next action.
- Honest step statuses.
- The hypothesis history: plan versions, deviations, acknowledgements.

**Kept from B.**
- The task as the unit of analysis, with Run and the result in view: setup on the left, result and checks on the right (37.4; stacked below about 1,180 px).
- Variable sets reused from another task (exists since 36.1).
- The analysis plan as a list of tasks with their state (the task bar and the hypothesis rows).
- Expert method controls stay reachable from the same form (37.4 replaces the Guided / All-methods switch by in-form disclosure, review §7).

**Rejected from A, and why.**
- *Removing Analyze as an area.* Tasks without a hypothesis are legitimate: a Table 1 of descriptives, a reliability check, an exploratory batch. They need a home that is not "other". It would also rewrite `AREAS`, the shortcuts and the selectors of the 13 packaged GUI journeys for no scientific gain.
- *Inline accordions for everything.* The Study page would become the longest page of the program. The hybrid keeps one compact row per hypothesis and opens one hypothesis at a time.

**Rejected from B, and why.**
- *The three-pane desk.* It does not fit the measured compact case (1,097 × 617 at 175 %), and it is the most expensive path for the beginner (26 interactions).
- *The manual link after the result.* It produces exactly the post hoc sequence the plan exists to make visible; the prototype shows B's results marked "linked after calculation".
- *An implicit next step.*

**Why this is right for this code base.**
- 37.0 needs no layout change. It reuses `ResearchPlanCard`, `plan_versions`, `hypothesis_status`, `research_tasks.hypothesis_id`, the guided steps, `ResultsPage`, the page footer mechanism (`WorkspaceApp.render` already shows a page's `footer()` below the scrolling content) and `research_report`.
- The data change is one table.
- The layout half (37.4) is then a contained change to the Analyze page, informed by the user test.

**Information architecture.** In 37.0 the sidebar, labels and shortcuts are unchanged: Home · Project · Data · Questionnaires · Analyze · Results · Reports. This keeps the RC's journeys and the help text valid. Renaming "Project" to "Study" is not proposed.

---

## 7. Stage 37.0 specification: the hypothesis and research workflow

### 7.1 Scope

**In.**
- Typed research questions.
- H1/H0 with direction.
- Designation set before results, with an audit log.
- Task–hypothesis link with a result snapshot.
- Step status per task.
- Deterministic consistency checks with acknowledgements.
- Protocol deviations.
- The next-action bar.
- The Hypotheses section of the Word report names the links and the deviations.
- The additive data model.
- A copy of a project for an older version.

**Not in** (§12): AI planning, report QA, the measurement layer, the two-panel layout, new statistics.

### 7.2 Typed research questions

- A question has an `id` (12 hex characters), a `type` and a `text`.
- `type` is one of the guided goals (`workspace_methods.GOALS`), shown with their existing labels: *Compare groups*, *Compare repeated measurements*, *Relationship between two variables*, *Association between categories*, *Predict an outcome*, *Check a questionnaire scale*, *Explore questionnaire structure*, *Describe a variable*. The empty value means *not chosen*.
- The type decides three things:
  - which hypotheses make sense: none for *Describe a variable*; for scale and structure, an expectation rather than H0/H1, which is 37.1;
  - the H1/H0 drafts;
  - the goal of an analysis created from the question, so the guided analysis starts at step 2.
- Questions are part of the plan (plan JSON, §8.2), versioned with it.
- **The existing Question card.** It is replaced by Q1 of the plan.
  - On the first plan save, the text of its `research_questions` row becomes Q1 (*not chosen*).
  - The row is kept and written through with Q1's text, because the AI *overview* source and the reports read it.
  - A project that has never used the plan shows that row as Q1 until it is saved.

### 7.3 Hypotheses: H1, H0, direction, designation, α

- **Drafts.** *Add hypothesis to Q1* creates H1 and H0 drafted from the question type. Example (EN): *‹First variable› is associated with ‹each of the other variables›.* / *There is no association (ρ = 0 for each pair).* The researcher edits the text; nothing is confirmed until *Save plan version*.
- **Direction.** Two-sided, greater (one-sided) or less (one-sided), unchanged. For *Relationship* questions the labels name the sign (*positive*, *negative*). For a one-sided two-group hypothesis the expected higher group can be named (`expected`, optional). The editor says that the tests of this version report two-sided p-values (§2.4).
- **Designation.** Primary, secondary or exploratory. It is stored in the existing `priority` key; only the label changes to *Designation*.
- **α.** As today: 0 < α ≤ .2.
- **Optional before data:** the intended method, the variables and a family label.
  - The intended method is chosen from the method list (method key and options) or left as *decided in the analysis*.
  - The variables are role → name entries for the question type (`GOAL_ROLES`), chosen from the dataset once it is open. A name that is missing from the dataset is shown as such.
  - The family label is drafted as "H1 (k tests)".
- **When they are left empty,** the first run of an analysis linked to the hypothesis becomes the reference for later changes. That run is an immutable record, so nothing is written into the plan for it.
- **Old free text** (outcome, predictors, covariates, method, family, exclusions) stays, under *More details*: shown, editable, never deleted.
- **Controls.** The existing ones stay (dropdowns for direction and designation; `plan-h{i}-*` data keys), so `tests/test_workspace_plan.py` and the journeys keep working. The prototype draws segmented buttons for compactness. Typing never re-renders the page; this is the existing pattern.

### 7.4 Designation before results, and its audit log

- **Planned or not.** A hypothesis is *planned before any result* when the first plan version containing it was saved while the project held no result. This is today's rule, and it stays strict.
- **Facts shown beside the standing.** The detail lists which results existed then and whether any used the hypothesis's variables (e.g. *1 result existed: Descriptive statistics of Age; none used H1's variables*). The researcher can record a **justification** (§7.8).
- **Changing a designation after results.** It requires a reason; *Save plan version* explains this beside the field rather than disabling itself. The change becomes a `designation` record with the old and new value, the plan version, the number of results in the project and the number of results of the hypothesis. It is also written to the project's event log as `designation_changed`.
- **Changing it before any result** needs no reason; it appears in the history as an ordinary plan version.
- **Where the history appears.** The hypothesis detail shows the history: plan versions with the hypothesis, records, dates, result counts. The Word report prints a designation change that happened after results (§7.10).

### 7.5 Linking tasks to hypotheses

- **The link.**
  - A task tests at most one hypothesis (`research_tasks.hypothesis_id`, the existing column). A hypothesis may be tested by several tasks, for example a main analysis and a robustness check.
  - *Create the analysis for H1* (hypothesis detail, or the next-action bar) creates a task with `hypothesis_id = H1`, the question type as goal, and the plan's variables and intended method when they were typed. Analyze opens at step 2.
  - Step 1 of a task shows *Tests hypothesis* (a dropdown of the saved hypotheses, or *No hypothesis (exploratory or descriptive)*).
- **Changing the link.**
  - It writes a `link` record (from → to, the task's results so far).
  - Results calculated before the change keep their snapshot. The new hypothesis lists them as *linked after calculation* (check H-LINKED-LATE), so a result is never silently re-attributed.
- **The result snapshot.** At calculation time a result stores `provenance.hypothesis = {id, plan_version, priority, direction, alpha, standing}` in the `runs.provenance` JSON. It is restored with the result and shown in Results and in the provenance: *Calculated as a test of H1 (primary at the time, plan version 2; now secondary)*.
- **A removed hypothesis** leaves its links. The task shows *H… removed from the plan in version N*, and its Hypothesis step needs attention.
- **All-methods results** have no task, so they are not linked in 37.0. They show *Not linked to a hypothesis*. 37.4 merges the two modes.

### 7.6 Step status per task

Statuses are derived, never stored, except an explicit *skipped* for the optional interpretation (`research_tasks.state["skipped"]`).

| Step | Done when | Needs attention when |
|---|---|---|
| Hypothesis | the task tests a hypothesis of the current plan (*No hypothesis* is shown as skipped, not missing) | its hypothesis was removed from the plan |
| Variables | every required role of the goal is filled | a chosen variable is no longer in the dataset |
| Design | no blocker, and the required confirmations were given for the current data and variables (K1) | confirmations were given for other data or variables (K1) |
| Method | a method is chosen, recommended or the researcher's | it differs from the plan's intended method and no deviation is recorded |
| Result | a current result of this set-up exists | the latest result is stale, or the set-up changed after it |
| Checks | every assumption check of the current result is ticked (K2) | some are not ticked |
| Interpretation | a note is written (K2), or the step was skipped | — |
| Report | the current result is in the report | an older result of the task is in the report while a newer one exists |

- The first step that is not done is *current*.
- The statuses appear in three places: the task header on Analyze; the hypothesis row (*5 of 8 steps done · next: Checks*); and the **journey strip**. The strip keeps its seven chips, data keys and navigation, but its statuses come from the open task, or from the task of the first primary hypothesis. This fixes U10. The test that asserted the old behaviour changes deliberately (§11).

### 7.7 Hypothesis–analysis consistency checks

**What they are.** Pure functions of the plan history, the tasks, the results (structured result, options, provenance, `run_status`, review ticks) and the protocol records. They make no engine call and no network call. They give the same answer before and after a restart, and they are unit-tested one by one.

**Severities.**
- *Warning:* the researcher must decide, by resolving it or recording a reason.
- *Info:* a disclosed fact.
- *Passed:* shown collapsed.

**What a check never does.** It never blocks *Run* or the export: the existing gate for stale results in the report stays as it is. It never decides for the researcher. It never says that a hypothesis is supported.

| Key | Condition (deterministic) | Severity | Resolution offered | Fingerprint facts |
|---|---|---|---|---|
| `H-NO-TASK` | a primary or secondary hypothesis is saved and no task tests it | warning (info if exploratory) | *Create the analysis for H…* | — |
| `H-DIR-TWOSIDED` | the direction is greater or less, and the task's method reports two-sided p (every method in this version) | warning | make H two-sided (an ordinary edit before results; after results a plan change recorded in the history), or **acknowledge** (*the two-sided p is reported; the sign of each estimate is compared with the prediction*) | direction, method key and method option |
| `H-DIR-OMNIBUS` | the direction is one-sided and the test compares 3 or more groups or occasions (Kruskal–Wallis, ANOVA, Welch ANOVA, batch groups with 3+ groups, Friedman, RM ANOVA) or is a χ² larger than 2×2 | warning | name the expected order and read the pairwise comparisons, make H two-sided, or acknowledge | direction, method, number of groups |
| `H-DIR-SIGN` | after a result: an estimate's sign is opposite to the prediction (correlation coefficients; a two-group difference when `expected` is set) | info | none; it is listed (*AntisocialAction: ρ = .08; H1 predicts negative coefficients*) | — |
| `H-FAMILY-UNCORRECTED` | a batch family of k ≥ 2 tests uses `adjust = none` | warning | open the task with Holm chosen (*Run again* makes a new result version), or acknowledge (*each test answers its own hypothesis*) | k, adjustment |
| `H-FAMILY-SPLIT` | the tasks of one hypothesis, or of hypotheses with the same family label, together hold T tests, but each was corrected only for its own k | warning | acknowledge (*separate families by design*) or relabel; a correction across tasks is 37.2 | family label, task ids, k per task |
| `H-ALPHA` | the plan's α differs from the α of the result (structured options, .05 today) | warning | acknowledge and judge p against the plan's α; 37.2 passes the plan's α to the engines (open question 5) | plan α, result α |
| `H-METHOD-DIFFERS` | the plan has an intended method, and the task's method or options differ | warning | **record as a deviation** (reason required), or change the analysis | planned and actual method and options |
| `H-VARIABLES-DIFFER` | the plan has variables, and the task's selection differs (another first variable or group; outcomes left out or added) | warning | record as a deviation, or change the analysis | planned and actual roles |
| `H-SPEC-CHANGED` | a later result of a task linked to H differs in roles, method or options from the first result linked to H: a change after results | warning | record as a deviation (*what changed after the first result and why*) | the first and the later specification |
| `H-ASSUMPTIONS-OPEN` | the current result has assumption checks that are not ticked (K2) | warning | *Review the assumptions*; not acknowledgeable, the boxes are ticked | — |
| `H-RESULT-STALE` | `run_status` is stale (data changed, a level changed, or the recalculated report differs) | warning | *Recalculate with current data* (exists); not acknowledgeable | — |
| `H-DESIGNATION-CHANGED` | the designation changed after results (§7.4) | warning, shown as *recorded* with its reason | the reason is required at the save | from, to, plan version |
| `H-ADDED-AFTER` | standing *added after results*, and the designation is not exploratory | warning (info when exploratory) | mark exploratory, or record a justification | first version, results then |
| `H-LINKED-LATE` | a task was linked to H after it had results | info | none; it is disclosed | — |

**Acknowledgements are bound to their facts.**
- An `acknowledgement` record stores the check key, the hypothesis, the task, and the SHA-256 of the canonical JSON of the check's facts (the last column). A check counts as acknowledged only while those facts are unchanged. Changing the direction, the method or the family size reopens it, as K1 does for confirmations.
- A reason is always required.
- Deviation-type checks are resolved by a deviation record instead.

**Deferred to report QA (37.3).** Results of one hypothesis from several data versions (the report already names versions), and selective reporting (two analyses test H1, one is in the report).

### 7.8 Protocol deviations

- **What a deviation is.** A recorded difference between the plan and what was done. Fields: what changed (method, variables, direction, α, designation, sample, exclusions, data, other), planned, actual, the reason, the time, the plan version, the number of results of the hypothesis and of the project at that moment, and whether it was *detected* (from a check) or *declared* by the researcher (*Record a deviation…*, e.g. *data collection stopped at n = 55, 80 were planned*).
- **Never deleted.** Withdrawing a deviation adds a `withdrawal` record that points to it, and the history shows both.
- **Acknowledgement or deviation.** An *acknowledgement* says that a known mismatch is handled by design (a two-sided test of a one-sided hypothesis). A *deviation* says that what was done differs from what was planned. Both need a reason, and both are reported.
- **Never automatic.** The app detects candidates; only the researcher records one.
- **Where they appear:** the hypothesis detail; the result's *Tests H…* card; the history; the Word report (§7.10).

### 7.9 The next action

One sentence, one button that does exactly what it names, an optional secondary button (*Skip*), and *Why this?*, which lists the facts evaluated (✓/○). It sits at the top of the Project page (replacing the *Next step* card) and in the footer of Data, Analyze, Results and Reports, using the existing page footer mechanism.

**Rules.** The first rule that applies wins. Hypotheses are taken by designation: primary, then secondary, then exploratory but only when linked.

| # | Condition | Action |
|---|---|---|
| N1 | no typed question with text, and the project has no result | *Write your research question* (the field is on the page) |
| N2 | a question of a testable type has no hypothesis | *Add a hypothesis to Q1* |
| N3 | the plan has unsaved hypotheses or changes | *Save the plan before any result* → *Save plan version* |
| N4 | no dataset | *Open the data* → *Open CSV / Excel…* |
| N5 | unconfirmed levels (of the variables the next task uses; otherwise all) | *Confirm the measurement levels* → Data |
| N6a | the hypothesis has no task | *Create the analysis for H1* |
| N6b | its task has no current result | *Choose the variables and run the analysis for H1* → the task |
| N6c | its result is stale | *Recalculate H1's result with the current data* |
| N6d | an open warning check, other than assumptions | *Decide on: “H1 predicts a negative direction …”* → the check |
| N6e | assumption checks not ticked | *Review 3 assumption checks of H1's result* |
| N6f | no note and not skipped | *Write your interpretation of H1's result (optional)* · *Skip* |
| N6g | the result is not in the report | *Add H1's result to the report* |
| N7 | the report was not exported since its last change (a `report_exported` event) | *Export the Word report* → Reports |
| N8 | otherwise | *Every planned step is done* |

**Behaviour.**
- **Without a plan.** Data-first work is not nagged: once a project has results but no plan, N1–N3 become a secondary link (*Add the research question these analyses answer; they will be shown as exploratory*). The bar then follows N4–N8 for the tasks, as today's `next_step()` does.
- **No disabled button.** When the action cannot run, the bar says why in text (§2.5). The button is a normal Flet button, reachable by Tab.
- **Tasks without a hypothesis** are outside the plan's path; their stale results are still counted by the existing project chip.

### 7.10 Changes, page by page

New data keys for the harness and the journeys are in `code` font.

**Project page.**
- The next-action bar (`next-action`, `next-why`, `next-alt`) replaces the Next step card.
- *Research questions and hypotheses* replaces the Question and Research plan cards.
  - *List:* questions (`plan-question-{i}-type`, `plan-question-{i}-text`, `plan-question-add`); each hypothesis as a focusable row (`hyp-{i}`) with designation, direction, α, standing, the analysis that tests it, *n of 8 steps* and a count of open checks; *Add hypothesis to Q…*; *Save plan version* and *Plan history* (existing keys).
  - *Detail of the selected hypothesis:* fields and *Edit*; *Analysis that tests H…* with the step status, *Create the analysis* / *Open the task* (`hyp-{i}-analysis`) and *Show the evidence* (`hyp-{i}-evidence`: the result table excerpt, provenance, reviewed assumptions, measurement note); *Checks against the plan* (`hyp-{i}-check-{key}-…`); *Deviations from the plan* (`hyp-{i}-deviation-new`); *History* (`hyp-{i}-history`).
  - Wide windows show list and detail side by side; below about 1,180 px they stack.
- Data sources, questionnaires, results and report stay.

**Analyze.**
- Task chips show the hypothesis: *H1 · UCLA with 8 variables*.
- Step 1 gains *Tests hypothesis* (`task-hypothesis`).
- A step-status row sits under the task bar (`task-steps`).
- Step 4 lists the plan checks that apply before Run (`task-checks`: direction, method, family, α).
- The batch result card (step 5) gains the *Tests H…* line, the assumption ticks (`task-review-{i}`) and the note (`task-notes`, `task-skip-notes`). They are bound to the same persisted state as Results (K2), so the beginner does not leave the task to review.
- The footer shows the next-action bar.

**Results.** The result detail gains *Tests H…* (`result-hypothesis`): the snapshot, the open checks and the recorded deviations, with *Open H…*.

**Reports.** No new control. In *Hypotheses*, the plan builder adds per hypothesis:
- the direction;
- *Tested by: “UCLA with 8 variables” (Spearman's ρ, 8 tests, Holm), result current*;
- each deviation (*Deviation from the plan (method): Pearson's r planned; Spearman's ρ used. Reason: …; recorded before H1 had any result.*);
- each acknowledgement;
- a designation change made after results.

No number is computed. EN, LV and RU are written. The full hypothesis–evidence table and report QA are 37.3.

**Data.** The footer shows the next-action bar. The rest is unchanged.

### 7.11 Code structure

- **New `research_workflow.py`.** No Flet imports, like `workspace_methods.py`. It holds the question types and the drafts (text keys), `task_steps(...)`, `hypothesis_checks(...)`, `fingerprint(...)`, `next_action(...)` and `designation_history(...)`, with plain data classes `Step`, `Check` and `NextAction` (text key, parameters, action).
- **`project_store.py`.** Migration F+1; the plan JSON v2 in `normalise_plan`; `add_protocol_record()` and `protocol_records()`, with no update or delete; a `hypothesis=` argument in `record_run`; a `report_exported` event; `copy_for_format(F)` (§8.6).
- **`project_session.py`.** Pass the hypothesis snapshot to `record_run`; restore it into `ResultEntry.provenance`; read the protocol records once per open and after each write.
- **`workspace_plan.py`.** The hypothesis workspace (list, detail, checks, deviations, history).
- **`workspace_analyze.py`.** The link control, the step row, the checks before Run, the review ticks and note in the task result, `footer()`.
- **`workspace_projects.py`, `workspace_shell.py`.** The bar on the project page and the journey-strip statuses from `task_steps`.
- **`research_report.py`.** The hypothesis lines.
- **`workspace_text.py`.** About 90 keys in EN, LV and RU; LV and RU marked for native review.
- **Untouched:** the engines, `analysis_runs`, the installer, the updater, the workflows, the locks.

### 7.12 Localization, accessibility, display scales

- **Language.** Every new string is a text key in three languages. Method names stay international. LV and RU are drafts for native review; no review has taken place yet.
- **Controls.** Each new control is a button, dropdown, checkbox or text field with a visible label; the hypothesis rows are buttons, not ink containers. No new primary action relies on the disabled state (§2.5).
- **Announcements.** The status line already announces outcomes: *Plan version 2 saved*, *Linked to H1*, *Deviation recorded*.
- **Display scales.** At 1,097 × 617 logical pixels (175 % on 1080p) the bar takes at most two lines and the hypothesis list and detail stack. Checked at 100/125/150/175 % in the Windows DPI journey.
- **Keyboard.** No new shortcut in 37.0; a shortcut for the next action is open question 12. Typing in the hypothesis editor never rebuilds the page, and a browser state check is added (§11).

### 7.13 The PR

One draft PR, *Stage 37.0: hypothesis workflow*, in four reviewable commits. The first two can ship as 37.0a if the owner wants a smaller first PR.
1. The model: migration, plan v2, protocol records, `research_workflow.py` with its unit tests.
2. The Project page: the hypothesis workspace and the next-action bar.
3. Analyze and Results: link, step status, checks, review in the task, the journey statuses.
4. The report lines, the Windows journey `stage37-hypothesis`, and `docs/STAGE37_UX_RESULTS.md` with the measured counts.

**As built (default 14 of §13): 37.0a now, 37.0b later.** 37.0a is three commits: (1) the model (format 6, plan v2, protocol records, the hypothesis snapshot); (2) `research_workflow.py` with its unit tests and texts; (3) a minimal UI (the next-action bar, the hypothesis list and detail, the link in Analyze, the step row, the *Tests H…* line on Results). The report lines (§7.10), the Windows journey and the measured UX results are 37.0b. Two compatibility choices of 37.0a:
- A project without a started plan keeps the Stage 34.5 next-step order, texts and `data` keys, which the Windows journeys and the tests use. The plan-first rules (N1–N6) apply once a question or a hypothesis is started.
- The Question card (`project-question`) stays. The typed questions of the plan are added beside it, not in its place.

---

## 8. Data model: additive changes

### 8.1 Format F+1: one new table

F is the release candidate's latest format. The RC fixed K2 without a migration, so F = 5 and 37.0a adds **format 6** (`_migrate_v6`), with one migration that only creates objects. It does not alter or rewrite an existing table. In 37.0a the table also has two triggers that refuse every `UPDATE` and `DELETE`, so append-only holds in the database itself, not only in the store's API.

```sql
CREATE TABLE IF NOT EXISTS protocol_records (
    id TEXT PRIMARY KEY,                      -- uuid4
    at TEXT NOT NULL,                         -- UTC, ISO 8601
    kind TEXT NOT NULL CHECK (kind IN ('deviation', 'acknowledgement', 'designation',
                                       'justification', 'link', 'withdrawal')),
    hypothesis_id TEXT,                       -- plan hypothesis id; kept if it leaves the plan
    task_id TEXT,                             -- research task id; kept if the task is deleted
    run_id TEXT,                              -- the run concerned, if any (informational)
    check_key TEXT NOT NULL DEFAULT '',       -- e.g. H-DIR-TWOSIDED
    fingerprint TEXT NOT NULL DEFAULT '',     -- SHA-256 of the facts the check evaluated
    plan_version INTEGER,                     -- plan version current at the time
    results_of_hypothesis INTEGER NOT NULL DEFAULT 0,
    results_in_project INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '{}',        -- JSON: what, planned, actual, from, to
    reason TEXT NOT NULL DEFAULT '',          -- the researcher's words
    supersedes TEXT                           -- a withdrawal names the record it withdraws
);
CREATE INDEX IF NOT EXISTS protocol_records_hypothesis ON protocol_records (hypothesis_id, at);
```

- The table is append-only: the store has no update or delete method for it.
- Ids are plain text, not foreign keys, so a record outlives the task, run or hypothesis it names. A task can be deleted, and a post hoc test replaces its run; the history must stay.
- `IF NOT EXISTS` makes the migration safe for the copy described in §8.6.
- The `.sra` backup, *Duplicate* and the trash already copy the whole database, so they carry the table.

### 8.2 The plan JSON, version 2

In `plan_versions.plan`, all additions are optional. Their absence means a 36.x plan.

```json
{
  "objectives": "", "design": "", "population": "", "ethics": "", "preregistration": "",
  "plan_format": 2,
  "questions": [{"id": "1a2b3c4d5e6f", "type": "relate", "text": "Is loneliness related to …?"}],
  "hypotheses": [{
    "id": "0f1e2d3c4b5a", "text": "…", "h0": "…", "direction": "two-sided",
    "priority": "primary", "alpha": 0.05,
    "outcome": "", "predictors": "", "covariates": "", "method": "", "family": "", "exclusions": "",
    "question_id": "1a2b3c4d5e6f",
    "method_key": "batch_correlation", "method_options": {"method": "spearman", "adjust": "holm"},
    "roles": {"x": "UCLA", "ys": ["AssertiveAction", "SocialJoining"]},
    "expected": ""
  }]
}
```

`normalise_plan` validates the additions:
- `type` must be in `GOALS`, and a question id must be 12 hex characters;
- `question_id` must name a question of the same plan, or be empty;
- `method_key` must be in `METHODS`, and every option must be one of its choices;
- `roles` keys must be roles of the question's goal, with names as text of at most 200 characters;
- `expected` is at most 200 characters;
- a plan holds at most 100 questions.

The 36.x fields keep their meaning and are still written (`priority` is the designation). The plan stays human-authored: no version is ever saved by the app on the researcher's behalf.

### 8.3 Existing columns put to use

- `research_tasks.hypothesis_id`: filled (§7.5).
- `research_tasks.state` (JSON): `skipped` steps.
- `runs.provenance` (JSON): the `hypothesis` snapshot (§7.5).
- `events`: `designation_changed`, `report_exported`, `protocol_record`. This is the activity log; the records themselves are in their own table.

Step statuses, checks and the next action are derived and not stored.

### 8.4 Old projects

- Projects of formats 1…F open as today: the chain of migrations runs, then F+1, after a copy in `.backups/`, in one transaction.
- A plan without `plan_format` is shown in the typed editor: its hypotheses have no question link (*Not linked to a question*), and the old free text is under *More details*. The project's Question row is Q1, *not chosen*.
- Nothing is converted until the researcher saves a plan version.

### 8.5 What the AI receives

`ai_context._plan` keeps its fixed field list. Questions, records and snapshots are not sent; a regression test checks this. AI planning is 37.5.

### 8.6 An older version with a newer project

**What the RC (format F) does with a project of format F+1:**
- The project still appears on Home, because the list reads only the `project` table.
- Opening it is refused without any write, by the existing read-only check in `migrate()`: *This project was saved by a newer version (format F+1); this version reads up to format F.*
- A `.sra` backup made by 37.0 can be restored by the RC (its package format is unchanged), but the restored project is refused in the same way when opened.

**How to go back.** The updater never offers an older version, so a downgrade is a deliberate reinstall. Two paths exist:
1. **The automatic backup.** The copy `.backups/<project>-v{F}-<time>.sqlite3` holds the project as it was before 37.0 first opened it, without what was done in 37.0.
2. **A copy for an older version** (37.0, *Settings → Your data*, or the project's *Back up…* menu). It duplicates the project and sets the copy's format to F.
   - The RC opens the copy and ignores what it does not know: the table, the plan's extra keys, the snapshot.
   - The RC drops the plan's extra keys only when it saves a new plan version.
   - If the copy comes back to 37.0, the migration runs again. `IF NOT EXISTS` keeps the records.
   - Typed fields missing from a plan version saved by the RC are carried forward by hypothesis id from the last version 2 plan. A notice names them; nothing is restored silently.

Whether this copy ships in 37.0 or in 37.0.x is open question 2.

### 8.7 Rejected alternative: no format change

All 37.0 data could live in existing JSON fields (plan JSON, task state, provenance, events) without changing the format, so the RC would keep opening the projects. This was rejected for three reasons:
- **Silent data loss.** The RC would open such a project and write to it. Its `normalise_plan` strips the new plan keys on every save, so typed questions, links to questions and deviations kept in the plan would silently vanish from the current version.
- **A broken guarantee.** It breaks the documented rule that an older version never writes to a project saved by a newer one (`docs/IN_APP_UPDATES.md`).
- **The wrong home for deviations.** They would have only the activity log, which is not structured.

A read-only mode for newer formats in the RC was also considered. `ProjectBinding` saves on every session event, so making the RC safe read-only is not a small RC change; it is open question 1.

---

## 9. Compatibility with the installer, the updater and persistent projects

- **Release candidate.** Stage 37 work stays on `claude/stage37-research-workflow`. The 37.0 PR is stacked on the RC branch after K1–K3 land, and nothing merges until the RC is accepted (open question 9). The feature branch does not touch:
  - `packaging/`, `.github/workflows/`, `requirements*.txt` or the build locks;
  - `app_identity`, the update manifest or the signing configuration.
- **Installer.** It is unchanged. Projects stay in the per-user data folder and are never in the program folder. Uninstalling keeps them, and reinstalling finds them. `docs/` (this design and the prototype) is not in the bundle.
- **Updater.** The signed channel and the rules (no downgrade, channel, signature) are unchanged.
  - An update replaces the program folder and never touches a project. A project is migrated only when it is opened, after the backup.
  - Whether 37.0 previews use the preview channel the 1.0.0-preview.1 users follow is open question 10: they would receive 37.0 and their projects would be migrated on first open.
- **Persistent projects.**
  - Every new state is saved at once (write-through, like tasks and charts).
  - A crash during the migration leaves the old format; one transaction.
  - A crash after it leaves a consistent F+1 project.
  - The project lock and the recovery message are unchanged.
- **The Windows journeys.** The 13 packaged GUI journeys and the 5 installed-program journeys still run in their order. `stage37-hypothesis` is appended after the last of them, so the state every earlier journey meets is unchanged. The A→B update journey (`update-a-to-b`) gains one check: a project made in A opens in B, is migrated with a backup, and keeps its results and tasks.

---

## 10. Acceptance criteria

Each criterion is an automated test unless it says otherwise. The *Test* column names the test file or journey.

| ID | Criterion | Test |
|---|---|---|
| AC-1 | A question saves with a type from `GOALS`; an unknown type is refused with a message and nothing is saved; a 36.x plan opens and shows its Question row as Q1 (*not chosen*) | `test_stage37_workflow`, `test_stage37_store` |
| AC-2 | *Add hypothesis* drafts H1/H0 for every question type in EN, LV and RU; direction defaults to two-sided, designation to primary; the α rule is unchanged | `test_stage37_workflow` |
| AC-3 | A hypothesis saved while the project has no result is *planned before any result*. Changing its designation after a result is refused without a reason and recorded with one; the record shows in the history and the Word report. A change before results needs no reason. | `test_stage37_store`, `test_stage37_reports` |
| AC-4 | *Create the analysis for H1* makes a task with `hypothesis_id = H1` and the goal of its question; the link and the result's snapshot (id, plan version, designation, direction, α) survive a restart; relinking a task with results writes a `link` record and lists the earlier results as *linked after calculation* | `test_stage37_ux`, `test_stage37_store` |
| AC-5 | The eight step statuses follow §7.6 and are the same after a restart. A result of another task does not tick this task's steps. The journey strip shows the open task's statuses. | `test_stage37_workflow`, `test_workspace_journey_strip` (updated) |
| AC-6 | Each of the 15 checks has a case that produces it and one that does not. Checks call no engine and no network, and the list is identical after a restart. | `test_stage37_workflow` |
| AC-7 | An acknowledgement needs a reason. Changing a fingerprinted fact (direction, method, family size, α) reopens the check. | `test_stage37_workflow` |
| AC-8 | A deviation needs a reason. The store has no update or delete for records. A withdrawal is a new record. Deviations appear in the hypothesis detail, the result card and the Word report. | `test_stage37_store`, `test_stage37_reports` |
| AC-9 | Each next-action rule N1–N8 has a test. The bar never shows a disabled button. Its button performs exactly what its label names. A project with results and no plan does not get N1–N3 as its main action. | `test_stage37_workflow`, `test_stage37_ux` |
| AC-10 | With `CountingWorkspace` plus typed fields and page changes: the beginner flow takes ≤ 20 interactions, ≤ 5 typed fields and ≤ 4 page changes; the professor flow ≤ 6 interactions and ≤ 2 page changes. The Stage 36 baselines are unchanged: 8, 2, 8, 8, 2, 1 and 3. | `test_stage37_ux`, `test_stage36_ux_baseline` |
| AC-11 | Formats 1…F migrate to F+1 with a copy in `.backups/` in one transaction. An F+1 project is refused by a build of format F without any write (simulated by patching `SCHEMA_VERSION`). The copy for an older version opens at F and comes back to F+1 with its records. | `test_stage37_store` |
| AC-12 | The AI *plan* preview contains exactly the 36.x fields | `test_workspace_ai` (extended) |
| AC-13 | Every new key exists in EN, LV and RU, with the same placeholders | `test_workspace_foundations` (`test_every_key_has_three_languages_with_the_same_placeholders`) |
| AC-14 | New actions are labelled buttons, the hypothesis rows take keyboard focus, and typing in the hypothesis editor keeps the focus and every character | harness test; browser state check `plan-type-hypothesis` |
| AC-15 | The *Hypotheses* section lists the direction, *Tested by …*, deviations, acknowledgements and designation changes in EN, LV and RU; table numbering is unchanged | `test_stage37_reports`, `test_stage36_reports` |
| AC-16 | Windows journey `stage37-hypothesis` (packaged program): create a project → Q1 and H1 → save → open the CSV → accept levels → create the analysis from H1 → Spearman batch → review ticks → add to report → export Word (its Hypotheses section has *Tested by*) → restart (link, statuses, records back). Negative cases: a designation change after results without a reason is explained and nothing is saved; a project of a newer format is refused with the message. | `tools/windows_gui_e2e.py` |
| AC-17 | Human acceptance, not automated: the owner's checklist (`STAGE368_REAL_USER_ACCEPTANCE`) gains the beginner and professor flows above, done on the installed preview | manual, signed off by the owner |

---

## 11. Regressions to watch

| Area | Risk | Guard |
|---|---|---|
| Stage 36 workflows | counts grow (eight correlations from Analyze without a hypothesis must stay 8) | `test_stage36_ux_baseline` thresholds; the next-action bar adds no step to them |
| Journey strip | its statuses change on purpose (U10); the D1 navigation must not | update `test_the_strip_follows_the_research`; EXE journey `stage36-tasks` "each research step opens itself" |
| Research plan | the typed editor breaks the `plan-*` keys or the version tests | keep the keys and control types; `test_workspace_plan` |
| Report | new lines shift the table numbering or duplicate paragraphs | `test_stage36_reports`, `test_report_docx`, EXE `stage36-report` |
| AI context | new plan data reaches a prompt | AC-12 |
| Migration and backups | F+1 breaks older formats, `.sra` round trip, duplicate or trash | `test_project_store`, `test_project_session`, AC-11 |
| Focus and typing | the editor re-renders on input; the bar moves the focus | the existing browser state checks and `plan-type-hypothesis` |
| Async handlers | a lambda returning a coroutine makes a button dead (the Stage 36 Flet pitfall) | the harness `dispatch` already fails on it |
| Accessibility | a disabled primary action read as available by Narrator | reasons shown as text (§7.9); AC-14 |
| Compact windows | the bar or the hypothesis detail clips at 1,097 × 617 | Windows DPI journey at 150/175 %; browser screenshots |
| Render cost | checks recomputed per render with database reads | records read once per open and after writes; checks from memory |
| K1/K2 interplay | 37.0 assumes the RC's persistence of ticks and notes | rebase on the RC; AC-5 after a restart |
| Old free-text hypotheses | lost or hidden by the typed editor | shown under *More details*; `normalise_plan` keeps them |

---

## 12. Not in 37.0, and the roadmap

**Explicitly out of 37.0.**
- **AI planning** (37.5): AI at the plan stage (review AI1), a local OpenAI-compatible endpoint (AI5), the accept/reject log of drafts (AI3). In 37.5 the AI explains the deterministic check list of §7.7 (review AI2); it does not replace it.
- **Report QA** (37.3): structured assembly without repeated text (U7), full localization of engine strings (U11), the hypothesis–evidence table, linked paragraphs, alerts for stale or unverified results, report diffs, the checks deferred in §7.7.
- **The measurement layer** (37.1): scoring keys from the imported questionnaire, reverse items, α/ω per subscale, value labels, moving data preparation out of the classic panel (S1, K3), and measurement evidence linked to later analyses.
- **Also not in 37.0:**
  - one-sided tests in the engine (open question 4);
  - a correction across tasks;
  - passing the plan's α to the engines;
  - batch descriptives, a correlation matrix with p, intervals for effect sizes (37.2);
  - the two-panel task and Chart Studio, and variable search (37.4);
  - workflow templates and a safe re-run on a new dataset version with diffs (#63 priority 2; 37.2/37.3);
  - renaming the navigation areas.

**Roadmap after 37.0** (the review's, adjusted to this design):

| Increment | Content |
|---|---|
| 37.1 | the measurement layer above; the hypothesis detail shows the measurement evidence of its variables |
| 37.2 | batch descriptives (U1), a matrix with p (S3), effect-size intervals (S4), one method rule for 1 and N outcomes (S5), the plan's α in the engines, a correction across tasks of one family, one-sided p if approved |
| 37.3 | the report: structured assembly, full localization, the hypothesis–evidence table, report QA |
| 37.4 | the hybrid's task surface (two panels, tabs when narrow), Chart Studio in two panels (U2), variable search and ranges (U8), method kept when variables change (U4), U5, U6, U13; decided with the user test (§5.4) |
| 37.5 | AI as above |
| 37.6 | sensitivity (S6) and robustness (S7) |

---

## 13. Open questions for the owner, with the defaults used in 37.0a

The coordinator recorded an architect default for each question so that 37.0a could be built. **These are defaults; the owner may change any of them.** Where a default shaped the code, the last column names where.

| # | Question | Default (owner may change) | Where it shows in 37.0a |
|---|---|---|---|
| 1 | **Project format.** Accept format F+1 (one additive table, a backup before migration, a copy for older versions)? Or should the RC first learn to open newer formats read-only (§8.7)? | Format F+1 = **6**, additive. The RC (format 5) refuses a format-6 project without writing to it. | `project_store._migrate_v6`; `tests/test_stage37_store.py` (`FormatSixTests`) proves the backup, the migration and that a format-5 reader refuses without changing a byte. |
| 2 | **The copy for an older version.** In 37.0, or in 37.0.x? | Not in 37.0a. | — |
| 3 | **Standing rule.** Keep today's strict rule (any result in the project makes a later hypothesis "added after results"), or count only results that used its variables? | Keep the strict rule. | `H-ADDED-AFTER` in `research_workflow.hypothesis_checks` uses `runs_before`, counted project-wide. |
| 4 | **One-sided hypotheses.** Keep two-sided tests with the check and acknowledgement of §7.7, or add one-sided p-values to the engines in 37.2? | Engines stay two-sided; only the direction checks. No engine and no `analysis_runs` change. | `H-DIR-TWOSIDED`, `H-DIR-OMNIBUS`, `H-DIR-SIGN`. |
| 5 | **α.** Pass the plan's α to the batch engines? In 37.0 or 37.2? | Not passed. The `H-ALPHA` check reports a plan α that differs from the α the result used. | `H-ALPHA`. |
| 6 | **Vocabulary.** *Primary / Secondary / Exploratory*, stored as `priority`, or *Confirmatory / Exploratory* with a second axis? | Primary / Secondary / Exploratory, stored in `priority`. | The existing `plan-*-priority` dropdown and its texts. |
| 7 | **The first run as reference.** When the plan has no typed variables or method, may the first result linked to a hypothesis be the reference for later changes? | Yes. | `H-SPEC-CHANGED` compares later results of the task with its first result linked to the hypothesis. |
| 8 | **The report in 37.0.** Add the hypothesis lines of §7.10, or leave the report untouched? | The Word-report hypothesis lines are 37.0b. | The report is unchanged in 37.0a, except that an export is now logged (`report_exported`) for the next action. |
| 9 | **PR base and timing.** | The PR stacks on `claude/stage368-rc`. | The branch merges the RC head `07c37f6`. |
| 10 | **Version and channel.** | No version or channel change. | — |
| 11 | **The user test.** Who recruits the students and supervisors? | The owner's task. | — |
| 12 | **Keyboard shortcut** for the next action. | No shortcut. | — |
| 13 | **Native review** of the new LV and RU texts. | LV and RU are drafts, marked "needs native review". | The Stage 37.0a block of `workspace_text.py`; the key list is in `docs/STAGE37_0A_STATUS.md`. |
| 14 | **PR size.** One 37.0 PR, or 37.0a and 37.0b? | 37.0a now, 37.0b later (§7.13). | `docs/STAGE37_0A_STATUS.md`. |

---

## Appendix A — Baseline measurement (55f94b1, re-measured at 07c37f6)

`python docs/stage37/measure_baseline.py`, from the repository root, with the locked environment (Python 3.12, Flet as locked). Counted controls by `data` key; ⟨…⟩ marks what is counted apart or not counted. The script prints the short commit it measured in each table title.

**Re-measured at the RC head `07c37f6`** (the merge `e06736c` on this branch, before any 37.0a change): beginner 22 interactions, 10 typed fields, 5 page changes and 2 system dialogs; professor 14 interactions, 0 typed, 6 page changes; scale quality 5 · 0 · 2; `hypothesis_id` of the tasks still `[None, None]`. The only difference from `55f94b1` is the line *lost after the restart*, which now reads `nothing`: K2 (`23f4f4a`) keeps the note, the review ticks and the study title.

- **Beginner.**
  1. Project: `project-new-title` (typed), `project-create`.
  2. Question: `project-question` (typed); saved on blur ⟨not counted⟩.
  3. Hypothesis: `plan-add`; `plan-h0-text`, `-h0`, `-outcome`, `-predictors`, `-method`, `-family` (typed); `plan-save`.
  4. Data: *Open CSV / Excel…* ⟨+ system Open dialog⟩.
  5. Levels: `data-accept-confirm`, `data-accept`.
  6. Scales: nothing to do.
  7. Analysis: `nav-analyze`, `goal-relate`, `role-x` (dropdown), `role-y-all-scale`, `role-y-Age` (untick), `alt-batch_correlation-spearman`, `guided-run`.
  8. Link: no control.
  9. Interpretation: `task-open-result`, `result-interpretation-section` (expand), `result-notes` (typed), `review-0…2`.
  10. Report: `result-add-report`, `nav-reports`, `reports-study-title` (typed), *Export Word report…* ⟨+ system Save dialog⟩.
- **Professor**, a new workspace on the same data folder, which is a restart; set-up not counted: a second task (Kruskal–Wallis by UCLA_Level) and H2 in the plan.
  1. `project-open-<id>`.
  2. `plan-history` (expand).
  3. `nav-results`, `result-1`.
  4. Provenance: reading.
  5. `result-interpretation-section`, `result-depth` → *Professor*, `result-method-notes`.
  6. `nav-analyze`, `task-<id>`.
  7. `nav-data`.
  8. `nav-results`, `result-2`.
  9. `nav-reports`, `reports-preview`.
  10. No control exists.

Output at `55f94b1`:

```
== Beginner flow today (55f94b1)                                   inter.  typed  pages
1 project: title, Create project                                        1      1      1
2 research question: one text field                                     0      1      0
3 hypothesis: add, six text fields (direction, priority, α default), save  2   6      0
4 data: Open CSV / Excel… (+ the system Open dialog)                    1      0      1
5 measurement levels: accept the suggestions, 0 corrections             2      0      0
6 scales: the file holds totals; α/ω are refused for totals (D5)        0      0      0
7 analysis: eight Spearman correlations in one batch (Stage 36)         8      0      1
8 link the analysis to H1: no control exists (hypothesis_id stays empty) 0     0      0
9 interpretation: open the result, expand, note, 3 review ticks         5      1      1
10 report: add, Reports, study title, Export Word (+ the Save dialog)    3      1      1
TOTAL                                                                  22     10      5   + 2 system dialog(s)

== Professor flow today (55f94b1)                                  inter.  typed  pages
TOTAL                                                                  14      0      6
lost after the restart: note, review ticks, study title
hypothesis_id of the tasks before the restart: [None, None]

== Scale quality on item data today (55f94b1)
reliability of 10 items (item_diagnostics)                              5      0      2
```

## Appendix B — Prototype click paths (estimates)

Each path is the flow guide of `docs/stage37/prototype.html`. `#selftest` replays it through the page's handlers and reports the counts; a headless-Chromium run replayed it by real clicks at 100 % and 125 %. Steps typed into a field count once in *typed*, and the two system dialogs are apart.

**Hybrid, beginner: 20 · 5 · 4 · 2.**
1. Home: title (typed), *Create project* → Project.
2. Q1 kind *Relationship between two variables*; question text (typed).
3. *Add hypothesis to Q1*; edit H1 (typed); *Save plan version*.
4. Bar: *Open CSV / Excel…* ⟨Open dialog⟩ → Data.
5. Tick the confirmation; *Use suggestions…*.
6. Bar: *Create the analysis for H1* → Analyze, linked, goal chosen.
7. First variable UCLA (dropdown, 2); *All quantitative (9)*; untick Age; Spearman *Use instead*; *Run Spearman's ρ*.
8. Three review ticks in the task's result; note (typed); *Add to report*.
9. Bar: *Open the report* → Reports.
10. Study title (typed); *Export Word report…* ⟨Save dialog⟩.

**Hybrid, professor: 6 · 0 · 2.**
1. *Open* → Project.
2. Row H1: checks (one-sided vs two-sided, acknowledged; one coefficient against the prediction), the deviation (method, recorded before H1's first result), history.
3. *Show the evidence*: table excerpt, provenance (levels accepted from suggestions, D5 note), 3 of 3 reviewed.
4. Row H2: designation changed after 2 results with its reason; one assumption check open.
5. Reports.
6. Preview of the Hypotheses section.

**A, beginner: 19 · 5 · 2 · 2.**
1. Home: title, *Create project* → Study.
2. Q1 kind, text; *Add hypothesis to Q1*, H1, *Save plan version*.
3. *Next step: Open the data for H1* ⟨Open dialog⟩, staying on Study.
4. H1 › *Data and scales*: UCLA (2), *All quantitative (9)*, untick Age, tick, *Use the suggested levels for these variables*.
5. H1 › *Analysis*: Spearman *Use instead*, *Run*.
6. H1 › *Checks*: 3 ticks.
7. H1 › *Interpretation and report*: note, *Add to report*.
8. *Next step: Open the report* → Report.
9. Title, *Export Word report…* ⟨Save dialog⟩.

**A, professor: 8 · 0 · 2.** *Open* → Study; H1 › *Analysis*; H1 › *Checks*; H1 › *History*; H2 › *Checks*; H2 › *History*; Report; preview.

**B, beginner: 26 · 5 · 4 · 2.**
1. Home: title, *Create project* → Project.
2. Q1 kind, text; *Add hypothesis*, H1, *Save plan version*.
3. Next step card *Open CSV / Excel…* ⟨Open dialog⟩ → Data; tick; *Use suggestions…*.
4. *Analysis desk*: *Correlations*; UCLA (2); *All quantitative (9)*; untick Age; *Spearman's ρ*; *Run*.
5. Inspector *Hypothesis*; *Tests hypothesis* H1 (2), shown as linked after the result.
6. *Assumptions*: 3 ticks.
7. *Report*: note, *Add to report*.
8. Reports: title, *Export Word report…* ⟨Save dialog⟩.

**B, professor: 12 · 0 · 4.**
1. *Open* → Project.
2. *Analysis desk*.
3. Plan row H1's task; inspector *Hypothesis*, *Assumptions*, *Provenance*.
4. Plan row H2's task; *Hypothesis*.
5. Project; *Plan history* (the designation change is a version note only).
6. Reports; preview.
