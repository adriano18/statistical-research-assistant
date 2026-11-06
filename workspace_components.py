"""Reusable Stage 33 components built only from design tokens.

Rules every component follows (docs/UX_STAGE33_SPEC.md §7):

* colours come from the resolved :class:`workspace_tokens.Palette`;
* text sizes come from the type scale and are never below 12 px;
* icon-only buttons always carry a tooltip (screen-reader label);
* status is never shown by colour alone — tone chips have an icon and text;
* headings are sentence case, never all caps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import flet as ft

import workspace_tokens as tk
from workspace_text import t as translate


@dataclass
class Ui:
    """Rendering context: palette, language and corner style."""

    palette: tk.Palette
    language: str = "en"
    corners: str = "windows"

    def t(self, key: str, **values) -> str:
        return translate(self.language, key, **values)

    @property
    def p(self) -> tk.Palette:
        return self.palette

    def radius(self, kind: str = "card") -> int:
        base = {"control": tk.RADIUS_CONTROL, "card": tk.RADIUS_CARD,
                "dialog": tk.RADIUS_DIALOG}[kind]
        return base + (2 if self.corners == "macos" else 0)


TONES = {
    "neutral": ("surface_alt", "text_secondary", ft.Icons.INFO_OUTLINE),
    "info": ("accent_subtle", "on_accent_subtle", ft.Icons.INFO_OUTLINE),
    "success": ("success_subtle", "success", ft.Icons.CHECK_CIRCLE_OUTLINE),
    "warning": ("warning_subtle", "warning", ft.Icons.WARNING_AMBER_ROUNDED),
    "danger": ("danger_subtle", "danger", ft.Icons.ERROR_OUTLINE),
}


def text(ui: Ui, value: str, kind=tk.TYPE_BODY, *, color: str | None = None,
         selectable: bool = False, max_lines: int | None = None,
         weight=None, italic: bool = False, data=None, align=None) -> ft.Text:
    size, height, default_weight = kind
    return ft.Text(
        value, size=size, weight=weight or default_weight,
        color=color or ui.p.text, selectable=selectable, max_lines=max_lines,
        overflow=ft.TextOverflow.ELLIPSIS if max_lines else None,
        style=ft.TextStyle(height=height / size, italic=italic),
        data=data, text_align=align,
    )


def heading(ui: Ui, value: str, kind=tk.TYPE_TITLE_S, **kwargs) -> ft.Text:
    return text(ui, value, kind, **kwargs)


def caption(ui: Ui, value: str, **kwargs) -> ft.Text:
    return text(ui, value, tk.TYPE_CAPTION, color=kwargs.pop("color", ui.p.text_muted), **kwargs)


def _button_style(ui: Ui, *, kind: str) -> ft.ButtonStyle:
    shape = ft.RoundedRectangleBorder(radius=ui.radius("control"))
    padding = ft.Padding.symmetric(horizontal=tk.SPACE_4, vertical=tk.SPACE_2)
    text_style = ft.TextStyle(size=14, weight=ft.FontWeight.W_500)
    if kind == "primary":
        return ft.ButtonStyle(
            bgcolor={ft.ControlState.DEFAULT: ui.p.accent,
                     ft.ControlState.HOVERED: ui.p.accent_hover,
                     ft.ControlState.DISABLED: ui.p.surface_hover},
            color={ft.ControlState.DEFAULT: ui.p.on_accent,
                   ft.ControlState.DISABLED: ui.p.text_muted},
            shape=shape, padding=padding, elevation=0, text_style=text_style,
        )
    if kind == "secondary":
        return ft.ButtonStyle(
            bgcolor={ft.ControlState.DEFAULT: ui.p.surface,
                     ft.ControlState.HOVERED: ui.p.surface_hover},
            color={ft.ControlState.DEFAULT: ui.p.text,
                   ft.ControlState.DISABLED: ui.p.text_muted},
            side=ft.BorderSide(1, ui.p.border_strong),
            shape=shape, padding=padding, elevation=0, text_style=text_style,
        )
    return ft.ButtonStyle(  # quiet
        color={ft.ControlState.DEFAULT: ui.p.accent,
               ft.ControlState.DISABLED: ui.p.text_muted},
        overlay_color=ft.Colors.with_opacity(0.08, ui.p.accent),
        shape=shape, padding=padding, text_style=text_style,
    )


def button(ui: Ui, label: str, on_click=None, *, kind: str = "secondary",
           icon=None, tooltip: str | None = None, disabled: bool = False,
           action=None, data=None, key=None) -> ft.Control:
    kwargs = dict(content=label, icon=icon, style=_button_style(ui, kind=kind),
                  tooltip=tooltip, disabled=disabled, height=tk.CONTROL_HEIGHT,
                  data=data)
    if key is not None:
        kwargs["key"] = key
    if action is not None:
        kwargs["action"] = action
    else:
        kwargs["on_click"] = on_click
    if kind == "quiet":
        return ft.TextButton(**kwargs)
    return ft.Button(**kwargs)


def icon_button(ui: Ui, icon, tooltip: str, on_click=None, *, selected: bool = False,
                data=None, disabled: bool = False) -> ft.IconButton:
    if not tooltip:
        raise ValueError("Icon-only buttons need a tooltip (accessible name).")
    return ft.IconButton(
        icon=icon, tooltip=tooltip, on_click=on_click, data=data, disabled=disabled,
        icon_color=ui.p.accent if selected else ui.p.text_secondary,
        icon_size=20, width=tk.CONTROL_HEIGHT, height=tk.CONTROL_HEIGHT,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=ui.radius("control"))),
    )


def chip(ui: Ui, label: str, tone: str = "neutral", *, icon=None,
         tooltip: str | None = None, on_click=None, data=None) -> ft.Container:
    bg, fg, default_icon = TONES[tone]
    return ft.Container(
        content=ft.Row(
            [ft.Icon(icon or default_icon, size=16, color=getattr(ui.p, fg)),
             text(ui, label, tk.TYPE_LABEL, color=getattr(ui.p, fg) if tone != "neutral"
                  else ui.p.text_secondary)],
            spacing=tk.SPACE_1, tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=getattr(ui.p, bg), border_radius=ui.radius("control"),
        padding=ft.Padding.symmetric(horizontal=tk.SPACE_2 + 2, vertical=tk.SPACE_1 + 2),
        tooltip=tooltip, on_click=on_click, data=data,
        ink=on_click is not None,
    )


def notice(ui: Ui, message: str, tone: str = "info", *, title: str | None = None,
           actions: Iterable[ft.Control] = (), data=None) -> ft.Container:
    bg, fg, icon = TONES[tone]
    body: list[ft.Control] = []
    if title:
        body.append(text(ui, title, tk.TYPE_LABEL, weight=ft.FontWeight.W_600))
    body.append(text(ui, message, tk.TYPE_BODY, selectable=True))
    actions = list(actions)
    if actions:
        body.append(ft.Row(actions, wrap=True, spacing=tk.SPACE_2))
    return ft.Container(
        content=ft.Row(
            [ft.Icon(icon, color=getattr(ui.p, fg), size=20),
             ft.Column(body, spacing=tk.SPACE_1, expand=True)],
            vertical_alignment=ft.CrossAxisAlignment.START, spacing=tk.SPACE_3,
        ),
        bgcolor=getattr(ui.p, bg), border_radius=ui.radius("card"),
        padding=tk.SPACE_4, data=data,
    )


def card(ui: Ui, content: list[ft.Control], *, title: str | None = None,
         description: str | None = None, actions: Iterable[ft.Control] = (),
         padding: int = tk.SPACE_5, expand=None, col=None, data=None,
         bgcolor: str | None = None, border: str | None = None) -> ft.Container:
    body: list[ft.Control] = []
    if title:
        body.append(heading(ui, title, tk.TYPE_TITLE_S))
    if description:
        body.append(text(ui, description, tk.TYPE_BODY, color=ui.p.text_secondary))
    body.extend(content)
    actions = list(actions)
    if actions:
        body.append(ft.Row(actions, wrap=True, spacing=tk.SPACE_2))
    return ft.Container(
        content=ft.Column(body, spacing=tk.SPACE_3, tight=True),
        bgcolor=bgcolor or ui.p.surface, border=ft.Border.all(1, border or ui.p.border),
        border_radius=ui.radius("card"), padding=padding, expand=expand,
        col=col, data=data,
    )


def page_header(ui: Ui, title: str, subtitle: str | None = None, *,
                actions: Iterable[ft.Control] = (), badge: ft.Control | None = None) -> ft.Control:
    left = [ft.Row([heading(ui, title, tk.TYPE_TITLE_L)] + ([badge] if badge else []),
                   spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                   wrap=True)]
    if subtitle:
        left.append(text(ui, subtitle, tk.TYPE_BODY_L, color=ui.p.text_secondary))
    return ft.Row(
        [ft.Column(left, spacing=tk.SPACE_1, expand=True),
         ft.Row(list(actions), spacing=tk.SPACE_2)],
        vertical_alignment=ft.CrossAxisAlignment.START,
    )


def empty_state(ui: Ui, icon, title: str, body: str,
                actions: Iterable[ft.Control] = (), data=None) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [ft.Icon(icon, size=40, color=ui.p.text_muted),
             heading(ui, title, tk.TYPE_TITLE_S, align=ft.TextAlign.CENTER),
             text(ui, body, tk.TYPE_BODY, color=ui.p.text_secondary, align=ft.TextAlign.CENTER),
             ft.Row(list(actions), alignment=ft.MainAxisAlignment.CENTER, wrap=True,
                    spacing=tk.SPACE_2)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=tk.SPACE_3,
            tight=True,
        ),
        padding=tk.SPACE_7, alignment=ft.Alignment.CENTER, data=data,
        border=ft.Border.all(1, ui.p.border), border_radius=ui.radius("card"),
        bgcolor=ui.p.surface,
    )


def action_tile(ui: Ui, icon, title: str, body: str, button_label: str, *,
                on_click=None, action=None, primary: bool = False, data=None,
                col=None) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [ft.Container(ft.Icon(icon, size=24, color=ui.p.accent),
                          bgcolor=ui.p.accent_subtle, border_radius=ui.radius("control"),
                          padding=tk.SPACE_2, width=40, height=40,
                          alignment=ft.Alignment.CENTER),
             heading(ui, title, tk.TYPE_TITLE_S),
             text(ui, body, tk.TYPE_BODY, color=ui.p.text_secondary),
             ft.Container(height=tk.SPACE_1),
             button(ui, button_label, on_click, action=action,
                    kind="primary" if primary else "secondary", data=data)],
            spacing=tk.SPACE_3, tight=True,
        ),
        bgcolor=ui.p.surface, border=ft.Border.all(1, ui.p.border),
        border_radius=ui.radius("card"), padding=tk.SPACE_5, col=col,
        data=f"{data}-tile" if data else None,
    )


def stat(ui: Ui, label: str, value: str, detail: str = "", *, col=None) -> ft.Container:
    controls = [caption(ui, label), text(ui, value, tk.TYPE_TITLE_M, selectable=True)]
    if detail:
        controls.append(caption(ui, detail, selectable=True))
    return ft.Container(
        content=ft.Column(controls, spacing=2, tight=True),
        bgcolor=ui.p.surface_alt, border_radius=ui.radius("card"),
        padding=ft.Padding.symmetric(horizontal=tk.SPACE_4, vertical=tk.SPACE_3),
        col=col,
    )


def labeled(ui: Ui, label: str, value: str) -> ft.Row:
    return ft.Row(
        [ft.Container(caption(ui, label), width=150),
         ft.Container(text(ui, value, tk.TYPE_BODY, selectable=True), expand=True)],
        vertical_alignment=ft.CrossAxisAlignment.START, spacing=tk.SPACE_3,
    )


def apa_table(ui: Ui, columns: tuple[str, ...], rows: tuple[tuple[str, ...], ...], *,
              title: str = "", number: int | None = None, note: str = "",
              hide: tuple[str, ...] = ("Sig.",)) -> ft.Control:
    """APA 7 style: number, italic title, horizontal rules only."""
    keep = [i for i, name in enumerate(columns) if name not in hide]
    table = ft.DataTable(
        columns=[ft.DataColumn(text(ui, columns[i], tk.TYPE_LABEL,
                                    weight=ft.FontWeight.W_600))
                 for i in keep],
        rows=[ft.DataRow(cells=[ft.DataCell(text(ui, row[i], tk.TYPE_BODY, selectable=True))
                                for i in keep]) for row in rows],
        heading_row_height=40, data_row_min_height=36, data_row_max_height=56,
        column_spacing=tk.SPACE_5, horizontal_margin=tk.SPACE_2,
        border=ft.Border(top=ft.BorderSide(1.5, ui.p.text), bottom=ft.BorderSide(1.5, ui.p.text)),
        horizontal_lines=ft.BorderSide(0.5, ui.p.border),
        heading_row_color=ui.p.surface,
    )
    controls: list[ft.Control] = []
    if number is not None:
        controls.append(text(ui, f"Table {number}", tk.TYPE_LABEL, weight=ft.FontWeight.W_700))
    if title:
        controls.append(text(ui, title, tk.TYPE_BODY, italic=True))
    controls.append(ft.Row([table], scroll=ft.ScrollMode.AUTO))
    if note:
        controls.append(caption(ui, note))
    return ft.Column(controls, spacing=tk.SPACE_2)


def figure(ui: Ui, png: bytes, *, caption_text: str = "", on_enlarge=None,
           max_height: int = 460, enlarge_label: str = "") -> ft.Control:
    """Figure that scales to its container instead of a fixed pixel size."""
    image = ft.Image(src=png, fit=ft.BoxFit.CONTAIN, height=max_height,
                     semantics_label=caption_text or "Figure", gapless_playback=True)
    controls: list[ft.Control] = [
        ft.Container(image, bgcolor="#FFFFFF", border_radius=ui.radius("card"),
                     padding=tk.SPACE_2, border=ft.Border.all(1, ui.p.border),
                     alignment=ft.Alignment.CENTER),
    ]
    row = []
    if caption_text:
        row.append(ft.Container(caption(ui, caption_text), expand=True))
    if on_enlarge is not None:
        row.append(button(ui, enlarge_label or "Enlarge", on_enlarge, kind="quiet",
                          icon=ft.Icons.OPEN_IN_FULL))
    if row:
        controls.append(ft.Row(row, vertical_alignment=ft.CrossAxisAlignment.CENTER))
    return ft.Column(controls, spacing=tk.SPACE_2)


def step_card(ui: Ui, number: int, title: str, content: list[ft.Control], *,
              state: str = "active", summary: str = "", data=None) -> ft.Container:
    """Guided step: 'done' shows a summary, 'locked' explains what is missing."""
    marker_bg = {"done": ui.p.success_subtle, "active": ui.p.accent,
                 "locked": ui.p.surface_alt}[state]
    marker_fg = {"done": ui.p.success, "active": ui.p.on_accent,
                 "locked": ui.p.text_muted}[state]
    marker = ft.Container(
        content=(ft.Icon(ft.Icons.CHECK, size=16, color=marker_fg) if state == "done"
                 else text(ui, str(number), tk.TYPE_LABEL, color=marker_fg,
                           weight=ft.FontWeight.W_700)),
        width=28, height=28, border_radius=14, bgcolor=marker_bg,
        alignment=ft.Alignment.CENTER,
    )
    header = ft.Row([marker, heading(ui, title, tk.TYPE_TITLE_S,
                                     color=ui.p.text if state != "locked" else ui.p.text_muted)],
                    spacing=tk.SPACE_3, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    body: list[ft.Control] = [header]
    if summary:
        body.append(ft.Container(text(ui, summary, tk.TYPE_BODY, color=ui.p.text_secondary),
                                 padding=ft.Padding.only(left=40)))
    if content:
        body.append(ft.Container(ft.Column(content, spacing=tk.SPACE_3),
                                 padding=ft.Padding.only(left=40)))
    return ft.Container(
        content=ft.Column(body, spacing=tk.SPACE_3),
        bgcolor=ui.p.surface,
        border=ft.Border.all(1.5 if state == "active" else 1,
                             ui.p.accent if state == "active" else ui.p.border),
        border_radius=ui.radius("card"), padding=tk.SPACE_5, data=data,
    )


def segmented(ui: Ui, options: list[tuple[str, str]], value: str,
              on_change: Callable[[str], None], *, data=None,
              tooltips: dict[str, str] | None = None, compact: bool = False) -> ft.Control:
    """Accessible two-to-four way switch built from buttons (keyboard focusable)."""
    controls = []
    for key, label in options:
        selected = key == value
        controls.append(ft.Button(
            content=label, data=key, height=32 if compact else 36,
            on_click=lambda e, k=key: on_change(k),
            style=ft.ButtonStyle(
                bgcolor=ui.p.surface if selected else ui.p.surface_alt,
                color=ui.p.text if selected else ui.p.text_secondary,
                side=ft.BorderSide(1, ui.p.border_strong if selected else ui.p.surface_alt),
                shape=ft.RoundedRectangleBorder(radius=ui.radius("control")),
                elevation=0, text_style=ft.TextStyle(
                    size=14, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_500),
            ),
            tooltip=(tooltips or {}).get(key),
        ))
    return ft.Container(
        content=ft.Row(controls, spacing=tk.SPACE_1, tight=True),
        bgcolor=ui.p.surface_alt, border_radius=ui.radius("control") + 2,
        padding=3, data=data,
    )


def dropdown(ui: Ui, label: str, options: list[tuple[str, str]], value: str | None,
             on_select=None, *, width: int | None = 280, data=None,
             disabled: bool = False, tooltip: str | None = None) -> ft.Dropdown:
    return ft.Dropdown(
        label=label, value=value, width=width, data=data, disabled=disabled,
        options=[ft.DropdownOption(key=k, text=v) for k, v in options],
        on_select=on_select, border_radius=ui.radius("control"),
        border_color=ui.p.border_strong, focused_border_color=ui.p.focus,
        text_size=14, tooltip=tooltip, dense=False,
    )


def text_field(ui: Ui, label: str, value: str = "", *, width: int | None = None,
               multiline: bool = False, on_change=None, data=None, hint: str | None = None,
               expand=None) -> ft.TextField:
    return ft.TextField(
        label=label, value=value, width=width, multiline=multiline,
        min_lines=3 if multiline else None, max_lines=8 if multiline else 1,
        on_change=on_change, data=data, hint_text=hint, expand=expand,
        border_radius=ui.radius("control"), border_color=ui.p.border_strong,
        focused_border_color=ui.p.focus, text_size=14,
    )


def checkbox(ui: Ui, label: str, value: bool = False, on_change=None, *,
             data=None, disabled: bool = False) -> ft.Checkbox:
    return ft.Checkbox(
        label=label, value=value, on_change=on_change, data=data, disabled=disabled,
        label_style=ft.TextStyle(size=14, color=ui.p.text),
        active_color=ui.p.accent, check_color=ui.p.on_accent,
    )


def section_label(ui: Ui, value: str) -> ft.Text:
    return text(ui, value, tk.TYPE_LABEL, color=ui.p.text_secondary,
                weight=ft.FontWeight.W_600)


def divider(ui: Ui) -> ft.Divider:
    return ft.Divider(height=1, thickness=1, color=ui.p.border)


def constrained(content: ft.Control, max_width: int = tk.CONTENT_MAX_WIDTH) -> ft.Row:
    """Centre content with a maximum width (long lines stay readable)."""
    return ft.Row(
        [ft.Container(content, width=None, expand=True,
                      constraints=ft.BoxConstraints(max_width=max_width))],
        alignment=ft.MainAxisAlignment.CENTER,
    )
