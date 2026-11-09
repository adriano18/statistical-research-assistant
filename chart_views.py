"""The charts of one result: its stored values and the researcher's views.

Stage 36.4 (docs/STAGE36_SPEC.md §9). A result keeps the values it was
calculated from (:class:`chart_studio.ChartData`, taken once from the
dataset version the result rests on) and any number of views
(:class:`chart_studio.ChartSpec`). Changing a view changes how the result is
drawn; it never runs the analysis again, never reads the dataset and never
changes a number of the result. The state is JSON-serialisable, so a
project keeps the views and their data across restarts.

This module contains no user-interface code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
from typing import Any, Callable, Mapping

import pandas as pd

import chart_studio as cs
from variable_rules import looks_like_identifier

STATE_VERSION = 1
MAX_VIEWS = 12

#: Roles that name the grouping of a result, in the order they are tried.
GROUP_ROLES = ("group",)
#: Roles a method uses as categories (the two variables of a chi-square
#: test): they are never plotted as numbers.
CATEGORY_ROLES = ("a", "b")
#: Measurement levels a plotted variable may have (charts draw numbers).
PLOTTED_LEVELS = ("scale", "ordinal")
GROUP_LEVELS = ("nominal", "ordinal")


class ChartsUnavailable(ValueError):
    """The result's charts cannot be prepared; ``key`` names the reason."""

    def __init__(self, key: str, **params: Any):
        super().__init__(key)
        self.key = key
        self.params = params


def dataset_sha256(frame: pd.DataFrame) -> str:
    """The dataset version a result records (as ``ResearchSession.provenance_for``)."""
    table = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(table).hexdigest()


def _role_names(value) -> list[str]:
    items = value if isinstance(value, (list, tuple)) else [value]
    return [item for item in items if isinstance(item, str) and item]


def chart_roles(roles: Mapping[str, Any] | None, frame: pd.DataFrame,
                level: Callable[[str], str]) -> tuple[list[str], str | None]:
    """The variables a result's charts plot and the group that splits them.

    Variables are the result's own variables (in role order) that are numeric
    in the dataset and confirmed as scale or ordinal; identifiers and
    nominal variables are left out. The group is the result's grouping role
    when it is nominal or ordinal and has at most
    :data:`chart_studio.MAX_GROUP_LEVELS` levels.
    """
    roles = dict(roles or {})
    group = None
    for key in GROUP_ROLES:
        names = _role_names(roles.get(key))
        if len(names) == 1 and names[0] in frame.columns:
            candidate = names[0]
            levels = frame[candidate].dropna().nunique()
            if (level(candidate) in GROUP_LEVELS and 2 <= levels <= cs.MAX_GROUP_LEVELS
                    and not looks_like_identifier(candidate)):
                group = candidate
            break
    variables: list[str] = []
    for key, value in roles.items():
        if key in GROUP_ROLES or key in CATEGORY_ROLES:
            continue
        for name in _role_names(value):
            if name in variables or name == group or name not in frame.columns:
                continue
            if looks_like_identifier(name) or level(name) not in PLOTTED_LEVELS:
                continue
            series = frame[name]
            if not pd.api.types.is_numeric_dtype(series) or pd.api.types.is_bool_dtype(series):
                continue
            variables.append(name)
    return variables[:cs.MAX_STORED_VARIABLES], group


def may_have_charts(roles: Mapping[str, Any] | None, levels: Mapping[str, str]) -> bool:
    """Whether a result has a variable Chart Studio could draw, judged from
    its roles and recorded levels (no dataset needed): a variable that is not
    the group and is not recorded as nominal or an identifier."""
    for key, value in dict(roles or {}).items():
        if key in GROUP_ROLES or key in CATEGORY_ROLES:
            continue
        for name in _role_names(value):
            if levels.get(name, "unknown") not in ("nominal", "id"):
                return True
    return False


def _small_groups(source: cs.ChartData) -> bool:
    if source.group is None:
        return False
    counts = {level: 0 for level in source.group_levels}
    for label in source.group_values:
        if label is not None:
            counts[label] += 1
    return any(0 < count < cs.SMALL_GROUP_N for count in counts.values())


def default_view(method: str | None, options: Mapping[str, Any] | None,
                 source: cs.ChartData) -> cs.ChartSpec:
    """The first view of a result: the chart that answers its question."""
    options = dict(options or {})
    names = source.variables
    group = source.group
    points = _small_groups(source)
    method = method or ""
    if method in ("batch_correlation", "matrix") and len(names) >= 2:
        coefficient = options.get("method", "pearson")
        if coefficient not in cs.CORRELATION_METHODS:
            coefficient = "pearson"
        return cs.ChartSpec(kind="heatmap", variables=names[:cs.MAX_VARIABLES],
                            correlation_method=coefficient)
    if method in ("correlation", "regression") and len(names) >= 2:
        coefficient = options.get("method", "pearson")
        x, y = (names[1], names[0]) if method == "regression" else (names[0], names[1])
        return cs.ChartSpec(kind="scatter", variables=(x, y),
                            trend="ols" if coefficient == "pearson" else "lowess")
    if group is not None:
        if len(names) == 1:
            return cs.ChartSpec(kind="boxplot", variables=names, group=group,
                                show_points=points)
        return cs.ChartSpec(kind="multi_boxplot", variables=names[:cs.MAX_VARIABLES],
                            group=group, multibox_layout="panels", show_points=points)
    if len(names) == 1:
        return cs.ChartSpec(kind="histogram", variables=names)
    return cs.ChartSpec(kind="multi_boxplot", variables=names[:cs.MAX_VARIABLES],
                        multibox_layout="single")


def _data_key(spec: cs.ChartSpec) -> tuple:
    """What a view's data depend on; presentation settings are not part of it."""
    return (spec.kind == "heatmap", spec.kind == "line", spec.variables, spec.group,
            spec.correlation_method if spec.kind == "heatmap" else "",
            spec.x_order if spec.kind == "line" else ())


@dataclass
class ChartState:
    """A result's stored chart values and its views.

    ``views[active]`` is the view on screen; ``report`` is the view the Word
    report uses (``None``: the result's own figure). ``dataset_sha256`` is
    the dataset version the values were taken from; ``ordered_group`` says
    the researcher confirmed the group as ordinal (a line chart across its
    levels is then meaningful).
    """

    source: cs.ChartData
    views: list[cs.ChartSpec]
    active: int = 0
    report: int | None = None
    dataset_sha256: str = ""
    ordered_group: bool = False
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.views:
            raise ValueError("A chart state needs at least one view.")
        self.active = min(max(0, int(self.active)), len(self.views) - 1)
        if self.report is not None and not 0 <= self.report < len(self.views):
            self.report = None

    # ----------------------------------------------------------- views
    @property
    def view(self) -> cs.ChartSpec:
        return self.views[self.active]

    def kinds(self) -> tuple[str, ...]:
        return cs.available_kinds(self.source, ordered_group=self.ordered_group)

    def data(self, spec: cs.ChartSpec | None = None) -> cs.ChartData:
        """The view's data, derived from the stored values (cached by what
        they depend on, so presentation changes reuse them)."""
        spec = spec or self.view
        key = _data_key(spec)
        data = self._cache.get(key)
        if data is None:
            data = cs.derive(spec, self.source)
            if len(self._cache) > 16:
                self._cache.clear()
            self._cache[key] = data
        return data

    def warnings(self, spec: cs.ChartSpec | None = None) -> tuple[str, ...]:
        spec = spec or self.view
        return cs.chart_warnings(spec, self.data(spec))

    def update(self, spec: cs.ChartSpec) -> cs.ChartSpec:
        """Replace the view on screen after checking it can be drawn."""
        self.data(spec)              # raises ValueError for an impossible view
        cs.chart_warnings(spec, self.data(spec))
        self.views[self.active] = spec
        return spec

    def add_view(self) -> int:
        if len(self.views) >= MAX_VIEWS:
            raise ValueError(f"A result keeps at most {MAX_VIEWS} chart views.")
        self.views.append(self.view)
        self.active = len(self.views) - 1
        return self.active

    def remove_view(self, index: int) -> None:
        if len(self.views) <= 1 or not 0 <= index < len(self.views):
            return
        del self.views[index]
        if self.report is not None:
            if self.report == index:
                self.report = None
            elif self.report > index:
                self.report -= 1
        self.active = min(self.active if self.active < index else self.active - 1,
                          len(self.views) - 1)
        self.active = max(0, self.active)

    # ------------------------------------------------------------ files
    def render(self, fmt: str = "png", *, index: int = 0,
               spec: cs.ChartSpec | None = None) -> bytes:
        spec = spec or self.view
        return cs.render(spec, self.data(spec), fmt, index=index)

    def render_document(self, spec: cs.ChartSpec | None = None) -> bytes:
        """PNG/PDF-ready output for documents: every figure of the view in
        one PDF (sequential layouts have one page per variable)."""
        spec = spec or self.view
        return cs.render_pdf_pages(spec, self.data(spec))

    def report_figure(self) -> tuple[bytes, str, str] | None:
        """(PNG without the in-image caption, title, note) of the report view.

        The Word report sets its own numbered caption and note; the image
        then carries only the plot. A sequential layout contributes its first
        figure."""
        if self.report is None:
            return None
        spec = replace(self.views[self.report], caption_in_image=False, figure_number=None)
        data = self.data(spec)
        png = cs.render(spec, data, "png", index=0)
        return png, cs.figure_title(spec, 0 if cs.figure_count(spec, data) > 1 else None), \
            cs.figure_note(spec, data, 0 if cs.figure_count(spec, data) > 1 else None)

    # ------------------------------------------------------------- JSON
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": STATE_VERSION,
            "source": self.source.to_dict(),
            "views": [view.to_dict() for view in self.views],
            "active": self.active,
            "report": self.report,
            "dataset_sha256": self.dataset_sha256,
            "ordered_group": self.ordered_group,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ChartState":
        if not isinstance(payload, Mapping):
            raise ValueError("Chart state must be a JSON object.")
        version = payload.get("version", STATE_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("Chart state has an invalid version.")
        views = [cs.ChartSpec.from_dict(view) for view in payload.get("views") or ()]
        report = payload.get("report")
        return cls(
            source=cs.ChartData.from_dict(payload["source"]),
            views=views,
            active=int(payload.get("active") or 0),
            report=report if isinstance(report, int) and not isinstance(report, bool) else None,
            dataset_sha256=str(payload.get("dataset_sha256") or ""),
            ordered_group=bool(payload.get("ordered_group")),
        )


def create_state(*, method: str | None, roles: Mapping[str, Any] | None,
                 options: Mapping[str, Any] | None, frame: pd.DataFrame | None,
                 level: Callable[[str], str], expected_sha256: str = "") -> ChartState:
    """Take a result's chart values from the dataset it was calculated on.

    Refuses (``ChartsUnavailable``) when there is no dataset, when the data
    on screen are not the version the result rests on (its charts would
    show other values than its numbers), or when the result has no numeric
    variable to draw.
    """
    if frame is None or frame.columns.empty:
        raise ChartsUnavailable("chart.no_data")
    current = dataset_sha256(frame)
    if expected_sha256 and expected_sha256 != current:
        raise ChartsUnavailable("chart.data_changed")
    variables, group = chart_roles(roles, frame, level)
    if not variables:
        raise ChartsUnavailable("chart.no_numeric")
    try:
        source = cs.snapshot(frame, variables, group)
    except ValueError as error:
        raise ChartsUnavailable("chart.not_drawable", reason=str(error)) from error
    view = default_view(method, options, source)
    try:
        cs.derive(view, source)
    except ValueError:
        view = cs.ChartSpec(kind="histogram", variables=source.variables[:1])
    return ChartState(source=source, views=[view], dataset_sha256=current,
                      ordered_group=group is not None and level(group) == "ordinal")
