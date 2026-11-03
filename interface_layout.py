"""Flet interface layout for the Statistical Research Assistant.

The interface is divided into twelve screens. Calculation logic stays in app.py;
existing controls are reused, so switching screens preserves user selections.
"""

import flet as ft


def build_interface(page: ft.Page, controls: dict, actions: dict):
    """Create a sidebar and one visible workspace at a time."""
    c = controls
    a = actions

    def heading(title, subtitle):
        return ft.Column(
            controls=[
                ft.Text(title, size=26, weight="bold"),
                ft.Text(subtitle, color="#A8B6C9", size=13),
            ],
            spacing=5,
        )

    def panel(title, content):
        return ft.Container(
            bgcolor="#1A2635",
            border_radius=14,
            padding=20,
            content=ft.Column(
                controls=[
                    ft.Text(title, size=17, weight="bold"),
                    *content,
                ],
                spacing=13,
            ),
        )

    # Screen 1: upload and inspect the current local dataset.
    dataset_screen = ft.Column(
        controls=[
            heading(
                "Dataset",
                "Import research data and inspect its variables before analysis.",
            ),
            panel("Choose a data source", [
                ft.Row(
                    controls=[
                        ft.Button("Open CSV / Excel", on_click=a["choose_file"]),
                        ft.Button("Load survey example", on_click=a["load_sample"]),
                        ft.Button("Load scale example", on_click=a["load_scale_example"]),
                        ft.Button("Load paired example", on_click=a["load_paired_example"]),
                        ft.Button("Load categorical example", on_click=a["load_categorical_example"]),
                        ft.Button("Load three-group example", on_click=a["load_three_groups_example"]),
                        ft.Button("Load regression example", on_click=a["load_regression_example"]),
                        ft.Button("Load logistic example", on_click=a["load_logistic_example"]),
                        ft.Button("Load repeated example", on_click=a["load_repeated_example"]),
                    ],
                    wrap=True,
                    spacing=10,
                ),
                ft.Text(
                    "Files are processed locally. Real participant records should "
                    "not be committed to a public repository.",
                    color="#A8B6C9",
                    size=12,
                ),
            ]),
            panel("Variable overview", [
                ft.Text(
                    "Check missing values and types. Numeric storage does not "
                    "prove that a measurement is continuous.",
                    color="#A8B6C9",
                ),
                c["overview_area"],
            ]),
        ],
        spacing=18,
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
                ft.Text(
                    "Choose a quantitative outcome and optional grouping variable. "
                    "The figure includes a boxplot and normal Q–Q plot.",
                    color="#A8B6C9",
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
                ft.Text(
                    "Select at least three items from one scale. Check any "
                    "reverse-scored items before running the analysis.",
                    color="#A8B6C9",
                ),
                c["reliability_items"],
                c["reliability_confirm"],
                ft.Button(
                    "Calculate Cronbach’s α",
                    on_click=a["calculate_alpha"],
                ),
            ]),
            panel("APA 7-style result", [
                c["reliability_output"],
                c["reliability_guide"],
                c["reliability_warnings"],
            ]),
            panel("Reliability figure", [
                c["reliability_chart_area"],
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
                ft.Text(
                    "This module does not support paired or repeated-measure data. "
                    "The group variable must have exactly two observed categories.",
                    color="#A8B6C9",
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
                ft.Text(
                    "Each spreadsheet row must represent one participant, "
                    "with both values aligned. Independent groups are not paired.",
                    color="#A8B6C9",
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
                ft.Text(
                    "Choose two nominal or ordinal variables (including coded "
                    "categories). This is a test of independence, not of means.",
                    color="#A8B6C9",
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
                ft.Text(
                    "One quantitative outcome and 1–5 quantitative predictors. "
                    "Numeric category codes are not automatically converted to dummies.",
                    color="#A8B6C9",
                ),
                c["reg_outcome"],
                ft.Text("Predictors", weight="bold"),
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
                ft.Text(
                    "Wide format: one row per participant, one selected column "
                    "per occasion. Select 3–8 columns in the intended time order.",
                    color="#A8B6C9",
                ),
                ft.Text("Repeated measurement columns", weight="bold"),
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
                ft.Text(
                    "Outcome must be explicitly coded 0 = no event, "
                    "1 = event. Select 1–5 meaningful quantitative predictors; "
                    "numeric category codes require separate recoding.",
                    color="#A8B6C9",
                ),
                c["log_outcome"],
                ft.Text("Quantitative predictors", weight="bold"),
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

    screens = {
        "dataset": dataset_screen,
        "descriptive": descriptive_screen,
        "reliability": reliability_screen,
        "correlation": correlation_screen,
        "matrix": matrix_screen,
        "groups": groups_screen,
        "paired": paired_screen,
        "chi": chi_screen,
        "omnibus": omnibus_screen,
        "regression": regression_screen,
        "logistic": logistic_screen,
        "repeated": repeated_screen,
    }
    labels = {
        "dataset": "Dataset",
        "descriptive": "Descriptive",
        "reliability": "Scale reliability",
        "correlation": "Correlations",
        "matrix": "Correlation matrix",
        "groups": "Compare groups",
        "paired": "Paired measures",
        "chi": "Chi-square",
        "omnibus": "ANOVA / Kruskal",
        "regression": "Linear regression",
        "logistic": "Logistic regression",
        "repeated": "Repeated measures",
    }

    # One visible workspace avoids a several-screen-long vertical application.
    buttons = {}

    def switch_screen(key):
        a["set_active_screen"](key)
        for name, screen in screens.items():
            screen.visible = name == key
            buttons[name].content.value = (
                f"●  {labels[name]}" if name == key else f"    {labels[name]}"
            )
        page.update()

    for key, label in labels.items():
        buttons[key] = ft.Button(
            content=ft.Text(f"●  {label}" if key == "dataset" else f"    {label}"),
            on_click=lambda e, section=key: switch_screen(section),
            width=210,
        )

    sidebar = ft.Container(
        width=240,
        bgcolor="#152030",
        border_radius=16,
        padding=16,
        content=ft.Column(
            controls=[
                ft.Text("RESEARCH", size=13, weight="bold", color="#9CB7DA"),
                ft.Text("ANALYZER", size=21, weight="bold"),
                ft.Text(
                    "Statistics workspace",
                    size=11,
                    color="#A8B6C9",
                ),
                ft.Divider(),
                ft.Text("DATA & MEASUREMENT", size=10, color="#9CB7DA"),
                buttons["dataset"],
                buttons["descriptive"],
                buttons["reliability"],
                ft.Text("ASSOCIATIONS", size=10, color="#9CB7DA"),
                buttons["correlation"],
                buttons["matrix"],
                buttons["chi"],
                ft.Text("GROUP COMPARISONS", size=10, color="#9CB7DA"),
                buttons["groups"],
                buttons["paired"],
                buttons["omnibus"],
                buttons["repeated"],
                ft.Text("MODELING", size=10, color="#9CB7DA"),
                buttons["regression"],
                buttons["logistic"],
                ft.Divider(),
                ft.Text(
                    "Tip: load data in Dataset, then choose any analysis "
                    "from this menu.",
                    color="#A8B6C9",
                    size=12,
                ),
            ],
            spacing=10,
        ),
    )

    # Keep export controls visible while long results scroll independently.
    workspace = ft.Column(
        controls=[
            ft.Container(
                bgcolor="#152030",
                border_radius=12,
                padding=12,
                content=ft.Row(
                    controls=[
                        ft.Text("CURRENT DATASET", weight="bold", size=12),
                        c["status"],
                    ],
                    wrap=True,
                    spacing=16,
                ),
            ),
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

    return ft.Row(
        controls=[
            sidebar,
            ft.Container(content=workspace, expand=True, padding=4),
        ],
        vertical_alignment=ft.CrossAxisAlignment.START,
        spacing=20,
        expand=True,
    )
