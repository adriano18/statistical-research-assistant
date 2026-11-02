"""Short paired summaries and ignored-folder local export tests."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd

from paired_analysis import analyze_paired
from paired_presentation import (
    paired_main_result, paired_descriptives, paired_interpretation
)
from paired_reporting import format_paired_report
from paired_charts import make_paired_chart
from report_export import save_apa_txt, save_figure_png


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_paired.csv"


class PairedPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = pd.read_csv(SAMPLE)
        cls.result = analyze_paired(
            data, "before_score", "after_score", "paired_t", "scale", True, True
        )

    def test_main_descriptives_and_interpretation(self):
        self.assertIn("Paired t-test", paired_main_result(self.result))
        self.assertIn("N = 22", paired_main_result(self.result))
        self.assertIn("Before:", paired_descriptives(self.result))
        self.assertIn("After:", paired_descriptives(self.result))
        self.assertIn("decrease", paired_interpretation(self.result))

    def test_save_png_and_report_locally(self):
        report = format_paired_report(self.result)
        png = make_paired_chart(self.result)
        with TemporaryDirectory() as directory:
            with patch("report_export.REPORTS", Path(directory)):
                text_path = save_apa_txt(report)
                png_path = save_figure_png(png)
                self.assertIn("paired-samples", text_path.read_text("utf-8"))
                self.assertTrue(
                    png_path.read_bytes().startswith(
                        bytes.fromhex("89504e470d0a1a0a")
                    )
                )

    def test_reject_empty_and_path_traversal(self):
        with TemporaryDirectory() as directory:
            with patch("report_export.REPORTS", Path(directory)):
                with self.assertRaisesRegex(ValueError, "Run an analysis"):
                    save_apa_txt("")
                with self.assertRaisesRegex(ValueError, "valid PNG"):
                    save_figure_png(b"not a picture")
                with self.assertRaisesRegex(ValueError, "filename"):
                    save_apa_txt("hello", "../leak.txt")


if __name__ == "__main__":
    unittest.main()
