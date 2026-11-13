# Stage 36.8 — Accessibility and localization

Issue #62, P1: the import wizard's step-2 discrepancy, keyboard-only use, focus, Narrator, status announcements, display scales, compact windows, and the RU/LV texts.

## 1. The import wizard's disabled step, and why UI Automation reported it as enabled

**Finding.** Before a form was chosen, the step-2 button was disabled in the program (`disabled=True`, harness tests), but UI Automation reported it as enabled (`step_2_enabled_before_choice: true`, Stage 36 runs).

**Cause, measured.** This is not specific to the step. Flutter's Windows accessibility bridge (Flutter 3.47.9) reports every button as enabled.
- The 37 UI Automation trees the Stage 36 Windows runs saved hold about 4,800 elements, and not one is reported as disabled (`IsEnabled = false`).
- Several buttons were disabled in those states: Run before its confirmations, Next before a choice, the locked steps.

Flet maps `disabled` correctly (`onPressed: null`, flet 1.1.2 `controls/button.dart`). The state is lost between Flutter's semantics tree and UI Automation. Narrator reads UI Automation, so it would announce such a button as available.

**Fix (dff65c8).**
- A step that cannot open yet is no longer a disabled button. It is text with a lock icon (`wc.locked_step`): no keyboard focus, nothing to invoke, read by Narrator as text.
- The reason "Choose the form to review first (step 1)." is shown once below the steps.
- The sticky footer shows Back only after the first step, and Next only when the next step can open. Its caption says what to do first.

**Verified on Windows.** Run 43418623163, packaged program, journey `import-cope-docx`: before the choice there is no step-2 button in the UI Automation tree (`step_2_button_before_choice: false`), and the reason text is shown. All 13 journeys passed in that run. Harness: locked steps are not buttons and cannot be clicked, and there is no Next or Back before the choice (`tests/test_stage36_import_ui.py`).

**A disabled action never executes.** In Flet a disabled button has no `onPressed`, so there is no tap action in the semantics tree, and UI Automation's Invoke does nothing. The handlers check the state again (`ImportPage._go` refuses a locked step). A locked step now has no handler at all.

**Remaining platform limitation (documented, not fixed here).** Other buttons that are disabled while their reason is shown next to them are still reported as enabled by UI Automation. Examples: Run before its confirmations, and "Create draft" before the review is complete. Their reasons are visible text right beside them (Stage 34.5 D4/D9/D5 refusals), and invoking them does nothing. This should be reported upstream to Flutter (Windows accessibility bridge: disabled state not exposed). Replacing every disabled button with text would change many screens and the GUI journeys' selectors, so it was not done for this RC.

## 2. Keyboard

| What | Where verified |
|---|---|
| Ctrl+1 … Ctrl+6 pages, Ctrl+B sidebar, Ctrl+O open data, Ctrl+Shift+L theme, Ctrl+Enter run (Analyze), F1 help | harness `tests/test_workspace_shell.py::test_keyboard_shortcuts` |
| The import wizard's keys on the items step: F8 / Shift+F8, F9, Alt+↓ / Alt+↑ (never plain text keys) | `tests/test_workspace_import_wizard.py`, browser check `import-120-next-item` |
| Focus and typed characters kept while editing a 120-item review | GUI journey `review-120` (Windows), browser checks `questionnaire-120-item-60`, `import-120-item-60` |
| Locked wizard steps take no focus | by construction (text, not a control) |

Not verified: a **keyboard-only** walk of a whole journey on the packaged program. Tab order and the focus highlight on Windows were not checked by a test. The GUI journeys use mouse clicks and UI Automation Invoke. This remains an open P1 item for the RC.

## 3. Narrator and announcements

- Status line: an `ft.Semantics(live_region=True)` around the status text (`workspace_shell.py`). Every outcome (saved, refused, read N items) is written there. The browser check `data-status-announced` asserts that confirming the suggested measurement levels is announced ("levels confirmed from suggestions") through the accessibility tree.
- Import processing status (reading page X of N, candidates found, items needing attention): a live region in `workspace_questionnaires.py`.
- **Not verified with Narrator.** Speech cannot be asserted on CI runners, and no person has run Narrator against this build. The journeys verify what Narrator reads: UI Automation names, roles and text.

## 4. Display scales and compact windows

| Scale | Result | Evidence |
|---|---|---|
| 100 %, 125 %, 150 % | window DPI 96/120/144 as expected; Home shows "Create project"; all 7 sidebar items; nothing clipped | runs 43418623308 (dff65c8) and 43421786800 (216353d), packaged program on Windows |
| 175 % | window DPI 168 as expected; Home shows "Create project"; all 7 sidebar items; nothing clipped | run 43425712379 (48a09e8), packaged program; screenshot `home-175.png` in its artifact |
| Browser rendering at 100/125/150 %, light/dark, EN/LV/RU | no blank pages or Flutter error placeholders | Python tests, job `workspace-screenshots` |

At 175 % on 1920×1080 the program has 1097×617 logical pixels. That is the compact-window case.

## 5. Nothing lost while working

The Stage 34.5 checks still run on every commit. Each fails if a click or keystroke rebuilds the page.

| Browser state check (Flet 1.1.2 web client since Stage 36.8) | Checks |
|---|---|
| results-scroll-then-check | the scroll position survives ticking a confirmation |
| reports-type-title | the typed report title survives a re-render |
| questionnaire-120-item-60, import-120-item-60, import-120-next-item | item 60 of 120 stays in place; typed text kept |
| results-section-stays-open | an opened section stays open |
| results-add-report-twice | a button that changes kind is patched, not replaced |

Review finding K2 found that the researcher's notes, review ticks and report settings were not saved across a restart. That is persistence, not rendering. It is being fixed on this branch; see `docs/STAGE368_RELEASE_CHECKLIST.md`.

## 6. Russian and Latvian texts

Summary of `docs/STAGE368_LOCALE_REVIEW.md`: the automated audit and the review list for native speakers.

**No native-speaker review has taken place.** The review list is the input for one. "Language review passed" stays **not yet** in `docs/STAGE368_REAL_USER_ACCEPTANCE.md`.

`tools/locale_audit.py` checks every EN/LV/RU text table (2,034 texts in 20 tables) and the workspace screens. The same version of the checker was run on dff65c8 and after the fixes:

| Finding | Before | After | Notes |
|---|---:|---:|---|
| Missing translation or key | 11 | **0** | the 11 method choices of the guided analysis showed English in LV/RU |
| LV/RU identical to English | 0 | 0 | |
| Placeholder mismatch | 0 | **0** | also enforced by a unit test |
| English written directly in a workspace screen | 49 | **2** | import options, sample datasets, questionnaire templates and operators, "Table N", page-failure title, path field; the 2 left are in `workspace_analyze.py` |
| Style (spaces, mixed scripts, diacritics) | 10 | 10 | in the classic interface's table; review input |
| Long button or step label (layout risk) | 17 | 17 | review input; the display-scale check (§4) covers Home and the sidebar only, not these labels |

`tests/test_locale_audit.py` keeps "missing" and "placeholder" at zero. The Word report now writes the assumption checks in the report's language.

For the native-speaker review, the document lists by priority screen:
- every text added in Stage 36.8 (51 keys, 11 method names);
- terminology conflicts, for example RU «пункт»/«вопрос» for an item, LV «ticamība»/«uzticamība» for reliability, LV «lapa»/«lappuse» for a page;
- about 20 texts with the wrong noun form after a number;
- the English that the engine and the report builder still generate: batch tables, family warnings, Methods and Notes, Chart Studio texts, import diagnostics.

Not translated, and why: the data-preparation panel (`preparation_ui.py`). Its item check boxes are also column names, so running them through the translator would break scale scoring. That needs a separate fix.
