"""Stage 37 (#67): pyreadstat, the one new runtime dependency.

- requirements.in gives a range; requirements.txt pins one version with the
  hash of the Windows wheel the program bundles (cp312, win_amd64);
- the SBOM lists pyreadstat (Apache-2.0) with the ReadStat C library inside
  it (MIT), and the licence table shows both;
- the build's cleanup keeps the licence file and the compiled modules.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_toolchain as toolchain  # noqa: E402

# pyreadstat-1.3.7-cp312-cp312-win_amd64.whl as published on PyPI (2026-10-21),
# checked against PyPI's JSON metadata when the lock was regenerated.
WINDOWS_WHEEL_SHA256 = "7b65bd28c402376c5bafa44c691acf726904611621e09404bbf4827de78b4609"


class LockTests(unittest.TestCase):
    def test_a_range_in_the_input_and_one_hashed_version_in_the_lock(self):
        lines = [line.split("#", 1)[0].strip() for line in
                 (ROOT / "requirements.in").read_text(encoding="utf-8").splitlines()]
        wanted = [Requirement(line) for line in lines if line.startswith("pyreadstat")]
        self.assertEqual(len(wanted), 1)
        self.assertEqual(str(wanted[0].specifier), "<2,>=1.3")
        pins = {toolchain.canonical(p.name): p for p in toolchain.parse_lock(toolchain.RUNTIME_LOCK)}
        pin = pins["pyreadstat"]
        self.assertEqual(pin.version, "1.3.7")
        self.assertIn(WINDOWS_WHEEL_SHA256, pin.hashes, "the cp312 win_amd64 wheel is locked")
        # Its dependencies were pinned before; nothing else had to move.
        self.assertEqual(pins["narwhals"].version, "2.28.0")
        self.assertEqual(pins["numpy"].version, "2.5.4")
        self.assertEqual(len(pins), 50)

    def test_the_windows_runtime_includes_it(self):
        lock = toolchain.load_lock()
        environment = toolchain.marker_environment(windows=True, python=lock["python"]["embedded"])
        wanted = toolchain.applicable(toolchain.parse_lock(toolchain.RUNTIME_LOCK), environment)
        self.assertIn("pyreadstat", wanted)


class SbomTests(unittest.TestCase):
    def test_pyreadstat_apache_and_readstat_mit_inside_it(self):
        import build_sbom

        components = build_sbom.python_components(build_sbom.toolchain.load_lock())
        entry = next(c for c in components if c["name"] == "pyreadstat")
        self.assertEqual(entry["version"], "1.3.7")
        self.assertEqual(entry["licenses"], [{"expression": "Apache-2.0"}])
        inner = entry["components"]
        self.assertEqual([(c["name"], c["licenses"]) for c in inner],
                         [("ReadStat", [{"expression": "MIT"}])])
        table = build_sbom.licences_markdown({"components": components})
        self.assertIn("| pyreadstat | 1.3.7 | Apache-2.0 |  | pypi |", table)
        self.assertIn("| ReadStat | in pyreadstat 1.3.7 | MIT |  | pypi (inside pyreadstat) |",
                      table)

    def test_the_cleanup_keeps_the_licence_and_the_compiled_modules(self):
        from prune_packages import SERIOUS_PYTHON_DEFAULTS, glob_regex, matches, project_globs

        regexes = [glob_regex(g) for g in SERIOUS_PYTHON_DEFAULTS + project_globs()]
        for kept in ("pyreadstat-1.3.7.dist-info/licenses/LICENSE",
                     "pyreadstat/_readstat_writer.cp312-win_amd64.pyd",
                     "pyreadstat/_readstat_parser.cp312-win_amd64.pyd",
                     "pyreadstat/pyreadstat.py"):
            self.assertFalse(matches(kept, regexes), kept)
        for removed in ("pyreadstat/_readstat_writer.c", "pyreadstat/_readstat_parser.pyx",
                        "pyreadstat/readstat_api.pxd"):
            self.assertTrue(matches(removed, regexes), removed)


if __name__ == "__main__":
    unittest.main()
