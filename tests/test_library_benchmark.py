"""The research library's tokenizer and query form are chosen by evidence
(Stage 37.3, Issue #69; docs/STAGE37_RAG.md §4).

``tools/library_benchmark.py`` indexes the labelled synthetic EN/LV/RU corpus
with 13 configurations. The library default must reach the best recall@1, @3
and @5 overall and in every language, and an MRR within 0.01 (one query of
the 51 moving one place) of the best; a configuration with a better MRR but
an index more than twice as large, slower queries and no exact pure-Python
fallback (trigram) does not replace it. The exact-word baseline must be
clearly worse, and the independent review's probes must rank first.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("MPLBACKEND", "Agg")

import library_benchmark as bench  # noqa: E402
import library_fixtures as fx  # noqa: E402


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = bench.run()
        cls.results = {r["config"]["key"]: r for r in cls.report["results"] if r["available"]}
        cls.default = cls.results[cls.report["default"]]

    def test_the_corpus_and_queries_cover_three_languages(self):
        self.assertEqual(len(fx.CORPUS), 12)
        self.assertEqual(sum(len(d.passages) for d in fx.CORPUS), 51)
        for language in bench.LANGUAGES:
            queries = [q for q in fx.QUERIES if q.language == language]
            self.assertEqual(len(queries), 17, language)
            self.assertTrue({"inflected", "exact"} <= {q.kind for q in queries})
        for query in fx.QUERIES:
            self.assertTrue(all(key in fx.PASSAGES for key in query.relevant), query.key)
        self.assertEqual(self.report["default"], "G")

    def test_the_default_has_the_best_recall_and_an_mrr_within_one_query_of_the_best(self):
        """Best overall recall@1/3/5; overall MRR within 0.01 of the best; in
        each language every metric within one query (1/17) of the best there
        (porter on exact words finds the English typo query at rank 3, the
        default does not find it; both are listed in docs/STAGE37_RAG.md §4)."""
        for k in bench.KS:
            metric = f"recall@{k}"
            best = max(r["summary"]["all"][metric] for r in self.results.values())
            self.assertEqual(self.default["summary"]["all"][metric], best, metric)
        for language in bench.LANGUAGES:
            for metric in (*(f"recall@{k}" for k in bench.KS), "mrr"):
                best = max(r["summary"][language][metric] for r in self.results.values())
                with self.subTest(language=language, metric=metric):
                    self.assertGreaterEqual(self.default["summary"][language][metric],
                                            best - 1 / 17 - 1e-4)
        best_mrr = max(r["summary"]["all"]["mrr"] for r in self.results.values())
        self.assertGreaterEqual(self.default["summary"]["all"]["mrr"], best_mrr - 0.01)
        better = [key for key, r in self.results.items()
                  if r["summary"]["all"]["mrr"] > self.default["summary"]["all"]["mrr"]]
        for key in better:
            self.assertTrue(self.results[key]["config"]["tokenizer"].startswith("trigram"), key)
            if self.default["index_bytes"] is not None:
                self.assertGreater(self.results[key]["index_bytes"],
                                   2 * self.default["index_bytes"], key)

    def test_per_language_accuracy_of_the_default(self):
        summary = self.default["summary"]
        for language in bench.LANGUAGES:
            with self.subTest(language=language):
                self.assertGreaterEqual(summary[language]["recall@5"], 0.94)
                self.assertGreaterEqual(summary[language]["mrr"], 0.90)
        self.assertEqual(summary["ru"]["recall@5"], 1.0)

    def test_exact_words_are_clearly_worse(self):
        exact = self.results["C"]["summary"]["all"]
        self.assertGreater(self.default["summary"]["all"]["mrr"] - exact["mrr"], 0.05)
        self.assertGreater(self.default["summary"]["all"]["recall@5"] - exact["recall@5"], 0.03)

    def test_the_reviewers_probes_rank_first(self):
        ranks = {q["query"]: q["first_relevant_rank"] for q in self.default["queries"]}
        for query in ("q-en-lonely", "q-ru-razryv", "q-lv-plaisa", "q-ru-podschet", "q-ru-obem",
                      "q-lv-atsaukums", "q-lv-etika"):
            self.assertEqual(ranks[query], 1, query)

    def test_the_report_reads_as_a_table(self):
        table = bench.to_markdown(self.report)
        self.assertIn("| G (default) | unicode61 remove_diacritics 2 · stem · ё→е |", table)
        self.assertEqual(table.count("\n| "), len(bench.CONFIGS) + 1)


if __name__ == "__main__":
    unittest.main()
