"""Offline tests for SPSS-style Explore and local export."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from explore_analysis import (
    explore_quantitative, format_explore_report, make_explore_chart
)
from output_workspace import AnalysisOutput, save_selected_output


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_three_groups.csv"


class ExploreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = pd.read_csv(SAMPLE)

    def test_ungrouped_boxplot_and_shapiro(self):
        result = explore_quantitative(self.data, "score")
        self.assertEqual(result.n_complete, 36)
        self.assertEqual(result.labels, ["All observations"])
        self.assertIsNotNone(result.shapiro_p)
        self.assertIsNone(result.levene_p)
        self.assertTrue(0 <= result.shapiro_p <= 1)
        self.assertIn("Shapiro", format_explore_report(result))

    def test_grouped_checks_and_png(self):
        result = explore_quantitative(self.data, "score", "group")
        self.assertEqual(result.labels, ["A", "B", "C"])
        self.assertEqual([len(a) for a in result.samples], [12, 12, 12])
        self.assertIsNotNone(result.levene_p)
        self.assertTrue(0 <= result.levene_p <= 1)
        img = make_explore_chart(result)
        self.assertTrue(img.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(img), 1000)

    def test_invalid_variables_and_design(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            explore_quantitative(self.data, "missing")
        with self.assertRaisesRegex(ValueError, "distinct"):
            explore_quantitative(self.data, "score", "score")
        data = self.data.copy()
        data["participant_id"] = range(1, len(data) + 1)
        with self.assertRaisesRegex(ValueError, "Identifiers"):
            explore_quantitative(data, "participant_id")
        data["score"] = data["score"].astype(object)
        data.loc[0, "score"] = "invalid"
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            explore_quantitative(data, "score")

    def test_missing_data_does_not_create_values(self):
        df = self.data.copy()
        df.loc[0, "score"] = np.nan
        result = explore_quantitative(df, "score", "group")
        self.assertEqual(result.n_complete, 35)
        self.assertTrue(any("Excluded 1" in text for text in result.warnings))


class OutputWorkspaceTests(unittest.TestCase):
    def test_save_report_and_image_as_explicit_paths(self):
        with TemporaryDirectory() as folder:
            txt = Path(folder) / "study_report.txt"
            png = Path(folder) / "study_figure.png"
            output = AnalysisOutput(
                title="Test", report="χ²(1) = 6.67",
                png=bytes.fromhex("89504e470d0a1a0a") + b"test-content"
            )
            self.assertEqual(save_selected_output(txt, output, "text"), txt)
            self.assertIn("χ²", txt.read_text(encoding="utf-8"))
            self.assertEqual(save_selected_output(png, output, "image"), png)
            self.assertEqual(png.read_bytes(), output.png)

    def test_reject_mismatch_missing_content(self):
        with TemporaryDirectory() as folder:
            output = AnalysisOutput(title="Empty", report="", png=None)
            with self.assertRaisesRegex(ValueError, "No report"):
                save_selected_output(Path(folder) / "a.txt", output, "text")
            with self.assertRaisesRegex(ValueError, "No valid PNG"):
                save_selected_output(Path(folder) / "a.png", output, "image")
            with self.assertRaisesRegex(ValueError, "ending in"):
                save_selected_output(Path(folder) / "a.csv", output, "text")


if __name__ == "__main__":
    unittest.main()
