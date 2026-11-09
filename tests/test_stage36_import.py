"""Stage 36.5: structure-first Word forms, OCR table rows and honest counts.

Synthetic fixtures only (tests/fixtures/stage36/generate_fixtures.py and
small documents built here). D6/D7/D8 themselves are reproduced in
tests/test_stage36_regressions.py; these tests pin down the evidence the
fixes produce: per-form counts and labels, scheme evidence, scoring keys
as metadata, flagged numbers, joined continuation lines, legends, regions.
"""

from __future__ import annotations

from dataclasses import replace
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


# ------------- structural patterns reported from a real scan (invented words)
#
# Positions (page fractions) and word confidences follow the structural
# evidence of an authorized private check; every word here is invented.

FILLER = ("aaaa", "bbbbbb", "cccc", "ddddddd", "eeee", "ffffff", "ggg", "hhhhhhh")
LABELS = ("nekad", "reti", "dažreiz", "bieži", "vienmēr")


def invented(n: int) -> str:
    return f"Iedomāta rinda {n} " + " ".join(FILLER[(n + k) % len(FILLER)] for k in range(4)) + "."


def tokens_at(tokens, x=0.76, step=0.042, conf=80.0):
    """Answer-area tokens: plain strings, or (text, x, confidence)."""
    parts = []
    for token in tokens:
        text, at, score = token if isinstance(token, tuple) else (token, x, conf)
        parts.append((text, at, at + 0.009 * len(text), score))
        x = at + step
    return parts


class RealLayout:
    """Synthetic OCR lines: number column 0.13-0.16, statement column 0.21,
    answers 0.72-0.97, ruled-line noise between rows."""

    def __init__(self, page=1):
        self.page, self.lines, self.y = page, [], 0.05

    def add(self, parts, step=0.02, height=0.013):
        line_id = f"p{self.page}-b1-r1-l{len(self.lines) + 1}"
        words = tuple(OCRWord(f"{line_id}-w{k}", text, (x0, self.y, x1, self.y + height), conf,
                              line_id) for k, (text, x0, x1, conf) in enumerate(parts, 1))
        self.lines.append(OCRLine(line_id, f"p{self.page}-b1", words,
                                  union_box(w.box for w in words)))
        self.y += step

    @staticmethod
    def words(text, x, conf=95.0):
        parts = []
        for token in text.split():
            parts.append((token, x, x + 0.0075 * len(token), conf))
            x += 0.0075 * len(token) + 0.006
        return parts

    def row(self, number, text, answers, *, number_x=0.15, number_conf=92.0, more=(),
            noise=True):
        parts = [(number, number_x, number_x + 0.0075 * len(number), number_conf)] if number else []
        self.add(parts + self.words(text, 0.21) + answers)
        for extra in more:
            self.add(self.words(extra, 0.21))
        if noise:  # a ruled line read as text
            self.add([("ii", 0.08, 0.93, 11.0), ("m", 0.40, 0.45, 20.0)], step=0.008,
                     height=0.018)

    def legend(self, x=0.355, step=0.017):
        for code, label in zip("12345", LABELS):
            self.add([(f"{code}-", x, x + 0.015, 93.0)] + self.words(label, x + 0.022), step=step)

    def ocr_page(self):
        block = OCRBlock(f"p{self.page}-b1", tuple(self.lines), union_box(l.box for l in self.lines))
        return OCRPage(self.page, 1200, 1700, (block,), "tesseract_tsv", "lav")


def first_page(rows=range(1, 9), *, instruction=True, legend=True, special=None):
    """Title, an instruction line opening with a bare "5", the legend, rows."""
    sheet = RealLayout(1)
    sheet.add(sheet.words("IEDOMĀTA APTAUJA", 0.30))
    if instruction:
        sheet.add(sheet.words("Lūdzu, izvēlieties katrai rindai vienu no", 0.10))
        sheet.add([("5", 0.18, 0.188, 90.0)] + sheet.words("atbilžu variantiem zemāk:", 0.205))
    if legend:
        sheet.legend()
    confidences = {1: 57.0, 2: 74.0, 3: 91.0, 4: 95.0}
    for n in rows:
        if special and n in special:
            special[n](sheet, n)
            continue
        sheet.row(f"{n}.", invented(n), tokens_at("1 2 3 4 5".split()),
                  number_x=0.16 if n <= 4 else 0.15, number_conf=confidences.get(n, 92.0),
                  more=("turpinājums ar dažiem vārdiem",) if n in (1, 4) else ())
    return sheet.ocr_page()


def rows_of(pages):
    tables = reconstruct_tables(pages)
    numbers = [row.number for row in tables.rows]
    if len(numbers) != len(set(numbers)):
        raise AssertionError(f"an item number was used twice: {numbers}")
    return {row.number: row for row in tables.rows}, tables


class RealScanPatternTests(unittest.TestCase):
    def test_1_a_bare_digit_and_the_legend_never_start_or_advance_the_sequence(self):
        rows, tables = rows_of([first_page()])
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertEqual(rows[1].prompt, invented(1) + " turpinājums ar dažiem vārdiem")
        self.assertEqual(rows[4].prompt, invented(4) + " turpinājums ar dažiem vārdiem")
        self.assertEqual(rows[5].prompt, invented(5), "the instruction line is not item 5")
        self.assertTrue(all(r.number_source == "printed" for r in rows.values()))
        self.assertEqual([legend.pairs for legend in tables.legends], [tuple(zip("12345", LABELS))])
        text = [str(line) for line in tables.lines[1]]
        self.assertIn("5 atbilžu variantiem zemāk:", text, "the instruction stays plain text")

    def test_1_the_bare_digit_is_refused_even_where_its_text_meets_the_statement_column(self):
        def instruction_row(sheet, n):
            sheet.row(f"{n}.", invented(n), tokens_at("1 2 3 4 5".split()), number_x=0.16)
        page = RealLayout(1)
        page.add([("5", 0.17, 0.178, 90.0)] + page.words("atbilžu variantiem zemāk:", 0.21))
        page.legend()
        for n in range(1, 6):
            instruction_row(page, n)
        rows, _ = rows_of([page.ocr_page()])
        self.assertEqual(sorted(rows), [1, 2, 3, 4, 5])
        self.assertEqual(rows[5].prompt, invented(5))

    def test_2_a_quoted_number_with_a_lost_first_answer_digit(self):
        def quoted(sheet, n):
            sheet.row(f'"{n}.', invented(n), tokens_at("2 3 4 5".split(), x=0.80),
                      number_conf=52.0, more=("turpinājums ar dažiem vārdiem",))
        rows, _ = rows_of([first_page(range(1, 9), special={6: quoted})])
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertEqual((rows[6].number_source, rows[6].number_text), ("normalised", '"6.'))
        self.assertEqual(rows[6].prompt, invented(6) + " turpinājums ar dažiem vārdiem")

    def test_2_a_number_split_onto_its_own_line_or_behind_a_speck_is_still_read(self):
        def split(sheet, n):    # OCR puts '"6.' on a line of its own, at the row's height
            top = sheet.y
            sheet.add(sheet.words(invented(n), 0.21) + tokens_at("2 3 4 5".split(), x=0.80),
                      step=0.0)
            sheet.y = top + 0.001
            sheet.add([(f'"{n}.', 0.15, 0.172, 52.0)])
            sheet.add([("ii", 0.08, 0.93, 11.0)], step=0.008, height=0.018)

        def speck(sheet, n):    # a low-scored speck left of the number
            sheet.add([("a", 0.135, 0.14, 20.0), (f'"{n}.', 0.15, 0.172, 52.0)]
                      + sheet.words(invented(n), 0.21) + tokens_at("1 2 3 4 5".split()))
        rows, _ = rows_of([first_page(range(1, 10), special={6: split, 8: speck})])
        self.assertEqual(sorted(rows), list(range(1, 10)))
        self.assertEqual([rows[n].prompt for n in (6, 8)], [invented(6), invented(8)])
        self.assertEqual({rows[n].number_source for n in (6, 8)}, {"normalised"})

    def test_2_specks_and_merged_rule_noise_do_not_hide_a_quoted_row(self):
        def speck_in_text(sheet, n):    # a speck just left of the first statement word
            sheet.add([(f'"{n}.', 0.15, 0.172, 52.0), (",", 0.198, 0.201, 15.0)]
                      + sheet.words(invented(n), 0.21) + tokens_at("2 3 4 5".split(), x=0.80))

        def merged_noise(sheet, n):     # rule noise read into the same line
            sheet.add([(f'"{n}.', 0.15, 0.172, 52.0)] + sheet.words(invented(n), 0.21)
                      + [("ii", 0.56, 0.60, 12.0), ("m", 0.62, 0.64, 18.0)]
                      + tokens_at("1 2 3 4 5".split()))
        rows, _ = rows_of([first_page(range(1, 9), special={5: speck_in_text, 7: merged_noise})])
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertEqual(rows[5].prompt, invented(5), "the speck is not statement text")
        self.assertEqual({rows[n].number_source for n in (5, 7)}, {"normalised"})

    def test_2_low_scored_first_words_still_anchor_the_row(self):
        def low_scored(sheet, n):   # e.g. Latvian words read with English OCR
            words = sheet.words(invented(n), 0.21)
            words[0] = (*words[0][:3], 28.0)
            words[1] = (*words[1][:3], 33.0)
            sheet.add([(f"{n}.", 0.15, 0.165, 92.0)] + words + tokens_at(["123", "45"], x=0.78))
        rows, _ = rows_of([first_page(range(1, 9), special={3: low_scored, 6: low_scored})])
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertEqual([rows[n].prompt for n in (3, 6)], [invented(3), invented(6)])
        self.assertEqual([rows[n].answers for n in (3, 6)], [("123", "45")] * 2)

    def test_3_look_alike_letters_reach_only_the_expected_number(self):
        cases = {"Aī.": 41, "A1.": 41, "4ī.": 41, "Il.": 11, "|7.": 17, "!8.": 18,
                 "S2.": 52, "Z5.": 25, "B4.": 84, "G1.": 61, "T3.": 73, "lO.": 10}
        for token, number in cases.items():
            with self.subTest(token=token):
                self.assertEqual(read_number(token, number), (number, "normalised"))
                self.assertIsNone(read_number(token, number + 1))
        self.assertIsNone(read_number("Aa.", 41))
        self.assertEqual(read_number("41.", 7), (41, "printed"), "clean numbers are kept")

    def test_3_a_look_alike_row_is_flagged_and_its_glued_answers_stripped(self):
        def misread(sheet, n):   # "41." read as "Aī."
            sheet.row("Aī.", invented(n), tokens_at(["a2", "3", "7", "5"], x=0.78, conf=50.0),
                      number_x=0.14, number_conf=16.0)
        page = first_page(range(37, 46), instruction=False, legend=False, special={41: misread})
        rows, tables = rows_of([page])
        self.assertEqual(sorted(rows), list(range(37, 46)))
        self.assertEqual((rows[41].number_source, rows[41].number_text), ("normalised", "Aī."))
        self.assertEqual(rows[41].prompt, invented(41))
        self.assertEqual(rows[41].answers, ("a2", "3", "7", "5"))
        line = next(line for line in tables.lines[1] if getattr(line, "number", None) == 41)
        self.assertIn("check this number: OCR read “Aī.”", line.flags)

    def test_4_a_partial_number_between_its_neighbours_is_inferred_and_flagged(self):
        def partial(sheet, n):
            sheet.row("_4.", invented(n), tokens_at([("a", 0.78, 30.0), ("3", 0.85, 80.0),
                                                     ("45", 0.89, 70.0)]),
                      number_x=0.13, number_conf=55.0)
        rows, tables = rows_of([first_page(range(1, 9), special={6: partial})])
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertEqual((rows[6].number_source, rows[6].number_text), ("inferred", "_4."))
        self.assertEqual(rows[6].prompt, invented(6))
        line = next(line for line in tables.lines[1] if getattr(line, "number", None) == 6)
        self.assertIn("item number inferred from order", line.flags)
        self.assertIn("check this number: OCR read “_4.”", line.flags)

    def test_4_a_partial_number_is_not_inferred_without_the_next_row(self):
        def partial(sheet, n):   # "14." read as "_1.", last row, no answer digits
            sheet.row("_1.", invented(n), [], number_x=0.13, number_conf=55.0)
        rows, tables = rows_of([first_page(range(1, 15), special={14: partial})])
        self.assertEqual(sorted(rows), list(range(1, 14)), "nothing after it confirms 14")
        self.assertIn(f"_1. {invented(14)}", [str(line) for line in tables.lines[1]],
                      "it stays plain text for the researcher, not part of item 13")

    ANSWER_TOKENS = (
        ["12", "345"], ["123", "45"], ["1", "234", "5"], ["12", "3", "45"], ["333", "45"],
        ["737", "5"], ["37", "5"], ["12375"], ["a2345"], ["[1", "2", "3", "4", "5"],
        ["|", "2", "3", "4", "5"], ["1", "2", "3", "4", "5”"], ["1", "23”", "45"],
        ["1—2", "3", "4—5"], ["—", "2", "3", "4", "5"], ["-", "2", "3", "4", "5"],
        ["1", "2", "3", "7", "5"], [("a", 0.73, 40.0), "2", "3", "4", "5"],
        ["1", ("a", 0.80, 30.0), "3", "4", ("a", 0.92, 25.0)],
    )

    def test_5_every_listed_answer_token_form_is_stripped_from_the_row_end(self):
        page = RealLayout(1)
        page.legend()
        for n, tokens in enumerate(self.ANSWER_TOKENS, 1):
            start = 0.72 + 0.10 * ((n * 7) % 11) / 10     # skew and lost digits: 0.72-0.82
            page.row(f"{n}.", invented(n), tokens_at(tokens, x=start))
        rows, _ = rows_of([page.ocr_page()])
        self.assertEqual(sorted(rows), list(range(1, len(self.ANSWER_TOKENS) + 1)))
        for n, row in rows.items():
            self.assertEqual(row.prompt, invented(n), self.ANSWER_TOKENS[n - 1])
            self.assertTrue(row.answers)

    def test_5_statement_words_and_two_letter_tokens_are_never_stripped(self):
        page = RealLayout(1)
        long = "Iedomāta rinda ar ļoti garu tekstu kas beidzas pie labās malas un"
        endings = {
            1: (long, ["1", "2", "3", "4", "5"]),                  # "un" ends at x ≈ 0.70
            2: ("Iedomāta rinda 2 numurs 12 un vēl teksts", ["1", "2", "3", "4", "5"]),
            3: ("Iedomāta rinda 3 aaaa bbbbbb", [("ab", 0.74, 30.0), "3", "4", "5"]),
            4: ("Iedomāta rinda 4 cccc dddd", [("k", 0.73, 90.0), "2", "3", "4", "5"]),
            5: ("Iedomāta rinda 5 eeee ffff", [("L", 0.73, 90.0), "2", "3", "4", "5"]),
            6: ("Iedomāta rinda 6 gggg hhhh", [("LZ", 0.73, 51.0), "3", "4", "5"]),
        }
        for n, (text, tokens) in endings.items():
            page.row(f"{n}.", text, tokens_at(tokens, x=0.76 if n != 1 else 0.74))
        rows, _ = rows_of([page.ocr_page()])
        self.assertEqual(rows[1].prompt, long, "a statement word near the answers stays")
        self.assertEqual(rows[2].prompt, endings[2][0], "digits inside the statement stay")
        self.assertTrue(rows[3].prompt.endswith(" ab"), "two letters are never stripped")
        self.assertTrue(rows[4].prompt.endswith(" k"), "a confidently read letter stays")
        self.assertEqual(rows[5].prompt, endings[5][0], "a look-alike letter (L for 1) goes")
        self.assertTrue(rows[6].prompt.endswith(" LZ"), "two-letter junk stays, as read")

    def test_6_a_legend_merged_with_rule_noise_never_becomes_an_item(self):
        second = RealLayout(2)
        second.add([("a", 0.15, 0.158, 36.0), ("1-", 0.36, 0.375, 90.0)]
                   + second.words("nekad", 0.382))
        for code, label in zip("234", LABELS[1:4]):
            second.add([(f"{code}-", 0.36, 0.375, 92.0)] + second.words(label, 0.382), step=0.017)
        # Worst case: rule noise reads as "ZT" (2 → Z, 7 → T: the expected 27)
        # in the number column and texts land in the statement column; the
        # next numbered line prints 27 itself, so this line is not item 27.
        second.add([("ZT", 0.15, 0.165, 22.0), ("vārds", 0.21, 0.245, 75.0),
                    ("cits", 0.25, 0.28, 75.0), ("5-", 0.36, 0.375, 90.0)]
                   + second.words("vienmēr", 0.382))
        for n in range(27, 32):
            second.row(f"{n}.", invented(n), tokens_at("1 2 3 4 5".split()))
        first = first_page(range(21, 27), instruction=False)
        rows, tables = rows_of([first, second.ocr_page()])
        self.assertEqual(sorted(rows), list(range(21, 32)))
        self.assertEqual(rows[27].prompt, invented(27))
        self.assertEqual(rows[27].number_source, "printed")
        self.assertIn("ZT vārds cits 5- vienmēr", [str(line) for line in tables.lines[2]])

    def test_7_rows_without_answer_digits_count_when_their_number_fits(self):
        def blank(sheet, n):
            sheet.row(f"{n}.", invented(n), [("aaa", 0.74, 0.765, 20.0), ("a", 0.92, 0.928, 25.0)])
        rows, _ = rows_of([first_page(range(1, 9), special={5: blank, 7: blank})])
        self.assertEqual(sorted(rows), list(range(1, 9)))
        self.assertEqual(rows[5].prompt, invented(5) + " aaa", "three letters are kept as read")
        self.assertEqual(rows[5].number_source, "printed")

    def test_all_patterns_together_give_every_number_once(self):
        def quoted(sheet, n):
            sheet.row(f'"{n}.', invented(n), tokens_at("2 3 4 5".split(), x=0.80), number_conf=52.0)

        def misread(sheet, n):
            sheet.row("Aī.", invented(n), tokens_at(["a2", "3", "7", "5"], x=0.78, conf=50.0),
                      number_x=0.14, number_conf=16.0)

        def partial(sheet, n):
            sheet.row("_4.", invented(n), tokens_at([("a", 0.78, 30.0), "3", "45"]),
                      number_x=0.13, number_conf=55.0)

        def blank(sheet, n):
            sheet.row(f"{n}.", invented(n), [("a", 0.92, 0.928, 25.0)])
        rows, tables = rows_of([first_page(range(1, 14), special={
            5: quoted, 9: misread, 11: partial, 12: blank})])
        self.assertEqual(sorted(rows), list(range(1, 14)))
        self.assertEqual({n for n, r in rows.items() if r.number_source != "printed"}, {5, 9, 11})
        for n, row in rows.items():
            self.assertTrue(row.prompt.startswith(invented(n)), n)
            self.assertNotRegex(row.prompt, r"\s\d+$", "no answer digits at the end")


class LooseFirstWordTests(unittest.TestCase):
    """Round 3: the geometry a private check traced for the lost item 17.

    Line height 0.0225 of a 1200 × 1700 page gives unit_x ≈ 0.0319; the
    statement column runs x = 0.207 − 0.0043·y; numbers stand at x ≈ 0.149
    (quoted) to 0.155; answer digits at 0.713 (scored 0), 0.849, 0.885,
    0.920 and 0.956. Item 17's first word box starts 0.63·unit_x left of the
    column (0.0201 > the strict 0.6·unit_x); item 20's starts 0.018 left
    (inside it), as on the real page. Invented words only.
    """
    HEIGHT, STEP = 0.0225, 0.045
    UNIT = HEIGHT * 1700 / 1200

    def page(self, shifted=17):
        lines, y = [], 0.05

        def add(parts, height=self.HEIGHT):
            line_id = f"p1-b1-r1-l{len(lines) + 1}"
            words = tuple(OCRWord(f"{line_id}-w{k}", text, (x0, y, x1, y + height), conf, line_id)
                          for k, (text, x0, x1, conf) in enumerate(parts, 1))
            lines.append(OCRLine(line_id, "p1-b1", words, union_box(w.box for w in words)))

        for n in range(13, 23):
            column = 0.207 - 0.0043 * (y + self.HEIGHT / 2)
            start = column - {shifted: 0.63 * self.UNIT, 20: 0.018}.get(n, 0.0)
            quoted = n in (17, 18, 19, 20)
            number = f'"{n}.' if quoted else f"{n}."
            x0 = 0.149 if quoted else 0.155
            words = [(number, x0, x0 + 0.009 * len(number), 52.0 if n == 17 else 92.0)]
            first = "abcdefghijk" if n == 17 else ("abc" if n == 20 else "aaaaaaa")
            words.append((first, start, start + 0.0105 * len(first), 32.0 if n == 20 else 90.0))
            x = start + 0.0105 * len(first) + 0.008
            for token in invented(n).split()[1:]:
                words.append((token, x, x + 0.0105 * len(token), 92.0))
                x += 0.0105 * len(token) + 0.008
            words += [("1", 0.713, 0.721, 0.0 if n == 17 else 88.0)] + [
                (code, at, at + 0.008, 88.0) for code, at in zip("2345", (0.849, 0.885, 0.920, 0.956))]
            add(words)
            y += self.STEP * 0.6
            add([("ii", 0.08, 0.93, 11.0), ("m", 0.40, 0.45, 20.0)], height=0.025)
            y += self.STEP * 0.4
        block = OCRBlock("p1-b1", tuple(lines), union_box(l.box for l in lines))
        return OCRPage(1, 1200, 1700, (block,), "tesseract_tsv", "lav")

    def test_the_page_has_the_traced_geometry(self):
        geo = page_geometry(self.page())
        self.assertAlmostEqual(geo.unit_x, 0.0319, places=3)
        self.assertAlmostEqual(geo.statement_a, 0.207, delta=0.002)
        self.assertAlmostEqual(geo.statement_b, -0.0043, delta=0.002)
        self.assertEqual(geo.number_style, "dot")
        self.assertLess(geo.answer_floor, 0.713)

    def test_a_numbered_row_whose_first_word_starts_left_of_the_column_is_kept(self):
        rows, _ = rows_of([self.page()])
        self.assertEqual(sorted(rows), list(range(13, 23)))
        self.assertEqual((rows[17].number_source, rows[17].number_text), ("normalised", '"17.'))
        self.assertTrue(rows[17].prompt.startswith("abcdefghijk "))
        self.assertEqual(rows[17].answers, ("1", "2", "3", "4", "5"))
        self.assertEqual(rows[20].number_source, "normalised")

    def test_lines_without_a_number_keep_the_strict_tolerance(self):
        # The same offset without a number in the column: no row, and no
        # continuation of row 16 either (it is not aligned).
        page = self.page()
        lines = list(page.lines)
        k = next(i for i, line in enumerate(lines) if line.words[0].text == '"17.')
        unnumbered = replace(lines[k], words=lines[k].words[1:])
        block = replace(page.blocks[0], lines=tuple([*lines[:k], unnumbered, *lines[k + 1:]]))
        rows, tables = rows_of([replace(page, blocks=(block,))])
        self.assertNotIn(17, rows)
        self.assertNotIn("abcdefghijk", rows[16].prompt)


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
