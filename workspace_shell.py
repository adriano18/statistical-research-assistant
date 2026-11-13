"""Stage 33 research workspace: shell, navigation and the Home/Data pages.

``WorkspaceApp`` owns the window chrome (collapsible sidebar, context bar,
status line), keyboard shortcuts, theme and language, the file pickers and
the session. Pages are small classes with a ``build()`` method; Analyze,
Results and Reports live in ``workspace_analyze``; Questionnaires and the
scientific import workspace in ``workspace_questionnaires``.

The workspace runs standalone (``python workspace_app.py``) or inside the
classic application through a :class:`ClassicBridge`, which shares the
dataset, survey storage and language with the classic screens. Since Stage
37 (issue #68) it is the normal start of the program; the classic interface
stays one click away (sidebar, Help, Settings) and can be chosen as the
start interface. The researcher's settings (language, theme, accent, text
size, density, typeface, window, sidebar, last page) are kept in one file
(``user_settings``); the Settings page is ``workspace_settings``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Awaitable, Callable
import weakref

import flet as ft
import pandas as pd

import user_settings as us
import workspace_tokens as tk
import workspace_components as wc
from workspace_state import LEVELS, ResearchSession
from workspace_text import count_text

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"
# Sample datasets: (file in examples/, text key of its label).
SAMPLES = (
    ("sample_scale.csv", "sample.scale"),
    ("sample_survey.csv", "sample.survey"),
    ("sample_three_groups.csv", "sample.three_groups"),
    ("sample_paired.csv", "sample.paired"),
    ("sample_repeated.csv", "sample.repeated"),
    ("sample_categorical.csv", "sample.categorical"),
    ("sample_regression.csv", "sample.regression"),
    ("sample_logistic.csv", "sample.logistic"),
    ("sample_ancova.csv", "sample.ancova"),
    ("sample_ancova_interaction.csv", "sample.ancova_interaction"),
    ("sample_omega_bootstrap.csv", "sample.omega_bootstrap"),
    ("sample_factor.csv", "sample.factor"),
)
AREAS = ("home", "data", "questionnaires", "analyze", "results", "reports")
# Pages with a sidebar name (the last page offered on Home is named by it).
_NAV_KEYS = {f"nav.{key}" for key in AREAS + ("project", "settings", "help")}
_ACTIVE: "weakref.ReferenceType[WorkspaceApp] | None" = None


def active_app() -> "WorkspaceApp | None":
    """The workspace most recently mounted in this process (tests, diagnostics)."""
    return _ACTIVE() if _ACTIVE is not None else None
DATA_EXTENSIONS = ["csv", "tsv", "xlsx", "xlsm"]
DOCUMENT_EXTENSIONS = ["pdf", "docx", "doc"]


@dataclass
class ClassicBridge:
    """Connections to the classic application (all optional)."""

    current_dataset: Callable[[], tuple[pd.DataFrame | None, str]] | None = None
    adopt_dataset: Callable[[pd.DataFrame, str], Awaitable[None]] | None = None
    return_to_classic: Callable[[], None] | None = None
    open_classic: Callable[[str], None] | None = None
    survey_root: Path | None = None
    project_root: Path | None = None
    store_language: Callable[[str], None] | None = None
    preparation: Callable[[], tuple[ft.Control, Callable]] | None = None


def workspace_settings_path() -> Path:
    """Where versions before Stage 37 kept the workspace's accent colour
    (beside the classic preferences file). Only read, once, when the settings
    file (``user_settings``) is made; never written again."""
    from app_preferences import preferences_path

    return preferences_path().parent / "workspace.json"


def load_workspace_settings() -> dict:
    """The old workspace.json (only read; see ``workspace_settings_path``)."""
    import json

    try:
        data = json.loads(workspace_settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _cell(value) -> str:
    """Display form of a data cell: blank for missing, 4 instead of 4.0."""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _level_options(ui: wc.Ui) -> list[tuple[str, str]]:
    return [(level, ui.t(f"level.{level}")) for level in LEVELS]


class WorkspaceApp:
    """The Stage 33 shell. ``mount()`` shows it on ``page``."""

    def __init__(self, page: ft.Page, *, bridge: ClassicBridge | None = None,
                 session: ResearchSession | None = None, language: str | None = None,
                 corners: str | None = None, survey_root: Path | None = None,
                 project_root: Path | None = None,
                 settings: "us.UserSettings | None" = None):
        """``language`` and ``corners`` apply only when the settings file holds
        none (a fresh installation): the researcher's saved choice wins."""
        from project_session import ProjectBinding

        self.page = page
        self.bridge = bridge or ClassicBridge()
        self.session = session or ResearchSession(language=language or "en",
                                                  corners=corners or "windows")
        self.survey_root = Path(survey_root or self.bridge.survey_root or (ROOT / "data" / "surveys"))
        self.project_root = Path(project_root or self.bridge.project_root
                                 or (self.survey_root.parent / "projects"))
        # Saves every change of the session into the open project; subscribed
        # before the chrome so the context bar shows the saved state.
        self.projects = ProjectBinding(self.session, self.project_root)
        # Before an in-app update closes the program, close the open project.
        import update_ui

        update_ui.register_before_exit(self.close_project_for_update)
        self._shown_project_message = None
        # Optional local researcher profile (beside the projects folder).
        from researcher_profile import load_profile, profile_path

        self.profile_path = profile_path(self.project_root.parent)
        self.profile = load_profile(self.profile_path)
        # Stage 37 (#68): one settings file beside the projects folder; the
        # first start of this version copies the older files' values into it
        # (D1: the language no longer depends on a researcher profile).
        if settings is None:
            from app_preferences import preferences_path

            settings = us.UserSettings.load(
                us.path_for(self.project_root.parent),
                legacy=us.LegacySources(preferences_path(), workspace_settings_path(),
                                        self.profile_path))
        self.settings = settings
        if settings.is_set("language"):
            # A language this version does not know is shown as English and
            # kept in the file; Russian is kept and shown.
            self.session.language = settings.get("language")
        if settings.is_set("corners"):
            self.session.corners = settings.get("corners")
        self.session.accent = settings.get("accent")
        self.theme_choice = settings.get("theme")          # light | dark | system
        self.session.theme = self._resolved_theme()
        self.text_scale = settings.get("text_scale")       # per cent
        self.density = settings.get("density")
        self.typeface = settings.get("typeface")
        tk.apply_density(self.density)
        self.area = "home"
        self.route = "home"          # sub-route (e.g. "import" under questionnaires)
        # Narrow windows start with the icon rail; the user's toggle wins, also
        # at the next start (D2).
        stored = settings.get("sidebar_expanded")
        self.sidebar_expanded = (stored if stored is not None else
                                 int(getattr(page, "width", None) or 1280) >= tk.BREAKPOINT_NARROW)
        # Where the researcher was when the program last closed (Home offers it).
        self.last_place = (settings.get("last_project"), settings.get("last_route"))
        self._focus_target: str | None = None
        self.pages: dict[str, object] = {}
        self.root: ft.Control | None = None
        self.status_text: ft.Text | None = None
        self.status_icon: ft.Icon | None = None
        # The page sits in a list so that Flet's keyed list reconciliation
        # applies (a single `content` field is always replaced wholesale).
        self._page_stack = ft.Column(expand=True, spacing=0)
        self.content_host = ft.Container(self._page_stack, expand=True)
        self.sidebar_host = ft.Container()
        self.context_host = ft.Container()
        self._classic_seen = None      # id() of the classic dataframe last exchanged
        self._handed_over = None       # id() of the workspace dataframe last handed over
        self._rendered_width = None
        self.last_folder: str | None = None   # the next save dialog opens here
        self.question_draft = ""      # research question without a project
        self._install_services()
        from workspace_analyze import AnalyzePage, ReportsPage, ResultsPage
        from workspace_charts import ChartStudioPage
        from workspace_projects import ProjectHub, ProjectPage
        from workspace_questionnaires import ImportPage, QuestionnairesPage
        from workspace_settings import SettingsPage

        self.hub = ProjectHub(self)

        self.pages = {
            "home": HomePage(self), "project": ProjectPage(self), "data": DataPage(self),
            "questionnaires": QuestionnairesPage(self), "import": ImportPage(self),
            "analyze": AnalyzePage(self), "results": ResultsPage(self),
            "reports": ReportsPage(self), "settings": SettingsPage(self),
            "help": HelpPage(self), "charts": ChartStudioPage(self),
        }
        self.session.subscribe(self._on_session_change)
        from survey_storage import get_survey

        self.session.questionnaire_loader = lambda survey_id: get_survey(self.survey_root,
                                                                         survey_id)

    # ------------------------------------------------------------ context
    @property
    def ui(self) -> wc.Ui:
        return wc.Ui(tk.palette(self.session.theme, self.session.accent), self.session.language,
                     self.session.corners, text_scale=self.text_scale / 100,
                     typeface=self.typeface)

    def t(self, key: str, **values) -> str:
        return self.ui.t(key, **values)

    @property
    def content_width(self) -> int:
        width = int(getattr(self.page, "width", None) or 1280)
        sidebar = tk.SIDEBAR_EXPANDED if self.sidebar_expanded else tk.SIDEBAR_COLLAPSED
        return max(360, width - sidebar - 2 * tk.SPACE_6)

    @property
    def compact(self) -> bool:
        return int(getattr(self.page, "width", None) or 1280) < tk.BREAKPOINT_COMPACT

    def constrained(self, content: ft.Control, max_width: int = tk.CONTENT_MAX_WIDTH) -> ft.Control:
        return ft.Row([ft.Container(content, width=min(max_width, self.content_width))],
                      alignment=ft.MainAxisAlignment.CENTER)

    # ------------------------------------------------------------- pickers
    def close_project_for_update(self) -> None:
        """Release the open project (its lock) before an in-app update."""
        self.projects.close(clear=False)

    def _install_services(self):
        self.data_picker = ft.FilePicker(on_result=self._on_data_picked)
        self.document_picker = ft.FilePicker(on_result=self._on_document_picked)
        self.save_picker = ft.FilePicker()
        for picker in (self.data_picker, self.document_picker, self.save_picker):
            self.page.services.append(picker)
        web = bool(getattr(self.page, "web", False))
        self.open_data_action = ft.PickFiles(
            self.data_picker, allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=DATA_EXTENSIONS, with_data=web)
        self.open_document_action = ft.PickFiles(
            self.document_picker, allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=DOCUMENT_EXTENSIONS, with_data=web)

    async def _on_data_picked(self, e):
        await self.import_files(getattr(e, "files", None))

    async def _on_document_picked(self, e):
        files = getattr(e, "files", None)
        if files:
            self.navigate("import")
            await self.pages["import"].open_files(files)

    async def open_data_dialog(self, e=None):
        """Keyboard path (Ctrl+O): Python-side picker call."""
        try:
            files = await self.data_picker.pick_files(
                allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=DATA_EXTENSIONS,
                with_data=bool(getattr(self.page, "web", False)))
        except Exception as error:  # pragma: no cover - client dependent
            self.status(self.t("data.load_failed", error=error), "danger")
            return
        await self.import_files(files)

    async def save_dialog(self, title: str, file_name: str, extension: str) -> str | None:
        return await self.save_picker.save_file(
            dialog_title=title, file_name=file_name, initial_directory=self.last_folder,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=[extension])

    async def save_file(self, title: str, file_name: str, extension: str, writer, *,
                        announce=None):
        """Ask where to save, write there and say what happened.

        ``writer(path)`` writes the file (in a worker thread) and may return
        the path it wrote. The outcome (cancelled, saved with the full path
        of the verified file, or an actionable explanation) is shown in the
        status bar and returned for the page to show next to the action;
        ``announce(path)`` may word the success message.
        """
        import workspace_files as wf

        since = wf.now()
        try:
            chosen = await self.save_dialog(title, file_name, extension)
        except Exception as error:  # pragma: no cover - client dependent
            outcome = wf.SaveOutcome(None, self.t("save.dialog_failed", reason=str(error)
                                                  or type(error).__name__), "danger")
            self.status(outcome.message, outcome.tone)
            return outcome
        if not chosen:
            outcome = wf.SaveOutcome(None, self.t("save.cancelled"), "info")
            self.status(outcome.message, outcome.tone)
            return outcome
        typed = Path(str(chosen)).expanduser()
        path = wf.with_extension(typed, extension)
        try:
            written = await asyncio.to_thread(wf.write_verified, path, writer)
        except Exception as error:
            outcome = wf.SaveOutcome(None, wf.explain(error, path, self.t), "danger")
        else:
            wf.remove_placeholder(typed, written, since)
            self.last_folder = str(written.parent)
            outcome = wf.SaveOutcome(
                written, announce(written) if announce else self.t("save.saved", path=written),
                "success")
        self.status(outcome.message, outcome.tone)
        return outcome

    # ------------------------------------------------------------ datasets
    async def import_files(self, files) -> bool:
        from import_workflow import import_picked_files

        async def from_bytes(data: bytes, name: str) -> bool:
            with TemporaryDirectory(prefix="workspace-import-") as temporary:
                path = Path(temporary) / Path(name).name
                path.write_bytes(data)
                return await self.load_path(str(path), display_name=name, remember=False,
                                            origin="upload")

        result = await import_picked_files(files, import_path=self.load_path,
                                           import_bytes=from_bytes)
        if not result.successful and not result.cancelled:
            self.status(result.message, "danger")
        return result.successful

    async def load_path(self, path: str, *, display_name: str | None = None,
                        options=None, remember: bool = True, origin: str | None = None) -> bool:
        from data_loader import ImportOptions, load_dataset_with_report

        try:
            df, report = await asyncio.to_thread(
                load_dataset_with_report, path, options or ImportOptions())
            self.session.set_dataset(df, display_name or Path(path).name, report=report,
                                     path=path if remember else None,
                                     origin=origin or ("file" if remember else "copy"))
        except Exception as error:
            self.status(self.t("data.load_failed", error=error), "danger")
            return False
        if remember:
            self._remember_file(path)
        self.status(self.t("data.loaded", name=self.session.source_name), "success")
        self.navigate("data")
        return True

    async def load_sample(self, name: str) -> bool:
        return await self.load_path(str(EXAMPLES / name), remember=False, origin="sample")

    def _remember_file(self, path: str):
        try:
            from app_preferences import AppPreferences, remember_file

            known = AppPreferences(recent_files=tuple(self.settings.get("recent_files")))
            self.settings.update(recent_files=list(remember_file(known, path).recent_files))
        except Exception:
            pass  # recent files are a convenience; never block an import

    def recent_files(self) -> list[str]:
        try:
            return [p for p in self.settings.get("recent_files") if Path(p).is_file()]
        except Exception:
            return []

    def adopt_classic_dataset(self):
        """On entry, take the classic dataset if it changed since last time."""
        if self.bridge.current_dataset is None:
            return
        df, name = self.bridge.current_dataset()
        if df is None or df.columns.empty or id(df) == self._classic_seen:
            return
        self._classic_seen = id(df)
        self.session.set_dataset(df.copy(deep=True), name or "Classic dataset", origin="classic")
        self._handed_over = id(self.session.df)

    async def hand_dataset_to_classic(self):
        """On exit, give the classic interface a dataset loaded here."""
        if self.bridge.adopt_dataset is None or not self.session.has_data:
            return
        if id(self.session.df) == self._handed_over:
            return
        await self.bridge.adopt_dataset(self.session.df.copy(deep=True),
                                        self.session.source_name)
        self._handed_over = id(self.session.df)
        if self.bridge.current_dataset is not None:
            self._classic_seen = id(self.bridge.current_dataset()[0])

    # --------------------------------------------------------- navigation
    def navigate(self, route: str, *, refresh: bool = True, section: str | None = None):
        """Open ``route``; ``section`` names a part of it (a research step such
        as "variables" or "method"), which the page scrolls to and the journey
        marks as current (Stage 36, D1)."""
        if route == "project" and not self.projects.active:
            route = "home"            # the project page needs an open project
        self.route = route
        self.section = section
        self.area = self.SUB_ROUTES.get(route, route)
        self._remember_place()
        if refresh:
            self.render()
            key = self.SECTION_KEYS.get((self.route, section or ""))
            if key is None and route == "settings" and section:
                from workspace_settings import section_key

                key = section_key(section)       # a section of the Settings hub
            if key and self.page is not None:
                try:
                    self.page.run_task(self._scroll_to_section, key)
                except Exception:    # no event loop (tests): the section is still marked
                    pass

    async def _scroll_to_section(self, key: str):
        control = self.page_control
        if control is not None:
            try:
                await control.scroll_to(scroll_key=key, duration=250)
            except Exception:
                pass

    @property
    def page_control(self) -> ft.Control | None:
        """The page currently on screen (its scroll container)."""
        return self._page_stack.controls[0] if self._page_stack.controls else None

    # Pages of a project that the next start offers to continue on (a page
    # that needs a choice made on screen continues on the page it belongs to).
    CONTINUE_ROUTES = {"project": "project", "data": "data", "analyze": "analyze",
                       "results": "results", "reports": "reports",
                       "questionnaires": "questionnaires", "import": "questionnaires",
                       "charts": "results"}

    def _remember_place(self) -> None:
        """Keep the open project and its page for the next start (D2). Pages
        seen without a project (Home, Settings, Help) leave the last place."""
        route = self.CONTINUE_ROUTES.get(self.route)
        if route is None or not self.projects.active:
            return
        try:
            self.settings.update(last_route=route, last_project=self.projects.info().id)
        except Exception:
            pass        # a convenience: never disturb the navigation

    def continue_place(self):
        """(project info, route) to continue from Home, or None: the project
        of the last session must still exist, not be open and not be archived."""
        project_id, route = self.last_place
        if not project_id or route not in self.CONTINUE_ROUTES or self.projects.active:
            return None
        try:
            info = next((i for i in self.projects.projects() if i.id == project_id), None)
        except Exception:
            return None
        if info is None or info.archived:
            return None
        return info, self.CONTINUE_ROUTES[route]

    async def continue_where_left(self, e=None):
        """Open the last project on the page the researcher was on (one click)."""
        place = self.continue_place()
        if place is None:
            return
        info, route = place
        self.last_place = (None, None)
        await self.hub.open(info.id, route=route)

    # Keyboard focus (U11): a main action that opens new content moves the
    # focus to what comes next, where Flet can move it.
    def request_focus(self, data: str, *, first_inside: bool = False) -> None:
        """Move the keyboard focus, after the next render, to the control
        ``data`` (or to the first focusable control inside it)."""
        self._focus_target = (data, first_inside)

    @staticmethod
    def _descendants(root):
        stack = [root]
        while stack:
            item = stack.pop()
            yield item
            for name in ("controls", "content", "actions"):
                child = getattr(item, name, None)
                if isinstance(child, list):
                    stack.extend(reversed(child))
                elif isinstance(child, ft.Control):
                    stack.append(child)

    def _apply_focus(self) -> None:
        request, self._focus_target = self._focus_target, None
        if not request:
            return
        target, first_inside = request
        holder = next((c for c in self._descendants(self._page_stack)
                       if getattr(c, "data", None) == target), None)
        if holder is None:
            return
        focusable = (ft.Button, ft.TextButton, ft.IconButton, ft.TextField, ft.Dropdown)
        if first_inside:
            control = next((c for c in self._descendants(holder) if c is not holder
                            and isinstance(c, focusable) and not getattr(c, "disabled", False)),
                           None)
        else:
            control = holder if isinstance(holder, focusable) else None
        if control is None:
            return
        self.focused = getattr(control, "data", None) or target
        control.autofocus = True              # a newly built control takes it itself
        try:
            self.page.run_task(control.focus)  # one rebuilt in place is told to
        except Exception:                     # no client (tests): recorded only
            pass

    focused: str | None = None                # what the last focus request reached

    # Saved as they are typed; nothing in the chrome shows them (Stage 36.8).
    QUIET_EVENTS = ("notes", "report_settings")

    def _on_session_change(self, what: str):
        # Context bar and sidebar badges follow the session.
        if self.root is not None and what not in self.QUIET_EVENTS:
            self._render_chrome()
        message = self.projects.message
        if message is not None and message is not self._shown_project_message:
            self._shown_project_message = message
            self.status(self.t(message[0]), message[1])

    # The research journey (Issue #32): where the researcher is, what is done.
    # Each research step opens its own place: Variables is the dictionary on
    # the Data page, Design and Method are steps 3 and 4 of the analysis.
    JOURNEY = (("question", "project"), ("data", "data"), ("variables", "data"),
               ("design", "analyze"), ("method", "analyze"), ("result", "results"),
               ("report", "reports"))
    JOURNEY_ROUTES = {"project": "question", "data": "data", "analyze": "design",
                      "results": "result", "reports": "report", "charts": "result"}
    # Pages that belong to an area of the sidebar (Chart Studio is part of Results).
    SUB_ROUTES = {"import": "questionnaires", "charts": "results"}
    SECTION_KEYS = {("data", "data"): "data-top", ("data", "variables"): "data-variables",
                    ("analyze", "design"): "step-design", ("analyze", "method"): "step-method",
                    ("analyze", "variables"): "step-variables",
                    ("analyze", "task-result"): "task-result",
                    ("project", "hypotheses"): "project-hypotheses",
                    ("settings", "ai"): "settings-ai"}
    section: str | None = None

    def journey_status(self) -> dict[str, bool]:
        s = self.session
        analyzed = bool(s.results)
        return {
            "question": bool(self.research_question()),
            "data": s.has_data,
            "variables": s.has_data and not s.pending_levels(),
            "design": analyzed, "method": analyzed, "result": analyzed,
            "report": bool(s.report_order),
        }

    def research_question(self) -> str:
        if self.projects.active:
            try:
                return self.projects.research_question()
            except Exception:
                return ""
        return self.question_draft

    def _journey(self) -> ft.Control:
        ui = self.ui
        status = self.journey_status()
        current = self.JOURNEY_ROUTES.get(self.route)
        steps = {key for key, route in self.JOURNEY if route == self.route}
        if self.section in steps:
            current = self.section             # the step the researcher opened
        elif current == "data" and self.session.has_data and self.session.pending_levels():
            current = "variables"
        chips = []
        for number, (key, route) in enumerate(self.JOURNEY, start=1):
            done = status[key]
            tone = "info" if key == current else "success" if done else "neutral"
            target = route if route != "project" or self.projects.active else "home"
            chips.append(wc.chip(
                ui, f"{number}. {ui.t('journey.' + key)}", tone,
                icon=ft.Icons.CHECK_CIRCLE if done else (
                    ft.Icons.ARROW_CIRCLE_RIGHT if key == current else ft.Icons.CIRCLE_OUTLINED),
                tooltip=ui.t("journey." + key + ".tip"),
                on_click=lambda e, r=target, k=key: self.navigate(r, section=k),
                data=f"journey-{key}"))
        return ft.Row(chips, wrap=True, spacing=tk.SPACE_1, data="journey")

    def render(self):
        if self.root is None:
            return
        self._render_chrome()
        page = self.pages[self.route]
        try:
            body = page.build()
        except Exception as error:  # a page bug must not blank the window
            body = wc.notice(self.ui, f"{type(error).__name__}: {error}", "danger",
                             title=self.t("page.failed"))
        if self.route in self.JOURNEY_ROUTES:
            body = ft.Column([self.constrained(self._journey()), body], spacing=tk.SPACE_3,
                             horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        # A stable key per route makes Flet reconcile the rebuilt page with the
        # one on screen (same control identities) instead of replacing it, so
        # the scroll position, keyboard focus, caret and expanded sections
        # survive a re-render; another route gets a fresh page.
        controls: list[ft.Control] = [ft.Column(
            [body], scroll=ft.ScrollMode.AUTO, expand=True,
            data=f"workspace-page-{self.route}", key=f"workspace-page-{self.route}",
        )]
        # A page may keep its main actions on screen below the scrolling
        # content (the import review's sticky footer).
        footer = page.footer() if hasattr(page, "footer") else None
        if footer is not None:
            controls.append(ft.Container(footer, key=f"workspace-footer-{self.route}",
                                         data="workspace-footer"))
        self._page_stack.controls = controls
        self.content_host.bgcolor = self.ui.p.canvas
        self.root.bgcolor = self.ui.p.canvas
        self._rendered_width = int(getattr(self.page, "width", None) or 1280)
        self.page.update()
        self._apply_focus()

    def scroll_page(self, delta: float) -> None:
        """Scroll the page on screen by ``delta`` pixels (negative: up)."""
        column = self.page_control
        if column is None or not delta:
            return
        try:
            self.page.run_task(column.scroll_to, delta=delta, duration=0)
        except Exception:  # pragma: no cover - no page on screen
            pass

    def reveal(self, key: str) -> None:
        """Scroll the page on screen to the control with ``ft.ScrollKey(key)``
        (an item reached with the keyboard, or restored after a restart)."""
        column = self.page_control
        if column is None:
            return
        try:
            self.page.run_task(column.scroll_to, scroll_key=key, duration=150)
        except Exception:  # pragma: no cover - no page on screen
            pass

    def _render_chrome(self):
        self.sidebar_host.content = self._sidebar()
        self.context_host.content = self._context_bar()

    def status(self, message: str, tone: str = "info"):
        if self.status_text is None:
            return
        _, fg, icon = wc.TONES[tone]
        wc.set_text(self.status_text, message)
        self.status_text.color = self.ui.p.text
        self.status_icon.name = icon
        self.status_icon.color = getattr(self.ui.p, fg)
        self.status_icon.visible = bool(message)
        try:
            self.page.update()
        except Exception:
            pass

    # ------------------------------------------------------------- chrome
    def _apply_theme(self) -> None:
        """Themes, typeface, text size and density on the page (Stage 37)."""
        tk.apply_density(self.density)
        self.session.theme = self._resolved_theme()
        options = dict(typeface=self.typeface, text_scale=self.text_scale / 100,
                       density=self.density)
        self.page.theme = tk.build_theme("light", self.session.accent, **options)
        self.page.dark_theme = tk.build_theme("dark", self.session.accent, **options)
        self.page.theme_mode = {"dark": ft.ThemeMode.DARK, "system": ft.ThemeMode.SYSTEM}.get(
            self.theme_choice, ft.ThemeMode.LIGHT)
        self.page.bgcolor = self.ui.p.canvas

    def _resolved_theme(self) -> str:
        """light or dark; "system" follows Windows' app mode."""
        if self.theme_choice in ("light", "dark"):
            return self.theme_choice
        brightness = getattr(self.page, "platform_brightness", None)
        return "dark" if getattr(brightness, "value", brightness) == "dark" else "light"

    def _on_brightness(self, e=None):
        if self.theme_choice == "system":
            self.session.theme = self._resolved_theme()
            self.page.bgcolor = self.ui.p.canvas
            self.render()

    def build(self) -> ft.Control:
        self._apply_theme()
        ui = self.ui
        self.status_icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=16, visible=False)
        self.status_text = ft.Text("", size=ui.size(13), color=ui.p.text, selectable=True,
                                   data="workspace-status")
        status_bar = ft.Container(
            content=ft.Semantics(
                live_region=True,
                content=ft.Row([self.status_icon, self.status_text], spacing=tk.SPACE_2),
            ),
            padding=ft.Padding.symmetric(horizontal=tk.SPACE_5, vertical=tk.SPACE_1 + 2),
            bgcolor=ui.p.surface, border=ft.Border(top=ft.BorderSide(1, ui.p.border)),
        )
        main = ft.Column(
            [self.context_host,
             ft.Container(self.content_host, expand=True,
                          padding=ft.Padding.symmetric(horizontal=tk.SPACE_6,
                                                       vertical=tk.SPACE_5)),
             status_bar],
            spacing=0, expand=True,
        )
        self.root = ft.Container(
            content=ft.Row([self.sidebar_host, main], spacing=0, expand=True,
                           vertical_alignment=ft.CrossAxisAlignment.STRETCH),
            expand=True, bgcolor=ui.p.canvas, data="workspace-root",
        )
        self._render_chrome()
        return self.root

    def mount(self):
        """Replace the page content with the workspace (one update)."""
        global _ACTIVE
        _ACTIVE = weakref.ref(self)
        root = self.build()
        self.page.controls.clear()
        self.page.add(root)
        self.page.on_keyboard_event = self.on_keyboard
        if hasattr(self.page, "on_resize"):
            self.page.on_resize = self._on_resize
        if hasattr(self.page, "on_platform_brightness_change"):
            self.page.on_platform_brightness_change = self._on_brightness
        self.adopt_classic_dataset()
        self.render()

    def _on_resize(self, e=None):
        """Re-layout only when the width changes enough to matter."""
        width = int(getattr(self.page, "width", None) or 1280)
        last = self._rendered_width or 0
        crossed = any((last < b) != (width < b) for b in
                      (tk.BREAKPOINT_NARROW, tk.BREAKPOINT_COMPACT, 1600))
        if crossed or abs(width - last) >= 96:
            self.render()

    def _nav_item(self, key: str, icon, label: str, *, selected: bool, on_click,
                  badge: str | None = None) -> ft.Control:
        ui = self.ui
        expanded = self.sidebar_expanded
        fg = ui.p.on_accent_subtle if selected else ui.p.text_secondary
        row = [ft.Icon(icon, size=20, color=ui.p.accent if selected else ui.p.text_secondary)]
        if expanded:
            row.append(ft.Text(label, size=ui.size(14), color=fg, expand=True,
                               weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500,
                               max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
            if badge:
                row.append(ft.Container(
                    ft.Text(badge, size=ui.size(12), color=ui.p.on_accent_subtle),
                    bgcolor=ui.p.accent_subtle if not selected else ui.p.surface,
                    border_radius=10, padding=ft.Padding.symmetric(horizontal=6, vertical=1)))
        indicator = ft.Container(width=3, height=20, border_radius=2,
                                 bgcolor=ui.p.accent if selected else ui.p.surface_alt)
        return ft.TextButton(
            content=ft.Row([indicator, *row], spacing=tk.SPACE_3,
                           vertical_alignment=ft.CrossAxisAlignment.CENTER),
            on_click=on_click, data=f"nav-{key}",
            tooltip=None if expanded else label,
            height=tk.CONTROL_HEIGHT,
            style=ft.ButtonStyle(
                bgcolor={ft.ControlState.DEFAULT: ui.p.accent_subtle if selected
                         else ui.p.surface_alt,
                         ft.ControlState.HOVERED: ui.p.accent_subtle if selected
                         else ui.p.surface_hover},
                shape=ft.RoundedRectangleBorder(radius=ui.radius("control")),
                padding=ft.Padding.only(left=0, right=tk.SPACE_3),
            ),
        )

    def _sidebar(self) -> ft.Control:
        ui = self.ui
        icons = {
            "home": ft.Icons.HOME_OUTLINED, "data": ft.Icons.TABLE_CHART_OUTLINED,
            "questionnaires": ft.Icons.ASSIGNMENT_OUTLINED, "analyze": ft.Icons.QUERY_STATS,
            "results": ft.Icons.INSIGHTS_OUTLINED, "reports": ft.Icons.DESCRIPTION_OUTLINED,
        }
        badges = {
            "results": str(len(self.session.results)) if self.session.results else None,
            "reports": str(len(self.session.report_order)) if self.session.report_order else None,
        }
        items = [
            self._nav_item(key, icons[key], ui.t(f"nav.{key}"), selected=self.area == key,
                           on_click=lambda e, k=key: self.navigate(k), badge=badges.get(key))
            for key in AREAS
        ]
        if self.projects.active:
            # The open project's own page, right under Home.
            items.insert(1, self._nav_item(
                "project", ft.Icons.FOLDER_OUTLINED, ui.t("nav.project"),
                selected=self.area == "project", on_click=lambda e: self.navigate("project")))
        bottom = [
            self._nav_item("settings", ft.Icons.SETTINGS_OUTLINED, ui.t("nav.settings"),
                           selected=self.area == "settings",
                           on_click=lambda e: self.navigate("settings")),
            self._nav_item("help", ft.Icons.HELP_OUTLINE, ui.t("nav.help"),
                           selected=self.area == "help",
                           on_click=lambda e: self.navigate("help")),
        ]
        if self.bridge.return_to_classic is not None:
            bottom.append(self._nav_item(
                "classic", ft.Icons.SWAP_HORIZ, ui.t("nav.classic"), selected=False,
                on_click=self.return_to_classic))
        toggle = wc.icon_button(
            ui, ft.Icons.MENU_OPEN if self.sidebar_expanded else ft.Icons.MENU,
            ui.t("nav.collapse") if self.sidebar_expanded else ui.t("nav.expand"),
            on_click=lambda e: self.toggle_sidebar(), data="nav-toggle")
        brand_children: list[ft.Control] = [
            ft.Container(ft.Icon(ft.Icons.INSIGHTS, color=ui.p.on_accent, size=18),
                         bgcolor=ui.p.accent, width=32, height=32, border_radius=8,
                         alignment=ft.Alignment.CENTER),
        ]
        if self.sidebar_expanded:
            brand_children.append(ft.Column(
                [ft.Text(ui.t("app.name"), size=ui.size(13), weight=ft.FontWeight.W_600,
                         color=ui.p.text, max_lines=2)],
                spacing=2, expand=True))
        brand = ft.Row(brand_children, spacing=tk.SPACE_3,
                       vertical_alignment=ft.CrossAxisAlignment.START)
        width = tk.SIDEBAR_EXPANDED if self.sidebar_expanded else tk.SIDEBAR_COLLAPSED
        return ft.Container(
            content=ft.Column(
                [ft.Row([toggle], alignment=ft.MainAxisAlignment.START), brand,
                 ft.Container(height=tk.SPACE_2),
                 ft.Column(items, spacing=2),
                 ft.Container(expand=True),
                 wc.divider(ui),
                 ft.Column(bottom, spacing=2)],
                spacing=tk.SPACE_2, expand=True,
            ),
            width=width, bgcolor=ui.p.surface_alt,
            border=ft.Border(right=ft.BorderSide(1, ui.p.border)),
            padding=ft.Padding.symmetric(horizontal=tk.SPACE_2 + 2, vertical=tk.SPACE_3),
            data="workspace-sidebar",
        )

    def _context_bar(self) -> ft.Control:
        ui = self.ui
        s = self.session
        left: list[ft.Control] = [self._project_chip()]
        if s.has_data:
            rows, cols = len(s.df), len(s.df.columns)
            left.append(wc.chip(
                ui, f"{s.source_name} · {count_text(ui.language, rows, 'rows')} · "
                f"{count_text(ui.language, cols, 'variables')}", "neutral",
                icon=ft.Icons.TABLE_CHART_OUTLINED, tooltip=ui.t("context.open_data_tip"),
                on_click=lambda e: self.navigate("data"), data="context-dataset"))
            pending = s.pending_levels()
            if pending:
                left.append(wc.chip(ui, ui.t("context.levels_pending", count=pending), "warning",
                                    icon=ft.Icons.RULE, on_click=lambda e: self.navigate("data"),
                                    data="context-pending"))
        else:
            left.append(wc.chip(ui, ui.t("context.no_data"), "neutral",
                                icon=ft.Icons.TABLE_CHART_OUTLINED,
                                on_click=lambda e: self.navigate("data"),
                                data="context-dataset"))
        # Stage 37 (#68): EN and LV as quick choices; every language, Russian
        # included, in the globe menu beside them and in Settings.
        language = ft.Semantics(
            label=ui.t("context.language"), container=True,
            content=wc.segmented(
                ui, [(code, code.upper()) for code in us.QUICK_LANGUAGES], ui.language,
                self.set_language,
                tooltips={code: us.LANGUAGE_NAMES[code] for code in us.QUICK_LANGUAGES},
                compact=True, data="context-language"))
        languages = self._language_menu()
        theme = wc.icon_button(
            ui, ft.Icons.DARK_MODE_OUTLINED if s.theme == "light" else ft.Icons.LIGHT_MODE_OUTLINED,
            ui.t("context.theme_dark") if s.theme == "light" else ui.t("context.theme_light"),
            on_click=lambda e: self.toggle_theme(), data="context-theme")
        right = [
            wc.chip(ui, ui.t("context.local"), "success", icon=ft.Icons.LOCK_OUTLINE,
                    tooltip=ui.t("context.local_tip"), data="context-local"),
            theme, language, languages,
        ]
        return ft.Container(
            content=ft.Row(
                [ft.Row(left, spacing=tk.SPACE_2, expand=True, wrap=True),
                 ft.Row(right, spacing=tk.SPACE_2)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=tk.CONTEXT_BAR_HEIGHT + 8, bgcolor=ui.p.surface,
            padding=ft.Padding.symmetric(horizontal=tk.SPACE_5, vertical=tk.SPACE_2),
            border=ft.Border(bottom=ft.BorderSide(1, ui.p.border)),
            data="workspace-context",
        )

    def _language_menu(self) -> ft.Control:
        """The globe: every interface language (a tick on the current one) and
        the language settings. Its name says the current language."""
        ui = self.ui
        items = [ft.PopupMenuItem(content=us.LANGUAGE_NAMES[code], checked=code == ui.language,
                                  on_click=lambda e, c=code: self.set_language(c),
                                  data=f"context-language-menu-{code}")
                 for code in us.LANGUAGES]
        items.append(ft.PopupMenuItem())       # a divider
        items.append(ft.PopupMenuItem(content=ui.t("context.language_settings"),
                                      icon=ft.Icons.SETTINGS_OUTLINED,
                                      on_click=lambda e: self.navigate("settings",
                                                                       section="language"),
                                      data="context-language-menu-settings"))
        name = us.LANGUAGE_NAMES.get(ui.language, us.LANGUAGE_NAMES["en"])
        return ft.PopupMenuButton(
            icon=ft.Icons.LANGUAGE, items=items, data="context-language-menu",
            tooltip=ui.t("context.language_menu", name=name),
            icon_color=ui.p.text_secondary, icon_size=20,
            menu_position=ft.PopupMenuPosition.UNDER)

    def _project_chip(self) -> ft.Control:
        ui = self.ui
        info = self.projects.info() if self.projects.active else None
        if info is None:
            return wc.chip(ui, ui.t("context.no_project"), "neutral", icon=ft.Icons.FOLDER_OFF_OUTLINED,
                           tooltip=ui.t("context.no_project_tip"),
                           on_click=lambda e: self.navigate("home"), data="context-project")
        stale = self.projects.stale_count()
        return wc.chip(ui, ui.t("context.project", title=info.title), "warning" if stale else "info",
                       icon=ft.Icons.FOLDER_OUTLINED, tooltip=ui.t("context.project_tip"),
                       on_click=lambda e: self.navigate("project"), data="context-project")

    # ------------------------------------------------------------ actions
    def _save(self, **changes) -> None:
        """Keep a choice for the next start; say so if the file cannot be written."""
        if not self.settings.update(**changes):
            self.status(self.t("settings.not_saved", error=self.settings.error or ""), "warning")

    def toggle_sidebar(self):
        self.sidebar_expanded = not self.sidebar_expanded
        self._save(sidebar_expanded=self.sidebar_expanded)
        self.render()

    def toggle_theme(self):
        """Ctrl+Shift+L and the moon/sun button: the other of light and dark."""
        self.set_theme("dark" if self.session.theme == "light" else "light")

    def set_theme(self, choice: str):
        """light, dark or system (Windows' app mode); kept for the next start."""
        if choice not in us.THEMES:
            return
        self.theme_choice = choice
        self._save(theme=choice)
        self._apply_theme()
        self.render()

    def set_language(self, language: str, *, render: bool = True):
        """The interface language, kept for the next start without a profile
        (D1); Russian is offered in the globe menu and in Settings."""
        if language not in us.LANGUAGES:
            return
        self.session.language = language
        self._save(language=language)
        if self.bridge.store_language is not None:
            self.bridge.store_language(language)
        if self.profile.language and self.profile.language != language:
            # The profile's language is the interface language; keep them equal.
            from dataclasses import replace

            from researcher_profile import save_profile

            try:
                self.profile = save_profile(self.profile_path,
                                            replace(self.profile, language=language))
            except (OSError, ValueError):
                pass
        if render:
            self.render()

    def set_corners(self, corners: str):
        if corners in us.CORNERS:
            self.session.corners = corners
            self._save(corners=corners)
            self.render()

    def set_accent(self, accent: str):
        """Change the accent colour preset; kept for the next start."""
        if accent not in tk.ACCENTS:
            return
        self.session.accent = accent
        self._save(accent=accent)
        self._apply_theme()
        self.render()

    def set_text_scale(self, value) -> None:
        """Text size 90/100/110/125 %: every token-sized text (wc.text and the
        components) and the theme's text; the chrome is rebuilt."""
        value = int(value)
        if value not in us.TEXT_SCALES:
            return
        self.text_scale = value
        self._save(text_scale=value)
        self._rebuild()

    def set_density(self, value: str) -> None:
        """Comfortable or compact spacing and control heights."""
        if value not in us.DENSITIES:
            return
        self.density = value
        self._save(density=value)
        self._rebuild()

    def set_typeface(self, value: str) -> None:
        if value not in us.TYPEFACES:
            return
        self.typeface = value
        self._save(typeface=value)
        self._rebuild()

    def set_start_interface(self, value: str) -> None:
        """Which interface opens at the next start (the workspace by default)."""
        if value not in us.START_INTERFACES:
            return
        self._save(start_interface=value)
        self.render()

    def reset_settings(self) -> None:
        """Every setting back to its default; research data is not touched."""
        if not self.settings.reset():
            self.status(self.t("settings.not_saved", error=self.settings.error or ""), "warning")
            return
        s = self.settings
        self.session.language = s.get("language")
        self.session.corners = s.get("corners")
        self.session.accent = s.get("accent")
        self.theme_choice = s.get("theme")
        self.text_scale, self.density, self.typeface = (
            s.get("text_scale"), s.get("density"), s.get("typeface"))
        self.last_place = (None, None)
        self._rebuild()
        self.status(self.t("settings.reset_done"), "success")

    def _rebuild(self) -> None:
        """Build the chrome again (sizes changed) and show the same page."""
        if self.root is None:
            return
        self.mount()

    async def return_to_classic(self, e=None):
        if self.bridge.return_to_classic is None:
            return
        await self.hand_dataset_to_classic()
        self.bridge.return_to_classic()

    async def on_keyboard(self, e: ft.KeyboardEvent):
        key = (e.key or "").upper()
        if e.ctrl and not e.alt and key in {str(i) for i in range(1, 7)}:
            self.navigate(AREAS[int(key) - 1])
        elif e.ctrl and key == "B":
            self.toggle_sidebar()
        elif e.ctrl and key == "O":
            await self.open_data_dialog()
        elif e.ctrl and e.shift and key == "L":
            self.toggle_theme()
        elif e.ctrl and key == "ENTER" and self.route == "analyze":
            await self.pages["analyze"].run_current()
        elif self.route == "import" and self.pages["import"].shortcut(e):
            pass        # items step: F8 / Shift+F8, F9, Alt+↓ / Alt+↑ (never text keys)
        elif key == "F1":
            self.navigate("help")


# =================================================================== pages
class HomePage:
    def __init__(self, app: WorkspaceApp):
        self.app = app
        # Experienced researchers (optional profile) start without the introduction.
        self.hide_onboarding = app.profile.experience == "experienced"

    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        s = app.session
        cols = {"xs": 12, "md": 6, "xl": 3}
        tiles = ft.ResponsiveRow(controls=[
            wc.action_tile(ui, ft.Icons.TABLE_CHART_OUTLINED, ui.t("home.analyze.title"),
                           ui.t("home.analyze.body"), ui.t("home.analyze.button"),
                           action=app.open_data_action, primary=True, col=cols,
                           data="home-open-data"),
            wc.action_tile(ui, ft.Icons.EDIT_NOTE, ui.t("home.build.title"),
                           ui.t("home.build.body"), ui.t("home.build.button"),
                           on_click=lambda e: app.navigate("questionnaires"), col=cols,
                           data="home-build"),
            wc.action_tile(ui, ft.Icons.DOCUMENT_SCANNER_OUTLINED, ui.t("home.import.title"),
                           ui.t("home.import.body"), ui.t("home.import.button"),
                           action=app.open_document_action, col=cols, data="home-import"),
            wc.action_tile(ui, ft.Icons.SCIENCE_OUTLINED, ui.t("home.sample.title"),
                           ui.t("home.sample.body"), ui.t("home.sample.button"),
                           on_click=self._sample, col=cols, data="home-sample"),
        ], spacing=tk.SPACE_4, run_spacing=tk.SPACE_4)
        self._equalize(tiles)
        continue_cards: list[ft.Control] = []
        if s.has_data:
            pending = s.pending_levels()
            continue_cards.append(wc.card(ui, [
                wc.text(ui, s.source_name, tk.TYPE_BODY, weight=ft.FontWeight.W_600),
                wc.caption(ui, f"{count_text(ui.language, len(s.df), 'rows')} · "
                               f"{count_text(ui.language, len(s.df.columns), 'variables')}"),
                *([wc.chip(ui, ui.t("context.levels_pending", count=pending), "warning")]
                  if pending else []),
            ], title=ui.t("home.current"), actions=[
                wc.button(ui, ui.t("home.current_open"), lambda e: app.navigate("data")),
                wc.button(ui, ui.t("home.current_analyze"), lambda e: app.navigate("analyze"),
                          kind="primary"),
            ], col={"xs": 12, "lg": 4}, data="home-current"))
        recent = app.recent_files()[:5]
        def opener(path):
            async def open_recent(e):
                await app.load_path(path)
            return open_recent

        recent_rows: list[ft.Control] = [
            wc.button(ui, Path(path).name, opener(path), kind="quiet", icon=ft.Icons.HISTORY,
                      tooltip=path)
            for path in recent
        ] or [wc.caption(ui, ui.t("home.recent_none"))]
        continue_cards.append(wc.card(
            ui, recent_rows + [wc.caption(ui, ui.t("home.recent_note"))],
            title=ui.t("home.recent"), col={"xs": 12, "md": 6, "lg": 4}, data="home-recent"))
        surveys = self._saved_surveys()
        survey_rows: list[ft.Control] = [
            ft.Row([ft.Icon(ft.Icons.ASSIGNMENT_OUTLINED, size=18, color=ui.p.text_secondary),
                    wc.text(ui, title, max_lines=1),
                    wc.caption(ui, count_text(ui.language, count, "responses"))],
                   spacing=tk.SPACE_2)
            for title, count in surveys[:5]
        ] or [wc.caption(ui, ui.t("home.saved_none"))]
        continue_cards.append(wc.card(
            ui, survey_rows, title=ui.t("home.saved"), col={"xs": 12, "md": 6, "lg": 4},
            actions=[wc.button(ui, ui.t("nav.questionnaires"),
                               lambda e: app.navigate("questionnaires"), kind="quiet")],
            data="home-saved"))
        how = []
        if not self.hide_onboarding:
            steps = ft.ResponsiveRow([
                ft.Container(ft.Column([
                    ft.Row([ft.Container(wc.text(ui, str(i), tk.TYPE_LABEL, color=ui.p.accent,
                                                 weight=ft.FontWeight.W_700),
                                         width=24, height=24, border_radius=12,
                                         bgcolor=ui.p.accent_subtle,
                                         alignment=ft.Alignment.CENTER),
                            wc.text(ui, ui.t(f"home.how{i}.title"), tk.TYPE_LABEL,
                                    weight=ft.FontWeight.W_600)], spacing=tk.SPACE_2),
                    wc.text(ui, ui.t(f"home.how{i}.body"), tk.TYPE_BODY,
                            color=ui.p.text_secondary),
                ], spacing=tk.SPACE_2), col={"xs": 12, "sm": 6, "lg": 3})
                for i in range(1, 5)
            ], spacing=tk.SPACE_5, run_spacing=tk.SPACE_4)
            how = [wc.card(ui, [steps], title=ui.t("home.how"), actions=[
                wc.button(ui, ui.t("common.close"), self._hide, kind="quiet")],
                data="home-how")]
        body = ft.Column([
            wc.page_header(ui, ui.t("home.title"), ui.t("home.subtitle")),
            *self._continue(),
            tiles,
            *how,
            ft.Column(app.hub.section(), spacing=tk.SPACE_3, data="home-projects",
                      horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            wc.heading(ui, ui.t("home.continue"), tk.TYPE_TITLE_M),
            ft.ResponsiveRow(continue_cards, spacing=tk.SPACE_4, run_spacing=tk.SPACE_4),
            wc.notice(ui, ui.t("home.privacy"), "neutral", data="home-privacy"),
        ], spacing=tk.SPACE_5, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        return app.constrained(body)

    def _continue(self) -> list[ft.Control]:
        """Stage 37 (#68): back to the project and page of the last session,
        in one click (the project is never reopened without asking)."""
        app, ui = self.app, self.app.ui
        place = app.continue_place()
        if place is None:
            return []
        info, route = place
        page = ui.t(f"nav.{route}") if f"nav.{route}" in _NAV_KEYS else ui.t("nav.project")
        return [wc.notice(ui, ui.t("home.continue_body", title=info.title, page=page), "info",
                          title=ui.t("home.continue_title"), actions=[
                              wc.button(ui, ui.t("home.continue_button", page=page),
                                        app.continue_where_left, kind="primary",
                                        icon=ft.Icons.PLAY_ARROW_OUTLINED,
                                        data="home-continue")],
                          data="home-continue-card")]

    def _equalize(self, tiles: ft.ResponsiveRow) -> None:
        """Same height for every start tile, estimated from the longest text.

        Flet's ResponsiveRow cannot stretch children to a common height, so
        the tallest tile's text decides; LV/RU text gets the room it needs.
        """
        import math

        page_width = int(getattr(self.app.page, "width", None) or 1280)
        columns = 4 if page_width >= 1200 else 2 if page_width >= 768 else 1
        if columns == 1:
            return
        width = (self.app.content_width - tk.SPACE_4 * (columns - 1)) / columns
        per_line = max(18, (width - 2 * tk.SPACE_5) / (7.6 * self.app.text_scale / 100))
        longest = 0
        for tile in tiles.controls:
            texts = [c for c in tile.content.controls if isinstance(c, ft.Text)]
            body = len(texts[-1].value) if texts else 0
            title = len(texts[0].value) if texts else 0
            lines = math.ceil(body / per_line) + 24 * (math.ceil(title * 1.25 / per_line) - 1) / 20
            longest = max(longest, lines)
        line = 20 * self.app.text_scale / 100
        height = (2 * tk.SPACE_5 + 40 + 24 * self.app.text_scale / 100 + tk.CONTROL_HEIGHT
                  + 4 * tk.SPACE_3 + tk.SPACE_1 + line * longest + 4)
        for tile in tiles.controls:
            tile.height = int(height)

    def _saved_surveys(self) -> list[tuple[str, int]]:
        try:
            from survey_storage import list_surveys, response_count

            return [(s.title, response_count(self.app.survey_root, s.survey_id))
                    for s in list_surveys(self.app.survey_root)]
        except Exception:
            return []

    async def _sample(self, e=None):
        await self.app.load_sample("sample_scale.csv")

    def _hide(self, e=None):
        self.hide_onboarding = True
        self.app.render()


class DataPage:
    PREVIEW_ROWS = 12

    def __init__(self, app: WorkspaceApp):
        self.app = app
        self.show_preparation = False
        self.accept_checked = False
        self.opened: set[str] = set()
        self.sample = SAMPLES[0][0]
        self._preparation = None
        from workspace_groups import GroupsCard

        self.groups = GroupsCard(app)      # Stage 36.3: groups from a scale
        self.options = {"sheet": None, "header_row": "1", "data_start": "", "separator": "auto",
                        "decimal": "auto", "encoding": "auto", "missing": "NA;N/A;NULL"}

    def build(self) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        header = wc.page_header(ui, ui.t("data.title"), ui.t("data.subtitle"), actions=[
            wc.button(ui, ui.t("data.open"), action=app.open_data_action, kind="primary",
                      icon=ft.Icons.FOLDER_OPEN, data="data-open"),
        ])
        if not s.has_data:
            return app.constrained(ft.Column([
                header,
                wc.empty_state(ui, ft.Icons.TABLE_CHART_OUTLINED, ui.t("data.empty.title"),
                               ui.t("data.empty.body"), actions=[
                                   wc.button(ui, ui.t("data.open"), action=app.open_data_action,
                                             kind="primary"),
                               ], data="data-empty"),
                self._sample_picker(),
                self._path_fallback(),
            ], spacing=tk.SPACE_5))
        df = s.df
        if app.projects.active:
            # Every dataset of the project stays available; this one is in use.
            datasets = app.projects.project.datasets()
            if len(datasets) > 1:
                header.controls[1].controls.insert(0, wc.dropdown(
                    ui, ui.t("source.in_use"), [(d.id, d.name) for d in datasets],
                    app.projects.dataset_id,
                    on_select=self._on_source, width=300,
                    data="data-source"))
        stats = ft.ResponsiveRow([
            wc.stat(ui, ui.t("data.source"), s.source_name, col={"xs": 12, "md": 6, "lg": 3}),
            wc.stat(ui, ui.t("data.rows"), str(len(df)), col={"xs": 6, "md": 3, "lg": 3}),
            wc.stat(ui, ui.t("data.variables"), str(len(df.columns)),
                    col={"xs": 6, "md": 3, "lg": 3}),
            wc.stat(ui, ui.t("data.missing"), str(s.missing_cells()),
                    col={"xs": 12, "md": 6, "lg": 3}),
        ], spacing=tk.SPACE_3, run_spacing=tk.SPACE_3)
        return app.constrained(ft.Column([
            ft.Container(header, key=ft.ScrollKey("data-top")), stats, self._next_step(),
            ft.Container(self._dictionary(), key=ft.ScrollKey("data-variables")),
            ft.Container(self.groups.build(), key=ft.ScrollKey("data-groups")), self._preview(),
            self._import_options(), self._preparation_card(), self._sample_picker(),
        ], spacing=tk.SPACE_5, horizontal_alignment=ft.CrossAxisAlignment.STRETCH))

    async def _on_source(self, e):
        await self._use_source(e.control.value)

    async def _use_source(self, dataset_id: str | None):
        if dataset_id and dataset_id != self.app.projects.dataset_id:
            await self.app.pages["project"].use(dataset_id)

    def _next_step(self) -> ft.Control:
        """What to do with this dataset now: confirm levels, then analyze."""
        app, ui, s = self.app, self.app.ui, self.app.session
        pending, total = s.pending_levels(), len(s.variables)
        if pending:
            return wc.notice(ui, ui.t("data.next_levels_body", count=pending, total=total), "info",
                             title=ui.t("next.levels"), data="data-next")
        return wc.notice(ui, ui.t("data.next_analyze_body", total=total), "success",
                         title=ui.t("next.analyze"), actions=[
                             wc.button(ui, ui.t("next.choose_analysis"),
                                       lambda e: app.navigate("analyze"), kind="primary",
                                       icon=ft.Icons.QUERY_STATS, data="data-next-analyze")],
                         data="data-next")

    # ------------------------------------------------------------ dictionary
    def _dictionary(self) -> ft.Control:
        ui, s = self.app.ui, self.app.session
        columns = [ui.t("data.col.variable"), ui.t("data.col.storage"),
                   ui.t("data.col.values"), ui.t("data.col.suggested"),
                   ui.t("data.col.level"), ui.t("data.col.missing"),
                   ui.t("data.col.distinct")]
        rows = []
        for info in s.variables.values():
            level = wc.dropdown(ui, "", _level_options(ui), info.confirmed,
                                on_select=lambda e, n=info.name: self._confirm(n, e.control.value),
                                width=230, data=f"level-{info.name}")
            level.label = None
            level.tooltip = ui.t("design.level_of", name=info.name)
            level.dense = True
            suggestion = ui.t(f"level.{info.suggested}")
            if info.binary:
                suggestion += f" · {ui.t('level.binary')}"
            rows.append(ft.DataRow(cells=[
                ft.DataCell(wc.text(ui, info.name, weight=ft.FontWeight.W_600, selectable=True)),
                ft.DataCell(wc.text(ui, ui.t(f"storage.{info.storage}"),
                                    color=ui.p.text_secondary)),
                ft.DataCell(wc.text(ui, s.value_summary(info.name, ui.language),
                                    color=ui.p.text_secondary,
                                    max_lines=2, data=f"values-{info.name}")),
                ft.DataCell(wc.text(ui, suggestion, color=ui.p.text_secondary)),
                ft.DataCell(level),
                ft.DataCell(wc.text(ui, str(info.missing))),
                ft.DataCell(wc.text(ui, str(info.distinct))),
            ]))
        table = ft.DataTable(
            columns=[ft.DataColumn(wc.text(ui, c, tk.TYPE_LABEL, weight=ft.FontWeight.W_600))
                     for c in columns],
            rows=rows, heading_row_height=40, data_row_min_height=48, data_row_max_height=56,
            column_spacing=tk.SPACE_5, horizontal_lines=ft.BorderSide(0.5, ui.p.border),
            heading_row_color=ui.p.surface_alt, data="data-dictionary",
        )
        pending = s.pending_levels()
        # A disabled button says why, and what to do instead.
        reason = (ui.t("data.accept_none_left") if not pending else
                  None if self.accept_checked else ui.t("data.accept_tick_first"))
        accept = ft.Column([
            wc.caption(ui, ui.t("data.accept_explain")),
            ft.Row([
                wc.checkbox(ui, ui.t("data.accept_confirm"), self.accept_checked,
                            on_change=self._accept_checked, data="data-accept-confirm"),
                wc.button(ui, ui.t("data.accept_suggestions"), self._accept,
                          disabled=not (self.accept_checked and pending), tooltip=reason,
                          data="data-accept"),
            ], wrap=True, spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            *([wc.caption(ui, reason, data="data-accept-reason")] if reason else []),
        ], spacing=tk.SPACE_2)
        return wc.card(ui, [ft.Row([table], scroll=ft.ScrollMode.AUTO), accept],
                       title=ui.t("data.dictionary"), description=ui.t("data.dictionary.help"))

    def _confirm(self, name: str, level: str):
        self.app.session.confirm_level(name, level or "unknown", "data")
        self.app.status(self.app.t("design.saved_level"), "success")

    def _accept_checked(self, e):
        self.accept_checked = bool(e.control.value)
        self.app.render()

    def _accept(self, e=None):
        changed = self.app.session.accept_suggestions()
        self.accept_checked = False
        self.app.status(self.app.t("data.accept_done", count=changed), "success")
        self.app.render()

    # ------------------------------------------------------------- preview
    def _preview(self) -> ft.Control:
        ui, df = self.app.ui, self.app.session.df
        head = df.head(self.PREVIEW_ROWS)
        table = ft.DataTable(
            columns=[ft.DataColumn(wc.text(ui, str(c), tk.TYPE_LABEL, weight=ft.FontWeight.W_600))
                     for c in head.columns],
            rows=[ft.DataRow(cells=[ft.DataCell(wc.text(
                ui, _cell(v), color=ui.p.text)) for v in row])
                for row in head.itertuples(index=False)],
            heading_row_height=36, data_row_min_height=32, data_row_max_height=40,
            column_spacing=tk.SPACE_5, horizontal_lines=ft.BorderSide(0.5, ui.p.border),
            heading_row_color=ui.p.surface_alt,
        )
        return wc.card(ui, [ft.Row([table], scroll=ft.ScrollMode.AUTO)],
                       title=ui.t("data.preview", count=min(self.PREVIEW_ROWS, len(df))),
                       data="data-preview")

    # ------------------------------------------------------ import options
    def _import_options(self) -> ft.Control:
        ui, s = self.app.ui, self.app.session
        o = self.options

        def setter(name):
            return lambda e: o.__setitem__(name, e.control.value)

        sheets = []
        if s.source_path and Path(s.source_path).suffix.lower() in {".xlsx", ".xlsm"}:
            try:
                from data_loader import workbook_sheets

                sheets = workbook_sheets(s.source_path)
            except Exception:
                sheets = []

        def choices(group, values):
            return [(v, ui.t(f"data.opt.{group}.{v}")) for v in values]

        encodings = choices("encoding", ("auto",))
        encodings += [("utf-8-sig", "UTF-8"), ("utf-16", "UTF-16")]
        encodings += choices("encoding", ("cp1257", "cp1251", "cp1252"))
        fields = [
            wc.dropdown(ui, ui.t("data.opt.sheet"), [(n, n) for n in sheets], o["sheet"],
                        on_select=setter("sheet"), width=220, disabled=not sheets),
            wc.text_field(ui, ui.t("data.opt.header_row"), o["header_row"], width=170,
                          on_change=setter("header_row")),
            wc.text_field(ui, ui.t("data.opt.data_start"), o["data_start"], width=230,
                          on_change=setter("data_start")),
            wc.dropdown(ui, ui.t("data.opt.separator"),
                        choices("separator", ("auto", "comma", "semicolon", "tab", "pipe")),
                        o["separator"], on_select=setter("separator"), width=190),
            wc.dropdown(ui, ui.t("data.opt.decimal"),
                        choices("decimal", ("auto", "dot", "comma")),
                        o["decimal"], on_select=setter("decimal"), width=230),
            wc.dropdown(ui, ui.t("data.opt.encoding"), encodings,
                        o["encoding"], on_select=setter("encoding"), width=250),
            wc.text_field(ui, ui.t("data.opt.missing"), o["missing"],
                          width=360, on_change=setter("missing")),
        ]
        report = s.import_report
        diagnostics = []
        if report is not None:
            text = report.as_text() if hasattr(report, "as_text") else str(report)
            if text.strip():
                diagnostics = [wc.section_label(ui, ui.t("data.diagnostics")),
                               wc.text(ui, text, tk.TYPE_BODY, color=ui.p.text_secondary,
                                       selectable=True)]
        tile = ft.ExpansionTile(
            title=wc.heading(ui, ui.t("data.import_options"), tk.TYPE_TITLE_S),
            subtitle=wc.caption(ui, ui.t("data.import_options.body")),
            expanded="data-import-options" in self.opened, key="data-import-options",
            on_change=wc.expansion_handler(self.opened, "data-import-options"),
            controls=[ft.Container(ft.Column([
                ft.Row(fields, wrap=True, spacing=tk.SPACE_3, run_spacing=tk.SPACE_3),
                wc.button(ui, ui.t("data.reimport"), self._reimport,
                          disabled=not s.source_path,
                          tooltip=None if s.source_path else ui.t("disabled.no_source_file"),
                          data="data-reimport"),
                *diagnostics,
            ], spacing=tk.SPACE_3), padding=tk.SPACE_4)],
            collapsed_bgcolor=ui.p.surface, bgcolor=ui.p.surface,
            shape=ft.RoundedRectangleBorder(radius=ui.radius("card")),
            collapsed_shape=ft.RoundedRectangleBorder(radius=ui.radius("card")),
            data="data-import-options",
        )
        return ft.Container(tile, border=ft.Border.all(1, ui.p.border),
                            border_radius=ui.radius("card"))

    async def _reimport(self, e=None):
        from data_loader import ImportOptions

        s, o = self.app.session, self.options
        if not s.source_path:
            return
        try:
            options = ImportOptions(
                sheet=o["sheet"] or 0, header_row=int((o["header_row"] or "1").strip()),
                data_start_row=int(o["data_start"]) if (o["data_start"] or "").strip() else None,
                separator=o["separator"] or "auto", encoding=o["encoding"] or "auto",
                decimal=o["decimal"] or "auto",
                missing_tokens=("", *[x.strip() for x in (o["missing"] or "").split(";")
                                      if x.strip()]),
            )
        except ValueError as error:
            self.app.status(self.app.t("data.load_failed", error=error), "danger")
            return
        await self.app.load_path(s.source_path, display_name=s.source_name, options=options)

    # --------------------------------------------------------- preparation
    def _preparation_card(self) -> ft.Control:
        ui = self.app.ui
        content: list[ft.Control] = []
        if self.show_preparation:
            panel = self._preparation_panel()
            if panel is not None:
                content.append(panel)
        return wc.card(ui, content, title=ui.t("data.prepare"),
                       description=ui.t("data.prepare.body"), actions=[] if self.show_preparation
                       else [wc.button(ui, ui.t("data.prepare.open"), self._open_preparation,
                                       icon=ft.Icons.TUNE, data="data-prepare")],
                       data="data-preparation")

    def _preparation_panel(self):
        """The validated classic preparation tools, hosted unchanged."""
        if self._preparation is None:
            from data_preparation import history_record
            from preparation_ui import build_preparation_workspace

            async def adopt(prepared: pd.DataFrame, steps: list[dict]):
                # Stage 36.8 (K3): the columns that are still there keep their
                # confirmed levels, and every step goes into the project history.
                self.app.session.add_prepared_columns(
                    prepared, [history_record(step) for step in steps])
                self.app.status(self.app.t("data.loaded", name=self.app.session.source_name),
                                "success")
                self.app.render()

            # The theme's text colour: readable in the light and the dark theme (D6).
            self._preparation = build_preparation_workspace(self.app.page, load_dataframe=adopt,
                                                            with_steps=True, caption_color=None)
            self._preparation_df = None
        panel, reset = self._preparation
        if self._preparation_df is not self.app.session.df:
            reset(self.app.session.df, self.app.session.source_path)
            self._preparation_df = self.app.session.df
        return panel

    def _open_preparation(self, e=None):
        self.show_preparation = True
        self.app.render()

    # ------------------------------------------------------------- helpers
    def _sample_picker(self) -> ft.Control:
        ui = self.app.ui

        def pick(e):
            self.sample = e.control.value

        async def load(e):
            await self.app.load_sample(self.sample)

        return wc.card(ui, [ft.Row([
            wc.dropdown(ui, ui.t("data.sample_pick"), [(n, f"{ui.t(key)} · {n}") for n, key in SAMPLES],
                        self.sample, on_select=pick, width=380, data="data-sample-pick"),
            wc.button(ui, ui.t("data.sample"), load, icon=ft.Icons.SCIENCE_OUTLINED,
                      data="data-sample"),
        ], wrap=True, spacing=tk.SPACE_3)], title=ui.t("home.sample.title"),
            description=ui.t("home.sample.body"))

    def _path_fallback(self) -> ft.Control:
        ui = self.app.ui
        field = wc.text_field(ui, ui.t("data.path_field"), width=520)

        async def open_path(e):
            raw = (field.value or "").strip().strip('"')
            if raw:
                await self.app.import_files([SimpleNamespace(name=Path(raw).name, path=raw)])

        return ft.Row([wc.caption(ui, ui.t("data.path_fallback")), field,
                       wc.button(ui, ui.t("data.path_open"), open_path)],
                      wrap=True, spacing=tk.SPACE_3,
                      vertical_alignment=ft.CrossAxisAlignment.CENTER)


class HelpPage:
    SHORTCUTS = (("Ctrl+1 … Ctrl+6", "sc.areas"), ("Ctrl+B", "sc.sidebar"),
                 ("Ctrl+O", "sc.open"), ("Ctrl+Enter", "sc.run"),
                 ("Ctrl+Shift+L", "sc.theme"), ("F1", "sc.help"))

    def __init__(self, app: WorkspaceApp):
        self.app = app

    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        shortcuts = [wc.labeled(ui, keys, ui.t(key)) for keys, key in self.SHORTCUTS]
        cards = [
            wc.page_header(ui, ui.t("help.title")),
            wc.card(ui, shortcuts, title=ui.t("help.shortcuts"), data="help-shortcuts"),
            wc.card(ui, [wc.text(ui, ui.t("help.privacy.body"), tk.TYPE_BODY_L)],
                    title=ui.t("help.privacy")),
            wc.card(ui, [wc.text(ui, ui.t("help.ai.body"), tk.TYPE_BODY_L)],
                    title=ui.t("help.ai")),
        ]
        actions = [wc.button(ui, ui.t("help.settings_open"),
                             lambda e: app.navigate("settings"), icon=ft.Icons.SETTINGS_OUTLINED,
                             data="help-settings")]
        if app.bridge.return_to_classic is not None:
            actions.insert(0, wc.button(ui, ui.t("settings.classic"), app.return_to_classic,
                                        icon=ft.Icons.SWAP_HORIZ, data="help-classic"))
        cards.append(wc.card(ui, [wc.text(ui, ui.t("help.interfaces.body"), tk.TYPE_BODY_L)],
                             title=ui.t("help.interfaces"), actions=actions,
                             data="help-interfaces"))
        return app.constrained(ft.Column(cards, spacing=tk.SPACE_5,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.READING_MAX_WIDTH + 200)
