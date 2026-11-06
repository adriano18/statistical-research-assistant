"""Tesseract resolver, bundle verification and bounded subprocess tests."""

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import threading
import time
from unittest.mock import patch
import unittest

import ocr_runtime
from ocr_runtime import (
    OCRCancelled, OCRConfigurationError, TesseractRuntime, ocr_readiness,
    resolve_tesseract, run_tesseract, verify_bundle,
)


def make_bundle(root: Path, *, languages=("eng", "lav", "rus")) -> Path:
    folder = root / "windows-x64"
    (folder / "bin").mkdir(parents=True)
    (folder / "tessdata").mkdir()
    name = "tesseract.exe" if os.name == "nt" else "tesseract"
    exe = folder / "bin" / name
    exe.write_bytes(b"synthetic placeholder executable")
    (folder / "bin" / "libsynthetic.dll").write_bytes(b"dll")
    for code in languages:
        (folder / "tessdata" / f"{code}.traineddata").write_bytes(code.encode() * 10)
    files = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(folder).as_posix(), "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    (folder / "MANIFEST.json").write_text(json.dumps({"files": files}))
    return folder


def fake_engine(root: Path, body: str) -> Path:
    script = root / "fake_tesseract.py"
    script.write_text("import sys, time\n" + body)
    if os.name == "nt":
        launcher = root / "fake_tesseract.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        launcher = root / "fake_tesseract"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    return launcher


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        ocr_runtime._READINESS_CACHE.clear()

    def test_developer_override_wins_and_missing_override_is_reported(self):
        bundle = make_bundle(self.root)
        engine = fake_engine(self.root, "print('tesseract 5.9.9')")
        env = {"TESSERACT_CMD": str(engine), "SRA_OCR_RUNTIME_DIR": str(bundle)}
        with patch.dict(os.environ, env):
            runtime = resolve_tesseract()
        self.assertEqual(runtime.origin, "override")
        self.assertIsNone(runtime.tessdata_dir)
        with patch.dict(os.environ, {"TESSERACT_CMD": str(self.root / "nope.exe")}):
            with self.assertRaisesRegex(OCRConfigurationError, "TESSERACT_CMD"):
                resolve_tesseract()

    def test_bundled_runtime_sets_tessdata_and_dll_search_path(self):
        bundle = make_bundle(self.root)
        with patch.dict(os.environ, {"TESSERACT_CMD": "", "SRA_OCR_RUNTIME_DIR": str(bundle)}):
            runtime = resolve_tesseract()
        self.assertEqual(runtime.origin, "bundled")
        self.assertEqual(runtime.tessdata_dir, bundle / "tessdata")
        command = runtime.command("{image}", "stdout")
        self.assertEqual(command[1:3], ["--tessdata-dir", str(bundle / "tessdata")])
        env = runtime.environment()
        self.assertEqual(env["TESSDATA_PREFIX"], str(bundle / "tessdata"))
        self.assertTrue(env["PATH"].startswith(str(bundle / "bin")))

    def test_path_fallback_and_disable_switch(self):
        with patch.dict(os.environ, {"TESSERACT_CMD": "", "SRA_OCR_RUNTIME_DIR": ""}):
            with patch("ocr_runtime.bundle_candidates", return_value=[]):
                with patch("ocr_runtime.shutil.which", return_value="/usr/bin/tesseract"):
                    self.assertEqual(resolve_tesseract().origin, "path")
                with patch("ocr_runtime.shutil.which", return_value=None):
                    with self.assertRaisesRegex(OCRConfigurationError, "not installed"):
                        resolve_tesseract()
        with patch.dict(os.environ, {"SRA_DISABLE_OCR": "1"}):
            with self.assertRaisesRegex(OCRConfigurationError, "disabled"):
                resolve_tesseract()

    def test_manifest_detects_missing_and_corrupt_files(self):
        bundle = make_bundle(self.root)
        self.assertTrue(verify_bundle(bundle, full_hash=True).ok)
        (bundle / "bin" / "libsynthetic.dll").write_bytes(b"DLL")  # same size
        quick = verify_bundle(bundle)
        self.assertTrue(quick.ok)
        full = verify_bundle(bundle, full_hash=True)
        self.assertFalse(full.ok)
        self.assertIn("SHA-256", " ".join(full.problems))
        (bundle / "tessdata" / "rus.traineddata").unlink()
        missing = verify_bundle(bundle)
        self.assertTrue(any("rus" in p for p in missing.problems))
        (bundle / "MANIFEST.json").unlink()
        self.assertFalse(verify_bundle(bundle).ok)


@unittest.skipIf(os.name == "nt", "POSIX launcher script used for timing tests")
class SubprocessTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        ocr_runtime._READINESS_CACHE.clear()

    def test_image_is_passed_as_private_temp_file_and_removed(self):
        engine = fake_engine(self.root, (
            "path = sys.argv[1]\n"
            "data = open(path, 'rb').read()\n"
            "print(path)\nprint(len(data))\n"
        ))
        runtime = TesseractRuntime(engine, "override")
        code, out, _ = run_tesseract(runtime, ["{image}", "stdout"], image=b"\x89PNGdata")
        path, size = out.decode().split()
        self.assertEqual(code, 0)
        self.assertEqual(int(size), 8)
        self.assertFalse(Path(path).exists())

    def test_timeout_cancel_and_output_limit(self):
        sleeper = TesseractRuntime(fake_engine(self.root, "time.sleep(30)"), "override")
        start = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "time limit"):
            run_tesseract(sleeper, ["x"], timeout=1)
        self.assertLess(time.monotonic() - start, 10)
        cancel = threading.Event()
        threading.Timer(0.3, cancel.set).start()
        with self.assertRaises(OCRCancelled):
            run_tesseract(sleeper, ["x"], timeout=30, cancel=cancel)
        loud = TesseractRuntime(
            fake_engine(self.root, "sys.stdout.write('x' * 300000)"), "override",
        )
        with self.assertRaisesRegex(RuntimeError, "safety limit"):
            run_tesseract(loud, ["x"], max_output=1000)

    def test_readiness_reports_version_languages_and_missing(self):
        engine = fake_engine(self.root, (
            "if '--version' in sys.argv: print('tesseract 5.9.9')\n"
            "else: print('List of available languages in \"x\" (2):'); print('eng'); print('rus')\n"
        ))
        with patch.dict(os.environ, {"TESSERACT_CMD": str(engine)}):
            ready = ocr_readiness(use_cache=False)
        self.assertTrue(ready.available)
        self.assertEqual(ready.version, "tesseract 5.9.9")
        self.assertEqual(ready.languages, ("eng", "rus"))
        self.assertEqual(ready.missing_languages, ("lav",))
        self.assertIn("missing: lav", ready.summary())
        with patch.dict(os.environ, {"SRA_DISABLE_OCR": "1"}):
            off = ocr_readiness(use_cache=False)
        self.assertFalse(off.available)
        self.assertIn("unavailable", off.summary())


if __name__ == "__main__":
    unittest.main()
