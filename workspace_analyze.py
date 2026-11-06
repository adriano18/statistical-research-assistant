"""Analyze (guided + all methods), Results and Reports pages.

Both analysis modes execute through ``workspace_methods.run_method`` and
therefore through ``analysis_runs`` — the classic engine compositions.
Results show only values the engine computed (``AnalysisEvidence`` rows,
engine tables, report text); no number is formatted or derived here.
"""

from __future__ import annotations

import asyncio

import flet as ft

import workspace_components as wc
import workspace_tokens as tk
from workspace_methods import (
    FAMILIES, GOAL_ROLES, GOALS, METHODS, RoleProblems, advise, default_options,
    required_confirmations, run_method,
)
from workspace_state import LEVELS
from workspace_text import count_text, label as engine_label

GOAL_ICONS = {
    "compare": ft.Icons.COMPARE_ARROWS, "change": ft.Icons.TIMELINE,
    "relate": ft.Icons.SCATTER_PLOT_OUTLINED, "associate": ft.Icons.GRID_ON,
    "predict": ft.Icons.TRENDING_UP, "scale": ft.Icons.FACT_CHECK_OUTLINED,
    "structure": ft.Icons.ACCOUNT_TREE_OUTLINED, "describe": ft.Icons.BAR_CHART,
}


def problem_text(ui, key: str, params: dict) -> str:
    """A blocker in the researcher's language; parameters that are text keys
    (roles, measurement levels, "level.a / level.b" lists) are translated too."""
    from workspace_text import T

    def value(item):
        if isinstance(item, str):
            parts = [part.strip() for part in item.split(" / ")]
            if parts and all(part in T for part in parts):
                return " / ".join(ui.t(part) for part in parts)
        return item

    return ui.t(key, **{name: value(item) for name, item in params.items()})


def problems_text(ui, problems) -> str:
    return "\n".join("• " + problem_text(ui, key, params) for key, params in problems)


def session_note(app) -> str:
    """Where results live: the open project, or this session only."""
    info = app.projects.info() if app.projects.active else None
    if info is None:
        return app.t("results.session_note")
    return app.t("results.project_note", title=info.title)


def method_label(key: str, options: dict) -> str:
    spec = METHODS[key]
    for option in spec.options:
        if option.key == "method":
            value = options.get("method", option.default)
            return next((label for k, label in option.choices if k == value), spec.title)
    return spec.title


def _variable_options(ui: wc.Ui, session, *, allow_id: bool = False):
    options = []
    for info in session.variables.values():
        if info.suggested == "id" and not allow_id:
            continue
        level = ui.t(f"level.{info.confirmed}")
        options.append((info.name, f"{info.name} · {level}"))
    return options


class AnalyzePage:
    def __init__(self, app):
        self.app = app
        self.mode = "guided"
        self.goal: str | None = None
        self.selection: dict = {}
        self.confirms: dict = {}
        self.override: tuple[str, dict] | None = None
        self.search = ""
        self.method: str | None = None         # all-methods form
        self.form_roles: dict = {}
        self.form_options: dict = {}
        self.form_confirms: dict = {}
        self.running = False
        self.message: tuple[str, str] | None = None
        self.choosing_goal = False          # step 1 re-opened with "Change"

    def rerun(self, entry) -> None:
        """Open a saved result's analysis for the current data. The researcher
        gives the confirmations again: they were made for the earlier data."""
        key = "omnibus" if entry.method == "posthoc" else entry.method
        self.mode, self.method = "all", key
        self.form_roles = dict(entry.roles or {})
        self.form_options = {**default_options(METHODS[key]), **(entry.options or {})}
        self.form_confirms = {}
        self.message = (self.app.t("analyze.rerun", title=entry.title), "info")
        self.app.navigate("analyze")

    def reset(self) -> None:
        """Forget choices made for another project's data."""
        self.goal, self.selection, self.confirms, self.override = None, {}, {}, None
        self.choosing_goal = False
        self.method, self.form_roles, self.form_options, self.form_confirms = None, {}, {}, {}
        self.message = None

    # ----------------------------------------------------------- layout
    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        switch = wc.segmented(ui, [("guided", ui.t("analyze.mode.guided")),
                                   ("all", ui.t("analyze.mode.all"))], self.mode,
                              self._set_mode, data="analyze-mode")
        header = wc.page_header(ui, ui.t("analyze.title"), ui.t("analyze.subtitle"),
                                actions=[switch])
        if not app.session.has_data:
            body = [wc.empty_state(ui, ft.Icons.QUERY_STATS, ui.t("data.empty.title"),
                                   ui.t("analyze.needs_data"), actions=[
                                       wc.button(ui, ui.t("data.open"),
                                                 action=app.open_data_action, kind="primary"),
                                       wc.button(ui, ui.t("data.sample"),
                                                 self._load_sample)])]
        elif self.mode == "guided":
            body = self._guided()
        elif self.method:
            body = self._method_form()
        else:
            body = self._catalog()
        if self.message:
            body.append(wc.notice(ui, self.message[0], self.message[1], data="analyze-message"))
        return app.constrained(ft.Column([header, *body], spacing=tk.SPACE_5,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH))

    def _set_mode(self, mode: str):
        self.mode = mode
        self.message = None
        self.app.render()

    async def _load_sample(self, e=None):
        await self.app.load_sample("sample_scale.csv")
        self.app.navigate("analyze")

    # ----------------------------------------------------------- guided
    def _guided(self) -> list[ft.Control]:
        ui, s = self.app.ui, self.app.session
        goal_tiles = []
        for goal in GOALS:
            selected = goal == self.goal
            goal_tiles.append(ft.Container(
                content=ft.Row([
                    ft.Icon(GOAL_ICONS[goal], color=ui.p.accent, size=22),
                    ft.Column([wc.text(ui, ui.t(f"goal.{goal}"), tk.TYPE_LABEL,
                                       weight=ft.FontWeight.W_600),
                               wc.caption(ui, ui.t(f"goal.{goal}.body"),
                                          color=ui.p.text_secondary)],
                              spacing=2, expand=True),
                ], spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.START),
                bgcolor=ui.p.accent_subtle if selected else ui.p.surface,
                border=ft.Border.all(1.5 if selected else 1,
                                     ui.p.accent if selected else ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_4, ink=True,
                on_click=lambda e, g=goal: self._set_goal(g), data=f"goal-{goal}",
                col={"xs": 12, "md": 6, "xl": 3}, tooltip=ui.t(f"goal.{goal}.body"),
            ))
        if self.goal and not self.choosing_goal:
            # Progressive disclosure: the chosen question stays in view as one
            # line, so the variables, checks and the run button move up.
            chosen_goal = ft.Row([
                ft.Icon(GOAL_ICONS[self.goal], color=ui.p.accent, size=22),
                ft.Column([wc.text(ui, ui.t(f"goal.{self.goal}"), tk.TYPE_LABEL,
                                   weight=ft.FontWeight.W_600, data="goal-summary"),
                           wc.caption(ui, ui.t(f"goal.{self.goal}.body"))],
                          spacing=2, expand=True),
                wc.button(ui, ui.t("analyze.change_goal"), self._change_goal, kind="quiet",
                          icon=ft.Icons.EDIT_OUTLINED, data="goal-change"),
            ], spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER)
            goal_content = [chosen_goal]
        else:
            goal_content = [ft.ResponsiveRow(goal_tiles, spacing=tk.SPACE_3,
                                             run_spacing=tk.SPACE_3)]
        steps = [wc.step_card(
            ui, 1, ui.t("step.goal"), goal_content,
            state="done" if self.goal else "active", data="step-goal")]
        if not self.goal:
            steps += [wc.step_card(ui, 2, ui.t("step.variables"), [], state="locked"),
                      wc.step_card(ui, 3, ui.t("step.design"), [], state="locked"),
                      wc.step_card(ui, 4, ui.t("step.method"), [], state="locked")]
            return steps
        steps.append(wc.step_card(ui, 2, ui.t("step.variables"), self._role_pickers(),
                                  state="active", data="step-variables"))
        advice = advise(self.goal, self.selection, s)
        chosen = self._chosen(advice)
        steps.append(wc.step_card(ui, 3, ui.t("step.design"), self._design(advice, chosen),
                                  state="active" if self._roles_filled() else "locked",
                                  data="step-design"))
        steps.append(wc.step_card(ui, 4, ui.t("step.method"), self._recommendation(advice, chosen),
                                  state="active" if advice.ready else "locked",
                                  data="step-method"))
        return steps

    def _set_goal(self, goal: str):
        if goal != self.goal:
            self.goal, self.selection, self.confirms, self.override = goal, {}, {}, None
            self.message = None
        self.choosing_goal = False
        self.app.render()

    def _change_goal(self, e=None):
        """Show every question again (the current one stays selected)."""
        self.choosing_goal = True
        self.app.render()

    def _roles_filled(self) -> bool:
        for role in GOAL_ROLES.get(self.goal, ()):
            value = self.selection.get(role.key)
            if not role.optional and not value:
                return False
        return True

    def _role_pickers(self) -> list[ft.Control]:
        ui, s = self.app.ui, self.app.session
        controls: list[ft.Control] = []
        for role in GOAL_ROLES[self.goal]:
            options = _variable_options(ui, s)
            if role.multiple:
                chosen = list(self.selection.get(role.key) or [])
                boxes = [wc.checkbox(ui, label, name in chosen,
                                     on_change=lambda e, r=role.key, n=name: self._toggle(r, n,
                                                                                          e.control.value),
                                     data=f"role-{role.key}-{name}")
                         for name, label in options]
                controls += [wc.section_label(ui, ui.t(role.label)),
                             ft.Container(ft.Row(boxes, wrap=True, spacing=tk.SPACE_4,
                                                 run_spacing=0),
                                          data=f"role-{role.key}")]
            else:
                if role.optional:
                    options = [("", ui.t("role.none"))] + options
                controls.append(wc.dropdown(
                    ui, ui.t(role.label), options, self.selection.get(role.key),
                    on_select=lambda e, r=role.key: self._pick(r, e.control.value),
                    width=360, data=f"role-{role.key}"))
        return [ft.Row(controls[:2], wrap=True, spacing=tk.SPACE_4)] + controls[2:] \
            if not any(r.multiple for r in GOAL_ROLES[self.goal]) else controls

    def _pick(self, role: str, value):
        self.selection[role] = value or None
        self.override = None
        self.app.render()

    def _toggle(self, role: str, name: str, value: bool):
        chosen = list(self.selection.get(role) or [])
        if value and name not in chosen:
            chosen.append(name)
        if not value and name in chosen:
            chosen.remove(name)
        self.selection[role] = chosen
        self.override = None
        self.app.render()

    def _chosen(self, advice):
        if not advice.ready:
            return None
        if self.override and self.override[0] in METHODS:
            key, options = self.override
            return key, {**advice.options, **options}, advice.roles
        return advice.method, advice.options, advice.roles

    def _design(self, advice, chosen) -> list[ft.Control]:
        ui, s = self.app.ui, self.app.session
        controls: list[ft.Control] = []
        names = []
        for role in GOAL_ROLES[self.goal]:
            value = self.selection.get(role.key)
            names += list(value) if isinstance(value, list) else ([value] if value else [])
        level_rows = []
        for name in names:
            info = s.variables.get(name)
            if info is None or info.suggested == "id":
                continue
            options = [(lvl, ui.t(f"level.{lvl}")) for lvl in LEVELS if lvl != "id"]
            level_rows.append(wc.dropdown(
                ui, ui.t("design.level_of", name=name), options, info.confirmed,
                on_select=lambda e, n=name: self._confirm_level(n, e.control.value),
                width=300, data=f"design-level-{name}"))
        if level_rows:
            controls.append(ft.Row(level_rows, wrap=True, spacing=tk.SPACE_3,
                                   run_spacing=tk.SPACE_3))
        if advice.blockers:
            controls.append(wc.notice(
                ui, problems_text(ui, advice.blockers), "warning", title=ui.t("design.blocked"),
                data="design-blockers"))
            return controls
        for key, params in advice.reasons[:1]:
            if key == "design.groups_found":
                controls.append(wc.chip(ui, ui.t(key, **params), "info", icon=ft.Icons.GROUPS))
        if chosen:
            spec = METHODS[chosen[0]]
            for confirmation in required_confirmations(spec, chosen[1]):
                controls.append(wc.checkbox(
                    ui, engine_label(ui.language, confirmation.label),
                    bool(self.confirms.get(confirmation.key)),
                    on_change=lambda e, k=confirmation.key: self._confirm(k, e.control.value),
                    data=f"design-confirm-{confirmation.key}"))
        return controls

    def _confirm_level(self, name: str, level: str):
        self.app.session.confirm_level(name, level or "unknown", "analyze")
        self.override = None
        self.app.status(self.app.t("design.saved_level"), "success")
        self.app.render()

    def _confirm(self, key: str, value: bool):
        self.confirms[key] = bool(value)
        self.app.render()

    def _recommendation(self, advice, chosen) -> list[ft.Control]:
        ui = self.app.ui
        if not chosen:
            return []
        key, options, roles = chosen
        label = method_label(key, options)
        reasons = [wc.text(ui, "• " + ui.t(k, **p), tk.TYPE_BODY)
                   for k, p in advice.reasons if k != "design.groups_found"]
        alternatives = []
        candidates = list(advice.alternatives)
        if self.override:
            candidates = [a for a in candidates if (a.method, a.options) != self.override]
            from workspace_methods import Alternative
            candidates.insert(0, Alternative(advice.method, advice.options, ""))
        for alternative in candidates:
            alt_label = method_label(alternative.method, {**advice.options, **alternative.options})
            alternatives.append(ft.Row([
                ft.Column([wc.text(ui, alt_label, tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                           *([wc.caption(ui, ui.t(alternative.note), color=ui.p.text_secondary)]
                             if alternative.note else [])], spacing=2, expand=True),
                wc.button(ui, ui.t("rec.use_instead"),
                          lambda e, a=alternative: self._use(a.method, a.options), kind="quiet",
                          data=f"alt-{alternative.method}-{alternative.options.get('method', '')}"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        spec = METHODS[key]
        missing = [c for c in required_confirmations(spec, options)
                   if not self.confirms.get(c.key)]
        run = wc.button(ui, ui.t("rec.run", method=label), self._run_guided, kind="primary",
                        icon=ft.Icons.PLAY_ARROW, disabled=bool(missing) or self.running,
                        tooltip=ui.t("disabled.confirm_first") if missing else None,
                        data="guided-run")
        controls: list[ft.Control] = [
            ft.Row([wc.heading(ui, label, tk.TYPE_TITLE_M, data="guided-method"),
                    wc.chip(ui, ui.t("rec.chosen") if self.override else ui.t("rec.recommended"),
                            "warning" if self.override else "success",
                            icon=ft.Icons.TUNE if self.override else ft.Icons.VERIFIED_OUTLINED)],
                   spacing=tk.SPACE_3, wrap=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            wc.section_label(ui, ui.t("rec.why")), *reasons,
        ]
        if alternatives:
            controls += [wc.section_label(ui, ui.t("rec.alternatives")), *alternatives]
        controls += [
            wc.notice(ui, ui.t("rec.not_automatic"), "neutral"),
            ft.Row([run, wc.button(ui, ui.t("rec.open_advanced"),
                                   lambda e: self._open_in_form(key, options, roles),
                                   kind="quiet")], wrap=True, spacing=tk.SPACE_3),
        ]
        if self.running:
            controls.append(ft.Row([ft.ProgressRing(width=18, height=18, stroke_width=2),
                                    wc.text(ui, ui.t("run.running"))], spacing=tk.SPACE_2))
        return controls

    def _use(self, method: str, options: dict):
        self.override = (method, dict(options))
        self.app.render()

    def _open_in_form(self, key: str, options: dict, roles: dict):
        self.mode, self.method = "all", key
        self.form_roles = dict(roles)
        self.form_options = {**default_options(METHODS[key]), **options}
        self.form_confirms = {k: v for k, v in self.confirms.items()}
        self.app.render()

    async def _run_guided(self, e=None):
        advice = advise(self.goal, self.selection, self.app.session)
        chosen = self._chosen(advice)
        if chosen:
            await self._execute(chosen[0], chosen[2], chosen[1], self.confirms)

    async def run_current(self):
        """Ctrl+Enter: run whatever analysis is ready on screen."""
        if self.mode == "guided" and self.goal:
            advice = advise(self.goal, self.selection, self.app.session)
            chosen = self._chosen(advice)
            if chosen and not [c for c in required_confirmations(METHODS[chosen[0]], chosen[1])
                               if not self.confirms.get(c.key)]:
                await self._execute(chosen[0], chosen[2], chosen[1], self.confirms)
        elif self.mode == "all" and self.method:
            await self._run_form()

    async def _execute(self, key: str, roles: dict, options: dict, confirms: dict):
        app = self.app
        self.running, self.message = True, None
        app.render()
        # A result belongs to the data and project it was calculated on.
        started = (app.projects.generation, id(app.session.df))
        try:
            run = await asyncio.to_thread(run_method, key, app.session, roles, options, confirms)
        except RoleProblems as error:
            # Explained in the researcher's language, never as internal codes.
            self.running = False
            self.message = (app.t("run.blocked") + "\n" + problems_text(app.ui, error.problems),
                            "warning")
            app.status(app.t("run.blocked"), "warning")
            app.render()
            return None
        except Exception as error:
            self.running = False
            self.message = (app.t("run.failed", error=error), "danger")
            app.render()
            return None
        self.running = False
        if (app.projects.generation, id(app.session.df)) != started:
            self.message = (app.t("run.discarded"), "warning")
            app.status(self.message[0], "warning")
            app.render()
            return None
        confirmed = [c.label for c in METHODS[key].confirmations if confirms.get(c.key)]
        entry = app.session.add_result(
            run, confirmed, method=key, roles=dict(roles),
            options={**default_options(METHODS[key]), **options}, confirms=dict(confirms))
        app.status(app.t("run.done"), "success")
        app.navigate("results")
        return entry

    # ------------------------------------------------------ all methods
    def _catalog(self) -> list[ft.Control]:
        ui = self.app.ui
        query = self.search.strip().lower()
        sections: list[ft.Control] = [
            ft.Row([wc.text_field(ui, ui.t("catalog.search"), self.search, width=360,
                                  on_change=self._search, data="catalog-search"),
                    wc.caption(ui, ui.t("catalog.hint"))], wrap=True, spacing=tk.SPACE_4,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]
        shown = 0
        for family in FAMILIES:
            cards = []
            for spec in METHODS.values():
                haystack = f"{spec.title} {spec.summary} {spec.section}".lower()
                if spec.family != family or (query and query not in haystack):
                    continue
                shown += 1
                cards.append(ft.Container(
                    content=ft.Column([
                        wc.text(ui, spec.title, tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                        wc.caption(ui, spec.summary, color=ui.p.text_secondary),
                    ], spacing=tk.SPACE_1),
                    bgcolor=ui.p.surface, border=ft.Border.all(1, ui.p.border),
                    border_radius=ui.radius("card"), padding=tk.SPACE_4, ink=True,
                    on_click=lambda e, k=spec.key: self._open_method(k),
                    col={"xs": 12, "md": 6, "xl": 4}, data=f"method-{spec.key}",
                    tooltip=spec.summary,
                ))
            if cards:
                sections += [wc.heading(ui, ui.t(f"fam.{family}"), tk.TYPE_TITLE_S),
                             ft.ResponsiveRow(cards, spacing=tk.SPACE_3, run_spacing=tk.SPACE_3)]
        if not shown:
            sections.append(wc.caption(ui, ui.t("catalog.none")))
        return sections

    def _search(self, e):
        self.search = e.control.value or ""
        self.app.render()

    def _open_method(self, key: str):
        self.method = key
        self.form_roles, self.form_confirms = {}, {}
        self.form_options = default_options(METHODS[key])
        self.message = None
        self.app.render()

    def _method_form(self) -> list[ft.Control]:
        ui, s = self.app.ui, self.app.session
        spec = METHODS[self.method]
        roles: list[ft.Control] = []
        for role in spec.roles:
            options = _variable_options(ui, s)
            if role.multiple:
                chosen = list(self.form_roles.get(role.key) or [])
                roles += [wc.section_label(ui, ui.t(role.label)), ft.Row([
                    wc.checkbox(ui, label, name in chosen,
                                on_change=lambda e, r=role.key, n=name: self._form_toggle(
                                    r, n, e.control.value),
                                data=f"form-{role.key}-{name}")
                    for name, label in options], wrap=True, spacing=tk.SPACE_4)]
            else:
                if role.optional:
                    options = [("", ui.t("role.none"))] + options
                roles.append(wc.dropdown(
                    ui, ui.t(role.label), options, self.form_roles.get(role.key),
                    on_select=lambda e, r=role.key: self._form_pick(r, e.control.value),
                    width=340, data=f"form-{role.key}"))
        option_controls = [wc.dropdown(
            ui, engine_label(ui.language, option.label),
            [(k, engine_label(ui.language, v)) for k, v in option.choices],
            self.form_options.get(option.key, option.default),
            on_select=lambda e, k=option.key: self._form_option(k, e.control.value),
            width=320, data=f"form-option-{option.key}") for option in spec.options]
        confirmations = [wc.checkbox(
            ui, engine_label(ui.language, c.label), bool(self.form_confirms.get(c.key)),
            on_change=lambda e, k=c.key: self._form_confirm(k, e.control.value),
            data=f"form-confirm-{c.key}")
            for c in required_confirmations(spec, self.form_options)]
        from workspace_methods import role_problems
        problems = role_problems(spec, self.form_roles, s)
        unknown = [p["name"] for k, p in problems if k == "design.confirm_level"]
        level_fixes = [wc.dropdown(
            ui, ui.t("design.level_of", name=name),
            [(lvl, ui.t(f"level.{lvl}")) for lvl in LEVELS if lvl != "id"], "unknown",
            on_select=lambda e, n=name: self._confirm_level(n, e.control.value), width=300,
            data=f"form-level-{name}") for name in unknown]
        missing = [c for c in required_confirmations(spec, self.form_options)
                   if not self.form_confirms.get(c.key)]
        content: list[ft.Control] = [
            ft.Row(roles, wrap=True, spacing=tk.SPACE_4) if not any(r.multiple for r in spec.roles)
            else ft.Column(roles, spacing=tk.SPACE_2)]
        if level_fixes:
            content.append(ft.Row(level_fixes, wrap=True, spacing=tk.SPACE_3))
        if option_controls:
            content += [wc.section_label(ui, ui.t("form.options")),
                        ft.Row(option_controls, wrap=True, spacing=tk.SPACE_3)]
        if confirmations:
            content += [wc.section_label(ui, ui.t("form.confirmations")), *confirmations]
        other = [p for p in problems if p[0] != "design.confirm_level"]
        if other:
            content.append(wc.notice(ui, problems_text(ui, other), "warning",
                                     data="form-problems"))
        content.append(ft.Row([
            wc.button(ui, ui.t("form.run"), self._run_form, kind="primary",
                      icon=ft.Icons.PLAY_ARROW, disabled=bool(problems or missing) or self.running,
                      tooltip=(ui.t("disabled.resolve_first") if problems else
                               ui.t("disabled.confirm_first") if missing else None),
                      data="form-run"),
            wc.button(ui, ui.t("form.back"), self._back, kind="quiet", icon=ft.Icons.ARROW_BACK),
        ], spacing=tk.SPACE_3))
        return [wc.card(ui, content, title=spec.title, description=spec.summary,
                        data=f"form-{spec.key}")]

    def _form_pick(self, role, value):
        self.form_roles[role] = value or None
        self.app.render()

    def _form_toggle(self, role, name, value):
        chosen = list(self.form_roles.get(role) or [])
        if value and name not in chosen:
            chosen.append(name)
        if not value and name in chosen:
            chosen.remove(name)
        self.form_roles[role] = chosen
        self.app.render()

    def _form_option(self, key, value):
        self.form_options[key] = value
        self.app.render()

    def _form_confirm(self, key, value):
        self.form_confirms[key] = bool(value)
        self.app.render()

    def _back(self, e=None):
        self.method = None
        self.message = None
        self.app.render()

    async def _run_form(self, e=None):
        if self.method:
            await self._execute(self.method, self.form_roles, self.form_options, self.form_confirms)


# ================================================================= results
class ResultsPage:
    def __init__(self, app):
        self.app = app
        self.opened: set[str] = set()      # expanded sections (kept across renders)
        self._seen: set[int] = set()
        self.depth: str | None = None   # interpretation: "student" or "professor"
        self.reviewed: dict[int, set[str]] = {}
        self.notes: dict[int, str] = {}
        self.feedback: dict[int, tuple[str, str]] = {}
        self.figure_number = "1"

    def build(self) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        header = wc.page_header(ui, ui.t("results.title"), ui.t("results.subtitle"))
        if not s.results:
            return app.constrained(ft.Column([header, wc.empty_state(
                ui, ft.Icons.INSIGHTS_OUTLINED, ui.t("results.empty.title"),
                ui.t("results.empty.body"), actions=[
                    wc.button(ui, ui.t("nav.analyze"), lambda e: app.navigate("analyze"),
                              kind="primary")], data="results-empty")], spacing=tk.SPACE_5))
        entry = s.result(s.selected_result) or s.results[-1]
        detail = self._detail(entry)
        if app.compact:
            picker = wc.dropdown(ui, ui.t("results.title"),
                                 [(str(r.id), f"{r.id}. {r.title}") for r in reversed(s.results)],
                                 str(entry.id), on_select=lambda e: self._select(int(e.control.value)),
                                 width=420, data="results-picker")
            body = ft.Column([header, picker, detail], spacing=tk.SPACE_4)
        else:
            body = ft.Column([header, ft.Row([
                ft.Container(self._log(entry), width=tk.PANE_LIST_WIDTH),
                ft.Container(detail, expand=True),
            ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=tk.SPACE_5)],
                spacing=tk.SPACE_4)
        return app.constrained(ft.Column(
            [body, wc.caption(self.app.ui, session_note(app), data="results-note")],
            spacing=tk.SPACE_3), tk.CONTENT_MAX_WIDTH + 200)

    def _select(self, entry_id: int):
        self.app.session.selected_result = entry_id
        self.app.render()

    def _log(self, current) -> ft.Control:
        ui = self.app.ui
        items = []
        for entry in reversed(self.app.session.results):
            selected = entry.id == current.id
            items.append(ft.Container(
                content=ft.Column([
                    wc.text(ui, entry.title, tk.TYPE_LABEL, weight=ft.FontWeight.W_600,
                            max_lines=2),
                    wc.caption(ui, f"{entry.dataset} · {entry.created:%H:%M}"),
                    *([wc.chip(ui, ui.t("results.in_report"), "success",
                               icon=ft.Icons.DESCRIPTION_OUTLINED)] if entry.in_report else []),
                    *([wc.chip(ui, ui.t("results.stale"), "warning", icon=ft.Icons.UPDATE,
                               data=f"result-stale-{entry.id}")] if entry.stale_reasons else []),
                ], spacing=2),
                bgcolor=ui.p.accent_subtle if selected else ui.p.surface,
                border=ft.Border.all(1, ui.p.accent if selected else ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_3, ink=True,
                on_click=lambda e, i=entry.id: self._select(i), data=f"result-{entry.id}",
            ))
        return ft.Column(items, spacing=tk.SPACE_2, data="results-log",
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    # ------------------------------------------------------------- detail
    def _detail(self, entry) -> ft.Control:
        ui = self.app.ui
        run = entry.run
        evidence = run.evidence()
        reviewed = self.reviewed.setdefault(entry.id, set())
        rows = list(evidence.rows)
        estimates = [wc.stat(ui, row.parameter, row.estimate,
                             " · ".join(x for x in (
                                 f"{ui.t('est.ci')} {row.ci}" if row.ci != "Not calculated" else "",
                                 f"p {row.p}" if row.p != "Not calculated" else "") if x),
                             col={"xs": 12, "sm": 6, "lg": 4})
                     for row in rows[:6]]
        answer = run.interpretation or run.summary
        sections: list[ft.Control] = [
            ft.Row([
                ft.Column([wc.heading(ui, run.title, tk.TYPE_TITLE_M, data="result-title"),
                           wc.caption(ui, f"{evidence.method} · {entry.dataset}")],
                          spacing=2, expand=True),
                self._report_toggle(entry),
            ], vertical_alignment=ft.CrossAxisAlignment.START),
        ]
        if entry.stale_reasons:
            from workspace_projects import stale_text

            reasons = "; ".join(stale_text(ui, reason) for reason in entry.stale_reasons)
            rerun = [] if entry.method is None else [wc.button(
                ui, ui.t("results.recalculate"), lambda e, i=entry.id: self._rerun(i),
                kind="primary", icon=ft.Icons.REFRESH, disabled=not self.app.session.has_data,
                data="result-recalculate")]
            sections.append(wc.notice(ui, ui.t("results.stale_body", reasons=reasons), "warning",
                                      title=ui.t("results.stale_title"), actions=rerun,
                                      data="result-stale"))
        summary_card = figure_card = None
        wide = self._wide_detail()
        if answer:
            summary_card = wc.card(ui, [wc.text(ui, answer, tk.TYPE_BODY_L, selectable=True,
                                                data="result-answer")],
                                   title=ui.t("results.answer"), data="result-summary")
        if run.png:
            from apa_figures import section_embeds_figure_header

            embedded = section_embeds_figure_header(run.section)
            figure_card = wc.card(ui, [wc.figure(
                ui, run.png, caption_text="" if embedded else run.title,
                on_enlarge=lambda e: self._enlarge(run), enlarge_label=ui.t("results.enlarge"),
                max_height=360 if wide and answer else 460)],
                title=ui.t("results.figure"), data="result-figure")
        # The primary result first: the summary and its figure, side by side
        # when the detail column is wide enough, before estimates and tables.
        if summary_card is not None and figure_card is not None and wide:
            sections.append(ft.Row([ft.Container(summary_card, expand=1),
                                    ft.Container(figure_card, expand=1)],
                                   spacing=tk.SPACE_4, data="result-primary",
                                   vertical_alignment=ft.CrossAxisAlignment.START))
        else:
            sections += [card for card in (summary_card, figure_card) if card is not None]
        if estimates:
            sections.append(wc.card(ui, [ft.ResponsiveRow(estimates, spacing=tk.SPACE_3,
                                                          run_spacing=tk.SPACE_3)],
                                    title=ui.t("results.estimates"), data="result-estimates"))
        tables: list[ft.Control] = []
        if rows:
            dash = lambda value: "—" if value == "Not calculated" else value  # noqa: E731
            tables.append(wc.apa_table(
                ui, ("Parameter", "Estimate", "95% CI", "p"),
                tuple((r.parameter, r.estimate, dash(r.ci), dash(r.p)) for r in rows),
                number=1, title=f"{run.title}: verified estimates",
                note=ui.t("results.sig_note") + " " + ui.t("results.dash_note")))
        for number, table in enumerate(run.tables, start=2 if rows else 1):
            tables.append(wc.apa_table(ui, table.columns, table.rows, number=number,
                                       title=table.title, note=ui.t("results.sig_note")))
        if run.section == "omnibus" and not run.tables:
            tables.append(wc.button(ui, ui.t("results.posthoc"),
                                    lambda e, i=entry.id: self._posthoc(i),
                                    icon=ft.Icons.COMPARE_ARROWS, data="result-posthoc"))
        sections.append(wc.card(ui, tables or [wc.caption(ui, ui.t("results.no_table"))],
                                title=ui.t("results.table"), data="result-table"))
        checks = [wc.checkbox(ui, assumption, assumption in reviewed,
                              on_change=lambda e, a=assumption, i=entry.id: self._review(
                                  i, a, e.control.value), data=f"review-{index}")
                  for index, assumption in enumerate(evidence.assumptions)]
        unreviewed = len([a for a in evidence.assumptions if a not in reviewed])
        cautions = [wc.text(ui, "• " + w, tk.TYPE_BODY, color=ui.p.text_secondary, selectable=True)
                    for w in evidence.warnings]
        sections.append(wc.card(ui, [
            *checks,
            *([wc.chip(ui, ui.t("results.unreviewed", count=unreviewed), "warning")]
              if unreviewed else []),
            wc.text(ui, evidence.limitation, tk.TYPE_BODY, color=ui.p.text_secondary),
            *cautions,
        ], title=ui.t("results.checks"), data="result-checks"))
        from interpretation_wizard import interpretation_summary

        notes = wc.text_field(ui, "Researcher interpretation (optional, unverified)",
                              self.notes.get(entry.id, ""), multiline=True,
                              on_change=lambda e, i=entry.id: self.notes.__setitem__(
                                  i, e.control.value or ""))
        if entry.id not in self._seen:
            # "Detailed" explanations (optional profile) open the interpretation
            # once; afterwards the researcher's own choice is kept.
            self._seen.add(entry.id)
            if self.app.profile.explanations == "detailed":
                self.opened.add(f"interpretation-{entry.id}")
        unverified = [a for a in evidence.assumptions if a not in reviewed]
        depth = self.depth or self._default_depth()
        if depth == "professor":
            explained = [wc.text(ui, interpretation_summary(evidence, reviewed,
                                                            self.notes.get(entry.id, "")),
                                 tk.TYPE_BODY, selectable=True, data="result-interpretation")]
            from statistical_guide import method_guide_text

            guide = method_guide_text(run.section, ui.language)
            if guide:
                explained.append(wc.expansion(
                    ui, wc.text(ui, ui.t("depth.method_notes"), tk.TYPE_LABEL,
                                weight=ft.FontWeight.W_600),
                    [ft.Container(wc.text(ui, guide, tk.TYPE_BODY, selectable=True),
                                  padding=tk.SPACE_3)],
                    key=f"guide-{entry.id}", opened=self.opened, data="result-method-notes"))
        else:
            explained = [
                wc.section_label(ui, ui.t("depth.plain")),
                wc.text(ui, run.interpretation or run.summary, tk.TYPE_BODY, selectable=True,
                        data="result-interpretation"),
                wc.section_label(ui, ui.t("depth.main_result")),
                wc.text(ui, run.summary, tk.TYPE_BODY, selectable=True),
                wc.section_label(ui, ui.t("depth.not_shown")),
                wc.text(ui, evidence.limitation, tk.TYPE_BODY, selectable=True),
            ]
        # Unverified decisions are always labelled, at both depths.
        labels = ([wc.notice(ui, ui.t("depth.unverified", count=len(unverified))
                             + "\n" + "\n".join("• " + a for a in unverified), "warning",
                             data="result-unverified")] if unverified else
                  [wc.notice(ui, ui.t("depth.all_reviewed"), "success", data="result-unverified")])
        sections.append(wc.expansion(
            ui, wc.heading(ui, ui.t("results.interpretation"), tk.TYPE_TITLE_S),
            [ft.Container(ft.Column([
                wc.segmented(ui, [("student", ui.t("depth.student")),
                                  ("professor", ui.t("depth.professor"))], depth,
                             self._set_depth, data="result-depth"),
                *labels,
                *explained,
                notes,
            ], spacing=tk.SPACE_3), padding=tk.SPACE_4)],
            key=f"interpretation-{entry.id}", opened=self.opened,
            subtitle=wc.caption(ui, ui.t("results.interpretation_hint")),
            data="result-interpretation-section"))
        sections.append(wc.expansion(
            ui, wc.heading(ui, ui.t("results.report"), tk.TYPE_TITLE_S),
            [ft.Container(wc.text(ui, run.report, tk.TYPE_BODY, selectable=True,
                                  data="result-report"), padding=tk.SPACE_4)],
            key=f"report-{entry.id}", opened=self.opened, data="result-report-section"))
        provenance = self._provenance(entry, evidence)
        sections.append(wc.card(ui, provenance, title=ui.t("results.provenance"),
                                data="result-provenance"))
        sections.append(self._exports(entry, evidence, reviewed))
        return ft.Column(sections, spacing=tk.SPACE_4, data=f"result-detail-{entry.id}",
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    def _provenance(self, entry, evidence) -> list[ft.Control]:
        """What the numbers rest on (Issue #32): the dataset version, complete
        cases, how each variable was coded, the method's options and who
        confirmed what. Nothing here is estimated or invented."""
        from workspace_methods import METHODS

        ui, run, facts = self.app.ui, entry.run, entry.provenance or {}
        dataset = f"{entry.dataset} · {count_text(ui.language, entry.rows, 'rows')}"
        if facts.get("dataset_sha256"):
            dataset += " · " + ui.t("prov.version", sha=facts["dataset_sha256"][:12])
        rows = [wc.labeled(ui, ui.t("results.dataset"), dataset)]
        complete, total = evidence.n_complete, evidence.n_total
        if complete is None and facts.get("complete") is not None:
            complete, total = facts["complete"], facts.get("rows")
        if complete is not None and total:
            rows.append(wc.labeled(ui, ui.t("prov.complete"), ui.t(
                "prov.complete_value", complete=complete, total=total,
                missing=max(0, int(total) - int(complete)))))
        levels = facts.get("levels") or {}
        if levels:
            coded = []
            for name, level in levels.items():
                text = f"{name}: {ui.t('level.' + level) if level else '—'}"
                labels = (facts.get("groups") or {}).get(name)
                if labels:
                    text += f" ({', '.join(str(x) for x in labels)})"
                if (facts.get("confirmed_in") or {}).get(name) == "data-bulk":
                    text += " · " + ui.t("prov.bulk")
                coded.append(text)
            rows.append(wc.labeled(ui, ui.t("prov.coding"), "; ".join(coded)))
        else:
            rows.append(wc.labeled(ui, ui.t("results.variables"), "; ".join(
                f"{k} = {v}" for k, v in run.inputs.items() if v not in (None, "", []))))
        spec = METHODS.get(entry.method) if entry.method else None
        if spec is not None:
            options = "; ".join(
                f"{engine_label(ui.language, o.label)} = "
                f"{engine_label(ui.language, dict(o.choices).get((entry.options or {}).get(o.key, o.default), ''))}"
                for o in spec.options)
            rows.append(wc.labeled(ui, ui.t("prov.method"),
                                   spec.title + (f" · {options}" if options else "")))
        rows += [
            wc.labeled(ui, ui.t("results.confirmed"), "; ".join(entry.confirmations) or "—"),
            wc.labeled(ui, ui.t("results.time"), f"{entry.created:%Y-%m-%d %H:%M:%S}"
                       + (" · " + ui.t("prov.restored") if entry.restored else "")),
            wc.labeled(ui, ui.t("results.engine"), f"analysis_runs · {run.section}"),
        ]
        return rows

    def _default_depth(self) -> str:
        """Doctoral and faculty profiles start with the technical depth."""
        return "professor" if self.app.profile.study_level in ("doctoral", "faculty") \
            else "student"

    def _set_depth(self, value: str):
        self.depth = value if value in ("student", "professor") else "student"
        self.app.render()

    def _wide_detail(self) -> bool:
        """Room for the summary and the figure next to each other (≥ 1000 px)."""
        app = self.app
        width = min(tk.CONTENT_MAX_WIDTH + 200, app.content_width)
        if not app.compact:
            width -= tk.PANE_LIST_WIDTH + tk.SPACE_5
        return width >= 1000

    def _report_toggle(self, entry) -> ft.Control:
        ui = self.app.ui
        return wc.button(
            ui, ui.t("results.in_report") if entry.in_report else ui.t("results.add_report"),
            lambda e, i=entry.id: self._toggle_report(i),
            kind="secondary" if entry.in_report else "primary",
            icon=ft.Icons.CHECK if entry.in_report else ft.Icons.PLAYLIST_ADD,
            data="result-add-report")

    def _toggle_report(self, entry_id: int):
        self.app.session.toggle_report(entry_id)
        self.app.render()

    def _review(self, entry_id: int, assumption: str, value: bool):
        reviewed = self.reviewed.setdefault(entry_id, set())
        (reviewed.add if value else reviewed.discard)(assumption)
        self.app.render()

    def _enlarge(self, run):
        ui = self.app.ui
        dialog = ft.AlertDialog(
            title=wc.heading(ui, run.title, tk.TYPE_TITLE_S),
            content=ft.Container(ft.Image(src=run.png, fit=ft.BoxFit.CONTAIN),
                                 width=min(1100, self.app.content_width),
                                 bgcolor="#FFFFFF"),
            actions=[wc.button(ui, ui.t("common.close"),
                               lambda e: self.app.page.pop_dialog())],
        )
        self.app.page.show_dialog(dialog)

    async def _posthoc(self, entry_id: int):
        from analysis_runs import run_posthoc

        entry = self.app.session.result(entry_id)
        if not await self.app.projects.ensure_result(entry):
            self.feedback[entry_id] = (self.app.t("results.not_reproducible"), "warning")
            self.app.render()
            return
        try:
            run = await asyncio.to_thread(run_posthoc, entry.run)
        except Exception as error:
            self.feedback[entry_id] = (self.app.t("run.failed", error=error), "danger")
            self.app.render()
            return
        if entry.method == "omnibus":
            entry.method = "posthoc"   # how the project reproduces it
        self.app.session.replace_run(entry_id, run)
        self.app.render()

    def _rerun(self, entry_id: int):
        entry = self.app.session.result(entry_id)
        if entry is not None and entry.method:
            self.app.pages["analyze"].rerun(entry)

    # ------------------------------------------------------------- exports
    def complete_report(self, run) -> str:
        """The classic 'complete_output': report + cited method notes."""
        from statistical_guide import method_guide_text

        notes = method_guide_text(run.section, self.app.session.language)
        return run.report + ("\n\n---\n" + notes if notes else "")

    def _exports(self, entry, evidence, reviewed) -> ft.Control:
        ui = self.app.ui
        run = entry.run
        figure_number = wc.text_field(ui, "Figure number", self.figure_number, width=150,
                                      on_change=lambda e: setattr(self, "figure_number",
                                                                  e.control.value or "1"))
        # The outcome of the last save or copy sits right under the buttons.
        feedback = ([wc.notice(ui, *self.feedback[entry.id], data="result-feedback")]
                    if entry.id in self.feedback else [])
        settings = wc.caption(ui, ui.t(
            "prov.export_settings", reviewed=len([a for a in evidence.assumptions if a in reviewed]),
            total=len(evidence.assumptions), figure=self.figure_number or "1",
            title=self.app.pages["reports"].study_title or "—",
            notes=ui.t("common.yes") if self.notes.get(entry.id, "").strip() else ui.t("common.no")),
            data="result-export-settings")
        return wc.card(ui, [ft.Row([
            wc.button(ui, ui.t("results.copy"), lambda e, i=entry.id: self._copied(i),
                      action=ft.CopyToClipboard(self.complete_report(run)),
                      icon=ft.Icons.CONTENT_COPY, data="export-copy"),
            wc.button(ui, ui.t("results.save_txt"), lambda e: self._save(entry, "text"),
                      icon=ft.Icons.TEXT_SNIPPET_OUTLINED, data="export-txt"),
            wc.button(ui, ui.t("results.save_png"), lambda e: self._save(entry, "image"),
                      icon=ft.Icons.IMAGE_OUTLINED, disabled=not run.png,
                      tooltip=None if run.png else ui.t("disabled.no_figure"), data="export-png"),
            wc.button(ui, ui.t("results.save_docx"), lambda e: self._save(entry, "docx"),
                      icon=ft.Icons.DESCRIPTION_OUTLINED, kind="primary", data="export-docx"),
            figure_number,
        ], wrap=True, spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            settings, *feedback], title=None, data="result-exports")

    def _copied(self, entry_id: int):
        self.feedback[entry_id] = (self.app.t("results.copied"), "success")
        self.app.render()

    def export_payload(self, entry, kind: str):
        """(suggested name, writer(path)) — writers use the classic export code."""
        from apa_figures import (default_section_figure_note, make_apa7_export_png,
                                 section_embeds_figure_header)
        from interpretation_docx import save_apa_docx
        from output_workspace import AnalysisOutput, save_selected_output

        run = entry.run
        section = run.section
        if kind == "text":
            output = AnalysisOutput(title=run.title, report=self.complete_report(run), png=run.png)
            return f"{section}_report.txt", lambda path: save_selected_output(path, output, "text")
        if kind == "image":
            def write_png(path):
                note = default_section_figure_note(
                    "omega" if section == "reliability" and "omega" in run.title.lower()
                    else section)
                png = make_apa7_export_png(
                    run.png, run.title, figure_number=int((self.figure_number or "1").strip()),
                    note=note, strip_embedded_caption=section_embeds_figure_header(section))
                output = AnalysisOutput(title=run.title, report=self.complete_report(run), png=png)
                return save_selected_output(path, output, "image")
            return f"{section}_figure.png", write_png
        evidence = run.evidence()
        reviewed = self.reviewed.get(entry.id, set())
        notes = self.notes.get(entry.id, "")
        figure_note = default_section_figure_note(
            "omega" if section == "reliability" and "omega" in run.title.lower() else section)
        return f"{section}_apa7_draft.docx", lambda path: save_apa_docx(
            path, evidence, reviewed=reviewed, researcher_notes=notes,
            study_title=self.app.pages["reports"].study_title, figure_title=run.title,
            figure_note=figure_note)

    async def _save(self, entry, kind: str):
        app = self.app
        if kind == "docx" and not await app.projects.ensure_result(entry):
            self.feedback[entry.id] = (app.t("results.not_reproducible"), "warning")
            app.render()
            return
        name, writer = self.export_payload(entry, kind)
        extension = name.rsplit(".", 1)[-1]
        outcome = await app.save_file(app.t("results.save_" + (
            "txt" if kind == "text" else "png" if kind == "image" else "docx")), name,
            extension, writer)
        self.feedback[entry.id] = (outcome.message, outcome.tone)
        app.render()


# ================================================================= reports
class ReportsPage:
    def __init__(self, app):
        self.app = app
        self.study_title = ""
        self.include_stale = False
        self.opened: set[str] = set()
        self.feedback: tuple[str, str] | None = None
        self._preview: ft.Text | None = None   # updated in place while typing

    def _blocked(self) -> bool:
        stale = [e for e in self.app.session.report_entries() if e.stale_reasons]
        return bool(stale) and not self.include_stale

    def build(self) -> ft.Control:
        app, ui, s = self.app, self.app.ui, self.app.session
        header = wc.page_header(ui, ui.t("reports.title"), ui.t("reports.subtitle"), actions=[
            wc.button(ui, ui.t("reports.export_txt"), self._export, kind="primary",
                      icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                      disabled=not s.report_order or self._blocked(),
                      tooltip=(ui.t("disabled.report_empty") if not s.report_order else
                               ui.t("disabled.report_stale") if self._blocked() else None),
                      data="reports-export"),
        ])
        entries = s.report_entries()
        self._preview = None
        if not entries:
            body = [wc.empty_state(ui, ft.Icons.DESCRIPTION_OUTLINED, ui.t("reports.empty.title"),
                                   ui.t("reports.empty.body"), actions=[
                                       wc.button(ui, ui.t("nav.results"),
                                                 lambda e: app.navigate("results"))],
                                   data="reports-empty")]
        else:
            items = []
            for number, entry in enumerate(entries, start=1):
                items.append(wc.card(ui, [ft.Row([
                    ft.Column([wc.text(ui, f"{number}. {entry.title}", tk.TYPE_LABEL,
                                       weight=ft.FontWeight.W_600),
                               wc.caption(ui, f"{entry.dataset} · {entry.created:%H:%M}"),
                               *([wc.chip(ui, ui.t("results.stale"), "warning",
                                          icon=ft.Icons.UPDATE,
                                          on_click=lambda e, i=entry.id: self._show(i),
                                          data=f"report-stale-{entry.id}")]
                                 if entry.stale_reasons else [])],
                              spacing=2, expand=True),
                    wc.icon_button(ui, ft.Icons.OPEN_IN_NEW, ui.t("reports.open_result"),
                                   lambda e, i=entry.id: self._show(i),
                                   data=f"report-open-{entry.id}"),
                    wc.icon_button(ui, ft.Icons.ARROW_UPWARD, ui.t("reports.move_up"),
                                   lambda e, i=entry.id: self._move(i, -1),
                                   disabled=number == 1),
                    wc.icon_button(ui, ft.Icons.ARROW_DOWNWARD, ui.t("reports.move_down"),
                                   lambda e, i=entry.id: self._move(i, 1),
                                   disabled=number == len(entries)),
                    wc.icon_button(ui, ft.Icons.REMOVE_CIRCLE_OUTLINE, ui.t("reports.remove"),
                                   lambda e, i=entry.id: self._remove(i)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER)], padding=tk.SPACE_4,
                    data=f"report-item-{entry.id}"))
            stale = [e for e in entries if e.stale_reasons]
            gate = [] if not stale else [wc.notice(
                ui, ui.t("reports.stale_block", count=len(stale)), "warning", actions=[
                    wc.checkbox(ui, ui.t("reports.include_stale"), self.include_stale,
                                on_change=lambda e: self._include(bool(e.control.value)),
                                data="reports-include-stale")], data="reports-stale")]
            self._preview = wc.text(
                ui, s.combined_report(self.study_title), tk.TYPE_BODY, selectable=True,
                data="reports-preview-text")
            preview = wc.expansion(
                ui, wc.heading(ui, ui.t("reports.preview"), tk.TYPE_TITLE_S),
                [ft.Container(self._preview, padding=tk.SPACE_4)],
                key="reports-preview", opened=self.opened,
                subtitle=wc.caption(ui, ui.t("reports.preview_hint")), data="reports-preview")
            body = [
                wc.text_field(ui, ui.t("reports.study_title"), self.study_title, width=520,
                              on_change=self._set_title, data="reports-study-title"),
                *gate,
                *items,
                preview,
                wc.notice(ui, ui.t("reports.export_docx_note"), "neutral"),
            ]
        if self.feedback:
            body.append(wc.notice(ui, self.feedback[0], self.feedback[1], data="reports-feedback"))
        return app.constrained(ft.Column([header, *body, wc.caption(
            ui, session_note(app), data="reports-note")], spacing=tk.SPACE_4,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH), tk.READING_MAX_WIDTH + 240)

    def _set_title(self, e):
        """The preview shows the title as it will be exported. It is updated
        in place: re-rendering the page on every keystroke is not needed."""
        self.study_title = e.control.value or ""
        if self._preview is not None:
            self._preview.value = self.app.session.combined_report(self.study_title)
            try:
                self.app.page.update()
            except Exception:  # pragma: no cover - page not shown
                pass

    def _include(self, value: bool):
        self.include_stale = value
        self.app.render()

    def _show(self, entry_id: int):
        self.app.session.selected_result = entry_id
        self.app.navigate("results")

    def _move(self, entry_id: int, step: int):
        self.app.session.move_in_report(entry_id, step)
        self.app.render()

    def _remove(self, entry_id: int):
        self.app.session.toggle_report(entry_id)
        self.app.render()

    async def _export(self, e=None):
        app = self.app
        if self._blocked():
            return
        text = app.session.combined_report(self.study_title)

        def write(path):
            path.write_text(text, encoding="utf-8")
            return path

        outcome = await app.save_file(app.t("reports.export_txt"), "research_report.txt",
                                      "txt", write)
        self.feedback = (outcome.message, outcome.tone)
        app.render()
