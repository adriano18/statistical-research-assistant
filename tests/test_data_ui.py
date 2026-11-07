"""Stage 35 (#44): the dialogs that show where research data is kept and
copy an earlier version's data. Synthetic data only."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import data_ui  # noqa: E402
import legacy_data as ld  # noqa: E402
from test_legacy_data import LegacyCase  # noqa: E402


class FakePage:
    def __init__(self):
        self.dialogs, self.services, self.updates = [], [], 0

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def update(self, *controls):
        self.updates += 1


def texts(control) -> list[str]:
    found = []

    def walk(node):
        if isinstance(node, ft.Text) and isinstance(node.value, str):
            found.append(node.value)
        for name in ("content", "controls", "title", "actions"):
            child = getattr(node, name, None)
            for item in child if isinstance(child, list) else [child]:
                if isinstance(item, ft.Control):
                    walk(item)
    walk(control)
    return found


def button(dialog, data):
    return next(b for b in dialog.actions if b.data == data)


class TextTests(unittest.TestCase):
    def test_every_language_has_every_text(self):
        for language in ("lv", "ru"):
            with self.subTest(language=language):
                self.assertEqual(set(data_ui.TEXT[language]), set(data_ui.TEXT["en"]))


class MigrationDialogTests(LegacyCase):
    def test_the_dialog_lists_what_it_would_copy(self):
        source = ld.inspect(self.old, self.new, "preview")
        shown = " ".join(texts(data_ui.migration_dialog(FakePage(), source, self.new, "en")))
        self.assertIn(str(self.old), shown)
        self.assertIn(str(self.new), shown)
        self.assertIn("Projects (2): Second fictional study, Sleep and stress (fictional)", shown,
                      "listed in alphabetical order")
        self.assertIn("Questionnaires with their responses (1): Synthetic pilot", shown)
        self.assertIn("nothing in the earlier folder is changed or deleted", shown)
        russian = " ".join(texts(data_ui.migration_dialog(FakePage(), source, self.new, "ru")))
        self.assertIn("Проекты (2)", russian)

    def test_copy_reports_what_was_copied_and_checked(self):
        page = FakePage()
        source = ld.inspect(self.old, self.new, "preview")
        dialog = data_ui.migration_dialog(page, source, self.new, "en")
        page.show_dialog(dialog)
        asyncio.run(button(dialog, "migration-copy").on_click(None))
        shown = " ".join(texts(dialog))
        self.assertIn("Copied: 2 project(s), 1 questionnaire(s), the researcher profile. "
                      "Each copy was checked against its original.", shown)
        self.assertIn(f"The originals are unchanged in {self.old}.", shown)
        self.assertEqual([b.data for b in dialog.actions], ["migration-close"])
        import project_store as ps

        self.assertEqual(len(ps.ProjectStore(self.new / "projects").list()), 2)

    def test_not_now_is_remembered(self):
        page = FakePage()
        source = ld.inspect(self.old, self.new, "preview")
        dialog = data_ui.migration_dialog(page, source, self.new, "en")
        page.show_dialog(dialog)
        button(dialog, "migration-later").on_click(None)
        self.assertTrue(ld.is_dismissed(self.old, self.new))
        self.assertEqual(page.dialogs, [])
        self.assertFalse((self.new / "projects").exists(), "nothing copied")

    def test_offered_once_at_startup_in_a_known_place(self):
        page = FakePage()
        environment = {"APPDATA": str(self.base / "AppData" / "Roaming"),
                       "SRA_DATA_DIR": str(self.new), "SRA_OFFER_MIGRATION": "1"}
        with mock.patch.dict(os.environ, environment), \
                mock.patch("startup_diagnostics.is_packaged", return_value=False):
            offered = asyncio.run(data_ui.offer_at_startup(page, ROOT, "en"))
            self.assertEqual(offered.folder, self.old)
            self.assertEqual(page.dialogs[0].data, "migration-dialog")
            button(page.dialogs[0], "migration-later").on_click(None)
            self.assertIsNone(asyncio.run(data_ui.offer_at_startup(page, ROOT, "en")))

    def test_not_offered_automatically_when_tests_choose_the_data_folder(self):
        page = FakePage()
        environment = {"APPDATA": str(self.base / "AppData" / "Roaming"),
                       "SRA_DATA_DIR": str(self.new), "SRA_OFFER_MIGRATION": ""}
        with mock.patch.dict(os.environ, environment):
            self.assertIsNone(asyncio.run(data_ui.offer_at_startup(page, ROOT, "en")))
        self.assertEqual(page.dialogs, [])

    def test_a_chosen_folder_without_new_data_says_so(self):
        page = FakePage()
        note = asyncio.run(data_ui.find_in_chosen_folder(page, str(self.base / "empty"),
                                                         self.new, "en"))
        self.assertIn("No data of an earlier version was found", note)
        asyncio.run(data_ui.find_in_chosen_folder(page, str(self.old.parent), self.new, "en"))
        self.assertEqual(page.dialogs[0].data, "migration-dialog")


class WorkspaceSettingsTests(unittest.TestCase):
    def test_settings_show_the_data_folder(self):
        from workspace_harness import Workspace

        ws = Workspace()
        self.addCleanup(ws.close)
        ws.app.navigate("settings")
        card = ws.find("settings-data")
        shown = " ".join(c.value for c in ws.controls(card)
                         if isinstance(c, ft.Text) and isinstance(c.value, str))
        self.assertIn(str(ws.app.project_root.parent), shown)
        self.assertIn("never changes this folder", shown)
        self.assertIsNotNone(ws.find("settings-data-find"))


if __name__ == "__main__":
    unittest.main()
