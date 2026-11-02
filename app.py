"""Step 2: local desktop viewer for CSV and Excel research datasets."""

import asyncio
from pathlib import Path

import flet as ft
import pandas as pd

from data_loader import load_dataset, variable_overview
from variable_rules import looks_like_identifier


SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_survey.csv"


async def main(page: ft.Page):
    page.title = "Statistical Research Assistant"
    page.window.width = 1000
    page.window.height = 700
    page.padding = 24
    page.scroll = ft.ScrollMode.AUTO

    # The source file stays on the user's computer; no cloud upload.
    picker = ft.FilePicker()
    page.services.append(picker)
    dataframe = None

    status = ft.Text("Open your CSV/Excel file or try the sample dataset.")
    overview_area = ft.Column()
    results = ft.Text("")
    variable = ft.Dropdown(label="Variable", width=270, options=[])
    scale = ft.Dropdown(
        label="Measurement scale (confirm manually)",
        width=300,
        value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="id", text="Identifier"),
            ft.DropdownOption(key="nominal", text="Nominal"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
        ],
    )

    def reset_scale(e):
        scale.value = "id" if looks_like_identifier(variable.value) else "unknown"
        results.value = ""
        page.update()

    variable.on_select = reset_scale

    # The same data loader is shared by this GUI and inspect_data.py.
    async def show_file(path):
        nonlocal dataframe
        try:
            df = await asyncio.to_thread(load_dataset, path)
            if df.columns.empty:
                raise ValueError("No variables found in this file.")
            overview = variable_overview(df)
        except Exception as error:
            status.value = f"Could not load file: {error}"
            page.update()
            return

        dataframe = df
        status.value = (
            f"Loaded: {Path(path).name} | "
            f"Respondents/rows: {len(df)} | Variables: {len(df.columns)}"
        )

        overview_area.controls.clear()
        overview_area.controls.append(
            ft.DataTable(
                columns=[
                    ft.DataColumn(label=ft.Text("Variable")),
                    ft.DataColumn(label=ft.Text("Data type")),
                    ft.DataColumn(label=ft.Text("Missing")),
                    ft.DataColumn(label=ft.Text("Unique")),
                    ft.DataColumn(label=ft.Text("Type hint")),
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(str(row["variable"]))),
                        ft.DataCell(ft.Text(str(row["dtype"]))),
                        ft.DataCell(ft.Text(str(row["missing"]))),
                        ft.DataCell(ft.Text(str(row["unique_values"]))),
                        ft.DataCell(ft.Text(str(row["type_hint"]))),
                    ])
                    for _, row in overview.iterrows()
                ],
            )
        )

        variable.options = [
            ft.DropdownOption(key=str(name), text=str(name))
            for name in df.columns
        ]
        # Start with the first non-identifier variable to avoid meaningless means.
        variable.value = next(
            (str(name) for name in df.columns if not looks_like_identifier(name)),
            str(df.columns[0]),
        )
        scale.value = "id" if looks_like_identifier(variable.value) else "unknown"
        results.value = ""
        page.update()

    async def choose_file(e):
        try:
            files = await picker.pick_files(
                allow_multiple=False,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["csv", "xlsx", "xlsm"],
            )
            if files:
                if files[0].path:
                    await show_file(files[0].path)
                else:
                    status.value = "A local file path is required. Run as a desktop app."
                    page.update()
        except Exception as error:
            status.value = f"File selection error: {error}"
            page.update()

    async def load_sample(e):
        await show_file(SAMPLE)

    def analyze_variable(e):
        if dataframe is None or not variable.value:
            results.value = "Load data first."
        elif looks_like_identifier(variable.value):
            results.value = (
                "This column looks like an identifier, not a research score. "
                "Choose an actual measurement variable instead."
            )
        elif scale.value == "unknown":
            results.value = "Confirm the measurement scale before analysis."
        elif scale.value == "id":
            results.value = "An identifier should not be analyzed as a score."
        else:
            values = dataframe[variable.value]
            missing = int(values.isna().sum())
            if scale.value == "scale":
                numeric = pd.to_numeric(values, errors="coerce").dropna()
                if len(numeric) != int(values.notna().sum()):
                    results.value = (
                        "Some values are not numeric. Check the variable first."
                    )
                elif numeric.empty:
                    results.value = "No valid numerical observations."
                else:
                    std = f"{numeric.std():.2f}" if len(numeric) > 1 else "N/A"
                    results.value = (
                        f"{variable.value} | N = {len(numeric)} | Missing = {missing}\n"
                        f"Mean = {numeric.mean():.2f} | Median = {numeric.median():.2f}\n"
                        f"SD = {std} | Min = {numeric.min():.2f} | "
                        f"Max = {numeric.max():.2f}"
                    )
            else:
                counts = values.astype("string").fillna("(missing)").value_counts().head(15)
                lines = [f"{variable.value} | {scale.value} | Missing = {missing}"]
                lines += [f"{label}: {count}" for label, count in counts.items()]
                if values.nunique(dropna=False) > 15:
                    lines.append("Showing only 15 most common categories.")
                results.value = "\n".join(lines)
        page.update()

    page.add(
        ft.Text("Statistical Research Assistant", size=28, weight="bold"),
        ft.Text("Step 2 | Local data inspection and basic descriptions"),
        ft.Row(
            controls=[
                ft.Button("Open CSV / Excel", on_click=choose_file),
                ft.Button("Load example", on_click=load_sample),
            ],
            wrap=True,
        ),
        status,
        ft.Text("VARIABLE OVERVIEW", size=18, weight="bold"),
        ft.Text("Numeric data type does not automatically mean quantitative scale."),
        overview_area,
        ft.Text("DESCRIPTIVE ANALYSIS", size=18, weight="bold"),
        ft.Row(controls=[variable, scale], wrap=True),
        ft.Button("Analyze selected variable", on_click=analyze_variable),
        results,
    )
    page.update()


if __name__ == "__main__":
    ft.run(main)
