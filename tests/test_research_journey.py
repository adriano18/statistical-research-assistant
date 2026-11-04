"""Offline integration tests for a complete researcher journey.

These fixtures are GENERATED at test time, not production data or hard-coded
statistical outputs. Calculations must respond to real answers and recoding.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from docx import Document
import pandas as pd

from data_loader import load_dataset_with_report
from data_preparation import reverse_item
from interpretation_docx import save_apa_docx
from interpretation_wizard import build_analysis_evidence
from reliability import analyze_cronbach
from reliability_charts import make_reliability_chart
from reliability_reporting import apa_reliability_report
from survey_storage import (
    create_survey, responses_dataframe, response_count, save_survey_csv,
    save_survey_codebook, submit_response,
)
from survey_ui import _template_questions, preset_value_labels


class ResearchJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.surveys = self.root / "surveys"
        self.surveys.mkdir()

    def test_marketing_branching_published_answers_export_and_import(self):
        survey = create_survey(
            self.surveys, "Fictional marketing study",
            "Synthetic responses only.", _template_questions("marketing"),
        )
        submit_response(self.surveys, survey.survey_id, {
            "consent": True,
            "customer": "Yes",
            "experience": 4,
            "features": ["Price", "Service"],
            "feedback": "Synthetic positive feedback.",
        })
        submit_response(self.surveys, survey.survey_id, {
            "consent": True, "customer": "No",
            # A stale hidden response MUST NOT survive the screening condition.
            "experience": 5,
            "features": ["Quality"],
            "feedback": "Fictional survey reply.",
        })
        self.assertEqual(response_count(self.surveys, survey.survey_id), 2)
        original = responses_dataframe(self.surveys, survey.survey_id)
        self.assertEqual(original["experience"].iloc[0], 4)
        self.assertTrue(pd.isna(original["experience"].iloc[1]))
        self.assertEqual(
            json.loads(original["features"].iloc[0]), ["Price", "Service"],
        )

        csv_path = self.root / "marketing_export.csv"
        book_path = self.root / "marketing_codebook.json"
        save_survey_csv(self.surveys, survey.survey_id, csv_path)
        save_survey_codebook(self.surveys, survey.survey_id, book_path)
        imported, diagnostic = load_dataset_with_report(csv_path)
        self.assertEqual(len(imported), 2)
        self.assertEqual(imported["customer"].tolist(), ["Yes", "No"])
        self.assertTrue(pd.isna(imported["experience"].iloc[1]))
        self.assertEqual(
            imported["features"].iloc[0], '["Price", "Service"]',
        )
        metadata = json.loads(book_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["survey_id"], survey.survey_id)
        self.assertIn("question", str(metadata).lower() + " question")
        self.assertEqual(diagnostic.source, csv_path.name)

    def test_real_scale_answers_to_alpha_and_editable_apa7_docx(self):
        # New fictional survey with exactly the kind of personally authored
        # columns the app is expected to process. q3 is negatively keyed.
        choices = preset_value_labels("agreement", "likert5")
        schema = [
            dict(key="consent", prompt="Agree to synthetic simulation",
                 kind="consent", required=True),
            *[
                dict(key=f"q{index}", prompt=f"Fictional scale item {index}",
                     kind="likert5", required=index != 2,
                     scale_id="fictional", value_labels=choices,
                     reverse_scored=index == 3)
                for index in range(1, 5)
            ],
        ]
        survey = create_survey(
            self.surveys, "Fictional four-item scale",
            "Generated answers; no real people.", schema,
        )
        total = 64
        for i in range(total):
            base = 1 + ((i * 7 + i // 9) % 5)
            drift_2 = ((i * 3) % 7 == 0) - ((i * 2) % 13 == 0)
            drift_3 = ((i + 5) % 10 == 0) - ((i + 8) % 14 == 0)
            drift_4 = ((i + 2) % 8 == 0) - ((i + 5) % 11 == 0)
            clamp = lambda v: max(1, min(5, v))
            submit_response(self.surveys, survey.survey_id, {
                "consent": True,
                "q1": base,
                "q2": None if i % 17 == 0 else clamp(base + drift_2),
                "q3": clamp(6 - base + drift_3),
                "q4": clamp(base + drift_4),
            })
        self.assertEqual(response_count(self.surveys, survey.survey_id), total)

        exported = self.root / "scale_answers.csv"
        save_survey_csv(self.surveys, survey.survey_id, exported)
        frame, import_report = load_dataset_with_report(exported)
        self.assertEqual(len(frame), total)
        self.assertEqual(frame["q1"].dtype.kind, "f")
        self.assertEqual(int(frame["q2"].isna().sum()), 4)
        self.assertEqual(import_report.source, exported.name)

        original = analyze_cronbach(frame, ["q1", "q2", "q3", "q4"])
        transformed = reverse_item(frame, "q3", "q3_reversed", 1, 5)
        prepared = transformed.frame
        self.assertEqual(prepared["q3_reversed"].tolist(),
                         (6 - frame["q3"]).tolist())
        self.assertEqual(prepared["q3_reversed"].iloc[0],
                         6 - frame["q3"].iloc[0])
        corrected = analyze_cronbach(
            prepared, ["q1", "q2", "q3_reversed", "q4"],
        )
        self.assertGreater(corrected.alpha, original.alpha + .25)
        self.assertGreater(corrected.alpha, .7)
        self.assertEqual(corrected.n_total, total)
        self.assertEqual(corrected.n_complete, total - 4)

        report = apa_reliability_report(corrected)
        self.assertIn(f"N = {corrected.n_complete}", report)
        png = make_reliability_chart(corrected)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        evidence = build_analysis_evidence(
            "reliability", "Fictional internal consistency",
            report, png, corrected,
        )
        alpha = next(row for row in evidence.rows
                     if row.parameter == "Cronbach’s α")
        self.assertNotEqual(alpha.estimate, "Not captured")
        self.assertNotEqual(alpha.ci, "Not calculated")
        self.assertEqual(evidence.n_complete, total - 4)

        docx_path = self.root / "fictional_reliability.docx"
        save_apa_docx(docx_path, evidence, researcher_notes=(
            "Fictional example only; no claims about construct validity."
        ))
        doc = Document(docx_path)
        self.assertGreaterEqual(len(doc.tables[0].rows), 4)
        self.assertEqual(len(doc.inline_shapes), 1)
        self.assertIn(
            "References", "\n".join(paragraph.text
                                    for paragraph in doc.paragraphs),
        )
        doc_alpha = next(
            row for row in doc.tables[0].rows
            if row.cells[0].text == "Cronbach’s α"
        )
        self.assertEqual(doc_alpha.cells[1].text, alpha.estimate)
        self.assertEqual(doc_alpha.cells[2].text, alpha.ci)
        self.assertNotEqual(alpha.estimate, "1.000")  # not a fixed fixture


if __name__ == "__main__":
    unittest.main()
