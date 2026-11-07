"""Flet interface layout for the Statistical Research Assistant.

The interface is divided into fifteen screens. Calculation logic stays in app.py;
existing controls are reused, so switching screens preserves user selections.
"""

from pathlib import Path

import flet as ft
from localization import LANGUAGES, tr
from statistical_guide import GUIDE_LABELS, method_guide_items
from desktop_shell_text import shell_label
from desktop_button_style import style_buttons


def build_interface(
    page: ft.Page, controls: dict, actions: dict, *,
    language: str = "en", on_language_change=None,
    appearance: str = "windows", on_appearance_change=None,
):
    """Create a navigation shell. English is the fresh-install default."""
    c = controls
    a = actions
    language = language if language in LANGUAGES else "en"
    translated_controls = []
    appearance = appearance if appearance in {"windows", "macos"} else "windows"
    cornered = []
    nav_groups = []
    menu_texts = []
    shell_root = None

    def corner_radius():
        return 10 if appearance == "macos" else 0

    def square_button_style(*, active=False):
        return ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=corner_radius()),
            bgcolor="#E5EFFC" if active else "#FFFFFF",
            color="#164C96" if active else "#283C58",
            elevation=0,
        )

    def localized_text(value="", *args, **kwargs):
        translated = tr(language, value) if isinstance(value, str) else value
        control = ft.Text(translated, *args, **kwargs)
        if isinstance(value, str):
            translated_controls.append((control, value))
        return control

    def heading(title, subtitle):
        return ft.Column(
            controls=[
                localized_text(title, size=27, weight="bold", color="#172A43"),
                localized_text(subtitle, color="#607087", size=13),
            ],
            spacing=5,
        )

    def panel(title, content):
        container = ft.Container(
            bgcolor="#FFFFFF",
            border_radius=corner_radius(),
            border=ft.Border.all(1, "#E1E7F1"),
            padding=20,
            content=ft.Column(
                controls=[
                    localized_text(title, size=17, weight="bold", color="#172A43"),
                    *content,
                ],
                spacing=13,
            ),
        )
        cornered.append(container)
        return container

    def start_card(title, description, action, action_label, icon):
        container = ft.Container(
            col={"xs": 12, "md": 6, "lg": 4},
            padding=20,
            bgcolor="#FFFFFF",
            border_radius=corner_radius(),
            border=ft.Border.all(1, "#DBE4F0"),
            content=ft.Column(
                controls=[
                    ft.Icon(icon, size=30, color="#2755A1"),
                    localized_text(title, size=18, weight="bold", color="#172A43"),
                    localized_text(description, size=13, color="#607087"),
                    ft.Button(
                        content=localized_text(action_label),
                        style=square_button_style(),
                        **(
                            {"action": action}
                            if isinstance(action, ft.PickFiles)
                            else {"on_click": action}
                        ),
                    ),
                ],
                spacing=12,
            ),
        )
        cornered.append(container)
        return container

    async def open_sample_from_home(e):
        await a["load_sample"](e)
        switch_screen("dataset")

    home_banner = ft.Container(
        padding=24,
        bgcolor="#EAF1FD",
        border_radius=corner_radius(),
        content=ft.Column(
            controls=[
                localized_text("YOUR RESEARCH WORKSPACE", size=12,
                        weight="bold", color="#2755A1"),
                localized_text("Start with a question. We'll help with the data.",
                        size=28, weight="bold", color="#172A43"),
                localized_text(
                    "Create questionnaires, prepare datasets and run "
                    "statistical analyses on this computer. Choose a "
                    "starting point below; no previous SPSS experience is needed.",
                    size=14, color="#415570",
                ),
            ],
            spacing=9,
        ),
    )
    cornered.append(home_banner)

    preview_entry = []
    if a.get("open_workspace_preview"):
        preview_entry = [ft.Container(
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
            bgcolor="#FFFFFF", border=ft.Border.all(1, "#DBE4F0"),
            border_radius=corner_radius(),
            content=ft.Row(
                controls=[
                    ft.Icon(ft.Icons.SCIENCE_OUTLINED, color="#2755A1"),
                    ft.Column(
                        controls=[
                            localized_text("Try the new research workspace (Stage 33 preview)",
                                           size=15, weight="bold", color="#172A43"),
                            localized_text(
                                "Guided analysis, a results log, a three-pane questionnaire "
                                "builder and a focused scientific import. Same engine, same "
                                "data; this classic interface stays available.",
                                size=13, color="#415570"),
                        ],
                        spacing=3, expand=True,
                    ),
                    ft.Button(
                        content=localized_text("Open the preview"),
                        on_click=a["open_workspace_preview"],
                        data="open-workspace-preview",
                    ),
                ],
                spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            data="workspace-preview-entry",
        )]
        cornered.append(preview_entry[0])

    home_screen = ft.Column(
        controls=[
            home_banner,
            *preview_entry,
            localized_text("What would you like to do?", size=20,
                    weight="bold", color="#172A43"),
            ft.ResponsiveRow(
                columns=12, spacing=14, run_spacing=14,
                controls=[
                    start_card(
                        "Open research data",
                        "Import a CSV or Excel file, check variables and "
                        "missing responses, then choose an analysis.",
                        a.get("choose_file_action", a["choose_file"]),
                        "Open CSV / Excel", ft.Icons.UPLOAD_FILE,
                    ),
                    start_card(
                        "Design a questionnaire",
                        "Build pages and rating scales, preview the respondent "
                        "experience, collect local test answers.",
                        lambda e: switch_screen("survey"),
                        "Create questionnaire", ft.Icons.ASSIGNMENT_OUTLINED,
                    ),
                    start_card(
                        "Try a guided example",
                        "Load fictional sample responses and learn how to "
                        "inspect data without using real participant records.",
                        open_sample_from_home,
                        "Explore sample data", ft.Icons.SCIENCE_OUTLINED,
                    ),
                ],
            ),
            c.get("home_import_feedback", ft.Text("")),
            localized_text(
                "File chooser not opening? Open Dataset and paste the "
                "full local file path under Import settings.",
                size=12, color="#6B7280",
            ),
            panel("A simple research workflow", [
                localized_text(
                    "1  Prepare or collect data    →    2  Review variable types "
                    "and missingness    →    3  Choose a statistical method "
                    "    →    4  Inspect assumptions and export the result",
                    size=13, color="#415570",
                ),
                ft.Row(
                    controls=[
                        ft.Button(
                            content=localized_text("Browse statistical methods"),
                            on_click=lambda e: switch_screen("descriptive"),
                        ),
                        ft.Button(
                            content=localized_text("See loaded dataset"),
                            on_click=lambda e: switch_screen("dataset"),
                        ),
                    ],
                    wrap=True, spacing=10,
                ),
            ]),
            localized_text(
                "Private by design: local files and survey responses are not "
                "automatically uploaded. Check consent and data-retention "
                "requirements before collecting real participant data.",
                color="#607087", size=12,
            ),
        ],
        spacing=18,
    )

    # Screen 1: upload and inspect the current local dataset.
    dataset_screen = ft.Column(
        controls=[
            heading(
                "Dataset",
                "Import research data and inspect its variables before analysis.",
            ),
            panel("Choose a data source", [
                ft.Button(
                    content=localized_text("Open CSV / Excel"),
                    icon=ft.Icons.FOLDER_OPEN,
                    **(
                        {"action": a["choose_file_action"]}
                        if "choose_file_action" in a
                        else {"on_click": a["choose_file"]}
                    ),
                ),
                ft.ExpansionTile(
                    title="Try a fictional example dataset",
                    expanded=False,
                    controls=[
                        ft.Row(controls=[
                            ft.Button("Load survey example", on_click=a["load_sample"]),
                        ft.Button("Load scale example", on_click=a["load_scale_example"]),
                        ft.Button("Load factor example", on_click=a["load_factor_example"]),
                        ft.Button("Load paired example", on_click=a["load_paired_example"]),
                        ft.Button("Load categorical example", on_click=a["load_categorical_example"]),
                        ft.Button("Load three-group example", on_click=a["load_three_groups_example"]),
                        ft.Button("Load regression example", on_click=a["load_regression_example"]),
                        ft.Button("Load logistic example", on_click=a["load_logistic_example"]),
                        ft.Button("Load ANCOVA example", on_click=a["load_ancova_example"]),
                        ft.Button("Load interaction example", on_click=a["load_ancova_interaction_example"]),
                            ft.Button("Load repeated example", on_click=a["load_repeated_example"]),
                        ], wrap=True, spacing=10),
                    ],
                ),
                localized_text(
                    "Files are processed locally. Real participant records should "
                    "not be committed to a public repository.",
                    color="#607087",
                    size=12,
                ),
            ]),
            panel("Import settings", [
                c.get("import_panel", localized_text("No file imported yet.")),
            ]),
            panel("Variable overview", [
                localized_text(
                    "Check missing values and types. Numeric storage does not "
                    "prove that a measurement is continuous.",
                    color="#607087",
                ),
                c["overview_area"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Local data preparation and questionnaire collection are separate workflows.
    preparation_screen = ft.Column(
        controls=[
            heading(
                "Data preparation",
                "Recode, reverse-score, handle missing codes and derive scale variables.",
            ),
            panel("Non-destructive transformation workspace", [
                c["preparation_panel"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    survey_screen = ft.Column(
        controls=[
            heading(
                "Questionnaire builder",
                "Design a local questionnaire, enter responses and analyze them.",
            ),
            panel("Local forms and collected responses", [
                c["survey_panel"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 2: one variable, one appropriate descriptive graph.
    descriptive_screen = ft.Column(
        controls=[
            heading(
                "Descriptive statistics",
                "Inspect a single variable using its confirmed measurement scale.",
            ),
            panel("Choose a variable", [
                ft.Row(
                    controls=[c["variable"], c["scale"]],
                    wrap=True,
                    spacing=12,
                ),
                ft.Button(
                    "Analyze selected variable",
                    on_click=a["analyze_variable"],
                ),
            ]),
            panel("Results and distribution", [
                c["results"],
                c["guidance"],
                c["chart_area"],
            ]),
            panel("Explore: boxplot and assumption checks", [
                localized_text(
                    "Choose a quantitative outcome and optional grouping variable. "
                    "The figure includes a boxplot and normal Q–Q plot.",
                    color="#607087",
                ),
                ft.Row(
                    controls=[c["explore_variable"], c["explore_group"]],
                    wrap=True, spacing=12,
                ),
                ft.Button("Explore distributions", on_click=a["run_explore"]),
                c["explore_output"],
                c["explore_chart"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 3: psychometric reliability and APA-style report.
    reliability_screen = ft.Column(
        controls=[
            heading(
                "Scale reliability",
                "Cronbach’s α for multiple items measuring the same construct.",
            ),
            panel("Select questionnaire items", [
                localized_text(
                    "Select at least three items from one scale. Check any "
                    "reverse-scored items before running the analysis.",
                    color="#607087",
                ),
                c["reliability_items"],
                c["reliability_confirm"],
                c["omega_ci_reps"],
                ft.Row(
                    controls=[
                        ft.Button(
                            "Calculate Cronbach’s α",
                            on_click=a["calculate_alpha"],
                        ),
                        ft.Button(
                            "Calculate McDonald’s ω + item analysis",
                            on_click=a["calculate_omega"],
                        ),
                    ],
                    wrap=True, spacing=10,
                ),
                localized_text(
                    "Both methods use the chosen complete-case items. "
                    "Omega uses a Pearson one-factor model and does not "
                    "automatically reverse-score answers. Optional CI "
                    "resamples whole respondents with a fixed random seed.",
                    size=12, color="#607087",
                ),
            ]),
            panel("Cronbach’s α: APA-style result", [
                c["reliability_output"],
                c["reliability_guide"],
                c["reliability_warnings"],
            ]),
            panel("Cronbach α figure", [
                c["reliability_chart_area"],
            ]),
            panel("McDonald’s ω: one-factor estimate", [
                c["omega_summary_text"],
            ]),
            panel("Item diagnostics", [
                c["omega_item_table"],
            ]),
            panel("Omega figure: item–rest correlations and loadings", [
                c["omega_chart_area"],
            ]),
            panel("Omega report and methodological cautions", [
                ft.ExpansionTile(
                    title="Show full one-factor reliability report",
                    expanded=False,
                    controls=[c["omega_report"]],
                ),
                ft.ExpansionTile(
                    title="Review omega assumptions and limitations",
                    expanded=False,
                    controls=[c["omega_warnings"]],
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    factor_screen = ft.Column(
        controls=[
            heading(
                "Exploratory EFA / PCA",
                "PCA is total-variance data reduction; EFA estimates latent shared structure.",
            ),
            panel("Select questionnaire or measurement variables", [
                localized_text(
                    "Select 3–12 numeric research items from a coherent set. "
                    "At least max(60, 8 × item count) complete rows are required.",
                    color="#607087",
                ),
                c["factor_items"],
                ft.Row(
                    controls=[
                        c["factor_method"], c["factor_count"],
                        c["factor_rotation"],
                    ], wrap=True, spacing=10,
                ),
                localized_text(
                    "PCA uses unrotated total-variance components. EFA uses "
                    "principal-axis common-factor extraction, optionally "
                    "varimax (orthogonal) or oblimin (correlated factors). "
                    "Rotating PCA is not implemented.",
                    size=12, color="#607087",
                ),
                c["factor_confirm"],
                ft.Button(
                    "Run exploratory factor / component analysis",
                    on_click=a["calculate_factor_exploration"],
                ),
            ]),
            panel("Factorability and retention summary", [
                c["factor_main_text"],
            ]),
            panel("Scree, parallel analysis and item loadings", [
                c["factor_chart_area"],
            ]),
            panel("Component / factor loading matrix", [
                c["factor_loading_table"],
                c["factor_correlation_text"],
            ]),
            panel("APA-style report and methodological limitations", [
                ft.ExpansionTile(
                    title="Show full exploration report",
                    controls=[c["factor_report"]], expanded=False,
                ),
                ft.ExpansionTile(
                    title="Review factor-analysis cautions",
                    controls=[c["factor_warnings"]], expanded=False,
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 4: two-variable inferential correlation analysis.
    correlation_screen = ft.Column(
        controls=[
            heading(
                "Correlations",
                "Test association between two confirmed measurements.",
            ),
            panel("Select two variables", [
                ft.Row(
                    controls=[c["corr_x"], c["corr_y"]],
                    wrap=True,
                    spacing=12,
                ),
                ft.Row(
                    controls=[c["corr_scale_x"], c["corr_scale_y"]],
                    wrap=True,
                    spacing=12,
                ),
                c["corr_advice"],
                c["corr_method"],
                c["corr_confirm"],
                ft.Button(
                    "Calculate correlation",
                    on_click=a["calculate_correlation"],
                ),
            ]),
            panel("Statistical result", [
                c["corr_output"],
                c["corr_warnings"],
            ]),
            panel("Scatterplot", [
                c["corr_chart"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 5: exploratory heatmap with pairwise sample sizes.
    matrix_screen = ft.Column(
        controls=[
            heading(
                "Correlation matrix",
                "Explore 2–8 variables together without automatic significance claims.",
            ),
            panel("Select variables and method", [
                c["matrix_items"],
                c["matrix_method"],
                c["matrix_confirm"],
                ft.Button(
                    "Calculate correlation matrix",
                    on_click=a["calculate_matrix"],
                ),
            ]),
            panel("Matrix summary", [
                c["matrix_output"],
                c["matrix_warnings"],
            ]),
            panel("Correlation heatmap", [
                c["matrix_chart"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 6: independent-group Welch t and Mann–Whitney U comparisons.
    groups_screen = ft.Column(
        controls=[
            heading(
                "Compare two groups",
                "Choose two independent groups and a suitable outcome measurement.",
            ),
            panel("Study design and variables", [
                localized_text(
                    "This module does not support paired or repeated-measure data. "
                    "The group variable must have exactly two observed categories.",
                    color="#607087",
                ),
                ft.Row(
                    controls=[c["group_variable"], c["group_outcome"]],
                    wrap=True,
                    spacing=12,
                ),
                ft.Row(
                    controls=[c["group_outcome_scale"], c["group_method"]],
                    wrap=True,
                    spacing=12,
                ),
                c["group_advice"],
                c["group_independent"],
                c["group_assumptions"],
                ft.Button(
                    "Compare groups",
                    on_click=a["calculate_groups"],
                ),
            ]),
            panel("APA 7-style statistical result", [
                c["group_output"],
                c["group_warnings"],
            ]),
            panel("Group distributions", [
                c["group_chart"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 7: before/after measurements from the same respondents.
    paired_screen = ft.Column(
        controls=[
            heading(
                "Paired measurements",
                "Compare before and after results from the same participants.",
            ),
            panel("Select repeated measurements", [
                localized_text(
                    "Each spreadsheet row must represent one participant, "
                    "with both values aligned. Independent groups are not paired.",
                    color="#607087",
                ),
                ft.Row(
                    controls=[c["paired_before"], c["paired_after"]],
                    wrap=True, spacing=12,
                ),
                ft.Row(
                    controls=[c["paired_scale"], c["paired_method"]],
                    wrap=True, spacing=12,
                ),
                c["paired_confirm"],
                c["paired_advice"],
                c["paired_assumptions"],
                ft.Button("Compare paired scores", on_click=a["calculate_paired"]),
            ]),
            panel("A. Main result", [
                c["paired_main"],
                c["paired_brief"],
            ]),
            panel("B. Descriptives", [
                c["paired_descriptive"],
            ]),
            panel("C. Notes / assumptions", [
                c["paired_warnings"],
            ]),
            panel("APA 7 report and local export", [
                c["paired_output"],
                ft.Row(
                    controls=[
                        c["paired_export_png_button"],
                        c["paired_export_txt_button"],
                    ],
                    wrap=True, spacing=12,
                ),
                c["paired_export_status"],
            ]),
            panel("Individual changes", [
                c["paired_chart"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 8: independence test for categorical variables.
    chi_screen = ft.Column(
        controls=[
            heading(
                "Chi-square association",
                "Explore association between two categorical variables.",
            ),
            panel("Select categorical variables", [
                localized_text(
                    "Choose two nominal or ordinal variables (including coded "
                    "categories). This is a test of independence, not of means.",
                    color="#607087",
                ),
                ft.Row(
                    controls=[c["chi_a"], c["chi_b"]],
                    wrap=True, spacing=12,
                ),
                c["chi_confirm"],
                ft.Button(
                    "Calculate χ²",
                    on_click=a["calculate_chi_square"],
                ),
            ]),
            panel("A. Main result and interpretation", [
                c["chi_main"],
                c["chi_brief"],
            ]),
            panel("B. Observed and expected counts / APA text", [
                c["chi_output"],
                ft.Row(
                    controls=[
                        c["chi_export_png_button"],
                        c["chi_export_txt_button"],
                    ],
                    wrap=True, spacing=12,
                ),
                c["chi_export_status"],
            ]),
            panel("C. Notes / assumptions", [
                c["chi_warnings"],
            ]),
            panel("Contingency table figure", [
                c["chi_chart"],
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 9: summary and figure first; detailed text can be expanded.
    omnibus_screen = ft.Column(
        controls=[
            heading(
                "ANOVA & Kruskal–Wallis",
                "Compare 3–8 independent groups and review assumptions.",
            ),
            panel("Choose groups, outcome and method", [
                ft.Row(
                    controls=[c["omnibus_group"], c["omnibus_outcome"]],
                    wrap=True, spacing=12,
                ),
                ft.Row(
                    controls=[c["omnibus_scale"], c["omnibus_method"]],
                    wrap=True, spacing=12,
                ),
                c["omnibus_independent"],
                c["omnibus_assumptions"],
                c["omnibus_advice"],
                ft.Button(
                    "Run group comparison", on_click=a["calculate_omnibus"]
                ),
            ]),
            panel("Main result and interpretation", [
                c["omnibus_main"],
                c["omnibus_brief"],
            ]),
            panel("Group distributions", [
                c["omnibus_chart"],
            ]),
            panel("Post-hoc pairwise comparisons", [
                c["posthoc_button"],
                c["posthoc_table"],
                c["posthoc_output"],
                ft.ExpansionTile(
                    title="Pairwise assumptions and cautions",
                    expanded=False,
                    controls=[c["posthoc_warnings"]],
                ),
            ]),
            panel("Full APA report and exports", [
                ft.ExpansionTile(
                    title="Show full statistical report",
                    expanded=False,
                    controls=[c["omnibus_output"]],
                ),
                ft.Row(
                    controls=[
                        c["omnibus_export_png_button"],
                        c["omnibus_export_txt_button"],
                    ],
                    wrap=True, spacing=12,
                ),
                c["omnibus_export_status"],
            ]),
            panel("Assumptions and cautions", [
                ft.ExpansionTile(
                    title="View methodological notes",
                    expanded=False,
                    controls=[c["omnibus_warnings"]],
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 10: one or several numerical predictors, independent observations.
    regression_screen = ft.Column(
        controls=[
            heading(
                "Linear regression",
                "Simple and multiple OLS with transparent coefficients and residual checks.",
            ),
            panel("Study variables and design", [
                localized_text(
                    "One quantitative outcome and 1–5 quantitative predictors. "
                    "Numeric category codes are not automatically converted to dummies.",
                    color="#607087",
                ),
                c["reg_outcome"],
                localized_text("Predictors", weight="bold"),
                c["reg_predictors"],
                c["reg_hc3"],
                c["reg_confirm"],
                ft.Button("Fit linear model", on_click=a["run_regression"]),
            ]),
            panel("Main model result", [
                c["reg_main"],
                c["reg_brief"],
            ]),
            panel("Model diagnostics", [
                c["reg_chart"],
            ]),
            panel("Coefficients and APA-style report", [
                ft.ExpansionTile(
                    title="Show detailed regression report",
                    expanded=False,
                    controls=[c["reg_report"]],
                ),
            ]),
            panel("Assumptions and cautions", [
                ft.ExpansionTile(
                    title="Review regression limitations",
                    expanded=False,
                    controls=[c["reg_warnings"]],
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 11: three or more observations from the SAME participants.
    repeated_screen = ft.Column(
        controls=[
            heading(
                "Repeated measurements",
                "Friedman for ordinal responses or repeated-measures ANOVA for quantitative scores.",
            ),
            panel("Study design and occasions", [
                localized_text(
                    "Wide format: one row per participant, one selected column "
                    "per occasion. Select 3–8 columns in the intended time order.",
                    color="#607087",
                ),
                localized_text("Repeated measurement columns", weight="bold"),
                c["rep_items"],
                ft.Row(
                    controls=[c["rep_scale"], c["rep_method"]],
                    wrap=True, spacing=12,
                ),
                c["rep_same_people"],
                c["rep_assumptions"],
                ft.Button(
                    "Analyze repeated scores", on_click=a["run_repeated"]
                ),
            ]),
            panel("Main result and interpretation", [
                c["rep_main"], c["rep_brief"],
            ]),
            panel("Individual trajectories", [
                c["rep_chart"],
            ]),
            panel("Holm-adjusted pairwise comparisons", [
                c["rep_pair_table"],
            ]),
            panel("APA 7-style report", [
                ft.ExpansionTile(
                    title="Show full repeated-measures report",
                    expanded=False,
                    controls=[c["rep_report"]],
                ),
            ]),
            panel("Assumptions and cautions", [
                ft.ExpansionTile(
                    title="View repeated-measures limitations",
                    expanded=False,
                    controls=[c["rep_warnings"]],
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 12: each row is independent; the binary event is coded 0 or 1.
    logistic_screen = ft.Column(
        controls=[
            heading(
                "Binary logistic regression",
                "Estimate a 0/1 outcome using quantitative predictors.",
            ),
            panel("Outcome, predictors and design", [
                localized_text(
                    "Outcome must be explicitly coded 0 = no event, "
                    "1 = event. Select 1–5 meaningful quantitative predictors; "
                    "numeric category codes require separate recoding.",
                    color="#607087",
                ),
                c["log_outcome"],
                localized_text("Quantitative predictors", weight="bold"),
                c["log_predictors"],
                c["log_confirm"],
                ft.Button(
                    "Fit logistic model", on_click=a["run_logistic"]
                ),
            ]),
            panel("Main result and interpretation", [
                c["log_main"],
                c["log_brief"],
            ]),
            panel("Odds ratios and 95% confidence intervals", [
                c["log_odds_table"],
            ]),
            panel("ROC, predicted probabilities and calibration", [
                c["log_chart"],
            ]),
            panel("Complete APA-style report", [
                ft.ExpansionTile(
                    title="Show logistic regression report",
                    expanded=False,
                    controls=[c["log_report"]],
                ),
            ]),
            panel("Assumptions and cautions", [
                ft.ExpansionTile(
                    title="Review interpretation and model limitations",
                    expanded=False,
                    controls=[c["log_warnings"]],
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    # Screen 13: Gaussian general linear model for adjusted group comparisons.
    ancova_screen = ft.Column(
        controls=[
            heading(
                "ANCOVA / General Linear Model",
                "Compare independent groups after accounting for quantitative covariates.",
            ),
            panel("Study design and model", [
                localized_text(
                    "Choose one quantitative outcome, one categorical group factor "
                    "(2–6 levels) and 1–3 quantitative covariates. ANCOVA assumes "
                    "parallel regression slopes; interaction GLM allows different slopes.",
                    color="#607087",
                ),
                ft.Row(
                    controls=[c["ac_outcome"], c["ac_group"]],
                    wrap=True, spacing=12,
                ),
                localized_text("Quantitative covariates", weight="bold"),
                c["ac_covariates"],
                c["ac_mode"],
                c["ac_confirm"],
                ft.Button(
                    "Run ANCOVA / GLM", on_click=a["run_ancova"]
                ),
            ]),
            panel("Main result and interpretation", [
                c["ac_main"], c["ac_brief"],
            ]),
            panel("Group fits and adjusted means", [
                c["ac_chart"],
            ]),
            panel("Adjusted group means at covariate reference", [
                c["ac_means_table"],
            ]),
            panel("Holm-adjusted group comparisons", [
                c["ac_pairs_table"],
            ]),
            panel("Complete APA-style report", [
                ft.ExpansionTile(
                    title="Show detailed ANCOVA / GLM report",
                    expanded=False,
                    controls=[c["ac_report"]],
                ),
            ]),
            panel("Assumptions and cautions", [
                ft.ExpansionTile(
                    title="Review methodological limitations",
                    expanded=False,
                    controls=[c["ac_warnings"]],
                ),
            ]),
        ],
        spacing=18,
        visible=False,
    )

    screens = {
        "home": home_screen,
        "dataset": dataset_screen,
        "preparation": preparation_screen,
        "survey": survey_screen,
        "descriptive": descriptive_screen,
        "reliability": reliability_screen,
        "factor": factor_screen,
        "correlation": correlation_screen,
        "matrix": matrix_screen,
        "groups": groups_screen,
        "paired": paired_screen,
        "chi": chi_screen,
        "omnibus": omnibus_screen,
        "regression": regression_screen,
        "logistic": logistic_screen,
        "ancova": ancova_screen,
        "repeated": repeated_screen,
    }
    labels = {
        "home": "Home",
        "dataset": "Dataset",
        "preparation": "Data preparation",
        "survey": "Questionnaires",
        "descriptive": "Descriptive",
        "reliability": "Scale reliability",
        "factor": "EFA / PCA",
        "correlation": "Correlations",
        "matrix": "Correlation matrix",
        "groups": "Compare groups",
        "paired": "Paired measures",
        "chi": "Chi-square",
        "omnibus": "ANOVA / Kruskal",
        "regression": "Linear regression",
        "logistic": "Logistic regression",
        "ancova": "ANCOVA / GLM",
        "repeated": "Repeated measures",
    }

    guide_widgets = {}
    def refresh_statistical_guides():
        ui_labels = GUIDE_LABELS[language]
        for section, entry in guide_widgets.items():
            entry.title = ft.Text(
                ui_labels["title"], weight="bold", size=14,
                color="#2755A1",
            )
            content = [
                ft.Text(ui_labels["caution"], size=12, color="#5D6F84"),
            ]
            for data in method_guide_items(section, language):
                content.append(
                    ft.Container(
                        padding=12, border_radius=10, bgcolor="#F5F8FD",
                        content=ft.Column(
                            controls=[
                                ft.Text(data["symbol"], size=14,
                                        weight="bold", color="#172A43"),
                                ft.Text(data["explanation"], size=12),
                                ft.Text(
                                    data["reference"] + "\n" + data["url"],
                                    size=11, selectable=True, color="#526987",
                                ),
                            ],
                            spacing=5,
                        ),
                    )
                )
            entry.controls = content

    for name, screen in screens.items():
        guide = ft.ExpansionTile(
            title=ft.Text("Understanding the statistics · Sources"),
            controls=[], expanded=False,
        )
        guide_widgets[name] = guide
        screen.controls.append(guide)
    refresh_statistical_guides()

    # One visible workspace avoids a several-screen-long vertical application.
    buttons = {}

    def switch_screen(key):
        a["set_active_screen"](key)
        # The survey has its own draft/response workflow; the global statistical
        # copy/save bar and an unrelated loaded-dataset banner are distracting.
        dataset_header.visible = key not in {"home", "survey"}
        c["output_toolbar"].visible = key not in {
            "home", "dataset", "preparation", "survey",
        }
        compact_navigation.value = key
        for name, screen in screens.items():
            screen.visible = name == key
            buttons[name].content.value = (
                f"●  {tr(language, labels[name])}" if name == key
                else f"    {tr(language, labels[name])}"
            )
            buttons[name].style = square_button_style(active=name == key)
        page.update()

    if a.get("register_import_navigation"):
        a["register_import_navigation"](switch_screen)

    for key, label in labels.items():
        buttons[key] = ft.Button(
            content=localized_text(
                f"●  {tr(language, label)}" if key == "home"
                else f"    {tr(language, label)}"
            ),
            on_click=lambda e, section=key: switch_screen(section),
            width=250, height=44,
            style=square_button_style(active=key == "home"),
        )

    def nav_group(title, keys, *, expanded=False):
        tile = ft.ExpansionTile(
            title=localized_text(
                title, weight="bold", size=12, color="#2755A1",
            ),
            expanded=expanded,
            min_tile_height=42,
            dense=True,
            controls_padding=ft.Padding.symmetric(horizontal=4),
            tile_padding=ft.Padding.symmetric(horizontal=10),
            shape=ft.RoundedRectangleBorder(radius=corner_radius()),
            collapsed_shape=ft.RoundedRectangleBorder(radius=corner_radius()),
            controls=[buttons[key] for key in keys],
        )
        nav_groups.append(tile)
        return tile

    def change_language(value):
        nonlocal language
        if value not in LANGUAGES:
            return
        language = value
        for widget, original in translated_controls:
            widget.value = tr(language, original)
        for key, button in buttons.items():
            label = tr(language, labels[key])
            button.content.value = (
                f"●  {label}" if screens[key].visible else f"    {label}"
            )
        compact_navigation.options = [
            ft.DropdownOption(key=key, text=tr(language, english))
            for key, english in labels.items()
        ]
        compact_navigation.label = tr(language, "Go to workspace")
        language_picker.value = value
        language_picker.label = tr(language, "Language")
        compact_language.value = value
        compact_language.label = tr(language, "Language")
        refresh_statistical_guides()
        for widget, label_key in menu_texts:
            widget.value = shell_label(language, label_key)
        appearance_picker.label = shell_label(language, "style")
        compact_appearance.label = shell_label(language, "style")
        appearance_picker.options = [
            ft.DropdownOption(key=key, text=shell_label(language, label_key))
            for key, label_key in (("windows", "windows"), ("macos", "macos"))
        ]
        compact_appearance.options = [
            ft.DropdownOption(key=key, text=shell_label(language, label_key))
            for key, label_key in (("windows", "windows"), ("macos", "macos"))
        ]
        if on_language_change is not None:
            on_language_change(value)
        page.update()

    def change_appearance(value):
        nonlocal appearance
        if value not in {"windows", "macos"}:
            return
        appearance = value
        for control in cornered:
            control.border_radius = corner_radius()
        for tile in nav_groups:
            tile.shape = ft.RoundedRectangleBorder(radius=corner_radius())
            tile.collapsed_shape = ft.RoundedRectangleBorder(radius=corner_radius())
        for key, button in buttons.items():
            button.style = square_button_style(active=screens[key].visible)
        if shell_root is not None:
            style_buttons(shell_root, appearance)
        appearance_picker.value = value
        compact_appearance.value = value
        if on_appearance_change is not None:
            on_appearance_change(value)
        page.update()

    language_picker = ft.Dropdown(
        label=tr(language, "Language"), width=252,
        value=language,
        options=[
            ft.DropdownOption(key=code, text=label)
            for code, label in LANGUAGES.items()
        ],
        on_select=lambda e: change_language(language_picker.value),
    )
    compact_language = ft.Dropdown(
        label=tr(language, "Language"), width=180, visible=False,
        value=language,
        options=[
            ft.DropdownOption(key=code, text=label)
            for code, label in LANGUAGES.items()
        ],
        on_select=lambda e: change_language(compact_language.value),
    )

    appearance_picker = ft.Dropdown(
        label=shell_label(language, "style"), width=252, value=appearance,
        options=[
            ft.DropdownOption(key=key, text=shell_label(language, key))
            for key in ("windows", "macos")
        ],
        on_select=lambda e: change_appearance(appearance_picker.value),
    )
    compact_appearance = ft.Dropdown(
        label=shell_label(language, "style"), width=208, value=appearance,
        visible=False,
        options=[
            ft.DropdownOption(key=key, text=shell_label(language, key))
            for key in ("windows", "macos")
        ],
        on_select=lambda e: change_appearance(compact_appearance.value),
    )

    sidebar = ft.Container(
        width=288,
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E1E7F1"),
        border_radius=corner_radius(),
        padding=16,
        content=ft.Column(
            controls=[
                localized_text("STATISTICAL", size=12, weight="bold", color="#2755A1"),
                localized_text("Research Assistant", size=18,
                        weight="bold", color="#172A43"),
                localized_text("Research · Analysis · Reports",
                        size=11, color="#607087"),
                ft.Divider(color="#E1E7F1"),
                buttons["home"],
                language_picker,
                appearance_picker,
                nav_group(
                    "DATA & MEASUREMENT",
                    ["dataset", "preparation", "survey", "descriptive",
                     "reliability", "factor"],
                    expanded=True,
                ),
                nav_group(
                    "RELATIONSHIPS",
                    ["correlation", "matrix", "chi"],
                ),
                nav_group(
                    "GROUP COMPARISONS",
                    ["groups", "paired", "omnibus", "repeated"],
                ),
                nav_group(
                    "STATISTICAL MODELS",
                    ["regression", "logistic", "ancova"],
                ),
                ft.Divider(color="#E1E7F1"),
                localized_text(
                    "Start on Home. The advanced modules are grouped "
                    "so you can open only what you need.",
                    color="#607087", size=12,
                ),
            ],
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )

    cornered.append(sidebar)

    compact_navigation = ft.Dropdown(
        label=tr(language, "Go to workspace"),
        width=None,
        visible=False,
        value="home",
        options=[
            ft.DropdownOption(key=key, text=tr(language, label))
            for key, label in labels.items()
        ],
        on_select=lambda e: switch_screen(compact_navigation.value),
    )

    def resize_navigation(e=None):
        page_width = getattr(page, "width", None) or 1280
        compact = page_width < 1060
        sidebar.visible = not compact
        compact_navigation.visible = compact
        compact_language.visible = compact
        compact_appearance.visible = compact
        page.update()

    if hasattr(page, "on_resize"):
        page.on_resize = resize_navigation

    def command_text(key):
        label = ft.Text(shell_label(language, key), size=13)
        menu_texts.append((label, key))
        return label

    def item(key, callback):
        return ft.MenuItemButton(
            content=command_text(key), on_click=callback,
        )

    def group(label, entries):
        return ft.SubmenuButton(
            content=command_text(label),
            controls=[item(key, callback) for key, callback in entries],
        )

    menu_notice_label = ft.Text(
        "", size=12, selectable=True, color="#3C536F",
    )
    menu_notice = ft.Container(
        visible=False, bgcolor="#EBF1FA", border_radius=corner_radius(),
        padding=12, content=menu_notice_label,
    )
    cornered.append(menu_notice)

    def explain(key):
        menu_notice_label.value = shell_label(language, key)
        menu_notice.visible = True
        page.update()

    async def show_ocr_status(e=None):
        """Settings/About: bundled OCR version, languages and integrity."""
        import asyncio
        from ocr_runtime import ocr_readiness

        menu_notice_label.value = shell_label(language, "ocr_checking")
        menu_notice.visible = True
        page.update()
        ready = await asyncio.to_thread(ocr_readiness, full_hash=True, use_cache=False)
        menu_notice_label.value = shell_label(language, "ocr_note") + ready.summary()
        page.update()

    def show_data_folder(e=None):
        """Settings → Your data…: the data folder and earlier versions' data (#44)."""
        import data_ui

        data_ui.show_data_folder(page, Path(__file__).resolve().parent, language)

    def navigate_and_open(section, registered_action):
        switch_screen(section)
        if registered_action in a:
            a[registered_action]()

    def report_wizard(e):
        # The shared report bar is displayed only on analysis workspaces.
        current = next(
            (key for key, screen in screens.items()
             if screen.visible and key not in {
                 "home", "dataset", "preparation", "survey",
             }), None
        )
        if current is None:
            switch_screen("reliability")
        else:
            switch_screen(current)
        if "open_report_wizard" in a:
            a["open_report_wizard"]()
            page.update()

    menu = ft.MenuBar(
        controls=[
            group("file", [
                ("open_data", lambda e: switch_screen("dataset")),
                ("import_questionnaire", lambda e: navigate_and_open(
                    "survey", "open_survey_import",
                )),
                ("new_survey", lambda e: switch_screen("survey")),
                ("recent", lambda e: switch_screen("dataset")),
            ]),
            group("data", [
                ("recent", lambda e: switch_screen("dataset")),
                ("prepare", lambda e: switch_screen("preparation")),
            ]),
            group("analysis", [
                ("descriptive", lambda e: switch_screen("descriptive")),
                ("reliability", lambda e: switch_screen("reliability")),
                ("factor", lambda e: switch_screen("factor")),
                ("correlation", lambda e: switch_screen("correlation")),
                ("regression", lambda e: switch_screen("regression")),
            ]),
            group("reports", [
                ("word", report_wizard),
                ("method", lambda e: switch_screen("descriptive")),
            ]),
            group("database", [
                ("survey_db", lambda e: navigate_and_open(
                    "survey", "open_survey_responses",
                )),
            ]),
            group("settings", [
                ("windows", lambda e: change_appearance("windows")),
                ("macos", lambda e: change_appearance("macos")),
                ("ocr_status", show_ocr_status),
                ("data_folder", show_data_folder),
            ]),
            group("ai", [
                ("ai_status", lambda e: explain("ai_note")),
                ("method", lambda e: switch_screen("descriptive")),
            ]),
            group("help", [
                ("ai_status", lambda e: explain("ai_note")),
                ("privacy", lambda e: explain("privacy_note")),
                ("ocr_status", show_ocr_status),
            ]),
        ],
    )
    menu_frame = ft.Container(
        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E1E7F1"),
        border_radius=corner_radius(),
        content=ft.Row(
            controls=[menu],
            scroll=ft.ScrollMode.AUTO,
        ),
    )
    cornered.append(menu_frame)

    # Keep export controls visible while long results scroll independently.
    dataset_header = ft.Container(
        visible=False,
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E1E7F1"),
        border_radius=corner_radius(),
        padding=12,
        content=ft.Row(
            controls=[
                localized_text("CURRENT DATASET", weight="bold", size=12),
                c["status"],
            ],
            wrap=True,
            spacing=16,
        ),
    )
    cornered.append(dataset_header)
    c["output_toolbar"].visible = False
    workspace = ft.Column(
        controls=[
            menu_frame,
            menu_notice,
            compact_navigation,
            compact_language,
            compact_appearance,
            dataset_header,
            c["output_toolbar"],
            ft.Column(
                controls=list(screens.values()),
                spacing=18,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        ],
        spacing=12,
        expand=True,
    )

    shell_root = ft.Row(
        controls=[
            sidebar,
            ft.Container(content=workspace, expand=True, padding=8),
        ],
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        spacing=14,
        expand=True,
    )
    style_buttons(shell_root, appearance)
    resize_navigation()
    return shell_root
