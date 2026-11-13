"""Chart Studio (Stage 36.4, docs/STAGE36_SPEC.md §9): edit how a result is shown.

A result's charts are drawn from the values it was calculated on
(``chart_views.ChartState``). Choosing another chart type, layout or look
changes the view only: the analysis is not run again and no number of the
result changes. Views are saved with the project as soon as they change.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import re

import flet as ft

import chart_studio as cs
import chart_views as cv
import workspace_components as wc
import workspace_tokens as tk

KIND_ORDER = cs.KINDS
LEGENDS = ("best", "outside", "upper right", "upper left", "lower right", "lower left", "none")
LEGEND_KEYS = {"best": "auto", "outside": "outside", "upper right": "upper_right",
               "upper left": "upper_left", "lower right": "lower_right",
               "lower left": "lower_left", "none": "hidden"}
# Segoe UI first (Stage 37): the default where installed (cs.DEFAULT_FONT).
FONTS = ("Segoe UI", "DejaVu Sans", "Arial", "Calibri", "Times New Roman", "Liberation Sans")
NUMBER_FORMATS = ((".0f", "0"), (".1f", "0.0"), (".2f", "0.00"), (".3f", "0.000"))
DPIS = ("100", "150", "300", "600")
PREVIEW_DPI = 110
MULTI_VARIABLE_KINDS = ("histogram", "frequency_polygon", "boxplot", "violin", "qq",
                        "multi_boxplot", "heatmap", "faceted")
GROUPABLE_KINDS = ("histogram", "frequency_polygon", "boxplot", "violin", "qq",
                   "multi_boxplot", "scatter")
POINT_KINDS = ("boxplot", "violin", "multi_boxplot", "faceted")


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return (slug or "chart")[:60]


def _number(text: str) -> float | None:
    text = (text or "").strip().replace(",", ".")
    return float(text) if text else None


class ChartStudioPage:
    def __init__(self, app):
        self.app = app
        self.entry_id: int | None = None
        self.index = 0                          # figure of a sequential layout
        self.pending: dict[str, str] = {}       # typed, not yet applied
        self.feedback: dict[int, tuple[str, str]] = {}
        self.problem: dict[int, tuple[str, dict]] = {}
        self.error: str | None = None
        self.opened: set[str] = set()
        self._previews: dict[tuple, bytes] = {}

    # ------------------------------------------------------------ entry
    def open_charts(self, entry_id: int) -> None:
        """Show the charts of result ``entry_id`` (from Results or a task)."""
        self.entry_id = entry_id
        self.app.session.selected_result = entry_id
        self.index = 0
        self.pending = {}
        self.error = None
        self.app.navigate("charts")

    def _entry(self):
        s = self.app.session
        return (s.result(self.entry_id) or s.result(s.selected_result)
                or (s.results[-1] if s.results else None))

    def _level(self, entry):
        recorded = dict((entry.provenance or {}).get("levels") or {})
        session = self.app.session

        def level(name: str) -> str:
            value = recorded.get(name)
            return value if value and value != "unknown" else session.level(name)
        return level

    def state(self, entry):
        """The result's chart state, prepared from its data on first use."""
        if entry.charts is not None:
            return entry.charts
        session = self.app.session
        expected = str((entry.provenance or {}).get("dataset_sha256") or "")
        if entry.restored and not expected:
            # The data version of this result was never recorded: its charts
            # could be drawn from other values than its numbers.
            self.problem[entry.id] = ("chart.version_unknown", {})
            return None
        if any("data changed" in reason for reason in entry.stale_reasons or ()):
            self.problem[entry.id] = ("chart.data_changed", {})
            return None
        try:
            entry.charts = cv.create_state(
                method=entry.method, roles=entry.roles, options=entry.options,
                frame=session.df if session.has_data else None, level=self._level(entry),
                expected_sha256=expected)
        except cv.ChartsUnavailable as error:
            self.problem[entry.id] = (error.key, error.params)
            return None
        self.problem.pop(entry.id, None)
        session.save_charts(entry.id)
        return entry.charts

    # ------------------------------------------------------------ build
    def build(self) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        header = wc.page_header(ui, ui.t("chart.title"), ui.t("chart.subtitle"))
        entry = self._entry()
        if entry is None:
            return app.constrained(ft.Column([header, wc.empty_state(
                ui, ft.Icons.BAR_CHART, ui.t("chart.empty.title"), ui.t("chart.empty.body"),
                actions=[wc.button(ui, ui.t("nav.analyze"), lambda e: app.navigate("analyze"),
                                   kind="primary")], data="charts-empty")], spacing=tk.SPACE_5))
        self.entry_id = entry.id
        picker = wc.dropdown(
            ui, ui.t("chart.result"),
            [(str(r.id), f"{r.id}. {r.title}") for r in reversed(s.results)], str(entry.id),
            on_select=lambda e: self._pick(int(e.control.value)), width=520, data="chart-result")
        top = ft.Row([picker, wc.button(ui, ui.t("chart.back"), lambda e: self._back(),
                                        icon=ft.Icons.ARROW_BACK, data="chart-back")],
                     wrap=True, spacing=tk.SPACE_3,
                     vertical_alignment=ft.CrossAxisAlignment.CENTER)
        state = self.state(entry)
        if state is None:
            key, params = self.problem.get(entry.id, ("chart.no_numeric", {}))
            actions = []
            if key in ("chart.data_changed", "chart.version_unknown") and entry.method:
                actions.append(wc.button(ui, ui.t("chart.recalculate"),
                                         lambda e: self._recalculate(entry.id),
                                         kind="primary", icon=ft.Icons.REFRESH,
                                         data="chart-recalculate"))
            body = [wc.notice(ui, ui.t(key, **params), "warning", actions=actions,
                              data="chart-unavailable")]
            return app.constrained(ft.Column([header, top, *body], spacing=tk.SPACE_4),
                                   tk.CONTENT_MAX_WIDTH + 200)
        controls = [header, top, self._views(entry, state), self._kinds(state),
                    self._editor(entry, state)]
        if self.error:
            controls.append(wc.notice(ui, ui.t("chart.invalid", reason=self.error), "danger",
                                      data="chart-error"))
        controls += [self._preview(entry, state), self._appearance(state),
                     self._actions(entry, state)]
        controls.append(wc.caption(ui, ui.t("chart.saved_in_project") if app.projects.active
                                   else ui.t("chart.not_saved"), data="chart-saved-note"))
        return app.constrained(ft.Column(controls, spacing=tk.SPACE_4,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.CONTENT_MAX_WIDTH + 200)

    def _views(self, entry, state) -> ft.Control:
        ui = self.app.ui
        chips = [wc.chip(ui, ui.t("chart.view", number=index + 1)
                         + (" · Word" if state.report == index else ""),
                         "info" if index == state.active else "neutral",
                         icon=ft.Icons.CHECK_CIRCLE if index == state.active else ft.Icons.IMAGE_OUTLINED,
                         on_click=lambda e, i=index: self._activate(i),
                         data=f"chart-view-{index}")
                 for index in range(len(state.views))]
        chips.append(wc.button(ui, ui.t("chart.add_view"), lambda e: self._add_view(),
                               icon=ft.Icons.ADD, kind="quiet", data="chart-add-view",
                               disabled=len(state.views) >= cv.MAX_VIEWS))
        if len(state.views) > 1:
            chips.append(wc.button(ui, ui.t("chart.remove_view"), lambda e: self._remove_view(),
                                   icon=ft.Icons.DELETE_OUTLINE, kind="quiet",
                                   data="chart-remove-view"))
        return ft.Row([wc.section_label(ui, ui.t("chart.views")), *chips], wrap=True,
                      spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                      data="chart-views")

    def _kinds(self, state) -> ft.Control:
        ui = self.app.ui
        current = state.view.kind
        chips = [wc.chip(ui, ui.t("chart.kind." + kind), "info" if kind == current else "neutral",
                         icon=ft.Icons.RADIO_BUTTON_CHECKED if kind == current
                         else ft.Icons.RADIO_BUTTON_UNCHECKED,
                         on_click=lambda e, k=kind: self.set_kind(k), data=f"chart-kind-{kind}")
                 for kind in state.kinds()]
        return wc.card(ui, [ft.Row(chips, wrap=True, spacing=tk.SPACE_2, run_spacing=tk.SPACE_2)],
                       title=ui.t("chart.kind"), data="chart-kinds")

    def _editor(self, entry, state) -> ft.Control:
        ui = self.app.ui
        spec = state.view
        source = state.source
        kind = spec.kind
        rows: list[ft.Control] = []
        names = source.variables
        if kind == "scatter":
            options = [(name, name) for name in names]
            rows.append(ft.Row([
                wc.dropdown(ui, ui.t("chart.x"), options, spec.variables[0],
                            on_select=lambda e: self._axis(0, e.control.value), data="chart-x"),
                wc.dropdown(ui, ui.t("chart.y"), options, spec.variables[1],
                            on_select=lambda e: self._axis(1, e.control.value), data="chart-y"),
            ], wrap=True, spacing=tk.SPACE_3))
        else:
            plotted = spec.variables[1:] if kind == "line" else spec.variables
            boxes = [wc.checkbox(ui, name, name in plotted,
                                 on_change=lambda e, n=name: self._toggle(n, bool(e.control.value)),
                                 data=f"chart-var-{name}")
                     for name in names]
            rows.append(ft.Row(boxes, wrap=True, spacing=tk.SPACE_3, data="chart-variables"))
        if source.group and kind in GROUPABLE_KINDS:
            rows.append(wc.checkbox(ui, ui.t("chart.group", group=source.group),
                                    spec.group is not None,
                                    on_change=lambda e: self._split(bool(e.control.value)),
                                    data="chart-group"))
        if kind == "multi_boxplot":
            layouts = [layout for layout in cs.MULTIBOX_LAYOUTS
                       if layout != "by_group" or spec.group]
            rows.append(self._labelled("chart.layout", wc.segmented(
                ui, [(layout, ui.t("chart.layout." + layout)) for layout in layouts],
                spec.multibox_layout, lambda value: self.change(multibox_layout=value),
                data="chart-layout")))
        if kind == "histogram":
            rows.append(self._labelled("chart.density", wc.segmented(
                ui, [(value, ui.t("chart.density." + value)) for value in cs.DENSITIES],
                spec.density, lambda value: self.change(density=value), data="chart-density")))
        if kind == "scatter":
            rows.append(self._labelled("chart.trend", wc.segmented(
                ui, [(value, ui.t("chart.trend." + value)) for value in cs.TRENDS],
                spec.trend, lambda value: self.change(trend=value), data="chart-trend")))
        if kind == "heatmap":
            rows.append(self._labelled("chart.method", wc.segmented(
                ui, [(value, cs.METHOD_LABELS[value]) for value in cs.CORRELATION_METHODS],
                spec.correlation_method, lambda value: self.change(correlation_method=value),
                data="chart-method")))
        if kind == "faceted":
            rows.append(self._labelled("chart.facet", wc.segmented(
                ui, [(value, ui.t("chart.facet." + value)) for value in cs.FACET_KINDS],
                spec.facet_kind, lambda value: self._facet(value), data="chart-facet")))
        if kind == "line":
            rows.append(self._order(state))
        if kind in POINT_KINDS or (kind == "faceted" and spec.facet_kind == "boxplot"):
            rows.append(ft.Row([
                wc.checkbox(ui, ui.t("chart.points"), spec.show_points,
                            on_change=lambda e: self.change(show_points=bool(e.control.value)),
                            data="chart-points"),
                wc.checkbox(ui, ui.t("chart.outliers"), spec.show_outliers,
                            on_change=lambda e: self.change(show_outliers=bool(e.control.value)),
                            data="chart-outliers"),
            ], wrap=True, spacing=tk.SPACE_4))
        if kind != "heatmap" and kind != "scatter" and len(spec.variables) > 1:
            rows.append(wc.checkbox(ui, ui.t("chart.standardize"), spec.standardize,
                                    on_change=lambda e: self.change(
                                        standardize=bool(e.control.value)),
                                    data="chart-standardize"))
        return wc.card(ui, rows, title=ui.t("chart.variables"), data="chart-editor")

    def _labelled(self, key: str, control: ft.Control) -> ft.Control:
        ui = self.app.ui
        return ft.Row([wc.text(ui, ui.t(key), tk.TYPE_LABEL), control], wrap=True,
                      spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _order(self, state) -> ft.Control:
        ui = self.app.ui
        order = list(state.view.x_order or state.source.group_levels)
        rows = [wc.caption(ui, ui.t("chart.order"))]
        for index, level in enumerate(order):
            rows.append(ft.Row([
                ft.Container(wc.text(ui, f"{index + 1}. {level}", tk.TYPE_BODY), expand=True),
                wc.icon_button(ui, ft.Icons.ARROW_UPWARD, ui.t("chart.move_up"),
                               lambda e, i=index: self._move_level(i, -1), disabled=index == 0,
                               data=f"chart-order-up-{index}"),
                wc.icon_button(ui, ft.Icons.ARROW_DOWNWARD, ui.t("chart.move_down"),
                               lambda e, i=index: self._move_level(i, 1),
                               disabled=index == len(order) - 1,
                               data=f"chart-order-down-{index}"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        return ft.Column(rows, spacing=tk.SPACE_1, data="chart-order")

    def _preview(self, entry, state) -> ft.Control:
        ui = self.app.ui
        spec = state.view
        data = state.data()
        count = cs.figure_count(spec, data)
        self.index = min(self.index, count - 1)
        png = self.preview_png(entry, state)
        alt = cs.describe(spec, data, self.index if count > 1 else None)
        controls: list[ft.Control] = [wc.figure(ui, png, caption_text="", max_height=520,
                                                semantics=alt)]
        if count > 1:
            controls.append(ft.Row([
                wc.icon_button(ui, ft.Icons.CHEVRON_LEFT, ui.t("chart.previous"),
                               lambda e: self._page(-1), disabled=self.index == 0,
                               data="chart-prev"),
                wc.text(ui, ui.t("chart.figure_of", index=self.index + 1, count=count),
                        tk.TYPE_LABEL, data="chart-page"),
                wc.icon_button(ui, ft.Icons.CHEVRON_RIGHT, ui.t("chart.next"),
                               lambda e: self._page(1), disabled=self.index >= count - 1,
                               data="chart-next"),
            ], alignment=ft.MainAxisAlignment.CENTER))
        warnings = state.warnings()
        if warnings:
            controls.append(wc.notice(ui, "\n".join("• " + w for w in warnings), "warning",
                                      title=ui.t("chart.warnings"), data="chart-warnings"))
        controls.append(wc.caption(ui, ui.t("chart.unchanged"), data="chart-unchanged"))
        controls.append(wc.caption(ui, ui.t("chart.alt", text=alt), data="chart-alt"))
        return wc.card(ui, controls, title=ui.t("chart.preview"), data="chart-preview")

    def preview_png(self, entry, state) -> bytes:
        spec = replace(state.view, dpi=min(state.view.dpi, PREVIEW_DPI))
        key = (entry.id, spec.to_json(), self.index)
        png = self._previews.get(key)
        if png is None:
            png = state.render("png", index=self.index, spec=spec)
            if len(self._previews) > 12:
                self._previews.clear()
            self._previews[key] = png
        return png

    def _appearance(self, state) -> ft.Control:
        ui = self.app.ui
        spec = state.view

        def field(key: str, label: str, value: str, *, width: int = 220,
                  multiline: bool = False) -> ft.TextField:
            control = wc.text_field(ui, label, self.pending.get(key, value), width=width,
                                    multiline=multiline,
                                    on_change=lambda e, k=key: self._draft(k, e.control.value),
                                    data=f"chart-{key}")
            control.on_blur = lambda e: self.apply()
            if not multiline:
                control.on_submit = lambda e: self.apply()
            return control

        limits = lambda pair, i: "" if pair is None else f"{pair[i]:g}"  # noqa: E731
        texts = ft.Row([
            field("title", ui.t("chart.title_field"), spec.title, width=420),
            field("xlabel", ui.t("chart.xlabel"), spec.x_label),
            field("ylabel", ui.t("chart.ylabel"), spec.y_label),
        ], wrap=True, spacing=tk.SPACE_3)
        note = field("note", ui.t("chart.note"), spec.note, width=660, multiline=True)
        look = ft.Row([
            wc.dropdown(ui, ui.t("chart.legend"),
                        [(value, ui.t("chart.legend." + LEGEND_KEYS[value])) for value in LEGENDS],
                        spec.legend if spec.legend in LEGENDS else "best",
                        on_select=lambda e: self.change(legend=e.control.value), width=200,
                        data="chart-legend"),
            wc.dropdown(ui, ui.t("chart.palette"),
                        [(name, ui.t("chart.palette." + name)) for name in cs.PALETTES],
                        spec.palette, on_select=lambda e: self.change(palette=e.control.value),
                        width=240, data="chart-palette"),
            wc.dropdown(ui, ui.t("chart.font"), [(font, font) for font in FONTS],
                        spec.font_family if spec.font_family in FONTS else cs.DEFAULT_FONT,
                        on_select=lambda e: self.change(font_family=e.control.value), width=210,
                        data="chart-font"),
            wc.dropdown(ui, ui.t("chart.number_format"), list(NUMBER_FORMATS),
                        spec.number_format if spec.number_format in dict(NUMBER_FORMATS) else ".2f",
                        on_select=lambda e: self.change(number_format=e.control.value),
                        width=170, data="chart-number-format"),
            wc.dropdown(ui, ui.t("chart.dpi"), [(d, d) for d in DPIS],
                        str(spec.dpi) if str(spec.dpi) in DPIS else "150",
                        on_select=lambda e: self.change(dpi=int(e.control.value)), width=150,
                        data="chart-dpi"),
        ], wrap=True, spacing=tk.SPACE_3)
        size = ft.Row([
            field("font-size", ui.t("chart.font_size"), f"{spec.font_size:g}", width=150),
            field("width", ui.t("chart.width"), "" if spec.width_in is None else f"{spec.width_in:g}",
                  width=150),
            field("height", ui.t("chart.height"),
                  "" if spec.height_in is None else f"{spec.height_in:g}", width=150),
            field("figure-number", ui.t("chart.figure_number"),
                  "" if spec.figure_number is None else str(spec.figure_number), width=150),
        ], wrap=True, spacing=tk.SPACE_3)
        axes = ft.Row([
            field("xmin", ui.t("chart.xmin"), limits(spec.x_limits, 0), width=130),
            field("xmax", ui.t("chart.xmax"), limits(spec.x_limits, 1), width=130),
            field("ymin", ui.t("chart.ymin"), limits(spec.y_limits, 0), width=130),
            field("ymax", ui.t("chart.ymax"), limits(spec.y_limits, 1), width=130),
        ], wrap=True, spacing=tk.SPACE_3)
        switches = ft.Row([
            wc.checkbox(ui, ui.t("chart.grid"), spec.grid,
                        on_change=lambda e: self.change(grid=bool(e.control.value)),
                        data="chart-grid"),
            wc.checkbox(ui, ui.t("chart.apa"), spec.apa_style,
                        on_change=lambda e: self.change(apa_style=bool(e.control.value)),
                        data="chart-apa"),
        ], wrap=True, spacing=tk.SPACE_4)
        body = ft.Container(ft.Column([
            texts, note, look, size, wc.caption(ui, ui.t("chart.limits")), axes, switches,
            ft.Row([wc.button(ui, ui.t("chart.apply"), lambda e: self.apply(), kind="primary",
                              icon=ft.Icons.CHECK, data="chart-apply")]),
        ], spacing=tk.SPACE_3), padding=tk.SPACE_4)
        return wc.expansion(ui, wc.heading(ui, ui.t("chart.appearance"), tk.TYPE_TITLE_S),
                            [body], key="chart-appearance", opened=self.opened,
                            subtitle=wc.caption(ui, ui.t("chart.appearance_hint")),
                            data="chart-appearance")

    def _actions(self, entry, state) -> ft.Control:
        ui = self.app.ui
        used = state.report is not None and state.report == state.active
        feedback = ([wc.notice(ui, *self.feedback[entry.id], data="chart-feedback")]
                    if entry.id in self.feedback else [])
        return wc.card(ui, [ft.Row([
            wc.button(ui, ui.t("chart.copy"), wc.handler(self.copy), kind="primary",
                      icon=ft.Icons.CONTENT_COPY, data="chart-copy"),
            wc.button(ui, ui.t("chart.save_png"), wc.handler(self.save, "png"),
                      icon=ft.Icons.IMAGE_OUTLINED, data="chart-save-png"),
            wc.button(ui, ui.t("chart.save_svg"), wc.handler(self.save, "svg"),
                      icon=ft.Icons.POLYLINE_OUTLINED, data="chart-save-svg"),
            wc.button(ui, ui.t("chart.save_pdf"), wc.handler(self.save, "pdf"),
                      icon=ft.Icons.PICTURE_AS_PDF_OUTLINED, data="chart-save-pdf"),
            wc.button(ui, ui.t("chart.report_on") if used else ui.t("chart.report_add"),
                      lambda e: self.toggle_report(), kind="secondary",
                      icon=ft.Icons.CHECK if used else ft.Icons.DESCRIPTION_OUTLINED,
                      data="chart-report"),
        ], wrap=True, spacing=tk.SPACE_3), *feedback], data="chart-actions")

    # ---------------------------------------------------------- changes
    def _current(self):
        entry = self._entry()
        return entry, (entry.charts if entry is not None else None)

    def change(self, **fields) -> bool:
        """Apply a change to the view on screen; never runs an analysis."""
        entry, state = self._current()
        if state is None:
            return False
        try:
            spec = replace(state.view, **fields)
            state.update(spec)
        except (TypeError, ValueError) as error:
            self.error = str(error)
            self.app.render()
            return False
        self.error = None
        self.index = 0 if "multibox_layout" in fields or "variables" in fields else self.index
        self.app.session.save_charts(entry.id)
        self.app.render()
        return True

    def set_kind(self, kind: str) -> bool:
        """Switch the chart type, keeping the variables that the type can show."""
        entry, state = self._current()
        if state is None:
            return False
        spec, source = state.view, state.source
        names = [n for n in spec.variables if n in source.variables] or list(source.variables)
        if spec.kind in ("line",):
            names = [n for n in spec.variables[1:]] or list(source.variables)
        if spec.kind in ("scatter", "histogram", "frequency_polygon", "qq") or len(names) < 2:
            # Kinds that showed a part of the selection: start from all values.
            names = list(source.variables)
        group = spec.group or (source.group if spec.kind in ("heatmap", "line", "scatter")
                               else None)
        group = group if source.group else None
        fields: dict = {"kind": kind, "x_order": ()}
        if kind in ("histogram", "frequency_polygon", "qq"):
            fields.update(variables=tuple(names[:1] if group else names[:cs.MAX_VARIABLES]),
                          group=group)
        elif kind in ("boxplot", "violin"):
            fields.update(variables=tuple(names[:cs.MAX_VARIABLES]), group=group)
        elif kind == "multi_boxplot":
            fields.update(variables=tuple(names[:cs.MAX_VARIABLES]), group=group,
                          multibox_layout="panels" if group else "single")
        elif kind == "scatter":
            pair = names[:2] if len(names) >= 2 else list(source.variables[:2])
            fields.update(variables=tuple(pair), group=None)
        elif kind == "heatmap":
            fields.update(variables=tuple(names[:cs.MAX_VARIABLES]), group=None)
        elif kind == "faceted":
            fields.update(variables=tuple(names[:1]), group=source.group, facet_kind="histogram")
        elif kind == "line":
            fields.update(variables=(source.group, *names[:6]), group=None,
                          x_order=tuple(source.group_levels))
        if kind in ("boxplot", "violin", "multi_boxplot") and group and cv._small_groups(source):
            fields["show_points"] = True
        if kind in ("heatmap", "scatter"):
            fields["standardize"] = False
        return self.change(**fields)

    def _toggle(self, name: str, on: bool) -> None:
        entry, state = self._current()
        if state is None:
            return
        spec = state.view
        if spec.kind == "line":
            chosen = set(spec.variables[1:])
            (chosen.add if on else chosen.discard)(name)
            ys = tuple(n for n in state.source.variables if n in chosen)
            self.change(variables=(spec.variables[0], *ys))
            return
        chosen = set(spec.variables)
        (chosen.add if on else chosen.discard)(name)
        names = tuple(n for n in state.source.variables if n in chosen)
        if spec.kind in ("histogram", "frequency_polygon", "qq") and spec.group and len(names) > 1:
            names = (name,) if on else names[:1]    # one variable per split histogram
        if spec.kind == "faceted" and spec.facet_kind == "histogram" and len(names) > 1:
            names = (name,) if on else names[:1]
        self.change(variables=names)

    def _axis(self, position: int, name: str) -> None:
        entry, state = self._current()
        if state is None or not name:
            return
        pair = list(state.view.variables)
        other = 1 - position
        if pair[other] == name:                  # swap instead of a duplicate
            pair[other] = pair[position]
        pair[position] = name
        self.change(variables=tuple(pair))

    def _split(self, on: bool) -> None:
        entry, state = self._current()
        if state is None:
            return
        spec = state.view
        fields: dict = {"group": state.source.group if on else None}
        if on and spec.kind in ("histogram", "frequency_polygon", "qq") and len(spec.variables) > 1:
            fields["variables"] = spec.variables[:1]
        if not on and spec.kind == "multi_boxplot" and spec.multibox_layout == "by_group":
            fields["multibox_layout"] = "single"
        self.change(**fields)

    def _facet(self, value: str) -> None:
        entry, state = self._current()
        if state is None:
            return
        names = state.view.variables
        if value == "histogram":
            names = names[:1]
        else:
            names = tuple(n for n in state.source.variables)[:cs.MAX_VARIABLES]
        self.change(facet_kind=value, variables=names)

    def _move_level(self, index: int, step: int) -> None:
        entry, state = self._current()
        if state is None:
            return
        order = list(state.view.x_order or state.source.group_levels)
        target = index + step
        if 0 <= target < len(order):
            order[index], order[target] = order[target], order[index]
            self.change(x_order=tuple(order))

    def _draft(self, key: str, value: str) -> None:
        self.pending[key] = value or ""

    def apply(self) -> bool:
        """Apply what was typed in the appearance fields."""
        if not self.pending:
            return True
        entry, state = self._current()
        if state is None:
            return False
        spec = state.view
        values = dict(self.pending)
        try:
            fields: dict = {}
            if "title" in values:
                fields["title"] = values["title"]
            if "xlabel" in values:
                fields["x_label"] = values["xlabel"]
            if "ylabel" in values:
                fields["y_label"] = values["ylabel"]
            if "note" in values:
                fields["note"] = values["note"]
            if "font-size" in values:
                fields["font_size"] = _number(values["font-size"]) or 10.0
            if "width" in values:
                fields["width_in"] = _number(values["width"])
            if "height" in values:
                fields["height_in"] = _number(values["height"])
            if "figure-number" in values:
                number = _number(values["figure-number"])
                fields["figure_number"] = None if number is None else int(number)
            for axis in ("x", "y"):
                low_key, high_key = f"{axis}min", f"{axis}max"
                if low_key in values or high_key in values:
                    current = getattr(spec, f"{axis}_limits") or (None, None)
                    low = _number(values[low_key]) if low_key in values else current[0]
                    high = _number(values[high_key]) if high_key in values else current[1]
                    fields[f"{axis}_limits"] = (None if low is None and high is None
                                                else (low, high))
        except ValueError:
            self.error = self.app.t("chart.not_a_number")
            self.app.render()
            return False
        limits_incomplete = [axis for axis in ("x", "y")
                             if fields.get(f"{axis}_limits") is not None
                             and None in fields[f"{axis}_limits"]]
        if limits_incomplete:
            self.error = self.app.t("chart.limits_pair")
            self.app.render()
            return False
        self.pending = {}
        return self.change(**fields)

    def _activate(self, index: int) -> None:
        entry, state = self._current()
        if state is None:
            return
        self.apply()
        state.active = max(0, min(index, len(state.views) - 1))
        self.index = 0
        self.app.session.save_charts(entry.id)
        self.app.render()

    def _add_view(self) -> None:
        entry, state = self._current()
        if state is None:
            return
        state.add_view()
        self.index = 0
        self.app.session.save_charts(entry.id)
        self.app.render()

    def _remove_view(self) -> None:
        entry, state = self._current()
        if state is None:
            return
        state.remove_view(state.active)
        self.index = 0
        self.app.session.save_charts(entry.id)
        self.app.render()

    def _page(self, step: int) -> None:
        self.index = max(0, self.index + step)
        self.app.render()

    def _pick(self, entry_id: int) -> None:
        self.entry_id = entry_id
        self.app.session.selected_result = entry_id
        self.index = 0
        self.pending = {}
        self.error = None
        self.app.render()

    def _back(self) -> None:
        if self.entry_id is not None:
            self.app.session.selected_result = self.entry_id
        self.app.navigate("results")

    def _recalculate(self, entry_id: int) -> None:
        entry = self.app.session.result(entry_id)
        if entry is not None and entry.method:
            self.app.pages["analyze"].rerun(entry)

    # ----------------------------------------------------------- output
    def _file_name(self, state, extension: str) -> str:
        spec = state.view
        return f"{_slug(cs.figure_title(spec))}.{extension}"

    async def copy(self):
        """Put the chart on the clipboard as an image (not a file path)."""
        entry, state = self._current()
        if state is None:
            return
        self.apply()
        app = self.app
        try:
            png = await asyncio.to_thread(state.render, "png", index=self.index)
        except ValueError as error:
            self.feedback[entry.id] = (app.t("chart.copy_failed", reason=str(error)), "danger")
            app.render()
            return
        self.feedback[entry.id] = await copy_to_clipboard(app, png)
        app.render()

    async def save(self, fmt: str):
        entry, state = self._current()
        if state is None:
            return
        self.apply()
        app = self.app
        index = self.index
        spec = state.view

        def write(path):
            if fmt == "pdf":
                data = state.render_document(spec)
            else:
                data = state.render(fmt, index=index, spec=spec)
            path.write_bytes(data)
            return path

        outcome = await app.save_file(app.t("chart.save_" + fmt), self._file_name(state, fmt),
                                      fmt, write)
        self.feedback[entry.id] = (outcome.message, outcome.tone)
        app.render()

    def toggle_report(self) -> None:
        """Use the view on screen as the result's figure in the Word report."""
        entry, state = self._current()
        if state is None:
            return
        self.apply()
        session = self.app.session
        if state.report == state.active:
            state.report = None
            self.feedback[entry.id] = (self.app.t("chart.report_removed"), "info")
        else:
            state.report = state.active
            if not entry.in_report:
                session.toggle_report(entry.id)
            self.feedback[entry.id] = (self.app.t("chart.report_added"), "success")
        session.save_charts(entry.id)
        self.app.render()


async def copy_to_clipboard(app, png: bytes) -> tuple[str, str]:
    """Copy ``png`` as an image; returns the (message, tone) shown to the researcher."""
    import image_clipboard

    width, height = _png_size(png)
    if getattr(app.page, "web", False):
        try:
            clipboard = ft.Clipboard()
            app.page.services.append(clipboard)
            await clipboard.set_image(png)
            outcome = image_clipboard.ClipboardOutcome(True, "browser")
        except Exception as error:   # pragma: no cover - browser dependent
            outcome = image_clipboard.ClipboardOutcome(False, "failed", str(error))
    else:
        outcome = await asyncio.to_thread(image_clipboard.copy_png, png)
    if outcome.copied:
        message = (app.t("chart.copied", width=width, height=height), "success")
    elif outcome.how == "unavailable":
        message = (app.t("chart.copy_unavailable", reason=outcome.detail), "warning")
    else:
        message = (app.t("chart.copy_failed", reason=outcome.detail), "danger")
    app.status(*message)
    return message


def _png_size(png: bytes) -> tuple[int, int]:
    """Width and height from a PNG header."""
    if len(png) < 24:
        return 0, 0
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
