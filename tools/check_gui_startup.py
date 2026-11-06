"""Windows CI: launch the packaged app normally and prove the GUI appears.

Usage: python tools/check_gui_startup.py path\\to\\StatisticalResearchAssistant.exe OUT_DIR

The executable runs its ordinary startup path (NOT the OCR self-test) with a
system-only PATH, so neither Python nor Tesseract from the runner can be
used. ``SRA_STARTUP_SMOKE`` only makes the app write its startup timings and
an interface summary when the real workspace is on screen, keep the window
open for screenshots and exit.

While the app starts, the window is captured every 0.5 s. The check fails if

* the app reports a failed startup or the Home screen is missing,
* the window stays (almost) black for more than ``--max-black`` seconds
  after it first appears (the reported "long black screen"),
* the final screenshot is not the light application UI,
* the interface is not ready within ``--timeout`` seconds.

Screenshots and a JSON verdict are written to OUT_DIR for the CI artifact.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

TITLE = "Statistical Research Assistant"


def descendants(root: int, pairs) -> set[int]:
    """``root`` and every process below it, from (pid, parent pid) pairs."""
    children: dict[int, list[int]] = {}
    for pid, parent in pairs:
        if pid != parent:
            children.setdefault(parent, []).append(pid)
    tree, todo = set(), [root]
    while todo:
        pid = todo.pop()
        if pid not in tree:
            tree.add(pid)
            todo.extend(children.get(pid, ()))
    return tree


def process_tree(root: int) -> set[int]:
    """The launched process and its descendants (Windows Toolhelp snapshot).

    ``flet build`` draws its window in the launched process; ``flet pack``
    starts a separate Flet client process that owns the window."""

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260)]

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)   # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return {root}
    pairs = []
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    try:
        more = kernel32.Process32First(snapshot, ctypes.byref(entry))
        while more:
            pairs.append((entry.th32ProcessID, entry.th32ParentProcessID))
            more = kernel32.Process32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return descendants(root, pairs)


def stop_tree(process) -> None:
    """End the app and every process it started (a Flet client, helpers);
    a left-over client would slow down every later launch on the runner."""
    if os.name == "nt":
        # Children keep their parent's id after it exits, so the tree is still
        # found when the launched process has already gone.
        pids = sorted(process_tree(process.pid))
        command = ["taskkill", "/T", "/F"]
        for pid in pids:
            command += ["/PID", str(pid)]
        try:
            subprocess.run(command, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    if process.poll() is None:
        process.kill()


def find_window(pid: int):
    user32 = ctypes.windll.user32
    found = []
    pids = process_tree(pid)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if width > 200 and height > 150:
                found.append((width * height, hwnd, (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        return None
    _, hwnd, rect = max(found)
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    return rect


def client_box(rect):
    # Skip the native title bar/borders: only the Flutter client area matters.
    left, top, right, bottom = rect
    return (left + 10, top + 45, right - 10, bottom - 10)


def frame_stats(image):
    gray = image.convert("L").resize((160, 100))
    pixels = list(gray.getdata())
    dark = sum(1 for p in pixels if p < 40) / len(pixels)
    mean = sum(pixels) / len(pixels)
    return dark, mean


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--max-black", type=float, default=3.0)
    parser.add_argument("--workspace", action="store_true",
                        help="start in the Stage 33 workspace preview (SRA_UI=workspace)")
    args = parser.parse_args(argv)
    if os.name != "nt":
        print("GUI startup check runs on Windows only.")
        return 2
    from PIL import ImageGrab

    args.out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="sra-gui-"))
    result_path = work / "startup-smoke.json"
    system = os.environ.get("SystemRoot", r"C:\Windows")
    env = {
        key: os.environ[key] for key in (
            "SystemRoot", "SYSTEMROOT", "windir", "TEMP", "TMP", "USERPROFILE",
            "LOCALAPPDATA", "APPDATA", "HOMEDRIVE", "HOMEPATH", "USERNAME",
            "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
        ) if key in os.environ
    }
    env.update({
        "PATH": f"{system}\\System32;{system};{system}\\System32\\Wbem",
        "SRA_STARTUP_SMOKE": str(result_path),
        "SRA_STARTUP_SMOKE_HOLD": "12",
        "SRA_LOG_DIR": str(work / "logs"),
    })
    if args.workspace:
        env["SRA_UI"] = "workspace"
    started = time.monotonic()
    process = subprocess.Popen([str(args.exe)], cwd=str(args.exe.parent), env=env)
    frames = []  # (seconds, dark_fraction, mean_luma)
    window_seen = None
    saved = {}
    ready_at = None
    try:
        while time.monotonic() - started < args.timeout:
            now = time.monotonic() - started
            if process.poll() is not None and not result_path.exists():
                break
            rect = find_window(process.pid)
            if rect:
                if window_seen is None:
                    window_seen = now
                try:
                    image = ImageGrab.grab(bbox=client_box(rect), all_screens=True)
                except OSError:
                    image = None
                if image is not None:
                    dark, mean = frame_stats(image)
                    frames.append((round(now, 2), round(dark, 3), round(mean, 1)))
                    for label, at in (("first", 0.0), ("after_2s", 2.0), ("after_5s", 5.0)):
                        if label not in saved and now - window_seen >= at:
                            image.save(args.out / f"startup_{label}.png")
                            saved[label] = now
            if result_path.exists() and ready_at is None:
                ready_at = now
            if ready_at is not None and now - ready_at > 3.0:
                break
            time.sleep(0.5)
        final = None
        rect = find_window(process.pid)
        if rect:
            final = ImageGrab.grab(bbox=client_box(rect), all_screens=True)
            final.save(args.out / "startup_final.png")
    finally:
        stop_tree(process)
    errors = []
    smoke = {}
    if result_path.exists():
        smoke = json.loads(result_path.read_text(encoding="utf-8"))
        if smoke.get("outcome") != "ok":
            errors.append(f"startup outcome: {smoke.get('outcome')}: {(smoke.get('error') or '')[-400:]}")
        if args.workspace and not smoke.get("workspace_present"):
            errors.append("Stage 33 workspace preview not on screen")
        if not args.workspace and not smoke.get("has_home_banner"):
            errors.append("Home screen text not found in the interface")
        if smoke.get("splash_present") or smoke.get("failure_present"):
            errors.append("splash or failure view still on screen after startup")
    else:
        errors.append(f"no startup result within {args.timeout:.0f}s (exit code {process.poll()})")
    if window_seen is None:
        errors.append("application window never appeared")
    longest = 0.0
    run_start = None
    for seconds, dark, _mean in frames:
        if dark > 0.9:
            run_start = seconds if run_start is None else run_start
            longest = max(longest, seconds - run_start)
        else:
            run_start = None
    if longest > args.max_black:
        errors.append(f"window stayed black for {longest:.1f}s (limit {args.max_black:.1f}s)")
    final_stats = frame_stats(final) if final is not None else None
    if final_stats is None:
        errors.append("no final screenshot")
    elif final_stats[0] > 0.5 or final_stats[1] < 150:
        errors.append(f"final window is not the light UI (dark {final_stats[0]:.2f}, mean {final_stats[1]:.0f})")
    first_light = next((s for s, dark, mean in frames if dark < 0.5 and mean > 150), None)
    phases = {p["phase"]: p["seconds"] for p in smoke.get("phases", [])}
    verdict = {
        "ok": not errors, "errors": errors,
        "window_visible_after_s": window_seen,
        "first_light_frame_after_s": first_light,
        "interface_ready_reported_s": phases.get("interface_ready"),
        "splash_shown_reported_s": phases.get("splash_shown"),
        "longest_black_s": round(longest, 2),
        "final_dark_fraction": final_stats[0] if final_stats else None,
        "final_mean_luma": final_stats[1] if final_stats else None,
        "frames": frames, "app_result": smoke,
    }
    (args.out / "gui-startup-result.json").write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in verdict.items() if k not in {"frames", "app_result"}}, indent=1))
    print("Phases:", ", ".join(f"{k} {v}s" for k, v in phases.items()))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
