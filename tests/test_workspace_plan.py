"""Stage 35 (#40): the research plan card of the project page."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from workspace_harness import Workspace  # noqa: E402


def texts(ws, data: str) -> str:
    return " ".join(c.value for c in ws.controls(ws.find(data))
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


class ResearchPlanCardTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)
        self.ws.app.projects.create("Fictional planned study")
        self.ws.app.navigate("project")

    def test_a_plan_is_written_and_saved_as_versions(self):
        ws = self.ws
        ws.type("plan-objectives", "Fictional aims")
        ws.click("plan-add")
        ws.type("plan-h0-text", "Group B reports more stress")
        ws.choose("plan-h0-direction", "greater")
        ws.click("plan-save")
        project = ws.app.projects.project
        self.assertEqual(project.plan()["plan"]["objectives"], "Fictional aims")
        self.assertEqual(project.plan()["plan"]["hypotheses"][0]["direction"], "greater")
        self.assertIn("Saved as version 1", texts(ws, "plan-feedback"))
        self.assertIn("Planned before any result", texts(ws, "plan-standing-0"))
        ws.click("plan-save")
        self.assertIn("No changes since the last version", texts(ws, "plan-feedback"))
        ws.type("plan-design", "Two independent groups")
        ws.click("plan-save")
        self.assertEqual([v["version"] for v in project.plan_history()], [2, 1])
        self.assertIsNotNone(ws.find("plan-version-1"), "the history lists earlier versions")

    def test_an_invalid_value_is_explained_and_nothing_is_saved(self):
        ws = self.ws
        ws.click("plan-add")
        ws.type("plan-h0-text", "Some hypothesis")
        ws.type("plan-h0-alpha", "0.9")
        ws.click("plan-save")
        self.assertIn("The plan was not saved", texts(ws, "plan-feedback"))
        self.assertEqual(ws.app.projects.project.plan_history(), [])


if __name__ == "__main__":
    unittest.main()
