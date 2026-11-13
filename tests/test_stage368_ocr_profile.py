"""Stage 36.8 (issue #62): the time of a reading, stage by stage, and the
two measured speed-ups that keep OCR input pixel-identical.

- ocr_profile: stages add up per reading; the active profile reaches the
  worker thread (asyncio.to_thread copies it); without one nothing is
  recorded; ``SRA_OCR_PROFILE`` writes the result; a stalled event loop is
  measured.
- PNG pages are encoded at zlib level 3 instead of ``optimize=True``: the
  decoded pixels are identical, so the engine reads exactly the same image
  (and with a real engine the same TSV).
- The real import of the scanned 52-item Latvian table, profiled: every
  OCR stage is recorded once per page, the page shown first is drawn in the
  worker, and the interface's event loop is never held for long.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import ocr_profile  # noqa: E402
from visual_survey_review import encode_png  # noqa: E402


def tesseract_with(language: str) -> bool:
    try:
        from ocr_runtime import ocr_readiness

        return language in ocr_readiness().languages
    except Exception:
        return False


class ProfileTests(unittest.TestCase):
    def test_stages_add_up(self):
        profile = ocr_profile.Profile("test")
        with ocr_profile.activate(profile):
            for _ in range(2):
                with ocr_profile.stage("page_rendering"):
                    time.sleep(0.01)
            ocr_profile.mark("page 1: read")
        result = profile.result()
        self.assertEqual(result["stages"]["page_rendering"]["calls"], 2)
        self.assertGreaterEqual(result["stages"]["page_rendering"]["seconds"], 0.02)
        self.assertEqual(result["stages"]["ocr_execution"]["calls"], 0)
        self.assertEqual(result["events"][0][1], "page 1: read")
        self.assertEqual(list(result["stages"]), list(ocr_profile.STAGES))
        self.assertEqual(len(ocr_profile.STAGES), 12)

    def test_without_a_profile_nothing_is_recorded(self):
        self.assertIsNone(ocr_profile.current())
        with ocr_profile.stage("ocr_execution"):
            pass
        ocr_profile.mark("ignored")

    def test_the_profile_reaches_the_worker_thread(self):
        profile = ocr_profile.Profile()

        def work():
            with ocr_profile.stage("tsv_parsing"):
                return ocr_profile.current()

        async def main():
            with ocr_profile.activate(profile):
                return await asyncio.to_thread(work)

        self.assertIs(asyncio.run(main()), profile)
        self.assertEqual(profile.result()["stages"]["tsv_parsing"]["calls"], 1)

    def test_written_only_when_asked(self):
        profile = ocr_profile.Profile("x")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ocr_profile.ENVIRONMENT, None)
            self.assertIsNone(profile.write())
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.dict(os.environ, {ocr_profile.ENVIRONMENT: folder}):
                first, second = profile.write(), profile.write()
            self.assertEqual((first.name, second.name), ("ocr-profile-01.json", "ocr-profile-02.json"))
            self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["label"], "x")

    def test_a_stalled_event_loop_is_measured(self):
        profile = ocr_profile.Profile()

        async def main():
            stop = asyncio.Event()
            watcher = asyncio.create_task(ocr_profile.watch_event_loop(profile, stop))
            await asyncio.sleep(0.12)
            time.sleep(0.4)                     # the loop is held
            await asyncio.sleep(0.12)
            stop.set()
            await watcher

        asyncio.run(main())
        self.assertGreaterEqual(profile.loop_stall_seconds, 0.3)

    def test_process_measurements_never_fail(self):
        self.assertIsInstance(ocr_profile.process_io(), dict)
        peak = ocr_profile.peak_memory()
        self.assertTrue(peak is None or peak > 0)


class FastPngTests(unittest.TestCase):
    def page(self) -> Image.Image:
        rng = np.random.default_rng(5)
        pixels = np.full((420, 300, 3), 255, np.uint8)
        pixels[40:60, 20:280] = 0                                     # a rule
        pixels[100:380, 30:270] = rng.integers(0, 256, (280, 240, 3), dtype=np.uint8)
        return Image.fromarray(pixels)

    def test_level_three_keeps_every_pixel(self):
        image = self.page()
        slow = io.BytesIO()
        image.save(slow, "PNG", optimize=True)
        fast = encode_png(image)
        decoded = [np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
                   for data in (slow.getvalue(), fast)]
        self.assertTrue(np.array_equal(*decoded))

    def test_the_size_limit_falls_back_to_the_smaller_encoding(self):
        image = self.page()
        data = encode_png(image, limit=1)                             # over any limit
        slow = io.BytesIO()
        image.save(slow, "PNG", optimize=True)
        self.assertLessEqual(len(data), max(len(slow.getvalue()), len(encode_png(image))))
        self.assertTrue(np.array_equal(np.asarray(Image.open(io.BytesIO(data)).convert("RGB")),
                                       np.asarray(image)))

    @unittest.skipUnless(tesseract_with("lav"), "local OCR with Latvian is not installed")
    def test_the_engine_reads_the_same_words(self):
        from stage36_fixtures import generator
        from visual_survey_review import _render_pdf_page, recognize_page_layout

        with tempfile.TemporaryDirectory() as folder:
            pdf = generator().create_lv_table_scan_pdf(Path(folder))
            png, dpi = _render_pdf_page(pdf.read_bytes(), 1, scale=2.0, max_width=1800)
        slow = io.BytesIO()
        Image.open(io.BytesIO(png)).save(slow, "PNG", optimize=True)
        words = [[(w.text, w.box) for w in recognize_page_layout(data, "lav", dpi=dpi).words]
                 for data in (png, slow.getvalue())]
        self.assertEqual(words[0], words[1])


@unittest.skipUnless(tesseract_with("lav"), "local OCR with Latvian is not installed")
class ProfiledScanImportTests(unittest.TestCase):
    def test_the_52_item_scan_is_profiled_stage_by_stage(self):
        import stage36_fixtures as fx
        from test_stage36_import_ui import Base

        case = Base("run")
        case.setUp()
        try:
            ws, page = case.ws, case.page
            case.open(case.local(fx.SCAN_TABLE_LV), ws)
            ws.choose("imp-ocr-language", "lav")
            ws.click("imp-ocr-run")
            self.assertEqual(case.state(ws)[0], "review")
            profile = page.last_profile
        finally:
            case.tearDown()
            case.doCleanups()
        stages = profile["stages"]
        print("\n[ocr profile] " + ", ".join(
            f"{name} {v['seconds']:.2f}s/{v['calls']}" for name, v in stages.items())
            + f"; total {profile['total_seconds']:.2f}s, loop stall "
              f"{profile['event_loop_max_stall_seconds']:.2f}s, renders {profile['renders']}")
        self.assertEqual(profile["facts"]["items"], 52)
        self.assertEqual(profile["facts"]["ocr_pages"], [1, 2])
        for name in ("image_preprocessing", "ocr_initialization", "ocr_execution", "tsv_parsing"):
            self.assertEqual(stages[name]["calls"], 2, name)
        # Two pages for the engine, then the page shown first (in the worker).
        self.assertEqual(stages["page_rendering"]["calls"], 3)
        for name in ("source_open", "pdf_loading", "table_reconstruction",
                     "question_reconstruction", "confidence_assessment", "review_model",
                     "ui_update"):
            self.assertGreater(stages[name]["calls"], 0, name)
        self.assertEqual(len(profile["engine_runs"]), 2)
        accounted = sum(v["seconds"] for v in stages.values())
        self.assertLessEqual(accounted, profile["total_seconds"] + 0.05)
        self.assertLess(profile["event_loop_max_stall_seconds"], 3.0,
                        "the window could not react for seconds while reading")



class ReadingIndicatorTests(unittest.TestCase):
    """While reading, the status line shows how many OCR pages are read and
    never runs an endless animation, which is redrawn on every frame."""

    def test_the_ring_counts_pages_and_never_spins(self):
        import flet as ft
        from test_stage36_import_ui import Base

        case = Base("run")
        case.setUp()
        try:
            page = case.page
            page.busy, page.progress_done = True, None
            before = page._reading_indicator()
            with mock.patch.object(page.app, "render"):
                page._show_progress("Reading page 1 with local OCR (1 of 2)…")
                first = page._reading_indicator()
                page._show_progress("Reading page 2 with local OCR (2 of 2)…")
                second = page._reading_indicator()
        finally:
            case.tearDown()
            case.doCleanups()
        self.assertIsInstance(before, ft.Icon)       # a text reading: no ring at all
        self.assertIsInstance(first, ft.ProgressRing)
        self.assertEqual(first.value, 0.0)
        self.assertEqual(second.value, 0.5)


if __name__ == "__main__":
    unittest.main()
