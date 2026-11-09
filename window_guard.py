"""Show the program's own window when it is still hidden after start (Windows).

Packaged-build CI runs saw a started program whose native window never
appeared: the Flutter runner window existed, already sized (1200 x 720) and
centred by the program, but stayed hidden (``IsWindowVisible`` false) for
300 s while the program's startup log recorded a complete start (installer
run 42648266085, "the next start does not ask again"; update journeys on
#55 at 51618f3 and 8681d94). A user would see nothing at all.

The runner shows its window on the first rendered frame and Flet's client
shows it again once ``window_manager`` is ready; this guard covers the case
where neither did. It looks only at this process's own runner window
(``FLUTTER_RUNNER_WIN32_WINDOW``), acts at most once, and never touches a
window that is visible (a window the user minimized is visible, so it is
left alone). Nothing happens outside Windows or when the window belongs to
another process (``flet run`` during development).

Every intervention is appended to the local ``startup.log`` so that CI and
support can see how often it was needed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import sys
import time
from typing import Callable, Iterable, Protocol

FLUTTER_WINDOW_CLASS = "FLUTTER_RUNNER_WIN32_WINDOW"
SW_SHOWNORMAL = 1
# Seconds after the splash was painted. The runner normally shows the window
# before Python even starts, so the first check already finds it visible.
CHECKS = (3.0, 8.0, 15.0, 30.0)


@dataclass(frozen=True)
class NativeWindow:
    handle: int
    visible: bool
    minimized: bool


class Windows(Protocol):
    def own_windows(self, pid: int) -> list[NativeWindow]: ...

    def show(self, handle: int) -> bool: ...


class Win32Windows:
    """The few user32 calls the guard needs, with their own prototypes."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self._ctypes, self._wintypes = ctypes, wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._visit_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [self._visit_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                    ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        self._user32 = user32

    def own_windows(self, pid: int) -> list[NativeWindow]:
        ctypes, wintypes, user32 = self._ctypes, self._wintypes, self._user32
        found: list[NativeWindow] = []

        def visit(hwnd, _):
            try:
                owner = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value == pid:
                    name = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(hwnd, name, 128)
                    if name.value == FLUTTER_WINDOW_CLASS:
                        found.append(NativeWindow(int(hwnd), bool(user32.IsWindowVisible(hwnd)),
                                                  bool(user32.IsIconic(hwnd))))
            except Exception:
                pass
            return True

        user32.EnumWindows(self._visit_type(visit), 0)
        return found

    def show(self, handle: int) -> bool:
        shown = bool(self._user32.ShowWindow(handle, SW_SHOWNORMAL)) \
            or bool(self._user32.IsWindowVisible(handle))
        try:    # a newly started program normally comes to the front
            self._user32.SetForegroundWindow(handle)
        except Exception:
            pass
        return shown


def ensure_shown(windows: Windows | None = None, pid: int | None = None) -> str:
    """One check: "visible", "shown", "failed", "no_window" or "unsupported"."""
    if windows is None:
        if sys.platform != "win32":
            return "unsupported"
        try:
            windows = Win32Windows()
        except Exception:
            return "unsupported"
    try:
        own = windows.own_windows(os.getpid() if pid is None else pid)
    except Exception:
        return "unsupported"
    if not own:
        return "no_window"
    if any(window.visible for window in own):
        return "visible"
    try:
        return "shown" if windows.show(own[0].handle) else "failed"
    except Exception:
        return "failed"


async def guard(*, windows: Windows | None = None, pid: int | None = None,
                checks: Iterable[float] = CHECKS,
                log: Callable[[dict], object] | None = None,
                sleep: Callable[[float], object] = asyncio.sleep) -> str:
    """Check at ``checks`` seconds until the window is visible.

    Stops as soon as the window is found visible (the normal case, at the
    first check), was shown, or there is nothing to guard; only a failed
    attempt is repeated at the next check. Each intervention is passed to
    ``log``."""
    started = time.monotonic()
    waited = 0.0
    outcome = "visible"
    for at in checks:
        await sleep(max(0.0, at - waited))
        waited = at
        outcome = ensure_shown(windows, pid)
        if outcome in ("shown", "failed") and log is not None:
            try:
                log({"event": "window_guard", "outcome": outcome,
                     "after_s": round(time.monotonic() - started, 1),
                     "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            except Exception:
                pass
        if outcome != "failed":
            return outcome
    return outcome
