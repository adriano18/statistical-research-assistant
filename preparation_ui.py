"""Flet controls for safe data preparation without overwriting source columns."""

import asyncio

import flet as ft
import pandas as pd

from data_preparation import (
    mark_missing, recode_column, reverse_item, score_scale,
    save_prepared_dataset,
)


def build_preparation_workspace(page, load_dataframe, *, with_steps=False):
    """Return (view, reset_for_new_dataset). Loading into analysis is explicit.

    ``with_steps``: ``load_dataframe(frame, steps)`` also receives the steps
    applied since the last reset, so the caller can keep them as history."""
    state = {"working": None, "steps": [], "source_path": None}

    method = ft.Dropdown(
        label="Transformation", width=350, value="missing",
        options=[
            ft.DropdownOption(key="missing", text="Mark missing-value codes"),
            ft.DropdownOption(key="recode", text="Recode values"),
            ft.DropdownOption(key="reverse", text="Reverse-score an item"),
            ft.DropdownOption(key="scale", text="Create mean/sum scale score"),
        ],
    )
    source = ft.Dropdown(label="Source variable", width=310, options=[])
    target = ft.TextField(label="New variable name", width=310)
    missing_codes = ft.TextField(
        label="Missing codes, comma-separated", value="99", width=440
    )
    recode_pairs = ft.TextField(
        label="Recode pairs, e.g. No=0;Yes=1", width=440
    )
    recode_unmatched = ft.Dropdown(
        label="Other values", width=280, value="keep",
        options=[
            ft.DropdownOption(key="keep", text="Retain unchanged"),
            ft.DropdownOption(key="missing", text="Mark missing"),
        ],
    )
    reverse_min = ft.TextField(label="Minimum", value="1", width=150)
    reverse_max = ft.TextField(label="Maximum", value="5", width=150)
    items = ft.Column(height=170, scroll=ft.ScrollMode.AUTO)
    score_method = ft.Dropdown(
        label="Scale score", width=220, value="mean",
        options=[
            ft.DropdownOption(key="mean", text="Mean of answered items"),
            ft.DropdownOption(key="sum", text="Sum (complete cases only)"),
        ],
    )
    min_answered = ft.TextField(
        label="Minimum answered items", value="3", width=230
    )
    mode_missing = ft.Column([missing_codes])
    mode_recode = ft.Column([recode_pairs, recode_unmatched])
    mode_reverse = ft.Row([reverse_min, reverse_max], wrap=True)
    mode_scale = ft.Column([
        ft.Text("Items of ONE construct, already coded in the same direction"),
        items,
        ft.Row([score_method, min_answered], wrap=True),
    ])
    status = ft.Text("Load a dataset first.")
    history = ft.Text("")
    picker = ft.FilePicker()
    page.services.append(picker)

    def set_mode(e=None):
        mode_missing.visible = method.value == "missing"
        mode_recode.visible = method.value == "recode"
        mode_reverse.visible = method.value == "reverse"
        mode_scale.visible = method.value == "scale"
        source.visible = method.value != "scale"
        if state["working"] is not None:
            hint = {
                "missing": "_clean", "recode": "_recoded",
                "reverse": "_reverse", "scale": "_mean",
            }[method.value]
            if method.value != "scale" and source.value:
                target.value = source.value + hint
            elif method.value == "scale":
                target.value = "scale_mean"
        page.update()

    method.on_select = set_mode

    def reset_for_dataset(df: pd.DataFrame, source_path=None):
        state["working"] = df.copy(deep=True)
        state["steps"] = []
        state["source_path"] = source_path
        status.value = f"Working copy: {len(df)} rows, {len(df.columns)} columns."
        history.value = "No transformations yet."
        update_columns()
        set_mode()

    def update_columns():
        frame = state["working"]
        if frame is None:
            return
        columns = [str(c) for c in frame.columns]
        source.options = [
            ft.DropdownOption(key=c, text=c) for c in columns
        ]
        source.value = next(
            (x for x in columns if x.startswith("stress_q")), columns[0]
        ) if columns else None
        items.controls = [
            ft.Checkbox(label=c, value=False) for c in columns
            if pd.api.types.is_numeric_dtype(frame[c])
        ]
        min_answered.value = "3"
        set_mode()

    def recode_rules(value):
        rules = {}
        for part in value.split(";"):
            if not part.strip():
                continue
            if "=" not in part:
                raise ValueError("Use old=new pairs separated by semicolons.")
            old, new = (v.strip() for v in part.split("=", 1))
            if not old or not new or old in rules:
                raise ValueError("Each old value needs one nonempty distinct new value.")
            rules[old] = new
        return rules

    def apply_step(e):
        if state["working"] is None:
            status.value = "Load a dataset first."
            page.update()
            return
        frame = state["working"]
        output = (target.value or "").strip()
        try:
            if method.value == "missing":
                codes = [x.strip() for x in missing_codes.value.split(",")]
                result = mark_missing(frame, source.value, output, codes)
            elif method.value == "recode":
                result = recode_column(
                    frame, source.value, output,
                    recode_rules(recode_pairs.value), recode_unmatched.value
                )
            elif method.value == "reverse":
                result = reverse_item(
                    frame, source.value, output,
                    float(reverse_min.value), float(reverse_max.value),
                )
            elif method.value == "scale":
                selected = [
                    box.label for box in items.controls if bool(box.value)
                ]
                result = score_scale(
                    frame, selected, output, score_method.value,
                    int(min_answered.value),
                )
            else:
                raise ValueError("Unknown transformation.")
            state["working"] = result.frame
            state["steps"].append(result.step)
            history.value = "\n".join(
                f"{i}. {step['type']} → {step['target']}"
                for i, step in enumerate(state["steps"], 1)
            )
            status.value = result.message
            update_columns()
        except (ValueError, TypeError, KeyError) as err:
            status.value = f"Transformation error: {err}"
        page.update()

    async def load_for_analysis(e):
        if state["working"] is None:
            status.value = "Load a dataset first."
        else:
            frame = state["working"].copy(deep=True)
            if with_steps:
                await load_dataframe(frame, [dict(step) for step in state["steps"]])
            else:
                await load_dataframe(frame)
            status.value = (
                f"Prepared table sent to Dataset: "
                f"{len(state['working'])} rows."
            )
        page.update()

    async def save_prepared(e):
        if state["working"] is None:
            status.value = "Load a dataset first."
            page.update()
            return
        try:
            path = await picker.save_file(
                dialog_title="Save a new prepared CSV and transformation log",
                file_name="prepared_study.csv",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv"],
            )
            if path:
                csv, recipe = await asyncio.to_thread(
                    save_prepared_dataset,
                    state["working"], state["steps"], path,
                    state["source_path"],
                )
                status.value = f"Saved: {csv}\nRecipe: {recipe}"
        except Exception as err:
            status.value = f"Save error: {err}"
        page.update()

    view = ft.Column(
        controls=[
            ft.Text(
                "Work on a COPY. Every action creates a NEW column. "
                "Original variables and the original CSV/XLSX are left intact.",
                color="#A8B6C9",
            ),
            method,
            ft.Row([source, target], wrap=True, spacing=12),
            mode_missing, mode_recode, mode_reverse, mode_scale,
            ft.Row([
                ft.Button("Apply transformation", on_click=apply_step),
                ft.Button(
                    "Use working copy in analysis", on_click=load_for_analysis
                ),
                ft.Button("Save prepared CSV + steps JSON", on_click=save_prepared),
            ], wrap=True, spacing=10),
            status,
            ft.Text("Transformation history", weight="bold"),
            history,
        ],
        spacing=12,
    )
    # Avoid re-rendering partially configured forms on initial creation.
    mode_recode.visible = False
    mode_reverse.visible = False
    mode_scale.visible = False
    return view, reset_for_dataset
