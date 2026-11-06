"""Matrix (row × response column) reconstruction and editing regressions.

Every questionnaire here is synthetic: "PSS-like" and "UCLA-like" refer only
to the *layout* (0–4 frequency grid, 1–4 frequency grid), never to the
wording of the published instruments.
"""

import unittest

from matrix_reconstruction import (
    accept_cell, add_column, add_row, delete_column, delete_row,
    docx_matrices, geometric_matrices, matrix_to_questions, move_column,
    move_row, set_cell, set_column, set_row, verify_matrix,
)
from ocr_layout import page_from_plain_text
from synthetic_documents import (
    FREQUENCY_LABELS, docx_matrix, matrix_text_pdf, text_pdf,
)
from visual_survey_review import pdf_text_layer_page

PSS_LIKE_LABELS = ("Never", "Almost never", "Sometimes", "Fairly often", "Very often")
PSS_LIKE_ITEMS = (
    "How often did synthetic plans change unexpectedly?",
    "How often did fictional errands feel under control?",
    "How often did invented deadlines pile up?",
)
UCLA_LIKE_LABELS = ("Never", "Rarely", "Sometimes", "Often")
UCLA_LIKE_ITEMS = (
    "How often do you feel in tune with fictional neighbours?",
    "How often do you lack invented company?",
    "How often do you feel part of a synthetic group?",
)


def text_pages(pdf):
    from visual_survey_review import pdf_page_count
    return [pdf_text_layer_page(pdf, n) for n in range(1, pdf_page_count(pdf) + 1)]


class DocxMatrixTests(unittest.TestCase):
    def test_merged_header_and_numeric_code_row(self):
        (matrix,) = docx_matrices(docx_matrix())
        self.assertEqual(matrix.source_kind, "docx_table")
        self.assertEqual([c.label for c in matrix.columns], list(FREQUENCY_LABELS))
        self.assertEqual(matrix.codes, ("0", "1", "2", "3", "4"))
        self.assertTrue(all(c.group == "How often during the past week?" for c in matrix.columns))
        self.assertEqual([r.number for r in matrix.rows], [1, 2, 3, 4])
        self.assertEqual(matrix.blocking_problems(), ())
        self.assertIn("DOCX table 1", matrix.rows[0].provenance)
        # The original detected grid is preserved separately from edits.
        self.assertEqual(matrix.source_grid[0][2], "How often during the past week? / Never [0]")

    def test_missing_cells_multiline_prompt_and_no_codes(self):
        (matrix,) = docx_matrices(docx_matrix(
            merged_header=False, numeric_row=False, missing_cell=True, multiline=True,
        ))
        self.assertEqual(matrix.codes, (None,) * 5)
        self.assertTrue(matrix.rows[1].multiline)
        self.assertEqual(matrix.rows[1].prompt, "Synthetic tasks felt manageable for me.")
        self.assertEqual(matrix.unresolved_cells, ((2, 2),))
        self.assertTrue(any("No numeric codes" in i for i in matrix.issues))
        with self.assertRaisesRegex(ValueError, "missing/ambiguous"):
            verify_matrix(matrix)
        reviewed = accept_cell(matrix, 2, 2)
        self.assertEqual(reviewed.rows[2].cells[2].provenance, "reviewed")
        verified = verify_matrix(reviewed)
        questions = matrix_to_questions(verified)
        self.assertEqual(questions[0]["kind"], "single_choice")
        self.assertEqual(questions[0]["options"], list(FREQUENCY_LABELS))
        with self.assertRaisesRegex(ValueError, "numeric code"):
            matrix_to_questions(verified, accept_codes=True)

    def test_non_matrix_tables_are_ignored(self):
        from io import BytesIO
        from docx import Document
        document = Document()
        table = document.add_table(rows=3, cols=2)
        table.cell(0, 0).text = "Name"
        table.cell(1, 0).text = "Department"
        stream = BytesIO()
        document.save(stream)
        self.assertEqual(docx_matrices(stream.getvalue()), ())


class GeometryMatrixTests(unittest.TestCase):
    def test_text_layer_matrix_spanning_a_page_break(self):
        (matrix,) = geometric_matrices(text_pages(matrix_text_pdf(split_after=2)))
        self.assertEqual(matrix.pages, (1, 2))
        self.assertEqual([c.label for c in matrix.columns], list(FREQUENCY_LABELS))
        self.assertEqual(matrix.codes, ("0", "1", "2", "3", "4"))
        self.assertEqual([r.number for r in matrix.rows], [1, 2, 3, 4])
        self.assertEqual([r.page for r in matrix.rows], [1, 1, 2, 2])
        self.assertTrue(any("page break" in i for i in matrix.issues))
        self.assertEqual(matrix.rows[3].prompt, "My invented schedule felt predictable.")
        self.assertIsNotNone(matrix.rows[0].cells[0].box)

    def test_pss_like_and_ucla_like_layouts(self):
        pss = matrix_text_pdf(PSS_LIKE_ITEMS, PSS_LIKE_LABELS, ("0", "1", "2", "3", "4"))
        (matrix,) = geometric_matrices(text_pages(pss))
        self.assertEqual(matrix.codes, ("0", "1", "2", "3", "4"))
        self.assertEqual(len(matrix.rows), 3)
        ucla = matrix_text_pdf(UCLA_LIKE_ITEMS, UCLA_LIKE_LABELS, ("1", "2", "3", "4"))
        (matrix,) = geometric_matrices(text_pages(ucla))
        self.assertEqual([c.label for c in matrix.columns], list(UCLA_LIKE_LABELS))
        self.assertEqual(matrix.codes, ("1", "2", "3", "4"))

    def test_descending_codes_are_flagged_not_reordered(self):
        pdf = matrix_text_pdf(codes=("4", "3", "2", "1", "0"))
        (matrix,) = geometric_matrices(text_pages(pdf))
        self.assertEqual(matrix.codes, ("4", "3", "2", "1", "0"))
        self.assertTrue(any("DEScend" in i for i in matrix.issues))

    def test_touching_header_labels_are_flagged(self):
        pdf = matrix_text_pdf(spacing=0.075, label_size=12, start=0.5)
        (matrix,) = geometric_matrices(text_pages(pdf))
        self.assertTrue(any("spans columns" in i for i in matrix.issues))
        self.assertTrue(any("overlaps another column" in p for p in matrix.blocking_problems()))
        fixed = matrix
        for k, label in enumerate(FREQUENCY_LABELS):
            if matrix.columns[k].ambiguous:
                fixed = set_column(fixed, k, label=label)
        self.assertEqual(verify_matrix(fixed).blocking_problems(), ())

    def test_multilingual_latvian_and_russian_layouts(self):
        lv = matrix_text_pdf(
            ("Sintētiskā nedēļa bija mierīga.", "Izdomātie uzdevumi šķita viegli."),
            ("Nekad", "Reti", "Dažreiz", "Bieži"), ("1", "2", "3", "4"),
        )
        (matrix,) = geometric_matrices(text_pages(lv))
        self.assertEqual([c.label for c in matrix.columns], ["Nekad", "Reti", "Dažreiz", "Bieži"])
        self.assertEqual(matrix.rows[0].prompt, "Sintētiskā nedēļa bija mierīga.")
        ru = matrix_text_pdf(
            ("Вымышленная неделя была спокойной.", "Синтетические задачи были простыми."),
            ("Никогда", "Редко", "Иногда", "Часто"), ("1", "2", "3", "4"),
        )
        (matrix,) = geometric_matrices(text_pages(ru))
        self.assertEqual(matrix.columns[0].label, "Никогда")
        self.assertEqual(matrix.rows[1].prompt, "Синтетические задачи были простыми.")

    def test_plain_lists_and_text_without_geometry_are_not_matrices(self):
        pdf = text_pdf([[(0.1, 0.9, "1. A synthetic open question?"),
                         (0.1, 0.85, "2. Another synthetic open question?")]])
        self.assertEqual(geometric_matrices(text_pages(pdf)), ())
        self.assertEqual(geometric_matrices([page_from_plain_text(1, "1. A\n2. B")]), ())


class MatrixEditingTests(unittest.TestCase):
    def setUp(self):
        (self.matrix,) = docx_matrices(docx_matrix())

    def test_edits_reset_verification_and_keep_source_grid(self):
        verified = verify_matrix(self.matrix)
        self.assertTrue(verified.verified)
        edited = set_cell(verified, 0, 0, "")
        self.assertFalse(edited.verified)
        self.assertTrue(edited.edited)
        self.assertEqual(edited.source_grid, self.matrix.source_grid)
        self.assertEqual(edited.rows[0].cells[0].state, "empty")
        for operation in (
            lambda m: set_row(m, 0, prompt="Edited synthetic statement"),
            lambda m: add_row(m, 1, "Inserted synthetic statement"),
            lambda m: delete_row(m, 0), lambda m: move_row(m, 0, 2),
            lambda m: set_column(m, 0, label="Not at all"),
            lambda m: move_column(m, 0, 1), lambda m: delete_column(m, 4),
            lambda m: add_column(m, None, "Extra", "5"),
        ):
            self.assertFalse(operation(verified).verified)

    def test_row_and_column_operations(self):
        m = move_row(self.matrix, 0, 1)
        self.assertEqual(m.rows[1].prompt, self.matrix.rows[0].prompt)
        m = add_row(self.matrix, None, "A synthetic extra statement.")
        self.assertEqual(len(m.rows), 5)
        self.assertEqual(len(m.rows[-1].cells), 5)
        m = add_column(self.matrix, 0, "Not applicable", "9")
        self.assertEqual(len(m.columns), 6)
        self.assertTrue(all(len(r.cells) == 6 for r in m.rows))
        m = move_column(m, 0, 10)
        self.assertEqual(m.columns[-1].label, "Not applicable")
        m = delete_column(m, 5)
        self.assertEqual([c.label for c in m.columns], list(FREQUENCY_LABELS))
        with self.assertRaisesRegex(ValueError, "integer"):
            set_column(self.matrix, 0, code="one")
        with self.assertRaises(IndexError):
            set_cell(self.matrix, 99, 0, "x")

    def test_scoring_and_reverse_keys_require_explicit_confirmation(self):
        marked = set_row(self.matrix, 1, reverse_proposed=True)
        with self.assertRaisesRegex(ValueError, "Verify"):
            matrix_to_questions(marked, accept_codes=True)
        verified = verify_matrix(marked)
        plain = matrix_to_questions(verified)
        self.assertTrue(all(q["kind"] == "single_choice" for q in plain))
        self.assertFalse(any(q.get("reverse_scored") for q in plain))
        with self.assertRaisesRegex(ValueError, "before applying reverse"):
            matrix_to_questions(verified, accept_reverse=True)
        coded = matrix_to_questions(verified, accept_codes=True)
        self.assertEqual(coded[0]["kind"], "rating_scale")
        self.assertEqual(coded[0]["value_labels"]["0"], "Never")
        self.assertFalse(any(q["reverse_scored"] for q in coded))
        both = matrix_to_questions(verified, accept_codes=True, accept_reverse=True)
        self.assertEqual([q["reverse_scored"] for q in both], [False, True, False, False])
        self.assertTrue(all(q["scale_id"] == "matrix_scale" for q in both))

    def test_duplicate_codes_and_labels_block_verification(self):
        bad = set_column(self.matrix, 1, code="0")
        with self.assertRaisesRegex(ValueError, "unique integers"):
            verify_matrix(bad)
        bad = set_column(self.matrix, 1, label="Never")
        with self.assertRaisesRegex(ValueError, "distinct"):
            verify_matrix(bad)


if __name__ == "__main__":
    unittest.main()
