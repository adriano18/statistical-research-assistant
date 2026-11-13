export const meta = {
  name: 'verify-stage37-methods',
  description: 'Adversarially verify the research-methods branch (numerics, wording, locks, integration), then fix confirmed findings',
  phases: [
    { title: 'Verify', detail: 'four independent read-only reviewers' },
    { title: 'Fix', detail: 'red tests and fixes for confirmed findings' },
  ],
}

const ROOT = '/home/user/statistical-research-assistant'
const SCRATCH = '/tmp/claude-0/-home-user-statistical-research-assistant/8d8df448-6aa8-50d6-b440-62d0c67e9744/scratchpad'
const PY = SCRATCH + '/venv-lock/bin/python'
const BRANCH = 'claude/stage37-methods'
const BASE = '2f9af71'
const COMMON = `
Context: desktop app "Statistical Research Assistant" (Python, Flet 1.1.2, Windows-first, EN/LV/RU), repo ${ROOT} (shared object store; never touch other branches). Branch under review: ${BRANCH} on ${BASE} (Issue #66): process_models.py (PROCESS-style Models 1, 4, 7, 14 with percentile bootstrap, simple slopes, Johnson–Neyman for Model 1, index of moderated mediation, conditional indirect effects), linear_model.py (categorical covariates as dummies with a stated reference), process_text/process_reporting/process_charts, workspace methods linear_model/mediation/moderation/conditional_process and a "process" goal with design confirmations (mediators named before results, cross-sectional limit, moderator named before results, Model 7 vs 14 chosen by the researcher with no default), Spearman permutation-floor note (S10), H1–H6 synthetic acceptance (tests/test_stage37_master_acceptance.py, tests/fixtures/stage37/synthetic_construct_mapping.json, docs/STAGE37_MASTER_ACCEPTANCE.md, docs/STAGE37_METHODS.md), fixture v2 generator, and as the LAST commit the licence path (cronbach.py replaces pingouin at runtime; pingouin moved to the dev lock; both hashed locks regenerated; python-tests.yml installs the dev lock for the unit job).
Fixtures: tests/fixtures/stage37/generate_master_fixture.py (owner's v1; 180 synthetic cases) and generate_master_fixture_v2.py.
Python: ${PY} (3.12; NOTE this venv still has pingouin installed — use it as an oracle only). Full suite: SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 <python> -m unittest discover -s tests (~18 min). Synthetic data only; never open ${SCRATCH}/private or /root/.claude/uploads.`

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
  ['numerics', 'Independent numerical verification. Write YOUR OWN oracle code from textbook formulas (do NOT import or copy the branch\'s test oracles): OLS via numpy lstsq/statsmodels formulas for every path of Models 1, 4 (simple and parallel, with covariates age, sex, employment as dummies), 7 and 14 on the v1 and v2 fixtures (listwise); indirect effects a*b, total = c\' + sum(ab); simple slopes at mean±1 SD and 16/50/84th percentiles (type 7); Johnson–Neyman boundaries by solving t(b1+b3*W)=t_crit; index of moderated mediation (a3*b for Model 7, a*b3 for Model 14); conditional indirect effects; the linear model with Treatment dummies and reference categories; HC3 where offered; Cronbach α and Feldt CI from the formulas (and pingouin as a second oracle). Compare with the branch\'s engine outputs to 1e-9 (point estimates/SEs). For bootstrap CIs: check the resampling is a proper case bootstrap with a fixed reported seed and B, reproducible across runs, percentile type documented, and that your own bootstrap with a different RNG lands within Monte Carlo error. Report any deviation with numbers.'],
  ['science', 'Scientific integrity and wording: Model numbers are never auto-selected (grep every recommender/advise/default path; the 7/14 option has no default and the run refuses without a choice — including Ctrl+Enter, Run again, clone and the all-methods form, since UI Automation reports disabled buttons as enabled); mediators are never screened by p-values; no causal wording in EN/LV/RU templates, reports, docs (search for cause/effect-of/leads to/izraisa/вызывает/приводит etc. and judge context); suppression wording when ab and c/c\' differ in sign; cross-sectional limit stated; everything labelled synthetic in the acceptance doc and outputs, never described as empirical findings; PROCESS wording says "structure equivalent to … computed by this program, not by the PROCESS macro"; sensitivity/power simulation clearly labelled; missing-data policy explicit.'],
  ['locks', 'Dependency, licence and packaging: the regenerated runtime lock removes exactly pingouin and its exclusive dependents with every other pin byte-identical (versions, markers, hashes), the dev lock adds the same versions/hashes, the --exclude-newer and flags match the header; no runtime import of pingouin/seaborn/sklearn/xarray/tabulate anywhere (including lazy imports, item_diagnostics, chart code, research_app, app.py comments are fine); tools/build_toolchain.py identity/strict and tools/build_sbom.py still pass with the new lock (run them on a simulated bundle if possible); docs (STAGE368_BUILD_LOCK licence section or the new docs) state the owner\'s licence decision is still open and no LICENSE file was added; python-tests.yml change is minimal and does not make the pruned-runtime job install the dev lock; size impact noted.'],
  ['integration', 'Workspace integration and regression: new methods appear only where eligible; role eligibility (categorical vs scale; no outcome as covariate); K1 confirmation scopes apply to the new design/data confirmations (change of mediator/moderator/model clears the right ones); structured results stored, restored after restart, shown in Results and the Word report (with tables editable), report texts EN/LV/RU (run tools/locale_audit.py: missing and placeholder must stay 0); the method catalog count change (18 → 22 cards) does not break the Windows journeys in tools/windows_gui_e2e.py (check any card-count or index-based selection); hypothesis linking (37.0a snapshot) works for the new methods; no regression in the existing 18 journeys\' harness walks.'],
]

phase('Verify')
const verdicts = await parallel(LENSES.map(([key, lens]) => () => agent(`${COMMON}

TASK (adversarial review, READ-ONLY): create a detached temporary worktree of ${BRANCH} under /tmp/verify-methods-${key} (git -C ${ROOT} worktree add --detach /tmp/verify-methods-${key} ${BRANCH}), work there with PYTHONDONTWRITEBYTECODE=1 (throwaway scripts only under /tmp/verify-methods-${key}-scratch), and remove the worktree afterwards. Do not edit the branch, commit, push or post anything. Diff: git -C ${ROOT} diff ${BASE} ${BRANCH}.
Lens: ${lens}
For every candidate finding try to REFUTE it first; mark confirmed=true only with concrete evidence (file:line plus a failing command, script output or numbers). Give a red_test that fails today. List what you checked and found fine. No style nits.`, { label: `verify:${key}`, phase: 'Verify', schema: FINDINGS, agentType: 'Plan' })))

const all = verdicts.filter(Boolean)
const confirmed = all.flatMap(v => v.findings).filter(f => f.confirmed)
log(`${confirmed.length} confirmed findings (${confirmed.filter(f => f.severity !== 'minor').length} blocker/major)`)

phase('Fix')
let fixed = null
if (confirmed.length) {
  fixed = await agent(`${COMMON}

TASK (fix confirmed findings): in your worktree check out ${BRANCH} (git checkout ${BRANCH}). For each finding: reproduce it first with the red test (keep the test); fix it with the smallest correct change; if on investigation a finding is not real, record why with evidence instead of changing code. Keep the licence-path commit last if you can (put fixes that belong to it in a new commit at the end and say so). Do not refactor validated algorithms beyond the fix. Run the full suite until green; update docs/STAGE37_METHODS.md. Commit on ${BRANCH}; commits end with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015XDAvgHXs9eUoQoRrZKQA6
No push, no PR. Findings: ${JSON.stringify(confirmed)}`, { label: 'fix:methods', phase: 'Fix', schema: RESULT, isolation: 'worktree' })
}
return { reviews: all, confirmed, fixed }