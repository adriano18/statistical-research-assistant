"""Inventory every screen, command and input of the CLASSIC interface.

Usage::

    python tools/ux_inventory.py            # print a summary
    python tools/ux_inventory.py --json out.json --markdown out.md

The script builds the real classic workspace (``research_app.main``) on a
lightweight fake page — the same code path the desktop executable runs — and
walks the resulting Flet control tree. Nothing is guessed from source text:
a command appears in the inventory only if a control for it exists.

Stage 33 uses the result to prove feature parity: every classic screen, menu
command and registered action must have a destination in
``workspace_routes.ROUTE_MAP`` (see ``tests/test_workspace_routes.py``).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402

# Order of the classic screens as built by interface_layout.build_interface.
CLASSIC_SCREENS = (
    "home", "dataset", "preparation", "survey", "descriptive", "reliability",
    "factor", "correlation", "matrix", "groups", "paired", "chi", "omnibus",
    "regression", "logistic", "ancova", "repeated",
)
SURVEY_VIEWS = ("build", "preview", "fill", "responses")


class _Window(SimpleNamespace):
    async def center(self):
        return None


class FakePage:
    """Just enough of ``ft.Page`` to build controls without a client."""

    def __init__(self, width: int = 1280):
        self.controls: list = []
        self.services: list = []
        self.overlay: list = []
        self.window = _Window()
        self.web = False
        self.width = width
        self.height = 800
        self._services = SimpleNamespace(
            register_service=lambda service: None,
            unregister_services=lambda: None,
        )

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self, *args):
        return None


def build_classic(page: FakePage | None = None, captured: dict | None = None):
    """Build the classic workspace on ``page``; return (page, root)."""
    from flet.controls.context import _context_page
    import research_app

    page = page or FakePage()
    original = research_app.build_interface

    def spy(page_, controls, actions, **kwargs):
        if captured is not None:
            captured["controls"] = controls
            captured["actions"] = actions
        return original(page_, controls, actions, **kwargs)

    token = _context_page.set(page)
    research_app.build_interface = spy
    try:
        asyncio.run(research_app.main(page))
    finally:
        research_app.build_interface = original
        _context_page.reset(token)
    return page, page.controls[0]


def _text_of(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, ft.Text):
        return _text_of(value.value)
    for name in ("content", "title", "label"):
        inner = getattr(value, name, None)
        if inner is not None and inner is not value:
            found = _text_of(inner)
            if found:
                return found
    controls = getattr(value, "controls", None)
    if isinstance(controls, list):
        return " ".join(t for t in (_text_of(c) for c in controls) if t)
    return ""


def _children(control):
    if not dataclasses.is_dataclass(control):
        return
    for field in dataclasses.fields(control):
        if field.name.startswith("_") or field.name in {"data", "parent"}:
            continue
        value = getattr(control, field.name, None)
        if isinstance(value, ft.BaseControl):
            yield value
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, ft.BaseControl):
                    yield item


def walk(control, visit, depth=0, seen=None):
    seen = set() if seen is None else seen
    if control is None or id(control) in seen or depth > 80:
        return
    seen.add(id(control))
    visit(control, depth)
    for child in _children(control):
        walk(child, visit, depth + 1, seen)


def describe(control) -> dict | None:
    """A compact, human-readable record for one interactive control."""
    kind = type(control).__name__
    if isinstance(control, (ft.MenuItemButton, ft.SubmenuButton)):
        return None  # handled by the menu inventory
    if isinstance(control, ft.Dropdown):
        return {
            "type": "choice", "control": kind,
            "label": _text_of(control.label),
            "options": [_text_of(o.text) or str(o.key) for o in control.options or []],
        }
    if isinstance(control, (ft.Checkbox, ft.Switch)):
        return {"type": "confirmation" if "confirm" in _text_of(control.label).lower()
                or "i reviewed" in _text_of(control.label).lower() else "toggle",
                "control": kind, "label": _text_of(control.label)}
    if isinstance(control, ft.TextField):
        return {"type": "input", "control": kind, "label": _text_of(control.label)}
    if isinstance(control, ft.RadioGroup):
        return {"type": "choice", "control": kind, "label": _text_of(control.content)}
    if isinstance(control, ft.ExpansionTile):
        return {"type": "section", "control": kind, "label": _text_of(control.title)}
    if isinstance(control, ft.DataTable):
        return {"type": "table", "control": kind,
                "label": ", ".join(_text_of(c.label) for c in control.columns or [])}
    if isinstance(control, ft.IconButton):
        return {"type": "command", "control": kind,
                "label": _text_of(control.tooltip) or str(control.icon)}
    if isinstance(control, (ft.Button, ft.TextButton, ft.OutlinedButton,
                            ft.FilledButton, ft.FilledTonalButton)):
        label = _text_of(control.content)
        if control.action is not None and not label:
            label = type(control.action).__name__
        lowered = label.lower()
        if lowered.startswith(("open", "import", "load", "pickfiles")):
            kind_name = "import"
        elif any(word in lowered for word in ("save", "export", "copy", "download")):
            kind_name = "export"
        else:
            kind_name = "command"
        return {"type": kind_name, "control": kind, "label": label}
    if isinstance(control, ft.Text) and isinstance(control.value, str):
        size = control.size or 14
        bold = str(control.weight or "").lower() in {"bold", "w600", "w700", "fontweight.bold"}
        if size >= 16 or (bold and len(control.value) < 90):
            return {"type": "heading", "control": kind, "label": _text_of(control.value)}
    return None


def screen_inventory(screen) -> dict:
    items: list[dict] = []

    def visit(control, depth):
        record = describe(control)
        if record and record["label"]:
            items.append(record)

    walk(screen, visit)
    summary: dict[str, list] = {}
    for record in items:
        summary.setdefault(record["type"], []).append(
            {k: v for k, v in record.items() if k != "type"}
        )
    return summary


def menu_inventory(root) -> list[dict]:
    groups: list[dict] = []

    def visit(control, depth):
        if isinstance(control, ft.SubmenuButton):
            groups.append({
                "group": _text_of(control.content),
                "commands": [_text_of(item.content) for item in control.controls or []
                             if isinstance(item, ft.MenuItemButton)],
            })

    walk(root, visit)
    return groups


def collect_inventory() -> dict:
    captured: dict = {}
    page, root = build_classic(captured=captured)
    workspace = root.controls[1].content
    screens_column = workspace.controls[-1]
    screens = list(screens_column.controls)
    if len(screens) != len(CLASSIC_SCREENS):
        raise RuntimeError(
            f"Expected {len(CLASSIC_SCREENS)} classic screens, found {len(screens)}"
        )
    labels = _screen_labels(workspace)
    inventory = {
        "generated_by": "tools/ux_inventory.py",
        "screens": [],
        "menu": menu_inventory(root),
        "actions": sorted(captured.get("actions", {})),
        "controls": sorted(captured.get("controls", {})),
    }
    for index, (key, screen) in enumerate(zip(CLASSIC_SCREENS, screens)):
        inventory["screens"].append({
            "key": key,
            "label": labels.get(key, key),
            **screen_inventory(screen),
        })
    survey = captured["controls"]["survey_panel"]
    views = [c for c in survey.controls if isinstance(c, ft.Column)][:len(SURVEY_VIEWS)]
    inventory["survey_views"] = [
        {"key": key, **screen_inventory(view)} for key, view in zip(SURVEY_VIEWS, views)
    ]
    return inventory


def _screen_labels(workspace) -> dict[str, str]:
    """Screen key → label, read from the compact "Go to workspace" picker."""
    for control in workspace.controls:
        if isinstance(control, ft.Dropdown) and control.options and {
            str(o.key) for o in control.options
        } == set(CLASSIC_SCREENS):
            return {str(o.key): _text_of(o.text) for o in control.options}
    raise RuntimeError("Classic screen picker not found")


def to_markdown(inventory: dict) -> str:
    lines = [
        "# Classic interface inventory (generated)",
        "",
        "Generated by `python tools/ux_inventory.py --markdown …` from the real "
        "control tree of the classic workspace. Do not edit by hand.",
        "",
        "| Screen key | Sidebar label | Commands | Imports | Exports | Choices | "
        "Inputs | Confirmations | Sections |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for screen in inventory["screens"]:
        count = lambda name: len(screen.get(name, []))  # noqa: E731
        lines.append(
            f"| `{screen['key']}` | {screen['label']} | {count('command')} | "
            f"{count('import')} | {count('export')} | {count('choice')} | {count('input')} | "
            f"{count('confirmation')} | {count('section')} |"
        )
    lines += ["", "## Top menu", ""]
    for group in inventory["menu"]:
        lines.append(f"- **{group['group']}**: " + "; ".join(group["commands"]))
    lines += ["", "## Registered classic actions", "",
              ", ".join(f"`{a}`" for a in inventory["actions"]), ""]
    for screen in inventory["screens"] + [
        {**v, "key": f"survey/{v['key']}", "label": f"Questionnaire · {v['key']}"}
        for v in inventory["survey_views"]
    ]:
        lines += ["", f"## `{screen['key']}` — {screen['label']}", ""]
        for kind in ("heading", "command", "import", "export", "choice", "input",
                     "confirmation", "toggle", "section", "table"):
            entries = screen.get(kind, [])
            if not entries:
                continue
            seen = []
            for entry in entries:
                text = entry["label"]
                if kind == "choice" and entry.get("options"):
                    shown = entry["options"][:8]
                    more = len(entry["options"]) - len(shown)
                    text += " — " + ", ".join(shown) + (f" (+{more})" if more > 0 else "")
                if text not in seen:
                    seen.append(text)
            lines.append(f"- **{kind}** ({len(seen)}): " + " · ".join(seen))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    inventory = collect_inventory()
    if args.json:
        args.json.write_text(json.dumps(inventory, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(to_markdown(inventory), encoding="utf-8")
    if not args.json and not args.markdown:
        for screen in inventory["screens"]:
            print(f"{screen['key']:<12} {screen['label']:<22} "
                  f"commands={len(screen.get('command', []))} "
                  f"exports={len(screen.get('export', []))} "
                  f"inputs={len(screen.get('choice', [])) + len(screen.get('input', []))}")
        print("menu:", [g["group"] for g in inventory["menu"]])
        print("actions:", len(inventory["actions"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
