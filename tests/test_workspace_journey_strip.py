"""Stage 34.5 (issue #32): the research journey shown on the work pages —
question, data, variables, design, method, result, report — with what is
done and where the researcher is. Fictional data only."""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from workspace_harness import Workspace  # noqa: E402

STAGES = ("question", "data", "variables", "design", "method", "result", "report")


def tone_of(ws, key: str) -> str:
    """success (done), info (here) or neutral, read from the chip colour."""
    import workspace_tokens as tk

    chip = ws.find(f"journey-{key}")
    palette = tk.palette(ws.app.session.theme)
    for tone, (bg, _fg, _icon) in __import__("workspace_components").TONES.items():
        if chip.bgcolor == getattr(palette, bg):
            return tone
    return "?"


class JourneyTests(unittest.TestCase):
    def test_the_strip_follows_the_research(self):
        ws = Workspace()
        self.addCleanup(ws.close)
        ws.app.navigate("data")
        self.assertEqual([c.data for c in ws.find_all("journey-")],
                         [f"journey-{key}" for key in STAGES])
        self.assertEqual(tone_of(ws, "data"), "info", "you are here")
        ws.run(ws.app.load_sample("sample_scale.csv"))
        self.assertEqual(tone_of(ws, "variables"), "info", "levels still to confirm")
        ws.check("data-accept-confirm", True)
        ws.click("data-accept")
        self.assertEqual(tone_of(ws, "variables"), "success")
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        ws.run(ws.app.pages["analyze"]._execute(
            "groups", {"outcome": "stress_q1", "group": "group"}, {}, {"independent": True}))
        self.assertEqual(tone_of(ws, "result"), "info")
        # Changed deliberately in Stage 37.0b (design §7.6, AC-5, review U10):
        # a result no longer ticks Design and Method by itself. They come
        # from the steps of a research task, and this result has none.
        self.assertEqual(tone_of(ws, "method"), "neutral")
        self.assertEqual(tone_of(ws, "design"), "neutral")
        self.assertEqual(tone_of(ws, "report"), "neutral")
        ws.click("journey-report")
        self.assertEqual(ws.app.route, "reports")
        ws.click("journey-question")
        self.assertEqual(ws.app.route, "home", "without a project the question starts on Home")

    def test_home_and_settings_have_no_strip(self):
        ws = Workspace()
        self.addCleanup(ws.close)
        for route in ("home", "settings", "help"):
            ws.app.navigate(route)
            self.assertFalse(ws.find_all("journey-"), route)


class TaskStatusTests(unittest.TestCase):
    """Stage 37.0b (AC-5): the strip shows the steps of the open task, or of
    the task of the first hypothesis; another task's result ticks nothing."""

    def test_the_strip_follows_the_open_task(self):
        from test_stage36_ux_baseline import prepared_workspace

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-relate")
        self.assertEqual([tone_of(ws, k) for k in ("design", "method", "result")],
                         ["info", "neutral", "neutral"], "nothing chosen yet")
        ws.choose("role-x", "UCLA")
        ws.click("role-y-all-scale")
        ws.click("alt-batch_correlation-spearman")
        self.assertEqual(tone_of(ws, "method"), "success", "a method is chosen")
        self.assertEqual(tone_of(ws, "result"), "neutral", "not run yet")
        ws.click("guided-run")
        self.assertEqual(tone_of(ws, "result"), "success")
        self.assertEqual(tone_of(ws, "report"), "neutral")
        ws.click("task-add-report")
        self.assertEqual(tone_of(ws, "report"), "success")
        # A new analysis on screen: its own steps, not the first task's result.
        ws.click("task-new")
        ws.click("goal-compare")
        self.assertEqual([tone_of(ws, k) for k in ("method", "result", "report")],
                         ["neutral", "neutral", "neutral"])

    def test_without_an_open_task_the_first_hypothesis_task_counts(self):
        from test_stage37_ui import run_correlations, write_plan
        from test_stage36_ux_baseline import prepared_workspace

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        write_plan(ws, direction="two-sided")
        ws.app.navigate("project")
        ws.click("next-create-analysis")             # H1's task, not run
        h1_task = ws.app.session.tasks[-1]
        ws.click("task-new")
        ws.click("goal-relate")
        run_correlations(ws)                         # another task, with a result
        ws.app.pages["analyze"].reset()              # no task on screen now
        ws.app.navigate("data")
        self.assertEqual(ws.app.focus_steps()[0].key, "hypothesis")
        self.assertEqual(tone_of(ws, "result"), "neutral",
                         "the other task's result does not tick H1's analysis")
        ws.click("nav-analyze")
        ws.click(f"task-{h1_task.id}")
        self.assertEqual(tone_of(ws, "result"), "neutral")


class ValueSummaryTests(unittest.TestCase):
    def test_the_dictionary_shows_what_each_column_holds(self):
        ws = Workspace()
        self.addCleanup(ws.close)
        ws.run(ws.app.load_sample("sample_scale.csv"))
        values = {name: ws.find(f"values-{name}").value for name in ws.app.session.variables}
        self.assertEqual(values["participant_id"], "32 unique")
        self.assertEqual(values["group"], "A (16), B (16)")
        self.assertEqual(values["stress_q1"], "1 (2), 2 (8), 3 (6), 4 (11), 5 (5)",
                         "the codes of a response scale, not a range")
        ws.run(ws.app.load_sample("sample_ancova.csv"))
        self.assertEqual(ws.find("values-wellbeing").value, "34.24 – 66.13")


class ResearchQuestionTests(unittest.TestCase):
    def test_the_question_is_kept_in_the_project(self):
        with TemporaryDirectory() as folder:
            ws = Workspace(root=Path(folder))
            try:
                info = ws.app.projects.create("Fictional question study")
                ws.app.navigate("project")
                self.assertEqual(tone_of(ws, "question"), "info")
                ws.type("project-question", "Does fictional training raise wellbeing?")
                field = ws.find("project-question")
                ws.run(field.on_blur(SimpleNamespace(control=field)))
                self.assertEqual(ws.app.projects.research_question(),
                                 "Does fictional training raise wellbeing?")
                self.assertTrue(ws.app.journey_status()["question"])
                ws.app.navigate("data")
                self.assertEqual(tone_of(ws, "question"), "success", "done, seen from Data")
            finally:
                ws.close()
            again = Workspace(root=Path(folder))
            try:
                again.app.projects.open(info.id)
                again.app.navigate("project")
                self.assertEqual(again.find("project-question").value,
                                 "Does fictional training raise wellbeing?")
            finally:
                again.close()


if __name__ == "__main__":
    unittest.main()
