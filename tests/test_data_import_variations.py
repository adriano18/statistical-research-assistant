"""Synthetic questionnaire-export compatibility and rejection matrix.

No real participant records. Every fixture is created in a temporary folder.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from data_loader import (
    DEFAULT_MISSING, ImportOptions, load_dataset, load_dataset_with_report,
    workbook_sheets,
)


class SurveyImportVariationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def csv(self, name, text, encoding="utf-8"):
        path = self.folder / name
        path.write_text(text, encoding=encoding)
        return path

    def excel(self, name, **sheets):
        path = self.folder / name
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for title, frame in sheets.items():
                frame.to_excel(writer, sheet_name=title, index=False)
        return path

    def test_common_delimiters_unicode_quotes_and_multiline_answers(self):
        cases = (
            ("comma", "id,q1,comment\n001,3,\"good, clear\"\n002,5,ok\n", ","),
            ("semicolon", "id;q1;comment\n001;3;\"labi; ļoti labi\"\n002;5;ok\n", ";"),
            ("tab", "id\tq1\tcomment\n001\t3\tХорошо\n002\t5\tЛаби\n", "\t"),
            ("pipe", "id|q1|comment\n001|3|\"clear | fine\"\n002|5|fine\n", "|"),
        )
        for name, data, delimiter in cases:
            with self.subTest(format=name):
                ext = ".tsv" if name == "tab" else ".csv"
                df, report = load_dataset_with_report(self.csv(name + ext, data))
                self.assertEqual(df.shape, (2, 3))
                self.assertEqual(report.separator, delimiter)
                self.assertEqual(df["id"].tolist(), ["001", "002"])
                self.assertEqual(df["q1"].tolist(), [3.0, 5.0])
                self.assertEqual(df["comment"].iloc[0].split()[0],
                                 {"comma": "good,", "semicolon": "labi;",
                                  "tab": "Хорошо", "pipe": "clear"}[name])

    def test_utf8_bom_utf16_and_legacy_cyrillic_override(self):
        for encoding in ("utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                path = self.csv(encoding + ".csv", "question;score\nПривет;2\n", encoding)
                df, report = load_dataset_with_report(path)
                self.assertEqual(df["question"].iloc[0], "Привет")
                self.assertEqual(df["score"].iloc[0], 2.0)
                self.assertIn(report.encoding, ("utf-8-sig", "utf-16"))
        cyrillic = self.csv(
            "cyrillic.csv", "ответ;оценка\nотлично;5\n", encoding="cp1251"
        )
        df, report = load_dataset_with_report(
            cyrillic, ImportOptions(encoding="cp1251")
        )
        self.assertEqual(df["ответ"].iloc[0], "отлично")
        self.assertTrue(any("Legacy encoding" in note for note in report.warnings))

    def test_multi_sheet_excel_and_header_after_title_row(self):
        path = self.folder / "forms.xlsx"
        book = Workbook()
        intro = book.active
        intro.title = "Instructions"
        intro.append(["Not response data"])
        results = book.create_sheet("Survey responses")
        results.merge_cells("A1:C1")
        results["A1"] = "Fictional questionnaire; headers begin below"
        results["A1"].font = Font(bold=True)
        results.append(["Respondent ID", "Satisfaction", "Group"])
        results.append(["001", 4, "A"])
        results.append(["002", 5, "B"])
        results["B3"].fill = PatternFill("solid", fgColor="FFFACD")
        book.save(path)
        with self.assertRaises(ValueError):
            load_dataset(path)  # First sheet is an instruction sheet, not data.
        self.assertEqual(workbook_sheets(path), ["Instructions", "Survey responses"])
        df, report = load_dataset_with_report(
            path, ImportOptions(sheet="Survey responses", header_row=2)
        )
        self.assertEqual(df["Satisfaction"].tolist(), [4.0, 5.0])
        self.assertEqual(df["Respondent ID"].tolist(), ["001", "002"])
        self.assertEqual(report.sheet, "Survey responses")
        self.assertTrue(any("Header row 2" in note for note in report.warnings))

    def test_rows_from_spreadsheet_with_title_preamble_and_missing_cells(self):
        path = self.csv(
            "manual.csv",
            "Student survey generated on campus\n"
            "id;score;group\n"
            "001;1;A\n"
            "002;3\n"
            "\n"
            "003;5;B\n",
        )
        frame, report = load_dataset_with_report(
            path, ImportOptions(header_row=2)
        )
        self.assertEqual(frame.shape, (3, 3))
        self.assertTrue(pd.isna(frame["group"].iloc[1]))
        self.assertTrue(any("short CSV row" in n for n in report.warnings))
        self.assertTrue(any("blank row" in n for n in report.warnings))

    def test_duplicated_or_blank_column_headers_rejected(self):
        cases = (
            ("score;score\n1;2\n", "Duplicate"),
            ("score; score \n1;2\n", "Duplicate"),
            ("score;\n1;2\n", "blank"),
        )
        for text, problem in cases:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, problem):
                    load_dataset(self.csv("broken.csv", text))

    def test_malformed_rows_and_broken_quotes_rejected(self):
        for text in (
            "a,b\n1,2,unexpected\n",
            'a,b\n"unterminated,2\n',
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    load_dataset(self.csv("broken.csv", text))

    def test_auto_and_explicit_decimal_notation(self):
        eu = self.csv("eu.csv", "q1;q2\n1,25;1.234,5\n2,75;2.345,5\n")
        df, report = load_dataset_with_report(eu)
        self.assertEqual(df["q1"].tolist(), [1.25, 2.75])
        self.assertEqual(df["q2"].tolist(), [1234.5, 2345.5])
        self.assertIn("q1", report.converted_columns)
        ambiguous = self.csv("ambiguous.csv", "score;group\n1,234;A\n2,345;B\n")
        df, report = load_dataset_with_report(ambiguous)
        self.assertFalse(pd.api.types.is_numeric_dtype(df["score"]))
        self.assertTrue(any("ambiguous" in w for w in report.warnings))
        df_comma, _ = load_dataset_with_report(
            ambiguous, ImportOptions(decimal="comma")
        )
        self.assertEqual(df_comma["score"].tolist(), [1.234, 2.345])
        df_dot, _ = load_dataset_with_report(
            ambiguous, ImportOptions(decimal="dot")
        )
        self.assertEqual(df_dot["score"].tolist(), [1234.0, 2345.0])

    def test_mixed_text_preserved_and_no_silent_recode(self):
        path = self.csv(
            "mixed.csv",
            "student_code;rating;condition\n"
            "001;1;Yes\n002;uncertain;No\n003;3;NA\n",
        )
        df, report = load_dataset_with_report(path)
        self.assertEqual(df["student_code"].tolist(), ["001", "002", "003"])
        self.assertEqual(df["rating"].iloc[1], "uncertain")
        self.assertTrue(pd.isna(df["condition"].iloc[2]))
        self.assertTrue(any("mixed or ambiguous" in w for w in report.warnings))
        self.assertTrue(any("converted to missing" in w for w in report.warnings))

    def test_question_text_headers_and_quoted_free_text(self):
        path = self.csv(
            "questionnaire.csv",
            '"Respondent","Do you agree with this statement?","Comment"\n'
            '"P1","Strongly agree","Line one\nLine two, with comma"\n'
            '"P2","Disagree","safe text"\n',
        )
        df, report = load_dataset_with_report(path)
        self.assertEqual(df.shape, (2, 3))
        self.assertEqual(df["Comment"].iloc[0], "Line one\nLine two, with comma")
        self.assertFalse(pd.api.types.is_numeric_dtype(
            df["Do you agree with this statement?"]
        ))
        self.assertTrue(any("No numeric" in w for w in report.warnings))

    def test_formulas_remain_unexecuted_and_malicious_text_is_not_code(self):
        path = self.csv(
            "untrusted.csv",
            'participant,q1,comment\n'
            'P1,3,"=HYPERLINK(""https://example.invalid"",""click"")"\n',
        )
        df = load_dataset(path)
        self.assertIn("HYPERLINK", df["comment"].iloc[0])
        self.assertEqual(df["q1"].iloc[0], 3.0)

    def test_excel_formula_is_not_executed_and_is_reported(self):
        path = self.folder / "formula_export.xlsx"
        book = Workbook()
        sheet = book.active
        sheet.append(["score", "date_code"])
        sheet.append(["=SUM(2,3)", "P1"])
        sheet.append([5, "P2"])
        book.save(path)
        df, report = load_dataset_with_report(path)
        self.assertTrue(pd.isna(df["score"].iloc[0]))
        self.assertEqual(df["score"].iloc[1], 5.0)
        self.assertTrue(any("NOT executed" in note for note in report.warnings))

    def test_scientific_number_format_and_percent_strings(self):
        path = self.csv(
            "scientific.csv", "value;share\n1e-3;25%\n2E+4;50%\n"
        )
        df, report = load_dataset_with_report(path)
        self.assertEqual(df["value"].tolist(), [0.001, 20000.0])
        self.assertEqual(df["share"].tolist(), ["25%", "50%"])
        self.assertTrue(any("percentages" in note for note in report.warnings))

    def test_missing_markers_are_configurable(self):
        path = self.csv("missing.csv", "a,b\nDK,2\nN/A,4\n")
        df, _ = load_dataset_with_report(
            path, ImportOptions(missing_tokens=("", "DK"))
        )
        self.assertTrue(pd.isna(df["a"].iloc[0]))
        self.assertEqual(df["a"].iloc[1], "N/A")
        df_default, _ = load_dataset_with_report(path)
        self.assertEqual(df_default["a"].iloc[0], "DK")
        self.assertTrue(pd.isna(df_default["a"].iloc[1]))
        self.assertIn("NA", DEFAULT_MISSING)

    def test_empty_wrong_extension_invalid_options_and_header_row(self):
        empty = self.csv("empty.csv", "")
        with self.assertRaisesRegex(ValueError, "empty"):
            load_dataset(empty)
        text = self.csv("document.txt", "a,b\n1,2\n")
        with self.assertRaisesRegex(ValueError, "Supported"):
            load_dataset(text)
        data = self.csv("valid.csv", "a,b\n1,2\n")
        for options in (
            ImportOptions(header_row=0), ImportOptions(header_row=101),
            ImportOptions(decimal="unspecified"),
            ImportOptions(encoding="utf-77"),
            ImportOptions(separator="slash"),
        ):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    load_dataset_with_report(data, options)
        with self.assertRaisesRegex(ValueError, "Header row"):
            load_dataset_with_report(data, ImportOptions(header_row=3))

    def test_explicit_error_when_no_respondent_rows(self):
        path = self.csv("no_data.csv", "q1;q2\n")
        with self.assertRaisesRegex(ValueError, "No respondent rows"):
            load_dataset(path)

    def test_no_correlation_between_reading_and_original_file(self):
        path = self.csv("source.csv", "score;group\n1;A\n2;B\n")
        before = path.read_bytes()
        df, _ = load_dataset_with_report(path)
        df.loc[0, "score"] = 999
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
