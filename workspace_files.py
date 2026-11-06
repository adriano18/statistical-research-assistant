"""Saving files from the workspace: one path for every export.

Every save ends with an outcome the researcher can see: cancelled, saved
(with the full path of a file that exists and is not empty) or an
explanation of what went wrong and what to do next. No raw ``[Errno …]``
text reaches the screen.

Windows' save dialog may return the name exactly as it was typed, without
the extension of the chosen filter (``results`` instead of
``results.docx``); the extension is added here, so the exact file the
writer needs is the file the researcher gets.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import time
from typing import Callable


@dataclass(frozen=True)
class SaveOutcome:
    path: Path | None      # the verified file, or None (cancelled or failed)
    message: str
    tone: str              # success / info / danger

    @property
    def saved(self) -> bool:
        return self.path is not None


class NotWritten(OSError):
    """The writer returned but no (or an empty) file is there."""


def with_extension(path: Path, extension: str) -> Path:
    """``path`` ending in ``.extension``: the extension is appended (never
    swapped for a part of the name such as ``wave.2``)."""
    suffix = "." + extension.lower().lstrip(".")
    # Windows drops trailing dots and spaces from file names.
    name = path.name.rstrip(". ") or "untitled"
    if name.lower().endswith(suffix) and len(name) > len(suffix):
        return path.with_name(name)
    return path.with_name(name + suffix)


def write_verified(path: Path, writer: Callable[[Path], object]) -> Path:
    """Run ``writer(path)`` and return the file it wrote, checked on disk.

    ``writer`` may return the path it actually wrote (some writers normalise
    it); anything else means ``path``.
    """
    if not path.parent.is_dir():
        raise FileNotFoundError(errno.ENOENT, "folder missing", str(path.parent))
    result = writer(path)
    written = Path(result) if isinstance(result, (str, os.PathLike)) else path
    try:
        size = written.stat().st_size if written.is_file() else 0
    except OSError:
        size = 0
    if size <= 0:
        raise NotWritten(errno.EIO, "not written", str(written))
    return written


def remove_placeholder(chosen: Path, written: Path, since: float) -> None:
    """Remove the empty file a desktop save dialog may create at the name as
    typed, when the file was written under another name (an extension was
    added). Only a file that is empty and appeared during this save is
    touched; anything else is left alone."""
    if chosen == written:
        return
    try:
        stat = chosen.stat()
        if chosen.is_file() and stat.st_size == 0 and stat.st_mtime >= since - 2:
            chosen.unlink()
    except OSError:
        pass


def explain(error: BaseException, path: Path, t: Callable[..., str]) -> str:
    """A localized, actionable message for a failed save (``t`` translates)."""
    folder, name = str(path.parent), path.name
    if isinstance(error, NotWritten):
        return t("save.not_written", name=name, folder=folder)
    if isinstance(error, IsADirectoryError):
        return t("save.is_folder", name=name)
    if isinstance(error, PermissionError):
        return t("save.file_locked" if path.exists() else "save.folder_read_only",
                 name=name, folder=folder)
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        # The folder may exist and still refuse new files (for example
        # protected folders on Windows).
        return t("save.blocked" if path.parent.is_dir() else "save.folder_missing",
                 name=name, folder=folder)
    if isinstance(error, OSError):
        code = getattr(error, "errno", None)
        if code in (errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)):
            return t("save.disk_full", name=name, folder=folder)
        if code == errno.EROFS:
            return t("save.folder_read_only", name=name, folder=folder)
        if code in (errno.EINVAL, errno.ENAMETOOLONG):
            return t("save.bad_name", name=name)
        reason = getattr(error, "strerror", None) or type(error).__name__
        return t("save.failed_reason", name=name, reason=reason)
    reason = str(error).strip().rstrip(".") or type(error).__name__
    return t("save.failed_reason", name=name, reason=reason)


def now() -> float:
    return time.time()
