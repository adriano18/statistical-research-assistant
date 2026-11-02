"""Small smoke tests for the new Flet navigation layout."""

import unittest
import flet as ft

from interface_layout import build_interface


CONTROL_NAMES = [
    "status", "overview_area", "variable", "scale", "results", "guidance",
    "chart_area", "reliability_items", "reliability_confirm",
    "reliability_output", "reliability_guide", "reliability_warnings",
    "reliability_chart_area", "corr_x", "corr_y", "corr_scale_x",
    "corr_scale_y", "corr_advice", "corr_method", "corr_confirm",
    "corr_output", "corr_warnings", "corr_chart", "matrix_items",
    "matrix_method", "matrix_confirm", "matrix_output", "matrix_warnings",
    "matrix_chart",
]

ACTION_NAMES = [
    "choose_file", "load_sample", "load_scale_example", "analyze_variable",
    "calculate_alpha", "calculate_correlation", "calculate_matrix",
]


class DummyPage:
    def update(self):
        pass


class LayoutTests(unittest.TestCase):
    def test_all_five_screens_exist_and_only_dataset_is_visible(self):
        controls = {name: ft.Text(name) for name in CONTROL_NAMES}
        actions = {name: (lambda e: None) for name in ACTION_NAMES}

        root = build_interface(DummyPage(), controls, actions)

        self.assertIsInstance(root, ft.Row)
        self.assertEqual(len(root.controls), 2)

        sidebar = root.controls[0]
        nav_buttons = [
            item for item in sidebar.content.controls
            if isinstance(item, ft.Button)
        ]
        self.assertEqual(len(nav_buttons), 5)

        workspace = root.controls[1].content
        screens = workspace.controls[1:]
        self.assertEqual(len(screens), 5)
        self.assertTrue(screens[0].visible)
        self.assertTrue(all(not screen.visible for screen in screens[1:]))


if __name__ == "__main__":
    unittest.main()
