"""Stage 37 (Issue #68): the measured interaction cost of eight research tasks.

A reproducible measurement aid, not part of the application or of the
installer. It starts the program the way a researcher does (the real
``research_app.main``, then the workspace if the classic interface opens
first) and drives the REAL handlers through ``tests/workspace_harness.py``,
with the counting rule of ``tests/test_stage36_ux_baseline.py`` and
``docs/stage37/measure_baseline.py``:

* **interactions**: a click or a checkbox counts 1, a dropdown choice 2 (open
  the list, pick the entry). An expansion tile, one segment of a segmented
  switch and the classic Home's button into the workspace (*Open the preview*,
  *Open the research workspace* since Stage 37) are clicks.
* **typed fields**: each text field the researcher types into, once (apart).
* **page changes**: every change of page, also one a handler makes (loading
  a file opens Data, a run opens Results), and the switch from the classic
  interface to the workspace (apart).
* **system dialogs**: the Windows Open and Save dialogs (apart).
* **repeated variable selections**: a variable ticked or picked in a
  dropdown that had already been put into a role earlier in the chain of
  tasks (the same items ticked again for reliability after scoring, …).
  Variables a quick-select button adds are remembered, not counted.
* **focus losses**: a text field or dropdown the researcher is operating
  that a re-render rebuilds. Flet 1.x keeps the Flutter widget (and so the
  keyboard focus and caret) when the control keeps its place in the tree:
  the same type at the same position among unkeyed siblings, or the same
  explicit key (``flet/controls/object_patch.py``). A focus loss is counted
  when the interaction re-rendered the page and the field's place changed
  or the field disappeared, on the same page.
* **scroll (estimate)**: scrolling cannot be measured in the harness, which
  has no client to lay out the page. The estimate lays each page out from
  control counts and nominal heights (``Layout``: tokens of
  ``workspace_tokens``, 40-px controls, 56-px fields, table rows as
  declared, wrapped rows of checkboxes by label width) and adds the distance
  the page must move so that each control used comes into view, plus, for
  the content a task reads (the 98-row dictionary, a result), the distance
  to its end. An inner list with its own height scrolls apart from the page
  (the mouse wheel over it moves the list, not the page). It is an
  estimate, never a measurement, and is labelled so wherever it is shown.

The eight tasks, four of a novice and four of a supervisor, are one chain
in one project, on synthetic data only: the Stage 37 master fixture (180
fictional cases, 98 columns, generated into a temporary folder by
``tests/fixtures/stage37/generate_master_fixture.py``) and the Stage 36
UCLA/SACS-shaped CSV (``tests/fixtures/stage36``).

    Session 1, novice, first start
      T1 first start to an open project with data (master CSV)
      T2 confirm the measurement levels of the 98 variables
      T3 define and score one 20-item scale and check its reliability
      -- set-up, not counted: the Stage 36 CSV is opened in the project and
         its 13 levels are confirmed (as in the Stage 36 baseline)
      T4 eight correlations in one batch, added to the report
    Session 2, supervisor, after a restart
      T7 reopen the project and review every result
      T5 repeat a previous analysis with one variable changed
      T6 export the Word report
      T8 change the language and the text size, and continue
    Session 3, the next start: T8 continues (are the choices kept?)

Every task checks that it produced what it names (the project, the levels,
the score and its α, the batch, the new run, the Word file, the language),
so a shortcut that skips a needed step cannot hide in a count. Projects and
settings live in a temporary folder; nothing in the repository or in the
user's data changes, and nothing goes to the network.

Run from the repository root::

    python tools/ux_metrics.py [--json out.json] [--markdown out.md]
                               [--width 1440] [--height 800]
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import contextlib
import dataclasses
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from test_stage36_ux_baseline import LEVELS as STAGE36_LEVELS, CountingWorkspace  # noqa: E402
from workspace_harness import FakePage  # noqa: E402
import workspace_tokens as tk  # noqa: E402

MASTER_GENERATOR = ROOT / "tests" / "fixtures" / "stage37" / "generate_master_fixture.py"
PROJECT_TITLE = "Fictional master study"
LON_ITEMS = tuple(f"SYN_LON_{n:02d}" for n in range(1, 21))
LON_SCORE = "SYN_LON_MEAN"
STATUS_BAR = 30.0          # the status line under the page (13-px text, 6-px padding)
PERSONAS = {"T1": "novice", "T2": "novice", "T3": "novice", "T4": "novice",
            "T5": "supervisor", "T6": "supervisor", "T7": "supervisor", "T8": "supervisor"}
TASKS = {
    "T1": "First start to an open project with data",
    "T2": "Confirm the measurement levels of the 98-variable file",
    "T3": "Define and score one 20-item scale, check its reliability",
    "T4": "Eight correlations in one batch, add them to the report",
    "T5": "Repeat a previous analysis with one variable changed",
    "T6": "Export the Word report",
    "T7": "Reopen the project after a restart, review every result",
    "T8": "Change the language and the text size, continue",
}
ORDER = ("T1", "T2", "T3", "T4", "T7", "T5", "T6", "T8")     # the order they run in


def commit() -> str:
    """The checkout measured (its short commit), for the printed tables."""
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip() or "this checkout"
    except (OSError, subprocess.CalledProcessError):
        return "this checkout"


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def stable(label: str) -> str:
    """A step label without the run's random project and task ids."""
    return _UUID.sub("<id>", label or "")


# ======================================================================= fixtures
def generate_fixtures(folder: Path) -> dict[str, Path]:
    """The synthetic master CSV (stdlib generator) and the Stage 36 CSV, in ``folder``."""
    spec = importlib.util.spec_from_file_location("stage37_master_fixture", MASTER_GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    master, _model = module.generate(folder / "stage37")
    (folder / "stage36").mkdir(parents=True, exist_ok=True)
    stage36 = fx.generator().create_csv(folder / "stage36")
    return {"master": Path(master), "stage36": Path(stage36)}


def master_levels(columns) -> dict[str, str]:
    """The levels a careful researcher confirms for the master fixture: the
    code identifies, age and the derived scores are quantitative, sex and
    employment are categories, every item is an ordered answer."""
    levels = {}
    for name in columns:
        if name == "participant_code":
            levels[name] = "id"
        elif name in ("sex_code", "employed_code"):
            levels[name] = "nominal"
        elif name == "age_years" or name.endswith(("_TOTAL", "_MEAN", "_RAW", "_0_100")):
            levels[name] = "scale"
        else:
            levels[name] = "ordinal"
    return levels


# ================================================================ layout (estimate)
CHAR_EM = 0.52      # average advance of Segoe UI glyphs in Latin text, in em
LINE_EM = 1.4       # line height where a text sets none, in em
BUTTONS = tuple(getattr(ft, name) for name in (
    "Button", "TextButton", "OutlinedButton", "FilledButton", "FilledTonalButton")
    if hasattr(ft, name))


def _num(value, default=None):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) \
        else default


def _edges(value) -> tuple[float, float, float, float]:
    if value is None:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(value, (int, float)):
        return (float(value),) * 4
    return tuple(float(getattr(value, side, 0) or 0)
                 for side in ("left", "top", "right", "bottom"))


def _label(value) -> str:
    if isinstance(value, str):
        return value
    inner = getattr(value, "value", None)
    return inner if isinstance(inner, str) else ""


def _visible(control) -> bool:
    return control is not None and getattr(control, "visible", True) is not False


def _text_width(text: str, size: float) -> float:
    return len(text) * size * CHAR_EM


class Layout:
    """Estimated geometry of one page: ``boxes[id(control)] = (scroller, y, h)``.

    ``scroller`` is ``None`` for the page's own scrolling, or ``id()`` of an
    inner list that scrolls by itself (a Column or ListView with a height
    and a scroll mode); ``y`` is then measured inside that list. Heights come
    from the controls (declared heights, table row heights, text length and
    size) and from nominal Material sizes where a control declares none. An
    estimate: Flutter's real layout is never run here.
    """

    def __init__(self, root, width: float, page_width: float | None = None):
        self.boxes: dict[int, tuple[int | None, float, float]] = {}
        self.inner: dict[int, tuple[float, float]] = {}     # id → (visible, content) height
        # ResponsiveRow chooses its breakpoint by the window's width.
        self.page_width = float(page_width or width)
        self.height = self.place(root, 0.0, float(width), None)

    def place(self, control, y: float, width: float, scroller) -> float:
        if not _visible(control):
            return 0.0
        height = self._measure(control, y, max(1.0, width), scroller)
        self.boxes[id(control)] = (scroller, y, height)
        return height

    # ----------------------------------------------------------- controls
    def _measure(self, c, y, width, scroller) -> float:
        if isinstance(c, ft.Text):
            return self._text(c, width)
        if isinstance(c, ft.TextField):
            if getattr(c, "multiline", False):
                lines = sum(max(1, math.ceil(_text_width(line, 14) / max(40.0, width - 24)))
                            for line in (c.value or "").split("\n"))
                lines = max(int(c.min_lines or 1), min(lines, int(c.max_lines or lines)))
                return 20.0 * lines + 36.0
            return 56.0
        if isinstance(c, ft.Dropdown):
            return 48.0 if getattr(c, "dense", False) else 56.0
        if isinstance(c, ft.Checkbox):
            lines = math.ceil(_text_width(_label(c.label), 14) / max(40.0, width - 48))
            return max(40.0, 20.0 * lines)
        if isinstance(c, ft.IconButton) or isinstance(c, BUTTONS):
            return _num(c.height, 40.0)
        if isinstance(c, ft.Icon):
            return _num(c.size, 24.0)
        if isinstance(c, ft.Image):
            return _num(c.height, 200.0)
        if isinstance(c, ft.Divider):
            return _num(c.height, 16.0)
        if isinstance(c, ft.ProgressRing):
            return _num(c.height, 36.0)
        if isinstance(c, ft.DataTable):
            return self._table(c, y, width, scroller)
        if isinstance(c, ft.ExpansionTile):
            return self._tile(c, y, width, scroller)
        if isinstance(c, ft.Container):
            return self._container(c, y, width, scroller)
        if isinstance(c, ft.ResponsiveRow):
            return self._responsive(c, y, width, scroller)
        if isinstance(c, ft.Row):
            return self._row(c, y, width, scroller)
        if isinstance(c, (ft.Column, ft.ListView)):
            return self._column(c, y, width, scroller)
        if isinstance(c, ft.Stack):
            return max([self.place(child, y, width, scroller) for child in c.controls] or [0.0])
        content = getattr(c, "content", None)
        if isinstance(content, ft.BaseControl):
            return self.place(content, y, width, scroller)
        controls = getattr(c, "controls", None)
        if isinstance(controls, list):
            return self._stack_vertically(controls, y, width, scroller, 0.0)
        return _num(getattr(c, "height", None), 24.0)

    @staticmethod
    def _text(c, width) -> float:
        size = _num(c.size, 14.0)
        style = getattr(c, "style", None)
        factor = _num(getattr(style, "height", None), LINE_EM) if style is not None else LINE_EM
        value = c.value if isinstance(c.value, str) else ""
        lines = sum(max(1, math.ceil(_text_width(line, size) / width))
                    for line in value.split("\n")) if value else 1
        if c.max_lines:
            lines = min(lines, int(c.max_lines))
        return lines * size * factor

    def _stack_vertically(self, controls, y, width, scroller, spacing) -> float:
        offset, first = y, True
        for child in controls:
            if not _visible(child):
                continue
            if not first:
                offset += spacing
            offset += self.place(child, offset, width, scroller)
            first = False
        return offset - y

    def _column(self, c, y, width, scroller) -> float:
        default = 0.0 if isinstance(c, ft.ListView) else 10.0
        spacing = _num(c.spacing, default)
        fixed = _num(c.height)
        if fixed is not None and getattr(c, "scroll", None) is not None:
            # An inner list: its items are placed inside it, from its top.
            content = self._stack_vertically(c.controls, 0.0, width, id(c), spacing)
            self.inner[id(c)] = (fixed, content)
            return fixed
        height = self._stack_vertically(c.controls, y, width, scroller, spacing)
        return fixed if fixed is not None else height

    def _container(self, c, y, width, scroller) -> float:
        ml, mt, mr, mb = _edges(getattr(c, "margin", None))
        pl, pt, pr, pb = _edges(c.padding)
        outer = _num(c.width, width)
        limit = _num(getattr(getattr(c, "constraints", None), "max_width", None))
        if limit is not None and math.isfinite(limit):
            outer = min(outer, limit)
        inner = max(1.0, min(outer, width) - ml - mr - pl - pr)
        content = self.place(c.content, y + mt + pt, inner, scroller) if c.content else 0.0
        fixed = _num(c.height)
        return (fixed if fixed is not None else content + pt + pb) + mt + mb

    def _row(self, c, y, width, scroller) -> float:
        children = [child for child in c.controls if _visible(child)]
        if not children:
            return 0.0
        spacing = _num(c.spacing, 10.0)
        if getattr(c, "wrap", False):
            run_spacing = _num(c.run_spacing, 10.0)
            lines: list[list] = [[]]
            used = 0.0
            for child in children:
                w = min(width, self.intrinsic(child, width))
                if lines[-1] and used + spacing + w > width:
                    lines.append([])
                    used = 0.0
                used += (spacing if lines[-1] else 0.0) + w
                lines[-1].append((child, w))
            total = 0.0
            for line in lines:
                total += max(self.place(child, y + total, w, scroller) for child, w in line)
                total += run_spacing
            return max(0.0, total - run_spacing)
        flexible = [child for child in children if getattr(child, "expand", None)]
        fixed = sum(min(width, self.intrinsic(child, width)) for child in children
                    if child not in flexible) + spacing * (len(children) - 1)
        remaining = max(1.0, width - fixed)
        weights = sum(int(child.expand) if not isinstance(child.expand, bool) else 1
                      for child in flexible) or 1
        height = 0.0
        for child in children:
            if child in flexible:
                weight = int(child.expand) if not isinstance(child.expand, bool) else 1
                w = remaining * weight / weights
            else:
                w = min(width, self.intrinsic(child, width))
            height = max(height, self.place(child, y, w, scroller))
        return height

    @staticmethod
    def _span(child, width: float, columns: float) -> float:
        col = getattr(child, "col", None)
        if isinstance(col, (int, float)):
            return float(col)
        if isinstance(col, dict):
            spans = {str(getattr(k, "value", k)): v for k, v in col.items()}
            for name, minimum in (("xxl", 1400), ("xl", 1200), ("lg", 992), ("md", 768),
                                  ("sm", 576), ("xs", 0)):
                if width >= minimum and name in spans:
                    return float(spans[name])
        return columns

    def _responsive(self, c, y, width, scroller) -> float:
        columns = _num(getattr(c, "columns", None), 12.0)
        spacing = _num(c.spacing, 10.0)
        run_spacing = _num(c.run_spacing, 10.0)
        lines: list[list] = [[]]
        used = 0.0
        for child in c.controls:
            if not _visible(child):
                continue
            span = min(columns, self._span(child, self.page_width, columns))
            if lines[-1] and used + span > columns:
                lines.append([])
                used = 0.0
            used += span
            lines[-1].append((child, span))
        total = 0.0
        for line in lines:
            if not line:
                continue
            total += max(self.place(child, y + total, width * span / columns - spacing,
                                    scroller) for child, span in line)
            total += run_spacing
        return max(0.0, total - run_spacing)

    def _table(self, c, y, width, scroller) -> float:
        # Every table of the workspace sits in a horizontally scrolling row:
        # a column takes the width of its widest cell and text does not wrap.
        heading = _num(c.heading_row_height, 56.0)
        low = _num(c.data_row_min_height, 48.0)
        high = _num(c.data_row_max_height, max(low, 48.0))

        def unwrapped(control):
            return max(60.0, self.intrinsic(control, 10_000.0))

        for column in c.columns or []:
            label = getattr(column, "label", None)
            self.place(label, y, unwrapped(label), scroller)
        offset = y + heading
        for row in c.rows or []:
            tallest = 0.0
            for cell in row.cells or []:
                tallest = max(tallest, self.place(cell.content, offset, unwrapped(cell.content),
                                                  scroller))
                self.boxes[id(cell)] = (scroller, offset, 0.0)
            height = min(high, max(low, tallest + 16.0))
            self.boxes[id(row)] = (scroller, offset, height)
            for cell in row.cells or []:
                self.boxes[id(cell)] = (scroller, offset, height)
            offset += height
        return offset - y

    def _tile(self, c, y, width, scroller) -> float:
        header = 56.0 + (16.0 if c.subtitle is not None else 0.0)
        self.place(c.title, y + 8.0, width - 64.0, scroller)
        if c.subtitle is not None:
            self.place(c.subtitle, y + 32.0, width - 64.0, scroller)
        if not c.expanded:
            return header
        return header + self._stack_vertically(c.controls, y + header, width, scroller, 0.0)

    # ------------------------------------------------------ natural width
    def intrinsic(self, c, cap: float) -> float:
        if not _visible(c):
            return 0.0
        own = _num(getattr(c, "width", None))
        if own is not None:
            return min(cap, own)
        if isinstance(c, ft.Text):
            value = c.value if isinstance(c.value, str) else ""
            size = _num(c.size, 14.0)
            return min(cap, max([_text_width(line, size) for line in value.split("\n")] or [0]))
        if isinstance(c, BUTTONS):
            icon = 32.0 if getattr(c, "icon", None) else 0.0
            return min(cap, 32.0 + icon + _text_width(_label(c.content), 14))
        if isinstance(c, ft.IconButton):
            return 40.0
        if isinstance(c, ft.Checkbox):
            return min(cap, 48.0 + _text_width(_label(c.label), 14))
        if isinstance(c, (ft.Dropdown, ft.TextField)):
            return cap if getattr(c, "expand", None) else min(cap, 220.0)
        if isinstance(c, ft.Icon):
            return _num(c.size, 24.0)
        if isinstance(c, ft.Image):
            return min(cap, 200.0)
        if getattr(c, "expand", None):
            return cap
        if isinstance(c, ft.Container):
            pl, _, pr, _ = _edges(c.padding)
            ml, _, mr, _ = _edges(getattr(c, "margin", None))
            inner = self.intrinsic(c.content, cap - pl - pr - ml - mr) if c.content else 0.0
            return min(cap, inner + pl + pr + ml + mr)
        if isinstance(c, ft.ResponsiveRow):
            return cap
        if isinstance(c, ft.Row):
            children = [child for child in c.controls if _visible(child)]
            spacing = _num(c.spacing, 10.0) * max(0, len(children) - 1)
            return min(cap, sum(self.intrinsic(child, cap) for child in children) + spacing)
        if isinstance(c, (ft.Column, ft.ListView)):
            return min(cap, max([self.intrinsic(child, cap) for child in c.controls] or [0.0]))
        if isinstance(c, ft.DataTable):
            return min(cap, 140.0 * len(c.columns or []))
        content = getattr(c, "content", None)
        if isinstance(content, ft.BaseControl):
            return self.intrinsic(content, cap)
        return min(cap, 120.0)


# ======================================================== reconciliation (focus)
def _child_slots(control):
    """(field, key, child) for the children of ``control`` as Flet 1.x pairs
    them on a re-render: list items by explicit key, otherwise by position
    among the unkeyed items (``object_patch._compare_lists``, frozen mode,
    which applies under the workspace page's keyed column)."""
    from flet.controls.object_patch import get_control_key

    if not dataclasses.is_dataclass(control):
        return
    for field in dataclasses.fields(control):
        if field.name.startswith("_") or field.name in {"data", "parent"}:
            continue
        value = getattr(control, field.name, None)
        if isinstance(value, ft.BaseControl):
            yield field.name, None, value
        elif isinstance(value, (list, tuple)):
            unkeyed = 0
            for item in value:
                if not isinstance(item, ft.BaseControl):
                    continue
                key = get_control_key(item)
                if key is not None:
                    yield field.name, ("k", key), item
                else:
                    yield field.name, ("pos", unkeyed), item
                    unkeyed += 1


def reconciliation_path(root, target) -> tuple | None:
    """Where ``target`` sits in ``root`` for Flet's reconciliation: the type,
    field and list key of every step down to it. Two renders that give a
    control the same path keep its Flutter widget, and with it the keyboard
    focus and caret; a different path (or none) rebuilds it."""
    seen: set[int] = set()

    def visit(control, trail):
        if id(control) in seen or len(trail) > 120:
            return None
        seen.add(id(control))
        if control is target:
            return trail + (type(control).__name__,)
        for name, key, child in _child_slots(control):
            found = visit(child, trail + ((type(control).__name__, name, key),))
            if found is not None:
                return found
        return None

    return visit(root, ())


# ===================================================================== recording
@dataclasses.dataclass
class Segment:
    """One task, or the part of a task done in one program session."""

    task: str
    title: str
    session: int
    clicks: int = 0
    checks: int = 0
    dropdowns: int = 0          # choices; each counts 2 interactions
    typed: int = 0
    pages: list = dataclasses.field(default_factory=list)
    dialogs: list = dataclasses.field(default_factory=list)
    repeated: list = dataclasses.field(default_factory=list)
    focus_losses: list = dataclasses.field(default_factory=list)
    renders: int = 0
    scroll_px: float = 0.0
    unavailable: list = dataclasses.field(default_factory=list)
    facts: dict = dataclasses.field(default_factory=dict)
    steps: list = dataclasses.field(default_factory=list)

    @property
    def interactions(self) -> int:
        return self.clicks + self.checks + 2 * self.dropdowns


class Recorder:
    """The chain of tasks: segments in order and every variable put into a role."""

    def __init__(self):
        self.segments: list[Segment] = []
        self.selected: set[str] = set()
        self.sessions = 0

    @contextlib.contextmanager
    def task(self, meter: "Meter", task: str, title: str | None = None):
        segment = Segment(task, title or TASKS[task], meter.session)
        self.segments.append(segment)
        meter.segment = segment
        try:
            yield segment
        finally:
            meter.segment = None

    def results(self, *, width: int, height: int, viewport: float, measured: str) -> dict:
        tasks = []
        for key in sorted(TASKS):
            parts = [s for s in self.segments if s.task == key]
            if not parts:
                continue
            total = {
                "task": key, "title": TASKS[key], "persona": PERSONAS[key],
                "run_order": ORDER.index(key) + 1,
                "fixture": parts[0].facts.get("fixture", ""),
                "interactions": sum(p.interactions for p in parts),
                "clicks": sum(p.clicks for p in parts),
                "checkboxes": sum(p.checks for p in parts),
                "dropdowns": sum(p.dropdowns for p in parts),
                "typed": sum(p.typed for p in parts),
                "page_changes": sum(len(p.pages) for p in parts),
                "dialogs": sum(len(p.dialogs) for p in parts),
                "repeated_selections": sum(len(p.repeated) for p in parts),
                "focus_losses": sum(len(p.focus_losses) for p in parts),
                "renders": sum(p.renders for p in parts),
                "scroll_px_estimate": int(round(sum(p.scroll_px for p in parts))),
                "scroll_screens_estimate": round(sum(p.scroll_px for p in parts) / viewport, 1),
                "unavailable": [u for p in parts for u in p.unavailable],
                "segments": [{
                    "title": p.title, "session": p.session, "interactions": p.interactions,
                    "clicks": p.clicks, "checkboxes": p.checks, "dropdowns": p.dropdowns,
                    "typed": p.typed, "pages": list(p.pages), "dialogs": list(p.dialogs),
                    "repeated_selections": list(p.repeated),
                    "focus_losses": list(p.focus_losses), "renders": p.renders,
                    "scroll_px_estimate": int(round(p.scroll_px)),
                    "unavailable": list(p.unavailable), "facts": dict(p.facts),
                    "steps": list(p.steps)} for p in parts],
            }
            tasks.append(total)
        personas = {}
        for persona in ("novice", "supervisor"):
            rows = [t for t in tasks if t["persona"] == persona]
            personas[persona] = {name: sum(t[name] for t in rows) for name in (
                "interactions", "typed", "page_changes", "dialogs", "repeated_selections",
                "focus_losses", "scroll_px_estimate")}
        return {
            "measured": measured, "window": {"width": width, "height": height},
            "viewport_px_estimate": round(viewport), "tasks": tasks, "personas": personas,
            "rule": "click or checkbox 1, dropdown 2; typed fields, page changes, system "
                    "dialogs, repeated variable selections and focus losses apart; scroll "
                    "is an estimate from control counts and nominal heights",
        }


# ======================================================================== meter
class Meter(CountingWorkspace):
    """The harness's ``CountingWorkspace`` (click/checkbox 1, dropdown 2) with
    the Stage 37 observations: typed fields, page changes, system dialogs,
    repeated variable selections, focus losses, re-renders and the scroll
    estimate. Interactions outside a task (set-up) are not recorded."""

    def __init__(self, root: Path, recorder: Recorder, *, width: int = 1440, height: int = 800):
        # The program's own start, not the harness's direct WorkspaceApp: the
        # same data folder at every start (a restart), settings beside it.
        from flet.controls.context import _context_page
        import app_preferences
        import secret_store
        import workspace_shell

        self.rec = recorder
        recorder.sessions += 1
        self.session = recorder.sessions
        self.segment: Segment | None = None
        self.temp = None
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.counts: Counter = Counter()
        self.routes: list[str] = []
        self.saved: list[Path] = []
        self._patches = [
            mock.patch.dict(os.environ, {"SRA_DATA_DIR": str(self.root), "SRA_UI": ""}),
            mock.patch.object(app_preferences, "preferences_path",
                              lambda: self.root / "preferences.json"),
            mock.patch.object(workspace_shell, "workspace_settings_path",
                              lambda: self.root / "workspace.json"),
            # The computer's credential store is never read: as on a computer
            # without one (no AI key anywhere, nothing on the network).
            mock.patch.object(secret_store, "backend", side_effect=secret_store
                              .SecretStoreUnavailable("not used by the measurement")),
        ]
        for patch in self._patches:
            patch.start()
        self._settings = SimpleNamespace(stop=lambda: None)
        self.page = FakePage(width)
        self.page.height = height
        self._token = _context_page.set(self.page)
        self.app = None
        self.scroll: dict[str, float] = {}
        self._renders = 0
        self._route = "classic"
        self._section = None
        self._closed = False

    # ---------------------------------------------------------------- start
    def start(self) -> None:
        """``research_app.main`` on the page, as the packaged program runs it
        after its splash. If the classic interface opens, its *Open the
        preview* button is the researcher's first click (counted)."""
        import research_app
        from workspace_shell import active_app

        asyncio.run(research_app.main(self.page))
        root = self.page.controls[0] if self.page.controls else None
        classic = getattr(root, "data", None) != "workspace-root"
        if classic:
            entry = self.find("open-workspace-preview")
            if self.segment is not None:
                self.counts["click"] += 1
                self.segment.clicks += 1
                self.segment.steps.append("classic: Open the research workspace")
            self.dispatch(entry.on_click, SimpleNamespace(control=entry, data=None))
        self.app = active_app()
        ensure(self.app is not None and self.page.controls[0] is self.app.root,
               "the workspace did not open")
        self._attach()
        if not classic:
            self._route = self.app.route       # the workspace is the first page shown
        self.page_seen(start=True)

    def _attach(self) -> None:
        app = self.app
        render = app.render

        def counted_render():
            self._renders += 1
            return render()

        app.render = counted_render

        async def save_dialog(title, file_name, extension):
            path = self.root / "exports" / file_name
            path.parent.mkdir(parents=True, exist_ok=True)
            self.saved.append(path)
            if self.segment is not None:
                self.segment.dialogs.append(f"Save (.{extension})")
            return str(path)

        app.save_dialog = save_dialog

    def close(self):
        from flet.controls.context import _context_page

        if self._closed:
            return
        self._closed = True
        if self.app is not None:
            self.app.projects.close(clear=False)
        _context_page.reset(self._token)
        for patch in reversed(self._patches):
            patch.stop()

    # ---------------------------------------------------------- observation
    @property
    def viewport(self) -> float:
        return float(self.page.height) - (tk.CONTEXT_BAR_HEIGHT + 8) - STATUS_BAR \
            - 2 * tk.SPACE_5

    def layout(self) -> Layout | None:
        column = self.app.page_control if self.app is not None else None
        if column is None or not getattr(column, "controls", None):
            return None
        return Layout(column.controls[0], self.app.content_width, self.page.width)

    def page_seen(self, *, start: bool = False) -> None:
        """Record a change of page; a new page starts at its top, or at the
        section the program scrolls to (``navigate(section=…)``)."""
        app = self.app
        if app.route != self._route:
            if self.segment is not None:
                label = f"{self._route} → {app.route}" if start else app.route
                self.segment.pages.append(label)
            self._route = app.route
            self.scroll[app.route] = 0.0
            self._section = None
        section = getattr(app, "section", None)
        if section and section != self._section:
            self._section = section
            key = app.SECTION_KEYS.get((app.route, section))
            layout = self.layout()
            if key and layout is not None:
                target = self.find_where(lambda c: getattr(getattr(c, "key", None), "value",
                                                           None) == key)
                box = layout.boxes.get(id(target)) if target is not None else None
                if box is not None and box[0] is None:
                    self.scroll[app.route] = max(0.0, min(box[1], layout.height - self.viewport))

    def _move(self, start: float, height: float, total: float, *, read: bool = False,
              key: str | None = None, view: float | None = None) -> None:
        view = self.viewport if view is None else view
        key = key or self.app.route
        offset = min(self.scroll.get(key, 0.0), max(0.0, total - view))
        moved = 0.0
        if read:
            # Reading goes on downwards from where the researcher is: a part
            # already scrolled past counts as read, the rest is scrolled through.
            end = max(offset, start + height - view)
            moved += end - offset
            offset = end
        else:
            shown = min(height, view)
            if start < offset:
                moved += offset - start
                offset = start
            elif start + shown > offset + view:
                moved += start + shown - view - offset
                offset = start + shown - view
        self.scroll[key] = offset
        if self.segment is not None:
            self.segment.scroll_px += moved

    def bring_into_view(self, control, *, read: bool = False) -> None:
        """Scroll (estimated) until ``control`` is on screen, or, reading it,
        until its end has been on screen."""
        if self.segment is None or self.app is None:
            return
        layout = self.layout()
        box = layout.boxes.get(id(control)) if layout is not None else None
        if box is None:
            return
        scroller, y, h = box
        if scroller is None:
            self._move(y, h, layout.height, read=read)
            return
        outer = layout.boxes.get(scroller)
        if outer is not None and outer[0] is None:
            self._move(outer[1], outer[2], layout.height)
        visible, content = layout.inner.get(scroller, (h, h))
        self._move(y, h, content, read=read, key=f"{self.app.route}#{scroller}", view=visible)

    def read(self, data: str) -> None:
        """The researcher reads ``data`` to its end (scroll only, no interaction)."""
        control = self.find(data)
        before = self.segment.scroll_px if self.segment is not None else 0.0
        self.bring_into_view(control, read=True)
        if self.segment is not None:
            self.segment.steps.append(
                f"read {data} (scroll ≈ {self.segment.scroll_px - before:.0f} px)")

    def find_where(self, predicate):
        return next((c for c in self.controls() if predicate(c)), None)

    def _columns(self) -> set[str]:
        session = self.app.session
        return set(map(str, session.df.columns)) if session.has_data else set()

    def _selection_of(self, data: str, value) -> str | None:
        """The variable an explicit tick or dropdown choice puts into a role."""
        for prefix in ("role-", "form-"):
            if not data.startswith(prefix) or data.startswith(("form-option-", "form-confirm-",
                                                               "form-level-", "form-run")):
                continue
            role, _, name = data[len(prefix):].partition("-")
            if name and value is True and name in self._columns():
                return name
            if not name and isinstance(value, str) and value in self._columns():
                return value
        return None

    def _selections(self, names, *, explicit: bool) -> None:
        for name in names:
            if explicit and name in self.rec.selected and self.segment is not None:
                self.segment.repeated.append(name)
            self.rec.selected.add(name)

    def _bulk(self) -> set[str]:
        page = self.app.pages.get("analyze")
        chosen = set()
        for roles in (page.selection, page.form_roles):
            for value in roles.values():
                chosen.update(value if isinstance(value, list) else [value] if value else [])
        return chosen

    def _observe(self, kind: str, control, label: str, run, *, value=None, field=False):
        """Run one interaction on ``control`` through ``run`` and observe it."""
        segment = self.segment
        scrolled = segment.scroll_px if segment is not None else 0.0
        if segment is not None:
            self.bring_into_view(control)
            scrolled = segment.scroll_px - scrolled
        stack = self.app._page_stack
        before_path = reconciliation_path(stack, control) if field else None
        before_route, renders = self.app.route, self._renders
        before_bulk = self._bulk()
        result = run()
        if segment is None:
            self.page_seen()
            return result
        step = f"{kind} {stable(label)}"
        if value not in (None, True):
            step += f" = {value}"
        if scrolled >= 1:
            step += f" (scroll ≈ {scrolled:.0f} px)"
        segment.steps.append(step)
        name = self._selection_of(label, value) if label else None
        if name is not None:
            self._selections([name], explicit=True)
        elif kind == "click":
            self._selections(sorted(self._bulk() - before_bulk), explicit=False)
        segment.renders += self._renders - renders
        if field and self.app.route == before_route and self._renders > renders:
            again = self.find_where(lambda c: getattr(c, "data", None) == label) \
                if label and getattr(control, "data", None) == label else control
            if again is None or reconciliation_path(stack, again) != before_path:
                segment.focus_losses.append(label or type(control).__name__)
        self.page_seen()
        return result

    # ---------------------------------------------------------- interactions
    def click(self, data: str):
        control = self.find(data)
        parent = super().click
        before = self.total
        result = self._observe("click", control, data, lambda: parent(data))
        if self.segment is not None:
            self.segment.clicks += self.total - before
        return result

    def check(self, data: str, value: bool = True):
        control = self.find(data, ft.Checkbox)
        parent = super().check
        before = self.total
        result = self._observe("check" if value else "untick", control, data,
                               lambda: parent(data, value), value=value)
        if self.segment is not None:
            self.segment.checks += self.total - before
        return result

    def choose(self, data: str, value):
        control = self.find(data, ft.Dropdown)
        parent = super().choose
        before = self.total
        result = self._observe("choose", control, data, lambda: parent(data, value),
                               value=value, field=True)
        if self.segment is not None:
            self.segment.dropdowns += (self.total - before) // 2
        return result

    def type(self, data: str, value: str):
        control = self.find(data, ft.TextField)
        parent = super().type
        result = self._observe("type", control, data, lambda: parent(data, value),
                               value=value, field=True)
        if self.segment is not None:
            self.segment.typed += 1
        return result

    def segment_click(self, data: str, key: str):
        """One segment of a segmented switch (a click), as ``Measured.segment``."""
        group = self.find(data)
        button = next((c for c in self.controls(group)
                       if isinstance(c, ft.Button) and c.data == key), None)
        if button is None:
            raise AssertionError(f"segment {key} not in {data}")
        return self.click_control(button, f"{data}:{key}")

    # Hosted classic controls carry no data keys: they are operated by object.
    def click_control(self, control, label: str):
        handler = getattr(control, "on_click", None)
        if handler is None:
            raise AssertionError(f"{label} is not clickable")
        self.counts["click"] += 1
        result = self._observe("click", control, label, lambda: self.dispatch(
            handler, SimpleNamespace(control=control, data=None)))
        if self.segment is not None:
            self.segment.clicks += 1
        return result

    def check_control(self, control, label: str, value: bool = True):
        self.counts["check"] += 1

        def run():
            control.value = value
            handler = getattr(control, "on_change", None)    # classic boxes are read on Apply
            return self.dispatch(handler, SimpleNamespace(control=control, data=value)) \
                if handler else None

        result = self._observe("check" if value else "untick", control, label, run, value=value)
        if self.segment is not None:
            self.segment.checks += 1
            if value and label in self._columns():
                self._selections([label], explicit=True)
        return result

    def choose_control(self, control, label: str, value):
        self.counts["choose"] += 2

        def run():
            control.value = value
            handler = control.on_select
            return self.dispatch(handler, SimpleNamespace(control=control, data=value)) \
                if handler else None

        result = self._observe("choose", control, label, run, value=value, field=True)
        if self.segment is not None:
            self.segment.dropdowns += 1
        return result

    def type_control(self, control, label: str, value: str):
        def run():
            control.value = value
            handler = getattr(control, "on_change", None)
            return self.dispatch(handler, SimpleNamespace(control=control, data=value)) \
                if handler else None

        result = self._observe("type", control, label, run, value=value, field=True)
        if self.segment is not None:
            self.segment.typed += 1
        return result

    def open_file(self, data: str, path: Path):
        """A button whose action is the system Open dialog (``ft.PickFiles``):
        one click, the dialog, and the file the researcher picks in it, given
        to the picker's real ``on_result`` handler."""
        control = self.find(data)
        action = getattr(control, "action", None)
        if not isinstance(action, ft.PickFiles):
            raise AssertionError(f"{data} does not open the system Open dialog")
        self.counts["click"] += 1
        picked = SimpleNamespace(files=[SimpleNamespace(name=path.name, path=str(path))])
        handler = action.file_picker.on_result
        result = self._observe("click", control, data, lambda: self.dispatch(handler, picked))
        if self.segment is not None:
            self.segment.clicks += 1
            self.segment.dialogs.append(f"Open: {path.name}")
        return result

    def unavailable(self, what: str) -> None:
        """A step the task asks for that has no control in this version."""
        if self.segment is not None:
            self.segment.unavailable.append(what)
            self.segment.steps.append(f"not available: {what}")


# ===================================================================== the tasks
def _preparation(ws: Meter) -> dict:
    """The hosted classic *Prepare data* panel (no data keys), by its labels."""
    panel = ws.app.pages["data"]._preparation[0]
    found = {}
    for control in ws.controls(panel):
        if isinstance(control, ft.Dropdown) and control.label == "Transformation":
            found["method"] = control
        elif isinstance(control, ft.TextField) and control.label == "New variable name":
            found["target"] = control
        elif isinstance(control, ft.Button) and _label(control.content) == "Apply transformation":
            found["apply"] = control
        elif isinstance(control, ft.Button) and _label(control.content) == \
                "Use working copy in analysis":
            found["use"] = control
        elif isinstance(control, ft.Checkbox) and isinstance(control.label, str):
            found.setdefault("items", {})[control.label] = control
    missing = {"method", "target", "apply", "use", "items"} - set(found)
    if missing:
        raise AssertionError(f"the Prepare data panel lacks {sorted(missing)}")
    return found


def ensure(condition, message: str = "") -> None:
    """A task's check of its own outcome (kept under ``python -O``)."""
    if not condition:
        raise AssertionError(message or "a task did not produce its outcome")


def novice(rec: Recorder, root: Path, files: dict, *, width: int, height: int) -> dict:
    """Session 1: the novice's first start and first analyses (T1–T4)."""
    facts: dict = {}
    ws = Meter(root, rec, width=width, height=height)
    try:
        with rec.task(ws, "T1") as seg:
            seg.facts["fixture"] = "Stage 37 master (180 × 98)"
            ws.start()
            ws.type("project-new-title", PROJECT_TITLE)
            ws.click("project-create")
            ws.open_file("next-open-data", files["master"])
            session = ws.app.session
            ensure(ws.app.projects.active and ws.app.projects.info().title == PROJECT_TITLE,
                   "no project")
            ensure(session.has_data and session.df.shape == (180, 98), "the data did not open")
            facts["project_id"] = ws.app.projects.info().id
            seg.facts["start"] = ("classic interface first"
                                  if seg.steps[:1] == ["classic: Open the research workspace"]
                                  else "workspace first")

        with rec.task(ws, "T2") as seg:
            seg.facts["fixture"] = "Stage 37 master (180 × 98)"
            session = ws.app.session
            wanted = master_levels(session.df.columns)
            # Corrected as the rows are met, reading from the top.
            fixes = [name for name, info in session.variables.items()
                     if info.suggested != wanted[name]]
            for name in fixes:
                ws.choose(f"level-{name}", wanted[name])
            ws.read("data-dictionary")          # every suggestion is checked, to the last row
            ws.check("data-accept-confirm")
            ws.click("data-accept")
            wrong = {n: session.level(n) for n in wanted if session.level(n) != wanted[n]}
            ensure(not session.pending_levels() and not wrong, f"levels left: {wrong}")
            seg.facts["corrections"] = fixes
            seg.facts["suggestions"] = dict(sorted(Counter(
                info.suggested for info in session.variables.values()).items()))

        with rec.task(ws, "T3") as seg:
            seg.facts["fixture"] = "Stage 37 master, SYN_LON_01–20"
            ws.click("data-prepare")
            prep = _preparation(ws)
            ws.choose_control(prep["method"], "Transformation", "scale")
            prep = _preparation(ws)
            seg.facts["prepare_list_choices"] = len(prep["items"])
            for item in LON_ITEMS:
                ws.check_control(prep["items"][item], item)
            ws.type_control(prep["target"], "New variable name", LON_SCORE)
            ws.click_control(prep["apply"], "Apply transformation")
            ws.click_control(_preparation(ws)["use"], "Use working copy in analysis")
            session = ws.app.session
            ensure(LON_SCORE in session.df.columns, "the score was not added")
            expected = session.df[list(LON_ITEMS)].mean(axis=1)
            ensure((session.df[LON_SCORE] - expected).abs().max() < 1e-9, "a wrong score")
            if session.level(LON_SCORE) != "scale":
                ws.choose(f"level-{LON_SCORE}", "scale")
            ensure(session.level(LON_SCORE) == "scale", "the score's level is not confirmed")
            ws.click("nav-analyze")
            if not ws.find_all("goal-scale"):
                ws.click("goal-change")
            ws.click("goal-scale")
            seg.facts["item_picker_choices"] = sum(
                isinstance(c, ft.Checkbox) for c in ws.find_all("role-items-"))
            for item in LON_ITEMS:
                ws.check(f"role-items-{item}")
            for control in ws.find_all("design-confirm-"):
                ws.check(control.data)
            ws.click("guided-run")
            entry = session.results[-1]
            ensure(entry.roles.get("items") == list(LON_ITEMS), "reliability of other items")
            ws.read("result-summary")
            alpha = next((row.estimate for row in entry.run.evidence().rows
                          if "α" in row.parameter or "alpha" in row.parameter.lower()), None)
            ensure(alpha, "no α in the result")
            seg.facts.update(method=entry.method, alpha=alpha, score=LON_SCORE)
            facts["reliability_result"] = entry.id

        # Set-up, not counted (as in the Stage 36 baseline): the second data
        # file of the project, with its levels confirmed.
        ensure(ws.run(ws.app.load_path(str(files["stage36"]))), "the Stage 36 CSV did not open")
        for name, level in STAGE36_LEVELS.items():
            ws.app.session.confirm_level(name, level)
        ws.page_seen()

        with rec.task(ws, "T4") as seg:
            seg.facts["fixture"] = "Stage 36 UCLA/SACS (55 × 13)"
            ws.click("nav-analyze")
            if not ws.find_all("goal-relate"):
                ws.click("task-new")           # the previous analysis is still on screen
            ws.click("goal-relate")
            ws.choose("role-x", "UCLA")
            ws.click("role-y-all-scale")       # every quantitative variable but UCLA
            ws.check("role-y-Age", False)      # Age is not a coping scale
            ws.click("alt-batch_correlation-spearman")
            ws.click("guided-run")
            entry = ws.app.session.results[-1]
            ensure(entry.method == "batch_correlation"
                   and [row.y for row in entry.run.result.rows] == list(fx.SCALES)
                   and entry.run.result.method == "spearman", "not the eight correlations")
            ws.click("task-add-report")
            ensure(entry.in_report, "the batch is not in the report")
            facts["batch_task"] = entry.task_id
            facts["batch_result"] = entry.id
            seg.facts["pairs"] = len(entry.run.result.rows)
    finally:
        ws.close()
    return facts


def supervisor(rec: Recorder, root: Path, facts: dict, *, width: int, height: int) -> None:
    """Session 2 (after a restart) and the start of session 3 (T7, T5, T6, T8)."""
    ws = Meter(root, rec, width=width, height=height)
    try:
        with rec.task(ws, "T7") as seg:
            seg.facts["fixture"] = "the project of T1–T4"
            ws.start()
            open_project(ws, facts["project_id"])
            ws.click("nav-results")
            results = ws.app.session.results
            reviewed = []
            for entry in reversed(results):
                if not ws.find_all(f"result-detail-{entry.id}"):
                    if ws.find_all("results-picker"):      # compact window: a dropdown
                        ws.choose("results-picker", str(entry.id))
                    else:
                        ws.click(f"result-{entry.id}")
                ws.read(f"result-detail-{entry.id}")
                reviewed.append(entry.id)
            ensure(sorted(reviewed) == sorted(e.id for e in results), "a result was not seen")
            seg.facts["results"] = len(results)
            seg.facts["estimate_rows"] = {e.method: len(e.run.evidence().rows) for e in results}

        with rec.task(ws, "T5") as seg:
            from workspace_methods import advise

            seg.facts["fixture"] = "Stage 36 UCLA/SACS: UCLA → UCLA_Level"
            ws.click("nav-analyze")
            page = ws.app.pages["analyze"]
            if page.task_id != facts["batch_task"]:
                ws.click(f"task-{facts['batch_task']}")
            ws.choose("role-x", "UCLA_Level")
            chosen = page._chosen(advise(page.goal, page.selection, ws.app.session))
            if chosen and chosen[1].get("method") != "spearman":
                ws.click("alt-batch_correlation-spearman")   # the method of the earlier run
            for control in ws.find_all("design-confirm-"):
                if not control.value:
                    ws.check(control.data)
            before = len(ws.app.session.results)
            ws.click("guided-run")
            entry = ws.app.session.results[-1]
            ensure(len(ws.app.session.results) == before + 1
                   and entry.method == "batch_correlation" and entry.roles["x"] == "UCLA_Level"
                   and [row.y for row in entry.run.result.rows] == list(fx.SCALES),
                   "not the same analysis with UCLA_Level")
            seg.facts.update(method=entry.run.result.method,
                             same_task=entry.task_id == facts["batch_task"])

        with rec.task(ws, "T6") as seg:
            from docx import Document

            seg.facts["fixture"] = "the project's report"
            ws.click("nav-reports")
            ws.click("reports-export-docx")
            ensure(ws.saved and ws.saved[-1].exists(), "no Word file")
            document = Document(str(ws.saved[-1]))
            cells = " ".join(cell.text for table in document.tables for row in table.rows
                             for cell in row.cells)
            ensure(all(scale in cells for scale in fx.SCALES), "the batch is not in the report")
            seg.facts["file"] = ws.saved[-1].suffix          # the name carries the time
            seg.facts["tables"] = len(document.tables)

        with rec.task(ws, "T8", "Change the language and the text size, continue") as seg:
            seg.facts["fixture"] = "settings"
            route, selected = ws.app.route, ws.app.session.selected_result
            ws.segment_click("context-language", "lv")
            set_text_size(ws, "125", route)
            ensure(ws.app.session.language == "lv", "the language did not change")
            ensure(ws.app.route == route and ws.app.session.selected_result == selected,
                   "the work in progress was lost")
            facts["last_route"] = route
            seg.facts["language"] = ws.app.session.language
    finally:
        ws.close()

    ws = Meter(root, rec, width=width, height=height)
    try:
        with rec.task(ws, "T8", "Next start: the same language, project and page") as seg:
            ws.start()
            seg.facts["language_at_start"] = ws.app.session.language
            seg.facts["page_at_start"] = ws.app.route
            seg.facts["project_open_at_start"] = ws.app.projects.active
            if ws.app.session.language != "lv":
                ws.segment_click("context-language", "lv")
            open_project(ws, facts["project_id"])
            if ws.app.route != facts["last_route"]:
                ws.click(f"nav-{facts['last_route']}")
            ensure(ws.app.session.language == "lv" and ws.app.route == facts["last_route"],
                   "not back where the supervisor was")
    finally:
        ws.close()


def open_project(ws: Meter, project_id: str) -> None:
    """Open the project from Home, unless the program reopened it at start.
    Where Home offers "Continue where you left off" for this project (Stage
    37), that one click opens it on the page of the last session."""
    if ws.app.projects.active and ws.app.projects.info().id == project_id:
        return
    if ws.app.route != "home":
        ws.click("nav-home")
    place = ws.app.continue_place() if hasattr(ws.app, "continue_place") else None
    if place is not None and place[0].id == project_id and ws.find_all("home-continue"):
        ws.click("home-continue")
    else:
        ws.click(f"project-open-{project_id}")
    ensure(ws.app.projects.active and ws.app.projects.info().id == project_id,
           "the project did not open")


TEXT_SIZE_KEYS = ("text-size", "text_size", "textsize")


def _offers_text_size(control) -> bool:
    data = getattr(control, "data", None)
    return isinstance(data, str) and any(key in data for key in TEXT_SIZE_KEYS) \
        and isinstance(control, (ft.Dropdown, ft.Container, ft.Row))


def set_text_size(ws: Meter, value: str, back_to: str) -> None:
    """Choose a text size where the program offers one: on screen, or in
    Settings and back to the page. Without such a control the step is
    recorded as not available (U12): nothing is counted for it."""
    found = ws.find_where(_offers_text_size)
    if found is None:
        # Settings is looked at off screen first: a search that finds
        # nothing is not counted as interactions.
        if not any(_offers_text_size(c) for c in ws.controls(ws.app.pages["settings"].build())):
            ws.unavailable("text size 90/100/110/125 % (no control, U12)")
            return
        ws.click("nav-settings")
        found = ws.find_where(_offers_text_size)
    if isinstance(found, ft.Dropdown):
        ws.choose(found.data, value)
    else:
        ws.segment_click(found.data, value)
    if ws.app.route != back_to:
        ws.click(f"nav-{back_to}")


def measure(*, width: int = 1440, height: int = 800, keep: Path | None = None) -> dict:
    """Run the chain of tasks in a temporary folder and return the numbers."""
    recorder = Recorder()
    with tempfile.TemporaryDirectory(prefix="ux-metrics-") as temporary:
        folder = Path(keep) if keep is not None else Path(temporary)
        files = generate_fixtures(folder / "fixtures")
        data = folder / "data"
        facts = novice(recorder, data, files, width=width, height=height)
        supervisor(recorder, data, facts, width=width, height=height)
    viewport = float(height) - (tk.CONTEXT_BAR_HEIGHT + 8) - STATUS_BAR - 2 * tk.SPACE_5
    return recorder.results(width=width, height=height, viewport=viewport, measured=commit())


# ===================================================================== reporting
COLUMNS = (("interactions", "Inter."), ("typed", "Typed"), ("page_changes", "Pages"),
           ("dialogs", "Dialogs"), ("repeated_selections", "Repeat sel."),
           ("focus_losses", "Focus lost"), ("scroll_px_estimate", "Scroll px (est.)"))


def markdown(results: dict) -> str:
    """The baseline table (Markdown), one row per task, persona totals after."""
    lines = ["| # | Persona | Task | Fixture | Inter. (click · box · dropdown) | Typed | Pages "
             "| Dialogs | Repeat sel. | Focus lost | Scroll px (est.) |",
             "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for t in results["tasks"]:
        unavailable = (f" — not available: {'; '.join(t['unavailable'])}"
                       if t["unavailable"] else "")
        lines.append(
            f"| {t['task']} | {t['persona']} | {t['title']}{unavailable} | {t['fixture']} | "
            f"{t['interactions']} ({t['clicks']} · {t['checkboxes']} · {t['dropdowns']}) | "
            f"{t['typed']} | {t['page_changes']} | {t['dialogs']} | {t['repeated_selections']} | "
            f"{t['focus_losses']} | ≈ {t['scroll_px_estimate']:,} |")
    for persona, total in results["personas"].items():
        lines.append(f"| | **{persona}** | **total** | | **{total['interactions']}** | "
                     f"**{total['typed']}** | **{total['page_changes']}** | "
                     f"**{total['dialogs']}** | **{total['repeated_selections']}** | "
                     f"**{total['focus_losses']}** | **≈ {total['scroll_px_estimate']:,}** |")
    return "\n".join(lines) + "\n"


def text_report(results: dict) -> str:
    out = [f"Stage 37 UX metrics ({results['measured']}), window "
           f"{results['window']['width']} × {results['window']['height']}, "
           f"viewport ≈ {results['viewport_px_estimate']} px",
           f"rule: {results['rule']}", ""]
    head = f"{'task':4} {'persona':10} " + " ".join(f"{label:>16}" for _, label in COLUMNS)
    out.append(head)
    for t in results["tasks"]:
        out.append(f"{t['task']:4} {t['persona']:10} "
                   + " ".join(f"{t[key]:>16}" for key, _ in COLUMNS))
        for part in t["segments"]:
            out.append(f"       · {part['title']} (session {part['session']}): "
                       f"{part['interactions']} inter., {part['typed']} typed, "
                       f"pages {part['pages'] or '—'}, dialogs {part['dialogs'] or '—'}")
            if part["repeated_selections"]:
                out.append(f"         repeated: {', '.join(part['repeated_selections'])}")
            if part["focus_losses"]:
                out.append(f"         focus lost: {', '.join(part['focus_losses'])}")
            if part["unavailable"]:
                out.append(f"         not available: {'; '.join(part['unavailable'])}")
    out.append("")
    for persona, total in results["personas"].items():
        out.append(f"{persona:10} " + " ".join(f"{k}={v}" for k, v in total.items()))
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", type=Path, help="write the numbers as JSON")
    parser.add_argument("--markdown", type=Path, help="write the baseline table (Markdown)")
    parser.add_argument("--width", type=int, default=1440, help="window width (harness default)")
    parser.add_argument("--height", type=int, default=800, help="window height")
    parser.add_argument("--keep", type=Path, help="keep the fixtures and projects in this folder")
    args = parser.parse_args(argv)
    results = measure(width=args.width, height=args.height, keep=args.keep)
    print(text_report(results))
    if args.json:
        args.json.write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
