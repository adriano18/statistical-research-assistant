"""The hypothesis workspace of the Project page (Stage 37.0a, issue #63).

Two parts, both built from ``research_workflow``, where the rules live:

* the next-action bar (``project-next-action``): the one step that moves the
  project on, with buttons that do what they name. A button is never
  disabled: where nothing can be done from the bar, its text says what to do.
  *Why this step?* lists what is done and what is not.
* the hypotheses of the saved plan (``project-hypotheses``): designation,
  direction, α, standing, the steps of the analysis and the checks that
  wait for a decision. The detail of a hypothesis shows its analyses with
  their steps, every check with the decision that resolves it (acknowledge,
  record a deviation, justify: each needs a reason), the recorded decisions
  with *Withdraw…*, and its priority through the plan versions.

A check never blocks a run or an export. Typing a reason changes only this
panel's state: the page is not re-rendered on a keystroke.
"""

from __future__ import annotations

import flet as ft

import research_workflow as rw
import workspace_components as wc
import workspace_tokens as tk
from project_store import DEVIATION_WHAT, ProjectError

STEP_TONES = {"done": "success", "current": "info", "todo": "neutral", "attention": "warning",
              "skipped": "neutral"}
STEP_ICONS = {"done": ft.Icons.CHECK_CIRCLE, "current": ft.Icons.ARROW_CIRCLE_RIGHT,
              "todo": ft.Icons.CIRCLE_OUTLINED, "attention": ft.Icons.WARNING_AMBER_ROUNDED,
              "skipped": ft.Icons.REMOVE_CIRCLE_OUTLINE}
CHECK_TONES = {"open": "warning", "acknowledged": "success", "recorded": "success",
               "info": "neutral", "passed": "success"}
# A check's resolution → the kind of record it writes and its button.
DECISIONS = {"acknowledge": ("acknowledgement", "hyp.acknowledge"),
             "deviation": ("deviation", "hyp.deviation"),
             "justify": ("justification", "hyp.justify")}
WITHDRAWABLE = ("acknowledgement", "deviation", "justification")


def _when(stamp: str) -> str:
    from project_session import _local_time

    try:
        return f"{_local_time(stamp):%Y-%m-%d %H:%M}"
    except (TypeError, ValueError):
        return str(stamp or "")[:16].replace("T", " ")


def alpha_text(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def hypothesis_line(ui: wc.Ui, number: int, priority: str, direction: str, alpha) -> str:
    """``H1 · Primary · Less (one-sided) · α = 0.05``."""
    return " · ".join((f"H{number}", ui.t(f"plan.priority.{priority}"),
                       ui.t(f"plan.direction.{direction}"), f"α = {alpha_text(alpha)}"))


def step_row(ui: wc.Ui, steps, *, data: str) -> ft.Control:
    """The eight steps of a task as one row of chips; the state is in words,
    not only in colour."""
    chips = [wc.chip(ui, f"{number}. {ui.t('steps.' + step.key)}: "
                         f"{ui.t('steps.state.' + step.state)}",
                     STEP_TONES[step.state], icon=STEP_ICONS[step.state],
                     data=f"{data}-{step.key}")
             for number, step in enumerate(steps, start=1)]
    return ft.Row(chips, wrap=True, spacing=tk.SPACE_1, run_spacing=tk.SPACE_1, data=data)


class HypothesisPanel:
    def __init__(self, app):
        self.app = app
        self.opened: set[str] = set()      # hypotheses whose detail is shown
        self.show_why = False
        self.footer_why = False             # Why this step? in the page footers
        self.form: dict | None = None      # the record being written, if any
        self.reason = ""                   # its reason, as typed
        self.what = "method"               # what a free deviation is about
        self.message: tuple[str, str, str] | None = None   # (hypothesis id, text, tone)
        self._views: tuple = ()

    @property
    def project(self):
        return self.app.projects.project if self.app.projects.active else None

    def reset(self) -> None:
        """Another project: no detail open, no form half written."""
        self.opened, self.form, self.reason, self.message = set(), None, "", None
        self.show_why, self.footer_why, self._views = False, False, ()

    # --------------------------------------------------------------- facts
    def views(self) -> tuple:
        project = self.project
        self._views = rw.hypothesis_views(self.app.session, project) if project else ()
        return self._views

    def _view(self, hypothesis_id: str):
        return next((v for v in self._views if v.facts.id == hypothesis_id), None)

    def exported(self) -> bool:
        """The report, with the results it holds now, was exported."""
        project = self.project
        last = project.last_report_export() if project is not None else None
        current = [e.record_id for e in self.app.session.report_entries()]
        return bool(last and current and all(current)
                    and [str(r) for r in last.get("runs") or []] == current)

    def next_action(self, datasets, views=None) -> rw.NextAction:
        app = self.app
        views = self._views if views is None else views
        draft = app.pages["project"].plan.facts_draft()
        facts = rw.project_facts(app.session, self.project, views=views, draft=draft,
                                 questionnaire_draft=bool(app.pages["questionnaires"].draft),
                                 has_datasets=bool(datasets), exported=self.exported())
        return rw.next_action(facts)

    # ---------------------------------------------------- next-action bar
    def next_card(self, datasets, views=None) -> ft.Control:
        app, ui = self.app, self.app.ui
        action = self.next_action(datasets, views)
        params = action.params
        buttons = []
        for item in action.actions:
            label = ui.t(item.label, **params)
            kind = "primary" if item.primary else "secondary"
            if item.action == "open_data":
                buttons.append(wc.button(ui, label, action=app.open_data_action, kind=kind,
                                         data=item.data))
            else:
                buttons.append(wc.button(ui, label, wc.handler(self.run_action, item.action,
                                                               item.target),
                                         kind=kind, data=item.data))
        content: list[ft.Control] = [wc.text(ui, ui.t(action.body, **params), tk.TYPE_BODY,
                                             data="next-body")]
        if buttons:
            content.append(ft.Row(buttons, wrap=True, spacing=tk.SPACE_2))
        if action.why:
            content.append(wc.button(
                ui, ui.t("next.why.hide" if self.show_why else "next.why.title"),
                self._toggle_why, kind="quiet",
                icon=ft.Icons.EXPAND_LESS if self.show_why else ft.Icons.HELP_OUTLINE,
                data="next-why"))
            if self.show_why:
                lines = [wc.text(ui, ("✓ " if done else "○ ")
                                 + ui.t("next.why.done" if done else "next.why.todo") + ": "
                                 + ui.t(key, **values), tk.TYPE_BODY,
                                 color=None if done else ui.p.text_secondary,
                                 data=f"next-why-{index}")
                         for index, (done, key, values) in enumerate(action.why)]
                content.append(ft.Column(lines, spacing=tk.SPACE_1, data="next-why-list"))
        return wc.card(ui, content, title=ui.t(action.title, **params),
                       data="project-next-action", border=ui.p.accent)

    def _toggle_why(self, e=None):
        self.show_why = not self.show_why
        self.app.render()

    # ------------------------------------- the bar in the page footers (37.0b)
    # Where a next-action button takes the researcher: on that page itself
    # the button is left out and the bar says the step is done here.
    GOES_TO = {"sample_data": "data", "review_levels": "data", "choose_analysis": "analyze",
               "review_results": "results", "open_report": "reports",
               "questionnaire": "questionnaires", "continue_draft": "questionnaires"}

    def footer_bar(self, route: str) -> ft.Control | None:
        """The next action in the footer of Data, Analyze, Results and
        Reports (design §7.9): one line with the step, its buttons and *Why
        this step?*; never a disabled button. Only while a project is open."""
        app, ui = self.app, self.app.ui
        if not app.projects.active:
            return None
        project = app.projects.project
        action = self.next_action(project.datasets(), self.views())
        params = action.params
        buttons, here = [], False
        for item in action.actions:
            if self.GOES_TO.get(item.action) == route:
                here = True
                continue
            label = ui.t(item.label, **params)
            kind = "primary" if item.primary else "secondary"
            if item.action == "open_data":
                buttons.append(wc.button(ui, label, action=app.open_data_action, kind=kind,
                                         data=item.data))
            else:
                buttons.append(wc.button(ui, label, wc.handler(self.run_action, item.action,
                                                               item.target),
                                         kind=kind, data=item.data))
        line: list[ft.Control] = [
            ft.Icon(ft.Icons.ARROW_CIRCLE_RIGHT, size=18, color=ui.p.accent),
            wc.text(ui, ui.t("footer.next_step"), tk.TYPE_LABEL, weight=ft.FontWeight.W_600,
                    data="footer-next-label"),
            wc.text(ui, ui.t(action.title, **params), tk.TYPE_BODY, data="footer-next-title"),
        ]
        if here and not buttons:
            line.append(wc.caption(ui, ui.t("next.here"), data="footer-next-here"))
        line += buttons
        if action.why:
            line.append(wc.button(
                ui, ui.t("next.why.hide" if self.footer_why else "next.why.title"),
                self._toggle_footer_why, kind="quiet",
                icon=ft.Icons.EXPAND_LESS if self.footer_why else ft.Icons.HELP_OUTLINE,
                data="footer-next-why"))
        content: list[ft.Control] = [ft.Row(line, wrap=True, spacing=tk.SPACE_2,
                                            run_spacing=tk.SPACE_1,
                                            vertical_alignment=ft.CrossAxisAlignment.CENTER)]
        if self.footer_why and action.why:
            content.append(ft.Column([wc.text(
                ui, ("✓ " if done else "○ ") + ui.t("next.why.done" if done else "next.why.todo")
                + ": " + ui.t(key, **values), tk.TYPE_BODY,
                color=None if done else ui.p.text_secondary, data=f"footer-next-why-{index}")
                for index, (done, key, values) in enumerate(action.why)], spacing=2))
        return ft.Container(ft.Column(content, spacing=tk.SPACE_1),
                            padding=ft.Padding.symmetric(horizontal=tk.SPACE_4,
                                                         vertical=tk.SPACE_2),
                            bgcolor=ui.p.surface, border=ft.Border.only(
                                top=ft.BorderSide(1, ui.p.border)),
                            data="footer-next-action")

    def _toggle_footer_why(self, e=None):
        self.footer_why = not self.footer_why
        self.app.render()

    def footer_for(self, route: str) -> ft.Control | None:
        """``footer_bar`` for a page's ``footer()``: a failure leaves the page
        without the bar instead of blanking the window."""
        try:
            return self.footer_bar(route)
        except Exception:          # pragma: no cover - a bug must not hide the page
            return None

    def run_action(self, action: str, target: str = "") -> None:
        """Do what the button of the next action names."""
        app = self.app
        plan = app.pages["project"].plan
        if action in ("sample_data", "review_levels"):
            app.navigate("data")
        elif action in ("questionnaire", "continue_draft"):
            app.navigate("questionnaires")
        elif action == "choose_analysis":
            app.navigate("analyze")
        elif action == "review_results":
            app.navigate("results")
        elif action == "open_report":
            app.navigate("reports")
        elif action in ("write_question", "add_hypothesis", "save_plan"):
            if action == "write_question":
                plan.add_question(prefill=True)
            elif action == "add_hypothesis":
                plan.add_hypothesis_for(int(target) if str(target).isdigit() else 0)
            else:
                plan.save()
            if app.route != "project":
                # From a page footer: the plan card is on the Project page.
                app.navigate("project")
        elif action == "create_analysis":
            app.pages["analyze"].create_for_hypothesis(target)
        elif action == "open_task":
            app.pages["analyze"].open_task_for(target)
        elif action == "show_checks":
            self.opened.add(target)
            app.navigate("project", section="hypotheses")
        elif action == "review":
            self.open_result(target)
        elif action == "write_note":
            self.open_result(target, interpretation=True)
        elif action == "skip_note":
            self.skip_interpretation(target)
        elif action == "add_to_report":
            self.add_to_report(target)
        else:
            app.render()

    def show_hypothesis(self, hypothesis_id: str) -> None:
        """*Open H…* (a result's card): the hypothesis's detail on the Project page."""
        self.opened.add(hypothesis_id)
        self.app.navigate("project", section="hypotheses")

    def open_result(self, target, *, interpretation: bool = False) -> None:
        app = self.app
        entry = app.session.result(int(target)) if str(target).isdigit() else None
        if entry is not None:
            app.session.selected_result = entry.id
            if interpretation:
                app.pages["results"].opened.add(f"interpretation-{entry.id}")
        app.navigate("results")

    def skip_interpretation(self, task_id: str) -> None:
        """The researcher chose to write no interpretation for this task."""
        session = self.app.session
        task = session.task(task_id)
        if task is not None:
            skipped = list((task.state or {}).get("skipped") or [])
            if "interpretation" not in skipped:
                skipped.append("interpretation")
            task.state = {**(task.state or {}), "skipped": skipped}
            session.save_task(task)
        self.app.render()

    def add_to_report(self, target) -> None:
        session = self.app.session
        entry = session.result(int(target)) if str(target).isdigit() else None
        if entry is not None and not entry.in_report:
            session.toggle_report(entry.id)
        self.app.render()

    # ------------------------------------------------------- hypotheses
    def list_card(self, views=None) -> ft.Control:
        ui = self.app.ui
        views = self._views if views is None else views
        if not views:
            return ft.Container(visible=False)
        rows: list[ft.Control] = [wc.caption(ui, ui.t("hyp.body"))]
        rows += [self._row(view) for view in views]
        return ft.Container(wc.card(ui, rows, title=ui.t("hyp.title"), data="project-hypotheses"),
                            key=ft.ScrollKey("project-hypotheses"))

    def toggle(self, hypothesis_id: str) -> None:
        if hypothesis_id in self.opened:
            self.opened.discard(hypothesis_id)
        else:
            self.opened.add(hypothesis_id)
        self.app.render()

    def _row(self, view) -> ft.Control:
        ui, f = self.app.ui, view.facts
        n = f.number
        decide = rw.open_checks(view.checks)
        opened = f.id in self.opened
        standing_tone = {"confirmatory": "success", "added_after_results": "warning"}.get(
            f.standing, "neutral")
        steps_text = (ui.t("steps.count", done=rw.steps_complete(view.steps),
                           total=len(rw.STEP_KEYS)) if view.steps else ui.t("hyp.no_task"))
        chips = [
            wc.chip(ui, ui.t(f"plan.standing.{f.standing}", runs=f.runs_before), standing_tone,
                    data=f"hyp-{n}-standing"),
            wc.chip(ui, steps_text, "info" if view.steps else "neutral", icon=ft.Icons.CHECKLIST,
                    data=f"hyp-{n}-steps"),
            wc.chip(ui, ui.t("hyp.open_checks", count=len(decide)) if decide
                    else ui.t("hyp.no_open_checks"), "warning" if decide else "success",
                    data=f"hyp-{n}-open"),
        ]
        header = ft.Row([
            ft.Column([wc.text(ui, hypothesis_line(ui, n, f.priority, f.direction, f.alpha),
                               tk.TYPE_LABEL, weight=ft.FontWeight.W_600, data=f"hyp-{n}-line"),
                       wc.text(ui, f.text, tk.TYPE_BODY, selectable=True)],
                      spacing=2, expand=True),
            wc.button(ui, ui.t("hyp.hide" if opened else "hyp.show"),
                      wc.handler(self.toggle, f.id), kind="quiet",
                      icon=ft.Icons.EXPAND_LESS if opened else ft.Icons.EXPAND_MORE,
                      data=f"hyp-{n}-toggle"),
        ], vertical_alignment=ft.CrossAxisAlignment.START)
        content: list[ft.Control] = [header, ft.Row(chips, wrap=True, spacing=tk.SPACE_2)]
        if opened:
            content += self._detail(view)
        return ft.Container(ft.Column(content, spacing=tk.SPACE_2),
                            border=ft.Border.all(1, ui.p.border), border_radius=ui.radius("card"),
                            padding=tk.SPACE_3, data=f"hyp-{n}")

    def _detail(self, view) -> list[ft.Control]:
        app, ui, f = self.app, self.app.ui, view.facts
        n = f.number
        out: list[ft.Control] = []
        if view.plan.get("h0"):
            out.append(wc.labeled(ui, ui.t("plan.h.h0"), view.plan["h0"]))
        if f.planned_version is not None:
            # Stage 37.0b (review S16): what the standing was decided on.
            out.append(wc.caption(ui, ui.t("hyp.standing_facts", version=f.planned_version,
                                           total=f.results_then, counted=f.runs_before),
                                  data=f"hyp-{n}-standing-facts"))
        plan_ids = frozenset(v.facts.id for v in self._views)
        if view.tasks:
            for index, task in enumerate(view.tasks):
                steps = view.steps if index == 0 else rw.task_steps(
                    rw.task_facts(task, app.session, plan_ids=plan_ids))
                out.append(ft.Row([
                    wc.text(ui, ui.t("hyp.analysis", title=task.title), tk.TYPE_LABEL,
                            weight=ft.FontWeight.W_600),
                    wc.button(ui, ui.t("next.open_task", h=n),
                              wc.handler(app.pages["analyze"].open_task_for, task.id),
                              icon=ft.Icons.OPEN_IN_NEW, data=f"hyp-{n}-open-task-{index}"),
                ], wrap=True, spacing=tk.SPACE_2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER))
                out.append(step_row(ui, steps, data=f"hyp-{n}-steps-{index}"))
        else:
            out.append(ft.Row([
                wc.text(ui, ui.t("check.no_task", h=n), tk.TYPE_BODY),
                wc.button(ui, ui.t("next.create_analysis_button", h=n),
                          wc.handler(app.pages["analyze"].create_for_hypothesis, f.id),
                          kind="primary", icon=ft.Icons.ADD, data=f"hyp-{n}-create-task"),
            ], wrap=True, spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        out.append(wc.section_label(ui, ui.t("hyp.checks")))
        for index, check in enumerate(view.checks):
            out.append(self._check_row(view, index, check))
            if self._form_is(f.id, check=check):
                out.append(self._form_controls(view))
        if self.message and self.message[0] == f.id:
            out.append(wc.notice(ui, self.message[1], self.message[2], data=f"hyp-{n}-message"))
        out.append(wc.button(ui, ui.t("hyp.deviation"),
                             wc.handler(self.open_form, f.id, "deviation"), kind="quiet",
                             icon=ft.Icons.EDIT_NOTE, data=f"hyp-{n}-record-deviation"))
        if self._form_is(f.id, kind="deviation", free=True):
            out.append(self._form_controls(view))
        out += self._records(view)
        out += self._history(view)
        return out

    def _check_row(self, view, index: int, check) -> ft.Control:
        app, ui = self.app, self.app.ui
        n = view.facts.number
        data = f"hyp-{n}-check-{index}"
        if check.state in ("acknowledged", "recorded"):
            record = next((r for r in view.records if r.get("id") == check.record_id), {})
            status = ui.t(f"hyp.check.{check.state}",
                          reason=record.get("reason") or check.params.get("reason", ""))
        else:
            status = ui.t({"open": "hyp.check.open", "info": "hyp.check.info",
                           "passed": "hyp.check.passed"}[check.state])
        lines: list[ft.Control] = []
        if check.task_id and len(view.tasks) > 1:
            task = app.session.task(check.task_id)
            lines.append(wc.caption(ui, ui.t("hyp.analysis", title=task.title if task else "—")))
        lines += [wc.text(ui, rw.check_message(check, ui.language), tk.TYPE_BODY,
                          selectable=True, data=f"{data}-text"),
                  wc.caption(ui, status, data=f"{data}-state")]
        buttons = []
        if check.needs_decision:
            if check.resolution in DECISIONS:
                kind, label = DECISIONS[check.resolution]
                buttons.append(wc.button(ui, ui.t(label),
                                         wc.handler(self.open_form, view.facts.id, kind, index),
                                         data=f"{data}-{check.resolution}"))
            elif check.resolution == "review":
                entries = app.session.task_results(check.task_id) if check.task_id else []
                buttons.append(wc.button(ui, ui.t("next.review_button"),
                                         wc.handler(self.open_result,
                                                    str(entries[-1].id) if entries else ""),
                                         data=f"{data}-review"))
            elif check.resolution == "recalculate":
                buttons.append(wc.button(ui, ui.t("next.open_task", h=n),
                                         wc.handler(app.pages["analyze"].open_task_for,
                                                    check.task_id or ""),
                                         data=f"{data}-recalculate"))
            elif check.resolution == "create_task":
                buttons.append(wc.button(ui, ui.t("next.create_analysis_button", h=n),
                                         wc.handler(app.pages["analyze"].create_for_hypothesis,
                                                    view.facts.id),
                                         data=f"{data}-create-task"))
        icon = {"open": ft.Icons.WARNING_AMBER_ROUNDED, "info": ft.Icons.INFO_OUTLINE}.get(
            check.state, ft.Icons.CHECK_CIRCLE_OUTLINE)
        tone = CHECK_TONES[check.state]
        color = {"warning": ui.p.warning, "success": ui.p.success}.get(tone, ui.p.text_secondary)
        body: list[ft.Control] = [ft.Row([ft.Icon(icon, size=18, color=color),
                                          ft.Column(lines, spacing=2, expand=True)],
                                         vertical_alignment=ft.CrossAxisAlignment.START,
                                         spacing=tk.SPACE_2)]
        if buttons:
            body.append(ft.Row(buttons, wrap=True, spacing=tk.SPACE_2))
        return ft.Container(ft.Column(body, spacing=tk.SPACE_2), padding=tk.SPACE_2, data=data)

    # ----------------------------------------------------- record forms
    def _form_is(self, hypothesis_id: str, *, check=None, kind: str | None = None,
                 free: bool = False, record: str | None = None) -> bool:
        form = self.form
        if form is None or form["hypothesis"] != hypothesis_id:
            return False
        if check is not None:
            return (form["kind"] != "withdrawal" and form["check_key"] == check.key
                    and form["task_id"] == check.task_id
                    and form["fingerprint"] == check.fingerprint)
        if record is not None:
            return form["kind"] == "withdrawal" and form["record"] == record
        return free and form["kind"] == kind and not form["check_key"]

    def open_form(self, hypothesis_id: str, kind: str, check_index: int | None = None,
                  record_id: str | None = None) -> None:
        """Open the form of one record: for a check (its facts are bound to
        the record), a free deviation, or the withdrawal of a record."""
        view = self._view(hypothesis_id)
        check = None
        if view is not None and check_index is not None and check_index < len(view.checks):
            check = view.checks[check_index]
        self.form = {"hypothesis": hypothesis_id, "kind": kind,
                     "check_key": check.key if check else "",
                     "task_id": check.task_id if check else None,
                     "fingerprint": check.fingerprint if check else "",
                     "what": rw.DEVIATION.get(check.key) if check and kind == "deviation" else None,
                     "record": record_id,
                     # Stage 37.0b: what was planned and what was done, kept
                     # with a deviation so the report can say it.
                     "facts": dict(check.facts) if check and kind == "deviation" else {}}
        self.reason, self.message = "", None
        self.app.render()

    def cancel_form(self, e=None) -> None:
        self.form, self.reason = None, ""
        self.app.render()

    def _set_reason(self, value: str) -> None:
        self.reason = value          # no re-render while typing

    def _set_what(self, value: str) -> None:
        self.what = value or "other"

    def _form_controls(self, view) -> ft.Control:
        ui = self.app.ui
        n = view.facts.number
        form = self.form
        controls: list[ft.Control] = [wc.caption(ui, ui.t(f"hyp.form.{form['kind']}"))]
        if form["kind"] == "deviation" and not form["check_key"]:
            controls.append(wc.dropdown(
                ui, ui.t("hyp.what"), [(w, ui.t(f"hyp.what.{w}")) for w in DEVIATION_WHAT],
                self.what, on_select=lambda e: self._set_what(e.control.value), width=320,
                data=f"hyp-{n}-what"))
        controls.append(wc.text_field(ui, ui.t("hyp.reason"), self.reason, multiline=True,
                                      on_change=lambda e: self._set_reason(e.control.value or ""),
                                      data=f"hyp-{n}-reason"))
        controls.append(ft.Row([
            wc.button(ui, ui.t("hyp.save_record"), self.save_form, kind="primary",
                      icon=ft.Icons.SAVE_OUTLINED, data=f"hyp-{n}-save"),
            wc.button(ui, ui.t("common.cancel"), self.cancel_form, kind="quiet",
                      data=f"hyp-{n}-cancel"),
        ], wrap=True, spacing=tk.SPACE_2))
        return ft.Container(ft.Column(controls, spacing=tk.SPACE_2), padding=tk.SPACE_3,
                            bgcolor=ui.p.surface_alt, border_radius=ui.radius("card"),
                            data=f"hyp-{n}-form")

    def save_form(self, e=None) -> None:
        """Append the record. Without a reason nothing is written and the
        form says so (the Save button is never disabled)."""
        form, ui = self.form, self.app.ui
        if form is None:
            return
        hypothesis_id = form["hypothesis"]
        reason = (self.reason or "").strip()
        if not reason:
            self.message = (hypothesis_id, ui.t("hyp.reason_first"), "warning")
            self.app.render()
            return
        detail = {}
        if form["kind"] == "deviation":
            detail["what"] = form["what"] or self.what
            facts = form.get("facts") or {}
            planned = facts.get("planned", facts.get("first"))
            actual = facts.get("actual", facts.get("later"))
            if planned is not None and actual is not None:
                detail["planned"], detail["actual"] = planned, actual
        try:
            self.project.add_protocol_record(
                form["kind"], hypothesis_id=hypothesis_id, task_id=form["task_id"],
                run_id=self._run_of(form["task_id"]), check_key=form["check_key"],
                fingerprint=form["fingerprint"], detail=detail, reason=reason,
                supersedes=form["record"])
        except (ProjectError, OSError) as error:
            self.message = (hypothesis_id, ui.t("hyp.not_recorded", reason=str(error)), "danger")
            self.app.render()
            return
        self.form, self.reason = None, ""
        self.message = (hypothesis_id, ui.t("hyp.recorded"), "success")
        self.app.render()

    def _run_of(self, task_id: str | None) -> str | None:
        """The saved result a decision about a task's check is made about:
        the latest result of that task (Stage 37.0b, review D12)."""
        if not task_id:
            return None
        entries = self.app.session.task_results(task_id)
        return entries[-1].record_id if entries else None

    # ------------------------------------------------ records, history
    def _record_text(self, record: dict) -> str:
        ui = self.app.ui
        when = _when(record.get("at", ""))
        kind = record.get("kind")
        detail = record.get("detail") or {}
        reason = record.get("reason") or ""
        if kind == "designation":
            return ui.t("hyp.record.designation", when=when, reason=reason, **{
                "from": ui.t(f"plan.priority.{detail.get('from', 'primary')}"),
                "to": ui.t(f"plan.priority.{detail.get('to', 'primary')}")})
        if kind == "link":
            task = self.app.session.task(record.get("task_id"))
            linked = detail.get("to") == record.get("hypothesis_id")
            return ui.t("hyp.record.link" if linked else "hyp.record.unlink", when=when,
                        task=task.title if task is not None else "—")
        if kind == "deviation":
            what = detail.get("what") if detail.get("what") in DEVIATION_WHAT else "other"
            return ui.t("hyp.record.deviation", when=when, what=ui.t(f"hyp.what.{what}"),
                        reason=reason)
        return ui.t(f"hyp.record.{kind}", when=when, reason=reason)

    def _records(self, view) -> list[ft.Control]:
        ui = self.app.ui
        n = view.facts.number
        out: list[ft.Control] = [wc.section_label(ui, ui.t("hyp.records"))]
        records = view.records
        if not records:
            out.append(wc.caption(ui, ui.t("hyp.records_none")))
        withdrawn = {r.get("supersedes") for r in records if r.get("kind") == "withdrawal"}
        for index, record in enumerate(records):
            text = self._record_text(record)
            if record.get("id") in withdrawn:
                text += f" ({ui.t('hyp.record.withdrawn')})"
            item: list[ft.Control] = [wc.text(ui, text, tk.TYPE_BODY, selectable=True,
                                              data=f"hyp-{n}-record-{index}")]
            if record.get("kind") in WITHDRAWABLE and record.get("id") not in withdrawn:
                item.append(wc.button(ui, ui.t("hyp.withdraw"),
                                      wc.handler(self.open_form, view.facts.id, "withdrawal",
                                                 None, record["id"]),
                                      kind="quiet", data=f"hyp-{n}-record-{index}-withdraw"))
            out.append(ft.Column(item, spacing=tk.SPACE_1))
            if self._form_is(view.facts.id, record=record.get("id")):
                out.append(self._form_controls(view))
        return out

    def _history(self, view) -> list[ft.Control]:
        """The priority through the plan versions, when it ever changed."""
        if not any(entry.get("changed") for entry in view.history):
            return []
        ui = self.app.ui
        n = view.facts.number
        out: list[ft.Control] = [wc.section_label(ui, ui.t("hyp.history"))]
        for index, entry in enumerate(view.history):
            values = {"version": entry["version"], "when": _when(entry.get("saved_at", "")),
                      "priority": ui.t(f"plan.priority.{entry['priority']}")}
            if entry.get("changed"):
                text = ui.t("hyp.history_changed",
                            previous=ui.t(f"plan.priority.{entry['previous']}"),
                            runs=entry.get("runs_before", 0), **values)
            else:
                text = ui.t("hyp.history_line", **values)
            out.append(wc.caption(ui, text, data=f"hyp-{n}-history-{index}"))
        return out
