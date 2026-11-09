"""Typed statistical results (Stage 36, spec §8).

Every number a result shows comes from a :class:`Quantity` computed by the
engine, never from parsing report text. A quantity that has no value says
why: not applicable, not calculated, unavailable, or calculation failed
(never a made-up zero, a dash or "Not captured").

A :class:`StructuredResult` holds what a method produced: the sample,
the inputs, the quantities (estimates, intervals, test statistics),
diagnostics, warnings, tables and provenance. It serialises to JSON so a
research task can store it and show it again after a restart.

Descriptive statistics (:func:`describe_quantitative`) use pandas with
stated conventions:

- SD: sample standard deviation (n - 1 denominator).
- Percentiles, quartiles and IQR: linear interpolation between order
  statistics (Hyndman–Fan type 7, pandas/NumPy default).
- Skewness G1 and excess kurtosis G2: the bias-adjusted sample estimators
  (as in SPSS and Excel; pandas ``skew``/``kurt``), with their usual
  standard errors.
- The 95% confidence interval of the mean is optional (t distribution);
  it is not added to every descriptive value by default.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

ENGINE_VERSION = "stage36.2"

STATUSES = ("ok", "not_applicable", "not_calculated", "unavailable", "failed")
STATUS_TEXT = {
    "not_applicable": "Not applicable",
    "not_calculated": "Not calculated",
    "unavailable": "Unavailable",
    "failed": "Calculation failed",
}


def _finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class Quantity:
    """One reported number, with its interval and test when it has them."""

    key: str                         # stable identifier, e.g. "mean", "rho"
    label: str                       # display label (English; the UI may translate the key)
    value: float | int | None = None
    status: str = "ok"
    note: str = ""                   # how it was computed, or why there is no value
    ci_low: float | None = None
    ci_high: float | None = None
    ci_level: float | None = None
    ci_method: str = ""
    p: float | None = None
    p_method: str = ""
    integer: bool = False            # counts are shown without decimals

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"Unknown status: {self.status}")
        if self.status == "ok" and not _finite(self.value):
            raise ValueError(f"{self.key}: a value with status 'ok' must be finite")

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def has_ci(self) -> bool:
        return _finite(self.ci_low) and _finite(self.ci_high)

    @classmethod
    def missing(cls, key: str, label: str, status: str, note: str) -> "Quantity":
        if status == "ok":
            raise ValueError("A missing quantity needs a status other than 'ok'.")
        return cls(key, label, None, status, note)

    def text(self, digits: int = 2) -> str:
        """The value as shown in tables, or the reason it is absent."""
        if not self.ok:
            return STATUS_TEXT[self.status]
        if self.integer:
            return str(int(round(float(self.value))))
        return f"{float(self.value):.{digits}f}"

    def ci_text(self, digits: int = 2) -> str:
        if not self.has_ci:
            return ""
        level = f"{self.ci_level:.0%} " if self.ci_level else ""
        return f"{level}CI [{self.ci_low:.{digits}f}, {self.ci_high:.{digits}f}]"

    def to_dict(self) -> dict:
        # Identity checks: a value of 0 must survive (0 == False in Python).
        return {k: v for k, v in asdict(self).items()
                if v is not None and v is not False and not (isinstance(v, str) and v == "")}

    @classmethod
    def from_dict(cls, data: dict) -> "Quantity":
        names = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass(frozen=True)
class Table:
    """A table built from quantities (rows of already formatted cells)."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict:
        return {"title": self.title, "columns": list(self.columns),
                "rows": [list(row) for row in self.rows]}

    @classmethod
    def from_dict(cls, data: dict) -> "Table":
        return cls(data["title"], tuple(data["columns"]), tuple(tuple(r) for r in data["rows"]))


@dataclass(frozen=True)
class StructuredResult:
    """What one analysis produced, independent of how it is presented."""

    method_id: str
    title: str
    sample: dict
    inputs: dict
    quantities: tuple[Quantity, ...]
    diagnostics: tuple[Quantity, ...] = ()
    warnings: tuple[str, ...] = ()
    tables: tuple[Table, ...] = ()
    provenance: dict = field(default_factory=dict)
    method_version: str = ENGINE_VERSION

    def quantity(self, key: str) -> Quantity | None:
        for quantity in (*self.quantities, *self.diagnostics):
            if quantity.key == key:
                return quantity
        return None

    def to_dict(self) -> dict:
        return {
            "method_id": self.method_id, "method_version": self.method_version,
            "title": self.title, "sample": _json_safe(self.sample),
            "inputs": _json_safe(self.inputs),
            "quantities": [q.to_dict() for q in self.quantities],
            "diagnostics": [q.to_dict() for q in self.diagnostics],
            "warnings": list(self.warnings),
            "tables": [t.to_dict() for t in self.tables],
            "provenance": _json_safe(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructuredResult":
        return cls(
            method_id=data["method_id"], title=data["title"], sample=dict(data["sample"]),
            inputs=dict(data["inputs"]),
            quantities=tuple(Quantity.from_dict(q) for q in data["quantities"]),
            diagnostics=tuple(Quantity.from_dict(q) for q in data.get("diagnostics", ())),
            warnings=tuple(data.get("warnings", ())),
            tables=tuple(Table.from_dict(t) for t in data.get("tables", ())),
            provenance=dict(data.get("provenance", {})),
            method_version=data.get("method_version", ENGINE_VERSION),
        )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


# ------------------------------------------------------------ descriptive
def describe_quantitative(values: pd.Series, name: str, *, ci_mean: bool = False,
                          level: float = 0.95) -> StructuredResult:
    """N, missing, M, SD, median, quartiles, IQR, min/max, percentiles,
    skewness and kurtosis of one quantitative variable."""
    raw = values
    numeric = pd.to_numeric(raw, errors="coerce")
    non_numeric = int((raw.notna() & numeric.isna()).sum())
    clean = numeric.dropna().astype(float)
    n = int(clean.size)
    missing = int(raw.isna().sum())
    quantities: list[Quantity] = [
        Quantity("n", "N", n, integer=True),
        Quantity("missing", "Missing", missing, integer=True,
                 note="empty cells in this variable"),
    ]
    warnings: list[str] = []
    if non_numeric:
        warnings.append(f"{non_numeric} non-numeric value(s) were left out.")
    if n == 0:
        for key, label in (("mean", "Mean"), ("sd", "SD"), ("median", "Median"),
                           ("iqr", "IQR"), ("min", "Minimum"), ("max", "Maximum")):
            quantities.append(Quantity.missing(key, label, "unavailable", "no numeric values"))
        return StructuredResult("descriptive", f"Descriptive statistics: {name}",
                                {"n_total": int(raw.size), "n_used": 0, "n_missing": missing},
                                {"variables": [name], "options": {"ci_mean": ci_mean}},
                                tuple(quantities), warnings=tuple(warnings),
                                provenance=_provenance())
    mean = float(clean.mean())
    quantities.append(Quantity("mean", "Mean", mean))
    if n >= 2:
        sd = float(clean.std(ddof=1))
        quantities.append(Quantity("sd", "SD", sd, note="sample SD (n - 1)"))
        se = sd / math.sqrt(n)
        quantities.append(Quantity("se_mean", "SE of the mean", se))
    else:
        quantities.append(Quantity.missing("sd", "SD", "not_applicable", "needs at least two values"))
        quantities.append(Quantity.missing("se_mean", "SE of the mean", "not_applicable",
                                           "needs at least two values"))
    q1, median, q3 = (float(v) for v in clean.quantile([0.25, 0.5, 0.75]))
    rule = "linear interpolation (Hyndman–Fan type 7)"
    quantities += [
        Quantity("median", "Median", median),
        Quantity("q1", "Q1 (25th percentile)", q1, note=rule),
        Quantity("q3", "Q3 (75th percentile)", q3, note=rule),
        Quantity("iqr", "IQR", q3 - q1, note=rule),
        Quantity("min", "Minimum", float(clean.min())),
        Quantity("max", "Maximum", float(clean.max())),
    ]
    for pct in (5, 10, 90, 95):
        quantities.append(Quantity(f"p{pct}", f"{pct}th percentile",
                                   float(clean.quantile(pct / 100)), note=rule))
    diagnostics: list[Quantity] = []
    if n >= 3 and clean.std(ddof=1) > 0:
        skew = float(clean.skew())
        se_skew = math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))
        diagnostics.append(Quantity("skewness", "Skewness (G1)", skew,
                                    note=f"bias-adjusted; SE = {se_skew:.3f}"))
    else:
        diagnostics.append(Quantity.missing("skewness", "Skewness (G1)", "not_applicable",
                                            "needs at least three values with variation"))
    if n >= 4 and clean.std(ddof=1) > 0:
        kurt = float(clean.kurt())
        se_skew = math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))
        se_kurt = 2 * se_skew * math.sqrt((n * n - 1) / ((n - 3) * (n + 5)))
        diagnostics.append(Quantity("kurtosis", "Excess kurtosis (G2)", kurt,
                                    note=f"bias-adjusted; SE = {se_kurt:.3f}"))
    else:
        diagnostics.append(Quantity.missing("kurtosis", "Excess kurtosis (G2)", "not_applicable",
                                            "needs at least four values with variation"))
    if ci_mean:
        if n >= 2 and clean.std(ddof=1) > 0:
            t = stats.t.ppf(0.5 + level / 2, n - 1)
            se = float(clean.std(ddof=1)) / math.sqrt(n)
            quantities = [q if q.key != "mean" else Quantity(
                "mean", "Mean", mean, ci_low=mean - t * se, ci_high=mean + t * se,
                ci_level=level, ci_method="t distribution, df = n - 1") for q in quantities]
        else:
            warnings.append("The confidence interval of the mean needs at least two different values.")
    if n < 5:
        warnings.append("Very few values: percentiles and shape statistics are unstable.")
    return StructuredResult(
        "descriptive", f"Descriptive statistics: {name}",
        {"n_total": int(raw.size), "n_used": n, "n_missing": missing},
        {"variables": [name], "options": {"ci_mean": ci_mean, "level": level}},
        tuple(quantities), tuple(diagnostics), tuple(warnings), provenance=_provenance())


def describe_categorical(values: pd.Series, name: str, scale: str) -> StructuredResult:
    """Counts and percentages of a nominal or ordinal variable."""
    missing = int(values.isna().sum())
    present = values.dropna()
    counts = present.astype("string").value_counts()
    if scale == "ordinal":
        try:
            counts = counts.sort_index(key=lambda idx: pd.to_numeric(idx, errors="coerce"))
        except (TypeError, ValueError):
            counts = counts.sort_index()
    n = int(present.size)
    rows = tuple((str(label), str(int(count)), f"{100 * count / n:.1f}" if n else "")
                 for label, count in counts.items())
    quantities = (Quantity("n", "N", n, integer=True),
                  Quantity("missing", "Missing", missing, integer=True),
                  Quantity("categories", "Categories", int(counts.size), integer=True))
    if n:
        mode_label = str(counts.idxmax())
        quantities += (Quantity("mode_count", f"Most frequent: {mode_label}", int(counts.max()),
                                integer=True),)
    table = Table(f"Frequencies: {name}", ("Category", "n", "%"), rows)
    return StructuredResult("descriptive", f"Descriptive statistics: {name}",
                            {"n_total": int(values.size), "n_used": n, "n_missing": missing},
                            {"variables": [name], "options": {"scale": scale}},
                            quantities, tables=(table,), provenance=_provenance())


def _provenance(**extra) -> dict:
    import platform

    import scipy

    record = {"engine": ENGINE_VERSION, "python": platform.python_version(),
              "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__}
    record.update(extra)
    return record
