"""Stage 35 (#43): Settings -> AI providers, with a fake credential store
and a fake provider (no key leaves the test, nothing goes on the network)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import ai_providers as ap  # noqa: E402
import secret_store  # noqa: E402
from workspace_harness import Workspace  # noqa: E402

KEY = "sk-test-settings-1234567890"


def texts(ws, data: str) -> str:
    return " ".join(c.value for c in ws.controls(ws.find(data))
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


class AiProvidersCardTests(unittest.TestCase):
    def setUp(self):
        self.stored = {}
        fake = mock.Mock(set=lambda t, s: self.stored.__setitem__(t, s),
                         get=lambda t: self.stored.get(t),
                         remove=lambda t: self.stored.pop(t, None) is not None)
        patcher = mock.patch.object(secret_store, "backend", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ws = Workspace()
        self.addCleanup(self.ws.close)
        self.ws.app.navigate("settings")

    def test_connect_a_provider_with_a_key_and_choose_a_model(self):
        ws = self.ws
        self.assertIn("AI is off until you connect a provider", texts(ws, "settings-ai-providers"))
        ws.choose("ai-provider", "anthropic")
        ws.type("ai-key", KEY)
        ws.click("ai-save-key")
        self.assertEqual(self.stored, {"StatisticalResearchAssistant/ai/anthropic": KEY})
        self.assertIn("A key for Anthropic is stored", texts(ws, "ai-key-state"))
        models = [ap.Model("claude-test-1", "Claude Test"), ap.Model("claude-test-2", "Claude Two")]
        with mock.patch.object(ap, "list_models", return_value=models) as listed:
            ws.click("ai-test")
        self.assertEqual(listed.call_args.args[:2], ("anthropic", KEY))
        self.assertIn("Connected: 2 text models available.", texts(ws, "ai-message"))
        ws.choose("ai-model", "claude-test-2")
        settings = json.loads((ws.app.project_root.parent / "ai" / "settings.json").read_text())
        self.assertEqual(settings, {"provider": "anthropic", "model": "claude-test-2", "daily_tokens": 0})
        self.assertNotIn(KEY, json.dumps(settings), "the key is never in a settings file")
        ws.click("ai-remove-key")
        self.assertEqual(self.stored, {})

    def test_a_typed_model_id_and_a_refused_key(self):
        ws = self.ws
        ws.type("ai-manual-model", "gpt-future-model")
        ws.click("ai-use-model")
        self.assertIn("Model in use: gpt-future-model", texts(ws, "ai-model-set"))
        ws.type("ai-key", KEY)
        ws.click("ai-save-key")
        with mock.patch.object(ap, "list_models", side_effect=ap.ProviderError("bad_key")):
            ws.click("ai-test")
        self.assertIn("The provider refused the key.", texts(ws, "ai-message"))


if __name__ == "__main__":
    unittest.main()
