"""Stage 37 licence path: the in-house Cronbach's α, Feldt interval and α if
item deleted (``cronbach.py``) against hand calculation and, as a test-only
oracle, pingouin (GPL-3.0; a development dependency, never bundled).

Tolerances
* Hand calculation (exact fractions, then floats): 1e-12.
* pingouin's α and α if deleted: 1e-12 absolute (the same formula; observed
  differences are a few units in the last place).
* pingouin rounds Feldt's bounds to three decimals; the engine reports them
  rounded the same way, and the rounded bounds must be identical. The
  unrounded bounds equal the written-out formula with ``f.isf`` to 1e-12.

The pingouin tests are skipped when pingouin is not installed (a
runtime-only environment such as the pruned-runtime CI job); the hand
calculations always run. Only fictional, simulated data appear here.
"""

from __future__ import annotations

from fractions import Fraction
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

import cronbach  # noqa: E402
from reliability import analyze_cronbach  # noqa: E402

HAS_PINGOUIN = importlib.util.find_spec("pingouin") is not None


def datasets():
    """Fictional item sets: one-factor items of several sizes, a 3-item set, a
    set with a contradictory item (negative α), ordinal codes with ties, and
    the scales of the Stage 37 fixture."""
    rng = np.random.default_rng(3701)
    out = []
    for n, k, loading in ((40, 3, 0.6), (120, 5, 0.7), (200, 8, 0.5), (60, 12, 0.4),
                          (300, 20, 0.8)):
        trait = rng.normal(size=n)
        out.append((f"factor n={n} k={k}", np.column_stack(
            [loading * trait + rng.normal(0, 1, n) for _ in range(k)])))
    trait = rng.normal(size=80)
    out.append(("negative", np.column_stack([trait + rng.normal(0, .5, 80),
                                             -trait + rng.normal(0, .5, 80),
                                             rng.normal(0, 1, 80)])))
    out.append(("likert", np.clip(np.round(3 + 0.9 * rng.normal(size=(150, 1))
                                            + rng.normal(0, 1, (150, 6))), 1, 5)))
    sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "stage37"))
    import generate_master_fixture as fixture

    with tempfile.TemporaryDirectory() as folder:
        frame = pd.read_csv(fixture.generate(Path(folder))[0])
    for prefix, count in (("SYN_LON_", 20), ("SYN_SUP_", 12), ("SYN_WELL_", 5)):
        columns = [f"{prefix}{j:02d}" for j in range(1, count + 1)]
        out.append((prefix, frame[columns].dropna().to_numpy(float)))
    out.append(("SYN_COPE_01..07", frame[[f"SYN_COPE_{j:02d}" for j in range(1, 8)]]
                .dropna().to_numpy(float)))
    return out


class HandCalculationTests(unittest.TestCase):
    def test_alpha_by_exact_fractions(self):
        values = [[1, 2, 2], [2, 2, 3], [3, 4, 3], [4, 3, 5], [5, 5, 4]]
        n, k = len(values), 3

        def var(column):
            mean = Fraction(sum(column), n)
            return sum((Fraction(v) - mean) ** 2 for v in column) / (n - 1)

        items = [var([row[j] for row in values]) for j in range(k)]
        total = var([sum(row) for row in values])
        exact = Fraction(k, k - 1) * (1 - sum(items) / total)
        self.assertAlmostEqual(cronbach.cronbach_alpha(values), float(exact), delta=1e-12)
        deleted = cronbach.alpha_if_deleted(values)
        for j in range(k):
            rest = [[v for i, v in enumerate(row) if i != j] for row in values]
            a = [var([row[i] for row in rest]) for i in range(2)]
            t = var([sum(row) for row in rest])
            self.assertAlmostEqual(deleted[j], float(2 * (1 - sum(a) / t)), delta=1e-12)

    def test_feldt_interval_written_out(self):
        for alpha, n, k in ((0.81, 120, 5), (0.35, 40, 3), (-0.2, 80, 3), (0.95, 300, 20)):
            df1, df2 = n - 1, (n - 1) * (k - 1)
            low = 1 - (1 - alpha) * stats.f.isf(0.025, df1, df2)
            high = 1 - (1 - alpha) * stats.f.isf(0.975, df1, df2)
            got = cronbach.feldt_interval(alpha, n, k)
            self.assertAlmostEqual(got[0], low, delta=1e-12)
            self.assertAlmostEqual(got[1], high, delta=1e-12)
            self.assertLess(got[0], alpha)
            self.assertGreater(got[1], alpha)
        low90, high90 = cronbach.feldt_interval(0.8, 100, 6, level=0.90)
        low95, high95 = cronbach.feldt_interval(0.8, 100, 6)
        self.assertGreater(low90, low95)
        self.assertLess(high90, high95)

    def test_identical_items_and_refusals(self):
        answers = np.array([1, 2, 3, 4, 5, 3, 2], dtype=float)
        self.assertAlmostEqual(cronbach.cronbach_alpha(np.column_stack([answers] * 3)), 1.0,
                               delta=1e-12)
        with self.assertRaises(ValueError):
            cronbach.cronbach_alpha([[1, 1], [1, 1]])               # no total variation
        with self.assertRaises(ValueError):
            cronbach.cronbach_alpha([[1, np.nan], [2, 3]])
        with self.assertRaises(ValueError):
            cronbach.cronbach_alpha([[1, 2, 3]])                    # one respondent
        self.assertIsNone(cronbach.alpha_if_deleted([[1, 1, 5], [1, 2, 4], [1, 3, 3]])[2])


@unittest.skipUnless(HAS_PINGOUIN, "pingouin (test-only oracle) is not installed")
class PingouinOracleTests(unittest.TestCase):
    def test_alpha_interval_and_alpha_if_deleted_match_pingouin(self):
        import pingouin as pg

        largest = 0.0
        for name, values in datasets():
            frame = pd.DataFrame(values)
            reference, ci = pg.cronbach_alpha(data=frame, nan_policy="listwise")
            alpha = cronbach.cronbach_alpha(values)
            largest = max(largest, abs(alpha - reference))
            self.assertAlmostEqual(alpha, reference, delta=1e-12, msg=name)
            bounds = np.round(cronbach.feldt_interval(alpha, *values.shape), 3)
            np.testing.assert_array_equal(bounds, ci, err_msg=name)
            for j, deleted in enumerate(cronbach.alpha_if_deleted(values)):
                rest = frame.drop(columns=j)
                self.assertAlmostEqual(deleted, pg.cronbach_alpha(data=rest)[0], delta=1e-12,
                                       msg=f"{name} without {j}")
        self.assertLess(largest, 1e-12)

    def test_the_reliability_engine_reports_what_pingouin_reported(self):
        """The values earlier versions showed: α, the 3-decimal Feldt bounds
        and α if deleted, on every data set and on the bundled example."""
        import pingouin as pg

        sets = [(name, pd.DataFrame(values, columns=[f"q{j}" for j in range(values.shape[1])]))
                for name, values in datasets() if values.shape[1] >= 3]
        example = pd.read_csv(ROOT / "examples" / "sample_scale.csv")
        sets.append(("sample_scale.csv", example[["stress_q1", "stress_q2", "stress_q3",
                                                  "stress_q4"]]))
        for name, frame in sets:
            result = analyze_cronbach(frame, list(frame.columns))
            # Earlier versions passed the listwise-complete cases to pingouin.
            # (Given rows with missing answers, pingouin's own listwise option
            # takes Feldt's n from the rows BEFORE deletion: 32 instead of 30
            # on the bundled example — see the next test.)
            complete = frame.dropna()
            reference, ci = pg.cronbach_alpha(data=complete, nan_policy="listwise")
            self.assertAlmostEqual(result.alpha, reference, delta=1e-12, msg=name)
            self.assertEqual((result.ci_low, result.ci_high), (float(ci[0]), float(ci[1])),
                             name)
            if frame.shape[1] >= 4:
                for column in frame.columns:
                    expected = pg.cronbach_alpha(data=complete.drop(columns=column))[0]
                    self.assertAlmostEqual(result.alpha_if_deleted[column], expected,
                                           delta=1e-12, msg=f"{name} {column}")


    def test_feldt_uses_the_complete_cases_unlike_pingouins_listwise_option(self):
        """Documented difference of the oracle, not of the program: with rows
        that have missing answers, ``pingouin.cronbach_alpha(nan_policy=
        "listwise")`` drops them for α but keeps their count in Feldt's n.
        The program (before and after Stage 37) uses the n of the complete
        cases whose answers enter α."""
        import pingouin as pg

        frame = pd.read_csv(ROOT / "examples" / "sample_scale.csv")[
            ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]]
        complete = frame.dropna()
        self.assertEqual((len(frame), len(complete)), (32, 30))
        result = analyze_cronbach(frame, list(frame.columns))
        alpha = cronbach.cronbach_alpha(complete.to_numpy(float))
        on_complete = np.round(cronbach.feldt_interval(alpha, 30, 4), 3)
        on_all_rows = np.round(cronbach.feldt_interval(alpha, 32, 4), 3)
        self.assertEqual((result.ci_low, result.ci_high), tuple(on_complete))
        np.testing.assert_array_equal(pg.cronbach_alpha(data=frame, nan_policy="listwise")[1],
                                      on_all_rows)
        self.assertNotEqual(tuple(on_complete), tuple(on_all_rows))


class NoPingouinAtRunTimeTests(unittest.TestCase):
    def test_an_alpha_is_calculated_without_importing_pingouin(self):
        script = ("import json, sys\n"
                  "import pandas as pd\n"
                  "import reliability, item_diagnostics\n"
                  "frame = pd.read_csv(sys.argv[1])\n"
                  "items = ['stress_q1', 'stress_q2', 'stress_q3', 'stress_q4']\n"
                  "a = reliability.analyze_cronbach(frame, items)\n"
                  "d = item_diagnostics.diagnose_items(frame, items, resamples=0)\n"
                  "print(json.dumps({'pingouin': 'pingouin' in sys.modules,\n"
                  "                  'sklearn': 'sklearn' in sys.modules,\n"
                  "                  'alpha': a.alpha, 'method': d.alpha.ci_method}))\n")
        done = subprocess.run([sys.executable, "-c", script,
                               str(ROOT / "examples" / "sample_scale.csv")], cwd=ROOT,
                              capture_output=True, text=True, check=True,
                              env={**os.environ, "MPLBACKEND": "Agg"})
        found = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertFalse(found["pingouin"])
        self.assertFalse(found["sklearn"])
        self.assertNotIn("pingouin", found["method"])
        self.assertIn("Feldt", found["method"])

    def test_pingouin_is_not_a_runtime_requirement(self):
        runtime = (ROOT / "requirements.in").read_text(encoding="utf-8")
        development = (ROOT / "requirements-dev.in").read_text(encoding="utf-8")
        lines = [line.split("#")[0].strip() for line in runtime.splitlines()]
        self.assertFalse(any(line.startswith("pingouin") for line in lines))
        self.assertIn("pingouin", development)
        lock = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        for package in ("pingouin==", "scikit-learn==", "seaborn==", "xarray==",
                        "pandas-flavor=="):
            self.assertNotIn(package, lock)
        from project_store import LIBRARIES

        self.assertNotIn("pingouin", LIBRARIES)


if __name__ == "__main__":
    unittest.main()
