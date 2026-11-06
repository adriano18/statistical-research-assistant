"""Research data that earlier versions kept outside today's data folder.

Stage 35 (#44). Preview builds stored projects, questionnaires and the
researcher profile in Flet's per-user folder
(``%APPDATA%\\Your Company\\Statistical Research Assistant\\data`` on
Windows: "Your Company" was the build's placeholder company name), and the
oldest previews kept questionnaires inside the folder they were unpacked
to. The installed application keeps everything in ``app_paths.data_root``.

This module looks only in those known places, and in a folder the
researcher chooses; it never searches the disk. It shows what it would copy
(``Source.items``), copies on request, checks every copy against its
original and records what it did in ``<data folder>/migration.json``. It
never moves, changes or deletes an original, and never replaces anything
already in the data folder: a project or questionnaire that exists there
with other content is reported as a conflict and left alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

RECORD = "migration.json"
RECORD_FORMAT = 1
PROJECT_DB = "project.sqlite3"
PROFILE = Path("profile") / "profile.json"
# The Flet data folder of every preview build (company placeholder).
PREVIEW_FOLDER = ("Your Company", "Statistical Research Assistant", "data")
SKIPPED_NAMES = {"project.lock"}
SKIPPED_SUFFIXES = ("-wal", "-shm", "-journal")
MAX_SCAN_DIRECTORIES = 4000
MAX_SCAN_DEPTH = 6


class MigrationError(Exception):
    """A copy could not be completed; the original is unchanged."""


@dataclass(frozen=True)
class Item:
    kind: str           # "project" | "questionnaire" | "profile"
    title: str
    source: Path
    target: Path
    digest: str         # content digest of the original
    size: int           # bytes on disk
    # "new": not in the data folder yet; "copied": copied earlier and
    # unchanged since; "present": the same content is already there;
    # "conflict": other content is there under the same identity;
    # "changed": copied earlier, then changed in the earlier version.
    state: str = "new"


@dataclass(frozen=True)
class Source:
    folder: Path
    kind: str           # "preview" | "portable" | "chosen"
    items: tuple[Item, ...] = ()

    @property
    def pending(self) -> tuple[Item, ...]:
        return tuple(item for item in self.items if item.state == "new")

    def count(self, kind: str, state: str = "new") -> int:
        return sum(1 for item in self.items if item.kind == kind and item.state == state)


@dataclass(frozen=True)
class Report:
    copied: tuple[Item, ...] = ()
    skipped: tuple[tuple[Item, str], ...] = ()
    failed: tuple[tuple[Item, str], ...] = ()
    record: Path | None = None
    stopped: str = ""   # why copying stopped early, if it did

    @property
    def ok(self) -> bool:
        return not self.failed and not self.stopped


# ----------------------------------------------------------------- digests

def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def database_digest(path: Path) -> str:
    """Digest of a SQLite database's content (schema, rows, format number),
    independent of page layout, so a copy made with the backup API compares
    equal to its original, including changes still in the WAL file."""
    digest = hashlib.sha256()
    with closing(_read_only(path)) as db:
        digest.update(f"user_version={db.execute('PRAGMA user_version').fetchone()[0]}\n".encode())
        for line in db.iterdump():
            digest.update(line.encode("utf-8", "surrogatepass"))
            digest.update(b"\n")
    return digest.hexdigest()


def _skipped(path: Path) -> bool:
    return path.name in SKIPPED_NAMES or path.name.endswith(SKIPPED_SUFFIXES)


def _project_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*")
                  if p.is_file() and not p.is_symlink() and not _skipped(p))


def project_digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in _project_files(folder):
        relative = path.relative_to(folder).as_posix()
        value = database_digest(path) if relative == PROJECT_DB else _file_digest(path)
        digest.update(f"{relative}\0{value}\n".encode())
    return digest.hexdigest()


def _digest(kind: str, path: Path) -> str:
    if kind == "project":
        return project_digest(path)
    if kind == "questionnaire":
        return database_digest(path)
    return _file_digest(path)


def _size(path: Path) -> int:
    if path.is_dir():
        return sum(p.stat().st_size for p in _project_files(path))
    return path.stat().st_size


# ------------------------------------------------------------------ record

def _record_path(data_root: Path) -> Path:
    return Path(data_root) / RECORD


def load_record(data_root: Path) -> dict:
    try:
        raw = json.loads(_record_path(data_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    copied = raw.get("copied") if isinstance(raw.get("copied"), list) else []
    dismissed = raw.get("dismissed") if isinstance(raw.get("dismissed"), dict) else {}
    return {"format": RECORD_FORMAT, "copied": [entry for entry in copied if isinstance(entry, dict)],
            "dismissed": dismissed}


def _save_record(data_root: Path, record: dict) -> Path:
    path = _record_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".migration-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=1)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return path


def _key(path: Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def dismiss(folder: Path, data_root: Path) -> None:
    """The researcher chose "Not now": do not offer this folder at startup again."""
    record = load_record(data_root)
    record["dismissed"][_key(folder)] = _now()
    _save_record(data_root, record)


def is_dismissed(folder: Path, data_root: Path) -> bool:
    return _key(folder) in load_record(data_root)["dismissed"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------- discovery

def _inside(path: Path, folder: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(folder).resolve())
        return True
    except ValueError:
        return False


def known_folders(source_root: Path, data_root: Path) -> list[tuple[Path, str]]:
    """Data folders of earlier versions, in the places they are known to use."""
    from startup_diagnostics import is_packaged

    candidates: list[tuple[Path, str]] = []
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        candidates.append((Path(appdata).joinpath(*PREVIEW_FOLDER), "preview"))
    if is_packaged():
        flet = os.environ.get("FLET_APP_STORAGE_DATA", "").strip()
        if flet:
            candidates.append((Path(flet), "preview"))
        candidates.append((Path(source_root) / "data", "portable"))
    seen, found = set(), []
    for folder, kind in candidates:
        key = _key(folder)
        if key in seen or not folder.is_dir():
            continue
        seen.add(key)
        if _inside(folder, data_root) or _inside(data_root, folder):
            continue
        found.append((folder, kind))
    return found


def _title(db_path: Path, table: str) -> str:
    try:
        with closing(_read_only(db_path)) as db:
            row = db.execute(f"SELECT title FROM {table} LIMIT 1").fetchone()
        return str(row[0]) if row and row[0] else db_path.stem
    except sqlite3.DatabaseError:
        return ""


def _candidates(folder: Path, data_root: Path) -> Iterable[tuple[str, str, Path, Path]]:
    """(kind, title, source, target) for every item an earlier version saved."""
    projects = folder / "projects"
    if projects.is_dir():
        for path in sorted(projects.iterdir()):
            if path.is_symlink() or not path.is_dir() or path.name.startswith("."):
                continue
            try:
                uuid.UUID(path.name)
            except ValueError:
                continue
            if (path / PROJECT_DB).is_file():
                title = _title(path / PROJECT_DB, "project")
                if title:
                    yield "project", title, path, Path(data_root) / "projects" / path.name
    surveys = folder / "surveys"
    if surveys.is_dir():
        for path in sorted(surveys.glob("survey_*.sqlite3")):
            if path.is_file() and not path.is_symlink():
                title = _title(path, "survey")
                if title:
                    yield "questionnaire", title, path, Path(data_root) / "surveys" / path.name
    profile = folder / PROFILE
    if profile.is_file() and not profile.is_symlink():
        yield "profile", "", profile, Path(data_root) / PROFILE


def inspect(folder: Path, data_root: Path, kind: str = "chosen") -> Source | None:
    """What ``folder`` (an earlier version's data folder) holds, with the
    state of each item against the data folder; None if it holds nothing."""
    folder = Path(folder)
    if not folder.is_dir() or _inside(folder, data_root):
        return None
    record = load_record(data_root)
    copied = {(_key(Path(entry.get("source", ""))), entry.get("digest")) for entry in record["copied"]}
    copied_sources = {source for source, _ in copied}
    items = []
    for item_kind, title, source, target in _candidates(folder, data_root):
        try:
            digest = _digest(item_kind, source)
            size = _size(source)
        except (OSError, sqlite3.DatabaseError):
            continue
        key = _key(source)
        if (key, digest) in copied:
            state = "copied"
        elif target.exists():
            try:
                same = _digest(item_kind, target) == digest
            except (OSError, sqlite3.DatabaseError):
                same = False
            state = "present" if same else ("changed" if key in copied_sources else "conflict")
        else:
            state = "changed" if key in copied_sources else "new"
        items.append(Item(item_kind, title, source, target, digest, size, state))
    return Source(folder, kind, tuple(items)) if items else None


def find(source_root: Path, data_root: Path) -> list[Source]:
    """Earlier versions' data in the known places."""
    found = []
    for folder, kind in known_folders(source_root, data_root):
        source = inspect(folder, data_root, kind)
        if source is not None:
            found.append(source)
    return found


def find_in(chosen: Path, data_root: Path) -> list[Source]:
    """Earlier versions' data inside a folder the researcher chose, such as
    the folder a portable preview was unpacked to. Only that folder is
    searched (a few levels deep), for folders that hold ``projects``,
    ``surveys`` or ``profile``."""
    chosen = Path(chosen)
    found: list[Source] = []
    queue, visited = [(chosen, 0)], 0
    while queue and visited < MAX_SCAN_DIRECTORIES:
        folder, depth = queue.pop(0)
        visited += 1
        if _inside(folder, data_root):
            continue
        if any((folder / name).is_dir() for name in ("projects", "surveys")) or (folder / PROFILE).is_file():
            source = inspect(folder, data_root, "chosen")
            if source is not None:
                found.append(source)
                continue
        if depth >= MAX_SCAN_DEPTH:
            continue
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir() and not p.is_symlink())
        except OSError:
            continue
        queue.extend((child, depth + 1) for child in children
                     if child.name not in {"projects", "surveys", "site-packages", "__pycache__"})
    return found


# ----------------------------------------------------------------- copying

def _copy_database(source: Path, target: Path) -> None:
    with closing(_read_only(source)) as db, closing(sqlite3.connect(target)) as out:
        db.backup(out)
    with closing(sqlite3.connect(target)) as out:
        if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MigrationError(f"The copy of {source.name} failed its integrity check.")


def _copy_project(item: Item) -> None:
    staging = item.target.parent / f".migrating-{item.source.name}-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True)
    try:
        for path in _project_files(item.source):
            relative = path.relative_to(item.source)
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative.as_posix() == PROJECT_DB:
                _copy_database(path, destination)
            else:
                shutil.copy2(path, destination)
        if project_digest(staging) != item.digest:
            raise MigrationError("The copied project differs from the original "
                                 "(it may have changed while it was copied).")
        if item.target.exists():
            raise MigrationError("A project with the same identity appeared in the data folder.")
        os.replace(staging, item.target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _copy_file(item: Item) -> None:
    item.target.parent.mkdir(parents=True, exist_ok=True)
    staging = item.target.parent / f".migrating-{uuid.uuid4().hex[:8]}-{item.target.name}"
    try:
        if item.kind == "questionnaire":
            _copy_database(item.source, staging)
        else:
            shutil.copy2(item.source, staging)
        if _digest(item.kind, staging) != item.digest:
            raise MigrationError("The copy differs from the original "
                                 "(it may have changed while it was copied).")
        if item.target.exists():
            raise MigrationError("The same item appeared in the data folder.")
        os.replace(staging, item.target)
    except BaseException:
        staging.unlink(missing_ok=True)
        raise


def copy_items(source: Source, data_root: Path, *,
               progress: Callable[[int, int, Item], None] | None = None) -> Report:
    """Copy every pending item of ``source`` into the data folder.

    Each item is copied to a staging name, compared with its original and
    only then given its final name, so an interrupted copy leaves nothing
    half-written behind. Originals are only read.
    """
    data_root = Path(data_root)
    pending = source.pending
    copied, skipped, failed = [], [], []
    for item in source.items:
        if item.state != "new":
            skipped.append((item, item.state))
    record = load_record(data_root)
    stopped = ""
    for number, item in enumerate(pending, start=1):
        if progress is not None:
            progress(number, len(pending), item)
        try:
            if item.target.exists():
                skipped.append((item, "conflict"))
                continue
            if item.kind == "project":
                _copy_project(item)
            else:
                _copy_file(item)
        except OSError as error:
            failed.append((item, str(error)))
            if getattr(error, "errno", None) == 28:   # ENOSPC: no point going on
                stopped = "disk_full"
                break
            continue
        except (MigrationError, sqlite3.DatabaseError) as error:
            failed.append((item, str(error)))
            continue
        copied.append(replace(item, state="copied"))
        record["copied"].append({"kind": item.kind, "title": item.title,
                                 "source": str(item.source), "target": str(item.target),
                                 "digest": item.digest, "at": _now()})
        _save_record(data_root, record)
    path = _record_path(data_root) if copied else None
    return Report(tuple(copied), tuple(skipped), tuple(failed), path, stopped)
