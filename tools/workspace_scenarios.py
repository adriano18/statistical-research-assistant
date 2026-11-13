"""Reproducible Stage 33 workspace states for screenshots and reviews.

    python tools/workspace_scenarios.py --scenario results --port 8601

serves the workspace in a local browser (Flet web) after preparing a named
state with fictional data only. ``tools/capture_workspace.js`` drives the
page with Playwright and saves PNG screenshots. The same scenario code is
used by ``tests/test_workspace_shell.py`` so screenshots and tests cannot
drift apart.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("MPLBACKEND", "Agg")

SCENARIOS = (
    "home", "data", "guided", "results", "catalog", "form", "reports",
    "questionnaires", "phone-preview", "import", "help", "settings",
    "projects", "results-stale", "settings-profile", "import-zoom", "questionnaire-120",
    "project", "import-psq", "import-120", "classic-home", "classic-groups",
)


def long_questionnaire(count: int = 120) -> list[dict]:
    """A fictional questionnaire with ``count`` five-point items."""
    return [{"key": f"item_{n:03d}", "kind": "likert5", "required": False,
             "prompt": f"Fictional statement {n}. I feel rested among fictional neighbours."}
            for n in range(1, count + 1)]


async def projects(app) -> None:
    """Three fictional projects (one archived) and an open one with a result
    that needs review after a measurement level changed."""
    s, store = app.session, app.projects.store
    for title in ("Exam anxiety pilot (fictional)", "Peer support evaluation (fictional)"):
        store.create(title)
    archived = store.create("Pilot 2025 (fictional)")
    store.set_archived(archived.id, True)
    app.projects.create("Sleep and stress (fictional)")
    await app.load_sample("sample_scale.csv")
    page = app.pages["analyze"]
    page.mode = "guided"
    page._set_goal("compare")
    page.selection = {"outcome": "stress_q1", "group": "group"}
    s.confirm_level("stress_q1", "ordinal", "analyze")
    s.confirm_level("group", "nominal", "analyze")
    # Ticked through the handler, which records what it is given for (36.8).
    page._confirm("independent", True)
    await page._run_guided()
    s.toggle_report(s.results[-1].id)
    s.confirm_level("stress_q1", "scale", "data")      # the result now needs review
    app.status("")


async def project_page(app) -> None:
    """The open project's page: a data file with a result in the report, and a
    published questionnaire whose responses are their own dataset."""
    from survey_storage import create_survey, responses_dataframe, submit_response

    s = app.session
    app.projects.create("Sleep and stress (fictional)")
    await app.load_sample("sample_scale.csv")
    page = app.pages["analyze"]
    page.mode = "guided"
    page._set_goal("compare")
    page.selection = {"outcome": "stress_q1", "group": "group"}
    s.confirm_level("stress_q1", "ordinal", "analyze")
    s.confirm_level("group", "nominal", "analyze")
    page._confirm("independent", True)
    await page._run_guided()
    s.toggle_report(s.results[-1].id)
    survey = create_survey(app.survey_root, "Fictional wellbeing check", "Fictional items", [
        {"key": "group", "kind": "single_choice", "prompt": "Fictional group", "required": True,
         "options": ["A", "B"]},
        {"key": "rested", "kind": "likert5", "prompt": "I wake up rested (fictional).",
         "required": True, "options": []},
    ])
    for group, value in (("A", "2"), ("A", "3"), ("B", "4"), ("B", "5"), ("B", "4")):
        submit_response(app.survey_root, survey.survey_id, {"group": group, "rested": value})
    app.projects.link_questionnaire(survey.survey_id, survey.title, "published")
    app.pages["questionnaires"]._use_responses(
        survey, responses_dataframe(app.survey_root, survey.survey_id),
        app.t("responses.name", title=survey.title))
    app.projects.activate_dataset(app.projects.project.datasets()[0].id)
    app.status("")
    app.navigate("project")


async def apply(app, name: str) -> None:
    """Drive ``app`` (a WorkspaceApp) into the named state."""
    s = app.session
    if name in {"home", "help", "settings"}:
        app.navigate(name)
        return
    if name == "project":
        await project_page(app)
        return
    if name in {"projects", "results-stale"}:
        await projects(app)
        app.pages["home"].hide_onboarding = True
        app.navigate("home" if name == "projects" else "results")
        return
    if name == "settings-profile":
        from researcher_profile import ResearcherProfile

        await projects(app)
        app.pages["settings"].profile.draft = ResearcherProfile(
            display_name="Fictional researcher", study_level="master",
            research_field="Educational psychology", experience="some",
            explanations="standard")
        app.navigate("settings")
        return
    if name in {"data", "guided", "results", "catalog", "form", "reports"}:
        await app.load_sample("sample_scale.csv")
    if name == "data":
        s.confirm_level("group", "nominal")
        app.navigate("data")
        return
    page = app.pages["analyze"]
    if name in {"guided", "results", "reports"}:
        page.mode = "guided"
        page._set_goal("compare")
        page.selection = {"outcome": "stress_q1", "group": "group"}
        s.confirm_level("stress_q1", "ordinal", "analyze")
        s.confirm_level("group", "nominal", "analyze")
        page._confirm("independent", True)
        app.navigate("analyze")
        if name == "guided":
            return
        await page._run_guided()
        if name == "reports":
            s.toggle_report(s.results[-1].id)
            page._set_goal("scale")
            page.selection = {"items": ["stress_q1", "stress_q2", "stress_q3", "stress_q4"]}
            for item in page.selection["items"]:
                s.confirm_level(item, "ordinal", "analyze")
            # Confirm what the current recommendation asks for (Stage 36.3:
            # item diagnostics ask "one_construct"); a blocked run must not
            # pass silently, or the report would lose its first result.
            from workspace_methods import advise

            for key in advise("scale", page.selection, s).design_checks:
                page._confirm(key, True)
            before = len(s.results)
            await page._run_guided()
            if len(s.results) != before + 1:
                raise RuntimeError("the reports scenario's scale analysis did not run")
            s.toggle_report(s.results[-1].id)
            app.navigate("reports")
        return
    if name == "catalog":
        page.mode = "all"
        app.navigate("analyze")
        return
    if name == "form":
        page.mode = "all"
        page._open_method("omnibus")
        app.navigate("analyze")
        return
    if name in {"questionnaires", "phone-preview"}:
        builder = app.pages["questionnaires"]
        builder.preview_width = "phone" if name == "phone-preview" else "desktop"
        builder.template = "psychology"
        builder._load_template()
        builder.title = "Fictional wellbeing pilot"
        builder.selected = 1
        app.navigate("questionnaires")
        return
    if name == "questionnaire-120":
        builder = app.pages["questionnaires"]
        builder.load_draft(long_questionnaire(120), title="Fictional 120-item inventory")
        builder.selected = None
        app.navigate("questionnaires")
        return
    if name == "import-zoom":
        from synthetic_documents import connectedness_text_pdf

        page = app.pages["import"]
        app.navigate("import")
        await page.open_bytes(connectedness_text_pdf(), "synthetic_two_versions.pdf")
        page.zoom = "150"
        page.enlarge_page()
        return
    if name == "import":
        from synthetic_documents import connectedness_text_pdf

        page = app.pages["import"]
        app.navigate("import")
        await page.open_bytes(connectedness_text_pdf(), "synthetic_two_versions.pdf")
        if len(page.session.instruments) > 1:
            page._instrument(1)
        page._select(0)
        return
    if name == "import-psq":
        from synthetic_documents import psq_like_pdf

        page = app.pages["import"]
        app.navigate("import")
        await page.open_bytes(psq_like_pdf(), "synthetic_strain_questionnaire.pdf")
        page.opened.add("imp-excluded")
        app.render()
        return
    if name == "import-120":
        from synthetic_documents import numbered_items_pdf

        page = app.pages["import"]
        app.navigate("import")
        await page.open_bytes(numbered_items_pdf(120), "synthetic_120_items.pdf")
        page._go("items")
        return
    raise ValueError(f"Unknown scenario: {name}")


async def classic(page, name: str) -> None:
    """The unchanged classic interface, for before/after comparisons."""
    import research_app

    captured = {}
    original = research_app.build_interface

    def spy(page_, controls, actions, **kwargs):
        captured.update(controls=controls, actions=actions)
        return original(page_, controls, actions, **kwargs)

    research_app.build_interface = spy
    try:
        await research_app.main(page, interface="classic")
    finally:
        research_app.build_interface = original
    if name == "classic-groups":
        controls, actions = captured["controls"], captured["actions"]
        await actions["load_scale_example"](None)
        controls["group_variable"].value = "group"
        controls["group_outcome"].value = "stress_q1"
        controls["group_outcome_scale"].value = "ordinal"
        controls["group_method"].value = "mannwhitney"
        controls["group_independent"].value = True
        await actions["calculate_groups"](None)
        # The classic switcher is registered through the import navigation.
        for control in page.controls[0].controls[0].content.controls:
            for button in getattr(control, "controls", []) or []:
                text = getattr(getattr(button, "content", None), "value", "") or ""
                if "Compare groups" in str(text):
                    button.on_click(None)
        page.update()


def serve(scenario: str, port: int, language: str, theme: str) -> None:
    import flet as ft

    from workspace_shell import ClassicBridge, WorkspaceApp

    storage = Path(mkdtemp(prefix="workspace-scenario-"))

    async def main(page: ft.Page):
        if scenario.startswith("classic"):
            await classic(page, scenario)
            return
        from user_settings import UserSettings, path_for

        page.title = "Statistical Research Assistant — workspace"
        page.padding = 0
        # A settings file of its own, never made from this computer's files
        # (the scenario's language and theme are what the screenshot shows).
        app = WorkspaceApp(page, bridge=ClassicBridge(survey_root=storage / "surveys"),
                           language=language,
                           settings=UserSettings.load(path_for(storage), migrate=False))
        app.theme_choice = theme
        app.mount()
        await apply(app, scenario)

    ft.run(main, view=ft.AppView.WEB_BROWSER, port=port)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="home", choices=SCENARIOS)
    parser.add_argument("--port", type=int, default=8601)
    parser.add_argument("--language", default="en", choices=("en", "lv", "ru"))
    parser.add_argument("--theme", default="light", choices=("light", "dark"))
    args = parser.parse_args(argv)
    serve(args.scenario, args.port, args.language, args.theme)
    return 0


if __name__ == "__main__":
    sys.exit(main())
