"""Consistent square Windows / soft macOS-style buttons across Flet screens.

Apply only to control geometry, keeping a button's existing colors, state,
actions and keyboard interaction intact. No research values are modified.
"""

import flet as ft


def style_buttons(root, appearance: str) -> int:
    radius = 10 if appearance == "macos" else 0
    visited = set()
    changed = 0

    def visit(node):
        nonlocal changed
        if node is None or isinstance(node, (str, bytes, int, float, bool)):
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                visit(child)
            return
        if id(node) in visited:
            return
        visited.add(id(node))
        if isinstance(node, ft.Button):
            previous = node.style or ft.ButtonStyle()
            node.style = previous.copy(
                shape=ft.RoundedRectangleBorder(radius=radius),
            )
            changed += 1
        for name in ("controls", "content", "title", "leading", "trailing"):
            try:
                visit(getattr(node, name, None))
            except (AttributeError, TypeError):
                pass

    visit(root)
    return changed
