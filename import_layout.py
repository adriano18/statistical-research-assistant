"""Bounded, responsive desktop file-path fallback.

Avoid flex expansion on a TextField inside a wrapping Row. In the Flet
desktop renderer, an unbounded flex child can monopolize the remaining
vertical viewport as a large gray input surface.
"""

import flet as ft


def manual_file_path_field() -> ft.TextField:
    return ft.TextField(
        label="Full local file path (fallback if dialog does not open)",
        hint_text=r"C:\Users\you\Documents\research.xlsx",
        width=510,
        height=52,
    )


def manual_file_path_row(field: ft.TextField, button: ft.Button) -> ft.Row:
    return ft.Row(
        controls=[field, button],
        wrap=True,
        spacing=10,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
