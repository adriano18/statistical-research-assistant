"""Stage 36.7: table rules whitened before local OCR (ocr_rules.py).

Synthetic images only: rules, bars and letter-like blocks drawn with Pillow.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ocr_rules import ruling_line_mask, without_ruling_lines  # noqa: E402

WIDTH, HEIGHT = 1190, 1684        # an A4 page rendered at 144 dpi


def page(draw_on) -> Image.Image:
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw_on(ImageDraw.Draw(image))
    return image


def png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def grey(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(BytesIO(data)).convert("L"))


def blocks(draw, top: int) -> None:
    """Letter-like blocks (no run of ink is a fifth of the page long)."""
    for k in range(30):
        x = 120 + k * 32
        draw.rectangle((x, top, x + 18, top + 20), fill=0)


class RuleRemovalTests(unittest.TestCase):
    def test_a_page_without_rules_is_returned_unchanged(self):
        source = png(page(lambda d: blocks(d, 400)))
        self.assertIs(without_ruling_lines(source, dpi=144), source)

    def test_a_slightly_rotated_hairline_rule_is_whitened_and_the_text_kept(self):
        def draw(d):
            blocks(d, 400)
            blocks(d, 440)
            d.line((105, 431, 1150, 431), fill=85, width=1)
        rotated = page(draw).rotate(0.35, resample=Image.BICUBIC, fillcolor=255)
        before = np.asarray(rotated)
        after = grey(without_ruling_lines(png(rotated), dpi=144))
        # Nothing as dark as the rule is left between the two rows of blocks.
        gap = after[426:437, 100:1160]
        rule_ink = (before[426:437, 100:1160] < 170) & (after[426:437, 100:1160] < 170)
        self.assertLess(int(rule_ink.sum()), 40, f"left of the rule: {int((gap < 170).sum())} px")
        # The blocks keep their ink (at most the rows touching the rule change).
        for top in (403, 447):
            self.assertEqual(int((after[top:top + 12, 100:1100] < 128).sum()),
                             int((before[top:top + 12, 100:1100] < 128).sum()))

    def test_the_whole_rule_goes_including_its_ends(self):
        def draw(d):
            d.line((60, 800, 1130, 806), fill=0, width=2)    # rotated by about 0.3°
        mask = ruling_line_mask(np.asarray(page(draw)), dpi=144)
        columns = np.flatnonzero(mask.any(axis=0))
        self.assertLessEqual(columns.min(), 61)
        self.assertGreaterEqual(columns.max(), 1129)

    def test_a_vertical_rule_is_whitened_too(self):
        def draw(d):
            blocks(d, 600)
            d.line((150, 200, 151, 1500), fill=0, width=2)
        before = np.asarray(page(draw))
        after = grey(without_ruling_lines(png(page(draw)), dpi=144))
        for rows in (slice(200, 595), slice(625, 1500)):      # above and below the blocks
            self.assertEqual(int((after[rows, 145:157] < 128).sum()), 0)
        # The block next to the rule (x = 152-170) keeps its ink.
        self.assertEqual(int((after[600:621, 153:171] < 128).sum()),
                         int((before[600:621, 153:171] < 128).sum()))

    def test_a_filled_bar_a_short_rule_and_light_lines_stay(self):
        def draw(d):
            d.rectangle((100, 300, 1100, 330), fill=0)       # a header bar, 31 px thick
            d.line((100, 600, 300, 600), fill=0, width=2)    # a short rule (17 % of the width)
            d.line((100, 900, 1100, 900), fill="#CCCCCC")    # lighter than ink
        image = page(draw)
        self.assertFalse(ruling_line_mask(np.asarray(image), dpi=144).any())
        source = png(image)
        self.assertIs(without_ruling_lines(source, dpi=144), source)

    def test_letters_touching_a_rule_keep_what_is_away_from_it(self):
        def draw(d):
            d.line((100, 1000, 1100, 1000), fill=0, width=2)
            for k in range(10):
                x = 150 + k * 80
                d.rectangle((x, 978, x + 10, 1001), fill=0)   # stems standing on the rule
        before = np.asarray(page(draw))
        after = grey(without_ruling_lines(png(page(draw)), dpi=144))
        self.assertEqual(int((after[978:996] < 128).sum()), int((before[978:996] < 128).sum()))
        self.assertEqual(int((after[999:1001, 100:1100] < 128).sum()), 0)

    def test_an_unreadable_image_is_returned_as_it_is(self):
        self.assertEqual(without_ruling_lines(b"not a png"), b"not a png")


if __name__ == "__main__":
    unittest.main()
