# Updates inside the application (Stage 35, issue #45)

A researcher installs the program once (`docs/WINDOWS_INSTALLER.md`). Every later version arrives inside the application.

## What the researcher sees

1. **The new version is announced.**
   - **When it is noticed:** at most once a day, a few seconds after the start, the program checks for a new version. The check can be turned off under **Settings → About and updates** (in the classic window: **Settings → Check for updates…** or **Help → About and updates…**).
   - **The banner:** if a newer version exists, a banner says **"A new version is available — 1.1.0"**, with **What's new**, **Update now** and **Later**. Later hides it for a week.
2. **What's new.** It shows the change list and the known limitations in English, Latvian or Russian, and a link to the release notes.
3. **Update now:**
   - downloads the installer, showing progress (MB) and a **Cancel** button;
   - checks it;
   - backs up every project database;
   - closes the program and installs the new version.
4. **The program starts again by itself** and says **"Updated to version 1.1.0. Your projects and research data are preserved."** It also gives the result of checking that every project listed before the update is still there (**View what's new**).
   Its window comes up above the other windows: while the old version closed, Windows usually activated another program, and the new window would otherwise open behind it. It does not take the keyboard from another program; if Windows does not let it become the active window, its taskbar button flashes.
5. **Without a connection,** the check fails silently and the program works as usual. A manual check says so in words.

## What is checked, and in which order

Nothing downloaded is executed before every check below has passed. Each refusal is explained in words, and the program keeps working.

| Step | Check | Refused when |
|---|---|---|
| Manifest download | HTTPS only, from `github.com` and GitHub's download hosts; redirects only to those; at most 256 KiB | another scheme, host or port |
| Signature | Ed25519 over the exact manifest bytes, by a key this build trusts (`build_info.json`). The private key exists only as a GitHub secret | unsigned, signed by another key, or changed after signing |
| Identity | the AppId of this application | another application |
| Channel | stable builds take stable releases only; preview builds take preview and stable | another channel, or a "stable" pre-release |
| Version | SemVer greater than the installed one, and the update's minimum version is met | equal or older: no downgrade, no replayed old manifest |
| Download | never more bytes than announced; resumable after an interruption; cancellable | larger or truncated |
| Checksum | SHA-256 of the file equals the signed manifest's | any difference: the file is deleted |
| Code signature | Windows' own verification (`WinVerifyTrust`; the signer's subject and thumbprint from `Get-AuthenticodeSignature` in Windows PowerShell, started with its own system module path). A build made with a certificate accepts only the same publisher (subject and thumbprint pinned) | unsigned while a signature is required, another publisher, or a broken or untrusted signature. Unsigned preview builds accept unsigned installers, never broken ones |

### Then the handoff

1. Every open project is closed.
2. Every project database and the profile are copied to `projects\.backups\update-<from>-to-<to>-<time>`. The last three such copies are kept.
3. The update is recorded in `updates\pending.json`.
4. The verified installer is started with `/UPDATEFROMAPP`, and the program closes.
5. Setup waits for the program's mutex to disappear (at most 120 s) and replaces the program files. It never touches the data folder: research data lives in `%LOCALAPPDATA%\StatisticalResearchAssistant` (`app_paths.py`). Then setup starts the new version.
6. The new version compares the record with itself:
   - which version it now is;
   - whether every project listed before the update is still there.

   It reports the result and keeps a history in `updates\history.json`.

**If the installation did not happen,** the next start says "The update was not installed; this is still version X. Your data is unchanged." and names the installer's log.

**Database formats and downgrades:**
- A new version that changes the project format migrates a project only when it is opened, and backs up its database first (`project_store.migrate`).
- An older version never writes to a project saved by a newer version: it refuses it without touching it.
- The updater never offers an older version.

## Owner setup (once)

1. **Update-signing key (required).** On any computer with Python:

   ```bash
   python tools/update_signing.py new-key --private-out update-signing.key
   ```

   - Add the one line in `update-signing.key` as the repository secret `SRA_UPDATE_SIGNING_KEY` (Settings → Secrets and variables → Actions), then delete the file. Do not commit it.
   - Every release build writes the matching public key into its `build_info.json`.
   - Without the secret, the release workflow stops: no build ships that cannot verify its own updates.
2. **Code-signing certificate (required for the stable channel).** Store an OV/EV certificate as `WINDOWS_SIGNING_PFX_BASE64` and `WINDOWS_SIGNING_PFX_PASSWORD`. Without it only **preview** releases can be built, and they are labelled as unsigned previews everywhere.

## Releasing a version

1. Set `app_identity.VERSION` and add `release-notes/<version>.json` (change list and known limitations, EN/LV/RU).
2. Run **Release (draft)** (`.github/workflows/release.yml`) with the version and channel. It:
   - builds the application and the installer, signing them if a certificate is configured;
   - installs it, starts it and uninstalls it on a clean runner;
   - writes the signed `sra-update-<channel>.json`;
   - creates a **draft** GitHub release with the installer, its SHA-256, `installer.json`, `build_info.json` and the manifest.
3. Review the draft and **publish it**. Nothing is public before that.
   - **Stable:** the published release becomes GitHub's "latest". Every stable installation finds it at `releases/latest/download/sra-update-stable.json`.
   - **Preview:** publishing copies `sra-update-preview.json` to the `preview-channel` pre-release that preview installations check.

The full installer is downloaded for every update. A delta-update system such as Velopack would need a proof of concept on Windows first, and no custom binary patching is used.

## Tests

- `tests/test_updates.py`, 41 tests, most against a local HTTP server (Linux and Windows; five are Windows-only):
  - signatures, the app, channel and version rules;
  - downloads: resume, damage, oversize, cancel, redirects, offline;
  - code-signature decisions;
  - the backup and record before the handoff;
  - the report after the restart, also when the installer file is still in use;
  - after the restart the window is raised above other windows and never left always on top (Windows);
  - the signer is read even when the program was started from PowerShell 7 (Windows);
  - the dialog's texts in every language.
- `.github/workflows/windows-update-e2e.yml` (Windows), on the installed program:
  - **Setup:** two test installers A and B, whose update key is generated for the run and thrown away; a local update server that only those test builds accept.
  - **Refusals:** a manifest signed with another key is rejected, an older version is not offered, and a damaged download is deleted without starting it.
  - **The update itself:** the update is announced at start. **What's new** is shown. The download is interrupted, then retried, and continues where it stopped. **Update now** installs B, the program starts again as B and reports the update, and the project opens. The driver checks that B's window came to the front by itself before it touches the window (a click at its centre reaches B).
  - **After the update:** exactly one installation of B is registered, and the uninstaller keeps the data.
  - **Code signatures:** checked with a throwaway self-signed certificate:
    - untrusted is refused;
    - trusted with the pinned publisher is accepted;
    - another publisher, a tampered signed file, or an unsigned file while a signature is required is refused.
