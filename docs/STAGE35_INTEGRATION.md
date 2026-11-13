# Stage 35.0 — integration report (#39)

One branch, `claude/stage35-integration` (PR #47), contains every open pull
request of Stages 32–34.5. The combined application was tested on **one
SHA, `a3dc4f9`**:
- the full Linux suite;
- the Windows CI jobs;
- the packaged executable with its OCR and analysis self-tests;
- the six researcher journeys on that executable.

Green CI on the separate branches was not taken as evidence for the combination: the combined branch did fail one check that every branch passed alone (see below).

Nothing is merged into `main`.

## Ancestry and merge order

The main stack is linear: each pull request is based on the previous one.

```
main ─ #15 ─┬─ #21 ─┬─ #26 ─ #27 ─ #28 ─ #29 ─┬─ #33 ─┬─ #35 ─┬─ #36
            │       │                         │       │       └─ #37
            │       │                         │       └─ #38
            │       │                         └─ #34 (merged into #35)
            │       └─ #25
            └─ #22
```

The integration branch starts from #36 (`71d8a32`), which already contains
#15, #21, #26–#29 and #33–#35. It then merges the four branches #36 does not
contain, in this order:

1. #37 (`9241e0e`)
2. #38 (`33f8f9d`)
3. #25 (`1d72092`)
4. #22 (`ff48948`)

## Inclusion matrix

| PR | Branch | Head | Own commits | Included | How | Conflicts |
|---|---|---|---:|---|---|---|
| #15 Stage 32: spatial OCR, matrices, bundled Windows OCR | `claude/eager-cerf-d4cnd3` | `6016af9` | 23 | yes | ancestor of #36 | — |
| #21 Stage 33: research workspace prototype | `claude/stage33-research-workspace` | `266f401` | 3 | yes | ancestor of #36 | — |
| #22 Issue #20: Brief COPE-style import | `claude/issue20-brief-cope` | `ff48948` | 14 | yes | merged (`a4a0f2f`) | 4 files, both sides kept (below) |
| #25 Stage 34: measured package cleanup, single-ZIP download | `claude/stage34-distribution` | `1d72092` | 5 | yes | merged (`7a83351`) | none |
| #26 Stage 34: local-first projects | `claude/stage34-projects` | `165aa59` | 2 | yes | ancestor of #36 | — |
| #27 Stage 34: Project Hub, autosave, stale results | `claude/stage34-project-hub` | `8764d37` | 3 | yes | ancestor of #36 | — |
| #28 Stage 34: researcher profile, project-scoped AI permissions | `claude/stage34-profile` | `d9f081f` | 1 | yes | ancestor of #36 | — |
| #29 Stage 34 UX increment | `claude/stage34-ux-results` | `c840571` | 2 | yes | ancestor of #36 | — |
| #33 Stage 34.5: stabilised Windows workspace journeys | `claude/stage345-p0` | `2ab2f1f` | 3 | yes | ancestor of #36 | — |
| #34 Stage 34.5: bibliography and image-page import integrity | `claude/stage345-import-integrity` | `c835a9e` | 5 | yes | ancestor of #36 (via #35) | — |
| #35 Stage 34.5: scientific import review wizard | `claude/stage345-import-ui` | `c0cb88f` | 5 | yes | ancestor of #36 | — |
| #36 Stage 34.5: GUI journeys on the packaged EXE | `claude/stage345-e2e` | `71d8a32` | 22 | yes | base of the integration branch | — |
| #37 Stage 34.5: research journey, guided design, provenance | `claude/stage345-journey` | `9241e0e` | 3 | yes | merged (`1d154ba`) | browser checks, both sides kept |
| #38 Stage 34.5: engine ground truth (33 tests) | `claude/stage345-parity` | `33f8f9d` | 1 | yes | merged (`6535098`) | none |

Nothing was excluded. Every commit of every pull request is listed in the appendix.

### #22 (Brief COPE) — included

#22 branched from #15 and never saw the import-integrity work of #34. Both
change the scientific importer:
- #34 keeps bibliographies out of items, reads image-only pages by OCR and checks the stated item count;
- #22 adds letter-spacing repair, answer choices repeated after every item and scoring evidence.

They conflicted in four files. Every conflict was resolved by keeping both sides.

| File | Resolution |
|---|---|
| `scientific_survey_import.py` | the review keeps the bibliography lines left out, the stated item count and the OCR language (#34), and the spacing repairs and repeated-choice layout (#22) |
| `visual_survey_review.py` | the OCR path applies #22's spacing repairs and still reports #34's reason why no numbered item was found |
| `tests/synthetic_documents.py` | both synthetic families: the strain questionnaire with references, and the coping inventory |
| `tools/check_packaged_ocr.py` | the packaged-module check lists the modules of both |

The Brief COPE suite (28 tests) and the import-integrity suite (19 tests)
both pass with real local OCR, as does the rest of the importer suite.

### #25 (packaging) — included

#25 merged without conflicts. It brings:
- package test suites, build-only files and the Pillow AVIF codec left out of the bundle;
- pingouin imported on first use;
- the analysis self-test inside the packaged application, whose report hashes must equal the source checkout's;
- the size budget: installed ≤ 400 MiB, ZIP ≤ 160 MiB.

The `pruned-runtime` job reruns the whole suite on an environment pruned exactly like the bundle.

## Findings of the integration

1. **A check that passed on every branch alone failed on the combination** (`ea29526`).
   - **What happened:** the scan for buttons that hand Flet a coroutine (#33) matched names across all modules. So `analysis_selftest._sample` (#25, a plain function) was reported because `WorkspaceShell._sample` (#33) is async. So were `runs.run_explore()` and others, because the classic window nests async closures of those names.
   - **Fix:** a bare name now resolves to a coroutine of the same module, or one imported by name; an attribute call resolves to a coroutine method or module-level coroutine.
   - **Verified:** the scan has its own test. Run on `c840571`, before the #30 fix, it still reports all 12 dropped handlers.
2. **Downgrade safety: an older version wrote to a project saved by a newer one** (`a3dc4f9`).
   - **What happened:** opening such a project switched its database to WAL before the version check refused it. So running an older version after an update, or after a failed one, changed a database it cannot read.
   - **Fix:** the format is now read through a read-only connection and refused without any write.
   - **Tests:** a new test fails before the change (the header bytes are rewritten) and passes after. A second new test shows that a project in the current format reopens after an update without a backup copy. Existing tests already cover: backup before a schema change, a failed migration that leaves the old format untouched, and a refused newer format.

## Verification on `a3dc4f9`

| Check | Result |
|---|---|
| Full Linux suite with real local OCR (ENG/LAV/RUS), this machine | 647 tests OK |
| *Python tests* (Linux unit tests with real OCR, pruned runtime, Windows SQLite, Windows research journey, Windows OCR bundle), run 42309305044 | success |
| *Windows desktop bundle* (build, packaged OCR self-test, packaged analysis self-test against the source report hashes, GUI start, size budget), run 42309305164 | success |
| *Windows packaged GUI journeys*: project-a, project-b, import-30, review-120, responses, blocked-design on the packaged executable, run 42309305349 | all 6 journeys pass |
| *Windows packaging experiments* (same-runner size and start-up), run 42309305064 | success |

Native Windows display scaling of 125 % and 150 % is still covered only by
browser screenshots at device scale 1.25/1.5. That is not native DPI
testing; it is tracked in #46.

## What the program writes where

The integration branch itself writes research data where Stage 34 put it.
The installer branch (#48, stacked on this one) moves every packaged
build's data to `%LOCALAPPDATA%\StatisticalResearchAssistant`. It also checks on a real
Windows runner:
- that the installed program writes nothing into the program folder;
- that the installer writes only to the program folder, the Start menu and its own registration.

## How to merge (owner's choice)

- **Either** merge the stack in order (#15 → #21 → … → #36), then #47.
- **Or** merge #47 alone into `main` (it contains everything) and close the others as superseded.

In both cases, the installer (#48) and updates PRs follow on top.

## Appendix: commits of every pull request

**#15** (`eager-cerf-d4cnd3`)

- `09c7734` Add typed spatial OCR models, TSV parsing and region linkage
- `390acef` Add bounded local Tesseract resolver with bundle verification
- `cc32d88` Reconstruct editable questionnaire matrices from DOCX, PDF and OCR
- `744373f` Use spatial Tesseract TSV and PDF text geometry in visual review
- `ff0042b` Bundle a pinned offline Tesseract 5 runtime in the Windows build
- `5520a9e` Add split-screen spatial review and matrix editor to the importer
- `f084fbc` Render synthetic OCR fixtures with matplotlib's DejaVu Sans on all OSes
- `d5708c0` Show offline OCR engine readiness under Settings and Help
- `c600c3f` Report per-language OCR output in the multilingual real-engine test
- `2e2e057` Offer main-language-first OCR combinations for Latvian and Russian
- `2168e1e` Document Stage 32 spatial review, matrices and bundled Windows OCR
- `0e817b4` Record CI-verified packaged Windows OCR in the roadmap
- `a9c429a` Keep matrix grid edits across view refreshes; never reuse scoring approvals
- `80916a1` Show a startup screen immediately and log startup timings
- `4fc1e84` Recognize True/False, T/F and Yes/No answer formats on import
- `0b72905` Verify normal packaged GUI startup on Windows CI with screenshots
- `0016e72` Document fast startup, startup logs and True/False imports
- `7916a02` Model shared response scales and keep instrument versions separate
- `5d62619` Link matrices to questions and review a whole shared scale at once
- `a1b5f11` Run shared-scale tests on Windows and document scale review
- `608b7cd` Show the selected instrument version's own source page
- `891aab6` Repair 'L' misreads in OCR code rows; report OCR lines on scan failures
- `6016af9` Seed the ML starting values of every omega fit (statsmodels 0.15)

**#21** (`stage33-research-workspace`)

- `021349a` Stage 33: research workspace prototype on the validated engine
- `905a920` Stage 33: specification, screenshots, CI checks and parity details
- `8be92bd` Block imports until low-confidence items are compared with the source

**#22** (`issue20-brief-cope`)

- `9034a35` Add conservative letter-spacing repair for PDF text layers
- `907f3f5` Read answer blocks repeated after every item and documented scoring
- `e21cfa3` Import coping-inventory layouts as one shared scale with review gates
- `1cb4fe9` Reconstruct labelled answer-cell grids from page geometry and OCR
- `e402a92` Add synthetic coping-inventory fixtures and regression tests
- `4fb1242` Report questionnaire structure without source wording in the local audit
- `c24d8ad` Document repeated answer-choice imports and run their tests in CI
- `4165c2c` Prefer the spaced spelling of OCR-read answer labels
- `68df2db` Break ties in answer-label consensus deterministically
- `0a4d4de` Take labels of code-only repeated blocks from this instrument's legend
- `b890c69` Add a screenshot of the coping-inventory scale review (synthetic fixture)
- `0265775` Restore physical lines that pypdf 6.21 merges without whitespace
- `13b32f6` Report glyph-gap geometry when a spacing-repair test fails
- `1bd5f97` Make the coping fixture machine-independent; fix the defects it hid

**#25** (`stage34-distribution`)

- `470a47d` Measure the Windows package and drop files the app never uses
- `0c30f5a` Add the distribution report and a same-runner packaging experiment
- `600f86b` Record same-runner startup results; load pingouin on first use
- `4e3cb90` Find a window in the whole process tree and stop the whole tree
- `1d72092` Record the same-runner before/after startup and the flet pack result

**#26** (`stage34-projects`)

- `2559a82` Add a local-first project store with provenance, stale results and backups
- `165aa59` Keep loaded tables, their source file hash and the full run texts

**#27** (`stage34-project-hub`)

- `dd1ebe4` Keep the workspace in research projects: Home hub, autosave, stale results
- `3bfc9d2` Say on Home that a backup holds the project's data
- `8764d37` Give the screenshot capture time for slow CI frames, retry once

**#28** (`stage34-profile`)

- `9251eac` Add an optional local researcher profile and project-scoped AI permissions

**#29** (`stage34-ux-results`)

- `5fe7e76` Fold the chosen question, show the primary result first, preview reports
- `c840571` Read the import source page large, with page turning and zoom

**#33** (`stage345-p0`)

- `5a559dd` Stabilize the workspace for the reported Windows journeys (#30)
- `1d9ed1c` Keep buttons drawable when a re-render changes their kind
- `2ab2f1f` Make Save, Open and the other async buttons actually run (#30)

**#34** (`stage345-import-integrity`)

- `fbd69cc` Keep citations out of imported items and read image-only pages with OCR
- `4a9ef65` Do not read a scoring note's subset as the form's item count
- `5a559dd` Stabilize the workspace for the reported Windows journeys (#30)
- `1d9ed1c` Keep buttons drawable when a re-render changes their kind
- `2ab2f1f` Make Save, Open and the other async buttons actually run (#30)

**#35** (`stage345-import-ui`)

- `fbd69cc` Keep citations out of imported items and read image-only pages with OCR
- `4a9ef65` Do not read a scoring note's subset as the form's item count
- `96d2963` Review scientific imports in a wizard with a footer that stays on screen (#31)
- `daf9d7e` Edit the opened item like a person: scroll it into view, type at the end
- `ac9c704` Test the import wizard without an OCR engine; word OCR facts for any page count

**#36** (`stage345-e2e`)

- `dfd0d4e` Drive the packaged Windows application through real researcher journeys
- `2d68298` Fill the Windows file dialogs reliably and log what is on screen
- `e9fac5c` Choose dropdown entries by keyboard when the menu does not list them
- `03e6eb7` E2E: use only this application's dialogs, maximize the window, open the question list on narrow layouts
- `44cfa54` E2E: find the Open/Save dialog inside the application window
- `5717c49` E2E: read selectable text, scroll to messages, check a refused design
- `1ce70fe` E2E: open a project by its own Open button; match tiles by their title
- `78752ab` Give selectable text an accessible name; announce status changes
- `3bf7012` Add the Stage 34.5 release-readiness checklist
- `30d73dc` E2E: never type into the window's system menu; choose dropdown entries safely
- `3003ed3` Keep the next item under the pointer in the import review
- `6e2bc80` E2E: maximize once the app is ready, click clear of the footer, open dropdowns via UI Automation
- `399c95b` E2E: tick checkboxes on the box, keep typed spaces
- `1d59a42` E2E: keep only the footer and status line out of reach; pick wizard steps by their button
- `9f8eb20` E2E: match the run button as 'Run <method>' without a broken escape
- `10907c4` E2E: fill the response form in its own dialog; keep clicks clear of the context bar
- `b5214d9` E2E: recognize a save by its 'Saved:' line and file name, not one spelling of the folder
- `b71b5d6` E2E: open dropdowns through UI Automation first again; open the response form by Invoke if a click does not
- `ecc861a` E2E: find the response form by its 'Alert' dialog; check a typed-without-extension save under its real name
- `73e7adc` E2E: click a dialog's controls only where its scroll area shows them; match sidebar items with a count
- `24cc255` E2E: rate each question under its own heading; recognize a save by its file name
- `71d8a32` Release checklist: the packaged-EXE journeys pass; record the defects they found

**#37** (`stage345-journey`)

- `b4f1cab` Show the research journey, the design behind a method and what a result rests on (#32)
- `f74f0a8` Confirm measurement levels from what each column holds (#32)
- `e3d3ef5` Check pointer cursors and hover states in a real browser (#32)

**#38** (`stage345-parity`)

- `77cb30e` Add engine ground-truth tests against independent references (#32)

