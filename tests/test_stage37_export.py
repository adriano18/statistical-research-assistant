"""Stage 37 (#67): export and interoperability, with independent readers.

Round trips on the synthetic 180-case master fixture
(tests/fixtures/stage37/generate_master_fixture.py, generated into a
temporary folder) plus adversarial columns: cells that begin with = + - @,
a tab or an apostrophe, long Latvian and Russian names, dates, leading
zeros, labels for missing codes, user-missing codes, empty texts beside
missing ones. Every file is read back with a reader the export does not
use: openpyxl (.xlsx), pandas.read_csv (.csv), pyreadstat.read_sav (.sav),
zipfile (.zip), and R for the R syntax when Rscript is installed.

Documented tolerances (docs/STAGE37_EXPORT.md §4):
- .xlsx: openpyxl writes a number with 16 significant digits, so a double
  that needs 17 (0.1 + 0.2) reads back within 1e-15 relative; every value of
  the fixture is exact. A whole number reads back as an int, a date as a
  datetime at midnight.
- .csv: numbers are exact (repr). pandas reads a column of whole numbers as
  int64 and cannot tell ``""`` from an empty field (both NaN); text columns
  are read as text, as the codebook says; the apostrophe is removed with
  csv_safety.restore.
- .sav: doubles exact, whole numbers as float64; an identifier is a string;
  a missing text is an empty text declared missing (NaN when read).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import csv_safety  # noqa: E402
import data_export as de  # noqa: E402
import export_bundle as eb  # noqa: E402
from data_loader import ImportOptions, load_dataset_with_report  # noqa: E402
from workspace_state import ResearchSession  # noqa: E402

GENERATOR = ROOT / "tests" / "fixtures" / "stage37" / "generate_master_fixture.py"
FORMULAS = ("=1+1", "+x", "-2+3", "@SUM(A1)", "\tTAB", "plain", "'=quoted")
LV_NAME = "Ļoti garš mainīgā nosaukums ar garumzīmēm un vēl vairāk teksta līdz robežai"
RU_NAME = "Очень длинное имя переменной на русском языке, чтобы превысить лимит SPSS"
RATING_LABELS = {"1": "Never", "2": "Rarely", "5": "Always", "-9": "Refused",
                 "-8": "Don't know"}


def generate_master(folder: Path) -> Path:
    spec = importlib.util.spec_from_file_location("stage37_master_fixture", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    csv_path, _ = module.generate(folder)
    return csv_path


def master_session(folder: Path, *, adversarial: bool = True) -> ResearchSession:
    """The fixture as the program loads it, levels confirmed, plus the
    adversarial columns and their documented metadata."""
    frame, report = load_dataset_with_report(generate_master(folder))
    if adversarial:
        n = len(frame)
        extra = pd.DataFrame({
            "formula_text": [FORMULAS[i % len(FORMULAS)] for i in range(n)],
            LV_NAME: np.arange(n, dtype=float) / 4,
            RU_NAME: [("Да", "Нет", None)[i % 3] for i in range(n)],
            "visit_date": [None if i % 5 == 0 else dt.datetime(2024, 1, 1) + dt.timedelta(
                days=i, hours=i % 24) for i in range(n)],
            "visit_day": [None if i % 7 == 0 else dt.date(2025, 1, 1) + dt.timedelta(days=i)
                          for i in range(n)],
            "code_lz": [f"{i:03d}" for i in range(n)],
            "rating": [(1.0, 2.0, -9.0, 5.0, -8.0, np.nan)[i % 6] for i in range(n)],
            "unlabelled": [float(i % 4) for i in range(n)],
            "empty_or_missing": [("", None, "x")[i % 3] for i in range(n)],
            "precise": [0.1 + 0.2 if i % 2 else 1 / 3 for i in range(n)],
            # "1,234" is ambiguous to a reader guessing the decimal mark.
            "thousandths": [float(f"{i % 10}.234") for i in range(n)],
        }, index=frame.index)
        extra["visit_date"] = extra["visit_date"].astype(object)
        extra["visit_day"] = extra["visit_day"].astype(object)
        frame = pd.concat([frame, extra], axis=1)
    session = ResearchSession()
    session.set_dataset(frame, "synthetic_master_research_n180.csv", report=report)
    for name, info in session.variables.items():
        level = "scale" if info.storage == "number" else "nominal"
        if name in ("participant_code", "code_lz"):
            level = "id"
        if name in ("sex_code", "employed_code"):
            level = "nominal"
        if name == "rating":
            level = "ordinal"
        session.confirm_level(name, level)
    if adversarial:
        session.set_metadata({
            "rating": {"label": "How often? (fictional item, " + "ā" * 140 + ")",
                       "value_labels": RATING_LABELS, "missing_codes": ["-9", "-8"],
                       "source": "codebook"},
            "SYN_LON_TOTAL": {"label": "Fictional loneliness-like total (20 items)",
                              "source": "codebook"},
            RU_NAME: {"label": "Да/нет (вымышленный вопрос)",
                      "value_labels": {"Да": "согласие " + "ж" * 70}, "source": "codebook"},
        })
    return session


def codebook_of(session: ResearchSession, **kwargs) -> de.Codebook:
    return eb.codebook_for(session, app_version="test", **kwargs)


def same_number(a, b, *, rel: float = 0.0) -> bool:
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)):
        return (a is None or (isinstance(a, float) and math.isnan(a))) and \
            (b is None or (isinstance(b, float) and math.isnan(b)))
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=0.0) if rel else \
        float(a) == float(b)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.session = master_session(self.folder / "fixture")
        self.df = self.session.df
        self.book = codebook_of(self.session)


# ================================================================= .xlsx
class XlsxRoundTripTests(Fixture):
    def export(self, **kwargs) -> Path:
        path = self.folder / "data.xlsx"
        facts = de.export_xlsx(path, self.df, self.book, **kwargs)
        self.assertEqual(facts["verified"]["rows"], 180)
        return path

    def test_values_types_and_missing_survive_openpyxl(self):
        from openpyxl import load_workbook

        path = self.export()
        sheet = load_workbook(path)["Data"]
        header = [c.value for c in sheet[1]]
        self.assertEqual(header, [str(c) for c in self.df.columns])
        for position, name in enumerate(self.df.columns, start=1):
            entry = self.book.variable(name)
            for row, value in enumerate(self.df[name], start=2):
                cell = sheet.cell(row=row, column=position)
                if de.is_missing(value):
                    self.assertIsNone(cell.value, (name, row))
                    self.assertEqual(cell.data_type, "n", "a missing value is no cell at all")
                elif isinstance(value, str):
                    if value == "":
                        self.assertEqual(cell.data_type, "inlineStr",
                                         "an empty text is a text cell, unlike a missing value")
                    else:
                        self.assertEqual((cell.value, cell.data_type), (value, "s"), (name, row))
                elif entry.kind == "number":
                    self.assertTrue(same_number(cell.value, value, rel=1e-15), (name, row))
                    if name != "precise":
                        self.assertEqual(float(cell.value), float(value), "fixture values exact")
                elif isinstance(value, dt.datetime):
                    self.assertEqual(cell.value, value)
                elif isinstance(value, dt.date):
                    self.assertEqual(cell.value, dt.datetime.combine(value, dt.time()))
        self.assertEqual(sheet.cell(row=2, column=header.index("code_lz") + 1).value, "000")
        self.assertEqual(sheet.cell(row=9, column=header.index("code_lz") + 1).value, "007")

    def test_no_cell_is_ever_a_formula(self):
        path = self.export(sections=de.SECTIONS)
        with zipfile.ZipFile(path) as archive:
            sheets = [n for n in archive.namelist() if n.startswith("xl/worksheets/")]
            text = "".join(archive.read(n).decode("utf-8") for n in sheets)
        self.assertNotIn("<f>", text)
        self.assertNotIn("<f ", text)
        for attack in ("=1+1", "+x", "-2+3", "@SUM(A1)"):
            self.assertIn(f'<c r="', text)
            self.assertRegex(text, rf't="inlineStr"><is><t>{re.escape(attack)}</t>')

    def test_pandas_reads_the_data_sheet(self):
        path = self.export()
        text = [v.name for v in self.book.variables if v.kind in ("text", "mixed")]
        frame = pd.read_excel(path, sheet_name="Data", dtype={c: str for c in text})
        self.assertEqual(list(frame.columns), [str(c) for c in self.df.columns])
        self.assertEqual(frame["code_lz"].tolist()[:3], ["000", "001", "002"])
        for name in ("SYN_LON_TOTAL", "SYN_SUP_MEAN", LV_NAME, "rating"):
            pd.testing.assert_series_equal(frame[name].astype(float), self.df[name].astype(float),
                                           check_names=False)
        self.assertEqual(frame["formula_text"].tolist()[:4], list(FORMULAS[:4]))

    def test_codebook_scales_and_provenance_sheets(self):
        from openpyxl import load_workbook

        path = self.export(sections=("data", "codebook", "scales", "provenance"))
        book = load_workbook(path)
        self.assertEqual(book.sheetnames, ["Data", "Codebook", "Scales", "Provenance"])
        rows = list(book["Codebook"].iter_rows(values_only=True))
        self.assertEqual(list(rows[0][:len(de.CODEBOOK_COLUMNS)]), list(de.CODEBOOK_COLUMNS))
        by_name = {r[0]: r for r in rows[1:len(self.df.columns) + 1]}
        rating = dict(zip(de.CODEBOOK_COLUMNS, by_name["rating"]))
        self.assertEqual(rating["Measurement level"], "ordinal")
        self.assertEqual(rating["Value labels"], "-9 = Refused; -8 = Don't know; 1 = Never; "
                                                 "2 = Rarely; 5 = Always")
        self.assertEqual(rating["Missing codes (user-missing)"], "-9; -8")
        self.assertEqual((rating["User-missing"], rating["Missing (empty)"]), (60, 30))
        self.assertEqual(dict(zip(de.CODEBOOK_COLUMNS, by_name["code_lz"]))["Measurement level"],
                         "id")
        provenance = dict(r[:2] for r in book["Provenance"].iter_rows(values_only=True) if r[0])
        self.assertEqual(provenance["Dataset SHA-256 (CSV text, as results record it)"],
                         self.session.dataset_sha256())

    def test_streaming_reports_progress_and_refuses_what_excel_cannot_hold(self):
        calls = []
        with mock.patch.object(de, "PROGRESS_EVERY", 50):
            de.export_xlsx(self.folder / "p.xlsx", self.df, self.book,
                           progress=lambda done, total: calls.append((done, total)))
        self.assertEqual(calls, [(50, 180), (100, 180), (150, 180), (180, 180)])
        with mock.patch.object(de, "XLSX_MAX_ROWS", 100):
            with self.assertRaisesRegex(de.ExportError, "do not fit"):
                de.export_xlsx(self.folder / "big.xlsx", self.df, self.book)
        self.assertFalse((self.folder / "big.xlsx").exists())


# ================================================================== .csv
class CsvRoundTripTests(Fixture):
    def read(self, path: Path, *, sep=",", decimal=".") -> pd.DataFrame:
        text = [v.name for v in self.book.variables if v.kind in ("text", "mixed")]
        return pd.read_csv(path, encoding="utf-8-sig", sep=sep, decimal=decimal,
                           dtype={csv_safety.protect(c): str for c in text},
                           keep_default_na=False, na_values=[""])

    def check_frame(self, frame: pd.DataFrame) -> None:
        self.assertEqual([csv_safety.restore(c) for c in frame.columns],
                         [str(c) for c in self.df.columns])
        frame.columns = [csv_safety.restore(c) for c in frame.columns]
        for name in self.df.columns:
            entry = self.book.variable(name)
            if entry.kind == "number":
                for a, b in zip(frame[name], self.df[name]):
                    self.assertTrue(same_number(a, b), (name, a, b))
            elif entry.kind in ("text", "mixed"):
                for a, b in zip(frame[name], self.df[name]):
                    if de.is_missing(b) or b == "":
                        self.assertTrue(de.is_missing(a), "pandas reads both as NaN")
                    else:
                        self.assertEqual(csv_safety.restore(a), b)

    def test_comma_layout_with_pandas(self):
        path = self.folder / "data.csv"
        facts = de.export_csv(path, self.df, self.book, bom=True, layout="comma")
        self.assertEqual(facts["verified"]["rows"], 180)
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.check_frame(self.read(path))
        book = json.loads(csv_safety.codebook_path(path).read_text(encoding="utf-8"))
        self.assertEqual(book["data_file"]["sha256"], csv_safety.sha256_file(path))
        self.assertEqual((book["data_file"]["delimiter"], book["data_file"]["decimal"]),
                         (",", "dot"))

    def test_semicolon_layout_with_decimal_comma_for_excel_in_latvian_or_russian(self):
        path = self.folder / "lv.csv"
        de.export_csv(path, self.df, self.book, bom=True, layout="semicolon")
        first = path.read_text(encoding="utf-8-sig").splitlines()[1]
        self.assertIn(";", first)
        self.assertRegex(path.read_text(encoding="utf-8-sig"), r";0,25;")
        self.check_frame(self.read(path, sep=";", decimal=","))

    def test_formula_injection_is_neutralised_and_numbers_are_not(self):
        path = self.folder / "data.csv"
        de.export_csv(path, self.df, self.book, bom=False)
        import csv
        import io

        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))
        column = rows[0].index("formula_text")
        cells = [r[column] for r in rows[1:8]]
        self.assertEqual(cells, ["'=1+1", "'+x", "'-2+3", "'@SUM(A1)", "'\tTAB", "plain",
                                 "''=quoted"])
        for cell in (r[column] for r in rows[1:]):
            self.assertFalse(cell[:1] in csv_safety.TRIGGERS, cell)
        rating = rows[0].index("rating")
        self.assertIn("-9", [r[rating] for r in rows[1:]], "a negative number stays a number")
        raw = path.read_text(encoding="utf-8")
        self.assertIn(',-9,', raw.replace('"', ""))
        self.assertNotIn("'-9", raw)

    def test_the_program_reads_its_own_csv_back_exactly(self):
        for layout in ("comma", "semicolon"):
            path = self.folder / f"own_{layout}.csv"
            de.export_csv(path, self.df, self.book, layout=layout)
            frame, report = load_dataset_with_report(path)
            self.assertEqual(list(frame.columns), [str(c) for c in self.df.columns])
            self.assertEqual(frame["formula_text"].tolist(), self.df["formula_text"].tolist())
            self.assertEqual(frame["code_lz"].tolist(), self.df["code_lz"].tolist())
            for name in ("SYN_SUP_MEAN", LV_NAME, "rating", "precise", "thousandths"):
                for a, b in zip(frame[name], self.df[name]):
                    self.assertTrue(same_number(a, b), (layout, name, a, b))
            if layout == "semicolon":
                self.assertIn(";1,234\n", path.read_text(encoding="utf-8-sig"),
                              "the last column, written with a decimal comma")
            self.assertEqual(report.metadata["rating"]["value_labels"], RATING_LABELS)
            self.assertEqual(report.metadata["rating"]["missing_codes"], ["-9", "-8"])
            self.assertEqual(report.metadata["SYN_LON_TOTAL"]["measure"], "scale")
            self.assertTrue(any("Formula protection removed" in w for w in report.warnings))
            session = ResearchSession()
            session.set_dataset(frame, path.name, report=report)
            self.assertEqual(session.variables["rating"].value_label_map, RATING_LABELS)
            self.assertEqual(session.variables["rating"].suggested, "ordinal")
            self.assertEqual(session.variables["rating"].confirmed, "unknown",
                             "a documented level is a suggestion, never a confirmation")


# ================================================================== .sav
class SavRoundTripTests(Fixture):
    def test_values_labels_levels_and_missing_codes_with_pyreadstat(self):
        import pyreadstat

        path = self.folder / "data.sav"
        plan = de.plan_sav(self.df, self.book)
        facts = de.export_sav(path, self.df, self.book, plan=plan)
        self.assertEqual(facts["verified"]["rows"], 180)
        frame, meta = pyreadstat.read_sav(str(path), user_missing=True)
        names = [self.book.variable(c).spss_name for c in self.df.columns]
        self.assertEqual(list(frame.columns), names)
        for column, spss in zip(self.df.columns, names):
            entry, values = self.book.variable(column), frame[spss]
            if entry.kind == "number" and entry.level != "id":
                for a, b in zip(values, self.df[column]):
                    self.assertTrue(same_number(a, b), (column, a, b))
            self.assertEqual(meta.variable_measure[spss],
                             {"id": "nominal"}.get(entry.level, entry.level), column)
        self.assertEqual(meta.missing_ranges["rating"], [{"lo": -9.0, "hi": -9.0},
                                                         {"lo": -8.0, "hi": -8.0}])
        self.assertEqual(meta.variable_value_labels["rating"],
                         {float(k): v for k, v in RATING_LABELS.items()})
        self.assertEqual(meta.column_names_to_labels["SYN_LON_TOTAL"],
                         "Fictional loneliness-like total (20 items)")
        label = meta.column_names_to_labels["rating"]
        self.assertLessEqual(len(label.encode("utf-8")), de.SAV_LABEL_BYTES)
        self.assertTrue(label.startswith("How often? (fictional item, ā"))
        self.assertEqual(frame["code_lz"].tolist()[:8], [f"{i:03d}" for i in range(8)],
                         "an identifier is a string variable with its leading zeros")
        self.assertEqual(meta.original_variable_types["code_lz"][0], "A")
        ru = plan.renamed[RU_NAME]
        self.assertEqual(meta.missing_ranges[ru], [{"lo": "", "hi": ""}])
        self.assertEqual(frame[ru].tolist()[:3], ["Да", "Нет", ""])
        plain, _ = pyreadstat.read_sav(str(path))
        self.assertTrue(pd.isna(plain[ru].iloc[2]), "a missing text reads back as missing")
        self.assertEqual(frame["formula_text"].tolist()[:7], list(FORMULAS))
        self.assertEqual(frame["visit_date"].iloc[1], pd.Timestamp(2024, 1, 2, 1))
        self.assertEqual(meta.file_encoding, "UTF-8")

    def test_names_are_valid_unique_without_case_and_reversible(self):
        names = ["age", "AGE", "1st item", "a b", "TO", "with", "x.", "_lead", "#scratch",
                 "$sys", LV_NAME, RU_NAME, "Возраст", "ā" * 40, "", "Q1__missing_reason",
                 "a" * 70, "a" * 71]
        mapping = de.spss_names(names)
        spss = list(mapping.values())
        self.assertEqual(len({s.casefold() for s in spss}), len(names))
        for name in spss:
            self.assertTrue(de.valid_sav_name(name), name)
            self.assertLessEqual(len(name.encode("utf-8")), 64)
            self.assertNotIn(name.upper(), de.SAV_RESERVED)
        self.assertEqual(mapping["age"], "age")
        self.assertEqual(mapping["Q1__missing_reason"], "Q1__missing_reason", "valid: unchanged")
        self.assertEqual(mapping["Возраст"], "Возраст", "Unicode letters are valid in SPSS")
        self.assertEqual(mapping["TO"], "V_TO")
        frame = pd.DataFrame([[0] * len(names)], columns=[mapping[n] for n in names])
        self.assertEqual(list(de.restore_names(frame, mapping).columns), names)

    def test_the_preview_lists_every_renamed_cut_or_converted_field(self):
        frame = pd.DataFrame({
            "id": [1.0, 2.0], "a b": [1.0, 2.0], "q": [1.0, 2.0],
            "group": pd.Categorical(["low", "high"], categories=["low", "high"], ordered=True),
            "many": [1.0, -9.0]})
        book = de.build_codebook(frame, "Fictional " + "x" * 80, levels={"id": ("id", "data", "id")},
                                 metadata={"q": {"label": "L" * 300,
                                                 "value_labels": {"1": "V" * 130}},
                                           # no range can hold these without the valid 1
                                           "many": {"missing_codes": ["-9", "-8", "5", "99"]}})
        plan = de.plan_sav(frame, book)
        self.assertEqual(plan.renamed, {"a b": "a_b"})
        keys = {(name, key) for name, key, _ in plan.changes}
        self.assertEqual(keys, {("id", "export.change.id_text"),
                                ("q", "export.change.label_cut"),
                                ("q", "export.change.value_label_cut"),
                                ("group", "export.change.category_codes"),
                                ("many", "export.change.missing_limit"),
                                ("", "export.change.file_label_cut")})
        from workspace_text import T

        for _, key, values in plan.changes:
            for text in T[key]:
                text.format(name="x", **values)       # every language, same placeholders
        de.export_sav(self.folder / "plan.sav", frame, book, plan=plan)

    def test_the_program_restores_names_and_metadata_from_its_own_sav(self):
        path = self.folder / "own.sav"
        de.export_sav(path, self.df, self.book)
        frame, report = load_dataset_with_report(path)
        self.assertEqual(list(frame.columns), [str(c) for c in self.df.columns],
                         "names restored from the file's notes, the long LV/RU ones included")
        self.assertTrue(any("restored from the notes" in w for w in report.warnings))
        self.assertEqual(report.metadata["rating"]["value_labels"], RATING_LABELS)
        self.assertEqual(report.metadata["rating"]["missing_codes"], ["-9", "-8"])
        self.assertEqual(report.metadata["rating"]["measure"], "ordinal")
        user = self.df["rating"].isin([-9.0, -8.0])
        self.assertTrue(frame["rating"][user].isna().all(),
                        "by default a user-missing value is missing, as SPSS treats it")
        self.assertTrue((frame["rating"][~user].fillna(-1) == self.df["rating"][~user]
                         .fillna(-1)).all())
        kept, _ = load_dataset_with_report(path, ImportOptions(user_missing="codes"))
        pd.testing.assert_series_equal(kept["rating"], self.df["rating"], check_names=False)
        self.assertEqual(frame["code_lz"].tolist(), self.df["code_lz"].tolist())
        for name in ("SYN_SUP_MEAN", LV_NAME, "precise"):
            pd.testing.assert_series_equal(frame[name].astype(float),
                                           self.df[name].astype(float), check_names=False)

    def test_an_external_sav_comes_in_and_goes_out_with_its_metadata(self):
        import pyreadstat

        source = self.folder / "external.sav"
        external = pd.DataFrame({
            "resp": ["007", "010", "011", "012", "013"],
            "q1": [1.0, 5.0, -9.0, 3.0, 2.0], "q2": [2.0, -8.0, 4.0, 99.0, -1.0],
            "sex": [1.0, 2.0, 1.0, 2.0, 1.0], "note": ["=1+1", "", "ok", "DK", "Ж"]})
        pyreadstat.write_sav(
            external, str(source),
            column_labels={"q1": "Kā jūtaties? / Как вы?", "sex": "Sex"},
            variable_value_labels={"q1": {1: "Never", 5: "Always", -9: "Refused"},
                                   "sex": {1: "female", 2: "male"}, "note": {"DK": "Don't know"}},
            missing_ranges={"q1": [-9], "q2": [{"lo": -8, "hi": -1}, 99], "note": ["DK"]},
            variable_measure={"q1": "ordinal", "sex": "nominal", "q2": "scale", "resp": "nominal"})
        frame, report = load_dataset_with_report(source, ImportOptions(user_missing="codes"))
        session = ResearchSession()
        session.set_dataset(frame, source.name, report=report)
        session.confirm_level("resp", "id")
        session.accept_suggestions()
        self.assertEqual(session.variables["q1"].confirmed, "ordinal")
        self.assertEqual(session.variables["q1"].label, "Kā jūtaties? / Как вы?")
        out = self.folder / "out.sav"
        de.export_sav(out, session.df, codebook_of(session))
        again, meta = pyreadstat.read_sav(str(out), user_missing=True)
        _, original = pyreadstat.read_sav(str(source), user_missing=True)
        for column in ("q1", "q2", "sex"):
            pd.testing.assert_series_equal(again[column], external[column], check_names=False)
        self.assertEqual(again["resp"].tolist(), external["resp"].tolist())
        self.assertEqual(again["note"].tolist(), external["note"].tolist())
        self.assertEqual(meta.column_names_to_labels["q1"], original.column_names_to_labels["q1"])
        self.assertEqual(meta.column_names_to_labels["sex"], "Sex")
        self.assertEqual(meta.variable_value_labels, original.variable_value_labels)
        self.assertEqual(meta.missing_ranges["q1"], original.missing_ranges["q1"])
        self.assertEqual(meta.missing_ranges["q2"], original.missing_ranges["q2"])
        self.assertEqual(meta.missing_ranges["note"][0], {"lo": "DK", "hi": "DK"})
        for column in ("q1", "q2", "sex"):
            self.assertEqual(meta.variable_measure[column], original.variable_measure[column])


# ============================================================= metadata
class MetadataStorageTests(unittest.TestCase):
    def test_the_project_keeps_metadata_in_format_6_without_a_new_column(self):
        import project_store as ps

        self.assertEqual(ps.SCHEMA_VERSION, 6)
        with tempfile.TemporaryDirectory() as folder:
            store = ps.ProjectStore(Path(folder))
            info = store.create("Fictional metadata study")
            with store.open(info.id) as project:
                record = project.add_frame(pd.DataFrame({"q1": [1.0, 2.0], "id": ["a", "b"]}),
                                           "data", origin="copy")
                project.save_variable_metadata(record.id, {
                    "q1": {"label": "Kā jūtaties?", "value_labels": {"1": "Never"},
                           "missing_codes": ["-9", ["range", -8, -1]], "source": "sav"}})
                self.assertEqual(project.variable_metadata(record.id), {
                    "q1": {"label": "Kā jūtaties?", "value_labels": {"1": "Never"},
                           "missing_codes": ["-9", ["range", -8, -1]], "source": "sav"}})
                self.assertEqual(project.levels(record.id)["q1"]["label"], "Kā jūtaties?")
                with project._db() as db:
                    columns = [r[1] for r in db.execute("PRAGMA table_info(datasets)")]
                    notes = db.execute("SELECT notes FROM datasets").fetchone()[0]
                self.assertIn("notes", columns)
                self.assertEqual(json.loads(notes)["format"], ps.METADATA_FORMAT)
                with project._write() as db:
                    db.execute("UPDATE datasets SET notes = 'the researcher wrote this'")
                with self.assertRaises(ps.ProjectError):
                    project.save_variable_metadata(record.id, {"q1": {"label": "x"}})
                with project._db() as db:
                    self.assertEqual(db.execute("SELECT notes FROM datasets").fetchone()[0],
                                     "the researcher wrote this", "never overwritten")

    def test_metadata_follows_the_dataset_through_a_restart_and_a_prepared_version(self):
        from workspace_harness import Workspace

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "labelled.sav"
            import pyreadstat

            pyreadstat.write_sav(pd.DataFrame({"q1": [1.0, 2.0, 3.0], "q2": [3.0, 2.0, 1.0]}),
                                 str(source), column_labels={"q1": "Fictional item one"},
                                 variable_value_labels={"q1": {1: "Never", 3: "Often"}},
                                 missing_ranges={"q1": [-9]})
            ws = Workspace(root=root)
            try:
                ws.app.projects.create("Fictional labelled study")
                self.assertTrue(ws.run(ws.app.load_path(str(source))))
                ws.click("nav-data")
                self.assertEqual(ws.find("label-q1").value, "Fictional item one")
            finally:
                ws.close()
            again = Workspace(root=root)
            try:
                project = again.app.projects.projects()[0]
                again.app.projects.open(project.id)
                info = again.app.session.variables["q1"]
                self.assertEqual((info.label, info.value_label_map, info.missing_codes),
                                 ("Fictional item one", {"1": "Never", "3": "Often"}, ("-9",)))
                frame = again.app.session.df.copy()
                frame["q3"] = frame["q1"] + frame["q2"]
                again.app.session.add_prepared_columns(frame, [])
                self.assertEqual(again.app.session.variables["q1"].label, "Fictional item one")
                dataset = again.app.projects.dataset_id
                self.assertEqual(again.app.projects.project.variable_metadata(dataset)["q1"]
                                 ["label"], "Fictional item one", "saved with the new version")
            finally:
                again.close()


# ============================================================= codebook
class CodebookTests(unittest.TestCase):
    def test_the_master_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            session = master_session(Path(folder), adversarial=False)
            book = codebook_of(session)
        self.assertEqual((book.rows, book.columns), (180, 98))
        self.assertEqual(book.sha256, session.dataset_sha256())
        cope = book.variable("SYN_COPE_01")
        self.assertEqual((cope.n_missing, cope.n_valid, cope.level), (3, 177, "scale"))
        self.assertEqual(book.variable("SYN_SUP_03").n_missing, 2)
        age = book.variable("age_years")
        self.assertEqual((age.minimum, age.maximum), (18.0, 30.0))
        self.assertEqual(book.variable("participant_code").level, "id")
        self.assertEqual(book.variable("participant_code").valid, "180 distinct values",
                         "no participant code is listed")

    def test_derived_variables_scales_reverse_items_and_missing_codes(self):
        from data_preparation import history_record, mark_missing, reverse_item, score_scale

        with tempfile.TemporaryDirectory() as folder:
            session = master_session(Path(folder), adversarial=False)
            frame = session.df.copy()
            frame.loc[0, "SYN_WELL_01"] = -9
            steps = []
            for apply in (lambda f: reverse_item(f, "SYN_LON_02", "SYN_LON_02_rev", 1, 4),
                          lambda f: score_scale(f, ["SYN_LON_01", "SYN_LON_02_rev", "SYN_LON_03"],
                                                "LON3_mean", "mean", 2),
                          lambda f: mark_missing(f, "SYN_WELL_01", "SYN_WELL_01_clean", ["-9"])):
                result = apply(frame)
                frame = result.frame
                steps.append(history_record(result.step))
            session.add_prepared_columns(frame, steps)
            book = codebook_of(session)
        reverse = book.variable("SYN_LON_02_rev")
        self.assertTrue(reverse.reverse)
        self.assertEqual(reverse.derived, "reverse-keyed SYN_LON_02: 1 + 4 − SYN_LON_02")
        score = next(s for s in book.scales if s["scale"] == "LON3_mean")
        self.assertEqual(score["items"], ["SYN_LON_01", "SYN_LON_02_rev", "SYN_LON_03"])
        self.assertEqual(score["reverse_items"], ["SYN_LON_02_rev"])
        self.assertEqual(score["rule"], "mean; at least 2 of 3 answered")
        well = book.variable("SYN_WELL_01")
        self.assertEqual((well.missing_codes, well.n_user_missing), (["-9"], 1))
        self.assertEqual([h["kind"] for h in book.history],
                         ["reverse_item", "score_scale", "mark_missing"])

    def test_a_questionnaire_gives_labels_codes_reverse_keys_and_scales(self):
        from survey_storage import create_survey

        with tempfile.TemporaryDirectory() as folder:
            survey = create_survey(Path(folder), "Fictional scale", "", [
                {"key": "i1", "prompt": "First fictional item", "kind": "likert5",
                 "scale_id": "FS", "min_label": "Never", "max_label": "Always"},
                {"key": "i2", "prompt": "Second fictional item", "kind": "rating_scale",
                 "scale_id": "FS", "reverse_scored": True,
                 "value_labels": {"0": "No", "1": "Yes"}, "missing_options": {"DK": "Don't know"}}])
            session = ResearchSession()
            session.set_dataset(pd.DataFrame({"i1": [1.0, 5.0], "i2": [0.0, None],
                                              "i2__missing_reason": [None, "DK"]}), "answers",
                                origin="survey", survey_id=survey.survey_id)
            session.questionnaire_loader = lambda sid: survey
            book = codebook_of(session)
        i1, i2, reason = (book.variable(n) for n in ("i1", "i2", "i2__missing_reason"))
        self.assertEqual((i1.label, i1.value_labels), ("First fictional item",
                                                       {"1": "Never", "5": "Always"}))
        self.assertTrue(i2.reverse)
        self.assertEqual(reason.missing_codes, ["DK"])
        self.assertEqual(book.scales[0]["items"], ["i1", "i2"])
        self.assertEqual(book.scales[0]["reverse_items"], ["i2"])


# ======================================================= results, bundle
SYNTAX_ANALYSES = (
    ("correlation", {"x": "SYN_LON_TOTAL", "y": "SYN_WELL_0_100"}, {"method": "pearson"},
     {"pearson": True}),
    ("regression", {"outcome": "SYN_WELL_0_100", "predictors": ["SYN_LON_TOTAL", "SYN_SUP_MEAN"]},
     {"hc3": "no"}, {"model": True}),
    ("groups", {"outcome": "SYN_WELL_0_100", "group": "employed_code"}, {"method": "welch"},
     {"independent": True, "assumptions": True}),
    ("omnibus", {"outcome": "SYN_WELL_0_100", "group": "sex_code"}, {"method": "anova"},
     {"independent": True, "assumptions": True}),
    ("omnibus", {"outcome": "SYN_SUP_MEAN", "group": "sex_code"}, {"method": "welch"},
     {"independent": True, "assumptions": True}),
    ("correlation", {"x": "SYN_LON_TOTAL", "y": "SYN_COPE_DIM1_MEAN"}, {"method": "spearman"}, {}),
)


def analysed(folder: Path) -> ResearchSession:
    from workspace_methods import run_method

    session = master_session(folder, adversarial=False)
    for key, roles, options, confirms in SYNTAX_ANALYSES:
        run = run_method(key, session, roles, options, confirms)
        session.add_result(run, method=key, roles=roles, options=options, confirms=confirms)
    return session


class ResultsAndBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name)
        cls.session = analysed(cls.folder / "fixture")
        cls.book = codebook_of(cls.session)
        from chart_views import create_state

        groups = cls.session.results[2]          # a Chart Studio view of the Welch result
        groups.charts = create_state(method=groups.method, roles=groups.roles,
                                     options=groups.options, frame=cls.session.df,
                                     level=cls.session.level)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_results_workbook_sheets_engine_values_and_provenance(self):
        from openpyxl import load_workbook

        path = self.folder / "results.xlsx"
        facts = eb.export_results(path, self.session.results)
        book = load_workbook(path)
        self.assertEqual(book.sheetnames[0], "Results")
        self.assertEqual(book.sheetnames[-1], "Provenance")
        self.assertEqual(len(book.sheetnames), 2 + len(SYNTAX_ANALYSES))
        self.assertEqual(facts["verified"]["sheets"], book.sheetnames)
        correlation = self.session.results[0].run.result
        rows = list(book[book.sheetnames[1]].iter_rows(values_only=True))
        values = {r[0]: r[1] for r in rows if r and r[0]}
        self.assertEqual(values["coefficient"], correlation.coefficient, "unrounded, a number")
        self.assertEqual(values["p_value"], correlation.p_value)
        self.assertNotIn("x_values", values, "no participant values")
        provenance = list(book["Provenance"].iter_rows(values_only=True))
        header = next(i for i, r in enumerate(provenance) if r and r[0] == "Result")
        first = dict(zip(eb.PROVENANCE_COLUMNS, provenance[header + 1]))
        self.assertEqual(first["Method key"], "correlation")
        self.assertEqual(json.loads(first["Options (JSON)"]), {"method": "pearson"})
        self.assertEqual(first["Dataset SHA-256"], self.session.dataset_sha256())

    def test_the_bundle_manifest_files_and_checksums(self):
        path = self.folder / "bundle.zip"
        facts = eb.write_bundle(path, df=self.session.df, codebook=self.book,
                                entries=self.session.results, app={"version": "test"},
                                libraries={"pyreadstat": "1.3.7"})
        self.assertEqual(facts["verified"]["rows"], 180)
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            names = set(archive.namelist())
            for entry in manifest["files"]:
                self.assertEqual(eb.hashlib.sha256(archive.read(entry["path"])).hexdigest(),
                                 entry["sha256"])
        self.assertEqual(manifest["dataset"]["sha256"], self.session.dataset_sha256())
        self.assertEqual(manifest["dataset"]["rows"], 180)
        for name in ("data/synthetic_master_research_n180.csv",
                     "data/synthetic_master_research_n180.xlsx",
                     "data/synthetic_master_research_n180.sav", "codebook/codebook.json",
                     "results/results.xlsx", "figures/R1_correlation.png",
                     "figures/R3_groups_view.svg"):
            self.assertIn(name, names)
        with zipfile.ZipFile(path) as archive:
            svg = archive.read("figures/R3_groups_view.svg").decode("utf-8")
        self.assertIn("<svg", svg)
        self.assertIn("<desc>", svg, "the SVG carries its text alternative")
        analyses = manifest["analyses"]
        self.assertEqual([a["method"] for a in analyses], [a[0] for a in SYNTAX_ANALYSES])
        self.assertEqual(analyses[0]["options"], {"method": "pearson"})
        self.assertEqual(analyses[5]["seeds"]["engine"]["seed"], 2026, "Spearman permutation")
        self.assertIsNone(analyses[5]["syntax"]["r"], "no unverified syntax")
        self.assertEqual(sorted(n for n in names if n.startswith("syntax/")),
                         [f"syntax/R{i}_{a[0]}.R" for i, a in enumerate(SYNTAX_ANALYSES[:5], 1)])
        self.assertFalse(manifest["privacy"]["uploaded"])
        self.assertEqual(manifest["privacy"]["possibly_identifying_columns"][0]["variable"],
                         "participant_code")

    @unittest.skipUnless(shutil.which("Rscript"), "R is not installed here")
    def test_the_r_syntax_reproduces_the_engine(self):
        path = self.folder / "r_bundle.zip"
        eb.write_bundle(path, df=self.session.df, codebook=self.book,
                        entries=self.session.results, app={"version": "test"})
        unpacked = self.folder / "r_bundle"
        with zipfile.ZipFile(path) as archive:
            archive.extractall(unpacked)
            manifest = json.loads(archive.read("manifest.json"))
        checked = 0
        for analysis in manifest["analyses"]:
            script = analysis["syntax"]["r"]
            if script is None:
                continue
            run = subprocess.run(["Rscript", str(unpacked / script), str(unpacked)],
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            found = dict(re.findall(r"^(\S+) = (\S+)$", run.stdout, flags=re.M))
            for name, expected in analysis["syntax"]["check_values"].items():
                self.assertTrue(math.isclose(float(found[name]), float(expected),
                                             rel_tol=1e-9, abs_tol=1e-12),
                                (script, name, found.get(name), expected))
                checked += 1
        # r, p, n and the CI; R², adjusted R², F, n and b, SE, p of 3 terms; t, df, p;
        # F, df1, df2, p twice.
        self.assertEqual(checked, 5 + 13 + 3 + 4 + 4)

    def test_engine_seeds_named_in_the_manifest_are_the_engine_s(self):
        source = (ROOT / "correlation.py").read_text(encoding="utf-8")
        self.assertIn("n_resamples=1999", source)
        self.assertIn("default_rng(2026)", source)
        factor = (ROOT / "factor_exploration.py").read_text(encoding="utf-8")
        self.assertIn("simulations=150, seed=20261103", factor)


# ========================================================= atomic save
class AtomicSaveTests(unittest.TestCase):
    def test_a_failed_write_or_check_leaves_the_destination_as_it_was(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "kept.csv"
            target.write_text("old content", encoding="utf-8")

            def broken(temporary):
                temporary.write_text("half", encoding="utf-8")
                raise OSError("disk full")

            with self.assertRaises(OSError):
                de.save_atomic(target, broken, lambda t, f: {})
            self.assertEqual(target.read_text(encoding="utf-8"), "old content")

            def wrong(temporary, facts):
                raise de.VerificationFailed("not what was written")

            with self.assertRaises(de.VerificationFailed):
                de.save_atomic(target, lambda t: t.write_text("new", encoding="utf-8") and {},
                               wrong)
            self.assertEqual(target.read_text(encoding="utf-8"), "old content")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["kept.csv"],
                             "no partial file is left")


# ======================================================== participants
class SensitivityTests(unittest.TestCase):
    def test_direct_identifiers_codes_and_free_text_are_flagged(self):
        frame = pd.DataFrame({
            "Vārds": ["Anna", "Jānis"], "e-mail": ["x", "y"], "Телефон": ["1", "2"],
            "contact": ["anna@example.invalid", "janis@example.invalid"],
            "pk": ["010101-12345", "020202-23456"], "dzimšanas datums": ["2000", "2001"],
            "answer": ["A long fictional free-text answer that goes on for a while " * 2,
                       "Another long fictional free-text answer, quite different " * 2],
            "score": [1.0, 2.0], "visit": ["2024-01-02", "2024-01-03"]})
        found = {c.name: c.reason for c in de.sensitive_columns(frame)}
        self.assertEqual(found, {"Vārds": "direct", "e-mail": "direct", "Телефон": "direct",
                                 "contact": "direct", "pk": "direct",
                                 "dzimšanas datums": "direct", "answer": "free_text"})
        with tempfile.TemporaryDirectory() as folder:
            session = master_session(Path(folder), adversarial=False)
            flagged = de.sensitive_columns(session.df, codebook_of(session))
        self.assertEqual([(c.name, c.reason) for c in flagged],
                         [("participant_code", "identifier")])


# ========================================================== preferences
class PreferenceTests(unittest.TestCase):
    def test_export_choices_are_remembered_and_survive_other_saves(self):
        from app_preferences import (AppPreferences, export_preferences, load_preferences,
                                     remember_export, save_preferences)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            self.assertEqual(export_preferences(path), {})
            remember_export({"formats": {"data": "sav", "nowhere": "x"}, "csv_layout": "semicolon",
                             "csv_bom": False}, path)
            remember_export({"formats": {"results": "bundle"}}, path)
            save_preferences(AppPreferences(language="lv"), path)      # the classic interface
            self.assertEqual(export_preferences(path), {
                "formats": {"data": "sav", "results": "bundle"}, "csv_layout": "semicolon",
                "csv_bom": False})
            self.assertEqual(load_preferences(path).language, "lv")
            remember_export({"formats": {"data": "exe"}, "csv_layout": "tab"}, path)
            self.assertEqual(export_preferences(path)["formats"]["data"], "sav")


if __name__ == "__main__":
    unittest.main()
