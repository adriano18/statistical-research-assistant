"""Chart Studio engine: editable chart specifications drawn from prepared data.

Stage 36.4 (docs/STAGE36_SPEC.md §9). A chart is described by a
:class:`ChartSpec` (JSON-serialisable, stored with the project) and drawn from
a :class:`ChartData` that :func:`prepare` extracts from a DataFrame.

* ``prepare(spec, frame)`` reads exactly the columns the chart needs, applies
  the incomplete-row rule of the kind (:data:`CASE_HANDLING`), records missing
  counts, computes the statistics a chart displays (the coefficients of a
  correlation heatmap) and returns warnings. It never modifies the DataFrame.
* ``render(spec, data, fmt)`` draws only from the prepared data. Changing the
  title, labels, palette, fonts, size, kind or layout redraws the stored
  values and never recomputes a statistic of the analysis. Presentation
  quantities (bins, kernel density curves, box quartiles, display z-scores,
  means along a line, trend lines) are derived again from the stored values
  while drawing.

Output is deterministic: the same specification and data give byte-identical
PNG and SVG files and PDFs with a stable page count (no dates or software
versions are written, SVG ids use a fixed salt and display jitter uses a fixed
random state). Warnings are returned as text, never printed. Every figure has
a title and an alt text from :func:`describe`, embedded as PNG/PDF metadata
and as the SVG ``<title>``/``<desc>``.

This module contains no user-interface code.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from io import BytesIO
import json
import math
import numbers
import re
import textwrap
from typing import Any
import warnings
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use("Agg")
from matplotlib import cycler, font_manager
from matplotlib.axes import Axes
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgba
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd
from scipy import stats

from variable_rules import looks_like_identifier


__all__ = [
    "SPEC_VERSION", "DATA_VERSION", "KINDS", "KIND_LABELS", "MULTIBOX_LAYOUTS",
    "TRENDS", "DENSITIES", "CORRELATION_METHODS", "BANDWIDTH_RULES", "FACET_KINDS",
    "LEGEND_POSITIONS", "FORMATS", "CASE_HANDLING", "PRESENTATION_FIELDS",
    "Palette", "PALETTES", "DEFAULT_PALETTE", "ChartSpec", "CorrelationTable",
    "ChartData", "prepare", "correlation_chart_data", "chart_warnings",
    "figure_count", "describe", "build_figure", "render", "render_all",
    "render_pdf_pages", "resolved_font",
]


# --------------------------------------------------------------------------
# Vocabulary and thresholds
# --------------------------------------------------------------------------

SPEC_VERSION = 1
DATA_VERSION = 1

KINDS = (
    "histogram", "frequency_polygon", "boxplot", "multi_boxplot", "violin",
    "scatter", "heatmap", "qq", "line", "faceted",
)
KIND_LABELS = {
    "histogram": "Histogram",
    "frequency_polygon": "Frequency polygon",
    "boxplot": "Boxplot",
    "multi_boxplot": "Multi-variable boxplots",
    "violin": "Violin plot",
    "scatter": "Scatterplot",
    "heatmap": "Correlation heatmap",
    "qq": "Normal Q–Q plot",
    "line": "Line chart",
    "faceted": "Small multiples",
}
MULTIBOX_LAYOUTS = ("single", "panels", "sequential", "by_group")
TRENDS = ("none", "ols", "lowess")
DENSITIES = ("none", "kde", "normal")
CORRELATION_METHODS = ("pearson", "spearman", "kendall")
BANDWIDTH_RULES = ("scott", "silverman")
FACET_KINDS = ("histogram", "boxplot")
LEGEND_POSITIONS = (
    "none", "best", "upper right", "upper left", "lower left", "lower right",
    "right", "center left", "center right", "lower center", "upper center",
    "center", "outside",
)
FORMATS = ("png", "svg", "pdf")

METHOD_LABELS = {
    "pearson": "Pearson’s r",
    "spearman": "Spearman’s ρ",
    "kendall": "Kendall’s τ-b",
}
TREND_LABELS = {"ols": "OLS trend line", "lowess": "LOWESS curve"}

_AVAILABLE_CASES = (
    "Available cases: each variable uses all of its non-missing values; in a "
    "display split by group, rows without a group value are left out."
)
#: How each kind treats incomplete rows; quoted in the figure note whenever
#: rows or values are left out, and summarised in the missing-value warnings.
CASE_HANDLING = {
    "histogram": _AVAILABLE_CASES,
    "frequency_polygon": _AVAILABLE_CASES,
    "boxplot": _AVAILABLE_CASES,
    "multi_boxplot": _AVAILABLE_CASES,
    "violin": _AVAILABLE_CASES,
    "qq": _AVAILABLE_CASES,
    "faceted": _AVAILABLE_CASES,
    "scatter": "Complete pairs: only rows where both variables (and the group, "
               "if one is used) are present.",
    "line": "Complete pairs: each line uses the rows where x and that y variable "
            "(and the group, if one is used) are present.",
    "heatmap": "Pairwise complete: each coefficient uses the rows where both "
               "variables are present; N is reported for every pair.",
}

#: Spec fields that only change the look of a chart. Changing them never
#: changes :class:`ChartData` (values, statistics or warnings).
PRESENTATION_FIELDS = frozenset({
    "title", "x_label", "y_label", "legend", "palette", "font_family",
    "font_size", "width_in", "height_in", "dpi", "show_points", "show_outliers",
    "grid", "x_limits", "y_limits", "number_format", "apa_style", "bins",
    "bandwidth", "group_order", "note", "figure_number",
})

RANGE_RATIO_LIMIT = 3.0      # one range > 3 times another: not comparable on one axis
MIN_DENSITY_N = 3            # kernel or normal density curves and violins
MIN_QQ_N = 3
MIN_CORRELATION_N = 5        # as in correlation_matrix.py
MIN_TREND_N = {"ols": 3, "lowess": 5}
SMALL_GROUP_N = 5
MAX_GROUP_LEVELS = 12
MAX_VARIABLES = 24
MAX_BINS = 100
JITTER_SEED = 2026           # the display-jitter seed of the other chart modules
LOWESS_FRACTION = 2 / 3
LOWESS_ITERATIONS = 3
LOWESS_EXACT_N = 1000        # larger samples interpolate within 1% of the x range
SVG_HASH_SALT = "chart-studio"
FALLBACK_FONT = "DejaVu Sans"
TREND_COLOR = "#1F1F1F"
MISSING_CELL_COLOR = "#E5E7EB"

_MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")
_LINESTYLES = ("-", "--", "-.", ":")
_LINE_HEIGHT = 1.28          # text line height as a multiple of the font size


# --------------------------------------------------------------------------
# Palettes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    """A named, colour-blind-safe colour set.

    ``colors`` distinguish series (variables or groups); ``diverging`` is the
    colour ramp of correlation heatmaps from -1 to +1; ``hatches`` add patterns
    to filled areas when colour alone would not separate the series.
    """

    name: str
    label: str
    colors: tuple[str, ...]
    diverging: tuple[str, ...]
    hatches: tuple[str, ...] = ()
    source: str = ""


PALETTES: dict[str, Palette] = {palette.name: palette for palette in (
    Palette(
        "scientific_blue", "Scientific blue",
        ("#4477AA", "#EE6677", "#228833", "#CCBB44", "#66CCEE", "#AA3377", "#BBBBBB"),
        ("#2166AC", "#4393C3", "#92C5DE", "#D1E5F0", "#F7F7F7", "#FDDBC7",
         "#F4A582", "#D6604D", "#B2182B"),
        source="Calm blue first, then Paul Tol's colour-blind-safe 'bright' "
               "scheme; ColorBrewer RdBu (colour-blind safe) for heatmaps.",
    ),
    Palette(
        "okabe_ito", "Okabe–Ito",
        ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00",
         "#F0E442", "#000000"),
        ("#542788", "#8073AC", "#B2ABD2", "#D8DAEB", "#F7F7F7", "#FEE0B6",
         "#FDB863", "#E08214", "#B35806"),
        source="Okabe & Ito (2008) colour-universal design; ColorBrewer PuOr "
               "(colour-blind safe) for heatmaps.",
    ),
    Palette(
        "tol_muted", "Muted (Tol)",
        ("#332288", "#88CCEE", "#44AA99", "#117733", "#999933", "#DDCC77",
         "#CC6677", "#882255", "#AA4499"),
        ("#364B9A", "#4A7BB7", "#6EA6CD", "#98CAE1", "#C2E4EF", "#EAECCC",
         "#FEDA8B", "#FDB366", "#F67E4B", "#DD3D2D", "#A50026"),
        source="Paul Tol's colour-blind-safe 'muted' qualitative and 'sunset' "
               "diverging schemes.",
    ),
    Palette(
        "grayscale", "Grayscale (print)",
        ("#404040", "#A0A0A0", "#000000", "#D0D0D0", "#707070"),
        # Shading shows the strength of a coefficient; its sign is printed.
        ("#3A3A3A", "#F7F7F7", "#3A3A3A"),
        hatches=("", "///", "...", "\\\\\\", "xx"),
        source="Lightness steps plus hatching; readable without colour vision "
               "and in black-and-white print.",
    ),
)}
DEFAULT_PALETTE = "scientific_blue"


# --------------------------------------------------------------------------
# Chart specification
# --------------------------------------------------------------------------

def _choice(value: Any, options: Sequence[str], label: str) -> str:
    if not isinstance(value, str) or value not in options:
        raise ValueError(f"{label} must be one of: {', '.join(options)}.")
    return value


def _text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    if len(value) > limit:
        raise ValueError(f"{label} must be at most {limit} characters.")
    return value


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f"{label} must be a column name (1–200 characters).")
    return value


def _names(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError(f"{label} must be a list of column names.")
    return tuple(_name(item, label) for item in value)


def _flag(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be true or false.")
    return value


def _number(value: Any, label: str, low: float, high: float) -> float:
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real)
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{label} must be a number from {low:g} to {high:g}.")
    return float(value)


def _integer(value: Any, label: str, low: int, high: int) -> int:
    if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
        if math.isfinite(value) and float(value).is_integer():
            value = int(value)
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral)
            or not low <= value <= high):
        raise ValueError(f"{label} must be a whole number from {low} to {high}.")
    return int(value)


def _limits(value: Any, label: str) -> tuple[float, float] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError(f"{label} must be two numbers: lower and upper limit.")
    pair = tuple(value)
    if len(pair) != 2:
        raise ValueError(f"{label} must be two numbers: lower and upper limit.")
    low, high = (_number(item, label, -1e15, 1e15) for item in pair)
    if not low < high:
        raise ValueError(f"{label}: the lower limit must be below the upper limit.")
    return low, high


def _legend_position(value: Any) -> str:
    if value is True:
        return "best"
    if value is False:
        return "none"
    return _choice(value, LEGEND_POSITIONS, "Legend position")


def _bins(value: Any) -> int | str:
    if value == "auto" and isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_BINS:
        raise ValueError(f"Bins must be 'auto' or a whole number from 1 to {MAX_BINS}.")
    return value


def _number_format(value: Any) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 12 or "{" in value or "}" in value:
        raise ValueError("Number format must be a short format such as .2f.")
    try:
        sample = format(-1234.5678, value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Number format {value!r} does not format numbers (try .2f or .3f)."
        ) from None
    if not any(character.isdigit() for character in sample):
        raise ValueError(f"Number format {value!r} shows no digits.")
    return value


def _font_name(value: Any) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 80
            or any(not character.isprintable() for character in value)):
        raise ValueError("Font family must be a font name (1–80 characters).")
    return value.strip()


def _order(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError(f"{label} must be a list of category labels.")
    items = tuple(value)
    if any(not isinstance(item, str) for item in items):
        raise ValueError(f"{label} must contain text labels.")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} lists a category twice.")
    return items


def _units(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        items = list(value.items())
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        items = list(value)
    else:
        raise ValueError("Units must map variable names to unit names.")
    units: dict[str, str] = {}
    for item in items:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("Units must map variable names to unit names.")
        variable = _name(item[0], "Unit variable")
        unit = _text(item[1], "Unit", 40).strip()
        if unit:
            units[variable] = unit
    return tuple(sorted(units.items()))


@dataclass(frozen=True)
class ChartSpec:
    """Everything that defines one chart; immutable and JSON-serialisable.

    Values are validated (and lists normalised to tuples) on construction, so
    an invalid setting fails early with a clear ``ValueError``. Fields listed
    in :data:`PRESENTATION_FIELDS` only change the look of the chart.

    ``variables`` are the plotted columns. Per kind: histogram, frequency
    polygon, boxplot, violin and Q–Q take one or more; scatter takes x and y;
    heatmap two or more; line takes an ordered x followed by one or more y;
    faceted takes one (histograms) or more (boxplots). ``group`` splits a
    chart by a categorical column. ``x_order`` orders text categories of a
    line chart's x; ``group_order`` orders groups on screen. ``units`` maps
    variables to declared units (used for the comparability warning and axis
    labels). ``note`` replaces the automatic APA note; ``figure_number`` adds
    "Figure N" above an APA-style title.
    """

    kind: str = "histogram"
    variables: tuple[str, ...] = ()
    group: str | None = None
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    legend: str = "best"
    palette: str = DEFAULT_PALETTE
    font_family: str = FALLBACK_FONT
    font_size: float = 10.0
    width_in: float | None = None
    height_in: float | None = None
    dpi: int = 150
    show_points: bool = False
    show_outliers: bool = True
    grid: bool = True
    x_limits: tuple[float, float] | None = None
    y_limits: tuple[float, float] | None = None
    number_format: str = ".2f"
    apa_style: bool = True
    multibox_layout: str = "single"
    standardize: bool = False
    trend: str = "none"
    density: str = "none"
    bins: int | str = "auto"
    correlation_method: str = "pearson"
    bandwidth: str = "scott"
    facet_kind: str = "histogram"
    x_order: tuple[str, ...] = ()
    group_order: tuple[str, ...] = ()
    units: tuple[tuple[str, str], ...] = ()
    note: str = ""
    figure_number: int | None = None

    def __post_init__(self) -> None:
        def put(name: str, value: Any) -> None:
            object.__setattr__(self, name, value)

        put("kind", _choice(self.kind, KINDS, "Chart kind"))
        variables = _names(self.variables, "Variables")
        if len(set(variables)) != len(variables):
            raise ValueError("Choose each variable only once.")
        if len(variables) > MAX_VARIABLES:
            raise ValueError(f"Choose at most {MAX_VARIABLES} variables for one chart.")
        put("variables", variables)
        if isinstance(self.group, str) and not self.group.strip():
            put("group", None)               # an empty choice means "no group"
        if self.group is not None:
            put("group", _name(self.group, "Group variable"))
            if self.group in variables:
                raise ValueError("The group variable cannot also be a plotted variable.")
        put("title", _text(self.title, "Title", 300))
        put("x_label", _text(self.x_label, "X-axis label", 160))
        put("y_label", _text(self.y_label, "Y-axis label", 160))
        put("legend", _legend_position(self.legend))
        put("palette", _choice(self.palette, tuple(PALETTES), "Palette"))
        put("font_family", _font_name(self.font_family))
        put("font_size", _number(self.font_size, "Font size", 6, 32))
        for name, label in (("width_in", "Width"), ("height_in", "Height")):
            value = getattr(self, name)
            put(name, None if value is None else _number(value, f"{label} (inches)", 2, 40))
        put("dpi", _integer(self.dpi, "Resolution (dpi)", 50, 600))
        for name in ("show_points", "show_outliers", "grid", "apa_style", "standardize"):
            put(name, _flag(getattr(self, name), name.replace("_", " ").capitalize()))
        put("x_limits", _limits(self.x_limits, "X-axis limits"))
        put("y_limits", _limits(self.y_limits, "Y-axis limits"))
        put("number_format", _number_format(self.number_format))
        put("multibox_layout", _choice(self.multibox_layout, MULTIBOX_LAYOUTS, "Layout"))
        put("trend", _choice(self.trend, TRENDS, "Trend"))
        put("density", _choice(self.density, DENSITIES, "Density"))
        put("bins", _bins(self.bins))
        put("correlation_method", _choice(
            self.correlation_method, CORRELATION_METHODS, "Correlation method"))
        put("bandwidth", _choice(self.bandwidth, BANDWIDTH_RULES, "Bandwidth rule"))
        put("facet_kind", _choice(self.facet_kind, FACET_KINDS, "Facet chart"))
        put("x_order", _order(self.x_order, "Category order"))
        put("group_order", _order(self.group_order, "Group order"))
        put("units", _units(self.units))
        put("note", _text(self.note, "Note", 1200))
        if self.figure_number is not None:
            put("figure_number", _integer(self.figure_number, "Figure number", 1, 999))

    def unit(self, variable: str) -> str:
        """The declared unit of a variable, or an empty string."""
        return dict(self.units).get(variable, "")

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON-compatible settings, with a ``version`` field."""
        payload: dict[str, Any] = {"version": SPEC_VERSION}
        for item in fields(self):
            value = getattr(self, item.name)
            if item.name == "units":
                value = dict(value)
            elif isinstance(value, tuple):
                value = list(value)
            payload[item.name] = value
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ChartSpec:
        """Read settings written by :meth:`to_dict`.

        Unknown keys are ignored, so settings saved by a later version load
        with the fields this version knows; every known value is validated.
        """
        if not isinstance(payload, Mapping):
            raise ValueError("Chart settings must be a JSON object.")
        version = payload.get("version", SPEC_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Chart settings have an invalid version.")
        known = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in known})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> ChartSpec:
        return cls.from_dict(json.loads(text))


# --------------------------------------------------------------------------
# Prepared data
# --------------------------------------------------------------------------

def _stored(column: np.ndarray) -> tuple[float | None, ...]:
    return tuple(None if math.isnan(value) else value for value in column.tolist())


def _stored_value(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{label} must contain numbers or empty values.")
    number = float(value)
    if math.isnan(number):
        return None
    if not math.isfinite(number):
        raise ValueError(f"{label} must not contain infinite values.")
    return number


@dataclass(frozen=True)
class CorrelationTable:
    """Correlation coefficients shown by a heatmap, with their pairwise N.

    ``coefficients[i][j]`` is ``None`` where no coefficient exists (too few
    complete pairs or a constant variable). ``pair_counts`` is empty when the
    counts are unknown (supplied coefficients without N). ``supplied`` marks
    coefficients that were passed in rather than computed by :func:`prepare`.
    """

    method: str
    names: tuple[str, ...]
    coefficients: tuple[tuple[float | None, ...], ...]
    pair_counts: tuple[tuple[int, ...], ...] = ()
    supplied: bool = False

    def __post_init__(self) -> None:
        def put(name: str, value: Any) -> None:
            object.__setattr__(self, name, value)

        put("method", _choice(self.method, CORRELATION_METHODS, "Correlation method"))
        names = _names(self.names, "Correlation variables")
        if len(names) < 2 or len(set(names)) != len(names):
            raise ValueError("A correlation matrix needs at least two different variables.")
        put("names", names)
        size = len(names)
        try:
            rows = [[_stored_value(value, "Coefficients") for value in row]
                    for row in self.coefficients]
        except TypeError:
            raise ValueError("Coefficients must be a square table of numbers.") from None
        if len(rows) != size or any(len(row) != size for row in rows):
            raise ValueError("The coefficient matrix must be square, one row per variable.")
        for i in range(size):
            for j in range(size):
                value = rows[i][j]
                if value is not None and abs(value) > 1 + 1e-9:
                    raise ValueError("Correlation coefficients must lie between -1 and 1.")
                mirror = rows[j][i]
                if (value is None) != (mirror is None) or (
                        value is not None and abs(value - mirror) > 1e-9):
                    raise ValueError("The coefficient matrix must be symmetric.")
                if value is not None:
                    rows[i][j] = min(1.0, max(-1.0, value))
        put("coefficients", tuple(tuple(row) for row in rows))
        if self.pair_counts is None or len(self.pair_counts) == 0:
            put("pair_counts", ())
        else:
            counts = np.asarray(self.pair_counts, dtype=float)
            if counts.shape != (size, size):
                raise ValueError("Pair counts must be a square table matching the coefficients.")
            if (not np.all(np.isfinite(counts)) or np.any(counts < 0)
                    or np.any(counts != np.round(counts)) or np.any(counts != counts.T)):
                raise ValueError("Pair counts must be symmetric whole numbers of at least 0.")
            put("pair_counts", tuple(tuple(int(value) for value in row) for row in counts))
        put("supplied", _flag(self.supplied, "Supplied"))

    def matrix(self) -> np.ndarray:
        """Coefficients as a float array with NaN where none exists."""
        return np.array([[np.nan if value is None else value for value in row]
                         for row in self.coefficients], dtype=float)

    def counts(self) -> np.ndarray | None:
        """Pairwise N as an integer array, or ``None`` when unknown."""
        return np.array(self.pair_counts, dtype=int) if self.pair_counts else None

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "names": list(self.names),
                "coefficients": [list(row) for row in self.coefficients],
                "pair_counts": [list(row) for row in self.pair_counts],
                "supplied": self.supplied}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CorrelationTable:
        if not isinstance(payload, Mapping):
            raise ValueError("A correlation table must be a JSON object.")
        return cls(method=payload.get("method"), names=payload.get("names", ()),
                   coefficients=payload.get("coefficients", ()),
                   pair_counts=payload.get("pair_counts", ()),
                   supplied=payload.get("supplied", False))


@dataclass(frozen=True)
class ChartData:
    """The values and statistics one chart is drawn from.

    Immutable and JSON-serialisable (:meth:`to_dict`), so a project can store
    it and redraw several views without the original dataset. ``values`` hold
    one column per variable, aligned by dataset row, with ``None`` for a
    missing value; ``missing`` counts them per variable. ``group_values``
    holds each row's group label (``None`` = missing) and ``group_levels``
    the observed levels in their natural order. For a line chart over text
    categories, the x column stores category positions and ``x_categories``
    their ordered labels. ``correlation`` holds heatmap coefficients; data
    built from supplied coefficients has no values. ``warnings`` are those
    of the specification :func:`prepare` was given (see
    :func:`chart_warnings` for another view of the same data).
    """

    variables: tuple[str, ...]
    values: tuple[tuple[float | None, ...], ...] = ()
    rows: int = 0
    missing: tuple[int, ...] | None = None
    group: str | None = None
    group_values: tuple[str | None, ...] = ()
    group_levels: tuple[str, ...] = ()
    group_missing: int | None = None
    x_categories: tuple[str, ...] = ()
    correlation: CorrelationTable | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        def put(name: str, value: Any) -> None:
            object.__setattr__(self, name, value)

        variables = _names(self.variables, "Variables")
        if not variables or len(set(variables)) != len(variables):
            raise ValueError("Chart data needs one or more different variables.")
        put("variables", variables)
        rows = _integer(self.rows, "Rows", 0, 10**9)
        put("rows", rows)
        columns = tuple(
            tuple(_stored_value(value, "Values") for value in column)
            for column in self.values
        )
        if columns and len(columns) != len(variables):
            raise ValueError("Chart data needs one value column per variable.")
        if any(len(column) != rows for column in columns):
            raise ValueError("Every value column must have one entry per row.")
        put("values", columns)
        counted = tuple(sum(value is None for value in column) for column in columns)
        if self.missing is not None and tuple(self.missing) != counted:
            raise ValueError("Missing counts do not match the stored values.")
        put("missing", counted)
        if self.group is None:
            if self.group_values or self.group_levels:
                raise ValueError("Group values need a group variable.")
            put("group_values", ())
            put("group_levels", ())
            put("group_missing", 0)
        else:
            put("group", _name(self.group, "Group variable"))
            levels = _order(self.group_levels, "Group levels")
            labels = tuple(None if value is None else str(value) for value in self.group_values)
            if columns and len(labels) != rows:
                raise ValueError("Group values must have one entry per row.")
            if any(label is not None and label not in levels for label in labels):
                raise ValueError("Every group value must be one of the group levels.")
            put("group_levels", levels)
            put("group_values", labels)
            missing_groups = sum(label is None for label in labels)
            if self.group_missing is not None and self.group_missing != missing_groups:
                raise ValueError("The missing group count does not match the group values.")
            put("group_missing", missing_groups)
        categories = _order(self.x_categories, "X categories")
        if categories:
            if not columns:
                raise ValueError("X categories need stored values.")
            if any(value is not None and (value not in range(len(categories)))
                   for value in columns[0]):
                raise ValueError("X category positions must index the x categories.")
        put("x_categories", categories)
        if self.correlation is not None:
            if not isinstance(self.correlation, CorrelationTable):
                raise ValueError("The correlation must be a CorrelationTable.")
            if self.correlation.names != variables:
                raise ValueError("The correlation table must cover the chart variables.")
        if not columns and self.correlation is None:
            raise ValueError("Chart data needs values or a correlation table.")
        if isinstance(self.warnings, str) or not isinstance(self.warnings, Iterable):
            raise ValueError("Warnings must be a list of texts.")
        put("warnings", tuple(_text(item, "Warning", 2000) for item in self.warnings))

    @property
    def has_values(self) -> bool:
        return bool(self.values)

    def column(self, name: str) -> np.ndarray:
        """One variable's stored values as floats with NaN for missing."""
        if not self.values:
            raise ValueError("This chart data holds only a correlation matrix.")
        try:
            position = self.variables.index(name)
        except ValueError:
            raise KeyError(name) from None
        return np.array([np.nan if value is None else value
                         for value in self.values[position]], dtype=float)

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON-compatible data (missing values as null)."""
        return {
            "version": DATA_VERSION,
            "variables": list(self.variables),
            "values": [list(column) for column in self.values],
            "rows": self.rows,
            "missing": list(self.missing or ()),
            "group": self.group,
            "group_values": list(self.group_values),
            "group_levels": list(self.group_levels),
            "group_missing": self.group_missing,
            "x_categories": list(self.x_categories),
            "correlation": None if self.correlation is None else self.correlation.to_dict(),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ChartData:
        """Read data written by :meth:`to_dict` (validated; unknown keys ignored)."""
        if not isinstance(payload, Mapping):
            raise ValueError("Chart data must be a JSON object.")
        version = payload.get("version", DATA_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Chart data have an invalid version.")
        correlation = payload.get("correlation")
        return cls(
            variables=payload.get("variables", ()),
            values=payload.get("values", ()),
            rows=payload.get("rows", 0),
            missing=payload.get("missing"),
            group=payload.get("group"),
            group_values=payload.get("group_values", ()),
            group_levels=payload.get("group_levels", ()),
            group_missing=payload.get("group_missing"),
            x_categories=payload.get("x_categories", ()),
            correlation=None if correlation is None else CorrelationTable.from_dict(correlation),
            warnings=payload.get("warnings", ()),
        )


# --------------------------------------------------------------------------
# prepare(): extraction, validation and displayed statistics
# --------------------------------------------------------------------------

@contextmanager
def _quiet() -> Iterator[None]:
    """Keep library warnings out of the console; ours are returned as text."""
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        yield


def _check_shape(spec: ChartSpec) -> None:
    """Refuse variable/group combinations a kind cannot draw."""
    count = len(spec.variables)
    kind = spec.kind
    label = KIND_LABELS[kind]
    if count == 0:
        raise ValueError("Choose at least one variable to plot.")
    if kind in ("histogram", "frequency_polygon", "qq") and spec.group and count > 1:
        raise ValueError(f"{label}: a split by group takes exactly one variable; choose "
                         "one variable, or use small multiples.")
    if kind == "scatter" and count != 2:
        raise ValueError("A scatterplot needs exactly two variables: x, then y.")
    if kind == "heatmap":
        if count < 2:
            raise ValueError("A correlation heatmap needs at least two variables.")
        if spec.group:
            raise ValueError("A correlation heatmap does not use a group variable.")
    if kind == "line":
        if count < 2:
            raise ValueError("A line chart needs an ordered x variable and at least one y variable.")
        if spec.group and count != 2:
            raise ValueError("A line chart split by group takes exactly one y variable.")
    if kind == "multi_boxplot" and spec.multibox_layout == "by_group" and not spec.group:
        raise ValueError("The by-group layout needs a group variable.")
    if kind == "faceted":
        if not spec.group:
            raise ValueError("Small multiples need a group variable: one panel per group level.")
        if spec.facet_kind == "histogram" and count != 1:
            raise ValueError("Faceted histograms show one variable; choose one, or facet "
                             "boxplots instead.")


def _level_label(value: Any) -> str | None:
    """A readable group/category label (1.0 → "1"); None for blank text."""
    if isinstance(value, (bool, np.bool_)):
        return "True" if value else "False"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:g}"
    text = str(value).strip()
    return text or None


def _labels_of(series: pd.Series) -> list[str | None]:
    present = series.notna().to_numpy(dtype=bool)
    raw = series.to_numpy(dtype=object)
    return [_level_label(value) if keep else None for value, keep in zip(raw, present)]


def _natural_key(text: str) -> list[tuple[int, Any]]:
    return [(0, int(part)) if part.isdigit() else (1, part.casefold())
            for part in re.split(r"(\d+)", text) if part]


def _is_temporal(series: pd.Series) -> bool:
    return (pd.api.types.is_datetime64_any_dtype(series.dtype)
            or pd.api.types.is_timedelta64_dtype(series.dtype))


def _as_numbers(series: pd.Series) -> np.ndarray | None:
    """Float copy of a column, or None if a present value is not a number."""
    if isinstance(series.dtype, pd.CategoricalDtype):
        series = series.astype(object)
    if pd.api.types.is_numeric_dtype(series.dtype):
        numeric = series
    else:
        numeric = pd.to_numeric(series, errors="coerce")
    values = np.array(numeric.to_numpy(dtype=float, na_value=np.nan), dtype=float, copy=True)
    present = series.notna().to_numpy(dtype=bool)
    if np.any(present & np.isnan(values)):
        return None
    return values


def _numeric_column(series: pd.Series, name: str) -> np.ndarray:
    if looks_like_identifier(name):
        raise ValueError(f"'{name}' looks like an identifier; identifiers are not "
                         "plotted as measurements.")
    if _is_temporal(series):
        raise ValueError(f"'{name}' holds dates or durations; choose a numeric variable.")
    values = _as_numbers(series)
    if values is None:
        numeric = pd.to_numeric(series.astype(object), errors="coerce").to_numpy()
        present = series.notna().to_numpy(dtype=bool)
        raw = series.to_numpy(dtype=object)
        bad = [str(value) for value, keep, number in zip(raw, present, numeric)
               if keep and pd.isna(number)]
        examples = ", ".join(repr(value) for value in list(dict.fromkeys(bad))[:3])
        raise ValueError(f"'{name}' contains values that are not numbers (for example "
                         f"{examples}); recode them or mark them as missing.")
    if np.isinf(values).any():
        raise ValueError(f"'{name}' contains infinite values, which cannot be plotted.")
    return values


def _line_axis(series: pd.Series, name: str,
               x_order: tuple[str, ...]) -> tuple[np.ndarray, tuple[str, ...]]:
    """The x of a line chart: numbers, or positions of explicitly ordered categories."""
    if _is_temporal(series):
        raise ValueError(f"A line chart cannot use the dates in '{name}' yet; convert them "
                         "to a number (for example days since the start).")
    categorical = isinstance(series.dtype, pd.CategoricalDtype)
    if not categorical:
        numbers = _as_numbers(series)
        if numbers is not None:
            return _numeric_column(series, name), ()
    if x_order:
        order = list(x_order)
    elif categorical and series.cat.ordered:
        order = [label for label in (_level_label(c) for c in series.cat.categories) if label]
    else:
        raise ValueError(
            f"A line chart needs an ordered x axis, but '{name}' holds unordered "
            "categories. Choose a numeric x variable, state the category order "
            "explicitly (x_order) or use ordered categories."
        )
    labels = _labels_of(series)
    observed = {label for label in labels if label is not None}
    unknown = sorted(observed - set(order), key=_natural_key)
    if unknown:
        raise ValueError(f"The category order for '{name}' does not include: "
                         f"{', '.join(unknown[:5])}.")
    categories = tuple(label for label in order if label in observed)
    if not categories:
        raise ValueError(f"'{name}' has no values to place on the x axis.")
    position = {label: float(index) for index, label in enumerate(categories)}
    codes = np.array([np.nan if label is None else position[label] for label in labels],
                     dtype=float)
    return codes, categories


def _group_column(series: pd.Series, name: str) -> tuple[tuple[str | None, ...], tuple[str, ...]]:
    """Each row's group label and the observed levels in natural order."""
    if looks_like_identifier(name):
        raise ValueError(f"'{name}' looks like an identifier; it cannot define groups.")
    labels = _labels_of(series)
    observed = {label for label in labels if label is not None}
    if not observed:
        raise ValueError(f"The group variable '{name}' has no values.")
    if isinstance(series.dtype, pd.CategoricalDtype):
        candidates = [_level_label(category) for category in series.cat.categories]
    elif (pd.api.types.is_numeric_dtype(series.dtype)
          and not pd.api.types.is_bool_dtype(series.dtype)):
        numbers = np.unique(series.dropna().to_numpy(dtype=float))
        candidates = [_level_label(number) for number in numbers]
    elif pd.api.types.is_bool_dtype(series.dtype):
        candidates = ["False", "True"]
    else:
        candidates = sorted(observed, key=_natural_key)
    levels = tuple(dict.fromkeys(label for label in candidates if label in observed))
    if len(levels) != len(observed):     # labels outside the declared categories
        levels += tuple(sorted(observed - set(levels), key=_natural_key))
    if len(levels) > MAX_GROUP_LEVELS:
        raise ValueError(f"'{name}' has {len(levels)} groups; choose a grouping variable "
                         f"with at most {MAX_GROUP_LEVELS} levels.")
    return tuple(labels), levels


def _coefficient(x: np.ndarray, y: np.ndarray, method: str) -> float:
    if method == "pearson":
        return float(stats.pearsonr(x, y).statistic)
    if method == "spearman":
        return float(stats.spearmanr(x, y).statistic)
    return float(stats.kendalltau(x, y).statistic)      # tau-b


def _correlation_table(names: tuple[str, ...], columns: Sequence[np.ndarray],
                       method: str) -> CorrelationTable:
    """Pairwise-complete coefficients (SciPy) and N for every pair."""
    size = len(names)
    coefficients: list[list[float | None]] = [[None] * size for _ in range(size)]
    counts = [[0] * size for _ in range(size)]
    for i in range(size):
        for j in range(i, size):
            keep = ~np.isnan(columns[i]) & ~np.isnan(columns[j])
            n = int(keep.sum())
            counts[i][j] = counts[j][i] = n
            if n < MIN_CORRELATION_N:
                continue
            x, y = columns[i][keep], columns[j][keep]
            if np.ptp(x) == 0 or np.ptp(y) == 0:
                continue
            value = 1.0 if i == j else _coefficient(x, y, method)
            if math.isfinite(value):
                coefficients[i][j] = coefficients[j][i] = value
    return CorrelationTable(method=method, names=names, coefficients=coefficients,
                            pair_counts=counts)


def prepare(spec: ChartSpec, frame: pd.DataFrame) -> ChartData:
    """Extract the columns ``spec`` needs from ``frame`` and return ChartData.

    Only the plotted variables and the group column are read; the DataFrame
    is never modified. Plotted variables must be numeric (a line chart's x may
    instead hold explicitly ordered categories). A heatmap's coefficients are
    computed here, pairwise complete, with SciPy. Raises ``ValueError`` with
    an explanation when the data cannot be drawn as requested.
    """
    if not isinstance(spec, ChartSpec):
        raise TypeError("prepare() needs a ChartSpec.")
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("prepare() needs a pandas DataFrame.")
    _check_shape(spec)
    needed = [*spec.variables, *([spec.group] if spec.group else [])]
    absent = [name for name in needed if name not in frame.columns]
    if absent:
        raise ValueError(f"Not in the dataset: {', '.join(absent)}.")
    repeated = [name for name in needed if int((frame.columns == name).sum()) > 1]
    if repeated:
        raise ValueError(f"Several dataset columns are named {', '.join(repeated)}; "
                         "rename them first.")
    with _quiet():
        columns: list[np.ndarray] = []
        categories: tuple[str, ...] = ()
        for position, name in enumerate(spec.variables):
            if spec.kind == "line" and position == 0:
                column, categories = _line_axis(frame[name], name, spec.x_order)
            else:
                column = _numeric_column(frame[name], name)
            columns.append(column)
        group_values: tuple[str | None, ...] = ()
        levels: tuple[str, ...] = ()
        if spec.group:
            group_values, levels = _group_column(frame[spec.group], spec.group)
        correlation = (_correlation_table(spec.variables, columns, spec.correlation_method)
                       if spec.kind == "heatmap" else None)
    data = ChartData(
        variables=spec.variables,
        values=tuple(_stored(column) for column in columns),
        rows=len(frame),
        group=spec.group,
        group_values=group_values,
        group_levels=levels,
        x_categories=categories,
        correlation=correlation,
    )
    return replace(data, warnings=chart_warnings(spec, data))


def correlation_chart_data(names: Sequence[str], coefficients: Any,
                           pair_counts: Any = None, *,
                           method: str = "pearson") -> ChartData:
    """ChartData for a heatmap of coefficients computed elsewhere.

    ``coefficients`` is a square table (NaN or None where undefined), for
    example ``CorrelationMatrixResult.coefficients``; ``pair_counts`` the
    matching pairwise N, or None if unknown. Nothing is recomputed.
    """
    table = CorrelationTable(method=method, names=names, coefficients=coefficients,
                             pair_counts=() if pair_counts is None else pair_counts,
                             supplied=True)
    data = ChartData(variables=table.names, correlation=table)
    spec = ChartSpec(kind="heatmap", variables=table.names, correlation_method=table.method)
    return replace(data, warnings=chart_warnings(spec, data))


# --------------------------------------------------------------------------
# Drawing state shared by warnings, descriptions and rendering
# --------------------------------------------------------------------------

@dataclass(frozen=True, eq=False)
class _Series:
    """One drawn distribution: label on screen, values, palette index, name."""

    label: str
    values: np.ndarray
    color: int
    name: str


class _Context:
    """Arrays and display helpers for one specification/data pair."""

    def __init__(self, spec: ChartSpec, data: ChartData) -> None:
        self.spec = spec
        self.data = data
        self.palette = PALETTES[spec.palette]
        self.rng = np.random.default_rng(JITTER_SEED)
        self._raw = ({name: data.column(name) for name in data.variables}
                     if data.values else {})
        self._shown: dict[str, np.ndarray] = {}
        self._group = (np.array(data.group_values, dtype=object)
                       if data.group_values else None)
        ordered = [level for level in spec.group_order if level in data.group_levels]
        self.levels = tuple(ordered) + tuple(
            level for level in data.group_levels if level not in ordered)

    # colours and markers -------------------------------------------------
    def color(self, index: int) -> str:
        return self.palette.colors[index % len(self.palette.colors)]

    def hatch(self, index: int) -> str | None:
        hatches = self.palette.hatches
        return (hatches[index % len(hatches)] or None) if hatches else None

    def level_color(self, level: str) -> int:
        """Palette index of a group level (fixed by the natural level order)."""
        return self.data.group_levels.index(level)

    # values --------------------------------------------------------------
    def raw(self, name: str) -> np.ndarray:
        return self._raw[name]

    def is_line_x(self, name: str) -> bool:
        return self.spec.kind == "line" and name == self.spec.variables[0]

    def column(self, name: str) -> np.ndarray:
        """A variable as drawn: z-scores when the spec standardizes."""
        if name not in self._shown:
            raw = self._raw[name]
            if self.spec.standardize and not self.is_line_x(name):
                present = raw[~np.isnan(raw)]
                if present.size < 2 or np.ptp(present) == 0:
                    raise ValueError(f"Cannot show '{name}' as z-scores: it needs at "
                                     "least two different values.")
                raw = (raw - present.mean()) / present.std(ddof=1)
            self._shown[name] = raw
        return self._shown[name]

    def in_level(self, level: str) -> np.ndarray:
        if self._group is None:
            return np.zeros(self.data.rows, dtype=bool)
        return np.asarray(self._group == level, dtype=bool)

    def grouped_rows(self) -> np.ndarray:
        if self._group is None:
            return np.zeros(self.data.rows, dtype=bool)
        return np.array([value is not None for value in self._group], dtype=bool)

    def complete(self, *names: str, grouped: bool = False) -> np.ndarray:
        keep = np.ones(self.data.rows, dtype=bool)
        for name in names:
            keep &= ~np.isnan(self._raw[name])
        if grouped:
            keep &= self.grouped_rows()
        return keep

    def available(self, name: str, level: str | None = None) -> np.ndarray:
        keep = ~np.isnan(self._raw[name])
        if level is not None:
            keep &= self.in_level(level)
        return self.column(name)[keep]

    def count(self, name: str, level: str | None = None) -> int:
        keep = ~np.isnan(self._raw[name])
        if level is not None:
            keep &= self.in_level(level)
        return int(keep.sum())

    # text ----------------------------------------------------------------
    def axis_name(self, name: str, standardized: bool | None = None) -> str:
        if self.spec.standardize if standardized is None else standardized:
            return f"{name} (z-score)"
        unit = self.spec.unit(name)
        return f"{name} ({unit})" if unit else name

    def value_name(self) -> str:
        if self.spec.standardize:
            return "z-score"
        units = {self.spec.unit(name) for name in self.spec.variables}
        return f"Value ({units.pop()})" if len(units) == 1 and "" not in units else "Value"

    def number(self, value: float) -> str:
        return _format_number(value, self.spec.number_format)

    def coefficient(self, value: float) -> str:
        text = self.number(value)
        if self.spec.apa_style:          # APA: no leading zero for values bounded by 1
            if text.startswith("0."):
                return text[1:]
            if text.startswith("-0."):
                return "-" + text[2:]
        return text


def _format_number(value: float, number_format: str) -> str:
    text = format(value, number_format)
    if text.startswith("-"):
        try:
            if float(text[1:].replace(",", "").rstrip("%")) == 0:
                text = text[1:]       # never show "-0.00"
        except ValueError:
            pass
    return text


def _splits_by_group(spec: ChartSpec) -> bool:
    """Whether this view separates rows by the group variable."""
    if not spec.group:
        return False
    return not (spec.kind == "multi_boxplot" and spec.multibox_layout == "single")


def _box_layout(spec: ChartSpec) -> str:
    if spec.kind == "multi_boxplot":
        return spec.multibox_layout
    return "by_group" if spec.group else "single"


def _one_axis_variables(spec: ChartSpec) -> tuple[str, ...]:
    """Variables sharing one value axis in this view (comparability check)."""
    names = spec.variables
    kind = spec.kind
    if kind in ("histogram", "frequency_polygon", "boxplot", "violin"):
        return names if len(names) > 1 else ()
    if kind == "multi_boxplot":
        return names if spec.multibox_layout in ("single", "by_group") and len(names) > 1 else ()
    if kind == "faceted":
        return names if spec.facet_kind == "boxplot" and len(names) > 1 else ()
    if kind == "line":
        return names[1:] if len(names) > 2 else ()
    return ()


def _hist_series(ctx: _Context) -> list[_Series]:
    spec = ctx.spec
    if spec.group:
        name = spec.variables[0]
        return [_Series(level, ctx.available(name, level), ctx.level_color(level),
                        f"{name} ({spec.group} = {level})") for level in ctx.levels]
    return [_Series(name, ctx.available(name), index, name)
            for index, name in enumerate(spec.variables)]


def _level_series(ctx: _Context, name: str) -> list[_Series]:
    group = ctx.spec.group
    return [_Series(level, ctx.available(name, level), ctx.level_color(level),
                    f"{name} ({group} = {level})") for level in ctx.levels]


def _box_series(ctx: _Context, index: int | None) -> list[_Series]:
    """Every box or violin of the view (for warnings and descriptions)."""
    spec = ctx.spec
    layout = _box_layout(spec)
    names = spec.variables
    if layout == "sequential" and index is not None:
        names = (names[index],)
    if layout == "single" or not spec.group:
        return [_Series(name, ctx.available(name), 0, name) for name in names]
    return [item for name in names for item in _level_series(ctx, name)]


def _qq_series(ctx: _Context) -> list[_Series]:
    spec = ctx.spec
    if spec.group:
        return _level_series(ctx, spec.variables[0])
    return [_Series(name, ctx.available(name), index, name)
            for index, name in enumerate(spec.variables)]


def _density_possible(values: np.ndarray) -> bool:
    return values.size >= MIN_DENSITY_N and float(np.ptp(values)) > 0


def _bin_edges(values: np.ndarray, bins: int | str) -> np.ndarray:
    """Equal-width bin edges shared by every series of a histogram.

    ``auto`` follows NumPy's rule (the larger of Sturges and
    Freedman–Diaconis); for whole-number data the width is rounded up to a
    whole number and edges sit halfway between scores, so no bin holds a
    different number of possible values.
    """
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.array([0.0, 1.0])
    low, high = float(values.min()), float(values.max())
    if low == high:
        return np.array([low - 0.5, high + 0.5])
    if isinstance(bins, int):
        return np.histogram_bin_edges(values, bins=bins)
    edges = np.histogram_bin_edges(values, bins="auto")
    if np.all(values == np.round(values)):
        width = max(1.0, float(math.ceil(edges[1] - edges[0] - 1e-9)))
        count = int(math.ceil((high - low + 1.0) / width))
        edges = low - 0.5 + width * np.arange(count + 1)
    if edges.size - 1 > MAX_BINS:
        edges = np.histogram_bin_edges(values, bins=MAX_BINS)
    return edges


# --------------------------------------------------------------------------
# Warnings
# --------------------------------------------------------------------------

STANDARDIZE_WARNING = (
    "Standardized display: values shown as z-scores (each variable centred and "
    "scaled); not the raw scale. Each variable is centred at its mean and divided "
    "by its standard deviation over all of its non-missing values."
)


def _check_compatible(spec: ChartSpec, data: ChartData) -> None:
    """Refuse to draw data prepared for a different selection."""
    if not isinstance(spec, ChartSpec):
        raise TypeError("A ChartSpec is required.")
    if not isinstance(data, ChartData):
        raise TypeError("ChartData from prepare() is required.")
    _check_shape(spec)
    if spec.variables != data.variables:
        raise ValueError("The chart data were prepared for other variables; prepare "
                         "the chart again.")
    if spec.group != data.group:
        raise ValueError("The chart data were prepared with another group variable; "
                         "prepare the chart again.")
    if spec.kind == "heatmap":
        if data.correlation is None:
            raise ValueError("These chart data have no correlation coefficients; prepare "
                             "the chart as a heatmap.")
        if data.correlation.method != spec.correlation_method:
            raise ValueError(f"The stored coefficients are {data.correlation.method}; "
                             f"prepare the chart again for {spec.correlation_method}.")
        return
    if not data.values:
        raise ValueError("These chart data hold only a correlation matrix; they can be "
                         "drawn as a heatmap only.")
    if data.x_categories:
        if spec.kind != "line":
            raise ValueError("The first variable was prepared as ordered categories for a "
                             "line chart; prepare the chart again for this kind.")
        if spec.x_order and tuple(
                label for label in spec.x_order if label in data.x_categories
        ) != data.x_categories:
            raise ValueError("The category order changed; prepare the chart again.")


def _range_warnings(ctx: _Context, names: Sequence[str]) -> list[str]:
    spans = []
    for name in names:
        values = ctx.raw(name)
        values = values[~np.isnan(values)]
        if values.size:
            low, high = float(values.min()), float(values.max())
            if high > low:
                spans.append((high - low, name, low, high))
    if len(spans) < 2:
        return []
    widest, narrowest = max(spans), min(spans)
    if widest[0] <= RANGE_RATIO_LIMIT * narrowest[0]:
        return []
    return [
        f"{widest[1]} (range {widest[2]:g}–{widest[3]:g}) and {narrowest[1]} (range "
        f"{narrowest[2]:g}–{narrowest[3]:g}) differ markedly in range (more than "
        f"{RANGE_RATIO_LIMIT:g} times); the variables are not comparable on one axis; "
        "consider panels or an explicit standardization."
    ]


def _unit_warnings(spec: ChartSpec, names: Sequence[str]) -> list[str]:
    declared = [(name, spec.unit(name)) for name in names if spec.unit(name)]
    if len({unit for _, unit in declared}) < 2:
        return []
    listing = "; ".join(f"{name}: {unit}" for name, unit in declared)
    return [f"The variables have different declared units ({listing}); they are not "
            "comparable on one axis; consider panels."]


def _missing_warnings(ctx: _Context) -> list[str]:
    spec, data = ctx.spec, ctx.data
    rows = data.rows
    grouped = _splits_by_group(spec)
    found = []
    if spec.kind == "scatter":
        x_name, y_name = spec.variables
        n = int(ctx.complete(x_name, y_name, grouped=grouped).sum())
        if n < rows:
            lacking = f"{x_name}, {y_name} or {spec.group}" if grouped else f"{x_name} or {y_name}"
            found.append(f"{rows - n} of {rows} rows lack {lacking} and are left out; "
                         f"the scatterplot shows {n} complete pairs.")
        return found
    if spec.kind == "line":
        x_name = spec.variables[0]
        for y_name in spec.variables[1:]:
            n = int(ctx.complete(x_name, y_name, grouped=grouped).sum())
            if n < rows:
                found.append(f"The line for {y_name} uses {n} of {rows} rows; rows lacking "
                             f"{x_name}, {y_name}{' or ' + spec.group if grouped else ''} "
                             "are left out.")
        return found
    parts = [f"{name} {count} of {rows}" for name, count in zip(data.variables, data.missing)
             if count]
    if parts:
        found.append("Missing values left out (available cases): " + ", ".join(parts) + ".")
    if grouped and data.group_missing:
        found.append(f"{data.group_missing} of {rows} rows have no {spec.group} value and are "
                     "left out of the grouped display.")
    return found


def _level_sizes(ctx: _Context) -> dict[str, int]:
    spec = ctx.spec
    sizes = {}
    for level in ctx.levels:
        member = ctx.in_level(level)
        if spec.kind == "scatter":
            sizes[level] = int((ctx.complete(*spec.variables) & member).sum())
        elif spec.kind == "line":
            sizes[level] = int((ctx.complete(*spec.variables[:2]) & member).sum())
        else:
            sizes[level] = min(ctx.count(name, level) for name in spec.variables)
    return sizes


def _group_warnings(ctx: _Context) -> list[str]:
    spec = ctx.spec
    found = []
    if spec.group and spec.kind == "multi_boxplot" and spec.multibox_layout == "single":
        found.append(f"The single-axis layout does not split by {spec.group}; choose the "
                     "by-group layout to compare its groups.")
    if not _splits_by_group(spec):
        return found
    sizes = _level_sizes(ctx)
    small = [f"{level} (n = {n})" for level, n in sizes.items() if 0 < n < SMALL_GROUP_N]
    if small:
        found.append(f"Small groups of {spec.group}: {', '.join(small)}. Summaries of fewer "
                     f"than {SMALL_GROUP_N} observations are unstable; consider showing the "
                     "individual points.")
    empty = [level for level, n in sizes.items() if n == 0]
    if empty:
        found.append(f"No complete observations for {spec.group} = {', '.join(empty)}; "
                     "those boxes, lines or panels stay empty.")
    return found


def _density_warnings(series: Sequence[_Series], noun: str, consequence: str) -> list[str]:
    found = []
    for item in series:
        if item.values.size < MIN_DENSITY_N:
            found.append(f"No {noun} for {item.name}: fewer than {MIN_DENSITY_N} "
                         f"observations (n = {item.values.size}){consequence}.")
        elif float(np.ptp(item.values)) == 0:
            found.append(f"No {noun} for {item.name}: all of its values are equal"
                         f"{consequence}.")
    return found


def _drawing_warnings(ctx: _Context) -> list[str]:
    spec = ctx.spec
    kind = spec.kind
    found: list[str] = []
    if spec.density != "none" and (kind in ("histogram", "frequency_polygon") or (
            kind == "faceted" and spec.facet_kind == "histogram")):
        series = (_level_series(ctx, spec.variables[0]) if kind == "faceted"
                  else _hist_series(ctx))
        found += _density_warnings(series, "density curve", "")
    if kind == "violin":
        found += _density_warnings(_box_series(ctx, None), "violin",
                                   "; its median and quartiles are shown")
    if kind == "qq":
        for item in _qq_series(ctx):
            if item.values.size < MIN_QQ_N:
                found.append(f"No Q–Q plot for {item.name}: fewer than {MIN_QQ_N} "
                             f"observations (n = {item.values.size}).")
    if kind == "scatter" and spec.trend != "none":
        x_name, y_name = spec.variables
        keep = ctx.complete(x_name, y_name, grouped=_splits_by_group(spec))
        n = int(keep.sum())
        label = TREND_LABELS[spec.trend]
        if n < MIN_TREND_N[spec.trend]:
            found.append(f"No {label}: fewer than {MIN_TREND_N[spec.trend]} complete pairs "
                         f"(n = {n}).")
        elif float(np.ptp(ctx.raw(x_name)[keep])) == 0:
            found.append(f"No {label}: {x_name} has no variation.")
    return found


def _heatmap_warnings(table: CorrelationTable) -> list[str]:
    found = []
    names = table.names
    size = len(names)
    counts = table.counts()
    if counts is not None:
        off_diagonal = {int(counts[i, j]) for i in range(size) for j in range(i + 1, size)}
        if len(off_diagonal) > 1:
            found.append(f"Pairwise-complete N varies from {min(off_diagonal)} to "
                         f"{max(off_diagonal)}; each cell states its N.")
    undefined = [f"{names[i]} and {names[j]}" for i in range(size) for j in range(i + 1, size)
                 if table.coefficients[i][j] is None]
    if undefined:
        listing = "; ".join(undefined[:6])
        if len(undefined) > 6:
            listing += f"; and {len(undefined) - 6} more pairs"
        reason = ("not available in the supplied matrix" if table.supplied else
                  f"fewer than {MIN_CORRELATION_N} complete pairs or a variable without "
                  "variation")
        found.append(f"No coefficient for {listing}: {reason}; shown as N/A.")
    return found


def chart_warnings(spec: ChartSpec, data: ChartData) -> tuple[str, ...]:
    """Warnings for drawing ``data`` as ``spec`` describes (returned, never printed).

    Computed from the stored data only, so a view can be re-checked after a
    change of kind or layout without the dataset. :func:`prepare` stores the
    warnings of the specification it was given in ``ChartData.warnings``.
    Raises ``ValueError`` when the data cannot be drawn this way (including a
    z-transformation of a variable without variation).
    """
    _check_compatible(spec, data)
    found: list[str] = []
    with _quiet():
        if spec.kind == "heatmap":
            if spec.standardize:
                found.append("Standardization does not change correlation coefficients; "
                             "the heatmap ignores it.")
            found += _heatmap_warnings(data.correlation)
        else:
            # Natural group order: the on-screen order is presentation only.
            ctx = _Context(replace(spec, group_order=()), data)
            if spec.standardize:
                for name in spec.variables:
                    ctx.column(name)            # raises when z-scores are undefined
                found.append(STANDARDIZE_WARNING)
            else:
                shared = _one_axis_variables(spec)
                found += _range_warnings(ctx, shared)
                found += _unit_warnings(spec, shared)
            found += _missing_warnings(ctx)
            found += _group_warnings(ctx)
            found += _drawing_warnings(ctx)
    return tuple(dict.fromkeys(found))


# --------------------------------------------------------------------------
# Titles, notes and alt text
# --------------------------------------------------------------------------

def figure_count(spec: ChartSpec, data: ChartData) -> int:
    """Number of figures: one per variable for the sequential layout, else 1."""
    _check_compatible(spec, data)
    if spec.kind == "multi_boxplot" and spec.multibox_layout == "sequential":
        return len(spec.variables)
    return 1


def _check_index(index: Any, count: int) -> int:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count:
        raise ValueError(f"Figure index must be a whole number from 0 to {count - 1}.")
    return index


def _listing(names: Sequence[str], limit: int = 12) -> str:
    items = list(names[:limit])
    if len(names) > limit:
        items.append(f"{len(names) - limit} more")
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _counts_phrase(series: Sequence[_Series]) -> str:
    sizes = {item.values.size for item in series}
    if len(series) == 1:
        return f"{series[0].label} (n = {series[0].values.size})"
    if len(sizes) == 1:
        return f"{_listing([item.label for item in series])} (n = {sizes.pop()} each)"
    return ", ".join(f"{item.label} (n = {item.values.size})" for item in series)


def _default_title(spec: ChartSpec, index: int | None) -> str:
    names = spec.variables
    count = len(names)
    group = spec.group
    by = f" by {group}" if group and _splits_by_group(spec) else ""
    subject = names[0] if count == 1 else f"{count} Variables"
    kind = spec.kind
    if kind == "histogram":
        return f"{'Distribution' if count == 1 else 'Distributions'} of {subject}{by}"
    if kind == "frequency_polygon":
        return f"Frequency {'Polygon' if count == 1 and not group else 'Polygons'} of {subject}{by}"
    if kind in ("boxplot", "violin", "multi_boxplot"):
        noun = "Violin Plot" if kind == "violin" else "Boxplot"
        if kind == "multi_boxplot" and spec.multibox_layout == "sequential":
            if index is None:
                return f"{noun}s of {count} Variables{by}, One Figure Each"
            return f"{noun} of {names[index]}{by} ({index + 1} of {count})"
        plural = noun if count == 1 and not group else f"{noun}s"
        return f"{plural} of {subject}{by}"
    if kind == "scatter":
        return f"Scatterplot of {names[1]} Against {names[0]}{by}"
    if kind == "heatmap":
        method = spec.correlation_method.capitalize()
        return f"{method} Correlations Among {count} Variables"
    if kind == "qq":
        return f"Normal Q–Q {'Plot' if count == 1 and not group else 'Plots'} of {subject}{by}"
    if kind == "line":
        ys = names[1:]
        target = f"Mean {ys[0]}" if len(ys) == 1 else f"Means of {len(ys)} Variables"
        return f"{target} Across {names[0]}{by}"
    if spec.facet_kind == "histogram":
        return f"Distribution of {names[0]} by {group}"
    return f"Boxplots of {subject} by {group}"


def _display_title(spec: ChartSpec, index: int | None) -> str:
    custom = " ".join(spec.title.split())
    if not custom:
        return _default_title(spec, index)
    if spec.kind == "multi_boxplot" and spec.multibox_layout == "sequential" and index is not None:
        return f"{custom}: {spec.variables[index]}"
    return custom


def _density_sentence(spec: ChartSpec) -> str:
    if spec.density == "kde":
        return (f"Curves are Gaussian kernel density estimates ({spec.bandwidth.capitalize()}’s "
                "rule bandwidth) scaled to counts.")
    if spec.density == "normal":
        return ("Curves are normal distributions with the sample mean and SD, scaled to "
                "counts.")
    return ""


def _hist_sentences(ctx: _Context, alt: bool) -> list[str]:
    spec = ctx.spec
    series = _hist_series(ctx)
    edges = _bin_edges(np.concatenate([item.values for item in series]), spec.bins)
    width = ctx.number(float(edges[1] - edges[0]))
    polygon = spec.kind == "frequency_polygon"
    sentences = []
    if alt:
        noun = "frequency polygon" if polygon else "histogram"
        if len(series) == 1:
            first = f"{noun.capitalize()} of {series[0].name} (N = {series[0].values.size})"
        elif spec.group:
            first = (f"Overlaid {noun}s of {spec.variables[0]} for each level of {spec.group}: "
                     f"{_counts_phrase(series)}")
        else:
            first = (f"Overlaid {noun}s of {len(series)} variables on one axis: "
                     f"{_counts_phrase(series)}")
        sentences.append(f"{first}; {edges.size - 1} bins of width {width}.")
    else:
        sentences.append(f"Bins of width {width} from {ctx.number(float(edges[0]))} to "
                         f"{ctx.number(float(edges[-1]))}.")
    if polygon:
        sentences.append("Points mark the count of each bin at its midpoint; the polygon "
                         "is closed at zero one bin beyond each end.")
    if spec.density != "none":
        sentences.append(_density_sentence(spec))
    return sentences


def _box_sentences(ctx: _Context, index: int | None, alt: bool) -> list[str]:
    spec = ctx.spec
    violin = spec.kind == "violin"
    noun = "violin plot" if violin else "boxplot"
    layout = _box_layout(spec)
    names = spec.variables
    group = spec.group
    sentences = []
    if alt:
        if layout == "sequential" and index is None:
            text = (f"A sequence of {len(names)} figures, one {noun} per variable: "
                    f"{_listing(names)}" + (f", each split by {group}" if group else ""))
        elif layout == "sequential":
            series = _box_series(ctx, index)
            text = (f"Figure {index + 1} of {len(names)}: {noun} of {names[index]}"
                    + (f" for each level of {group}: {_counts_phrase(series)}" if group
                       else f" (N = {series[0].values.size})"))
        elif layout == "panels":
            series = [_Series(name, ctx.available(name), 0, name) for name in names]
            text = (f"{noun.capitalize()}s in {len(names)} panels, one per variable: "
                    f"{_counts_phrase(series)}" + (f"; each panel split by {group}" if group
                                                   else ""))
        elif layout == "by_group" and len(names) == 1:
            text = (f"{noun.capitalize()}s of {names[0]} for each level of {group}: "
                    f"{_counts_phrase(_level_series(ctx, names[0]))}")
        elif layout == "by_group":
            text = (f"{noun.capitalize()}s of {len(names)} variables on one axis, each split "
                    f"by {group} ({_listing(ctx.levels)}): {_listing(names)}")
        elif len(names) == 1:
            text = f"{noun.capitalize()} of {names[0]} (N = {ctx.available(names[0]).size})"
        else:
            series = [_Series(name, ctx.available(name), 0, name) for name in names]
            text = (f"{noun.capitalize()}s of {len(names)} variables on one axis: "
                    f"{_counts_phrase(series)}")
        sentences.append(text + ".")
    if violin:
        sentences.append(f"Violins are Gaussian kernel density estimates "
                         f"({spec.bandwidth.capitalize()}’s rule) cut at the observed range; "
                         "the bar marks the interquartile range and the dot the median.")
    else:
        sentences.append("Boxes show the median and interquartile range; whiskers reach the "
                         "most extreme values within 1.5 × IQR"
                         + ("; circles mark values beyond them." if spec.show_outliers else "."))
    if spec.show_points:
        sentences.append("Dots are individual observations; their horizontal jitter is for "
                         "display only.")
    return sentences


def _scatter_sentences(ctx: _Context, alt: bool) -> list[str]:
    spec = ctx.spec
    x_name, y_name = spec.variables
    keep = ctx.complete(x_name, y_name, grouped=_splits_by_group(spec))
    n = int(keep.sum())
    sentences = []
    if alt:
        sentences.append(f"Scatterplot of {y_name} (vertical axis) against {x_name} "
                         f"(horizontal axis) for {n} complete pairs"
                         + (f", coloured and shaped by {spec.group}" if spec.group else "") + ".")
    else:
        sentences.append("Each point is one complete pair of values.")
    drawn = (spec.trend != "none" and n >= MIN_TREND_N[spec.trend]
             and float(np.ptp(ctx.raw(x_name)[keep])) > 0)
    if drawn and spec.trend == "ols":
        sentences.append("The line is an ordinary least-squares fit to all points with a 95% "
                         "confidence band for the fitted mean; it describes association, "
                         "not causation.")
    elif drawn:
        interpolated = (f"; fits within 1% of the x range are interpolated above "
                        f"{LOWESS_EXACT_N} points" if n > LOWESS_EXACT_N else "")
        sentences.append(f"The curve is a LOWESS smoother of all points (fraction "
                         f"{LOWESS_FRACTION:.2f}, {LOWESS_ITERATIONS} robustness iterations"
                         f"{interpolated}); it is descriptive only.")
    return sentences


def _heatmap_sentences(spec: ChartSpec, table: CorrelationTable, alt: bool) -> list[str]:
    names = table.names
    size = len(names)
    label = METHOD_LABELS[table.method]
    counts = table.counts()
    if counts is None:
        n_text = "pairwise N not supplied"
    else:
        off = sorted({int(counts[i, j]) for i in range(size) for j in range(i + 1, size)})
        n_text = (f"pairwise-complete N = {off[0]} for every pair" if len(off) == 1
                  else f"pairwise-complete N from {off[0]} to {off[-1]}, stated per cell")
    sentences = []
    if alt:
        sentences.append(f"Correlation heatmap of {size} variables ({_listing(names)}) showing "
                         f"{label} for each pair; {n_text}.")
        values = [table.coefficients[i][j] for i in range(size) for j in range(i + 1, size)
                  if table.coefficients[i][j] is not None]
        if values:
            low = _format_number(min(values), spec.number_format)
            high = _format_number(max(values), spec.number_format)
            sentences.append(f"Coefficients range from {low} to {high}.")
    else:
        sentences.append(f"Cells show {label} with {n_text}. No significance tests are shown; "
                         "correlations do not establish causation.")
        if table.supplied:
            sentences.append("Coefficients are taken from the analysis result.")
    return sentences


def _qq_sentences(ctx: _Context, alt: bool) -> list[str]:
    series = _qq_series(ctx)
    sentences = []
    if alt:
        if len(series) == 1:
            sentences.append(f"Normal Q–Q plot of {series[0].name} "
                             f"(N = {series[0].values.size}).")
        else:
            unit = (f"level of {ctx.spec.group}" if ctx.spec.group else "variable")
            sentences.append(f"Normal Q–Q plots in {len(series)} panels, one per {unit}: "
                             f"{_counts_phrase(series)}.")
    sentences.append("Points compare the ordered observations with standard normal quantiles; "
                     "the dashed line is a least-squares fit. Points close to the line are "
                     "consistent with a normal distribution.")
    return sentences


def _line_sentences(ctx: _Context, alt: bool) -> list[str]:
    spec, data = ctx.spec, ctx.data
    x_name, ys = spec.variables[0], spec.variables[1:]
    x = ctx.raw(x_name)
    positions = np.unique(x[~np.isnan(x)]).size
    sentences = []
    if alt:
        if spec.group:
            text = (f"Line chart of the mean of {ys[0]} at each of {positions} ordered values "
                    f"of {x_name}, one line per level of {spec.group} ({_listing(ctx.levels)})")
        elif len(ys) == 1:
            text = f"Line chart of the mean of {ys[0]} at each of {positions} ordered values of {x_name}"
        else:
            text = (f"Line chart of the means of {len(ys)} variables ({_listing(ys)}) at each "
                    f"of {positions} ordered values of {x_name}")
        if data.x_categories:
            text += f" (order: {_listing(data.x_categories)})"
        sentences.append(text + ".")
    sentences.append("Points are means of the y variable at each x value; lines connect "
                     "consecutive x values.")
    if spec.show_points:
        sentences.append("Small dots are individual observations.")
    return sentences


def _faceted_sentences(ctx: _Context, alt: bool) -> list[str]:
    spec = ctx.spec
    name = spec.variables[0]
    sentences = []
    if spec.facet_kind == "histogram":
        series = _level_series(ctx, name)
        if alt:
            sentences.append(f"Small multiples: one histogram of {name} per level of "
                             f"{spec.group} ({_counts_phrase(series)}), with shared axes.")
        edges = _bin_edges(np.concatenate([item.values for item in series]), spec.bins)
        sentences.append(f"All panels share bins of width {ctx.number(float(edges[1] - edges[0]))}.")
        if spec.density != "none":
            sentences.append(_density_sentence(spec))
    else:
        if alt:
            sentences.append(f"Small multiples: boxplots of {_listing(spec.variables)} in one "
                             f"panel per level of {spec.group} ({_listing(ctx.levels)}), with a "
                             "shared value axis.")
        sentences.append("Boxes show the median and interquartile range; whiskers reach the "
                         "most extreme values within 1.5 × IQR.")
    return sentences


def _sample_sentence(ctx: _Context, index: int | None) -> str:
    """N of the figure; the kind's case-handling rule when rows were left out."""
    spec, data = ctx.spec, ctx.data
    rows = data.rows
    grouped = _splits_by_group(spec)
    if spec.kind == "scatter":
        sizes = [int(ctx.complete(*spec.variables, grouped=grouped).sum())]
        text = f"N = {sizes[0]} complete pairs"
    elif spec.kind == "line":
        sizes = sorted({int(ctx.complete(spec.variables[0], name, grouped=grouped).sum())
                        for name in spec.variables[1:]})
        text = (f"N = {sizes[0]} complete rows" if len(sizes) == 1 else
                f"N = {sizes[0]}–{sizes[-1]} complete rows per line")
    else:
        names = spec.variables
        if spec.kind == "multi_boxplot" and spec.multibox_layout == "sequential" \
                and index is not None:
            names = (names[index],)
        sizes = sorted({ctx.count(name) for name in names})
        text = (f"N = {sizes[0]}" if len(sizes) == 1 else
                f"N = {sizes[0]}–{sizes[-1]} per variable")
    sentence = text + (f" of {rows} rows." if sizes[0] < rows else ".")
    if sizes[0] < rows or (grouped and data.group_missing):
        sentence += " " + CASE_HANDLING[spec.kind]
    return sentence


def _sentences(ctx: _Context, index: int | None, alt: bool) -> list[str]:
    kind = ctx.spec.kind
    if kind in ("histogram", "frequency_polygon"):
        return _hist_sentences(ctx, alt)
    if kind in ("boxplot", "violin", "multi_boxplot"):
        return _box_sentences(ctx, index, alt)
    if kind == "scatter":
        return _scatter_sentences(ctx, alt)
    if kind == "qq":
        return _qq_sentences(ctx, alt)
    if kind == "line":
        return _line_sentences(ctx, alt)
    return _faceted_sentences(ctx, alt)


def _note_text(spec: ChartSpec, data: ChartData, index: int | None) -> str:
    """The figure note: the user's note, or an automatic APA note."""
    custom = spec.note.strip()
    if not custom and not spec.apa_style:
        return ""
    if custom:
        body = custom
    elif spec.kind == "heatmap":
        body = " ".join(_heatmap_sentences(spec, data.correlation, alt=False))
    else:
        ctx = _Context(spec, data)
        parts = [_sample_sentence(ctx, index), *_sentences(ctx, index, alt=False)]
        if spec.standardize:
            parts.append("Values shown as z-scores (each variable centred and scaled); not "
                         "the raw scale.")
        body = " ".join(part for part in parts if part)
    if spec.apa_style and not body.startswith("Note."):
        body = "Note. " + body
    return body


def describe(spec: ChartSpec, data: ChartData, index: int | None = None) -> str:
    """Alt text for screen readers: the figure title and what the chart shows.

    ``index`` selects one figure of a sequential layout; ``None`` describes
    the whole chart (for the sequential layout, the whole sequence).
    """
    count = figure_count(spec, data)
    if index is not None:
        _check_index(index, count)
    elif count == 1:
        index = 0
    with _quiet():
        title = _display_title(spec, index)
        if spec.kind == "heatmap":
            body = _heatmap_sentences(spec, data.correlation, alt=True)
        else:
            ctx = _Context(spec, data)
            body = _sentences(ctx, index, alt=True)
            if spec.standardize:
                body.append("Values are shown as z-scores (each variable centred and "
                            "scaled), not on the raw scale.")
    return " ".join([title.rstrip(".") + ".", *[part for part in body if part]])


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

@lru_cache(maxsize=64)
def resolved_font(family: str) -> str:
    """The font family actually used: ``family`` if installed, else DejaVu Sans.

    The lookup never logs; the fallback is silent, so the user interface can
    call this to tell the user which font a chart will use.
    """
    try:
        font_manager.findfont(font_manager.FontProperties(family=[family]),
                              fallback_to_default=False)
    except ValueError:
        return FALLBACK_FONT
    return family


def _rc_params(spec: ChartSpec) -> dict[str, Any]:
    size = spec.font_size
    family = resolved_font(spec.font_family)
    apa = spec.apa_style
    return {
        # DejaVu Sans stays as a fallback for glyphs (Cyrillic, Latvian) missing in a font.
        "font.family": list(dict.fromkeys([family, FALLBACK_FONT])),
        "font.size": size,
        "axes.titlesize": size + 0.5,
        "axes.labelsize": size,
        "xtick.labelsize": max(5.0, size - 1),
        "ytick.labelsize": max(5.0, size - 1),
        "legend.fontsize": max(5.0, size - 1),
        "legend.title_fontsize": max(5.0, size - 0.5),
        "legend.frameon": not apa,
        "text.parse_math": False,          # "$" and "_" in names stay literal text
        "text.color": "black",
        "axes.labelcolor": "black",
        "axes.edgecolor": "black" if apa else "#333333",
        "axes.linewidth": 0.8,
        "axes.spines.top": not apa,
        "axes.spines.right": not apa,
        "axes.facecolor": "white",
        "axes.prop_cycle": cycler(color=list(PALETTES[spec.palette].colors)),
        "xtick.color": "black",
        "ytick.color": "black",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.hashsalt": SVG_HASH_SALT,
        "svg.fonttype": "path",
        "pdf.fonttype": 42,
    }


@contextmanager
def _render_context(spec: ChartSpec) -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(_quiet())
        stack.enter_context(matplotlib.rc_context(_rc_params(spec)))
        yield


def _wrap(text: str, width_in: float, size: float) -> list[str]:
    characters = max(24, int(width_in * 72 * 0.94 / (size * 0.56)))
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, characters) or [""])
    return lines


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _figure(ctx: _Context, title: str, note: str, plot_size: tuple[float, float]) -> Figure:
    """A figure with a title block on top, a note block below and the plot between."""
    spec = ctx.spec
    width = spec.width_in or plot_size[0]
    title_size = spec.font_size + 1.0
    note_size = max(6.0, spec.font_size - 1.5)
    header: list[tuple[str, str, str]] = []
    if spec.apa_style and spec.figure_number is not None:
        header.append((f"Figure {spec.figure_number}", "bold", "normal"))
    for line in _wrap(title, width - 0.3, title_size):
        header.append((line, "normal", "italic") if spec.apa_style else (line, "bold", "normal"))
    note_lines = _wrap(note, width - 0.3, note_size) if note else []
    header_height = 0.18 + len(header) * title_size * _LINE_HEIGHT / 72
    note_height = (0.18 + len(note_lines) * note_size * _LINE_HEIGHT / 72) if note_lines else 0.06
    height = spec.height_in or (plot_size[1] + header_height + note_height)
    bottom, top = note_height / height, 1 - header_height / height
    if top - bottom < 0.2:
        raise ValueError("The figure is too small for its title and note; make it taller or "
                         "shorten the text.")
    figure = Figure(figsize=(width, height), dpi=spec.dpi, layout="constrained",
                    facecolor="white")
    figure.get_layout_engine().set(rect=(0.0, bottom, 1.0, top - bottom))
    left = 0.15 / width
    x, align = (left, "left") if spec.apa_style else (0.5, "center")
    y = 1 - 0.12 / height
    for text, weight, style in header:
        figure.text(x, y, text, ha=align, va="top", fontsize=title_size, fontweight=weight,
                    fontstyle=style)
        y -= title_size * _LINE_HEIGHT / 72 / height
    if note_lines:
        figure.text(left, (note_height - 0.10) / height, "\n".join(note_lines), ha="left",
                    va="top", fontsize=note_size, linespacing=_LINE_HEIGHT)
    return figure


def _panel_columns(count: int) -> int:
    if count <= 3:
        return count
    if count == 4:
        return 2
    return 3 if count <= 9 else 4


def _panel_size(count: int) -> tuple[float, float]:
    columns = _panel_columns(count)
    rows = math.ceil(count / columns)
    return _clamp(2.9 * columns + 0.5, 4.8, 13.0), 2.5 * rows + 0.4


def _panel_axes(figure: Figure, count: int) -> tuple[list[Axes], int]:
    columns = _panel_columns(count)
    grid = figure.subplots(math.ceil(count / columns), columns, squeeze=False)
    axes = list(grid.ravel())
    for extra in axes[count:]:
        extra.remove()
    return axes[:count], columns


def _label_panels(axes: Sequence[Axes], columns: int, x_text: str, y_text: str) -> None:
    for position, ax in enumerate(axes):
        if position + columns >= len(axes):
            ax.set_xlabel(x_text)
        if position % columns == 0:
            ax.set_ylabel(y_text)


def _share_limits(axes: Sequence[Axes], *, x: bool, y: bool) -> None:
    if x:
        lows, highs = zip(*(ax.get_xlim() for ax in axes))
        for ax in axes:
            ax.set_xlim(min(lows), max(highs))
    if y:
        lows, highs = zip(*(ax.get_ylim() for ax in axes))
        for ax in axes:
            ax.set_ylim(min(lows), max(highs))


def _finish_axes(ax: Axes, ctx: _Context, grid: str | None, *,
                 x_limits: bool = True, y_limits: bool = True) -> None:
    spec = ctx.spec
    if spec.grid and grid:
        ax.grid(True, axis=grid, color="#D9D9D9", linewidth=0.6)
        ax.set_axisbelow(True)
    else:
        ax.grid(False)
    if x_limits and spec.x_limits:
        ax.set_xlim(spec.x_limits)
    if y_limits and spec.y_limits:
        ax.set_ylim(spec.y_limits)


def _legend_outside(spec: ChartSpec, entries: int, long_labels: bool,
                    prefer_outside: bool = False) -> bool:
    """Whether the legend goes to the right of the axes rather than over the data."""
    if spec.legend == "outside":
        return True
    return spec.legend == "best" and (prefer_outside or entries > 3
                                      or (entries > 2 and long_labels))


def _legend_room(spec: ChartSpec, entries: int, *, long_labels: bool = False,
                 prefer_outside: bool = False) -> float:
    """Extra automatic figure width (inches) for a legend outside the axes."""
    if (spec.width_in is not None or entries == 0
            or not _legend_outside(spec, entries, long_labels, prefer_outside)):
        return 0.0
    return 2.6 if long_labels else 1.2


def _legend(ax: Axes, spec: ChartSpec, *, handles: Sequence[Any] | None = None,
            title: str | None = None, prefer_outside: bool = False) -> None:
    """Draw the legend; "best" moves outside the axes when it would crowd the data."""
    if spec.legend == "none":
        return
    if handles is None:
        handles, _ = ax.get_legend_handles_labels()
    if not handles:
        return
    location = spec.legend
    long_labels = max(len(str(handle.get_label())) for handle in handles) > 28
    if _legend_outside(spec, len(handles), long_labels, prefer_outside):
        location = "outside"
    options: dict[str, Any] = {"handles": list(handles), "title": title,
                               "frameon": not spec.apa_style}
    if location == "outside":
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0, **options)
    else:
        ax.legend(loc=location, **options)


def _rotate_crowded(ax: Axes, names: Sequence[str]) -> None:
    longest = max((len(name) for name in names), default=0)
    if len(names) > 4 or (len(names) > 1 and longest > 12):
        for label in ax.get_xticklabels():
            label.set_rotation(30)
            label.set_horizontalalignment("right")
            label.set_rotation_mode("anchor")


def _level_handles(ctx: _Context) -> list[Patch]:
    return [Patch(facecolor=to_rgba(ctx.color(ctx.level_color(level)), 0.55),
                  edgecolor="black", hatch=ctx.hatch(ctx.level_color(level)), label=level)
            for level in ctx.levels]


# -- histograms and polygons ------------------------------------------------

def _density_curve(ax: Axes, ctx: _Context, values: np.ndarray, scale: float, color: str,
                   prefix: str | None, linestyle: str) -> None:
    """A KDE or normal curve scaled to histogram counts (n × bin width)."""
    if not _density_possible(values):
        return
    spec = ctx.spec
    sd = float(np.std(values, ddof=1))
    low, high = float(values.min()), float(values.max())
    if spec.density == "kde":
        kde = stats.gaussian_kde(values, bw_method=spec.bandwidth)
        bandwidth = float(kde.factor) * sd
        grid = np.linspace(low - 3 * bandwidth, high + 3 * bandwidth, 256)
        curve = kde(grid) * scale
        text = f"Gaussian KDE ({spec.bandwidth.capitalize()}’s rule, h = {ctx.number(bandwidth)})"
    else:
        mean = float(values.mean())
        grid = np.linspace(min(low, mean - 3 * sd), max(high, mean + 3 * sd), 256)
        curve = stats.norm.pdf(grid, mean, sd) * scale
        text = f"Normal curve (M = {ctx.number(mean)}, SD = {ctx.number(sd)})"
    ax.plot(grid, curve, color=color, linewidth=1.8, linestyle=linestyle,
            label=f"{prefix}: {text}" if prefix else text, zorder=4)


def _draw_hist_axes(ax: Axes, ctx: _Context, series: Sequence[_Series], edges: np.ndarray,
                    *, polygon: bool) -> None:
    spec = ctx.spec
    width = float(edges[1] - edges[0])
    middles = (edges[:-1] + edges[1:]) / 2
    overlay = len(series) > 1
    for position, item in enumerate(series):
        color = ctx.color(item.color)
        counts = np.histogram(item.values, bins=edges)[0]
        density = spec.density != "none" and _density_possible(item.values)
        style = _LINESTYLES[position % len(_LINESTYLES)] if overlay else "-"
        if polygon:
            ax.plot(np.r_[middles[0] - width, middles, middles[-1] + width],
                    np.r_[0, counts, 0], color=color, linewidth=1.6, linestyle=style,
                    marker=_MARKERS[position % len(_MARKERS)], markersize=4,
                    label=item.label if overlay else ("Frequency polygon" if density else None))
        elif overlay:
            ax.stairs(counts, edges, fill=True, facecolor=to_rgba(color, 0.28),
                      edgecolor=color, linewidth=0, hatch=ctx.hatch(item.color))
            ax.stairs(counts, edges, color=color, linewidth=1.5, linestyle=style,
                      label=item.label)
        else:
            ax.bar(edges[:-1], counts, width=width, align="edge", color=to_rgba(color, 0.8),
                   edgecolor="black", linewidth=0.6, hatch=ctx.hatch(item.color),
                   label="Observed frequency" if density else None)
        if density:
            _density_curve(ax, ctx, item.values, item.values.size * width,
                           color if overlay else "black", item.label if overlay else None,
                           style)
    if polygon:
        ax.set_ylim(bottom=0)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))    # counts are whole numbers


def _draw_histogram(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec = ctx.spec
    series = _hist_series(ctx)
    edges = _bin_edges(np.concatenate([item.values for item in series]), spec.bins)
    curves = spec.density != "none"
    entries = len(series) * (2 if curves else 1) if len(series) > 1 else 0
    room = _legend_room(spec, entries, long_labels=curves)
    figure = _figure(ctx, title, note, (6.4 + room, 4.4))
    ax = figure.add_subplot()
    _draw_hist_axes(ax, ctx, series, edges, polygon=spec.kind == "frequency_polygon")
    single = len(spec.variables) == 1
    ax.set_xlabel(spec.x_label or (ctx.axis_name(spec.variables[0]) if single
                                   else ctx.value_name()))
    ax.set_ylabel(spec.y_label or "Frequency")
    _finish_axes(ax, ctx, "y")
    _legend(ax, spec, title=spec.group if spec.group else None)
    return figure


# -- boxplots and violins -----------------------------------------------------

def _boxes(ax: Axes, ctx: _Context, items: Sequence[_Series],
           positions: Sequence[float], width: float) -> None:
    """Tukey boxplots (whiskers at 1.5 × IQR), drawn in one call."""
    parts = ax.boxplot(
        [item.values for item in items], positions=list(positions), widths=width,
        patch_artist=True, showfliers=ctx.spec.show_outliers, manage_ticks=False,
        boxprops={"edgecolor": "black", "linewidth": 0.9},
        medianprops={"color": "black", "linewidth": 1.6},
        whiskerprops={"color": "black", "linewidth": 0.9},
        capprops={"color": "black", "linewidth": 0.9},
        flierprops={"marker": "o", "markerfacecolor": "none", "markeredgecolor": "black",
                    "markersize": 4.5, "linestyle": "none"},
    )
    for patch, item in zip(parts["boxes"], items):
        patch.set_facecolor(to_rgba(ctx.color(item.color), 0.55))
        patch.set_hatch(ctx.hatch(item.color))


def _violins(ax: Axes, ctx: _Context, items: Sequence[_Series],
             positions: Sequence[float], width: float) -> None:
    """Kernel density violins with median, quartiles and Tukey outliers.

    A series with fewer than three distinct-enough values gets no violin body
    (no density from so few observations), only its median and quartiles.
    """
    dense = [(item, x) for item, x in zip(items, positions) if _density_possible(item.values)]
    if dense:
        # SciPy's KDE: the same estimator and bandwidth rule as histogram curves
        # (and compiled, unlike the Python loop of Axes.violinplot).
        shapes = []
        for item, _ in dense:
            values = item.values
            coords = np.linspace(float(values.min()), float(values.max()), 100)
            shapes.append({
                "coords": coords,
                "vals": stats.gaussian_kde(values, bw_method=ctx.spec.bandwidth)(coords),
                "mean": float(values.mean()), "median": float(np.median(values)),
                "min": float(values.min()), "max": float(values.max()),
                "quantiles": np.array([]),
            })
        parts = ax.violin(shapes, positions=[x for _, x in dense], widths=width,
                          showextrema=False, showmedians=False)
        for body, (item, _) in zip(parts["bodies"], dense):
            body.set_alpha(None)
            body.set_facecolor(to_rgba(ctx.color(item.color), 0.55))
            body.set_edgecolor("black")
            body.set_linewidth(0.8)
            body.set_hatch(ctx.hatch(item.color))
    for item, x in zip(items, positions):
        values = item.values
        first, median, third = np.percentile(values, [25, 50, 75])
        ax.vlines(x, first, third, color="black", linewidth=3.2, zorder=3)
        ax.scatter([x], [median], s=26, facecolor="white", edgecolor="black", linewidth=1.0,
                   zorder=4)
        if ctx.spec.show_outliers:
            spread = 1.5 * (third - first)
            outliers = values[(values < first - spread) | (values > third + spread)]
            if outliers.size:
                ax.scatter(np.full(outliers.size, x), outliers, s=20, facecolor="none",
                           edgecolor="black", linewidth=0.8, zorder=4)


def _points(ax: Axes, ctx: _Context, item: _Series, x: float, width: float) -> None:
    jitter = ctx.rng.uniform(-0.32, 0.32, item.values.size) * width
    ax.scatter(x + jitter, item.values, s=12, color=ctx.color(item.color), edgecolors="black",
               linewidths=0.3, alpha=0.75, zorder=3)


def _draw_clusters(ax: Axes, ctx: _Context,
                   clusters: Sequence[tuple[str, Sequence[_Series]]], *, violin: bool) -> None:
    """Boxes (or violins) per cluster; a cluster holds one box per series."""
    spec = ctx.spec
    per_cluster = max(len(series) for _, series in clusters)
    slot = 0.8 / per_cluster
    width = 0.5 if per_cluster == 1 else slot * 0.82
    labels = []
    drawn: list[_Series] = []
    positions: list[float] = []
    for position, (label, series) in enumerate(clusters, start=1):
        start = -(len(series) - 1) / 2
        for offset, item in enumerate(series):
            if item.values.size:              # an empty group leaves its slot empty
                drawn.append(item)
                positions.append(position + (start + offset) * slot)
        count = f"\nn = {series[0].values.size}" if len(series) == 1 and spec.apa_style else ""
        labels.append(f"{label}{count}")
    if drawn:
        (_violins if violin else _boxes)(ax, ctx, drawn, positions, width)
        if spec.show_points:
            for item, x in zip(drawn, positions):
                _points(ax, ctx, item, x, width)
    ax.set_xticks(range(1, len(clusters) + 1), labels=labels)
    ax.set_xlim(0.4, len(clusters) + 0.6)
    _rotate_crowded(ax, [label for label, _ in clusters])


def _variable_cluster(ctx: _Context, name: str) -> tuple[str, list[_Series]]:
    return name, [_Series(name, ctx.available(name), 0, name)]


def _level_clusters(ctx: _Context, name: str) -> list[tuple[str, list[_Series]]]:
    return [(item.label, [item]) for item in _level_series(ctx, name)]


def _draw_boxes(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec = ctx.spec
    violin = spec.kind == "violin"
    layout = _box_layout(spec)
    group = spec.group
    if layout in ("panels", "sequential"):
        names = spec.variables if layout == "panels" else (spec.variables[index],)
        if layout == "panels":
            size = _panel_size(len(names))
        else:
            size = (_clamp(2.4 + 1.0 * len(ctx.levels), 5.0, 12.0) if group else 5.0, 4.4)
        figure = _figure(ctx, title, note, size)
        if layout == "panels":
            axes, columns = _panel_axes(figure, len(names))
        else:
            axes, columns = [figure.add_subplot()], 1
        for ax, name in zip(axes, names):
            clusters = _level_clusters(ctx, name) if group else [_variable_cluster(ctx, name)]
            _draw_clusters(ax, ctx, clusters, violin=violin)
            if layout == "panels":
                ax.set_title(name)
            _finish_axes(ax, ctx, "y", x_limits=False)
        y_default = ctx.axis_name(names[0]) if len(names) == 1 else ctx.value_name()
        _label_panels(axes, columns, spec.x_label or (group or ""), spec.y_label or y_default)
        return figure
    names = spec.variables
    if layout == "by_group" and len(names) == 1:
        clusters = _level_clusters(ctx, names[0])
    elif layout == "by_group":
        clusters = [(name, _level_series(ctx, name)) for name in names]
    else:
        clusters = [_variable_cluster(ctx, name) for name in names]
    boxes = sum(len(series) for _, series in clusters)
    entries = len(ctx.levels) if layout == "by_group" and len(names) > 1 else 0
    room = _legend_room(spec, entries, prefer_outside=True)
    figure = _figure(ctx, title, note,
                     (_clamp(1.8 + 0.55 * boxes + 0.3 * len(clusters), 5.0, 13.0) + room, 4.4))
    ax = figure.add_subplot()
    _draw_clusters(ax, ctx, clusters, violin=violin)
    _finish_axes(ax, ctx, "y", x_limits=False)
    if len(names) == 1:
        x_default = group if layout == "by_group" else ""
        y_default = ctx.axis_name(names[0])
    else:
        x_default, y_default = "", ctx.value_name()
    ax.set_xlabel(spec.x_label or x_default)
    ax.set_ylabel(spec.y_label or y_default)
    if layout == "by_group" and len(names) > 1:
        _legend(ax, spec, handles=_level_handles(ctx), title=group, prefer_outside=True)
    return figure


# -- scatterplots, Q–Q plots and line charts -------------------------------------

def _trend(ax: Axes, ctx: _Context, x: np.ndarray, y: np.ndarray) -> None:
    trend = ctx.spec.trend
    if trend == "none" or x.size < MIN_TREND_N[trend] or float(np.ptp(x)) == 0:
        return
    if trend == "ols":
        import statsmodels.api as sm

        fit = sm.OLS(y, sm.add_constant(x)).fit()
        grid = np.linspace(float(x.min()), float(x.max()), 120)
        band = fit.get_prediction(sm.add_constant(grid, has_constant="add")).summary_frame(
            alpha=0.05)
        ax.fill_between(grid, band["mean_ci_lower"].to_numpy(),
                        band["mean_ci_upper"].to_numpy(), color=TREND_COLOR, alpha=0.16,
                        linewidth=0, label="95% CI of the fitted mean", zorder=2)
        ax.plot(grid, band["mean"].to_numpy(), color=TREND_COLOR, linewidth=2.0,
                label="OLS fit (all points)", zorder=4)
    else:
        from statsmodels.nonparametric.smoothers_lowess import lowess

        # Above LOWESS_EXACT_N points, fits within 1% of the x range are
        # interpolated (statsmodels' delta); exact for smaller samples.
        delta = 0.0 if x.size <= LOWESS_EXACT_N else 0.01 * float(np.ptp(x))
        curve = lowess(y, x, frac=LOWESS_FRACTION, it=LOWESS_ITERATIONS, delta=delta,
                       return_sorted=True)
        ax.plot(curve[:, 0], curve[:, 1], color=TREND_COLOR, linewidth=2.0, zorder=4,
                label=f"LOWESS (f = {LOWESS_FRACTION:.2f})")


def _draw_scatter(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec = ctx.spec
    x_name, y_name = spec.variables
    entries = len(ctx.levels) + {"none": 0, "ols": 2, "lowess": 1}[spec.trend]
    figure = _figure(ctx, title, note, (6.4 + _legend_room(spec, entries), 4.6))
    ax = figure.add_subplot()
    x, y = ctx.column(x_name), ctx.column(y_name)
    keep = ctx.complete(x_name, y_name, grouped=_splits_by_group(spec))
    if spec.group:
        for level in ctx.levels:
            member = keep & ctx.in_level(level)
            color = ctx.level_color(level)
            ax.scatter(x[member], y[member], s=30, color=ctx.color(color),
                       marker=_MARKERS[color % len(_MARKERS)], edgecolors="black",
                       linewidths=0.3, alpha=0.85, zorder=3,
                       label=f"{level} (n = {int(member.sum())})")
    else:
        ax.scatter(x[keep], y[keep], s=30, color=ctx.color(0), edgecolors="black",
                   linewidths=0.3, alpha=0.8, zorder=3)
    _trend(ax, ctx, x[keep], y[keep])
    ax.set_xlabel(spec.x_label or ctx.axis_name(x_name))
    ax.set_ylabel(spec.y_label or ctx.axis_name(y_name))
    _finish_axes(ax, ctx, "both")
    _legend(ax, spec, title=spec.group)
    return figure


def _draw_qq(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec = ctx.spec
    series = _qq_series(ctx)
    if len(series) == 1:
        figure = _figure(ctx, title, note, (5.6, 4.6))
        axes, columns = [figure.add_subplot()], 1
    else:
        figure = _figure(ctx, title, note, _panel_size(len(series)))
        axes, columns = _panel_axes(figure, len(series))
    drawn = []
    for ax, item in zip(axes, series):
        if item.values.size < MIN_QQ_N:
            ax.text(0.5, 0.5, f"Too few observations\n(n = {item.values.size})",
                    ha="center", va="center", transform=ax.transAxes)
        else:
            (theoretical, ordered), (slope, intercept, _) = stats.probplot(item.values,
                                                                           dist="norm")
            ax.scatter(theoretical, ordered, s=18, color=ctx.color(item.color),
                       edgecolors="black", linewidths=0.3, zorder=3,
                       label="Ordered observations")
            ends = np.array([theoretical[0], theoretical[-1]])
            ax.plot(ends, intercept + slope * ends, color="black", linestyle="--",
                    linewidth=1.2, label="Least-squares line", zorder=4)
            drawn.append(ax)
        if len(series) > 1:
            label = f"{spec.group} = {item.label}" if spec.group else item.label
            ax.set_title(f"{label} (n = {item.values.size})")
    if len(drawn) > 1 and (spec.group or spec.standardize):
        _share_limits(drawn, x=True, y=True)     # groups of one variable share one scale
    for ax in axes:
        _finish_axes(ax, ctx, "both")
    if len(series) == 1:
        y_default = ctx.axis_name(series[0].name)
    else:
        y_default = "Observed z-score" if spec.standardize else "Observed value"
    _label_panels(axes, columns, spec.x_label or "Theoretical normal quantiles",
                  spec.y_label or y_default)
    if len(series) == 1:
        _legend(axes[0], spec)
    return figure


def _draw_line(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec, data = ctx.spec, ctx.data
    x_name, ys = spec.variables[0], spec.variables[1:]
    lines = len(ctx.levels) if spec.group else len(ys)
    figure = _figure(ctx, title, note,
                     (6.4 + _legend_room(spec, lines if lines > 1 else 0), 4.4))
    ax = figure.add_subplot()
    x = ctx.raw(x_name)
    grouped = bool(spec.group)
    if grouped:
        series = [(level, ys[0], level, ctx.level_color(level)) for level in ctx.levels]
    else:
        series = [(name, name, None, position) for position, name in enumerate(ys)]
    categorical = bool(data.x_categories)
    distinct = np.unique(x[~np.isnan(x)])
    step = 1.0 if categorical or distinct.size < 2 else float(np.min(np.diff(distinct)))
    for label, y_name, level, color in series:
        keep = ctx.complete(x_name, y_name, grouped=grouped)
        if level is not None:
            keep &= ctx.in_level(level)
        xs, values = x[keep], ctx.column(y_name)[keep]
        if xs.size == 0:
            continue
        positions, inverse = np.unique(xs, return_inverse=True)
        means = np.bincount(inverse, weights=values) / np.bincount(inverse)
        if spec.show_points:
            ax.scatter(xs + ctx.rng.uniform(-0.08, 0.08, xs.size) * step, values, s=10,
                       color=ctx.color(color), alpha=0.35, linewidths=0, zorder=2)
        ax.plot(positions, means, color=ctx.color(color), linewidth=1.8, markersize=5.5,
                marker=_MARKERS[color % len(_MARKERS)],
                linestyle=_LINESTYLES[color % len(_LINESTYLES)],
                label=label if len(series) > 1 else None, zorder=3)
    if categorical:
        ax.set_xticks(range(len(data.x_categories)), labels=list(data.x_categories))
        _rotate_crowded(ax, data.x_categories)
    elif 0 < distinct.size <= 12:       # a few ordered values: tick each one
        ax.set_xticks(distinct, labels=[_level_label(value) or "" for value in distinct])
    ax.set_xlabel(spec.x_label or ctx.axis_name(x_name, standardized=False))
    if len(ys) == 1:
        y_default = f"Mean {ctx.axis_name(ys[0])}"
    else:
        y_default = "Mean z-score" if spec.standardize else f"Mean {ctx.value_name().lower()}"
    ax.set_ylabel(spec.y_label or y_default)
    _finish_axes(ax, ctx, "both", x_limits=not categorical)
    _legend(ax, spec, title=spec.group if grouped else None)
    return figure


# -- heatmaps and small multiples ------------------------------------------------

def _text_color(rgba: Sequence[float]) -> str:
    red, green, blue = rgba[:3]
    return "white" if 0.2126 * red + 0.7152 * green + 0.0722 * blue < 0.45 else "black"


def _draw_heatmap(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec = ctx.spec
    table = ctx.data.correlation
    names = table.names
    size = len(names)
    matrix = table.matrix()
    counts = table.counts()
    shown = matrix.copy()
    np.fill_diagonal(shown, np.nan)
    side = _clamp(0.62 * size + 2.6, 4.6, 11.0)
    figure = _figure(ctx, title, note, (side + 1.3, side))
    ax = figure.add_subplot()
    colormap = LinearSegmentedColormap.from_list(
        f"chart-studio-{ctx.palette.name}", list(ctx.palette.diverging), N=256
    ).with_extremes(bad=MISSING_CELL_COLOR)
    scale = Normalize(vmin=-1.0, vmax=1.0)
    edges = np.arange(size + 1) - 0.5
    mesh = ax.pcolormesh(edges, edges, np.ma.masked_invalid(shown), cmap=colormap, norm=scale,
                         edgecolors="white", linewidth=1.0)
    ax.set_facecolor(MISSING_CELL_COLOR)
    ax.set_xlim(-0.5, size - 0.5)
    ax.set_ylim(size - 0.5, -0.5)
    ax.set_aspect("equal")
    ax.set_xticks(range(size), labels=list(names), rotation=35, ha="right",
                  rotation_mode="anchor")
    ax.set_yticks(range(size), labels=list(names))
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    uniform = counts is None or len({int(counts[i, j]) for i in range(size)
                                     for j in range(size) if i != j}) <= 1
    font = max(5.5, spec.font_size - (1.5 if size > 6 else 0.5))
    for i in range(size):
        for j in range(size):
            if i == j:
                ax.text(j, i, "—", ha="center", va="center", fontsize=font, color="black")
                continue
            value = matrix[i, j]
            text = ctx.coefficient(float(value)) if np.isfinite(value) else "N/A"
            if not uniform:
                text += f"\nN = {int(counts[i, j])}"
            color = _text_color(colormap(scale(value))) if np.isfinite(value) else "black"
            ax.text(j, i, text, ha="center", va="center", fontsize=font, color=color)
    bar = figure.colorbar(mesh, ax=ax, shrink=0.8)
    bar.set_label(METHOD_LABELS[table.method])
    bar.outline.set_visible(False)
    return figure


def _draw_faceted(ctx: _Context, title: str, note: str, index: int) -> Figure:
    spec = ctx.spec
    group = spec.group
    figure = _figure(ctx, title, note, _panel_size(len(ctx.levels)))
    axes, columns = _panel_axes(figure, len(ctx.levels))
    if spec.facet_kind == "histogram":
        name = spec.variables[0]
        series = _level_series(ctx, name)
        edges = _bin_edges(np.concatenate([item.values for item in series]), spec.bins)
        for ax, item in zip(axes, series):
            _draw_hist_axes(ax, ctx, [item], edges, polygon=False)
            ax.set_title(f"{group} = {item.label} (n = {item.values.size})")
        _share_limits(axes, x=True, y=True)
        x_text, y_text = spec.x_label or ctx.axis_name(name), spec.y_label or "Frequency"
    else:
        drawn = []
        for ax, level in zip(axes, ctx.levels):
            color = ctx.level_color(level)
            clusters = [(name, [_Series(name, ctx.available(name, level), color,
                                        f"{name} ({group} = {level})")])
                        for name in spec.variables]
            _draw_clusters(ax, ctx, clusters, violin=False)
            ax.set_title(f"{group} = {level}")
            if any(series[0].values.size for _, series in clusters):
                drawn.append(ax)
        if drawn:                   # an empty panel's default limits are not data
            _share_limits(drawn, x=False, y=True)
            for ax in axes:
                ax.set_ylim(drawn[0].get_ylim())
        y_default = (ctx.axis_name(spec.variables[0]) if len(spec.variables) == 1
                     else ctx.value_name())
        x_text, y_text = spec.x_label, spec.y_label or y_default
    for ax in axes:
        _finish_axes(ax, ctx, "y", x_limits=spec.facet_kind == "histogram")
    # No legend: it would describe one panel only; the note explains the curves.
    _label_panels(axes, columns, x_text, y_text)
    return figure


_DRAWERS = {
    "histogram": _draw_histogram,
    "frequency_polygon": _draw_histogram,
    "boxplot": _draw_boxes,
    "multi_boxplot": _draw_boxes,
    "violin": _draw_boxes,
    "scatter": _draw_scatter,
    "heatmap": _draw_heatmap,
    "qq": _draw_qq,
    "line": _draw_line,
    "faceted": _draw_faceted,
}


def _build(spec: ChartSpec, data: ChartData, index: int) -> Figure:
    ctx = _Context(spec, data)
    return _DRAWERS[spec.kind](ctx, _display_title(spec, index), _note_text(spec, data, index),
                               index)


def build_figure(spec: ChartSpec, data: ChartData, index: int = 0) -> Figure:
    """The matplotlib Figure of one chart (no pyplot state; nothing to close).

    For inspection and embedding. Exports should use :func:`render`, which
    also fixes the export settings that make files byte-identical.
    """
    _check_index(index, figure_count(spec, data))
    with _render_context(spec):
        return _build(spec, data, index)


def _metadata(fmt: str, title: str, description: str) -> dict[str, Any]:
    if fmt == "png":
        return {"Software": None, "Title": title, "Description": description}
    if fmt == "svg":
        return {"Creator": None, "Date": None, "Title": title, "Description": description}
    return {"Creator": None, "Producer": None, "CreationDate": None, "Title": title,
            "Subject": description}


def _svg_with_description(svg: bytes, description: str) -> bytes:
    """Add an SVG ``<desc>`` (read by screen readers) after the ``<title>``."""
    text = svg.decode("utf-8")
    element = f"\n <desc>{escape(description)}</desc>"
    closing = text.find("</title>")
    if closing >= 0:
        position = closing + len("</title>")
    else:
        position = text.find(">", text.find("<svg")) + 1
    return (text[:position] + element + text[position:]).encode("utf-8")


def _format_of(fmt: Any) -> str:
    if not isinstance(fmt, str) or fmt.lower() not in FORMATS:
        raise ValueError(f"Export format must be one of: {', '.join(FORMATS)}.")
    return fmt.lower()


def render(spec: ChartSpec, data: ChartData, fmt: str = "png", *, index: int = 0) -> bytes:
    """Draw one figure from ``data`` and return PNG, SVG or PDF bytes.

    Only stored values and statistics are used; nothing is read from or
    written to a dataset. ``index`` selects a figure of the sequential layout.
    """
    fmt = _format_of(fmt)
    _check_index(index, figure_count(spec, data))
    title = _display_title(spec, index)
    description = describe(spec, data, index)
    buffer = BytesIO()
    with _render_context(spec):
        figure = _build(spec, data, index)
        figure.savefig(buffer, format=fmt, dpi=spec.dpi, facecolor="white",
                       metadata=_metadata(fmt, title, description))
    output = buffer.getvalue()
    if fmt == "svg":
        output = _svg_with_description(output, description)
    return output


def render_all(spec: ChartSpec, data: ChartData, fmt: str = "png") -> list[bytes]:
    """Every figure of the chart (one per variable in the sequential layout)."""
    return [render(spec, data, fmt, index=index)
            for index in range(figure_count(spec, data))]


def render_pdf_pages(spec: ChartSpec, data: ChartData) -> bytes:
    """One PDF with a page per figure (the whole sequence for sequential layouts)."""
    count = figure_count(spec, data)
    buffer = BytesIO()
    with _render_context(spec):
        with PdfPages(buffer, metadata=_metadata("pdf", _display_title(spec, None),
                                                 describe(spec, data))) as pages:
            for index in range(count):
                pages.savefig(_build(spec, data, index), facecolor="white")
    return buffer.getvalue()
