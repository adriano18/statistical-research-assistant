"""Stage 34 distribution tools (issue #23): package audit and runtime pruning."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import package_audit as audit  # noqa: E402
import prune_packages as prune  # noqa: E402
import startup_ab  # noqa: E402


def write(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def fake_build(root: Path) -> None:
    """A miniature Flet Windows build with one of every component."""
    write(root, "StatisticalResearchAssistant.exe", b"MZ" + b"\0" * 5000)
    write(root, "flutter_windows.dll", b"flutter" * 3000)
    write(root, "msvcp140.dll", b"msvc" * 2000)
    write(root, "python312.dll", b"py" * 4000)
    write(root, "Lib/json/__init__.pyc", b"json" * 500)
    write(root, "data/app.so", b"dart" * 4000)
    write(root, "app/app.pyc", b"code" * 900)
    write(root, "app/examples/sample.csv", b"a,b\n1,2\n" * 50)
    write(root, "app/tests/test_x.pyc", b"t" * 3000)
    write(root, "app/docs/images/shot.png", b"\x89PNG" + bytes(range(256)) * 40)
    write(root, "app/bundled_ocr/windows-x64/bin/tesseract.exe", b"tess" * 3000)
    write(root, "app/bundled_ocr/windows-x64/tessdata/eng.traineddata", b"eng" * 6000)
    write(root, "app/bundled_ocr/windows-x64/tests/keep.txt", b"bundled runtime stays")
    write(root, "site-packages/numpy/__init__.pyc", b"np" * 3000)
    write(root, "site-packages/numpy/testing/__init__.pyc", b"testing stays" * 100)
    write(root, "site-packages/numpy/_core/tests/test_a.pyc", b"x" * 8000)
    write(root, "site-packages/numpy/_core/lib/npymath.lib", b"lib" * 3000)
    write(root, "site-packages/numpy.libs/libopenblas.dll", b"blas" * 6000)
    write(root, "site-packages/numpy-2.5.4.dist-info/RECORD",
          b"numpy/__init__.py,,\nnumpy.libs/libopenblas.dll,,\n")
    write(root, "site-packages/PIL/_avif.cp312-win_amd64.pyd", bytes(range(256)) * 60)
    write(root, "site-packages/PIL/_imaging.cp312-win_amd64.pyd", b"imaging" * 1000)
    write(root, "site-packages/pillow-12.3.0.dist-info/RECORD", b"PIL/__init__.py,,\n")
    write(root, "site-packages/joblib/test/test_b.pyc", b"y" * 5000)
    write(root, "site-packages/pandas/_testing/__init__.pyc", b"pandas testing" * 100)
    write(root, "site-packages/scipy/stats/tests/data/big.npz", b"z" * 9000)
    write(root, "site-packages/statsmodels/dup_a.bin", b"same" * 2000)
    write(root, "site-packages/statsmodels/dup_b.bin", b"same" * 2000)


def zip_folder(folder: Path, target: Path, *, skip=lambda path: False) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            relative = path.relative_to(folder).as_posix()
            if not skip(relative):
                archive.write(path, relative)


class PackageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        fake_build(self.build)

    def report(self, source: Path) -> dict:
        entries, layers = audit.read_build(source)
        return audit.analyse(entries, layers, audit.record_texts_of(source))

    def test_components_and_distributions_come_from_the_build(self):
        report = self.report(self.build)
        components = report["components"]
        self.assertEqual(set(components), {
            "Python packages", "Bundled OCR", "Flutter engine and UI", "Python runtime",
            "Application", "Microsoft C++ runtime"})
        packages = {row[0] for row in components["Python packages"]["details"]}
        # numpy.libs belongs to numpy through its RECORD; PIL to pillow.
        self.assertIn("numpy", packages)
        self.assertIn("pillow", packages)
        self.assertNotIn("numpy.libs", packages)
        ocr = {row[0] for row in components["Bundled OCR"]["details"]}
        self.assertEqual(ocr, {"engine and libraries", "language data eng", "notices and manifest"})
        self.assertEqual(report["total"]["files"], 27)

    def test_candidates_keep_runtime_testing_modules_and_the_bundled_ocr(self):
        report = self.report(self.build)
        examples = {c["id"]: c for c in report["candidates"]}
        tests = examples["package-tests"]
        self.assertEqual(tests["files"], 3)  # numpy/_core/tests, joblib/test, scipy/stats/tests
        listed = json.dumps(report["candidates"])
        self.assertNotIn("numpy/testing", listed)
        self.assertNotIn("pandas/_testing", listed)
        self.assertNotIn("bundled_ocr", listed)
        self.assertNotIn("app/examples", listed)
        self.assertEqual(examples["pillow-avif"]["files"], 1)
        self.assertEqual(examples["build-only-files"]["files"], 1)  # npymath.lib
        self.assertEqual(examples["app-dev-files"]["files"], 2)
        self.assertEqual(report["duplicates"][0]["wasted_bytes"], 8000)

    def test_reported_saving_equals_the_real_difference_between_two_zips(self):
        full, slim = self.root / "full.zip", self.root / "slim.zip"
        zip_folder(self.build, full)
        report = self.report(full)
        removed = {c["id"] for c in report["candidates"]}
        zip_folder(self.build, slim, skip=lambda path: audit.candidate_of(path) in removed)
        saving = sum(c["zip_saving"] for c in report["candidates"])
        # The central directory end record is shared; everything else is exact.
        self.assertEqual(full.stat().st_size - slim.stat().st_size, saving)

    def test_nested_ci_artifact_reports_every_layer(self):
        inner = self.root / "StatisticalResearchAssistant-Windows-x64.zip"
        zip_folder(self.build, inner)
        artifact = self.root / "artifact.zip"
        with zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as outer:
            outer.write(inner, inner.name)
            outer.writestr("gui-startup/gui-startup-result.json", json.dumps({
                "ok": True, "window_visible_after_s": 1.5, "interface_ready_reported_s": 3.2,
                "longest_black_s": 0.0}))
        report = self.report(artifact)
        self.assertEqual(report["layers"]["artifact_bytes"], artifact.stat().st_size)
        self.assertEqual(report["layers"]["distributed_zip_bytes"], inner.stat().st_size)
        self.assertEqual(report["total"]["files"], 27)
        self.assertEqual(report["startup"][0]["interface_ready_reported_s"], 3.2)
        markdown = audit.to_markdown(report)
        self.assertIn("CI artifact download (wrapper ZIP)", markdown)
        self.assertIn("3.20 s", markdown)

    def test_budget_failure_is_reported(self):
        code = audit.main([str(self.build), "--budget-installed-mib", "0.01"])
        self.assertEqual(code, 1)
        self.assertEqual(audit.main([str(self.build), "--budget-installed-mib", "100"]), 0)

    def test_unsafe_archive_paths_are_rejected(self):
        evil = self.root / "evil.zip"
        with zipfile.ZipFile(evil, "w") as archive:
            archive.writestr("../outside.dll", b"x")
            archive.writestr("app.exe", b"MZ")
        with self.assertRaises(ValueError):
            audit.read_build(evil)


class PruneTests(unittest.TestCase):
    def test_project_globs_come_from_pyproject(self):
        globs = prune.project_globs()
        self.assertIn("**/tests", globs)
        self.assertIn("PIL/_avif.*", globs)

    def test_glob_rules_match_serious_python_semantics(self):
        rx = lambda g: prune.glob_regex(g)  # noqa: E731
        self.assertTrue(rx("**/tests").match("scipy/special/tests"))
        self.assertTrue(rx("**/tests").match("tests"))
        self.assertFalse(rx("**/tests").match("numpy/testing"))
        self.assertFalse(rx("**/tests").match("pandas/_testing"))
        self.assertFalse(rx("**/tests").match("scipy/special/tests_data.py"))
        self.assertTrue(rx("**.lib").match("numpy/_core/lib/npymath.lib"))
        self.assertTrue(rx("PIL/_avif.*").match("PIL/_avif.cp312-win_amd64.pyd"))
        self.assertTrue(rx("PIL/_avif.*").match("PIL/_avif.cpython-312-x86_64-linux-gnu.so"))
        self.assertFalse(rx("PIL/_avif.*").match("PIL/_imaging.cp312-win_amd64.pyd"))
        self.assertFalse(rx("PIL/_avif.*").match("PIL/AvifImagePlugin.py"))

    def test_pruning_removes_only_matching_paths(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            fake_build(root)
            site = root / "site-packages"
            before = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
            dry = prune.find_removals(site, prune.SERIOUS_PYTHON_DEFAULTS + prune.project_globs())
            self.assertEqual(
                sorted(p.relative_to(site).as_posix() for p in dry),
                ["PIL/_avif.cp312-win_amd64.pyd", "joblib/test", "numpy/_core/lib/npymath.lib",
                 "numpy/_core/tests", "scipy/stats/tests"])
            self.assertEqual(prune.main(["--site-packages", str(site)]), 0)
            after = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
            self.assertIn("numpy/testing/__init__.pyc", after)
            self.assertIn("pandas/_testing/__init__.pyc", after)
            self.assertIn("PIL/_imaging.cp312-win_amd64.pyd", after)
            self.assertEqual(len(before - after), 5)

    def test_dry_run_changes_nothing(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            fake_build(root)
            site = root / "site-packages"
            before = sorted(p.as_posix() for p in site.rglob("*"))
            stream = io.StringIO()
            from contextlib import redirect_stdout
            with redirect_stdout(stream):
                prune.main(["--site-packages", str(site), "--dry-run"])
            self.assertEqual(before, sorted(p.as_posix() for p in site.rglob("*")))
            self.assertIn("scipy/stats/tests", stream.getvalue())


class StartupComparisonTests(unittest.TestCase):
    def test_cold_start_is_separate_and_warm_starts_use_the_median(self):
        def launch(window, ready, ok=True):
            return {"ok": ok, "window_visible_after_s": window, "interface_ready_reported_s": ready}

        summary = startup_ab.summarise({
            "baseline": [launch(2.0, 4.5), launch(1.5, 3.2), launch(1.5, 3.0), launch(1.5, 3.4)],
            "cleaned": [launch(2.0, 4.1), launch(1.5, 2.9), launch(None, None, ok=False),
                        launch(1.5, 3.1)],
        })
        self.assertEqual(summary["baseline"]["cold"]["interface_ready_reported_s"], 4.5)
        self.assertEqual(summary["baseline"]["interface_ready_reported_s"]["median"], 3.2)
        self.assertEqual(summary["cleaned"]["ok"], 3)
        self.assertEqual(summary["cleaned"]["interface_ready_reported_s"]["median"], 3.0)
        markdown = startup_ab.to_markdown(summary)
        self.assertIn("| baseline | 4/4 | 2.00 s / 4.50 s | 1.50 s / 3.20 s | 3.00 s–3.40 s |", markdown)
        self.assertIn("| cleaned | 3/4 |", markdown)


class AnalysisSelftestTests(unittest.TestCase):
    def test_every_procedure_runs_and_identical_runs_compare_equal(self):
        import analysis_selftest

        with TemporaryDirectory() as folder:
            target = Path(folder) / "result.json"
            self.assertEqual(analysis_selftest.run_selftest(target), 0)
            result = json.loads(target.read_text(encoding="utf-8"))
        steps = result["steps"]
        for step in ("descriptive", "explore", "alpha", "omega", "omega_bootstrap", "factor",
                     "correlation_matrix", "correlation", "regression", "groups_mannwhitney",
                     "groups_welch", "paired", "repeated", "chi_square", "omnibus", "posthoc",
                     "logistic", "ancova"):
            self.assertTrue(steps[step]["ok"], step)
            self.assertEqual(len(steps[step]["report_sha256"]), 64)
        self.assertGreater(result["exports"]["docx_bytes"], 1000)
        self.assertEqual(result["exports"]["survey_rows"], 1)
        self.assertEqual(analysis_selftest.compare(result, result), [])
        changed = json.loads(json.dumps(result))
        changed["steps"]["ancova"]["report_sha256"] = "0" * 64
        self.assertEqual(analysis_selftest.compare(result, changed),
                         ["ancova: report differs from the source checkout"])


if __name__ == "__main__":
    unittest.main()


class StartupImportTests(unittest.TestCase):
    def test_pingouin_is_imported_only_when_an_alpha_is_calculated(self):
        """pingouin (with scikit-learn, seaborn and xarray) is the largest single
        import of the classic interface; it now loads on first use."""
        import subprocess

        script = (
            "import sys\n"
            "import pandas as pd\n"
            "import reliability\n"
            "print('before', 'pingouin' in sys.modules)\n"
            "frame = pd.read_csv(sys.argv[1])\n"
            "result = reliability.analyze_cronbach(frame, ['stress_q1', 'stress_q2', 'stress_q3', 'stress_q4'])\n"
            "print('after', 'pingouin' in sys.modules, round(result.alpha, 12))\n"
        )
        output = subprocess.run(
            [sys.executable, "-c", script, str(ROOT / "examples" / "sample_scale.csv")],
            cwd=ROOT, capture_output=True, text=True, check=True,
            env={**__import__("os").environ, "MPLBACKEND": "Agg"}).stdout.split("\n")
        self.assertEqual(output[0], "before False")
        self.assertTrue(output[1].startswith("after True "))
        # Same value as calculating in this process (where pingouin may be loaded).
        import pandas as pd
        import reliability

        frame = pd.read_csv(ROOT / "examples" / "sample_scale.csv")
        expected = reliability.analyze_cronbach(
            frame, ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]).alpha
        self.assertEqual(output[1].split()[-1], str(round(expected, 12)))

    def test_flet_pack_workaround_only_drops_encodings_in_binary_mode(self):
        import flet_pack_compat

        with TemporaryDirectory() as temp:
            path = Path(temp) / "overlay.bin"
            path.write_bytes(b"MZ")
            with flet_pack_compat._binary_safe_open(path, "ab", encoding="utf-8") as stream:
                stream.write(b"\x00overlay")
            self.assertEqual(path.read_bytes(), b"MZ\x00overlay")
            text = Path(temp) / "note.txt"
            with flet_pack_compat._binary_safe_open(text, "w", encoding="utf-8") as stream:
                stream.write("päivä")
            self.assertEqual(text.read_text(encoding="utf-8"), "päivä")


class GuiStartupCheckTests(unittest.TestCase):
    def test_the_window_search_covers_every_process_the_app_started(self):
        """flet pack draws its window in a child Flet client process."""
        import check_gui_startup as check

        pairs = [(100, 1), (200, 100), (300, 200), (400, 1), (500, 400), (600, 300), (100, 100)]
        self.assertEqual(check.descendants(100, pairs), {100, 200, 300, 600})
        self.assertEqual(check.descendants(400, pairs), {400, 500})
        self.assertEqual(check.descendants(999, pairs), {999})
