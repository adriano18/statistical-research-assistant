"""The AI assistant section of a result on the Results page (Stage 36, §12).

What the researcher sees, in order: the task, the context sources this
project allows (each with what it holds), a preview of exactly what would be
sent — provider, the exact model chosen in Settings, size, data rows and the
full text — and a **Send to <provider> (<model>)** button. Pressing it is
the consent for that one request; nothing is sent before, and nothing when a
project opens. While waiting, the request can be cancelled.

The reply is a draft: numbers that do not appear in what was sent are
highlighted and listed. The researcher copies it, adds it to their own
interpretation note (labelled as an unverified AI draft) or discards it; a
draft never changes a result. Every failure is explained with a next step.

Without a provider, a model and the researcher's key (``ai_context.readiness``)
the section only says how to connect one in Settings, no request is ever
made, and everything else works as before. Without an open project only the
result's own text can be sent (no project sources).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import itertools
import threading

import flet as ft

import ai_assist
import ai_context
import ai_providers
import secret_store
import workspace_components as wc
import workspace_tokens as tk

NOTE_LIMIT = 10_000          # interpretation_docx refuses longer researcher notes
# Project sources that help each task; offered only when the project allows them.
SUGGESTED = {
    "explain_table": (),
    "explain_method": ("profile",),
    "interpretation": ("overview", "plan"),
    "contradictions": ("plan", "results"),
    "methods": ("overview", "dictionary"),
    "hypotheses": ("overview", "dictionary"),
    "report_structure": ("overview", "plan", "results"),
}
# A refusal code or ProviderError reason -> the "assistant.error.*" text.
ERRORS = {
    "not_ready": "not_ready", "bad_model": "not_ready", "unknown_provider": "not_ready",
    "no_models": "not_ready", "no_store": "no_store", "bad_key": "bad_key",
    "offline": "offline", "rate_limited": "rate_limited", "unavailable": "unavailable",
    "budget": "budget", "not_allowed": "not_allowed", "unknown_source": "not_allowed",
    "rows_not_anonymous": "rows_not_anonymous", "no_project": "no_project",
    "too_long": "too_long", "cancelled": "cancelled", "not_found": "not_found",
    "empty": "empty", "malformed": "malformed", "too_large": "malformed",
}
NEEDS_SETTINGS = {"not_ready", "no_store", "bad_key", "budget", "not_found", "empty", "unknown"}
NEEDS_PERMISSIONS = {"not_allowed", "rows_not_anonymous"}
REFUSED = {"not_ready", "no_store", "budget", "not_allowed", "rows_not_anonymous",
           "no_project", "too_long"}


@dataclass
class PanelState:
    """One result's assistant: choices, the request in flight and its outcome."""

    task: str | None = None
    depth: str = "researcher"
    sources: set[str] = field(default_factory=set)
    question: str = ""
    busy: bool = False
    cancel: threading.Event | None = None
    ticket: int = 0
    draft: ai_assist.Draft | None = None
    used: bool = False                       # the draft was added to the note
    error: tuple[str, dict] | None = None     # (code, values)
    notice: tuple[str, str] | None = None     # (message, tone)


class AssistantPanel:
    """Builds the section for one result and runs its requests."""

    def __init__(self, results_page):
        self.results = results_page
        self.app = results_page.app
        self.states: dict[int, PanelState] = {}
        self.previewed: dict[int, ai_assist.Request] = {}
        # Extra arguments for the provider calls; tests point them at a local
        # mock server (``base=``). Empty in the application.
        self.http: dict = {}
        self._tickets = itertools.count(1)

    # ------------------------------------------------------------- state
    @property
    def data_root(self):
        return self.app.project_root.parent

    def state(self, entry_id: int) -> PanelState:
        return self.states.setdefault(entry_id, PanelState())

    def project(self):
        binding = self.app.projects
        return binding.project if binding.active else None

    def tasks(self, entry) -> list[str]:
        return [task for task in ai_assist.TASKS
                if task != "explain_table" or ai_assist.has_tables(entry.run)]

    def task(self, entry, state: PanelState) -> str:
        offered = self.tasks(entry)
        return state.task if state.task in offered else offered[0]

    def offered(self, project) -> dict[str, str]:
        """Each project source with its state here: "on" (may be chosen),
        "rows" (allowed, but the project lacks the anonymity statement) or
        "off" (not allowed for this project)."""
        if project is None:
            return {}
        decided = ai_context.permissions(project)
        anonymous = project.data_anonymous
        return {key: ("off" if not decided[key] else
                      "rows" if key == "raw_data" and not anonymous else "on")
                for key in ai_context.SOURCE_KEYS}

    def request(self, entry, state: PanelState) -> ai_assist.Request:
        """What would be sent now for this result (built locally)."""
        app = self.app
        project = self.project()
        offered = self.offered(project)
        task = self.task(entry, state)
        sources = [key for key in ai_context.SOURCE_KEYS
                   if key in state.sources and offered.get(key) == "on"]
        result = ai_assist.describe_result(
            entry, parts=ai_assist.TASK_SPECS[task].parts,
            reviewed=self.results.reviewed.get(entry.id, set()),
            results_in_session=len(app.session.results))
        return ai_assist.build_request(
            task, result=result, question=state.question, sources=sources, project=project,
            session=app.session, profile=app.profile, survey_root=app.survey_root,
            depth=state.depth, language=app.session.language)

    # ------------------------------------------------------------- build
    def section(self, entry) -> ft.Control:
        ui = self.app.ui
        state = self.state(entry.id)
        setup = ai_context.readiness(self.data_root)
        if setup.ready:
            content = self._ready(entry, state, setup)
            hint = ui.t("assistant.hint_ready", provider=setup.provider_name)
            if state.error is not None:
                content.append(self._error(entry, state, setup))
        else:              # the notice says why and what to do; older errors are moot
            content = self._not_ready(setup)
            hint = ui.t("assistant.hint_off")
        if state.notice is not None:
            content.append(wc.notice(ui, state.notice[0], state.notice[1], data="ai-notice"))
        if state.draft is not None:
            content.append(self._draft(entry, state))
        return wc.expansion(
            ui, wc.heading(ui, ui.t("assistant.title"), tk.TYPE_TITLE_S),
            [ft.Container(ft.Column(content, spacing=tk.SPACE_3), padding=tk.SPACE_4)],
            key=f"ai-{entry.id}", opened=self.results.opened,
            subtitle=wc.caption(ui, hint, data="ai-hint"), data="ai-panel")

    def _not_ready(self, setup: ai_context.Readiness) -> list[ft.Control]:
        ui = self.app.ui
        return [wc.notice(ui, ui.t(f"assistant.off.{setup.problem}", provider=setup.provider_name),
                          "info", title=ui.t("assistant.off_title"), actions=[
                              wc.button(ui, ui.t("assistant.open_settings"), self._open_settings,
                                        icon=ft.Icons.SETTINGS_OUTLINED,
                                        data="ai-open-settings")],
                          data="ai-not-ready")]

    def _ready(self, entry, state: PanelState, setup: ai_context.Readiness) -> list[ft.Control]:
        ui = self.app.ui
        task = self.task(entry, state)
        busy = state.busy
        controls: list[ft.Control] = [
            wc.caption(ui, ui.t("assistant.intro")),
            wc.dropdown(ui, ui.t("assistant.task"),
                        [(key, ui.t(f"assistant.task.{key}")) for key in self.tasks(entry)], task,
                        on_select=lambda e, i=entry.id: self._set_task(i, e.control.value),
                        width=420, disabled=busy, data="ai-task"),
            wc.caption(ui, ui.t(f"assistant.task.{task}.detail"), data="ai-task-detail"),
            wc.section_label(ui, ui.t("assistant.depth")),
            wc.segmented(ui, [("student", ui.t("depth.student")),
                              ("researcher", ui.t("assistant.depth.researcher")),
                              ("professor", ui.t("depth.professor"))], state.depth,
                         lambda value, i=entry.id: self._set_depth(i, value), data="ai-depth"),
        ]
        question = wc.text_field(ui, ui.t("assistant.question"), state.question, multiline=True,
                                 hint=ui.t("assistant.question_hint"),
                                 on_change=lambda e, i=entry.id: self._set_question(
                                     i, e.control.value or ""), data="ai-question")
        question.on_blur = lambda e: self.app.render()
        question.disabled = busy
        controls.append(question)
        controls += self._sources(entry, state, task)
        try:
            request = self.request(entry, state)
        except ai_context.ContextRefused as refused:      # e.g. a source of another project
            state.error = (refused.codes[0] if refused.codes else "unknown", {})
            return controls
        self.previewed[entry.id] = request
        controls.append(self._preview(entry, request, setup))
        too_long = request.characters > ai_assist.MAX_PROMPT_CHARS
        if too_long:
            controls.append(wc.notice(ui, ui.t("assistant.too_long", chars=request.characters,
                                               limit=ai_assist.MAX_PROMPT_CHARS),
                                      "warning", data="ai-too-long"))
        send = wc.button(ui, ui.t("assistant.send", provider=setup.provider_name,
                                  model=setup.model),
                         wc.handler(self._send_ai_request, entry.id), kind="primary",
                         icon=ft.Icons.SEND_OUTLINED, disabled=busy or too_long, data="ai-send")
        controls.append(send)
        controls.append(wc.caption(ui, ui.t("assistant.consent" if self.project() is not None
                                            else "assistant.consent_local"),
                                   data="ai-consent"))
        if busy:
            controls.append(ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=2,
                                semantics_label=ui.t("assistant.sending",
                                                     provider=setup.provider_name,
                                                     model=setup.model)),
                wc.text(ui, ui.t("assistant.sending", provider=setup.provider_name,
                                 model=setup.model), data="ai-progress-text"),
                wc.button(ui, ui.t("assistant.cancel"),
                          lambda e, i=entry.id: self._cancel_ai_request(i),
                          icon=ft.Icons.CLOSE, data="ai-cancel"),
            ], spacing=tk.SPACE_3, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                data="ai-progress"))
        return controls

    def _sources(self, entry, state: PanelState, task: str) -> list[ft.Control]:
        ui = self.app.ui
        project = self.project()
        controls: list[ft.Control] = [
            wc.section_label(ui, ui.t("assistant.sources")),
            wc.checkbox(ui, ui.t("assistant.source.result"), True, disabled=True,
                        data="ai-source-result"),
            ft.Container(wc.caption(ui, ui.t("assistant.source.result_detail")),
                         padding=ft.Padding.only(left=tk.SPACE_6)),
        ]
        offered = self.offered(project)
        # A source withdrawn since it was ticked is forgotten: allowing it
        # again later needs a new tick, never a silent return.
        state.sources &= {key for key, standing in offered.items() if standing == "on"}
        if project is None:
            controls.append(wc.caption(ui, ui.t("assistant.no_project"), data="ai-no-project"))
            return controls
        labels = {source.key: source for source in ai_context.SOURCES}
        for key, standing in offered.items():
            if standing == "off":
                continue
            source = labels[key]
            controls.append(wc.checkbox(
                ui, ui.t(source.label), key in state.sources and standing == "on",
                on_change=lambda e, i=entry.id, k=key: self._toggle_source(
                    i, k, bool(e.control.value)),
                disabled=state.busy or standing != "on", data=f"ai-source-{key}"))
            detail = ui.t(source.detail) + ("\n" + ui.t("assistant.rows_blocked")
                                             if standing == "rows" else "")
            controls.append(ft.Container(wc.caption(ui, detail),
                                         padding=ft.Padding.only(left=tk.SPACE_6)))
        refused = [ui.t(labels[key].label) for key, standing in offered.items() if standing == "off"]
        if refused:
            controls.append(wc.caption(ui, ui.t("assistant.not_allowed", sources=", ".join(refused)),
                                       data="ai-not-allowed"))
        useful = [ui.t(labels[key].label) for key in SUGGESTED.get(task, ())]
        if useful:
            controls.append(wc.caption(ui, ui.t("assistant.suggested", sources=", ".join(useful)),
                                       data="ai-suggested"))
        controls.append(wc.button(ui, ui.t("assistant.permissions"), self._open_permissions,
                                  kind="quiet", icon=ft.Icons.TUNE, data="ai-permissions"))
        return controls

    def _preview(self, entry, request: ai_assist.Request,
                 setup: ai_context.Readiness) -> ft.Control:
        ui = self.app.ui
        labels = {source.key: ui.t(source.label) for source in ai_context.SOURCES}
        included = [ui.t("assistant.source.result")] if request.includes_result else []
        included += [labels[key] for key in request.sources]
        rows = (ui.t("assistant.preview.rows_some", rows=request.data_rows) if request.data_rows
                else ui.t("assistant.preview.rows_none"))
        text = wc.text(ui, request.prompt, tk.TYPE_BODY, selectable=True, data="ai-preview-text")
        return wc.card(ui, [
            wc.text(ui, ui.t("assistant.preview.to", provider=setup.provider_name,
                             host=setup.host, model=setup.model), data="ai-preview-to"),
            wc.text(ui, ui.t("assistant.preview.size", chars=request.characters,
                             tokens=request.tokens, reply=request.reply_tokens),
                    data="ai-preview-size"),
            wc.text(ui, rows, data="ai-preview-rows"),
            wc.text(ui, ui.t("assistant.preview.sources", sources=", ".join(included)),
                    data="ai-preview-sources"),
            wc.expansion(ui, wc.text(ui, ui.t("assistant.preview.text"), tk.TYPE_LABEL,
                                     weight=ft.FontWeight.W_600),
                         [ft.Container(text, padding=tk.SPACE_3)],
                         key=f"ai-text-{entry.id}", opened=self.results.opened,
                         data="ai-preview-exact"),
        ], title=ui.t("assistant.preview"), bgcolor=ui.p.surface_alt, data="ai-preview")

    def _error(self, entry, state: PanelState, setup: ai_context.Readiness) -> ft.Control:
        ui = self.app.ui
        code, values = state.error
        key = ERRORS.get(code, "unknown")
        message = ui.t(f"assistant.error.{key}", provider=setup.provider_name,
                       model=setup.model or "—", **values)
        actions = []
        if key in NEEDS_SETTINGS:
            actions.append(wc.button(ui, ui.t("assistant.open_settings"), self._open_settings,
                                     icon=ft.Icons.SETTINGS_OUTLINED, data="ai-error-settings"))
        if key in NEEDS_PERMISSIONS:
            actions.append(wc.button(ui, ui.t("assistant.permissions"), self._open_permissions,
                                     icon=ft.Icons.TUNE, data="ai-error-permissions"))
        tone = "info" if key == "cancelled" else "warning" if key in REFUSED else "danger"
        return wc.notice(ui, message, tone, actions=actions, data="ai-error")

    def _draft(self, entry, state: PanelState) -> ft.Control:
        ui = self.app.ui
        draft = state.draft
        style = tk.TYPE_BODY
        spans = [ft.TextSpan(piece, style=ft.TextStyle(
                     bgcolor=ui.p.warning_subtle, color=ui.p.warning, weight=ft.FontWeight.W_700,
                     decoration=ft.TextDecoration.UNDERLINE)) if flagged else ft.TextSpan(piece)
                 for piece, flagged in ai_assist.highlight(draft.text, draft.unverified)]
        body = ft.Text(spans=spans, size=style[0], color=ui.p.text, selectable=True,
                       style=ft.TextStyle(height=style[1] / style[0]),
                       semantics_label=draft.text, data="ai-draft-text")
        when = _local(draft.at)
        meta = ui.t("assistant.draft_meta", task=ui.t(f"assistant.task.{draft.task}"),
                    provider=_provider_name(draft.provider), model=draft.model, time=when,
                    tokens=draft.tokens)
        if draft.unverified:
            check = wc.notice(ui, ui.t("assistant.unverified", numbers=", ".join(draft.unverified)),
                              "warning", title=ui.t("assistant.unverified_title"),
                              data="ai-unverified")
        else:
            check = wc.notice(ui, ui.t("assistant.verified"), "info", data="ai-unverified")
        copy = wc.button(ui, ui.t("assistant.copy"), icon=ft.Icons.CONTENT_COPY,
                         action=ft.CopyToClipboard(draft.text), data="ai-copy")
        copy.on_click = lambda e, i=entry.id: self._copied(i)
        return wc.card(ui, [
            ft.Row([wc.chip(ui, ui.t("assistant.draft"), "warning", icon=ft.Icons.EDIT_NOTE,
                            data="ai-draft-chip")], wrap=True),
            wc.caption(ui, meta, data="ai-draft-meta"),
            body,
            check,
        ], actions=[
            copy,
            wc.button(ui, ui.t("assistant.use_note"), lambda e, i=entry.id: self._use_note(i),
                      kind="primary", icon=ft.Icons.NOTE_ADD_OUTLINED, disabled=state.used,
                      data="ai-use-note"),
            wc.button(ui, ui.t("assistant.discard"), lambda e, i=entry.id: self._discard(i),
                      kind="quiet", icon=ft.Icons.DELETE_OUTLINE, data="ai-discard"),
        ], border=ui.p.warning, data="ai-draft")

    # ----------------------------------------------------------- actions
    def _set_task(self, entry_id: int, value):
        state = self.state(entry_id)
        if not state.busy and value in ai_assist.TASKS:
            state.task, state.notice = value, None
        self.app.render()

    def _set_depth(self, entry_id: int, value: str):
        state = self.state(entry_id)
        if not state.busy and value in ai_assist.DEPTHS:
            state.depth = value
        self.app.render()

    def _set_question(self, entry_id: int, value: str):
        """Typing does not re-render; the preview follows when the field is
        left, and Send refuses a text that differs from the preview."""
        state = self.state(entry_id)
        if not state.busy:
            state.question = value[:ai_assist.MAX_QUESTION_CHARS]

    def _toggle_source(self, entry_id: int, key: str, value: bool):
        state = self.state(entry_id)
        if not state.busy:
            (state.sources.add if value else state.sources.discard)(key)
        self.app.render()

    def _open_settings(self, e=None):
        self.app.navigate("settings")

    def _open_permissions(self, e=None):
        self.app.navigate("settings", section="ai")

    async def _send_ai_request(self, entry_id: int):
        """Send exactly the previewed request; the click is the consent."""
        app = self.app
        entry, state = app.session.result(entry_id), self.state(entry_id)
        if entry is None or state.busy:
            return
        state.notice = None
        setup = ai_context.readiness(self.data_root)
        if not setup.ready:
            state.error = ("not_ready", {})
            app.render()
            return
        try:
            request = self.request(entry, state)
        except ai_context.ContextRefused as refused:
            state.error = (refused.codes[0] if refused.codes else "unknown", {})
            app.render()
            return
        shown = self.previewed.get(entry_id)
        if shown is None or shown.prompt != request.prompt:
            # Something changed after the preview was drawn: show it first.
            state.notice = (app.t("assistant.preview_changed"), "warning")
            app.render()
            return
        state.busy, state.error, state.draft, state.used = True, None, None, False
        state.cancel = cancel = threading.Event()
        state.ticket = ticket = next(self._tickets)
        generation = app.projects.generation
        project = self.project()
        app.render()
        draft, error = None, None
        try:
            draft = await asyncio.to_thread(self._exchange, request, setup, project, cancel)
        except ai_providers.ProviderError as failure:
            error = (failure.reason, self._values(failure.reason, setup, request, project))
        except ai_context.ContextRefused as refused:
            code = refused.codes[0] if refused.codes else "unknown"
            error = (code, self._values(code, setup, request, project))
        except (secret_store.SecretStoreUnavailable, OSError):
            error = ("no_store", {})
        except Exception:
            error = ("unknown", {})
        if state.ticket != ticket:
            return       # cancelled or replaced: whatever came back is not shown
        state.busy, state.cancel = False, None
        if app.projects.generation != generation:
            draft, error = None, None            # another project is open now
        state.error, state.draft = error, draft
        if draft is not None and not draft.logged:
            state.notice = (app.t("assistant.not_logged"), "warning")
        app.render()

    def _exchange(self, request, setup, project, cancel) -> ai_assist.Draft:
        """In a worker thread: read the key and send (never on the event loop)."""
        key = secret_store.get_key(setup.provider)
        if not key:
            raise ai_context.ContextRefused("No key is stored for this provider.", ("not_ready",))
        budget = ai_providers.Budget(ai_providers.usage_path(self.data_root), setup.daily_tokens)
        return ai_assist.send(request, setup=setup, key=key, project=project,
                              data_root=self.data_root, budget=budget, cancel=cancel, **self.http)

    def _values(self, code: str, setup, request, project) -> dict:
        """The figures an error message names."""
        if code == "budget":
            budget = ai_providers.Budget(ai_providers.usage_path(self.data_root),
                                         setup.daily_tokens)
            return {"used": budget.used(), "limit": setup.daily_tokens,
                    "needed": request.tokens + request.reply_tokens}
        if code in ("not_allowed", "unknown_source") and project is not None:
            labels = {source.key: self.app.t(source.label) for source in ai_context.SOURCES}
            decided = ai_context.permissions(project)
            refused = [labels.get(key, key) for key in request.sources if not decided.get(key)]
            return {"sources": ", ".join(refused) or "—"}
        return {}

    def _cancel_ai_request(self, entry_id: int):
        state = self.state(entry_id)
        if not state.busy:
            return
        if state.cancel is not None:
            state.cancel.set()
        state.busy, state.cancel, state.ticket = False, None, 0
        state.error = ("cancelled", {})
        self.app.render()

    def _copied(self, entry_id: int):
        self.state(entry_id).notice = (self.app.t("assistant.copied"), "success")
        self.app.render()

    def _use_note(self, entry_id: int):
        """Add the draft to the researcher's own note, labelled as an
        unverified AI draft; the result itself is not touched."""
        app, state = self.app, self.state(entry_id)
        draft = state.draft
        if draft is None or state.used:
            return
        label = app.t("assistant.note_label", provider=_provider_name(draft.provider),
                      model=draft.model, time=_local(draft.at))
        lines = [label]
        if draft.unverified:
            lines.append(app.t("assistant.note_unverified", numbers=", ".join(draft.unverified)))
        lines.append(draft.text)
        current = self.results.notes.get(entry_id, "").rstrip()
        note = (current + "\n\n" if current else "") + "\n".join(lines)
        if len(note) > NOTE_LIMIT:
            state.notice = (app.t("assistant.note_too_long", limit=NOTE_LIMIT), "warning")
            app.render()
            return
        self.results.notes[entry_id] = note
        self.results.opened.add(f"interpretation-{entry_id}")
        state.used = True
        state.notice = (app.t("assistant.note_added"), "success")
        app.render()

    def _discard(self, entry_id: int):
        state = self.state(entry_id)
        state.draft, state.used, state.notice = None, False, None
        self.app.render()


def _provider_name(provider: str) -> str:
    info = ai_providers.PROVIDERS.get(provider)
    return info.name if info else provider


def _local(stamp: str) -> str:
    try:
        return f"{datetime.fromisoformat(stamp).astimezone():%Y-%m-%d %H:%M}"
    except ValueError:
        return stamp
