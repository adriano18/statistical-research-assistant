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


# ====================================================================== app
class Gui:
    """One running instance of the packaged application."""

    def __init__(self, exe: Path, data_dir: Path, out: Path):
        self.exe, self.data_dir, self.out = exe, data_dir, out
        self.process: subprocess.Popen | None = None
        self.win = None
        self.handle = None
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
            "SRA_DATA_DIR": str(self.data_dir),
            "SRA_LOG_DIR": str(self.out / "app-logs"),
        })
        return env

    def start(self, timeout: float = 300) -> None:
        from pywinauto import Desktop
        from pywinauto.application import Application

        self.process = subprocess.Popen([str(self.exe)], cwd=str(self.exe.parent),
                                        env=self.environment())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise StepFailure(f"the application exited during startup ({self.process.returncode})")
            for window in Desktop(backend="uia").windows():
                try:
                    if window.process_id() == self.process.pid or WINDOW_TITLE in window.window_text():
                        rect = window.rectangle()
                        if rect.width() > 300 and rect.height() > 200:
                            self.handle = window.handle
                            break
                except Exception:
                    continue
            if self.handle:
                break
            time.sleep(1)
        if not self.handle:
            raise StepFailure("the application window never appeared")
        app = Application(backend="uia").connect(handle=self.handle)
        self.win = app.window(handle=self.handle)
        with contextlib.suppress(Exception):
            self.win.maximize()
        with contextlib.suppress(Exception):
            self.win.set_focus()
        # The workspace is ready when its Home page offers to create a project.
        self.find(T("project.create"), timeout=max(30, deadline - time.monotonic()),
                  scroll=False, visible=False)

    def stop(self, *, graceful: bool = True) -> None:
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
        self.process, self.win, self.handle = None, None, None

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
                    self.frames[0].save(target, save_all=True, append_images=self.frames[1:],
                                        duration=400, loop=0, optimize=True)
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
            lines.append(f"    {info.control_type:<12} | {(info.name or '')[:70]!r} | "
                         f"{info.automation_id or ''} | {info.class_name or ''} | {where}")
        return "\n".join(lines)

    def log_screen(self, title: str) -> None:
        """What is on screen now, printed into the CI log (artifacts may not be
        reachable when diagnosing a failure)."""
        try:
            visible = [e for e in self.elements() if (e.element_info.name or "").strip()
                       and self.on_screen(e)]
            print(f"  [screen: {title}] {len(visible)} named elements on screen", flush=True)
            print(self.describe(visible, 90), flush=True)
        except Exception as error:
            print(f"  [screen: {title}] could not list elements: {error!r}", flush=True)

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

    def query(self, name=None, *, regex=None, control_type=None):
        found = [e for e in self.elements() if self._matches(e, name, regex, control_type)]
        return found

    def texts(self) -> list[str]:
        return [e.element_info.name or "" for e in self.elements()]

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

    def scroll_into_view(self, element, attempts: int = 30):
        for _ in range(attempts):
            if self.on_screen(element):
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
                if not visible or self.on_screen(element):
                    return element
                if scroll:
                    self.scroll_into_view(element)
                    if self.on_screen(element):
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

    def value(self, element) -> str:
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
        box = self.find(label, control_type="CheckBox", index=index)
        state = None
        with contextlib.suppress(Exception):
            state = box.get_toggle_state()
        if state is None or bool(state) != value:
            box.click_input()
            time.sleep(0.8)
        return box

    def choose(self, label: str, option: str, *, index: int = 0):
        """Pick ``option`` in the dropdown named ``label`` (mouse only)."""
        field = None
        for kinds in (("ComboBox",), ("Edit",), ("Button", "Group", "Custom", "Pane", "Text")):
            found = self.query(label, control_type=kinds)
            if len(found) > index:
                field = found[index]
                break
        if field is None:
            field = self.find(label, index=index)
        self.scroll_into_view(field)
        field.click_input()
        time.sleep(0.9)
        item = self.find(option, control_type=("MenuItem", "ListItem", "Button", "Text",
                                               "Custom", "Group"), scroll=False, timeout=8)
        item.click_input()
        time.sleep(0.9)

    def keys(self, keys: str):
        from pywinauto import keyboard

        keyboard.send_keys(keys)
        time.sleep(0.5)

    def status(self) -> str:
        """The status line (a live region) as Windows exposes it."""
        texts = self.texts()
        return " | ".join(t for t in texts if t)[-4000:]

    def wait_text(self, fragment: str, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.has_text(fragment):
                return
            time.sleep(0.5)
        self.dump(f"no-text-{fragment}")
        self.shot(f"no-text-{fragment}")
        raise StepFailure(f"text never appeared: {fragment!r}")

    # --------------------------------------------------------- file dialogs
    def dialogs(self) -> list:
        """Visible standard Windows dialogs (class #32770) of any process."""
        from pywinauto import Desktop

        found = []
        for window in Desktop(backend="uia").windows():
            with contextlib.suppress(Exception):
                if window.class_name() == "#32770" and window.is_visible():
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
            # The File name box is the lowest edit field (the search box is on top).
            edit = max(edits, key=lambda e: e.element_info.rectangle.top)
        print(f"  [file dialog] {dialog.window_text()!r}: {len(edits)} edit field(s); using "
              f"{(edit.element_info.automation_id if edit else 'keyboard focus')!r}", flush=True)
        if edit is None:
            print(self.describe(dialog.descendants(), 80), flush=True)
        with contextlib.suppress(Exception):
            dialog.set_focus()
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

    def recover(self) -> None:
        """After a failed journey: close dialogs and return to Home."""
        from pywinauto import keyboard

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


def option_label(name: str, level: str) -> str:
    return f"{name} · {T('level.' + level)}"


def create_project(gui: Gui, journey: Journey, title: str) -> None:
    with journey.step(f"create project {title}"):
        gui.click(T("nav.home"), control_type=("Button", "Text"))
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
        gui.click(T("nav.data"), control_type=("Button", "Text"))
        gui.check(T("data.accept_confirm"))
        gui.click(T("data.accept_suggestions"), control_type="Button")
        gui.wait_text(T("next.analyze"))


def save_via_dialog(gui: Gui, journey: Journey, button: str, target: Path, *, kind: str,
                    contains=()) -> dict:
    with journey.step(f"save {target.name} with '{button}'"):
        gui.click(button, control_type=("Button", "Text"))
        gui.file_dialog(target, save=True)
        gui.wait_text(str(target) if kind != "sra" else target.name, timeout=40)
        facts = verify_saved(target, kind=kind, contains=contains)
        journey.facts[target.name] = facts
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
        gui.click(T("nav.analyze"), control_type=("Button", "Text"))
        gui.click(T("analyze.mode.all"), control_type=("Button", "Text"))
        from workspace_methods import METHODS

        gui.click(METHODS["ancova"].title)
    with journey.step("choose outcome, group and covariate"):
        gui.choose(T("role.outcome"), option_label("wellbeing", "scale"))
        gui.choose(T("role.group"), option_label("group", "nominal"))
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
        gui.click(T("nav.reports"), control_type=("Button", "Text"))
        gui.type_into(T("reports.study_title"), "Fictional ANCOVA study")
        field = gui.find(T("reports.study_title"), control_type="Edit")
        expect(gui.value(field) == "Fictional ANCOVA study",
               f"typed title kept: {gui.value(field)!r}")
    save_via_dialog(gui, journey, T("reports.export_txt"), work / "combined_report.txt",
                    kind="txt", contains=("Fictional ANCOVA study", expected.report.strip()))
    with journey.step("back up the project"):
        gui.click(T("nav.project"), control_type=("Button", "Text"))
    save_via_dialog(gui, journey, T("project.backup"), work / "study_a_backup.sra", kind="sra",
                    contains=("Fictional study A",))
    with journey.step("restart the application"):
        gui.stop()
        gui.start()
    with journey.step("reopen project A after the restart"):
        gui.click(T("nav.home"), control_type=("Button", "Text"))
        gui.click(T("project.open"), control_type="Button")
        gui.wait_text("Fictional study A")
        gui.wait_text("sample_ancova.csv")
        gui.wait_text(expected.title)
    with journey.step("open the restored result"):
        try:
            gui.click(T("reports.open_result"), control_type=("Button", "Text"), timeout=6)
        except StepFailure:   # the icon's name may be its tooltip or nothing
            gui.click(T("nav.results"), control_type=("Button", "Text"))
            gui.click(expected.title, control_type=("Button", "Text", "ListItem"))
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
        gui.click(T("nav.home"), control_type=("Button", "Text"))
        gui.click(T("project.open"), control_type="Button", index=0)
        gui.wait_text("Fictional study A")
        gui.wait_text("sample_ancova.csv")
        expect(not gui.has_text("sample_three_groups.csv"), "project A shows B's data")
    with journey.step("switch back to project B: only its own data"):
        gui.click(T("nav.home"), control_type=("Button", "Text"))
        gui.click(T("project.open"), control_type="Button", index=0)
        gui.wait_text("Fictional study B")
        gui.wait_text("sample_three_groups.csv")
        expect(not gui.has_text("sample_ancova.csv"), "project B shows A's data")
        expect(gui.has_text(T("project.no_results")), "project B shows A's results")


def import_document(gui: Gui, journey: Journey, pdf: Path, *, expected_items: int) -> None:
    with journey.step(f"import {pdf.name} in the Windows Open dialog"):
        gui.click(T("nav.questionnaires"), control_type=("Button", "Text"))
        gui.click(T("q.import"), control_type=("Button", "Text"))
        gui.file_dialog(pdf, save=False)
        # Reading (and local OCR of image pages) runs with a progress line.
        gui.wait_text(T("imp.read_ok", instruments=1, items=expected_items, name=pdf.name),
                      timeout=180)


def wizard_step(gui: Gui, number: int) -> None:
    """Open step ``number`` of the review wizard by its step button."""
    gui.click(regex=rf"^{number}\. ", control_type=("Button", "Text"))


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
        gui.keys("{END}")
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
    for item in range(3):
        gui.click(labels[int(stress)], control_type=("RadioButton", "Text"), index=item)


def journey_responses(gui: Gui, work: Path, journey: Journey) -> None:
    with journey.step("open project A (its dataset is in use)"):
        gui.click(T("nav.home"), control_type=("Button", "Text"))
        opened = False
        for index in range(3):
            with contextlib.suppress(StepFailure):
                gui.click(T("project.open"), control_type="Button", index=index, timeout=5)
                if gui.has_text("Fictional study A"):
                    opened = True
                    break
        expect(opened or gui.has_text("Fictional study A"), "project A did not open")
    with journey.step("start a small questionnaire from a template"):
        gui.click(T("nav.questionnaires"), control_type=("Button", "Text"))
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
            gui.click(T("q.collect"), control_type=("Button", "Text"), index=0)
            answer_form(gui, group, stress, 30 + respondent)
            gui.click(T("q.collect"), control_type="Button", index=0)
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
        gui.click(T("nav.project"), control_type=("Button", "Text"))
        gui.wait_text("sample_ancova.csv")
        gui.wait_text(T("responses.name", title="Fictional wellbeing pilot"))
    with journey.step("return to the original dataset with its levels"):
        gui.click(T("source.use"), control_type=("Button", "Text"), index=0)
        gui.wait_text(T("source.now_using", name="sample_ancova.csv"))


JOURNEYS = {
    "project-a": journey_project_a,
    "project-b": journey_project_b,
    "import-30": journey_import_30,
    "review-120": journey_review_120,
    "responses": journey_responses,
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
    parser.add_argument("--only", nargs="*", choices=sorted(JOURNEYS))
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv)
    if os.name != "nt":
        print("The packaged GUI journeys run on Windows only.")
        return 2
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="sra-e2e-files-"))
    data = Path(tempfile.mkdtemp(prefix="sra-e2e-data-"))
    preferences = Path.home() / ".statistical_research_assistant" / "preferences.json"
    with contextlib.suppress(OSError):
        preferences.unlink()        # default (English) preferences
    gui = Gui(args.exe.resolve(), data, out)
    report = {"exe": str(args.exe), "journeys": []}
    started = time.monotonic()
    try:
        gui.start()
        if args.probe:
            probe(gui)
        for name in args.only or list(JOURNEYS):
            journey = Journey(name, gui)
            outcome = {"journey": name, "ok": False}
            with gui.record(name):
                try:
                    if gui.process is None or gui.process.poll() is not None:
                        gui.start()
                    JOURNEYS[name](gui, work, journey)
                    outcome["ok"] = True
                except Exception as error:
                    outcome["error"] = f"{type(error).__name__}: {error}"
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
    (out / "gui-e2e-result.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                             encoding="utf-8")
    for name in ("ancova_report.txt", "combined_report.txt", "pilot_responses.csv"):
        with contextlib.suppress(OSError):
            shutil.copy(work / name, out / name)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
