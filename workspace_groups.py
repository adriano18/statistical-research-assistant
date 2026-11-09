"""Create groups from a scale (Stage 36.3, docs/STAGE36_SPEC.md §6).

A card on the Data page: choose a quantitative score (e.g. UCLA), a rule
(documented cut points with their source, the researcher's own ranges,
quantiles or equal-width intervals), see every group with its bounds,
inclusivity, N and percent, the missing and out-of-range values and the
warnings, then create a new ordered categorical variable. The score itself
is never changed; the rule is stored in the project's history with the new
dataset version. An existing grouping (such as UCLA_Level for UCLA) is
offered for use instead, never chosen silently.
"""

from __future__ import annotations

import re

import flet as ft

import scale_groups as sg
import workspace_components as wc
import workspace_tokens as tk

METHODS = ("documented", "custom", "quantile", "equal_width")
K_CHOICES = ("2", "3", "4", "5")


def _numbers(text: str) -> list[float]:
    """Cut points typed as "39; 59" (or "39, 59" with decimal points)."""
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"[;\n]+", text) if ";" in text or "\n" in text else re.split(r",\s*", text)
    values = []
    for part in parts:
        part = part.strip().replace(",", ".")
        if part:
            values.append(float(part))
    return values


def _labels(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"[;\n]+", text) if ";" in text or "\n" in text else text.split(",")
    return [part.strip() for part in parts if part.strip()]


class GroupsCard:
    def __init__(self, app):
        self.app = app
        self.source: str | None = None
        self.method = "quantile"
        self.k = "3"
        self.closed = "right"
        self.cuts = ""
        self.labels = ""
        self.citation = ""
        self.target = ""
        self.feedback: tuple[str, str] | None = None
        self.created: str | None = None

    # ----------------------------------------------------------- choices
    def candidates(self) -> list[str]:
        s = self.app.session
        return [name for name, info in s.variables.items()
                if info.confirmed == "scale" and info.storage == "number"]

    def message_text(self, message) -> str:
        ui = self.app.ui
        from workspace_text import T

        if message.key in T:
            try:
                return ui.t(message.key, **message.params)
            except (KeyError, IndexError, ValueError):
                pass
        return message.text

    def rule(self) -> sg.GroupRule:
        """The rule as chosen; raises ValueError with a text key or a reason."""
        if self.method in ("quantile", "equal_width"):
            k = int(self.k)
            maker = sg.quantile_rule if self.method == "quantile" else sg.equal_width_rule
            labels = _labels(self.labels)
            return maker(k, labels if len(labels) == k else None, closed=self.closed)
        cuts = _numbers(self.cuts)
        if not cuts:
            raise ValueError("groups.need_cuts")
        if self.method == "documented" and not self.citation.strip():
            raise ValueError("groups.need_citation")
        labels = _labels(self.labels)
        if len(labels) != len(cuts) + 1:
            labels = list(sg.default_labels(self.method, len(cuts) + 1))
        return sg.contiguous_rule(self.method, cuts, labels, closed=self.closed,
                                  source=self.citation.strip())

    def default_target(self) -> str:
        base = f"{self.source}_groups" if self.source else "groups"
        names = set(self.app.session.df.columns) if self.app.session.has_data else set()
        target, number = base, 2
        while target in names:
            target, number = f"{base}{number}", number + 1
        return target

    # ------------------------------------------------------------- build
    def build(self) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        candidates = self.candidates()
        if self.source not in candidates:
            self.source = candidates[0] if candidates else None
        controls: list[ft.Control] = [wc.caption(ui, ui.t("groups.subtitle"))]
        if not candidates:
            controls.append(wc.notice(ui, ui.t("groups.no_scale"), "info", data="groups-no-scale"))
            return wc.card(ui, controls, title=ui.t("groups.title"), data="groups-card")
        controls.append(wc.dropdown(
            ui, ui.t("groups.source"), [(name, name) for name in candidates], self.source,
            on_select=lambda e: self._set(source=e.control.value), width=300,
            data="groups-source"))
        for existing in sg.existing_groupings(s.df, self.source):
            categories = ", ".join(f"{c} ({n})" for c, n in zip(existing.categories,
                                                                 existing.counts))
            controls.append(wc.notice(
                ui, ui.t("groups.existing", name=existing.name, source=self.source,
                         categories=categories), "info",
                actions=[wc.button(ui, ui.t("groups.use_existing", name=existing.name),
                                   lambda e, n=existing.name: self.compare_by(n), kind="secondary",
                                   data=f"groups-use-{existing.name}")],
                data=f"groups-existing-{existing.name}"))
        controls.append(ft.Row([wc.text(ui, ui.t("groups.method"), tk.TYPE_LABEL), wc.segmented(
            ui, [(m, ui.t(f"groups.method.{m}")) for m in METHODS], self.method,
            lambda value: self._set(method=value), data="groups-method")], wrap=True,
            spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        fields: list[ft.Control] = []
        if self.method in ("quantile", "equal_width"):
            fields.append(wc.dropdown(ui, ui.t("groups.k"), [(k, k) for k in K_CHOICES], self.k,
                                      on_select=lambda e: self._set(k=e.control.value),
                                      width=180, data="groups-k"))
        else:
            fields.append(self._field("cuts", ui.t("groups.cuts"), self.cuts, 220,
                                      hint=ui.t("groups.cuts_hint")))
        fields.append(self._field("labels", ui.t("groups.labels"), self.labels, 320))
        if self.method == "documented":
            fields.append(self._field("citation", ui.t("groups.citation"), self.citation, 420))
        controls.append(ft.Row(fields, wrap=True, spacing=tk.SPACE_3))
        controls.append(ft.Row([wc.text(ui, ui.t("groups.closed"), tk.TYPE_LABEL), wc.segmented(
            ui, [("right", ui.t("groups.closed.right")), ("left", ui.t("groups.closed.left"))],
            self.closed, lambda value: self._set(closed=value), data="groups-closed")],
            wrap=True, spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        controls.append(self._field("target", ui.t("groups.target"),
                                    self.target or self.default_target(), 300))
        controls.append(wc.button(ui, ui.t("groups.preview"), lambda e: app.render(),
                                  icon=ft.Icons.REFRESH, kind="quiet", data="groups-refresh"))
        controls += self._preview()
        if self.feedback:
            controls.append(wc.notice(ui, self.feedback[0], self.feedback[1],
                                      actions=([wc.button(
                                          ui, ui.t("groups.use_existing", name=self.created),
                                          lambda e, n=self.created: self.compare_by(n),
                                          kind="primary", data=f"groups-use-{self.created}")]
                                          if self.created else ()),
                                      data="groups-feedback"))
        return wc.card(ui, controls, title=ui.t("groups.title"), data="groups-card")

    def _field(self, key: str, label: str, value: str, width: int, *,
               hint: str | None = None) -> ft.TextField:
        control = wc.text_field(self.app.ui, label, value, width=width, hint=hint,
                                on_change=lambda e, k=key: setattr(self, k, e.control.value or ""),
                                data=f"groups-{key}")
        # The preview follows when the field is left (no re-render per keystroke).
        control.on_blur = lambda e: self.app.render()
        control.on_submit = lambda e: self.app.render()
        return control

    def _preview(self) -> list[ft.Control]:
        ui, s = self.app.ui, self.app.session
        try:
            rule = self.rule()
            preview = sg.preview(s.df[self.source], rule)
        except ValueError as error:
            key = str(error)
            text = ui.t(key) if key.startswith("groups.") else ui.t("groups.invalid", reason=key)
            return [wc.notice(ui, text, "warning", data="groups-problem")]
        rows = [ft.DataRow(cells=[
            ft.DataCell(wc.text(ui, group.label, tk.TYPE_BODY, weight=ft.FontWeight.W_600)),
            ft.DataCell(wc.text(ui, group.interval, tk.TYPE_BODY)),
            ft.DataCell(wc.text(ui, str(group.n), tk.TYPE_BODY)),
            ft.DataCell(wc.text(ui, "—" if group.percent is None else f"{group.percent:.1f}",
                                tk.TYPE_BODY)),
        ]) for group in preview.groups]
        table = ft.DataTable(columns=[ft.DataColumn(wc.text(ui, ui.t(f"groups.col.{c}"),
                                                            tk.TYPE_LABEL))
                                      for c in ("group", "range", "n", "percent")],
                             rows=rows, heading_row_color=ui.p.surface_alt, data="groups-preview")
        controls: list[ft.Control] = [
            wc.section_label(ui, ui.t("groups.preview")), table,
            wc.caption(ui, ui.t("groups.counts", valid=preview.n_valid, missing=preview.n_missing,
                                outside=preview.n_out_of_range), data="groups-counts"),
            wc.notice(ui, self.message_text(preview.statement), "neutral",
                      data="groups-statement"),
        ]
        for warning in preview.warnings:
            controls.append(wc.notice(ui, self.message_text(warning), "warning",
                                      data=f"groups-warning-{warning.key}"))
        blocked = any(w.key in ("groups.overlap", "groups.overlap_values")
                      for w in preview.warnings)
        controls.append(wc.button(ui, ui.t("groups.create"), lambda e: self.create_groups(),
                                  kind="primary", icon=ft.Icons.ADD_CHART, disabled=blocked,
                                  data="groups-create"))
        return controls

    # ---------------------------------------------------------- actions
    def _set(self, **values) -> None:
        for key, value in values.items():
            setattr(self, key, value or "")
        if "source" in values:
            self.target = ""
        self.feedback, self.created = None, None
        self.app.render()

    def create_groups(self) -> bool:
        app, s = self.app, self.app.session
        target = (self.target or self.default_target()).strip()
        try:
            rule = self.rule()
            result = sg.apply(s.df, self.source, rule, target)
            s.add_derived_column(result.frame, target, "ordinal", result.record())
        except ValueError as error:
            key = str(error)
            text = app.t(key) if key.startswith("groups.") else app.t("groups.invalid", reason=key)
            self.feedback, self.created = (text, "danger"), None
            app.render()
            return False
        groups = "; ".join(f"{g.label} {g.interval}: n = {g.n}" for g in result.preview.groups)
        self.feedback = (app.t("groups.created", target=target, source=self.source,
                               groups=groups), "success")
        self.created = target
        self.target = ""
        app.status(self.feedback[0], "success")
        app.render()
        return True

    def compare_by(self, name: str) -> None:
        """Compare groups by ``name`` (an existing or a new grouping)."""
        page = self.app.pages["analyze"]
        page.reset()
        page.mode, page.goal = "guided", "compare"
        page.selection = {"group": name, "outcome": []}
        self.app.navigate("analyze", section="variables")
