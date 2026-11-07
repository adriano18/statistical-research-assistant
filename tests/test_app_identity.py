"""Stage 35 (#44, #45): version identity, build information and the
installer layout. Runs on every OS; the installer itself is compiled and
installed on Windows CI."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import app_identity as ai  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_semver_precedence(self):
        ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                   "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1",
                   "1.1.0-preview.1", "1.1.0", "2.0.0"]
        versions = [ai.parse_version(v) for v in ordered]
        for lower, higher in zip(versions, versions[1:]):
            with self.subTest(lower=str(lower), higher=str(higher)):
                self.assertLess(lower, higher)
                self.assertGreater(higher, lower)
        self.assertEqual(ai.parse_version("1.0.0+build.5"), ai.parse_version("1.0.0+other"))

    def test_only_semver_is_accepted(self):
        for text in ("1.0", "v1.0.0", "1.0.0.0", "01.0.0", "1.0.0-", "1.0.0-01", "", "1.0.0 ",
                     "1.0.0-a b", "9" * 70 + ".0.0"):
            with self.subTest(text=text):
                if text == "1.0.0 ":
                    self.assertEqual(str(ai.parse_version(text)), "1.0.0")
                    continue
                with self.assertRaises(ValueError):
                    ai.parse_version(text)

    def test_windows_version_resources_get_four_numbers(self):
        self.assertEqual(ai.parse_version("1.2.3-preview.4").numeric, "1.2.3.0")

    def test_the_source_version_is_semver(self):
        self.assertFalse(ai.parse_version(ai.VERSION).prerelease)


class BuildInfoTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.folder, True)

    def write(self, value) -> Path:
        path = self.folder / ai.BUILD_INFO
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def test_a_source_checkout_reports_the_source_channel(self):
        info = ai.read_build_info(self.folder / "missing.json")
        self.assertEqual((info.version, info.channel, info.distributed), (ai.VERSION, "source", False))
        self.assertEqual(ai.read_build_info(self.write("{broken")).channel, "source")

    def test_values_of_the_wrong_type_are_ignored(self):
        info = ai.read_build_info(self.write({
            "version": "1.2.0-preview.1", "channel": "preview", "signed": "yes",
            "update_keys": ["a", 3], "build": "41", "unknown": 1}))
        self.assertEqual((info.version, info.channel, info.build), ("1.2.0-preview.1", "preview", "41"))
        self.assertFalse(info.signed)
        self.assertEqual(info.update_keys, ())
        self.assertEqual(info.endpoint, ai.UPDATE_ENDPOINTS["preview"])

    def test_an_invalid_version_falls_back_to_the_source_identity(self):
        info = ai.read_build_info(self.write({"version": "latest", "channel": "stable"}))
        self.assertEqual((info.version, info.channel), (ai.VERSION, "source"))

    def test_describe_names_version_channel_and_project_format(self):
        import project_store

        about = ai.describe(ai.BuildInfo(version="1.0.0", channel="stable", build="7"))
        self.assertEqual((about["version"], about["channel"], about["build"]), ("1.0.0", "stable", "7"))
        self.assertEqual(about["project_format"], project_store.SCHEMA_VERSION)


class WriteBuildInfoTests(unittest.TestCase):
    def run_tool(self, *args) -> dict:
        import write_build_info

        out = Path(tempfile.mkdtemp()) / ai.BUILD_INFO
        write_build_info.main([*args, "--out", str(out)])
        return json.loads(out.read_text(encoding="utf-8"))

    def test_a_stable_build_must_carry_the_source_version(self):
        self.assertEqual(self.run_tool("--channel", "stable")["version"], ai.VERSION)
        with self.assertRaises(SystemExit):
            self.run_tool("--channel", "stable", "--version", "9.9.9")
        with self.assertRaises(SystemExit):
            self.run_tool("--channel", "preview", "--version", ai.VERSION)

    def test_a_local_test_endpoint_is_only_for_test_builds(self):
        info = self.run_tool("--channel", "test", "--version", "1.0.1-test.1",
                             "--test-endpoint", "http://127.0.0.1:8765/manifest.json",
                             "--update-key", "AAAA")
        self.assertEqual((info["test_endpoint"], info["update_keys"]),
                         ("http://127.0.0.1:8765/manifest.json", ["AAAA"]))
        for args in (("--channel", "preview", "--version", "1.0.1-preview.1",
                      "--test-endpoint", "http://127.0.0.1:1/"),
                     ("--channel", "test", "--version", "1.0.1-test.1",
                      "--test-endpoint", "http://example.org/")):
            with self.subTest(args=args), self.assertRaises(SystemExit):
                self.run_tool(*args)


class InstallerLayoutTests(unittest.TestCase):
    def test_updates_remove_old_program_files_but_never_app_data(self):
        import build_installer

        bundle = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, bundle, True)
        for name in ("StatisticalResearchAssistant.exe", "flutter_windows.dll", "python312.dll"):
            (bundle / name).write_bytes(b"x")
        for folder in ("data/flutter_assets", "site-packages/numpy", "app/bundled_ocr",
                       "app/examples", "app/data/surveys"):
            (bundle / folder).mkdir(parents=True)
        (bundle / "app" / "app.py").write_text("")
        text = build_installer.layout(bundle)
        install, uninstall = text.split("[UninstallDelete]")
        for entry in ('Type: files; Name: "{app}\\StatisticalResearchAssistant.exe"',
                      'Type: filesandordirs; Name: "{app}\\site-packages"',
                      'Type: filesandordirs; Name: "{app}\\data"',
                      'Type: filesandordirs; Name: "{app}\\app\\bundled_ocr"',
                      'Type: files; Name: "{app}\\app\\app.py"'):
            self.assertIn(entry, install)
        self.assertNotIn("app\\data", text, "old portable questionnaires are never deleted")
        self.assertIn('Type: filesandordirs; Name: "{app}\\app\\__pycache__"', uninstall)
        self.assertNotIn("Type: files;", uninstall, "the uninstaller removes installed files itself")

    def test_the_script_keeps_one_app_id_and_per_user_defaults(self):
        script = (ROOT / "packaging" / "windows" / "StatisticalResearchAssistant.iss").read_text(
            encoding="utf-8")
        self.assertIn("AppId={" + ai.INSTALLER_APP_ID, script)
        self.assertIn("PrivilegesRequired=lowest", script)
        self.assertIn("DefaultDirName={autopf}", script)
        self.assertIn(ai.MUTEX, script)
        self.assertIn("if (not UninstallSilent) and DirExists(Folder)", script)
        self.assertIn("StatisticalResearchAssistant-{#AppVersion}-Setup", script)
        self.assertNotIn("{app}\\app\\data", script)


if __name__ == "__main__":
    unittest.main()
