"""Capture and sanity-check the Stage 33 review screenshots.

    python tools/workspace_screenshot_suite.py docs/images/stage33

For every entry of ``MATRIX`` a fresh Flet web preview serves a scenario
from ``tools/workspace_scenarios.py`` and Playwright saves a PNG at the
given window size and device pixel ratio (1.25/1.5 emulate 125/150 %
Windows display scaling). Each image is then checked automatically:

* the page rendered (enough distinct colours, not a blank canvas);
* no Flutter error placeholder (large flat grey blocks) is visible.

Requires Node with the pre-installed Playwright Chromium. Fictional data only.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

# name, scenario, width, height, scale, language, theme
MATRIX = (
    ("home_light", "home", 1440, 900, 1, "en", "light"),
    ("home_dark", "home", 1440, 900, 1, "en", "dark"),
    ("home_ru_150", "home", 1280, 800, 1.5, "ru", "light"),
    ("data_dictionary", "data", 1440, 1100, 1, "en", "light"),
    ("analyze_guided", "guided", 1440, 1300, 1, "en", "light"),
    ("analyze_guided_lv_125", "guided", 1280, 1300, 1.25, "lv", "light"),
    ("analyze_catalog", "catalog", 1440, 1200, 1, "en", "light"),
    ("results_detail", "results", 1440, 2600, 1, "en", "light"),
    ("results_dark_compact", "results", 1100, 1200, 1, "en", "dark"),
    ("reports", "reports", 1440, 900, 1, "en", "light"),
    ("questionnaires_builder", "questionnaires", 1440, 1100, 1, "en", "light"),
    ("questionnaires_phone_preview", "phone-preview", 1440, 1100, 1, "en", "light"),
    ("questionnaires_narrow", "questionnaires", 960, 1000, 1, "en", "light"),
    ("scientific_import", "import", 1600, 1500, 1, "en", "light"),
    ("help_shortcuts", "help", 1280, 800, 1, "en", "light"),
    ("home_projects", "projects", 1440, 1500, 1, "en", "light"),
    ("home_projects_lv_125", "projects", 1280, 1600, 1.25, "lv", "light"),
    ("home_projects_ru_dark", "projects", 1100, 1600, 1, "ru", "dark"),
    ("results_stale", "results-stale", 1440, 1500, 1, "en", "light"),
    ("settings_profile", "settings-profile", 1440, 2600, 1, "en", "light"),
    ("settings_profile_ru", "settings-profile", 1280, 2600, 1.25, "ru", "light"),
    ("classic_home", "classic-home", 1440, 900, 1, "en", "light"),
    ("classic_groups", "classic-groups", 1440, 2200, 1, "en", "light"),
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait(port: int, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    raise TimeoutError(f"preview server on {port} did not start")


def check_image(path: Path) -> list[str]:
    """Rendered-content and error-placeholder checks for one screenshot."""
    from PIL import Image

    problems = []
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        small = rgb.resize((max(1, rgb.width // 4), max(1, rgb.height // 4)))
        pixels = [small.getpixel((x, y)) for y in range(small.height) for x in range(small.width)]
    colours = len(set(pixels))
    if colours < 40:
        problems.append(f"almost blank ({colours} colours)")
    # Rendered pages are at most ~60 % one background colour; Flet's loading
    # screen (a logo on white) is ~99 % and has enough anti-aliased colours
    # to pass the check above.
    dominant = Counter(pixels).most_common(1)[0][1] / len(pixels)
    if dominant > 0.9:
        problems.append(f"not rendered: {dominant:.0%} one colour (loading screen?)")
    # Flutter's release-mode error box is flat neutral grey: #B7B7B7 on the
    # dark theme, slightly lighter on the light theme.
    grey = sum(1 for r, g, b in pixels if 175 <= r <= 200 and 175 <= g <= 200
               and 175 <= b <= 200 and abs(r - g) < 8 and abs(g - b) < 8)
    if grey / len(pixels) > 0.04:
        problems.append(f"possible error placeholder ({grey / len(pixels):.1%} flat grey)")
    return problems


def capture(entry, out_dir: Path, wait_ms: int) -> dict:
    name, scenario, width, height, scale, language, theme = entry
    port = _free_port()
    env = {**os.environ, "MPLBACKEND": "Agg"}
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "workspace_scenarios.py"), "--scenario", scenario,
         "--port", str(port), "--language", language, "--theme", theme],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    target = out_dir / f"{name}.png"
    try:
        _wait(port)
        node_env = {**os.environ}
        try:
            root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True,
                                  check=False).stdout.strip()
            node_env["NODE_PATH"] = root
        except FileNotFoundError:
            pass
        result = subprocess.run(
            ["node", str(ROOT / "tools" / "capture_workspace.js"), f"http://127.0.0.1:{port}/",
             str(target), str(width), str(height), str(scale), str(wait_ms)],
            cwd="/tmp" if os.name != "nt" else None, env=node_env, capture_output=True,
            text=True, timeout=300, check=False)
        if result.returncode:
            return {"name": name, "ok": False, "problems": [result.stderr[-400:]]}
    finally:
        server.kill()
    try:
        from PIL import Image

        with Image.open(target) as image:
            # 256-colour palette keeps review screenshots small in Git.
            compact = image.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        compact.save(target, optimize=True)
    except Exception:
        pass
    problems = check_image(target)
    return {"name": name, "scenario": scenario, "size": [width, height], "scale": scale,
            "language": language, "theme": theme, "ok": not problems, "problems": problems}


def compose(out_dir: Path) -> None:
    """Before/after pairs for the review document."""
    from PIL import Image, ImageDraw

    for before, after, target in (("classic_home", "home_light", "compare_home"),
                                  ("classic_groups", "results_detail", "compare_groups")):
        a, b = out_dir / f"{before}.png", out_dir / f"{after}.png"
        if not (a.is_file() and b.is_file()):
            continue
        with Image.open(a) as left, Image.open(b) as right:
            height = min(left.height, right.height, 1800)
            left = left.crop((0, 0, left.width, height)).convert("RGB")
            right = right.crop((0, 0, right.width, height)).convert("RGB")
            canvas = Image.new("RGB", (left.width + right.width + 24, height + 44), "#FFFFFF")
            canvas.paste(left, (0, 44))
            canvas.paste(right, (left.width + 24, 44))
            draw = ImageDraw.Draw(canvas)
            draw.text((12, 14), "Before: classic interface", fill="#1A202C")
            draw.text((left.width + 36, 14), "After: Stage 33 workspace preview", fill="#1A202C")
            canvas = canvas.resize((canvas.width // 2, canvas.height // 2))
            canvas.quantize(colors=256).save(out_dir / f"{target}.png", optimize=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--wait", type=int, default=9000)
    parser.add_argument("--check-only", action="store_true",
                        help="re-check existing PNGs without capturing")
    args = parser.parse_args(argv)
    args.out = args.out.resolve()  # the browser runs from another directory
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "screenshots.json"
    try:
        previous = {item["name"]: item for item in json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        previous = {}
    report = []
    for entry in MATRIX:
        if args.only and entry[0] not in args.only:
            if entry[0] in previous:
                report.append(previous[entry[0]])
            continue
        if args.check_only:
            name, scenario, width, height, scale, language, theme = entry
            problems = check_image(args.out / f"{name}.png")
            outcome = {"name": name, "scenario": scenario, "size": [width, height],
                       "scale": scale, "language": language, "theme": theme,
                       "ok": not problems, "problems": problems}
        else:
            outcome = capture(entry, args.out, args.wait)
        report.append(outcome)
        print(("ok   " if outcome["ok"] else "FAIL ") + outcome["name"], *outcome["problems"])
    compose(args.out)
    path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0 if all(item["ok"] for item in report) else 1


if __name__ == "__main__":
    sys.exit(main())
