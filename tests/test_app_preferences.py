"""Preferences are local; English is always the first-launch default."""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from app_preferences import (
    AppPreferences, load_preferences, save_preferences, remember_file,
)
from localization import LANGUAGES, tr


class DesktopPreferencesTests(unittest.TestCase):
    def test_first_launch_english_then_latvian_and_russian_opt_in(self):
        with TemporaryDirectory() as folder:
            location = Path(folder) / "prefs.json"
            first = load_preferences(location)
            self.assertEqual(first.language, "en")
            self.assertEqual(first.recent_files, ())
            save_preferences(AppPreferences(language="lv"), location)
            self.assertEqual(load_preferences(location).language, "lv")
            save_preferences(AppPreferences(language="ru"), location)
            self.assertEqual(load_preferences(location).language, "ru")

    def test_unknown_or_corrupted_language_falls_back_to_english(self):
        with TemporaryDirectory() as folder:
            location = Path(folder) / "prefs.json"
            location.write_text('{"language": "xx"}', encoding="utf-8")
            self.assertEqual(load_preferences(location).language, "en")
            location.write_text('this is not JSON', encoding="utf-8")
            self.assertEqual(load_preferences(location), AppPreferences())
            with self.assertRaisesRegex(ValueError, "en, lv or ru"):
                save_preferences(AppPreferences(language="de"), location)

    def test_windows_default_and_user_selected_mac_style_are_local(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "appearance.json"
            initial = load_preferences(file)
            self.assertEqual(initial.appearance, "windows")
            save_preferences(
                AppPreferences(language="lv", appearance="macos"), file
            )
            self.assertEqual(load_preferences(file).appearance, "macos")
            stored = json.loads(file.read_text(encoding="utf-8"))
            self.assertEqual(stored["appearance"], "macos")
            stored["appearance"] = "unrecognized-style"
            file.write_text(json.dumps(stored), encoding="utf-8")
            self.assertEqual(load_preferences(file).appearance, "windows")
            with self.assertRaisesRegex(ValueError, "Appearance"):
                save_preferences(AppPreferences(appearance="other"), file)

    def test_recent_files_are_deduplicated_bounded_and_local(self):
        with TemporaryDirectory() as folder:
            location = Path(folder) / "prefs.json"
            prefs = AppPreferences()
            files = []
            for i in range(12):
                path = Path(folder) / f"test{i}.csv"
                path.write_text("x\n1\n", encoding="utf-8")
                files.append(path)
                prefs = remember_file(prefs, path)
            self.assertEqual(len(prefs.recent_files), 8)
            prefs = remember_file(prefs, files[-1])
            self.assertEqual(len(prefs.recent_files), 8)
            prefs = remember_file(prefs, Path(folder) / "missing.csv")
            self.assertEqual(len(prefs.recent_files), 8)
            save_preferences(prefs, location)
            loaded = load_preferences(location)
            self.assertEqual(len(loaded.recent_files), 8)
            self.assertEqual(loaded.recent_files[0], str(files[-1].resolve()))
            self.assertTrue(location.is_file())
            content = json.loads(location.read_text(encoding="utf-8"))
            self.assertEqual(content["language"], "en")

    def test_user_visible_navigation_and_fallback(self):
        self.assertEqual(LANGUAGES, {
            "en": "English", "lv": "Latviešu", "ru": "Русский"
        })
        self.assertEqual(tr("en", "Home"), "Home")
        self.assertEqual(tr("ru", "Home"), "Главная")
        self.assertEqual(tr("lv", "Home"), "Sākums")
        self.assertEqual(tr("xx", "Home"), "Home")
        self.assertEqual(tr("ru", "Untranslated scientific term"), "Untranslated scientific term")


if __name__ == "__main__":
    unittest.main()
