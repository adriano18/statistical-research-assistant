"""Layout regression for the huge gray import fallback input field."""

import unittest

import flet as ft

from import_layout import manual_file_path_field, manual_file_path_row


class ImportFallbackLayoutTests(unittest.TestCase):
    def test_fallback_path_input_never_expands_without_bounds(self):
        field = manual_file_path_field()
        self.assertIsInstance(field, ft.TextField)
        self.assertEqual(field.width, 510)
        self.assertEqual(field.height, 52)
        self.assertFalse(bool(getattr(field, "expand", False)))
        self.assertFalse(field.multiline)
        self.assertIn("local file path", field.label.lower())

    def test_wrapping_row_does_not_use_expand_or_fixed_viewport_height(self):
        field = manual_file_path_field()
        button = ft.Button("Open file by full path")
        row = manual_file_path_row(field, button)
        self.assertIsInstance(row, ft.Row)
        self.assertEqual(row.controls, [field, button])
        self.assertTrue(row.wrap)
        self.assertIsNone(row.height)
        self.assertFalse(bool(getattr(row, "expand", False)))


if __name__ == "__main__":
    unittest.main()
