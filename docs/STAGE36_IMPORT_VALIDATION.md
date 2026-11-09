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
   (≤ 2 characters, no digit, score < 40) are ignored;
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
Whether the real scan now gives 52 can only be checked in the private
setting.

**Honest counts.** Every review now ends its document notes with what was
found next to what the document states, e.g. "Found 120 candidate items in
2 instruments (60, 60). The document text states no item count, so the
count cannot be checked against it; compare the list with the source."

## Results (local Tesseract 5 with eng, lav, rus; Linux)

| Fixture (OCR language) | Before (36.0) | Expected | Found | Response schemes | Other evidence |
|---|---|---|---|---|---|
| numbered DOCX | 60 + 60, 0 schemes, stated count 4 | 60 + 60 | **60 + 60**, items 1–60 each | 2 (one per form): 4 labels from the instruction, codes 1–4, 60 items each, not confirmed | titles from headings; stated count `None`; 15 scoring groups; 2 references kept out |
| unnumbered DOCX | not recognised (`NoQuestionsFound`), stated count 4 | 60 + 60 | **60 + 60**, numbered by row order | 2: form 1 from the header row, form 2 from the instruction; codes 1–4; 60 items each; not confirmed | header row not an item; stated count `None`; 15 scoring groups; 2 references kept out |
| LV table scan (`lav`) | 16 of 52 | 52 | **52** (1–52); the bare `5` stays instruction text | 1 from the legend: 5 labels, codes 1–5, 52 items, not confirmed | 49 of 52 statements identical to the generator text (Latvian letters intact); the other 3 keep OCR junk of two or more letters from the answer area (`il`, `du`, `laiz BS.4`); 6 numbers flagged (17–21, 24); 13 wrapped statements joined; 44 noise lines dropped; 52 regions; 2 references kept out |
| LV table scan (`eng`) | — | 52 | **52** | 1 from the legend (letters without diacritics), 52 items | numbers 17–21, 24 and 44 (`44,`) flagged; 0 statements identical (English OCR drops Latvian diacritics) |
| LV table scan (`lav+rus+eng`) | — | 52 | **52** | 1 from the legend: 5 labels, 52 items | 48 of 52 statements identical (the rest: OCR letter substitutions such as Cyrillic `Мг.` for `Nr.`, or two-letter junk); 6 numbers flagged |
| inline scan (`eng`) | 52 | 52 | **52** | 0 (unchanged) | geometry path not used (inline numbers); 52 regions; 2 references kept out |

The existing PSQ-like strain-table scan of the test kit
(`tests/synthetic_documents.psq_like_pdf`, page 2) also has a number
column: with the geometry path it gives the same 30 items, the same 30
prompts and the same header scheme as the text-only path.

Full suite: `python -m unittest discover -s tests -q` → OK with 6 skips and
7 expected failures (D1–D5, D9, D10; 36.0 had 10).

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
  stripped and stays at the end of the prompt (3 of 52 on the Latvian scan
  read with `lav`); a statement that really ends with digits right of the
  answer floor would lose them.
* An unreadable number on the last row of a table without answer digits
  cannot be confirmed by a next row and stays plain text.
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
