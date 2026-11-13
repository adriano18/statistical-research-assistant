"""Stage 37 (#67, review finding D8): CSV exports never hand a spreadsheet a
formula.

A text cell that begins with ``=``, ``+``, ``-`` or ``@`` (or a tab or a
carriage return) is written with a leading apostrophe (OWASP "CSV
Injection"); numbers are never changed; the program's own importer removes
the apostrophe again when the codebook next to the CSV vouches for the file
(csv_safety). Covers the two CSV exports that existed before Stage 37: the
questionnaire responses (survey_storage) and the prepared dataset
(data_preparation). Synthetic data only.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import csv_safety  # noqa: E402
from data_loader import load_dataset_with_report  # noqa: E402

ATTACKS = ("=1+1", "+x", "-2+3", "@SUM(A1)", "=HYPERLINK(\"http://example.invalid\")")


def cells(path: Path) -> list[list[str]]:
    """The CSV as the cells a spreadsheet gets (quotes removed)."""
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.reader(io.StringIO(text, newline="")))


class RuleTests(unittest.TestCase):
    def test_every_trigger_gets_one_apostrophe_and_numbers_never_do(self):
        for text in (*ATTACKS, "\tTAB", "\rCR"):
            self.assertEqual(csv_safety.protect(text), "'" + text)
        for text in ("plain", "", "'quoted'", "007", "1,5", "[\"a\"]", " =spaced"):
            self.assertEqual(csv_safety.protect(text), text, text)

    def test_restore_undoes_protect_for_every_text(self):
        generator = random.Random(37067)
        alphabet = "'=+-@\t\rab1 ,;\"ĀЖ"
        samples = ["", "'", "''", "'=", "''=x", "'-", "'a", *ATTACKS]
        samples += ["".join(generator.choice(alphabet) for _ in range(generator.randint(0, 6)))
                    for _ in range(4000)]
        for text in samples:
            protected = csv_safety.protect(text)
            self.assertEqual(csv_safety.restore(protected), text, repr(text))
            self.assertFalse(protected[:1] in csv_safety.TRIGGERS, repr(text))

    def test_an_apostrophe_of_the_researcher_is_text_unless_the_codebook_vouches(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "elsewhere.csv"
            path.write_text("note\n'=kept as typed\nplain\n", encoding="utf-8")
            frame, _ = load_dataset_with_report(path)
            self.assertEqual(frame["note"].tolist(), ["'=kept as typed", "plain"])


class SurveyExportTests(unittest.TestCase):
    """Questionnaire responses: Questionnaires → Export CSV + codebook."""

    def setUp(self):
        from survey_storage import create_survey

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "surveys"
        self.survey = create_survey(self.root, "Fictional formula check", "", [
            {"key": "comment", "prompt": "Any comment?", "kind": "short_text"},
            {"key": "change", "prompt": "Change in points", "kind": "number"},
        ])

    def export(self) -> tuple[Path, Path]:
        from survey_storage import save_survey_codebook, save_survey_csv, submit_response

        for text, number in zip(ATTACKS, (-5, -2.5, 3, 0, 1)):
            submit_response(self.root, self.survey.survey_id, {"comment": text, "change": number})
        submit_response(self.root, self.survey.survey_id, {"comment": "fine", "change": -1})
        folder = Path(self.tmp.name)
        written = save_survey_csv(self.root, self.survey.survey_id, folder / "pilot.csv")
        book = save_survey_codebook(self.root, self.survey.survey_id,
                                    csv_safety.codebook_path(written), data_file=written)
        return written, book

    def test_formula_text_is_written_as_text_and_numbers_unchanged(self):
        written, _ = self.export()
        rows = cells(written)
        header, body = rows[0], rows[1:]
        comments = [row[header.index("comment")] for row in body]
        self.assertEqual(comments, ["'" + text for text in ATTACKS] + ["fine"])
        changes = [row[header.index("change")] for row in body]
        self.assertEqual([float(c) for c in changes], [-5, -2.5, 3, 0, 1, -1],
                         "numbers are never changed (no apostrophe before -5)")
        self.assertFalse(any(c.startswith("'") for c in changes))

    def test_the_program_reads_back_exactly_what_was_answered(self):
        written, book = self.export()
        info = json.loads(book.read_text(encoding="utf-8"))
        self.assertEqual(info["data_file"]["formula_protection"]["rule"], csv_safety.RULE)
        self.assertEqual(info["questions"][0]["key"], "comment", "the codebook is as before")
        frame, report = load_dataset_with_report(written)
        self.assertEqual(frame["comment"].tolist(), [*ATTACKS, "fine"])
        self.assertTrue(any("Formula protection removed from 5" in w for w in report.warnings))

    def test_an_edited_csv_keeps_its_apostrophes(self):
        written, _ = self.export()
        written.write_text(written.read_text(encoding="utf-8-sig") + '"x","\'=edited",7\n',
                           encoding="utf-8-sig")
        frame, report = load_dataset_with_report(written)
        self.assertEqual(frame["comment"].iloc[0], "'=1+1", "the codebook no longer vouches")
        self.assertFalse(any("Formula protection" in w for w in report.warnings))


class PreparedExportTests(unittest.TestCase):
    """Data → Prepare → Save a new prepared CSV and transformation log."""

    def test_formula_text_and_header_are_protected_numbers_are_not(self):
        from data_preparation import save_prepared_dataset

        frame = pd.DataFrame({"answer": [*ATTACKS, "fine"], "=score": [-5, -1.5, 0, 2, 3, 4],
                              "code": ["007", "-01", "+3", "x", "y", "z"]})
        with tempfile.TemporaryDirectory() as folder:
            path, recipe = save_prepared_dataset(frame, [], Path(folder) / "prepared.csv")
            rows = cells(path)
            self.assertEqual(rows[0], ["answer", "'=score", "code"])
            self.assertEqual([r[0] for r in rows[1:]], ["'" + t for t in ATTACKS] + ["fine"])
            self.assertEqual([float(r[1]) for r in rows[1:]], [-5, -1.5, 0, 2, 3, 4])
            self.assertEqual([r[2] for r in rows[1:]], ["007", "'-01", "'+3", "x", "y", "z"])
            log = json.loads(recipe.read_text(encoding="utf-8"))
            self.assertEqual(log["format"], "statistical-research-assistant-prep-v1")
            self.assertEqual(log["data_file"]["formula_protection"]["rule"], csv_safety.RULE)
            back, _ = load_dataset_with_report(path)
            self.assertEqual(list(back.columns), ["answer", "=score", "code"])
            self.assertEqual(back["answer"].tolist(), [*ATTACKS, "fine"])
            self.assertEqual(back["code"].tolist(), ["007", "-01", "+3", "x", "y", "z"])


if __name__ == "__main__":
    unittest.main()
