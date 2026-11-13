"""Stage 37.0b (design AC-10): the measured interaction cost of the 37.0 flows.

The flows are those of ``docs/stage37/measure_baseline.py`` (the design's
measurement aid), driven through the real workspace controls with the Stage 36
``CountingWorkspace``: a click or a tick counts 1, a dropdown 2; typed fields,
page changes and system dialogs are counted apart. The numbers below are the
measured ones; docs/STAGE37_UX_RESULTS.md records them with the design's
thresholds (beginner ≤ 20 interactions, ≤ 5 typed fields, ≤ 4 page changes;
professor ≤ 6 and ≤ 2). The beginner flow measures 21 interactions, one over
the threshold: the question's kind is a dropdown (2), where the prototype
counted one click. Synthetic data only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def measurement():
    spec = importlib.util.spec_from_file_location(
        "stage37_measure_baseline", ROOT / "docs" / "stage37" / "measure_baseline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def totals(ws) -> tuple[int, int, int, int]:
    return (sum(row[1] for row in ws.log), sum(row[2] for row in ws.log),
            sum(row[3] for row in ws.log), ws.dialogs)


class Stage37FlowTests(unittest.TestCase):
    def test_the_37_0_flows_as_measured(self):
        m = measurement()
        with tempfile.TemporaryDirectory() as folder:
            beginner, professor = m.measure_37(Path(folder), show=False)
            try:
                self.assertEqual(totals(beginner), (21, 5, 4, 2),
                                 "beginner: interactions, typed, page changes, dialogs")
                self.assertEqual(beginner.pages[:4], ["project", "data", "analyze", "reports"],
                                 "the routes of the flow (the set-up for the professor follows)")
                self.assertLessEqual(totals(beginner)[1], 5, "AC-10: typed fields")
                self.assertLessEqual(totals(beginner)[2], 4, "AC-10: page changes")
                self.assertEqual(totals(professor), (5, 0, 2, 0))
                self.assertLessEqual(totals(professor)[0], 6, "AC-10: professor interactions")
                self.assertLessEqual(totals(professor)[2], 2, "AC-10: professor page changes")
                # The analysis is linked to H1 at creation (no extra interaction).
                hypothesis_ids = beginner.facts["hypothesis_ids"]
                self.assertTrue(hypothesis_ids and hypothesis_ids[0])
            finally:
                professor.close()

    def test_the_stage_36_and_today_baselines_are_unchanged(self):
        """The 37.0b pages add no step to the flows measured before it."""
        m = measurement()
        with tempfile.TemporaryDirectory() as folder:
            facts = self._quiet(m.beginner, Path(folder))
            professor = self._quiet(m.professor, Path(folder), facts)
            self.assertIsNone(professor)

    @staticmethod
    def _quiet(function, *args):
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()) as out:
            result = function(*args)
        text = out.getvalue()
        if function.__name__ == "beginner":
            assert "TOTAL" in text and " 22     10      5" in text, text
        else:
            assert " 14      0      6" in text, text
        return result


if __name__ == "__main__":
    unittest.main()
