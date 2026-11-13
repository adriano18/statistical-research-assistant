"""Audit the English, Latvian and Russian text of the application.

Usage::

    python tools/locale_audit.py                      # counts per category
    python tools/locale_audit.py --markdown out.md    # every finding, as Markdown
    python tools/locale_audit.py --json out.json      # the same, as JSON
    python tools/locale_audit.py --strict missing,placeholder
                                                      # exit 1 if these categories
                                                      # have findings

Findings do not change the exit status unless ``--strict`` names their
category: the audit is the input for a native-speaker review (Stage 36.8,
issue #62), not a gate. ``tests/test_locale_audit.py`` keeps two categories
at zero: ``missing`` and ``placeholder``.

The audit reads every EN/LV/RU text table (``TABLES``) and the source of the
workspace screens (``workspace_*.py``). It changes nothing.

Categories
----------
``missing``
    An LV/RU text is absent or empty where English has text; an English source
    text (scale-group messages, method profiles, engine option labels) has no
    translation entry; a key the workspace code asks ``ui.t`` for is not
    defined, so the screen would show the bare key.
``identical``
    An LV/RU text is the same as English although it contains words. Proper
    names, abbreviations and symbols that are the same in every language
    (``SAME_IN_ALL_LANGUAGES``) do not count.
``placeholder``
    The ``{name}`` fields of LV/RU differ from English, or braces are
    malformed (``str.format`` would fail or drop a value).
``style``
    Doubled spaces; lowercase Latin words in Russian text (usually an
    untranslated word); a word mixing Latin and Cyrillic letters; Cyrillic in
    Latvian text; a long Latvian text without any diacritic, or a word with an
    obviously missing one; whitespace at the ends that differs from English
    (texts that are joined to other texts); a key written twice, so that a
    later entry silently replaces a translation.
``length``
    A button or step label whose LV/RU text is more than ``LENGTH_RATIO`` times
    as long as English. A layout risk to check on screen, not an error.
``hardcoded``
    An English string literal given to a visible-text parameter of a component
    in ``workspace_*.py`` (``wc.text``, ``wc.button``, ``wc.caption``,
    ``ft.Text`` and the other helpers in ``COMPONENT_TEXT``/``FLET_TEXT``)
    instead of a ``ui.t`` key.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
import importlib
import json
import os
from pathlib import Path
import re
import string
import sys
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLBACKEND", "Agg")

LANGS = ("en", "lv", "ru")
TRANSLATIONS = ("lv", "ru")
CATEGORIES = ("missing", "identical", "placeholder", "style", "length", "hardcoded")
CATEGORY_TITLES = {
    "missing": "Missing translations and keys",
    "identical": "LV/RU identical to English",
    "placeholder": "Placeholder mismatches",
    "style": "Style: spaces, scripts, diacritics",
    "length": "Long button and step labels (layout risk)",
    "hardcoded": "Hard-coded English in workspace screens",
}

# Text that is correctly the same in every language. An LV/RU text identical
# to English is accepted only if nothing but these, placeholders, numbers,
# punctuation and non-Latin symbols (α, ω, ρ, τ, χ², η², ×, –) is left. Keep
# the list short: a word that a translator could translate does not belong
# here. Matching is case-sensitive, by whole word.
SAME_IN_ALL_LANGUAGES = frozenset({
    # Product, platform and file-format names.
    "Statistical Research Assistant", "Windows", "macOS", "GitHub", "Word", "Excel",
    "CSV", "TSV", "XLSX", "DOCX", "PDF", "PNG", "SVG", "JSON", "TXT", "UTF-8", "UTF-16",
    # Software, standards and identifiers cited as such.
    "SPSS", "APA", "OCR", "API", "ID", "SHA-256", "Tesseract", "PDFium",
    # Method abbreviations that stay international (workspace_text docstring).
    "ANOVA", "ANCOVA", "GLM", "EFA", "PCA", "HC3", "ROC", "Varimax", "Oblimin",
    # Each language's name, written in that language (language pickers).
    "English", "Latviešu", "Русский", "EN", "LV", "RU",
    # The ISO 8601 date mask of a date answer (whether LV/RU should show
    # GGGG-MM-DD / ГГГГ-ММ-ДД is open: docs/STAGE368_LOCALE_REVIEW.md).
    "YYYY-MM-DD",
})

# Lowercase Latin words that are correct inside Russian text: Latin terms of
# scientific writing and units.
LATIN_IN_RUSSIAN = frozenset({"post", "hoc", "dpi", "logit"})

LENGTH_RATIO = 1.6
# A label this short does not wrap or push a row apart even when it is
# several times the English length ("Save" -> "Сохранить").
LENGTH_MIN_CHARS = 12
# Characters a placeholder stands for when lengths are compared ("{method}"
# is a method or variable name, not three characters).
PLACEHOLDER_CHARS = 10

LATVIAN_LETTERS = "āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ"
LATVIAN_SUFFIXES = (
    # A Latvian word with an ending that always carries a diacritic.
    (re.compile(r"\b\w{2,}sana(?:s|i|u|m)?\b", re.I), "-šana"),
    (re.compile(r"\b\w{3,}iba(?:s|i|u|m)?\b", re.I), "-ība"),
    (re.compile(r"\b\w{3,}tajs\b", re.I), "-tājs"),
    (re.compile(r"\brezultat\w*", re.I), "rezultāt-"),
    (re.compile(r"\bmainig\w*", re.I), "mainīg-"),
)
# A Latvian text of this many words without one diacritic was almost certainly
# typed without them (short texts such as "Dati" or "Fails" have none).
LATVIAN_LONG_WORDS = 8

_FORMATTER = string.Formatter()
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_URL = re.compile(r"https?://\S+|www\.\S+")
_LATIN_WORD = re.compile(r"[A-Za-z]+")
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Entry:
    """One text in its three languages (``None``: no text in that language)."""

    table: str
    key: str
    en: str | None
    lv: str | None
    ru: str | None
    location: str = ""

    def text(self, language: str) -> str | None:
        return getattr(self, language)


@dataclass(frozen=True)
class Finding:
    category: str
    table: str
    key: str
    language: str
    detail: str
    text: str = ""
    location: str = ""


@dataclass(frozen=True)
class TableSpec:
    """Where a text table lives and how it is shaped.

    ``shape`` is one of ``triples`` (key: (en, lv, ru)), ``pairs``
    (English: (lv, ru)), ``languages`` ({lang: {key: text}}), ``tuples``
    ({lang: (text, ...)}), ``plurals``, ``terms`` (statistical_guide.Term),
    ``assumptions`` ({English: {lang: text}}), ``methods``
    (interpretation_i18n.METHOD_TEXT with the English of interpretation_wizard)
    and ``scales`` (survey_ui scale presets). ``static`` tables are read from
    the source without importing the module (``app`` starts the program).
    """

    name: str
    module: str
    attribute: str
    shape: str
    area: str = "workspace"     # workspace | report | classic | shared | engine
    static: bool = False


TABLES: tuple[TableSpec, ...] = (
    TableSpec("workspace_text.T", "workspace_text", "T", "triples"),
    TableSpec("workspace_text.LABELS", "workspace_text", "LABELS", "pairs"),
    TableSpec("workspace_text.PLURALS", "workspace_text", "PLURALS", "plurals"),
    TableSpec("workspace_ai.TEXT", "workspace_ai", "TEXT", "languages"),
    TableSpec("research_report.TEXT", "research_report", "TEXT", "languages", "report"),
    TableSpec("report_docx.LABELS", "report_docx", "LABELS", "languages", "report"),
    TableSpec("interpretation_i18n.ASSUMPTION_TEXT", "interpretation_i18n", "ASSUMPTION_TEXT",
              "assumptions", "report"),
    TableSpec("interpretation_i18n.METHOD_TEXT", "interpretation_i18n", "METHOD_TEXT",
              "methods", "report"),
    TableSpec("interpretation_ui.LABELS", "interpretation_ui", "LABELS", "languages", "classic"),
    TableSpec("localization.TEXT", "localization", "TEXT", "pairs", "classic"),
    TableSpec("desktop_shell_text.SHELL_TEXT", "desktop_shell_text", "SHELL_TEXT", "languages",
              "classic"),
    TableSpec("statistical_guide.GUIDE_LABELS", "statistical_guide", "GUIDE_LABELS",
              "languages", "classic"),
    TableSpec("statistical_guide.TERMS", "statistical_guide", "TERMS", "terms", "classic"),
    TableSpec("survey_ui.SCALE_PRESETS", "survey_ui", "LOCALIZED_SCALE_PRESETS", "scales",
              "classic"),
    TableSpec("update_ui.TEXT", "update_ui", "TEXT", "languages", "shared"),
    TableSpec("data_ui.TEXT", "data_ui", "TEXT", "languages", "shared"),
    TableSpec("app.SPLASH_TEXT", "app", "SPLASH_TEXT", "tuples", "shared", static=True),
    TableSpec("batch_correlation.TEMPLATES", "batch_correlation", "TEMPLATES", "languages",
              "engine"),
    TableSpec("batch_correlation.MAGNITUDE_WORDS", "batch_correlation", "MAGNITUDE_WORDS",
              "languages", "engine"),
    TableSpec("batch_groups.GROUP_TEMPLATES", "batch_groups", "GROUP_TEMPLATES", "languages",
              "engine"),
)


# ------------------------------------------------------------------ loading
def _ensure_path(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _static_value(root: Path, module: str, attribute: str):
    """A literal assigned at module level, read without importing the module."""
    tree = ast.parse((root / f"{module}.py").read_text(encoding="utf-8"))
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == attribute for t in targets):
            return ast.literal_eval(node.value)
    raise LookupError(f"{module}.{attribute} is not a module-level literal")


def _text(value) -> str | None:
    return value if isinstance(value, str) else None


def _flatten(table: str, key: str, values: dict[str, object], location: str) -> list[Entry]:
    """Entries for one key whose texts may be tuples (column headers)."""
    sequences = [v for v in values.values() if isinstance(v, (tuple, list))]
    if not sequences:
        return [Entry(table, key, *(_text(values.get(lang)) for lang in LANGS), location)]
    size = max(len(v) for v in sequences)
    entries = []
    for index in range(size):
        parts = []
        for lang in LANGS:
            value = values.get(lang)
            parts.append(_text(value[index]) if isinstance(value, (tuple, list))
                         and index < len(value) else None)
        entries.append(Entry(table, f"{key}[{index}]", *parts, location))
    return entries


def entries_from(spec: TableSpec, value, *, location: str = "",
                 english: dict | None = None) -> list[Entry]:
    """Normalise a table of any shape to :class:`Entry` rows."""
    name, shape = spec.name, spec.shape
    rows: list[Entry] = []
    if shape == "triples":
        for key, texts in value.items():
            texts = list(texts) + [None] * 3
            rows.append(Entry(name, key, *(_text(t) for t in texts[:3]), location))
    elif shape == "pairs":
        for source, texts in value.items():
            texts = list(texts) + [None] * 2
            rows.append(Entry(name, source, source, _text(texts[0]), _text(texts[1]), location))
    elif shape == "languages":
        keys = list(dict.fromkeys(k for lang in LANGS for k in value.get(lang, {})))
        for key in keys:
            rows.extend(_flatten(name, key, {lang: value.get(lang, {}).get(key)
                                             for lang in LANGS}, location))
    elif shape == "tuples":
        rows.extend(_flatten(name, "text", {lang: tuple(value.get(lang, ())) for lang in LANGS},
                             location))
    elif shape == "plurals":
        for noun, forms in value.items():
            size = max(len(forms.get(lang, ())) for lang in LANGS)
            for index in range(size):
                texts = [forms.get(lang, ())[index] if index < len(forms.get(lang, ()))
                         else None for lang in LANGS]
                # English has two forms (one, other); LV and RU three.
                if texts[0] is None and index == 2:
                    texts[0] = forms["en"][-1]
                rows.append(Entry(name, f"{noun}[{index}]", *texts, location))
    elif shape == "terms":
        for key, term in value.items():
            rows.append(Entry(name, key, term.en, term.lv, term.ru, location))
    elif shape == "assumptions":
        for source, texts in value.items():
            rows.append(Entry(name, source, source, _text(texts.get("lv")),
                              _text(texts.get("ru")), location))
        for source in (english or {}):
            if source not in value:
                rows.append(Entry(name, source, source, None, None, location))
    elif shape == "methods":
        sections = list(dict.fromkeys([*(english or {}), *value]))
        for section in sections:
            profile = (english or {}).get(section, {})
            fields = list(dict.fromkeys([*profile, *(f for lang in TRANSLATIONS
                                                     for f in value.get(section, {})
                                                     .get(lang, {}))]))
            for item in fields:
                rows.append(Entry(name, f"{section}.{item}", profile.get(item),
                                  *(_text(value.get(section, {}).get(lang, {}).get(item))
                                    for lang in TRANSLATIONS), location))
    elif shape == "scales":
        for preset, sizes in (english or {}).items():
            for size, labels in sizes.items():
                for index, label in enumerate(labels):
                    texts = []
                    for lang in TRANSLATIONS:
                        localized = value.get(lang, {}).get(preset, {}).get(size, [])
                        texts.append(localized[index] if index < len(localized) else None)
                    rows.append(Entry(name, f"{preset}.{size}[{index}]", label, *texts,
                                      location))
    else:
        raise ValueError(f"unknown table shape {shape!r}")
    return rows


def load_tables(root: Path = ROOT,
                specs: Iterable[TableSpec] = TABLES) -> tuple[list[Entry], list[str]]:
    """All entries of ``specs`` and the tables that could not be read."""
    _ensure_path(root)
    entries: list[Entry] = []
    errors: list[str] = []
    for spec in specs:
        location = f"{spec.module}.py"
        try:
            if spec.static:
                value = _static_value(root, spec.module, spec.attribute)
            else:
                value = getattr(importlib.import_module(spec.module), spec.attribute)
            english = None
            if spec.shape == "assumptions":
                english = {a: None for a in _profile_assumptions()}
            elif spec.shape == "methods":
                english = _profile_texts()
            elif spec.shape == "scales":
                english = importlib.import_module(spec.module).SCALE_PRESETS
            entries.extend(entries_from(spec, value, location=location, english=english))
        except Exception as error:    # a broken table is itself a finding
            errors.append(f"{spec.name}: {type(error).__name__}: {error}")
    return entries, errors


def _profile_texts() -> dict[str, dict[str, str]]:
    from interpretation_wizard import METHOD_PROFILES

    return {section: {"rationale": p.rationale, "limitation": p.limitation}
            for section, p in METHOD_PROFILES.items()}


def _profile_assumptions() -> list[str]:
    from interpretation_wizard import METHOD_PROFILES

    return list(dict.fromkeys(a for p in METHOD_PROFILES.values() for a in p.assumptions))


def source_entries(root: Path = ROOT) -> tuple[list[Finding], list[str]]:
    """English source texts that the interface translates by key or by text:
    each needs an entry in a table (``missing`` findings)."""
    _ensure_path(root)
    findings: list[Finding] = []
    errors: list[str] = []
    try:
        import scale_groups
        from workspace_text import T

        for key, english in scale_groups.TEXT.items():
            if key not in T:
                findings.append(Finding("missing", "workspace_text.T", key, "all",
                                        "scale_groups message has no workspace text",
                                        english, "scale_groups.py"))
            elif _fields(english) != _fields(T[key][0]):
                findings.append(Finding("placeholder", "workspace_text.T", key, "en",
                                        "fields differ from scale_groups.TEXT "
                                        f"{sorted(_fields(english) or ())}",
                                        T[key][0], "workspace_text.py"))
    except Exception as error:
        errors.append(f"scale_groups.TEXT: {type(error).__name__}: {error}")
    try:
        from localization import TEXT as CLASSIC
        from workspace_methods import METHODS
        from workspace_text import LABELS

        # workspace_text.label() shows these through LABELS, then the classic table.
        seen = set()
        for spec in METHODS.values():
            labels = [(i.label, "method confirmation/option label")
                      for i in (*spec.confirmations, *spec.options)]
            labels += [(text, "method option choice") for option in spec.options
                       for _, text in option.choices]
            for text, what in labels:
                if text in seen or not re.search(r"[A-Za-z]{2}", text):
                    continue
                seen.add(text)
                if text not in LABELS and text not in CLASSIC:
                    findings.append(Finding("missing", "workspace_text.LABELS", text, "all",
                                            f"{what} has no translation", text,
                                            "workspace_methods.py"))
    except Exception as error:
        errors.append(f"workspace_methods.METHODS: {type(error).__name__}: {error}")
    return findings, errors


# ------------------------------------------------------------------- checks
def _fields(text: str) -> frozenset[str] | None:
    """``str.format`` field names of ``text`` (None: malformed braces)."""
    try:
        return frozenset(name for _, name, _, _ in _FORMATTER.parse(text) if name is not None)
    except ValueError:
        return None


def _without_placeholders(text: str) -> str:
    return _PLACEHOLDER.sub(" ", text)


def residual_words(text: str) -> list[str]:
    """Latin words left after removing placeholders, URLs and allowed names."""
    rest = _URL.sub(" ", _without_placeholders(text))
    for name in sorted(SAME_IN_ALL_LANGUAGES, key=len, reverse=True):
        rest = re.sub(rf"(?<![\w-]){re.escape(name)}(?![\w-])", " ", rest)
    return [w for w in _LATIN_WORD.findall(rest) if len(w) >= 2]


def check_missing(entry: Entry) -> list[Finding]:
    found = []
    if not (entry.en or "").strip():
        if any((entry.text(lang) or "").strip() for lang in TRANSLATIONS):
            found.append(Finding("missing", entry.table, entry.key, "en",
                                 "translated but no English source text",
                                 entry.lv or entry.ru or "", entry.location))
        return found
    for lang in TRANSLATIONS:
        if not (entry.text(lang) or "").strip():
            found.append(Finding("missing", entry.table, entry.key, lang, "no translation",
                                 entry.en, entry.location))
    return found


def check_identical(entry: Entry) -> list[Finding]:
    found = []
    english = (entry.en or "").strip()
    if not english:
        return found
    for lang in TRANSLATIONS:
        value = (entry.text(lang) or "").strip()
        if value == english:
            words = residual_words(value)
            if words:
                found.append(Finding("identical", entry.table, entry.key, lang,
                                     "same as English: " + ", ".join(dict.fromkeys(words)),
                                     value, entry.location))
    return found


def check_placeholders(entry: Entry) -> list[Finding]:
    found = []
    if entry.en is None:
        return found
    english = _fields(entry.en)
    if english is None:
        found.append(Finding("placeholder", entry.table, entry.key, "en", "malformed braces",
                             entry.en, entry.location))
        return found
    for lang in TRANSLATIONS:
        value = entry.text(lang)
        if not value:
            continue
        fields = _fields(value)
        if fields is None:
            found.append(Finding("placeholder", entry.table, entry.key, lang,
                                 "malformed braces", value, entry.location))
        elif fields != english:
            missing, extra = sorted(english - fields), sorted(fields - english)
            parts = ([f"missing {{{'}, {'.join(missing)}}}"] if missing else []) + (
                [f"unexpected {{{'}, {'.join(extra)}}}"] if extra else [])
            found.append(Finding("placeholder", entry.table, entry.key, lang,
                                 "; ".join(parts), value, entry.location))
    return found


def _latvian_style(value: str) -> list[str]:
    problems = []
    if _CYRILLIC.search(value):
        problems.append("Cyrillic letters in Latvian text")
    plain = _URL.sub(" ", _without_placeholders(value))
    words = [w for w in _LATIN_WORD.findall(plain) if len(w) >= 2]
    if (len(words) >= LATVIAN_LONG_WORDS and not any(c in LATVIAN_LETTERS for c in plain)
            and residual_words(plain)):
        problems.append("no Latvian diacritics in a long text")
    for pattern, ending in LATVIAN_SUFFIXES:
        for match in pattern.finditer(plain):
            word = match.group(0)
            if not any(c in LATVIAN_LETTERS for c in word):
                problems.append(f"“{word}” lacks a diacritic ({ending})")
    return problems


def _russian_style(value: str, english: str) -> list[str]:
    problems = []
    plain = _URL.sub(" ", _without_placeholders(value))
    if not _CYRILLIC.search(plain) and residual_words(plain) and value.strip() != english.strip():
        problems.append("no Cyrillic letters in Russian text")
    latin = []
    # Lowercase words of three letters or more, not part of a file name,
    # path, identifier or function call (data.csv, a/b, snake_case, f(x)).
    for match in re.finditer(r"(?<![\w.\-/\\])[a-z]{3,}(?![\w\-/\\(])(?!\.\w)", plain):
        word = match.group(0)
        if word not in LATIN_IN_RUSSIAN:
            latin.append(word)
    if latin and _CYRILLIC.search(plain):
        problems.append("Latin words in Russian text: " + ", ".join(dict.fromkeys(latin)))
    return problems


def check_style(entry: Entry) -> list[Finding]:
    found = []
    for lang in LANGS:
        value = entry.text(lang)
        if not value:
            continue
        problems = []
        if re.search(r"\S {2,}\S", value):
            problems.append("doubled space")
        for word in _WORD.findall(value):
            if re.search(r"[A-Za-z]", word) and _CYRILLIC.search(word):
                problems.append(f"“{word}” mixes Latin and Cyrillic letters")
        if lang != "en" and entry.en:
            for side, english_edge, edge in (
                    ("start", entry.en[:1].isspace(), value[:1].isspace()),
                    ("end", entry.en[-1:].isspace(), value[-1:].isspace())):
                if english_edge != edge:
                    problems.append(f"whitespace at the {side} differs from English")
        if lang == "lv" and value.strip() != (entry.en or "").strip():
            problems.extend(_latvian_style(value))
        if lang == "ru":
            problems.extend(_russian_style(value, entry.en or ""))
        for problem in problems:
            found.append(Finding("style", entry.table, entry.key, lang, problem, value,
                                 entry.location))
    return found


def _display_length(text: str) -> int:
    """Length on screen; a placeholder holds a name or number of typical length."""
    return len(_PLACEHOLDER.sub("x" * PLACEHOLDER_CHARS, text).strip())


def check_length(entry: Entry, ratio: float = LENGTH_RATIO,
                 minimum: int = LENGTH_MIN_CHARS) -> list[Finding]:
    found = []
    if not entry.en:
        return found
    english = max(_display_length(entry.en), 1)
    for lang in TRANSLATIONS:
        value = entry.text(lang)
        if not value or value.strip() == entry.en.strip():
            continue
        length = _display_length(value)
        if length >= minimum and length > ratio * english:
            found.append(Finding("length", entry.table, entry.key, lang,
                                 f"{length} characters, {length / english:.1f}× English "
                                 f"({english})", value, entry.location))
    return found


CHECKS: tuple[Callable[[Entry], list[Finding]], ...] = (
    check_missing, check_identical, check_placeholders, check_style)


# --------------------------------------------------------- source scanning
# Visible-text parameters of the workspace components: positional indexes and
# keyword names. "options" is a list of (value, label) pairs; "tooltips" a
# {value: text} dict.
COMPONENT_TEXT: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "text": ((1,), ()), "heading": ((1,), ()), "caption": ((1,), ()),
    "section_label": ((1,), ()), "labeled": ((1,), ()), "checkbox": ((1,), ()),
    "button": ((1,), ("tooltip",)), "locked_step": ((1,), ()),
    "icon_button": ((2,), ("tooltip",)), "chip": ((1,), ("tooltip",)),
    "notice": ((1,), ("title",)), "card": ((), ("title", "description")),
    "page_header": ((1, 2), ("subtitle",)), "empty_state": ((2, 3), ()),
    "action_tile": ((2, 3, 4), ()), "stat": ((1, 3), ("detail",)),
    "apa_table": ((), ("title", "note")), "figure": ((), ("caption_text", "enlarge_label")),
    "step_card": ((2,), ("summary",)), "dropdown": ((1,), ("tooltip",)),
    "text_field": ((1,), ("hint",)), "segmented": ((), ()),
}
COMPONENT_OPTIONS = {"dropdown": 2, "segmented": 1}
FLET_TEXT: dict[str, tuple[tuple[int, ...], tuple[str, ...]]] = {
    "Text": ((0,), ("value", "tooltip")),
    "Button": ((0,), ("content", "text", "tooltip")),
    "TextButton": ((0,), ("content", "text", "tooltip")),
    "OutlinedButton": ((0,), ("content", "text", "tooltip")),
    "FilledButton": ((0,), ("content", "text", "tooltip")),
    "FilledTonalButton": ((0,), ("content", "text", "tooltip")),
    "ElevatedButton": ((0,), ("content", "text", "tooltip")),
    "Tooltip": ((), ("message",)), "DropdownOption": ((), ("text",)),
    "Checkbox": ((), ("label", "tooltip")), "TextField": ((), ("label", "hint_text")),
    "Dropdown": ((), ("label", "hint_text")), "Tab": ((), ("label", "text")),
}
# Label parameters that make a key a button or a step label (length check).
BUTTON_PARAMETERS = {"button": (1,), "action_tile": (4,), "locked_step": (1,),
                     "step_card": (2,)}
BUTTON_CONTROLS = {"Button", "TextButton", "OutlinedButton", "FilledButton",
                   "FilledTonalButton", "ElevatedButton"}
# Keys shown as step labels through a variable (journey strip, import wizard).
STEP_KEY_PATTERNS = (re.compile(r"^step\.[^.]+$"), re.compile(r"^imp\.step\.[^.]+$"),
                     re.compile(r"^journey\.[^.]+$"))
UI_MODULES = "workspace_*.py"
NOT_UI_MODULES = {"workspace_text.py", "workspace_tokens.py", "workspace_routes.py"}
# The option choices of workspace_methods are canonical engine labels shown
# through workspace_text.label(); the ``missing`` check covers them.
LABEL_PAIR_EXEMPT = {"workspace_methods.py"}
# Modules whose table literals are checked for keys written twice.
DUPLICATE_SOURCES = ("workspace_text.py", "localization.py", "localization_extended.py",
                     "interpretation_i18n.py", "desktop_shell_text.py", "research_report.py",
                     "report_docx.py", "workspace_ai.py")


@dataclass
class SourceScan:
    keys: dict[str, list[str]] = field(default_factory=dict)          # key -> locations
    patterns: dict[str, list[str]] = field(default_factory=dict)      # regex -> locations
    own_keys: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    button_keys: set[str] = field(default_factory=set)
    button_patterns: set[str] = field(default_factory=set)
    literals: list[Finding] = field(default_factory=list)


def _call_name(node: ast.Call) -> tuple[str, str | None, str | None]:
    """("attr", owner, name) for ``owner.name(...)`` (owner None when it is not
    a plain name, as in ``self.app.t``), ("name", None, name) for ``name(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        owner = func.value.id if isinstance(func.value, ast.Name) else None
        return "attr", owner, func.attr
    if isinstance(func, ast.Name):
        return "name", None, func.id
    return "other", None, None


def _translation_argument(node: ast.Call, own_t: bool) -> tuple[str, ast.AST] | None:
    """(table, key argument) of ``ui.t(key)``, ``self.app.t(key)``,
    ``t(language, key)`` or ``translate(language, key)``; ``own`` is the
    module's own ``t`` (workspace_ai)."""
    kind, _, name = _call_name(node)
    if kind == "attr" and name == "t" and node.args:
        return "workspace_text.T", node.args[0]
    if kind == "name" and name in ("t", "translate") and len(node.args) >= 2:
        return ("own" if own_t and name == "t" else "workspace_text.T"), node.args[1]
    return None


def _key_expression(node: ast.AST) -> tuple[str | None, str | None]:
    """(key, None) for a literal key, (None, regex) for a composed one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, None
    parts: list[str] = []

    def collect(item) -> bool:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            parts.append(re.escape(item.value))
        elif isinstance(item, ast.JoinedStr):
            for value in item.values:
                if isinstance(value, ast.Constant):
                    parts.append(re.escape(value.value))
                else:
                    parts.append(r"[^.]+")
        elif isinstance(item, ast.BinOp) and isinstance(item.op, ast.Add):
            return collect(item.left) and collect(item.right)
        elif isinstance(item, (ast.Name, ast.Attribute, ast.Subscript, ast.Call)):
            parts.append(r"[^.]+")
        else:
            return False
        return True

    if isinstance(node, (ast.JoinedStr, ast.BinOp)) and collect(node):
        pattern = "^" + "".join(parts) + "$"
        if re.sub(r"\[\^\.\]\+", "", pattern) != "^$":
            return None, pattern
    return None, None


def _literal_texts(node: ast.AST) -> list[tuple[str, int]]:
    """Visible literal text in an argument with its line: constants, f-string
    parts, either side of ``a or "b"`` / ``"a" if c else "b"``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [(node.value, node.lineno)]
    if isinstance(node, ast.JoinedStr):
        text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
        return [(text, node.lineno)] if text.replace("{}", "").strip() else []
    if isinstance(node, ast.BoolOp):
        return [t for value in node.values for t in _literal_texts(value)]
    if isinstance(node, ast.IfExp):
        return _literal_texts(node.body) + _literal_texts(node.orelse)
    return []


def _label_pairs(node: ast.AST) -> list[ast.Constant]:
    """The labels of a literal list of ``(value, "Label")`` pairs (choices kept
    in a constant and handed to a dropdown later, e.g. ``OPERATORS``)."""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) < 2:
        return []
    labels = []
    for element in node.elts:
        if not (isinstance(element, ast.Tuple) and len(element.elts) == 2 and all(
                isinstance(x, ast.Constant) and isinstance(x.value, str) for x in element.elts)):
            return []
        value, label = element.elts
        if not re.fullmatch(r"[\w.\-+]*", value.value):
            return []
        labels.append(label)
    return labels


def english_words(text: str) -> list[str]:
    """Words that make a literal English interface text (none: a symbol, a
    number, an allowed name or an identifier such as ``data-reimport``)."""
    plain = text.replace("{}", " ")
    if re.fullmatch(r"\s*[\w.\-:/#]*\s*", plain) and not re.search(r"[A-Z ]", plain.strip()):
        return []          # an identifier, key or value, not a sentence or a label
    return [w for w in residual_words(plain) if len(w) >= 3 or w.isupper()]


def _translation_calls(node: ast.AST, own_t: bool):
    """Every translation call inside ``node`` as (table, key argument)."""
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            found = _translation_argument(item, own_t)
            if found is not None:
                yield found


def scan_source(root: Path = ROOT) -> SourceScan:
    scan = SourceScan()
    for path in sorted(root.glob(UI_MODULES)):
        if path.name in NOT_UI_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        own_t = any(isinstance(n, ast.FunctionDef) and n.name == "t" for n in tree.body)
        components_module = path.name == "workspace_components.py"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            where = f"{path.name}:{node.lineno}"
            kind, owner, name = _call_name(node)
            # Keys asked for (missing keys): every translation call.
            translation = _translation_argument(node, own_t)
            if translation is not None:
                table, argument = translation
                key, pattern = _key_expression(argument)
                if table == "own":
                    if key is not None:
                        scan.own_keys.setdefault(path.stem, {}).setdefault(
                            key, []).append(where)
                elif key is not None:
                    scan.keys.setdefault(key, []).append(where)
                elif pattern is not None:
                    scan.patterns.setdefault(pattern, []).append(where)
                continue
            component = name in COMPONENT_TEXT and (
                (kind == "attr" and owner == "wc") or (components_module and kind == "name"))
            control = kind == "attr" and owner == "ft" and name in FLET_TEXT
            if not (component or control):
                continue
            positions, keywords = (COMPONENT_TEXT if component else FLET_TEXT)[name]
            arguments = [node.args[i] for i in positions if i < len(node.args)]
            arguments += [k.value for k in node.keywords if k.arg in keywords]
            options = []
            if component and name in COMPONENT_OPTIONS:
                index = COMPONENT_OPTIONS[name]
                value = node.args[index] if index < len(node.args) else next(
                    (k.value for k in node.keywords if k.arg == "options"), None)
                if isinstance(value, (ast.List, ast.Tuple)):
                    for element in value.elts:
                        if isinstance(element, ast.Tuple) and len(element.elts) == 2:
                            options.append(element.elts[1])
            if component and name == "segmented":
                tips = next((k.value for k in node.keywords if k.arg == "tooltips"), None)
                if isinstance(tips, ast.Dict):
                    arguments += list(tips.values)
            # Button and step labels (length check).
            labels = []
            if component and name in BUTTON_PARAMETERS:
                labels = [node.args[i] for i in BUTTON_PARAMETERS[name] if i < len(node.args)]
            elif component and name == "segmented":
                labels = options
            elif control and name in BUTTON_CONTROLS:
                labels = node.args[:1] + [k.value for k in node.keywords
                                          if k.arg in ("content", "text")]
            for label in labels:
                for _, argument in _translation_calls(label, own_t):
                    key, pattern = _key_expression(argument)
                    if key is not None:
                        scan.button_keys.add(key)
                    elif pattern is not None:
                        scan.button_patterns.add(pattern)
            # Hard-coded English.
            for argument in arguments + options:
                for literal, line in _literal_texts(argument):
                    words = english_words(literal)
                    if words:
                        scan.literals.append(Finding(
                            "hardcoded", path.name, f"{'wc' if component else 'ft'}.{name}",
                            "en", "English literal: " + ", ".join(dict.fromkeys(words)),
                            literal, f"{path.name}:{line}"))
        if path.name in LABEL_PAIR_EXEMPT:
            continue
        reported = {(f.location, f.text) for f in scan.literals}
        for node in ast.walk(tree):
            for label in _label_pairs(node):
                where = f"{path.name}:{label.lineno}"
                words = english_words(label.value)
                if words and (where, label.value) not in reported:
                    reported.add((where, label.value))
                    scan.literals.append(Finding(
                        "hardcoded", path.name, "(value, label) choices", "en",
                        "English literal: " + ", ".join(dict.fromkeys(words)), label.value,
                        where))
    return scan


def _table_literals(tree: ast.Module):
    """(table name, key node, value node) of every ``NAME = {...}`` and
    ``NAME.update({...})`` dict literal."""
    for node in ast.walk(tree):
        name, value = None, None
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if names and isinstance(node.value, ast.Dict):
                name, value = names[0], node.value
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == "update" and isinstance(node.func.value, ast.Name)
              and node.args and isinstance(node.args[0], ast.Dict)):
            name, value = node.func.value.id, node.args[0]
        if name is not None:
            for key, item in zip(value.keys, value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    yield name, key, item


def duplicate_keys(root: Path = ROOT) -> list[Finding]:
    """A key written twice: the later text silently replaces the earlier one,
    so a reviewer may be reading a text the program never shows."""
    found = []
    for module in DUPLICATE_SOURCES:
        path = Path(root) / module
        if not path.exists():
            continue
        seen: dict[tuple[str, str], list[tuple[int, ast.AST]]] = {}
        for name, key, item in _table_literals(ast.parse(path.read_text(encoding="utf-8"))):
            seen.setdefault((name, key.value), []).append((key.lineno, item))
        for (name, key), places in seen.items():
            if len(places) < 2:
                continue
            lines = ", ".join(str(line) for line, _ in places)
            same = len({ast.dump(item) for _, item in places}) == 1
            found.append(Finding("style", f"{path.stem}.{name}", key, "all",
                                 f"key written {len(places)} times (lines {lines}); "
                                 + ("same text" if same else "the last text is shown"),
                                 key, module))
    try:
        base = _static_value(Path(root), "localization", "TEXT")
        from localization_extended import EXTRA_TEXT

        for key, texts in base.items():
            later = EXTRA_TEXT.get(key)
            if later is not None and tuple(later) != tuple(texts):
                found.append(Finding("style", "localization.TEXT", key, "all",
                                     "replaced by localization_extended.EXTRA_TEXT: "
                                     f"{' / '.join(later)} (not {' / '.join(texts)})", key,
                                     "localization.py"))
    except Exception:       # reported by load_tables when the table is broken
        pass
    return found


def check_keys(scan: SourceScan, entries: list[Entry]) -> list[Finding]:
    """Keys the workspace asks for that no table defines."""
    defined = {e.key for e in entries if e.table == "workspace_text.T"}
    own = {}
    for e in entries:
        own.setdefault(e.table, set()).add(e.key)
    found = []
    for key, where in sorted(scan.keys.items()):
        if key not in defined:
            found.append(Finding("missing", "workspace_text.T", key, "all",
                                 "used by the workspace but not defined (the screen shows "
                                 "the key)", key, ", ".join(where[:3])))
    for pattern, where in sorted(scan.patterns.items()):
        if not any(re.match(pattern, key) for key in defined):
            found.append(Finding("missing", "workspace_text.T", pattern, "all",
                                 "no defined key matches this composed key", pattern,
                                 ", ".join(where[:3])))
    for module, keys in sorted(scan.own_keys.items()):
        table = f"{module}.TEXT"
        for key, where in sorted(keys.items()):
            if table in own and key not in own[table]:
                found.append(Finding("missing", table, key, "all",
                                     "used but not defined", key, ", ".join(where[:3])))
    return found


def is_button_key(key: str, scan: SourceScan) -> bool:
    if key in scan.button_keys:
        return True
    patterns = [*STEP_KEY_PATTERNS, *(re.compile(p) for p in scan.button_patterns)]
    return any(p.match(key) for p in patterns)


# ------------------------------------------------------------------- report
@dataclass
class Audit:
    findings: list[Finding]
    entries: int
    tables: dict[str, int]
    errors: list[str]

    def counts(self) -> dict[str, int]:
        counts = {category: 0 for category in CATEGORIES}
        for finding in self.findings:
            counts[finding.category] += 1
        return counts

    def of(self, category: str) -> list[Finding]:
        return [f for f in self.findings if f.category == category]


def run_audit(root: Path = ROOT, specs: Iterable[TableSpec] = TABLES) -> Audit:
    root = Path(root)
    entries, errors = load_tables(root, specs)
    findings: list[Finding] = []
    for entry in entries:
        for check in CHECKS:
            findings.extend(check(entry))
    sources, source_errors = source_entries(root)
    findings.extend(sources)
    errors.extend(source_errors)
    findings.extend(duplicate_keys(root))
    scan = scan_source(root)
    findings.extend(check_keys(scan, entries))
    for entry in entries:
        if entry.table == "workspace_text.T" and is_button_key(entry.key, scan):
            findings.extend(check_length(entry))
    findings.extend(scan.literals)
    tables: dict[str, int] = {}
    for entry in entries:
        tables[entry.table] = tables.get(entry.table, 0) + 1
    order = {c: i for i, c in enumerate(CATEGORIES)}
    findings.sort(key=lambda f: (order[f.category], f.table, f.key, f.language))
    return Audit(findings, len(entries), tables, errors)


def _cell(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[:limit - 1] + "…"
    return text.replace("|", "\\|")


def render_markdown(audit: Audit) -> str:
    counts = audit.counts()
    lines = ["# Localization audit", "",
             "Generated by `python tools/locale_audit.py --markdown`. Findings are input for "
             "a native-speaker review; none of them changes the exit status unless `--strict` "
             "names its category.", "",
             f"Texts audited: {audit.entries} in {len(audit.tables)} tables.", "",
             "| Category | Findings |", "|---|---:|"]
    lines += [f"| {CATEGORY_TITLES[c]} (`{c}`) | {counts[c]} |" for c in CATEGORIES]
    lines += ["", "| Table | Texts |", "|---|---:|"]
    lines += [f"| `{name}` | {count} |" for name, count in audit.tables.items()]
    if audit.errors:
        lines += ["", "## Tables that could not be read", ""]
        lines += [f"- {_cell(error, 300)}" for error in audit.errors]
    for category in CATEGORIES:
        items = audit.of(category)
        lines += ["", f"## {CATEGORY_TITLES[category]} ({len(items)})", ""]
        if not items:
            lines.append("None.")
            continue
        if category == "hardcoded":
            lines += ["| Where | Call | Literal | Detail |", "|---|---|---|---|"]
            lines += [f"| `{f.location}` | `{f.key}` | {_cell(f.text)} | {_cell(f.detail)} |"
                      for f in items]
        else:
            lines += ["| Table | Key | Lang | Detail | Text |", "|---|---|---|---|---|"]
            lines += [f"| `{f.table}` | `{_cell(f.key, 80)}` | {f.language} | "
                      f"{_cell(f.detail)} | {_cell(f.text)} |" for f in items]
    return "\n".join(lines) + "\n"


def render_summary(audit: Audit) -> str:
    counts = audit.counts()
    lines = [f"Localization audit: {audit.entries} texts in {len(audit.tables)} tables"]
    lines += [f"  {c:<12} {counts[c]:>5}  {CATEGORY_TITLES[c]}" for c in CATEGORIES]
    lines += [f"  error: {e}" for e in audit.errors]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--markdown", type=Path, help="write every finding as Markdown")
    parser.add_argument("--json", type=Path, help="write every finding as JSON")
    parser.add_argument("--strict", default="",
                        help="comma-separated categories that make the exit status 1 "
                             "(default: none; 'all' for every category)")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    strict = set(CATEGORIES) if args.strict.strip() == "all" else {
        c.strip() for c in args.strict.split(",") if c.strip()}
    unknown = strict - set(CATEGORIES)
    if unknown:
        parser.error(f"unknown categories: {', '.join(sorted(unknown))}")
    audit = run_audit(args.root)
    if args.markdown:
        args.markdown.write_text(render_markdown(audit), encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps({
            "entries": audit.entries, "tables": audit.tables, "errors": audit.errors,
            "counts": audit.counts(), "findings": [asdict(f) for f in audit.findings],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render_summary(audit))
    counts = audit.counts()
    failed = sorted(c for c in strict if counts[c])
    if failed or (strict and audit.errors):
        print("strict: " + ", ".join(failed or ["tables could not be read"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
