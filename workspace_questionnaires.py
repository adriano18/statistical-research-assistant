"""Questionnaire builder (list / editor / respondent preview) and the
scientific import workspace (source / review / preview).

Storage and validation are the classic ``survey_storage`` functions:
drafts are validated with ``validate_questions`` before publishing, a
published questionnaire is immutable, and responses are written only
through ``submit_response``. The import workspace drives
``import_session.ImportSession`` — the classic importer pipeline — and
keeps each document's review on this computer (``import_review``).
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
from dataclasses import dataclass, field
from pathlib import Path
import shutil

import flet as ft

import workspace_components as wc
import workspace_tokens as tk
from import_review import (
    DEFAULT_OCR, OCR_CHOICES, FormReview, ReviewRecord, ReviewStore, form_fingerprint,
    ocr_language_used, scanned_pages, sessions_folder, source_sha256,
)
from import_session import ImportSession
from workspace_text import count_text

IMPORT_SUFFIXES = (".pdf", ".docx", ".doc")


def pages_text(language: str, pages) -> str:
    """"page 2" / "pages 2, 3 and 5" in the interface language."""
    numbers = [str(p) for p in sorted(set(pages))]
    if not numbers:
        return ""
    if language == "lv":
        if len(numbers) == 1:
            return f"{numbers[0]}. lappuse"
        return ", ".join(n + "." for n in numbers[:-1]) + f" un {numbers[-1]}. lappuse"
    if language == "ru":
        if len(numbers) == 1:
            return f"страница {numbers[0]}"
        return f"страницы {', '.join(numbers[:-1])} и {numbers[-1]}"
    if len(numbers) == 1:
        return f"page {numbers[0]}"
    return f"pages {', '.join(numbers[:-1])} and {numbers[-1]}"

KINDS = ("single_choice", "multiple_choice", "likert5", "likert7", "rating_scale",
         "yes_no", "number", "short_text", "long_text", "date", "consent")
CHOICE_KINDS = {"single_choice", "multiple_choice"}
SCALE_KINDS = {"likert5", "likert7", "rating_scale"}
CONDITION_PARENTS = {"single_choice", "yes_no", "likert5", "likert7", "rating_scale", "number"}
OPERATORS = ("equals", "not_equals", "greater", "less")     # labels: q.operator.*
TEMPLATES = ("psychology", "demographics", "hr", "marketing")  # labels: q.template.*


def scale_library(language: str, draft: list[dict]) -> list[tuple[str, str, dict]]:
    """(id, label, {"kind", "value_labels"}) — presets plus scales in the draft."""
    from survey_ui import preset_value_labels, semantic_differential_labels
    from workspace_text import t

    library = []
    for name in ("agreement", "frequency", "quality"):
        for kind in ("likert5", "likert7"):
            try:
                labels = preset_value_labels(name, kind, language)
            except (KeyError, ValueError):
                continue
            library.append((f"{name}-{kind}", t(language, "q.scale.points",
                                                scale=t(language, f"q.scale.{name}"),
                                                count=kind[-1]),
                            {"kind": kind, "value_labels": labels}))
    library.append(("semantic", t(language, "q.scale.semantic"),
                    {"kind": "rating_scale", "value_labels": semantic_differential_labels(language)}))
    seen = set()
    for q in draft:
        labels = q.get("value_labels") or {}
        if q.get("kind") in SCALE_KINDS and labels:
            signature = tuple(labels.items())
            if signature not in seen and len(library) < 40:
                seen.add(signature)
                shown = " / ".join(list(labels.values())[:3]) + ("…" if len(labels) > 3 else "")
                library.append((f"draft-{len(seen)}", t(language, "q.scale.from_draft",
                                                        labels=shown),
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
                      icon=ft.Icons.PUBLISH, disabled=not self.draft,
                      tooltip=None if self.draft else ui.t("disabled.no_questions"),
                      data="q-publish"),
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
        body = [header, *self._resume_notice(),
                meta, ft.Row(status, spacing=tk.SPACE_2, wrap=True), panes]
        if self.feedback:
            body.append(wc.notice(ui, self.feedback[0], self.feedback[1], data="q-feedback"))
        body.append(self._published())
        return app.constrained(ft.Column(body, spacing=tk.SPACE_4,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.CONTENT_MAX_WIDTH + 280)

    def _resume_notice(self) -> list[ft.Control]:
        """An unfinished import review (kept on this computer) can be
        continued from here, where imports start, also after a restart."""
        importer = self.app.pages.get("import")
        offers = importer.resume_offers(include_open=True) if importer is not None else []
        if not offers:
            return []
        ui = self.app.ui
        actions = [wc.button(ui, importer.resume_label(record),
                             wc.handler(importer.resume_review, record.sha256),
                             kind="primary" if number == 0 else "secondary",
                             icon=ft.Icons.HISTORY, tooltip=record.path,
                             data=f"q-resume-{number}")
                   for number, record in enumerate(offers[:3])]
        return [wc.notice(ui, ui.t("imp.resume_note"), "info", title=ui.t("imp.resume_title"),
                          actions=actions, data="q-resume")]

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
        templates = wc.dropdown(ui, ui.t("q.template"),
                                [(k, ui.t(f"q.template.{k}")) for k in TEMPLATES],
                                self.template,
                                on_select=lambda e: setattr(self, "template", e.control.value),
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

        questions = copy.deepcopy(_template_questions(self.template))

        def replace():
            self.load_draft(questions)
            self.feedback = None
            self.app.render()

        self.confirm_replace(self.template, len(questions), replace)

    def confirm_replace(self, incoming: str, count: int, replace) -> None:
        """Run ``replace`` at once when the builder is empty; otherwise ask
        first, so an unsaved draft is never silently replaced or mixed with
        imported questions."""
        if not self.draft:
            replace()
            return
        app, ui = self.app, self.app.ui

        def confirm(e=None):
            app.page.pop_dialog()
            replace()

        app.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=wc.heading(ui, ui.t("q.replace_title"), tk.TYPE_TITLE_S),
            content=ft.Container(wc.text(ui, ui.t(
                "q.replace_body", current=self.title.strip() or ui.t("q.untitled"),
                current_count=len(self.draft), incoming=incoming, count=count), tk.TYPE_BODY),
                width=500),
            actions=[wc.button(ui, ui.t("common.cancel"), lambda e: app.page.pop_dialog(),
                               kind="quiet", data="q-replace-cancel"),
                     wc.button(ui, ui.t("q.replace_confirm"), confirm, kind="primary",
                               data="q-replace-confirm")],
        ))

    def load_draft(self, questions: list[dict], *, title: str = "", origin: str = ""):
        """Start a new draft from ``questions`` (an import or a template).

        The previous draft, its title and instructions are replaced as a
        whole: questions of two questionnaires are never mixed."""
        self.draft = copy.deepcopy(questions)
        self.selected = 0 if questions else None
        self.title = title
        self.description = ""
        self.origin = origin
        self.preview_answers = {}
        self.editor_error = ""

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
                wc.dropdown(ui, ui.t("q.condition_operator"),
                            [(k, ui.t(f"q.operator.{k}")) for k in OPERATORS],
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
        # Published while a project is open: the form belongs to that project.
        try:
            self.app.projects.link_questionnaire(survey.survey_id, survey.title, "published")
        except Exception:
            pass   # the questionnaire itself is saved; linking is a convenience
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
        linked = self.app.projects.questionnaire_ids()
        if self.app.projects.active:
            # This project's questionnaires first, the others under their own label.
            surveys.sort(key=lambda s: s.survey_id not in linked)
        rows = []
        label_other = self.app.projects.active
        for index, survey in enumerate(surveys[:12]):
            if self.app.projects.active and index == 0 and survey.survey_id in linked:
                rows.append(wc.section_label(ui, ui.t("q.in_project")))
            if label_other and survey.survey_id not in linked:
                rows.append(wc.section_label(ui, ui.t("q.other_surveys")))
                label_other = False
            count = response_count(self.app.survey_root, survey.survey_id)
            rows.append(ft.Row([
                ft.Icon(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, size=18, color=ui.p.text_secondary),
                ft.Column([wc.text(ui, survey.title, tk.TYPE_BODY, weight=ft.FontWeight.W_600),
                           wc.caption(ui, f"{count_text(ui.language, len(survey.questions), 'questions')}"
                                          f" · {ui.t('q.collected', count=count)}")],
                          spacing=2, expand=True),
                wc.button(ui, ui.t("q.collect"), lambda e, s=survey: self._collect(s),
                          kind="quiet", icon=ft.Icons.EDIT_NOTE, data=f"collect-{survey.survey_id}"),
                wc.button(ui, ui.t("q.export_responses"), wc.handler(self._export, survey),
                          kind="quiet", icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
                          disabled=count == 0, data=f"export-responses-{survey.survey_id}"),
                wc.button(ui, ui.t("q.analyze_responses"), lambda e, s=survey: self._analyze(s),
                          icon=ft.Icons.QUERY_STATS, disabled=count == 0,
                          tooltip=None if count else ui.t("q.no_responses_yet"),
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
                wc.set_text(message, str(error))
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

        app = self.app

        def codebook(csv_path: Path) -> Path:
            return csv_path.with_name(csv_path.stem + "_codebook.json")

        def write(csv_path: Path) -> Path:
            written = save_survey_csv(app.survey_root, survey.survey_id, csv_path)
            save_survey_codebook(app.survey_root, survey.survey_id, codebook(written),
                                 data_file=written)
            return written

        outcome = await app.save_file(
            app.t("q.export_responses"), f"{survey.survey_id}_responses.csv", "csv", write,
            announce=lambda path: app.t("q.exported", path=path, codebook=codebook(path).name))
        self.feedback = (outcome.message, outcome.tone)
        app.render()

    def _analyze(self, survey):
        """Analyze collected responses as their own, explicitly named dataset.

        The dataset in use is never replaced without asking: in a project it
        stays among the project's data sources; without one, the researcher
        is told that it will be closed."""
        from survey_storage import responses_dataframe

        app, s = self.app, self.app.session
        try:
            df = responses_dataframe(app.survey_root, survey.survey_id)
        except (OSError, ValueError) as error:
            self.feedback = (app.t("data.load_failed", error=error), "danger")
            app.render()
            return
        name = app.t("responses.name", title=survey.title)
        same = s.dataset_origin == "survey" and s.dataset_survey_id == survey.survey_id
        if not s.has_data or same:
            self._use_responses(survey, df, name)
            return
        ui = app.ui

        def use(e=None):
            app.page.pop_dialog()
            self._use_responses(survey, df, name)

        body = ui.t("responses.body_project" if app.projects.active else "responses.body_alone",
                    name=name, current=s.source_name, count=len(df))
        app.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=wc.heading(ui, ui.t("responses.title", title=survey.title), tk.TYPE_TITLE_S),
            content=ft.Container(wc.text(ui, body, tk.TYPE_BODY), width=500),
            actions=[wc.button(ui, ui.t("common.cancel"), lambda e: app.page.pop_dialog(),
                               kind="quiet", data="responses-cancel"),
                     wc.button(ui, ui.t("responses.use"), use, kind="primary",
                               icon=ft.Icons.QUERY_STATS, data="responses-use")],
        ))

    def _use_responses(self, survey, df, name: str):
        app = self.app
        app.session.set_dataset(df, name, origin="survey", survey_id=survey.survey_id)
        app.pages["analyze"].reset()
        app.status(app.t("responses.loaded", name=name, count=len(df)), "success")
        app.navigate("data")


# ================================================================== import
def ocr_language_options(language: str, installed=None) -> list[tuple[str, str]]:
    """(code, label) of the OCR languages offered, e.g. ("lav", "Latvian");
    only those whose language data is installed, when that is known."""
    from workspace_text import t

    options = []
    for code in OCR_CHOICES:
        parts = code.split("+")
        if installed and not all(part in installed for part in parts):
            continue
        options.append((code, " + ".join(t(language, f"imp.ocr_lang.{part}") for part in parts)))
    return options


def ocr_language_name(language: str, code: str | None) -> str:
    """"Latvian + English" for "lav+eng", inside a sentence of the interface
    language (Latvian and Russian write language names in lower case)."""
    from workspace_text import T, t

    names = [t(language, f"imp.ocr_lang.{part}") if f"imp.ocr_lang.{part}" in T else part
             for part in str(code or "").split("+") if part]
    if language in ("lv", "ru"):
        names = [name[:1].lower() + name[1:] for name in names]
    return " + ".join(names)


def evidence_text(language: str, evidence: str) -> str:
    """Where a form documents its answer options ("instruction before the
    table"); the engine's evidence kinds may be joined ("header+matrix")."""
    from workspace_text import T, t

    return " + ".join(t(language, f"imp.evidence.{part}") if f"imp.evidence.{part}" in T
                      else part for part in str(evidence or "").split("+") if part)


@dataclass
class FormProgress:
    """The researcher's review of one form while the document is open:
    items compared with the source, the three confirmations, and the
    wording and scale reviews in the order they were applied."""

    reviewed: set = field(default_factory=set)
    checks: dict = field(default_factory=dict)
    actions: list = field(default_factory=list)


class ImportPage:
    """The review wizard: source and version → shared response scale →
    items → confirm and create (spec §10, Stage 36.5 UI)."""

    STEPS = ("source", "scale", "items", "confirm")
    # A long list is shown a page of rows at a time (spec §10: 200+ items).
    PAGE_SIZE = 100
    PAGE_LIMIT = 150

    def __init__(self, app):
        self.app = app
        self.session = ImportSession()
        self.original = None        # the review as read: "discard" returns to it
        self.page_number = 1
        self.selected: int | None = None
        self.busy = False
        self.reading = "text"       # what the reader does while busy: "text" or "ocr"
        self.reading_name = ""
        self.reading_language: str | None = None
        self.error: str | None = None   # why the last document could not be read
        self.scale_edits: dict = {}
        self.scale_errors: dict = {}
        self._page_cache: dict = {}
        self.zoom = "fit"           # enlarged page view: fit, 150 or 200 (%)
        # Review wizard (Issue #31): source → shared scale → items → confirm.
        self.step = "source"
        self.filter = "all"         # items step: "all" or "attention"
        self.progress: str | None = None   # what the reading is doing now
        self.progress_done: tuple[int, int] | None = None  # OCR pages read, of how many
        self._cancel = None         # threading.Event while reading
        self.opened: set[str] = set()
        self._editor_height = 0.0   # the open item editor, as laid out
        # Stage 36.5 UI: the form under review is the researcher's choice.
        self.chosen: int | None = None
        self.forms_progress: dict[int, FormProgress] = {}
        self.fingerprints: dict[int, str] = {}
        self.list_page = 0
        self.sha: str | None = None
        self.source_path: str | None = None
        self.ocr_language: str | None = None     # the OCR language of the reading
        self.ocr_manual: tuple[int, ...] = ()     # pages read with "OCR this page"
        self.ocr_choice: str | None = None        # the language chosen for the next OCR
        self.scan: tuple[int, ...] = ()           # scanned pages waiting for OCR
        self.restored: tuple[int, int] | None = None
        self.restore_partial = False
        self._typed: dict[int, str] = {}          # wording typed, not applied yet
        self._ocr_runtime: tuple[bool, tuple[str, ...]] | None = None
        self._profile = None                # ocr_profile.Profile while reading
        self.last_profile: dict | None = None
        self.store = ReviewStore(sessions_folder(app.survey_root))

    # ----------------------------------------------------------- reading
    async def open_files(self, files):
        picked = files[0]
        name = str(getattr(picked, "name", "") or Path(getattr(picked, "path", "") or "").name)
        path = getattr(picked, "path", None) or None
        try:
            if path:
                binary = await asyncio.to_thread(Path(path).read_bytes)
            else:
                binary = getattr(picked, "bytes", None)
            await self.open_bytes(binary, name, path=path)
        except Exception as error:
            self._fail(self.app.t("imp.read_failed", name=name, error=error))

    def unreadable(self, name: str) -> str | None:
        """Why this document cannot be read here, with what to do instead
        (checked before anything is replaced)."""
        suffix = Path(name).suffix.lower()
        if suffix not in IMPORT_SUFFIXES:
            return self.app.t("imp.unsupported", name=name)
        if suffix == ".doc" and shutil.which("antiword") is None:
            return self.app.t("imp.doc_unavailable", name=name)
        return None

    async def open_bytes(self, binary: bytes, name: str, *, path: str | None = None,
                         language: str | None = None):
        """Read a document in a worker thread, with progress and Cancel.

        It is read into a fresh session: a document that cannot be read
        leaves the one under review as it was. The same bytes reviewed
        before (the same SHA-256) come back with that review. A PDF without
        any text layer is not read before the researcher has chosen the
        OCR language; ``language`` reads it (or any PDF's image pages) with
        local OCR in that language."""
        import threading

        import ocr_profile

        problem = self.unreadable(name)
        if problem:
            # Nothing is opened, and a document already under review stays.
            self._fail(problem)
            return
        if not isinstance(binary, bytes) or not binary:
            self._fail(self.app.t("imp.read_failed", name=name,
                                  error=self.app.t("common.not_available")))
            return
        # Where this reading's time goes (Stage 36.8): ocr_profile.
        profile = ocr_profile.Profile(f"{name} · {language or 'text'}")
        with profile.stage("source_open"):
            sha = source_sha256(binary)
            record = self.store.load(sha)
        chosen_language = language
        if language is None and record is not None:
            language = record.ocr_language
        if language is None and record is None and Path(name).suffix.lower() == ".pdf":
            pages = await asyncio.to_thread(scanned_pages, binary)
            if pages:
                await self._offer_scan(binary, name, sha, path, pages)
                return
        loop = asyncio.get_running_loop()
        self._cancel = threading.Event()
        self.busy, self.error, self.progress = True, None, None
        self.progress_done = None
        self.reading = "ocr" if language else "text"
        self.reading_name, self.reading_language = name, language
        self._profile = profile
        with profile.stage("ui_update"):
            self.app.render()
        profile.renders += 1

        def progress(message: str):
            loop.call_soon_threadsafe(self._show_progress, message)

        fresh = ImportSession()
        manual = record.ocr_pages if record is not None and language else ()
        restored = remember = False
        first_page = None
        stop = asyncio.Event()
        watcher = asyncio.create_task(ocr_profile.watch_event_loop(profile, stop))
        try:
            with ocr_profile.activate(profile):
                await asyncio.to_thread(fresh.open, binary, name, progress=progress,
                                        cancel=self._cancel, language=language)
                if manual:
                    await asyncio.to_thread(fresh.ocr_pages, list(manual), language,
                                            cancel=self._cancel)
                # The page shown first is drawn here, in the worker: drawn
                # while rendering, it held the window (the event loop) still.
                number = (fresh.instrument.first_page if fresh.instrument is not None else 1) or 1
                with contextlib.suppress(Exception):
                    with profile.stage("page_rendering"):
                        first_page = (number, await asyncio.to_thread(fresh.render_page, number))
        except Exception as error:
            self.error = self.app.t("imp.read_failed", name=name, error=error)
        else:
            with profile.stage("review_model"):
                self._adopt(fresh, sha=sha, path=path, language=language, manual=manual)
                if first_page is not None and first_page[0] == self.page_number:
                    self._page_cache[(self.page_number, 0)] = first_page[1]
                if record is not None:
                    restored = self._restore(record)
            # The OCR language the researcher chose is part of the review.
            remember = bool(chosen_language) and not restored
        finally:
            self.busy, self.progress, self._cancel = False, None, None
            stop.set()
            with contextlib.suppress(Exception):
                await watcher
        if remember:
            with profile.stage("review_model"):
                self._autosave()
        self._announce()
        with profile.stage("ui_update"):
            self.app.render()
        profile.renders += 1
        if restored and self.step == "items" and self.selected is not None:
            self._reveal(self.selected)
        profile.facts.update({
            "language": language, "pages": self.session.page_count,
            "ocr_pages": list(self.session.ocr_pages_used),
            "items": sum(len(x.questions) for x in self.session.instruments),
            "forms": len(self.session.instruments), "error": bool(self.error)})
        self.last_profile = profile.result()
        self._profile = None
        profile.write()

    async def _offer_scan(self, binary: bytes, name: str, sha: str, path, pages):
        """A PDF without any text layer: show it and offer local OCR in the
        language the researcher chooses (nothing is read before)."""
        from visual_survey_review import pdf_page_count

        try:
            count = await asyncio.to_thread(pdf_page_count, binary)
        except Exception as error:
            self._fail(self.app.t("imp.read_failed", name=name, error=error))
            return
        preview = ImportSession(filename=name, source=binary, page_count=count,
                                image_pages=tuple(pages))
        self._adopt(preview, sha=sha, path=path, language=None)
        self.scan = tuple(pages)
        self.page_number = pages[0]
        self._ocr_runtime = await asyncio.to_thread(self._probe_ocr)
        self.app.status(self.app.t("imp.scan_status", name=name), "info")
        self.app.render()

    @staticmethod
    def _probe_ocr() -> tuple[bool, tuple[str, ...]]:
        """Whether local OCR runs here, and its installed languages."""
        try:
            from visual_survey_review import tesseract_available

            if not tesseract_available():
                return False, ()
            from ocr_runtime import ocr_readiness

            return True, tuple(ocr_readiness().languages)
        except Exception:
            return False, ()

    def _adopt(self, session: ImportSession, *, sha: str | None, path, language,
               manual=()) -> None:
        """Take a fresh reading: its review starts from what was read."""
        self.session = session
        self.original = session.review
        self.sha, self.source_path = sha, path
        self.ocr_language = ((language or ocr_language_used(session.review))
                             if session.ocr_pages_used else None)
        self.ocr_manual = tuple(manual)
        self.fingerprints = {i: form_fingerprint(x) for i, x in enumerate(session.instruments)}
        # One form is the form; between two or more the researcher chooses.
        self.chosen = 0 if len(session.instruments) == 1 else None
        self.forms_progress = {}
        self.step, self.filter, self.selected, self.list_page = "source", "all", None, 0
        self.page_number, self.scale_edits, self.scale_errors = 1, {}, {}
        self._page_cache, self._typed = {}, {}
        self.scan, self.restored, self.restore_partial, self.error = (), None, False, None
        if session.instrument is not None:
            self.page_number = session.instrument.first_page or 1

    def _fail(self, message: str) -> None:
        """A document could not be read: say why; whatever was under review stays."""
        self.error = message
        self.app.status(message, "danger")
        self.app.render()

    def _announce(self) -> None:
        """The outcome of a reading in the application's status line."""
        t, s = self.app.t, self.session
        if self.error:
            self.app.status(self.error, "danger")
        elif s.instruments:
            self.app.status(t("imp.read_ok", instruments=len(s.instruments),
                              items=sum(len(i.questions) for i in s.instruments),
                              name=s.filename), "success")
        elif self._unread_pages()[0]:
            self.app.status(t("imp.scan_status", name=s.filename), "warning")
        else:
            self.app.status(t("imp.none_found", name=s.filename), "warning")

    def _show_progress(self, message: str):
        """A progress message of the reader, in the interface language."""
        import re

        match = re.search(r"page (\d+) with local OCR \((\d+) of (\d+)\)", message)
        if match:
            self.reading = "ocr"
            self.progress_done = (int(match[2]) - 1, int(match[3]))
        self.progress = (self.app.t("imp.ocr_progress", page=match[1], done=match[2],
                                    total=match[3]) if match else message)
        if self.busy:
            profile = getattr(self, "_profile", None)
            if profile is None:
                self.app.render()
                return
            with profile.stage("ui_update"):
                self.app.render()
            profile.renders += 1

    def cancel_reading(self, e=None):
        if self._cancel is not None:
            self._cancel.set()
            self.progress = self.app.t("imp.cancelling")
            self.app.render()

    # ------------------------------------------------- autosave and resume
    def _progress(self) -> FormProgress | None:
        if self.chosen is None:
            return None
        return self.forms_progress.setdefault(self.chosen, FormProgress())

    def _stash_form(self) -> None:
        """Keep the form's own review while another form is looked at."""
        progress = self._progress()
        if progress is not None:
            progress.reviewed = set(self.session.reviewed)
            progress.checks = dict(self.session.checks)

    def _log(self, action: dict) -> None:
        progress = self._progress()
        if progress is not None:
            progress.actions.append(action)

    def _has_progress(self) -> bool:
        self._stash_form()
        return any(p.reviewed or p.actions or any(p.checks.values())
                   for p in self.forms_progress.values())

    def review_record(self) -> ReviewRecord:
        """The review of the open document, as it is kept on disk."""
        self._stash_form()
        s = self.session
        forms = {}
        for index, progress in sorted(self.forms_progress.items()):
            if index >= len(s.instruments):
                continue
            form = s.instruments[index]
            forms[index] = FormReview(
                self.fingerprints.get(index, ""), form.title, len(form.questions),
                tuple(sorted(progress.reviewed)),
                {key: True for key, value in progress.checks.items() if value is True},
                tuple(progress.actions))
        return ReviewRecord(self.sha or "", s.filename, self.source_path, self.ocr_language,
                            tuple(self.ocr_manual),
                            self.chosen if self.chosen in forms else None, self.step,
                            self.selected, forms)

    def _autosave(self) -> None:
        """Keep the review on this computer after every change."""
        if self.sha and self.session.instruments and not self.busy:
            self.store.save(self.review_record())

    def _changed(self, *, render: bool = True) -> None:
        """The researcher changed something: save it, show it."""
        self.error, self.restored = None, None
        self._autosave()
        if render:
            self.app.render()

    def _restore(self, record: ReviewRecord) -> bool:
        """Replay the researcher's own review of the same bytes. A form whose
        reading differs from the one reviewed is left as read."""
        s = self.session
        restored = []
        for index, form in sorted(record.forms.items()):
            if (index >= len(s.instruments) or form.fingerprint != self.fingerprints.get(index)
                    or form.count != len(s.instruments[index].questions)
                    or not self._replay(index, form.actions)):
                self.restore_partial = True
                continue
            self.forms_progress[index] = FormProgress(set(form.reviewed), dict(form.checks),
                                                      list(form.actions))
            restored.append(index)
        if record.chosen not in restored:
            return False
        from import_session import fresh_checks

        self.chosen = record.chosen
        s.instrument_index = record.chosen
        progress = self.forms_progress[record.chosen]
        s.reviewed, s.checks = set(progress.reviewed), {**fresh_checks(), **progress.checks}
        count = len(s.instrument.questions)
        if record.selected is not None and 0 <= record.selected < count:
            self.selected = record.selected
            self.page_number = s.instrument.questions[record.selected].page or self.page_number
        self.step = record.step
        self.list_page = self._page_of(self.selected) if self.selected is not None else 0
        self.restored = (len(s.reviewed), count)
        return True

    def _replay(self, index: int, actions) -> bool:
        """Apply recorded actions to form ``index``; all or nothing."""
        s = self.session
        keep, before = s.instrument_index, s.review
        s.instrument_index = index
        try:
            for action in actions:
                if action["do"] == "wording":
                    s.correct_wording(action["index"], action["prompt"])
                elif action["do"] == "scale":
                    s.review_scale(action["scheme"], labels=action["labels"],
                                   codes=action["codes"], reverse_items=action["reverse_items"],
                                   structure=action["structure"], numeric=action["numeric"],
                                   reverse=action["reverse"])
                elif action["do"] == "not_shared":
                    s.not_shared(action["scheme"])
            return True
        except Exception:
            s.review = before
            return False
        finally:
            s.instrument_index = keep

    def resume_offers(self, *, include_open: bool = False) -> list[ReviewRecord]:
        """Unfinished reviews whose document is still at its path, unchanged
        (the most recent first)."""
        try:
            records = self.store.resumable()
        except Exception:
            return []
        return [r for r in records if include_open or r.sha256 != self.sha]

    def resume_label(self, record: ReviewRecord) -> str:
        if record.chosen is None:
            return self.app.t("imp.resume_no_form", file=record.filename)
        return self.app.t("imp.resume", file=record.filename, checked=record.checked,
                          total=record.total)

    async def resume_review(self, sha: str):
        """Open a saved review again: its document from its path, then the
        researcher's review of it, at the item last selected."""
        if sha == self.sha and self.session.source is not None:
            self.app.navigate("import")
            return
        record = self.store.load(sha)
        if record is None or not record.path:
            return
        self.app.navigate("import")
        try:
            binary = await asyncio.to_thread(Path(record.path).read_bytes)
        except OSError:
            self._fail(self.app.t("imp.resume_missing", file=record.filename))
            return
        await self.open_bytes(binary, record.filename, path=record.path)
        if source_sha256(binary) != sha:
            self.app.status(self.app.t("imp.resume_changed", file=record.filename), "warning")

    def _confirm(self, title: str, body: str, label: str, action, *, data: str) -> None:
        """Ask before something is discarded; ``action`` may be a coroutine function."""
        import inspect

        ui = self.app.ui

        def cancel(e=None):
            self.app.page.pop_dialog()

        async def go(e=None):
            self.app.page.pop_dialog()
            result = action()
            if inspect.iscoroutine(result):
                await result

        self.app.page.show_dialog(ft.AlertDialog(
            modal=True, title=wc.heading(ui, title, tk.TYPE_TITLE_S),
            content=ft.Container(wc.text(ui, body, tk.TYPE_BODY), width=520),
            actions=[wc.button(ui, ui.t("common.cancel"), cancel, kind="quiet",
                               data=f"{data}-cancel"),
                     wc.button(ui, label, go, kind="primary", data=f"{data}-confirm")]))

    def _ask_discard(self, e=None):
        name = self.session.filename
        self._confirm(self.app.t("imp.discard_title", file=name), self.app.t("imp.discard_body"),
                      self.app.t("imp.discard_confirm"), self._discard, data="imp-discard")

    def _discard(self):
        """Discard the review of the open document: back to the reading as
        it came, nothing confirmed, the saved session removed."""
        from import_session import fresh_checks

        if self.sha:
            self.store.remove(self.sha)
        s = self.session
        if self.original is not None:
            s.review = self.original
        s.instrument_index, s.checks, s.reviewed = 0, fresh_checks(), set()
        self.chosen = 0 if len(s.instruments) == 1 else None
        self.forms_progress = {}
        self.step, self.filter, self.selected, self.list_page = "source", "all", None, 0
        self.scale_edits, self.scale_errors, self._typed = {}, {}, {}
        self.restored, self.restore_partial = None, False
        self.app.status(self.app.t("imp.discarded", file=s.filename), "info")
        self.app.render()

    def _ask_discard_saved(self, sha: str, name: str):
        self._confirm(self.app.t("imp.discard_title", file=name), self.app.t("imp.discard_body"),
                      self.app.t("imp.discard_confirm"),
                      lambda: self._discard_saved(sha, name), data="imp-discard")

    def _discard_saved(self, sha: str, name: str):
        if sha == self.sha:
            self._discard()
            return
        self.store.remove(sha)
        self.app.status(self.app.t("imp.discarded", file=name), "info")
        self.app.render()

    def _resume_cards(self) -> list[ft.Control]:
        """Unfinished reviews on the empty import page (after a restart)."""
        ui = self.app.ui
        offers = self.resume_offers()
        if not offers:
            return []
        rows: list[ft.Control] = []
        for number, record in enumerate(offers[:8]):
            rows.append(ft.Row([
                wc.button(ui, self.resume_label(record), wc.handler(self.resume_review,
                                                                     record.sha256),
                          kind="primary" if number == 0 else "secondary", icon=ft.Icons.HISTORY,
                          tooltip=record.path, data=f"imp-resume-{number}"),
                wc.button(ui, ui.t("imp.resume_discard"),
                          wc.handler(self._ask_discard_saved, record.sha256, record.filename),
                          kind="quiet", icon=ft.Icons.DELETE_OUTLINE,
                          data=f"imp-resume-discard-{number}"),
            ], wrap=True, spacing=tk.SPACE_2))
        rows.append(wc.caption(ui, ui.t("imp.resume_note")))
        return [wc.card(ui, rows, title=ui.t("imp.resume_title"), padding=tk.SPACE_4,
                        data="imp-resume")]

    # ------------------------------------------------------------- build
    def build(self) -> ft.Control:
        app, ui = self.app, self.app.ui
        header = wc.page_header(ui, ui.t("imp.title"), ui.t("imp.subtitle"), actions=[
            wc.button(ui, ui.t("imp.choose"), action=app.open_document_action, kind="primary",
                      icon=ft.Icons.UPLOAD_FILE, disabled=self.busy, data="imp-choose"),
            wc.button(ui, ui.t("nav.questionnaires"), lambda e: app.navigate("questionnaires"),
                      kind="quiet", icon=ft.Icons.ARROW_BACK),
        ])
        body: list[ft.Control] = [header]
        status = self._status_line()
        if status is not None:
            body.append(status)
        if self.session.source is None:
            if not self.busy:
                body += self._resume_cards()
                body.append(wc.empty_state(ui, ft.Icons.DOCUMENT_SCANNER_OUTLINED,
                                           ui.t("imp.empty.title"), ui.t("imp.empty.body"),
                                           actions=[wc.button(ui, ui.t("imp.choose"),
                                                              action=app.open_document_action,
                                                              kind="primary")],
                                           data="imp-empty"))
            return app.constrained(ft.Column(body, spacing=tk.SPACE_4))
        steps = {"source": self._step_source, "scale": self._step_scale,
                 "items": self._step_items, "confirm": self._step_confirm}
        if self._locked(self.step):
            self.step = "source"
        content = steps[self.step]()
        source = self._source_pane()
        if app.content_width >= 1100:
            panes = ft.Row([ft.Container(source, width=int(app.content_width * 0.38)),
                            ft.Container(content, expand=True)],
                           vertical_alignment=ft.CrossAxisAlignment.START, spacing=tk.SPACE_4)
        else:
            panes = ft.Column([content, source], spacing=tk.SPACE_4)
        if self.session.instrument is not None:
            body.append(self._stepper())
        body.append(panes)
        return app.constrained(ft.Column(body, spacing=tk.SPACE_4,
                                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                               tk.CONTENT_MAX_WIDTH + 400)

    # ------------------------------------------------- processing status
    def _unread_pages(self) -> tuple[list[int], str | None]:
        """Image pages whose questions are not read, and why: None (the
        researcher has not chosen the OCR language yet) or the fact key."""
        if self.scan:
            return list(self.scan), None
        if self.session.instrument is not None:
            return [], None
        for key, values in self.session.facts:
            if key in ("ocr_cancelled", "ocr_unavailable", "ocr_failed", "ocr_nothing"):
                return list(values.get("pages") or ()), key
        return [], None

    def processing_state(self) -> tuple[str, str, list, str, list] | None:
        """The ONE status of the import: (state, title, [(data, line)], tone,
        actions). States: loaded, recognizing, scan, found, review, ready,
        error (spec §10 "Ошибки"); None while no document is open."""
        app, ui, s = self.app, self.app.ui, self.session
        t = ui.t
        if self.busy:
            cancel = [wc.button(ui, t("imp.cancel_ocr"), self.cancel_reading, kind="quiet",
                                icon=ft.Icons.CANCEL_OUTLINED, data="imp-cancel")]
            if self.reading == "ocr":
                line = self.progress or t("imp.ocr_starting", ocr=ocr_language_name(
                    ui.language, self.reading_language) or "…")
                return ("recognizing", t("imp.state.recognizing"), [("imp-progress", line)],
                        "info", cancel)
            line = self.progress or t("imp.reading_name", name=self.reading_name)
            return "loaded", t("imp.state.loaded"), [("imp-progress", line)], "info", cancel
        choose_other = wc.button(ui, t("imp.choose_other"), action=app.open_document_action,
                                 kind="secondary", icon=ft.Icons.UPLOAD_FILE,
                                 data="imp-choose-other")
        if self.error:
            lines = [("imp-status-detail", self.error)]
            if s.instruments:
                total = sum(len(x.questions) for x in s.instruments)
                lines.append(("imp-status-kept", t("imp.state.kept", name=s.filename,
                                                   total=total)))
            return "error", t("imp.state.error"), lines, "danger", [choose_other]
        if s.source is None:
            return None
        if s.instrument is None:
            pages, reason = self._unread_pages()
            if not pages:
                return ("error", t("imp.state.none"),
                        [("imp-status-detail", t("imp.none_found", name=s.filename)),
                         ("imp-status-next", t("imp.next.none"))], "warning", [choose_other])
            where = pages_text(ui.language, pages)
            where = where[:1].upper() + where[1:]
            available = (self._ocr_runtime or (True, ()))[0] and reason != "ocr_unavailable"
            if reason == "ocr_failed":
                detail = next((v.get("detail", "") for k, v in s.facts if k == reason), "")
                line = t("imp.scan.failed", pages=where, detail=detail)
            elif reason in ("ocr_cancelled", "ocr_nothing"):
                line = t(f"imp.scan.{reason[4:]}", pages=where)
            elif not available:
                line = t("imp.scan.unavailable", pages=where)
            else:
                line = t("imp.scan.detail", pages=where)
            if available:
                actions = [self._ocr_dropdown(),
                           wc.button(ui, t("imp.ocr_run"), self._read_with_ocr, kind="primary",
                                     icon=ft.Icons.DOCUMENT_SCANNER_OUTLINED, data="imp-ocr-run")]
            else:
                actions = [wc.button(ui, t("nav.settings"), lambda e: app.navigate("settings"),
                                     kind="secondary", icon=ft.Icons.SETTINGS_OUTLINED,
                                     data="imp-open-settings"), choose_other]
            return ("scan", t("imp.state.scan"), [("imp-status-detail", line)],
                    "info" if available else "warning", actions)
        lines: list[tuple[str, str]] = []
        if self.chosen is None:
            sizes = ", ".join(str(len(x.questions)) for x in s.instruments)
            lines += [("imp-status-detail", t("imp.state.found_detail", items=sum(
                len(x.questions) for x in s.instruments), forms=len(s.instruments), sizes=sizes)),
                      ("imp-status-next", t("imp.state.choose"))]
            state, title, tone = "found", t("imp.state.found"), "info"
        else:
            status, keys = self._status(), self._blockers()
            form = s.instrument.title
            if keys:
                lines += [("imp-status-detail", t("imp.state.review_detail", form=form,
                                                  total=status["total"],
                                                  attention=status["attention"],
                                                  checked=status["checked"])),
                          ("imp-status-next", t("imp.state.next", step=self.blocker_text(*keys[0])))]
                state, title, tone = "review", t("imp.state.review"), "warning"
            else:
                lines.append(("imp-status-detail", t("imp.state.ready_detail", form=form,
                                                     total=status["total"])))
                state, title, tone = "ready", t("imp.state.ready"), "success"
        if s.ocr_pages_used:
            # A successful OCR stays visible as a fact (with its language).
            lines.append(("imp-status-ocr", t(
                "imp.state.ocr_used", pages=pages_text(ui.language, s.ocr_pages_used),
                ocr=ocr_language_name(ui.language, self.ocr_language) or "—")))
        if self.restored:
            lines.append(("imp-status-restored", t("imp.state.restored", checked=self.restored[0],
                                                   total=self.restored[1])))
        if self.restore_partial:
            lines.append(("imp-status-partial", t("imp.state.restore_partial")))
        actions = []
        if self._has_progress():
            actions.append(wc.button(ui, t("imp.discard"), self._ask_discard, kind="quiet",
                                     icon=ft.Icons.DELETE_OUTLINE, data="imp-discard"))
        return state, title, lines, tone, actions

    def _status_line(self) -> ft.Control | None:
        """One status line for reading, OCR, review and errors; announced to
        screen readers when it changes."""
        ui = self.app.ui
        found = self.processing_state()
        if found is None:
            return None
        state, title, lines, tone, actions = found
        bg, fg, icon = wc.TONES[tone]
        leading = (self._reading_indicator() if self.busy
                   else ft.Icon(icon, color=getattr(ui.p, fg), size=20))
        texts: list[ft.Control] = [wc.text(ui, title, tk.TYPE_LABEL, weight=ft.FontWeight.W_600,
                                           data="imp-status-title")]
        texts += [wc.text(ui, line, tk.TYPE_BODY, selectable=True, data=data)
                  for data, line in lines]
        column: list[ft.Control] = [ft.Row([leading, ft.Column(texts, spacing=2, expand=True)],
                                           spacing=tk.SPACE_3,
                                           vertical_alignment=ft.CrossAxisAlignment.START)]
        if actions:
            column.append(ft.Container(ft.Row(actions, wrap=True, spacing=tk.SPACE_2,
                                              vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                       padding=ft.Padding.only(left=20 + tk.SPACE_3)))
        return ft.Semantics(live_region=True, content=ft.Container(
            ft.Column(column, spacing=tk.SPACE_2), bgcolor=getattr(ui.p, bg),
            border_radius=ui.radius("card"), padding=ft.Padding.symmetric(
                horizontal=tk.SPACE_4, vertical=tk.SPACE_3), data="imp-status", key="imp-status"))

    def _reading_indicator(self) -> ft.Control:
        """How far a reading is, without an endless animation.

        An indeterminate ring is redrawn on every frame. In the Windows GUI
        journey (run 43421786722, no graphics card) the program used about 3.4
        of the runner's 4 processor cores during a 50 s OCR reading, while
        Tesseract got about 4.5 s of processor time per page. A determinate
        ring changes only when a page is done; the text beside it names the
        page."""
        ui = self.app.ui
        if self.progress_done is None:
            return ft.Icon(ft.Icons.HOURGLASS_TOP, color=ui.p.text_secondary, size=20,
                           data="imp-reading-icon")
        done, total = self.progress_done
        return ft.ProgressRing(value=done / max(total, 1), width=20, height=20, stroke_width=3,
                               bgcolor=ui.p.border_strong, data="imp-reading-progress")

    # ------------------------------------------------------------------ OCR
    def _ocr_code(self) -> str:
        """The OCR language for the next reading: the researcher's choice,
        else the one of the interface language (when installed)."""
        installed = (self._ocr_runtime or (True, ()))[1]
        codes = [code for code, _ in ocr_language_options(self.app.ui.language, installed)]
        if self.ocr_choice in codes:
            return self.ocr_choice
        default = DEFAULT_OCR.get(self.app.ui.language, "eng")
        return default if default in codes else (codes[0] if codes else "eng")

    def _ocr_dropdown(self) -> ft.Dropdown:
        ui = self.app.ui
        installed = (self._ocr_runtime or (True, ()))[1]
        return wc.dropdown(ui, ui.t("imp.ocr_language"),
                           ocr_language_options(ui.language, installed), self._ocr_code(),
                           on_select=lambda e: self._set_ocr_choice(e.control.value),
                           width=280, data="imp-ocr-language")

    def _set_ocr_choice(self, code: str):
        # No re-render: the dropdown shows the choice itself.
        self.ocr_choice = code or None

    async def _read_with_ocr(self, e=None):
        """Read the document (its image pages) with local OCR in the chosen language."""
        s = self.session
        if s.source is None or self.busy:
            return
        await self.open_bytes(s.source, s.filename, path=self.source_path,
                              language=self._ocr_code())

    async def _ask_ocr_again(self, e=None):
        if self._has_progress():
            self._confirm(self.app.t("imp.reread_title"),
                          self.app.t("imp.reread_body", file=self.session.filename),
                          self.app.t("imp.reread_confirm"), self._read_again, data="imp-reread")
            return
        await self._read_again()

    async def _read_again(self):
        if self.sha:
            self.store.remove(self.sha)     # the new reading starts a new review
        await self._read_with_ocr()

    async def _ocr_page(self, e=None):
        """Read the page on screen with local OCR (the researcher's choice)."""
        if self._has_progress():
            self._confirm(self.app.t("imp.reread_title"),
                          self.app.t("imp.reread_body", file=self.session.filename),
                          self.app.t("imp.reread_confirm"), self._ocr_this_page,
                          data="imp-reread")
            return
        await self._ocr_this_page()

    async def _ocr_this_page(self):
        s, page, language = self.session, self.page_number, self._ocr_code()
        self.busy, self.error = True, None
        self.reading, self.reading_language = "ocr", language
        self.progress = self.app.t("imp.ocr_progress", page=page, done=1, total=1)
        self.progress_done = (0, 1)
        self.app.render()
        try:
            await asyncio.to_thread(s.ocr_pages, [page], language)
        except Exception as error:
            self.error = self.app.t("imp.read_failed", name=s.filename, error=error)
        else:
            self._adopt(s, sha=self.sha, path=self.source_path, language=language,
                        manual=(page,))
            self.page_number = page
        finally:
            self.busy, self.progress = False, None
        if self.error:
            self.app.status(self.error, "danger")
        else:
            self._autosave()
            self.app.status(self.app.t("imp.ocr_done", pages=pages_text(
                self.app.ui.language, [page])), "success")
        self.app.render()

    # ---------------------------------------------------------- wizard
    def _locked(self, step: str) -> bool:
        """Steps after the first wait for a form chosen by the researcher."""
        return step != "source" and (self.session.instrument is None or self.chosen is None)

    def _blockers(self) -> list[tuple[str, dict]]:
        if self.session.instrument is not None and self.chosen is None:
            return [("choose_form", {})]
        return self.session.blocker_keys()

    def _status(self) -> dict:
        """What is still open in each step (counts for the stepper and footer)."""
        s = self.session
        instrument = s.instrument
        keys = dict(self._blockers())
        schemes = instrument.schemes if instrument else ()
        confirmed = sum(1 for x in schemes if x.structure_confirmed)
        attention = len({i for i, _ in s.flags()} - s.reviewed)
        checks = sum(1 for key in ("rights", "version", "items") if s.checks.get(key))
        return {
            "source": instrument is not None and self.chosen is not None,
            "scale": "scale" not in keys and "choose_form" not in keys,
            "schemes": len(schemes), "confirmed": confirmed,
            "items": "unreviewed" not in keys and "choose_form" not in keys,
            "attention": attention,
            "total": len(instrument.questions) if instrument else 0,
            "checked": len(s.reviewed),
            "confirm": checks == 3 and "choose_form" not in keys, "checks": checks,
            "ready": not keys,
        }

    def _step_label(self, key: str, status: dict) -> str:
        ui, s = self.app.ui, self.session
        number = self.STEPS.index(key) + 1
        title = ui.t(f"imp.step.{key}")
        if key == "source":
            forms = len(s.instruments)
            if forms > 1 and self.chosen is None:
                detail = ui.t("imp.status.forms", count=forms)
            elif forms > 1:
                detail = (ui.t("imp.status.form_of", number=self.chosen + 1, total=forms) + " · "
                          + count_text(ui.language, status["total"], "questions"))
            else:
                detail = count_text(ui.language, status["total"], "questions")
        elif key == "scale":
            detail = (ui.t("imp.status.scales", done=status["confirmed"], total=status["schemes"])
                      if status["schemes"] else ui.t("imp.status.no_scales"))
        elif key == "items":
            detail = (ui.t("imp.status.attention", count=status["attention"])
                      if status["attention"] else ui.t("imp.status.all_checked"))
        else:
            detail = ui.t("imp.status.confirmations", done=status["checks"], total=3)
        return f"{number}. {title} · {detail}"

    def _stepper(self) -> ft.Control:
        ui = self.app.ui
        status = self._status()
        steps, locked_any = [], False
        for key in self.STEPS:
            if self._locked(key):
                # Not a disabled button: UI Automation on Windows would report
                # it as enabled (wc.locked_step, Stage 36.8).
                locked_any = True
                steps.append(wc.locked_step(ui, self._step_label(key, status),
                                            data=f"imp-step-{key}"))
                continue
            steps.append(wc.button(
                ui, self._step_label(key, status), lambda e, k=key: self._go(k),
                kind="primary" if key == self.step else "secondary",
                icon=ft.Icons.CHECK_CIRCLE if status[key] else ft.Icons.RADIO_BUTTON_UNCHECKED,
                data=f"imp-step-{key}"))
        row = ft.Row(steps, wrap=True, spacing=tk.SPACE_2, data="imp-steps")
        if not locked_any:
            return row
        return ft.Column([row, wc.caption(ui, ui.t("imp.choose_form_first"),
                                          data="imp-steps-locked")], spacing=tk.SPACE_1)

    def _go(self, step: str):
        if step in self.STEPS and not self._locked(step):
            self.step = step
            self._changed()

    def footer(self) -> ft.Control | None:
        """Sticky review actions: always on screen below the page, however
        far the list has been scrolled (Issue #31)."""
        ui, s = self.app.ui, self.session
        if s.source is None or s.instrument is None or self.busy:
            return None
        status = self._status()
        index = self.STEPS.index(self.step)
        keys = self._blockers()
        reason = self.blocker_text(*keys[0]) if keys else None
        summary = ui.t("imp.step_of", number=index + 1, total=len(self.STEPS),
                       title=ui.t(f"imp.step.{self.step}"))
        if self.chosen is None:
            counts = ui.t("imp.counts_forms", forms=len(s.instruments),
                          total=sum(len(x.questions) for x in s.instruments))
        else:
            counts = ui.t("imp.counts", total=status["total"], attention=status["attention"],
                          checked=status["checked"])
        # Back and Next appear only when they lead somewhere: a disabled button
        # is reported as enabled by UI Automation on Windows (wc.locked_step).
        # The footer caption already says what to do first.
        actions = []
        if index > 0:
            actions.append(wc.button(ui, ui.t("imp.back"), lambda e: self._go(self.STEPS[index - 1]),
                                     kind="quiet", icon=ft.Icons.ARROW_BACK, data="imp-back"))
        if index < len(self.STEPS) - 1 and not self._locked(self.STEPS[index + 1]):
            actions.append(wc.button(ui, ui.t("imp.next"),
                                     lambda e: self._go(self.STEPS[index + 1]),
                                     kind="secondary", icon=ft.Icons.ARROW_FORWARD,
                                     data="imp-next"))
        actions.append(wc.button(ui, ui.t("imp.create_draft"), self._create_draft,
                                 kind="primary", icon=ft.Icons.CHECK,
                                 disabled=bool(keys), tooltip=reason, data="imp-create-draft"))
        return ft.Container(ft.Row([
            ft.Column([wc.text(ui, summary, tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                       wc.caption(ui, counts + (" · " + reason if reason else ""),
                                  data="imp-footer-status")],
                      spacing=2, expand=True),
            *actions,
        ], spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=ui.p.surface, border=ft.Border(top=ft.BorderSide(1, ui.p.border)),
            padding=ft.Padding.symmetric(horizontal=tk.SPACE_5, vertical=tk.SPACE_2),
            data="imp-footer")

    def blocker_text(self, key: str, values: dict) -> str:
        return self.app.t(f"impblock.{key}", **values)

    def fact_text(self, key: str, values: dict) -> str:
        values = dict(values)
        if "pages" in values:
            values["pages"] = pages_text(self.app.ui.language, values["pages"])
        text = self.app.t(f"impnote.{key}", **values)
        return text[:1].upper() + text[1:]

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
                wc.icon_button(ui, ft.Icons.OPEN_IN_FULL, ui.t("imp.enlarge"),
                               self.enlarge_page, disabled=png is None, data="imp-enlarge"),
                *chips,
            ], wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(
                ft.Image(src=png, fit=ft.BoxFit.CONTAIN, semantics_label=s.filename)
                if png else wc.caption(ui, ui.t("common.not_available")),
                bgcolor="#FFFFFF", border=ft.Border.all(1, ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_1, data="imp-source-image"),
        ]
        # OCR for this document; while it waits for its first OCR the
        # status line above offers it instead.
        if Path(s.filename).suffix.lower() == ".pdf" and not self._unread_pages()[0]:
            ocr = [self._ocr_dropdown(),
                   wc.button(ui, ui.t("imp.ocr_page"), self._ocr_page,
                             icon=ft.Icons.DOCUMENT_SCANNER_OUTLINED, disabled=self.busy,
                             data="imp-ocr")]
            if s.ocr_pages_used and not self.ocr_manual:
                ocr.append(wc.button(ui, ui.t("imp.ocr_again"), self._ask_ocr_again,
                                     kind="quiet", icon=ft.Icons.REFRESH, disabled=self.busy,
                                     data="imp-ocr-run"))
            controls.append(ft.Row(ocr, wrap=True, spacing=tk.SPACE_2,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER))
        if self.app.bridge.open_classic is not None:
            controls.append(wc.button(ui, ui.t("imp.advanced"),
                                      lambda e: self.app.bridge.open_classic("survey"),
                                      kind="quiet", icon=ft.Icons.OPEN_IN_NEW))
        return wc.card(ui, controls, title=f"{ui.t('imp.source')} · {s.filename}",
                       padding=tk.SPACE_4, data="imp-source")

    def _page(self, step: int):
        self.page_number += step
        self.app.render()

    # --------------------------------------------------- enlarged viewer
    ZOOMS = {"fit": 1.0, "150": 1.5, "200": 2.0}

    def _page_image(self, zoom: str) -> bytes | None:
        key = (self.page_number, 0) if zoom == "fit" else (self.page_number, 0, zoom)
        if key not in self._page_cache:
            try:
                self._page_cache[key] = self.session.render_page(
                    self.page_number, zoom=self.ZOOMS[zoom])
            except Exception:
                self._page_cache[key] = None
        return self._page_cache[key]

    def enlarge_page(self, e=None):
        """The source page in a large view with page turning and zoom, to
        compare small print with the draft (nothing is changed here)."""
        self.app.page.show_dialog(self._viewer_dialog())

    def _viewer_dialog(self) -> ft.AlertDialog:
        ui, s = self.app.ui, self.session
        count = max(1, s.page_count)
        width = int(min(1200, max(480, int(getattr(self.app.page, "width", None) or 1280) - 160)))
        height = int(min(900, max(360, int(getattr(self.app.page, "height", None) or 900) - 240)))
        png = self._page_image(self.zoom)
        factor = self.ZOOMS[self.zoom]
        if png is None:
            view: ft.Control = wc.caption(ui, ui.t("common.not_available"))
        elif self.zoom == "fit":
            view = ft.Image(src=png, fit=ft.BoxFit.CONTAIN, width=width - 32, height=height - 16,
                            semantics_label=s.filename, data="imp-viewer-image")
        else:
            # Wider than the dialog: scroll sideways and down to any part.
            view = ft.Column([ft.Row([ft.Image(
                src=png, fit=ft.BoxFit.FIT_WIDTH, width=int((width - 32) * factor),
                semantics_label=s.filename, data="imp-viewer-image")],
                scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.AUTO, height=height - 16)
        controls = ft.Row([
            wc.icon_button(ui, ft.Icons.CHEVRON_LEFT, ui.t("imp.prev_page"),
                           lambda e: self._viewer_page(-1), disabled=self.page_number <= 1,
                           data="imp-viewer-prev"),
            wc.text(ui, ui.t("imp.page", page=self.page_number, count=count), tk.TYPE_LABEL,
                    data="imp-viewer-page"),
            wc.icon_button(ui, ft.Icons.CHEVRON_RIGHT, ui.t("imp.next_page"),
                           lambda e: self._viewer_page(1), disabled=self.page_number >= count,
                           data="imp-viewer-next"),
            ft.Container(expand=True),
            wc.segmented(ui, [("fit", ui.t("imp.zoom_fit")), ("150", "150 %"), ("200", "200 %")],
                         self.zoom, self._set_zoom, compact=True, data="imp-zoom"),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        return ft.AlertDialog(
            title=wc.heading(ui, f"{ui.t('imp.source')} · {s.filename}", tk.TYPE_TITLE_S),
            content=ft.Container(ft.Column([controls, ft.Container(
                view, bgcolor="#FFFFFF", border=ft.Border.all(1, ui.p.border),
                border_radius=ui.radius("card"), padding=tk.SPACE_1)], spacing=tk.SPACE_3),
                width=width, data="imp-viewer"),
            actions=[wc.button(ui, ui.t("common.close"), self._close_viewer,
                               data="imp-viewer-close")],
        )

    def _refresh_viewer(self):
        self.app.page.pop_dialog()
        self.app.page.show_dialog(self._viewer_dialog())
        self.app.render()          # the source pane follows the page shown

    def _viewer_page(self, step: int):
        count = max(1, self.session.page_count)
        self.page_number = max(1, min(count, self.page_number + step))
        self._refresh_viewer()

    def _set_zoom(self, zoom: str):
        if zoom in self.ZOOMS:
            self.zoom = zoom
            self._refresh_viewer()

    def _close_viewer(self, e=None):
        self.app.page.pop_dialog()

    # ------------------------------------------------------------ steps
    def _step_source(self) -> ft.Control:
        """Step 1: what was read from which pages, what was kept out, how
        many items the document says it has, and every form found in it."""
        ui, s = self.app.ui, self.session
        instrument = s.instrument
        rows: list[ft.Control] = []
        tones = {"count_match": "success", "references": "info", "ocr_read": "info"}
        for key, values in s.facts:
            rows.append(wc.notice(ui, self.fact_text(key, values), tones.get(key, "warning"),
                                  data=f"imp-fact-{key}"))
        if instrument is None:
            pages, reason = self._unread_pages()
            if pages and reason is None:
                rows.append(wc.notice(ui, ui.t("imp.scan.pending", pages=pages_text(
                    ui.language, pages)), "info", data="imp-scan-pending"))
            elif not pages:
                rows.append(wc.notice(ui, ui.t("impblock.no_instrument"), "warning",
                                      data="imp-no-items"))
            return wc.card(ui, rows, title=ui.t("imp.step.source"), data="imp-step-body")
        if s.expected_count is None:
            rows.append(wc.caption(ui, ui.t("imp.no_count"), data="imp-no-count"))
        if s.non_items:
            listing = [wc.caption(ui, f"p. {page}: {line}") for page, line in s.non_items[:60]]
            rows.append(wc.expansion(
                ui, wc.text(ui, ui.t("imp.excluded", count=len(s.non_items)), tk.TYPE_LABEL,
                            weight=ft.FontWeight.W_600),
                [ft.Container(ft.Column(listing, spacing=2), padding=tk.SPACE_3)],
                key="imp-excluded", opened=self.opened, data="imp-excluded"))
        forms: list[ft.Control] = []
        if len(s.instruments) > 1:
            forms += [wc.heading(ui, ui.t("imp.forms_title"), tk.TYPE_TITLE_S),
                      wc.caption(ui, ui.t("imp.forms_hint", count=len(s.instruments)))]
        forms += [self._form_card(i, form) for i, form in enumerate(s.instruments)]
        rows.append(ft.Column(forms, spacing=tk.SPACE_3, data="imp-instruments"))
        if self.chosen is not None:
            rows += [wc.notice(ui, w, "warning") for w in instrument.warnings[:3]]
        return wc.card(ui, rows, title=ui.t("imp.step.source"), data="imp-step-body")

    def _form_card(self, index: int, form) -> ft.Control:
        """One form of the document: its title, items, documented answer
        options with their evidence, pages, and the researcher's choice."""
        ui = self.app.ui
        t = ui.t
        several = len(self.session.instruments) > 1
        chosen = self.chosen == index
        pages = sorted({row.page for row in form.questions if row.page})
        summary = count_text(ui.language, len(form.questions), "items")
        if pages:
            summary += " · " + pages_text(ui.language, pages)
        lines: list[ft.Control] = [
            ft.Row([wc.heading(ui, form.title, tk.TYPE_TITLE_S),
                    *([wc.chip(ui, t("imp.form.chosen"), "success", icon=ft.Icons.CHECK_CIRCLE,
                               data=f"imp-instrument-chosen-{index}")]
                      if chosen and several else [])],
                   wrap=True, spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            wc.caption(ui, summary, data=f"imp-instrument-summary-{index}"),
        ]
        for scheme in form.schemes:
            state = t("imp.form.confirmed") if scheme.structure_confirmed else t(
                "imp.form.unconfirmed")
            lines += [wc.text(ui, t("imp.form.options", labels=" / ".join(scheme.labels)),
                              tk.TYPE_BODY, data=f"imp-instrument-options-{index}-{scheme.id}"),
                      wc.caption(ui, t("imp.form.evidence", evidence=evidence_text(
                          ui.language, scheme.evidence), page=scheme.page) + " · " + state)]
        for answer in form.response_formats:
            lines += [wc.text(ui, t("imp.form.options", labels=" / ".join(answer.labels)),
                              tk.TYPE_BODY),
                      wc.caption(ui, t("imp.form.evidence", evidence=evidence_text(
                          ui.language, answer.evidence), page=answer.page))]
        if not form.schemes and not form.response_formats:
            lines.append(wc.caption(ui, t("imp.form.no_options")))
        if several:
            lines.append(ft.Row([wc.button(
                ui, t("imp.form.continue") if chosen else t("imp.form.use"),
                wc.handler(self._use_form, index),
                kind="primary" if self.chosen is None else "secondary",
                icon=ft.Icons.ARROW_FORWARD if chosen else ft.Icons.FACT_CHECK_OUTLINED,
                tooltip=t("imp.form.use_tip", title=form.title),
                data=f"imp-instrument-use-{index}")]))
        else:
            lines.append(wc.caption(ui, t("imp.form.only")))
        card = wc.card(ui, lines, padding=tk.SPACE_4, data=f"imp-instrument-{index}",
                       border=ui.p.accent if chosen and several else None,
                       bgcolor=ui.p.accent_subtle if chosen and several else None)
        card.key = f"imp-instrument-{index}"
        return card

    def _use_form(self, index: int):
        """Review form ``index``: the later steps show only this form. Each
        form keeps its own review when the researcher switches between them."""
        from import_session import fresh_checks

        s = self.session
        if self.busy or not 0 <= index < len(s.instruments):
            return
        if self.chosen != index:
            self._stash_form()
            s.select(index)
            kept = self.forms_progress.get(index)
            if kept is not None:
                s.reviewed, s.checks = set(kept.reviewed), {**fresh_checks(), **kept.checks}
            self.chosen = index
            self.selected, self.list_page, self.filter = None, 0, "all"
            self.scale_edits, self.scale_errors, self._typed = {}, {}, {}
            self.page_number = s.instrument.first_page or 1
        self.step = "scale"
        self._changed()

    def _instrument(self, index: int):
        """The form chooser by index (kept for scenarios and older callers)."""
        self._use_form(index)

    def _step_scale(self) -> ft.Control:
        """Step 2: each shared response scale, confirmed on its own."""
        ui, instrument = self.app.ui, self.session.instrument
        if not instrument.schemes:
            return wc.card(ui, [wc.text(ui, ui.t("imp.no_scales"), tk.TYPE_BODY)],
                           title=ui.t("imp.step.scale"), data="imp-step-body")
        return ft.Column([wc.heading(ui, ui.t("imp.step.scale"), tk.TYPE_TITLE_S),
                          *[self._scale_card(scheme) for scheme in instrument.schemes]],
                         spacing=tk.SPACE_3, data="imp-step-body")

    # ------------------------------------------------------------- items
    def _attention(self) -> list[int]:
        s = self.session
        return sorted({i for i, _ in s.flags()} - s.reviewed)

    def _visible(self, attention=None) -> list[int]:
        """The items the list shows (all, or those needing attention)."""
        count = len(self.session.instrument.questions)
        if self.filter != "attention":
            return list(range(count))
        attention = set(self._attention() if attention is None else attention)
        return [i for i in range(count) if i in attention or i == self.selected]

    def _window(self, visible: list[int]) -> tuple[list[int], int, int]:
        """(rows shown, page, pages): a long list a fixed page at a time,
        so rows never shift while the selection moves inside a page."""
        if len(visible) <= self.PAGE_LIMIT:
            return visible, 0, 1
        pages = -(-len(visible) // self.PAGE_SIZE)
        page = max(0, min(self.list_page, pages - 1))
        return visible[page * self.PAGE_SIZE:(page + 1) * self.PAGE_SIZE], page, pages

    def _page_of(self, index: int | None) -> int:
        visible = self._visible()
        if index is None or index not in visible or len(visible) <= self.PAGE_LIMIT:
            return self.list_page if len(visible) > self.PAGE_LIMIT else 0
        return visible.index(index) // self.PAGE_SIZE

    def _step_items(self) -> ft.Control:
        """Step 3: every item with status counts; the selected one opens
        right under itself, so the list never jumps to an editor far away."""
        ui, s = self.app.ui, self.session
        instrument = s.instrument
        flags = {i for i, _ in s.flags()}
        attention = flags - s.reviewed
        status = self._status()
        selector = wc.segmented(ui, [
            ("all", ui.t("imp.filter.all", count=status["total"])),
            ("attention", ui.t("imp.filter.attention", count=len(attention)))],
            self.filter, self._set_filter, data="imp-filter")
        window, page, pages = self._window(self._visible(attention))
        items: list[ft.Control] = []
        for index in window:
            row = instrument.questions[index]
            selected = index == self.selected
            kind = row.question.get("kind")
            items.append(ft.Container(
                content=ft.Row([
                    wc.text(ui, str(row.number), tk.TYPE_LABEL, color=ui.p.text_muted),
                    ft.Column([
                        wc.text(ui, f"{row.number}. {row.question.get('prompt', '')}",
                                tk.TYPE_BODY, max_lines=2),
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
                on_click=lambda e, i=index: self._select(i, keep_in_place=True),
                # A scroll key: the page can bring the row into view (keyboard,
                # restore) and Flet reconciles rows by it across re-renders.
                key=ft.ScrollKey(f"imp-row-{index}"), data=f"imp-item-{index}"))
            if selected:
                items.append(self._item_editor(index, low=index in flags))
        if not items:
            items.append(wc.caption(ui, ui.t("imp.status.all_checked")))
        controls: list[ft.Control] = [
            ft.Row([wc.heading(ui, ui.t("imp.step.items"), tk.TYPE_TITLE_S), selector],
                   wrap=True, spacing=tk.SPACE_3,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            wc.caption(ui, ui.t("imp.counts", total=status["total"],
                                attention=status["attention"], checked=status["checked"]),
                       data="imp-counts"),
            wc.caption(ui, ui.t("imp.keys"), data="imp-keys"),
        ]
        if pages > 1:
            controls.append(self._pager(window, page, pages, ""))
        controls.append(ft.Column(items, spacing=tk.SPACE_1, data="imp-items"))
        if pages > 1:
            controls.append(self._pager(window, page, pages, "-end"))
        return ft.Column(controls, spacing=tk.SPACE_3, data="imp-step-body")

    def _pager(self, window: list[int], page: int, pages: int, suffix: str) -> ft.Control:
        ui = self.app.ui
        questions = self.session.instrument.questions
        return ft.Row([
            wc.button(ui, ui.t("imp.list_prev"), lambda e: self._list_page(page - 1),
                      kind="quiet", icon=ft.Icons.CHEVRON_LEFT, disabled=page <= 0,
                      data=f"imp-list-prev{suffix}"),
            wc.text(ui, ui.t("imp.list_page", first=questions[window[0]].number,
                             last=questions[window[-1]].number, page=page + 1, pages=pages),
                    tk.TYPE_LABEL, data=f"imp-list-page{suffix}"),
            wc.button(ui, ui.t("imp.list_next"), lambda e: self._list_page(page + 1),
                      kind="quiet", icon=ft.Icons.CHEVRON_RIGHT, disabled=page >= pages - 1,
                      data=f"imp-list-next{suffix}"),
        ], wrap=True, spacing=tk.SPACE_2, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _list_page(self, page: int):
        """Show another page of a long list, from its first row."""
        pages = self._window(self._visible())[2]
        self.list_page = max(0, min(page, pages - 1))
        self.app.render()
        window = self._window(self._visible())[0]
        if window:
            self._reveal(window[0])

    def _item_editor(self, index: int, *, low: bool) -> ft.Control:
        """The selected item: its source excerpt, a one-question preview and
        the wording correction."""
        from scientific_survey_import import proposed_scheme_question

        ui, s = self.app.ui, self.session
        row = s.instrument.questions[index]
        prompt = row.question.get("prompt", "")
        typed = self._typed.get(index)
        wording = wc.text_field(ui, ui.t("imp.edit_wording"), prompt if typed is None else typed,
                                multiline=True, data="imp-wording",
                                on_change=lambda e, i=index: self._typing(i, e.control.value))
        question = dict(row.question)
        schemes = {x.id: x for x in s.instrument.schemes}
        if row.scheme_id in schemes:
            question = proposed_scheme_question(question, schemes[row.scheme_id])
        editor = wc.card(ui, [
            wc.section_label(ui, ui.t("imp.source_excerpt")),
            wc.text(ui, row.excerpt, tk.TYPE_BODY, color=ui.p.text_secondary, selectable=True),
            *[wc.caption(ui, "• " + note) for note in row.notes],
            wc.checkbox(ui, ui.t("imp.item_reviewed"), index in s.reviewed,
                        on_change=lambda e, i=index: self._reviewed(i, e.control.value),
                        data="imp-item-reviewed"),
            wording,
            *([wc.caption(ui, ui.t("imp.not_applied"), data="imp-not-applied")]
              if typed is not None and typed != prompt else []),
            ft.Row([
                wc.button(ui, ui.t("q.apply"), lambda e: self._wording(wording.value),
                          data="imp-wording-apply"),
                wc.button(ui, ui.t("imp.check_next"), lambda e: self.check_and_next(),
                          kind="quiet", icon=ft.Icons.DONE, data="imp-check-next"),
                wc.button(ui, ui.t("imp.next_flag"), self._next_flag, kind="quiet",
                          icon=ft.Icons.SKIP_NEXT, data="imp-next-flag"),
            ], wrap=True, spacing=tk.SPACE_2),
            wc.section_label(ui, ui.t("q.preview")),
            respondent_question(ui, question, None, lambda k, v: None, number=row.number),
        ], title=f"{row.number}. {ui.t('q.editor')}", padding=tk.SPACE_4,
            border=ui.p.accent, data="imp-editor")
        # A stable key: the editor moves with the selection, keeping its
        # identity (and the keyboard focus of its field) across re-renders.
        editor.key = "imp-editor"
        editor.on_size_change = self._editor_resized
        return editor

    def _typing(self, index: int, value: str):
        """Wording being typed: kept for the item, applied only by "Apply"
        (never automatically) and never re-rendered while typing."""
        self._typed[index] = value or ""

    def _editor_resized(self, e):
        self._editor_height = float(getattr(e, "height", 0) or 0)

    def _set_filter(self, value: str):
        self.filter = value if value in ("all", "attention") else "all"
        self.list_page = self._page_of(self.selected)
        self.app.render()

    def _next_flag(self, e=None):
        self.next_attention()

    def next_attention(self, *, backwards: bool = False):
        """The next (or previous) item that needs attention, brought into view."""
        attention = self._attention()
        if not attention:
            self.app.status(self.app.t("imp.all_checked"), "success")
            return
        current = self.selected
        if backwards:
            before = [i for i in attention if current is None or i < current]
            target = (before or attention)[-1]
        else:
            after = [i for i in attention if current is None or i > current]
            target = (after or attention)[0]
        self._select(target, reveal=True)

    def check_and_next(self):
        """Mark the selected item as compared with the source, then go to
        the next item that needs attention."""
        if self.selected is None:
            self.next_attention()
            return
        current = self.selected
        self.session.mark_reviewed(current, True)
        attention = self._attention()
        after = [i for i in attention if i > current] or attention
        if after:
            self._select(after[0], reveal=True)
        else:
            self.app.status(self.app.t("imp.all_checked"), "success")
            self._changed()

    def step_item(self, delta: int):
        """The next (+1) or previous (-1) item of the list as shown."""
        visible = self._visible()
        if not visible:
            return
        if self.selected in visible:
            position = visible.index(self.selected) + delta
            if not 0 <= position < len(visible):
                return
            target = visible[position]
        else:
            target = visible[0] if delta > 0 else visible[-1]
        self._select(target, reveal=True)

    def shortcut(self, e) -> bool:
        """Keys of the items step, routed here by the shell (only while the
        items step is shown): F8 / Shift+F8 the next / previous item that
        needs attention, F9 mark checked and go on, Alt+↓ / Alt+↑ the next /
        previous item. None of them types or edits text."""
        if (self.busy or self.step != "items" or self.session.instrument is None
                or self.chosen is None):
            return False
        key = (getattr(e, "key", "") or "").upper()
        ctrl, alt, shift = bool(e.ctrl), bool(e.alt), bool(e.shift)
        if key == "F8" and not ctrl and not alt:
            self.next_attention(backwards=shift)
        elif key == "F9" and not (ctrl or alt or shift):
            self.check_and_next()
        elif alt and not ctrl and not shift and key in ("ARROW DOWN", "ARROW UP"):
            self.step_item(1 if key == "ARROW DOWN" else -1)
        else:
            return False
        return True

    def _reveal(self, index: int) -> None:
        self.app.reveal(f"imp-row-{index}")

    def _step_confirm(self) -> ft.Control:
        """Step 4: the researcher's independent confirmations."""
        ui, s = self.app.ui, self.session
        status = self._status()
        count_fact = next((f for f in s.facts if f[0] in ("count_match", "count_mismatch")), None)
        controls: list[ft.Control] = [
            wc.checkbox(ui, ui.t("imp.check_version"), bool(s.checks.get("version")),
                        on_change=lambda e: self._check("version", e.control.value),
                        data="imp-check-version"),
            wc.checkbox(ui, ui.t("imp.check_rights"), bool(s.checks.get("rights")),
                        on_change=lambda e: self._check("rights", e.control.value),
                        data="imp-check-rights"),
            wc.checkbox(ui, ui.t("imp.check_items"), bool(s.checks.get("items")),
                        on_change=lambda e: self._check("items", e.control.value),
                        data="imp-check-items"),
            wc.caption(ui, self.fact_text(*count_fact) if count_fact else ui.t("imp.no_count")),
        ]
        for done, label in ((status["scale"], self._step_label("scale", status)),
                            (status["items"], self._step_label("items", status))):
            controls.append(ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE if done else ft.Icons.PENDING_OUTLINED,
                        color=ui.p.success if done else ui.p.warning, size=18),
                wc.text(ui, label)], spacing=tk.SPACE_2))
        keys = self._blockers()
        if keys:
            controls.append(wc.notice(ui, "\n".join("• " + self.blocker_text(*k) for k in keys),
                                      "warning", title=ui.t("imp.blocked", reason="").rstrip(": "),
                                      data="imp-blockers"))
        else:
            controls.append(wc.notice(ui, ui.t("imp.ready"), "success", data="imp-ready"))
        return wc.card(ui, controls, title=ui.t("imp.step.confirm"), data="imp-checklist")

    def _select(self, index: int, *, keep_in_place: bool = False, reveal: bool = False):
        """Open item ``index``. A row clicked below the open editor stays under
        the pointer: that editor closes above it, so the page scrolls up by the
        editor's height (without this the row jumped up by ~560 px). Keys and
        "next item" bring the item into view instead."""
        previous, was_items = self.selected, self.step == "items"
        self.selected = index
        self.step = "items"
        row = self.session.instrument.questions[index]
        self.page_number = row.page or self.page_number   # the source follows the item
        self.list_page = self._page_of(index)
        self._changed()
        if reveal:
            self._reveal(index)
        elif (keep_in_place and was_items and previous is not None and previous < index
                and self._editor_height):
            self.app.scroll_page(-(self._editor_height + tk.SPACE_1))

    def _reviewed(self, index: int, value: bool):
        self.session.mark_reviewed(index, bool(value))
        self._changed()

    def _wording(self, prompt: str):
        index = self.selected
        if index is None:
            return
        try:
            self.session.correct_wording(index, prompt or "")
        except Exception as error:
            self.app.status(str(error), "danger")
            self.app.render()
            return
        self._typed.pop(index, None)
        self._log({"do": "wording", "index": index, "prompt": prompt or ""})
        self.app.status(self.app.t("imp.wording_applied",
                                   number=self.session.instrument.questions[index].number),
                        "success")
        self._changed()

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
        error = self.scale_errors.get(scheme.id)
        return wc.card(ui, [
            ft.Row([wc.chip(ui, ui.t("imp.scale_items", count=len(linked)), state,
                            icon=ft.Icons.LINK),
                    wc.caption(ui, ui.t("imp.form.evidence", evidence=evidence_text(
                        ui.language, scheme.evidence), page=scheme.page))], wrap=True,
                   spacing=tk.SPACE_2),
            *fields, *issues,
            wc.text_field(ui, ui.t("imp.reverse_items"), edits["reverse"], width=320,
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
            *([wc.notice(ui, error, "danger", data=f"scale-{scheme.id}-error")] if error else []),
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
        # Kept exactly as the researcher applied it (replayed on restore).
        reviewed = next(x for x in self.session.instrument.schemes if x.id == scheme_id)
        self._log({"do": "scale", "scheme": scheme_id, "labels": list(reviewed.labels),
                   "codes": [c or "" for c in reviewed.codes],
                   "reverse_items": list(reviewed.reverse_items),
                   "structure": reviewed.structure_confirmed,
                   "numeric": reviewed.codes_confirmed, "reverse": reviewed.reverse_confirmed})
        self._changed(render=False)

    def _apply_scale(self, scheme_id: str):
        edits = self.scale_edits.get(scheme_id, {})
        try:
            self.apply_scale(scheme_id, structure=edits.get("structure", False),
                             numeric=edits.get("numeric", False),
                             reverse=edits.get("reverse_ok", False))
            self.scale_errors.pop(scheme_id, None)
            self.app.status(self.app.t("imp.scale_applied",
                                       count=len(self.session.linked(scheme_id))), "success")
        except (ValueError, KeyError) as error:
            self.scale_errors[scheme_id] = str(error)
            self.app.status(str(error), "danger")
        self.app.render()

    def _not_shared(self, scheme_id: str):
        try:
            self.session.not_shared(scheme_id)
            self.scale_edits.pop(scheme_id, None)
            self.scale_errors.pop(scheme_id, None)
            self._log({"do": "not_shared", "scheme": scheme_id})
            self._changed(render=False)
        except (ValueError, KeyError) as error:
            self.scale_errors[scheme_id] = str(error)
            self.app.status(str(error), "danger")
        self.app.render()

    # --------------------------------------------------------- confirm
    def _check(self, key: str, value: bool):
        self.session.checks[key] = bool(value)
        self._changed()

    def _finished(self) -> None:
        """The draft was created: its review session is no longer kept."""
        if self.sha:
            self.store.remove(self.sha)

    def create_draft(self) -> list[dict]:
        if self.chosen is None:
            raise ValueError(self.blocker_text("choose_form", {}))
        questions = self.session.draft()
        builder = self.app.pages["questionnaires"]
        builder.load_draft(questions, title=self.session.instrument.title,
                           origin=f"{self.session.filename} · {self.session.instrument.title}")
        self._finished()
        return questions

    def _create_draft(self, e=None):
        if self.chosen is None:
            self.app.status(self.blocker_text("choose_form", {}), "danger")
            self.app.render()
            return
        try:
            questions = self.session.draft()
        except ValueError as error:
            self.app.status(self.app.t("imp.blocked", reason=error), "danger")
            self.app.render()
            return
        instrument, filename = self.session.instrument, self.session.filename
        builder = self.app.pages["questionnaires"]

        def replace():
            builder.load_draft(questions, title=instrument.title,
                               origin=f"{filename} · {instrument.title}")
            self._finished()
            self.app.status(self.app.t("imp.draft_created", count=len(questions)), "success")
            self.app.navigate("questionnaires")

        builder.confirm_replace(instrument.title, len(questions), replace)
