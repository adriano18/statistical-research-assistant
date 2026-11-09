"""Stage 36 synthetic fixtures for tests: generated once per test run.

The generator (tests/fixtures/stage36/generate_fixtures.py) is
deterministic and writes only invented content. Nothing here reads the
owner's private documents.
"""

from __future__ import annotations

import atexit
import importlib.util
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tests" / "fixtures" / "stage36" / "generate_fixtures.py"

CSV = "synthetic_ucla_sacs_55.csv"
DOCX_NUMBERED = "synthetic_cope_two_forms_60.docx"
DOCX_UNNUMBERED = "synthetic_cope_two_forms_60_unnumbered.docx"
SCAN_INLINE = "synthetic_sacs_scanned_52.pdf"
SCAN_TABLE_LV = "synthetic_lv_table_scan_52.pdf"

SCALES = ("AssertiveAction", "SocialJoining", "SeekingSocialSupport", "CautiousAction",
          "InstinctiveAction", "Avoidancen", "IndirectAction", "AntisocialAction")

_FOLDER: Path | None = None


def generator():
    spec = importlib.util.spec_from_file_location("stage36_generate_fixtures", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate(out_dir: Path) -> dict[str, Path]:
    module = generator()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = (module.create_csv(out_dir), module.create_docx(out_dir),
             module.create_scan_pdf(out_dir), module.create_docx_unnumbered(out_dir),
             module.create_lv_table_scan_pdf(out_dir))
    return {path.name: path for path in paths}


def fixture(name: str) -> Path:
    """The path of one generated fixture (generated on first use)."""
    global _FOLDER
    if _FOLDER is None:
        _FOLDER = Path(tempfile.mkdtemp(prefix="stage36-fixtures-"))
        atexit.register(shutil.rmtree, _FOLDER, True)
        generate(_FOLDER)
    path = _FOLDER / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path
