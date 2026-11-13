"""Stage 37.3 (#69): the flow of the packaged-program journey
`research-library`, through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. This test walks the same flow in the workspace harness
and checks, at each point, that every text and button name the journey waits
for is really there in that state (a button is named by its label), with the
journey's own texts and on-disk helpers. The Open dialog is the only step
the harness cannot show: the file it would return is handed to the page's
picker handler. Disabled states are not part of the journey (UI Automation
reports every button as enabled). Synthetic data only; no AI key anywhere
and nothing on the network.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

from test_stage368_acceptance import (  # noqa: E402
    create_project_in_ui, folder_of, label, names, on_screen,
)
from test_stage368_ai_gate import NetworkGuard  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402


class JourneyOrderTests(unittest.TestCase):
    def test_the_library_journey_follows_the_eighteen(self):
        self.assertEqual(len(e2e.JOURNEYS), 19)
        self.assertEqual(list(e2e.JOURNEYS)[18:], ["research-library"])
        self.assertIs(e2e.JOURNEYS["research-library"], e2e.journey_research_library)
        self.assertNotIn("research-library", e2e.STARTS_ITSELF)


class ResearchLibraryJourneyTests(unittest.TestCase):
    """Journey `research-library`: add, search offline, open the citation,
    remove with one action, nothing found afterwards."""

    def test_add_search_open_remove_and_nothing_found(self):
        guard = NetworkGuard()
        guard.install(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ws = Workspace(root=root)
            self.addCleanup(ws.close)
            disk, title = folder_of(root), e2e.LIBRARY_PROJECT
            texts = e2e.library_texts()
            pdf = e2e.library_document(root / "work")
            create_project_in_ui(ws, title)
            self.assertEqual(ws.app.route, "project", "a new project opens on its page")
            before = e2e.ai_traffic(disk, title)

            # Open the research library from the project page.
            self.assertEqual(label(ws, "project-library-open"), texts["open"])
            ws.click("project-library-open")
            self.assertTrue(on_screen(ws, texts["local"]))
            self.assertIn(texts["title"], names(ws))

            # Add document… → the Open dialog gives the PDF.
            self.assertEqual(label(ws, "library-add"), texts["add"])
            self.assertIsInstance(ws.find("library-add").action, ft.PickFiles,
                                  "the button opens the system's Open dialog")
            page = ws.app.pages["library"]
            ws.run(page._on_picked(SimpleNamespace(files=[
                SimpleNamespace(name=pdf.name, path=str(pdf))])))
            self.assertTrue(on_screen(ws, texts["added"]))
            self.assertEqual(e2e.library_counts(disk, title),
                             {"exists": True, "documents": 1, "passages": 5,
                              "backend": "fts5", "index_rows": 5, "stored_files": 1})

            # Search offline.
            field = ws.find("library-query", ft.TextField)
            self.assertEqual(field.label, texts["query"])
            ws.type("library-query", e2e.LIBRARY_QUERY)
            self.assertEqual(label(ws, "library-search-run"), texts["search"])
            ws.click("library-search-run")
            self.assertTrue(on_screen(ws, texts["count"]))
            where = [t for t in names(ws) if e2e.LIBRARY_WHERE.match(t)]
            self.assertEqual(len(where), 1, names(ws))
            cite = e2e.LIBRARY_WHERE.match(where[0]).group(1)
            self.assertEqual(cite, page.result.hits[0].cite_id)

            # Open the citation in the page viewer, then close it.
            self.assertEqual(label(ws, "library-hit-1-open"), texts["open_page"])
            ws.click("library-hit-1-open")
            self.assertEqual(ws.find("library-viewer-title").value, texts["viewer"])
            self.assertEqual(label(ws, "library-viewer-close"), texts["close"])
            ws.click("library-viewer-close")
            self.assertIsNone(ws.page.dialog)
            self.assertFalse(on_screen(ws, texts["viewer"]))

            # Remove with one action: the only "Remove" button on the page.
            document = page.library().documents()[0]
            removes = [c for c in ws.controls() if isinstance(c, (ft.Button, ft.TextButton))
                       and c.content == texts["remove"]]
            self.assertEqual([c.data for c in removes], [f"library-doc-{document.id}-remove"])
            ws.click(f"library-doc-{document.id}-remove")
            self.assertIsNone(ws.page.dialog, "no confirmation step")
            self.assertTrue(on_screen(ws, texts["removed"]))
            self.assertEqual(e2e.library_counts(disk, title),
                             {"exists": True, "documents": 0, "passages": 0,
                              "backend": "fts5", "index_rows": 0, "stored_files": 0})

            # The same search finds nothing.
            self.assertEqual(ws.find("library-query", ft.TextField).value, e2e.LIBRARY_QUERY)
            ws.click("library-search-run")
            self.assertTrue(on_screen(ws, texts["nothing"]))
            self.assertFalse([t for t in names(ws) if re.search(r"-p2\.1$", t)])
            self.assertEqual(e2e.ai_traffic(disk, title), before, "nothing was sent")
        self.assertEqual(guard.attempts, [])

    def test_the_journey_texts_exist_in_the_interface_table(self):
        texts = e2e.library_texts()
        self.assertEqual(texts["added"], "Added “Fictional review of loneliness and support”: "
                                         "5 passages.")
        self.assertEqual(texts["viewer"], "Fictional review of loneliness and support — page 2 of 3")
        self.assertTrue(e2e.LIBRARY_WHERE.match("page 2 · Coping as a mediator · DABCDEF12-p2.1"))


if __name__ == "__main__":
    unittest.main()
