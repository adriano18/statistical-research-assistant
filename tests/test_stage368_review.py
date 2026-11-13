"""Stage 36.8 review, defects K1–K3 (FABLE review, sections K1–K3).

K1  A design-step confirmation holds only for what it was given for.
    Design confirmations (independent groups, the same participants, items
    meant for one construct, two categorical variables) stay with the task
    while the variables they speak about are unchanged. Data confirmations
    (distributions, outliers, group sizes, linearity …) hold for one table
    (its SHA-256), one set of variables with their confirmed levels and one
    method with its options; any change clears them.
K2  The researcher's notes and assumption reviews (per result) and the
    report's title, sections and language (per project) are kept in the
    project, come back after a restart and never appear in another project.
K3  Data → Prepare keeps the confirmed levels of the columns that are still
    there and records every step in the project history (and so in the
    report's data-preparation section).

Every workflow is driven through the real handlers (tests/workspace_harness.py)
on synthetic data.
"""

from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import uuid

import flet as ft
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import stage36_fixtures as fx  # noqa: E402
from test_stage36_ux_baseline import (  # noqa: E402
    LEVELS, CountingWorkspace, eight_correlations, prepared_workspace,
)
from workspace_harness import Workspace  # noqa: E402

INDEPENDENT = "I confirm the groups contain independent participants"
DISTRIBUTIONS = "I reviewed the outcome distributions, outliers and group sizes"
NOTE = "Fictional reading: loneliness goes with more cautious action."


def compare_by_levels(ws) -> None:
    """Goal "compare": the eight scales by UCLA_Level (3 groups), both
    confirmations given."""
    ws.click("nav-analyze")
    ws.click("goal-compare")
    ws.choose("role-group", "UCLA_Level")
    for scale in fx.SCALES:
        ws.check(f"role-outcome-{scale}")
    ws.check("design-confirm-independent")
    ws.check("design-confirm-assumptions")


def ticked(ws, key: str) -> bool:
    return bool(ws.find(f"design-confirm-{key}").value)


def document_text(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def corrected_file(folder: Path) -> Path:
    """The same participants and groups, other scale values (a corrected file)."""
    frame = pd.read_csv(fx.fixture(fx.CSV))
    frame[list(fx.SCALES)] = frame[list(fx.SCALES)].sample(frac=1, random_state=1).to_numpy()
    path = Path(folder) / "corrected.csv"
    frame.to_csv(path, index=False)
    return path


# ===================================================================== K1
class DesignConfirmationTests(unittest.TestCase):
    def test_another_grouping_variable_clears_both_confirmations(self):
        """repro1 A: confirmed for UCLA_Level (Kruskal–Wallis), then Sex."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        compare_by_levels(ws)
        self.assertFalse(ws.find("guided-run").disabled)
        self.assertEqual(ws.find_all("design-reconfirm"), [])
        ws.choose("role-group", "Sex")
        self.assertFalse(ticked(ws, "independent"), "given for other groups")
        self.assertFalse(ticked(ws, "assumptions"), "given for other groups and another test")
        self.assertEqual(ws.app.pages["analyze"].confirms, {}, "cleared, not only hidden")
        self.assertTrue(ws.find("guided-run").disabled)
        self.assertTrue(ws.find_all("design-reconfirm"), "the empty boxes are explained")
        ws.key("Enter", ctrl=True)                      # the keyboard path does not run it
        self.assertEqual(ws.app.session.results, [])
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        self.assertEqual(ws.find_all("design-reconfirm"), [])
        ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.roles["group"], "Sex")
        self.assertEqual(entry.confirmations, (INDEPENDENT, DISTRIBUTIONS))

    def test_other_outcomes_keep_the_design_and_clear_the_data_confirmation(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        compare_by_levels(ws)
        ws.check(f"role-outcome-{fx.SCALES[0]}", False)
        self.assertTrue(ticked(ws, "independent"), "the groups are the same groups")
        self.assertFalse(ticked(ws, "assumptions"), "other outcome distributions")
        self.assertTrue(ws.find("guided-run").disabled)
        ws.check("design-confirm-assumptions")
        ws.click("guided-run")
        entry = ws.app.session.results[-1]
        self.assertEqual(entry.roles["outcomes"], list(fx.SCALES[1:]))
        self.assertEqual(entry.confirmations, (INDEPENDENT, DISTRIBUTIONS))

    def test_another_method_clears_the_data_confirmation(self):
        """Welch's t needs the distributions reviewed; after Mann–Whitney and
        back, that review is asked again (it was given for Welch)."""
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.click("goal-compare")
        ws.choose("role-group", "Sex")
        ws.check("role-outcome-UCLA")
        self.assertTrue(ws.find("guided-method").value.startswith("Welch"))
        ws.check("design-confirm-independent")
        ws.check("design-confirm-assumptions")
        ws.click("alt-groups-mannwhitney")
        self.assertEqual(ws.find_all("design-confirm-assumptions"), [], "not asked for ranks")
        self.assertTrue(ticked(ws, "independent"))
        self.assertFalse(ws.find("guided-run").disabled)
        ws.click("alt-groups-welch")
        self.assertTrue(ticked(ws, "independent"))
        self.assertFalse(ticked(ws, "assumptions"), "given for another method")
        self.assertTrue(ws.find("guided-run").disabled)

    def test_a_changed_measurement_level_clears_the_data_confirmation(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        compare_by_levels(ws)
        ws.click("nav-data")
        ws.choose(f"level-{fx.SCALES[0]}", "ordinal")
        ws.click("nav-analyze")
        self.assertTrue(ticked(ws, "independent"))
        self.assertFalse(ticked(ws, "assumptions"), "reviewed as a quantitative variable")
        self.assertTrue(ws.find("guided-run").disabled)

    def test_run_again_on_the_same_data_needs_no_new_confirmation(self):
        """Run again stays two actions in the session, and after a restart on
        the same data the task's confirmations still hold."""
        with TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                compare_by_levels(ws)
                ws.click("guided-run")
                task = ws.app.projects.project.task(ws.app.session.results[0].task_id)
                scopes = task.state["confirm_scopes"]          # what each was given for
                self.assertEqual((scopes["independent"]["kind"], scopes["assumptions"]["kind"]),
                                 ("design", "data"))
                self.assertEqual(scopes["independent"]["variables"], {"group": ["UCLA_Level"]})
                self.assertEqual(scopes["assumptions"]["dataset"],
                                 ws.app.session.results[0].provenance["dataset_sha256"])
                ws.click("nav-results")
                ws.counts.clear()
                ws.click("nav-analyze")
                ws.click("task-rerun")
                self.assertEqual(ws.total, 2)
                first, second = ws.app.session.results
                self.assertEqual(second.task_id, first.task_id)
                self.assertEqual(second.confirmations, (INDEPENDENT, DISTRIBUTIONS))
                task_id, project_id = first.task_id, ws.app.projects.info().id
            finally:
                ws.close()
            again = CountingWorkspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                again.counts.clear()
                again.click("nav-analyze")
                again.click(f"task-{task_id}")
                self.assertTrue(ticked(again, "independent"))
                self.assertTrue(ticked(again, "assumptions"), "the same table, variables, method")
                again.click("task-rerun")
                self.assertEqual(again.total, 3)
                self.assertEqual(len(again.app.session.results), 3)
                self.assertEqual(again.app.session.results[-1].confirmations,
                                 (INDEPENDENT, DISTRIBUTIONS))
            finally:
                again.close()

    def test_after_a_restart_another_data_file_needs_the_data_confirmation_again(self):
        """repro9: the task reopens on a corrected file."""
        with TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                compare_by_levels(ws)
                ws.click("guided-run")
                project_id = ws.app.projects.info().id
            finally:
                ws.close()
            changed = corrected_file(Path(folder))
            again = CountingWorkspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                session = again.app.session
                self.assertTrue(again.run(again.app.load_path(str(changed))))
                for name, level in LEVELS.items():
                    session.confirm_level(name, level)
                again.click("nav-analyze")
                again.click(f"task-{session.tasks[0].id}")
                self.assertTrue(ticked(again, "independent"), "a design confirmation")
                self.assertFalse(ticked(again, "assumptions"), "given for another table")
                self.assertTrue(again.find_all("design-reconfirm"))
                self.assertTrue(again.find("guided-run").disabled)
                self.assertTrue(again.find("task-rerun").disabled)
                before = len(session.results)
                again.key("Enter", ctrl=True)
                self.assertEqual(len(session.results), before, "nothing ran")
                again.check("design-confirm-assumptions")
                self.assertFalse(again.find("task-rerun").disabled)
                again.click("guided-run")
                entry = session.results[-1]
                self.assertEqual(entry.dataset, "corrected.csv")
                self.assertEqual(entry.confirmations, (INDEPENDENT, DISTRIBUTIONS))
            finally:
                again.close()

    def test_a_task_without_a_record_of_its_confirmations_asks_again(self):
        """A task saved before Stage 36.8 cannot say what its ticks were
        given for, so none is taken over."""
        from workspace_state import ResearchTask

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        session = ws.app.session
        task = session.save_task(ResearchTask(
            str(uuid.uuid4()), "8 outcomes by UCLA_Level", "compare",
            {"outcome": list(fx.SCALES), "group": "UCLA_Level"}, "batch_groups",
            {"adjust": "holm", "two_group_method": "mannwhitney"},
            {"independent": True, "assumptions": True}, None, {"created": "2026-11-01T10:00:00"}))
        ws.click("nav-analyze")
        ws.click(f"task-{task.id}")
        self.assertFalse(ticked(ws, "independent"))
        self.assertFalse(ticked(ws, "assumptions"))
        self.assertTrue(ws.find_all("design-reconfirm"))
        self.assertTrue(ws.find("guided-run").disabled)

    def test_the_all_methods_form_follows_the_same_rule(self):
        ws = prepared_workspace()
        self.addCleanup(ws.close)
        ws.click("nav-analyze")
        ws.segment("analyze-mode", "all")
        ws.click("method-groups")
        ws.choose("form-outcome", "UCLA")
        ws.choose("form-group", "Sex")
        ws.choose("form-option-method", "welch")
        ws.check("form-confirm-independent")
        ws.check("form-confirm-assumptions")
        self.assertFalse(ws.find("form-run").disabled)
        ws.choose("form-outcome", "Age")
        self.assertTrue(ws.find("form-confirm-independent").value)
        self.assertFalse(ws.find("form-confirm-assumptions").value)
        self.assertTrue(ws.find_all("form-reconfirm"))
        self.assertTrue(ws.find("form-run").disabled)
        ws.key("Enter", ctrl=True)
        self.assertEqual(ws.app.session.results, [], "Ctrl+Enter does not run it either")


# ===================================================================== K2
class ResearcherEntriesTests(unittest.TestCase):
    def enter_everything(self, ws):
        """A result with one reviewed check and a note in the report, the
        report titled, the limitations left out and Latvian chosen."""
        eight_correlations(ws)
        entry = ws.app.session.results[-1]
        ws.click("task-add-report")
        ws.click("task-open-result")
        ws.check("review-0", True)
        ws.type("result-notes", NOTE)
        ws.click("nav-reports")
        ws.type("reports-study-title", "Fictional loneliness study")
        ws.check("reports-section-limitations", False)
        ws.choose("reports-language", "lv")
        return entry, entry.run.evidence().assumptions

    def test_a_restart_brings_back_notes_reviews_and_report_settings(self):
        from research_report import TEXT as REPORT

        with TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                _, assumptions = self.enter_everything(ws)
                project_id = ws.app.projects.info().id
            finally:
                ws.close()
            again = Workspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                restored = again.app.session.results[-1]
                again.app.session.selected_result = restored.id
                again.click("nav-results")
                self.assertEqual(again.find("result-notes").value, NOTE)
                self.assertTrue(again.find("review-0").value)
                self.assertFalse(again.find("review-1").value)
                self.assertEqual(restored.note, NOTE)
                self.assertEqual(set(restored.reviewed), {assumptions[0]})
                again.click("nav-reports")
                self.assertEqual(again.find("reports-study-title").value,
                                 "Fictional loneliness study")
                self.assertFalse(again.find("reports-section-limitations").value)
                self.assertTrue(again.find("reports-section-appendix").value)
                self.assertEqual(again.find("reports-language").value, "lv")
                # The Word report written after the restart knows what was reviewed.
                again.click("reports-export-docx")
                text = document_text(again.saved[-1])
                # The report writes each check in its own language (Stage 36.8
                # locale audit); the review is recorded against the English text.
                from interpretation_i18n import translate_assumption

                reviewed, still_open = (translate_assumption(a, "lv") for a in assumptions[:2])
                self.assertIn(f"{reviewed} — {REPORT['lv']['assumption_reviewed']}", text)
                self.assertIn(f"{still_open} — {REPORT['lv']['assumption_open']}", text)
                self.assertIn(NOTE, text)
                self.assertIn("Fictional loneliness study", text)
                self.assertNotIn(REPORT["lv"]["limitations"], text, "left out by the researcher")
                # So does the result's own Word draft.
                again.app.session.selected_result = restored.id
                again.click("nav-results")
                again.click("export-docx")
                draft = document_text(again.saved[-1])
                self.assertIn(f"Reviewed by researcher: {assumptions[0]}", draft)
                self.assertIn(f"Not reviewed: {assumptions[1]}", draft)
                self.assertIn(NOTE, draft)
            finally:
                again.close()

    def test_another_project_shows_none_of_these_entries(self):
        from research_report import SECTIONS

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        project_a = ws.app.projects.info().id
        entry_a, _ = self.enter_everything(ws)
        record_a = entry_a.record_id
        reports = ws.app.pages["reports"]
        reports.include_stale = True        # a deliberate override, for A only
        ws.click("nav-home")
        ws.type("project-new-title", "Fictional study B")
        ws.click("project-create")
        self.assertEqual(ws.app.session.results, [])
        self.assertEqual((reports.study_title, reports.sections, reports.language,
                          reports.include_stale), ("", set(SECTIONS), None, False))
        self.assertTrue(ws.run(ws.app.load_path(str(fx.fixture(fx.CSV)))))
        for name, level in LEVELS.items():
            ws.app.session.confirm_level(name, level)
        eight_correlations(ws)
        ws.click("task-add-report")
        ws.click("task-open-result")
        self.assertEqual(ws.find("result-notes").value, "")
        self.assertFalse(ws.find("review-0").value)
        ws.click("nav-reports")
        self.assertEqual(ws.find("reports-study-title").value, "")
        self.assertTrue(ws.find("reports-section-limitations").value)
        self.assertEqual(ws.find("reports-language").value, "en")
        # Back in A, A's entries are there again.
        ws.click("nav-home")
        ws.click(f"project-open-{project_a}")
        entry = ws.app.session.results[-1]
        self.assertEqual((entry.record_id, entry.note), (record_a, NOTE))
        self.assertEqual((reports.study_title, reports.language),
                         ("Fictional loneliness study", "lv"))
        self.assertNotIn("limitations", reports.sections)

    def test_a_title_typed_last_is_saved_when_the_project_closes(self):
        """The title is saved when its field is left; typed as the very last
        thing before the program ends, it is saved when the project closes."""
        with TemporaryDirectory() as folder:
            ws = prepared_workspace(root=Path(folder))
            try:
                eight_correlations(ws)
                ws.click("task-add-report")
                ws.click("nav-reports")
                ws.type("reports-study-title", "Fictional title typed last")
                project_id = ws.app.projects.info().id
            finally:
                ws.close()
            again = Workspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                again.click("nav-reports")
                self.assertEqual(again.find("reports-study-title").value,
                                 "Fictional title typed last")
            finally:
                again.close()

    def test_a_title_typed_last_is_saved_when_the_program_ends(self):
        """Closing the window ends the process; the exit hook saves first."""
        import weakref

        import project_session

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        eight_correlations(ws)
        ws.click("task-add-report")
        ws.click("nav-reports")
        ws.type("reports-study-title", "Fictional title at exit")
        binding = ws.app.projects
        project_session._release_at_exit(weakref.ref(binding))
        with binding.store.open(binding.project.id, read_only=True) as stored:
            self.assertEqual(stored.report_settings()["title"], "Fictional title at exit")

    def test_work_done_before_the_project_moves_into_it(self):
        with TemporaryDirectory() as folder:
            ws = Workspace(root=Path(folder))
            try:
                self.assertTrue(ws.run(ws.app.load_path(str(fx.fixture(fx.CSV)))))
                for name, level in LEVELS.items():
                    ws.app.session.confirm_level(name, level)
                _, assumptions = self.enter_everything(ws)
                info = ws.app.projects.create("Fictional adopted study")
            finally:
                ws.close()
            again = Workspace(root=Path(folder))
            try:
                again.app.projects.open(info.id)
                reports = again.app.pages["reports"]
                self.assertEqual((reports.study_title, reports.language),
                                 ("Fictional loneliness study", "lv"))
                restored = again.app.session.results[-1]
                again.app.session.selected_result = restored.id
                again.click("nav-results")
                self.assertEqual(again.find("result-notes").value, NOTE)
                self.assertEqual((restored.note, set(restored.reviewed)), (NOTE, {assumptions[0]}))
            finally:
                again.close()

    def test_the_project_format_is_unchanged(self):
        """No migration: the entries use storage that format-5 programs
        already have and ignore (docs/PROJECTS_ARCHITECTURE.md §4)."""
        import json
        import sqlite3
        from contextlib import closing

        from project_store import DB_NAME, SCHEMA_VERSION

        ws = prepared_workspace()
        self.addCleanup(ws.close)
        entry, assumptions = self.enter_everything(ws)
        path = ws.app.projects.project.path / DB_NAME

        def stored_settings() -> list[dict]:
            with closing(sqlite3.connect(path)) as db:
                return [json.loads(row[0]) for row in db.execute(
                    "SELECT detail FROM events WHERE kind = 'report_settings' ORDER BY id")]

        before = len(stored_settings())
        title = "Fictional loneliness study, wave 2"
        for end in range(1, len(title) + 1):                  # typed key by key
            ws.type("reports-study-title", title[:end])
        self.assertEqual(len(stored_settings()), before, "nothing logged per keystroke")
        field = ws.find("reports-study-title")
        ws.dispatch(field.on_blur, SimpleNamespace(control=field))   # the field is left
        settings = stored_settings()
        self.assertEqual(len(settings), before + 1, "one entry for the edit")
        self.assertEqual(settings[-1], {"title": title, "sections_off": ["limitations"],
                                        "language": "lv"})
        # Stage 37.0a moved the project to format 6 (protocol records, an
        # additive table); the four K2 entries still use format-5 storage.
        self.assertEqual(SCHEMA_VERSION, 6)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
            note, provenance = db.execute("SELECT note, provenance FROM runs WHERE id = ?",
                                          (entry.record_id,)).fetchone()
        self.assertEqual(note, NOTE)                         # runs.note (format 1)
        provenance = json.loads(provenance)
        self.assertEqual(provenance["reviewed"], [assumptions[0]])
        self.assertTrue({"libraries", "rows", "inputs"} <= set(provenance), "read as before")


# ===================================================================== K3
class PreparationHistoryTests(unittest.TestCase):
    """Data → Prepare (the classic panel, hosted unchanged) driven by its
    own controls: reverse-score an item, then a scale mean."""

    def panel(self, ws):
        return ws.controls(ws.app.pages["data"]._preparation[0])

    def control(self, ws, kind, label):
        for control in self.panel(ws):
            if isinstance(control, kind) and label in (getattr(control, "label", None),
                                                       getattr(control, "content", None)):
                return control
        raise AssertionError(f"no {kind.__name__} {label!r} in the preparation panel")

    def press(self, ws, label):
        button = self.control(ws, ft.Button, label)
        ws.dispatch(button.on_click, SimpleNamespace(control=button))

    def choose(self, ws, label, value):
        dropdown = self.control(ws, ft.Dropdown, label)
        dropdown.value = value
        if dropdown.on_select is not None:
            ws.dispatch(dropdown.on_select, SimpleNamespace(control=dropdown, data=value))

    def prepare(self, ws):
        ws.click("nav-data")
        ws.click("data-prepare")
        self.choose(ws, "Transformation", "reverse")
        self.choose(ws, "Source variable", "ZEP04")
        self.control(ws, ft.TextField, "New variable name").value = "ZEP04_r"
        self.press(ws, "Apply transformation")
        self.choose(ws, "Transformation", "scale")
        for item in ("ZEP01", "ZEP02", "ZEP03", "ZEP04_r"):
            self.control(ws, ft.Checkbox, item).value = True
        self.control(ws, ft.TextField, "New variable name").value = "ZEP_mean4"
        self.press(ws, "Apply transformation")
        self.press(ws, "Use working copy in analysis")

    def items_workspace(self, root=None):
        ws = Workspace(root=root)
        ws.app.projects.create("Fictional scoring study")
        self.assertTrue(ws.run(ws.app.load_path(str(fx.fixture(fx.ITEMS_CSV)))))
        session = ws.app.session
        session.accept_suggestions()
        session.confirm_level("ZEP01", "ordinal")          # the researcher's own decision
        session.confirm_level(fx.ITEM_TOTAL, "scale")
        return ws

    def test_the_confirmed_levels_of_existing_columns_are_kept(self):
        with TemporaryDirectory() as folder:
            ws = self.items_workspace(Path(folder))
            try:
                session = ws.app.session
                before = {name: (info.confirmed, info.confirmed_in)
                          for name, info in session.variables.items()}
                self.assertEqual(session.pending_levels(), 0)
                self.prepare(ws)
                self.assertIn("ZEP_mean4", session.df.columns)
                self.assertEqual(session.dataset_origin, "prepared")
                after = {name: (info.confirmed, info.confirmed_in)
                         for name, info in session.variables.items()}
                self.assertEqual({name: after[name] for name in before}, before)
                self.assertEqual((session.level("ZEP04_r"), session.level("ZEP_mean4")),
                                 ("unknown", "unknown"), "new columns wait for the researcher")
                self.assertEqual(session.pending_levels(), 2)
                project_id = ws.app.projects.info().id
            finally:
                ws.close()
            again = Workspace(root=Path(folder))
            try:
                again.app.projects.open(project_id)
                restored = {name: (info.confirmed, info.confirmed_in)
                            for name, info in again.app.session.variables.items()
                            if name in before}
                self.assertEqual(restored, before, "saved with the prepared dataset")
            finally:
                again.close()

    def test_a_prepared_table_given_directly_keeps_the_levels_too(self):
        """repro4 hands the prepared table to set_dataset itself."""
        import data_preparation as dp

        ws = self.items_workspace()
        self.addCleanup(ws.close)
        session = ws.app.session
        before = {name: session.level(name) for name in session.variables}
        step = dp.reverse_item(session.df, "ZEP04", "ZEP04_r", 1, 5)
        session.set_dataset(step.frame, f"{session.source_name} (prepared)", origin="prepared")
        self.assertEqual({name: session.level(name) for name in before}, before)
        # Another file with some of the same column names is another dataset.
        session.set_dataset(session.df[["ZEP01", "ZEP02"]].copy(), "other.csv")
        self.assertEqual(session.pending_levels(), 2)

    def test_the_steps_are_in_the_project_history_and_the_report(self):
        import research_report as rr

        ws = self.items_workspace()
        self.addCleanup(ws.close)
        self.prepare(ws)
        project = ws.app.projects.project
        active = project.active_dataset()
        self.assertEqual(active.origin, "derived")
        steps = project.transformations(active.id)
        self.assertEqual([s["kind"] for s in steps], ["reverse_item", "score_scale"])
        self.assertEqual([s["output_columns"] for s in steps], [["ZEP04_r"], ["ZEP_mean4"]])
        self.assertEqual((steps[0]["params"]["source"], steps[0]["params"]["minimum"],
                          steps[0]["params"]["maximum"]), ("ZEP04", 1.0, 5.0))
        self.assertEqual(steps[1]["params"]["sources"], ["ZEP01", "ZEP02", "ZEP03", "ZEP04_r"])
        self.assertEqual(ws.app.session.pending_transformations, [])
        inputs = ws.app.pages["reports"].report_inputs()
        plan = rr.plan_report(inputs)
        section = next(s for s in plan.sections if s.key == "preparation")
        listed = "\n".join(item.text for item in section.items)
        self.assertIn("reverse_item → ZEP04_r", listed)
        self.assertIn("score_scale → ZEP_mean4", listed)


if __name__ == "__main__":
    unittest.main()
