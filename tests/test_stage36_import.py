"""Stage 36.5: structure-first Word forms, OCR table rows and honest counts.

Synthetic fixtures only (tests/fixtures/stage36/generate_fixtures.py and
small documents built here). D6/D7/D8 themselves are reproduced in
tests/test_stage36_regressions.py; these tests pin down the evidence the
fixes produce: per-form counts and labels, scheme evidence, scoring keys
as metadata, flagged numbers, joined continuation lines, legends, regions.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import stage36_fixtures as fx  # noqa: E402
from ocr_layout import OCRBlock, OCRLine, OCRPage, OCRWord, question_ref, union_box  # noqa: E402
from ocr_table_rows import page_geometry, read_number, reconstruct_tables  # noqa: E402
from response_scales import code_label_pairs, line_code_label  # noqa: E402
from scientific_survey_import import (  # noqa: E402
    expected_item_count, read_scientific_document, reviewed_draft,
)
from table_forms import find_forms, read_docx_blocks  # noqa: E402

GENERAL = ("Hardly ever", "Now and then", "Fairly often", "Very often")
SITUATIONAL = ("Not at all", "Slightly", "Moderately", "Strongly")
NUMBERED = ("Never", "Rarely", "Sometimes", "Often")
LV_LABELS = ("gandrīz nekad", "reti", "dažkārt", "bieži", "gandrīz vienmēr")
ARTIFACT_ROWS = {17, 18, 19, 20, 21, 24}     # tick marks drawn before these numbers


def docx_bytes(build) -> bytes:
    from docx import Document

    document = Document()
    build(document)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def table(document, rows):
    grid = document.add_table(rows=len(rows), cols=len(rows[0]))
    for r, values in enumerate(rows):
        for c, value in enumerate(values):
            grid.cell(r, c).text = value


def read_docx(data: bytes, name: str = "form.docx"):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / name
        path.write_bytes(data)
        return read_scientific_document(path)


class UnnumberedWordFormsTests(unittest.TestCase):
    """Spec §10 COPE-LV shape: two 60-row table forms without item numbers."""

    @classmethod
    def setUpClass(cls):
        cls.path = fx.fixture(fx.DOCX_UNNUMBERED)
        cls.review = read_scientific_document(cls.path)
        from docx import Document

        cls.cells = [[row.cells[0].text for row in grid.rows] for grid in Document(cls.path).tables]

    def test_each_form_is_one_instrument_titled_by_its_heading(self):
        review = self.review
        self.assertEqual([x.title for x in review.instruments],
                         ["INVENTORY FORM: GENERAL", "INVENTORY FORM: SITUATIONAL"])
        self.assertEqual([len(x.questions) for x in review.instruments], [60, 60])
        for instrument in review.instruments:
            self.assertEqual([q.number for q in instrument.questions], list(range(1, 61)))
            self.assertTrue(any("numbered 1–60 in table order" in w for w in instrument.warnings))
        self.assertTrue(any("never merge" in w for w in review.warnings))

    def test_items_keep_the_cell_wording_and_skip_the_header_row(self):
        general, situational = self.review.instruments
        self.assertEqual([q.question["prompt"] for q in general.questions], self.cells[0][1:])
        self.assertEqual([q.question["prompt"] for q in situational.questions], self.cells[1])
        self.assertNotIn("Invented statement", [q.question["prompt"] for q in general.questions])

    def test_each_form_documents_its_own_unconfirmed_scale(self):
        expected = ((GENERAL, "header"), (SITUATIONAL, "instruction"))
        for instrument, (labels, evidence) in zip(self.review.instruments, expected):
            (scheme,) = instrument.schemes
            self.assertEqual(scheme.labels, labels)
            self.assertEqual(scheme.codes, ("1", "2", "3", "4"))
            self.assertEqual(scheme.evidence, evidence)
            self.assertEqual(scheme.items, tuple(range(1, 61)))
            self.assertEqual(scheme.issues, ())
            self.assertFalse(scheme.structure_confirmed or scheme.codes_confirmed
                             or scheme.reverse_confirmed)
            self.assertEqual({q.scheme_id for q in instrument.questions}, {scheme.id})
            self.assertEqual(instrument.questions[0].question["options"], list(labels))
            with self.assertRaisesRegex(ValueError, "unverified 4-choice scale"):
                reviewed_draft(instrument)   # confirmation stays with the researcher

    def test_scoring_key_paragraphs_are_metadata_not_questions(self):
        prompts = [q.question["prompt"] for x in self.review.instruments for q in x.questions]
        self.assertFalse([p for p in prompts if p.startswith(("Dimension", "Fifteen"))])
        groups = self.review.instruments[1].evidence.scoring_groups
        self.assertEqual(len(groups), 15)
        self.assertEqual(groups[0].name, "Dimension 1 (invented)")
        self.assertEqual([g.items for g in groups],
                         [tuple(k + 1 + 15 * n for n in range(4)) for k in range(15)])
        self.assertFalse(any(g.approved for g in groups))

    def test_references_stay_out_and_the_count_is_stated_honestly(self):
        self.assertEqual(len(self.review.non_items), 2)
        self.assertIsNone(self.review.expected_count)
        self.assertTrue(any("Found 120 candidate items in 2 instruments (60, 60)" in w
                            and "states no item count" in w for w in self.review.warnings))

    def test_document_order_and_headings_are_read_from_the_structure(self):
        blocks = read_docx_blocks(self.path)
        kinds = [b.kind for b in blocks]
        self.assertEqual(kinds.count("table"), 2)
        headings = [b.text for b in blocks if b.heading_level == 1]
        self.assertEqual(headings[:2], ["INVENTORY FORM: GENERAL", "INVENTORY FORM: SITUATIONAL"])
        forms = find_forms(blocks)
        self.assertEqual([(f.title, len(f.rows), f.numbered) for f in forms],
                         [("INVENTORY FORM: GENERAL", 60, False),
                          ("INVENTORY FORM: SITUATIONAL", 60, False)])
        self.assertEqual(forms[0].rows[0].table_row, 2, "the header row is not an item")


class NumberedWordFormsTests(unittest.TestCase):
    def test_numbered_cells_keep_their_items_and_get_the_instruction_scale(self):
        review = read_scientific_document(fx.fixture(fx.DOCX_NUMBERED))
        self.assertEqual([len(x.questions) for x in review.instruments], [60, 60])
        self.assertEqual([x.title for x in review.instruments],
                         ["SYNTHETIC FORM: GENERAL", "SYNTHETIC FORM: SITUATIONAL"])
        for instrument in review.instruments:
            (scheme,) = instrument.schemes
            self.assertEqual((scheme.labels, scheme.codes, scheme.evidence),
                             (NUMBERED, ("1", "2", "3", "4"), "instruction"))
            self.assertEqual(len(scheme.items), 60)
            self.assertFalse(scheme.structure_confirmed)
        self.assertIsNone(review.expected_count)
        groups = review.instruments[1].evidence.scoring_groups
        self.assertEqual([g.items for g in groups][:2], [(1, 2, 3, 4), (5, 6, 7, 8)])


class WordFormDetectionTests(unittest.TestCase):
    STATEMENTS = ("I plan an invented trip carefully", "I keep a fictional diary daily",
                  "I compare made-up offers calmly", "I discuss an imaginary budget openly")

    def forms(self, build):
        return find_forms(read_docx_blocks(docx_bytes(build)))

    def test_header_labels_that_disagree_with_the_instruction_are_reported(self):
        def build(document):
            document.add_heading("FICTIONAL CHECK FORM", 1)
            document.add_paragraph("Use one of: 1 = Never; 2 = Sometimes; 3 = Always.")
            table(document, [("Statement", "Rarely", "Often", "Always"),
                             *[(s, "1", "2", "3") for s in self.STATEMENTS]])
        (form,) = self.forms(build)
        self.assertEqual(form.scale.labels, ("Rarely", "Often", "Always"))
        self.assertEqual(form.scale.evidence, "header")
        self.assertTrue(any("names other answer options" in i for i in form.scale.issues))

    def test_a_numeric_header_row_is_not_an_item_and_codes_come_from_the_cells(self):
        def build(document):
            document.add_paragraph("Answer with 1 Never / 2 Sometimes / 3 Often.")
            table(document, [("Statement", "1", "2", "3"),
                             *[(s, "1", "2", "3") for s in self.STATEMENTS]])
        (form,) = self.forms(build)
        self.assertEqual([row.statement for row in form.rows], list(self.STATEMENTS))
        self.assertEqual([row.number for row in form.rows], [1, 2, 3, 4])
        self.assertEqual((form.scale.labels, form.scale.evidence),
                         (("Never", "Sometimes", "Often"), "instruction"))

    def test_labels_printed_in_every_row_are_row_evidence(self):
        def build(document):
            table(document, [(s, "Never", "Sometimes", "Often") for s in self.STATEMENTS])
        (form,) = self.forms(build)
        self.assertEqual((form.scale.labels, form.scale.codes, form.scale.evidence),
                         (("Never", "Sometimes", "Often"), (None, None, None), "row"))

    def test_binary_marker_and_code_label_cells_keep_their_own_readers(self):
        layouts = {
            "true/false": [(s, "True", "False") for s in self.STATEMENTS],
            "markers": [(s, "○", "○", "○") for s in self.STATEMENTS],
            "code + label": [(s, "1\nNEVER", "2\nOFTEN") for s in self.STATEMENTS],
            "blank boxes": [(s, "", "", "") for s in self.STATEMENTS],
        }
        for name, rows in layouts.items():
            with self.subTest(name):
                self.assertEqual(self.forms(lambda d, rows=rows: table(d, rows)), ())

    def test_an_unnumbered_form_without_documented_options_says_so(self):
        def build(document):
            document.add_heading("FICTIONAL FORM WITHOUT A KEY", 1)
            table(document, [(s, "1", "2", "3", "4") for s in self.STATEMENTS])
        review = read_docx(docx_bytes(build))
        (instrument,) = review.instruments
        self.assertEqual(instrument.title, "FICTIONAL FORM WITHOUT A KEY")
        self.assertEqual(len(instrument.questions), 4)
        (scheme,) = instrument.schemes        # codes printed in every row, no labels
        self.assertEqual(scheme.codes, ("1", "2", "3", "4"))
        self.assertTrue(scheme.label_problems())


class StatedItemCountTests(unittest.TestCase):
    """D7: a count only counts when it describes the questionnaire length."""

    def test_scoring_notes_and_part_sizes_are_not_the_form_length(self):
        for text in ("Fifteen fictional subscales, each with four invented items:",
                     "Fifteen invented dimensions; each dimension sums four statements.",
                     "Each subscale consists of 4 items.",
                     "The inventory has 15 subscales of 4 items.",
                     "Katrā apakšskalā ir 4 apgalvojumi.",
                     "Каждая подшкала включает 4 вопроса."):
            with self.subTest(text=text):
                self.assertIsNone(expected_item_count([text]))

    def test_statements_about_the_whole_form_still_count(self):
        cases = {
            "The questionnaire consists of 60 items.": 60,
            "Each of the 20 items is rated on a 4-point scale.": 20,
            "A 52-item synthetic form.": 52,
            "The form, which measures 15 dimensions, consists of 60 items.": 60,
            "Fifteen subscales, each with four items. The form consists of 60 items.": 60,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(expected_item_count([text]), expected)


class AnswerOptionTextTests(unittest.TestCase):
    def test_instruction_and_legend_formats(self):
        self.assertEqual(code_label_pairs("Answer with one of: 1 = Hardly ever; 2 = Now and then."),
                         (("1", "Hardly ever"), ("2", "Now and then")))
        self.assertEqual(code_label_pairs("Select one: 1 Never / 2 Rarely / 3 Often. Thank you."),
                         (("1", "Never"), ("2", "Rarely"), ("3", "Often")))
        self.assertEqual(code_label_pairs("(0) not at all (1) a little (2) a lot"),
                         (("0", "not at all"), ("1", "a little"), ("2", "a lot")))
        self.assertEqual(line_code_label("5- gandrīz vienmēr"), ("5", "gandrīz vienmēr"))

    def test_ranges_lists_and_numbered_text_are_not_options(self):
        for text in ("Scores range from 0 = never to 4 = always.", "Rate from 1 to 5.",
                     "Dimension 1 (invented): statements 1, 16, 31, 46.",
                     "1. In an invented scenario 1, I chose an option.",
                     "Choose one of the 5 answer options below:"):
            with self.subTest(text=text):
                self.assertEqual(code_label_pairs(text), ())


# ------------------------------------------------- OCR geometry (synthetic boxes)

def _words(line_id, parts):
    return tuple(OCRWord(f"{line_id}-w{k}", text, (x0, top, x1, bottom), conf, line_id)
                 for k, (text, x0, x1, top, bottom, conf) in enumerate(parts, 1))


def _line(page, n, parts):
    line_id = f"p{page}-b1-r1-l{n}"
    words = _words(line_id, parts)
    return OCRLine(line_id, f"p{page}-b1", words, union_box(w.box for w in words))


def _text(text, x, top, *, conf=95.0, height=0.013):
    parts = []
    for token in text.split():
        width = 0.0075 * len(token)
        parts.append((token, x, x + width, top, top + height, conf))
        x += width + 0.006
    return parts


class SyntheticTable:
    """Positioned words of a scanned table: number | statement | answer digits."""

    def __init__(self, page=1):
        self.page, self.lines, self.top = page, [], 0.08

    def add(self, parts, step=0.022):
        self.lines.append(_line(self.page, len(self.lines) + 1, parts))
        self.top += step

    def text(self, text, x=0.10):
        self.add(_text(text, x, self.top))

    def row(self, number_text, statement, more=(), answers="1 2 3 4 5", number_x=0.10):
        parts = []
        if number_text:
            parts.append((number_text, number_x, 0.10 + 0.0075 * len(number_text.lstrip('"')),
                          self.top, self.top + 0.013, 93.0))
        parts += _text(statement, 0.14, self.top)
        x = 0.78
        for token in answers.split():
            parts.append((token, x, x + 0.008 * len(token), self.top, self.top + 0.013, 90.0))
            x += 0.008 * len(token) + 0.022
        self.add(parts)
        for line in more:
            self.add(_text(line, 0.14, self.top))
        self.noise()

    def noise(self):
        self.add([("ii", 0.08, 0.93, self.top, self.top + 0.018, 11.0),
                  ("m", 0.40, 0.45, self.top, self.top + 0.018, 20.0)], step=0.012)

    def ocr_page(self):
        block = OCRBlock(f"p{self.page}-b1", tuple(self.lines), union_box(l.box for l in self.lines))
        return OCRPage(self.page, 1200, 1700, (block,), "tesseract_tsv", "lav")


def legend(sheet):
    for code, label in zip("12345", LV_LABELS):
        sheet.add(_text(f"{code}- {label}", 0.35, sheet.top))


def statement(n):
    return f"Izdomātā situācijā Nr. {n} es pārrunāju izdomāto uzdevumu."


def two_pages():
    first = SyntheticTable(1)
    first.text("IZDOMĀTA APTAUJA")
    legend(first)
    for n in range(1, 8):
        number = f'"{n}.' if n == 4 else ("l7." if n == 7 else f"{n}.")   # l7. reads as 17
        more = ("kamēr pārējie vēl gaida.",) if n == 2 else ()
        first.row(number, statement(n), more)
    second = SyntheticTable(2)
    legend(second)
    for n in range(8, 13):
        second.row({10: "", 11: "Il."}.get(n, f"{n}."), statement(n))
    second.text("Atsauces:")
    second.text("1. Izdomāts Autors (2099). Testa piezīme.")
    return [first.ocr_page(), second.ocr_page()]


class OCRTableRowTests(unittest.TestCase):
    def test_numbers_are_read_strictly_then_normalised_only_towards_the_sequence(self):
        self.assertEqual(read_number("12.", None), (12, "printed"))
        self.assertEqual(read_number('"17.', 17), (17, "normalised"))
        self.assertEqual(read_number("„17.", 17), (17, "normalised"))
        self.assertEqual(read_number("I7.", 17), (17, "normalised"))
        self.assertEqual(read_number("2O.", 20), (20, "normalised"))
        self.assertIsNone(read_number("I7.", 30), "look-alikes only reach the expected number")
        self.assertIsNone(read_number('"7.', 17))
        self.assertIsNone(read_number("W", 17))

    def test_rows_flags_continuations_legend_and_references(self):
        tables = reconstruct_tables(two_pages())
        rows = {row.number: row for row in tables.rows}
        self.assertEqual(sorted(rows), list(range(1, 13)))
        self.assertEqual(rows[4].number_source, "normalised")      # "4. → 4
        self.assertEqual(rows[11].number_source, "normalised")     # Il. → 11 (expected)
        self.assertEqual(rows[7].number_source, "inferred")        # l7. is no 7
        self.assertEqual(rows[7].number_text, "l7.")
        self.assertEqual(rows[10].number_source, "inferred")       # nothing readable
        self.assertEqual({n for n, r in rows.items() if r.number_source != "printed"},
                         {4, 7, 10, 11})
        self.assertEqual(rows[2].prompt, statement(2)[:-1] + ". kamēr pārējie vēl gaida.")
        self.assertEqual(rows[2].prompt_lines, 2)
        for row in rows.values():
            self.assertNotRegex(row.prompt, r"\b1 2 3 4 5\b", "answer digits stay out")
            self.assertTrue(row.prompt.startswith(f"Izdomātā situācijā Nr. {row.number} "))
        self.assertGreaterEqual(tables.dropped_lines, 12, "rule noise between rows is dropped")
        self.assertEqual([legend.pairs for legend in tables.legends],
                         [tuple(zip("12345", LV_LABELS))] * 2)
        text = " ".join(str(line) for page in tables.lines.values() for line in page)
        self.assertIn("1. Izdomāts Autors (2099).", text, "references stay plain text")

    def test_a_number_inline_with_its_text_is_not_a_column(self):
        sheet = SyntheticTable()
        for n in range(1, 6):
            number = f"{n}."
            parts = [(number, 0.10, 0.10 + 0.0075 * len(number), sheet.top, sheet.top + 0.013, 95.0)]
            parts += _text(statement(n), 0.10 + 0.0075 * len(number) + 0.006, sheet.top)
            sheet.add(parts)
        self.assertIsNone(page_geometry(sheet.ocr_page()))
        self.assertIsNone(reconstruct_tables([sheet.ocr_page()]))

    def test_the_importer_flags_numbers_keeps_regions_and_one_legend_scheme(self):
        import visual_survey_review as vsr

        pages = two_pages()
        source = vsr.load_document_bytes(fx.fixture(fx.SCAN_TABLE_LV))
        review = vsr.ocr_scientific_pdf(source, "table.pdf", [1, 2], "lav",
                                        recognizer=lambda png, language: pages.pop(0))
        (instrument,) = review.instruments
        self.assertEqual(instrument.title, "IZDOMĀTA APTAUJA")
        self.assertEqual([q.number for q in instrument.questions], list(range(1, 13)))
        (scheme,) = instrument.schemes
        self.assertEqual((scheme.labels, scheme.codes, scheme.evidence),
                         (LV_LABELS, ("1", "2", "3", "4", "5"), "legend"))
        self.assertFalse(scheme.structure_confirmed)
        self.assertIn("read by OCR", " ".join(scheme.issues))
        flags = dict(instrument.evidence.item_flags)
        self.assertIn('check this number: OCR read “"4.”', flags[4])
        self.assertIn("check this number: OCR read “Il.”", flags[11])
        self.assertIn("check this number: OCR read “l7.”", flags[7])
        self.assertIn("item number inferred from order", flags[7])
        self.assertIn("check this number: no readable number", flags[10])
        self.assertIn("prompt joined from 2 lines", flags[2])
        self.assertFalse([n for n in (1, 2, 3, 5, 6, 8, 9, 12)
                          if any("check this number" in f for f in flags.get(n, ()))])
        for number in (4, 7, 10, 11):
            notes = instrument.questions[number - 1].notes
            self.assertTrue(any("Check this number" in note for note in notes), number)
        self.assertEqual(len(review.non_items), 1)
        for j, question in enumerate(instrument.questions):
            (region,) = review.spatial.regions(question_ref(0, j))
            self.assertEqual(region.page, question.page)
            if question.number != 10:      # row 10 prints no number to cover
                self.assertLess(region.box[0], 0.12, "the region covers the number")
            self.assertLess(region.box[2], 0.78, "the region stops before the answer digits")
        self.assertTrue(any("Found 12 candidate items" in w for w in review.warnings))


@unittest.skipUnless(shutil.which("tesseract"), "local OCR engine")
class RealOCRTableTests(unittest.TestCase):
    """Real local Tesseract on the synthetic scans (D8 and the older inline scan)."""

    @classmethod
    def setUpClass(cls):
        import visual_survey_review as vsr

        source = vsr.load_document_bytes(fx.fixture(fx.SCAN_TABLE_LV))
        cls.review = vsr.ocr_scientific_pdf(source, fx.SCAN_TABLE_LV, [1, 2], "lav")
        inline = vsr.load_document_bytes(fx.fixture(fx.SCAN_INLINE))
        cls.inline = vsr.ocr_scientific_pdf(inline, fx.SCAN_INLINE, [1, 2], "eng")

    def test_all_52_statements_with_latvian_letters_and_no_answer_digits(self):
        (instrument,) = self.review.instruments
        self.assertEqual([q.number for q in instrument.questions], list(range(1, 53)))
        for q in instrument.questions:
            prompt = q.question["prompt"]
            self.assertTrue(prompt.startswith(f"Izdomātā situācijā Nr. {q.number} "), prompt)
            self.assertNotRegex(prompt, r"\d{3,}", "answer digits are not statement text")
        long_rows = [q for q in instrument.questions if q.number % 4 == 1]
        self.assertEqual(len(long_rows), 13)
        for q in long_rows:
            self.assertTrue(q.question["prompt"].endswith("nemaina savas domas."), q.number)
            self.assertTrue(any(f.startswith("prompt joined from") for f in
                                instrument.evidence.flags_for(q.number)), q.number)

    def test_the_legend_is_one_unconfirmed_scheme_and_never_an_item(self):
        (instrument,) = self.review.instruments
        (scheme,) = instrument.schemes
        self.assertEqual(scheme.labels, LV_LABELS)
        self.assertEqual(scheme.evidence, "legend")
        self.assertEqual(len(scheme.items), 52)
        self.assertFalse(scheme.structure_confirmed or scheme.codes_confirmed)
        prompts = " ".join(q.question["prompt"] for q in instrument.questions)
        self.assertNotIn("gandrīz nekad", prompts)
        self.assertNotIn("Izdomāts Autors", prompts)
        self.assertEqual(len(self.review.non_items), 2)

    def test_only_artifact_rows_are_flagged_and_every_row_has_a_region(self):
        (instrument,) = self.review.instruments
        flagged = {n for n, flags in instrument.evidence.item_flags
                   if any("check this number" in f for f in flags)}
        self.assertTrue(flagged)
        self.assertLessEqual(flagged, ARTIFACT_ROWS)
        for j, question in enumerate(instrument.questions):
            (region,) = self.review.spatial.regions(question_ref(0, j))
            self.assertEqual(region.page, question.page)
            self.assertTrue(region.line_ids)

    def test_confidence_stays_character_confidence_and_the_count_is_stated(self):
        warnings = " ".join(self.review.warnings)
        self.assertIn("OCR confidence measures character recognition only", warnings)
        self.assertIn("Found 52 candidate items", warnings)

    def test_the_inline_number_scan_still_gives_52(self):
        numbers = [q.number for x in self.inline.instruments for q in x.questions]
        self.assertEqual(numbers, list(range(1, 53)))
        self.assertTrue(all(re.match(r"Invented coping action \d+ ", q.question["prompt"])
                            for x in self.inline.instruments for q in x.questions))


if __name__ == "__main__":
    unittest.main()
