"""Stage 34.5 (issue #32): guided analysis separates exploring a variable
from testing a hypothesis, and reaches ANCOVA as "compare groups adjusted
for a covariate", with the design reasons shown. Fictional data only."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from workspace_harness import Workspace  # noqa: E402
from workspace_methods import advise  # noqa: E402
from workspace_state import ResearchSession  # noqa: E402


def ancova_session() -> ResearchSession:
    from data_loader import load_dataset

    session = ResearchSession()
    session.set_dataset(load_dataset(ROOT / "examples" / "sample_ancova.csv"), "sample_ancova.csv")
    session.accept_suggestions()
    return session


class AdviceTests(unittest.TestCase):
    def test_a_covariate_turns_the_comparison_into_ancova(self):
        session = ancova_session()
        plain = advise("compare", {"outcome": "wellbeing", "group": "group"}, session)
        self.assertEqual(plain.method, "omnibus")
        adjusted = advise("compare", {"outcome": "wellbeing", "group": "group",
                                      "covariates": ["baseline_score"]}, session)
        self.assertTrue(adjusted.ready)
        self.assertEqual(adjusted.method, "ancova")
        self.assertEqual(adjusted.roles, {"outcome": "wellbeing", "group": "group",
                                          "covariates": ["baseline_score"]})
        keys = [key for key, _ in adjusted.reasons]
        self.assertIn("why.ancova_adjusted", keys)
        self.assertIn("why.ancova_design", keys, "why the design matters is said")
        self.assertIn("unadjusted", [a.note.split(".")[-1] for a in adjusted.alternatives])

    def test_adjusting_an_ordinal_outcome_is_explained_not_run(self):
        session = ancova_session()
        session.confirm_level("wellbeing", "ordinal")
        advice = advise("compare", {"outcome": "wellbeing", "group": "group",
                                    "covariates": ["baseline_score"]}, session)
        self.assertFalse(advice.ready)
        self.assertEqual(advice.blockers[0][0], "block.adjust_outcome")

    def test_exploring_is_not_a_hypothesis_test(self):
        from workspace_text import T

        session = ancova_session()
        advice = advise("describe", {"variable": "wellbeing", "group": "group"}, session)
        self.assertEqual(advice.method, "explore")
        self.assertIn("tests no hypothesis", T["why.explore"][0])
        self.assertIn("No hypothesis is tested", T["goal.describe.body"][0])

    def test_the_method_never_depends_on_a_normality_test(self):
        """Same design, same levels: a skewed and a symmetric outcome get the
        same recommendation (no Shapiro-Wilk p decides)."""
        rng = np.random.default_rng(20261106)
        group = np.repeat(["A", "B"], 40)
        picks = []
        for outcome in (rng.normal(50, 10, 80), rng.lognormal(3, 1.2, 80)):
            session = ResearchSession()
            session.set_dataset(pd.DataFrame({"score": outcome, "group": group}), "x")
            session.confirm_level("score", "scale")
            session.confirm_level("group", "nominal")
            picks.append(advise("compare", {"outcome": "score", "group": "group"}, session))
        self.assertEqual([(p.method, p.options) for p in picks],
                         [(picks[0].method, picks[0].options)] * 2)


class GuidedAncovaJourneyTests(unittest.TestCase):
    def test_a_novice_reaches_ancova_from_compare_groups(self):
        from workspace_methods import run_method

        ws = Workspace()
        self.addCleanup(ws.close)
        ws.run(ws.app.load_sample("sample_ancova.csv"))
        ws.check("data-accept-confirm", True)
        ws.click("data-accept")
        ws.app.navigate("analyze")
        ws.click("goal-compare")
        ws.check("role-outcome-wellbeing")
        ws.choose("role-group", "group")
        ws.check("role-covariates-baseline_score", True)
        self.assertEqual(ws.find("guided-method").value.split(" ")[0], "ANCOVA")
        self.assertTrue(ws.has_text("This is a hypothesis test, not an exploration"))
        self.assertTrue(ws.find("guided-run").disabled, "the design is confirmed first")
        confirmations = ws.find_all("design-confirm-")
        self.assertTrue(confirmations)
        for control in confirmations:
            ws.check(control.data, True)
        self.assertFalse(ws.find("guided-run").disabled)
        ws.click("guided-run")
        self.assertTrue(ws.app.session.results, ws.app.pages["analyze"].message)
        entry = ws.app.session.results[-1]
        self.assertEqual(ws.app.route, "results")
        direct = run_method("ancova", ws.app.session, {"outcome": "wellbeing", "group": "group",
                                                       "covariates": ["baseline_score"]},
                            {"mode": "ancova"}, {"model": True})
        self.assertEqual(entry.run.report, direct.report, "the engine's numbers, unchanged")


if __name__ == "__main__":
    unittest.main()
