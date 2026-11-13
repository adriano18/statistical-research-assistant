"""Windows: end-to-end journeys on the packaged application (Stage 34.5).

    python tools/windows_gui_e2e.py path\\to\\StatisticalResearchAssistant.exe OUT_DIR

Drives the distributed executable the way a researcher does: real mouse
clicks and key presses on the controls that Windows UI Automation exposes
(Flutter's accessibility tree), the native Open and Save dialogs, and a
real restart of the application. Nothing is mocked: files are chosen in
the system dialogs, written by the application and then opened and checked
here. Numbers in the exported reports are compared with the validated
engine run in this process on the same data.

Journeys (synthetic data only; see JOURNEYS):

* project-a      create project A, open a CSV in the Open dialog, confirm
                 levels, run ANCOVA, save Word/PNG/TXT and the combined
                 report, back up the project (.sra), restart, reopen A and
                 save Word again from the restored result
* project-b      create project B, open other data, switch A ↔ B, check
                 that each shows only its own data and results
* import-30      import a 30-item questionnaire whose items are an image
                 and whose text layer holds a bibliography and a shared
                 response matrix (local OCR), review, create the draft
* review-120     import a 120-item form and review several items: the
                 list must not jump and typing must keep the focus
* responses      publish a questionnaire, collect responses in its form,
                 analyze them as an explicitly named dataset, export CSV +
                 codebook, and return to the original dataset
* import-cope-docx
                 a Word document with two unnumbered 60-item table forms:
                 both shown, the situational one chosen, its own answer
                 options reviewed, 60 items, a draft of exactly 60
* import-scan-lv a scanned Latvian 52-item table: the scan is detected,
                 read with local OCR in Latvian, its legend offered as one
                 documented scale, a draft of exactly 52
* stage36-tasks  eight correlations in one batch, back to the task and run
                 again, each research step opens itself, restart
* stage36-charts eight scales by UCLA_Level in one Kruskal–Wallis batch,
                 Chart Studio (type, layout, title), image clipboard, PNG/SVG,
                 the view for the report, restart
* stage36-groups three quantile groups of UCLA previewed and created, the
                 existing UCLA_Level offered, the batch by the new groups
* stage36-report the batch and a description into one Word report; no
                 reliability coefficient from totals (D5)
* import-damaged a damaged PDF while a document is under review: refused
                 with its reason, the review kept
* blocked-design a quantitative group variable refused in words
* psychometrics  (Stage 36.8, spec F) the scale check of an item-level
                 scale: α, ω and the α-if-item-deleted table on screen,
                 checked against numpy α computed here; the TXT report; no
                 coefficient from totals
* import-resume  (Stage 36.8, spec E) local OCR cancelled while it reads,
                 read again, one item checked, restart, the same PDF brings
                 the saved review back
* negative-paths (Stage 36.8) saving into a read-only folder and over a
                 read-only file refused in words; the AI assistant without a
                 provider; an AI permission allowed and revoked
* confirmations  (review K1, spec B) other outcomes after a run keep the
                 design confirmation and clear the data one; nothing runs
                 until it is given again; another group clears both
* report-composition
                 (review K2, spec G) report order, a note, a reviewed check,
                 title, a section left out and Latvian, kept over a restart
                 and in the Word report; none of it in a second project

Every step is recorded in OUT_DIR: a screenshot, the UI Automation tree
when something is missing, an animated recording per journey
(``<journey>.gif``) and ``gui-e2e-result.json`` with the verdict. Exit
code 0 only if every journey passed.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
os.environ.setdefault("MPLBACKEND", "Agg")

WINDOW_TITLE = "Statistical Research Assistant"
CONTROL_TYPES_CLICKABLE = ("Button", "MenuItem", "ListItem", "TabItem", "Hyperlink",
                           "CheckBox", "RadioButton", "Text", "Group", "Custom", "Pane")


# Control types whose text is their value (Flutter's selectable text, fields).
TEXT_FIELDS = ("Edit", "Document")


def T(key: str, **values) -> str:
    """The English interface text for ``key`` (the app runs in English)."""
    from workspace_text import T as TABLE

    text = TABLE[key][0]
    return text.format(**values) if values else text


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text))[:60].strip("-").lower() or "x"


def escape_keys(text: str) -> str:
    """Text for pywinauto.keyboard.send_keys, typed literally."""
    return "".join("{" + c + "}" if c in "{}[]()+^%~" else c for c in text)


class StepFailure(AssertionError):
    pass


# ================================================================== windows
FLUTTER_WINDOW_CLASS = "FLUTTER_RUNNER_WIN32_WINDOW"


def ctypes_user32():
    """user32 with the prototypes used here (a private instance: the shared
    ctypes.windll prototypes stay as other code expects them)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    return user32


def top_windows(pid: int | None = None) -> list[dict]:
    """Top-level windows from Win32 (of process ``pid``, or all), with the
    state UI Automation does not show: visible, minimized, class."""
    import ctypes
    from ctypes import wintypes

    try:
        user32 = ctypes_user32()
        visit_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [visit_type, wintypes.LPARAM]
    except Exception:
        return []
    found: list[dict] = []

    def visit(hwnd, _):
        try:
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if pid is None or owner.value == pid:
                name = ctypes.create_unicode_buffer(128)
                user32.GetClassNameW(hwnd, name, 128)
                title = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, title, 256)
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                found.append({"hwnd": hwnd, "pid": owner.value, "class": name.value,
                              "title": title.value, "visible": bool(user32.IsWindowVisible(hwnd)),
                              "minimized": bool(user32.IsIconic(hwnd)),
                              "rect": (rect.left, rect.top, rect.right, rect.bottom)})
        except Exception:
            pass
        return True

    with contextlib.suppress(Exception):
        user32.EnumWindows(visit_type(visit), 0)
    return found


def window_guard_events(log: Path) -> list[dict]:
    """The ``window_guard`` lines of the program's startup log."""
    events = []
    with contextlib.suppress(OSError):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            with contextlib.suppress(ValueError):
                record = json.loads(line)
                if isinstance(record, dict) and record.get("event") == "window_guard":
                    events.append(record)
    return events


# ====================================================================== app
class Gui:
    """One running instance of the packaged application."""

    def __init__(self, exe: Path, data_dir: Path, out: Path, *, real_data: bool = False):
        self.exe, self.data_dir, self.out = exe, data_dir, out
        # Installed-application journeys use the real per-user data folder
        # (%LOCALAPPDATA%\StatisticalResearchAssistant) instead of a temporary one.
        self.real_data = real_data
        self.process: subprocess.Popen | None = None
        self.win = None
        self.handle, self.window_pid = None, None
        self.frames: list = []
        self._recording = None
        self.step_index = 0

    # ----------------------------------------------------------- lifecycle
    def environment(self) -> dict:
        system = os.environ.get("SystemRoot", r"C:\Windows")
        keep = ("SystemRoot", "SYSTEMROOT", "windir", "TEMP", "TMP", "USERPROFILE",
                "LOCALAPPDATA", "APPDATA", "HOMEDRIVE", "HOMEPATH", "USERNAME",
                "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
        env = {key: os.environ[key] for key in keep if key in os.environ}
        env.update({
            # A clean machine: neither the runner's Python nor Tesseract.
            "PATH": f"{system}\\System32;{system};{system}\\System32\\Wbem",
            "SRA_UI": "workspace",
            "SRA_LOG_DIR": str(self.out / "app-logs"),
            # Every document reading writes its stage timings here (ocr_profile).
            "SRA_OCR_PROFILE": str(self.out / "ocr-profiles"),
        })
        if not self.real_data:
            env["SRA_DATA_DIR"] = str(self.data_dir)
        return env

    def start(self, timeout: float = 300, *, ready: str | None = None) -> None:
        from pywinauto import Desktop
        from pywinauto.application import Application

        self.process = subprocess.Popen([str(self.exe)], cwd=str(self.exe.parent),
                                        env=self.environment())
        deadline = time.monotonic() + timeout
        restored = False
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise StepFailure(f"the application exited during startup ({self.process.returncode})")
            # Win32 first (by process id, without UI Automation): run
            # 42319964691 saw the program start (its startup log says ready
            # after 4 s) while UI Automation listed no window for 300 s.
            own = [w for w in top_windows(self.process.pid)
                   if w["class"] == FLUTTER_WINDOW_CLASS and w["visible"]]
            if own and own[0]["minimized"] and not restored:
                print(f"  [window] the program's window is minimized: {own[0]}; restoring it",
                      flush=True)
                with contextlib.suppress(Exception):
                    ctypes_user32().ShowWindow(own[0]["hwnd"], 9)        # SW_RESTORE
                restored = True
            elif own and not own[0]["minimized"]:
                left, top, right, bottom = own[0]["rect"]
                if right - left > 300 and bottom - top > 200:
                    self.handle, self.window_pid = own[0]["hwnd"], own[0]["pid"]
                    break
            with contextlib.suppress(Exception):
                for window in Desktop(backend="uia").windows():
                    try:
                        if window.process_id() == self.process.pid or WINDOW_TITLE in window.window_text():
                            rect = window.rectangle()
                            if rect.width() > 300 and rect.height() > 200:
                                self.handle = window.handle
                                self.window_pid = window.process_id()
                                break
                    except Exception:
                        continue
            if self.handle:
                break
            time.sleep(1)
        if not self.handle:
            self.log_desktop("the application window never appeared")
            raise StepFailure("the application window never appeared")
        app = Application(backend="uia").connect(handle=self.handle)
        self.win = app.window(handle=self.handle)
        self.wait_ready(ready, deadline)
        # Maximize only now: the application sets its window size (1200 x 720)
        # while it starts, which undid an earlier maximize (runs 5-9 worked in
        # 1200 x 720 inside a maximized frame). No set_focus(): pywinauto
        # presses Alt for it, which can leave the system menu waiting.
        self.maximize()

    def wait_ready(self, ready: str | None, deadline: float) -> None:
        # The workspace is ready when its Home page offers to create a project
        # (or, when given, when ``ready`` is shown, e.g. a dialog over Home).
        if ready:
            self.find(regex=re.escape(ready), timeout=max(30, deadline - time.monotonic()),
                      scroll=False, visible=False)
        else:
            self.find(T("project.create"), timeout=max(30, deadline - time.monotonic()),
                      scroll=False, visible=False)

    def running(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        return bool(self.window_pid)

    def attach(self, timeout: float = 300, *, ready: str | None = None) -> bool:
        """Connect to the program that the installer started after an
        in-app update (not a process this driver started), once it shows
        ``ready``. Returns whether its window came to the front by itself
        (checked before this driver touches the window)."""
        from pywinauto import Desktop
        from pywinauto.application import Application

        self.process, self.win, self.handle, self.window_pid = None, None, None, None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self.handle:
            # Flutter's window class: not the installer's own window, whose
            # title also names the application.
            for window in top_windows():
                left, top, right, bottom = window["rect"]
                if (window["class"] == FLUTTER_WINDOW_CLASS and window["visible"]
                        and not window["minimized"] and right - left > 300 and bottom - top > 200):
                    self.handle, self.window_pid = window["hwnd"], window["pid"]
                    break
            with contextlib.suppress(Exception):
                for window in ([] if self.handle else Desktop(backend="uia").windows()):
                    try:
                        if window.class_name() != FLUTTER_WINDOW_CLASS:
                            continue
                        rect = window.rectangle()
                        if rect.width() > 300 and rect.height() > 200:
                            self.handle, self.window_pid = window.handle, window.process_id()
                            break
                    except Exception:
                        continue
            if not self.handle:
                time.sleep(2)
        if not self.handle:
            self.log_desktop("the updated program did not start again")
            raise StepFailure("the updated program did not start again")
        self.win = Application(backend="uia").connect(handle=self.handle).window(handle=self.handle)
        # Wait until it has started before maximizing: it sets its own window
        # size meanwhile, which undid the maximize (run 42319959848: 1200 x 720).
        self.wait_ready(ready, deadline)
        in_front = False
        until = time.monotonic() + 20
        while time.monotonic() < until and not in_front:
            in_front = self.in_front()
            if not in_front:
                time.sleep(0.5)
        print(f"  [window] the updated program {'came' if in_front else 'did NOT come'} "
              f"to the front by itself", flush=True)
        if not in_front:
            self.shot("behind another window")
            self.bring_to_front()       # finish the journey; the caller reports it
        self.maximize()
        return in_front

    def in_front(self) -> bool:
        """Whether a click at the centre of the window reaches this window
        (and not a window above it)."""
        from ctypes import wintypes

        try:
            user32 = ctypes_user32()
            left, top, right, bottom = self.window_box()
            hit = user32.WindowFromPoint(wintypes.POINT((left + right) // 2, (top + bottom) // 2))
            return bool(hit) and user32.GetAncestor(hit, 2) == self.handle      # GA_ROOT
        except Exception:
            return False

    def bring_to_front(self) -> None:
        """Make the window the foreground window without a key press
        (pywinauto's set_focus() presses Alt, which can leave the system
        menu waiting): share the input state of the current foreground
        window's thread for a moment, which Windows requires."""
        import ctypes
        from ctypes import wintypes

        with contextlib.suppress(Exception):
            user32 = ctypes_user32()
            mine = ctypes.windll.kernel32.GetCurrentThreadId()
            foreground = user32.GetForegroundWindow()
            theirs = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
            attached = bool(theirs and theirs != mine and user32.AttachThreadInput(mine, theirs, True))
            try:
                keep = 0x0001 | 0x0002                       # SWP_NOSIZE | SWP_NOMOVE
                user32.SetWindowPos(self.handle, wintypes.HWND(-1), 0, 0, 0, 0, keep)  # TOPMOST
                user32.SetWindowPos(self.handle, wintypes.HWND(-2), 0, 0, 0, 0, keep)  # NOTOPMOST
                user32.BringWindowToTop(self.handle)
                user32.SetForegroundWindow(self.handle)
            finally:
                if attached:
                    user32.AttachThreadInput(mine, theirs, False)
            time.sleep(0.5)
            print(f"  [window] brought to the front by the driver: in front={self.in_front()}",
                  flush=True)

    def maximize(self) -> None:
        import ctypes

        with contextlib.suppress(Exception):
            ctypes.windll.user32.ShowWindow(self.handle, 3)      # SW_MAXIMIZE
        time.sleep(1.5)
        self.close_menus()
        bottom = 0
        with contextlib.suppress(Exception):
            bottom = max(e.element_info.rectangle.bottom for e in self.elements()
                         if (e.element_info.name or "").strip())
        with contextlib.suppress(Exception):
            print(f"  [window] {self.win.window_text()!r} at {self.window_box()}; "
                  f"content reaches y={bottom}", flush=True)

    def stop(self, *, graceful: bool = True) -> None:
        if self.process is None and self.window_pid:
            # Attached after an update: close that process by its id.
            if graceful and self.win is not None:
                with contextlib.suppress(Exception):
                    self.win.close()
                time.sleep(8)
            subprocess.run(["taskkill", "/PID", str(self.window_pid), "/T", "/F"],
                           capture_output=True, check=False)
            self.win, self.handle, self.window_pid = None, None, None
            return
        if self.process is None:
            return
        if graceful and self.win is not None:
            with contextlib.suppress(Exception):
                self.win.close()
            try:
                self.process.wait(timeout=40)
            except subprocess.TimeoutExpired:
                pass
        if self.process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                           capture_output=True, check=False)
            with contextlib.suppress(Exception):
                self.process.wait(timeout=20)
        self.process, self.win, self.handle, self.window_pid = None, None, None, None

    # ------------------------------------------------------------ evidence
    def window_box(self):
        rect = self.win.rectangle()
        return rect.left, rect.top, rect.right, rect.bottom

    def grab(self):
        from PIL import ImageGrab

        return ImageGrab.grab(bbox=self.window_box(), all_screens=True)

    def shot(self, name: str) -> Path | None:
        self.step_index += 1
        target = self.out / "steps" / f"{self.step_index:03d}-{slug(name)}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.grab().save(target)
            return target
        except Exception:
            return None

    def record(self, name: str):
        """Context manager: an animated recording of the window."""
        gui = self

        class Recorder:
            def __enter__(self):
                self.stop = threading.Event()
                self.frames = []

                def loop():
                    while not self.stop.is_set() and len(self.frames) < 400:
                        try:
                            image = gui.grab()
                            if image.width > 1 and image.height > 1:
                                image.thumbnail((960, 960))
                                self.frames.append(image.convert("P", palette=1, colors=128))
                        except Exception:
                            pass
                        self.stop.wait(0.8)

                self.thread = threading.Thread(target=loop, daemon=True)
                self.thread.start()
                return self

            def __exit__(self, *exc):
                self.stop.set()
                self.thread.join(timeout=5)
                if self.frames:
                    target = gui.out / f"{name}.gif"
                    try:
                        self.frames[0].save(target, save_all=True,
                                            append_images=self.frames[1:],
                                            duration=400, loop=0, optimize=True)
                    except Exception as error:   # a recording never fails a journey
                        print(f"  [record] {name}: {error!r}", flush=True)
                return False

        return Recorder()

    def dump(self, name: str) -> Path:
        """The UI Automation tree (what a screen reader sees) for diagnosis."""
        rows = []
        try:
            for element in self.win.descendants():
                info = element.element_info
                try:
                    rect = info.rectangle
                    box = [rect.left, rect.top, rect.right, rect.bottom]
                except Exception:
                    box = None
                rows.append({"type": info.control_type, "name": info.name,
                             "id": info.automation_id, "class": info.class_name, "rect": box,
                             "enabled": info.enabled})
        except Exception as error:
            rows.append({"error": repr(error)})
        target = self.out / "trees" / f"{self.step_index:03d}-{slug(name)}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
        return target

    @staticmethod
    def describe(elements, limit: int = 120) -> str:
        """Compact lines "type | name | automation id" for the CI log."""
        lines = []
        for element in list(elements)[:limit]:
            info = element.element_info
            try:
                rect = info.rectangle
                where = f"{rect.left},{rect.top},{rect.width()}x{rect.height()}"
            except Exception:
                where = "?"
            value = ""
            if info.control_type in TEXT_FIELDS:
                value = Gui.value(element)
            lines.append(f"    {info.control_type:<12} | {(info.name or '')[:70]!r} | "
                         f"{info.automation_id or ''} | {info.class_name or ''} | {where}"
                         + (f" | value {value[:70]!r}" if value else ""))
        return "\n".join(lines)

    def log_screen(self, title: str) -> None:
        """What is on screen now, printed into the CI log (artifacts may not be
        reachable when diagnosing a failure)."""
        try:
            visible = [e for e in self.elements()
                       if ((e.element_info.name or "").strip()
                           or e.element_info.control_type in TEXT_FIELDS)
                       and self.on_screen(e)]
            print(f"  [screen: {title}] {len(visible)} named elements on screen", flush=True)
            print(self.describe(visible, 90), flush=True)
        except Exception as error:
            print(f"  [screen: {title}] could not list elements: {error!r}", flush=True)

    def log_desktop(self, reason: str) -> None:
        """The whole desktop and every visible top-level window (with its
        process, class and state) when the program's window is not found."""
        print(f"  [desktop: {reason}]", flush=True)
        pid = self.process.pid if self.process is not None else None
        for window in top_windows():
            if window["visible"] or window["pid"] == pid:
                mark = "  <- this program" if window["pid"] == pid else ""
                print(f"    {window['pid']:>6} {window['class'][:32]:<32} {window['title'][:40]!r} "
                      f"{window['rect']} visible={window['visible']} "
                      f"minimized={window['minimized']}{mark}", flush=True)
        with contextlib.suppress(Exception):
            from PIL import ImageGrab

            target = self.out / "steps" / f"000-desktop-{slug(reason)}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            ImageGrab.grab(all_screens=True).save(target)

    # ------------------------------------------------------------- queries
    def elements(self):
        return self.win.descendants()

    def _matches(self, element, name, regex, control_type) -> bool:
        info = element.element_info
        if control_type and info.control_type not in (
                (control_type,) if isinstance(control_type, str) else control_type):
            return False
        text = info.name or ""
        if name is not None and text != name:
            return False
        if regex is not None and not re.search(regex, text):
            return False
        return True

    region = None     # (left, top, right, bottom): only elements inside it, see within()

    def query(self, name=None, *, regex=None, control_type=None):
        found = [e for e in self.elements() if self._matches(e, name, regex, control_type)]
        if self.region is not None:
            left, top, right, bottom = self.region

            def inside(element):
                with contextlib.suppress(Exception):
                    r = element.element_info.rectangle
                    x, y = (r.left + r.right) // 2, (r.top + r.bottom) // 2
                    return left <= x <= right and top <= y <= bottom
                return False

            found = [e for e in found if inside(e)]
        return found

    @contextlib.contextmanager
    def within(self, region):
        """Look for controls only inside ``region`` (an open dialog): the page
        behind a non-modal dialog may hold controls with the same names, and a
        click on them dismisses the dialog."""
        previous, self.region = self.region, region
        try:
            yield
        finally:
            self.region = previous

    def texts(self) -> list[str]:
        """Every name on screen, and the text of read-only text fields: Flutter
        exposes selectable text (notices, messages) as an Edit whose text is
        its value, not its name."""
        found = []
        for element in self.elements():
            info = element.element_info
            found.append(info.name or "")
            if info.control_type in TEXT_FIELDS:
                value = self.value(element)
                if value:
                    found.append(value)
        return found

    def has_text(self, fragment: str) -> bool:
        return any(fragment in text for text in self.texts())

    def content_box(self):
        left, top, right, bottom = self.window_box()
        # Leave out the title bar, the context bar and the status line.
        return left + 250, top + 110, right - 10, bottom - 50

    def on_screen(self, element) -> bool:
        try:
            rect = element.element_info.rectangle
        except Exception:
            return False
        left, top, right, bottom = self.window_box()
        return (rect.width() > 0 and rect.height() > 0 and rect.top >= top + 60
                and rect.bottom <= bottom - 30 and rect.left >= left and rect.right <= right)

    def wheel(self, clicks: int, at=None) -> None:
        from pywinauto import mouse

        left, top, right, bottom = self.content_box()
        x, y = at or ((left + right) // 2, (top + bottom) // 2)
        mouse.scroll(coords=(x, y), wheel_dist=clicks)
        time.sleep(0.35)

    # The bottom of the content can be covered by the status line and, in the
    # import review, by its sticky footer: a click there lands on them.
    STATUS_LINE = 45
    CONTEXT_BAR = 115
    _footer_cache = (0.0, None)

    def footer_top(self):
        """Where the import review's sticky footer starts (None: no footer)."""
        stamp, top = self._footer_cache
        if time.monotonic() - stamp < 2.0:
            return top
        top = None
        with contextlib.suppress(Exception):
            _, _, _, bottom = self.window_box()
            tops = [e.element_info.rectangle.top
                    for name in (T("imp.back"), T("imp.next"), T("imp.create_draft"))
                    for e in self.query(name, control_type="Button")
                    if e.element_info.rectangle.top > bottom - 260]
            top = min(tops) - 12 if tops else None
        self._footer_cache = (time.monotonic(), top)
        return top

    def clickable(self, element) -> bool:
        if not self.on_screen(element):
            return False
        info = element.element_info
        rect = info.rectangle
        if self.region is not None:
            # In a dialog: only what its scroll area shows, above its buttons
            # (a control listed below them is hidden; a click there lands
            # outside the dialog and dismisses it).
            left, top, right, bottom = self.region
            return (rect.top >= top and rect.bottom <= bottom
                    and rect.left >= left and rect.right <= right)
        left, _, _, bottom = self.window_box()
        if rect.right <= left + 260:
            return True                       # the sidebar never scrolls
        if (info.name or "") in (T("imp.back"), T("imp.next"), T("imp.create_draft")):
            return True                       # the sticky footer itself
        if (info.name or "") in self.banner_actions():
            return True                       # the update banner sits above the context bar
        limit = bottom - self.STATUS_LINE
        footer = self.footer_top()
        if footer is not None:
            limit = min(limit, footer)
        # Content scrolled under the title bar and the context bar (to y ~105)
        # is reported on screen, but a click there lands on the bar.
        _, top, _, _ = self.window_box()
        return rect.bottom <= limit and rect.top >= top + self.CONTEXT_BAR

    @staticmethod
    def banner_actions() -> set[str]:
        import update_ui

        return {update_ui.t("en", key) for key in ("whats_new", "update_now", "later")}

    def scroll_into_view(self, element, attempts: int = 30):
        for _ in range(attempts):
            if self.clickable(element):
                return element
            rect = element.element_info.rectangle
            _, top, _, bottom = self.content_box()
            self.wheel(2 if rect.top < top else -2)
        return element

    def find(self, name=None, *, regex=None, control_type=None, timeout: float = 15,
             scroll: bool = True, index: int = 0, visible: bool = True):
        """The ``index``-th element with this name (or regex), on screen.

        Waits for it; then scrolls the page down, then up, the way a person
        looks for a control below or above the visible part.
        """
        deadline = time.monotonic() + timeout
        settle_until = time.monotonic() + min(4.0, timeout)
        moves, direction = 0, -1
        while True:
            found = self.query(name, regex=regex, control_type=control_type)
            if len(found) > index:
                element = found[index]
                if not visible or self.clickable(element):
                    return element
                if scroll:
                    self.scroll_into_view(element)
                    if self.clickable(element):
                        return element
            now = time.monotonic()
            if now > deadline:
                break
            if scroll and now > settle_until and moves < 40:
                self.wheel(3 * direction)
                moves += 1
                if moves == 20:
                    direction = 1
            else:
                time.sleep(0.4)
        self.dump(f"missing-{name or regex}")
        self.shot(f"missing-{name or regex}")
        self.log_screen(f"missing {name or regex!r}")
        raise StepFailure(f"not found on screen: {name or regex!r} ({control_type or 'any'})")

    # ------------------------------------------------------------- actions
    def click(self, name=None, *, regex=None, control_type=None, index: int = 0,
              timeout: float = 15, settle: float = 0.8):
        element = self.find(name, regex=regex, control_type=control_type, index=index,
                            timeout=timeout)
        info = element.element_info
        if info.control_type in ("RadioButton", "CheckBox"):
            # On the button itself: its row spans the page (see check()).
            rect = info.rectangle
            element.click_input(coords=(min(20, rect.width() // 2), rect.height() // 2))
        else:
            element.click_input()
        time.sleep(settle)
        return element

    def type_into(self, label: str, text: str, *, clear: bool = True, index: int = 0):
        from pywinauto import keyboard

        field = self.find(label, control_type="Edit", index=index)
        field.click_input()
        time.sleep(0.3)
        if clear:
            keyboard.send_keys("^a{BACKSPACE}")
        keyboard.send_keys(escape_keys(text), with_spaces=True, pause=0.02)
        time.sleep(0.8)
        return field

    @staticmethod
    def value(element) -> str:
        with contextlib.suppress(Exception):
            return element.get_value() or ""
        with contextlib.suppress(Exception):
            return element.iface_value.CurrentValue or ""
        return ""

    def focused(self):
        from pywinauto.uia_defines import IUIA
        from pywinauto.uia_element_info import UIAElementInfo

        return UIAElementInfo(IUIA().get_focused_element())

    def check(self, label: str, value: bool = True, *, index: int = 0):
        """Tick (or clear) a checkbox like a person: on the box itself. Its row
        spans the page, and a click on the empty part to the right of the label
        does nothing (run 10: the levels and the scale were never confirmed)."""
        box = self.find(label, control_type="CheckBox", index=index)

        def state():
            with contextlib.suppress(Exception):
                return bool(box.get_toggle_state())
            return None

        if state() == value:
            return box
        rect = box.element_info.rectangle
        box.click_input(coords=(min(20, rect.width() // 2), rect.height() // 2))
        time.sleep(0.8)
        if state() not in (value, None):
            print(f"  [check] clicking {label[:50]!r} did not change it; using UI Automation",
                  flush=True)
            with contextlib.suppress(Exception):
                box.toggle()
            time.sleep(0.8)
        expect(state() in (value, None), f"{label[:60]!r} could not be set to {value}")
        return box

    # The window's system menu (Restore, Move, Size, Minimize, Maximize, Close).
    SYSTEM_MENU_IDS = {"61728", "61456", "61440", "61472", "61488", "61536"}

    def system_menu_open(self) -> bool:
        with contextlib.suppress(Exception):
            return any(e.element_info.automation_id in self.SYSTEM_MENU_IDS
                       and self.on_screen(e)
                       for e in self.query(control_type="MenuItem"))
        return False

    def close_menus(self) -> None:
        """Close the window's system menu if something opened it: typing into
        it could minimize or close the application."""
        from pywinauto import keyboard

        for _ in range(3):
            if not self.system_menu_open():
                return
            print("  [menu] the window's system menu is open; closing it", flush=True)
            keyboard.send_keys("{ESC}")
            time.sleep(0.5)

    @staticmethod
    def element_id(element):
        info = element.element_info
        with contextlib.suppress(Exception):
            return tuple(info.runtime_id)
        rect = info.rectangle
        return (info.control_type, info.name, rect.left, rect.top)

    @staticmethod
    def activate(element) -> str:
        """Press a control through UI Automation's Invoke pattern (what a
        screen reader or a switch device does); a mouse click otherwise."""
        try:
            element.invoke()
            return "invoke"
        except Exception:
            element.click_input()
            return "click"

    def choose(self, label: str, option: str, *, index: int = 0, options=None):
        """Pick ``option`` in the dropdown named ``label``: open it through UI
        Automation and press the entry that appeared with the menu (the page
        may hold a checkbox of the same name: the ANCOVA form lists the
        covariates). Where the open menu exposes no entries (the method form,
        runs 13-14), choose like a keyboard user: Down to the entry, Enter."""
        from pywinauto import keyboard

        kinds_menu = ("MenuItem", "ListItem", "Button", "Text", "Custom", "Group")
        self.close_menus()
        field = None
        for kinds in (("ComboBox",), ("Edit",), ("Button", "Group", "Custom", "Pane", "Text")):
            found = self.query(label, control_type=kinds)
            if len(found) > index:
                field = found[index]
                break
        if field is None:
            field = self.find(label, index=index)
        self.scroll_into_view(field)
        before = {self.element_id(e) for e in self.query(option)}
        everything_before = {self.element_id(e) for e in self.elements()}

        def entries(wait: float = 3.0):
            deadline = time.monotonic() + wait
            while True:
                self.close_menus()
                found = [e for e in self.query(option, control_type=kinds_menu)
                         if self.element_id(e) not in before
                         and e.element_info.automation_id not in self.SYSTEM_MENU_IDS]
                if found or time.monotonic() > deadline:
                    return found
                time.sleep(0.5)

        how = self.activate(field)
        appeared = entries()
        if not appeared and how == "invoke":
            field.click_input()                      # open it with the mouse instead
            how = "click"
            appeared = entries()
        if appeared:
            print(f"  [choose] {label!r}: opened by {how}; picking {option!r}", flush=True)
            self.activate(appeared[-1])
            time.sleep(1.0)
            return
        new = [e for e in self.elements() if self.element_id(e) not in everything_before
               and (e.element_info.name or "").strip()][:20]
        print(f"  [choose] {label!r} opened by {how}; no entry {option!r}; "
              f"{len(new)} new named elements:\n" + self.describe(new, 20), flush=True)
        if options is None or option not in options:
            raise StepFailure(f"{option!r} is not listed in the dropdown {label!r}")
        # The keys go to the dropdown that Flutter has focused (Windows reports
        # Flutter's focus as its view, an unnamed pane), never to the system menu.
        focused = self.focused()
        expect(focused.process_id == self.window_pid and not self.system_menu_open(),
               f"the dropdown {label!r} does not have the keyboard focus")
        current = self.value(field)
        start = options.index(current) if current in options else -1
        moves = options.index(option) - start
        print(f"  [choose] choosing entry {options.index(option) + 1} of {len(options)} by "
              f"keyboard (from {current!r})", flush=True)
        keyboard.send_keys(("{DOWN}" if moves > 0 else "{UP}") * abs(moves))
        time.sleep(0.4)
        keyboard.send_keys("{ENTER}")
        time.sleep(0.9)

    def keys(self, keys: str):
        from pywinauto import keyboard

        # with_spaces: pywinauto drops spaces otherwise (" (checked)" arrived
        # as "(checked)" in run 10).
        keyboard.send_keys(keys, with_spaces=True)
        time.sleep(0.5)

    def status(self) -> str:
        """The status line (a live region) as Windows exposes it."""
        texts = self.texts()
        return " | ".join(t for t in texts if t)[-4000:]

    def wait_text(self, fragment: str, timeout: float = 30, *, scroll: bool = True) -> None:
        """Wait for ``fragment`` on screen. After a few seconds also look below
        and above the visible part, as a person scrolls to a message: Flutter
        exposes to UI Automation only what is near the visible part."""
        deadline = time.monotonic() + timeout
        settle_until = time.monotonic() + min(4.0, timeout / 2)
        moves, direction = 0, -1
        while time.monotonic() < deadline:
            if self.has_text(fragment):
                return
            if scroll and time.monotonic() > settle_until and moves < 40:
                self.wheel(3 * direction)
                moves += 1
                if moves == 20:
                    direction = 1
            else:
                time.sleep(0.5)
        self.dump(f"no-text-{fragment}")
        self.shot(f"no-text-{fragment}")
        self.log_screen(f"text never appeared: {fragment[:50]!r}")
        raise StepFailure(f"text never appeared: {fragment!r}")

    # --------------------------------------------------------- file dialogs
    def dialogs(self) -> list:
        """Visible standard Windows dialogs (class #32770) of THIS application.

        UI Automation lists a dialog owned by the application window (the
        Open and Save dialogs) as a child of that window, not on the desktop,
        so both places are searched. Dialogs of other processes (a hosted
        runner shows its own paging-file warning) are never taken."""
        from pywinauto import Desktop

        pid = self.window_pid or (
            self.process.pid if self.process is not None else None)
        candidates = []
        with contextlib.suppress(Exception):
            candidates.extend(self.win.wrapper_object().children())
        with contextlib.suppress(Exception):
            candidates.extend(Desktop(backend="uia").windows())
        found, seen = [], set()
        for window in candidates:
            with contextlib.suppress(Exception):
                info = window.element_info
                if (info.class_name == "#32770" and info.process_id == pid
                        and window.is_visible() and info.handle not in seen):
                    seen.add(info.handle)
                    found.append(window)
        return found

    def file_dialog(self, path: Path, *, save: bool, timeout: float = 30) -> None:
        """Fill in the native Windows Open/Save dialog like a person: the
        dialog opens with the keyboard in its File name box."""
        from pywinauto import keyboard

        deadline = time.monotonic() + timeout
        dialog = None
        while time.monotonic() < deadline and dialog is None:
            found = self.dialogs()
            dialog = found[0] if found else None
            time.sleep(0.5)
        if dialog is None:
            self.shot("no-file-dialog")
            self.log_screen("no file dialog")
            raise StepFailure("the Windows file dialog did not open")
        time.sleep(1.0)            # let the dialog finish building its controls
        self.shot("file-dialog")
        edits = []
        with contextlib.suppress(Exception):
            edits = dialog.descendants(control_type="Edit")
        wanted = ("1001", "1148") if save else ("1148", "1001")
        edit = next((e for key in wanted for e in edits
                     if e.element_info.automation_id == key), None)
        if edit is None and edits:
            # Else the lowest edit field (the search box is on top).
            edit = max(edits, key=lambda e: e.element_info.rectangle.top)
        print(f"  [file dialog] {dialog.window_text()!r}: {len(edits)} edit field(s); using "
              f"{(edit.element_info.automation_id if edit else 'keyboard focus')!r}", flush=True)
        if edit is None:
            print(self.describe(dialog.descendants(), 80), flush=True)
        # No set_focus(): pywinauto presses Alt to take the foreground, which
        # can leave the window's system menu waiting for the next key.
        if edit is not None:
            with contextlib.suppress(Exception):
                edit.click_input()
        else:
            keyboard.send_keys("%n")          # Alt+N: the File name box
        time.sleep(0.3)
        keyboard.send_keys("^a{BACKSPACE}")
        keyboard.send_keys(escape_keys(str(path)), with_spaces=True, pause=0.01)
        time.sleep(0.4)
        keyboard.send_keys("{ENTER}")
        # An existing file asks to be replaced; otherwise the dialog closes.
        end_at = time.monotonic() + 15
        while time.monotonic() < end_at:
            open_dialogs = self.dialogs()
            if not open_dialogs:
                break
            for window in open_dialogs:
                with contextlib.suppress(Exception):
                    for button in window.descendants(control_type="Button"):
                        if button.window_text() in ("Yes", "&Yes"):
                            button.click_input()
            time.sleep(0.5)
        if self.dialogs():
            self.shot("file-dialog-still-open")
            print(self.describe(self.dialogs()[0].descendants(), 60), flush=True)
            raise StepFailure("the Windows file dialog stayed open after Enter")
        time.sleep(1.0)

    def print_app_log(self, lines: int = 40) -> None:
        """The application's own log (exceptions in handlers land there)."""
        logs = sorted((self.out / "app-logs").glob("**/*"), key=lambda p: p.stat().st_mtime)
        for log in [p for p in logs if p.is_file()][-2:]:
            text = log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
            print(f"  [app log] {log.name} (last {len(text)} lines)", flush=True)
            for line in text:
                print("    " + line[:220], flush=True)

    def recover(self) -> None:
        """After a failed journey: close menus and dialogs, show the window
        maximized again and return to Home."""
        from pywinauto import keyboard

        self.close_menus()
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.user32.ShowWindow(self.handle, 3)      # SW_MAXIMIZE
            time.sleep(1.0)
        for _ in range(3):
            for window in self.dialogs():
                with contextlib.suppress(Exception):
                    window.close()
            with contextlib.suppress(Exception):
                keyboard.send_keys("{ESC}")
            time.sleep(0.5)
        with contextlib.suppress(Exception):
            self.click(T("nav.home"), control_type=("Button", "Text"), timeout=8)


# ================================================================ journeys
class Journey:
    def __init__(self, name: str, gui: Gui):
        self.name, self.gui = name, gui
        self.steps: list[dict] = []
        self.facts: dict = {}

    @contextlib.contextmanager
    def step(self, title: str):
        started = time.monotonic()
        entry = {"step": title}
        try:
            yield entry
        except Exception as error:
            entry.update(ok=False, error=f"{type(error).__name__}: {error}",
                         trace=traceback.format_exc()[-2000:])
            with contextlib.suppress(Exception):
                self.gui.dump(f"failed-{title}")
            with contextlib.suppress(Exception):
                entry["screenshot"] = str(self.gui.shot(f"failed-{title}"))
            entry["seconds"] = round(time.monotonic() - started, 1)
            self.steps.append(entry)
            raise
        entry.update(ok=True, seconds=round(time.monotonic() - started, 1))
        with contextlib.suppress(Exception):
            entry["screenshot"] = str(self.gui.shot(title))
        self.steps.append(entry)


def expect(condition, message: str):
    if not condition:
        raise StepFailure(message)


def verify_saved(path: Path, *, kind: str, contains: tuple[str, ...] = ()) -> dict:
    """The file the application wrote, opened and checked here."""
    expect(path.is_file(), f"{path.name} was not written")
    size = path.stat().st_size
    expect(size > 0, f"{path.name} is empty")
    facts = {"file": path.name, "bytes": size}
    if kind == "docx":
        from docx import Document

        text = "\n".join(p.text for p in Document(str(path)).paragraphs)
        for table in Document(str(path)).tables:
            for row in table.rows:
                text += "\n" + " ".join(cell.text for cell in row.cells)
        for fragment in contains:
            expect(fragment in text, f"{path.name} lacks {fragment!r}")
        facts["paragraphs"] = len(text.splitlines())
    elif kind == "png":
        from PIL import Image

        expect(path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG")
        with Image.open(path) as image:
            facts["pixels"] = list(image.size)
            expect(min(image.size) > 200, f"{path.name} is too small: {image.size}")
    elif kind in ("txt", "csv", "json"):
        text = path.read_text(encoding="utf-8-sig")
        for fragment in contains:
            expect(fragment in text, f"{path.name} lacks {fragment!r}")
        facts["characters"] = len(text)
        if kind == "json":
            json.loads(text)
    elif kind == "sra":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("manifest.json"))
        expect("manifest.json" in names, "backup without manifest")
        for fragment in contains:
            expect(fragment in json.dumps(manifest, ensure_ascii=False), f"backup lacks {fragment!r}")
        facts["entries"] = len(names)
        facts["project"] = manifest.get("project", {}).get("title")
    elif kind == "svg":
        text = path.read_text(encoding="utf-8")
        expect("<svg" in text[:600], f"{path.name} is not an SVG")
        expect("<desc>" in text, f"{path.name} has no text alternative")
        for fragment in contains:
            expect(fragment in text, f"{path.name} lacks {fragment!r}")
        facts["characters"] = len(text)
    return facts


def engine_ancova(csv: Path):
    """The validated engine on the same data and choices as the GUI run."""
    from data_loader import load_dataset
    from workspace_methods import run_method
    from workspace_state import ResearchSession

    session = ResearchSession()
    session.set_dataset(load_dataset(csv), csv.name)
    session.accept_suggestions()
    return run_method("ancova", session, {"outcome": "wellbeing", "group": "group",
                                          "covariates": ["baseline_score"]},
                      {"mode": "ancova"}, {"model": True})


def nav(gui: Gui, key: str) -> None:
    """Go to a sidebar area; its button may carry a count ("Reports\\n1")."""
    gui.click(regex="^" + re.escape(T(key)) + r"(\n\d+)?$", control_type=("Button", "Text"))


def option_label(name: str, level: str) -> str:
    return f"{name} · {T('level.' + level)}"


# The variable dropdowns of sample_ancova.csv after its levels are confirmed:
# every variable but the identifier, in column order.
ANCOVA_OPTIONS = [option_label("group", "nominal"), option_label("age", "scale"),
                  option_label("baseline_score", "scale"), option_label("wellbeing", "scale")]


def open_project(gui: Gui, title: str) -> None:
    """Open the project ``title`` from Home with its own Open button (its
    accessible name carries the tooltip "Open “title”"), then check that it
    is the open project: the project page, with this title as its heading."""
    nav(gui, "nav.home")
    subtitle = T("project.dashboard_subtitle")
    try:
        # Windows exposes the tooltip as an element over the button itself.
        holder = gui.find(regex=re.escape(T("project.open_named", title=title)),
                          control_type=("Button", "Group", "Custom", "Text"), timeout=10)
    except StepFailure:
        # Already the open project: its row says "Open now" instead.
        gui.click(T("nav.project"), control_type=("Button", "Text"), timeout=8)
    else:
        rect = holder.element_info.rectangle
        button = next((b for b in gui.query(T("project.open"), control_type="Button")
                       if b.element_info.rectangle == rect), holder)
        button.click_input()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not gui.has_text(subtitle):
            time.sleep(0.5)
        if not gui.has_text(subtitle):
            print(f"  [open] the click on Open did not open {title!r}; pressing it through "
                  f"UI Automation", flush=True)
            Gui.activate(button)
    gui.wait_text(subtitle, timeout=20, scroll=False)
    heading = [e for e in gui.query(title, control_type="Text")
               if e.element_info.rectangle.top < gui.window_box()[1] + 200]
    expect(heading, f"{title} is not the open project")


def create_project(gui: Gui, journey: Journey, title: str) -> None:
    with journey.step(f"create project {title}"):
        nav(gui, "nav.home")
        gui.type_into(T("project.new_title"), title)
        gui.click(T("project.create"), control_type="Button")
        gui.wait_text(title)
        gui.wait_text(T("next.add_data"))


def open_data(gui: Gui, journey: Journey, csv: Path) -> None:
    with journey.step(f"open {csv.name} in the Windows Open dialog"):
        gui.click(T("data.open"), control_type=("Button", "Text"))
        gui.file_dialog(csv, save=False)
        gui.wait_text(T("data.loaded", name=csv.name), timeout=40)


def accept_levels(gui: Gui, journey: Journey) -> None:
    with journey.step("confirm the measurement levels"):
        nav(gui, "nav.data")
        gui.check(T("data.accept_confirm"))
        gui.click(T("data.accept_suggestions"), control_type="Button")
        gui.wait_text(T("next.analyze"))


def save_via_dialog(gui: Gui, journey: Journey, button: str, target: Path, *, kind: str,
                    contains=()) -> dict:
    with journey.step(f"save {target.name} with '{button}'"):
        gui.click(button, control_type=("Button", "Text"))
        gui.file_dialog(target, save=True)
        # The announcement ("Saved: <path>", "Backup saved: <path>") names the
        # file; the name, so that a short or long form of the folder
        # (RUNNER~1 / runneradmin) both count. The file itself is checked next.
        gui.wait_text(target.name if target.suffix else target.name + ".", timeout=40)
        # A name typed without its extension is saved with it (``with_extension``).
        written = target if target.suffix else target.with_name(target.name + "." + kind)
        facts = verify_saved(written, kind=kind, contains=contains)
        journey.facts[written.name] = facts
        return facts


def journey_project_a(gui: Gui, work: Path, journey: Journey) -> None:
    csv = work / "sample_ancova.csv"
    shutil.copy(ROOT / "examples" / "sample_ancova.csv", csv)
    expected = engine_ancova(csv)
    journey.facts["engine_report_first_line"] = expected.report.strip().splitlines()[0]
    create_project(gui, journey, "Fictional study A")
    open_data(gui, journey, csv)
    accept_levels(gui, journey)
    with journey.step("open ANCOVA among all methods"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.all"), control_type=("Button", "Text"))
        from workspace_methods import METHODS

        # A method card is named by its title and its summary.
        gui.click(regex="^" + re.escape(METHODS["ancova"].title) + r"(\n|$)",
                  control_type=("Button", "Text", "Group", "Custom"))
    with journey.step("choose outcome, group and covariate"):
        gui.choose(T("role.outcome"), option_label("wellbeing", "scale"), options=ANCOVA_OPTIONS)
        gui.choose(T("role.group"), option_label("group", "nominal"), options=ANCOVA_OPTIONS)
        gui.check(option_label("baseline_score", "scale"))
        from workspace_methods import METHODS, default_options, required_confirmations
        from workspace_text import label as engine_label

        spec = METHODS["ancova"]
        for confirmation in required_confirmations(spec, default_options(spec)):
            gui.check(engine_label("en", confirmation.label))
    with journey.step("run ANCOVA"):
        gui.click(T("form.run"), control_type="Button")
        gui.wait_text(T("results.save_docx"), timeout=90)
    with journey.step("provenance names the dataset and its rows"):
        gui.wait_text("sample_ancova.csv · 180 rows")
    save_via_dialog(gui, journey, T("results.save_txt"), work / "ancova_report.txt", kind="txt",
                    contains=(expected.report.strip(),))
    save_via_dialog(gui, journey, T("results.save_png"), work / "ancova_figure.png", kind="png")
    # The Windows dialog may return the name as typed: no extension here.
    save_via_dialog(gui, journey, T("results.save_docx"), work / "ancova_word", kind="docx")
    journey.facts["docx_written_as"] = "ancova_word.docx"
    with journey.step("the Word file without a typed extension is a real document"):
        verify_saved(work / "ancova_word.docx", kind="docx", contains=("ANCOVA",))
    with journey.step("add the result to the report and export it"):
        gui.click(T("results.add_report"), control_type=("Button", "Text"))
        nav(gui, "nav.reports")
        gui.type_into(T("reports.study_title"), "Fictional ANCOVA study")
        field = gui.find(T("reports.study_title"), control_type="Edit")
        expect(gui.value(field) == "Fictional ANCOVA study",
               f"typed title kept: {gui.value(field)!r}")
    save_via_dialog(gui, journey, T("reports.export_txt"), work / "combined_report.txt",
                    kind="txt", contains=("Fictional ANCOVA study", expected.report.strip()))
    # The research report (#42, Stage 36.6): one editable document in numbered
    # sections, each result in the section it belongs to, real tables.
    from research_report import TEXT as REPORT_TEXT

    save_via_dialog(gui, journey, T("reports.export_docx"), work / "combined_report.docx",
                    kind="docx", contains=("Fictional ANCOVA study", expected.title,
                                           REPORT_TEXT["en"]["tests"], "Table 1",
                                           REPORT_TEXT["en"]["appendix"], "sample_ancova.csv"))
    with journey.step("back up the project"):
        nav(gui, "nav.project")
    save_via_dialog(gui, journey, T("project.backup"), work / "study_a_backup.sra", kind="sra",
                    contains=("Fictional study A",))
    with journey.step("restart the application"):
        gui.stop()
        gui.start()
    with journey.step("reopen project A after the restart"):
        open_project(gui, "Fictional study A")
        gui.wait_text("sample_ancova.csv")
        gui.wait_text(expected.title)
    with journey.step("open the restored result"):
        try:
            gui.click(T("reports.open_result"), control_type=("Button", "Text"), timeout=6)
        except StepFailure:   # the icon's name may be its tooltip or nothing
            nav(gui, "nav.results")
            # A result in the list is named by its title and its details.
            gui.click(regex="^" + re.escape(expected.title),
                      control_type=("Button", "Text", "ListItem", "Group", "Custom"))
        gui.wait_text(T("results.save_docx"), timeout=60)
    time.sleep(4)   # restored results are recalculated in the background
    save_via_dialog(gui, journey, T("results.save_docx"), work / "ancova_after_restart.docx",
                    kind="docx", contains=("ANCOVA",))


def journey_project_b(gui: Gui, work: Path, journey: Journey) -> None:
    csv = work / "sample_three_groups.csv"
    shutil.copy(ROOT / "examples" / "sample_three_groups.csv", csv)
    create_project(gui, journey, "Fictional study B")
    with journey.step("project B starts empty"):
        gui.wait_text(T("source.none"))
        gui.wait_text(T("project.no_results"))
    open_data(gui, journey, csv)
    with journey.step("switch to project A: only its own data and results"):
        open_project(gui, "Fictional study A")
        gui.wait_text("sample_ancova.csv")
        expect(not gui.has_text("sample_three_groups.csv"), "project A shows B's data")
    with journey.step("switch back to project B: only its own data"):
        open_project(gui, "Fictional study B")
        gui.wait_text("sample_three_groups.csv")
        expect(not gui.has_text("sample_ancova.csv"), "project B shows A's data")
        expect(gui.has_text(T("project.no_results")), "project B shows A's results")


def import_document(gui: Gui, journey: Journey, pdf: Path, *, expected_items: int = 0,
                    instruments: int = 1, shows: str | None = None) -> None:
    """Questionnaires → Import PDF / Word… → the document in the Windows Open
    dialog, until the reading is announced ("Read 1 instrument(s) and 30
    candidate items from …") or, for a scan waiting for its OCR language,
    until ``shows`` is on screen."""
    with journey.step(f"import {pdf.name} in the Windows Open dialog"):
        nav(gui, "nav.questionnaires")
        gui.click(T("q.import"), control_type=("Button", "Text"))
        gui.file_dialog(pdf, save=False)
        # Reading (and local OCR of image pages) runs with a progress line.
        gui.wait_text(shows or T("imp.read_ok", instruments=instruments, items=expected_items,
                                 name=pdf.name), timeout=180)


def wizard_step(gui: Gui, number: int) -> None:
    """Open step ``number`` of the review wizard by its step button, named
    "N. Title · detail" (an item's text may also start with "N. ")."""
    gui.click(regex=rf"^{number}\. [^\n]* · ", control_type="Button")


def finish_import(gui: Gui, journey: Journey) -> None:
    with journey.step("step 2: confirm the shared scale"):
        wizard_step(gui, 2)
        gui.check(T("imp.confirm_structure"))
        gui.check(T("imp.confirm_codes"))
        gui.click(T("imp.apply_scale"), control_type=("Button", "Text"))
    with journey.step("step 4: the independent confirmations"):
        wizard_step(gui, 4)
        gui.check(T("imp.check_version"))
        gui.check(T("imp.check_rights"))
        gui.check(T("imp.check_items"))
        gui.wait_text(T("imp.ready"))
    with journey.step("create the editable draft from the footer"):
        gui.click(T("imp.create_draft"), control_type="Button")
        with contextlib.suppress(StepFailure):
            gui.click(T("q.replace_confirm"), control_type="Button", timeout=4)
        gui.wait_text(T("q.survey_title"))


def journey_import_30(gui: Gui, work: Path, journey: Journey) -> None:
    from synthetic_documents import psq_like_pdf

    pdf = work / "synthetic_strain_questionnaire.pdf"
    pdf.write_bytes(psq_like_pdf())
    import_document(gui, journey, pdf, expected_items=30)
    with journey.step("the bibliography is kept out and the count matches"):
        gui.wait_text(T("impnote.count_match", found=30, expected=30))
        gui.wait_text("look like references")
        gui.wait_text("local OCR")
    finish_import(gui, journey)
    with journey.step("the builder holds exactly the 30 items"):
        gui.wait_text("30. ")
        expect(not gui.has_text("31. "), "a 31st question was created")


def journey_review_120(gui: Gui, work: Path, journey: Journey) -> None:
    from synthetic_documents import numbered_items_pdf, strain_statements

    pdf = work / "synthetic_120_items.pdf"
    pdf.write_bytes(numbered_items_pdf(120))
    statements = strain_statements(120)
    import_document(gui, journey, pdf, expected_items=120)
    with journey.step("the count matches and step 3 lists the items"):
        gui.wait_text(T("impnote.count_match", found=120, expected=120))
        wizard_step(gui, 3)
    for number in (60, 61, 95):
        with journey.step(f"select item {number} of 120: the list stays in place"):
            prefix = f"{number}. {statements[number - 1][:30]}"
            row = gui.find(regex=re.escape(prefix))
            before = row.element_info.rectangle.top
            row.click_input()
            time.sleep(1.5)
            after_rows = gui.query(regex=re.escape(prefix))
            expect(after_rows, f"item {number} left the screen after the click")
            moved = after_rows[0].element_info.rectangle.top - before
            journey.facts[f"item_{number}_moved_px"] = moved
            expect(abs(moved) <= 40, f"item {number} moved {moved} px after the click")
    with journey.step("edit item 95: focus and every typed character stay"):
        field = gui.find(T("imp.edit_wording"), control_type="Edit")
        field.click_input()
        gui.keys("^{END}")                 # the end of the text, not of a visual line
        gui.keys(escape_keys(" (checked)"))
        focused = gui.focused()
        journey.facts["focused_type"] = focused.control_type
        expect(focused.control_type == "Edit", f"focus moved to {focused.control_type}")
        value = gui.value(field)
        journey.facts["edited_value_end"] = value[-30:]
        expect(value.endswith(" (checked)"), f"typed text lost: {value[-40:]!r}")
    finish_import(gui, journey)
    with journey.step("the builder holds the 120 items"):
        gui.wait_text("120. ", timeout=30)


# ------------------------------------------- Stage 36.5 scientific import review
COPE_GENERAL = "INVENTORY FORM: GENERAL"
COPE_SITUATIONAL = "INVENTORY FORM: SITUATIONAL"
SITUATIONAL_OPTIONS = "Not at all / Slightly / Moderately / Strongly"
GENERAL_OPTIONS = "Hardly ever / Now and then / Fairly often / Very often"


def review_form(gui: Gui, title: str, *, index: int, then: str) -> None:
    """Press "Review this form" on the card of the form ``title`` (the
    ``index``-th card), until ``then`` is on screen. Every card has a button
    of that name; its tooltip names the form, and Windows exposes a tooltip
    as an element over the button itself (as for Home's Open buttons)."""
    tip = T("imp.form.use_tip", title=title)
    try:
        holder = gui.find(regex=re.escape(tip),
                          control_type=("Button", "Group", "Custom", "Text"), timeout=15)
    except StepFailure:
        # No tooltip element: the cards stand in document order.
        print(f"  [form] no tooltip names {title!r}; using card {index + 1}", flush=True)
        holder = gui.find(T("imp.form.use"), control_type="Button", index=index)
    rect = holder.element_info.rectangle
    button = next((b for b in gui.query(T("imp.form.use"), control_type="Button")
                   if b.element_info.rectangle == rect), holder)
    button.click_input()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not gui.has_text(then):
        time.sleep(0.5)
    if not gui.has_text(then):
        print(f"  [form] the click did not open {title!r}; pressing it through UI Automation",
              flush=True)
        Gui.activate(button)
    gui.wait_text(then, timeout=20)


def journey_import_cope_docx(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journey 5 on the packaged EXE: a Word document with two
    60-item table forms without item numbers; both are shown, the researcher
    chooses the situational one, its own answer options are reviewed, the
    items step counts 60 and the draft holds exactly those 60 items."""
    from stage36_fixtures import generator

    docx = generator().create_docx_unnumbered(work)
    import_document(gui, journey, docx, expected_items=120, instruments=2)
    with journey.step("both forms are shown; none is chosen for the researcher"):
        gui.wait_text(T("imp.state.found"))
        gui.wait_text(T("imp.state.found_detail", items=120, forms=2, sizes="60, 60"))
        gui.wait_text(T("imp.state.choose"))
        gui.wait_text(COPE_GENERAL)
        gui.wait_text(COPE_SITUATIONAL)
        gui.wait_text(T("imp.form.options", labels=GENERAL_OPTIONS))
        gui.wait_text(T("imp.form.options", labels=SITUATIONAL_OPTIONS))
        # Stage 36.8: a step that cannot open is text, not a button (UI
        # Automation on Windows reports every button as enabled). Before the
        # choice no step-2 button exists to announce or invoke; the reason is
        # shown as text.
        journey.facts["step_2_button_before_choice"] = bool(
            gui.query(regex=r"^2\. [^\n]* · ", control_type="Button"))
        expect(not journey.facts["step_2_button_before_choice"],
               "step 2 is offered as a button before a form is chosen")
        gui.wait_text(T("imp.choose_form_first"))
    with journey.step("review the second (situational) form: its own options"):
        # Only the choice shows "form 2 of 2" (step 1's label); the options
        # are on the form's card before it, so they cannot tell a click.
        review_form(gui, COPE_SITUATIONAL, index=1,
                    then=T("imp.status.form_of", number=2, total=2))
        gui.wait_text(T("imp.scale_items", count=60))           # its scale step
        gui.wait_text(SITUATIONAL_OPTIONS)
        expect(not gui.has_text(GENERAL_OPTIONS), "the general form's options are shown")
    with journey.step("the items step counts 60 situational items"):
        wizard_step(gui, 3)
        gui.wait_text(T("imp.counts", total=60, attention=0, checked=0))
        gui.wait_text("In this invented situational case 1 I would")
        expect(not gui.has_text("In this invented general case"), "items of the other form")
    finish_import(gui, journey)
    with journey.step("the builder holds the 60 items of the chosen form"):
        gui.wait_text("60. ", timeout=30)
        expect(not gui.has_text("61. "), "a 61st question was created")
        gui.wait_text(COPE_SITUATIONAL)


def direct_ocr(pdf: Path, language: str, out: Path | None = None, pages=(1, 2)) -> dict:
    """Read ``pages`` with the program's OCR code and runtime, as the program
    renders them, outside the program: seconds and words per page, and (into
    ``out``) the page image and Tesseract's word boxes (TSV), so that the
    reading of this engine can be replayed elsewhere. Synthetic documents only;
    a diagnostic that never fails the journey."""
    from visual_survey_review import _render_pdf_page, _run_ocr, parse_tesseract_tsv

    facts = {}
    for page in pages:
        try:
            png, dpi = _render_pdf_page(pdf.read_bytes(), page, scale=2.0, max_width=1800,
                                        rotation=0)
            started = time.monotonic()
            tsv = _run_ocr(png, language,
                           ["-c", "tessedit_create_tsv=1", "-c", "tessedit_create_txt=0"],
                           timeout=240, cancel=None, dpi=dpi)
            seconds = round(time.monotonic() - started, 1)
            words = parse_tesseract_tsv(tsv, page, language=language, rotation=0,
                                        engine="tesseract").words
            facts[f"page_{page}"] = {"seconds": seconds, "words": len(words), "dpi": round(dpi, 2)}
            if out is not None:
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{pdf.stem}-p{page}.png").write_bytes(png)
                (out / f"{pdf.stem}-p{page}-{language}.tsv").write_text(tsv, encoding="utf-8")
        except Exception as error:      # a diagnostic: never fails the journey
            facts[f"page_{page}"] = f"{type(error).__name__}: {error}"
    return facts


def direct_rows(pdf: Path, language: str) -> dict:
    """The program's whole OCR reading (``ocr_scientific_pdf``) of ``pdf``,
    outside the program, with the same engine: the item numbers it finds.
    A diagnostic that never fails the journey; synthetic documents only."""
    from visual_survey_review import ocr_scientific_pdf

    started = time.monotonic()
    try:
        review = ocr_scientific_pdf(pdf.read_bytes(), pdf.name, [1, 2], language)
        numbers = [q.number for x in review.instruments for q in x.questions]
        return {"items": len(numbers), "numbers_1_to_52": numbers == list(range(1, 53)),
                "seconds": round(time.monotonic() - started, 1)}
    except Exception as error:      # a diagnostic: never fails the journey
        return {"error": f"{type(error).__name__}: {error}"}


def process_cpu_seconds(pid: int | None) -> float | None:
    """User plus kernel processor seconds a process has used so far (Windows)."""
    if not pid or os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return sum(((t.dwHighDateTime << 32) | t.dwLowDateTime) / 1e7 for t in times[2:])
    finally:
        kernel32.CloseHandle(handle)


def program_cpu_cores(gui: Gui, seconds: float = 6.0) -> float | None:
    """Processor cores the program uses while this driver only waits: no UI
    Automation queries, no input. The baseline for a reading's profile."""
    pid = gui.window_pid or (gui.process.pid if gui.process is not None else None)
    before, started = process_cpu_seconds(pid), time.monotonic()
    time.sleep(seconds)
    after = process_cpu_seconds(pid)
    if before is None or after is None:
        return None
    return round((after - before) / (time.monotonic() - started), 2)


def latest_profile(gui: Gui, after: set | None = None) -> dict | None:
    """The newest reading profile the program wrote (ocr_profile), as a
    compact fact: total, per-stage seconds, engine runs, the event-loop
    stall; ``after`` = file names already seen."""
    folder = gui.out / "ocr-profiles"
    files = sorted(p for p in folder.glob("ocr-profile-*.json") if p.name not in (after or set()))
    if not files:
        return None
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return {
        "file": files[-1].name, "total_seconds": data["total_seconds"],
        "stages": {k: v["seconds"] for k, v in data["stages"].items()},
        "unaccounted_seconds": data["unaccounted_seconds"],
        "engine_runs": [{k: r.get(k) for k in ("seconds", "cpu_seconds", "peak_memory_bytes")}
                        for r in data["engine_runs"]],
        "event_loop_max_stall_seconds": data["event_loop_max_stall_seconds"],
        "renders": data["renders"], "peak_memory_bytes": data["peak_memory_bytes"],
        "process_cpu_seconds": data["process_cpu_seconds"], "max_threads": data["max_threads"],
        "program_cpu_cores": round(data["process_cpu_seconds"] / data["total_seconds"], 2)
        if data["total_seconds"] else None,
        "items": data["facts"].get("items"),
    }


def journey_import_scan_lv(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journey 6 on the packaged EXE: a scanned Latvian 52-item
    table without a text layer is detected, read with the bundled local OCR
    in Latvian, offers its legend as one documented (unconfirmed) scale and
    becomes a draft of exactly 52 items after the researcher's review."""
    from stage36_fixtures import generator
    from workspace_questionnaires import ocr_language_options

    pdf = generator().create_lv_table_scan_pdf(work)
    # The bundled engine's own reading of both pages, with no interface around
    # it: its speed, and its word boxes kept with the evidence (gui.out/ocr),
    # so that a reading that differs from Linux can be replayed there.
    journey.facts["direct_ocr_lav"] = direct_ocr(pdf, "lav", gui.out / "ocr")
    print(f"  [ocr] Latvian outside the program: {journey.facts['direct_ocr_lav']}", flush=True)
    # The same table set in a Times-like font (STIX), read by this engine with
    # the program's code: before 36.7 that typeface lost rows on Windows.
    stix = generator().create_lv_table_scan_pdf(work, "stix")
    journey.facts["stix_table_outside_program"] = direct_rows(stix, "lav")
    print(f"  [ocr] Times-like table outside the program: "
          f"{journey.facts['stix_table_outside_program']}", flush=True)
    import_document(gui, journey, pdf, shows=T("imp.state.scan"))
    with journey.step("the scan is detected: local OCR is offered with its language"):
        gui.wait_text(T("imp.scan.detail", pages="Pages 1 and 2"))
        gui.find(T("imp.ocr_run"), control_type="Button")
    with journey.step("read it with local OCR in Latvian (lav)"):
        options = [label for _, label in ocr_language_options("en")]
        gui.choose(T("imp.ocr_language"), T("imp.ocr_lang.lav"), options=options)
        # The program's processor use while it only shows the page, as the
        # baseline for the reading's own (program_cpu_cores of the profile).
        journey.facts["program_cpu_cores_idle"] = program_cpu_cores(gui)
        journey.facts["logical_processors"] = os.cpu_count()
        seen = {p.name for p in (gui.out / "ocr-profiles").glob("*.json")}
        gui.click(T("imp.ocr_run"), control_type="Button")
        started = time.monotonic()
        # Whatever the reading gives is recorded before it is checked.
        gui.wait_text(T("imp.state.ocr_used", pages="pages 1 and 2",
                        ocr=T("imp.ocr_lang.lav")), timeout=600)
        # Until UI Automation shows the result (this driver's polling and
        # scrolling included); the program's own timings are the profile.
        journey.facts["ocr_in_program_seconds"] = round(time.monotonic() - started, 1)
        journey.facts["ocr_profile_first"] = latest_profile(gui, seen)
        print(f"  [ocr] in the program (first reading): {journey.facts['ocr_profile_first']}",
              flush=True)
        journey.facts["candidates_in_program"] = [
            text for text in gui.texts() if "candidate items" in text][:3]
        gui.wait_text(T("imp.read_ok", instruments=1, items=52, name=pdf.name), timeout=30)
    with journey.step("52 candidates; the OCR stays a visible fact"):
        gui.wait_text("52 candidate items")
        gui.wait_text(T("imp.state.ocr_used", pages="pages 1 and 2",
                        ocr=T("imp.ocr_lang.lav")))
    with journey.step("read it again in the same program (warm): the same 52 candidates"):
        seen = {p.name for p in (gui.out / "ocr-profiles").glob("*.json")}
        gui.click(T("imp.ocr_again"), control_type="Button")
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline and latest_profile(gui, seen) is None:
            time.sleep(0.5)
        journey.facts["ocr_profile_again"] = latest_profile(gui, seen)
        print(f"  [ocr] in the program (read again): {journey.facts['ocr_profile_again']}",
              flush=True)
        expect(journey.facts["ocr_profile_again"] is not None, "the second reading wrote no profile")
        expect(journey.facts["ocr_profile_again"]["items"] == 52,
               f"{journey.facts['ocr_profile_again']['items']} candidates on the second reading")
        gui.wait_text("52 candidate items", timeout=60)
    with journey.step("the legend is offered as one documented scale for all 52 items"):
        wizard_step(gui, 2)
        gui.wait_text(T("imp.scale_items", count=52))
        gui.wait_text(T("imp.evidence.legend"))
        scales = gui.query(T("imp.apply_scale"), control_type="Button")
        journey.facts["documented_scales"] = len(scales)
        expect(len(scales) == 1, f"{len(scales)} scales offered instead of one")
    finish_import(gui, journey)
    with journey.step("the draft holds the 52 items"):
        gui.wait_text("52. ", timeout=30)
        expect(not gui.has_text("53. "), "a 53rd question was created")


def answer_form(gui: Gui, group: str, stress: str, age: int) -> None:
    """Fill in the questionnaire form in its dialog, like a respondent."""
    from survey_storage import likert_choices
    from survey_ui import _template_questions

    questions = {q["key"]: q for q in _template_questions("psychology")}
    labels = dict(likert_choices(questions["stress_q1"]))
    gui.check(questions["consent"]["prompt"])
    gui.type_into(T("q.your_answer"), str(age), index=0)
    gui.click(group, control_type=("RadioButton", "Text"), index=0)
    gui.click(T("common.no"), control_type=("RadioButton", "Text"), index=0)
    # Each rating under its own question ("6. Fictional stress statement 1 *"):
    # the form scrolls, so the n-th "4 — Often" on screen is not item n.
    numbers = [i + 1 for i, q in enumerate(_template_questions("psychology"))
               if str(q.get("key", "")).startswith("stress_q")]
    for number in numbers:
        rate(gui, number, labels[int(stress)])


def rate(gui: Gui, number: int, option: str) -> None:
    """Click ``option`` of question ``number`` in the open form."""
    heading = gui.find(regex=rf"^{number}\. ", control_type="Text")
    for _ in range(12):
        top = heading.element_info.rectangle.bottom
        below = sorted((e for e in gui.query(option, control_type="RadioButton")
                        if e.element_info.rectangle.top >= top),
                       key=lambda e: e.element_info.rectangle.top)
        if below and gui.clickable(below[0]):
            rect = below[0].element_info.rectangle
            below[0].click_input(coords=(min(20, rect.width() // 2), rect.height() // 2))
            time.sleep(0.6)
            return
        gui.wheel(-2)                     # bring the options of this question up
    raise StepFailure(f"{option!r} of question {number} is not on screen")


def open_project_a(gui: Gui, journey: Journey) -> None:
    with journey.step("open project A (its dataset is in use)"):
        open_project(gui, "Fictional study A")
        gui.wait_text("sample_ancova.csv")


def journey_responses(gui: Gui, work: Path, journey: Journey) -> None:
    open_project_a(gui, journey)
    with journey.step("start a small questionnaire from a template"):
        nav(gui, "nav.questionnaires")
        # Narrow windows show one pane at a time: the list holds the templates.
        if gui.query(T("q.questions"), control_type="Button"):
            gui.click(T("q.questions"), control_type="Button")
        gui.click(T("common.continue"), control_type=("Button", "Text"))
        with contextlib.suppress(StepFailure):
            gui.click(T("q.replace_confirm"), control_type="Button", timeout=5)
        gui.type_into(T("q.survey_title"), "Fictional wellbeing pilot")
    with journey.step("publish it in the project"):
        gui.click(T("q.publish"), control_type="Button")
        gui.click(T("q.publish").rstrip("…"), control_type="Button", index=0, timeout=8)
        gui.wait_text(T("q.publish_ok", title="Fictional wellbeing pilot"))
    for respondent, (group, stress) in enumerate((("A", "2"), ("B", "4"), ("A", "3"))):
        with journey.step(f"collect response {respondent + 1} in the form"):
            opener = gui.click(T("q.collect"), control_type=("Button", "Text"), index=0)

            def form(wait):
                # Flutter names an open dialog "Alert"; the page behind it is hidden.
                deadline = time.monotonic() + wait
                while time.monotonic() < deadline:
                    found = gui.query("Alert", control_type=("Group", "Pane", "Window", "Custom"))
                    if found:
                        return found[-1]
                    time.sleep(0.5)
                return None

            alert = form(8)
            if alert is None:
                print("  [form] the click did not open the response form; pressing the "
                      "button through UI Automation", flush=True)
                Gui.activate(opener)
                alert = form(10)
            if alert is None:
                gui.log_screen("the response form did not open")
            expect(alert is not None, "the response form did not open")
            r = alert.element_info.rectangle
            buttons = [b.element_info.rectangle.top
                       for b in gui.query(T("common.cancel"), control_type="Button")
                       if r.left <= b.element_info.rectangle.left <= r.right]
            # The questions scroll above the dialog's buttons.
            dialog = (r.left, r.top, r.right, (min(buttons) - 6) if buttons else r.bottom)
            print(f"  [form] the response form is open at {dialog}", flush=True)
            with gui.within(dialog):
                answer_form(gui, group, stress, 30 + respondent)
            with gui.within((r.left, r.top, r.right, r.bottom)):
                gui.click(T("q.collect"), control_type="Button")
            gui.wait_text(T("run.done"))
    save_via_dialog(gui, journey, T("q.export_responses"), work / "pilot_responses.csv",
                    kind="csv", contains=("stress_q1",))
    with journey.step("the codebook is written next to the CSV"):
        journey.facts["codebook"] = verify_saved(work / "pilot_responses_codebook.json",
                                                 kind="json")
        rows = (work / "pilot_responses.csv").read_text(encoding="utf-8-sig").strip().splitlines()
        expect(len(rows) == 4, f"3 responses expected in the CSV, found {len(rows) - 1}")
    with journey.step("analyze the responses: asked first, explicitly named"):
        gui.click(T("q.analyze_responses"), control_type="Button", index=0)
        gui.click(T("responses.use"), control_type="Button")
        gui.wait_text(T("responses.name", title="Fictional wellbeing pilot"))
    with journey.step("both datasets stay in the project"):
        nav(gui, "nav.project")
        gui.wait_text("sample_ancova.csv")
        gui.wait_text(T("responses.name", title="Fictional wellbeing pilot"))
    with journey.step("return to the original dataset with its levels"):
        gui.click(T("source.use"), control_type=("Button", "Text"), index=0)
        gui.wait_text(T("source.now_using", name="sample_ancova.csv"))


# Interface identifiers that must never reach the screen untranslated.
RAW_KEY = re.compile(r"\b(?:block|why|alt|design|role|rec|goal|disabled|level)\.[a-z_]+\b")


def journey_blocked_design(gui: Gui, work: Path, journey: Journey) -> None:
    """A design the methods cannot accept is refused in words (never a raw
    identifier such as ``block.level_mismatch``) and nothing can be run;
    choosing a suitable variable lifts the refusal."""
    open_project_a(gui, journey)
    with journey.step("guided analysis: compare groups"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        with contextlib.suppress(StepFailure):     # a question is already chosen
            gui.click(T("analyze.change_goal"), control_type=("Button", "Text"), timeout=4)
        # A question tile is named by its title, its explanation and its tooltip.
        gui.click(regex="^" + re.escape(T("goal.compare")) + r"\b",
                  control_type=("Button", "Text", "Group", "Custom"))
    with journey.step("a quantitative group variable is refused in words"):
        # Stage 36: outcomes are a multiple choice (one or more).
        gui.check(option_label("wellbeing", "scale"))
        gui.choose(T("role.group"), option_label("age", "scale"), options=ANCOVA_OPTIONS)
        gui.wait_text(T("design.blocked"))
        gui.wait_text("age is quantitative")
        raw = [text for text in gui.texts() if RAW_KEY.search(text)]
        expect(not raw, f"untranslated identifiers on screen: {raw[:3]}")
        expect(not gui.query(regex=r"^" + re.escape(T("rec.run", method="")),
                             control_type="Button"),
               "a run button is offered for a refused design")
        gui.shot("blocked-design")
    with journey.step("a categorical group lifts the refusal"):
        gui.choose(T("role.group"), option_label("group", "nominal"), options=ANCOVA_OPTIONS)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and gui.has_text(T("design.blocked")):
            time.sleep(0.5)
        expect(not gui.has_text(T("design.blocked")), "the refusal stayed after the correction")


# ------------------------------------------- installed application (#44)
PREVIEW_PROJECT = "Preview-era study (fictional)"
PREVIEW_SURVEY = "Preview-era questionnaire (fictional)"
INSTALLED_PROJECT = "Installed study (fictional)"


def _snapshot(folder: Path) -> dict[str, str]:
    import hashlib

    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()
            and not p.name.endswith("-shm") and not (p.name.endswith("-wal") and p.stat().st_size == 0)}


def seed_preview_data() -> tuple[Path, str]:
    """What a preview build left in Flet's per-user folder ("Your Company"):
    a project with a dataset and a questionnaire with a response. Synthetic."""
    import legacy_data
    import project_store as ps
    from survey_storage import create_survey, submit_response

    folder = Path(os.environ["APPDATA"]).joinpath(*legacy_data.PREVIEW_FOLDER)
    store = ps.ProjectStore(folder / "projects")
    info = store.create(PREVIEW_PROJECT)
    with store.open(info.id) as project:
        project.add_question("Does a fictional routine relate to stress?")
        project.import_dataset(ROOT / "examples" / "sample_scale.csv", mode="copy")
    ps._OPEN.clear()
    questions = [{"key": "group", "kind": "single_choice", "prompt": "Synthetic group",
                  "required": True, "options": ["A", "B"]}]
    survey = create_survey(folder / "surveys", PREVIEW_SURVEY, "Fictional", questions)
    submit_response(folder / "surveys", survey.survey_id, {"group": "A"})
    return folder, info.id


def journey_legacy_migration(gui: Gui, work: Path, journey: Journey) -> None:
    """A researcher who used a preview build installs the application: the
    first start offers to copy the earlier data, copies and checks it, and
    leaves the originals as they were."""
    import data_ui

    expect(gui.real_data, "run installed journeys with --real-data")
    with journey.step("leave data where a preview build kept it"):
        gui.stop()
        folder, project_id = seed_preview_data()
        before = _snapshot(folder)
        journey.facts["preview_folder"] = str(folder)
    with journey.step("the first start offers to copy it"):
        gui.start(ready=data_ui.t("en", "title"))
        gui.wait_text(PREVIEW_PROJECT, scroll=False)
        gui.wait_text(PREVIEW_SURVEY, scroll=False)
        gui.shot("earlier data offered")
    with journey.step("copy it and see every copy checked"):
        gui.click(data_ui.t("en", "copy"), control_type="Button")
        gui.wait_text("Each copy was checked against its original", timeout=90, scroll=False)
        gui.shot("earlier data copied")
        gui.click(data_ui.t("en", "close"), control_type="Button")
    with journey.step("the copied project opens"):
        open_project(gui, PREVIEW_PROJECT)
    with journey.step("the copies are in the data folder, the originals unchanged"):
        data = Path(os.environ["LOCALAPPDATA"]) / "StatisticalResearchAssistant"
        expect((data / "projects" / project_id / "project.sqlite3").is_file(),
               f"no copy of the project in {data}")
        expect(len(list((data / "surveys").glob("survey_*.sqlite3"))) == 1,
               "the questionnaire was not copied")
        expect(_snapshot(folder) == before, "the preview folder changed")
        journey.facts.update(data_folder=str(data), copied_project=project_id)
    with journey.step("the next start does not ask again"):
        gui.stop()
        gui.start()
        expect(not gui.has_text(data_ui.t("en", "title")), "the copy was offered again")


def journey_installed_data(gui: Gui, work: Path, journey: Journey) -> None:
    """A project created in the installed application lives in the per-user
    data folder; the program folder gains nothing (updates and uninstalling
    can therefore never touch research data)."""
    expect(gui.real_data, "run installed journeys with --real-data")
    program = gui.exe.parent
    data = Path(os.environ["LOCALAPPDATA"]) / "StatisticalResearchAssistant"
    before = {p.relative_to(program).as_posix() for p in program.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts}
    create_project(gui, journey, INSTALLED_PROJECT)
    with journey.step("the project is in the per-user data folder"):
        gui.stop()
        import sqlite3

        titles = []
        for db in (data / "projects").glob("*/project.sqlite3"):
            with contextlib.closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
                titles.append(con.execute("SELECT title FROM project").fetchone()[0])
        expect(INSTALLED_PROJECT in titles, f"{INSTALLED_PROJECT} is not in {data}: {titles}")
        after = {p.relative_to(program).as_posix() for p in program.rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts}
        expect(after == before, f"the program folder gained files: {sorted(after - before)[:10]}")
        journey.facts.update(data_folder=str(data), projects=titles)
    with journey.step("it reopens after a restart"):
        gui.start()
        open_project(gui, INSTALLED_PROJECT)


# ------------------------------------------------ in-app updates (#45)
_UPDATE_SERVER = None


def update_server():
    """The local update server of test builds (tools/update_test_server.py)."""
    global _UPDATE_SERVER
    if _UPDATE_SERVER is None:
        from update_test_server import UpdateTestServer

        _UPDATE_SERVER = UpdateTestServer(Path(os.environ["SRA_E2E_UPDATE_ROOT"]), 8765).start()
    return _UPDATE_SERVER


def check_for_updates(gui: Gui, expected: str, *, scenario: str, fault=None) -> None:
    import update_ui

    server = update_server()
    server.scenario, server.fault = scenario, fault
    nav(gui, "nav.settings")
    gui.click(update_ui.t("en", "check"), control_type="Button")
    gui.wait_text(expected, timeout=90, scroll=False)


def close_dialog(gui: Gui) -> None:
    import update_ui

    gui.click(update_ui.t("en", "close"), control_type="Button")
    time.sleep(1)


def journey_update_refusals(gui: Gui, work: Path, journey: Journey) -> None:
    """Updates that must never be installed are refused in words, and the
    program keeps working: another signer, an older version, a damaged file."""
    import update_ui

    expect(gui.real_data, "run update journeys with --real-data")
    data = Path(os.environ["LOCALAPPDATA"]) / "StatisticalResearchAssistant"
    with journey.step("update information signed with another key is rejected"):
        check_for_updates(gui, "is not signed by the publisher of this application",
                          scenario="tampered")
        gui.shot("another signer rejected")
        close_dialog(gui)
    with journey.step("an older version is never offered (no downgrade)"):
        check_for_updates(gui, update_ui.t("en", "latest", version=os.environ["SRA_E2E_UPDATE_FROM"]),
                          scenario="older")
        gui.shot("older version not offered")
        close_dialog(gui)
    with journey.step("a damaged download is deleted and nothing is started"):
        target = os.environ["SRA_E2E_UPDATE_TO"]
        check_for_updates(gui, update_ui.t("en", "available", version=target), scenario="good")
        update_server().fault = "corrupt"
        gui.click(update_ui.t("en", "update_now"), control_type="Button")
        gui.wait_text("does not match the published checksum", timeout=240, scroll=False)
        gui.shot("damaged download refused")
        expect(gui.process is not None and gui.process.poll() is None, "the program stopped")
        expect(not list((data / "updates").glob("*.exe")), "a damaged installer was kept")
        update_server().fault = None
        gui.click(update_ui.t("en", "later"), control_type="Button")
    journey.facts["requests"] = update_server().requests[-10:]


def journey_update_a_to_b(gui: Gui, work: Path, journey: Journey) -> None:
    """The acceptance test of Stage 35: the installed program is told about
    a new version, shows what is new, downloads and checks it (after an
    interruption), installs it with one click, starts again as the new
    version and opens the same project."""
    import update_ui

    expect(gui.real_data, "run update journeys with --real-data")
    target = os.environ["SRA_E2E_UPDATE_TO"]
    data = Path(os.environ["LOCALAPPDATA"]) / "StatisticalResearchAssistant"
    server = update_server()
    server.scenario, server.fault = "good", None
    with journey.step("the new version is announced when the program starts"):
        state = data / "updates" / "state.json"
        with contextlib.suppress(OSError, ValueError):
            value = json.loads(state.read_text(encoding="utf-8"))
            value.pop("last_check", None)
            value.pop("snoozed", None)
            state.write_text(json.dumps(value), encoding="utf-8")
        gui.stop()
        gui.start()
        gui.wait_text(update_ui.t("en", "available", version=target), timeout=120, scroll=False)
        gui.shot("update announced")
    with journey.step("what's new"):
        gui.click(update_ui.t("en", "whats_new"), control_type="Button")
        gui.wait_text("Fictional change list for the update test", timeout=30, scroll=False)
        gui.shot("what's new")
    with journey.step("an interrupted download can simply be retried"):
        server.fault = "interrupt"
        gui.click(update_ui.t("en", "update_now"), control_type="Button")
        gui.wait_text("The download was interrupted", timeout=240, scroll=False)
        gui.shot("download interrupted")
    with journey.step("update now: download, check, install, restart"):
        gui.click(update_ui.t("en", "update_now"), control_type="Button")
        with contextlib.suppress(StepFailure):     # shown for a few seconds only
            gui.wait_text("Installing version", timeout=300, scroll=False)
            gui.shot("installing")
        old = gui.process
        expect(old is not None, "no running program")
        try:
            old.wait(timeout=90)
        except subprocess.TimeoutExpired as error:
            raise StepFailure("the program did not close itself for the update") from error
        came_forward = gui.attach(timeout=360,
                                  ready=update_ui.t("en", "updated_title", version=target))
        journey.facts["came_to_front_by_itself"] = came_forward
    with journey.step("the new version reports the update"):
        gui.wait_text(update_ui.t("en", "updated_title", version=target), timeout=120, scroll=False)
        gui.wait_text(update_ui.t("en", "updated"), timeout=10, scroll=False)
        gui.wait_text("projects are in place", timeout=10, scroll=False)
        gui.shot("updated")
        gui.click(update_ui.t("en", "close"), control_type="Button")
    with journey.step("the project opens in the new version"):
        open_project(gui, INSTALLED_PROJECT)
    with journey.step("Settings name the new version"):
        nav(gui, "nav.settings")
        gui.wait_text(update_ui.t("en", "version", version=target), timeout=20)
        gui.shot("new version in settings")
    # Spec §14 (packaging regression): A → B → open the project → use the
    # new functionality, here a Stage 36 batch analysis in that project.
    from stage36_fixtures import generator

    nav(gui, "nav.project")
    open_data(gui, journey, generator().create_csv(work))
    accept_levels(gui, journey)
    with journey.step("the new version runs eight correlations in one batch"):
        run_eight_correlations(gui)
        gui.wait_text("p (Holm)", timeout=30)
        gui.shot("stage 36 batch after the update")
    history = data / "updates" / "history.json"
    with contextlib.suppress(OSError, ValueError):
        journey.facts["history"] = json.loads(history.read_text(encoding="utf-8"))["updates"][-1]
    journey.facts["ranges"] = [r for _, r in server.requests if r]
    # Checked when the new version appeared, before this driver touched its
    # window; reported last so that a failure here still shows the rest.
    with journey.step("the new version came to the front by itself"):
        expect(came_forward, "after the update the program's window stayed behind another "
                             "window (its outcome was hidden)")


# ------------------------------------------------ Stage 36 research tasks
STAGE36_PROJECT = "Fictional Stage 36 study"
# UI Automation names a chip by its label, then ". " and its tooltip (or a
# new line and its explanation), e.g. "5. Method. The recommended method…".
CHIP_END = r"(\.|\n|$)"


def stage36_options() -> list[str]:
    """The variable dropdown of the synthetic UCLA/SACS table after its
    levels are accepted: every variable but the identifier, in column order."""
    from stage36_fixtures import SCALES

    return [option_label("Age", "scale"), option_label("Sex", "nominal"),
            option_label("UCLA", "scale"), *[option_label(s, "scale") for s in SCALES],
            option_label("UCLA_Level", "ordinal")]


def journey_stage36_tasks(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journeys 1, 2 and 9 on the packaged EXE: eight correlations
    in one batch, back to the task and run again, a restart that brings the
    task and its result back; and each research step opens itself (D1)."""
    import pandas as pd

    from batch_correlation import correlate_many
    from stage36_fixtures import SCALES, generator

    csv = generator().create_csv(work)
    expected = correlate_many(pd.read_csv(csv), "UCLA", list(SCALES), method="spearman")
    journey.facts["engine_rho"] = {row.y: round(row.estimate, 2) for row in expected.rows}
    create_project(gui, journey, STAGE36_PROJECT)
    open_data(gui, journey, csv)
    with journey.step("the participant code is suggested as identifier"):
        nav(gui, "nav.data")
        gui.wait_text(T("level.id"))
    accept_levels(gui, journey)
    title = T("task.title_relate", x="UCLA", count=8)
    with journey.step("UCLA with eight scales: goal, UCLA, all scales, Spearman, Run"):
        run_eight_correlations(gui)
        gui.shot("eight correlations in one batch")
    with journey.step("one table: eight pairs, N, interval, raw and Holm p"):
        for scale in SCALES:
            gui.wait_text(scale, timeout=10)
        gui.wait_text("p (Holm)", timeout=10)
        gui.wait_text(T("task.rerun"), timeout=10)     # still in the task, not in Results
    with journey.step("back to the task and run it again in two actions"):
        nav(gui, "nav.results")
        nav(gui, "nav.analyze")
        gui.click(T("task.rerun"), control_type="Button")
        gui.wait_text(T("task.versions", count=2), timeout=120)
        gui.shot("task run again")
    with journey.step("each research step opens its own step (D1)"):
        gui.click(regex=r"^5\. " + re.escape(T("journey.method")) + CHIP_END,
                  control_type=("Button", "Text", "Group", "Custom"))
        # The application scrolls to the step itself: found without the
        # driver scrolling (scroll=False), as a researcher would see it.
        gui.find(T("step.method"), timeout=15, scroll=False)
        gui.click(regex=r"^3\. " + re.escape(T("journey.variables")) + CHIP_END,
                  control_type=("Button", "Text", "Group", "Custom"))
        gui.find(T("data.dictionary"), timeout=15, scroll=False)      # the dictionary
    with journey.step("restart: the task and its result come back"):
        gui.stop()
        gui.start()
        open_project(gui, STAGE36_PROJECT)
        nav(gui, "nav.analyze")
        gui.click(regex="^" + re.escape(title) + CHIP_END,
                  control_type=("Button", "Text", "Group", "Custom"))
        gui.wait_text("p (Holm)", timeout=30)
        gui.shot("task after restart")


def run_eight_correlations(gui: Gui) -> str:
    """Guided analysis: UCLA with the eight scales (Spearman) in one batch,
    until the task's table is shown; returns the task's title."""
    title = T("task.title_relate", x="UCLA", count=8)
    nav(gui, "nav.analyze")
    gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
    gui.click(regex="^" + re.escape(T("goal.relate")) + r"\b",
              control_type=("Button", "Text", "Group", "Custom"))
    gui.choose(T("role.x"), option_label("UCLA", "scale"), options=stage36_options())
    gui.click(T("pick.all_scale", count=9), control_type="Button")
    gui.check(option_label("Age", "scale"), False)
    gui.click(T("rec.use_instead"), control_type="Button", index=0)   # Spearman
    gui.click(regex="^" + re.escape(T("rec.run", method="")) + "Spearman",
              control_type="Button")
    gui.wait_text(title, timeout=120)
    return title


STAGE36_CHARTS_PROJECT = "Fictional Stage 36 charts"


def click_chip(gui: Gui, label: str) -> None:
    """A chip or tile: named by its label, sometimes followed by a tooltip."""
    gui.click(regex="^" + re.escape(label) + CHIP_END,
              control_type=("Button", "Text", "Group", "Custom"))


def journey_stage36_charts(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journeys 3 and 4 on the packaged EXE: the eight scales by the
    existing UCLA_Level in one Kruskal–Wallis batch; then Chart Studio: change
    the chart type without running the analysis, a multi-boxplot, an image on
    the clipboard (a bitmap of the announced size, not a path), PNG and SVG
    files, the view for the Word report, and the view after a restart."""
    from image_clipboard import clipboard_image_size
    from stage36_fixtures import SCALES, generator

    csv = generator().create_csv(work)
    create_project(gui, journey, STAGE36_CHARTS_PROJECT)
    open_data(gui, journey, csv)
    accept_levels(gui, journey)
    title = T("task.title_compare", group="UCLA_Level", count=8)
    with journey.step("eight scales by UCLA_Level: one Kruskal–Wallis batch"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        click_chip(gui, T("goal.compare"))
        gui.choose(T("role.group"), option_label("UCLA_Level", "ordinal"),
                   options=stage36_options())
        gui.click(T("pick.all_scale", count=10), control_type="Button")
        gui.check(option_label("Age", "scale"), False)
        gui.check(option_label("UCLA", "scale"), False)
        # The recommendation (which needs the outcomes too) explains the small
        # groups before Run (D9).
        gui.wait_text("fewer than five values", timeout=20)
        # The method's own confirmations (engine wording, never pre-ticked).
        gui.check("I confirm the groups contain independent participants")
        gui.check("I reviewed the outcome distributions, outliers and group sizes")
        gui.click(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        gui.wait_text(title, timeout=180)
        for scale in SCALES:
            gui.wait_text(scale, timeout=10)
        gui.shot("kruskal-wallis batch")
    with journey.step("Chart Studio opens from the task"):
        gui.click(T("chart.open"), control_type="Button")
        gui.wait_text(T("chart.unchanged"), timeout=60)
        gui.wait_text("Small groups of UCLA_Level", timeout=20)
        gui.shot("chart studio")
    with journey.step("change the chart type: violin, then multi-boxplot panels"):
        click_chip(gui, T("chart.kind.violin"))
        gui.wait_text(T("chart.alt", text="Violin Plots of 8 Variables by UCLA_Level"), timeout=60)
        click_chip(gui, T("chart.kind.multi_boxplot"))
        gui.click(T("chart.layout.panels"), control_type="Button")
        gui.wait_text(T("chart.alt", text="Boxplots of 8 Variables by UCLA_Level"), timeout=60)
        expect(not gui.has_text(T("run.failed", error="")[:12]), "an analysis ran")
        gui.shot("multi-boxplot")
    custom = "Fictional coping by loneliness level"
    with journey.step("title typed in Appearance"):
        click_chip(gui, T("chart.appearance"))
        gui.type_into(T("chart.title_field"), custom)
        gui.click(T("chart.apply"), control_type="Button")
        gui.wait_text(T("chart.alt", text=custom), timeout=60)
    with journey.step("copy: the clipboard holds a bitmap of the announced size"):
        gui.click(T("chart.copy"), control_type="Button")
        prefix = T("chart.copied", width=0, height=0).split("(")[0]
        gui.wait_text(prefix, timeout=60)
        announced = next(text for text in gui.texts() if text.startswith(prefix))
        match = re.search(r"\((\d+) × (\d+)", announced)
        expect(match is not None, f"no size in {announced!r}")
        size = clipboard_image_size()
        expect(size is not None, "the clipboard holds no image (CF_DIB)")
        expect(size == (int(match.group(1)), int(match.group(2))),
               f"clipboard {size} differs from the announced {match.groups()}")
        journey.facts["clipboard_bitmap"] = list(size)
    save_via_dialog(gui, journey, T("chart.save_png"), work / "stage36_chart.png", kind="png")
    save_via_dialog(gui, journey, T("chart.save_svg"), work / "stage36_chart.svg", kind="svg",
                    contains=(custom,))
    with journey.step("the view is chosen for the Word report"):
        gui.click(T("chart.report_add"), control_type="Button")
        gui.wait_text(T("chart.report_added")[:40], timeout=30)
    with journey.step("restart: the chart view comes back"):
        gui.stop()
        gui.start()
        open_project(gui, STAGE36_CHARTS_PROJECT)
        nav(gui, "nav.results")
        gui.click(T("chart.open"), control_type="Button")
        gui.wait_text(T("chart.alt", text=custom), timeout=60)
        gui.wait_text(T("chart.report_on"), timeout=20)
        gui.shot("chart after restart")


STAGE36_GROUPS_PROJECT = "Fictional Stage 36 groups"


def journey_stage36_groups(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journey 3 on the packaged EXE: groups from the UCLA score
    (the existing UCLA_Level is offered first; three quantile groups are
    previewed and created as a new variable, UCLA itself unchanged), then
    the eight scales by the new groups in one Kruskal–Wallis batch."""
    import pandas as pd

    from stage36_fixtures import SCALES, generator

    csv = generator().create_csv(work)
    expected = pd.qcut(pd.read_csv(csv)["UCLA"], 3).value_counts(sort=False).tolist()
    journey.facts["engine_group_sizes"] = expected
    create_project(gui, journey, STAGE36_GROUPS_PROJECT)
    open_data(gui, journey, csv)
    accept_levels(gui, journey)
    with journey.step("the existing UCLA_Level is offered for UCLA"):
        nav(gui, "nav.data")
        gui.choose(T("groups.source"), "UCLA", options=["Age", "UCLA", *SCALES])
        gui.wait_text("UCLA_Level already groups UCLA", timeout=20)
    with journey.step("three quantile groups previewed, then created"):
        gui.wait_text(T("groups.counts", valid=55, missing=0, outside=0), timeout=20)
        gui.shot("groups previewed")
        gui.click(T("groups.create"), control_type="Button")
        gui.wait_text("UCLA itself is unchanged", timeout=30)
        # Windows exposes a preview row as one element, not a cell per number:
        # the group sizes are read from the announcement ("Q1 [37, 46]: n = 18").
        for size in expected:
            gui.wait_text(f": n = {size}", timeout=10)
        gui.shot("groups created")
    title = T("task.title_compare", group="UCLA_groups", count=8)
    with journey.step("the eight scales by the new groups: one Kruskal–Wallis batch"):
        gui.click(T("groups.use_existing", name="UCLA_groups"), control_type="Button")
        gui.click(T("pick.all_scale", count=10), control_type="Button")
        gui.check(option_label("Age", "scale"), False)
        gui.check(option_label("UCLA", "scale"), False)
        gui.check("I confirm the groups contain independent participants")
        gui.check("I reviewed the outcome distributions, outliers and group sizes")
        gui.click(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        gui.wait_text(title, timeout=180)
        for scale in SCALES:
            gui.wait_text(scale, timeout=10)
        gui.shot("kruskal-wallis by the new groups")


def stage36_options_with_groups() -> list[str]:
    """The variable dropdown once journey stage36-groups created UCLA_groups."""
    return [*stage36_options(), option_label("UCLA_groups", "ordinal")]


def stage36_report_fragments() -> tuple[str, ...]:
    """What the Word report of journey stage36-report must hold: both results,
    the sections they belong in, numbered tables, the appendix, the data."""
    from research_report import TEXT as REPORT_TEXT
    from stage36_fixtures import CSV

    text = REPORT_TEXT["en"]
    return ("Kruskal–Wallis", "UCLA_groups", "Descriptive: UCLA", text["descriptives"],
            text["tests"], "Table 1", "Table 2", text["appendix"], CSV)


def journey_stage36_report(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journey 8 on the packaged EXE, in the project of
    stage36-groups: the Kruskal–Wallis batch and a description of UCLA go into
    one Word report (numbered sections, each result in its own section). On
    the way, a scale check on totals offers no coefficient (D5, a refusal of
    journey 10). tests/test_stage36_acceptance.py walks the same flow."""
    from stage36_fixtures import SCALES

    title = T("task.title_compare", group="UCLA_groups", count=8)
    with journey.step("the Kruskal–Wallis task goes into the report"):
        open_project(gui, STAGE36_GROUPS_PROJECT)
        nav(gui, "nav.analyze")
        click_chip(gui, title)
        gui.wait_text(T("task.rerun"), timeout=30)
        gui.click(T("results.add_report"), control_type="Button")
        gui.find(T("results.in_report"), control_type="Button", timeout=20)
    with journey.step("a second result: describe UCLA, then into the report"):
        gui.click(T("task.new"), control_type="Button")
        click_chip(gui, T("goal.describe"))
        gui.choose(T("role.variable"), option_label("UCLA", "scale"),
                   options=stage36_options_with_groups())
        gui.click(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        gui.wait_text("Descriptive: UCLA", timeout=120)
        gui.click(T("results.add_report"), control_type="Button")
        gui.find(T("results.in_report"), control_type="Button", timeout=20)
        gui.shot("two results in the report")
    with journey.step("totals get no reliability coefficient (D5)"):
        nav(gui, "nav.analyze")
        gui.click(T("task.new"), control_type="Button")
        click_chip(gui, T("goal.scale"))
        for scale in SCALES[:3]:
            gui.check(option_label(scale, "scale"))
        gui.wait_text("Only a total score is available now", timeout=20)
        runs = gui.query(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        expect(not runs, f"a Run button is offered for totals: {len(runs)}")
        gui.shot("no coefficient from totals")
    with journey.step("one Word report from both results"):
        nav(gui, "nav.reports")
    save_via_dialog(gui, journey, T("reports.export_docx"), work / "stage36_report.docx",
                    kind="docx", contains=stage36_report_fragments())


DAMAGED_PDF = b"%PDF-1.4\n% fictional damaged scan: the file ends here"


def damaged_document_fragments(broken: str, kept: str, items: int = 120) -> tuple[str, ...]:
    """What the status line says when ``broken`` cannot be read while
    ``kept`` is under review (each fragment is one text on screen)."""
    return (T("imp.state.error"), f"{broken} could not be read",
            f"The document under review, {kept} ({items} items), is unchanged.")


def journey_import_damaged(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec §14 journey 10 on the packaged EXE (damaged documents): while a
    Word document is under review, a damaged PDF is refused with its reason
    and the next step; the review under way is kept and goes on.
    tests/test_stage36_acceptance.py walks the same flow."""
    from stage36_fixtures import generator

    docx = generator().create_docx_unnumbered(work)
    broken = work / "fictional_broken_scan.pdf"
    broken.write_bytes(DAMAGED_PDF)
    import_document(gui, journey, docx, expected_items=120, instruments=2)
    import_document(gui, journey, broken, shows=T("imp.state.error"))
    with journey.step("the damaged file is explained; the review under way is kept"):
        for fragment in damaged_document_fragments(broken.name, docx.name):
            gui.wait_text(fragment, timeout=20)
        gui.shot("damaged document refused")
    with journey.step("the researcher goes on with the document under review"):
        review_form(gui, COPE_SITUATIONAL, index=1,
                    then=T("imp.status.form_of", number=2, total=2))


def journey_installed_reopen(gui: Gui, work: Path, journey: Journey) -> None:
    """After an update (or a reinstall) the same projects open again."""
    expect(gui.real_data, "run installed journeys with --real-data")
    gui.stop()
    gui.start()
    for title in (INSTALLED_PROJECT, PREVIEW_PROJECT):
        with journey.step(f"open {title}"):
            open_project(gui, title)


# ============================== Stage 36.8 (#62, Part 8): user acceptance
# Spec journeys F (psychometrics) and E (import: cancel, resume after a
# restart) and the negative paths a researcher can meet, as far as the
# packaged program shows them. tests/test_stage368_acceptance.py walks the
# same flows in the workspace harness, with the texts defined here.
PSYCHOMETRICS_PROJECT = "Fictional psychometrics study"
NEGATIVE_PROJECT = "Fictional negative paths"
ALPHA_ITEM = "ZEP04"      # α if this item were deleted: computed by the driver itself
ALPHA_IF_DELETED = "α if deleted"        # the column of the item diagnostics table
TOTALS_ONLY = "Only a total score is available now"     # D5, as journey stage36-report
RESUME_ITEM = 13          # the item compared with the source before the restart
# The scale check's summary (run.summary), e.g.
# "Cronbach’s α = 0.57; McDonald’s ω = 0.71; k = 10, n = 192."
SUMMARY = re.compile(r"Cronbach’s α = (?P<alpha>[−-]?\d*\.\d+); McDonald’s ω = "
                     r"(?P<omega>[−-]?\d*\.\d+); k = (?P<k>\d+), n = (?P<n>\d+)")


def data_folder(gui: Gui) -> Path:
    """Where the program keeps this run's projects, questionnaires and reviews."""
    if gui.real_data:
        return Path(os.environ["LOCALAPPDATA"]) / "StatisticalResearchAssistant"
    return Path(gui.data_dir)


def template_pattern(key: str) -> re.Pattern:
    """The English text of ``key`` as a pattern: each {placeholder} matches
    any text (a folder may be shown in its long or its 8.3 form)."""
    from workspace_text import T as TABLE

    parts = re.split(r"\{[a-z_]+\}", TABLE[key][0])
    return re.compile(".+?".join(re.escape(part) for part in parts))


def number_shown(text: str) -> float:
    """A number as the program shows it: "0.57", ".72" (APA, no leading
    zero), "−.12", "+.154"."""
    return float(text.strip().replace("−", "-").replace("+", ""))


def same_as_shown(value: float, text: str) -> bool:
    """``value`` is what ``text`` shows, at the precision shown."""
    shown = text.strip().replace("−", "-").replace("+", "")
    digits = len(shown.split(".", 1)[1]) if "." in shown else 0
    return f"{float(value):.{digits}f}" == f"{number_shown(shown):.{digits}f}"


# ------------------------------------------------- what is on the screen
def element_text(gui: Gui, element) -> str:
    """What an element shows: its name, or a text field's value."""
    info = element.element_info
    name = info.name or ""
    if not name and info.control_type in TEXT_FIELDS:
        return gui.value(element)
    return name


def screen_texts(gui: Gui) -> list[tuple[object, str]]:
    """(element, text) of everything that shows a text: its name and, for
    a text field, its value (Flutter's selectable text; see Gui.texts)."""
    found = []
    for element in gui.elements():
        with contextlib.suppress(Exception):
            info = element.element_info
            if info.name:
                found.append((element, info.name))
            if info.control_type in TEXT_FIELDS:
                value = gui.value(element)
                if value:
                    found.append((element, value))
    return found


def find_text(gui: Gui, fragment: str | None = None, *, regex: str | None = None,
              exact: bool = False, timeout: float = 30, moves: int = 60,
              first: str = "down", control_type=None) -> tuple[object, str]:
    """(element, text) of what shows ``fragment`` (or matches ``regex``),
    scrolled into view; only elements of ``control_type`` when it is given.
    Waits; then scrolls ``first`` down (or up) and back, in steps larger than
    Gui.find's, as a person looks for one line of a long page (a result's
    tables run thousands of pixels below its summary)."""
    pattern = re.compile(regex) if regex is not None else None
    kinds = (control_type,) if isinstance(control_type, str) else control_type

    def matches(element, text: str) -> bool:
        if kinds and element.element_info.control_type not in kinds:
            return False
        if pattern is not None:
            return bool(pattern.search(text))
        return text == fragment if exact else fragment in text

    deadline = time.monotonic() + timeout
    settle = time.monotonic() + min(4.0, timeout / 2)
    done, direction = 0, (-1 if first == "down" else 1)
    while True:
        for element, text in screen_texts(gui):
            if matches(element, text):
                with contextlib.suppress(Exception):
                    gui.scroll_into_view(element)
                return element, text
        if time.monotonic() > deadline:
            break
        if time.monotonic() > settle and done < 2 * moves:
            gui.wheel(5 * direction)
            done += 1
            if done == moves:
                direction = -direction
        else:
            time.sleep(0.4)
    what = regex if pattern is not None else fragment
    gui.dump(f"no-text-{what}")
    gui.shot(f"no-text-{what}")
    gui.log_screen(f"text never appeared: {str(what)[:50]!r}")
    raise StepFailure(f"text never appeared: {what!r}")


def wait_any(gui: Gui, wanted: dict, timeout: float = 30, *, scroll: bool = True,
             step: int = 3) -> tuple[str, str]:
    """(name, text) of the first of several outcomes on screen: ``wanted``
    maps a name to a text fragment or a compiled pattern, in priority order.
    It scrolls down, then up, by ``step`` wheel notches at a time."""
    deadline = time.monotonic() + timeout
    settle = time.monotonic() + min(4.0, timeout / 2)
    moves, direction = 0, -1
    while True:
        texts = [text for _, text in screen_texts(gui)]
        for key, what in wanted.items():
            for text in texts:
                if (what.search(text) if hasattr(what, "search") else what in text):
                    return key, text
        if time.monotonic() > deadline:
            break
        if scroll and time.monotonic() > settle and moves < 40:
            gui.wheel(step * direction)
            moves += 1
            if moves == 20:
                direction = 1
        else:
            time.sleep(0.5)
    gui.dump("no-outcome")
    gui.shot("no-outcome")
    gui.log_screen(f"none of {list(wanted)} appeared")
    raise StepFailure(f"none of these appeared: {list(wanted)}")


def shot_at(gui: Gui, element, title: str) -> Path | None:
    """A screenshot with ``element`` on screen (what is being verified, not
    another part of the page), and a close-up of it next to it."""
    with contextlib.suppress(Exception):
        gui.scroll_into_view(element)
    path = gui.shot(title)
    with contextlib.suppress(Exception):
        box = element.element_info.rectangle
        left, top, right, bottom = gui.window_box()
        crop = (max(box.left - 160, left) - left, max(box.top - 90, top) - top,
                min(box.right + 160, right) - left, min(box.bottom + 90, bottom) - top)
        gui.grab().crop(crop).save(path.with_name(path.stem + "-closeup.png"))
    return path


def row_cells(gui: Gui, anchor) -> list[tuple[int | None, str]]:
    """(left, text) of the cells in ``anchor``'s table row, left to right.
    Windows may expose a table row as ONE element whose name holds its cells
    as lines (journey stage36-groups), or each cell on its own; a merged row
    gives its lines with left None."""
    own = element_text(gui, anchor)
    if "\n" in own:
        return [(None, line) for line in own.split("\n") if line.strip()]
    box = anchor.element_info.rectangle
    height = max(1, box.height())
    found, seen = [], set()
    for element, text in screen_texts(gui):
        if "\n" in text:            # a merged row over the same cells
            continue
        with contextlib.suppress(Exception):
            rect = element.element_info.rectangle
            middle = (rect.top + rect.bottom) // 2
            if (box.top - 4 <= middle <= box.bottom + 4 and rect.height() <= 3 * height + 12
                    and rect.right > box.left - 2 and (rect.left, text) not in seen):
                seen.add((rect.left, text))
                found.append((rect.left, text))
    found.sort(key=lambda cell: cell[0])
    return found


def column_cell(gui: Gui, header_anchor, header: str, row_anchor) -> str | None:
    """The text of ``row_anchor``'s row in the column headed ``header``: by
    position when the cells are separate elements, else by column order."""
    heads, cells = row_cells(gui, header_anchor), row_cells(gui, row_anchor)
    left = next((x for x, text in heads if text == header), None)
    if left is not None and cells and all(x is not None for x, _ in cells):
        return min(cells, key=lambda cell: abs(cell[0] - left))[1]
    names, values = [text for _, text in heads], [text for _, text in cells]
    if header in names and len(names) == len(values):
        return values[names.index(header)]
    return None


def toggle_state(element):
    """1 (ticked), 0 or None (not readable through UI Automation)."""
    with contextlib.suppress(Exception):
        return int(element.get_toggle_state())
    return None


# --------------------------------------------------- the project on disk
def project_database(gui: Gui, title: str) -> Path:
    """The database of the project ``title`` (the newest one of that title)."""
    import sqlite3

    found = []
    for db in (data_folder(gui) / "projects").glob("*/project.sqlite3"):
        with contextlib.suppress(sqlite3.Error):
            with contextlib.closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro",
                                                    uri=True)) as con:
                row = con.execute("SELECT title, created_at FROM project").fetchone()
            if row and row[0] == title:
                found.append((row[1], str(db)))
    expect(found, f"no project {title!r} in {data_folder(gui)}")
    return Path(max(found)[1])


def project_query(gui: Gui, title: str, sql: str, args=()) -> list[tuple]:
    """Rows of a read-only query of the project's database (the program
    keeps it open; a read-only connection does not disturb it)."""
    import sqlite3

    database = project_database(gui, title)
    with contextlib.closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro",
                                            uri=True)) as con:
        return con.execute(sql, args).fetchall()


# ------------------------------------------- journey F: psychometrics
def independent_alpha(csv_path: Path, items, *, without: str | None = None) -> tuple[float, int]:
    """(Cronbach's α, complete respondents) computed here with numpy from the
    CSV itself, not by the program's engine: α = k/(k−1)·(1 − Σ var_i /
    var_total) with sample variances (ddof = 1), on the respondents who
    answered every item (the program's complete cases). ``without`` leaves
    one item out of the same respondents: α if that item were deleted."""
    import csv

    import numpy as np

    items = list(items)
    with open(csv_path, encoding="utf-8-sig", newline="") as file:
        rows = [[(row.get(item) or "").strip() for item in items] for row in csv.DictReader(file)]
    answers = np.array([[float(value) for value in row] for row in rows if all(row)])
    if without is not None:
        answers = np.delete(answers, items.index(without), axis=1)
    k = answers.shape[1]
    alpha = k / (k - 1) * (1 - answers.var(axis=0, ddof=1).sum()
                           / answers.sum(axis=1).var(ddof=1))
    return float(alpha), int(answers.shape[0])


def reference_omega(csv_path: Path, items) -> float:
    """McDonald's ω of the same items from the program's validated engine
    (item_diagnostics, which uses omega_analysis), run in this process."""
    import warnings

    from data_loader import load_dataset
    from item_diagnostics import diagnose_items

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(diagnose_items(load_dataset(csv_path), list(items), ci=False).omega.value)


def psychometrics_expected(csv_path: Path) -> dict:
    """What the scale check of the item-level fixture must show."""
    from stage36_fixtures import ITEMS

    alpha, n = independent_alpha(csv_path, ITEMS)
    deleted, _ = independent_alpha(csv_path, ITEMS, without=ALPHA_ITEM)
    return {"k": len(ITEMS), "n": n, "alpha": alpha, "alpha_if_deleted": deleted,
            "omega": reference_omega(csv_path, ITEMS)}


def item_table_title(expected: dict) -> str:
    """The title of the item diagnostics table (ItemDiagnostics.table)."""
    return f"Item diagnostics: {expected['k']} items, N = {expected['n']} complete respondents"


def scale_check_confirmations() -> list[str]:
    """The confirmations the scale check asks for (engine wording, never pre-ticked)."""
    from workspace_methods import METHODS, default_options, required_confirmations
    from workspace_text import label as engine_label

    spec = METHODS["item_diagnostics"]
    return [engine_label("en", c.label) for c in required_confirmations(spec, default_options(spec))]


def psychometrics_report_fragments(expected: dict) -> tuple[str, ...]:
    """What the saved TXT report must hold: the driver's own α and n, the
    engine's ω, at the report's precision."""
    return (f"Items: k = {expected['k']} (", f"complete cases n = {expected['n']} of ",
            f"Cronbach’s α = {expected['alpha']:.2f}",
            f"McDonald’s ω (one factor) = {expected['omega']:.2f}")


def journey_psychometrics(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec journey F on the packaged program: the item-level scale (ten
    invented items, two of them reverse-keyed and not recoded) is checked
    through the guided scale question; Cronbach's α, McDonald's ω and the
    α-if-item-deleted table are on screen and agree with the driver's own
    numpy α (and α without ZEP04) and with ω from the engine run here; the
    TXT report holds them. A totals-only dataset in the same project gets
    no coefficient and no Run button (D5). tests/test_stage368_acceptance.py
    walks the same flow."""
    from stage36_fixtures import ITEMS, SCALES, generator

    csv_path = generator().create_items_csv(work)
    expected = psychometrics_expected(csv_path)
    journey.facts["driver"] = {
        "alpha_numpy": round(expected["alpha"], 6), "n_complete": expected["n"],
        f"alpha_if_deleted_{ALPHA_ITEM}_numpy": round(expected["alpha_if_deleted"], 6),
        "omega_engine_in_driver": round(expected["omega"], 6)}
    create_project(gui, journey, PSYCHOMETRICS_PROJECT)
    open_data(gui, journey, csv_path)
    accept_levels(gui, journey)
    with journey.step("scale check: the ten items of one scale, one construct confirmed"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        click_chip(gui, T("goal.scale"))
        gui.click(T("pick.all_ordinal", count=len(ITEMS)), control_type="Button")
        gui.wait_text(T("design.levels_summary", count=len(ITEMS), levels=T("level.ordinal")))
        journey.facts["items_ticked"] = {
            item: toggle_state(box) for item in ITEMS
            for box in gui.query(option_label(item, "ordinal"), control_type="CheckBox")[:1]}
        for confirmation in scale_check_confirmations():
            gui.check(confirmation)
        gui.click(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        # The result opens at its summary; its export buttons lie below two
        # tables (145 and 10 rows), beyond what Gui.wait_text scrolls to.
        find_text(gui, regex=SUMMARY.pattern, timeout=300, first="up")
    with journey.step("Cronbach's α and McDonald's ω as the driver computes them"):
        element, text = find_text(gui, regex=SUMMARY.pattern, timeout=60, first="up")
        shown = SUMMARY.search(text).groupdict()
        journey.facts["shown_summary"] = text
        expect(same_as_shown(expected["alpha"], shown["alpha"]),
               f"α shown {shown['alpha']}, the driver's numpy α {expected['alpha']:.4f}")
        omega = number_shown(shown["omega"])
        expect(0 <= omega <= 1, f"ω shown {shown['omega']} is not in [0, 1]")
        expect(same_as_shown(expected["omega"], shown["omega"]),
               f"ω shown {shown['omega']}, the engine in the driver {expected['omega']:.4f}")
        expect((int(shown["k"]), int(shown["n"])) == (expected["k"], expected["n"]),
               f"k = {shown['k']}, n = {shown['n']} shown; {expected['k']} items and "
               f"{expected['n']} complete respondents in the CSV")
        shot_at(gui, element, "alpha and omega")
    label = f"{ALPHA_IF_DELETED}: {ALPHA_ITEM}"
    with journey.step(f"verified estimates: {label} as the driver computes it"):
        row, _ = find_text(gui, regex=rf"(?:^|\n){re.escape(label)}(?:\n|$)", timeout=150,
                           moves=90)
        cells = [text for _, text in row_cells(gui, row)]
        journey.facts["verified_estimate_row"] = cells
        value = cells[cells.index(label) + 1] if label in cells[:-1] else None
        expect(value is not None and same_as_shown(expected["alpha_if_deleted"], value),
               f"{label} shown as {value!r}; the driver's numpy value "
               f"{expected['alpha_if_deleted']:.4f}")
        shot_at(gui, row, "alpha if deleted, verified estimates")
    with journey.step(f"the α-if-item-deleted table: {ALPHA_ITEM} as the driver computes it"):
        find_text(gui, item_table_title(expected), timeout=180, moves=120)
        header, _ = find_text(gui, regex=rf"(?:^|\n){re.escape(ALPHA_IF_DELETED)}(?:\n|$)",
                              timeout=30)
        row, _ = find_text(gui, regex=rf"(?:^|\n){ALPHA_ITEM}(?:\n|$)", timeout=30)
        value = column_cell(gui, header, ALPHA_IF_DELETED, row)
        journey.facts["item_table_header"] = [text for _, text in row_cells(gui, header)]
        journey.facts[f"item_table_row_{ALPHA_ITEM}"] = [text for _, text in row_cells(gui, row)]
        journey.facts[f"item_table_alpha_if_deleted_{ALPHA_ITEM}"] = value
        expect(value is not None and same_as_shown(expected["alpha_if_deleted"], value),
               f"{ALPHA_IF_DELETED} of {ALPHA_ITEM} in the table: {value!r}; the driver's "
               f"numpy value {expected['alpha_if_deleted']:.4f}")
        shot_at(gui, row, "alpha-if-item-deleted table")
    with journey.step("the export buttons below the tables"):
        find_text(gui, T("results.save_txt"), exact=True, timeout=120)
    save_via_dialog(gui, journey, T("results.save_txt"), work / "psychometrics_report.txt",
                    kind="txt", contains=psychometrics_report_fragments(expected))
    journey.facts["report_lines"] = [
        line for line in (work / "psychometrics_report.txt").read_text(
            encoding="utf-8-sig").splitlines() if line.startswith(("Cronbach", "McDonald"))]
    totals = generator().create_csv(work)
    with journey.step("a totals-only dataset in the same project"):
        nav(gui, "nav.data")
    open_data(gui, journey, totals)
    accept_levels(gui, journey)
    with journey.step("totals get no reliability coefficient and no Run button (D5)"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        gui.click(T("task.new"), control_type="Button")
        click_chip(gui, T("goal.scale"))
        for scale in SCALES[:3]:
            gui.check(option_label(scale, "scale"))
        element, text = find_text(gui, TOTALS_ONLY, timeout=20)
        journey.facts["totals_refusal"] = text
        runs = gui.query(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        expect(not runs, f"a Run button is offered for totals: {len(runs)}")
        shot_at(gui, element, "no coefficient from totals")
    with journey.step("nothing was calculated from the totals"):
        runs = project_query(gui, PSYCHOMETRICS_PROJECT, "SELECT method FROM runs")
        journey.facts["runs_in_project"] = [method for (method,) in runs]
        expect(journey.facts["runs_in_project"] == ["item_diagnostics"],
               f"results in the project: {journey.facts['runs_in_project']}")


# --------------------------------- journey E: cancel, change, restart, resume
def counts_pattern() -> re.Pattern:
    """The items step's counts, "52 items · 17 need attention · 0 compared
    with the source" (imp.counts)."""
    from workspace_text import T as TABLE

    pattern = re.escape(TABLE["imp.counts"][0])
    for name in ("total", "attention", "checked"):
        pattern = pattern.replace(re.escape("{" + name + "}"), rf"(?P<{name}>\d+)")
    return re.compile(pattern)


def read_counts(gui: Gui, *, checked: int | None = None, timeout: float = 30) -> dict:
    """The counts on screen (until ``checked`` items are checked, if given)."""
    deadline = time.monotonic() + timeout
    while True:
        _, text = find_text(gui, regex=counts_pattern().pattern, timeout=max(5, timeout / 2))
        counts = {k: int(v) for k, v in counts_pattern().search(text).groupdict().items()}
        if checked is None or counts["checked"] == checked or time.monotonic() > deadline:
            return counts
        time.sleep(0.5)


def import_resume_texts(name: str, *, checked: int = 1, total: int = 52) -> dict[str, str]:
    """What journey import-resume waits for, for the document ``name``."""
    return {
        "cancelled": T("imp.scan.cancelled", pages="Pages 1 and 2"),
        "read": T("imp.read_ok", instruments=1, items=total, name=name),
        "ocr_used": T("imp.state.ocr_used", pages="pages 1 and 2", ocr=T("imp.ocr_lang.lav")),
        "offer": T("imp.resume", file=name, checked=checked, total=total),
        "restored": T("imp.state.restored", checked=checked, total=total),
        "discarded": T("imp.discarded", file=name),
    }


def saved_review(gui: Gui, sha: str) -> dict | None:
    """The review the program keeps on disk for the document ``sha``."""
    path = data_folder(gui) / "import_sessions" / f"{sha}.json"
    with contextlib.suppress(OSError, ValueError):
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def journey_import_resume(gui: Gui, work: Path, journey: Journey) -> None:
    """Spec journey E on the packaged program, the parts the earlier
    journeys do not cover: local OCR of the scanned Latvian 52-item table is
    cancelled while it reads (explained, nothing applied, offered again),
    read to completion, one item is compared with the source, the program is
    closed and started again, and the same PDF opened again brings the saved
    review back: the change, the 52 items and the items still needing
    attention. tests/test_stage368_acceptance.py walks the same flow."""
    import hashlib

    from stage36_fixtures import generator
    from workspace_questionnaires import ocr_language_options

    pdf = generator().create_lv_table_scan_pdf(work)
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    texts = import_resume_texts(pdf.name)
    options = [label for _, label in ocr_language_options("en")]
    latvian = T("imp.ocr_lang.lav")
    stale = data_folder(gui) / "import_sessions" / f"{sha}.json"
    if stale.exists():
        # Left by an earlier run on a real data folder that stopped midway
        # (journey import-scan-lv ends its own review with the draft). A saved
        # review would be read again at once, without the scan offer.
        stale.unlink()
        journey.facts["stale_review_removed"] = str(stale)
    import_document(gui, journey, pdf, shows=T("imp.state.scan"))
    with journey.step("local OCR in Latvian, cancelled with Cancel while it reads"):
        gui.choose(T("imp.ocr_language"), latvian, options=options)
        gui.click(T("imp.ocr_run"), control_type="Button")
        gui.wait_text(T("imp.state.recognizing"), timeout=60, scroll=False)
        started = time.monotonic()
        gui.click(T("imp.cancel_ocr"), control_type="Button", timeout=20)
        key, _ = wait_any(gui, {"cancelled": texts["cancelled"], "read": texts["read"]},
                          timeout=300, scroll=False)
        journey.facts["cancel"] = {"outcome": key,
                                   "seconds_click_to_outcome": round(time.monotonic() - started, 1)}
        expect(key == "cancelled", "the reading finished although Cancel was pressed")
    with journey.step("cancelled: explained, nothing applied, local OCR offered again"):
        element, line = find_text(gui, texts["cancelled"], first="up")
        journey.facts["cancel"]["explanation"] = line
        gui.wait_text(T("imp.state.scan"), scroll=False)
        gui.find(T("imp.ocr_run"), control_type="Button")
        expect(not gui.has_text("candidate items"), "items were applied after the cancel")
        expect(not gui.query(regex=r"^\d\. [^\n]* · ", control_type="Button"),
               "the review wizard opened after the cancel")
        journey.facts["cancel"]["review_saved"] = saved_review(gui, sha) is not None
        expect(not journey.facts["cancel"]["review_saved"], "a review was saved after the cancel")
        shot_at(gui, element, "OCR cancelled")
    with journey.step("read it again to completion: 52 candidates"):
        gui.choose(T("imp.ocr_language"), latvian, options=options)
        gui.click(T("imp.ocr_run"), control_type="Button")
        gui.wait_text(texts["read"], timeout=600, scroll=False)
        gui.wait_text(texts["ocr_used"], timeout=30)
        gui.wait_text("52 candidate items", timeout=30)
    with journey.step(f"one review change: item {RESUME_ITEM} compared with the source"):
        wizard_step(gui, 3)
        before = read_counts(gui)
        row, _ = find_text(gui, regex=rf"(?:^|\n){RESUME_ITEM}\. ")
        row.click_input()
        time.sleep(1.5)
        box = gui.check(T("imp.item_reviewed"))
        after = read_counts(gui, checked=before["checked"] + 1)
        journey.facts.update(counts_before_change=before, counts_after_change=after)
        expect(after["total"] == 52 and after["checked"] == before["checked"] + 1,
               f"counts after the change: {after} (before: {before})")
        expect(before["attention"] - after["attention"] in (0, 1),
               f"items needing attention: {before['attention']} → {after['attention']}")
        record = saved_review(gui, sha)
        expect(record is not None, "the change was not saved on this computer")
        form = (record.get("forms") or {}).get(str(record.get("chosen")), {})
        journey.facts["saved_review"] = {key: record.get(key) for key in
                                         ("file", "ocr_language", "chosen", "step", "selected")}
        journey.facts["saved_review"]["reviewed"] = form.get("reviewed")
        expect(len(form.get("reviewed") or ()) == 1, f"saved review: {record}")
        shot_at(gui, box, "item compared with the source")
    with journey.step("restart the program"):
        gui.stop()
        gui.start()
    with journey.step("after the restart the unfinished review is offered"):
        nav(gui, "nav.questionnaires")
        element, _ = find_text(gui, texts["offer"])
        shot_at(gui, element, "unfinished review offered")
    with journey.step("the same PDF opened again: the saved review comes back"):
        gui.click(T("q.import"), control_type=("Button", "Text"))
        gui.file_dialog(pdf, save=False)
        gui.wait_text(texts["read"], timeout=600, scroll=False)
        element, line = find_text(gui, texts["restored"], first="up")
        journey.facts["restored"] = line
        gui.wait_text(texts["ocr_used"])
        shot_at(gui, element, "review restored")
    with journey.step("the change, the 52 items and the items needing attention are shown"):
        counts = read_counts(gui)
        journey.facts["counts_after_restore"] = counts
        expect(counts == after, f"after the restart: {counts}; before it: {after}")
        # The status line is a live region: Windows may expose it as one text.
        find_text(gui, T("imp.state.review"), first="up")
        if counts["attention"]:
            find_text(gui, T("imp.filter.attention", count=counts["attention"]))
        # The restored review opens at the item last selected, its editor open.
        box, _ = find_text(gui, T("imp.item_reviewed"), exact=True)
        journey.facts["item_checked_after_restore"] = toggle_state(box)
        expect(journey.facts["item_checked_after_restore"] in (1, None),
               f"item {RESUME_ITEM} is no longer marked as compared with the source")
        shot_at(gui, box, "change restored")
    with journey.step("discard the review (the journey can run again on this computer)"):
        # The review is long: the page stands thousands of pixels down at the
        # item, and the mouse wheel over the item list scrolls the list, not
        # the page (round 7, run 43434129037: the status line with "Discard
        # this review" stayed 3,700 px above the window). After a restart the
        # unfinished review is offered at the top of Questionnaires; the offer
        # opens the review from its file on a page not yet scrolled, where the
        # status line and its Discard are found as the restored text was.
        gui.stop()
        gui.start()
        nav(gui, "nav.questionnaires")
        find_text(gui, texts["offer"])
        gui.click(texts["offer"], control_type=("Button", "Text"))
        gui.wait_text(texts["read"], timeout=600, scroll=False)
        find_text(gui, texts["restored"], first="up")
        find_text(gui, T("imp.discard"), exact=True, first="up")
        gui.click(T("imp.discard"), control_type=("Button", "Text"))
        gui.click(T("imp.discard_confirm"), control_type="Button")
        gui.wait_text(texts["discarded"], timeout=20)
        expect(saved_review(gui, sha) is None, "the saved review was kept after Discard")
        expect(not gui.has_text(texts["offer"]), "the discarded review is still offered")


# ------------------------------------------------- negative paths
# Message boxes of the Windows Save dialog: the buttons by name and by id
# (MessageBox and TaskDialog ids), so that any Windows language is answered.
DIALOG_BUTTONS = {"yes": (("Yes",), ("6", "CommandButton_6")),
                  "no": (("No",), ("7", "CommandButton_7")),
                  "ok": (("OK",), ("1", "CommandButton_1")),
                  "cancel": (("Cancel",), ("2", "CommandButton_2"))}
# Every outcome of a save (workspace_files): a refusal names why.
SAVE_REFUSALS = ("save.folder_read_only", "save.file_locked", "save.blocked", "save.not_written",
                 "save.failed_reason", "save.dialog_failed")


def save_outcomes(target: Path) -> dict:
    """What the program can say after a save to ``target``, in priority
    order: "saved" (naming the file), each refusal, "cancelled"."""
    stem = target.name.split(".")[0]
    found = {"saved": re.compile(re.escape(T("save.saved", path="")) + r".*" + re.escape(stem))}
    found.update({key.split(".", 1)[1]: template_pattern(key) for key in SAVE_REFUSALS})
    found["cancelled"] = re.compile(re.escape(T("save.cancelled")))
    return found


def current_user() -> str:
    """This user for icacls: ``*<SID>`` (any Windows language), else the name."""
    import csv

    with contextlib.suppress(Exception):
        out = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                             text=True, timeout=30).stdout.strip()
        sid = next(csv.reader([out]))[1]
        if sid.startswith("S-1-"):
            return "*" + sid
    return os.environ.get("USERNAME", "")


@contextlib.contextmanager
def read_only_folder(folder: Path):
    """``folder`` made read-only for this user: the read-only attribute and
    an access-control entry that denies writing (inherited by its files);
    undone afterwards. Yields facts, including whether the driver itself is
    refused (else the folder is not read-only on this computer)."""
    folder.mkdir(parents=True, exist_ok=True)
    who = current_user()
    attrib = subprocess.run(["attrib", "+R", str(folder)], capture_output=True, text=True)
    # Creating files and writing data, attributes and extended attributes are
    # denied; reading and listing stay allowed (the plain W right would also
    # deny SYNCHRONIZE and READ_CONTROL, and the folder could not be opened).
    deny = subprocess.run(["icacls", str(folder), "/deny", f"{who}:(OI)(CI)(WD,AD,WEA,WA)"],
                          capture_output=True, text=True)
    facts = {"folder": str(folder), "user": who, "attrib_rc": attrib.returncode,
             "icacls_rc": deny.returncode,
             "icacls": " ".join((deny.stdout + deny.stderr).split())[-200:]}
    probe = folder / "driver-probe.txt"
    try:
        probe.write_bytes(b"x")
        facts["driver_refused"] = False
        with contextlib.suppress(OSError):
            probe.unlink()
    except PermissionError:
        facts["driver_refused"] = True
    try:
        yield facts
    finally:
        subprocess.run(["icacls", str(folder), "/remove:d", who], capture_output=True)
        subprocess.run(["attrib", "-R", str(folder)], capture_output=True)


@contextlib.contextmanager
def read_only_file(path: Path, text: str):
    """``path`` with ``text``, read-only (its attribute); writable again afterwards."""
    import stat

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, stat.S_IREAD)
    facts = {"file": str(path)}
    try:
        with open(path, "ab"):
            pass
        facts["driver_refused"] = False
    except PermissionError:
        facts["driver_refused"] = True
    try:
        yield facts
    finally:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def _has_name_box(window) -> bool:
    """The Save dialog itself (it has a File name box), not a message box over it."""
    with contextlib.suppress(Exception):
        return bool(window.descendants(control_type="Edit"))
    return False


def _is_message_box(window) -> bool:
    """A message box: no File name box, and Yes, No or OK to answer it."""
    if _has_name_box(window):
        return False
    with contextlib.suppress(Exception):
        for button in window.descendants(control_type="Button"):
            info = button.element_info
            for answer in ("yes", "no", "ok"):
                names, ids = DIALOG_BUTTONS[answer]
                if (info.name or "").replace("&", "") in names or (info.automation_id or "") in ids:
                    return True
    return False


def save_dialog_windows(gui: Gui) -> tuple[list, list]:
    """(Save dialogs, message boxes) of the program now. UI Automation lists
    a window owned by another under its owner (Gui.dialogs), so a message
    box of the Save dialog may be one of that dialog's children."""
    dialogs, boxes = [], []
    for window in gui.dialogs():
        if not _has_name_box(window):
            if _is_message_box(window):
                boxes.append(window)
            continue
        dialogs.append(window)
        with contextlib.suppress(Exception):
            boxes += [child for child in window.children()
                      if child.element_info.class_name == "#32770" and _is_message_box(child)]
    return dialogs, boxes


def _dialog_text(window) -> str:
    parts = []
    with contextlib.suppress(Exception):
        parts.append(window.window_text())
    with contextlib.suppress(Exception):
        parts += [e.element_info.name for e in window.descendants(control_type="Text")
                  if (e.element_info.name or "").strip()]
    return " | ".join(part for part in parts if part)


def _press(window, *answers: str) -> str:
    """Press the first of ``answers`` (DIALOG_BUTTONS keys) the window offers."""
    from pywinauto import keyboard

    buttons = []
    with contextlib.suppress(Exception):
        buttons = window.descendants(control_type="Button")
    for answer in answers:
        names, ids = DIALOG_BUTTONS[answer]
        for button in buttons:
            info = button.element_info
            if (info.name or "").replace("&", "") in names or (info.automation_id or "") in ids:
                button.click_input()
                time.sleep(0.8)
                return answer
    keyboard.send_keys("{ESC}")
    time.sleep(0.8)
    return "escape"


def refused_save(gui: Gui, button: str, target: Path) -> dict:
    """Press ``button`` and save to ``target`` in the Windows Save dialog
    where the save cannot succeed. Unlike Gui.file_dialog, the dialog's own
    questions are answered so that the program gets the path wherever
    Windows lets it: Yes to replacing an existing file, otherwise No (never
    "save somewhere else instead"). When Windows itself refuses the location
    and the dialog stays open, it is cancelled. Returns what happened."""
    from pywinauto import keyboard

    gui.click(button, control_type=("Button", "Text"))
    deadline, dialog = time.monotonic() + 30, None
    while time.monotonic() < deadline and dialog is None:
        dialog = next((w for w in gui.dialogs() if _has_name_box(w)), None)
        time.sleep(0.5)
    expect(dialog is not None, "the Windows Save dialog did not open")
    time.sleep(1.0)
    edits = []
    with contextlib.suppress(Exception):
        edits = dialog.descendants(control_type="Edit")
    edit = next((e for key in ("1001", "1148") for e in edits
                 if e.element_info.automation_id == key), None)
    if edit is None and edits:
        edit = max(edits, key=lambda e: e.element_info.rectangle.top)
    if edit is not None:
        with contextlib.suppress(Exception):
            edit.click_input()
    else:
        keyboard.send_keys("%n")
    time.sleep(0.3)
    keyboard.send_keys("^a{BACKSPACE}")
    keyboard.send_keys(escape_keys(str(target)), with_spaces=True, pause=0.01)
    time.sleep(0.4)
    keyboard.send_keys("{ENTER}")
    facts = {"typed": str(target), "dialog_messages": [], "answers": [],
             "cancelled_by_driver": False}
    answered, quiet = set(), time.monotonic()
    end = time.monotonic() + 40
    while time.monotonic() < end:
        windows, boxes = save_dialog_windows(gui)
        if not windows and not boxes:
            break
        for box in boxes:
            handle = getattr(box.element_info, "handle", None) or id(box)
            if handle in answered:
                continue
            answered.add(handle)
            text = _dialog_text(box)
            gui.shot("save dialog message")
            replace = re.search(r"replace|already exists", text, re.IGNORECASE)
            facts["dialog_messages"].append(text)
            facts["answers"].append(_press(box, *(("yes",) if replace else ()), "no", "ok",
                                           "cancel"))
            quiet = time.monotonic()
        if not boxes and windows and time.monotonic() - quiet > 5:
            # Only the Save dialog is open: Windows refused the location (or
            # went into a folder). Cancel it; nothing may be saved elsewhere.
            gui.shot("save dialog still open")
            for window in windows:
                facts["answers"].append(_press(window, "cancel"))
            facts["cancelled_by_driver"] = True
            quiet = time.monotonic()
        time.sleep(0.5)
    if any(save_dialog_windows(gui)):
        gui.shot("save dialog stayed open")
        raise StepFailure("the Windows Save dialog stayed open")
    return facts


def program_outcome(gui: Gui, target: Path) -> tuple[str, str]:
    """(outcome, message) the program shows after a save to ``target``."""
    time.sleep(3)        # the outcome replaces any earlier one on screen
    return wait_any(gui, save_outcomes(target), timeout=40)


def check_refused(journey: Journey, name: str, attempt: dict, outcome: str, message: str,
                  *, unchanged: bool) -> None:
    """A save that could not succeed was not claimed as saved, nothing was
    written, and whoever refused it said why: the program (when it got the
    path) or Windows' Save dialog (the program then says nothing was saved)."""
    attempt.update(outcome=outcome, message=message)
    journey.facts[name] = attempt
    expect(outcome != "saved", f"the program claims a save that cannot have succeeded: {message}")
    expect(unchanged, "a file was written or changed where the save had to fail")
    if attempt["cancelled_by_driver"]:
        attempt["refused_by"] = "the Windows Save dialog"
        expect(outcome == "cancelled", f"after Windows refused the location: {message}")
        expect(attempt["dialog_messages"], "the Save dialog stayed open without a message")
    else:
        attempt["refused_by"] = "the program"
        expect(outcome in ("folder_read_only", "file_locked", "blocked"),
               f"the program did not say why it could not save: {message}")


def assistant_states() -> dict:
    """What the assistant section can show, in priority order: a Send
    button (a provider is connected on this computer) or why it is off."""
    return {"ready": template_pattern("assistant.send"),
            "no_key": T("assistant.off.no_key"),
            "no_model": template_pattern("assistant.off.no_model"),
            "no_store": T("assistant.off.no_store")}


def ai_traffic(gui: Gui, title: str) -> dict:
    """What the program recorded of AI requests: the project's audit log (a
    request that may have reached a provider is always logged), today's
    token count and the local log of requests without a project."""
    import ai_assist
    import ai_providers

    usage = {}
    with contextlib.suppress(OSError, ValueError):
        usage = json.loads(ai_providers.usage_path(data_folder(gui)).read_text(encoding="utf-8"))
    return {"logged_requests": len(project_query(
                gui, title, "SELECT id FROM events WHERE kind = 'ai_request'")),
            "tokens_today": int(usage.get("tokens", 0) or 0),
            "local_log": ai_assist.local_log_path(data_folder(gui)).exists()}


def permission(gui: Gui, title: str, source: str, allowed: int, timeout: float = 15) -> list:
    """The stored decision for ``source``, once it is ``allowed`` (or the timeout)."""
    deadline = time.monotonic() + timeout
    while True:
        rows = project_query(gui, title, "SELECT allowed FROM ai_permissions WHERE source = ?",
                             (source,))
        if [row[0] for row in rows] == [allowed] or time.monotonic() > deadline:
            return [row[0] for row in rows]
        time.sleep(0.5)


def journey_negative_paths(gui: Gui, work: Path, journey: Journey) -> None:
    """Negative paths a researcher can meet, as far as the packaged program
    shows them: (a) saving a result into a folder made read-only (attribute
    and ACL) and over a read-only file, each refused in words and never
    claimed as saved; (b) the AI assistant on a result without a provider:
    it says why and offers nothing to send, and nothing is sent; (c) an AI
    permission allowed and revoked for the project. A request refused after
    the revocation needs a connected provider (a real key and a model): it
    is recorded as not reachable, never attempted. No key is used anywhere.
    tests/test_stage368_acceptance.py walks the same flow."""
    import workspace_ai
    from stage36_fixtures import generator

    create_project(gui, journey, NEGATIVE_PROJECT)
    open_data(gui, journey, generator().create_csv(work))
    accept_levels(gui, journey)
    with journey.step("a result to save: describe UCLA"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        click_chip(gui, T("goal.describe"))
        gui.choose(T("role.variable"), option_label("UCLA", "scale"), options=stage36_options())
        gui.click(regex="^" + re.escape(T("rec.run", method="")), control_type="Button")
        gui.wait_text("Descriptive: UCLA", timeout=120)
        find_text(gui, T("results.save_txt"), exact=True, timeout=120)
    locked = work / "read-only-folder"
    with journey.step("(a) save TXT into a folder made read-only: refused, not claimed"):
        target = locked / "negative_result.txt"
        with read_only_folder(locked) as lock:
            expect(lock["driver_refused"], f"the folder could not be made read-only: {lock}")
            attempt = refused_save(gui, T("results.save_txt"), target)
            outcome, message = program_outcome(gui, target)
            attempt.update(lock)
            check_refused(journey, "read_only_folder", attempt, outcome, message,
                          unchanged=not target.exists())
        element, _ = find_text(gui, message)
        shot_at(gui, element, "read-only folder refused")
    with journey.step("(a) save TXT over a read-only file: refused, the file unchanged"):
        existing = work / "read-only-file" / "negative_report.txt"
        original = "Fictional placeholder: this file must stay as it is.\n"
        # Typed without its extension: the dialog accepts the new name and the
        # program adds ".txt" (workspace_files.with_extension), which is the
        # read-only file; the program itself must then refuse.
        typed = existing.with_name("negative_report")
        with read_only_file(existing, original) as lock:
            expect(lock["driver_refused"], f"the file could not be made read-only: {lock}")
            find_text(gui, T("results.save_txt"), exact=True, timeout=60)
            attempt = refused_save(gui, T("results.save_txt"), typed)
            outcome, message = program_outcome(gui, existing)
            attempt.update(lock, placeholder_left=typed.exists())
            check_refused(journey, "read_only_file", attempt, outcome, message,
                          unchanged=existing.read_text(encoding="utf-8") == original)
        element, _ = find_text(gui, message)
        shot_at(gui, element, "read-only file refused")
    before = ai_traffic(gui, NEGATIVE_PROJECT)
    journey.facts["ai_traffic_before"] = before
    with journey.step("(b) the AI assistant without a provider: why, and nothing to send"):
        header, _ = find_text(gui, regex="^" + re.escape(T("assistant.title")), first="up")
        header.click_input()
        try:
            state, text = wait_any(gui, assistant_states(), timeout=10)
        except StepFailure:
            print("  [assistant] the click did not open the section; opening it through "
                  "UI Automation", flush=True)
            try:
                header.expand()
            except Exception:
                Gui.activate(header)
            state, text = wait_any(gui, assistant_states(), timeout=20)
        journey.facts["assistant"] = {"state": state, "text": text}
        if state == "ready":
            journey.facts["assistant"]["note"] = (
                "a provider is connected on this computer, so (b) and (c) do not apply; "
                "nothing was sent")
        else:
            element, _ = find_text(gui, T("assistant.off_title"))
            sends = gui.query(regex="^" + re.escape(T("assistant.send", provider="\0",
                                                      model="").split("\0")[0]),
                              control_type="Button")
            expect(not sends, f"a Send button is offered without a provider: {len(sends)}")
            shot_at(gui, element, "assistant not connected")
            gui.click(T("assistant.open_settings"), control_type=("Button", "Text"))
            # Settings → AI providers, below the appearance, profile and AI
            # assistance cards (several thousand pixels down).
            key_state, key_text = wait_any(gui, {
                "no_key": workspace_ai.t("en", "no_key", provider="OpenAI"),
                "no_store": workspace_ai.t("en", "no_store"),
                "stored": workspace_ai.t("en", "stored", provider="OpenAI")},
                timeout=120, step=5)
            journey.facts["assistant"]["settings"] = {"key": key_state, "text": key_text}
            element, _ = find_text(gui, key_text)
            shot_at(gui, element, "no key stored")
            element, _ = find_text(gui, T("ai.unavailable"), first="up", timeout=120)
            shot_at(gui, element, "AI assistance not connected")
    with journey.step("(c) an AI permission allowed, then revoked for the project"):
        if journey.facts["assistant"]["state"] == "ready":
            journey.facts["permission"] = "not attempted: a provider is connected on this computer"
        else:
            nav(gui, "nav.settings")
            find_text(gui, T("ai.sources", title=NEGATIVE_PROJECT), timeout=120)
            allowed = gui.check(T("ai.allow"), True, index=0)       # the first: Project overview
            stored = permission(gui, NEGATIVE_PROJECT, "overview", 1)
            shot_at(gui, allowed, "permission allowed")
            gui.check(T("ai.allow"), False, index=0)
            revoked = permission(gui, NEGATIVE_PROJECT, "overview", 0)
            changes = [json.loads(detail) for (detail,) in project_query(
                gui, NEGATIVE_PROJECT, "SELECT detail FROM events WHERE kind = 'ai_permission' "
                                       "ORDER BY id")]
            journey.facts["permission"] = {"overview_allowed": stored, "overview_revoked": revoked,
                                           "logged": changes[-2:]}
            expect(stored == [1] and revoked == [0], f"overview stored {stored}, then {revoked}")
            expect(changes[-2:] == [{"source": "overview", "allowed": True},
                                    {"source": "overview", "allowed": False}],
                   f"the permission changes logged in the project: {changes[-2:]}")
        journey.facts["request_after_revocation"] = (
            "not reachable without a connected provider: the assistant prepares and sends a "
            "request only with a provider, a key in the credential store and a model, and any "
            "Send then contacts that provider; no key is used here. The refusal of a revoked "
            "source is covered by tests/test_workspace_assistant.py (RefusalTests, a fake "
            "credential store and a local mock provider)")
    with journey.step("nothing was sent to an AI provider"):
        after = ai_traffic(gui, NEGATIVE_PROJECT)
        journey.facts["ai_traffic_after"] = after
        expect(after == before, f"AI traffic recorded: before {before}, after {after}")


# ============================ Stage 36.8 review findings K1 and K2 (#62)
# tests/test_stage368_review_journeys.py walks both flows in the workspace harness.
CONFIRMATIONS_PROJECT = "Fictional confirmations study"
REPORT_PROJECT = "Fictional report composition"
SECOND_REPORT_PROJECT = "Fictional second study"
DESCRIPTIVE_UCLA = "Descriptive: UCLA"                     # the describe result's title
REPORT_TITLE = "Fictional loneliness study"
REPORT_NOTE = "Fictional reading: loneliness goes with more cautious action."
LEFT_OUT = "limitations"                                  # the section left out (research_report)
REPORT_LANGUAGES = ["English", "Latviešu", "Русский"]       # the report language dropdown


def run_button() -> str:
    """The guided Run button ("Run <method>"), not "Run again" beside a task's result."""
    run, again = T("rec.run", method=""), T("task.rerun")
    return "^" + re.escape(run) + "(?!" + re.escape(again[len(run):]) + "$)"


def group_confirmations(options: dict | None = None) -> dict[str, str]:
    """``{"design": label, "data": label}``: what the group comparison of
    several outcomes asks the researcher to confirm (engine wording), for
    these options (a two-group test: ``{"two_group_method": ...}``)."""
    from workspace_methods import METHODS, default_options, required_confirmations
    from workspace_text import label as engine_label

    spec = METHODS["batch_groups"]
    found = {}
    for confirmation in required_confirmations(spec, {**default_options(spec), **(options or {})}):
        found.setdefault(confirmation.kind, engine_label("en", confirmation.label))
    return found


def group_runs(gui: Gui, title: str) -> list[list[str]]:
    """The outcomes of every group-comparison result of the project, in the
    order they were calculated (its database, read-only)."""
    rows = project_query(gui, title, "SELECT roles FROM runs WHERE method = 'batch_groups' "
                                     "ORDER BY rowid")
    return [list(json.loads(roles).get("outcomes") or ()) for (roles,) in rows]


def project_runs(gui: Gui, title: str) -> int:
    """How many results (runs of any method) the project holds."""
    return project_query(gui, title, "SELECT COUNT(*) FROM runs")[0][0]


def runs_after(gui: Gui, title: str, before: int, wait: float = 10) -> int:
    """How many results the project holds once ``wait`` seconds have passed
    (earlier if one more than ``before`` appears)."""
    deadline = time.monotonic() + wait
    while True:
        count = project_runs(gui, title)
        if count > before or time.monotonic() > deadline:
            return count
        time.sleep(1)


def confirmation_states(gui: Gui, labels) -> dict[str, int | None]:
    """The toggle state of each confirmation box, read through UI Automation."""
    return {label: toggle_state(gui.find(label, control_type="CheckBox")) for label in labels}


def journey_confirmations(gui: Gui, work: Path, journey: Journey) -> None:
    """Review finding K1 on the packaged program (spec B: change the
    variables, then run again). A design confirmation (independent groups)
    holds while its variables are the same; a data confirmation (outcome
    distributions, outliers, group sizes) holds for one table, one set of
    variables and one method. After a batch run the program keeps the
    researcher in the task with its variables step above the result
    ("Change variables"), so the outcomes are changed after the run.
    UI Automation reports every button as enabled (docs/STAGE368_A11Y_AND_
    LOCALE.md §1): instead of Run's state, the project's database shows
    that Run, Ctrl+Enter and Run again add no result before the data
    confirmation is given again. tests/test_stage368_review_journeys.py
    walks the same flow."""
    from stage36_fixtures import SCALES, generator

    labels = group_confirmations()
    design, data = labels["design"], labels["data"]
    dropped, title = SCALES[0], CONFIRMATIONS_PROJECT
    create_project(gui, journey, title)
    open_data(gui, journey, generator().create_csv(work))
    accept_levels(gui, journey)
    with journey.step("eight scales by UCLA_Level, both confirmations, Run"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        click_chip(gui, T("goal.compare"))
        gui.choose(T("role.group"), option_label("UCLA_Level", "ordinal"),
                   options=stage36_options())
        gui.click(T("pick.all_scale", count=10), control_type="Button")
        gui.check(option_label("Age", "scale"), False)
        gui.check(option_label("UCLA", "scale"), False)
        gui.wait_text("fewer than five values", timeout=20)
        gui.check(design)
        gui.check(data)
        gui.click(regex=run_button(), control_type="Button")
        gui.wait_text(T("task.title_compare", group="UCLA_Level", count=8), timeout=180)
        runs = group_runs(gui, title)
        journey.facts["first_run_outcomes"] = runs[-1] if runs else None
        expect(len(runs) == 1 and sorted(runs[0]) == sorted(SCALES),
               f"group comparisons in the project: {runs}")
    with journey.step(f"after the run, {dropped} left out of the outcomes"):
        gui.click(T("task.change_variables"), control_type=("Button", "Text"))
        gui.check(option_label(dropped, "scale"), False)
    with journey.step("the design confirmation holds, the data confirmation is cleared"):
        states = confirmation_states(gui, (design, data))
        journey.facts["after_outcome_change"] = states
        expect(states[design] == 1, f"{design!r} after other outcomes: {states[design]}")
        expect(states[data] == 0, f"{data!r} after other outcomes: {states[data]}")
        element, _ = find_text(gui, T("design.reconfirm"))
        shot_at(gui, element, "data confirmation to give again")
    with journey.step("Run, Ctrl+Enter and Run again add no result before re-confirming"):
        before = project_runs(gui, title)
        attempts = {"runs_before": before}
        gui.click(regex=run_button(), control_type="Button")
        attempts["after_run"] = runs_after(gui, title, before)
        gui.keys("^{ENTER}")
        attempts["after_ctrl_enter"] = runs_after(gui, title, before)
        # Said in the status line after Ctrl+Enter; also Run's tooltip, so
        # only a fact, the database count above is the evidence.
        attempts["confirm_first_text_shown"] = gui.has_text(T("disabled.confirm_first"))
        gui.click(T("task.rerun"), control_type="Button")
        attempts["after_run_again"] = runs_after(gui, title, before)
        journey.facts["attempts_before_reconfirming"] = attempts
        expect(all(attempts[key] == before for key in ("after_run", "after_ctrl_enter",
                                                       "after_run_again")),
               f"a result was added before the data confirmation was given again: {attempts}")
    with journey.step(f"the data confirmation given again: a result for {len(SCALES) - 1} "
                      f"outcomes"):
        gui.check(data)
        gui.click(regex=run_button(), control_type="Button")
        expect(runs_after(gui, title, before, wait=180) == before + 1, "no second result")
        runs = group_runs(gui, title)
        journey.facts["second_run_outcomes"] = runs[-1]
        expect(sorted(runs[-1]) == sorted(SCALES[1:]),
               f"outcomes of the second result: {runs[-1]}")
        element, _ = find_text(gui, T("task.versions", count=2), timeout=60)
        shot_at(gui, element, "second result of the task")
    with journey.step("another grouping variable, Sex (two groups): both cleared"):
        gui.choose(T("role.group"), option_label("Sex", "nominal"), options=stage36_options())
        find_text(gui, design, exact=True)
        asked = [name for name in dict.fromkeys(
            e.element_info.name or "" for e in gui.query(control_type="CheckBox"))
            if name and " · " not in name]              # not a variable's box ("Age · …")
        states = confirmation_states(gui, asked)
        expected = list(group_confirmations({"two_group_method": "welch"}).values())
        journey.facts["two_group_test"] = {"asked": asked, "states": states,
                                           "engine_labels": expected}
        expect(sorted(asked) == sorted(expected), f"the two-group test asks for {asked}")
        expect(all(state == 0 for state in states.values()),
               f"confirmations given for UCLA_Level are still ticked: {states}")
        element, _ = find_text(gui, T("design.reconfirm"))
        shot_at(gui, element, "both confirmations to give again")


def press_in_row(gui: Gui, row_text: str, name: str):
    """Press the control named ``name`` (an icon button, named by its
    tooltip) in the same row as the text ``row_text`` (a report entry)."""
    anchor, _ = find_text(gui, row_text, exact=True)
    box = anchor.element_info.rectangle
    middle = (box.top + box.bottom) // 2
    found = []
    for element in gui.query(name):
        with contextlib.suppress(Exception):
            rect = element.element_info.rectangle
            if rect.left >= box.left and abs((rect.top + rect.bottom) // 2 - middle) <= 45:
                found.append((abs((rect.top + rect.bottom) // 2 - middle), element))
    expect(found, f"no {name!r} in the row of {row_text!r}")
    element = min(found, key=lambda pair: pair[0])[1]
    element.click_input()
    time.sleep(1.0)
    return element


def set_box(gui: Gui, box, value: bool):
    """Tick or clear a checkbox found by pattern (Gui.check needs its exact name)."""
    if toggle_state(box) != int(value):
        rect = box.element_info.rectangle
        box.click_input(coords=(min(20, rect.width() // 2), rect.height() // 2))
        time.sleep(0.8)
    if toggle_state(box) not in (int(value), None):
        with contextlib.suppress(Exception):
            box.toggle()
        time.sleep(0.8)
    expect(toggle_state(box) in (int(value), None), f"the box could not be set to {value}")
    return box


def section_pattern(language: str, key: str = LEFT_OUT) -> str:
    """The Reports page's box of one section, "14. Limitations · …": its
    title is written in the report's language."""
    import research_report as rr

    number = rr.SECTIONS.index(key) + 1
    return rf"^{number}\. {re.escape(rr.text(language, key))} · "


def section_box(gui: Gui, language: str, key: str = LEFT_OUT):
    box, _ = find_text(gui, regex=section_pattern(language, key), timeout=60,
                       control_type="CheckBox")
    return box


def open_interpretation(gui: Gui) -> None:
    """Open a result's Interpretation section (it holds the researcher's
    note), unless it is open already: a click on an open section closes it."""
    header, _ = find_text(gui, regex="^" + re.escape(T("results.interpretation")) + r"(\n|$)")
    for attempt in range(3):
        with contextlib.suppress(StepFailure):
            find_text(gui, T("results.notes"), exact=True, timeout=6, moves=3)
            return
        if attempt == 0:
            header.click_input()
        else:
            try:
                header.expand()
            except Exception:
                Gui.activate(header)
        time.sleep(1.0)
    raise StepFailure("the Interpretation section did not open")


def saved_entries(gui: Gui, title: str, method: str, wait: float = 15) -> dict:
    """The note and reviewed checks the project holds for its ``method``
    result (typed text reaches the program a little after the keys)."""
    deadline = time.monotonic() + wait
    while True:
        rows = project_query(gui, title, "SELECT note, provenance FROM runs WHERE method = ?",
                             (method,))
        found = {"note": rows[0][0], "reviewed": json.loads(rows[0][1]).get("reviewed")} \
            if rows else {}
        if (found.get("note") == REPORT_NOTE and found.get("reviewed")) or \
                time.monotonic() > deadline:
            return found
        time.sleep(1)


def batch_title(csv_path: Path) -> str:
    """The title of the eight-correlation batch result, from the engine."""
    import pandas as pd

    from batch_correlation import correlate_many
    from stage36_fixtures import SCALES

    return correlate_many(pd.read_csv(csv_path), "UCLA", list(SCALES),
                          method="spearman").table().title


def docx_tables(path: Path) -> list[list[list[str]]]:
    """Every table of a Word document as rows of cell texts."""
    from docx import Document

    return [[[cell.text.strip() for cell in row.cells] for row in table.rows]
            for table in Document(str(path)).tables]


def report_order(path: Path, language: str) -> dict[str, list[str]]:
    """The results in the order the research report lists them: its data and
    sample table and its reproducibility appendix (research_report)."""
    from research_report import TEXT as REPORT

    order = {}
    for table in docx_tables(path):
        if table and tuple(table[0]) == tuple(REPORT[language]["data_columns"]):
            order["data_and_sample"] = [row[0] for row in table[1:]]
        if table and tuple(table[0]) == tuple(REPORT[language]["appendix_columns"]):
            order["appendix"] = [row[1] for row in table[1:]]
    return order


def report_checks(batch: str) -> dict[str, str]:
    """The batch result's first assumption check (reviewed) and its second
    (left open), as the Latvian report writes them."""
    from interpretation_i18n import translate_assumption
    from interpretation_wizard import METHOD_PROFILES
    from research_report import TEXT as REPORT

    first, second = METHOD_PROFILES["batch_correlation"].assumptions[:2]
    return {"reviewed": first, "open": second,
            "reviewed_lv": f"{translate_assumption(first, 'lv')} — "
                           f"{REPORT['lv']['assumption_reviewed']}",
            "open_lv": f"{translate_assumption(second, 'lv')} — {REPORT['lv']['assumption_open']}"}


def journey_report_composition(gui: Gui, work: Path, journey: Journey) -> None:
    """Review finding K2 on the packaged program (spec G: compose the report,
    restart, the composition is kept). Two results go into the report and
    their order is changed with the Reports page's own Move up; the batch
    result gets a researcher's note and one assumption check reviewed; the
    report gets a title, one section left out and Latvian. After a restart
    all of it is back, and the Word report has the results in that order,
    the title, no left-out section and the reviewed check marked in
    Latvian. A second project created in the hub shows none of it.
    tests/test_stage368_review_journeys.py walks the same flow."""
    import research_report as rr
    from stage36_fixtures import generator

    csv_path = generator().create_csv(work)
    batch = batch_title(csv_path)
    checks = report_checks(batch)
    journey.facts["engine_titles"] = [batch, DESCRIPTIVE_UCLA]
    create_project(gui, journey, REPORT_PROJECT)
    open_data(gui, journey, csv_path)
    accept_levels(gui, journey)
    with journey.step("eight correlations: a result in the report"):
        run_eight_correlations(gui)
        gui.click(T("results.add_report"), control_type="Button")
        gui.find(T("results.in_report"), control_type="Button", timeout=20)
    with journey.step("a description of UCLA: a second result in the report"):
        gui.click(T("task.new"), control_type="Button")
        click_chip(gui, T("goal.describe"))
        gui.choose(T("role.variable"), option_label("UCLA", "scale"), options=stage36_options())
        gui.click(regex=run_button(), control_type="Button")
        gui.wait_text(DESCRIPTIVE_UCLA, timeout=120)
        gui.click(T("results.add_report"), control_type="Button")
        gui.find(T("results.in_report"), control_type="Button", timeout=20)
    with journey.step("Move up on the Reports page: the description first"):
        nav(gui, "nav.reports")
        find_text(gui, f"1. {batch}", exact=True)
        press_in_row(gui, f"2. {DESCRIPTIVE_UCLA}", T("reports.move_up"))
        element, _ = find_text(gui, f"1. {DESCRIPTIVE_UCLA}", exact=True, timeout=20)
        find_text(gui, f"2. {batch}", exact=True)
        shot_at(gui, element, "report order changed")
    with journey.step("the batch result: one check reviewed and a researcher's note"):
        press_in_row(gui, f"2. {batch}", T("reports.open_result"))
        gui.wait_text(batch, timeout=30)
        box = gui.check(checks["reviewed"])
        open_interpretation(gui)
        gui.type_into(T("results.notes"), REPORT_NOTE)
        saved = saved_entries(gui, REPORT_PROJECT, "batch_correlation")
        journey.facts["saved_note_and_review"] = saved
        expect(saved == {"note": REPORT_NOTE, "reviewed": [checks["reviewed"]]},
               f"saved in the project: {saved}")
        shot_at(gui, box, "check reviewed")
    with journey.step("a study title, the limitations left out, the report in Latvian"):
        nav(gui, "nav.reports")
        gui.type_into(T("reports.study_title"), REPORT_TITLE)
        gui.keys("{TAB}")                  # the title is saved when its field is left
        set_box(gui, section_box(gui, "en"), False)
        gui.choose(T("reports.language"), "Latviešu", options=REPORT_LANGUAGES)
        box = section_box(gui, "lv")       # the sections are named in the report's language
        expect(toggle_state(box) == 0 and T("reports.section_off") in element_text(gui, box),
               f"the section is not left out: {element_text(gui, box)!r}, "
               f"toggle state {toggle_state(box)}")
        settings = [json.loads(detail) for (detail,) in project_query(
            gui, REPORT_PROJECT, "SELECT detail FROM events WHERE kind = 'report_settings' "
                                 "ORDER BY id")]
        journey.facts["saved_report_settings"] = settings[-1] if settings else None
        expect(settings and settings[-1] == {"title": REPORT_TITLE, "sections_off": [LEFT_OUT],
                                             "language": "lv"},
               f"report settings saved in the project: {settings[-1:] or None}")
        shot_at(gui, box, "section left out")
    with journey.step("restart the program and open the project"):
        gui.stop()
        gui.start()
        open_project(gui, REPORT_PROJECT)
    with journey.step("after the restart: the order, title, section and language are kept"):
        nav(gui, "nav.reports")
        element, _ = find_text(gui, f"1. {DESCRIPTIVE_UCLA}", exact=True)
        find_text(gui, f"2. {batch}", exact=True)
        field = gui.find(T("reports.study_title"), control_type="Edit")
        journey.facts["title_after_restart"] = gui.value(field)
        expect(gui.value(field) == REPORT_TITLE, f"the study title: {gui.value(field)!r}")
        box = section_box(gui, "lv")
        journey.facts["section_after_restart"] = {"text": element_text(gui, box),
                                                  "ticked": toggle_state(box)}
        expect(toggle_state(box) == 0 and T("reports.section_off") in element_text(gui, box),
               f"the section after the restart: {journey.facts['section_after_restart']}")
        language, _ = wait_any(gui, {code: re.compile(section_pattern(code, "descriptives"))
                                     for code in ("lv", "en")}, timeout=30)
        journey.facts["report_language_after_restart"] = language
        expect(language == "lv", "the report language came back as English")
        shot_at(gui, element, "report composition after the restart")
    with journey.step("after the restart: the note and the reviewed check are back"):
        press_in_row(gui, f"2. {batch}", T("reports.open_result"))
        gui.wait_text(batch, timeout=30)
        reviewed = toggle_state(gui.find(checks["reviewed"], control_type="CheckBox"))
        still_open = toggle_state(gui.find(checks["open"], control_type="CheckBox"))
        open_interpretation(gui)
        note = gui.value(gui.find(T("results.notes"), control_type="Edit"))
        journey.facts["after_restart"] = {"reviewed": reviewed, "open": still_open, "note": note}
        expect((reviewed, still_open) == (1, 0),
               f"assumption checks after the restart (toggle states): {reviewed}, {still_open}")
        expect(note == REPORT_NOTE, f"the note after the restart: {note!r}")
    with journey.step("the Word report"):
        nav(gui, "nav.reports")
    path = work / "report_composition.docx"
    save_via_dialog(gui, journey, T("reports.export_docx"), path, kind="docx",
                    contains=(REPORT_TITLE, checks["reviewed_lv"], checks["open_lv"],
                              REPORT_NOTE))
    with journey.step("the Word report: the chosen order, nothing left out shown"):
        order = report_order(path, "lv")
        journey.facts["word_report_order"] = order
        expect(order.get("data_and_sample") == [DESCRIPTIVE_UCLA, batch]
               and order.get("appendix") == [DESCRIPTIVE_UCLA, batch],
               f"results in the Word report: {order}")
        from docx import Document

        document = Document(str(path))
        text = "\n".join(p.text for p in document.paragraphs)
        headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
        journey.facts["word_report_headings"] = headings
        left_out = rr.text("lv", LEFT_OUT)
        expect(not any(left_out in heading for heading in headings) and left_out not in text,
               f"the left-out section {left_out!r} is in the report")
    # A second project, created in the hub (Home), with a result of its own.
    create_project(gui, journey, SECOND_REPORT_PROJECT)
    open_data(gui, journey, csv_path)
    accept_levels(gui, journey)
    with journey.step("the second project shows none of these entries"):
        nav(gui, "nav.analyze")
        gui.click(T("analyze.mode.guided"), control_type=("Button", "Text"))
        click_chip(gui, T("goal.describe"))
        gui.choose(T("role.variable"), option_label("UCLA", "scale"), options=stage36_options())
        gui.click(regex=run_button(), control_type="Button")
        gui.wait_text(DESCRIPTIVE_UCLA, timeout=120)
        from interpretation_wizard import METHOD_PROFILES

        described = confirmation_states(gui, METHOD_PROFILES["descriptive"].assumptions)
        open_interpretation(gui)
        note = gui.value(gui.find(T("results.notes"), control_type="Edit"))
        gui.click(T("results.add_report"), control_type="Button")
        gui.find(T("results.in_report"), control_type="Button", timeout=20)
        nav(gui, "nav.reports")
        find_text(gui, f"1. {DESCRIPTIVE_UCLA}", exact=True)
        others = [text for _, text in screen_texts(gui)
                  if text == f"2. {DESCRIPTIVE_UCLA}" or text.startswith(f"2. {batch}")]
        title = gui.value(gui.find(T("reports.study_title"), control_type="Edit"))
        box = section_box(gui, "en")
        second = {"checks_reviewed": described, "note": note, "title": title,
                  "limitations": {"text": element_text(gui, box), "ticked": toggle_state(box)},
                  "other_entries": others}
        journey.facts["second_project"] = second
        expect(all(state == 0 for state in described.values()) and note == "" and title == ""
               and not others, f"the second project shows entries of the first: {second}")
        expect(toggle_state(box) == 1 and T("reports.section_off") not in
               element_text(gui, box), "a section is left out in the second project")
        shot_at(gui, box, "second project report settings")


# Journeys that prepare the machine and start the program themselves.
STARTS_ITSELF = {"legacy-migration", "installed-reopen", "update-a-to-b"}

INSTALLED_JOURNEYS = {
    "legacy-migration": journey_legacy_migration,
    "installed-data": journey_installed_data,
    "installed-reopen": journey_installed_reopen,
    "update-refusals": journey_update_refusals,
    "update-a-to-b": journey_update_a_to_b,
}


JOURNEYS = {
    "stage36-tasks": journey_stage36_tasks,
    "stage36-charts": journey_stage36_charts,
    "stage36-groups": journey_stage36_groups,
    "project-a": journey_project_a,
    "project-b": journey_project_b,
    "import-30": journey_import_30,
    "review-120": journey_review_120,
    "responses": journey_responses,
    "blocked-design": journey_blocked_design,
    # Stage 36.5 (spec §14 journeys 5 and 6), after the journeys above so
    # that their order and the state they meet stay as they were.
    "import-cope-docx": journey_import_cope_docx,
    "import-scan-lv": journey_import_scan_lv,
    # Stage 36.7: spec §14 journeys 8 and 10 (after stage36-groups, whose
    # project stage36-report continues).
    "stage36-report": journey_stage36_report,
    "import-damaged": journey_import_damaged,
    # Stage 36.8 (#62, Part 8: installed-Windows user acceptance): spec
    # journeys F and E and the negative paths, after the 13 journeys above,
    # which run unchanged and in their order.
    "psychometrics": journey_psychometrics,
    "import-resume": journey_import_resume,
    "negative-paths": journey_negative_paths,
    # Stage 36.8 review findings K1 and K2 (#62), after the journeys above.
    "confirmations": journey_confirmations,
    "report-composition": journey_report_composition,
}


def probe(gui: Gui) -> None:
    """Dump what UI Automation exposes on the main screens (diagnosis)."""
    gui.dump("home")
    for key in ("nav.data", "nav.questionnaires", "nav.analyze", "nav.home"):
        with contextlib.suppress(Exception):
            gui.click(T(key), control_type=("Button", "Text"), timeout=8)
            gui.dump(key)
            gui.shot(key)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--only", nargs="*", choices=sorted(JOURNEYS) + sorted(INSTALLED_JOURNEYS))
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--real-data", action="store_true",
                        help="use the real per-user data folder (installed application)")
    args = parser.parse_args(argv)
    journeys = {**JOURNEYS, **INSTALLED_JOURNEYS}
    if os.name != "nt":
        print("The packaged GUI journeys run on Windows only.")
        return 2
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # resolve(): the long form of the folder. TEMP on the runner is an 8.3
    # short path (RUNNER~1) while the Save dialog returns the long one.
    work = Path(tempfile.mkdtemp(prefix="sra-e2e-files-")).resolve()
    data = Path(tempfile.mkdtemp(prefix="sra-e2e-data-"))
    preferences = Path.home() / ".statistical_research_assistant" / "preferences.json"
    with contextlib.suppress(OSError):
        preferences.unlink()        # default (English) preferences
    gui = Gui(args.exe.resolve(), data, out, real_data=args.real_data)
    report = {"exe": str(args.exe), "journeys": []}
    started = time.monotonic()
    try:
        selected = args.only or list(JOURNEYS)
        if selected[0] not in STARTS_ITSELF:
            gui.start()
        if args.probe:
            probe(gui)
        for name in selected:
            journey = Journey(name, gui)
            outcome = {"journey": name, "ok": False}
            with gui.record(name):
                try:
                    if name not in STARTS_ITSELF and not gui.running():
                        gui.start()
                    journeys[name](gui, work, journey)
                    outcome["ok"] = True
                except Exception as error:
                    outcome["error"] = f"{type(error).__name__}: {error}"
                    with contextlib.suppress(Exception):
                        gui.print_app_log()
                    with contextlib.suppress(Exception):
                        gui.recover()
            outcome.update(steps=journey.steps, facts=journey.facts)
            report["journeys"].append(outcome)
            print(("ok   " if outcome["ok"] else "FAIL ") + name,
                  outcome.get("error", ""), flush=True)
            for entry in journey.steps:
                print(f"     {'ok ' if entry['ok'] else 'FAIL'} {entry['step']} "
                      f"({entry['seconds']} s){'  ' + entry['error'] if not entry['ok'] else ''}",
                      flush=True)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print("FAIL startup:", report["error"], flush=True)
        with contextlib.suppress(Exception):
            gui.dump("startup-failure")
    finally:
        gui.stop()
    report["seconds"] = round(time.monotonic() - started, 1)
    report["ok"] = bool(report["journeys"]) and all(j["ok"] for j in report["journeys"]) \
        and "error" not in report
    # Evidence for the window guard (window_guard.py): each time the program
    # had to show its own still-hidden window, its startup log says so.
    report["window_guard"] = window_guard_events(out / "app-logs" / "startup.log")
    print(f"window guard: {len(report['window_guard'])} intervention(s)"
          + "".join(f"\n  {event}" for event in report["window_guard"]), flush=True)
    (out / "gui-e2e-result.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
    for name in ("ancova_report.txt", "combined_report.txt", "pilot_responses.csv",
                 "psychometrics_report.txt"):
        with contextlib.suppress(OSError):
            shutil.copy(work / name, out / name)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
