"""Tests for offline questionnaire storage, response validation and Pandas transfer."""

from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

import pandas as pd

from survey_storage import (
    create_survey, get_survey, list_surveys, validate_questions,
    submit_response, response_count, responses_dataframe, save_survey_csv,
)


QUESTIONS = [
    {
        "key": "consent", "prompt": "I agree to the fictional pilot study.",
        "kind": "consent", "required": True, "options": [],
    },
    {
        "key": "group", "prompt": "Select your study group",
        "kind": "single_choice", "required": True, "options": ["A", "B"],
    },
    {
        "key": "stress_q1", "prompt": "Stress statement one",
        "kind": "likert5", "required": True, "options": [],
    },
    {
        "key": "stress_q2", "prompt": "Stress statement two",
        "kind": "likert5", "required": False, "options": [],
    },
    {
        "key": "age", "prompt": "Age in years",
        "kind": "number", "required": False, "options": [],
    },
]


class SurveyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "surveys"
        self.definition = create_survey(
            self.root, "Local test survey", "No real respondent data", QUESTIONS
        )

    def response(self, **overrides):
        base = {
            "consent": True, "group": "A", "stress_q1": "3",
            "stress_q2": 4, "age": "27",
        }
        base.update(overrides)
        return base

    def test_definition_persists_and_is_listed(self):
        definition = get_survey(self.root, self.definition.survey_id)
        self.assertEqual(definition.title, "Local test survey")
        self.assertEqual(len(definition.questions), 5)
        self.assertEqual(len(list_surveys(self.root)), 1)
        self.assertEqual(response_count(self.root, definition.survey_id), 0)

    def test_submit_and_load_dataframe_for_analysis(self):
        sid = self.definition.survey_id
        a = submit_response(self.root, sid, self.response())
        b = submit_response(
            self.root, sid, self.response(
                group="B", stress_q1="5", stress_q2=None, age=None
            )
        )
        self.assertNotEqual(a, b)
        frame = responses_dataframe(self.root, sid)
        self.assertEqual(frame.shape, (2, 6))
        self.assertEqual(frame["stress_q1"].tolist(), [3, 5])
        self.assertTrue(pd.isna(frame.loc[1, "age"]))
        self.assertEqual(frame.loc[1, "group"], "B")
        self.assertNotIn("submitted_at", frame.columns)
        self.assertEqual(response_count(self.root, sid), 2)

    def test_invalid_consent_fails_without_partial_submission(self):
        sid = self.definition.survey_id
        with self.assertRaisesRegex(ValueError, "Consent"):
            submit_response(self.root, sid, self.response(consent=False))
        self.assertEqual(response_count(self.root, sid), 0)

    def test_required_missing_and_out_of_range_values_rejected(self):
        sid = self.definition.survey_id
        with self.assertRaisesRegex(ValueError, "Required"):
            submit_response(self.root, sid, self.response(group=""))
        with self.assertRaisesRegex(ValueError, "1–5"):
            submit_response(self.root, sid, self.response(stress_q1=6))
        with self.assertRaisesRegex(ValueError, "listed option"):
            submit_response(self.root, sid, self.response(group="C"))
        with self.assertRaisesRegex(ValueError, "Numeric answer"):
            submit_response(self.root, sid, self.response(age="unknown"))
        self.assertEqual(response_count(self.root, sid), 0)

    def test_invalid_schema_and_duplicate_variables_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_questions(QUESTIONS + [QUESTIONS[-1]])
        with self.assertRaisesRegex(ValueError, "Invalid"):
            validate_questions([
                {"key": "response_id", "prompt": "Forbidden ID",
                 "kind": "short_text", "required": False, "options": []}
            ])
        with self.assertRaisesRegex(ValueError, "Consent"):
            validate_questions([
                {"key": "consent", "prompt": "I agree",
                 "kind": "consent", "required": False, "options": []}
            ])

    def test_no_unknown_answer_keys(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            submit_response(
                self.root, self.definition.survey_id,
                self.response(private_name="Should not be stored"),
            )

    def test_csv_export_is_explicit_not_automatic(self):
        sid = self.definition.survey_id
        output = Path(self.tmp.name) / "responses.csv"
        with self.assertRaisesRegex(ValueError, "no responses"):
            save_survey_csv(self.root, sid, output)
        submit_response(self.root, sid, self.response())
        saved = save_survey_csv(self.root, sid, output)
        self.assertTrue(saved.is_file())
        self.assertIn("stress_q1", saved.read_text(encoding="utf-8-sig"))
        self.assertNotIn("submitted_at", saved.read_text(encoding="utf-8-sig"))

    def test_invalid_survey_id_cannot_escape_storage_folder(self):
        with self.assertRaisesRegex(ValueError, "Invalid survey"):
            get_survey(self.root, "../../outside")
        self.assertEqual(len(list_surveys(self.root)), 1)

    def test_responses_stay_local_in_sqlite(self):
        sid = self.definition.survey_id
        submit_response(self.root, sid, self.response())
        path = self.root / f"survey_{sid}.sqlite3"
        self.assertTrue(path.is_file())
        with closing(sqlite3.connect(path)) as db:
            rows = db.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        self.assertEqual(rows, 1)


if __name__ == "__main__":
    unittest.main()
