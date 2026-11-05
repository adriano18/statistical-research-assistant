"""Pinned Windows OCR bundle lock file and packaging helper checks."""

import importlib.util
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "packaging" / "windows_ocr_runtime.lock.json"


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LockFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads(LOCK.read_text(encoding="utf-8"))

    def test_tesseract_5_with_required_languages(self):
        self.assertTrue(self.lock["tesseract_version"].startswith("5."))
        paths = {f["path"] for f in self.lock["files"]}
        for required in ("bin/tesseract.exe", "tessdata/eng.traineddata",
                         "tessdata/lav.traineddata", "tessdata/rus.traineddata"):
            self.assertIn(required, paths)
        self.assertTrue(any(p.startswith("bin/libtesseract") for p in paths))
        self.assertTrue(any(p.startswith("bin/libleptonica") for p in paths))

    def test_every_artifact_is_pinned_by_sha256(self):
        packages = {p["name"]: p for p in self.lock["packages"]}
        digest = re.compile(r"^[0-9a-f]{64}$")
        for package in packages.values():
            self.assertRegex(package["sha256"], digest)
            self.assertTrue(package["filename"].endswith(".pkg.tar.zst"))
        for entry in self.lock["files"]:
            self.assertIn(entry["package"], packages)
            self.assertTrue(packages[entry["package"]]["used"])
            self.assertRegex(entry["sha256"], digest)
            self.assertGreater(entry["size"], 0)
            self.assertFalse(entry["path"].startswith(("/", "..")))
        for source in self.lock["license_sources"]:
            self.assertRegex(source["sha256"], digest)

    def test_every_used_package_has_licence_text(self):
        covered = {f["package"] for f in self.lock["files"] if f["path"].startswith("licenses/")}
        covered |= {s["package"] for s in self.lock["license_sources"]}
        used = {p["name"] for p in self.lock["packages"] if p["used"]}
        data = {n for n in used if "tesseract-data" in n}  # Apache-2.0 copy
        self.assertEqual(used - covered - data, set())

    def test_notices_name_gpl_components_and_sources(self):
        tool = load_tool("prepare_windows_ocr_runtime")
        text = tool.third_party_notices(self.lock)
        self.assertIn("jbigkit", text)
        self.assertIn("GPL-2.0-or-later", text)
        self.assertIn("repo.msys2.org/mingw/sources", text)
        self.assertIn("tesseract-ocr", text)


class PackagedCheckTests(unittest.TestCase):
    def test_finds_runtime_inside_app_archive(self):
        tool = load_tool("check_packaged_ocr")
        with TemporaryDirectory() as temp:
            build = Path(temp) / "build" / "windows" / "data"
            build.mkdir(parents=True)
            with zipfile.ZipFile(build / "app.zip", "w") as z:
                z.writestr("app.py", "")
                z.writestr("bundled_ocr/windows-x64/MANIFEST.json", "{}")
            kind, where = tool.find_package(Path(temp) / "build")
            self.assertEqual(kind, "zip")
            self.assertEqual(where.name, "app.zip")
            with self.assertRaises(SystemExit):
                tool.find_package(Path(temp) / "nothing")


if __name__ == "__main__":
    unittest.main()
