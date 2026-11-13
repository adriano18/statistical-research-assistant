"""Stage 37.0b: project format 6 — migration from every older format with a
backup, `.sra` backup and restore with protocol records, and the copy for an
older version (design §8.6, AC-11).

Format 6 stays: nothing here adds a format. Synthetic data only (examples/).
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import analysis_runs as runs  # noqa: E402
import project_store as ps  # noqa: E402
from project_store import ProjectStore  # noqa: E402
from test_stage37_ui import Case as UiCase, run_correlations, write_plan  # noqa: E402

EXAMPLES = ROOT / "examples"
PRINT = "b" * 64


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def objects(path: Path) -> dict[str, set[str]]:
    with closing(sqlite3.connect(path)) as db:
        found: dict[str, set[str]] = {}
        for kind, name in db.execute("SELECT type, name FROM sqlite_master"):
            found.setdefault(kind, set()).add(name)
        return found


def version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as db:
        return db.execute("PRAGMA user_version").fetchone()[0]


class Case(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.store = ProjectStore(self.base / "projects")

    def restart(self, root: str = "projects") -> ProjectStore:
        return ProjectStore(self.base / root)

    def project_with_records(self):
        """A format-6 project: a plan, a run that tests H1, three records."""
        info = self.store.create("Fictional records study")
        with self.store.open(info.id) as project:
            project.save_plan({"questions": [{"type": "compare", "text": "Do groups differ?"}],
                               "hypotheses": [{"text": "Group B reports more stress",
                                               "direction": "greater"}]})
            plan = project.plan()["plan"]
            hid = plan["hypotheses"][0]["id"]
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            frame = project.load_frame(dataset.id)
            run = runs.run_groups(frame, "group", "stress_q1", "mannwhitney", "ordinal", True,
                                  False)
            task = project.save_task(task_id=None, title="Stress by group", goal="compare",
                                     selection={"group": "group", "outcome": ["stress_q1"]},
                                     hypothesis_id=hid)
            record = project.record_run(
                run, method="groups", dataset_id=dataset.id,
                roles={"group": "group", "outcome": "stress_q1"}, options={},
                confirms={}, task_id=task.id,
                hypothesis={"id": hid, "plan_version": 1, "priority": "primary",
                            "direction": "greater", "alpha": 0.05})
            project.add_protocol_record("link", hypothesis_id=hid, task_id=task.id,
                                        detail={"from": None, "to": hid})
            ack = project.add_protocol_record(
                "acknowledgement", hypothesis_id=hid, task_id=task.id, run_id=record.id,
                check_key="H-DIR-TWOSIDED", fingerprint=PRINT, reason="Fictional: two-sided.")
            project.add_protocol_record("withdrawal", hypothesis_id=hid, supersedes=ack["id"],
                                        reason="Fictional: recorded for the wrong check.")
            records = project.protocol_records()
        return info, hid, record, records


class MigrationTests(Case):
    def legacy(self, found: int) -> tuple[Path, str]:
        """A project database as a build of format ``found`` left it."""
        info = self.store.create(f"Fictional format {found}")
        path = info.path / ps.DB_NAME
        path.unlink()
        for name in ("-wal", "-shm"):
            Path(str(path) + name).unlink(missing_ok=True)
        with closing(sqlite3.connect(path)) as db:
            for step in range(1, found + 1):
                ps.MIGRATIONS[step](db)
            stamp = ps.now()
            db.execute("INSERT INTO project (id, title, created_at, modified_at, last_opened_at)"
                       " VALUES (?, ?, ?, ?, ?)", (info.id, f"Fictional format {found}", stamp,
                                                   stamp, stamp))
            db.execute("INSERT INTO research_questions VALUES (?, 0, 'question', ?, ?, ?)",
                       ("q1", "Does sleep relate to stress?", stamp, stamp))
            db.execute(f"PRAGMA user_version = {found}")
            db.commit()
        return path, info.id

    def test_every_older_format_migrates_to_six_after_a_backup(self):
        for found in range(1, 6):
            with self.subTest(format=found):
                path, project_id = self.legacy(found)
                before = sha(path)
                with self.restart().open(project_id) as project:
                    self.assertEqual(project.questions()[0]["text"],
                                     "Does sleep relate to stress?")
                    self.assertEqual(project.protocol_records(), [])
                    project.add_protocol_record("link", hypothesis_id="0a1b2c3d4e5f",
                                                task_id="t1")
                self.assertEqual(version(path), 6)
                self.assertEqual(objects(path)["trigger"],
                                 {"protocol_records_no_update", "protocol_records_no_delete"})
                backups = list((self.store.root / ps.BACKUPS).glob(f"{project_id}-v{found}-*"))
                self.assertEqual(len(backups), 1, "one copy before the migration")
                self.assertEqual(version(backups[0]), found)
                self.assertTrue(path.exists() and before, "the copy is taken, the file stays")

    def test_a_failed_migration_leaves_the_old_format(self):
        path, project_id = self.legacy(5)
        with mock.patch.dict(ps.MIGRATIONS, {6: mock.Mock(side_effect=RuntimeError("crash"))}):
            with self.assertRaises(RuntimeError):
                self.restart().open(project_id)
        self.assertEqual(version(path), 5, "one transaction: nothing half changed")
        self.assertNotIn("protocol_records", objects(path).get("table", set()))
        with self.restart().open(project_id):
            pass
        self.assertEqual(version(path), 6)


class BackupTests(Case):
    def test_a_sra_backup_round_trip_keeps_every_record_and_its_guard(self):
        info, hid, record, records = self.project_with_records()
        package = self.store.export_package(info.id, self.base / "study.sra")
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["schema_version"], 6)
        other = self.restart("elsewhere")
        restored, warnings = other.import_package(package)
        self.assertEqual(warnings, [])
        with other.open(restored.id) as project:
            again = project.protocol_records()
            self.assertEqual(again, records, "every field of every record, in order")
            self.assertEqual(project.run(record.id).hypothesis["id"], hid, "the snapshot")
            self.assertEqual([r["run_id"] for r in again if r["kind"] == "acknowledgement"],
                             [record.id])
        with closing(sqlite3.connect(restored.path / ps.DB_NAME)) as db:
            for statement in ("UPDATE protocol_records SET reason = 'x'",
                              "DELETE FROM protocol_records"):
                with self.subTest(statement=statement), \
                        self.assertRaises(sqlite3.DatabaseError):
                    db.execute(statement)

    def test_a_backup_restored_beside_its_project_is_a_copy_with_the_records(self):
        info, hid, record, records = self.project_with_records()
        package = self.store.export_package(info.id, self.base / "study.sra")
        copy, warnings = self.restart().import_package(package)
        self.assertNotEqual(copy.id, info.id)
        self.assertTrue(warnings, "said in words")
        with self.restart().open(copy.id) as project:
            self.assertEqual([r["id"] for r in project.protocol_records()],
                             [r["id"] for r in records])
        with self.restart().open(info.id) as project:
            self.assertEqual(project.protocol_records(), records, "the original is unchanged")

    def test_a_backup_made_by_the_release_candidate_is_migrated_on_restore(self):
        info, hid, record, records = self.project_with_records()
        package = self.store.export_for_format(info.id, self.base / "rc.sra")[0]
        restored, _ = self.restart("elsewhere").import_package(package)
        path = restored.path / ps.DB_NAME
        self.assertEqual(version(path), 6)
        backups = list((self.base / "elsewhere" / ps.BACKUPS).glob("*-v5-*.sqlite3"))
        self.assertEqual(len(backups), 1, "the format-5 database is kept before the migration")


class OlderVersionCopyTests(Case):
    def test_the_copy_is_format_5_without_the_records_and_the_original_is_untouched(self):
        info, hid, record, records = self.project_with_records()
        original = info.path / ps.DB_NAME
        before = sha(original)
        package, left_out = self.store.export_for_format(info.id, self.base / "for-36x.sra")
        self.assertEqual(left_out, len(records))
        self.assertEqual(sha(original), before, "not one byte of the original is written")
        with closing(sqlite3.connect(original)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM protocol_records").fetchone()[0],
                             len(records))
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            database = archive.read(f"project/{ps.DB_NAME}")
        self.assertEqual(manifest["schema_version"], 5)
        self.assertEqual(manifest["for_older_version"],
                         {"format": 5, "protocol_records_left_out": len(records)})
        copy = self.base / "copy.sqlite3"
        copy.write_bytes(database)
        self.assertEqual(version(copy), 5)
        found = objects(copy)
        self.assertNotIn("protocol_records", found.get("table", set()))
        self.assertNotIn("trigger", found)
        self.assertNotIn(b"Fictional: two-sided.", database, "no page of the records is left")
        with closing(sqlite3.connect(copy)) as db:
            event = json.loads(db.execute("SELECT detail FROM events WHERE kind = "
                                          "'copied_for_format'").fetchone()[0])
        self.assertEqual(event, {"format": 5, "from_project": info.id,
                                 "protocol_records_left_out": len(records)})

    def test_a_format_5_build_opens_the_copy_and_it_comes_back_to_six(self):
        info, hid, record, records = self.project_with_records()
        package, _ = self.store.export_for_format(info.id, self.base / "for-36x.sra")
        with mock.patch.object(ps, "SCHEMA_VERSION", 5):   # what the release candidate reads
            rc = self.restart("release-candidate")
            restored, _ = rc.import_package(package)
            with rc.open(restored.id) as project:
                self.assertEqual(project.run(record.id).report, project.runs()[0].report)
                plan = project.plan()["plan"]
                self.assertEqual(plan["hypotheses"][0]["id"], hid)
                self.assertEqual(project.tasks()[0].hypothesis_id, hid)
            self.assertEqual(version(restored.path / ps.DB_NAME), 5, "opened as it is")
            self.assertFalse((self.base / "release-candidate" / ps.BACKUPS).exists(),
                             "no migration in the release candidate")
        # The copy comes back to this version: migrated after a backup, no records.
        with self.restart("release-candidate").open(restored.id) as project:
            self.assertEqual(project.protocol_records(), [])
            self.assertEqual(project.run(record.id).hypothesis["id"], hid)
        self.assertEqual(version(restored.path / ps.DB_NAME), 6)
        self.assertEqual(len(list((self.base / "release-candidate" / ps.BACKUPS)
                                  .glob("*-v5-*.sqlite3"))), 1)

    def test_only_format_5_is_offered(self):
        info, *_ = self.project_with_records()
        with self.assertRaises(ps.ProjectError):
            self.store.export_for_format(info.id, self.base / "x.sra", 4)


class CopyInTheInterfaceTests(UiCase):
    def test_the_project_page_warns_first_and_leaves_the_project_as_it_is(self):
        ws = self.workspace()
        hid = write_plan(ws)
        ws.app.navigate("project")
        ws.click("next-create-analysis")
        run_correlations(ws)
        project = ws.app.projects.project
        records = project.protocol_records()
        ws.app.navigate("project")
        self.assertEqual(ws.find("project-copy-older").content, ws.app.t("project.copy_older"))
        ws.click("project-copy-older")
        body = ws.find("project-copy-older-body").value
        self.assertEqual(body, ws.app.t("project.copy_older_body", count=len(records)))
        self.assertEqual(ws.saved, [], "the warning comes before the Save dialog")
        ws.click("project-copy-older-confirm")
        saved = ws.saved[-1]
        self.assertTrue(saved.name.endswith("_36x.sra") and saved.exists())
        with zipfile.ZipFile(saved) as archive:
            self.assertEqual(json.loads(archive.read("manifest.json"))["schema_version"], 5)
        self.assertEqual(project.protocol_records(), records, "the records stay here")
        self.assertEqual(version(project.path / ps.DB_NAME), 6)
        self.assertEqual(project.plan()["plan"]["hypotheses"][0]["id"], hid)
        events = [e["kind"] for e in project.events()]
        self.assertNotIn("copied_for_format", events, "nothing is written to this project")


if __name__ == "__main__":
    unittest.main()
