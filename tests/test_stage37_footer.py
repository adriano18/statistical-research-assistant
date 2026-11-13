"""Stage 37.0b: the next-action bar in the footer of Data, Analyze, Results
and Reports, and the plan link offered after results without a plan
(design §7.9). Through the real handlers, synthetic data only.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from test_stage36_ux_baseline import CountingWorkspace, eight_correlations  # noqa: E402
from test_stage37_ui import Case, title, write_plan  # noqa: E402
from workspace_text import T  # noqa: E402


def footer(ws):
    found = ws.find_all("footer-next-action")
    return found[0] if found else None


def footer_text(ws) -> str:
    return " ".join(c.value for c in ws.controls(footer(ws))
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


def footer_buttons(ws) -> list:
    return [c for c in ws.controls(footer(ws)) if isinstance(c, (ft.Button, ft.TextButton))]


class FooterTests(Case):
    def test_the_bar_is_below_the_four_pages_of_a_project(self):
        ws = self.workspace()
        for route in ("data", "analyze", "results", "reports"):
            with self.subTest(route=route):
                ws.app.navigate(route)
                self.assertIsNotNone(footer(ws))
                self.assertEqual(ws.find("footer-next-label").value, T["footer.next_step"][0])
                self.assertEqual([b.data for b in footer_buttons(ws) if b.disabled], [],
                                 "never a disabled button")
        for route in ("project", "home", "settings"):
            ws.app.navigate(route)
            self.assertIsNone(footer(ws), route)

    def test_no_bar_without_a_project(self):
        ws = CountingWorkspace()
        self.addCleanup(ws.close)
        ws.app.navigate("data")
        self.assertIsNone(footer(ws))

    def test_its_button_does_what_it_names_on_another_page(self):
        ws, hid = self.planned()
        ws.app.navigate("data")
        self.assertEqual(ws.find("footer-next-title").value,
                         ws.app.t("next.create_analysis", h=1))
        ws.click("next-create-analysis")
        self.assertEqual((ws.app.route, ws.app.section), ("analyze", "variables"))
        self.assertEqual(ws.app.session.tasks[-1].hypothesis_id, hid)

    def test_on_the_page_it_leads_to_the_bar_says_the_step_is_here(self):
        ws = CountingWorkspace()
        self.addCleanup(ws.close)
        ws.app.projects.create("Fictional footer study")
        import stage36_fixtures as fx

        self.assertTrue(ws.run(ws.app.load_path(str(fx.fixture(fx.CSV)))))
        ws.app.navigate("data")
        self.assertEqual(ws.find("footer-next-title").value, T["next.levels"][0])
        self.assertEqual(footer_buttons(ws)[:-1], [], "no button to the page already open")
        self.assertEqual(ws.find("footer-next-here").value, T["next.here"][0])
        ws.app.navigate("results")
        self.assertEqual([b.data for b in footer_buttons(ws)][:1], ["next-levels"])

    def test_why_this_step_opens_in_the_footer(self):
        ws, hid = self.planned()
        ws.app.navigate("analyze")
        self.assertEqual(ws.find("footer-next-why").content, T["next.why.title"][0])
        ws.click("footer-next-why")
        lines = [c.value for c in ws.find_all("footer-next-why-")]
        self.assertTrue(lines and lines[0].startswith("✓ "), lines)
        self.assertFalse(ws.app.pages["project"].hypotheses.show_why,
                         "the Project page keeps its own choice")

    def test_after_results_without_a_plan_the_plan_link_is_offered(self):
        ws = self.workspace()
        eight_correlations(ws)
        ws.app.navigate("results")
        self.assertIn("next-plan-link", [b.data for b in footer_buttons(ws)])
        self.assertEqual(ws.find("next-plan-link").content, T["next.plan_link"][0])
        ws.click("next-plan-link")
        self.assertEqual(ws.app.route, "project")
        self.assertEqual(ws.find("plan-q0-text").value, "", "Q1, to be written")
        self.assertIn("next-plan-link", [c.data for c in ws.find_all("next-")],
                      "the Project page bar offers it too")
        ws.type("plan-q0-text", "Is loneliness related to coping?")
        ws.app.navigate("project")
        self.assertEqual(title(ws), ws.app.t("next.question", q=1),
                         "once written, Q1 starts the plan: its kind is next")

    def test_the_bar_reads_in_every_language(self):
        ws, hid = self.planned()
        bare = re.compile(r"\b(next|footer|plan|hyp)\.[a-z_]+")
        for language in ("en", "lv", "ru"):
            with self.subTest(language=language):
                ws.app.session.language = language
                for route in ("data", "analyze", "results", "reports"):
                    ws.app.navigate(route)
                    self.assertNotRegex(footer_text(ws), bare)

    def test_the_stage_36_flow_counts_no_footer_click(self):
        ws = self.workspace()
        write_plan(ws)
        ws.counts.clear()
        eight_correlations(ws)
        self.assertEqual(ws.total, 8, "the bar adds no step to the Stage 36 flow")


if __name__ == "__main__":
    unittest.main()
