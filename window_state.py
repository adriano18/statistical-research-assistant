"""The program window's size, position and maximized state, kept between
starts (Stage 37, issue #68; review finding D2).

Before Stage 37 every start set the window to 1200 x 720 and centred it. The
window's normal bounds and whether it was maximized are now saved in the
settings file (``user_settings``, key ``window``) while the program runs and
restored at the next start, before the splash is painted.

A position is restored only when the saved window still lies mostly on one of
the screens Windows reports now (a monitor may have been disconnected or its
resolution changed); otherwise the window keeps the saved size, shrunk to fit
when needed, and is centred as before. A window can never be restored off
screen. Elsewhere than on Windows only the size and the maximized state are
restored. No Flet imports.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_SIZE = (1200, 720)
MIN_SIZE = (800, 560)
VISIBLE_PART = 0.5          # this share of a restored window must be on one screen
TITLE_BAR = 40              # and the top band (the title bar) must be reachable


@dataclass(frozen=True)
class Placement:
    width: float
    height: float
    left: float | None = None      # None: centre the window
    top: float | None = None
    maximized: bool = False


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, right - left) * max(0.0, bottom - top)


def placement(saved: dict | None, screens: list[tuple[float, float, float, float]] | None
              ) -> Placement:
    """Where to open the window: ``saved`` is the settings' ``window`` value,
    ``screens`` the work areas (left, top, right, bottom) in the same logical
    pixels, or None when they cannot be known."""
    width, height = DEFAULT_SIZE
    if not saved:
        return Placement(width, height)
    width = max(MIN_SIZE[0], float(saved.get("width") or width))
    height = max(MIN_SIZE[1], float(saved.get("height") or height))
    maximized = bool(saved.get("maximized"))
    left, top = saved.get("left"), saved.get("top")
    if screens:
        largest = max(screens, key=lambda s: (s[2] - s[0]) * (s[3] - s[1]))
        width = min(width, largest[2] - largest[0])
        height = min(height, largest[3] - largest[1])
    if left is None or top is None or not screens:
        return Placement(width, height, maximized=maximized)
    box = (float(left), float(top), float(left) + width, float(top) + height)
    title = (box[0], box[1], box[2], box[1] + TITLE_BAR)
    area = width * height
    on_screen = any(_overlap(box, screen) >= VISIBLE_PART * area
                    and _overlap(title, screen) > 0 for screen in screens)
    if not on_screen:
        return Placement(width, height, maximized=maximized)
    return Placement(width, height, float(left), float(top), maximized)


def capture(window, *, maximized: bool | None = None, previous: dict | None = None) -> dict | None:
    """The settings value for ``window`` (a ``ft.Window`` or a stand-in).

    While the window is maximized its normal bounds are not known, so the
    previous ones are kept with ``maximized`` set."""
    is_maximized = bool(getattr(window, "maximized", False)) if maximized is None else maximized
    if is_maximized:
        if previous:
            return {**previous, "maximized": True}
        return {"width": float(DEFAULT_SIZE[0]), "height": float(DEFAULT_SIZE[1]),
                "maximized": True}
    width, height = getattr(window, "width", None), getattr(window, "height", None)
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)) \
            or width < 100 or height < 100:
        return None
    value = {"width": round(float(width), 1), "height": round(float(height), 1),
             "maximized": False}
    left, top = getattr(window, "left", None), getattr(window, "top", None)
    if isinstance(left, (int, float)) and isinstance(top, (int, float)):
        value.update(left=round(float(left), 1), top=round(float(top), 1))
    return value


def work_areas() -> list[tuple[float, float, float, float]] | None:
    """Windows: the work area of every monitor, in logical pixels of the
    primary monitor's scale (Flet's window coordinates); None elsewhere or if
    they cannot be read."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        # A private instance with its own prototypes (handles are 64-bit).
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        areas: list[tuple[float, float, float, float]] = []
        visit_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
        user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                               visit_type, wintypes.LPARAM]
        user32.EnumDisplayMonitors.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL

        def visit(monitor, _dc, _rect, _data):
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                work = info.rcWork
                areas.append((work.left, work.top, work.right, work.bottom))
            return True

        callback = visit_type(visit)          # kept alive for the call
        user32.EnumDisplayMonitors(None, None, callback, 0)
        scale = 1.0
        try:
            user32.GetDpiForSystem.restype = wintypes.UINT
            scale = max(0.5, user32.GetDpiForSystem() / 96.0)
        except Exception:
            pass
        return [tuple(v / scale for v in area) for area in areas] or None
    except Exception:
        return None
