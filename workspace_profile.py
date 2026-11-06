"""Settings: the optional researcher profile and the AI context overview
(Stage 34, part C). See ``researcher_profile`` and ``ai_context``."""

from __future__ import annotations

from dataclasses import replace

import flet as ft

import ai_context
import workspace_components as wc
import workspace_tokens as tk
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
        app, ui = self.app, self.app.ui
        binding = app.projects
        project = binding.project if binding.active else None
        rows: list[ft.Control] = []
        decided = ai_context.permissions(project) if project is not None else {}
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
                text = ai_context.preview(source.key, project=project, session=app.session,
                                          profile=app.profile, survey_root=app.survey_root)
                block.append(wc.expansion(
                    ui, wc.text(ui, ui.t("ai.preview"), tk.TYPE_BODY),
                    [ft.Container(wc.text(
                        ui, text or ui.t("ai.preview_empty"), tk.TYPE_BODY, selectable=True,
                        color=ui.p.text if text else ui.p.text_secondary,
                        data=f"ai-preview-{source.key}"), padding=tk.SPACE_3)],
                    key=f"ai-preview-tile-{source.key}", opened=self.opened))
            rows.append(ft.Container(ft.Column(block, spacing=tk.SPACE_2), padding=tk.SPACE_3,
                                     border=ft.Border.all(1, ui.p.border),
                                     border_radius=ui.radius("card")))
        content: list[ft.Control] = [
            ft.Row([wc.chip(ui, ui.t("ai.unavailable"), "neutral", icon=ft.Icons.BLOCK,
                            data="ai-unavailable")]),
            wc.text(ui, ui.t("ai.intro"), tk.TYPE_BODY),
            wc.section_label(ui, ui.t("ai.sources", title=binding.info().title)
                             if project is not None else ui.t("ai.sources_none")),
            *rows,
        ]
        if project is None:
            content.append(wc.caption(ui, ui.t("ai.no_project")))
        content += [wc.text(ui, "• " + ui.t(f"ai.rule.{rule}"), tk.TYPE_BODY,
                            color=ui.p.text_secondary)
                    for rule in ("consent", "rows", "log", "profile")]
        return wc.card(ui, content, title=ui.t("settings.ai"), data="settings-ai")
