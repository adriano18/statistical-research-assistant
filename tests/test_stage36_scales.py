"""Stage 36.3: scale groups and item diagnostics against independent oracles.

Oracles are computed here, not through the application's code paths:
α, its Feldt interval and the corrected item–total correlations written
out from sums; α if item deleted recomputed by hand; pingouin called
directly; ``pandas.qcut``/``pandas.cut`` and ``numpy.linspace`` for the
group bounds and counts; SciPy for skewness and kurtosis. ω is checked
against the validated ``omega_analysis`` engine on the same complete
cases. Tolerances are in docs/STAGE36_STATISTICAL_VALIDATION.md.
Synthetic, invented data only.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
import item_diagnostics as idg  # noqa: E402
import scale_groups as sg  # noqa: E402
from omega_analysis import analyze_omega  # noqa: E402
from stat_results import StructuredResult  # noqa: E402

TIGHT = 1e-12


def items_frame() -> pd.DataFrame:
    return pd.read_csv(fx.fixture(fx.ITEMS_CSV))


def totals_frame() -> pd.DataFrame:
    return pd.read_csv(fx.fixture(fx.CSV))


def variance(values: np.ndarray) -> float:
    return float(((values - values.sum() / values.size) ** 2).sum() / (values.size - 1))


def alpha_by_hand(x: np.ndarray) -> float:
    k = x.shape[1]
    items = sum(variance(x[:, j]) for j in range(k))
    return k / (k - 1) * (1 - items / variance(x.sum(axis=1)))


def pearson_by_hand(a: np.ndarray, b: np.ndarray) -> float:
    da, db = a - a.sum() / a.size, b - b.sum() / b.size
    return float((da * db).sum() / np.sqrt((da * da).sum() * (db * db).sum()))


@contextmanager
def quiet():
    """statsmodels 0.15 returns loadings with a zero imaginary part; the
    validated omega engine casts them to real. Keep the test log readable."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", np.exceptions.ComplexWarning)
        yield


class ItemsVersusTotalsTests(unittest.TestCase):
    """D5: item responses are told apart from total or derived scores."""

    def test_the_55_row_scale_totals_are_not_item_responses(self):
        frame = totals_frame()
        problems = {p.name: p for p in idg.item_response_problems(frame, list(frame.columns))}
        for name in (*fx.SCALES, "UCLA", "Age"):
            self.assertTrue(problems[name].looks_like_total, name)
            self.assertIn("many_values", problems[name].reasons)
            self.assertIn("wide_range", problems[name].reasons)
        for name in ("UCLA_Level", "Sex"):
            self.assertNotIn(name, problems, "a few codes look like item responses")
        self.assertFalse(problems["Code"].looks_like_total, "text codes are not totals")
        self.assertIn("not_numeric", problems["Code"].reasons)

    def test_the_item_fixture_items_are_item_responses_and_its_total_is_not(self):
        frame = items_frame()
        self.assertEqual(idg.item_response_problems(frame, list(fx.ITEMS)), [])
        (total,) = idg.item_response_problems(frame, [fx.ITEM_TOTAL])
        self.assertTrue(total.looks_like_total)
        self.assertEqual(total.distinct, frame[fx.ITEM_TOTAL].nunique())
        self.assertEqual((total.minimum, total.maximum),
                         (frame[fx.ITEM_TOTAL].min(), frame[fx.ITEM_TOTAL].max()))
        self.assertIn("total or derived score", total.text)

    def test_each_threshold_on_its_own(self):
        frame = pd.DataFrame({
            "rating_0_10": [v % 11 for v in range(40)],           # 11 codes, range 10: an item
            "codes_0_11": [v % 12 for v in range(40)],            # 12 codes, range 11
            "two_codes_far_apart": [1, 20] * 20,                  # range 19
            "mean_score": [1.5, 2.25, 3.0, 4.75] * 10,            # decimals
            "words": ["often", "never"] * 20,
            "empty": [None] * 40,
            "ignored_unknown_column_is_not_listed": range(40),
        })
        problems = {p.name: p for p in idg.item_response_problems(
            frame, ["rating_0_10", "codes_0_11", "two_codes_far_apart", "mean_score", "words",
                    "empty", "not_a_column"])}
        self.assertNotIn("rating_0_10", problems)
        self.assertEqual(problems["codes_0_11"].reasons, ("many_values", "wide_range"))
        self.assertEqual(problems["two_codes_far_apart"].reasons, ("wide_range",))
        self.assertEqual(problems["mean_score"].reasons, ("non_integer",))
        self.assertEqual(problems["words"].reasons, ("not_numeric", "no_values"))
        self.assertEqual(problems["empty"].reasons, ("no_values",))
        self.assertNotIn("not_a_column", problems)
        self.assertTrue(all(problems[n].looks_like_total
                            for n in ("codes_0_11", "two_codes_far_apart", "mean_score")))
        self.assertFalse(problems["words"].looks_like_total or problems["empty"].looks_like_total)

    def session(self, frame: pd.DataFrame, levels: dict):
        from workspace_state import ResearchSession

        session = ResearchSession()
        session.set_dataset(frame, "synthetic.csv")
        for name, level in levels.items():
            session.confirm_level(name, level)
        return session

    def test_the_advice_offers_no_coefficient_for_totals_or_a_total_among_items(self):
        import workspace_methods as wm

        totals = self.session(totals_frame(), {name: "scale" for name in fx.SCALES})
        advice = wm.advise("scale", {"items": list(fx.SCALES[:4])}, totals)
        self.assertIsNone(advice.method)
        self.assertFalse(advice.alternatives)
        self.assertEqual(advice.blockers, (("block.totals_not_items",
                                            {"names": ", ".join(fx.SCALES[:4])}),))
        frame = items_frame()
        levels = {**{item: "ordinal" for item in fx.ITEMS}, fx.ITEM_TOTAL: "scale"}
        items = self.session(frame, levels)
        mixed = wm.advise("scale", {"items": [*fx.ITEMS[:9], fx.ITEM_TOTAL]}, items)
        self.assertIsNone(mixed.method)
        self.assertEqual(mixed.blockers, (("block.total_among_items",
                                           {"names": fx.ITEM_TOTAL}),))
        genuine = wm.advise("scale", {"items": list(fx.ITEMS)}, items)
        self.assertTrue(genuine.ready, genuine.blockers)
        self.assertEqual(genuine.method, "omega")

    def test_the_explanation_is_in_three_languages_with_the_required_russian_text(self):
        from workspace_text import T, t

        english, latvian, russian = T["block.totals_not_items"]
        self.assertIn("Для анализа надёжности нужны отдельные ответы на пункты шкалы. "
                      "Сейчас доступен только суммарный показатель", russian)
        self.assertIn("Импортируйте", russian)
        self.assertIn("Import the item-level data", english)
        self.assertIn("Importējiet", latvian)
        for language in ("en", "lv", "ru"):
            for key in ("block.totals_not_items", "block.total_among_items"):
                self.assertIn("UCLA, Age", t(language, key, names="UCLA, Age"))

    def test_item_diagnostics_refuse_totals_unless_the_researcher_confirms(self):
        frame = totals_frame()
        with self.assertRaises(ValueError) as raised:
            idg.diagnose_items(frame, list(fx.SCALES[:4]), ci=False)
        self.assertIn("total or derived scores", str(raised.exception))
        with quiet():
            confirmed = idg.diagnose_items(frame, list(fx.SCALES[:4]), ci=False,
                                           items_confirmed=True)
        self.assertTrue(any("confirmed" in w for w in confirmed.warnings))
        # Four unrelated invented totals hardly share a factor: statsmodels warns
        # that some refits did not converge, and the result says so.
        unsettled = [row.name for row in confirmed.rows
                     if idg.NOT_CONVERGED in row.omega_if_deleted.note]
        if unsettled:
            self.assertTrue(any(idg.NOT_CONVERGED in w and unsettled[0] in w
                                for w in confirmed.warnings))


class ItemDiagnosticsOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._quiet = quiet()
        cls._quiet.__enter__()
        cls.frame = items_frame()
        cls.before = cls.frame.copy(deep=True)
        cls.items = list(fx.ITEMS)
        cls.result = idg.diagnose_items(cls.frame, cls.items, ci=True, resamples=0)
        cls.complete = cls.frame[cls.items].dropna()

    @classmethod
    def tearDownClass(cls):
        cls._quiet.__exit__(None, None, None)

    def test_nothing_in_the_data_is_changed(self):
        pd.testing.assert_frame_equal(self.frame, self.before)
        self.assertEqual(self.result.items, tuple(self.items), "no item was dropped")
        self.assertEqual([row.name for row in self.result.rows], self.items)

    def test_one_complete_sample(self):
        self.assertEqual(self.result.n_total, 200)
        self.assertEqual(self.result.n_complete, len(self.complete))
        self.assertEqual(self.result.n_complete, 192)
        for row in self.result.rows:
            self.assertEqual(row.n, 192)
            self.assertEqual(row.missing, int(self.frame[row.name].isna().sum()))
            self.assertAlmostEqual(row.missing_percent, 100 * row.missing / 200, places=12)

    def test_alpha_matches_the_formula_and_pingouin(self):
        import pingouin as pg

        x = self.complete.to_numpy(dtype=float)
        alpha = self.result.alpha
        self.assertAlmostEqual(alpha.value, alpha_by_hand(x), delta=TIGHT)
        self.assertAlmostEqual(alpha.value, pg.cronbach_alpha(data=self.complete)[0], delta=TIGHT)
        n, k = x.shape
        low = 1 - (1 - alpha.value) * stats.f.isf(0.025, n - 1, (n - 1) * (k - 1))
        high = 1 - (1 - alpha.value) * stats.f.isf(0.975, n - 1, (n - 1) * (k - 1))
        self.assertAlmostEqual(alpha.ci_low, low, delta=5e-4 + 1e-12)
        self.assertAlmostEqual(alpha.ci_high, high, delta=5e-4 + 1e-12)
        self.assertEqual((alpha.ci_low, alpha.ci_high), (round(low, 3), round(high, 3)))
        self.assertEqual(alpha.ci_level, 0.95)
        self.assertIn("Feldt", alpha.ci_method)

    def test_corrected_item_total_correlations_by_hand(self):
        x = self.complete.to_numpy(dtype=float)
        total = x.sum(axis=1)
        for j, row in enumerate(self.result.rows):
            self.assertAlmostEqual(row.item_total_r.value,
                                   pearson_by_hand(x[:, j], total - x[:, j]), delta=TIGHT)
            self.assertAlmostEqual(row.mean, x[:, j].sum() / x.shape[0], delta=TIGHT)
            self.assertAlmostEqual(row.sd, np.sqrt(variance(x[:, j])), delta=TIGHT)

    def test_alpha_if_deleted_by_recomputation(self):
        x = self.complete.to_numpy(dtype=float)
        for j, row in enumerate(self.result.rows):
            expected = alpha_by_hand(np.delete(x, j, axis=1))
            self.assertAlmostEqual(row.alpha_if_deleted.value, expected, delta=TIGHT)
            self.assertAlmostEqual(row.alpha_change.value, expected - self.result.alpha.value,
                                   delta=TIGHT)

    def test_omega_matches_the_validated_engine_on_the_same_complete_cases(self):
        full = analyze_omega(self.frame, self.items)
        self.assertAlmostEqual(self.result.omega.value, full.omega, delta=TIGHT)
        loadings = np.array([d.standardized_loading for d in full.diagnostics])
        uniqueness = np.array([d.uniqueness for d in full.diagnostics])
        by_formula = loadings.sum() ** 2 / (loadings.sum() ** 2 + uniqueness.sum())
        self.assertAlmostEqual(self.result.omega.value, by_formula, delta=TIGHT)
        for row, diagnostic in zip(self.result.rows, full.diagnostics):
            self.assertAlmostEqual(row.loading.value, diagnostic.standardized_loading, delta=TIGHT)
            self.assertAlmostEqual(row.item_total_r.value, diagnostic.corrected_item_rest_r,
                                   delta=TIGHT)
            rest = [item for item in self.items if item != row.name]
            refit = analyze_omega(self.complete[rest], rest).omega
            self.assertAlmostEqual(row.omega_if_deleted.value, refit, delta=TIGHT)
            self.assertAlmostEqual(row.omega_change.value, refit - full.omega, delta=TIGHT)
            self.assertIn("192 complete cases", row.omega_if_deleted.note)
        # Row 133 skipped ZEP01 only: a refit with its own listwise deletion
        # would use 193 respondents; the diagnostics keep the same 192.
        rest = self.items[1:]
        self.assertNotAlmostEqual(analyze_omega(self.frame, rest).omega,
                                  self.result.row("ZEP01").omega_if_deleted.value, places=12)

    def test_omega_states_its_model_assumptions(self):
        text = " ".join(self.result.omega_assumptions).lower()
        for phrase in ("unidimensional", "congeneric", "uncorrelated errors",
                       "maximum-likelihood"):
            self.assertIn(phrase, text)
        keys = [q.key for q in self.result.omega_fit]
        self.assertEqual(keys, ["largest_residual", "first_eigenvalue", "second_eigenvalue"])

    def test_distribution_diagnostics(self):
        for row in self.result.rows:
            values = self.complete[row.name].to_numpy(dtype=float)
            self.assertAlmostEqual(row.skewness.value, stats.skew(values, bias=False),
                                   delta=1e-10)
            self.assertAlmostEqual(row.kurtosis.value, stats.kurtosis(values, bias=False),
                                   delta=1e-10)
            self.assertEqual(row.categories_used, len(set(values)))
            self.assertEqual(row.categories_possible, 5)
            self.assertAlmostEqual(row.floor_percent, 100 * np.sum(values == 1) / values.size,
                                   delta=TIGHT)
            self.assertAlmostEqual(row.ceiling_percent, 100 * np.sum(values == 5) / values.size,
                                   delta=TIGHT)
        self.assertEqual((self.result.scale_min, self.result.scale_max), (1.0, 5.0))
        self.assertEqual((self.result.scale_min_source, self.result.scale_max_source),
                         ("observed", "observed"))
        floor = self.result.row(fx.FLOOR_ITEM)
        self.assertIn("floor", floor.flags)
        self.assertGreater(floor.floor_percent, 50)
        self.assertEqual([row.name for row in self.result.rows if "floor" in row.flags],
                         [fx.FLOOR_ITEM])
        self.assertTrue(any("observed in these items" in note for note in self.result.notes))

    def test_stated_codes_change_floor_ceiling_and_count_outside_values(self):
        frame = self.frame.copy()
        frame.loc[0, "ZEP03"] = 9                       # a missing-value code left in the data
        result = idg.diagnose_items(frame, self.items, scale_min=0, scale_max=6, ci=False)
        self.assertEqual((result.scale_min_source, result.scale_max_source), ("given", "given"))
        row = result.row("ZEP03")
        self.assertEqual(row.out_of_range, 1)
        self.assertIn("out_of_range", row.flags)
        self.assertEqual(row.categories_possible, 7)
        self.assertTrue(all(r.floor_percent == 0 for r in result.rows))
        self.assertTrue(any("outside the codes 0–6" in w for w in result.warnings))

    def test_reverse_keying_is_flagged_never_recoded(self):
        self.assertEqual(self.result.flagged_reverse, fx.REVERSE_ITEMS)
        for item in fx.REVERSE_ITEMS:
            row = self.result.row(item)
            self.assertLess(row.item_total_r.value, 0)
            self.assertLess(row.loading.value, 0)
            self.assertIn("possible_reverse", row.flags)
            self.assertIn("check the scoring key", row.notes[0])
        self.assertTrue(any("Possibly reverse-keyed" in w for w in self.result.warnings))
        documented = idg.diagnose_items(self.frame, self.items, reverse_keyed=fx.REVERSE_ITEMS,
                                        reverse_source="an invented confirmed key", ci=False)
        pd.testing.assert_frame_equal(self.frame, self.before)
        for item in fx.REVERSE_ITEMS:
            row = documented.row(item)
            self.assertEqual(row.recoding, "appears_not_recoded")
            self.assertEqual(row.flags, ("not_recoded",))
        recoded = self.frame.copy()
        for item in fx.REVERSE_ITEMS:
            recoded[item] = 6 - recoded[item]
        fixed = idg.diagnose_items(recoded, self.items, reverse_keyed=fx.REVERSE_ITEMS, ci=False)
        self.assertEqual(fixed.flagged_reverse, ())
        self.assertEqual([fixed.row(item).recoding for item in fx.REVERSE_ITEMS],
                         ["appears_recoded"] * 2)
        self.assertGreater(fixed.alpha.value, self.result.alpha.value)
        with self.assertRaises(ValueError):
            idg.diagnose_items(self.frame, self.items[:5], reverse_keyed=["ZEP08"], ci=False)

    def test_no_item_is_deleted_and_the_content_note_is_neutral(self):
        rising = [row.name for row in self.result.rows if row.alpha_change.value > 0]
        self.assertEqual(rising, list(fx.REVERSE_ITEMS))
        self.assertEqual(len(self.result.rows), 10)
        self.assertTrue(any("content validity" in note for note in self.result.notes))
        self.assertAlmostEqual(self.result.alpha.value,
                               alpha_by_hand(self.complete.to_numpy(dtype=float)), delta=TIGHT)

    def test_short_and_long_scales_say_why_a_value_is_missing(self):
        three = idg.diagnose_items(self.frame, self.items[:3], ci=False)
        for row in three.rows:
            self.assertEqual(row.alpha_if_deleted.status, "not_applicable")
            self.assertEqual(row.omega_if_deleted.status, "unavailable")
            self.assertIn("fewer than 3 items", row.omega_if_deleted.note)
            self.assertEqual(row.omega_change.status, "unavailable")
        frame = self.frame.copy()
        for extra in ("ZEP11", "ZEP12", "ZEP13"):
            frame[extra] = frame["ZEP01"].where(frame.index % 7 != 0, frame["ZEP02"])
        long = idg.diagnose_items(frame, [*self.items, "ZEP11", "ZEP12", "ZEP13"], ci=False)
        self.assertEqual(long.omega.status, "not_calculated")
        self.assertEqual(long.omega.text(), "Not calculated")
        self.assertTrue(all(row.omega_if_deleted.status == "not_calculated" for row in long.rows))
        self.assertTrue(all(row.loading.status == "not_calculated" for row in long.rows))
        small = idg.diagnose_items(self.complete.head(25), self.items, ci=False)
        self.assertEqual(small.omega.status, "unavailable")
        self.assertIn("at least 50 complete respondents", small.omega.note)
        self.assertTrue(small.alpha.ok)

    def test_the_omega_interval_is_the_reproducible_bootstrap(self):
        from omega_bootstrap import bootstrap_omega

        first = idg.diagnose_items(self.frame, self.items, ci=True, resamples=100, seed=5)
        again = idg.diagnose_items(self.frame, self.items, ci=True, resamples=100, seed=5)
        interval = bootstrap_omega(self.frame, self.items, n_resamples=100, seed=5)
        self.assertEqual((first.omega.ci_low, first.omega.ci_high),
                         (interval.lower, interval.upper))
        self.assertEqual(first.omega, again.omega)
        self.assertIn("100/100", first.omega.ci_method)
        self.assertIsNone(idg.diagnose_items(self.frame, self.items, ci=False).alpha.ci_low)
        with self.assertRaises(ValueError):
            idg.diagnose_items(self.frame, self.items, resamples=50)

    def test_results_survive_json_and_are_structured(self):
        again = idg.ItemDiagnostics.from_dict(json.loads(json.dumps(self.result.to_dict())))
        self.assertEqual(again, self.result)
        structured = self.result.structured()
        self.assertIsInstance(structured, StructuredResult)
        self.assertEqual(StructuredResult.from_dict(json.loads(json.dumps(structured.to_dict()))),
                         structured)
        self.assertEqual(structured.method_id, "item_diagnostics")
        self.assertEqual(structured.quantity("alpha").value, self.result.alpha.value)
        self.assertEqual(structured.quantity("item_total_r:ZEP04").value,
                         self.result.row("ZEP04").item_total_r.value)
        self.assertEqual(structured.quantity("skewness:ZEP06").value,
                         self.result.row("ZEP06").skewness.value)
        self.assertEqual(structured.sample["n_used"], 192)
        table = structured.tables[0]
        self.assertEqual(len(table.rows), 10)
        self.assertIn("possibly reverse-keyed", table.rows[3][-1])
        from result_store import from_json, to_json

        payload = to_json(self.result)
        self.assertEqual(payload["kind"], "item_diagnostics")
        self.assertEqual(from_json(json.loads(json.dumps(payload))), self.result)

    def test_the_chart_is_a_deterministic_png(self):
        before = self.result.to_dict()
        first = idg.make_item_diagnostics_chart(self.result)
        self.assertTrue(first.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(first, idg.make_item_diagnostics_chart(self.result))
        self.assertEqual(self.result.to_dict(), before)
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(first))
        self.assertGreater(image.size[0], 800)
        self.assertIn("ZEP04, ZEP08", image.info.get("Description", ""))
        three = idg.diagnose_items(self.frame, self.items[:3], ci=False)
        self.assertTrue(idg.make_item_diagnostics_chart(three).startswith(b"\x89PNG"))


class ConfirmedReverseKeysTests(unittest.TestCase):
    def candidate(self):
        from scientific_survey_import import (Candidate, InstrumentCandidate, ProposedScoring,
                                              ResponseScheme)

        rows = tuple(Candidate(n, {"key": key, "prompt": f"Invented calm statement {n}",
                                   "kind": "single_choice", "options": ["a", "b"],
                                   "required": False, "page": 1, "section": ""},
                               1, "", "review", scheme_id="s1")
                     for n, key in enumerate(fx.ITEMS, 1))
        labels = ("Never (invented)", "Rarely (invented)", "Sometimes (invented)",
                  "Often (invented)", "Always (invented)")
        scheme = ResponseScheme("s1", labels, labels, ("1", "2", "3", "4", "5"), "header", 1,
                                "invented legend", tuple(range(1, 11)), reverse_items=(4, 8))
        return InstrumentCandidate("Invented calm scale", rows, ProposedScoring(), (), 1,
                                   schemes=(scheme,)), labels

    def test_only_a_confirmed_review_yields_reverse_keys(self):
        from scientific_survey_import import draft_questions
        from shared_scales import review_scheme

        candidate, labels = self.candidate()
        proposed = idg.confirmed_reverse_keys(fx.ITEMS, instrument=candidate)
        self.assertEqual((proposed.items, proposed.confirmed), ((), False))
        self.assertIn("nothing is returned", proposed.note)
        coded = review_scheme(candidate, "s1", labels=labels, codes=("1", "2", "3", "4", "5"),
                              reverse_items=(4, 8), structure=True, numeric=True)
        self.assertEqual(idg.confirmed_reverse_keys(fx.ITEMS, instrument=coded).items, ())
        reviewed = review_scheme(candidate, "s1", labels=labels, codes=("1", "2", "3", "4", "5"),
                                 reverse_items=(4, 8), structure=True, numeric=True, reverse=True)
        keys = idg.confirmed_reverse_keys(fx.ITEMS, instrument=reviewed)
        self.assertEqual((keys.items, keys.confirmed), (fx.REVERSE_ITEMS, True))
        self.assertIn("Invented calm scale", keys.source)
        saved = idg.confirmed_reverse_keys(fx.ITEMS, questionnaire=draft_questions(reviewed))
        self.assertEqual(saved.items, fx.REVERSE_ITEMS)
        with quiet():
            result = idg.diagnose_items(items_frame(), list(fx.ITEMS), reverse_keyed=keys.items,
                                        reverse_source=keys.source, ci=False)
        self.assertEqual(result.reverse_keyed, fx.REVERSE_ITEMS)
        self.assertTrue(any(keys.source in note for note in result.notes))

    def test_nothing_confirmed_returns_nothing_and_says_so(self):
        from scientific_survey_import import draft_questions

        candidate, _ = self.candidate()
        unflagged = idg.confirmed_reverse_keys(fx.ITEMS, questionnaire=draft_questions(candidate))
        self.assertEqual((unflagged.items, unflagged.confirmed), ((), False))
        self.assertIn("does not confirm", unflagged.note)
        nothing = idg.confirmed_reverse_keys(fx.ITEMS)
        self.assertEqual((nothing.items, nothing.confirmed, nothing.source), ((), False, ""))
        self.assertIn("not known", nothing.note)
        codebook = {"title": "Invented codebook", "questions": [
            {"key": "ZEP04", "reverse_scored": True}, {"key": "other", "reverse_scored": True}]}
        partial = idg.confirmed_reverse_keys(["ZEP04", "ZEP05"], questionnaire=codebook)
        self.assertEqual(partial.items, ("ZEP04",))
        self.assertIn("Not in the questionnaire: ZEP05", partial.note)


def norm_claims(text: str) -> list[str]:
    """Sentences that mention norms without negating them."""
    sentences = re.split(r"(?<=[.;:])\s+", text)
    return [s for s in sentences if re.search(r"\bnorm", s, re.I)
            and not re.search(r"\bnot\b", s, re.I)]


class GroupRuleTests(unittest.TestCase):
    def documented(self, **changes):
        rule = sg.range_rule("documented", [
            ("Low", 20, 39, True, True), ("Moderate", 40, 59, True, True),
            ("High", 60, 80, True, True)], source="Invented Manual (2099), table 9")
        return replace(rule, **changes) if changes else rule

    def test_rules_survive_json(self):
        rules = [self.documented(),
                 sg.range_rule("custom", [("Below", None, 40, False, False),
                                          ("From 40", 40, None, True, False)], source="pilot"),
                 sg.quantile_rule(4), sg.quantile_rule(3, ("L", "M", "H"), closed="left"),
                 sg.equal_width_rule(3), sg.equal_width_rule(2, span=(20, 80))]
        for rule in rules:
            data = json.loads(json.dumps(rule.to_dict()))
            self.assertEqual(data["version"], sg.RULE_VERSION)
            self.assertEqual(sg.GroupRule.from_dict(data), rule)
            self.assertEqual(sg.GroupRule.from_dict({**data, "unknown_key": 1}), rule)
        with self.assertRaises(ValueError):
            sg.GroupRule.from_dict({**rules[0].to_dict(), "version": sg.RULE_VERSION + 1})

    def test_contiguous_rules_from_cut_points_have_no_gaps_or_overlaps(self):
        values = pd.Series([20, 39, 40, 59, 60, 80, 39.5], name="score")
        right = sg.contiguous_rule("documented", [39, 59], ("Low", "Moderate", "High"),
                                   lowest=20, highest=80, source="Invented Manual (2099)")
        self.assertEqual([r.text() for r in right.ranges], ["[20, 39]", "(39, 59]", "(59, 80]"])
        preview = sg.preview(values, right)
        self.assertEqual([g.n for g in preview.groups], [2, 3, 2])
        self.assertEqual(preview.warning_keys(), ("groups.small",) * 3)
        left = sg.contiguous_rule("custom", [40, 60], ("Low", "Moderate", "High"),
                                  closed="left")
        self.assertEqual([r.text() for r in left.ranges], ["< 40", "[40, 60)", "≥ 60"])
        self.assertEqual([g.n for g in sg.preview(values, left).groups], [3, 2, 2])
        for bad in (lambda: sg.contiguous_rule("custom", [60, 40], ("A", "B", "C")),
                    lambda: sg.contiguous_rule("custom", [40], ("A", "B", "C")),
                    lambda: sg.contiguous_rule("custom", [40], ("A", "B"), lowest=45),
                    lambda: sg.contiguous_rule("documented", [40], ("A", "B"))):
            with self.assertRaises(ValueError):
                bad()

    def test_invalid_rules_are_refused(self):
        rows = [("Low", 20, 39, True, True), ("High", 40, 80, True, True)]
        cases = [
            lambda: sg.range_rule("documented", rows, source=""),           # no source named
            lambda: sg.range_rule("custom", [rows[1], rows[0]]),             # not ascending
            lambda: sg.range_rule("custom", [("A", 1, 2, True, True), ("a", 3, 4, True, True)]),
            lambda: sg.range_rule("custom", [("A", 5, 5, True, False), ("B", 6, 9, True, True)]),
            lambda: sg.range_rule("custom", [("A", 9, 5, True, True), ("B", 10, 12, True, True)]),
            lambda: sg.range_rule("custom", [("A", None, 5, True, True), ("B", 6, 9, True, True)]),
            lambda: sg.range_rule("custom", [("Only", 1, 5, True, True)]),   # one group
            lambda: sg.quantile_rule(3, ("A", "B")),
            lambda: sg.quantile_rule(3, closed="both"),
            lambda: sg.GroupRule("quantile", ("A", "B"), k=2, span=(0, 1)),
            lambda: sg.equal_width_rule(2, span=(5, 5)),
            lambda: sg.GroupRule("median_split", ("A", "B"), k=2),
            lambda: sg.GroupRule("custom", ("A", "B"), (sg.GroupRange(0, 1, True, True),
                                                         sg.GroupRange(2, 3, True, True)), k=2),
        ]
        for index, case in enumerate(cases):
            with self.assertRaises(ValueError, msg=f"case {index}"):
                case()

    def test_the_wording_never_presents_thresholds_as_norms(self):
        frame = totals_frame()
        documented = sg.preview(frame["UCLA"], self.documented()).statement.text
        self.assertIn("as entered by the researcher", documented)
        self.assertIn("Invented Manual (2099), table 9", documented)
        self.assertIn("manual", documented.replace("Manual", ""))
        self.assertNotIn("norm", documented.lower())
        custom = sg.range_rule("custom", [("Lower", 20, 49, True, True),
                                          ("Higher", 50, 80, True, True)])
        for rule in (custom, sg.quantile_rule(3), sg.equal_width_rule(3),
                     sg.equal_width_rule(3, span=(20, 80))):
            result = sg.apply(frame, "UCLA", rule, "UCLA_groups")
            for text in (result.preview.statement.text, result.message):
                self.assertIn("not", text)
                self.assertRegex(text, r"\bnorms\b")
                self.assertEqual(norm_claims(text), [], text)
        self.assertIn("Researcher-defined", sg.preview(frame["UCLA"], custom).statement.text)
        quantile = sg.preview(frame["UCLA"], sg.quantile_rule(3)).statement.text
        self.assertIn("depend on this sample", quantile)
        self.assertIn("Data-derived", quantile)


class GroupPreviewAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.frame = totals_frame()
        self.original = self.frame.copy(deep=True)

    def test_quantile_groups_match_pandas_qcut(self):
        values = self.frame["UCLA"]
        for k in (2, 3, 4, 5):
            preview = sg.preview(values, sg.quantile_rule(k))
            expected = pd.qcut(values, k).value_counts(sort=False).tolist()
            self.assertEqual([g.n for g in preview.groups], expected, k)
            np.testing.assert_allclose(
                preview.cut_points, np.quantile(values, np.arange(1, k) / k), rtol=0, atol=1e-9)
            self.assertEqual(sum(g.n for g in preview.groups), 55)
            self.assertTrue(preview.groups[0].lower_inclusive)
            self.assertTrue(all(g.upper_inclusive for g in preview.groups))
            self.assertFalse(any(g.lower_inclusive for g in preview.groups[1:]))
        total = pd.read_csv(fx.fixture(fx.ITEMS_CSV))[fx.ITEM_TOTAL]
        for k in (3, 4):
            preview = sg.preview(total, sg.quantile_rule(k))
            self.assertEqual([g.n for g in preview.groups],
                             pd.qcut(total, k).value_counts(sort=False).tolist())
            self.assertEqual(preview.n_missing, 8)

    def test_equal_width_groups_use_numpy_edges(self):
        values = self.frame["UCLA"]
        for k in (2, 3, 4, 6):
            preview = sg.preview(values, sg.equal_width_rule(k))
            edges = np.linspace(values.min(), values.max(), k + 1)
            self.assertEqual([g.lower for g in preview.groups], list(edges[:-1]))
            self.assertEqual([g.upper for g in preview.groups], list(edges[1:]))
            x = values.to_numpy(dtype=float)
            by_hand = [int(np.sum((x >= edges[0]) & (x <= edges[1])))] + [
                int(np.sum((x > edges[i]) & (x <= edges[i + 1]))) for i in range(1, k)]
            self.assertEqual([g.n for g in preview.groups], by_hand)
            self.assertEqual(by_hand, pd.cut(values, k).value_counts(sort=False).tolist())
        fixed = sg.preview(values, sg.equal_width_rule(3, span=(20, 80)))
        self.assertEqual([(g.lower, g.upper) for g in fixed.groups],
                         [(20.0, 40.0), (40.0, 60.0), (60.0, 80.0)])

    def test_values_exactly_on_a_boundary_follow_the_stated_inclusivity(self):
        series = pd.Series([0.0, 5.0, 10.0, 10.0, 15.0, 20.0], name="score")
        lower_takes = sg.range_rule("custom", [("A", 0, 10, True, True),
                                               ("B", 10, 20, False, True)])
        upper_takes = sg.range_rule("custom", [("A", 0, 10, True, False),
                                               ("B", 10, 20, True, True)])
        self.assertEqual([g.n for g in sg.preview(series, lower_takes).groups], [4, 2])
        self.assertEqual([g.n for g in sg.preview(series, upper_takes).groups], [2, 4])
        nine = pd.Series(range(1, 10), name="nine")            # median position (9 − 1)/2 = 4
        right = sg.preview(nine, sg.quantile_rule(2))
        left = sg.preview(nine, sg.quantile_rule(2, closed="left"))
        self.assertEqual(right.cut_points, (5.0,))
        self.assertEqual([g.n for g in right.groups], [5, 4], "5 belongs to the lower group")
        self.assertEqual([g.n for g in left.groups], [4, 5], "5 belongs to the upper group")
        self.assertEqual([(g.lower_inclusive, g.upper_inclusive) for g in left.groups],
                         [(True, False), (True, True)])
        four = pd.Series([0, 10, 20, 30], name="four")
        self.assertEqual([g.n for g in sg.preview(four, sg.equal_width_rule(3)).groups],
                         [2, 1, 1])
        self.assertEqual([g.n for g in sg.preview(four, sg.equal_width_rule(3, closed="left"))
                          .groups], [1, 1, 2])

    def test_missing_non_numeric_and_out_of_range_values_are_counted_not_grouped(self):
        frame = pd.DataFrame({"score": [18, 20, 39, 40, None, "n/a", 81, 59, 60, 80, np.nan]})
        rule = sg.range_rule("documented", [("Low", 20, 39, True, True),
                                            ("Moderate", 40, 59, True, True),
                                            ("High", 60, 80, True, True)],
                             source="Invented Manual (2099)")
        preview = sg.preview(frame["score"], rule)
        self.assertEqual((preview.n_total, preview.n_missing, preview.n_non_numeric,
                          preview.n_out_of_range, preview.n_valid), (11, 2, 1, 2, 8))
        self.assertEqual([g.n for g in preview.groups], [2, 2, 2])
        self.assertAlmostEqual(preview.groups[0].percent, 25.0)
        self.assertAlmostEqual(preview.out_of_range_percent, 25.0)
        self.assertTrue({"groups.out_of_range", "groups.missing", "groups.non_numeric"}
                        <= set(preview.warning_keys()))
        result = sg.apply(frame, "score", rule, "score_level")
        derived = result.frame["score_level"]
        self.assertEqual(derived.isna().tolist(),
                         [True, False, False, False, True, True, True, False, False, False, True])
        self.assertEqual(result.params["n_out_of_range"], 2)
        self.assertEqual(result.params["n_missing"], 2)
        self.assertEqual(result.params["n_non_numeric"], 1)

    def test_apply_returns_a_new_frame_and_leaves_the_source_unchanged(self):
        rule = sg.quantile_rule(3, ("Lower third", "Middle third", "Upper third"))
        preview = sg.preview(self.frame["UCLA"], rule)
        pd.testing.assert_frame_equal(self.frame, self.original)
        result = sg.apply(self.frame, "UCLA", rule, "UCLA_tertile")
        pd.testing.assert_frame_equal(self.frame, self.original)
        self.assertNotIn("UCLA_tertile", self.frame.columns)
        pd.testing.assert_series_equal(result.frame["UCLA"], self.original["UCLA"])
        pd.testing.assert_frame_equal(result.frame.drop(columns="UCLA_tertile"), self.original)
        derived = result.frame["UCLA_tertile"]
        self.assertIsInstance(derived.dtype, pd.CategoricalDtype)
        self.assertTrue(derived.dtype.ordered)
        self.assertEqual(list(derived.dtype.categories), list(rule.labels))
        self.assertEqual(derived.value_counts(sort=False).tolist(), [g.n for g in preview.groups])
        bounds = preview.groups
        for value, label in zip(self.frame["UCLA"], derived):
            group = preview.group(label)
            self.assertTrue(sg.GroupRange(group.lower, group.upper, group.lower_inclusive,
                                          group.upper_inclusive).includes(value))
        self.assertEqual(len(bounds), 3)

    def test_the_target_must_be_new(self):
        rule = sg.quantile_rule(3)
        with self.assertRaises(ValueError):
            sg.apply(self.frame, "UCLA", rule, "UCLA_Level")
        with self.assertRaises(ValueError):
            sg.apply(self.frame, "UCLA", rule, "UCLA")
        with self.assertRaises(ValueError):
            sg.apply(self.frame, "UCLA", rule, "2 groups")
        with self.assertRaises(ValueError):
            sg.apply(self.frame, "Missing", rule, "Missing_groups")
        pd.testing.assert_frame_equal(self.frame, self.original)

    def test_the_preview_warns_before_anything_is_applied(self):
        values = self.frame["UCLA"]
        documented = sg.range_rule("documented", [("Low", 20, 39, True, True),
                                                  ("Moderate", 40, 59, True, True),
                                                  ("High", 60, 80, True, True)],
                                   source="Invented Manual (2099)")
        small = sg.preview(values, documented)
        self.assertEqual([g.n for g in small.groups], [3, 47, 5])
        self.assertEqual(small.warning_keys(), ("groups.small",), "3 is under 5, no gap for "
                         "whole numbers between 39 and 40")
        overlap = sg.range_rule("custom", [("A", 20, 40, True, True), ("B", 40, 60, True, False),
                                           ("C", 61.5, 70, True, True), ("D", 75, 80, True, True)])
        preview = sg.preview(values, overlap)
        keys = preview.warning_keys()
        for key in ("groups.overlap", "groups.overlap_values", "groups.gap",
                    "groups.non_integer_threshold", "groups.empty", "groups.out_of_range"):
            self.assertIn(key, keys)
        self.assertEqual(preview.n_overlapping, int((values == 40).sum()))
        with self.assertRaises(ValueError) as raised:
            sg.apply(self.frame, "UCLA", overlap, "UCLA_custom")
        self.assertIn("overlap", str(raised.exception))
        impossible = sg.range_rule("custom", [("Low", 20, 50, True, True),
                                              ("Between", 50, 51, False, False),
                                              ("High", 51, 80, True, True)])
        self.assertIn("groups.no_integer_in_range", sg.preview(values, impossible).warning_keys())
        # Positions 11·j/4 on the sorted values give the edges 1, 1, 1.5, 4.25 and 5:
        # the six tied 1s fill Q1 = [1, 1], Q2 = (1, 1.5] is empty (pandas.qcut refuses
        # the duplicate edge).
        ties = pd.Series([1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 5, 5], name="codes")
        tied = sg.preview(ties, sg.quantile_rule(4))
        self.assertEqual([g.n for g in tied.groups], [6, 0, 3, 3])
        self.assertEqual([(g.lower, g.upper) for g in tied.groups],
                         [(1.0, 1.0), (1.0, 1.5), (1.5, 4.25), (4.25, 5.0)])
        self.assertEqual(tied.warning_keys().count("groups.quantile_ties"), 1)
        self.assertIn("6 tied values", tied.warnings[0].text)
        self.assertIn("“Q1”", tied.warnings[0].text)
        self.assertIn("groups.empty", tied.warning_keys())
        with self.assertRaises(ValueError):
            pd.qcut(ties, 4)
        balanced = sg.preview(values, sg.quantile_rule(2))
        self.assertNotIn("groups.quantile_ties", balanced.warning_keys(),
                         "28/27 is as equal as 55 values allow")
        heavy = pd.Series([3] * 30 + [1, 2, 4, 5] * 5, name="heavy")
        empty = sg.preview(heavy, sg.quantile_rule(4))
        self.assertIn("groups.empty", empty.warning_keys())
        with self.assertRaises(ValueError):
            sg.preview(pd.Series([None, "x"], name="nothing"), sg.quantile_rule(2))

    def test_preview_messages_and_the_record_are_json(self):
        rule = sg.quantile_rule(4)
        preview = sg.preview(self.frame["UCLA"], rule)
        again = sg.GroupPreview.from_dict(json.loads(json.dumps(preview.to_dict())))
        self.assertEqual(again, preview)
        for message in preview.warnings:
            self.assertEqual(message.text, sg.TEXT[message.key].format(**message.params))
        result = sg.apply(self.frame, "UCLA", rule, "UCLA_quartile")
        record = json.loads(json.dumps(result.record()))
        self.assertEqual(record["kind"], "scale_groups")
        self.assertEqual(record["output_columns"], ["UCLA_quartile"])
        params = record["params"]
        self.assertEqual((params["source"], params["target"], params["version"]),
                         ("UCLA", "UCLA_quartile", sg.RULE_VERSION))
        self.assertEqual(sg.GroupRule.from_dict(params["rule"]), rule)
        self.assertEqual([g["upper"] for g in params["groups"][:-1]], list(preview.cut_points))

    def test_the_record_fits_the_project_transformations_table(self):
        from project_store import ProjectStore

        rule = sg.range_rule("custom", [("Lower", 20, 49, True, True),
                                        ("Higher", 50, 80, True, True)])
        result = sg.apply(self.frame, "UCLA", rule, "UCLA_split")
        with tempfile.TemporaryDirectory() as folder:
            store = ProjectStore(Path(folder) / "projects")
            info = store.create("Invented study")
            with store.open(info.id) as project:
                dataset = project.add_frame(result.frame, "UCLA groups")
                project.add_transformation(dataset.id, **result.record())
                (stored,) = project.transformations(dataset.id)
                self.assertEqual(stored["kind"], "scale_groups")
                self.assertEqual(stored["output_columns"], ["UCLA_split"])
                self.assertEqual(stored["params"], json.loads(json.dumps(result.params)))
                loaded = project.load_frame(dataset.id)
                pd.testing.assert_series_equal(loaded["UCLA_split"], result.frame["UCLA_split"])
                pd.testing.assert_series_equal(loaded["UCLA"], self.original["UCLA"])


class ExistingGroupingTests(unittest.TestCase):
    def test_ucla_level_is_proposed_for_ucla_and_nothing_is_selected(self):
        frame = totals_frame()
        before = frame.copy(deep=True)
        (proposal,) = sg.existing_groupings(frame, "UCLA")
        self.assertEqual(proposal.name, "UCLA_Level")
        self.assertEqual(proposal.categories, ("1", "2", "3"))
        self.assertEqual(proposal.counts, (3, 47, 5))
        self.assertTrue(proposal.splits_scale)
        self.assertIn("own range of UCLA", proposal.reason)
        pd.testing.assert_frame_equal(frame, before)
        self.assertEqual(sg.existing_groupings(frame, "Age"), ())
        self.assertEqual(sg.existing_groupings(frame, fx.SCALES[0]), ())

    def test_name_forms_and_overlapping_categories(self):
        rng = np.random.default_rng(3)
        scale = rng.integers(10, 50, 60)
        frame = pd.DataFrame({
            "Stress": scale,
            "Stress_group": np.where(scale < 30, "low", "high"),          # text, splits
            "stress-cat": rng.integers(1, 4, 60),                        # random, overlaps
            "Level_Stress": pd.Categorical(np.where(scale < 25, "a", "b"),
                                           categories=["a", "b"], ordered=True),
            "Stress_total": scale * 2,                                   # not a grouping word
            "StressGroupID": np.arange(60),                              # too many values
        })
        proposals = {p.name: p for p in sg.existing_groupings(frame, "Stress")}
        self.assertEqual(set(proposals), {"Stress_group", "stress-cat", "Level_Stress"})
        self.assertTrue(proposals["Stress_group"].splits_scale)
        self.assertEqual(proposals["Stress_group"].categories, ("low", "high"))
        self.assertFalse(proposals["stress-cat"].splits_scale)
        self.assertIn("do not split", proposals["stress-cat"].reason)
        self.assertEqual(proposals["Level_Stress"].categories, ("a", "b"))
        self.assertEqual(list(proposals)[-1], "stress-cat", "splitting proposals come first")


if __name__ == "__main__":
    unittest.main()
