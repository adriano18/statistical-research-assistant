# Stage 37 — pause checkpoint (2026-11-13)

The owner has paused all work until **Monday 2026-11-16**, at the owner's request for token-efficient maintenance. Work resumes only after the owner explicitly authorises it.

Nothing was merged into `main`, nothing was released, and no Stable build was published. No force-push, hard reset or worktree deletion was used.

## 1. Branches, commits and PRs

All PRs are drafts. "Opened at checkpoint" means the PR was opened at the checkpoint and its CI started automatically. Its results were deliberately not read, because the owner asked for no CI polling.

| PR | Branch @ head | Base | Content | State at the checkpoint |
|---|---|---|---|---|
| #64 | `claude/stage368-rc` @ `8f49d54` (last code commit `b2abe20`) | `claude/stage36-acceptance` | Stage 36.8 release candidate | Untouched. CI green on `8f49d54`. |
| #65 | `claude/stage37-research-workflow` @ `519b1ec` | `claude/stage368-rc` | Stage 37.0a | Untouched. CI green (10 checks). |
| #71 | `stage37/master-acceptance-interoperability-spec` @ `2f9af71` | `claude/stage37-research-workflow` | Owner's spec and synthetic fixture | Owner's PR, unchanged |
| #72 | `claude/stage37-review` (this commit) | #71 | Fable review, licensing brief, this checkpoint | CI green on `f05dbd4` (5 checks). This commit's CI was not read. |
| #73 | `claude/stage37-0b` @ `a8663ce` | #71 | Stage 37.0b | Opened at checkpoint |
| #74 | `claude/stage37-methods` @ `074dfbc` | #71 | Research methods (#66) | Opened at checkpoint |
| #75 | `claude/stage37-rag` @ `9da2c4c` | #71 | Local research library (#69) | Opened at checkpoint |
| #76 | `claude/stage37-ux-shell` @ `4da2a98` | #71 | UX 1/2 (#68): start, settings, language, typography | Opened at checkpoint |
| #77 | `claude/stage37-ux-vars` @ `0cdd4a0` | #71 | UX 2/2 (#68): variable panel, reuse | Opened at checkpoint |
| #78 | `claude/stage37-export` @ `619143d` | #71 | Export (#67) | Opened at checkpoint |

- **Siblings, not yet stacked.** #73–#78 are independent siblings on #71. They are meant to be stacked with merge commits in this order: 0b → methods → export → RAG → UX.
- **Local refs with no unique commits.** These were not pushed. Stopped workflow stages created them, and they hold nothing new:
  - `claude/stage37-ux` = `b83567c` (contained in #76 and #77);
  - `claude/stage37-0b-fixes` = `a8663ce`;
  - `claude/stage37-methods-fixes` = `c66798b` (an ancestor of `074dfbc`).
- **Watching.** This session is unsubscribed from #64, #65 and #72–#78 and has no scheduled check-ins.

## 2. Test results (exact, and who ran them)

The Linux suite command was:

```
SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 python -m unittest discover -s tests
```

| Commit | Result | Run by |
|---|---|---|
| `a8663ce` (0b) | 1,389 OK, 10 skipped | implementing agent |
| `074dfbc` (methods) | 1,421 OK, 10 skipped | implementing agent |
| `619143d` (export) | 1,376 OK, 10 skipped, 1,043 s | implementing agent |
| `9da2c4c` (RAG) | 1,403 OK, 10 skipped, 1,023 s | implementing agent |
| `e15ad78` (UX shell) | 1,389 OK, 10 skipped, 970 s | implementing agent |
| UX vars | 1,368 OK, 10 skipped, 1,002 s | implementing agent |
| `b83567c` (UX baseline) | 1,342 OK, 10 skipped | implementing agent |
| `8f49d54` / `b2abe20` (RC) | All workflows green: Python, bundle, GUI 18/18, installer, update, DPI, reproducibility | GitHub Actions |
| `519b1ec` (37.0a) | 10 checks green | GitHub Actions |

Notes on the table:
- For UX shell, `4da2a98` changed only documentation, and its doc test was re-run.
- For UX vars, the suite ran on the committed code; `0cdd4a0` is documentation only.
- For the UX baseline, the run came before three refactors of its new test module. Those 16 tests were re-run after the refactors.

**Not verified:**
- The integrator did not re-run these suites. The counts come from the implementing agents' reports, and their logs were in the session scratchpad, which is not durable.
- No Stage 37 implementation commit has run on Windows yet. Six new journeys have never run there: `stage37-hypothesis`, `export-data`, `research-library`, `startup-workspace`, `settings-language` and `variable-picker`. They first run in the CI of #73–#78.

## 3. Independent reviews

- **Fable 5.2 narrow review.** Complete and read-only, in `docs/STAGE37_FABLE_NARROW_REVIEW.md`. It covers top-10 improvements, defects D1–D12, science S1–S17, UX U1–U12, maintainability M1–M7 and two interface architectures, with one recommended.
- **Adversarial verification.** Read-only reviewers per lens. Every fix stage was stopped at its start, before any change. The files are:
  - `docs/stage37/checkpoint/verification/*.json` (each finding with evidence and a red test);
  - `SUMMARY.md` (the table of confirmed findings);
  - `ux-implement-results.json` (the UX implementers' reports).

| Branch @ commit | Lenses completed | Confirmed findings: blocker / major / minor |
|---|---|---|
| 0b @ `a8663ce` | audit, report, workflow, Windows | 0 / 9 / 21 |
| methods @ `074dfbc` | numerics, science, locks, integration | 0 / 5 / 10 |
| export @ `619143d` | injection, .sav, .xlsx, integrity, integration | 0 / 11 / 32 |
| RAG @ `9da2c4c` | privacy, injection, storage, retrieval, integration | 3 / 18 / 26 |
| UX shell, UX vars | none (review not started) | — |

The methods numerics lens matched every path coefficient, SE, t, CI, R² and F of Models 1/4/7/14 to the reviewer's own QR-based OLS/HC3 within 1e-9. It ran on fixtures v1 and v2.

## 4. Known defects to fix first

The full list is in `SUMMARY.md`. The PR bodies of #73–#78 list every major.

- **Blocker (RAG).** `stored_name` from a restored `.sra` library is joined to `sources/` unchecked and passed to `os.startfile`. Open can therefore launch an attacker-chosen file.
- **Blocker (RAG).** When the open project's library fails to open, the page serves the previous project's library.
- **Major, scientific wording (methods).** "Inconsistent mediation (suppression)" is stated from the sign of the point estimate even when the bootstrap CI includes 0.
- **Major, model confirmations (methods).** After a switch between Model 7 and Model 14, the other model's confirmation is still held.
- **Major, audit trail (0b).** These changes after results are possible without a reason or a record:
  - removing a hypothesis;
  - changing the planned method or variables;
  - changing the question kind.
- **Major, legacy plans (0b).** Older plan versions recount S16 and can flip a hypothesis to confirmatory.
- **Major, report (0b).** The hypothesis block shows a raw p next to "Holm", and the two-group n does not come from the engine.
- **Major, data fidelity (export).**
  - The CSV guard can be bypassed through the separator.
  - In `.xlsx`, pre-1900 dates are corrupted, and the "lossless" output changes content silently.
  - In `.sav`, there are missing-value, short-name and windows-1251 defects.
- **Major, privacy (RAG).**
  - Numeric participant codes are not treated as identifiers.
  - An approved Ask request is resent up to 3 times after a connection reset.
  - Removed documents stay in FTS5 and in backups.
  - Unbounded PDF/DOCX inflation, plus cubic and quadratic text-processing paths.
- **Merge (all branches).** Every branch claims the same journey slot or slots in `tools/windows_gui_e2e.py` and in the journey-count test.

## 5. Not finished

- Fix stages: none started on any branch.
- UX: #76 and #77 are not merged into one branch and have not been reviewed. Their combined interaction count has not been measured. Separately, #76 took the novice from 68 to 67 interactions and #77 from 68 to 30.
- Stacking and integration are not done. The runtime lock must be regenerated once for methods (pingouin removed) and export (pyreadstat added) together.
- 37.0b AC-10 is only partly met: a beginner needs 21 interactions; the target is ≤ 20.
- From the RC: keyboard-only and Narrator checks on Windows are still open.

## 6. Decisions for the owner

1. **Licence.** Choose A, B or C before any public distribution; see `docs/STAGE37_LICENSING_OPTIONS.md`. The last commit of #74 implements the B/C path: an in-house α, with pingouin only in the test lock.
2. **pyreadstat.** Accept it in the runtime (Apache-2.0, ReadStat MIT, about +1.6 MiB). Optionally allow GNU PSPP in the environment for an independent `.sav` check.
3. **Start interface.** Make the research workspace the default start (#76); the classic interface stays reachable.
4. **AC-10.** Accept 21 interactions for the beginner, or ask for more reduction. Mandatory confirmations stay either way.
5. **Stacking.** Confirm the stack order and the base retargeting of #73–#78.
6. **Outside the code:** native LV/RU review, signing keys, and any Stable release.

## 7. How to resume

```bash
git fetch origin
git worktree add ../s37-rag claude/stage37-rag        # one worktree per branch
python3.12 -m venv ../venv-s37 && ../venv-s37/bin/pip install --require-hashes -r requirements-dev.txt
SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 ../venv-s37/bin/python -m unittest discover -s tests
```

- Use each branch's own locks: #74 moves pingouin to `requirements-dev.txt`, and #78 adds pyreadstat to `requirements.txt`.
- The workflow scripts are in `docs/stage37/checkpoint/workflows/`. Update their path constants first. Do not re-run completed lenses: give the fix stage the confirmed findings from the JSON files.

## 8. Recommended first three actions

1. Read the CI results of #73–#78 once. They are the first Windows runs of the six new journeys. Add any failures to the finding lists.
2. Fix each branch from the saved findings, blockers first: RAG path escape and the cross-project library. Write a red test before each fix, and run one full suite at the end of each branch.
3. Merge the two UX halves, then run their review and fixes. Then stack 0b → methods → export → RAG → UX, regenerate the runtime lock once, and run the Windows E2E suite once on the top of the stack.

## 9. Preservation

- **Committed and pushed.** At the checkpoint, every agent worktree and the integrator's worktrees were clean. All unique commits are pushed.
- **Two old scratch worktrees still had uncommitted files:**
  - In `before` at `c840571`, from the Stage 34.5 measurements, two helper scripts had never been committed. They are saved as `docs/stage37/checkpoint/unpushed-scratch/before-worktree-c840571.patch`.
  - In `base` on `claude/eager-cerf-d4cnd3`, there were 267 changed or untracked files. Checked by blob hash, every one of them already exists in committed history.
- **Private files.** The thesis plan, WHO-5 PDF and MSPSS PDF were never committed or quoted. They exist only in the paused session's private scratchpad.
- **Data in CI and reviews.** Public CI and every review used synthetic fixtures only.
- **Project format.** Format-6 migrations and the append-only protocol records are unchanged on every branch.
