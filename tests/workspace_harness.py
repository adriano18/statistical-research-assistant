"""Test helpers: build the Stage 33 workspace on a fake page and click it."""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

from ux_inventory import FakePage as _InventoryPage, walk  # noqa: E402


class FakePage(_InventoryPage):
    def __init__(self, width: int = 1440):
        super().__init__(width)
        self.dialog = None
        self.on_keyboard_event = None
        self.on_resize = None

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None


class Workspace:
    """A live WorkspaceApp plus helpers to find and operate controls."""

    def __init__(self, width: int = 1440, *, language: str = "en", bridge=None,
                 root: Path | None = None):
        """``root`` reuses a data folder (an application restart); by default
        every workspace gets its own temporary folder."""
        from flet.controls.context import _context_page
        from workspace_shell import ClassicBridge, WorkspaceApp

        self.temp = None if root is not None else TemporaryDirectory()
        self.root = Path(root) if root is not None else Path(self.temp.name)
        # Workspace appearance settings live in the test folder, not in $HOME.
        from unittest import mock
        import workspace_shell

        self._settings = mock.patch.object(workspace_shell, "workspace_settings_path",
                                           lambda: self.root / "workspace.json")
        self._settings.start()
        self.page = FakePage(width)
        self._token = _context_page.set(self.page)
        self.app = WorkspaceApp(
            self.page, language=language,
            bridge=bridge or ClassicBridge(survey_root=self.root / "surveys"))
        self.app.mount()
        self.saved: list[Path] = []

        async def save_dialog(title, file_name, extension):
            path = self.root / file_name
            self.saved.append(path)
            return str(path)

        self.app.save_dialog = save_dialog

    def close(self):
        """Quit the application: the open project is closed, its lock released."""
        from flet.controls.context import _context_page

        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.app.projects.close(clear=False)
        self._settings.stop()
        _context_page.reset(self._token)
        if self.temp is not None:
            self.temp.cleanup()

    # ------------------------------------------------------------ queries
    def controls(self, root=None) -> list:
        found = []
        walk(root or self.page.controls[0], lambda c, d: found.append(c))
        if self.page.dialog is not None:
            walk(self.page.dialog, lambda c, d: found.append(c))
        return found

    def find(self, data: str, kind=None):
        for control in self.controls():
            if getattr(control, "data", None) == data and (kind is None or isinstance(control, kind)):
                return control
        raise AssertionError(f"No control with data={data!r} on route {self.app.route}")

    def find_all(self, prefix: str) -> list:
        return [c for c in self.controls()
                if isinstance(getattr(c, "data", None), str) and c.data.startswith(prefix)]

    def texts(self) -> list[str]:
        return [c.value for c in self.controls()
                if isinstance(c, ft.Text) and isinstance(c.value, str)]

    def has_text(self, fragment: str) -> bool:
        return any(fragment in text for text in self.texts())

    # ------------------------------------------------------------ actions
    def run(self, result):
        if asyncio.iscoroutine(result):
            return asyncio.run(result)
        return result

    def dispatch(self, handler, event):
        """Call an event handler exactly as Flet 1.x does
        (``flet/controls/base_control.py``): a coroutine function is awaited;
        any other callable is called and whatever it returns is dropped. A
        plain handler, such as a lambda, that returns a coroutine therefore does
        nothing in the application: it fails here instead of being run."""
        from flet.utils.object_model import get_param_count

        def call():
            return handler() if get_param_count(handler) == 0 else handler(event)

        if inspect.iscoroutinefunction(handler):
            return asyncio.run(call())
        result = call()
        if inspect.iscoroutine(result):
            result.close()
            raise AssertionError(f"{handler!r} returns a coroutine that Flet never awaits: "
                                 "the action would do nothing in the application")
        return result

    def click(self, data: str):
        control = self.find(data)
        handler = getattr(control, "on_click", None)
        if handler is None:
            raise AssertionError(f"{data} is not clickable")
        if getattr(control, "disabled", False):
            raise AssertionError(f"{data} is disabled")
        return self.dispatch(handler, SimpleNamespace(control=control, data=None))

    def choose(self, data: str, value):
        control = self.find(data, ft.Dropdown)
        control.value = value
        return self.dispatch(control.on_select, SimpleNamespace(control=control, data=value))

    def check(self, data: str, value: bool = True):
        control = self.find(data, ft.Checkbox)
        control.value = value
        return self.dispatch(control.on_change, SimpleNamespace(control=control, data=value))

    def type(self, data: str, value: str):
        control = self.find(data, ft.TextField)
        control.value = value
        return self.dispatch(control.on_change, SimpleNamespace(control=control, data=value))

    def segment(self, data: str, key: str):
        group = self.find(data)
        for control in self.controls(group):
            if isinstance(control, ft.Button) and control.data == key:
                return self.dispatch(control.on_click, SimpleNamespace(control=control))
        raise AssertionError(f"segment {key} not in {data}")

    def key(self, key: str, *, ctrl=False, shift=False, alt=False):
        event = SimpleNamespace(key=key, ctrl=ctrl, shift=shift, alt=alt, meta=False)
        return self.dispatch(self.app.on_keyboard, event)
