"""Stage 34.5 (issue #30): blockers found by testing the packaged Windows app.

Each test drives the real workspace controls through the harness (synthetic
data only). They were written against PR #29 first and failed there; the
root causes are recorded in docs/STAGE345_FINDINGS.md.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

from workspace_harness import Workspace  # noqa: E402

EXAMPLES = ROOT / "examples"
GROUPS = {"outcome": "stress_q1", "group": "group"}
QUESTIONS = [
    {"key": "group", "kind": "single_choice", "prompt": "Fictional group", "required": True,
     "options": ["A", "B"]},
    {"key": "q1", "kind": "likert5", "prompt": "Fictional statement", "required": True,
     "options": []},
]


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        remember = mock.patch("workspace_shell.WorkspaceApp._remember_file")
        remember.start()
        self.addCleanup(remember.stop)

    def workspace(self, **kwargs) -> Workspace:
        ws = Workspace(root=self.base, **kwargs)
        self.addCleanup(ws.close)
        return ws

    def status(self, ws) -> str:
        return ws.app.status_text.value or ""

    def groups_result(self, ws):
        data = self.base / "measurements.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", data)
        self.assertTrue(ws.run(ws.app.load_path(str(data))))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        entry = ws.run(ws.app.pages["analyze"]._execute("groups", GROUPS, {},
                                                        {"independent": True}))
        self.assertIsNotNone(entry)
        return entry


class ProjectWorkspaceTests(Case):
    """Opening or creating a project must lead somewhere understandable."""

    def test_creating_a_project_opens_its_workspace(self):
        ws = self.workspace()
        ws.app.navigate("home")
        ws.type("project-new-title", "Fictional sleep study")
        ws.click("project-create")
        self.assertEqual(ws.app.route, "project")
        self.assertTrue(ws.find("project-dashboard"))
        self.assertTrue(ws.has_text("Fictional sleep study"))
        self.assertTrue(ws.find("project-next-action"), "the first step is offered")

    def test_opening_a_project_opens_its_workspace_with_its_sources(self):
        ws = self.workspace()
        info = ws.app.projects.create("Fictional exam study")
        self.groups_result(ws)
        ws.app.projects.close()
        ws.app.navigate("home")
        ws.click(f"project-open-{info.id}")
        self.assertEqual(ws.app.route, "project")
        self.assertTrue(ws.find("project-sources"))
        self.assertTrue(ws.has_text("measurements.csv"))
        self.assertTrue(ws.find("project-results"))


class ProjectPageTests(Case):
    """The project page keeps sources apart and always offers the next step."""

    def next_title(self, ws) -> str:
        card = ws.find("project-next-action")
        return next(c.value for c in ws.controls(card) if isinstance(c, ft.Text))

    def test_the_next_step_follows_the_research(self):
        ws = self.workspace()
        ws.app.projects.create("Fictional journey")
        ws.app.navigate("project")
        self.assertEqual(self.next_title(ws), ws.app.t("next.add_data"))
        self.assertTrue(ws.find("next-open-data"))
        data = self.base / "measurements.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", data)
        ws.run(ws.app.load_path(str(data)))
        ws.app.navigate("project")
        self.assertEqual(self.next_title(ws), ws.app.t("next.levels"))
        ws.app.session.accept_suggestions()
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        ws.app.navigate("project")
        self.assertEqual(self.next_title(ws), ws.app.t("next.analyze"))
        entry = ws.run(ws.app.pages["analyze"]._execute("groups", GROUPS, {},
                                                        {"independent": True}))
        ws.app.navigate("project")
        self.assertEqual(self.next_title(ws), ws.app.t("next.report"))
        self.assertTrue(ws.find(f"project-result-{entry.id}"))
        ws.app.session.toggle_report(entry.id)
        ws.app.navigate("project")
        self.assertEqual(self.next_title(ws), ws.app.t("next.export"))
        ws.click("next-report")
        self.assertEqual(ws.app.route, "reports")

    def test_the_data_page_switches_between_the_projects_datasets(self):
        ws = self.workspace()
        ws.app.projects.create("Fictional two tables")
        self.groups_result(ws)
        ws.run(ws.app.load_sample("sample_three_groups.csv"))
        records = {d.name: d.id for d in ws.app.projects.project.datasets()}
        self.assertEqual(set(records), {"measurements.csv", "sample_three_groups.csv"})
        ws.app.navigate("data")
        ws.choose("data-source", records["measurements.csv"])
        self.assertEqual(ws.app.session.source_name, "measurements.csv")
        self.assertEqual(ws.app.session.level("group"), "nominal")
        self.assertEqual(len(ws.app.projects.project.datasets()), 2, "nothing is copied again")

    def test_a_questionnaire_published_in_a_project_belongs_to_it(self):
        ws = self.workspace()
        ws.app.projects.create("Fictional survey project")
        builder = ws.app.pages["questionnaires"]
        builder.title = "Fictional project form"
        builder.draft = [dict(q) for q in QUESTIONS]
        survey = builder._publish()
        self.assertIn(survey.survey_id, ws.app.projects.questionnaire_ids())
        ws.app.navigate("project")
        self.assertTrue(ws.find(f"project-collect-{survey.survey_id}"))
        self.assertTrue(ws.has_text("Fictional project form"))
        ws.app.navigate("questionnaires")
        self.assertTrue(ws.has_text(ws.app.t("q.in_project")))

    def test_closing_the_project_returns_home(self):
        ws = self.workspace()
        ws.app.projects.create("Fictional closing")
        ws.app.navigate("project")
        ws.click("project-close")
        self.assertEqual(ws.app.route, "home")
        ws.app.navigate("project")
        self.assertEqual(ws.app.route, "home", "no project page without a project")

    def test_a_disabled_accept_button_says_why(self):
        ws = self.workspace()
        ws.run(ws.app.load_sample("sample_scale.csv"))
        self.assertEqual(ws.find("data-accept-reason").value, ws.app.t("data.accept_tick_first"))
        self.assertTrue(ws.find("data-accept").disabled)
        ws.check("data-accept-confirm", True)
        ws.click("data-accept")
        self.assertEqual(ws.find("data-accept-reason").value, ws.app.t("data.accept_none_left"))
        self.assertTrue(ws.find("data-next-analyze"))


class SaveOutcomeTests(Case):
    """Every save ends with a visible outcome and a real file."""

    def dialog(self, ws, answer):
        async def save_dialog(title, file_name, extension):
            ws.saved.append(answer)
            return None if answer is None else str(answer)

        ws.app.save_dialog = save_dialog

    def test_a_cancelled_save_is_reported(self):
        ws = self.workspace()
        self.groups_result(ws)
        self.dialog(ws, None)
        ws.click("export-docx")
        self.assertIn("cancelled", self.status(ws).lower())

    def test_a_saved_word_file_is_announced_and_is_a_real_document(self):
        ws = self.workspace()
        self.groups_result(ws)
        target = self.base / "groups.docx"
        self.dialog(ws, target)
        ws.click("export-docx")
        self.assertTrue(target.is_file() and target.stat().st_size > 1000)
        from docx import Document

        text = "\n".join(p.text for p in Document(str(target)).paragraphs)
        self.assertIn("Mann", text)
        self.assertIn(str(target), self.status(ws))

    def test_a_name_typed_without_extension_still_gives_the_right_file(self):
        """Windows' save dialog may return the typed name without the filter's extension."""
        ws = self.workspace()
        self.groups_result(ws)
        for button, suffix in (("export-docx", ".docx"), ("export-txt", ".txt"),
                               ("export-png", ".png")):
            with self.subTest(button=button):
                typed = self.base / f"typed-{suffix[1:]}"
                self.dialog(ws, typed)
                ws.click(button)
                written = typed.with_name(typed.name + suffix)
                self.assertTrue(written.is_file(), f"{written.name} was not written")
                self.assertGreater(written.stat().st_size, 0)
                self.assertIn(written.name, self.status(ws))

    def test_a_folder_that_cannot_be_written_gives_an_actionable_message(self):
        ws = self.workspace()
        self.groups_result(ws)
        self.dialog(ws, self.base / "no-such-folder" / "groups.docx")
        ws.click("export-docx")
        message = self.status(ws)
        self.assertIn("folder", message.lower())
        self.assertNotIn("Errno", message)

    def test_a_report_and_a_backup_are_announced_too(self):
        ws = self.workspace()
        info = ws.app.projects.create("Fictional backup study")
        entry = self.groups_result(ws)
        ws.app.session.toggle_report(entry.id)
        ws.app.navigate("reports")
        report = self.base / "report"
        self.dialog(ws, report)
        ws.click("reports-export")
        self.assertTrue(report.with_name("report.txt").is_file())
        self.assertIn("report.txt", self.status(ws))
        ws.app.navigate("home")
        backup = self.base / "backup"
        self.dialog(ws, backup)
        ws.click(f"project-backup-{info.id}")
        self.assertTrue(backup.with_name("backup.sra").is_file())
        self.assertIn("backup.sra", self.status(ws))


class DataSourceTests(Case):
    """Questionnaire responses never silently replace the dataset in use."""

    def survey_with_responses(self, ws):
        from survey_storage import create_survey, submit_response

        survey = create_survey(ws.app.survey_root, "Fictional wellbeing check", "Fictional",
                               QUESTIONS)
        for group, value in (("A", "1"), ("A", "2"), ("A", "2"), ("B", "4"), ("B", "5")):
            submit_response(ws.app.survey_root, survey.survey_id, {"group": group, "q1": value})
        return survey

    def test_analyzing_responses_asks_before_replacing_the_open_dataset(self):
        ws = self.workspace()
        self.groups_result(ws)
        survey = self.survey_with_responses(ws)
        ws.app.navigate("questionnaires")
        ws.click(f"analyze-{survey.survey_id}")
        self.assertEqual(ws.app.session.source_name, "measurements.csv",
                         "nothing changes before the researcher decides")
        self.assertIsNotNone(ws.page.dialog)
        ws.click("responses-use")
        self.assertIn("Fictional wellbeing check", ws.app.session.source_name)
        self.assertNotEqual(ws.app.session.source_name, "Fictional wellbeing check",
                            "the response dataset has an explicit name of its own")

    def test_in_a_project_both_datasets_stay_available(self):
        ws = self.workspace()
        ws.app.projects.create("Fictional two sources")
        self.groups_result(ws)
        survey = self.survey_with_responses(ws)
        ws.app.navigate("questionnaires")
        ws.click(f"analyze-{survey.survey_id}")
        ws.click("responses-use")
        names = [d.name for d in ws.app.projects.project.datasets()]
        self.assertEqual(len(names), 2)
        self.assertIn("measurements.csv", names)
        ws.app.navigate("project")
        original = next(d for d in ws.app.projects.project.datasets()
                        if d.name == "measurements.csv")
        ws.click(f"source-use-{original.id}")
        self.assertEqual(ws.app.session.source_name, "measurements.csv")
        self.assertEqual(ws.app.session.level("stress_q1"), "ordinal", "levels come back too")


class MessageTests(Case):
    """No raw technical identifiers reach the screen."""

    def test_a_blocked_method_explains_itself_instead_of_showing_a_code(self):
        ws = self.workspace()
        ws.run(ws.app.load_sample("sample_scale.csv"))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        analyze = ws.app.pages["analyze"]
        # "Explore distributions" needs a quantitative variable.
        ws.run(analyze._execute("explore", {"variable": "stress_q1"}, {}, {}))
        message = analyze.message[0]
        self.assertNotIn("block.", message)
        self.assertIn("stress_q1", message)

    def test_guided_advice_and_the_engine_agree_on_measurement_levels(self):
        """Advice that offers a method must pass the method's own role checks."""
        import itertools
        import warnings

        from data_loader import load_dataset
        from workspace_methods import GOAL_ROLES, GOALS, METHODS, advise, role_problems
        from workspace_state import ResearchSession

        warnings.simplefilter("ignore")
        frame = load_dataset(EXAMPLES / "sample_ancova.csv")
        names = [c for c in frame.columns if c != "participant_id"]
        disagreements = []
        for levels in itertools.product(("scale", "ordinal", "nominal"), repeat=len(names)):
            session = ResearchSession()
            session.set_dataset(frame, "x")
            for name, level in zip(names, levels):
                session.confirm_level(name, level)
            for goal in GOALS:
                single = [r for r in GOAL_ROLES[goal] if not r.multiple]
                multiple = [r for r in GOAL_ROLES[goal] if r.multiple]
                for chosen in itertools.permutations(names, len(single)):
                    base = {r.key: n for r, n in zip(single, chosen)}
                    fillings = [{r.key: [n for n in names if n not in chosen][:max(
                        r.minimum or 1, 3)] for r in multiple}]
                    if any(r.optional for r in multiple):   # and without the optional ones
                        fillings.append({r.key: fillings[0][r.key] for r in multiple
                                         if not r.optional})
                    for filling in fillings:
                        advice = advise(goal, {**base, **filling}, session)
                        if advice.ready and advice.method:
                            problems = role_problems(METHODS[advice.method], advice.roles,
                                                     session)
                            if problems:
                                disagreements.append((goal, advice.method, problems[0][0]))
        self.assertEqual(disagreements[:5], [], f"{len(disagreements)} offered but blocked")


class StableRenderTests(Case):
    """The page is reconciled, not replaced, when it is re-rendered."""

    def test_the_page_container_keeps_its_key_across_renders(self):
        ws = self.workspace()
        self.groups_result(ws)
        first = ws.app.page_control
        ws.check("review-0", True)
        second = ws.app.page_control
        self.assertEqual(first.key, second.key)
        self.assertIn(second, ws.app._page_stack.controls)
        self.assertIsInstance(ws.app._page_stack, ft.Column)

    def test_buttons_that_change_kind_can_be_patched(self):
        """A reconciled button is patched when its kind changes ("Add to
        report" → "In report" → back). Flet 1.x breaks the control when a
        patch adds a key to a per-state colour map, so every kind of
        ``ft.Button`` uses the same keys (found by a real-browser check)."""
        import workspace_components as wc

        ui = ws_ui = self.workspace().app.ui
        del ws_ui
        styles = [wc._button_style(ui, kind=kind) for kind in ("primary", "secondary")]
        for name in ("bgcolor", "color", "overlay_color"):
            keys = [set(value) if isinstance(value, dict) else type(value).__name__
                    for value in (getattr(style, name) for style in styles)]
            self.assertEqual(keys[0], keys[1], name)
        self.assertEqual([s.side is not None for s in styles], [True, True])

    def test_typing_a_study_title_does_not_rebuild_the_page(self):
        ws = self.workspace()
        entry = self.groups_result(ws)
        ws.app.session.toggle_report(entry.id)
        ws.app.navigate("reports")
        with mock.patch.object(ws.app, "render", wraps=ws.app.render) as render:
            ws.type("reports-study-title", "Fictional study")
        self.assertEqual(render.call_count, 0)
        self.assertEqual(ws.find("reports-preview-text").value.splitlines()[0],
                         "Fictional study")


if __name__ == "__main__":
    unittest.main()
