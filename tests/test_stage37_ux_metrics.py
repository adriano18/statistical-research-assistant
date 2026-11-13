"""Stage 37 (Issue #68): ``tools/ux_metrics.py`` runs, and counts by the rule.

The tool measures eight tasks through the real handlers (its numbers are the
baseline in docs/STAGE37_UX_METRICS.md). These tests check that it runs on
the synthetic fixtures and gives consistent numbers, that its counter
reproduces the Stage 36 count of the same flow, that its focus-loss detector
tells a moved field from one kept in place, and that its scroll estimate
lays controls out as declared. They do not pin the baseline itself: the UX
work is meant to change it.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from test_stage36_ux_baseline import LEVELS, eight_correlations  # noqa: E402
import ux_metrics as um  # noqa: E402


class LayoutEstimateTests(unittest.TestCase):
    def test_a_column_stacks_its_children_with_its_spacing(self):
        first, second = ft.Text("One line"), ft.Button(content="Two", height=40)
        layout = um.Layout(ft.Column([first, second], spacing=10), 800)
        _, y1, h1 = layout.boxes[id(first)]
        _, y2, h2 = layout.boxes[id(second)]
        self.assertEqual((y1, y2, h2), (0.0, h1 + 10, 40.0))
        self.assertEqual(layout.height, h1 + 10 + 40)

    def test_table_rows_keep_their_declared_height_and_never_wrap(self):
        rows = [ft.DataRow(cells=[ft.DataCell(ft.Text("A rather long parameter label " * 3))])
                for _ in range(10)]
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text("Parameter"))], rows=rows,
                             heading_row_height=40, data_row_min_height=36,
                             data_row_max_height=56)
        layout = um.Layout(table, 300)
        self.assertEqual(layout.height, 40 + 10 * 36)
        self.assertEqual(layout.boxes[id(rows[3])][1], 40 + 3 * 36)

    def test_an_inner_list_scrolls_apart_from_the_page(self):
        boxes = [ft.Checkbox(label=f"item {n}") for n in range(12)]
        inner = ft.Column(boxes, height=170, scroll=ft.ScrollMode.AUTO)
        layout = um.Layout(ft.Column([ft.Text("Above"), inner]), 600)
        self.assertEqual(layout.boxes[id(inner)][2], 170)
        scroller, y, _ = layout.boxes[id(boxes[5])]
        self.assertEqual((scroller, y), (id(inner), 5 * 50.0))
        self.assertEqual(layout.inner[id(inner)], (170, 12 * 40 + 11 * 10))

    def test_wrapped_checkboxes_flow_into_lines(self):
        boxes = [ft.Checkbox(label="SYN_LON_01 · Ordinal") for _ in range(10)]
        row = ft.Row(boxes, wrap=True, spacing=16, run_spacing=0)
        layout = um.Layout(row, 1000)
        per_line = sum(1 for box in boxes if layout.boxes[id(box)][1] == 0.0)
        self.assertGreater(per_line, 1)
        self.assertLess(per_line, 10)
        self.assertEqual(layout.height, 40.0 * -(-10 // per_line))

    def test_a_responsive_row_follows_the_window_width(self):
        tiles = [ft.Container(height=100, col={"xs": 12, "md": 6, "xl": 3}) for _ in range(4)]
        wide = um.Layout(ft.ResponsiveRow(tiles, spacing=10, run_spacing=10), 1100, 1440)
        narrow = um.Layout(ft.ResponsiveRow(tiles, spacing=10, run_spacing=10), 1100, 1100)
        self.assertEqual(wide.height, 100)
        self.assertEqual(narrow.height, 210)


class FocusPathTests(unittest.TestCase):
    """Flet 1.x keeps a rebuilt control's widget (and focus) when its place
    in the tree is the same; ``reconciliation_path`` names that place."""

    @staticmethod
    def page(*controls):
        return ft.Column(list(controls), key="workspace-page-test")

    def test_a_field_rebuilt_in_the_same_place_keeps_its_path(self):
        old, new = ft.TextField(data="f"), ft.TextField(data="f")
        self.assertEqual(um.reconciliation_path(self.page(ft.Text("a"), old), old),
                         um.reconciliation_path(self.page(ft.Text("b"), new), new))

    def test_a_control_inserted_above_moves_the_field(self):
        old, new = ft.TextField(data="f"), ft.TextField(data="f")
        self.assertNotEqual(
            um.reconciliation_path(self.page(ft.Text("a"), old), old),
            um.reconciliation_path(self.page(ft.Text("a"), ft.Text("notice"), new), new))

    def test_an_explicit_key_keeps_the_place_whatever_comes_before(self):
        old = ft.Container(ft.TextField(data="f"), key="kept")
        new = ft.Container(ft.TextField(data="f"), key="kept")
        self.assertEqual(
            um.reconciliation_path(self.page(ft.Text("a"), old), old.content),
            um.reconciliation_path(self.page(ft.Text("a"), ft.Text("notice"), new), new.content))

    def test_a_control_outside_the_tree_has_no_path(self):
        self.assertIsNone(um.reconciliation_path(self.page(ft.Text("a")), ft.TextField()))


class MeterTests(unittest.TestCase):
    """The Meter on the program's own start, in a temporary data folder."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.rec = um.Recorder()
        self.ws = um.Meter(Path(self.folder.name) / "data", self.rec)
        self.addCleanup(self.ws.close)
        self.ws.start()                          # outside a task: not counted

    def test_the_stage36_flow_counts_as_in_the_stage36_baseline(self):
        """Eight correlations: 8 interactions and 1 page change, exactly the
        count of ``test_stage36_ux_baseline`` for the same controls."""
        ws = self.ws
        fixtures = Path(self.folder.name) / "fixtures"
        fixtures.mkdir()
        ws.app.projects.create("Fictional UX study")
        assert ws.run(ws.app.load_path(str(fx.generator().create_csv(fixtures))))
        for name, level in LEVELS.items():
            ws.app.session.confirm_level(name, level)
        ws.page_seen()
        with self.rec.task(ws, "T4") as segment:
            eight_correlations(ws)
        self.assertEqual(segment.interactions, 8)
        self.assertEqual((segment.clicks, segment.checks, segment.dropdowns), (5, 1, 1))
        self.assertEqual(segment.pages, ["analyze"])
        self.assertEqual(segment.repeated, [])
        self.assertEqual(self.ws.app.session.results[-1].method, "batch_correlation")

    def test_a_typed_field_moved_by_a_render_is_a_focus_loss(self):
        ws, home = self.ws, self.ws.app.pages["home"]
        build = home.build
        state = {"notice": False, "where": 0}

        def built():
            body = build()
            if state["notice"]:
                column = body.controls[0].content
                column.controls.insert(state["where"], ft.Text("A notice", data="notice"))
            return body

        home.build = built

        def typed(e):
            state["notice"] = True
            ws.app.render()

        with self.rec.task(ws, "T1") as segment:
            state["where"] = 10_000             # appended at the end: the field stays
            ws.find("project-new-title").on_change = typed
            ws.type("project-new-title", "Fictional")
            self.assertEqual(segment.focus_losses, [])
            state["notice"], state["where"] = False, 0
            ws.app.render()
            ws.find("project-new-title").on_change = typed
            ws.type("project-new-title", "Fictional study")   # inserted above: moved
        self.assertEqual(segment.focus_losses, ["project-new-title"])
        self.assertEqual(segment.typed, 2)


class ToolRunTests(unittest.TestCase):
    """One full run of the eight tasks (about half a minute)."""

    @classmethod
    def setUpClass(cls):
        cls.results = um.measure()

    def test_eight_tasks_four_of_each_persona(self):
        tasks = self.results["tasks"]
        self.assertEqual([t["task"] for t in tasks], [f"T{n}" for n in range(1, 9)])
        self.assertEqual(sorted(t["persona"] for t in tasks), ["novice"] * 4 + ["supervisor"] * 4)
        self.assertEqual(sorted(t["run_order"] for t in tasks), list(range(1, 9)))

    def test_the_numbers_are_consistent(self):
        counts = ("interactions", "typed", "page_changes", "dialogs", "repeated_selections",
                  "focus_losses", "scroll_px_estimate")
        for task in self.results["tasks"]:
            with self.subTest(task=task["task"]):
                for name in counts:
                    self.assertIsInstance(task[name], int)
                    self.assertGreaterEqual(task[name], 0)
                self.assertEqual(task["interactions"],
                                 task["clicks"] + task["checkboxes"] + 2 * task["dropdowns"])
                self.assertEqual(task["interactions"],
                                 sum(s["interactions"] for s in task["segments"]))
                self.assertEqual(task["page_changes"],
                                 sum(len(s["pages"]) for s in task["segments"]))
                self.assertGreater(task["interactions"], 0)
        for persona, total in self.results["personas"].items():
            rows = [t for t in self.results["tasks"] if t["persona"] == persona]
            for name in counts:
                self.assertEqual(total[name], sum(t[name] for t in rows), (persona, name))

    def test_every_task_produced_what_it_names(self):
        facts = {t["task"]: {k: v for s in t["segments"] for k, v in s["facts"].items()}
                 for t in self.results["tasks"]}
        self.assertTrue(facts["T3"]["alpha"])
        self.assertEqual(facts["T3"]["score"], um.LON_SCORE)
        self.assertEqual(facts["T4"]["pairs"], 8)
        self.assertEqual(facts["T5"]["method"], "spearman")
        self.assertTrue(facts["T6"]["file"].endswith(".docx"))
        self.assertEqual(facts["T7"]["results"], 2)
        self.assertEqual(facts["T8"]["language"], "lv")
        self.assertGreaterEqual(len(self.results["tasks"][7]["segments"]), 2,
                                "T8 goes on at the next start")

    def test_the_reports(self):
        json.dumps(self.results)
        table = um.markdown(self.results)
        self.assertEqual(sum(line.startswith("| T") for line in table.splitlines()), 8)
        self.assertIn("**novice**", table)
        self.assertIn("**supervisor**", table)
        self.assertIn("Scroll px (est.)", um.text_report(self.results))

    def test_the_command_line_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(um, "measure", return_value=self.results), \
                mock.patch("builtins.print"):
            out = Path(folder)
            self.assertEqual(um.main(["--json", str(out / "m.json"),
                                      "--markdown", str(out / "m.md")]), 0)
            self.assertEqual(json.loads((out / "m.json").read_text(encoding="utf-8")),
                             self.results)
            self.assertIn("| T8 |", (out / "m.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
