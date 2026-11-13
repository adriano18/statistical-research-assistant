"""Exports of a dataset with its codebook (Stage 37, issue #67).

No Flet here: the workspace (``workspace_export``) and the tests call these
functions directly.

Formats and what each carries (docs/STAGE37_EXPORT.md has the full table):

* ``.xlsx`` (openpyxl, streaming write-only mode): the sheets Data,
  Codebook, Scales, Results and Provenance, each optional. Numbers are
  written as numbers, dates and times as spreadsheet dates, and every text
  cell explicitly as text, so nothing is ever evaluated as a formula and an
  identifier such as ``001`` keeps its leading zeros. A missing value is an
  empty cell; an empty text is a text cell with no characters, and a
  user-missing code (``-9``, ``DK``) is written as itself and listed in the
  codebook, never blanked.
* ``.csv`` (UTF-8, optional byte-order mark): numbers unquoted with every
  digit Python needs to read the same number back (``repr``), every text
  quoted (``""`` is an empty text, an unquoted empty field a missing value),
  and the OWASP formula protection of ``csv_safety`` on text cells. Two
  layouts: comma-separated with a decimal point, or semicolon-separated with
  a decimal comma, which Excel set to Latvian or Russian opens in columns.
  The codebook is written next to the file (``<name>_codebook.json``).
* ``.sav`` (pyreadstat / ReadStat): SPSS variable names (a reversible
  rename table), variable labels, value labels, measurement levels and
  user-defined missing values within the format's limits; identifiers are
  string variables. Every renamed, cut or converted field is listed before
  saving (:func:`plan_sav`). The project's audit trail,
  derived-variable history and analysis provenance are not part of a .sav
  file; they are exported separately (codebook, bundle).

Every file is written to a temporary file in the chosen folder, re-opened
with an independent reader (openpyxl, csv, pyreadstat, zipfile) to check its
signature and row count, and only then moved into place (:func:`save_atomic`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import csv
from dataclasses import asdict, dataclass, field
import datetime as dt
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import unicodedata
import zipfile

import numpy as np
import pandas as pd

import csv_safety
from variable_rules import looks_like_identifier

FORMATS = ("xlsx", "sav", "csv")
SECTIONS = ("data", "codebook", "scales", "results", "provenance")
SHEET_TITLES = {"data": "Data", "codebook": "Codebook", "scales": "Scales",
                "results": "Results", "provenance": "Provenance"}
LEVELS = ("unknown", "id", "nominal", "ordinal", "scale")

XLSX_MAX_ROWS = 1_048_576          # rows per worksheet, the header included
XLSX_MAX_TEXT = 32_767             # characters per cell
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_EXACT_INTEGER = 2 ** 53           # every integer up to this is a double exactly

# SPSS (sav) limits, as ReadStat enforces them (checked against pyreadstat 1.3.7).
SAV_NAME_BYTES = 64
SAV_LABEL_BYTES = 256
SAV_VALUE_LABEL_BYTES = 120
SAV_FILE_LABEL_BYTES = 64
SAV_NOTE_BYTES = 80
SAV_MISSING_DISCRETE = 3
SAV_MISSING_STRING_BYTES = 8
SAV_RESERVED = frozenset({"ALL", "AND", "BY", "EQ", "GE", "GT", "LE", "LT", "NE", "NOT", "OR",
                          "TO", "WITH"})
SAV_MEASURE = {"nominal": "nominal", "ordinal": "ordinal", "scale": "scale",
               "id": "nominal", "unknown": "unknown"}

PROGRESS_EVERY = 2_000             # rows between progress calls
CSV_LAYOUTS = {"comma": (",", "dot"), "semicolon": (";", "comma")}
METADATA_SOURCES = {"sav": "the SPSS file", "codebook": "the exported codebook",
                    "project": "the project"}

Progress = Callable[[int, int], None]


class ExportError(Exception):
    """An export that cannot be made as asked; the message says why."""


class VerificationFailed(ExportError):
    """The file was written but re-reading it did not give what was written."""


# ============================================================ values and kinds
def is_missing(value) -> bool:
    if value is None or value is pd.NaT or value is pd.NA:
        return True
    if isinstance(value, (float, np.floating)):
        return math.isnan(value)
    if isinstance(value, (np.datetime64, np.timedelta64)):
        return bool(np.isnat(value))
    return False


def value_kind(value) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "boolean"
    if isinstance(value, (int, float, np.integer, np.floating, Decimal)):
        return "number"
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return "datetime_tz" if value.tzinfo is not None else "datetime"
    if isinstance(value, np.datetime64):
        return "datetime"
    if isinstance(value, dt.date):
        return "date"
    if isinstance(value, dt.time):
        return "time" if value.tzinfo is None else "text"
    if isinstance(value, (dt.timedelta, pd.Timedelta, np.timedelta64)):
        return "duration"
    return "text"


def column_kind(values: pd.Series) -> str:
    """number, boolean, datetime, datetime_tz, date, time, duration, category,
    text, mixed or empty (every value missing)."""
    dtype = values.dtype
    if isinstance(dtype, pd.CategoricalDtype):
        return "category"
    if pd.api.types.is_bool_dtype(dtype):
        return "boolean"
    if pd.api.types.is_numeric_dtype(dtype):
        return "number" if values.notna().any() else "empty"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "datetime_tz" if getattr(dtype, "tz", None) is not None else "datetime"
    if pd.api.types.is_timedelta64_dtype(dtype):
        return "duration"
    kinds = {value_kind(v) for v in values if not is_missing(v)}
    if not kinds:
        return "empty"
    if kinds == {"date", "datetime"}:
        return "datetime"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def number_text(value) -> str:
    """A number as text that reads back as the same number: integers without a
    decimal point, other numbers with every digit Python needs (``repr``)."""
    if isinstance(value, (bool, np.bool_)):
        return "True" if value else "False"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    number = float(value)
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    if _whole(number):
        return str(int(number))
    return repr(number)


def _whole(number: float) -> bool:
    """A double that is an integer a reader gets back exactly (not -0.0)."""
    return (number.is_integer() and abs(number) < _EXACT_INTEGER
            and not (number == 0 and math.copysign(1.0, number) < 0))


def plain_number(value):
    """The value as a Python int or float (what the writers write)."""
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    number = float(value)
    return int(number) if _whole(number) else number


def as_text(value) -> str:
    """Any value as the text a person would read (no formula protection)."""
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, np.bool_)):
        return "True" if value else "False"
    if isinstance(value, (int, float, np.integer, np.floating, Decimal)):
        return number_text(value)
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        stamp = pd.Timestamp(value)
        if stamp.tzinfo is None and stamp == stamp.normalize():
            return stamp.strftime("%Y-%m-%d")
        return stamp.isoformat(sep=" ")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return as_text(pd.Timestamp(value))
    return str(value)


def utf8_cut(text: str, limit: int) -> str:
    """``text`` cut to at most ``limit`` UTF-8 bytes, never inside a character."""
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode("utf-8", errors="ignore")


# ================================================================== codebook
@dataclass
class VariableEntry:
    """One row of the codebook."""

    name: str
    position: int
    kind: str
    dtype: str
    label: str = ""
    label_source: str = ""
    level: str = "unknown"            # the confirmed measurement level
    confirmed_in: str = ""
    suggested: str = ""
    value_labels: dict = field(default_factory=dict)     # code (text) -> label
    missing_codes: list = field(default_factory=list)    # user-missing codes, as in the data
    missing_source: str = ""
    categories: list = field(default_factory=list)      # a categorical column's categories
    ordered: bool = False
    valid: str = ""                   # valid codes or the observed range, as text
    n_valid: int = 0
    n_missing: int = 0                # missing values (empty cells)
    n_user_missing: int = 0           # values equal to a user-missing code
    n_empty_text: int = 0             # texts with no characters (not missing)
    n_distinct: int = 0
    minimum: float | None = None
    maximum: float | None = None
    reverse: bool = False
    reverse_note: str = ""
    scales: list = field(default_factory=list)          # scales this variable belongs to
    derived: str = ""                 # the rule that made a derived variable
    spss_name: str = ""
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("minimum", "maximum"):
            if data[key] is not None:
                data[key] = plain_number(data[key])
        data["missing_codes"] = [dict(c) if isinstance(c, dict) else c
                                 for c in self.missing_codes]
        return data


@dataclass
class Codebook:
    dataset: str
    rows: int
    columns: int
    sha256: str
    variables: list[VariableEntry]
    scales: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    questionnaires: list[str] = field(default_factory=list)
    created: str = ""
    app_version: str = ""

    def variable(self, name: str) -> VariableEntry | None:
        return next((v for v in self.variables if v.name == name), None)

    @property
    def renamed(self) -> dict[str, str]:
        """{original name: SPSS name} for every variable whose name changes."""
        return {v.name: v.spss_name for v in self.variables if v.spss_name != v.name}

    def to_dict(self) -> dict:
        return {
            "format": csv_safety.CODEBOOK_FORMAT, "version": 1,
            "dataset": {"name": self.dataset, "rows": self.rows, "columns": self.columns,
                        "sha256": self.sha256},
            "created": self.created, "app_version": self.app_version,
            "questionnaires": list(self.questionnaires),
            "variables": [v.to_dict() for v in self.variables],
            "scales": _json_safe(self.scales),
            "history": _json_safe(self.history),
            "spss_names": {v.name: v.spss_name for v in self.variables},
        }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else str(number)
    if isinstance(value, (dt.date, dt.datetime, dt.time, pd.Timestamp)):
        return as_text(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _code_text(code) -> str:
    """A value-label or missing code as the codebook writes it (``1``, ``-9``, ``DK``)."""
    if isinstance(code, str):
        stripped = code.strip()
        try:
            return number_text(float(stripped)) if stripped else code
        except ValueError:
            return code
    return number_text(code) if isinstance(code, (int, float, np.number)) else str(code)


def _matches_code(value, codes_text: set[str]) -> bool:
    if is_missing(value) or not codes_text:
        return False
    try:
        return as_text(value) in codes_text or _code_text(value) in codes_text
    except (TypeError, ValueError):
        return False


def missing_items(codes) -> list:
    """User-missing codes in one form: a code as text (``-9``, ``DK``) or a
    range ``{"lo": -9.0, "hi": -1.0}``. Accepts numbers, texts, ``("range",
    lo, hi)`` and ``{"lo", "hi"}``."""
    items: list = []
    for code in codes or ():
        if isinstance(code, dict) and {"lo", "hi"} <= set(code):
            item = {"lo": float(code["lo"]), "hi": float(code["hi"])}
        elif isinstance(code, (list, tuple)) and len(code) == 3 and code[0] == "range":
            item = {"lo": float(code[1]), "hi": float(code[2])}
        elif isinstance(code, (str, int, float, np.number)) and not isinstance(code, bool):
            item = _code_text(code) if not isinstance(code, str) else code
        else:
            continue
        if item not in items:
            items.append(item)
    return items


def missing_text(item) -> str:
    if isinstance(item, dict):
        return f"{number_text(item['lo'])} thru {number_text(item['hi'])}"
    return _code_text(item)


def _is_user_missing(value, discrete: set[str], ranges: list[tuple[float, float]]) -> bool:
    if is_missing(value):
        return False
    if discrete and _matches_code(value, discrete):
        return True
    if ranges and isinstance(value, (int, float, np.integer, np.floating)) \
            and not isinstance(value, (bool, np.bool_)):
        return any(low <= float(value) <= high for low, high in ranges)
    return False


def _describe_valid(entry: VariableEntry, values: pd.Series) -> str:
    """The valid codes or the observed range, without listing what could
    identify a participant (no text of an identifier or of free text)."""
    if entry.kind == "category":
        return "; ".join(str(c) for c in entry.categories)
    if entry.kind in ("number", "boolean"):
        if entry.value_labels:
            missing = {_code_text(m) for m in entry.missing_codes if not isinstance(m, dict)}
            codes = [c for c in entry.value_labels if c not in missing]
            return "; ".join(codes)
        if entry.minimum is None:
            return ""
        whole = entry.minimum == int(entry.minimum) and entry.maximum == int(entry.maximum)
        clean = pd.to_numeric(values, errors="coerce").dropna()
        if entry.level in ("nominal", "ordinal") and whole and 0 < entry.n_distinct <= 12:
            return "; ".join(number_text(v) for v in sorted(clean.unique()))
        return f"{number_text(entry.minimum)} – {number_text(entry.maximum)}"
    if entry.kind in ("datetime", "date"):
        clean = [v for v in values if not is_missing(v)]
        try:
            return f"{as_text(min(clean))} – {as_text(max(clean))}" if clean else ""
        except TypeError:
            return ""
    if entry.kind == "text" and entry.level in ("nominal", "ordinal") and entry.n_distinct <= 20:
        shown = sorted({v for v in values if isinstance(v, str)})
        return "; ".join(shown)
    if entry.n_distinct:
        return f"{entry.n_distinct} distinct values"
    return ""


def _question_value_labels(question: dict) -> dict[str, str]:
    labels = {str(k): str(v) for k, v in (question.get("value_labels") or {}).items()}
    kind = str(question.get("kind", ""))
    if not labels and kind in ("likert5", "likert7"):
        top = int(kind[-1])
        if question.get("min_label"):
            labels["1"] = str(question["min_label"])
        if question.get("max_label"):
            labels[str(top)] = str(question["max_label"])
    if kind == "consent":
        labels.setdefault("1", "Consent given")
    return dict(sorted(labels.items(), key=lambda item: _sort_key(item[0])))


def _sort_key(code: str):
    try:
        return (0, float(code), "")
    except ValueError:
        return (1, 0.0, code)


def _describe_step(kind: str, params: dict) -> str:
    """One line for a derived variable's rule (English; the codebook keeps the
    parameters themselves too)."""
    source = params.get("source", "")
    if kind == "mark_missing":
        return f"copy of {source}; codes {', '.join(map(str, params.get('codes', [])))} set to missing"
    if kind == "recode_column":
        pairs = ", ".join(f"{a} → {b}" for a, b in (params.get("mapping") or {}).items())
        return f"recode of {source}: {pairs}; other values: {params.get('unmapped', 'keep')}"
    if kind == "reverse_item":
        low, high = params.get("minimum"), params.get("maximum")
        return f"reverse-keyed {source}: {number_text(low)} + {number_text(high)} − {source}"
    if kind == "score_scale":
        items = list(params.get("sources") or [])
        return (f"{params.get('method', '')} of {len(items)} items ({', '.join(items)}); "
                f"at least {params.get('min_answered', '')} answered")
    if kind == "scale_groups":
        rule = params.get("rule") or {}
        groups = "; ".join(str(g.get("label", "")) for g in params.get("groups") or [])
        return f"groups of {source} ({rule.get('method', '')}): {groups}"
    shown = ", ".join(f"{k}={v}" for k, v in params.items() if k not in ("target",))
    return f"{kind}: {shown}"


def build_codebook(df: pd.DataFrame, name: str, *, levels: dict | None = None,
                   metadata: dict | None = None,
                   questionnaires: Iterable[dict] = (), history: Iterable[dict] = (),
                   sha256: str = "", created: str = "", app_version: str = "") -> Codebook:
    """The codebook of ``df``: every variable with its level, labels, codes,
    missing values, scales, reverse keying and derivation.

    ``levels``: {variable: (confirmed level, where confirmed, suggested)}.
    ``metadata``: what the data documents ({variable: {"label",
    "value_labels", "missing_codes", "source"}}, from a .sav file or an
    exported codebook); it comes first, and a questionnaire only fills gaps.
    ``questionnaires``: {"title", "questions"} of the questionnaires whose
    question keys are column names (the dataset's own first).
    ``history``: the derived-variable records, oldest first ({"kind",
    "params", "output_columns", "created_at"?, "dataset"?}).
    """
    levels = levels or {}
    history = [dict(step) for step in history]
    questionnaires = list(questionnaires)
    names = [str(c) for c in df.columns]
    spss = spss_names(names)
    entries: list[VariableEntry] = []
    questions: dict[str, tuple[dict, str]] = {}
    reasons: dict[str, tuple[dict, str]] = {}
    for book in questionnaires:
        for question in book.get("questions") or ():
            key = str(question.get("key", ""))
            questions.setdefault(key, (question, str(book.get("title", ""))))
            if question.get("missing_options"):
                reasons.setdefault(key + "__missing_reason", (question, str(book.get("title", ""))))
    for position, column in enumerate(df.columns):
        values = df[column]
        kind = column_kind(values)
        level, where, suggested = (tuple(levels.get(str(column), ())) + ("unknown", "", ""))[:3]
        entry = VariableEntry(name=str(column), position=position + 1, kind=kind,
                              dtype=str(values.dtype), level=level or "unknown",
                              confirmed_in=where or "", suggested=suggested or "",
                              spss_name=spss[str(column)])
        if kind == "category":
            entry.categories = [as_text(c) for c in values.cat.categories]
            entry.ordered = bool(values.cat.ordered)
        documented = (metadata or {}).get(entry.name) or {}
        where_from = METADATA_SOURCES.get(str(documented.get("source") or ""),
                                          str(documented.get("source") or "the data file"))
        if documented.get("label"):
            entry.label, entry.label_source = str(documented["label"]), where_from
        if documented.get("value_labels"):
            entry.value_labels = dict(sorted(
                ((str(k), str(v)) for k, v in documented["value_labels"].items()),
                key=lambda item: _sort_key(item[0])))
        if documented.get("missing_codes"):
            entry.missing_codes = missing_items(documented["missing_codes"])
            entry.missing_source = where_from
        found = questions.get(entry.name)
        if found is not None:
            question, title = found
            if not entry.label:
                entry.label = str(question.get("prompt", ""))
                entry.label_source = f"questionnaire: {title}"
            if not entry.value_labels:
                entry.value_labels = _question_value_labels(question)
            if question.get("reverse_scored"):
                entry.reverse = True
                entry.reverse_note = ("reverse-keyed in the questionnaire; raw responses are "
                                      "not reversed")
            if question.get("scale_id"):
                entry.scales.append(str(question["scale_id"]))
            if question.get("missing_options"):
                entry.notes.append(f"don't-know / prefer-not answers are missing here; the "
                                   f"reason is in {entry.name}__missing_reason")
        reason = reasons.get(entry.name)
        if reason is not None:
            question, title = reason
            options = {str(k): str(v) for k, v in (question.get("missing_options") or {}).items()}
            if not entry.label:
                entry.label = f"Missing reason: {question.get('key', '')}"
                entry.label_source = f"questionnaire: {title}"
            entry.value_labels = {**options, **entry.value_labels}
            if not entry.missing_codes:
                entry.missing_codes = list(options)
                entry.missing_source = "questionnaire missing options"
        entries.append(entry)
    by_name = {e.name: e for e in entries}
    scales: list[dict] = []
    # The questionnaire's scales: items grouped by scale id.
    for book in questionnaires:
        groups: dict[str, list[dict]] = {}
        for question in book.get("questions") or ():
            if question.get("scale_id") and str(question.get("key")) in by_name:
                groups.setdefault(str(question["scale_id"]), []).append(question)
        for scale_id, items in groups.items():
            scales.append({"scale": scale_id, "kind": "questionnaire scale",
                           "items": [str(q["key"]) for q in items],
                           "reverse_items": [str(q["key"]) for q in items
                                             if q.get("reverse_scored")],
                           "rule": "items of one scale in the questionnaire; the program does "
                                   "not compute a score from them",
                           "source": f"questionnaire: {book.get('title', '')}"})
    for number, step in enumerate(history, start=1):
        kind = str(step.get("kind", ""))
        params = dict(step.get("params") or {})
        outputs = [str(c) for c in step.get("output_columns") or ()]
        step.setdefault("step", number)
        line = _describe_step(kind, params)
        for output in outputs:
            entry = by_name.get(output)
            if entry is None:
                continue
            entry.derived = line
            if kind == "reverse_item":
                entry.reverse = True
                entry.reverse_note = line
        source = by_name.get(str(params.get("source", "")))
        if kind == "mark_missing" and source is not None:
            for code in missing_items(params.get("codes") or ()):
                if code not in source.missing_codes:
                    source.missing_codes.append(code)
            source.missing_source = (f"data preparation: {', '.join(outputs)} sets these codes "
                                     f"to missing")
        if kind == "score_scale":
            items = [str(s) for s in params.get("sources") or ()]
            scales.append({"scale": outputs[0] if outputs else "", "kind": "score",
                           "items": items,
                           "reverse_items": [i for i in items if by_name.get(i) is not None
                                             and by_name[i].reverse],
                           "rule": f"{params.get('method', '')}; at least "
                                   f"{params.get('min_answered', '')} of {len(items)} answered",
                           "source": f"data preparation, step {number}"})
            for item in items:
                if item in by_name and (outputs[0] if outputs else "") not in by_name[item].scales:
                    by_name[item].scales.append(outputs[0] if outputs else "")
        if kind == "scale_groups":
            rule = params.get("rule") or {}
            scales.append({"scale": outputs[0] if outputs else "", "kind": "groups from a scale",
                           "items": [str(params.get("source", ""))], "reverse_items": [],
                           "rule": f"{rule.get('method', '')}: " + "; ".join(
                               f"{g.get('label', '')} [{_bound(g)}]"
                               for g in params.get("groups") or []),
                           "source": str(params.get("statement", ""))})
    for entry in entries:
        _count(entry, df[entry.name])
    return Codebook(dataset=name, rows=int(len(df)), columns=int(df.shape[1]), sha256=sha256,
                    variables=entries, scales=scales, history=_json_safe(history),
                    questionnaires=[str(b.get("title", "")) for b in questionnaires],
                    created=created, app_version=app_version)


def _bound(group: dict) -> str:
    low, high = group.get("lower"), group.get("upper")
    left = "[" if group.get("lower_inclusive", True) else "("
    right = "]" if group.get("upper_inclusive", True) else ")"
    show = (lambda v: "" if v is None else number_text(v))  # noqa: E731
    return f"{left}{show(low)}, {show(high)}{right}"


def _count(entry: VariableEntry, values: pd.Series) -> None:
    missing = values.isna()
    entry.n_missing = int(missing.sum())
    present = values[~missing]
    entry.n_empty_text = int(sum(1 for v in present if isinstance(v, str) and v == ""))
    discrete = {_code_text(c) for c in entry.missing_codes if not isinstance(c, dict)}
    ranges = [(c["lo"], c["hi"]) for c in entry.missing_codes if isinstance(c, dict)]
    user = (present.astype(object).map(
        lambda v: _is_user_missing(v, discrete, ranges)).astype(bool)
        if entry.missing_codes else None)
    entry.n_user_missing = int(user.sum()) if user is not None else 0
    valid = present[~user] if user is not None else present
    entry.n_valid = int(len(valid)) - entry.n_empty_text
    try:
        entry.n_distinct = int(valid.nunique())
    except TypeError:
        entry.n_distinct = int(len({as_text(v) for v in valid}))
    if entry.kind in ("number", "boolean"):
        numbers = pd.to_numeric(valid, errors="coerce").dropna()
        numbers = numbers[np.isfinite(numbers.astype(float))]
        if not numbers.empty:
            entry.minimum, entry.maximum = float(numbers.min()), float(numbers.max())
    entry.valid = _describe_valid(entry, valid)


# ================================================================ SPSS names
def _sav_char(ch: str, first: bool) -> bool:
    if ch.isascii():
        if first:
            return ch.isalpha()
        return ch.isalnum() or ch in "_.@#$"
    # Unicode letters and digits are valid in SPSS's Unicode mode; ReadStat
    # accepts any non-ASCII character in a UTF-8 file.
    return ch.isalpha() if first else (ch.isalnum() or unicodedata.category(ch) in ("Mn", "Mc"))


def valid_sav_name(name: str) -> bool:
    if not name or len(name.encode("utf-8")) > SAV_NAME_BYTES:
        return False
    if name.upper() in SAV_RESERVED or name.endswith("."):
        return False
    return _sav_char(name[0], True) and all(_sav_char(c, False) for c in name[1:])


def _sav_candidate(name: str, position: int) -> str:
    text = unicodedata.normalize("NFC", str(name)).strip()
    out, replaced = [], False
    for ch in text:
        if _sav_char(ch, False):
            out.append(ch)
            replaced = False
        elif not replaced:          # a run of characters SPSS refuses becomes one "_"
            out.append("_")
            replaced = True
    candidate = "".join(out).strip("_")
    if not candidate:
        return f"VAR{position:05d}"
    if not _sav_char(candidate[0], True) or candidate.upper() in SAV_RESERVED:
        candidate = "V_" + candidate
    candidate = utf8_cut(candidate, SAV_NAME_BYTES).rstrip("._")
    return candidate or f"VAR{position:05d}"


def spss_names(columns: Iterable[str]) -> dict[str, str]:
    """{column: SPSS name}, one per column and unique without regard to case
    (SPSS compares names case-insensitively). A name that is already valid
    is kept; the others become valid with as few changes as possible:
    characters SPSS refuses become ``_``, a name that does not start with a
    letter or is a reserved word gets ``V_`` in front, a name longer than 64
    UTF-8 bytes is cut, and a clash gets ``_2``, ``_3`` …"""
    columns = [str(c) for c in columns]
    result: dict[str, str] = {}
    taken: set[str] = set()
    for column in columns:          # valid names first: they keep their names
        if valid_sav_name(column) and column.casefold() not in taken:
            result[column] = column
            taken.add(column.casefold())
    for position, column in enumerate(columns, start=1):
        if column in result:
            continue
        base = _sav_candidate(column, position)
        candidate, number = base, 1
        while candidate.casefold() in taken or not valid_sav_name(candidate):
            number += 1
            suffix = f"_{number}"
            candidate = utf8_cut(base, SAV_NAME_BYTES - len(suffix)).rstrip(".") + suffix
        result[column] = candidate
        taken.add(candidate.casefold())
    return result


def restore_names(frame: pd.DataFrame, names: dict[str, str]) -> pd.DataFrame:
    """Undo :func:`spss_names`: ``names`` is {original: SPSS name}."""
    back = {spss: original for original, spss in names.items()}
    return frame.rename(columns=lambda c: back.get(str(c), c))


# ===================================================================== .sav
@dataclass
class SavColumn:
    original: str
    name: str
    kind: str
    label: str
    value_labels: dict
    missing: list
    measure: str
    fmt: str | None


@dataclass
class SavPlan:
    """What a .sav export will hold: every renamed variable, and every field
    that is cut or converted (shown to the researcher before saving)."""

    columns: list[SavColumn]
    renamed: dict[str, str]                   # original -> SPSS name
    changes: list[tuple[str, str, dict]]      # (variable or "", message key, values)
    file_label: str = ""


def _numeric_codes(codes) -> list[float]:
    found = []
    for code in codes:
        try:
            number = float(code)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number not in found:
            found.append(number)
    return found


def _sav_missing(entry: VariableEntry, kind: str, values: pd.Series,
                 lossy: list) -> list:
    """The user-missing values of one .sav variable, within the format's
    limits: at most three codes, or one range and one code. A text column
    that has missing values also gets the empty text as a missing value:
    SPSS has no missing value for texts, so a missing text is written as an
    empty one, and declaring it keeps it missing."""
    codes = list(entry.missing_codes)
    text_like = kind in ("text", "mixed", "duration")
    if text_like and entry.n_missing and "" not in codes:
        codes.append("")
    if not codes:
        return []
    if kind in ("number", "boolean", "empty"):
        ranges = [c for c in codes if isinstance(c, dict)]
        discrete = [c for c in codes if not isinstance(c, dict)]
        numbers = sorted(_numeric_codes(discrete))
        if len(numbers) != len(discrete):
            lossy.append((entry.name, "export.change.missing_not_numeric",
                          {"codes": ", ".join(map(str, discrete))}))
        if ranges:
            dropped = [missing_text(r) for r in ranges[1:]] + \
                [number_text(n) for n in numbers[1:]]
            if dropped:
                lossy.append((entry.name, "export.change.missing_limit",
                              {"codes": ", ".join(dropped)}))
            return [{"lo": ranges[0]["lo"], "hi": ranges[0]["hi"]}, *numbers[:1]]
        if len(numbers) <= SAV_MISSING_DISCRETE:
            return numbers
        observed = pd.to_numeric(values, errors="coerce").dropna()
        valid = observed[~observed.isin(numbers)]
        # One range (and one more discrete code) when no valid value falls in it.
        for keep in (numbers, numbers[:-1], numbers[1:]):
            low, high = keep[0], keep[-1]
            inside = valid[(valid >= low) & (valid <= high)]
            rest = [n for n in numbers if n not in keep]
            if inside.empty and len(rest) <= 1:
                return [{"lo": low, "hi": high}, *rest]
        lossy.append((entry.name, "export.change.missing_limit",
                      {"codes": ", ".join(number_text(n) for n in numbers[SAV_MISSING_DISCRETE:])}))
        return numbers[:SAV_MISSING_DISCRETE]
    if text_like:
        texts = [str(c) for c in codes if not isinstance(c, dict)]
        fit = [t for t in texts if len(t.encode("utf-8")) <= SAV_MISSING_STRING_BYTES]
        dropped = [t for t in texts if t not in fit] + fit[SAV_MISSING_DISCRETE:]
        if dropped:
            lossy.append((entry.name, "export.change.missing_limit",
                          {"codes": ", ".join(dropped)}))
        return fit[:SAV_MISSING_DISCRETE]
    lossy.append((entry.name, "export.change.missing_kind",
                  {"codes": ", ".join(missing_text(c) for c in codes)}))
    return []


def _sav_format(values: pd.Series) -> str:
    numbers = pd.to_numeric(values, errors="coerce").dropna()
    numbers = numbers[np.isfinite(numbers.astype(float))]
    if numbers.empty:
        return "F8.2"
    decimals = 0
    for number in numbers.unique()[:5000]:
        text = repr(float(number))
        if "e" in text or "E" in text:
            decimals = max(decimals, 16)
        elif "." in text and not float(number).is_integer():
            decimals = max(decimals, len(text.split(".")[1]))
    decimals = min(decimals, 16)
    digits = max(len(str(int(abs(n)))) for n in (numbers.min(), numbers.max()))
    width = min(40, max(8, digits + decimals + (2 if decimals else 1)))
    return f"F{width}.{decimals}"


def plan_sav(df: pd.DataFrame, codebook: Codebook) -> SavPlan:
    """Names, labels, codes and formats of the .sav file, and what is lost."""
    columns: list[SavColumn] = []
    lossy: list[tuple[str, str, dict]] = []
    for column in df.columns:
        entry = codebook.variable(str(column))
        if entry is None:
            raise ExportError(f"{column} is not in the codebook")
        values = df[column]
        kind = entry.kind
        codes = list(entry.value_labels) + [c for c in entry.missing_codes
                                            if not isinstance(c, dict)]
        if kind == "empty" and codes and len(_numeric_codes(codes)) < len(codes):
            kind = "text"           # an empty column of text codes (a missing-reason column)
        if entry.level == "id" and kind in ("number", "boolean", "empty"):
            kind = "text"           # an identifier is a string variable, never a number
            lossy.append((entry.name, "export.change.id_text", {}))
        label = entry.label or (entry.name if entry.spss_name != entry.name else "")
        if len(label.encode("utf-8")) > SAV_LABEL_BYTES:
            lossy.append((entry.name, "export.change.label_cut", {"limit": SAV_LABEL_BYTES}))
            label = utf8_cut(label, SAV_LABEL_BYTES)
        measure = SAV_MEASURE.get(entry.level, "unknown")
        value_labels: dict = {}
        if kind == "category":
            value_labels = {float(i): c for i, c in enumerate(entry.categories, start=1)}
            if entry.level == "unknown":
                measure = "ordinal" if entry.ordered else "nominal"
            lossy.append((entry.name, "export.change.category_codes",
                          {"count": len(entry.categories)}))
        elif kind == "boolean":
            value_labels = {0.0: "False", 1.0: "True"}
        elif entry.value_labels:
            if kind in ("number", "empty"):
                for code, text in entry.value_labels.items():
                    numbers = _numeric_codes([code])
                    if numbers:
                        value_labels[numbers[0]] = text
                    else:
                        lossy.append((entry.name, "export.change.value_label_code",
                                      {"code": code}))
            else:
                value_labels = {str(code): text for code, text in entry.value_labels.items()}
        for code, text in list(value_labels.items()):
            if len(str(text).encode("utf-8")) > SAV_VALUE_LABEL_BYTES:
                value_labels[code] = utf8_cut(str(text), SAV_VALUE_LABEL_BYTES)
                lossy.append((entry.name, "export.change.value_label_cut",
                              {"code": _code_text(code), "limit": SAV_VALUE_LABEL_BYTES}))
        missing = _sav_missing(entry, kind, values, lossy)
        text_like = kind in ("text", "mixed", "duration")
        if kind == "datetime_tz":
            lossy.append((entry.name, "export.change.timezone", {}))
        if kind == "mixed":
            lossy.append((entry.name, "export.change.mixed_text", {}))
        if text_like and entry.n_missing and entry.n_empty_text:
            lossy.append((entry.name, "export.change.text_missing",
                          {"missing": entry.n_missing, "empty": entry.n_empty_text}))
        if text_like and measure == "scale":
            measure = "nominal"
            lossy.append((entry.name, "export.change.text_scale", {}))
        if kind == "number":
            big = pd.to_numeric(values, errors="coerce").abs() > _EXACT_INTEGER
            if bool(big.fillna(False).any()) and pd.api.types.is_integer_dtype(values.dtype):
                lossy.append((entry.name, "export.change.big_integer", {}))
        fmt = _sav_format(values) if kind == "number" else None
        columns.append(SavColumn(entry.name, entry.spss_name, kind, label, value_labels, missing,
                                 measure, fmt))
    renamed = {c.original: c.name for c in columns if c.original != c.name}
    file_label = utf8_cut(codebook.dataset, SAV_FILE_LABEL_BYTES)
    if file_label != codebook.dataset:
        lossy.append(("", "export.change.file_label_cut", {"limit": SAV_FILE_LABEL_BYTES}))
    return SavPlan(columns, renamed, lossy, file_label)


def _sav_values(values: pd.Series, column: SavColumn) -> pd.Series:
    kind = column.kind
    if kind == "category":
        codes = values.cat.codes.astype("float64")
        return codes.where(codes >= 0, np.nan) + 1.0
    if kind == "boolean":
        return values.map(lambda v: np.nan if is_missing(v) else (1.0 if v else 0.0)).astype(
            "float64")
    if kind == "number":
        if pd.api.types.is_numeric_dtype(values.dtype):
            return pd.to_numeric(values, errors="coerce").astype("float64")
        return values.map(lambda v: np.nan if is_missing(v) else float(v)).astype("float64")
    if kind == "empty":
        return pd.Series(np.nan, index=values.index, dtype="float64")
    if kind == "datetime":
        if pd.api.types.is_datetime64_any_dtype(values.dtype):
            return values
        return pd.to_datetime(values.map(lambda v: None if is_missing(v) else pd.Timestamp(v)))
    if kind == "datetime_tz":
        return values.dt.tz_convert("UTC").dt.tz_localize(None)
    if kind in ("date", "time"):
        return values.map(lambda v: None if is_missing(v) else v).astype(object)
    return values.map(lambda v: "" if is_missing(v) else as_text(v)).astype(object)


def sav_notes(codebook: Codebook, plan: SavPlan, exported: str) -> list[str]:
    notes = [f"Statistical Research Assistant export, {exported}",
             utf8_cut(f"Dataset: {codebook.dataset}", SAV_NOTE_BYTES),
             f"Rows: {codebook.rows}; variables: {codebook.columns}"]
    if codebook.sha256:
        notes.append(f"Data SHA-256: {codebook.sha256}")
    notes += ["Not in this file: audit trail, derived-variable history,",
              "analysis provenance. They are in the codebook and the bundle."]
    for original, name in plan.renamed.items():
        notes.extend(rename_note(name, original))
    return notes


def rename_note(name: str, original: str) -> list[str]:
    """Note lines that give a renamed variable's original name back
    (data_loader.sav_renames reads them): ``Renamed: NAME = original`` when it
    fits in one 80-byte line, otherwise ``Renamed: NAME =`` followed by
    ``+ `` lines that hold the original name in pieces. No piece ends with a
    space (the file pads lines with spaces)."""
    line = f"Renamed: {name} = {original}"
    if len(line.encode("utf-8")) <= SAV_NOTE_BYTES and "\n" not in original \
            and not original.endswith(" "):
        return [line]
    lines, rest = [f"Renamed: {name} ="], original
    room = SAV_NOTE_BYTES - 2
    while rest:
        piece = utf8_cut(rest, room)
        while len(piece) > 1 and piece.endswith(" "):
            piece = piece[:-1]
        lines.append("+ " + piece)
        rest = rest[len(piece):]
    return lines


def write_sav(path: Path, df: pd.DataFrame, codebook: Codebook, *,
              plan: SavPlan | None = None, exported: str = "") -> dict:
    """Write ``df`` as SPSS ``.sav`` (pyreadstat); returns the facts written."""
    import pyreadstat

    plan = plan or plan_sav(df, codebook)
    frame = pd.DataFrame({c.name: _sav_values(df[c.original], c) for c in plan.columns},
                         index=df.index).reset_index(drop=True)
    labels = {c.name: (c.label or None) for c in plan.columns}
    value_labels = {c.name: c.value_labels for c in plan.columns if c.value_labels}
    missing = {c.name: c.missing for c in plan.columns if c.missing}
    measure = {c.name: c.measure for c in plan.columns}
    formats = {c.name: c.fmt for c in plan.columns if c.fmt}
    pyreadstat.write_sav(frame, str(path), file_label=plan.file_label,
                         column_labels=labels, variable_value_labels=value_labels or None,
                         missing_ranges=missing or None, variable_measure=measure,
                         variable_format=formats or None,
                         note=sav_notes(codebook, plan, exported or _today()))
    return {"rows": int(len(frame)), "columns": int(frame.shape[1]),
            "names": [c.name for c in plan.columns]}


def _today() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


# ===================================================================== .csv
class _CommaNumber(float):
    """A number the csv module writes unquoted, with a decimal comma."""

    def __repr__(self) -> str:
        return number_text(float(self)).replace(".", ",")

    __str__ = __repr__


def csv_cell(value, decimal: str = "dot"):
    """What the CSV writer gets for one value: None (missing), a number
    (unquoted) or a protected text (quoted)."""
    if is_missing(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating, Decimal)):
        number = plain_number(value)
        if decimal == "comma" and isinstance(number, float):
            return _CommaNumber(number)
        return number
    return csv_safety.protect(as_text(value))


class _Counter:
    def __init__(self):
        self.protected = 0


def write_csv(path: Path, df: pd.DataFrame, *, bom: bool = True, layout: str = "comma",
              progress: Progress | None = None) -> dict:
    """Write ``df`` as UTF-8 CSV; returns the facts written (cells protected).
    ``layout``: "comma" (``,`` and a decimal point) or "semicolon" (``;`` and
    a decimal comma)."""
    if layout not in CSV_LAYOUTS:
        raise ExportError(f"Unknown CSV layout: {layout}")
    delimiter, decimal = CSV_LAYOUTS[layout]
    counter = _Counter()
    columns = [df[c].tolist() for c in df.columns]
    total = len(df)

    def protected(value):
        cell = csv_cell(value, decimal)
        if isinstance(cell, str) and cell != as_text(value):
            counter.protected += 1
        return cell

    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=delimiter, quoting=csv.QUOTE_STRINGS,
                            lineterminator="\r\n")
        writer.writerow([protected(str(c)) for c in df.columns])
        for index, row in enumerate(zip(*columns), start=1):
            writer.writerow([protected(v) for v in row])
            if progress is not None and index % PROGRESS_EVERY == 0:
                progress(index, total)
        if not len(df.columns):
            pass
    if progress is not None:
        progress(total, total)
    return {"rows": total, "columns": int(df.shape[1]), "protected": counter.protected,
            "bom": bool(bom), "delimiter": delimiter, "decimal": decimal}


def read_exported_csv(path: Path, codebook: Codebook | dict | None = None) -> pd.DataFrame:
    """The program's own reading of a CSV it exported (for tests and the
    bundle): text cells restored, text columns read as text."""
    book = codebook.to_dict() if isinstance(codebook, Codebook) else (codebook or {})
    text_columns = [v["name"] for v in book.get("variables", [])
                    if v.get("kind") in ("text", "mixed", "category")]
    info = book.get("data_file") or {}
    frame = pd.read_csv(path, encoding="utf-8-sig", sep=info.get("delimiter", ","),
                        decimal="," if info.get("decimal") == "comma" else ".",
                        dtype={csv_safety.protect(c): str for c in text_columns},
                        keep_default_na=False, na_values=[""])
    frame.columns = [csv_safety.restore(str(c)) for c in frame.columns]
    for column in frame.columns:
        if column in text_columns:
            frame[column] = frame[column].map(
                lambda v: v if is_missing(v) else csv_safety.restore(str(v)))
    return frame


# ==================================================================== .xlsx
@dataclass
class Sheet:
    """A worksheet of rows. A cell is a value (written by type) or a
    ``(value, "text")`` pair to force text."""

    title: str
    rows: list
    widths: dict = field(default_factory=dict)
    freeze: str | None = "A2"


def xlsx_text(value: str) -> str:
    """A text as a worksheet cell holds it: characters XML cannot carry
    replaced by U+FFFD, at most 32,767 characters."""
    return _ILLEGAL_XML.sub("\ufffd", value)[:XLSX_MAX_TEXT]


class _CellWriter:
    """Typed, formula-proof cells for openpyxl's write-only mode."""

    def __init__(self, ws):
        from openpyxl.cell import WriteOnlyCell

        self.ws, self.Cell = ws, WriteOnlyCell
        self.cleaned = self.cut = self.text_numbers = 0

    def text(self, value: str):
        if _ILLEGAL_XML.search(value):
            value = _ILLEGAL_XML.sub("�", value)
            self.cleaned += 1
        if len(value) > XLSX_MAX_TEXT:
            value = value[:XLSX_MAX_TEXT]
            self.cut += 1
        cell = self.Cell(self.ws, value=value)
        cell.data_type = "s"          # never a formula, whatever the text begins with
        return cell

    def __call__(self, value):
        if isinstance(value, tuple) and len(value) == 2 and value[1] == "text":
            return self.text(as_text(value[0]))
        if is_missing(value):
            return None
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)):
            number = int(value)
            if abs(number) > _EXACT_INTEGER:
                self.text_numbers += 1
                return self.text(str(number))     # a spreadsheet number would round it
            return number
        if isinstance(value, (float, np.floating, Decimal)):
            number = float(value)
            if math.isinf(number):
                self.text_numbers += 1
                return self.text(number_text(number))
            return plain_number(number)
        if isinstance(value, (pd.Timestamp, dt.datetime)):
            stamp = pd.Timestamp(value)
            if stamp.tzinfo is not None:
                return self.text(stamp.isoformat())   # spreadsheets have no time zones
            return stamp.to_pydatetime()
        if isinstance(value, np.datetime64):
            return pd.Timestamp(value).to_pydatetime()
        if isinstance(value, dt.time) and value.tzinfo is not None:
            return self.text(value.isoformat())
        if isinstance(value, (dt.date, dt.time)):
            return value
        return self.text(as_text(value))


def _sheet_title(title: str, used: set[str]) -> str:
    clean = re.sub(r"[\[\]:*?/\\]", "_", title).strip("'") or "Sheet"
    clean = clean[:31]
    candidate, number = clean, 1
    while candidate.casefold() in used:
        number += 1
        suffix = f" ({number})"
        candidate = clean[:31 - len(suffix)] + suffix
    used.add(candidate.casefold())
    return candidate


def _float_cells(series: pd.Series) -> list | None:
    """A float column as worksheet values in one pass (None, int or float),
    or None when it holds an infinity (those need text cells)."""
    values = series.to_numpy(dtype=float)
    if np.isinf(values).any():
        return None
    out: list = []
    append = out.append
    for number in values.tolist():
        if number != number:
            append(None)
        elif number.is_integer() and -_EXACT_INTEGER < number < _EXACT_INTEGER and \
                not (number == 0 and math.copysign(1.0, number) < 0):
            append(int(number))
        else:
            append(number)
    return out


def _data_columns(df: pd.DataFrame) -> list[tuple[bool, list]]:
    """Per column: (ready, values). A ready column's values go into the
    worksheet as they are (numbers and empty cells: never a formula); the
    others pass through :class:`_CellWriter` cell by cell."""
    columns = []
    for name in df.columns:
        series = df[name]
        kind = column_kind(series)
        if kind == "number" and pd.api.types.is_float_dtype(series.dtype):
            ready = _float_cells(series)
            if ready is not None:
                columns.append((True, ready))
                continue
        if kind in ("category", "duration"):
            columns.append((False, [None if is_missing(v) else (as_text(v), "text")
                                    for v in series]))
        else:
            columns.append((False, series.tolist()))
    return columns


def write_xlsx(path: Path, sheets: list[Sheet], *, data: pd.DataFrame | None = None,
               data_title: str = "Data", progress: Progress | None = None) -> dict:
    """A workbook of ``sheets`` (in order); ``data`` (if given) is written
    first as the sheet ``data_title``, streamed row by row."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    if data is not None and len(data) + 1 > XLSX_MAX_ROWS:
        raise ExportError(f"{len(data)} rows do not fit in one worksheet "
                          f"({XLSX_MAX_ROWS - 1:,} at most)")
    workbook = Workbook(write_only=True)
    used: set[str] = set()
    facts = {"sheets": [], "rows": None, "columns": None, "cleaned": 0, "cut": 0,
             "text_numbers": 0}
    writers = []
    if data is not None:
        ws = workbook.create_sheet(_sheet_title(data_title, used))
        ws.freeze_panes = "A2"
        cells = _CellWriter(ws)
        writers.append(cells)
        for index, name in enumerate(data.columns, start=1):
            ws.column_dimensions[get_column_letter(index)].width = min(
                40, max(10, len(str(name)) + 2))
        ws.append([cells.text(str(c)) for c in data.columns])
        total = len(data)
        columns = _data_columns(data)
        for index in range(total):
            ws.append([values[index] if ready else cells(values[index])
                       for ready, values in columns])
            if progress is not None and (index + 1) % PROGRESS_EVERY == 0:
                progress(index + 1, total)
        if progress is not None:
            progress(total, total)
        facts.update(rows=total, columns=int(data.shape[1]))
        facts["sheets"].append(ws.title)
    for sheet in sheets:
        ws = workbook.create_sheet(_sheet_title(sheet.title, used))
        if sheet.freeze:
            ws.freeze_panes = sheet.freeze
        for column, width in sheet.widths.items():
            ws.column_dimensions[column].width = width
        cells = _CellWriter(ws)
        writers.append(cells)
        for row in sheet.rows:
            ws.append([cells(v) for v in row])
        facts["sheets"].append(ws.title)
    if not facts["sheets"]:
        raise ExportError("Choose at least one part of the workbook.")
    workbook.save(str(path))
    for cells in writers:
        facts["cleaned"] += cells.cleaned
        facts["cut"] += cells.cut
        facts["text_numbers"] += cells.text_numbers
    return facts


# ----------------------------------------------------- codebook as sheets
CODEBOOK_COLUMNS = ("Variable", "SPSS name", "Label", "Label source", "Measurement level",
                    "Confirmed in", "Suggested level", "Storage", "Value labels",
                    "Missing codes (user-missing)", "Missing codes defined by",
                    "Valid values", "Valid", "Missing (empty)", "User-missing", "Empty text",
                    "Distinct", "Reverse-keyed", "Scales", "Derived by", "Notes")
HISTORY_COLUMNS = ("Step", "Kind", "Output variables", "Inputs", "Parameters (JSON)",
                   "Recorded", "Dataset")
SCALE_COLUMNS = ("Scale", "Kind", "Items", "Reverse-keyed items", "Scoring rule", "Defined by")


def _labels_text(labels: dict) -> str:
    return "; ".join(f"{code} = {label}" for code, label in labels.items())


def codebook_sheet(codebook: Codebook) -> Sheet:
    rows: list = [[(c, "text") for c in CODEBOOK_COLUMNS]]
    for v in codebook.variables:
        rows.append([
            (v.name, "text"), (v.spss_name, "text"), (v.label, "text"),
            (v.label_source, "text"), (v.level, "text"), (v.confirmed_in, "text"),
            (v.suggested, "text"), (f"{v.kind} ({v.dtype})", "text"),
            (_labels_text(v.value_labels), "text"),
            ("; ".join(missing_text(c) for c in v.missing_codes), "text"),
            (v.missing_source, "text"), (v.valid, "text"), v.n_valid, v.n_missing,
            v.n_user_missing, v.n_empty_text, v.n_distinct,
            ("yes" if v.reverse else "", "text"), ("; ".join(v.scales), "text"),
            (v.derived or v.reverse_note, "text"), ("; ".join(v.notes), "text"),
        ])
    rows.append([])
    rows.append([("Derived-variable history (oldest first)", "text")])
    rows.append([(c, "text") for c in HISTORY_COLUMNS])
    for number, step in enumerate(codebook.history, start=1):
        params = step.get("params") or {}
        inputs = params.get("sources") or ([params["source"]] if params.get("source") else [])
        rows.append([step.get("step", number), (str(step.get("kind", "")), "text"),
                     (", ".join(map(str, step.get("output_columns") or [])), "text"),
                     (", ".join(map(str, inputs)), "text"),
                     (json.dumps(params, ensure_ascii=False, sort_keys=True), "text"),
                     (str(step.get("created_at", "")), "text"),
                     (str(step.get("dataset", "")), "text")])
    if not codebook.history:
        rows.append([("none", "text")])
    return Sheet("Codebook", rows, widths={"A": 24, "B": 22, "C": 48, "I": 40, "T": 40})


def scales_sheet(codebook: Codebook) -> Sheet:
    rows: list = [[(c, "text") for c in SCALE_COLUMNS]]
    for scale in codebook.scales:
        rows.append([(str(scale.get("scale", "")), "text"), (str(scale.get("kind", "")), "text"),
                     (", ".join(scale.get("items") or []), "text"),
                     (", ".join(scale.get("reverse_items") or []), "text"),
                     (str(scale.get("rule", "")), "text"), (str(scale.get("source", "")), "text")])
    reverse = [v.name for v in codebook.variables if v.reverse]
    rows.append([])
    rows.append([("Reverse-keyed variables", "text"), (", ".join(reverse) or "none", "text")])
    return Sheet("Scales", rows, widths={"A": 24, "C": 60, "E": 60, "F": 40})


def provenance_rows(codebook: Codebook, facts: dict) -> list:
    """Key/value rows: what was exported, from which data version."""
    rows = [[("Export", "text"), ("Value", "text")]]
    for key, value in (("Program", f"Statistical Research Assistant {codebook.app_version}"),
                       ("Exported", codebook.created),
                       ("Dataset", codebook.dataset), ("Rows", codebook.rows),
                       ("Variables", codebook.columns),
                       ("Dataset SHA-256 (CSV text, as results record it)", codebook.sha256),
                       *facts.items()):
        rows.append([(key, "text"), cell_value(value)])
    return rows


def cell_value(value):
    """A value for a key/value sheet: numbers stay numbers, the rest is text."""
    if isinstance(value, (bool, np.bool_)) or value is None:
        return ("" if value is None else ("yes" if value else "no"), "text")
    if isinstance(value, (int, float, np.integer, np.floating)):
        return value
    if isinstance(value, (list, tuple, dict)):
        return (json.dumps(_json_safe(value), ensure_ascii=False), "text")
    return (as_text(value), "text")


# ================================================================ verification
XLSX_SIGNATURE = b"PK\x03\x04"
SAV_SIGNATURES = (b"$FL2", b"$FL3")


def _signature(path: Path, expected: tuple[bytes, ...]) -> bytes:
    with open(path, "rb") as stream:
        head = stream.read(4)
    if head not in expected:
        raise VerificationFailed(f"{path.name}: unexpected file signature {head!r}")
    return head


def verify_xlsx(path: Path, *, rows: int | None, header: list[str] | None,
                sheets: list[str]) -> dict:
    """Re-open the workbook (openpyxl, read-only): signature, sheets, the data
    header and the number of data rows."""
    from openpyxl import load_workbook

    _signature(path, (XLSX_SIGNATURE,))
    if not zipfile.is_zipfile(path):
        raise VerificationFailed(f"{path.name} is not a valid workbook")
    book = load_workbook(str(path), read_only=True, data_only=False)
    try:
        if book.sheetnames != list(sheets):
            raise VerificationFailed(f"sheets {book.sheetnames} instead of {sheets}")
        counted = None
        if header is not None:
            ws = book[sheets[0]]
            iterator = ws.iter_rows(values_only=True)
            first = list(next(iterator, ()))
            first = [("" if v is None else str(v)) for v in first]
            if first != list(header):
                raise VerificationFailed("the data header does not match the variables")
            counted = sum(1 for _ in iterator)
            if rows is not None and counted != rows:
                raise VerificationFailed(f"{counted} data rows re-read instead of {rows}")
    finally:
        book.close()
    return {"signature": "xlsx (zip)", "rows": counted, "sheets": list(sheets)}


def verify_csv(path: Path, *, rows: int, header: list[str], bom: bool,
               delimiter: str = ",") -> dict:
    data = path.read_bytes()
    has_bom = data.startswith(b"\xef\xbb\xbf")
    if has_bom != bool(bom):
        raise VerificationFailed("byte-order mark not as chosen")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise VerificationFailed(f"not UTF-8: {error}") from error
    import io

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        first = next(reader)
        counted = sum(1 for _ in reader)
    except (StopIteration, csv.Error) as error:
        raise VerificationFailed(f"not a readable CSV: {error}") from error
    if [csv_safety.restore(c) for c in first] != list(header):
        raise VerificationFailed("the CSV header does not match the variables")
    if counted != rows:
        raise VerificationFailed(f"{counted} data rows re-read instead of {rows}")
    return {"signature": "utf-8 csv" + (" with BOM" if has_bom else ""), "rows": counted}


def verify_sav(path: Path, *, rows: int, names: list[str]) -> dict:
    import pyreadstat

    head = _signature(path, SAV_SIGNATURES)
    _, meta = pyreadstat.read_sav(str(path), metadataonly=True)
    if list(meta.column_names) != list(names):
        raise VerificationFailed("the .sav variables are not the ones written")
    if names:
        frame, _ = pyreadstat.read_sav(str(path), usecols=[names[0]])
        counted = len(frame)
    else:
        counted = 0
    if counted != rows or (meta.number_rows not in (None, -1) and meta.number_rows != rows):
        raise VerificationFailed(f"{counted} rows re-read instead of {rows}")
    return {"signature": head.decode("ascii"), "rows": counted, "encoding": meta.file_encoding}


def verify_zip(path: Path, *, manifest: str = "manifest.json") -> dict:
    _signature(path, (XLSX_SIGNATURE,))
    with zipfile.ZipFile(path) as archive:
        broken = archive.testzip()
        if broken is not None:
            raise VerificationFailed(f"{broken} is damaged")
        names = archive.namelist()
        if manifest not in names:
            raise VerificationFailed("the bundle has no manifest")
        book = json.loads(archive.read(manifest).decode("utf-8"))
        for entry in book.get("files", []):
            data = archive.read(entry["path"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise VerificationFailed(f"{entry['path']} differs from the manifest")
    return {"signature": "zip", "files": len(names)}


# ================================================================ atomic save
def _temporary(path: Path) -> Path:
    return path.with_name(f".{path.stem}.{secrets.token_hex(4)}.partial{path.suffix}")


def _sha256(path: Path) -> str:
    return csv_safety.sha256_file(path)


def save_atomic(path: Path, produce: Callable[[Path], dict],
                verify: Callable[[Path, dict], dict]) -> dict:
    """Write with ``produce(temporary)`` in the destination folder, check the
    file with ``verify(temporary, facts)``, then move it to ``path`` in one
    step. A failure leaves no partial file behind and ``path`` as it was."""
    path = Path(path)
    temporary = _temporary(path)
    try:
        facts = dict(produce(temporary) or {})
        facts["verified"] = verify(temporary, facts)
        with open(temporary, "rb+") as stream:
            os.fsync(stream.fileno())
        digest, size = _sha256(temporary), temporary.stat().st_size
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    if path.stat().st_size != size or _sha256(path) != digest:
        raise VerificationFailed(f"{path.name} changed after it was moved into place")
    facts.update(path=str(path), bytes=size, sha256=digest)
    return facts


# ================================================================ the three formats
def export_xlsx(path: Path, df: pd.DataFrame | None, codebook: Codebook | None, *,
                sections: Iterable[str] = ("data", "codebook", "scales"),
                extra: Iterable[Sheet] = (), provenance: dict | None = None,
                progress: Progress | None = None) -> dict:
    """The workbook: Data, Codebook, Scales, then ``extra`` sheets (results)
    and Provenance, as chosen in ``sections``."""
    chosen = [s for s in SECTIONS if s in set(sections)]
    if not chosen:
        raise ExportError("Choose at least one part of the workbook.")
    sheets: list[Sheet] = []
    if "codebook" in chosen and codebook is not None:
        sheets.append(codebook_sheet(codebook))
    if "scales" in chosen and codebook is not None:
        sheets.append(scales_sheet(codebook))
    if "results" in chosen:
        sheets.extend(extra)
    if "provenance" in chosen:
        rows = provenance_rows(codebook, {}) if codebook is not None else [[("Export", "text")]]
        for extra_row in (provenance or {}).get("rows", []):
            rows.append(extra_row)
        sheets.append(Sheet("Provenance", rows, widths={"A": 44, "B": 70}))
    data = df if ("data" in chosen and df is not None) else None
    titles: list[str] = []

    def produce(temporary: Path) -> dict:
        facts = write_xlsx(temporary, sheets, data=data, progress=progress)
        titles.extend(facts["sheets"])
        return facts

    def verify(temporary: Path, facts: dict) -> dict:
        return verify_xlsx(temporary, rows=len(data) if data is not None else None,
                           header=[xlsx_text(str(c)) for c in data.columns]
                           if data is not None else None, sheets=titles)

    return save_atomic(path, produce, verify)


def export_csv(path: Path, df: pd.DataFrame, codebook: Codebook, *, bom: bool = True,
               layout: str = "comma", progress: Progress | None = None) -> dict:
    """The CSV and its codebook (``<name>_codebook.json``) next to it."""
    header = [str(c) for c in df.columns]
    delimiter, decimal = CSV_LAYOUTS.get(layout, (",", "dot"))
    facts = save_atomic(path, lambda temporary: write_csv(temporary, df, bom=bom, layout=layout,
                                                          progress=progress),
                        lambda temporary, written: verify_csv(temporary, rows=len(df),
                                                              header=header, bom=bom,
                                                              delimiter=delimiter))
    book = codebook.to_dict()
    book["data_file"] = {
        "name": Path(path).name, "sha256": facts["sha256"], "bytes": facts["bytes"],
        "format": "csv", "encoding": "utf-8", "bom": bool(bom), "delimiter": delimiter,
        "decimal": decimal,
        "quoting": "every text quoted; numbers unquoted",
        "missing": "an empty, unquoted field",
        "empty_text": "\"\" (a quoted field with no characters)",
        "formula_protection": {
            "rule": csv_safety.RULE, "cells": facts["protected"],
            "description": "a text cell that begins with = + - @, a tab or a carriage return "
                           "(or with apostrophes followed by one) has one apostrophe added; "
                           "numbers are never changed; remove one leading apostrophe from such "
                           "a cell to get the exported text back"},
    }
    sidecar = csv_safety.codebook_path(Path(path))
    text = json.dumps(book, ensure_ascii=False, indent=1).encode("utf-8")

    def produce_book(temporary: Path) -> dict:
        temporary.write_bytes(text)
        return {}

    def verify_book(temporary: Path, _facts: dict) -> dict:
        if json.loads(temporary.read_text(encoding="utf-8")) != book:
            raise VerificationFailed("the codebook does not read back")
        return {"signature": "json"}

    facts["codebook"] = save_atomic(sidecar, produce_book, verify_book)["path"]
    return facts


def export_sav(path: Path, df: pd.DataFrame, codebook: Codebook, *,
               plan: SavPlan | None = None) -> dict:
    plan = plan or plan_sav(df, codebook)
    names = [c.name for c in plan.columns]
    facts = save_atomic(path, lambda temporary: write_sav(temporary, df, codebook, plan=plan),
                        lambda temporary, written: verify_sav(temporary, rows=len(df),
                                                              names=names))
    facts["renamed"] = dict(plan.renamed)
    facts["changes"] = len(plan.changes)
    return facts


# ======================================================== participant data
_SENSITIVE_NAMES = (
    "name", "first_name", "firstname", "surname", "last_name", "lastname", "full_name",
    "fullname", "vards", "vārds", "uzvards", "uzvārds", "имя", "фамилия", "отчество", "фио",
    "email", "e_mail", "mail", "epasts", "e_pasts", "почта", "электронная_почта",
    "phone", "telephone", "tel", "mobile", "talrunis", "tālrunis", "telefons", "телефон",
    "address", "adrese", "адрес", "street", "iela", "улица",
    "birth", "birthdate", "birth_date", "date_of_birth", "dob", "dzimsanas", "dzimšanas",
    "dzimšanas_datums", "рождения", "дата_рождения",
    "personal_code", "personas_kods", "personaskods", "pk", "ssn", "passport", "pase",
    "паспорт", "ip", "ip_address", "latitude", "longitude", "gps",
)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE = re.compile(r"^\+?[\d\s\-()]{8,20}$")
_DATE_LIKE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")
_PERSONAL_CODE = re.compile(r"^\d{6}-?\d{5}$")      # the Latvian personas kods shape
_IPV4 = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


@dataclass(frozen=True)
class SensitiveColumn:
    name: str
    reason: str          # "direct" name/value pattern, "identifier", "free_text"
    detail: str


def _phone_like(value: str) -> bool:
    digits = sum(c.isdigit() for c in value)
    return 8 <= digits <= 15 and not _DATE_LIKE.match(value.strip())


def _name_tokens(name: str) -> set[str]:
    text = unicodedata.normalize("NFC", str(name)).casefold()
    text = re.sub(r"[\s\-./]+", "_", text)
    parts = {p for p in text.split("_") if p}
    return parts | {text}


def sensitive_columns(df: pd.DataFrame, codebook: Codebook | None = None,
                      sample: int = 200, *, levels: dict | None = None
                      ) -> list[SensitiveColumn]:
    """Columns that may identify a participant: direct identifiers (by name or
    by what the values look like), participant codes and free text. A
    heuristic warning, never a guarantee either way. ``levels``:
    {variable: (confirmed level, suggested level)} when there is no codebook."""
    found: list[SensitiveColumn] = []
    for column in df.columns:
        name = str(column)
        tokens = _name_tokens(name)
        entry = codebook.variable(name) if codebook is not None else None
        if entry is None and levels and name in levels:
            confirmed, suggested = levels[name]
            entry = VariableEntry(name=name, position=0, kind="", dtype="", level=confirmed,
                                  suggested=suggested)
        hit = next((t for t in _SENSITIVE_NAMES if t in tokens), None)
        if hit is not None:
            found.append(SensitiveColumn(name, "direct", f"name: {hit}"))
            continue
        values = [v for v in df[column].head(5000) if isinstance(v, str) and v.strip()][:sample]
        pattern = None
        if values:
            for label, regex in (("e-mail", _EMAIL), ("personal code", _PERSONAL_CODE),
                                 ("IP address", _IPV4), ("phone number", _PHONE)):
                share = sum(1 for v in values if regex.match(v.strip())
                            and (regex is not _PHONE or _phone_like(v))) / len(values)
                if share >= 0.5:
                    pattern = label
                    break
        if pattern is not None:
            found.append(SensitiveColumn(name, "direct", f"values: {pattern}"))
            continue
        level = entry.level if entry is not None else "unknown"
        suggested = entry.suggested if entry is not None else ""
        if level == "id" or (level == "unknown" and suggested == "id") or \
                looks_like_identifier(name):
            found.append(SensitiveColumn(name, "identifier", "participant code"))
            continue
        if values and sum(len(v) for v in values) / len(values) > 40 and \
                len(set(values)) > 0.5 * len(values):
            found.append(SensitiveColumn(name, "free_text", "free text answers"))
    return found
