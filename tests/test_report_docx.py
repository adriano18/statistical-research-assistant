"""Stage 35 (#42): one editable Word document from several results.

Real engine runs (ANCOVA, scale reliability, correlation) on the bundled
fictional examples; the document is opened again with python-docx and its
XML is inspected: order, numbering, real tables equal to the engine's,
embedded figures, header and page numbers, provenance, languages."""

from __future__ import annotations

import io
import sys
import unittest
import zipfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pandas as pd  # noqa: E402
from docx import Document  # noqa: E402

import analysis_runs as runs  # noqa: E402
import report_docx as rd  # noqa: E402

EXAMPLES = ROOT / "examples"
WHEN = datetime(2026, 11, 6, 12, 30)


def sample(name: str) -> pd.DataFrame:
    return pd.read_csv(EXAMPLES / name)


def engine_runs():
    scale = sample("sample_scale.csv")
    return [
        runs.run_ancova(sample("sample_ancova.csv"), "wellbeing", "group", ["baseline_score"],
                        "ancova", True),
        runs.run_alpha(scale, ["stress_q1", "stress_q2", "stress_q3", "stress_q4"], True),
        runs.run_correlation(sample("sample_regression.csv"), "study_hours", "stress_score",
                             "pearson", "scale", "scale", True),
        runs.run_omega(scale, ["stress_q1", "stress_q2", "stress_q3", "stress_q4"], True, 0),
    ]


RUNS = None


def blocks():
    global RUNS
    if RUNS is None:
        RUNS = engine_runs()
    return [rd.ReportBlock(title=run.title, report=run.report, tables=run.tables, figure=run.png,
                           section=run.section, dataset=f"data-{n}.csv", rows=100 + n,
                           dataset_sha256=f"{n:02d}" * 32, created=WHEN, method=run.section,
                           run_id=f"run-{n}", warnings=run.warnings)
            for n, run in enumerate(RUNS, start=1)]


def reopen(document) -> Document:
    stream = io.BytesIO()
    document.save(stream)
    stream.seek(0)
    return Document(stream), stream.getvalue()


def texts(document) -> list[str]:
    return [p.text for p in document.paragraphs]


class ReportDocumentTests(unittest.TestCase):
    def test_every_result_in_order_with_real_tables_and_figures(self):
        parts = blocks()
        document, raw = reopen(rd.build_report_docx(parts, title="Fictional wellbeing study",
                                                    project="Project A", version="1.0.0",
                                                    generated=WHEN))
        lines = texts(document)
        expected = [f"{n}. {p.title}" for n, p in enumerate(parts, start=1)]
        self.assertEqual([line for line in lines if line in expected], expected * 2,
                         "listed in the contents, then one section each in the same order")
        tables_expected = sum(len(p.tables) for p in parts)
        captions = [line for line in lines if line.startswith("Table ")]
        self.assertEqual(captions, [f"Table {n}" for n in range(1, tables_expected + 1)])
        figures = [line for line in lines if line.startswith("Figure ")]
        self.assertEqual(figures, [f"Figure {n}" for n in range(1, sum(1 for p in parts if p.figure) + 1)])
        # Engine tables are real Word tables with the engine's own cells.
        first = parts[0].tables[0]
        word = document.tables[0]
        self.assertEqual([c.text for c in word.rows[0].cells], list(first.columns))
        self.assertEqual([c.text for c in word.rows[1].cells], [str(v) for v in first.rows[0]])
        self.assertEqual(len(document.tables), tables_expected + 1, "+ the provenance table")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            images = [n for n in archive.namelist() if n.startswith("word/media/")]
            xml = archive.read("word/document.xml").decode("utf-8")
            footer = "".join(archive.read(n).decode("utf-8") for n in archive.namelist()
                             if n.startswith("word/footer"))
            header = "".join(archive.read(n).decode("utf-8") for n in archive.namelist()
                             if n.startswith("word/header"))
        self.assertEqual(len(images), len(figures))
        self.assertIn("<w:tblHeader", xml, "long tables repeat their header row")
        self.assertIn("PAGE", footer)
        self.assertIn("FICTIONAL WELLBEING STUDY", header)
        # The engine's report text is there word for word.
        self.assertIn(parts[1].report.strip().splitlines()[0].strip(), "\n".join(lines))

    def test_provenance_names_dataset_version_and_run_of_every_result(self):
        document, _ = reopen(rd.build_report_docx(blocks(), title="T", generated=WHEN))
        provenance = document.tables[-1]
        self.assertEqual([c.text for c in provenance.rows[0].cells], list(rd.LABELS["en"]["columns"]))
        rows = [[c.text for c in row.cells] for row in provenance.rows[1:]]
        self.assertEqual([r[3] for r in rows], [f"data-{n}.csv" for n in range(1, 5)])
        self.assertEqual([r[4] for r in rows], [f"{n:02d}" * 6 for n in range(1, 5)])
        self.assertEqual([r[7] for r in rows], [f"run-{n}" for n in range(1, 5)])

    def test_reordering_renumbers_tables_and_figures(self):
        parts = blocks()
        later = next(p for p in parts[1:] if p.tables)
        reordered = [later] + [p for p in parts if p is not later]
        document, _ = reopen(rd.build_report_docx(reordered, title="T", generated=WHEN))
        lines = texts(document)
        self.assertIn(f"1. {later.title}", lines)
        self.assertEqual([line for line in lines if line.startswith("Table ")][0], "Table 1")
        self.assertEqual([c.text for c in document.tables[0].rows[0].cells],
                         list(later.tables[0].columns), "Table 1 now belongs to the first result")

    def test_results_that_need_review_are_refused_or_marked(self):
        parts = blocks()
        parts[1] = replace(parts[1], stale=("the dataset changed",))
        with self.assertRaises(ValueError) as refused:
            rd.build_report_docx(parts, title="T")
        self.assertIn(parts[1].title, str(refused.exception))
        document, _ = reopen(rd.build_report_docx(parts, title="T", allow_stale=True))
        joined = "\n".join(texts(document))
        self.assertIn(f"2. {parts[1].title} — needs review", joined)
        self.assertIn("calculated before these changes: the dataset changed", joined)

    def test_latvian_and_russian_labels_with_diacritics(self):
        for language, table, figure in (("lv", "Tabula", "Attēls"), ("ru", "Таблица", "Рисунок")):
            with self.subTest(language=language):
                document, raw = reopen(rd.build_report_docx(blocks(), title="Pētījums / Исследование",
                                                            language=language, generated=WHEN))
                lines = texts(document)
                self.assertIn(f"{table} 1", lines)
                self.assertIn(f"{figure} 1", lines)
                self.assertIn(rd.LABELS[language]["provenance"], lines)
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    header = "".join(archive.read(n).decode("utf-8") for n in archive.namelist()
                                     if n.startswith("word/header"))
                self.assertIn("PĒTĪJUMS / ИССЛЕДОВАНИЕ", header)

    def test_thirty_two_results_make_one_long_document(self):
        parts = [replace(blocks()[n % 3], title=f"Result {n}") for n in range(32)]
        document, raw = reopen(rd.build_report_docx(parts, title="Long", generated=WHEN))
        figures = [line for line in texts(document) if line.startswith("Figure ")]
        self.assertEqual(figures[-1], f"Figure {sum(1 for p in parts if p.figure)}")
        self.assertEqual(len([l for l in texts(document) if l.startswith("Result ")]), 0)
        self.assertEqual(sum(1 for line in texts(document) if line.startswith("32. Result 31")), 2,
                         "listed in the contents and as the last section")

    def test_each_export_gets_a_new_file_name_and_writes_atomically(self):
        import tempfile

        self.assertEqual(rd.default_file_name("Fictional: study / 2026", WHEN),
                         "Fictional_study_2026_2026-11-06_1230.docx")
        folder = Path(tempfile.mkdtemp())
        target = folder / "report.docx"
        rd.save_report_docx(target, rd.build_report_docx(blocks(), title="T"))
        Document(str(target))                  # opens again
        self.assertEqual([p.name for p in folder.iterdir()], ["report.docx"])

    def test_an_empty_report_is_refused(self):
        with self.assertRaises(ValueError):
            rd.build_report_docx([], title="T")


class WorkspaceExportTests(unittest.TestCase):
    def test_the_reports_page_exports_one_word_document_in_report_order(self):
        from workspace_harness import Workspace

        ws = Workspace()
        self.addCleanup(ws.close)
        session = ws.app.session
        for run in engine_runs()[:2]:
            entry = session.add_result(run, method=run.section)
            session.toggle_report(entry.id)
        ws.app.navigate("reports")
        ws.click("reports-export-docx")
        saved = [p for p in ws.saved if p.suffix == ".docx"]
        self.assertEqual(len(saved), 1)
        document = Document(str(saved[0]))
        lines = [p.text for p in document.paragraphs]
        entries = session.report_entries()
        # Stage 36.6: one research report in sections; each result is written
        # in the section it belongs to (a test, a reliability analysis …).
        headings = [p.text for p in document.paragraphs if p.style.name.startswith("Heading")]
        for entry in entries:
            self.assertIn(entry.title, headings)
        self.assertTrue(any(h.endswith("Hypothesis tests") for h in headings))
        self.assertTrue(any(h.endswith("Reliability and measurement quality") for h in headings))
        self.assertIn("Table 1", lines)


if __name__ == "__main__":
    unittest.main()
