# Stage 32 — bundled offline OCR (developer guide)

The Windows desktop package ships its own Tesseract 5 engine, so researchers
do **not** install Tesseract, Python or language packs. Source checkouts on
any OS keep using a locally installed engine.

## How the engine is resolved

`ocr_runtime.resolve_tesseract()` checks, in order:

| Order | Source | Notes |
|---|---|---|
| 1 | `TESSERACT_CMD` | Explicit developer override. If set to a missing file, OCR reports a configuration error; there is **no silent fallback**. |
| 2 | Bundled runtime | `bundled_ocr/windows-x64/` next to the application code (or `SRA_OCR_RUNTIME_DIR`). Runs `bin/tesseract.exe --tessdata-dir <bundle>/tessdata`, sets `TESSDATA_PREFIX`, puts `bin/` first on the child's `PATH`. |
| 3 | `tesseract` on `PATH` | Typical for Linux/macOS development. |

`SRA_DISABLE_OCR=1` turns OCR off. Browser/server mode never runs OCR.

Every call runs as a local subprocess on a private temporary PNG that is
deleted afterwards, with a deadline, user cancellation and a 16 MB output
cap. `ocr_readiness()` reports version, languages, missing `eng/lav/rus` data
and bundle integrity (file sizes, or full SHA-256 against `MANIFEST.json`).
The same information appears in the app under **Settings → Offline OCR
engine…** and **Help → Offline OCR engine…**.

## What is bundled and why it is trusted

* **Tesseract 5.5.4** from the MSYS2 UCRT64 binary repository (MinGW-w64,
  the toolchain family used by the common Windows Tesseract installers).
* Exactly the **40 DLLs** in the import closure of `tesseract.exe`, computed
  from the PE import tables with `pefile`; training tools are not bundled.
* `eng`, `lav`, `rus` and `osd` language data (tessdata_fast 4.1.0, the same
  files Debian/Ubuntu ship).
* Licence texts for every package (`licenses/`), including upstream texts
  taken from pinned MSYS2 *source* packages when a binary package has none
  (giflib, lz4, libidn2), plus `THIRD_PARTY_NOTICES.txt`.

`packaging/windows_ocr_runtime.lock.json` pins every package file name and
SHA-256 (from the MSYS2 repository database), and every extracted file's
SHA-256 and size. `tools/prepare_windows_ocr_runtime.py fetch` refuses any
mismatch. Binaries are **never committed** to Git; `bundled_ocr/` is ignored.

Total size: about 53 MB uncompressed.

### Licensing summary (review before public releases)

Most components are permissive (Apache-2.0, BSD, MIT, zlib, libpng and similar).
Copyleft components, used as replaceable DLLs inside the separate
`tesseract.exe` process:

* **jbigkit** (loaded by libtiff): GPL-2.0-or-later. Its source headers state
  "version 2 … or (at your option) any later version", so together with
  Apache-2.0 Tesseract the program is redistributed under terms compatible
  with GPL-3.0-or-later.
* libidn2, libunistring, libiconv, libintl: LGPL (with GPL alternatives).
* GCC runtime (libgcc, libstdc++, libgomp): GPL-3.0 with the GCC Runtime
  Library Exception.

The notices name the exact MSYS2 source packages
(`https://repo.msys2.org/mingw/sources/`). Whoever publishes a release should
keep those sources available on request and review this summary with their
own legal advisor; it is not legal advice.

## Build the runtime locally

```bash
python -m pip install "zstandard>=0.23,<1"
python tools/prepare_windows_ocr_runtime.py fetch --out bundled_ocr/windows-x64
```

Then build the Windows app from the repository root (Windows, with the Flet
build prerequisites):

```powershell
flet build windows . --module-name app --python-version 3.12 `
  --product "Statistical Research Assistant" --artifact "StatisticalResearchAssistant" --yes
python tools/check_packaged_ocr.py build/windows
```

`flet build windows` packages the whole application folder, including
`bundled_ocr/`, which the resolver finds next to `ocr_runtime.py` at run
time. This was chosen over `flet pack --onedir` because it is the build the
project already ships, keeps native binaries as ordinary files (no
self-extracting one-file archive) and lets the runtime be verified inside
the produced package.

## Refreshing the pinned versions

```bash
python -m pip install zstandard pefile
python tools/prepare_windows_ocr_runtime.py lock
git diff packaging/windows_ocr_runtime.lock.json
```

Review new versions, licences and the DLL list in the diff before committing.
MSYS2 occasionally removes very old packages from its mirrors; if a pinned
file disappears, CI fails with a download/hash error and the lock must be
refreshed. The CI cache keyed on the lock hash avoids repeated downloads.

## CI verification (`.github/workflows/windows-package.yml`)

1. Fetch and verify the pinned runtime.
2. Run `tesseract.exe --version` and `--list-langs` with `PATH` reduced to
   Windows system folders, so a missing bundled DLL fails immediately.
3. Run the real-engine regression tests (`SRA_REQUIRE_REAL_OCR=1`) against
   the bundle.
4. `flet build windows`, then `tools/check_packaged_ocr.py`: find the runtime
   inside the produced package, verify every file's SHA-256 and run the OCR
   self-test from the packaged code.
5. Launch the built `StatisticalResearchAssistant.exe` with
   `SRA_OCR_SELFTEST=<result.json>` and a system-only `PATH`. The packaged app
   OCRs a generated scanned questionnaire with the bundled engine, writes a
   JSON verdict (must report `"origin": "bundled"`) and exits.
6. Upload `StatisticalResearchAssistant-Windows-x64.zip` and the self-test
   result as an artifact.

## Self-test for support

From a source checkout: `python ocr_selftest.py result.json`. In a packaged
build: set `SRA_OCR_SELFTEST=C:\path\result.json` and start the executable;
it exits after writing the result. No user documents are read.
