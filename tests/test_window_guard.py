"""The window guard: a started program never stays invisible (Windows).

CI saw the packaged program's runner window stay hidden after a complete
start (installer run 42648266085). The guard shows this process's own
window once if it is still hidden; it never touches a visible window, a
minimized one (which is visible) or anything outside Windows. A fake Win32
layer stands in for user32 here; the packaged EXE journeys exercise the
real one.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import window_guard as wg  # noqa: E402


class FakeWindows:
    def __init__(self, states, *, show_works=True):
        self.states = list(states)        # what each check sees
        self.shown: list[int] = []
        self.show_works = show_works
        self.pids: list[int] = []

    def own_windows(self, pid):
        self.pids.append(pid)
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def show(self, handle):
        self.shown.append(handle)
        return self.show_works if isinstance(self.show_works, bool) else self.show_works.pop(0)


def run_guard(windows, checks=(3.0, 8.0, 15.0, 30.0)):
    slept, logged = [], []

    async def sleep(seconds):
        slept.append(seconds)

    outcome = asyncio.run(wg.guard(windows=windows, pid=4242, checks=checks,
                                   log=logged.append, sleep=sleep))
    return outcome, slept, logged


HIDDEN = wg.NativeWindow(handle=77, visible=False, minimized=False)
VISIBLE = wg.NativeWindow(handle=77, visible=True, minimized=False)
MINIMIZED = wg.NativeWindow(handle=77, visible=True, minimized=True)


class GuardTests(unittest.TestCase):
    def test_a_visible_window_is_left_alone_and_the_guard_stops(self):
        windows = FakeWindows([[VISIBLE]])
        outcome, slept, logged = run_guard(windows)
        self.assertEqual(outcome, "visible")
        self.assertEqual(windows.shown, [])
        self.assertEqual(slept, [3.0], "one check, then the guard is done")
        self.assertEqual(logged, [])
        self.assertEqual(windows.pids, [4242], "only this process's windows")

    def test_a_minimized_window_is_the_users_choice(self):
        windows = FakeWindows([[MINIMIZED]])
        self.assertEqual(run_guard(windows)[0], "visible")
        self.assertEqual(windows.shown, [])

    def test_a_hidden_window_is_shown_once_and_logged(self):
        windows = FakeWindows([[HIDDEN]])
        outcome, slept, logged = run_guard(windows)
        self.assertEqual(outcome, "shown")
        self.assertEqual(windows.shown, [77])
        self.assertEqual(slept, [3.0])
        self.assertEqual(len(logged), 1)
        self.assertEqual((logged[0]["event"], logged[0]["outcome"]), ("window_guard", "shown"))

    def test_a_window_shown_late_by_the_runner_needs_nothing(self):
        windows = FakeWindows([[VISIBLE], [VISIBLE]])
        self.assertEqual(run_guard(windows)[0], "visible")
        self.assertEqual(windows.shown, [])

    def test_a_failed_attempt_is_retried_at_the_next_check(self):
        windows = FakeWindows([[HIDDEN]], show_works=[False, True])
        outcome, slept, logged = run_guard(windows)
        self.assertEqual(outcome, "shown")
        self.assertEqual(slept, [3.0, 5.0], "checks at 3 s and 8 s after the splash")
        self.assertEqual([entry["outcome"] for entry in logged], ["failed", "shown"])

    def test_without_an_own_window_there_is_nothing_to_guard(self):
        # flet run (development): the window belongs to another process.
        windows = FakeWindows([[]])
        outcome, slept, logged = run_guard(windows)
        self.assertEqual((outcome, slept, logged), ("no_window", [3.0], []))

    def test_outside_windows_nothing_is_done(self):
        if sys.platform == "win32":
            self.skipTest("checks the non-Windows path")
        self.assertEqual(wg.ensure_shown(), "unsupported")

    def test_errors_never_reach_the_program(self):
        class Broken:
            def own_windows(self, pid):
                raise OSError("no access")

            def show(self, handle):
                raise AssertionError("not reached")

        self.assertEqual(wg.ensure_shown(Broken(), pid=1), "unsupported")

        class ShowRaises(FakeWindows):
            def show(self, handle):
                raise OSError("denied")

        self.assertEqual(wg.ensure_shown(ShowRaises([[HIDDEN]]), pid=1), "failed")


class StartupHookTests(unittest.TestCase):
    def test_the_launcher_starts_the_guard_after_the_splash_and_logs_its_events(self):
        from test_app_startup import FakePage, run_start
        from startup_diagnostics import StartupTimeline

        with TemporaryDirectory() as folder, patch.dict(os.environ, {
                "SRA_LOG_DIR": folder, "MPLBACKEND": "Agg", "SRA_STARTUP_SMOKE": "",
                "SRA_WINDOW_GUARD": ""}):
            calls = []

            async def fake_guard(*, log):
                calls.append(log)
                log({"event": "window_guard", "outcome": "shown", "after_s": 3.0})
                return "shown"

            with patch.object(wg, "guard", fake_guard):
                page = FakePage()
                timeline = StartupTimeline()
                run_start(page, import_workspace=lambda: __import__("research_app"),
                          timeline=timeline)
            self.assertEqual(timeline.outcome, "ok", timeline.error)
            self.assertEqual(len(calls), 1)
            lines = [json.loads(line) for line in
                     (Path(folder) / "startup.log").read_text(encoding="utf-8").splitlines()]
            self.assertIn({"event": "window_guard", "outcome": "shown", "after_s": 3.0}, lines)
            records = [line for line in lines if "phases" in line]
            self.assertEqual([r["outcome"] for r in records], ["ok"],
                             "the startup record is still written")

    def test_the_guard_can_be_switched_off_for_diagnosis(self):
        from test_app_startup import FakePage, run_start
        from startup_diagnostics import StartupTimeline

        with TemporaryDirectory() as folder, patch.dict(os.environ, {
                "SRA_LOG_DIR": folder, "MPLBACKEND": "Agg", "SRA_STARTUP_SMOKE": "",
                "SRA_WINDOW_GUARD": "0"}):
            calls = []

            async def fake_guard(*, log):
                calls.append(log)

            with patch.object(wg, "guard", fake_guard):
                run_start(FakePage(), import_workspace=lambda: __import__("research_app"),
                          timeline=StartupTimeline())
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
