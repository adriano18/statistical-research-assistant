"""The research library of a project (Stage 37.3, Issue #69): reading,
passages, citations, search, the FTS5 fallback, isolation and offline use.

Synthetic documents only (``tests/library_fixtures.py``). The real local
Tesseract reads the image page where it is installed (CI's pruned-runtime job
requires it). No test opens a network connection (``OfflineTests`` guards it).
"""

from __future__ import annotations

from contextlib import closing
from io import BytesIO
import os
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("MPLBACKEND", "Agg")

import library_fixtures as fx  # noqa: E402
import research_library as rl  # noqa: E402

REQUIRE_OCR = os.environ.get("SRA_REQUIRE_REAL_OCR") == "1"


def ocr_with(*languages: str) -> bool:
    available, installed = rl.ocr_available()
    return available and set(languages) <= set(installed)


class LibraryCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.sources = self.base / "sources"

    def library(self, name: str = "library", **options) -> rl.Library:
        return rl.Library(self.base / name, **options)

    def add(self, library, document, kind, **options):
        return library.add_document(fx.write(document, self.sources, kind, **options),
                                    version_label=document.version)

    @staticmethod
    def cites(result) -> list[str]:
        return [hit.cite_id for hit in result.hits]


# ================================================================ SQLite
class CapabilityTests(LibraryCase):
    def test_fts5_with_its_tokenizers_is_compiled_into_this_python(self):
        caps = rl.capabilities()
        self.assertTrue(caps.fts5, f"SQLite {caps.sqlite} without FTS5")
        self.assertTrue(caps.trigram)
        self.assertTrue(caps.tokenizer_works(rl.DEFAULT_TOKENIZER))
        self.assertEqual(self.library().backend, "fts5")

    def test_without_fts5_the_python_index_is_used(self):
        missing = rl.Capabilities("3.0.0", False, False, False)
        with mock.patch.object(rl, "capabilities", return_value=missing), \
                mock.patch.object(rl.Capabilities, "tokenizer_works", return_value=False):
            library = self.library()
        self.assertEqual(library.backend, "python")
        self.add(library, fx.EN_MANUAL_V1, "md")
        self.assertEqual(self.cites(library.search("withdraw consent"))[:1],
                         [fx.relevance_map(library)["en-consent"]])
        with self.assertRaises(rl.LibraryError) as refused:
            rl.Library(self.base / "other", tokenizer="trigram", backend="python")
        self.assertEqual(refused.exception.reason, "tokenizer_unavailable")


# ============================================================ tokenizing
class TokenizerTests(LibraryCase):
    EDGE = ("Vientulība ŠŪPOLES ģimenes Ёлка йод ЩУКА naïve 3.14 x_y café-bar co-op "
            "“quoted” – dash … ½ ² e-mail SYN-2026-04 O’Brien")

    def test_python_tokens_are_the_tokens_of_fts5_unicode61(self):
        texts = [p.text for _, p in fx.PASSAGES.values()] + [self.EDGE, fx.HOSTILE.passages[0].text]
        for option in (0, 1, 2):
            with self.subTest(remove_diacritics=option), closing(sqlite3.connect(":memory:")) as db:
                db.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize="
                           f"'unicode61 remove_diacritics {option}')")
                db.execute("CREATE VIRTUAL TABLE v USING fts5vocab(t, 'instance')")
                for rowid, text in enumerate(texts, start=1):
                    db.execute("INSERT INTO t (rowid, a) VALUES (?, ?)", (rowid, text))
                for rowid, text in enumerate(texts, start=1):
                    fts = [r[0] for r in db.execute(
                        "SELECT term FROM v WHERE doc = ? ORDER BY offset", (rowid,))]
                    self.assertEqual(rl.tokens(text, option), fts, text[:40])

    def test_the_reviewers_probes_find_the_inflected_words(self):
        """unicode61 folds diacritics but does not stem (independent review §7):
        «одиночества» ≠ «одиночество», "lonely" ≠ "loneliness". The stemmed
        prefix query finds them; the exact query does not."""
        library = self.library()
        self.add(library, fx.EN_REVIEW, "md")
        self.add(library, fx.RU_REVIEW, "md")
        self.add(library, fx.LV_REVIEW, "md")
        ids = fx.relevance_map(library)
        exact = rl.Library(self.base / "exact", query_mode="exact")
        self.add(exact, fx.EN_REVIEW, "md")
        self.add(exact, fx.RU_REVIEW, "md")
        self.assertEqual(rl.stem("одиночества"), "одиночеств")
        self.assertEqual(rl.stem("lonely"), "lone")
        self.assertEqual(rl.stem("vientulības"), "vientulīb")
        for probe, passage in (("одиночества", "ru-obzor-vvedenie"), ("lonely", "en-review-intro"),
                               ("vientulības", "lv-parskats-ievads")):
            with self.subTest(probe=probe):
                found = self.cites(library.search(probe, limit=20))
                self.assertIn(ids[passage], found)
        intro = fx.relevance_map(exact)["en-review-intro"]
        self.assertNotIn(intro, self.cites(exact.search("lonely", limit=20)))
        vvedenie = fx.relevance_map(exact)["ru-obzor-vvedenie"]
        self.assertNotIn(vvedenie, self.cites(exact.search("одиночества", limit=20)))

    def test_query_syntax_is_never_passed_to_fts5(self):
        library = self.library()
        self.add(library, fx.EN_MANUAL_V1, "md")
        for query in ('"', '""', "*", "consent*", 'NEAR(consent form)', "consent NOT form",
                      "-consent", "text:consent", "^consent", "consent OR", "(consent",
                      "'; DROP TABLE chunks; --", "\x00consent", "c" * 2000):
            with self.subTest(query=query[:30]):
                result = library.search(query)
                self.assertIsInstance(result.total, int)
        self.assertTrue(library.search('consent" OR "x').hits)
        self.assertEqual(library.counts()[0], 1, "nothing was dropped")

    def test_function_words_alone_find_nothing(self):
        library = self.library()
        self.add(library, fx.EN_MANUAL_V1, "md")
        result = library.search("the and of how un ir и в")
        self.assertEqual((result.terms, result.hits, result.total), ((), (), 0))


# ============================================================ extraction
class ExtractionTests(LibraryCase):
    def test_pdf_pages_sections_title_and_exact_offsets(self):
        library = self.library()
        outcome = self.add(library, fx.EN_REVIEW, "pdf")
        document = outcome.document
        self.assertEqual((document.title, document.type, document.page_count, document.language),
                         (fx.EN_REVIEW.title, "pdf", 3, "en"))
        passages = library.passages(document.id)
        by_section = {p.section: p for p in passages}
        for passage in fx.EN_REVIEW.passages:
            stored = by_section[passage.section]
            self.assertEqual(stored.page, passage.page, passage.key)
            self.assertIn(passage.text[:60], " ".join(stored.text.split()))
            self.assertRegex(stored.cite_id, rf"^{document.key}-p{passage.page}\.\d$")
        segments = library.segments(document.id)
        self.assertEqual([s.page for s in segments], [1, 2, 3])
        for stored in passages:
            self.assertEqual(segments[stored.segment].text[stored.start:stored.end], stored.text)
            self.assertNotRegex(stored.text, r"(?m)^\d$", "page numbers are left out")
        self.assertEqual(len({p.cite_id for p in passages}), len(passages))

    def test_docx_heading_styles_are_sections_and_tables_are_read(self):
        library = self.library()
        document = self.add(library, fx.LV_MANUAL_V1, "docx", table=True).document
        self.assertEqual((document.title, document.language, document.page_count),
                         (fx.LV_MANUAL_V1.title, "lv", 0))
        sections = [p.section for p in library.passages(document.id)]
        self.assertEqual(sections, [p.section for p in fx.LV_MANUAL_V1.passages] + ["Schedule"])
        hit = library.search("Room 214 pilot interview").hits[0]
        self.assertEqual(hit.passage.section, "Schedule")
        self.assertIn("Pilot interview | Room 214", hit.passage.text)
        self.assertRegex(hit.cite_id, rf"^{document.key}-s\d+\.1$")

    def test_markdown_and_text_headings(self):
        library = self.library()
        notes = self.add(library, fx.EN_NOTES, "txt").document
        self.assertEqual(notes.title, "Lab notes")
        self.assertEqual([p.section for p in library.passages(notes.id)],
                         ["1. Pilot session", "2. Printing", "3. Rooms"])
        setext = self.sources / "setext.md"
        setext.write_text("Setext title\n============\n\nIntro text about the synthetic setup.\n\n"
                          "Second part\n-----------\n\nMore synthetic text.\n\n```\n"
                          "# not a heading\n"
                          "```\n", encoding="utf-8")
        document = library.add_document(setext).document
        self.assertEqual(document.title, "Setext title")
        self.assertEqual([p.section for p in library.passages(document.id)],
                         ["", "Second part"])
        self.assertIn("# not a heading", library.passages(document.id)[-1].text)

    def test_long_sections_are_cut_at_sentences_and_never_cross_pages(self):
        sentences = [f"Synthetic sentence number {n} describes an invented step of the protocol "
                     f"in plain words." for n in range(1, 90)]
        long_md = self.sources / "long.md"
        self.sources.mkdir(parents=True, exist_ok=True)
        long_md.write_text("# Long synthetic protocol\n\n## Procedure\n\n" + " ".join(sentences),
                           encoding="utf-8")
        library = self.library()
        document = library.add_document(long_md).document
        passages = library.passages(document.id)
        self.assertGreater(len(passages), 4)
        for passage in passages:
            self.assertLessEqual(len(passage.text), rl.MAX_PASSAGE_CHARS)
            self.assertTrue(passage.text.rstrip().endswith("."), passage.text[-30:])
            self.assertEqual(passage.section, "Procedure")
        self.assertEqual([p.cite_id.split("-")[-1] for p in passages],
                         [f"s2.{n}" for n in range(1, len(passages) + 1)],
                         "section 2: the title heading is section 1")
        pdf_passages = library.passages(self.add(library, fx.RU_REVIEW, "pdf").document.id)
        for passage in pdf_passages:
            self.assertIsNotNone(passage.page)
        self.assertEqual(sorted({p.page for p in pdf_passages}), [1, 2, 3])

    def test_language_of_each_document(self):
        library = self.library()
        for document, kind in ((fx.EN_NOTES, "txt"), (fx.LV_NOTES, "txt"), (fx.RU_NOTES, "txt"),
                               (fx.LV_REVIEW, "pdf")):
            with self.subTest(document=document.key):
                self.assertEqual(self.add(library, document, kind).document.language,
                                 document.language)

    def test_unusable_files_are_refused_and_nothing_is_stored(self):
        from pypdf import PdfReader, PdfWriter

        library = self.library()
        self.sources.mkdir(parents=True, exist_ok=True)
        encrypted = BytesIO()
        writer = PdfWriter(clone_from=PdfReader(BytesIO(fx.pdf(fx.EN_NOTES))))
        writer.encrypt("synthetic-secret")
        writer.write(encrypted)
        cases = {
            "unsupported": ("notes.rtf", b"{\\rtf1 synthetic}"),
            "empty": ("empty.txt", b""),
            "encrypted": ("locked.pdf", encrypted.getvalue()),
            "unreadable": ("damaged.pdf", b"%PDF-1.4\n% fictional damaged file"),
            "no_text": ("blank.md", b"\n\n   \n"),
        }
        for reason, (name, data) in cases.items():
            with self.subTest(reason=reason):
                path = self.sources / name
                path.write_bytes(data)
                with self.assertRaises(rl.LibraryError) as refused:
                    library.add_document(path)
                self.assertEqual(refused.exception.reason, reason)
        with mock.patch.object(rl, "MAX_BYTES", 10):
            with self.assertRaises(rl.LibraryError) as refused:
                library.add_document(data=b"x" * 11, file_name="big.txt")
        self.assertEqual(refused.exception.reason, "too_large")
        self.assertEqual(library.counts(), (0, 0))
        self.assertEqual(list((library.folder / rl.SOURCES).iterdir()), [])


@unittest.skipUnless(ocr_with("eng") or REQUIRE_OCR, "local OCR is not installed")
class OcrTests(LibraryCase):
    """An image-only page (a scan, no text layer) read with the local engine."""

    def test_an_image_page_is_read_with_local_ocr_when_asked(self):
        library = self.library()
        path = fx.write(fx.EN_NOTES, self.sources, "pdf", image_page=fx.SCAN_LINES)
        without = library.add_document(path)
        self.assertIn(("ocr_off", {"pages": [2]}), without.notes)
        self.assertFalse(library.search("transcription recordings erased").hits)
        library.remove_document(without.document.id)
        progress = []
        outcome = library.add_document(path, ocr=True, ocr_language="eng",
                                       progress=lambda *step: progress.append(step))
        self.assertEqual(outcome.document.ocr_pages, (2,))
        self.assertIn(("ocr_read", {"pages": [2]}), outcome.notes)
        self.assertIn(("ocr", 1, 1), progress)
        hit = library.search("recordings erased after transcription").hits[0]
        self.assertEqual(hit.passage.page, 2)
        self.assertRegex(hit.cite_id, r"-p2\.1$")

    def test_reindexing_keeps_the_recognised_text_without_reading_again(self):
        library = self.library()
        path = fx.write(fx.EN_NOTES, self.sources, "pdf", image_page=fx.SCAN_LINES)
        document = library.add_document(path, ocr=True, ocr_language="eng").document
        before = [(p.cite_id, p.text) for p in library.passages(document.id)]
        with mock.patch.object(rl, "ocr_page", side_effect=AssertionError("read again")):
            again = library.reindex(document.id)
        self.assertEqual(again.ocr_pages, (2,))
        self.assertEqual([(p.cite_id, p.text) for p in library.passages(document.id)], before)


class OcrUnavailableTests(LibraryCase):
    def test_without_an_engine_the_page_is_named_and_the_rest_is_kept(self):
        library = self.library()
        path = fx.write(fx.EN_NOTES, self.sources, "pdf", image_page=fx.SCAN_LINES)
        with mock.patch.object(rl, "ocr_available", return_value=(False, ())):
            outcome = library.add_document(path, ocr=True)
        self.assertIn(("ocr_unavailable", {"pages": [2]}), outcome.notes)
        self.assertEqual(outcome.document.ocr_pages, ())
        self.assertTrue(library.search("double-sided printing").hits)


# ================================================================= store
class StoreTests(LibraryCase):
    def test_the_same_bytes_are_never_added_twice(self):
        library = self.library()
        path = fx.write(fx.EN_MANUAL_V1, self.sources, "md")
        first = library.add_document(path)
        copy = self.sources / "renamed_copy.md"
        copy.write_bytes(path.read_bytes())
        second = library.add_document(copy)
        self.assertTrue(second.duplicate)
        self.assertFalse(first.duplicate)
        self.assertEqual(second.document.id, first.document.id)
        self.assertEqual(library.counts(), (1, first.passages))
        self.assertEqual(len(list((library.folder / rl.SOURCES).iterdir())), 1)

    def test_a_revision_of_the_same_file_gets_a_version_label(self):
        library = self.library()
        folder = self.sources / "v"
        first = library.add_document(fx.write(fx.EN_MANUAL_V1, folder, "md").rename(
            folder / "manual.md"))
        changed = folder / "next" / "manual.md"
        changed.parent.mkdir()
        changed.write_text(fx.markdown(fx.EN_MANUAL_V2), encoding="utf-8")
        second = library.add_document(changed)
        self.assertEqual(second.document.version_label, "v2")
        self.assertIn(("versioned", {"label": "v2", "earlier": 1}), second.notes)
        self.assertEqual(library.document(first.document.id).version_label, "v1")
        labelled = library.add_document(data=b"# Synthetic manual\n\n## Note\n\nThird text.",
                                        file_name="manual.md", version_label="2026 draft")
        self.assertEqual(labelled.document.version_label, "2026 draft")

    def test_removing_a_document_removes_its_passages_index_rows_and_copy(self):
        library = self.library()
        keep = self.add(library, fx.EN_REVIEW, "pdf").document
        gone = self.add(library, fx.EN_MANUAL_V1, "md").document
        self.assertGreater(library.index_rows(gone.id), 0)
        copy = library.source_file(gone)
        self.assertTrue(copy.is_file())
        self.assertTrue(library.search("informed consent withdrawn").hits)
        removed = library.remove_document(gone.id)
        self.assertEqual(removed.id, gone.id)
        self.assertEqual(library.passages(gone.id), [])
        self.assertEqual(library.segments(gone.id), [])
        self.assertEqual(library.index_rows(gone.id), 0)
        self.assertFalse(copy.exists())
        self.assertFalse([h for h in library.search("informed consent withdrawn").hits
                          if h.document.id == gone.id])
        self.assertEqual(library.integrity(), [])
        self.assertEqual([d.id for d in library.documents()], [keep.id])
        self.assertEqual(library.index_rows(), len(library.passages(keep.id)))
        with closing(sqlite3.connect(library.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM chunks WHERE document_id = ?",
                                        (gone.id,)).fetchone()[0], 0)

    def test_reindexing_keeps_cite_ids_and_finds_outdated_documents(self):
        library = self.library()
        documents = [self.add(library, d, k).document for d, k in
                     ((fx.EN_REVIEW, "pdf"), (fx.LV_MANUAL_V1, "docx"), (fx.RU_NOTES, "txt"))]
        before = {d.id: [p.cite_id for p in library.passages(d.id)] for d in documents}
        self.assertEqual(library.outdated(), [])
        with mock.patch.object(rl, "CHUNKER", "passages-next"):
            self.assertEqual({d.id for d in library.outdated()}, {d.id for d in documents})
            self.assertEqual(library.reindex_all(only_outdated=True), 3)
            self.assertEqual(library.outdated(), [])
        self.assertEqual({d.id: [p.cite_id for p in library.passages(d.id)] for d in documents},
                         before)
        self.assertEqual(library.reindex_all(), 3)
        self.assertEqual(library.integrity(), [])
        self.assertEqual(self.cites(library.search("Пилотная сессия"))[:1],
                         [fx.relevance_map(library)["ru-zametki-pilot"]])

    def test_cite_ids_are_the_same_in_every_library(self):
        path = fx.write(fx.RU_REVIEW, self.sources, "pdf")
        first, second = self.library("one"), self.library("two", backend="python")
        self.add(first, fx.EN_NOTES, "txt")
        a = first.add_document(path).document
        b = second.add_document(path).document
        self.assertEqual(a.key, "D" + a.sha256[:8].upper())
        self.assertEqual([p.cite_id for p in first.passages(a.id)],
                         [p.cite_id for p in second.passages(b.id)])

    def test_a_library_of_a_newer_version_is_refused_without_writing(self):
        library = self.library()
        self.add(library, fx.EN_NOTES, "txt")
        with closing(sqlite3.connect(library.path)) as db:
            db.execute(f"PRAGMA user_version = {rl.SCHEMA_VERSION + 1}")
            db.commit()
        before = library.path.read_bytes()
        with self.assertRaises(rl.LibraryError) as refused:
            rl.Library(library.folder)
        self.assertEqual(refused.exception.reason, "newer_format")
        self.assertEqual(library.path.read_bytes(), before)
        self.assertEqual(rl.peek(self.base.parent / "nowhere"), (0, 0))

    def test_switching_the_backend_rebuilds_the_index(self):
        library = self.library()
        self.add(library, fx.LV_REVIEW, "pdf")
        expected = self.cites(library.search("sociālais atbalsts kā buferis"))
        fallback = rl.Library(library.folder, backend="python")
        self.assertEqual(self.cites(fallback.search("sociālais atbalsts kā buferis")), expected)
        self.assertEqual(fallback.integrity(), [])
        self.add(fallback, fx.LV_NOTES, "txt")       # written without FTS5
        again = rl.Library(library.folder)            # FTS5 back: rebuilt from the passages
        self.assertEqual(again.backend, "fts5")
        self.assertEqual(again.integrity(), [])
        self.assertTrue(again.search("pilotsesija otrdien").hits)


class FallbackEquivalenceTests(LibraryCase):
    """The pure-Python BM25 gives FTS5's order and scores on every benchmark query."""

    def test_python_bm25_ranks_like_fts5(self):
        fts5 = self.library("fts5")
        python = self.library("python", backend="python")
        for document in fx.CORPUS:
            path = fx.write(document, self.sources, "md")
            fts5.add_document(path)
            python.add_document(path)
        for query in fx.QUERIES:
            with self.subTest(query=query.key):
                a, b = fts5.search(query.text, limit=10), python.search(query.text, limit=10)
                self.assertEqual(self.cites(a), self.cites(b))
                self.assertEqual(a.total, b.total)
                for x, y in zip(a.hits, b.hits):
                    self.assertAlmostEqual(x.score, y.score, places=9)
                    self.assertIn(rl.MARK_OPEN, y.snippet)


# ================================================================ search
class SearchTests(LibraryCase):
    def setUp(self):
        super().setUp()
        self.lib = self.library()
        for document in fx.CORPUS:
            self.add(self.lib, document, fx.KINDS[document.key])
        self.ids = fx.relevance_map(self.lib)

    def test_a_hit_reads_document_page_or_section_excerpt_and_version(self):
        hit = self.lib.search("avoidant coping mediator").hits[0]
        self.assertEqual(hit.cite_id, self.ids["en-review-coping"])
        self.assertEqual((hit.document.title, hit.passage.page, hit.passage.section),
                         (fx.EN_REVIEW.title, 2, "Coping as a mediator"))
        parts = rl.snippet_parts(hit.snippet)
        self.assertIn(("Avoidant", True), parts)
        self.assertIn(("mediator", True), parts)
        revision = self.lib.search("statements no longer reverse-scored").hits[0]
        self.assertEqual((revision.document.version_label, revision.cite_id),
                         ("v2", self.ids["en-scoring-v2"]))

    def test_contradicting_revisions_are_both_found_with_their_versions(self):
        result = self.lib.search("statements 3 7 12 reverse-scored", limit=5)
        found = {hit.cite_id: hit.document.version_label for hit in result.hits}
        self.assertEqual(found[self.ids["en-scoring"]], "v1")
        self.assertEqual(found[self.ids["en-scoring-v2"]], "v2")

    def test_filters_type_language_and_date(self):
        query = "pilot session"
        self.assertEqual({h.document.type for h in self.lib.search(query, types=("txt",)).hits},
                         {"txt"})
        self.assertEqual({h.document.language for h in self.lib.search(
            "2026 04", language="lv").hits}, {"lv"})
        self.assertEqual(len(self.lib.search("2026 04").hits), 3)
        self.assertEqual(self.lib.search("2026 04", since="2999-01-01").hits, ())
        self.assertEqual(len(self.lib.search("2026 04", until="2999-01-01").hits), 3)
        self.assertEqual(self.lib.search("2026 04", types=("docx",)).filters,
                         {"types": ("docx",)})

    def test_snippets_keep_the_documents_own_letters(self):
        hit = self.lib.search("подсчет баллов").hits[0]
        self.assertIn(("Подсчёт", True), rl.snippet_parts(hit.snippet))
        self.assertIn(hit.cite_id, (self.ids["ru-podschet"], self.ids["ru-podschet-v2"]))

    def test_why_this_source(self):
        result = self.lib.search("social support buffers loneliness")
        hit = result.hits[0]
        why = self.lib.explain(hit, result)
        self.assertEqual((why.rank, why.backend), (1, "fts5"))
        self.assertEqual(why.total, result.total)
        self.assertIn(("support…", 3), why.matched)
        self.assertIn(("buffer…", 2), why.matched)     # the heading and the text
        self.assertEqual(why.missing, ())
        self.assertGreater(why.score, 0)


# ============================================================= isolation
class IsolationTests(unittest.TestCase):
    def test_each_project_has_its_own_library(self):
        from project_store import ProjectStore

        with TemporaryDirectory() as folder:
            base = Path(folder)
            store = ProjectStore(base / "projects")
            first, second = store.create("Study A"), store.create("Study B")
            with store.open(first.id) as a, store.open(second.id) as b:
                library_a = rl.Library.for_project(a.path)
                library_b = rl.Library.for_project(b.path)
                library_a.add_document(fx.write(fx.EN_REVIEW, base / "in", "md"))
                library_b.add_document(fx.write(fx.LV_NOTES, base / "in", "txt"))
                self.assertTrue(library_a.search("avoidant coping").hits)
                self.assertEqual(library_b.search("avoidant coping").hits, ())
                self.assertEqual(library_a.search("pilotsesija").hits, ())
                self.assertEqual(rl.peek(a.path), (1, 5))
                self.assertEqual(rl.peek(b.path)[0], 1)
                self.assertTrue(library_a.path.is_relative_to(a.path))
                project_db = a.path / "project.sqlite3"
                with closing(sqlite3.connect(project_db)) as db:
                    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master")}
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
                self.assertFalse(any("chunk" in t or "document" in t for t in tables),
                                 "the project database is not touched")
            trashed = store.delete(first.id)
            self.assertTrue((trashed / rl.FOLDER / rl.DB_NAME).is_file(),
                            "a deleted project takes its library to the trash")


# =============================================================== offline
class OfflineTests(LibraryCase):
    def test_nothing_opens_a_network_connection(self):
        from test_stage368_ai_gate import NetworkGuard

        guard = NetworkGuard()
        guard.install(self)
        library = self.library()
        documents = [self.add(library, d, k).document for d, k in
                     ((fx.EN_REVIEW, "pdf"), (fx.LV_MANUAL_V1, "docx"), (fx.RU_MANUAL_V1, "md"),
                      (fx.EN_NOTES, "txt"))]
        result = library.search("social support buffer")
        library.explain(result.hits[0], result)
        self.assertTrue(library.render_page(documents[0], 2).startswith(b"\x89PNG"))
        library.reindex(documents[1].id)
        library.remove_document(documents[2].id)
        rl.Library(library.folder, backend="python").search("vientulība")
        self.assertEqual(guard.attempts, [])


if __name__ == "__main__":
    unittest.main()
