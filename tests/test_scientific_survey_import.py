"""Scientific questionnaire import regression: version, scoring, provenance, refusal.

Fixtures are synthetic analogues of user-provided document structures.
Do not commit copyrighted questionnaires or clinical score thresholds.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from docx import Document
from pypdf import PdfWriter

from scientific_survey_import import (
    parse_scientific_lines, read_scientific_document, reviewed_draft,
)


def numbered(lines):
    return [(1, line) for line in lines]


class ScientificQuestionnaireTests(unittest.TestCase):
    def test_pss_like_frequency_survey_makes_reviewed_reverse_key(self):
        content = [
            "Perceived Stress Scale",
            "For each question choose from the following alternatives:",
            "0 - never  1 - almost never  2 - sometimes  3 - fairly often  4 - very often",
        ]
        content += [
            f"________ {'l' if n == 1 else n}. In the last month have you "
            f"experienced fictional situation {n} that was difficult "
            f"to manage?" for n in range(1, 11)
        ]
        content += [
            "Figuring Your PSS Score",
            "First, reverse your scores for questions 4, 5, 7, and 8.",
            "Then add up the items; do not infer population cutoffs.",
        ]
        result = parse_scientific_lines(numbered(content), "synthetic_pss.pdf")
        self.assertEqual(len(result.instruments), 1)
        inst = result.instruments[0]
        self.assertEqual(len(inst.questions), 10)
        self.assertEqual(inst.questions[0].number, 1)
        self.assertEqual(inst.questions[0].question["kind"], "rating_scale")
        self.assertEqual(inst.questions[0].question["value_labels"]["0"], "never")
        self.assertEqual(inst.scoring.reverse_numbers, (4, 5, 7, 8))
        unscored = reviewed_draft(inst)
        self.assertTrue(all(q["kind"] == "single_choice" for q in unscored))
        self.assertFalse(any(q.get("reverse_scored") for q in unscored))
        numeric = reviewed_draft(inst, accept_numeric=True)
        self.assertEqual(numeric[0]["kind"], "rating_scale")
        self.assertFalse(any(q.get("reverse_scored") for q in numeric))
        approved = reviewed_draft(inst, accept_numeric=True, accept_reverse=True)
        self.assertEqual(
            [i for i, q in enumerate(approved, 1) if q["reverse_scored"]],
            [4, 5, 7, 8],
        )

    def test_isma_like_yes_no_table_has_25_distinct_real_questions(self):
        lines = [
            "Stress Questionnaire",
            "This stress instrument is not a diagnosis.",
            "Yes No",
        ]
        lines += [
            f"{i}  In the past week I have encountered fictional "
            f"stress situation number {i}" for i in range(1, 26)
        ]
        lines += ["A yes answer score = one; no answer score = zero.",
                  "Your score:", "4 points or less"]
        parsed = parse_scientific_lines(numbered(lines), "practice-stress.pdf")
        inst = parsed.instruments[0]
        self.assertEqual(len(inst.questions), 25)
        self.assertTrue(all(q.question["kind"] == "single_choice"
                            for q in inst.questions))
        self.assertEqual(inst.questions[14].question["options"], ["Yes", "No"])
        self.assertFalse(any(q.question.get("value_labels")
                             for q in inst.questions))
        self.assertTrue(any("NOT applied" in warning for warning in inst.warnings))

    def test_short_ucla_like_scale_does_not_import_anchors_as_questions(self):
        lines = ["UCLA Loneliness Scale – Questionnaire (short version).",
                 "Scale of 1-4", "1- Never", "2- Rarely",
                 "3- Sometimes", "4- Always"]
        lines += [
            f"{n}) How frequently did fictional experience number {n} "
            f"occur during the last month?"
            for n in range(1, 11)
        ]
        lines += ["SCORES", "20 = average", "30+ = Very high"]
        parsed = parse_scientific_lines(numbered(lines), "synthetic_ucla.pdf")
        self.assertEqual(len(parsed.instruments), 1)
        inst = parsed.instruments[0]
        self.assertEqual(len(inst.questions), 10)
        self.assertEqual(
            dict(inst.scoring.code_labels),
            {"1":"Never","2":"Rarely","3":"Sometimes","4":"Always"},
        )

    def test_collection_isolates_versions_and_does_not_merge_items(self):
        lines = []
        for heading, page in [
            ("UCLA LONELINESS SCALE", 2),
            ("REVISED UCLA LONELINESS SCALE", 4),
            ("UCLA LONELINESS SCALE VERSION 3", 6),
        ]:
            lines += [
                (page, heading),
                (page, "Reference:"),
                (page, "1. This is a journal citation not an item."),
                (page, "Scale:"),
                (page, "INSTRUCTIONS: Circle one response for each item"),
            ]
            lines += [
                (page, f"{i}. Fictional loneliness item number {i} "
                       "in a local example only 1 2 3 4")
                for i in range(1, 21)
            ]
            lines += [(page, "Scoring:"), (page, "Keep scoring continuous.")]
        parsed = parse_scientific_lines(
            lines, "Self_Measures_LONELINESS_AND_INTERPERSONAL.pdf",
            page_count=8,
        )
        self.assertEqual(len(parsed.instruments), 3)
        self.assertEqual(
            [len(group.questions) for group in parsed.instruments],
            [20, 20, 20],
        )
        self.assertEqual(parsed.instruments[2].first_page, 6)
        self.assertEqual(parsed.instruments[1].questions[4].number, 5)
        self.assertTrue(any("never merge" in w for w in parsed.warnings))

    def test_image_only_scale_with_bibliography_cannot_be_misimported(self):
        lines = [
            (1,"64"),
            (1,"Purpose This is a research scale discussion"),
            (2,"References"),
            (2,"1. Levenstein, S., Prantera, C., Varvo, V. (1993)."),
            (2,"2. Another bibliography citation from a journal."),
        ]
        with self.assertRaisesRegex(ValueError, "No numbered questions"):
            parse_scientific_lines(
                lines, "synthetic_image_scale.pdf",
                page_count=2, image_pages=(2,),
            )

    def test_legacy_word_table_and_conditional_instruction(self):
        lines = numbered([
            "RESEARCH QUESTIONNAIRE",
            "Section A: Socio-Demographic Characteristics",
            "|1 |What is your gender? |[ ] Male",
            "|  | |[ ] Female",
            "|2 |What is your age range? |[ ] Under 18",
            "|  | |[ ] 18 or over",
            "Section B: Awareness",
            "|3 |Have you attended a fictional training programme? |[ ] Yes",
            "|  | |[ ] No",
            "|4 |If Yes to Question 3, which programme did you attend? |",
        ])
        parsed = parse_scientific_lines(lines, "synthetic_survey.doc")
        inst = parsed.instruments[0]
        self.assertEqual(len(inst.questions), 4)
        self.assertEqual(inst.questions[0].question["options"], ["Male","Female"])
        self.assertEqual(inst.questions[1].question["section"],
                         "Section A: Socio-Demographic Characteristics")
        self.assertEqual(inst.questions[2].question["section"],
                         "Section B: Awareness")
        self.assertTrue(any("conditional" in n.lower() for n in inst.warnings))
        self.assertFalse(any(q.question.get("condition") for q in inst.questions))

    def test_paragraph_word_read_and_source_provenance(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "survey.docx"
            document = Document()
            document.add_paragraph("1. What did you like about the service?")
            document.add_paragraph("A) Quality")
            document.add_paragraph("B) Friendliness")
            document.add_paragraph("2. Any comments?")
            document.save(path)
            parsed = read_scientific_document(path)
            inst = parsed.instruments[0]
            self.assertEqual(len(inst.questions), 2)
            self.assertEqual(inst.questions[0].page, 1)
            self.assertEqual(inst.questions[0].question["options"],
                             ["Quality", "Friendliness"])

    def test_scanned_pdf_empty_text_explicitly_rejected(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "scanned.pdf"
            pdf = PdfWriter()
            pdf.add_blank_page(width=612,height=792)
            with path.open("wb") as handle:
                pdf.write(handle)
            with self.assertRaisesRegex(ValueError, "OCR"):
                read_scientific_document(path)


if __name__ == "__main__":
    unittest.main()
