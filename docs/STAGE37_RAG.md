# Stage 37.3 — the research library (Issue #69)

Offline lexical search over a project's own papers, plans, manuals and notes, with page and section citations, and an optional "Ask with sources" that sends only approved passages to the AI provider the researcher set up. The scope is `docs/STAGE37_NEXT_SPEC.md` §4 and Issue #69, plus four points of the independent review (`docs/STAGE37_FABLE_NARROW_REVIEW.md` on `claude/stage37-review`, §7): tokenizer evidence, identifier and free-text columns in AI data rows, an explicit backup choice for library files, and quoted spans checked in every AI answer.

- **Branch.** `claude/stage37-rag`, from `stage37/master-acceptance-interoperability-spec` (`2f9af71`). Not pushed; no pull request.
- **Rule of this file.** An item is *done* only when a named test proves it. Everything is synthetic: no real paper, manual, instrument or participant data is in the repository or in a test.

## 1. Architecture

| Part | File | Role |
|---|---|---|
| Store, reading, passages, search | `research_library.py` | No Flet. One library per project; FTS5 search with a pure-Python fallback. |
| Ask with sources | `library_ask.py` | No Flet. Builds the exact request from approved passages, sends it through `ai_providers`, checks the answer. |
| Page | `workspace_library.py` | The Research Library page and the card on the Project page. |
| Backups and copies | `project_store.py` (`_library_files`) | Adds the library to a `.sra` backup or a project copy only when the researcher chose so. |
| Quote check | `ai_assist.py` (`unverified_quotes`) | Every quoted span of every AI answer is looked up in what was sent. |
| Data rows | `ai_context.py` (`excluded_columns`) | Identifier and free-text columns never go with AI data rows. |
| Packaged self-test | `analysis_selftest.py` (`_library`) | FTS5 in the runtime's SQLite and an offline search, compared with the source run. |
| Benchmark | `tools/library_benchmark.py` | 13 tokenizer and query configurations on a labelled EN/LV/RU set. |
| Windows journey | `tools/windows_gui_e2e.py` (`research-library`) | The packaged program, driven through UI Automation. |

### 1.1 Storage

```
projects/<project-id>/
  project.sqlite3              unchanged (format 6); the library never writes here
  library/
    library.sqlite3            PRAGMA user_version = 1 (the library's own schema)
    sources/<sha256><ext>      the added files, content-addressed, never changed
    backup.json                the researcher's backup choice (only once chosen)
```

Tables of `library.sqlite3`:

| Table | Holds |
|---|---|
| `documents` | id, cite key (`D` + 8 hex of the SHA-256), title, file name, SHA-256, size, type (pdf, docx, txt, md), language (en, lv, ru, other), version label, page count, `imported_at`, source path, stored name, OCR pages and language, chunker version, `indexed_at` |
| `segments` | the extracted text of every PDF page (or of a whole document without pages) with its paragraphs and headings |
| `chunks` | the passages: document, ordinal, segment, page, section path, text, `start_offset`, `end_offset`, cite ID, token count |
| `chunk_index` | FTS5, external content over the view `chunk_search` (ё read as е), BM25 with `snippet()` |
| `postings` | the pure-Python index, used only where FTS5 is missing |
| `ai_transfers` | which passages went to an AI provider: cite IDs, provider, model, tokens, outcome (never the text) |
| `meta` | backend, tokenizer, folding, creation time |

- **The project format is untouched.** Project schema 6 is unchanged, and so is the `.sra` package format (version 1). A project without a library opens exactly as before. `test_research_library.IsolationTests` checks that the project database has no library table and is still format 6.
- **A newer library is refused without writing.** The format is read through a read-only connection first. `StoreTests.test_a_library_of_a_newer_version_is_refused_without_writing` compares the file bytes.
- **Concurrency.** Every operation opens its own connection: WAL, `synchronous=FULL`, a busy timeout, and writes serialised. A document can be indexed in a worker thread while the page searches.

### 1.2 Reading

| Type | How | Sections |
|---|---|---|
| PDF | pypdf text per page. Its text visitor gives each piece of text with its font size. | Lines set at least 1.15 × the body size are headings, ranked by size. The largest line of page 1 is the title unless the PDF metadata names one. Numbered lines ("2.1 Sample"), common section words in EN/LV/RU and short all-capital lines are headings too. |
| PDF image page | Read with the bundled local Tesseract (`ocr_runtime`, `--psm 3`), only when the researcher ticks *Read image-only PDF pages with local OCR* | A page with fewer than 25 letters in its text layer whose images cover ≥ 8 % of it. At most 60 OCR pages per document. |
| DOCX | python-docx, paragraphs and tables in document order | Heading styles (`Heading n`, `Title`, Latvian and Russian style names, outline level). A table row becomes its cells joined by a vertical bar. |
| Markdown | `#` and underlined headings | Fenced code is text. |
| TXT | paragraphs separated by blank lines | A short first line is the title. Numbered, common or all-capital lines are headings. UTF-8 (with BOM), UTF-16, else CP1251 or CP1257. |

All text is NFC-normalised, so a decomposed `ā` cannot split a word. Control characters are removed. Bare page numbers are dropped, and a word broken over two lines with a hyphen is joined.

Limits: 64 MiB per file, 2,000 pages, 4 million extracted characters.

Refusals are explained in words and store nothing (`ExtractionTests.test_unusable_files_are_refused_and_nothing_is_stored`): unsupported type, empty, password-protected PDF, damaged file, no text, too large.

### 1.3 Passages and citations

- A passage starts at a heading, which it includes, or continues its section.
- It grows to about 900 characters and is cut at sentence ends above 1,400.
- It never crosses a page or a section.
- A short last passage joins the one before it.
- Each passage is an exact slice of its stored page text: `segment.text[start:end] == passage.text`, checked for every passage (`test_pdf_pages_sections_title_and_exact_offsets`).

**Cite IDs.** A cite ID is the document key followed by a locator:
- `D3F9A1B2C-p4.2`: page 4, second passage;
- `D3F9A1B2C-s3.1`: section 3 of a document without pages.

The same bytes read by the same chunker version give the same IDs, in any library and after any reindex. Proved by:
- `test_cite_ids_are_the_same_in_every_library`;
- `test_reindexing_keeps_cite_ids_and_finds_outdated_documents`;
- `DocumentTests.test_reindex_all_keeps_the_citations`.

**Changes to the library.**

| What | How it works | Proved by |
|---|---|---|
| Dedupe | The same SHA-256 is never added twice, whatever the file name. | `test_the_same_bytes_are_never_added_twice` |
| Revisions | Another file with the same name gets a version label `vN`; the earlier one becomes `v1`. A label can also be typed. | `test_a_revision_of_the_same_file_gets_a_version_label` |
| Incremental reindex | `outdated()` lists documents read by an older chunker. `reindex_all(only_outdated=True)` reads only those, and pages read by OCR keep their recognised text without being read again. | `OcrTests.test_reindexing_keeps_the_recognised_text_without_reading_again` |
| Remove | Removes passages, FTS rows and segments in one transaction, then the stored copy. A copy another program holds open (Windows refuses to delete it) goes the next time the library is opened; it is never searchable. | `test_removing_a_document_removes_its_passages_index_rows_and_copy`, with FTS5's `integrity-check` against the content; `test_a_copy_held_open_elsewhere_is_deleted_the_next_time` |

### 1.4 Search

- **Query.** Query words are tokenised like `unicode61`. In the chosen configuration (§4):
  - EN/LV/RU function words are left out;
  - every other word is stemmed with English, Latvian and Russian endings;
  - each stem is searched as a quoted prefix, `"одиночеств"*`, joined with `OR`.
- **No query syntax reaches FTS5.** Quotes, `*`, `NOT`, `NEAR`, column filters and SQL fragments in a query are plain words (`test_query_syntax_is_never_passed_to_fts5`).
- **Ranking.** BM25 (`k1 = 1.2`, `b = 0.75`). Ties are broken by passage id, so the order is deterministic.
- **Filters.** Document type, language, and date added (since/until).
- **Snippets.** `snippet()` marks the matched words. FTS5 reads the ё-folded view, so the snippet's letters are restored from the passage itself ("Подсчёт", not "Подсчет"; `test_snippets_keep_the_documents_own_letters`).
- **Why this source?** The rank among all matches, the BM25 score, the query words found in the passage with their counts, the words it lacks, and the filters.
- **Pure-Python fallback.** Where FTS5 is missing, the library uses its own tokens (a mirror of `unicode61`), postings and BM25 (FTS5's formula, IDF floor `1e-6`).
  - Its tokens equal FTS5's on the whole corpus and on edge strings, for `remove_diacritics` 0, 1 and 2 (`test_python_tokens_are_the_tokens_of_fts5_unicode61`).
  - On all 51 benchmark queries its order, match counts and scores (to 9 decimals) equal FTS5's (`FallbackEquivalenceTests`).
  - A library built with FTS5 and opened without it, or the other way round, rebuilds its index from the stored passages (`test_switching_the_backend_rebuilds_the_index`).

### 1.5 The page

**Where it is.** *Project page → Research library → Open the research library*. The route `library` belongs to the Project item of the sidebar (`SUB_ROUTES`). The sidebar items and Ctrl+1…6 are unchanged (`PlaceTests`). Without an open project, the route leads to Home.

**Cards.**
- **Documents.**
  - *Add document…* opens the system's Open dialog (PDF, DOCX, TXT, MD, several files at once). The OCR choice and its language are shown when the engine runs here; a version label can be typed.
  - Indexing progress: page n of N, OCR page n of N, passages. *Cancel* stores nothing.
  - Each document shows its type, language, version, passages, pages, date added and file name, with *Open* and a one-action *Remove* (no dialog).
  - *Read every document again*.
  - The backup choice.
- **Search.** Query, *Search*, and the filters type, language and *Added*. Each result reads document | page or section | excerpt | version, with its cite ID.
  - *Open page n* shows a PDF page in the program's own page viewer (PDFium, previous/next page, the cited passage under the page).
  - *Open the document* opens other files in the system's viewer.
  - *Why this source?* explains the match.
- **Ask with sources.** See §5.
- **Badge.** "Local only · search never goes online".

**Project switch.** Switching project switches the library and forgets the page state: results, the question and selections (`IsolationTests.test_switching_project_switches_the_library_and_forgets_the_page`).

**Languages.** EN/LV/RU. LV and RU are drafts for native review. Every key exists in three languages with the same placeholders (`test_locale_audit`, `test_workspace_foundations`). No bare key is shown in any language (`LanguageTests`).

## 2. The independent review's four points

| Point | What was done | Proved by |
|---|---|---|
| 1. Tokenization: unicode61 folds Latvian diacritics but does not stem («одиночества» ≠ «одиночество», "lonely" ≠ "loneliness") | Benchmarked exact words, pure prefix (`term*`), multilingual stems and per-language stems, porter and trigram (with and without diacritic removal), ё→е (§4). The chosen configuration finds both probes at rank 1. | `test_the_reviewers_probes_find_the_inflected_words`, `test_the_reviewers_probes_rank_first` |
| 2. AI data rows sent every column | **Red test first** (`3fc204b`, marked expectedFailure), then the fix (`db7514e`). Identifier columns and free-text columns are left out of the rows by default. Identifiers are columns confirmed or suggested as identifiers, named like one, or holding unique codes with digits, even when bulk-confirmed as a category. Free text is prose, or text that is not a category. The request records what was left out. The assistant preview (`ai-preview-excluded`) and Settings (`ai-excluded-raw_data`) name the columns. With nothing left, no row is sent. | `tests/test_stage37_ai_rows.py` (5 tests, one end to end through the fake provider) |
| 3. GDPR and backups | An explicit per-project choice, **off by default**: *Include the library in backups and project copies*, with a caption on what it means. The Project card repeats it. `project_store` adds the library (a consistent snapshot of its database, the choice and the stored documents) to `.sra` backups and project copies only when it is on. A restored backup brings the same documents and cite IDs back. Schema 6 and the package format are unchanged. A deleted project takes its library to the trash with it. | `BackupChoiceTests.test_off_by_default_on_when_chosen_in_backups_and_copies`, `IsolationTests.test_each_project_has_its_own_library` |
| 4. Quoted spans | `ai_assist.unverified_quotes` looks up every quoted span ("…", “…”, „…“, «…», ‘…’; an ellipsis inside a quote separates parts) in what was sent, ignoring case, spacing, dash and apostrophe styles. It is used by both AI answers: the Results-page assistant (`ai-unverified-quotes`, also written into the note) and Ask with sources (`library-answer-quotes`). | `CheckTests.test_quotes_are_found_word_for_word_or_flagged`, `ResultsAssistantQuoteTests`, `CheckedAnswerTests.test_citations_numbers_and_quotes_are_checked` |

## 3. FTS5 in this Python and in the packaged Windows runtime

| Runtime | SQLite | FTS5 | trigram | trigram `remove_diacritics` | Evidence |
|---|---|---|---|---|---|
| This session (`venv-lock`, CPython 3.12.3) | 3.45.1 | yes | yes | yes | `CapabilityTests`, in-memory probes; `PRAGMA compile_options` lists `ENABLE_FTS5` |
| Packaged Windows program (CPython 3.12.16, standalone build 20261026, flet-dev/python-build release 20261027) | 3.49.1 (2025-02-18) | yes | yes (≥ 3.34) | yes (≥ 3.45) | Static inspection, below |

The packaged runtime was inspected statically, not run.
- The archive the build embeds, `python-windows-for-dart-3.12.16.zip`, was downloaded from that release (SHA-256 `dba7912df9f8c2b85e052aaf21e816af70178c38d26d41705250f4f58185fcc8`).
- Its `DLLs/sqlite3.dll` carries the source id `2025-02-18 13:38:58 873d4e27…` (SQLite 3.49.1).
- Its compile-option strings are `ENABLE_FTS3`, `ENABLE_FTS4`, `ENABLE_FTS5`, `ENABLE_MATH_FUNCTIONS` and `ENABLE_RTREE`, with the `fts5`, `bm25`, `snippet`, `trigram`, `unicode61` and `remove_diacritics` names present.
- These match the defines of CPython's `PCbuild/sqlite3.vcxproj` (FTS4 implies FTS3). The python.org Windows build that CI uses as the host Python comes from the same project file. That was not inspected here; the source run of the self-test records it.

**How CI checks it in the packaged program.** There is a packaged self-test, so the check was added to it (`analysis_selftest._library`). No workflow was changed:
- The Windows packaging job already runs the self-test inside the packaged program (`SRA_ANALYSIS_SELFTEST`) and compares it with the source run (`analysis_selftest.py --compare`).
- The new step `research_library` records the SQLite version, FTS5, trigram and the backend. It reads four synthetic documents (PDF, DOCX, TXT, MD), searches them in EN, LV and RU, renders a PDF page and checks the index.
- Its hash covers the backend and the ranking (title and locator), so a packaged runtime without FTS5 does **not** compare equal, even though its fallback still finds everything (`SelfTestTests.test_a_runtime_without_fts5_does_not_compare_equal`).
- The Linux job compares the self-test before and after pruning the same way.

## 4. Tokenizer benchmark (choose by evidence)

**Corpus.** `tests/library_fixtures.py` holds 12 invented documents, 51 passages: in each language a study manual in two revisions (with contradicting statements), a review and lab notes. The benchmark reads them as Markdown through the library itself.

**Queries.** 51 labelled queries, 17 per language:
- exact wording;
- inflected forms;
- Latvian without diacritics;
- Russian with е for ё;
- paraphrases;
- a typo in English and one in Latvian;
- the review's probes ("the painful gap of being lonely", «болезненный разрыв из-за одиночества», "sāpīgā plaisa vientulības dēļ").

**Metrics.** Recall@k is the share of a query's relevant passages among the first k, averaged over queries; a query with two relevant passages can reach only 0.5 at k = 1. MRR is the reciprocal rank of the first relevant passage among the first 10.

`python tools/library_benchmark.py` on SQLite 3.45.1:

| | Configuration | EN R@5 | EN MRR | LV R@5 | LV MRR | RU R@5 | RU MRR | All R@1 | All R@3 | All R@5 | All MRR | Index | Median query |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | unicode61 remove_diacritics 0 · exact | 0.941 | 0.902 | 0.765 | 0.735 | 0.941 | 0.912 | 0.755 | 0.882 | 0.882 | 0.850 | 36 KiB | 1.57 ms |
| B | unicode61 remove_diacritics 1 · exact | 0.941 | 0.902 | 0.882 | 0.853 | 0.941 | 0.912 | 0.794 | 0.922 | 0.922 | 0.889 | 36 KiB | 1.00 ms |
| C | unicode61 remove_diacritics 2 · exact | 0.941 | 0.902 | 0.882 | 0.853 | 0.941 | 0.912 | 0.794 | 0.922 | 0.922 | 0.889 | 36 KiB | 1.10 ms |
| D | unicode61 remove_diacritics 2 · prefix | 0.882 | 0.843 | 0.882 | 0.853 | 1.000 | 0.971 | 0.794 | 0.922 | 0.922 | 0.889 | 36 KiB | 1.52 ms |
| E | unicode61 remove_diacritics 2 · stem | 0.941 | 0.902 | 0.941 | 0.941 | 1.000 | 0.971 | 0.843 | 0.951 | 0.961 | 0.938 | 36 KiB | 1.58 ms |
| F | unicode61 remove_diacritics 2 · stem-lang | 0.941 | 0.902 | 0.941 | 0.941 | 1.000 | 0.971 | 0.843 | 0.951 | 0.961 | 0.938 | 36 KiB | 1.37 ms |
| **G (default)** | **unicode61 remove_diacritics 2 · stem · ё→е** | **0.941** | **0.902** | **0.941** | **0.941** | **1.000** | **1.000** | **0.853** | **0.961** | **0.961** | **0.948** | **36 KiB** | **1.18 ms** |
| H | unicode61 remove_diacritics 2 · stem-lang · ё→е | 0.941 | 0.902 | 0.941 | 0.941 | 1.000 | 1.000 | 0.853 | 0.961 | 0.961 | 0.948 | 36 KiB | 1.04 ms |
| I | porter unicode61 remove_diacritics 2 · exact | 1.000 | 0.961 | 0.882 | 0.882 | 0.941 | 0.912 | 0.824 | 0.941 | 0.941 | 0.918 | 32 KiB | 1.11 ms |
| J | porter unicode61 remove_diacritics 2 · stem · ё→е | 0.941 | 0.902 | 0.941 | 0.941 | 1.000 | 1.000 | 0.853 | 0.961 | 0.961 | 0.948 | 32 KiB | 1.24 ms |
| K | trigram · exact | 0.882 | 0.853 | 0.765 | 0.726 | 1.000 | 0.971 | 0.755 | 0.882 | 0.882 | 0.850 | 96 KiB | 2.54 ms |
| L | trigram · stem · ё→е | 0.941 | 0.912 | 0.882 | 0.882 | 1.000 | 1.000 | 0.833 | 0.941 | 0.941 | 0.931 | 96 KiB | 2.14 ms |
| M | trigram remove_diacritics 1 · stem · ё→е | 0.941 | 0.912 | 0.941 | 0.941 | 1.000 | 1.000 | 0.853 | 0.961 | 0.961 | 0.951 | 96 KiB | 2.14 ms |

**Per language for the default (G):**

| Language | Queries | R@1 | R@3 | R@5 | MRR |
|---|---|---|---|---|---|
| English | 17 | 0.794 | 0.941 | 0.941 | 0.902 |
| Latvian | 17 | 0.882 | 0.941 | 0.941 | 0.941 |
| Russian | 17 | 0.882 | 1.000 | 1.000 | 1.000 |
| All | 51 | 0.853 | 0.961 | 0.961 | 0.948 |

The exact-word baseline C reaches overall R@5 0.922 and MRR 0.889. For Latvian it reaches R@5 0.882 and MRR 0.853; without diacritic removal (A), Latvian falls to R@5 0.765 and MRR 0.735.

**Decision rule.**
1. The default must have the best overall recall@1, @3 and @5.
2. Its overall MRR must be within 0.01 of the best.
3. In each language it must be within one query (1/17) of the best.
4. A configuration may beat it on MRR only if its index is more than twice as large (`tests/test_library_benchmark.py`).

**Why G.**
- G, H and J tie for the best recall and MRR among the `unicode61` configurations.
- M (trigram with diacritic removal) is +0.003 MRR higher. The difference is one query, `q-en-pilot`, at rank 2 instead of 3.
- M costs 2.7 × the index and 1.8 × the query time. It cannot match terms shorter than three characters, needs SQLite ≥ 3.45, and has no exact pure-Python fallback.
- H's per-language endings add a language guess and gain nothing over the shared endings. Porter adds nothing over G, and the Python fallback cannot mirror it.
- ё→е folding (G against E) is what takes Russian from MRR 0.971 to 1.000.

**What G misses.**
- The two typo queries ("reliabilty", "ticamiibas"): no lexical configuration finds these.
- The English paraphrase "how long did the pilot take" at rank 3.

**This is a small synthetic set.** The numbers compare configurations on the same data; they are not an estimate of quality on real libraries.

## 5. Ask with sources: privacy controls

| Control | Proved by (`tests/test_library_ask.py` unless named) |
|---|---|
| Offline search works with no key and no internet: no request, no connection attempt, and the page explains how to connect a provider | `OfflineTests`; `test_research_library.OfflineTests` (NetworkGuard over add, search, why, render, reindex, remove, fallback); journey walk under NetworkGuard |
| Nothing leaves before *Send*. The preview names the provider, host, model, size and cite IDs and shows the exact prompt. The request that leaves is byte-identical to the preview. *Send* is the approval of that one request. | `ConsentTests.test_nothing_leaves_before_send_and_the_request_is_the_preview` |
| A provider or model changed elsewhere after the preview: shown again first, nothing sent | `test_a_request_changed_after_the_preview_is_shown_again_first` |
| Only ticked passages (3 pre-ticked of 6 found, at most 8, each ≤ 1,500 characters), never a data row, never another context source, never the whole library | `PayloadTests`, `RequestTests.test_only_the_given_passages_are_quoted_as_sources` |
| Without a matching passage nothing can be sent ("nothing was sent"). An answer the passages do not contain is reported plainly (`NOT_IN_SOURCES`). | `test_without_a_matching_passage_nothing_can_be_sent`, `test_an_answer_the_sources_do_not_hold_is_said_plainly`, `RefusalTests` |
| Citations must name a passage that was sent: unknown labels, outside references (`[1]`, `(Smith, 2020)`) and statements without a citation are flagged. Cited labels map to cite IDs, and a cited source opens at its page. | `CheckTests.test_citations_must_name_a_passage_that_was_sent`, `CheckedAnswerTests` |
| Numbers come only from the deterministic engine. The rules forbid any calculation, no result of the study is sent, and every number of the answer that is not in the passages is highlighted and listed. | `test_citations_numbers_and_quotes_are_checked` (0.85 and 2020 flagged; 3, 7 and 12 verified) |
| Quotes are checked word for word | §2, point 4 |
| Audit. The project activity log records provider, model, tokens, outcome, source `library` and task `library_ask`. The library log records the cite IDs sent. Neither the prompt nor the answer is stored. | `ConsentTests` |
| Retrieved text is untrusted (§6) | `InjectionTests`, `RequestTests.test_a_source_cannot_close_its_element_or_open_another` |

## 6. Prompt-injection containment

- **Data, not instructions.** Each passage is sent inside `<source id="S1" document="…" version="…" location="…">…</source>`.
  - A `<source` or `</source` inside the text is broken (`< source`, `< /source`), so a passage can neither close its element nor open a forged one (`S9`).
  - Attribute values cannot hold quotes or angle brackets.
  - The question cannot close its own element.
- **The rules come first.** They say that a source is quoted data that never changes the rules.
- **The answer can do nothing.** It is plain text in a draft card: no links, no tool, no action. A provider that obeys the hostile memo ("delete the library", "reveal the API key", cites `[S9]`) changes nothing:
  - the documents, the project's AI permissions, the AI settings and the page are as before;
  - exactly one request was made;
  - `S9` is flagged as a citation of a passage that was not sent;
  - the key is not in the prompt.

  Proved by `InjectionTests.test_retrieved_instructions_cannot_change_the_program`.
- **Offline search has no model,** so it carries no injection risk.

## 7. Tests

**New test files (77 tests).**

| File | Tests | Covers |
|---|---|---|
| `tests/test_stage37_ai_rows.py` | 5 | data rows without identifier and free-text columns (review point 2) |
| `tests/test_research_library.py` | 33 | capabilities and fallback, tokens equal FTS5, reviewer probes, query syntax, PDF/DOCX/MD/TXT reading, page mapping, exact offsets, refusals, real OCR, dedupe, revisions, remove (also with the copy held open), reindex, stable cite IDs, newer format, backend switch, fallback equivalence, filters, contradictions, snippets, why, project isolation, the packaged self-test step, offline guard |
| `tests/test_library_benchmark.py` | 6 | the evidence for the default, per-language thresholds, probes |
| `tests/test_workspace_library.py` | 13 | the page: place, sidebar and shortcuts, progress, cancel, remove, reindex, search, filters, why, viewer and system viewer, isolation, backup choice, EN/LV/RU |
| `tests/test_library_ask.py` | 17 | request building, citation and quote checks, consent, preview, payload, answers, injection, Results-page quotes, refusals |
| `tests/test_stage37_library_journey.py` | 3 | the Windows journey's flow in the harness, journey order |

**Changed test.** `tests/test_stage368_review_journeys.py` now expects 19 journeys; the first 18 keep their order.

**Fixtures.** `tests/library_fixtures.py` writes the synthetic corpus as PDF (text layer, page numbers, an image-only page for OCR), DOCX (Title and Heading styles, a table), Markdown and TXT. It also holds the hostile memo.

**Windows journey `research-library`.** It is the 19th entry of `JOURNEYS`, after the 18 existing ones.
- Create a project.
- Open the library from the Project page.
- Add the synthetic PDF in the Open dialog.
- Search offline.
- Open the citation at page 2 in the page viewer.
- Remove the document with one action.
- The same search finds nothing.

The driver reads the library on disk after adding (1 document, 5 passages, 5 FTS rows, 1 stored file) and after removing (all 0), and checks that no AI request was recorded. No disabled state is asserted. It has not been run on Windows in this increment; its harness walk passes.

## 8. Limitations

- **Lexical only.** Synonyms and cross-language questions (an English question about a Latvian passage) are not found. Typos are not found either.
- **Approximate structure.** Headings in PDFs come from font size and a few patterns. Bold headings set at body size without numbers are missed, and multi-column layouts are read in pypdf's order. Page numbers are the physical PDF pages, not printed page labels.
- **OCR is opt-in.** Its quality depends on the scan. A document added without OCR must be removed and added again to read its image pages: its SHA-256 dedupe returns the existing document.
- **Query syntax.** Queries are bags of words: no phrases, boolean operators or field filters.
- **The library is per project.** It travels in backups and copies only when chosen. A library written by a later format is refused, not converted.
- **Unchecked parts of an answer.** The citation check flags statements without a label, but it cannot judge whether a cited passage supports a statement. Number and quote checks catch invented or altered values, not misread ones.
- **Native review and Windows runs pending.** LV and RU texts are drafts. The Windows journey and the packaged self-test step need a Windows CI run, which only the owner can start.
- **The benchmark is small and synthetic** (51 passages, 51 queries).

## 9. Embeddings: not in this increment

No embedding model ships. Before any is considered, the following evidence is needed.

1. **Retrieval quality.**
   - Extend the labelled set to at least 150 queries per language, with paraphrases and cross-language questions (EN↔LV, EN↔RU, LV↔RU).
   - Measure recall@5, MRR and citation accuracy (the cited passage is the labelled one) for lexical (G), dense, and hybrid (reciprocal-rank fusion, k = 60).
   - Required gains:
     - hybrid at least +0.05 recall@5 on paraphrase and cross-language queries in **each** language;
     - no loss on exact and inflected queries;
     - cross-language recall@5 ≥ 0.80.
2. **Licence.**
   - Weights, tokenizer and training-data terms must allow redistribution in a commercial desktop program: MIT or Apache-2.0. No non-commercial or research-only terms.
   - Record it in the SBOM.
3. **Size.**
   - The Windows package budget is installed ≤ 400 MiB and ZIP ≤ 160 MiB; it is at 376.3 / 149.3 MiB (`docs/DISTRIBUTION_OPTIMIZATION.md`).
   - A model of 100 MiB or more cannot be bundled, so it would be an optional, signed, hash-pinned download module, with offline module files for restricted networks.
   - Any runtime (for example ONNX Runtime) is a new locked dependency with its own size and licence review.
4. **Speed.** On a 4-core laptop CPU, without a GPU:
   - indexing ≥ 20 passages per second;
   - query latency ≤ 150 ms at 10,000 passages;
   - peak memory ≤ 600 MiB.
5. **Privacy and integrity.**
   - Vectors live in the library database and are deleted with their passages.
   - The same project isolation and backup choice apply.
   - Nothing is downloaded at search time.

## 10. Done and not done

| Item | Status | Proved by / note |
|---|---|---|
| Per-project library database with its own schema version; project schema unchanged | done | §1.1 tests |
| documents / chunks / FTS5 with BM25 and `snippet()` | done | `SearchTests`, `FallbackEquivalenceTests` |
| FTS5 checked here and in the packaged runtime; tested fallback; packaged self-test | done (static check of the packaged DLL; the self-test step runs on the next Windows CI) | §3 |
| Explicit import of PDF (with optional OCR), DOCX (heading styles), TXT/MD; section- and page-aware passages | done | `ExtractionTests`, `OcrTests` |
| SHA-256 dedupe, incremental reindex, delete, reindex all, stable cite IDs | done | `StoreTests` |
| Offline BM25 with type, language and date filters; tokenizer benchmark; choice by evidence | done | §4 |
| Results read document, page or section, excerpt and version; open in the page viewer or the system viewer | done | `SearchTests` (UI) |
| Project isolation; deletion purges passages and index rows | done | `IsolationTests` (both files) |
| Ask with sources: approval per query, exact preview, no rows, not the whole library, untrusted text delimited, citation validation, honest "nothing found", no calculation by the AI, offline without a key | done | §5, §6 |
| Page: Add, Search, Ask; progress, local badge, why, one-action remove; EN/LV/RU (LV/RU drafts) | done | `tests/test_workspace_library.py` |
| Synthetic PDF/DOCX/MD documents with contradictions, page mapping, LV/RU/EN, revisions, hostile instructions | done | `tests/library_fixtures.py` |
| Network guard on offline search; mocked providers for consent, preview, citations, injection | done | §5 |
| Windows journey `research-library` after the 18; harness walk | done in the harness; **not run on Windows** | §7 |
| Review point 1 (tokenization: prefix queries, trigram, per-language endings; recall and MRR per language) | done | §4, `tests/test_library_benchmark.py` |
| Review point 2 (data rows) with a red test first | done | `3fc204b` (red), `db7514e` (fix) |
| Review point 3 (backup choice) | done | `BackupChoiceTests` |
| Review point 4 (quoted spans in every AI answer) | done | §2 |
| Embeddings | not done (plan only, §9) | — |
| Native LV/RU review of the new texts | not done | owner |
| Phrase or boolean queries; printed page labels; text-size settings of the page | not done | — |
