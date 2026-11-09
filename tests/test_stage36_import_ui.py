"""Stage 36.5 UI: the scientific-import review wizard (spec §10, §14, §15).

1. Source / version: every form of a document is its own card (title,
   items, documented answer options with their evidence, pages); the
   researcher chooses the form, nothing is chosen silently.
2. One processing status: source loaded, scanned pages detected (OCR
   offered with its language), recognizing, candidates found, needs
   review, ready to create the draft, or an error with what to do next.
3. Autosave and resume: ``<data>/import_sessions/<sha256>.json``, written
   atomically after every change, restored only for the same bytes,
   never confirming anything the researcher did not confirm.
4. Keys on the items step (F8, Shift+F8, F9, Alt+↓ / Alt+↑) through the
   shell's keyboard handler.
5. 200 items: a page of rows at a time, stable keys, the filter, the
   editor under its row, and the measured build time.

Plus the interaction counts of docs/STAGE36_UX_AUDIT.md. Synthetic,
invented documents only (tests/fixtures/stage36, tests/synthetic_documents).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from workspace_harness import Workspace  # noqa: E402

GENERAL = "INVENTORY FORM: GENERAL"
SITUATIONAL = "INVENTORY FORM: SITUATIONAL"
GENERAL_OPTIONS = "Hardly ever / Now and then / Fairly often / Very often"
SITUATIONAL_OPTIONS = "Not at all / Slightly / Moderately / Strongly"


def texts_in(ws, data: str) -> str:
    control = ws.find(data)
    return " ".join(c.value for c in ws.controls(control)
                    if isinstance(c, ft.Text) and isinstance(c.value, str))


def has(ws, data: str) -> bool:
    """A control with exactly this id is on screen (not just the prefix)."""
    return any(getattr(c, "data", None) == data for c in ws.controls())


def rows(ws) -> list[int]:
    """Item rows on screen, in order."""
    return [int(c.data[len("imp-item-"):]) for c in ws.controls()
            if isinstance(getattr(c, "data", None), str) and c.data.startswith("imp-item-")
            and c.data[len("imp-item-"):].isdigit()]


def tesseract_with(*languages: str) -> bool:
    try:
        from ocr_runtime import ocr_readiness
        from visual_survey_review import tesseract_available

        return tesseract_available() and set(languages) <= set(ocr_readiness().languages)
    except Exception:
        return False


class Base(unittest.TestCase):
    language = "en"

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.ws = self.workspace()
        self.page = self.ws.app.pages["import"]
        self.ws.app.navigate("import")

    def workspace(self, cls=Workspace) -> Workspace:
        ws = cls(language=self.language, root=self.root)
        self.addCleanup(ws.close)
        return ws

    def local(self, fixture: str) -> Path:
        """A synthetic fixture copied where a researcher keeps documents."""
        documents = self.root / "documents"
        documents.mkdir(exist_ok=True)
        target = documents / fixture
        if not target.exists():
            target.write_bytes(fx.fixture(fixture).read_bytes())
        return target

    def open(self, path: Path, ws=None):
        ws = ws or self.ws
        page = ws.app.pages["import"]
        ws.run(page.open_bytes(path.read_bytes(), path.name, path=str(path)))
        return page

    def state(self, ws=None) -> tuple[str, str, str]:
        """(state, title, all lines) of the one processing status."""
        found = (ws or self.ws).app.pages["import"].processing_state()
        return found[0], found[1], " ".join(line for _, line in found[2])

    def sessions(self) -> list[Path]:
        return sorted((self.root / "import_sessions").glob("*"))


# ======================================================== 1. source / version
class FormCardTests(Base):
    def setUp(self):
        super().setUp()
        self.docx = self.local(fx.DOCX_UNNUMBERED)
        self.open(self.docx)

    def test_each_form_is_a_card_and_none_is_chosen_silently(self):
        ws, page = self.ws, self.page
        self.assertIsNone(page.chosen, "two forms: the researcher chooses")
        first, second = texts_in(ws, "imp-instrument-0"), texts_in(ws, "imp-instrument-1")
        self.assertIn(GENERAL, first)
        self.assertIn(SITUATIONAL, second)
        for text in (first, second):
            self.assertIn("60 items", text)
            self.assertIn("page 1", text)
            self.assertIn("not confirmed yet", text)
        self.assertIn(f"Response options: {GENERAL_OPTIONS}", first)
        self.assertIn("header row of the table", first)
        self.assertIn(f"Response options: {SITUATIONAL_OPTIONS}", second)
        self.assertIn("instruction before the table", second)
        for index in (0, 1):
            button = ws.find(f"imp-instrument-use-{index}")
            self.assertEqual(button.content, "Review this form")
        self.assertFalse(ws.find_all("imp-instrument-chosen-"))
        # Nothing later than step 1 opens before the choice.
        for step in ("scale", "items", "confirm"):
            self.assertTrue(ws.find(f"imp-step-{step}").disabled, step)
        self.assertTrue(ws.find("imp-next").disabled)
        self.assertIn("Choose which form", ws.find("imp-create-draft").tooltip)
        with self.assertRaises(ValueError):
            page.create_draft()
        self.assertEqual(self.state()[0], "found")

    def test_the_chosen_form_is_reviewed_with_its_own_options(self):
        ws, page = self.ws, self.page
        ws.click("imp-instrument-use-1")
        self.assertEqual((page.chosen, page.step), (1, "scale"))
        self.assertEqual(page.session.instrument.title, SITUATIONAL)
        scheme = page.session.instrument.schemes[0]
        self.assertEqual(" / ".join(scheme.labels), SITUATIONAL_OPTIONS)
        self.assertIn(SITUATIONAL_OPTIONS, texts_in(ws, f"scale-{scheme.id}"))
        self.assertFalse(ws.has_text("Hardly ever"), "the other form's options are not shown")
        ws.click("imp-step-items")
        self.assertIn("60 items", texts_in(ws, "imp-counts"))
        self.assertEqual(len(rows(ws)), 60)
        self.assertIn("situational case 1 ", texts_in(ws, "imp-item-0"))
        ws.click("imp-step-source")
        self.assertIn("Chosen for review", texts_in(ws, "imp-instrument-1"))
        self.assertEqual(ws.find("imp-instrument-use-1").content, "Continue with this form")
        self.assertEqual(ws.find("imp-instrument-use-0").content, "Review this form")

    def test_switching_back_keeps_each_forms_own_review(self):
        ws, page = self.ws, self.page
        ws.click("imp-instrument-use-1")
        ws.click("imp-step-items")
        ws.click("imp-item-3")
        ws.check("imp-item-reviewed")
        ws.click("imp-step-confirm")
        ws.check("imp-check-version")
        ws.click("imp-step-source")
        ws.click("imp-instrument-use-0")                # the other form: its own review
        self.assertEqual(page.session.instrument.title, GENERAL)
        self.assertEqual(page.session.reviewed, set())
        self.assertFalse(any(page.session.checks.values()), "no confirmation carries over")
        ws.click("imp-step-source")
        ws.click("imp-instrument-use-1")                # back: as the researcher left it
        self.assertEqual(page.session.reviewed, {3})
        self.assertTrue(page.session.checks["version"])
        self.assertFalse(page.session.checks["rights"])

    def test_the_draft_holds_the_chosen_form_only(self):
        ws, page = self.ws, self.page
        ws.click("imp-instrument-use-1")
        scheme = page.session.instrument.schemes[0]
        ws.check(f"scale-{scheme.id}-structure")
        ws.check(f"scale-{scheme.id}-numeric")
        ws.click(f"scale-{scheme.id}-apply")
        ws.click("imp-step-confirm")
        for key in ("version", "rights", "items"):
            ws.check(f"imp-check-{key}")
        self.assertEqual(self.state()[0], "ready")
        ws.click("imp-create-draft")
        builder = ws.app.pages["questionnaires"]
        self.assertEqual(ws.app.route, "questionnaires")
        self.assertEqual(len(builder.draft), 60)
        self.assertEqual(builder.title, SITUATIONAL)
        self.assertTrue(all("situational" in q["prompt"] for q in builder.draft))
        self.assertEqual(list(builder.draft[0]["value_labels"].values()),
                         SITUATIONAL_OPTIONS.split(" / "))


class SingleFormTests(Base):
    def test_a_single_form_is_the_form_without_a_choice(self):
        from synthetic_documents import numbered_items_pdf

        ws = self.ws
        ws.run(self.page.open_bytes(numbered_items_pdf(30), "synthetic_30.pdf"))
        self.assertEqual(self.page.chosen, 0)
        self.assertIn("The only form found in this document.", texts_in(ws, "imp-instrument-0"))
        self.assertFalse(ws.find_all("imp-instrument-use-"))
        self.assertFalse(ws.find("imp-step-scale").disabled)


class FormCardLatvianTests(FormCardTests):
    language = "lv"

    def test_each_form_is_a_card_and_none_is_chosen_silently(self):
        ws = self.ws
        self.assertIsNone(self.page.chosen)
        second = texts_in(ws, "imp-instrument-1")
        self.assertIn(f"Atbilžu varianti: {SITUATIONAL_OPTIONS}", second)
        self.assertIn("instrukcija pirms tabulas", second)
        self.assertIn("60 jautājumi", second)
        self.assertEqual(ws.find("imp-instrument-use-1").content, "Pārbaudīt šo formu")
        self.assertEqual(self.state()[1], "Atrasti kandidāti")
        self.assertIn("Izvēlieties, kuru formu", ws.find("imp-create-draft").tooltip)

    def test_the_chosen_form_is_reviewed_with_its_own_options(self):
        ws = self.ws
        ws.click("imp-instrument-use-1")
        ws.click("imp-step-source")
        self.assertIn("Izvēlēta pārbaudei", texts_in(ws, "imp-instrument-1"))


# =============================================== 2. one processing status
class StatusTests(Base):
    def test_candidates_found_then_needs_review_then_ready(self):
        ws, page = self.ws, self.page
        self.open(self.local(fx.DOCX_UNNUMBERED))
        state, title, lines = self.state()
        self.assertEqual((state, title), ("found", "Candidates found"))
        self.assertIn("120 candidate items in 2 forms (60, 60).", lines)
        self.assertIn("none is chosen for you", lines)
        ws.click("imp-instrument-use-0")
        state, title, lines = self.state()
        self.assertEqual((state, title), ("review", "Needs review"))
        self.assertIn(f"{GENERAL} — 60 candidate items · 0 need attention", lines)
        self.assertIn("Next: Confirm the shared response scale (step 2)", lines)
        scheme = page.session.instrument.schemes[0]
        ws.check(f"scale-{scheme.id}-structure")
        ws.check(f"scale-{scheme.id}-numeric")
        ws.click(f"scale-{scheme.id}-apply")
        self.assertIn("Next: Confirm the instrument version and wording (step 4).",
                      self.state()[2])
        ws.click("imp-step-confirm")
        for key in ("version", "rights", "items"):
            ws.check(f"imp-check-{key}")
        state, title, lines = self.state()
        self.assertEqual((state, title), ("ready", "Ready to create the draft"))
        self.assertIn("every required confirmation is given", lines)
        self.assertFalse(ws.find("imp-create-draft").disabled)
        self.assertEqual(ws.find("imp-status-title").value, "Ready to create the draft")

    def test_the_text_is_read_with_the_source_loaded_state(self):
        import import_session

        from synthetic_documents import numbered_items_pdf

        ws, page = self.ws, self.page
        entered, release = threading.Event(), threading.Event()
        real = import_session.read_scientific_document

        def slow(path):
            entered.set()
            release.wait(10)
            return real(path)

        async def journey():
            with mock.patch("import_session.read_scientific_document", side_effect=slow):
                task = asyncio.create_task(page.open_bytes(numbered_items_pdf(30),
                                                           "synthetic_30.pdf"))
                while not entered.is_set():
                    await asyncio.sleep(0.02)
                shown = self.state(), ws.find("imp-progress").value
                release.set()
                await task
                return shown

        (state, title, lines), progress = ws.run(journey())
        self.assertEqual((state, title), ("loaded", "Source loaded"))
        self.assertEqual(progress, "Reading synthetic_30.pdf on this computer…")
        self.assertEqual(self.state()[0], "review")

    def test_a_scan_is_detected_and_ocr_is_offered_with_its_language(self):
        ws, page = self.ws, self.page
        with mock.patch.object(type(page), "_probe_ocr", staticmethod(
                lambda: (True, ("eng", "lav", "rus")))):
            self.open(self.local(fx.SCAN_TABLE_LV))
        state, title, lines = self.state()
        self.assertEqual((state, title), ("scan", "Scanned pages detected"))
        self.assertIn("Pages 1 and 2: no text layer", lines)
        self.assertIsNone(page.session.instrument, "nothing is read before the choice")
        language = ws.find("imp-ocr-language", ft.Dropdown)
        self.assertEqual(language.value, "eng", "the interface language is proposed")
        self.assertEqual([o.key for o in language.options],
                         ["eng", "lav", "rus", "lav+eng", "rus+eng", "lav+rus+eng"])
        self.assertEqual(ws.find("imp-ocr-run").content, "Read with local OCR")
        self.assertTrue(ws.find_all("imp-scan-pending"))
        self.assertFalse(ws.find_all("imp-steps"), "no wizard before there are items")
        self.assertFalse(has(ws, "imp-ocr"), "one OCR offer at a time")

    def test_recognizing_shows_progress_and_cancel_returns_to_the_offer(self):
        from ocr_runtime import OCRCancelled

        ws, page = self.ws, self.page
        started = threading.Event()
        seen = []

        def slow_ocr(source, filename, pages, language, *, cancel=None, progress=None, **kw):
            seen.append(language)
            if progress is not None:
                progress(0, len(pages))
            started.set()
            while not cancel.is_set():
                cancel.wait(0.05)
            raise OCRCancelled()

        with mock.patch.object(type(page), "_probe_ocr", staticmethod(lambda: (True, ()))):
            self.open(self.local(fx.SCAN_TABLE_LV))
        ws.choose("imp-ocr-language", "lav")

        async def journey():
            with mock.patch("visual_survey_review.ocr_scientific_pdf", side_effect=slow_ocr), \
                    mock.patch("visual_survey_review.tesseract_available", return_value=True):
                task = asyncio.create_task(page._read_with_ocr())
                while not started.is_set():
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.1)
                shown = self.state(), ws.find("imp-progress").value, ws.find("imp-cancel")
                page.cancel_reading()
                await task
                return shown

        (state, title, _), progress, cancel = ws.run(journey())
        self.assertEqual((state, title), ("recognizing", "Recognizing the scanned pages"))
        self.assertIn("Reading page 1 with local OCR (1 of 2)", progress)
        self.assertIsNotNone(cancel)
        self.assertEqual(seen, ["lav"], "OCR runs in the language the researcher chose")
        state, title, lines = self.state()
        self.assertEqual(state, "scan")
        self.assertIn("reading with local OCR was cancelled", lines)
        self.assertTrue(ws.find_all("imp-ocr-run"), "it can be read again")

    def test_errors_say_why_and_what_to_do_next(self):
        ws, page = self.ws, self.page
        ws.run(page.open_bytes(b"fictional notes", "notes.rtf"))
        state, title, lines = self.state()
        self.assertEqual((state, title), ("error", "Not imported"))
        self.assertIn("is not a PDF or Word document", lines)
        self.assertTrue(ws.find_all("imp-choose-other"))
        # A failure while a document is under review explains its counts.
        self.open(self.local(fx.DOCX_UNNUMBERED))
        ws.run(page.open_bytes(b"%PDF-1.4 fictional broken bytes", "broken.pdf"))
        state, title, lines = self.state()
        self.assertEqual(state, "error")
        self.assertIn("broken.pdf could not be read", lines)
        self.assertIn(f"The document under review, {fx.DOCX_UNNUMBERED} (120 items), is "
                      "unchanged.", lines)
        self.assertEqual(page.session.filename, fx.DOCX_UNNUMBERED)
        self.assertNotIn("not recognised", " ".join(ws.texts()).lower())
        ws.click("imp-instrument-use-0")                 # working on clears the error
        self.assertEqual(self.state()[0], "review")

    def test_no_items_is_an_explained_state_with_a_next_step(self):
        from synthetic_documents import references_only_pdf

        ws = self.ws
        ws.run(self.page.open_bytes(references_only_pdf(), "fictional_reading_list.pdf"))
        state, title, lines = self.state()
        self.assertEqual((state, title), ("error", "No questionnaire items found"))
        self.assertIn("No questionnaire items were found in fictional_reading_list.pdf", lines)
        self.assertIn("Next: choose another document", lines)
        self.assertNotIn("candidate items", lines)


class StatusRussianTests(Base):
    language = "ru"

    def test_states_and_facts_in_russian(self):
        ws = self.ws
        with mock.patch.object(type(self.page), "_probe_ocr", staticmethod(lambda: (True, ()))):
            self.open(self.local(fx.SCAN_TABLE_LV))
        state, title, lines = self.state()
        self.assertEqual(title, "Обнаружены отсканированные страницы")
        self.assertIn("Страницы 1 и 2: нет текстового слоя", lines)
        self.assertEqual(ws.find("imp-ocr-language", ft.Dropdown).value, "rus")
        self.open(self.local(fx.DOCX_UNNUMBERED))
        state, title, lines = self.state()
        self.assertEqual(title, "Найдены кандидаты")
        self.assertIn("Пунктов-кандидатов: 120; форм: 2 (60, 60).", lines)
        self.assertNotIn("Found", lines)


# ================================================== 3. autosave and resume
class ReviewStoreTests(unittest.TestCase):
    """import_review: one JSON file per document, nothing trusted blindly."""

    def setUp(self):
        from import_review import ReviewStore

        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = ReviewStore(Path(self.folder.name) / "import_sessions")

    def record(self, sha="a" * 64):
        from import_review import FormReview, ReviewRecord

        form = FormReview("f" * 64, "Fictional form", 10, (2, 3), {"version": True},
                          ({"do": "wording", "index": 2, "prompt": "Fictional wording."},))
        return ReviewRecord(sha, "fictional.pdf", "/fictional/fictional.pdf", "lav", (), 0,
                            "items", 3, {0: form})

    def test_a_review_round_trips_and_is_written_atomically(self):
        record = self.record()
        self.assertTrue(self.store.save(record))
        files = sorted(p.name for p in self.store.folder.iterdir())
        self.assertEqual(files, [f"{'a' * 64}.json"], "no temporary file is left behind")
        loaded = self.store.load("a" * 64)
        self.assertEqual(loaded.to_json(), record.to_json())
        self.assertEqual((loaded.checked, loaded.total), (2, 10))
        self.assertTrue(loaded.saved_at)
        self.store.remove("a" * 64)
        self.assertIsNone(self.store.load("a" * 64))

    def test_foreign_corrupt_or_tampered_files_restore_nothing(self):
        folder = self.store.folder
        folder.mkdir(parents=True)
        self.assertIsNone(self.store.load("../outside"))
        (folder / f"{'b' * 64}.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(self.store.load("b" * 64))
        moved = self.record("c" * 64).to_json()
        (folder / f"{'d' * 64}.json").write_text(json.dumps(moved), encoding="utf-8")
        self.assertIsNone(self.store.load("d" * 64), "a review of other bytes")
        older = dict(moved, version=0)
        (folder / f"{'c' * 64}.json").write_text(json.dumps(older), encoding="utf-8")
        self.assertIsNone(self.store.load("c" * 64), "another session format")
        tampered = dict(moved, chosen=True, selected=False, ocr_language="eng; rm -rf",
                        forms={"0": dict(moved["forms"]["0"], reviewed=[True, 2, 99],
                                         checks={"version": 1, "rights": True, "other": True},
                                         actions=[{"do": "scale", "scheme": "s1",
                                                   "labels": ["a"], "codes": [1]},
                                                  {"do": "approve_scoring"}])})
        (folder / f"{'c' * 64}.json").write_text(json.dumps(tampered), encoding="utf-8")
        loaded = self.store.load("c" * 64)
        self.assertEqual((loaded.chosen, loaded.selected, loaded.ocr_language), (None, None, None))
        form = loaded.forms[0]
        self.assertEqual((form.reviewed, form.checks, form.actions), ((2,), {"rights": True}, ()))
        self.assertEqual(self.store.records()[0].sha256, "c" * 64)

    def test_only_a_pdf_without_any_text_layer_is_a_scan(self):
        from import_review import scanned_pages
        from synthetic_documents import numbered_items_pdf, psq_like_pdf

        self.assertEqual(scanned_pages(fx.fixture(fx.SCAN_TABLE_LV).read_bytes()), (1, 2))
        self.assertEqual(scanned_pages(numbered_items_pdf(5)), ())
        self.assertEqual(scanned_pages(psq_like_pdf()), (), "its text tells the OCR language")
        self.assertEqual(scanned_pages(b"%PDF-1.4 fictional broken bytes"), ())


class AutosaveFlow(Base):
    def setUp(self):
        super().setUp()
        self.docx = self.local(fx.DOCX_UNNUMBERED)
        self.sha = hashlib.sha256(self.docx.read_bytes()).hexdigest()

    def saved(self) -> dict:
        return json.loads((self.root / "import_sessions" / f"{self.sha}.json")
                          .read_text(encoding="utf-8"))

    def review(self, ws=None):
        """Form 2: item 8 checked, item 5 reworded, the scale's structure
        confirmed (not its codes), "rights" confirmed, item 12 selected."""
        ws = ws or self.ws
        page = self.open(self.docx, ws)
        ws.click("imp-instrument-use-1")
        scheme = page.session.instrument.schemes[0]
        ws.check(f"scale-{scheme.id}-structure")
        ws.click(f"scale-{scheme.id}-apply")
        ws.click("imp-step-confirm")
        ws.check("imp-check-rights")
        ws.click("imp-step-items")
        ws.click("imp-item-4")
        ws.type("imp-wording", "In this invented situational case 5 I would compare imaginary "
                               "choices calmly (corrected).")
        ws.click("imp-wording-apply")
        ws.click("imp-item-7")
        ws.check("imp-item-reviewed")
        ws.click("imp-item-12")
        return page


class AutosaveTests(AutosaveFlow):
    def test_every_change_is_saved_atomically_beside_the_surveys(self):
        ws, page = self.ws, self.page
        self.open(self.docx)
        self.assertEqual(self.sessions(), [], "opening alone is not a review")
        ws.click("imp-instrument-use-1")
        self.assertEqual(self.sessions(), [self.root / "import_sessions" / f"{self.sha}.json"])
        self.assertEqual(self.saved()["chosen"], 1)
        self.assertEqual(self.saved()["step"], "scale")
        ws.click("imp-step-items")
        ws.click("imp-item-7")
        self.assertEqual((self.saved()["step"], self.saved()["selected"]), ("items", 7))
        ws.check("imp-item-reviewed")
        self.assertEqual(self.saved()["forms"]["1"]["reviewed"], [7])
        record = self.saved()
        self.assertEqual(record["sha256"], self.sha)
        self.assertEqual(record["path"], str(self.docx))
        self.assertEqual(record["file"], fx.DOCX_UNNUMBERED)
        self.assertEqual(record["forms"]["1"]["title"], SITUATIONAL)
        self.assertEqual(record["forms"]["1"]["count"], 60)
        self.assertEqual(record["forms"]["1"]["checks"], {}, "nothing confirmed yet")
        self.assertEqual([p.suffix for p in self.sessions()], [".json"], "no temporary file left")
        self.assertEqual(self.sessions()[0].parent.parent, ws.app.survey_root.parent)

    def test_the_same_document_opened_again_comes_back_as_left(self):
        ws = self.ws
        page = self.review()
        from synthetic_documents import numbered_items_pdf

        ws.run(page.open_bytes(numbered_items_pdf(30), "synthetic_30.pdf"))
        self.assertEqual(page.session.filename, "synthetic_30.pdf")
        with mock.patch.object(ws.app, "reveal") as reveal:
            self.open(self.docx)
        self.assert_restored(ws, page)
        reveal.assert_called_with("imp-row-12")

    def assert_restored(self, ws, page):
        s = page.session
        self.assertEqual((page.chosen, page.step, page.selected), (1, "items", 12))
        self.assertEqual(s.instrument.title, SITUATIONAL)
        self.assertEqual(s.reviewed, {7})
        self.assertTrue(s.instrument.questions[4].question["prompt"].endswith("(corrected)."))
        scheme = s.instrument.schemes[0]
        self.assertEqual((scheme.structure_confirmed, scheme.codes_confirmed,
                          scheme.reverse_confirmed), (True, False, False))
        self.assertEqual(s.checks, {"version": False, "rights": True, "items": False})
        self.assertEqual([c.data for c in ws.controls() if getattr(c, "data", None) in
                          ("imp-item-12", "imp-editor", "imp-item-13")],
                         ["imp-item-12", "imp-editor", "imp-item-13"])
        self.assertIn("Your earlier review of this document was restored: 1 of 60 items "
                      "checked", self.state(ws)[2])

    def test_after_a_restart_the_import_page_offers_to_continue(self):
        self.review()
        self.ws.close()
        again = self.workspace()
        again.app.navigate("questionnaires")
        self.assertEqual(again.find("q-resume-0").content,
                         f"Continue reviewing {fx.DOCX_UNNUMBERED} — 1 of 60 checked")
        again.app.navigate("import")
        self.assertTrue(again.find_all("imp-empty"))
        self.assertEqual(again.find("imp-resume-0").content,
                         f"Continue reviewing {fx.DOCX_UNNUMBERED} — 1 of 60 checked")
        page = again.app.pages["import"]
        with mock.patch.object(again.app, "reveal") as reveal:
            again.click("imp-resume-0")
        self.assert_restored(again, page)
        reveal.assert_called_with("imp-row-12")
        self.assertEqual(page.source_path, str(self.docx))

    def test_a_document_that_moved_or_changed_is_not_offered_or_restored(self):
        from docx import Document

        self.review()
        self.ws.close()
        changed = Document(str(self.docx))
        changed.add_paragraph("A fictional note added later.")
        changed.save(str(self.docx))
        again = self.workspace()
        again.app.navigate("import")
        self.assertFalse(again.find_all("imp-resume-"), "the file at the path changed")
        page = self.open(self.docx, again)
        self.assertIsNone(page.chosen, "a changed document starts a new review")
        self.assertEqual(page.session.reviewed, set())
        self.assertFalse(page.restored)
        self.docx.unlink()
        again.app.navigate("questionnaires")
        self.assertFalse(again.find_all("q-resume"), "nothing to continue without its file")

    def test_a_reading_that_differs_is_never_restored(self):
        self.review()
        record = self.saved()
        record["forms"]["1"]["fingerprint"] = "0" * 64       # read differently now
        (self.root / "import_sessions" / f"{self.sha}.json").write_text(
            json.dumps(record), encoding="utf-8")
        self.ws.close()
        again = self.workspace()
        page = self.open(self.docx, again)
        self.assertIsNone(page.chosen)
        self.assertFalse(page.session.instruments[1].schemes[0].structure_confirmed)
        self.assertIn("Part of the earlier review was not restored", self.state(again)[2])

    def test_restoring_never_confirms_what_the_researcher_did_not(self):
        self.review()
        record = self.saved()
        form = record["forms"]["1"]
        form["checks"] = {"version": "yes", "items": 1, "rights": True}   # tampered values
        form["reviewed"] += [999, -1, "8"]
        form["actions"].append({"do": "approve_scoring"})
        (self.root / "import_sessions" / f"{self.sha}.json").write_text(
            json.dumps(record), encoding="utf-8")
        self.ws.close()
        again = self.workspace()
        again.app.navigate("import")
        page = self.open(self.docx, again)
        s = page.session
        self.assertEqual(s.checks, {"version": False, "rights": True, "items": False})
        self.assertEqual(s.reviewed, {7})
        scheme = s.instrument.schemes[0]
        self.assertFalse(scheme.codes_confirmed or scheme.reverse_confirmed)
        self.assertFalse(s.instruments[0].schemes[0].structure_confirmed, "the other form")
        self.assertTrue(again.find("imp-create-draft").disabled)

    def test_creating_the_draft_removes_the_session(self):
        ws = self.ws
        page = self.review()
        scheme = page.session.instrument.schemes[0]
        ws.click("imp-step-scale")
        ws.check(f"scale-{scheme.id}-numeric")
        ws.click(f"scale-{scheme.id}-apply")
        ws.click("imp-step-confirm")
        ws.check("imp-check-version")
        ws.check("imp-check-items")
        self.assertTrue(self.sessions())
        ws.click("imp-create-draft")
        self.assertEqual(ws.app.route, "questionnaires")
        self.assertEqual(self.sessions(), [])
        self.assertFalse(ws.find_all("q-resume"))

    def test_discarding_the_review_removes_the_session_and_every_change(self):
        ws = self.ws
        page = self.review()
        ws.click("imp-discard")
        self.assertIsNotNone(ws.page.dialog, "the researcher is asked first")
        ws.click("imp-discard-cancel")
        self.assertTrue(self.sessions())
        ws.click("imp-discard")
        ws.click("imp-discard-confirm")
        self.assertEqual(self.sessions(), [])
        s = page.session
        self.assertIsNone(page.chosen)
        self.assertEqual((s.reviewed, page.step), (set(), "source"))
        self.assertFalse(s.instruments[1].questions[4].question["prompt"].endswith("(corrected)."))
        self.assertFalse(s.instruments[1].schemes[0].structure_confirmed)

    def test_a_saved_review_can_be_discarded_from_the_offer(self):
        self.review()
        self.ws.close()
        again = self.workspace()
        again.app.navigate("import")
        again.click("imp-resume-discard-0")
        again.click("imp-discard-confirm")
        self.assertEqual(self.sessions(), [])
        self.assertFalse(again.find_all("imp-resume-"))

    def test_the_review_stays_on_this_computer(self):
        import socket

        def no_network(*args, **kwargs):
            raise AssertionError("the import review must not use the network")

        with mock.patch.object(socket.socket, "connect", no_network), \
                mock.patch.object(socket, "create_connection", no_network):
            self.review()
            self.ws.close()
            again = self.workspace()
            again.app.navigate("import")
            again.click("imp-resume-0")
        self.assertEqual(again.app.pages["import"].session.reviewed, {7})
        self.assertFalse(any(Path(ROOT).glob("import_sessions")), "nothing in the repository")

    def test_the_ocr_language_of_a_scan_is_kept_and_used_again(self):
        """A scan read with local OCR in Russian is read in Russian again
        when its review is continued (OCR stubbed: only the language matters)."""
        from scientific_survey_import import parse_scientific_lines

        languages = []

        def fake_ocr(source, filename, pages, language, **kw):
            languages.append(language)
            lines = [(1 + n // 26, f"{n + 1}. Fictional scanned statement {n + 1}.")
                     for n in range(52)]
            review = parse_scientific_lines(lines, filename, page_count=2,
                                            ocr_pages=tuple(pages),
                                            text_source="pdf_text_layer")
            return replace(review, warnings=(f"OCR pages: 1, 2. Language: {language}. "
                                             "Results were processed locally.",
                                             *review.warnings))

        scan = self.local(fx.SCAN_TABLE_LV)
        with mock.patch("visual_survey_review.ocr_scientific_pdf", side_effect=fake_ocr), \
                mock.patch("visual_survey_review.tesseract_available", return_value=True), \
                mock.patch.object(type(self.page), "_probe_ocr",
                                  staticmethod(lambda: (True, ()))):
            page = self.open(scan)
            self.ws.choose("imp-ocr-language", "rus")
            self.ws.click("imp-ocr-run")
            self.assertEqual(len(page.session.instrument.questions), 52)
            self.assertIn("Local OCR read pages 1 and 2 (language: Russian)", self.state()[2])
            self.ws.click("imp-step-items")
            self.ws.click("imp-item-30")
            self.ws.close()
            again = self.workspace()
            again.app.navigate("import")
            again.click("imp-resume-0")
        restored = again.app.pages["import"]
        self.assertEqual(languages, ["rus", "rus"])
        self.assertEqual((restored.step, restored.selected), ("items", 30))
        self.assertEqual(restored.ocr_language, "rus")


class AutosaveLatvianTests(AutosaveFlow):
    language = "lv"

    def test_after_a_restart_the_import_page_offers_to_continue(self):
        self.review()
        self.ws.close()
        again = self.workspace()
        again.app.navigate("import")
        self.assertEqual(again.find("imp-resume-0").content,
                         f"Turpināt pārbaudīt {fx.DOCX_UNNUMBERED} — pārbaudīti 1 no 60")
        again.click("imp-resume-0")
        page = again.app.pages["import"]
        self.assertEqual((page.chosen, page.step, page.selected), (1, "items", 12))
        self.assertEqual(page.session.reviewed, {7})
        self.assertIn("Jūsu iepriekšējā šī dokumenta pārbaude ir atjaunota: pārbaudīti 1 no 60",
                      self.state(again)[2])


# ============================================================== 4. keyboard
class KeyboardFlow(Base):
    FLAGGED = (4, 11, 20)

    def setUp(self):
        super().setUp()
        from synthetic_documents import numbered_items_pdf

        ws, page = self.ws, self.page
        ws.run(page.open_bytes(numbered_items_pdf(30), "synthetic_30.pdf"))
        s = page.session
        questions = list(s.instrument.questions)
        for index in self.FLAGGED:
            questions[index] = replace(questions[index], confidence="low")
        s.review = replace(s.review, instruments=(replace(s.instrument,
                                                          questions=tuple(questions)),))
        self.reveal = mock.patch.object(ws.app, "reveal").start()
        self.addCleanup(mock.patch.stopall)


class KeyboardTests(KeyboardFlow):
    def test_keys_act_only_on_the_items_step(self):
        ws, page = self.ws, self.page
        for step in ("source", "scale", "confirm"):
            ws.click(f"imp-step-{step}")
            ws.key("F8")
            ws.key("Arrow Down", alt=True)
            self.assertEqual((page.step, page.selected), (step, None), step)
        ws.app.navigate("questionnaires")
        ws.key("F9")
        self.assertEqual(page.session.reviewed, set())

    def test_f8_and_shift_f8_go_to_the_items_that_need_attention(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        visits = []
        for shift in (False, False, False, False, True):
            ws.key("F8", shift=shift)
            visits.append(page.selected)
        self.assertEqual(visits, [4, 11, 20, 4, 20], "F8 wraps; Shift+F8 goes back")
        self.reveal.assert_called_with("imp-row-20")

    def test_f9_marks_the_item_checked_and_goes_on(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        ws.key("F8")
        ws.key("F9")
        self.assertEqual((page.session.reviewed, page.selected), ({4}, 11))
        ws.key("F9")
        ws.key("F9")
        self.assertEqual(page.session.reviewed, {4, 11, 20})
        self.assertIn("Every item that needed attention is checked", ws.app.status_text.value)
        self.assertNotIn("unreviewed", dict(page.session.blocker_keys()))
        self.assertIn(" 3 compared with the source", texts_in(ws, "imp-counts"))

    def test_alt_arrows_move_to_the_next_and_previous_item(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        ws.click("imp-item-9")
        ws.key("Arrow Down", alt=True)
        ws.key("Arrow Down", alt=True)
        self.assertEqual(page.selected, 11)
        ws.key("Arrow Up", alt=True)
        self.assertEqual(page.selected, 10)
        ws.key("Arrow Down")                      # without Alt: the list's own keys
        self.assertEqual(page.selected, 10)
        self.reveal.assert_called_with("imp-row-10")
        self.assertEqual(rows(ws), list(range(30)), "the list keeps every row in place")
        self.assertEqual([c.data for c in ws.controls() if getattr(c, "data", None) in
                          ("imp-item-10", "imp-editor", "imp-item-11")],
                         ["imp-item-10", "imp-editor", "imp-item-11"])

    def test_keys_follow_the_filter(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        ws.segment("imp-filter", "attention")
        ws.key("Arrow Down", alt=True)
        ws.key("Arrow Down", alt=True)
        self.assertEqual(page.selected, 11)

    def test_typed_wording_is_never_applied_by_a_key(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        ws.click("imp-item-4")
        original = page.session.instrument.questions[4].question["prompt"]
        ws.type("imp-wording", original + " (typed, not applied)")
        ws.key("F8")
        self.assertEqual(page.selected, 11)
        self.assertEqual(page.session.instrument.questions[4].question["prompt"], original)
        self.assertNotIn(4, page.session.reviewed)
        ws.key("Arrow Up", alt=True)
        ws.click("imp-item-4")
        self.assertEqual(ws.find("imp-wording", ft.TextField).value,
                         original + " (typed, not applied)")
        self.assertTrue(ws.find_all("imp-not-applied"))

    def test_the_editor_keeps_one_identity_while_moving(self):
        ws = self.ws
        ws.click("imp-step-items")
        ws.click("imp-item-2")
        self.assertEqual(ws.find("imp-editor").key, "imp-editor")
        key = ws.find("imp-item-15").key
        self.assertIsInstance(key, ft.ScrollKey)
        ws.key("F8")
        self.assertEqual(ws.find("imp-item-15").key, key)

    def test_the_keys_are_shown_on_the_items_step(self):
        ws = self.ws
        ws.click("imp-step-items")
        caption = ws.find("imp-keys").value
        for key in ("F8", "Shift+F8", "F9", "Alt+↓", "Alt+↑"):
            self.assertIn(key, caption)
        self.assertFalse(has(ws, "imp-check-next"), "no editor until an item is selected")
        ws.click("imp-item-0")
        self.assertIn("F9", ws.find("imp-check-next").content)


class KeyboardLatvianTests(KeyboardFlow):
    language = "lv"

    def test_the_keys_are_shown_and_work_in_latvian(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        caption = ws.find("imp-keys").value
        self.assertTrue(caption.startswith("Taustiņi: F8"))
        self.assertIn("Alt+↓ / Alt+↑", caption)
        ws.key("F8")
        ws.key("F9")
        self.assertEqual((page.session.reviewed, page.selected), ({4}, 11))
        self.assertIn("salīdzināti ar avotu: 1", texts_in(ws, "imp-counts"))


# ================================================================ 5. 200 items
class LongListTests(Base):
    COUNT = 200
    _pdf = None

    @classmethod
    def pdf(cls) -> bytes:
        from synthetic_documents import numbered_items_pdf

        if LongListTests._pdf is None:
            LongListTests._pdf = numbered_items_pdf(cls.COUNT)
        return LongListTests._pdf

    def setUp(self):
        super().setUp()
        self.ws.run(self.page.open_bytes(self.pdf(), "synthetic_200.pdf"))
        self.assertEqual(len(self.page.session.instrument.questions), self.COUNT)

    def test_200_items_are_listed_a_page_at_a_time(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        self.assertFalse(ws.has_text("could not be shown"))
        self.assertEqual(rows(ws), list(range(100)))
        self.assertEqual(ws.find("imp-list-page").value, "Items 1–100 (page 1 of 2)")
        self.assertTrue(ws.find("imp-list-prev").disabled)
        ws.click("imp-list-next")
        self.assertEqual(rows(ws), list(range(100, 200)))
        self.assertEqual(ws.find("imp-list-page-end").value, "Items 101–200 (page 2 of 2)")
        ws.click("imp-item-150")
        self.assertEqual([c.data for c in ws.controls() if getattr(c, "data", None) in
                          ("imp-item-150", "imp-editor", "imp-item-151")],
                         ["imp-item-150", "imp-editor", "imp-item-151"])
        self.assertEqual(page.list_page, 1)

    def test_rows_keep_stable_keys(self):
        ws = self.ws
        ws.click("imp-step-items")
        before = {c.data: c.key for c in ws.controls()
                  if isinstance(getattr(c, "data", None), str) and c.data.startswith("imp-item-")
                  and c.data[9:].isdigit()}
        ws.click("imp-item-40")
        ws.click("imp-item-41")
        after = {c.data: c.key for c in ws.controls()
                 if isinstance(getattr(c, "data", None), str) and c.data.startswith("imp-item-")
                 and c.data[9:].isdigit()}
        self.assertEqual(before, after)
        self.assertEqual(after["imp-item-41"], ft.ScrollKey("imp-row-41"))

    def test_the_filter_works_on_a_long_list(self):
        ws, page = self.ws, self.page
        s = page.session
        questions = list(s.instrument.questions)
        for index in (5, 120, 199):
            questions[index] = replace(questions[index], confidence="low")
        s.review = replace(s.review, instruments=(replace(s.instrument,
                                                          questions=tuple(questions)),))
        ws.click("imp-step-items")
        ws.segment("imp-filter", "attention")
        self.assertEqual(rows(ws), [5, 120, 199])
        self.assertFalse(ws.find_all("imp-list-page"), "a short filtered list has one page")
        ws.click("imp-item-120")
        ws.check("imp-item-reviewed")
        self.assertEqual(rows(ws), [5, 120, 199], "the selected item stays while open")
        ws.segment("imp-filter", "all")
        self.assertEqual(rows(ws), list(range(100, 200)), "the page of the selected item")

    def test_moving_on_from_the_last_row_of_a_page_opens_the_next_page(self):
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        ws.click("imp-item-99")
        with mock.patch.object(ws.app, "reveal") as reveal:
            ws.key("Arrow Down", alt=True)
        self.assertEqual((page.selected, page.list_page), (100, 1))
        self.assertEqual(rows(ws)[0], 100)
        reveal.assert_called_with("imp-row-100")

    def test_the_items_step_builds_fast_enough(self):
        """Measured: building the items step (all of render()) with 200
        items, a page of 100 rows, compared with every row at once."""
        ws, page = self.ws, self.page
        ws.click("imp-step-items")
        ws.click("imp-item-60")

        def median_ms() -> float:
            times = []
            for _ in range(7):
                started = time.perf_counter()
                ws.app.render()
                times.append(time.perf_counter() - started)
            return 1000 * statistics.median(times)

        def patch_ms() -> float | None:
            """Flet's diff of the rebuilt page for one selection (what is
            computed and sent to the window); informative only."""
            import warnings

            try:
                from flet.controls.base_control import BaseControl
                from flet.controls.object_patch import ObjectPatch
            except ImportError:
                return None
            ws.click("imp-item-60")
            before = ws.app.page_control
            ws.click("imp-item-61")
            after = ws.app.page_control
            started = time.perf_counter()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ObjectPatch.from_diff(before, after, control_cls=BaseControl, frozen=True)
            return 1000 * (time.perf_counter() - started)

        windowed, windowed_patch = median_ms(), patch_ms()
        self.assertEqual(len(rows(ws)), 100)
        with mock.patch.object(type(page), "PAGE_LIMIT", 10_000):
            everything, everything_patch = median_ms(), patch_ms()
            self.assertEqual(len(rows(ws)), 200)
        print(f"\n[ux] items step with {self.COUNT} items: {windowed:.0f} ms per build "
              f"(100 rows shown); {everything:.0f} ms with all {self.COUNT} rows")
        if windowed_patch is not None:
            print(f"[ux] Flet patch of one selection: {windowed_patch:.0f} ms (100 rows); "
                  f"{everything_patch:.0f} ms (all {self.COUNT} rows)")
        self.assertLess(windowed, 600, "the items step must build well under a second")


# ======================================== interaction counts (UX audit rows)
def confirm_and_create(ws) -> None:
    """On the scale step: the scale's structure and codes, then step 4's
    three confirmations, then the draft (the minimum the wizard requires)."""
    page = ws.app.pages["import"]
    scheme = page.session.instrument.schemes[0]
    ws.check(f"scale-{scheme.id}-structure")
    ws.check(f"scale-{scheme.id}-numeric")
    ws.click(f"scale-{scheme.id}-apply")
    ws.click("imp-step-confirm")
    for key in ("version", "rights", "items"):
        ws.check(f"imp-check-{key}")
    ws.click("imp-create-draft")


class ImportInteractionCounts(Base):
    """docs/STAGE36_UX_AUDIT.md: a dropdown counts as two interactions; the
    document itself is opened in the system's Open dialog (not counted)."""

    def counting(self):
        from test_stage36_ux_baseline import CountingWorkspace

        self.ws.close()
        ws = self.workspace(CountingWorkspace)
        ws.app.navigate("import")
        return ws

    def test_review_a_60_item_table_form_without_item_numbers(self):
        ws = self.counting()
        self.open(self.local(fx.DOCX_UNNUMBERED), ws)
        ws.counts.clear()
        ws.click("imp-instrument-use-1")       # the situational form, to its scale step
        confirm_and_create(ws)
        builder = ws.app.pages["questionnaires"]
        self.assertEqual(ws.app.route, "questionnaires")
        self.assertEqual((len(builder.draft), builder.title), (60, SITUATIONAL))
        self.assertEqual(ws.total, 9)
        print(f"\n[ux] review a 60-item table form without item numbers: {ws.total} "
              f"interactions ({dict(ws.counts)}) after the Open dialog (before: blocked)")

    @unittest.skipUnless(tesseract_with("lav"), "local OCR with Latvian is not installed")
    def test_import_a_scanned_52_item_table(self):
        ws = self.counting()
        page = self.open(self.local(fx.SCAN_TABLE_LV), ws)
        self.assertEqual(self.state(ws)[0], "scan")
        ws.counts.clear()
        ws.choose("imp-ocr-language", "lav")
        ws.click("imp-ocr-run")
        state, _, lines = self.state(ws)
        self.assertEqual(state, "review")
        self.assertIn("52 candidate items", lines)
        self.assertIn("Local OCR read pages 1 and 2 (language: Latvian)", lines)
        schemes = page.session.instrument.schemes
        self.assertEqual(len(schemes), 1, "the legend is one documented scale")
        self.assertEqual((schemes[0].evidence, schemes[0].size), ("legend", 5))
        self.assertEqual(len(page.session.linked(schemes[0].id)), 52)
        self.assertFalse(schemes[0].structure_confirmed, "never confirmed automatically")
        ws.click("imp-next")                   # one form: step 1 (facts) → step 2
        confirm_and_create(ws)
        self.assertEqual(len(ws.app.pages["questionnaires"].draft), 52)
        self.assertEqual(ws.total, 12)
        self.assertEqual(self.sessions(), [], "the draft ends the saved review")
        print(f"\n[ux] import a scanned 52-item table (OCR, English interface): {ws.total} "
              f"interactions ({dict(ws.counts)}) after the Open dialog (before: 16 of 52 "
              "found, 36 typed by hand)")


@unittest.skipUnless(tesseract_with("lav"), "local OCR with Latvian is not installed")
class LatvianScanTests(Base):
    language = "lv"

    def test_the_latvian_interface_proposes_latvian_ocr(self):
        from test_stage36_ux_baseline import CountingWorkspace

        self.ws.close()
        ws = self.workspace(CountingWorkspace)
        ws.app.navigate("import")
        page = self.open(self.local(fx.SCAN_TABLE_LV), ws)
        self.assertEqual(ws.find("imp-ocr-language", ft.Dropdown).value, "lav")
        ws.counts.clear()
        ws.click("imp-ocr-run")
        state, title, lines = self.state(ws)
        self.assertEqual(title, "Jāpārbauda")
        self.assertIn("kandidātjautājumi: 52", lines)
        self.assertIn("Lokālā OCR nolasīja: 1. un 2. lappuse (valoda: latviešu)", lines)
        self.assertIn("gandrīz", " / ".join(page.session.instrument.schemes[0].labels))
        ws.click("imp-next")
        confirm_and_create(ws)
        self.assertEqual(len(ws.app.pages["questionnaires"].draft), 52)
        self.assertEqual(ws.total, 10)
        print(f"\n[ux] import a scanned 52-item table (OCR, Latvian interface): {ws.total} "
              f"interactions ({dict(ws.counts)})")


if __name__ == "__main__":
    unittest.main()
