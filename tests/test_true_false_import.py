"""True/False, T/F and Yes/No answer formats in PDF, DOCX and OCR imports.

All statements are synthetic (generated), not items of a published inventory.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import flet as ft

from binary_responses import (
    TRUE_FALSE, YES_NO, expand_with_legend, legend_labels, match_header,
    match_instruction, split_row, strip_noisy_row_pair,
)
from matrix_reconstruction import docx_matrices, geometric_matrices, matrix_to_questions, verify_matrix
from ocr_runtime import tesseract_available
from scientific_survey_import import parse_scientific_lines, read_scientific_document, reviewed_draft
from synthetic_documents import (
    image_pdf, true_false_docx, true_false_scan_pages, true_false_statements,
    true_false_text_pdf,
)
from visual_survey_review import apply_response_format, ocr_scientific_pdf, pdf_text_layer_page


def lines(rows, page=1):
    return [(page, row) for row in rows]


def kinds(instrument):
    found = {}
    for q in instrument.questions:
        found[q.question["kind"]] = found.get(q.question["kind"], 0) + 1
    return found


def assert_binary(test, instrument, labels, count=60):
    test.assertEqual(len(instrument.questions), count)
    test.assertEqual(kinds(instrument), {"single_choice": count})
    test.assertEqual({tuple(q.question["options"]) for q in instrument.questions}, {labels})
    test.assertFalse(any(q.question.get("value_labels") for q in instrument.questions))
    test.assertFalse(any(q.question.get("reverse_scored") for q in instrument.questions))
    test.assertEqual(instrument.scoring.code_labels, ())
    test.assertTrue(any("NOT applied" in w for w in instrument.warnings))


class DetectorTests(unittest.TestCase):
    def test_headers_in_three_languages_and_ocr_variants(self):
        cases = {
            "T F": (TRUE_FALSE, ("T", "F")), "T / F": (TRUE_FALSE, ("T", "F")),
            "T | F": (TRUE_FALSE, ("T", "F")), "T|F": (TRUE_FALSE, ("T", "F")),
            "Т F": (TRUE_FALSE, ("T", "F")),  # Cyrillic Т from eng+rus OCR
            "TRUE  FALSE": (TRUE_FALSE, ("True", "False")),
            "Statement True False": (TRUE_FALSE, ("True", "False")),
            "No. Statement T F": (TRUE_FALSE, ("T", "F")),
            "Yes No": (YES_NO, ("Yes", "No")), "yes / no": (YES_NO, ("Yes", "No")),
            "Верно Неверно": (TRUE_FALSE, ("Верно", "Неверно")),
            "Утверждение Да Нет": (YES_NO, ("Да", "Нет")),
            "Jā Nē": (YES_NO, ("Jā", "Nē")),
            "Patiesi Nepatiesi": (TRUE_FALSE, ("Patiesi", "Nepatiesi")),
        }
        for text, (kind, labels) in cases.items():
            scale = match_header(text)
            self.assertIsNotNone(scale, text)
            self.assertEqual((scale.kind, scale.labels), (kind, labels), text)

    def test_rows_are_detected_but_prose_is_not(self):
        rest, scale = split_row("12. I enjoy invented trips.   T  F")
        self.assertEqual((rest, scale.labels), ("12. I enjoy invented trips.", ("T", "F")))
        rest, scale = split_row("T F 12. I enjoy invented trips.")
        self.assertEqual(rest, "12. I enjoy invented trips.")
        self.assertEqual(split_row("4. I like it | T | F |")[1].labels, ("T", "F"))
        for prose in ("12. Do you smoke, yes or no?", "3. I can say Yes No to all",
                      "12. I tell the truth T"):
            self.assertIsNone(split_row(prose)[1], prose)
        self.assertIsNone(match_header("Is it true or false that you sleep well?"))
        self.assertIsNone(match_instruction("Is it true or false that you sleep well?"))
        rest, scale = strip_noisy_row_pair("2. My invented team plans trips. tT F")
        self.assertEqual(rest, "2. My invented team plans trips.")
        self.assertIsNone(strip_noisy_row_pair("9. We met at Fort F")[1])

    def test_instructions_and_legends(self):
        for text in ("Answer each statement True or False.",
                     "Ответьте «Верно» или «Неверно» на каждое утверждение.",
                     "Atbildiet uz katru apgalvojumu Jā vai Nē."):
            self.assertIsNotNone(match_instruction(text), text)
        legend = legend_labels("Circle T = True or F = False.")
        self.assertEqual(legend, {"T": "True", "F": "False"})
        expanded = expand_with_legend(match_header("T F"), legend)
        self.assertEqual(expanded.labels, ("True", "False"))
        self.assertEqual(expand_with_legend(match_header("T F"), {}).labels, ("T", "F"))


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.statements = true_false_statements(60)

    def test_shared_header_applies_to_sixty_items(self):
        rows = ["Synthetic habits form", "T F"] + [
            f"{n}. {text}" for n, text in enumerate(self.statements, 1)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "habits.pdf").instruments
        assert_binary(self, inst, ("T", "F"))
        (fmt,) = inst.response_formats
        self.assertEqual((fmt.evidence, fmt.kind, len(fmt.applied_to)), ("header", TRUE_FALSE, 60))
        self.assertIn("shared header", inst.questions[45].notes[-1])
        draft = reviewed_draft(inst)
        self.assertEqual(draft[45]["options"], ["T", "F"])
        self.assertFalse(any(q.get("value_labels") for q in draft))

    def test_per_row_labels_and_legend_expansion(self):
        rows = ["Synthetic habits form", "Circle T = True or F = False."] + [
            f"{n}. {text}  T  F" for n, text in enumerate(self.statements, 1)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "habits.pdf").instruments
        assert_binary(self, inst, ("True", "False"))
        self.assertEqual(inst.response_formats[0].evidence, "row")
        self.assertFalse(inst.questions[0].question["prompt"].endswith("F"))

    def test_russian_and_latvian_shared_headers(self):
        ru = ["Синтетическая анкета", "Верно Неверно"] + [
            f"{n}. Вымышленное утверждение номер {n} о привычках." for n in range(1, 61)
        ]
        (inst,) = parse_scientific_lines(lines(ru), "ru.pdf").instruments
        assert_binary(self, inst, ("Верно", "Неверно"))
        lv = ["Sintētiska aptauja", "Apgalvojums Jā Nē"] + [
            f"{n}. Izdomāts apgalvojums numur {n} par paradumiem." for n in range(1, 61)
        ]
        (inst,) = parse_scientific_lines(lines(lv), "lv.pdf").instruments
        assert_binary(self, inst, ("Jā", "Nē"))
        self.assertEqual(inst.response_formats[0].kind, YES_NO)

    def test_instruction_only_is_not_applied_without_review(self):
        rows = ["Synthetic habits form", "Answer each statement True or False."] + [
            f"{n}. {text}" for n, text in enumerate(self.statements, 1)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "habits.pdf").instruments
        self.assertEqual(kinds(inst), {"short_text": 60})
        (fmt,) = inst.response_formats
        self.assertEqual((fmt.evidence, len(fmt.candidates)), ("instruction", 60))
        reviewed = apply_response_format(inst, 0, fmt.labels)
        assert_binary(self, reviewed, ("True", "False"))
        self.assertEqual(reviewed.response_formats[0].candidates, ())
        self.assertIn("after review", reviewed.questions[59].notes[-1])

    def test_bulk_relabel_keeps_manual_edits(self):
        rows = ["Synthetic habits form", "T F"] + [
            f"{n}. {text}" for n, text in enumerate(self.statements, 1)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "habits.pdf").instruments
        from visual_survey_review import edit_candidate_question
        edited = edit_candidate_question(
            inst, 4, prompt=inst.questions[4].question["prompt"],
            kind="single_choice", options_text="Agree\nDisagree", section="",
        )
        renamed = apply_response_format(edited, 0, ("True", "False"))
        self.assertEqual(renamed.questions[4].question["options"], ["Agree", "Disagree"])
        self.assertEqual(renamed.questions[5].question["options"], ["True", "False"])
        with self.assertRaisesRegex(ValueError, "two different"):
            apply_response_format(inst, 0, ("True", "True"))

    def test_question_text_alone_never_converts(self):
        rows = ["Synthetic open form"] + [
            f"{n}. Is it true or false that invented habit {n} matters to you?"
            for n in range(1, 11)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "open.pdf").instruments
        self.assertEqual(kinds(inst), {"short_text": 10})
        self.assertEqual(inst.response_formats, ())

    def test_header_after_open_items_does_not_convert_them(self):
        rows = ["Synthetic mixed form",
                "1. Describe an invented hobby in your own words please.",
                "2. Describe a fictional place you would like to visit.",
                "Part two: answer each statement.", "T F"] + [
            f"{n}. {self.statements[n]}" for n in range(3, 13)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "mixed.pdf").instruments
        self.assertEqual([q.question["kind"] for q in inst.questions[:2]], ["short_text"] * 2)
        self.assertEqual(kinds(inst)["single_choice"], 10)

    def test_marked_binary_items_get_no_reverse_proposal(self):
        rows = ["Synthetic habits form", "T F"] + [
            f"{'*' if n in (3, 7) else ''}{n}. {text}"
            for n, text in enumerate(self.statements[:12], 1)
        ]
        (inst,) = parse_scientific_lines(lines(rows), "habits.pdf").instruments
        self.assertEqual(inst.scoring.reverse_numbers, ())
        self.assertTrue(any("keyed answers" in w for w in inst.scoring.warnings))


class DocumentReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def read(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        (inst,) = read_scientific_document(path).instruments
        return inst

    def test_pdf_text_layer_rows_and_header_only(self):
        assert_binary(self, self.read("rows.pdf", true_false_text_pdf()), ("T", "F"))
        header_only = self.read("header.pdf", true_false_text_pdf(row_labels=False))
        assert_binary(self, header_only, ("T", "F"))
        self.assertEqual([f.evidence for f in header_only.response_formats], ["header"])

    def test_docx_native_tables_and_paragraphs(self):
        assert_binary(self, self.read("table.docx", true_false_docx()), ("True", "False"))
        assert_binary(self, self.read("rows.docx", true_false_docx(row_labels=True, labels=("T", "F"))), ("T", "F"))
        assert_binary(self, self.read("nonum.docx", true_false_docx(number_column=False)), ("True", "False"))
        assert_binary(self, self.read("para.docx", true_false_docx(paragraphs=True)), ("T", "F"))
        assert_binary(self, self.read("para_yes.docx", true_false_docx(paragraphs=True, header_line="Yes / No")), ("Yes", "No"))

    def test_matrix_integration_for_binary_columns(self):
        (matrix,) = docx_matrices(true_false_docx(row_labels=True, labels=("T", "F")))
        self.assertEqual([c.label for c in matrix.columns], ["T", "F"])
        self.assertEqual(len(matrix.rows), 60)
        self.assertEqual(matrix.unresolved_cells, ())
        questions = matrix_to_questions(verify_matrix(matrix))
        self.assertEqual(questions[0]["options"], ["T", "F"])
        self.assertFalse(questions[0].get("value_labels"))
        pdf = true_false_text_pdf()
        from visual_survey_review import pdf_page_count
        pages = [pdf_text_layer_page(pdf, n) for n in range(1, pdf_page_count(pdf) + 1)]
        (matrix,) = geometric_matrices(pages)
        self.assertEqual([c.label for c in matrix.columns], ["T", "F"])
        self.assertEqual(len(matrix.rows), 60)


@unittest.skipUnless(tesseract_available(), "No local Tesseract engine installed")
class ScannedSixtyItemTests(unittest.TestCase):
    def test_scanned_pdf_with_row_labels(self):
        pdf = image_pdf(*true_false_scan_pages())
        review = ocr_scientific_pdf(pdf, "tf_scan.pdf", [1, 2, 3], "eng")
        (inst,) = review.instruments
        self.assertEqual(len(inst.questions), 60)
        self.assertEqual(kinds(inst), {"single_choice": 60})
        self.assertEqual({tuple(q.question["options"]) for q in inst.questions}, {("T", "F")})
        self.assertEqual(inst.scoring.code_labels, ())
        linked = sum(1 for j in range(60) if review.spatial.regions(f"0:{j}"))
        self.assertGreaterEqual(linked, 55)
        self.assertTrue(any([c.label for c in m.columns] == ["T", "F"] for m in review.matrices))

    def test_scanned_pdf_with_shared_header_only(self):
        pdf = image_pdf(*true_false_scan_pages(row_labels=False))
        review = ocr_scientific_pdf(pdf, "tf_header_scan.pdf", [1, 2, 3], "eng")
        (inst,) = review.instruments
        self.assertEqual(kinds(inst), {"single_choice": 60})
        self.assertEqual([f.evidence for f in inst.response_formats], ["header"])


class BinaryImportUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from survey_ui import build_survey_workspace
        from test_visual_survey_import_ui import DummyPage

        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.page = DummyPage()

        async def noop(frame):
            return True

        self.view = build_survey_workspace(self.page, root=self.root, load_dataframe=noop)

    async def pick(self, path):
        await self.page.services[-1].on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(path), name=path.name)]
        ))

    def texts(self):
        from test_visual_survey_import_ui import children
        return " ".join(c.value for c in children(self.view)
                        if isinstance(c, ft.Text) and isinstance(c.value, str))

    async def test_instruction_only_document_offers_reviewed_bulk_conversion(self):
        from docx import Document
        from io import BytesIO
        from test_visual_survey_import_ui import find

        document = Document()
        document.add_paragraph("Synthetic Everyday Habits Inventory")
        document.add_paragraph("Answer each statement True or False.")
        for n, text in enumerate(true_false_statements(60), 1):
            document.add_paragraph(f"{n}. {text}")
        stream = BytesIO()
        document.save(stream)
        path = self.root / "instruction_only.docx"
        path.write_bytes(stream.getvalue())
        await self.pick(path)
        picker = find(self.view, ft.Dropdown, label="Detected binary answer format")
        self.assertEqual(len(picker.options), 1)
        self.assertIn("60 text item(s) await review", self.texts())
        first = find(self.view, ft.TextField, label="First answer label")
        self.assertEqual(first.value, "True")
        button = find(self.view, ft.Button, label="Apply binary answers to matching items")
        button.on_click(None)
        self.assertIn("confirm that these items share", self.texts())
        approved = find(self.view, ft.Checkbox,
                        label="I verified the instrument version, wording, permissions "
                              "and extracted question list against the source")
        approved.value = True
        find(self.view, ft.Checkbox,
             label="I checked the source: these items share this answer format").value = True
        button.on_click(None)
        self.assertIn("applied to 60 item(s)", self.texts())
        self.assertFalse(approved.value)  # approvals reset after the bulk edit
        approved.value = True
        find(self.view, ft.Button, label="Use extracted questions as editable draft").on_click(None)
        self.assertIn("Imported 60 editable questions", self.texts())

    async def test_true_false_table_imports_as_binary_choices(self):
        from test_visual_survey_import_ui import find

        path = self.root / "tf_table.docx"
        path.write_bytes(true_false_docx())
        await self.pick(path)
        from test_visual_survey_import_ui import children
        editor_type = next(
            c for c in children(self.view) if isinstance(c, ft.Dropdown)
            and c.label == "Response type"
            and any(o.key == "rating_scale" and "proposed" in o.text for o in c.options)
        )
        self.assertEqual(editor_type.value, "single_choice")
        options = find(self.view, ft.TextField, label="Choice labels · one per line")
        self.assertEqual(options.value, "True\nFalse")
        self.assertIn("Applied to 60 item(s)", self.texts())


if __name__ == "__main__":
    unittest.main()
