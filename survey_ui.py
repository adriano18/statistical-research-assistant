"""Focused local questionnaire editor, realistic preview and response workspace.

Four views replace one long mixed-purpose form. The respondent preview does
not write any test answers. Published local survey schemas stay immutable;
researchers can clone a published form into a fresh editable draft.
"""

import asyncio
import copy
from pathlib import Path
from tempfile import TemporaryDirectory

import flet as ft
import pandas as pd

from localization import tr
from survey_document_import import read_survey_document
from survey_storage import (
    validate_questions, create_survey, get_survey, list_surveys,
    submit_response, response_count, responses_dataframe, save_survey_csv,
    save_survey_codebook, question_is_visible, likert_choices,
    reorder_questions, reorder_sections, section_blocks, validate_page_answers,
)


QUESTION_TYPES = [
    ("likert5", "Likert scale 1–5"),
    ("likert7", "Likert scale 1–7"),
    ("rating_scale", "Custom numeric / semantic differential"),
    ("single_choice", "One choice"),
    ("multiple_choice", "Multiple choices"),
    ("yes_no", "Yes / No"),
    ("number", "Number"),
    ("short_text", "Short text"),
    ("long_text", "Long text"),
    ("date", "Date"),
    ("consent", "Required consent"),
]


SCALE_PRESETS = {
    "agreement": {
        5: ["Strongly disagree", "Disagree", "Neither agree nor disagree",
            "Agree", "Strongly agree"],
        7: ["Strongly disagree", "Disagree", "Somewhat disagree",
            "Neither agree nor disagree", "Somewhat agree", "Agree",
            "Strongly agree"],
    },
    "quality": {
        5: ["Very poor", "Poor", "Fair", "Good", "Very good"],
        7: ["Extremely poor", "Very poor", "Poor", "Fair", "Good",
            "Very good", "Excellent"],
    },
    "frequency": {
        5: ["Never", "Rarely", "Sometimes", "Often", "Always"],
        7: ["Never", "Almost never", "Rarely", "Sometimes",
            "Often", "Almost always", "Always"],
    },
}



# Template labels are an explicit draft-authoring choice, not an automatic
# translation of previously collected study responses.
LOCALIZED_SCALE_PRESETS = {
    "lv": {
        "agreement": {
            5: ["Pilnīgi nepiekrītu", "Nepiekrītu", "Ne piekrītu, ne nepiekrītu",
                "Piekrītu", "Pilnīgi piekrītu"],
            7: ["Pilnīgi nepiekrītu", "Nepiekrītu", "Drīzāk nepiekrītu",
                "Ne piekrītu, ne nepiekrītu", "Drīzāk piekrītu",
                "Piekrītu", "Pilnīgi piekrītu"],
        },
        "quality": {
            5: ["Ļoti slikti", "Slikti", "Vidēji", "Labi", "Ļoti labi"],
            7: ["Ārkārtīgi slikti", "Ļoti slikti", "Slikti", "Vidēji",
                "Labi", "Ļoti labi", "Izcili"],
        },
        "frequency": {
            5: ["Nekad", "Reti", "Dažreiz", "Bieži", "Vienmēr"],
            7: ["Nekad", "Gandrīz nekad", "Reti", "Dažreiz",
                "Bieži", "Gandrīz vienmēr", "Vienmēr"],
        },
    },
    "ru": {
        "agreement": {
            5: ["Совершенно не согласен(-на)", "Не согласен(-на)",
                "Ни согласен(-на), ни не согласен(-на)",
                "Согласен(-на)", "Полностью согласен(-на)"],
            7: ["Совершенно не согласен(-на)", "Не согласен(-на)",
                "Скорее не согласен(-на)",
                "Ни согласен(-на), ни не согласен(-на)",
                "Скорее согласен(-на)", "Согласен(-на)",
                "Полностью согласен(-на)"],
        },
        "quality": {
            5: ["Очень плохо", "Плохо", "Средне", "Хорошо", "Очень хорошо"],
            7: ["Крайне плохо", "Очень плохо", "Плохо", "Средне",
                "Хорошо", "Очень хорошо", "Отлично"],
        },
        "frequency": {
            5: ["Никогда", "Редко", "Иногда", "Часто", "Всегда"],
            7: ["Никогда", "Почти никогда", "Редко", "Иногда",
                "Часто", "Почти всегда", "Всегда"],
        },
    },
}

def preset_value_labels(
    name: str, kind: str, language: str = "en"
) -> dict[str, str]:
    """Return full respondent-facing labels for stable numeric response codes."""
    if kind not in {"likert5", "likert7"}:
        raise ValueError("Presets only apply to Likert scales.")
    return {str(i): label for i, label in enumerate(
        LOCALIZED_SCALE_PRESETS.get(language, SCALE_PRESETS)[name][int(kind[-1])],
        start=1
    )}


def format_value_labels(labels: dict[str, str]) -> str:
    return "\n".join(f"{code} = {label}" for code, label in labels.items())


def parse_value_labels(raw: str, kind: str) -> dict[str, str]:
    """Parse numeric code = text lines; schemas validate full code ranges."""
    if kind not in {"likert5", "likert7", "rating_scale"} or not raw.strip():
        return {}
    labels = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise ValueError("Use one choice per line, e.g. 1 = Very poor.")
        code, label = (part.strip() for part in line.split("=", 1))
        try:
            canonical = str(int(code))
        except ValueError as err:
            raise ValueError("Scale codes must be integers.") from err
        if canonical != code or code in labels:
            raise ValueError("Every scale code must be a unique canonical integer.")
        labels[code] = label
    if kind.startswith("likert"):
        expected = {str(n) for n in range(1, int(kind[-1]) + 1)}
        if set(labels) != expected:
            raise ValueError("Label every code in this Likert scale.")
    elif not 2 <= len(labels) <= 11:
        raise ValueError("Custom scales need 2–11 distinct numeric codes.")
    return labels


def semantic_differential_labels(language: str = "en") -> dict[str, str]:
    """Synthetic bipolar example. Wording requires study-specific validation."""
    examples = {
        "en": ["Very difficult", "Difficult", "Somewhat difficult",
               "Neutral", "Somewhat easy", "Easy", "Very easy"],
        "lv": ["Ļoti grūti", "Grūti", "Drīzāk grūti", "Neitrāli",
               "Drīzāk viegli", "Viegli", "Ļoti viegli"],
        "ru": ["Очень трудно", "Трудно", "Скорее трудно", "Нейтрально",
               "Скорее легко", "Легко", "Очень легко"],
    }
    labels = examples.get(language, examples["en"])
    return {str(code): text for code, text in zip(range(-3, 4), labels)}



def build_numeric_rating_selector(question, on_change=None):
    """One accessible selection group for scored choices and explicit missing."""
    score_cards = [
        ft.Container(
            col={"xs": 12, "sm": 6, "xl": 4},
            padding=10,
            border_radius=corner_radius(),
            border=ft.Border.all(1, "#DAE3F0"),
            bgcolor="#F8FAFE",
            content=ft.Radio(
                value=str(number), label=display, active_color="#2457AC",
            ),
        )
        for number, display in likert_choices(question)
    ]
    content = [
        ft.Text("Choose one answer", size=12, color="#51637B"),
        ft.ResponsiveRow(
            controls=score_cards, columns=12, spacing=8, run_spacing=8,
        ),
    ]
    missing = question.get("missing_options") or {}
    if missing:
        content.extend([
            ft.Divider(color="#E0E7F0"),
            ft.Text("Another response", size=12, color="#51637B"),
            ft.Column(
                controls=[
                    ft.Radio(value=code, label=label, active_color="#2457AC")
                    for code, label in missing.items()
                ],
                spacing=5,
            ),
        ])
    return ft.RadioGroup(
        content=ft.Column(controls=content, spacing=8),
        on_change=on_change,
    )


def _pilot_questions():
    """Original fictional practice items, not a validated clinical instrument."""
    return [
        dict(
            key="consent", prompt="I agree to take part in this fictional pilot.",
            kind="consent", required=True, section="Study information",
            page=1, page_title="Introduction",
        ),
        dict(
            key="age", prompt="Your age in years (optional)",
            kind="number", required=False, section="Demographics",
            page=2, page_title="Background",
        ),
        dict(
            key="group", prompt="Fictional study group",
            kind="single_choice", options=["A", "B"], required=True,
            section="Demographics", page=2, page_title="Background",
        ),
        dict(
            key="employed", prompt="Are you currently employed?",
            kind="yes_no", required=True, section="Demographics",
            page=2, page_title="Background",
        ),
        dict(
            key="work_years", prompt="Years in current employment",
            kind="number", required=True, section="Demographics",
            page=2, page_title="Background",
            condition={
                "question": "employed", "operator": "equals", "value": "Yes",
            },
        ),
        dict(
            key="stress_q1", prompt="Fictional stress statement 1",
            kind="likert5", required=True, section="Stress items", page=3, page_title="Stress scale",
            scale_id="stress", min_label="Never", max_label="Always",
            value_labels=preset_value_labels("frequency", "likert5"),
        ),
        dict(
            key="stress_q2", prompt="Fictional positively worded statement 2",
            kind="likert5", required=True, section="Stress items", page=3, page_title="Stress scale",
            scale_id="stress", reverse_scored=True,
            min_label="Never", max_label="Always",
            value_labels=preset_value_labels("frequency", "likert5"),
        ),
        dict(
            key="stress_q3", prompt="Fictional stress statement 3",
            kind="likert5", required=True, section="Stress items", page=3, page_title="Stress scale",
            scale_id="stress", min_label="Never", max_label="Always",
            value_labels=preset_value_labels("frequency", "likert5"),
        ),
    ]


def _template_questions(template: str) -> list[dict]:
    if template == "psychology":
        return _pilot_questions()
    if template == "hr":
        return [
            dict(
                key="consent", prompt="I agree to join this fictional workplace pilot.",
                kind="consent", required=True, section="Information",
            ),
            dict(
                key="department", prompt="Department",
                kind="single_choice", options=[
                    "Operations", "Office", "Other", "Prefer not to answer",
                ], required=False, section="Background",
            ),
            *[
                dict(
                    key=f"engagement_q{i}",
                    prompt=f"Fictional work engagement statement {i}",
                    kind="likert5", required=True, section="Engagement",
                    scale_id="engagement",
                    value_labels=preset_value_labels("agreement", "likert5"),
                )
                for i in range(1, 4)
            ],
            dict(
                key="suggestion", prompt="Optional improvement suggestion",
                kind="long_text", required=False, section="Feedback",
            ),
        ]
    if template == "marketing":
        return [
            dict(
                key="consent", prompt="I agree to participate in this fictional survey.",
                kind="consent", required=True, section="Information",
            ),
            dict(
                key="customer", prompt="Have you used this product?",
                kind="yes_no", required=True, section="Screening",
            ),
            dict(
                key="experience", prompt="Rate your experience",
                kind="likert5", required=True, section="Experience",
                value_labels=preset_value_labels("quality", "likert5"),
                condition={
                    "question": "customer", "operator": "equals", "value": "Yes",
                },
            ),
            dict(
                key="features", prompt="Which features matter most?",
                kind="multiple_choice", options=[
                    "Price", "Quality", "Delivery", "Service",
                ], required=False, section="Preferences",
            ),
            dict(
                key="feedback", prompt="Any additional thoughts?",
                kind="long_text", required=False, section="Feedback",
            ),
        ]
    return [
        dict(
            key="consent", prompt="I agree to take part in this fictional pilot.",
            kind="consent", required=True, section="Study information",
        ),
        dict(
            key="age", prompt="Age in years (optional)",
            kind="number", required=False, section="Demographics",
        ),
        dict(
            key="education", prompt="Education level",
            kind="single_choice", options=[
                "Secondary", "Bachelor", "Master", "Doctorate",
                "Other", "Prefer not to answer",
            ], required=False, section="Demographics",
        ),
        dict(
            key="comment", prompt="Optional feedback",
            kind="short_text", required=False, section="Feedback",
        ),
    ]


def build_survey_workspace(
    page, load_dataframe, root: str | Path, *,
    language_getter=None, translate_view=None,
    on_dataset_loaded=None, register_survey_navigation=None,
    appearance_getter=None,
):
    """Researcher workspace; UI language never alters published survey data."""
    def language():
        return language_getter() if language_getter else "en"

    def ui_label(english):
        return tr(language(), english)

    def corner_radius():
        return 10 if (
            appearance_getter and appearance_getter() == "macos"
        ) else 0

    root = Path(root)
    draft: list[dict] = []
    state = {
        "edit": None, "survey_id": None,
        "fill_items": [], "preview_items": [],
    }

    def text(value="", *, color=None, size=12, weight=None):
        return ft.Text(value, color=color, size=size, weight=weight)

    def block(title_text, controls, width=None, col=None):
        return ft.Container(
            width=width, col=col, padding=16, bgcolor="#FFFFFF",
            border=ft.Border.all(1, "#E1E7F1"),
            border_radius=corner_radius(),
            content=ft.Column(
                controls=[
                    ft.Text(title_text, weight="bold", size=16),
                    *controls,
                ],
                spacing=12,
            ),
        )

    status = ft.Text(
        "Create a draft, preview it, then save a local questionnaire.",
        size=12, color="#607087",
    )
    picker = ft.FilePicker()
    page.services.append(picker)

    title = ft.TextField(
        label="Survey title", value="Pilot wellbeing questionnaire",
        width=None,
    )
    description = ft.TextField(
        label="Participant instructions / research information",
        value=(
            "Fictional local pilot. Replace this text with study-specific "
            "information, privacy details and consent instructions."
        ),
        width=None, multiline=True,
    )
    document_import_status = ft.Text(
        "Import text-based PDF or Word (.docx) questionnaires as a draft. "
        "Scanned PDFs require OCR elsewhere. Check all questions before publishing.",
        size=12, color="#5E6D82",
    )
    document_import_preview = ft.Column(spacing=5)
    document_replace_confirm = ft.Checkbox(
        label="Replace existing unsaved draft questions",
        value=False,
    )
    document_commit_button = ft.Button(
        "Use extracted questions as editable draft", disabled=True,
    )
    extracted_document = None

    async def on_document_picker_result(event):
        nonlocal extracted_document
        files = getattr(event, "files", None) or []
        if not files:
            document_import_status.value = "Document selection cancelled."
            page.update()
            return
        picked = files[0]
        filename = Path(str(getattr(picked, "name", "questionnaire.docx"))).name
        suffix = Path(filename).suffix.lower()
        extracted_document = None
        document_commit_button.disabled = True
        document_import_preview.controls = []
        try:
            if suffix not in {".docx", ".pdf"}:
                raise ValueError("Choose a .docx or .pdf document.")
            if getattr(picked, "path", None):
                parsed = await asyncio.to_thread(
                    read_survey_document, picked.path,
                )
            else:
                data = getattr(picked, "bytes", None)
                if not isinstance(data, bytes) or len(data) > 20_000_000:
                    raise ValueError(
                        "No readable file bytes (or over 20 MB). "
                        "Use the desktop application for local-only import."
                    )
                with TemporaryDirectory(prefix="questionnaire-draft-") as tmp:
                    path = Path(tmp) / filename
                    path.write_bytes(data)
                    parsed = await asyncio.to_thread(
                        read_survey_document, path,
                    )
            extracted_document = parsed
            document_import_status.value = (
                f"Read {len(parsed.questions)} candidate question(s) from "
                f"{filename}. They are NOT published or validated."
            )
            document_import_preview.controls = [
                ft.Text(f"{i}. {q['prompt']} [{q['kind']}]",
                        selectable=True, size=12)
                for i, q in enumerate(parsed.questions[:20], 1)
            ] + [
                ft.Text(note, size=11, color="#936022")
                for note in parsed.notes
            ]
            if len(parsed.questions) > 20:
                document_import_preview.controls.append(
                    ft.Text(f"… plus {len(parsed.questions)-20} more questions")
                )
            document_commit_button.disabled = False
        except Exception as error:
            document_import_status.value = f"Document import failed: {error}"
        page.update()

    document_picker = ft.FilePicker(on_result=on_document_picker_result)
    page.services.append(document_picker)
    document_action = ft.PickFiles(
        document_picker,
        allow_multiple=False,
        file_type=ft.FilePickerFileType.CUSTOM,
        allowed_extensions=["docx", "pdf"],
        with_data=bool(getattr(page, "web", False)),
    )

    def commit_document_draft(e=None):
        if extracted_document is None:
            document_import_status.value = "Select and review a document first."
            page.update()
            return
        if draft and not document_replace_confirm.value:
            document_import_status.value = (
                "Your current draft has unsaved questions. Check the replace "
                "confirmation to overwrite that draft. Published surveys are untouched."
            )
            page.update()
            return
        try:
            # Imported documents never write to SQLite automatically.
            draft[:] = validate_questions(
                [copy.deepcopy(q) for q in extracted_document.questions]
            )
            title.value = Path(extracted_document.source_name).stem[:120]
            new_editor()
            update_draft()
            document_import_status.value = (
                f"Imported {len(draft)} editable questions. "
                "Review each question, options and scoring before publishing."
            )
            document_commit_button.disabled = True
            document_replace_confirm.value = False
            page.update()
        except Exception as error:
            document_import_status.value = f"Cannot use draft: {error}"
            page.update()

    document_commit_button.on_click = commit_document_draft

    document_import_tile = ft.ExpansionTile(
        title=ft.Text("Import questionnaire from Word / PDF"),
        expanded=False,
        controls=[
            ft.Text(
                "Local text extraction only; a scanned PDF needs OCR. "
                "Document structure, scoring and consent require "
                "researcher review before publishing.",
                size=12,
            ),
            ft.Button(
                "Choose Word / PDF questionnaire", action=document_action,
            ),
            document_import_status,
            document_import_preview,
            document_replace_confirm,
            document_commit_button,
        ],
    )

    template = ft.Dropdown(
        label="Starting template", width=270, value="psychology",
        options=[
            ft.DropdownOption(key="psychology", text="Psychology / Likert"),
            ft.DropdownOption(key="demographics", text="Demographics"),
            ft.DropdownOption(key="hr", text="HR / Workplace"),
            ft.DropdownOption(key="marketing", text="Marketing / Feedback"),
        ],
    )

    # --- Draft list and selected question editor ---
    draft_list = ft.ReorderableListView(
        height=420, spacing=7, show_default_drag_handles=True,
    )
    draft_count = text("No questions yet", color="#607087")
    section_page = ft.Dropdown(label="Page for section reorder", width=220, options=[])
    section_drag_list = ft.ReorderableListView(
        height=260, spacing=7, show_default_drag_handles=True,
    )
    editor_heading = ft.Text("New question", weight="bold", size=15)
    q_key = ft.TextField(label="Variable ID, e.g. stress_q1", width=260)
    q_prompt = ft.TextField(label="Question text", width=None)
    q_kind = ft.Dropdown(
        label="Response type", width=285, value="likert5",
        options=[ft.DropdownOption(key=k, text=name) for k, name in QUESTION_TYPES],
    )
    q_section = ft.TextField(
        label="Topic / section, e.g. Demographics", width=285,
    )
    q_page = ft.TextField(label="Page number (1–20)", value="1", width=160)
    q_page_title = ft.TextField(label="Page title, e.g. Background", width=285)
    q_required = ft.Checkbox(label="Required answer", value=True)
    q_options = ft.TextField(
        label="Options separated by semicolons", width=None, visible=False,
    )
    q_scale = ft.TextField(
        label="Scale / subscale ID, e.g. stress", width=285,
    )
    q_reverse = ft.Checkbox(
        label="Reverse-scored item (metadata only)", value=False,
    )
    q_min_label = ft.TextField(label="Low anchor (e.g. Never)", width=285)
    q_max_label = ft.TextField(label="High anchor (legacy forms)", width=285)
    q_preset = ft.Dropdown(
        label="Text scale preset", width=285, value="agreement",
        options=[
            ft.DropdownOption(key="agreement", text="Agreement"),
            ft.DropdownOption(key="quality", text="Quality: poor → good"),
            ft.DropdownOption(key="frequency", text="Frequency"),
        ],
    )
    q_value_labels = ft.TextField(
        label="Respondent labels: one numeric code = text per line",
        width=None, multiline=True, min_lines=5, max_lines=11,
    )
    q_missing_dk = ft.Checkbox(label="Offer 'Don't know' as missing", value=False)
    q_missing_pna = ft.Checkbox(
        label="Offer 'Prefer not to answer' as missing", value=False
    )
    q_missing_dk_label = ft.TextField(
        label="Don't know: respondent label", value="Don't know",
        width=285,
    )
    q_missing_pna_label = ft.TextField(
        label="Prefer not: respondent label", value="Prefer not to answer",
        width=285,
    )
    q_parent = ft.Dropdown(
        label="Show conditionally when…", width=285,
        value="always",
        options=[
            ft.DropdownOption(key="always", text="Always show"),
        ],
    )
    q_operator = ft.Dropdown(
        label="Condition operator", width=210, value="equals",
        options=[
            ft.DropdownOption(key="equals", text="Equals"),
            ft.DropdownOption(key="not_equals", text="Not equal"),
            ft.DropdownOption(key="greater", text="Greater than"),
            ft.DropdownOption(key="less", text="Less than"),
        ],
    )
    q_expected = ft.TextField(
        label="Answer value (e.g. Yes)", width=210,
    )
    editor_note = text(
        "Changing a published survey is not allowed. Clone it as a new draft.",
        color="#2755A1",
    )

    def editor_dependencies():
        limit = len(draft) if state["edit"] is None else state["edit"]
        possible = [
            q for q in draft[:limit]
            if q["kind"] in {
                "single_choice", "yes_no", "likert5", "likert7",
                "rating_scale", "number",
            }
        ]
        old = q_parent.value
        q_parent.options = [
            ft.DropdownOption(key="always", text="Always show"),
            *[
                ft.DropdownOption(
                    key=q["key"], text=f"{q['key']} — {q['prompt'][:35]}"
                )
                for q in possible
            ],
        ]
        q_parent.value = (
            old if old in {"always", *[q["key"] for q in possible]}
            else "always"
        )

    def refresh_editor_fields(e=None):
        q_options.visible = q_kind.value in {"single_choice", "multiple_choice"}
        rated = q_kind.value in {"likert5", "likert7", "rating_scale"}
        likert = q_kind.value in {"likert5", "likert7"}
        q_scale.visible = rated
        q_reverse.visible = rated
        q_min_label.visible = rated
        q_max_label.visible = rated
        q_preset.visible = likert
        q_value_labels.visible = rated
        apply_labels_button.visible = likert
        semantic_button.visible = q_kind.value == "rating_scale"
        q_missing_dk.visible = rated
        q_missing_pna.visible = rated
        q_missing_dk_label.visible = rated and q_missing_dk.value
        q_missing_pna_label.visible = rated and q_missing_pna.value
        if not rated:
            q_reverse.value = False
        if q_kind.value == "consent":
            q_required.value = True
        q_operator.visible = q_parent.value != "always"
        q_expected.visible = q_parent.value != "always"
        page.update()

    def apply_preset(e=None):
        q_value_labels.value = format_value_labels(
            preset_value_labels(
                q_preset.value or "agreement", q_kind.value, language()
            )
        )
        page.update()

    apply_labels_button = ft.Button("Use preset labels", on_click=apply_preset)
    def apply_semantic_example(e=None):
        q_value_labels.value = format_value_labels(
            semantic_differential_labels(language())
        )
        q_min_label.value = ui_label("Difficult")
        q_max_label.value = ui_label("Easy")
        page.update()

    semantic_button = ft.Button(
        "Use bipolar example −3…3", on_click=apply_semantic_example
    )
    q_kind.on_select = refresh_editor_fields
    q_parent.on_select = refresh_editor_fields
    q_missing_dk.on_change = refresh_editor_fields
    q_missing_pna.on_change = refresh_editor_fields

    def new_editor(e=None):
        state["edit"] = None
        editor_heading.value = "New question"
        q_key.value = ""
        q_prompt.value = ""
        q_kind.value = "likert5"
        q_section.value = draft[-1].get("section", "") if draft else ""
        q_page.value = str(draft[-1].get("page", 1)) if draft else "1"
        q_page_title.value = draft[-1].get("page_title", "") if draft else ""
        q_required.value = True
        q_options.value = ""
        q_scale.value = ""
        q_reverse.value = False
        q_min_label.value = ""
        q_max_label.value = ""
        q_preset.value = "agreement"
        q_value_labels.value = format_value_labels(
            preset_value_labels("agreement", "likert5", language())
        )
        q_missing_dk.value = False
        q_missing_pna.value = False
        q_missing_dk_label.value = ui_label("Don't know")
        q_missing_pna_label.value = ui_label("Prefer not to answer")
        q_parent.value = "always"
        q_operator.value = "equals"
        q_expected.value = ""
        editor_dependencies()
        refresh_editor_fields()

    def new_page_editor(e=None):
        new_editor()
        next_page = (draft[-1].get("page", 1) + 1) if draft else 1
        if next_page > 20:
            status.value = "Maximum 20 pages. Reuse an existing page."
        else:
            q_page.value = str(next_page)
            q_page_title.value = ""
            q_section.value = ""
            status.value = f"New page {next_page}: give it a title and add a question."
        page.update()

    def edit_question(index):
        state["edit"] = index
        q = draft[index]
        editor_heading.value = f"Edit question {index+1}"
        q_key.value = q["key"]
        q_prompt.value = q["prompt"]
        q_kind.value = q["kind"]
        q_section.value = q.get("section", "")
        q_page.value = str(q.get("page", 1))
        q_page_title.value = q.get("page_title", "")
        q_required.value = q["required"]
        q_options.value = "; ".join(q.get("options", []))
        q_scale.value = q.get("scale_id", "")
        q_reverse.value = q.get("reverse_scored", False)
        q_min_label.value = q.get("min_label", "")
        q_max_label.value = q.get("max_label", "")
        q_value_labels.value = format_value_labels(q.get("value_labels", {}))
        q_missing_dk.value = "DK" in q.get("missing_options", {})
        q_missing_pna.value = "PNA" in q.get("missing_options", {})
        q_missing_dk_label.value = q.get("missing_options", {}).get(
            "DK", ui_label("Don't know")
        )
        q_missing_pna_label.value = q.get("missing_options", {}).get(
            "PNA", ui_label("Prefer not to answer")
        )
        editor_dependencies()
        condition = q.get("condition")
        q_parent.value = condition["question"] if condition else "always"
        q_operator.value = condition["operator"] if condition else "equals"
        q_expected.value = (
            str(condition["value"]) if condition else ""
        )
        refresh_editor_fields()

    def move_section(page_no, old, new):
        try:
            selected_key = (
                draft[state["edit"]]["key"] if state["edit"] is not None else None
            )
            reordered = reorder_sections(draft, page_no, old, new)
            draft[:] = reordered
            state["edit"] = (
                next((i for i, item in enumerate(draft)
                      if item["key"] == selected_key), None)
                if selected_key else None
            )
            status.value = "Entire section moved; question dependencies are valid."
        except ValueError as err:
            status.value = f"Section not moved: {err}"
        update_draft()

    def update_section_list():
        pages = sorted({q.get("page", 1) for q in draft})
        previous = section_page.value
        section_page.options = [
            ft.DropdownOption(key=str(n), text=f"Page {n}") for n in pages
        ]
        section_page.value = (
            previous if previous in {str(n) for n in pages}
            else (str(pages[0]) if pages else None)
        )
        section_drag_list.controls = []
        if not section_page.value:
            return
        current = int(section_page.value)
        for index, block_items in enumerate(section_blocks(draft, current)):
            section_name = block_items[0].get("section") or "General"
            section_drag_list.controls.append(
                ft.Container(
                    key="section_" + block_items[0]["key"],
                    padding=9, border_radius=corner_radius(), bgcolor="#F5F8FD",
                    content=ft.Column(controls=[
                        ft.Text(
                            f"{section_name} · {len(block_items)} question(s)",
                            size=12, weight="bold",
                        ),
                        ft.Row(controls=[
                            ft.Button(
                                "↑", tooltip="Move section up",
                                on_click=lambda e, i=index, p=current:
                                    move_section(p, i, i-1),
                            ),
                            ft.Button(
                                "↓", tooltip="Move section down",
                                on_click=lambda e, i=index, p=current:
                                    move_section(p, i, i+1),
                            ),
                        ], spacing=6),
                    ], spacing=5),
                )
            )

    def on_section_reorder(e):
        if section_page.value:
            move_section(int(section_page.value), e.old_index, e.new_index)

    def choose_section_page(e=None):
        update_section_list()
        page.update()

    section_page.on_select = choose_section_page
    section_drag_list.on_reorder = on_section_reorder

    def update_draft():
        draft_count.value = f"{len(draft)} question(s) on {len({q.get('page', 1) for q in draft})} page(s)"
        draft_list.controls = []
        previous_page = None
        for i, q in enumerate(draft):
            current = i == state["edit"]
            page_num = q.get("page", 1)
            page_heading = q.get("page_title") or f"Page {page_num}"
            details = (
                f"{q['kind']} · {q.get('section') or 'General'}"
                + (" · reverse-keyed" if q.get("reverse_scored") else "")
                + (" · conditional" if q.get("condition") else "")
            )
            draft_list.controls.append(
                ft.Container(
                    key=f"draft_{q['key']}",
                    bgcolor="#E7EFFD" if current else "#F5F8FD",
                    border=ft.Border.all(1, "#DAE3F0"),
                    border_radius=corner_radius(), padding=10,
                    content=ft.Column(
                        controls=[
                            *(
                                [ft.Text(f"PAGE {page_num} · {page_heading}",
                                         size=11, weight="bold", color="#2755A1")]
                                if page_num != previous_page else []
                            ),
                            ft.Button(
                                f"{i+1}. {q['prompt'][:38]}",
                                on_click=lambda e, idx=i: edit_question(idx),
                            ),
                            ft.Text(q["key"] + " | " + details, size=11,
                                    color="#4B5F79"),
                        ],
                        spacing=3,
                    ),
                )
            )
            previous_page = page_num
        update_section_list()
        page.update()

    def on_question_reorder(e):
        try:
            chosen_key = (
                draft[state["edit"]]["key"]
                if state["edit"] is not None else None
            )
            moved = reorder_questions(draft, e.old_index, e.new_index)
            draft[:] = moved
            state["edit"] = (
                next((i for i, q in enumerate(draft) if q["key"] == chosen_key), None)
                if chosen_key else None
            )
            status.value = "Question order updated; conditional dependencies preserved."
        except Exception as err:
            status.value = f"Move rejected: {err}"
        update_draft()

    draft_list.on_reorder = on_question_reorder

    def draft_from_editor():
        kind = q_kind.value
        choices = (
            [x.strip() for x in (q_options.value or "").split(";")
             if x.strip()]
            if kind in {"single_choice", "multiple_choice"} else []
        )
        condition = (
            None if q_parent.value == "always" else {
                "question": q_parent.value,
                "operator": q_operator.value,
                "value": (q_expected.value or "").strip(),
            }
        )
        return {
            "key": (q_key.value or "").strip(),
            "prompt": (q_prompt.value or "").strip(),
            "kind": kind,
            "required": bool(q_required.value) or kind == "consent",
            "options": choices,
            "section": (q_section.value or "").strip(),
            "page": int((q_page.value or "").strip()),
            "page_title": (q_page_title.value or "").strip(),
            "value_labels": parse_value_labels(q_value_labels.value or "", kind),
            "missing_options": (
                {**({"DK": q_missing_dk_label.value or ""}
                     if q_missing_dk.value else {}),
                 **({"PNA": q_missing_pna_label.value or ""}
                     if q_missing_pna.value else {})}
                if kind in {"likert5", "likert7", "rating_scale"} else {}
            ),
            "scale_id": (
                (q_scale.value or "").strip()
                if kind in {"likert5", "likert7", "rating_scale"} else ""
            ),
            "reverse_scored": (
                bool(q_reverse.value)
                if kind in {"likert5", "likert7", "rating_scale"} else False
            ),
            "min_label": (q_min_label.value or "").strip(),
            "max_label": (q_max_label.value or "").strip(),
            "condition": condition,
        }

    def save_question(e):
        try:
            candidate = copy.deepcopy(draft)
            if state["edit"] is None:
                candidate.append(draft_from_editor())
                selected = len(candidate)-1
            else:
                selected = state["edit"]
                candidate[selected] = draft_from_editor()
            # Renaming a page title in-place renames the shared heading.
            if state["edit"] is not None:
                before = draft[state["edit"]]
                changed = candidate[selected]
                if (changed["page"] == before.get("page", 1)
                        and changed["page_title"] != before.get("page_title", "")):
                    for q in candidate:
                        if q["page"] == changed["page"]:
                            q["page_title"] = changed["page_title"]
            candidate = validate_questions(candidate)
            draft[:] = candidate
            status.value = f"Saved question {draft[selected]['key']} in draft."
            edit_question(selected)
            update_draft()
        except Exception as err:
            status.value = f"Question not saved: {err}"
            page.update()

    def mutate_selected(operation):
        index = state["edit"]
        if index is None:
            status.value = "Select a question in the list first."
            page.update()
            return
        proposal = copy.deepcopy(draft)
        selected = index
        if operation == "delete":
            proposal.pop(index)
            selected = None
        elif operation == "duplicate":
            duplicated = copy.deepcopy(proposal[index])
            base = duplicated["key"] + "_copy"
            key = base[:64]
            serial = 2
            while any(q["key"] == key for q in proposal):
                suffix = f"_{serial}"
                key = base[:64-len(suffix)] + suffix
                serial += 1
            duplicated["key"] = key
            proposal.insert(index+1, duplicated)
            selected = index+1
        else:
            next_index = index-1 if operation == "up" else index+1
            if not 0 <= next_index < len(proposal):
                return
            proposal[index], proposal[next_index] = (
                proposal[next_index], proposal[index]
            )
            selected = next_index
        try:
            if proposal:
                proposal = validate_questions(proposal)
            draft[:] = proposal
            if selected is None:
                new_editor()
            else:
                edit_question(selected)
            status.value = "Draft updated. Published surveys are unchanged."
            update_draft()
        except Exception as err:
            status.value = f"Cannot {operation} question: {err}"
            page.update()

    def apply_template(e):
        new = _template_questions(template.value or "psychology")
        if language() in LOCALIZED_SCALE_PRESETS:
            for question in new:
                kind = question.get("kind", "")
                if kind in {"likert5", "likert7"} and question.get("value_labels"):
                    for name in SCALE_PRESETS:
                        if question["value_labels"] == preset_value_labels(name, kind):
                            question["value_labels"] = preset_value_labels(
                                name, kind, language()
                            )
                            break
                for field in (
                    "prompt", "section", "page_title", "min_label", "max_label"
                ):
                    if question.get(field):
                        question[field] = ui_label(question[field])
        draft[:] = validate_questions(new)
        new_editor()
        status.value = (
            "Loaded an ORIGINAL fictional practice template. "
            "Review prompts, consent and scoring before real research."
        )
        update_draft()

    saved_picker = ft.Dropdown(
        label="Published questionnaires on this computer",
        width=None, options=[],
    )
    published_info = ft.Text("", color="#4B5F79", size=12)
    preview_title = ft.Text("", weight="bold", size=19)
    preview_description = ft.Text("", color="#4B5F79")
    preview_form = ft.Column(spacing=10)
    preview_note = ft.Text("")
    fill_title = ft.Text("", weight="bold", size=19)
    fill_info = ft.Text("")
    fill_form = ft.Column(spacing=12)
    fill_status = ft.Text("")
    fill_submit_button = ft.Button("Submit response locally")
    response_count_text = ft.Text("")
    response_table = ft.Column(spacing=8)
    response_status = ft.Text("")
    response_hint = ft.Text(
        "For real participant research, document ethical approval, "
        "appropriate consent and data-retention procedures.",
        color="#2755A1", size=12,
    )

    def read_widget(entry):
        q = entry["question"]
        if q["kind"] == "multiple_choice":
            return [
                cb.label for cb in entry["input"]
                if cb.value
            ]
        value = entry["input"].value
        return bool(value) if q["kind"] == "consent" else value

    def context_value(question, value):
        if value is None or value == "":
            return None
        kind = question["kind"]
        if kind in {"likert5", "likert7", "rating_scale"}:
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        if kind == "number":
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return value

    def make_form(questions, *, mode):
        """Build a respondent form with topic headings and local page navigation."""
        entries = []
        state[f"{mode}_items"] = entries
        pages = sorted({q.get("page", 1) for q in questions})
        page_panels = {}
        page_title_map = {
            q.get("page", 1): q.get("page_title") or f"Page {q.get('page', 1)}"
            for q in questions
        }
        page_heading = ft.Text("", weight="bold", size=17)
        page_progress = ft.Text("", color="#607087", size=12)
        progress_bar = ft.ProgressBar(
            value=0, color="#2755A1", bgcolor="#DFE7F3", height=7,
        )
        nav_note = ft.Text("", color="#A94E16", size=12)
        back_button = ft.Button("← Previous")
        next_button = ft.Button("Next →")

        def update_visibility(e=None, *, refresh=True):
            earlier = {}
            for entry in entries:
                q = entry["question"]
                visible = question_is_visible(q, earlier)
                entry["container"].visible = visible
                earlier[q["key"]] = (
                    context_value(q, read_widget(entry)) if visible else None
                )
            if refresh:
                page.update()

        def render_current_page(*, refresh=True):
            current = state[f"{mode}_page"]
            for number, panel in page_panels.items():
                panel.visible = number == current
            page_heading.value = page_title_map[current]
            page_progress.value = (
                f"{ui_label('Page')} {pages.index(current)+1} "
                f"{ui_label('of')} {len(pages)}"
            )
            progress_bar.value = (pages.index(current)+1) / len(pages)
            back_button.visible = current != pages[0]
            next_button.visible = current != pages[-1]
            if mode == "fill":
                fill_submit_button.visible = current == pages[-1]
            if refresh:
                page.update()

        def change_page(direction):
            current = state[f"{mode}_page"]
            if direction > 0:
                try:
                    answers = {entry["question"]["key"]: read_widget(entry)
                               for entry in entries}
                    validate_page_answers(questions, answers, current)
                except ValueError as err:
                    nav_note.value = f"Complete this page before continuing: {err}"
                    page.update()
                    return
            target_index = pages.index(current) + direction
            if 0 <= target_index < len(pages):
                state[f"{mode}_page"] = pages[target_index]
                nav_note.value = ""
                render_current_page()

        back_button.on_click = lambda e: change_page(-1)
        next_button.on_click = lambda e: change_page(1)
        for number in pages:
            page_panels[number] = ft.Column(
                spacing=13, visible=number == pages[0]
            )
        last_section_by_page = {}
        for q in questions:
            page_number = q.get("page", 1)
            body = page_panels[page_number]
            section = q.get("section") or ui_label("General")
            if section != last_section_by_page.get(page_number):
                body.controls.append(
                    ft.Text(section.upper(), size=12, weight="bold",
                            color="#2755A1")
                )
                last_section_by_page[page_number] = section

            label = q["prompt"] + (" *" if q["required"] else "")
            kind = q["kind"]
            if kind in {"likert5", "likert7", "rating_scale"}:
                field = build_numeric_rating_selector(
                    q, on_change=update_visibility,
                )
                endpoint_note = (
                    f"{q.get('min_label') or ''}  —  {q.get('max_label') or ''}"
                    if kind == "rating_scale" and (
                        q.get("min_label") or q.get("max_label")
                    ) else ""
                )
                field_controls = [field] + (
                    [ft.Text(endpoint_note, size=12, color="#51637B")]
                    if endpoint_note else []
                )
            elif kind in {"single_choice", "yes_no"}:
                values = ["Yes", "No"] if kind == "yes_no" else q["options"]
                field = ft.Dropdown(
                    label="Choose one answer", width=None,
                    options=[
                        ft.DropdownOption(
                            key=v, text=ui_label(v) if kind == "yes_no" else v
                        )
                        for v in values
                    ],
                    on_select=update_visibility,
                )
                field_controls = [field]
            elif kind == "multiple_choice":
                field = [
                    ft.Checkbox(label=v, value=False, on_change=update_visibility)
                    for v in q["options"]
                ]
                field_controls = [ft.Column(controls=field, spacing=5)]
            elif kind == "consent":
                field = ft.Checkbox(
                    label="I agree", value=False, on_change=update_visibility,
                )
                field_controls = [field]
            else:
                field = ft.TextField(
                    label="Your answer", width=None,
                    on_change=update_visibility,
                    multiline=kind == "long_text",
                    hint_text="YYYY-MM-DD" if kind == "date" else None,
                )
                field_controls = [field]

            container = ft.Container(
                padding=16, border_radius=corner_radius(), bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#DDE6F1"),
                content=ft.Column(
                    controls=[
                        ft.Text(label, size=14, weight="bold"),
                        *field_controls,
                    ],
                    spacing=9,
                ),
            )
            body.controls.append(container)
            entries.append({
                "question": q, "input": field, "container": container,
            })
        state[f"{mode}_page"] = pages[0]
        body = ft.Column(
            controls=[
                page_heading, page_progress, progress_bar,
                *[page_panels[number] for number in pages],
                ft.Row(controls=[back_button, next_button], wrap=True, spacing=10),
                nav_note,
            ],
            spacing=12,
        )
        # Build the complete control tree before asking Flet to repaint.
        # Updating the Page while these controls are still unmounted can
        # trigger "Frozen controls cannot be updated" in Flet 1.x.
        update_visibility(refresh=False)
        render_current_page(refresh=False)
        return body

    def show_preview(e=None):
        try:
            if draft:
                questions = validate_questions(draft)
                preview_title.value = title.value or "Untitled draft"
                preview_description.value = description.value or ""
                preview_note.value = (
                    "Preview only. No answers are stored. "
                    "Reverse-scored marks affect the codebook, not raw responses."
                )
            elif state["survey_id"]:
                published = get_survey(root, state["survey_id"])
                questions = list(published.questions)
                preview_title.value = published.title
                preview_description.value = published.description
                preview_note.value = "Published form preview. No answers are stored."
            else:
                preview_note.value = "Create a draft or select a saved questionnaire."
                preview_form.controls.clear()
                return
            form = make_form(questions, mode="preview")
            if translate_view is not None:
                # Translate only freshly constructed, unmounted controls.
                # Never retranslate a previously mounted Flet tree on each tab.
                translate_view(form)
            preview_form.controls = [form]
        except Exception as err:
            preview_note.value = f"Cannot preview: {err}"
            preview_form.controls.clear()
        # select_view() publishes the completed pane and updates the page once.
        # Do not flush the partially attached form here.

    def refresh_saved(selected=None):
        published = list_surveys(root)
        saved_picker.options = [
            ft.DropdownOption(
                key=s.survey_id, text=f"{s.title}  ·  {s.survey_id[:8]}"
            )
            for s in published
        ]
        ids = [s.survey_id for s in published]
        if selected in ids:
            saved_picker.value = selected
        elif saved_picker.value in ids:
            pass
        else:
            saved_picker.value = ids[-1] if ids else None
        state["survey_id"] = saved_picker.value
        show_published()
        page.update()

    def show_published(e=None):
        state["survey_id"] = saved_picker.value
        if not state["survey_id"]:
            published_info.value = "No published questionnaires yet."
            fill_title.value = ""
            fill_info.value = ""
            fill_form.controls.clear()
            state["fill_items"] = []
            update_response_table()
            return
        try:
            definition = get_survey(root, state["survey_id"])
            count = response_count(root, state["survey_id"])
            published_info.value = (
                f"{len(definition.questions)} questions · "
                f"{count} local response(s) · schema locked after publishing."
            )
            fill_title.value = definition.title
            fill_info.value = definition.description
            form = make_form(list(definition.questions), mode="fill")
            if translate_view is not None:
                translate_view(form)
            fill_form.controls = [form]
            fill_status.value = ""
            update_response_table()
        except Exception as err:
            published_info.value = f"Could not load survey: {err}"
        page.update()

    saved_picker.on_select = show_published

    def publish(e):
        try:
            normalized = validate_questions(draft)
            definition = create_survey(
                root, title.value or "", description.value or "", normalized
            )
            draft.clear()
            new_editor()
            update_draft()
            refresh_saved(definition.survey_id)
            status.value = (
                f"Created '{definition.title}' locally. Saved questions are "
                "locked to preserve response integrity; clone to make revisions."
            )
        except Exception as err:
            status.value = f"Publish error: {err}"
        page.update()

    def clone_saved(e):
        sid = state["survey_id"]
        if not sid:
            status.value = "Choose a published questionnaire first."
            page.update()
            return
        definition = get_survey(root, sid)
        draft[:] = copy.deepcopy(list(definition.questions))
        title.value = definition.title + " (revised)"
        description.value = definition.description
        new_editor()
        update_draft()
        status.value = (
            "Copied questionnaire to a NEW draft. Existing responses "
            "are preserved in the original survey."
        )
        select_view("build")

    def submit(e):
        sid = state["survey_id"]
        if not sid:
            fill_status.value = "Select a published questionnaire first."
            page.update()
            return
        try:
            answers = {
                entry["question"]["key"]: read_widget(entry)
                for entry in state["fill_items"]
            }
            submit_response(root, sid, answers)
            show_published()  # Discard previous answer widgets on success.
            fill_status.value = (
                f"Response recorded locally. Total: {response_count(root, sid)}."
            )
        except Exception as err:
            fill_status.value = f"Not saved: {err}"
        page.update()

    fill_submit_button.on_click = submit

    def update_response_table():
        sid = state["survey_id"]
        response_table.controls.clear()
        if not sid:
            response_count_text.value = "Select a saved survey."
            return
        try:
            frame = responses_dataframe(root, sid)
            response_count_text.value = (
                f"{len(frame)} response(s) · {frame.shape[1]-1} question columns"
            )
            if frame.empty:
                response_table.controls.append(
                    ft.Text("No answers yet. Use Preview / Fill to enter a test response.")
                )
                return
            subset = frame.iloc[:10, :7]
            response_table.controls.append(
                ft.DataTable(
                    columns=[
                        ft.DataColumn(label=ft.Text(str(col)[:20]))
                        for col in subset.columns
                    ],
                    rows=[
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(
                                "—" if pd.isna(v) else str(v)[:35]
                            ))
                            for v in row
                        ])
                        for row in subset.itertuples(index=False, name=None)
                    ],
                )
            )
            if len(frame) > 10 or frame.shape[1] > 7:
                response_table.controls.append(
                    ft.Text(
                        "Preview shows the first 10 rows and 7 columns. "
                        "Export CSV for the complete dataset.",
                        size=12, color="#607087",
                    )
                )
        except Exception as err:
            response_count_text.value = f"Could not read responses: {err}"

    async def load_responses(e):
        sid = state["survey_id"]
        if not sid:
            response_status.value = "Select a saved questionnaire."
            page.update()
            return
        try:
            frame = await asyncio.to_thread(responses_dataframe, root, sid)
            if frame.empty:
                raise ValueError("No submitted responses to analyze.")
            # Label the dataset in the main app without adding a fake
            # respondent column or changing any of the numeric answers.
            definition = await asyncio.to_thread(get_survey, root, sid)
            frame.attrs["research_source_name"] = (
                f"Questionnaire: {definition.title}"
            )
            loaded = await load_dataframe(frame)
            if loaded is not True:
                raise ValueError(
                    "Dataset did not accept the questionnaire responses. "
                    "The previous dataset remains active; check the import status."
                )
            response_status.value = (
                f"Loaded {len(frame)} local responses into Dataset. "
                "Raw scale answers are not reverse-scored automatically."
            )
            if on_dataset_loaded is not None:
                # Only navigate after confirmation that the dataset was
                # actually accepted; never leave Survey on a failed import.
                on_dataset_loaded()
        except Exception as err:
            response_status.value = f"Import error: {err}"
        page.update()

    async def export_responses(e):
        sid = state["survey_id"]
        if not sid:
            response_status.value = "Select a saved questionnaire."
            page.update()
            return
        try:
            path = await picker.save_file(
                dialog_title="Save questionnaire CSV and variable codebook",
                file_name="survey_responses.csv",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv"],
            )
            if path:
                output = await asyncio.to_thread(save_survey_csv, root, sid, path)
                codebook_path = output.with_name(output.stem + "_codebook.json")
                await asyncio.to_thread(
                    save_survey_codebook, root, sid, codebook_path,
                )
                response_status.value = (
                    f"CSV: {output}\nCodebook: {codebook_path}"
                )
        except Exception as err:
            response_status.value = f"Export error: {err}"
        page.update()

    # Responsive layout: on narrow windows the editor stacks below the list.
    build_view = ft.Column(
        controls=[
            block("1. Survey details", [
                title, description,
                ft.Row(
                    controls=[
                        template,
                        ft.Button("Load template", on_click=apply_template),
                    ],
                    wrap=True, spacing=12,
                ),
                document_import_tile,
            ]),
            ft.ResponsiveRow(
                columns=12, spacing=12, run_spacing=12,
                controls=[
                    block("2. Questions", [
                        draft_count,
                        ft.Text("Drag the handle to reorder. Use Move up/down "
                                "for keyboard access.", size=11, color="#607087"),
                        ft.Row(controls=[
                            ft.Button("+ New question", on_click=new_editor),
                            ft.Button("+ New page", on_click=new_page_editor),
                        ], wrap=True, spacing=6),
                        draft_list,
                    ], col={"xs": 12, "md": 5, "lg": 4}),
                    block("3. Question editor", [
                        editor_heading,
                        ft.Row(
                            controls=[q_key, q_kind], wrap=True, spacing=10
                        ),
                        q_prompt,
                        ft.Row(
                            controls=[q_section, q_page, q_page_title],
                            wrap=True, spacing=10,
                        ),
                        ft.Text("Group questions by topic and assign consecutive "
                                "pages, starting with page 1.", size=11,
                                color="#607087"),
                        q_options,
                        q_required,
                        ft.Row(
                            controls=[q_scale, q_reverse], wrap=True,
                        ),
                        ft.Row(
                            controls=[q_preset, apply_labels_button, semantic_button],
                            wrap=True, spacing=10,
                        ),
                        q_value_labels,
                        ft.Row(
                            controls=[q_missing_dk, q_missing_dk_label],
                            wrap=True, spacing=8,
                        ),
                        ft.Row(
                            controls=[q_missing_pna, q_missing_pna_label],
                            wrap=True, spacing=8,
                        ),
                        ft.Text(
                            "Use all numeric labels for Likert, or 2–11 custom "
                            "integer codes (e.g. −3…3). Missing options are "
                            "NOT scores; they export as NaN plus reason codes.",
                            size=11, color="#607087",
                        ),
                        ft.Row(
                            controls=[q_min_label, q_max_label], wrap=True,
                        ),
                        q_parent,
                        ft.Row(
                            controls=[q_operator, q_expected], wrap=True,
                        ),
                        ft.Row(controls=[
                            ft.Button("Save question", on_click=save_question),
                            ft.Button(
                                "Duplicate",
                                on_click=lambda e: mutate_selected("duplicate"),
                            ),
                            ft.Button(
                                "Move up",
                                on_click=lambda e: mutate_selected("up"),
                            ),
                            ft.Button(
                                "Move down",
                                on_click=lambda e: mutate_selected("down"),
                            ),
                            ft.Button(
                                "Remove",
                                on_click=lambda e: mutate_selected("delete"),
                            ),
                        ], wrap=True, spacing=8),
                        editor_note,
                    ], col={"xs": 12, "md": 7, "lg": 8}),
                ],
            ),
            block("4. Reorder entire topic sections", [
                ft.Text(
                    "Drag a section handle to move all of its questions "
                    "within the selected page. Use ↑/↓ if needed. Moves that "
                    "break conditional dependencies are rejected.",
                    size=12, color="#607087",
                ),
                section_page,
                section_drag_list,
            ]),
            block("5. Finish the draft", [
                ft.Text(
                    "Preview pages and respondent-visible answer labels before "
                    "publishing. Saved definitions stay immutable; Clone to revise.",
                    size=12, color="#607087",
                ),
                ft.Row(controls=[
                    ft.Button(
                        "Preview draft", on_click=lambda e: select_view("preview"),
                    ),
                    ft.Button(
                        "Create local questionnaire", on_click=publish,
                    ),
                ], wrap=True, spacing=10),
            ]),
        ],
        spacing=14,
    )
    preview_view = ft.Column(
        controls=[
            block("Respondent preview", [
                preview_title, preview_description, preview_note,
                preview_form,
                ft.Text(
                    "Preview mode never saves submissions.",
                    color="#2755A1",
                ),
            ]),
        ],
        visible=False, spacing=14,
    )
    fill_view = ft.Column(
        controls=[
            block("Select a saved questionnaire", [
                saved_picker,
                published_info,
                ft.Button(
                    "Clone published survey into editable draft",
                    on_click=clone_saved,
                ),
            ]),
            block("Enter a participant response on this computer", [
                fill_title, fill_info, fill_form,
                fill_submit_button,
                fill_status,
            ]),
        ],
        visible=False, spacing=14,
    )
    responses_view = ft.Column(
        controls=[
            block("Collected responses", [
                ft.Button(
                    "Refresh response table",
                    on_click=lambda e: (update_response_table(), page.update()),
                ),
                response_count_text,
                response_table,
                ft.Row(
                    controls=[
                        ft.Button(
                            "Load responses into Dataset",
                            on_click=load_responses,
                        ),
                        ft.Button(
                            "Export CSV + codebook",
                            on_click=export_responses,
                        ),
                    ], wrap=True, spacing=10,
                ),
                response_status,
                response_hint,
            ]),
        ],
        visible=False, spacing=14,
    )
    panes = {
        "build": build_view, "preview": preview_view,
        "fill": fill_view, "responses": responses_view,
    }

    def select_view(which):
        for name, pane in panes.items():
            pane.visible = name == which
            if name in tab_buttons:
                tab_buttons[name].style = ft.ButtonStyle(
                    bgcolor="#DFEAFB" if name == which else "#FFFFFF",
                    color="#1C4D9A" if name == which else "#425873",
                )
        if which == "preview":
            show_preview()
        if which == "responses":
            update_response_table()
        # The shell was translated when created or on explicit language
        # change; updating all its mounted controls during every tab switch
        # is unnecessary and unsafe under Flet 1.x's frozen-control model.
        page.update()

    tab_names = {
        "build": "1. Build", "preview": "2. Preview",
        "fill": "3. Fill survey", "responses": "4. Responses & export",
    }
    tab_buttons = {
        name: ft.Button(
            label, on_click=lambda e, target=name: select_view(target),
        ) for name, label in tab_names.items()
    }
    navigation = ft.Row(
        controls=list(tab_buttons.values()), wrap=True, spacing=10,
    )
    view = ft.Column(
        controls=[
            ft.Container(
                width=None, padding=15, border_radius=corner_radius(),
                bgcolor="#EDF3FF",
                content=ft.Column(controls=[
                    ft.Text(
                        "LOCAL QUESTIONNAIRE WORKSPACE",
                        weight="bold", size=12, color="#2755A1",
                    ),
                    ft.Text(
                        "Create forms, preview conditional questions, collect "
                        "local responses and analyze without Google Forms.",
                        size=13,
                    ),
                    ft.Text(
                        "No public URL or remote collection. For real participant "
                        "data, review consent, privacy, access and retention first.",
                        size=12, color="#607087",
                    ),
                    navigation,
                ], spacing=8),
            ),
            build_view, preview_view, fill_view, responses_view,
            status,
        ],
        width=None, spacing=15,
    )
    new_editor()
    update_draft()
    refresh_saved()
    select_view("build")
    if register_survey_navigation is not None:
        def open_document_import():
            document_import_tile.expanded = True
            select_view("build")

        register_survey_navigation({
            "import": open_document_import,
            "responses": lambda: select_view("responses"),
        })
    if translate_view is not None:
        translate_view(view)
    return view
