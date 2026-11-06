# Stage 34.5 release-readiness checklist

The status of every release gate in the Stage 34.5 request (issues #30, #31
and #32). Nothing has been merged: each pull request is a draft for review,
stacked in this order:

#33 → #34 → #35 → #36 / #37, with #38 on top of #33.

A signed installer comes after these gates pass on the distributed
application.

**Status:** done · open (work remains) · later (by request).

## Release gates

| Gate | Status | Evidence |
|---|---|---|
| Reported failures reproduced before fixing; each root cause and the test that failed before the fix recorded | done | `docs/STAGE345_FINDINGS.md`: 12 root causes (#33). On `c840571`, 25 tests failed (19 failures, 9 errors) and 4 real-browser checks failed; all pass now. Root cause 13 was found by the packaged-EXE journeys (#36): selectable text was invisible to screen readers. 3 tests and 1 browser check fail before its fix |
| No full page rebuild after a checkbox or text input; scroll, focus, caret, item 60 of 120 and open sections kept | done | `tools/workspace_state_checks.py` in a real browser, in CI (job *workspace-screenshots*); `StableRenderTests` |
| Windows save dialogs: TXT, PNG, DOCX, CSV and SRA actually written | done (Python + browser) · open (packaged EXE) | `SaveOutcomeTests`, `tests/test_workspace_files.py` (#33); native dialogs on the EXE: `tools/windows_gui_e2e.py` (#36) |
| Project creation and opening lead to the project workspace | done | `ProjectWorkspaceTests`, `ProjectPageTests` (#33) |
| Datasets, drafts, published forms, responses and derived datasets kept apart; Analyze Responses never replaces a source silently | done | `DataSourceTests` (#33); the responses journey (#36) |
| PSQ-like import: the bibliography never becomes items; image pages are read by OCR; the stated item count is checked | done | `tests/test_import_integrity.py` (19 tests, #34). Private PDFs were compared locally only, never committed: PSQ 2 → 30 items, Holmes–Rahe 0 → 43, PSS/UCLA/F2 unchanged |
| Legacy DOC and unsupported formats explained and actionable; imports never mix with an unsaved draft | done | `UnreadableDocumentTests`, `DraftGuardTests` (#33); wizard tests (#35) |
| Raw technical identifiers replaced by localized explanations | done | `MessageTests` (#33); RU facts in `tests/test_workspace_import_wizard.py` (#35) |
| Linux CI: full unit suite with real local OCR (ENG/LAV/RUS) | done | *Python tests / unittest* — green on every Stage 34.5 head |
| Windows CI: workspace, SQLite, research journey | done | *windows-sqlite*, *windows-research-journey* — green |
| Bundled OCR regression on Windows | done | *windows-ocr-bundle*: real OCR regression against the bundled engine, then the OCR self-test inside the packaged application |
| Project migrations (format 2, atomic writes) | done | `tests/test_project_store.py` on Linux and Windows |
| Real GUI E2E on the packaged Windows EXE (UI Automation, native dialogs, restart) | open | #36, workflow *Windows packaged GUI journeys*, artifact `windows-gui-e2e` (screenshots, one GIF per journey, `gui-e2e-result.json`) |
| Numerical parity with the validated engine | done | `tests/test_analysis_runs.py` (workspace = classic) and `tests/test_engine_ground_truth.py` (33 tests against independent references, #38). No discrepancies found |
| Synthetic fixtures only; no private questionnaires or participant data | done | `tests/synthetic_documents.py`, `examples/`; private PDFs never committed |
| Classic interface kept until the new one is equivalent | done | unchanged; reachable from the workspace sidebar |
| Screenshots at 100/125/150 %, light/dark, EN/LV/RU | done | artifact `workspace-screenshots` |
| Signed Windows installer | later | by request, after the GUI journeys pass |

## Packaged-EXE journeys (#36)

| Journey | What it does on the real executable |
|---|---|
| project-a | Creates a project and opens `sample_ancova.csv` in the Windows Open dialog. Confirms the levels and runs ANCOVA. Checks that the provenance names the dataset and its rows. Saves TXT, PNG and Word (Word typed without an extension), then the combined report and an `.sra` backup. Restarts the application, reopens the project and saves Word again. Each saved file is opened and checked; the report text must equal the validated engine's on the same data. |
| project-b | Creates a second project with other data and switches A ↔ B: each project shows only its own data and results. |
| import-30 | Imports a 30-item questionnaire with a bibliography and a shared response matrix, reviews it in the wizard and creates the draft. |
| review-120 | Imports a 120-item form and selects items 60, 61 and 95: the page does not jump, and typing keeps the focus and every character. |
| responses | Publishes a questionnaire and collects responses in its form. Exports CSV plus the JSON codebook, analyzes the responses as an explicitly named dataset, then returns to the original dataset. |
| blocked-design | In guided "Compare groups", picks a quantitative group variable. The design is refused in words, with no raw identifier and no run button. Choosing a categorical group lifts the refusal. |

## Priority 2 (#32)

| Item | Status | Evidence |
|---|---|---|
| Research journey with the next action in context | done | `JOURNEY` strip, project and data next steps (#37); `tests/test_workspace_journey_strip.py` |
| Guided ANCOVA design next to expert access to all 15 methods | done | `tests/test_workspace_guided_design.py`; no method is chosen from a Shapiro–Wilk p |
| Interpretation at student and professor depth; unverified decisions labelled | done | `result-depth`, `result-unverified` (#37) |
| Result provenance: source hash, N/missingness, coding, options, export settings | done | `tests/test_workspace_provenance.py` (#37) |
| Scientific Import layout: sticky actions, counts, progress, large source view, focused editing | done | #35 wizard; browser check *import-120-item-60* |
| Pointer cursors, hover and focus states, tooltips | done | browser checks *results-pointer-affordances* and *import-pointer-affordances* (#37) |
| Accent presets (blue default), light/dark, WCAG AA contrast | done | `tests/test_workspace_accents.py` (#37) |
