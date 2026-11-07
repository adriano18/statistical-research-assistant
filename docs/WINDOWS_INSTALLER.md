# Windows installer (Stage 35, issue #44)

The application is installed once with
`StatisticalResearchAssistant-<version>-Setup.exe` and started from the
Start menu (or, optionally, from the desktop). Nothing else is installed by
hand: the setup file contains the program and everything it needs, offline:

- the Flutter/Flet runtime and the embedded Python;
- every statistical package;
- the local OCR engine with English, Latvian and Russian language data and its licences;
- the example datasets, fonts and assets.

## What the installer does

| | |
|---|---|
| Installs for | the current user, without administrator rights (`%LOCALAPPDATA%\Programs\Statistical Research Assistant`). "All users" can be chosen on the first page and needs administrator rights. |
| Identity | one fixed AppId `{8467540D-B8DC-4046-A878-0EE29F330E63}` (`app_identity.INSTALLER_APP_ID`). A later version replaces the installed one; it never appears twice in "Installed apps". |
| Shortcuts | Start menu always; desktop shortcut only if ticked. |
| Registration | "Installed apps" / "Programs and Features": name, version, publisher, uninstaller. |
| Updates | Before an update, the previous version's own files and folders are removed, so no stale Python package survives (`generated-layout.iss`, written by `tools/build_installer.py` from the bundle). If the program is running, setup waits until it closes (in-app update) or asks to close it; it never terminates the program. |
| Uninstall | Removes the program, its shortcuts and its registration. Research data is kept, see below. |
| Windows | 10 or 11, 64-bit. |

## Where research data lives

The following are kept in **`%LOCALAPPDATA%\StatisticalResearchAssistant`**, never in the program folder:

- projects, with their copies of the source data;
- questionnaires and their responses;
- the researcher profile;
- figures and backups (`app_paths.py`).

So installing, updating, reinstalling or uninstalling the program cannot change or delete them.

```
%LOCALAPPDATA%\StatisticalResearchAssistant\
  projects\        one folder per project (database, dataset copies, figures, backups)
  surveys\         questionnaires and responses
  profile\         the optional researcher profile
  logs\            startup logs (no research data)
  migration.json   what was copied from earlier versions
```

The folder is shown in **Settings → Your data**, with **Open folder** (in the classic window: **Settings → Your data…**).

**Uninstall and data:**

- The uninstaller asks whether the research data should be deleted too. The default answer is **No**.
- Deleting needs a second, explicit confirmation.
- A silent uninstall (`/VERYSILENT`) never deletes it.

## Data of earlier preview versions

Preview builds kept data in two other places:

- Flet's per-user folder `%APPDATA%\Your Company\Statistical Research Assistant\data` ("Your Company" was the build's placeholder company name);
- the oldest previews kept questionnaires inside the folder the ZIP was unpacked to.

The installed program never uses those folders in place:

- **Known places only.** On the first start it looks in these known places, and nowhere else on the disk.
- **Preview first.** If it finds earlier data, it lists each project and questionnaire by title and offers **Copy into my data folder** or **Not now**.
- **Checked copies.** Each item is copied under a temporary name and compared with its original: the database content, including changes still in its write-ahead log, and every other file byte for byte. Only then is it given its final name. An interrupted copy leaves nothing half-written.
- **Originals untouched.** Originals are only read: they are never moved, changed or deleted.
- **Nothing overwritten.** An item that already exists in the data folder with other content is reported as a conflict and left alone. Nothing is ever replaced.
- **Remembered.** "Not now" is remembered. A copied item is not offered again, even after it changes in the new folder.
- **Portable folders.** For a portable folder elsewhere (for example in Downloads), use **Settings → Your data → Find data from an earlier version…** and choose that folder. Only that folder is searched.
- **Recovery.** If copying fails, the dialog names what was not copied and why. Nothing in the earlier folder has changed, so the step can be repeated later.

Tests: `tests/test_legacy_data.py`, `tests/test_data_ui.py`, and the `legacy-migration` journey on the installed program.

## Size

The measured size of every installer is written into the summary of the *Windows installer* workflow. Compression is LZMA2, solid.

The program folder is the measured bundle of #25 (`docs/DISTRIBUTION_OPTIMIZATION.md`): package test suites, build-only files and the Pillow AVIF codec are removed.

- **Nothing the program uses is removed.** The whole test suite runs on the same pruned environment, and the packaged analysis self-test reproduces every report hash.
- **No formula is replaced.**
- **The installer stays a complete offline installer.** OCR stays included.

## Code signing

The pipeline signs when a certificate is configured, and only then.

| Build | Signed | How it is labelled |
|---|---|---|
| Pull request and preview builds | no | artifact `StatisticalResearchAssistant-Setup-unsigned-preview`; `installer.json` says `"signed": false`; Windows SmartScreen may warn |
| Release with a certificate | setup, uninstaller and program | `"signed": true`; updates must carry the same publisher (#45) |

To sign, a legitimate code-signing certificate is needed. Its credentials are stored as GitHub Actions secrets, never in the repository:

- for an OV/EV certificate in a file, `WINDOWS_SIGNING_PFX_BASE64` and `WINDOWS_SIGNING_PFX_PASSWORD`;
- or the settings of a cloud signing service such as Azure Trusted Signing.

`tools/build_installer.py --sign-command "signtool sign /fd sha256 /tr <timestamp> /td sha256 ... $f"` signs setup and uninstaller.

Until a certificate exists, the installer is an **unsigned preview**: it is not presented as trusted or signed anywhere.

## How it is tested (Windows CI, `.github/workflows/windows-installer.yml`)

On a clean runner, against the real program and the real registry:

1. Build the application as distributed and package it.
2. Silent per-user install. Check:
   - the program folder;
   - that the Start-menu shortcut targets the installed executable;
   - one "Installed apps" registration with the right version and folder.
3. On the **installed** program with the real data folder:
   - a preview build's data is offered, copied, checked and opened, and the originals are unchanged;
   - a project created there lands in `%LOCALAPPDATA%\StatisticalResearchAssistant`;
   - running the program adds nothing to the program folder.
4. The six researcher journeys of Stage 34.5 on the installed program, and a normal start with screenshots.
5. Upgrade in place to a later version: still one registration, the new version recorded, every project intact and opening.
6. Silent uninstall: program, shortcut and registration gone, research data kept. A new installation finds the projects again.

Evidence such as logs, screenshots and the result JSON is in the artifact `windows-installer-evidence`.
