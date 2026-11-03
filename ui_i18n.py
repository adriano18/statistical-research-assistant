"""Translate visible static Flet controls without touching scores or respondent data.

Labels, help hints, buttons and choice display text are localized. A TextField's
value, Dropdown.key and survey variable IDs remain immutable. The translator
remembers the original source string only while the control keeps that text;
dynamic analyses replacing a Text are never overwritten by a language change.
"""

from __future__ import annotations

from localization import LANGUAGES, TEXT, tr


class UITranslator:
    def __init__(self):
        self._sources: dict[tuple[int, str], str] = {}
        self._last_displayed: dict[tuple[int, str], str] = {}

    def _translate_property(self, control, field: str, language: str):
        try:
            current = getattr(control, field, None)
        except (AttributeError, TypeError):
            return
        if not isinstance(current, str):
            return
        identity = (id(control), field)
        original = self._sources.get(identity)
        previously = self._last_displayed.get(identity)
        if original is None:
            if current not in TEXT:
                return
            original = current
            self._sources[identity] = original
        elif current not in {original, previously}:
            # A runtime calculation/status replaced the original help text.
            # Treat it as user data, not as a literal that we can overwrite.
            if current not in TEXT:
                self._sources.pop(identity, None)
                self._last_displayed.pop(identity, None)
                return
            original = current
            self._sources[identity] = original
        localized = tr(language, original)
        try:
            setattr(control, field, localized)
        except (AttributeError, TypeError, ValueError):
            return
        self._last_displayed[identity] = localized

    def apply(self, root, language: str):
        """Apply EN/LV/RU to all currently mounted static UI elements."""
        if language not in LANGUAGES:
            language = "en"
        visited: set[int] = set()

        def visit(item):
            if item is None or isinstance(item, (str, bytes, int, float, bool)):
                return
            if isinstance(item, (tuple, list)):
                for child in item:
                    visit(child)
                return
            if isinstance(item, dict):
                for child in item.values():
                    visit(child)
                return
            if id(item) in visited:
                return
            visited.add(id(item))
            cls = type(item).__name__
            # Never translate .value on TextFields, dropdowns, checkboxes,
            # radio groups or other user-input / statistical controls.
            if cls == "Text":
                self._translate_property(item, "value", language)
            elif cls == "DropdownOption":
                self._translate_property(item, "text", language)
            else:
                for prop in ("label", "tooltip", "hint_text"):
                    self._translate_property(item, prop, language)
                # Some Flet controls use a literal title or button content.
                if cls in {"ExpansionTile", "Button"}:
                    for prop in ("title", "content"):
                        self._translate_property(item, prop, language)
            for prop in (
                "controls", "content", "title", "options", "actions",
                "leading", "trailing", "tabs",
            ):
                try:
                    visit(getattr(item, prop, None))
                except (AttributeError, TypeError):
                    pass

        visit(root)
