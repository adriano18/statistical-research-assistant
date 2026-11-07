"""Startup phase timing and local diagnostics logging (stdlib only).

Imported by the thin ``app.py`` launcher before Flet or any analysis
package, so it must stay dependency-free and fast. Each launch appends ONE
JSON line to ``startup.log`` with phase timings, the outcome and — on
failure — a traceback of *code locations*. It never records questionnaire
content, file names chosen by the user, dataset values or other personal
data.

Log folder (first writable wins):

1. ``SRA_LOG_DIR`` (tests / support override)
2. Windows: ``%LOCALAPPDATA%\\StatisticalResearchAssistant\\logs``
3. ``FLET_APP_STORAGE_DATA/logs`` (packaged Flet app data folder)
4. ``~/.statistical_research_assistant/logs``
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback

LOG_NAME = "startup.log"
MAX_LOG_BYTES = 512_000
KEEP_LINES = 200


def log_directories() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("SRA_LOG_DIR", "").strip()
    if override:
        candidates.append(Path(override))
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        candidates.append(Path(local) / "StatisticalResearchAssistant" / "logs")
    data = os.environ.get("FLET_APP_STORAGE_DATA", "").strip()
    if data:
        candidates.append(Path(data) / "logs")
    candidates.append(Path.home() / ".statistical_research_assistant" / "logs")
    return candidates


def writable_log_directory() -> Path | None:
    for folder in log_directories():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return folder
        except OSError:
            continue
    return None


def is_packaged() -> bool:
    """True inside a `flet build` desktop bundle (not a source checkout)."""
    return bool(os.environ.get("FLET_APP_STORAGE_DATA")) and not (
        Path(__file__).resolve().parent / ".git"
    ).exists()


class StartupTimeline:
    """Monotonic phase marks measured from interpreter-level start."""

    def __init__(self, started: float | None = None):
        self.started = time.perf_counter() if started is None else started
        self.phases: list[tuple[str, float]] = []
        self.outcome = "running"
        self.error: str | None = None

    def mark(self, name: str) -> float:
        elapsed = time.perf_counter() - self.started
        self.phases.append((str(name)[:60], round(elapsed, 3)))
        return elapsed

    def seconds(self, name: str) -> float | None:
        for phase, value in reversed(self.phases):
            if phase == name:
                return value
        return None

    def fail(self, error: BaseException) -> None:
        self.outcome = "failed"
        # Code locations and the exception type/message only: exception
        # messages from this application never embed questionnaire text.
        self.error = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )[-6000:]

    def succeed(self) -> None:
        self.outcome = "ok"

    def record(self) -> dict:
        return {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "outcome": self.outcome,
            "phases": [{"phase": p, "seconds": s} for p, s in self.phases],
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "packaged": is_packaged(),
            "error": self.error,
        }

    def summary(self) -> str:
        return ", ".join(f"{p} {s:.1f}s" for p, s in self.phases)


def write_startup_record(timeline: StartupTimeline) -> Path | None:
    """Append one JSON line; keep the file bounded. Never raises."""
    folder = writable_log_directory()
    if folder is None:
        return None
    target = folder / LOG_NAME
    try:
        line = json.dumps(timeline.record(), ensure_ascii=False)
        if target.exists() and target.stat().st_size > MAX_LOG_BYTES:
            kept = target.read_text(encoding="utf-8", errors="replace").splitlines()[-KEEP_LINES:]
            target.write_text("\n".join(kept) + "\n", encoding="utf-8")
        with target.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        return target
    except OSError:
        return None


def survey_data_root(source_root: Path) -> Path:
    """Where questionnaires are stored: ``<data folder>/surveys``.

    See ``app_paths``: a packaged build never stores them inside the
    program folder. Questionnaires an earlier unpacked preview saved there
    are offered for copying by ``legacy_data`` instead of being used in place.
    """
    from app_paths import surveys_root

    return surveys_root(source_root)
