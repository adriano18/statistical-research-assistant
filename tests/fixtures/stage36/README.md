# Stage 36 — reproducible, privacy-safe acceptance kit

The **complete product specification** is [docs/STAGE36_SPEC.md](../../../docs/STAGE36_SPEC.md). It is based on the owner's Stage 36 prompt, with private research dataset-derived results replaced by a synthetic-fixture protocol.

## Public CI fixtures (no personal or proprietary questionnaire content)

Run from the repository root:

```bash
python tests/fixtures/stage36/generate_fixtures.py --out-dir .stage36-fixtures
```

This requires `python-docx`, `Pillow` and `matplotlib` in the *developer/CI environment*; it does **not** require the end user to install packages. Add them to test-only dependencies if missing.

The scans are drawn with fonts that matplotlib ships (DejaVu, STIX), never with the fonts of the computer, and laid out by Pillow's basic text engine (Pillow shapes text with libraqm on Linux but cannot on Windows), so Linux and Windows generate the same pages. Before Stage 36.7 the Windows runner drew the Latvian table in Times New Roman: the packaged-EXE journey then read a different document than the Linux tests did.

The generator is deterministic and creates:

| Filename | Intended regression |
|---|---|
| `synthetic_ucla_sacs_55.csv` | 55 invented participants; 13 fields; three imbalanced groups (3/47/5); 8 synthetic scales; test batch correlation, category derivation, N/exclusions, Kruskal–Wallis |
| `synthetic_cope_two_forms_60.docx` | Two separate 60-item **fictional** tables, with different header conventions plus synthetic scoring metadata and numbered references. Verify the importer does not mistake citations for questions or combine versions. |
| `synthetic_sacs_scanned_52.pdf` | Two image-only pages with 52 invented numbered items, five printed response columns, and two numbered reference distractors. Verify offline OCR, table rows, item count and review UX. |

Stage 36.0 added two structural variants that reproduce the layouts which
defeated the importer on the owner's private documents, with wholly
invented text:

| Filename | Intended regression |
|---|---|
| `synthetic_cope_two_forms_60_unnumbered.docx` | Two 60-item table forms with **no item numbers inside the cells** (first table 61 rows with a header of response labels, second 60 rows, 5 columns), each form with its own response options, a 15 × 4 scoring note and numbered references. |
| `synthetic_lv_table_scan_52.pdf` | Two image-only pages of a table: item numbers in their own column, statements wrapped onto a second line, Latvian letters with diacritics, the response legend repeated at the top of page 2, a slight rotation and tick-like artifacts before some numbers. |
| `synthetic_lv_table_scan_52_stix.pdf` | Stage 36.7: the same table set in STIX General, a Times-like serif. In that typeface the rules between rows made Tesseract drop whole text lines, single-digit numbers were misread and a legend line read as `4 bieži` tilted the statement column (the packaged Windows run found 45 of 52 on the Times New Roman version). |

`tests/test_stage36_fixtures.py` checks the minimal verification below;
`tests/test_stage36_regressions.py` reproduces the documented defects on
these files (see `docs/STAGE36_PLAN.md`).

These are structural/functional fixtures only. They **do not validate any real UCLA, COPE or SACS instrument**, scoring key, translation or intellectual-property rights.

### Minimal independent verification expected

- CSV: 55 data rows, 13 columns, unique fictional IDs, group sizes exactly 3/47/5.
- DOCX: two table-based instrument forms of 60 items each; references/method notes excluded from extracted questions.
- PDF: 2 pages, 52 numbered prompts, no selectable PDF text; references excluded; OCR word-level confidences must not be misrepresented as calibrated questionnaire confidence.
- Independent SciPy/statsmodels numerical parity tests must be computed on generated data, not copied from any thesis or real participant dataset.
- One packaged Windows EXE run must actually perform import and export, record GUI interactions, and inspect output files on disk. A passing browser test does not replace Windows E2E.

## Owner's private acceptance materials — LOCAL ONLY

For additional scientific checks, the owner can keep originals under `private-test-data/` (this directory is gitignored). Example local layout:

```text
private-test-data/
  participant_dataset.csv
  thesis_for_comparison.docx
  coping_instrument_original.docx
  coping_instrument_scan.pdf
```

These files are **never** pushed to GitHub, uploaded as PR attachments or included in public CI artifacts. Claude Code running locally on the owner's computer may read them when given explicit access. Cloud GitHub Actions cannot access local private files, and that is intentional.

Do not store extracted participant rows, original question text, original thesis pages, screenshots with personal data or original document blobs in test recordings or CI logs. Report counts and discrepancies only.

## Claude Code starting instruction

> Read `docs/STAGE36_SPEC.md` and `tests/fixtures/stage36/README.md` from the Stage 36 branch. The specification is the full implementation task, not a request for a new plan. First generate and validate synthetic fixtures; build red regression tests for known UX/statistical/import issues; then implement in separate reviewable PRs, with native Windows EXE E2E. Use no real research data in GitHub. Communicate progress in Russian. Never auto-merge into main or publish a release.

## Status

This repository addition supplies a **specification and a fixture generator**, not a completed Stage 36 implementation. End-to-end application behavior remains to be implemented and tested by the development agent.
