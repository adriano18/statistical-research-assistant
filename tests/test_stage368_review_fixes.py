"""Stage 36.8: findings of the independent review, reproduced, then fixed.

K4 — an interpretation sentence named its p-value "adjusted" whatever the
researcher chose, also "None (raw p only)". It now names the procedure
actually applied, in every language, and an unadjusted family says once that
its false-positive risk is higher than α.

K5 — the batch Kruskal–Wallis result computed group medians, mean ranks and
Dunn's pairs, and its "Methods" said pairwise tests were made, but it showed
one table without any of them. It now shows the groups of every outcome and
Dunn's pairs for each outcome whose Kruskal–Wallis test is significant after
the adjustment across outcomes; the values are the engine's own (and equal an
independent call of posthoc_analysis.dunn_pairs).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis_runs import run_batch_groups  # noqa: E402
from batch_correlation import P_LABELS, correlate_many  # noqa: E402
from batch_groups import compare_many, compare_two_many, interpret_groups  # noqa: E402
from posthoc_analysis import dunn_pairs  # noqa: E402


def _correlation_data(n: int = 60, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    return pd.DataFrame({"focal": x, "related": x + rng.normal(scale=0.6, size=n),
                         "noise_a": rng.normal(size=n), "noise_b": rng.normal(size=n)})


def _group_data(seed: int = 11) -> pd.DataFrame:
    """Three groups of 20; 'shifted' differs between groups, 'flat' does not."""
    rng = np.random.default_rng(seed)
    groups = np.repeat(["A", "B", "C"], 20)
    shift = np.select([groups == "A", groups == "B"], [0.0, 1.0], 2.0)
    return pd.DataFrame({"group": groups,
                         "shifted": np.round(rng.normal(size=60) + shift, 2),
                         "flat": np.round(rng.normal(size=60), 2)})


class PValueLabelTests(unittest.TestCase):
    """K4."""

    def _sentences(self, adjust: str, language: str) -> list[str]:
        family = correlate_many(_correlation_data(), "focal", ["related", "noise_a", "noise_b"],
                                method="spearman", adjust=adjust, spearman_p="asymptotic")
        return family.interpretation(language)

    def test_no_adjustment_is_never_called_adjusted(self):
        for language, adjusted_word in (("en", "adjusted"), ("lv", "koriģēts"), ("ru", "скорр")):
            sentences = self._sentences("none", language)
            label = P_LABELS[language]["none"]
            for sentence in sentences:
                self.assertIn(f"{label} = ", sentence, language)
                self.assertNotIn(f"p({adjusted_word}", sentence, language)

    def test_every_procedure_is_named(self):
        for adjust in ("holm", "bh", "bonferroni"):
            for language in ("en", "lv", "ru"):
                for sentence in self._sentences(adjust, language):
                    self.assertIn(f"{P_LABELS[language][adjust]} = ", sentence, (adjust, language))

    def test_an_unadjusted_family_warns_once(self):
        unadjusted = correlate_many(_correlation_data(), "focal", ["related", "noise_a", "noise_b"],
                                    method="spearman", adjust="none", spearman_p="asymptotic")
        warning = [w for w in unadjusted.warnings if w.startswith("No multiple-comparison")]
        self.assertEqual(len(warning), 1)
        self.assertIn("3 tests", warning[0])
        holm = correlate_many(_correlation_data(), "focal", ["related", "noise_a", "noise_b"],
                              method="spearman", adjust="holm", spearman_p="asymptotic")
        self.assertFalse([w for w in holm.warnings if w.startswith("No multiple-comparison")])

    def test_group_families_name_the_procedure_too(self):
        data = _group_data()
        many = compare_many(data, "group", ["shifted", "flat"], adjust="none", permutations=999)
        two = compare_two_many(data[data["group"] != "C"], "group", ["shifted", "flat"],
                               adjust="bonferroni")
        for language in ("en", "lv", "ru"):
            for sentence in interpret_groups(many, language):
                self.assertIn(f"{P_LABELS[language]['none']} = ", sentence)
            for sentence in interpret_groups(two, language):
                self.assertIn(f"{P_LABELS[language]['bonferroni']} = ", sentence)
        self.assertTrue([w for w in many.warnings if w.startswith("No multiple-comparison")])


class KruskalWallisGroupTableTests(unittest.TestCase):
    """K5."""

    @classmethod
    def setUpClass(cls):
        cls.data = _group_data()
        cls.family = compare_many(cls.data, "group", ["shifted", "flat"], permutations=999)

    def test_the_result_has_three_tables(self):
        titles = [table.title for table in self.family.tables()]
        self.assertEqual(len(titles), 3, titles)
        self.assertTrue(titles[1].startswith("Groups of group"))
        self.assertTrue(titles[2].startswith("Dunn's pairwise tests"))
        structured = self.family.structured()
        self.assertEqual([t.title for t in structured.tables], titles)

    def test_groups_table_holds_n_median_and_mean_rank_of_every_group(self):
        table = self.family.group_table()
        self.assertEqual(table.columns, ("Outcome", "group", "n", "Median", "Mean rank"))
        self.assertEqual(len(table.rows), 6)                  # 2 outcomes × 3 groups
        for outcome in ("shifted", "flat"):
            for label in ("A", "B", "C"):
                values = self.data.loc[self.data["group"] == label, outcome]
                row = next(r for r in table.rows if r[0] == outcome and r[1] == label)
                self.assertEqual(row[2], "20")
                self.assertAlmostEqual(float(row[3]), float(np.median(values)), places=3)
        ranks = self.data["shifted"].rank()
        expected = ranks[self.data["group"] == "C"].mean()
        row = next(r for r in table.rows if r[0] == "shifted" and r[1] == "C")
        self.assertAlmostEqual(float(row[4]), expected, places=1)

    def test_pairs_only_for_significant_outcomes_and_equal_to_dunn(self):
        shifted, flat = self.family.row("shifted"), self.family.row("flat")
        self.assertLess(shifted.p_adjusted, 0.05)
        self.assertGreaterEqual(flat.p_adjusted, 0.05)
        table = self.family.pairs_table()
        self.assertEqual({row[0] for row in table.rows}, {"shifted"})
        samples = [self.data.loc[self.data["group"] == g, "shifted"].to_numpy(float)
                   for g in ("A", "B", "C")]
        independent = dunn_pairs(samples, ["A", "B", "C"])
        self.assertEqual(len(table.rows), len(independent))
        for pair, row in zip(independent, table.rows):
            self.assertEqual(row[1], f"{pair.first} – {pair.second}")
            self.assertAlmostEqual(float(row[2]), pair.estimate, places=1)
            self.assertAlmostEqual(float(row[3]), pair.statistic, places=2)
        engine = {(p.first, p.second): p for p in shifted.pairs}
        for pair in independent:
            mine = engine[(pair.first, pair.second)]
            self.assertAlmostEqual(mine.p_raw, pair.p_raw, delta=1e-12)
            self.assertAlmostEqual(mine.p_adjusted, pair.p_adjusted, delta=1e-12)

    def test_the_analysis_run_shows_and_reports_them(self):
        run = run_batch_groups(self.data, "group", ["shifted", "flat"], scale="ordinal")
        self.assertEqual(len(run.tables), 3)
        self.assertIn("Groups of group: n, median and mean rank", run.report)
        self.assertIn("Dunn's pairwise tests", run.report)
        self.assertIn("shown for the outcomes whose Kruskal–Wallis test is significant", run.guide)

    def test_no_significant_outcome_no_pairs_table(self):
        family = compare_many(self.data, "group", ["flat"], permutations=999)
        self.assertGreaterEqual(family.row("flat").p_adjusted, 0.05)
        self.assertEqual(len(family.tables()), 2)


class ReliabilityReportTextTests(unittest.TestCase):
    """The scale check's report (Stage 36.8 journey review): the interval is
    named once, sentences end with one full stop, and the codes used for
    floor and ceiling are stated once."""

    def test_the_report_names_each_interval_once(self):
        sys.path.insert(0, str(ROOT / "tests"))
        import stage36_fixtures as fx
        from analysis_runs import run_item_diagnostics

        frame = pd.read_csv(fx.fixture(fx.ITEMS_CSV))
        run = run_item_diagnostics(frame, list(fx.ITEMS), True, resamples=120,
                                   items_confirmed=True)
        report = run.report
        self.assertNotIn("CI 95% CI", report)
        self.assertNotIn("..", report)
        alpha_line = next(line for line in report.splitlines() if line.startswith("Cronbach’s α ="))
        omega_line = next(line for line in report.splitlines() if line.startswith("McDonald’s ω"))
        self.assertEqual(alpha_line.count("95% CI ["), 1, alpha_line)
        self.assertEqual(omega_line.count("95% CI ["), 1, omega_line)
        self.assertEqual(report.count("Floor and ceiling use the codes"), 1)


if __name__ == "__main__":
    unittest.main()
