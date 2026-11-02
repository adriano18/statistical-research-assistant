"""Flet interface layout for the Statistical Research Assistant.

The interface is divided into five screens. Calculation logic stays in app.py;
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

    screens = {
        "dataset": dataset_screen,
        "descriptive": descriptive_screen,
        "reliability": reliability_screen,
        "correlation": correlation_screen,
        "matrix": matrix_screen,
    }
    labels = {
        "dataset": "Dataset",
        "descriptive": "Descriptive",
        "reliability": "Scale reliability",
        "correlation": "Correlations",
        "matrix": "Correlation matrix",
    }

    # One visible workspace avoids a several-screen-long vertical application.
    buttons = {}

    def switch_screen(key):
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
