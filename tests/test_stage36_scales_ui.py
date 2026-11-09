"""Stage 36.3 in the workspace: groups from a scale, item diagnostics, D5.

Synthetic data only (tests/fixtures/stage36). The groups card previews
every group before anything is created, the score is never changed, the
rule is kept in the project's history, and an existing grouping is offered
instead of being re-created. Item diagnostics run from the guided scale
question; totals get no α or ω, also among all methods.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import stage36_fixtures as fx  # noqa: E402
from test_stage36_ux_baseline import (  # noqa: E402
    LEVELS, CountingWorkspace, prepared_workspace)


def rows(ws) -> list[tuple[str, str, str]]:
    table = ws.find("groups-preview")
    return [tuple(cell.content.value for cell in row.cells[:3]) for row in table.rows]


class GroupsFromScaleTests(unittest.TestCase):
    def setUp(self):
        self.ws = prepared_workspace()
        self.addCleanup(self.ws.close)
        self.ws.click("nav-data")
        self.ws.choose("groups-source", "UCLA")

    def test_an_existing_grouping_is_offered_not_recreated(self):
        ws = self.ws
        self.assertTrue(ws.find("groups-existing-UCLA_Level"))
        self.assertTrue(ws.has_text("UCLA_Level already groups UCLA"))
        ws.click("groups-use-UCLA_Level")
        page = ws.app.pages["analyze"]
        self.assertEqual(ws.app.route, "analyze")
        self.assertEqual((page.goal, page.selection.get("group")), ("compare", "UCLA_Level"))
        self.assertNotIn("UCLA_groups", ws.app.session.df.columns, "nothing was created")

    def test_quantile_groups_preview_then_create_a_new_variable(self):
        ws, s = self.ws, self.ws.app.session
        before = s.df["UCLA"].copy()
        ws.choose("groups-k", "3")
        expected = pd.qcut(before, 3).value_counts(sort=False).tolist()
        self.assertEqual([int(n) for _, _, n in rows(ws)], expected)
        self.assertTrue(ws.has_text("They depend on this sample and are not norms"))
        self.assertEqual(rows(ws)[0][1], "[37, 46]", "bounds and inclusivity are shown")
        ws.click("groups-create")
        self.assertIn("UCLA_groups", s.df.columns)
        pd.testing.assert_series_equal(s.df["UCLA"], before, obj="the score itself")
        self.assertTrue(s.df["UCLA_groups"].cat.ordered)
        self.assertEqual(list(s.df["UCLA_groups"].cat.categories), ["Q1", "Q2", "Q3"])
        self.assertEqual(s.variables["UCLA_groups"].confirmed, "ordinal")
        self.assertEqual(s.level("AssertiveAction"), "scale", "other levels are kept")
        project = ws.app.projects.project
        steps = project.transformations(ws.app.projects.dataset_id)
        self.assertEqual([t["kind"] for t in steps], ["scale_groups"])
        self.assertEqual(steps[0]["output_columns"], ["UCLA_groups"])
        self.assertEqual(steps[0]["params"]["source"], "UCLA")
        origins = [d.origin for d in project.datasets()]
        self.assertEqual(origins, ["copy", "derived"], "a new version; the original stays")
        self.assertTrue(ws.has_text("UCLA itself is unchanged"))

    def test_documented_cut_points_need_their_source_and_are_not_called_norms(self):
        ws = self.ws
        ws.segment("groups-method", "documented")
        ws.type("groups-cuts", "39; 59")
        ws.type("groups-labels", "Lower; Middle; Higher")
        ws.click("groups-refresh")
        self.assertTrue(ws.has_text("Name the source of documented cut points"))
        self.assertFalse(ws.find_all("groups-create"))
        ws.type("groups-citation", "Fictional manual, 2nd ed., p. 12")
        ws.click("groups-refresh")
        self.assertEqual([(g, r, n) for g, r, n in rows(ws)],
                         [("Lower", "≤ 39", "3"), ("Middle", "(39, 59]", "47"),
                          ("Higher", "> 59", "5")])
        statement = " ".join(t for t in ws.texts() if "Fictional manual" in t)
        self.assertIn("This program has not checked them", statement)
        self.assertNotIn("norm", statement.lower())
        self.assertTrue(ws.find("groups-warning-groups.small"), "groups under five are warned")

    def test_new_groups_go_straight_to_a_batch_comparison(self):
        ws = self.ws
        ws.choose("groups-k", "3")
        ws.click("groups-create")
        ws.click("groups-use-UCLA_groups")
        for scale in fx.SCALES:
            ws.check(f"role-outcome-{scale}")
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "batch_groups")
        self.assertEqual(entry.run.result.group, "UCLA_groups")
        self.assertEqual(len(entry.run.result.rows), 8)

    def test_the_derived_variable_and_its_history_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                ws.click("nav-data")
                ws.choose("groups-source", "UCLA")
                ws.choose("groups-k", "3")
                ws.click("groups-create")
                project_id = ws.app.projects.info().id
            finally:
                ws.close()
            again = CountingWorkspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                s = again.app.session
                self.assertIn("UCLA_groups", s.df.columns)
                self.assertEqual(s.level("UCLA_groups"), "ordinal")
                steps = again.app.projects.project.transformations(again.app.projects.dataset_id)
                self.assertEqual([t["kind"] for t in steps], ["scale_groups"])
            finally:
                again.close()

    def test_the_card_speaks_latvian_and_russian(self):
        for language, words in (("lv", "Izveidot grupas no skalas"),
                                ("ru", "Создать группы по шкале")):
            self.ws.app.set_language(language)
            self.ws.click("nav-data")
            self.assertTrue(self.ws.has_text(words))
            raw = [t for t in self.ws.texts() if t.startswith("groups.")]
            self.assertEqual(raw, [], language)


class ItemDiagnosticsWorkspaceTests(unittest.TestCase):
    def workspace(self):
        ws = CountingWorkspace()
        self.addCleanup(ws.close)
        ws.app.projects.create("Fictional scale study")
        self.assertTrue(ws.run(ws.app.load_path(str(fx.fixture(fx.ITEMS_CSV)))))
        s = ws.app.session
        s.confirm_level("Code", "id")
        for item in fx.ITEMS:
            s.confirm_level(item, "ordinal")
        s.confirm_level(fx.ITEM_TOTAL, "scale")
        return ws

    def test_the_scale_question_gives_alpha_omega_and_every_item(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-scale")
        for item in fx.ITEMS:
            ws.check(f"role-items-{item}")
        self.assertTrue(ws.has_text("Scale quality: α, ω and item diagnostics"))
        ws.check("design-confirm-one_construct")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "item_diagnostics")
        result = entry.run.result
        self.assertEqual(result.flagged_reverse, tuple(fx.REVERSE_ITEMS))
        self.assertEqual(len(entry.run.tables[0].rows), len(fx.ITEMS))
        self.assertTrue(entry.run.png.startswith(b"\x89PNG"))
        self.assertIn("nothing was recoded", entry.run.report)
        from result_store import from_json
        record = ws.app.projects.project.run(entry.record_id)
        self.assertEqual(from_json(record.structured).alpha.value, result.alpha.value,
                         "the structured result is stored with the project")

    def test_totals_are_explained_and_need_a_confirmation_among_all_methods(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        ws.click("method-alpha")
        for scale in fx.SCALES[:4]:
            ws.check(f"form-items-{scale}")
        self.assertTrue(ws.find("form-totals"))
        self.assertTrue(ws.has_text("Only a total score is available now"), ws.texts()[-12:])
        ws.check("form-confirm-construct")
        self.assertTrue(ws.find("form-run").disabled, "no α on totals without a confirmation")
        # The heuristic cannot be certain (0–100 visual-analogue items look like
        # totals): the researcher may state that these are item responses.
        ws.check("form-confirm-items_not_totals")
        self.assertFalse(ws.find("form-run").disabled)
        ws.check(f"form-items-{fx.SCALES[4]}")
        self.assertFalse(ws.app.pages["analyze"].form_confirms.get("items_not_totals"),
                         "a confirmation is given for the columns it was given for")
        self.assertTrue(ws.find("form-run").disabled)

    def test_item_diagnostics_among_all_methods_record_the_confirmation(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        ws.click("method-item_diagnostics")
        for scale in fx.SCALES[:4]:
            ws.check(f"form-items-{scale}")
        ws.choose("form-option-ci", "0")
        ws.check("form-confirm-one_construct")
        ws.check("form-confirm-items_not_totals")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ws.click("form-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.method, "item_diagnostics")
        self.assertTrue(entry.run.inputs["items_confirmed"])
        self.assertIn("I checked that these columns hold answers to single items, "
                      "not total or mean scores", entry.confirmations)

    def test_factor_analysis_is_not_a_reliability_coefficient(self):
        import workspace_methods as wm

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        roles = {"items": list(fx.SCALES[:4])}
        self.assertIsNone(wm.total_score_problem(wm.METHODS["factor"], roles, ws.app.session))
        self.assertEqual(wm.role_problems(wm.METHODS["factor"], roles, ws.app.session), [])


class GroupsUxTests(unittest.TestCase):
    def test_create_groups_from_a_scale_in_at_most_five_interactions(self):
        """UX audit row: scale, rule, preview, create — target ≤ 5."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.counts.clear()
        ws.click("nav-data")
        ws.choose("groups-source", "UCLA")
        ws.click("groups-create")            # quantiles, three groups: the defaults
        self.assertIn("UCLA_groups", ws.app.session.df.columns)
        self.assertLessEqual(ws.total, 5)
        print(f"\n[ux] create groups from a scale: {ws.total} interactions "
              "(before Stage 36: not available)")


if __name__ == "__main__":
    unittest.main()
