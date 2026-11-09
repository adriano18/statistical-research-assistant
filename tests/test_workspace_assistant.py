"""Stage 36 (spec §12): the AI assistant on the Results page, driven through
the real Flet controls with a fake credential store and the local mock of
each provider's API. Synthetic data only; no key leaves the test and nothing
goes on the network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import socket
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import ai_assist  # noqa: E402
import ai_context  # noqa: E402
import ai_providers as ap  # noqa: E402
import secret_store  # noqa: E402
from test_ai_providers import MockProviders  # noqa: E402
from workspace_harness import Workspace  # noqa: E402

KEY = "sk-test-panel-0123456789abcdef"
EXAMPLES = ROOT / "examples"
GROUPS = {"outcome": "stress_q1", "group": "group"}
# A reply with one statistic the engine reported (U) and one it did not (p = .001).
FABRICATED = "The groups differ (U = 139.500, p = .001), so the hypothesis is supported."


def texts(ws, data: str) -> str:
    found = []
    for control in ws.controls(ws.find(data)):
        if isinstance(control, ft.Text):
            found.append(control.value or "".join(s.text or "" for s in control.spans or []))
        elif isinstance(control, (ft.Button, ft.TextButton)) and isinstance(control.content, str):
            found.append(control.content)
    return " ".join(found)


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class AssistantCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.data = self.base / "fictional_scale.csv"
        shutil.copy(EXAMPLES / "sample_scale.csv", self.data)
        self.stored = {}
        fake = mock.Mock(set=lambda t, s: self.stored.__setitem__(t, s),
                         get=lambda t: self.stored.get(t),
                         remove=lambda t: self.stored.pop(t, None) is not None)
        for patcher in (mock.patch.object(secret_store, "backend", return_value=fake),
                        mock.patch.object(ap, "_retry_after", return_value=0.0),
                        mock.patch("workspace_shell.WorkspaceApp._remember_file")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.mock = MockProviders()
        self.addCleanup(self.mock.close)

    def workspace(self, **kwargs) -> Workspace:
        ws = Workspace(root=self.base, **kwargs)
        self.addCleanup(ws.close)
        ws.app.pages["results"].assistant.http = {"base": self.mock.base}
        return ws

    def connect(self, ws, *, daily_tokens: int | None = None):
        """Settings → AI providers: save the (fake) key, list the provider's
        models from the mock, choose one — exactly as a researcher does."""
        ws.app.navigate("settings")
        ws.choose("ai-provider", "openai")
        ws.type("ai-key", KEY)
        ws.click("ai-save-key")
        real = ap.list_models

        def from_mock(provider, key, **kwargs):
            return real(provider, key, base=self.mock.base, **kwargs)

        with mock.patch.object(ap, "list_models", side_effect=from_mock):
            ws.click("ai-test")
        ws.choose("ai-model", "gpt-test-1")
        if daily_tokens is not None:
            ws.type("ai-budget", str(daily_tokens))
        self.mock.requests.clear()          # listing the models is not an assistant request

    def analyse(self, ws):
        self.assertTrue(ws.run(ws.app.load_path(str(self.data))))
        ws.app.session.confirm_level("stress_q1", "ordinal")
        ws.app.session.confirm_level("group", "nominal")
        entry = ws.run(ws.app.pages["analyze"]._execute("groups", GROUPS, {},
                                                        {"independent": True}))
        self.assertIsNotNone(entry)
        ws.app.navigate("results")
        return entry

    def posts(self):
        return [r for r in self.mock.requests if r[0] == "POST"]

    def ai_events(self, ws):
        return [e["detail"] for e in ws.app.projects.project.events() if e["kind"] == "ai_request"]

    def send(self, ws):
        """Press Send; the preview on screen is what must go out."""
        previewed = ws.find("ai-preview-text").value
        ws.click("ai-send")
        return previewed


class AssistantFlowTests(AssistantCase):
    def test_connect_analyse_preview_send_check_and_use_as_a_note(self):
        ws = self.workspace()
        ws.app.projects.create("Fictional sleep study")
        project = ws.app.projects.project
        project.add_question("Does stress differ between the two groups?")
        self.connect(ws)
        entry = self.analyse(ws)
        report, rows = entry.run.report, entry.run.evidence().rows
        # The panel is on the result, ready, and has sent nothing yet.
        self.assertTrue(ws.find("ai-panel"))
        self.assertIn("Drafts from OpenAI", texts(ws, "ai-hint"))
        ws.choose("ai-task", "interpretation")
        self.assertIn("A draft paragraph for you to rewrite", texts(ws, "ai-task-detail"))
        # Only sources the project allows are offered.
        self.assertEqual(ws.find_all("ai-source-overview"), [])
        self.assertIn("Project overview", texts(ws, "ai-not-allowed"))
        ws.click("ai-permissions")
        self.assertEqual(ws.app.route, "settings")
        ws.check("ai-allow-overview", True)
        ws.app.navigate("results")
        ws.check("ai-source-overview", True)
        self.assertTrue(ws.find("ai-source-result").value and ws.find("ai-source-result").disabled)
        # The preview: provider, exact model, size, rows and the exact text.
        self.assertEqual(texts(ws, "ai-preview-to"),
                         "To: OpenAI (api.openai.com) · model gpt-test-1")
        exact = ws.find("ai-preview-text").value
        self.assertIn(f"Size: {len(exact)} characters, about {len(exact) // 3} tokens.",
                      texts(ws, "ai-preview-size"))
        self.assertEqual(texts(ws, "ai-preview-rows"),
                         "Data rows: 0 — no row of the dataset is sent.")
        self.assertIn("This result (always included), Project overview",
                      texts(ws, "ai-preview-sources"))
        self.assertIn("Research question: Does stress differ between the two groups?", exact)
        self.assertIn("Report:\n" + report.strip(), exact)
        self.assertNotIn("1,A,4,4,4,3", exact, "no data row is in the request")
        self.assertEqual(texts(ws, "ai-send"), "Send to OpenAI (gpt-test-1)")
        self.assertEqual(self.mock.requests, [], "nothing is sent before Send is pressed")
        # Send: the request is exactly the preview; the reply is a draft.
        self.mock.text = FABRICATED
        previewed = self.send(ws)
        self.assertEqual(len(self.posts()), 1)
        self.assertEqual(self.posts()[0][3]["input"], previewed)
        self.assertEqual(self.posts()[0][3]["model"], "gpt-test-1")
        self.assertIn("Draft — not verified", texts(ws, "ai-draft"))
        self.assertIn("gpt-test-1-2026-01-01", texts(ws, "ai-draft-meta"))
        flagged = [s.text for s in ws.find("ai-draft-text").spans if s.style is not None]
        self.assertEqual(flagged, [".001"], "the invented p value is highlighted")
        self.assertIn("Not found in what was sent — check before any use: .001",
                      texts(ws, "ai-unverified"))
        self.assertEqual(ws.find("ai-copy").action.data, FABRICATED)
        # Use it as the researcher's note: labelled as an unverified AI draft.
        ws.click("ai-use-note")
        note = ws.find("result-notes").value
        self.assertTrue(note.startswith("[AI draft — OpenAI, gpt-test-1-2026-01-01, "))
        self.assertIn("Unverified: check every statement and number against the result.]", note)
        self.assertIn("[Numbers not found in what was sent: .001]", note)
        self.assertTrue(note.endswith(FABRICATED))
        self.assertIn("unverified", ws.find("result-notes").label)
        self.assertTrue(ws.find("result-interpretation-section").expanded)
        self.assertTrue(ws.find("ai-use-note").disabled, "added once")
        self.assertIn("Added to your interpretation note", texts(ws, "ai-notice"))
        # The result itself is unchanged; the audit names no text.
        self.assertEqual(entry.run.report, report)
        self.assertEqual(entry.run.evidence().rows, rows)
        self.assertEqual(self.ai_events(ws), [{
            "provider": "openai", "model": "gpt-test-1-2026-01-01",
            "sources": ["overview", "result"], "tokens": 160, "outcome": "ok",
            "task": "interpretation"}])
        log = json.dumps(project.events())
        for text in (KEY, FABRICATED, previewed[:200], "Does stress differ"):
            self.assertNotIn(text, log)

    def test_copy_and_discard_keep_the_result_untouched(self):
        ws = self.workspace()
        self.connect(ws)
        entry = self.analyse(ws)
        self.send(ws)
        ws.click("ai-copy")
        self.assertIn("Draft copied.", texts(ws, "ai-notice"))
        ws.click("ai-discard")
        self.assertEqual(ws.find_all("ai-draft"), [])
        self.assertEqual(ws.app.pages["results"].notes.get(entry.id, ""), "")

    def test_without_a_project_only_the_result_is_sent_and_logged_locally(self):
        ws = self.workspace()
        self.connect(ws)
        self.analyse(ws)
        self.assertIn("No project is open, so only this result’s own text can be sent",
                      texts(ws, "ai-no-project"))
        self.assertEqual(ws.find_all("ai-source-dictionary"), [])
        self.assertIn("a log on this computer", texts(ws, "ai-consent"))
        previewed = self.send(ws)
        self.assertTrue(ws.find("ai-draft"))
        line = ai_assist.local_log_path(self.base).read_text(encoding="utf-8").splitlines()[-1]
        entry = json.loads(line)
        self.assertEqual((entry["provider"], entry["model"], entry["sources"], entry["tokens"],
                          entry["outcome"]),
                         ("openai", "gpt-test-1-2026-01-01", ["result"], 160, "ok"))
        self.assertNotIn(previewed[:120], line)
        self.assertNotIn(self.mock.text, line)

    def test_a_typed_question_is_previewed_before_it_can_be_sent(self):
        ws = self.workspace()
        self.connect(ws)
        self.analyse(ws)
        ws.choose("ai-task", "hypotheses")
        ws.type("ai-question", "Is stress higher in group B?")
        ws.click("ai-send")      # the preview did not show the question yet
        self.assertEqual(self.mock.requests, [])
        self.assertIn("changed after the preview", texts(ws, "ai-notice"))
        self.assertIn("<question>\nIs stress higher in group B?\n</question>",
                      ws.find("ai-preview-text").value)
        previewed = self.send(ws)
        self.assertEqual(self.posts()[0][3]["input"], previewed)


class RefusalTests(AssistantCase):
    def test_without_a_provider_the_panel_explains_and_nothing_is_sent(self):
        ws = self.workspace()
        ws.app.projects.create("No provider")
        self.analyse(ws)
        self.assertIn("No AI provider is connected", texts(ws, "ai-not-ready"))
        self.assertIn("Settings → AI providers", texts(ws, "ai-not-ready"))
        self.assertEqual(ws.find_all("ai-send"), [])
        ws.click("ai-open-settings")
        self.assertEqual(ws.app.route, "settings")
        self.assertTrue(ws.find("ai-unavailable"))
        # A key without a model is not enough either.
        ws.type("ai-key", KEY)
        ws.click("ai-save-key")
        ws.app.navigate("results")
        self.assertIn("no model is chosen", texts(ws, "ai-not-ready"))
        self.assertEqual(self.mock.requests, [])
        # The rest of the result works as before.
        self.assertTrue(ws.find("result-table"))
        self.assertTrue(ws.find("export-docx"))

    def test_a_source_the_project_does_not_allow_is_never_sent(self):
        ws = self.workspace()
        ws.app.projects.create("Permissions")
        project = ws.app.projects.project
        self.connect(ws)
        entry = self.analyse(ws)
        panel = ws.app.pages["results"].assistant
        panel.state(entry.id).sources.add("dictionary")      # not allowed: ignored
        ws.app.render()
        self.assertNotIn("CONTEXT (dictionary)", ws.find("ai-preview-text").value)
        # A permission withdrawn after the preview (elsewhere): nothing is sent.
        ai_context.allow(project, "overview", True, remote=True)
        ws.app.render()
        ws.check("ai-source-overview", True)
        ai_context.allow(project, "overview", False, remote=True)
        ws.click("ai-send")
        self.assertEqual(self.mock.requests, [])
        self.assertIn("changed after the preview", texts(ws, "ai-notice"))
        # Allowed again: it is not silently chosen again.
        ai_context.allow(project, "overview", True, remote=True)
        ws.app.render()
        self.assertFalse(ws.find("ai-source-overview").value)
        # Withdrawn while the request was being prepared: refused with a reason.
        ws.check("ai-source-overview", True)
        real_send = ai_assist.send

        def withdraw_then_send(*args, **kwargs):
            ai_context.allow(project, "overview", False, remote=True)
            return real_send(*args, **kwargs)

        with mock.patch.object(ai_assist, "send", side_effect=withdraw_then_send):
            ws.click("ai-send")
        self.assertEqual(self.mock.requests, [])
        self.assertIn("Not sent: this project does not allow Project overview.",
                      texts(ws, "ai-error"))
        ws.click("ai-error-permissions")
        self.assertEqual(ws.app.route, "settings")
        self.assertEqual(self.ai_events(ws), [])

    def test_data_rows_need_the_anonymity_statement(self):
        ws = self.workspace()
        ws.app.projects.create("Rows")
        project = ws.app.projects.project
        self.connect(ws)
        entry = self.analyse(ws)
        ai_context.allow(project, "raw_data", True, remote=False)    # allowed, no statement
        ws.app.render()
        self.assertTrue(ws.find("ai-source-raw_data").disabled)
        ws.app.pages["results"].assistant.state(entry.id).sources.add("raw_data")
        ws.app.render()
        self.assertEqual(texts(ws, "ai-preview-rows"),
                         "Data rows: 0 — no row of the dataset is sent.")
        with self.assertRaises(ai_context.ContextRefused) as refused:
            ai_assist.send(ai_assist.build_request("explain_table", result="x",
                                                   sources=("raw_data",), project=project,
                                                   session=ws.app.session),
                           setup=ai_context.readiness(self.base), key=KEY, project=project,
                           base=self.mock.base)
        self.assertEqual(refused.exception.codes, ("rows_not_anonymous",))
        # With the statement, rows can be chosen and the preview counts them.
        ws.app.navigate("settings")
        ws.check("ai-anonymous", True)
        ws.check("ai-allow-raw_data", True)
        ws.app.navigate("results")
        self.assertFalse(ws.find("ai-source-raw_data").disabled)
        self.assertFalse(ws.find("ai-source-raw_data").value, "chosen only by a new tick")
        ws.check("ai-source-raw_data", True)
        self.assertEqual(texts(ws, "ai-preview-rows"),
                         "Data rows: 5 — the first rows of the dataset, exactly as in the text below.")
        self.assertIn("CONTEXT (raw_data)", ws.find("ai-preview-text").value)
        self.assertEqual(self.mock.requests, [])


class ErrorTests(AssistantCase):
    def ready(self, **connect):
        ws = self.workspace()
        ws.app.projects.create("Errors")
        self.connect(ws, **connect)
        self.analyse(ws)
        return ws

    def test_each_failure_is_explained_with_a_next_step(self):
        ws = self.ready()
        cases = (
            ([401], "OpenAI refused the API key", "ai-error-settings", "bad_key", 1),
            ([429] * (ap.RETRIES + 1), "still refused after several tries (rate limit). Wait a "
             "minute and try again.", None, "rate_limited", ap.RETRIES + 1),
            ([503] * (ap.RETRIES + 1), "did not answer properly", None, "unavailable",
             ap.RETRIES + 1),
        )
        for faults, message, action, outcome, attempts in cases:
            with self.subTest(outcome=outcome):
                self.mock.requests.clear()
                self.mock.faults = list(faults)
                self.send(ws)
                self.assertIn(message, texts(ws, "ai-error"))
                self.assertEqual(ws.find_all("ai-draft"), [])
                self.assertEqual(len(self.posts()), attempts)
                self.assertEqual(self.ai_events(ws)[0]["outcome"], outcome)
                if action:
                    ws.click(action)
                    self.assertEqual(ws.app.route, "settings")
                    ws.app.navigate("results")

    def test_offline(self):
        ws = self.ready()
        ws.app.pages["results"].assistant.http = {"base": f"http://127.0.0.1:{closed_port()}"}
        self.send(ws)
        self.assertIn("OpenAI could not be reached", texts(ws, "ai-error"))
        self.assertIn("everything else works offline", texts(ws, "ai-error"))
        self.assertTrue(ws.find("result-table"), "the result is still on screen")

    def test_the_daily_limit(self):
        ws = self.ready(daily_tokens=100)
        self.send(ws)
        message = texts(ws, "ai-error")
        self.assertIn("This request would go over today’s token limit: 0 of 100 are used", message)
        self.assertIn("Nothing was sent.", message)
        self.assertEqual(self.mock.requests, [])
        self.assertEqual(self.ai_events(ws), [])

    def test_a_request_can_be_cancelled_while_waiting(self):
        ws = self.ready()
        self.mock.faults = ["slow"]           # the provider takes its time
        send = ws.find("ai-send").on_click

        async def scenario():
            waiting = asyncio.ensure_future(send(SimpleNamespace(control=None, data=None)))
            for _ in range(500):
                if self.posts():
                    break
                await asyncio.sleep(0.01)
            self.assertIn("Waiting for OpenAI (gpt-test-1)…", texts(ws, "ai-progress"))
            self.assertTrue(ws.find("ai-send").disabled)
            ws.click("ai-cancel")
            self.assertIn("Cancelled.", texts(ws, "ai-error"))
            await waiting

        asyncio.run(scenario())
        self.assertIn("Cancelled. No draft is kept", texts(ws, "ai-error"))
        self.assertEqual(ws.find_all("ai-draft"), [], "the late reply is discarded")
        self.assertEqual(ws.find_all("ai-progress"), [])
        self.assertFalse(ws.find("ai-send").disabled)
        self.assertEqual(self.ai_events(ws)[0]["outcome"], "cancelled")


class LanguageTests(AssistantCase):
    def test_the_panel_speaks_latvian_and_russian(self):
        expected = {
            "lv": ("MI asistents (pēc izvēles)", "Sūtīt uz OpenAI (gpt-test-1)",
                   "Saņēmējs: OpenAI (api.openai.com) · modelis gpt-test-1",
                   "Datu rindas: 0 — neviena datu kopas rinda netiek nosūtīta.",
                   "Melnraksts — nav pārbaudīts", "Nav atrasti nosūtītajā tekstā",
                   "Izmantot kā manu interpretācijas piezīmi",
                   "Pētnieka interpretācija (pēc izvēles, nepārbaudīta)"),
            "ru": ("ИИ-помощник (необязательно)", "Отправить в OpenAI (gpt-test-1)",
                   "Получатель: OpenAI (api.openai.com) · модель gpt-test-1",
                   "Строки данных: 0 — ни одна строка набора данных не отправляется.",
                   "Черновик — не проверен", "Не найдены в отправленном тексте",
                   "Использовать как мою заметку об интерпретации",
                   "Интерпретация исследователя (необязательно, не проверена)"),
        }
        for language, (title, send, to, rows, draft, unverified, use, note) in expected.items():
            with self.subTest(language=language):
                ws = self.workspace(language=language)
                self.connect(ws)
                self.analyse(ws)
                self.assertTrue(ws.has_text(title))
                self.assertEqual(texts(ws, "ai-send"), send)
                self.assertEqual(texts(ws, "ai-preview-to"), to)
                self.assertEqual(texts(ws, "ai-preview-rows"), rows)
                self.assertIn({"lv": "Answer in Latvian", "ru": "Answer in Russian"}[language],
                              ws.find("ai-preview-text").value)
                self.mock.text = FABRICATED
                self.send(ws)
                self.assertIn(draft, texts(ws, "ai-draft"))
                self.assertIn(unverified, texts(ws, "ai-unverified"))
                self.assertEqual(texts(ws, "ai-use-note"), use)
                self.assertEqual(ws.find("result-notes").label, note)
                ws.click("ai-use-note")
                self.assertTrue(ws.find("result-notes").value.startswith(
                    {"lv": "[MI melnraksts — OpenAI", "ru": "[Черновик ИИ — OpenAI"}[language]))
                self.mock.faults = [401]
                ws.click("ai-discard")
                self.send(ws)
                self.assertIn({"lv": "OpenAI noraidīja API atslēgu",
                               "ru": "OpenAI отклонил API-ключ"}[language], texts(ws, "ai-error"))
                ws.close()

    def test_not_connected_in_russian(self):
        ws = self.workspace(language="ru")
        self.analyse(ws)
        self.assertIn("ИИ-провайдер не подключён", texts(ws, "ai-not-ready"))
        self.assertTrue(ws.has_text("Не подключён. Всё остальное работает без него."))


if __name__ == "__main__":
    unittest.main()
