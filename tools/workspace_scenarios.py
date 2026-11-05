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
import asyncio
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
    "questionnaires", "import", "help", "settings",
)


async def apply(app, name: str) -> None:
    """Drive ``app`` (a WorkspaceApp) into the named state."""
    s = app.session
    if name in {"home", "help", "settings"}:
        app.navigate(name)
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
        page.confirms = {"independent": True}
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
            page.confirms = {"construct": True}
            await page._run_guided()
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
    if name == "questionnaires":
        builder = app.pages["questionnaires"]
        builder.template = "psychology"
        builder._load_template()
        builder.title = "Fictional wellbeing pilot"
        builder.selected = 1
        app.navigate("questionnaires")
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
    raise ValueError(f"Unknown scenario: {name}")


def serve(scenario: str, port: int, language: str, theme: str) -> None:
    import flet as ft

    from workspace_shell import ClassicBridge, WorkspaceApp

    storage = Path(mkdtemp(prefix="workspace-scenario-"))

    async def main(page: ft.Page):
        page.title = "Statistical Research Assistant — workspace preview"
        page.padding = 0
        app = WorkspaceApp(page, bridge=ClassicBridge(survey_root=storage / "surveys"),
                           language=language)
        app.session.theme = theme
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
