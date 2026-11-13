"""Stage 37.0b (design AC-16): the flow of the packaged-program journey
`stage37-hypothesis`, through the harness.

`tools/windows_gui_e2e.py` drives the real Windows program by the texts UI
Automation exposes. This test walks the same flow in the workspace harness and
checks, at each point, that every text, button name, field label and dropdown
entry the journey waits for or presses is there in that state, using the
journey's own constants and helpers; and it reads the project's database the
way the journey does (read-only): the protocol records stay and their count
never decreases. UI Automation reports every button as enabled, so the
journey never relies on a disabled state; neither does this walk. Synthetic
data only (tests/fixtures/stage36).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))

import flet as ft  # noqa: E402

import stage36_fixtures as fx  # noqa: E402
from test_stage368_acceptance import (  # noqa: E402
    T, accept_levels_in_ui, buttons, create_project_in_ui, folder_of, label, on_screen, open_csv,
)
import windows_gui_e2e as e2e  # noqa: E402  (imports nothing Windows-only)
from workspace_harness import Workspace  # noqa: E402


def first_button(ws, text: str):
    """The control the journey presses: the first button with this name."""
    found = [c for c in ws.controls() if isinstance(c, (ft.Button, ft.TextButton))
             and c.content == text]
    assert found, f"no button named {text!r}"
    return found[0]


def press_first(ws, text: str) -> None:
    ws.click(first_button(ws, text).data)


def to_top(ws, key: str) -> None:
    """e2e.to_top: leave the page and open it again."""
    ws.click("nav-data" if key != "nav-data" else "nav-results")
    ws.click(key)


class JourneyOrderTests(unittest.TestCase):
    def test_the_hypothesis_journey_follows_the_eighteen(self):
        self.assertEqual(len(e2e.JOURNEYS), 19)
        self.assertEqual(list(e2e.JOURNEYS)[:18][-2:], ["confirmations", "report-composition"])
        self.assertEqual(list(e2e.JOURNEYS)[18:], ["stage37-hypothesis"])
        self.assertNotIn("stage37-hypothesis", e2e.STARTS_ITSELF)


class Stage37HypothesisJourneyTests(unittest.TestCase):
    def test_the_hypothesis_workflow_survives_a_restart(self):
        title = e2e.STAGE37_PROJECT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            disk = folder_of(root)
            csv_path = fx.generator().create_csv(root)
            counts: list[int] = []

            def record_count() -> int:
                counts.append(len(e2e.protocol_rows(disk, title)))
                self.assertEqual(counts, sorted(counts), "the record count never decreases")
                return counts[-1]

            ws = Workspace(root=root)
            try:
                create_project_in_ui(ws, title)
                self.assertEqual(ws.app.route, "project")

                # Q1: shown by itself; its text and its kind.
                self.assertTrue(on_screen(ws, T("plan.q.from_project")))
                self.assertEqual(ws.find("plan-q0-text").label, T("plan.q.text", n=1))
                ws.type("plan-q0-text", e2e.STAGE37_QUESTION)
                kind = ws.find("plan-q0-type", ft.Dropdown)
                self.assertEqual(kind.label, T("plan.q.type"))
                self.assertEqual([o.text for o in kind.options], e2e.stage37_kinds())
                ws.choose("plan-q0-type", "relate")
                self.assertTrue(on_screen(ws, T("next.add_hypothesis", q=1)))

                # H1: primary, less (one-sided).
                self.assertEqual(first_button(ws, T("next.add_hypothesis_button", q=1)).data,
                                 "next-add-hypothesis", "the bar's button comes first")
                press_first(ws, T("next.add_hypothesis_button", q=1))
                text = ws.find("plan-h0-text")
                self.assertEqual(text.label, T("plan.h.text"))
                self.assertEqual([c.data for c in ws.controls() if isinstance(c, ft.TextField)
                                  and c.label == T("plan.h.text")], ["plan-h0-text"])
                ws.type("plan-h0-text", e2e.STAGE37_H1)
                direction = ws.find("plan-h0-direction", ft.Dropdown)
                self.assertEqual(direction.label, T("plan.h.direction"))
                self.assertEqual([o.text for o in direction.options], e2e.stage37_directions())
                ws.choose("plan-h0-direction", "less")
                self.assertEqual(ws.find("plan-h0-priority").value, "primary")

                # Save plan version.
                press_first(ws, T("plan.save"))
                self.assertTrue(on_screen(ws, T("plan.saved", version=1)))
                (plan,) = e2e.project_query(disk, title, "SELECT plan FROM plan_versions")[0]
                saved = json.loads(plan)
                hypothesis = saved["hypotheses"][0]
                self.assertEqual((saved["plan_format"], saved["questions"][0]["type"],
                                  saved["questions"][0]["text"]),
                                 (2, "relate", e2e.STAGE37_QUESTION))
                self.assertEqual((hypothesis["text"], hypothesis["direction"],
                                  hypothesis["priority"]), (e2e.STAGE37_H1, "less", "primary"))
                self.assertEqual(record_count(), 0)

                # The data through the bar's Open button, then the levels.
                open_csv(ws, csv_path)
                accept_levels_in_ui(ws)

                # Create the analysis for H1 (the bar on the Project page).
                to_top(ws, "nav-project")
                self.assertTrue(on_screen(ws, T("next.create_analysis", h=1)))
                press_first(ws, T("next.create_analysis_button", h=1))
                self.assertEqual((ws.app.route, ws.app.section), ("analyze", "variables"))
                self.assertEqual(ws.find("role-x", ft.Dropdown).label, T("role.x"))
                self.assertEqual(record_count(), 1, "the link is recorded")

                # UCLA with the eight scales, Spearman, Run.
                self.assertEqual([o.text for o in ws.find("role-x", ft.Dropdown).options],
                                 e2e.stage36_options())
                ws.choose("role-x", "UCLA")
                self.assertEqual(label(ws, "role-y-all-scale"), T("pick.all_scale", count=9))
                ws.click("role-y-all-scale")
                self.assertEqual(ws.find("role-y-Age").label, e2e.option_label("Age", "scale"))
                ws.check("role-y-Age", False)
                self.assertEqual(first_button(ws, T("rec.use_instead")).data,
                                 "alt-batch_correlation-spearman", "index 0 is Spearman")
                ws.click("alt-batch_correlation-spearman")
                self.assertRegex(label(ws, "guided-run"),
                                 "^" + re.escape(T("rec.run", method="")) + "Spearman")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    ws.click("guided-run")
                self.assertTrue(on_screen(ws, T("task.title_relate", x="UCLA", count=8)))
                runs = e2e.project_query(disk, title, "SELECT provenance FROM runs")
                snapshot = json.loads(runs[0][0])["hypothesis"]
                self.assertEqual((snapshot["id"], snapshot["plan_version"], snapshot["direction"]),
                                 (hypothesis["id"], 1, "less"))

                # A check appears: H1 is one-sided, the p-values two-sided.
                to_top(ws, "nav-project")
                self.assertTrue(on_screen(ws, T("next.decide", h=1)))
                press_first(ws, T("next.show_checks", h=1))
                self.assertTrue(on_screen(ws, e2e.stage37_check_text()))

                # Acknowledge it, with a reason.
                before = record_count()
                self.assertEqual(buttons(ws, "^" + re.escape(T("hyp.acknowledge")) + "$"),
                                 [T("hyp.acknowledge")], "one Acknowledge… on the page")
                press_first(ws, T("hyp.acknowledge"))
                self.assertEqual(ws.find("hyp-1-reason").label, T("hyp.reason"))
                ws.type("hyp-1-reason", e2e.STAGE37_REASON)
                self.assertEqual(label(ws, "hyp-1-save"), T("hyp.save_record"))
                press_first(ws, T("hyp.save_record"))
                self.assertTrue(on_screen(ws, T("hyp.recorded")))
                rows = e2e.protocol_rows(disk, title)
                self.assertEqual(record_count(), before + 1)
                self.assertEqual(rows[-1][1:], ("acknowledgement", e2e.STAGE37_REASON))

                # Results shows Tests H1; into the report.
                ws.click("nav-results")
                self.assertTrue(on_screen(ws, T("results.tests", h=1, text=e2e.STAGE37_H1)))
                self.assertEqual(first_button(ws, T("results.add_report")).data,
                                 "result-add-report")
                press_first(ws, T("results.add_report"))
                self.assertEqual(label(ws, "result-add-report"), T("results.in_report"))

                # The Word report, with the hypothesis rows.
                ws.click("nav-reports")
                self.assertEqual(label(ws, "reports-export-docx"), T("reports.export_docx"))
                ws.click("reports-export-docx")
                first = ws.saved[-1]
                e2e.verify_saved(first, kind="docx", contains=e2e.stage37_report_fragments())
                import research_report as rr

                table = next(t for t in e2e.docx_tables(first)
                             if t and tuple(t[0]) == tuple(rr.TEXT["en"]["evidence_columns"]))
                self.assertEqual(len(table), 2)
                self.assertEqual(table[1][0], "H1 (primary)")
                self.assertTrue(table[1][1].startswith("Spearman ρ: UCLA with 8 variables "
                                                       "(current)"))
                before_restart = [row[0] for row in e2e.protocol_rows(disk, title)]
                project_id = ws.app.projects.info().id
            finally:
                ws.close()

            # Restart: the plan, the records, the snapshot and the report rows.
            again = Workspace(root=root)
            try:
                again.click("nav-home")
                again.click(f"project-open-{project_id}")
                from workspace_hypotheses import alpha_text

                line = " · ".join(("H1", T("plan.priority.primary"), T("plan.direction.less"),
                                   f"α = {alpha_text(0.05)}"))
                self.assertEqual(again.find("hyp-1-line").value, line)
                self.assertEqual(first_button(again, T("hyp.show")).data, "hyp-1-toggle")
                press_first(again, T("hyp.show"))
                self.assertTrue(on_screen(again, T("hyp.check.acknowledged",
                                                   reason=e2e.STAGE37_REASON)))
                after = [row[0] for row in e2e.protocol_rows(disk, title)]
                self.assertEqual(after[:len(before_restart)], before_restart)
                record_count()
                again.click("nav-results")
                self.assertTrue(on_screen(again, T("results.tests", h=1, text=e2e.STAGE37_H1)))
                again.click("nav-reports")
                again.click("reports-export-docx")
                e2e.verify_saved(again.saved[-1], kind="docx",
                                 contains=e2e.stage37_report_fragments())

                # A priority changed after results without a reason: nothing saved.
                to_top(again, "nav-project")
                priority = again.find("plan-h0-priority", ft.Dropdown)
                self.assertEqual(priority.label, T("plan.h.priority"))
                self.assertEqual([o.text for o in priority.options], e2e.stage37_priorities())
                again.choose("plan-h0-priority", "secondary")
                self.assertEqual(first_button(again, T("plan.save")).data, "next-save-plan",
                                 "the bar's Save plan version comes first")
                press_first(again, T("plan.save"))
                self.assertTrue(on_screen(again, T("plan.reason_needed", h=1)))
                self.assertEqual(e2e.project_query(disk, title,
                                                   "SELECT COUNT(*) FROM plan_versions")[0][0], 1)

                # The database, read-only: the records are kept, never fewer.
                rows = e2e.protocol_rows(disk, title)
                self.assertEqual([kind for _, kind, _ in rows], ["link", "acknowledgement"])
                record_count()
                self.assertEqual(counts, sorted(counts))
            finally:
                again.close()


if __name__ == "__main__":
    unittest.main()
