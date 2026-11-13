"""Stage 37 (issue #68): one settings file, the research workspace as the
normal start, EN/LV in the top bar with Russian kept, typography, text size,
density, the Settings hub and the review findings D1, D2, D6, D10/D11 (the
Reports wording), U1, U10, U11, U12.

Everything runs in temporary folders: the settings file of a data folder,
and the files earlier versions kept (patched ``preferences_path``).
Synthetic data only.
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
import user_settings as us  # noqa: E402
import window_state  # noqa: E402
import workspace_tokens as tk  # noqa: E402
from workspace_harness import Workspace  # noqa: E402


def write_json(path: Path, value) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path.read_bytes()


class Folder(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.data = self.root / "data"
        self.legacy = self.root / "home" / ".statistical_research_assistant"
        self.sources = us.LegacySources(self.legacy / "preferences.json",
                                        self.legacy / "workspace.json",
                                        self.data / "profile" / "profile.json")

    def load(self) -> us.UserSettings:
        return us.UserSettings.load(us.path_for(self.data), legacy=self.sources)

    def stored(self) -> dict:
        return json.loads(us.path_for(self.data).read_text(encoding="utf-8"))


# =================================================================== the file
class MigrationTests(Folder):
    def test_the_first_start_copies_every_earlier_setting_and_changes_no_old_file(self):
        recent = [str(self.root / "a.csv")]
        prefs = write_json(self.sources.preferences, {"language": "ru", "recent_files": recent,
                                                      "appearance": "macos"})
        accent = write_json(self.sources.workspace, {"accent": "teal"})
        settings = self.load()
        self.assertEqual((settings.get("language"), settings.get("corners"),
                          settings.get("accent"), settings.get("recent_files")),
                         ("ru", "macos", "teal", recent))
        stored = self.stored()
        self.assertEqual(stored["migrated"]["from"], ["preferences.json", "workspace.json"])
        self.assertEqual(self.sources.preferences.read_bytes(), prefs, "only read")
        self.assertEqual(self.sources.workspace.read_bytes(), accent, "only read")
        # Migrated once: a later change of the old file is not read again.
        write_json(self.sources.preferences, {"language": "lv"})
        self.assertEqual(self.load().get("language"), "ru")

    def test_a_language_other_than_english_is_kept_wherever_it_was(self):
        cases = {("en", "lv"): "lv", ("ru", "en"): "ru", ("ru", None): "ru",
                 (None, "ru"): "ru", ("lv", "ru"): "ru", ("en", None): "en", (None, None): None}
        for (preferences, profile), expected in cases.items():
            with self.subTest(preferences=preferences, profile=profile):
                for path in (self.sources.preferences, self.sources.profile,
                             us.path_for(self.data)):
                    path.unlink(missing_ok=True)
                if preferences:
                    write_json(self.sources.preferences, {"language": preferences})
                if profile:
                    write_json(self.sources.profile, {"format": 1,
                                                      "profile": {"language": profile}})
                settings = self.load()
                self.assertEqual(settings.stored("language"), expected)
                self.assertEqual(settings.get("language"), expected or "en")

    def test_an_unknown_value_is_kept_in_the_file_and_shown_as_the_default(self):
        write_json(self.sources.preferences, {"language": "de", "appearance": "retro"})
        settings = self.load()
        self.assertEqual((settings.get("language"), settings.get("corners")), ("en", "windows"))
        self.assertFalse(settings.known("language"))
        self.assertTrue(settings.update(theme="dark", text_scale=125))
        stored = self.stored()
        self.assertEqual((stored["language"], stored["corners"]), ("de", "retro"),
                         "never rewritten by a save of other settings")
        self.assertEqual((stored["theme"], stored["text_scale"]), ("dark", 125))

    def test_a_value_written_by_a_newer_version_survives(self):
        write_json(us.path_for(self.data), {"format": 2, "language": "ru", "theme": "sepia",
                                           "future_key": {"x": 1}})
        settings = self.load()
        self.assertEqual((settings.get("language"), settings.get("theme")), ("ru", "light"))
        settings.update(density="compact")
        stored = self.stored()
        self.assertEqual((stored["language"], stored["theme"], stored["future_key"],
                          stored["format"]), ("ru", "sepia", {"x": 1}, 2))

    def test_a_damaged_file_gives_the_defaults_and_is_kept_aside(self):
        path = us.path_for(self.data)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        write_json(self.sources.preferences, {"language": "ru"})
        settings = self.load()
        self.assertEqual(settings.get("language"), "en", "no migration over a damaged file")
        self.assertEqual(path.read_text(encoding="utf-8"), "{not json", "not overwritten yet")
        self.assertTrue(settings.update(language="lv"))
        self.assertEqual(self.stored()["language"], "lv")
        self.assertEqual(path.with_name(us.DAMAGED_NAME).read_text(encoding="utf-8"),
                         "{not json")

    def test_values_that_are_not_offered_are_refused(self):
        settings = self.load()
        for key, value in (("language", "de"), ("text_scale", 130), ("theme", "blue"),
                           ("start_interface", "web"), ("window", {"width": 5})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                settings.update(**{key: value})
        with self.assertRaises(ValueError):
            settings.update(unknown_key=1)

    def test_a_write_that_fails_never_stops_the_program(self):
        settings = self.load()
        with mock.patch.object(us, "_write", side_effect=PermissionError("read-only")):
            self.assertFalse(settings.update(language="lv"))
        self.assertIn("read-only", settings.error)
        self.assertEqual(settings.get("language"), "lv", "applies to this session")
        self.assertTrue(settings.update(language="ru"))
        self.assertIsNone(settings.error)
        self.assertEqual(list(self.data.glob(".settings-*")), [], "no temporary file left")

    def test_reset_writes_the_defaults_and_never_migrates_again(self):
        write_json(self.sources.preferences, {"language": "ru"})
        settings = self.load()
        settings.update(theme="dark", text_scale=110, start_interface="classic")
        project = self.data / "projects" / "p1" / "project.sqlite3"
        project.parent.mkdir(parents=True)
        project.write_bytes(b"research data")
        self.assertTrue(settings.reset())
        self.assertEqual(settings.as_dict(), {**us.DEFAULTS, "recent_files": []})
        again = self.load()
        self.assertEqual(again.get("language"), "en", "the old file is not read again")
        self.assertIn("migrated", self.stored())
        self.assertEqual(project.read_bytes(), b"research data", "research data untouched")


class PreferencesCompatibilityTests(Folder):
    """``app_preferences`` (the classic screens) reads and writes the settings file."""

    def setUp(self):
        super().setUp()
        for patch in (mock.patch.dict(os.environ, {"SRA_DATA_DIR": str(self.data)}),
                      mock.patch.object(app_preferences, "preferences_path",
                                        lambda: self.sources.preferences)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_classic_screens_share_the_one_file(self):
        write_json(self.sources.preferences, {"language": "lv", "appearance": "macos"})
        self.assertEqual(app_preferences.load_preferences(),
                         app_preferences.AppPreferences("lv", (), "macos"))
        csv = self.root / "data.csv"
        csv.write_text("a\n1\n", encoding="utf-8")
        loaded = app_preferences.load_preferences()
        app_preferences.save_preferences(app_preferences.remember_file(loaded, csv))
        stored = self.stored()
        self.assertEqual((stored["language"], stored["recent_files"]),
                         ("lv", [str(csv.resolve())]))
        app_preferences.update_preferences(language="ru")
        self.assertEqual(app_preferences.load_preferences().language, "ru")
        with self.assertRaises(ValueError):
            app_preferences.update_preferences(language="xx")

    def test_saving_other_preferences_never_resets_an_unknown_language(self):
        write_json(us.path_for(self.data), {"format": 1, "language": "de"})
        loaded = app_preferences.load_preferences()
        self.assertEqual(loaded.language, "en", "shown as English")
        app_preferences.save_preferences(app_preferences.AppPreferences(
            loaded.language, ("x.csv",), "macos"))
        stored = self.stored()
        self.assertEqual((stored["language"], stored["corners"]), ("de", "macos"))


# ============================================================ the workspace
class WorkspaceSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def workspace(self, **kwargs) -> Workspace:
        ws = Workspace(root=self.root, **kwargs)
        self.addCleanup(ws.close)
        return ws

    def stored(self) -> dict:
        return json.loads((self.root / "settings.json").read_text(encoding="utf-8"))

    def test_d1_a_language_chosen_in_the_workspace_is_kept_without_a_profile(self):
        ws = self.workspace()
        ws.segment("context-language", "lv")
        self.assertFalse(ws.app.profile_path.exists(), "no researcher profile")
        ws.close()
        again = self.workspace()
        self.assertEqual(again.app.session.language, "lv")
        self.assertTrue(again.has_text("Sākums"))

    def test_d2_theme_sidebar_accent_text_size_and_density_are_kept(self):
        ws = self.workspace()
        ws.click("context-theme")
        ws.click("nav-toggle")
        ws.app.navigate("settings")
        ws.segment("settings-accent", "violet")
        ws.segment("settings-text-size", "110")
        ws.segment("settings-density", "compact")
        ws.segment("settings-typeface", "segoe_variable")
        ws.close()
        again = self.workspace()
        app = again.app
        self.assertEqual((app.theme_choice, app.session.theme), ("dark", "dark"))
        self.assertEqual(again.page.theme_mode, ft.ThemeMode.DARK)
        self.assertFalse(app.sidebar_expanded)
        self.assertEqual(app.session.accent, "violet")
        self.assertEqual((app.text_scale, app.density, app.typeface),
                         (110, "compact", "segoe_variable"))
        self.assertEqual(again.page.theme.font_family, "Segoe UI Variable Text")
        self.assertEqual((tk.ACTIVE_DENSITY, tk.SPACE_5, tk.CONTROL_HEIGHT), ("compact", 16, 36))
        again.close()
        self.assertEqual((tk.ACTIVE_DENSITY, tk.SPACE_5), ("comfortable", 24),
                         "the harness restores the default density")

    def test_the_system_theme_follows_windows(self):
        ws = self.workspace()
        ws.app.navigate("settings")
        ws.page.platform_brightness = ft.Brightness.DARK
        ws.segment("settings-theme", "system")
        self.assertEqual(ws.page.theme_mode, ft.ThemeMode.SYSTEM)
        self.assertEqual(ws.app.session.theme, "dark")
        ws.page.platform_brightness = ft.Brightness.LIGHT
        ws.app._on_brightness()
        self.assertEqual(ws.app.session.theme, "light")
        self.assertEqual(self.stored()["theme"], "system")

    def test_the_window_bounds_survive_and_never_open_off_screen(self):
        screen = [(0, 0, 1920, 1040)]
        saved = {"width": 1500, "height": 900, "left": 100, "top": 60, "maximized": False}
        self.assertEqual(window_state.placement(saved, screen),
                         window_state.Placement(1500, 900, 100, 60, False))
        # The monitor that held the window is gone: centred, same size.
        away = {**saved, "left": 2500, "top": 200}
        self.assertEqual(window_state.placement(away, screen),
                         window_state.Placement(1500, 900, None, None, False))
        # Larger than the screen now: shrunk to fit; maximized kept.
        huge = {"width": 3000, "height": 2000, "maximized": True}
        self.assertEqual(window_state.placement(huge, screen),
                         window_state.Placement(1920, 1040, None, None, True))
        self.assertEqual(window_state.placement(None, screen),
                         window_state.Placement(1200, 720))
        # Outside Windows (no screens known): the size only.
        self.assertEqual(window_state.placement(saved, None),
                         window_state.Placement(1500, 900, None, None, False))
        window = SimpleNamespace(width=1300.4, height=800, left=10, top=20, maximized=False)
        normal = window_state.capture(window)
        self.assertEqual(normal, {"width": 1300.4, "height": 800.0, "left": 10.0, "top": 20.0,
                                  "maximized": False})
        self.assertEqual(window_state.capture(window, maximized=True, previous=normal),
                         {**normal, "maximized": True}, "a maximized window keeps its bounds")
        ws = self.workspace()
        self.assertTrue(ws.app.settings.update(window=normal))
        self.assertEqual(us.UserSettings.load(us.path_for(self.root)).get("window"), normal)

    def test_the_launcher_restores_and_keeps_the_window(self):
        import app

        settings = us.UserSettings.load(us.path_for(self.root))
        settings.update(window={"width": 1400, "height": 860, "maximized": True})
        with mock.patch.object(window_state, "work_areas", return_value=[(0, 0, 1920, 1040)]):
            place = app._placement(settings)
        self.assertEqual((place.width, place.height, place.maximized), (1400, 860, True))

        class Page:
            def __init__(self):
                self.window = SimpleNamespace(width=1500, height=900, left=40, top=30,
                                              maximized=False, on_event=None)
                self.tasks = []

            def run_task(self, handler, *args):
                self.tasks.append(asyncio.run(handler(*args)))

        page = Page()
        with mock.patch.object(app, "WINDOW_SAVE_DELAY", 0), \
                mock.patch.dict(os.environ, {"SRA_STARTUP_SMOKE": ""}):
            app._keep_window(page, settings)
            page.window.on_event(SimpleNamespace(type=ft.WindowEventType.RESIZED))
        self.assertEqual(settings.get("window"), {"width": 1500.0, "height": 900.0,
                                                  "left": 40.0, "top": 30.0,
                                                  "maximized": False})
        page.window.on_event(SimpleNamespace(type=ft.WindowEventType.MAXIMIZE))
        self.assertTrue(settings.get("window")["maximized"])
        self.assertEqual(settings.get("window")["width"], 1500.0, "the normal bounds stay")

    def test_the_last_page_of_the_project_is_offered_at_the_next_start(self):
        ws = self.workspace()
        ws.type("project-new-title", "Fictional continuation study")
        ws.click("project-create")
        project = ws.app.projects.info().id
        ws.click("nav-reports")
        self.assertEqual((self.stored()["last_route"], self.stored()["last_project"]),
                         ("reports", project))
        ws.app.navigate("settings")                 # pages without a project keep the place
        self.assertEqual(self.stored()["last_route"], "reports")
        ws.close()
        again = self.workspace()
        self.assertEqual(again.app.route, "home", "the program still starts on Home")
        self.assertFalse(again.app.projects.active, "and opens no project by itself")
        self.assertTrue(again.has_text("Fictional continuation study"))
        again.click("home-continue")
        self.assertEqual((again.app.projects.info().id, again.app.route), (project, "reports"))
        again.app.navigate("home")
        self.assertEqual(again.find_all("home-continue"), [], "offered once")

    def test_u11_the_keyboard_focus_moves_to_the_next_step(self):
        ws = self.workspace()
        ws.type("project-new-title", "Fictional focus study")
        ws.click("project-create")
        self.assertEqual(ws.app.focused, "next-open-data")
        self.assertTrue(ws.find("next-open-data").autofocus)
        ws.app.projects.close()
        ws.app.navigate("home")
        ws.click(f"project-open-{ws.app.projects.projects()[0].id}")
        self.assertTrue(ws.app.focused)
        # A dialog opens with its safe answer focused.
        ws.app.navigate("home")
        info = ws.app.projects.info()
        ws.app.hub.confirm_delete(info.id, info.title)
        self.assertTrue(ws.find("project-delete-cancel").autofocus)

    def test_u10_the_research_question_uses_the_card_width(self):
        ws = self.workspace()
        ws.type("project-new-title", "Fictional width study")
        ws.click("project-create")
        field = ws.find("project-question", ft.TextField)
        row = ws.find("project-question-row", ft.Row)
        self.assertIn(field, row.controls)
        self.assertTrue(field.expand)


class TopBarAndRussianTests(unittest.TestCase):
    """Issue #68: EN and LV quick choices; Russian in Settings and the globe
    menu; a Russian preference of an earlier version survives the upgrade."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_an_earlier_russian_preference_starts_the_workspace_in_russian(self):
        before = write_json(self.root / "preferences.json",
                            {"language": "ru", "recent_files": [], "appearance": "windows"})
        ws = Workspace(root=self.root)
        self.addCleanup(ws.close)
        self.assertEqual(ws.app.session.language, "ru")
        self.assertTrue(ws.has_text("Главная"))
        quick = ws.find("context-language")
        self.assertEqual([c.data for c in ws.controls(quick) if isinstance(c, ft.Button)],
                         ["en", "lv"], "the top bar has EN and LV only")
        menu = ws.find("context-language-menu", ft.PopupMenuButton)
        self.assertEqual({item.data: item.checked for item in menu.items if item.data},
                         {"context-language-menu-en": False, "context-language-menu-lv": False,
                          "context-language-menu-ru": True,
                          "context-language-menu-settings": None})
        self.assertIn("Русский", menu.tooltip)
        ws.app.navigate("settings")
        self.assertEqual(ws.find("settings-language", ft.Dropdown).value, "ru")
        self.assertEqual((self.root / "preferences.json").read_bytes(), before)
        stored = json.loads((self.root / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["language"], "ru")

    def test_russian_from_the_globe_menu_and_settings_and_back(self):
        ws = Workspace(root=self.root)
        self.addCleanup(ws.close)
        ws.click("context-language-menu-ru")
        self.assertEqual(ws.app.session.language, "ru")
        ws.click("context-language-menu-settings")
        self.assertEqual((ws.app.route, ws.app.section), ("settings", "language"))
        ws.choose("settings-language", "lv")
        self.assertEqual(ws.app.session.language, "lv")
        ws.segment("context-language", "en")
        self.assertEqual(ws.app.session.language, "en")

    def test_an_unknown_stored_language_shows_english_and_is_kept(self):
        write_json(self.root / "settings.json", {"format": 1, "language": "de"})
        ws = Workspace(root=self.root)
        self.addCleanup(ws.close)
        self.assertEqual(ws.app.session.language, "en")
        ws.click("context-theme")
        stored = json.loads((self.root / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["language"], "de")

    def test_a_fresh_installation_takes_the_language_argument(self):
        ws = Workspace(root=self.root, language="lv")
        self.addCleanup(ws.close)
        self.assertEqual(ws.app.session.language, "lv")
        self.assertNotIn("language", json.loads(
            (self.root / "settings.json").read_text(encoding="utf-8")))


class TypographyTests(unittest.TestCase):
    def sizes(self, scale: int) -> dict:
        ws = Workspace()
        try:
            if scale != 100:
                ws.app.set_text_scale(scale)
            ws.run(ws.app.load_sample("sample_scale.csv"))
            found = {}
            for route in ("home", "data", "settings"):
                ws.app.navigate(route)
                for control in ws.controls():
                    if isinstance(control, ft.Text) and control.size and isinstance(
                            control.value, str) and control.value:
                        found.setdefault((route, control.value), control.size)
            return found
        finally:
            ws.close()

    def test_text_size_scales_every_token_text_and_keeps_12_px(self):
        normal, larger, smaller = self.sizes(100), self.sizes(125), self.sizes(90)
        shared = set(normal) & set(larger) & set(smaller)
        self.assertGreater(len(shared), 100)
        for key in shared:
            self.assertAlmostEqual(larger[key], tk.scaled(normal[key], 1.25), msg=key)
            self.assertAlmostEqual(smaller[key], max(12.0, round(normal[key] * 0.9, 1)), msg=key)
            self.assertGreaterEqual(smaller[key], tk.MIN_TEXT_SIZE, key)

    def test_the_theme_names_segoe_ui_with_fallbacks_for_latvian_and_cyrillic(self):
        theme = tk.build_theme("light", typeface="segoe", text_scale=1.25)
        self.assertEqual(theme.font_family, "Segoe UI")
        fallback = theme.text_theme.body_medium.font_family_fallback
        self.assertEqual(fallback[0], "Segoe UI Variable Text")
        self.assertIn("DejaVu Sans", fallback)
        self.assertEqual(theme.text_theme.body_medium.size, 17.5)
        self.assertEqual(tk.build_theme("light", typeface="segoe_variable").font_family,
                         "Segoe UI Variable Text")
        self.assertIsNone(tk.build_theme("light").text_theme.body_medium.size,
                          "100 %: Flutter's own sizes")

    def test_a_fallback_font_has_every_latvian_and_russian_letter(self):
        """No font is shipped: the last fallbacks must cover the glyphs on
        any computer. DejaVu Sans comes with matplotlib (and Linux); on
        Windows, Segoe UI itself is checked too."""
        import matplotlib
        from fontTools.ttLib import TTFont

        letters = "āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ" + "абвгдеёжзийклмнопрстуфхцчшщъыьэюяЁЙЩЯ"
        fonts = [Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"]
        windows = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Fonts" / "segoeui.ttf"
        if windows.is_file():
            fonts.append(windows)
        for font in fonts:
            cmap = TTFont(str(font)).getBestCmap()
            missing = [c for c in letters if ord(c) not in cmap]
            self.assertEqual(missing, [], font.name)

    def test_charts_default_to_segoe_ui_where_installed(self):
        import chart_studio as cs
        import workspace_charts

        expected = "Segoe UI" if cs._installed("Segoe UI") else "DejaVu Sans"
        self.assertEqual(cs.DEFAULT_FONT, expected)
        self.assertEqual(cs.ChartSpec(kind="histogram", variables=("x",)).font_family, expected)
        self.assertEqual(cs.resolved_font(cs.DEFAULT_FONT), expected)
        self.assertIn(cs.DEFAULT_FONT, workspace_charts.FONTS)

    def test_compact_density_and_the_comfortable_tokens(self):
        try:
            self.assertEqual(tk.apply_density("compact"), "compact")
            self.assertEqual((tk.SPACE_4, tk.SPACE_5, tk.CONTROL_HEIGHT,
                              tk.CONTEXT_BAR_HEIGHT), (12, 16, 36, 48))
            self.assertEqual(tk.build_theme("light").visual_density, ft.VisualDensity.COMPACT)
        finally:
            tk.apply_density("comfortable")
        self.assertEqual((tk.SPACE_4, tk.SPACE_5, tk.CONTROL_HEIGHT), (16, 24, 40))
        self.assertEqual(tk.apply_density("unknown"), "comfortable")


class SettingsHubTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)
        self.ws.app.navigate("settings")

    def test_every_section_of_the_hub_is_there_in_order(self):
        import workspace_settings as wst

        keys = [s.key for s in self.ws.app.pages["settings"].sections()]
        self.assertEqual(keys, ["appearance", "typography", "language", "start", "projects",
                                "backups", "updates", "ai", "profile", "ocr", "reset"])
        for key in keys:
            self.assertTrue(self.ws.find(f"settings-jump-{key}"), key)
        for data in ("settings-theme", "settings-accent", "settings-corners",
                     "settings-text-size", "settings-density", "settings-typeface",
                     "settings-language", "settings-start-interface", "settings-data",
                     "settings-data-folder", "settings-data-open", "settings-file",
                     "settings-backups-folder", "settings-backups-privacy",
                     "settings-restore-backup", "settings-updates", "settings-version",
                     "settings-updates-automatic", "settings-ai-privacy", "settings-ai",
                     "settings-profile", "settings-ocr", "settings-reset",
                     "settings-delete-data-body"):
            self.assertTrue(self.ws.find(data), data)
        self.assertEqual([o.data for o in self.ws.find("settings-text-size")
                          .content.controls], ["90", "100", "110", "125"])
        self.ws.click("settings-jump-backups")
        self.assertEqual(self.ws.app.section, "backups")
        self.assertEqual(wst.section_key("backups"), "settings-section-backups")

    def test_another_feature_adds_its_section_with_one_entry(self):
        import workspace_settings as wst

        section = wst.SettingsSection("export", "settings.section.backups", 65,
                                      lambda page: [ft.Text("Export defaults", data="x-export")])
        wst.register(section)
        self.addCleanup(wst.SECTIONS.pop, "export")
        self.ws.app.render()
        keys = [s.key for s in self.ws.app.pages["settings"].sections()]
        self.assertEqual(keys.index("export"), keys.index("backups") + 1)
        self.assertTrue(self.ws.find("x-export"))
        self.assertTrue(self.ws.find("settings-section-export"))

    def test_reset_settings_is_confirmed_and_keeps_research_data(self):
        app = self.ws.app
        app.projects.create("Fictional reset study")
        app.set_language("lv")
        app.set_text_scale(125)
        app.set_theme("dark")
        app.navigate("settings")
        self.ws.click("settings-reset")
        self.assertEqual(self.ws.page.dialog.data, "settings-reset-dialog")
        self.assertTrue(self.ws.find("settings-reset-cancel").autofocus, "the safe answer")
        self.ws.click("settings-reset-confirm")
        self.assertEqual((app.session.language, app.text_scale, app.theme_choice),
                         ("en", 100, "light"))
        self.assertEqual([p.title for p in app.projects.projects()], ["Fictional reset study"])
        self.assertTrue(self.ws.has_text("No research data was changed"))

    def test_the_start_interface_is_chosen_here(self):
        self.ws.choose("settings-start-interface", "classic")
        self.assertEqual(self.ws.app.settings.get("start_interface"), "classic")
        stored = json.loads(self.ws.app.settings.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["start_interface"], "classic")

    def test_recent_data_files_are_listed_and_cleared(self):
        app = self.ws.app
        csv = self.ws.root / "fictional.csv"
        csv.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
        self.ws.run(app.load_path(str(csv)))
        app.navigate("settings")
        self.assertTrue(self.ws.has_text(str(csv.resolve())))
        self.ws.click("settings-recent-clear")
        self.assertEqual(app.recent_files(), [])
        self.assertTrue(csv.exists(), "the file itself stays")


class StartInterfaceTests(unittest.TestCase):
    """U1: the research workspace is the normal start, also for researchers
    with older settings; the classic interface stays one click away."""

    def test_the_start_interface_is_the_request_then_sra_ui_then_settings(self):
        import research_app

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, {"SRA_DATA_DIR": folder, "SRA_UI": ""}), \
                mock.patch.object(app_preferences, "preferences_path",
                                  lambda: Path(folder) / "old" / "preferences.json"):
            self.assertEqual(research_app.start_interface(), "workspace")
            us.UserSettings.load(us.path_for(Path(folder))).update(start_interface="classic")
            self.assertEqual(research_app.start_interface(), "classic")
            with mock.patch.dict(os.environ, {"SRA_UI": "workspace"}):
                self.assertEqual(research_app.start_interface(), "workspace")
            self.assertEqual(research_app.start_interface("workspace"), "workspace")
            with mock.patch.dict(os.environ, {"SRA_UI": "nonsense"}):
                self.assertEqual(research_app.start_interface(), "classic")

    def test_the_program_starts_in_the_workspace_and_the_classic_one_follows_its_language(self):
        import research_app
        from flet.controls.context import _context_page
        from ux_inventory import FakePage, walk

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, {"SRA_DATA_DIR": folder, "SRA_UI": ""}), \
                mock.patch.object(app_preferences, "preferences_path",
                                  lambda: Path(folder) / "old" / "preferences.json"):
            page = FakePage()
            page.show_dialog = lambda dialog: None
            token = _context_page.set(page)
            try:
                asyncio.run(research_app.main(page))
                from workspace_shell import active_app

                app = active_app()
                self.assertIs(page.controls[0], app.root, "the workspace, no preview step")
                app.set_language("lv")
                found = []
                walk(page.controls[0], lambda c, d: found.append(c)
                     if getattr(c, "data", None) == "nav-classic" else None)
                asyncio.run(found[0].on_click(SimpleNamespace(control=found[0])))
                classic = page.controls[0]
                self.assertNotEqual(getattr(classic, "data", None), "workspace-root")
                texts = []
                walk(classic, lambda c, d: texts.append(c.value)
                     if isinstance(c, ft.Text) and isinstance(c.value, str) else None)
                self.assertIn("Atvērt pētījumu darba vidi", texts,
                              "the classic screens follow the language chosen in the workspace")
                self.assertEqual(app_preferences.load_preferences().language, "lv")
            finally:
                _context_page.reset(token)

    def test_help_and_settings_offer_the_classic_interface(self):
        from workspace_shell import ClassicBridge

        called = []
        ws = Workspace(bridge=None)
        self.addCleanup(ws.close)
        ws.app.bridge = ClassicBridge(survey_root=ws.root / "surveys",
                                      return_to_classic=lambda: called.append(True))
        ws.app.navigate("help")
        self.assertTrue(ws.find("help-classic"))
        self.assertTrue(ws.find("help-settings"))
        ws.app.navigate("settings")
        self.assertTrue(ws.find("settings-open-classic"))
        ws.click("settings-open-classic")
        self.assertEqual(called, [True])
        self.assertTrue(ws.find("nav-classic"))


class ReviewFindingTests(unittest.TestCase):
    def test_d6_the_preparation_caption_is_readable(self):
        import preparation_ui

        page = SimpleNamespace(services=[], update=lambda: None)
        classic, _ = preparation_ui.build_preparation_workspace(page, lambda frame: None)
        caption = next(c for c in classic.controls if getattr(c, "data", None)
                       == "preparation-caption")
        for background in ("#FFFFFF", "#F5F7FC"):
            self.assertGreaterEqual(tk.contrast_ratio(caption.color, background), 4.5)
        hosted, _ = preparation_ui.build_preparation_workspace(page, lambda frame: None,
                                                               caption_color=None)
        caption = next(c for c in hosted.controls if getattr(c, "data", None)
                       == "preparation-caption")
        self.assertIsNone(caption.color, "the workspace theme's text colour (light or dark)")

    def test_d11_report_sections_count_their_parts_and_name_the_report_language(self):
        from workspace_text import count_text

        self.assertEqual([count_text("en", n, "parts") for n in (1, 2)], ["1 part", "2 parts"])
        self.assertEqual([count_text("lv", n, "parts") for n in (1, 2, 0)],
                         ["1 daļa", "2 daļas", "0 daļu"])
        self.assertEqual([count_text("ru", n, "parts") for n in (1, 3, 5)],
                         ["1 часть", "3 части", "5 частей"])
        ws = Workspace()
        self.addCleanup(ws.close)
        ws.run(ws.app.load_sample("sample_scale.csv"))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.run(ws.app.pages["analyze"]._execute("descriptive", {"variable": "stress_q1"}, {}, {}))
        ws.app.session.toggle_report(ws.app.session.results[-1].id)
        ws.app.navigate("reports")
        labels = [c.label for c in ws.find_all("reports-section-") if isinstance(c, ft.Checkbox)]
        self.assertFalse([label for label in labels if " 1 parts" in label])
        self.assertTrue(any(label.endswith(" · 1 part") for label in labels), labels)
        self.assertEqual(ws.find_all("reports-section-language"), [])
        ws.app.session.update_report(language="lv")
        ws.app.render()
        self.assertTrue(ws.find("reports-section-language"))
        self.assertTrue(ws.has_text("Latviešu"))


class StartupCheckTests(unittest.TestCase):
    """tools/check_gui_startup.py: the normal start shows the workspace;
    ``--classic`` checks the classic interface (Windows workflows)."""

    def test_the_expected_interface(self):
        import check_gui_startup as check

        workspace = {"workspace_present": True, "has_home_banner": False}
        classic = {"workspace_present": False, "has_home_banner": True}
        self.assertEqual(check.interface_errors(workspace, "workspace"), [])
        self.assertEqual(check.interface_errors(classic, "classic"), [])
        self.assertTrue(check.interface_errors(classic, "workspace"))
        self.assertTrue(check.interface_errors(workspace, "classic"))
        self.assertEqual(check.ui_override("workspace"), "workspace")
        self.assertEqual(check.ui_override("classic"), "classic")
        self.assertIsNone(check.ui_override(None))


class DraftTextTests(unittest.TestCase):
    def test_every_new_text_has_three_languages_and_is_listed_for_review(self):
        from workspace_text import DRAFT_KEYS, T

        self.assertGreater(len(DRAFT_KEYS), 40)
        for key in DRAFT_KEYS:
            self.assertEqual(len(T[key]), 3, key)
            self.assertTrue(all(value.strip() for value in T[key]), key)
        doc = (ROOT / "docs" / "STAGE37_UX_SHELL.md").read_text(encoding="utf-8")
        self.assertEqual([key for key in sorted(DRAFT_KEYS) if f"`{key}`" not in doc], [])

    def test_settings_choices_match_the_tokens(self):
        self.assertEqual(us.ACCENTS, tuple(tk.ACCENTS))
        self.assertEqual(us.TEXT_SCALES, tk.TEXT_SCALES)
        self.assertEqual(us.DENSITIES, tuple(tk.DENSITIES))
        self.assertEqual(us.TYPEFACES, tuple(tk.TYPEFACES))


if __name__ == "__main__":
    unittest.main()
