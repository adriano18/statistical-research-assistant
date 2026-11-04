# Stage 30 — Scientific Questionnaire Importer

## Researcher workflow

1. Open **Questionnaires → 1. Build → Scientific importer · Word / PDF questionnaires**. Select DOCX, text-based PDF, or legacy DOC (the latter requires a locally installed antiword program; otherwise convert the document to DOCX in Word).
2. **Choose ONE instrument and version** from the list. Original source-line excerpts and approximate source page are displayed alongside proposed editable questions. DOC/DOCX physical page numbers are not recoverable reliably; refer to the original document.
3. Check the entire question list, version, rights, scoring, wording and language, plus warnings about image-only pages and conditional logic.
4. Check **I verified the instrument version, wording, permissions and extracted question list against the source**. The default draft is unscored. Optionally approve a proposed numeric response scale; independently approve reversed items. Approval is required for these proposals.
5. Select **Use extracted questions as editable draft**. Unsaved draft replacement requires separate consent. Published survey versions and collected responses are untouched.
6. Review every item in the ordinary editor before publishing: codebook, response semantics, missingness, consent, pages, score direction and skip logic.

**A source document is not evidence that an instrument is psychometrically validated.** No automatic diagnoses, thresholds, norm claims, reverse-scoring of participant responses or third-party uploads are performed. A checked reverse-item flag remains metadata until the researcher explicitly processes the data.

## Recognized versus uncertain structures

| Input | Stage 30 behavior |
| --- | --- |
| Numbered PDF/DOCX items (including 1., 1), and ISMA-style 1  Item) | Parse contiguous item sequences and conservative wraps |
| Word table with [ ] or A) / B) choices | Propose single/multiple choice types for review |
| UCLA booklet containing several named versions | Isolate each candidate version instead of merging |
| Numeric anchors such as 0–4, 1–4 | Propose labeled numeric codes, disabled until confirmation |
| Explicit reverse-item list or star markers | Propose key directions, disabled until separate confirmation |
| Yes / No table columns | Propose textual answers, never invent 1/0 codes |
| Conditional phrase “If Yes to Question 8” | Warn, do not invent routing |
| PDF with scanned/image-only scale table and selectable bibliography | Reject bibliography as items; request independently approved local OCR |
| Legacy DOC without local antiword binary | Explain DOCX conversion |
| Purchase-only/licensed questionnaires | Warn about reproduction rights; never reconstruct unavailable licensed item banks |

Complex nested rating matrices, layouts with multiple columns, and scans without text are not yet reliably convertible. This importer must be considered a **human-reviewed drafting tool**, not a validated psychometric test generator.

## Privacy-preserving audit of the supplied examples

Synthetic CI fixtures model the input characteristics of UCLA short, UCLA multi-scale compilation, ISMA Stress, PSS-10, PSQ and legacy Word demographic/conditional questionnaires. Full copyrighted questionnaires are not stored in the repository. The six private uploaded files are not available to GitHub Actions.

After copying those original documents to your research computer, run this command from the repository root and provide your own file paths:

~~~powershell
python tools/audit_local_survey_docs.py "C:\Research\UCLA-Questionnaire.pdf" "C:\Research\Stress-Questionnaire-F2.pdf" "C:\Research\percieved stress scale.pdf" "C:\Research\Perceived Stress Questionnaire (PSQ).pdf" "C:\Research\Self_Measures_for_Love_and_Compassion_Research_LONELINESS_AND_INTERPERSONAL_PROBLEMS.pdf" "C:\Research\QUESTIONNAIREEdited1.doc"
~~~

The audit prints instrument titles, question counts and warnings only, not item wording. An explicit refusal for the image-backed PSQ is currently a safe outcome. Always compare all extracted pages with the original source/manual and verify license rights.

## Engineering follow-ups

- Visual side-by-side page rendering with explicit location confidence rather than text excerpts.
- Optional, fully local OCR with researcher approval and controls for uncertain text.
- Rich Word matrix/grid capture and conditional rules.
- Version-specific scale scoring recipes with missing-value policy and reproducible source references.
- Native Windows/macOS GUI smoke tests and restricted licensed-source regression corpus.
