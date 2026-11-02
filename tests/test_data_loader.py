"""Offline tests for the first research data inspection module."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pandas as pd

from data_loader import load_dataset, variable_overview


class DataLoaderTests(unittest.TestCase):
    def test_csv_with_semicolon_separator(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "sample.csv"
            path.write_text("group;score\nA;3\nB;\n", encoding="utf-8")
            df = load_dataset(path)
            self.assertEqual(df.shape, (2, 2))
            self.assertEqual(int(df["score"].isna().sum()), 1)

    def test_excel_first_sheet(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "sample.xlsx"
            pd.DataFrame({"score": [1, 2]}).to_excel(path, index=False)
            df = load_dataset(path)
            self.assertEqual(df["score"].tolist(), [1, 2])

    def test_variable_overview(self):
        df = pd.DataFrame({"group": ["A", "B"], "score": [3, None]})
        overview = variable_overview(df)
        self.assertEqual(overview.loc[overview["variable"] == "score", "missing"].iloc[0], 1)
        self.assertIn("verify scale", overview.iloc[0]["type_hint"])

    def test_invalid_extension(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "notes.txt"
            path.write_text("a,b\n1,2", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_dataset(path)


if __name__ == "__main__":
    unittest.main()
