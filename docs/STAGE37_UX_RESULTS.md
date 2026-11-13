# Stage 37.0 — measured interaction cost (AC-10)

Measured with `docs/stage37/measure_baseline.py` (run from the repository root with the locked environment: `python docs/stage37/measure_baseline.py`). The script drives the real workspace controls through the Stage 36 `CountingWorkspace`:

- a click or a tick counts 1, a dropdown 2 (open, choose);
- typed fields are counted once each, apart;
- page changes count every change of route, also one a handler makes;
- system dialogs (the Windows Open and Save dialogs) are counted apart.

Synthetic data only (`tests/fixtures/stage36`). The harness runs on Linux and calls the handlers a click calls; Windows was not used. `tests/test_stage37_ux.py` asserts the numbers below, so a change of the flows shows as a test failure.

## Before and after

| Flow | Before (`2f9af71`, = 55f94b1 / 07c37f6) | After (Stage 37.0b) | AC-10 threshold | Met |
|---|---|---|---|---|
| Beginner: interactions | 22 | **21** | ≤ 20 | **no, one over** |
| Beginner: typed fields | 10 | **5** | ≤ 5 | yes |
| Beginner: page changes | 5 | **4** | ≤ 4 | yes |
| Beginner: system dialogs | 2 | 2 | — | — |
| Beginner: analysis linked to H1 | not possible | **automatic** (at *Create the analysis for H1*) | — | — |
| Professor: interactions | 14 | **5** | ≤ 6 | yes |
| Professor: page changes | 6 | **2** | ≤ 2 | yes |
| Stage 36 baselines (8, 2, 8, 8, 2, 1, 3) | unchanged | unchanged | unchanged | yes (`test_stage36_ux_baseline`) |
| Today's flows re-measured at this branch | 22 · 10 · 5 and 14 · 0 · 6 | unchanged | — | `test_stage37_ux.test_the_stage_36_and_today_baselines_are_unchanged` |

**Why 21, not 20.** The prototype's path (design Appendix B) counts the kind of Q1 as one click. The plan card keeps the 37.0a dropdown `plan-q{i}-type` (2 interactions) so that every existing data key and control type stays. Everything else of the prototype's path is met step for step. Ways to the 20th interaction, left to the owner: the kind as chips (one click; it changes the control type of `plan-q{i}-type`), or a kind preset from the guided goal already chosen.

## Beginner flow, Stage 37.0b

| # | Segment | Inter. | Typed | Pages |
|---|---|---:|---:|---:|
| 1 | Project: title, *Create project* | 1 | 1 | 1 |
| 2 | Q1, shown by itself: its text, its kind (dropdown) | 2 | 1 | 0 |
| 3 | H1: *Add a hypothesis to Q1* (bar), its text, *Save plan version* | 2 | 1 | 0 |
| 4 | Data: *Open CSV / Excel…* on the bar (+ the Open dialog) | 1 | 0 | 1 |
| 5 | Levels: tick, *Use suggestions…*; 0 corrections | 2 | 0 | 0 |
| 6 | *Create the analysis for H1* in the Data page's footer: Analyze, linked, at the variables | 1 | 0 | 1 |
| 7 | Analysis: UCLA (dropdown), all quantitative, untick Age, Spearman, Run | 6 | 0 | 0 |
| 8 | In the task: 3 review ticks, the note, *Add to report* | 4 | 1 | 0 |
| 9 | *Open the report* in the footer | 1 | 0 | 1 |
| 10 | Study title, *Export Word report…* (+ the Save dialog) | 1 | 1 | 0 |
| | **Total** | **21** | **5** | **4** (+2 dialogs) |

Routes: project → data → analyze → reports.

## Professor flow, Stage 37.0b (after a restart)

Set-up, not counted: a second analysis (Kruskal–Wallis by UCLA_Level) linked to H2, H2's priority changed after results with its reason, a deviation recorded for H1.

| # | Segment | Inter. | Pages |
|---|---|---:|---:|
| 1 | Open the project | 1 | 1 |
| 2 | H1 *Show details*: analyses and their steps, every check with its state, the recorded decisions with reasons, the priority history, the facts beside the standing | 1 | 0 |
| 3 | H2 *Show details*: its analysis, the priority changed after results with its reason | 1 | 0 |
| 4 | Reports | 1 | 1 |
| 5 | The preview and the structure (the Hypotheses section's item count) | 1 | 0 |
| | **Total** | **5** | **2** |

What the professor does not see in the program: the design's *Show the evidence* (a table excerpt inside the hypothesis detail) is not built; the evidence per hypothesis and result is in the Word report's Hypotheses section and its table *Hypotheses and evidence* (`docs/STAGE37_0B_STATUS.md` §1).

## Not measured

- No test with users (design §5.4); no timings; no Windows run of the counts.
- Scrolling is not counted (as in the design).
