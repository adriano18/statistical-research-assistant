"""Stage 37 Phase D: the measured interaction cost of the two persona flows today.

A measurement aid for docs/STAGE37_DESIGN.md, not part of the application or of
the test suite. It drives the real workspace controls through the Stage 36
``CountingWorkspace`` (tests/test_stage36_ux_baseline.py): a click or a
checkbox counts 1, a dropdown 2. Three things are counted on top, apart from
the Stage 36 number so that it stays comparable:

* typed fields: each text field the researcher types into, once;
* page changes: every change of route, also one a handler makes (loading a
  file opens Data);
* system dialogs: the Windows Open and Save dialogs.

Synthetic fixtures only (tests/fixtures/stage36). Projects are created in a
temporary folder; nothing in the repository or the user's data changes.

Run from the repository root:  python docs/stage37/measure_baseline.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def _commit() -> str:
    """The checkout measured (its short commit), for the printed tables."""
    import subprocess

    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip() or "this checkout"
    except (OSError, subprocess.CalledProcessError):
        return "this checkout"


COMMIT = _commit()

import stage36_fixtures as fx  # noqa: E402
from test_stage36_ux_baseline import LEVELS, CountingWorkspace, eight_correlations  # noqa: E402


class Measured(CountingWorkspace):
    """CountingWorkspace plus typed fields, expansion tiles, segments and page changes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.typed = 0
        self.pages: list[str] = []
        self.dialogs = 0
        self.log: list[tuple[str, int, int, int]] = []
        self._route = self.app.route
        self._mark = (0, 0, 0)

    def _seen(self):
        if self.app.route != self._route:
            self.pages.append(self.app.route)
            self._route = self.app.route

    def click(self, data):
        result = super().click(data)
        self._seen()
        return result

    def choose(self, data, value):
        result = super().choose(data, value)
        self._seen()
        return result

    def check(self, data, value=True):
        result = super().check(data, value)
        self._seen()
        return result

    def type(self, data, value):
        self.typed += 1
        result = super().type(data, value)
        self._seen()
        return result

    def expand(self, data):
        """Open an expansion tile: one click on its header."""
        self.counts["click"] += 1
        tile = self.find(data)
        self.dispatch(tile.on_change, SimpleNamespace(control=tile, data="true"))
        self.app.render()

    def segment(self, data, key):
        self.counts["click"] += 1
        return super().segment(data, key)

    def button_with_system_dialog(self):
        """A button whose action is the system dialog (Open CSV / Excel…, Export…)."""
        self.counts["click"] += 1
        self.dialogs += 1

    def done(self, name: str):
        now = (self.total, self.typed, len(self.pages))
        self.log.append((name, now[0] - self._mark[0], now[1] - self._mark[1],
                         now[2] - self._mark[2]))
        self._mark = now

    def table(self, title: str):
        print(f"\n== {title}")
        print(f"{'segment':66} {'inter.':>6} {'typed':>6} {'pages':>6}")
        for name, inter, typed, pages in self.log:
            print(f"{name:66} {inter:6d} {typed:6d} {pages:6d}")
        print(f"{'TOTAL':66} {sum(r[1] for r in self.log):6d} {sum(r[2] for r in self.log):6d} "
              f"{sum(r[3] for r in self.log):6d}   + {self.dialogs} system dialog(s)")
        print("routes:", " → ".join(self.pages))


def beginner(folder: Path) -> dict:
    """Question → hypothesis → data → scales → analysis → interpretation → report."""
    ws = Measured(root=folder)
    ws.type("project-new-title", "Fictional loneliness and coping study")
    ws.click("project-create")
    ws.done("1 project: title, Create project")
    ws.type("project-question", "Is loneliness related to how students cope with stress?")
    ws.app.pages["project"].save_question()            # saved when the field loses focus
    ws.done("2 research question: one text field")
    ws.click("plan-add")
    ws.type("plan-h0-text", "Loneliness (UCLA) is associated with each of the eight SACS scales.")
    ws.type("plan-h0-h0", "There is no association between UCLA and the coping scales.")
    ws.type("plan-h0-outcome", "Eight SACS coping scales")
    ws.type("plan-h0-predictors", "UCLA loneliness")
    ws.type("plan-h0-method", "Spearman correlations")
    ws.type("plan-h0-family", "UCLA x 8 SACS scales, Holm")
    ws.click("plan-save")
    assert ws.app.projects.project.plan()["plan"]["hypotheses"]
    ws.done("3 hypothesis: add, six text fields (direction, priority, α default), save")
    ws.button_with_system_dialog()                      # Open CSV / Excel… and the Open dialog
    assert ws.run(ws.app.load_path(str(fx.fixture(fx.CSV))))
    ws._seen()
    ws.done("4 data: Open CSV / Excel… (+ the system Open dialog)")
    ws.check("data-accept-confirm")
    ws.click("data-accept")
    fixes = [name for name, level in LEVELS.items() if ws.app.session.level(name) != level]
    for name in fixes:
        ws.choose(f"level-{name}", LEVELS[name])
    ws.done(f"5 measurement levels: accept the suggestions, {len(fixes)} corrections")
    ws.done("6 scales: the file holds totals; α/ω are refused for totals (D5)")
    eight_correlations(ws)
    ws._seen()
    ws.done("7 analysis: eight Spearman correlations in one batch (Stage 36)")
    ws.done("8 link the analysis to H1: no control exists (hypothesis_id stays empty)")
    ws.click("task-open-result")
    ws.expand("result-interpretation-section")
    ws.type("result-notes", "No pair reaches p (Holm) < .05; the intervals are wide.")
    reviews = [c.data for c in ws.find_all("review-")]
    for data in reviews:
        ws.check(data)
    ws.done(f"9 interpretation: open the result, expand, note, {len(reviews)} review ticks")
    ws.click("result-add-report")
    ws.click("nav-reports")
    ws.type("reports-study-title", "Loneliness and coping (fictional)")
    ws.counts["click"] += 1                             # Export Word report…
    ws.dialogs += 1                                     # the system Save dialog
    ws.run(ws.app.pages["reports"]._export_docx())
    assert ws.saved and ws.saved[-1].exists()
    ws.done("10 report: add, Reports, study title, Export Word (+ the Save dialog)")
    ws.table(f"Beginner flow ({COMMIT})")
    # Setup for the professor, not counted: a second analysis and a second hypothesis.
    task = ws.app.session.tasks[0]
    ws.click("nav-analyze")
    ws.click("task-new")
    ws.click("goal-compare")
    ws.choose("role-group", "UCLA_Level")
    ws.click(f"role-outcome-from-{task.id}")
    ws.check("design-confirm-independent")
    ws.check("design-confirm-assumptions")
    ws.click("guided-run")
    project = ws.app.projects.project
    plan = project.plan()["plan"]
    plan["hypotheses"].append({"text": "Coping differs between the UCLA_Level groups.",
                               "h0": "The groups do not differ.", "direction": "two-sided",
                               "priority": "secondary", "alpha": 0.05})
    project.save_plan(plan)
    facts = {"project_id": ws.app.projects.info().id, "fixes": fixes, "reviews": len(reviews),
             "hypothesis_ids": [t.hypothesis_id for t in ws.app.session.tasks]}
    ws.close()
    return facts


def professor(folder: Path, facts: dict) -> None:
    """After a restart: methodology, measurement quality and provenance of H1, then H2."""
    ws = Measured(root=folder)
    ws.click(f"project-open-{facts['project_id']}")
    ws.done("1 open the project after a restart")
    ws.expand("plan-history")
    ws.done("2 the plan: hypotheses and standing; open the plan history")
    ws.click("nav-results")
    first = ws.app.session.results[0]
    ws.click(f"result-{first.id}")
    ws.done("3 find H1's result by its title (nothing links them)")
    ws.done("4 provenance and confirmations: in the result detail (scrolling)")
    ws.expand("result-interpretation-section")
    ws.segment("result-depth", "professor")
    ws.expand("result-method-notes")
    lost = {"note": not ws.app.pages["results"].notes.get(first.id),
            "review ticks": not ws.app.pages["results"].reviewed.get(first.id)}
    ws.done("5 interpretation at the professor depth, method notes")
    ws.click("nav-analyze")
    ws.click(f"task-{ws.app.session.tasks[0].id}")
    ws.done("6 the task: variables, method, options")
    ws.click("nav-data")
    ws.done("7 measurement: levels on Data (no reliability evidence is linked)")
    ws.click("nav-results")
    ws.click(f"result-{ws.app.session.results[1].id}")
    ws.done("8 H2: find its result by title, read its checks")
    ws.click("nav-reports")
    ws.expand("reports-preview")
    lost["study title"] = not ws.app.pages["reports"].study_title
    ws.done("9 the report: structure and preview")
    ws.done("10 deviations, consistency, audit log: not shown anywhere")
    ws.table(f"Professor flow ({COMMIT})")
    print("lost after the restart:", ", ".join(k for k, v in lost.items() if v) or "nothing")
    print("hypothesis_id of the tasks before the restart:", facts["hypothesis_ids"])
    ws.close()


def scale_quality(folder: Path) -> None:
    """Reliability on item-level data (the synthetic 10-item fixture), for reference."""
    ws = Measured(root=folder)
    ws.app.projects.create("Fictional item study")
    assert ws.run(ws.app.load_path(str(fx.fixture(fx.ITEMS_CSV))))
    for name in fx.ITEMS:
        ws.app.session.confirm_level(name, "ordinal")
    ws.counts.clear()
    ws.pages, ws._route = [], ws.app.route
    ws.click("nav-analyze")
    ws.click("goal-scale")
    ws.click([c.data for c in ws.find_all("role-items-all-")][0])
    for control in ws.find_all("design-confirm-"):
        ws.check(control.data)
    ws.click("guided-run")
    ws.done(f"reliability of {len(fx.ITEMS)} items ({ws.app.session.results[-1].method})")
    ws.table(f"Scale quality on item data ({COMMIT})")
    ws.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as folder:
        facts = beginner(Path(folder))
        print("level corrections after accepting the suggestions:", facts["fixes"] or "none")
        print("review ticks on the batch result:", facts["reviews"])
        professor(Path(folder), facts)
    with tempfile.TemporaryDirectory() as folder:
        scale_quality(Path(folder))
