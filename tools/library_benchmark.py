"""Benchmark of the research library's tokenizers and query forms (Stage 37.3).

    python tools/library_benchmark.py [--json out.json]

Indexes the synthetic EN/LV/RU corpus of ``tests/library_fixtures.py`` (12
documents, 51 passages, written as Markdown and read by the library itself)
once per configuration and runs the labelled queries (``QUERIES``). Every
configuration is a SQLite FTS5 tokenizer, a query form and whether ё is read
as е:

* tokenizers: ``unicode61`` with ``remove_diacritics`` 0, 1 or 2, ``porter``
  over ``unicode61`` and ``trigram`` (with ``remove_diacritics`` where the
  SQLite has it, 3.45+);
* query forms (``research_library.query_terms``): ``exact`` words, ``prefix``
  (``word*``), ``stem`` (English, Latvian and Russian endings removed, then
  ``stem*``) and ``stem-lang`` (the endings of the query's language only).

For each language and overall it reports recall@1, @3 and @5 (the share of
the relevant passages among the first k, averaged over queries) and MRR (the
reciprocal rank of the first relevant passage among the first 10). It also
reports the size of the search index and the median search time. The library
default must be the configuration with the best overall MRR and recall@5
(``tests/test_library_benchmark.py``). Offline: nothing leaves the computer.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from statistics import median
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
os.environ.setdefault("MPLBACKEND", "Agg")

LANGUAGES = ("en", "lv", "ru")
KS = (1, 3, 5)
DEPTH = 10


@dataclass(frozen=True)
class Config:
    key: str
    tokenizer: str
    query_mode: str
    fold: bool

    @property
    def label(self) -> str:
        return f"{self.tokenizer} · {self.query_mode}" + (" · ё→е" if self.fold else "")


CONFIGS = (
    Config("A", "unicode61 remove_diacritics 0", "exact", False),
    Config("B", "unicode61 remove_diacritics 1", "exact", False),
    Config("C", "unicode61 remove_diacritics 2", "exact", False),
    Config("D", "unicode61 remove_diacritics 2", "prefix", False),
    Config("E", "unicode61 remove_diacritics 2", "stem", False),
    Config("F", "unicode61 remove_diacritics 2", "stem-lang", False),
    Config("G", "unicode61 remove_diacritics 2", "stem", True),
    Config("H", "unicode61 remove_diacritics 2", "stem-lang", True),
    Config("I", "porter unicode61 remove_diacritics 2", "exact", False),
    Config("J", "porter unicode61 remove_diacritics 2", "stem", True),
    Config("K", "trigram", "exact", False),
    Config("L", "trigram", "stem", True),
    Config("M", "trigram remove_diacritics 1", "stem", True),
)


def default_config() -> Config:
    import research_library as rl

    for config in CONFIGS:
        if (config.tokenizer, config.query_mode, config.fold) == (
                rl.DEFAULT_TOKENIZER, rl.DEFAULT_QUERY_MODE, rl.DEFAULT_FOLD_YO):
            return config
    raise LookupError("the library default is not among the benchmarked configurations")


def _index_bytes(path: Path) -> int | None:
    """Bytes of the search index tables (dbstat), None where SQLite lacks it."""
    import sqlite3
    from contextlib import closing

    try:
        with closing(sqlite3.connect(path)) as db:
            row = db.execute("SELECT SUM(pgsize) FROM dbstat WHERE name LIKE 'chunk_index%'"
                             ).fetchone()
            return int(row[0] or 0)
    except sqlite3.Error:
        return None


def measure(config: Config, *, queries=None, corpus=None) -> dict:
    """Index the corpus with ``config`` and score every query."""
    import library_fixtures as fx
    import research_library as rl

    queries = fx.QUERIES if queries is None else queries
    corpus = fx.CORPUS if corpus is None else corpus
    caps = rl.capabilities()
    if not caps.tokenizer_works(config.tokenizer):
        return {"config": asdict(config), "label": config.label, "available": False}
    with tempfile.TemporaryDirectory(prefix="sra-library-benchmark-") as folder:
        folder = Path(folder)
        library = rl.Library(folder / "library", tokenizer=config.tokenizer,
                             query_mode=config.query_mode, fold=config.fold, backend="fts5")
        started = time.perf_counter()
        for document in corpus:
            library.add_document(fx.write(document, folder / "sources", "md"))
        build_seconds = time.perf_counter() - started
        relevant_ids = fx.relevance_map(library, corpus)
        per_query, latencies = [], []
        for query in queries:
            wanted = {relevant_ids[key] for key in query.relevant}
            started = time.perf_counter()
            result = library.search(query.text, limit=DEPTH)
            latencies.append(time.perf_counter() - started)
            ranked = [hit.cite_id for hit in result.hits]
            first = next((rank for rank, cite in enumerate(ranked, start=1) if cite in wanted), 0)
            per_query.append({
                "query": query.key, "language": query.language, "kind": query.kind,
                "rr": 1.0 / first if first else 0.0, "first_relevant_rank": first,
                **{f"recall@{k}": len(wanted & set(ranked[:k])) / len(wanted) for k in KS}})
        index_bytes = _index_bytes(library.path)
    summary = {}
    for language in (*LANGUAGES, "all"):
        rows = [q for q in per_query if language == "all" or q["language"] == language]
        summary[language] = {"queries": len(rows),
                             "mrr": round(sum(q["rr"] for q in rows) / len(rows), 4),
                             **{f"recall@{k}": round(sum(q[f"recall@{k}"] for q in rows)
                                                      / len(rows), 4) for k in KS}}
    return {"config": asdict(config), "label": config.label, "available": True,
            "summary": summary, "queries": per_query,
            "index_bytes": index_bytes, "build_seconds": round(build_seconds, 3),
            "median_query_ms": round(1000 * median(latencies), 3)}


def run(configs=CONFIGS) -> dict:
    import research_library as rl

    caps = rl.capabilities()
    return {"sqlite": caps.sqlite, "fts5": caps.fts5,
            "default": default_config().key,
            "results": [measure(config) for config in configs]}


def to_markdown(report: dict) -> str:
    lines = [f"SQLite {report['sqlite']}; library default: configuration {report['default']}.",
             "",
             "| | Configuration | EN R@5 | EN MRR | LV R@5 | LV MRR | RU R@5 | RU MRR "
             "| All R@1 | All R@3 | All R@5 | All MRR | Index | Median query |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for result in report["results"]:
        key = result["config"]["key"]
        if not result["available"]:
            lines.append(f"| {key} | {result['label']} | not available in this SQLite |"
                         + " |" * 11)
            continue
        s = result["summary"]
        size = (f"{result['index_bytes'] / 1024:.0f} KiB" if result["index_bytes"] is not None
                else "—")
        marker = " (default)" if key == report["default"] else ""
        lines.append(
            f"| {key}{marker} | {result['label']} "
            f"| {s['en']['recall@5']:.3f} | {s['en']['mrr']:.3f} "
            f"| {s['lv']['recall@5']:.3f} | {s['lv']['mrr']:.3f} | {s['ru']['recall@5']:.3f} "
            f"| {s['ru']['mrr']:.3f} | {s['all']['recall@1']:.3f} | {s['all']['recall@3']:.3f} "
            f"| {s['all']['recall@5']:.3f} | {s['all']['mrr']:.3f} | {size} "
            f"| {result['median_query_ms']:.2f} ms |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", type=Path, help="also write the full report as JSON")
    args = parser.parse_args(argv)
    report = run()
    print(to_markdown(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
