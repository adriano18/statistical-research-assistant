"""Stage 37 (Issue #68, review UX-3, U2, D7): the variable panel and reuse.

* The panel of every multiple role (guided step 2, the All-methods form, and
  the items of a scale score in Data → Prepare): search by a part of a
  name, a pattern or a range; name groups (a 20-item set in one action);
  select or unselect what is shown; clear; a visible count.
* Only the variables a role can take are listed (D7): the grouping variable
  and the outcome are never offered as covariates, and every variable left
  out is named with its reason, as text.
* Reuse: a task duplicated, a result repeated with changes, recent methods,
  the items of a scale score. Nothing confirmed is ever copied (K1): every
  confirmation is given again, for the analysis it is given for.
* Keyboard and UI Automation: the panel's controls are ordinary focusable
  controls in reading order, each named by its text.
* The Windows journey ``variable-picker`` (tools/windows_gui_e2e.py), walked
  here with the journey's own texts, numbers and counts.

Synthetic data only: the Stage 36 fixtures, the bundled sample_ancova.csv
and the Stage 37 master fixture (180 fictional cases, generated here).
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
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from test_stage368_acceptance import (  # noqa: E402
    T, accept_levels_in_ui, create_project_in_ui, folder_of, guided, label, open_csv,
)
from test_stage36_ux_baseline import CountingWorkspace, prepared_workspace  # noqa: E402
import ux_metrics as um  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402
import workspace_variables as wv  # noqa: E402

LON = tuple(f"SYN_LON_{n:02d}" for n in range(1, 21))
COPE = tuple(f"SYN_COPE_{n:02d}" for n in range(1, 53))


def run(ws, data: str):
    """A Run button press; the engines' numeric warnings are not the point."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ws.click(data)


def boxes(ws, key: str) -> list[str]:
    """The variables a panel lists, in order (its boxes' names)."""
    prefix = f"{key}-"
    return [c.data[len(prefix):] for c in ws.find_all(prefix) if isinstance(c, ft.Checkbox)]


def text_of(ws, data: str) -> str:
    return ws.find(data).value


def submit(ws, data: str, value: str):
    """Enter in a text field: Flet's on_submit with the field's value."""
    field = ws.find(data, ft.TextField)
    field.value = value
    return ws.dispatch(field.on_submit, SimpleNamespace(control=field, data=value))


class MasterFixture:
    """The Stage 37 master fixture, generated once per test class."""

    folder: tempfile.TemporaryDirectory | None = None
    csv: Path

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.csv = e2e.master_fixture(Path(cls.folder.name))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def workspace(self, root: Path | None = None) -> CountingWorkspace:
        ws = CountingWorkspace(root=root)
        self.addCleanup(ws.close)
        ws.app.projects.create("Fictional master study")
        self.assertTrue(ws.run(ws.app.load_path(str(self.csv))))
        ws.check("data-accept-confirm")
        ws.click("data-accept")
        ws.counts.clear()
        return ws


# ===================================================================== logic
class PanelLogicTests(unittest.TestCase):
    NAMES = ["participant_code", "age_years", *LON, "SYN_SUP_01", "SYN_SUP_02",
             "SYN_LON_TOTAL", "SYN_WELL_0_100", "q1", "q10", "Q2", "7"]

    def test_name_groups_are_numbered_names_with_one_stem(self):
        groups = dict(wv.name_groups(self.NAMES))
        self.assertEqual(list(groups), ["SYN_LON_", "SYN_SUP_", "q"])
        self.assertEqual(groups["SYN_LON_"], list(LON))
        self.assertEqual(groups["q"], ["q1", "q10"])
        self.assertNotIn("SYN_WELL_0_", groups, "one member is no group")
        self.assertEqual(wv.group_pattern("SYN_LON_"), "SYN_LON_*")

    def test_a_part_of_a_name_a_pattern_a_range_or_several(self):
        names = self.NAMES
        self.assertEqual(wv.filter_names(names, "lon_0"), list(LON[:9]))
        self.assertEqual(wv.filter_names(names, "SYN_LON_?5"), ["SYN_LON_05", "SYN_LON_15"])
        self.assertEqual(wv.filter_names(names, "SYN_LON_05..SYN_LON_08"), list(LON[4:8]))
        self.assertEqual(wv.filter_names(names, "syn_lon_08..SYN_LON_05"), list(LON[4:8]),
                         "either way round, in column order")
        span = ["SYN_LON_19", "SYN_LON_20", "SYN_SUP_01", "SYN_SUP_02"]
        for query in ("SYN_LON_19 – SYN_SUP_02", "SYN_LON_19 to SYN_SUP_02",
                      "SYN_LON_19…SYN_SUP_02"):
            self.assertEqual(wv.filter_names(names, query), span, query)
        self.assertEqual(wv.filter_names(names, "SYN_LON_01, SYN_SUP_*; q1"),
                         ["SYN_LON_01", "SYN_SUP_01", "SYN_SUP_02", "q1", "q10"])
        self.assertEqual(wv.filter_names(names, "SYN_LON_01 SYN_LON_03"),
                         ["SYN_LON_01", "SYN_LON_03"], "names separated by spaces")
        self.assertEqual(wv.filter_names(names, "SYN_LON_01..NOT_A_VARIABLE"), [])
        self.assertEqual(wv.filter_names(names, "   "), names)

    def test_a_range_counts_the_data_order_and_keeps_only_offered_names(self):
        offered = [n for n in self.NAMES if n not in ("participant_code", "SYN_LON_02")]
        self.assertEqual(wv.filter_names(offered, "participant_code..SYN_LON_03", self.NAMES),
                         ["age_years", "SYN_LON_01", "SYN_LON_03"])

    def test_added_names_follow_the_chosen_ones(self):
        self.assertEqual(wv.merged(["b", "a"], ["a", "c", "d"]), ["b", "a", "c", "d"])

    def test_left_out_variables_have_a_reason(self):
        from workspace_methods import GOAL_ROLES
        from workspace_state import VariableInfo

        def info(name, suggested="ordinal", confirmed="ordinal", binary=False):
            return VariableInfo(name, "number", suggested, 0, 3, binary, confirmed, "data")

        session = SimpleNamespace(variables={
            "code": info("code", "id", "unknown"), "group": info("group", "nominal", "nominal"),
            "x1": info("x1", "scale", "scale"), "x2": info("x2", "scale", "scale"),
            "fresh": info("fresh", "scale", "unknown"), "item": info("item")})
        roles = GOAL_ROLES["compare"]
        covariates = next(r for r in roles if r.key == "covariates")
        taken = wv.taken_by_others(roles, {"group": "group", "outcome": ["x1"]}, "covariates")
        self.assertEqual(taken, {"group": "group", "x1": "outcomes"}, "one of the outcomes")
        offered, left_out = wv.offered_variables(session, covariates, taken)
        self.assertEqual(offered, ["x2", "fresh"], "a level still to confirm is offered")
        self.assertEqual([(n.name, n.reason, n.detail) for n in left_out],
                         [("code", "identifier", ""), ("group", "role", "group"),
                          ("x1", "role", "outcomes"), ("item", "level", "ordinal")])

    def test_the_reasons_read_as_text_in_each_language(self):
        from workspace_components import Ui
        import workspace_tokens as tk

        left_out = [wv.NotOffered("code", "identifier"), wv.NotOffered("UCLA_Level", "role", "group"),
                    *[wv.NotOffered(f"i{n}", "level", "ordinal") for n in range(11)]]
        for language in ("en", "lv", "ru"):
            ui = Ui(tk.palette("light", "blue"), language)
            lines = wv.not_offered_lines(ui, left_out, ("scale",))
            self.assertEqual(len(lines), 3, language)
            self.assertIn("code", lines[0])
            self.assertIn(ui.t("vars.role.group"), lines[1])
            self.assertIn(ui.t("level.ordinal"), lines[2])
            self.assertIn(ui.t("level.scale"), lines[2])
            self.assertIn("i7", lines[2])
            self.assertNotIn("i8", lines[2], "eight names, then how many more")
            self.assertIn("3", lines[2])
        en = wv.not_offered_lines(Ui(tk.palette("light", "blue"), "en"), left_out[:2], ())
        self.assertEqual(en, ["code — identifier", "UCLA_Level — already the grouping variable"])

    def test_every_new_text_has_three_languages(self):
        from workspace_text import T as TABLE

        keys = [k for k in TABLE if k.startswith(("vars.", "pick.score_items", "task.duplicate",
                                                  "task.copy_notice", "results.repeat",
                                                  "results.other", "catalog.recent",
                                                  "analyze.recent"))]
        self.assertEqual(len(keys), 51)
        for key in keys:
            self.assertEqual(len(TABLE[key]), 3, key)
            self.assertTrue(all(TABLE[key]), key)
            fields = [set(re.findall(r"\{(\w+)\}", text)) for text in TABLE[key]]
            self.assertEqual(fields[0], fields[1], key)
            self.assertEqual(fields[0], fields[2], key)


# ===================================================================== D7
class EligibleVariablesTests(unittest.TestCase):
    """Review D7: a role lists only the variables it can take, and says why
    not the others."""

    def test_covariates_offer_neither_the_group_nor_the_outcome(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")
        ws.check("role-outcome-UCLA")
        self.assertNotIn("UCLA_Level", boxes(ws, "role-outcome"), "the group is no outcome")
        covariates = boxes(ws, "role-covariates")
        self.assertEqual(covariates, ["Age", *[s for s in fx.SCALES]])
        reasons = text_of(ws, "role-covariates:not-offered")
        for line in ("Code — identifier", "Sex — Nominal (categories); this role takes "
                     "Quantitative", "UCLA — already an outcome",
                     "UCLA_Level — already the grouping variable"):
            self.assertIn(line, reasons)
        self.assertIn("UCLA_Level — already the grouping variable",
                      text_of(ws, "role-outcome:not-offered"))

    def test_the_ancova_form_offers_neither_its_outcome_nor_its_group(self):
        """The screenshot of review D7: ANCOVA among all methods."""
        ws = Workspace()
        self.addCleanup(ws.close)
        ws.run(ws.app.load_sample("sample_ancova.csv"))
        ws.check("data-accept-confirm")
        ws.click("data-accept")
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        ws.click("method-ancova")
        self.assertEqual(boxes(ws, "form-covariates"), ["age", "baseline_score", "wellbeing"])
        ws.choose("form-outcome", "wellbeing")
        ws.choose("form-group", "group")
        self.assertEqual(boxes(ws, "form-covariates"), ["age", "baseline_score"])
        reasons = text_of(ws, "form-covariates:not-offered")
        self.assertIn("wellbeing — already the outcome", reasons)
        self.assertIn("group — already the grouping variable", reasons)
        stack = ws.app._page_stack
        before = um.reconciliation_path(stack, ws.find("form-covariates-baseline_score"))
        self.assertFalse(ws.find_all("form-covariates-clear"))
        ws.check("form-covariates-baseline_score")       # Space on the box: Clear appears
        self.assertEqual(ws.app.pages["analyze"].form_roles["covariates"], ["baseline_score"])
        self.assertTrue(ws.find_all("form-covariates-clear"))
        self.assertEqual(um.reconciliation_path(stack, ws.find("form-covariates-baseline_score")),
                         before, "the ticked box keeps its place and its keyboard focus")

    def test_the_quick_selections_keep_their_names_keys_and_counts(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-relate")
        ws.choose("role-x", "UCLA")
        self.assertEqual(label(ws, "role-y-all-scale"), T("pick.all_scale", count=9))
        self.assertNotIn("UCLA", boxes(ws, "role-y"), "the first variable is not related to itself")
        self.assertEqual(ws.find("role-y-Age").label, e2e.option_label("Age", "scale"))
        ws.click("role-y-all-scale")
        self.assertEqual(label(ws, "role-y-clear"), T("pick.clear"))
        self.assertEqual(text_of(ws, "role-y:count"), T("vars.count", selected=9, total=11))

    def test_a_variable_chosen_before_stays_listed_until_it_is_unticked(self):
        """A task saved before this change may hold the group among its
        covariates: it is listed, ticked, so that it can be unticked."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-compare")
        page = ws.app.pages["analyze"]
        page.selection = {"group": "Sex", "outcome": ["UCLA"], "covariates": ["Sex", "Age"]}
        ws.app.render()
        self.assertIn("Sex", boxes(ws, "role-covariates"))
        self.assertTrue(ws.find("role-covariates-Sex").value)
        ws.check("role-covariates-Sex", False)
        self.assertEqual(page.selection["covariates"], ["Age"])
        self.assertNotIn("Sex", boxes(ws, "role-covariates"))


# ============================================================ the master fixture
class TwentyItemsTests(MasterFixture, unittest.TestCase):
    """U2: an item set chosen in one action, not 20 boxes."""

    def test_the_item_list_offers_ordered_variables_and_says_why_not_the_rest(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-scale")
        # More than 40: listed after a search, a name group or Show all
        # (about 100 boxes would be 100 Tab stops above the confirmations).
        self.assertEqual(boxes(ws, "role-items"), [])
        self.assertEqual(text_of(ws, "role-items:collapsed"), T("vars.collapsed", count=96))
        self.assertEqual(label(ws, "role-items:show-all"), T("vars.show_all", count=96))
        ws.click("role-items:show-all")
        offered = boxes(ws, "role-items")
        self.assertEqual(len(offered), 96)
        self.assertNotIn("participant_code", offered)
        self.assertNotIn("employed_code", offered)
        self.assertEqual(label(ws, "role-items:show-all"), T("vars.show_chosen"))
        self.assertEqual(text_of(ws, "role-items:count"), T("vars.count", selected=0, total=96))
        reasons = text_of(ws, "role-items:not-offered")
        self.assertIn("participant_code — identifier", reasons)
        self.assertIn("employed_code — Nominal (categories)", reasons)
        self.assertEqual([c.content for c in ws.find_all("role-items:group:")],
                         ["All SYN_LON_* (20)", "All SYN_SUP_* (12)", "All SYN_WELL_* (5)",
                          "All SYN_COPE_* (52)"])

    def test_a_twenty_item_set_by_its_name_group_in_one_action(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-scale")
        ws.counts.clear()
        ws.click("role-items:group:SYN_LON_")
        self.assertEqual(ws.total, 1)
        page = ws.app.pages["analyze"]
        self.assertEqual(page.selection["items"], list(LON))
        self.assertEqual(boxes(ws, "role-items"), list(LON), "the chosen ones are listed")
        self.assertEqual(text_of(ws, "role-items:collapsed"), T("vars.collapsed", count=76))
        self.assertEqual(text_of(ws, "role-items:count"), T("vars.count", selected=20, total=96))
        self.assertEqual(label(ws, "role-items:group:SYN_LON_"),
                         T("vars.ungroup", pattern="SYN_LON_*", count=20))
        ws.click("role-items:group:SYN_LON_")
        self.assertEqual(page.selection["items"], [])

    def test_search_a_pattern_or_a_range_then_select_or_unselect_what_is_shown(self):
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-scale")
        page = ws.app.pages["analyze"]
        ws.type("role-items:search", "SYN_COPE_0*")
        self.assertEqual(boxes(ws, "role-items"), list(COPE[:9]))
        self.assertEqual(text_of(ws, "role-items:count"),
                         T("vars.count_shown", selected=0, total=96, shown=9))
        self.assertEqual(label(ws, "role-items:select-shown"), T("vars.select_shown", count=9))
        ws.click("role-items:select-shown")
        self.assertEqual(page.selection["items"], list(COPE[:9]))
        ws.type("role-items:search", "SYN_COPE_01..SYN_COPE_07")
        self.assertEqual(label(ws, "role-items:unselect-shown"), T("vars.unselect_shown", count=7))
        ws.click("role-items:unselect-shown")
        self.assertEqual(page.selection["items"], ["SYN_COPE_08", "SYN_COPE_09"])
        submit(ws, "role-items:search", "SYN_LON_1*")      # Enter selects what is shown
        self.assertEqual(page.selection["items"],
                         ["SYN_COPE_08", "SYN_COPE_09", *LON[9:19]])
        ws.type("role-items:search", "nothing_like_this")
        self.assertEqual(boxes(ws, "role-items"), [])
        self.assertEqual(text_of(ws, "role-items:none"),
                         T("vars.none_match", query="nothing_like_this"))
        ws.type("role-items:search", "employed")
        self.assertIn("employed_code — Nominal (categories)",
                      text_of(ws, "role-items:not-offered"),
                      "a variable searched for and not offered says why")
        ws.click("goal-change")
        ws.click("goal-structure")
        self.assertEqual(ws.find("role-items:search").value, "", "another question: no search")

    def test_the_panel_confirms_nothing(self):
        """A selection by group or search never ticks a confirmation, and Run
        waits for it (K1)."""
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-scale")
        ws.click("role-items:group:SYN_LON_")
        self.assertFalse(ws.find("design-confirm-one_construct").value)
        self.assertTrue(ws.find("guided-run").disabled)
        ws.check("design-confirm-one_construct")
        self.assertFalse(ws.find("guided-run").disabled)
        ws.click("role-items:group:SYN_SUP_")              # other items: given again
        self.assertFalse(ws.find("design-confirm-one_construct").value)
        self.assertTrue(ws.find("guided-run").disabled)

    def test_keyboard_order_and_names_for_ui_automation(self):
        """Tab moves in reading order: the search field, the name groups, the
        actions, then the boxes; every control is named by its text; the
        search field and a box keep their place (and the keyboard focus)
        when the page is rebuilt while typing or ticking."""
        ws = self.workspace()
        ws.click("nav-analyze")
        ws.click("goal-scale")
        ws.click("role-items:group:SYN_LON_")
        panel = ws.find("role-items:panel")
        focusable = [c for c in ws.controls(panel)
                     if isinstance(c, (ft.TextField, ft.Button, ft.TextButton, ft.IconButton,
                                       ft.Checkbox))]
        kinds = [type(c).__name__ for c in focusable]
        self.assertEqual(kinds[0], "TextField")
        first_box = kinds.index("Checkbox")
        self.assertTrue(all(kind in ("TextButton", "Button") for kind in kinds[1:first_box]))
        self.assertTrue(all(kind == "Checkbox" for kind in kinds[first_box:]))
        for control in focusable:
            name = (control.label if isinstance(control, (ft.TextField, ft.Checkbox))
                    else control.content)
            self.assertTrue(isinstance(name, str) and name.strip(), control)
        field = ws.find("role-items:search")
        self.assertEqual(field.label, T("vars.search"))
        self.assertIsNotNone(field.on_submit, "Enter selects what is shown")
        stack = ws.app._page_stack
        before = um.reconciliation_path(stack, field)
        ws.type("role-items:search", "SYN_LON")
        self.assertEqual(um.reconciliation_path(stack, ws.find("role-items:search")), before)
        box = ws.find("role-items-SYN_LON_05")
        before = um.reconciliation_path(stack, box)
        ws.check("role-items-SYN_LON_05", False)
        self.assertEqual(um.reconciliation_path(stack, ws.find("role-items-SYN_LON_05")), before)


# ======================================================================= reuse
class ReuseTests(unittest.TestCase):
    def compare_batch(self, ws):
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "UCLA_Level")
        ws.click("role-outcome-all-scale")
        for name in ("Age", "UCLA"):
            ws.check(f"role-outcome-{name}", False)
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        run(ws, "guided-run")
        return ws.app.session.results[-1]

    def test_a_duplicated_task_has_the_variables_and_method_and_nothing_confirmed(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        entry = self.compare_batch(ws)
        session, page = ws.app.session, ws.app.pages["analyze"]
        original = session.task(entry.task_id)
        kept = (original.title, dict(original.selection), dict(original.confirms))
        self.assertEqual(set(original.confirms), {"independent", "assumptions"})
        ws.counts.clear()
        ws.click(f"task-duplicate-{original.id}")
        self.assertEqual(ws.total, 1)
        self.assertIsNone(page.task_id, "a new analysis, not the task")
        self.assertEqual(page.selection, original.selection)
        self.assertEqual(page.confirms, {})
        self.assertFalse(ws.find("design-confirm-independent").value)
        self.assertFalse(ws.find("design-confirm-assumptions").value)
        self.assertTrue(ws.find("guided-run").disabled, "Run waits for the confirmations")
        self.assertTrue(ws.find("task-copy-notice"))
        self.assertEqual(ws.app.section, "variables")
        ws.check("role-outcome-UCLA")                      # one variable changed
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        run(ws, "guided-run")
        copy = session.task(session.results[-1].task_id)
        self.assertNotEqual(copy.id, original.id)
        self.assertEqual(copy.state.get("copied_from"), original.id)
        self.assertEqual(copy.title, T("task.title_compare", group="UCLA_Level", count=9))
        self.assertEqual((original.title, original.selection, original.confirms), kept,
                         "the original task is unchanged")
        self.assertEqual([e.id for e in session.task_results(original.id)], [entry.id])
        stored = {t.id: t for t in ws.app.projects.project.tasks()}
        self.assertEqual(stored[copy.id].state.get("copied_from"), original.id)

    def test_repeat_with_changes_takes_the_variables_of_that_run(self):
        """Review D5: a task changed in place no longer shows the variables
        of its first result; repeating that result copies that run's."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-relate")
        ws.choose("role-x", "UCLA")
        ws.click("role-y-all-scale")
        ws.check("role-y-Age", False)
        ws.click("alt-batch_correlation-spearman")
        run(ws, "guided-run")
        first = ws.app.session.results[-1]
        ws.choose("role-x", "UCLA_Level")                  # in place, as before
        run(ws, "guided-run")
        task = ws.app.session.task(first.task_id)
        self.assertEqual(task.selection["x"], "UCLA_Level")
        ws.click("nav-results")
        self.assertEqual(ws.find(f"result-repeat-{first.id}").tooltip,
                         T("results.repeat_named", title=first.title))
        ws.counts.clear()
        ws.click(f"result-repeat-{first.id}")
        self.assertEqual(ws.total, 1)
        page = ws.app.pages["analyze"]
        self.assertEqual(ws.app.route, "analyze")
        self.assertEqual(page.selection, {"x": "UCLA", "y": list(fx.SCALES)})
        self.assertEqual(page.override[0], "batch_correlation")
        self.assertEqual(page.override[1]["method"], "spearman", "the method of that run")

    def test_other_results_at_the_end_of_a_result(self):
        """Where the reading of a long result ends, the other results can be
        opened (from their top) or repeated with changes, without scrolling
        back to the results list."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        first = self.compare_batch(ws)
        ws.click("nav-analyze")
        ws.click("task-new")
        ws.click("goal-describe")
        ws.choose("role-variable", "UCLA")
        run(ws, "guided-run")
        second = ws.app.session.results[-1]
        self.assertEqual(ws.app.route, "results")
        others = ws.controls(ws.find("result-others"))
        self.assertIn(T("results.others"), [c.value for c in others if isinstance(c, ft.Text)])
        self.assertTrue(label(ws, f"result-other-{first.id}").startswith(first.title))
        self.assertEqual(ws.find(f"result-other-repeat-{first.id}").tooltip,
                         T("results.repeat_named", title=first.title))
        self.assertFalse(ws.find_all(f"result-other-{second.id}"), "not the result on screen")
        ws.click(f"result-other-{first.id}")
        self.assertEqual(ws.app.session.selected_result, first.id)
        self.assertEqual((ws.app.route, ws.app.section), ("results", "detail"),
                         "shown from its top")
        ws.counts.clear()
        ws.click(f"result-other-repeat-{second.id}")
        self.assertEqual(ws.total, 1)
        page = ws.app.pages["analyze"]
        self.assertEqual((ws.app.route, page.goal, page.selection),
                         ("analyze", "describe", {"variable": "UCLA"}))
        self.assertIsNone(page.task_id)

    def test_the_guided_choices_of_a_run_for_every_question(self):
        from workspace_analyze import selection_from_run

        cases = [
            ("relate", "batch_correlation", {"x": "a", "ys": ["b", "c"]},
             {"x": "a", "y": ["b", "c"]}),
            ("relate", "correlation", {"x": "a", "y": "b"}, {"x": "a", "y": ["b"]}),
            ("relate", "chi", {"a": "a", "b": "b"}, {"x": "a", "y": ["b"]}),
            ("compare", "batch_groups", {"group": "g", "outcomes": ["o1", "o2"]},
             {"outcome": ["o1", "o2"], "group": "g"}),
            ("compare", "omnibus", {"outcome": "o", "group": "g"},
             {"outcome": ["o"], "group": "g"}),
            ("compare", "chi", {"a": "g", "b": "o"}, {"outcome": ["o"], "group": "g"}),
            ("compare", "ancova", {"outcome": "o", "group": "g", "covariates": ["c"]},
             {"outcome": ["o"], "group": "g", "covariates": ["c"]}),
            ("change", "paired", {"before": "t1", "after": "t2"}, {"measures": ["t1", "t2"]}),
            ("change", "repeated", {"measures": ["t1", "t2", "t3"]},
             {"measures": ["t1", "t2", "t3"]}),
            ("associate", "chi", {"a": "a", "b": "b"}, {"a": "a", "b": "b"}),
            ("predict", "regression", {"outcome": "y", "predictors": ["p"]},
             {"outcome": "y", "predictors": ["p"]}),
            ("predict", "ancova", {"outcome": "y", "group": "g", "covariates": ["c"]},
             {"outcome": "y", "predictors": ["g", "c"]}),
            ("scale", "item_diagnostics", {"items": ["i1", "i2", "i3"]},
             {"items": ["i1", "i2", "i3"]}),
            ("structure", "factor", {"items": ["i1", "i2", "i3"]}, {"items": ["i1", "i2", "i3"]}),
            ("describe", "explore", {"variable": "v", "group": "g"},
             {"variable": "v", "group": "g"}),
            ("describe", "descriptive", {"variable": "v"}, {"variable": "v"}),
        ]
        for goal, method, roles, expected in cases:
            self.assertEqual(selection_from_run(goal, method, roles), expected, (goal, method))
        self.assertIsNone(selection_from_run("relate", "regression", {"outcome": "y"}))

    def test_recent_methods_bring_variables_and_options_back_not_confirmations(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        entry = self.compare_batch(ws)
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        self.assertEqual([c.data for c in ws.find_all("recent-")], ["recent-batch_groups"])
        ws.click("recent-batch_groups")
        page = ws.app.pages["analyze"]
        self.assertEqual(page.method, "batch_groups")
        self.assertEqual(page.form_roles, entry.roles)
        self.assertEqual(page.form_options["adjust"], entry.options["adjust"])
        self.assertEqual(page.form_confirms, {})
        self.assertFalse(ws.find("form-confirm-independent").value)
        self.assertTrue(ws.find("form-run").disabled)
        self.assertTrue(page.message[0].startswith("Filled in from your last"))


class ScoreItemsTests(MasterFixture, unittest.TestCase):
    """The items of a scale score are chosen once: in Data → Prepare by
    their name group, and offered again for the score's reliability."""

    def prepare_score(self, ws):
        ws.click("nav-data")
        ws.click("data-prepare")
        panel = ws.app.pages["data"]._preparation[0]
        method = next(c for c in ws.controls(panel)
                      if isinstance(c, ft.Dropdown) and c.label == "Transformation")
        method.value = "scale"
        ws.dispatch(method.on_select, SimpleNamespace(control=method, data="scale"))
        picker = ws.app.pages["data"].items_picker
        self.assertEqual(text_of(ws, "prep-items:count"), T("vars.count", selected=0, total=96))
        reasons = text_of(ws, "prep-items:not-offered")
        self.assertIn("participant_code — not numeric", reasons)
        self.assertIn("employed_code — Nominal (categories)", reasons)
        ws.counts.clear()
        ws.click("prep-items:group:SYN_LON_")
        self.assertEqual(ws.total, 1)
        self.assertEqual(picker.selected(), list(LON))
        self.assertEqual(text_of(ws, "prep-items:count"), T("vars.count", selected=20, total=96))
        target = next(c for c in ws.controls(panel)
                      if isinstance(c, ft.TextField) and c.label == "New variable name")
        target.value = "SYN_LON_MEAN"
        for label_text in ("Apply transformation", "Use working copy in analysis"):
            button = next(c for c in ws.controls(panel)
                          if isinstance(c, ft.Button) and c.content == label_text)
            ws.dispatch(button.on_click, SimpleNamespace(control=button))
        session = ws.app.session
        self.assertIn("SYN_LON_MEAN", session.df.columns)
        expected = session.df[list(LON)].mean(axis=1)
        self.assertLess(float((session.df["SYN_LON_MEAN"] - expected).abs().max()), 1e-9)

    def test_the_prepare_items_search_and_unselect(self):
        ws = self.workspace()
        ws.click("nav-data")
        ws.click("data-prepare")
        panel = ws.app.pages["data"]._preparation[0]
        method = next(c for c in ws.controls(panel)
                      if isinstance(c, ft.Dropdown) and c.label == "Transformation")
        method.value = "scale"
        ws.dispatch(method.on_select, SimpleNamespace(control=method, data="scale"))
        picker = ws.app.pages["data"].items_picker
        field, listing = ws.find("prep-items:search"), ws.find("prep-items:list")
        ws.type("prep-items:search", "SYN_WELL_*")
        # The hosted panel is updated in place (page.update(), no keyed
        # re-render): a field made again would be a new widget and lose the
        # keyboard focus at each character, so the same objects are kept.
        self.assertIs(ws.find("prep-items:search"), field)
        self.assertIs(ws.find("prep-items:list"), listing)
        self.assertEqual([c.label for c in ws.controls(ws.find("prep-items:list"))
                          if isinstance(c, ft.Checkbox)],
                         [f"SYN_WELL_{n:02d}" for n in range(1, 6)]
                         + ["SYN_WELL_RAW", "SYN_WELL_0_100"])
        submit(ws, "prep-items:search", "SYN_WELL_0?")
        self.assertEqual(picker.selected(), [f"SYN_WELL_{n:02d}" for n in range(1, 6)])
        ws.click("prep-items:unselect-shown")
        self.assertEqual(picker.selected(), [])

    def test_the_items_of_a_score_are_offered_for_its_reliability(self):
        with tempfile.TemporaryDirectory() as folder:
            ws = self.workspace(Path(folder))
            self.prepare_score(ws)
            ws.app.session.confirm_level("SYN_LON_MEAN", "scale")
            ws.click("nav-analyze")
            ws.click("goal-scale")
            key = "role-items:score:SYN_LON_MEAN"
            self.assertEqual(label(ws, key), T("pick.score_items", score="SYN_LON_MEAN", count=20))
            ws.counts.clear()
            ws.click(key)
            self.assertEqual(ws.total, 1)
            self.assertEqual(ws.app.pages["analyze"].selection["items"], list(LON))
            self.assertFalse(ws.find_all(key), "offered while the items are other ones")
            project_id = ws.app.projects.info().id
            ws.close()
            again = CountingWorkspace(root=Path(folder))
            self.addCleanup(again.close)
            again.app.projects.open(project_id)
            again.click("nav-analyze")
            again.click("goal-scale")
            self.assertTrue(again.find_all(key), "kept with the project's history of the data")


# ================================================== the Windows journey, walked
class VariablePickerJourneyTests(MasterFixture, unittest.TestCase):
    """Journey ``variable-picker`` (tools/windows_gui_e2e.py) in the harness:
    every name the journey presses or waits for is there in that state, its
    numbers are the driver's own, and its counts are the harness's."""

    def test_the_journey_follows_the_eighteen_others(self):
        journeys = list(e2e.JOURNEYS)
        self.assertEqual(journeys[16:18], ["confirmations", "report-composition"])
        self.assertIn("variable-picker", journeys[18:])
        self.assertIs(e2e.JOURNEYS["variable-picker"], e2e.journey_variable_picker)

    def test_names_with_a_tooltip_still_match(self):
        texts = e2e.panel_texts(96)
        for name in (texts["group"], texts["group"] + "\nSelect the 20 variables …"):
            self.assertRegex(name, "^" + re.escape(texts["group"]) + e2e.CHIP_END)
        self.assertNotRegex(T("results.repeat_named", title="Scale quality"),
                            "^" + re.escape(texts["repeat"]) + e2e.CHIP_END,
                            "the list's icon is not the detail's button")

    def test_the_walk(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ws = CountingWorkspace(root=root)
            self.addCleanup(ws.close)
            csv_path = self.csv
            offered = e2e.panel_offered(csv_path)
            self.assertEqual(offered, 96)
            texts = e2e.panel_texts(offered)
            alpha, n = e2e.independent_alpha(csv_path, e2e.PANEL_ITEMS)
            fewer, same_n = e2e.independent_alpha(csv_path, e2e.PANEL_ITEMS[:-1])
            self.assertEqual((n, same_n), (180, 180))
            create_project_in_ui(ws, e2e.VARIABLE_PANEL_PROJECT)
            open_csv(ws, csv_path)
            accept_levels_in_ui(ws)
            self.assertEqual(ws.find("data-accept-confirm").label, T("data.accept_confirm"))

            # The item list: what it does not offer, and why.
            guided(ws)
            ws.click("goal-scale")
            reasons = text_of(ws, "role-items:not-offered")
            self.assertIn(texts["identifier"], reasons)
            self.assertIn("employed_code", reasons)
            self.assertFalse([c for c in ws.find_all("role-items-participant_code")])

            # The 20 items in one action: their name group.
            key = f"role-items:group:{e2e.PANEL_STEM}"
            self.assertEqual(label(ws, key), texts["group"])
            ws.counts.clear()
            ws.click(key)
            actions = {"items_by_name_group": {"clicks": ws.counts["click"],
                                               "boxes": ws.counts["check"], "typed": 0}}
            self.assertEqual(text_of(ws, "role-items:count"), texts["selected"])

            # One construct confirmed, Run: α as the driver computes it.
            self.assertEqual([ws.find("design-confirm-one_construct").label],
                             e2e.scale_check_confirmations())
            ws.check("design-confirm-one_construct")
            self.assertRegex(label(ws, "guided-run"), e2e.run_button())
            run(ws, "guided-run")
            summary = ws.find("result-answer").value
            shown = e2e.ALPHA_SUMMARY.search(summary).groupdict()
            self.assertEqual((int(shown["k"]), int(shown["n"])), (20, n))
            self.assertTrue(e2e.same_as_shown(alpha, shown["alpha"]), summary)

            # Repeat with changes: a new task, the same 20 items, nothing confirmed.
            self.assertEqual(label(ws, "result-repeat"), texts["repeat"])
            ws.counts.clear()
            typed = 0
            ws.click("result-repeat")
            notice = [c.value for c in ws.controls(ws.find("task-copy-notice"))
                      if isinstance(c, ft.Text)]
            self.assertTrue(any(e2e.template_pattern("task.copy_notice").search(t)
                                for t in notice), notice)
            self.assertEqual(text_of(ws, "role-items:count"), texts["selected"])
            self.assertEqual(e2e.scale_check_confirmations(),
                             [ws.find("design-confirm-one_construct").label])
            self.assertFalse(ws.find("design-confirm-one_construct").value)

            # The keyboard: the item found by typing, left out with Tab and Space.
            self.assertEqual(ws.find("role-items:search").label, texts["search"])
            ws.type("role-items:search", e2e.PANEL_DROPPED)
            typed += 1
            self.assertEqual(text_of(ws, "role-items:count"), texts["found"])
            panel = [c for c in ws.controls(ws.find("role-items:panel"))
                     if isinstance(c, (ft.TextField, ft.Button, ft.TextButton, ft.Checkbox))]
            names = [c.label if isinstance(c, (ft.TextField, ft.Checkbox)) else c.content
                     for c in panel]
            self.assertEqual(names[0], texts["search"])
            self.assertEqual(names[-1], texts["dropped"], "Tab reaches the box after the field")
            self.assertLessEqual(len(names) - 1, 25, "within focus_on's Tab presses")
            ws.check(f"role-items-{e2e.PANEL_DROPPED}", False)           # Space on the box
            self.assertEqual(text_of(ws, "role-items:count"), texts["left_out"])

            # Confirmed again, Run: α of 19 items as numpy computes it.
            ws.check("design-confirm-one_construct")
            run(ws, "guided-run")
            actions["repeat_with_one_item_fewer"] = {
                "clicks": ws.counts["click"], "boxes": ws.counts["check"], "typed": typed}
            self.assertEqual(actions, e2e.PANEL_ACTIONS)
            summary = ws.find("result-answer").value
            self.assertTrue(re.search(r"k = 19, n = \d+", summary), summary)
            shown = e2e.ALPHA_SUMMARY.search(summary).groupdict()
            self.assertEqual(int(shown["n"]), same_n)
            self.assertTrue(e2e.same_as_shown(fewer, shown["alpha"]), summary)
            deleted = ws.app.session.results[0].run.evidence()
            row = next(r for r in deleted.rows
                       if r.parameter == f"{e2e.ALPHA_IF_DELETED}: {e2e.PANEL_DROPPED}")
            self.assertTrue(e2e.same_as_shown(fewer, row.estimate),
                            "the first result's α if deleted")

            # Two tasks in the project: the first unchanged, the copy re-confirmed.
            rows = e2e.project_query(folder_of(root), e2e.VARIABLE_PANEL_PROJECT,
                                     "SELECT id, selection, confirms, state FROM research_tasks "
                                     "ORDER BY position")
            tasks = [(task_id, json.loads(selection).get("items"), json.loads(confirms),
                      json.loads(state)) for task_id, selection, confirms, state in rows]
            self.assertEqual(len(tasks), 2)
            self.assertEqual(tasks[0][1], list(e2e.PANEL_ITEMS))
            self.assertEqual(tasks[1][1], list(e2e.PANEL_ITEMS[:-1]))
            self.assertEqual(tasks[1][3].get("copied_from"), tasks[0][0])
            self.assertEqual(tasks[1][2], {"one_construct": True})
            self.assertEqual(tasks[0][2], {"one_construct": True})


if __name__ == "__main__":
    unittest.main()
