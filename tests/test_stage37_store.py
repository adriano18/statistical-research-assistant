"""Stage 37.0a: project format 6 — typed plans, protocol records, result snapshots.

Synthetic data only (examples/ and the Stage 36 fixtures).
"""

from __future__ import annotations

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import analysis_runs as runs  # noqa: E402
import project_store as ps  # noqa: E402
from project_store import (  # noqa: E402
    DesignationReasonNeeded, ProjectError, ProjectFormatError, ProjectStore,
)

EXAMPLES = ROOT / "examples"
PRINT = "a" * 64


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.store = ProjectStore(self.base / "projects")

    def restart(self) -> ProjectStore:
        return ProjectStore(self.base / "projects")

    def groups_run(self, project, dataset, **kwargs):
        frame = project.load_frame(dataset.id)
        run = runs.run_groups(frame, "group", "stress_q1", "mannwhitney", "ordinal", True, False)
        project.save_levels(dataset.id, {"stress_q1": ("ordinal", "analyze"),
                                         "group": ("nominal", "analyze")})
        return project.record_run(
            run, method="groups", dataset_id=dataset.id,
            roles={"group": "group", "outcome": "stress_q1"},
            options={"method": "mannwhitney"}, confirms={"independent": True},
            confirmations=["I confirm that the two groups contain independent observations"],
            levels={"stress_q1": "ordinal", "group": "nominal"}, **kwargs)

    def sha(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


QUESTION = {"id": "1a2b3c4d5e6f", "type": "relate",
            "text": "Is loneliness related to how students cope with stress?"}
TYPED = {"objectives": "Fictional aims", "questions": [QUESTION], "hypotheses": [
    {"text": "Loneliness is associated with coping", "h0": "No association",
     "direction": "less", "priority": "primary", "alpha": 0.05, "question_id": QUESTION["id"],
     "method_key": "batch_correlation", "method_options": {"method": "spearman", "adjust": "holm"},
     "roles": {"x": "UCLA", "y": ["AssertiveAction", "SocialJoining"]}, "family": "coping"}]}


class FormatSixTests(Case):
    def test_the_format_is_six_and_adds_only(self):
        self.assertEqual(ps.SCHEMA_VERSION, 6)
        info = self.store.create("Format six")
        with closing(sqlite3.connect(info.path / ps.DB_NAME)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            triggers = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertIn("protocol_records", tables)
        self.assertEqual(triggers, {"protocol_records_no_update", "protocol_records_no_delete"})

    def test_a_format_5_project_migrates_with_a_backup_and_keeps_everything(self):
        info = self.store.create("Format five")
        with self.store.open(info.id) as project:
            project.add_question("Does sleep relate to stress?")
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            run = self.groups_run(project, dataset)
            version = project.save_plan({"objectives": "Kept", "hypotheses": [
                {"text": "Group B reports more stress", "priority": "primary"}]})
        database = info.path / ps.DB_NAME
        with closing(sqlite3.connect(database)) as db, db:     # what a 36.8 build left
            db.execute("DROP TABLE protocol_records")
            db.execute("PRAGMA user_version = 5")
        with self.restart().open(info.id) as project:
            self.assertEqual(project.questions()[0]["text"], "Does sleep relate to stress?")
            self.assertEqual(project.run(run.id).report, run.report)
            self.assertEqual(project.plan()["version"], version)
            self.assertEqual(project.protocol_records(), [])
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
        backups = list((self.store.root / ps.BACKUPS).glob(f"{info.id}-v5-*.sqlite3"))
        self.assertEqual(len(backups), 1, "the format-5 database is kept before the migration")
        with closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)

    def test_a_format_5_reader_refuses_a_format_6_project_without_writing(self):
        """What the release candidate (format 5) does with a 37.0a project."""
        info = self.store.create("Newer")
        with self.store.open(info.id) as project:
            project.save_plan(TYPED)
            project.add_protocol_record("link", hypothesis_id=project.plan()["plan"]
                                        ["hypotheses"][0]["id"], task_id="t1")
        database = info.path / ps.DB_NAME
        before = self.sha(database)
        with mock.patch.object(ps, "SCHEMA_VERSION", 5):
            reader = self.restart()
            self.assertEqual([p.id for p in reader.list()], [info.id], "still listed")
            with self.assertRaises(ProjectFormatError) as caught:
                reader.open(info.id)
        self.assertIn("newer version (format 6)", str(caught.exception))
        self.assertIn("up to format 5", str(caught.exception))
        self.assertEqual(self.sha(database), before, "not one byte written")
        self.assertFalse((info.path / ps.LOCK_NAME).exists(), "no lock left behind")
        with self.restart().open(info.id) as project:          # and 37.0a still opens it
            self.assertEqual(len(project.protocol_records()), 1)


class TypedPlanTests(Case):
    def test_typed_questions_and_hypotheses_round_trip(self):
        info = self.store.create("Typed")
        with self.store.open(info.id) as project:
            project.save_plan(TYPED)
        with self.restart().open(info.id) as project:
            plan = project.plan()["plan"]
        self.assertEqual(plan["plan_format"], 2)
        self.assertEqual(plan["questions"], [QUESTION])
        hypothesis = plan["hypotheses"][0]
        for key in ("question_id", "method_key", "method_options", "roles", "family"):
            self.assertEqual(hypothesis[key], TYPED["hypotheses"][0][key], key)
        self.assertEqual(hypothesis["direction"], "less")

    def test_a_plan_without_typed_fields_stays_as_before(self):
        info = self.store.create("Plain")
        plain = {"objectives": "Aims", "hypotheses": [{"text": "H", "priority": "primary"}]}
        with self.store.open(info.id) as project:
            first = project.save_plan(plain)
            saved = project.plan()["plan"]
            self.assertNotIn("plan_format", saved)
            self.assertNotIn("questions", saved)
            self.assertFalse({"question_id", "method_key", "roles"} & set(saved["hypotheses"][0]))
            self.assertEqual(project.save_plan(saved), first, "unchanged: no new version")
            second = project.save_plan({**saved, "questions": [QUESTION]})
        self.assertGreater(second, first)

    def test_question_ids_are_given_and_every_reference_is_checked(self):
        info = self.store.create("Ids")
        with self.store.open(info.id) as project:
            project.save_plan({"questions": [{"type": "compare", "text": "Do groups differ?"},
                                             {"type": "", "text": ""}]})
            questions = project.plan()["plan"]["questions"]
        self.assertEqual(len(questions), 1, "an empty question is dropped")
        self.assertRegex(questions[0]["id"], r"^[0-9a-f]{12}$")

    def test_invalid_typed_fields_are_refused_in_words(self):
        info = self.store.create("Invalid")
        hypothesis = TYPED["hypotheses"][0]
        bad_plans = (
            {"questions": [{**QUESTION, "type": "sideways"}]},
            {"questions": [{**QUESTION, "id": "../etc"}]},
            {"questions": [QUESTION, QUESTION]},
            {"questions": [QUESTION], "hypotheses": [{**hypothesis, "question_id": "ffffffffffff"}]},
            {"questions": [QUESTION], "hypotheses": [{**hypothesis, "method_key": "magic"}]},
            {"questions": [QUESTION], "hypotheses": [{**hypothesis,
                                                      "method_options": {"method": "magic"}}]},
            {"questions": [QUESTION], "hypotheses": [{**hypothesis,
                                                      "method_options": {"colour": "red"}}]},
            {"questions": [QUESTION], "hypotheses": [{**hypothesis, "roles": {"group": "Sex"}}]},
            {"questions": [QUESTION], "hypotheses": [{**hypothesis, "roles": {"x": ["a"] * 101}}]},
        )
        with self.store.open(info.id) as project:
            for bad in bad_plans:
                with self.subTest(plan=bad), self.assertRaises(ProjectError):
                    project.save_plan(bad)
            self.assertEqual(project.plan_history(), [])


class DesignationTests(Case):
    def test_a_change_after_results_needs_a_reason_and_is_recorded(self):
        info = self.store.create("Designation")
        with self.store.open(info.id) as project:
            project.save_plan({"hypotheses": [{"text": "H1", "priority": "primary"}]})
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            self.groups_run(project, dataset)
            plan = project.plan()["plan"]
            hid = plan["hypotheses"][0]["id"]
            plan["hypotheses"][0]["priority"] = "secondary"
            with self.assertRaises(DesignationReasonNeeded) as caught:
                project.save_plan(plan)
            self.assertEqual(caught.exception.hypotheses, (hid,))
            self.assertEqual(len(project.plan_history()), 1, "nothing saved without the reason")
            version = project.save_plan(plan, reasons={hid: "Groups of 3, 47 and 5."})
            records = project.protocol_records(hypothesis_id=hid)
            events = [e["kind"] for e in project.events()]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual((record["kind"], record["plan_version"], record["reason"]),
                         ("designation", version, "Groups of 3, 47 and 5."))
        self.assertEqual(record["detail"], {"from": "primary", "to": "secondary"})
        self.assertEqual(record["results_in_project"], 1)
        self.assertIn("designation_changed", events)

    def test_a_change_before_any_result_needs_no_reason(self):
        info = self.store.create("Early")
        with self.store.open(info.id) as project:
            project.save_plan({"hypotheses": [{"text": "H1", "priority": "primary"}]})
            plan = project.plan()["plan"]
            plan["hypotheses"][0]["priority"] = "exploratory"
            project.save_plan(plan)
            self.assertEqual(project.protocol_records(), [])
            self.assertEqual(len(project.plan_history()), 2)


class ProtocolRecordTests(Case):
    def project(self):
        info = self.store.create("Records")
        project = self.store.open(info.id)
        self.addCleanup(project.close)
        project.save_plan(TYPED)
        return info, project, project.plan()["plan"]["hypotheses"][0]["id"]

    def test_records_keep_their_order_and_survive_a_restart(self):
        info, project, hid = self.project()
        link = project.add_protocol_record("link", hypothesis_id=hid, task_id="t1",
                                           detail={"from": None, "to": hid})
        ack = project.add_protocol_record("acknowledgement", hypothesis_id=hid, task_id="t1",
                                          check_key="H-DIR-TWOSIDED", fingerprint=PRINT,
                                          reason="The two-sided p is reported.")
        self.assertEqual((link["plan_version"], link["results_in_project"]), (1, 0))
        project.close()
        with self.restart().open(info.id) as again:
            stored = again.protocol_records(hypothesis_id=hid)
        self.assertEqual([r["id"] for r in stored], [link["id"], ack["id"]])
        self.assertEqual(stored[1]["check_key"], "H-DIR-TWOSIDED")
        self.assertEqual(stored[0]["detail"], {"from": None, "to": hid})

    def test_a_reason_is_required_where_a_decision_is_recorded(self):
        _, project, hid = self.project()
        for kind in ("acknowledgement", "deviation", "justification", "designation"):
            with self.subTest(kind=kind), self.assertRaises(ProjectError):
                project.add_protocol_record(kind, hypothesis_id=hid, check_key="H-ALPHA",
                                            fingerprint=PRINT, detail={"what": "method"},
                                            reason="   ")
        with self.assertRaises(ProjectError):
            project.add_protocol_record("deviation", hypothesis_id=hid, reason="Why",
                                        detail={"what": "colour"})
        with self.assertRaises(ProjectError):
            project.add_protocol_record("acknowledgement", hypothesis_id=hid, reason="Why",
                                        check_key="H-ALPHA", fingerprint="short")
        with self.assertRaises(ProjectError):
            project.add_protocol_record("rumour", hypothesis_id=hid, reason="Why")
        self.assertEqual(project.protocol_records(), [])

    def test_a_withdrawal_points_to_a_record_and_withdraws_it_once(self):
        _, project, hid = self.project()
        deviation = project.add_protocol_record(
            "deviation", hypothesis_id=hid, reason="Skewed totals.",
            detail={"what": "method", "planned": "Pearson's r", "actual": "Spearman's ρ"})
        with self.assertRaises(ProjectError):
            project.add_protocol_record("withdrawal", hypothesis_id=hid, reason="Wrong")
        with self.assertRaises(ProjectError):
            project.add_protocol_record("withdrawal", hypothesis_id=hid, reason="Wrong",
                                        supersedes="no-such-record")
        withdrawal = project.add_protocol_record("withdrawal", hypothesis_id=hid,
                                                 reason="Recorded for the wrong task.",
                                                 supersedes=deviation["id"])
        with self.assertRaises(ProjectError):
            project.add_protocol_record("withdrawal", hypothesis_id=hid, reason="Again",
                                        supersedes=deviation["id"])
        with self.assertRaises(ProjectError):
            project.add_protocol_record("withdrawal", hypothesis_id=hid, reason="Undo",
                                        supersedes=withdrawal["id"])
        self.assertEqual([r["kind"] for r in project.protocol_records()],
                         ["deviation", "withdrawal"], "both stay in the history")

    def test_records_cannot_be_changed_or_deleted(self):
        info, project, hid = self.project()
        project.add_protocol_record("link", hypothesis_id=hid, task_id="t1")
        self.assertEqual(sorted(n for n in dir(project) if "protocol" in n),
                         ["add_protocol_record", "protocol_records"], "no update or delete API")
        with closing(sqlite3.connect(info.path / ps.DB_NAME)) as db:
            for statement in ("UPDATE protocol_records SET reason = 'x'",
                              "DELETE FROM protocol_records"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    db.execute(statement)
        self.assertEqual(len(project.protocol_records()), 1)

    def test_records_travel_in_a_backup_and_a_duplicate(self):
        info, project, hid = self.project()
        project.add_protocol_record("deviation", hypothesis_id=hid, reason="Skewed totals.",
                                    detail={"what": "method"})
        project.close()
        self.store.export_package(info.id, self.base / "study.sra")
        restored, _ = self.restart().import_package(self.base / "study.sra")
        copy = self.restart().duplicate(info.id)
        for project_id in (restored.id, copy.id):
            with self.restart().open(project_id) as other:
                self.assertEqual([r["kind"] for r in other.protocol_records()], ["deviation"])


class SnapshotTests(Case):
    SNAPSHOT = {"id": "0a1b2c3d4e5f", "plan_version": 2, "priority": "primary",
                "direction": "less", "alpha": 0.05, "standing": "confirmatory",
                "question_id": "1a2b3c4d5e6f"}

    def test_a_run_keeps_the_hypothesis_it_was_calculated_for(self):
        info = self.store.create("Snapshot")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            run = self.groups_run(project, dataset, hypothesis={**self.SNAPSHOT, "extra": "x"})
            plain = self.groups_run(project, dataset)
        with self.restart().open(info.id) as project:
            self.assertEqual(project.run(run.id).hypothesis, self.SNAPSHOT, "known keys only")
            self.assertIsNone(project.run(plain.id).hypothesis)

    def test_an_invalid_snapshot_is_refused(self):
        info = self.store.create("Bad snapshot")
        with self.store.open(info.id) as project:
            dataset = project.import_dataset(EXAMPLES / "sample_scale.csv", mode="copy")
            with self.assertRaises(ProjectError):
                self.groups_run(project, dataset, hypothesis={**self.SNAPSHOT, "id": "../x"})

    def test_the_snapshot_comes_back_into_the_session_after_a_restart(self):
        from test_stage36_ux_baseline import CountingWorkspace, eight_correlations, prepared_workspace

        with TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                eight_correlations(ws)
                first = ws.app.session.results[0]
                entry = ws.app.session.add_result(
                    first.run, (), method=first.method, roles=first.roles, options=first.options,
                    confirms={}, task_id=first.task_id, hypothesis=self.SNAPSHOT)
                self.assertEqual(entry.provenance["hypothesis"], self.SNAPSHOT)
                project_id = ws.app.projects.info().id
            finally:
                ws.close()
            again = CountingWorkspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                restored = again.app.session.results
                self.assertIsNone(restored[0].provenance.get("hypothesis"))
                self.assertEqual(restored[1].provenance["hypothesis"], self.SNAPSHOT)
            finally:
                again.close()


class ReportExportTests(Case):
    def test_the_last_export_is_remembered(self):
        info = self.store.create("Export")
        with self.store.open(info.id) as project:
            self.assertIsNone(project.last_report_export())
            project.record_report_export(["r1", "r2"], "docx")
            self.assertEqual(project.last_report_export(), {"format": "docx", "runs": ["r1", "r2"]})


if __name__ == "__main__":
    unittest.main()
