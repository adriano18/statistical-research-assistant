"""Step 2: local desktop viewer for CSV and Excel research datasets."""

import asyncio
from pathlib import Path

import flet as ft
import pandas as pd

from data_loader import load_dataset, variable_overview
from variable_rules import looks_like_identifier
from descriptive_charts import make_descriptive_chart
from reliability import analyze_cronbach
from reliability_reporting import apa_reliability_report, ALPHA_GUIDE
from reliability_charts import make_reliability_chart
from correlation import analyze_correlation, recommend_method
from correlation_reporting import format_correlation_report
from correlation_charts import make_correlation_chart
from correlation_matrix import analyze_correlation_matrix
from correlation_matrix_charts import make_correlation_matrix_chart


SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_survey.csv"
SCALE_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_scale.csv"


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
    guidance = ft.Text("")
    chart_area = ft.Column()
    reliability_items = ft.Column(height=180, scroll=ft.ScrollMode.AUTO)
    reliability_confirm = ft.Checkbox(
        label="I checked that the items measure one construct and reversed items are recoded",
        value=False,
    )
    reliability_output = ft.Text("")
    reliability_warnings = ft.Text("")
    reliability_guide = ft.Text("")
    reliability_chart_area = ft.Column()

    # Correlation requires two real measurements, not just two numeric columns.
    corr_x = ft.Dropdown(label="Variable X", width=270, options=[])
    corr_y = ft.Dropdown(label="Variable Y", width=270, options=[])
    corr_scale_x = ft.Dropdown(
        label="X measurement scale", width=250, value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="nominal", text="Nominal (not supported)"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
        ],
    )
    corr_scale_y = ft.Dropdown(
        label="Y measurement scale", width=250, value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="nominal", text="Nominal (not supported)"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
        ],
    )
    corr_method = ft.Dropdown(
        label="Correlation method", width=250, value="spearman",
        options=[
            ft.DropdownOption(key="spearman", text="Spearman’s ρ"),
            ft.DropdownOption(key="pearson", text="Pearson’s r"),
        ],
    )
    corr_confirm = ft.Checkbox(
        label=(
            "For Pearson only: I reviewed linearity, outliers, "
            "independence and suitability of the variables"
        ),
        value=False,
    )
    corr_advice = ft.Text("")
    corr_output = ft.Text("")
    corr_warnings = ft.Text("")
    corr_chart = ft.Column()

    # Exploratory correlation matrix (2–8 user-confirmed measurements).
    matrix_items = ft.Column(height=170, scroll=ft.ScrollMode.AUTO)
    matrix_method = ft.Dropdown(
        label="Matrix method", width=250, value="spearman",
        options=[
            ft.DropdownOption(key="spearman", text="Spearman’s ρ"),
            ft.DropdownOption(key="pearson", text="Pearson’s r"),
        ],
    )
    matrix_confirm = ft.Checkbox(
        label=(
            "I confirmed the measurement scales and study assumptions "
            "(Pearson: quantitative and linear; Spearman: ordinal or quantitative)"
        ),
        value=False,
    )
    matrix_output = ft.Text("")
    matrix_warnings = ft.Text("")
    matrix_chart = ft.Column()

    def update_corr_advice(e=None):
        corr_advice.value = recommend_method(
            corr_scale_x.value, corr_scale_y.value
        )
        corr_confirm.value = False
        corr_output.value = ""
        corr_warnings.value = ""
        corr_chart.controls.clear()
        page.update()

    def reset_corr_selection(e):
        if e.control == corr_x:
            corr_scale_x.value = "unknown"
        else:
            corr_scale_y.value = "unknown"
        update_corr_advice()

    corr_x.on_select = reset_corr_selection
    corr_y.on_select = reset_corr_selection
    corr_scale_x.on_select = update_corr_advice
    corr_scale_y.on_select = update_corr_advice
    corr_method.on_select = update_corr_advice
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
        guidance.value = ""
        chart_area.controls.clear()
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
        guidance.value = ""
        chart_area.controls.clear()

        # Numeric columns are only candidates, not automatically valid scales.
        reliability_items.controls = [
            ft.Checkbox(label=str(name), value=False)
            for name in df.columns
            if pd.api.types.is_numeric_dtype(df[name])
            and not looks_like_identifier(name)
        ]
        reliability_confirm.value = False
        reliability_output.value = ""
        reliability_warnings.value = ""
        reliability_guide.value = ""
        reliability_chart_area.controls.clear()

        # Offer numeric variables but leave their measurement scales unconfirmed.
        numeric_candidates = [
            str(name) for name in df.columns
            if pd.api.types.is_numeric_dtype(df[name])
            and not looks_like_identifier(name)
        ]
        corr_x.options = [
            ft.DropdownOption(key=name, text=name) for name in numeric_candidates
        ]
        corr_y.options = [
            ft.DropdownOption(key=name, text=name) for name in numeric_candidates
        ]
        corr_x.value = numeric_candidates[0] if numeric_candidates else None
        corr_y.value = numeric_candidates[1] if len(numeric_candidates) > 1 else None
        corr_scale_x.value = "unknown"
        corr_scale_y.value = "unknown"
        corr_method.value = "spearman"
        corr_confirm.value = False
        corr_output.value = ""
        corr_warnings.value = ""
        corr_chart.controls.clear()
        corr_advice.value = recommend_method("unknown", "unknown")

        matrix_items.controls = [
            ft.Checkbox(label=name, value=False)
            for name in numeric_candidates
        ]
        matrix_method.value = "spearman"
        matrix_confirm.value = False
        matrix_output.value = ""
        matrix_warnings.value = ""
        matrix_chart.controls.clear()
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

    async def load_scale_example(e):
        await show_file(SCALE_SAMPLE)

    async def calculate_alpha(e):
        reliability_chart_area.controls.clear()
        reliability_guide.value = ""
        reliability_warnings.value = ""

        if dataframe is None:
            reliability_output.value = "Load a dataset first."
            page.update()
            return

        selected = [
            box.label for box in reliability_items.controls if box.value
        ]
        if not reliability_confirm.value:
            reliability_output.value = (
                "Confirm common construct and consistent scoring direction first."
            )
            page.update()
            return

        reliability_output.value = "Calculating Cronbach’s α..."
        page.update()

        try:
            analysis = await asyncio.to_thread(
                analyze_cronbach, dataframe, selected
            )
            reliability_output.value = apa_reliability_report(analysis)
            reliability_guide.value = ALPHA_GUIDE
            reliability_warnings.value = "\n".join(analysis.warnings)

            png = await asyncio.to_thread(make_reliability_chart, analysis)
            chart_height = min(
                850, max(430, 280 + 58 * (len(analysis.alpha_if_deleted) + 1))
            )
            reliability_chart_area.controls.append(
                ft.Image(src=png, width=850, height=chart_height)
            )
        except Exception as error:
            reliability_output.value = f"Reliability analysis error: {error}"
        page.update()

    async def calculate_correlation(e):
        corr_chart.controls.clear()
        corr_warnings.value = ""

        if dataframe is None:
            corr_output.value = "Load a dataset first."
            page.update()
            return
        if not corr_x.value or not corr_y.value:
            corr_output.value = "Choose two numeric research variables."
            page.update()
            return

        corr_output.value = "Calculating correlation and preparing figure..."
        page.update()
        try:
            analysis = await asyncio.to_thread(
                analyze_correlation,
                dataframe,
                corr_x.value,
                corr_y.value,
                corr_method.value,
                corr_scale_x.value,
                corr_scale_y.value,
                bool(corr_confirm.value),
            )
            corr_output.value = format_correlation_report(analysis)
            corr_warnings.value = "\n".join(analysis.warnings)
            figure = await asyncio.to_thread(make_correlation_chart, analysis)
            corr_chart.controls.append(
                ft.Image(src=figure, width=820, height=520)
            )
        except Exception as error:
            corr_output.value = f"Correlation analysis error: {error}"
        page.update()

    async def calculate_matrix(e):
        matrix_chart.controls.clear()
        matrix_warnings.value = ""

        if dataframe is None:
            matrix_output.value = "Load a dataset first."
            page.update()
            return

        selected = [
            check.label for check in matrix_items.controls if check.value
        ]
        matrix_output.value = "Calculating exploratory correlation matrix..."
        page.update()

        try:
            analysis = await asyncio.to_thread(
                analyze_correlation_matrix,
                dataframe,
                selected,
                matrix_method.value,
                bool(matrix_confirm.value),
            )
            label = "Pearson’s r" if analysis.method == "pearson" else "Spearman’s ρ"
            matrix_output.value = (
                f"Exploratory {label} matrix with {len(analysis.names)} variables.\n"
                "Each cell shows a coefficient and its pairwise-complete N.\n"
                "No significance tests or p-values are calculated for this matrix."
            )
            matrix_warnings.value = "\n".join(analysis.warnings)
            png = await asyncio.to_thread(make_correlation_matrix_chart, analysis)
            matrix_chart.controls.append(
                ft.Image(src=png, width=850, height=760)
            )
        except Exception as error:
            matrix_output.value = f"Correlation matrix error: {error}"
        page.update()

    # Visualization follows the same scale and identifier safeguards as the table.
    async def analyze_variable(e):
        chart_area.controls.clear()
        guidance.value = ""

        if dataframe is None or not variable.value:
            results.value = "Load data first."
            page.update()
            return

        if looks_like_identifier(variable.value) or scale.value == "id":
            results.value = "An identifier is not a research measurement."
            page.update()
            return

        if scale.value not in ("scale", "nominal", "ordinal"):
            results.value = "Confirm the measurement scale before analysis."
            page.update()
            return

        values = dataframe[variable.value]
        missing = int(values.isna().sum())
        results.value = "Preparing descriptive statistics and chart..."
        page.update()

        try:
            png = await asyncio.to_thread(
                make_descriptive_chart, values, scale.value
            )

            if scale.value == "scale":
                numeric = pd.to_numeric(values, errors="coerce").dropna()
                std = f"{numeric.std():.2f}" if len(numeric) > 1 else "N/A"
                results.value = (
                    f"{variable.value} | N = {len(numeric)} | Missing = {missing}\n"
                    f"Mean = {numeric.mean():.2f} | Median = {numeric.median():.2f}\n"
                    f"SD = {std} | Min = {numeric.min():.2f} | "
                    f"Max = {numeric.max():.2f}"
                )
                guidance.value = (
                    "Interpretation: these numbers describe the loaded sample only. "
                    "The histogram shows the observed distribution; it does not "
                    "prove normality or population-level conclusions."
                )
            else:
                counts = (
                    values.astype("string")
                    .fillna("(missing)")
                    .value_counts()
                    .head(15)
                )
                lines = [
                    f"{variable.value} | {scale.value} | Missing = {missing}"
                ]
                lines += [f"{label}: {count}" for label, count in counts.items()]
                if values.nunique(dropna=False) > 15:
                    lines.append("Showing only 15 most common categories.")
                results.value = "\n".join(lines)
                guidance.value = (
                    "Interpretation: the bars show response frequencies, not "
                    "evidence of differences between groups. For ordinal data, "
                    "response order matters; for nominal data, categories have no "
                    "natural numeric distance."
                )

            chart_area.controls.append(
                ft.Image(src=png, width=720, height=420)
            )
        except (ValueError, TypeError) as error:
            results.value = f"Cannot analyze this variable: {error}"

        page.update()

    page.add(
        ft.Text("Statistical Research Assistant", size=28, weight="bold"),
        ft.Text("Step 6 | Reliability, correlations and exploratory matrices"),
        ft.Row(
            controls=[
                ft.Button("Open CSV / Excel", on_click=choose_file),
                ft.Button("Load example", on_click=load_sample),
                ft.Button("Load scale example", on_click=load_scale_example),
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
        guidance,
        chart_area,
        ft.Text("SCALE RELIABILITY", size=18, weight="bold"),
        ft.Text(
            "Select at least three numeric items from ONE questionnaire scale. "
            "Do not select demographics, IDs, or unrelated variables."
        ),
        reliability_items,
        reliability_confirm,
        ft.Button("Calculate Cronbach's alpha", on_click=calculate_alpha),
        reliability_output,
        reliability_guide,
        reliability_warnings,
        reliability_chart_area,
        ft.Text("CORRELATION ANALYSIS", size=18, weight="bold"),
        ft.Text(
            "Select two measurements. Confirm their scales; review the "
            "study design and scatterplot before interpreting significance."
        ),
        ft.Row(controls=[corr_x, corr_y], wrap=True),
        ft.Row(controls=[corr_scale_x, corr_scale_y], wrap=True),
        corr_advice,
        corr_method,
        corr_confirm,
        ft.Button("Calculate correlation", on_click=calculate_correlation),
        corr_output,
        corr_warnings,
        corr_chart,
        ft.Text("CORRELATION MATRIX", size=18, weight="bold"),
        ft.Text(
            "Explore relationships among 2–8 numeric-coded variables. "
            "Select only genuine ordinal or quantitative measurements."
        ),
        matrix_items,
        matrix_method,
        matrix_confirm,
        ft.Button("Calculate correlation matrix", on_click=calculate_matrix),
        matrix_output,
        matrix_warnings,
        matrix_chart,
    )
    page.update()


if __name__ == "__main__":
    ft.run(main)
