"""Offline checks for the descriptive chart generator."""

import unittest
import pandas as pd
from descriptive_charts import make_descriptive_chart


PNG_SIGNATURE = b"\\x89PNG\\r\\n\\x1a\\n"


class DescriptiveChartTests(unittest.TestCase):
    def test_histogram_bytes(self):
        values = pd.Series([22, 25, 31, 35, None], name="age")
        png = make_descriptive_chart(values, "scale")
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_category_chart_bytes(self):
        values = pd.Series(["A", "B", "A", None], name="group")
        png = make_descriptive_chart(values, "nominal")
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))

    def test_reject_identifier(self):
        with self.assertRaises(ValueError):
            make_descriptive_chart(pd.Series([1, 2], name="participant_id"), "scale")

    def test_reject_incorrect_numeric_values(self):
        with self.assertRaises(ValueError):
            make_descriptive_chart(pd.Series(["yes", "no"], name="response"), "scale")


if __name__ == "__main__":
    unittest.main()
