# Stage 36 — reproducible, privacy-safe acceptance kit

The **complete product specification** is [docs/STAGE36_SPEC.md](../../../docs/STAGE36_SPEC.md). It is based on the owner's Stage 36 prompt, with private research dataset-derived results replaced by a synthetic-fixture protocol.

## Public CI fixtures (no personal or proprietary questionnaire content)

Run from the repository root:

```bash
python tests/fixtures/stage36/generate_fixtures.py --out-dir .stage36-fixtures
```

This requires `python-docx` and `Pillow` in the *developer/CI environment*; it does **not** require the end user to install packages. Add them to test-only dependencies if missing.

The generator is deterministic and creates:

| Filename | Intended regression |
|---|---|
| `synthetic_ucla_sacs_55.csv` | 55 invented participants; 13 fields; three imbalanced groups (3/47/5); 8 synthetic scales; test batch correlation, category derivation, N/exclusions, Kruskal–Wallis |
| `synthetic_cope_two_forms_60.docx` | Two separate 60-item **fictional** tables, with different header conventions plus synthetic scoring metadata and numbered references. Verify the importer does not mistake citations for questions or combine versions. |
| `synthetic_sacs_scanned_52.pdf` | Two image-only pages with 52 invented numbered items, five printed response columns, and two numbered reference distractors. Verify offline OCR, table rows, item count and review UX. |

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
