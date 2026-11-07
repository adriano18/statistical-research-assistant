"""Where the application keeps a researcher's data (Stage 35, #44).

Every project, questionnaire, response and the researcher profile live in
one per-user data folder, never in the program folder. Installing, updating
or uninstalling the program therefore cannot change or remove research
data, and a new version always finds the data of the previous one.

| Situation | Data folder |
|---|---|
| ``SRA_DATA_DIR`` set (tests, portable use) | ``$SRA_DATA_DIR`` |
| Packaged build on Windows | ``%LOCALAPPDATA%\\StatisticalResearchAssistant`` |
| Packaged build elsewhere | Flet's per-user data folder (``FLET_APP_STORAGE_DATA``) |
| Source checkout | ``<repo>/data`` (git-ignored) |

On Windows the folder no longer depends on the company and product names
written into the executable (Flet's own folder is
``%APPDATA%\\<company>\\<product>\\data``; preview builds had the
placeholder company "Your Company"). Data that earlier versions kept
elsewhere is found and copied on request by ``legacy_data``; it is never
used in place, moved or deleted.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_FOLDER = "StatisticalResearchAssistant"


def _packaged() -> bool:
    from startup_diagnostics import is_packaged

    return is_packaged()


def _windows() -> bool:
    return os.name == "nt"


def data_root(source_root: Path) -> Path:
    """The folder that holds ``projects``, ``surveys`` and ``profile``."""
    override = os.environ.get("SRA_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if _packaged():
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if _windows() and local:
            return Path(local) / APP_FOLDER
        flet = os.environ.get("FLET_APP_STORAGE_DATA", "").strip()
        if flet:
            return Path(flet)
    return Path(source_root) / "data"


def projects_root(source_root: Path) -> Path:
    return data_root(source_root) / "projects"


def surveys_root(source_root: Path) -> Path:
    return data_root(source_root) / "surveys"


def updates_root(source_root: Path) -> Path:
    """Downloaded and verified updates; a cache, safe to delete."""
    return data_root(source_root) / "updates"
