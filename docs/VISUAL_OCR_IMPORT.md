# Stage 31 — local OCR and visual Word/PDF questionnaire editor

## What happens inside the desktop program

Go to **Questionnaires → 1. Build → Scientific importer · Word / PDF questionnaires** and select your own PDF, DOCX or legacy DOC. The application now keeps the selected source in memory while you review it. PDF pages are actually rendered inside the desktop window using PDFium; the left side has a **Source page** selector and image. For DOCX/DOC, the preview is a visual reconstruction of paragraphs and table cells — it is not an exact layout/page number match to Microsoft Word. Longer Word documents can be browsed as multiple **preview segments**, each labeled distinctly from physical pages. The source itself is not modified.

On the right, select an extracted question. You can edit its wording, response type, options (one per line), section and required-answer flag, and click **Apply correction to extracted question**. You can choose other questions or source pages; each correction updates only the current in-memory proposal and keeps its original source excerpt. It is **not published** or saved to the SQLite answer database. Invalid questions are rejected without replacing the earlier proposal.

After reviewing, acknowledge source/version/rights and (optionally) proposed numeric codes and reverse-item flags; click **Use extracted questions as editable draft**. This opens the existing questionnaire editor for further adjustments such as page grouping, rating-scale labels, conditional routing, consent and preview. An existing unsaved draft is not overwritten without its separate confirmation. Published versions and collected responses remain untouched.

## Using OCR on scanned PDFs

The application performs OCR **locally** using a separately installed Tesseract executable and its trained language packs. The PDF image rendering library is installed with the Python requirements, but the Tesseract engine and languages must be installed on the researcher's computer.

1. Install Tesseract OCR for your operating system and the needed language packs (English: eng, Latvian: lav, Russian: rus). Verify the engine from PowerShell: `tesseract --version`. If Tesseract is installed outside PATH, set `TESSERACT_CMD` to the full executable path in the terminal **before** starting Flet.
2. Restart the desktop application, choose a scanned PDF and select the source page from the dropdown.
3. Choose the language combination and click **Run local OCR on this PDF page** or **OCR first 20 PDF pages**. The latter is bounded to 20 pages; for longer books use the individual-page review.
4. OCR text is re-parsed into candidate questionnaire instruments, with explicit OCR provenance and a warning that characters, rows and numbering can be wrong. Prior scientific and scoring confirmations are reset. Compare every proposed question and edit it using the right-hand editor, then review and confirm as above.

The current implementation uses Tesseract through a local subprocess; it makes **no network calls**. In browser/server mode, OCR is disabled, because a browser upload could otherwise send identifiable documents to a remote server. Use the **desktop application** for confidential questionnaire documents. PDF input is limited to 20 MB, 80 pages, and a bounded rendered image size; OCR runs on at most 20 pages per batch.

If no text is detected in a scanned PDF, the original source is still displayed. The absence of detected questions must **never** appear as a successful conversion. OCR does not invent validated questionnaires, psychometric norms, scoring keys, licensing rights or conditional logic.

## Known limitations

- Word layout is a **reconstruction**, not a pixel-perfect render of the original page. Convert a Word document to PDF locally if precise visual pagination is necessary.
- Scanned column/matrix tables may need substantial manual correction. The imported draft currently supports the existing questionnaire response types, but does not automatically reconstruct complex rating-matrix controls.
- OCR quality depends on scan resolution, skew, image contrast and language packs; full fidelity is not guaranteed. Some multi-page questionnaires need all relevant pages OCRed in sequence.
- The native Windows/macOS UI and Tesseract executable itself require a manual smoke test in addition to the synthetic CI tests. CI uses a mocked OCR text result and a real image-based PDF render, so it does not certify a particular user's installed OCR engine.

## Regression coverage

The test suite creates a real image-only PDF, renders its page as PNG, injects simulated local OCR output and verifies page provenance and unvalidated import warnings. It checks DOCX table/paragraph previews, atomic question corrections, bad option rejection, and Flet import behavior including source preview → correction → scientific confirmation → editable draft.

Run:

~~~powershell
python -m unittest discover -s tests -p "test_visual_survey_review.py" -v
python -m unittest discover -s tests -p "test_visual_survey_import_ui.py" -v
~~~

The repository still contains **no full text of the user's six private questionnaire documents**; those should be audited on the researcher's computer before any real study.
