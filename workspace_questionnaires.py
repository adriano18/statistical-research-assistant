"""Questionnaire builder (list / editor / respondent preview) and the
scientific import workspace (source / review / preview).

Storage and validation are the classic ``survey_storage`` functions:
drafts are validated with ``validate_questions`` before publishing, a
published questionnaire is immutable, and responses are written only
through ``submit_response``. The import workspace drives
``import_session.ImportSession`` — the classic importer pipeline.
"""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import flet as ft

import workspace_components as wc
import workspace_tokens as tk
from import_session import ImportSession
from workspace_text import count_text

KINDS = ("single_choice", "multiple_choice", "likert5", "likert7", "rating_scale",
         "yes_no", "number", "short_text", "long_text", "date", "consent")
CHOICE_KINDS = {"single_choice", "multiple_choice"}
SCALE_KINDS = {"likert5", "likert7", "rating_scale"}
CONDITION_PARENTS = {"single_choice", "yes_no", "likert5", "likert7", "rating_scale", "number"}
OPERATORS = (("equals", "Equals"), ("not_equals", "Not equal"),
             ("greater", "Greater than"), ("less", "Less than"))


def scale_library(language: str, draft: list[dict]) -> list[tuple[str, str, dict]]:
    """(id, label, {"kind", "value_labels"}) — presets plus scales in the draft."""
    from survey_ui import preset_value_labels, semantic_differential_labels

    library = []
    for name, label in (("agreement", "Agreement"), ("frequency", "Frequency"),
                        ("quality", "Quality: poor → good")):
        for kind in ("likert5", "likert7"):
            try:
                labels = preset_value_labels(name, kind, language)
            except (KeyError, ValueError):
                continue
            library.append((f"{name}-{kind}", f"{label} · {kind[-1]} points",
                            {"kind": kind, "value_labels": labels}))
    library.append(("semantic", "Semantic differential −3…3",
                    {"kind": "rating_scale", "value_labels": semantic_differential_labels(language)}))
    seen = set()
    for q in draft:
        labels = q.get("value_labels") or {}
        if q.get("kind") in SCALE_KINDS and labels:
            signature = tuple(labels.items())
            if signature not in seen and len(library) < 40:
                seen.add(signature)
                library.append((f"draft-{len(seen)}", "From this draft: "
                                + " / ".join(list(labels.values())[:3])
                                + ("…" if len(labels) > 3 else ""),
                                {"kind": q["kind"], "value_labels": dict(labels)}))
    return library


def respondent_question(ui: wc.Ui, question: dict, value, on_change, *, number: int | None = None,
                        width: int | None = None) -> ft.Control:
    """One question rendered with the control a respondent will use."""
    from survey_storage import likert_choices

    kind = question.get("kind")
    prompt = question.get("prompt", "")
    title = (f"{number}. " if number else "") + prompt + (" *" if question.get("required") else "")
    controls: list[ft.Control] = [wc.text(ui, title, tk.TYPE_BODY_L, weight=ft.FontWeight.W_500)]
    key = question.get("key", "")

    def radio(options: list[tuple[str, str]]):
        return ft.RadioGroup(
            value=None if value is None else str(value),
            on_change=lambda e: on_change(key, e.control.value),
            content=ft.Column([ft.Radio(value=v, label=label,
                                        label_style=ft.TextStyle(size=14, color=ui.p.text))
                               for v, label in options], spacing=0),
            data=f"answer-{key}")

    if kind in CHOICE_KINDS and kind == "single_choice":
        controls.append(radio([(o, o) for o in question.get("options", [])]))
    elif kind == "multiple_choice":
        chosen = list(value or [])
        controls.append(ft.Column([
            wc.checkbox(ui, option, option in chosen,
                        on_change=lambda e, o=option: on_change(
                            key, sorted({*chosen, o} if e.control.value else set(chosen) - {o},
                                        key=question["options"].index)),
                        data=f"answer-{key}-{option}")
            for option in question.get("options", [])], spacing=0))
    elif kind in SCALE_KINDS:
        try:
            options = [(str(code), label) for code, label in likert_choices(question)]
        except (ValueError, KeyError):
            options = []
        options += [(code, label) for code, label in (question.get("missing_options") or {}).items()]
        controls.append(radio(options))
    elif kind == "yes_no":
        controls.append(radio([("Yes", ui.t("common.yes")), ("No", ui.t("common.no"))]))
    elif kind == "consent":
        controls.append(wc.checkbox(ui, question.get("prompt", ""), value is True,
                                    on_change=lambda e: on_change(key, bool(e.control.value)),
                                    data=f"answer-{key}"))
    else:
        field = wc.text_field(ui, ui.t("q.your_answer"), "" if value is None else str(value),
                              multiline=kind == "long_text", width=width,
                              on_change=lambda e: on_change(key, e.control.value),
                              hint="YYYY-MM-DD" if kind == "date" else None,
                              data=f"answer-{key}")
        if kind == "number":
            field.keyboard_type = ft.KeyboardType.NUMBER
        controls.append(field)
    return ft.Container(ft.Column(controls, spacing=tk.SPACE_2),
                        padding=ft.Padding.symmetric(vertical=tk.SPACE_2),
                        data=f"preview-{key}")


class QuestionnairesPage:
    def __init__(self, app):
        self.app = app
        self.title = ""
        self.description = ""
        self.draft: list[dict] = []
        self.origin = ""
        self.selected: int | None = None
        self.pane = "edit"           # compact layouts: "list" | "edit" | "preview"
        self.preview_width = "desktop"
        self.preview_answers: dict = {}
        self.editor_error = ""
        self.feedback: tuple[str, str] | None = None
        self.template = "psychology"
        self.scale_choice: str | None = None

    # ------------------------------------------------------------- build
    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        header = wc.page_header(ui, ui.t("q.title"), ui.t("q.subtitle"), actions=[
            wc.button(ui, ui.t("q.import"), action=app.open_document_action,
                      icon=ft.Icons.DOCUMENT_SCANNER_OUTLINED, data="q-import"),
            wc.button(ui, ui.t("q.publish"), self._ask_publish, kind="primary",
                      icon=ft.Icons.PUBLISH, disabled=not self.draft, data="q-publish"),
        ])
        meta = ft.Row([
            wc.text_field(ui, ui.t("q.survey_title"), self.title, width=420,
                          on_change=lambda e: setattr(self, "title", e.control.value or ""),
                          data="q-title"),
            wc.text_field(ui, ui.t("q.instructions"), self.description, expand=True,
                          on_change=lambda e: setattr(self, "description", e.control.value or ""),
                          data="q-description"),
        ], spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.START)
        status = [wc.chip(ui, ui.t("q.unsaved"), "warning", icon=ft.Icons.EDIT_NOTE)] \
            if self.draft else []
        if self.origin:
            status.append(wc.chip(ui, self.origin, "info", icon=ft.Icons.SOURCE_OUTLINED))
        width = app.content_width
        list_pane = self._list_pane()
        editor = self._editor_pane()
        preview = self._preview_pane()
        if width >= tk.BREAKPOINT_COMPACT - tk.SIDEBAR_EXPANDED:
            panes = ft.Row([
                ft.Container(list_pane, width=tk.PANE_LIST_WIDTH),
                ft.Container(editor, expand=True),
                ft.Container(preview, width=tk.PANE_PREVIEW_WIDTH),
            ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=tk.SPACE_4)
        else:
            switch = wc.segmented(ui, [("list", ui.t("q.questions")), ("edit", ui.t("q.editor")),
                                       ("preview", ui.t("q.preview"))], self.pane,
                                  self._set_pane, data="q-pane")
            current = {"list": list_pane, "edit": editor, "preview": preview}[self.pane]
            panes = ft.Column([switch, current], spacing=tk.SPACE_3)
        body = [header, meta, ft.Row(status, spacing=tk.SPACE_2, wrap=True), panes]
        if self.feedback:
            body.append(wc.notice(ui, self.feedback[0], self.feedback[1], data="q-feedback"))
        body.append(self._published())
        return app.constrained(ft.Column(body, spacing=tk.SPACE_4,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.CONTENT_MAX_WIDTH + 280)

    def _set_pane(self, pane: str):
        self.pane = pane
        self.app.render()

    # -------------------------------------------------------------- list
    def _list_pane(self) -> ft.Control:
        ui = self.app.ui
        items = []
        for index, q in enumerate(self.draft):
            selected = index == self.selected
            flags = []
            if q.get("required"):
                flags.append(ft.Icon(ft.Icons.EMERGENCY, size=14, color=ui.p.text_muted,
                                     tooltip=ui.t("q.required")))
            if q.get("condition"):
                flags.append(ft.Icon(ft.Icons.CALL_SPLIT, size=14, color=ui.p.text_muted,
                                     tooltip=ui.t("q.condition")))
            items.append(ft.Container(
                content=ft.Row([
                    wc.text(ui, str(index + 1), tk.TYPE_LABEL, color=ui.p.text_muted),
                    ft.Column([wc.text(ui, q.get("prompt", ""), tk.TYPE_BODY, max_lines=2),
                               ft.Row([wc.caption(ui, ui.t(f"kind.{q.get('kind')}")), *flags],
                                      spacing=tk.SPACE_1)], spacing=2, expand=True),
                ], spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.START),
                bgcolor=ui.p.accent_subtle if selected else ui.p.surface,
                border=ft.Border.all(1, ui.p.accent if selected else ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_3, ink=True,
                on_click=lambda e, i=index: self._select(i), key=f"q-{index}-{q.get('key')}",
                data=f"q-item-{index}",
            ))
        listing: ft.Control
        if items:
            listing = ft.ReorderableListView(
                controls=items, on_reorder=self._reorder, spacing=tk.SPACE_2,
                height=min(560, 72 * len(items) + 16), data="q-list",
                show_default_drag_handles=True)
        else:
            listing = wc.caption(ui, ui.t("q.empty"))
        templates = wc.dropdown(ui, ui.t("q.template"), [
            ("psychology", "Psychology / Likert"), ("demographics", "Demographics"),
            ("hr", "HR / Workplace"), ("marketing", "Marketing / Feedback")],
            self.template, on_select=lambda e: setattr(self, "template", e.control.value),
            width=None, data="q-template")
        return wc.card(ui, [
            ft.Row([wc.button(ui, ui.t("q.add"), self._add, kind="primary", icon=ft.Icons.ADD,
                              data="q-add")], wrap=True),
            listing,
            wc.caption(ui, ui.t("q.drag_hint")),
            wc.divider(ui),
            templates,
            wc.button(ui, ui.t("common.continue"), self._load_template, kind="quiet",
                      icon=ft.Icons.AUTO_AWESOME_MOSAIC_OUTLINED, data="q-template-load"),
        ], title=ui.t("q.questions"), padding=tk.SPACE_4, data="q-list-pane")

    def _select(self, index: int):
        self.selected = index
        self.editor_error = ""
        self.pane = "edit"
        self.app.render()

    def _reorder(self, e):
        from survey_storage import reorder_questions

        old, new = e.old_index, e.new_index
        if old is None or new is None or old == new:
            return
        if new > old:
            new -= 1
        try:
            self.draft = reorder_questions(self.draft, old, new)
        except ValueError as error:
            self.feedback = (str(error), "warning")
        self.selected = new
        self.app.render()

    def _move(self, step: int):
        if self.selected is None:
            return
        old, new = self.selected, self.selected + step
        if 0 <= new < len(self.draft):
            draft = list(self.draft)
            draft.insert(new, draft.pop(old))
            self.draft, self.selected = draft, new
            self.app.render()

    def _unique_key(self, base: str = "q") -> str:
        keys = {q.get("key") for q in self.draft}
        number = len(self.draft) + 1
        while f"{base}{number}" in keys:
            number += 1
        return f"{base}{number}"

    def _add(self, e=None):
        page = self.draft[-1].get("page", 1) if self.draft else 1
        self.draft.append({"key": self._unique_key(), "prompt": "New question",
                           "kind": "likert5", "required": False, "page": page,
                           "value_labels": {}})
        self.selected = len(self.draft) - 1
        self.app.render()

    def _load_template(self, e=None):
        from survey_ui import _template_questions

        if self.draft and self.feedback != ("replace", "confirm"):
            self.feedback = ("replace", "confirm")
        self.draft = copy.deepcopy(_template_questions(self.template))
        self.selected = 0 if self.draft else None
        self.origin = ""
        self.feedback = None
        self.app.render()

    def load_draft(self, questions: list[dict], *, title: str = "", origin: str = ""):
        """Entry point used by the scientific import workspace."""
        self.draft = copy.deepcopy(questions)
        self.selected = 0 if questions else None
        if title and not self.title:
            self.title = title
        self.origin = origin

    # ------------------------------------------------------------ editor
    def _editor_pane(self) -> ft.Control:
        ui = self.app.ui
        if self.selected is None or self.selected >= len(self.draft):
            return wc.empty_state(ui, ft.Icons.EDIT_NOTE, ui.t("q.editor"), ui.t("q.empty"),
                                  actions=[wc.button(ui, ui.t("q.add"), self._add, kind="primary")])
        q = self.draft[self.selected]
        kind = q.get("kind")
        fields: list[ft.Control] = [
            wc.text_field(ui, ui.t("q.prompt"), q.get("prompt", ""), multiline=True,
                          on_change=lambda e: self._set("prompt", e.control.value),
                          data="editor-prompt"),
            ft.Row([
                wc.text_field(ui, ui.t("q.key"), q.get("key", ""), width=220,
                              on_change=lambda e: self._set("key", e.control.value),
                              data="editor-key"),
                wc.dropdown(ui, ui.t("q.kind"), [(k, ui.t(f"kind.{k}")) for k in KINDS], kind,
                            on_select=lambda e: self._set_kind(e.control.value), width=260,
                            data="editor-kind"),
            ], wrap=True, spacing=tk.SPACE_3),
        ]
        if kind in CHOICE_KINDS:
            fields.append(wc.text_field(
                ui, ui.t("q.options"), "\n".join(q.get("options", [])), multiline=True,
                on_change=lambda e: self._set("options", [x.strip() for x in
                                                          (e.control.value or "").splitlines()
                                                          if x.strip()]),
                data="editor-options"))
        if kind in SCALE_KINDS:
            library = scale_library(ui.language, self.draft)
            labels = q.get("value_labels") or {}
            fields += [
                wc.section_label(ui, ui.t("q.scales_library")),
                ft.Row([
                    wc.dropdown(ui, ui.t("q.scale"), [(i, label) for i, label, _ in library],
                                self.scale_choice, on_select=lambda e: setattr(
                                    self, "scale_choice", e.control.value), width=340,
                                data="editor-scale"),
                    wc.button(ui, ui.t("q.apply"), lambda e: self._apply_scale(False),
                              data="editor-scale-apply"),
                    wc.button(ui, ui.t("q.apply_scale_all"), lambda e: self._apply_scale(True),
                              kind="quiet", data="editor-scale-all"),
                ], wrap=True, spacing=tk.SPACE_2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([wc.chip(ui, f"{code} = {label}", "neutral", icon=ft.Icons.CIRCLE_OUTLINED)
                        for code, label in labels.items()], wrap=True, spacing=tk.SPACE_1),
            ]
        fields += [
            ft.Row([
                wc.text_field(ui, ui.t("q.section"), q.get("section", ""), width=260,
                              on_change=lambda e: self._set("section", e.control.value)),
                wc.checkbox(ui, ui.t("q.required"), bool(q.get("required")),
                            on_change=lambda e: self._set("required", bool(e.control.value)),
                            data="editor-required"),
            ], wrap=True, spacing=tk.SPACE_4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            *self._condition_editor(q),
        ]
        if self.editor_error:
            fields.append(wc.notice(ui, ui.t("q.invalid", error=self.editor_error), "danger",
                                    data="editor-error"))
        fields.append(ft.Row([
            wc.button(ui, ui.t("q.apply"), self._apply, kind="primary", icon=ft.Icons.CHECK,
                      data="editor-apply"),
            wc.icon_button(ui, ft.Icons.ARROW_UPWARD, ui.t("reports.move_up"),
                           lambda e: self._move(-1), disabled=self.selected == 0),
            wc.icon_button(ui, ft.Icons.ARROW_DOWNWARD, ui.t("reports.move_down"),
                           lambda e: self._move(1), disabled=self.selected == len(self.draft) - 1),
            wc.icon_button(ui, ft.Icons.CONTENT_COPY, ui.t("q.duplicate"), self._duplicate),
            wc.icon_button(ui, ft.Icons.DELETE_OUTLINE, ui.t("q.delete"), self._delete,
                           data="editor-delete"),
        ], spacing=tk.SPACE_2, wrap=True))
        return wc.card(ui, fields, title=f"{ui.t('q.editor')} · {self.selected + 1}",
                       padding=tk.SPACE_4, data="q-editor-pane")

    def _condition_editor(self, q: dict) -> list[ft.Control]:
        ui = self.app.ui
        earlier = [p for p in self.draft[:self.selected] if p.get("kind") in CONDITION_PARENTS]
        condition = q.get("condition") or {}
        options = [("", ui.t("q.condition_always"))] + [
            (p["key"], f"{p['key']} · {p.get('prompt', '')[:40]}") for p in earlier]
        controls = [wc.dropdown(ui, ui.t("q.condition"), options, condition.get("question", ""),
                                on_select=lambda e: self._set_condition("question",
                                                                        e.control.value),
                                width=340, data="editor-condition")]
        if condition.get("question"):
            controls += [
                wc.dropdown(ui, "Condition operator", list(OPERATORS),
                            condition.get("operator", "equals"),
                            on_select=lambda e: self._set_condition("operator", e.control.value),
                            width=200),
                wc.text_field(ui, ui.t("q.condition_value"), str(condition.get("value", "")),
                              width=200, on_change=lambda e: self._set_condition(
                                  "value", e.control.value)),
            ]
        return [ft.Row(controls, wrap=True, spacing=tk.SPACE_3)]

    def _set(self, name: str, value):
        self.draft[self.selected][name] = value

    def _set_kind(self, kind: str):
        q = self.draft[self.selected]
        q["kind"] = kind
        if kind not in CHOICE_KINDS:
            q.pop("options", None)
        else:
            q.setdefault("options", ["Option 1", "Option 2"])
        if kind not in SCALE_KINDS:
            for name in ("value_labels", "scale_id", "missing_options"):
                q.pop(name, None)
            q["reverse_scored"] = False
        if kind == "consent":
            q["required"] = True
        self.app.render()

    def _set_condition(self, name: str, value):
        q = self.draft[self.selected]
        if name == "question" and not value:
            q.pop("condition", None)
        else:
            condition = dict(q.get("condition") or {"operator": "equals", "value": ""})
            condition[name] = value
            q["condition"] = condition
        self.app.render()

    def _apply_scale(self, all_in_section: bool):
        library = {i: spec for i, _, spec in scale_library(self.app.ui.language, self.draft)}
        spec = library.get(self.scale_choice or "")
        if spec is None:
            return
        target = self.draft[self.selected]
        section = target.get("section", "")
        for q in self.draft if all_in_section else [target]:
            if all_in_section and (q.get("kind") not in SCALE_KINDS
                                   or q.get("section", "") != section):
                continue
            q["kind"] = spec["kind"]
            q["value_labels"] = dict(spec["value_labels"])
        self.app.render()

    def _apply(self, e=None):
        from survey_storage import validate_questions

        try:
            validate_questions(self._for_validation())
            self.editor_error = ""
            self.app.status(self.app.t("run.done"), "success")
        except ValueError as error:
            self.editor_error = str(error)
        self.app.render()

    def _for_validation(self) -> list[dict]:
        cleaned = []
        for q in copy.deepcopy(self.draft):
            condition = q.get("condition")
            if condition and not condition.get("question"):
                q.pop("condition", None)
            cleaned.append(q)
        return cleaned

    def _duplicate(self, e=None):
        q = copy.deepcopy(self.draft[self.selected])
        q["key"] = self._unique_key(q.get("key", "q") + "_copy")
        q.pop("condition", None)
        self.draft.insert(self.selected + 1, q)
        self.selected += 1
        self.app.render()

    def _delete(self, e=None):
        removed = self.draft.pop(self.selected)
        for q in self.draft:  # a dependent condition must not point to a removed question
            if (q.get("condition") or {}).get("question") == removed.get("key"):
                q.pop("condition", None)
        self.selected = min(self.selected, len(self.draft) - 1) if self.draft else None
        self.app.render()

    # ----------------------------------------------------------- preview
    def _preview_pane(self) -> ft.Control:
        ui = self.app.ui
        from survey_storage import question_is_visible

        switch = wc.segmented(ui, [("desktop", ui.t("q.preview_desktop")),
                                   ("phone", ui.t("q.preview_phone"))], self.preview_width,
                              self._set_preview_width, data="q-preview-width")
        width = 340 if self.preview_width == "phone" else None
        controls: list[ft.Control] = [switch]
        if self.title:
            controls.append(wc.heading(ui, self.title, tk.TYPE_TITLE_S))
        page_title = None
        for index, q in enumerate(self.draft):
            try:
                visible = question_is_visible(q, self.preview_answers) if q.get("condition") \
                    else True
            except Exception:
                visible = True
            if not visible:
                continue
            if q.get("page_title") and q.get("page_title") != page_title:
                page_title = q.get("page_title")
                controls.append(wc.section_label(ui, page_title))
            controls.append(respondent_question(ui, q, self.preview_answers.get(q.get("key")),
                                                self._preview_answer, number=index + 1,
                                                width=width))
        if not self.draft:
            controls.append(wc.caption(ui, ui.t("q.empty")))
        frame = ft.Container(ft.Column(controls, spacing=tk.SPACE_2, scroll=ft.ScrollMode.AUTO,
                                       height=880), width=width,
                             bgcolor=ui.p.surface, padding=tk.SPACE_4,
                             border=ft.Border.all(1, ui.p.border), border_radius=ui.radius("card"))
        return ft.Column([wc.heading(ui, ui.t("q.preview"), tk.TYPE_TITLE_S),
                          ft.Row([frame], alignment=ft.MainAxisAlignment.CENTER)],
                         spacing=tk.SPACE_3, data="q-preview-pane")

    def _set_preview_width(self, value: str):
        self.preview_width = value
        self.app.render()

    def _preview_answer(self, key: str, value):
        self.preview_answers[key] = int(value) if isinstance(value, str) and value.lstrip(
            "-").isdigit() else value
        self.app.render()

    # ---------------------------------------------------------- publish
    def _ask_publish(self, e=None):
        ui = self.app.ui
        dialog = ft.AlertDialog(
            modal=True,
            title=wc.heading(ui, ui.t("q.publish").rstrip("…"), tk.TYPE_TITLE_S),
            content=ft.Container(wc.text(ui, ui.t("q.publish_confirm"), tk.TYPE_BODY_L), width=480),
            actions=[wc.button(ui, ui.t("common.cancel"), lambda e: self.app.page.pop_dialog(),
                               kind="quiet"),
                     wc.button(ui, ui.t("q.publish").rstrip("…"), self._publish, kind="primary",
                               data="q-publish-confirm")],
        )
        self.app.page.show_dialog(dialog)

    def _publish(self, e=None):
        from survey_storage import create_survey, validate_questions

        try:
            self.app.page.pop_dialog()
        except Exception:
            pass
        title = (self.title or "").strip() or "Untitled questionnaire"
        try:
            questions = validate_questions(self._for_validation())
            survey = create_survey(self.app.survey_root, title, self.description, questions)
        except (ValueError, OSError) as error:
            self.feedback = (self.app.t("q.invalid", error=error), "danger")
            self.app.render()
            return None
        self.feedback = (self.app.t("q.publish_ok", title=survey.title), "success")
        self.app.render()
        return survey

    # --------------------------------------------------------- published
    def _published(self) -> ft.Control:
        ui = self.app.ui
        try:
            from survey_storage import list_surveys, response_count

            surveys = list_surveys(self.app.survey_root)
        except Exception:
            surveys = []
        rows = []
        for survey in surveys[:12]:
            count = response_count(self.app.survey_root, survey.survey_id)
            rows.append(ft.Row([
                ft.Icon(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, size=18, color=ui.p.text_secondary),
                ft.Column([wc.text(ui, survey.title, tk.TYPE_BODY, weight=ft.FontWeight.W_600),
                           wc.caption(ui, f"{count_text(ui.language, len(survey.questions), 'questions')}"
                                          f" · {count_text(ui.language, count, 'responses')}")],
                          spacing=2, expand=True),
                wc.button(ui, ui.t("q.collect"), lambda e, s=survey: self._collect(s),
                          kind="quiet", icon=ft.Icons.EDIT_NOTE, data=f"collect-{survey.survey_id}"),
                wc.button(ui, ui.t("q.export_responses"), lambda e, s=survey: self._export(s),
                          kind="quiet", icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                          disabled=count == 0),
                wc.button(ui, ui.t("q.analyze_responses"), lambda e, s=survey: self._analyze(s),
                          icon=ft.Icons.QUERY_STATS, disabled=count == 0,
                          data=f"analyze-{survey.survey_id}"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        return wc.card(ui, rows or [wc.caption(ui, ui.t("home.saved_none"))],
                       title=ui.t("q.saved_list"), data="q-published")

    def _collect(self, survey):
        ui = self.app.ui
        answers: dict = {}
        holder = ft.Column(scroll=ft.ScrollMode.AUTO, height=460, width=560, spacing=tk.SPACE_2)
        message = ft.Text("", size=13, color=ui.p.danger)

        def redraw():
            from survey_storage import question_is_visible

            holder.controls = [
                respondent_question(ui, q, answers.get(q["key"]), change, number=i + 1)
                for i, q in enumerate(survey.questions) if question_is_visible(q, answers)
            ]

        def change(key, value):
            answers[key] = value
            redraw()
            try:
                self.app.page.update()
            except Exception:
                pass

        def submit(e=None):
            from survey_storage import submit_response

            try:
                submit_response(self.app.survey_root, survey.survey_id, answers)
            except ValueError as error:
                message.value = str(error)
                self.app.page.update()
                return
            self.app.page.pop_dialog()
            self.feedback = (ui.t("run.done"), "success")
            self.app.render()

        redraw()
        self.app.page.show_dialog(ft.AlertDialog(
            title=wc.heading(ui, survey.title, tk.TYPE_TITLE_S),
            content=ft.Column([holder, message], tight=True),
            actions=[wc.button(ui, ui.t("common.cancel"), lambda e: self.app.page.pop_dialog(),
                               kind="quiet"),
                     wc.button(ui, ui.t("q.collect"), submit, kind="primary",
                               data="collect-submit")],
        ))
        self._collect_state = (answers, submit)

    async def _export(self, survey):
        from survey_storage import save_survey_codebook, save_survey_csv

        destination = await self.app.save_dialog(self.app.t("q.export_responses"),
                                                 f"{survey.survey_id}_responses.csv", "csv")
        if not destination:
            return
        try:
            csv_path = Path(destination)
            book = csv_path.with_name(csv_path.stem + "_codebook.json")
            await asyncio.to_thread(save_survey_csv, self.app.survey_root, survey.survey_id, csv_path)
            await asyncio.to_thread(save_survey_codebook, self.app.survey_root, survey.survey_id,
                                    book)
            self.feedback = (self.app.t("results.saved", path=f"{csv_path} · {book.name}"),
                             "success")
        except Exception as error:
            self.feedback = (self.app.t("results.save_failed", error=error), "danger")
        self.app.render()

    def _analyze(self, survey):
        from survey_storage import responses_dataframe

        df = responses_dataframe(self.app.survey_root, survey.survey_id)
        self.app.session.set_dataset(df, survey.title)
        self.app.status(self.app.t("data.loaded", name=survey.title), "success")
        self.app.navigate("data")


# ================================================================== import
class ImportPage:
    def __init__(self, app):
        self.app = app
        self.session = ImportSession()
        self.page_number = 1
        self.selected: int | None = None
        self.busy = False
        self.feedback: tuple[str, str] | None = None
        self.scale_edits: dict = {}
        self._page_cache: dict = {}

    async def open_files(self, files):
        picked = files[0]
        name = str(getattr(picked, "name", "") or Path(getattr(picked, "path", "") or "").name)
        try:
            if getattr(picked, "path", None):
                binary = await asyncio.to_thread(Path(picked.path).read_bytes)
            else:
                binary = getattr(picked, "bytes", None)
            await self.open_bytes(binary, name)
        except Exception as error:
            self.feedback = (self.app.t("imp.read_failed", error=error), "danger")
            self.app.render()

    async def open_bytes(self, binary: bytes, name: str):
        self.busy, self.feedback = True, (self.app.t("imp.reading"), "info")
        self.app.render()
        try:
            message = await asyncio.to_thread(self.session.open, binary, name)
            ok = self.session.instrument is not None
            self.feedback = ((self.app.t("imp.read_ok", instruments=len(self.session.instruments),
                                         items=sum(len(i.questions)
                                                   for i in self.session.instruments),
                                         name=name), "success") if ok
                             else (self.app.t("imp.read_failed", error=message), "warning"))
        except Exception as error:
            self.feedback = (self.app.t("imp.read_failed", error=error), "danger")
        self.busy = False
        self.page_number, self.selected = 1, None
        self.scale_edits, self._page_cache = {}, {}
        if self.session.instrument is not None:
            self.page_number = self.session.instrument.first_page or 1
        self.app.render()

    # ------------------------------------------------------------- build
    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        header = wc.page_header(ui, ui.t("imp.title"), ui.t("imp.subtitle"), actions=[
            wc.button(ui, ui.t("imp.choose"), action=app.open_document_action, kind="primary",
                      icon=ft.Icons.UPLOAD_FILE, data="imp-choose"),
            wc.button(ui, ui.t("nav.questionnaires"), lambda e: app.navigate("questionnaires"),
                      kind="quiet", icon=ft.Icons.ARROW_BACK),
        ])
        body: list[ft.Control] = [header]
        if self.feedback:
            body.append(wc.notice(ui, self.feedback[0], self.feedback[1], data="imp-feedback"))
        if self.session.source is None:
            body.append(wc.empty_state(ui, ft.Icons.DOCUMENT_SCANNER_OUTLINED,
                                       ui.t("imp.empty.title"), ui.t("imp.empty.body"),
                                       actions=[wc.button(ui, ui.t("imp.choose"),
                                                          action=app.open_document_action,
                                                          kind="primary")],
                                       data="imp-empty"))
            return app.constrained(ft.Column(body, spacing=tk.SPACE_4))
        source = self._source_pane()
        review = self._review_pane()
        preview = self._preview_pane()
        if app.content_width >= 1180:
            panes = ft.Row([ft.Container(source, width=int(app.content_width * 0.34)),
                            ft.Container(review, expand=True),
                            ft.Container(preview, width=tk.PANE_PREVIEW_WIDTH - 40)],
                           vertical_alignment=ft.CrossAxisAlignment.START, spacing=tk.SPACE_4)
        else:
            panes = ft.Column([source, review, preview], spacing=tk.SPACE_4)
        body += [panes, self._checklist()]
        return app.constrained(ft.Column(body, spacing=tk.SPACE_4,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.CONTENT_MAX_WIDTH + 400)

    # ------------------------------------------------------------ source
    def _source_pane(self) -> ft.Control:
        ui, s = self.app.ui, self.session
        count = max(1, s.page_count)
        self.page_number = max(1, min(self.page_number, count))
        key = (self.page_number, 0)
        if key not in self._page_cache:
            try:
                self._page_cache[key] = s.render_page(self.page_number)
            except Exception:
                self._page_cache[key] = None
        png = self._page_cache[key]
        evidence = s.evidence_source
        chips = []
        if evidence == "pdf_text_layer":
            chips.append(wc.chip(ui, ui.t("imp.text_layer"), "info", icon=ft.Icons.TEXT_FIELDS))
        elif evidence == "tesseract_tsv":
            chips.append(wc.chip(ui, "OCR", "warning", icon=ft.Icons.DOCUMENT_SCANNER_OUTLINED))
        controls = [
            ft.Row([
                wc.icon_button(ui, ft.Icons.CHEVRON_LEFT, ui.t("imp.prev_page"),
                               lambda e: self._page(-1), disabled=self.page_number <= 1),
                wc.text(ui, ui.t("imp.page", page=self.page_number, count=count), tk.TYPE_LABEL,
                        data="imp-page"),
                wc.icon_button(ui, ft.Icons.CHEVRON_RIGHT, ui.t("imp.next_page"),
                               lambda e: self._page(1), disabled=self.page_number >= count),
                *chips,
            ], wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                ft.Image(src=png, fit=ft.BoxFit.CONTAIN, semantics_label=s.filename)
                if png else wc.caption(ui, ui.t("common.not_available")),
                bgcolor="#FFFFFF", border=ft.Border.all(1, ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_1, data="imp-source-image"),
        ]
        if Path(s.filename).suffix.lower() == ".pdf":
            controls.append(wc.button(ui, ui.t("imp.ocr_page"), self._ocr_page,
                                      icon=ft.Icons.DOCUMENT_SCANNER_OUTLINED, disabled=self.busy,
                                      data="imp-ocr"))
        if self.app.bridge.open_classic is not None:
            controls.append(wc.button(ui, ui.t("imp.advanced"),
                                      lambda e: self.app.bridge.open_classic("survey"),
                                      kind="quiet", icon=ft.Icons.OPEN_IN_NEW))
        return wc.card(ui, controls, title=f"{ui.t('imp.source')} · {s.filename}",
                       padding=tk.SPACE_4, data="imp-source")

    def _page(self, step: int):
        self.page_number += step
        self.app.render()

    async def _ocr_page(self, e=None):
        self.busy, self.feedback = True, (self.app.t("run.running"), "info")
        self.app.render()
        try:
            message = await asyncio.to_thread(self.session.ocr_pages, [self.page_number])
            self.feedback = (message, "success")
        except Exception as error:
            self.feedback = (self.app.t("imp.read_failed", error=error), "danger")
        self.busy = False
        self.app.render()

    # ------------------------------------------------------------ review
    def _review_pane(self) -> ft.Control:
        ui, s = self.app.ui, self.session
        instrument = s.instrument
        if instrument is None:
            return wc.card(ui, [wc.caption(ui, s.message or ui.t("common.not_available"))],
                           title=ui.t("imp.items"))
        picker = wc.dropdown(ui, ui.t("imp.instrument"), [
            (str(i), f"{x.title} ({count_text(ui.language, len(x.questions), 'questions')})")
            for i, x in enumerate(s.instruments)], str(s.instrument_index),
            on_select=lambda e: self._instrument(int(e.control.value)), width=None,
            data="imp-instrument")
        scales = [self._scale_card(scheme) for scheme in instrument.schemes]
        flags = {i for i, _ in s.flags()}
        items = []
        for index, row in enumerate(instrument.questions):
            selected = index == self.selected
            kind = row.question.get("kind")
            items.append(ft.Container(
                content=ft.Row([
                    wc.text(ui, str(row.number), tk.TYPE_LABEL, color=ui.p.text_muted),
                    ft.Column([
                        wc.text(ui, row.question.get("prompt", ""), tk.TYPE_BODY, max_lines=2),
                        ft.Row([wc.caption(ui, f"p. {row.page} · {ui.t('kind.' + kind)}"),
                                *([wc.chip(ui, ui.t("imp.reviewed"), "success")]
                                  if index in s.reviewed else
                                  [wc.chip(ui, ui.t("imp.flags"), "warning")]
                                  if index in flags else [])], spacing=tk.SPACE_2),
                    ], spacing=2, expand=True),
                ], spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.START),
                bgcolor=ui.p.accent_subtle if selected else ui.p.surface,
                border=ft.Border.all(1, ui.p.accent if selected else ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_2 + 2, ink=True,
                on_click=lambda e, i=index: self._select(i), data=f"imp-item-{index}"))
        detail = []
        if self.selected is not None and self.selected < len(instrument.questions):
            row = instrument.questions[self.selected]
            wording = wc.text_field(ui, ui.t("imp.edit_wording"), row.question.get("prompt", ""),
                                    multiline=True, data="imp-wording")
            low = row.confidence == "low"
            detail = [wc.card(ui, [
                wc.section_label(ui, ui.t("imp.source_excerpt")),
                wc.text(ui, row.excerpt, tk.TYPE_BODY, color=ui.p.text_secondary, selectable=True),
                *[wc.caption(ui, "• " + note) for note in row.notes],
                *([wc.checkbox(ui, ui.t("imp.item_reviewed"),
                               self.selected in self.session.reviewed,
                               on_change=lambda e, i=self.selected: self._reviewed(
                                   i, e.control.value), data="imp-item-reviewed")]
                  if low else []),
                wording,
                wc.button(ui, ui.t("q.apply"), lambda e: self._wording(wording.value),
                          data="imp-wording-apply"),
            ], title=f"{row.number}. {ui.t('q.editor')}", padding=tk.SPACE_4)]
        return ft.Column([
            wc.card(ui, [picker, *([wc.notice(ui, w, "warning") for w in instrument.warnings[:3]])],
                    padding=tk.SPACE_4),
            *([wc.heading(ui, ui.t("imp.scales"), tk.TYPE_TITLE_S)] + scales if scales else []),
            wc.heading(ui, ui.t("imp.items"), tk.TYPE_TITLE_S),
            ft.Column(items, spacing=tk.SPACE_1, data="imp-items"),
            *detail,
        ], spacing=tk.SPACE_3, data="imp-review")

    def _instrument(self, index: int):
        self.session.select(index)
        self.selected, self.scale_edits = None, {}
        if self.session.instrument is not None:
            self.page_number = self.session.instrument.first_page or 1
        self.app.render()

    def _select(self, index: int):
        self.selected = index
        row = self.session.instrument.questions[index]
        self.page_number = row.page or self.page_number
        self.app.render()

    def _reviewed(self, index: int, value: bool):
        self.session.mark_reviewed(index, bool(value))
        self.app.render()

    def _wording(self, prompt: str):
        try:
            self.session.correct_wording(self.selected, prompt or "")
            self.feedback = (self.app.t("run.done"), "success")
        except Exception as error:
            self.feedback = (str(error), "danger")
        self.app.render()

    def _scale_card(self, scheme) -> ft.Control:
        ui, s = self.app.ui, self.session
        edits = self.scale_edits.setdefault(scheme.id, {
            "labels": list(scheme.labels), "codes": [c or "" for c in scheme.codes]
            if scheme.codes else [""] * scheme.size,
            "reverse": ", ".join(str(n) for n in scheme.reverse_items),
            "structure": scheme.structure_confirmed, "numeric": scheme.codes_confirmed,
            "reverse_ok": scheme.reverse_confirmed,
        })
        linked = s.linked(scheme.id)
        state = ("success" if scheme.structure_confirmed else "warning")
        fields = []
        for k in range(scheme.size):
            fields.append(ft.Row([
                wc.text_field(ui, f"{ui.t('imp.scale_labels')} {k + 1}", edits["labels"][k],
                              width=240, on_change=lambda e, i=k: edits["labels"].__setitem__(
                                  i, e.control.value or ""), data=f"scale-{scheme.id}-label-{k}"),
                wc.text_field(ui, f"{ui.t('imp.scale_codes')} {k + 1}",
                              str(edits["codes"][k] or ""), width=150,
                              on_change=lambda e, i=k: edits["codes"].__setitem__(
                                  i, e.control.value or ""), data=f"scale-{scheme.id}-code-{k}"),
            ], spacing=tk.SPACE_2))
        issues = [wc.caption(ui, "• " + issue) for issue in (*scheme.issues, *scheme.label_problems())]
        return wc.card(ui, [
            ft.Row([wc.chip(ui, ui.t("imp.scale_items", count=len(linked)), state,
                            icon=ft.Icons.LINK),
                    wc.caption(ui, f"{scheme.evidence} · p. {scheme.page}")], wrap=True,
                   spacing=tk.SPACE_2),
            *fields, *issues,
            wc.text_field(ui, "Reverse-keyed items (as documented)", edits["reverse"], width=320,
                          on_change=lambda e: edits.__setitem__("reverse", e.control.value or "")),
            wc.checkbox(ui, ui.t("imp.confirm_structure"), edits["structure"],
                        on_change=lambda e: edits.__setitem__("structure", bool(e.control.value)),
                        data=f"scale-{scheme.id}-structure"),
            wc.checkbox(ui, ui.t("imp.confirm_codes"), edits["numeric"],
                        on_change=lambda e: edits.__setitem__("numeric", bool(e.control.value)),
                        data=f"scale-{scheme.id}-numeric"),
            wc.checkbox(ui, ui.t("imp.confirm_reverse"), edits["reverse_ok"],
                        on_change=lambda e: edits.__setitem__("reverse_ok", bool(e.control.value)),
                        data=f"scale-{scheme.id}-reverse"),
            ft.Row([
                wc.button(ui, ui.t("imp.apply_scale"), lambda e: self._apply_scale(scheme.id),
                          kind="primary", data=f"scale-{scheme.id}-apply"),
                wc.button(ui, ui.t("imp.not_shared"), lambda e: self._not_shared(scheme.id),
                          kind="quiet"),
            ], wrap=True, spacing=tk.SPACE_2),
        ], title=" / ".join(scheme.labels), padding=tk.SPACE_4, data=f"scale-{scheme.id}")

    def apply_scale(self, scheme_id: str, *, structure=True, numeric=False, reverse=False):
        """Programmatic equivalent of the scale card (used by tests)."""
        edits = self.scale_edits.get(scheme_id) or {}
        scheme = next(x for x in self.session.instrument.schemes if x.id == scheme_id)
        labels = edits.get("labels", list(scheme.labels))
        codes = edits.get("codes", list(scheme.codes) if scheme.codes else [""] * scheme.size)
        reverse_items = [int(x) for x in str(edits.get("reverse", ", ".join(
            str(n) for n in scheme.reverse_items))).replace(";", ",").split(",") if x.strip()]
        self.session.review_scale(scheme_id, labels=labels, codes=codes,
                                  reverse_items=reverse_items, structure=structure,
                                  numeric=numeric, reverse=reverse)
        self.scale_edits.pop(scheme_id, None)

    def _apply_scale(self, scheme_id: str):
        edits = self.scale_edits.get(scheme_id, {})
        try:
            self.apply_scale(scheme_id, structure=edits.get("structure", False),
                             numeric=edits.get("numeric", False),
                             reverse=edits.get("reverse_ok", False))
            self.feedback = (self.app.t("run.done"), "success")
        except (ValueError, KeyError) as error:
            self.feedback = (str(error), "danger")
        self.app.render()

    def _not_shared(self, scheme_id: str):
        try:
            self.session.not_shared(scheme_id)
            self.scale_edits.pop(scheme_id, None)
        except (ValueError, KeyError) as error:
            self.feedback = (str(error), "danger")
        self.app.render()

    # ----------------------------------------------------------- preview
    def _preview_pane(self) -> ft.Control:
        ui, s = self.app.ui, self.session
        instrument = s.instrument
        controls: list[ft.Control] = [wc.heading(ui, ui.t("q.preview"), tk.TYPE_TITLE_S)]
        if instrument is not None:
            from scientific_survey_import import proposed_scheme_question

            schemes = {x.id: x for x in instrument.schemes}
            for row in instrument.questions[:40]:
                q = dict(row.question)
                if row.scheme_id in schemes:
                    q = proposed_scheme_question(q, schemes[row.scheme_id])
                controls.append(respondent_question(ui, q, None, lambda k, v: None,
                                                    number=row.number))
        return ft.Container(ft.Column(controls, spacing=tk.SPACE_1), bgcolor=ui.p.surface,
                            border=ft.Border.all(1, ui.p.border), border_radius=ui.radius("card"),
                            padding=tk.SPACE_4, data="imp-preview")

    # --------------------------------------------------------- checklist
    def _checklist(self) -> ft.Control:
        ui, s = self.app.ui, self.session
        if s.instrument is None:
            return ft.Container()
        blockers = s.blockers()
        scales_ok = not any("unverified" in b for b in blockers)
        controls = [
            wc.checkbox(ui, ui.t("imp.check_version"), bool(s.checks.get("version")),
                        on_change=lambda e: self._check("version", e.control.value),
                        data="imp-check-version"),
            wc.checkbox(ui, ui.t("imp.check_items"), bool(s.checks.get("items")),
                        on_change=lambda e: self._check("items", e.control.value),
                        data="imp-check-items"),
            ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE if scales_ok else ft.Icons.PENDING_OUTLINED,
                            color=ui.p.success if scales_ok else ui.p.warning, size=18),
                    wc.text(ui, ui.t("imp.check_scales"))], spacing=tk.SPACE_2),
        ]
        if blockers:
            controls.append(wc.notice(ui, "\n".join("• " + b for b in blockers), "warning",
                                      title=ui.t("imp.blocked", reason="").rstrip(": "),
                                      data="imp-blockers"))
        controls.append(wc.button(ui, ui.t("imp.create_draft"), self._create_draft,
                                  kind="primary", icon=ft.Icons.ARROW_FORWARD,
                                  disabled=bool(blockers), data="imp-create-draft"))
        return wc.card(ui, controls, title=ui.t("imp.checklist"), data="imp-checklist")

    def _check(self, key: str, value: bool):
        self.session.checks[key] = bool(value)
        self.app.render()

    def create_draft(self) -> list[dict]:
        questions = self.session.draft()
        builder = self.app.pages["questionnaires"]
        builder.load_draft(questions, title=self.session.instrument.title,
                           origin=f"{self.session.filename} · {self.session.instrument.title}")
        return questions

    def _create_draft(self, e=None):
        try:
            questions = self.create_draft()
        except ValueError as error:
            self.feedback = (self.app.t("imp.blocked", reason=error), "danger")
            self.app.render()
            return
        self.app.status(self.app.t("imp.draft_created", count=len(questions)), "success")
        self.app.navigate("questionnaires")
