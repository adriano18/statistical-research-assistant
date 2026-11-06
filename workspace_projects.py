"""Research projects in the workspace (Stage 34, issue #24).

The Home page shows the current project and every saved project on this
computer: create (a title and one click), open, switch, duplicate, archive,
back up, delete (to "Recently deleted") and restore a backup. All the work
itself is saved by ``project_session.ProjectBinding`` as it happens.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import flet as ft

import workspace_tokens as tk
import workspace_components as wc
from project_session import _local_time
from project_store import ProjectError
from workspace_state import LEVELS
from workspace_text import count_text

VISIBLE_PROJECTS = 8
_LEVEL_CHANGE = re.compile(
    r"^measurement level of (?P<name>.+) changed \((?P<old>\S+) → (?P<new>[^)]+)\)$")


def stale_text(ui: wc.Ui, reason: str) -> str:
    """A stored stale reason (English, like the engine reports) in the interface language."""
    if reason.startswith("data changed"):
        return ui.t("project.stale.data")
    if reason == "dataset removed":
        return ui.t("project.stale.dataset_removed")
    if reason.startswith("recalculated"):
        return ui.t("project.stale.differs")
    if reason.startswith("removed from"):
        return ui.t("project.stale.removed")
    match = _LEVEL_CHANGE.match(reason)
    if match:
        def level(value: str) -> str:
            return ui.t(f"level.{value}") if value in LEVELS else ui.t("level.unknown")
        return ui.t("project.stale.level", name=match["name"], old=level(match["old"]),
                    new=level(match["new"]))
    return reason


def _when(stamp: str) -> str:
    return f"{_local_time(stamp):%Y-%m-%d %H:%M}"


def _file_name(title: str) -> str:
    """A backup file name from a project title (letters of every language kept)."""
    name = re.sub(r"[^\w\- ]+", "", title, flags=re.UNICODE).strip().replace(" ", "_")
    return (name or "project")[:60] + ".sra"


class ProjectHub:
    """The projects part of Home, and the project actions behind it."""

    def __init__(self, app):
        self.app = app
        self.new_title = ""
        self.show_archived = False
        self.show_all = False
        self.feedback: tuple[str, str] | None = None
        self.restored_id: str | None = None
        self.backup_picker = ft.FilePicker(on_result=self._on_backup_picked)
        app.page.services.append(self.backup_picker)
        self.restore_action = ft.PickFiles(
            self.backup_picker, allow_multiple=False, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["sra"], with_data=bool(getattr(app.page, "web", False)))

    @property
    def binding(self):
        return self.app.projects

    # ------------------------------------------------------------- view
    def section(self) -> list[ft.Control]:
        ui, binding = self.app.ui, self.app.projects
        controls: list[ft.Control] = [
            wc.heading(ui, ui.t("project.section"), tk.TYPE_TITLE_M),
            wc.text(ui, ui.t("project.section_body"), tk.TYPE_BODY, color=ui.p.text_secondary),
        ]
        if binding.unavailable:
            controls.append(wc.notice(ui, ui.t("project.unavailable", error=binding.unavailable),
                                      "warning", data="project-unavailable"))
            return controls
        if binding.message:
            key, tone = binding.message
            controls.append(wc.notice(ui, ui.t(key), tone, data="project-message"))
        if binding.active:
            controls.append(self._current())
        controls.append(self._projects())
        if self.feedback:
            actions = []
            if self.restored_id:
                actions.append(wc.button(ui, ui.t("project.open"),
                                         lambda e, i=self.restored_id: self.open(i),
                                         kind="primary", data="project-open-restored"))
            controls.append(wc.notice(ui, self.feedback[0], self.feedback[1], actions=actions,
                                      data="project-feedback"))
        return controls

    def _counts(self, counts: dict) -> str:
        language = self.app.ui.language
        parts = [count_text(language, counts.get("datasets", 0), "datasets"),
                 count_text(language, counts.get("runs", 0), "results")]
        if counts.get("questionnaires"):
            parts.append(count_text(language, counts["questionnaires"], "questionnaires"))
        return " · ".join(parts)

    def _current(self) -> ft.Control:
        app, ui, binding = self.app, self.app.ui, self.app.projects
        info = binding.info()
        stale = binding.stale_count()
        chips = [wc.chip(ui, ui.t("project.saved_auto", time=f"{_local_time(info.modified_at):%H:%M}"),
                         "success", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, data="project-saved")]
        if stale:
            chips.append(wc.chip(ui, ui.t("project.needs_attention", count=stale), "warning",
                                 icon=ft.Icons.UPDATE, on_click=lambda e: app.navigate("results"),
                                 data="project-stale"))
        return wc.card(ui, [
            wc.heading(ui, info.title, tk.TYPE_TITLE_S, data="project-current-title"),
            wc.caption(ui, self._counts(info.counts)),
            ft.Row(chips, wrap=True, spacing=tk.SPACE_2),
        ], title=ui.t("project.current"), actions=[
            wc.button(ui, ui.t("project.backup"), lambda e, i=info.id, t=info.title: self.backup(i, t),
                      icon=ft.Icons.SAVE_ALT, data="project-backup-current"),
            wc.button(ui, ui.t("project.close"), self.close, kind="quiet",
                      icon=ft.Icons.CLOSE, data="project-close"),
        ], data="project-current", border=ui.p.accent)

    def _projects(self) -> ft.Control:
        app, ui, binding = self.app, self.app.ui, self.app.projects
        title = wc.text_field(ui, ui.t("project.new_title"), self.new_title,
                              hint=ui.t("project.new_hint"), expand=True,
                              on_change=lambda e: setattr(self, "new_title", e.control.value or ""),
                              data="project-new-title")
        title.on_submit = self.create
        create = wc.button(ui, ui.t("project.create"), self.create,
                           kind="secondary" if binding.active else "primary",
                           icon=ft.Icons.CREATE_NEW_FOLDER_OUTLINED, data="project-create")
        content: list[ft.Control] = [
            ft.Row([title, create], spacing=tk.SPACE_3,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]
        session = app.session
        if not binding.active and (session.has_data or session.results):
            content.append(wc.caption(ui, ui.t("project.create_keeps")))
        projects = binding.projects(include_archived=self.show_archived)
        if binding.active:   # the open project first, then by last opened
            projects.sort(key=lambda info: info.id != binding.project.id)
        shown = projects if self.show_all else projects[:VISIBLE_PROJECTS]
        if shown:
            content.append(ft.Column([self._row(info) for info in shown], spacing=tk.SPACE_2,
                                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH))
        if not projects:
            content.append(wc.caption(ui, ui.t("project.empty"), data="project-empty"))
        footer: list[ft.Control] = []
        if len(projects) > VISIBLE_PROJECTS:
            footer.append(wc.button(ui, ui.t("common.less" if self.show_all else "common.more"),
                                    self._toggle_all, kind="quiet", data="project-more"))
        footer += [
            wc.checkbox(ui, ui.t("project.show_archived"), self.show_archived,
                        on_change=lambda e: self._set_archived_view(bool(e.control.value)),
                        data="project-show-archived"),
            wc.button(ui, ui.t("project.restore_backup"), action=self.restore_action,
                      kind="quiet", icon=ft.Icons.RESTORE, data="project-restore-backup"),
        ]
        content.append(ft.Row(footer, wrap=True, spacing=tk.SPACE_3,
                              vertical_alignment=ft.CrossAxisAlignment.CENTER))
        deleted = binding.deleted_projects()
        if deleted:
            rows = [ft.Row([
                ft.Column([wc.text(ui, d.title, tk.TYPE_BODY, weight=ft.FontWeight.W_600),
                           wc.caption(ui, ui.t("project.deleted_on", date=self._deleted_date(d)))],
                          spacing=2, expand=True),
                wc.button(ui, ui.t("project.restore_deleted"),
                          lambda e, p=d.path: self.restore_deleted(p), kind="quiet",
                          icon=ft.Icons.RESTORE_FROM_TRASH, data=f"project-undelete-{index}"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER) for index, d in enumerate(deleted[:10])]
            content.append(ft.Container(ft.ExpansionTile(
                title=wc.text(ui, f"{ui.t('project.recently_deleted')} ({len(deleted)})",
                              tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                controls=[ft.Container(ft.Column(rows, spacing=tk.SPACE_2), padding=tk.SPACE_3)],
                bgcolor=ui.p.surface, collapsed_bgcolor=ui.p.surface,
            ), border=ft.Border.all(1, ui.p.border), border_radius=ui.radius("card"),
                data="project-deleted"))
        return wc.card(ui, content, data="project-list")

    @staticmethod
    def _deleted_date(deleted) -> str:
        stamp = deleted.deleted
        if len(stamp) == 15 and stamp[8] == "-":
            return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}"
        return stamp

    def _row(self, info) -> ft.Control:
        app, ui, binding = self.app, self.app.ui, self.app.projects
        current = binding.active and binding.project.id == info.id
        meta = [self._counts(info.counts), ui.t("project.last_opened", date=_when(info.last_opened_at))]
        heading: list[ft.Control] = [wc.text(ui, info.title, tk.TYPE_BODY, weight=ft.FontWeight.W_600,
                                             max_lines=2)]
        if info.archived:
            heading.append(wc.chip(ui, ui.t("project.archived_badge"), "neutral",
                                   icon=ft.Icons.ARCHIVE_OUTLINED))
        trailing: list[ft.Control] = [
            wc.chip(ui, ui.t("project.is_open"), "success", icon=ft.Icons.FOLDER_OPEN,
                    data=f"project-current-{info.id}") if current else
            wc.button(ui, ui.t("project.open"), lambda e, i=info.id: self.open(i),
                      kind="secondary", icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                      tooltip=ui.t("project.open_named", title=info.title),
                      data=f"project-open-{info.id}", disabled=info.archived),
            wc.icon_button(ui, ft.Icons.CONTENT_COPY, ui.t("project.duplicate"),
                           lambda e, i=info.id: self.duplicate(i), data=f"project-duplicate-{info.id}"),
            wc.icon_button(ui, ft.Icons.SAVE_ALT, ui.t("project.backup"),
                           lambda e, i=info.id, t=info.title: self.backup(i, t),
                           data=f"project-backup-{info.id}"),
            wc.icon_button(ui, ft.Icons.UNARCHIVE_OUTLINED if info.archived else ft.Icons.ARCHIVE_OUTLINED,
                           ui.t("project.unarchive" if info.archived else "project.archive"),
                           lambda e, i=info.id, a=not info.archived: self.archive(i, a),
                           data=f"project-archive-{info.id}"),
            wc.icon_button(ui, ft.Icons.DELETE_OUTLINE, ui.t("project.delete"),
                           lambda e, i=info.id, t=info.title: self.confirm_delete(i, t),
                           data=f"project-delete-{info.id}"),
        ]
        details = ft.Column([ft.Row(heading, spacing=tk.SPACE_2, wrap=True),
                             wc.caption(ui, " · ".join(meta))], spacing=2,
                            expand=not app.compact)
        actions = ft.Row(trailing, spacing=tk.SPACE_1, wrap=app.compact)
        # Narrow windows stack the actions under the title; an expanding child
        # cannot sit inside a wrapping row (Flutter shows an error box).
        layout = (ft.Column([details, actions], spacing=tk.SPACE_2) if app.compact else
                  ft.Row([details, actions], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        return ft.Container(
            content=layout,
            bgcolor=ui.p.accent_subtle if current else ui.p.surface,
            border=ft.Border.all(1, ui.p.accent if current else ui.p.border),
            border_radius=ui.radius("card"), padding=tk.SPACE_3, data=f"project-row-{info.id}",
        )

    # ---------------------------------------------------------- actions
    def _done(self, message: str, tone: str = "success", *, restored: str | None = None):
        self.feedback = (message, tone)
        self.restored_id = restored
        self.app.status(message, tone)
        self.app.render()

    def _failed(self, error: Exception):
        self._done(self.app.t("project.failed", error=error), "danger")

    async def create(self, e=None):
        title = self.new_title.strip()
        if not title:
            self._done(self.app.t("project.title_needed"), "warning")
            return
        try:
            info = self.binding.create(title)
        except (ProjectError, OSError) as error:
            self._failed(error)
            return
        self.new_title = ""
        self._done(self.app.t("project.created", title=info.title))

    async def open(self, project_id: str):
        try:
            info = self.binding.open(project_id)
        except (ProjectError, OSError) as error:
            self._failed(error)
            return
        self.app.pages["analyze"].reset()
        self._done(self.app.t("project.opened", title=info.title))
        await self.verify()

    async def verify(self):
        """Recalculate restored results in the background, then refresh."""
        verified = await self.binding.verify_restored()
        if verified:
            self.app.status(self.app.t("project.verified", count=verified), "success")
            self.app.render()

    async def close(self, e=None):
        self.binding.close()
        self.app.pages["analyze"].reset()
        self._done(self.app.t("project.closed"))

    async def duplicate(self, project_id: str):
        try:
            info = await asyncio.to_thread(self.binding.duplicate, project_id)
        except (ProjectError, OSError) as error:
            self._failed(error)
            return
        self._done(self.app.t("project.duplicated", title=info.title))

    async def archive(self, project_id: str, archived: bool):
        try:
            info = self.binding.set_archived(project_id, archived)
        except (ProjectError, OSError) as error:
            self._failed(error)
            return
        self._done(self.app.t("project.archived" if archived else "project.unarchived",
                              title=info.title))

    def confirm_delete(self, project_id: str, title: str):
        ui = self.app.ui

        async def delete(e=None):
            self.app.page.pop_dialog()
            await self.delete(project_id, title)

        dialog = ft.AlertDialog(
            modal=True,
            title=wc.heading(ui, ui.t("project.delete_title", title=title), tk.TYPE_TITLE_S),
            content=ft.Container(wc.text(ui, ui.t("project.delete_body"), tk.TYPE_BODY), width=460),
            actions=[
                wc.button(ui, ui.t("common.cancel"), lambda e: self.app.page.pop_dialog(),
                          kind="quiet", data="project-delete-cancel"),
                wc.button(ui, ui.t("project.delete_confirm"), delete, kind="primary",
                          icon=ft.Icons.DELETE_OUTLINE, data="project-delete-confirm"),
            ],
        )
        self.app.page.show_dialog(dialog)

    async def delete(self, project_id: str, title: str):
        try:
            self.binding.delete(project_id)
        except (ProjectError, OSError) as error:
            self._failed(error)
            return
        self._done(self.app.t("project.deleted", title=title))

    async def restore_deleted(self, path: Path):
        try:
            info = self.binding.restore_deleted(path)
        except (ProjectError, OSError) as error:
            self._failed(error)
            return
        self._done(self.app.t("project.restored", title=info.title), restored=info.id)

    async def backup(self, project_id: str, title: str):
        app = self.app
        try:
            destination = await app.save_dialog(app.t("project.backup_title"), _file_name(title), "sra")
            if not destination:
                return
            saved = await asyncio.to_thread(self.binding.export, project_id, Path(destination),
                                            app.survey_root)
        except Exception as error:
            self._failed(error)
            return
        self._done(app.t("project.backup_saved", path=saved))

    async def _on_backup_picked(self, e):
        await self.restore_files(getattr(e, "files", None))

    async def restore_files(self, files) -> bool:
        """Restore the chosen ``.sra`` file (a path on desktop, bytes on the web)."""
        app = self.app
        if not files:
            return False
        picked = files[0]
        try:
            with TemporaryDirectory(prefix="workspace-backup-") as temporary:
                path = getattr(picked, "path", None)
                if not path:
                    data = getattr(picked, "bytes", None) or getattr(picked, "data", None)
                    if not data:
                        raise ProjectError("The browser did not provide the file.")
                    path = Path(temporary) / Path(getattr(picked, "name", "backup.sra")).name
                    path.write_bytes(data)
                info, warnings = await asyncio.to_thread(self.binding.restore, Path(path),
                                                         app.survey_root)
        except Exception as error:
            self._done(app.t("project.restore_failed", error=error), "danger")
            return False
        message = app.t("project.restored", title=info.title)
        if warnings:
            message += " " + " ".join(warnings)
        self._done(message, "warning" if warnings else "success", restored=info.id)
        return True

    def _set_archived_view(self, value: bool):
        self.show_archived = value
        self.app.render()

    def _toggle_all(self, e=None):
        self.show_all = not self.show_all
        self.app.render()
