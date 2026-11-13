export const meta = {
  name: 'verify-stage37-0b',
  description: 'Adversarially verify the Stage 37.0b branch through four lenses, then fix confirmed findings with red tests',
  phases: [
    { title: 'Verify', detail: 'four independent read-only reviewers' },
    { title: 'Fix', detail: 'red tests and fixes for confirmed findings' },
  ],
}

const ROOT = '/home/user/statistical-research-assistant'
const SCRATCH = '/tmp/claude-0/-home-user-statistical-research-assistant/8d8df448-6aa8-50d6-b440-62d0c67e9744/scratchpad'
const PY = SCRATCH + '/venv-lock/bin/python'
const BRANCH = 'claude/stage37-0b'
const BASE = '2f9af71'
const COMMON = `
Context: desktop app "Statistical Research Assistant" (Python, Flet 1.1.2, Windows-first, EN/LV/RU), repo ${ROOT} (shared object store; other agents work on other branches — never touch them). Branch under review: ${BRANCH} (4 commits on ${BASE}: Stage 37.0b — hypothesis rows in the Word research report, the editable "Hypotheses and evidence" table, Windows journey stage37-hypothesis, planned-variables editor, journey strip from task_steps, next-action footer bar, in-task review, step-4 plan checks, copy for an older version (format-5 .sra without protocol records), Q1 by default, and review fixes D3 D4 D5 D9 D12 S8 S14 S16 S17). Its own status doc: docs/STAGE37_0B_STATUS.md; the independent review: docs/STAGE37_FABLE_NARROW_REVIEW.md (git -C ${ROOT} show claude/stage37-review:docs/STAGE37_FABLE_NARROW_REVIEW.md).
Python: ${PY} (3.12, all locks). Full suite: SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 <python> -m unittest discover -s tests (~18 min). Synthetic data only; never open ${SCRATCH}/private or /root/.claude/uploads.`

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
  ['audit', 'Audit integrity and storage: protocol records stay append-only (triggers, no update/delete path anywhere, run_id now written), every research decision and deviation is recorded with its reason and cannot be silently overwritten (S8: wording/direction/α/priority changes after results need a reason; H-PLAN-CHANGED compares snapshots), hypothesis snapshots are immutable, migrations 1–5 → 6 keep a backup and a failed migration leaves the old format, the .sra backup round-trip keeps every record and the triggers, the copy for an older version never alters the original, warns with the count of omitted records and is refused/migrated correctly when it comes back. Also S15 (notes/review ticks overwritten without history) — state whether this branch makes it worse.'],
  ['report', 'Word report correctness: each hypothesis block and the "Hypotheses and evidence" table carry only engine-saved numbers (cross-check against the stored results), never "supported"/"confirmed" or causal wording in EN/LV/RU, stale vs current status is right after data changes, deviations/acknowledgements/open checks appear (S14), no duplicated paragraphs (#8), A4 and Heading 3 (D9), a report without hypotheses is unchanged in content and numbering, editable tables (python-docx reads them).'],
  ['workflow', 'Workflow and UX regression: next-action footer bar (never a disabled button, never bypasses a confirmation, right next action for multi-task hypotheses — D4), journey strip from task_steps, D5 (a task renamed to what it runs; every result keeps its own specification and title), S16 rule (only inferential runs make a hypothesis "added after results" — check the classification of every method key), S17 drafts, step-4 plan checks, the in-task review bound to the same persisted state as Results (restart round-trip), K1 confirmation scopes unaffected, the 18 earlier harness journeys still valid.'],
  ['windows', 'Windows journey robustness: review tools/windows_gui_e2e.py journey stage37-hypothesis and the driver change for the sticky footer against known pitfalls — UI Automation reports every button as enabled (never assert disabled), the mouse wheel over an inner list scrolls the list not the page, controls under a sticky footer, Save/Open dialogs, restart handling, timing; confirm tests/test_stage37_journey.py walks the same texts/states; flag any step likely to fail on the packaged Windows program with concrete reasoning.'],
]

phase('Verify')
const verdicts = await parallel(LENSES.map(([key, lens]) => () => agent(`${COMMON}

TASK (adversarial review, READ-ONLY): create a detached temporary worktree of ${BRANCH} under /tmp/verify-0b-${key} (git -C ${ROOT} worktree add --detach /tmp/verify-0b-${key} ${BRANCH}), run what you need there with PYTHONDONTWRITEBYTECODE=1, and remove the worktree afterwards (git worktree remove --force). Do not edit the branch, commit, push or post anything. Read the diff: git -C ${ROOT} diff ${BASE} ${BRANCH}.
Lens: ${lens}
For every candidate finding try to REFUTE it first; mark confirmed=true only with concrete evidence (file:line plus a failing command, script output or test). Give a red_test that fails today. Also list what you checked and found fine. No style nits.`, { label: `verify:${key}`, phase: 'Verify', schema: FINDINGS, agentType: 'Plan' })))

const all = verdicts.filter(Boolean)
const confirmed = all.flatMap(v => v.findings).filter(f => f.confirmed)
log(`${confirmed.length} confirmed findings (${confirmed.filter(f => f.severity !== 'minor').length} blocker/major)`)

phase('Fix')
let fixed = null
if (confirmed.length) {
  fixed = await agent(`${COMMON}

TASK (fix confirmed findings): in your worktree check out ${BRANCH} (local branch of the shared repo; git checkout ${BRANCH}). For each finding: reproduce it first with the red test (keep the test); fix it; if on investigation a finding is not real, record why with evidence instead of changing code. Keep format 6, the immutable records, snapshots, backups and provenance; no engine/analysis_runs/installer/updater/workflow/lock changes. Run the full suite until green. Update docs/STAGE37_0B_STATUS.md. Commit on ${BRANCH}; commits end with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015XDAvgHXs9eUoQoRrZKQA6
No push, no PR. Findings: ${JSON.stringify(confirmed)}`, { label: 'fix:0b', phase: 'Fix', schema: RESULT, isolation: 'worktree' })
}
return { reviews: all, confirmed, fixed }