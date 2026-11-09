# Stage 36 — packaged Windows EXE end-to-end results

Spec §14 Level 4: the distributed Windows program, driven through Windows UI
Automation with real mouse clicks and key presses, the native Open and Save
dialogs and real restarts. Nothing is mocked. Files are chosen in the
system dialogs, written by the program and then opened and checked by the
driver. Numbers in exported reports are compared with the validated engine
run on the same data. Synthetic data only (`tests/fixtures/stage36`); the
owner's private materials were never used in CI.

## Final runs

The whole stack is the head of #61 (`claude/stage36-acceptance`, d6418e6),
which contains #52–#60; the commits after it change documentation only.
Its last runs:

| Workflow | What it runs | Run | Result |
|---|---|---|---|
| `windows-gui-e2e.yml` | the 13 journeys below on the portable build | 42686880526 | green: all 13 journeys, 902 s |
| `windows-installer.yml` | per-user setup on a clean runner: legacy migration, installed data, every journey on the installed program, B over A, uninstall keeps the data, reinstall finds the projects | 42686880239 | green: the 13 journeys on the installed program; `legacy-migration`, `installed-data`; `installed-reopen` after the upgrade and after the reinstall; both projects and the questionnaire kept after the upgrade and after the uninstall |
| `windows-update-e2e.yml` | installs A; installed data; refused updates (another signer, an older version, a damaged download); A → B from inside the program, then the project opens in B and eight correlations run in one batch | 42686880135 | green |
| `windows-package.yml` | the bundled OCR runtime self-test, packaged startup, the packaged analysis self-test, the size budget | 42686880304 | green |
| `windows-native-dpi.yml` | Windows display scale 100/125/150 % (not browser zoom) | 42686880540 | green |
| `python-tests.yml` | the Linux suite (1105 tests on this head), browser state checks (EN/LV/RU, light/dark, compact widths, pointer, focus), SQLite and the research journey on Windows | 42686880646 | green (one browser check, `reports-type-title`, crashed once in headless Chromium with "Page crashed" and passed when the job was re-run) |

Each run's artifact holds the evidence: a screenshot per step, an animated
recording per journey (`<journey>.gif`), the UI Automation tree whenever
something is missing, the program's own logs, the files it wrote and
`gui-e2e-result.json` (verdict, steps with seconds, facts, window guard).
The installer and update workflows keep the same per journey under
`windows-installer-evidence` and `windows-update-e2e`.

Earlier runs that the final runs repeat:

| Head | Runs | What they showed |
|---|---|---|
| #56 a6e2491 | GUI 42685352772, installer 42685352757, update 42685352768, package 42685352754, DPI 42685352638, Python 42685352889: all green | `import-scan-lv` on the packaged program: 52 candidates, one legend scale, a draft of exactly 52 (D8 on Windows fixed) |
| #61 7f5e5a9 | GUI 42682182804, installer 42682182853 | every journey green except `import-scan-lv`, whose fixture generator overflowed on Windows (fixed in a6e2491) |
| #61 7f5e5a9 | update 42682183161, package 42682182745, DPI 42682182981, Python 42682182727: green | A → B, then the project opens in B and eight correlations run in one batch |

A journey passes only when every step passes. A step waits for what a
researcher would see (a text, a button name) and fails with the screen's
UI Automation tree if it never appears.

## Spec §14 journeys on the packaged EXE

| Spec | Journey | Steps checked |
|---|---|---|
| 1 | `stage36-tasks` | create a project; open the synthetic CSV in the Windows Open dialog; the participant code is suggested as identifier; UCLA with eight scales in one batch (goal, UCLA, all scales, Spearman, Run); one table with eight pairs, N, interval, raw and Holm p |
| 2 | `stage36-tasks` | back to the task and run it again in two actions |
| 3 | `stage36-groups`, `stage36-charts` | the existing UCLA_Level offered for UCLA; three quantile groups previewed and created; the eight scales by the new groups in one Kruskal–Wallis batch; the same by UCLA_Level with the small groups explained before Run |
| 4 | `stage36-charts` | Chart Studio from the task; violin, then multi-boxplot panels; the title typed; the Windows clipboard holds a bitmap of the announced size; PNG and SVG saved and checked; the view chosen for the report; restart brings the view back |
| 5 | `import-cope-docx` | a Word document with two unnumbered 60-item table forms: both shown, none chosen for the researcher; the situational form reviewed with its own options; 60 items; a draft of exactly 60 |
| 6 | `import-scan-lv` | a scanned Latvian 52-item table: the scan detected, local OCR offered with its language; read in Latvian; 52 candidates; the legend offered as one documented scale; a draft of exactly 52 |
| 7 | `review-120` | a 120-item form: selecting items 60, 61 and 95 keeps the list in place; editing item 95 keeps the focus and every typed character |
| 8 | `stage36-report`, `project-a` | the Kruskal–Wallis batch and a description of UCLA in one Word report: both results, the Descriptive statistics and Hypothesis tests sections, Tables 1 and 2, the reproducibility appendix and the dataset; `project-a`: ANCOVA, TXT/PNG/Word, combined report, backup, restart |
| 9 | `stage36-tasks`, `stage36-charts`, `project-a` | restart: the task and its result, the chart view, the project and its result come back |
| 10 | `blocked-design`, `stage36-report`, `import-damaged`, `update-refusals` | a quantitative group variable refused in words; no reliability coefficient (no Run button) for totals; a damaged PDF refused with its reason while the review under way is kept; another signer, an older version and a damaged download refused by the updater |
| packaging | `update-a-to-b` | A → B from inside the program, then the project opens in B and eight correlations run in one batch |

Earlier journeys stay in the set: `project-b`, `import-30`, `responses`
(Stage 34.5/35) and, in the installer workflow, `legacy-migration`,
`installed-data`, `installed-reopen`.

## Measured on the packaged program

From the journeys' facts (`gui-e2e-result.json`; 42686880526 unless stated):

| Fact | Value |
|---|---|
| Spearman ρ of UCLA with the 8 scales, the engine on the same file | −0.24, −0.10, −0.00, −0.33, −0.10, −0.08, −0.34, 0.08 (recorded; the journey checks the table's eight scales and its Holm column, not the printed values) |
| Chart copied to the clipboard | a bitmap of 1380 × 1313 px; PNG 1380 × 1313 (183 KB), SVG 231 KB, both reopened |
| Quantile groups of UCLA | the engine's 19, 18 and 18 participants are the sizes the program announces after Create |
| 120-item form | items 60, 61 and 95 moved 0 px when selected; the focus stays in the edit field; the typed text ends exactly as typed |
| Word report of two results (`stage36_report.docx`) | 128 KB, 99 paragraphs; checked for both results, both sections, Tables 1 and 2 and the appendix |
| Latvian table scan | 52 candidates, 17 marked for attention, one legend scale, a draft of 52 (the same in run 42685352772 on #56 and on the installed program, run 42686880239) |
| The same table in a Times-like font (STIX), the program's code with the bundled engine, outside the program | 52 items numbered 1–52, 5.0 s for both pages |
| Bundled Tesseract alone, both pages, before rule removal | 6.5 s and 5.3 s (581 and 505 words) |
| Local OCR in the program, from the click to the result | 39.5 s in the portable build, 52.8 s in the installed program (76.8 s before the rules were whitened) |
| Window guard interventions | 0 in the final runs (it showed a hidden window once in each of runs 42658212347 and 42664741403) |

## UX before and after (measured)

The interaction counts come from `docs/STAGE36_UX_AUDIT.md`, measured in the
workspace harness with the same rules (a dropdown counts two, a typed field
one); the journeys above perform the same flows on the packaged program.

| Workflow | Before Stage 36 | After |
|---|---:|---:|
| Correlate UCLA with 8 scales | 43 interactions, 16 page changes, 8 separate results | 8 interactions, 1 page change, one table |
| Repeat an analysis | 5 | 2 |
| Compare 3 groups on 8 scales | refused after Run, 9 interactions spent | 8 interactions, small groups explained before Run |
| Create groups from a scale | not available | 4 |
| Change a chart type | not possible | 2, nothing re-run |
| Copy a chart | not possible | 1 (an image on the clipboard) |
| Word report from 8 results | 19 + Save dialog | 3 + Save dialog |
| Review an unnumbered 60-item Word form | blocked | 9 after the Open dialog |
| Import a scanned 52-item table | 16 of 52 found | 52 of 52; 12 interactions (10 in the Latvian interface) |

## Defects found by the packaged EXE and fixed

| Found by | Symptom | Cause | Fix |
|---|---|---|---|
| `stage36-charts` (first run) | the goal tiles were missing in a new project | a new project inherited the previous project's analysis selection and task | `ProjectHub.create()` resets the Analyze page; `reset()` clears the task (60c7cae, test `test_a_new_project_starts_a_new_analysis`) |
| installer run 42648266085; update journeys on #55 | the program started (its log says so) but its window stayed hidden for 300 s | the Flutter runner window was created, sized and centred but never shown | `window_guard.py` shows this process's own window if it is still hidden 3–30 s after start, and logs each intervention (df30954) |
| `import-scan-lv` (first run, 42656712671) | both pages of the Latvian scan stopped at the per-page OCR limit | the bundled Windows engine ran about 15 times slower than the Linux one; two spinning OpenMP threads | one OpenMP thread, a 180 s per-page safety limit, timing facts in the journey (ae2b417) |
| journey review | "I confirm that the two groups contain independent observations" for 3–8 groups | the batch comparison used the two-group label | the k-group label (6bae97b) |
| `stage36-groups` (run 42658249711) | the wrong scale was grouped | the groups card preselected the first quantitative variable (Age), a hidden default that UI Automation cannot even read | no preselection: the card asks for the score first, in EN/LV/RU (63821de) |
| `import-scan-lv` (installer run 42669384359) | 45 of 52 items from the Latvian table | the Windows runner drew the fixture in Times New Roman; in that typeface the table rules made Tesseract drop text lines, a legend line read as `4 bieži` tilted the statement column, and lone top digits were misread | rules whitened before OCR, a Theil–Sen column, top rows numbered back and flagged, fixture fonts from matplotlib and a STIX variant (e725120) |
| `import-scan-lv` (GUI run 42680523635) | "item 26 does not fit on page 1" in the fixture generator | Pillow sets text with libraqm on Linux but cannot on Windows, about 1 % wider | Pillow's basic layout on every platform, answer digits 20 px further right (a6e2491) |

Journey-side fixes (the program was right):

- **stage36-tasks** — a chip's accessible name is "label. tooltip".
- **stage36-tasks** — the Variables step shows the dictionary.
- **stage36-charts** — the small-group explanation needs the outcomes too.
- **stage36-groups** — Windows exposes a preview row as one element, so no element is named "18"; the group sizes are read from the announcement after Create (3285a60).
- **project-a** — the combined Word report is one document in numbered sections.
- **workspace-screenshots** — the browser reports scenario now confirms what the scale recommendation asks for.

## Not verified on the packaged EXE

- The owner's real documents and data (the scanned SACS-LV form, the COPE Word form, the 55-participant dataset) are never used in CI. They were checked only locally, counts only (`STAGE36_IMPORT_VALIDATION.md`, `STAGE36_STATISTICAL_VALIDATION.md`).
- The AI assistant panel has no packaged-EXE journey (no provider is called in CI).
- Display scales above 175 % (the runner's limit), multiple monitors and right-to-left layouts.
- Keyboard-only use of the whole program on the EXE. The browser checks and the review wizard's keys (F8/F9, Alt+arrows) are tested, but there is no EXE keyboard-only journey.
- Local OCR in the program takes 40–53 s for the two table pages on the CI runner, while the bundled engine needs about 12 s for them (6.5 + 5.3 s) and the program's own processing takes about 5 s here. The rest lies in the interface or in the UI Automation driver that polls it; it was not profiled.
- UI Automation reports the import wizard's step-2 button as enabled before a form is chosen (`step_2_enabled_before_choice`), although the program disables it (harness test). A screen reader may announce it as available; its tooltip explains why it does nothing. Not checked with Narrator.
