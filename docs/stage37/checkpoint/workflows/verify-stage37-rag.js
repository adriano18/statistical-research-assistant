export const meta = {
  name: 'verify-stage37-rag',
  description: 'Adversarially verify the local research library (privacy, injection, storage, retrieval, integration), then fix confirmed findings',
  phases: [
    { title: 'Verify', detail: 'five independent read-only reviewers' },
    { title: 'Fix', detail: 'red tests and fixes for confirmed findings' },
  ],
}

const ROOT = '/home/user/statistical-research-assistant'
const SCRATCH = '/tmp/claude-0/-home-user-statistical-research-assistant/8d8df448-6aa8-50d6-b440-62d0c67e9744/scratchpad'
const PY = SCRATCH + '/venv-lock/bin/python'
const BRANCH = 'claude/stage37-rag'
const BASE = '2f9af71'
const COMMON = `
Context: desktop app "Statistical Research Assistant" (Python, Flet 1.1.2, Windows-first, EN/LV/RU), repo ${ROOT} (shared object store; never touch other branches). Branch under review: ${BRANCH} on ${BASE} (Issue #69, local research library MVP), 8 commits: identifier/free-text columns left out of AI data rows (red tests then fix); a per-project research library (<project>/library/library.sqlite3, schema v1, sources/<sha256><ext>), PDF/DOCX/MD/TXT reading with page/section-aware passages and stable cite IDs, SHA-256 dedupe, versions, reindex, remove; SQLite FTS5 (unicode61 remove_diacritics 2, multilingual stems as prefix queries, ё→е) with a pure-Python BM25 fallback; a Research Library page (Add with progress/Cancel, offline search with filters, "Why this source?", citations open the PDF at the page, Remove); "Ask with sources" (only ticked passages + question after an exact preview, byte-identical request, per-request consent, passages inside quoted <source> elements, citation/quote/number checks, no data rows, no calculations, activity log with cite IDs only); per-project checkbox (default off) to include library files in .sra backups/copies; packaged self-test FTS5 check; Windows journey "research-library" appended as the 19th journey; docs/STAGE37_RAG.md (benchmark: 51 synthetic passages, 51 queries EN/LV/RU, 13 configurations).
Product rules to hold it against: search works without internet or AI credentials; project isolation; deletion and reindexing; provenance and hashes; AI answers must cite retrieved passages; untrusted document text is never treated as instructions; raw participant records and full libraries are never sent without explicit consent and payload preview; the deterministic statistics engine stays the only source of computed results; embeddings only after proven benefit (none shipped).
Python: ${PY} (3.12). Full suite: SRA_REQUIRE_REAL_OCR=1 MPLBACKEND=Agg PYTHONUTF8=1 <python> -m unittest discover -s tests (~18 min). Synthetic data only; never open ${SCRATCH}/private or /root/.claude/uploads.`

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
  ['privacy', 'Privacy and egress. Prove or refute: (a) no code path of add/search/why/render/reindex/remove/backup/open-citation can open a network connection (look for any requests/httpx/urllib/socket use, OCR or PDF libraries fetching, provider warm-ups, update checks triggered from the page); (b) the Ask request that leaves is byte-identical to the preview for every provider adapter (OpenAI-, Anthropic-, Gemini-style and any other in the AI module), including headers/system prompt, and a change of ticked passages, question, provider or model after the preview invalidates consent; (c) consent is per request (a second Send or a retry/timeout path cannot resend without a new approval; the RC fixed a 4x-resend-on-timeout bug — check the new path); (d) data rows, results, file paths, project names, researcher profile fields are never in the payload; (e) logs contain cite IDs only; (f) the AI-rows fix: identifier and free-text detection is neither too weak (numeric participant codes, e-mail-like strings, UUIDs, long free text bulk-confirmed as categories) nor drops ordinary Likert/numeric columns, and the preview/Settings name the dropped columns. Write throwaway scripts with a socket/connect monkeypatch guard.'],
  ['injection', 'Untrusted input. (a) Search queries reach FTS5 MATCH: try quotes, unbalanced quotes, AND/OR/NOT/NEAR(, column filters (title:, cite_id:), ^, *, -, parentheses, very long queries, NUL, emoji, RTL marks, only punctuation, SQL meta characters — no exception reaches the UI, no syntax is interpreted, and the fallback is the same; (b) prompt injection: documents containing "</source>", variants with whitespace/case/unicode lookalikes/entities, "[S9]" fake citations, "ignore previous instructions", fake system/assistant turns, tool-call-shaped JSON, markdown links/images with URLs that could exfiltrate when rendered, very long passages — check the escaping really cannot be closed, rendered answers do not auto-load remote content, and nothing in a document or answer can change settings, permissions, the library or trigger a second request; (c) file names and metadata: path traversal or reserved Windows names (CON, aux.pdf, trailing dots/spaces, ADS "a.pdf:x"), very long names, duplicate names, symlinks — the stored copy path is only the hash; (d) hostile files: encrypted PDF, broken xref, huge page count, decompression bomb (pypdf/pypdfium2 limits), DOCX zip bomb or XXE/external entities in DOCX XML, non-UTF-8 TXT — bounded time/memory and a clear message, no crash, no partial library.'],
  ['storage', 'Storage, isolation and integrity. (a) project isolation: two projects never see each other\'s documents (search, why, ask, backup, copy); a library path cannot escape its project; (b) remove deletes passages, FTS rows, the stored copy (also when held open on Windows semantics — read the fix 907d516) and does not delete a copy still used by another document version; dedupe/version semantics; (c) reindex and reindex-all are idempotent and restore exact passages and cite IDs; cite IDs stable across reindex, app restart and backup restore; (d) a library with a newer schema version is refused without writing (check that opening even read-only does not create WAL/SHM or migrate); corrupt library.sqlite3 gives a message, not a crash, and does not corrupt the project; (e) concurrency: two adds, add during search, cancel mid-add leaves no half-indexed document; (f) the backup checkbox: default off, included only when on, restore/copy round trip, and the project format 6 / .sra format are unchanged as claimed (diff project_store and package code); (g) disk usage: stored copies counted, large libraries do not load everything in memory.'],
  ['retrieval', 'Retrieval correctness. (a) Re-run the benchmark yourself and confirm every number in docs/STAGE37_RAG.md (R@1/3/5, MRR per language, the 13 configurations, index size and timing ratios); (b) look for over-stemming false positives: very short stems used as prefix queries (e.g. 1–3 letter stems, stems of stop words) matching a large share of passages — measure precision on queries for absent concepts; LV and RU suffix rules on real morphology (ā/ē/ī/ū, ļ/ņ/ķ/ģ/š/ž/č; падежи) — write 30+ of your own word pairs that should and should not match; (c) the pure-Python BM25 fallback really equals FTS5 bm25() ordering and scores (also on ties, empty queries, column weights) beyond the 51 queries; (d) passage slicing: exact slices of the stored page text, never crossing pages/sections, no lost text at boundaries, offsets correct with combining characters/ligatures/hyphenation; page numbers physical; (e) the packaged-runtime claim: find the pinned python-windows-for-dart 3.12.16 archive (see the toolchain lock/cache files and .github/actions) and verify FTS5 support of its sqlite3.dll from bytes if available locally; if not available, say so; check the self-test hash change cannot make the existing --compare step fail spuriously between the CI Python and the packaged runtime.'],
  ['integration', 'Integration and regression. (a) tools/locale_audit.py: missing and placeholder counts stay 0 and new texts are in EN/LV/RU; (b) the page integrates without rebuilding while typing (search field keeps focus and caret), keyboard reachability, Ctrl+1…6 unchanged, 125 %/175 % layout reasoning; (c) the Results-page assistant quote checks do not regress the RC AI gate tests (tests/test_stage368_ai_gate*.py or similar) or change prompts byte-wise where tests pin them; (d) the Windows journey research-library in tools/windows_gui_e2e.py: selectors exist, file dialogs handled like other journeys, disk checks correct, cleanup leaves no state that breaks later journeys, and appending it as #19 vs other Stage 37 branches that also append a 19th journey (stage37-hypothesis on claude/stage37-0b) — report the exact merge conflict risk and the test that pins the count; (e) packaged self-test change: tools/ or app self-test code path still runs in the packaged build without extra imports, and the expected-hash file update is consistent; (f) nothing in research_app.py classic interface broke; (g) PROJECTS_ARCHITECTURE.md and STAGE37_RAG.md claims match code.'],
]

phase('Verify')
const verdicts = await parallel(LENSES.map(([key, lens]) => () => agent(`${COMMON}

TASK (adversarial review, READ-ONLY): create a detached temporary worktree of ${BRANCH} under /tmp/verify-rag-${key} (git -C ${ROOT} worktree add --detach /tmp/verify-rag-${key} ${BRANCH}), work there with PYTHONDONTWRITEBYTECODE=1 (throwaway scripts only under /tmp/verify-rag-${key}-scratch), and remove the worktree afterwards. Do not edit the branch, commit, push or post anything. Diff: git -C ${ROOT} diff ${BASE} ${BRANCH}.
Lens: ${lens}
For every candidate finding try to REFUTE it first; mark confirmed=true only with concrete evidence (file:line plus a failing command, script output or numbers). Give a red_test that fails today. List what you checked and found fine. No style nits.`, { label: `verify:${key}`, phase: 'Verify', schema: FINDINGS, agentType: 'Plan' })))

const all = verdicts.filter(Boolean)
const confirmed = all.flatMap(v => v.findings).filter(f => f.confirmed)
log(`${confirmed.length} confirmed findings (${confirmed.filter(f => f.severity !== 'minor').length} blocker/major)`)

phase('Fix')
let fixed = null
if (confirmed.length) {
  fixed = await agent(`${COMMON}

TASK (fix confirmed findings): in your worktree check out ${BRANCH} (git checkout ${BRANCH}). For each finding: reproduce it first with the red test (keep the test); fix it with the smallest correct change; if on investigation a finding is not real, record why with evidence instead of changing code. Do not touch the journey ordering beyond what a finding needs (the integrator resolves the 19th-journey merge with other branches). Run the full suite until green; update docs/STAGE37_RAG.md (limitations and the done/not-done table). Commit on ${BRANCH}; commits end with exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_015XDAvgHXs9eUoQoRrZKQA6
No push, no PR. Findings: ${JSON.stringify(confirmed)}`, { label: 'fix:rag', phase: 'Fix', schema: RESULT, isolation: 'worktree' })
}
return { reviews: all, confirmed, fixed }