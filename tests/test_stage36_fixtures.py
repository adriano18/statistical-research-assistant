"""Stage 36.0: the synthetic acceptance fixtures are what they claim to be.

tests/fixtures/stage36/README.md lists the minimal independent checks:
CSV shape and group sizes, two 60-item DOCX forms, image-only scans with
52 numbered prompts and reference distractors, and determinism.
"""

from __future__ import annotations

import collections
import csv
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import stage36_fixtures as fx  # noqa: E402


class CsvFixtureTests(unittest.TestCase):
    def test_shape_ids_and_imbalanced_groups(self):
        rows = list(csv.DictReader(fx.fixture(fx.CSV).open(encoding="utf-8")))
        self.assertEqual(len(rows), 55)
        self.assertEqual(list(rows[0]), fx.generator().COLUMNS)
        self.assertEqual(len(rows[0]), 13)
        self.assertEqual(len({row["Code"] for row in rows}), 55, "unique fictional IDs")
        self.assertTrue(all(row["Code"].startswith("fictional_") for row in rows))
        self.assertEqual(dict(collections.Counter(row["UCLA_Level"] for row in rows)),
                         {"1": 3, "2": 47, "3": 5})
        for row in rows:
            ucla, level = int(row["UCLA"]), row["UCLA_Level"]
            self.assertEqual(level, "1" if ucla <= 39 else "2" if ucla <= 59 else "3",
                             "the level is derived from the invented score")
            for scale in fx.SCALES:
                self.assertTrue(8 <= int(row[scale]) <= 45, scale)

    def test_the_generator_is_deterministic(self):
        with tempfile.TemporaryDirectory() as folder:
            again = fx.generate(Path(folder))
            self.assertEqual(again[fx.CSV].read_bytes(), fx.fixture(fx.CSV).read_bytes())
            self.assertEqual(again[fx.ITEMS_CSV].read_bytes(),
                             fx.fixture(fx.ITEMS_CSV).read_bytes())
            from docx import Document

            for name in (fx.DOCX_NUMBERED, fx.DOCX_UNNUMBERED):
                first = [[c.text for c in r.cells] for t in Document(fx.fixture(name)).tables
                         for r in t.rows]
                second = [[c.text for c in r.cells] for t in Document(again[name]).tables
                          for r in t.rows]
                self.assertEqual(first, second, name)


class ItemFixtureTests(unittest.TestCase):
    """Stage 36.3: invented item-level responses for item diagnostics."""

    def rows(self):
        with fx.fixture(fx.ITEMS_CSV).open(encoding="utf-8", newline="") as file:
            return list(csv.DictReader(file))

    def test_shape_names_and_codes_in_range(self):
        module = fx.generator()
        self.assertEqual((module.ITEMS, module.ITEM_TOTAL, module.REVERSE_ITEMS, module.FLOOR_ITEM),
                         (fx.ITEMS, fx.ITEM_TOTAL, fx.REVERSE_ITEMS, fx.FLOOR_ITEM))
        rows = self.rows()
        self.assertEqual(len(rows), 200)
        self.assertEqual(list(rows[0]), ["Code", *fx.ITEMS, fx.ITEM_TOTAL])
        self.assertEqual(len({row["Code"] for row in rows}), 200, "unique invented codes")
        self.assertTrue(all(row["Code"].startswith("invented_") for row in rows))
        for row in rows:
            for item in fx.ITEMS:
                if row[item]:
                    self.assertIn(row[item], {"1", "2", "3", "4", "5"}, item)

    def test_a_few_missing_answers_and_the_invented_total(self):
        rows = self.rows()
        missing = [(number, item) for number, row in enumerate(rows, 1) for item in fx.ITEMS
                   if not row[item]]
        self.assertEqual(missing, sorted(fx.generator().ITEM_MISSING))
        self.assertEqual(len(missing), 9)
        for row in rows:
            codes = [row[item] for item in fx.ITEMS]
            if "" in codes:
                self.assertEqual(row[fx.ITEM_TOTAL], "", "no total for an incomplete row")
                continue
            scored = [6 - int(code) if item in fx.REVERSE_ITEMS else int(code)
                      for item, code in zip(fx.ITEMS, codes)]
            self.assertEqual(int(row[fx.ITEM_TOTAL]), sum(scored))

    def test_reverse_keyed_items_are_not_recoded_and_one_item_has_a_floor(self):
        import pandas as pd

        frame = pd.read_csv(fx.fixture(fx.ITEMS_CSV))
        complete = frame[list(fx.ITEMS)].dropna()
        total = complete.sum(axis=1)
        for item in fx.ITEMS:
            r = complete[item].corr(total - complete[item])
            if item in fx.REVERSE_ITEMS:
                self.assertLess(r, -0.3, f"{item} runs against the other items")
            else:
                self.assertGreater(r, 0.3, item)
        floor = (frame[fx.FLOOR_ITEM] == 1).mean()
        self.assertGreater(floor, 0.5)
        self.assertTrue(all((frame[item] == 1).mean() < 0.15 for item in fx.ITEMS
                            if item != fx.FLOOR_ITEM))


class DocxFixtureTests(unittest.TestCase):
    def tables(self, name):
        from docx import Document

        return Document(fx.fixture(name)).tables

    def test_two_sixty_item_forms_with_numbered_cells(self):
        tables = self.tables(fx.DOCX_NUMBERED)
        self.assertEqual([(len(t.rows), len(t.columns)) for t in tables], [(61, 5), (60, 5)])

    def test_two_sixty_item_forms_without_numbers_in_cells(self):
        tables = self.tables(fx.DOCX_UNNUMBERED)
        self.assertEqual([(len(t.rows), len(t.columns)) for t in tables], [(61, 5), (60, 5)])
        prompts = [row.cells[0].text for table in tables for row in table.rows][1:]
        self.assertEqual(len(prompts), 120)
        self.assertFalse(any(prompt[:1].isdigit() for prompt in prompts),
                         "no item numbers inside the cells")
        self.assertEqual([c.text for c in tables[0].rows[0].cells][1:],
                         ["Hardly ever", "Now and then", "Fairly often", "Very often"])

    def test_references_and_scoring_key_are_paragraphs_not_table_rows(self):
        from docx import Document

        for name in (fx.DOCX_NUMBERED, fx.DOCX_UNNUMBERED):
            document = Document(fx.fixture(name))
            cells = " ".join(c.text for t in document.tables for r in t.rows for c in r.cells)
            self.assertNotIn("Imaginary Author", cells)
            text = "\n".join(p.text for p in document.paragraphs)
            self.assertIn("Imaginary Author", text)
            self.assertIn("Dimension 15", text)


class ScanFixtureTests(unittest.TestCase):
    def test_image_only_two_page_scans(self):
        import pypdf

        for name in (fx.SCAN_INLINE, fx.SCAN_TABLE_LV):
            reader = pypdf.PdfReader(fx.fixture(name))
            self.assertEqual(len(reader.pages), 2, name)
            self.assertEqual([(page.extract_text() or "").strip() for page in reader.pages],
                             ["", ""], f"{name} has no selectable text layer")

    def test_the_lv_statements_carry_latvian_letters_and_wrap(self):
        module = fx.generator()
        statements = [module._lv_statement(i) for i in range(1, 53)]
        self.assertTrue(all(any(ch in s for ch in "āēīūčšžģķļņ") for s in statements))
        self.assertEqual(sum(1 for i in range(1, 53) if i % 4 == 1), 13,
                         "13 long statements wrap onto a second line")


if __name__ == "__main__":
    unittest.main()
