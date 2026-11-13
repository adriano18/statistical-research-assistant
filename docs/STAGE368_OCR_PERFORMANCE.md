# Stage 36.8 — OCR performance and quality

Issue #62 asked why a two-page scanned questionnaire takes about 40 s in the program (39.5 s portable, 52.8 s installed, Stage 36) when the OCR engine itself needs about 12 s. It also asked for each stage to be profiled before anything is optimized. Accuracy and questionnaire integrity must not be traded for speed.

The fixture throughout is the synthetic 52-item Latvian table scan, image only, two pages (`tests/fixtures/stage36`). No private material was used.

## 1. How it is measured

`ocr_profile.py` records one `Profile` per document reading, always (it costs a few clock reads):
- the twelve stages of the issue: wall seconds, CPU seconds of the reading thread, number of calls;
- per Tesseract process: wall seconds, plus CPU seconds and peak memory from its process handle on Windows;
- for the program: peak memory, I/O bytes, threads, and the longest stall of the interface's event loop while the reading ran.

With `SRA_OCR_PROFILE=<folder>` each profile is also written as JSON. The GUI journeys set it, so the Windows numbers come from the packaged program itself.

The GUI journey's `ocr_in_program_seconds` is something else: the time until UI Automation **shows** the result. It also counts the driver's own polling, which enumerates the whole UI Automation tree on every poll, and its scrolling while it waits. It is kept for comparison with Stage 36. It is not the program's time.

| # | Stage (issue #62) | What it covers in the code |
|---|---|---|
| 1 | Opening the source | `source_sha256`, the saved-review lookup (`workspace_questionnaires.open_bytes`) |
| 2 | PDF loading | page count, text layer attempt, image coverage, `PdfReader` (`import_session`, `visual_survey_review`) |
| 3 | Page rendering | PDFium render + PNG encoding, for the engine (2 pages) and for the page shown first |
| 4 | Image preprocessing | table rules whitened (`ocr_rules.without_ruling_lines`) |
| 5 | OCR initialization | engine resolved, image written, process created (`ocr_runtime.run_tesseract` until `Popen` returns) |
| 6 | OCR execution | the Tesseract process from start to exit (language model loading included) |
| 7 | TSV parsing | `parse_tesseract_tsv` |
| 8 | Table reconstruction | answer grids, table rows, matrices, text repair |
| 9 | Question reconstruction | `parse_scientific_lines` |
| 10 | Confidence assessment | `ocr_confidence_warning` |
| 11 | Scientific review-model creation | evidence links, scales, the import session's facts, the review adopted by the page, autosave |
| 12 | Flet UI rendering and update | `app.render()` on the event loop (Python side; the Flutter client's frame time is not visible to Python) |

## 2. What the profile found (before)

Local, Linux, the same code as the program:
- `cProfile` of `ImportSession.open` (6.1 s, cold and warm alike): the Tesseract processes took 3.9 s, **PNG encoding 1.8 s**, rule removal 0.4 s, everything else < 0.1 s.
- The PNG cost was `Image.save(..., optimize=True)` in `_render_pdf_page`: 0.84 s for one 1191×1684 page. `compress_level=3` takes 0.11 s and writes a **smaller** file (0.91 MB against 1.08 MB) with identical pixels. The cleaned page was encoded a second time (default level, 0.08 s).
- The page shown first after the reading was rendered (PDF → PNG with `optimize=True`, 0.45 s) inside `app.render()`, on the event loop. The window could not react meanwhile.

Windows, packaged program, run 43418623163 (dff65c8, before the change):

| | Seconds |
|---|---|
| Engine alone, page 1 / page 2 (`direct_ocr`, outside the program) | 8.0 / 6.4 |
| Until UI Automation showed "52 candidate items" (`ocr_in_program_seconds`) | 46.4 |
| Stage 36 measurement, same journey (run 42686880526) | 39.5 |

That run had no in-program profile yet.

## 3. Changes, each justified by the profile

| Change | Why it is safe | Effect (local) |
|---|---|---|
| `encode_png`: zlib level 3 instead of `optimize=True` (engine pages, viewer pages, Word segments, the cleaned page) | PNG is lossless: the decoded pixels are identical (test), and with a real engine the words and their boxes are identical (test `test_the_engine_reads_the_same_words`). `optimize=True` is still tried if a page would exceed the 12 MB limit | page rendering 1.7 s → 0.3 s for two pages |
| The page shown first is drawn in the worker thread, before the review is shown | the same function and parameters, only another thread | the render that shows the result held the event loop ≈ 0.5 s; now all four renders of a reading take 0.03 s |

Not changed, and why:
- **Bounded parallel OCR** of the two pages was considered and not done. Each Tesseract process already runs OpenMP threads; two processes would compete for the same cores on a student's laptop. Whether recognition stays identical under parallel processes has not been tested on the bundled engine. Accuracy comes first.
- **Reusing earlier OCR on unchanged pages.** A review of the same bytes (same SHA-256) is already restored from the saved review without new OCR (`ReviewStore`). Only "read again" and a changed OCR language re-run it, as they must.

After, locally (Linux, in the program through the harness, `tests/test_stage368_ocr_profile.py`):

| Stage | s | calls |
|---|---:|---:|
| source_open | 0.00 | 1 |
| pdf_loading | 0.01 | 5 |
| page_rendering | 0.41 | 3 |
| image_preprocessing | 0.33 | 2 |
| ocr_initialization | 0.00 | 2 |
| ocr_execution | 3.47 | 2 |
| tsv_parsing | 0.01 | 2 |
| table_reconstruction | 0.02 | 3 |
| question_reconstruction | 0.02 | 1 |
| confidence_assessment | 0.00 | 1 |
| review_model | 0.00 | 4 |
| ui_update | 0.03 | 4 |
| **total** | **4.30** (was ≈ 6.6) | |
| event-loop stall | 0.00 | |

### 3.1 Windows after the PNG change: what remained

Packaged program, GUI journey `import-scan-lv`, run 43421786722 (216353d). The profile is the program's own; the journey reads the same document twice in one program.

| | First reading | Read again (warm) |
|---|---:|---:|
| Total in the program (profile) | 50.4 s | 38.3 s |
| OCR execution (2 Tesseract processes) | 26.8 + 22.3 s | 18.5 + 18.5 s |
| Processor time of each Tesseract process | 4.5 + 4.3 s | 4.3 + 4.4 s |
| All other stages together | 1.3 s | 1.3 s |
| Longest stall of the interface's event loop | 0.03 s | 0.03 s |
| Processor time of the **program's own process** | 173 s (3.4 of 4 cores) | 130 s (3.4 of 4 cores) |
| Engine alone outside the program, same pages (`direct_ocr`) | 7.8 + 6.4 s | |

So the PNG and first-page changes did what they should: everything apart from OCR now takes 1.3 s, and the window never froze.

But each Tesseract process ran 18–27 s while it needed only about 4.5 s of processor time. **The engine was waiting for the processor, not working.** In the same seconds the program's own process used about 3.4 of the runner's 4 cores, while its Python side was only waiting for Tesseract's output.

The UI Automation driver is not the cause: during the second reading it only watched for the profile file, and the ratio was the same.

What the program did meanwhile: the status line showed an indeterminate `ProgressRing`. Flutter redraws such a ring on every frame, and the runner draws without a graphics card. Every other profile of that run, even a 0.2 s text reading, shows the same ~3.4 cores while busy.

### 3.2 The change for it (f528a1c), and how it is verified

- While reading, the ring is **determinate**: it shows the OCR pages already read (0 of 2, then 1 of 2) and changes only when a page is done. The text beside it still names the page being read. A text reading shows an hourglass icon. Nothing animates on its own (`tests/test_stage368_ocr_profile.py::ReadingIndicatorTests`).
- The scan journey now measures the program's processor use while it only shows the page (`program_cpu_cores_idle`). Each reading's profile gives `program_cpu_cores`.

The cause counts as confirmed only if, on the next Windows run:
- the reading's `program_cpu_cores` falls to the idle level;
- the engine's time approaches its processor time.

**Result: confirmed.** Packaged program, GUI journey `import-scan-lv`, run 43429053006 (467945c), the same runner type, document and pages:

| | Before (run 43421786722) | After (run 43429053006) |
|---|---:|---:|
| Program's processor use while it only shows the page (`program_cpu_cores_idle`) | not measured | 0.00 cores |
| Program's processor use while reading, first reading / read again | 3.4 / 3.4 cores | **0.78 / 0.56 cores** |
| Each Tesseract process, wall / processor seconds, first reading | 26.8 / 4.5 and 22.3 / 4.3 | **2.5 / 2.4 and 2.9 / 2.4** |
| Total in the program, first reading / read again (profile) | 50.4 / 38.3 s | **6.1 / 5.7 s** |
| Until UI Automation showed "52 candidate items" (`ocr_in_program_seconds`) | 50.0 s | **5.5 s** |
| Engine alone outside the program, same pages (`direct_ocr`) | 7.8 + 6.4 s | 6.6 + 5.3 s |
| Longest stall of the event loop | 0.03 s | 0.01 s |
| Candidates found | 52 | 52 |

On the final RC code commit b2abe20 (run 43440145161), the same journey gave:
- 6.2 s for the first reading and 5.9 s read again;
- 0.83 and 0.54 cores while reading, 0.00 idle;
- 6.1 s until UI Automation showed the 52 candidates.

The engine's time now equals its processor time: it no longer waits. Inside the program it is even faster than the engine alone on the raw page, because the program gives it the page with the table rules whitened (§1, stage 4).

The Stage 36 question (about 40 s in the program against about 12 s for the engine) is answered. Over 30 s of it was the engine waiting for the processor while the program redrew an animation. The rest was PNG encoding and a render on the event loop (§2).

**Not changed, not measured.** Three other indeterminate rings remain:
- while an analysis runs (`workspace_analyze.py`);
- while an AI request is out (`workspace_assistant.py`);
- on the start screen (`app.py`).

Analyses take seconds, and the analysis runs in the same process, which still has a core of its own on a 4-core runner. Whether they slow down the same way has not been measured, so they were left as they are. They are candidates for the same change once a profile shows a cost.

**Where this applies.** On computers that draw without a graphics card (virtual machines, remote desktop sessions, some older laptops) the gain is about as large as here. A computer with a working graphics driver draws the ring cheaply, so the gain there is the smaller one of §3: about 2 s from PNG encoding and the event loop.


## 4. Progress and responsiveness

- The reading runs in a worker thread. The status line says which page is being read and how far it is ("Reading page 1 with local OCR (1 of 2)…", LV/RU alike), and offers **Cancel**. Cancel stops the Tesseract process and applies nothing.
- When the reading ends, the status names the candidates found and how many need attention ("52 candidate items · 17 need attention · 0 compared with the source", Windows run 43418623163).
- An interrupted review is saved automatically and comes back when the same document is opened again (same SHA-256). The new `import-resume` journey checks this on Windows (`docs/STAGE368_REAL_USER_ACCEPTANCE.md`).
- The event-loop stall during a reading is measured in every profile. It must stay well under a second; `tests/test_stage368_ocr_profile.py` requires < 3 s.

## 5. Recognition quality: four things, kept apart

| Measure | Latvian table, DejaVu | Latvian table, STIX (Times-like) | Source |
|---|---|---|---|
| Items detected, numbered 1–52 | 52 | 52 | real-OCR tests, Linux; GUI journey, Windows |
| Wording identical to the generator's text (Linux engine) | **52 of 52** (51 before 5cefded) | **50 of 52** (46 before) | §6; `test_every_statement_ends_as_printed_no_answer_area_marks` |
| Needing attention (flagged for review) | 17 on Windows (run 43418623163) | — | status line |
| Response options / scale | one documented legend scale (5 labels), **not confirmed** | same | tests |
| Scientific confirmation | none automatic: versions, scoring keys, reverse items and response coding are confirmed only by the researcher | | `scientific_survey_import`, tests |

"52 of 52 detected" does not mean 52 exact statements. Every OCR item stays "review" until the researcher compares it with the source page.

## 6. Characters from the answer columns in the wording

The word boxes (Linux engine, STIX table) show the cause:

| Item | OCR line | Answer-area tokens (x ≥ 0.796) |
|---|---|---|
| 9 | `… vēl gaida 1 2.3 du 5` | `1`, `2.3`, `du` (score 40), `5` |
| 10 | `… lēmumu. Ll 2% 3. 4.15` | `Ll` (42), `2%`, `3.`, `4.15` |
| 38 | `… pārbaudījumu. 1 Z Ss` | `1`, `Z`, `Ss` (no score) |
| 39 | `… plānu. Lzs45` | `Lzs45` (32) |

These are misread answer codes. They stand in the answer columns, right of every statement (statements end by x ≈ 0.77). The Stage 36 rule removed only answer-like tokens and never a token with two letters, so the rest stayed in the wording.

Stage 36.8 rule (`ocr_table_rows._split_answers`):
- When a row's trailing run right of the answer floor holds a digit, so it is the answer codes, it also takes the **answer-area marks** inside it: tokens with a digit, or scored below 60.
- A confidently read word is never removed. A run without any digit keeps its letters as read.
- Each mark taken out is **named in the item's flags and notes** ("answer-area marks left out of the wording: Ll 2%"), so the reviewer sees what was removed.

Result: DejaVu 51 → 52 exact statements, STIX 46 → 50. Two artifacts remain, both outside the answer area, and both stay as read with their low score:
- "Nr. 1" read as "Nr. |";
- a speck glued to a first word ("lIzdomātā", score 31).

The Windows engine reads differently in places. "Need attention" counts the items that carry any flag and are not yet marked as compared: on Windows 17 before this change, from the existing rules (wrapped prompts joined, numbers to check). The new flag adds items whose answer-area marks were left out. That is intended: such an item must be compared with the source page.

## 7. Limits of these measurements

- GitHub's Windows runners are shared virtual machines. The same engine took 6.5 + 5.3 s in Stage 36 and 8.0 + 6.4 s in run 43418623163. Absolute seconds vary by ±30 % between runs, so comparisons are made within one run where possible.
- The Flutter client's own frame time and the cost of sending images to it are not visible to Python. The difference between the journey time and the in-program total contains it, together with the driver's UI Automation polling.
- The installed program was slower than the portable one in Stage 36 (52.8 s against 39.5 s). In-program profiles of the installed program come from the installer workflow's journeys. A first start after installation is also scanned by Windows Defender; that cost is outside the program.
