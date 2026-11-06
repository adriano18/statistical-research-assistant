"""Stage 34.5 (issue #32): what a result rests on, and interpretation at a
student's and a professor's depth with unverified decisions labelled.
Fictional data only; drives the real controls through the harness."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from workspace_harness import Workspace  # noqa: E402

ROLES = {"outcome": "wellbeing", "group": "group", "covariates": ["baseline_score"]}


def texts_in(ws, data: str) -> str:
    return " ".join(c.value for c in ws.controls(ws.find(data))
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.close)
        self.ws.run(self.ws.app.load_sample("sample_ancova.csv"))
        self.ws.app.session.accept_suggestions()
        self.entry = self.ws.run(self.ws.app.pages["analyze"]._execute(
            "ancova", ROLES, {"mode": "ancova"}, {"model": True}))


class ProvenanceTests(Base):
    def test_the_result_names_the_data_version_complete_cases_and_coding(self):
        ws, entry = self.ws, self.entry
        digest = hashlib.sha256(ws.app.session.df.to_csv(index=False, lineterminator="\n")
                                .encode("utf-8")).hexdigest()
        self.assertEqual(entry.provenance["dataset_sha256"], digest)
        self.assertEqual(entry.provenance["variables"], ["wellbeing", "group", "baseline_score"])
        text = texts_in(ws, "result-provenance")
        self.assertIn(f"version {digest[:12]}", text)
        self.assertIn("179 of 180 rows used (1 excluded for missing values)", text,
                      "the engine's own complete-case count")
        self.assertIn("group: Nominal (categories) (A, B, C)", text)
        self.assertIn("level accepted from the suggestions", text)
        self.assertIn("ANCOVA / general linear model · Model = ", text)

    def test_the_word_export_settings_are_stated(self):
        ws = self.ws
        self.assertIn("0 of 3 checks marked as reviewed", texts_in(ws, "result-export-settings"))
        ws.check("review-0", True)
        self.assertIn("1 of 3 checks marked as reviewed", texts_in(ws, "result-export-settings"))

    def test_a_restored_result_keeps_its_version(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as folder:
            first = Workspace(root=Path(folder))
            try:
                first.app.projects.create("Fictional provenance")
                first.run(first.app.load_sample("sample_ancova.csv"))
                first.app.session.accept_suggestions()
                entry = first.run(first.app.pages["analyze"]._execute(
                    "ancova", ROLES, {"mode": "ancova"}, {"model": True}))
                digest = entry.provenance["dataset_sha256"]
                project_id = first.app.projects.project.id
            finally:
                first.close()
            again = Workspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                restored = again.app.session.results[0]
                self.assertTrue(restored.restored)
                self.assertEqual(restored.provenance["dataset_sha256"], digest)
                again.app.session.selected_result = restored.id
                again.app.navigate("results")
                self.assertIn("restored from the project", texts_in(again, "result-provenance"))
            finally:
                again.close()


class DepthTests(Base):
    def open_interpretation(self):
        page = self.ws.app.pages["results"]
        page.opened.add(f"interpretation-{self.entry.id}")
        self.ws.app.render()
        return page

    def test_student_and_professor_depth_and_unverified_labels(self):
        ws = self.ws
        self.open_interpretation()
        student = ws.find("result-interpretation").value
        self.assertIn("This does not establish causality", student)
        self.assertIn("Not yet verified by you (3)", texts_in(ws, "result-unverified"))
        ws.segment("result-depth", "professor")
        professor = ws.find("result-interpretation").value
        self.assertIn("Verified calculation output", professor)
        self.assertIn("95% CI", professor)
        self.assertIn("3 check(s) remain unreviewed", professor)
        for index in range(3):
            ws.check(f"review-{index}", True)
        self.assertIn("does not prove the assumptions hold", texts_in(ws, "result-unverified"))

    def test_doctoral_and_faculty_profiles_start_with_professor_depth(self):
        from dataclasses import replace

        ws = self.ws
        page = self.open_interpretation()
        self.assertEqual(page._default_depth(), "student")
        ws.app.profile = replace(ws.app.profile, study_level="faculty")
        self.assertEqual(page._default_depth(), "professor")
        ws.app.render()
        self.assertIn("Verified calculation output", ws.find("result-interpretation").value)

    def test_no_confidence_interval_is_invented(self):
        rows = self.entry.run.evidence().rows
        group_f = next(r for r in rows if r.parameter == "Adjusted group F")
        self.assertEqual(group_f.ci, "Not calculated")
        self.open_interpretation()
        self.ws.segment("result-depth", "professor")
        text = self.ws.find("result-interpretation").value
        self.assertNotIn("Adjusted group F: 32.607, 95% CI", text)


if __name__ == "__main__":
    unittest.main()
