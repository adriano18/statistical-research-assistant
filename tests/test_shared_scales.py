"""Shared 4-category response scales (#18): detection, linking, review, draft.

Fixtures are synthetic "connectedness" inventories that only imitate the
LAYOUT of UCLA-style forms (an O/S/R/N original form with a legend and a
Never/Rarely/Sometimes/Often revised form with 1–4 codes and a reverse-key
note). No published item wording is used.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import flet as ft

from ocr_runtime import tesseract_available
from response_scales import (
    match_scale_header, normalize_tokens, parse_code_legend, parse_legend,
    split_row_tokens,
)
from scientific_survey_import import (
    linked_questions, parse_scientific_lines, read_scientific_document,
    reviewed_draft, scheme_banner,
)
from shared_scales import review_scheme, unlink_scheme
from survey_storage import (
    responses_dataframe, save_survey_codebook, save_survey_csv,
    submit_response,
)
from synthetic_documents import (
    ORIGINAL_LABELS, REVISED_LABELS, REVISED_REVERSE, connectedness_docx,
    connectedness_scan_pages, connectedness_text_pdf,
    image_pdf,
)
from visual_survey_review import (
    attach_docx_matrices, attach_text_layer_geometry, edit_candidate_question,
    ocr_scientific_pdf,
)


def read_pdf(data, name="two_forms.pdf"):
    with TemporaryDirectory() as temp:
        path = Path(temp) / name
        path.write_bytes(data)
        review = read_scientific_document(path)
    return attach_text_layer_geometry(review, data)


def kinds(instrument):
    found = {}
    for q in instrument.questions:
        found[q.question["kind"]] = found.get(q.question["kind"], 0) + 1
    return found


class ScaleTextTests(unittest.TestCase):
    def test_legends_headers_and_row_tokens(self):
        legend = parse_legend("O = Often   S = Sometimes   R = Rarely   N = Never")
        self.assertEqual(legend, dict(zip("OSRN", ORIGINAL_LABELS)))
        self.assertEqual(parse_code_legend("1 = Never  2 = Rarely  3 = Sometimes"),
                         {"1": "Never", "2": "Rarely", "3": "Sometimes"})
        header = match_scale_header("O S R N", legend)
        self.assertEqual(header.labels, ORIGINAL_LABELS)
        self.assertTrue(header.defined)
        undefined = match_scale_header("O S R N")
        self.assertFalse(undefined.defined)
        self.assertEqual(undefined.labels, ("O", "S", "R", "N"))
        for text in ("Never Rarely Sometimes Often", "Statement Never Rarely Sometimes Often",
                     "Никогда Редко Иногда Часто", "Nekad Reti Dažreiz Bieži",
                     "Strongly disagree Disagree Neutral Agree Strongly agree"):
            self.assertIsNotNone(match_scale_header(text), text)
        partial = match_scale_header("Almost Sometimes Often Usually")
        self.assertEqual(partial.uncertain, ("Almost",))
        for prose in ("I often feel left out", "Never Rarely Often Never", "Sometimes Often"):
            self.assertIsNone(match_scale_header(prose), prose)
        self.assertEqual(split_row_tokens("3. I feel close to invented friends. O S R N")[1],
                         ("O", "S", "R", "N"))
        self.assertEqual(split_row_tokens("3. I visit the USA often")[1], ())
        self.assertEqual(normalize_tokens(("I", "2", "3", "4")), ("1", "2", "3", "4"))


class TwoVersionPdfTests(unittest.TestCase):
    def setUp(self):
        self.review = read_pdf(connectedness_text_pdf())
        self.original, self.revised = self.review.instruments

    def test_original_and_revised_versions_stay_separate(self):
        self.assertEqual(len(self.review.instruments), 2)
        self.assertEqual(self.original.title, "SYNTHETIC CONNECTEDNESS INVENTORY")
        self.assertEqual(self.revised.title, "REVISED SYNTHETIC CONNECTEDNESS INVENTORY")
        self.assertEqual([len(i.questions) for i in self.review.instruments], [20, 20])
        (orig,) = self.original.schemes
        (rev,) = self.revised.schemes
        self.assertEqual(orig.labels, ORIGINAL_LABELS)   # from THIS form's legend
        self.assertEqual(orig.printed, ("O", "S", "R", "N"))
        self.assertEqual(orig.codes, (None,) * 4)         # none printed
        self.assertEqual(orig.reverse_items, ())          # revised note not borrowed
        self.assertEqual(rev.labels, REVISED_LABELS)
        self.assertEqual(rev.codes, ("1", "2", "3", "4"))
        self.assertEqual(rev.reverse_items, REVISED_REVERSE)
        self.assertIn("reverse", rev.reverse_evidence.lower())

    def test_every_matrix_row_is_linked_to_its_question(self):
        for instrument in self.review.instruments:
            (scheme,) = instrument.schemes
            self.assertIsNotNone(scheme.matrix_id)
            self.assertEqual(len(linked_questions(instrument, scheme.id)), 20)
            self.assertTrue(all(q.matrix_row and q.matrix_row.startswith(scheme.matrix_id)
                                for q in instrument.questions))
            self.assertEqual(kinds(instrument), {"single_choice": 20})
        self.assertNotEqual(self.original.schemes[0].matrix_id, self.revised.schemes[0].matrix_id)
        # Source regions stay linked for the overlay (text layer, not OCR).
        evidence = self.review.spatial
        self.assertTrue(evidence.regions("1:0"))

    def test_unverified_scale_blocks_the_draft(self):
        banner = scheme_banner(self.original)
        self.assertEqual(
            banner,
            "20 questions use an unverified 4-choice scale (Often / Sometimes / Rarely / "
            "Never). Review and confirm the response scale before importing.",
        )
        with self.assertRaisesRegex(ValueError, "unverified 4-choice"):
            reviewed_draft(self.original)

    def test_structure_codes_and_reverse_are_confirmed_separately(self):
        rev = self.revised.schemes[0]
        common = dict(labels=rev.labels, codes=rev.codes, reverse_items=rev.reverse_items)
        structure = review_scheme(self.revised, rev.id, structure=True, **common)
        draft = reviewed_draft(structure)
        self.assertEqual({q["kind"] for q in draft}, {"single_choice"})
        self.assertEqual(draft[0]["options"], list(REVISED_LABELS))  # exactly as printed
        coded = review_scheme(self.revised, rev.id, structure=True, numeric=True, **common)
        draft = reviewed_draft(coded)
        self.assertEqual(draft[0]["kind"], "rating_scale")
        self.assertEqual(draft[0]["value_labels"], dict(zip("1234", REVISED_LABELS)))
        self.assertFalse(any(q["reverse_scored"] for q in draft))
        keyed = review_scheme(self.revised, rev.id, structure=True, numeric=True,
                              reverse=True, **common)
        draft = reviewed_draft(keyed)
        self.assertEqual([i for i, q in enumerate(draft, 1) if q["reverse_scored"]],
                         list(REVISED_REVERSE))
        with self.assertRaisesRegex(ValueError, "numeric coding before reverse"):
            review_scheme(self.revised, rev.id, structure=True, reverse=True, **common)
        orig = self.original.schemes[0]
        with self.assertRaisesRegex(ValueError, "numeric code for every category"):
            review_scheme(self.original, orig.id, structure=True, numeric=True,
                          labels=orig.labels, codes=orig.codes, reverse_items=())

    def test_edits_reset_confirmations_and_manual_edits_survive(self):
        rev = self.revised.schemes[0]
        confirmed = review_scheme(self.revised, rev.id, structure=True, labels=rev.labels,
                                  codes=rev.codes, reverse_items=())
        relabelled = review_scheme(confirmed, rev.id, labels=("Not at all", *rev.labels[1:]),
                                   codes=rev.codes, reverse_items=())
        self.assertFalse(relabelled.schemes[0].structure_confirmed)
        self.assertEqual(relabelled.questions[0].question["options"][0], "Not at all")
        manual = edit_candidate_question(
            confirmed, 3, prompt=confirmed.questions[3].question["prompt"],
            kind="short_text", options_text="", section="",
        )
        self.assertIsNone(manual.questions[3].scheme_id)
        self.assertFalse(manual.schemes[0].structure_confirmed)  # membership changed
        again = review_scheme(manual, rev.id, structure=True, labels=rev.labels,
                              codes=rev.codes, reverse_items=())
        draft = reviewed_draft(again)
        self.assertEqual(draft[3]["kind"], "short_text")      # manual edit kept
        self.assertEqual(draft[4]["kind"], "single_choice")

    def test_researcher_can_declare_items_not_a_scale(self):
        orig = self.original.schemes[0]
        text = unlink_scheme(self.original, orig.id)
        self.assertEqual(text.schemes, ())
        self.assertEqual({q["kind"] for q in reviewed_draft(text)}, {"short_text"})
        self.assertIn("not a shared scale", text.questions[0].notes[-1])


class VariantTests(unittest.TestCase):
    def test_uncoded_revised_form_has_no_codes(self):
        review = read_pdf(connectedness_text_pdf(coded=False, reverse_note=False))
        rev = review.instruments[1].schemes[0]
        self.assertEqual(rev.codes, (None,) * 4)
        self.assertEqual(rev.reverse_items, ())
        self.assertEqual(rev.labels, REVISED_LABELS)

    def test_undefined_abbreviations_require_labels(self):
        review = read_pdf(connectedness_text_pdf(legend=False))
        original = review.instruments[0]
        scheme = original.schemes[0]
        self.assertTrue(scheme.label_problems())
        self.assertEqual(kinds(original), {"short_text": 20})  # not usable yet …
        self.assertIn("unverified", scheme_banner(original))   # … but never silent
        with self.assertRaisesRegex(ValueError, "Abbreviations"):
            review_scheme(original, scheme.id, structure=True, labels=scheme.labels,
                          codes=scheme.codes, reverse_items=())
        fixed = review_scheme(original, scheme.id, structure=True, labels=ORIGINAL_LABELS,
                              codes=scheme.codes, reverse_items=())
        self.assertEqual(reviewed_draft(fixed)[0]["options"], list(ORIGINAL_LABELS))

    def test_matrix_split_over_pages_with_repeated_header(self):
        review = read_pdf(connectedness_text_pdf(split_revised=True))
        revised = review.instruments[1]
        self.assertEqual(len(revised.questions), 20)
        self.assertEqual(len(revised.schemes), 1)
        self.assertEqual(len(linked_questions(revised, revised.schemes[0].id)), 20)
        self.assertEqual({q.page for q in revised.questions}, {2, 3})

    def test_psq_style_reverse_rule_is_a_proposal(self):
        rows = ["Synthetic Pressure Form", "Almost Sometimes Often Usually"]
        rows += [f"{n}. You feel invented pressure number {n} 1 2 3 4" for n in range(1, 11)]
        rows += ["Score 5-circled number for items 1, 4, 7", "Score circled number for all other items"]
        (inst,) = parse_scientific_lines([(1, r) for r in rows], "psq_like.pdf").instruments
        (scheme,) = inst.schemes
        self.assertEqual(scheme.codes, ("1", "2", "3", "4"))
        self.assertEqual(scheme.reverse_items, (1, 4, 7))
        self.assertTrue(any("incomplete" in issue for issue in scheme.issues))
        self.assertFalse(any(q.question.get("reverse_scored") for q in inst.questions))

    def test_docx_tables_link_to_extracted_questions(self):
        for coded in (False, True):
            data = connectedness_docx(coded_row=coded)
            with TemporaryDirectory() as temp:
                path = Path(temp) / "table.docx"
                path.write_bytes(data)
                review = attach_docx_matrices(read_scientific_document(path), data)
            (inst,) = review.instruments
            (scheme,) = inst.schemes
            self.assertEqual(scheme.labels, ORIGINAL_LABELS)  # legend paragraph
            self.assertEqual(len(linked_questions(inst, scheme.id)), 20)
            self.assertEqual(scheme.codes, ("1", "2", "3", "4") if coded else (None,) * 4)
            self.assertTrue(all(q.matrix_row for q in inst.questions))


@unittest.skipUnless(tesseract_available(), "No local Tesseract engine installed")
class ScannedTwoVersionTests(unittest.TestCase):
    def test_scanned_original_and_revised_forms(self):
        pdf = image_pdf(*connectedness_scan_pages())
        review = ocr_scientific_pdf(pdf, "scan.pdf", [1, 2], "eng")
        seen = "\n".join(
            f"p{page.page_number}: {line.text}"
            for page in review.spatial.pages for line in page.lines[:5]
        )
        self.assertEqual(len(review.instruments), 2, seen)
        original, revised = review.instruments
        report = seen + "\n" + "\n".join(
            f"{i.title}: {[(s.labels, s.codes, s.evidence, s.issues[:2]) for s in i.schemes]}"
            for i in review.instruments
        )
        self.assertEqual(original.schemes[0].labels, ORIGINAL_LABELS, report)
        self.assertEqual(revised.schemes[0].labels, REVISED_LABELS, report)
        for instrument in review.instruments:
            self.assertGreaterEqual(len(linked_questions(instrument, instrument.schemes[0].id)), 18)
        self.assertEqual(original.schemes[0].reverse_items, ())
        self.assertTrue(set(revised.schemes[0].reverse_items) <= set(REVISED_REVERSE))


class FullWorkflowUITests(unittest.IsolatedAsyncioTestCase):
    """Import → blocked draft → scale review → draft → preview → publish → export."""

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

    async def test_revised_form_from_pdf_to_preview_and_export(self):
        from test_visual_survey_import_ui import children

        path = self.root / "two_forms.pdf"
        path.write_bytes(connectedness_text_pdf())
        await self.page.services[-1].on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(path), name=path.name)]
        ))
        instrument = self.find(ft.Dropdown, "Extracted instrument / version")
        self.assertEqual(len(instrument.options), 2)
        instrument.value = "1"  # the revised form
        await instrument.on_select(None)
        # The viewer follows the selected version to its own page.
        self.assertEqual(self.find(ft.Dropdown, "Source page · visual preview").value, "2")
        self.assertIn("20 questions use an unverified 4-choice scale (Never / Rarely / "
                      "Sometimes / Often)", self.texts())
        confirm = self.find(ft.Checkbox, "I verified the instrument version, wording, "
                                         "permissions and extracted question list against the source")
        commit = self.find(ft.Button, "Use extracted questions as editable draft")
        confirm.value = True
        commit.on_click(None)
        self.assertIn("Cannot use proposed draft: 20 questions use an unverified", self.texts())
        # One coherent review: labels, codes and reverse items for all 20 rows.
        self.assertEqual(self.find(ft.TextField, "Category 1 label").value, "Never")
        self.assertEqual(self.find(ft.TextField, "Category 4 code").value, "4")
        self.assertEqual(self.find(ft.TextField, "Reverse-keyed items (as documented)").value,
                         ", ".join(map(str, REVISED_REVERSE)))
        self.find(ft.Checkbox, "Confirm structure: all linked questions share these "
                               "categories and labels").value = True
        self.find(ft.Checkbox, "Confirm numeric coding exactly as printed in the source").value = True
        self.find(ft.Button, "Apply scale review to all linked questions").on_click(None)
        self.assertIn("Applied to 20 linked questions: structure confirmed, numeric codes confirmed",
                      self.texts())
        self.assertFalse(confirm.value)  # document approvals reset after the review
        confirm.value = True
        commit.on_click(None)
        self.assertIn("Imported 20 editable questions", self.texts())

        preview = next(c for c in children(self.view)
                       if isinstance(c, ft.Button) and c.content == "2. Preview")
        preview.on_click(None)
        radios = [c for c in children(self.view) if isinstance(c, ft.RadioGroup)]
        free_text = [c for c in children(self.view)
                     if isinstance(c, ft.TextField) and c.label == "Your answer"]
        self.assertEqual(len(radios), 20)
        self.assertEqual(free_text, [])

        build = next(c for c in children(self.view)
                     if isinstance(c, ft.Button) and c.content == "1. Build")
        build.on_click(None)
        self.find(ft.Button, "Create local questionnaire").on_click(None)
        from survey_storage import list_surveys
        (survey,) = list_surveys(self.root / "surveys")
        kinds_ = {q["kind"] for q in survey.questions}
        self.assertEqual(kinds_, {"rating_scale"})
        answers = {q["key"]: (n % 4) + 1 for n, q in enumerate(survey.questions)}
        submit_response(self.root / "surveys", survey.survey_id, answers)
        frame = responses_dataframe(self.root / "surveys", survey.survey_id)
        self.assertEqual(int(frame[survey.questions[0]["key"]].iloc[0]), 1)
        csv_path = save_survey_csv(self.root / "surveys", survey.survey_id, self.root / "out.csv")
        self.assertIn(survey.questions[3]["key"], csv_path.read_text(encoding="utf-8"))
        codebook = json.loads(save_survey_codebook(
            self.root / "surveys", survey.survey_id, self.root / "codebook.json",
        ).read_text(encoding="utf-8"))
        text = json.dumps(codebook, ensure_ascii=False)
        self.assertIn("Sometimes", text)
        self.assertNotIn('"reverse_scored": true', text.replace(" ", ""))

    async def test_original_form_keeps_labels_without_numeric_codes(self):
        from test_visual_survey_import_ui import children

        path = self.root / "two_forms.pdf"
        path.write_bytes(connectedness_text_pdf())
        await self.page.services[-1].on_result(SimpleNamespace(
            files=[SimpleNamespace(path=str(path), name=path.name)]
        ))
        self.assertEqual(self.find(ft.TextField, "Category 1 label").value, "Often")
        self.assertTrue(self.find(ft.Checkbox, "Confirm numeric coding exactly as printed "
                                               "in the source").value is False)
        self.find(ft.Checkbox, "Confirm structure: all linked questions share these "
                               "categories and labels").value = True
        self.find(ft.Button, "Apply scale review to all linked questions").on_click(None)
        self.find(ft.Checkbox, "I verified the instrument version, wording, permissions "
                               "and extracted question list against the source").value = True
        self.find(ft.Button, "Use extracted questions as editable draft").on_click(None)
        self.assertIn("Imported 20 editable questions", self.texts())
        preview = next(c for c in children(self.view)
                       if isinstance(c, ft.Button) and c.content == "2. Preview")
        preview.on_click(None)
        choices = [c for c in children(self.view)
                   if isinstance(c, ft.Dropdown) and c.label == "Choose one answer"]
        self.assertEqual(len(choices), 20)
        self.assertEqual([o.key for o in choices[0].options], list(ORIGINAL_LABELS))


if __name__ == "__main__":
    unittest.main()
