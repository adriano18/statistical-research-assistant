"""Stage 37.0b: the plan card's Q1 row and its editor of planned variables.

* A plan without typed questions (Stage 36, or none yet) shows the project's
  research question as Q1 by itself, kind not chosen; it does not start the
  plan until the researcher uses it, and it is saved with the next version
  (design §7.2, §8.4).
* Each hypothesis of a typed question names its planned variables by role,
  chosen from the data (typed before the data is open). The check
  H-VARIABLES-DIFFER is then reachable from the interface.

Synthetic data only; the handlers a click calls.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from test_stage36_ux_baseline import CountingWorkspace  # noqa: E402
from test_stage37_ui import (  # noqa: E402
    H1, QUESTION, Case, check_index, check_state, title,
)
from workspace_text import T  # noqa: E402


class QuestionRowTests(Case):
    def test_a_stage_36_plan_shows_the_projects_question_as_q1(self):
        ws = self.workspace()
        project = ws.app.projects.project
        ws.app.projects.set_research_question(QUESTION)
        project.save_plan({"objectives": "Fictional", "hypotheses": [
            {"text": "Loneliness relates to coping", "priority": "primary"}]})
        ws.app.pages["project"].plan.draft = None         # the page opens the project anew
        ws.app.navigate("project")
        self.assertEqual(ws.find("plan-q0-text").value, QUESTION)
        self.assertIsNone(ws.find("plan-q0-type").value, "kind not chosen")
        self.assertEqual(ws.find("plan-q0-auto").value, T["plan.q.from_project"][0])
        self.assertEqual(ws.find("plan-h0-question").value, "", "not linked to a question")
        self.assertEqual(title(ws), ws.app.t("next.create_analysis", h=1),
                         "Q1 shown by itself asks for nothing (not N1: its kind)")
        self.assertEqual(project.plan()["version"], 1, "nothing converted on screen")
        ws.click("plan-save")                              # the first save writes it as Q1
        saved = project.plan()["plan"]
        self.assertEqual([(q["type"], q["text"]) for q in saved["questions"]], [("", QUESTION)])
        self.assertEqual(saved["plan_format"], 2)

    def test_a_new_project_shows_an_empty_q1_that_counts_once_used(self):
        ws = self.workspace()
        ws.app.navigate("project")
        self.assertEqual([c.data for c in ws.find_all("plan-q") if c.data.endswith("-text")],
                         ["plan-q0-text"])
        self.assertEqual(ws.find("plan-q0-text").value, "")
        self.assertEqual(title(ws), ws.app.t("next.analyze"))
        ws.type("plan-q0-text", QUESTION)
        ws.app.navigate("project")
        self.assertEqual(title(ws), ws.app.t("next.question", q=1), "now Q1 needs its kind")
        ws.click("plan-add-question")                      # a second question this time
        self.assertEqual(len(ws.app.pages["project"].plan.draft["questions"]), 2)

    def test_q1_is_written_through_to_the_projects_question(self):
        ws = self.workspace()
        ws.app.navigate("project")
        ws.type("plan-q0-text", QUESTION)
        ws.choose("plan-q0-type", "relate")
        ws.click("plan-q0-add-hypothesis")
        ws.type("plan-h0-text", H1)
        ws.click("plan-save")
        self.assertEqual(ws.app.projects.research_question(), QUESTION,
                         "the AI overview and the report read the project's question")
        self.assertEqual(ws.find("project-question").value, QUESTION)


class PlannedVariablesTests(Case):
    def planned_roles(self):
        ws = self.workspace()
        ws.app.navigate("project")
        ws.type("plan-q0-text", QUESTION)
        ws.choose("plan-q0-type", "relate")
        ws.click("plan-q0-add-hypothesis")
        ws.type("plan-h0-text", H1)
        return ws

    def test_the_roles_of_the_question_are_chosen_from_the_data(self):
        ws = self.planned_roles()
        x = ws.find("plan-h0-role-x", ft.Dropdown)
        self.assertEqual(x.label, T["role.x"][0])
        self.assertEqual(x.options[0].text, T["plan.h.role_none"][0])
        self.assertIn("UCLA · " + T["level.scale"][0], [o.text for o in x.options])
        self.assertNotIn("Code", [o.key for o in x.options], "no identifier")
        ws.choose("plan-h0-role-x", "UCLA")
        for name in ("AssertiveAction", "SocialJoining", "CautiousAction"):
            ws.check(f"plan-h0-role-y-{name}")
        ws.check("plan-h0-role-y-SocialJoining", False)
        ws.click("plan-save")
        hypothesis = ws.app.projects.project.plan()["plan"]["hypotheses"][0]
        self.assertEqual(hypothesis["roles"], {"x": "UCLA",
                                               "y": ["AssertiveAction", "CautiousAction"]})

    def test_the_planned_variables_reach_the_analysis_and_the_check(self):
        ws = self.planned_roles()
        ws.choose("plan-h0-role-x", "UCLA")
        for name in ("AssertiveAction", "CautiousAction"):
            ws.check(f"plan-h0-role-y-{name}")
        ws.click("plan-save")
        hid = ws.app.projects.project.plan()["plan"]["hypotheses"][0]["id"]
        ws.click("next-create-analysis")
        page = ws.app.pages["analyze"]
        self.assertEqual(page.selection, {"x": "UCLA", "y": ["AssertiveAction", "CautiousAction"]},
                         "the planned variables are chosen")
        ws.check("role-y-SocialJoining")                   # one more than planned
        ws.click("alt-batch_correlation-spearman")
        ws.click("guided-run")
        self.assertEqual(check_state(ws, "H-VARIABLES-DIFFER"), "open")
        ws.click("hyp-1-toggle")
        index = check_index(ws, "H-VARIABLES-DIFFER")
        self.assertIn("SocialJoining", " ".join(
            c.value for c in ws.controls(ws.find(f"hyp-1-check-{index}"))
            if isinstance(c, ft.Text) and isinstance(c.value, str)))
        ws.click(f"hyp-1-check-{index}-deviation")
        ws.type("hyp-1-reason", "Fictional: SocialJoining was added on the supervisor's advice.")
        ws.click("hyp-1-save")
        self.assertEqual(check_state(ws, "H-VARIABLES-DIFFER"), "recorded")
        record = ws.app.projects.project.protocol_records(hypothesis_id=hid)[-1]
        self.assertEqual(record["detail"]["what"], "variables")
        self.assertEqual(record["detail"]["planned"],
                         {"x": ["UCLA"], "y": ["AssertiveAction", "CautiousAction"]})

    def test_before_the_data_names_are_typed_and_typing_never_rebuilds_the_page(self):
        ws = CountingWorkspace()
        self.addCleanup(ws.close)
        ws.app.projects.create("Fictional study without data")
        ws.app.navigate("project")
        ws.type("plan-q0-text", QUESTION)
        ws.choose("plan-q0-type", "relate")
        ws.click("plan-q0-add-hypothesis")
        x, y = ws.find("plan-h0-role-x", ft.TextField), ws.find("plan-h0-role-y", ft.TextField)
        self.assertEqual(x.hint_text, T["plan.h.roles_hint"][0])
        with mock.patch.object(ws.app, "render", wraps=ws.app.render) as render:
            ws.type("plan-h0-role-x", "UCLA")
            ws.type("plan-h0-role-y", "AssertiveAction, CautiousAction ,")
        self.assertEqual(render.call_count, 0)
        draft = ws.app.pages["project"].plan.draft["hypotheses"][0]
        self.assertEqual(draft["roles"], {"x": "UCLA", "y": ["AssertiveAction", "CautiousAction"]})
        self.assertTrue(y)

    def test_a_planned_name_missing_from_the_data_is_shown_as_such(self):
        ws = self.planned_roles()
        draft = ws.app.pages["project"].plan.draft["hypotheses"][0]
        draft["roles"] = {"x": "Loneliness_total", "y": ["AssertiveAction"]}
        ws.app.navigate("project")
        options = {o.key: o.text for o in ws.find("plan-h0-role-x", ft.Dropdown).options}
        self.assertEqual(options["Loneliness_total"],
                         ws.app.t("plan.h.role_missing", name="Loneliness_total"))
        notice = " ".join(c.value for c in ws.controls(ws.find("plan-h0-roles-missing"))
                          if isinstance(c, ft.Text) and isinstance(c.value, str))
        self.assertIn(ws.app.t("plan.h.roles_missing", names="Loneliness_total"), notice)

    def test_another_kind_of_question_leaves_out_roles_it_does_not_have(self):
        ws = self.planned_roles()
        ws.choose("plan-h0-role-x", "UCLA")
        ws.check("plan-h0-role-y-AssertiveAction")
        ws.choose("plan-q0-type", "compare")
        draft = ws.app.pages["project"].plan.draft["hypotheses"][0]
        self.assertNotIn("roles", draft, "x and y are not roles of a group comparison")
        self.assertTrue(ws.find_all("plan-h0-role-group"))
        ws.click("plan-save")
        self.assertNotIn("roles", ws.app.projects.project.plan()["plan"]["hypotheses"][0])


if __name__ == "__main__":
    unittest.main()
