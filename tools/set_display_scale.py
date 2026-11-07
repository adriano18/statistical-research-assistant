"""Set the Windows display scale (100 %, 125 %, 150 %) for native DPI tests (#46).

    python tools/set_display_scale.py 125        # prints the scale now in effect
    python tools/set_display_scale.py --get

This is the display setting a person changes in Settings -> Display ->
Scale, not browser zoom. Windows applies it to newly started programs
without signing out. It uses the DisplayConfig API with the source DPI
scale device-info types that Windows' own settings page uses (-3 to read,
-4 to set; not in the public headers). The scale is set relative to the
display's recommended step.
"""

from __future__ import annotations

import ctypes
import json
import sys
from ctypes import wintypes

STEPS = (100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500)
QDC_ONLY_ACTIVE_PATHS = 2
GET_DPI_SCALE, SET_DPI_SCALE = -3, -4


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class PATH_SOURCE(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("statusFlags", ctypes.c_uint32)]


class PATH_TARGET(ctypes.Structure):
    _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32), ("modeInfoIdx", ctypes.c_uint32),
                ("outputTechnology", ctypes.c_uint32), ("rotation", ctypes.c_uint32),
                ("scaling", ctypes.c_uint32), ("refreshRate", ctypes.c_uint32 * 2),
                ("scanLineOrdering", ctypes.c_uint32), ("targetAvailable", wintypes.BOOL),
                ("statusFlags", ctypes.c_uint32)]


class PATH_INFO(ctypes.Structure):
    _fields_ = [("sourceInfo", PATH_SOURCE), ("targetInfo", PATH_TARGET), ("flags", ctypes.c_uint32)]


class MODE_INFO(ctypes.Structure):
    _fields_ = [("infoType", ctypes.c_uint32), ("id", ctypes.c_uint32), ("adapterId", LUID),
                ("data", ctypes.c_byte * 48)]


class HEADER(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int32), ("size", ctypes.c_uint32), ("adapterId", LUID),
                ("id", ctypes.c_uint32)]


class GET_SCALE(ctypes.Structure):
    _fields_ = [("header", HEADER), ("minScaleRel", ctypes.c_int32), ("curScaleRel", ctypes.c_int32),
                ("maxScaleRel", ctypes.c_int32)]


class SET_SCALE(ctypes.Structure):
    _fields_ = [("header", HEADER), ("scaleRel", ctypes.c_int32)]


def _primary_source() -> PATH_SOURCE:
    user = ctypes.windll.user32
    paths, modes = ctypes.c_uint32(), ctypes.c_uint32()
    if user.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(paths), ctypes.byref(modes)):
        raise OSError("GetDisplayConfigBufferSizes failed")
    path_array = (PATH_INFO * paths.value)()
    mode_array = (MODE_INFO * modes.value)()
    if user.QueryDisplayConfig(QDC_ONLY_ACTIVE_PATHS, ctypes.byref(paths), path_array,
                               ctypes.byref(modes), mode_array, None):
        raise OSError("QueryDisplayConfig failed")
    if not paths.value:
        raise OSError("no active display")
    return path_array[0].sourceInfo


def _header(kind: int, size: int, source: PATH_SOURCE) -> HEADER:
    return HEADER(kind, size, source.adapterId, source.id)


def get_scale() -> dict:
    source = _primary_source()
    info = GET_SCALE()
    info.header = _header(GET_DPI_SCALE, ctypes.sizeof(GET_SCALE), source)
    if ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)):
        raise OSError("reading the display scale failed")
    recommended = abs(info.minScaleRel)
    current = recommended + info.curScaleRel
    maximum = recommended + info.maxScaleRel
    return {"current": STEPS[current], "recommended": STEPS[recommended],
            "maximum": STEPS[min(maximum, len(STEPS) - 1)],
            "system_dpi": ctypes.windll.user32.GetDpiForSystem()}


def set_scale(percent: int) -> dict:
    if percent not in STEPS:
        raise ValueError(f"Windows offers {STEPS}, not {percent}")
    source = _primary_source()
    info = GET_SCALE()
    info.header = _header(GET_DPI_SCALE, ctypes.sizeof(GET_SCALE), source)
    if ctypes.windll.user32.DisplayConfigGetDeviceInfo(ctypes.byref(info)):
        raise OSError("reading the display scale failed")
    recommended = abs(info.minScaleRel)
    wanted = STEPS.index(percent) - recommended
    if not info.minScaleRel <= wanted <= info.maxScaleRel:
        raise ValueError(f"this display allows {STEPS[0]}..{STEPS[recommended + info.maxScaleRel]} %")
    request = SET_SCALE()
    request.header = _header(SET_DPI_SCALE, ctypes.sizeof(SET_SCALE), source)
    request.scaleRel = wanted
    if ctypes.windll.user32.DisplayConfigSetDeviceInfo(ctypes.byref(request)):
        raise OSError("setting the display scale failed")
    return get_scale()


def per_monitor_aware() -> None:
    """Make this process see real DPI values (not the 96 of unaware programs)."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_V2
    except (AttributeError, OSError):
        pass


def main(argv=None) -> int:
    per_monitor_aware()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] == "--get":
        print(json.dumps(get_scale()))
        return 0
    result = set_scale(int(args[0]))
    print(json.dumps(result))
    return 0 if result["current"] == int(args[0]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
