"""Local survey form builder and respondent-entry view for Flet desktop.

This MVP runs on the current device. It does not publish an online URL.
Individual answers are validated and saved transactionally to local SQLite.
"""

import asyncio
from pathlib import Path

import flet as ft

from survey_storage import (
    validate_questions, create_survey, get_survey, list_surveys,
    submit_response, response_count, responses_dataframe, save_survey_csv,
)


def build_survey_workspace(page, load_dataframe, root: str | Path):
    root = Path(root)
    draft = []
    current = {"id": None, "widgets": {}}

    title = ft.TextField(
        label="Survey title", width=500, value="Pilot wellbeing questionnaire",
    )
    description = ft.TextField(
        label="Participant instructions / study information",
        width=700,
        value="Fictional pilot form. For research use, provide study-specific information and consent.",
    )
    question_key = ft.TextField(
        label="Variable name (e.g. stress_q1)", width=280
    )
    question_prompt = ft.TextField(
        label="Question text", width=600
    )
    kind = ft.Dropdown(
        label="Answer format", width=290, value="likert5",
        options=[
            ft.DropdownOption(key="likert5", text="Likert 1–5"),
            ft.DropdownOption(key="single_choice", text="Single choice"),
            ft.DropdownOption(key="number", text="Numeric answer"),
            ft.DropdownOption(key="short_text", text="Short text"),
            ft.DropdownOption(key="consent", text="Required consent"),
        ],
    )
    options = ft.TextField(
        label="Choices, separated by semicolons", width=500,
        visible=False,
    )
    required = ft.Checkbox(label="Answer required", value=True)
    draft_view = ft.Column()
    survey_picker = ft.Dropdown(
        label="Saved local survey", width=600, options=[]
    )
    survey_info = ft.Text("")
    respondent_form = ft.Column()
    response_info = ft.Text("")
    status = ft.Text(
        "Draft a form or load the pilot template. "
        "No service accounts or network are involved.",
    )
    file_picker = ft.FilePicker()
    page.services.append(file_picker)

    def update_kind(e=None):
        options.visible = kind.value == "single_choice"
        if kind.value == "consent":
            required.value = True
        page.update()

    kind.on_select = update_kind

    def update_draft():
        draft_view.controls = [
            ft.Text(
                f"{i}. {q['key']} | {q['kind']} | "
                f"{q['prompt'][:100]}" + (" (required)" if q["required"] else ""),
                size=12,
            )
            for i, q in enumerate(draft, 1)
        ]
        page.update()

    def add_question(e):
        try:
            choice_items = [
                item.strip() for item in (options.value or "").split(";")
                if item.strip()
            ] if kind.value == "single_choice" else []
            candidate = {
                "key": (question_key.value or "").strip(),
                "prompt": (question_prompt.value or "").strip(),
                "kind": kind.value,
                "required": bool(required.value) or kind.value == "consent",
                "options": choice_items,
            }
            validate_questions(draft + [candidate])
            draft.append(candidate)
            question_key.value = ""
            question_prompt.value = ""
            options.value = ""
            status.value = f"Added {candidate['key']} to draft."
            update_draft()
        except Exception as err:
            status.value = f"Question error: {err}"
            page.update()

    def undo_last(e):
        if draft:
            removed = draft.pop()
            status.value = f"Removed draft question {removed['key']}."
        update_draft()

    def load_pilot(e):
        draft.clear()
        draft.extend([
            {
                "key": "consent", "prompt": (
                    "I have read the study information and agree to participate "
                    "in this fictional pilot."
                ), "kind": "consent", "required": True, "options": [],
            },
            {
                "key": "group", "prompt": "Select the fictional study group",
                "kind": "single_choice", "required": True,
                "options": ["A", "B"],
            },
            *[
                {
                    "key": f"stress_q{i}",
                    "prompt": f"Stress-related statement {i} (1 = low, 5 = high)",
                    "kind": "likert5", "required": True, "options": [],
                }
                for i in range(1, 5)
            ],
        ])
        status.value = (
            "Loaded a six-question fictional survey template. "
            "Replace study information before collecting real data."
        )
        update_draft()

    def refresh_surveys(selected=None):
        definitions = list_surveys(root)
        survey_picker.options = [
            ft.DropdownOption(
                key=s.survey_id,
                text=f"{s.title} ({s.survey_id[:8]})",
            )
            for s in definitions
        ]
        if selected and any(s.survey_id == selected for s in definitions):
            survey_picker.value = selected
        elif definitions:
            survey_picker.value = definitions[-1].survey_id
        else:
            survey_picker.value = None
        show_survey()
        page.update()

    def create_form(e):
        try:
            definition = create_survey(
                root, title.value or "", description.value or "",
                draft,
            )
            current["id"] = definition.survey_id
            draft.clear()
            update_draft()
            refresh_surveys(definition.survey_id)
            status.value = (
                f"Created local survey '{definition.title}'. "
                "Its question schema is now fixed to protect existing response data."
            )
            page.update()
        except Exception as err:
            status.value = f"Survey creation error: {err}"
            page.update()

    def selected_survey(e=None):
        current["id"] = survey_picker.value
        show_survey()
        page.update()

    survey_picker.on_select = selected_survey

    def show_survey():
        survey_id = survey_picker.value
        current["id"] = survey_id
        current["widgets"] = {}
        respondent_form.controls.clear()
        if not survey_id:
            survey_info.value = "No saved surveys yet."
            response_info.value = ""
            return
        try:
            definition = get_survey(root, survey_id)
            survey_info.value = (
                f"{definition.title}\n{definition.description}\n"
                f"Saved locally: {response_count(root, survey_id)} responses. "
                "Forms cannot be edited after creation; create a new survey version."
            )
            for q in definition.questions:
                kind_name = q["kind"]
                label = q["prompt"] + (" *" if q["required"] else "")
                if kind_name == "likert5":
                    widget = ft.Dropdown(
                        label=label, width=680,
                        options=[
                            ft.DropdownOption(key=str(n), text=str(n))
                            for n in range(1, 6)
                        ],
                    )
                elif kind_name == "single_choice":
                    widget = ft.Dropdown(
                        label=label, width=680,
                        options=[
                            ft.DropdownOption(key=opt, text=opt)
                            for opt in q["options"]
                        ],
                    )
                elif kind_name == "consent":
                    widget = ft.Checkbox(label=label, value=False)
                else:
                    widget = ft.TextField(label=label, width=680)
                current["widgets"][q["key"]] = widget
                respondent_form.controls.append(widget)
            response_info.value = ""
        except Exception as err:
            survey_info.value = f"Unable to load selected survey: {err}"

    def save_answer(e):
        survey_id = current["id"]
        if not survey_id:
            response_info.value = "Choose a saved survey first."
            page.update()
            return
        try:
            definition = get_survey(root, survey_id)
            answer = {
                q["key"]: (
                    bool(current["widgets"][q["key"]].value)
                    if q["kind"] == "consent"
                    else current["widgets"][q["key"]].value
                )
                for q in definition.questions
            }
            submit_response(root, survey_id, answer)
            show_survey()  # Clear input widgets after successful submission.
            response_info.value = (
                "Response saved locally. "
                f"Total: {response_count(root, survey_id)}."
            )
        except Exception as err:
            response_info.value = f"Response not saved: {err}"
        page.update()

    async def load_answers_into_analysis(e):
        if not current["id"]:
            response_info.value = "Select a survey first."
            page.update()
            return
        try:
            frame = await asyncio.to_thread(
                responses_dataframe, root, current["id"]
            )
            if frame.empty:
                raise ValueError("No responses collected yet.")
            await load_dataframe(frame)
            response_info.value = (
                f"Loaded {len(frame)} anonymous response rows into Dataset. "
                "All analysis tools now use this local table."
            )
        except Exception as err:
            response_info.value = f"Loading error: {err}"
        page.update()

    async def export_answers(e):
        if not current["id"]:
            response_info.value = "Select a survey first."
            page.update()
            return
        try:
            path = await file_picker.save_file(
                dialog_title="Export local survey answers",
                file_name="survey_responses.csv",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv"],
            )
            if path:
                saved = await asyncio.to_thread(
                    save_survey_csv, root, current["id"], path
                )
                response_info.value = f"Saved local CSV: {saved}"
        except Exception as err:
            response_info.value = f"Export error: {err}"
        page.update()

    view = ft.Column(
        controls=[
            ft.Text(
                "LOCAL PILOT: participants fill out this form on this computer. "
                "No public link, internet hosting or remote submissions are provided.",
                weight="bold", color="#9CB7DA",
            ),
            ft.Text(
                "For real research, write proper participant information, "
                "consent/privacy terms and a retention policy. Do not collect "
                "unnecessary identifying or sensitive personal details.",
                color="#A8B6C9",
            ),
            ft.ExpansionTile(
                title="1. Create a new questionnaire",
                expanded=True,
                controls=[
                    title, description,
                    ft.Row([question_key, kind], wrap=True, spacing=10),
                    question_prompt,
                    options,
                    required,
                    ft.Row([
                        ft.Button("Add question", on_click=add_question),
                        ft.Button("Remove last", on_click=undo_last),
                        ft.Button("Pilot template", on_click=load_pilot),
                    ], wrap=True, spacing=10),
                    draft_view,
                    ft.Button(
                        "Create local questionnaire", on_click=create_form
                    ),
                ],
            ),
            ft.Text("2. Enter and save participant responses", weight="bold"),
            survey_picker,
            survey_info,
            respondent_form,
            ft.Button("Submit response locally", on_click=save_answer),
            response_info,
            ft.Text("3. Transfer to statistical analysis", weight="bold"),
            ft.Row([
                ft.Button(
                    "Load responses into Dataset",
                    on_click=load_answers_into_analysis,
                ),
                ft.Button("Export responses CSV", on_click=export_answers),
                ft.Button(
                    "Refresh saved surveys",
                    on_click=lambda e: refresh_surveys(survey_picker.value),
                ),
            ], wrap=True, spacing=10),
            status,
        ],
        spacing=14,
    )
    # Initialized after the page and all controls exist.
    refresh_surveys()
    return view
