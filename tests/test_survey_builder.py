"""Survey builder tests: skip logic, safe metadata, response types and codebooks."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from survey_storage import (
    create_survey, get_survey, validate_questions, submit_response,
    responses_dataframe, response_count, survey_codebook,
    save_survey_codebook, question_is_visible, likert_choices,
    reorder_questions, validate_page_answers,
)
from survey_ui import _template_questions, preset_value_labels, parse_value_labels


def test_questions():
    return [
        dict(
            key="consent", prompt="Agree to fictional pilot",
            kind="consent", required=True, section="Information",
        ),
        dict(
            key="employed", prompt="Are you employed?",
            kind="yes_no", required=True, section="Demographics",
        ),
        dict(
            key="years", prompt="Years employed",
            kind="number", required=True, section="Demographics",
            condition={
                "question": "employed", "operator": "equals", "value": "Yes",
            },
        ),
        dict(
            key="long_service", prompt="Additional years information",
            kind="long_text", required=True,
            condition={
                "question": "years", "operator": "greater", "value": "5",
            },
        ),
        dict(
            key="rating", prompt="Original seven point statement",
            kind="likert7", required=True,
            section="Research scale", scale_id="research",
            reverse_scored=True, min_label="Never", max_label="Always",
        ),
        dict(
            key="interests", prompt="Choose several topics",
            kind="multiple_choice", required=False,
            options=["Work", "Family", "Study"],
        ),
        dict(
            key="entry_date", prompt="Date of participation",
            kind="date", required=False,
        ),
    ]


class SurveyBuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.q = validate_questions(test_questions())
        self.survey = create_survey(
            self.path, "Fictional research survey",
            "No real participants", self.q,
        )

    def test_templates_are_valid_and_nonclinical(self):
        for name in ("psychology", "demographics", "marketing", "hr"):
            items = validate_questions(_template_questions(name))
            self.assertGreaterEqual(len(items), 3)
            self.assertEqual(items[0]["kind"], "consent")
        q = validate_questions(_template_questions("psychology"))
        reverse = [item for item in q if item["reverse_scored"]]
        self.assertEqual(len(reverse), 1)
        self.assertEqual(reverse[0]["scale_id"], "stress")

    def test_branching_does_not_store_skipped_required_questions(self):
        sid = self.survey.survey_id
        submit_response(
            self.path, sid,
            {
                "consent": True, "employed": "No",
                "years": 12, "long_service": "stale hidden form answer",
                "rating": "6",
            },
        )
        frame = responses_dataframe(self.path, sid)
        self.assertEqual(len(frame), 1)
        self.assertTrue(pd.isna(frame.loc[0, "years"]))
        self.assertTrue(pd.isna(frame.loc[0, "long_service"]))
        self.assertEqual(frame.loc[0, "rating"], 6)
        self.assertEqual(response_count(self.path, sid), 1)

    def test_conditional_required_fields_only_when_visible(self):
        sid = self.survey.survey_id
        with self.assertRaisesRegex(ValueError, "Required"):
            submit_response(
                self.path, sid,
                {"consent": True, "employed": "Yes", "rating": 4},
            )
        with self.assertRaisesRegex(ValueError, "Required"):
            submit_response(
                self.path, sid,
                {
                    "consent": True, "employed": "Yes",
                    "years": 8, "rating": 3,
                },
            )
        submit_response(
            self.path, sid,
            {
                "consent": True, "employed": "Yes", "years": 2,
                "rating": 7,
            },
        )
        self.assertEqual(response_count(self.path, sid), 1)
        self.assertTrue(pd.isna(responses_dataframe(self.path, sid).loc[0, "long_service"]))

    def test_numeric_condition_and_visibility_cascade(self):
        q = self.q
        self.assertFalse(question_is_visible(q[2], {"employed": "No"}))
        self.assertFalse(question_is_visible(q[3], {"years": None}))
        self.assertFalse(question_is_visible(q[3], {"years": 2}))
        self.assertTrue(question_is_visible(q[3], {"years": 7}))

    def test_cannot_reference_future_or_free_text_condition(self):
        future = test_questions()
        future[0]["condition"] = {
            "question": "employed", "operator": "equals", "value": "Yes",
        }
        with self.assertRaisesRegex(ValueError, "EARLIER"):
            validate_questions(future)
        invalid = test_questions()
        invalid[3]["condition"] = {
            "question": "consent", "operator": "equals", "value": "Yes",
        }
        with self.assertRaisesRegex(ValueError, "choice or numeric"):
            validate_questions(invalid)

    def test_consent_cannot_be_hidden_by_skip_logic(self):
        questions = test_questions()
        questions[0]["condition"] = {
            "question": "employed", "operator": "equals", "value": "Yes"
        }
        with self.assertRaises(ValueError):
            validate_questions(questions)
        questions = test_questions()
        questions.insert(1, dict(
            key="additional_consent", prompt="Additional consent",
            kind="consent", required=True,
            condition={
                "question": "employed", "operator": "equals", "value": "Yes"
            },
        ))
        with self.assertRaises(ValueError):
            validate_questions(questions)

    def test_reject_unknown_conditional_values_and_unsafe_expressions(self):
        cases = [
            {"question": "employed", "operator": "equals", "value": "Maybe"},
            {"question": "employed", "operator": "__import__", "value": "Yes"},
            {"question": "employed", "operator": "greater", "value": "Yes"},
        ]
        for condition in cases:
            original = test_questions()
            original[2]["condition"] = condition
            with self.assertRaises(ValueError):
                validate_questions(original)

    def test_reverse_code_is_metadata_and_raw_answer_stays_unchanged(self):
        sid = self.survey.survey_id
        submit_response(
            self.path, sid,
            {"consent": True, "employed": "No", "rating": "1"},
        )
        values = responses_dataframe(self.path, sid)
        self.assertEqual(values.loc[0, "rating"], 1)
        saved = get_survey(self.path, sid)
        scored = [q for q in saved.questions if q["key"] == "rating"][0]
        self.assertTrue(scored["reverse_scored"])
        self.assertEqual(scored["scale_id"], "research")
        codebook = survey_codebook(self.path, sid)
        self.assertIn("METADATA ONLY", codebook["scoring_note"])
        target = self.path / "codebook.json"
        save_survey_codebook(self.path, sid, target)
        self.assertTrue(json.loads(target.read_text(encoding="utf-8"))["questions"][4]["reverse_scored"])

    def test_multi_choice_date_and_long_text(self):
        sid = self.survey.survey_id
        submit_response(
            self.path, sid, {
                "consent": True, "employed": "No", "rating": 5,
                "interests": ["Work", "Study"], "entry_date": "2026-11-03",
            },
        )
        frame = responses_dataframe(self.path, sid)
        self.assertEqual(json.loads(frame.loc[0, "interests"]), ["Work", "Study"])
        self.assertEqual(frame.loc[0, "entry_date"], "2026-11-03")

    def test_invalid_multi_choice_and_date_rejected(self):
        sid = self.survey.survey_id
        for item in (
            {"interests": ["Work", "Unknown"]},
            {"interests": ["Work", "Work"]},
            {"entry_date": "2026-02-30"},
        ):
            with self.assertRaises(ValueError):
                submit_response(
                    self.path, sid,
                    {"consent": True, "employed": "No", "rating": 2, **item},
                )
        self.assertEqual(response_count(self.path, sid), 0)

    def test_existing_old_survey_format_works(self):
        questions = [
            dict(
                key="group", prompt="Select group", kind="single_choice",
                required=True, options=["A", "B"],
            ),
            dict(
                key="q1", prompt="Original item one", kind="likert5",
                required=False, options=[],
            ),
        ]
        created = create_survey(
            self.path, "Older pilot survey", "Compatibility test", questions
        )
        submit_response(self.path, created.survey_id, {"group": "B", "q1": 3})
        frame = responses_dataframe(self.path, created.survey_id)
        self.assertEqual(frame.loc[0, "group"], "B")
        self.assertEqual(frame.loc[0, "q1"], 3)
        self.assertIsNone(get_survey(self.path, created.survey_id).questions[1]["condition"])

    def test_text_labels_are_display_only_raw_scores_remain_numeric(self):
        labels = {
            "1": "Очень плохо", "2": "Плохо", "3": "Средне",
            "4": "Хорошо", "5": "Очень хорошо",
        }
        questions = [
            dict(key="agree", prompt="Consent to fictional pilot",
                 kind="consent", required=True, page=1,
                 page_title="Introduction", section="Study information"),
            dict(key="quality", prompt="Rate this fictional experience",
                 kind="likert5", required=True, page=2,
                 page_title="Experience", section="Ratings",
                 value_labels=labels, scale_id="experience"),
        ]
        created = create_survey(
            self.path, "Quality label test", "Artificial responses", questions
        )
        saved = get_survey(self.path, created.survey_id)
        self.assertEqual(
            likert_choices(saved.questions[1])[2], (3, "3 — Средне")
        )
        submit_response(self.path, created.survey_id, {
            "agree": True, "quality": "5",
        })
        data = responses_dataframe(self.path, created.survey_id)
        self.assertEqual(data["quality"].iloc[0], 5)
        self.assertTrue(pd.api.types.is_numeric_dtype(data["quality"]))
        book = survey_codebook(self.path, created.survey_id)
        self.assertEqual(book["questions"][1]["value_labels"]["5"], "Очень хорошо")
        self.assertEqual(book["questions"][1]["measurement_level"], "ordinal")
        self.assertEqual(book["questions"][1]["page"], 2)

    def test_page_navigation_and_conditional_validation(self):
        questions = validate_questions([
            dict(key="accept", prompt="Fictional consent", kind="consent",
                 required=True, page=1, page_title="Intro"),
            dict(key="rating", prompt="Choose a rating", kind="likert5",
                 required=True, page=2, page_title="Scale",
                 value_labels=preset_value_labels("quality", "likert5")),
            dict(key="details", prompt="Explain higher ratings",
                 kind="short_text", required=True, page=2,
                 condition={"question": "rating", "operator": "greater",
                            "value": 3}),
        ])
        with self.assertRaisesRegex(ValueError, "Consent"):
            validate_page_answers(questions, {}, 1)
        validate_page_answers(questions, {"accept": True}, 1)
        validate_page_answers(
            questions, {"accept": True, "rating": "2"}, 2
        )
        with self.assertRaisesRegex(ValueError, "Required"):
            validate_page_answers(
                questions, {"accept": True, "rating": "5"}, 2
            )
        validate_page_answers(
            questions, {"accept": True, "rating": "5", "details": "Test"}, 2
        )

    def test_reordering_keeps_conditions_and_pages_valid(self):
        questions = validate_questions([
            dict(key="first", prompt="First choice", kind="yes_no", page=1),
            dict(key="second", prompt="Independent text", kind="short_text", page=1),
            dict(key="follow", prompt="Conditional follow-up", kind="short_text",
                 page=1, condition={
                     "question": "first", "operator": "equals", "value": "Yes",
                 }),
            dict(key="last", prompt="Final question", kind="likert5",
                 page=2, page_title="Final"),
        ])
        valid = reorder_questions(questions, 1, 2)
        self.assertEqual([q["key"] for q in valid], [
            "first", "follow", "second", "last",
        ])
        with self.assertRaisesRegex(ValueError, "EARLIER"):
            reorder_questions(questions, 0, 2)
        with self.assertRaisesRegex(ValueError, "page"):
            reorder_questions(questions, 3, 1)
        self.assertEqual(questions[0]["key"], "first")

    def test_scale_label_and_page_schema_rejections(self):
        item = dict(key="q", prompt="Survey rating", kind="likert5")
        incomplete = {str(i): f"Label {i}" for i in range(1, 5)}
        with self.assertRaisesRegex(ValueError, "every numeric"):
            validate_questions([{**item, "value_labels": incomplete}])
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate_questions([{
                **item, "value_labels": {str(i): "Same" for i in range(1, 6)}
            }])
        with self.assertRaisesRegex(ValueError, "page 1"):
            validate_questions([{**item, "page": 2}])
        with self.assertRaisesRegex(ValueError, "page title"):
            validate_questions([
                {**item, "page_title": "Part A"},
                dict(key="q2", prompt="Another rating", kind="likert5",
                     page_title="Part B"),
            ])
        self.assertEqual(len(parse_value_labels(
            "1 = Очень плохо\\n2 = Плохо\\n3 = Средне\\n4 = Хорошо\\n5 = Очень хорошо",
            "likert5",
        )), 5)
        with self.assertRaisesRegex(ValueError, "Label every"):
            parse_value_labels("1 = Bad", "likert5")


if __name__ == "__main__":
    unittest.main()
