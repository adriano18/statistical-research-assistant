"""Stage 36.8 review findings K1 and K2 (#62): the flows of the packaged-
program journeys `confirmations` and `report-composition`, through the
harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. These tests walk the same flows in the workspace
harness and check, at each point, that every text, button name and box the
journey waits for is there in that state, with the journey's own texts and
helpers. The packaged program cannot show a disabled button as disabled
(docs/STAGE368_A11Y_AND_LOCALE.md §1); the harness can, so here it is also
checked that the buttons the journey presses before re-confirming are
disabled, which is why those presses add no result on Windows. Synthetic
data only.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from test_stage368_acceptance import (  # noqa: E402
    T, accept_levels_in_ui, create_project_in_ui, folder_of, guided, label, on_screen,
    open_csv,
)
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402


def boxes(ws) -> dict[str, bool]:
    """The confirmation boxes on screen (a variable's box reads "Age · …")."""
    return {c.label: bool(c.value) for c in ws.controls()
            if isinstance(c, ft.Checkbox) and isinstance(c.label, str) and " · " not in c.label
            and str(c.data).startswith("design-confirm-")}


def in_card(ws, data: str, tooltip: str) -> ft.IconButton:
    """The icon button named ``tooltip`` in the card ``data`` (a report entry):
    the journey presses it by its name in that entry's row."""
    found = [c for c in ws.controls(ws.find(data)) if isinstance(c, ft.IconButton)
             and c.tooltip == tooltip]
    assert len(found) == 1, (data, tooltip, found)
    return found[0]


def card_title(ws, entry) -> str:
    """The entry's line on the Reports page, "1. Descriptive: UCLA"."""
    texts = [c.value for c in ws.controls(ws.find(f"report-item-{entry.id}"))
             if isinstance(c, ft.Text)]
    return texts[0]


def notes_value(ws) -> str:
    field = ws.find("result-notes")
    assert field.label == T("results.notes")
    return field.value or ""


class JourneyOrderTests(unittest.TestCase):
    def test_the_review_journeys_follow_the_others(self):
        self.assertEqual(list(e2e.JOURNEYS)[16:], ["confirmations", "report-composition"])
        self.assertEqual(len(e2e.JOURNEYS), 18)


class ConfirmationsJourneyTests(unittest.TestCase):
    """Journey `confirmations` (K1, spec B: change the variables, run again)."""

    def test_other_outcomes_after_a_run_then_another_group(self):
        from workspace_methods import advise

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ws = Workspace(root=root)
            self.addCleanup(ws.close)
            disk, title = folder_of(root), e2e.CONFIRMATIONS_PROJECT
            labels = e2e.group_confirmations()
            design, data = labels["design"], labels["data"]
            self.assertEqual((design, data), (
                "I confirm the groups contain independent participants",
                "I reviewed the outcome distributions, outliers and group sizes"))
            create_project_in_ui(ws, title)
            open_csv(ws, fx.generator().create_csv(root))
            accept_levels_in_ui(ws)

            # UCLA_Level (3 groups), the eight scales, both confirmations, Run.
            guided(ws)
            self.assertTrue(ws.has_text(T("goal.compare")))
            ws.click("goal-compare")
            group = ws.find("role-group", ft.Dropdown)
            self.assertEqual(group.label, T("role.group"))
            self.assertEqual([o.text for o in group.options], e2e.stage36_options())
            ws.choose("role-group", "UCLA_Level")
            self.assertEqual(label(ws, "role-outcome-all-scale"), T("pick.all_scale", count=10))
            ws.click("role-outcome-all-scale")
            for name in ("Age", "UCLA"):
                self.assertEqual(ws.find(f"role-outcome-{name}").label,
                                 e2e.option_label(name, "scale"))
                ws.check(f"role-outcome-{name}", False)
            self.assertTrue(on_screen(ws, "fewer than five values"))
            self.assertEqual(ws.find("design-confirm-independent").label, design)
            self.assertEqual(ws.find("design-confirm-assumptions").label, data)
            ws.check("design-confirm-independent")
            ws.check("design-confirm-assumptions")
            self.assertRegex(label(ws, "guided-run"), e2e.run_button())
            ws.click("guided-run")
            self.assertTrue(on_screen(ws, T("task.title_compare", group="UCLA_Level", count=8)))
            self.assertEqual([sorted(r) for r in e2e.group_runs(disk, title)],
                             [sorted(fx.SCALES)])

            # After the run: Change variables, one scale left out.
            self.assertEqual(ws.app.route, "analyze", "the researcher stays in the task")
            self.assertEqual(label(ws, "task-change-variables"), T("task.change_variables"))
            ws.click("task-change-variables")
            dropped = fx.SCALES[0]
            self.assertEqual(ws.find(f"role-outcome-{dropped}").label,
                             e2e.option_label(dropped, "scale"))
            ws.check(f"role-outcome-{dropped}", False)
            self.assertEqual(boxes(ws), {design: True, data: False})
            self.assertTrue(on_screen(ws, T("design.reconfirm")))

            # Run, Ctrl+Enter, Run again: nothing is added before re-confirming.
            self.assertTrue(ws.find("guided-run").disabled, "the journey's click is a no-op")
            self.assertEqual(label(ws, "task-rerun"), T("task.rerun"))
            self.assertNotRegex(label(ws, "task-rerun"), e2e.run_button())
            self.assertTrue(ws.find("task-rerun").disabled, "the journey's click is a no-op")
            self.assertEqual(e2e.project_runs(disk, title), 1)
            ws.key("Enter", ctrl=True)
            self.assertEqual(e2e.project_runs(disk, title), 1, "Ctrl+Enter ran nothing")
            self.assertEqual(e2e.runs_after(disk, title, 1, wait=0), 1)
            self.assertTrue(on_screen(ws, T("disabled.confirm_first")), "said in the status line")

            # The data confirmation given again: seven outcomes.
            ws.check("design-confirm-assumptions")
            self.assertFalse(on_screen(ws, T("design.reconfirm")))
            ws.click("guided-run")
            self.assertEqual(e2e.runs_after(disk, title, 1, wait=0), 2)
            runs = e2e.group_runs(disk, title)
            self.assertEqual([sorted(r) for r in runs], [sorted(fx.SCALES), sorted(fx.SCALES[1:])])
            self.assertTrue(on_screen(ws, T("task.versions", count=2)))

            # Another grouping variable, Sex (two groups): both cleared.
            self.assertIn(e2e.option_label("Sex", "nominal"),
                          [o.text for o in ws.find("role-group", ft.Dropdown).options])
            ws.choose("role-group", "Sex")
            page = ws.app.pages["analyze"]
            method, options, _ = page._chosen(advise(page.goal, page.selection, ws.app.session))
            self.assertEqual((method, options.get("two_group_method")), ("batch_groups", "welch"),
                             "a two-group test of each outcome")
            two = e2e.group_confirmations({"two_group_method": "welch"})
            self.assertEqual(boxes(ws), {two["design"]: False, two["data"]: False})
            # The journey takes every box whose name lacks " · " (a variable's
            # box reads "Age · Quantitative"): exactly the confirmations.
            unnamed_variables = [c.label for c in ws.controls() if isinstance(c, ft.Checkbox)
                                 and " · " not in c.label]
            self.assertEqual(unnamed_variables, list(boxes(ws)))
            self.assertTrue(on_screen(ws, T("design.reconfirm")))


class ReportCompositionJourneyTests(unittest.TestCase):
    """Journey `report-composition` (K2, spec G: the composition survives a restart)."""

    def test_order_entries_and_settings_come_back_and_reach_the_word_report(self):
        import research_report as rr
        from interpretation_wizard import METHOD_PROFILES

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disk = folder_of(root)
            csv_path = fx.generator().create_csv(root)
            batch = e2e.batch_title(csv_path)
            checks = e2e.report_checks(batch)
            self.assertEqual((batch, checks["reviewed"]), (
                "Spearman ρ: UCLA with 8 variables",
                "Confirm measurement levels and independence of observations"))
            ws = Workspace(root=root)
            try:
                create_project_in_ui(ws, e2e.REPORT_PROJECT)
                open_csv(ws, csv_path)
                accept_levels_in_ui(ws)

                # run_eight_correlations, then into the report.
                guided(ws)
                self.assertTrue(ws.has_text(T("goal.relate")))
                ws.click("goal-relate")
                ws.choose("role-x", "UCLA")
                self.assertEqual(label(ws, "role-y-all-scale"), T("pick.all_scale", count=9))
                ws.click("role-y-all-scale")
                ws.check("role-y-Age", False)
                self.assertEqual(label(ws, "alt-batch_correlation-spearman"), T("rec.use_instead"))
                ws.click("alt-batch_correlation-spearman")
                self.assertRegex(label(ws, "guided-run"), "^" + re.escape(T("rec.run", method=""))
                                 + "Spearman")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    ws.click("guided-run")
                self.assertTrue(on_screen(ws, T("task.title_relate", x="UCLA", count=8)))
                first = ws.app.session.results[-1]
                self.assertEqual(first.title, batch, "the engine's title the journey expects")
                self.assertEqual(label(ws, "task-add-report"), T("results.add_report"))
                ws.click("task-add-report")
                self.assertEqual(label(ws, "task-add-report"), T("results.in_report"))

                # A description of UCLA, then into the report.
                self.assertEqual(label(ws, "task-new"), T("task.new"))
                ws.click("task-new")
                self.assertTrue(ws.has_text(T("goal.describe")), "click_chip(goal.describe)")
                ws.click("goal-describe")
                variable = ws.find("role-variable", ft.Dropdown)
                self.assertEqual([o.text for o in variable.options], e2e.stage36_options())
                ws.choose("role-variable", "UCLA")
                self.assertRegex(label(ws, "guided-run"), e2e.run_button())
                ws.click("guided-run")
                second = ws.app.session.results[-1]
                self.assertEqual(second.title, e2e.DESCRIPTIVE_UCLA)
                self.assertTrue(on_screen(ws, e2e.DESCRIPTIVE_UCLA))
                self.assertEqual(label(ws, "result-add-report"), T("results.add_report"))
                ws.click("result-add-report")
                self.assertEqual(label(ws, "result-add-report"), T("results.in_report"))

                # Reports: Move up on the description's entry.
                ws.click("nav-reports")
                self.assertEqual(card_title(ws, first), f"1. {batch}")
                self.assertEqual(card_title(ws, second), f"2. {e2e.DESCRIPTIVE_UCLA}")
                move = in_card(ws, f"report-item-{second.id}", T("reports.move_up"))
                self.assertFalse(move.disabled)
                ws.dispatch(move.on_click, SimpleNamespace(control=move))
                self.assertEqual(card_title(ws, second), f"1. {e2e.DESCRIPTIVE_UCLA}")
                self.assertEqual(card_title(ws, first), f"2. {batch}")

                # The batch result: one check reviewed and a note.
                show = in_card(ws, f"report-item-{first.id}", T("reports.open_result"))
                ws.dispatch(show.on_click, SimpleNamespace(control=show))
                self.assertEqual((ws.app.route, ws.app.session.selected_result),
                                 ("results", first.id))
                self.assertTrue(on_screen(ws, batch))
                self.assertEqual(ws.find("review-0").label, checks["reviewed"])
                self.assertEqual(ws.find("review-1").label, checks["open"])
                ws.check("review-0", True)
                tile = ws.find("result-interpretation-section", ft.ExpansionTile)
                self.assertTrue(re.match("^" + re.escape(T("results.interpretation")) + r"(\n|$)",
                                         tile.title.value))
                ws.dispatch(tile.on_change, SimpleNamespace(control=tile, data="true"))
                self.assertEqual(notes_value(ws), "")
                ws.type("result-notes", e2e.REPORT_NOTE)
                self.assertEqual(e2e.saved_entries(disk, e2e.REPORT_PROJECT, "batch_correlation"),
                                 {"note": e2e.REPORT_NOTE, "reviewed": [checks["reviewed"]]})

                # The title (saved when the field is left), a section out, Latvian.
                ws.click("nav-reports")
                field = ws.find("reports-study-title")
                self.assertEqual(field.label, T("reports.study_title"))
                ws.type("reports-study-title", e2e.REPORT_TITLE)
                ws.dispatch(field.on_blur, SimpleNamespace(control=field))
                limitations = ws.find(f"reports-section-{e2e.LEFT_OUT}")
                self.assertRegex(limitations.label, e2e.section_pattern("en"))
                ws.check(f"reports-section-{e2e.LEFT_OUT}", False)
                language = ws.find("reports-language", ft.Dropdown)
                self.assertEqual(language.label, T("reports.language"))
                self.assertEqual([o.text for o in language.options], e2e.REPORT_LANGUAGES)
                ws.choose("reports-language", "lv")
                limitations = ws.find(f"reports-section-{e2e.LEFT_OUT}")
                self.assertRegex(limitations.label, e2e.section_pattern("lv"))
                self.assertIn(T("reports.section_off"), limitations.label)
                settings = [json.loads(detail) for (detail,) in e2e.project_query(
                    disk, e2e.REPORT_PROJECT,
                    "SELECT detail FROM events WHERE kind = 'report_settings' ORDER BY id")]
                self.assertEqual(settings[-1], {"title": e2e.REPORT_TITLE,
                                                "sections_off": [e2e.LEFT_OUT], "language": "lv"})
                project_id = ws.app.projects.info().id
            finally:
                ws.close()

            # Restart: open the project from Home.
            again = Workspace(root=root)
            try:
                again.click("nav-home")
                again.click(f"project-open-{project_id}")
                session = again.app.session
                restored = {entry.title: entry for entry in session.results}
                again.click("nav-reports")
                self.assertEqual(card_title(again, restored[e2e.DESCRIPTIVE_UCLA]),
                                 f"1. {e2e.DESCRIPTIVE_UCLA}")
                self.assertEqual(card_title(again, restored[batch]), f"2. {batch}")
                self.assertEqual(again.find("reports-study-title").value, e2e.REPORT_TITLE)
                limitations = again.find(f"reports-section-{e2e.LEFT_OUT}")
                self.assertFalse(limitations.value)
                self.assertRegex(limitations.label, e2e.section_pattern("lv"))
                self.assertIn(T("reports.section_off"), limitations.label)
                self.assertRegex(again.find("reports-section-descriptives").label,
                                 e2e.section_pattern("lv", "descriptives"))
                show = in_card(again, f"report-item-{restored[batch].id}", T("reports.open_result"))
                again.dispatch(show.on_click, SimpleNamespace(control=show))
                self.assertTrue(again.find("review-0").value)
                self.assertFalse(again.find("review-1").value)
                self.assertEqual(notes_value(again), e2e.REPORT_NOTE)

                # The Word report.
                again.click("nav-reports")
                self.assertEqual(label(again, "reports-export-docx"), T("reports.export_docx"))
                again.click("reports-export-docx")
                path = again.saved[-1]
                self.assertEqual(e2e.report_order(path, "lv"), {
                    "data_and_sample": [e2e.DESCRIPTIVE_UCLA, batch],
                    "appendix": [e2e.DESCRIPTIVE_UCLA, batch]})
                from docx import Document

                document = Document(str(path))
                text = "\n".join(p.text for p in document.paragraphs)
                for fragment in (e2e.REPORT_TITLE, checks["reviewed_lv"], checks["open_lv"],
                                 e2e.REPORT_NOTE):
                    self.assertIn(fragment, text)
                headings = [p.text for p in document.paragraphs
                            if p.style.name.startswith("Heading")]
                self.assertTrue(headings, "the journey reads the headings by their style")
                self.assertTrue(any(rr.text("lv", "descriptives") in h for h in headings))
                self.assertFalse(any(rr.text("lv", e2e.LEFT_OUT) in h for h in headings))
                self.assertNotIn(rr.text("lv", e2e.LEFT_OUT), text)

                # A second project created in the hub shows none of it.
                create_project_in_ui(again, e2e.SECOND_REPORT_PROJECT)
                open_csv(again, csv_path)
                accept_levels_in_ui(again)
                guided(again)
                again.click("goal-describe")
                again.choose("role-variable", "UCLA")
                again.click("guided-run")
                self.assertTrue(on_screen(again, e2e.DESCRIPTIVE_UCLA))
                described = [again.find(f"review-{i}") for i in range(3)]
                self.assertEqual([box.label for box in described],
                                 list(METHOD_PROFILES["descriptive"].assumptions))
                self.assertFalse(any(box.value for box in described))
                self.assertEqual(notes_value(again), "")
                again.click("result-add-report")
                again.click("nav-reports")
                entries = again.app.session.report_entries()
                self.assertEqual([card_title(again, entry) for entry in entries],
                                 [f"1. {e2e.DESCRIPTIVE_UCLA}"])
                self.assertEqual(again.find("reports-study-title").value, "")
                limitations = again.find(f"reports-section-{e2e.LEFT_OUT}")
                self.assertTrue(limitations.value)
                self.assertRegex(limitations.label, e2e.section_pattern("en"))
                self.assertNotIn(T("reports.section_off"), limitations.label)
                self.assertEqual(again.find("reports-language").value, "en")
            finally:
                again.close()


if __name__ == "__main__":
    unittest.main()
