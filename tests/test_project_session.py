"""The workspace session kept in a research project (Stage 34, issue #24).

Synthetic data only. Every change is saved as it happens; reopening a project
(also after a restart) restores the dataset, confirmed levels, results and
report, and a background check recalculates each saved result on the exact
dataset version it used.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from data_loader import load_dataset  # noqa: E402
from project_session import ProjectBinding  # noqa: E402
from project_store import ProjectError, ProjectStore  # noqa: E402
from survey_storage import create_survey, responses_dataframe, submit_response  # noqa: E402
from workspace_methods import METHODS, default_options, run_method  # noqa: E402
from workspace_state import ResearchSession  # noqa: E402

EXAMPLES = ROOT / "examples"
GROUPS = {"outcome": "stress_q1", "group": "group"}


def analyse(session, key, roles, confirms, options=None):
    """What the Analyze page does: run, then add the result with its provenance."""
    options = {**default_options(METHODS[key]), **(options or {})}
    run = run_method(key, session, roles, options, confirms)
    confirmed = [c.label for c in METHODS[key].confirmations if confirms.get(c.key)]
    return session.add_result(run, confirmed, method=key, roles=dict(roles),
                              options=options, confirms=dict(confirms))


def load(session, path: Path, *, origin="file"):
    session.set_dataset(load_dataset(path), path.name,
                        path=str(path) if origin == "file" else None, origin=origin)


class BindingCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data = self.base / "measurements.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", self.data)

    def binding(self):
        """A fresh session and binding on the same folder (as after a restart)."""
        binding = ProjectBinding(ResearchSession(), self.base / "projects")
        self.addCleanup(binding.close, clear=False)
        return binding

    def prepare(self, session):
        load(session, self.data)
        session.confirm_level("stress_q1", "ordinal")
        session.confirm_level("group", "nominal")


class SavingAndRestoringTests(BindingCase):
    def test_work_is_saved_as_it_happens_and_comes_back_after_a_restart(self):
        first = self.binding()
        first.create("Stress study")
        self.prepare(first.session)
        entry = analyse(first.session, "groups", GROUPS, {"independent": True})
        first.session.toggle_report(entry.id)
        report = entry.run.report
        project_id = first.project.id
        first.close(clear=False)              # the application quits; no save step

        second = self.binding()
        second.open(project_id)
        session = second.session
        self.assertEqual(session.source_name, "measurements.csv")
        self.assertEqual(session.level("stress_q1"), "ordinal")
        self.assertEqual(session.level("group"), "nominal")
        self.assertEqual(len(session.results), 1)
        restored = session.results[0]
        self.assertTrue(restored.restored)
        self.assertEqual(restored.run.report, report)
        self.assertEqual([e.id for e in session.report_entries()], [restored.id])
        self.assertIsNone(restored.run.result)
        self.assertEqual(restored.stale_reasons, ())
        # The background check recalculates on the stored table, in a worker
        # thread (the project database is never touched there).
        self.assertEqual(asyncio.run(second.verify_restored()), 1)
        self.assertIsNotNone(restored.run.result)
        self.assertEqual(restored.run.report, report)
        pd.testing.assert_frame_equal(session.df, load_dataset(self.data))

    def test_switching_projects_never_mixes_datasets_or_results(self):
        binding = self.binding()
        first = binding.create("Two groups")
        self.prepare(binding.session)
        analyse(binding.session, "groups", GROUPS, {"independent": True})
        second = binding.create("Three groups")
        self.assertFalse(binding.session.has_data, "a new project starts empty")
        self.assertEqual(binding.session.results, [])
        load(binding.session, EXAMPLES / "sample_three_groups.csv")
        binding.session.confirm_level("score", "scale")
        binding.session.confirm_level("group", "nominal")
        analyse(binding.session, "omnibus", {"outcome": "score", "group": "group"},
                {"independent": True, "assumptions": True})
        binding.open(first.id)
        self.assertEqual(binding.session.source_name, "measurements.csv")
        self.assertEqual([e.method for e in binding.session.results], ["groups"])
        binding.open(second.id)
        self.assertEqual(binding.session.source_name, "sample_three_groups.csv")
        self.assertEqual([e.method for e in binding.session.results], ["omnibus"])
        infos = {i.title: i.counts for i in binding.projects()}
        self.assertEqual(infos["Two groups"]["runs"], 1)
        self.assertEqual(infos["Three groups"]["runs"], 1)

    def test_work_started_without_a_project_moves_into_the_first_one_created(self):
        binding = self.binding()
        self.prepare(binding.session)
        before = analyse(binding.session, "groups", GROUPS, {"independent": True})
        load(binding.session, EXAMPLES / "sample_three_groups.csv")   # another table
        binding.session.confirm_level("score", "scale")
        binding.session.confirm_level("group", "nominal")
        current = analyse(binding.session, "omnibus", {"outcome": "score", "group": "group"},
                          {"independent": True, "assumptions": True})
        binding.create("Saved later")
        self.assertTrue(binding.session.has_data, "the work on screen is kept")
        runs = {r.id: r for r in binding.project.runs()}
        self.assertEqual(len(runs), 2)
        # Only the result of the table on screen is linked to that table; the
        # earlier one keeps its report text but claims no dataset it did not use.
        self.assertEqual(runs[current.record_id].dataset_id, binding.dataset_id)
        self.assertIsNone(runs[before.record_id].dataset_id)

    def test_a_project_that_cannot_be_stored_leaves_the_workspace_usable(self):
        blocked = self.base / "not-a-folder"
        blocked.write_text("a file where the project folder should be", encoding="utf-8")
        binding = ProjectBinding(ResearchSession(), blocked)
        self.assertIsNotNone(binding.unavailable)
        self.assertEqual(binding.projects(), [])
        with self.assertRaises(ProjectError):
            binding.create("Anything")
        self.prepare(binding.session)
        self.assertEqual(len(analyse(binding.session, "groups", GROUPS,
                                     {"independent": True}).run.report) > 0, True)


class StaleResultTests(BindingCase):
    def test_loading_the_changed_file_again_keeps_old_results_reproducible(self):
        binding = self.binding()
        binding.create("Changing data")
        self.prepare(binding.session)
        entry = analyse(binding.session, "groups", GROUPS, {"independent": True})
        report = entry.run.report
        changed = pd.read_csv(self.data)
        changed.loc[0, "stress_q1"] = 1
        changed.to_csv(self.data, index=False)
        load(binding.session, self.data)
        self.assertEqual(binding.message, ("project.new_version", "warning"))
        self.assertEqual(len(binding.project.datasets()), 1, "a new version, not a new dataset")
        self.assertIn("data changed after this result", entry.stale_reasons)
        # Levels survive the reload; the stale result still reproduces exactly
        # on the version it was calculated on.
        self.assertEqual(binding.session.level("stress_q1"), "ordinal")
        project_id = binding.project.id
        binding.close(clear=False)
        again = self.binding()
        again.open(project_id)
        restored = again.session.results[0]
        self.assertIn("data changed after this result", restored.stale_reasons)
        self.assertTrue(asyncio.run(again.ensure_result(restored)))
        self.assertEqual(restored.run.report, report)

    def test_changing_a_measurement_level_marks_only_results_that_used_it(self):
        binding = self.binding()
        binding.create("Levels")
        self.prepare(binding.session)
        binding.session.confirm_level("stress_q2", "ordinal")
        groups = analyse(binding.session, "groups", GROUPS, {"independent": True})
        other = analyse(binding.session, "descriptive", {"variable": "stress_q2"}, {})
        binding.session.confirm_level("stress_q1", "scale")
        self.assertTrue(any("stress_q1" in r for r in groups.stale_reasons))
        self.assertEqual(other.stale_reasons, ())

    def test_a_follow_up_keeps_the_data_version_of_the_result_it_extends(self):
        three = self.base / "three.csv"
        shutil.copy(EXAMPLES / "sample_three_groups.csv", three)
        binding = self.binding()
        binding.create("Follow-up")
        load(binding.session, three)
        binding.session.confirm_level("score", "scale")
        binding.session.confirm_level("group", "nominal")
        omnibus = analyse(binding.session, "omnibus", {"outcome": "score", "group": "group"},
                          {"independent": True, "assumptions": True})
        first_version = binding.project.dataset(binding.dataset_id).sha256
        changed = pd.read_csv(three)
        changed.loc[0, "score"] = 9
        changed.to_csv(three, index=False)
        load(binding.session, three)                       # a newer version
        from analysis_runs import run_posthoc

        omnibus.method = "posthoc"
        binding.session.replace_run(omnibus.id, run_posthoc(omnibus.run))
        record = binding.project.run(omnibus.record_id)
        self.assertEqual(record.method, "posthoc")
        self.assertEqual(record.dataset_sha256, first_version)
        self.assertEqual(len(binding.project.runs()), 1, "replaced, not duplicated")
        project_id, report = binding.project.id, omnibus.run.report
        binding.close(clear=False)
        again = self.binding()
        again.open(project_id)
        restored = again.session.results[0]
        self.assertTrue(asyncio.run(again.ensure_result(restored)))
        self.assertEqual(restored.run.report, report)

    def test_questionnaire_responses_are_one_dataset_with_versions(self):
        surveys = self.base / "surveys"
        survey = create_survey(surveys, "Synthetic wellbeing", "Fictional", [
            {"key": "group", "kind": "single_choice", "prompt": "Synthetic group",
             "required": True, "options": ["A", "B"]},
            {"key": "q1", "kind": "likert5", "prompt": "Synthetic statement",
             "required": True, "options": []},
        ])
        for group, value in (("A", 1), ("A", 2), ("A", 2), ("B", 4), ("B", 5), ("B", 4)):
            submit_response(surveys, survey.survey_id, {"group": group, "q1": str(value)})
        binding = self.binding()
        binding.create("Questionnaire")

        def analyse_responses():
            binding.session.set_dataset(responses_dataframe(surveys, survey.survey_id),
                                        survey.title, origin="survey",
                                        survey_id=survey.survey_id)
            binding.session.confirm_level("q1", "ordinal")
            binding.session.confirm_level("group", "nominal")
            return analyse(binding.session, "groups", {"outcome": "q1", "group": "group"},
                           {"independent": True})

        entry = analyse_responses()
        self.assertEqual([q["survey_id"] for q in binding.project.questionnaires()],
                         [survey.survey_id])
        submit_response(surveys, survey.survey_id, {"group": "B", "q1": "3"})
        analyse_responses()
        datasets = binding.project.datasets()
        self.assertEqual(len(datasets), 1)
        self.assertEqual(datasets[0].origin, "survey")
        self.assertEqual(len(binding.project.dataset_versions(datasets[0].id)), 2)
        self.assertIn("data changed after this result", entry.stale_reasons)
        # The questionnaire and its responses are untouched by the project.
        self.assertEqual(len(responses_dataframe(surveys, survey.survey_id)), 7)


class LifecycleTests(BindingCase):
    def test_delete_moves_to_the_trash_and_can_be_undone(self):
        binding = self.binding()
        info = binding.create("Disposable")
        self.prepare(binding.session)
        binding.delete(info.id)
        self.assertFalse(binding.active)
        self.assertFalse(binding.session.has_data)
        self.assertEqual(binding.projects(), [])
        deleted = binding.deleted_projects()
        self.assertEqual([d.title for d in deleted], ["Disposable"])
        restored = binding.restore_deleted(deleted[0].path)
        self.assertEqual(restored.title, "Disposable")
        self.assertEqual([p.title for p in binding.projects()], ["Disposable"])

    def test_backup_and_restore_through_the_binding(self):
        binding = self.binding()
        info = binding.create("Backed up")
        self.prepare(binding.session)
        analyse(binding.session, "groups", GROUPS, {"independent": True})
        backup = binding.export(info.id, self.base / "backup.sra", None)
        other = ProjectBinding(ResearchSession(), self.base / "elsewhere")
        restored, warnings = other.restore(backup, None)
        self.assertEqual(warnings, [])
        other.open(restored.id)
        self.addCleanup(other.close, clear=False)
        self.assertEqual(len(other.session.results), 1)
        self.assertEqual(asyncio.run(other.verify_restored()), 1)
        self.assertEqual(ProjectStore(self.base / "elsewhere").list()[0].title, "Backed up")


if __name__ == "__main__":
    unittest.main()
