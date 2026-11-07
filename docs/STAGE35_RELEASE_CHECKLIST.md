# Stage 35 release-readiness checklist

Each gate below has a status and the evidence behind it. Nothing is merged
into `main`. The pull requests are drafts, stacked in this order:

#47 (integration) → #48 (installer) → #49 (updates) → #50 (research plan, Word report) → #51 (AI providers, native DPI)

**Status:** done · open (work remains) · owner (needs the owner).

## Distribution and updates (highest priority)

| Gate | Status | Evidence |
|---|---|---|
| One integration branch; full suite and the packaged-EXE journeys on one SHA | done | #47, `docs/STAGE35_INTEGRATION.md`. On `a3dc4f9` all four workflows passed: Python tests 42309305044, Windows bundle 42309305164, GUI journeys 42309305349 (6/6) and packaging experiments 42309305064 |
| Brief COPE (#22) and packaging (#25) audited and included | done | merged into #47; Brief COPE (28) and import-integrity (19) suites pass together |
| Older version never writes to a newer project (downgrade safety) | done | `tests/test_project_store.py`: the new test fails before the fix and passes after |
| Versioned setup `StatisticalResearchAssistant-<version>-Setup.exe` | done | #48; `packaging/windows/StatisticalResearchAssistant.iss`; run 42315977581 built `…-1.0.0-preview.3-Setup.exe` (95.3 MiB) |
| Per-user install without administrator rights, one AppId, Start menu, "Installed apps" | done | run 42315977581, installed in 16.5 s; the shortcut target, a single registration and the version were checked |
| Research data outside the program folder; the program folder unchanged by use | done | `app_paths.py`; journey `installed-data`; check `unchanged` (6,650 files) |
| Data of preview builds found, previewed, copied, verified; originals untouched | done | `legacy_data.py`, `data_ui.py`, `tests/test_legacy_data.py` (14 tests); journey `legacy-migration` on the installed program |
| Upgrade in place keeps every project | done | run 42315977581: B installed over A in 17.7 s, one registration, both projects open |
| Uninstall removes the program and keeps the data; the data is deleted only after two confirmations and never silently | done | run 42315977581: uninstalled in 3.5 s, nothing left in the program folder, the data folder kept; a reinstall finds the projects |
| Signed manifest (Ed25519), SHA-256, host/channel/version/AppId rules, no downgrade | done | #49; `update_manifest.py`, `update_client.py`, `tests/test_updates.py` |
| In-app update A → B on the installed program, with negative cases | done | `windows-update-e2e.yml` passed end to end on `1931d11` (run 42324768467), and on the merged #50 (42324797400) and #51 (42324827922). Covered: another signer refused; older version not offered; damaged download deleted; update announced at start; What's new; interrupted download resumed; **Update now** to the restarted B in 45.1 s; B came to the front by itself and reported "Updated to version 1.0.1-test.19 … All 1 projects are in place"; the project opens; one registration of B; the uninstaller keeps the data. Fixed on the way: a PowerShell call that did not answer (`8dce446`); the installer inherited this runtime's private variables (`eb91410`); the new window opened behind another one (`05528de`) |
| Code-signature decisions on real Windows | done | run 42324768467, `tools/check_code_signature.py` with a throwaway certificate: untrusted refused (NotTrusted); trusted with the pinned publisher accepted (Valid); another publisher refused; changed after signing refused (HashMismatch), also by unsigned preview builds; unsigned refused while a signature is required; unsigned accepted by an unsigned preview build |
| The publisher of a signed update is read however the program was started | done | `1931d11`: Windows PowerShell is started with its own module path. A program started from PowerShell 7 read no publisher and would have refused a correctly signed update. Tested on Windows (`tests/test_updates.py`) and in the code-signature step above |
| Draft releases only; stable needs a code-signing certificate | done | `release.yml`; the owner publishes |
| Update-signing key in GitHub secrets | owner | `python tools/update_signing.py new-key …` → secret `SRA_UPDATE_SIGNING_KEY` |
| Code-signing certificate | owner | secrets `WINDOWS_SIGNING_PFX_BASE64` / `_PASSWORD`; until then only labelled unsigned previews can be built |

## Research workspace

| Gate | Status | Evidence |
|---|---|---|
| One editable Word report from several results (#42) | done | #50; `report_docx.py`; `tests/test_report_docx.py` (9 tests); the journey `project-a` exports it on the packaged EXE |
| Versioned, hypothesis-aware research plan (#40) | done (first increment) | #50; project format 3; `tests/test_project_store.py`, `tests/test_workspace_plan.py` |
| Joining datasets, the study graph, the supervisor audit view (#40) | open | not started |
| Deterministic method recommendation with explanations (#41) | open (partly) | the guided design of #37 (alternatives, checks, refusals in words); explanations for all 15 methods are not done |
| 33 engine ground-truth tests kept | done | #38, merged into #47 |

## AI (#43)

| Gate | Status | Evidence |
|---|---|---|
| Bring your own key (BYOK) in Windows Credential Manager, no plain-text fallback | done | #51; `secret_store.py`; a real Credential Manager round trip runs on Windows CI |
| Model lists from the provider (OpenAI, Anthropic, Gemini), manual model ID, exact model recorded | done | `ai_providers.py`, `tests/test_ai_providers.py` (17 tests, against a mock of each provider) |
| Retries on 429/5xx, timeouts, cancellation, daily token budget, key never in errors or logs | done | same |
| Integrity: numbers not in the engine output flagged, prompt injection neutralised, no text in the audit log | done | `ai_assist.py` |
| Assistant panel that sends project content (preview, consent, accept or edit) | open | the pipeline is implemented and tested; the panel is not enabled (`AI_AVAILABLE` stays False) |
| Streaming replies | open | replies arrive whole |

## Display and accessibility (#46)

| Gate | Status | Evidence |
|---|---|---|
| Native Windows display scale 100/125/150 % (not browser zoom) | done | `windows-native-dpi.yml` (runs 42318347352 and 42324828590): window DPI 96/120/144 at 100/125/150 %, Home and all seven sidebar areas shown, nothing clipped. The runner's display allows at most 175 %; `tools/set_display_scale.py` changes the Windows setting itself |
| Browser screenshots at device scale 1.25/1.5 | done (earlier) | artifact `workspace-screenshots`; a weaker check, kept separate |
