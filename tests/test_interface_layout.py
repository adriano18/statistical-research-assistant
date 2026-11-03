"""Small smoke tests for the new Flet navigation layout."""

import unittest
import flet as ft

from interface_layout import build_interface


CONTROL_NAMES = [
    "status", "overview_area", "variable", "scale", "results", "guidance",
    "preparation_panel", "survey_panel",
    "chart_area", "output_toolbar",
    "explore_variable", "explore_group", "explore_output", "explore_chart",
    "reg_outcome", "reg_predictors", "reg_hc3", "reg_confirm",
    "reg_main", "reg_brief", "reg_report", "reg_warnings", "reg_chart",
    "log_outcome", "log_predictors", "log_confirm", "log_main",
    "log_brief", "log_odds_table", "log_report", "log_warnings", "log_chart",
    "ac_outcome", "ac_group", "ac_covariates", "ac_mode", "ac_confirm",
    "ac_main", "ac_brief", "ac_means_table", "ac_pairs_table",
    "ac_chart", "ac_report", "ac_warnings",
    "rep_items", "rep_scale", "rep_method", "rep_same_people",
    "rep_assumptions", "rep_main", "rep_brief", "rep_report",
    "rep_warnings", "rep_chart", "rep_pair_table",
    "reliability_items", "reliability_confirm",
    "reliability_output", "reliability_guide", "reliability_warnings",
    "reliability_chart_area", "omega_summary_text", "omega_item_table",
    "omega_report", "omega_warnings", "omega_chart_area", "omega_ci_reps",
    "factor_items", "factor_method", "factor_count", "factor_rotation",
    "factor_confirm", "factor_main_text", "factor_report",
    "factor_warnings", "factor_loading_table", "factor_correlation_text",
    "factor_chart_area",
    "corr_x", "corr_y", "corr_scale_x",
    "corr_scale_y", "corr_advice", "corr_method", "corr_confirm",
    "corr_output", "corr_warnings", "corr_chart", "matrix_items",
    "matrix_method", "matrix_confirm", "matrix_output", "matrix_warnings",
    "matrix_chart",
    "group_variable", "group_outcome", "group_outcome_scale", "group_method",
    "group_independent", "group_assumptions", "group_advice", "group_output",
    "group_warnings", "group_chart",
    "paired_before", "paired_after", "paired_scale", "paired_method",
    "paired_confirm", "paired_assumptions", "paired_advice",
    "paired_output", "paired_warnings", "paired_chart",
    "paired_main", "paired_descriptive", "paired_brief",
    "paired_export_png_button", "paired_export_txt_button",
    "paired_export_status",
    "chi_a", "chi_b", "chi_confirm", "chi_main", "chi_brief",
    "chi_output", "chi_warnings", "chi_chart",
    "chi_export_png_button", "chi_export_txt_button", "chi_export_status",
    "omnibus_group", "omnibus_outcome", "omnibus_scale", "omnibus_method",
    "omnibus_independent", "omnibus_assumptions", "omnibus_advice",
    "omnibus_main", "omnibus_brief", "omnibus_output", "omnibus_warnings",
    "omnibus_chart", "omnibus_export_png_button",
    "omnibus_export_txt_button", "omnibus_export_status",
    "posthoc_button", "posthoc_output", "posthoc_table", "posthoc_warnings",
]

ACTION_NAMES = [
    "choose_file", "load_sample", "load_scale_example", "load_factor_example", "analyze_variable",
    "calculate_alpha", "calculate_omega", "calculate_factor_exploration", "calculate_correlation", "calculate_matrix",
    "calculate_groups", "calculate_paired", "load_paired_example",
    "calculate_chi_square", "load_categorical_example",
    "calculate_omnibus", "load_three_groups_example",
    "run_explore", "set_active_screen", "run_regression", "load_regression_example",
    "run_logistic", "load_logistic_example",
    "run_ancova", "load_ancova_example", "load_ancova_interaction_example",
    "run_repeated", "load_repeated_example",
]


class DummyPage:
    def __init__(self, width=1280):
        self.width = width
        self.on_resize = None

    def update(self):
        pass


class LayoutTests(unittest.TestCase):
    def make_screen(self, width=1280):
        controls = {name: ft.Text(name) for name in CONTROL_NAMES}
        actions = {name: (lambda e: None) for name in ACTION_NAMES}
        return build_interface(DummyPage(width), controls, actions)

    def test_home_is_initial_screen_and_methods_are_grouped(self):
        root = self.make_screen()
        self.assertIsInstance(root, ft.Row)
        self.assertEqual(len(root.controls), 2)
        sidebar = root.controls[0]
        groups = [
            item for item in sidebar.content.controls
            if isinstance(item, ft.ExpansionTile)
        ]
        self.assertEqual(len(groups), 4)
        buttons = [
            item for item in sidebar.content.controls
            if isinstance(item, ft.Button)
        ]
        for group in groups:
            buttons.extend(item for item in group.controls
                           if isinstance(item, ft.Button))
        self.assertEqual(len(buttons), 17)

        workspace = root.controls[1].content
        self.assertFalse(workspace.controls[0].visible)
        self.assertFalse(workspace.controls[1].visible)  # No dataset banner on Home
        self.assertFalse(workspace.controls[2].visible)  # No export on Home
        screens = workspace.controls[3].controls
        self.assertEqual(len(screens), 17)
        self.assertTrue(screens[0].visible)
        self.assertTrue(all(not screen.visible for screen in screens[1:]))

    def test_compact_windows_show_dropdown_navigation(self):
        root = self.make_screen(width=800)
        self.assertFalse(root.controls[0].visible)
        compact = root.controls[1].content.controls[0]
        self.assertIsInstance(compact, ft.Dropdown)
        self.assertTrue(compact.visible)
        self.assertEqual(compact.value, "home")
        self.assertEqual(len(compact.options), 17)


if __name__ == "__main__":
    unittest.main()
