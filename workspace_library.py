"""The Research Library page of a project (Stage 37.3, Issue #69).

Reached from the Project page (*Open the research library*); the sidebar and
its Ctrl+1 … Ctrl+6 shortcuts are unchanged (the page belongs to the Project
item). Three cards:

* **Documents**: *Add document…* (PDF, DOCX, TXT, Markdown; local OCR for
  image-only PDF pages when ticked), indexing progress with Cancel, every
  document with its passages, pages, language and version, *Open* and a
  one-action *Remove*; *Read every document again*; whether the library
  travels in backups and project copies (off by default).
* **Search**: offline BM25 search with type, language and date filters. Each
  result reads document | page or section | excerpt | version, opens its
  source (PDF pages in the program's own page viewer, other files in the
  system's viewer) and answers *Why this source?*.
* **Ask with sources** (optional): local search for the question, the
  passages ticked by the researcher, the exact request, and *Send* as the
  approval of that one request (``library_ask``). The answer is a draft with
  every citation, number and quote checked against the passages sent.

A "Local only" badge says that search never goes online. Switching project
switches the library and forgets the page's state: nothing of one project is
shown in another (``LibraryPage.library``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import itertools
import os
from pathlib import Path
import subprocess
import sys
import threading

import flet as ft

import workspace_components as wc
import workspace_tokens as tk
from workspace_text import count_text

ADD_EXTENSIONS = ["pdf", "docx", "txt", "md"]
OCR_CHOICES = ("eng", "lav", "rus")
UI_OCR = {"en": "eng", "lv": "lav", "ru": "rus"}
DATE_FILTERS = {"any": None, "week": 7, "month": 30, "year": 365}
RESULTS = 10
CANDIDATES = 6
PRESELECTED = 3


def open_with_system(path: Path) -> None:
    """Open a file in the program the system uses for it (local, no network)."""
    path = Path(path)
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606 - a document the researcher added
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class AskState:
    """One question to the AI provider: the passages, the request, the answer."""

    def __init__(self):
        self.question = ""
        self.candidates = None          # research_library.SearchResult
        self.selected: set[int] = set()  # ranks of the ticked passages
        self.previewed = None           # library_ask.AskRequest shown now
        self.destination = None         # (provider, model) the preview names
        self.busy = False
        self.cancel: threading.Event | None = None
        self.ticket = 0
        self.answer = None              # library_ask.Answer
        self.error: tuple[str, dict] | None = None
        self.notice: tuple[str, str] | None = None


class LibraryPage:
    def __init__(self, app):
        self.app = app
        self.picker = ft.FilePicker(on_result=self._on_picked)
        app.page.services.append(self.picker)
        self.add_action = ft.PickFiles(
            self.picker, allow_multiple=True, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=ADD_EXTENSIONS, with_data=bool(getattr(app.page, "web", False)))
        # Extra arguments for the provider calls (tests: a local mock server).
        self.http: dict = {}
        self._tickets = itertools.count(1)
        self._library = None
        self._library_for = None
        self._ocr_probe: tuple[bool, tuple[str, ...]] | None = None
        self.opened: set[str] = set()
        self.reset()

    def reset(self) -> None:
        """Forget everything shown (another project, or none, is open now)."""
        self.query = ""
        self.result = None
        self.filter_type, self.filter_language, self.filter_date = "all", "all", "any"
        self.why: set[str] = set()
        self.busy = False
        self.progress: tuple[str, int, int, str] | None = None
        self._cancel: threading.Event | None = None
        self.message: tuple[str, str] | None = None
        self.version_label = ""
        self.ocr = True
        self.ocr_language: str | None = None
        self.ask = AskState()
        self.viewer: dict | None = None

    # ------------------------------------------------------------ state
    def library(self):
        """The open project's library (created on first use), or None."""
        from research_library import Library

        binding = self.app.projects
        if not binding.active:
            self._library, self._library_for = None, None
            return None
        key = (binding.project.id, binding.generation)
        if self._library_for != key:
            self.reset()
            self._library_for = key
            self._library = Library.for_project(binding.project.path)
        return self._library

    def ocr_engine(self) -> tuple[bool, tuple[str, ...]]:
        if self._ocr_probe is None:
            from research_library import ocr_available

            self._ocr_probe = ocr_available()
        return self._ocr_probe

    @property
    def data_root(self) -> Path:
        return self.app.project_root.parent

    def _language_of_ui(self) -> str:
        return UI_OCR.get(self.app.ui.language, "eng")

    # ------------------------------------------------------------ build
    def build(self) -> ft.Control:
        from research_library import LibraryError

        app, ui = self.app, self.app.ui
        try:
            library = self.library()
        except LibraryError as error:
            return app.constrained(wc.notice(ui, self.error_text(error), "danger",
                                             title=ui.t("library.title"), data="library-failed"))
        if library is None:
            return wc.empty_state(ui, ft.Icons.LOCAL_LIBRARY_OUTLINED, ui.t("library.title"),
                                  ui.t("library.no_project"), actions=[
                                      wc.button(ui, ui.t("nav.home"), lambda e: app.navigate("home"),
                                                kind="primary", data="library-home")],
                                  data="library-none")
        info = app.projects.info()
        badge = wc.chip(ui, ui.t("library.local"), "success", icon=ft.Icons.LOCK_OUTLINE,
                        tooltip=ui.t("library.local_tip"), data="library-local")
        header = wc.page_header(ui, ui.t("library.title"),
                                ui.t("library.subtitle", project=info.title), badge=badge,
                                actions=[wc.button(ui, ui.t("library.back"),
                                                   lambda e: app.navigate("project"), kind="quiet",
                                                   icon=ft.Icons.ARROW_BACK, data="library-back")])
        body: list[ft.Control] = [header]
        if self.message:
            body.append(wc.notice(ui, self.message[0], self.message[1], data="library-message"))
        body += [self._documents(library), self._search(library), self._ask(library)]
        return app.constrained(ft.Column(body, spacing=tk.SPACE_4, data="library-page",
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH))

    # ------------------------------------------------------- documents
    def _documents(self, library) -> ft.Control:
        import research_library as rl

        ui = self.app.ui
        documents = library.documents()
        available, languages = self.ocr_engine()
        add_row: list[ft.Control] = [
            wc.button(ui, ui.t("library.add"), action=self.add_action, kind="primary",
                      icon=ft.Icons.NOTE_ADD_OUTLINED, data="library-add"),
        ]
        version = wc.text_field(ui, ui.t("library.version"), self.version_label, width=240,
                                hint=ui.t("library.version_hint"),
                                on_change=lambda e: setattr(self, "version_label",
                                                            e.control.value or ""),
                                data="library-version")
        add_row.append(version)
        options: list[ft.Control] = []
        if available:
            options.append(wc.checkbox(ui, ui.t("library.ocr"), self.ocr,
                                       on_change=lambda e: self._set_ocr(bool(e.control.value)),
                                       data="library-ocr"))
            offered = [code for code in OCR_CHOICES if code in languages] or ["eng"]
            chosen = self.ocr_language or self._language_of_ui()
            if chosen not in offered:
                chosen = offered[0]
            options.append(wc.dropdown(ui, ui.t("library.ocr_language"),
                                       [(code, ui.t(f"library.ocr_lang.{code}")) for code in offered],
                                       chosen, on_select=lambda e: self._set_ocr_language(
                                           e.control.value), width=220,
                                       data="library-ocr-language"))
        else:
            options.append(wc.caption(ui, ui.t("library.ocr_unavailable"),
                                      data="library-ocr-unavailable"))
        content: list[ft.Control] = [
            ft.Row(add_row, wrap=True, spacing=tk.SPACE_3,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(options, wrap=True, spacing=tk.SPACE_3,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            wc.caption(ui, ui.t("library.permitted")),
        ]
        if self.busy:
            content.append(self._progress_row())
        rows: list[ft.Control] = [self._document_row(document) for document in documents]
        if not rows:
            rows.append(wc.caption(ui, ui.t("library.empty"), data="library-empty"))
        content += rows
        count, passages = len(documents), sum(d.passages for d in documents)
        footer: list[ft.Control] = [wc.caption(ui, counts_text(ui, count, passages),
                                               data="library-counts")]
        if documents:
            footer.append(wc.button(ui, ui.t("library.reindex"), self.reindex_all, kind="quiet",
                                    icon=ft.Icons.REFRESH, data="library-reindex"))
        content.append(ft.Row(footer, wrap=True, spacing=tk.SPACE_3,
                              vertical_alignment=ft.CrossAxisAlignment.CENTER))
        outdated = [d for d in documents if d.chunker != rl.CHUNKER]
        if outdated:
            content.append(wc.notice(ui, ui.t("library.outdated", documents=count_text(
                ui.language, len(outdated), "documents")), "info", data="library-outdated"))
        travels = rl.travels(self.app.projects.project.path)
        content.append(wc.checkbox(ui, ui.t("library.backup"), travels,
                                   on_change=lambda e: self.set_travels(bool(e.control.value)),
                                   data="library-backup"))
        content.append(wc.caption(ui, ui.t("library.backup_on" if travels else "library.backup_off"),
                                  data="library-backup-note"))
        return wc.card(ui, content, title=ui.t("library.documents"),
                       description=ui.t("library.documents_body"), data="library-documents")

    def _progress_row(self) -> ft.Control:
        ui = self.app.ui
        stage, done, total, name = self.progress or ("read", 0, 0, "")
        text = ui.t(f"library.progress.{stage}", name=name, done=done, total=total)
        value = (done / total) if total else None
        return ft.Column([
            ft.ProgressBar(value=value, semantics_label=text),
            ft.Row([wc.text(ui, text, data="library-progress-text"),
                    wc.button(ui, ui.t("library.cancel"), self.cancel_adding, kind="quiet",
                              icon=ft.Icons.CLOSE, data="library-cancel")],
                   wrap=True, spacing=tk.SPACE_3,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], spacing=tk.SPACE_2, data="library-progress")

    def _document_row(self, document) -> ft.Control:
        ui = self.app.ui
        chips = [wc.chip(ui, document.type.upper(), "neutral"),
                 wc.chip(ui, ui.t(f"library.lang.{document.language}"), "neutral")]
        if document.version_label:
            chips.append(wc.chip(ui, ui.t("library.version_chip", version=document.version_label),
                                 "info"))
        meta = [count_text(ui.language, document.passages, "passages")]
        if document.page_count:
            meta.append(count_text(ui.language, document.page_count, "pages"))
        meta.append(ui.t("library.added", date=_date(document.imported_at)))
        meta.append(document.file_name)
        details: list[ft.Control] = [
            ft.Row([wc.text(ui, document.title, tk.TYPE_BODY, weight=ft.FontWeight.W_600),
                    *chips], wrap=True, spacing=tk.SPACE_2),
            wc.caption(ui, " · ".join(meta), data=f"library-doc-{document.id}-meta"),
        ]
        if document.ocr_pages:
            details.append(wc.caption(ui, ui.t("library.ocr_pages", pages=_pages(
                document.ocr_pages))))
        actions = ft.Row([
            wc.button(ui, ui.t("library.open"), wc.handler(self.open_document, document.id),
                      kind="quiet", icon=ft.Icons.OPEN_IN_NEW, data=f"library-doc-{document.id}-open"),
            wc.button(ui, ui.t("library.remove"), wc.handler(self.remove, document.id),
                      kind="quiet", icon=ft.Icons.DELETE_OUTLINE,
                      tooltip=ui.t("library.remove_tip"), data=f"library-doc-{document.id}-remove"),
        ], spacing=tk.SPACE_1, wrap=True)
        layout = (ft.Column([ft.Column(details, spacing=2), actions], spacing=tk.SPACE_2)
                  if self.app.compact else
                  ft.Row([ft.Column(details, spacing=2, expand=True), actions],
                         vertical_alignment=ft.CrossAxisAlignment.CENTER))
        return ft.Container(layout, border=ft.Border.all(1, ui.p.border),
                            border_radius=ui.radius("card"), padding=tk.SPACE_3,
                            data=f"library-doc-{document.id}")

    # ---------------------------------------------------------- search
    def _filters(self) -> list[ft.Control]:
        ui = self.app.ui
        return [
            wc.dropdown(ui, ui.t("library.filter.type"),
                        [("all", ui.t("library.filter.any_type")),
                         *[(kind, kind.upper()) for kind in ("pdf", "docx", "txt", "md")]],
                        self.filter_type, on_select=lambda e: self._set_filter("type",
                                                                              e.control.value),
                        width=180, data="library-filter-type"),
            wc.dropdown(ui, ui.t("library.filter.language"),
                        [("all", ui.t("library.filter.any_language")),
                         *[(code, ui.t(f"library.lang.{code}")) for code in ("en", "lv", "ru",
                                                                             "other")]],
                        self.filter_language, on_select=lambda e: self._set_filter(
                            "language", e.control.value), width=200,
                        data="library-filter-language"),
            wc.dropdown(ui, ui.t("library.filter.date"),
                        [(key, ui.t(f"library.filter.date.{key}")) for key in DATE_FILTERS],
                        self.filter_date, on_select=lambda e: self._set_filter("date",
                                                                              e.control.value),
                        width=200, data="library-filter-date"),
        ]

    def _search(self, library) -> ft.Control:
        ui = self.app.ui
        field = wc.text_field(ui, ui.t("library.query"), self.query, expand=True,
                              hint=ui.t("library.query_hint"),
                              on_change=lambda e: setattr(self, "query", e.control.value or ""),
                              data="library-query")
        field.on_submit = lambda e: self.search()
        content: list[ft.Control] = [
            ft.Row([field, wc.button(ui, ui.t("library.search"), lambda e: self.search(),
                                     kind="primary", icon=ft.Icons.SEARCH,
                                     data="library-search-run")],
                   spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row(self._filters(), wrap=True, spacing=tk.SPACE_3),
        ]
        result = self.result
        if result is not None:
            if not result.terms:
                content.append(wc.notice(ui, ui.t("library.no_terms"), "info",
                                         data="library-no-results"))
            elif not result.hits:
                content.append(wc.notice(ui, ui.t("library.no_results", query=result.query),
                                         "info", data="library-no-results"))
            else:
                content.append(wc.caption(ui, ui.t("library.count", shown=len(result.hits),
                                                   total=result.total), data="library-count"))
                content += [self._hit(library, result, hit) for hit in result.hits]
        return wc.card(ui, content, title=ui.t("library.search_title"),
                       description=ui.t("library.search_body"), data="library-search")

    def where(self, hit) -> str:
        """Page or section, version and cite ID, in the interface language."""
        ui = self.app.ui
        parts = []
        if hit.passage.page is not None:
            parts.append(ui.t("library.page", page=hit.passage.page))
        if hit.passage.section:
            parts.append(hit.passage.section)
        if hit.document.version_label:
            parts.append(ui.t("library.version_chip", version=hit.document.version_label))
        parts.append(hit.cite_id)
        return " · ".join(parts)

    def _excerpt(self, snippet: str, data: str) -> ft.Text:
        import research_library as rl

        ui = self.app.ui
        spans = [ft.TextSpan(" ".join(text.split("\n")), style=ft.TextStyle(
            weight=ft.FontWeight.W_700, bgcolor=ui.p.accent_subtle) if marked else None)
                 for text, marked in rl.snippet_parts(snippet)]
        plain = rl.plain_snippet(snippet)
        return ft.Text(spans=spans, size=tk.TYPE_BODY[0], color=ui.p.text, selectable=True,
                       semantics_label=plain, data=data)

    def _hit(self, library, result, hit) -> ft.Control:
        ui = self.app.ui
        key = f"library-hit-{hit.rank}"
        open_label = (ui.t("library.open_page", page=hit.passage.page)
                      if hit.document.type == "pdf" and hit.passage.page else
                      ui.t("library.open_document"))
        content: list[ft.Control] = [
            wc.text(ui, hit.document.title, tk.TYPE_BODY, weight=ft.FontWeight.W_600,
                    data=f"{key}-title"),
            wc.caption(ui, self.where(hit), data=f"{key}-where"),
            self._excerpt(hit.snippet, f"{key}-excerpt"),
            ft.Row([
                wc.button(ui, open_label, wc.handler(self.open_hit, hit), kind="quiet",
                          icon=ft.Icons.OPEN_IN_NEW, data=f"{key}-open"),
                wc.button(ui, ui.t("library.why_hide" if key in self.why else "library.why"),
                          lambda e, k=key: self._toggle_why(k), kind="quiet",
                          icon=ft.Icons.HELP_OUTLINE, data=f"{key}-why"),
            ], wrap=True, spacing=tk.SPACE_1),
        ]
        if key in self.why:
            content.append(wc.caption(ui, self.explanation(library, result, hit),
                                      data=f"{key}-why-text"))
        return ft.Container(ft.Column(content, spacing=tk.SPACE_1),
                            border=ft.Border.all(1, ui.p.border), border_radius=ui.radius("card"),
                            padding=tk.SPACE_3, data=key)

    def explanation(self, library, result, hit) -> str:
        ui = self.app.ui
        why = library.explain(hit, result)
        lines = [ui.t("library.why.rank", rank=why.rank, total=why.total,
                      score=f"{why.score:.2f}")]
        if why.matched:
            lines.append(ui.t("library.why.matched", words=", ".join(
                f"“{word}” ×{count}" for word, count in why.matched)))
        if why.missing:
            lines.append(ui.t("library.why.missing", words=", ".join(f"“{w}”" for w in why.missing)))
        lines.append(ui.t("library.why.method"))
        if why.filters:
            lines.append(ui.t("library.why.filters", filters=self._filter_text(why.filters)))
        return "\n".join(lines)

    def _filter_text(self, filters: dict) -> str:
        ui = self.app.ui
        parts = []
        if filters.get("types"):
            parts.append(", ".join(kind.upper() for kind in filters["types"]))
        if filters.get("language"):
            parts.append(ui.t(f"library.lang.{filters['language']}"))
        if filters.get("since"):
            parts.append(ui.t(f"library.filter.date.{self.filter_date}"))
        return "; ".join(parts)

    def search_options(self) -> dict:
        days = DATE_FILTERS.get(self.filter_date)
        since = ((datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
                 if days else None)
        return {"types": () if self.filter_type == "all" else (self.filter_type,),
                "language": None if self.filter_language == "all" else self.filter_language,
                "since": since}

    def search(self, *, render: bool = True):
        """Search the open project's library (offline)."""
        library = self.library()
        if library is None:
            return None
        self.result = library.search(self.query, limit=RESULTS, **self.search_options())
        self.why = set()
        if self.result.terms:
            self.app.status(self.app.t("library.searched", passages=count_text(
                self.app.ui.language, self.result.total, "passages")), "info")
        if render:
            self.app.render()
        return self.result

    # ------------------------------------------------------ open sources
    async def open_hit(self, hit):
        await self.show_source(hit.document, hit.passage.page, passage=hit.passage)

    async def open_document(self, document_id: int):
        library = self.library()
        if library is None:
            return
        document = library.document(document_id)
        await self.show_source(document, 1 if document.type == "pdf" else None)

    async def show_source(self, document, page, *, passage=None):
        """A PDF page in the program's page viewer; other files in the system's."""
        from research_library import LibraryError

        app, library = self.app, self.library()
        if library is None:
            return
        path = library.source_file(document)
        if document.type != "pdf" or not page:
            try:
                await asyncio.to_thread(open_with_system, path)
            except Exception as error:
                app.status(app.t("library.open_failed", name=document.file_name,
                                 error=str(error) or type(error).__name__), "danger")
                return
            app.status(app.t("library.opened_system", name=document.file_name), "success")
            return
        try:
            png = await asyncio.to_thread(library.render_page, document, int(page))
        except (LibraryError, OSError, ValueError) as error:
            app.status(app.t("library.open_failed", name=document.file_name,
                             error=self.error_text(error)), "danger")
            return
        self.viewer = {"document": document, "page": int(page), "png": png, "passage": passage}
        self._show_viewer()
        app.status(app.t("library.viewer_status", title=document.title, page=page), "info")

    def _show_viewer(self):
        app, ui = self.app, self.app.ui
        viewer = self.viewer
        document, page = viewer["document"], viewer["page"]
        title = ui.t("library.viewer_title", title=document.title, page=page,
                     pages=document.page_count)
        content: list[ft.Control] = [
            ft.Container(ft.Image(src=viewer["png"], fit=ft.BoxFit.CONTAIN,
                                  semantics_label=title),
                         bgcolor="#FFFFFF", height=min(760, int(getattr(app.page, "height", 800)
                                                                 or 800) - 220)),
        ]
        passage = viewer.get("passage")
        if passage is not None and passage.page == page:
            content.append(wc.caption(ui, ui.t("library.viewer_passage", cite=passage.cite_id,
                                               text=" ".join(passage.text.split())[:400]),
                                      data="library-viewer-passage"))
        actions = []
        if page > 1:
            actions.append(wc.button(ui, ui.t("library.viewer_previous"),
                                     wc.handler(self.turn, -1), kind="quiet",
                                     icon=ft.Icons.NAVIGATE_BEFORE, data="library-viewer-prev"))
        if page < document.page_count:
            actions.append(wc.button(ui, ui.t("library.viewer_next"), wc.handler(self.turn, 1),
                                     kind="quiet", icon=ft.Icons.NAVIGATE_NEXT,
                                     data="library-viewer-next"))
        actions += [
            wc.button(ui, ui.t("library.viewer_system"), wc.handler(self.open_in_system),
                      kind="quiet", icon=ft.Icons.OPEN_IN_NEW, data="library-viewer-system"),
            wc.button(ui, ui.t("common.close"), self.close_viewer, kind="primary",
                      data="library-viewer-close"),
        ]
        dialog = ft.AlertDialog(
            title=wc.heading(ui, title, tk.TYPE_TITLE_S, data="library-viewer-title"),
            content=ft.Container(ft.Column(content, spacing=tk.SPACE_2, tight=True,
                                           scroll=ft.ScrollMode.AUTO),
                                 width=min(980, app.content_width)),
            actions=actions, data="library-viewer")
        app.page.show_dialog(dialog)

    async def turn(self, step: int):
        viewer = self.viewer
        if viewer is None:
            return
        document = viewer["document"]
        page = min(max(1, viewer["page"] + step), document.page_count)
        try:
            png = await asyncio.to_thread(self.library().render_page, document, page)
        except Exception as error:
            self.app.status(self.app.t("library.open_failed", name=document.file_name,
                                       error=self.error_text(error)), "danger")
            return
        self.viewer = {**viewer, "page": page, "png": png}
        self.app.page.pop_dialog()
        self._show_viewer()

    async def open_in_system(self):
        viewer = self.viewer
        if viewer is None:
            return
        self.close_viewer()
        await self.show_source(viewer["document"], None)

    def close_viewer(self, e=None):
        self.viewer = None
        self.app.page.pop_dialog()

    # ---------------------------------------------------- add, remove
    async def _on_picked(self, e):
        await self.add_files(getattr(e, "files", None))

    def _set_ocr(self, value: bool):
        self.ocr = value
        self.app.render()

    def _set_ocr_language(self, value):
        if value in OCR_CHOICES:
            self.ocr_language = value
        self.app.render()

    def _set_filter(self, which: str, value):
        if which == "type":
            self.filter_type = value or "all"
        elif which == "language":
            self.filter_language = value or "all"
        elif value in DATE_FILTERS:
            self.filter_date = value
        if self.result is not None:
            self.search(render=False)
        self.app.render()

    def _toggle_why(self, key: str):
        (self.why.discard if key in self.why else self.why.add)(key)
        self.app.render()

    async def add_files(self, files) -> list:
        """Add the chosen files one by one in a worker thread, with progress."""
        from research_library import LibraryError

        app = self.app
        library = self.library()
        if library is None or not files or self.busy:
            return []
        loop = asyncio.get_running_loop()
        self.busy, self.message = True, None
        self._cancel = cancel = threading.Event()
        generation = app.projects.generation
        available, _ = self.ocr_engine()
        language = self.ocr_language or self._language_of_ui()
        outcomes, messages = [], []
        try:
            for picked in files:
                name = str(getattr(picked, "name", "") or Path(getattr(picked, "path", "")
                                                                or "document").name)
                path = getattr(picked, "path", None) or None
                data = None if path else (getattr(picked, "bytes", None)
                                          or getattr(picked, "data", None))
                self.progress = ("read", 0, 0, name)
                app.render()

                def progress(stage, done, total, name=name):
                    loop.call_soon_threadsafe(self._progressed, stage, done, total, name)

                try:
                    outcome = await asyncio.to_thread(
                        library.add_document, path, data=data, file_name=name,
                        version_label=self.version_label, ocr=self.ocr and available,
                        ocr_language=language, progress=progress, cancel=cancel)
                except LibraryError as error:
                    if error.reason == "cancelled":
                        messages.append((app.t("library.cancelled", name=name), "info"))
                        break
                    messages.append((app.t("library.add_failed", name=name,
                                           reason=self.error_text(error)), "danger"))
                    continue
                except Exception as error:
                    messages.append((app.t("library.add_failed", name=name,
                                           reason=str(error) or type(error).__name__), "danger"))
                    continue
                outcomes.append(outcome)
                messages.append(self._added(outcome))
        finally:
            self.busy, self.progress, self._cancel = False, None, None
        if app.projects.generation != generation:
            return outcomes                   # another project is open now
        self.version_label = ""
        tone = ("danger" if any(t == "danger" for _, t in messages) else
                "warning" if any(t == "warning" for _, t in messages) else
                messages[-1][1] if messages else "info")
        self.message = (" ".join(text for text, _ in messages), tone) if messages else None
        if self.message:
            app.status(self.message[0], tone)
        if self.result is not None:
            self.search(render=False)
        app.render()
        return outcomes

    def _progressed(self, stage: str, done: int, total: int, name: str):
        if self.busy:
            self.progress = (stage, done, total, name)
            self.app.render()

    def cancel_adding(self, e=None):
        if self._cancel is not None:
            self._cancel.set()

    def _added(self, outcome) -> tuple[str, str]:
        app = self.app
        document = outcome.document
        if outcome.duplicate:
            return app.t("library.duplicate", title=document.title), "info"
        parts = [app.t("library.added_message", title=document.title,
                       passages=count_text(app.ui.language, outcome.passages, "passages"))]
        tone = "success"
        for key, values in outcome.notes:
            pages = _pages(values.get("pages", ()))
            if key == "versioned":
                parts.append(app.t("library.note.versioned", label=values["label"]))
            elif key in ("ocr_off", "ocr_unavailable", "ocr_failed", "ocr_limit"):
                parts.append(app.t(f"library.note.{key}", pages=pages,
                                   limit=values.get("limit", "")))
                tone = "warning"
            elif key == "ocr_read":
                parts.append(app.t("library.note.ocr_read", pages=pages))
        return " ".join(parts), tone

    async def remove(self, document_id: int):
        """One action: the document, its passages and their index rows go."""
        from research_library import LibraryError

        app, library = self.app, self.library()
        if library is None:
            return
        try:
            document = library.document(document_id)
            await asyncio.to_thread(library.remove_document, document_id)
        except (LibraryError, OSError) as error:
            self.message = (app.t("library.remove_failed", reason=self.error_text(error)),
                            "danger")
            app.render()
            return
        self.message = (app.t("library.removed", title=document.title, passages=count_text(
            app.ui.language, document.passages, "passages")), "success")
        app.status(self.message[0], "success")
        if self.result is not None:
            self.search(render=False)
        if self.ask.candidates is not None:
            self.ask.candidates, self.ask.selected, self.ask.previewed = None, set(), None
        app.render()

    async def reindex_all(self, e=None):
        from research_library import LibraryError

        app, library = self.app, self.library()
        if library is None or self.busy:
            return
        loop = asyncio.get_running_loop()
        self.busy, self.progress = True, ("document", 0, len(library.documents()), "")
        self._cancel = cancel = threading.Event()
        app.render()

        def progress(stage, done, total):
            loop.call_soon_threadsafe(self._progressed, "document", done, total, "")

        try:
            count = await asyncio.to_thread(library.reindex_all, progress=progress, cancel=cancel)
        except LibraryError as error:
            self.message = (app.t("library.reindex_failed", reason=self.error_text(error)),
                            "danger")
        else:
            self.message = (app.t("library.reindexed", documents=count_text(
                app.ui.language, count, "documents")), "success")
        finally:
            self.busy, self.progress, self._cancel = False, None, None
        if self.result is not None:
            self.search(render=False)
        app.render()

    def set_travels(self, value: bool):
        import research_library as rl

        project = self.app.projects.project
        if project is None:
            return
        rl.set_travels(project.path, value)
        self.message = (self.app.t("library.backup_on" if value else "library.backup_off"), "info")
        self.app.render()

    def error_text(self, error) -> str:
        reason = getattr(error, "reason", "")
        values = dict(getattr(error, "values", {}) or {})
        key = f"library.error.{reason}"
        from workspace_text import T

        if key in T:
            values.setdefault("name", "")
            if "size" in values:
                values["size"] = f"{values['size'] / 1024 ** 2:.1f} MB"
            if "limit" in values and reason == "too_large":
                values["limit"] = f"{values['limit'] / 1024 ** 2:.0f} MB"
            try:
                return self.app.t(key, **values)
            except (KeyError, IndexError):
                pass
        return str(error) or type(error).__name__

    # ------------------------------------------------------------- ask
    def _ask(self, library) -> ft.Control:
        import ai_context

        ui = self.app.ui
        state = self.ask
        setup = ai_context.readiness(self.data_root)
        content: list[ft.Control] = [wc.caption(ui, ui.t("library.ask.intro"))]
        if not setup.ready:
            content.append(wc.notice(
                ui, ui.t(f"assistant.off.{setup.problem}", provider=setup.provider_name), "info",
                title=ui.t("assistant.off_title"), actions=[
                    wc.button(ui, ui.t("assistant.open_settings"),
                              lambda e: self.app.navigate("settings"),
                              icon=ft.Icons.SETTINGS_OUTLINED, data="library-ask-settings")],
                data="library-ask-off"))
            return wc.card(ui, content, title=ui.t("library.ask.title"), data="library-ask")
        question = wc.text_field(ui, ui.t("library.ask.question"), state.question, multiline=True,
                                 hint=ui.t("library.ask.question_hint"),
                                 on_change=lambda e: setattr(state, "question",
                                                             (e.control.value or "")[:1000]),
                                 data="library-ask-question")
        question.disabled = state.busy
        content += [question,
                    wc.button(ui, ui.t("library.ask.find"), lambda e: self.find_passages(),
                              icon=ft.Icons.SEARCH, data="library-ask-find")]
        result = state.candidates
        if result is not None:
            if not result.hits:
                content.append(wc.notice(ui, ui.t("library.ask.none"), "info",
                                         data="library-ask-none"))
            else:
                content.append(wc.section_label(ui, ui.t("library.ask.passages")))
                for hit in result.hits:
                    content.append(wc.checkbox(
                        ui, f"{hit.document.title} · {self.where(hit)}", hit.rank in state.selected,
                        on_change=lambda e, r=hit.rank: self._pick(r, bool(e.control.value)),
                        disabled=state.busy, data=f"library-ask-pick-{hit.rank}"))
                    content.append(ft.Container(self._excerpt(hit.snippet,
                                                              f"library-ask-excerpt-{hit.rank}"),
                                                padding=ft.Padding.only(left=tk.SPACE_6)))
                request = self.ask_request()
                if request is None:
                    content.append(wc.caption(ui, ui.t("library.ask.choose"),
                                              data="library-ask-choose"))
                else:
                    state.previewed = request
                    state.destination = (setup.provider, setup.model)
                    content.append(self._preview(request, setup))
                    content.append(wc.button(
                        ui, ui.t("assistant.send", provider=setup.provider_name, model=setup.model),
                        wc.handler(self.send), kind="primary", icon=ft.Icons.SEND_OUTLINED,
                        disabled=state.busy, data="library-ask-send"))
                    content.append(wc.caption(ui, ui.t("library.ask.consent"),
                                              data="library-ask-consent"))
        if state.busy:
            content.append(ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=2),
                wc.text(ui, ui.t("assistant.sending", provider=setup.provider_name,
                                 model=setup.model)),
                wc.button(ui, ui.t("assistant.cancel"), self.cancel_ask, icon=ft.Icons.CLOSE,
                          data="library-ask-cancel"),
            ], spacing=tk.SPACE_3, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                data="library-ask-progress"))
        if state.notice is not None:
            content.append(wc.notice(ui, state.notice[0], state.notice[1],
                                     data="library-ask-notice"))
        if state.error is not None:
            content.append(self._error(setup))
        if state.answer is not None:
            content.append(self._answer(state.answer))
        return wc.card(ui, content, title=ui.t("library.ask.title"), data="library-ask")

    def ask_request(self):
        """The request the ticked passages make now (built locally), or None."""
        import library_ask

        state = self.ask
        if state.candidates is None:
            return None
        hits = [hit for hit in state.candidates.hits if hit.rank in state.selected]
        if not hits:
            return None
        return library_ask.build_request(state.question, hits, language=self.app.ui.language)

    def _preview(self, request, setup) -> ft.Control:
        ui = self.app.ui
        return wc.card(ui, [
            wc.text(ui, ui.t("assistant.preview.to", provider=setup.provider_name,
                             host=setup.host, model=setup.model), data="library-ask-to"),
            wc.text(ui, ui.t("assistant.preview.size", chars=request.characters,
                             tokens=request.tokens, reply=request.reply_tokens),
                    data="library-ask-size"),
            wc.text(ui, ui.t("library.ask.sent_passages", passages=count_text(
                ui.language, len(request.sources), "passages"), cites=", ".join(request.cite_ids)),
                data="library-ask-passages"),
            wc.text(ui, ui.t("library.ask.nothing_else"), data="library-ask-nothing-else"),
            wc.expansion(ui, wc.text(ui, ui.t("assistant.preview.text"), tk.TYPE_LABEL,
                                     weight=ft.FontWeight.W_600),
                         [ft.Container(wc.text(ui, request.prompt, tk.TYPE_BODY, selectable=True,
                                               data="library-ask-preview-text"),
                                       padding=tk.SPACE_3)],
                         key="library-ask-exact", opened=self.opened,
                         data="library-ask-exact"),
        ], title=ui.t("assistant.preview"), bgcolor=ui.p.surface_alt, data="library-ask-preview")

    def _error(self, setup) -> ft.Control:
        from workspace_assistant import ERRORS

        ui = self.app.ui
        code, values = self.ask.error
        if code in ("no_sources", "too_long"):
            message = ui.t(f"library.ask.error.{code}")
        else:
            key = ERRORS.get(code, "unknown")
            message = ui.t(f"assistant.error.{key}", provider=setup.provider_name,
                           model=setup.model or "—", **values)
        tone = "info" if code == "cancelled" else "danger"
        return wc.notice(ui, message, tone, data="library-ask-error")

    def _answer(self, answer) -> ft.Control:
        import ai_assist

        ui = self.app.ui
        controls: list[ft.Control] = [
            ft.Row([wc.chip(ui, ui.t("assistant.draft"), "warning", icon=ft.Icons.EDIT_NOTE)],
                   wrap=True),
            wc.caption(ui, ui.t("library.ask.meta", provider=_provider_name(answer.provider),
                                model=answer.model, time=_local(answer.at), tokens=answer.tokens),
                       data="library-answer-meta"),
        ]
        if answer.not_in_sources:
            controls.append(wc.notice(ui, ui.t("library.ask.not_in_sources"), "info",
                                      data="library-answer-none"))
        else:
            spans = [ft.TextSpan(piece, style=ft.TextStyle(
                bgcolor=ui.p.warning_subtle, color=ui.p.warning, weight=ft.FontWeight.W_700,
                decoration=ft.TextDecoration.UNDERLINE)) if flagged else ft.TextSpan(piece)
                for piece, flagged in ai_assist.highlight(answer.text, answer.unverified_numbers)]
            controls.append(ft.Text(spans=spans, size=tk.TYPE_BODY[0], color=ui.p.text,
                                    selectable=True, semantics_label=answer.text,
                                    data="library-answer-text"))
            check = answer.citations
            labels = {source.label: source for source in answer.sources}
            if check.cited:
                controls.append(wc.notice(ui, ui.t("library.ask.cited", labels=", ".join(
                    f"{label} = {labels[label].cite_id}" for label in check.cited)), "success",
                    data="library-answer-cited"))
            if check.unknown:
                controls.append(wc.notice(ui, ui.t("library.ask.unknown",
                                                   labels=", ".join(check.unknown)), "danger",
                                          title=ui.t("library.ask.unknown_title"),
                                          data="library-answer-unknown"))
            if check.foreign:
                controls.append(wc.notice(ui, ui.t("library.ask.foreign",
                                                   references="; ".join(check.foreign)),
                                          "warning", data="library-answer-foreign"))
            if check.uncited:
                controls.append(wc.notice(ui, ui.t("library.ask.uncited", statements=count_text(
                    ui.language, len(check.uncited), "statements")), "warning",
                    data="library-answer-uncited"))
            if answer.unverified_numbers:
                controls.append(wc.notice(ui, ui.t("library.ask.numbers", numbers=", ".join(
                    answer.unverified_numbers)), "warning", title=ui.t("assistant.unverified_title"),
                    data="library-answer-numbers"))
            if answer.unverified_quotes:
                controls.append(wc.notice(ui, ui.t("assistant.unverified_quotes", quotes="; ".join(
                    f"“{q}”" for q in answer.unverified_quotes)), "warning",
                    title=ui.t("assistant.unverified_quotes_title"),
                    data="library-answer-quotes"))
        for source in answer.sources:
            controls.append(ft.Row([
                wc.caption(ui, f"[{source.label}] {source.title} · {source.location}"
                           + (f" · {source.version}" if source.version else "")
                           + f" · {source.cite_id}", data=f"library-answer-source-{source.label}"),
                wc.button(ui, ui.t("library.open"),
                          wc.handler(self.open_cited, source.cite_id), kind="quiet",
                          icon=ft.Icons.OPEN_IN_NEW, data=f"library-answer-open-{source.label}"),
            ], wrap=True, spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        copy = wc.button(ui, ui.t("assistant.copy"), icon=ft.Icons.CONTENT_COPY,
                         action=ft.CopyToClipboard(answer.text), data="library-answer-copy")
        return wc.card(ui, controls, actions=[
            copy,
            wc.button(ui, ui.t("assistant.discard"), self.discard, kind="quiet",
                      icon=ft.Icons.DELETE_OUTLINE, data="library-answer-discard"),
        ], border=ui.p.warning, data="library-answer")

    def find_passages(self):
        """Local search for the question: the passages that may be sent."""
        library = self.library()
        state = self.ask
        if library is None or state.busy:
            return
        state.candidates = library.search(state.question, limit=CANDIDATES,
                                          **self.search_options())
        state.selected = {hit.rank for hit in state.candidates.hits[:PRESELECTED]}
        state.previewed, state.answer, state.error, state.notice = None, None, None, None
        self.app.render()

    def _pick(self, rank: int, value: bool):
        if not self.ask.busy:
            (self.ask.selected.add if value else self.ask.selected.discard)(rank)
        self.app.render()

    async def open_cited(self, cite_id: str):
        library = self.library()
        passage = library.passage(cite_id) if library is not None else None
        if passage is None:
            self.app.status(self.app.t("library.cite_gone", cite=cite_id), "warning")
            return
        document = library.document(passage.document_id)
        await self.show_source(document, passage.page if document.type == "pdf" else None,
                               passage=passage)

    async def send(self):
        """Send exactly the previewed request; the click is the approval."""
        import ai_context
        import ai_providers
        import secret_store

        app, state = self.app, self.ask
        if state.busy:
            return
        state.notice = None
        setup = ai_context.readiness(self.data_root)
        if not setup.ready:
            state.error = ("not_ready", {})
            app.render()
            return
        request = self.ask_request()
        if request is None:
            state.error = ("no_sources", {})
            app.render()
            return
        shown = state.previewed
        if (shown is None or shown.prompt != request.prompt
                or state.destination != (setup.provider, setup.model)):
            state.notice = (app.t("assistant.preview_changed"), "warning")
            app.render()
            return
        state.busy, state.error, state.answer = True, None, None
        state.cancel = cancel = threading.Event()
        state.ticket = ticket = next(self._tickets)
        generation = app.projects.generation
        project, library = app.projects.project, self.library()
        app.render()
        answer, error = None, None
        try:
            answer = await asyncio.to_thread(self._exchange, request, setup, project, library,
                                             cancel)
        except ai_providers.ProviderError as failure:
            error = (failure.reason, self._values(failure.reason, setup, request))
        except ai_context.ContextRefused as refused:
            error = (refused.codes[0] if refused.codes else "unknown", {})
        except (secret_store.SecretStoreUnavailable, OSError):
            error = ("no_store", {})
        except Exception:
            error = ("unknown", {})
        if state.ticket != ticket:
            return
        state.busy, state.cancel = False, None
        if app.projects.generation != generation:
            return                                  # another project is open now
        state.error, state.answer = error, answer
        if answer is not None and not answer.logged:
            state.notice = (app.t("assistant.not_logged"), "warning")
        app.render()

    def _exchange(self, request, setup, project, library, cancel):
        import ai_providers
        import library_ask
        import secret_store

        key = secret_store.get_key(setup.provider)
        if not key:
            import ai_context

            raise ai_context.ContextRefused("No key is stored for this provider.", ("not_ready",))
        budget = ai_providers.Budget(ai_providers.usage_path(self.data_root), setup.daily_tokens)
        return library_ask.send(request, setup=setup, key=key, project=project,
                                data_root=self.data_root, library=library, budget=budget,
                                cancel=cancel, **self.http)

    def _values(self, code: str, setup, request) -> dict:
        if code == "budget":
            import ai_providers

            budget = ai_providers.Budget(ai_providers.usage_path(self.data_root),
                                         setup.daily_tokens)
            return {"used": budget.used(), "limit": setup.daily_tokens,
                    "needed": request.tokens + request.reply_tokens}
        return {}

    def cancel_ask(self, e=None):
        state = self.ask
        if not state.busy:
            return
        if state.cancel is not None:
            state.cancel.set()
        state.busy, state.cancel, state.ticket = False, None, 0
        state.error = ("cancelled", {})
        self.app.render()

    def discard(self, e=None):
        self.ask.answer, self.ask.notice = None, None
        self.app.render()


# ================================================================ project
def project_card(app) -> ft.Control:
    """The Research library card on the Project page."""
    import research_library as rl

    ui = app.ui
    documents, passages = rl.peek(app.projects.project.path)
    summary = counts_text(ui, documents, passages) if documents else ui.t("library.card_empty")
    travels = rl.travels(app.projects.project.path)
    return wc.card(ui, [wc.text(ui, summary, tk.TYPE_BODY, data="project-library-counts"),
                        wc.caption(ui, ui.t("library.card_backup_on" if travels
                                            else "library.card_backup_off"),
                                   data="project-library-backup")],
                   title=ui.t("library.title"), description=ui.t("library.card_body"),
                   actions=[wc.button(ui, ui.t("library.open_library"),
                                      lambda e: app.navigate("library"),
                                      icon=ft.Icons.LOCAL_LIBRARY_OUTLINED,
                                      data="project-library-open")],
                   data="project-library")


def counts_text(ui, documents: int, passages: int) -> str:
    return ui.t("library.counts", documents=count_text(ui.language, documents, "documents"),
                passages=count_text(ui.language, passages, "passages"))


def _date(stamp: str) -> str:
    try:
        return f"{datetime.fromisoformat(stamp).astimezone():%Y-%m-%d}"
    except ValueError:
        return stamp[:10]


def _local(stamp: str) -> str:
    try:
        return f"{datetime.fromisoformat(stamp).astimezone():%Y-%m-%d %H:%M}"
    except ValueError:
        return stamp


def _pages(pages) -> str:
    return ", ".join(str(page) for page in pages)


def _provider_name(provider: str) -> str:
    import ai_providers

    info = ai_providers.PROVIDERS.get(provider)
    return info.name if info else provider
