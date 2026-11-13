# Stage 37 synthetic master's research acceptance fixture

Run (from repository root):

```bash
python tests/fixtures/stage37/generate_master_fixture.py --out-dir .stage37-fixtures
```

Only Python standard library is required to generate the fixture (the installed Windows application's end users still need no Python).

Produces:

- `synthetic_master_research_n180.csv`: 180 entirely fictional participants, 98 columns, ~89 item-level fields across four **invented** questionnaire-like constructs, plus demographics and derived synthetic scores.
- `synthetic_master_model_spec.json`: deterministic seed, fictional latent generating equations, missingness and exact fixture warnings.

The fixture was built from generic statistical model requirements, **not derived from any real research participant** or the original text of WHO-5, MSPSS, UCLA, SACS or the owner's unpublished thesis. A 'WHO-5-like' numeric 5-item schema is not the WHO questionnaire; do not reproduce, publish, or score real instruments based on this example.

### Verification tasks

1. Check 180 rows, 98 columns, unique `FAKE_0001..FAKE_0180`, 18–30 age range, correct numeric ranges, 5 strategically missing items and corresponding missing derived scores, WHO-like raw×4 consistency.
2. Compute independent reference Pearson/Spearman, correlations for all constructs, item-level alpha and alpha-if-item-deleted, multiple linear regression, interactions, bootstrapped mediation and conditional indirect effect. The latent generating coefficients in the JSON **do not equal** observed-score fitted OLS coefficients.
3. Use the app to export data and a codebook to .xlsx, .csv and .sav, then independently reopen files and compare original values, labels, levels, categories, missing codes and provenance.
4. In installed Windows EXE, run hypothesis→analysis→report workflow, save/restart, export and in-app update A→B with project preservation.
5. Keep real private documents under `private-test-data/` for separately authorized local acceptance; GitHub public CI must never see them.

See [Stage 37 next specification](../../../docs/STAGE37_NEXT_SPEC.md) and GitHub Issues #66–#70.

**Status:** verification task 3 (export to .xlsx, .csv and .sav, reopened with independent readers) is implemented on `claude/stage37-export` and tested on this fixture (`docs/STAGE37_EXPORT.md`; `tests/test_stage37_export*.py`; Windows journey `export-data`, not yet run on Windows). RAG and mediation/moderation are not implemented.
