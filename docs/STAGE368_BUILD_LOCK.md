# Stage 36.8 — Build lock: versions, hashes, sources, licences

Issue #62, P0 "reproducible runtime and secure release". This document lists exactly what the Windows program is built from, how each input is pinned and checked, what a build records about itself, and what is still not pinned. Every number below comes from a file in the repository or from a CI run named here.

"MiB" = 1,048,576 bytes.

## 1. The problem that was fixed

| Before Stage 36.8 | Evidence |
|---|---|
| `requirements.txt` held ranges (`flet>=1.0,<2`, `pandas>=2.2,<4`, …). Every build resolved them anew. | `requirements.txt` at ac02e73 |
| The browser checks ran **Flet 1.0.5**. `flet-web==1.0.5` on the same pip command downgraded flet. | Run 42686880646, job workspace-screenshots: `Successfully installed … flet-1.0.5 flet-web-1.0.5` |
| The Windows program embedded **Flet 1.1.2**. | Run 42686880304: `Installing flet-cli 1.1.2 package... Installing Flutter 3.47.9...` |
| `flet build` downloaded the following without any checksum, and a different version could arrive without anyone noticing: flet-cli (unpinned dependencies), the Flutter SDK, the build template, the Python version table and the Dart packages of the app shell (caret ranges). | flet-cli 1.1.2 source: `flet/utils/pip.py`, `flet_cli/utils/flutter.py`, `flet_cli/utils/python_versions.py`; template `pubspec.yaml` |
| `setup-python` asked for "3.12" and got 3.12.10 on Windows and 3.12.16 on Linux, by chance of the runner image. | Run logs of 2026-11-09 |
| Inno Setup was whatever the runner had, or the latest Chocolatey package. | `windows-installer.yml` at ac02e73 |

## 2. What is pinned now

### 2.1 Python packages (bundled)

- `requirements.in`: the supported ranges (human-maintained). flet is exact: `flet==1.1.2`.
- `requirements.txt`: the **lock**.
  - It is a universal `uv pip compile` resolution with `--generate-hashes`, made as of `--exclude-newer 2026-11-09T19:00:00Z`.
  - It pins 49 packages, each with the SHA-256 of every published file.
  - These are **the same 49 versions** that the green CI runs of 2026-11-09 installed (compared line by line), so no version was changed to make the lock.
- `flet build windows` installs this file in pip's hash-checking mode. flet-cli 1.1.2 supports it: "A file with hashes is only checked".

| Package | Version | | Package | Version |
|---|---|---|---|---|
| flet | 1.1.2 | | numpy | 2.5.4 |
| pandas | 3.1.1 | | scipy | 1.18.1 |
| statsmodels | 0.15.0 | | matplotlib | 3.11.2 |
| python-docx | 1.2.0 | | openpyxl | 3.1.5 |
| pypdf | 6.21.4 | | pypdfium2 (PDFium) | 5.15.2 |
| Pillow | 12.3.0 | | pingouin | 0.7.0 |
| scikit-learn | 1.9.1 | | seaborn | 0.13.2 |
| xarray | 2026.9.0 | | cryptography | 50.0.2 |
| lxml | 6.1.3 | | threadpoolctl | 3.8.0 |

The remaining 31 are transitive dependencies; all of them are in `requirements.txt`.

### 2.2 Build and test tools (never bundled)

`requirements-dev.in` → `requirements-dev.txt`: 58 packages with hashes, resolved against the runtime lock, so shared packages have one version (tested). It contains:
- flet-cli 1.1.2, preinstalled so that `flet build` no longer downloads its own;
- flet-web 1.1.2, so the browser checks run the client the program embeds;
- zstandard 0.25.0;
- pywinauto 0.6.9 (Windows only).

`pyproject.toml` excludes `requirements.in`, `requirements-dev.in` and `requirements-dev.txt` from the bundle.

### 2.3 Toolchain (`packaging/build_toolchain.lock.json`)

| Component | Version / identity | Source | SHA-256 | Checked by |
|---|---|---|---|---|
| Embedded CPython (runs the program) | 3.12.16 (standalone build 20261026) | flet-dev/python-build release 20261027, chosen by flet-cli 1.1.2 / serious_python 6.1.3 | python-build manifest `2a11018e…beaf3b` (`packaging/python-build-manifest.json`, given to flet build via `FLET_PYTHON_BUILD_MANIFEST`) | packaged self-tests report `"python": "3.12.16"` |
| Host Python, Windows | 3.12.10 (the newest 3.12 `actions/setup-python` offers for Windows) | actions/python-versions | — | `identity`; `tests/test_build_lock.py` (every Windows job) |
| Host Python, Linux | 3.12.16 | actions/python-versions | — | `tests/test_build_lock.py` (every Linux job) |
| Flet (Python), flet-cli, flet-web | 1.1.2 | PyPI | in the locks | `identity`; lock tests |
| Flutter SDK | 3.47.9 stable, framework `c197ca5199e9ee5661e865596c9c07294dfab51c`, Dart 3.13.7 | `storage.googleapis.com/flutter_infra_release/…/flutter_windows_3.47.9-stable.zip` | `d8e2b5977e09082c6440f89dc1aa887b94c8fbcc3b39222797046295a3f68a9e` (= Flutter's own `releases_windows.json`) | `tools/build_toolchain.py flutter` before the build; `identity` reads the SDK the app shell was built with (`.dart_tool/package_config.json`) and its revision |
| flet build template | 1.1.2 | `github.com/flet-dev/flet/releases/download/v1.1.2/flet-build-template.zip` | `ccd6ecabc2afbe14343be3bc51bb4b012672add25e0378be18758f9ddd4ca643` | `tools/build_toolchain.py template`; passed as `flet build --template` |
| Dart packages of the app shell | 142 packages, 138 hosted with their pub SHA-256 (flet 1.1.2, serious_python 6.1.3, window_manager 0.5.2, path_provider 2.1.6, …) | pub.dev | `packaging/flutter/pubspec.lock` (file SHA-256 `3a9dc27c…8d2ad3`) | Put into the template, so `flutter pub get` keeps these versions. `identity --strict` fails on any drift. |
| Tesseract OCR | 5.5.4-1 (MSYS2 UCRT64) | repo.msys2.org (mirror.msys2.org) | `packaging/windows_ocr_runtime.lock.json`: 53 packages, 38 used, 92 files, each with SHA-256; `tesseract.exe` `1038246a…e673f4` | `tools/prepare_windows_ocr_runtime.py fetch`; `check_packaged_ocr.py` (bundle integrity) |
| Language models | tessdata_fast 4.1.0-3: eng `7d4322bd…70b2`, lav `7d9eaf22…8847`, rus `e16e5e03…e225`, osd `9cf5d576…00ff` | MSYS2 packages tesseract-data-* | in the OCR lock | packaged OCR self-test: `languages: eng, lav, osd, rus`, `bundle integrity verified` |
| Inno Setup | 6.7.1 | the runner image, else Chocolatey `innosetup --version=6.7.1` | Chocolatey checks its package checksum | `tools/build_toolchain.py iscc` (fails on another version); `identity --iscc` |
| Visual Studio / MSVC, Windows SDK, CMake | recorded, **not pinned**: windows-2025-vs2026 20261103.298.1 (VS Enterprise 2026 18.11.12328.437, CMake 4.4.5) | the GitHub runner image | — | `identity` records the image (`ImageOS`, `ImageVersion`) |

### 2.4 How CI uses the lock

- Every job sets up the exact Python of the lock. Every `pip install` is `--require-hashes` from `requirements.txt` and `requirements-dev.txt` only. The single exception is the PyInstaller variant of the packaging experiment (not a release input). `tests/test_build_lock.py` asserts all of this for every workflow.
- Every Windows build uses `.github/actions/pinned-windows-toolchain`, which does, in order:
  1. sets up the exact host Python;
  2. installs both hashed locks;
  3. installs the Flutter SDK from its verified archive, at the place flet-cli looks for it;
  4. prepares the verified template with the Dart lock;
  5. supplies the pinned Python version table.

  After that, `flet build` downloads none of these.
- `tools/build_toolchain.py identity` writes `build-identity.json` with each build. It checks against the locks:
  - the host Python and every host package;
  - flet and flet-cli;
  - the Flutter SDK the app shell was built with, and its revision;
  - the template;
  - the Dart resolution;
  - every Python package inside the bundle.

  It is `--strict` (a deviation fails the build) in the bundle, installer and release workflows.
- `tools/build_sbom.py` writes a CycloneDX 1.5 SBOM with each build. `release.yml` attaches it to the draft release.

### 2.5 Updating the lock (owner or maintainer)

1. Edit `requirements.in`, or `requirements-dev.in`.
2. Regenerate:
   - `uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --exclude-newer <UTC time> -o requirements.txt`
   - then `uv pip compile requirements-dev.in -c requirements.txt …`, with the same options, into `requirements-dev.txt`.
3. A new flet release changes flet, flet-cli and flet-web together. It also changes the template URL and its SHA-256, the Flutter version, archive SHA-256 and revision, the python-build manifest, and `packaging/flutter/pubspec.lock`, which is taken from the first build's `diagnostics/flutter-pubspec.lock` after review.
4. Review the diff: versions, licences (`diagnostics/licenses.md`), size report. Then run the full CI, including the reproducibility workflow.

## 3. Clean Windows build verification (issue #62, items 1–9)

First pinned build: run **43418623124** on dff65c8. The pull-request merge commit 0c0263c has the same tree, because the RC branch contains its base. Clean `windows-latest` runner.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | All dependencies resolve | done | hashed install of both locks succeeded |
| 2 | No unexpected build-time upgrades | done | `build-identity.json`: bundled packages 49/49 equal to the lock, 0 missing, 0 extra, 0 changed; flet build installed no flet-cli and no Flutter of its own (no such lines in the log); Flutter archive SHA-256 verified; Flutter 3.47.9 at revision c197ca5 used by the app shell. The only host-side extra was pipx (+4 dependencies) preinstalled in the runner's Python; it never enters the bundle and is now listed as a host tool |
| 3 | The bundled OCR engine is usable | done | packaged OCR self-test: `ok`, `origin: bundled`, tesseract 5.5.4, `bundle_verified: true` |
| 4 | English, Latvian and Russian data present | done | same self-test: `languages: eng, lav, osd, rus`, `missing_languages: []` |
| 5 | Statistical functions numerically equivalent | done | packaged analysis self-test: report hashes equal to the source checkout's (`analysis_selftest.py --compare`) |
| 6 | Starts without system Python | done | GUI startup with `PATH` reduced to System32: Home shown, no black window |
| 7 | Works without preinstalled Tesseract | done | same startup and OCR self-test with no Tesseract on PATH and `TESSERACT_CMD`/`TESSDATA_PREFIX` removed |
| 8 | Existing projects and databases migrate safely | see installer run | the installer workflow's legacy-migration and reopen journeys (`docs/STAGE368_REAL_USER_ACCEPTANCE.md`) |
| 9 | No development-only material or duplicates | done, with known duplicates | package audit: 0 test suites, 0 headers/stubs, 0 developer files in the bundle; identical copies: `msvcp140.dll` ×3 (1.1 MiB, loaded by private path, deduplication unsafe), shared licence texts (0.3 MiB, intentional) |

### Sizes against earlier measurements

| Measurement | Before | This RC (run 43418623124) |
|---|---|---|
| Installed application folder | 376.3 MiB (Stage 34 distribution audit); 389.7 MiB (Stage 36, run 42686880239) | 389.9 MiB, 408,808,738 B, 6,847 files |
| Sum of per-file deflate sizes | 145.8 MiB (Stage 34) | 150.9 MiB |
| Downloaded ZIP of the portable preview | 149.3 MiB (Stage 34) | 154.6 MiB (162,103,942 B) |
| Python packages / OCR / Flutter / Python runtime (installed) | — | 267.4 / 50.3 / 41.0 / 26.6 MiB |

The growth since Stage 34 is the Stage 35–36 features, not the lock: the lock pins the same versions the Stage 36 builds used. No dependency was removed to save space. Removing pingouin would be a licensing decision, not a size one (§5).

## 4. Reproducibility: two clean runners, one commit

`windows-reproducibility.yml` builds the same commit on two fresh runners with the pinned toolchain. It compares every file of the bundle and of the installed program by SHA-256, classifies each deviation, and compares the installers.

Results: *pending — filled in from run 43418623260 and the run on the final commit.*

## 5. Licences

The SBOM (`diagnostics/sbom.cdx.json` of every build) has 228 components: 49 Python packages, the embedded CPython, Flutter, the template, 138 Dart packages and 38 MSYS2 packages. Licence metadata of the Python packages is read from the installed distributions (`License-Expression` first). For five packages whose metadata has only a classifier or the full text, it is read from the licence file each wheel ships (`tools/build_sbom.py`). Dart packages carry their licences in the program's `data/flutter_assets/NOTICES.Z`, which Flutter generates.

### 5.1 Copyleft terms found (13 components)

| Component | Licence | Where it runs | What it requires before a public release |
|---|---|---|---|
| **pingouin 0.7.0** | **GPL-3.0** | imported **in the program's own process** (`reliability.py`, Cronbach's α and its Feldt interval) | **Owner decision (P0 blocker for a public release).** The repository has **no LICENSE file**, so no licence to the program itself is granted. Distributing it with a GPL-3.0 library imported into the same process makes the combined work subject to GPL-3.0. Two ways out: (a) the owner licenses Statistical Research Assistant under GPL-3.0-or-later (all other components are compatible) and ships the source; or (b) α and the Feldt interval are computed in-house, verified against pingouin in the tests (pingouin moves to the build/test lock), and pingouin leaves the bundle. Option (b) is a change to a validated numerical path; it needs an oracle comparison to 1e-12 and the owner's go-ahead. Not done in this RC. |
| jbigkit 2.1 | GPL-2.0-or-later | `libjbig` DLL loaded by libtiff inside `tesseract.exe`, a separate process the program starts | Ship the licence text (done: `bundled_ocr/…/licenses/`, `THIRD_PARTY_NOTICES.txt`). Offer the corresponding source: attach the pinned MSYS2 source packages (or a written offer) to each public release. Not yet attached; release checklist item |
| libiconv, gettext-runtime (libintl), libunistring, libidn2 | LGPL-2.1+/LGPL-3.0+ (or dual with GPL) | DLLs of the OCR engine | Licence texts shipped (done). Source available (same as above). DLLs are replaceable separate files (done) |
| libgcc, libstdc++, libgomp | GPL-3.0+ WITH GCC Runtime Library Exception 3.1 | DLLs of the OCR engine | The exception permits distribution with the compiled program; licence texts shipped |
| xz, lz4, zstd | permissive library licences (0BSD, BSD); the GPL terms cover their command-line tools, which are not shipped | DLLs | licence texts shipped |
| certifi | MPL-2.0 (file-level) | bundled CA list, unmodified | notice shipped in its dist-info |

Everything else is permissive (MIT, BSD, Apache-2.0, PSF, MIT-CMU, Zlib, CC0). Packages the OCR lock lists but does not ship (ICU, GnuTLS, nettle, …) are not in the program. The full table is in each build's `diagnostics/licenses.md`.

### 5.2 The project's own licence

There is no `LICENSE` file. Before any public distribution the owner must choose one. That choice also settles the pingouin question above. This RC does not add a licence: it is the owner's decision.

## 6. Supported operating systems and architectures

| Target | Status |
|---|---|
| Windows 11 and Windows 10 (64-bit, x64) | the product target. CI evidence on Windows Server 2025 (10.0.26100) only; Flutter 3.47 requires Windows 10 or later; the OCR runtime is UCRT x64 (UCRT is part of Windows 10+) |
| Windows on Arm | not built, not tested (x64 emulation may work; unverified) |
| 32-bit Windows, Windows 8.1 or older | not supported |
| Linux, macOS | source checkout for development and the Linux test suite only; not a distributed product |

## 7. Known limitations of the lock

- The runner image (Visual Studio, Windows SDK, CMake) is recorded per build, not pinned. GitHub updates it weekly. The reproducibility comparison (§4) shows what such a change can alter.
- The embedded CPython archive is fetched by serious_python inside `flutter build`. Its version is fixed by the pinned serious_python 6.1.3 and the pinned python-build manifest. The downloaded bytes are not checked by a hash before use. The resulting `python312.dll`/`python3.dll` hashes are recorded in every `build-identity.json` and compared between builds.
- `pip` itself (24.x in the toolcache Python) and the runner's preinstalled pipx are not pinned. They install nothing into the bundle.
- The update-signing key and the code-signing certificate are owner-supplied secrets and are not part of the lock (`docs/STAGE368_RELEASE_CHECKLIST.md`).
