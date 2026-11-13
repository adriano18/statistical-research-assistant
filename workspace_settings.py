"""Settings: one place for every choice the researcher makes about the
program (Stage 37, issue #68).

The page is a list of sections drawn from a registry (``SECTIONS``), in
their ``order``. A feature adds its own section with one entry::

    from workspace_settings import SettingsSection, register

    register(SettingsSection("export", "settings.section.export", 65, build_export))

where ``build_export(page)`` returns the section's controls (``page`` is the
:class:`SettingsPage`; ``page.app`` the workspace). Orders 10-100 are taken
by the built-in sections below; the gaps (65, 85) are free for the export
defaults and the research library's privacy settings.

What is chosen here is kept in the settings file (``user_settings``) and
applies at once: appearance, typeface, text size, density, language, the
interface opened at start, and where research data lives. "Reset settings"
and "Delete research data" are two separate, explained sections: a reset
never touches research data.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import flet as ft

import user_settings as us
import workspace_components as wc
import workspace_tokens as tk


@dataclass(frozen=True)
class SettingsSection:
    key: str                     # "appearance"; the card's data is settings-section-<key>
    title: str                   # text key of its heading
    order: int                   # place on the page (low first)
    build: Callable[["SettingsPage"], list[ft.Control] | ft.Control | None]
    description: str | None = None   # text key of a line under the heading
    framed: bool = True          # False: ``build`` returns finished cards


SECTIONS: dict[str, SettingsSection] = {}


def register(section: SettingsSection) -> SettingsSection:
    """Add (or replace) a section of the Settings page."""
    SECTIONS[section.key] = section
    return section


def section_key(key: str) -> str:
    """The scroll key of a section (``navigate("settings", section=key)``)."""
    return f"settings-section-{key}"


class SettingsPage:
    def __init__(self, app):
        from workspace_ai import AiProvidersCard
        from workspace_profile import ProfileSettings

        self.app = app
        self.ocr_summary = ""
        self.data_note = ""
        self.feedback: tuple[str, str] | None = None
        self.profile = ProfileSettings(app)
        self.ai_providers = AiProvidersCard(app)

    # -------------------------------------------------------------- page
    def sections(self) -> list[SettingsSection]:
        return sorted(SECTIONS.values(), key=lambda s: (s.order, s.key))

    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        cards: list[ft.Control] = []
        shown: list[SettingsSection] = []
        for section in self.sections():
            try:
                content = section.build(self)
            except Exception as error:      # one section's bug never hides the others
                content = [wc.notice(ui, f"{type(error).__name__}: {error}", "danger",
                                     title=ui.t("page.failed"))]
            if content is None:
                continue
            shown.append(section)
            if not section.framed:
                cards.extend(content if isinstance(content, list) else [content])
                continue
            controls = content if isinstance(content, list) else [content]
            card = wc.card(ui, controls, title=ui.t(section.title),
                           description=ui.t(section.description) if section.description
                           else None, data=section_key(section.key))
            card.key = ft.ScrollKey(section_key(section.key))
            cards.append(card)
        index = wc.card(ui, [ft.Row([
            wc.chip(ui, ui.t(s.title), "neutral",
                    on_click=lambda e, k=s.key: app.navigate("settings", section=k),
                    data=f"settings-jump-{s.key}")
            for s in shown], wrap=True, spacing=tk.SPACE_2)],
            title=ui.t("settings.sections"), data="settings-index")
        body = [wc.page_header(ui, ui.t("settings.title"), ui.t("settings.subtitle")), index]
        if self.feedback:
            body.append(wc.notice(ui, self.feedback[0], self.feedback[1],
                                  data="settings-feedback"))
        return app.constrained(ft.Column(body + cards, spacing=tk.SPACE_5,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.READING_MAX_WIDTH + 200)

    # ------------------------------------------------------- appearance
    def appearance(self) -> list[ft.Control]:
        app, ui, s = self.app, self.app.ui, self.app.session
        return [
            wc.section_label(ui, ui.t("settings.theme")),
            wc.segmented(ui, [("light", ui.t("settings.theme.light")),
                              ("dark", ui.t("settings.theme.dark")),
                              ("system", ui.t("settings.theme.system"))], app.theme_choice,
                         app.set_theme, data="settings-theme"),
            wc.caption(ui, ui.t("settings.theme_note")),
            wc.section_label(ui, ui.t("settings.accent")),
            wc.segmented(ui, [(key, ui.t(f"accent.{key}")) for key in tk.ACCENTS], s.accent,
                         app.set_accent, data="settings-accent"),
            wc.caption(ui, ui.t("settings.accent_note")),
            wc.section_label(ui, ui.t("settings.corners")),
            wc.segmented(ui, [("windows", ui.t("settings.corners.windows")),
                              ("macos", ui.t("settings.corners.macos"))], s.corners,
                         app.set_corners, data="settings-corners"),
        ]

    def typography(self) -> list[ft.Control]:
        app, ui = self.app, self.app.ui
        return [
            wc.section_label(ui, ui.t("settings.text_size")),
            wc.segmented(ui, [(str(value), f"{value} %") for value in us.TEXT_SCALES],
                         str(app.text_scale), app.set_text_scale, data="settings-text-size"),
            wc.caption(ui, ui.t("settings.text_size_note")),
            wc.section_label(ui, ui.t("settings.density")),
            wc.segmented(ui, [(key, ui.t(f"settings.density.{key}")) for key in us.DENSITIES],
                         app.density, app.set_density, data="settings-density"),
            wc.section_label(ui, ui.t("settings.typeface")),
            wc.segmented(ui, [(key, ui.t(f"settings.typeface.{key}")) for key in us.TYPEFACES],
                         app.typeface, app.set_typeface, data="settings-typeface"),
            wc.caption(ui, ui.t("settings.typeface_note")),
        ]

    def language(self) -> list[ft.Control]:
        app, ui = self.app, self.app.ui
        return [
            wc.dropdown(ui, ui.t("settings.language"),
                        [(code, us.LANGUAGE_NAMES[code]) for code in us.LANGUAGES],
                        ui.language, on_select=lambda e: app.set_language(e.control.value),
                        width=260, data="settings-language"),
            wc.caption(ui, ui.t("settings.language_note")),
        ]

    def start(self) -> list[ft.Control]:
        app, ui = self.app, self.app.ui
        # A dropdown: its entries cannot be confused with the sidebar's
        # "Classic interface", which switches at once.
        rows: list[ft.Control] = [
            wc.dropdown(ui, ui.t("settings.start_interface"),
                        [(key, ui.t(f"settings.start.{key}")) for key in us.START_INTERFACES],
                        app.settings.get("start_interface"),
                        on_select=lambda e: app.set_start_interface(e.control.value),
                        width=320, data="settings-start-interface"),
            wc.caption(ui, ui.t("settings.start_note")),
        ]
        if app.bridge.return_to_classic is not None:
            rows.append(ft.Row([wc.button(ui, ui.t("settings.classic"), app.return_to_classic,
                                          icon=ft.Icons.SWAP_HORIZ,
                                          data="settings-open-classic")]))
        return rows

    # -------------------------------------------------------- data folder
    def projects(self) -> ft.Control:
        """Where research data lives (#44), recent projects and data files."""
        import data_ui

        app, ui = self.app, self.app.ui
        language = app.session.language
        root = app.project_root.parent
        rows: list[ft.Control] = [
            wc.text(ui, data_ui.t(language, "folder_body"), color=ui.p.text_secondary),
            wc.text(ui, str(root), selectable=True, data="settings-data-folder"),
            wc.caption(ui, data_ui.t(language, "folder_note")),
            ft.Row([wc.button(ui, data_ui.t(language, "open_folder"),
                              lambda e=None: data_ui.open_folder(root),
                              icon=ft.Icons.FOLDER_OPEN_OUTLINED, data="settings-data-open"),
                    wc.button(ui, data_ui.t(language, "find"), self._find_legacy,
                              icon=ft.Icons.MANAGE_SEARCH, data="settings-data-find")],
                   wrap=True, spacing=tk.SPACE_2),
        ]
        if self.data_note:
            rows.append(wc.text(ui, self.data_note, selectable=True, data="settings-data-note"))
        rows.append(wc.caption(ui, ui.t("settings.settings_file", path=app.settings.path),
                               selectable=True, data="settings-file"))
        rows.append(wc.section_label(ui, ui.t("settings.recent_projects")))
        try:
            recent = [info for info in app.projects.projects() if not info.archived][:5]
        except Exception:
            recent = []
        for info in recent:
            current = app.projects.active and app.projects.info().id == info.id
            rows.append(ft.Row([
                ft.Container(wc.text(ui, info.title, tk.TYPE_BODY, max_lines=1), expand=True),
                wc.chip(ui, ui.t("project.is_open"), "success") if current else
                wc.button(ui, ui.t("project.open"), wc.handler(app.hub.open, info.id),
                          kind="quiet", icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                          tooltip=ui.t("project.open_named", title=info.title),
                          data=f"settings-recent-project-{info.id}"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if not recent:
            rows.append(wc.caption(ui, ui.t("settings.recent_none")))
        rows.append(wc.section_label(ui, ui.t("settings.recent_files")))
        files = app.recent_files()
        rows += [wc.text(ui, path, tk.TYPE_BODY, selectable=True, max_lines=1)
                 for path in files[:5]] or [wc.caption(ui, ui.t("settings.recent_none"))]
        if files:
            rows.append(ft.Row([wc.button(ui, ui.t("settings.recent_clear"), self._clear_recent,
                                          kind="quiet", icon=ft.Icons.CLEAR_ALL,
                                          data="settings-recent-clear")]))
        card = wc.card(ui, rows, title=ui.t("settings.section.projects"), data="settings-data")
        card.key = ft.ScrollKey(section_key("projects"))
        return card

    def _clear_recent(self, e=None):
        self.app._save(recent_files=[])
        self.feedback = (self.app.t("settings.recent_cleared"), "success")
        self.app.render()

    async def _find_legacy(self, e=None):
        import data_ui

        language = self.app.session.language
        picker = data_ui.folder_picker(self.app.page)
        try:
            chosen = await picker.get_directory_path(dialog_title=data_ui.t(language, "pick"))
        except Exception:
            chosen = None
        self.data_note = await data_ui.find_in_chosen_folder(
            self.app.page, chosen, self.app.project_root.parent, language)
        self.app.render()

    def backups(self) -> list[ft.Control]:
        import data_ui

        app, ui = self.app, self.app.ui
        folder = app.project_root / ".backups"
        rows: list[ft.Control] = [
            wc.text(ui, ui.t("settings.backups_body"), tk.TYPE_BODY),
            wc.text(ui, str(folder), selectable=True, data="settings-backups-folder"),
            wc.notice(ui, ui.t("settings.backups_privacy"), "warning",
                      data="settings-backups-privacy"),
        ]
        actions = [wc.button(ui, ui.t("settings.backups_open"),
                             lambda e=None: data_ui.open_folder(
                                 folder if folder.is_dir() else app.project_root),
                             icon=ft.Icons.FOLDER_OPEN_OUTLINED, data="settings-backups-open")]
        if app.projects.active:
            info = app.projects.info()
            actions.insert(0, wc.button(ui, ui.t("settings.backup_open_project", title=info.title),
                                        wc.handler(app.hub.backup, info.id, info.title),
                                        icon=ft.Icons.SAVE_ALT, data="settings-backup-project"))
        actions.append(wc.button(ui, ui.t("project.restore_backup"), action=app.hub.restore_action,
                                 kind="quiet", icon=ft.Icons.RESTORE,
                                 data="settings-restore-backup"))
        rows.append(ft.Row(actions, wrap=True, spacing=tk.SPACE_2))
        return rows

    def updates(self) -> ft.Control:
        """Version, channel and in-app updates (#45): what the updater offers."""
        import app_identity
        import update_client
        import update_ui

        app, ui = self.app, self.app.ui
        language = app.session.language
        build = app_identity.build_info()
        root = app.project_root.parent
        rows = [wc.text(ui, line, data="settings-version") for line in
                update_ui.version_lines(language, build)]
        rows.append(wc.caption(ui, ui.t("settings.updates_channel")))

        def toggle(e=None):
            state = update_client.state(root)
            state["automatic"] = bool(e.control.value) if e is not None else True
            update_client.save_state(root, state)

        rows.append(ft.Checkbox(label=update_ui.t(language, "automatic"),
                                value=update_client.state(root).get("automatic", True),
                                on_change=toggle, data="settings-updates-automatic"))
        rows.append(wc.caption(ui, update_ui.t(language, "privacy")))
        rows.append(wc.button(ui, update_ui.t(language, "check"),
                              lambda e=None: update_ui.open_dialog(app.page, Path(__file__)
                                                                   .resolve().parent, language),
                              icon=ft.Icons.SYSTEM_UPDATE_ALT, data="settings-updates-check"))
        card = wc.card(ui, rows, title=update_ui.t(language, "title"), data="settings-updates")
        card.key = ft.ScrollKey(section_key("updates"))
        return card

    def ai(self) -> list[ft.Control]:
        """AI privacy: the providers (keys stay in the credential store) and
        what the assistant may see in the open project (all off by default)."""
        ui = self.app.ui
        intro = wc.notice(ui, ui.t("settings.ai_body"), "info", title=ui.t("settings.section.ai"),
                          data="settings-ai-privacy")
        intro.key = ft.ScrollKey(section_key("ai"))
        return [intro, self.ai_providers.build(), self.profile.ai_card()]

    def researcher(self) -> ft.Control:
        card = self.profile.profile_card()
        card.key = ft.ScrollKey(section_key("profile"))
        return card

    def ocr(self) -> list[ft.Control]:
        ui = self.app.ui
        rows: list[ft.Control] = [wc.button(ui, ui.t("settings.ocr_check"), self._check_ocr,
                                            icon=ft.Icons.DOCUMENT_SCANNER_OUTLINED,
                                            data="settings-ocr")]
        if self.ocr_summary:
            rows.append(wc.text(ui, self.ocr_summary, selectable=True, color=ui.p.text_secondary))
        return rows

    async def _check_ocr(self, e=None):
        from ocr_runtime import ocr_readiness

        self.ocr_summary = self.app.t("run.running")
        self.app.render()
        ready = await asyncio.to_thread(ocr_readiness, full_hash=False)
        self.ocr_summary = ready.summary()
        self.app.render()

    # ------------------------------------------------------------ reset
    def reset(self) -> list[ft.Control]:
        """Two separate actions: settings back to their defaults (research
        data untouched), and how research data is deleted (never by a reset)."""
        import data_ui

        app, ui = self.app, self.app.ui
        root = app.project_root.parent
        return [
            wc.section_label(ui, ui.t("settings.reset")),
            wc.text(ui, ui.t("settings.reset_body"), tk.TYPE_BODY),
            ft.Row([wc.button(ui, ui.t("settings.reset"), self._ask_reset,
                              icon=ft.Icons.SETTINGS_BACKUP_RESTORE, data="settings-reset")]),
            wc.divider(ui),
            wc.section_label(ui, ui.t("settings.delete_data")),
            wc.text(ui, ui.t("settings.delete_data_body"), tk.TYPE_BODY,
                    data="settings-delete-data-body"),
            ft.Row([wc.button(ui, data_ui.t(app.session.language, "open_folder"),
                              lambda e=None: data_ui.open_folder(root),
                              icon=ft.Icons.FOLDER_OPEN_OUTLINED, kind="quiet",
                              data="settings-delete-data-folder"),
                    wc.button(ui, ui.t("settings.delete_data_projects"),
                              lambda e: app.navigate("home"), kind="quiet",
                              icon=ft.Icons.FOLDER_COPY_OUTLINED,
                              data="settings-delete-data-projects")],
                   wrap=True, spacing=tk.SPACE_2),
        ]

    def _ask_reset(self, e=None):
        app, ui = self.app, self.app.ui

        def confirm(e=None):
            app.page.pop_dialog()
            self.feedback = None
            app.reset_settings()

        app.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=wc.heading(ui, ui.t("settings.reset_title"), tk.TYPE_TITLE_S),
            content=ft.Container(wc.text(ui, ui.t("settings.reset_body"), tk.TYPE_BODY),
                                 width=480),
            actions=[wc.button(ui, ui.t("common.cancel"), lambda e: app.page.pop_dialog(),
                               kind="quiet", data="settings-reset-cancel", autofocus=True),
                     wc.button(ui, ui.t("settings.reset_confirm"), confirm, kind="primary",
                               data="settings-reset-confirm")],
            data="settings-reset-dialog",
        ))


# The built-in sections. Gaps in the order are left for other features.
for _section in (
    SettingsSection("appearance", "settings.section.appearance", 10, SettingsPage.appearance),
    SettingsSection("typography", "settings.section.typography", 20, SettingsPage.typography,
                    description="settings.section.typography_body"),
    SettingsSection("language", "settings.section.language", 30, SettingsPage.language),
    SettingsSection("start", "settings.section.start", 40, SettingsPage.start),
    SettingsSection("projects", "settings.section.projects", 50, SettingsPage.projects,
                    framed=False),
    SettingsSection("backups", "settings.section.backups", 60, SettingsPage.backups),
    SettingsSection("updates", "settings.section.updates", 70, SettingsPage.updates,
                    framed=False),
    SettingsSection("ai", "settings.section.ai", 80, SettingsPage.ai, framed=False),
    SettingsSection("profile", "settings.profile", 90, SettingsPage.researcher, framed=False),
    SettingsSection("ocr", "settings.ocr", 95, SettingsPage.ocr),
    SettingsSection("reset", "settings.section.reset", 100, SettingsPage.reset),
):
    register(_section)
