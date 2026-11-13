# Stage 36.8 — Preview release candidate checklist

The release candidate is the branch `claude/stage368-rc`, draft PR #64 (base `claude/stage36-acceptance`, the head of the Stage 36 stack). Nothing is merged into `main` and nothing is published by this work. The owner decides.

Every gate below names its evidence. "done" means verified by the named test or run, not merely implemented.

## 1. Four statuses, kept apart

| Status | State |
|---|---|
| Automated QA passed | see §2; all major checks on one final commit (§5) |
| Manual user acceptance passed | **not yet** (`docs/STAGE368_REAL_USER_ACCEPTANCE.md` §3) |
| Language review passed (LV, RU) | **not yet**: no native-speaker review has taken place (`docs/STAGE368_LOCALE_REVIEW.md`) |
| Production signing configured | **no**: unsigned preview; `SRA_UPDATE_SIGNING_KEY`, `WINDOWS_SIGNING_PFX_BASE64` and `WINDOWS_SIGNING_PFX_PASSWORD` are owner-supplied and not configured |

## 2. Definition of done (issue #62, Part 14)

| Gate | State | Evidence |
|---|---|---|
| Every required earlier feature is in the integration graph | done | `docs/STAGE368_BRANCH_INTEGRATION.md`: the only missing commit, af300b5, is merged (3435368) |
| One reproducible RC branch | done | `claude/stage368-rc`; `docs/STAGE368_BUILD_LOCK.md` |
| Runtime dependencies and toolchain pinned | done | hashed locks, `packaging/build_toolchain.lock.json`, Dart lock; strict build identity; `tests/test_build_lock.py` |
| No known critical data-loss, startup or workflow bug | **open** | the review findings K1–K5 in §3 |
| Import accessibility discrepancy resolved or documented | done | `docs/STAGE368_A11Y_AND_LOCALE.md` §1; Windows run 43418623163 |
| OCR performance profiled, improvements measured | done (Windows after-profile from the final run) | `docs/STAGE368_OCR_PERFORMANCE.md` |
| Scientific safeguards kept | done | full suite incl. numeric oracles; no automatic confirmation (scales, versions, scoring keys, reverse items, coding) |
| RU/LV reviewable quality report | see `docs/STAGE368_LOCALE_REVIEW.md` | |
| All 13 Windows GUI journeys pass on the final commit | | §5 |
| Installer and A → B update pass | | §5 |
| Project data survive update and reinstall | | installer workflow (upgrade, uninstall, reinstall); update workflow |
| AI privacy gates enforced | see `docs/STAGE368_AI_GATE.md` | |
| Unsigned-release limitations explicit | done | this file §4; installer and release texts say "unsigned preview" |
| Checklist and evidence complete | this file | |

## 3. Review findings (independent Fable review) and their state

| Finding | Kind | State |
|---|---|---|
| K1: design and data confirmations carried over to other variables and data | scientific integrity | being fixed on this branch (see commit log) |
| K2: notes, review ticks and report settings not saved across a restart; report title shown in another project | data loss | being fixed on this branch |
| K3: data preparation reset confirmed measurement levels and was missing from the project history | data integrity | being fixed on this branch |
| K4: "p(adjusted)" written also without correction | scientific correctness | **fixed** f193df2, `tests/test_stage368_review_fixes.py` |
| K5: Kruskal–Wallis batch without group medians, mean ranks and Dunn pairs | scientific reporting | **fixed** f193df2 |
| K6: UI Automation disabled state, keyboard, Narrator | accessibility | step fixed (dff65c8); platform limitation and the open items documented |
| R7 / licence: pingouin (GPL-3.0) in the program's process, no project LICENSE | legal | **owner decision** (`docs/STAGE368_BUILD_LOCK.md` §5) |

## 4. Before any public release (owner actions)

1. **Licence.** Choose the program's licence (add a LICENSE file). Then either keep pingouin (GPL-3.0-or-later fits) or approve replacing its one use (Cronbach's α + Feldt interval) with an in-house implementation, verified against pingouin in the tests.
2. **Update-signing key.** Create the Ed25519 key offline (`tools/update_signing.py new-key`, public part with `public-key`). Store the private key only as the repository secret `SRA_UPDATE_SIGNING_KEY`, never in chat, logs or files. Put the public key into the build (`write_build_info --update-key`).
3. **Code signing (stable channel only).** A certificate as `WINDOWS_SIGNING_PFX_BASE64` and `WINDOWS_SIGNING_PFX_PASSWORD`. Without it only the preview channel can be released, and it stays "unsigned preview".
4. **Corresponding source for the OCR runtime's GPL/LGPL DLLs** (jbigkit, libiconv, libintl, libunistring, libidn2). Attach the pinned MSYS2 source packages to the release, or keep the written offer of `THIRD_PARTY_NOTICES.txt`.
5. **Merge** (`docs/STAGE368_BRANCH_INTEGRATION.md`): retarget PR #64 to `main` and use "Create a merge commit". `release.yml` can be dispatched only once it is on `main`.

## 5. All major checks on one final commit

*Filled in once the final RC commit is pushed. Each row is the run on that SHA.*

| Check | Run | Result |
|---|---|---|
| Python tests (Linux suite with real OCR; pruned runtime; Windows SQLite; Windows research journey; browser screenshots and state checks) | | |
| Windows bundle (toolchain, hashed install, real OCR tests, packaged OCR and analysis self-tests, identity strict, SBOM, size budget) | | |
| Packaged GUI journeys (13 existing + new) | | |
| Installer (install, legacy migration, journeys on the installed program, B over A, uninstall keeps data, reinstall) | | |
| In-app update A → B (refusals, interrupted download, update, project in B) | | |
| Native display scale 100/125/150/175 % | | |
| Reproducible build (two runners, compared) | | |

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
