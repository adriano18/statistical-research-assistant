"""Optional researcher profile and project-scoped AI context permissions
(Stage 34, part C). Synthetic data only; no network is used anywhere."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import socket
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import ai_context  # noqa: E402
from project_store import ProjectStore  # noqa: E402
from researcher_profile import (  # noqa: E402
    ProfileError, ResearcherProfile, delete_profile, load_profile, profile_path, save_profile,
)
from workspace_harness import Workspace  # noqa: E402

EXAMPLES = ROOT / "examples"


class TempCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.path = profile_path(self.base)


class ProfileStorageTests(TempCase):
    def test_the_profile_is_optional_and_round_trips(self):
        self.assertTrue(load_profile(self.path).empty)
        self.assertFalse(self.path.exists())
        profile = ResearcherProfile(display_name="  Ilze  ", study_level="master",
                                    research_field="Educational psychology",
                                    experience="some", language="lv", explanations="detailed")
        saved = save_profile(self.path, profile)
        self.assertEqual(saved.display_name, "Ilze")
        self.assertEqual(load_profile(self.path), saved)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["format"], 1)
        self.assertEqual(set(data["profile"]), {"display_name", "study_level", "research_field",
                                                "experience", "language", "explanations"})
        # Saving an empty profile keeps no file at all.
        save_profile(self.path, ResearcherProfile())
        self.assertFalse(self.path.exists())

    def test_values_outside_the_offered_choices_or_personal_identifiers_are_refused(self):
        for profile in (ResearcherProfile(study_level="professor"),
                        ResearcherProfile(display_name="ilze@example.org"),
                        ResearcherProfile(research_field="contact: someone@uni.example.lv"),
                        ResearcherProfile(display_name="x" * 81),
                        ResearcherProfile(display_name="two\nlines")):
            with self.subTest(profile=profile), self.assertRaises(ProfileError):
                save_profile(self.path, profile)
        self.assertFalse(self.path.exists())

    def test_a_damaged_or_newer_file_never_stops_the_application(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertTrue(load_profile(self.path).empty)
        self.path.write_text(json.dumps({"format": 9, "profile": {
            "experience": "experienced", "study_level": "unknown-level", "orcid": "0000",
            "display_name": 42}}), encoding="utf-8")
        loaded = load_profile(self.path)
        self.assertEqual(loaded.experience, "experienced")
        self.assertEqual(loaded.study_level, "")           # not offered here: ignored
        self.assertEqual(loaded.display_name, "")          # wrong type: ignored

    def test_deleting_the_profile_leaves_every_project_untouched(self):
        store = ProjectStore(self.base / "projects")
        info = store.create("Kept")
        save_profile(self.path, ResearcherProfile(experience="new"))
        before = self.path.read_bytes()
        with store.open(info.id) as project:        # projects never write into the profile
            project.add_question("Does it stay?")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertTrue(delete_profile(self.path))
        self.assertFalse(delete_profile(self.path))
        self.assertEqual([p.title for p in store.list()], ["Kept"])
        with store.open(info.id) as project:
            self.assertEqual(project.questions()[0]["text"], "Does it stay?")


class AiContextTests(TempCase):
    def setUp(self):
        super().setUp()
        self.store = ProjectStore(self.base / "projects")
        self.first = self.store.create("First")
        self.second = self.store.create("Second")

    def test_every_source_is_off_and_no_request_can_be_made_without_a_provider(self):
        """Stage 36: the assistant is usable only when a provider, a model and
        the researcher's key are set up; otherwise every request is refused."""
        not_set_up = "No AI provider is set up: connect a provider with your own key and " \
                     "choose a model in Settings."
        with self.store.open(self.first.id) as project:
            self.assertEqual(ai_context.permissions(project),
                             {key: False for key in ai_context.SOURCE_KEYS})
            ai_context.allow(project, "dictionary", True, remote=True)
            reasons = ai_context.check_request(project, ["dictionary"], remote=False)
            no_model = ai_context.check_request(
                project, ["dictionary"], remote=False,
                available=ai_context.Readiness("openai", "", 0, "no_model"))
            ready = ai_context.check_request(
                project, ["dictionary"], remote=False,
                available=ai_context.Readiness("openai", "gpt-test-1", 0, ""))
        self.assertFalse(hasattr(ai_context, "AI_AVAILABLE"), "no global switch any more")
        self.assertEqual(reasons, [not_set_up])
        self.assertEqual(no_model, [not_set_up])
        self.assertEqual(ready, [])

    def test_readiness_needs_a_model_and_a_key_in_the_os_store(self):
        import ai_providers
        import secret_store

        stored = {}
        fake = mock.Mock(get=lambda target: stored.get(target))
        root = self.base / "data"
        with mock.patch.object(secret_store, "backend", return_value=fake):
            self.assertEqual(ai_context.readiness(root).problem, "no_key")
            stored["StatisticalResearchAssistant/ai/anthropic"] = "sk-test-0123456789"
            ai_providers.save_settings(root, {"provider": "anthropic", "model": "",
                                              "daily_tokens": 0})
            self.assertEqual(ai_context.readiness(root).problem, "no_model")
            ai_providers.save_settings(root, {"provider": "anthropic", "model": "claude-test-1",
                                              "daily_tokens": 500})
            setup = ai_context.readiness(root)
        self.assertTrue(setup.ready)
        self.assertEqual((setup.provider, setup.model, setup.daily_tokens, setup.provider_name),
                         ("anthropic", "claude-test-1", 500, "Anthropic"))
        broken = mock.Mock(get=mock.Mock(side_effect=RuntimeError("keychain locked")))
        with mock.patch.object(secret_store, "backend", return_value=broken):
            self.assertEqual(ai_context.readiness(root).problem, "no_store")
        with mock.patch.object(secret_store, "_BACKEND", None), \
                mock.patch.object(secret_store, "_Keyring", side_effect=ImportError("none")), \
                mock.patch.object(secret_store.os, "name", "posix"):
            self.assertEqual(ai_context.readiness(root).problem, "no_store")

    def test_rules_a_future_assistant_must_pass(self):
        with self.store.open(self.first.id) as project:
            def check(sources, remote):
                return ai_context.check_request(project, sources, remote=remote, available=True)

            self.assertEqual(check(["results"], True), ["Not allowed for this project: results"])
            ai_context.allow(project, "results", True, remote=True)
            self.assertEqual(check(["results"], True), [])
            # Data rows to a remote provider need the anonymity statement first.
            with self.assertRaises(ai_context.ContextRefused):
                ai_context.allow(project, "raw_data", True, remote=True)
            ai_context.allow(project, "raw_data", True, remote=False)    # a local model
            self.assertEqual(check(["raw_data"], False), [])
            self.assertTrue(check(["raw_data"], True))
            project.set_data_anonymous(True)
            self.assertEqual(check(["raw_data"], True), [])
            # Withdrawing the statement withdraws data rows as well.
            ai_context.state_anonymous(project, False)
            self.assertFalse(ai_context.permissions(project)["raw_data"])
            # Without an open project no project source can be sent.
            self.assertEqual([r.code for r in ai_context.refusals(None, ["results"], remote=True,
                                                                  available=True)],
                             ["no_project"])
            self.assertEqual(ai_context.refusals(None, [], remote=True, available=True), [])
            kinds = [event["kind"] for event in project.events()]
            self.assertIn("ai_permission", kinds)
            self.assertIn("data_anonymous", kinds)
            with self.assertRaises(ai_context.ContextRefused):
                ai_context.allow(project, "everything", True, remote=False)
        with self.store.open(self.second.id) as other:   # another project: nothing allowed
            self.assertFalse(any(ai_context.permissions(other).values()))

    def test_permissions_travel_with_the_project_backup(self):
        with self.store.open(self.first.id) as project:
            ai_context.allow(project, "overview", True, remote=False)
        backup = self.store.export_package(self.first.id, self.base / "first.sra")
        elsewhere = ProjectStore(self.base / "elsewhere")
        restored, _ = elsewhere.import_package(backup)
        with elsewhere.open(restored.id) as project:
            self.assertTrue(ai_context.permissions(project)["overview"])

    def test_previews_show_exactly_what_would_be_shared_and_use_no_network(self):
        from data_loader import load_dataset
        from workspace_state import ResearchSession

        session = ResearchSession()
        session.set_dataset(load_dataset(EXAMPLES / "sample_scale.csv"), "sample_scale.csv")
        session.confirm_level("stress_q1", "ordinal")
        profile = ResearcherProfile(display_name="Ilze", study_level="doctoral",
                                    experience="new", explanations="detailed")

        def no_network(*args, **kwargs):
            raise AssertionError("a preview must not open a network connection")

        with self.store.open(self.first.id) as project, \
                mock.patch.object(socket, "socket", no_network):
            project.add_question("Does stress differ between groups?")
            overview = ai_context.preview("overview", project=project)
            dictionary = ai_context.preview("dictionary", session=session)
            rows = ai_context.preview("raw_data", session=session)
            mine = ai_context.preview("profile", profile=profile)
        self.assertIn("Research question: Does stress differ between groups?", overview)
        self.assertIn("stress_q1: ordinal", dictionary)
        self.assertIn("group: unknown", dictionary)
        self.assertNotIn(",", dictionary, "names and levels only, no values")
        self.assertEqual(len(rows.splitlines()), 1 + ai_context.PREVIEW_ROWS + 1)
        self.assertTrue(rows.endswith("more rows"))
        self.assertIn("explanations: detailed", mine)
        self.assertNotIn("doctoral", mine)
        self.assertNotIn("Ilze", mine)


class ProfileWorkspaceTests(TempCase):
    def setUp(self):
        super().setUp()
        remember = mock.patch("workspace_shell.WorkspaceApp._remember_file")
        remember.start()
        self.addCleanup(remember.stop)

    def workspace(self, **kwargs) -> Workspace:
        ws = Workspace(root=self.base, **kwargs)
        self.addCleanup(ws.close)
        return ws

    def test_the_profile_is_filled_saved_and_applied_after_a_restart(self):
        ws = self.workspace()
        ws.app.navigate("settings")
        self.assertTrue(ws.find("settings-profile"))
        ws.type("profile-name", "Ilze")
        ws.choose("profile-experience", "experienced")
        ws.choose("profile-explanations", "detailed")
        ws.choose("profile-language", "lv")
        ws.click("profile-save")
        self.assertEqual(load_profile(ws.app.profile_path).experience, "experienced")
        self.assertEqual(ws.app.session.language, "lv")
        ws.close()

        again = self.workspace()
        self.assertEqual(again.app.session.language, "lv")
        self.assertTrue(again.app.pages["home"].hide_onboarding)
        again.app.navigate("home")
        with self.assertRaises(AssertionError):
            again.find("home-how")
        # "Detailed" opens the interpretation of each result.
        shutil.copy(EXAMPLES / "sample_scale.csv", self.base / "data.csv")
        again.run(again.app.load_path(str(self.base / "data.csv")))
        again.app.session.confirm_level("stress_q1", "ordinal")
        again.app.session.confirm_level("group", "nominal")
        again.run(again.app.pages["analyze"]._execute(
            "groups", {"outcome": "stress_q1", "group": "group"}, {}, {"independent": True}))
        self.assertTrue(again.find("result-interpretation-section").expanded)
        # Switching the language keeps the profile's language equal to it.
        again.app.set_language("ru")
        self.assertEqual(load_profile(again.app.profile_path).language, "ru")

    def test_a_refused_value_is_explained_and_nothing_is_saved(self):
        ws = self.workspace()
        ws.app.navigate("settings")
        ws.type("profile-name", "ilze@example.org")
        ws.click("profile-save")
        self.assertTrue(ws.find("profile-feedback"))
        self.assertTrue(ws.has_text("e-mail"))
        self.assertFalse(ws.app.profile_path.exists())

    def test_deleting_the_profile_from_settings(self):
        save_profile(self.path, ResearcherProfile(experience="new"))
        ws = self.workspace()
        ws.app.navigate("settings")
        ws.click("profile-delete")
        self.assertFalse(self.path.exists())
        self.assertTrue(ws.app.profile.empty)
        self.assertTrue(ws.has_text("No project was changed"))

    def test_the_ai_card_says_it_is_not_available_and_previews_the_open_project(self):
        ws = self.workspace()
        ws.app.navigate("settings")
        self.assertTrue(ws.find("ai-unavailable"))
        self.assertTrue(ws.has_text("Open a project on Home"))
        ws.app.projects.create("Preview me")
        ws.run(ws.app.load_sample("sample_scale.csv"))
        ws.app.navigate("settings")
        for key in ai_context.SOURCE_KEYS:
            self.assertTrue(ws.find(f"ai-status-{key}"))
            self.assertTrue(ws.find(f"ai-preview-{key}"))
        self.assertIn("stress_q1", ws.find("ai-preview-dictionary").value)
        self.assertTrue(ws.has_text("Off"))
        self.assertFalse(ws.has_text("Allowed"))

    def test_the_ai_card_allows_sources_per_project_and_rows_need_the_statement(self):
        """Stage 36: the switches the assistant's permissions link opens."""
        ws = self.workspace()
        ws.app.projects.create("Switches")
        ws.run(ws.app.load_sample("sample_scale.csv"))
        ws.app.navigate("settings")
        project = ws.app.projects.project
        ws.check("ai-allow-overview", True)
        self.assertTrue(ai_context.permissions(project)["overview"])
        self.assertTrue(ws.find("ai-allow-raw_data").disabled, "rows need the statement first")
        self.assertTrue(ws.has_text("First state below that this project’s data rows identify nobody."))
        ws.check("ai-anonymous", True)
        self.assertTrue(project.data_anonymous)
        ws.check("ai-allow-raw_data", True)
        self.assertTrue(ai_context.permissions(project)["raw_data"])
        ws.check("ai-anonymous", False)          # withdrawing the statement withdraws rows
        self.assertFalse(project.data_anonymous)
        self.assertFalse(ai_context.permissions(project)["raw_data"])
        self.assertTrue(ws.find("ai-allow-raw_data").disabled)
        kinds = [event["kind"] for event in project.events()]
        self.assertIn("ai_permission", kinds)
        self.assertIn("data_anonymous", kinds)
        ws.check("ai-allow-overview", False)
        self.assertFalse(any(ai_context.permissions(project).values()))

    def test_settings_are_translated(self):
        for language, title in (("lv", "Pētnieka profils (pēc izvēles)"),
                                ("ru", "Профиль исследователя (необязательно)")):
            with self.subTest(language=language):
                ws = self.workspace(language=language)
                ws.app.navigate("settings")
                self.assertTrue(ws.has_text(title))
                ws.close()


if __name__ == "__main__":
    unittest.main()
