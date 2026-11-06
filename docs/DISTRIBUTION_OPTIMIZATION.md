# Windows distribution — measured audit and optimisation (Stage 34, issue #23)

Every number below comes from a real CI build that was downloaded and taken
apart with `tools/package_audit.py`; nothing is estimated from package lists.
"MiB" = 1,048,576 bytes.

## 1. Before / after

| | Before: PR #21 `266f401` (artifact 13488263838) | After: PR #25 `470a47d` (artifact 13489971859) | Change |
|---|---:|---:|---:|
| Download (CI artifact) | 194,566,155 B (185.6 MiB) — a ZIP containing another ZIP | 156,586,364 B (149.3 MiB) — one ZIP of the application folder | **−37,979,791 B (−19.5 %)** |
| Installed (extracted) | 495,313,140 B (472.4 MiB) | 394,614,701 B (376.3 MiB) | **−100,698,439 B (−20.3 %)** |
| Files | 10,736 | 6,617 | −4,119 |
| Packaged analysis self-test | — | 18/18 procedures, report SHA-256 identical to the source checkout | |
| Packaged OCR self-test | passed | passed (Tesseract 5.5.4, eng/lav/osd/rus, bundle verified) | |
| GUI start (one run each, different runners) | window 1.50 s, ready 3.14 s (classic) / 3.04 s (workspace) | window 2.00 s, ready 3.59 s / 3.69 s | not comparable, see §4 |

The same comparison built on **one runner** (experiments run 42200307088:
*before* = this PR's base commit `266f401`, *after* = its head) gives the same
result: installed 495,005,439 B (472.1 MiB, 10,735 files) → 394,611,220 B
(376.3 MiB, 6,616 files), **−20.3 %**; sum of per-file deflate sizes
180.7 → 145.8 MiB, **−19.3 %**.

Per component (installed MiB; compressed MiB in brackets):

| Component | Before | After | What changed |
|---|---:|---:|---|
| Python packages | 349.4 (132.5) | 255.9 (96.3) | package test suites, `.lib`/`.pxi`, Pillow AVIF removed |
| Bundled OCR | 50.3 (22.1) | 50.3 (21.5) | unchanged¹ |
| Flutter engine and UI | 40.9 (17.0) | 40.9 (16.5) | unchanged¹ |
| Python runtime | 26.6 (10.7) | 26.6 (10.4) | unchanged¹ |
| Application | 4.3 (2.7) | 1.8 (0.8) | repository tests/tools/docs/README no longer copied |
| C++ runtime | 0.8 (0.3) | 0.8 (0.3) | unchanged |

¹ "Before" compressed sizes are the entries of the PowerShell ZIP; "after" is
deflate level 9 (the artifact's compression). Unchanged components differ by
that compressor difference only.

Largest packages after the change (compressed / installed MiB): scipy 31.7 / 87.0,
numpy 10.3 / 31.3, matplotlib 9.4 / 20.7, pandas 8.4 / 23.3, statsmodels 7.2 / 22.3,
scikit-learn 7.2 / 19.3, pypdfium2 3.7 / 7.6, lxml 3.5 / 6.9, Pillow 2.9 / 6.7.

## 2. How it is measured (reproducible)

```
python tools/package_audit.py <build folder | distributed ZIP | CI artifact ZIP> \
    --json size.json --markdown size.md
```

- Reads all three layers (artifact wrapper, distributed ZIP, extracted files),
  hashes every file (SHA-256), groups files into components and into
  distributions using the installed `RECORD` files, lists identical copies and
  the largest files.
- A removal candidate's *ZIP saving* is the sum of its entries' compressed
  sizes plus their ZIP headers; a unit test checks that this equals the real
  size difference of two archives built with and without the files.
- Every Windows build now writes this report into the job summary and fails
  above the budgets **installed ≤ 400 MiB, ZIP ≤ 160 MiB**
  (`.github/workflows/windows-package.yml`).

## 3. What was removed and why it is safe

| Removed (via Flet's own options in `pyproject.toml`) | Files | Installed | ZIP |
|---|---:|---:|---:|
| `tests`/`test` folders inside installed packages (`[tool.flet.cleanup] package_files`) | 3,831 | 84.7 MiB | 29.9 MiB |
| Pillow AVIF codec `PIL/_avif.*` | 1 | 7.5 MiB | 4.2 MiB |
| Repository tests, tools, docs (with screenshots), packaging, README/ROADMAP (`[tool.flet.app] exclude`) | 98 | 2.6 MiB | 1.9 MiB |
| Import libraries `.lib`, Cython includes `.pxi` | 190 | 1.2 MiB | 0.4 MiB |

Kept on purpose: the bundled OCR runtime with its manifest, notices and
licences; the example datasets; the `testing` modules that libraries import at
runtime (`numpy.testing`, `pandas._testing`, `xarray.testing`,
`sklearn.utils._testing`); every `dist-info` (version lookups).

Evidence that nothing needed was removed:
1. **`pruned-runtime` CI job (Linux):** `tools/prune_packages.py` applies exactly the
   same globs (serious_python defaults + `pyproject.toml`) to the interpreter,
   then the complete test suite runs with real OCR required, and the analysis
   self-test must give the same report hashes as before pruning. Green on PR #25.
2. **Packaged analysis self-test (Windows):** `analysis_selftest.py` runs every
   statistical procedure (descriptives, exploration, α, ω, bootstrap ω, EFA,
   correlation matrix, correlation, regression, Mann–Whitney, Welch, paired,
   repeated measures, χ², omnibus, post-hoc, logistic regression, ANCOVA), their
   charts, the APA figure, Word and XLSX export and the survey database
   **inside the packaged exe** (`SRA_ANALYSIS_SELFTEST`); CI fails unless every
   report SHA-256 equals the source checkout's. 18/18 identical on PR #25.
3. Existing packaged OCR self-test and both GUI startup checks still pass.

## 4. Startup — measured on one runner

Single launches on different runners vary more than any packaging effect:
recent builds of essentially the same code reported "interface ready" between
**3.0 s and 3.9 s** (PR #21: 3.03–3.16 s; PR #22: 3.71 s; PR #15: 3.9 s; PR #25:
3.59–3.69 s), and window visibility is sampled only every 0.5 s. Startup is
therefore compared only within one job, where
`.github/workflows/windows-packaging-experiments.yml` builds the variants and
launches them alternately five times each (`tools/startup_ab.py`); the first
launch is reported separately as the cold start.

**Removing unused files does not change startup.** Run 42191629552 (commit
`0c30f5a`, one Windows runner) compared the pre-Stage-34 package contents with
the cleaned contents, built from the same source:

| Build | Launches OK | Cold: window / ready | Warm median: window / ready | Warm range ready |
|---|---:|---:|---:|---:|
| without the cleanup | 5/5 | 2.00 s / 3.86 s | 2.01 s / 3.94 s | 3.87–3.99 s |
| with the cleanup | 5/5 | 2.02 s / 3.85 s | 2.01 s / 3.92 s | 3.88–3.97 s |

The difference (0.02 s) is inside the spread of either build; as expected,
files that are never opened cost no time. The size gain of §1 is therefore
the whole benefit of the cleanup. (The size report of that run is not used:
its second build packaged the first one's output folder, which the workflow
now keeps outside the source tree.)

**Where the time goes.** The application records its own timeline (median of
the five warm launches, cleaned build):

| Phase | Reached at | Step |
|---|---:|---:|
| Flet imported | 0.07 s | 0.07 s |
| Window connected | 0.36 s | 0.29 s |
| Startup screen shown | 0.41 s | 0.05 s |
| Interface module imported (`research_app`) | 3.38 s | **2.97 s** |
| Preferences, controls and workspaces built | 3.70 s | 0.32 s |
| Interface ready | 3.91 s | 0.21 s |

Three quarters of the time to a usable window is spent importing the
statistics stack that `research_app` loads at start, while the startup screen
is already visible. `python -X importtime -c "import research_app"` (Linux,
warm cache, 1.70–1.88 s in total) attributes it to `reliability` → pingouin
0.68 s (pingouin imports scikit-learn, seaborn and xarray), the statsmodels
modules used by `omega_analysis`/`regression_analysis` about 0.3 s once
pingouin is gone, matplotlib through `apa_figures` 0.26–0.29 s and pandas
0.20–0.25 s.

This PR moves the pingouin import into `reliability.analyze_cronbach`, the
only place that uses it: the same function computes the same alpha (checked
in `test_pingouin_is_imported_only_when_an_alpha_is_calculated`), and
scikit-learn, seaborn and xarray are no longer loaded at start. Locally that
alone saves only about 0.2 s, because statsmodels and SciPy are still loaded
by other analysis modules.

**This PR as a whole, measured on one runner** (run 42200307088: *before* =
base commit `266f401`, *after* = head `4e3cb90`, five alternating launches
each, all fifteen successful):

| Build | Cold: window / ready | Warm median: window / ready | Warm range ready | Interface module imported (median) |
|---|---:|---:|---:|---:|
| before | 1.52 s / 2.60 s | 1.01 s / 2.52 s | 2.43–2.61 s | 2.19 s |
| after | 1.51 s / 2.78 s | 1.02 s / **2.40 s** | 2.36–2.51 s | **2.04 s** |

Warm starts are 0.12 s faster, the same as the shorter import phase
(−0.15 s), i.e. the deferred pingouin import; the window appears at the same
time. The single cold launch of each build is within that spread and is not
read as a difference. This runner was faster than the one above (2.5 s
instead of 3.9 s for the same builds): runner-to-runner differences are much
larger than any effect measured here, which is why only same-runner numbers
are compared.

The larger, still unmeasured opportunity is to load the whole analysis stack
after the interface is shown (statsmodels, SciPy, matplotlib; together most
of the import phase, 2.0–3.0 s depending on the runner), with each analysis
waiting for it on first use. That changes the import structure of the classic
interface and is proposed as its own pull request with a same-runner
before/after measurement, not as part of this one.

## 5. Distribution and download

- **Done:** the CI artifact is the application folder itself (one extraction,
  no nested ZIP), compressed at level 9; diagnostics are a separate artifact;
  the job summary shows the artifact URL and the SHA-256 of the downloaded ZIP.
- **Recommended next (needs the owner):** versioned GitHub Releases instead of
  14-day CI artifacts — one ZIP per version plus `SHA256SUMS.txt`; later a
  signed per-user installer (Inno Setup or MSIX) that installs to
  `%LOCALAPPDATA%\Programs`, adds a Start Menu entry and a clean uninstaller,
  and keeps projects and questionnaires in the user data folder (already the
  case for packaged builds). Updates: an explicit "check for updates" that only
  downloads a signed release; no silent auto-update.

## 6. Further reductions — measured, not applied

| Option | ZIP saving | Installed | Cost / risk | Decision needed |
|---|---:|---:|---|---|
| Replace pingouin (used only for `cronbach_alpha`) with an in-house α verified against pingouin in tests; drops pingouin, scikit-learn, xarray, seaborn, joblib, tabulate, pandas_flavor | 9.7 MiB | 26.0 MiB | touches the calculation engine; α and Feldt CI must stay bit-identical | owner |
| Drop `osd.traineddata` (the app always runs `--psm 6`; rotation is chosen by the researcher) | 4.1 MiB | 10.6 MB | changes the pinned OCR lock and bundle manifest | owner |
| Optional OCR module (scanned PDFs, Latvian/Russian OCR) downloaded on request | 21.5 MiB | 50.3 MiB | needs signed, hash-pinned module packages, offline module files for restricted networks, and the full installer kept | owner |
| Identical DLL copies (`msvcp140` in numpy/pandas/scikit-learn) | ≈1.1 MiB | 1.1 MiB | delvewheel loads them by private path; deduplication is unsafe | no |

Fixed costs that stay with any Flet build: Flutter engine and UI 16.5 MiB,
Python runtime 10.4 MiB (compressed).

## 7. Modular core with application-managed modules (design)

- **Core** (always): interface, data import, every statistical procedure, Word
  export, questionnaires; works fully offline.
- **Modules** (optional, explicit "Install" button with size and source): OCR
  engine + language packs; later, rarely used heavy features.
- Module packages are versioned ZIPs listed in a manifest **built into the
  application** (URL, size, SHA-256, signature). The app downloads only on
  request, verifies hash and signature before unpacking (same safe-extraction
  rules as project backups), installs into the user data folder and never
  executes code from anywhere else. A module file can also be installed from
  disk ("Install from file…") for PCs without internet.
- The **complete offline package** (core + all modules) stays available for
  every release; users never install Python or Tesseract themselves.
- Worth doing only if download size matters more than one extra step: the
  measured saving is 21.5 MiB (14 % of the current download) for OCR.

## 8. Packaging alternatives

| Variant | Status |
|---|---|
| `flet build windows` (current) | measured above |
| `flet pack --onedir` (PyInstaller, officially documented by Flet) | **Measured, not recommended.** `flet pack` fails on Windows with flet-cli 1.0.5 and 1.1.0: after updating the executable's version resource it restores the overlay with `open(exe_path, "ab", encoding="utf-8")`, and binary mode takes no encoding (`ValueError`). With `tools/flet_pack_compat.py` (the unchanged CLI with that one call fixed) it builds, and its packaged analysis self-test reproduces every report hash. Run 42200307088, same runner: installed 368,703,287 B (351.6 MiB, 1,774 files) but **185.6 MiB** of compressed data against 145.8 MiB for `flet build` (its Flet client is an already-compressed 33.6 MiB archive, unpacked again on first start), and slower: startup screen after 1.25 s instead of 0.26 s, ready after 3.48 s instead of 2.40 s (warm medians; cold 4.59 s). It would also depend on the workaround or an upstream fix. |
| Nuitka, Briefcase | not evaluated: not part of Flet's supported packaging; would need a separate Flutter client strategy |

## 9. Server option (study)

| Criterion | Local desktop app (current) | Browser front-end + server calculations |
|---|---|---|
| Download | ~150 MiB once | none (browser) |
| Cost / latency | none / local CPU | hosting, scaling and monitoring costs; network round trips per analysis |
| GDPR / research privacy | data never leaves the PC | personal research data on a server: legal basis, DPA, EU hosting, retention, breach duties, ethics approvals must cover it |
| Offline | full | none |

Conclusion: keep calculations local by default. A server could only be an
explicitly opted-in product (e.g. for respondents' web forms, Stage 33 §13),
never a silent upload or a "streamed DLL".

## 10. Open checks on a real PC

Cold start with Windows Defender real-time scanning, 100/125/150 % DPI,
Narrator/NVDA, offline launch, all 15 analyses and the scientific importer on
the downloaded artifact.
