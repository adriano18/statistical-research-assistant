export const meta = {
  name: 'verify-stage37-export',
  description: 'Adversarially verify Excel/SPSS/CSV export and import (injection, .sav fidelity, .xlsx fidelity, integrity, integration), then fix',
  phases: [
    { title: 'Verify', detail: 'five independent read-only reviewers' },
    { title: 'Fix', detail: 'red tests and fixes for confirmed findings' },
  ],
}

const ROOT = '/home/user/statistical-research-assistant'
const SCRATCH = '/tmp/claude-0/-home-user-statistical-research-assistant/8d8df448-6aa8-50d6-b440-62d0c67e9744/scratchpad'
const PY = SCRATCH + '/venv-export/bin/python'
const BRANCH = 'claude/stage37-export'
const BASE = '2f9af71'
const COMMON = `
Context: desktop app "Statistical Research Assistant" (Python, Flet 1.1.2, Windows-first, EN/LV/RU), repo ${ROOT} (shared object store; never touch other branches). Branch under review: ${BRANCH} on ${BASE} (Issue #67), 5 commits: 2ef9110 formula-injection guard for the two existing CSV exports (review D8); 4bd86e5 pyreadstat 1.3.7 added to the hashed runtime lock (+SBOM/licence notes); 9a094ea the export feature (data_export.py, export_bundle.py, workspace_export.py, csv_safety.py: .xlsx with Data/Codebook/Scales/Results/Provenance sheets, .csv comma/semicolon + BOM with an apostrophe guard and a <name>_codebook.json that allows stripping only when its SHA-256 matches, .sav via pyreadstat with SPSS-valid names and original names in notes, labels/value labels/measurement levels/missing codes, .sav import, results .xlsx, reproducibility bundle .zip with manifest, data, codebook, results, Word report, PNG/SVG figures and R syntax for a few methods; temp file + independent re-read + move; identifying-column warning; one Export card on three pages with remembered choices; labels in variables.label and value labels/missing codes as a marked JSON document in datasets.notes, project format 6 unchanged); b210777 Windows journey export-data appended as the 19th journey + workflow path triggers; 619143d docs/STAGE37_EXPORT.md.
Product rules: researchers export their own data and results to .xlsx, .sav, CSV, codebook, reproducibility bundle, existing DOCX/figures; preserve variable and value labels, measurement levels, user-defined missing values where supported, stable identifiers; prevent spreadsheet formula injection and accidental data corruption; one clear Export action with remembered preferences and optional advanced options; real round-trip tests; saved files validated on disk.
Python: ${PY} (3.12, has pyreadstat; use it, do not modify it). Rscript 4.3.3 exists at /usr/bin/Rscript but R packages foreign/haven are NOT installed; do not install system or R packages (a PSPP install was refused earlier) — where an independent reader is needed, write your own minimal reader from the documented format (zipfile+ElementTree for .xlsx; the SPSS system-file record layout for .sav: header, type-2 variable records, type-3/4 value labels, type-7 subtypes 3/4/11/13/14/20/21, type-999, bytecode or uncompressed data). Full suite: SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 <python> -m unittest discover -s tests (~18 min). Synthetic data only; never open ${SCRATCH}/private or /root/.claude/uploads.`

const FINDINGS = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, area: { type: 'string' },
      file_line: { type: 'string' }, claim: { type: 'string' }, evidence: { type: 'string' },
      red_test: { type: 'string' }, confirmed: { type: 'boolean' } },
      required: ['id', 'severity', 'claim', 'evidence', 'confirmed'] } },
    checked_and_fine: { type: 'array', items: { type: 'string' } },
  },
  required: ['findings', 'checked_and_fine'],
}
const RESULT = {
  type: 'object',
  properties: {
    commits: { type: 'array', items: { type: 'string' } },
    fixed: { type: 'array', items: { type: 'string' } },
    rejected_with_evidence: { type: 'array', items: { type: 'string' } },
    tests: { type: 'string' },
  },
  required: ['commits', 'fixed', 'rejected_with_evidence', 'tests'],
}

const LENSES = [
  ['injection', 'Formula injection and spreadsheet safety across EVERY export path (data/results/codebook/scales/provenance sheets, CSV both layouts, codebook JSON, bundle members, R syntax files, existing exports in survey_storage.py and data_preparation.py, chart/table exports, Word tables if they can carry formulas, any older CSV/XLSX export elsewhere in the app such as research_app.py classic exports). Try: = + - @ tab CR LF leading, leading whitespace or quotes before =, full-width ＝＋－＠, DDE (=cmd|...), |, HYPERLINK, negative numbers stored as text ("-5" text vs -5 number), "+371..." phone numbers, values in HEADER names/variable labels/value labels/sheet names/category labels, very long strings; check the .xlsx XML for any <f> element or cells whose type is not s/inlineStr/n/d/b as intended; check the apostrophe-strip on re-import cannot be triggered by a forged codebook (hash binding) and that an attacker-supplied CSV + matching codebook is still safe; check that numbers are never altered. Compare with OWASP CSV-injection guidance.'],
  ['sav', 'SPSS .sav fidelity with an INDEPENDENT reader you write yourself (see Context). Verify on the 180-case synthetic fixture (tests/fixtures/stage37/) plus adversarial data: names (≤64 bytes in the file encoding, unique ignoring case, reserved words ALL AND BY EQ GE GT LE LT NE NOT OR TO WITH, first char rules, trailing period/underscore, Latvian/Russian names, collisions after truncation), long-name record, encoding record (UTF-8), very long strings (>255 bytes), string widths with multibyte text, value labels for numeric and string vars (label length limits 120 bytes), measurement levels (nominal/ordinal/scale) and roles, display widths, missing values (≤3 discrete, range+1, string missing ≤8 bytes), dates/datetimes (SPSS epoch 1582-10-14, format DATE11/DATETIME20), integers vs doubles, NaN/inf, system-missing vs empty string, compression (bytecode) correctness, case count field; also import of external .sav (labels/levels/missing/very long strings, encodings other than UTF-8 such as windows-1257/windows-1251) and the import option semantics. Report exact byte-level evidence for any defect.'],
  ['xlsx', 'Excel .xlsx fidelity with an independent reader (zipfile+ElementTree) in addition to openpyxl: numbers vs text (17-digit doubles, large integers >2^53 and IDs with >15 digits must not be silently rounded — must be text), leading zeros, booleans, dates/datetimes/time zones (1900 date system, the 1900 leap-year bug for dates before 1900-03-01), NaN/inf (Excel cannot store them), empty vs missing, cell text limit 32,767 characters, illegal XML control characters (\\x00-\\x08, \\x0b, \\x0c, \\x0e-\\x1f — openpyxl raises IllegalCharacterError: what happens, data loss or crash?), row limit 1,048,576 and column limit 16,384 (refuse/split with a clear message, never truncate silently), sheet name rules (31 chars, []:*?/\\ , uniqueness, results sheets per analysis with long LV/RU titles), Codebook/Scales/Results/Provenance content correctness (labels, value labels, missing codes, scale items with reverse keys, result estimates vs engine unrounded values), the CSV semicolon/decimal-comma layout (numbers with thousands separators? dates?) and BOM behaviour.'],
  ['integrity', 'Data integrity and file safety: temp file + independent re-read + atomic move (Windows os.replace semantics, a target held open by Excel → PermissionError → clear message, old file intact; read-only folder; unicode/long paths; same-folder temp file); verification really independent and actually comparing content (not just row count?) — try to make a corrupted write pass verification; bundle: manifest hashes match members, dataset SHA-256 and seeds recorded, deterministic member order/timestamps if claimed, zip-slip safety on any bundle import, R syntax correctness — run Rscript on the generated syntax for the synthetic fixture and compare with the engine to 1e-9 (the claimed 29 checks), and confirm methods without syntax state a reason; the data-model change (M2): variables.label and the marked JSON in datasets.notes — never overwrite other notes text, survives restart and new dataset versions, an older RC (format 5 refuses format 6 — still true) and existing format-6 projects from 37.0a open unchanged; remembered preferences stored per user, never leak between projects in a wrong way; the identifying-column warning fires for ID/e-mail/name/free-text columns.'],
  ['integration', 'Integration and regression: the lock change (exactly one new pin pyreadstat==1.3.7 with all hashes incl. cp312 win_amd64; release date before the lock --exclude-newer; narwhals/numpy comment lines only; requirements-dev.txt byte-identical; tools/build_toolchain.py strict identity and tools/build_sbom.py pass on a simulated bundle; ReadStat MIT listed), lazy import of pyreadstat (startup time), the Export card on three pages (no rebuild while typing, keyboard, advanced options collapsed, remembered choices, disabled-state handled as text not disabled buttons since UIA reports all buttons enabled), locale audit (tools/locale_audit.py: missing 0, placeholders 0), the Windows journey export-data in tools/windows_gui_e2e.py (native Save dialog handling identical to the other journeys, files validated on disk, cleanup), the workflow path-trigger change (which workflows, does it widen correctly), the 19th-journey count conflict with claude/stage37-0b (stage37-hypothesis) and claude/stage37-rag (research-library) which also append a 19th journey — report the exact conflict and the test that pins the count; docs/STAGE37_EXPORT.md claims vs code.'],
]

phase('Verify')
const verdicts = await parallel(LENSES.map(([key, lens]) => () => agent(`${COMMON}

TASK (adversarial review, READ-ONLY): create a detached temporary worktree of ${BRANCH} under /tmp/verify-export-${key} (git -C ${ROOT} worktree add --detach /tmp/verify-export-${key} ${BRANCH}), work there with PYTHONDONTWRITEBYTECODE=1 (throwaway scripts only under /tmp/verify-export-${key}-scratch), and remove the worktree afterwards. Do not edit the branch, commit, push or post anything. Diff: git -C ${ROOT} diff ${BASE} ${BRANCH}.
Lens: ${lens}
For every candidate finding try to REFUTE it first; mark confirmed=true only with concrete evidence (file:line plus a failing command, script output or numbers). Give a red_test that fails today. List what you checked and found fine. No style nits.`, { label: `verify:${key}`, phase: 'Verify', schema: FINDINGS, agentType: 'Plan' })))

const all = verdicts.filter(Boolean)
const confirmed = all.flatMap(v => v.findings).filter(f => f.confirmed)
log(`${confirmed.length} confirmed findings (${confirmed.filter(f => f.severity !== 'minor').length} blocker/major)`)

phase('Fix')
let fixed = null
if (confirmed.length) {
  fixed = await agent(`${COMMON}

TASK (fix confirmed findings): in your worktree check out ${BRANCH} (git checkout ${BRANCH}). For each finding: reproduce it first with the red test (keep the test); fix it with the smallest correct change; if on investigation a finding is not real, record why with evidence instead of changing code. Do not touch the journey ordering beyond what a finding needs (the integrator resolves the 19th-journey merge with other branches). Do not change the lock unless a finding requires it (then regenerate with the exact header command). Run the full suite with ${PY} until green; update docs/STAGE37_EXPORT.md (limitations, done/not-done). Commit on ${BRANCH}; commits end with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015XDAvgHXs9eUoQoRrZKQA6
No push, no PR. Findings: ${JSON.stringify(confirmed)}`, { label: 'fix:export', phase: 'Fix', schema: RESULT, isolation: 'worktree' })
}
return { reviews: all, confirmed, fixed }