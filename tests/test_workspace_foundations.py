"""Stage 33 foundations: design tokens, localization, advisor and route map."""

from __future__ import annotations

import os
from pathlib import Path
import re
import string
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("MPLBACKEND", "Agg")

import workspace_tokens as tk  # noqa: E402
from workspace_text import LANGS, PLURALS, T, count_text, plural_index, t  # noqa: E402


class TokenTests(unittest.TestCase):
    def test_text_pairs_meet_wcag_aa_in_both_themes(self):
        for mode, palette in tk.PALETTES.items():
            for fg, bg in tk.TEXT_PAIRS:
                ratio = tk.contrast_ratio(getattr(palette, fg), getattr(palette, bg))
                self.assertGreaterEqual(ratio, 4.5, f"{mode}: {fg} on {bg} = {ratio:.2f}")
            for fg, bg in tk.UI_PAIRS:
                ratio = tk.contrast_ratio(getattr(palette, fg), getattr(palette, bg))
                self.assertGreaterEqual(ratio, 3.0, f"{mode}: {fg} on {bg} = {ratio:.2f}")

    def test_type_scale_and_sizes_follow_the_specification(self):
        sizes = [token[0] for token in (tk.TYPE_DISPLAY, tk.TYPE_TITLE_L, tk.TYPE_TITLE_M,
                                        tk.TYPE_TITLE_S, tk.TYPE_BODY_L, tk.TYPE_BODY,
                                        tk.TYPE_LABEL, tk.TYPE_CAPTION)]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertGreaterEqual(min(sizes), tk.MIN_TEXT_SIZE)
        self.assertTrue(14 <= tk.TYPE_BODY[0] <= 16)
        self.assertTrue(20 <= tk.TYPE_TITLE_M[0] <= 28 and tk.TYPE_DISPLAY[0] <= 28)
        self.assertTrue(220 <= tk.SIDEBAR_EXPANDED <= 248)
        self.assertGreaterEqual(tk.CONTROL_HEIGHT, 40)
        self.assertTrue(56 <= tk.CONTEXT_BAR_HEIGHT <= 64)
        for value in (tk.SPACE_2, tk.SPACE_4, tk.SPACE_5, tk.SPACE_6, tk.SPACE_8):
            self.assertEqual(value % 8, 0)

    def test_themes_are_built_from_tokens(self):
        for mode in ("light", "dark"):
            theme = tk.build_theme(mode)
            self.assertEqual(theme.color_scheme.primary, tk.palette(mode).accent)
            self.assertEqual(theme.color_scheme.surface, tk.palette(mode).surface)


class TextTests(unittest.TestCase):
    def test_every_key_has_three_languages_with_the_same_placeholders(self):
        formatter = string.Formatter()
        for key, values in T.items():
            self.assertEqual(len(values), 3, key)
            fields = [{f for _, f, _, _ in formatter.parse(v) if f} for v in values]
            for language, value, names in zip(LANGS, values, fields):
                self.assertTrue(value.strip(), f"{key}/{language} is empty")
                self.assertEqual(names, fields[0], f"{key}/{language} placeholders differ")

    def test_headings_are_not_all_caps(self):
        for key, values in T.items():
            for value in values:
                letters = re.sub(r"[^A-Za-zĀ-žА-я]", "", value)
                if len(letters) > 4:
                    self.assertFalse(letters.isupper(), f"{key}: {value}")

    def test_plural_rules(self):
        self.assertEqual([plural_index("ru", n) for n in (1, 2, 5, 11, 21, 22, 25)],
                         [0, 1, 2, 2, 0, 1, 2])
        self.assertEqual([plural_index("lv", n) for n in (0, 1, 2, 11, 21)], [2, 0, 1, 1, 0])
        self.assertEqual(count_text("en", 1, "rows"), "1 row")
        self.assertEqual(count_text("ru", 3, "questions"), "3 вопроса")
        self.assertEqual(count_text("lv", 21, "rows"), "21 rinda")
        for noun, forms in PLURALS.items():
            self.assertEqual(len(forms["en"]), 2)
            self.assertEqual(len(forms["lv"]), 3)
            self.assertEqual(len(forms["ru"]), 3)

    def test_every_engine_confirmation_and_option_label_is_translated(self):
        from workspace_methods import METHODS
        from workspace_text import LABELS

        for spec in METHODS.values():
            for confirmation in spec.confirmations:
                self.assertIn(confirmation.label, LABELS, confirmation.label)
            for option in spec.options:
                self.assertIn(option.label, LABELS, option.label)

    def test_unknown_key_is_visible_and_values_format(self):
        self.assertEqual(t("en", "missing.key"), "missing.key")
        self.assertIn("5", t("lv", "context.levels_pending", count=5))


class AdvisorTests(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        from workspace_state import ResearchSession

        self.session = ResearchSession()
        rows = 24
        self.session.set_dataset(pd.DataFrame({
            "participant_id": range(1, rows + 1),
            "group": ["A", "B"] * (rows // 2),
            "arm": ["x", "y", "z"] * (rows // 3),
            "score": [float(v % 7) + 0.5 for v in range(rows)],
            "likert": [v % 5 + 1 for v in range(rows)],
            "t1": [v % 5 + 1 for v in range(rows)],
            "t2": [(v + 1) % 5 + 1 for v in range(rows)],
            "t3": [(v + 2) % 5 + 1 for v in range(rows)],
            "passed": [v % 2 for v in range(rows)],
            "hours": [v * 0.7 for v in range(rows)],
            **{f"{base}_{copy}": [(v + shift) % 5 + 1 for v in range(rows)]
               for copy in "bcd" for shift, base in enumerate(("t1", "t2", "t3", "l"))},
        }), "synthetic.csv")
        for name, level in {"group": "nominal", "arm": "nominal", "score": "scale",
                            "likert": "ordinal", "t1": "ordinal", "t2": "ordinal",
                            "t3": "ordinal", "passed": "nominal", "hours": "scale"}.items():
            self.session.confirm_level(name, level)
        for name in self.session.variables:
            if "_" in name and name != "participant_id":
                self.session.confirm_level(name, "ordinal")

    def advise(self, goal, **selection):
        from workspace_methods import advise

        return advise(goal, selection, self.session)

    def test_decisions_follow_design_and_confirmed_levels(self):
        cases = [
            (("compare", {"outcome": "likert", "group": "group"}), ("groups", "mannwhitney")),
            (("compare", {"outcome": "score", "group": "group"}), ("groups", "welch")),
            (("compare", {"outcome": "likert", "group": "arm"}), ("omnibus", "kruskal")),
            (("compare", {"outcome": "score", "group": "arm"}), ("omnibus", "welch")),
            (("compare", {"outcome": "passed", "group": "group"}), ("chi", None)),
            (("change", {"measures": ["t1", "t2"]}), ("paired", "wilcoxon")),
            (("change", {"measures": ["t1", "t2", "t3"]}), ("repeated", "friedman")),
            (("relate", {"x": "likert", "y": "score"}), ("correlation", "spearman")),
            (("relate", {"x": "hours", "y": "score"}), ("correlation", "pearson")),
            (("associate", {"a": "group", "b": "arm"}), ("chi", None)),
            (("predict", {"outcome": "passed", "predictors": ["hours"]}), ("logistic", None)),
            (("predict", {"outcome": "score", "predictors": ["hours"]}), ("regression", None)),
            (("predict", {"outcome": "score", "predictors": ["group", "hours"]}), ("ancova", None)),
            # Stage 36.3: α, ω and every item's statistics in one result.
            (("scale", {"items": ["t1", "t2", "t3"]}), ("item_diagnostics", None)),
            (("scale", {"items": ["t1", "t2", "t3", "likert", "t1_b", "t2_b", "t3_b",
                                  "l_b", "t1_c", "t2_c", "t3_c", "l_c", "t1_d"]}),
             ("item_diagnostics", None)),
            (("structure", {"items": ["t1", "t2", "t3"]}), ("factor", None)),
            (("describe", {"variable": "score", "group": "group"}), ("explore", None)),
            (("describe", {"variable": "group"}), ("descriptive", None)),
        ]
        for (goal, selection), (method, option) in cases:
            advice = self.advise(goal, **selection)
            self.assertTrue(advice.ready, (goal, selection, advice.blockers))
            self.assertEqual(advice.method, method, (goal, selection))
            if option:
                self.assertEqual(advice.options.get("method"), option, (goal, selection))
            self.assertTrue(advice.reasons)

    def test_quantitative_outcomes_always_offer_the_rank_alternative(self):
        advice = self.advise("compare", outcome="score", group="group")
        self.assertIn(("groups", {"method": "mannwhitney"}),
                      [(a.method, a.options) for a in advice.alternatives])

    def test_advice_never_depends_on_the_observed_values(self):
        before = self.advise("compare", outcome="score", group="group")
        self.session.df["score"] = self.session.df["score"] ** 3  # strongly skewed
        after = self.advise("compare", outcome="score", group="group")
        self.assertEqual((before.method, before.options), (after.method, after.options))

    def test_engine_item_limits_are_known_before_running(self):
        too_few = self.advise("scale", items=["t1", "t2"])
        self.assertEqual(too_few.blockers[0], ("block.need_items", {"count": 3}))
        many = [n for n in self.session.variables if n.startswith(("t", "l_"))][:13]
        structure = self.advise("structure", items=many)
        self.assertEqual(structure.blockers[0], ("block.max_items", {"count": 12}))

    def test_blockers_for_unconfirmed_identifier_and_duplicate_variables(self):
        self.session.confirm_level("score", "unknown")
        advice = self.advise("compare", outcome="score", group="group")
        self.assertFalse(advice.ready)
        self.assertEqual(advice.blockers[0][0], "design.confirm_level")
        advice = self.advise("compare", outcome="participant_id", group="group")
        self.assertEqual(advice.blockers[0][0], "block.identifier")
        advice = self.advise("relate", x="hours", y="hours")
        self.assertEqual(advice.blockers[0][0], "block.same_variable")
        advice = self.advise("compare", outcome="likert", group="hours")
        self.assertEqual(advice.blockers[0][0], "block.group_quantitative")

    def test_engine_confirmations_are_still_enforced(self):
        from workspace_methods import run_method

        with self.assertRaises(ValueError):
            run_method("groups", self.session, {"outcome": "likert", "group": "group"},
                       {"method": "mannwhitney"}, {})
        run = run_method("groups", self.session, {"outcome": "likert", "group": "group"},
                         {"method": "mannwhitney"}, {"independent": True})
        self.assertEqual(run.section, "groups")


class ImportGateTests(unittest.TestCase):
    def test_low_confidence_items_block_until_compared_with_the_source(self):
        from dataclasses import replace

        from import_session import ImportSession
        from synthetic_documents import connectedness_text_pdf

        session = ImportSession()
        session.open(connectedness_text_pdf(), "two_versions.pdf")
        instrument = session.instrument
        questions = list(instrument.questions)
        questions[2] = replace(questions[2], confidence="low")
        session.review = replace(session.review, instruments=(
            replace(instrument, questions=tuple(questions)), *session.instruments[1:]))
        session.checks = {"version": True, "rights": True, "items": True}
        blocked = [b for b in session.blockers() if "low-confidence" in b]
        self.assertEqual(len(blocked), 1)
        self.assertIn(str(questions[2].number), blocked[0])
        session.mark_reviewed(2)
        self.assertFalse([b for b in session.blockers() if "low-confidence" in b])
        # Issue #31: confirmations are independent. Reviewing a scale does not
        # withdraw the item comparisons or the version/rights/count checks.
        scheme = session.instrument.schemes[0]
        session.review_scale(scheme.id, labels=list(scheme.labels), codes=list(scheme.codes),
                             reverse_items=[], structure=True)
        self.assertEqual(session.reviewed, {2})
        self.assertTrue(session.checks["version"] and session.checks["rights"])
        # Another instrument (version) of the document starts over.
        session.select(1)
        self.assertEqual(session.reviewed, set())
        self.assertFalse(any(session.checks.values()))


class RouteMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ux_inventory

        cls.inventory = ux_inventory.collect_inventory()

    def test_every_classic_screen_menu_command_and_action_has_a_destination(self):
        import workspace_routes as routes

        for screen in self.inventory["screens"]:
            self.assertIn(screen["key"], routes.SCREENS, screen["key"])
        for group in self.inventory["menu"]:
            for command in group["commands"]:
                self.assertIn((group["group"], command), routes.MENU, (group, command))
        for action in self.inventory["actions"]:
            self.assertIn(action, routes.ACTIONS, action)

    def test_destinations_exist_in_the_workspace(self):
        import workspace_routes as routes
        from workspace_methods import METHODS
        from workspace_shell import AREAS

        known = set(AREAS) | {"settings", "help", "questionnaires/import", "data#prepare"}
        for mapping in (routes.SCREENS, routes.MENU, routes.ACTIONS):
            for route, status, _ in mapping.values():
                self.assertIn(status, {"workspace", "hosted", "partial", "classic", "retired"})
                if route.startswith("analyze/all/"):
                    self.assertIn(route.rsplit("/", 1)[1], METHODS, route)
                else:
                    self.assertIn(route, known, route)

    def test_all_classic_analysis_areas_are_in_the_method_catalog(self):
        import workspace_routes as routes
        from workspace_methods import METHODS

        analysis = [s["key"] for s in self.inventory["screens"]
                    if s["key"] not in {"home", "dataset", "preparation", "survey"}]
        self.assertEqual(len(analysis), 13)
        for key in analysis:
            for method in routes.SCREEN_METHODS[key]:
                self.assertEqual(METHODS[method].section, key)
        # Stage 36 adds batch analyses that have no classic screen.
        self.assertEqual({m.section for m in METHODS.values()} - set(analysis),
                         {"batch_correlation", "batch_groups"})
        self.assertLessEqual(set(analysis), {m.section for m in METHODS.values()})


if __name__ == "__main__":
    unittest.main()
