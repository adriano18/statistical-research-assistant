# Stage 31–32 — local OCR, spatial review and questionnaire matrices

## Stage 32 at a glance

* **No separate installation on Windows.** The Windows desktop package
  contains a pinned Tesseract 5 engine with English, Latvian and Russian
  language data. Check it under **Settings → Offline OCR engine…**.
* **Spatial review.** Every recognized word keeps its position on the page.
  Questions are highlighted directly on the rendered PDF page; click a box to
  open that question, zoom from 50–300 % without losing alignment.
* **Two separate kinds of certainty.** *OCR confidence* is Tesseract's raw
  character-recognition score per word; *structure status* is a rule-based
  check of how the question was reconstructed. Neither says anything about
  reliability, validity or correct scoring of a scale.
* **Matrix editor.** Row × column rating grids (Likert-type scales) from
  Word tables, text-based PDFs and scans become an editable grid that must be
  verified before its rows can be used, with numeric codes and reverse-keyed
  rows confirmed separately.

![Spatial overlay review](images/stage32_spatial_overlay.png)

### The split-screen importer

Open **Questionnaires → 1. Build → Scientific importer · Word / PDF
questionnaires** and choose a document. On wide windows the source page is on
the left and the review tools are on the right; on narrow windows they stack.

Left side:

* **Source page**, **Zoom** slider and **Page view rotation** (0/90/180/270°
  clockwise, for sideways scans — the file itself is never changed).
* Coloured boxes: **blue** = selected question; **green / amber / red / grey**
  = OCR high / review / low / unknown; **purple** = text that is not linked to
  any question. Clicking purple text never creates a question.
* OCR buttons (current page or first 20 pages), **Cancel OCR** and **Check OCR
  engine**. OCR runs at the current view rotation. If you rotate the view
  after OCR, overlays are hidden until you rotate back or re-run OCR.

Right side:

* The existing question editor (wording, response type, options, section,
  required flag).
* **CONFIDENCE · selected question**: the OCR confidence summary (mean,
  minimum, low-scoring words) and the structural heuristic with its reasons.
* **SOURCE REGIONS**: adjust the selected box in page percentages, **Split**
  it (between lines, or at the widest word gap), **Merge** all boxes of the
  question, **Unlink**, **Revert this question** or **Revert all regions**.
  **Link mode** lets you click purple text to attach it to the selected
  question.
* **REVIEW QUEUE**: lists questions with low/unknown OCR confidence, no linked
  region, or structural flags, plus the count of unresolved matrix cells.
* **MATRIX EDITOR** (when a grid is detected), described below.

Any change to regions, matrix cells or question wording resets the
scientific, numeric-code and reverse-key approvals.

### Shared response scales (Likert / frequency tables)

Questionnaires such as a 20-item frequency inventory print one response scale
for many rows (`O S R N`, `Never Rarely Sometimes Often`, `1 2 3 4`). The
importer treats them as **questions sharing one response scale**:

* The scale comes from the column header, this document's own legend
  (`O = Often   S = Sometimes …`), codes printed in each row, and the
  reconstructed matrix. Every matrix row is linked to its extracted question
  and source region. Labels stay exactly as documented; abbreviations become
  words only when the same document defines them.
* **Original and revised versions stay separate.** When numbering restarts at
  1 after a new heading (or a new scale header/legend/page), a new instrument
  starts. Legends, codes and reverse-scoring notes never cross versions.
* Linked questions are proposed as fixed choices but marked **NOT verified**.
  An amber banner ("20 questions use an unverified 4-choice scale …") blocks
  **Use extracted questions as editable draft** until the scale is reviewed.
  A matrix is never silently imported as free text.
* **RESPONSE SCALE REVIEW** (top of the right-hand panel) shows the evidence,
  linked items, problems (undefined abbreviations, possibly incomplete
  two-line labels, unreadable or differing cells) and editable labels, codes
  and reverse-keyed items for the whole scale. It has three independent
  confirmations:
  1. **Confirm structure** — the linked questions become `single_choice` with
     the documented labels;
  2. **Confirm numeric coding exactly as printed** — `rating_scale` with those
     codes (only when every category has a printed code);
  3. **Confirm reverse scoring** of the listed items (only after numeric
     coding; the source statement is shown, e.g. "Items 1, 5, 6 … are reverse
     scored" or "Score 5-circled number for items …").
  Press **Apply scale review to all linked questions**. Editing labels, codes
  or reverse items, or detaching a question by editing it manually, clears
  the confirmations. **Not a shared scale** keeps the questions as text by
  explicit decision. **Show this scale on the source page** jumps to the rows.
* Text-layer PDFs show "PDF text layer — OCR confidence does not apply"; only
  scanned pages report OCR word confidence.

### Answer choices printed after every item (coping-inventory layouts, #20)

Some inventories print the complete answer set again under or beside EVERY
item, so that respondents circle a code — for example a 28-item coping
checklist with four cells per row (`1` *NOT AT ALL* · `2` *A SMALL AMOUNT* ·
`3` *A FAIR AMOUNT* · `4` *VERY MUCH*; the labels are often tiny, uppercase
and wrapped over two lines). Read as text, the codes look like item
numbers. The importer handles this layout as follows:

* **Repeated block by consensus.** An ascending run of codes (`0`/`1`, `2`, …)
  each followed by 0–4 label lines is accepted as the answer block only when
  the same codes and labels follow at least three items. Every copy is
  removed from the item text; the codes and labels may also share a line
  (`1 NOT AT ALL`) or use circled digits (`①`). Each choice's label is the
  spelling most copies print; on OCR pages near-identical spellings are
  grouped first and the group's most frequent spelling wins, so a garbled
  copy (`NOT AT An`) cannot outvote the printed label just because it
  resembles several other garbles.
* **Numbers joined with their prompts.** A standalone number line (`1`), a
  number on the prompt's first line (`17 During …`), a circled number (`①`)
  or a number drawn inside a circle (text-layer `1`) is joined with the
  1–6 prompt lines that follow it (sequence logic — no geometry needed, so
  the same rules work for text layers, OCR text and Word tables). A number
  OCR cannot read is inferred from the order and flagged on that item.
  Page headers/footers between items stay outside the prompts; item order
  (1-based) and the page of every item are kept.
* **One shared scale.** All items with the common block are linked to ONE
  `ResponseScheme` (evidence `item_block`, `+matrix` when the page geometry
  or a Word table also yields the grid). Labels stay exactly as printed —
  only whitespace and apostrophe variants (`ʼ`, `’` → `'`) are normalised and
  uppercase is kept; codes are proposed only because they are printed. The
  items are proposed as `single_choice`, never as free text, and the usual
  banner ("28 questions use an unverified 4-choice scale …") blocks the
  draft until **Response scale review** confirms the structure (and,
  separately, the numeric codes). When the repeated blocks print codes
  only, a code legend (`1 = …  2 = …`) or a scale header of the same
  instrument supplies the labels (evidence `item_block+legend` /
  `item_block+header`); a legend that disagrees with labels printed after
  the items is reported as an issue.
* **Differences are reported, never unified silently.** If the block printed
  after an item differs (another label, a missing choice, an OCR variant),
  the scale's issues name the items ("Printed answer choices differ on
  item(s) 7 (item 7: choice 3 reads “RATHER OFTEN” instead of …)") and the
  item carries the flag `answer choices differ from the common scale`. A
  different block repeated identically after two or more items becomes a
  separate scale.
* **Missing items block the draft.** Item numbers absent from an otherwise
  consecutive sequence (or named by a documented scoring rule but not
  found) are reported: "Item 14 is missing from the numbered sequence
  1–28. Check the source page, add the item(s) or confirm that the source
  omits them before importing." The banner shows it, and the draft is
  refused until the item is added or **I checked the source: the missing
  item number(s) are not printed there** is ticked.
* **Form fields are not items.** Lines such as *PARTICIPANT NAME · DATE ·
  RATER* or a link to an online version are never items and never
  become the instrument title.
* **Word tables.** Rows `No. | Statement | four cells` work with a code and
  label in every cell (two paragraphs) or with the labels as column
  headers and codes in the cells (then the Word-table matrix supplies the
  labels).
* **Scans.** Tesseract reads a row of answer cells together with the prompt,
  left to right. When at least three rows print the same ascending codes in
  aligned columns with labels under them, the page boxes are regrouped into
  "number, prompt, then each code with its label" before parsing. Label
  spellings are compared tolerantly on OCR pages (and every OCR variant is
  still listed as an issue). If OCR cannot read the small labels at all, the
  codes and rows are kept and the labels must be entered.

#### Letter-spaced PDF text layers

Designed forms often position every glyph separately. Text extractors then
either split words (`sched ule`, `m arked`, `A FA IR`) or put a space between
every glyph (`s c h e d u l e  f o r`). The importer repairs only
whitespace, conservatively, from PDFium character boxes:

* two fragments are joined only when both neighbouring characters are
  letters on the same baseline and the gap between their advance boxes is
  small — below 0.16 of the line's median advance width, or below 70 % of
  the real word spaces of the same line when that line has space
  characters; a gap of ≥ 0.45 advance widths is never closed, nor is a
  line or column change. This holds whether PDFium or another extractor
  put the space there (their space thresholds differ);
* when an extractor glues text across a real line change without any
  whitespace (pypdf 6.21 groups text at nearby baselines into one line:
  `inventedgarden`, `1NOT ATALL`), the line is cut at PDFium's line
  changes. On `/Rotate` pages PDFium lists the lines in another order, so
  the line is matched piece by piece; a piece that runs on into another
  line and stops inside it is cut back to that line change, because
  wording repeated on every item would otherwise match a neighbouring item;
* for an extractor line with a space between every glyph, single spaces
  join and runs of two spaces separate words, but a wide gap in the glyph
  geometry (an item number before its prompt, form-field columns) always
  stays a space;
* without usable geometry a text-only rule handles such lines (single
  spaces join, double spaces separate, a digit next to a letter keeps its
  space);
* every changed line is kept as a `SpacingRepair` (page, original,
  repaired, joins, restored gaps, method `geometry`/`text`) in
  `ScientificDocumentReview.spacing_repairs`; affected items get the flag
  `spacing repaired` and a note, and a document warning summarises the
  repair. Ordinary text layers are left unchanged.

#### Documented scoring — review-only evidence

Instrument editions and translations document different scoring (for
example a few broad groups averaged over their items in one edition, many
two-item subscales in another). The importer keeps
the verified response scale separate from any scoring recipe and only
records what THIS document states: group name, listed items, aggregation
word (mean/sum), stated number of values, printed range, page, source line
and whether it came from the text layer, a Word file or OCR. It never
infers subscale pairings, totals, reverse keys or norms, and nothing is
applied to questions, codes or exports — not even after approval.

#### Interface for the Stage 33 review UI

`InstrumentCandidate.evidence` is a frozen `scoring_evidence.ReviewEvidence`:

| Field / member | Meaning |
|---|---|
| `scoring_groups: tuple[ScoringGroup, ...]` | documented groups: `id`, `name`, `items`, `aggregation` (`mean`/`sum`/`unspecified`), `stated_count`, `value_range`, `page`, `source_line`, `evidence` (`pdf_text_layer`/`docx`/`doc`/`text`/`ocr`), `issues` (unknown items, count mismatch, OCR only), `approved`, `ocr_only` |
| `scoring_statements: tuple[ScoringStatement, ...]` | other scoring sentences (`page`, `text`, `evidence`) |
| `missing_items: tuple[int, ...]` | numbers missing from the item sequence |
| `item_flags: tuple[(number, flags), ...]`, `flags_for(n)` | per-item flags: `item number inferred from order`, `answer choices differ from the common scale`, `prompt joined from N lines`, `spacing repaired`, `read by OCR` |
| `issues` | instrument-level notes (items in several groups, review-only reminder) |
| `missing_acknowledged`, `has_scoring`, `ocr_only`, `scoring_approved`, `unassigned_items(numbers)` | state and helpers |

Functions in `scientific_survey_import`:

* `missing_items_banner(candidate)` / `review_banner(candidate)` — blocking
  texts (scale, then sequence), `None` when nothing blocks;
* `acknowledge_missing_items(candidate)` — researcher confirms the numbers
  are absent in the source;
* `approve_scoring_evidence(candidate, group_ids=None, *, ocr_checked=False)`
  — marks groups as checked; requires confirmed numeric codes for every
  listed item and `ocr_checked=True` for OCR-only evidence; changes nothing
  else;
* `reviewed_draft(...)` refuses unconfirmed scales and unacknowledged
  missing items; `draft_questions(...)` validates a partial review without
  these gates.

`ScientificDocumentReview.choice_layout` (`repeated_choices.ChoiceLayout`)
holds the common block (`template`: codes, labels, page) and every item's
own printed block (`items`: `BlockItem` with `number`, `prompt`, `page`,
`block`, `number_source` `standalone`/`inline`/`circled`/`inferred`,
`prompt_lines`, `deviations`).

#### Checking a private copy without sharing its wording

~~~powershell
python tools/audit_local_survey_docs.py "C:\Research\coping-form.pdf"
python tools/audit_local_survey_docs.py --ocr eng --items "C:\Research\coping-form.pdf"
~~~

The report lists pages, spacing repairs, the repeated block (codes, label
lengths and a hash), how numbers were printed, item numbers found and
missing, question types, scales, documented scoring groups, item flags,
what blocks the draft, linked page regions and matrices — for the text
layer and, with `--ocr`, separately for local OCR. Titles, labels and names
appear only as a hash prefix and a length (for example `#1a2b3c4d/42`), so the output
can be shared to discuss a discrepancy. `--show-titles` adds titles and
warnings, which may contain source text.

### True/False, T/F and Yes/No answers

Binary answer formats are recognized from evidence in the source:

| Evidence | Example | What happens |
|---|---|---|
| Each item's own row | `12. I enjoy invented trips.   T  F` | converted to a `single_choice` with those labels |
| Shared column header | `T F`, `Statement  True  False`, a Word table header `No. │ Statement │ T │ F` | every following text item of the same instrument gets the labels |
| Instructions only | "Answer each statement True or False." | **not** converted automatically; the **BINARY ANSWERS** panel offers a reviewed bulk conversion |

* English, Russian and Latvian forms are recognized: `T/F`, `True/False`, `Yes/No`, `Y/N`, `Верно/Неверно`, `Правда/Неправда`, `Да/Нет`, `Jā/Nē`, `Patiesi/Nepatiesi`, `Pareizi/Nepareizi`. OCR variants such as `T | F`, `T/F`, a Cyrillic `Т` or a speck before the `T` (`tT F`) are tolerated.
* True/False and Yes/No are different formats and are never swapped. Labels stay as printed. Single letters stay letters unless the document defines them (`T = True`, `True (T)`).
* No numeric 1/0 codes, answer keys or reverse scoring are assigned. Star marks on binary items are not treated as reverse keys.
* Question wording alone ("Is it true or false that…?") never creates a binary item. A header that appears after open questions does not change those earlier questions.
* **BINARY ANSWERS · shared response format** (right-hand panel) shows the evidence, page and number of items. Edit the two labels (for example `T`/`F` → `True`/`False`), tick *I checked the source…* and press **Apply binary answers to matching items**. Manually edited questions are not overwritten, and every approval is reset afterwards.
* Word tables and text/OCR geometry also produce a two-column matrix proposal in the matrix editor.

### OCR confidence thresholds

| Status | Rule (mean of Tesseract word confidences, ignoring `-1`) |
|---|---|
| High | mean ≥ 85 and no word below 60 |
| Review | mean 60–84, or any single word below 60 |
| Low | mean < 60 |
| Unknown | fewer than 2 scored words — e.g. text-layer PDFs, Word files, or no OCR |

These are engine scores for characters, not calibrated probabilities. A
"high" question can still be split wrongly, belong to a different version of
a scale or have a wrong scoring key. The structure status ("consistent",
"needs review", "unresolved") is deliberately not a percentage.

### Matrix editor

![Matrix editor](images/stage32_matrix_editor.png)

1. Choose a **Detected response matrix**. Its source is shown
   (`docx_table`, `pdf_text_layer` or `tesseract_tsv`) together with pages.
2. Read the **Review** and **Blocking** messages: overlapping header labels,
   missing or ambiguous cells (also outlined on the page), descending code
   order, numbering gaps, rows continued after a page break, unnumbered rows.
3. Edit column labels and codes, item numbers, question text, cell contents
   and reverse-key marks directly in the grid, then **Apply grid edits**. Use
   the arrows/× buttons to move or delete rows and columns, and **Add row** /
   **Add column** when the reconstruction missed something. **Accept flagged
   cells as shown** confirms legitimately blank or unusual cells.
4. **Verify grid against source** is enabled only when nothing is blocking.
   The read-only **Original detected grid** always shows what was detected.
5. Optionally tick **Apply printed numeric codes as scale values** and
   **Apply marked reverse-keyed rows** — each is an explicit researcher
   decision; without them rows become labelled single-choice questions.
6. Tick the scientific review confirmation (and draft replacement if needed)
   and press **Use verified matrix rows as editable draft**.

Word tables are preferred for matrices because their cell structure is
explicit; merged header cells become a column *group* label, numeric header
rows become proposed codes, and multi-line cells are joined.

## Stage 31 — local OCR and visual Word/PDF questionnaire editor

## What happens inside the desktop program

Go to **Questionnaires → 1. Build → Scientific importer · Word / PDF questionnaires** and select your own PDF, DOCX or legacy DOC. The application now keeps the selected source in memory while you review it. PDF pages are actually rendered inside the desktop window using PDFium; the left side has a **Source page** selector and image. For DOCX/DOC, the preview is a visual reconstruction of paragraphs and table cells — it is not an exact layout/page number match to Microsoft Word. Longer Word documents can be browsed as multiple **preview segments**, each labeled distinctly from physical pages. The source itself is not modified.

On the right, select an extracted question. You can edit its wording, response type, options (one per line), section and required-answer flag, and click **Apply correction to extracted question**. You can choose other questions or source pages; each correction updates only the current in-memory proposal and keeps its original source excerpt. It is **not published** or saved to the SQLite answer database. Invalid questions are rejected without replacing the earlier proposal.

After reviewing, acknowledge source/version/rights and (optionally) proposed numeric codes and reverse-item flags; click **Use extracted questions as editable draft**. This opens the existing questionnaire editor for further adjustments such as page grouping, rating-scale labels, conditional routing, consent and preview. An existing unsaved draft is not overwritten without its separate confirmation. Published versions and collected responses remain untouched.

## Using OCR on scanned PDFs

**Windows desktop package:** nothing to install. The bundled engine is used
automatically; **Settings → Offline OCR engine…** shows its version, languages
and integrity.

**Running from source (developers, macOS, Linux):** install Tesseract 5 with
the `eng`, `lav` and `rus` language data (for example
`sudo apt install tesseract-ocr tesseract-ocr-lav tesseract-ocr-rus`, or the
Windows/macOS installers), check `tesseract --version`, or set
`TESSERACT_CMD` to the full executable path **before** starting the program.
`TESSERACT_CMD` always overrides the bundled engine.

1. Choose a scanned PDF and select the source page.
2. If the page is sideways, choose a **Page view rotation** first.
3. Choose the language combination — **put the document's main language
   first** (for example *All three · Latvian main* = `lav+rus+eng`). The
   bundled Tesseract 5.5 favours the first language: in CI, `eng+lav+rus`
   turned Latvian "nedēļa" into "nedéla", while `lav+rus+eng` kept it. Then
   click **Run local OCR on this PDF page** or **OCR first 20 PDF pages** (bounded to 20 pages). **Cancel OCR**
   stops a running job without changing the existing proposal.
4. Review the overlays, confidence, queue and matrix editor as described
   above. Prior scientific and scoring confirmations are reset after OCR.

OCR uses Tesseract through a local subprocess on a temporary image that is
deleted immediately; it makes **no network calls**. In browser/server mode,
OCR is disabled, because a browser upload could otherwise send identifiable
documents to a remote server. PDF input is limited to 20 MB, 80 pages and a
bounded rendered image size; OCR runs on at most 20 pages per batch, with a
time limit per page.

If no text is detected in a scanned PDF, the original source is still displayed. The absence of detected questions must **never** appear as a successful conversion. OCR does not invent validated questionnaires, psychometric norms, scoring keys, licensing rights or conditional logic.

## Known limitations

- Word layout is a **reconstruction**, not a pixel-perfect render of the original page. Convert a Word document to PDF locally if precise visual pagination is necessary.
- Answer choices repeated after every item are recognized only as an ascending run of codes starting at 0 or 1 that repeats after at least three items; descending blocks (`4 … 1`), choices printed inline on the item's own line (`… 1 NOT AT ALL 2 …`) and blocks without codes are not reconstructed. On scans, at least three rows must print the codes in aligned columns.
- OCR renders PDF pages at a bounded resolution: very small answer labels (about 4 pt) and small or circled item numbers may be unreadable (circled digits are often read as `@`). Then the labels must be entered and unreadable numbers are inferred from the order (flagged); a whole row missed by OCR shifts inferred numbers until the next readable one. Prefer the text layer when the PDF has one.
- Letter-spacing repair only changes whitespace and never guesses words: a space the text layer does not encode at all (a word gap no wider than the letter tracking) cannot be restored from geometry, and widely tracked title lines may keep extra spaces. Text drawn rotated inside an upright page is not repaired; whole pages with a `/Rotate` entry are supported.
- Matrix reconstruction is conservative: printed codes/markers or clear header labels are required to find columns; transposed grids (items as columns), rotated header text and hand-drawn tables are not reconstructed and must be entered manually. Ticked answers on filled-in forms are not interpreted.
- Matrix rows become ordinary questions sharing one scale (rating scale or single choice); a dedicated respondent-facing grid control is not part of this stage.
- OCR quality depends on scan resolution, skew, image contrast and language packs; full fidelity is not guaranteed. Small skew is handled by Tesseract; larger skew is not corrected automatically. Some multi-page questionnaires need all relevant pages OCRed in sequence.
- Word previews have no positional overlay (they are reconstructions); Word tables use the matrix editor instead.
- Region edits are review metadata for the import session; they are not saved with the published survey.
- High-DPI and screen-reader QA of the native window still need a manual check on Windows; see the steps below.

## Regression coverage

The test suite creates real image-only PDFs, renders them as PNG and — whenever a local engine is available (always in CI) — runs **real Tesseract** on synthetic scans: clean, noisy, skewed, sideways, wrapped questions and EN/LV/RU text. Mocked recognizers additionally cover deterministic edge cases. It checks DOCX table/paragraph previews, atomic question corrections, bad option rejection, and Flet import behavior including source preview → correction → scientific confirmation → editable draft.

Run:

~~~powershell
python -m unittest discover -s tests -p "test_visual_survey_review.py" -v
python -m unittest discover -s tests -p "test_visual_survey_import_ui.py" -v
python -m unittest discover -s tests -p "test_ocr_*.py" -v
python -m unittest discover -s tests -p "test_matrix_reconstruction.py" -v
python -m unittest discover -s tests -p "test_spatial_review_ui.py" -v
python -m unittest discover -s tests -p "test_real_tesseract_ocr.py" -v
python -m unittest discover -s tests -p "test_brief_cope_import.py" -v
~~~

## Manual Windows check (packaged app)

1. Unzip `StatisticalResearchAssistant-Windows-x64.zip` on a Windows 10/11
   PC **without** Python or Tesseract installed and start
   `StatisticalResearchAssistant.exe` (unsigned preview: SmartScreen may ask
   for confirmation).
2. **Settings → Offline OCR engine…** must report "bundled with this
   application", languages eng, lav, rus and "bundle integrity verified".
3. Import a fictional scanned questionnaire, run OCR, zoom to 50 % and 250 %,
   click boxes, split/merge/revert a region and correct a matrix.
4. Repeat at 150 % Windows display scaling and with Narrator enabled.

The repository still contains **no full text of the user's six private questionnaire documents**; those should be audited on the researcher's computer before any real study.
