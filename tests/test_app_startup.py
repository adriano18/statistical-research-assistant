"""Desktop launcher: splash first, background workspace import, diagnostics.

Builds the REAL research workspace on a lightweight fake page, so the same
code path the Windows executable runs is exercised on every CI platform.
"""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]


class _Window(SimpleNamespace):
    async def center(self):
        return None


class FakePage:
    """Just enough of ft.Page for building controls without a client."""

    def __init__(self):
        self.controls = []
        self.services = []
        self.overlay = []
        self.window = _Window()
        self.web = False
        self.width = 1280
        self.height = 800
        self.updates = 0
        self._services = SimpleNamespace(
            register_service=lambda service: None,
            unregister_services=lambda: None,
        )

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        self.updates += 1


def run_start(page, **kwargs):
    import app
    from flet.controls.context import _context_page

    token = _context_page.set(page)
    try:
        asyncio.run(app.start(page, **kwargs))
    finally:
        _context_page.reset(token)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Projects and the settings file in a temporary data folder; the
        # preferences file of earlier versions there too (none: a new user).
        self.data = Path(self.temp.name) / "data"
        self.env = patch.dict(os.environ, {
            "SRA_LOG_DIR": self.temp.name, "MPLBACKEND": "Agg",
            "SRA_STARTUP_SMOKE": "", "SRA_DATA_DIR": str(self.data), "SRA_UI": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        import app_preferences

        legacy = patch.object(app_preferences, "preferences_path",
                              lambda: Path(self.temp.name) / "legacy" / "preferences.json")
        legacy.start()
        self.addCleanup(legacy.stop)

    def test_launcher_module_does_not_import_heavy_libraries(self):
        code = (
            "import sys, app; heavy = [m for m in ('pandas', 'scipy', 'statsmodels', "
            "'pingouin', 'matplotlib', 'research_app') if m in sys.modules]; "
            "print(','.join(heavy))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, capture_output=True,
            text=True, timeout=120, env={**os.environ, "SRA_OCR_SELFTEST": ""},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_real_workspace_replaces_splash_and_logs_timings(self):
        from startup_diagnostics import StartupTimeline

        page = FakePage()
        seen_during_import = []

        def importer():
            # The splash must already be on screen while libraries load.
            seen_during_import.append(
                [getattr(c, "data", None) for c in page.controls]
            )
            import importlib
            return importlib.import_module("research_app")

        timeline = StartupTimeline()
        run_start(page, import_workspace=importer, timeline=timeline)
        self.assertEqual(seen_during_import, [["startup-splash"]])
        self.assertEqual(timeline.outcome, "ok", timeline.error)
        phases = [name for name, _ in timeline.phases]
        for expected in ("page_connected", "splash_shown", "workspace_imported",
                         "interface_built", "interface_ready"):
            self.assertIn(expected, phases)
        self.assertLess(phases.index("splash_shown"), phases.index("workspace_imported"))
        import app
        summary = app._smoke_summary(page)
        # Stage 37 (#68): the research workspace is the normal start.
        self.assertTrue(summary["workspace_present"])
        self.assertEqual(summary["interface"], "workspace")
        self.assertFalse(summary["has_home_banner"])
        self.assertFalse(summary["splash_present"])
        self.assertFalse(summary["failure_present"])
        self.assertIn("workspace_shown", phases)
        log = Path(self.temp.name) / "startup.log"
        record = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["outcome"], "ok")
        self.assertEqual(set(record), {"time", "outcome", "phases", "python",
                                       "platform", "packaged", "error"})

    def test_failure_is_visible_and_logged_instead_of_a_blank_window(self):
        from startup_diagnostics import StartupTimeline

        def broken():
            raise ImportError("synthetic missing DLL")

        page = FakePage()
        timeline = StartupTimeline()
        run_start(page, import_workspace=broken, timeline=timeline)
        self.assertEqual(timeline.outcome, "failed")
        self.assertEqual([getattr(c, "data", None) for c in page.controls],
                         ["startup-failure"])
        import app
        summary = app._smoke_summary(page)
        self.assertTrue(summary["failure_present"])
        record = json.loads((Path(self.temp.name) / "startup.log")
                            .read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(record["outcome"], "failed")
        self.assertIn("synthetic missing DLL", record["error"])

    def test_smoke_mode_writes_result_for_the_windows_gui_check(self):
        import importlib
        from startup_diagnostics import StartupTimeline

        result = Path(self.temp.name) / "smoke.json"
        page = FakePage()
        with patch.dict(os.environ, {"SRA_STARTUP_SMOKE": str(result),
                                     "SRA_STARTUP_SMOKE_HOLD": "600"}):
            run_start(page, import_workspace=lambda: importlib.import_module("research_app"),
                      timeline=StartupTimeline())
        data = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(data["outcome"], "ok")
        self.assertTrue(data["workspace_present"])
        self.assertEqual(data["interface"], "workspace")
        self.assertEqual(data["pid"], os.getpid())

    def test_the_classic_interface_starts_when_chosen_or_requested(self):
        """The classic interface stays available: as the researcher's start
        choice (Settings), or for one run with SRA_UI=classic."""
        import importlib

        import app
        from startup_diagnostics import StartupTimeline
        from user_settings import UserSettings, path_for

        UserSettings.load(path_for(self.data)).update(start_interface="classic")
        page = FakePage()
        run_start(page, import_workspace=lambda: importlib.import_module("research_app"),
                  timeline=StartupTimeline())
        summary = app._smoke_summary(page)
        self.assertEqual((summary["interface"], summary["has_home_banner"]), ("classic", True))
        UserSettings.load(path_for(self.data)).update(start_interface="workspace")
        with patch.dict(os.environ, {"SRA_UI": "classic"}):
            page = FakePage()
            run_start(page, import_workspace=lambda: importlib.import_module("research_app"),
                      timeline=StartupTimeline())
        self.assertEqual(app._smoke_summary(page)["interface"], "classic")
        stored = json.loads((self.data / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["start_interface"], "workspace", "SRA_UI changes no setting")


class DataLocationTests(unittest.TestCase):
    def test_source_checkout_keeps_repository_survey_folder(self):
        from startup_diagnostics import survey_data_root

        with patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": "", "SRA_DATA_DIR": ""}):
            self.assertEqual(survey_data_root(ROOT), ROOT / "data" / "surveys")

    def test_packaged_build_uses_durable_user_folder(self):
        import app_paths
        import startup_diagnostics as sd

        with TemporaryDirectory() as bundle, TemporaryDirectory() as data:
            with patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": data, "SRA_DATA_DIR": ""}):
                with patch.object(sd, "is_packaged", return_value=True), \
                        patch.object(app_paths, "_windows", return_value=False):
                    self.assertEqual(sd.survey_data_root(Path(bundle)),
                                     Path(data) / "surveys")
                    legacy = Path(bundle) / "data" / "surveys"
                    legacy.mkdir(parents=True)
                    (legacy / "surveys.sqlite3").write_bytes(b"x")
                    # Stage 35: never used in place inside the program folder;
                    # legacy_data offers to copy it into the data folder.
                    self.assertEqual(sd.survey_data_root(Path(bundle)),
                                     Path(data) / "surveys")

    def test_log_folder_falls_back_when_first_choice_is_not_writable(self):
        import startup_diagnostics as sd

        with TemporaryDirectory() as temp:
            blocked = Path(temp) / "file-not-dir"
            blocked.write_text("x")
            with patch.dict(os.environ, {"SRA_LOG_DIR": str(blocked / "logs"),
                                         "LOCALAPPDATA": temp}):
                folder = sd.writable_log_directory()
            self.assertEqual(folder, Path(temp) / "StatisticalResearchAssistant" / "logs")


if __name__ == "__main__":
    unittest.main()
