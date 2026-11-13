"""The research plan card of the project page (Stage 35, #40).

Objectives, design, population, ethics notes and an optional
preregistration reference, then the hypotheses. Each hypothesis records:
- H1 and H0;
- its direction (two-sided, greater, less);
- whether it is primary, secondary or exploratory;
- the outcome, predictors or groups and covariates;
- the intended method, the significance level, the multiplicity family and
  the exclusion policy.

Stage 37.0a adds typed research questions (a kind and a sentence) and, per
hypothesis, the question it answers and the planned analysis that the checks
compare with what is run. A hypothesis of a typed question shows a hint for
H1 (never prefilled, so a template cannot be saved as a hypothesis) and is
offered a drafted H0 to keep or edit. Once results exist, a changed priority
needs a reason, which is recorded with the new plan version.

**Save plan version** adds a version to the project's history; nothing is
overwritten. Every hypothesis shows its standing:
- *planned before any result*;
- *added after results were calculated*: exploratory unless justified;
- or *exploratory*.

That standing is derived from when it entered the plan, not from the
researcher's wish. Typing changes only the draft: the page is not re-rendered
on every keystroke.
"""

from __future__ import annotations

import copy
import uuid

import flet as ft

import research_workflow as rw
import workspace_components as wc
import workspace_tokens as tk
from workspace_text import label as engine_label

EMPTY_PLAN = {"objectives": "", "design": "", "population": "", "ethics": "",
              "preregistration": "", "questions": [], "hypotheses": []}
PLAN_FIELDS = (("objectives", True), ("design", True), ("population", False),
               ("ethics", False), ("preregistration", False))
HYPOTHESIS_TEXT = (("text", True), ("h0", False), ("outcome", False), ("predictors", False),
                   ("covariates", False), ("method", False), ("family", False),
                   ("exclusions", False))


def _local(stamp: str) -> str:
    return stamp.replace("T", " ")[:16]


class ResearchPlanCard:
    def __init__(self, app):
        self.app = app
        self.draft: dict | None = None
        self.project_id: str | None = None
        self.opened: set[str] = set()
        self.feedback: tuple[str, str] | None = None
        # Stage 37.0a: {hypothesis id: reason} for a priority changed after results.
        self.reasons: dict[str, str] = {}
        # Stage 37.0b: the id of Q1 while it only shows the project's research
        # question (a plan without typed questions); None once the researcher
        # uses it (types, chooses its kind, adds a hypothesis to it).
        self.auto_question: str | None = None
        self.linked_question: str | None = None   # Q1 that mirrors that row

    # --------------------------------------------------------------- state
    def _project(self):
        return self.app.projects.project

    def _sync(self, project) -> None:
        """Start the draft from the saved plan of the open project."""
        info_id = getattr(project, "path", None)
        if self.draft is None or info_id != self.project_id:
            current = project.plan()
            self.draft = copy.deepcopy(current["plan"]) if current else copy.deepcopy(EMPTY_PLAN)
            self.project_id = info_id
            self.feedback = None
            self.reasons = {}
            self.auto_question = self.linked_question = None
            self.draft.setdefault("questions", [])
            self._show_question_row()
        self.draft.setdefault("questions", [])
        self.draft.setdefault("hypotheses", [])
        self._refresh_question_row()

    def _show_question_row(self) -> None:
        """Stage 37.0b (design §7.2, §8.4): a plan without typed questions (a
        Stage 36 plan, or none yet) shows the project's research question as
        Q1 by itself, its kind not chosen. Nothing is converted: the row
        counts for the next step only once the researcher uses it, and it is
        saved with the next plan version."""
        if self.draft.get("questions"):
            return
        question = {"id": uuid.uuid4().hex[:12], "type": "",
                    "text": self.app.research_question().strip()}
        self.draft["questions"] = [question]
        self.auto_question = self.linked_question = question["id"]

    def _write_through(self, plan: dict) -> None:
        """Q1 taken from the project's research question keeps that row up to
        date when the plan is saved (the AI overview and the report's
        Research question section read the row); so does a first Q1 of a
        project that had no research question."""
        questions = plan.get("questions") or []
        if not questions:
            return
        first = questions[0]
        current = self.app.research_question().strip()
        text = str(first.get("text") or "").strip()
        if text and text != current and (first.get("id") == self.linked_question or not current):
            try:
                self.app.projects.set_research_question(text)
            except Exception:       # the plan is saved; the row stays as it was
                pass

    def _auto_row(self) -> dict | None:
        """Q1 while it only shows the project's research question."""
        if self.auto_question is None:
            return None
        return next((q for q in self.draft.get("questions", [])
                     if q.get("id") == self.auto_question), None)

    def _refresh_question_row(self) -> None:
        """The shown Q1 follows the Question card until the researcher uses it."""
        row = self._auto_row()
        if row is None:
            self.auto_question = None
            return
        if not row.get("type"):
            row["text"] = self.app.research_question().strip()

    def _use_question(self, question_id: str | None) -> None:
        """The researcher works with this question: Q1 is part of the plan now."""
        if question_id is not None and question_id == self.auto_question:
            self.auto_question = None

    def current_draft(self) -> dict | None:
        """The plan as it is on screen (unsaved changes included)."""
        project = self._project() if self.app.projects.active else None
        if project is None:
            return None
        self._sync(project)
        return self.draft

    def facts_draft(self) -> dict | None:
        """The draft as the next step judges it: Q1 shown by itself from the
        project's research question does not start the plan."""
        draft = self.current_draft()
        if draft is None or self.auto_question is None:
            return draft
        return {**draft, "questions": [q for q in draft.get("questions", [])
                                       if q.get("id") != self.auto_question]}

    def _set(self, key: str, value: str) -> None:
        self.draft[key] = value

    def _set_hypothesis(self, index: int, key: str, value) -> None:
        self.draft["hypotheses"][index][key] = value

    def _questions_by_id(self) -> dict[str, dict]:
        return {q.get("id"): q for q in self.draft.get("questions", []) if q.get("id")}

    def _saved_priorities(self, project) -> dict[str, str]:
        current = project.plan()
        return {h["id"]: h.get("priority", "primary")
                for h in ((current or {}).get("plan") or {}).get("hypotheses", [])}

    def _changes(self, project, hypothesis: dict) -> list[str]:
        """What changes in a saved hypothesis (Stage 37.0b, review S8): its
        priority, wording (H1, H0), direction or α. The α as typed: one that
        is not a number is explained when the plan is saved."""
        current = project.plan()
        saved = {h["id"]: h for h in ((current or {}).get("plan") or {}).get("hypotheses", [])}
        old = saved.get(hypothesis.get("id"))
        if old is None:
            return []
        changes = []
        if old.get("priority", "primary") != hypothesis.get("priority", "primary"):
            changes.append("designation")
        if (str(old.get("text", "")).strip() != str(hypothesis.get("text") or "").strip()
                or str(old.get("h0", "")).strip() != str(hypothesis.get("h0") or "").strip()):
            changes.append("wording")
        if old.get("direction", "two-sided") != hypothesis.get("direction", "two-sided"):
            changes.append("direction")
        try:
            if abs(float(old.get("alpha", 0.05)) - float(hypothesis.get("alpha", 0.05))) > 1e-12:
                changes.append("alpha")
        except (TypeError, ValueError):
            pass
        return changes

    def _needs_reason(self, project, hypothesis: dict) -> bool:
        """A saved hypothesis that changes while results exist (its priority,
        and since Stage 37.0b its wording, direction or α)."""
        if not self.app.session.results:
            return False
        return bool(self._changes(project, hypothesis))

    def _reason_message(self, project, number: int, hypothesis: dict) -> str:
        """The message of a missing reason: the 37.0a one for a priority."""
        ui = self.app.ui
        if self._changes(project, hypothesis) == ["designation"]:
            return ui.t("plan.reason_needed", h=number)
        return ui.t("plan.change_reason_needed", h=number)

    # --------------------------------------------------------------- build
    def build(self) -> ft.Control:
        ui = self.app.ui
        project = self._project()
        if project is None:
            return ft.Container(visible=False)
        self._sync(project)
        status = project.hypothesis_status()
        rows: list[ft.Control] = [wc.caption(ui, ui.t("plan.body"))]
        for key, multiline in PLAN_FIELDS:
            rows.append(wc.text_field(
                ui, ui.t(f"plan.{key}"), self.draft.get(key, ""), multiline=multiline,
                on_change=lambda e, k=key: self._set(k, e.control.value or ""),
                data=f"plan-{key}"))
        rows += self._questions()
        rows.append(wc.section_label(ui, ui.t("plan.hypotheses")))
        for index, hypothesis in enumerate(self.draft["hypotheses"]):
            rows.append(self._hypothesis(index, hypothesis, status.get(hypothesis.get("id", "")),
                                         project))
        if not self.draft["hypotheses"]:
            rows.append(wc.caption(ui, ui.t("plan.no_hypotheses")))
        rows.append(ft.Row([
            wc.button(ui, ui.t("plan.add"), self._add, icon=ft.Icons.ADD, data="plan-add"),
            wc.button(ui, ui.t("plan.save"), self._save, kind="primary",
                      icon=ft.Icons.SAVE_OUTLINED, data="plan-save"),
        ], wrap=True, spacing=tk.SPACE_2))
        if self.feedback:
            rows.append(wc.notice(ui, self.feedback[0], self.feedback[1], data="plan-feedback"))
        history = project.plan_history()
        if history:
            lines = [wc.caption(ui, ui.t("plan.version_line", version=v["version"],
                                         when=_local(v["saved_at"]),
                                         count=len(v["plan"]["hypotheses"]),
                                         runs=v["runs_before"])
                                + (f" · {v['note']}" if v["note"] else ""),
                                data=f"plan-version-{v['version']}") for v in history]
            rows.append(wc.expansion(ui, wc.text(ui, ui.t("plan.history", count=len(history)),
                                                 tk.TYPE_LABEL), lines, key="plan-history",
                                     opened=self.opened, data="plan-history"))
        return wc.card(ui, rows, title=ui.t("plan.title"), data="project-plan")

    def _questions(self) -> list[ft.Control]:
        """Stage 37.0a: the typed research questions (kind and sentence)."""
        ui = self.app.ui
        questions = self.draft["questions"]
        kinds = [(kind, ui.t(f"goal.{kind}")) for kind in rw.QUESTION_TYPES]
        rows: list[ft.Control] = [wc.section_label(ui, ui.t("plan.questions")),
                                  wc.caption(ui, ui.t("plan.questions_body"))]
        for index, question in enumerate(questions):
            number = index + 1
            shown = ([wc.caption(ui, ui.t("plan.q.from_project"), data=f"plan-q{index}-auto")]
                     if question.get("id") == self.auto_question else [])
            rows.append(ft.Container(ft.Column(shown + [
                wc.text_field(ui, ui.t("plan.q.text", n=number), question.get("text", ""),
                              multiline=True,
                              on_change=lambda e, i=index: self._set_question(
                                  i, "text", e.control.value or ""),
                              data=f"plan-q{index}-text"),
                ft.Row([
                    wc.dropdown(ui, ui.t("plan.q.type"), kinds, question.get("type") or None,
                                on_select=lambda e, i=index: self._set_question_type(
                                    i, e.control.value), width=360, data=f"plan-q{index}-type"),
                    wc.button(ui, ui.t("next.add_hypothesis_button", q=number),
                              lambda e, n=number: self.add_hypothesis_for(n), kind="quiet",
                              icon=ft.Icons.ADD, data=f"plan-q{index}-add-hypothesis"),
                    wc.button(ui, ui.t("plan.q.remove"),
                              lambda e, i=index: self._remove_question(i), kind="quiet",
                              icon=ft.Icons.DELETE_OUTLINE, data=f"plan-q{index}-remove"),
                ], wrap=True, spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=tk.SPACE_2), data=f"plan-q{index}"))
        if not questions:
            rows.append(wc.caption(ui, ui.t("plan.q.none")))
        rows.append(ft.Row([wc.button(ui, ui.t("plan.q.add"), lambda e: self.add_question(),
                                      icon=ft.Icons.ADD, data="plan-add-question")]))
        return rows

    def _hypothesis(self, index: int, hypothesis: dict, standing: dict | None,
                    project) -> ft.Control:
        ui = self.app.ui
        fields: list[ft.Control] = []
        if standing is not None:
            tone = {"confirmatory": "success", "added_after_results": "warning"}.get(
                standing["standing"], "neutral")
            fields.append(wc.chip(ui, ui.t(f"plan.standing.{standing['standing']}",
                                           runs=standing.get("inferential_before",
                                                             standing["runs_before"])), tone,
                                  data=f"plan-standing-{index}"))
        else:
            fields.append(wc.chip(ui, ui.t("plan.standing.new"), "neutral",
                                  data=f"plan-standing-{index}"))
        questions = self.draft["questions"]
        question = self._questions_by_id().get(hypothesis.get("question_id") or "")
        if questions:
            options = [("", ui.t("plan.h.no_question"))] + [
                (q["id"], f"Q{number}. {(q.get('text') or '').strip()[:80] or '—'}")
                for number, q in enumerate(questions, start=1) if q.get("id")]
            fields.append(wc.dropdown(ui, ui.t("plan.h.question"), options,
                                      hypothesis.get("question_id") or "",
                                      on_select=lambda e, i=index: self._set_question_link(
                                          i, e.control.value), width=480,
                                      data=f"plan-h{index}-question"))
        hint = ui.t(rw.draft_keys(question["type"])[0]) if question and question.get("type") \
            else None
        for key, multiline in HYPOTHESIS_TEXT:
            fields.append(wc.text_field(
                ui, ui.t(f"plan.h.{key}"), str(hypothesis.get(key, "")), multiline=multiline,
                hint=hint if key == "text" else None,
                on_change=lambda e, i=index, k=key: self._set_hypothesis(i, k, e.control.value or ""),
                data=f"plan-h{index}-{key}"))
        fields += self._planned_method(index, hypothesis)
        fields += self._planned_roles(index, hypothesis)
        fields.append(ft.Row([
            wc.dropdown(ui, ui.t("plan.h.direction"),
                        [(d, ui.t(f"plan.direction.{d}")) for d in ("two-sided", "greater", "less")],
                        hypothesis.get("direction", "two-sided"),
                        on_select=lambda e, i=index: self._set_hypothesis(i, "direction", e.control.value),
                        data=f"plan-h{index}-direction"),
            wc.dropdown(ui, ui.t("plan.h.priority"),
                        [(p, ui.t(f"plan.priority.{p}")) for p in ("primary", "secondary", "exploratory")],
                        hypothesis.get("priority", "primary"),
                        on_select=lambda e, i=index: self._set_priority(i, e.control.value),
                        data=f"plan-h{index}-priority"),
            wc.text_field(ui, ui.t("plan.h.alpha"), str(hypothesis.get("alpha", 0.05)), width=140,
                          on_change=lambda e, i=index: self._set_hypothesis(i, "alpha", e.control.value),
                          data=f"plan-h{index}-alpha"),
        ], wrap=True, spacing=tk.SPACE_2))
        if self._needs_reason(project, hypothesis):
            label = ("plan.h.reason" if self._changes(project, hypothesis) == ["designation"]
                     else "plan.h.change_reason")
            fields.append(wc.text_field(
                ui, ui.t(label), self.reasons.get(hypothesis["id"], ""), multiline=True,
                on_change=lambda e, h=hypothesis["id"]: self._set_reason(h, e.control.value or ""),
                data=f"plan-h{index}-reason"))
        fields.append(wc.button(ui, ui.t("plan.remove"), lambda e, i=index: self._remove(i),
                                icon=ft.Icons.DELETE_OUTLINE, data=f"plan-h{index}-remove"))
        title = hypothesis.get("text") or ui.t("plan.h.untitled")
        return wc.card(ui, fields, title=f"H{index + 1}. {title}"[:120], data=f"plan-h{index}")

    def _planned_method(self, index: int, hypothesis: dict) -> list[ft.Control]:
        """The analysis the plan names: compared with the one that is run."""
        from workspace_methods import METHODS

        ui = self.app.ui
        key = hypothesis.get("method_key") or ""
        methods = [("", ui.t("plan.h.method_none"))] + [
            (spec.key, engine_label(ui.language, spec.title)) for spec in METHODS.values()]
        controls: list[ft.Control] = [wc.dropdown(
            ui, ui.t("plan.h.method_key"), methods, key,
            on_select=lambda e, i=index: self._set_method(i, e.control.value), width=420,
            data=f"plan-h{index}-method_key")]
        spec = METHODS.get(key)
        variant = next((o for o in spec.options if o.key == "method"), None) if spec else None
        if variant is not None:
            choices = [("", ui.t("plan.h.method_none"))] + [
                (k, engine_label(ui.language, v)) for k, v in variant.choices]
            controls.append(wc.dropdown(
                ui, ui.t("plan.h.variant"), choices,
                (hypothesis.get("method_options") or {}).get("method", ""),
                on_select=lambda e, i=index: self._set_variant(i, e.control.value), width=320,
                data=f"plan-h{index}-variant"))
        return [ft.Row(controls, wrap=True, spacing=tk.SPACE_2)]

    # ------------------------------------------------------------- actions
    def _set_question(self, index: int, key: str, value: str) -> None:
        question = self.draft["questions"][index]
        self._use_question(question.get("id"))
        question[key] = value                            # no re-render while typing

    def _set_question_type(self, index: int, value) -> None:
        question = self.draft["questions"][index]
        self._use_question(question.get("id"))
        question["type"] = value or ""
        for hypothesis in self.draft["hypotheses"]:
            if hypothesis.get("question_id") == question.get("id"):
                self._prune_roles(hypothesis)
        self.app.render()                                # the H1 hints follow the kind

    def _remove_question(self, index: int) -> None:
        removed = self.draft["questions"].pop(index)
        self._use_question(removed.get("id"))
        for hypothesis in self.draft["hypotheses"]:
            if hypothesis.get("question_id") == removed.get("id"):
                hypothesis["question_id"] = ""
                self._prune_roles(hypothesis)
        self.app.render()

    def add_question(self, *, prefill: bool = False) -> None:
        """A new research question. The first one starts from the project's
        research question; from the next-action bar an empty question is
        reused rather than a second one added. Q1 shown by itself (from the
        project's research question) is taken into the plan instead of a
        second question being added."""
        if self.current_draft() is None:      # also from a page footer
            return
        questions = self.draft.setdefault("questions", [])
        if self._auto_row() is not None:
            self._use_question(self.auto_question)
            self.app.render()
            return
        empty = [q for q in questions if not str(q.get("text") or "").strip() and not q.get("type")]
        if not (prefill and empty):
            text = self.app.research_question().strip() if not questions else ""
            questions.append({"id": uuid.uuid4().hex[:12], "type": "", "text": text})
        self.app.render()

    def add_hypothesis_for(self, number: int) -> None:
        """A hypothesis of research question Q``number``: H0 is drafted from
        the kind of question; H1 stays empty, with a hint."""
        if self.current_draft() is None:
            return
        questions = self.draft.setdefault("questions", [])
        question = questions[number - 1] if 0 < number <= len(questions) else None
        hypothesis = {"text": "", "direction": "two-sided", "priority": "primary", "alpha": 0.05}
        if question is not None:
            self._use_question(question.get("id"))
            hypothesis["question_id"] = question["id"]
            _, h0 = rw.draft_keys(question.get("type") or "")
            if h0:
                hypothesis["h0"] = self.app.ui.t(h0)
        self.draft["hypotheses"].append(hypothesis)
        self.app.render()

    def _set_question_link(self, index: int, value) -> None:
        hypothesis = self.draft["hypotheses"][index]
        hypothesis["question_id"] = value or ""
        self._use_question(value or None)
        self._prune_roles(hypothesis)
        question = self._questions_by_id().get(value or "")
        if question is not None and not str(hypothesis.get("h0") or "").strip():
            _, h0 = rw.draft_keys(question.get("type") or "")
            if h0:
                hypothesis["h0"] = self.app.ui.t(h0)
        self.app.render()

    # ------------------------------------- planned variables (Stage 37.0b)
    def _goal_of(self, hypothesis: dict) -> str:
        question = self._questions_by_id().get(hypothesis.get("question_id") or "")
        return (question or {}).get("type") or ""

    def _prune_roles(self, hypothesis: dict) -> None:
        """Planned variables belong to the roles of the question's kind: those
        of another kind are left out of the draft (nothing saved is changed)."""
        from workspace_methods import GOAL_ROLES

        roles = hypothesis.get("roles") or {}
        allowed = {role.key for role in GOAL_ROLES.get(self._goal_of(hypothesis), ())}
        kept = {key: value for key, value in roles.items() if key in allowed}
        if kept:
            hypothesis["roles"] = kept
        else:
            hypothesis.pop("roles", None)

    def _set_role(self, index: int, role, names: list[str]) -> None:
        hypothesis = self.draft["hypotheses"][index]
        roles = dict(hypothesis.get("roles") or {})
        names = [n for n in dict.fromkeys(str(n).strip() for n in names) if n]
        if names:
            roles[role.key] = names if role.multiple else names[0]
        else:
            roles.pop(role.key, None)
        if roles:
            hypothesis["roles"] = roles
        else:
            hypothesis.pop("roles", None)

    def _type_role(self, index: int, role, value: str) -> None:
        self._set_role(index, role, value.split(","))   # no re-render while typing

    def _pick_role(self, index: int, role, value) -> None:
        self._set_role(index, role, [value] if value else [])

    def _toggle_role(self, index: int, role, name: str, value: bool) -> None:
        planned = (self.draft["hypotheses"][index].get("roles") or {}).get(role.key) or []
        names = list(planned) if isinstance(planned, list) else [planned]
        if value and name not in names:
            names.append(name)
        if not value:
            names = [n for n in names if n != name]
        self._set_role(index, role, names)

    def _planned_roles(self, index: int, hypothesis: dict) -> list[ft.Control]:
        """The variables the plan names for each role of the question's kind
        (design §7.3). Chosen from the data once it is open; typed as names
        before that. A planned name missing from the data is shown as such.
        The check H-VARIABLES-DIFFER compares them with the analysis run."""
        from workspace_analyze import _variable_options
        from workspace_methods import GOAL_ROLES

        roles = GOAL_ROLES.get(self._goal_of(hypothesis))
        if not roles:
            return []
        ui, session = self.app.ui, self.app.session
        planned = hypothesis.get("roles") or {}
        options = _variable_options(ui, session) if session.has_data else []
        present = {name for name, _ in options}
        controls: list[ft.Control] = [wc.section_label(ui, ui.t("plan.h.roles")),
                                      wc.caption(ui, ui.t("plan.h.roles_body"))]
        missing: list[str] = []
        for role in roles:
            value = planned.get(role.key)
            chosen = list(value) if isinstance(value, list) else ([value] if value else [])
            data = f"plan-h{index}-role-{role.key}"
            if not options:
                controls.append(wc.text_field(
                    ui, ui.t(role.label), ", ".join(chosen), hint=ui.t("plan.h.roles_hint"),
                    on_change=lambda e, i=index, r=role: self._type_role(i, r, e.control.value or ""),
                    data=data))
                continue
            missing += [name for name in chosen if name not in present]
            if role.multiple:
                boxes = [wc.checkbox(ui, text, name in chosen,
                                     on_change=lambda e, i=index, r=role, n=name: self._toggle_role(
                                         i, r, n, bool(e.control.value)),
                                     data=f"{data}-{name}") for name, text in options]
                controls.append(ft.Column([
                    wc.text(ui, ui.t(role.label), tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                    ft.Row(boxes, wrap=True, spacing=tk.SPACE_4, run_spacing=0)],
                    spacing=tk.SPACE_1, data=data))
            else:
                choices = ([("", ui.t("plan.h.role_none"))] + options
                           + [(name, ui.t("plan.h.role_missing", name=name))
                              for name in chosen if name not in present])
                controls.append(wc.dropdown(
                    ui, ui.t(role.label), choices, chosen[0] if chosen else "",
                    on_select=lambda e, i=index, r=role: self._pick_role(i, r, e.control.value),
                    width=360, data=data))
        if missing:
            controls.append(wc.notice(ui, ui.t("plan.h.roles_missing",
                                               names=", ".join(dict.fromkeys(missing))),
                                      "warning", data=f"plan-h{index}-roles-missing"))
        return controls

    def _set_method(self, index: int, value) -> None:
        hypothesis = self.draft["hypotheses"][index]
        hypothesis["method_key"] = value or ""
        hypothesis.pop("method_options", None)           # options belong to a method
        self.app.render()

    def _set_variant(self, index: int, value) -> None:
        hypothesis = self.draft["hypotheses"][index]
        options = dict(hypothesis.get("method_options") or {})
        if value:
            options["method"] = value
        else:
            options.pop("method", None)
        hypothesis["method_options"] = options

    def _set_priority(self, index: int, value) -> None:
        self._set_hypothesis(index, "priority", value)
        self.app.render()                                # a reason may now be needed

    def _set_reason(self, hypothesis_id: str, value: str) -> None:
        self.reasons[hypothesis_id] = value              # no re-render while typing

    def _add(self, e=None):
        self.draft["hypotheses"].append({"text": "", "direction": "two-sided",
                                         "priority": "primary", "alpha": 0.05})
        self.app.render()

    def _remove(self, index: int):
        del self.draft["hypotheses"][index]
        self.app.render()

    def _to_save(self) -> dict:
        """The draft as saved: a hypothesis keeps its question only if the
        question has a kind or a sentence (empty questions are not saved)."""
        draft = copy.deepcopy(self.draft)
        kept = {q.get("id") for q in draft.get("questions", [])
                if str(q.get("text") or "").strip() or q.get("type")}
        for hypothesis in draft.get("hypotheses", []):
            if hypothesis.get("question_id") and hypothesis["question_id"] not in kept:
                hypothesis["question_id"] = ""
        return draft

    def save(self, e=None):
        from project_store import DesignationReasonNeeded, ProjectError

        project = self._project()
        if project is None or self.current_draft() is None:
            return
        ui = self.app.ui
        before = project.plan()
        hypotheses = self.draft["hypotheses"]
        missing = [number for number, h in enumerate(hypotheses, start=1)
                   if str(h.get("text") or "").strip() and self._needs_reason(project, h)
                   and not self.reasons.get(h.get("id"), "").strip()]
        if missing:
            self.feedback = (self._reason_message(project, missing[0],
                                                  hypotheses[missing[0] - 1]), "danger")
            self.app.render()
            return
        reasons = {hid: text.strip() for hid, text in self.reasons.items() if text.strip()}
        try:
            version = project.save_plan(self._to_save(), reasons=reasons)
        except DesignationReasonNeeded as error:
            ids = [h.get("id") for h in hypotheses]
            number = ids.index(error.hypotheses[0]) + 1 if error.hypotheses[0] in ids else 1
            self.feedback = (self._reason_message(project, number, hypotheses[number - 1])
                             if number <= len(hypotheses) else
                             ui.t("plan.change_reason_needed", h=number), "danger")
            self.app.render()
            return
        except (ProjectError, OSError) as error:
            self.feedback = (ui.t("plan.invalid", reason=str(error)), "danger")
            self.app.render()
            return
        if before is not None and before["version"] == version:
            self.feedback = (ui.t("plan.unchanged"), "info")
        else:
            self.feedback = (ui.t("plan.saved", version=version), "success")
        self._write_through(project.plan()["plan"])
        self.draft = copy.deepcopy(project.plan()["plan"])
        self.draft.setdefault("questions", [])
        self.auto_question = None
        self._show_question_row()
        self.reasons = {}
        self.app.render()

    _save = save
