"""Research projects in the workspace interface (Stage 34, issue #24).

Synthetic data only. Drives the real Flet controls through the test harness:
Home's project hub, the context bar, Results and Reports.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd  # noqa: E402

from workspace_harness import Workspace  # noqa: E402

EXAMPLES = ROOT / "examples"
GROUPS = {"outcome": "stress_q1", "group": "group"}


class ProjectWorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data = self.base / "measurements.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", self.data)
        # Recent files are a user preference outside the test folder.
        remember = mock.patch("workspace_shell.WorkspaceApp._remember_file")
        remember.start()
        self.addCleanup(remember.stop)

    def workspace(self, **kwargs) -> Workspace:
        ws = Workspace(root=self.base, **kwargs)
        self.addCleanup(ws.close)
        return ws

    def create(self, ws: Workspace, title: str):
        ws.app.navigate("home")
        ws.type("project-new-title", title)          # action 1
        ws.click("project-create")                   # action 2
        return ws.app.projects.info()

    def analyse(self, ws: Workspace):
        self.assertTrue(ws.run(ws.app.load_path(str(self.data))))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        entry = ws.run(ws.app.pages["analyze"]._execute("groups", GROUPS, {},
                                                        {"independent": True}))
        self.assertIsNotNone(entry)
        return entry


class ProjectHubTests(ProjectWorkspaceCase):
    def test_a_project_is_created_in_two_actions_and_saves_without_a_save_step(self):
        ws = self.workspace()
        self.assertTrue(ws.has_text("No project"))
        info = self.create(ws, "Sleep and stress")
        self.assertEqual(info.title, "Sleep and stress")
        self.assertTrue(ws.has_text("Project: Sleep and stress"))
        entry = self.analyse(ws)
        ws.click("result-add-report")
        self.assertTrue(ws.has_text("Results are saved automatically in the project"))
        runs = ws.app.projects.project.runs()
        self.assertEqual([r.id for r in runs], [entry.record_id])
        self.assertEqual([r.id for r in ws.app.projects.project.report_runs()], [entry.record_id])

    def test_reopening_after_a_restart_restores_data_levels_results_and_report(self):
        ws = self.workspace()
        info = self.create(ws, "Restart check")
        entry = self.analyse(ws)
        ws.click("result-add-report")
        report = entry.run.report
        ws.close()                                   # the application quits

        again = self.workspace()
        again.app.navigate("home")
        self.assertTrue(again.has_text("Restart check"))
        again.click(f"project-open-{info.id}")
        session = again.app.session
        self.assertEqual(session.source_name, "measurements.csv")
        self.assertEqual(session.level("stress_q1"), "ordinal")
        self.assertEqual(len(session.results), 1)
        restored = session.results[0]
        self.assertEqual(restored.run.report, report)
        self.assertTrue(restored.in_report)
        # The background check recalculated it on the stored table, so the
        # Word export (which needs the engine's result object) works.
        self.assertIsNotNone(restored.run.result)
        again.app.navigate("results")
        again.click("export-docx")
        self.assertTrue(again.saved[-1].is_file())
        self.assertFalse(again.app.projects.message, "a clean exit is not a recovery")

    def test_switching_projects_from_home_keeps_their_work_apart(self):
        ws = self.workspace()
        first = self.create(ws, "First study")
        self.analyse(ws)
        second = self.create(ws, "Second study")
        self.assertFalse(ws.app.session.has_data)
        self.assertEqual(ws.app.session.results, [])
        ws.run(ws.app.load_sample("sample_three_groups.csv"))
        ws.app.navigate("home")
        ws.click(f"project-open-{first.id}")
        self.assertEqual(ws.app.session.source_name, "measurements.csv")
        self.assertEqual(len(ws.app.session.results), 1)
        ws.click(f"project-open-{second.id}")
        self.assertEqual(ws.app.session.source_name, "sample_three_groups.csv")
        self.assertEqual(ws.app.session.results, [])
        self.assertTrue(ws.find(f"project-current-{second.id}"))

    def test_duplicate_archive_backup_delete_and_restore_from_home(self):
        ws = self.workspace()
        info = self.create(ws, "Lifecycle")
        self.analyse(ws)
        ws.app.navigate("home")
        ws.click(f"project-duplicate-{info.id}")
        titles = [p.title for p in ws.app.projects.projects()]
        self.assertIn("Lifecycle (copy)", titles)
        copy = next(p for p in ws.app.projects.projects() if p.title == "Lifecycle (copy)")

        ws.click(f"project-archive-{copy.id}")
        self.assertNotIn("Lifecycle (copy)", [p.title for p in ws.app.projects.projects()])
        ws.check("project-show-archived", True)
        self.assertTrue(ws.find(f"project-row-{copy.id}"))
        ws.click(f"project-archive-{copy.id}")      # back from the archive
        self.assertIn("Lifecycle (copy)", [p.title for p in ws.app.projects.projects()])

        ws.click(f"project-backup-{info.id}")
        backup = ws.saved[-1]
        self.assertEqual(backup.suffix, ".sra")
        with zipfile.ZipFile(backup) as archive:
            self.assertIn("manifest.json", archive.namelist())

        ws.click(f"project-delete-{info.id}")
        self.assertIsNotNone(ws.page.dialog, "deleting asks first")
        ws.click("project-delete-confirm")
        self.assertFalse(ws.app.projects.active)
        self.assertNotIn("Lifecycle", [p.title for p in ws.app.projects.projects()])
        self.assertTrue(ws.find("project-deleted"))
        ws.click("project-undelete-0")
        self.assertIn("Lifecycle", [p.title for p in ws.app.projects.projects()])

        # Restoring the backup never overwrites the project that exists.
        self.assertTrue(ws.run(ws.app.hub.restore_files(
            [SimpleNamespace(path=str(backup), name=backup.name)])))
        titles = [p.title for p in ws.app.projects.projects()]
        self.assertIn("Lifecycle", titles)
        self.assertIn("Lifecycle (restored)", titles)
        ws.click("project-open-restored")
        self.assertEqual(ws.app.projects.info().title, "Lifecycle (restored)")
        self.assertEqual(len(ws.app.session.results), 1)

    def test_a_backup_from_the_browser_arrives_as_bytes(self):
        ws = self.workspace()
        info = self.create(ws, "Browser backup")
        ws.app.navigate("home")
        ws.click(f"project-backup-{info.id}")
        data = ws.saved[-1].read_bytes()
        ws.click(f"project-delete-{info.id}")
        ws.click("project-delete-confirm")
        self.assertTrue(ws.run(ws.app.hub.restore_files(
            [SimpleNamespace(path=None, name="Browser_backup.sra", bytes=data)])))
        self.assertIn("Browser backup", [p.title for p in ws.app.projects.projects()])

    def test_a_damaged_backup_is_refused_with_a_message(self):
        ws = self.workspace()
        broken = self.base / "broken.sra"
        broken.write_bytes(b"not a zip")
        self.assertFalse(ws.run(ws.app.hub.restore_files(
            [SimpleNamespace(path=str(broken), name=broken.name)])))
        self.assertTrue(ws.has_text("could not be restored"))
        self.assertEqual(ws.app.projects.projects(), [])

    def test_projects_that_cannot_be_stored_leave_the_workspace_usable(self):
        from workspace_shell import ClassicBridge

        blocked = self.base / "blocked"
        blocked.write_text("a file, not a folder", encoding="utf-8")
        ws = self.workspace(bridge=ClassicBridge(survey_root=self.base / "surveys",
                                                 project_root=blocked))
        ws.app.navigate("home")
        self.assertTrue(ws.find("project-unavailable"))
        self.analyse(ws)
        self.assertEqual(len(ws.app.session.results), 1)

    def test_the_hub_is_translated(self):
        for language, heading in (("lv", "Pētījumu projekti"), ("ru", "Исследовательские проекты")):
            with self.subTest(language=language):
                ws = self.workspace(language=language)
                ws.app.navigate("home")
                self.assertTrue(ws.has_text(heading))
                ws.close()


class ReviewScenarioTests(unittest.TestCase):
    def test_the_screenshot_scenarios_for_projects_build(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from workspace_scenarios import apply

        for name, route in (("projects", "home"), ("results-stale", "results")):
            with self.subTest(scenario=name):
                ws = Workspace()
                self.addCleanup(ws.close)
                with mock.patch("workspace_shell.WorkspaceApp._remember_file"):
                    ws.run(apply(ws.app, name))
                self.assertEqual(ws.app.route, route)
                self.assertEqual(ws.app.projects.stale_count(), 1)
                self.assertEqual(len(ws.app.projects.projects()), 3, "the archived one is hidden")


class RunningAnalysisTests(ProjectWorkspaceCase):
    def test_a_result_finished_after_switching_projects_is_not_filed_in_the_new_one(self):
        ws = self.workspace()
        self.create(ws, "Started here")
        self.assertTrue(ws.run(ws.app.load_path(str(self.data))))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        other = ws.app.projects.store.create("Opened meanwhile")
        import workspace_analyze

        real = workspace_analyze.run_method

        def slow_switch(*args):
            run = real(*args)
            ws.app.projects.open(other.id)          # the researcher switched meanwhile
            return run

        with mock.patch.object(workspace_analyze, "run_method", slow_switch):
            entry = ws.run(ws.app.pages["analyze"]._execute("groups", GROUPS, {},
                                                            {"independent": True}))
        self.assertIsNone(entry)
        self.assertEqual(ws.app.session.results, [])
        self.assertEqual(ws.app.projects.project.runs(), [])
        message, tone = ws.app.pages["analyze"].message
        self.assertEqual(tone, "warning")
        self.assertIn("was not kept", message)


class StaleResultWorkspaceTests(ProjectWorkspaceCase):
    def change_data(self, ws):
        changed = pd.read_csv(self.data)
        changed.loc[0, "stress_q1"] = 1
        changed.to_csv(self.data, index=False)
        self.assertTrue(ws.run(ws.app.load_path(str(self.data))))

    def test_changed_data_marks_results_and_holds_the_report_until_decided(self):
        ws = self.workspace()
        self.create(ws, "Stale data")
        entry = self.analyse(ws)
        ws.click("result-add-report")
        self.change_data(ws)
        self.assertIn("data changed after this result", entry.stale_reasons)
        self.assertTrue(ws.has_text("Project: Stale data"))
        ws.app.navigate("results")
        ws.app.session.selected_result = entry.id
        ws.app.render()
        self.assertTrue(ws.find("result-stale"))
        self.assertTrue(ws.find(f"result-stale-{entry.id}"))
        self.assertTrue(ws.has_text("the data changed after this result was calculated"))

        ws.app.navigate("reports")
        self.assertTrue(ws.find("reports-stale"))
        self.assertTrue(ws.find("reports-export").disabled)
        ws.check("reports-include-stale", True)
        self.assertFalse(ws.find("reports-export").disabled)
        ws.click("reports-export")
        text = ws.saved[-1].read_text(encoding="utf-8")
        self.assertIn("Needs review: calculated before these changes: data changed", text)
        self.assertIn(entry.run.report.strip(), text)

    def test_recalculating_opens_the_analysis_and_asks_for_the_checks_again(self):
        ws = self.workspace()
        self.create(ws, "Recalculate")
        entry = self.analyse(ws)
        self.change_data(ws)
        ws.app.navigate("results")
        ws.app.session.selected_result = entry.id
        ws.app.render()
        ws.click("result-recalculate")
        analyze = ws.app.pages["analyze"]
        self.assertEqual(ws.app.route, "analyze")
        self.assertEqual((analyze.mode, analyze.method), ("all", "groups"))
        self.assertEqual(analyze.form_roles, GROUPS)
        self.assertEqual(analyze.form_confirms, {}, "confirmations are given again")
        self.assertTrue(ws.find("analyze-message"))
        analyze.form_confirms = {"independent": True}
        fresh = ws.run(analyze._run_form())
        self.assertIsNone(fresh)            # _run_form returns nothing; the result is added
        newest = ws.app.session.results[-1]
        self.assertEqual(newest.stale_reasons, ())
        self.assertNotEqual(newest.run.report, entry.run.report)
        self.assertEqual(len(ws.app.projects.project.runs()), 2, "the earlier result is kept")

    def test_a_result_that_cannot_be_reproduced_is_not_exported_as_word(self):
        ws = self.workspace()
        info = self.create(ws, "Missing copy")
        entry = self.analyse(ws)
        record = ws.app.projects.project.run(entry.record_id)
        stored = ws.app.projects.project.path / ws.app.projects.project.dataset(
            record.dataset_id).stored_path
        ws.close()
        stored.write_text("participant_id,group\n1,A\n", encoding="utf-8")   # damaged copy

        again = self.workspace()
        again.app.navigate("home")
        again.click(f"project-open-{info.id}")
        restored = again.app.session.results[0]
        self.assertIsNone(restored.run.result)
        again.app.navigate("results")
        before = len(again.saved)
        again.click("export-docx")
        self.assertEqual(len(again.saved), before, "no Word file from an unverified result")
        self.assertTrue(again.has_text("could not be calculated again"))
        again.click("export-txt")                  # the saved text stays available
        self.assertEqual(again.saved[-1].suffix, ".txt")


if __name__ == "__main__":
    unittest.main()
