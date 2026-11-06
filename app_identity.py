"""Identity and version of this build (Stage 35, #44 and #45).

The application knows its name, version (SemVer), channel, build and the
project format it writes. A source checkout reports the version below on
the "source" channel. A distributed build carries ``build_info.json``
(written by ``tools/write_build_info.py`` before ``flet build``) with the
channel, CI build number, commit and the keys that may sign its updates.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

NAME = "Statistical Research Assistant"
APP_ID = "StatisticalResearchAssistant"
# Inno Setup AppId: the same value for every version, so an update replaces
# the installed program instead of installing a second copy. Never change it.
INSTALLER_APP_ID = "{8467540D-B8DC-4046-A878-0EE29F330E63}"
# Version of this source tree. A release tag v<VERSION> must match it.
VERSION = "1.0.0"
REPOSITORY = "adriano18/statistical-research-assistant"
# Named mutex held while the application runs; the installer waits for it.
MUTEX = "StatisticalResearchAssistant.Running"
BUILD_INFO = "build_info.json"
CHANNELS = ("stable", "preview")
UPDATE_ENDPOINTS = {
    # GitHub's "latest" release excludes drafts and pre-releases.
    "stable": f"https://github.com/{REPOSITORY}/releases/latest/download/sra-update-stable.json",
    "preview": f"https://github.com/{REPOSITORY}/releases/download/preview-channel/"
               "sra-update-preview.json",
}

_SEMVER = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    text: str = ""

    def _key(self):
        # SemVer 2.0 precedence: a pre-release sorts before its release;
        # numeric identifiers compare numerically and before text ones.
        pre = tuple((0, int(part), "") if part.isdigit() else (1, 0, part)
                    for part in self.prerelease)
        return (self.major, self.minor, self.patch, 0 if self.prerelease else 1, pre)

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __le__(self, other: "Version") -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: "Version") -> bool:
        return self._key() > other._key()

    def __ge__(self, other: "Version") -> bool:
        return self._key() >= other._key()

    def __eq__(self, other) -> bool:
        return isinstance(other, Version) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    @property
    def numeric(self) -> str:
        """Four numbers for Windows version resources (pre-releases share them)."""
        return f"{self.major}.{self.minor}.{self.patch}.0"

    def __str__(self) -> str:
        return self.text or f"{self.major}.{self.minor}.{self.patch}"


def parse_version(text: str) -> Version:
    """A SemVer 2.0 version; raises ValueError for anything else."""
    value = str(text).strip()
    match = _SEMVER.fullmatch(value)
    if not match or len(value) > 64:
        raise ValueError(f"Not a version: {text!r}")
    major, minor, patch, pre, _build = match.groups()
    return Version(int(major), int(minor), int(patch), tuple(pre.split(".")) if pre else (), value)


@dataclass(frozen=True)
class BuildInfo:
    version: str = VERSION
    channel: str = "source"          # "stable" | "preview" | "test" | "source"
    build: str = ""                  # CI run number
    commit: str = ""
    built_at: str = ""
    # Code signing of the distributed executable and installer.
    signed: bool = False
    publisher: str = ""              # expected certificate subject of updates
    publisher_thumbprints: tuple[str, ...] = ()
    require_signature: bool = False  # updates must carry a valid signature by `publisher`
    # Ed25519 public keys (base64) that may sign this build's update manifests.
    update_keys: tuple[str, ...] = ()
    update_endpoint: str = ""        # manifest URL; empty = the channel's default
    # Test builds only: also accept this http://127.0.0.1 endpoint.
    test_endpoint: str = ""

    @property
    def parsed_version(self) -> Version:
        return parse_version(self.version)

    @property
    def distributed(self) -> bool:
        return self.channel in ("stable", "preview", "test")

    @property
    def endpoint(self) -> str:
        return self.update_endpoint or UPDATE_ENDPOINTS.get(self.channel, "")


def _coerce(raw: dict) -> BuildInfo:
    values = {}
    for item in fields(BuildInfo):
        if item.name not in raw:
            continue
        value = raw[item.name]
        default = getattr(BuildInfo, item.name)
        if isinstance(default, bool):
            if isinstance(value, bool):
                values[item.name] = value
        elif isinstance(default, tuple):
            if isinstance(value, list) and all(isinstance(v, str) for v in value):
                values[item.name] = tuple(value)
        elif isinstance(value, str):
            values[item.name] = value.strip()
    info = BuildInfo(**values)
    try:
        info.parsed_version
    except ValueError:
        info = BuildInfo(**{**values, "version": VERSION, "channel": "source"})
    return info


def read_build_info(path: Path | None = None) -> BuildInfo:
    location = Path(path) if path is not None else Path(__file__).resolve().parent / BUILD_INFO
    try:
        raw = json.loads(location.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return BuildInfo()
    return _coerce(raw) if isinstance(raw, dict) else BuildInfo()


@lru_cache(maxsize=1)
def build_info() -> BuildInfo:
    return read_build_info()


def describe(info: BuildInfo | None = None) -> dict:
    """What "About" shows and what diagnostics record."""
    import platform

    info = info or build_info()
    try:
        from project_store import SCHEMA_VERSION
    except Exception:   # pragma: no cover - the store always imports
        SCHEMA_VERSION = None
    return {
        "name": NAME, "version": info.version, "channel": info.channel,
        "build": info.build or "-", "commit": (info.commit or "-")[:12],
        "built_at": info.built_at or "-", "signed": info.signed,
        "project_format": SCHEMA_VERSION, "python": platform.python_version(),
    }
