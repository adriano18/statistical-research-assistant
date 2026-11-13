"""Settings: the optional researcher profile and what the AI assistant may
see in the open project (Stage 34, part C; switches since Stage 36). See
``researcher_profile`` and ``ai_context``."""

from __future__ import annotations

from dataclasses import replace

import flet as ft

import ai_context
import workspace_components as wc
import workspace_tokens as tk
from project_store import ProjectError
from researcher_profile import (
    EXPERIENCE, EXPLANATIONS, LANGUAGES, STUDY_LEVELS, ProfileError, ResearcherProfile,
    delete_profile, save_profile,
)

UNSET = "none"     # dropdown key for "not set" (an empty key is not a valid option)
LANGUAGE_NAMES = {"en": "English", "lv": "Latviešu", "ru": "Русский"}


class ProfileSettings:
    """The profile form and the AI overview on the Settings page."""

    def __init__(self, app):
        self.app = app
        self.draft = app.profile
        self.feedback: tuple[str, str] | None = None
        self.ai_feedback: tuple[str, str] | None = None
        self.opened: set[str] = set()

    # ---------------------------------------------------------- profile
    def profile_card(self) -> ft.Control:
        ui, draft = self.app.ui, self.draft

        def choice(field: str, values, prefix: str, label: str, width: int = 320):
            options = [(value or UNSET, ui.t(f"{prefix}.{value or UNSET}") if prefix
                        else LANGUAGE_NAMES.get(value) or ui.t("profile.lang.none"))
                       for value in values]
            return wc.dropdown(ui, label, options, getattr(draft, field) or UNSET,
                               on_select=lambda e, f=field: self._set(f, e.control.value),
                               width=width, data=f"profile-{field.replace('_', '-')}")

        name = wc.text_field(ui, ui.t("profile.name"), draft.display_name, width=420,
                             on_change=lambda e: self._set("display_name", e.control.value),
                             data="profile-name")
        research_field = wc.text_field(ui, ui.t("profile.field"), draft.research_field,
                                       width=420, hint=ui.t("profile.field_hint"),
                                       on_change=lambda e: self._set("research_field",
                                                                     e.control.value),
                                       data="profile-field")
        content: list[ft.Control] = [
            wc.text(ui, ui.t("profile.intro", path=self.app.profile_path), tk.TYPE_BODY,
                    color=ui.p.text_secondary, selectable=True),
            name,
            choice("study_level", STUDY_LEVELS, "profile.level", ui.t("profile.study_level")),
            research_field,
            choice("experience", EXPERIENCE, "profile.exp", ui.t("profile.experience")),
            choice("language", LANGUAGES, "", ui.t("profile.language")),
            choice("explanations", EXPLANATIONS, "profile.expl", ui.t("profile.explanations")),
            wc.caption(ui, ui.t("profile.effects")),
        ]
        if self.feedback:
            content.append(wc.notice(ui, self.feedback[0], self.feedback[1],
                                     data="profile-feedback"))
        exists = self.app.profile_path.is_file()
        return wc.card(ui, content, title=ui.t("settings.profile"), actions=[
            wc.button(ui, ui.t("profile.save"), self.save, kind="primary",
                      icon=ft.Icons.SAVE_OUTLINED, data="profile-save"),
            wc.button(ui, ui.t("profile.delete"), self.delete, kind="quiet",
                      icon=ft.Icons.DELETE_OUTLINE, disabled=not exists, data="profile-delete"),
        ], data="settings-profile")

    def _set(self, field: str, value):
        value = "" if value in (None, UNSET) else str(value)
        self.draft = replace(self.draft, **{field: value})

    def save(self, e=None):
        app = self.app
        try:
            profile = save_profile(app.profile_path, self.draft)
        except ProfileError as error:
            self.feedback = (app.t("profile.invalid", error=error), "warning")
            app.render()
            return
        except OSError as error:
            self.feedback = (app.t("profile.invalid", error=error), "danger")
            app.render()
            return
        app.profile = self.draft = profile
        self.feedback = (app.t("profile.empty_saved" if profile.empty else "profile.saved"),
                         "success")
        if profile.language and profile.language != app.session.language:
            app.set_language(profile.language)      # also renders
            return
        app.render()

    def delete(self, e=None):
        app = self.app
        delete_profile(app.profile_path)
        app.profile = self.draft = ResearcherProfile()
        self.feedback = (app.t("profile.deleted"), "success")
        app.render()

    # --------------------------------------------------------------- AI
    def ai_card(self) -> ft.Control:
        """What the assistant may see in the open project: one switch per
        source (all off by default) and the statement that the data rows
        identify nobody, without which data rows cannot be allowed."""
        app, ui = self.app, self.app.ui
        binding = app.projects
        project = binding.project if binding.active else None
        rows: list[ft.Control] = []
        decided = ai_context.permissions(project) if project is not None else {}
        anonymous = project.data_anonymous if project is not None else False
        for source in ai_context.SOURCES:
            allowed = decided.get(source.key, False)
            heading = ft.Row([
                ft.Column([wc.text(ui, ui.t(source.label), tk.TYPE_LABEL, weight=ft.FontWeight.W_600),
                           wc.caption(ui, ui.t(source.detail))], spacing=2, expand=True),
                wc.chip(ui, ui.t("ai.on" if allowed else "ai.off"),
                        "warning" if allowed else "neutral",
                        icon=ft.Icons.TOGGLE_ON_OUTLINED if allowed else ft.Icons.TOGGLE_OFF_OUTLINED,
                        data=f"ai-status-{source.key}"),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
            block: list[ft.Control] = [heading]
            if project is not None:
                locked = source.key == "raw_data" and not anonymous and not allowed
                block.append(wc.checkbox(
                    ui, ui.t("ai.allow"), allowed, disabled=locked,
                    on_change=lambda e, k=source.key: self._allow(k, bool(e.control.value)),
                    data=f"ai-allow-{source.key}"))
                if locked:
                    block.append(wc.caption(ui, ui.t("ai.rows_locked")))
                text = ai_context.preview(source.key, project=project, session=app.session,
                                          profile=app.profile, survey_root=app.survey_root)
                block.append(wc.expansion(
                    ui, wc.text(ui, ui.t("ai.preview"), tk.TYPE_BODY),
                    [ft.Container(wc.text(
                        ui, text or ui.t("ai.preview_empty"), tk.TYPE_BODY, selectable=True,
                        color=ui.p.text if text else ui.p.text_secondary,
                        data=f"ai-preview-{source.key}"), padding=tk.SPACE_3)],
                    key=f"ai-preview-tile-{source.key}", opened=self.opened))
                if source.key == "raw_data":
                    # Stage 37: what the data rows never contain, shown here too.
                    left_out = ai_context.excluded_columns(app.session)
                    if left_out:
                        from workspace_assistant import excluded_text

                        block.append(wc.caption(
                            ui, ui.t("ai.excluded", columns=excluded_text(ui, left_out)),
                            data="ai-excluded-raw_data"))
            rows.append(ft.Container(ft.Column(block, spacing=tk.SPACE_2), padding=tk.SPACE_3,
                                     border=ft.Border.all(1, ui.p.border),
                                     border_radius=ui.radius("card")))
        setup = ai_context.readiness(app.project_root.parent)
        status = (wc.chip(ui, ui.t("ai.ready", provider=setup.provider_name, model=setup.model),
                          "success", icon=ft.Icons.CHECK_CIRCLE_OUTLINE, data="ai-ready")
                  if setup.ready else
                  wc.chip(ui, ui.t("ai.unavailable"), "neutral", icon=ft.Icons.BLOCK,
                          data="ai-unavailable"))
        content: list[ft.Control] = [
            ft.Row([status]),
            wc.text(ui, ui.t("ai.intro"), tk.TYPE_BODY),
            wc.section_label(ui, ui.t("ai.sources", title=binding.info().title)
                             if project is not None else ui.t("ai.sources_none")),
            *rows,
        ]
        if project is None:
            content.append(wc.caption(ui, ui.t("ai.no_project")))
        else:
            content += [wc.checkbox(ui, ui.t("ai.anonymous"), anonymous,
                                    on_change=lambda e: self._anonymous(bool(e.control.value)),
                                    data="ai-anonymous"),
                        wc.caption(ui, ui.t("ai.anonymous_note"))]
        if self.ai_feedback:
            content.append(wc.notice(ui, self.ai_feedback[0], self.ai_feedback[1],
                                     data="ai-feedback"))
        content += [wc.text(ui, "• " + ui.t(f"ai.rule.{rule}"), tk.TYPE_BODY,
                            color=ui.p.text_secondary)
                    for rule in ("consent", "rows", "log", "profile")]
        card = wc.card(ui, content, title=ui.t("settings.ai"), data="settings-ai")
        card.key = ft.ScrollKey("settings-ai")    # the assistant's "AI permissions" link
        return card

    def _allow(self, source: str, allowed: bool):
        """One source on or off for the open project (stored and logged there)."""
        binding = self.app.projects
        self.ai_feedback = None
        if binding.active:
            try:
                ai_context.allow(binding.project, source, allowed, remote=True)
            except ai_context.ContextRefused:
                self.ai_feedback = (self.app.t("ai.rows_locked"), "warning")
            except ProjectError as error:
                self.ai_feedback = (self.app.t("profile.invalid", error=error), "danger")
        self.app.render()

    def _anonymous(self, value: bool):
        """The researcher's statement that the data rows identify nobody;
        withdrawing it withdraws data rows too."""
        binding = self.app.projects
        self.ai_feedback = None
        if binding.active:
            try:
                ai_context.state_anonymous(binding.project, value)
            except ProjectError as error:
                self.ai_feedback = (self.app.t("profile.invalid", error=error), "danger")
        self.app.render()
