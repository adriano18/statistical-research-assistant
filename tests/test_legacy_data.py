"""Stage 35 (#44): data of earlier versions is found, shown, copied and
checked, and never moved, changed or deleted. Synthetic data only."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import legacy_data as ld  # noqa: E402
import project_store as ps  # noqa: E402
from researcher_profile import ResearcherProfile, save_profile  # noqa: E402
from survey_storage import create_survey, list_surveys, responses_dataframe, submit_response  # noqa: E402

EXAMPLES = ROOT / "examples"
QUESTIONS = [
    {"key": "group", "kind": "single_choice", "prompt": "Synthetic group", "required": True,
     "options": ["A", "B"]},
    {"key": "q1", "kind": "likert5", "prompt": "Synthetic statement", "required": True,
     "options": []},
]


def snapshot(folder: Path) -> dict[str, str]:
    """Every file's content. SQLite's shared-memory index (-shm) and an empty
    write-ahead log are left out: any reader of a WAL database creates them;
    a log that holds changes is compared like any other file."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()
            and not p.name.endswith("-shm")
            and not (p.name.endswith("-wal") and p.stat().st_size == 0)}


class LegacyCase(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.base, True)
        self.old = self.base / "AppData" / "Roaming" / "Your Company" / \
            "Statistical Research Assistant" / "data"
        self.new = self.base / "AppData" / "Local" / "StatisticalResearchAssistant"
        store = ps.ProjectStore(self.old / "projects")
        self.first = store.create("Sleep and stress (fictional)")
        with store.open(self.first.id) as project:
            project.add_question("Does sleep relate to stress?")
            self.dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
        self.second = store.create("Second fictional study")
        survey = create_survey(self.old / "surveys", "Synthetic pilot", "Fictional", QUESTIONS)
        submit_response(self.old / "surveys", survey.survey_id, {"group": "A", "q1": "2"})
        self.survey = survey
        save_profile(self.old / ld.PROFILE, ResearcherProfile(display_name="Fictional Researcher"))
        ps._OPEN.clear()


class FindAndCopyTests(LegacyCase):
    def test_everything_is_shown_before_anything_is_copied(self):
        before = snapshot(self.old)
        source = ld.inspect(self.old, self.new, "preview")
        kinds = sorted((item.kind, item.title, item.state) for item in source.items)
        self.assertEqual(kinds, [
            ("profile", "", "new"),
            ("project", "Second fictional study", "new"),
            ("project", "Sleep and stress (fictional)", "new"),
            ("questionnaire", "Synthetic pilot", "new"),
        ])
        self.assertFalse(self.new.exists(), "looking copies nothing")
        self.assertEqual(snapshot(self.old), before)

    def test_copies_open_in_the_new_folder_and_the_originals_stay(self):
        before = snapshot(self.old)
        report = ld.copy_items(ld.inspect(self.old, self.new, "preview"), self.new)
        self.assertTrue(report.ok)
        self.assertEqual(len(report.copied), 4)
        self.assertEqual(snapshot(self.old), before, "originals are only read")

        store = ps.ProjectStore(self.new / "projects")
        self.assertEqual({p.title for p in store.list()},
                         {"Sleep and stress (fictional)", "Second fictional study"})
        with store.open(self.first.id) as project:
            self.assertEqual(project.questions()[0]["text"], "Does sleep relate to stress?")
            frame = project.load_frame(self.dataset.id)
            self.assertEqual(project.dataset(self.dataset.id).sha256, self.dataset.sha256)
        self.assertEqual(len(frame), len(__import__("pandas").read_csv(EXAMPLES / "sample_scale.csv")))
        self.assertEqual([s.title for s in list_surveys(self.new / "surveys")], ["Synthetic pilot"])
        self.assertEqual(len(responses_dataframe(self.new / "surveys", self.survey.survey_id)), 1)
        self.assertTrue((self.new / ld.PROFILE).is_file())
        record = json.loads((self.new / ld.RECORD).read_text(encoding="utf-8"))
        self.assertEqual(len(record["copied"]), 4)
        self.assertEqual(list(self.new.glob("projects/.migrating-*")), [])

    def test_a_second_look_offers_nothing_again(self):
        ld.copy_items(ld.inspect(self.old, self.new, "preview"), self.new)
        again = ld.inspect(self.old, self.new, "preview")
        self.assertEqual(again.pending, ())
        self.assertEqual({item.state for item in again.items}, {"copied"})

    def test_work_in_the_new_folder_is_never_replaced(self):
        ld.copy_items(ld.inspect(self.old, self.new, "preview"), self.new)
        with ps.ProjectStore(self.new / "projects").open(self.first.id) as project:
            project.add_question("Added after the move")
        ps._OPEN.clear()
        # The earlier version is used again and changes the original too.
        with ps.ProjectStore(self.old / "projects").open(self.first.id) as project:
            project.add_question("Added in the earlier version")
        ps._OPEN.clear()
        moved = snapshot(self.new / "projects" / self.first.id)
        source = ld.inspect(self.old, self.new, "preview")
        states = {item.title: item.state for item in source.items if item.kind == "project"}
        self.assertEqual(states["Sleep and stress (fictional)"], "changed")
        self.assertEqual(source.pending, ())
        ld.copy_items(source, self.new)
        self.assertEqual(snapshot(self.new / "projects" / self.first.id), moved)

    def test_other_content_under_the_same_identity_is_a_conflict(self):
        other = ps.ProjectStore(self.new / "projects")
        conflict = other.root / self.first.id
        conflict.mkdir(parents=True)
        with closing(sqlite3.connect(self.old / "projects" / self.first.id / ps.DB_NAME)) as db, \
                closing(sqlite3.connect(conflict / ps.DB_NAME)) as out:
            db.backup(out)
        with closing(sqlite3.connect(conflict / ps.DB_NAME)) as db, db:
            db.execute("UPDATE project SET title = 'Edited elsewhere'")
        kept = snapshot(conflict)
        source = ld.inspect(self.old, self.new, "preview")
        states = {item.source.name: item.state for item in source.items if item.kind == "project"}
        self.assertEqual(states[self.first.id], "conflict")
        report = ld.copy_items(source, self.new)
        self.assertIn(self.first.id, [item.source.name for item, why in report.skipped
                                      if why == "conflict"])
        self.assertEqual(snapshot(conflict), kept)

    def test_identical_content_already_there_is_not_copied_twice(self):
        ld.copy_items(ld.inspect(self.old, self.new, "preview"), self.new)
        (self.new / ld.RECORD).unlink()            # e.g. copied by hand earlier
        source = ld.inspect(self.old, self.new, "preview")
        self.assertEqual({item.state for item in source.items}, {"present"})

    def test_changes_still_in_the_write_ahead_log_are_copied(self):
        database = self.old / "projects" / self.second.id / ps.DB_NAME
        writer = sqlite3.connect(database)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("UPDATE project SET description = 'only in the WAL file'")
        writer.commit()
        self.assertTrue(Path(str(database) + "-wal").stat().st_size > 0)
        report = ld.copy_items(ld.inspect(self.old, self.new, "preview"), self.new)
        self.assertTrue(report.ok)
        with closing(sqlite3.connect(self.new / "projects" / self.second.id / ps.DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT description FROM project").fetchone()[0],
                             "only in the WAL file")

    def test_an_interrupted_copy_leaves_nothing_half_written(self):
        before = snapshot(self.old)
        source = ld.inspect(self.old, self.new, "preview")

        def broken(src, dst):
            Path(dst).write_bytes(b"partial")
            raise OSError(5, "Input/output error (simulated)")

        with mock.patch.object(ld, "_copy_database", side_effect=broken):
            report = ld.copy_items(source, self.new)
        self.assertFalse(report.ok)
        self.assertEqual({item.kind for item, _ in report.failed}, {"project", "questionnaire"})
        self.assertEqual([item.kind for item in report.copied], ["profile"])
        self.assertEqual(list((self.new / "projects").glob("*")) if (self.new / "projects").exists()
                         else [], [])
        self.assertEqual(list((self.new / "surveys").glob("*")) if (self.new / "surveys").exists()
                         else [], [])
        self.assertEqual(snapshot(self.old), before)
        # Trying again later copies the rest.
        again = ld.copy_items(ld.inspect(self.old, self.new, "preview"), self.new)
        self.assertTrue(again.ok)
        self.assertEqual(sorted(item.kind for item in again.copied),
                         ["project", "project", "questionnaire"])

    def test_a_full_disk_stops_copying_at_once(self):
        source = ld.inspect(self.old, self.new, "preview")
        with mock.patch.object(ld, "_copy_database", side_effect=OSError(28, "No space left")):
            report = ld.copy_items(source, self.new)
        self.assertEqual(report.stopped, "disk_full")
        self.assertEqual(len(report.failed), 1)


class DiscoveryTests(LegacyCase):
    def test_the_preview_folder_is_found_in_its_known_place(self):
        with mock.patch.dict(os.environ, {"APPDATA": str(self.base / "AppData" / "Roaming")}), \
                mock.patch("startup_diagnostics.is_packaged", return_value=False):
            found = ld.find(ROOT, self.new)
        self.assertEqual([s.folder for s in found], [self.old])
        self.assertEqual(found[0].count("project"), 2)

    def test_the_data_folder_itself_is_never_a_source(self):
        with mock.patch.dict(os.environ, {"APPDATA": str(self.base / "AppData" / "Roaming")}), \
                mock.patch("startup_diagnostics.is_packaged", return_value=False):
            self.assertEqual(ld.find(ROOT, self.old), [])

    def test_a_portable_program_folder_is_looked_at_only_when_packaged(self):
        program = self.base / "unpacked"
        create_survey(program / "data" / "surveys", "Portable questionnaire", "", QUESTIONS)
        with mock.patch.dict(os.environ, {"APPDATA": "", "FLET_APP_STORAGE_DATA": ""}):
            with mock.patch("startup_diagnostics.is_packaged", return_value=False):
                self.assertEqual(ld.find(program, self.new), [])
            with mock.patch("startup_diagnostics.is_packaged", return_value=True):
                found = ld.find(program, self.new)
        self.assertEqual([(s.kind, s.count("questionnaire")) for s in found], [("portable", 1)])

    def test_a_chosen_folder_is_searched_only_inside_itself(self):
        unpacked = self.base / "Downloads" / "StatisticalResearchAssistant-preview"
        app = unpacked / "data" / "flutter_assets" / "app"
        create_survey(app / "data" / "surveys", "Old portable questionnaire", "", QUESTIONS)
        (unpacked / "lib" / "site-packages" / "surveys").mkdir(parents=True)   # not data
        found = ld.find_in(unpacked, self.new)
        self.assertEqual([s.folder for s in found], [app / "data"])
        self.assertEqual(found[0].items[0].title, "Old portable questionnaire")
        self.assertEqual(ld.find_in(self.base / "Downloads" / "nothing-here", self.new), [])

    def test_not_now_is_remembered_and_a_damaged_record_is_survivable(self):
        ld.dismiss(self.old, self.new)
        self.assertTrue(ld.is_dismissed(self.old, self.new))
        (self.new / ld.RECORD).write_text("{not json", encoding="utf-8")
        self.assertFalse(ld.is_dismissed(self.old, self.new))
        self.assertEqual(len(ld.inspect(self.old, self.new).pending), 4)


if __name__ == "__main__":
    unittest.main()
