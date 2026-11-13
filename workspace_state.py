"""Session state for the Stage 33 workspace (no Flet imports).

* :class:`VariableInfo` — one row of the variable dictionary. The suggested
  measurement level is a heuristic; only ``confirmed`` is ever used by an
  analysis, and every confirmation records where it was made.
* :class:`ResearchSession` — the open dataset, its dictionary, the results
  log and the report selection. Everything lives in memory for the current
  session; nothing here pretends to be project persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import itertools
from typing import Callable

import pandas as pd

from variable_rules import looks_like_identifier

LEVELS = ("unknown", "id", "nominal", "ordinal", "scale")
ANALYSIS_LEVELS = ("nominal", "ordinal", "scale")


@dataclass(frozen=True)
class VariableInfo:
    name: str
    storage: str              # "number" | "text" | "empty"
    suggested: str            # one of LEVELS (heuristic only)
    missing: int
    distinct: int
    binary: bool              # numeric values ⊆ {0, 1}
    confirmed: str = "unknown"
    confirmed_in: str = ""    # "data", "analyze", "data-bulk"

    @property
    def level(self) -> str:
        return self.confirmed


def suggest_level(name: str, values: pd.Series) -> tuple[str, str, int, bool]:
    """(storage, suggested level, distinct, binary) — never authoritative."""
    clean = values.dropna()
    distinct = int(clean.nunique())
    if clean.empty:
        return "empty", "unknown", 0, False
    numeric = pd.to_numeric(clean, errors="coerce")
    is_number = bool(numeric.notna().all())
    if looks_like_identifier(name):
        return ("number" if is_number else "text"), "id", distinct, False
    if is_number:
        binary = set(numeric.unique()) <= {0, 1}
        integers = bool((numeric == numeric.round()).all())
        if distinct <= 2:
            return "number", "nominal", distinct, binary
        if integers and distinct <= 7:
            return "number", "ordinal", distinct, binary
        return "number", "scale", distinct, binary
    if distinct <= 20 or distinct <= max(2, len(clean) // 3):
        return "text", "nominal", distinct, False
    if distinct == len(clean) == len(values) and len(clean) >= 10:
        # A different text code in every row (P001, q17, fictional_003): a
        # participant code, suggested as identifier (Stage 36 audit). Still
        # only a suggestion; the researcher confirms it.
        return "text", "id", distinct, False
    return "text", "unknown", distinct, False


def build_dictionary(df: pd.DataFrame,
                     previous: dict[str, VariableInfo] | None = None) -> dict[str, VariableInfo]:
    """Variable dictionary; confirmations survive a re-import of the same column."""
    previous = previous or {}
    result = {}
    for name in df.columns:
        storage, suggested, distinct, binary = suggest_level(str(name), df[name])
        info = VariableInfo(
            name=str(name), storage=storage, suggested=suggested,
            missing=int(df[name].isna().sum()), distinct=distinct, binary=binary,
        )
        old = previous.get(str(name))
        if old is not None and old.storage == storage and old.confirmed != "unknown":
            info = replace(info, confirmed=old.confirmed, confirmed_in=old.confirmed_in)
        result[str(name)] = info
    return result


@dataclass
class ResultEntry:
    id: int
    run: object                     # analysis_runs.AnalysisRun
    dataset: str
    rows: int
    created: datetime
    confirmations: tuple[str, ...] = ()
    in_report: bool = False
    # How the result was produced (method key, variable roles, effective
    # options, confirmations) — what a project stores to reproduce it.
    method: str | None = None
    roles: dict | None = None
    options: dict | None = None
    confirms: dict | None = None
    record_id: str | None = None    # saved analysis run in the open project
    restored: bool = False          # loaded from the project, not calculated now
    stale_reasons: tuple[str, ...] = ()
    # What the result was calculated on (Issue #32): the dataset version
    # (SHA-256 of its table), the confirmed level of every variable used,
    # group labels, and how many rows were complete for those variables.
    provenance: dict = field(default_factory=dict)
    task_id: str | None = None      # Stage 36: the research task this run belongs to
    # Stage 36.4: the values the result's charts are drawn from and the
    # researcher's chart views (chart_views.ChartState); None until opened.
    charts: object | None = None

    @property
    def title(self) -> str:
        return self.run.title


@dataclass
class ResearchTask:
    """Stage 36 (spec §4): one research question's analysis set-up, kept so
    it can be run again or continued, also after a restart."""

    id: str
    title: str
    goal: str
    selection: dict
    method: str = ""
    options: dict = field(default_factory=dict)
    confirms: dict = field(default_factory=dict)
    hypothesis_id: str | None = None
    state: dict = field(default_factory=dict)


@dataclass
class ResearchSession:
    df: pd.DataFrame | None = None
    source_name: str = ""
    import_report: object | None = None
    source_path: str | None = None
    # Where the table came from: "file", "sample", "upload", "survey",
    # "prepared" or "classic" — what a project records as its provenance.
    dataset_origin: str = ""
    dataset_survey_id: str | None = None
    variables: dict[str, VariableInfo] = field(default_factory=dict)
    results: list[ResultEntry] = field(default_factory=list)
    report_order: list[int] = field(default_factory=list)
    selected_result: int | None = None
    guided: dict = field(default_factory=dict)       # guided-analysis selections
    tasks: list[ResearchTask] = field(default_factory=list)   # Stage 36 research tasks
    # Stage 36.3: a saved questionnaire by id (set by the application), so
    # item diagnostics can use reverse keys the researcher confirmed.
    questionnaire_loader: Callable[[str], object] | None = field(default=None, repr=False)
    # Stage 36.3: history records of derived variables not yet stored with
    # the dataset version they created (the project stores and clears them).
    pending_transformations: list[dict] = field(default_factory=list, repr=False)
    language: str = "en"
    theme: str = "light"
    corners: str = "windows"
    accent: str = "blue"           # accent colour preset (workspace_tokens.ACCENTS)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1), repr=False)
    _listeners: list[Callable[[str], None]] = field(default_factory=list, repr=False)

    # ----------------------------------------------------------- events
    def subscribe(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def notify(self, what: str) -> None:
        for listener in list(self._listeners):
            listener(what)

    def clear(self) -> None:
        """Forget the dataset, results and report (switching projects);
        language, theme and listeners stay."""
        self.df = None
        self.source_name = ""
        self.import_report = None
        self.source_path = None
        self.dataset_origin = ""
        self.dataset_survey_id = None
        self.variables = {}
        self.results = []
        self.report_order = []
        self.selected_result = None
        self.guided = {}
        self.tasks = []
        self.pending_transformations = []
        self.notify("dataset")
        self.notify("results")

    # ---------------------------------------------------------- dataset
    @property
    def has_data(self) -> bool:
        return self.df is not None and not self.df.columns.empty

    def set_dataset(self, df: pd.DataFrame, name: str, *, report=None,
                    path: str | None = None, origin: str | None = None,
                    survey_id: str | None = None) -> None:
        if df is None or df.columns.empty:
            raise ValueError("No variables found in this file.")
        same_columns = self.df is not None and list(self.df.columns) == list(df.columns)
        self.variables = build_dictionary(df, self.variables if same_columns else None)
        self.df = df
        self.source_name = name
        self.import_report = report
        self.source_path = path
        self.dataset_origin = origin or ("file" if path else "copy")
        self.dataset_survey_id = survey_id
        self.guided = {}
        self.notify("dataset")

    def add_derived_column(self, frame: pd.DataFrame, column: str, level: str,
                           record: dict) -> None:
        """Use ``frame`` (the dataset with one new derived column) as the new
        version of the data: every other variable keeps its confirmed level,
        the new one gets ``level`` (it is defined by its rule), and the rule
        is kept as a history record. The source columns are not changed."""
        if column not in frame.columns or (self.df is not None and column in self.df.columns):
            raise ValueError(f"{column} must be a new column.")
        if level not in LEVELS:
            raise ValueError(f"Unknown measurement level: {level}")
        name = self.source_name or "Dataset"
        variables = build_dictionary(frame, self.variables)
        variables[column] = replace(variables[column], confirmed=level, confirmed_in="derived")
        self.variables = variables
        self.df = frame
        if not name.endswith("(prepared)"):
            name = f"{name} (prepared)"
        self.source_name = name
        self.dataset_origin = "prepared"
        self.pending_transformations.append(dict(record))
        self.notify("dataset")

    def confirm_level(self, name: str, level: str, where: str = "data") -> None:
        if level not in LEVELS:
            raise ValueError(f"Unknown measurement level: {level}")
        info = self.variables[name]
        self.variables[name] = replace(
            info, confirmed=level, confirmed_in=where if level != "unknown" else "",
        )
        self.notify("dictionary")

    def accept_suggestions(self) -> int:
        """Confirm every still-unconfirmed variable from its suggestion."""
        changed = 0
        for name, info in list(self.variables.items()):
            if info.confirmed == "unknown" and info.suggested != "unknown":
                self.variables[name] = replace(
                    info, confirmed=info.suggested, confirmed_in="data-bulk",
                )
                changed += 1
        if changed:
            self.notify("dictionary")
        return changed

    def pending_levels(self) -> int:
        return sum(1 for v in self.variables.values() if v.confirmed == "unknown")

    def level(self, name: str) -> str:
        info = self.variables.get(name)
        return info.confirmed if info else "unknown"

    def missing_cells(self) -> int:
        return int(self.df.isna().sum().sum()) if self.has_data else 0

    def value_summary(self, name: str, language: str = "en") -> str:
        """What a column holds, to confirm its level by its content (Issue #32):
        categories with counts, the codes of a short numeric scale, or the
        range of a quantitative score — never the storage type alone."""
        if not self.has_data or name not in self.df.columns:
            return ""
        series = self.df[name].dropna()
        if series.empty:
            return "—"
        distinct = series.nunique()
        numeric = pd.api.types.is_numeric_dtype(series)
        if distinct == len(series) and distinct > 20:
            from workspace_text import t

            return t(language, "data.values_unique", count=distinct)
        if numeric and distinct > 12:
            low, high = series.min(), series.max()
            fmt = (lambda v: f"{v:g}")
            return f"{fmt(low)} – {fmt(high)}"
        counts = series.value_counts() if numeric else series.astype(str).value_counts()
        order = sorted(counts.index)

        def show(value) -> str:     # 4 rather than 4.0 for the codes of a scale
            return f"{value:g}" if numeric else str(value)

        shown = [f"{show(value)} ({counts[value]})" for value in order[:8]]
        return ", ".join(shown) + (" …" if distinct > 8 else "")

    def group_labels(self, name: str) -> list[str]:
        if not self.has_data or name not in self.df.columns:
            return []
        values = self.df[name].dropna().astype(str)
        return sorted(values.unique().tolist())

    # ---------------------------------------------------------- results
    def add_result(self, run, confirmations=(), *, method: str | None = None,
                   roles: dict | None = None, options: dict | None = None,
                   confirms: dict | None = None, dataset: str | None = None,
                   rows: int | None = None, created: datetime | None = None,
                   record_id: str | None = None, restored: bool = False,
                   provenance: dict | None = None, task_id: str | None = None) -> ResultEntry:
        if provenance is None:
            provenance = {} if restored else self.provenance_for(roles)
        entry = ResultEntry(
            id=next(self._ids), run=run, dataset=self.source_name if dataset is None else dataset,
            rows=(0 if self.df is None else len(self.df)) if rows is None else rows,
            created=created or datetime.now(), confirmations=tuple(confirmations),
            method=method, roles=roles, options=options, confirms=confirms,
            record_id=record_id, restored=restored, provenance=provenance, task_id=task_id,
        )
        self.results.append(entry)
        self.selected_result = entry.id
        self.notify("results")
        return entry

    def provenance_for(self, roles: dict | None) -> dict:
        """The facts a result rests on, taken from the table on screen."""
        import hashlib

        if self.df is None:
            return {}
        used = []
        for value in (roles or {}).values():
            for name in (value if isinstance(value, (list, tuple)) else [value]):
                if isinstance(name, str) and name in self.df.columns and name not in used:
                    used.append(name)
        table = self.df.to_csv(index=False, lineterminator="\n").encode("utf-8")
        levels = {name: self.level(name) for name in used}
        groups = {name: self.group_labels(name)[:12] for name in used
                  if levels[name] in ("nominal", "ordinal")}
        complete = int(self.df[used].notna().all(axis=1).sum()) if used else len(self.df)
        how = {name: self.variables[name].confirmed_in for name in used if name in self.variables}
        return {"dataset_sha256": hashlib.sha256(table).hexdigest(), "variables": used,
                "levels": levels, "groups": groups, "complete": complete,
                "rows": len(self.df), "confirmed_in": how}

    # ------------------------------------------------------ research tasks
    def task(self, task_id: str | None) -> ResearchTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def save_task(self, task: ResearchTask) -> ResearchTask:
        """Add the task or replace the one with its id; listeners save it."""
        for index, existing in enumerate(self.tasks):
            if existing.id == task.id:
                self.tasks[index] = task
                break
        else:
            self.tasks.append(task)
        self.notify("tasks")
        return task

    def save_charts(self, entry_id: int) -> None:
        """The chart views of a result changed; listeners store them."""
        if self.result(entry_id) is not None:
            self.notify("charts")

    def task_results(self, task_id: str) -> list[ResultEntry]:
        return [entry for entry in self.results if entry.task_id == task_id]

    def result(self, entry_id: int | None) -> ResultEntry | None:
        return next((r for r in self.results if r.id == entry_id), None)

    def replace_run(self, entry_id: int, run) -> None:
        entry = self.result(entry_id)
        if entry is not None:
            entry.run = run
            self.notify("results")

    def toggle_report(self, entry_id: int) -> bool:
        entry = self.result(entry_id)
        if entry is None:
            return False
        entry.in_report = not entry.in_report
        if entry.in_report:
            self.report_order.append(entry_id)
        else:
            self.report_order = [i for i in self.report_order if i != entry_id]
        self.notify("report")
        return entry.in_report

    def move_in_report(self, entry_id: int, step: int) -> None:
        order = self.report_order
        if entry_id not in order:
            return
        index = order.index(entry_id)
        target = max(0, min(len(order) - 1, index + step))
        order.insert(target, order.pop(index))
        self.notify("report")

    def report_entries(self) -> list[ResultEntry]:
        return [e for e in (self.result(i) for i in self.report_order) if e is not None]

    def combined_report(self, study_title: str = "") -> str:
        """Plain-text report made ONLY of the engine's own report texts."""
        parts = []
        if study_title.strip():
            parts += [study_title.strip(), "=" * len(study_title.strip()), ""]
        for number, entry in enumerate(self.report_entries(), start=1):
            heading = f"{number}. {entry.run.title}"
            parts += [
                heading, "-" * len(heading),
                f"Dataset: {entry.dataset} ({entry.rows} rows) · "
                f"calculated {entry.created:%Y-%m-%d %H:%M}",
            ]
            if entry.stale_reasons:
                parts.append("Needs review: calculated before these changes: "
                             + "; ".join(entry.stale_reasons) + ".")
            parts += ["", entry.run.report.strip(), ""]
        return "\n".join(parts).rstrip() + "\n"
