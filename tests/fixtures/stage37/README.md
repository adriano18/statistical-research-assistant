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

**Status:** generator and requirements only. This branch does not implement .sav/.xlsx exports, RAG, mediation/moderation or new UI functionality.

**Stage 37 methods increment (Issue #66, branch `claude/stage37-methods`).**

- Mediation, moderation and conditional process models are implemented, with structures equivalent to PROCESS Models 4, 1, 7 and 14, as is a linear model with dummy-coded covariates. See [`docs/STAGE37_METHODS.md`](../../../docs/STAGE37_METHODS.md).
- The H1–H6 scenario on this fixture is `tests/test_stage37_master_acceptance.py`. It is documented in [`docs/STAGE37_MASTER_ACCEPTANCE.md`](../../../docs/STAGE37_MASTER_ACCEPTANCE.md).
- The public synthetic mapping of constructs, coping dimensions and hypotheses is [`synthetic_construct_mapping.json`](synthetic_construct_mapping.json). In the generator, coping group 0 is M; groups 2 and 5 play "avoidance-like" (+X) and groups 3 and 6 "assertive-like" (−X).
- The generator above is unchanged (v1).
