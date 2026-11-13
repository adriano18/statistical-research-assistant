"""Stage 37 (issue #68): the flows of the packaged-program journeys
`startup-workspace` and `settings-language`, through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. These tests start the program the way the launcher does
(``research_app.main``: no ``SRA_UI``, a data folder of its own, the
preferences file of earlier versions patched into it) and walk the same
flows, checking at each point that every text, button name, dropdown entry
and settings-file value the journey waits for is there, with the journey's
own texts and helpers. UI Automation reports every button as enabled, so
nothing here relies on a disabled state. Synthetic data only.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests", ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
os.environ.setdefault("MPLBACKEND", "Agg")

import flet as ft  # noqa: E402

import app_preferences  # noqa: E402
from test_stage368_acceptance import T, folder_of  # noqa: E402
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import FakePage, Workspace  # noqa: E402


class Program(Workspace):
    """The program as the launcher starts it, on a fake page: the classic
    interface built and the start interface shown (the harness otherwise
    builds the workspace alone). ``restart()`` is a new start on the same
    data folder."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.temp = None
        self._closed = False
        self.saved = []
        self._patches = [
            mock.patch.dict(os.environ, {"SRA_DATA_DIR": str(self.root), "SRA_UI": ""}),
            mock.patch.object(app_preferences, "preferences_path",
                              lambda: self.root / "home" / "preferences.json"),
        ]
        for patch in self._patches:
            patch.start()
        self._start()

    def _start(self):
        import research_app
        from flet.controls.context import _context_page

        self.page = FakePage(1440)
        self._token = _context_page.set(self.page)
        asyncio.run(research_app.main(self.page))
        self._token_page = self.page

    @property
    def app(self):
        from workspace_shell import active_app

        return active_app()

    @property
    def in_workspace(self) -> bool:
        return getattr(self.page.controls[0], "data", None) == "workspace-root"

    def restart(self):
        self.stop()
        self._start()

    def stop(self):
        from flet.controls.context import _context_page

        app = self.app
        if app is not None:
            app.projects.close(clear=False)
        _context_page.reset(self._token)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop()
        import workspace_tokens

        workspace_tokens.apply_density(workspace_tokens.DEFAULT_DENSITY)
        for patch in reversed(self._patches):
            patch.stop()

    def names(self) -> list[str]:
        """Texts, button names and checkbox labels (what UI Automation lists)."""
        found = list(self.texts())
        for control in self.controls():
            content = getattr(control, "content", None)
            if isinstance(control, (ft.Button, ft.TextButton)):
                if isinstance(content, str):
                    found.append(content)
                elif isinstance(content, ft.Text) and isinstance(content.value, str):
                    found.append(content.value)
        return found

    def button(self, name: str):
        """The button UI Automation names ``name`` (its label)."""
        for control in self.controls():
            if isinstance(control, (ft.Button, ft.TextButton)):
                content = control.content
                label = content if isinstance(content, str) else getattr(content, "value", None)
                if label == name:
                    return control
        raise AssertionError(f"no button named {name!r}")

    def press(self, name: str):
        control = self.button(name)
        return self.dispatch(control.on_click, SimpleNamespace(control=control, data=None))

    def dropdown(self, label: str) -> ft.Dropdown:
        found = [c for c in self.controls() if isinstance(c, ft.Dropdown) and c.label == label]
        assert len(found) == 1, (label, found)
        return found[0]

    def pick(self, label: str, entry: str):
        """``gui.choose(label, entry)``: the entry named ``entry``."""
        field = self.dropdown(label)
        key = next(o.key for o in field.options if o.text == entry)
        field.value = key
        return self.dispatch(field.on_select, SimpleNamespace(control=field, data=key))


class StartupWorkspaceJourneyTests(unittest.TestCase):
    """Journey `startup-workspace`."""

    def test_the_normal_start_the_classic_interface_and_the_start_choice(self):
        with tempfile.TemporaryDirectory() as folder:
            program = Program(Path(folder))
            self.addCleanup(program.close)
            disk = folder_of(Path(folder))

            # A normal start opens the research workspace (no SRA_UI).
            self.assertTrue(program.in_workspace)
            self.assertIn(T("project.create"), program.names(), "the journey's ready text")
            self.assertNotIn(e2e.CLASSIC_BANNER, program.names())
            self.assertIn(e2e.stored_settings(disk).get("start_interface"), (None, "workspace"))
            self.assertEqual(e2e.settings_file(disk), Path(folder) / "settings.json")
            classic_item = program.find("nav-classic")
            self.assertEqual(classic_item.content.controls[-1].value, T("nav.classic"))

            # The classic interface is one click away, and its Home leads back.
            program.click("nav-classic")
            self.assertFalse(program.in_workspace)
            self.assertIn(e2e.CLASSIC_BANNER, program.names())
            program.press(e2e.CLASSIC_OPEN_WORKSPACE)
            self.assertTrue(program.in_workspace)
            self.assertIn(T("project.create"), program.names())

            # Settings: the classic interface as the start interface (the index
            # chip "Start" leads to it).
            program.app.navigate("settings")
            self.assertIn(T("settings.section.start"), [
                c.content.controls[-1].value for c in program.find_all("settings-jump-")])
            field = program.dropdown(T("settings.start_interface"))
            self.assertEqual([o.text for o in field.options], e2e.START_OPTIONS)
            program.pick(T("settings.start_interface"), T("settings.start.classic"))
            self.assertEqual(e2e.stored_settings(disk)["start_interface"], "classic")

            # The next start opens the classic interface.
            program.restart()
            self.assertFalse(program.in_workspace)
            self.assertIn(e2e.CLASSIC_OPEN_WORKSPACE, program.names(), "the journey's ready text")
            self.assertIn(e2e.CLASSIC_BANNER, program.names())

            # The research workspace as the start interface again.
            program.press(e2e.CLASSIC_OPEN_WORKSPACE)
            program.app.navigate("settings")
            program.pick(T("settings.start_interface"), T("settings.start.workspace"))
            self.assertEqual(e2e.stored_settings(disk)["start_interface"], "workspace")
            program.restart()
            self.assertTrue(program.in_workspace)
            self.assertNotIn(e2e.CLASSIC_BANNER, program.names())


class SettingsLanguageJourneyTests(unittest.TestCase):
    """Journey `settings-language`."""

    def test_an_earlier_russian_preference_lv_after_a_restart_and_text_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disk = folder_of(root)
            legacy = root / "home" / "preferences.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps(e2e.UPGRADE_PREFERENCES), encoding="utf-8")
            before = legacy.read_bytes()
            self.assertFalse(e2e.settings_file(disk).exists(), "this version never ran")

            program = Program(root)
            self.addCleanup(program.close)
            with mock.patch.object(app_preferences, "preferences_path", lambda: legacy):
                self.assertEqual(e2e.legacy_preferences(), legacy)

            # The program starts in Russian; the old file is unchanged.
            self.assertTrue(program.in_workspace)
            names = program.names()
            self.assertIn(e2e.text_in("ru", "project.create"), names, "the journey's ready text")
            self.assertIn(e2e.text_in("ru", "nav.analyze"), names)
            self.assertEqual(e2e.stored_settings(disk)["language"], "ru")
            self.assertEqual(legacy.read_bytes(), before)

            # The top bar offers EN and LV only (buttons named by their code).
            quick = {code: code.upper() in names for code in ("en", "lv", "ru")}
            self.assertEqual(quick, {"en": True, "lv": True, "ru": False})

            # Settings show Russian.
            program.click("nav-settings")
            self.assertIn(e2e.text_in("ru", "settings.section.language"), [
                c.content.controls[-1].value for c in program.find_all("settings-jump-")])
            self.assertIn(e2e.text_in("ru", "settings.language_note"), program.names())
            field = program.dropdown(e2e.text_in("ru", "settings.language"))
            shown = next(o.text for o in field.options if o.key == field.value)
            self.assertEqual(shown, "Русский")
            self.assertEqual([o.text for o in field.options], e2e.LANGUAGE_OPTIONS)

            # LV in the top bar: still on Settings, now in Latvian, saved.
            program.press("LV")
            self.assertEqual(program.app.route, "settings")
            self.assertIn(e2e.text_in("lv", "settings.language_note"), program.names())
            self.assertEqual(e2e.stored_settings(disk)["language"], "lv")

            # After a restart: Latvian.
            program.restart()
            names = program.names()
            self.assertIn(e2e.text_in("lv", "project.create"), names)
            self.assertIn(e2e.text_in("lv", "nav.analyze"), names)

            # Text size 125 %: the label above the sizes is larger (the index
            # chip the journey clicks first leads to it).
            program.click("nav-settings")
            chip = program.find("settings-jump-typography")
            self.assertEqual(chip.content.controls[-1].value,
                             e2e.text_in("lv", "settings.section.typography"))
            program.click("settings-jump-typography")
            label = e2e.text_in("lv", "settings.text_size")

            def label_size():
                sizes = [c.size for c in program.controls()
                         if isinstance(c, ft.Text) and c.value == label and c.size]
                self.assertEqual(len(sizes), 1, "one text of that name")
                return sizes[0]

            normal = label_size()
            program.press("125 %")
            self.assertEqual(e2e.stored_settings(disk)["text_scale"], 125)
            self.assertGreaterEqual(label_size() / normal, 1.15)
            self.assertEqual(program.app.route, "settings", "the page stays open")

            # Back to 100 % and English (the journeys after this one start so).
            program.press("100 %")
            program.press("EN")
            self.assertIn(T("settings.language_note"), program.names())
            stored = e2e.stored_settings(disk)
            self.assertEqual((stored["language"], stored["text_scale"]), ("en", 100))
            self.assertEqual(legacy.read_bytes(), before, "never written")

    def test_restore_settings_repairs_a_half_finished_run(self):
        with tempfile.TemporaryDirectory() as folder:
            disk = folder_of(Path(folder))
            (Path(folder) / "settings.json").write_text(json.dumps(
                {"format": 1, "language": "lv", "text_scale": 125, "accent": "teal"}),
                encoding="utf-8")
            e2e.restore_settings(disk, language="en", text_scale=100)
            self.assertEqual(e2e.stored_settings(disk),
                             {"format": 1, "language": "en", "text_scale": 100, "accent": "teal"})


class JourneyListTests(unittest.TestCase):
    def test_the_stage37_journeys_follow_the_others(self):
        names = list(e2e.JOURNEYS)
        self.assertEqual(names[16:18], ["confirmations", "report-composition"])
        self.assertEqual(names[18:20], ["startup-workspace", "settings-language"])
        self.assertTrue(set(names).isdisjoint(e2e.STARTS_ITSELF))

    def test_a_segmented_button_is_found_with_or_without_its_tooltip(self):
        import re

        for name in ("LV", "LV. Latviešu", "LV\nLatviešu"):
            self.assertTrue(re.search(e2e.segment("LV"), name), name)
        for label, name in (("LV", "LVA"), ("LV", "ELV"), ("125 %", "125 %x")):
            self.assertFalse(re.search(e2e.segment(label), name), name)
        self.assertTrue(re.search(e2e.segment("125 %"), "125 %"))

    def test_the_program_starts_without_sra_ui_unless_a_journey_forces_one(self):
        with tempfile.TemporaryDirectory() as folder:
            gui = e2e.Gui(Path("program.exe"), Path(folder), Path(folder))
            self.assertNotIn("SRA_UI", gui.environment())
            gui.start_ui = "classic"
            self.assertEqual(gui.environment()["SRA_UI"], "classic")
            self.assertEqual(gui.environment()["SRA_DATA_DIR"], folder)


if __name__ == "__main__":
    unittest.main()
