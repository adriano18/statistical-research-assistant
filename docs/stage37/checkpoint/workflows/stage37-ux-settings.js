export const meta = {
  name: 'stage37-ux-settings',
  description: 'Issue #68: measure 8 tasks, implement settings/startup/typography and the variable panel, merge, adversarially verify, fix',
  phases: [
    { title: 'Baseline', detail: 'metrics tool + baseline on the UX branch' },
    { title: 'Implement', detail: 'shell/settings and variable panel in parallel worktrees' },
    { title: 'Merge', detail: 'merge both, full suite, measure after' },
    { title: 'Verify', detail: 'three adversarial reviewers' },
    { title: 'Fix', detail: 'red tests and fixes for confirmed findings' },
  ],
}

const ROOT = '/home/user/statistical-research-assistant'
const SCRATCH = '/tmp/claude-0/-home-user-statistical-research-assistant/8d8df448-6aa8-50d6-b440-62d0c67e9744/scratchpad'
const PY = SCRATCH + '/venv-lock/bin/python'
const BASE = 'origin/stage37/master-acceptance-interoperability-spec'
const COMMON = `
Context: desktop app "Statistical Research Assistant" (Python, Flet 1.1.2, Windows-first, EN/LV/RU), repo ${ROOT} (git, shared object store; other agents work on other branches — never touch their branches). Code/tests/docs in English. Synthetic data only.
Python: ${PY} (3.12, all locks installed). Full suite (~17 min, must stay green): SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 <python> -m unittest discover -s tests
Read first: docs/STAGE37_NEXT_SPEC.md §3 (owner's UX requirements) and the independent review docs/STAGE37_FABLE_NARROW_REVIEW.md (read with: git -C ${ROOT} show claude/stage37-review:docs/STAGE37_FABLE_NARROW_REVIEW.md) — findings D1, D2, D6, D7, D10, D11, U1, U2, U10, U11, U12 and its UX-1/UX-2/UX-3 split.
Issue #68 requirements (owner): Research Workspace becomes the normal entry point (classic interface stays available and discoverable; never require "Open the preview" each start). Top bar shows EN and LV quick choices; Russian stays fully supported via Settings → Language (an understandable language/globe menu is fine); an existing RU preference must survive upgrades and never be silently reset (app_preferences.py resets unknown languages to English — RU is known; keep it so). Classic native Windows look: Segoe UI / Segoe UI Variable with robust fallback and correct LV/RU glyphs, no bundled proprietary fonts. Text size 90/100/110/125 % and comfortable/compact density. One Settings hub: theme (light/dark/system), accent, language, typography/scale, density, start interface, local project folder (shown, openable), backups, recent projects, update channel (only what the updater supports), AI privacy (link to the existing AI settings). Per-user settings that survive restart and update; clear "Reset settings" vs "Delete research data". Save window size/position, sidebar state and last page. Never hide or bypass mandatory scientific confirmations to reduce clicks.
Windows journeys: tools/windows_gui_e2e.py (JOURNEYS dict; append new journeys after the existing ones); prove each with a harness walk test like tests/test_stage368_acceptance.py and tests/test_stage368_review_journeys.py. UI Automation reports every button as enabled (never assert disabled); the mouse wheel over an inner list scrolls the list, not the page. Journeys currently start the app with SRA_UI=workspace (tools/windows_gui_e2e.py ~line 232); the windows workflows (.github/workflows/windows-*.yml) contain classic-interface start checks — if the default start changes, update them consistently so no installer/update/GUI check regresses.
Rules: never open ${SCRATCH}/private or /root/.claude/uploads; no push, no PR; commits end with exactly these two lines:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015XDAvgHXs9eUoQoRrZKQA6
New UI strings: keys in EN/LV/RU (LV/RU marked as drafts for native review); keep existing data keys and the English texts journeys use.`

const RESULT = {
  type: 'object',
  properties: {
    branch: { type: 'string' },
    commits: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    tests: { type: 'string' },
    not_done: { type: 'array', items: { type: 'string' } },
    behaviour_changes: { type: 'array', items: { type: 'string' } },
  },
  required: ['branch', 'commits', 'summary', 'tests', 'not_done'],
}
const BASELINE = {
  type: 'object',
  properties: {
    branch: { type: 'string' },
    commit: { type: 'string' },
    command: { type: 'string' },
    tasks: { type: 'array', items: { type: 'object', properties: {
      task: { type: 'string' }, persona: { type: 'string' }, interactions: { type: 'number' },
      typed: { type: 'number' }, page_changes: { type: 'number' }, dialogs: { type: 'number' },
      repeated_selections: { type: 'number' }, focus_losses: { type: 'number' }, scroll_note: { type: 'string' } },
      required: ['task', 'persona', 'interactions'] } },
    notes: { type: 'string' },
  },
  required: ['branch', 'commit', 'command', 'tasks'],
}
const FINDINGS = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, severity: { type: 'string' }, area: { type: 'string' },
      file_line: { type: 'string' }, claim: { type: 'string' }, evidence: { type: 'string' },
      red_test: { type: 'string' }, confirmed: { type: 'boolean' } },
      required: ['id', 'severity', 'claim', 'evidence', 'confirmed'] } },
  },
  required: ['findings'],
}

phase('Baseline')
const base = await agent(`${COMMON}

TASK (baseline only): in your worktree, git fetch origin stage37/master-acceptance-interoperability-spec and create branch claude/stage37-ux from ${BASE} (2f9af71). Build tools/ux_metrics.py: a reproducible interaction counter that drives the REAL handlers through tests/workspace_harness.py (reuse docs/stage37/measure_baseline.py and tools/workspace_scenarios.py counting rules: click/checkbox = 1, dropdown = 2; count typed fields, page changes and system dialogs separately). Measure 8 representative tasks, 4 novice and 4 supervisor, on the synthetic master fixture (generate with tests/fixtures/stage37/generate_master_fixture.py into a temp dir) and the Stage 36 fixtures: (1) first start to an open project with data; (2) confirm measurement levels for the 98-variable file; (3) define/score one 20-item scale and check its reliability; (4) eight correlations in one batch and add to report; (5) repeat a previous analysis with one variable changed; (6) export the Word report; (7) supervisor: reopen the project after a restart and review all results; (8) supervisor: change language/text size and continue. Also count repeated variable selections (the same variable ticked again across tasks) and focus losses (a focused field rebuilt by a render). Scrolling cannot be measured in the harness: record a scroll estimate from control counts/heights and say so. Add a unit test that the tool runs. Write docs/STAGE37_UX_METRICS.md with the baseline table and method. Commit on claude/stage37-ux. Return the branch, the commit SHA, the exact command and the numbers.`, { label: 'baseline:metrics', phase: 'Baseline', schema: BASELINE, isolation: 'worktree' })

if (!base) { return { error: 'baseline agent failed' } }
log(`Baseline on ${base.branch} @ ${base.commit}: ${base.tasks.length} tasks measured`)
const baseNote = `The UX branch claude/stage37-ux has commit ${base.commit} with tools/ux_metrics.py (run: ${base.command}) and docs/STAGE37_UX_METRICS.md (baseline). Baseline numbers: ${JSON.stringify(base.tasks)}`

phase('Implement')
const [shell, vars] = await parallel([
  () => agent(`${COMMON}

${baseNote}
TASK (shell, settings, language, typography): in your worktree create branch claude/stage37-ux-shell from claude/stage37-ux (git fetch not needed; it is a local branch of the shared repo). Implement:
1) One per-user settings store (migrate from ~/.statistical_research_assistant/preferences.json, workspace.json and the profile's language without loss; tests for migration and that unknown/RU values are never rewritten); fix D1 (language chosen in the workspace persists without a profile) and D2 (theme, window size/position, sidebar state, last page persist).
2) Start interface setting: Research workspace by default for new and existing users (no stored choice exists today), classic interface one click away (Settings and sidebar/Help) and selectable as start interface; remove the "Preview"/"Prototype" labels from the workspace once it is the default; document parity status (which features exist only in classic) in docs.
3) Top bar: EN and LV quick buttons; Russian via Settings → Language and an understandable globe/language menu; an existing RU preference starts the app in Russian and is never reset; harness tests incl. a simulated upgrade with {"language": "ru"}.
4) Typography: Segoe UI / Segoe UI Variable with a fallback list (no font files bundled), text size 90/100/110/125 % applied through the Ui tokens/wc.text, comfortable/compact density through spacing/control-height tokens; chart default font Segoe UI where matplotlib finds it, else DejaVu Sans (do not break chart tests); fix D6 contrast in preparation_ui.py captions, D11 plural/mixed-language on Reports, U10 question field width, U11 focus management for the main actions (create project/analysis, dialogs) where Flet supports .focus().
5) Settings hub sections listed in the requirements (export defaults and research-library privacy will be added by other PRs: provide a small section registry so they can plug in with one entry).
6) Windows journeys: startup-workspace (installed/packaged program starts in the workspace without SRA_UI; classic reachable; the choice persists) and settings-language (RU preference survives; top bar EN/LV only; switch to LV, restart, LV; text size 125 % visible); update workflow start checks consistently.
Run the full suite and tools/ux_metrics.py; commit on claude/stage37-ux-shell. Return branch, commits, tests, not done and behaviour changes.`, { label: 'implement:shell', phase: 'Implement', schema: RESULT, isolation: 'worktree' }),
  () => agent(`${COMMON}

${baseNote}
TASK (variable selection and repetition): in your worktree create branch claude/stage37-ux-vars from claude/stage37-ux (local branch of the shared repo). Implement Fable UX-3 and the repetition reductions of Issue #68:
1) A reusable variable panel for role pickers in Analyze (and the item-set picks used for scales/reliability): search, prefix selection (e.g. all SYN_COPE_0*), range selection (first..last in column order), select-all of the filtered set, clear, and a visible count; only eligible variables are listed for each role (fix D7: the grouping variable and the outcome itself are not offered as covariates; the reason for an excluded variable is available as text, never silently dropped).
2) Reuse: duplicate/clone a previous analysis into a new task with the same variables (confirmations are NOT copied — they stay bound to their scope as K1 requires; the user re-confirms), recent methods, and remembered last choices where they do not bypass a confirmation.
3) Keyboard: the panel is reachable and usable by keyboard (Tab order, Enter/Space), names exposed to UI Automation.
4) Windows journey variable-picker: select a 20-item set by prefix in one action, run reliability, clone the task with one variable changed — counts recorded; harness walk test.
Run the full suite and tools/ux_metrics.py (tasks 3 and 5 must improve; record before/after); commit on claude/stage37-ux-vars. Return branch, commits, tests, not done and behaviour changes.`, { label: 'implement:variables', phase: 'Implement', schema: RESULT, isolation: 'worktree' }),
])
log(`shell: ${shell ? shell.branch : 'FAILED'}; variables: ${vars ? vars.branch : 'FAILED'}`)

phase('Merge')
const merged = await agent(`${COMMON}

TASK (merge and measure): in your worktree check out claude/stage37-ux (local branch, commit ${base.commit}). Merge ${shell ? shell.branch : '(shell branch missing — skip)'} and then ${vars ? vars.branch : '(variables branch missing — skip)'} with git merge --no-ff (no rebase, no force), resolving conflicts carefully (keep both features; text tables keep every key). Implementer reports: SHELL=${JSON.stringify(shell)} VARIABLES=${JSON.stringify(vars)}. Then run the full suite until green (fix only integration breakage, with tests), run ${base.command} for the after numbers, and update docs/STAGE37_UX_METRICS.md with a before/after table per task (never claim a reduction that hides a mandatory confirmation: list the confirmations still required per task). Add docs/STAGE37_UX_SETTINGS.md: what changed, settings migration, start interface and parity status, language rules, typography, density, keyboard/focus, known limits. Commit on claude/stage37-ux. Return branch, commits, tests (counts), not done.`, { label: 'merge:ux', phase: 'Merge', schema: RESULT, isolation: 'worktree' })

phase('Verify')
const LENSES = [
  ['correctness', 'Correctness and regression: settings migration (no lost preference, RU never reset, unknown values kept), start-interface default and the classic path, window/sidebar persistence, startup on Windows paths, workflow start checks, journeys still valid, upgrade from an RC-era preferences file, Reset settings never deletes research data.'],
  ['a11y-i18n', 'Accessibility, language and display: UI Automation names of new controls, keyboard reachability and focus order, contrast of new colours (compute with the repo formula), text size 90-125 % without clipping at 1097x617 logical px (175 % on 1080p), EN/LV/RU coverage of every new string (tools/locale_audit.py), the top bar EN/LV + globe menu behaviour.'],
  ['science', 'Scientific integrity of the UX changes: no mandatory design/data confirmation hidden, skipped or copied by clone/presets/remembered choices (K1 scopes still enforced), eligibility filtering never removes a variable silently or wrongly (types, levels), item-range/prefix selection cannot mix scales without showing it, measurement claims in docs/STAGE37_UX_METRICS.md are reproducible with the tool.'],
]
const verdicts = await parallel(LENSES.map(([key, lens]) => () => agent(`${COMMON}

TASK (adversarial review, READ-ONLY): review branch claude/stage37-ux against claude/stage37-ux~ (its baseline commit ${base.commit}) — use git -C ${ROOT} diff ${base.commit} claude/stage37-ux, git show, and run tests/harness with PYTHONDONTWRITEBYTECODE=1 against a detached temporary worktree you create under /tmp/ux-review-${key} (remove it afterwards). Do not edit the branch, commit, push or post anything. Lens: ${lens}
For every finding: try to REFUTE it first; mark confirmed=true only with concrete evidence (file:line, a failing command or harness output). Give a red_test that would fail today. Report only confirmed or high-likelihood issues; no style nits.`, { label: `verify:${key}`, phase: 'Verify', schema: FINDINGS, agentType: 'Plan' })))
const confirmed = verdicts.filter(Boolean).flatMap(v => v.findings).filter(f => f.confirmed)
log(`${confirmed.length} confirmed findings across ${LENSES.length} lenses`)

phase('Fix')
let fixed = null
if (confirmed.length) {
  fixed = await agent(`${COMMON}

TASK (fix confirmed review findings): in your worktree check out claude/stage37-ux. For each finding below, reproduce it with the red test first (keep the test), then fix it; if after investigation a finding is not real, say why with evidence instead of changing code. Run the full suite until green and re-run ${base.command}; update docs/STAGE37_UX_METRICS.md and docs/STAGE37_UX_SETTINGS.md if numbers or behaviour change. Commit on claude/stage37-ux. Findings: ${JSON.stringify(confirmed)}`, { label: 'fix:findings', phase: 'Fix', schema: RESULT, isolation: 'worktree' })
}
return { baseline: base, shell, vars, merged, findings: confirmed, fixed }