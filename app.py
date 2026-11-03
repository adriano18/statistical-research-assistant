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
from omega_analysis import analyze_omega
from omega_reporting import format_omega_report, omega_summary
from omega_charts import make_omega_chart
from correlation import analyze_correlation, recommend_method
from correlation_reporting import format_correlation_report
from correlation_charts import make_correlation_chart
from correlation_matrix import analyze_correlation_matrix
from correlation_matrix_charts import make_correlation_matrix_chart
from interface_layout import build_interface
from group_comparison import compare_independent_groups, recommend_group_test
from group_comparison_reporting import format_group_comparison
from group_comparison_charts import make_group_comparison_chart
from paired_analysis import analyze_paired, recommend_paired_test
from paired_reporting import format_paired_report
from paired_charts import make_paired_chart
from paired_presentation import paired_main_result, paired_descriptives, paired_interpretation
from report_export import save_apa_txt, save_figure_png
from chi_square import analyze_chi_square
from chi_square_reporting import (
    format_chi_square_report, summarize_chi_square, interpret_chi_square
)
from chi_square_charts import make_chi_square_chart
from omnibus_analysis import analyze_omnibus, recommend_omnibus_test
from omnibus_reporting import (
    format_omnibus_report, format_omnibus_summary, interpret_omnibus
)
from omnibus_charts import make_omnibus_chart
from posthoc_analysis import analyze_posthoc
from posthoc_reporting import format_posthoc_report
from output_workspace import AnalysisOutput, save_selected_output
from explore_analysis import (
    explore_quantitative, format_explore_report, make_explore_chart
)
from regression_analysis import analyze_regression
from regression_reporting import format_regression_report, regression_brief
from correlation_reporting import apa_p_value
from regression_charts import make_regression_chart
from repeated_analysis import analyze_repeated
from repeated_reporting import repeated_main, repeated_brief, format_repeated_report
from repeated_charts import make_repeated_chart
from logistic_analysis import binary_logistic_regression
from logistic_reporting import logistic_main, logistic_brief, format_logistic_report
from logistic_charts import make_logistic_chart
from ancova_analysis import analyze_ancova
from ancova_reporting import ancova_main, ancova_brief, format_ancova_report
from ancova_charts import make_ancova_chart
from preparation_ui import build_preparation_workspace
from survey_ui import build_survey_workspace


SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_survey.csv"
SCALE_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_scale.csv"
PAIRED_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_paired.csv"
CATEGORICAL_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_categorical.csv"
THREE_GROUPS_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_three_groups.csv"
REGRESSION_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_regression.csv"
REPEATED_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_repeated.csv"
LOGISTIC_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_logistic.csv"
ANCOVA_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_ancova.csv"
ANCOVA_INTERACTION_SAMPLE = Path(__file__).resolve().parent / "examples" / "sample_ancova_interaction.csv"


async def main(page: ft.Page):
    page.title = "Statistical Research Assistant"
    page.window.width = 1350
    page.window.height = 850
    page.padding = 18
    page.bgcolor = "#0E1622"
    page.theme_mode = ft.ThemeMode.DARK
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH

    # The source file stays on the user's computer; no cloud upload.
    picker = ft.FilePicker()
    page.services.append(picker)
    export_picker = ft.FilePicker()
    page.services.append(export_picker)
    dataframe = None

    # Every section shares one consistent output toolbar. Results remain
    # local and only the last successful analysis per section is retained.
    output_cache = {}
    active_section = "dataset"
    output_status = ft.Text("", size=12)
    copy_button = ft.Button(
        "Copy report", disabled=True, action=ft.CopyToClipboard("")
    )
    save_text_button = ft.Button("Save TXT as...", disabled=True)
    save_picture_button = ft.Button("Save PNG as...", disabled=True)
    output_toolbar = ft.Row(
        controls=[
            ft.Text("OUTPUT", weight="bold", size=12),
            copy_button, save_text_button, save_picture_button, output_status,
        ],
        wrap=True,
        spacing=12,
    )

    def refresh_output_buttons():
        item = output_cache.get(active_section)
        enabled = item is not None and bool(item.report.strip())
        copy_button.disabled = not enabled
        save_text_button.disabled = not enabled
        save_picture_button.disabled = item is None or not bool(item.png)
        copy_button.action = ft.CopyToClipboard(item.report if enabled else "")
        output_status.value = (
            f"Last completed: {item.title}" if item is not None
            else "Run an analysis to enable copy and save."
        )

    def set_active_screen(section):
        nonlocal active_section
        active_section = section
        refresh_output_buttons()

    def remember_output(section, title, report, image=None):
        output_cache[section] = AnalysisOutput(
            title=title, report=report, png=image
        )
        if active_section == section:
            refresh_output_buttons()

    async def save_active(kind):
        item = output_cache.get(active_section)
        if item is None:
            output_status.value = "Run an analysis first."
            page.update()
            return
        suffix = "txt" if kind == "text" else "png"
        suggested = f"{active_section}_report.{suffix}" if kind == "text" else f"{active_section}_figure.{suffix}"
        try:
            selected = await export_picker.save_file(
                dialog_title="Save local statistical output",
                file_name=suggested,
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=[suffix],
            )
            if selected:
                destination = await asyncio.to_thread(
                    save_selected_output, selected, item, kind
                )
                output_status.value = f"Saved: {destination}"
        except Exception as error:
            output_status.value = f"Save error: {error}"
        page.update()

    async def save_active_text(e):
        await save_active("text")

    async def save_active_png(e):
        await save_active("image")

    def output_copied(e):
        output_status.value = "Report copied to clipboard."
        page.update()

    save_text_button.on_click = save_active_text
    save_picture_button.on_click = save_active_png
    copy_button.on_click = output_copied
    refresh_output_buttons()

    status = ft.Text("Open your CSV/Excel file or try the sample dataset.")
    overview_area = ft.Column()
    results = ft.Text("")
    guidance = ft.Text("")
    chart_area = ft.Column()
    explore_variable = ft.Dropdown(
        label="Quantitative variable", width=290, options=[]
    )
    explore_group = ft.Dropdown(
        label="Group (optional)", width=290,
        value="(none)",
        options=[ft.DropdownOption(key="(none)", text="No grouping")],
    )
    explore_output = ft.Text("")
    explore_chart = ft.Column()

    # Ordinary least squares: all selected variables are quantitative.
    reg_outcome = ft.Dropdown(
        label="Quantitative outcome (Y)", width=340, options=[]
    )
    reg_predictors = ft.Column(height=195, scroll=ft.ScrollMode.AUTO)
    reg_hc3 = ft.Checkbox(
        label="Use HC3 heteroskedasticity-robust coefficient standard errors",
        value=False,
    )
    reg_confirm = ft.Checkbox(
        label="I reviewed linearity, independence, outliers and predictor scales",
        value=False,
    )
    reg_main = ft.Text("")
    reg_brief = ft.Text("")
    reg_report = ft.Text("")
    reg_warnings = ft.Text("")
    reg_chart = ft.Column()

    # Binary logistic regression is intentionally restricted to 0/1 outcomes
    # and quantitative predictors. Categorical coding is a separate feature.
    log_outcome = ft.Dropdown(
        label="Binary outcome (0 / 1)", width=330, options=[]
    )
    log_predictors = ft.Column(height=170, scroll=ft.ScrollMode.AUTO)
    log_confirm = ft.Checkbox(
        label=(
            "I confirmed independent observations, outcome coding, "
            "quantitative predictors and logit-linearity assumptions"
        ),
        value=False,
    )
    log_main = ft.Text("")
    log_brief = ft.Text("")
    log_odds_table = ft.Column()
    log_report = ft.Text("")
    log_warnings = ft.Text("")
    log_chart = ft.Column()

    # General Linear Model: categorical groups + continuous covariates.
    ac_outcome = ft.Dropdown(
        label="Quantitative outcome", width=310, options=[]
    )
    ac_group = ft.Dropdown(
        label="Group factor (2–6 groups)", width=310, options=[]
    )
    ac_covariates = ft.Column(height=160, scroll=ft.ScrollMode.AUTO)
    ac_mode = ft.Dropdown(
        label="Model", width=340, value="ancova",
        options=[
            ft.DropdownOption(
                key="ancova", text="ANCOVA (common slopes)"
            ),
            ft.DropdownOption(
                key="interaction", text="GLM (group × covariate interactions)"
            ),
        ],
    )
    ac_confirm = ft.Checkbox(
        label=(
            "I reviewed independent observations, quantitative covariates, "
            "group design, covariate timing, linearity and outliers"
        ),
        value=False,
    )
    ac_main = ft.Text("")
    ac_brief = ft.Text("")
    ac_means_table = ft.Column()
    ac_pairs_table = ft.Column()
    ac_chart = ft.Column()
    ac_report = ft.Text("")
    ac_warnings = ft.Text("")

    def clear_ancova(e=None):
        ac_main.value = ""
        ac_brief.value = ""
        ac_means_table.controls.clear()
        ac_pairs_table.controls.clear()
        ac_chart.controls.clear()
        ac_report.value = ""
        ac_warnings.value = ""
        output_cache.pop("ancova", None)
        if active_section == "ancova":
            refresh_output_buttons()
        page.update()

    def refresh_ancova_covariates(e=None):
        if dataframe is None:
            return
        checked = {
            box.label for box in ac_covariates.controls if bool(box.value)
        }
        choices = [
            str(name) for name in dataframe.columns
            if pd.api.types.is_numeric_dtype(dataframe[name])
            and not looks_like_identifier(name)
            and name not in {ac_outcome.value, ac_group.value}
        ]
        ac_covariates.controls = [
            ft.Checkbox(
                label=name, value=name in checked,
                on_change=clear_ancova,
            )
            for name in choices
        ]
        ac_confirm.value = False
        clear_ancova()

    ac_outcome.on_select = refresh_ancova_covariates
    ac_group.on_select = refresh_ancova_covariates
    ac_mode.on_select = clear_ancova
    ac_confirm.on_change = clear_ancova

    def clear_logistic(e=None):
        log_main.value = ""
        log_brief.value = ""
        log_odds_table.controls.clear()
        log_report.value = ""
        log_warnings.value = ""
        log_chart.controls.clear()
        output_cache.pop("logistic", None)
        if active_section == "logistic":
            refresh_output_buttons()
        page.update()

    def refresh_logistic_predictors(e=None):
        if dataframe is None:
            return
        previous = {
            item.label for item in log_predictors.controls if bool(item.value)
        }
        options = [
            str(name) for name in dataframe.columns
            if pd.api.types.is_numeric_dtype(dataframe[name])
            and not looks_like_identifier(name)
            and str(name) != log_outcome.value
        ]
        log_predictors.controls = [
            ft.Checkbox(
                label=name, value=name in previous,
                on_change=clear_logistic,
            )
            for name in options
        ]
        log_confirm.value = False
        clear_logistic()

    log_outcome.on_select = refresh_logistic_predictors
    log_confirm.on_change = clear_logistic

    # Repeated measures: explicit columns with the same construct in occasion order.
    rep_items = ft.Column(height=185, scroll=ft.ScrollMode.AUTO)
    rep_scale = ft.Dropdown(
        label="Measurement scale", width=260, value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
        ],
    )
    rep_method = ft.Dropdown(
        label="Repeated-measures method", width=290, value="friedman",
        options=[
            ft.DropdownOption(key="friedman", text="Friedman test"),
            ft.DropdownOption(key="rm_anova", text="Repeated-measures ANOVA"),
        ],
    )
    rep_same_people = ft.Checkbox(
        label="Selected columns measure the same construct in the SAME participants",
        value=False,
    )
    rep_assumptions = ft.Checkbox(
        label="I reviewed measurement scales, difference scores, outliers and design assumptions",
        value=False,
    )
    rep_main = ft.Text("")
    rep_brief = ft.Text("")
    rep_report = ft.Text("")
    rep_warnings = ft.Text("")
    rep_chart = ft.Column()
    rep_pair_table = ft.Column()

    def clear_repeated(e=None):
        rep_main.value = ""
        rep_brief.value = ""
        rep_report.value = ""
        rep_warnings.value = ""
        rep_chart.controls.clear()
        rep_pair_table.controls.clear()
        output_cache.pop("repeated", None)
        if active_section == "repeated":
            refresh_output_buttons()
        page.update()

    rep_method.on_select = clear_repeated
    rep_scale.on_select = clear_repeated
    rep_same_people.on_change = clear_repeated
    rep_assumptions.on_change = clear_repeated

    def refresh_regression_choices(e=None):
        if dataframe is None:
            return
        previous = {
            box.label for box in reg_predictors.controls if bool(box.value)
        }
        choices = [
            str(name) for name in dataframe.columns
            if pd.api.types.is_numeric_dtype(dataframe[name])
            and not looks_like_identifier(name)
            and str(name) != reg_outcome.value
        ]
        reg_predictors.controls = [
            ft.Checkbox(label=name, value=name in previous)
            for name in choices
        ]
        reg_main.value = ""
        reg_brief.value = ""
        reg_report.value = ""
        reg_warnings.value = ""
        reg_chart.controls.clear()
        output_cache.pop("regression", None)
        if active_section == "regression":
            refresh_output_buttons()
        page.update()

    reg_outcome.on_select = refresh_regression_choices
    reliability_items = ft.Column(height=180, scroll=ft.ScrollMode.AUTO)
    reliability_confirm = ft.Checkbox(
        label="I checked that the items measure one construct and reversed items are recoded",
        value=False,
    )
    reliability_output = ft.Text("")
    reliability_warnings = ft.Text("")
    reliability_guide = ft.Text("")
    reliability_chart_area = ft.Column()

    # One-factor standardized omega and corrected item-rest diagnostics.
    omega_summary_text = ft.Text("")
    omega_item_table = ft.Column()
    omega_report = ft.Text("")
    omega_warnings = ft.Text("")
    omega_chart_area = ft.Column()

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

    # Two independent groups: nominal group coding + confirmed outcome scale.
    group_variable = ft.Dropdown(
        label="Grouping variable (two categories)", width=300, options=[]
    )
    group_outcome = ft.Dropdown(
        label="Outcome variable", width=300, options=[]
    )
    group_outcome_scale = ft.Dropdown(
        label="Outcome measurement scale", width=270, value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
            ft.DropdownOption(key="nominal", text="Nominal (not supported)"),
        ],
    )
    group_method = ft.Dropdown(
        label="Statistical method", width=270, value="mannwhitney",
        options=[
            ft.DropdownOption(key="mannwhitney", text="Mann–Whitney U"),
            ft.DropdownOption(key="welch", text="Welch’s independent t"),
        ],
    )
    group_independent = ft.Checkbox(
        label="I confirm that the two groups contain independent observations",
        value=False,
    )
    group_assumptions = ft.Checkbox(
        label=(
            "For Welch only: I reviewed outcome distributions, "
            "outliers and suitability of mean comparisons"
        ),
        value=False,
    )
    group_advice = ft.Text("")
    group_output = ft.Text("")
    group_warnings = ft.Text("")
    group_chart = ft.Column()

    # Three or more independent groups (omnibus test, not post-hoc).
    omnibus_group = ft.Dropdown(
        label="Grouping variable (3–8 groups)", width=320, options=[]
    )
    omnibus_outcome = ft.Dropdown(
        label="Outcome variable", width=290, options=[]
    )
    omnibus_scale = ft.Dropdown(
        label="Outcome measurement scale", width=290, value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
        ],
    )
    omnibus_method = ft.Dropdown(
        label="Omnibus method", width=290, value="kruskal",
        options=[
            ft.DropdownOption(key="kruskal", text="Kruskal–Wallis H"),
            ft.DropdownOption(key="welch", text="Welch ANOVA"),
            ft.DropdownOption(key="anova", text="One-way ANOVA"),
        ],
    )
    omnibus_independent = ft.Checkbox(
        label="I confirm the groups contain independent participants",
        value=False,
    )
    omnibus_assumptions = ft.Checkbox(
        label="I reviewed distributions, outliers and assumptions of the chosen test",
        value=False,
    )
    omnibus_advice = ft.Text("")
    omnibus_main = ft.Text("")
    omnibus_brief = ft.Text("")
    omnibus_output = ft.Text("")
    omnibus_warnings = ft.Text("")
    omnibus_chart = ft.Column()
    omnibus_export_status = ft.Text("")
    omnibus_export_png_button = ft.Button("Save figure PNG", disabled=True)
    omnibus_export_txt_button = ft.Button("Save APA report TXT", disabled=True)
    omnibus_report_text = ""
    omnibus_png_data = None
    omnibus_result_data = None
    posthoc_output = ft.Text("")
    posthoc_table = ft.Column()
    posthoc_warnings = ft.Text("")
    posthoc_button = ft.Button("Run post-hoc comparisons", disabled=True)

    def clear_omnibus(e=None):
        nonlocal omnibus_report_text, omnibus_png_data, omnibus_result_data
        omnibus_report_text = ""
        omnibus_png_data = None
        omnibus_result_data = None
        posthoc_output.value = ""
        posthoc_table.controls.clear()
        posthoc_warnings.value = ""
        posthoc_button.disabled = True
        omnibus_main.value = ""
        omnibus_brief.value = ""
        omnibus_output.value = ""
        omnibus_warnings.value = ""
        omnibus_chart.controls.clear()
        omnibus_export_status.value = ""
        omnibus_export_png_button.disabled = True
        omnibus_export_txt_button.disabled = True
        omnibus_advice.value = recommend_omnibus_test(
            omnibus_scale.value, bool(omnibus_independent.value)
        )
        page.update()

    omnibus_group.on_select = clear_omnibus
    omnibus_outcome.on_select = clear_omnibus
    omnibus_scale.on_select = clear_omnibus
    omnibus_method.on_select = clear_omnibus
    omnibus_independent.on_change = clear_omnibus
    omnibus_assumptions.on_change = clear_omnibus

    # Paired design: each row must contain BOTH measurements of one participant.
    paired_before = ft.Dropdown(label="Before variable", width=280, options=[])
    paired_after = ft.Dropdown(label="After variable", width=280, options=[])
    paired_scale = ft.Dropdown(
        label="Measurement scale", width=250, value="unknown",
        options=[
            ft.DropdownOption(key="unknown", text="Not confirmed"),
            ft.DropdownOption(key="ordinal", text="Ordinal"),
            ft.DropdownOption(key="scale", text="Quantitative"),
        ],
    )
    paired_method = ft.Dropdown(
        label="Paired test", width=260, value="wilcoxon",
        options=[
            ft.DropdownOption(key="wilcoxon", text="Wilcoxon signed-rank"),
            ft.DropdownOption(key="paired_t", text="Paired-samples t-test"),
        ],
    )
    paired_confirm = ft.Checkbox(
        label="Each row contains two measurements from the SAME participant",
        value=False,
    )
    paired_assumptions = ft.Checkbox(
        label=(
            "I reviewed difference scores, their symmetry/normality as "
            "appropriate, outliers and independence between participants"
        ),
        value=False,
    )
    paired_advice = ft.Text("")
    paired_output = ft.Text("")
    paired_warnings = ft.Text("")
    paired_chart = ft.Column()
    paired_main = ft.Text("")
    paired_descriptive = ft.Text("")
    paired_brief = ft.Text("")
    paired_export_status = ft.Text("")
    paired_export_png_button = ft.Button("Save figure PNG", disabled=True)
    paired_export_txt_button = ft.Button("Save APA report TXT", disabled=True)
    paired_report_text = ""
    paired_png_data = None

    # Chi-square independence uses two categorical variables (not scores).
    chi_a = ft.Dropdown(label="Categorical variable A", width=300, options=[])
    chi_b = ft.Dropdown(label="Categorical variable B", width=300, options=[])
    chi_confirm = ft.Checkbox(
        label="I confirmed two categorical scales and independent observations",
        value=False,
    )
    chi_main = ft.Text("")
    chi_brief = ft.Text("")
    chi_output = ft.Text("")
    chi_warnings = ft.Text("")
    chi_chart = ft.Column()
    chi_export_status = ft.Text("")
    chi_export_png_button = ft.Button("Save figure PNG", disabled=True)
    chi_export_txt_button = ft.Button("Save APA report TXT", disabled=True)
    chi_report_text = ""
    chi_png_data = None

    def reset_chi_result(e=None):
        nonlocal chi_report_text, chi_png_data
        chi_report_text = ""
        chi_png_data = None
        chi_export_png_button.disabled = True
        chi_export_txt_button.disabled = True
        chi_export_status.value = ""
        chi_main.value = ""
        chi_brief.value = ""
        chi_output.value = ""
        chi_warnings.value = ""
        chi_chart.controls.clear()
        page.update()

    chi_a.on_select = reset_chi_result
    chi_b.on_select = reset_chi_result
    chi_confirm.on_change = reset_chi_result

    def update_paired_advice(e=None):
        nonlocal paired_report_text, paired_png_data
        paired_report_text = ""
        paired_png_data = None
        paired_export_png_button.disabled = True
        paired_export_txt_button.disabled = True
        paired_main.value = ""
        paired_descriptive.value = ""
        paired_brief.value = ""
        paired_export_status.value = ""
        paired_advice.value = recommend_paired_test(
            paired_scale.value, bool(paired_confirm.value)
        )
        paired_assumptions.value = False
        paired_output.value = ""
        paired_warnings.value = ""
        paired_chart.controls.clear()
        page.update()

    paired_scale.on_select = update_paired_advice
    paired_method.on_select = update_paired_advice
    paired_before.on_select = update_paired_advice
    paired_after.on_select = update_paired_advice
    paired_confirm.on_change = update_paired_advice

    def update_group_advice(e=None):
        group_advice.value = recommend_group_test(
            group_outcome_scale.value, bool(group_independent.value)
        )
        group_assumptions.value = False
        group_output.value = ""
        group_warnings.value = ""
        group_chart.controls.clear()
        page.update()

    group_variable.on_select = update_group_advice
    group_outcome.on_select = update_group_advice
    group_method.on_select = update_group_advice
    group_outcome_scale.on_select = update_group_advice
    group_independent.on_change = update_group_advice

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
        nonlocal dataframe, paired_report_text, paired_png_data, chi_report_text, chi_png_data, omnibus_report_text, omnibus_png_data, omnibus_result_data
        try:
            from_memory = isinstance(path, pd.DataFrame)
            df = (
                path.copy(deep=True) if from_memory
                else await asyncio.to_thread(load_dataset, path)
            )
            source_name = (
                "Prepared / local survey responses"
                if from_memory else Path(path).name
            )
            if df.columns.empty:
                raise ValueError("No variables found in this file.")
            overview = variable_overview(df)
        except Exception as error:
            status.value = f"Could not load file: {error}"
            page.update()
            return

        dataframe = df
        output_cache.clear()
        refresh_output_buttons()
        status.value = (
            f"Loaded: {source_name} | "
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
        omega_summary_text.value = ""
        omega_item_table.controls.clear()
        omega_report.value = ""
        omega_warnings.value = ""
        omega_chart_area.controls.clear()

        # Offer numeric variables but leave their measurement scales unconfirmed.
        numeric_candidates = [
            str(name) for name in df.columns
            if pd.api.types.is_numeric_dtype(df[name])
            and not looks_like_identifier(name)
        ]
        explore_variable.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        explore_variable.value = (
            "score" if "score" in numeric_candidates
            else (numeric_candidates[0] if numeric_candidates else None)
        )
        explore_group.options = [ft.DropdownOption(
            key="(none)", text="No grouping"
        )] + [
            ft.DropdownOption(key=str(name), text=str(name))
            for name in df.columns
            if not looks_like_identifier(name)
            and str(name) != explore_variable.value
            and 2 <= df[name].dropna().nunique() <= 8
        ]
        explore_group.value = "(none)"
        explore_output.value = ""
        explore_chart.controls.clear()
        rep_items.controls = [
            ft.Checkbox(
                label=name, value=name in {
                    "stress_before", "stress_mid", "stress_after"
                },
                on_change=clear_repeated,
            )
            for name in numeric_candidates
        ]
        rep_scale.value = "unknown"
        rep_method.value = "friedman"
        rep_same_people.value = False
        rep_assumptions.value = False
        rep_main.value = ""
        rep_brief.value = ""
        rep_report.value = ""
        rep_warnings.value = ""
        rep_chart.controls.clear()
        rep_pair_table.controls.clear()

        # Regression candidates exclude identifiers; categories still need manual review.
        reg_outcome.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        reg_outcome.value = (
            "stress_score" if "stress_score" in numeric_candidates
            else (numeric_candidates[-1] if numeric_candidates else None)
        )
        reg_predictors.controls = [
            ft.Checkbox(
                label=name,
                value=(name in {"study_hours", "sleep_hours"}),
            )
            for name in numeric_candidates if name != reg_outcome.value
        ]
        reg_hc3.value = False
        reg_confirm.value = False
        reg_main.value = ""
        reg_brief.value = ""
        reg_report.value = ""
        reg_warnings.value = ""
        reg_chart.controls.clear()

        # Group-adjusted general linear model candidate selection.
        ac_outcome.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        ac_outcome.value = (
            "wellbeing" if "wellbeing" in numeric_candidates
            else (numeric_candidates[-1] if numeric_candidates else None)
        )
        group_factors = [
            str(name) for name in df.columns
            if not looks_like_identifier(name)
            and 2 <= df[name].dropna().nunique() <= 6
        ]
        ac_group.options = [
            ft.DropdownOption(key=name, text=name)
            for name in group_factors
        ]
        ac_group.value = (
            "group" if "group" in group_factors
            else (group_factors[0] if group_factors else None)
        )
        ac_covariates.controls = [
            ft.Checkbox(
                label=name,
                value=name in {"age", "baseline_score"},
                on_change=clear_ancova,
            )
            for name in numeric_candidates
            if name not in {ac_outcome.value, ac_group.value}
        ]
        ac_mode.value = "ancova"
        ac_confirm.value = False
        ac_main.value = ""
        ac_brief.value = ""
        ac_means_table.controls.clear()
        ac_pairs_table.controls.clear()
        ac_chart.controls.clear()
        ac_report.value = ""
        ac_warnings.value = ""

        # Binary regression requires a verified 0/1 outcome.
        binary_outcomes = [
            name for name in numeric_candidates
            if set(df[name].dropna().unique().tolist()) == {0, 1}
        ]
        log_outcome.options = [
            ft.DropdownOption(key=name, text=name)
            for name in binary_outcomes
        ]
        log_outcome.value = (
            "wellbeing_improved" if "wellbeing_improved" in binary_outcomes
            else (binary_outcomes[0] if binary_outcomes else None)
        )
        log_predictors.controls = [
            ft.Checkbox(
                label=name,
                value=name in {"sleep_hours", "activity_hours"},
                on_change=clear_logistic,
            )
            for name in numeric_candidates
            if name != log_outcome.value
        ]
        log_confirm.value = False
        log_main.value = ""
        log_brief.value = ""
        log_odds_table.controls.clear()
        log_report.value = ""
        log_warnings.value = ""
        log_chart.controls.clear()

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

        # A group can use text or numeric codes; outcome must be numeric.
        grouping_candidates = [
            str(name) for name in df.columns if not looks_like_identifier(name)
        ]
        two_level_candidates = [
            name for name in grouping_candidates
            if df[name].dropna().nunique() == 2
        ]
        group_variable.options = [
            ft.DropdownOption(key=name, text=name)
            for name in grouping_candidates
        ]
        group_outcome.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        group_variable.value = (
            two_level_candidates[0] if two_level_candidates else None
        )
        group_outcome.value = next(
            (name for name in numeric_candidates if name != group_variable.value),
            None,
        )
        group_outcome_scale.value = "unknown"
        group_method.value = "mannwhitney"
        group_independent.value = False
        group_assumptions.value = False
        group_advice.value = recommend_group_test("unknown", False)
        group_output.value = ""
        group_warnings.value = ""
        group_chart.controls.clear()

        paired_before.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        paired_after.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        paired_before.value = (
            "before_score" if "before_score" in numeric_candidates
            else (numeric_candidates[0] if numeric_candidates else None)
        )
        paired_after.value = (
            "after_score" if "after_score" in numeric_candidates
            else (numeric_candidates[1] if len(numeric_candidates) > 1 else None)
        )
        paired_scale.value = "unknown"
        paired_method.value = "wilcoxon"
        paired_confirm.value = False
        paired_assumptions.value = False
        paired_advice.value = recommend_paired_test("unknown", False)
        paired_output.value = ""
        paired_warnings.value = ""
        paired_chart.controls.clear()
        paired_report_text = ""
        paired_png_data = None
        paired_export_png_button.disabled = True
        paired_export_txt_button.disabled = True
        paired_main.value = ""
        paired_descriptive.value = ""
        paired_brief.value = ""
        paired_export_status.value = ""

        category_candidates = [
            str(name) for name in df.columns
            if not looks_like_identifier(name)
            and 2 <= df[name].dropna().nunique() <= 10
        ]
        chi_a.options = [
            ft.DropdownOption(key=name, text=name)
            for name in category_candidates
        ]
        chi_b.options = [
            ft.DropdownOption(key=name, text=name)
            for name in category_candidates
        ]
        chi_a.value = (
            "group" if "group" in category_candidates
            else (category_candidates[0] if category_candidates else None)
        )
        chi_b.value = (
            "outcome" if "outcome" in category_candidates
            else next((v for v in category_candidates if v != chi_a.value), None)
        )
        chi_confirm.value = False
        chi_main.value = ""
        chi_brief.value = ""
        chi_output.value = ""
        chi_warnings.value = ""
        chi_chart.controls.clear()
        chi_report_text = ""
        chi_png_data = None
        chi_export_png_button.disabled = True
        chi_export_txt_button.disabled = True
        chi_export_status.value = ""

        # Offer appropriate candidates; the researcher still confirms scales.
        multi_group_candidates = [
            str(name) for name in df.columns
            if not looks_like_identifier(name)
            and 3 <= df[name].dropna().nunique() <= 8
        ]
        omnibus_group.options = [
            ft.DropdownOption(key=name, text=name)
            for name in multi_group_candidates
        ]
        omnibus_outcome.options = [
            ft.DropdownOption(key=name, text=name)
            for name in numeric_candidates
        ]
        omnibus_group.value = (
            "group" if "group" in multi_group_candidates
            else (multi_group_candidates[0] if multi_group_candidates else None)
        )
        omnibus_outcome.value = (
            "score" if "score" in numeric_candidates
            else next(
                (name for name in numeric_candidates
                 if name != omnibus_group.value),
                None,
            )
        )
        omnibus_scale.value = "unknown"
        omnibus_method.value = "kruskal"
        omnibus_independent.value = False
        omnibus_assumptions.value = False
        omnibus_report_text = ""
        omnibus_png_data = None
        omnibus_result_data = None
        posthoc_output.value = ""
        posthoc_warnings.value = ""
        posthoc_button.disabled = True
        omnibus_main.value = ""
        omnibus_brief.value = ""
        omnibus_output.value = ""
        omnibus_warnings.value = ""
        omnibus_advice.value = recommend_omnibus_test("unknown", False)
        omnibus_chart.controls.clear()
        omnibus_export_status.value = ""
        omnibus_export_png_button.disabled = True
        omnibus_export_txt_button.disabled = True
        # The source CSV/XLSX stays on disk unchanged. Preparation starts from a copy.
        reset_preparation(
            df, source_path=None if from_memory else path
        )
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

    async def load_paired_example(e):
        await show_file(PAIRED_SAMPLE)

    async def load_categorical_example(e):
        await show_file(CATEGORICAL_SAMPLE)

    async def load_three_groups_example(e):
        await show_file(THREE_GROUPS_SAMPLE)

    async def load_regression_example(e):
        await show_file(REGRESSION_SAMPLE)

    async def load_repeated_example(e):
        await show_file(REPEATED_SAMPLE)

    async def load_logistic_example(e):
        await show_file(LOGISTIC_SAMPLE)

    async def load_ancova_example(e):
        await show_file(ANCOVA_SAMPLE)

    async def load_ancova_interaction_example(e):
        await show_file(ANCOVA_INTERACTION_SAMPLE)

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
            remember_output(
                "reliability", "Cronbach alpha",
                reliability_output.value + "\n\n" + reliability_warnings.value, png
            )
        except Exception as error:
            reliability_output.value = f"Reliability analysis error: {error}"
        page.update()

    async def calculate_omega(e):
        omega_summary_text.value = ""
        omega_report.value = ""
        omega_warnings.value = ""
        omega_item_table.controls.clear()
        omega_chart_area.controls.clear()
        if dataframe is None:
            omega_summary_text.value = "Load a questionnaire dataset first."
            page.update()
            return

        selected = [
            box.label for box in reliability_items.controls if box.value
        ]
        if not reliability_confirm.value:
            omega_summary_text.value = (
                "Confirm common construct and correctly keyed reverse "
                "scoring before computing omega."
            )
            page.update()
            return

        omega_summary_text.value = "Estimating one-factor omega..."
        page.update()
        try:
            result = await asyncio.to_thread(
                analyze_omega, dataframe, selected
            )
            report = format_omega_report(result)
            png = await asyncio.to_thread(make_omega_chart, result)
            omega_summary_text.value = omega_summary(result)
            omega_report.value = report
            omega_warnings.value = "\n".join(result.warnings)
            omega_item_table.controls.append(
                ft.DataTable(
                    columns=[
                        ft.DataColumn(label=ft.Text(title))
                        for title in (
                            "Item", "M", "SD", "Missing",
                            "Item-rest r", "Loading", "Uniqueness",
                        )
                    ],
                    rows=[
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(item.name)),
                            ft.DataCell(ft.Text(f"{item.mean:.2f}")),
                            ft.DataCell(ft.Text(f"{item.sd:.2f}")),
                            ft.DataCell(ft.Text(str(item.missing))),
                            ft.DataCell(ft.Text(
                                f"{item.corrected_item_rest_r:.2f}"
                            )),
                            ft.DataCell(ft.Text(
                                f"{item.standardized_loading:.2f}"
                            )),
                            ft.DataCell(ft.Text(
                                f"{item.uniqueness:.2f}"
                            )),
                        ])
                        for item in result.diagnostics
                    ],
                )
            )
            height = min(
                950, max(440, 290 + len(result.items) * 48)
            )
            omega_chart_area.controls.append(
                ft.Image(src=png, width=1050, height=height)
            )
            remember_output(
                "reliability", "McDonald omega and item diagnostics",
                report, png,
            )
        except Exception as error:
            omega_summary_text.value = f"Omega analysis error: {error}"
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
            remember_output(
                "correlation", "Bivariate correlation",
                corr_output.value + "\n\n" + corr_warnings.value, figure
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
            matrix_rows = [
                "\t".join(["Variable", *analysis.names])
            ]
            for label, row in zip(analysis.names, analysis.coefficients):
                matrix_rows.append(
                    "\t".join([label, *[
                        f"{value:.3f}" if pd.notna(value) else "N/A"
                        for value in row
                    ]])
                )
            remember_output(
                "matrix", "Exploratory correlation matrix",
                matrix_output.value + "\n\n" + "\n".join(matrix_rows)
                + "\n\n" + matrix_warnings.value, png
            )
        except Exception as error:
            matrix_output.value = f"Correlation matrix error: {error}"
        page.update()

    async def calculate_groups(e):
        group_chart.controls.clear()
        group_warnings.value = ""

        if dataframe is None:
            group_output.value = "Load a dataset first."
            page.update()
            return
        if not group_variable.value or not group_outcome.value:
            group_output.value = "Choose grouping and outcome variables."
            page.update()
            return

        group_output.value = "Comparing groups and preparing chart..."
        page.update()
        try:
            comparison = await asyncio.to_thread(
                compare_independent_groups,
                dataframe,
                group_variable.value,
                group_outcome.value,
                group_method.value,
                group_outcome_scale.value,
                bool(group_independent.value),
                bool(group_assumptions.value),
            )
            group_output.value = format_group_comparison(comparison)
            group_warnings.value = "\n".join(comparison.warnings)
            figure = await asyncio.to_thread(
                make_group_comparison_chart, comparison
            )
            group_chart.controls.append(
                ft.Image(src=figure, width=850, height=550)
            )
            remember_output(
                "groups", "Independent-group comparison",
                group_output.value + "\n\n" + group_warnings.value, figure
            )
        except Exception as error:
            group_output.value = f"Group comparison error: {error}"
        page.update()

    async def calculate_paired(e):
        nonlocal paired_report_text, paired_png_data
        paired_chart.controls.clear()
        paired_main.value = ""
        paired_descriptive.value = ""
        paired_brief.value = ""
        paired_warnings.value = ""
        paired_export_status.value = ""
        paired_export_png_button.disabled = True
        paired_export_txt_button.disabled = True
        paired_report_text = ""
        paired_png_data = None

        if dataframe is None:
            paired_output.value = "Load a dataset first."
            page.update()
            return
        if not paired_before.value or not paired_after.value:
            paired_output.value = "Choose before and after variables."
            page.update()
            return

        paired_output.value = "Calculating paired test and drawing changes..."
        page.update()
        try:
            analysis = await asyncio.to_thread(
                analyze_paired, dataframe, paired_before.value, paired_after.value,
                paired_method.value, paired_scale.value,
                bool(paired_confirm.value), bool(paired_assumptions.value)
            )
            text_report = format_paired_report(analysis)
            png = await asyncio.to_thread(make_paired_chart, analysis)
            paired_report_text = text_report
            paired_png_data = png
            paired_main.value = paired_main_result(analysis)
            paired_descriptive.value = paired_descriptives(analysis)
            paired_brief.value = paired_interpretation(analysis)
            paired_output.value = text_report
            paired_warnings.value = "\n".join(analysis.warnings)
            paired_chart.controls.append(ft.Image(src=png, width=850, height=530))
            remember_output(
                "paired", "Paired comparison",
                text_report + "\n\n" + paired_warnings.value, png
            )
            paired_export_png_button.disabled = False
            paired_export_txt_button.disabled = False
        except Exception as error:
            paired_output.value = f"Paired analysis error: {error}"
        page.update()

    async def export_paired_png(e):
        if not paired_png_data:
            paired_export_status.value = "Run a paired analysis first."
        else:
            try:
                path = await asyncio.to_thread(
                    save_figure_png, paired_png_data, "paired_figure.png"
                )
                paired_export_status.value = f"Saved: {path}"
            except Exception as error:
                paired_export_status.value = f"Export error: {error}"
        page.update()

    async def export_paired_txt(e):
        if not paired_report_text:
            paired_export_status.value = "Run a paired analysis first."
        else:
            try:
                path = await asyncio.to_thread(
                    save_apa_txt, paired_report_text, "paired_APA7.txt"
                )
                paired_export_status.value = f"Saved: {path}"
            except Exception as error:
                paired_export_status.value = f"Export error: {error}"
        page.update()

    paired_export_png_button.on_click = export_paired_png
    paired_export_txt_button.on_click = export_paired_txt

    async def calculate_chi_square(e):
        nonlocal chi_report_text, chi_png_data
        chi_chart.controls.clear()
        chi_main.value = ""
        chi_brief.value = ""
        chi_warnings.value = ""
        chi_export_status.value = ""
        chi_export_png_button.disabled = True
        chi_export_txt_button.disabled = True
        chi_report_text = ""
        chi_png_data = None
        if dataframe is None:
            chi_output.value = "Load a dataset first."
            page.update()
            return
        chi_output.value = "Calculating categorical association..."
        page.update()
        try:
            analysis = await asyncio.to_thread(
                analyze_chi_square, dataframe, chi_a.value,
                chi_b.value, bool(chi_confirm.value)
            )
            png = await asyncio.to_thread(make_chi_square_chart, analysis)
            text_report = format_chi_square_report(analysis)
            chi_report_text = text_report
            chi_png_data = png
            chi_main.value = summarize_chi_square(analysis)
            chi_brief.value = interpret_chi_square(analysis)
            chi_output.value = text_report
            chi_warnings.value = "\n".join(analysis.warnings)
            chi_chart.controls.append(ft.Image(src=png, width=850, height=550))
            remember_output(
                "chi", "Chi-square independence",
                text_report + "\n\n" + chi_warnings.value, png
            )
            chi_export_png_button.disabled = False
            chi_export_txt_button.disabled = False
        except Exception as error:
            chi_output.value = f"Chi-square analysis error: {error}"
        page.update()

    async def export_chi_png(e):
        if not chi_png_data:
            chi_export_status.value = "Run Chi-square first."
        else:
            try:
                path = await asyncio.to_thread(
                    save_figure_png, chi_png_data, "chi_square_figure.png"
                )
                chi_export_status.value = f"Saved: {path}"
            except Exception as error:
                chi_export_status.value = f"Export error: {error}"
        page.update()

    async def export_chi_txt(e):
        if not chi_report_text:
            chi_export_status.value = "Run Chi-square first."
        else:
            try:
                path = await asyncio.to_thread(
                    save_apa_txt, chi_report_text, "chi_square_APA7.txt"
                )
                chi_export_status.value = f"Saved: {path}"
            except Exception as error:
                chi_export_status.value = f"Export error: {error}"
        page.update()

    chi_export_png_button.on_click = export_chi_png
    chi_export_txt_button.on_click = export_chi_txt

    async def calculate_omnibus(e):
        nonlocal omnibus_report_text, omnibus_png_data, omnibus_result_data
        omnibus_main.value = ""
        omnibus_brief.value = ""
        omnibus_result_data = None
        posthoc_output.value = ""
        posthoc_warnings.value = ""
        posthoc_button.disabled = True
        omnibus_output.value = "Calculating group comparison..."
        omnibus_warnings.value = ""
        omnibus_chart.controls.clear()
        omnibus_export_status.value = ""
        omnibus_export_png_button.disabled = True
        omnibus_export_txt_button.disabled = True
        omnibus_report_text = ""
        omnibus_png_data = None
        page.update()

        if dataframe is None:
            omnibus_output.value = "Load a dataset first."
            page.update()
            return
        try:
            analysis = await asyncio.to_thread(
                analyze_omnibus, dataframe,
                omnibus_group.value, omnibus_outcome.value,
                omnibus_method.value, omnibus_scale.value,
                bool(omnibus_independent.value),
                bool(omnibus_assumptions.value),
            )
            png = await asyncio.to_thread(make_omnibus_chart, analysis)
            report = format_omnibus_report(analysis)
            omnibus_main.value = format_omnibus_summary(analysis)
            omnibus_brief.value = interpret_omnibus(analysis)
            omnibus_output.value = report
            omnibus_warnings.value = "\n".join(analysis.warnings)
            omnibus_chart.controls.append(
                ft.Image(src=png, width=850, height=540)
            )
            omnibus_report_text = report
            omnibus_png_data = png
            remember_output(
                "omnibus", "ANOVA / Kruskal–Wallis",
                report + "\n\n" + omnibus_warnings.value, png
            )
            omnibus_result_data = analysis
            posthoc_button.disabled = False
            omnibus_export_png_button.disabled = False
            omnibus_export_txt_button.disabled = False
        except Exception as error:
            omnibus_output.value = f"Omnibus analysis error: {error}"
        page.update()

    async def calculate_posthoc(e):
        nonlocal omnibus_report_text
        if omnibus_result_data is None:
            posthoc_output.value = "Run the omnibus test first."
            page.update()
            return

        posthoc_output.value = "Calculating pairwise comparisons..."
        posthoc_warnings.value = ""
        posthoc_button.disabled = True
        page.update()
        try:
            comparisons = await asyncio.to_thread(
                analyze_posthoc, omnibus_result_data
            )
            text_report = format_posthoc_report(comparisons)
            posthoc_table.controls.clear()
            if comparisons.omnibus_method == "kruskal":
                headers = ["Pair", "Rank diff.", "z", "p adj.", "Sig."]
                data_rows = [
                    [
                        f"{p.first} - {p.second}",
                        f"{p.estimate:+.2f}",
                        f"{p.statistic:.2f}",
                        f"{p.p_adjusted:.3f}" if p.p_adjusted >= 0.001 else "< .001",
                        "Yes" if p.p_adjusted < 0.05 else "No",
                    ] for p in comparisons.pairs
                ]
            else:
                headers = ["Pair", "Mean diff.", "95% CI", "p adj.", "Sig."]
                data_rows = [
                    [
                        f"{p.first} - {p.second}",
                        f"{p.estimate:+.2f}",
                        f"[{p.ci_low:.2f}, {p.ci_high:.2f}]",
                        f"{p.p_adjusted:.3f}" if p.p_adjusted >= 0.001 else "< .001",
                        "Yes" if p.p_adjusted < 0.05 else "No",
                    ] for p in comparisons.pairs
                ]
            posthoc_table.controls.append(
                ft.DataTable(
                    columns=[ft.DataColumn(label=ft.Text(h)) for h in headers],
                    rows=[
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(value)) for value in row
                        ]) for row in data_rows
                    ],
                )
            )
            posthoc_output.value = (
                f"{comparisons.method}: "
                f"{sum(p.p_adjusted < 0.05 for p in comparisons.pairs)} of "
                f"{len(comparisons.pairs)} pairs have adjusted p < .05."
            )
            posthoc_warnings.value = "\n".join(comparisons.warnings)
            # Keep export coherent with visible current results.
            omnibus_report_text = (
                format_omnibus_report(omnibus_result_data)
                + "\n\n" + text_report
                + "\n\nAssumptions and limitations:\n"
                + "\n".join(comparisons.warnings)
            )
            remember_output(
                "omnibus", "ANOVA / Kruskal–Wallis with post-hoc",
                omnibus_report_text, omnibus_png_data
            )
        except Exception as error:
            posthoc_output.value = f"Post-hoc analysis error: {error}"
        finally:
            posthoc_button.disabled = False
        page.update()

    posthoc_button.on_click = calculate_posthoc

    async def export_omnibus_png(e):
        if not omnibus_png_data:
            omnibus_export_status.value = "Run an analysis first."
        else:
            try:
                path = await asyncio.to_thread(
                    save_figure_png, omnibus_png_data, "omnibus_figure.png"
                )
                omnibus_export_status.value = f"Saved: {path}"
            except Exception as error:
                omnibus_export_status.value = f"Export error: {error}"
        page.update()

    async def export_omnibus_txt(e):
        if not omnibus_report_text:
            omnibus_export_status.value = "Run an analysis first."
        else:
            try:
                path = await asyncio.to_thread(
                    save_apa_txt, omnibus_report_text, "omnibus_APA7.txt"
                )
                omnibus_export_status.value = f"Saved: {path}"
            except Exception as error:
                omnibus_export_status.value = f"Export error: {error}"
        page.update()

    omnibus_export_png_button.on_click = export_omnibus_png
    omnibus_export_txt_button.on_click = export_omnibus_txt

    async def run_explore(e):
        explore_output.value = "Preparing boxplots and diagnostic checks..."
        explore_chart.controls.clear()
        page.update()
        if dataframe is None or not explore_variable.value:
            explore_output.value = "Load a dataset and choose an outcome."
            page.update()
            return
        try:
            grouping = (
                explore_group.value if explore_group.value != "(none)"
                else None
            )
            investigation = await asyncio.to_thread(
                explore_quantitative,
                dataframe, explore_variable.value, grouping,
            )
            png = await asyncio.to_thread(
                make_explore_chart, investigation
            )
            report = format_explore_report(investigation)
            explore_output.value = report
            explore_chart.controls.append(
                ft.Image(src=png, width=900, height=500)
            )
            remember_output(
                "descriptive", f"Explore: {explore_variable.value}",
                report, png
            )
        except Exception as error:
            explore_output.value = f"Explore error: {error}"
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
            remember_output(
                "descriptive", f"Descriptive: {variable.value}",
                results.value + "\n\n" + guidance.value, png
            )
        except (ValueError, TypeError) as error:
            results.value = f"Cannot analyze this variable: {error}"

        page.update()

    async def run_regression(e):
        reg_main.value = ""
        reg_brief.value = ""
        reg_report.value = "Fitting the regression model..."
        reg_warnings.value = ""
        reg_chart.controls.clear()
        page.update()
        if dataframe is None or not reg_outcome.value:
            reg_report.value = "Load a dataset and choose a quantitative outcome."
            page.update()
            return
        chosen = [
            box.label for box in reg_predictors.controls
            if bool(box.value) and box.label != reg_outcome.value
        ]
        try:
            result = await asyncio.to_thread(
                analyze_regression, dataframe, reg_outcome.value,
                chosen, bool(reg_confirm.value), bool(reg_hc3.value),
            )
            image = await asyncio.to_thread(make_regression_chart, result)
            report = format_regression_report(result)
            reg_main.value = (
                f"N = {result.n_complete} | R² = {result.r_squared:.3f} | "
                f"Adjusted R² = {result.adjusted_r_squared:.3f}\n"
                f"F({result.model_df}, {result.residual_df}) = "
                f"{result.f_value:.2f}, {apa_p_value(result.f_p)}"
            )
            reg_brief.value = regression_brief(result)
            reg_report.value = report
            reg_warnings.value = "\n".join(result.warnings)
            reg_chart.controls.append(
                ft.Image(src=image, width=1080, height=440)
            )
            remember_output("regression", "Linear regression", report, image)
        except Exception as error:
            reg_report.value = f"Regression error: {error}"
        page.update()

    async def run_repeated(e):
        rep_main.value = ""
        rep_brief.value = ""
        rep_report.value = "Computing repeated-measures analysis..."
        rep_warnings.value = ""
        rep_chart.controls.clear()
        rep_pair_table.controls.clear()
        output_cache.pop("repeated", None)
        if active_section == "repeated":
            refresh_output_buttons()
        page.update()
        if dataframe is None:
            rep_report.value = "Load a dataset first."
            page.update()
            return

        selected = [
            control.label for control in rep_items.controls
            if bool(control.value)
        ]
        try:
            result = await asyncio.to_thread(
                analyze_repeated, dataframe, selected,
                rep_method.value, rep_scale.value,
                bool(rep_same_people.value), bool(rep_assumptions.value),
            )
            png = await asyncio.to_thread(make_repeated_chart, result)
            report = format_repeated_report(result)
            rep_main.value = repeated_main(result)
            rep_brief.value = repeated_brief(result)
            rep_report.value = report
            rep_warnings.value = "\n".join(result.warnings)
            rep_chart.controls.append(
                ft.Image(src=png, width=980, height=510)
            )

            columns = ["Pair", "Change", "Statistic", "p (Holm)", "Sig."]
            lines = []
            for pair in result.pairs:
                lines.append([
                    f"{pair.before} → {pair.after}",
                    f"{pair.estimate:+.2f}",
                    f"{pair.statistic:.2f}" if pair.statistic is not None else "N/A",
                    "< .001" if pair.p_holm < .001 else f"{pair.p_holm:.3f}",
                    "Yes" if pair.p_holm < .05 else "No",
                ])
            rep_pair_table.controls.append(ft.DataTable(
                columns=[ft.DataColumn(label=ft.Text(v)) for v in columns],
                rows=[
                    ft.DataRow(cells=[ft.DataCell(ft.Text(v)) for v in line])
                    for line in lines
                ],
            ))
            remember_output("repeated", "Repeated measurements", report, png)
        except Exception as error:
            rep_report.value = f"Repeated-measures error: {error}"
        page.update()

    async def run_logistic(e):
        clear_logistic()
        log_report.value = "Fitting binary logistic regression..."
        page.update()
        if dataframe is None or not log_outcome.value:
            log_report.value = "Load a dataset with a binary 0/1 outcome first."
            page.update()
            return

        chosen = [
            box.label for box in log_predictors.controls
            if bool(box.value) and box.label != log_outcome.value
        ]
        try:
            result = await asyncio.to_thread(
                binary_logistic_regression,
                dataframe, log_outcome.value, chosen,
                bool(log_confirm.value),
            )
            png = await asyncio.to_thread(make_logistic_chart, result)
            report = format_logistic_report(result)
            log_main.value = logistic_main(result)
            log_brief.value = logistic_brief(result)
            log_report.value = report
            log_warnings.value = "\n".join(result.warnings)

            columns = ["Variable", "B", "OR", "OR 95% CI", "p"]
            log_odds_table.controls.append(
                ft.DataTable(
                    columns=[
                        ft.DataColumn(label=ft.Text(name)) for name in columns
                    ],
                    rows=[
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(c.name)),
                            ft.DataCell(ft.Text(f"{c.b:+.3f}")),
                            ft.DataCell(ft.Text(f"{c.odds_ratio:.3f}")),
                            ft.DataCell(ft.Text(
                                f"[{c.or_low:.3f}, {c.or_high:.3f}]"
                            )),
                            ft.DataCell(ft.Text(apa_p_value(c.p))),
                        ])
                        for c in result.coefficients
                    ],
                )
            )
            log_chart.controls.append(
                ft.Image(src=png, width=1080, height=445)
            )
            remember_output(
                "logistic", "Binary logistic regression", report, png
            )
        except Exception as error:
            log_report.value = f"Logistic regression error: {error}"
        page.update()

    async def run_ancova(e):
        clear_ancova()
        ac_main.value = "Estimating covariate-adjusted group differences..."
        page.update()
        if dataframe is None or not ac_outcome.value or not ac_group.value:
            ac_main.value = "Load a dataset, choose an outcome and a group factor."
            page.update()
            return

        selected = [
            box.label for box in ac_covariates.controls if bool(box.value)
        ]
        try:
            result = await asyncio.to_thread(
                analyze_ancova,
                dataframe, ac_outcome.value, ac_group.value,
                selected, ac_mode.value, bool(ac_confirm.value),
            )
            chart = await asyncio.to_thread(make_ancova_chart, result)
            report = format_ancova_report(result)
            ac_main.value = ancova_main(result)
            ac_brief.value = ancova_brief(result)
            ac_report.value = report
            ac_warnings.value = "\n".join(result.warnings)
            ac_chart.controls.append(
                ft.Image(src=chart, width=1060, height=485)
            )
            means_columns = [
                "Group", "N", "Raw mean", "Adjusted mean", "95% CI"
            ]
            ac_means_table.controls.append(ft.DataTable(
                columns=[
                    ft.DataColumn(label=ft.Text(title))
                    for title in means_columns
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(g.label)),
                        ft.DataCell(ft.Text(str(g.n))),
                        ft.DataCell(ft.Text(f"{g.raw_mean:.2f}")),
                        ft.DataCell(ft.Text(f"{g.adjusted_mean:.2f}")),
                        ft.DataCell(ft.Text(
                            f"[{g.ci_low:.2f}, {g.ci_high:.2f}]"
                        )),
                    ]) for g in result.groups
                ],
            ))
            pairs_columns = [
                "Pair", "Adjusted diff.", "t", "Holm p", "Sig."
            ]
            ac_pairs_table.controls.append(ft.DataTable(
                columns=[
                    ft.DataColumn(label=ft.Text(title))
                    for title in pairs_columns
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(
                            f"{p.first} → {p.second}"
                        )),
                        ft.DataCell(ft.Text(f"{p.difference:+.2f}")),
                        ft.DataCell(ft.Text(f"{p.t:.2f}")),
                        ft.DataCell(ft.Text(apa_p_value(p.p_holm))),
                        ft.DataCell(ft.Text(
                            "Yes" if p.p_holm < .05 else "No"
                        )),
                    ]) for p in result.pairs
                ],
            ))
            remember_output(
                "ancova", "ANCOVA / General Linear Model",
                report, chart,
            )
        except Exception as error:
            ac_main.value = f"ANCOVA / GLM error: {error}"
            ac_report.value = ac_main.value
        page.update()

    # Create local-first questionnaire and data-preparation tools after
    # the Dataset loading callback is defined; both reuse that callback.
    preparation_panel, reset_preparation = build_preparation_workspace(
        page, load_dataframe=show_file
    )
    survey_panel = build_survey_workspace(
        page, load_dataframe=show_file,
        root=Path(__file__).resolve().parent / "data" / "surveys",
    )

    # STEP 6: Present existing actions in separate, easier-to-navigate screens.
    ui = build_interface(
        page,
        controls={
            "status": status,
            "output_toolbar": output_toolbar,
            "overview_area": overview_area,
            "preparation_panel": preparation_panel,
            "survey_panel": survey_panel,
            "variable": variable,
            "scale": scale,
            "results": results,
            "guidance": guidance,
            "chart_area": chart_area,
            "explore_variable": explore_variable,
            "explore_group": explore_group,
            "explore_output": explore_output,
            "explore_chart": explore_chart,
            "reg_outcome": reg_outcome,
            "reg_predictors": reg_predictors,
            "reg_hc3": reg_hc3,
            "reg_confirm": reg_confirm,
            "reg_main": reg_main,
            "reg_brief": reg_brief,
            "reg_report": reg_report,
            "reg_warnings": reg_warnings,
            "reg_chart": reg_chart,
            "log_outcome": log_outcome,
            "log_predictors": log_predictors,
            "log_confirm": log_confirm,
            "log_main": log_main,
            "log_brief": log_brief,
            "log_odds_table": log_odds_table,
            "log_report": log_report,
            "log_warnings": log_warnings,
            "log_chart": log_chart,
            "ac_outcome": ac_outcome,
            "ac_group": ac_group,
            "ac_covariates": ac_covariates,
            "ac_mode": ac_mode,
            "ac_confirm": ac_confirm,
            "ac_main": ac_main,
            "ac_brief": ac_brief,
            "ac_means_table": ac_means_table,
            "ac_pairs_table": ac_pairs_table,
            "ac_chart": ac_chart,
            "ac_report": ac_report,
            "ac_warnings": ac_warnings,
            "rep_items": rep_items,
            "rep_scale": rep_scale,
            "rep_method": rep_method,
            "rep_same_people": rep_same_people,
            "rep_assumptions": rep_assumptions,
            "rep_main": rep_main,
            "rep_brief": rep_brief,
            "rep_report": rep_report,
            "rep_warnings": rep_warnings,
            "rep_chart": rep_chart,
            "rep_pair_table": rep_pair_table,
            "reliability_items": reliability_items,
            "reliability_confirm": reliability_confirm,
            "reliability_output": reliability_output,
            "reliability_guide": reliability_guide,
            "reliability_warnings": reliability_warnings,
            "reliability_chart_area": reliability_chart_area,
            "omega_summary_text": omega_summary_text,
            "omega_item_table": omega_item_table,
            "omega_report": omega_report,
            "omega_warnings": omega_warnings,
            "omega_chart_area": omega_chart_area,
            "corr_x": corr_x,
            "corr_y": corr_y,
            "corr_scale_x": corr_scale_x,
            "corr_scale_y": corr_scale_y,
            "corr_advice": corr_advice,
            "corr_method": corr_method,
            "corr_confirm": corr_confirm,
            "corr_output": corr_output,
            "corr_warnings": corr_warnings,
            "corr_chart": corr_chart,
            "matrix_items": matrix_items,
            "matrix_method": matrix_method,
            "matrix_confirm": matrix_confirm,
            "matrix_output": matrix_output,
            "matrix_warnings": matrix_warnings,
            "matrix_chart": matrix_chart,
            "group_variable": group_variable,
            "group_outcome": group_outcome,
            "group_outcome_scale": group_outcome_scale,
            "group_method": group_method,
            "group_independent": group_independent,
            "group_assumptions": group_assumptions,
            "group_advice": group_advice,
            "group_output": group_output,
            "group_warnings": group_warnings,
            "group_chart": group_chart,
            "paired_before": paired_before,
            "paired_after": paired_after,
            "paired_scale": paired_scale,
            "paired_method": paired_method,
            "paired_confirm": paired_confirm,
            "paired_assumptions": paired_assumptions,
            "paired_advice": paired_advice,
            "paired_output": paired_output,
            "paired_warnings": paired_warnings,
            "paired_chart": paired_chart,
            "paired_main": paired_main,
            "paired_descriptive": paired_descriptive,
            "paired_brief": paired_brief,
            "paired_export_png_button": paired_export_png_button,
            "paired_export_txt_button": paired_export_txt_button,
            "paired_export_status": paired_export_status,
            "chi_a": chi_a,
            "chi_b": chi_b,
            "chi_confirm": chi_confirm,
            "chi_main": chi_main,
            "chi_brief": chi_brief,
            "chi_output": chi_output,
            "chi_warnings": chi_warnings,
            "chi_chart": chi_chart,
            "chi_export_png_button": chi_export_png_button,
            "chi_export_txt_button": chi_export_txt_button,
            "chi_export_status": chi_export_status,
            "omnibus_group": omnibus_group,
            "omnibus_outcome": omnibus_outcome,
            "omnibus_scale": omnibus_scale,
            "omnibus_method": omnibus_method,
            "omnibus_independent": omnibus_independent,
            "omnibus_assumptions": omnibus_assumptions,
            "omnibus_advice": omnibus_advice,
            "omnibus_main": omnibus_main,
            "omnibus_brief": omnibus_brief,
            "omnibus_output": omnibus_output,
            "omnibus_warnings": omnibus_warnings,
            "omnibus_chart": omnibus_chart,
            "omnibus_export_png_button": omnibus_export_png_button,
            "omnibus_export_txt_button": omnibus_export_txt_button,
            "omnibus_export_status": omnibus_export_status,
            "posthoc_button": posthoc_button,
            "posthoc_output": posthoc_output,
            "posthoc_table": posthoc_table,
            "posthoc_warnings": posthoc_warnings,
        },
        actions={
            "choose_file": choose_file,
            "set_active_screen": set_active_screen,
            "load_sample": load_sample,
            "load_scale_example": load_scale_example,
            "analyze_variable": analyze_variable,
            "run_explore": run_explore,
            "run_regression": run_regression,
            "run_logistic": run_logistic,
            "run_ancova": run_ancova,
            "load_ancova_example": load_ancova_example,
            "load_ancova_interaction_example": load_ancova_interaction_example,
            "load_logistic_example": load_logistic_example,
            "run_repeated": run_repeated,
            "load_repeated_example": load_repeated_example,
            "load_regression_example": load_regression_example,
            "calculate_alpha": calculate_alpha,
            "calculate_omega": calculate_omega,
            "calculate_correlation": calculate_correlation,
            "calculate_matrix": calculate_matrix,
            "calculate_groups": calculate_groups,
            "calculate_paired": calculate_paired,
            "load_paired_example": load_paired_example,
            "load_categorical_example": load_categorical_example,
            "calculate_chi_square": calculate_chi_square,
            "calculate_omnibus": calculate_omnibus,
            "load_three_groups_example": load_three_groups_example,
        },
    )
    page.add(ui)
    page.update()


if __name__ == "__main__":
    ft.run(main)
