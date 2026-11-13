"""Stage 36.8 (#62, Part 9): OPTIONAL live smoke test of the AI providers.

THIS TEST NEVER RUNS IN PUBLIC CI. Every test in it is skipped unless the
person running it sets, in their own shell:

    SRA_AI_LIVE_TEST=1
    SRA_AI_LIVE_OPENAI_KEY=…      and/or
    SRA_AI_LIVE_ANTHROPIC_KEY=…   and/or
    SRA_AI_LIVE_GEMINI_KEY=…      (their own, authorised key for that provider)

Optionally ``SRA_AI_LIVE_<PROVIDER>_MODEL`` names the model to ask (for
example ``SRA_AI_LIVE_OPENAI_MODEL``); otherwise the first listed model whose
ID has a part that suggests a small model ("nano", "mini", "haiku",
"flash-lite", "flash", "lite") is used, or the first listed one.

No workflow sets these variables (``test_stage368_ai_gate.PublicCiTests``
fails if one does), the program contains no key, and this test writes the
key nowhere: it is read from the environment and passed to the adapter.

For each provider with a key, the test lists the models the key can use
(``ai_providers.list_models``) and sends ONE tiny synthetic prompt through
the assistant's own path (``ai_assist.send``: the real HTTPS host, the audit
record in a temporary local log, the draft), with a reply limit of 512
tokens, under a local daily budget of 2,000 tokens. That is under 600 tokens
per provider — a fraction of a cent on a small model, but billed to the
key's owner.

    SRA_AI_LIVE_TEST=1 SRA_AI_LIVE_OPENAI_KEY=… \\
        python -m unittest discover -s tests -p "test_stage368_ai_live.py" -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ai_assist  # noqa: E402
import ai_context  # noqa: E402
import ai_providers as ap  # noqa: E402

LIVE = os.environ.get("SRA_AI_LIVE_TEST", "").strip() == "1"
SMALL = ("nano", "mini", "haiku", "flash-lite", "flash", "lite")
BUDGET = 2_000
REPLY_TOKENS = 512
PROMPT = ("This is a connection test of a statistics application; it contains no data. "
          "Reply with the single word: ready")


def live_key(provider: str) -> str:
    return os.environ.get(f"SRA_AI_LIVE_{provider.upper()}_KEY", "").strip()


def choose_model(provider: str, listed: list[str]) -> str:
    """The named model, else the first listed one with a whole ID part that
    suggests a small model ("mini" in "gpt-4o-mini", not in "gemini-…")."""
    named = os.environ.get(f"SRA_AI_LIVE_{provider.upper()}_MODEL", "").strip()
    if named:
        return named
    for fragment in SMALL:
        for model in listed:
            if f"-{fragment}-" in f"-{model.lower()}-":
                return model
    return listed[0]


@unittest.skipUnless(LIVE, "live AI providers: only with SRA_AI_LIVE_TEST=1 and a provider key "
                           "set by the person running it (never in public CI)")
class LiveProviderSmokeTests(unittest.TestCase):
    def smoke(self, provider: str) -> None:
        key = live_key(provider)
        if not key:
            self.skipTest(f"SRA_AI_LIVE_{provider.upper()}_KEY is not set")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            models = ap.list_models(provider, key, cache=root / "ai" / "models.json",
                                    refresh=True)
            listed = [model.id for model in models]
            self.assertTrue(listed, "the provider lists at least one text model")
            model = choose_model(provider, listed)
            setup = ai_context.Readiness(provider, model, BUDGET, "")
            request = ai_assist.Request("explain_method", PROMPT, (), (PROMPT,), 0, "student",
                                        "en", REPLY_TOKENS, False)
            budget = ap.Budget(ap.usage_path(root), BUDGET)
            try:
                draft = ai_assist.send(request, setup=setup, key=key, data_root=root,
                                       budget=budget)
            except ap.ProviderError as error:
                self.fail(f"{provider} {model}: {error.reason} ({error.detail}). If the model "
                          f"cannot answer a short text request, name another one in "
                          f"SRA_AI_LIVE_{provider.upper()}_MODEL.")
            self.assertTrue(draft.text.strip())
            self.assertTrue(draft.model, "the exact model that answered is reported")
            self.assertGreater(draft.tokens, 0)
            self.assertLessEqual(budget.used(), BUDGET)
            record = json.loads(ai_assist.local_log_path(root).read_text(encoding="utf-8")
                                .splitlines()[-1])
            self.assertEqual((record["provider"], record["model"], record["outcome"]),
                             (provider, draft.model, "ok"))
            # The key is in nothing this test produced.
            self.assertNotIn(key, repr(draft))
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertNotIn(key, path.read_text(encoding="utf-8", errors="replace"))
            print(f"\n{provider}: {len(listed)} text models; asked {model}; answered by "
                  f"{draft.model} with {draft.tokens} tokens: {draft.text[:60]!r}",
                  file=sys.stderr)

    def test_openai(self):
        self.smoke("openai")

    def test_anthropic(self):
        self.smoke("anthropic")

    def test_gemini(self):
        self.smoke("gemini")


if __name__ == "__main__":
    unittest.main()
