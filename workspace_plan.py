"""The research plan card of the project page (Stage 35, #40).

Objectives, design, population, ethics notes and an optional
preregistration reference, then the hypotheses. Each hypothesis records:
- H1 and H0;
- its direction (two-sided, greater, less);
- whether it is primary, secondary or exploratory;
- the outcome, predictors or groups and covariates;
- the intended method, the significance level, the multiplicity family and
  the exclusion policy.

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

import flet as ft

import workspace_components as wc
import workspace_tokens as tk

EMPTY_PLAN = {"objectives": "", "design": "", "population": "", "ethics": "",
              "preregistration": "", "hypotheses": []}
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

    def _set(self, key: str, value: str) -> None:
        self.draft[key] = value

    def _set_hypothesis(self, index: int, key: str, value) -> None:
        self.draft["hypotheses"][index][key] = value

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
        rows.append(wc.section_label(ui, ui.t("plan.hypotheses")))
        for index, hypothesis in enumerate(self.draft["hypotheses"]):
            rows.append(self._hypothesis(index, hypothesis, status.get(hypothesis.get("id", ""))))
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

    def _hypothesis(self, index: int, hypothesis: dict, standing: dict | None) -> ft.Control:
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
        for key, multiline in HYPOTHESIS_TEXT:
            fields.append(wc.text_field(
                ui, ui.t(f"plan.h.{key}"), str(hypothesis.get(key, "")), multiline=multiline,
                on_change=lambda e, i=index, k=key: self._set_hypothesis(i, k, e.control.value or ""),
                data=f"plan-h{index}-{key}"))
        fields.append(ft.Row([
            wc.dropdown(ui, ui.t("plan.h.direction"),
                        [(d, ui.t(f"plan.direction.{d}")) for d in ("two-sided", "greater", "less")],
                        hypothesis.get("direction", "two-sided"),
                        on_select=lambda e, i=index: self._set_hypothesis(i, "direction", e.control.value),
                        data=f"plan-h{index}-direction"),
            wc.dropdown(ui, ui.t("plan.h.priority"),
                        [(p, ui.t(f"plan.priority.{p}")) for p in ("primary", "secondary", "exploratory")],
                        hypothesis.get("priority", "primary"),
                        on_select=lambda e, i=index: self._set_hypothesis(i, "priority", e.control.value),
                        data=f"plan-h{index}-priority"),
            wc.text_field(ui, ui.t("plan.h.alpha"), str(hypothesis.get("alpha", 0.05)), width=140,
                          on_change=lambda e, i=index: self._set_hypothesis(i, "alpha", e.control.value),
                          data=f"plan-h{index}-alpha"),
        ], wrap=True, spacing=tk.SPACE_2))
        fields.append(wc.button(ui, ui.t("plan.remove"), lambda e, i=index: self._remove(i),
                                icon=ft.Icons.DELETE_OUTLINE, data=f"plan-h{index}-remove"))
        title = hypothesis.get("text") or ui.t("plan.h.untitled")
        return wc.card(ui, fields, title=f"H{index + 1}. {title}"[:120], data=f"plan-h{index}")

    # ------------------------------------------------------------- actions
    def _add(self, e=None):
        self.draft["hypotheses"].append({"text": "", "direction": "two-sided",
                                         "priority": "primary", "alpha": 0.05})
        self.app.render()

    def _remove(self, index: int):
        del self.draft["hypotheses"][index]
        self.app.render()

    def _save(self, e=None):
        from project_store import ProjectError

        project = self._project()
        if project is None:
            return
        ui = self.app.ui
        before = project.plan()
        try:
            version = project.save_plan(self.draft)
        except (ProjectError, OSError) as error:
            self.feedback = (ui.t("plan.invalid", reason=str(error)), "danger")
            self.app.render()
            return
        if before is not None and before["version"] == version:
            self.feedback = (ui.t("plan.unchanged"), "info")
        else:
            self.feedback = (ui.t("plan.saved", version=version), "success")
        self.draft = copy.deepcopy(project.plan()["plan"])
        self.app.render()
