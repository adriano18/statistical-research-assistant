"""Headless Flet construction checks for both local research workspaces."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import flet as ft
import pandas as pd

from preparation_ui import build_preparation_workspace
from survey_ui import build_survey_workspace


class DummyPage:
    def __init__(self):
        self.services = []
        self.updates = 0

    def update(self):
        self.updates += 1


class LocalWorkspaceTests(unittest.TestCase):
    def test_data_preparation_controls_can_initialize_and_reset(self):
        page = DummyPage()

        async def load_frame(frame):
            pass

        view, reset = build_preparation_workspace(page, load_frame)
        self.assertIsInstance(view, ft.Column)
        self.assertEqual(len(page.services), 1)
        df = pd.DataFrame({"stress_q1": [1, 2, 3], "stress_q2": [3, 2, 1]})
        reset(df)
        self.assertGreater(page.updates, 0)

    def test_survey_builder_can_initialize_without_any_saved_surveys(self):
        page = DummyPage()

        async def load_frame(frame):
            pass

        with TemporaryDirectory() as tmp:
            view = build_survey_workspace(
                page, load_frame, Path(tmp) / "surveys"
            )
            self.assertIsInstance(view, ft.Column)
            self.assertEqual(len(page.services), 1)
            self.assertGreater(page.updates, 0)


if __name__ == "__main__":
    unittest.main()
