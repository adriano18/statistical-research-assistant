"""Regression tests for non-destructive questionnaire transformations."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

from data_preparation import (
    mark_missing, recode_column, reverse_item, score_scale,
    save_prepared_dataset,
)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame({
            "q1": [1, 2, 3, 5, 99, np.nan],
            "q2": [5, 4, 3, 1, 2, 4],
            "q3": [2, 2, 4, 5, 3, 5],
            "choice": ["Yes", "No", "Maybe", "Yes", "No", None],
        })
        self.original = self.source.copy(deep=True)

    def test_missing_codes_create_new_column(self):
        result = mark_missing(self.source, "q1", "q1_clean", ["99"])
        self.assertTrue(np.isnan(result.frame.loc[4, "q1_clean"]))
        self.assertEqual(result.frame.loc[4, "q1"], 99)
        self.assertEqual(result.frame["q1_clean"].notna().sum(), 4)
        pd.testing.assert_frame_equal(self.original, self.source)

    def test_reverse_scoring_and_invalid_range(self):
        cleaned = mark_missing(self.source, "q1", "q1_clean", ["99"])
        reversed_result = reverse_item(
            cleaned.frame, "q1_clean", "q1_reverse", 1, 5
        )
        self.assertEqual(reversed_result.frame.loc[0, "q1_reverse"], 5)
        self.assertEqual(reversed_result.frame.loc[3, "q1_reverse"], 1)
        self.assertTrue(np.isnan(reversed_result.frame.loc[4, "q1_reverse"]))
        with self.assertRaisesRegex(ValueError, "outside"):
            reverse_item(self.source, "q1", "bad_reverse", 1, 5)

    def test_recoding_undocumented_values_is_explicit(self):
        mapped = recode_column(
            self.source, "choice", "choice_code",
            {"Yes": "1", "No": "0"}, unmapped="missing",
        )
        self.assertEqual(mapped.frame["choice_code"].iloc[0], 1)
        self.assertEqual(mapped.frame["choice_code"].iloc[1], 0)
        self.assertTrue(pd.isna(mapped.frame["choice_code"].iloc[2]))
        self.assertEqual(mapped.frame["choice"].iloc[2], "Maybe")
        self.assertIn("1 unmapped", mapped.message)
        kept = recode_column(
            self.source, "choice", "choice_other",
            {"Yes": "1"}, unmapped="keep",
        )
        self.assertEqual(kept.frame.loc[2, "choice_other"], "Maybe")

    def test_scale_mean_minimum_answered(self):
        clean = mark_missing(self.source, "q1", "q1_clean", ["99"])
        result = score_scale(
            clean.frame, ["q1_clean", "q2", "q3"], "stress_mean",
            "mean", 3,
        )
        self.assertEqual(result.frame.loc[0, "stress_mean"], 8 / 3)
        self.assertTrue(np.isnan(result.frame.loc[4, "stress_mean"]))
        self.assertTrue(np.isnan(result.frame.loc[5, "stress_mean"]))
        permissive = score_scale(
            clean.frame, ["q1_clean", "q2", "q3"],
            "stress_partial_mean", "mean", 2,
        )
        self.assertEqual(permissive.frame.loc[4, "stress_partial_mean"], 2.5)
        self.assertEqual(permissive.frame["stress_partial_mean"].notna().sum(), 6)

    def test_incomplete_sum_is_refused(self):
        with self.assertRaisesRegex(ValueError, "ALL items"):
            score_scale(
                self.source, ["q1", "q2", "q3"],
                "bad_sum", "sum", 2,
            )

    def test_cannot_overwrite_existing_columns(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            mark_missing(self.source, "q1", "q2", ["99"])
        with self.assertRaisesRegex(ValueError, "letters"):
            recode_column(self.source, "choice", "../bad", {"Yes": "1"})

    def test_bad_recoding_or_non_numeric_scale_rejected(self):
        with self.assertRaisesRegex(ValueError, "1–40"):
            recode_column(self.source, "choice", "bad", {})
        with self.assertRaisesRegex(ValueError, "numeric"):
            score_scale(
                self.source, ["choice", "q2"], "invalid", "mean", 2
            )

    def test_csv_and_recipe_are_saved_but_original_is_not_overwritten(self):
        completed = mark_missing(self.source, "q1", "q1_clean", ["99"])
        with TemporaryDirectory() as folder:
            input_path = Path(folder) / "input.csv"
            input_path.write_text("only,original\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "original"):
                save_prepared_dataset(
                    completed.frame, [completed.step],
                    input_path, source_file=input_path
                )
            output = Path(folder) / "prepared.csv"
            csv, recipe = save_prepared_dataset(
                completed.frame, [completed.step],
                output, source_file=input_path,
            )
            self.assertEqual(csv, output)
            self.assertEqual(recipe, Path(folder) / "prepared_steps.json")
            self.assertIn("q1_clean", csv.read_text(encoding="utf-8-sig"))
            self.assertEqual(
                json.loads(recipe.read_text(encoding="utf-8"))["steps"][0]["type"],
                "missing",
            )
            self.assertEqual(input_path.read_text(encoding="utf-8"), "only,original\n")
        pd.testing.assert_frame_equal(self.original, self.source)


if __name__ == "__main__":
    unittest.main()
