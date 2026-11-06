"""Updates inside the application (Stage 35, #45): the interface.

- ``open_dialog``: About and updates. Version, channel and build; Check for
  updates; when a newer version exists: "A new version is available —
  1.1.0", What's new, Update now / Later / Release notes; download
  progress with Cancel; every refusal explained in words.
- ``after_start``: once the window is usable, report the outcome of an
  update started by the previous run ("Updated to version 1.1.0. Your
  projects and research data are preserved."), then check automatically
  (at most once a day, if enabled) and show a banner when an update exists.

The work is done by ``update_client``; nothing here talks to the network.
"""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path

import flet as ft

import app_identity
import update_client as uc

AUTOMATIC_DELAY_SECONDS = 8
BEFORE_EXIT: list = []      # callbacks that close open projects before an update

TEXT = {
    "en": {
        "title": "About and updates", "menu": "Check for updates…",
        "version": "Version {version}", "channel": "Channel: {channel}",
        "channel.stable": "stable", "channel.preview": "preview", "channel.test": "test",
        "channel.source": "source checkout",
        "build": "Build {build} · {commit}", "unsigned": "Unsigned preview build",
        "signed": "Code-signed build",
        "check": "Check for updates", "checking": "Checking for updates…",
        "automatic": "Check for updates automatically (at most once a day)",
        "privacy": "A check downloads a small public file from GitHub; nothing about you or "
                   "your research is sent. Without a connection the application works as usual.",
        "latest": "You have the latest version ({version}).",
        "available": "A new version is available — {version}",
        "whats_new": "What's new", "limitations": "Known limitations",
        "update_now": "Update now", "later": "Later", "notes": "Release notes",
        "downloading": "Downloading the update: {done} of {total} MB…",
        "verifying": "Checking the download (checksum and code signature)…",
        "preparing": "Backing up your project databases before the update…",
        "restarting": "Installing version {version}. The application closes now and starts "
                      "again by itself; your projects stay where they are.",
        "cancel": "Cancel", "close": "Close",
        "cancelled": "The download was cancelled. Nothing was installed.",
        "updated_title": "Updated to version {version}",
        "updated": "Your projects and research data are preserved.",
        "updated_checked": "All {n} projects are in place.",
        "updated_missing": "{n} project(s) listed before the update are not in the data folder "
                           "({ids}). A copy of every project database made just before the "
                           "update is in {backup}.",
        "view_new": "View what's new",
        "not_installed_title": "The update was not installed",
        "not_installed": "Version {version} was not installed; this is still version "
                         "{current}. Your data is unchanged. Installer log: {log}",
        "manual.too_old": "Version {version} cannot be installed directly from this version. "
                          "Use the release page.",
        "manual.unsigned": "Version {version} is not code-signed, so it is not installed "
                           "automatically.",
        "manual.wrong_publisher": "Version {version} is signed by another publisher, so it is "
                                  "not installed automatically.",
        "error.offline": "The update server could not be reached. The application works normally "
                         "without a connection; try again later.",
        "error.unavailable": "The update server did not answer. Try again later.",
        "error.not_configured": "This build has no update channel (a source checkout or a "
                                "local build).",
        "error.no_keys": "This build has no key to verify updates with, so it cannot update "
                         "itself.",
        "error.unsigned": "The update information carries no signature, so it was rejected.",
        "error.bad_signature": "The update information is not signed by the publisher of this "
                               "application, so it was rejected.",
        "error.malformed": "The update information is damaged or in an unknown format, so it "
                           "was rejected.",
        "error.wrong_app": "The update information belongs to another application, so it was "
                           "rejected.",
        "error.wrong_channel": "The update information is for another release channel, so it "
                               "was rejected.",
        "error.bad_url": "The update would come from an address that is not allowed, so it was "
                         "rejected.",
        "error.damaged": "The downloaded file does not match the published checksum, so it was "
                         "deleted and nothing was installed.",
        "error.interrupted": "The download was interrupted. Try again: it continues where it "
                             "stopped.",
        "error.cancelled": "The download was cancelled. Nothing was installed.",
        "error.bad_code_signature": "The downloaded installer's code signature is not valid, so "
                                    "it was not started.",
        "error.wrong_publisher": "The downloaded installer is signed by another publisher, so it "
                                 "was not started.",
        "error.launch_failed": "The installer could not be started. Nothing was changed.",
        "error.disk": "There is not enough disk space for the update. Nothing was changed.",
        "error.unknown": "The update could not be completed. Nothing was changed.",
    },
    "lv": {
        "title": "Par programmu un atjauninājumi", "menu": "Meklēt atjauninājumus…",
        "version": "Versija {version}", "channel": "Kanāls: {channel}",
        "channel.stable": "stabilais", "channel.preview": "priekšskatījums",
        "channel.test": "tests", "channel.source": "pirmkoda kopija",
        "build": "Būvējums {build} · {commit}", "unsigned": "Neparakstīts priekšskatījuma būvējums",
        "signed": "Ar koda parakstu parakstīts būvējums",
        "check": "Meklēt atjauninājumus", "checking": "Meklē atjauninājumus…",
        "automatic": "Meklēt atjauninājumus automātiski (ne biežāk kā reizi dienā)",
        "privacy": "Pārbaude lejupielādē nelielu publisku failu no GitHub; nekas par jums vai "
                   "jūsu pētījumu netiek nosūtīts. Bez savienojuma lietotne darbojas kā parasti.",
        "latest": "Jums ir jaunākā versija ({version}).",
        "available": "Pieejama jauna versija — {version}",
        "whats_new": "Kas jauns", "limitations": "Zināmie ierobežojumi",
        "update_now": "Atjaunināt tagad", "later": "Vēlāk", "notes": "Laidiena piezīmes",
        "downloading": "Lejupielādē atjauninājumu: {done} no {total} MB…",
        "verifying": "Pārbauda lejupielādi (kontrolsummu un koda parakstu)…",
        "preparing": "Pirms atjaunināšanas saglabā projektu datu bāzu rezerves kopijas…",
        "restarting": "Instalē versiju {version}. Lietotne tagad aizveras un pati startējas no "
                      "jauna; jūsu projekti paliek savā vietā.",
        "cancel": "Atcelt", "close": "Aizvērt",
        "cancelled": "Lejupielāde atcelta. Nekas netika instalēts.",
        "updated_title": "Atjaunināts uz versiju {version}",
        "updated": "Jūsu projekti un pētījuma dati ir saglabāti.",
        "updated_checked": "Visi {n} projekti ir savā vietā.",
        "updated_missing": "{n} projekti, kas bija sarakstā pirms atjaunināšanas, nav datu mapē "
                           "({ids}). Visu projektu datu bāzu kopija, kas izveidota tieši pirms "
                           "atjaunināšanas, atrodas mapē {backup}.",
        "view_new": "Skatīt jaunumus",
        "not_installed_title": "Atjauninājums netika instalēts",
        "not_installed": "Versija {version} netika instalēta; šī joprojām ir versija {current}. "
                         "Jūsu dati nav mainīti. Instalētāja žurnāls: {log}",
        "manual.too_old": "Versiju {version} nevar instalēt tieši no šīs versijas. Izmantojiet "
                          "laidiena lapu.",
        "manual.unsigned": "Versijai {version} nav koda paraksta, tāpēc tā netiek instalēta "
                           "automātiski.",
        "manual.wrong_publisher": "Versiju {version} parakstījis cits izdevējs, tāpēc tā netiek "
                                  "instalēta automātiski.",
        "error.offline": "Atjauninājumu serveris nav sasniedzams. Lietotne bez savienojuma "
                         "darbojas normāli; mēģiniet vēlāk.",
        "error.unavailable": "Atjauninājumu serveris neatbildēja. Mēģiniet vēlāk.",
        "error.not_configured": "Šim būvējumam nav atjauninājumu kanāla (pirmkoda kopija vai "
                                "lokāls būvējums).",
        "error.no_keys": "Šim būvējumam nav atslēgas atjauninājumu pārbaudei, tāpēc tas nevar "
                         "sevi atjaunināt.",
        "error.unsigned": "Atjauninājuma informācija nav parakstīta, tāpēc tā noraidīta.",
        "error.bad_signature": "Atjauninājuma informāciju nav parakstījis šīs lietotnes izdevējs, "
                               "tāpēc tā noraidīta.",
        "error.malformed": "Atjauninājuma informācija ir bojāta vai nezināmā formātā, tāpēc tā "
                           "noraidīta.",
        "error.wrong_app": "Atjauninājuma informācija attiecas uz citu lietotni, tāpēc tā "
                           "noraidīta.",
        "error.wrong_channel": "Atjauninājuma informācija ir citam laidienu kanālam, tāpēc tā "
                               "noraidīta.",
        "error.bad_url": "Atjauninājums tiktu lejupielādēts no neatļautas adreses, tāpēc tas "
                         "noraidīts.",
        "error.damaged": "Lejupielādētais fails neatbilst publicētajai kontrolsummai, tāpēc tas "
                         "izdzēsts un nekas netika instalēts.",
        "error.interrupted": "Lejupielāde tika pārtraukta. Mēģiniet vēlreiz: tā turpināsies no "
                             "vietas, kur apstājās.",
        "error.cancelled": "Lejupielāde atcelta. Nekas netika instalēts.",
        "error.bad_code_signature": "Lejupielādētā instalētāja koda paraksts nav derīgs, tāpēc "
                                    "tas netika palaists.",
        "error.wrong_publisher": "Lejupielādēto instalētāju parakstījis cits izdevējs, tāpēc tas "
                                 "netika palaists.",
        "error.launch_failed": "Instalētāju neizdevās palaist. Nekas netika mainīts.",
        "error.disk": "Atjauninājumam nepietiek vietas diskā. Nekas netika mainīts.",
        "error.unknown": "Atjaunināšanu neizdevās pabeigt. Nekas netika mainīts.",
    },
    "ru": {
        "title": "О программе и обновления", "menu": "Проверить обновления…",
        "version": "Версия {version}", "channel": "Канал: {channel}",
        "channel.stable": "стабильный", "channel.preview": "предварительный",
        "channel.test": "тестовый", "channel.source": "исходный код",
        "build": "Сборка {build} · {commit}", "unsigned": "Неподписанная предварительная сборка",
        "signed": "Сборка с цифровой подписью кода",
        "check": "Проверить обновления", "checking": "Проверка обновлений…",
        "automatic": "Проверять обновления автоматически (не чаще раза в день)",
        "privacy": "Проверка загружает небольшой публичный файл с GitHub; ничего о вас или "
                   "вашем исследовании не отправляется. Без подключения приложение работает "
                   "как обычно.",
        "latest": "У вас последняя версия ({version}).",
        "available": "Доступна новая версия — {version}",
        "whats_new": "Что нового", "limitations": "Известные ограничения",
        "update_now": "Обновить сейчас", "later": "Позже", "notes": "Примечания к выпуску",
        "downloading": "Загрузка обновления: {done} из {total} МБ…",
        "verifying": "Проверка загрузки (контрольная сумма и подпись кода)…",
        "preparing": "Резервное копирование баз данных проектов перед обновлением…",
        "restarting": "Устанавливается версия {version}. Приложение сейчас закроется и само "
                      "запустится снова; ваши проекты остаются на месте.",
        "cancel": "Отмена", "close": "Закрыть",
        "cancelled": "Загрузка отменена. Ничего не установлено.",
        "updated_title": "Обновлено до версии {version}",
        "updated": "Ваши проекты и исследовательские данные сохранены.",
        "updated_checked": "Все проекты на месте: {n}.",
        "updated_missing": "Проекты из списка до обновления отсутствуют в папке данных: {n} "
                           "({ids}). Копия всех баз данных проектов, сделанная непосредственно "
                           "перед обновлением, находится в папке {backup}.",
        "view_new": "Посмотреть, что нового",
        "not_installed_title": "Обновление не установлено",
        "not_installed": "Версия {version} не установлена; это по-прежнему версия {current}. "
                         "Ваши данные не изменены. Журнал установщика: {log}",
        "manual.too_old": "Версию {version} нельзя установить напрямую из этой версии. "
                          "Воспользуйтесь страницей выпуска.",
        "manual.unsigned": "Версия {version} не подписана, поэтому не устанавливается "
                           "автоматически.",
        "manual.wrong_publisher": "Версия {version} подписана другим издателем, поэтому не "
                                  "устанавливается автоматически.",
        "error.offline": "Сервер обновлений недоступен. Без подключения приложение работает "
                         "нормально; повторите позже.",
        "error.unavailable": "Сервер обновлений не ответил. Повторите позже.",
        "error.not_configured": "У этой сборки нет канала обновлений (исходный код или "
                                "локальная сборка).",
        "error.no_keys": "У этой сборки нет ключа для проверки обновлений, поэтому она не может "
                         "обновиться сама.",
        "error.unsigned": "Сведения об обновлении не подписаны, поэтому отклонены.",
        "error.bad_signature": "Сведения об обновлении подписаны не издателем этого приложения, "
                               "поэтому отклонены.",
        "error.malformed": "Сведения об обновлении повреждены или в неизвестном формате, "
                           "поэтому отклонены.",
        "error.wrong_app": "Сведения об обновлении относятся к другому приложению, поэтому "
                           "отклонены.",
        "error.wrong_channel": "Сведения об обновлении относятся к другому каналу выпусков, "
                               "поэтому отклонены.",
        "error.bad_url": "Обновление пришлось бы загружать с недопустимого адреса, поэтому оно "
                         "отклонено.",
        "error.damaged": "Загруженный файл не совпадает с опубликованной контрольной суммой, "
                         "поэтому удалён; ничего не установлено.",
        "error.interrupted": "Загрузка прервана. Повторите: она продолжится с места остановки.",
        "error.cancelled": "Загрузка отменена. Ничего не установлено.",
        "error.bad_code_signature": "Подпись кода загруженного установщика недействительна, "
                                    "поэтому он не запущен.",
        "error.wrong_publisher": "Загруженный установщик подписан другим издателем, поэтому он "
                                 "не запущен.",
        "error.launch_failed": "Не удалось запустить установщик. Ничего не изменено.",
        "error.disk": "Недостаточно места на диске для обновления. Ничего не изменено.",
        "error.unknown": "Обновление не удалось завершить. Ничего не изменено.",
    },
}


def t(language: str, key: str, **values) -> str:
    table = TEXT.get(language, TEXT["en"])
    return table.get(key, TEXT["en"].get(key, key)).format(**values)


def error_text(language: str, reason: str) -> str:
    key = f"error.{reason}"
    return t(language, key) if key in TEXT["en"] else t(language, "error.unknown")


def register_before_exit(callback) -> None:
    """The workspace registers how to close its open project before an update."""
    if callback not in BEFORE_EXIT:
        BEFORE_EXIT.append(callback)


def _data_root(source_root: Path) -> Path:
    from app_paths import data_root

    return data_root(source_root)


def version_lines(language: str, build: app_identity.BuildInfo) -> list[str]:
    channel = t(language, f"channel.{build.channel}") if f"channel.{build.channel}" in TEXT["en"] \
        else build.channel
    lines = [t(language, "version", version=build.version), t(language, "channel", channel=channel)]
    if build.build or build.commit:
        lines.append(t(language, "build", build=build.build or "-", commit=(build.commit or "-")[:12]))
    if build.distributed:
        lines.append(t(language, "signed" if build.signed else "unsigned"))
    return lines


class UpdateDialog:
    """The About and updates dialog; one per page at a time."""

    def __init__(self, page, source_root: Path, language: str, *,
                 build: app_identity.BuildInfo | None = None):
        self.page, self.language = page, language
        self.build = build or app_identity.build_info()
        self.data_root = _data_root(source_root)
        self.offer = None
        self.cancel = threading.Event()
        self.busy = False
        self.status = ft.Text("", size=13, data="update-status")
        self.progress = ft.ProgressBar(value=0, visible=False, width=560, data="update-progress")
        self.details = ft.Column(spacing=6, visible=False, data="update-details")
        auto = uc.state(self.data_root).get("automatic", True)
        self.automatic = ft.Checkbox(label=t(language, "automatic"), value=auto,
                                     on_change=self._toggle_automatic, data="update-automatic")
        body = [ft.Text(line, size=13, data="update-version") for line in version_lines(language, self.build)]
        body += [self.automatic, ft.Text(t(language, "privacy"), size=12, italic=True),
                 self.status, self.progress, self.details]
        self.dialog = ft.AlertDialog(
            modal=True, title=ft.Text(t(language, "title")), data="update-dialog",
            content=ft.Column(body, tight=True, spacing=8, width=600, scroll=ft.ScrollMode.AUTO))
        self._actions_idle()

    # ----------------------------------------------------------- actions
    def _button(self, key, handler, data, filled=False):
        kind = ft.FilledButton if filled else ft.TextButton
        return kind(t(self.language, key), on_click=handler, data=data)

    def _actions_idle(self):
        self.dialog.actions = [self._button("check", self.check, "update-check"),
                               self._button("close", self.close, "update-close")]

    def _actions_offer(self):
        actions = [self._button("later", self.later, "update-later")]
        if self.offer.manifest.release_notes_url:
            actions.append(self._button("notes", self.notes, "update-notes"))
        actions.append(self._button("update_now", self.update_now, "update-now", filled=True))
        self.dialog.actions = actions

    def _refresh(self):
        try:
            self.page.update()
        except Exception:
            pass

    def _toggle_automatic(self, e=None):
        current = uc.state(self.data_root)
        current["automatic"] = bool(self.automatic.value)
        uc.save_state(self.data_root, current)

    def close(self, e=None):
        self.cancel.set()
        self.page.pop_dialog()

    def notes(self, e=None):
        url = self.offer.manifest.release_notes_url if self.offer else ""
        if url:
            self.page.launch_url(url)

    def later(self, e=None):
        if self.offer and self.offer.manifest:
            uc.snooze(self.data_root, str(self.offer.manifest.version))
        self.close()

    def show_offer(self, offer):
        self.offer = offer
        manifest = offer.manifest
        self.status.value = t(self.language, "available", version=str(manifest.version))
        self.status.weight = ft.FontWeight.BOLD
        rows = []
        changes = manifest.text("changelog", self.language)
        if changes:
            rows += [ft.Text(t(self.language, "whats_new"), weight=ft.FontWeight.W_600, size=13),
                     ft.Text(changes, size=13, data="update-changelog")]
        limits = manifest.text("limitations", self.language)
        if limits:
            rows += [ft.Text(t(self.language, "limitations"), weight=ft.FontWeight.W_600, size=13),
                     ft.Text(limits, size=13)]
        self.details.controls = rows
        self.details.visible = bool(rows)
        self._actions_offer()

    def show_message(self, text: str):
        self.status.value = text
        self.status.weight = None
        self.details.visible = False
        self.progress.visible = False
        self._actions_idle()

    # ------------------------------------------------------------- check
    async def check(self, e=None):
        if self.busy:
            return
        self.busy = True
        self.show_message(t(self.language, "checking"))
        self._refresh()
        try:
            offer = await asyncio.to_thread(uc.check, self.build)
            uc.remember_check(self.data_root, offer)
        except uc.UpdateError as error:
            self.show_message(error_text(self.language, error.reason))
        else:
            if offer.state == "update":
                self.show_offer(offer)
            elif offer.state == "manual":
                self.show_message(t(self.language, f"manual.{offer.reason}",
                                    version=str(offer.manifest.version)))
            else:
                self.show_message(t(self.language, "latest", version=self.build.version))
        finally:
            self.busy = False
        self._refresh()

    # ------------------------------------------------------------ update
    async def update_now(self, e=None):
        if self.busy or not self.offer:
            return
        self.busy = True
        manifest = self.offer.manifest
        self.cancel.clear()
        self.progress.visible, self.progress.value = True, 0
        self.dialog.actions = [self._button("cancel", self._cancel, "update-cancel")]
        self.status.value = t(self.language, "downloading", done=0,
                              total=round(manifest.installer.size / 1048576))
        self._refresh()
        loop = asyncio.get_running_loop()

        def progress(done, total):
            def show():
                self.progress.value = done / total if total else None
                self.status.value = t(self.language, "downloading", done=round(done / 1048576),
                                      total=round(total / 1048576))
                self._refresh()
            loop.call_soon_threadsafe(show)

        folder = self.data_root / "updates"
        try:
            installer = await asyncio.to_thread(uc.download, manifest, folder, self.build,
                                                progress=progress, cancel=self.cancel)
            self.status.value, self.progress.value = t(self.language, "verifying"), None
            self.dialog.actions = []
            self._refresh()
            await asyncio.to_thread(uc.verify_installer, installer, manifest, self.build)
            self.status.value = t(self.language, "preparing")
            self._refresh()
            for callback in list(BEFORE_EXIT):
                try:
                    callback()
                except Exception:
                    pass
            record = await asyncio.to_thread(uc.prepare, self.data_root, installer, manifest,
                                             self.build)
            try:
                await asyncio.to_thread(uc.launch_installer, record)
            except OSError as error:
                (self.data_root / "updates" / uc.PENDING).unlink(missing_ok=True)
                raise uc.UpdateError("launch_failed", str(error)) from error
        except uc.UpdateError as error:
            self.busy = False
            self.show_message(error_text(self.language, error.reason))
            self._actions_offer()
            self._refresh()
            return
        except OSError as error:
            self.busy = False
            reason = "disk" if getattr(error, "errno", None) == 28 else "unknown"
            self.show_message(error_text(self.language, reason))
            self._actions_offer()
            self._refresh()
            return
        self.status.value = t(self.language, "restarting", version=str(manifest.version))
        self.progress.visible = False
        self._refresh()
        await close_application(self.page)

    def _cancel(self, e=None):
        self.cancel.set()


async def close_application(page) -> None:
    """Close the window so the installer can replace the program."""
    await asyncio.sleep(1.5)
    try:
        await page.window.destroy()
    except Exception:
        pass
    await asyncio.sleep(5)
    os._exit(0)   # the window is gone; make sure the process (and its mutex) is too


def open_dialog(page, source_root: Path, language: str, *, offer=None, check: bool = True,
                build: app_identity.BuildInfo | None = None) -> UpdateDialog:
    dialog = UpdateDialog(page, source_root, language, build=build)
    page.show_dialog(dialog.dialog)
    if offer is not None:
        dialog.show_offer(offer)
        dialog._refresh()
    elif check and dialog.build.distributed:
        page.run_task(dialog.check)
    return dialog


def outcome_dialog(page, outcome: dict, language: str, source_root: Path) -> ft.AlertDialog:
    """After a restart: what the update did."""
    if outcome["state"] == "updated":
        lines = [t(language, "updated")]
        if outcome["missing_projects"]:
            lines.append(t(language, "updated_missing", n=len(outcome["missing_projects"]),
                           ids=", ".join(outcome["missing_projects"][:5]), backup=outcome.get("backup", "")))
        else:
            lines.append(t(language, "updated_checked", n=outcome["projects_kept"]))
        title = t(language, "updated_title", version=outcome["to"])
    else:
        lines = [t(language, "not_installed", version=outcome.get("to", "?"),
                   current=outcome.get("now", "?"), log=outcome.get("log", ""))]
        title = t(language, "not_installed_title")
    changes = (outcome.get("changelog") or {}).get(language) or (outcome.get("changelog") or {}).get("en")
    details = ft.Column([ft.Text(changes, size=13, data="update-changelog")], visible=False)

    def show_new(e=None):
        details.visible = True
        try:
            page.update()
        except Exception:
            pass

    actions = [ft.TextButton(t(language, "close"), on_click=lambda e: page.pop_dialog(),
                             data="update-outcome-close")]
    if changes and outcome["state"] == "updated":
        actions.insert(0, ft.TextButton(t(language, "view_new"), on_click=show_new,
                                        data="update-view-new"))
    return ft.AlertDialog(modal=False, title=ft.Text(title), data="update-outcome",
                          content=ft.Column([*(ft.Text(line, size=13, data="update-outcome-line")
                                               for line in lines), details],
                                            tight=True, spacing=8, width=560),
                          actions=actions)


def _automatic_allowed(build: app_identity.BuildInfo) -> bool:
    if os.environ.get("SRA_STARTUP_SMOKE", "").strip():
        return False
    if os.environ.get("SRA_UPDATE_CHECK", "").strip() == "0":
        return False
    if os.environ.get("SRA_DATA_DIR", "").strip() and os.environ.get("SRA_UPDATE_CHECK") != "1":
        return False      # isolated test runs
    return build.distributed and bool(build.update_keys)


def update_banner(page, offer, source_root: Path, language: str) -> ft.Banner:
    version = str(offer.manifest.version)
    data_root = _data_root(source_root)

    def close(e=None):
        page.pop_dialog()

    def whats_new(e=None):
        close()
        open_dialog(page, source_root, language, offer=offer)

    async def now(e=None):
        close()
        dialog = open_dialog(page, source_root, language, offer=offer)
        await dialog.update_now()

    def later(e=None):
        uc.snooze(data_root, version)
        close()

    return ft.Banner(
        content=ft.Text(t(language, "available", version=version), data="update-banner-text"),
        leading=ft.Icon(ft.Icons.SYSTEM_UPDATE_ALT), data="update-banner",
        actions=[ft.TextButton(t(language, "whats_new"), on_click=whats_new, data="update-banner-new"),
                 ft.TextButton(t(language, "update_now"), on_click=now, data="update-banner-now"),
                 ft.TextButton(t(language, "later"), on_click=later, data="update-banner-later")])


async def automatic_check(page, source_root: Path, language: str, *,
                          build: app_identity.BuildInfo | None = None, delay: float | None = None):
    """Check once a day in the background; never blocks or interrupts work."""
    build = build or app_identity.build_info()
    if not _automatic_allowed(build):
        return None
    data_root = _data_root(source_root)
    if not uc.due(data_root):
        return None
    await asyncio.sleep(AUTOMATIC_DELAY_SECONDS if delay is None else delay)
    try:
        offer = await asyncio.to_thread(uc.check, build)
    except Exception:        # offline or refused: say nothing, try tomorrow
        uc.remember_check(data_root, None)
        return None
    uc.remember_check(data_root, offer)
    if offer.state == "update" and not uc.snoozed(data_root, str(offer.manifest.version)):
        page.show_dialog(update_banner(page, offer, source_root, language))
        return offer
    return None


async def after_start(page, source_root: Path, language: str) -> str:
    """Startup tasks in order: an update's outcome, earlier data, automatic check."""
    data_root = _data_root(source_root)
    try:
        outcome = await asyncio.to_thread(uc.finish, data_root)
    except Exception:
        outcome = None
    shown = ""
    if outcome is not None:
        page.show_dialog(outcome_dialog(page, outcome, language, source_root))
        shown = "outcome"
    else:
        import data_ui

        if await data_ui.offer_at_startup(page, source_root, language) is not None:
            shown = "migration"
    page.run_task(automatic_check, page, source_root, language)
    return shown
