"""Local-first research projects (Stage 34, issue #24).

A project is one folder under the per-user data root::

    projects/
      <project-id>/
        project.sqlite3          metadata, research questions, datasets and
                                 their versions, variable levels, preparation
                                 steps, questionnaire links, analysis runs,
                                 report selection, activity log
        datasets/<sha256><ext>   imported copies, content-addressed, never
                                 modified after writing
        figures/<run-id>.png     the chart of every saved analysis run
        project.lock             present while one app instance has it open
      .trash/<id>-<timestamp>/   deleted projects (recoverable)
      .backups/                  database copies taken before a migration

There is no separate catalog: the project list is the set of project
folders, each describing itself, so nothing can drift out of sync and a
crash cannot lose the index. Questionnaires stay in the existing survey
storage (``data/surveys`` or the packaged per-user folder) and are
*linked* by survey id; their definitions and published responses are never
moved or rewritten here.

Every analysis run stores what is needed to reproduce and audit it: method
key, variable roles, options, confirmations, measurement levels, the
dataset version (SHA-256 of its content), the report text and its SHA-256,
library versions and the time. A run becomes *stale* — never silently
deleted — when its dataset content or a measurement level it relied on
changes afterwards.

Backups are ``.sra`` packages: a ZIP with ``manifest.json`` (SHA-256 and
size of every file), a consistent database snapshot, the dataset copies,
figures and, optionally, the linked questionnaires. Imports verify every
checksum, reject unsafe paths and oversized archives, and never overwrite
an existing project or questionnaire.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import sqlite3
import stat
import sys
import tempfile
from typing import Any, Iterable
import uuid
import zipfile

SCHEMA_VERSION = 5
PACKAGE_FORMAT = "sra-project"
PACKAGE_VERSION = 1
DB_NAME = "project.sqlite3"
LOCK_NAME = "project.lock"
TRASH = ".trash"
BACKUPS = ".backups"
MAX_PACKAGE_FILES = 20_000
MAX_PACKAGE_BYTES = 4 * 1024 ** 3          # uncompressed
MAX_COMPRESSION_RATIO = 250                # per entry, above 10 MiB
DATASET_SUFFIXES = {".csv", ".xlsx", ".xls", ".tsv", ".txt"}
TABLE_SCHEMA_SUFFIX = ".schema.json"         # column types of a stored CSV copy
LIBRARIES = ("numpy", "scipy", "pandas", "statsmodels", "pingouin", "matplotlib",
             "scikit-learn", "openpyxl", "python-docx")
PROJECT_FIELDS = ("title", "description", "research_area", "population_notes",
                  "language", "design")


class ProjectError(Exception):
    """A project operation that cannot be completed as asked."""


class ProjectLocked(ProjectError):
    """Another running instance has the project open."""


class ProjectFormatError(ProjectError):
    """A project database or package this version cannot use safely."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def frame_sha256(frame) -> str:
    """Content hash of a table: column names, dtypes and values in order."""
    text = frame.to_csv(index=False, lineterminator="\n")
    dtypes = ",".join(f"{c}:{t}" for c, t in frame.dtypes.astype(str).items())
    return sha256_bytes((dtypes + "\n" + text).encode("utf-8"))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def library_versions() -> dict[str, str]:
    from importlib import metadata

    found = {"python": platform.python_version()}
    for name in LIBRARIES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    found["app_build"] = os.environ.get("SRA_BUILD_ID", "").strip() or "source checkout"
    return found


def project_data_root(source_root: Path) -> Path:
    """Folder holding all projects: ``<data folder>/projects`` (``app_paths``).

    ``SRA_DATA_DIR`` wins (tests, portable use); a packaged build uses the
    per-user data folder, never the program folder, so installing, updating
    or uninstalling the program never touches a project. A source checkout
    keeps ``<repo>/data/projects`` (git-ignored, next to ``data/surveys``).
    """
    from app_paths import projects_root

    return projects_root(source_root)


# ------------------------------------------------------------------ schema

V1_SCHEMA = """
        CREATE TABLE project (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            research_area TEXT NOT NULL DEFAULT '', population_notes TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'en', design TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at TEXT NOT NULL, modified_at TEXT NOT NULL, last_opened_at TEXT NOT NULL,
            active_dataset TEXT
        );
        CREATE TABLE research_questions (
            id TEXT PRIMARY KEY, position INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('question', 'hypothesis')),
            text TEXT NOT NULL, created_at TEXT NOT NULL, modified_at TEXT NOT NULL
        );
        CREATE TABLE datasets (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            origin TEXT NOT NULL CHECK (origin IN ('copy', 'link', 'derived', 'survey')),
            source_path TEXT, stored_path TEXT, sha256 TEXT NOT NULL,
            rows INTEGER NOT NULL, columns INTEGER NOT NULL,
            created_at TEXT NOT NULL, modified_at TEXT NOT NULL,
            parent_id TEXT REFERENCES datasets(id), survey_id TEXT, notes TEXT NOT NULL DEFAULT '',
            source_sha256 TEXT
        );
        CREATE TABLE dataset_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            sha256 TEXT NOT NULL, stored_path TEXT, rows INTEGER NOT NULL, columns INTEGER NOT NULL,
            recorded_at TEXT NOT NULL, reason TEXT NOT NULL
        );
        CREATE TABLE variables (
            dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            name TEXT NOT NULL, storage TEXT NOT NULL DEFAULT '', level TEXT,
            confirmed_in TEXT NOT NULL DEFAULT '', confirmed_at TEXT, label TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (dataset_id, name)
        );
        CREATE TABLE transformations (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
            position INTEGER NOT NULL, kind TEXT NOT NULL, params TEXT NOT NULL,
            output_columns TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE questionnaires (
            survey_id TEXT PRIMARY KEY, title TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'linked',
            linked_at TEXT NOT NULL
        );
        CREATE TABLE runs (
            id TEXT PRIMARY KEY, method TEXT NOT NULL, section TEXT NOT NULL, title TEXT NOT NULL,
            dataset_id TEXT REFERENCES datasets(id) ON DELETE SET NULL,
            dataset_sha256 TEXT NOT NULL, roles TEXT NOT NULL, options TEXT NOT NULL,
            confirms TEXT NOT NULL, confirmations TEXT NOT NULL, levels TEXT NOT NULL,
            report TEXT NOT NULL, report_sha256 TEXT NOT NULL, summary TEXT NOT NULL,
            interpretation TEXT NOT NULL, warnings TEXT NOT NULL, tables TEXT NOT NULL,
            figure TEXT, provenance TEXT NOT NULL, created_at TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '', descriptives TEXT NOT NULL DEFAULT '',
            guide TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE report_items (
            position INTEGER PRIMARY KEY, run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE CASCADE
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL,
            detail TEXT NOT NULL
        );
        """


def _create_v1(db: sqlite3.Connection) -> None:
    # One statement at a time: executescript() would commit the
    # transaction that migrate() opened.
    for statement in V1_SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)


# version -> migration that upgrades a database from version-1 to version.
# Version 1 creates a new database inside a staging folder (see create());
# later migrations must use execute(), not executescript(), so they run in
# the single transaction that migrate() opens.
def _migrate_v2(db: sqlite3.Connection) -> None:
    """Format 2: project-scoped permissions for a future AI assistant.

    Every source is off unless the researcher allows it; the table starts
    empty (= all off). ``data_anonymous`` records the researcher's own
    statement that the project's data rows identify nobody, which a future
    remote assistant would require before it may ever receive rows.
    Individual statements, not a script, so the change stays inside the
    migration's transaction."""
    db.execute("CREATE TABLE ai_permissions ("
               " source TEXT PRIMARY KEY,"
               " allowed INTEGER NOT NULL DEFAULT 0 CHECK (allowed IN (0, 1)),"
               " changed_at TEXT NOT NULL)")
    db.execute("ALTER TABLE project ADD COLUMN data_anonymous INTEGER NOT NULL DEFAULT 0")


def _migrate_v3(db: sqlite3.Connection) -> None:
    """Format 3 (#40): a versioned research plan. Every save adds a version
    (the latest is current); nothing is overwritten. ``runs_before`` is the
    number of analysis results the project held when the version was saved,
    which tells planned hypotheses from ones added after results were seen."""
    db.execute("CREATE TABLE plan_versions ("
               " id INTEGER PRIMARY KEY AUTOINCREMENT,"
               " saved_at TEXT NOT NULL, plan TEXT NOT NULL,"
               " runs_before INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '')")


def _migrate_v4(db: sqlite3.Connection) -> None:
    """Format 4 (Stage 36): research tasks, and runs that remember their
    task and the structured result they were built from.

    A research task keeps what the researcher chose (question, variables,
    method, options, confirmations, its hypothesis and interface state), so
    the task can be run again or continued after a restart. ``structured``
    holds the JSON of the engine's structured result, so numbers and figures
    come back without recalculating or parsing report text."""
    db.execute("CREATE TABLE research_tasks ("
               " id TEXT PRIMARY KEY, position INTEGER NOT NULL, title TEXT NOT NULL,"
               " goal TEXT NOT NULL, selection TEXT NOT NULL, method TEXT NOT NULL DEFAULT '',"
               " options TEXT NOT NULL DEFAULT '{}', confirms TEXT NOT NULL DEFAULT '{}',"
               " hypothesis_id TEXT, state TEXT NOT NULL DEFAULT '{}',"
               " created_at TEXT NOT NULL, modified_at TEXT NOT NULL)")
    db.execute("ALTER TABLE runs ADD COLUMN task_id TEXT")
    db.execute("ALTER TABLE runs ADD COLUMN structured TEXT")


def _migrate_v5(db: sqlite3.Connection) -> None:
    """Format 5 (Stage 36.4): the charts of a result.

    ``runs.charts`` holds the Chart Studio state of a run as JSON: the
    values the result's charts are drawn from (taken once from the dataset
    version the run rests on), the researcher's chart views and which view
    the Word report uses. Changing a view never changes the run's numbers."""
    db.execute("ALTER TABLE runs ADD COLUMN charts TEXT")


MIGRATIONS = {1: _create_v1, 2: _migrate_v2, 3: _migrate_v3, 4: _migrate_v4, 5: _migrate_v5}


def _connect(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    else:
        db = sqlite3.connect(path)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA foreign_keys=ON")
    db.row_factory = sqlite3.Row
    return db


def migrate(path: Path, backups: Path) -> int:
    """Bring a project database to SCHEMA_VERSION; returns the version found.

    The format is read through a read-only connection first: a database
    written by a newer version (after a downgrade or a failed update) is
    refused without any write, not even the journal-mode switch that a
    read-write connection makes."""
    if Path(path).exists():
        with closing(_connect(path, read_only=True)) as db:
            found = db.execute("PRAGMA user_version").fetchone()[0]
        if found > SCHEMA_VERSION:
            raise ProjectFormatError(
                f"This project was saved by a newer version (format {found}); "
                f"this version reads up to format {SCHEMA_VERSION}.")
        if found == SCHEMA_VERSION:
            return found
    with closing(_connect(path)) as db:
        found = db.execute("PRAGMA user_version").fetchone()[0]
        if found > SCHEMA_VERSION:
            raise ProjectFormatError(
                f"This project was saved by a newer version (format {found}); "
                f"this version reads up to format {SCHEMA_VERSION}.")
        if found == SCHEMA_VERSION:
            return found
        if found > 0:  # keep the old database before changing it
            backups.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            with closing(sqlite3.connect(backups / f"{path.parent.name}-v{found}-{stamp}.sqlite3")) as copy:
                db.backup(copy)
        # One explicit transaction: Python's sqlite3 does not open one before
        # CREATE/ALTER statements, so without it a failure halfway would leave
        # a half-changed database still marked with the old format.
        db.execute("BEGIN IMMEDIATE")
        try:
            for version in range(found + 1, SCHEMA_VERSION + 1):
                MIGRATIONS[version](db)
                db.execute(f"PRAGMA user_version = {version}")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        return found


# ------------------------------------------------------------------ models

@dataclass(frozen=True)
class ProjectInfo:
    id: str
    title: str
    description: str
    research_area: str
    status: str
    created_at: str
    modified_at: str
    last_opened_at: str
    path: Path
    counts: dict = field(default_factory=dict)

    @property
    def archived(self) -> bool:
        return self.status == "archived"


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    name: str
    origin: str
    source_path: str | None
    stored_path: str | None
    sha256: str
    rows: int
    columns: int
    created_at: str
    modified_at: str
    parent_id: str | None = None
    survey_id: str | None = None
    source_sha256: str | None = None


@dataclass(frozen=True)
class SourceStatus:
    dataset_id: str
    state: str            # "unchanged" | "changed" | "missing" | "stored"
    detail: str = ""


@dataclass(frozen=True)
class RunRecord:
    id: str
    method: str
    section: str
    title: str
    dataset_id: str | None
    dataset_sha256: str
    roles: dict
    options: dict
    confirms: dict
    confirmations: tuple[str, ...]
    levels: dict
    report: str
    report_sha256: str
    summary: str
    interpretation: str
    warnings: tuple[str, ...]
    tables: tuple
    figure: str | None
    provenance: dict
    created_at: str
    note: str = ""
    descriptives: str = ""
    guide: str = ""
    task_id: str | None = None          # format 4: the research task it belongs to
    structured: dict | None = None      # format 4: result_store JSON of the engine result
    charts: dict | None = None          # format 5: chart_views.ChartState JSON


@dataclass(frozen=True)
class TaskRecord:
    """A research task (format 4): what the researcher chose, to run again."""

    id: str
    position: int
    title: str
    goal: str
    selection: dict
    method: str
    options: dict
    confirms: dict
    hypothesis_id: str | None
    state: dict
    created_at: str
    modified_at: str


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    stale: bool
    reasons: tuple[str, ...] = ()


# ------------------------------------------------------------------- store

def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":  # os.kill would terminate the process on Windows
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


PLAN_TEXT_FIELDS = ("objectives", "design", "population", "ethics", "preregistration")
HYPOTHESIS_FIELDS = ("text", "h0", "outcome", "predictors", "covariates", "method", "family",
                     "exclusions")
DIRECTIONS = ("two-sided", "greater", "less")
PRIORITIES = ("primary", "secondary", "exploratory")


def normalise_plan(plan: dict) -> dict:
    """A research plan as stored: known fields only, trimmed, validated."""
    if not isinstance(plan, dict):
        raise ProjectError("A research plan is a set of named fields.")
    clean = {name: str(plan.get(name) or "").strip()[:4000] for name in PLAN_TEXT_FIELDS}
    hypotheses = []
    for raw in plan.get("hypotheses") or []:
        if not isinstance(raw, dict):
            continue
        item = {name: str(raw.get(name) or "").strip()[:2000] for name in HYPOTHESIS_FIELDS}
        if not item["text"]:
            continue
        direction = raw.get("direction") or "two-sided"
        priority = raw.get("priority") or "primary"
        if direction not in DIRECTIONS:
            raise ProjectError(f"Unknown direction {direction!r}.")
        if priority not in PRIORITIES:
            raise ProjectError(f"Unknown priority {priority!r}.")
        try:
            alpha = float(raw.get("alpha", 0.05))
        except (TypeError, ValueError) as error:
            raise ProjectError("The significance level must be a number.") from error
        if not 0 < alpha <= 0.2:
            raise ProjectError("The significance level must be above 0 and at most 0.2.")
        hypothesis_id = str(raw.get("id") or "") or uuid.uuid4().hex[:12]
        if not re.fullmatch(r"[0-9a-f]{12}", hypothesis_id):
            raise ProjectError("Invalid hypothesis identifier.")
        hypotheses.append({**item, "id": hypothesis_id, "direction": direction,
                           "priority": priority, "alpha": alpha})
    if len(hypotheses) > 100:
        raise ProjectError("A plan holds at most 100 hypotheses.")
    clean["hypotheses"] = hypotheses
    return clean


class ProjectStore:
    """All projects of one user (one data root)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ listing
    def _folders(self) -> Iterable[Path]:
        for folder in sorted(self.root.iterdir()):
            if folder.is_dir() and not folder.name.startswith(".") and (folder / DB_NAME).is_file():
                yield folder

    def info(self, project_id: str) -> ProjectInfo:
        folder = self._folder(project_id)
        try:
            with closing(_connect(folder / DB_NAME, read_only=True)) as db:
                return _info(db, folder)
        except sqlite3.DatabaseError as error:
            raise ProjectFormatError(f"Project {project_id} cannot be read: {error}") from error

    def list(self, *, include_archived: bool = False, query: str = "") -> list[ProjectInfo]:
        found = []
        needle = query.strip().casefold()
        for folder in self._folders():
            try:
                info = self.info(folder.name)
            except ProjectError:
                continue
            if info.archived and not include_archived:
                continue
            if needle and needle not in " ".join(
                    (info.title, info.description, info.research_area)).casefold():
                continue
            found.append(info)
        return sorted(found, key=lambda i: i.last_opened_at, reverse=True)

    def _folder(self, project_id: str) -> Path:
        try:
            uuid.UUID(str(project_id))
        except ValueError as error:
            raise ProjectError(f"Not a project id: {project_id!r}") from error
        folder = self.root / str(project_id)
        if not (folder / DB_NAME).is_file():
            raise ProjectError(f"No project {project_id} in {self.root}")
        return folder

    # ----------------------------------------------------------- lifecycle
    def create(self, title: str, **fields: str) -> ProjectInfo:
        title = str(title).strip()
        if not title:
            raise ProjectError("A project needs a title.")
        unknown = set(fields) - set(PROJECT_FIELDS)
        if unknown:
            raise ProjectError(f"Unknown project fields: {sorted(unknown)}")
        project_id = str(uuid.uuid4())
        staging = self.root / f".new-{project_id}"
        staging.mkdir(parents=True)
        try:
            migrate(staging / DB_NAME, self.root / BACKUPS)
            stamp = now()
            with closing(_connect(staging / DB_NAME)) as db, db:
                db.execute(
                    "INSERT INTO project (id, title, description, research_area, population_notes,"
                    " language, design, created_at, modified_at, last_opened_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (project_id, title, fields.get("description", ""),
                     fields.get("research_area", ""), fields.get("population_notes", ""),
                     fields.get("language", "en") or "en", fields.get("design", ""),
                     stamp, stamp, stamp))
                _log(db, "created", {"title": title})
            os.replace(staging, self.root / project_id)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self.info(project_id)

    def open(self, project_id: str, *, read_only: bool = False) -> "Project":
        folder = self._folder(project_id)
        if read_only:
            return Project(self, folder, read_only=True)
        recovered = _acquire_lock(folder)
        try:
            migrate(folder / DB_NAME, self.root / BACKUPS)
        except BaseException:
            _release_lock(folder)
            raise
        project = Project(self, folder, read_only=False)
        with project._db() as db:
            db.execute("UPDATE project SET last_opened_at = ?", (now(),))
            if recovered:
                _log(db, "recovered", {"detail": recovered})
        project.recovered = recovered
        return project

    def duplicate(self, project_id: str, title: str | None = None) -> ProjectInfo:
        source = self._folder(project_id)
        new_id = str(uuid.uuid4())
        staging = self.root / f".new-{new_id}"
        try:
            _copy_project_folder(source, staging)
            with closing(_connect(staging / DB_NAME)) as db, db:
                old = db.execute("SELECT title FROM project").fetchone()["title"]
                stamp = now()
                db.execute("UPDATE project SET id = ?, title = ?, status = 'active', created_at = ?,"
                           " modified_at = ?, last_opened_at = ?",
                           (new_id, title or f"{old} (copy)", stamp, stamp, stamp))
                _log(db, "duplicated", {"from": project_id})
            os.replace(staging, self.root / new_id)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return self.info(new_id)

    def set_archived(self, project_id: str, archived: bool) -> ProjectInfo:
        folder = self._folder(project_id)
        _ensure_unlocked(folder)
        with closing(_connect(folder / DB_NAME)) as db, db:
            db.execute("UPDATE project SET status = ?, modified_at = ?",
                       ("archived" if archived else "active", now()))
            _log(db, "archived" if archived else "unarchived", {})
        return self.info(project_id)

    def delete(self, project_id: str) -> Path:
        """Move a project to the trash folder (it can be restored)."""
        folder = self._folder(project_id)
        _ensure_unlocked(folder)
        target = self.root / TRASH / f"{project_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(folder, target)
        return target

    def deleted(self) -> list[Path]:
        trash = self.root / TRASH
        return sorted(trash.iterdir()) if trash.is_dir() else []

    def restore_deleted(self, trashed: Path) -> ProjectInfo:
        trashed = Path(trashed)
        if trashed.parent != self.root / TRASH or not (trashed / DB_NAME).is_file():
            raise ProjectError("Not a deleted project of this store.")
        with closing(_connect(trashed / DB_NAME, read_only=True)) as db:
            project_id = db.execute("SELECT id FROM project").fetchone()["id"]
        if (self.root / project_id).exists():
            raise ProjectError("A project with this id already exists.")
        os.replace(trashed, self.root / project_id)
        return self.info(project_id)

    # ------------------------------------------------------------- backups
    def export_package(self, project_id: str, destination: Path, *,
                       survey_root: Path | None = None) -> Path:
        """Write a self-contained ``.sra`` backup (optionally with linked questionnaires)."""
        folder = self._folder(project_id)
        destination = Path(destination)
        if destination.suffix.lower() != ".sra":
            destination = destination.with_suffix(".sra")
        files: list[tuple[str, bytes]] = []
        with tempfile.TemporaryDirectory(prefix="sra-export-") as temp:
            snapshot = Path(temp) / DB_NAME
            with closing(_connect(folder / DB_NAME)) as db, closing(sqlite3.connect(snapshot)) as out:
                db.backup(out)
                info = _info(db, folder)
                surveys = [row["survey_id"] for row in db.execute("SELECT survey_id FROM questionnaires")]
            files.append((f"project/{DB_NAME}", snapshot.read_bytes()))
        for sub in ("datasets", "figures"):
            for path in sorted((folder / sub).glob("*")) if (folder / sub).is_dir() else []:
                if path.is_file():
                    files.append((f"project/{sub}/{path.name}", path.read_bytes()))
        included = []
        if survey_root is not None:
            for survey_id in surveys:
                survey_file = _survey_file(Path(survey_root), survey_id)
                if survey_file is None:
                    continue
                files.append((f"surveys/{survey_file.name}", _read_consistent(survey_file)))
                included.append(survey_id)
        manifest = {
            "format": PACKAGE_FORMAT, "format_version": PACKAGE_VERSION,
            "schema_version": SCHEMA_VERSION, "exported_at": now(),
            "project": {"id": info.id, "title": info.title},
            "questionnaires": included, "app": library_versions(),
            "files": [{"path": name, "size": len(data), "sha256": sha256_bytes(data)}
                      for name, data in files],
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
            for name, data in files:
                archive.writestr(name, data)
        _atomic_write(destination, buffer.getvalue())
        with closing(_connect(folder / DB_NAME)) as db, db:
            _log(db, "exported", {"file": destination.name, "questionnaires": included})
        return destination

    def import_package(self, source: Path, *, survey_root: Path | None = None) -> tuple[ProjectInfo, list[str]]:
        """Restore a ``.sra`` backup as a project; never overwrites anything."""
        warnings: list[str] = []
        entries = _read_package(Path(source))
        manifest = entries.pop("manifest.json")
        project_id = manifest["project"]["id"]
        new_id = project_id
        if (self.root / project_id).exists():
            new_id = str(uuid.uuid4())
            warnings.append("This project already exists; the backup was restored as a separate copy.")
        staging = self.root / f".new-{new_id}"
        staging.mkdir(parents=True)
        try:
            for name, data in entries.items():
                if name.startswith("project/"):
                    _atomic_write(staging / name.removeprefix("project/"), data)
            migrate(staging / DB_NAME, self.root / BACKUPS)
            with closing(_connect(staging / DB_NAME)) as db, db:
                if new_id != project_id:
                    title = db.execute("SELECT title FROM project").fetchone()["title"]
                    db.execute("UPDATE project SET id = ?, title = ?", (new_id, f"{title} (restored)"))
                db.execute("UPDATE project SET last_opened_at = ?", (now(),))
                _log(db, "restored", {"from": Path(source).name})
            os.replace(staging, self.root / new_id)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if survey_root is not None:
            warnings += _restore_surveys(entries, Path(survey_root), manifest.get("questionnaires", []))
        elif manifest.get("questionnaires"):
            warnings.append("Linked questionnaires in the backup were not restored.")
        return self.info(new_id), warnings


def _info(db: sqlite3.Connection, folder: Path) -> ProjectInfo:
    row = db.execute("SELECT * FROM project").fetchone()
    if row is None:
        raise ProjectFormatError(f"{folder} has no project record")
    counts = {
        "datasets": db.execute("SELECT COUNT(*) FROM datasets").fetchone()[0],
        "runs": db.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
        "questionnaires": db.execute("SELECT COUNT(*) FROM questionnaires").fetchone()[0],
        "questions": db.execute("SELECT COUNT(*) FROM research_questions").fetchone()[0],
    }
    return ProjectInfo(row["id"], row["title"], row["description"], row["research_area"],
                       row["status"], row["created_at"], row["modified_at"],
                       row["last_opened_at"], folder, counts)


def _log(db: sqlite3.Connection, kind: str, detail: dict) -> None:
    db.execute("INSERT INTO events (at, kind, detail) VALUES (?, ?, ?)",
               (now(), kind, json.dumps(detail, ensure_ascii=False, default=str)))


def _lock_owner(folder: Path) -> dict | None:
    try:
        return json.loads((folder / LOCK_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _lock_is_live(owner: dict | None) -> bool:
    return bool(owner) and owner.get("host") == socket.gethostname() and _pid_alive(int(owner.get("pid", 0)))


# Open projects of this process: folder -> number of open handles.
_OPEN: dict[Path, int] = {}


def _acquire_lock(folder: Path) -> str:
    """Take the project lock; returns a note when an abandoned lock was replaced."""
    key = folder.resolve()
    if _OPEN.get(key):
        _OPEN[key] += 1
        return ""
    lock = folder / LOCK_NAME
    owner = _lock_owner(folder)
    recovered = ""
    if lock.exists():
        if _lock_is_live(owner) and int(owner.get("pid", 0)) != os.getpid():
            raise ProjectLocked("This project is open in another window of the application.")
        recovered = (f"The project was not closed properly ({owner.get('since', 'earlier')})."
                     if owner else "The project was not closed properly.")
        lock.unlink(missing_ok=True)
    data = json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "since": now()})
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ProjectLocked("This project is open in another window of the application.") from error
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(data)
    _OPEN[key] = 1
    return recovered


def _release_lock(folder: Path) -> None:
    key = folder.resolve()
    count = _OPEN.get(key, 0) - 1
    if count > 0:
        _OPEN[key] = count
        return
    _OPEN.pop(key, None)
    owner = _lock_owner(folder)
    if owner and int(owner.get("pid", 0)) == os.getpid():
        (folder / LOCK_NAME).unlink(missing_ok=True)


def _ensure_unlocked(folder: Path) -> None:
    owner = _lock_owner(folder)
    if _OPEN.get(folder.resolve()) or ((folder / LOCK_NAME).exists() and _lock_is_live(owner)):
        raise ProjectLocked("Close the project before archiving, deleting or moving it.")


def _copy_project_folder(source: Path, target: Path) -> None:
    target.mkdir(parents=True)
    with closing(_connect(source / DB_NAME)) as db, closing(sqlite3.connect(target / DB_NAME)) as out:
        db.backup(out)
    for sub in ("datasets", "figures"):
        if (source / sub).is_dir():
            shutil.copytree(source / sub, target / sub)


def _read_consistent(path: Path) -> bytes:
    """Bytes of a file; SQLite databases are snapshotted through the backup API."""
    with open(path, "rb") as stream:
        header = stream.read(16)
    if header != b"SQLite format 3\x00":
        return path.read_bytes()
    with tempfile.TemporaryDirectory(prefix="sra-db-") as temp:
        copy = Path(temp) / "copy.sqlite3"
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db, \
                closing(sqlite3.connect(copy)) as out:
            db.backup(out)
        return copy.read_bytes()


def _survey_file(root: Path, survey_id: str) -> Path | None:
    """The questionnaire storage keeps one SQLite file per questionnaire."""
    if not re.fullmatch(r"[0-9a-f]{32}", str(survey_id)):
        return None
    candidate = root / f"survey_{survey_id}.sqlite3"
    return candidate if candidate.is_file() else None


def _logical_digest(data: bytes) -> str:
    """SHA-256 of a file's meaning: an SQLite database by its SQL dump (two
    snapshots of the same database differ in header counters), others by bytes."""
    if not data.startswith(b"SQLite format 3\x00"):
        return sha256_bytes(data)
    with tempfile.TemporaryDirectory(prefix="sra-cmp-") as temp:
        path = Path(temp) / "db.sqlite3"
        path.write_bytes(data)
        with closing(sqlite3.connect(path)) as db:
            return sha256_bytes("\n".join(db.iterdump()).encode("utf-8"))


def _safe_member(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name:
        return False
    parts = PurePosixPath(name).parts
    return ".." not in parts and "." not in parts and all(parts)


def _read_package(source: Path) -> dict[str, Any]:
    """Validated contents of a ``.sra`` package: {name: bytes, 'manifest.json': dict}."""
    try:
        archive = zipfile.ZipFile(source)
    except (OSError, zipfile.BadZipFile) as error:
        raise ProjectFormatError(f"{source.name} is not a project backup: {error}") from error
    with archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        if len(infos) > MAX_PACKAGE_FILES:
            raise ProjectFormatError("The backup contains too many files.")
        if sum(i.file_size for i in infos) > MAX_PACKAGE_BYTES:
            raise ProjectFormatError("The backup is larger than this version accepts.")
        names = [i.filename for i in infos]
        if len(set(names)) != len(names):
            raise ProjectFormatError("The backup lists a file twice.")
        for info in infos:
            mode = info.external_attr >> 16
            if not _safe_member(info.filename) or stat.S_ISLNK(mode):
                raise ProjectFormatError(f"Unsafe path in backup: {info.filename!r}")
            if info.file_size > 10 * 1024 ** 2 and info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1):
                raise ProjectFormatError(f"Suspicious compression ratio: {info.filename!r}")
        if "manifest.json" not in names:
            raise ProjectFormatError("The backup has no manifest.")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except ValueError as error:
            raise ProjectFormatError("The backup manifest is unreadable.") from error
        if manifest.get("format") != PACKAGE_FORMAT:
            raise ProjectFormatError("This file is not a Statistical Research Assistant project backup.")
        if int(manifest.get("format_version", 0)) > PACKAGE_VERSION:
            raise ProjectFormatError("The backup was made by a newer version of the application.")
        try:
            uuid.UUID(str(manifest["project"]["id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectFormatError("The backup manifest has no valid project id.") from error
        listed = {f["path"]: f for f in manifest.get("files", [])}
        if set(listed) != set(names) - {"manifest.json"}:
            raise ProjectFormatError("The backup contents do not match its manifest.")
        entries: dict[str, Any] = {"manifest.json": manifest}
        for name, expected in listed.items():
            if not name.startswith(("project/", "surveys/")):
                raise ProjectFormatError(f"Unexpected file in backup: {name!r}")
            data = archive.read(name)
            if len(data) != expected["size"] or sha256_bytes(data) != expected["sha256"]:
                raise ProjectFormatError(f"Checksum mismatch for {name!r}; the backup is damaged.")
            entries[name] = data
        if f"project/{DB_NAME}" not in entries:
            raise ProjectFormatError("The backup has no project database.")
        return entries


def _restore_surveys(entries: dict, root: Path, surveys: list[str]) -> list[str]:
    """Put questionnaires from a backup into the survey storage, never over one."""
    warnings = []
    root.mkdir(parents=True, exist_ok=True)
    for survey_id in surveys:
        if not re.fullmatch(r"[0-9a-f]{32}", str(survey_id)):
            continue
        name = f"survey_{survey_id}.sqlite3"
        data = entries.get(f"surveys/{name}")
        if data is None:
            continue
        target = root / name
        if target.exists():
            if _logical_digest(_read_consistent(target)) != _logical_digest(data):
                warnings.append(f"Questionnaire {survey_id} already exists here with other "
                                "content (for example newer responses); your existing version was kept.")
            continue
        _atomic_write(target, data)
    return warnings


# ----------------------------------------------------------------- project

class Project:
    """An open project. Every change is saved immediately (SQLite transactions)."""

    def __init__(self, store: ProjectStore, folder: Path, *, read_only: bool):
        self.store = store
        self.path = folder
        self.read_only = read_only
        self.recovered = ""
        self._closed = False

    @property
    def id(self) -> str:
        return self.path.name

    def __enter__(self) -> "Project":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self.read_only:
            _release_lock(self.path)

    def _db(self) -> sqlite3.Connection:
        if self._closed:
            raise ProjectError("The project is closed.")
        db = _connect(self.path / DB_NAME, read_only=self.read_only)
        return _ClosingConnection(db)

    def _write(self):
        if self.read_only:
            raise ProjectError("This project is open read-only.")
        return self._db()

    # ------------------------------------------------------------ metadata
    def info(self) -> ProjectInfo:
        with self._db() as db:
            return _info(db, self.path)

    def update(self, **fields: str) -> ProjectInfo:
        unknown = set(fields) - set(PROJECT_FIELDS)
        if unknown:
            raise ProjectError(f"Unknown project fields: {sorted(unknown)}")
        if "title" in fields and not str(fields["title"]).strip():
            raise ProjectError("A project needs a title.")
        with self._write() as db:
            for name, value in fields.items():
                db.execute(f"UPDATE project SET {name} = ?", (str(value).strip(),))
            db.execute("UPDATE project SET modified_at = ?", (now(),))
            _log(db, "updated", {"fields": sorted(fields)})
        return self.info()

    def _touch(self, db) -> None:
        db.execute("UPDATE project SET modified_at = ?", (now(),))

    # -------------------------------------------------- research questions
    def add_question(self, text: str, kind: str = "question") -> str:
        text = str(text).strip()
        if not text:
            raise ProjectError("Write the research question first.")
        question_id = str(uuid.uuid4())
        with self._write() as db:
            position = db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM research_questions").fetchone()[0]
            stamp = now()
            db.execute("INSERT INTO research_questions VALUES (?, ?, ?, ?, ?, ?)",
                       (question_id, position, kind, text, stamp, stamp))
            self._touch(db)
        return question_id

    def update_question(self, question_id: str, text: str) -> None:
        with self._write() as db:
            db.execute("UPDATE research_questions SET text = ?, modified_at = ? WHERE id = ?",
                       (str(text).strip(), now(), question_id))
            self._touch(db)

    def remove_question(self, question_id: str) -> None:
        with self._write() as db:
            db.execute("DELETE FROM research_questions WHERE id = ?", (question_id,))
            self._touch(db)

    def questions(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM research_questions ORDER BY position")]

    def log_ai_request(self, provider: str, model: str, sources, tokens: int, *,
                       task: str = "", outcome: str = "ok") -> None:
        """Audit an AI request: provider, exact model, approved source types and
        token count, and (Stage 36) the assistant task and how the request
        ended ("ok", or why it failed). Neither the prompt nor the reply is
        stored (#43)."""
        detail = {"provider": str(provider)[:40], "model": str(model)[:200],
                  "sources": sorted(map(str, sources)), "tokens": int(tokens),
                  "outcome": str(outcome)[:40]}
        if task:
            detail["task"] = str(task)[:40]
        with self._write() as db:
            _log(db, "ai_request", detail)

    # -------------------------------------------------------- research plan
    def save_plan(self, plan: dict, note: str = "") -> int:
        """Save the research plan as a new version and return its number.

        Nothing is overwritten: the history keeps every version. Saving the
        same plan again adds no version. Hypotheses keep their identity
        across versions (ids are given on first save)."""
        with self._write() as db:
            latest = db.execute("SELECT id, plan FROM plan_versions ORDER BY id DESC LIMIT 1").fetchone()
            previous = json.loads(latest["plan"]) if latest is not None else {"hypotheses": []}
            # A hypothesis without an id is the one of the same wording, if any.
            known = {h["text"]: h["id"] for h in previous.get("hypotheses", [])}
            if isinstance(plan, dict):
                plan = {**plan, "hypotheses": [
                    {**h, "id": h.get("id") or known.get(str(h.get("text") or "").strip(), "")}
                    if isinstance(h, dict) else h for h in plan.get("hypotheses") or []]}
            clean = normalise_plan(plan)
            if latest is not None and previous == clean:
                return int(latest["id"])
            runs = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            cursor = db.execute(
                "INSERT INTO plan_versions (saved_at, plan, runs_before, note) VALUES (?, ?, ?, ?)",
                (now(), json.dumps(clean, ensure_ascii=False, sort_keys=True), runs,
                 str(note).strip()[:500]))
            _log(db, "plan_saved", {"version": cursor.lastrowid,
                                    "hypotheses": len(clean["hypotheses"]), "runs_before": runs})
            self._touch(db)
            return int(cursor.lastrowid)

    def plan(self) -> dict | None:
        history = self.plan_history(limit=1)
        return history[0] if history else None

    def plan_history(self, *, limit: int | None = None) -> list[dict]:
        """Plan versions, newest first: version, saved_at, plan, runs_before, note."""
        query = "SELECT * FROM plan_versions ORDER BY id DESC" + (f" LIMIT {int(limit)}" if limit else "")
        with self._db() as db:
            return [{"version": row["id"], "saved_at": row["saved_at"], "plan": json.loads(row["plan"]),
                     "runs_before": row["runs_before"], "note": row["note"]}
                    for row in db.execute(query)]

    def hypothesis_status(self) -> dict[str, dict]:
        """For every hypothesis of the current plan: when it entered the plan
        and how many results existed then. One that entered after results were
        calculated is reported as such; it is exploratory unless the
        researcher justifies otherwise."""
        history = list(reversed(self.plan_history()))
        first: dict[str, dict] = {}
        for version in history:
            for hypothesis in version["plan"]["hypotheses"]:
                first.setdefault(hypothesis["id"], {"version": version["version"],
                                                    "saved_at": version["saved_at"],
                                                    "runs_before": version["runs_before"]})
        current = history[-1]["plan"]["hypotheses"] if history else []
        status = {}
        for hypothesis in current:
            entry = first[hypothesis["id"]]
            planned = entry["runs_before"] == 0
            status[hypothesis["id"]] = {
                **entry, "planned_before_results": planned,
                "standing": ("exploratory" if hypothesis["priority"] == "exploratory"
                             else "confirmatory" if planned else "added_after_results")}
        return status

    # ------------------------------------------------------------ datasets
    def import_dataset(self, path: Path, *, name: str | None = None, mode: str = "copy",
                       frame=None) -> DatasetRecord:
        """Add a data file: ``copy`` stores the file's bytes in the project,
        ``link`` only references the original (it is checked on every use)."""
        path = Path(path)
        if mode not in ("copy", "link"):
            raise ProjectError("mode must be 'copy' or 'link'")
        if path.suffix.lower() not in DATASET_SUFFIXES:
            raise ProjectError(f"Unsupported data file type: {path.suffix}")
        data = path.read_bytes()
        frame = frame if frame is not None else _load_frame(path)
        digest = sha256_bytes(data)
        stored = None
        if mode == "copy":
            stored = f"datasets/{digest}{path.suffix.lower()}"
            if not (self.path / stored).exists():
                _atomic_write(self.path / stored, data)
        return self._insert_dataset(name or path.stem, mode, str(path.resolve()), stored, digest, frame)

    def import_table(self, frame, name: str, *, source_path: str | Path | None = None) -> DatasetRecord:
        """Store the table exactly as it was loaded (import options applied) and
        remember which file it came from, with that file's SHA-256."""
        source = Path(source_path).resolve() if source_path else None
        source_hash = sha256_file(source) if source is not None and source.is_file() else None
        record = self.add_frame(frame, name, origin="copy")
        with self._write() as db:
            db.execute("UPDATE datasets SET source_path = ?, source_sha256 = ? WHERE id = ?",
                       (str(source) if source else None, source_hash, record.id))
        return self.dataset(record.id)

    def find_by_source(self, source_path: str | Path) -> DatasetRecord | None:
        """The dataset imported from this file earlier, if any."""
        wanted = str(Path(source_path).resolve())
        for record in self.datasets():
            if record.source_path == wanted:
                return record
        return None

    def add_frame(self, frame, name: str, *, origin: str = "derived", parent_id: str | None = None,
                  survey_id: str | None = None) -> DatasetRecord:
        """Store an in-memory table (prepared data, questionnaire responses) as CSV."""
        if origin not in ("copy", "derived", "survey"):
            raise ProjectError("origin must be 'copy', 'derived' or 'survey'")
        stored, digest = self._write_table(frame)
        return self._insert_dataset(name, origin, None, stored, digest, frame,
                                    parent_id=parent_id, survey_id=survey_id)

    def _write_table(self, frame) -> tuple[str, str]:
        """Store a table as CSV plus its column types; (stored path, SHA-256 of the CSV)."""
        data = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
        digest = sha256_bytes(data)
        stored = f"datasets/{digest}.csv"
        schema = self.path / "datasets" / f"{digest}{TABLE_SCHEMA_SUFFIX}"
        if not schema.exists():
            _atomic_write(schema, json.dumps(table_schema(frame), ensure_ascii=False).encode("utf-8"))
        if not (self.path / stored).exists():
            _atomic_write(self.path / stored, data)
        return stored, digest

    def _insert_dataset(self, name, origin, source, stored, digest, frame, *, parent_id=None,
                        survey_id=None) -> DatasetRecord:
        dataset_id = str(uuid.uuid4())
        rows, columns = int(frame.shape[0]), int(frame.shape[1])
        with self._write() as db:
            stamp = now()
            db.execute("INSERT INTO datasets (id, name, origin, source_path, stored_path, sha256,"
                       " rows, columns, created_at, modified_at, parent_id, survey_id)"
                       " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (dataset_id, str(name), origin, source, stored, digest, rows, columns,
                        stamp, stamp, parent_id, survey_id))
            db.execute("INSERT INTO dataset_versions (dataset_id, sha256, stored_path, rows, columns,"
                       " recorded_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (dataset_id, digest, stored, rows, columns, stamp, "added"))
            db.execute("UPDATE project SET active_dataset = ?", (dataset_id,))
            for column, dtype in frame.dtypes.astype(str).items():
                db.execute("INSERT INTO variables (dataset_id, name, storage) VALUES (?, ?, ?)",
                           (dataset_id, str(column), dtype))
            self._touch(db)
            _log(db, "dataset_added", {"name": str(name), "origin": origin, "sha256": digest})
        return self.dataset(dataset_id)

    def replace_dataset(self, dataset_id: str, path: Path | None = None, *, frame=None,
                        reason: str = "updated by the researcher") -> DatasetRecord:
        """A new version of the same dataset; results computed earlier become stale."""
        record = self.dataset(dataset_id)
        if path is not None:
            path = Path(path)
            data = path.read_bytes()
            frame = frame if frame is not None else _load_frame(path)
            suffix = path.suffix.lower()
        elif frame is not None:
            data = None
        else:
            raise ProjectError("Give the new file or table.")
        stored = record.stored_path
        if data is None:
            if record.origin == "link":
                raise ProjectError("A linked dataset changes with its file; relink it instead.")
            stored, digest = self._write_table(frame)
        else:
            digest = sha256_bytes(data)
            if record.origin != "link":
                stored = f"datasets/{digest}{suffix}"
                if not (self.path / stored).exists():
                    _atomic_write(self.path / stored, data)
        with self._write() as db:
            self._new_version(db, dataset_id, digest, stored, frame.shape, reason,
                              source=str(path.resolve()) if path is not None and record.origin == "link" else None)
        return self.dataset(dataset_id)

    def _new_version(self, db, dataset_id, digest, stored, shape, reason, source=None) -> None:
        stamp = now()
        db.execute("UPDATE datasets SET sha256 = ?, stored_path = ?, rows = ?, columns = ?,"
                   " modified_at = ? WHERE id = ?",
                   (digest, stored, int(shape[0]), int(shape[1]), stamp, dataset_id))
        if source:
            db.execute("UPDATE datasets SET source_path = ? WHERE id = ?", (source, dataset_id))
        db.execute("INSERT INTO dataset_versions (dataset_id, sha256, stored_path, rows, columns,"
                   " recorded_at, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (dataset_id, digest, stored, int(shape[0]), int(shape[1]), stamp, reason))
        self._touch(db)
        _log(db, "dataset_version", {"dataset": dataset_id, "sha256": digest, "reason": reason})

    def datasets(self) -> list[DatasetRecord]:
        with self._db() as db:
            return [_dataset(r) for r in db.execute("SELECT * FROM datasets ORDER BY created_at")]

    def dataset(self, dataset_id: str) -> DatasetRecord:
        with self._db() as db:
            row = db.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise ProjectError(f"No dataset {dataset_id} in this project.")
        return _dataset(row)

    def dataset_versions(self, dataset_id: str) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM dataset_versions WHERE dataset_id = ? ORDER BY id", (dataset_id,))]

    def active_dataset(self) -> DatasetRecord | None:
        with self._db() as db:
            row = db.execute("SELECT active_dataset FROM project").fetchone()
        return self.dataset(row["active_dataset"]) if row and row["active_dataset"] else None

    def set_active_dataset(self, dataset_id: str) -> None:
        self.dataset(dataset_id)
        with self._write() as db:
            db.execute("UPDATE project SET active_dataset = ?", (dataset_id,))

    def load_frame(self, dataset_id: str):
        """The dataset's current table; a linked file is re-checked first."""
        record = self.dataset(dataset_id)
        if record.origin == "link":
            status = self.check_source(dataset_id)
            if status.state == "missing":
                raise ProjectError(f"The linked file is missing: {record.source_path}")
            return _load_frame(Path(record.source_path))
        return _load_frame(self.path / record.stored_path)

    def version_files(self, dataset_id: str, sha256: str) -> tuple[Path, ...]:
        """Files that may hold one version of a dataset, newest first (no reading)."""
        record = self.dataset(dataset_id)
        paths = [self.path / version["stored_path"]
                 for version in reversed(self.dataset_versions(dataset_id))
                 if version["sha256"] == sha256 and version["stored_path"]]
        if record.origin == "link" and record.sha256 == sha256 and record.source_path:
            paths.append(Path(record.source_path))
        return tuple(paths)

    def load_version(self, dataset_id: str, sha256: str):
        """The table exactly as it was at one version, or None when the project
        kept no copy of that version (a linked file that has changed since)."""
        return load_verified(self.version_files(dataset_id, sha256), sha256)

    def check_source(self, dataset_id: str) -> SourceStatus:
        """For linked files: has the original been moved or changed?"""
        record = self.dataset(dataset_id)
        if record.origin != "link":
            stored = self.path / (record.stored_path or "")
            if not stored.is_file() or sha256_file(stored) != record.sha256:
                return SourceStatus(dataset_id, "missing", "The project's copy is damaged or missing.")
            return SourceStatus(dataset_id, "stored")
        source = Path(record.source_path or "")
        if not source.is_file():
            return SourceStatus(dataset_id, "missing", str(source))
        digest = sha256_file(source)
        if digest == record.sha256:
            return SourceStatus(dataset_id, "unchanged")
        frame = _load_frame(source)
        with self._write() as db:
            self._new_version(db, dataset_id, digest, None, frame.shape, "the linked file changed")
        return SourceStatus(dataset_id, "changed", "Results computed before the change are stale.")

    def relink(self, dataset_id: str, new_path: Path) -> SourceStatus:
        """Point a linked dataset at its moved file (content is compared)."""
        record = self.dataset(dataset_id)
        if record.origin != "link":
            raise ProjectError("Only linked files can be relinked.")
        new_path = Path(new_path)
        digest = sha256_file(new_path)
        with self._write() as db:
            db.execute("UPDATE datasets SET source_path = ? WHERE id = ?",
                       (str(new_path.resolve()), dataset_id))
            _log(db, "relinked", {"dataset": dataset_id, "path": str(new_path)})
            if digest == record.sha256:
                return SourceStatus(dataset_id, "unchanged")
            frame = _load_frame(new_path)
            self._new_version(db, dataset_id, digest, None, frame.shape,
                              "relinked to a file with other content")
        return SourceStatus(dataset_id, "changed", "Results computed before the change are stale.")

    # ------------------------------------------------------------ variables
    def save_levels(self, dataset_id: str, levels: dict[str, tuple[str | None, str]]) -> None:
        """{variable: (confirmed level or None, where it was confirmed)}."""
        with self._write() as db:
            stamp = now()
            for name, (level, where) in levels.items():
                db.execute(
                    "INSERT INTO variables (dataset_id, name, level, confirmed_in, confirmed_at)"
                    " VALUES (?, ?, ?, ?, ?) ON CONFLICT(dataset_id, name) DO UPDATE SET"
                    " level = excluded.level, confirmed_in = excluded.confirmed_in,"
                    " confirmed_at = excluded.confirmed_at",
                    (dataset_id, name, level, where or "", stamp if level else None))
            self._touch(db)

    def levels(self, dataset_id: str) -> dict[str, dict]:
        with self._db() as db:
            return {r["name"]: dict(r) for r in db.execute(
                "SELECT * FROM variables WHERE dataset_id = ? ORDER BY rowid", (dataset_id,))}

    def add_transformation(self, dataset_id: str, kind: str, params: dict,
                           output_columns: list[str]) -> str:
        step_id = str(uuid.uuid4())
        with self._write() as db:
            position = db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM transformations"
                                  " WHERE dataset_id = ?", (dataset_id,)).fetchone()[0]
            db.execute("INSERT INTO transformations VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (step_id, dataset_id, position, kind, json.dumps(params, default=str),
                        json.dumps(list(output_columns)), now()))
            self._touch(db)
        return step_id

    def transformations(self, dataset_id: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM transformations WHERE dataset_id = ? ORDER BY position",
                              (dataset_id,))
            return [dict(r) | {"params": json.loads(r["params"]),
                               "output_columns": json.loads(r["output_columns"])} for r in rows]

    # ------------------------------------------------------- questionnaires
    def link_questionnaire(self, survey_id: str, title: str, role: str = "linked") -> None:
        with self._write() as db:
            db.execute("INSERT INTO questionnaires VALUES (?, ?, ?, ?) ON CONFLICT(survey_id)"
                       " DO UPDATE SET title = excluded.title, role = excluded.role",
                       (survey_id, title, role, now()))
            self._touch(db)
            _log(db, "questionnaire_linked", {"survey": survey_id})

    def unlink_questionnaire(self, survey_id: str) -> None:
        with self._write() as db:
            db.execute("DELETE FROM questionnaires WHERE survey_id = ?", (survey_id,))
            self._touch(db)
            _log(db, "questionnaire_unlinked", {"survey": survey_id})

    def questionnaires(self) -> list[dict]:
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM questionnaires ORDER BY linked_at")]

    # ---------------------------------------------------------------- runs
    def record_run(self, run, *, method: str, dataset_id: str | None, roles: dict,
                   options: dict, confirms: dict, confirmations: Iterable[str] = (),
                   levels: dict | None = None, dataset_sha256: str | None = None,
                   task_id: str | None = None) -> RunRecord:
        """Save one completed analysis (an ``analysis_runs.AnalysisRun``).

        ``dataset_sha256`` names the dataset version the run was calculated on
        when that is not the current one (a follow-up of an earlier result)."""
        if dataset_sha256 and dataset_id:
            known = {v["sha256"] for v in self.dataset_versions(dataset_id)}
            if dataset_sha256 not in known:
                raise ProjectError("That dataset version is not part of this project.")
        dataset_sha = dataset_sha256 or (self.dataset(dataset_id).sha256 if dataset_id else "")
        run_id = str(uuid.uuid4())
        figure = None
        if run.png:
            figure = f"figures/{run_id}.png"
            _atomic_write(self.path / figure, run.png)
        tables = [{"title": t.title, "columns": list(t.columns), "rows": [list(r) for r in t.rows]}
                  for t in run.tables]
        from result_store import to_json

        structured = to_json(getattr(run, "result", None))
        provenance = {"libraries": library_versions(), "seed": options.get("seed"),
                      "rows": self.dataset(dataset_id).rows if dataset_id else None,
                      "inputs": run.inputs}
        with self._write() as db:
            db.execute(
                "INSERT INTO runs (id, method, section, title, dataset_id, dataset_sha256, roles,"
                " options, confirms, confirmations, levels, report, report_sha256, summary,"
                " interpretation, warnings, tables, figure, provenance, created_at, descriptives,"
                " guide, task_id, structured)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, method, run.section, run.title, dataset_id, dataset_sha,
                 json.dumps(roles, default=str), json.dumps(options, default=str),
                 json.dumps(confirms, default=str), json.dumps(list(confirmations)),
                 json.dumps(levels or {}), run.report, sha256_bytes(run.report.encode("utf-8")),
                 run.summary, run.interpretation, json.dumps(list(run.warnings)),
                 json.dumps(tables), figure, json.dumps(provenance, default=str), now(),
                 run.descriptives or "", run.guide or "", task_id,
                 json.dumps(structured, default=str) if structured else None))
            self._touch(db)
            _log(db, "run", {"run": run_id, "method": method, "dataset": dataset_id})
        return self.run(run_id)

    def runs(self) -> list[RunRecord]:
        with self._db() as db:
            return [_run(r) for r in db.execute("SELECT * FROM runs ORDER BY created_at, rowid")]

    def run(self, run_id: str) -> RunRecord:
        with self._db() as db:
            row = db.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise ProjectError(f"No analysis run {run_id} in this project.")
        return _run(row)

    def figure(self, run: RunRecord) -> bytes | None:
        return (self.path / run.figure).read_bytes() if run.figure else None

    def set_run_charts(self, run_id: str, charts: dict | None) -> None:
        """Store the Chart Studio state of a run (format 5); ``None`` removes it.

        Only the way the result is drawn is stored; the run's numbers,
        report and figure are not touched."""
        payload = None if charts is None else json.dumps(charts, default=str,
                                                         separators=(",", ":"))
        with self._write() as db:
            changed = db.execute("UPDATE runs SET charts = ? WHERE id = ?",
                                 (payload, run_id)).rowcount
            if not changed:
                raise ProjectError(f"No analysis run {run_id} in this project.")
            self._touch(db)
            _log(db, "charts", {"run": run_id, "views": len((charts or {}).get("views") or ())})

    def run_status(self, run: RunRecord) -> RunStatus:
        reasons = []
        if run.dataset_id:
            try:
                record = self.dataset(run.dataset_id)
            except ProjectError:
                reasons.append("dataset removed")
            else:
                if record.sha256 != run.dataset_sha256:
                    reasons.append("data changed after this result")
                current = self.levels(run.dataset_id)
                for name, level in run.levels.items():
                    now_level = current.get(name, {}).get("level")
                    if now_level != level:
                        reasons.append(f"measurement level of {name} changed ({level} → {now_level})")
        elif run.dataset_sha256:
            reasons.append("dataset removed")
        return RunStatus(run.id, bool(reasons), tuple(reasons))

    def set_note(self, run_id: str, note: str) -> None:
        with self._write() as db:
            db.execute("UPDATE runs SET note = ? WHERE id = ?", (str(note), run_id))

    def delete_run(self, run_id: str) -> None:
        run = self.run(run_id)
        with self._write() as db:
            db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            _log(db, "run_deleted", {"run": run_id, "title": run.title})
        if run.figure:
            (self.path / run.figure).unlink(missing_ok=True)

    # ------------------------------------------------------- research tasks
    def save_task(self, *, task_id: str | None, title: str, goal: str, selection: dict,
                  method: str = "", options: dict | None = None, confirms: dict | None = None,
                  hypothesis_id: str | None = None, state: dict | None = None) -> TaskRecord:
        """Create a research task, or update it in place (same id)."""
        if not str(title).strip():
            raise ProjectError("A research task needs a title.")
        stamp = now()
        task_id = task_id or str(uuid.uuid4())
        values = (str(title).strip()[:200], goal, json.dumps(selection, default=str), method,
                  json.dumps(options or {}, default=str), json.dumps(confirms or {}, default=str),
                  hypothesis_id, json.dumps(state or {}, default=str))
        with self._write() as db:
            existing = db.execute("SELECT id FROM research_tasks WHERE id = ?",
                                  (task_id,)).fetchone()
            if existing:
                db.execute("UPDATE research_tasks SET title = ?, goal = ?, selection = ?,"
                           " method = ?, options = ?, confirms = ?, hypothesis_id = ?, state = ?,"
                           " modified_at = ? WHERE id = ?", (*values, stamp, task_id))
            else:
                position = db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM research_tasks"
                                      ).fetchone()[0]
                db.execute("INSERT INTO research_tasks (id, position, title, goal, selection,"
                           " method, options, confirms, hypothesis_id, state, created_at,"
                           " modified_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (task_id, position, *values, stamp, stamp))
                _log(db, "task", {"task": task_id, "title": values[0]})
            self._touch(db)
        return self.task(task_id)

    def tasks(self) -> list[TaskRecord]:
        with self._db() as db:
            return [_task(r) for r in db.execute(
                "SELECT * FROM research_tasks ORDER BY position, created_at")]

    def task(self, task_id: str) -> TaskRecord:
        with self._db() as db:
            row = db.execute("SELECT * FROM research_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ProjectError(f"No research task {task_id} in this project.")
        return _task(row)

    def delete_task(self, task_id: str) -> None:
        """Remove the task; its results stay (no longer linked to a task)."""
        task = self.task(task_id)
        with self._write() as db:
            db.execute("UPDATE runs SET task_id = NULL WHERE task_id = ?", (task_id,))
            db.execute("DELETE FROM research_tasks WHERE id = ?", (task_id,))
            _log(db, "task_deleted", {"task": task_id, "title": task.title})

    # -------------------------------------------------------------- report
    def set_report(self, run_ids: list[str]) -> None:
        with self._write() as db:
            db.execute("DELETE FROM report_items")
            for position, run_id in enumerate(dict.fromkeys(run_ids)):
                db.execute("INSERT INTO report_items VALUES (?, ?)", (position, run_id))
            self._touch(db)

    def report_runs(self) -> list[RunRecord]:
        with self._db() as db:
            ids = [r["run_id"] for r in db.execute("SELECT run_id FROM report_items ORDER BY position")]
        return [self.run(i) for i in ids]

    def report_text(self, *, allow_stale: bool = False) -> str:
        """The combined report; refuses stale results unless explicitly allowed."""
        parts = []
        for run in self.report_runs():
            status = self.run_status(run)
            if status.stale and not allow_stale:
                raise ProjectError(f"“{run.title}” is stale ({'; '.join(status.reasons)}). "
                                   "Recalculate it or remove it from the report.")
            heading = run.title + (" — STALE: " + "; ".join(status.reasons) if status.stale else "")
            parts.append(f"{heading}\n{'=' * len(heading)}\n{run.report.strip()}")
        return "\n\n".join(parts) + ("\n" if parts else "")

    def reproducibility_appendix(self, run_ids: Iterable[str] | None = None) -> str:
        """Plain-text provenance of selected runs (for a supervisor or an appendix)."""
        runs = [self.run(i) for i in run_ids] if run_ids is not None else self.runs()
        info = self.info()
        lines = [f"Reproducibility appendix — {info.title}", f"Project id: {info.id}", ""]
        for run in runs:
            status = self.run_status(run)
            lines += [
                f"{run.title} ({run.method})",
                f"  Calculated: {run.created_at}",
                f"  Dataset: {self._dataset_name(run.dataset_id)} (SHA-256 {run.dataset_sha256})",
                f"  Variables: {json.dumps(run.roles, ensure_ascii=False)}",
                f"  Options: {json.dumps(run.options, ensure_ascii=False)}",
                f"  Measurement levels: {json.dumps(run.levels, ensure_ascii=False)}",
                f"  Confirmed by the researcher: {'; '.join(run.confirmations) or '—'}",
                f"  Report SHA-256: {run.report_sha256}",
                f"  Software: {json.dumps(run.provenance.get('libraries', {}), ensure_ascii=False)}",
                f"  Status: {'STALE — ' + '; '.join(status.reasons) if status.stale else 'current'}",
                "",
            ]
        return "\n".join(lines)

    def _dataset_name(self, dataset_id: str | None) -> str:
        if not dataset_id:
            return "—"
        try:
            return self.dataset(dataset_id).name
        except ProjectError:
            return "removed dataset"

    # ---------------------------------------------------------------- log
    # ----------------------------------------------- AI permissions (format 2)
    def ai_permissions(self) -> dict[str, bool]:
        """Stored decisions per context source; a missing source is off."""
        with self._db() as db:
            return {r["source"]: bool(r["allowed"])
                    for r in db.execute("SELECT source, allowed FROM ai_permissions")}

    def set_ai_permission(self, source: str, allowed: bool) -> None:
        """Record the researcher's decision for one source (``ai_context`` checks it)."""
        if not re.fullmatch(r"[a-z_]{1,40}", str(source)):
            raise ProjectError(f"Unknown context source: {source!r}")
        with self._write() as db:
            db.execute("INSERT INTO ai_permissions VALUES (?, ?, ?) ON CONFLICT(source)"
                       " DO UPDATE SET allowed = excluded.allowed, changed_at = excluded.changed_at",
                       (source, int(bool(allowed)), now()))
            self._touch(db)
            _log(db, "ai_permission", {"source": source, "allowed": bool(allowed)})

    @property
    def data_anonymous(self) -> bool:
        with self._db() as db:
            return bool(db.execute("SELECT data_anonymous FROM project").fetchone()[0])

    def set_data_anonymous(self, anonymous: bool) -> None:
        with self._write() as db:
            db.execute("UPDATE project SET data_anonymous = ?", (int(bool(anonymous)),))
            self._touch(db)
            _log(db, "data_anonymous", {"anonymous": bool(anonymous)})

    def events(self, limit: int = 200) -> list[dict]:
        with self._db() as db:
            return [dict(r) | {"detail": json.loads(r["detail"])} for r in db.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (int(limit),))]


class _ClosingConnection:
    """``with project._db() as db`` commits on success and always closes."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def __enter__(self) -> sqlite3.Connection:
        return self.db

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.db.commit()
            else:
                self.db.rollback()
        finally:
            self.db.close()


def load_verified(paths: Iterable[Path], sha256: str):
    """The first file whose content still has this SHA-256, loaded; else None.

    Touches no project database, so a worker thread may call it."""
    for path in paths:
        path = Path(path)
        if path.is_file() and sha256_file(path) == sha256:
            return _load_frame(path)
    return None


def table_schema(frame) -> dict:
    """What CSV text cannot carry about a table: each column's type, the
    categories of categorical columns, and which text cells were missing
    rather than empty. Stored next to every CSV copy the project writes."""
    import numpy as np
    import pandas as pd

    columns = []
    for position, (name, dtype) in enumerate(frame.dtypes.items()):
        entry: dict[str, Any] = {"name": str(name), "dtype": str(dtype)}
        if isinstance(dtype, pd.CategoricalDtype):
            entry["categories"] = [str(c) for c in dtype.categories]
            entry["ordered"] = bool(dtype.ordered)
        elif _is_text_type(entry["dtype"]):
            values = frame.iloc[:, position]
            missing = values.isna().to_numpy()
            empty = values.map(lambda v: isinstance(v, str) and v == "").to_numpy(dtype=bool)
            if empty.any():
                entry["empty_text"] = True
                if missing.any():
                    entry["missing_rows"] = [int(i) for i in np.flatnonzero(missing)]
        columns.append(entry)
    return {"format": 1, "columns": columns}


def _is_text_type(kind: str) -> bool:
    # "object" (pandas 2), "str" (pandas 3 default) and the explicit "string" types
    return kind in ("object", "str") or kind.startswith("string")


def _read_typed_table(path: Path):
    """A CSV copy written by this module, read back with its stored column
    types; None when the file has no schema (an original file)."""
    import pandas as pd

    schema_file = path.with_name(path.stem + TABLE_SCHEMA_SUFFIX)
    if path.suffix.lower() != ".csv" or not schema_file.is_file():
        return None
    try:
        columns = json.loads(schema_file.read_text(encoding="utf-8"))["columns"]
        names = [str(c["name"]) for c in columns]
        kinds = [str(c["dtype"]) for c in columns]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    read_as: dict[int, Any] = {}
    missing: dict[int, list[str]] = {}
    for index, (column, kind) in enumerate(zip(columns, kinds)):
        textual = _is_text_type(kind) or kind == "category" or kind.startswith(("datetime", "timedelta"))
        if textual:
            read_as[index] = str
            missing[index] = [] if column.get("empty_text") else [""]
        elif kind == "bool" or kind.startswith(("int", "uint")):
            read_as[index] = kind      # cannot hold missing values
            missing[index] = []
        else:                          # float64, Int64, Float64, boolean ...
            read_as[index] = kind
            missing[index] = [""]
    frame = pd.read_csv(path, header=None, skiprows=1, dtype=read_as, keep_default_na=False,
                        na_values=missing, encoding="utf-8", float_precision="round_trip")
    if frame.shape[1] != len(names):
        raise ProjectFormatError(f"{path.name} does not match its column types.")
    frame.columns = names
    for index, (column, kind) in enumerate(zip(columns, kinds)):
        values = frame.iloc[:, index]
        if column.get("missing_rows"):
            values = values.copy()
            values.iloc[column["missing_rows"]] = None
        if kind == "category":
            values = values.astype(pd.CategoricalDtype(column.get("categories") or None,
                                                       ordered=bool(column.get("ordered"))))
        elif kind.startswith("datetime"):
            values = pd.to_datetime(values, format="ISO8601").astype(kind)
        elif kind.startswith("timedelta"):
            values = pd.to_timedelta(values).astype(kind)
        elif kind == "object":
            values = values.astype(object)
        elif kind == "str" or kind.startswith("string"):
            values = values.astype(kind)
        frame.isetitem(index, values)
    return frame


def _load_frame(path: Path):
    typed = _read_typed_table(Path(path))
    if typed is not None:
        return typed
    from data_loader import load_dataset

    return load_dataset(path)


def _dataset(row: sqlite3.Row) -> DatasetRecord:
    return DatasetRecord(row["id"], row["name"], row["origin"], row["source_path"],
                         row["stored_path"], row["sha256"], row["rows"], row["columns"],
                         row["created_at"], row["modified_at"], row["parent_id"], row["survey_id"],
                         row["source_sha256"])


def _run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        row["id"], row["method"], row["section"], row["title"], row["dataset_id"],
        row["dataset_sha256"], json.loads(row["roles"]), json.loads(row["options"]),
        json.loads(row["confirms"]), tuple(json.loads(row["confirmations"])),
        json.loads(row["levels"]), row["report"], row["report_sha256"], row["summary"],
        row["interpretation"], tuple(json.loads(row["warnings"])),
        tuple(json.loads(row["tables"])), row["figure"], json.loads(row["provenance"]),
        row["created_at"], row["note"], row["descriptives"], row["guide"],
        row["task_id"] if "task_id" in row.keys() else None,
        json.loads(row["structured"]) if "structured" in row.keys() and row["structured"]
        else None,
        json.loads(row["charts"]) if "charts" in row.keys() and row["charts"] else None)


def _task(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(row["id"], row["position"], row["title"], row["goal"],
                      json.loads(row["selection"]), row["method"], json.loads(row["options"]),
                      json.loads(row["confirms"]), row["hypothesis_id"], json.loads(row["state"]),
                      row["created_at"], row["modified_at"])
