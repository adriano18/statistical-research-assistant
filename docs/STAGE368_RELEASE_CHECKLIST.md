# Stage 36.8 — Preview release candidate checklist

The release candidate is the branch `claude/stage368-rc`, draft PR #64 (base `claude/stage36-acceptance`, the head of the Stage 36 stack). Nothing is merged into `main` and nothing is published by this work. The owner decides.

Every gate below names its evidence. "done" means verified by the named test or run, not merely implemented.

## 1. Four statuses, kept apart

| Status | State |
|---|---|
| Automated QA passed | **yes**, on the final RC code commit b2abe20 (§5). The commits after it change only `docs/` |
| Manual user acceptance passed | **not yet** (`docs/STAGE368_REAL_USER_ACCEPTANCE.md` §3) |
| Language review passed (LV, RU) | **not yet**: no native-speaker review has taken place (`docs/STAGE368_LOCALE_REVIEW.md`) |
| Production signing configured | **no**: unsigned preview; `SRA_UPDATE_SIGNING_KEY`, `WINDOWS_SIGNING_PFX_BASE64` and `WINDOWS_SIGNING_PFX_PASSWORD` are owner-supplied and not configured |

## 2. Definition of done (issue #62, Part 14)

| Gate | State | Evidence |
|---|---|---|
| Every required earlier feature is in the integration graph | done | `docs/STAGE368_BRANCH_INTEGRATION.md`: the only missing commit, af300b5, is merged (3435368) |
| One reproducible RC branch | done | `claude/stage368-rc`; `docs/STAGE368_BUILD_LOCK.md` |
| Runtime dependencies and toolchain pinned | done | hashed locks, `packaging/build_toolchain.lock.json`, Dart lock; strict build identity; `tests/test_build_lock.py` |
| No known critical data-loss, startup or workflow bug | done in code and tests; Windows GUI confirmation in §5 | the review findings K1–K5 in §3 are fixed (`tests/test_stage368_review.py`, `tests/test_stage368_review_fixes.py`) |
| Import accessibility discrepancy resolved or documented | done | `docs/STAGE368_A11Y_AND_LOCALE.md` §1; Windows runs 43418623163 and 43440145161 |
| OCR performance profiled, improvements measured | done | `docs/STAGE368_OCR_PERFORMANCE.md`: the 52-item scan in the packaged program, 50.4 s before, 6.2 s on b2abe20 (run 43440145161), the same 52 candidates |
| Scientific safeguards kept | done | full suite incl. numeric oracles; no automatic confirmation (scales, versions, scoring keys, reverse items, coding) |
| RU/LV reviewable quality report | done (the review itself is the owner's) | `docs/STAGE368_LOCALE_REVIEW.md`: missing translations 11 → 0, English in workspace screens 49 → 2, a review list by screen and a glossary |
| All Windows GUI journeys pass on the final commit | done | 18 of 18 on the packaged program, and the same 18 on the installed program (§5) |
| Installer and A → B update pass | done | §5 |
| Project data survive update and reinstall | done | installer run 43440145158: B over A opens the same projects, uninstall keeps the data, the new installation finds it; update run 43440145261: the project opens in B |
| AI privacy gates enforced | done with mocked providers | `docs/STAGE368_AI_GATE.md`: the 10 gates of issue #62 in `tests/test_stage368_ai_gate.py` (30 tests, a network guard fails any real connection). Four defects found and fixed: a model refusing the request, a timed-out generation sent four times, cut-off replies crashing Test connection, Send after a provider change elsewhere. The assistant is off until a key and a model are set. **No real provider was called**: the live smoke test needs an authorised key and runs only when the owner enables it |
| Unsigned-release limitations explicit | done | this file §4; installer and release texts say "unsigned preview" |
| Checklist and evidence complete | done | this file; `docs/STAGE368_REAL_USER_ACCEPTANCE.md` §2 |

## 3. Review findings (independent Fable review) and their state

| Finding | Kind | State |
|---|---|---|
| K1: design and data confirmations carried over to other variables and data | scientific integrity | **fixed** 23f4f4a. A design confirmation holds while its variables are the same. A data confirmation holds for one table (SHA-256), one set of variables with their levels, and one method with its options. Otherwise it is cleared, with a notice. "Run again" on the same data still takes two actions. `DesignConfirmationTests` |
| K2: notes, review ticks and report settings not saved across a restart; report title shown in another project | data loss | **fixed** 23f4f4a. Stored in the project, format 5 kept, no migration. Restored after a restart; another project shows none of them. `ResearcherEntriesTests` |
| K3: data preparation reset confirmed measurement levels and was missing from the project history | data integrity | **fixed** 23f4f4a. Levels of existing columns kept; each step recorded and shown in the report's data-preparation section. `PreparationHistoryTests` |
| K4: "p(adjusted)" written also without correction | scientific correctness | **fixed** f193df2, `tests/test_stage368_review_fixes.py` |
| K5: Kruskal–Wallis batch without group medians, mean ranks and Dunn pairs | scientific reporting | **fixed** f193df2 |
| K6: UI Automation disabled state, keyboard, Narrator | accessibility | step fixed (dff65c8); platform limitation and the open items documented |
| R7 / licence: pingouin (GPL-3.0) in the program's process, no project LICENSE | legal | **owner decision** (`docs/STAGE368_BUILD_LOCK.md` §5). Stage 37 offers option (b) as one separate commit on `claude/stage37-methods`: α in-house, pingouin only in the test lock (§5.3). The project licence is still the owner's choice. |

## 4. Before any public release (owner actions)

1. **Licence.** Choose the program's licence (add a LICENSE file). Then either keep pingouin (GPL-3.0-or-later fits) or approve replacing its one use (Cronbach's α + Feldt interval) with an in-house implementation, verified against pingouin in the tests. The replacement is ready as one separate, droppable commit on the Stage 37 branch (`docs/STAGE368_BUILD_LOCK.md` §5.3). Approving it does not choose the licence.
2. **Update-signing key.** Create the Ed25519 key offline (`tools/update_signing.py new-key`, public part with `public-key`). Store the private key only as the repository secret `SRA_UPDATE_SIGNING_KEY`, never in chat, logs or files. Put the public key into the build (`write_build_info --update-key`).
3. **Code signing (stable channel only).** A certificate as `WINDOWS_SIGNING_PFX_BASE64` and `WINDOWS_SIGNING_PFX_PASSWORD`. Without it only the preview channel can be released, and it stays "unsigned preview".
4. **Corresponding source for the OCR runtime's GPL/LGPL DLLs** (jbigkit, libiconv, libintl, libunistring, libidn2). Attach the pinned MSYS2 source packages to the release, or keep the written offer of `THIRD_PARTY_NOTICES.txt`.
5. **Merge** (`docs/STAGE368_BRANCH_INTEGRATION.md`): retarget PR #64 to `main` and use "Create a merge commit". `release.yml` can be dispatched only once it is on `main`.
6. **Which interface opens first.** The program starts in the classic interface. The research workspace, which the changelog describes, opens from its Home screen ("Open the preview"), and the choice is not remembered between starts. Options for the next stage: open the workspace by default, or remember the interface used last.

## 5. All major checks on one final commit

The final RC code commit is **b2abe20** (`b2abe20ba7e5e26c3f06c5f85ce97b0621aaf648`). Every row is the run on that SHA. Later commits change only `docs/`. CI runs again on the branch head, and PR #64 lists those runs as well.

| Check | Run | Result |
|---|---|---|
| Python tests (Linux suite with real OCR; pruned runtime; Windows SQLite; Windows research journey; browser screenshots and state checks) | [43440145111](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145111) | success. The same suite locally: 1,249 tests OK (10 skipped: live AI and platform-only) |
| Windows bundle (toolchain, hashed install, real OCR tests, packaged OCR and analysis self-tests, identity strict, SBOM, size budget) | [43440145139](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145139) | success |
| Packaged GUI journeys (13 existing + 5 new) | [43440145161](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145161) | success: 18 of 18 in 27.6 min |
| Installer (install, legacy migration, journeys on the installed program, B over A, uninstall keeps data, reinstall) | [43440145158](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145158) | success: 18 of 18 journeys on the installed program, then upgrade, uninstall and reinstall |
| In-app update A → B (refusals, interrupted download, update, project in B) | [43440145261](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145261) | success |
| Native display scale 100/125/150/175 % | [43440145321](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145321) | success |
| Reproducible build (two runners, compared) | [43440145269](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145269) | success: 0 deviations not explained by a known build-time difference (`docs/STAGE368_BUILD_LOCK.md` §4) |
| Packaging experiments (size and start-up, informative) | [43440145142](https://github.com/adriano18/statistical-research-assistant/actions/runs/43440145142) | success |

The unsigned preview installer of this commit is the artifact `StatisticalResearchAssistant-Setup-unsigned-preview` of the installer run. The synthetic files for the owner's checklist are its `synthetic-acceptance-files` artifact. Both are kept for 14 days by GitHub.

**Not a release.** These are temporary GitHub Actions artifacts, made for review. The public update channel is the GitHub Release made by `release.yml` (§6), after the owner's go-ahead.

## 6. Releasing the preview (after the owner's go-ahead; not done by this work)

1. On `main`: Actions → "Release" → Run workflow. Version `1.0.0-preview.1`, channel `preview`.
2. The workflow:
   - builds with the pinned toolchain;
   - checks the build identity strictly;
   - runs the installed program's smoke test;
   - signs the update manifest with `SRA_UPDATE_SIGNING_KEY` and attaches it, the installer, its SHA-256, `build_info.json` and the SBOM;
   - creates a **draft** pre-release.
3. The owner reads the draft and publishes it. Publishing copies the signed manifest to the `preview-channel` release. Preview installations find the update there: a GitHub Release, not a temporary Actions artifact.
4. Changelog shown in the program: `release-notes/1.0.0-preview.1.json` (EN/LV/RU).

## 7. Rollback

- **A bad preview release.** Unpublish it, or mark it as a draft again, and restore the previous `sra-update-preview.json` in `preview-channel`. The updater never installs an older version than the one installed (downgrade refused), so users on the bad version stay on it until a fixed, newer version is published. This is the intended safety rule.
- **Projects.** Every migration writes a copy first (`project_store.migrate` → `.backups`). A project opened by a newer version can be restored from that copy for an older version.
- **The RC branch.** It is not merged. `main` is unchanged until the owner merges.
