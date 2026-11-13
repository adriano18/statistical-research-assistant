# Stage 36.8 — AI release-safety gate (issue #62, Part 9)

**Verified:** the release candidate `claude/stage368-rc` at `216353d`.
**Branch:** `claude/stage368-ai-gate`.
**Tests:**
- `tests/test_stage368_ai_gate.py` — one class per gate, plus supporting classes;
- `tests/test_stage368_ai_live.py` — an optional live smoke test that never runs in public CI.

**Result in one paragraph.** All ten gates pass on this branch, against mocked provider APIs only. On the RC head as delivered, three gates failed:
- gate 2: a model that refuses a text request was reported as a provider "server error";
- gate 5: Send could go to a different provider or model than the preview named;
- gate 7: timeouts were reported as "offline" after four paid attempts, and a cut-off reply crashed Test connection.

The gate-9 test found a fourth defect: a request that is still out when the researcher switches projects was recorded nowhere. Each defect has a minimal fix in the AI modules and a test that failed on `216353d` and passes now (section 4).

No real provider and no packaged EXE were tested (section 5). In the packaged build the assistant is **not** enabled by default (section 3), and it stays that way for the Preview RC.

## 1. The gates

The statuses are those of these tests:
- **RC `216353d`**: the RC head with the new tests copied in;
- **this branch**: after the fixes.

"Existing" names tests that already proved part of a gate. The new class references them and does not repeat them.

| # | Gate | RC `216353d` | This branch | Proven by (`tests/test_stage368_ai_gate.py`) | Existing tests relied on |
|---|---|---|---|---|---|
| 1 | Model discovery through the existing adapters; models fetched, not hard-coded | passed | **passed** | `Gate01ModelDiscoveryTests`: Settings → AI providers lists exactly the models each of the three providers returns, with model IDs invented while the test runs. Each listing goes to the provider's own HTTPS host with the key in its header, no body, the 30 s time limit and certificate checks. The chosen model is saved, and the list is cached. No model ID literal appears in the AI modules or in the AI texts. | `test_ai_providers` (model filter, cache), `test_workspace_ai` |
| 2 | Unsupported models and capabilities | **failed** | **passed** | `Gate02UnsupportedModelTests`: embedding, speech, image, moderation, realtime, search and computer-use models, and Gemini models without `generateContent`, are not offered. A key with no text model: "This key can use no text model." A typed model the provider does not know (HTTP 404): "does not know the model", Open Settings, one attempt, audited. A **listed model that refuses a text request (HTTP 400)**: now "refused this request for the model … choose another model" (was: "a server error, try again later"). A reasoning model that returns no text: "returned no text". | `test_ai_providers` (name filter) |
| 3 | No API key in logs or project backups | passed | **passed** | `Gate03KeyNeverWrittenTests`: one flow with the key `sk-test-SENTINEL-0000` (see below). | `test_ai_providers` (key in a header, never echoed; no plain-text store) |
| 4 | Project-specific consent | passed | **passed** | `Gate04ProjectConsentTests`: two projects created through the hub in one session. What the first project allows is not offered, not sent and not switched on in the second. Each Send is one request, recorded in its own project's activity log only. Back in the first project its permissions are its own, and nothing is ticked until the researcher ticks it again. | `test_project_profile` (switches, "another project starts with nothing allowed", permissions in backups), `test_workspace_assistant.RefusalTests` |
| 5 | Payload preview before transmission; nothing sent before confirmation | **failed** | **passed** | `Gate05PayloadPreviewTests`: for OpenAI, Anthropic and Gemini, the whole wire request matches the preview: host, path, model, reply limit, and every string in the JSON body. It is the on-screen text character for character, plus the model and the role. No header carries project text. Choosing a task, depth, source or question sends nothing. **Send goes only to the provider and model the preview names**: before the fix, a change in Settings made in another window sent the request elsewhere. | `test_workspace_assistant` (OpenAI body equals preview; typed question previewed first), `test_ai_assistant.NoNetworkTests` |
| 6 | Refusal when permission is missing | passed | **passed** | `Gate06RefusalTests`: the key removed between preview and Send (another window): no request. A key the store cannot read: "nothing was sent". The anonymity statement withdrawn between preview and Send: no request; the new preview shows 0 data rows, and the request then sent holds no row. | `test_ai_assistant.SendTests.test_refusals_send_nothing`, `test_workspace_assistant.RefusalTests` (not set up, no model, not allowed, withdrawn before and during sending, rows) |
| 7 | Timeouts and rate limits (429, Retry-After): clear message, no crash | **failed** | **passed** | `Gate07TimeoutsAndRateLimitsTests`: Retry-After is honoured, read as seconds, as a date (falls back to back-off) and capped at 30 s. After the retries, the rate-limit message appears, the request is audited, the result stays on screen and Send works again. **A generation that times out** now says "did not answer in time" and is not sent again; before the fix it said "could not be reached" after four POSTs. Test connection timeouts, 429s and **cut-off or non-HTTP replies** are explained; before the fix the latter crashed the Settings handler. On the panel, cut-off replies now say "could not be read" and are audited; before the fix they said "The request failed" and were not audited. No connection at all: "could not be reached". Every request carries the 30 s limit. | `test_ai_providers`, `test_ai_assistant.SendTests`, `test_workspace_assistant.ErrorTests` (401, 429, 503, offline) |
| 8 | Cancellation | passed | **passed** | `Gate08CancellationTests`: Cancel during a 20-second Retry-After wait ends it at once, with no further attempt; the request is audited as cancelled. The late reply of a cancelled request never replaces the draft of the request sent after it, and it stays on record with its tokens. | `test_ai_assistant` (cancel before and during a request), `test_workspace_assistant.ErrorTests.test_a_request_can_be_cancelled_while_waiting` |
| 9 | Changing projects leaks no previous context | passed (no leak); the late-reply test failed on defect D | **passed** | `Gate09ProjectSwitchTests`: the first project has a marker in its overview, research question, plan, questionnaire, data columns and rows, dataset name, results, typed question and reply. The first request is checked to carry all of them except the reply, which comes after it. The second project's request (all sources allowed and ticked) is searched for the marker over the whole wire text: none. The previous draft and note are gone. A reply that arrives after the switch is dropped, and the next request holds nothing of it. **Defect D** (fixed): that late request was recorded nowhere; it is now in the local log, with the project's id. | — (the existing switch test covers the session, not the request) |
| 10 | AI text cannot overwrite verified values; suggestions stay distinguishable | passed | **passed** | `Gate10DraftsNeverChangeResultsTests`: a reply that demands new statistics changes nothing — the run in memory, the saved project run (report, SHA-256, tables), the result on screen. Its invented numbers are flagged and highlighted. "Use as my note" labels it as an unverified AI draft. In the Word draft, Table 1 holds the engine's estimates, and the AI text appears only under "Researcher interpretation", below its label. In the research report it appears only as "Researcher's note (not verified by the analysis engine)". | `test_workspace_assistant` (draft label, note label, run unchanged in memory), `test_ai_assistant.NumberCheckTests` |

### Gate 3 in detail

`Gate03KeyNeverWrittenTests` runs one AI flow with the key `sk-test-SENTINEL-0000` and produces every kind of file the application writes:
- the Settings files: `ai/settings.json`, the model cache `ai/models.json` and the daily budget `ai/usage.json`;
- a project's database with its activity log of AI requests;
- a `.sra` backup made from the hub, and that backup restored as a second project;
- a migration copy in `projects/.backups/` (an older-format project opened);
- the local AI log `ai/requests.jsonl`, from a request without a project;
- `startup.log`, with crash records of the adapters' exceptions;
- `console.log`, the console the packaged build keeps;
- a DEBUG log of every Python logger;
- the Word draft with the AI note.

The flow includes:
- a 401 whose error body repeats the key, the worst case;
- 429, 500, 400 and 404 replies;
- timeouts, cut-off replies, non-HTTP replies and refused connections;
- a cancelled request;
- a request refused for a missing permission.

Every produced file, and every member of every ZIP (`.sra`, `.docx`), is searched for the key in UTF-8, in UTF-16, in base64 and URL-encoded, and for the word `SENTINEL`. The text of every exception is searched too: `str`, `repr`, `args` and the full traceback. So is every text, label, tooltip and value on the Settings, Results, Home, Reports and Help screens. Nothing was found, on the RC and on this branch.

To show that the search can find a leak, the test checks that the key was really in use: in the credential store, and in the authentication header of the requests.

### Supporting requirements

| Requirement | Status | Proven by |
|---|---|---|
| The scientific application stays fully functional without AI | **passed** | `ApplicationWithoutAiTests`: no credential store, no provider, no connection. Analysis, the result screen, the Word draft and the research report all work; zero connections are opened. Existing: `test_workspace_assistant.RefusalTests.test_without_a_provider_the_panel_explains_and_nothing_is_sent`. |
| Public CI uses mocked provider APIs only | **passed** | `PublicCiTests.test_no_workflow_turns_on_a_live_provider_test`: no workflow mentions `SRA_AI_LIVE*`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_API_KEY`. |
| No paid live run unless explicitly enabled with an authorised key | **passed** | `PublicCiTests.test_the_live_smoke_test_is_skipped_unless_its_owner_enables_it`: every test in `test_stage368_ai_live.py` is skipped. |
| No key embedded in the program | **passed** | `PublicCiTests.test_no_api_key_is_written_into_the_program`: no key-like string in any file the build packages, nor in any workflow. |
| Tests never touch the network | **passed** | `NetworkGuard` runs in every gate test, and `NetworkGuardTests` proves it catches a real request. |
| Default-off state | **passed** | `DefaultOffTests` (section 3). |

## 2. How the providers are faked

`FakeProviders` replaces only `http.client.HTTPSConnection`. Its socket is a buffer in memory.

- **The production code path runs.** `ai_providers` builds its real `urllib` opener, with its real `ssl.create_default_context()`, its real headers and its real host check. No `base=` hook is used, and no local server.
- **Real HTTP/1.1 bytes both ways.** Requests leave as real HTTP/1.1 bytes, which the fake parses. Replies come back as real HTTP/1.1 bytes, which `http.client` parses.
- **The real reply shapes.** The fake answers like the real APIs:
  - OpenAI Responses: a reasoning item, then the message, and no top-level `output_text`;
  - Anthropic Messages: `content` blocks, and the `anthropic-version` header is required;
  - Gemini `generateContent`: candidates and `usageMetadata`, and the model in the path.
- **The model lists.** Lists come back in each provider's own format.
- **The key.** A 401 whose body repeats the presented key, as the worst case.
- **Scripted faults.**
  - HTTP status codes, with headers such as Retry-After;
  - a read timeout;
  - a chunked body cut off mid-reply, and a reply that is not HTTP;
  - a refused connection;
  - a reply held until the test releases it;
  - a reply with no text.

`NetworkGuard` refuses, and records, every `socket.connect`, `connect_ex`, `create_connection`, `getaddrinfo` and TLS handshake. The record fails the test even when the code under test turns the error into a message. Asyncio's self-pipe on Windows is allowed. The data are synthetic: 40 invented rows per project, and fake keys only.

## 3. Is the assistant enabled by default in the packaged build?

**No.** Four layers keep it off, and the fourth applies to every request.

**1. The packaged program starts in the classic interface.**
- `research_app.py:3055-3057` shows the classic interface (`interface_layout.build_interface`).
- The research workspace, where the AI panel and the AI settings are, opens only from the classic Home card "Try the new research workspace (Stage 33 preview)" → **Open the preview** (`interface_layout.py:131-161`), or with `SRA_UI=workspace` (`research_app.py:3059-3061`; used by the Windows CI journeys).
- The classic interface's own AI menu says that no AI is connected (`desktop_shell_text.py:29-32`).

**2. In the workspace, the assistant is off until the researcher sets it up.**
- **The defaults.** `ai_providers.load_settings` defaults to provider `openai` and model `""` (`ai_providers.py:234-241`). The program contains no key (`secret_store.py:1-10`; `PublicCiTests`).
- **Readiness.** `ai_context.readiness` answers `no_key`, `no_model` or `no_store` until a key is in the OS credential store and a model is chosen (`ai_context.py:94-109`). With any of these, `ai_context.refusals` refuses every request (`ai_context.py:157-159`).
- **The panel.** The "AI assistant (optional)" section on each result is collapsed (`workspace_assistant.py:165-169`). Its subtitle reads "Not connected. Everything else works without it." When not ready, it shows only the "No AI provider is connected" notice and **Open Settings** (`workspace_assistant.py:152-160` and `171-178`). There is no Send button, and Send re-checks readiness (`workspace_assistant.py:403-407`). The section itself is always placed on the result (`workspace_analyze.py:1000`).
- **Settings → AI providers** says "AI is off until you connect a provider with your own API key" (`workspace_ai.py:23`). Help says "Optional and off by default" (`workspace_text.py:1953-1954`).
- **The key store.** On Windows, the key store is the Credential Manager through `ctypes` (`secret_store.py:124-133`). A computer without a protected store keeps no key at all.

**3. The project context sources are off per project.**
- Every source starts off: the permissions table starts empty (`project_store.py:243-247`), and `ai_context.permissions` defaults to off (`ai_context.py:119-122`).
- Data rows also need the project's statement that they identify nobody.

**4. Every request needs its own confirmation.** The researcher presses **Send to \<provider\> (\<model\>)** below the exact preview.

**What a researcher must do to use it**
1. On the classic Home, open the research workspace preview.
2. Open Settings → **AI providers** and choose OpenAI, Anthropic or Google Gemini.
3. Paste their own API key and press **Save key**. The key goes to Windows Credential Manager.
4. Press **Test connection**. This sends only the key, and the provider lists the models it allows.
5. Choose a model, or type a model ID and press **Use this model**. A daily token limit is optional.
6. On a result, open **AI assistant (optional)**, choose the task, check the preview and press **Send**.

With these steps, only the result's own text is sent. To add project context, open Settings → **AI assistance** and allow each source for that project. Data rows also need the anonymity statement.

The tests that show this: `DefaultOffTests.test_a_fresh_installation_has_the_assistant_off`, which also checks that nothing is written to `<data root>/ai` until the researcher acts, and `test_the_packaged_build_carries_the_assistant_without_a_key_or_a_switch`.

**Decision for the Preview RC: leave it disabled by default, as it is.**
- The AI code ships in the build, but it is inert until steps 1–5.
- It is verified only against mocked provider APIs, and has no packaged-EXE journey. It must therefore not be pre-configured, enabled for demonstration, or described as verified against real providers.
- A researcher who connected a provider in an earlier build has it ready after the update. Their key in Credential Manager and `<data root>/ai/settings.json` persist. That was their own earlier choice.

## 4. Defects found and fixed

Each test below **failed on `216353d`**, run with the same test file in a clean export of that commit, and **passes on this branch**.

| | Defect | Fix (AI modules only) | Test that failed, then passed |
|---|---|---|---|
| A (gate 2) | HTTP 400 or 422 — a listed model that cannot take a plain text request, such as a deep-research model that needs tools, or a completion-only model — was reported as "{provider} did not answer properly (a server error). Try again later." | `ai_providers._request`: 400/422 → reason `unsupported`, not retried. `workspace_assistant`: new message, with **Open Settings**. `workspace_text`: `assistant.error.unsupported` in EN/LV/RU. | `Gate02UnsupportedModelTests.test_a_listed_model_that_refuses_a_text_request` |
| B1 (gate 7) | A generation with no reply in time was retried three times, and each POST may be processed and billed. That took about 2 minutes at 30 s each, and ended with "could not be reached: this computer may be offline…". | `_request`: a read timeout raises `timeout`, and a POST is not sent again; a GET is still retried. New panel message (EN/LV/RU) and Settings text `error.timeout` (EN/LV/RU). One existing assertion updated: `test_ai_providers.ProviderTests.test_timeouts_and_cancellation` now expects `timeout` and one POST, not `offline`. | `Gate07…test_a_generation_that_times_out_is_explained_and_not_sent_again`; `Gate07…test_test_connection_failures_are_explained_and_never_crash` (timeout) |
| B2 (gate 7) | A reply cut off mid-body (chunked) or not HTTP at all raised `http.client.IncompleteRead` or `BadStatusLine`, which escaped the adapter. Test connection then failed with an unhandled exception, and its message stayed at "Contacting…". On the panel it showed "The request failed", and the request was missing from the activity log. | `_request`: `http.client.HTTPException` → `malformed`, the existing "could not be read" message. | `Gate07…test_replies_cut_off_or_not_http_and_no_connection_never_crash` (truncated, garbage); `Gate07…test_test_connection_failures_are_explained_and_never_crash` (truncated, garbage) |
| C (gate 5) | Send compared only the prompt text with the preview. After the provider or model was changed in Settings in another window, the button still read "Send to OpenAI (…)", and the request went to Anthropic. | `workspace_assistant`: the panel keeps the provider and model of each preview. A difference is treated like a changed text: nothing is sent, and the new preview is shown first. | `Gate05PayloadPreviewTests.test_send_goes_only_to_the_provider_and_model_on_screen` |
| D (found under gate 9) | A request still out when the researcher opened another project was recorded nowhere. `Project.log_ai_request` refuses once the project is closed, `audit` returned `False`, and the late draft was dropped without a warning. | `ai_assist.audit`: when the project's log cannot take the record, it goes to `<data root>/ai/requests.jsonl` with the project's id. It still returns `False`, so the panel's "could not be recorded in the activity log" warning stays accurate. | `Gate09ProjectSwitchTests.test_a_reply_that_arrives_after_the_switch_is_dropped_and_kept_on_record` |

Changed:
- `ai_providers.py`, `ai_assist.py`, `workspace_assistant.py` and `workspace_ai.py`;
- `workspace_text.py`: two new keys, in three languages;
- `tests/test_ai_providers.py`: one assertion.

`workspace_analyze.py`, `project_session.py`, `batch_*`, `analysis_runs.py` and `tools/windows_gui_e2e.py` were not touched.

## 5. Not tested, and remaining work

**Not tested here**
- **Real providers.** No real provider was called. The fake reproduces the documented request and reply shapes, but real APIs can differ: error bodies, which status a given provider uses for an unknown or unsuitable model, rate-limit headers, reply formats of new models. `tests/test_stage368_ai_live.py` lists the models and sends one tiny synthetic prompt per provider. It was **not run** for this gate, because no authorised key was available. Run it before a release that advertises the assistant:

  ```
  SRA_AI_LIVE_TEST=1 SRA_AI_LIVE_OPENAI_KEY=… SRA_AI_LIVE_ANTHROPIC_KEY=… SRA_AI_LIVE_GEMINI_KEY=… \
      python -m unittest discover -s tests -p "test_stage368_ai_live.py" -v
  ```

  `SRA_AI_LIVE_<PROVIDER>_MODEL` names the model to ask.
- **Real TLS, DNS and proxies.** The fake checks that the production context verifies certificates and host names, but no handshake takes place. System proxies are switched off in the tests.
- **Windows Credential Manager.** Only the existing Windows-only `test_ai_providers.SecretStoreTests.test_windows_credential_manager_round_trip` covers it. It runs in the `windows-research-journey` workflow and was skipped here, on Linux.
- **The packaged EXE.** There is no Windows EXE journey for the panel or the AI settings (`docs/STAGE36_AI_ASSISTANT.md` §9). The tests drive the Python controls through the harness, not the Flutter client.
- **Windows runs of the gate file.** `test_stage368_ai_gate.py` runs in the Ubuntu jobs of `python-tests.yml`, which discover all tests. The Windows jobs run only named patterns, so they do not run it. Its network guard allows asyncio's Windows self-pipe, but it was never run on Windows.
- **Flet's own debug logging.** With `FLET_LOG_LEVEL=debug` (developer mode, `flet run -v`), Flet logs control patches and events, which could include what is typed into the key field. Nothing in the repository sets that variable, and the packaged build does not.

**Remaining work, not done here**
- The 30 s time limit per attempt may be too short for slow reasoning models writing up to 1,200 tokens. A timeout is now explained and not re-sent, but such a model cannot be used. Consider a longer limit for generations, or streaming.
- Test connection cannot be cancelled. A provider that hangs shows "Contacting…" for up to 4 × 30 s.
- Retry-After is capped at 30 s. After three tries the message says "wait a minute", even when the provider asked for longer. OpenAI's 429 `insufficient_quota` (no credit) gets the rate-limit message.
- The model filter is a name heuristic (`ai_providers.NOT_TEXT`). Listed models that cannot answer a text request are still offered; since fix A, they fail with "choose another model".
- The number check is lexical. "Every number appears in what was sent" also counts numbers from the researcher's question and from context sources, not only the engine's output.
- **Copy** copies the draft without its "[AI draft — …]" label.
- **Owner decisions** (unchanged Stage 36 design):
  - the result's own text can be sent from any project, with consent per request, even when the project allows no context source;
  - AI permissions and the anonymity statement travel with `.sra` backups, so a project restored from someone else arrives with their decisions. Send still needs the current researcher.
- A key pasted by mistake into "Or type a model ID" would be saved as the model. It would then sit in plain text in `ai/settings.json` and in the activity log. Not guarded.
- The classic interface's "AI assistant status" text (`desktop_shell_text.py:30`) still says the assistant is "planned, not connected". It should mention the optional assistant in the workspace preview.
- Cancel cannot stop an HTTP request already in flight. The reply is discarded, but the provider may still bill it; the audit records it.

## 6. Test runs

All runs used the locked environment (`MPLBACKEND=Agg`; Python 3.12.3).

| Run | Result |
|---|---|
| `test_stage368_ai_gate.py` on `216353d` (clean export plus the final test files) | `Ran 30 tests in 27.918s` — `FAILED (failures=9)`: the six tests in section 4 (nine subtests) |
| `test_stage368_ai_gate.py` on this branch | `Ran 30 tests in 26.904s` — `OK` |
| `test_stage368_ai_live.py` (no live variables set) | `Ran 3 tests in 0.000s` — `OK (skipped=3)` |
| Existing AI tests on this branch: `test_ai_providers` (18, 1 skipped: Windows only), `test_ai_assistant` (21), `test_workspace_ai` (2), `test_workspace_assistant` (13), `test_project_profile` (15), `test_workspace_foundations` (18) | all `OK` |
| Full suite on this branch (`python -m unittest discover -s tests`) | `Ran 1185 tests in 794.459s` — `OK (skipped=10)` |

Run them with:

```
MPLBACKEND=Agg python -m unittest discover -s tests -p "test_stage368_ai_gate.py"
MPLBACKEND=Agg python -m unittest discover -s tests
```
