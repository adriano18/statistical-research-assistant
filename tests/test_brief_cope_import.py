"""Coping-inventory layouts (#20): answer choices printed after EVERY item.

Fixtures only imitate the LAYOUT of such forms (28 items, standalone or
circled numbering, four wrapped uppercase answer labels repeated under every
item, a letter-spaced text layer, two pages, a Word table, a scan, LV/RU
labels, a missing item and a documented scoring recipe). All wording is
invented; nothing is taken from a published inventory.
"""

from io import BytesIO
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import flet as ft

from letter_spacing import (
    letter_spaced_page, pdf_page_glyph_lines, repair_letter_spaced_line,
    repair_page_lines, repair_pdf_text,
)
from ocr_runtime import tesseract_available
from repeated_choices import code_label_of, code_of, printed_label, segment_repeated_choices
from scientific_survey_import import (
    acknowledge_missing_items, approve_scoring_evidence, linked_questions,
    missing_items_banner, parse_scientific_lines, read_scientific_document,
    review_banner, reviewed_draft, scheme_banner,
)
from shared_scales import review_scheme
from survey_storage import (
    create_survey, responses_dataframe, save_survey_codebook, save_survey_csv,
    submit_response,
)
from synthetic_documents import (
    COPING_LABELS, COPING_LABELS_LV, COPING_LABELS_RU, COPING_STYLES, COPING_TITLE,
    connectedness_text_pdf, coping_docx, coping_scan_pdf, coping_statements,
    coping_text_lines, coping_text_pdf,
)
from visual_survey_review import (
    attach_docx_matrices, attach_text_layer_geometry, ocr_scientific_pdf,
    pdf_text_layer_page,
)


def read(data: bytes, name: str):
    with TemporaryDirectory() as temp:
        path = Path(temp) / name
        path.write_bytes(data)
        review = read_scientific_document(path)
    if name.endswith(".pdf"):
        return attach_text_layer_geometry(review, data)
    return attach_docx_matrices(review, data)


def kinds(instrument):
    found = {}
    for row in instrument.questions:
        found[row.question["kind"]] = found.get(row.question["kind"], 0) + 1
    return found


def confirm(instrument, *, numeric=False):
    (scheme,) = instrument.schemes
    return review_scheme(
        instrument, scheme.id, labels=scheme.labels, codes=scheme.codes,
        reverse_items=(), structure=True, numeric=numeric,
    )


def spacing_diagnostics(data: bytes, page: int = 1, limit: int = 8) -> str:
    """Geometry facts for a failing spacing test (engine versions, gap ratios)."""
    from statistics import median
    import importlib.metadata as metadata
    import pypdfium2 as pdfium
    import letter_spacing as ls

    out = [f"pypdfium2 {metadata.version('pypdfium2')}, pypdf {metadata.version('pypdf')}"]
    pdf = pdfium.PdfDocument(data)
    try:
        lines = ls.pdfium_glyph_lines(pdf[page - 1].get_textpage())
    finally:
        pdf.close()
    for glyphs in lines:
        scale = ls._advance_scale(glyphs)
        if not scale:
            continue
        ratios = [None] + [(g.box[0] - p.box[2]) / scale for p, g in zip(glyphs, glyphs[1:])]
        real = [r for g, r in zip(glyphs, ratios) if g.before == "real" and r is not None]
        gap = median(real) if real else None
        for k in range(1, len(glyphs)):
            g, p = glyphs[k], glyphs[k - 1]
            if g.before == "generated" and p.char.isalpha() and g.char.isalpha():
                word = "".join(x.char for x in glyphs[max(0, k - 5):k + 5])
                out.append(f"{word!r}: ratio {ratios[k]:.3f}, line word gap "
                           f"{gap if gap is None else round(gap, 3)}, scale {scale:.3f}, "
                           f"box {tuple(round(v, 2) for v in g.box)}")
                if len(out) > limit:
                    return "\n".join(out)
    return "\n".join(out)


class SpacingRepairTests(unittest.TestCase):
    def test_text_only_rule_for_letter_spaced_lines(self):
        line = "W e  k e p t  s o r t i n g  1 0  i n v e n t e d  c h o r e s ."
        self.assertEqual(repair_letter_spaced_line(line)[0], "We kept sorting 10 invented chores.")
        # A glued item number keeps its space; quotes and dashes join.
        self.assertEqual(repair_letter_spaced_line("1 8 D u r i n g  “ t h e ”  w e e k ,  1 – 4")[0],
                         "18 During “the” week, 1–4")
        self.assertTrue(letter_spaced_page("\n".join([line] * 6)))
        self.assertFalse(letter_spaced_page("During the invented week I kept sorting chores. " * 8))

    def test_spurious_spaces_inside_words_are_rejoined_from_geometry(self):
        data = coping_text_pdf(letter_spaced=True)
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            raw = pdf[0].get_textpage().get_text_range()
        finally:
            pdf.close()
        # The artifact really exists in the raw PDFium text layer …
        self.assertIn("inve nted", raw)
        self.assertIn("postp oning", raw)
        statements = coping_statements()
        review = read(data, "spaced.pdf")
        (instrument,) = review.instruments
        # … and the imported prompts are exactly the printed statements.
        prompts = [row.question["prompt"] for row in instrument.questions]
        if prompts != statements:
            self.fail("Prompts differ:\n" + "\n".join(
                f"{a!r} != {b!r}" for a, b in zip(prompts, statements) if a != b
            )[:1500] + "\n" + spacing_diagnostics(data))
        words = {word.text for word in pdf_text_layer_page(data, 1).words}
        self.assertIn("postponing", words)
        self.assertNotIn("postp", words)
        self.assertEqual(len(review.spatial.links), 28)
        self.assertGreaterEqual(sum(1 for _, regions in review.spatial.links if regions), 26)

    def test_letter_spaced_fixture_does_not_depend_on_matplotlib_settings(self):
        """Under matplotlib's default hinting the drawn gap once became a full
        word space on CI; the fixture pins its font and metrics instead."""
        import matplotlib
        import pypdfium2 as pdfium

        boxes = []
        for style in ({"text.hinting": "force_autohint"},
                      {"text.hinting": "no_hinting", "font.family": ["DejaVu Serif"]}):
            with matplotlib.rc_context(style):
                data = coping_text_pdf(letter_spaced=True)
            pdf = pdfium.PdfDocument(data)
            try:
                lines = pdf_page_glyph_lines(pdf, 1)
            finally:
                pdf.close()
            boxes.append([glyph.box for line in lines for glyph in line.glyphs])
            # Every split word on the page is a letter gap, not a word space.
            self.assertEqual(sum(kind == "split" for line in lines for kind in line.classes),
                             14, style)
        self.assertEqual(boxes[0], boxes[1])

    def test_letter_spaced_extractor_output_is_repaired_with_geometry_or_text(self):
        data = coping_text_pdf(scoring=False)
        from pypdf import PdfReader
        import pypdfium2 as pdfium

        original = PdfReader(BytesIO(data)).pages[0].extract_text().splitlines()
        spaced = ["  ".join(" ".join(word) for word in line.split()) for line in original]
        pdf = pdfium.PdfDocument(data)
        try:
            geometry = pdf_page_glyph_lines(pdf, 1)
        finally:
            pdf.close()
        # Extractor versions group physical lines differently; the geometry
        # restores the same physical lines from the unspaced output.
        physical, _ = repair_page_lines(1, original, geometry)
        expected = [" ".join(line.split()) for line in physical]
        fixed, repairs = repair_page_lines(1, spaced, geometry)
        self.assertEqual(fixed, expected)
        self.assertTrue(repairs and {r.method for r in repairs} == {"geometry"})
        self.assertTrue(all(r.original != r.repaired for r in repairs))  # provenance kept
        text_only, repairs = repair_page_lines(1, spaced, None)  # no PDFium geometry
        # Without geometry a digit next to a letter keeps its space (glued item
        # numbers); some extractor versions glue "1" + "NOT" across cells.
        digit_letter = re.compile(r"(?<=\d)(?=[^\W\d_])|(?<=[^\W\d_])(?=\d)")
        self.assertEqual(text_only, [digit_letter.sub(" ", " ".join(line.split()))
                                     for line in original])
        self.assertEqual({r.method for r in repairs}, {"text"})
        (instrument,) = parse_scientific_lines([(1, line) for line in fixed], "spaced.pdf").instruments
        self.assertEqual([row.number for row in instrument.questions], list(range(1, 17)))

    def test_lines_glued_by_the_extractor_are_split_at_real_line_changes(self):
        """Any pypdf version: text merged across physical lines without a space
        (e.g. "invented" + "garden", "1" + "NOT AT" + "ALL") is restored from
        PDFium's glyph lines, also when the merge is in a different order."""
        data = coping_text_pdf(scoring=False)
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            geometry = pdf_page_glyph_lines(pdf, 1)
        finally:
            pdf.close()
        physical = ["".join(glyph.char for glyph in line.glyphs) for line in geometry]
        prompt = next(i for i, text in enumerate(physical) if text.startswith("During"))
        first, second = physical[prompt], physical[prompt + 1]
        glued = first + second.lstrip()            # no whitespace at the line change
        fixed, repairs = repair_page_lines(1, [glued], geometry)
        self.assertEqual(fixed, [" ".join(first.split()), " ".join(second.split())])
        self.assertTrue(repairs and repairs[0].original == glued)  # provenance kept
        # A line that only looks merged but keeps its spaces stays untouched.
        spaced = first + " " + second.lstrip()
        self.assertEqual(repair_page_lines(1, [spaced], geometry)[0], [spaced])
        # Rotated pages list the glyph lines in another order, and every item
        # repeats "During the invented week I kept": no prompt line may be cut
        # where a neighbouring item's line happens to continue the same words.
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        writer.add_page(PdfReader(BytesIO(data)).pages[0].rotate(90))
        stream = BytesIO()
        writer.write(stream)
        restored = []
        for blob in (data, stream.getvalue()):
            pdf = pdfium.PdfDocument(blob)
            try:
                page_geometry = pdf_page_glyph_lines(pdf, 1)
            finally:
                pdf.close()
            lines = PdfReader(BytesIO(blob)).pages[0].extract_text().splitlines()
            fixed = repair_page_lines(1, lines, page_geometry)[0]
            restored.append([re.sub(r"^\d+ ", "", line) for line in fixed if "During" in line])
        self.assertEqual(len(restored[0]), 16)
        self.assertEqual(restored[1], restored[0])

    def test_ordinary_text_layers_are_not_changed(self):
        data = connectedness_text_pdf()
        from pypdf import PdfReader

        pages = [(n, page.extract_text().splitlines())
                 for n, page in enumerate(PdfReader(BytesIO(data)).pages, 1)]
        fixed, repairs = repair_pdf_text(data, pages)
        self.assertEqual(repairs, ())
        self.assertEqual(fixed, pages)


class RepeatedChoiceLineTests(unittest.TestCase):
    def parse(self, rows, name="coping.pdf", **kwargs):
        (instrument,) = parse_scientific_lines(rows, name, **kwargs).instruments
        return instrument

    def test_codes_and_labels_on_lines(self):
        self.assertEqual(code_of("3"), 3)
        self.assertEqual(code_of("③"), 3)
        self.assertEqual(code_of("(2)"), 2)
        self.assertIsNone(code_of("3 apples"))
        self.assertEqual(code_label_of("2 A SMALL AMOUNT"), (2, "A SMALL AMOUNT"))
        self.assertEqual(code_label_of("④ VERY MUCH"), (4, "VERY MUCH"))
        self.assertEqual(printed_label("WE  DIDNʼT\nTRY"), "WE DIDN'T TRY")

    def test_standalone_numbers_and_wrapped_choices_after_every_item(self):
        rows = coping_text_lines()
        self.assertEqual(sum(1 for _, line in rows if line == "1"), 29)  # item 1 + 28 codes
        instrument = self.parse(rows)
        self.assertEqual(instrument.title, COPING_TITLE)  # not the form-field line
        self.assertEqual([row.number for row in instrument.questions], list(range(1, 29)))
        self.assertEqual([row.question["prompt"] for row in instrument.questions],
                         coping_statements())
        self.assertEqual({row.page for row in instrument.questions[:16]}, {1})
        self.assertEqual({row.page for row in instrument.questions[16:]}, {2})
        (scheme,) = instrument.schemes
        self.assertEqual(scheme.labels, COPING_LABELS)          # exactly as printed
        self.assertEqual(scheme.codes, ("1", "2", "3", "4"))    # because printed
        self.assertEqual(scheme.evidence, "item_block")
        self.assertEqual(scheme.issues, ())
        self.assertEqual(len(linked_questions(instrument, scheme.id)), 28)
        self.assertEqual(kinds(instrument), {"single_choice": 28})  # never short_text
        self.assertFalse(any(row.question.get("value_labels") for row in instrument.questions))
        self.assertEqual(
            scheme_banner(instrument),
            "28 questions use an unverified 4-choice scale (NOT AT ALL / A SMALL AMOUNT / "
            "A FAIR AMOUNT / VERY MUCH). Review and confirm the response scale before importing.",
        )
        with self.assertRaisesRegex(ValueError, "unverified 4-choice"):
            reviewed_draft(instrument)

    def test_inline_circled_and_single_line_choices(self):
        for kwargs in (dict(numbering="inline"), dict(numbering="circled"),
                       dict(same_line_codes=True)):
            instrument = self.parse(coping_text_lines(**kwargs))
            count = kwargs.get("count", 28)
            self.assertEqual([row.number for row in instrument.questions],
                             list(range(1, count + 1)), kwargs)
            self.assertEqual(instrument.schemes[0].labels, COPING_LABELS, kwargs)

    def test_code_only_blocks_take_labels_from_this_instruments_legend(self):
        labels = ("NEVER TRUE", "RARELY TRUE", "OFTEN TRUE", "ALWAYS TRUE")
        rows = coping_text_lines(labels=("", "", "", ""))  # only codes after every item
        rows.insert(3, (1, "  ".join(f"{n} = {label}" for n, label in enumerate(labels, 1))))
        instrument = self.parse(rows)
        (scheme,) = instrument.schemes
        self.assertEqual((scheme.labels, scheme.codes), (labels, ("1", "2", "3", "4")))
        self.assertEqual(scheme.evidence, "item_block+legend")
        self.assertEqual(len(linked_questions(instrument, scheme.id)), 28)
        # Without a legend the labels must be entered before the scale is usable.
        bare = self.parse(coping_text_lines(labels=("", "", "", "")))
        self.assertTrue(bare.schemes[0].label_problems())
        self.assertIn("unverified 4-choice scale (labels missing)", scheme_banner(bare))

    def test_a_block_that_differs_on_one_item_is_reported(self):
        odd = ("NOT AT ALL", "A SMALL AMOUNT", "RATHER OFTEN", "VERY MUCH")
        instrument = self.parse(coping_text_lines(overrides={7: odd}))
        (scheme,) = instrument.schemes
        self.assertEqual(scheme.labels, COPING_LABELS)
        self.assertTrue(any("item(s) 7" in issue and "RATHER OFTEN" in issue
                            for issue in scheme.issues), scheme.issues)
        self.assertIn("answer choices differ from the common scale",
                      instrument.evidence.flags_for(7))
        self.assertIn("RATHER OFTEN", instrument.questions[6].notes[-2])

    def test_ocr_label_consensus_takes_the_spelling_most_copies_print(self):
        # A Windows OCR engine read one copy as "NOT AT An" and another as
        # "NOT AT AUT.": "An" resembles both other spellings, yet the scale
        # label is the one that most copies print.
        rest = COPING_LABELS[1:]
        garbled = {1: ("NOT AT An", *rest), 16: ("NOT AT AUT.", *rest)}
        instrument = self.parse(coping_text_lines(overrides=garbled), "scan.pdf",
                                page_count=2, ocr_pages=(1, 2))
        (scheme,) = instrument.schemes
        self.assertEqual(scheme.labels, COPING_LABELS)
        self.assertTrue(any("item(s) 1, 16" in issue and "NOT AT An" in issue
                            for issue in scheme.issues), scheme.issues)

    def test_a_different_repeated_block_is_a_separate_scale(self):
        other = ("NEVER TRUE", "RARELY TRUE", "OFTEN TRUE", "ALWAYS TRUE")
        instrument = self.parse(coping_text_lines(overrides={n: other for n in range(21, 29)}))
        self.assertEqual(sorted(len(linked_questions(instrument, s.id)) for s in instrument.schemes),
                         [8, 20])
        self.assertEqual({s.labels for s in instrument.schemes}, {COPING_LABELS, other})

    def test_missing_item_is_reported_and_blocks_the_draft(self):
        instrument = self.parse(coping_text_lines(missing=(14,)))
        self.assertEqual(len(instrument.questions), 27)
        self.assertEqual(instrument.evidence.missing_items, (14,))
        self.assertEqual(
            missing_items_banner(instrument),
            "Item 14 is missing from the numbered sequence 1–28. Check the source page, add "
            "the item(s) or confirm that the source omits them before importing.",
        )
        self.assertTrue(any("14" in w and "missing" in w for w in instrument.warnings))
        confirmed = confirm(instrument)
        self.assertIsNone(scheme_banner(confirmed))
        self.assertIn("Item 14 is missing", review_banner(confirmed))
        with self.assertRaisesRegex(ValueError, "Item 14 is missing"):
            reviewed_draft(confirmed)
        draft = reviewed_draft(acknowledge_missing_items(confirmed))
        self.assertEqual(len(draft), 27)

    def test_scoring_item_absent_from_the_items_is_missing(self):
        instrument = self.parse(coping_text_lines(count=27))  # styles list item 28
        self.assertEqual(instrument.evidence.missing_items, (28,))
        group = next(g for g in instrument.evidence.scoring_groups if 28 in g.items)
        self.assertTrue(any("28" in issue for issue in group.issues))

    def test_ordinary_forms_are_not_mistaken_for_repeated_blocks(self):
        plain = [(1, "Synthetic open form")]
        for n in range(1, 11):
            plain += [(1, str(n)), (1, f"Describe invented hobby number {n} in your own words.")]
        lines, layout = segment_repeated_choices(plain)
        self.assertIsNone(layout)
        self.assertEqual(lines, plain)
        anchors = [(1, "Scale of 1-4"), (1, "1- Never"), (1, "2- Rarely"), (1, "3- Sometimes"),
                   (1, "4- Always")] + [
            (1, f"{n}) How frequently did fictional experience number {n} occur?")
            for n in range(1, 11)
        ]
        self.assertIsNone(segment_repeated_choices(anchors)[1])


class ScoringEvidenceTests(unittest.TestCase):
    def test_documented_scoring_is_captured_but_never_applied(self):
        (instrument,) = parse_scientific_lines(coping_text_lines(), "coping.pdf",
                                               text_source="pdf_text_layer").instruments
        evidence = instrument.evidence
        self.assertEqual([(g.name, g.items) for g in evidence.scoring_groups],
                         [(name, items) for name, items in COPING_STYLES])
        for group in evidence.scoring_groups:
            self.assertEqual((group.aggregation, group.stated_count, group.value_range),
                             ("mean", len(group.items), "1–4"))
            self.assertEqual((group.page, group.evidence, group.issues), (2, "pdf_text_layer", ()))
            self.assertTrue(group.source_line.startswith(group.name))
            self.assertFalse(group.approved)
        self.assertTrue(any("sum over all items" in s.text for s in evidence.scoring_statements))
        self.assertEqual(evidence.unassigned_items(range(1, 29)), ())
        self.assertFalse(evidence.ocr_only)
        self.assertEqual(instrument.scoring.reverse_numbers, ())  # no reverse keys inferred
        with self.assertRaisesRegex(ValueError, "numeric codes of the shared scale"):
            approve_scoring_evidence(instrument)
        coded = confirm(instrument, numeric=True)
        approved = approve_scoring_evidence(coded)
        self.assertTrue(approved.evidence.scoring_approved)
        draft = reviewed_draft(approved)
        self.assertEqual(draft, reviewed_draft(coded))  # approval changes nothing
        self.assertEqual({q["kind"] for q in draft}, {"rating_scale"})
        self.assertFalse(any(q["reverse_scored"] for q in draft))
        self.assertEqual(draft[0]["value_labels"], dict(zip("1234", COPING_LABELS)))

    def test_ocr_only_scoring_needs_its_own_check(self):
        (instrument,) = parse_scientific_lines(
            coping_text_lines(), "scan.pdf", ocr_pages=(1, 2),
        ).instruments
        self.assertTrue(instrument.evidence.ocr_only)
        self.assertTrue(all("OCR" in g.issues[-1] for g in instrument.evidence.scoring_groups))
        coded = confirm(instrument, numeric=True)
        with self.assertRaisesRegex(ValueError, "OCR only"):
            approve_scoring_evidence(coded)
        self.assertTrue(approve_scoring_evidence(coded, ocr_checked=True).evidence.scoring_approved)
        self.assertIn("read by OCR", instrument.evidence.flags_for(1))


class DocumentImportTests(unittest.TestCase):
    def test_text_pdf_over_two_pages(self):
        review = read(coping_text_pdf(), "coping.pdf")
        (instrument,) = review.instruments
        self.assertEqual(instrument.title, COPING_TITLE)
        self.assertEqual([row.number for row in instrument.questions], list(range(1, 29)))
        self.assertEqual({row.page for row in instrument.questions}, {1, 2})
        (scheme,) = instrument.schemes
        self.assertEqual((scheme.labels, scheme.codes), (COPING_LABELS, ("1", "2", "3", "4")))
        self.assertEqual(scheme.evidence, "item_block+matrix")  # geometric cell grid linked
        self.assertEqual(scheme.issues, ())
        self.assertTrue(all(row.matrix_row for row in instrument.questions))
        (matrix,) = review.matrices
        self.assertEqual([(c.label, c.code) for c in matrix.columns],
                         list(zip(COPING_LABELS, ("1", "2", "3", "4"))))
        self.assertEqual((len(matrix.rows), matrix.pages), (28, (1, 2)))
        self.assertEqual(matrix.unresolved_cells, ())
        self.assertEqual(sum(1 for _, regions in review.spatial.links if regions), 28)
        self.assertEqual(len(instrument.evidence.scoring_groups), 3)
        self.assertEqual(instrument.evidence.missing_items, ())
        draft = reviewed_draft(confirm(instrument))
        self.assertEqual({q["kind"] for q in draft}, {"single_choice"})
        self.assertEqual(draft[27]["options"], list(COPING_LABELS))

    def test_circled_ring_inline_numbering_and_rotated_pages(self):
        from pypdf import PdfReader, PdfWriter

        for numbering in ("circled", "ring", "inline"):
            count = 28
            data = coping_text_pdf(numbering=numbering, count=count, scoring=False)
            (instrument,) = read(data, f"{numbering}.pdf").instruments
            self.assertEqual([row.number for row in instrument.questions],
                             list(range(1, count + 1)), numbering)
            self.assertEqual(instrument.schemes[0].labels, COPING_LABELS, numbering)
        writer = PdfWriter()
        for page in PdfReader(BytesIO(coping_text_pdf())).pages:
            writer.add_page(page.rotate(90))
        stream = BytesIO()
        writer.write(stream)
        review = read(stream.getvalue(), "rotated.pdf")  # /Rotate 90 pages
        (instrument,) = review.instruments
        self.assertEqual(len(instrument.questions), 28)
        self.assertEqual(instrument.schemes[0].labels, COPING_LABELS)
        page = review.spatial.page(1)
        self.assertGreater(page.pixel_width, page.pixel_height)  # displayed as rotated
        linked = sum(1 for _, regions in review.spatial.links if regions)
        if linked < 28:
            unlinked = [key for key, regions in review.spatial.links if not regions]
            self.fail(f"{linked} of 28 rotated items linked; unlinked {unlinked}\n"
                      + spacing_diagnostics(stream.getvalue()))

    def test_latvian_and_russian_labels_stay_as_printed(self):
        for language, labels in (("lv", COPING_LABELS_LV), ("ru", COPING_LABELS_RU)):
            review = read(coping_text_pdf(language=language, labels=labels), f"{language}.pdf")
            (instrument,) = review.instruments
            self.assertEqual(len(instrument.questions), 28, language)
            self.assertEqual(instrument.questions[3].question["prompt"],
                             coping_statements(language=language)[3])
            (scheme,) = instrument.schemes
            self.assertEqual(scheme.labels, labels, language)
            self.assertEqual(reviewed_draft(confirm(instrument))[0]["options"], list(labels))
            self.assertEqual([g.items for g in instrument.evidence.scoring_groups],
                             [items for _, items in COPING_STYLES], language)

    def test_word_tables_with_choice_cells_or_header_columns(self):
        for header_columns in (False, True):
            review = read(coping_docx(header_columns=header_columns), "coping.docx")
            (instrument,) = review.instruments
            self.assertEqual(len(instrument.questions), 28, header_columns)
            (scheme,) = instrument.schemes
            self.assertEqual(scheme.labels, COPING_LABELS, header_columns)
            self.assertEqual(scheme.codes, ("1", "2", "3", "4"))
            self.assertEqual(scheme.issues, ())
            self.assertEqual(kinds(instrument), {"single_choice": 28})
            self.assertEqual({g.evidence for g in instrument.evidence.scoring_groups}, {"docx"})
        missing = read(coping_docx(missing=(14,)), "gap.docx").instruments[0]
        self.assertEqual(missing.evidence.missing_items, (14,))

    def test_pdf_with_a_missing_item(self):
        (instrument,) = read(coping_text_pdf(missing=(14,)), "gap.pdf").instruments
        self.assertEqual(len(instrument.questions), 27)
        self.assertEqual([row.number for row in instrument.questions][12:14], [13, 15])
        self.assertEqual(instrument.evidence.missing_items, (14,))
        with self.assertRaisesRegex(ValueError, "Item 14 is missing"):
            reviewed_draft(confirm(instrument))

    def test_export_through_survey_storage(self):
        (instrument,) = read(coping_text_pdf(), "coping.pdf").instruments
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for numeric in (False, True):
                draft = reviewed_draft(confirm(instrument, numeric=numeric))
                survey = create_survey(root / str(numeric), "Synthetic coping import",
                                       "Invented fixture", draft)
                answers = {
                    q["key"]: ((n % 4) + 1 if numeric else COPING_LABELS[n % 4])
                    for n, q in enumerate(survey.questions)
                }
                submit_response(root / str(numeric), survey.survey_id, answers)
                frame = responses_dataframe(root / str(numeric), survey.survey_id)
                first = survey.questions[0]["key"]
                self.assertEqual(frame[first].iloc[0], 1 if numeric else "NOT AT ALL")
                csv = save_survey_csv(root / str(numeric), survey.survey_id,
                                      root / f"out_{numeric}.csv").read_text(encoding="utf-8-sig")
                self.assertIn(survey.questions[27]["key"], csv)
                codebook = json.loads(save_survey_codebook(
                    root / str(numeric), survey.survey_id, root / f"codebook_{numeric}.json",
                ).read_text(encoding="utf-8"))
                question = codebook["questions"][0]
                if numeric:
                    self.assertEqual(question["value_labels"], dict(zip("1234", COPING_LABELS)))
                    self.assertEqual(question["measurement_level"], "ordinal")
                else:
                    self.assertEqual(question["options"], list(COPING_LABELS))
                text = json.dumps(codebook, ensure_ascii=False)
                self.assertNotIn("Synthetic planning style", text)  # scoring never exported
                self.assertNotIn('"reverse_scored": true', text.replace(" ", ""))


class AuditToolTests(unittest.TestCase):
    def test_structure_report_prints_no_source_wording(self):
        import importlib.util

        tool = Path(__file__).resolve().parents[1] / "tools" / "audit_local_survey_docs.py"
        spec = importlib.util.spec_from_file_location("audit_local_survey_docs", tool)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        review = read(coping_text_pdf(missing=(14,), letter_spaced=True), "gap.pdf")
        text = "\n".join(audit.structure_report(review, source="text layer", items=True))
        self.assertIn("Item numbers found: 1–13, 15–28; missing: 14", text)
        self.assertIn("common block 4 choices, codes 1,2,3,4", text)
        self.assertIn("evidence item_block+matrix | linked items 1–13, 15–28", text)
        self.assertIn("Documented scoring g3", text)
        self.assertIn("Draft blocked by: unverified scale, missing items", text)
        self.assertRegex(text, r"Spacing repairs: \d+ line")
        for wording in (*COPING_LABELS, COPING_TITLE, "invented", "Synthetic planning", "situation"):
            self.assertNotIn(wording, text)


@unittest.skipUnless(tesseract_available(), "No local Tesseract engine installed")
class ScannedCopingFormTests(unittest.TestCase):
    def test_scanned_form_with_real_ocr(self):
        review = ocr_scientific_pdf(coping_scan_pdf(), "coping_scan.pdf", [1, 2], "eng")
        seen = "\n".join(line.text for page in review.spatial.pages for line in page.lines[:6])
        self.assertEqual(len(review.instruments), 1, seen)
        (instrument,) = review.instruments
        (scheme,) = instrument.schemes
        report = f"{scheme.labels} {scheme.codes} {scheme.issues[:2]}\n{seen}"
        self.assertEqual(scheme.labels, COPING_LABELS, report)
        self.assertEqual(scheme.codes, ("1", "2", "3", "4"), report)
        self.assertGreaterEqual(len(linked_questions(instrument, scheme.id)), 25, report)
        self.assertTrue(any("OCR" in issue for issue in scheme.issues))
        numbers = [row.number for row in instrument.questions]
        self.assertEqual(numbers, sorted(numbers))
        self.assertLessEqual(max(numbers), 28)
        self.assertNotIn("short_text", kinds(instrument))
        self.assertIn("read by OCR", instrument.evidence.flags_for(numbers[0]))
        self.assertTrue(any(m.source_kind == "tesseract_tsv" and len(m.columns) == 4
                            for m in review.matrices))


class CopingImportUITests(unittest.IsolatedAsyncioTestCase):
    """Import → blocked draft → scale review → draft → preview (→ missing item)."""

    def setUp(self):
        from survey_ui import build_survey_workspace
        from test_visual_survey_import_ui import DummyPage

        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.page = DummyPage()

        async def noop(frame):
            return True

        self.view = build_survey_workspace(self.page, root=self.root / "surveys",
                                           load_dataframe=noop)

    def texts(self):
        from test_visual_survey_import_ui import children
        return " ".join(c.value for c in children(self.view)
                        if isinstance(c, ft.Text) and isinstance(c.value, str))

    def find(self, cls, label):
        from test_visual_survey_import_ui import find
        return find(self.view, cls, label=label)

    async def open(self, data, name):
        path = self.root / name
        path.write_bytes(data)
        await self.page.services[-1].on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(path), name=path.name)]
        ))

    def confirm_scale(self):
        self.find(ft.Checkbox, "Confirm structure: all linked questions share these "
                               "categories and labels").value = True
        self.find(ft.Button, "Apply scale review to all linked questions").on_click(None)

    async def test_structured_preview_after_scale_confirmation(self):
        from test_visual_survey_import_ui import children

        await self.open(coping_text_pdf(), "coping.pdf")
        self.assertIn("28 questions use an unverified 4-choice scale (NOT AT ALL / A SMALL "
                      "AMOUNT / A FAIR AMOUNT / VERY MUCH)", self.texts())
        self.assertEqual(self.find(ft.TextField, "Category 1 label").value, "NOT AT ALL")
        self.assertEqual(self.find(ft.TextField, "Category 4 code").value, "4")
        self.confirm_scale()
        self.assertIn("Applied to 28 linked questions: structure confirmed", self.texts())
        self.find(ft.Checkbox, "I verified the instrument version, wording, permissions "
                               "and extracted question list against the source").value = True
        self.find(ft.Button, "Use extracted questions as editable draft").on_click(None)
        self.assertIn("Imported 28 editable questions", self.texts())
        preview = next(c for c in children(self.view)
                       if isinstance(c, ft.Button) and c.content == "2. Preview")
        preview.on_click(None)
        choices = [c for c in children(self.view)
                   if isinstance(c, ft.Dropdown) and c.label == "Choose one answer"]
        self.assertEqual(len(choices), 28)
        self.assertEqual([o.key for o in choices[0].options], list(COPING_LABELS))
        free_text = [c for c in children(self.view)
                     if isinstance(c, ft.TextField) and c.label == "Your answer"]
        self.assertEqual(free_text, [])

    async def test_missing_item_needs_an_explicit_acknowledgement(self):
        await self.open(coping_text_pdf(missing=(14,)), "gap.pdf")
        self.assertIn("Item 14 is missing from the numbered sequence 1–28", self.texts())
        self.confirm_scale()
        approve = self.find(ft.Checkbox, "I verified the instrument version, wording, "
                                         "permissions and extracted question list against the source")
        approve.value = True
        commit = self.find(ft.Button, "Use extracted questions as editable draft")
        commit.on_click(None)
        self.assertIn("Cannot use proposed draft: Item 14 is missing", self.texts())
        acknowledge = self.find(ft.Checkbox, "I checked the source: the missing item number(s) "
                                             "are not printed there")
        self.assertTrue(acknowledge.visible)
        acknowledge.value = True
        commit.on_click(None)
        self.assertIn("Imported 27 editable questions", self.texts())


if __name__ == "__main__":
    unittest.main()
