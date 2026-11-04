"""Regression tests for marketing questionnaire preview and Flet layout.

Flet 1.x can raise "Frozen controls cannot be updated" when a respondent form
is repainted before it is attached, or when already-mounted controls are
retranslated during each survey tab switch. Tests exercise the actual builder
buttons, not a mocked validation-only preview.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import flet as ft

from survey_ui import build_survey_workspace
from ui_i18n import UITranslator


class DummyPage:
    def __init__(self):
        self.services = []
        self.updates = 0

    def update(self):
        self.updates += 1


def walk(item, visited=None):
    if visited is None:
        visited = set()
    if item is None or isinstance(item, (str, bytes, int, float, bool)):
        return
    if isinstance(item, (tuple, list)):
        for child in item:
            yield from walk(child, visited)
        return
    if id(item) in visited:
        return
    visited.add(id(item))
    yield item
    for field in ("controls", "content", "title", "options"):
        try:
            value = getattr(item, field, None)
        except (TypeError, AttributeError):
            continue
        yield from walk(value, visited)


def buttons_named(tree, label):
    return [
        element for element in walk(tree)
        if isinstance(element, ft.Button)
        and (
            getattr(element, "content", None) == label
            or getattr(getattr(element, "content", None), "value", None) == label
        )
    ]


class PreviewCrashRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.page = DummyPage()
        self.translator = UITranslator()
        self.translation_roots = []

        def translate_new(root):
            self.translation_roots.append(root)
            self.translator.apply(root, "ru")

        async def load_data(_):
            return True

        self.view = build_survey_workspace(
            self.page, load_dataframe=load_data,
            root=Path(self.temporary.name),
            language_getter=lambda: "ru",
            translate_view=translate_new,
        )

    def _choose_marketing(self):
        selectors = [
            item for item in walk(self.view)
            if isinstance(item, ft.Dropdown)
            and getattr(item, "label", None) in (
                "Starting template", "Начальный шаблон", "Шаблон анкеты",
            )
        ]
        self.assertEqual(len(selectors), 1)
        selectors[0].value = "marketing"
        choices = buttons_named(self.view, "Load template") + buttons_named(
            self.view, "Загрузить шаблон",
        )
        self.assertEqual(len(choices), 1)
        choices[0].on_click(None)

    def test_marketing_template_preview_is_single_atomic_page_update(self):
        self._choose_marketing()
        self.assertEqual(len(buttons_named(self.view, "2. Preview")), 0)
        preview_buttons = buttons_named(self.view, "2. Предпросмотр")
        self.assertEqual(len(preview_buttons), 1)

        before = self.page.updates
        translations_before = len(self.translation_roots)
        preview_buttons[0].on_click(None)

        # There is exactly one repaint after the entire form is built,
        # rather than repeated page.update() on unmounted child controls.
        self.assertEqual(self.page.updates - before, 1)
        self.assertEqual(len(self.translation_roots), translations_before + 1)
        self.assertIsNot(self.translation_roots[-1], self.view)

        preview_pane = self.view.controls[2]
        self.assertTrue(preview_pane.visible)
        panel = preview_pane.controls[0]
        form = panel.content.controls[4].controls[0]
        self.assertIs(self.translation_roots[-1], form)
        all_text = [
            item.value for item in walk(form)
            if isinstance(item, ft.Text) and isinstance(item.value, str)
        ]
        self.assertTrue(
            any("продукт" in entry.lower() or "опыт" in entry.lower()
                for entry in all_text),
            "Marketing respondent form should render real translated questions.",
        )

    def test_repeated_switches_do_not_retranslate_mounted_survey_shell(self):
        self._choose_marketing()
        preview = buttons_named(self.view, "2. Предпросмотр")[0]
        builder = buttons_named(self.view, "1. Создать")[0]

        for _ in range(3):
            preview.on_click(None)
            builder.on_click(None)
        self.assertEqual(
            sum(root is self.view for root in self.translation_roots), 1,
            "Only initial setup may translate the full survey tree.",
        )
        self.assertEqual(
            len(self.translation_roots), 1 + 3,
            "Each newly constructed preview is translated before mounting.",
        )
        self.assertTrue(self.view.controls[1].visible)
        self.assertFalse(self.view.controls[2].visible)


if __name__ == "__main__":
    unittest.main()
