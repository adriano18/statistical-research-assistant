"""Real-browser checks that the workspace keeps the researcher's place.

    python tools/workspace_state_checks.py workspace-screenshots/state

Each check serves a scenario from ``tools/workspace_scenarios.py`` in a Flet
web preview and drives it with ``tools/e2e_web_state.js`` (Playwright
Chromium, through Flutter's accessibility tree) the way a person would:
scroll and tick a checkbox, type into a field, select item 60 of a
120-item questionnaire and edit it, open a section and tick inside it. The
page must not jump, lose the keyboard focus or the typed text, or close the
section. Fictional data only. Stage 34.5, issue #30.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(_path))

from workspace_screenshot_suite import _free_port, _wait, check_image  # noqa: E402

TOLERANCE = 30   # px a re-laid-out row may shift (scrollbar, fonts)


def _near(value) -> bool:
    return value is not None and abs(value) <= TOLERANCE


def _import_120_args() -> list[str]:
    """Item 60 of the synthetic 120-item import, its wording field, item 1."""
    sys.path.insert(0, str(ROOT / "tests"))
    from synthetic_documents import strain_statements
    from workspace_text import T

    statements = strain_statements(120)
    return [f"60. {statements[59][:28]}", T["imp.edit_wording"][0], f"1. {statements[0][:20]}"]


def _labels(*keys: str):
    def arguments() -> list[str]:
        from workspace_text import T

        return [T[key][0] for key in keys]
    return arguments


# name, scenario, mode, text (or a function giving the arguments), what must hold
CHECKS = (
    ("results-scroll-then-check", "results", "scroll", "",
     lambda r: _near(r["moved_by"]) and r["checked_after"] == "true"),
    ("reports-type-title", "reports", "type", "Fictional stress study",
     lambda r: r["kept_everything"]),
    ("questionnaire-120-item-60", "questionnaire-120", "list", "Fictional statement 60.",
     lambda r: _near(r["moved_by"]) and r["kept_typing"]),
    ("results-section-stays-open", "results", "expand", "Interpretation",
     lambda r: r["still_open"]),
    ("import-120-item-60", "import-120", "list", _import_120_args,
     lambda r: _near(r["moved_by"]) and r["kept_typing"]),
    # A button that changes kind is patched, not replaced: it must still draw.
    ("results-add-report-twice", "results", "toggle", _labels("results.add_report",
                                                              "results.in_report"),
     lambda r: r["found_after"] and not r["image_problems"]),
    # The status line is announced to screen readers (selectable text needs
    # an explicit accessible name; found by the packaged-EXE journeys).
    ("data-status-announced", "data", "announce",
     _labels("data.accept_confirm", "data.accept_suggestions"),
     lambda r: any("levels confirmed from suggestions" in said for said in r["announced"])),
)


def run(check, out: Path) -> dict:
    name, scenario, mode, text, holds = check
    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "workspace_scenarios.py"), "--scenario", scenario,
         "--port", str(port), "--language", "en"],
        cwd=ROOT, env={**os.environ, "MPLBACKEND": "Agg"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    target = out / f"{name}.json"
    try:
        _wait(port)
        env = {**os.environ}
        try:
            env["NODE_PATH"] = subprocess.run(["npm", "root", "-g"], capture_output=True,
                                              text=True, check=False).stdout.strip()
        except FileNotFoundError:
            pass
        arguments = text() if callable(text) else ([text] if text else [])
        command = ["node", str(ROOT / "tools" / "e2e_web_state.js"), mode,
                   f"http://127.0.0.1:{port}/", str(target)] + arguments
        result = subprocess.run(command, cwd="/tmp" if os.name != "nt" else None, env=env,
                                capture_output=True, text=True, timeout=400, check=False)
    finally:
        server.kill()
    if result.returncode or not target.is_file():
        return {"name": name, "ok": False, "problem": (result.stderr or result.stdout)[-600:]}
    measured = json.loads(target.read_text(encoding="utf-8"))
    if measured.get("screenshot"):
        measured["image_problems"] = check_image(Path(measured["screenshot"]))
    return {"name": name, "scenario": scenario, "mode": mode, "ok": bool(holds(measured)),
            "measured": measured}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = []
    for check in CHECKS:
        if args.only and check[0] not in args.only:
            continue
        outcome = run(check, out)
        report.append(outcome)
        print(("ok   " if outcome["ok"] else "FAIL ") + outcome["name"],
              json.dumps(outcome.get("measured") or outcome.get("problem")))
    (out / "state-checks.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0 if report and all(item["ok"] for item in report) else 1


if __name__ == "__main__":
    sys.exit(main())
