"""Standalone launcher for the research workspace (without the classic interface).

    python workspace_app.py            # desktop window
    flet run --web workspace_app.py    # local browser preview (screenshots)

The packaged application starts in the same workspace (Stage 37, issue
#68: the normal start; the classic interface stays one click away); this
file is a developer and review convenience. Data stays on this computer.
``SRA_LANGUAGE``, ``SRA_THEME`` and ``SRA_ROUTE`` override the settings for
one run (screenshots) without saving them.
"""

from __future__ import annotations

import os
from pathlib import Path

import flet as ft

from project_store import project_data_root
from startup_diagnostics import survey_data_root
from workspace_shell import ClassicBridge, WorkspaceApp

ROOT = Path(__file__).resolve().parent


def build(page: ft.Page, *, language: str | None = None, theme: str | None = None,
          route: str | None = None) -> WorkspaceApp:
    page.title = "Statistical Research Assistant — workspace"
    page.padding = 0
    app = WorkspaceApp(
        page, bridge=ClassicBridge(survey_root=survey_data_root(ROOT),
                                   project_root=project_data_root(ROOT)),
    )
    language = language or os.environ.get("SRA_LANGUAGE")
    if language in ("en", "lv", "ru"):
        app.session.language = language          # this run only, not saved
    theme = theme or os.environ.get("SRA_THEME")
    if theme in ("light", "dark", "system"):
        app.theme_choice = theme
    app.mount()
    if route or os.environ.get("SRA_ROUTE"):
        app.navigate(route or os.environ["SRA_ROUTE"])
    return app


async def main(page: ft.Page):
    build(page)


if __name__ == "__main__":
    ft.run(main)
