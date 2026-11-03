"""Focused local questionnaire editor, realistic preview and response workspace.

Four views replace one long mixed-purpose form. The respondent preview does
not write any test answers. Published local survey schemas stay immutable;
researchers can clone a published form into a fresh editable draft.
"""

import asyncio
import copy
from pathlib import Path

import flet as ft
import pandas as pd

from survey_storage import (
    validate_questions, create_survey, get_survey, list_surveys,
    submit_response, response_count, responses_dataframe, save_survey_csv,
    save_survey_codebook, question_is_visible, likert_choices,
    reorder_questions, validate_page_answers,
)


QUESTION_TYPES = [
    ("likert5", "Likert scale 1–5"),
    ("likert7", "Likert scale 1–7"),
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


def preset_value_labels(name: str, kind: str) -> dict[str, str]:
    """Return full respondent-facing labels for stable numeric response codes."""
    if kind not in {"likert5", "likert7"}:
        raise ValueError("Presets only apply to Likert scales.")
    return {str(i): label for i, label in enumerate(
        SCALE_PRESETS[name][int(kind[-1])], start=1
    )}


def format_value_labels(labels: dict[str, str]) -> str:
    return "\n".join(f"{code} = {label}" for code, label in labels.items())


def parse_value_labels(raw: str, kind: str) -> dict[str, str]:
    """Parse one numeric code = text per line, with complete coverage."""
    if kind not in {"likert5", "likert7"} or not raw.strip():
        return {}
    labels = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        if "=" not in line:
            raise ValueError("Use one choice per line, e.g. 1 = Very poor.")
        code, label = (part.strip() for part in line.split("=", 1))
        if not code.isascii() or not code.isdigit() or code in labels:
            raise ValueError("Every scale code must be a unique integer.")
        labels[code] = label
    expected = {str(n) for n in range(1, int(kind[-1]) + 1)}
    if set(labels) != expected:
        raise ValueError("Label every code in this Likert scale.")
    return labels


def _pilot_questions():
    """Original fictional practice items, not a validated clinical instrument."""
    return [
        dict(
            key="consent", prompt="I agree to take part in this fictional pilot.",
            kind="consent", required=True, section="Study information",
        ),
        dict(
            key="age", prompt="Your age in years (optional)",
            kind="number", required=False, section="Demographics",
        ),
        dict(
            key="group", prompt="Fictional study group",
            kind="single_choice", options=["A", "B"], required=True,
            section="Demographics",
        ),
        dict(
            key="employed", prompt="Are you currently employed?",
            kind="yes_no", required=True, section="Demographics",
        ),
        dict(
            key="work_years", prompt="Years in current employment",
            kind="number", required=True, section="Demographics",
            condition={
                "question": "employed", "operator": "equals", "value": "Yes",
            },
        ),
        dict(
            key="stress_q1", prompt="Fictional stress statement 1",
            kind="likert5", required=True, section="Stress items",
            scale_id="stress", min_label="Never", max_label="Always",
            value_labels=preset_value_labels("frequency", "likert5"),
        ),
        dict(
            key="stress_q2", prompt="Fictional positively worded statement 2",
            kind="likert5", required=True, section="Stress items",
            scale_id="stress", reverse_scored=True,
            min_label="Never", max_label="Always",
            value_labels=preset_value_labels("frequency", "likert5"),
        ),
        dict(
            key="stress_q3", prompt="Fictional stress statement 3",
            kind="likert5", required=True, section="Stress items",
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


def build_survey_workspace(page, load_dataframe, root: str | Path):
    root = Path(root)
    draft: list[dict] = []
    state = {
        "edit": None, "survey_id": None,
        "fill_items": [], "preview_items": [],
    }

    def text(value="", *, color=None, size=12, weight=None):
        return ft.Text(value, color=color, size=size, weight=weight)

    def block(title_text, controls, width=980):
        return ft.Container(
            width=width, padding=18, bgcolor="#192638", border_radius=14,
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
        size=12, color="#A8B6C9",
    )
    picker = ft.FilePicker()
    page.services.append(picker)

    title = ft.TextField(
        label="Survey title", value="Pilot wellbeing questionnaire",
        width=780,
    )
    description = ft.TextField(
        label="Participant instructions / research information",
        value=(
            "Fictional local pilot. Replace this text with study-specific "
            "information, privacy details and consent instructions."
        ),
        width=780, multiline=True,
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
    draft_count = text("No questions yet", color="#A8B6C9")
    editor_heading = ft.Text("New question", weight="bold", size=15)
    q_key = ft.TextField(label="Variable ID, e.g. stress_q1", width=260)
    q_prompt = ft.TextField(label="Question text", width=580)
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
        label="Options separated by semicolons", width=580, visible=False,
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
        width=580, multiline=True, min_lines=5, max_lines=8,
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
        color="#9CB7DA",
    )

    def editor_dependencies():
        limit = len(draft) if state["edit"] is None else state["edit"]
        possible = [
            q for q in draft[:limit]
            if q["kind"] in {
                "single_choice", "yes_no", "likert5", "likert7", "number",
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
        likert = q_kind.value in {"likert5", "likert7"}
        q_scale.visible = likert
        q_reverse.visible = likert
        q_min_label.visible = likert
        q_max_label.visible = likert
        q_preset.visible = likert
        q_value_labels.visible = likert
        apply_labels_button.visible = likert
        if not likert:
            q_reverse.value = False
        if q_kind.value == "consent":
            q_required.value = True
        q_operator.visible = q_parent.value != "always"
        q_expected.visible = q_parent.value != "always"
        page.update()

    def apply_preset(e=None):
        q_value_labels.value = format_value_labels(
            preset_value_labels(q_preset.value or "agreement", q_kind.value)
        )
        page.update()

    apply_labels_button = ft.Button("Use preset labels", on_click=apply_preset)
    q_kind.on_select = refresh_editor_fields
    q_parent.on_select = refresh_editor_fields

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
            preset_value_labels("agreement", "likert5")
        )
        q_parent.value = "always"
        q_operator.value = "equals"
        q_expected.value = ""
        editor_dependencies()
        refresh_editor_fields()

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
        editor_dependencies()
        condition = q.get("condition")
        q_parent.value = condition["question"] if condition else "always"
        q_operator.value = condition["operator"] if condition else "equals"
        q_expected.value = (
            str(condition["value"]) if condition else ""
        )
        refresh_editor_fields()

    def update_draft():
        draft_count.value = f"{len(draft)} question(s) in this draft"
        draft_list.controls = []
        for i, q in enumerate(draft):
            current = i == state["edit"]
            details = (
                f"{q['kind']} · {q.get('section') or 'General'}"
                + (" · reverse-keyed" if q.get("reverse_scored") else "")
                + (" · conditional" if q.get("condition") else "")
            )
            draft_list.controls.append(
                ft.Container(
                    bgcolor="#30415A" if current else "#1E2D41",
                    border_radius=8, padding=10,
                    content=ft.Column(
                        controls=[
                            ft.Button(
                                f"{i+1}. {q['prompt'][:45]}",
                                on_click=lambda e, idx=i: edit_question(idx),
                            ),
                            ft.Text(q["key"] + " | " + details, size=11,
                                    color="#B8C7D9"),
                        ],
                        spacing=3,
                    ),
                )
            )
        page.update()

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
            "scale_id": (
                (q_scale.value or "").strip()
                if kind in {"likert5", "likert7"} else ""
            ),
            "reverse_scored": (
                bool(q_reverse.value) if kind in {"likert5", "likert7"} else False
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
        draft[:] = validate_questions(new)
        new_editor()
        status.value = (
            "Loaded an ORIGINAL fictional practice template. "
            "Review prompts, consent and scoring before real research."
        )
        update_draft()

    saved_picker = ft.Dropdown(
        label="Published questionnaires on this computer",
        width=690, options=[],
    )
    published_info = ft.Text("", color="#B8C7D9", size=12)
    preview_title = ft.Text("", weight="bold", size=19)
    preview_description = ft.Text("", color="#B8C7D9")
    preview_form = ft.Column(spacing=10)
    preview_note = ft.Text("")
    fill_title = ft.Text("", weight="bold", size=19)
    fill_info = ft.Text("")
    fill_form = ft.Column(spacing=12)
    fill_status = ft.Text("")
    response_count_text = ft.Text("")
    response_table = ft.Column(spacing=8)
    response_status = ft.Text("")
    response_hint = ft.Text(
        "For real participant research, document ethical approval, "
        "appropriate consent and data-retention procedures.",
        color="#9CB7DA", size=12,
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
        if kind in {"likert5", "likert7"}:
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
        """Build an actual response form; no entries are saved in preview."""
        entries = []
        body = ft.Column(spacing=14)
        state[f"{mode}_items"] = entries

        def update_visibility(e=None):
            earlier = {}
            for entry in entries:
                q = entry["question"]
                visible = question_is_visible(q, earlier)
                entry["container"].visible = visible
                earlier[q["key"]] = (
                    context_value(q, read_widget(entry)) if visible else None
                )
            page.update()

        last_section = None
        for i, q in enumerate(questions):
            section = q.get("section") or "General"
            if section != last_section:
                body.controls.append(
                    ft.Text(section.upper(), size=12, weight="bold",
                            color="#9CB7DA")
                )
                last_section = section
            label = q["prompt"] + (" *" if q["required"] else "")
            kind = q["kind"]
            if kind in {"likert5", "likert7"}:
                max_value = int(kind[-1])
                field = ft.Dropdown(
                    label=label, width=620,
                    options=[
                        ft.DropdownOption(key=str(n), text=str(n))
                        for n in range(1, max_value+1)
                    ],
                    on_select=update_visibility,
                )
                note = (
                    f"1 = {q.get('min_label') or 'lowest'}"
                    f"   ·   {max_value} = {q.get('max_label') or 'highest'}"
                )
                field_controls = [field, ft.Text(note, size=11, color="#A8B6C9")]
            elif kind in {"single_choice", "yes_no"}:
                values = (
                    ["Yes", "No"] if kind == "yes_no" else q["options"]
                )
                field = ft.Dropdown(
                    label=label, width=620,
                    options=[
                        ft.DropdownOption(key=v, text=v) for v in values
                    ],
                    on_select=update_visibility,
                )
                field_controls = [field]
            elif kind == "multiple_choice":
                field = [
                    ft.Checkbox(label=v, value=False,
                                on_change=update_visibility)
                    for v in q["options"]
                ]
                field_controls = [
                    ft.Text(label, size=14),
                    ft.Column(controls=field, spacing=5),
                ]
            elif kind == "consent":
                field = ft.Checkbox(
                    label=label, value=False,
                    on_change=update_visibility,
                )
                field_controls = [field]
            else:
                field = ft.TextField(
                    label=label, width=620,
                    on_change=update_visibility,
                    multiline=kind == "long_text",
                    hint_text="YYYY-MM-DD" if kind == "date" else None,
                )
                field_controls = [field]
            container = ft.Container(
                padding=12, border_radius=10, bgcolor="#1E2D41",
                content=ft.Column(controls=field_controls, spacing=6),
            )
            body.controls.append(container)
            entries.append({
                "question": q, "input": field, "container": container,
            })
        update_visibility()
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
            preview_form.controls = [
                make_form(questions, mode="preview")
            ]
        except Exception as err:
            preview_note.value = f"Cannot preview: {err}"
            preview_form.controls.clear()
        page.update()

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
            fill_form.controls = [
                make_form(list(definition.questions), mode="fill")
            ]
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
                        size=12, color="#A8B6C9",
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
            await load_dataframe(frame)
            response_status.value = (
                f"Loaded {len(frame)} local responses into Dataset. "
                "Raw scale answers are not reverse-scored automatically."
            )
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

    # The four focused views share one fixed-width content column.
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
            ]),
            ft.Row(
                controls=[
                    block("2. Questions", [
                        draft_count,
                        ft.Button("+ New question", on_click=new_editor),
                        draft_list,
                    ], width=350),
                    block("3. Question editor", [
                        editor_heading,
                        ft.Row(
                            controls=[q_key, q_kind], wrap=True, spacing=10
                        ),
                        q_prompt,
                        q_section,
                        q_options,
                        q_required,
                        ft.Row(
                            controls=[q_scale, q_reverse], wrap=True,
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
                    ], width=600),
                ],
                spacing=12, wrap=True,
            ),
            block("4. Finish the draft", [
                ft.Text(
                    "Preview the form before publishing. Saved definitions "
                    "cannot be edited in place; use Clone to revise.",
                    size=12, color="#A8B6C9",
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
                    color="#9CB7DA",
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
                ft.Button("Submit response locally", on_click=submit),
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
        if which == "preview":
            show_preview()
        if which == "responses":
            update_response_table()
        page.update()

    navigation = ft.Row(
        controls=[
            ft.Button("Build", on_click=lambda e: select_view("build")),
            ft.Button("Preview", on_click=lambda e: select_view("preview")),
            ft.Button("Fill survey", on_click=lambda e: select_view("fill")),
            ft.Button("Responses / Export",
                      on_click=lambda e: select_view("responses")),
        ], wrap=True, spacing=10,
    )
    view = ft.Column(
        controls=[
            ft.Container(
                width=980, padding=15, border_radius=12,
                bgcolor="#152030",
                content=ft.Column(controls=[
                    ft.Text(
                        "LOCAL QUESTIONNAIRE WORKSPACE",
                        weight="bold", size=12, color="#9CB7DA",
                    ),
                    ft.Text(
                        "Create forms, preview conditional questions, collect "
                        "local responses and analyze without Google Forms.",
                        size=13,
                    ),
                    ft.Text(
                        "No public URL or remote collection. For real participant "
                        "data, review consent, privacy, access and retention first.",
                        size=12, color="#A8B6C9",
                    ),
                    navigation,
                ], spacing=8),
            ),
            build_view, preview_view, fill_view, responses_view,
            status,
        ],
        width=1010, spacing=15,
    )
    new_editor()
    update_draft()
    refresh_saved()
    return view
