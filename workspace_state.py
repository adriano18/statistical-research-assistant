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

    @property
    def title(self) -> str:
        return self.run.title


@dataclass
class ResearchSession:
    df: pd.DataFrame | None = None
    source_name: str = ""
    import_report: object | None = None
    source_path: str | None = None
    variables: dict[str, VariableInfo] = field(default_factory=dict)
    results: list[ResultEntry] = field(default_factory=list)
    report_order: list[int] = field(default_factory=list)
    selected_result: int | None = None
    guided: dict = field(default_factory=dict)       # guided-analysis selections
    language: str = "en"
    theme: str = "light"
    corners: str = "windows"
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1), repr=False)
    _listeners: list[Callable[[str], None]] = field(default_factory=list, repr=False)

    # ----------------------------------------------------------- events
    def subscribe(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def notify(self, what: str) -> None:
        for listener in list(self._listeners):
            listener(what)

    # ---------------------------------------------------------- dataset
    @property
    def has_data(self) -> bool:
        return self.df is not None and not self.df.columns.empty

    def set_dataset(self, df: pd.DataFrame, name: str, *, report=None,
                    path: str | None = None) -> None:
        if df is None or df.columns.empty:
            raise ValueError("No variables found in this file.")
        same_columns = self.df is not None and list(self.df.columns) == list(df.columns)
        self.variables = build_dictionary(df, self.variables if same_columns else None)
        self.df = df
        self.source_name = name
        self.import_report = report
        self.source_path = path
        self.guided = {}
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

    def group_labels(self, name: str) -> list[str]:
        if not self.has_data or name not in self.df.columns:
            return []
        values = self.df[name].dropna().astype(str)
        return sorted(values.unique().tolist())

    # ---------------------------------------------------------- results
    def add_result(self, run, confirmations=()) -> ResultEntry:
        entry = ResultEntry(
            id=next(self._ids), run=run, dataset=self.source_name,
            rows=0 if self.df is None else len(self.df), created=datetime.now(),
            confirmations=tuple(confirmations),
        )
        self.results.append(entry)
        self.selected_result = entry.id
        self.notify("results")
        return entry

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
                "", entry.run.report.strip(), "",
            ]
        return "\n".join(parts).rstrip() + "\n"
