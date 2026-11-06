"""Real-browser checks that the workspace keeps the researcher's place.

    python tools/workspace_state_checks.py workspace-screenshots/state

Each check serves a scenario from ``tools/workspace_scenarios.py`` in a Flet
web preview and drives it with ``tools/e2e_web_state.js`` (Playwright
Chromium, through Flutter's accessibility tree) the way a person would:
scroll and tick a checkbox, type into a field, select item 60 of a
120-item questionnaire and edit it, open a section and tick inside it. The
page must not jump, lose the keyboard focus or the typed text, or close the
section. Fictional data only. Stage 34.5, issue #30.

The pointer checks hover one control of each clickable kind (sidebar item,
context chip, journey step, result card, buttons, segmented switch,
checkbox, section header, wizard step, item row, sticky footer): each must
show a pointer cursor and a visible hover state, and a disabled button must
not offer a pointer. Issue #32.
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


def _labels_with(prefix: str, button: str, expected: str):
    """A button named exactly (``prefix`` "=") and the text it must bring."""
    def arguments() -> list[str]:
        from workspace_text import T

        return [prefix + T[button][0], T[expected][0][:40]]
    return arguments


def _labels(*keys: str):
    def arguments() -> list[str]:
        from workspace_text import T

        return [T[key][0] for key in keys]
    return arguments


def _clickable_kinds() -> list[str]:
    """One control of each clickable kind on the Results page (role:label)."""
    from workspace_text import T

    return [
        f"button:={T['nav.data'][0]}",                       # sidebar item
        f"button:{T['context.open_data_tip'][0]}",            # context bar chip
        f"button:{T['journey.data.tip'][0][:30]}",            # research journey step
        "button:Independent-group comparison",                # result in the list
        f"button:{T['results.add_report'][0]}",               # secondary button
        "button:=LV",                                         # segmented switch
        "checkbox:Confirm independent participants",          # checkbox
        f"button:{T['results.interpretation'][0]}",           # section header
        f"button:{T['results.save_docx'][0]}",                # export button
    ]


def _import_clickable_kinds() -> list[str]:
    """The import wizard's step buttons, an item row, the filter and the footer."""
    sys.path.insert(0, str(ROOT / "tests"))
    from synthetic_documents import strain_statements
    from workspace_text import T

    return [
        f"button:1. {T['imp.step.source'][0]}",              # wizard step
        f"button:1. {strain_statements(120)[0][:20]}",        # item row
        f"button:{T['imp.filter.all'][0].split(' (')[0]} (",  # filter switch
        f"button:={T['imp.next'][0]}",                       # sticky footer
        f"!button:{T['imp.create_draft'][0]}",               # disabled until reviewed
    ]


def _pointer_everywhere(result) -> bool:
    """Every clickable control shows a pointer and a hover state; a disabled
    one (a target starting with "!") does not offer a pointer."""
    def fine(control) -> bool:
        if not control["found"]:
            return False
        if control.get("negative"):
            return control["cursor"] != "pointer"
        return (control["cursor"] == "pointer" and control["hover_visible"]
                and control["resting_cursor"] != "pointer")

    controls = result["controls"]
    return bool(controls) and all(fine(control) for control in controls)


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
    # Anything that can be clicked shows a pointer and a hover state (#32).
    ("results-pointer-affordances", "results", "affordance", _clickable_kinds,
     _pointer_everywhere),
    ("import-pointer-affordances", "import-120", "affordance", _import_clickable_kinds,
     _pointer_everywhere),
    # Open on Home opens the project (a lambda around the coroutine did nothing).
    ("projects-open-from-home", "projects", "effect",
     _labels_with("=", "project.open", "project.dashboard_subtitle"),
     lambda r: not r["shown_before"] and r["shown_after"]),
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
