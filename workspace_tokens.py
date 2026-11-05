"""Stage 33 design tokens: colour, type, spacing, shape and layout sizes.

One source of truth for the research workspace. Components never invent
colours or sizes; they read a resolved :class:`Palette` and the constants
below. ``tests/test_workspace_tokens.py`` checks WCAG 2.1 contrast for every
text/background pair in both themes, so a token change that hurts
readability fails CI.

Typography deliberately sets no font family: Flutter then uses the
platform UI font (Segoe UI on Windows, the system font on macOS) and its
own open fallback elsewhere. No proprietary font files are shipped.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import flet as ft

# ----------------------------------------------------------------- spacing
# 4-px base grid; layouts use the 8-px steps.
SPACE_1, SPACE_2, SPACE_3, SPACE_4 = 4, 8, 12, 16
SPACE_5, SPACE_6, SPACE_7, SPACE_8 = 24, 32, 40, 48

# ------------------------------------------------------------------- shape
RADIUS_CONTROL = 6   # buttons, inputs, chips
RADIUS_CARD = 8      # cards, list items, panes
RADIUS_DIALOG = 12   # dialogs, large surfaces

# ------------------------------------------------------------------ layout
SIDEBAR_EXPANDED = 232
SIDEBAR_COLLAPSED = 64
CONTEXT_BAR_HEIGHT = 56
CONTROL_HEIGHT = 40          # minimum interactive height (pointer + touch)
CONTENT_MAX_WIDTH = 1240     # forms, cards and reading pages
READING_MAX_WIDTH = 760      # long prose (~72 characters per line)
PANE_LIST_WIDTH = 300        # three-pane list column
PANE_PREVIEW_WIDTH = 380     # three-pane preview column
BREAKPOINT_COMPACT = 1280    # 1024–1279: compact laptop
BREAKPOINT_NARROW = 1024     # < 1024: narrow window / tablet

# -------------------------------------------------------------- typography
# (size, line height, weight). Helper text never goes below 12 px.
TYPE_DISPLAY = (28, 36, ft.FontWeight.W_600)
TYPE_TITLE_L = (24, 32, ft.FontWeight.W_600)
TYPE_TITLE_M = (20, 28, ft.FontWeight.W_600)
TYPE_TITLE_S = (16, 24, ft.FontWeight.W_600)
TYPE_BODY_L = (15, 24, ft.FontWeight.W_400)   # interpretations, reading text
TYPE_BODY = (14, 20, ft.FontWeight.W_400)
TYPE_LABEL = (13, 18, ft.FontWeight.W_500)
TYPE_CAPTION = (12, 16, ft.FontWeight.W_400)
MIN_TEXT_SIZE = 12


@dataclass(frozen=True)
class Palette:
    """Resolved colours for one theme. Every text role is contrast-tested."""

    mode: str
    canvas: str            # window background
    surface: str           # cards, panes
    surface_alt: str       # sidebar, table headers, subtle fills
    surface_hover: str
    border: str            # dividers, card strokes
    border_strong: str     # input outlines, focus-adjacent strokes
    text: str              # primary text
    text_secondary: str    # supporting text
    text_muted: str        # captions, placeholders (still AA)
    accent: str            # primary actions, links, selection
    accent_hover: str
    on_accent: str
    accent_subtle: str     # selected nav item, info background
    on_accent_subtle: str
    success: str
    success_subtle: str
    warning: str
    warning_subtle: str
    danger: str
    danger_subtle: str
    focus: str             # keyboard focus ring
    scrim: str

    def as_dict(self) -> dict[str, str]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


LIGHT = Palette(
    mode="light",
    canvas="#F6F7F9", surface="#FFFFFF", surface_alt="#F0F2F5",
    surface_hover="#E9EDF2", border="#E1E5EB", border_strong="#767F8F",
    text="#1A202C", text_secondary="#404A5A", text_muted="#5B6676",
    accent="#1F5BC4", accent_hover="#1A4EA8", on_accent="#FFFFFF",
    accent_subtle="#E7EEFB", on_accent_subtle="#173F86",
    success="#1C7240", success_subtle="#E5F3EA",
    warning="#8A5300", warning_subtle="#FDF1DC",
    danger="#B42318", danger_subtle="#FCE9E7",
    focus="#1F5BC4", scrim="#000000",
)

DARK = Palette(
    mode="dark",
    canvas="#14171C", surface="#1C2027", surface_alt="#232831",
    surface_hover="#2B313B", border="#323944", border_strong="#78849A",
    text="#E7EAF0", text_secondary="#C0C7D2", text_muted="#9DA7B6",
    accent="#8AB0F7", accent_hover="#A3C1F9", on_accent="#0E1830",
    accent_subtle="#22314D", on_accent_subtle="#CFDDFB",
    success="#74C996", success_subtle="#1D3327",
    warning="#E9B95C", warning_subtle="#3A2E17",
    danger="#F2958B", danger_subtle="#3D2220",
    focus="#8AB0F7", scrim="#000000",
)

PALETTES = {"light": LIGHT, "dark": DARK}

# Text-on-background pairs that must meet WCAG AA (4.5:1 normal text).
TEXT_PAIRS = (
    ("text", "canvas"), ("text", "surface"), ("text", "surface_alt"),
    ("text", "surface_hover"),
    ("text_secondary", "canvas"), ("text_secondary", "surface"),
    ("text_secondary", "surface_alt"),
    ("text_muted", "canvas"), ("text_muted", "surface"), ("text_muted", "surface_alt"),
    ("on_accent", "accent"), ("on_accent", "accent_hover"),
    ("on_accent_subtle", "accent_subtle"), ("accent", "surface"), ("accent", "canvas"),
    ("text", "accent_subtle"),
    ("success", "success_subtle"), ("success", "surface"),
    ("warning", "warning_subtle"), ("warning", "surface"),
    ("danger", "danger_subtle"), ("danger", "surface"),
    ("text", "success_subtle"), ("text", "warning_subtle"), ("text", "danger_subtle"),
)
# Non-text UI components (input outlines, focus ring) need 3:1 (WCAG 1.4.11).
UI_PAIRS = (
    ("border_strong", "surface"), ("border_strong", "canvas"),
    ("focus", "surface"), ("focus", "canvas"), ("accent", "surface_alt"),
)


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def palette(mode: str) -> Palette:
    return PALETTES.get(mode, LIGHT)


def text_style(token, color: str | None = None) -> ft.TextStyle:
    size, height, weight = token
    return ft.TextStyle(size=size, height=height / size, weight=weight, color=color)


def _color_scheme(p: Palette) -> ft.ColorScheme:
    return ft.ColorScheme(
        primary=p.accent, on_primary=p.on_accent,
        primary_container=p.accent_subtle, on_primary_container=p.on_accent_subtle,
        secondary=p.accent, on_secondary=p.on_accent,
        secondary_container=p.accent_subtle, on_secondary_container=p.on_accent_subtle,
        error=p.danger, on_error=p.surface,
        error_container=p.danger_subtle, on_error_container=p.danger,
        surface=p.surface, on_surface=p.text,
        on_surface_variant=p.text_secondary,
        surface_container_lowest=p.surface, surface_container_low=p.surface,
        surface_container=p.surface_alt, surface_container_high=p.surface_alt,
        surface_container_highest=p.surface_hover,
        outline=p.border_strong, outline_variant=p.border,
        shadow="#000000", scrim=p.scrim,
        inverse_surface=p.text, on_inverse_surface=p.surface,
        inverse_primary=p.accent_subtle, surface_tint=p.surface,
    )


def build_theme(mode: str) -> ft.Theme:
    """Material 3 theme whose colour roles are the Stage 33 tokens."""
    p = palette(mode)
    return ft.Theme(
        color_scheme=_color_scheme(p),
        use_material3=True,
        visual_density=ft.VisualDensity.STANDARD,
        focus_color=ft.Colors.with_opacity(0.18, p.focus),
        hover_color=ft.Colors.with_opacity(0.06, p.text),
        divider_theme=ft.DividerTheme(color=p.border, thickness=1, space=1),
        scrollbar_theme=ft.ScrollbarTheme(thickness=8, radius=4),
        tooltip_theme=ft.TooltipTheme(
            text_style=ft.TextStyle(size=12, color=p.surface),
            wait_duration=400,
        ),
    )
