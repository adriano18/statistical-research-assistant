# Stage 37 — design material (Phase D)

Issue #63, Phase D: interface design and the specification of the Stage 37.0 increment. This folder holds no product code; nothing here is part of the application or of the installer (`docs/` is excluded from the bundle).

| File | What it is |
|---|---|
| [`../STAGE37_DESIGN.md`](../STAGE37_DESIGN.md) | The design document. It covers two interface approaches (A, research protocol; B, analysis desk), the flows of a beginner and a professor with interaction counts, the hybrid decision, the Stage 37.0 specification (typed questions, H0/H1, designation, task–hypothesis link, step status, checks, deviations, next action), the additive data model, compatibility, acceptance criteria, regressions and open questions. |
| [`prototype.html`](prototype.html) | A clickable prototype of A, B and the hybrid. It is one self-contained HTML file, about 108 KB, with no external resources; open it in any browser, offline. |
| [`measure_baseline.py`](measure_baseline.py) | The measurement of today's flows at `55f94b1`. It uses the Stage 36 `CountingWorkspace`. Run it from the repository root: `python docs/stage37/measure_baseline.py`. |

## Using the prototype

- **Variant** switches between *A · Research protocol*, *B · Analysis desk* and *Hybrid (proposed)*. **Flow** switches between *Beginner* and *Professor*. Each switch restarts the flow.
- **The guide.** The bar under the prototype controls shows the next step of the flow. A dashed outline marks the control; *Show me* moves the focus to it, and *Skip step* skips it. *All steps of this flow* lists every step.
- **The counter** counts as `CountingWorkspace` does: a click or a checkbox 1, a dropdown 2. Typed fields (each field once), page changes and system dialogs are counted apart. Beside it is the count the design document reports for the flow.
- **Show the guide.** Untick it to hide the coaching for a moderated user test (design document §5.4); the counter keeps counting.
- **`prototype.html#selftest`** replays all six flows through the page's own handlers. The page title then ends in *[selftest: all flows ok]*, and the counts are printed on the page.
- **Keyboard.** Tab reaches every control; Enter or Space activates it; Escape closes a system dialog. The focus outline is always visible. In the title field, Enter creates the project, as in the app. Layouts reflow at 125 % and in narrow windows: the two panels and the desk stack. The page follows the system's light or dark setting.

**What is real.**
- The labels of existing controls come from the English interface (`workspace_text.py`).
- Names and numbers are the analysis engine's output on the invented fixture `synthetic_ucla_sacs_55.csv` at `55f94b1`, copied as text. There is no real data, and nothing is calculated, saved or sent.
- New 37.0 parts carry a dashed tag (`37.0`, `37.1`, `layout 37.4`) and use proposed labels.

**What it does not do.**
- Only the Spearman batch of UCLA × the 8 scales has numbers. Any other choice says that nothing is invented for it.
- It shows 12 of the 15 checks of the specification. `H-FAMILY-SPLIT`, `H-VARIABLES-DIFFER` and `H-SPEC-CHANGED` need more than one analysis per hypothesis or typed plan variables.
- Buttons outside the flows answer *Not part of this prototype*.
- Direction and designation are segmented buttons in the prototype; 37.0 keeps today's dropdowns so that their data keys stay stable (design document §7.3).

**How the counts were checked.** `#selftest`, and a headless-Chromium run that clicked the highlighted control at every step at 100 % and 125 % device scale. Both reproduce the counts of the design document for all six flows: the beginner flow is 19 in A, 26 in B and 20 in the hybrid; the professor flow is 8, 12 and 6.

## Open questions for the owner

Each is explained in §13 of the design document.

1. Accept project format F+1 (one additive table, a backup before migration, a copy for older versions)? Or should the release candidate first learn to open newer formats read-only?
2. Ship the copy for an older version in 37.0, or in 37.0.x?
3. Keep today's strict "added after results" rule (any result in the project), with the variable overlap shown and a justification allowed?
4. Add one-sided tests to the engines (37.2, with oracles), or keep two-sided tests with the direction check and an acknowledgement?
5. Pass the plan's α to the batch engines in 37.0, or in 37.2?
6. Use the vocabulary *Designation: Primary / Secondary / Exploratory*, or *Confirmatory / Exploratory* with primary/secondary as a second axis?
7. May the first result linked to a hypothesis be the reference for later changes when the plan has no typed variables or method?
8. Add the hypothesis lines (links, deviations) to the Word report in 37.0, or leave the report until 37.3?
9. Stack the 37.0 PR on the release-candidate branch after K1–K3, or wait for the merge to `main`?
10. Which version number for 37.0 previews, and should they go to the preview channel that 1.0.0-preview.1 users follow?
11. Who recruits the participants for the user test, and is a test on this prototype enough before 37.4?
12. Which key should focus the next action, if a shortcut is wanted?
13. Who reviews the new LV and RU texts?
14. One 37.0 PR in four commits, or 37.0a and 37.0b?
