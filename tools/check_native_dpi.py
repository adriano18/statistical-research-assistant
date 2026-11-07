"""The packaged program at native Windows display scales 100/125/150 % (#46).

    python tools/check_native_dpi.py build\\windows\\StatisticalResearchAssistant.exe out\\dpi

For each scale: set Windows' display scale (tools/set_display_scale.py; a
real system setting, not browser zoom), start the program, then:
- read the DPI Windows gives its window (GetDpiForWindow: 96/120/144);
- take a screenshot;
- through UI Automation, check that the Home page offers "Create project";
- check that every sidebar item is visible;
- check that no named control extends past the window's right edge (clipping).
The scale is restored to 100 % at the end.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import set_display_scale as sds  # noqa: E402

SIDEBAR = ("Home", "Data", "Questionnaires", "Analyze", "Results", "Reports", "Settings")


def run_at(exe: Path, scale: int, out: Path) -> dict:
    from PIL import ImageGrab
    from pywinauto import Desktop
    from pywinauto.application import Application

    applied = sds.set_scale(scale)
    time.sleep(3)
    system = os.environ.get("SystemRoot", r"C:\Windows")
    data = tempfile.mkdtemp(prefix="sra-dpi-")
    env = {k: os.environ[k] for k in ("SystemRoot", "SYSTEMROOT", "windir", "TEMP", "TMP", "USERPROFILE",
                                       "LOCALAPPDATA", "APPDATA", "USERNAME", "COMPUTERNAME")
           if k in os.environ}
    env.update({"PATH": f"{system}\\System32;{system}", "SRA_UI": "workspace", "SRA_DATA_DIR": data,
                "SRA_UPDATE_CHECK": "0"})
    process = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    facts = {"scale": scale, "display": applied}
    try:
        handle = None
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline and not handle:
            for window in Desktop(backend="uia").windows():
                with contextlib.suppress(Exception):
                    if window.process_id() == process.pid and window.rectangle().width() > 300:
                        handle = window.handle
                        break
            time.sleep(1)
        if not handle:
            facts["problem"] = "no window"
            return facts
        win = Application(backend="uia").connect(handle=handle).window(handle=handle)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            names = [e.element_info.name or "" for e in win.descendants()]
            if any(name == "Create project" for name in names):
                break
            time.sleep(1)
        time.sleep(2)
        ctypes.windll.user32.ShowWindow(handle, 3)                     # maximize
        time.sleep(3)
        rect = win.rectangle()
        facts["window_dpi"] = ctypes.windll.user32.GetDpiForWindow(handle)
        facts["expected_dpi"] = round(96 * scale / 100)
        facts["window"] = [rect.left, rect.top, rect.right, rect.bottom]
        elements = [(e.element_info.name or "", e.element_info.rectangle) for e in win.descendants()]
        named = [(n, r) for n, r in elements if n.strip() and r.width() > 0]
        facts["create_project_shown"] = any(n == "Create project" for n, _ in named)
        facts["sidebar_shown"] = sorted({n for n, _ in named if n in SIDEBAR})
        facts["clipped"] = sorted({n[:60] for n, r in named
                                   if r.right > rect.right + 2 and r.left < rect.right})[:20]
        shot = out / f"home-{scale}.png"
        ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True).save(shot)
        facts["screenshot"] = shot.name
    finally:
        with contextlib.suppress(Exception):
            process.terminate()
            process.wait(timeout=20)
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    return facts


def main(argv=None) -> int:
    if os.name != "nt":
        print("Native DPI checks run on Windows only.")
        return 2
    sds.per_monitor_aware()
    args = list(sys.argv[1:] if argv is None else argv)
    exe, out = Path(args[0]).resolve(), Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    before = sds.get_scale()
    results, problems = [], []
    try:
        for scale in (100, 125, 150):
            if scale > before["maximum"]:
                results.append({"scale": scale, "skipped": f"this display allows up to {before['maximum']} %"})
                problems.append(f"{scale} %: not offered by this display")
                continue
            facts = run_at(exe, scale, out)
            results.append(facts)
            if facts.get("window_dpi") != facts.get("expected_dpi"):
                problems.append(f"{scale} %: window DPI {facts.get('window_dpi')} instead of "
                                f"{facts.get('expected_dpi')}")
            if not facts.get("create_project_shown"):
                problems.append(f"{scale} %: Home did not offer Create project")
            if len(facts.get("sidebar_shown", [])) != len(SIDEBAR):
                problems.append(f"{scale} %: sidebar items missing: {sorted(set(SIDEBAR) - set(facts.get('sidebar_shown', [])))}")
            if facts.get("clipped"):
                problems.append(f"{scale} %: clipped at the right edge: {facts['clipped']}")
            print(json.dumps(facts), flush=True)
    finally:
        with contextlib.suppress(Exception):
            sds.set_scale(100)
    report = {"display_before": before, "results": results, "problems": problems}
    (out / "native-dpi.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for problem in problems:
        print("FAIL", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
