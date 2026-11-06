"""Local-first research projects (Stage 34, issue #24) — storage layer."""

from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import time
import unittest
from unittest import mock
import zipfile

os.environ.setdefault("MPLBACKEND", "Agg")

import pandas as pd  # noqa: E402

import analysis_runs as runs  # noqa: E402
import project_store as ps  # noqa: E402
from project_store import ProjectError, ProjectFormatError, ProjectLocked, ProjectStore  # noqa: E402
from survey_storage import create_survey, responses_dataframe, submit_response  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SURVEY_QUESTIONS = [
    {"key": "group", "kind": "single_choice", "prompt": "Synthetic group", "required": True,
     "options": ["A", "B"]},
    {"key": "q1", "kind": "likert5", "prompt": "Synthetic statement", "required": True,
     "options": []},
]


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.store = ProjectStore(self.base / "projects")
        self.surveys = self.base / "surveys"

    def restart(self) -> ProjectStore:
        """A new store on the same folder, as after an application restart."""
        return ProjectStore(self.base / "projects")

    def groups_run(self, project, dataset):
        frame = project.load_frame(dataset.id)
        run = runs.run_groups(frame, "group", "stress_q1", "mannwhitney", "ordinal", True, False)
        project.save_levels(dataset.id, {"stress_q1": ("ordinal", "analyze"),
                                         "group": ("nominal", "analyze")})
        return project.record_run(
            run, method="groups", dataset_id=dataset.id,
            roles={"group": "group", "outcome": "stress_q1"},
            options={"method": "mannwhitney"}, confirms={"independent": True},
            confirmations=["I confirm that the two groups contain independent observations"],
            levels={"stress_q1": "ordinal", "group": "nominal"})


class ProjectLifecycleTests(StoreCase):
    def test_two_projects_survive_restart_and_switching_without_mixing(self):
        a = self.store.create("Thesis A: stress", research_area="psychology")
        b = self.store.create("Study B: sleep", research_area="education")
        with self.store.open(a.id) as project:
            data_a = project.import_dataset(EXAMPLES / "sample_scale.csv")
            project.add_question("Do the groups differ in stress?")
            self.groups_run(project, data_a)
        with self.store.open(b.id) as project:
            data_b = project.import_dataset(EXAMPLES / "sample_paired.csv")
            project.add_question("Does sleep improve after the programme?", kind="hypothesis")

        store = self.restart()
        self.assertEqual({i.title for i in store.list()}, {"Thesis A: stress", "Study B: sleep"})
        with store.open(a.id) as project:
            self.assertEqual([d.name for d in project.datasets()], ["sample_scale"])
            self.assertEqual(len(project.runs()), 1)
            self.assertEqual(project.questions()[0]["text"], "Do the groups differ in stress?")
            self.assertEqual(project.active_dataset().id, data_a.id)
            frame = project.load_frame(data_a.id)
            self.assertIn("stress_q1", frame.columns)
        with store.open(b.id) as project:
            self.assertEqual([d.name for d in project.datasets()], ["sample_paired"])
            self.assertEqual(project.runs(), [])
            self.assertEqual(project.questions()[0]["kind"], "hypothesis")
            with self.assertRaises(ProjectError):
                project.dataset(data_a.id)  # A's data is not visible in B
            self.assertEqual(project.active_dataset().id, data_b.id)
        info = store.info(a.id)
        self.assertEqual(info.counts, {"datasets": 1, "runs": 1, "questionnaires": 0, "questions": 1})

    def test_a_blank_project_needs_only_a_title(self):
        info = self.store.create("Pilot")
        self.assertEqual(info.title, "Pilot")
        self.assertEqual(info.status, "active")
        with self.assertRaises(ProjectError):
            self.store.create("   ")
        with self.assertRaises(ProjectError):
            self.store.create("X", password="nope")
        with self.store.open(info.id) as project:
            project.update(title="Pilot study", design="cross-sectional")
            self.assertEqual(project.info().title, "Pilot study")
        self.assertEqual(self.store.list(query="pilot")[0].id, info.id)
        self.assertEqual(self.store.list(query="unrelated"), [])

    def test_duplicate_archive_delete_and_restore(self):
        info = self.store.create("Original")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv")
            self.groups_run(project, dataset)
        copy = self.store.duplicate(info.id)
        self.assertNotEqual(copy.id, info.id)
        self.assertEqual(copy.title, "Original (copy)")
        with self.store.open(copy.id) as project:
            self.assertEqual(len(project.runs()), 1)
            self.assertIsNotNone(project.figure(project.runs()[0]))
            project.add_question("Only in the copy")
        with self.store.open(info.id) as project:
            self.assertEqual(project.questions(), [])

        self.store.set_archived(info.id, True)
        self.assertEqual([i.id for i in self.store.list()], [copy.id])
        self.assertEqual(len(self.store.list(include_archived=True)), 2)
        self.store.set_archived(info.id, False)

        trashed = self.store.delete(copy.id)
        self.assertNotIn(copy.id, [i.id for i in self.store.list()])
        self.assertEqual(self.store.deleted(), [trashed])
        restored = self.store.restore_deleted(trashed)
        self.assertEqual(restored.id, copy.id)

    def test_open_projects_cannot_be_deleted_and_another_instance_is_refused(self):
        info = self.store.create("Busy")
        project = self.store.open(info.id)
        self.assertTrue((info.path / ps.LOCK_NAME).is_file())
        with self.assertRaises(ProjectLocked):
            self.store.delete(info.id)
        with self.assertRaises(ProjectLocked):
            self.store.set_archived(info.id, True)
        second = self.store.open(info.id)  # the same process may reopen it
        second.close()
        self.assertTrue((info.path / ps.LOCK_NAME).is_file())
        project.close()
        self.assertFalse((info.path / ps.LOCK_NAME).exists())

        # Another live process holds the lock: refused, but read-only works.
        (info.path / ps.LOCK_NAME).write_text(json.dumps(
            {"pid": os.getppid(), "host": ps.socket.gethostname(), "since": "x"}))
        with self.assertRaises(ProjectLocked):
            self.store.open(info.id)
        with self.store.open(info.id, read_only=True) as viewer:
            self.assertEqual(viewer.info().title, "Busy")
            with self.assertRaises(ProjectError):
                viewer.add_question("not allowed")

    def test_an_abandoned_lock_is_recovered_and_logged(self):
        info = self.store.create("Crashed")
        (info.path / ps.LOCK_NAME).write_text(json.dumps(
            {"pid": 2_147_000_000, "host": ps.socket.gethostname(), "since": "2026-11-06T08:00:00+00:00"}))
        with self.store.open(info.id) as project:
            self.assertIn("not closed properly", project.recovered)
            self.assertEqual(project.events(1)[0]["kind"], "recovered")

    def test_an_imported_table_keeps_its_source_file_and_run_texts(self):
        from data_loader import load_dataset

        source = self.base / "survey export.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", source)
        frame = load_dataset(source)
        info = self.store.create("Snapshot")
        with self.store.open(info.id) as project:
            record = project.import_table(frame, "survey export", source_path=source)
            self.assertEqual(record.origin, "copy")
            self.assertEqual(record.source_sha256, ps.sha256_file(source))
            self.assertEqual(project.find_by_source(source).id, record.id)
            self.assertIsNone(project.find_by_source(self.base / "other.csv"))
            pd.testing.assert_frame_equal(project.load_frame(record.id), frame, check_dtype=False)
            run = runs.run_descriptive(frame, "stress_q2", "ordinal")
            saved = project.record_run(run, method="descriptive", dataset_id=record.id,
                                       roles={"variable": "stress_q2"}, options={}, confirms={})
            self.assertEqual(saved.descriptives, run.descriptives)
            self.assertEqual(saved.guide, run.guide)

    def test_project_data_root_follows_the_questionnaire_storage(self):
        with mock.patch.dict(os.environ, {"SRA_DATA_DIR": str(self.base / "custom")}):
            self.assertEqual(ps.project_data_root(ROOT), self.base / "custom" / "projects")

    def test_packaged_data_never_lives_in_the_program_folder(self):
        """Stage 35 (#44): an installed or unpacked program folder never holds
        research data, so installing, updating or uninstalling the program
        cannot touch it. Questionnaires an earlier preview kept there are not
        used in place (legacy_data offers to copy them)."""
        import app_paths

        install = self.base / "Programs" / "Statistical Research Assistant"
        (install / "data" / "surveys").mkdir(parents=True)
        (install / "data" / "surveys" / "survey_old.sqlite3").write_bytes(b"kept")
        local, flet = self.base / "LocalAppData", self.base / "flet-data"
        environment = {"FLET_APP_STORAGE_DATA": str(flet), "LOCALAPPDATA": str(local)}
        with mock.patch.dict(os.environ, environment), \
                mock.patch("startup_diagnostics.is_packaged", return_value=True):
            os.environ.pop("SRA_DATA_DIR", None)
            from startup_diagnostics import survey_data_root

            with mock.patch.object(app_paths, "_windows", return_value=True):
                user = local / "StatisticalResearchAssistant"
                self.assertEqual(ps.project_data_root(install), user / "projects")
                self.assertEqual(survey_data_root(install), user / "surveys")
                self.assertEqual(app_paths.updates_root(install), user / "updates")
            with mock.patch.object(app_paths, "_windows", return_value=False):
                self.assertEqual(ps.project_data_root(install), flet / "projects")
                self.assertEqual(survey_data_root(install), flet / "surveys")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SRA_DATA_DIR", None)
            os.environ.pop("FLET_APP_STORAGE_DATA", None)
            self.assertEqual(ps.project_data_root(install), install / "data" / "projects")


class StoredTableTests(StoreCase):
    def test_stored_copies_read_back_as_exactly_the_same_table(self):
        """CSV text alone loses types ("01" → 1, "NA" → missing, 0.1 + 0.2 → 0.3);
        the stored column types keep the reopened table identical."""
        import numpy as np

        frame = pd.DataFrame({
            "id": ["001", "002", "003", "004"],
            "group": ["01", "02", "01", "02"],
            "score": [1.5, 0.1 + 0.2, np.nan, 1 / 3],
            "count": [1, 2, 3, 4],
            "nullable": pd.array([1, None, 3, 4], dtype="Int64"),
            "flag": [True, False, True, False],
            "text": ["a, b", "NA", None, 'x"y\nz'],
            "blank": ["", None, "q", ""],
            "when": pd.to_datetime(["2024-01-01", "2024-02-01 10:30", None, "2024-03-05"],
                                   format="ISO8601"),
            "level": pd.Categorical(["low", "high", "low", "high"],
                                    categories=["low", "mid", "high"], ordered=True),
            "decimal_comma_text": ["1,5", "2,5", "3,5", "4,5"],
            "extremes": [1e-300, -0.0, 12345678901234567.0, 2.5e10],
            "1": [1.25, 2.0, 3.0, 4.0],
        })
        info = self.store.create("Types")
        with self.store.open(info.id) as project:
            record = project.add_frame(frame, "types", origin="copy")
        with self.restart().open(info.id) as project:
            back = project.load_frame(record.id)
            version = project.load_version(record.id, record.sha256)
        pd.testing.assert_frame_equal(back, frame, check_exact=True)
        pd.testing.assert_frame_equal(version, frame, check_exact=True)
        self.assertEqual(ps.frame_sha256(back), ps.frame_sha256(frame))

    def test_original_files_without_stored_types_use_the_normal_importer(self):
        info = self.store.create("Original file")
        with self.store.open(info.id) as project:
            record = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            self.assertFalse(any(p.name.endswith(ps.TABLE_SCHEMA_SUFFIX)
                                 for p in (project.path / "datasets").iterdir()))
            from data_loader import load_dataset

            pd.testing.assert_frame_equal(project.load_frame(record.id),
                                          load_dataset(EXAMPLES / "sample_scale.csv"))


class StaleResultTests(StoreCase):
    def test_changed_source_data_marks_results_stale_without_deleting_them(self):
        original = self.base / "measurements.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", original)
        info = self.store.create("Linked data")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(original, mode="link")
            run = self.groups_run(project, dataset)
            project.set_report([run.id])
            self.assertFalse(project.run_status(run).stale)
            self.assertEqual(project.check_source(dataset.id).state, "unchanged")
            self.assertIn(run.report.strip().splitlines()[0], project.report_text())

            frame = pd.read_csv(original)
            frame.loc[0, "stress_q1"] = 5 if frame.loc[0, "stress_q1"] != 5 else 1
            frame.to_csv(original, index=False)
            self.assertEqual(project.check_source(dataset.id).state, "changed")
            status = project.run_status(project.run(run.id))
            self.assertTrue(status.stale)
            self.assertIn("data changed after this result", status.reasons)
            self.assertEqual(len(project.runs()), 1)  # kept, not silently removed
            with self.assertRaises(ProjectError):
                project.report_text()
            self.assertIn("STALE", project.report_text(allow_stale=True))
            self.assertIn("STALE", project.reproducibility_appendix())
            self.assertEqual(len(project.dataset_versions(dataset.id)), 2)

    def test_new_version_of_a_copied_dataset_or_a_changed_level_makes_results_stale(self):
        info = self.store.create("Copied data")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv")
            run = self.groups_run(project, dataset)
            project.save_levels(dataset.id, {"stress_q1": ("interval", "data")})
            status = project.run_status(run)
            self.assertTrue(status.stale)
            self.assertIn("measurement level of stress_q1 changed (ordinal → interval)", status.reasons)
            project.save_levels(dataset.id, {"stress_q1": ("ordinal", "data")})
            self.assertFalse(project.run_status(run).stale)

            changed = project.load_frame(dataset.id)
            changed.loc[0, "stress_q2"] = changed.loc[0, "stress_q2"] + 1
            project.replace_dataset(dataset.id, frame=changed)
            self.assertTrue(project.run_status(run).stale)
            # The first version stays on disk for provenance.
            first = project.dataset_versions(dataset.id)[0]["stored_path"]
            self.assertTrue((project.path / first).is_file())

    def test_saved_run_reproduces_the_same_report_from_the_project(self):
        from workspace_methods import METHODS, run_method
        from workspace_state import ResearchSession

        info = self.store.create("Reproducible")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv")
            session = ResearchSession()
            session.set_dataset(project.load_frame(dataset.id), dataset.name)
            session.confirm_level("stress_q1", "ordinal")
            session.confirm_level("group", "nominal")
            roles = {"outcome": "stress_q1", "group": "group"}
            options = {"method": "mannwhitney"}
            confirms = {c.key: True for c in METHODS["groups"].confirmations}
            run = run_method("groups", session, roles, options, confirms)
            project.save_levels(dataset.id, {k: (v.confirmed, v.confirmed_in)
                                             for k, v in session.variables.items() if v.confirmed})
            record = project.record_run(run, method="groups", dataset_id=dataset.id, roles=roles,
                                        options=options, confirms=confirms,
                                        levels={"stress_q1": "ordinal", "group": "nominal"})

        with self.restart().open(info.id) as project:  # later, after a restart
            saved = project.runs()[0]
            fresh = ResearchSession()
            fresh.set_dataset(project.load_frame(saved.dataset_id), "reloaded")
            for name, level in saved.levels.items():
                fresh.confirm_level(name, level)
            again = run_method(saved.method, fresh, saved.roles, saved.options, saved.confirms)
            self.assertEqual(ps.sha256_bytes(again.report.encode("utf-8")), saved.report_sha256)
            self.assertEqual(saved.report_sha256, record.report_sha256)
            self.assertIn("libraries", saved.provenance)
            self.assertIn("numpy", saved.provenance["libraries"])

    def test_missing_linked_file_can_be_relinked(self):
        original = self.base / "data.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", original)
        info = self.store.create("Moved file")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(original, mode="link")
            run = self.groups_run(project, dataset)
            moved = self.base / "moved" / "data.csv"
            moved.parent.mkdir()
            os.replace(original, moved)
            self.assertEqual(project.check_source(dataset.id).state, "missing")
            with self.assertRaises(ProjectError):
                project.load_frame(dataset.id)
            self.assertEqual(project.relink(dataset.id, moved).state, "unchanged")
            self.assertFalse(project.run_status(run).stale)
            other = self.base / "other.csv"
            shutil.copy(EXAMPLES / "sample_three_groups.csv", other)
            self.assertEqual(project.relink(dataset.id, other).state, "changed")
            self.assertTrue(project.run_status(run).stale)


class BackupTests(StoreCase):
    def make_project_with_questionnaire(self):
        survey = create_survey(self.surveys, "Synthetic pilot", "Fictional", SURVEY_QUESTIONS)
        submit_response(self.surveys, survey.survey_id, {"group": "A", "q1": "2"})
        info = self.store.create("Backed up")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv")
            self.groups_run(project, dataset)
            project.link_questionnaire(survey.survey_id, survey.title)
            responses = responses_dataframe(self.surveys, survey.survey_id)
            project.add_frame(responses, "Pilot responses", origin="survey", survey_id=survey.survey_id)
            project.add_question("What changes over time?")
        return info, survey

    def test_backup_restores_on_a_clean_machine_with_questionnaires(self):
        info, survey = self.make_project_with_questionnaire()
        package = self.store.export_package(info.id, self.base / "backup", survey_root=self.surveys)
        self.assertEqual(package.suffix, ".sra")
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["questionnaires"], [survey.survey_id])

        clean = self.base / "clean-pc"
        store = ProjectStore(clean / "projects")
        restored, warnings = store.import_package(package, survey_root=clean / "surveys")
        self.assertEqual(warnings, [])
        self.assertEqual(restored.id, info.id)
        with store.open(restored.id) as project:
            self.assertEqual(len(project.datasets()), 2)
            run = project.runs()[0]
            self.assertFalse(project.run_status(run).stale)
            self.assertTrue(project.figure(run).startswith(b"\x89PNG"))
            for dataset in project.datasets():
                self.assertEqual(project.check_source(dataset.id).state, "stored")
            self.assertEqual(project.questionnaires()[0]["survey_id"], survey.survey_id)
        answers = responses_dataframe(clean / "surveys", survey.survey_id)
        self.assertEqual(len(answers), 1)

    def test_restoring_twice_never_overwrites_a_project_or_newer_responses(self):
        info, survey = self.make_project_with_questionnaire()
        package = self.store.export_package(info.id, self.base / "backup.sra", survey_root=self.surveys)
        submit_response(self.surveys, survey.survey_id, {"group": "B", "q1": "4"})  # newer data
        before = (self.surveys / f"survey_{survey.survey_id}.sqlite3").read_bytes()
        restored, warnings = self.store.import_package(package, survey_root=self.surveys)
        self.assertNotEqual(restored.id, info.id)
        self.assertTrue(restored.title.endswith("(restored)"))
        self.assertEqual(len(warnings), 2)
        self.assertEqual((self.surveys / f"survey_{survey.survey_id}.sqlite3").read_bytes(), before)
        self.assertEqual(len(responses_dataframe(self.surveys, survey.survey_id)), 2)
        # An identical questionnaire is accepted silently.
        package2 = self.store.export_package(info.id, self.base / "backup2.sra", survey_root=self.surveys)
        _again, warnings = self.store.import_package(package2, survey_root=self.surveys)
        self.assertEqual(warnings, ["This project already exists; the backup was restored as a separate copy."])

    def test_damaged_or_unsafe_backups_are_rejected(self):
        info, _survey = self.make_project_with_questionnaire()
        package = self.store.export_package(info.id, self.base / "good.sra")
        with zipfile.ZipFile(package) as archive:
            contents = {i.filename: archive.read(i.filename) for i in archive.infolist()}
        manifest = json.loads(contents["manifest.json"])

        def build(name, files):
            path = self.base / name
            with zipfile.ZipFile(path, "w") as archive:
                for member, data in files.items():
                    archive.writestr(member, data)
            return path

        dataset_name = next(n for n in contents if n.startswith("project/datasets/"))
        cases = {
            "tampered.sra": {**contents, dataset_name: contents[dataset_name] + b"1,2\n"},
            "traversal.sra": {**contents, "../evil.txt": b"x"},
            "extra.sra": {**contents, "project/datasets/unlisted.csv": b"a\n"},
            "nomanifest.sra": {k: v for k, v in contents.items() if k != "manifest.json"},
            "newer.sra": {**contents, "manifest.json": json.dumps(manifest | {"format_version": 99})},
            "foreign.sra": {**contents, "manifest.json": json.dumps(manifest | {"format": "other"})},
        }
        for name, files in cases.items():
            with self.subTest(name), self.assertRaises(ProjectFormatError):
                self.store.import_package(build(name, files))
        (self.base / "notzip.sra").write_bytes(b"not a zip")
        with self.assertRaises(ProjectFormatError):
            self.store.import_package(self.base / "notzip.sra")
        link = zipfile.ZipInfo("project/datasets/link")
        link.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(self.base / "symlink.sra", "w") as archive:
            for member, data in contents.items():
                archive.writestr(member, data)
            archive.writestr(link, "/etc/passwd")
        with self.assertRaises(ProjectFormatError):
            self.store.import_package(self.base / "symlink.sra")
        self.assertEqual(len(self.store.list()), 1)  # nothing half-restored

    def test_existing_questionnaires_are_untouched_by_project_operations(self):
        survey = create_survey(self.surveys, "Already published", "Fictional", SURVEY_QUESTIONS)
        submit_response(self.surveys, survey.survey_id, {"group": "A", "q1": "3"})
        path = self.surveys / f"survey_{survey.survey_id}.sqlite3"
        before = path.read_bytes()
        info = self.store.create("Links only")
        with self.store.open(info.id) as project:
            project.link_questionnaire(survey.survey_id, survey.title)
        self.store.export_package(info.id, self.base / "b.sra", survey_root=self.surveys)
        self.store.duplicate(info.id)
        self.store.delete(info.id)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(responses_dataframe(self.surveys, survey.survey_id)), 1)


class MigrationTests(StoreCase):
    def test_newer_project_format_is_refused(self):
        info = self.store.create("Future")
        with closing(sqlite3.connect(info.path / ps.DB_NAME)) as db, db:
            db.execute("PRAGMA user_version = 99")
        with self.assertRaises(ProjectFormatError):
            self.store.open(info.id)
        self.assertFalse((info.path / ps.LOCK_NAME).exists())

    def test_an_older_version_never_writes_to_a_newer_project(self):
        """Found while preparing in-app updates (#39, #45): an older version
        opening a project saved by a newer one switched the database's
        journal mode before refusing it, so a downgrade changed a database
        it cannot read. Now nothing is written, and the project stays listed."""
        for journal in ("delete", "wal"):
            with self.subTest(journal=journal):
                info = self.store.create(f"From a newer version ({journal})")
                database = info.path / ps.DB_NAME
                with closing(sqlite3.connect(database)) as db:
                    db.execute(f"PRAGMA journal_mode={journal}")
                    db.execute(f"PRAGMA user_version = {ps.SCHEMA_VERSION + 1}")
                    db.commit()
                before = database.read_bytes()
                with self.assertRaises(ProjectFormatError) as refused:
                    self.store.open(info.id)
                self.assertIn("newer version", str(refused.exception))
                self.assertEqual(database.read_bytes(), before, "the database was not touched")
                self.assertFalse((info.path / ps.LOCK_NAME).exists())
                self.assertEqual(list((self.store.root / ps.BACKUPS).glob(f"{info.id}-*")), [])
                self.assertIn(info.id, [p.id for p in self.store.list()])

    def test_the_current_format_reopens_without_a_backup(self):
        """Updating the application without a format change copies nothing."""
        info = self.store.create("Same format")
        with self.store.open(info.id) as project:
            project.add_question("Unchanged by an update?")
        with self.restart().open(info.id) as project:
            self.assertEqual(project.questions()[0]["text"], "Unchanged by an update?")
        self.assertFalse((self.store.root / ps.BACKUPS).exists()
                         and any((self.store.root / ps.BACKUPS).iterdir()))

    def test_migration_backs_up_the_old_database_and_keeps_data(self):
        info = self.store.create("Old format")
        with self.store.open(info.id) as project:
            project.add_question("Kept across versions?")

        current, following = ps.SCHEMA_VERSION, ps.SCHEMA_VERSION + 1

        def to_next(db):
            db.execute("ALTER TABLE project ADD COLUMN supervisor_note TEXT NOT NULL DEFAULT ''")

        with mock.patch.object(ps, "SCHEMA_VERSION", following), \
                mock.patch.dict(ps.MIGRATIONS, {following: to_next}):
            with self.store.open(info.id) as project:
                self.assertEqual(project.questions()[0]["text"], "Kept across versions?")
            with closing(sqlite3.connect(info.path / ps.DB_NAME)) as db, db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], following)
        backups = list((self.store.root / ps.BACKUPS).glob(f"{info.id}-v{current}-*.sqlite3"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], current)

    def test_a_format_1_project_is_migrated_to_format_2_with_everything_off(self):
        """A real migration: a project written by the format-1 code opens in
        this version, keeps its data and gains AI permissions that are all off."""
        info = self.store.create("Format one")
        with self.store.open(info.id) as project:
            project.add_question("Does sleep relate to stress?")
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
        database = info.path / ps.DB_NAME
        with closing(sqlite3.connect(database)) as db, db:   # back to what format 1 wrote
            db.execute("DROP TABLE ai_permissions")
            db.execute("DROP TABLE plan_versions")
            db.execute("ALTER TABLE project DROP COLUMN data_anonymous")
            db.execute("PRAGMA user_version = 1")
        with self.restart().open(info.id) as project:
            self.assertEqual(project.questions()[0]["text"], "Does sleep relate to stress?")
            self.assertEqual(project.dataset(dataset.id).sha256, dataset.sha256)
            self.assertEqual(project.ai_permissions(), {})
            self.assertFalse(project.data_anonymous)
            self.assertIsNone(project.plan())
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], ps.SCHEMA_VERSION)
        self.assertEqual(len(list((self.store.root / ps.BACKUPS).glob(f"{info.id}-v1-*.sqlite3"))), 1)

    def test_a_format_2_project_gains_an_empty_plan_and_keeps_everything(self):
        """Projects of the Stage 34 builds (format 2) open in format 3 (#40)."""
        info = self.store.create("Format two")
        with self.store.open(info.id) as project:
            project.add_question("Kept?")
        database = info.path / ps.DB_NAME
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TABLE plan_versions")
            db.execute("PRAGMA user_version = 2")
        with self.restart().open(info.id) as project:
            self.assertEqual(project.questions()[0]["text"], "Kept?")
            self.assertEqual(project.plan_history(), [])
            self.assertEqual(project.save_plan({"objectives": "Fictional aims"}), 1)
        self.assertEqual(len(list((self.store.root / ps.BACKUPS).glob(f"{info.id}-v2-*.sqlite3"))), 1)

    def test_a_failed_migration_leaves_the_old_format_untouched(self):
        info = self.store.create("Interrupted")
        database = info.path / ps.DB_NAME
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("DROP TABLE plan_versions")
            db.execute("DROP TABLE ai_permissions")
            db.execute("ALTER TABLE project DROP COLUMN data_anonymous")
            db.execute("PRAGMA user_version = 1")

        def broken(db):
            db.execute("CREATE TABLE ai_permissions (source TEXT PRIMARY KEY, allowed INTEGER,"
                       " changed_at TEXT)")
            raise sqlite3.OperationalError("disk I/O error (simulated)")

        with mock.patch.dict(ps.MIGRATIONS, {2: broken}):
            with self.assertRaises(sqlite3.OperationalError):
                self.store.open(info.id)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("ai_permissions", tables, "the half-done change was rolled back")
        with self.store.open(info.id) as project:          # and opens normally afterwards
            self.assertEqual(project.ai_permissions(), {})


class ResearchPlanTests(StoreCase):
    """#40: a versioned, hypothesis-aware research plan (format 3)."""

    PLAN = {"objectives": "Fictional aims", "design": "Two independent groups",
            "hypotheses": [{"text": "Group B reports more stress", "h0": "No difference",
                            "direction": "greater", "priority": "primary", "outcome": "stress_q1",
                            "predictors": "group", "method": "Mann-Whitney U", "alpha": 0.05}]}

    def test_every_save_is_a_new_version_and_nothing_is_overwritten(self):
        info = self.store.create("Planned study")
        with self.store.open(info.id) as project:
            first = project.save_plan(self.PLAN)
            self.assertEqual(project.save_plan(self.PLAN), first, "an unchanged plan adds no version")
            plan = project.plan()["plan"]
            plan["design"] = "Two independent groups, balanced"
            second = project.save_plan(plan, note="balanced design")
            history = project.plan_history()
        self.assertEqual([v["version"] for v in history], [second, first])
        self.assertEqual(history[1]["plan"]["design"], "Two independent groups")
        self.assertEqual(history[0]["note"], "balanced design")
        self.assertEqual(history[0]["plan"]["hypotheses"][0]["id"],
                         history[1]["plan"]["hypotheses"][0]["id"], "a hypothesis keeps its id")

    def test_hypotheses_added_after_results_are_not_confirmatory(self):
        info = self.store.create("Planned study")
        with self.store.open(info.id) as project:
            project.save_plan(self.PLAN)
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            self.groups_run(project, dataset)
            plan = project.plan()["plan"]
            plan["hypotheses"].append({"text": "Stress relates to age", "priority": "secondary",
                                       "outcome": "stress_q2"})
            plan["hypotheses"].append({"text": "Look at subscales", "priority": "exploratory"})
            project.save_plan(plan)
            status = project.hypothesis_status()
            current = project.plan()["plan"]["hypotheses"]
        standing = {h["text"]: status[h["id"]]["standing"] for h in current}
        self.assertEqual(standing, {"Group B reports more stress": "confirmatory",
                                    "Stress relates to age": "added_after_results",
                                    "Look at subscales": "exploratory"})
        self.assertEqual(status[current[1]["id"]]["runs_before"], 1)

    def test_invalid_plans_are_refused_in_words(self):
        info = self.store.create("Planned study")
        with self.store.open(info.id) as project:
            for bad in ({"hypotheses": [{"text": "x", "direction": "sideways"}]},
                        {"hypotheses": [{"text": "x", "priority": "maybe"}]},
                        {"hypotheses": [{"text": "x", "alpha": 0.5}]},
                        {"hypotheses": [{"text": "x", "alpha": "five"}]},
                        {"hypotheses": [{"text": "x", "id": "../../etc"}]}):
                with self.subTest(plan=bad), self.assertRaises(ProjectError):
                    project.save_plan(bad)
            self.assertEqual(project.plan_history(), [])
            # Empty hypotheses are dropped, unknown fields ignored.
            project.save_plan({"objectives": " Aims ", "colour": "red",
                               "hypotheses": [{"text": "  "}]})
            self.assertEqual(project.plan()["plan"], {**{f: "" for f in ps.PLAN_TEXT_FIELDS},
                                                      "objectives": "Aims", "hypotheses": []})

    def test_the_plan_travels_in_a_project_backup(self):
        info = self.store.create("Planned study")
        with self.store.open(info.id) as project:
            project.save_plan(self.PLAN)
        self.store.export_package(info.id, self.base / "plan.sra")
        restored, _ = self.restart().import_package(self.base / "plan.sra")
        with self.restart().open(restored.id) as project:
            self.assertEqual(project.plan()["plan"]["hypotheses"][0]["text"],
                             "Group B reports more stress")


class LargeDatasetTests(StoreCase):
    def test_large_dataset_round_trip(self):
        frame = pd.DataFrame({f"item_{i}": (pd.Series(range(120_000)) * (i + 1)) % 5 + 1
                              for i in range(12)})
        path = self.base / "large.csv"
        frame.to_csv(path, index=False)
        info = self.store.create("Large")
        started = time.monotonic()
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(path)
            self.assertEqual((dataset.rows, dataset.columns), (120_000, 12))
            loaded = project.load_frame(dataset.id)
            self.assertEqual(loaded.shape, (120_000, 12))
            self.assertEqual(project.check_source(dataset.id).state, "stored")
        self.assertLess(time.monotonic() - started, 60)


if __name__ == "__main__":
    unittest.main()
