"""The Research Library page (Stage 37.3, Issue #69), through the workspace
harness: reached from the Project page with the sidebar unchanged, adding
with progress, offline search with filters, "why this source?", opening a
citation, one-action remove, project isolation, the backup and copy choice,
and EN/LV/RU. Synthetic documents only; no network.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402

import library_fixtures as fx  # noqa: E402
import research_library as rl  # noqa: E402
from workspace_harness import Workspace  # noqa: E402
from workspace_text import T as TABLE  # noqa: E402


def T(key: str, **values) -> str:
    text = TABLE[key][0]
    return text.format(**values) if values else text


def texts(ws, data: str) -> str:
    found = []
    for control in ws.controls(ws.find(data)):
        if isinstance(control, ft.Text):
            found.append(control.value or control.semantics_label
                         or "".join(s.text or "" for s in control.spans or []))
    return " ".join(found)


def picked(*paths: Path) -> list:
    return [SimpleNamespace(name=path.name, path=str(path)) for path in paths]


class LibraryUiCase(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)
        self.files = self.ws.root / "documents"

    def project(self, title: str = "Fictional library study"):
        ws = self.ws
        ws.click("nav-home")
        ws.type("project-new-title", title)
        ws.click("project-create")
        return ws.app.projects.project

    def open_library(self):
        self.ws.app.navigate("project")
        self.ws.click("project-library-open")
        return self.ws.app.pages["library"]

    def add(self, *documents_kinds):
        page = self.ws.app.pages["library"]
        paths = [fx.write(document, self.files, kind) for document, kind in documents_kinds]
        return self.ws.run(page.add_files(picked(*paths)))

    def search(self, query: str):
        self.ws.type("library-query", query)
        self.ws.click("library-search-run")


class PlaceTests(LibraryUiCase):
    def test_reached_from_the_project_page_with_the_sidebar_and_shortcuts_unchanged(self):
        ws = self.ws
        self.project()
        ws.app.navigate("project")
        card = texts(ws, "project-library")
        self.assertIn(T("library.title"), card)
        self.assertIn(T("library.card_empty"), card)
        self.assertIn(T("library.card_backup_off"), card)
        self.assertEqual(ws.find("project-library-open").content, T("library.open_library"))
        ws.click("project-library-open")
        self.assertEqual((ws.app.route, ws.app.area), ("library", "project"))
        self.assertEqual([c.data for c in ws.find_all("nav-") if c.data != "nav-toggle"],
                         ["nav-home", "nav-project", "nav-data", "nav-questionnaires",
                          "nav-analyze", "nav-results", "nav-reports", "nav-settings",
                          "nav-help"])
        self.assertIn(T("library.local"), texts(ws, "library-local"))
        for number, area in enumerate(("home", "data", "questionnaires", "analyze", "results",
                                       "reports"), start=1):
            ws.app.navigate("library")
            ws.key(str(number), ctrl=True)
            self.assertEqual(ws.app.route, area, f"Ctrl+{number}")
        ws.app.navigate("library")
        ws.click("library-back")
        self.assertEqual(ws.app.route, "project")

    def test_without_a_project_the_library_leads_home(self):
        self.ws.app.navigate("library")
        self.assertEqual(self.ws.app.route, "home")
        page = self.ws.app.pages["library"]
        self.assertIsNone(page.library())
        self.ws.app.route = "library"           # reached anyway: a plain explanation
        body = page.build()
        self.assertEqual(body.data, "library-none")


class DocumentTests(LibraryUiCase):
    def test_adding_shows_progress_then_the_documents(self):
        ws = self.ws
        self.project()
        page = self.open_library()
        seen = []
        original = page._progressed

        def spy(stage, done, total, name):
            original(stage, done, total, name)
            seen.append(ws.find("library-progress-text").value)

        page._progressed = spy
        outcomes = self.add((fx.EN_REVIEW, "pdf"), (fx.LV_MANUAL_V1, "docx"))
        self.assertEqual([o.passages for o in outcomes], [5, 6])
        self.assertIn("Reading fictional_review.pdf: page 1 of 3…", seen)
        self.assertIn("Reading fictional_review.pdf: page 3 of 3…", seen)
        self.assertIn("Indexing fictional_review.pdf: 5 passages…", seen)
        self.assertFalse(ws.find_all("library-progress"), "no progress once done")
        message = texts(ws, "library-message")
        self.assertIn(f"Added “{fx.EN_REVIEW.title}”: 5 passages.", message)
        self.assertIn(f"Added “{fx.LV_MANUAL_V1.title}”: 6 passages.", message)
        rows = {c.data for c in ws.find_all("library-doc-") if c.data.count("-") == 2}
        self.assertEqual(len(rows), 2)
        review = next(d for d in page.library().documents() if d.type == "pdf")
        meta = ws.find(f"library-doc-{review.id}-meta").value
        self.assertEqual(meta.split(" · ")[:2], ["5 passages", "3 pages"])
        self.assertEqual(ws.find("library-counts").value, "2 documents · 11 passages")
        again = self.add((fx.EN_REVIEW, "pdf"))
        self.assertTrue(again[0].duplicate)
        self.assertIn(T("library.duplicate", title=fx.EN_REVIEW.title),
                      texts(ws, "library-message"))
        broken = self.files / "broken.pdf"
        broken.write_bytes(b"%PDF-1.4\n% fictional damaged file")
        self.ws.run(page.add_files(picked(broken)))
        self.assertIn("broken.pdf was not added: the file could not be read; it may be damaged.",
                      texts(ws, "library-message"))

    def test_cancel_stops_adding_and_stores_nothing(self):
        ws = self.ws
        self.project()
        page = self.open_library()

        def cancel_on_first(stage, done, total, name):
            page.cancel_adding()

        page._progressed = cancel_on_first
        self.add((fx.RU_REVIEW, "pdf"))
        self.assertIn(T("library.cancelled", name="vymyshlennyj_obzor.pdf"),
                      texts(ws, "library-message"))
        self.assertEqual(page.library().counts(), (0, 0))

    def test_one_action_remove_and_the_search_no_longer_finds_it(self):
        ws = self.ws
        self.project()
        page = self.open_library()
        self.add((fx.EN_REVIEW, "pdf"), (fx.EN_NOTES, "txt"))
        self.search("avoidant coping mediator")
        self.assertIn("1 of 1 matching passages", ws.find("library-count").value)
        review = next(d for d in page.library().documents() if d.type == "pdf")
        remove = ws.find(f"library-doc-{review.id}-remove")
        self.assertEqual(remove.content, T("library.remove"))
        ws.click(f"library-doc-{review.id}-remove")              # one action, no dialog
        self.assertIsNone(ws.page.dialog)
        self.assertIn(T("library.removed", title=review.title, passages="5 passages"),
                      texts(ws, "library-message"))
        self.assertEqual(texts(ws, "library-no-results"),
                         T("library.no_results", query="avoidant coping mediator"))
        self.assertEqual(page.library().index_rows(review.id), 0)
        self.assertEqual(ws.find("library-counts").value, "1 document · 3 passages")

    def test_reindex_all_keeps_the_citations(self):
        ws = self.ws
        self.project()
        page = self.open_library()
        self.add((fx.RU_NOTES, "txt"), (fx.LV_REVIEW, "pdf"))
        before = sorted(p.cite_id for d in page.library().documents()
                        for p in page.library().passages(d.id))
        ws.click("library-reindex")
        self.assertIn(T("library.reindexed", documents="2 documents"),
                      texts(ws, "library-message"))
        after = sorted(p.cite_id for d in page.library().documents()
                       for p in page.library().passages(d.id))
        self.assertEqual(after, before)


class SearchTests(LibraryUiCase):
    def setUp(self):
        super().setUp()
        self.project()
        self.page = self.open_library()
        self.add((fx.EN_REVIEW, "pdf"), (fx.EN_MANUAL_V1, "md"), (fx.LV_REVIEW, "pdf"),
                 (fx.RU_NOTES, "txt"), (fx.RU_REVIEW, "md"), (fx.EN_NOTES, "txt"))

    def test_results_read_document_page_or_section_excerpt_and_version(self):
        ws = self.ws
        self.search("avoidant coping mediator")
        hit = self.page.result.hits[0]
        self.assertEqual(ws.find("library-hit-1-title").value, fx.EN_REVIEW.title)
        self.assertEqual(ws.find("library-hit-1-where").value,
                         f"page 2 · Coping as a mediator · {hit.cite_id}")
        excerpt = ws.find("library-hit-1-excerpt")
        marked = [span.text for span in excerpt.spans if span.style is not None]
        self.assertEqual(marked[:3], ["Coping", "mediator", "Avoidant"])
        self.assertEqual(ws.find("library-hit-1-open").content, T("library.open_page", page=2))
        self.search("informed consent withdrawn")
        where = ws.find("library-hit-1-where").value
        self.assertIn("Informed consent", where)
        self.assertEqual(ws.find("library-hit-1-open").content, T("library.open_document"))
        page = self.page
        library = page.library()
        manual = next(d for d in library.documents() if d.type == "md")
        self.assertTrue(manual.version_label == "" and "version" not in where)

    def test_why_this_source(self):
        ws = self.ws
        self.search("одиночества")
        self.assertFalse(ws.find_all("library-hit-1-why-text"))
        ws.click("library-hit-1-why")
        why = ws.find("library-hit-1-why-text").value
        self.assertIn("Rank 1 of", why)
        self.assertIn("“одиночеств…”", why)
        self.assertIn(T("library.why.method"), why)
        self.assertEqual(ws.find("library-hit-1-why").content, T("library.why_hide"))

    def test_filters_by_type_language_and_date(self):
        ws = self.ws
        self.search("pilot session")
        self.assertEqual({h.document.type for h in self.page.result.hits}, {"txt"})
        ws.choose("library-filter-type", "pdf")
        self.assertEqual({h.document.type for h in self.page.result.hits}, set())
        self.assertIn(T("library.no_results", query="pilot session"),
                      texts(ws, "library-no-results"))
        ws.choose("library-filter-type", "all")
        self.search("сессия одиночество")
        self.assertEqual({h.document.language for h in self.page.result.hits}, {"ru"})
        ws.choose("library-filter-language", "en")
        self.assertEqual(self.page.result.hits, ())
        ws.choose("library-filter-language", "ru")
        self.assertEqual({h.document.type for h in self.page.result.hits}, {"txt", "md"})
        ws.choose("library-filter-language", "all")
        ws.choose("library-filter-date", "week")
        self.assertTrue(self.page.result.hits, "added today")
        self.assertIn("since", self.page.result.filters)

    def test_a_pdf_citation_opens_in_the_page_viewer_and_others_in_the_system_viewer(self):
        ws = self.ws
        self.search("avoidant coping mediator")
        ws.click("library-hit-1-open")
        self.assertEqual(ws.find("library-viewer-title").value,
                         f"{fx.EN_REVIEW.title} — page 2 of 3")
        image = next(c for c in ws.controls(ws.page.dialog) if isinstance(c, ft.Image))
        self.assertTrue(image.src.startswith(b"\x89PNG"))
        self.assertIn(self.page.result.hits[0].cite_id, ws.find("library-viewer-passage").value)
        ws.click("library-viewer-prev")
        self.assertEqual(ws.find("library-viewer-title").value,
                         f"{fx.EN_REVIEW.title} — page 1 of 3")
        self.assertFalse(ws.find_all("library-viewer-prev"), "no page before the first")
        with mock.patch("workspace_library.open_with_system") as system:
            ws.click("library-viewer-system")
            self.assertIsNone(ws.page.dialog)
            system.assert_called_once()
            self.assertEqual(system.call_args.args[0].suffix, ".pdf")
            self.search("informed consent withdrawn")
            ws.click("library-hit-1-open")
            self.assertEqual(system.call_args.args[0].suffix, ".md")
        self.assertIn("opened in the system's viewer", ws.find("workspace-status").value)


class IsolationTests(LibraryUiCase):
    def test_switching_project_switches_the_library_and_forgets_the_page(self):
        ws = self.ws
        first = self.project("Fictional study A")
        page = self.open_library()
        self.add((fx.EN_REVIEW, "pdf"))
        self.search("avoidant coping")
        self.assertTrue(page.result.hits)
        second = self.project("Fictional study B")
        self.open_library()
        self.assertEqual(page.library().folder, second.path / rl.FOLDER)
        self.assertIsNone(page.result, "the results of A are not shown in B")
        self.assertIn(T("library.empty"), texts(ws, "library-documents"))
        self.search("avoidant coping")
        self.assertEqual(page.result.hits, ())
        ws.app.hub.binding.open(first.id)
        ws.app.navigate("library")
        self.assertEqual(page.library().counts()[0], 1)
        self.assertNotEqual(first.path, second.path)


class BackupChoiceTests(LibraryUiCase):
    """Whether the library travels in a .sra backup and in a project copy is
    the researcher's explicit choice, off by default (notes may hold
    personal data; independent review §7)."""

    def entries(self, path: Path) -> list[str]:
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()

    def test_off_by_default_on_when_chosen_in_backups_and_copies(self):
        ws = self.ws
        project = self.project("Fictional backup study")
        page = self.open_library()
        self.add((fx.EN_NOTES, "txt"), (fx.EN_REVIEW, "pdf"))
        self.assertFalse(ws.find("library-backup").value)
        self.assertEqual(ws.find("library-backup-note").value, T("library.backup_off"))
        store = ws.app.projects.store
        off = store.export_package(project.id, ws.root / "off.sra")
        self.assertFalse([n for n in self.entries(off) if "/library/" in n])
        copy = store.duplicate(project.id, "Copy without library")
        self.assertFalse((copy.path / rl.FOLDER).exists())

        ws.check("library-backup", True)
        self.assertTrue(rl.travels(project.path))
        self.assertEqual(ws.find("library-backup-note").value, T("library.backup_on"))
        ws.app.navigate("project")
        self.assertIn(T("library.card_backup_on"), texts(ws, "project-library"))
        on = store.export_package(project.id, ws.root / "on.sra")
        names = self.entries(on)
        self.assertIn("project/library/library.sqlite3", names)
        self.assertIn("project/library/backup.json", names)
        stored = [d.stored_name for d in page.library().documents()]
        for name in stored:
            self.assertIn(f"project/library/sources/{name}", names)
        restored, _warnings = store.import_package(on)
        self.assertNotEqual(restored.id, project.id)
        library = rl.Library.for_project(restored.path)
        self.assertEqual(sorted(p.cite_id for d in library.documents()
                                for p in library.passages(d.id)),
                         sorted(p.cite_id for d in page.library().documents()
                                for p in page.library().passages(d.id)))
        self.assertTrue(library.search("avoidant coping").hits)
        self.assertTrue(rl.travels(restored.path), "the choice travels with the library")
        duplicate = store.duplicate(project.id, "Copy with library")
        self.assertEqual(rl.Library.for_project(duplicate.path).counts(),
                         page.library().counts())

        ws.app.navigate("library")
        ws.check("library-backup", False)
        again = store.export_package(project.id, ws.root / "off-again.sra")
        self.assertFalse([n for n in self.entries(again) if "/library/" in n])


class LanguageTests(unittest.TestCase):
    def test_every_part_of_the_page_reads_in_every_language(self):
        for language in ("en", "lv", "ru"):
            with self.subTest(language=language), TemporaryDirectory() as folder:
                ws = Workspace(language=language, root=Path(folder))
                try:
                    ws.click("nav-home")
                    ws.type("project-new-title", "Fictional languages")
                    ws.click("project-create")
                    ws.app.navigate("project")
                    ws.click("project-library-open")
                    page = ws.app.pages["library"]
                    paths = [fx.write(fx.LV_REVIEW, Path(folder) / "in", "pdf"),
                             fx.write(fx.LV_MANUAL_V1, Path(folder) / "in", "docx")]
                    ws.run(page.add_files(picked(*paths)))
                    ws.type("library-query", "sociālais atbalsts")
                    ws.click("library-search-run")
                    ws.click("library-hit-1-why")
                    shown = [t for t in ws.texts() if t] + [
                        c.content for c in ws.controls()
                        if isinstance(c, (ft.Button, ft.TextButton)) and isinstance(c.content, str)]
                    bare = [t for t in shown if t.startswith(("library.", "assistant."))]
                    self.assertEqual(bare, [])
                    self.assertEqual(ws.find("library-add").content,
                                     TABLE["library.add"][("en", "lv", "ru").index(language)])
                    counts = ws.find("library-counts").value
                    self.assertTrue(counts.startswith("2 "), counts)
                finally:
                    ws.close()


if __name__ == "__main__":
    unittest.main()
