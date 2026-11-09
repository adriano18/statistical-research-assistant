"""Create Groups from Scale (Stage 36.3, docs/STAGE36_SPEC.md §6).

A researcher picks a numeric scale (for example a loneliness total) and
derives a NEW ordered categorical variable from it. Four kinds of rule:

- ``documented``: cut points of the instrument, typed in by the researcher,
  who names the source (a free-text citation). The program cannot check
  them against the manual and says so.
- ``custom``: ranges the researcher defines (not norms).
- ``quantile``: k groups at the sample quantiles (data-derived and
  sample-dependent, never norms).
- ``equal_width``: k intervals of equal width between the observed minimum
  and maximum, or over a range the researcher states.

Decisions (all visible in the rule and in the preview, none hidden in a
library default):

- Every group states whether its lower and upper bound belong to it.
  Ranges of documented/custom rules carry explicit flags. k-based rules
  carry ``closed``: ``"right"`` gives (a, b] with the first group [a, b]
  (as ``pandas.qcut``), ``"left"`` gives [a, b) with the last group [a, b].
- Quantile cut points are Hyndman–Fan type 7 sample quantiles (linear
  interpolation, the NumPy/pandas default) whose positions (n − 1)·j/k are
  computed exactly, so a cut point that should fall on an observed value
  does (pandas ≥ 3 ``qcut`` nudges the probabilities for the same reason).
- Equal-width edges are ``numpy.linspace(low, high, k + 1)``.
- Values outside every range and missing or non-numeric values are never
  put into a group: they become missing in the new variable and are
  counted in the preview and in the transformation record.
- Overlapping ranges are reported by :func:`preview` and refused by
  :func:`apply` (a value must belong to one group only). Gaps are reported;
  values in a gap become missing.
- Nothing is written to the source column; :func:`apply` returns a new
  DataFrame and a record for the project's ``transformations`` table
  (kind, params, output columns).
- Wording never presents thresholds as clinical norms: documented cut
  points are "as entered by the researcher from <source>; check them
  against the manual"; the other rules say they are researcher-defined or
  data-derived and are not norms.

:func:`existing_groupings` proposes columns that already group the scale
(``UCLA_Level`` for ``UCLA``); it never selects one.

Every message carries a stable ``key`` and ``params`` for translation and
an English ``text``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import re
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from data_preparation import _check_target   # the same target-name rules as Data → Prepare

ENGINE_VERSION = "stage36.3"
RULE_VERSION = 1
KIND = "scale_groups"                         # transformations.kind

METHODS = ("documented", "custom", "quantile", "equal_width")
RANGE_METHODS = ("documented", "custom")
COUNT_METHODS = ("quantile", "equal_width")
CLOSED = ("right", "left")
MIN_GROUPS, MAX_GROUPS = 2, 10
SMALL_GROUP = 5
MAX_LABEL = 60
MAX_SOURCE = 300

# English text of every message key; the interface translates by key.
TEXT = {
    "groups.statement.documented": (
        "Cut points as entered by the researcher from: {source}. This program has not "
        "checked them; verify them against the instrument's manual (edition, scoring and "
        "population) before reporting the groups as the manual's categories."),
    "groups.statement.custom": (
        "Researcher-defined ranges{note}. They are not clinical norms or validated "
        "cut-offs; report how and why they were chosen."),
    "groups.statement.quantile": (
        "Data-derived groups: sample quantiles of the {n} values of {name} in this dataset "
        "(cut points {cuts}). They depend on this sample and are not norms; another sample "
        "would give other cut points."),
    "groups.statement.equal_width": (
        "Data-derived groups: {k} intervals of equal width from {low} to {high} ({span}). "
        "They are not norms."),
    "groups.empty": "Group “{label}” {interval} has no values.",
    "groups.small": ("Group “{label}” {interval} has only {n} value(s), fewer than {minimum}; "
                     "comparisons involving it are unstable."),
    "groups.out_of_range": ("{n} value(s) of {name} fall outside every group; they will be "
                            "missing in the new variable."),
    "groups.missing": "{n} value(s) of {name} are missing; they stay missing.",
    "groups.non_numeric": ("{n} non-numeric value(s) of {name} cannot be grouped; they will be "
                           "missing in the new variable."),
    "groups.overlap": ("The ranges of “{first}” and “{second}” overlap ({detail}): a value "
                       "there would belong to both groups. Make one bound exclusive or move it."),
    "groups.overlap_values": "{n} value(s) of {name} fall into more than one range.",
    "groups.gap": ("No group covers {detail}; such values would be missing in the new "
                   "variable."),
    "groups.quantile_ties": (
        "Cut point {cut} falls on {ties} tied values of {name}; all of them go to “{label}”, "
        "so the groups are unequal ({sizes})."),
    "groups.non_integer_threshold": (
        "Threshold {value} is not a whole number, but every value of {name} is: no value can "
        "equal it, so whether it is inclusive makes no difference. If the source gives "
        "thresholds for another scoring (for example a mean instead of a sum), convert them "
        "first."),
    "groups.no_integer_in_range": (
        "Group “{label}” {interval} cannot contain any whole-number value, and every value of "
        "{name} is a whole number."),
}


def _num(value: float | None) -> str:
    if value is None:
        return ""
    value = float(value)
    return f"{value:g}" if value == int(value) or abs(value) >= 1e-4 else f"{value:.6g}"


def interval_text(lower: float | None, upper: float | None,
                  lower_inclusive: bool, upper_inclusive: bool) -> str:
    """``[20, 34]``, ``(34, 49]``, ``≥ 65`` or ``< 20``."""
    if lower is None and upper is None:
        return "all values"
    if lower is None:
        return f"{'≤' if upper_inclusive else '<'} {_num(upper)}"
    if upper is None:
        return f"{'≥' if lower_inclusive else '>'} {_num(lower)}"
    return (f"{'[' if lower_inclusive else '('}{_num(lower)}, {_num(upper)}"
            f"{']' if upper_inclusive else ')'}")


@dataclass(frozen=True)
class Message:
    """A preview message: stable key and parameters, plus its English text."""

    key: str
    params: dict
    text: str

    @classmethod
    def make(cls, key: str, **params) -> "Message":
        return cls(key, dict(params), TEXT[key].format(**params))

    def to_dict(self) -> dict:
        return {"key": self.key, "params": dict(self.params), "text": self.text}

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(str(data["key"]), dict(data.get("params", {})), str(data["text"]))


# ----------------------------------------------------------------- the rule
def _finite_number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{what} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{what} must be a finite number.")
    return number


@dataclass(frozen=True)
class GroupRange:
    """The range of the scale one group covers; ``None`` means no limit.

    Both inclusivity flags are explicit. An open end cannot be inclusive.
    A range such as (3, 3] is empty; a rule refuses it, but quantile cut
    points that coincide on tied values realise one (an empty group).
    """

    lower: float | None
    upper: float | None
    lower_inclusive: bool
    upper_inclusive: bool

    def __post_init__(self):
        for name in ("lower", "upper"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite_number(value, f"The {name} bound"))
        for name in ("lower_inclusive", "upper_inclusive"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be True or False.")
        if self.lower is None and self.upper is None:
            raise ValueError("A range needs at least one bound.")
        if self.lower is None and self.lower_inclusive:
            raise ValueError("A range without a lower bound cannot include it.")
        if self.upper is None and self.upper_inclusive:
            raise ValueError("A range without an upper bound cannot include it.")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError(f"Lower bound {_num(self.lower)} is above upper bound "
                             f"{_num(self.upper)}.")

    @property
    def low(self) -> float:
        return -math.inf if self.lower is None else self.lower

    @property
    def high(self) -> float:
        return math.inf if self.upper is None else self.upper

    @property
    def empty(self) -> bool:
        return self.low == self.high and not (self.lower_inclusive and self.upper_inclusive)

    def includes(self, point: float) -> bool:
        above = point > self.low or (point == self.lower and self.lower_inclusive)
        below = point < self.high or (point == self.upper and self.upper_inclusive)
        return above and below

    def members(self, values: np.ndarray) -> np.ndarray:
        """Boolean mask of ``values`` inside the range (NaN is never inside)."""
        inside = ~np.isnan(values)
        if self.lower is not None:
            inside &= (values >= self.lower) if self.lower_inclusive else (values > self.lower)
        if self.upper is not None:
            inside &= (values <= self.upper) if self.upper_inclusive else (values < self.upper)
        return inside

    def text(self) -> str:
        return interval_text(self.lower, self.upper, self.lower_inclusive, self.upper_inclusive)

    def to_dict(self) -> dict:
        return {"lower": self.lower, "upper": self.upper,
                "lower_inclusive": self.lower_inclusive, "upper_inclusive": self.upper_inclusive}

    @classmethod
    def from_dict(cls, data: dict) -> "GroupRange":
        return cls(data.get("lower"), data.get("upper"), data["lower_inclusive"],
                   data["upper_inclusive"])


def _clean_label(label) -> str:
    text = " ".join(str(label).split())
    if not text:
        raise ValueError("Every group needs a label.")
    if len(text) > MAX_LABEL:
        raise ValueError(f"Group labels must be at most {MAX_LABEL} characters.")
    return text


@dataclass(frozen=True)
class GroupRule:
    """How to cut one numeric scale into ordered groups (validated, frozen).

    ``labels`` give the groups in their order, from the lowest to the
    highest values. ``ranges`` (documented and custom rules) align with
    ``labels``; ``k`` and ``closed`` define quantile and equal-width rules,
    ``span`` optionally fixes the equal-width range. ``source`` is the
    citation of documented thresholds (required) or a note.
    """

    method: str
    labels: tuple[str, ...]
    ranges: tuple[GroupRange, ...] = ()
    k: int | None = None
    closed: str = "right"
    span: tuple[float, float] | None = None
    source: str = ""
    version: int = RULE_VERSION

    def __post_init__(self):
        if self.method not in METHODS:
            raise ValueError(f"Unknown grouping method: {self.method}")
        if isinstance(self.labels, str):
            raise ValueError("Labels must be a list of group names.")
        labels = tuple(_clean_label(label) for label in self.labels)
        object.__setattr__(self, "labels", labels)
        if not MIN_GROUPS <= len(labels) <= MAX_GROUPS:
            raise ValueError(f"Create {MIN_GROUPS}–{MAX_GROUPS} groups.")
        if len({label.casefold() for label in labels}) != len(labels):
            raise ValueError("Group labels must be different from each other.")
        source = " ".join(str(self.source or "").split())
        if len(source) > MAX_SOURCE:
            raise ValueError(f"The source note must be at most {MAX_SOURCE} characters.")
        object.__setattr__(self, "source", source)
        if isinstance(self.version, bool) or not isinstance(self.version, int) \
                or not 1 <= self.version <= RULE_VERSION:
            raise ValueError("This grouping rule was saved by a newer version of the program.")
        ranges = tuple(self.ranges)
        object.__setattr__(self, "ranges", ranges)
        if self.method in RANGE_METHODS:
            self._check_ranges(ranges, labels)
            if self.method == "documented" and not source:
                raise ValueError("Name the source of the documented thresholds (manual, article "
                                 "or table), so the cut points can be checked.")
        else:
            self._check_count(labels)

    def _check_ranges(self, ranges, labels):
        if self.k is not None or self.span is not None:
            raise ValueError("Ranges are given explicitly; k and span apply to quantile and "
                             "equal-width rules only.")
        if len(ranges) != len(labels) or not all(isinstance(r, GroupRange) for r in ranges):
            raise ValueError("Give exactly one range for every group label.")
        for label, r in zip(labels, ranges):
            if r.empty:
                raise ValueError(f"The range of “{label}” ({r.text()}) is empty; include both "
                                 "bounds for a single value.")
        for previous, current in zip(ranges, ranges[1:]):
            if current.low < previous.low or current.high < previous.high:
                raise ValueError("List the groups from the lowest to the highest values.")

    def _check_count(self, labels):
        if self.ranges:
            raise ValueError("Quantile and equal-width rules derive their bounds from the data.")
        if isinstance(self.k, bool) or not isinstance(self.k, int):
            raise ValueError("State the number of groups k.")
        if self.k != len(labels):
            raise ValueError("Give one label for each of the k groups.")
        if self.closed not in CLOSED:
            raise ValueError("closed must be 'right' ((a, b], first group [a, b]) or 'left' "
                             "([a, b), last group [a, b]).")
        if self.span is not None:
            if self.method != "equal_width":
                raise ValueError("A fixed range applies to equal-width intervals only.")
            if isinstance(self.span, (str, bytes)) or len(self.span) != 2:
                raise ValueError("The range needs a lower and an upper value.")
            low = _finite_number(self.span[0], "The range minimum")
            high = _finite_number(self.span[1], "The range maximum")
            if not low < high:
                raise ValueError("The range minimum must be below its maximum.")
            object.__setattr__(self, "span", (low, high))

    def to_dict(self) -> dict:
        return {"version": self.version, "method": self.method, "labels": list(self.labels),
                "ranges": [r.to_dict() for r in self.ranges], "k": self.k,
                "closed": self.closed, "span": list(self.span) if self.span else None,
                "source": self.source}

    @classmethod
    def from_dict(cls, data: dict) -> "GroupRule":
        """Rebuild a stored rule; unknown keys are ignored, newer versions refused."""
        span = data.get("span")
        return cls(method=data["method"], labels=tuple(data["labels"]),
                   ranges=tuple(GroupRange.from_dict(r) for r in data.get("ranges") or ()),
                   k=data.get("k"), closed=data.get("closed", "right"),
                   span=tuple(span) if span else None, source=data.get("source", ""),
                   version=data.get("version", RULE_VERSION))


def range_rule(method: str, groups: Iterable[Sequence], source: str = "") -> GroupRule:
    """A documented or custom rule from ``(label, lower, upper, lower_inclusive,
    upper_inclusive)`` rows, lowest values first."""
    labels, ranges = [], []
    for row in groups:
        label, lower, upper, lower_inclusive, upper_inclusive = row
        labels.append(label)
        ranges.append(GroupRange(lower, upper, lower_inclusive, upper_inclusive))
    return GroupRule(method, tuple(labels), tuple(ranges), source=source)


def contiguous_rule(method: str, cut_points: Sequence[float], labels: Sequence[str], *,
                    closed: str = "right", lowest: float | None = None,
                    highest: float | None = None, source: str = "") -> GroupRule:
    """A documented or custom rule from cut points, without gaps or overlaps.

    ``closed="right"`` puts a value equal to a cut point into the LOWER group
    ((a, b], the first group including ``lowest``); ``"left"`` puts it into
    the UPPER group ([a, b), the last group including ``highest``).
    ``lowest``/``highest`` bound the outer groups (else they are open).
    """
    if closed not in CLOSED:
        raise ValueError("closed must be 'right' or 'left'.")
    cuts = [_finite_number(cut, "A cut point") for cut in cut_points]
    if any(second <= first for first, second in zip(cuts, cuts[1:])):
        raise ValueError("Cut points must increase.")
    labels = tuple(labels)
    if len(labels) != len(cuts) + 1:
        raise ValueError("Give one label more than there are cut points.")
    edges = [lowest, *cuts, highest]
    ranges = []
    for index in range(len(labels)):
        lower, upper = edges[index], edges[index + 1]
        if closed == "right":
            lower_inclusive = index == 0 and lower is not None
            upper_inclusive = upper is not None
        else:
            lower_inclusive = lower is not None
            upper_inclusive = index == len(labels) - 1 and upper is not None
        ranges.append(GroupRange(lower, upper, lower_inclusive, upper_inclusive))
    return GroupRule(method, labels, tuple(ranges), source=source)


def default_labels(method: str, k: int) -> tuple[str, ...]:
    """Neutral labels for k-based rules (Q1…Qk, Interval 1…k); the researcher may rename."""
    if isinstance(k, bool) or not isinstance(k, int) or not MIN_GROUPS <= k <= MAX_GROUPS:
        raise ValueError(f"Create {MIN_GROUPS}–{MAX_GROUPS} groups.")
    if method == "quantile":
        return tuple(f"Q{i}" for i in range(1, k + 1))
    return tuple(f"Interval {i}" for i in range(1, k + 1))


def quantile_rule(k: int, labels: Sequence[str] | None = None, *,
                  closed: str = "right") -> GroupRule:
    return GroupRule("quantile", tuple(labels or default_labels("quantile", k)), k=k,
                     closed=closed)


def equal_width_rule(k: int, labels: Sequence[str] | None = None, *, closed: str = "right",
                     span: tuple[float, float] | None = None) -> GroupRule:
    return GroupRule("equal_width", tuple(labels or default_labels("equal_width", k)), k=k,
                     closed=closed, span=span)


# ------------------------------------------------------------- the preview
@dataclass(frozen=True)
class GroupCount:
    """One group as the rule realises it on the data."""

    label: str
    lower: float | None
    upper: float | None
    lower_inclusive: bool
    upper_inclusive: bool
    n: int
    percent: float | None            # of the non-missing numeric values

    @property
    def interval(self) -> str:
        return interval_text(self.lower, self.upper, self.lower_inclusive, self.upper_inclusive)

    def to_dict(self) -> dict:
        return {"label": self.label, "lower": self.lower, "upper": self.upper,
                "lower_inclusive": self.lower_inclusive,
                "upper_inclusive": self.upper_inclusive, "n": self.n, "percent": self.percent}

    @classmethod
    def from_dict(cls, data: dict) -> "GroupCount":
        return cls(**{name: data.get(name) for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class GroupPreview:
    """What a rule would do to one column; nothing has been changed.

    ``n_valid`` counts the non-missing numeric values; group percentages
    and ``out_of_range_percent`` are of ``n_valid``. ``statement`` says what
    the thresholds are (never norms); ``warnings`` list what to check.
    """

    name: str
    rule: GroupRule
    groups: tuple[GroupCount, ...]
    n_total: int
    n_valid: int
    n_missing: int
    n_non_numeric: int
    n_out_of_range: int
    n_overlapping: int
    integer_data: bool
    statement: Message
    warnings: tuple[Message, ...] = ()

    @property
    def out_of_range_percent(self) -> float | None:
        return 100.0 * self.n_out_of_range / self.n_valid if self.n_valid else None

    @property
    def cut_points(self) -> tuple[float, ...]:
        """Inner boundaries between consecutive groups (k-based rules)."""
        return tuple(group.upper for group in self.groups[:-1] if group.upper is not None)

    def group(self, label: str) -> GroupCount:
        for group in self.groups:
            if group.label == label:
                return group
        raise KeyError(label)

    def warning_keys(self) -> tuple[str, ...]:
        return tuple(message.key for message in self.warnings)

    def to_dict(self) -> dict:
        return {"name": self.name, "rule": self.rule.to_dict(),
                "groups": [g.to_dict() for g in self.groups], "n_total": self.n_total,
                "n_valid": self.n_valid, "n_missing": self.n_missing,
                "n_non_numeric": self.n_non_numeric, "n_out_of_range": self.n_out_of_range,
                "n_overlapping": self.n_overlapping, "integer_data": self.integer_data,
                "statement": self.statement.to_dict(),
                "warnings": [m.to_dict() for m in self.warnings]}

    @classmethod
    def from_dict(cls, data: dict) -> "GroupPreview":
        return cls(name=data["name"], rule=GroupRule.from_dict(data["rule"]),
                   groups=tuple(GroupCount.from_dict(g) for g in data["groups"]),
                   n_total=data["n_total"], n_valid=data["n_valid"],
                   n_missing=data["n_missing"], n_non_numeric=data["n_non_numeric"],
                   n_out_of_range=data["n_out_of_range"],
                   n_overlapping=data.get("n_overlapping", 0),
                   integer_data=data["integer_data"],
                   statement=Message.from_dict(data["statement"]),
                   warnings=tuple(Message.from_dict(m) for m in data.get("warnings", ())))


def _numbers(series: pd.Series) -> tuple[np.ndarray, int, int]:
    """(float values with NaN for anything unusable, missing count, non-numeric count)."""
    if isinstance(series.dtype, pd.CategoricalDtype):
        series = series.astype(object)
    missing = series.isna().to_numpy()
    numeric = pd.to_numeric(series, errors="coerce").astype("float64").to_numpy(copy=True)
    numeric[~np.isfinite(numeric)] = np.nan
    unusable = ~missing & np.isnan(numeric)
    return numeric, int(missing.sum()), int(unusable.sum())


def _quantile_edges(valid: np.ndarray, k: int) -> list[float]:
    """Type-7 sample quantiles at j/k with exactly computed positions (n − 1)·j/k."""
    ordered = np.sort(valid)
    n = ordered.size
    edges = []
    for j in range(k + 1):
        position = Fraction(n - 1) * Fraction(j, k)
        below = position.numerator // position.denominator
        fraction = position - below
        value = float(ordered[below])
        if fraction and below + 1 < n:
            value = value + float(fraction) * (float(ordered[below + 1]) - value)
        edges.append(value)
    return edges


def realised_ranges(rule: GroupRule, valid: np.ndarray) -> tuple[GroupRange, ...]:
    """The rule's ranges on these values (k-based rules derive their bounds)."""
    if rule.method in RANGE_METHODS:
        return rule.ranges
    if valid.size == 0:
        raise ValueError("The scale has no numeric values to group.")
    low, high = float(valid.min()), float(valid.max())
    if rule.method == "quantile":
        if low == high:
            raise ValueError("The scale has no variation; quantile groups need different values.")
        edges = _quantile_edges(valid, rule.k)
    else:
        if rule.span is not None:
            low, high = rule.span
        elif low == high:
            raise ValueError("The scale has no variation; equal-width intervals need "
                             "different values.")
        edges = [float(edge) for edge in np.linspace(low, high, rule.k + 1)]
    ranges = []
    for index in range(rule.k):
        if rule.closed == "right":
            ranges.append(GroupRange(edges[index], edges[index + 1], index == 0, True))
        else:
            ranges.append(GroupRange(edges[index], edges[index + 1], True,
                                     index == rule.k - 1))
    return tuple(ranges)


def _shared_values(low: float, high: float) -> str:
    if not math.isfinite(low):
        return f"values below {_num(high)}"
    if not math.isfinite(high):
        return f"values above {_num(low)}"
    return f"values from {_num(low)} to {_num(high)}"


def _overlaps(ranges: Sequence[GroupRange], labels: Sequence[str]) -> list[Message]:
    messages = []
    for i in range(len(ranges)):
        for j in range(i + 1, len(ranges)):
            a, b = ranges[i], ranges[j]
            low, high = max(a.low, b.low), min(a.high, b.high)
            if low < high:
                detail = _shared_values(low, high)
            elif low == high and a.includes(low) and b.includes(low):
                detail = f"the value {_num(low)}"
            else:
                continue
            messages.append(Message.make("groups.overlap", first=labels[i], second=labels[j],
                                         detail=detail))
    return messages


def _has_integer(low: float, high: float, low_inclusive: bool, high_inclusive: bool) -> bool:
    """Is there a whole number between ``low`` and ``high`` (with these inclusivities)?"""
    if not math.isfinite(low) or not math.isfinite(high):
        return True
    candidate = math.ceil(low)
    if candidate == low and not low_inclusive:
        candidate += 1
    return candidate < high or (candidate == high and high_inclusive)


def _gaps(ranges: Sequence[GroupRange], integer_data: bool) -> list[Message]:
    messages = []
    for a, b in zip(ranges, ranges[1:]):
        if a.high < b.low:
            low_inclusive, high_inclusive = not a.upper_inclusive, not b.lower_inclusive
            if integer_data and not _has_integer(a.high, b.low, low_inclusive, high_inclusive):
                continue  # no whole number can fall between them
            detail = "values " + interval_text(a.upper, b.lower, low_inclusive, high_inclusive)
        elif a.high == b.low and not a.upper_inclusive and not b.lower_inclusive:
            detail = f"the value {_num(a.upper)}"
        else:
            continue
        messages.append(Message.make("groups.gap", detail=detail))
    return messages


def _statement(rule: GroupRule, name: str, valid: np.ndarray,
               ranges: Sequence[GroupRange]) -> Message:
    if rule.method == "documented":
        return Message.make("groups.statement.documented", source=rule.source)
    if rule.method == "custom":
        return Message.make("groups.statement.custom",
                            note=f" ({rule.source})" if rule.source else "")
    if rule.method == "quantile":
        cuts = ", ".join(_num(r.upper) for r in ranges[:-1])
        return Message.make("groups.statement.quantile", n=int(valid.size), name=name, cuts=cuts)
    span = ("the range entered by the researcher" if rule.span is not None else
            "the smallest and largest value in this sample; they depend on this sample")
    return Message.make("groups.statement.equal_width", k=rule.k, low=_num(ranges[0].lower),
                        high=_num(ranges[-1].upper), span=span)


def _assign(numbers: np.ndarray, ranges: Sequence[GroupRange]) -> tuple[np.ndarray, np.ndarray]:
    """(membership matrix groups × values, number of groups each value falls into)."""
    membership = np.vstack([r.members(numbers) for r in ranges]) if ranges else \
        np.zeros((0, numbers.size), dtype=bool)
    return membership, membership.sum(axis=0)


def preview(series: pd.Series, rule: GroupRule) -> GroupPreview:
    """Counts, bounds and warnings of ``rule`` on ``series``; nothing is modified."""
    if not isinstance(rule, GroupRule):
        raise TypeError("rule must be a GroupRule.")
    name = str(series.name) if series.name is not None else "the scale"
    numbers, n_missing, n_non_numeric = _numbers(series)
    valid = numbers[~np.isnan(numbers)]
    if valid.size == 0:
        raise ValueError(f"{name} has no numeric values to group.")
    integer_data = bool(np.all(valid == np.round(valid)))
    ranges = realised_ranges(rule, valid)
    membership, hits = _assign(numbers, ranges)
    present = ~np.isnan(numbers)
    n_valid = int(valid.size)
    groups = tuple(
        GroupCount(label, r.lower, r.upper, r.lower_inclusive, r.upper_inclusive,
                   int(row.sum()), 100.0 * int(row.sum()) / n_valid)
        for label, r, row in zip(rule.labels, ranges, membership))
    n_out = int((present & (hits == 0)).sum())
    n_overlapping = int((hits > 1).sum())
    warnings: list[Message] = []
    if rule.method in RANGE_METHODS:
        warnings += _overlaps(ranges, rule.labels)
        if n_overlapping:
            warnings.append(Message.make("groups.overlap_values", n=n_overlapping, name=name))
        warnings += _gaps(ranges, integer_data)
        if integer_data:
            seen = set()
            for r in ranges:
                for value in (r.lower, r.upper):
                    if value is not None and value != int(value) and value not in seen:
                        seen.add(value)
                        warnings.append(Message.make("groups.non_integer_threshold",
                                                     value=_num(value), name=name))
            for label, r in zip(rule.labels, ranges):
                if not _has_integer(r.low, r.high, r.lower_inclusive, r.upper_inclusive):
                    warnings.append(Message.make("groups.no_integer_in_range", label=label,
                                                 interval=r.text(), name=name))
    counts = [g.n for g in groups]
    if rule.method == "quantile" and max(counts) - min(counts) > 1:
        # Without ties, quantile groups differ by at most one value; larger
        # differences come from tied values at the cut points.
        sizes = ", ".join(f"{g.label}: {g.n}" for g in groups)
        for cut in dict.fromkeys(r.upper for r in ranges[:-1]):   # each cut point once
            ties = int(np.sum(valid == cut))
            if ties >= 2:
                holder = next(g for g, r in zip(groups, ranges) if r.includes(cut))
                warnings.append(Message.make("groups.quantile_ties", cut=_num(cut), ties=ties,
                                             name=name, label=holder.label, sizes=sizes))
    for group in groups:
        if group.n == 0:
            warnings.append(Message.make("groups.empty", label=group.label,
                                         interval=group.interval))
        elif group.n < SMALL_GROUP:
            warnings.append(Message.make("groups.small", label=group.label,
                                         interval=group.interval, n=group.n,
                                         minimum=SMALL_GROUP))
    if n_out:
        warnings.append(Message.make("groups.out_of_range", n=n_out, name=name))
    if n_non_numeric:
        warnings.append(Message.make("groups.non_numeric", n=n_non_numeric, name=name))
    if n_missing:
        warnings.append(Message.make("groups.missing", n=n_missing, name=name))
    return GroupPreview(
        name=name, rule=rule, groups=groups, n_total=int(series.size), n_valid=n_valid,
        n_missing=n_missing, n_non_numeric=n_non_numeric, n_out_of_range=n_out,
        n_overlapping=n_overlapping, integer_data=integer_data,
        statement=_statement(rule, name, valid, ranges), warnings=tuple(warnings))


# ---------------------------------------------------------------- applying
@dataclass(frozen=True, eq=False)
class GroupingResult:
    """A new DataFrame with the derived column and its history record.

    ``record()`` is the row for the project's ``transformations`` table:
    ``ProjectStore``'s ``add_transformation(dataset_id, **result.record())``.
    """

    frame: pd.DataFrame
    kind: str
    params: dict
    output_columns: tuple[str, ...]
    preview: GroupPreview
    message: str

    def record(self) -> dict:
        return {"kind": self.kind, "params": self.params,
                "output_columns": list(self.output_columns)}


def apply(df: pd.DataFrame, source: str, rule: GroupRule, target: str) -> GroupingResult:
    """Derive ``target`` (ordered categorical, labels in rule order) from ``source``.

    The input DataFrame and its ``source`` column are not modified. Missing,
    non-numeric and out-of-range values become missing and are counted.
    Raises ``ValueError`` if ``target`` exists, is not a valid variable name,
    or if ranges overlap.
    """
    _check_target(df, [source], target)
    if not isinstance(rule, GroupRule):
        raise TypeError("rule must be a GroupRule.")
    if rule.method in RANGE_METHODS:
        overlaps = _overlaps(rule.ranges, rule.labels)
        if overlaps:
            raise ValueError(overlaps[0].text)
    result = preview(df[source], rule)
    numbers, _, _ = _numbers(df[source])
    ranges = tuple(GroupRange(g.lower, g.upper, g.lower_inclusive, g.upper_inclusive)
                   for g in result.groups)
    membership, hits = _assign(numbers, ranges)
    codes = np.full(numbers.size, -1, dtype=np.int64)
    for index, row in enumerate(membership):
        codes[row & (hits == 1)] = index
    derived = pd.Categorical.from_codes(codes, categories=list(rule.labels), ordered=True)
    frame = df.copy(deep=True)
    frame[target] = pd.Series(derived, index=df.index, name=target)
    params = {
        "engine": ENGINE_VERSION,
        "version": rule.version,
        "source": source,
        "target": target,
        "rule": rule.to_dict(),
        "groups": [{key: value for key, value in g.to_dict().items() if key != "percent"}
                   for g in result.groups],
        "n_total": result.n_total,
        "n_missing": result.n_missing,
        "n_non_numeric": result.n_non_numeric,
        "n_out_of_range": result.n_out_of_range,
        "statement": result.statement.text,
        "warnings": [m.text for m in result.warnings],
    }
    counts = ", ".join(f"{g.label} {g.n}" for g in result.groups)
    unassigned = result.n_missing + result.n_non_numeric + result.n_out_of_range
    message = (f"Created {target} from {source}: {len(result.groups)} groups ({counts}); "
               f"{unassigned} value(s) without a group are missing ({result.n_missing} missing, "
               f"{result.n_non_numeric} non-numeric, {result.n_out_of_range} outside every "
               f"range). {source} is unchanged. {result.statement.text}")
    return GroupingResult(frame, KIND, params, (target,), result, message)


# ------------------------------------------------------ existing groupings
GROUPING_WORDS = (
    "level", "levels", "lvl", "group", "groups", "grp", "grouped", "cat", "cats", "categ",
    "category", "categories", "class", "classes", "band", "bands", "bin", "bins", "binned",
    "tertile", "tertiles", "quartile", "quartiles", "quintile", "quintiles", "split",
    "severity", "grade", "grades",
    "limenis", "līmenis", "grupa", "grupas", "kategorija",     # Latvian
    "уровень", "группа", "группы", "категория",                 # Russian
)
_WORD = re.compile(r"^\d*(" + "|".join(sorted(map(re.escape, GROUPING_WORDS), key=len,
                                                   reverse=True)) + r")\d*$")
_SEPARATORS = " _-.:"


@dataclass(frozen=True)
class ExistingGrouping:
    """A column that may already group the scale (proposal only)."""

    name: str
    categories: tuple[str, ...]          # in their order (codes, ordered dtype or by median)
    counts: tuple[int, ...]              # rows with both values present
    source_ranges: tuple[tuple[float, float], ...]   # min–max of the scale in each category
    splits_scale: bool                   # categories cover non-overlapping ranges, in order
    missing: int                         # rows where the grouping is empty
    reason: str


def _name_matches(source: str, candidate: str) -> bool:
    stem, name = source.casefold().strip(), candidate.casefold().strip()
    if not stem or name == stem:
        return False
    rests = []
    if name.startswith(stem):
        rests.append(name[len(stem):].strip(_SEPARATORS))
    if name.endswith(stem):
        rests.append(name[:-len(stem)].strip(_SEPARATORS))
    return any(rest and _WORD.match(rest) for rest in rests)


def _category_text(value) -> str:
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _category_order(values: pd.Series, scale: pd.Series) -> list:
    if isinstance(values.dtype, pd.CategoricalDtype):
        present = set(values.dropna())
        return [c for c in values.dtype.categories if c in present]
    unique = list(pd.unique(values.dropna()))
    numeric = pd.to_numeric(pd.Series(unique, dtype=object), errors="coerce")
    if numeric.notna().all():
        return [value for _, value in sorted(zip(numeric, unique), key=lambda pair: pair[0])]
    medians = {value: float(scale[values == value].median()) for value in unique}
    return sorted(unique, key=lambda value: (medians[value], str(value)))


def existing_groupings(df: pd.DataFrame, source: str, *,
                       max_categories: int = MAX_GROUPS) -> tuple[ExistingGrouping, ...]:
    """Columns that look like a grouping of ``source`` (``UCLA_Level`` for ``UCLA``).

    A column is proposed when its name is the scale's name plus a grouping
    word (level, group, cat, tertile, …; English, Latvian or Russian) and it
    has 2–``max_categories`` distinct values. Proposals say whether the
    categories split the scale into non-overlapping ranges. Nothing is
    selected: the researcher decides whether to use one.
    """
    if source not in df.columns:
        raise ValueError(f"Unknown variable: {source}")
    scale = pd.to_numeric(df[source], errors="coerce")
    proposals = []
    for candidate in df.columns:
        candidate = str(candidate)
        if candidate == source or not _name_matches(source, candidate):
            continue
        values = df[candidate]
        distinct = int(values.nunique(dropna=True))
        if not 2 <= distinct <= max_categories:
            continue
        both = values.notna() & scale.notna()
        order = _category_order(values[both], scale[both])
        counts, spans = [], []
        for category in order:
            inside = scale[both & (values == category)]
            counts.append(int(inside.size))
            spans.append((float(inside.min()), float(inside.max())) if inside.size else
                          (math.nan, math.nan))
        splits = bool(spans) and all(math.isfinite(low) for low, _ in spans) and all(
            first[1] < second[0] for first, second in zip(spans, spans[1:]))
        described = "; ".join(f"{_category_text(category)}: {_num(low)}–{_num(high)}"
                              for category, (low, high) in zip(order, spans)
                              if math.isfinite(low))
        reason = (f"The name of {candidate} combines {source} with a grouping word, and it has "
                  f"{distinct} categories. ")
        reason += (f"Each category covers its own range of {source} ({described})."
                   if splits else
                   f"Its categories do not split {source} into separate ranges ({described}); "
                   "check how it was made before using it.")
        proposals.append(ExistingGrouping(
            candidate, tuple(_category_text(c) for c in order), tuple(counts), tuple(spans),
            splits, int(values.isna().sum()), reason))
    proposals.sort(key=lambda p: (not p.splits_scale, p.name.casefold()))
    return tuple(proposals)


__all__ = [
    "ENGINE_VERSION", "RULE_VERSION", "KIND", "METHODS", "TEXT", "Message", "GroupRange",
    "GroupRule", "range_rule", "contiguous_rule", "quantile_rule", "equal_width_rule",
    "default_labels",
    "GroupCount", "GroupPreview", "preview", "realised_ranges", "GroupingResult", "apply",
    "ExistingGrouping", "existing_groupings", "interval_text",
]
