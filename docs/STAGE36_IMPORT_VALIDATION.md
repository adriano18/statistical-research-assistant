# Stage 36.5 — scientific import validation (synthetic fixtures, counts only)

This note records how the importer fixes for the Stage 36.0 defects D6, D7
and D8 ([STAGE36_PLAN.md](STAGE36_PLAN.md)) were validated. Every number
below comes from the invented documents written by
`tests/fixtures/stage36/generate_fixtures.py`; no private questionnaire,
thesis or dataset was read, and no real questionnaire wording appears here
or in the tests. The tests are `tests/test_stage36_regressions.py`
(`ImportReproduction`, markers removed) and `tests/test_stage36_import.py`.

## Fixtures

| File | Structure | Expected |
|---|---|---|
| `synthetic_cope_two_forms_60.docx` | two Word tables (61 + 60 rows × 5 columns); item numbers inside the statement cells; each form's options in the instruction before its table ("Select one category: 1 Never / 2 Rarely / …"); scoring note "15 subscales, each with four items"; 15 "Dimension N: items …" lines; 2 numbered references | 2 forms × 60 items |
| `synthetic_cope_two_forms_60_unnumbered.docx` | the same shape with **no item numbers in the cells**; form 1 has a header row of answer labels, form 2 only an instruction ("1 = Not at all; 2 = Slightly; …"); scoring key "Dimension N (invented): statements a, b, c, d."; 2 references | 2 forms × 60 items |
| `synthetic_lv_table_scan_52.pdf` | two image-only pages, Latvian; number column, statement column (13 statements wrap), answer digits 1–5 on the right, an instruction line opening with a bare "5" right above the legend "1- …" to "5- …", which stands directly above item 1 and is repeated at the top of page 2, ±0.3° rotation, tick marks before items 17–21 and 24, ruled lines and speckle noise, 2 references | 52 items |
| `synthetic_sacs_scanned_52.pdf` | two image-only pages, English; number inline with the text ("12. Invented …"), answer digits on the right, 2 references | 52 items |

**Generator fix (36.5).** In the 36.0 generator the Latvian table scan drew
item 26 below the bottom edge of page 1 (row top at y = 1761 px on a
1754 px page) and the page footer over item 24, so the scan contained only
51 items and no reader could find 52. The statement column now ends at
x = 935 px (answer digits at x = 965 instead of 905), so exactly the 13 long
statements wrap, all 26 rows of each page end above the footer, and the
generator raises an error if a row or the references would not fit.

**Bare "5" above the legend (36.5, second round).** The instruction now
wraps so that its next line opens with the option count: a bare `5` drawn
between the number and the statement column, with the following word where
statements start — the worst case for a number-column reader. Checked with
the old code extracted from git on the regenerated scan (`lav`): the Stage
36.0 importer (b8e123c) still yields **16 of 52** (the sequence breaks at
`"17.`), so D8 stays reproduced; the first 36.5 version (cf736c7) yields 53
numbers (the bare `5` became a one-item instrument of its own), so the D8
test now also guards that defect.

## Method

**Word documents (D6) — structure first.** `table_forms.read_docx_blocks`
reads paragraphs (with heading levels from their styles) and tables (rows
× cells) in document order. A table is a questionnaire *form* when its
statement column holds statements and its other columns print the same
short codes or labels on at least 60 % of the statement rows. Each form:

* is one instrument, titled by the nearest heading before its table;
* without printed numbers, numbers its statement rows 1…N in table order
  (header row excluded) and says so in an instrument warning;
* documents its own answer options as a `DocumentedScale`: header-row
  labels (evidence `header`, codes as printed in the cells), else the
  instruction before the table (evidence `instruction`, codes as printed
  there), else labels printed in every row (evidence `row`); disagreements
  between header, instruction and cells are listed as scheme issues;
* becomes a `ResponseScheme` linking all its items, **not confirmed**.

Tables whose cells already carry numbers keep the established line parser;
their documented options are attached afterwards to items that found no
options (`attach_form_scales`), and an instrument titled only by the file
name takes its table's heading. Binary (True/False), marker (○) and
code-plus-label cells keep their existing readers. Scoring keys
("Dimension 3 (invented): statements 3, 18, 33, 48.") are parsed as
review-only `ScoringGroup` evidence; references stay non-items.

**Stated item count (D7).** `expected_item_count` ignores a count inside a
clause that distributes over parts of the form ("15 subscales, each with
four items", "each dimension sums four statements", "subscales of 4
items"); "each of the 20 items" still counts. With no statement about the
form length the result is `None`.

**Scanned tables (D8) — geometry first.** `ocr_table_rows` works from
Tesseract word boxes (normalised 0..1 page coordinates):

1. **visual lines:** a number, or a run of answer digits, that OCR put on a
   line of its own at the height of a statement line joins that line;
2. **columns:** lines starting with a clean number (`12.`) followed by a
   word give the number column; the left edges of those words give the
   statement column, fitted as x = a + b·y so rotation does not matter. A
   number followed by its text at an ordinary word gap is **not** a column
   — such pages (the inline scan) keep the line parser. Alignment is
   measured on the first word of a line; tiny low-scored specks before it
   (≤ 2 characters, no digit, score < 40) are ignored. A line is aligned
   within 0.6 line heights (as an x fraction, `unit_x`) of the column; a
   line with a plain number (quotes and ticks stripped) left of its first
   word and answer digits on the right may be up to 1.2 `unit_x` off,
   because OCR word boxes sometimes start early. Lines without such a
   number keep the strict test, so continuation and noise decisions are
   unchanged;
3. **answer tokens** come off the END of a line only: the trailing run of
   tokens right of the answer floor (a little left of the earliest answer
   runs of the page) made of digits and the glyphs OCR makes of them —
   `12375`, `333`, `1—2`, `[1`, `|`, `5”`, `—`, `-`, one letter glued to
   digits (`a2345`), a single digit look-alike letter (I l ī S Z B G T A O
   and `L`), any other lone letter scored below 60. A token with two or
   more letters is never removed;
4. **rows, two passes with look-ahead:** a line whose number-column text
   reads as the next number starts a row. A sequence (or a new table at
   `1`) starts only where a following numbered line reads the next number,
   and a number without the page's dot style (`5` among `12.`) never starts
   one — so an instruction line opening with `5`, and legend lines `1- …`
   printed in another column, never start or advance the sequence. In the
   number column only, quotes, ticks and dashes are stripped and look-alike
   glyphs (A → 4; I l | ī í ì i ! [ ] → 1; S → 5; Z → 2; B → 8; G → 6;
   T → 7; O o → 0) are mapped only when the result is the expected number;
   a normalised reading that the next numbered line contradicts (it prints
   the same number) is refused. A row whose number is unreadable or only
   part of the expected one (`_4.` for 49) gets the expected number when
   the next numbered line reads the number after it, or when its statement
   and answer digits are in place. Every normalised or inferred number is
   flagged `check this number: OCR read “…”` with a note. Rows without
   answer digits count when their number fits; a citation-shaped line is
   never a row;
5. **continuations:** a line with nothing in the number column that starts
   in the statement column directly under a row is appended to it
   (`prompt joined from N lines`);
6. **legend:** `1- …` to `5- …` (also repeated, or merged with rule noise,
   on the next page) becomes ONE `DocumentedScale` (evidence `legend`,
   codes as printed, labels as read, issue "read by OCR"), never items; a
   repeated legend that reads differently is reported;
7. lines inside the table without a confidently read word (ruled lines,
   specks) are dropped; references stay plain text and remain non-items;
8. each row keeps its page and box (number + statement words) as its
   source region in `review.spatial`.

A choice grid (codes with labels under them) keeps precedence, unless it
covers fewer than half of the rows the number column shows.

**Patterns reported from an authorized private check.** The owner's real
two-page scan gave 45 of 52 with the first 36.5 version (private check;
not accessible here). Its structural evidence — token shapes, positions
and confidences, no wording — is rebuilt with invented words in
`RealScanPatternTests` (synthetic `OCRPage` objects, no Tesseract):

| Pattern | Test |
|---|---|
| bare `5` opening an instruction line at x 0.18, legend `N-` at x 0.355, rows 1–4 at x 0.16 (scores 57–95) with continuations | `test_1_*` (items 1–4 found; the instruction stays text) |
| `"17.` scored 52 with answers `2 3 4 5`; the number split onto its own line; a speck before the number or the first word; rule noise in the line; low-scored first words | `test_2_*` |
| `Aī.` for 41 (score 16), answers `a2 3 7 5`; look-alike map A, ī/i/l/I/\|/!, S, Z, B, G, T only towards the expected number | `test_3_*` |
| `_4.` for 49 between 48 and 50, answers `a 3 45`; not inferred when no next row confirms | `test_4_*` |
| every listed answer token form, answer columns starting at x 0.72–0.82, statements ending by x 0.78; two-letter tokens kept | `test_5_*` |
| page 2 legend merged with rule noise (a letter scored 36 / `ZT` scored 22 at x 0.15) | `test_6_*` (no item; 27 follows printed) |
| rows without answer digits (`aaa` at 0.74, `a` at 0.92) | `test_7_*` |

Every one of these tests also rejects an item number used twice. The first
36.5 version (cf736c7) fails all 15 of them: it turns the bare `5` line
into a second item 5, and — checked before the duplicate test was added —
it also misses the split or speck-preceded number, the look-alike readings
and the answer-token stripping (`test_2` split/speck, `test_3`, `test_5`).

**Round 3.** The private check after round 2 (see below) traced the one
lost row from the structure alone. The page fitted x = 0.2070 − 0.0043·y
with `unit_x` = 0.0319. Item 17's first word box starts 0.0201
(0.63 `unit_x`) left of the column; its number `"17.` is at x 0.149 and
its answer digits at 0.713–0.956. `LooseFirstWordTests` rebuilds that
geometry with invented words. It fails on 132082c (17 lost, 18 taken as a
jump) and passes with the 1.2 `unit_x` tolerance for numbered rows. The
same offset on a line without a number still makes neither a row nor a
continuation. Whether the real scan now gives 52 can only be checked in
the private setting.

**Honest counts.** Every review now ends its document notes with what was
found next to what the document states, e.g. "Found 120 candidate items in
2 instruments (60, 60). The document text states no item count, so the
count cannot be checked against it; compare the list with the source."

## Results (local Tesseract 5 with eng, lav, rus; Linux)

| Fixture (OCR language) | Before (36.0) | Expected | Found | Response schemes | Other evidence |
|---|---|---|---|---|---|
| numbered DOCX | 60 + 60, 0 schemes, stated count 4 | 60 + 60 | **60 + 60**, items 1–60 each | 2 (one per form): 4 labels from the instruction, codes 1–4, 60 items each, not confirmed | titles from headings; stated count `None`; 15 scoring groups; 2 references kept out |
| unnumbered DOCX | not recognised (`NoQuestionsFound`), stated count 4 | 60 + 60 | **60 + 60**, numbered by row order | 2: form 1 from the header row, form 2 from the instruction; codes 1–4; 60 items each; not confirmed | header row not an item; stated count `None`; 15 scoring groups; 2 references kept out |
| LV table scan (`lav`) | 16 of 52 | 52 | **52** (1–52); the bare `5` stays instruction text | 1 from the legend: 5 labels, codes 1–5, 52 items, not confirmed | 51 of 52 statements identical to the generator text (Latvian letters intact; 49 before 36.7); the other keeps OCR junk of two letters from the answer area; 6 numbers flagged (17–21, 24); 13 wrapped statements joined; no noise lines left to drop (44 before the rules were whitened); 52 regions; 2 references kept out |
| LV table scan (`eng`) | — | 52 | **52** | 1 from the legend (letters without diacritics), 52 items | numbers 17–21 and 24 flagged; 0 statements identical (English OCR drops Latvian diacritics) |
| LV table scan (`lav+rus+eng`) | — | 52 | **52** | 1 from the legend: 5 labels, 52 items | 48 of 52 statements identical (the rest: OCR letter substitutions such as Cyrillic `Мг.` for `Nr.`, or two-letter junk); 6 numbers flagged |
| LV table scan in STIX General, a Times-like font (`lav`) | — | 52 | **52** (1–52) | 1 from the legend: 5 labels, 52 items, not confirmed | 46 of 52 statements identical; 6 numbers flagged; 13 wrapped statements joined (before 36.7: 26 rows, page 2 kept no table) |
| the same (`lav+rus+eng`) | — | 52 | **52** | 1 from the legend, 52 items | 41 of 52 statements identical; 6 numbers flagged |
| the same (`eng`) | — | 52 | **52** | none from the legend (English OCR misreads its labels; a row scheme covers 2 items) | 16 numbers flagged; the wrong OCR language for a Latvian form |
| inline scan (`eng`) | 52 | 52 | **52** | 0 (unchanged) | geometry path not used (inline numbers); 52 regions; 2 references kept out |

The LV rows were measured again at Stage 36.7, on the fixtures drawn with
matplotlib's fonts and Pillow's basic layout and with table rules whitened
before OCR; the STIX rows are new at 36.7.

The existing PSQ-like strain-table scan of the test kit
(`tests/synthetic_documents.psq_like_pdf`, page 2) also has a number
column: with the geometry path it gives the same 30 items, the same 30
prompts and the same header scheme as the text-only path.

Full suite on the Stage 36 stack (`claude/stage36-import`, on top of 36.1):
`python -m unittest discover -s tests -q` → 850 tests OK with 6 skips and
1 expected failure with the round-3 change (847 before its 3 tests; D5,
fixed by 36.3; D1–D4, D6–D10 are fixed; 36.0 had 10).

**Private check (authorized, local only; counts only).** The owner's real
two-page SACS-LV scan, read with local Tesseract:

| Importer | `lav` | `lav+rus+eng` | `eng` |
|---|---|---|---|
| Stage 36.0 | 16 of 52 | — | — |
| first 36.5 version | 45 of 52 | — | — |
| round 2 | 51 of 52 (17 read as text) | — | — |
| **round 3 (this branch)** | **52 of 52**, 1–52, no number twice | **52 of 52** | 51 of 52 (45 missing) |

With `lav`: one documented scale from the legend (5 labels, codes 1–5)
linked to all 52 items and **not confirmed**; 52 source regions; 3 prompts
still end in digit-like tokens from the answer area (was 32), which the
researcher removes in the review. English OCR is the wrong language for a
Latvian form; the review offers Latvian. No wording, image or value of the
private document is in this repository; these counts are the only record.

## OCR confidence semantics

OCR confidence remains Tesseract's per-word **character recognition**
score (0–100, `None` for text layers and Word files), aggregated per page
and per question region as before (high ≥ 85 mean and no word < 60;
review 60–84; low < 60; unknown with fewer than two scored words). The
"check this number" flags, joined-line flags and scheme issues are
structural review evidence, not confidence values; nothing in 36.5 turns
them into a score, and none of them says anything about reliability,
validity or correct scoring of a scale. Candidate counts are counts of
proposals awaiting review, not verified items.

## Known limitations

* A scoring key printed after the last form is attached to that form only
  (`evidence.scoring_groups` of the last instrument); it is not copied to
  the other form.
* Word tables with item numbers keep the line parser; their documented
  options only fill items that found no options of their own.
* The geometry path needs at least three clean numbers in a separate
  number column on a page; a page where OCR reads almost no number falls
  back to the line parser.
* Look-alike mapping covers A → 4, I l | ī í ì i ! [ ] → 1, S → 5, Z → 2,
  B → 8, G → 6, T → 7 and O o → 0 only, and only towards the expected
  number; a row missed entirely by OCR shifts inferred numbers until the
  next readable one (each inferred number is flagged).
* Answer-area junk of two or more letters (`LZ` for `1 2`, `du`) is never
  stripped and stays at the end of the prompt (on the synthetic Latvian
  table read with `lav`: 1 of 52 at 36.7, 3 of 52 before; 4 of 52 on the
  Windows pages of the Times New Roman table); a statement that really ends
  with digits right of the answer floor would lose them.
* An unreadable number on the last row of a table without answer digits
  cannot be confirmed by a next row and stays plain text.
* Rows above a table's first readable number are numbered back only when
  exactly that many clear rows stand there. Otherwise they stay plain text,
  and the researcher adds them in the review.
* Rule removal keeps rules lighter than grey level 200, rules shorter than a
  fifth of the page and bars thicker than about 1 mm. Where a rule crosses
  letters, the letter pixels within half the rule's thickness of its line are
  whitened with it.
* Legend labels are proposed as OCR read them; with an OCR language that
  lacks the document's letters (English for Latvian) labels and
  statements lose their diacritics.
* Glued answer digits (`1283845`) are removed from the statements but are
  not used as per-row codes; the codes come from the legend.
* Inline-number scans keep the line parser, including its existing
  behaviour of keeping a glued answer token (`12345`) at the end of the
  prompt on `synthetic_sacs_scanned_52.pdf`.
* Validation used synthetic documents only; real documents must still be
  compared with the source page by the researcher, and no accuracy claim
  is made for them.

## Review wizard (36.5 UI)

The engine above is reviewed in the workspace's import wizard
(`workspace_questionnaires.ImportPage`; review sessions in
`import_review.py`). Tests: `tests/test_stage36_import_ui.py` (harness,
English, Latvian and Russian); packaged-EXE journeys `import-cope-docx`
and `import-scan-lv` in `tools/windows_gui_e2e.py` (spec §14 journeys 5
and 6). The engine modules were not changed.

**What changed.**

* **Source / version.** Every form of a document is a card: title, item
  count, the documented answer options with their evidence (header row,
  instruction before the table, legend or labels in every row, and page),
  pages, and "Review this form". With two or more forms nothing is chosen
  for the researcher: steps 2–4, Next and "Create editable draft" wait for
  the choice, and the status says so. The chosen card says it is chosen;
  switching to the other form and back keeps each form's own review (its
  checked items and confirmations are never carried to the other form).
* **One processing status** (spec §10 "Ошибки") above the wizard, a live
  region: *Source loaded* (reading the text), *Scanned pages detected*
  (no text layer: local OCR offered with a language choice, proposed from
  the interface language; nothing is read before), *Recognizing the
  scanned pages* (page progress, Cancel), *Candidates found* (N items in
  M forms, choose one), *Needs review* (K need attention, and the next
  open step), *Ready to create the draft*, or *Not imported* / *No
  questionnaire items found* with the reason and the next step. A failed
  reading names the document under review that stays unchanged, so an
  error and the counts on screen are never shown without the difference
  being explained. A successful OCR stays as a line of the status ("Local
  OCR read pages 1 and 2 (language: Latvian). Compare every item …").
  A PDF with a text layer is still read with OCR automatically on its image
  pages (Stage 34.5), in the language its text suggests; "Read the scanned
  pages again" reads it in another language.
* **Autosave and resume.** Each document's review is kept in
  `<data>/import_sessions/<sha256 of the bytes>.json` (beside `surveys`,
  written atomically after every change): the chosen form, the step, the
  items compared with the source, wording corrections and scale reviews (as
  an ordered list of the researcher's own actions), the confirmations, the
  last selected item, the OCR language and the file's path. Opening the
  same bytes again restores it; after a restart the Questionnaires page and
  the empty Import page offer "Continue reviewing <file> — N of M checked"
  while the file is still at its path with the same SHA-256. The restored
  review opens at the item last selected, scrolled into view. Restoring
  replays only the researcher's own actions, and only on a form whose fresh
  reading has the same fingerprint (items, wording, scales); unknown or
  malformed entries are ignored, so nothing is ever confirmed by a restore.
  Creating the draft or "Discard this review" (asked first) removes the
  file. No network is used (a test forbids sockets during the whole flow).
* **Keys on the items step**, routed through the shell's keyboard handler
  and active only there: F8 / Shift+F8 the next / previous item that needs
  attention, F9 mark the item checked and go to the next one, Alt+↓ /
  Alt+↑ the next / previous item (also within the "Needs attention"
  filter). None of them is a text-editing key; a caption lists them, and a
  "Checked, next item to check (F9)" button does the same with the mouse.
  The editor keeps one identity (key) as it moves, rows keep scroll keys,
  and the reached item is scrolled into view. Wording typed but not applied
  is kept for its item and marked "Not applied yet"; no key applies it.
  Every item can now be marked as compared with the source (before, only
  items needing attention could).
* **Long forms.** Above 150 items the list is shown 100 rows at a time, in
  fixed pages (rows never shift while the selection moves inside a page;
  moving past the last row opens the next page), with the filter, stable
  row keys and the editor under its row.

**Measured** (Linux, Python 3.13, Flet 1.0.5; Tesseract 5.3.4):

| Measure | Result |
|---|---|
| Two unnumbered 60-item Word forms → draft of the chosen form | **9 interactions** after the Open dialog; 60 items, the form's own options |
| Scanned Latvian 52-item table → draft | **12 interactions** (English interface), **10** (Latvian interface, Latvian proposed); 52 items, one legend scale |
| Local OCR of the 2-page scan in Latvian | about 8 s (the same on restore: the scan is read again) |
| Items step with 200 items, one build of the page (median of 7; three runs) | **13–24 ms** with a 100-row page; 29–40 ms with all 200 rows; the test fails above 600 ms |
| Flet's patch of the rebuilt page for one selection (three runs) | 24–30 ms with a 100-row page; 33–36 ms with all 200 rows |

**Limitations.**

* The Windows journeys were written against the same texts and controls as
  the harness tests, but they run only on Windows (`windows-gui-e2e.yml`);
  they were not run for this change.
* The OCR language is asked for only when a PDF has no text layer at all;
  other PDFs are read automatically as before and can be read again in
  another language.
* A restore reads the document again (OCR included) and restores a form
  only if that reading is identical; another OCR engine or language data
  version can therefore start a new review (the status says so).
* The filter, the list page and wording typed but not applied are not
  saved; a review is found again only through the same file at the same
  path (or by opening the same bytes from anywhere).
* Items reached with a key, "Next item that needs attention" or a restore
  are brought into view with Flet's `scroll_to(scroll_key=…)`, which
  decides where the row lands (the harness checks the call, not the
  pixels); mouse clicks keep the clicked row under the pointer as before.
  On macOS, Option+↑/↓ inside the wording field also moves the caret.
* Forms up to 150 items are listed whole (the 120-item journey is
  unchanged).

## Local OCR speed on the packaged Windows program (36.7)

The first packaged-EXE run of `import-scan-lv` (run 42656712671) failed:
both pages of the synthetic Latvian table scan stopped at the per-page time
limit ("Local OCR exceeded its time limit"), which the status line explained
with the language kept. The same pages take 2.7–3.6 s each here (Tesseract
5.3.4, Linux); in the same Windows run the bundled engine (5.5.4) needed
about 15 times as long as here for the 30-item questionnaire page. Two
changes:

* The OCR process runs with one OpenMP thread (`OMP_THREAD_LIMIT=1` unless
  the researcher set it): here both table pages take 5.8 s with one thread,
  6.1 s with two and 6.4 s with four, and OpenMP threads that spin while they
  wait are a known cause of slow Tesseract runs on Windows.
* The per-page limit of the layout OCR is 180 s (was 90 s). It is a safety
  limit for an engine that hangs, not a budget: progress and Cancel are shown
  for every page.

The journey now records the engine's own time for page 1 outside the
program (`direct_ocr_page_1_lav`) and the time in the program
(`ocr_in_program_seconds`), so the Windows numbers are measured, not
assumed.

## The Latvian table read on the packaged Windows program (36.7)

The next packaged-EXE run of `import-scan-lv` (installer run 42669384359,
on #61) finished its OCR but read 45 of 52 items. The journey keeps the
bundled engine's own reading of both pages (page images and Tesseract TSV,
`ocr/` in the evidence), so the reading could be replayed and examined here.

The fixture was not the Linux fixture. The generator drew the table with
the computer's fonts: Times New Roman on the Windows runner, DejaVu Serif
on Linux. Two changes follow:

* The generator now uses the fonts that matplotlib ships and Pillow's basic
  text layout, so every platform gets the same pages. Pillow shapes text
  with libraqm on Linux and cannot on Windows; libraqm set the text about
  1 % narrower, so two short statements wrapped on Windows and item 26 no
  longer fitted on page 1 (the first packaged run with the bundled fonts
  stopped there). The answer digits now stand 20 px further right, which
  keeps the designed wrapping: 13 long statements, 4 of them on three lines.
* The Times-like case is kept as a fixture of its own,
  `synthetic_lv_table_scan_52_stix.pdf`, set in STIX General.

The engines read alike. On the Windows page images this engine finds 46
items and the Windows engine finds 45, with the same rows lost. The losses
came from the typeface, not from the engine. They exposed three weaknesses
of the importer, all reproduced on the STIX variant:

1. **Rules between rows made Tesseract drop whole text lines.** Tesseract
   reads the page as one block (`--psm 6`). Rows 29 and 42–45 were missing
   from the TSV itself. The OCR input is now cleaned first (`ocr_rules.py`):
   * A rule is a long, thin, nearly straight run of ink: at least a fifth of
     the page long and at most about 1 mm thick.
   * Each rule is traced along its fitted centre line to its real ends and
     whitened.
   * Letters that touch a rule lose only the touching pixels.
   * Filled bars, short rules and light lines stay.
   * Word boxes keep the coordinates of the original page, which stays the
     page shown to the researcher.
   * A page without rules is passed on unchanged, byte for byte.
2. **A legend line read as a numbered row tilted the statement column.** The
   legend's `4-` was read as `4 bieži`, without its dash. It pulled the
   least-squares fit of the statement column so far that page 2 kept no
   table. The column is now a Theil–Sen fit, which a few far-off points
   cannot tilt.
3. **Lone digits at the top of the table were misread.** OCR read `1.` as
   `ls`, `2.` as `vē` and `3.` as `K`, so the sequence started at 4. Rows
   above the first readable number are now numbered back from it, but only
   when exactly that many clear rows stand there. A clear row has:
   * a short token in the number column;
   * a statement of three or more words;
   * answer digits.

   Each such number is flagged "item number inferred from order".

Rows numbered 1–52 (before → after):

| Reading | `lav` | `lav+rus+eng` | `eng` |
|---|---|---|---|
| `synthetic_lv_table_scan_52.pdf` (DejaVu) | 52 → 52 | 52 → 52 | 52 → 52 |
| `synthetic_lv_table_scan_52_stix.pdf` | 26 → 52 | 26 → 52 | 52 → 52 |
| The same STIX table laid out by libraqm (as first generated here) | 0 → 52 | 26 → 52 | 50 → 52 |
| The captured Windows pages (Times New Roman) | 46 → 52 (5 numbers inferred and flagged) | — | — |
| The owner's SACS-LV scan (local only, counts only) | 52 → 52 | 52 → 52 | 51 → 52 |

The owner's scan is rotated by about 1.7° and has rules between some rows.
Its cleaned pages read better:
* `lav` gives 49 printed numbers, 3 normalised and none inferred (before:
  43, 8 and 1).
* The legend is found on both pages.

Removing the rules takes 0.1–0.3 s per page here. OCR of ruled pages got
faster: the two DejaVu pages with `lav+rus+eng` take 6.0 s instead of 15.1 s.

The journey also reads the STIX variant with the program's code and the
bundled engine outside the program, as a diagnostic
(`stix_table_outside_program`).

