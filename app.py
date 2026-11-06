"""Desktop entry point: show a light startup screen at once, then load the app.

The research workspace (``research_app``) imports pandas, SciPy, statsmodels,
pingouin and matplotlib, which can take many seconds on a cold Windows start
(antivirus scanning, first launch). Importing them before ``ft.run`` used to
leave the native window black until everything was loaded. This launcher
imports only Flet and the standard library, paints a startup screen, imports
the workspace in a background thread, then swaps in the real interface.

Every launch appends phase timings to a local ``startup.log`` (see
``startup_diagnostics``). A failure is shown in the window with the log
location instead of a silent black screen.

Test-only switch: ``SRA_STARTUP_SMOKE=<result.json>`` writes the timings and
an interface summary after the normal startup, keeps the window open for
``SRA_STARTUP_SMOKE_HOLD`` seconds (default 10) for screenshots, then exits.
"""

import time

_PROCESS_T0 = time.perf_counter()

import asyncio
import importlib
import json
import os
from pathlib import Path

from startup_diagnostics import StartupTimeline, write_startup_record, writable_log_directory


def _hold_instance_mutex():
    """Windows: hold a named mutex while the application runs. The installer
    waits for it to disappear before it replaces the program files, so an
    update never overwrites a running program (#44, #45)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        from app_identity import MUTEX

        create = ctypes.windll.kernel32.CreateMutexW
        create.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        create.restype = ctypes.c_void_p
        return create(None, False, MUTEX) or None
    except Exception:   # never prevent the start
        return None


_INSTANCE_MUTEX = _hold_instance_mutex()

TIMELINE = StartupTimeline(_PROCESS_T0)

from analysis_selftest import maybe_run_from_environment as maybe_run_analysis_selftest
from ocr_selftest import maybe_run_from_environment

# Packaging CI / support diagnostics only: when SRA_OCR_SELFTEST is set the
# bundled OCR engine is exercised on a synthetic scan and the process exits;
# SRA_ANALYSIS_SELFTEST runs every statistical procedure on the bundled
# fictional examples the same way and exits.
maybe_run_from_environment()
maybe_run_analysis_selftest()

import flet as ft

TIMELINE.mark("flet_imported")

BACKGROUND = "#F5F7FC"
SPLASH_TEXT = {
    "en": ("Statistical Research Assistant", "Starting… loading statistics libraries",
           "Preparing the workspace…", "The application could not start."),
    "lv": ("Statistical Research Assistant", "Startē… ielādē statistikas bibliotēkas",
           "Sagatavo darba vidi…", "Lietotni neizdevās palaist."),
    "ru": ("Statistical Research Assistant", "Запуск… загрузка статистических библиотек",
           "Подготовка рабочей области…", "Не удалось запустить приложение."),
}


def _language() -> str:
    try:
        from app_preferences import load_preferences

        code = load_preferences().language
    except Exception:
        return "en"
    return code if code in SPLASH_TEXT else "en"


def build_splash(language: str = "en") -> tuple[ft.Control, ft.Text]:
    title, message, _, _ = SPLASH_TEXT[language]
    status = ft.Text(message, size=13, color="#536781")
    view = ft.Container(
        expand=True, alignment=ft.Alignment.CENTER, bgcolor=BACKGROUND,
        content=ft.Column(
            tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=14,
            controls=[
                ft.Text(title, size=24, weight="bold", color="#172A43"),
                ft.ProgressRing(width=34, height=34, stroke_width=3, color="#2755A1"),
                status,
                ft.Text("Local processing only · no uploads", size=11, color="#8391A5"),
            ],
        ),
        data="startup-splash",
    )
    return view, status


def show_failure(page, language: str, log_path: Path | None, error: BaseException) -> None:
    _, _, _, headline = SPLASH_TEXT[language]
    where = str(log_path) if log_path else "(no writable log folder)"
    page.controls.clear()
    page.add(ft.Container(
        padding=30, bgcolor=BACKGROUND, expand=True,
        content=ft.Column(
            spacing=12,
            controls=[
                ft.Text(headline, size=22, weight="bold", color="#9B1C1C"),
                ft.Text(f"{type(error).__name__}: {str(error)[:300]}", selectable=True),
                ft.Text(f"Startup log: {where}", selectable=True, color="#536781"),
                ft.Text(
                    "Please send this log file to the developers. It contains "
                    "timings and code locations only, no questionnaire data.",
                    size=12, color="#536781",
                ),
            ],
        ),
        data="startup-failure",
    ))
    page.update()


def _smoke_summary(page) -> dict:
    texts = []

    def walk(control, depth=0):
        if control is None or depth > 40 or len(texts) > 4000:
            return
        if isinstance(control, (list, tuple)):
            for item in control:
                walk(item, depth + 1)
            return
        value = getattr(control, "value", None)
        if isinstance(control, ft.Text) and isinstance(value, str):
            texts.append(value)
        for name in ("controls", "content"):
            walk(getattr(control, name, None), depth + 1)

    walk(list(page.controls))
    return {
        "top_level_controls": len(page.controls),
        "splash_present": any(getattr(c, "data", None) == "startup-splash" for c in page.controls),
        "failure_present": any(getattr(c, "data", None) == "startup-failure" for c in page.controls),
        "has_home_banner": any("YOUR RESEARCH WORKSPACE" in t for t in texts),
        "workspace_present": any(getattr(c, "data", None) == "workspace-root"
                                 for c in page.controls),
        "text_controls": len(texts),
    }


async def start(page, *, import_workspace=None, timeline: StartupTimeline = TIMELINE):
    """Splash → background import → full interface (or a visible failure)."""
    timeline.mark("page_connected")
    language = _language()
    page.title = "Statistical Research Assistant"
    page.bgcolor = BACKGROUND
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    try:
        page.window.width = 1200
        page.window.height = 720
        page.window.visible = True
    except AttributeError:
        pass
    splash, status = build_splash(language)
    page.add(splash)
    page.update()
    timeline.mark("splash_shown")
    try:
        await page.window.center()
    except Exception:
        pass
    importer = import_workspace or (lambda: importlib.import_module("research_app"))
    try:
        workspace = await asyncio.to_thread(importer)
        timeline.mark("workspace_imported")
        status.value = SPLASH_TEXT[language][2]
        page.update()
        await workspace.main(page, startup=timeline)
        timeline.mark("interface_ready")
        timeline.succeed()
        _after_start(page, language)
    except Exception as error:  # never leave a blank/black window
        timeline.fail(error)
        show_failure(page, language, writable_log_directory(), error)
    finally:
        log = write_startup_record(timeline)
        smoke = os.environ.get("SRA_STARTUP_SMOKE", "").strip()
        if smoke:
            result = {
                **timeline.record(), "log": str(log) if log else None,
                "pid": os.getpid(), **_smoke_summary(page),
            }
            Path(smoke).write_text(json.dumps(result, indent=1), encoding="utf-8")
            hold = float(os.environ.get("SRA_STARTUP_SMOKE_HOLD", "10") or 10)
            asyncio.get_running_loop().call_later(hold, os._exit, 0 if timeline.outcome == "ok" else 1)


def _after_start(page, language: str) -> None:
    """Work that waits until the window is usable and never blocks it: offer
    to copy research data an earlier version kept elsewhere (#44)."""
    if os.environ.get("SRA_STARTUP_SMOKE", "").strip():
        return   # startup measurements only
    try:
        import data_ui

        page.run_task(data_ui.offer_at_startup, page, Path(__file__).resolve().parent, language)
    except Exception:
        pass


async def main(page: ft.Page):
    await start(page)


if __name__ == "__main__":
    ft.run(main)
