"""One settings file per user for the whole application (Stage 37, issue #68).

Before Stage 37 the program's own settings were kept in four places:
``~/.statistical_research_assistant/preferences.json`` (language, recent data
files, the classic corner style), ``workspace.json`` beside it (the
workspace's accent colour), the language of the optional researcher profile,
and state that only lived in memory (theme, window, sidebar, last page;
review findings D1 and D2). They now live in one file,
``<data folder>/settings.json`` (``app_paths.data_root``): per user and
outside the program folder, so installing, updating or uninstalling the
program never changes it, and a portable data folder (``SRA_DATA_DIR``)
carries its own settings.

Rules
-----
* The first start of this version copies what the old files hold into the
  new file (:func:`migrate_legacy`). The old files are only read: they are
  never changed, moved or deleted, so an earlier version still finds them.
* A value this version does not know (a language, theme or key written by a
  later version) is kept in the file exactly as it is. The program shows its
  own default instead, and every save writes only the keys that changed, so
  such a value is never silently replaced; a Russian preference is never
  reset to English.
* Every write is atomic (temporary file, fsync, replace). A write that fails
  never stops the program: the change applies to this session and
  :attr:`UserSettings.error` says why it was not kept.
* :meth:`UserSettings.reset` ("Reset settings") writes the defaults. It never
  touches research data: projects, questionnaires, responses, backups, the
  researcher profile and AI keys live elsewhere.

What stays elsewhere, on purpose: the update check's state
(``updates/state.json``, read by the updater and its helper), the researcher
profile (personal entries with their own Delete button) and the AI provider
settings (keys in the computer's credential store).

No Flet imports: the launcher reads the language and window from here
before the user interface is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
FILE_NAME = "settings.json"
DAMAGED_NAME = "settings.damaged.json"
FORMAT = 1

LANGUAGES = ("en", "lv", "ru")
QUICK_LANGUAGES = ("en", "lv")          # the top bar; Russian is in Settings and the globe menu
LANGUAGE_NAMES = {"en": "English", "lv": "Latviešu", "ru": "Русский"}
THEMES = ("light", "dark", "system")
ACCENTS = ("blue", "teal", "violet", "graphite")     # workspace_tokens.ACCENTS (tested)
CORNERS = ("windows", "macos")
TEXT_SCALES = (90, 100, 110, 125)       # per cent of the design sizes
DENSITIES = ("comfortable", "compact")
TYPEFACES = ("segoe", "segoe_variable")
START_INTERFACES = ("workspace", "classic")
# Pages the program may remember as "where you were" (workspace routes).
ROUTES = ("home", "project", "data", "questionnaires", "import", "analyze", "results",
          "reports", "charts", "settings", "help")
MAX_RECENTS = 8
MAX_PATH = 4096

DEFAULTS: dict[str, Any] = {
    "language": "en",
    "theme": "light",
    "accent": "blue",
    "corners": "windows",
    "text_scale": 100,
    "density": "comfortable",
    "typeface": "segoe",
    "start_interface": "workspace",
    "sidebar_expanded": None,      # None: chosen by the window width
    "last_route": "home",
    "last_project": None,
    "window": None,                # {"width", "height", "left", "top", "maximized"}
    "recent_files": [],
}

_LOCK = threading.Lock()


def _window(value: Any) -> dict | None:
    """A saved window: sizes and position in logical pixels, or None."""
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    for key, low, high in (("width", 400, 20000), ("height", 300, 20000)):
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) or not low <= number <= high:
            return None
        out[key] = round(float(number), 1)
    for key in ("left", "top"):
        number = value.get(key)
        if number is None:
            continue
        if isinstance(number, bool) or not isinstance(number, (int, float)) \
                or not math.isfinite(number) or not -40000 <= number <= 40000:
            return None
        out[key] = round(float(number), 1)
    out["maximized"] = value.get("maximized") is True
    return out


def _recent(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [item for item in value[:MAX_RECENTS]
            if isinstance(item, str) and 0 < len(item) <= MAX_PATH]


def _in(choices) -> Callable[[Any], Any]:
    return lambda value: value if isinstance(value, (str, int)) and not isinstance(value, bool) \
        and value in choices else None


# Each validator returns the value as the program uses it, or None when this
# version does not know it (the default is shown; the stored value is kept).
VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "language": _in(LANGUAGES),
    "theme": _in(THEMES),
    "accent": _in(ACCENTS),
    "corners": _in(CORNERS),
    "text_scale": _in(TEXT_SCALES),
    "density": _in(DENSITIES),
    "typeface": _in(TYPEFACES),
    "start_interface": _in(START_INTERFACES),
    "sidebar_expanded": lambda value: value if isinstance(value, bool) else None,
    "last_route": _in(ROUTES),
    "last_project": lambda value: value if isinstance(value, str) and 0 < len(value) <= 200
    else None,
    "window": _window,
    "recent_files": _recent,
}
# Keys whose None is a meaningful value ("not chosen"), not an unknown one.
NULLABLE = {"sidebar_expanded", "last_project", "window"}


def settings_path(source_root: Path | None = None) -> Path:
    """``<data folder>/settings.json`` (``app_paths.data_root``)."""
    import app_paths

    return app_paths.data_root(Path(source_root or ROOT)) / FILE_NAME


def path_for(data_root: Path) -> Path:
    """The settings file of a data folder (the folder that holds ``projects``)."""
    return Path(data_root) / FILE_NAME


@dataclass(frozen=True)
class LegacySources:
    """Where earlier versions kept the settings this file replaces."""

    preferences: Path | None = None      # ~/.statistical_research_assistant/preferences.json
    workspace: Path | None = None        # workspace.json beside it (accent)
    profile: Path | None = None          # <data folder>/profile/profile.json (language)


def legacy_sources(data_root: Path) -> LegacySources:
    import app_preferences

    preferences = app_preferences.preferences_path()
    return LegacySources(preferences, preferences.parent / "workspace.json",
                         Path(data_root) / "profile" / "profile.json")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path | None) -> Any:
    """The JSON content of ``path``; None if it is absent or unreadable."""
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def _read(path: Path) -> tuple[str, dict]:
    """("ok", data), ("missing", {}) or ("damaged", {})."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", {}
    except (OSError, UnicodeError):
        return "damaged", {}
    try:
        data = json.loads(text)
    except ValueError:
        return "damaged", {}
    return ("ok", data) if isinstance(data, dict) else ("damaged", {})


def _write(path: Path, data: dict) -> None:
    """Atomic write: a temporary file in the same folder, fsync, replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".settings-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _legacy_language(sources: LegacySources) -> str | None:
    """The language an earlier version showed, as the researcher chose it.

    Earlier versions kept the language twice: ``preferences.json`` (the
    classic interface, the splash and the workspace without a profile) and
    the researcher profile (the workspace). English is the default of both,
    so a language other than English is a choice the researcher made: it is
    kept over English, wherever it was stored. If both name different
    non-English languages, the profile's (the workspace's) is kept."""
    preferences = _read_json(sources.preferences)
    from_preferences = preferences.get("language") if isinstance(preferences, dict) else None
    profile = _read_json(sources.profile)
    data = profile.get("profile", profile) if isinstance(profile, dict) else None
    from_profile = data.get("language") if isinstance(data, dict) else None
    found = [value for value in (from_profile, from_preferences)
             if isinstance(value, str) and value.strip()]
    if not found:
        return None
    chosen = [value for value in found if value != "en"]
    return chosen[0] if chosen else found[0]


def migrate_legacy(sources: LegacySources) -> dict:
    """The new file's content from the files of earlier versions (only read)."""
    raw: dict[str, Any] = {"format": FORMAT}
    used = []
    preferences = _read_json(sources.preferences)
    if isinstance(preferences, dict):
        used.append("preferences.json")
        recent = _recent(preferences.get("recent_files"))
        if recent:
            raw["recent_files"] = recent
        appearance = preferences.get("appearance")
        if isinstance(appearance, str) and appearance.strip():
            raw["corners"] = appearance          # kept as written, even if unknown here
    workspace = _read_json(sources.workspace)
    if isinstance(workspace, dict):
        used.append("workspace.json")
        accent = workspace.get("accent")
        if isinstance(accent, str) and accent.strip():
            raw["accent"] = accent
    profile = _read_json(sources.profile)
    if isinstance(profile, dict):
        used.append("profile.json")
    language = _legacy_language(sources)
    if language is not None:
        raw["language"] = language
    raw["migrated"] = {"from": used, "at": _now()}
    return raw


class UserSettings:
    """The settings file of one data folder, as read at start and kept current."""

    def __init__(self, path: Path, raw: dict | None = None):
        self.path = Path(path)
        self._raw: dict = dict(raw or {})
        self.error: str | None = None      # why the last change could not be saved
        self._damaged = False

    # ------------------------------------------------------------ loading
    @classmethod
    def load(cls, path: Path | None = None, *, legacy: LegacySources | None = None,
             migrate: bool = True) -> "UserSettings":
        """Read the file; on the first start of this version, migrate.

        Never raises: an unreadable file gives the defaults (and is kept
        aside as ``settings.damaged.json`` before anything new is saved)."""
        path = Path(path) if path is not None else settings_path()
        status, raw = _read(path)
        settings = cls(path, raw)
        if status == "damaged":
            settings._damaged = True
        elif status == "missing" and migrate:
            try:
                sources = legacy if legacy is not None else legacy_sources(path.parent)
            except Exception:
                sources = LegacySources()
            settings._raw = migrate_legacy(sources)
            settings._save(settings._raw)
        return settings

    # ------------------------------------------------------------ reading
    def stored(self, key: str) -> Any:
        """The value in the file as written (None when absent)."""
        return self._raw.get(key)

    def is_set(self, key: str) -> bool:
        return key in self._raw and self._raw[key] is not None

    def known(self, key: str) -> bool:
        """The stored value is one this version knows (or there is none)."""
        if key not in self._raw or (self._raw[key] is None and key in NULLABLE):
            return True
        return VALIDATORS[key](self._raw[key]) is not None

    def get(self, key: str) -> Any:
        """The value the program uses: the stored one if valid, else the default."""
        if key not in VALIDATORS:
            raise KeyError(key)
        value = self._raw.get(key)
        if value is None:
            default = DEFAULTS[key]
            return list(default) if isinstance(default, list) else default
        checked = VALIDATORS[key](value)
        if checked is None:
            default = DEFAULTS[key]
            return list(default) if isinstance(default, list) else default
        return checked

    def as_dict(self) -> dict:
        return {key: self.get(key) for key in VALIDATORS}

    @property
    def raw(self) -> dict:
        return dict(self._raw)

    # ------------------------------------------------------------ writing
    def update(self, **changes) -> bool:
        """Save the changed keys (and only those); True when written.

        Refuses a value this version does not offer (ValueError); the file is
        read again first, so keys another part of the program wrote meanwhile
        are kept."""
        for key, value in changes.items():
            if key not in VALIDATORS:
                raise ValueError(f"Unknown setting: {key}")
            if value is None and key in NULLABLE:
                continue
            if VALIDATORS[key](value) is None:
                raise ValueError(f"{key}: {value!r} is not offered")
        values = {key: (list(value) if isinstance(value, (list, tuple)) else value)
                  for key, value in changes.items()}
        with _LOCK:
            # The file as it is now: another part of the program (the classic
            # screens, the launcher's window keeper) may have written it.
            status, current = _read(self.path)
            base = dict(current) if status == "ok" else dict(self._raw)
            if status == "damaged":
                self._damaged = True
            if status == "ok" and all(key in base and base[key] == value
                                      for key, value in values.items()):
                self._raw = base
                self.error = None
                return True                      # already so: nothing to write
            base.update(values)
            if not isinstance(base.get("format"), int) or base["format"] < FORMAT:
                base["format"] = FORMAT        # a newer version's format number is kept
            self._raw = base
            return self._save(base)

    def reset(self) -> bool:
        """Every setting back to its default ("Reset settings"); research
        data is never touched. The record of the migration is kept, so the
        files of earlier versions are not read again."""
        migrated = self._raw.get("migrated")
        base = {"format": FORMAT, "reset_at": _now()}
        if migrated is not None:
            base["migrated"] = migrated
        with _LOCK:
            self._raw = base
            return self._save(base)

    def _save(self, data: dict) -> bool:
        try:
            if self._damaged and self.path.exists():
                # Keep the unreadable file for support instead of losing it.
                os.replace(self.path, self.path.with_name(DAMAGED_NAME))
            self._damaged = False
            _write(self.path, data)
        except OSError as error:
            self.error = f"{type(error).__name__}: {error}"
            return False
        self.error = None
        return True


def load_quietly(path: Path | None = None) -> UserSettings:
    """For the launcher: the settings, or the defaults if anything fails."""
    try:
        return UserSettings.load(path)
    except Exception:
        return UserSettings(Path(path) if path is not None else Path(FILE_NAME))


def start_interface_override() -> str | None:
    """``SRA_UI=workspace|classic`` starts that interface for this run only
    (tests, support); the stored choice is not changed."""
    value = os.environ.get("SRA_UI", "").strip().lower()
    return value if value in START_INTERFACES else None
