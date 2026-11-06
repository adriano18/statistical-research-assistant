"""Check that a `flet build windows` output really contains the OCR runtime.

Usage: python tools/check_packaged_ocr.py build/windows

1. Finds the packaged Python application (an ``app.zip`` asset or an
   unpacked folder) and confirms ``bundled_ocr/windows-x64`` with
   ``bin/tesseract.exe``, ``MANIFEST.json`` and eng/lav/rus data is inside.
2. Extracts it to a temporary folder, verifies every file against the
   manifest (size + SHA-256) using the *packaged* ``ocr_runtime`` module.
3. Runs the packaged ``ocr_selftest`` with PATH reduced to Windows system
   folders, so the result cannot come from a developer installation.

The separate CI step that launches the real executable covers the embedded
Python interpreter; this script gives a precise diagnosis when it fails.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

RUNTIME = "bundled_ocr/windows-x64/"


def find_package(build: Path) -> tuple[str, Path]:
    for archive in sorted(build.rglob("*.zip")):
        try:
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            continue
        prefix = next((n[: -len(RUNTIME + "MANIFEST.json")] for n in names
                       if n.endswith(RUNTIME + "MANIFEST.json")), None)
        if prefix is not None:
            return "zip", archive
    for manifest in build.rglob("MANIFEST.json"):
        if manifest.parent.as_posix().endswith(RUNTIME.rstrip("/")):
            return "dir", manifest.parents[2]
    raise SystemExit(f"No packaged {RUNTIME} found below {build}")


def main() -> int:
    build = Path(sys.argv[1] if len(sys.argv) > 1 else "build/windows").resolve()
    kind, location = find_package(build)
    print(f"Packaged application ({kind}): {location}")
    with tempfile.TemporaryDirectory(prefix="sra-packaged-") as temp:
        if kind == "zip":
            with zipfile.ZipFile(location) as z:
                z.extractall(temp)
            root = next(p.parents[2] for p in Path(temp).rglob("MANIFEST.json")
                        if p.parent.as_posix().endswith(RUNTIME.rstrip("/")))
        else:
            root = location
        bundle = root / RUNTIME
        for required in ("bin/tesseract.exe", "tessdata/eng.traineddata",
                         "tessdata/lav.traineddata", "tessdata/rus.traineddata",
                         "THIRD_PARTY_NOTICES.txt"):
            if not (bundle / required).is_file():
                raise SystemExit(f"Packaged runtime lacks {required}")
        modules = {p.stem.split(".")[0] for p in root.iterdir() if p.suffix in {".py", ".pyc"}}
        for module in ("app", "research_app", "startup_diagnostics", "binary_responses",
                       "response_scales", "shared_scales", "letter_spacing",
                       "repeated_choices", "scoring_evidence", "matrix_reconstruction",
                       "ocr_runtime", "ocr_selftest", "analysis_selftest", "visual_survey_review",
                       "analysis_runs", "import_session", "workspace_shell",
                       "workspace_analyze", "workspace_questionnaires", "workspace_methods",
                       "workspace_components", "workspace_tokens", "workspace_text",
                       "workspace_state", "workspace_routes", "app_identity", "app_paths",
                       "legacy_data", "data_ui"):
            if module not in modules:
                raise SystemExit(f"Packaged application lacks module {module}")
        # The interface opens these; [tool.flet.app].exclude must never drop them.
        if not (root / "examples" / "sample_scale.csv").is_file():
            raise SystemExit("Packaged application lacks the example datasets")
        manifest = json.loads((bundle / "MANIFEST.json").read_text(encoding="utf-8"))
        print(f"Runtime files: {len(manifest['files'])}; Tesseract {manifest['tesseract_version']}")
        result = Path(temp) / "selftest.json"
        env = {
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "PATH": os.pathsep.join(filter(None, (
                os.path.join(os.environ.get("SYSTEMROOT", r"C:\Windows"), "System32"),
                os.environ.get("SYSTEMROOT", r"C:\Windows"),
            ))),
            "TEMP": temp, "TMP": temp, "PYTHONUTF8": "1", "MPLBACKEND": "Agg",
        }
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import ocr_runtime, ocr_selftest;"
            "from pathlib import Path;"
            "check = ocr_runtime.verify_bundle(Path(sys.argv[1]) / 'bundled_ocr' / 'windows-x64', full_hash=True);"
            "print('bundle', check);"
            "assert check.ok, check.problems;"
            "sys.exit(ocr_selftest.run_selftest(Path(sys.argv[2])))"
        )
        process = subprocess.run(
            [sys.executable, "-c", code, str(root), str(result)],
            env=env, cwd=temp, timeout=600, check=False,
        )
        if result.is_file():
            print(result.read_text(encoding="utf-8"))
            verdict = json.loads(result.read_text(encoding="utf-8"))
            if verdict.get("origin") != "bundled":
                raise SystemExit(f"Self-test used {verdict.get('origin')} engine, not bundled")
        if process.returncode:
            raise SystemExit(f"Packaged OCR self-test failed ({process.returncode})")
    print("Packaged OCR runtime verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
