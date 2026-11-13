"""Local desktop preferences only; never synchronize respondent data.

Since Stage 37 (issue #68) the preferences live in the one settings file of
``user_settings`` (``<data folder>/settings.json``). This module keeps the
interface the classic screens use: ``load_preferences()`` and
``save_preferences()`` without a path read and write that file.
``preferences_path()`` is where versions before Stage 37 kept them; the
settings file is made from it once, and it is never changed again. With an
explicit ``path`` the old single-file format is read and written as before.
"""

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
    """The preferences file of versions before Stage 37 (only read since)."""
    return Path.home() / ".statistical_research_assistant" / "preferences.json"


def _settings(path: Path | None = None):
    from user_settings import UserSettings

    return UserSettings.load(path)


def load_preferences(path: Path | None = None) -> AppPreferences:
    """English / Windows on first launch. A language or style this version
    does not know is shown as the default; the stored value is kept."""
    if path is not None:
        return _load_file(path)
    try:
        settings = _settings()
        return AppPreferences(settings.get("language"), tuple(settings.get("recent_files")),
                              settings.get("corners"))
    except Exception:
        return AppPreferences()


def update_preferences(**changes) -> Path:
    """Save only the given preferences (``language``, ``recent_files``,
    ``appearance``) in the settings file; raises OSError if it cannot be
    written, ValueError for a value that is not offered."""
    if "language" in changes and changes["language"] not in LANGUAGES:
        raise ValueError("Language must be en, lv or ru.")
    if "appearance" in changes and changes["appearance"] not in APPEARANCES:
        raise ValueError("Appearance must be windows or macos.")
    values = {}
    if "language" in changes:
        values["language"] = changes["language"]
    if "recent_files" in changes:
        values["recent_files"] = list(changes["recent_files"])[:MAX_RECENTS]
    if "appearance" in changes:
        values["corners"] = changes["appearance"]
    settings = _settings()
    if not settings.update(**values):
        raise OSError(settings.error or "the settings file could not be written")
    return settings.path


def save_preferences(
    preferences: AppPreferences, path: Path | None = None,
) -> Path:
    if preferences.language not in LANGUAGES:
        raise ValueError("Language must be en, lv or ru.")
    if preferences.appearance not in APPEARANCES:
        raise ValueError("Appearance must be windows or macos.")
    if path is not None:
        return _save_file(preferences, path)
    # Only what differs from the settings file as the program shows it is
    # written: a value the program shows as its default because this
    # version does not know it is never replaced by that default.
    current = load_preferences()
    changes = {}
    if preferences.language != current.language:
        changes["language"] = preferences.language
    if tuple(preferences.recent_files) != current.recent_files:
        changes["recent_files"] = preferences.recent_files
    if preferences.appearance != current.appearance:
        changes["appearance"] = preferences.appearance
    if not changes:
        return _settings().path
    return update_preferences(**changes)


def _load_file(location: Path) -> AppPreferences:
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


def _save_file(preferences: AppPreferences, destination: Path) -> Path:
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
