"""Keep the workspace session in a research project (Stage 34, issue #24).

``ProjectBinding`` listens to the ``ResearchSession`` events the workspace
already sends (``dataset``, ``dictionary``, ``results``, ``report``) and saves
each change into the open project at once, so there is no "Save" step and
nothing to lose on a crash. Opening a project puts its active dataset,
confirmed measurement levels, saved results and report selection back into
the session.

Saved results are shown immediately from their stored report, tables and
chart. ``verify_restored()`` then recalculates each one on the exact dataset
version it was calculated on, through the same ``run_method`` the interface
uses; a matching report SHA-256 restores the full result object (needed for
Word export and post-hoc tests), a mismatch is reported on the result instead
of replacing it. Nothing here changes how any statistic is computed.

Threads: the project database belongs to the thread that opened it (the UI
event loop). Recalculation therefore reads everything it needs from the
database first (:meth:`ProjectBinding.recalculation`) and hands a plain
:class:`Recalculation` to a worker thread, which only reads files.
"""

from __future__ import annotations

import asyncio
import atexit
import json
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
import weakref

from project_store import (
    DB_NAME, Project, ProjectError, ProjectInfo, ProjectStore, RunRecord, load_verified,
    sha256_bytes,
)
from workspace_state import LEVELS, ReportSettings, ResearchSession

# Dataset origins in the session (see ResearchSession.dataset_origin) that
# came from a file the researcher chose and can load again.
FILE_ORIGINS = ("file",)


def _local_time(stamp: str) -> datetime:
    try:
        return datetime.fromisoformat(stamp).astimezone().replace(tzinfo=None)
    except ValueError:
        return datetime.now()


def run_from_record(record: RunRecord, figure: bytes | None):
    """An ``AnalysisRun`` rebuilt from what the project stored (no engine object)."""
    from analysis_runs import AnalysisRun, ResultTable

    tables = tuple(ResultTable(t["title"], tuple(t["columns"]), tuple(tuple(r) for r in t["rows"]))
                   for t in record.tables)
    from result_store import from_json

    return AnalysisRun(
        record.section, record.title, record.report, figure, from_json(record.structured),
        summary=record.summary, interpretation=record.interpretation,
        descriptives=record.descriptives, guide=record.guide,
        warnings=tuple(record.warnings), tables=tables,
        inputs=record.provenance.get("inputs", {}),
    )


def same_report(first, second) -> bool:
    return (sha256_bytes(first.report.encode("utf-8"))
            == sha256_bytes(second.report.encode("utf-8")))


@dataclass(frozen=True)
class Recalculation:
    """Everything needed to calculate one saved result again; no database handle."""

    method: str
    roles: dict
    options: dict
    confirms: dict
    levels: dict
    dataset_name: str
    dataset_sha256: str
    files: tuple[Path, ...]


def recalculate(plan: Recalculation):
    """The run again on the exact stored table, or None when that version is
    gone or the calculation fails. Safe to call from a worker thread."""
    from workspace_methods import run_method

    frame = load_verified(plan.files, plan.dataset_sha256)
    if frame is None:
        return None
    temp = ResearchSession()
    temp.set_dataset(frame, plan.dataset_name)
    for name, level in plan.levels.items():
        if level in LEVELS and level != "unknown" and name in temp.variables:
            temp.confirm_level(name, level)
    try:
        if plan.method == "posthoc":
            from analysis_runs import run_posthoc

            return run_posthoc(run_method("omnibus", temp, plan.roles, plan.options, plan.confirms))
        return run_method(plan.method, temp, plan.roles, plan.options, plan.confirms)
    except Exception:
        return None


def _release_at_exit(reference: "weakref.ReferenceType[ProjectBinding]") -> None:
    """Closing the window ends the process: release the project's lock so the
    next start does not report an interrupted session."""
    binding = reference()
    if binding is not None and binding.project is not None:
        try:
            binding.flush()          # a title still being typed (Stage 36.8)
        except Exception:
            pass
        try:
            binding.project.close()
        except Exception:
            pass


@dataclass(frozen=True)
class DeletedProject:
    path: Path
    title: str
    deleted: str      # "YYYYMMDD-HHMMSS" from the trash folder name


class ProjectBinding:
    def __init__(self, session: ResearchSession, root: Path):
        self.session = session
        self.root = Path(root)
        self.project: Project | None = None
        self.dataset_id: str | None = None
        self.unavailable: str | None = None   # why projects cannot be used here
        try:
            self.store: ProjectStore | None = ProjectStore(self.root)
        except OSError as error:
            self.store = None
            self.unavailable = str(error)
        self.generation = 0                    # changes whenever another project opens
        self._restoring = False
        self._saved_levels: dict[str, tuple[str, str]] = {}
        self._saved_runs: dict[int, int] = {}       # entry id -> id(run) saved
        self._saved_charts: dict[int, str | None] = {}  # entry id -> chart state digest
        # Stage 36.8 (K2): the researcher's entries as saved in the project.
        self._saved_notes: dict[int, tuple[str, frozenset]] = {}  # entry id -> (note, reviewed)
        self._saved_report = ReportSettings()
        self.message: tuple[str, str] | None = None  # (text key, tone) for the UI
        session.subscribe(self._on_session)
        atexit.register(_release_at_exit, weakref.ref(self))

    # ------------------------------------------------------------ queries
    @property
    def active(self) -> bool:
        return self.project is not None

    def info(self) -> ProjectInfo | None:
        return self.project.info() if self.project is not None else None

    def projects(self, *, include_archived: bool = False, query: str = "") -> list[ProjectInfo]:
        if self.store is None:
            return []
        return self.store.list(include_archived=include_archived, query=query)

    def deleted_projects(self) -> list[DeletedProject]:
        """Projects in the trash, newest first, with their titles."""
        if self.store is None:
            return []
        found = []
        for path in self.store.deleted():
            try:
                with closing(sqlite3.connect(
                        (path / DB_NAME).resolve().as_uri() + "?mode=ro", uri=True)) as db:
                    title = db.execute("SELECT title FROM project").fetchone()[0]
            except (sqlite3.Error, OSError, TypeError):
                continue
            found.append(DeletedProject(path, title, path.name.rsplit("-", 2)[-2] + "-"
                                        + path.name.rsplit("-", 1)[-1]))
        return sorted(found, key=lambda d: d.deleted, reverse=True)

    def stale_count(self) -> int:
        return sum(1 for entry in self.session.results if entry.stale_reasons)

    def _store(self) -> ProjectStore:
        if self.store is None:
            raise ProjectError(f"Projects cannot be saved here: {self.unavailable}")
        return self.store

    # ---------------------------------------------------------- lifecycle
    def create(self, title: str, **fields) -> ProjectInfo:
        """A new project. Work done without a project (a dataset, results)
        moves into it; another open project is closed and stays as it was."""
        info = self._store().create(title, **fields)
        adopt = self.project is None and (self.session.has_data or bool(self.session.results))
        self.open(info.id, keep_session=adopt)
        return self.info()

    def open(self, project_id: str, *, keep_session: bool = False) -> ProjectInfo:
        """Switch to a project. ``keep_session`` saves the current, unsaved work
        (dataset and results) into it instead of clearing the session."""
        if self.project is not None and self.project.id == project_id:
            return self.info()
        project = self._store().open(project_id)
        self.close(clear=not keep_session)
        self.project = project
        self.generation += 1
        self.message = ("project.recovered", "warning") if project.recovered else None
        if keep_session:
            self._adopt_session()
        else:
            self._restore()
        return self.info()

    def close(self, *, clear: bool = True) -> None:
        if self.project is None:
            return
        self.flush()
        self.project.close()
        self.project = None
        self.generation += 1
        self.dataset_id = None
        self._saved_levels = {}
        self._saved_runs = {}
        self._saved_charts = {}
        self._saved_notes = {}
        self._saved_report = ReportSettings()
        for entry in self.session.results:
            entry.record_id = None
            entry.stale_reasons = ()
        if clear:
            self._restoring = True
            try:
                self.session.clear()
            finally:
                self._restoring = False

    def duplicate(self, project_id: str) -> ProjectInfo:
        return self._store().duplicate(project_id)

    def set_archived(self, project_id: str, archived: bool) -> ProjectInfo:
        if self.project is not None and self.project.id == project_id:
            self.close()
        return self._store().set_archived(project_id, archived)

    def delete(self, project_id: str) -> Path:
        """Move to the trash (``restore_deleted`` brings it back)."""
        if self.project is not None and self.project.id == project_id:
            self.close()
        return self._store().delete(project_id)

    def restore_deleted(self, path: Path) -> ProjectInfo:
        return self._store().restore_deleted(path)

    def export(self, project_id: str, destination: Path, survey_root: Path | None) -> Path:
        """A ``.sra`` backup; uses its own database connections (worker-thread safe)."""
        return self._store().export_package(project_id, destination, survey_root=survey_root)

    def restore(self, source: Path, survey_root: Path | None) -> tuple[ProjectInfo, list[str]]:
        """Restore a ``.sra`` backup as a project (worker-thread safe)."""
        return self._store().import_package(source, survey_root=survey_root)

    def rename(self, title: str) -> ProjectInfo:
        if self.project is None:
            raise ProjectError("No project is open.")
        return self.project.update(title=title)

    # ------------------------------------------------------------ restore
    def _restore(self) -> None:
        project, session = self.project, self.session
        self._restoring = True
        try:
            session.clear()
            record = project.active_dataset()
            if record is not None:
                try:
                    self._show_dataset(record)
                except Exception:
                    self.message = ("project.dataset_missing", "warning")
            names = {d.id: d.name for d in project.datasets()}
            for run in project.runs():
                entry = session.add_result(
                    run_from_record(run, project.figure(run)), run.confirmations,
                    method=run.method, roles=run.roles, options=run.options,
                    confirms=run.confirms, dataset=names.get(run.dataset_id, "—"),
                    rows=run.provenance.get("rows") or 0, created=_local_time(run.created_at),
                    record_id=run.id, restored=True, task_id=run.task_id,
                    provenance={"dataset_sha256": run.dataset_sha256, "levels": dict(run.levels),
                                "variables": list(run.levels), "rows": run.provenance.get("rows")},
                    # Stage 37.0a: the hypothesis it was calculated for, if any.
                    hypothesis=run.hypothesis)
                entry.stale_reasons = project.run_status(run).reasons
                self._saved_runs[entry.id] = id(entry.run)
                # Stage 36.8 (K2): the researcher's note and reviewed checks.
                entry.note, entry.reviewed = run.note or "", frozenset(run.reviewed)
                self._saved_notes[entry.id] = (entry.note, entry.reviewed)
                if run.charts:
                    try:
                        from chart_views import ChartState

                        entry.charts = ChartState.from_dict(run.charts)
                    except (KeyError, TypeError, ValueError):
                        entry.charts = None      # unreadable: drawn again on request
                    self._saved_charts[entry.id] = self._chart_digest(entry.charts)
            by_record = {e.record_id: e for e in session.results}
            for run in project.report_runs():
                entry = by_record.get(run.id)
                if entry is not None:
                    entry.in_report = True
                    session.report_order.append(entry.id)
            from workspace_state import ResearchTask

            session.tasks = [ResearchTask(t.id, t.title, t.goal, dict(t.selection), t.method,
                                          dict(t.options), dict(t.confirms), t.hypothesis_id,
                                          dict(t.state)) for t in project.tasks()]
            session.report = ReportSettings.from_dict(project.report_settings())
            self._saved_report = session.report
            session.notify("results")
        finally:
            self._restoring = False

    def _show_dataset(self, record) -> None:
        """Put a stored dataset on screen with exactly its confirmed levels
        (call with ``_restoring`` set: nothing is saved again)."""
        project, session = self.project, self.session
        frame = project.load_frame(record.id)
        origin = "survey" if record.survey_id else ("file" if record.source_path else "copy")
        session.set_dataset(frame, record.name, path=record.source_path, origin=origin,
                            survey_id=record.survey_id)
        self.dataset_id = record.id
        saved = project.levels(record.id)
        for name in list(session.variables):
            row = saved.get(name) or {}
            level = row.get("level")
            if level in LEVELS and level != "unknown":
                session.confirm_level(name, level, row.get("confirmed_in") or "data")
            elif session.level(name) != "unknown":
                # Same column names as the table shown before: its levels are
                # not this dataset's confirmations.
                session.confirm_level(name, "unknown")
        self._saved_levels = self._current_levels()

    def activate_dataset(self, dataset_id: str):
        """Use another dataset of the open project. Nothing is replaced or
        lost: the dataset in use stays in the project, and the chosen one
        comes back with its confirmed measurement levels."""
        if self.project is None:
            raise ProjectError("No project is open.")
        record = self.project.dataset(dataset_id)
        self._restoring = True
        try:
            self._show_dataset(record)
        finally:
            self._restoring = False
        self.project.set_active_dataset(record.id)
        self._refresh_stale()
        return record

    def link_questionnaire(self, survey_id: str, title: str, role: str = "published") -> None:
        """Keep a questionnaire published while this project is open with it."""
        if self.project is not None:
            self.project.link_questionnaire(survey_id, title, role)

    def research_question(self) -> str:
        """The project's research question or hypothesis ("" when none)."""
        if self.project is None:
            return ""
        rows = self.project.questions()
        return rows[0]["text"] if rows else ""

    def set_research_question(self, text: str) -> None:
        """Keep the research question in the project (an empty text removes it)."""
        if self.project is None:
            return
        rows = self.project.questions()
        text = (text or "").strip()
        if rows and text:
            self.project.update_question(rows[0]["id"], text)
        elif rows:
            self.project.remove_question(rows[0]["id"])
        elif text:
            self.project.add_question(text, "hypothesis" if "?" not in text else "question")

    def questionnaire_ids(self) -> set[str]:
        if self.project is None:
            return set()
        return {row["survey_id"] for row in self.project.questionnaires()}

    def _adopt_session(self) -> None:
        """Save the work already on screen into the (new) project."""
        if self.session.has_data:
            self._save_dataset()
            self._save_levels()
        self._save_results()
        self._save_report()
        self._save_report_settings()

    # ------------------------------------------------------- recalculation
    def recalculation(self, entry) -> Recalculation | None:
        """What a worker needs to calculate a saved result again (UI thread)."""
        if self.project is None or not entry.record_id or not entry.method:
            return None
        try:
            record = self.project.run(entry.record_id)
            if not record.dataset_id:
                return None
            files = self.project.version_files(record.dataset_id, record.dataset_sha256)
        except ProjectError:
            return None
        return Recalculation(record.method, dict(record.roles), dict(record.options),
                             dict(record.confirms), dict(record.levels), entry.dataset,
                             record.dataset_sha256, files)

    async def ensure_result(self, entry) -> bool:
        """Give a restored result its full engine object again (for Word export
        and post-hoc tests); False when the saved result cannot be reproduced."""
        if entry.run.result is not None:
            return True
        plan = self.recalculation(entry)
        if plan is None:
            return False
        generation = self.generation
        run = await asyncio.to_thread(recalculate, plan)
        if run is None or generation != self.generation or entry not in self.session.results:
            return False
        if not same_report(run, entry.run):
            self._mark_different(entry)
            return False
        entry.run = run
        self._saved_runs[entry.id] = id(run)
        return True

    async def verify_restored(self) -> int:
        """Recalculate restored results in the background; returns how many matched."""
        generation = self.generation
        verified = 0
        for entry in list(self.session.results):
            if generation != self.generation:
                break
            if not entry.restored or entry.run.result is not None:
                continue
            if await self.ensure_result(entry):
                verified += 1
        if verified and generation == self.generation:
            self.session.notify("results")
        return verified

    def _mark_different(self, entry) -> None:
        reason = "recalculated report differs from the saved one"
        if reason not in entry.stale_reasons:
            entry.stale_reasons = tuple(entry.stale_reasons) + (reason,)

    # -------------------------------------------------------- persistence
    def _on_session(self, what: str) -> None:
        if self._restoring or self.project is None:
            return
        try:
            if what == "dataset":
                self._save_dataset()
            elif what == "dictionary":
                self._save_levels()
            elif what == "results":
                self._save_results()
            elif what == "report":
                self._save_report()
            elif what == "tasks":
                self._save_tasks()
            elif what == "charts":
                self._save_charts()
            elif what == "notes":
                self._save_notes()
            elif what == "report_settings":
                self._save_report_settings()
        except Exception:
            self.message = ("project.save_failed", "danger")

    def flush(self) -> None:
        """Save what the session holds and the project does not yet: a report
        title typed but not yet saved (it is saved when the field is left).
        Called before the project closes and when the program ends."""
        if self.project is None or self._restoring:
            return
        try:
            self._save_notes()
            self._save_report_settings()
        except Exception:
            self.message = ("project.save_failed", "danger")

    def _save_notes(self) -> None:
        """The researcher's note and reviewed checks of every saved result are
        written through, like research tasks (Stage 36.8, K2)."""
        for entry in self.session.results:
            if not entry.record_id:
                continue
            note, reviewed = self._saved_notes.get(entry.id, ("", frozenset()))
            if note != entry.note:
                self.project.set_note(entry.record_id, entry.note)
            if reviewed != entry.reviewed:
                self.project.set_reviewed(entry.record_id, entry.reviewed)
            self._saved_notes[entry.id] = (entry.note, entry.reviewed)

    def _save_report_settings(self) -> None:
        """The report's title, sections and language belong to the project."""
        report = self.session.report
        if report != self._saved_report:
            self.project.save_report_settings(report.to_dict())
            self._saved_report = report

    def _save_tasks(self) -> None:
        """Research tasks are written through: what the researcher chose is in
        the project as soon as it changes (Stage 36)."""
        known = {t.id for t in self.project.tasks()}
        for task in self.session.tasks:
            self.project.save_task(task_id=task.id, title=task.title, goal=task.goal,
                                   selection=task.selection, method=task.method,
                                   options=task.options, confirms=task.confirms,
                                   hypothesis_id=task.hypothesis_id, state=task.state)
            known.discard(task.id)
        for task_id in known:                      # removed in the session
            self.project.delete_task(task_id)

    @staticmethod
    def _chart_digest(state) -> str | None:
        if state is None:
            return None
        return sha256_bytes(json.dumps(state.to_dict(), sort_keys=True, default=str)
                            .encode("utf-8"))

    def _save_charts(self) -> None:
        """Chart views are written through, like research tasks: a changed
        view is in the project as soon as it is chosen (Stage 36.4)."""
        for entry in self.session.results:
            if not entry.record_id or entry.charts is None:
                continue
            digest = self._chart_digest(entry.charts)
            if self._saved_charts.get(entry.id) == digest:
                continue
            self.project.set_run_charts(entry.record_id, entry.charts.to_dict())
            self._saved_charts[entry.id] = digest

    def _save_dataset(self) -> None:
        session, project = self.session, self.project
        if not session.has_data:
            return
        frame, name = session.df, session.source_name or "Dataset"
        digest = sha256_bytes(frame.to_csv(index=False, lineterminator="\n").encode("utf-8"))
        origin, path = session.dataset_origin, session.source_path
        record = None
        if origin == "survey" and session.dataset_survey_id:
            survey_id = session.dataset_survey_id
            record = next((d for d in project.datasets() if d.survey_id == survey_id), None)
            if record is None:
                record = project.add_frame(frame, name, origin="survey", survey_id=survey_id)
            elif record.sha256 != digest:
                record = project.replace_dataset(record.id, frame=frame,
                                                 reason="questionnaire responses loaded again")
                self.message = ("project.new_version", "warning")
            project.link_questionnaire(survey_id, name)
        elif origin in FILE_ORIGINS and path:
            record = project.find_by_source(path)
            if record is not None and record.origin == "link":
                record = None              # a linked file versions itself; store a copy
            if record is None:
                record = project.import_table(frame, name, source_path=path)
            elif record.sha256 != digest:
                record = project.replace_dataset(record.id, frame=frame,
                                                 reason="loaded again from the same file")
                self.message = ("project.new_version", "warning")
        elif origin == "prepared":
            record = project.add_frame(frame, name, origin="derived", parent_id=self.dataset_id)
            # Stage 36.3: the rule that made a derived variable is kept with
            # the dataset version it created.
            for step in session.pending_transformations:
                project.add_transformation(record.id, step["kind"], step["params"],
                                           step["output_columns"])
            session.pending_transformations.clear()
        else:
            # A sample, an uploaded copy or the classic interface's table:
            # the same content is not stored twice.
            record = next((d for d in project.datasets()
                           if d.sha256 == digest and d.origin == "copy"), None)
            if record is None:
                record = project.add_frame(frame, name, origin="copy")
        project.set_active_dataset(record.id)
        self.dataset_id = record.id
        self._saved_levels = {}
        self._save_levels()
        self._refresh_stale()

    def _current_levels(self) -> dict[str, tuple[str, str]]:
        return {name: (info.confirmed, info.confirmed_in)
                for name, info in self.session.variables.items() if info.confirmed != "unknown"}

    def _save_levels(self) -> None:
        if self.dataset_id is None:
            return
        current = self._current_levels()
        changed = {name: value for name, value in current.items()
                   if self._saved_levels.get(name) != value}
        removed = {name: (None, "") for name in self._saved_levels if name not in current}
        if changed or removed:
            self.project.save_levels(self.dataset_id, {**changed, **removed})
        self._saved_levels = current
        self._refresh_stale()

    def _save_results(self) -> None:
        session = self.session
        for entry in session.results:
            if self._saved_runs.get(entry.id) == id(entry.run):
                continue
            if entry.method is None:
                continue  # not produced by a known method: stays in this session only
            previous = None
            if entry.record_id:  # replaced in place (post-hoc tests on an omnibus result)
                try:
                    previous = self.project.run(entry.record_id)
                except ProjectError:
                    previous = None
            if previous is not None:
                # A follow-up of a saved result keeps that result's data version.
                dataset_id, version, levels = (previous.dataset_id, previous.dataset_sha256,
                                               previous.levels)
            else:
                # Work done before the project existed may come from an earlier
                # table; only results of the table on screen are linked to it.
                current = (session.has_data and entry.dataset == session.source_name
                           and entry.rows == len(session.df))
                dataset_id, version = (self.dataset_id if current else None), None
                used = {v for value in (entry.roles or {}).values()
                        for v in (value if isinstance(value, list) else [value])
                        if isinstance(v, str)}
                levels = {name: session.level(name) for name in used
                          if name in session.variables and session.level(name) != "unknown"}
            record = self.project.record_run(
                entry.run, method=entry.method, dataset_id=dataset_id,
                roles=entry.roles or {}, options=entry.options or {},
                confirms=entry.confirms or {}, confirmations=entry.confirmations,
                levels=levels, dataset_sha256=version or None, task_id=entry.task_id,
                hypothesis=(entry.provenance or {}).get("hypothesis"))
            # The researcher's entries stay with the result (also a replaced one).
            if entry.note:
                self.project.set_note(record.id, entry.note)
            if entry.reviewed:
                self.project.set_reviewed(record.id, entry.reviewed)
            self._saved_notes[entry.id] = (entry.note, entry.reviewed)
            if previous is not None:   # only once the replacement is safely stored
                self.project.delete_run(previous.id)
            entry.record_id = record.id
            entry.stale_reasons = self.project.run_status(record).reasons
            self._saved_runs[entry.id] = id(entry.run)
            self._saved_charts.pop(entry.id, None)
        self._save_charts()
        self._save_report()

    def _save_report(self) -> None:
        if self.project is None:
            return
        self.project.set_report([e.record_id for e in self.session.report_entries() if e.record_id])

    def _refresh_stale(self) -> None:
        for entry in self.session.results:
            if entry.record_id:
                try:
                    status = self.project.run_status(self.project.run(entry.record_id))
                except ProjectError:
                    entry.stale_reasons = ("removed from the project",)
                    continue
                differs = [r for r in entry.stale_reasons if r.startswith("recalculated")]
                entry.stale_reasons = tuple(status.reasons) + tuple(differs)
