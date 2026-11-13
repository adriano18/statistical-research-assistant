# Stage 37 next: master-level scientific validation, exports, UX, private RAG and independent review

> **PUBLIC-SAFE TECHNICAL SPECIFICATION.** This document intentionally does not reproduce any researcher's thesis, real study dataset, questionnaire text, names or participant identifiers. The owner provided source documents privately. The public acceptance dataset must always be synthetic.

Source: Draft PR #65 (Stage37.0a) stacked on #64 (Stage36.8 RC); inspect latest live GitHub state before making changes. Issues #66–#70 are the scoped requirements. **No auto merge or public release.** Communicate with owner in Russian; code/tests/docs in English; app EN/LV/RU.

## 0. Before implementation
1. Inspect `docs/STAGE37_0A_STATUS.md`, `docs/STAGE37_DESIGN.md`, `docs/STAGE368_RELEASE_CHECKLIST.md`, existing project schema 6, immutable protocol history and analysis numerical oracles. Complete outstanding 37.0b work from the status file.
2. Keep the Stage36.8 RC stable. Do not rebase/merge PR #64/#65 into main without owner approval.
3. Keep the installed Windows application's updater, local offline OCR and backwards-compatible project backups. User's default workspace should not require clicking **Open the preview** once parity/owner acceptance is achieved.
4. Do not commit private instrument PDFs, protected wording, thesis or participant data to this **public** repository. Existing gitignore excludes `private-test-data/`; private acceptance can run only with explicit local access.

## 1. Master's-level research acceptance (Issue #66)
The conceptual model has:
- X: loneliness-like predictor;
- M: coping-like potential mediator (multiple planned dimensions possible);
- Y: subjective well-being outcome;
- W: perceived social support moderator;
- controls: age, sex, employment; optional student status.

At acceptance, simulate N=180 fabricated cases using `tests/fixtures/stage37/generate_master_fixture.py`. Fixture names start `SYN_`; its 20/52/5/12 numeric question-like fields are **invented**, are NOT the original UCLA/SACS/WHO-5/MSPSS instruments, and use NO validated scoring keys. The generator gives generating parameters, not truth about fitted sample coefficients. Validate OLS/HC covariance, listwise/missingness policies, model conditioning, interactions and bootstrap computations against independent SciPy/statsmodels/R references.

The owner's plan calls for descriptive summaries, item reliability, distribution/assumption diagnostics, Pearson/Spearman, group tests, multivariable regression, indirect effects, moderation, and optional conditional process paths. Implementation must explicitly distinguish:
- mediation / Model 4: X -> M -> Y, direct path, bootstrap indirect-effect interval;
- moderation: X × W and simple slopes, Johnson–Neyman only if validated;
- Model 7: W moderates X -> M (a path);
- Model 14: W moderates M -> Y (b path).
Never auto-select 7 vs 14: the researcher must confirm which theoretical path is moderated. A separate X×W -> avoidance-like outcome hypothesis is not itself the same as Model 7/14.

Document cross-sectional causal limits. Do not label statistically significant mediation as causal proof. Do not make the presence of significant preliminary p-values a mandatory condition for selecting a mediator; a priori theory and exploratory status are distinct. Encourage sensitivity simulation/power assessment of the most complex path model rather than only heuristic N rules.

Research plan H1–H6 needs typed variable roles and linked, immutable, auditable analysis-run provenance. In Word, hypothesis rows and evidence show source, calculation, review status and limitations. Correlation, mediation and moderation statistics must be genuinely calculated, not AI-generated.

## 2. Export and interoperability (Issue #67)
Implement user-visible context-preserving export:
- Data: .xlsx, .sav, .csv (option BOM), optionally .por or .dta only with separately validated writer support.
- Codebook: variable labels, coding, nominal/ordinal/scale levels, missing values, reverse scoring and derived-variable history.
- Results: per-run and combined editable .xlsx, existing .docx, graphs PNG/SVG, reproducibility manifest and optional R/SPSS syntax for supported analyses.
- .xlsx sheets suggested: Data, Codebook, Scales, Results, Provenance.
- .sav writer: evaluate pyreadstat/ReadStat; enforce compatible names/labels/missing codes and deterministic round-trip verification. Proprietary SPSS is not required to create .sav, and .sav is not a substitute for the project's full audit.
- Protect against spreadsheet formula injection and preserve text IDs with leading zeros. Warn and show preview on lossy type/name conversions.
- One contextual Export button, last-used format, optional advanced settings; no repeated form loops. Verify native file picker and actual saved files with independent readers on installed Windows.

## 3. Personal settings + low-friction UX (Issue #68)
- Make Research Workspace normal start experience after parity gate; classic UI remains accessible in Settings.
- EN and LV quick language buttons visible; RU absent from top-bar quick switch **but fully available under Settings > Language**. Do not reset existing Russian user preferences or remove translations/ru report support.
- Default classic Windows legible typeface Segoe UI / Segoe UI Variable with fallback; user-selectable font size, comfortable/compact density, styles applied to charts and reports as independently appropriate. Do not distribute proprietary font files.
- Central Settings: appearance, accent, theme, density, font, language, local data folder, backup/update preferences, export defaults, RAG/AI privacy, recent projects, reset preferences vs delete data.
- User-owned local research projects, multiple datasets, portable backups and no mandatory account. No transfer to AI without opt-in.
- Task-to-task return and one-click reuse for analyses, source changes, charts, reports; preserve focus and scroll; metrics for interactions and first-use completion.
- Test existing Russian setting survives upgrade, 100–175% Windows DPI, Narrator, keyboard-only, and startup/restart/update.

## 4. Research RAG library (Issue #69)
Start with a safe **offline lexical search** MVP:
1. Explicitly import permitted papers, plans, manuals and local notes.
2. Parse PDF/DOCX, local OCR if needed, section/page-aware chunks and hashes.
3. Index in project-scoped SQLite FTS5/BM25 with citations to original local page/section.
4. Return snippets and open sources offline, with project isolation, updates/deletion and provenance.
5. Only then consider optional local multilingual embeddings (LV/RU/EN) and hybrid retrieval after benchmark (recall, multilingual correctness, cite accuracy, package size, speed). No compulsory GPU/vector models.
6. Optional provider AI receives only user-approved snippet payload, exact preview, no participant rows and no project data leaks.
7. Ground any AI narrative in retrieved citations and validated engine numbers; missing evidence must be reported honestly. Retrieved instructions are untrusted.

RAG is **not** a statistical engine, nor a model fine-tuned on the owner's own data. Never make remote requests for offline search.

## 5. Fable 5.2 independent Narrow Review (Issue #70)
Run on code/docs/screenshots and synthetic journey materials only; reviewer has **read-only** permissions, no direct implementation/push/merge. Ask for 10 evidence-grounded top improvements, click/scroll/action counts, two alternative IA proposals, novice vs professor journeys, scientific risks, accessibility, privacy, license and architecture. All findings must separate verified defects from ideas. Developer follows with red tests and owner review before changes. Preserve reviewer output in `docs/STAGE37_FABLE_NARROW_REVIEW.md`.

## 6. Licence and release gating
Current RC reports GPL-3.0 `pingouin` but project has no LICENSE. Do not assume rights; present the owner's decision between GPL-compatible distribution (including obligations) versus independent replacement of the needed alpha calculation with validated, appropriately licensed implementation. Consult licensing expertise before public commercial distribution. WHO-5 (2024 WHO edition) contains a CC BY-NC-SA 3.0 IGO notice: do not bundle its official questions/media or claim WHO endorsement without permitted license. Other instrument text and local adaptations require separate rights verification. Code signing remains owner-controlled; never request API/signing secrets in chat or commit.

## 7. Execution and gates
Order: 37.0b/fixture + numerical oracles -> 37.1 export -> 37.2 UX settings -> 37.3 local RAG -> 37.4 Fable review, with independent review ideally before material UX redesign; Fable may run earlier on a fixed snapshot read-only. Divide into small draft PRs, each with independent numerical tests and installed Windows E2E, on the correct Stage37 branch. Keep RC as stable release line. No feature declared done without actual test.
- Standalone CSV generator must be runnable with stdlib and not need source documents.
- End-to-end project starts with synthetic data, registers hypotheses and variable roles, validates regression/mediation/moderation and prints auditable independent results.
- Round-trip export/import .xlsx/.sav restores values, labels and missingness within documented format limitations.
- Source-cited RAG query produces correct, grounded local snippets offline and never sends private files by default.
- User's old RU UI preference remains saved though RU is hidden from quick header toggle; default classic typography is readable.
- 18 native GUI journeys, Windows installer update A->B and project-format-6 backup/restore remain green.
- Explicitly distinguish **synthetic functionality verified** from **real master's dataset empirical analysis**: current owner upload contains a plan and instruments, **not participant responses**.

## Claude Code kickoff
Read this file and Issues #66–#70. Implement rather than restate the plan. Validate synthetic fixtures, record independent model/test oracles, do NOT upload private source files. Communicate in Russian. Preserve numeric integrity and owner-controlled PR merging/publishing.
