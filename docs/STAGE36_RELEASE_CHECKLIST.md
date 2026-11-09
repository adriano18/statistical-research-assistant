# Stage 36 release-readiness checklist

Each gate of the Definition of Done (spec §17) and of the Stage 35
packaging regression (spec §14) has a status and the evidence behind it.
Nothing is merged into `main` and nothing is published. The pull requests
are drafts, stacked in this order:

#52 (spec) → #53 (36.0) → #54 (36.2) → #55 (36.1) → #56 (36.5) → #57 (36.4) → #58 (36.6 report) → #59 (36.3) → #60 (36.6 AI) → #61 (36.7)

**Status:** done · open (work remains) · owner (needs the owner's decision or secret).

Run IDs and the head SHA of each Windows run are in
[STAGE36_E2E_RESULTS.md](STAGE36_E2E_RESULTS.md).

## Definition of Done (spec §17)

| Gate | Status | Evidence |
|---|---|---|
| No known P0 defect in the main research workflows | done | D1–D10 of the 36.0 audit fixed, each with a reproduction that now passes (`tests/test_stage36_regressions.py`, no `expectedFailure` left on #59 and above). The packaged-EXE journeys found three more, all fixed: a new project inherited the previous project's analysis (60c7cae); the program's window could stay hidden after a complete start (window guard, df30954); the Latvian table scan gave 45 of 52 items on Windows (e725120, a6e2491; 52 of 52 on the packaged program in run 42685352772) |
| No dead buttons, silent refusals or lost input | done | the harness calls handlers exactly as Flet 1.x does (`workspace_harness.dispatch`); `test_no_lambda_hands_a_coroutine_to_flet`; refusals are explained before Run (D4, D9, D5); `review-120` and the 200-item tests keep focus and every typed character; the review wizard saves every change |
| The journey bar opens the right step | done | D1; EXE journey `stage36-tasks` step "each research step opens its own step (D1)", found without the driver scrolling |
| Batch analysis of several scales | done | `batch_correlation`, `batch_groups`; EXE journeys `stage36-tasks` (8 correlations), `stage36-charts` and `stage36-groups` (Kruskal–Wallis for 8 scales) |
| Results hold real structured numbers | done | D2; `runs.structured` (project format 4); restored after a restart without recalculation (`stage36-tasks` restart step) |
| Intervals and effect sizes correct, with their method | done | `STAGE36_STATISTICAL_VALIDATION.md` (independent oracles and tolerances); the private acceptance check reproduces the thesis to 3 decimals (counts only) |
| Significance never presented as proof of an effect or of no effect | done | interpretation and report wording tests; the AI rules (never "proven", non-significance is not equivalence) |
| No fictitious reliability from aggregated data | done | D5: the guided advice offers no coefficient for totals; among all methods only after an explicit, recorded confirmation; EXE journey `stage36-report` checks that totals get no Run button |
| Charts can be changed, copied and exported | done | Chart Studio (36.4); EXE journey `stage36-charts`: type and layout changed without re-running, the Windows clipboard holds a bitmap of the announced size, PNG and SVG saved and checked |
| COPE and SACS pass the structural check | done (synthetic) · local (private) | EXE journeys `import-cope-docx` (60 of the chosen form) and `import-scan-lv` (52 from a Latvian scan); the same table in a Times-like font gives 52 with the bundled engine; the owner's real SACS-LV scan gives 52 of 52 locally in `lav`, `lav+rus+eng` and `eng` (counts only, never in CI) |
| Long questionnaires edited without jumps or focus loss | done | EXE journey `review-120`; 200-item paging tests (13–24 ms per build) |
| Tasks, results and settings survive a restart | done | `stage36-tasks` (task and result), `stage36-charts` (the chart view), groups and their history (harness restart test) |
| One correct Word document from several results | done | `research_report.py`, `report_docx.py`; EXE journeys `project-a` and `stage36-report` (two results, numbered sections, tables, appendix) |
| Stage 34.5 / 35 functions do not regress | done | the full suite (all earlier tests kept); the Stage 34.5/35 journeys (`project-a`, `project-b`, `import-30`, `review-120`, `responses`, `blocked-design`) in every GUI run; the installer and update workflows below |
| All unit, integration and browser tests green | done | Linux `unittest`: 1105 tests OK on #61 (7 skipped); browser `workspace-screenshots` (EN/LV/RU, light/dark, compact widths, pointer and focus checks); see the final `python-tests` run |
| All key packaged-Windows-EXE journeys green | done | on the whole stack (#61, d6418e6): GUI run 42686880526 (13 of 13 journeys) and installer run 42686880239 (the 13 journeys on the installed program, plus migration, installed data, upgrade and reinstall); update run 42686880135 |
| UX before/after documented | done | `STAGE36_UX_AUDIT.md` (measured interaction counts), summarised in `STAGE36_E2E_RESULTS.md` |
| Limitations stated honestly | done | the limitation sections of every Stage 36 document and of the final report |

## Distribution and updates (Stage 35, spec §14 packaging regression)

| Gate | Status | Evidence |
|---|---|---|
| The installed program needs no Python on the user's computer | done | the installer workflow installs and runs the packaged program on a clean runner |
| Update from inside the program, with "What's new" | done | journey `update-a-to-b`: announced at start, What's new, interrupted download retried, **Update now**, restart as B |
| Data kept by an update; installing over an older version | done | `update-a-to-b`: "All 1 projects are in place", `projects_kept: 1`; installer workflow: B over A, both projects open |
| No manual download of archives for ordinary updates | done | the in-app update downloads, verifies (Ed25519 manifest, SHA-256) and installs |
| A failed or cancelled update destroys no project | done | `update-refusals`: another signer, an older version and a damaged download are refused, nothing is started; a backup is made before installing |
| A → B → open the project → use the new functionality | done | `update-a-to-b` opens the synthetic data in the updated program and runs eight correlations in one batch (run 42682183161 on #61 7f5e5a9, and the final update run) |
| The program's window always appears | done | `window_guard.py`: shows this process's own window if it is still hidden 3–30 s after start; the E2E report lists every intervention (0 in the final runs) |
| Code-signature decisions | done | `tools/check_code_signature.py` on Windows: untrusted, wrong publisher, tampered and unsigned cases refused as designed |
| The same synthetic fixtures on every platform | done | scans drawn with matplotlib's fonts and Pillow's basic layout (a6e2491); before, the Windows runner tested a different document |
| Update-signing key in GitHub secrets | owner | `SRA_UPDATE_SIGNING_KEY` (unchanged from Stage 35) |
| Code-signing certificate | owner | `WINDOWS_SIGNING_PFX_BASE64` / `_PASSWORD`; until then only labelled unsigned previews |
| Reproducible build toolchain | open | `requirements.txt` allows `flet>=1.0,<2`; the Windows builds now use flet-cli 1.1.2 with Flutter 3.47.9 while the source checkout was tested with Flet 1.0.5. Pinning the exact versions for a release is recommended |

## Owner decisions before a release

- Review and merge the stack (#52 → #61) in order; nothing is merged automatically.
- Native-speaker review of the new Latvian and Russian texts (import wizard, groups, report, AI assistant).
- Whether to enable the AI assistant in a release build: it stays off until a provider, a model and a key are set, but its data permissions deserve the owner's review.
- The two signing secrets above for a signed release.
- Check with Narrator that disabled steps of the import wizard are announced as unavailable (UI Automation reports one as enabled; see `STAGE36_E2E_RESULTS.md`).
