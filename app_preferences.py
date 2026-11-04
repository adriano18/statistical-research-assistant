"""Local desktop preferences only; never synchronize respondent data."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile


DEFAULT_LANGUAGE = "en"
LANGUAGES = {"en", "lv", "ru"}
MAX_RECENTS = 8
APPEARANCES = {"windows", "macos"}
DEFAULT_APPEARANCE = "windows"


@dataclass(frozen=True)
class AppPreferences:
    language: str = DEFAULT_LANGUAGE
    recent_files: tuple[str, ...] = ()
    appearance: str = DEFAULT_APPEARANCE


def preferences_path() -> Path:
    return Path.home() / ".statistical_research_assistant" / "preferences.json"


def load_preferences(path: Path | None = None) -> AppPreferences:
    location = path or preferences_path()
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return AppPreferences()
        language = raw.get("language", DEFAULT_LANGUAGE)
        if language not in LANGUAGES:
            language = DEFAULT_LANGUAGE
        files = raw.get("recent_files", [])
        if not isinstance(files, list):
            files = []
        recent = tuple(
            value for value in files[:MAX_RECENTS]
            if isinstance(value, str) and len(value) <= 4096
        )
        appearance = raw.get("appearance", DEFAULT_APPEARANCE)
        if appearance not in APPEARANCES:
            appearance = DEFAULT_APPEARANCE
        return AppPreferences(language, recent, appearance)
    except (FileNotFoundError, ValueError, OSError, TypeError):
        return AppPreferences()


def save_preferences(
    preferences: AppPreferences, path: Path | None = None,
) -> Path:
    if preferences.language not in LANGUAGES:
        raise ValueError("Language must be en, lv or ru.")
    if preferences.appearance not in APPEARANCES:
        raise ValueError("Appearance must be windows or macos.")
    destination = path or preferences_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Atomic update protects preferences from abrupt process termination.
    serialized = json.dumps({
        "language": preferences.language,
        "recent_files": list(preferences.recent_files[:MAX_RECENTS]),
        "appearance": preferences.appearance,
    }, ensure_ascii=False, indent=2)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".preferences-", suffix=".tmp", delete=False,
        ) as fh:
            temporary = Path(fh.name)
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def remember_file(
    preferences: AppPreferences, path: str | Path,
) -> AppPreferences:
    selected = Path(path).expanduser()
    if not selected.is_file():
        return preferences
    location = str(selected.resolve())
    unique = [location] + [
        old for old in preferences.recent_files if old != location
    ]
    return AppPreferences(
        preferences.language, tuple(unique[:MAX_RECENTS]),
        preferences.appearance,
    )
