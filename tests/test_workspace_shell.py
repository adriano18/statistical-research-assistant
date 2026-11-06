"""Stage 33 workspace shell: navigation, keyboard, themes, languages, a11y."""

from __future__ import annotations

import asyncio
import os
import unittest

os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402

from workspace_harness import Workspace  # noqa: E402

ROUTES = ("home", "data", "questionnaires", "import", "analyze", "results", "reports",
          "settings", "help")


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)

    def assert_page_ok(self, route):
        self.assertFalse(self.ws.has_text("This page could not be shown"), route)
        body = self.ws.app.page_control
        self.assertEqual(body.data, f"workspace-page-{route}")
        self.assertEqual(body.key, f"workspace-page-{route}")

    def test_every_route_renders_empty_and_with_data(self):
        for route in ROUTES:
            self.ws.app.navigate(route)
            self.assert_page_ok(route)
        self.ws.run(self.ws.app.load_sample("sample_scale.csv"))
        for route in ROUTES:
            self.ws.app.navigate(route)
            self.assert_page_ok(route)

    def test_sidebar_has_six_areas_and_no_duplicate_top_menu(self):
        nav = [c.data for c in self.ws.find_all("nav-")]
        for area in ("home", "data", "questionnaires", "analyze", "results", "reports"):
            self.assertIn(f"nav-{area}", nav)
        self.assertFalse([c for c in self.ws.controls() if isinstance(c, ft.MenuBar)])
        self.ws.click("nav-analyze")
        self.assertEqual(self.ws.app.route, "analyze")
        self.ws.click("nav-toggle")
        self.assertFalse(self.ws.app.sidebar_expanded)
        sidebar = self.ws.find("workspace-sidebar")
        self.assertEqual(sidebar.width, 64)
        # Collapsed items keep an accessible name through their tooltip.
        for item in self.ws.find_all("nav-"):
            if isinstance(item, ft.TextButton):
                self.assertTrue(item.tooltip, item.data)

    def test_keyboard_shortcuts(self):
        self.ws.key("2", ctrl=True)
        self.assertEqual(self.ws.app.route, "data")
        self.ws.key("6", ctrl=True)
        self.assertEqual(self.ws.app.route, "reports")
        self.ws.key("B", ctrl=True)
        self.assertFalse(self.ws.app.sidebar_expanded)
        self.ws.key("L", ctrl=True, shift=True)
        self.assertEqual(self.ws.app.session.theme, "dark")
        self.assertEqual(self.ws.page.theme_mode, ft.ThemeMode.DARK)
        self.ws.key("F1")
        self.assertEqual(self.ws.app.route, "help")

    def test_language_switch_translates_navigation_and_keeps_data(self):
        self.ws.run(self.ws.app.load_sample("sample_scale.csv"))
        self.ws.segment("context-language", "ru")
        self.assertTrue(self.ws.has_text("Анализ"))
        self.assertTrue(self.ws.has_text("Данные"))
        self.ws.segment("context-language", "lv")
        self.assertTrue(self.ws.has_text("Analīze"))
        self.assertTrue(self.ws.app.session.has_data)
        self.assertTrue(any("32 rindas" in t for t in self.ws.texts()))

    def test_dark_theme_uses_dark_tokens_everywhere(self):
        import workspace_tokens as tk

        self.ws.click("context-theme")
        self.assertEqual(self.ws.find("workspace-sidebar").bgcolor, tk.DARK.surface_alt)
        self.assertEqual(self.ws.find("workspace-context").bgcolor, tk.DARK.surface)

    def test_accessibility_rules_on_every_page(self):
        self.ws.run(self.ws.app.load_sample("sample_scale.csv"))
        for route in ROUTES:
            self.ws.app.navigate(route)
            for control in self.ws.controls():
                if isinstance(control, ft.IconButton):
                    self.assertTrue(control.tooltip, f"{route}: icon button without name")
                if isinstance(control, ft.Text) and control.size is not None:
                    self.assertGreaterEqual(control.size, 12, f"{route}: {control.value!r}")
                if isinstance(control, ft.Container) and control.on_click is not None:
                    self.assertTrue(control.ink, f"{route}: clickable container {control.data}")
                if isinstance(control, (ft.Dropdown, ft.TextField)):
                    self.assertTrue(control.label or control.tooltip or control.hint_text,
                                    f"{route}: unlabeled input {control.data}")
                if isinstance(control, (ft.Button, ft.TextButton)) and control.height:
                    self.assertGreaterEqual(control.height, 32, f"{route}: {control.data}")

    def test_compact_and_narrow_widths_render_all_pages(self):
        for width in (1100, 900):
            ws = Workspace(width)
            self.addCleanup(ws.close)
            ws.run(ws.app.load_sample("sample_scale.csv"))
            for route in ROUTES:
                ws.app.navigate(route)
                self.assertFalse(ws.has_text("This page could not be shown"), (width, route))
            ws.app.navigate("questionnaires")
            self.assertTrue(ws.find_all("q-pane"))  # compact layouts switch panes

    def test_no_expanding_child_in_a_wrapping_row(self):
        """Flutter cannot lay out an expanding child inside a wrapping row and
        shows a grey error box instead (found by the dark 1100 px screenshot
        of the project page). Every scenario, at a compact and a wide width."""
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        from workspace_scenarios import SCENARIOS, apply

        found = []
        for width in (1100, 1440):
            for name in [s for s in SCENARIOS if not s.startswith("classic")]:
                ws = Workspace(width)
                try:
                    ws.run(apply(ws.app, name))
                    for control in ws.controls():
                        if isinstance(control, ft.Row) and control.wrap:
                            for child in control.controls:
                                if getattr(child, "expand", None):
                                    found.append((width, name, getattr(child, "data", None)
                                                  or type(child).__name__))
                finally:
                    ws.close()
        self.assertEqual(found, [])

    def test_status_line_is_a_live_region(self):
        live = [c for c in self.ws.controls() if isinstance(c, ft.Semantics) and c.live_region]
        self.assertTrue(live)
        self.ws.run(self.ws.app.load_sample("sample_scale.csv"))
        self.assertIn("sample_scale.csv", self.ws.find("workspace-status").value)

    def test_preview_is_marked_as_prototype(self):
        self.assertTrue(self.ws.has_text("Preview"))
        self.assertTrue(self.ws.has_text("Prototype"))


class ClassicIntegrationTests(unittest.TestCase):
    def test_classic_home_opens_the_workspace_and_returns_with_the_dataset(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        import ux_inventory
        from flet.controls.context import _context_page
        from types import SimpleNamespace

        captured = {}
        page, classic = ux_inventory.build_classic(captured=captured)
        actions = captured["actions"]
        token = _context_page.set(page)
        try:
            asyncio.run(actions["load_scale_example"](None))
            entry = []
            ux_inventory.walk(classic, lambda c, d: entry.append(c)
                              if getattr(c, "data", None) == "open-workspace-preview" else None)
            self.assertEqual(len(entry), 1)
            page.show_dialog = lambda d: None
            entry[0].on_click(SimpleNamespace(control=entry[0]))
            self.assertEqual(page.controls[0].data, "workspace-root")
            # The workspace adopted the classic dataset.
            texts = []
            ux_inventory.walk(page.controls[0], lambda c, d: texts.append(c.value)
                              if isinstance(c, ft.Text) and isinstance(c.value, str) else None)
            self.assertTrue(any("sample_scale.csv" in t for t in texts))
            # A dataset opened in the workspace goes back to the classic screens.
            from workspace_shell import EXAMPLES, active_app

            workspace = active_app()
            self.assertIs(workspace.root, page.controls[0])
            asyncio.run(workspace.load_path(str(EXAMPLES / "sample_paired.csv")))
            back = []
            ux_inventory.walk(page.controls[0], lambda c, d: back.append(c)
                              if getattr(c, "data", None) == "nav-classic" else None)
            asyncio.run(back[0].on_click(SimpleNamespace(control=back[0])))
            # Return to classic: the very same classic root is shown again.
            self.assertIs(page.controls[0], classic)
            self.assertIn("sample_paired.csv", captured["controls"]["status"].value)
            # Re-entering after a classic import adopts the classic dataset again.
            asyncio.run(actions["load_three_groups_example"](None))
            entry[0].on_click(SimpleNamespace(control=entry[0]))
            self.assertEqual(workspace.session.source_name, "sample_three_groups.csv")
        finally:
            _context_page.reset(token)


if __name__ == "__main__":
    unittest.main()
