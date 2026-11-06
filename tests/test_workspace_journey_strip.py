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
        self.assertEqual(tone_of(ws, "method"), "success")
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
