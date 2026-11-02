"""In-memory analysis outputs and explicit user-selected local export.

Nothing is sent to a network service. Never cache source data in report files.
"""

from dataclasses import dataclass
from pathlib import Path


PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


@dataclass(frozen=True)
class AnalysisOutput:
    title: str
    report: str
    png: bytes | None = None


def save_selected_output(path: str | Path, output: AnalysisOutput, kind: str) -> Path:
    """Save to the exact user-selected desktop path; do not silently overwrite.

    FilePicker is responsible for allowing the user to choose the location.
    The destination directory must already exist.
    """
    destination = Path(path).expanduser()
    expected = ".txt" if kind == "text" else ".png" if kind == "image" else None
    if expected is None:
        raise ValueError("Unknown export kind.")
    if destination.suffix.lower() != expected:
        raise ValueError(f"Choose a destination ending in {expected}.")
    if not destination.parent.is_dir():
        raise FileNotFoundError("The destination folder does not exist.")

    if kind == "text":
        if not output.report.strip():
            raise ValueError("No report available for export.")
        payload = output.report.encode("utf-8")
    else:
        if not output.png or not output.png.startswith(PNG_SIGNATURE):
            raise ValueError("No valid PNG chart available for export.")
        payload = output.png

    # A file-picker may already confirm overwrite. This writes exactly
    # where the user explicitly selected, with no automatic cloud sync.
    destination.write_bytes(payload)
    return destination
