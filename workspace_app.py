"""Standalone launcher for the Stage 33 research workspace preview.

    python workspace_app.py            # desktop window
    flet run --web workspace_app.py    # local browser preview (screenshots)

The packaged application opens the same workspace from the classic Home
screen ("Try the new workspace") or with ``SRA_UI=workspace``; this file is
a developer and review convenience. Data stays on this computer.
"""

from __future__ import annotations

import os
from pathlib import Path

import flet as ft

from startup_diagnostics import survey_data_root
from workspace_shell import ClassicBridge, WorkspaceApp

ROOT = Path(__file__).resolve().parent


def build(page: ft.Page, *, language: str | None = None, theme: str | None = None,
          route: str | None = None) -> WorkspaceApp:
    from app_preferences import load_preferences

    preferences = load_preferences()
    page.title = "Statistical Research Assistant — workspace preview"
    page.padding = 0
    app = WorkspaceApp(
        page, bridge=ClassicBridge(survey_root=survey_data_root(ROOT)),
        language=language or os.environ.get("SRA_LANGUAGE") or preferences.language,
        corners=preferences.appearance,
    )
    if theme or os.environ.get("SRA_THEME"):
        app.session.theme = theme or os.environ["SRA_THEME"]
    app.mount()
    if route or os.environ.get("SRA_ROUTE"):
        app.navigate(route or os.environ["SRA_ROUTE"])
    return app


async def main(page: ft.Page):
    build(page)


if __name__ == "__main__":
    ft.run(main)
