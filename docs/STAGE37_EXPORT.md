# Stage 37.1 — Export and interoperability (Issue #67)

Branch `claude/stage37-export`, from `stage37/master-acceptance-interoperability-spec` (`2f9af71`). Scope: `docs/STAGE37_NEXT_SPEC.md` §2, plus the independent review's findings D8, M2, H2 and its `.sav` requirements (`docs/STAGE37_FABLE_NARROW_REVIEW.md` on `claude/stage37-review`). Synthetic data only: the 180-case master fixture (`tests/fixtures/stage37/generate_master_fixture.py`, generated into a temporary folder by every test) and invented adversarial values.

An item is **done** only when a named test proves it (§9). The Windows journey `export-data` is written and walked in the harness; it has **not** run on Windows in this branch (§8).

## 1. What the researcher sees

One **Export** card on each of three pages. It holds a format (the last one used is remembered), one button that opens the system's Save dialog, and *Advanced options*, folded away.

| Page | Formats (default first) | Default output |
|---|---|---|
| Data | `.xlsx` with codebook · `.sav` · `.csv` · bundle `.zip` | a lossless copy of the data: sheets Data, Codebook, Scales. No report is needed. |
| Results | results `.xlsx` · bundle `.zip` | every result; *Advanced*: all, the one on screen, or those in the report |
| Reports | bundle `.zip` · results `.xlsx` | data, codebook, results, the Word report as composed, figures, manifest |

- **Two actions at most.** With the remembered format, a click on the button opens the Save dialog. Choosing another format first is the second action.
- **Remembered.** The format per page, the CSV separator and the byte-order mark are kept in `preferences.json` under `"export"` (`app_preferences.export_preferences`, `remember_export`). `save_preferences`, which the classic interface also uses, now keeps keys it does not manage, so a language change there no longer drops them.
- **Before saving**, the card shows:
  - for `.sav`, what the format cannot hold, and every renamed, cut or converted field (see §3.3);
  - for `.csv`, the formula protection (§5.1);
  - for every row-level export, the columns that may identify participants (§5.4), with *Nothing is uploaded: the file is written only where you choose.*
- **After saving**, the card and the status line name the full path and what was checked, for example *Saved and checked: …\synthetic_master_research_n180.xlsx. Re-opened with an independent reader: 180 rows, 98 variables (xlsx (zip)).*
- **Progress.** Large tables are written row by row (openpyxl write-only mode, CSV row writer). The status line shows *Writing row 50,000 of 100,000…*, at most every 0.5 s.
- **Languages.** Every text is in EN/LV/RU (`workspace_text.T`, 71 keys under `export.*` and `data.opt.user_missing*`). LV and RU are drafts for native review. In Latvian or Russian the CSV separator starts as the semicolon (§3.2).

Data keys: `export-{data|results|reports}`, `export-format-…`, `export-save-…`, `export-advanced-…`, `export-feedback-…`, `export-section-{name}`, `export-csv-layout`, `export-csv-bom`, `export-scope`, `export-bundle-report`, `export-sav-limits`, `export-sav-changes`, `export-csv-note`, `export-sensitive`, `export-blocked-…`; on the Data page `data-opt-user-missing` and `label-{variable}`. No existing key or text was changed.

Code:
- `data_export.py`: formats, codebook, SPSS names, verification, atomic save, participant check. No Flet.
- `export_bundle.py`: codebook from the session and the project, results workbook, provenance, manifest, R syntax, bundle. No Flet.
- `workspace_export.py`: the card.
- `csv_safety.py`: the formula rule, shared with the importer.

## 2. Formats: what each carries and what it loses

### 2.1 `.xlsx` (openpyxl 3.1.5, write-only)

Sheets, each selectable under *Advanced*:

- **Data**: one row per case, the header in row 1 (frozen).
- **Codebook**: one row per variable (columns in §4), then the derived-variable history.
- **Scales**: questionnaire scales, scores made in Data → Prepare, groups made from a scale; the reverse-keyed variables.
- **Results**: an overview, then one sheet per analysis (§2.4).
- **Provenance**: the export's identity (program version, time, dataset, rows, variables, dataset SHA-256) and one row per result.

| Value | Written as | Read back (openpyxl) |
|---|---|---|
| number | a number. A whole number below 2⁵³ as an integer | the same number; whole numbers as `int` |
| a number that needs 17 significant digits (`0.1 + 0.2`) | openpyxl writes 16 | within 1e-15 relative. Every value of the fixture is exact |
| ±∞, an integer above 2⁵³ | text (a spreadsheet cannot hold them) | text, counted in the export facts |
| date, date-time, time | a spreadsheet date with its format | `datetime` (a date at midnight), `time` |
| date-time with a time zone | ISO text with the offset | text |
| text, including `001`, `=1+1`, `@x` | a text cell: `data_type = "s"`, an inline string. **Never a formula**: the sheet XML has no `<f>` element | the same text |
| empty text `""` | a text cell with no characters (`t="inlineStr"`) | `None` with `data_type "inlineStr"`. A missing value has no cell at all (`data_type "n"`): the two stay distinct |
| missing (NaN, None, NaT) | no cell | `None` |
| user-missing code (−9, DK) | the code itself, never blanked; listed in the Codebook | the code |
| category | its label as text; the order is in the Codebook | text |
| control characters XML cannot hold | U+FFFD, counted | — |
| text over 32,767 characters | cut (the Excel limit), counted | — |

More than 1,048,575 rows do not fit in one worksheet. The export says so and writes nothing.

### 2.2 `.csv` (UTF-8)

| Property | Rule |
|---|---|
| Layout | **comma** (`,` and a decimal point), or **semicolon** (`;` and a decimal comma). Excel set to Latvian or Russian opens the semicolon file in columns (review H2). Default: comma in English, semicolon in Latvian and Russian; the choice is remembered |
| Byte-order mark | on by default (Excel then shows ā, č and ж); can be switched off |
| Numbers | unquoted. Whole numbers without a decimal point; other numbers with every digit Python needs to read the same double back (`repr`). In the semicolon layout, a decimal comma |
| Texts | always quoted (`csv.QUOTE_STRINGS`). `""` is an empty text; an unquoted empty field is a missing value |
| Formula protection | §5.1 |
| Codebook | written next to the file as `<name>_codebook.json`, with the CSV's SHA-256, layout, decimal mark and the protection rule |

Lost or changed in CSV:
- type information (all text). The codebook says which columns are text.
- the difference between `""` and missing for readers that do not see quotes (pandas reads both as NaN).
- dates become ISO text.
- the program's own importer normalises a lone carriage return in a text to a line feed, as it does for every CSV.

### 2.3 `.sav` (pyreadstat 1.3.7 / ReadStat)

**Carried:**
- values: doubles exact; strings in UTF-8 with any width (long strings above 255 bytes are split by ReadStat);
- variable labels, value labels, measurement levels (confirmed level: nominal, ordinal and scale as such, identifier as nominal, unknown as unknown);
- user-missing values: at most three codes, or one range and one code;
- dates (DATE11), date-times (DATETIME20), times (TIME8);
- numeric display formats (`F8.0` for whole numbers, enough decimals otherwise: display only, the stored doubles are exact);
- the file label;
- notes: the export's identity, the dataset SHA-256, and the original name of every renamed variable.

**Converted, and listed in the preview before saving** (`plan_sav` → `export-sav-changes`):
- **Names.** At most 64 UTF-8 bytes, first character a letter, no reserved word (`ALL AND BY EQ GE GT LE LT NE NOT OR TO WITH`, any case), unique without regard to case.
  - A valid name is kept, Latvian and Russian letters included.
  - Otherwise each run of characters SPSS refuses becomes `_`, and `V_` is put in front of a name that does not begin with a letter or is a reserved word. The name is cut at 64 bytes on a character boundary. A clash gets `_2`, `_3`…
  - The rename table is reversible (`restore_names`). It is in the codebook (`spss_names`), and in the file's notes as `Renamed: NAME = original`, or as `Renamed: NAME =` followed by `+ ` lines when the original is longer than one 80-byte note line. The program's importer reads the notes and gives the original names back.
- **Labels** cut at 256 bytes, value labels at 120 bytes, the file label at 64 bytes, always on a character boundary.
- **Identifiers** (confirmed level *identifier*) are string variables, even when their codes are numbers.
- **Categories** (a pandas categorical, such as groups made from a scale) are codes 1…k with value labels, ordinal when ordered.
- **Booleans** are 0/1 with labels False/True.
- **Missing texts.** A text column with missing values gets `""` declared missing: SPSS has no missing value for texts, and declaring the blank keeps it missing. Empty texts and missing texts are then the same.
- **Missing codes beyond the format's limit.** More than three codes are folded into one range and one code when no valid value lies in the range; otherwise the rest are reported as not declared.
- **Other conversions:**
  - mixed number/text columns become text;
  - a text variable confirmed as *scale* is written as nominal;
  - times with a time zone are converted to UTC;
  - integers above 2⁵³ lose digits.

**Not carried, said in the card and here:** the project's audit trail, the derived-variable history, the analysis provenance, hypotheses and protocol records. They are in the codebook (`.xlsx`, `.json`) and the bundle.

### 2.4 Results workbook (`.xlsx`)

- **Results** sheet: one row per analysis (number, title, method, dataset, rows, complete cases, time, sheet).
- **One sheet per analysis:**
  - title, method, dataset, rows, the time it was calculated, complete cases, needs-review reasons;
  - the verified estimates as shown (parameter, estimate, 95 % CI, p);
  - every result table as shown. Cells are display text, never parsed into numbers;
  - **engine values**: every number of the engine's result object at full precision, as numbers (for example `coefficient`, `p_value`, `coefficients[SYN_LON_TOTAL].se`). Arrays of participants' values are left out;
  - the assumption checks with the researcher's review state, the limitation, cautions and the researcher's note.
- **Provenance** sheet, one row per result: result number, title, method key, options (JSON), variables (JSON), measurement levels (JSON), confirmations, dataset, dataset SHA-256, rows, complete cases, time, restored or not, needs review, saved run id, hypothesis snapshot, seeds (JSON), engine, report SHA-256.

A result restored from a project gets its engine object back first (`ProjectBinding.ensure_result`). When it cannot be recalculated, its sheet says that the engine values were not kept, and the shown estimates are its record.

### 2.5 Reproducibility bundle (`.zip`)

| Member | Content |
|---|---|
| `manifest.json` | format and version; time; program version, channel, build, commit; library versions (`project_store.library_versions`); project title and id; the dataset (name, rows, variables, **SHA-256 of the table as CSV text, as every result records it**); per analysis: method key and title, options, roles, confirms, confirmations, dataset SHA-256, rows, complete cases, levels, time, restored, needs review, saved run id, hypothesis, **seeds**, report SHA-256, syntax; every file with SHA-256, size and description; privacy (row-level data: yes; uploaded: no; possibly identifying columns); format notes; limitations |
| `data/<name>.csv` | comma layout, no byte-order mark, formula-protected (`data_file` in the codebook) |
| `data/<name>.xlsx` | Data, Codebook, Scales |
| `data/<name>.sav` | the `.sav` of §2.3 (when it cannot be written, the manifest says why) |
| `codebook/codebook.json` | the complete codebook (§4), with the rename table |
| `results/results.xlsx` | §2.4 with Provenance |
| `report/<name>.docx` | the Word report as composed on the Reports page, when there is one and it is not blocked by outdated results (can be left out under *Advanced*) |
| `figures/R<n>_<section>.png` | the figure of each result as shown |
| `figures/R<n>_<section>_view.svg` | the researcher's Chart Studio view of a result, as SVG with its text alternative, when one exists |
| `syntax/R<n>_<method>.R` | R syntax, only for the verified methods (§2.6) |

**Seeds.** The bundle records three kinds:
- the seeds and resampling counts the engine keeps in its result objects or structured provenance (`seed`, `resamples`, `permutations`);
- the seeds fixed inside engine functions that do not keep them (`export_bundle.ENGINE_SEEDS`): Spearman's permutation p (seed 2026, 1,999 resamples) and parallel analysis (seed 20261103, 150 simulations). A test checks that the engine still uses them;
- the engine's own p-method text when it names a seed.

### 2.6 R syntax (only where verified)

| Method | R code | Check values compared with the engine |
|---|---|---|
| Pearson correlation | `cor.test(x, y, method = "pearson")` | r, p, CI low/high, n |
| Linear regression without HC3 | `lm()` + `summary()` | R², adjusted R², F, n, and b, SE, p of every term |
| Welch t (two groups) | `t.test(y ~ g, var.equal = FALSE)`, the groups in the engine's order | t, df, p |
| One-way ANOVA / Welch ANOVA | `oneway.test(y ~ g, var.equal = TRUE/FALSE)` | F, df1, df2, p |

- Each script reads the bundle's CSV and removes the protective apostrophe from text columns. It prints the R output and the check values; the manifest holds the engine's values for the same names.
- **Verification:** `test_the_r_syntax_reproduces_the_engine` runs every script with Rscript (R 4.3.3 here) on an unpacked bundle of the fixture. All **29 check values** agree with the engine to 1e-9 relative. The test is skipped when Rscript is not installed (`skipUnless`).
- Every other method gets **no syntax**. The manifest gives the reason, for example *no verified syntax for this method in this version*. This covers Spearman (its p is a permutation estimate R would not reproduce), Mann–Whitney, chi-square, Kruskal–Wallis, paired tests, reliability and factor analysis.
- **SPSS syntax is not generated.** No SPSS or PSPP run could verify it in this branch.

## 3. Variable metadata (review M2) and `.sav` import

### 3.1 In the data model

`workspace_state.VariableInfo` has four new fields with defaults:
- `label`;
- `value_labels`: (code, label) pairs;
- `missing_codes`: codes as text, or `("range", lo, hi)`;
- `metadata_source`: `sav`, `codebook` or `project`.

They are documented metadata only, never inferred. They come from a `.sav` file, from the codebook of a CSV this program exported, or from the project. Questionnaires still give labels, value labels, missing options, reverse keys and scale ids for their own question keys.

- They stay with a column across a re-import and a prepared version (`build_dictionary`), as confirmed levels do.
- `ResearchSession.set_metadata` applies them. A level the file documents becomes the **suggested** level only; the researcher still confirms it.
- The Data page shows a label under the variable's name (`label-{variable}`).

There is **no editor** for labels, value labels or missing codes in this increment. They are imported from `.sav` and from the exported codebook, and taken from questionnaires.

### 3.2 In the project: format 6, no new column

`Project.save_variable_metadata` and `variable_metadata` store the metadata without a schema change. `SCHEMA_VERSION` stays 6, and the test checks it.
- Each label goes in **`variables.label`**: a format-6 column that nothing wrote before.
- Value labels and missing codes for each variable go in one JSON document in **`datasets.notes`**: also unused before, marked `"format": "sra-variable-metadata"`. Notes that hold anything else are never overwritten: the save is refused in words.
- `ProjectBinding` saves them on change and with every new dataset version, and restores them with the dataset. They therefore travel in `.sra` backups and duplicates like the rest of the database.

### 3.3 `.sav` import

`data_loader.load_dataset_with_report` reads `.sav` and `.zsav` with `pyreadstat.read_sav(user_missing=True)`. The Data page's Open dialog lists them.
- **Labels, value labels, missing codes and measurement levels** come in as `ImportReport.metadata`.
- **User-missing values** are, by default, *missing* in the table, as SPSS treats them, and their codes stay declared with the variable. Import option *SPSS user-missing values → Keep the codes as values* (`ImportOptions(user_missing="codes")`, `data-opt-user-missing`) keeps −9 or DK as values instead, for an exact round trip. The import report then tells the researcher to mark them missing before analysing.
- Blank texts are missing, as in every other import.
- A file this program exported gets its **original variable names** back from its notes.

## 4. The codebook

One row per variable, in `.xlsx`, `.json` and the bundle:

- variable name and SPSS name;
- full label and where it came from;
- measurement level (confirmed), where it was confirmed, the suggested level;
- storage (kind and dtype);
- value labels, user-missing codes and where they are defined;
- valid values or the observed range. An identifier's or free text's values are never listed, only their number;
- counts: valid, missing (empty cell), user-missing, empty text, distinct;
- reverse-keyed, scales, the derivation rule and notes.

Then the **derived-variable history**, oldest first: step, kind, outputs, inputs, parameters (JSON), recorded at, dataset. It is collected along the dataset's lineage in the project (every version back to the imported one) and from steps the session has not saved yet.

Sources:
- the data file's metadata (§3), first;
- the questionnaire: wording, value labels or Likert anchors, missing options (DK/PNA) for `…__missing_reason` columns, reverse keys, scale ids;
- Data → Prepare: reverse items, scale scores (method, minimum answered), missing codes (`mark_missing` declares its codes on the source column);
- groups from a scale: rule, bounds and labels, the statement on documented cut points.

## 5. Security and privacy

### 5.1 Formula injection in CSV (OWASP "CSV Injection")

- A text cell (and a column name) that begins with `=`, `+`, `-`, `@`, a tab or a carriage return gets **one leading apostrophe** (`csv_safety.protect`).
- So does a text that begins with apostrophes followed by one of those characters, which makes the rule **reversible** for every text: `restore(protect(t)) == t` (tested on 4,000 random strings and the edge cases).
- Every text is quoted, so a separator, quote or line break inside a text cannot start a new cell.
- **Numbers are never changed**: −5 in a numeric column is written `-5`, unquoted.
- The program's importer removes the apostrophe **only** when the codebook (or Data → Prepare's transformation log) next to the CSV vouches for exactly this file: format marker, rule and SHA-256. In any other CSV, and in an exported CSV edited afterwards, an apostrophe is the researcher's own text and stays.

**Review D8**, the first commit (`2ef9110`). The two CSV exports that existed before wrote text cells unescaped: questionnaire responses (`survey_storage.save_survey_csv`) and the prepared dataset (`data_preparation.save_prepared_dataset`). Both now protect text cells and column names. Their codebook or log records the file's SHA-256, so the program reads them back exactly. `tests/test_stage37_csv_guard.py` was written first and failed (red); it passes with the guard.

### 5.2 Spreadsheets
- Every text cell in `.xlsx` is written explicitly as a string (`data_type = "s"`).
- No cell can be a formula: the tests search the sheet XML for `<f>`.
- The importer already never evaluates formulas.

### 5.3 Files
- **Atomic save** (`save_atomic`):
  - write to `.<name>.<random>.partial<ext>` in the chosen folder;
  - re-open it with an independent reader and check the signature and the row count;
  - flush it to disk and move it into place with `os.replace`;
  - check that the moved file has the verified size and SHA-256.
  A failure leaves the destination as it was and no partial file.
- **The checks:**
  - xlsx: `PK` signature, sheet names, header, data rows counted with openpyxl in read-only mode;
  - csv: byte-order mark as chosen, UTF-8, header and record count with the csv module;
  - sav: `$FL2` signature, the variables (pyreadstat, metadata only), the rows of one column;
  - zip: CRC of every member, the SHA-256 of every file listed in the manifest, the data rows inside.
- A save the system refuses is explained in words (`workspace_files.explain`), as for every other export.

### 5.4 Participant data
- Before any row-level export, the card warns about columns that may identify participants (`data_export.sensitive_columns`):
  - names, e-mail, phone, address, birth date, personal code or IP, by column name in EN/LV/RU or by what most values look like (e-mail addresses, the Latvian *personas kods* shape, IPv4, phone numbers that are not dates);
  - participant codes (level *identifier*, confirmed or suggested);
  - free-text answers.
  It is a heuristic warning, never a guarantee either way. On the fixture it names `participant_code`.
- **Nothing is ever uploaded.** Exports write only to the folder chosen in the Save dialog. The manifest records `"uploaded": false`.

## 6. Dependency

- `requirements.in`: `pyreadstat>=1.3,<2`.
- `requirements.txt` was regenerated with the command in its own header:

```
uv pip compile requirements.in --universal --python-version 3.12 --generate-hashes --exclude-newer 2026-11-09T19:00:00Z -o requirements.txt
```

- **The diff** (commit `4bd86e5`):
  - the new entry `pyreadstat==1.3.7`, with the 26 hashes of all its published files;
  - one `#   pyreadstat` "via" line under narwhals and one under numpy.
  It now pins **50** packages instead of 49. No other pin or hash changed: compared pin by pin, 0 changed, 0 removed.
- **Dependencies:** pyreadstat 1.3.7 needs narwhals (2.28.0) and numpy (2.5.4), both already pinned.
- **Dev lock:** `requirements-dev.txt` regenerates byte-identical with its own command. The GUI driver installs both locks (`.github/actions/pinned-windows-toolchain`), so it has pyreadstat.
- **Windows:** the lock holds the hash of `pyreadstat-1.3.7-cp312-cp312-win_amd64.whl`, `7b65bd28c402376c5bafa44c691acf726904611621e09404bbf4827de78b4609`. It was checked against PyPI's metadata and against the downloaded wheel, and `tests/test_stage37_dependency.py` checks it.
- **Licences:**
  - pyreadstat is Apache-2.0 (its `License` metadata);
  - the ReadStat C library compiled into it is MIT (© Evan Miller). Both texts are in the wheel's `dist-info/licenses/LICENSE`, which the bundle keeps.
  - `tools/build_sbom.py` lists pyreadstat (`Apache-2.0`) and ReadStat as a component inside it (`MIT`, `BUNDLED_IN_WHEEL`), and both are in `licenses.md`. Neither is copyleft. `docs/STAGE368_BUILD_LOCK.md` §2.1 and §5 have the note.
- **Bundle size**, measured from the locked Windows wheel with the build's own cleanup globs (`tools/prune_packages.py`):
  - **+2.48 MiB installed** (12 files, mostly the two compiled modules of 1.2 MiB each);
  - **+1.62 MiB** as the sum of per-file deflate sizes, which approximates the growth of the installer and the portable ZIP;
  - the cleanup removes the 2.85 MiB of `.c`, `.pyx` and `.pxd` sources.
  - Not measured in a Windows build.

## 7. Performance

Linux container, Python 3.12.3, one table of 100,000 rows × 30 columns (3 million cells: 28 numeric, two text), write plus verification:

| Format | Time | File |
|---|---:|---:|
| `.xlsx` (Data only) | 48.5 s | 13.4 MiB |
| `.csv` | 5.4 s | 13.1 MiB |
| `.sav` | 1.5 s | 22.9 MiB |

The `.xlsx` time is openpyxl's own XML serialisation (≈ 100,000 cells/s) and the full re-read with openpyxl in read-only mode. Float columns skip the per-cell conversion. Progress is reported every 2,000 rows.

## 8. Windows journey `export-data`

`tools/windows_gui_e2e.py` gains the journey **`export-data`**. It is appended after the 18 existing journeys in `JOURNEYS`, whose order is unchanged (`tests/test_stage37_export_journey.py`). `tests/test_stage368_review_journeys.py` now expects 19 journeys.

The journey:
1. creates project *Fictional export study*;
2. generates the 180-case fixture with the stdlib generator and opens it in the Windows Open dialog;
3. on the Data page, finds the Export card, then for `.xlsx`, `.sav` and `.csv`:
   - chooses the format in the dropdown *Format*;
   - for `.sav`, waits for the text about what `.sav` cannot hold;
   - presses *Export .xlsx…* / *.sav…* / *.csv…*;
   - types the target in the **native Save dialog**;
   - waits for *Saved and checked* and the file name;
4. checks every file on disk with the driver's own independent readers (`check_export`):
   - openpyxl: no formula, sheets Data and Codebook, every cell;
   - pyreadstat: `$FL2`, names, every cell;
   - pandas: byte-order mark, every cell, and the codebook vouching for the CSV by SHA-256.
   Each cell is compared with the fixture as the driver reads it with the csv module;
5. checks that `preferences.json` remembers `csv`.

No disabled state is asserted, because UI Automation reports every button as enabled.

**Proof here:** `ExportDataJourneyTests.test_the_journey_flow_and_its_checks` walks the same flow in the harness with the journey's own texts, options and `check_export`. It also checks that the format is remembered after a restart. `test_the_journey_check_finds_a_changed_cell` shows that `check_export` fails on one changed cell.

**Not done:** a run on Windows. The journey runs in `windows-gui-e2e.yml`; its path filter now also covers `data_export.py`, `export_bundle.py`, `csv_safety.py`, `data_loader.py` and the stage 37 generator.

## 9. Test evidence

New test files:

| File | Tests | What they prove |
|---|---:|---|
| `tests/test_stage37_csv_guard.py` | 7 | D8: the rule, reversibility (4,000 random strings), both older exports protected, numbers unchanged, read back exactly only when the codebook or log vouches, an edited file keeps its apostrophes |
| `tests/test_stage37_dependency.py` | 4 | range and pin, the Windows wheel hash, 50 pins, narwhals and numpy unchanged; in the Windows runtime; SBOM Apache-2.0 + ReadStat MIT; the cleanup keeps the licence and the compiled modules |
| `tests/test_stage37_export.py` | 26 | round trips (below), SPSS names, preview, metadata storage and restart, codebook, results workbook, bundle, **R syntax**, engine seeds, atomic save, participant check, preferences |
| `tests/test_stage37_export_ui.py` | 10 | the card on the Data, Results and Reports pages; one click; `.sav` preview; CSV layout and byte-order mark remembered; a failed save; `.sav` opened with labels and the user-missing option; LV/RU; the bundle with the Word report; data export without a report |
| `tests/test_stage37_export_journey.py` | 3 | journey order; the `export-data` walk; its check catches a changed cell |

**Round trips** (fixture: 180 cases × 98 variables, plus adversarial columns):
- cells beginning with `= + - @`, a tab or an apostrophe;
- a 75-character Latvian and a 73-character Russian variable name (85 and 131 UTF-8 bytes);
- date-times and dates with gaps;
- `000`…`179` identifiers;
- a rating with labels for its missing codes −9 and −8, which are declared user-missing;
- an unlabelled numeric variable;
- empty texts beside missing ones;
- doubles that need 17 digits.

| Round trip | Independent reader | Result |
|---|---|---|
| app → `.xlsx` | openpyxl (cell by cell, types), pandas.read_excel | values exact (17-digit doubles within 1e-15); dates as datetimes; `000` stays text; formula texts are text cells and the XML holds no `<f>`; missing has no cell, an empty text is a text cell; Codebook: levels, value labels, missing codes, counts (`rating`: 60 user-missing, 30 missing); Provenance: dataset SHA-256 |
| app → `.csv`, comma and semicolon | pandas.read_csv | every number exact, decimal comma included; texts equal after `restore`; only `""` vs missing merges, as documented |
| app → `.csv` → app | data_loader | every protected text restored, numbers exact, `1,234` read as 1.234 in the semicolon layout, leading zeros kept; labels, value labels and missing codes come back as metadata, and the level as a suggestion only |
| app → `.sav` | pyreadstat.read_sav | values exact; SPSS names; measures equal to the confirmed levels; missing (−9, −8) declared; value labels; labels cut at 256 bytes on a character boundary; `code_lz` is a string with its zeros; missing Russian text is `""` declared missing, NaN when read normally; UTF-8 |
| app → `.sav` → app | data_loader | the original names come back, the long LV/RU ones included; metadata equal; user-missing values missing by default; with `user_missing="codes"` the `rating` series is equal |
| external `.sav` → app → `.sav` | pyreadstat.read_sav | values equal (codes kept), labels, value labels, missing values (discrete, range plus code, string) and measures equal |
| the bundle | zipfile + manifest | every file's SHA-256, 180 rows, all members, seeds, syntax only where verified |
| the bundle's R syntax | Rscript 4.3.3 | **29/29 check values** within 1e-9 of the engine |

**Full suite** (Linux, Python 3.12.3, a venv from both hashed locks, R 4.3.3 present, so the R syntax test ran):
- before the change (`2f9af71` with the lock change): 1,326 tests, OK, 10 skipped (999 s);
- after it (`b210777`): **1,376 tests, OK, 10 skipped** (1,043 s). The 50 new tests are the five files above.

Run with:

```
SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 python -m unittest discover -s tests
```

## 10. Limitations

- **xlsx:** doubles with 17 significant digits keep 16; there are no infinities; texts over 32,767 characters are cut; there is one worksheet (≤ 1,048,575 rows).
- **CSV:** types are not carried (the codebook says them). A reader that ignores quotes merges `""` with missing. The formula protection is visible in other programs as a leading apostrophe; only this program, with the codebook, removes it.
- **.sav:**
  - missing texts and empty texts become one declared-missing blank;
  - at most three missing codes or a range and a code;
  - categories become codes with labels; on import they come back as codes with value labels, not as a pandas categorical;
  - time zones are converted to UTC;
  - no audit trail, history or provenance;
  - default import makes user-missing values missing; keeping the codes is an explicit option.
- **Metadata:** there is no editor in this increment. Metadata comes from `.sav` files, exported codebooks and questionnaires. Metadata is not imported from an `.xlsx` Codebook sheet.
- **Syntax:** R only, for four method families. No SPSS syntax.
- **Participant warning:** a heuristic, so false positives and misses are possible.
- **Performance:** `.xlsx` is about 60,000 cells/s including the check (§7).
- **Windows:**
  - the journey has not run on Windows;
  - no measurement of the installed size;
  - no screenshot evidence of the card on Windows.
- **Locale:** LV and RU texts are drafts.

## 11. Done / not done

| Item | Status | Proved by |
|---|---|---|
| Data → .xlsx (openpyxl), .sav (pyreadstat), .csv (UTF-8, optional byte-order mark) | done | §9 round trips |
| Codebook: name, label, level, value labels, valid and missing codes, scales, reverse items, history | done | `CodebookTests`, `XlsxRoundTripTests.test_codebook_scales_and_provenance_sheets` |
| Results: editable .xlsx, per analysis, with provenance | done | `ResultsAndBundleTests.test_results_workbook_sheets_engine_values_and_provenance` |
| Bundle: manifest (dataset SHA-256, versions, methods, options, seeds), codebook, data, results, DOCX, figures | done | `test_the_bundle_manifest_files_and_checksums`, `test_the_bundle_from_the_reports_page_holds_the_word_report` |
| R syntax only where verified | done (R, 4 method families, 29 values) | `test_the_r_syntax_reproduces_the_engine` (needs Rscript) |
| SPSS syntax | not done | no SPSS or PSPP verification available |
| xlsx sheets Data, Codebook, Scales, Results, Provenance, selectable | done | `XlsxRoundTripTests`, `DataExportTests` |
| Numbers, dates, leading zeros, missing vs blank, explicit text cells | done | `test_values_types_and_missing_survive_openpyxl`, `test_no_cell_is_ever_a_formula` |
| CSV formula protection: documented, reversible, numbers unchanged | done | `test_formula_injection_is_neutralised_and_numbers_are_not`, `test_stage37_csv_guard` |
| Streaming with progress | done | `test_streaming_reports_progress_and_refuses_what_excel_cannot_hold`, §7 |
| .sav: levels, labels, value labels, user-missing within limits; SPSS names with a reversible rename table shown as a preview; Unicode and widths; what .sav cannot carry shown | done | `SavRoundTripTests`, `test_the_sav_preview_lists_every_renamed_or_cut_field_before_saving` |
| Review: identifiers as strings; at most 3 codes or 1 range (+1 code); every renamed or cut field previewed | done | `test_the_preview_lists_every_renamed_cut_or_converted_field` |
| Review D8: older CSV exports protected (red test first, own commit) | done | `tests/test_stage37_csv_guard.py`, commit `2ef9110` |
| Review M2: labels, value labels, missing codes in the model and stored in format 6 without a new column | done | `MetadataStorageTests` (both) |
| Review M2: editor | not done | import from .sav and from the exported codebook instead |
| Review H2: semicolon separator and byte-order mark, remembered | done | `test_semicolon_layout_…`, `test_csv_separator_and_byte_order_mark_are_offered_and_remembered`, `LanguageTests` |
| .sav import with labels and missing codes; round trips both ways | done | `test_the_program_restores_names_and_metadata_from_its_own_sav`, `test_an_external_sav_comes_in_and_goes_out_with_its_metadata`, `test_an_spss_file_opens_with_its_labels_and_its_missing_option` |
| Dependency: range, hashed lock, cp312 win_amd64 hash, licences, SBOM, size | done (size from the wheel, not from a build) | `tests/test_stage37_dependency.py`, §6 |
| One Export action in Data, Results, Reports; remembered format; folded options; lossless default; no report needed | done | `test_stage37_export_ui` |
| Atomic save, success location, verification after saving | done | `AtomicSaveTests`, every round trip (`verified`) |
| Participant warning; nothing uploaded | done | `SensitivityTests`, `test_participant_codes_are_flagged_and_nothing_is_uploaded` |
| EN/LV/RU (LV/RU drafts) | done (drafts) | `LanguageTests`, `test_locale_audit`, `test_workspace_foundations` |
| Windows journey `export-data`, walk test | written, walked in the harness | `tests/test_stage37_export_journey.py` |
| Windows journey run on installed Windows | not done | CI `windows-gui-e2e.yml` |
| `.por`, `.dta` | not done | no separately validated writer (spec: optional) |
