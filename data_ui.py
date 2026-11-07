"""Where research data is kept, and copying data of earlier versions (#44).

Shared by the classic window and the research workspace:

- ``offer_at_startup``: when an earlier version's data is found in one of
  its known places, a dialog lists it and offers to copy it into the data
  folder ("Not now" is remembered for that folder).
- ``show_data_folder``: the data folder, "Open folder" and "Find data from
  an earlier version…" (for a portable folder the researcher chooses).

Copying is done by ``legacy_data``: originals are only read, nothing in the
data folder is replaced, and every copy is checked against its original.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import weakref
from pathlib import Path

import flet as ft

import legacy_data as ld

TEXT = {
    "en": {
        "title": "Data from an earlier version",
        "found": "Research data saved by an earlier version of Statistical Research Assistant "
                 "was found in:",
        "into": "It can be copied into your data folder:",
        "projects": "Projects ({n}): {names}",
        "questionnaires": "Questionnaires with their responses ({n}): {names}",
        "profile": "Your researcher profile",
        "already": "Already in your data folder: {n}",
        "changed": "Changed in the earlier version after it was copied, not copied again: {names}",
        "conflicts": "Your data folder already holds a different version of: {names}. "
                     "Neither is replaced.",
        "originals": "The originals are only read: nothing in the earlier folder is changed or "
                     "deleted, and nothing already in your data folder is replaced.",
        "copy": "Copy into my data folder",
        "later": "Not now",
        "close": "Close",
        "copying": "Copying {i} of {n}: {name}…",
        "done_title": "Data copied",
        "done": "Copied: {summary}. Each copy was checked against its original.",
        "kept": "The originals are unchanged in {folder}.",
        "failed_title": "Some data could not be copied",
        "failed": "Not copied: {names} ({reason}). Nothing in the earlier folder was changed. "
                  "Try again later in Settings → Your data → Find data from an earlier version.",
        "disk_full": "Copying stopped because the disk is full. Free some space and try again; "
                     "nothing was lost.",
        "n_projects": "{n} project(s)", "n_questionnaires": "{n} questionnaire(s)",
        "n_profile": "the researcher profile",
        "folder_title": "Your data",
        "folder_body": "Projects, questionnaires, responses, reports and backups are stored on "
                       "this computer in:",
        "folder_note": "Installing, updating or uninstalling the program never changes this "
                       "folder.",
        "open_folder": "Open folder",
        "find": "Find data from an earlier version…",
        "searching": "Looking for data of an earlier version…",
        "none_found": "No data of an earlier version was found in {folder}.",
        "nothing_new": "Everything found in {folder} is already in your data folder.",
        "pick": "Choose the folder of an earlier (portable) version",
    },
    "lv": {
        "title": "Iepriekšējās versijas dati",
        "found": "Atrasti pētījuma dati, ko saglabājusi iepriekšēja Statistical Research "
                 "Assistant versija:",
        "into": "Tos var iekopēt jūsu datu mapē:",
        "projects": "Projekti ({n}): {names}",
        "questionnaires": "Anketas ar atbildēm ({n}): {names}",
        "profile": "Jūsu pētnieka profils",
        "already": "Jau ir jūsu datu mapē: {n}",
        "changed": "Iepriekšējā versijā mainīti pēc kopēšanas, netiek kopēti vēlreiz: {names}",
        "conflicts": "Jūsu datu mapē jau ir cita versija: {names}. Neviena netiek aizstāta.",
        "originals": "Oriģināli tiek tikai nolasīti: iepriekšējā mapē nekas netiek mainīts vai "
                     "dzēsts, un nekas jūsu datu mapē netiek aizstāts.",
        "copy": "Kopēt manā datu mapē",
        "later": "Ne tagad",
        "close": "Aizvērt",
        "copying": "Kopē {i}. no {n}: {name}…",
        "done_title": "Dati nokopēti",
        "done": "Nokopēts: {summary}. Katra kopija salīdzināta ar oriģinālu.",
        "kept": "Oriģināli nemainīti atrodas mapē {folder}.",
        "failed_title": "Daļu datu neizdevās nokopēt",
        "failed": "Nav nokopēts: {names} ({reason}). Iepriekšējā mapē nekas netika mainīts. "
                  "Mēģiniet vēlreiz vēlāk: Iestatījumi → Jūsu dati → Meklēt iepriekšējās "
                  "versijas datus.",
        "disk_full": "Kopēšana apturēta, jo disks ir pilns. Atbrīvojiet vietu un mēģiniet "
                     "vēlreiz; nekas nav zaudēts.",
        "n_projects": "projekti: {n}", "n_questionnaires": "anketas: {n}",
        "n_profile": "pētnieka profils",
        "folder_title": "Jūsu dati",
        "folder_body": "Projekti, anketas, atbildes, pārskati un rezerves kopijas glabājas šajā "
                       "datorā mapē:",
        "folder_note": "Programmas instalēšana, atjaunināšana vai atinstalēšana šo mapi nekad "
                       "nemaina.",
        "open_folder": "Atvērt mapi",
        "find": "Meklēt iepriekšējās versijas datus…",
        "searching": "Meklē iepriekšējās versijas datus…",
        "none_found": "Mapē {folder} iepriekšējās versijas dati netika atrasti.",
        "nothing_new": "Viss, kas atrasts mapē {folder}, jau ir jūsu datu mapē.",
        "pick": "Izvēlieties iepriekšējās (pārnēsājamās) versijas mapi",
    },
    "ru": {
        "title": "Данные предыдущей версии",
        "found": "Найдены исследовательские данные, сохранённые предыдущей версией "
                 "Statistical Research Assistant:",
        "into": "Их можно скопировать в вашу папку данных:",
        "projects": "Проекты ({n}): {names}",
        "questionnaires": "Анкеты с ответами ({n}): {names}",
        "profile": "Ваш профиль исследователя",
        "already": "Уже есть в вашей папке данных: {n}",
        "changed": "Изменены в предыдущей версии после копирования, повторно не копируются: "
                   "{names}",
        "conflicts": "В вашей папке данных уже есть другая версия: {names}. Ни одна не "
                     "заменяется.",
        "originals": "Оригиналы только читаются: в прежней папке ничего не изменяется и не "
                     "удаляется, а в вашей папке данных ничего не заменяется.",
        "copy": "Скопировать в мою папку данных",
        "later": "Не сейчас",
        "close": "Закрыть",
        "copying": "Копирование {i} из {n}: {name}…",
        "done_title": "Данные скопированы",
        "done": "Скопировано: {summary}. Каждая копия сверена с оригиналом.",
        "kept": "Оригиналы без изменений остались в папке {folder}.",
        "failed_title": "Часть данных скопировать не удалось",
        "failed": "Не скопировано: {names} ({reason}). В прежней папке ничего не изменено. "
                  "Повторите позже: Настройки → Ваши данные → Найти данные предыдущей версии.",
        "disk_full": "Копирование остановлено: диск заполнен. Освободите место и повторите; "
                     "ничего не потеряно.",
        "n_projects": "проектов: {n}", "n_questionnaires": "анкет: {n}",
        "n_profile": "профиль исследователя",
        "folder_title": "Ваши данные",
        "folder_body": "Проекты, анкеты, ответы, отчёты и резервные копии хранятся на этом "
                       "компьютере в папке:",
        "folder_note": "Установка, обновление или удаление программы никогда не изменяют эту "
                       "папку.",
        "open_folder": "Открыть папку",
        "find": "Найти данные предыдущей версии…",
        "searching": "Поиск данных предыдущей версии…",
        "none_found": "В папке {folder} данные предыдущей версии не найдены.",
        "nothing_new": "Всё найденное в папке {folder} уже есть в вашей папке данных.",
        "pick": "Выберите папку предыдущей (переносной) версии",
    },
}


def t(language: str, key: str, **values) -> str:
    table = TEXT.get(language, TEXT["en"])
    return table.get(key, TEXT["en"][key]).format(**values)


def _names(items, limit: int = 4) -> str:
    titles = sorted((item.title for item in items), key=str.casefold)
    shown = ", ".join(titles[:limit])
    return shown + (f" (+{len(titles) - limit})" if len(titles) > limit else "")


def summary_lines(source: ld.Source, language: str) -> list[str]:
    """What the dialog lists before anything is copied."""
    pending = source.pending
    lines = []
    projects = [i for i in pending if i.kind == "project"]
    surveys = [i for i in pending if i.kind == "questionnaire"]
    if projects:
        lines.append(t(language, "projects", n=len(projects), names=_names(projects)))
    if surveys:
        lines.append(t(language, "questionnaires", n=len(surveys), names=_names(surveys)))
    if any(i.kind == "profile" for i in pending):
        lines.append(t(language, "profile"))
    present = [i for i in source.items if i.state in ("present", "copied")]
    if present:
        lines.append(t(language, "already", n=len(present)))
    changed = [i for i in source.items if i.state == "changed" and i.title]
    if changed:
        lines.append(t(language, "changed", names=_names(changed)))
    conflicts = [i for i in source.items if i.state == "conflict" and i.title]
    if conflicts:
        lines.append(t(language, "conflicts", names=_names(conflicts)))
    return lines


def report_lines(report: ld.Report, source: ld.Source, language: str) -> tuple[str, list[str]]:
    """Title and lines shown after copying."""
    counts = []
    projects = sum(1 for i in report.copied if i.kind == "project")
    surveys = sum(1 for i in report.copied if i.kind == "questionnaire")
    if projects:
        counts.append(t(language, "n_projects", n=projects))
    if surveys:
        counts.append(t(language, "n_questionnaires", n=surveys))
    if any(i.kind == "profile" for i in report.copied):
        counts.append(t(language, "n_profile"))
    lines = []
    if counts:
        lines.append(t(language, "done", summary=", ".join(counts)))
    conflicts = [i for i, why in report.skipped if why == "conflict" and i.title]
    if conflicts:
        lines.append(t(language, "conflicts", names=_names(conflicts)))
    if report.failed:
        reason = report.failed[0][1][:160]
        names = ", ".join(i.title or t(language, "profile") for i, _ in report.failed[:4])
        lines.append(t(language, "failed", names=names, reason=reason))
    if report.stopped == "disk_full":
        lines.append(t(language, "disk_full"))
    lines.append(t(language, "kept", folder=str(source.folder)))
    title = t(language, "done_title") if report.ok else t(language, "failed_title")
    return title, lines


def _path_text(value: str) -> ft.Text:
    # Selectable text needs an explicit accessible name (see workspace_components.text).
    return ft.Text(value, selectable=True, semantics_label=value, size=13, weight=ft.FontWeight.W_600)


def migration_dialog(page, source: ld.Source, data_root: Path, language: str, *,
                     on_finished=None, remember_later: bool = True) -> ft.AlertDialog:
    """The dialog that lists ``source`` and copies it on request."""
    status = ft.Text("", size=13, data="migration-status")
    body = ft.Column(tight=True, spacing=8, scroll=ft.ScrollMode.AUTO, width=620, controls=[
        ft.Text(t(language, "found"), size=13), _path_text(str(source.folder)),
        ft.Text(t(language, "into"), size=13), _path_text(str(data_root)),
        *[ft.Text("• " + line, size=13) for line in summary_lines(source, language)],
        ft.Text(t(language, "originals"), size=12, italic=True),
        status,
    ])
    dialog = ft.AlertDialog(modal=True, title=ft.Text(t(language, "title")), content=body,
                            data="migration-dialog")

    def close(e=None):
        page.pop_dialog()
        if on_finished is not None:
            on_finished()

    def later(e=None):
        if remember_later:
            try:
                ld.dismiss(source.folder, data_root)
            except OSError:
                pass
        close()

    async def copy(e=None):
        copy_button.disabled = later_button.disabled = True
        page.update()
        loop = asyncio.get_running_loop()

        def progress(number, total, item):
            def show():
                status.value = t(language, "copying", i=number, n=total,
                                 name=item.title or t(language, "profile"))
                page.update()
            loop.call_soon_threadsafe(show)

        report = await asyncio.to_thread(ld.copy_items, source, data_root, progress=progress)
        title, lines = report_lines(report, source, language)
        dialog.title = ft.Text(title)
        body.controls = [ft.Text(line, size=13, data="migration-result") for line in lines]
        dialog.actions = [ft.TextButton(t(language, "close"), on_click=close,
                                        data="migration-close")]
        page.update()

    copy_button = ft.FilledButton(t(language, "copy"), on_click=copy, data="migration-copy")
    later_button = ft.TextButton(t(language, "later"), on_click=later, data="migration-later")
    dialog.actions = [later_button, copy_button]
    return dialog


def _automatic_offer_allowed() -> bool:
    if os.environ.get("SRA_OFFER_MIGRATION", "").strip() == "1":
        return True
    if os.environ.get("SRA_DATA_DIR", "").strip():
        return False          # tests and portable use choose their own folder
    from startup_diagnostics import is_packaged

    return is_packaged()


async def offer_at_startup(page, source_root: Path, language: str) -> ld.Source | None:
    """After the interface is ready: offer to copy an earlier version's data
    found in a known place, unless the researcher already chose "Not now"."""
    if not _automatic_offer_allowed():
        return None
    from app_paths import data_root

    root = data_root(source_root)
    try:
        sources = await asyncio.to_thread(ld.find, source_root, root)
    except Exception:
        return None
    for source in sources:
        if source.pending and not ld.is_dismissed(source.folder, root):
            page.show_dialog(migration_dialog(page, source, root, language))
            return source
    return None


def open_folder(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # noqa: S606 - the researcher's own data folder
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


async def find_in_chosen_folder(page, chosen: str | None, data_root: Path,
                                language: str) -> str:
    """Look in a folder the researcher chose; show the dialog or say why not."""
    if not chosen:
        return ""
    sources = await asyncio.to_thread(ld.find_in, Path(chosen), data_root)
    pending = [s for s in sources if s.pending]
    if pending:
        page.show_dialog(migration_dialog(page, pending[0], data_root, language,
                                          remember_later=False))
        return ""
    if sources:
        return t(language, "nothing_new", folder=chosen)
    return t(language, "none_found", folder=chosen)


_PICKERS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def folder_picker(page) -> ft.FilePicker:
    """One directory picker per page, registered as a page service once."""
    picker = _PICKERS.get(page)
    if picker is None:
        picker = ft.FilePicker()
        page.services.append(picker)
        _PICKERS[page] = picker
    return picker


def show_data_folder(page, source_root: Path, language: str) -> ft.AlertDialog:
    """Classic window: Settings → Your data…"""
    from app_paths import data_root

    root = data_root(source_root)
    message = ft.Text("", size=13, data="data-folder-message")
    picker = folder_picker(page)

    async def find(e=None):
        message.value = t(language, "searching")
        page.update()
        try:
            chosen = await picker.get_directory_path(dialog_title=t(language, "pick"))
        except Exception:
            chosen = None
        page.pop_dialog()
        note = await find_in_chosen_folder(page, chosen, root, language)
        if note:
            page.show_dialog(_note_dialog(page, note, language))

    dialog = ft.AlertDialog(
        modal=False, title=ft.Text(t(language, "folder_title")), data="data-folder-dialog",
        content=ft.Column(tight=True, spacing=8, width=600, controls=[
            ft.Text(t(language, "folder_body"), size=13), _path_text(str(root)),
            ft.Text(t(language, "folder_note"), size=12, italic=True), message]),
        actions=[ft.TextButton(t(language, "find"), on_click=find, data="data-folder-find"),
                 ft.TextButton(t(language, "open_folder"), on_click=lambda e: open_folder(root),
                               data="data-folder-open"),
                 ft.TextButton(t(language, "close"), on_click=lambda e: page.pop_dialog())])
    page.show_dialog(dialog)
    return dialog


def _note_dialog(page, note: str, language: str) -> ft.AlertDialog:
    return ft.AlertDialog(title=ft.Text(t(language, "folder_title")),
                          content=ft.Text(note, size=13, data="data-folder-note"),
                          actions=[ft.TextButton(t(language, "close"),
                                                 on_click=lambda e: page.pop_dialog())])
