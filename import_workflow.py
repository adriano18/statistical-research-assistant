"""Reliable, testable input routing for client-selected research datasets.

FilePicker is a client-side gesture (ft.PickFiles). The result may contain a
local desktop path or bytes from a browser. No missing file is reported as a
successful import; cancellation is distinguishable from a load error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Any

# Stage 37 (#67): SPSS files, read by data_loader with pyreadstat.
SUPPORTED_EXTENSIONS = frozenset({".csv", ".tsv", ".xlsx", ".xlsm", ".sav", ".zsav"})
MAX_TRANSFER_BYTES = 25_000_000


@dataclass(frozen=True)
class ImportAttempt:
    successful: bool
    message: str
    cancelled: bool = False


async def import_picked_files(
    files: list[Any] | None,
    *,
    import_path: Callable[[str], Awaitable[bool]],
    import_bytes: Callable[[bytes, str], Awaitable[bool]],
) -> ImportAttempt:
    """Import one file selected by a real Flet FilePicker event.

    A returned True means that the downstream dataframe reader committed the
    data. The import_path/import_bytes callbacks must return bool explicitly;
    no success is inferred from the absence of exceptions.
    """
    if not files:
        return ImportAttempt(False, "File selection cancelled.", cancelled=True)

    picked = files[0]
    name = str(getattr(picked, "name", "") or "").strip()
    original_path = getattr(picked, "path", None)
    if original_path:
        name = name or Path(original_path).name
    if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        return ImportAttempt(
            False,
            "Unsupported file extension. Choose CSV, TSV, XLSX, XLSM or SAV.",
        )

    try:
        if original_path:
            ok = await import_path(str(original_path))
        else:
            contents = getattr(picked, "bytes", None)
            if not isinstance(contents, bytes):
                return ImportAttempt(
                    False, "No readable file path or file contents were returned "
                    "by the picker. In desktop mode use the full-path fallback.",
                )
            if len(contents) > MAX_TRANSFER_BYTES:
                return ImportAttempt(
                    False,
                    "Browser file exceeds the 25 MB in-memory import limit. "
                    "Open it in the desktop application.",
                )
            ok = await import_bytes(contents, name)
    except (OSError, ValueError, RuntimeError, TypeError) as error:
        return ImportAttempt(False, f"Import failed: {error}")
    return (
        ImportAttempt(True, f"Imported: {name}")
        if ok else ImportAttempt(False, "Import failed: see diagnostics in Dataset.")
    )
