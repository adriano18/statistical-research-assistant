"""Regress the complete file-selection -> dataframe -> real analysis flow.

The datasets are synthetic and generated independently in temporary folders.
The test verifies that changing *imported* data changes calculated statistics.
"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import pandas as pd

from correlation import analyze_correlation
from data_loader import load_dataset_with_report
from import_workflow import (
    MAX_TRANSFER_BYTES, import_picked_files, SUPPORTED_EXTENSIONS,
)


class FilePickerRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_csv_path_loaded_and_reported(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "my_questionnaire.csv"
            path.write_text(
                "participant;rating;group\n001;4;A\n002;5;B\n",
                encoding="utf-8",
            )
            imported = []
            async def read_path(name):
                df, diagnostic = load_dataset_with_report(name)
                imported.append((df, diagnostic))
                return True

            async def read_bytes(data, name):
                self.fail("Desktop path should not use browser transfer bytes.")

            result = await import_picked_files(
                [SimpleNamespace(path=str(path), name=path.name, bytes=None)],
                import_path=read_path, import_bytes=read_bytes,
            )
            self.assertTrue(result.successful)
            self.assertIn("my_questionnaire.csv", result.message)
            self.assertEqual(imported[0][0].shape, (2, 3))
            self.assertEqual(imported[0][0]["rating"].tolist(), [4.0, 5.0])
            self.assertEqual(imported[0][0]["participant"].tolist(), ["001", "002"])

    async def test_real_excel_path_loaded_not_a_hardcoded_demo(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "edited_survey.xlsx"
            pd.DataFrame({
                "question": ["P1", "P2", "P3"],
                "score": [17, 29, 43],
                "group": ["A", "A", "B"],
            }).to_excel(path, index=False)
            loaded = []

            async def read_path(name):
                frame, report = load_dataset_with_report(name)
                loaded.append(frame)
                return True

            async def not_bytes(contents, name):
                self.fail("Expected local path instead of transfer bytes.")

            selection = await import_picked_files(
                [SimpleNamespace(name=path.name, path=str(path))],
                import_path=read_path, import_bytes=not_bytes,
            )
            self.assertTrue(selection.successful)
            self.assertEqual(loaded[0]["score"].tolist(), [17., 29., 43.])

    async def test_browser_bytes_no_path_can_be_read_with_same_loader(self):
        content = "participant,score\n001,3\n002,7\n".encode("utf-8")
        async def read_local(path):
            self.fail("This browser pick has no local path.")

        async def read_browser(data, name):
            with TemporaryDirectory() as directory:
                file = Path(directory) / name
                file.write_bytes(data)
                frame, _ = load_dataset_with_report(file)
                self.assertEqual(frame["score"].tolist(), [3.0, 7.0])
                return True

        result = await import_picked_files(
            [SimpleNamespace(name="browser_data.csv", path=None, bytes=content)],
            import_path=read_local, import_bytes=read_browser,
        )
        self.assertTrue(result.successful)

    async def test_user_cancel_does_not_claim_loaded(self):
        called = []
        async def load(*args):
            called.append(args)
            return True
        result = await import_picked_files(
            [], import_path=load, import_bytes=load,
        )
        self.assertFalse(result.successful)
        self.assertTrue(result.cancelled)
        self.assertEqual(called, [])

    async def test_invalid_extension_and_missing_bytes_are_explained(self):
        called = []
        async def load(*args):
            called.append(args)
            return True
        wrong = await import_picked_files(
            [SimpleNamespace(name="payload.exe", path="/tmp/payload.exe")],
            import_path=load, import_bytes=load,
        )
        missing = await import_picked_files(
            [SimpleNamespace(name="survey.csv", path=None, bytes=None)],
            import_path=load, import_bytes=load,
        )
        self.assertFalse(wrong.successful)
        self.assertIn("extension", wrong.message)
        self.assertFalse(missing.successful)
        self.assertIn("path or file contents", missing.message)
        self.assertEqual(called, [])
        self.assertIn(".tsv", SUPPORTED_EXTENSIONS)

    async def test_unreadable_file_and_false_result_do_not_claim_success(self):
        async def fail(*args):
            raise FileNotFoundError("missing source")
        async def reject(*args):
            return False
        path = SimpleNamespace(name="missing.csv", path="missing.csv")
        for func in (fail, reject):
            selection = await import_picked_files(
                [path], import_path=func, import_bytes=func,
            )
            self.assertFalse(selection.successful)
            self.assertIn("failed", selection.message.lower())

    async def test_browser_size_limit(self):
        called = []
        async def load(*args):
            called.append(args)
            return True
        result = await import_picked_files(
            [SimpleNamespace(name="huge.csv", bytes=b"x" * (MAX_TRANSFER_BYTES + 1))],
            import_path=load, import_bytes=load,
        )
        self.assertFalse(result.successful)
        self.assertIn("25 MB", result.message)
        self.assertEqual(called, [])


class DynamicUserDataTest(unittest.TestCase):
    """Prove a different imported dataset yields a different real statistic."""

    def test_two_changed_user_csv_files_recompute_correlation(self):
        with TemporaryDirectory() as directory:
            x = list(range(1, 31))
            # Both files have *exactly the same schema* and selection logic.
            # Only the user-provided responses differ.
            positive = pd.DataFrame({
                "rating_a": x,
                "rating_b": [2 * v + v % 3 for v in x],
            })
            negative = pd.DataFrame({
                "rating_a": x,
                "rating_b": [80 - 3 * v + v % 3 for v in x],
            })
            results = []
            for i, frame in enumerate((positive, negative)):
                path = Path(directory) / f"participant_export_{i}.csv"
                frame.to_csv(path, index=False)
                imported, report = load_dataset_with_report(path)
                self.assertEqual(len(imported), 30)
                self.assertEqual(imported.columns.tolist(), ["rating_a", "rating_b"])
                result = analyze_correlation(
                    imported, "rating_a", "rating_b",
                    "pearson", "scale", "scale", True,
                )
                results.append(result)
            self.assertGreater(results[0].coefficient, .98)
            self.assertLess(results[1].coefficient, -.98)
            self.assertGreater(
                results[0].coefficient - results[1].coefficient, 1.9
            )
            self.assertEqual(results[0].n_complete, results[1].n_complete)


if __name__ == "__main__":
    unittest.main()
