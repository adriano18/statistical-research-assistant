"""Save already-computed, local-only reports and graphs.

Generated files go to the ignored reports/ folder, not a cloud service.
"""

from pathlib import Path


REPORTS = Path(__file__).resolve().parent / "reports"


def save_apa_txt(report: str, filename: str = "paired_APA7.txt") -> Path:
    if not report.strip():
        raise ValueError("Run an analysis before exporting its APA report.")
    if Path(filename).name != filename or not filename.endswith(".txt"):
        raise ValueError("Choose a simple .txt filename.")
    REPORTS.mkdir(parents=True, exist_ok=True)
    target = REPORTS / filename
    target.write_text(report, encoding="utf-8")
    return target


def save_figure_png(data: bytes, filename: str = "paired_figure.png") -> Path:
    if not data or not data.startswith(bytes.fromhex("89504e470d0a1a0a")):
        raise ValueError("Run an analysis to produce a valid PNG figure first.")
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise ValueError("Choose a simple .png filename.")
    REPORTS.mkdir(parents=True, exist_ok=True)
    target = REPORTS / filename
    target.write_bytes(data)
    return target
