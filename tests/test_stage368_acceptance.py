"""Stage 36.8 (#62, Part 8): the flows of the new packaged-program journeys,
through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts
UI Automation exposes. These tests walk the flows of its journeys
`psychometrics`, `import-resume` and `negative-paths` in the workspace
harness and check, at each point, that every text and button name the
journey waits for is really there in that state (a button is named by its
label), using the journey's own texts and helpers. They do not replace the
Windows runs; they keep the journeys honest between them. Synthetic data
only; no AI key anywhere and nothing on the network.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402
from workspace_text import T as TABLE  # noqa: E402


def T(key: str, **values) -> str:
    text = TABLE[key][0]
    return text.format(**values) if values else text


def label(ws, data_id: str) -> str:
    """The name UI Automation gives a button: its label."""
    content = ws.find(data_id).content
    return content if isinstance(content, str) else getattr(content, "value", "")


def names(ws) -> list[str]:
    """Like the journeys' screen texts: texts, button names and checkbox labels."""
    found = list(ws.texts())
    for control in ws.controls():
        if isinstance(control, (ft.Button, ft.TextButton)) and isinstance(control.content, str):
            found.append(control.content)
        elif isinstance(control, ft.Checkbox) and isinstance(control.label, str):
            found.append(control.label)
    return found


def on_screen(ws, fragment: str) -> bool:
    return any(fragment in name for name in names(ws))


def first_outcome(ws, wanted: dict) -> str | None:
    """The outcome e2e.wait_any would report: ``wanted`` in priority order."""
    shown = names(ws)
    for key, what in wanted.items():
        for text in shown:
            if (what.search(text) if hasattr(what, "search") else what in text):
                return key
    return None


def buttons(ws, pattern: str) -> list[str]:
    return [c.content for c in ws.controls() if isinstance(c, (ft.Button, ft.TextButton))
            and isinstance(c.content, str) and re.search(pattern, c.content)]


def folder_of(root: Path) -> SimpleNamespace:
    """What the driver's on-disk checks need of its Gui: the data folder."""
    return SimpleNamespace(real_data=False, data_dir=root)


def tesseract_with(*languages: str) -> bool:
    try:
        from ocr_runtime import ocr_readiness
        from visual_survey_review import tesseract_available

        return tesseract_available() and set(languages) <= set(ocr_readiness().languages)
    except Exception:
        return False


# CI's pruned-runtime job requires the real engine: the walk must run there.
REQUIRE_OCR = os.environ.get("SRA_REQUIRE_REAL_OCR") == "1"


# ------------------------------------- fake UI Automation elements (row helpers)
class Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class Element:
    def __init__(self, name, left, top, right, bottom, control_type="Text"):
        self.element_info = SimpleNamespace(name=name, control_type=control_type,
                                            rectangle=Rect(left, top, right, bottom))


class Screen:
    """A Gui stand-in for the row and column helpers: a fixed set of elements."""

    def __init__(self, elements):
        self.items = list(elements)

    def elements(self):
        return self.items

    @staticmethod
    def value(element):
        return ""


def as_cells(columns, rows, *, merged: bool):
    """A table as Windows may expose it: every cell its own element, or each
    row (and the header) one element whose name holds the cells as lines."""
    elements, anchors = [], {}
    for line, cells in enumerate([tuple(columns), *rows]):
        top = 100 + 40 * line
        if merged:
            element = Element("\n".join(c for c in cells if c), 200, top, 1800, top + 36)
            elements.append(element)
            anchors[cells[0]] = element
            continue
        for column, cell in enumerate(cells):
            if not cell:
                continue                          # an empty cell has no name
            element = Element(cell, 200 + 110 * column, top + 6, 290 + 110 * column, top + 30)
            elements.append(element)
            if column == 0:
                anchors[cell] = element
            if line == 0:
                anchors.setdefault(("header", cell), element)
    # The surrounding table and card: tall, so never taken for a cell.
    elements.append(Element("APA-style table", 150, 60, 1850, 100 + 40 * (len(rows) + 1),
                            control_type="Group"))
    return Screen(elements), anchors


class DriverHelperTests(unittest.TestCase):
    """The parts of the new journeys that read the screen, on both ways
    Windows may expose a table (no Windows needed)."""

    COLUMNS = ("Item", "M", "SD", "Missing", "r (item–total, corrected)", "α if deleted", "Δα",
               "Flags")
    ROWS = (("ZEP03", "3.01", "1.00", "1 (0.5%)", ".57", ".45", "-.116", ""),
            ("ZEP04", "2.94", "1.01", "0 (0.0%)", "-.56", ".72", "+.154",
             "possibly reverse-keyed, not recoded"))

    def test_the_cell_under_a_header_with_separate_cells_and_with_merged_rows(self):
        for merged in (False, True):
            screen, anchors = as_cells(self.COLUMNS, self.ROWS, merged=merged)
            header = anchors["Item"] if merged else anchors[("header", "α if deleted")]
            value = e2e.column_cell(screen, header, e2e.ALPHA_IF_DELETED, anchors["ZEP04"])
            self.assertEqual(value, ".72", f"merged={merged}")
            cells = [text for _, text in e2e.row_cells(screen, anchors["ZEP04"])]
            self.assertEqual(cells[0], "ZEP04")
            self.assertEqual(cells[-1], "possibly reverse-keyed, not recoded")

    def test_a_verified_estimate_row_gives_its_value_after_its_label(self):
        label_text = f"{e2e.ALPHA_IF_DELETED}: {e2e.ALPHA_ITEM}"
        for merged in (False, True):
            screen, anchors = as_cells(("Parameter", "Estimate", "95% CI", "p"),
                                       ((label_text, "0.72", "—", "—"),), merged=merged)
            cells = [text for _, text in e2e.row_cells(screen, anchors[label_text])]
            self.assertEqual(cells[cells.index(label_text) + 1], "0.72")

    def test_numbers_are_compared_at_the_precision_shown(self):
        self.assertTrue(e2e.same_as_shown(0.7204064, ".72"))
        self.assertTrue(e2e.same_as_shown(0.5666379, "0.57"))
        self.assertTrue(e2e.same_as_shown(-0.1230, "−.123"))
        self.assertTrue(e2e.same_as_shown(0.1543, "+.154"))
        self.assertFalse(e2e.same_as_shown(0.5666379, "0.56"))
        self.assertEqual(e2e.number_shown(".72"), 0.72)

    def test_a_refused_save_passes_only_without_a_false_claim(self):
        journey = SimpleNamespace(facts={})
        program = {"cancelled_by_driver": False, "dialog_messages": []}
        e2e.check_refused(journey, "x", dict(program), "folder_read_only", "m", unchanged=True)
        windows = {"cancelled_by_driver": True, "dialog_messages": ["You don't have permission"]}
        e2e.check_refused(journey, "y", dict(windows), "cancelled", "m", unchanged=True)
        self.assertEqual(journey.facts["y"]["refused_by"], "the Windows Save dialog")
        for attempt, outcome, unchanged in ((program, "saved", True), (program, "cancelled", True),
                                            (program, "file_locked", False),
                                            (windows, "folder_read_only", True)):
            with self.assertRaises(e2e.StepFailure, msg=(attempt, outcome, unchanged)):
                e2e.check_refused(journey, "z", dict(attempt), outcome, "m", unchanged=unchanged)

    def test_the_new_journeys_follow_the_thirteen_unchanged(self):
        self.assertEqual(list(e2e.JOURNEYS)[:13], [
            "stage36-tasks", "stage36-charts", "stage36-groups", "project-a", "project-b",
            "import-30", "review-120", "responses", "blocked-design", "import-cope-docx",
            "import-scan-lv", "stage36-report", "import-damaged"])
        self.assertEqual(list(e2e.JOURNEYS)[13:16], ["psychometrics", "import-resume",
                                                      "negative-paths"])
        self.assertEqual(e2e.TOTALS_ONLY, "Only a total score is available now",
                         "the D5 text of journey stage36-report")


class Clock:
    """time for the driver: sleeping moves the clock, nothing waits."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Widget:
    """A UI Automation element of a Windows dialog, as pywinauto wraps it."""

    def __init__(self, name="", control_type="Pane", automation_id="", class_name="",
                 children=(), on_click=None):
        self.element_info = SimpleNamespace(name=name, control_type=control_type,
                                            automation_id=automation_id, class_name=class_name,
                                            handle=id(self), rectangle=Rect(0, 0, 100, 30))
        self.items, self.on_click, self.visible = list(children), on_click, True

    def children(self):
        return [child for child in self.items if child.visible]

    def descendants(self, control_type=None):
        found = []
        for child in self.children():
            if control_type is None or child.element_info.control_type == control_type:
                found.append(child)
            found += child.descendants(control_type)
        return found

    def click_input(self, *args, **kwargs):
        if self.on_click is not None:
            self.on_click()

    def window_text(self):
        return self.element_info.name


class SaveDialog:
    """The Windows Save dialog in one of three behaviours after Enter:
    "accept" (the path goes to the program), "refuse" (a message box OWNED
    by the dialog, so listed among its children: no permission here, save
    in Documents instead?) and "replace" (the file exists: replace it?)."""

    def __init__(self, behaviour: str):
        self.behaviour, self.open, self.box, self.typed, self.events = behaviour, False, None, "", []
        self.dialog = Widget("Save As", "Window", class_name="#32770", children=[
            Widget("File name:", "Edit", "1001"),
            Widget("Save", "Button", "1"), Widget("Cancel", "Button", "2", on_click=self.cancel)])

    def cancel(self):
        self.open = False
        self.events.append("cancelled")

    def keys(self, keys, **kwargs):
        if keys == "{ENTER}":
            self.enter()
        elif keys not in ("^a{BACKSPACE}", "%n", "{ESC}"):
            self.typed += keys

    def message(self, text, yes, no):
        box = Widget("Save As", "Window", class_name="#32770", children=[
            Widget(text, "Text", "65535"), Widget("Yes", "Button", "6", on_click=yes),
            Widget("No", "Button", "7", on_click=no)])
        self.box = box
        return box

    def close_box(self):
        self.box.visible = False

    def enter(self):
        if self.behaviour == "accept":
            self.open = False
            self.events.append("accepted")
        elif self.behaviour == "refuse":
            def elsewhere():
                self.events.append("saved in Documents")
                self.close_box()
                self.open = False
            self.dialog.items.append(self.message(
                "You don't have permission to save in this location. Would you like to save in "
                "the Documents folder instead?", elsewhere, self.close_box))
        else:
            def replace():
                self.events.append("replaced")
                self.close_box()
                self.open = False
            self.message("negative_report.txt already exists. Do you want to replace it?",
                         replace, self.close_box)

    def windows(self):
        found = [self.dialog] if self.open else []
        if self.behaviour == "replace" and self.box is not None and self.box.visible:
            found.append(self.box)          # a top-level message box
        return found


class DialogGui:
    """What refused_save needs of Gui: a button that opens the dialog, the
    dialogs of the program and screenshots."""

    def __init__(self, dialog: SaveDialog):
        self.save, self.pressed = dialog, []

    def click(self, name, **kwargs):
        self.pressed.append(name)
        self.save.open = True

    def dialogs(self):
        return self.save.windows()

    def shot(self, name):
        return None


class SaveDialogTests(unittest.TestCase):
    """refused_save answers the Windows Save dialog so that nothing is ever
    saved somewhere else, and records who refused (no Windows needed: fake
    UI Automation windows, a fake keyboard and a fake clock)."""

    def attempt(self, behaviour: str) -> tuple[dict, SaveDialog]:
        dialog = SaveDialog(behaviour)
        keyboard = SimpleNamespace(send_keys=dialog.keys)
        pywinauto = SimpleNamespace(keyboard=keyboard)
        clock = Clock()
        with mock.patch.dict(sys.modules, {"pywinauto": pywinauto, "pywinauto.keyboard": keyboard}), \
                mock.patch.object(e2e, "time", SimpleNamespace(monotonic=clock.monotonic,
                                                               sleep=clock.sleep)):
            facts = e2e.refused_save(DialogGui(dialog), "Save TXT…",
                                     Path("C:/fictional/read-only-folder/negative_result.txt"))
        self.assertIn("negative_result.txt", dialog.typed, "the path is typed in the dialog")
        return facts, dialog

    def test_the_path_reaches_the_program(self):
        facts, dialog = self.attempt("accept")
        self.assertEqual((facts["cancelled_by_driver"], facts["dialog_messages"]), (False, []))
        self.assertEqual(dialog.events, ["accepted"])

    def test_windows_refuses_the_folder_never_saved_elsewhere(self):
        facts, dialog = self.attempt("refuse")
        self.assertTrue(facts["cancelled_by_driver"])
        self.assertEqual(facts["answers"], ["no", "cancel"])
        self.assertIn("You don't have permission", facts["dialog_messages"][0])
        self.assertEqual(dialog.events, ["cancelled"], "never 'save in Documents instead'")

    def test_an_existing_file_is_replaced_so_the_program_gets_the_path(self):
        facts, dialog = self.attempt("replace")
        self.assertEqual((facts["cancelled_by_driver"], facts["answers"]), (False, ["yes"]))
        self.assertEqual(dialog.events, ["replaced"])

    def test_the_message_box_of_the_dialog_is_found_among_its_children(self):
        dialog = SaveDialog("refuse")
        dialog.open = True
        dialog.enter()
        found = e2e.save_dialog_windows(DialogGui(dialog))
        self.assertEqual(found, ([dialog.dialog], [dialog.box]))


class ScreenSearchTests(unittest.TestCase):
    """find_text and wait_any on a fake screen that scrolls."""

    class Page:
        """Elements by scroll position: ``rows`` appear once scrolled down far enough."""

        def __init__(self, rows):
            self.rows, self.offset, self.wheels, self.real_data = rows, 0, [], False

        def elements(self):
            return [element for position, element in self.rows if self.offset >= position]

        @staticmethod
        def value(element):
            return getattr(element, "text_value", "")

        def wheel(self, clicks, at=None):
            self.wheels.append(clicks)
            self.offset -= clicks              # negative clicks scroll down

        def scroll_into_view(self, element):
            return element

        def dump(self, name):
            return None

        def shot(self, name):
            return None

        def log_screen(self, title):
            return None

    def page(self):
        counts = Element("52 items · 16 need attention · 1 compared with the source", 0, 0, 10, 10)
        edit = Element("", 0, 0, 10, 10, control_type="Edit")
        edit.text_value = "Cronbach’s α = 0.57; McDonald’s ω = 0.71; k = 10, n = 192."
        far = Element("Item diagnostics: 10 items, N = 192 complete respondents", 0, 0, 10, 10)
        return self.Page([(0, counts), (0, edit), (25, far)])

    def run_with_clock(self, function, *args, **kwargs):
        clock = Clock()
        with mock.patch.object(e2e, "time", SimpleNamespace(monotonic=clock.monotonic,
                                                            sleep=clock.sleep)):
            return function(*args, **kwargs)

    def test_a_text_in_a_name_or_a_value_and_one_far_below(self):
        page = self.page()
        element, text = self.run_with_clock(e2e.find_text, page, regex=e2e.SUMMARY.pattern)
        self.assertTrue(text.startswith("Cronbach’s α = 0.57"), "a text field's value counts")
        self.assertEqual(page.wheels, [], "found without scrolling")
        _, text = self.run_with_clock(e2e.find_text, page, "Item diagnostics: 10 items",
                                      timeout=600)
        self.assertEqual(set(page.wheels), {-5}, "scrolled down to it")
        counts = self.run_with_clock(e2e.read_counts, page)
        self.assertEqual(counts, {"total": 52, "attention": 16, "checked": 1})

    def test_searching_up_first_and_giving_up(self):
        page = self.page()
        with self.assertRaises(e2e.StepFailure):
            self.run_with_clock(e2e.find_text, page, "not on this page", timeout=60,
                                moves=3, first="up")
        self.assertEqual(page.wheels, [5, 5, 5, -5, -5, -5], "up first, then back down")

    def test_wait_any_reports_the_first_outcome_in_priority_order(self):
        page = self.page()
        key, text = self.run_with_clock(e2e.wait_any, page, {
            "restored": "Your earlier review", "counts": e2e.counts_pattern(),
            "summary": "Cronbach"})
        self.assertEqual(key, "counts")


def create_project_in_ui(ws, title: str) -> None:
    """create_project: Home → the title typed → Create project."""
    ws.click("nav-home")
    ws.type("project-new-title", title)
    assert label(ws, "project-create") == T("project.create")
    ws.click("project-create")
    assert ws.has_text(title) and ws.has_text(T("next.add_data"))


def open_csv(ws, path: Path) -> None:
    """open_data: the button the journey clicks, then the file the Open dialog gives."""
    assert any(control.content == T("data.open") for control in ws.controls()
               if isinstance(control, (ft.Button, ft.TextButton)))
    assert ws.run(ws.app.load_path(str(path)))
    assert ws.has_text(T("data.loaded", name=path.name)), "open_data waits for this"


def accept_levels_in_ui(ws) -> None:
    ws.click("nav-data")
    assert ws.find("data-accept-confirm").label == T("data.accept_confirm")
    assert label(ws, "data-accept") == T("data.accept_suggestions")
    ws.check("data-accept-confirm")
    ws.click("data-accept")
    assert ws.has_text(T("next.analyze")), "accept_levels waits for this"


def guided(ws) -> None:
    ws.click("nav-analyze")
    mode = ws.find("analyze-mode")
    assert T("analyze.mode.guided") in [c.content for c in ws.controls(mode)
                                        if isinstance(c, ft.Button)]
    ws.segment("analyze-mode", "guided")


def table_rows(ws, title: str):
    """(columns, rows) of the result table titled ``title``."""
    controls = ws.controls(ws.find("result-table"))
    for index, control in enumerate(controls):
        if isinstance(control, ft.Text) and control.value == title:
            table = next(c for c in controls[index:] if isinstance(c, ft.DataTable))
            columns = [c.label.value for c in table.columns]
            rows = [[cell.content.value for cell in row.cells] for row in table.rows]
            return columns, rows
    raise AssertionError(f"no table {title!r}")


class PsychometricsJourneyTests(unittest.TestCase):
    """Journey `psychometrics` (spec journey F, and D5 in its own project)."""

    def test_the_driver_computes_alpha_itself_as_the_engine_does(self):
        import pandas as pd

        from reliability import analyze_cronbach

        csv_path = fx.fixture(fx.ITEMS_CSV)
        alpha, n = e2e.independent_alpha(csv_path, fx.ITEMS)
        engine = analyze_cronbach(pd.read_csv(csv_path), list(fx.ITEMS))
        self.assertAlmostEqual(alpha, engine.alpha, places=12)
        self.assertEqual(n, engine.n_complete)
        deleted, same = e2e.independent_alpha(csv_path, fx.ITEMS, without=e2e.ALPHA_ITEM)
        self.assertAlmostEqual(deleted, engine.alpha_if_deleted[e2e.ALPHA_ITEM], places=12)
        self.assertEqual(same, n, "α if deleted uses the same complete respondents")

    def test_scale_check_shows_what_the_driver_computes_and_totals_get_no_coefficient(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ws = Workspace(root=root)
            self.addCleanup(ws.close)
            app = ws.app
            csv_path = fx.generator().create_items_csv(root)
            expected = e2e.psychometrics_expected(csv_path)
            self.assertEqual((expected["k"], expected["n"]), (10, 192))
            create_project_in_ui(ws, e2e.PSYCHOMETRICS_PROJECT)
            open_csv(ws, csv_path)
            accept_levels_in_ui(ws)

            # The scale check: goal, the ten items in one action, the confirmation.
            guided(ws)
            self.assertTrue(ws.has_text(T("goal.scale")), "click_chip(goal.scale)")
            ws.click("goal-scale")
            self.assertEqual(label(ws, "role-items-all-ordinal"),
                             T("pick.all_ordinal", count=len(fx.ITEMS)))
            ws.click("role-items-all-ordinal")
            for item in fx.ITEMS:
                box = ws.find(f"role-items-{item}")
                self.assertEqual(box.label, e2e.option_label(item, "ordinal"))
                self.assertTrue(box.value, item)
            self.assertFalse(ws.find(f"role-items-{fx.ITEM_TOTAL}").value, "the total is no item")
            self.assertTrue(ws.has_text(T("design.levels_summary", count=len(fx.ITEMS),
                                          levels=T("level.ordinal"))))
            confirmations = e2e.scale_check_confirmations()
            self.assertEqual([ws.find("design-confirm-one_construct").label], confirmations)
            ws.check("design-confirm-one_construct")
            self.assertTrue(label(ws, "guided-run").startswith(T("rec.run", method="")))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ws.click("guided-run")
            self.assertEqual(app.route, "results")
            self.assertEqual(label(ws, "export-txt"), T("results.save_txt"))

            # α and ω: the summary the journey reads, at its precision.
            summary = ws.find("result-answer").value
            shown = e2e.SUMMARY.search(summary).groupdict()
            self.assertTrue(e2e.same_as_shown(expected["alpha"], shown["alpha"]), summary)
            self.assertTrue(e2e.same_as_shown(expected["omega"], shown["omega"]), summary)
            self.assertTrue(0 <= e2e.number_shown(shown["omega"]) <= 1)
            self.assertEqual((int(shown["k"]), int(shown["n"])), (expected["k"], expected["n"]))

            # The verified estimates: the row the journey reads.
            label_text = f"{e2e.ALPHA_IF_DELETED}: {e2e.ALPHA_ITEM}"
            columns, rows = table_rows(ws, f"{app.session.results[-1].run.title}: "
                                           "verified estimates")
            row = next(r for r in rows if r[0] == label_text)
            self.assertTrue(e2e.same_as_shown(expected["alpha_if_deleted"], row[1]), row)

            # The α-if-item-deleted table: its title, the column and the row.
            columns, rows = table_rows(ws, e2e.item_table_title(expected))
            self.assertIn(e2e.ALPHA_IF_DELETED, columns)
            row = next(r for r in rows if r[0] == e2e.ALPHA_ITEM)
            value = row[columns.index(e2e.ALPHA_IF_DELETED)]
            self.assertTrue(e2e.same_as_shown(expected["alpha_if_deleted"], value), value)
            for merged in (False, True):         # read the way the journey reads it
                screen, anchors = as_cells(columns, rows, merged=merged)
                header = anchors[columns[0]] if merged else anchors[("header",
                                                                     e2e.ALPHA_IF_DELETED)]
                self.assertEqual(e2e.column_cell(screen, header, e2e.ALPHA_IF_DELETED,
                                                 anchors[e2e.ALPHA_ITEM]), value)

            # The TXT report holds the same numbers.
            ws.click("export-txt")
            text = ws.saved[-1].read_text(encoding="utf-8")
            for fragment in e2e.psychometrics_report_fragments(expected):
                self.assertIn(fragment, text)
            self.assertTrue(ws.has_text(ws.saved[-1].name), "save_via_dialog waits for this")

            # A totals-only dataset in the same project: no coefficient, no Run.
            ws.click("nav-data")
            self.assertEqual(label(ws, "data-open"), T("data.open"))
            open_csv(ws, fx.generator().create_csv(root))
            accept_levels_in_ui(ws)
            guided(ws)
            self.assertEqual(label(ws, "task-new"), T("task.new"))
            ws.click("task-new")
            self.assertTrue(ws.has_text(T("goal.scale")))
            ws.click("goal-scale")
            for scale in fx.SCALES[:3]:
                self.assertEqual(ws.find(f"role-items-{scale}").label,
                                 e2e.option_label(scale, "scale"))
                ws.check(f"role-items-{scale}")
            self.assertTrue(ws.has_text(e2e.TOTALS_ONLY))
            self.assertFalse(ws.find_all("guided-run"))
            self.assertFalse(buttons(ws, "^" + re.escape(T("rec.run", method=""))),
                             "the journey finds no Run button")
            runs = e2e.project_query(folder_of(root), e2e.PSYCHOMETRICS_PROJECT,
                                     "SELECT method FROM runs")
            self.assertEqual([method for (method,) in runs], ["item_diagnostics"])


@unittest.skipUnless(tesseract_with("lav") or REQUIRE_OCR, "local OCR with Latvian is not installed")
class ImportResumeJourneyTests(unittest.TestCase):
    """Journey `import-resume` (spec journey E: cancel, resume after a restart),
    with the real local OCR."""

    def test_cancel_read_change_restart_and_the_saved_review_comes_back(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            documents = root / "documents"
            documents.mkdir()
            pdf = fx.generator().create_lv_table_scan_pdf(documents)
            sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
            texts = e2e.import_resume_texts(pdf.name)
            disk = folder_of(root)
            ws = Workspace(root=root)
            page = ws.app.pages["import"]
            ws.app.navigate("import")
            # import_document(..., shows=imp.state.scan): the Open dialog gives the file.
            ws.run(page.open_bytes(pdf.read_bytes(), pdf.name, path=str(pdf)))
            self.assertTrue(on_screen(ws, T("imp.state.scan")))
            language = ws.find("imp-ocr-language", ft.Dropdown)
            self.assertEqual(language.label, T("imp.ocr_language"))
            self.assertIn(T("imp.ocr_lang.lav"), [o.text for o in language.options])
            ws.choose("imp-ocr-language", "lav")
            self.assertEqual(label(ws, "imp-ocr-run"), T("imp.ocr_run"))

            # Cancel while it reads.
            seen = {}

            async def read_and_cancel():
                run = ws.find("imp-ocr-run")
                task = asyncio.create_task(run.on_click(SimpleNamespace(control=run, data=None)))
                while not (page.busy and page.reading == "ocr"):
                    await asyncio.sleep(0.02)
                seen["recognizing"] = on_screen(ws, T("imp.state.recognizing"))
                seen["cancel"] = label(ws, "imp-cancel")
                ws.click("imp-cancel")
                await task

            ws.run(read_and_cancel())
            self.assertEqual(seen, {"recognizing": True, "cancel": T("imp.cancel_ocr")})
            self.assertEqual(first_outcome(ws, {"cancelled": texts["cancelled"],
                                                "read": texts["read"]}), "cancelled")
            self.assertTrue(on_screen(ws, T("imp.state.scan")))
            self.assertEqual(label(ws, "imp-ocr-run"), T("imp.ocr_run"), "offered again")
            self.assertFalse(on_screen(ws, "candidate items"), "nothing applied")
            self.assertFalse(buttons(ws, r"^\d\. [^\n]* · "), "no review wizard")
            self.assertIsNone(page.session.instrument)
            self.assertIsNone(e2e.saved_review(disk, sha), "nothing saved")

            # Read again to completion: 52 candidates.
            ws.choose("imp-ocr-language", "lav")
            ws.click("imp-ocr-run")
            for key in ("read", "ocr_used"):
                self.assertTrue(on_screen(ws, texts[key]), key)
            self.assertTrue(on_screen(ws, "52 candidate items"))

            # One review change: item 13 compared with the source.
            step = ws.find("imp-step-items")
            self.assertRegex(step.content, r"^3\. [^\n]* · ", "wizard_step(gui, 3)")
            ws.click("imp-step-items")
            counts = [t for t in ws.texts() if e2e.counts_pattern().search(t)]
            self.assertTrue(counts, "read_counts")
            before = {k: int(v) for k, v in e2e.counts_pattern().search(counts[0])
                      .groupdict().items()}
            index = e2e.RESUME_ITEM - 1
            row = ws.find(f"imp-item-{index}")
            row_texts = [c.value for c in ws.controls(row) if isinstance(c, ft.Text)]
            self.assertTrue(any(re.match(rf"(?:^|\n){e2e.RESUME_ITEM}\. ", t) for t in row_texts),
                            row_texts)
            self.assertFalse([t for t in ws.texts() if re.search(rf"(?:^|\n){e2e.RESUME_ITEM}\. ", t)
                              and t not in row_texts], "the journey's row pattern is unique")
            ws.click(f"imp-item-{index}")
            self.assertEqual(ws.find("imp-item-reviewed").label, T("imp.item_reviewed"))
            ws.check("imp-item-reviewed")
            after = {k: int(v) for k, v in e2e.counts_pattern().search(
                next(t for t in ws.texts() if e2e.counts_pattern().search(t))).groupdict().items()}
            self.assertEqual((after["total"], after["checked"]), (52, before["checked"] + 1))
            self.assertIn(before["attention"] - after["attention"], (0, 1))
            record = e2e.saved_review(disk, sha)
            self.assertEqual(record["forms"][str(record["chosen"])]["reviewed"], [index])
            self.assertEqual((record["step"], record["selected"], record["ocr_language"]),
                             ("items", index, "lav"))

            # Restart: the unfinished review is offered, the same PDF brings it back.
            ws.close()
            again = Workspace(root=root)
            self.addCleanup(again.close)
            again.app.navigate("questionnaires")
            self.assertIn(texts["offer"], buttons(again, re.escape(texts["offer"])))
            self.assertIn(T("q.import"), buttons(again, re.escape(T("q.import"))))
            page = again.app.pages["import"]
            again.app.navigate("import")
            with mock.patch.object(again.app, "reveal"):
                again.run(page.open_bytes(pdf.read_bytes(), pdf.name, path=str(pdf)))
            for key in ("restored", "read", "ocr_used"):
                self.assertTrue(on_screen(again, texts[key]), key)
            shown = {k: int(v) for k, v in e2e.counts_pattern().search(
                next(t for t in again.texts() if e2e.counts_pattern().search(t))).groupdict().items()}
            self.assertEqual(shown, after, "the change and the items needing attention")
            if shown["attention"]:
                self.assertTrue(on_screen(again, T("imp.filter.attention",
                                                   count=shown["attention"])))
            self.assertTrue(on_screen(again, T("imp.state.review")))
            box = again.find("imp-item-reviewed")
            self.assertEqual((box.label, box.value), (T("imp.item_reviewed"), True))
            self.assertEqual(len(page.session.instrument.questions), 52)

            # Discard after another restart, from the offer at the top of
            # Questionnaires (the journey cannot reach the status line of a
            # long review on Windows): the journey can run again.
            again.close()
            third = Workspace(root=root)
            self.addCleanup(third.close)
            third.app.navigate("questionnaires")
            self.assertIn(texts["offer"], buttons(third, re.escape(texts["offer"])))
            # The offer opens the review from its file (resume_review).
            page = third.app.pages["import"]
            with mock.patch.object(third.app, "reveal"):
                third.run(page.resume_review(sha))
            for key in ("restored", "read"):
                self.assertTrue(on_screen(third, texts[key]), key)
            self.assertEqual(label(third, "imp-discard"), T("imp.discard"))
            third.click("imp-discard")
            self.assertEqual(label(third, "imp-discard-confirm"), T("imp.discard_confirm"))
            third.click("imp-discard-confirm")
            self.assertTrue(on_screen(third, texts["discarded"]))
            self.assertIsNone(e2e.saved_review(disk, sha))
            self.assertFalse(buttons(third, re.escape(texts["offer"])), "no longer offered")


class NegativePathsJourneyTests(unittest.TestCase):
    """Journey `negative-paths`: a read-only save location, the AI assistant
    without a provider, an AI permission allowed and revoked."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.ws = Workspace(root=self.root)
        self.addCleanup(self.ws.close)
        ws = self.ws
        create_project_in_ui(ws, e2e.NEGATIVE_PROJECT)
        open_csv(ws, fx.generator().create_csv(self.root))
        accept_levels_in_ui(ws)
        guided(ws)
        self.assertTrue(ws.has_text(T("goal.describe")))
        ws.click("goal-describe")
        variable = ws.find("role-variable")
        self.assertEqual(variable.label, T("role.variable"))
        self.assertEqual([o.text for o in variable.options], e2e.stage36_options(),
                         "the journey's keyboard fallback needs this exact list")
        ws.choose("role-variable", "UCLA")
        ws.click("guided-run")
        self.assertTrue(ws.has_text("Descriptive: UCLA"))
        self.assertEqual(label(ws, "export-txt"), T("results.save_txt"))

    def save(self, typed: str | None, refused: Path | None) -> str | None:
        """Save TXT where the save dialog returns ``typed``; writing ``refused``
        (or into it, a folder) raises PermissionError, as Windows does for a
        read-only folder or file (as root here, file modes would not)."""
        real = Path.write_bytes

        def write_bytes(path, data):
            if refused is not None and refused in (path, path.parent):
                raise PermissionError(errno.EACCES, "Permission denied", str(path))
            return real(path, data)

        async def dialog(title, file_name, extension):
            return typed

        self.ws.app.save_dialog = dialog
        with mock.patch.object(Path, "write_bytes", write_bytes):
            self.ws.click("export-txt")
        target = Path(typed) if typed else self.root / "never.txt"
        return first_outcome(self.ws, e2e.save_outcomes(target.with_suffix(".txt")))

    def test_a_read_only_folder_and_file_are_refused_in_words_never_claimed(self):
        locked = self.root / "read-only-folder"
        locked.mkdir()
        target = locked / "negative_result.txt"
        self.assertEqual(self.save(str(target), locked), "folder_read_only")
        self.assertFalse(target.exists())
        self.assertFalse(on_screen(self.ws, T("save.saved", path="")), "no success claimed")

        existing = self.root / "read-only-file" / "negative_report.txt"
        existing.parent.mkdir()
        existing.write_text("Fictional placeholder.\n", encoding="utf-8")
        # Typed without its extension, as the journey types it.
        self.assertEqual(self.save(str(existing.with_name("negative_report")), existing),
                         "file_locked")
        self.assertEqual(existing.read_text(encoding="utf-8"), "Fictional placeholder.\n")
        self.assertTrue(on_screen(self.ws, "negative_report.txt could not be replaced"))
        feedback = " ".join(c.value for c in self.ws.controls(self.ws.find("result-feedback"))
                            if isinstance(c, ft.Text))
        self.assertIn("could not be replaced", feedback, "shown next to the button too")

        # Windows' own Save dialog refused the location and was cancelled.
        self.assertEqual(self.save(None, None), "cancelled")

    def test_the_assistant_without_a_provider_and_a_permission_revoked(self):
        import secret_store
        import workspace_ai

        ws, disk = self.ws, folder_of(self.root)
        before = e2e.ai_traffic(disk, e2e.NEGATIVE_PROJECT)
        self.assertEqual(before, {"logged_requests": 0, "tokens_today": 0, "local_log": False})
        empty = mock.Mock(get=lambda target: None, set=mock.Mock(), remove=lambda target: False)
        # Windows: a credential store (Credential Manager) holding no key.
        with mock.patch.object(secret_store, "backend", return_value=empty):
            ws.app.navigate("results")
            tile = ws.find("ai-panel", ft.ExpansionTile)
            self.assertTrue(re.match("^" + re.escape(T("assistant.title")), tile.title.value))
            ws.dispatch(tile.on_change, SimpleNamespace(control=tile, data="true"))
            self.assertEqual(first_outcome(ws, e2e.assistant_states()), "no_key")
            self.assertTrue(on_screen(ws, T("assistant.off_title")))
            self.assertFalse(ws.find_all("ai-send"))
            self.assertFalse(buttons(ws, "^" + re.escape(T("assistant.send", provider="\0",
                                                            model="").split("\0")[0])))
            self.assertEqual(label(ws, "ai-open-settings"), T("assistant.open_settings"))
            ws.click("ai-open-settings")
            self.assertEqual(ws.app.route, "settings")
            self.assertTrue(on_screen(ws, workspace_ai.t("en", "no_key", provider="OpenAI")))
            self.assertTrue(on_screen(ws, T("ai.unavailable")))

            # (c) Settings: the first "Allow" is the project overview; allowed, revoked.
            self.assertTrue(on_screen(ws, T("ai.sources", title=e2e.NEGATIVE_PROJECT)))
            allows = [c for c in ws.controls() if isinstance(c, ft.Checkbox)
                      and str(c.data).startswith("ai-allow-")]
            self.assertEqual(allows[0].data, "ai-allow-overview")
            self.assertEqual({c.label for c in allows}, {T("ai.allow")})
            ws.check("ai-allow-overview", True)
            self.assertEqual(e2e.permission(disk, e2e.NEGATIVE_PROJECT, "overview", 1), [1])
            chip = [c.value for c in ws.controls(ws.find("ai-status-overview"))
                    if isinstance(c, ft.Text)]
            self.assertEqual(chip, [T("ai.on")])
            ws.check("ai-allow-overview", False)
            self.assertEqual(e2e.permission(disk, e2e.NEGATIVE_PROJECT, "overview", 0), [0])
            logged = [json.loads(detail) for (detail,) in e2e.project_query(
                disk, e2e.NEGATIVE_PROJECT,
                "SELECT detail FROM events WHERE kind = 'ai_permission' ORDER BY id")]
            self.assertEqual(logged[-2:], [{"source": "overview", "allowed": True},
                                           {"source": "overview", "allowed": False}])
            ws.app.navigate("results")
            self.assertFalse(ws.find_all("ai-send"), "still nothing to send")
        self.assertEqual(e2e.ai_traffic(disk, e2e.NEGATIVE_PROJECT), before, "nothing was sent")

    def test_a_computer_without_a_credential_store_is_one_of_the_states(self):
        import secret_store
        import workspace_ai

        with mock.patch.object(secret_store, "backend",
                               side_effect=secret_store.SecretStoreUnavailable("none")):
            self.ws.app.navigate("results")
            self.assertEqual(first_outcome(self.ws, e2e.assistant_states()), "no_store")
            self.ws.click("ai-open-settings")
            self.assertTrue(on_screen(self.ws, workspace_ai.t("en", "no_store")))


if __name__ == "__main__":
    unittest.main()
