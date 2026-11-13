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
        self.draft.setdefault("questions", [])
        self.draft.setdefault("hypotheses", [])

    def current_draft(self) -> dict | None:
        """The plan as it is on screen (unsaved changes included)."""
        project = self._project() if self.app.projects.active else None
        if project is None:
            return None
        self._sync(project)
        return self.draft

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

    def _needs_reason(self, project, hypothesis: dict) -> bool:
        """A saved hypothesis whose priority changes while results exist."""
        if not self.app.session.results:
            return False
        saved = self._saved_priorities(project)
        hypothesis_id = hypothesis.get("id")
        return (hypothesis_id in saved
                and saved[hypothesis_id] != hypothesis.get("priority", "primary"))

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
            rows.append(ft.Container(ft.Column([
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
                                           runs=standing["runs_before"]), tone,
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
            fields.append(wc.text_field(
                ui, ui.t("plan.h.reason"), self.reasons.get(hypothesis["id"], ""), multiline=True,
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
        self.draft["questions"][index][key] = value      # no re-render while typing

    def _set_question_type(self, index: int, value) -> None:
        self.draft["questions"][index]["type"] = value or ""
        self.app.render()                                # the H1 hints follow the kind

    def _remove_question(self, index: int) -> None:
        removed = self.draft["questions"].pop(index)
        for hypothesis in self.draft["hypotheses"]:
            if hypothesis.get("question_id") == removed.get("id"):
                hypothesis["question_id"] = ""
        self.app.render()

    def add_question(self, *, prefill: bool = False) -> None:
        """A new research question. The first one starts from the project's
        research question; from the next-action bar an empty question is
        reused rather than a second one added."""
        questions = self.draft.setdefault("questions", [])
        empty = [q for q in questions if not str(q.get("text") or "").strip() and not q.get("type")]
        if not (prefill and empty):
            text = self.app.research_question().strip() if not questions else ""
            questions.append({"id": uuid.uuid4().hex[:12], "type": "", "text": text})
        self.app.render()

    def add_hypothesis_for(self, number: int) -> None:
        """A hypothesis of research question Q``number``: H0 is drafted from
        the kind of question; H1 stays empty, with a hint."""
        questions = self.draft.setdefault("questions", [])
        question = questions[number - 1] if 0 < number <= len(questions) else None
        hypothesis = {"text": "", "direction": "two-sided", "priority": "primary", "alpha": 0.05}
        if question is not None:
            hypothesis["question_id"] = question["id"]
            _, h0 = rw.draft_keys(question.get("type") or "")
            if h0:
                hypothesis["h0"] = self.app.ui.t(h0)
        self.draft["hypotheses"].append(hypothesis)
        self.app.render()

    def _set_question_link(self, index: int, value) -> None:
        hypothesis = self.draft["hypotheses"][index]
        hypothesis["question_id"] = value or ""
        question = self._questions_by_id().get(value or "")
        if question is not None and not str(hypothesis.get("h0") or "").strip():
            _, h0 = rw.draft_keys(question.get("type") or "")
            if h0:
                hypothesis["h0"] = self.app.ui.t(h0)
        self.app.render()

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
        if project is None:
            return
        ui = self.app.ui
        before = project.plan()
        hypotheses = self.draft["hypotheses"]
        missing = [number for number, h in enumerate(hypotheses, start=1)
                   if str(h.get("text") or "").strip() and self._needs_reason(project, h)
                   and not self.reasons.get(h.get("id"), "").strip()]
        if missing:
            self.feedback = (ui.t("plan.reason_needed", h=missing[0]), "danger")
            self.app.render()
            return
        reasons = {hid: text.strip() for hid, text in self.reasons.items() if text.strip()}
        try:
            version = project.save_plan(self._to_save(), reasons=reasons)
        except DesignationReasonNeeded as error:
            ids = [h.get("id") for h in hypotheses]
            number = ids.index(error.hypotheses[0]) + 1 if error.hypotheses[0] in ids else 1
            self.feedback = (ui.t("plan.reason_needed", h=number), "danger")
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
        self.draft = copy.deepcopy(project.plan()["plan"])
        self.draft.setdefault("questions", [])
        self.reasons = {}
        self.app.render()

    _save = save
