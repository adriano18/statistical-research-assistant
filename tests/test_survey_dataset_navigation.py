"""Check survey responses load into Dataset only after the actual loader confirms it."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import flet as ft
import pandas as pd

from survey_storage import create_survey, submit_response
from survey_ui import _template_questions, build_survey_workspace


class DummyPage:
    def __init__(self):
        self.services = []
        self.updates = 0

    def update(self):
        self.updates += 1


def descendants(control, visited=None):
    if visited is None:
        visited = set()
    if control is None or isinstance(control, (str, bytes, int, bool)):
        return
    if isinstance(control, (list, tuple)):
        for item in control:
            yield from descendants(item, visited)
        return
    if id(control) in visited:
        return
    visited.add(id(control))
    yield control
    for prop in ("controls", "content", "title"):
        value = getattr(control, prop, None)
        yield from descendants(value, visited)


def load_button(view):
    choices = [
        item for item in descendants(view)
        if isinstance(item, ft.Button)
        and getattr(item, "content", None) == "Load responses into Dataset"
    ]
    if len(choices) != 1:
        raise AssertionError(f"Expected one load button; got {len(choices)}")
    return choices[0]


class SurveyDatasetNavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.page = DummyPage()
        self.survey = create_survey(
            self.root, "Fictional marketing responses",
            "Synthetic data only", _template_questions("marketing"),
        )
        submit_response(self.root, self.survey.survey_id, {
            "consent": True,
            "customer": "Yes",
            "experience": 4,
            "features": ["Quality"],
            "feedback": "Fictional comment.",
        })
        self.navigations = []
        self.seen = []

    def _build(self, accept=True):
        async def importer(frame):
            self.seen.append(frame.copy(deep=True))
            return accept

        return build_survey_workspace(
            self.page, load_dataframe=importer, root=self.root,
            on_dataset_loaded=lambda: self.navigations.append("dataset"),
        )

    async def test_successful_response_import_navigates_with_true_answers(self):
        view = self._build(accept=True)
        await load_button(view).on_click(None)
        self.assertEqual(self.navigations, ["dataset"])
        self.assertEqual(len(self.seen), 1)
        self.assertIsInstance(self.seen[0], pd.DataFrame)
        self.assertEqual(self.seen[0]["experience"].iloc[0], 4)
        self.assertEqual(self.seen[0]["customer"].iloc[0], "Yes")
        self.assertIn("response_id", self.seen[0].columns)

    async def test_failed_import_does_not_navigate_or_claim_success(self):
        view = self._build(accept=False)
        await load_button(view).on_click(None)
        self.assertEqual(self.navigations, [])
        self.assertEqual(len(self.seen), 1)
        text_items = [
            str(item.value) for item in descendants(view)
            if isinstance(item, ft.Text) and item.value
        ]
        self.assertTrue(
            any("Dataset did not accept" in item for item in text_items),
            "A rejected import must have visible error feedback.",
        )
        self.assertFalse(any(
            item.startswith("Loaded 1 local responses")
            for item in text_items
        ))

    async def test_empty_response_collection_does_not_navigate(self):
        from survey_storage import create_survey as publish
        from survey_storage import list_surveys
        # Start a second storage directory with no answers.
        other = self.root / "empty"
        other.mkdir()
        publish(
            other, "Empty pilot", "No answers",
            _template_questions("marketing"),
        )
        async def importer(frame):
            self.seen.append(frame)
            return True
        view = build_survey_workspace(
            self.page, load_dataframe=importer, root=other,
            on_dataset_loaded=lambda: self.navigations.append("dataset"),
        )
        await load_button(view).on_click(None)
        self.assertEqual(self.navigations, [])
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
