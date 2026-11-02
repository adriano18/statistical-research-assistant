"""Flet interface layout for the Statistical Research Assistant.

The interface is divided into nine screens. Calculation logic stays in app.py;
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

    # Screen 9: omnibus comparisons of three or more independent groups.
    omnibus_screen = ft.Column(
        controls=[
            heading(
                "ANOVA & Kruskal–Wallis",
                "Compare 3–8 independent groups and review assumptions.",
            ),
            panel("Choose groups, outcome and method", [
                ft.Text(
                    "Omnibus tests only. They cannot tell which specific groups "
                    "differ without post-hoc testing.",
                    color="#A8B6C9",
                ),
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
            panel("A. Main result and interpretation", [
                c["omnibus_main"],
                c["omnibus_brief"],
            ]),
            panel("B. Group descriptives and APA report", [
                c["omnibus_output"],
                ft.Row(
                    controls=[
                        c["omnibus_export_png_button"],
                        c["omnibus_export_txt_button"],
                    ],
                    wrap=True, spacing=12,
                ),
                c["omnibus_export_status"],
            ]),
            panel("C. Notes and assumptions", [
                c["omnibus_warnings"],
            ]),
            panel("D. Post-hoc pairwise comparisons", [
                ft.Text(
                    "Run the omnibus test first, then compare individual pairs "
                    "with familywise error control. Tukey follows ordinary ANOVA, "
                    "Games–Howell follows Welch and Dunn–Holm follows Kruskal–Wallis.",
                    color="#A8B6C9",
                ),
                c["posthoc_button"],
                c["posthoc_output"],
                c["posthoc_warnings"],
                ft.Text(
                    "Save APA report TXT above to export the pairwise results "
                    "after this step.",
                    color="#A8B6C9", size=12,
                ),
            ]),
            panel("Group distributions", [
                c["omnibus_chart"],
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
                *buttons.values(),
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

    workspace = ft.Column(
        controls=[
            ft.Container(
                bgcolor="#152030",
                border_radius=12,
                padding=15,
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
            *screens.values(),
        ],
        spacing=20,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
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
