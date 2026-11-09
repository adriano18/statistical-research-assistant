"""Copy a chart to the system clipboard as an image, not as a file path.

Stage 36.4 (docs/STAGE36_SPEC.md §9): "the clipboard must really contain an
image". Flet's desktop clipboard holds text and file references only, so
the desktop program writes the image itself:

* Windows: ``CF_DIB`` (a device-independent bitmap that Word, PowerPoint,
  Paint and e-mail programs paste) plus the registered ``PNG`` format
  (lossless, read by newer Office versions, LibreOffice and browsers),
  through the Win32 clipboard API with an owner window, as the API requires;
* Linux: ``wl-copy`` (Wayland) or ``xclip`` (X11) with ``image/png``,
  when one of them is installed.

Every attempt ends with a :class:`ClipboardOutcome`; nothing is retried
silently and no file is written. :func:`clipboard_image_size` reads back
what the Windows clipboard holds (used by the packaged-program tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
import shutil
import subprocess
import sys
import time

from PIL import Image

CF_DIB = 8
GMEM_MOVEABLE = 0x0002
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ClipboardOutcome:
    copied: bool
    how: str            # "windows", "wl-copy", "xclip", "unavailable" or "failed"
    detail: str = ""


def _checked_png(png: bytes) -> bytes:
    if not isinstance(png, (bytes, bytearray)) or not bytes(png).startswith(PNG_SIGNATURE):
        raise ValueError("Only a PNG image can be copied.")
    return bytes(png)


def png_to_dib(png: bytes) -> bytes:
    """A packed DIB (BITMAPINFOHEADER + 24-bit bottom-up rows) of ``png``.

    Transparent areas are laid on white, the background of every chart.
    """
    with Image.open(BytesIO(_checked_png(png))) as image:
        image.load()
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            rgb = Image.new("RGB", rgba.size, "white")
            rgb.paste(rgba, mask=rgba.getchannel("A"))
        else:
            rgb = image.convert("RGB")
    buffer = BytesIO()
    rgb.save(buffer, format="BMP")
    return buffer.getvalue()[14:]          # without the 14-byte BITMAPFILEHEADER


# ------------------------------------------------------------------ Windows
def _win32():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Pointer-sized handles must be declared, or 64-bit values are truncated.
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.restype = wintypes.HANDLE
    kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    return ctypes, user32, kernel32


def _open_clipboard(user32, owner) -> bool:
    # Another program may hold the clipboard for a moment.
    for _ in range(20):
        if user32.OpenClipboard(owner):
            return True
        time.sleep(0.05)
    return False


def _windows_copy(png: bytes) -> ClipboardOutcome:
    ctypes, user32, kernel32 = _win32()
    dib = png_to_dib(png)
    # SetClipboardData needs a clipboard owner window: with no owner,
    # EmptyClipboard leaves the clipboard without one and the data are refused.
    owner = user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
    if not owner:
        return ClipboardOutcome(False, "failed", f"no window ({ctypes.get_last_error()})")

    def put(fmt: int, data: bytes) -> None:
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise OSError(ctypes.get_last_error(), "GlobalAlloc failed")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise OSError(ctypes.get_last_error(), "GlobalLock failed")
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(fmt, handle):
            kernel32.GlobalFree(handle)     # still ours: the system did not take it
            raise OSError(ctypes.get_last_error(), "SetClipboardData failed")

    try:
        if not _open_clipboard(user32, owner):
            return ClipboardOutcome(False, "failed", "the clipboard is in use by another program")
        try:
            if not user32.EmptyClipboard():
                raise OSError(ctypes.get_last_error(), "EmptyClipboard failed")
            put(CF_DIB, dib)
            png_format = user32.RegisterClipboardFormatW("PNG")
            if png_format:
                put(png_format, png)
        finally:
            user32.CloseClipboard()
    except OSError as error:
        return ClipboardOutcome(False, "failed", str(error))
    finally:
        user32.DestroyWindow(owner)
    if not user32.IsClipboardFormatAvailable(CF_DIB):
        return ClipboardOutcome(False, "failed", "the image is not on the clipboard")
    return ClipboardOutcome(True, "windows")


def clipboard_image_size() -> tuple[int, int] | None:
    """Width and height of the bitmap on the Windows clipboard, or None."""
    if sys.platform != "win32":
        return None
    ctypes, user32, kernel32 = _win32()
    if not user32.IsClipboardFormatAvailable(CF_DIB):
        return None
    if not _open_clipboard(user32, None):
        return None
    try:
        handle = user32.GetClipboardData(CF_DIB)
        if not handle or kernel32.GlobalSize(handle) < 40:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            header = ctypes.string_at(pointer, 40)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    width = int.from_bytes(header[4:8], "little", signed=True)
    height = int.from_bytes(header[8:12], "little", signed=True)
    return width, abs(height)


# -------------------------------------------------------------------- Linux
def _linux_command() -> tuple[str, list[str]] | None:
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return "wl-copy", ["wl-copy", "--type", "image/png"]
    if os.environ.get("DISPLAY") and shutil.which("xclip"):
        return "xclip", ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"]
    return None


def copy_png(png: bytes) -> ClipboardOutcome:
    """Put ``png`` on the system clipboard as an image."""
    png = _checked_png(png)
    if sys.platform == "win32":
        return _windows_copy(png)
    if sys.platform.startswith("linux"):
        command = _linux_command()
        if command is None:
            return ClipboardOutcome(False, "unavailable",
                                    "install wl-clipboard or xclip to copy images")
        name, argv = command
        try:
            # The helper keeps serving the clipboard after we return; its
            # output is not captured, so nothing waits for it.
            subprocess.run(argv, input=png, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            return ClipboardOutcome(False, "failed", f"{name}: {error}")
        return ClipboardOutcome(True, name)
    return ClipboardOutcome(False, "unavailable", f"not supported on {sys.platform}")
