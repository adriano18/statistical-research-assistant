"""Spatial OCR model, TSV parsing, confidence and region-edit regressions.

TSV fixtures are synthetic and mirror Tesseract 5 output columns.
"""

import unittest

from ocr_layout import (
    OCR_HIGH_THRESHOLD, OCR_REVIEW_THRESHOLD, PSYCHOMETRIC_NOTICE,
    aggregate_confidence, assess_structure, link_candidates, merge_regions,
    normalize_box, page_from_plain_text, page_from_positioned_words,
    parse_tesseract_tsv, question_ref, revert_links, review_queue,
    set_region_box, split_region, link_line, unlink_region, to_pixels,
    add_manual_region,
)
from scientific_survey_import import parse_scientific_lines

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def tsv(rows, width=1000, height=800):
    out = [HEADER, f"1\t1\t0\t0\t0\t0\t0\t0\t{width}\t{height}\t-1\t"]
    for block, par, line, words in rows:
        out.append(f"4\t1\t{block}\t{par}\t{line}\t0\t0\t0\t1\t1\t-1\t")
        for n, (text, left, top, w, h, conf) in enumerate(words, 1):
            out.append(
                f"5\t1\t{block}\t{par}\t{line}\t{n}\t{left}\t{top}\t{w}\t{h}\t{conf}\t{text}"
            )
    return "\n".join(out) + "\n"


SAMPLE = tsv([
    (1, 1, 1, [("1.", 50, 100, 20, 20, 96), ("Synthetic", 80, 100, 120, 20, 95),
               ("calm", 210, 100, 60, 20, 93), ("question?", 280, 100, 120, 20, 91)]),
    (1, 1, 2, [("2.", 50, 160, 20, 20, 50), ("Fictional", 80, 160, 110, 20, 41),
               ("workload", 200, 160, 110, 20, 55), ("felt", 320, 160, 50, 20, 52)]),
    (1, 1, 3, [("manageable", 80, 190, 140, 20, 40), ("today?", 230, 190, 80, 20, 45)]),
    (1, 2, 1, [("3.", 50, 260, 20, 20, 90), ("Synthetic", 80, 260, 120, 20, 89),
               ("support", 210, 260, 100, 20, 77), ("was", 320, 260, 40, 20, 80),
               ("adequate?", 370, 260, 120, 20, 70)]),
    (2, 1, 1, [("Unlinked", 600, 700, 100, 20, 99), ("footer", 710, 700, 80, 20, -1)]),
])


class TsvParsingTests(unittest.TestCase):
    def test_parses_words_lines_blocks_and_normalized_boxes(self):
        page = parse_tesseract_tsv(SAMPLE, 1, language="eng")
        self.assertEqual((page.pixel_width, page.pixel_height), (1000, 800))
        self.assertEqual(len(page.blocks), 2)
        self.assertEqual(len(page.lines), 5)
        first = page.lines[0]
        self.assertEqual(first.text, "1. Synthetic calm question?")
        self.assertEqual(first.id, "p1-b1-r1-l1")
        self.assertAlmostEqual(first.words[0].box[0], 0.05)
        self.assertAlmostEqual(first.words[0].box[1], 0.125)
        self.assertAlmostEqual(first.box[2], 0.4)
        # Negative TSV confidence is "unavailable", never zero.
        footer = page.lines[-1].words[-1]
        self.assertIsNone(footer.confidence)
        ids = [w.id for w in page.words]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rejects_non_tsv_and_missing_dimensions(self):
        with self.assertRaisesRegex(ValueError, "TSV"):
            parse_tesseract_tsv("1. plain text", 1)
        with self.assertRaisesRegex(ValueError, "dimensions"):
            parse_tesseract_tsv(HEADER + "\n", 1)
        with self.assertRaisesRegex(ValueError, "positive"):
            parse_tesseract_tsv(SAMPLE, 0)

    def test_coordinates_scale_with_zoom(self):
        page = parse_tesseract_tsv(SAMPLE, 1)
        box = page.lines[0].box
        small = to_pixels(box, 500, 400)
        large = to_pixels(box, 1500, 1200)
        for a, b in zip(small, large):
            self.assertAlmostEqual(a * 3, b)

    def test_hit_test_line_without_creating_question(self):
        page = parse_tesseract_tsv(SAMPLE, 1)
        self.assertEqual(page.line_at(0.65, 0.885).text, "Unlinked footer")
        self.assertIsNone(page.line_at(0.99, 0.01))

    def test_positioned_words_group_into_lines(self):
        page = page_from_positioned_words(
            2, [("world", (0.3, 0.1, 0.4, 0.12)), ("Hello", (0.1, 0.1, 0.25, 0.12)),
                ("Next", (0.1, 0.2, 0.2, 0.22))],
            pixel_width=600, pixel_height=800,
        )
        self.assertEqual([l.text for l in page.lines], ["Hello world", "Next"])
        self.assertTrue(all(w.confidence is None for w in page.words))
        plain = page_from_plain_text(1, "1. Text only\n\n2. More")
        self.assertFalse(plain.has_geometry)
        self.assertEqual(len(plain.lines), 2)


class ConfidenceTests(unittest.TestCase):
    def test_thresholds_are_documented_and_categories_separate(self):
        self.assertEqual((OCR_HIGH_THRESHOLD, OCR_REVIEW_THRESHOLD), (85.0, 60.0))
        page = parse_tesseract_tsv(SAMPLE, 1)
        lines = page.lines
        self.assertEqual(aggregate_confidence(lines[0].words).category, "high")
        self.assertEqual(aggregate_confidence(lines[1].words).category, "low")
        # Mean ≥ 60 but below 85 → review.
        self.assertEqual(aggregate_confidence(lines[3].words).category, "review")
        # No OCR scores → explicit UNKNOWN, not 0 % or 100 %.
        unknown = aggregate_confidence(lines[4].words[1:])
        self.assertEqual(unknown.category, "unknown")
        self.assertIsNone(unknown.mean)
        self.assertIn("unknown", unknown.describe().lower())
        self.assertIn("NOT a measure of reliability", PSYCHOMETRIC_NOTICE)

    def test_single_low_word_prevents_high_status(self):
        page = parse_tesseract_tsv(tsv([(1, 1, 1, [
            ("A", 1, 1, 10, 10, 99), ("B", 20, 1, 10, 10, 99),
            ("C", 40, 1, 10, 10, 99), ("D", 60, 1, 10, 10, 99),
            ("E", 80, 1, 10, 10, 30),
        ])]), 1)
        conf = aggregate_confidence(page.words)
        self.assertGreaterEqual(conf.mean, 85)
        self.assertEqual(conf.category, "review")
        self.assertEqual(conf.low_words, ("E",))


class LinkingTests(unittest.TestCase):
    def setUp(self):
        self.page = parse_tesseract_tsv(SAMPLE, 1)
        self.review = parse_scientific_lines(
            [(1, line.text) for line in self.page.lines], "synthetic_scan.pdf",
        )
        self.evidence = link_candidates(self.review, [self.page])

    def test_links_candidates_to_their_lines_including_wrapping(self):
        questions = self.review.instruments[0].questions
        self.assertEqual(len(questions), 3)
        first = self.evidence.regions(question_ref(0, 0))
        self.assertEqual(first[0].line_ids, ("p1-b1-r1-l1",))
        wrapped = self.evidence.regions(question_ref(0, 1))
        self.assertEqual(wrapped[0].line_ids, ("p1-b1-r1-l2", "p1-b1-r1-l3"))
        self.assertEqual(self.evidence.confidence(question_ref(0, 1)).category, "low")
        self.assertEqual(self.evidence.confidence(question_ref(0, 0)).category, "high")
        unlinked = self.evidence.unlinked_lines(1)
        self.assertEqual([l.text for l in unlinked], ["Unlinked footer"])

    def test_hit_test_maps_regions_to_questions_only(self):
        ref, region = self.evidence.hit_test(1, 0.2, 0.135)
        self.assertEqual(ref, question_ref(0, 0))
        self.assertIsNotNone(region)
        self.assertEqual(self.evidence.hit_test(1, 0.65, 0.885), (None, None))

    def test_unmatched_candidate_stays_unlinked(self):
        review = parse_scientific_lines(
            [(1, "1. Completely different synthetic wording here?")], "x.pdf",
        )
        evidence = link_candidates(review, [self.page])
        self.assertEqual(evidence.regions(question_ref(0, 0)), ())
        queue = review_queue(review, evidence)
        self.assertEqual(queue, ((question_ref(0, 0), "unlinked"),))

    def test_merge_split_adjust_and_revert_regions(self):
        ref = question_ref(0, 1)
        region = self.evidence.regions(ref)[0]
        split = split_region(self.evidence, ref, region.id)
        parts = split.regions(ref)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].line_ids, ("p1-b1-r1-l2",))
        self.assertTrue(all(p.origin == "split" for p in parts))
        merged = merge_regions(split, ref, [p.id for p in parts])
        self.assertEqual(len(merged.regions(ref)), 1)
        self.assertEqual(merged.regions(ref)[0].box, region.box)
        moved = set_region_box(merged, ref, merged.regions(ref)[0].id,
                               (0.04, 0.19, 0.5, 0.27))
        self.assertEqual(moved.regions(ref)[0].origin, "manual")
        with self.assertRaisesRegex(ValueError, "positive"):
            set_region_box(merged, ref, merged.regions(ref)[0].id, (0.5, 0.5, 0.5, 0.6))
        restored = revert_links(moved, ref)
        self.assertEqual(restored.regions(ref), self.evidence.regions(ref))
        self.assertEqual(revert_links(moved).links, self.evidence.links)
        # Region IDs stay unique across edits.
        ids = [r.id for _, regions in moved.links for r in regions]
        self.assertEqual(len(ids), len(set(ids)))

    def test_single_line_split_uses_word_gap(self):
        ref = question_ref(0, 0)
        region = self.evidence.regions(ref)[0]
        split = split_region(self.evidence, ref, region.id)
        left, right = split.regions(ref)
        self.assertLess(left.box[2], right.box[2])
        self.assertAlmostEqual(left.box[2], right.box[0])

    def test_manual_link_unlink_and_duplicate_guard(self):
        ref = question_ref(0, 2)
        footer = self.page.lines[-1]
        linked = link_line(self.evidence, ref, 1, footer.id)
        self.assertEqual(len(linked.regions(ref)), 2)
        with self.assertRaisesRegex(ValueError, "already linked"):
            link_line(linked, question_ref(0, 0), 1, footer.id)
        manual = add_manual_region(linked, ref, 1, (0.1, 0.1, 0.2, 0.2))
        self.assertEqual(manual.regions(ref)[-1].origin, "manual")
        cleared = unlink_region(manual, ref, manual.regions(ref)[-1].id)
        self.assertEqual(len(cleared.regions(ref)), 2)
        with self.assertRaises(KeyError):
            link_line(self.evidence, ref, 1, "missing-line")

    def test_structural_assessment_is_categorical_not_percentage(self):
        candidate = self.review.instruments[0].questions[0]
        result = assess_structure(candidate, expected_number=1, linked_regions=1)
        self.assertIn(result.category, {"consistent", "needs_review", "unresolved"})
        self.assertNotIn("%", result.label)
        missing = assess_structure(candidate, expected_number=4, linked_regions=0)
        self.assertEqual(missing.category, "unresolved")
        self.assertTrue(any("Numbering" in r for r in missing.reasons))

    def test_box_validation(self):
        self.assertEqual(normalize_box((-1, 0, 2, 0.5)), (0.0, 0.0, 1.0, 0.5))
        with self.assertRaises(ValueError):
            normalize_box((0, 0, float("nan"), 1))


if __name__ == "__main__":
    unittest.main()
