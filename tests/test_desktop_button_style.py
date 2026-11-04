"""Ensure desktop shapes update while preserving actions and selected colors."""

import unittest
import flet as ft

from desktop_button_style import style_buttons


class ButtonGeometryTests(unittest.TestCase):
    def test_square_windows_buttons_preserve_callbacks_colors_and_text(self):
        pressed = []
        btn = ft.Button(
            "Run analysis",
            on_click=lambda e: pressed.append("yes"),
            style=ft.ButtonStyle(
                bgcolor="#E5EFFC", color="#164C96",
            ),
        )
        root = ft.Column(controls=[
            ft.Container(content=ft.Row(controls=[btn]))
        ])
        self.assertEqual(style_buttons(root, "windows"), 1)
        self.assertEqual(btn.style.shape.radius, 0)
        self.assertEqual(btn.style.bgcolor, "#E5EFFC")
        self.assertEqual(btn.style.color, "#164C96")
        btn.on_click(None)
        self.assertEqual(pressed, ["yes"])
        self.assertEqual(style_buttons(root, "macos"), 1)
        self.assertEqual(btn.style.shape.radius, 10)
        btn.on_click(None)
        self.assertEqual(pressed, ["yes", "yes"])

    def test_two_identical_buttons_both_styled_once(self):
        a, b = ft.Button("A"), ft.Button("B")
        root = ft.Column(controls=[a, ft.Row(controls=[b, a])])
        self.assertEqual(style_buttons(root, "windows"), 2)
        self.assertEqual(a.style.shape.radius, 0)
        self.assertEqual(b.style.shape.radius, 0)


if __name__ == "__main__":
    unittest.main()
