"""Stage 36.4: Chart Studio in the workspace (docs/STAGE36_SPEC.md §9).

A result's charts are drawn from the values it was calculated on. Changing
the chart type, layout or look never runs an analysis again and never
changes a number of the result; views are saved with the project, survive a
restart and can be drawn without the dataset; the clipboard receives an
image; the Word report can use a chosen view. Synthetic data only.
"""

from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import chart_studio as cs  # noqa: E402
import chart_views as cv  # noqa: E402
import image_clipboard  # noqa: E402
import stage36_fixtures as fx  # noqa: E402
from test_stage36_ux_baseline import (  # noqa: E402
    LEVELS, CountingWorkspace, eight_correlations, prepared_workspace)

PNG = b"\x89PNG\r\n\x1a\n"


def frame() -> pd.DataFrame:
    return pd.read_csv(fx.fixture(fx.CSV))


def level(name: str) -> str:
    return LEVELS.get(name, "scale")


def kruskal_in_task(ws) -> object:
    """The eight scales compared across UCLA_Level in a research task."""
    eight_correlations(ws)
    task = ws.app.session.tasks[0]
    ws.click("task-new")
    ws.click("goal-compare")
    ws.choose("role-group", "UCLA_Level")
    ws.click(f"role-outcome-from-{task.id}")
    ws.check("design-confirm-independent")
    ws.check("design-confirm-assumptions")
    ws.click("guided-run")
    entry = ws.app.session.results[-1]
    assert entry.method == "batch_groups"
    return entry


class NoAnalysis:
    """Fails the test if any analysis runs while it is active."""

    def __init__(self, case: unittest.TestCase):
        import analysis_runs

        self.patches = [mock.patch.object(analysis_runs, name, side_effect=AssertionError(
            f"analysis_runs.{name} ran: a chart change must not recalculate"))
            for name in dir(analysis_runs) if name.startswith("run_")]
        self.case = case

    def __enter__(self):
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in self.patches:
            patch.stop()


# ------------------------------------------------------------------ engine
class StoredValuesTests(unittest.TestCase):
    """Views are derived from the stored values, never from the dataset."""

    def setUp(self):
        self.frame = frame()
        self.copy = self.frame.copy()
        self.source = cs.snapshot(self.frame, ("UCLA", *fx.SCALES), "UCLA_Level")

    def test_snapshot_reads_the_columns_and_never_changes_the_dataset(self):
        pd.testing.assert_frame_equal(self.frame, self.copy)
        self.assertEqual(self.source.variables, ("UCLA", *fx.SCALES))
        self.assertEqual(self.source.group_levels, ("1", "2", "3"))
        self.assertEqual(self.source.rows, 55)
        np.testing.assert_allclose(self.source.column("UCLA"), self.frame["UCLA"].to_numpy(float))

    def test_heatmap_from_stored_values_equals_the_dataset_and_scipy(self):
        from scipy import stats

        spec = cs.ChartSpec(kind="heatmap", variables=("UCLA", *fx.SCALES),
                            correlation_method="spearman")
        derived = cs.derive(spec, self.source).correlation.matrix()
        prepared = cs.prepare(spec, self.frame).correlation.matrix()
        np.testing.assert_array_equal(derived, prepared)
        rho = stats.spearmanr(self.frame["UCLA"], self.frame[fx.SCALES[0]]).statistic
        self.assertAlmostEqual(derived[0, 1], rho, places=12)

    def test_a_view_can_only_use_what_is_stored(self):
        with self.assertRaisesRegex(ValueError, "not stored"):
            cs.derive(cs.ChartSpec(kind="histogram", variables=("Age",)), self.source)
        with self.assertRaisesRegex(ValueError, "not the group"):
            cs.derive(cs.ChartSpec(kind="boxplot", variables=("UCLA",), group="Sex"), self.source)

    def test_line_across_ordered_levels_uses_the_stated_order(self):
        spec = cs.ChartSpec(kind="line", variables=("UCLA_Level", "UCLA"), x_order=("3", "2", "1"))
        data = cs.derive(spec, self.source)
        self.assertEqual(data.x_categories, ("3", "2", "1"))
        positions = data.column("UCLA_Level")
        labels = self.frame["UCLA_Level"].astype(str).to_numpy()
        self.assertTrue(np.all(positions[labels == "3"] == 0))
        self.assertEqual(cs.available_kinds(self.source)[-1], "faceted")
        self.assertIn("line", cs.available_kinds(self.source, ordered_group=True))
        self.assertNotIn("line", cs.available_kinds(self.source, ordered_group=False))

    def test_caption_can_be_left_to_the_document(self):
        spec = cs.ChartSpec(kind="histogram", variables=("UCLA",), title="Fictional title")
        data = cs.derive(spec, self.source)
        with_caption = cs.build_figure(spec, data)
        without = cs.build_figure(cs.ChartSpec(kind="histogram", variables=("UCLA",),
                                               title="Fictional title", caption_in_image=False),
                                  data)
        self.assertTrue(any("Fictional title" in t.get_text() for t in with_caption.texts))
        self.assertEqual(without.texts, [], "no title or note band in the image")
        self.assertEqual(cs.figure_title(spec), "Fictional title")
        self.assertTrue(cs.figure_note(spec, data).startswith("Note."))


class ChartStateTests(unittest.TestCase):
    def state(self, method="batch_groups", roles=None, options=None, data=None):
        roles = roles or {"group": "UCLA_Level", "outcomes": list(fx.SCALES)}
        return cv.create_state(method=method, roles=roles, options=options or {},
                               frame=frame() if data is None else data, level=level)

    def test_each_result_opens_with_the_chart_that_answers_its_question(self):
        groups = self.state()
        self.assertEqual((groups.view.kind, groups.view.multibox_layout, groups.view.group),
                         ("multi_boxplot", "panels", "UCLA_Level"))
        self.assertTrue(groups.view.show_points, "a group of 3: the observations are shown")
        self.assertTrue(groups.ordered_group)
        family = self.state("batch_correlation", {"x": "UCLA", "ys": list(fx.SCALES)},
                            {"method": "spearman"})
        self.assertEqual((family.view.kind, family.view.correlation_method),
                         ("heatmap", "spearman"))
        pair = self.state("correlation", {"x": "UCLA", "y": fx.SCALES[0]}, {"method": "spearman"})
        self.assertEqual((pair.view.kind, pair.view.trend), ("scatter", "lowess"))
        single = self.state("descriptive", {"variable": "UCLA"})
        self.assertEqual(single.view.kind, "histogram")
        omnibus = self.state("omnibus", {"outcome": fx.SCALES[0], "group": "UCLA_Level"})
        self.assertEqual((omnibus.view.kind, omnibus.view.group), ("boxplot", "UCLA_Level"))

    def test_a_result_without_data_or_numbers_is_explained(self):
        with self.assertRaises(cv.ChartsUnavailable) as caught:
            cv.create_state(method="batch_groups", roles={}, options={}, frame=None, level=level)
        self.assertEqual(caught.exception.key, "chart.no_data")
        with self.assertRaises(cv.ChartsUnavailable) as caught:
            self.state("chi", {"a": "Sex", "b": "UCLA_Level"})
        self.assertEqual(caught.exception.key, "chart.no_numeric")
        changed = frame()
        changed.loc[0, "UCLA"] += 1
        with self.assertRaises(cv.ChartsUnavailable) as caught:
            cv.create_state(method="batch_groups",
                            roles={"group": "UCLA_Level", "outcomes": list(fx.SCALES)},
                            options={}, frame=changed, level=level,
                            expected_sha256=cv.dataset_sha256(frame()))
        self.assertEqual(caught.exception.key, "chart.data_changed")

    def test_views_round_trip_and_draw_the_same_figure(self):
        state = self.state()
        state.add_view()
        state.update(cs.ChartSpec(kind="violin", variables=fx.SCALES[:3], group="UCLA_Level",
                                  palette="okabe_ito"))
        state.report = 1
        again = cv.ChartState.from_dict(state.to_dict())
        self.assertEqual(again.views, state.views)
        self.assertEqual((again.active, again.report), (1, 1))
        self.assertEqual(again.render("png"), state.render("png"))
        self.assertEqual(again.render("svg"), state.render("svg"))
        again.remove_view(0)
        self.assertEqual((len(again.views), again.active, again.report), (1, 0, 0))

    def test_incomparable_ranges_on_one_axis_are_warned(self):
        rng = np.random.default_rng(36)
        data = pd.DataFrame({"short_scale": rng.integers(0, 6, 40).astype(float),
                             "long_scale": rng.integers(0, 101, 40).astype(float)})
        state = cv.create_state(method="paired", roles={"before": "short_scale",
                                                        "after": "long_scale"},
                                options={}, frame=data, level=lambda name: "scale")
        self.assertEqual((state.view.kind, state.view.multibox_layout), ("multi_boxplot", "single"))
        warning = [w for w in state.warnings() if "differ markedly in range" in w]
        self.assertTrue(warning, state.warnings())
        state.update(replace(state.view, multibox_layout="panels"))
        self.assertFalse([w for w in state.warnings() if "differ markedly" in w],
                         "separate panels have separate axes")
        state.update(replace(state.view, multibox_layout="single", standardize=True))
        self.assertTrue(any("z-scores" in w for w in state.warnings()))

    def test_an_impossible_view_is_refused_and_the_old_one_kept(self):
        state = self.state()
        before = state.view
        with self.assertRaises(ValueError):
            state.update(cs.ChartSpec(kind="scatter", variables=fx.SCALES[:3]))
        self.assertEqual(state.view, before)

    def test_report_figure_has_the_title_and_note_outside_the_image(self):
        state = self.state()
        state.report = 0
        png, title, note = state.report_figure()
        self.assertTrue(png.startswith(PNG))
        self.assertIn("UCLA_Level", title)
        self.assertTrue(note.startswith("Note."))


class ClipboardTests(unittest.TestCase):
    def png(self, mode="RGB", size=(30, 20)) -> bytes:
        image = Image.new(mode, size, (10, 20, 30, 0) if mode == "RGBA" else (10, 20, 30))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def test_dib_is_a_24_bit_bitmap_of_the_same_size(self):
        dib = image_clipboard.png_to_dib(self.png(size=(30, 20)))
        size, width, height, planes, bits = struct.unpack("<IiiHH", dib[:16])
        self.assertEqual((size, width, abs(height), planes, bits), (40, 30, 20, 1, 24))
        row = (30 * 3 + 3) // 4 * 4
        self.assertEqual(len(dib), 40 + row * 20)

    def test_transparent_areas_are_white(self):
        dib = image_clipboard.png_to_dib(self.png("RGBA"))
        self.assertEqual(dib[40:43], b"\xff\xff\xff", "laid on white, not black")

    def test_only_png_is_accepted(self):
        with self.assertRaises(ValueError):
            image_clipboard.png_to_dib(b"not an image")

    @unittest.skipIf(sys.platform == "win32", "Linux helper selection")
    def test_linux_uses_an_image_helper_or_says_it_is_missing(self):
        with mock.patch.dict("os.environ", {"DISPLAY": "", "WAYLAND_DISPLAY": ""}):
            outcome = image_clipboard.copy_png(self.png())
        self.assertEqual((outcome.copied, outcome.how), (False, "unavailable"))
        with mock.patch.dict("os.environ", {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}), \
                mock.patch.object(image_clipboard.shutil, "which", return_value="/usr/bin/xclip"), \
                mock.patch.object(image_clipboard.subprocess, "run") as run:
            outcome = image_clipboard.copy_png(self.png())
        self.assertTrue(outcome.copied)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:5], ["xclip", "-selection", "clipboard", "-t", "image/png"])
        self.assertTrue(run.call_args.kwargs["input"].startswith(PNG))

    @unittest.skipUnless(sys.platform == "win32", "the Windows clipboard")
    def test_windows_clipboard_holds_the_bitmap(self):
        outcome = image_clipboard.copy_png(self.png(size=(31, 17)))
        self.assertTrue(outcome.copied, outcome.detail)
        self.assertEqual(image_clipboard.clipboard_image_size(), (31, 17))


# --------------------------------------------------------------- workspace
class ChartStudioWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.ws = prepared_workspace()
        self.addCleanup(self.ws.close)
        self.entry = kruskal_in_task(self.ws)

    def studio(self):
        return self.ws.app.pages["charts"]

    def test_a_task_result_opens_in_chart_studio_with_its_warnings(self):
        ws = self.ws
        ws.click("task-edit-chart")
        self.assertEqual(ws.app.route, "charts")
        self.assertEqual(ws.app.area, "results", "Chart Studio belongs to Results")
        self.assertFalse(ws.has_text("could not be shown"))
        kinds = [c.data for c in ws.find_all("chart-kind-")]
        self.assertEqual(kinds, [f"chart-kind-{k}" for k in (
            "histogram", "frequency_polygon", "boxplot", "multi_boxplot", "violin", "scatter",
            "heatmap", "qq", "line", "faceted")])
        self.assertTrue(ws.has_text("Small groups of UCLA_Level"))
        self.assertTrue(ws.has_text("Text alternative:"))
        self.assertTrue(ws.find("chart-preview"))

    def test_changing_the_chart_never_runs_the_analysis(self):
        ws, entry = self.ws, self.entry
        ws.click("task-edit-chart")
        run, numbers = entry.run, entry.run.result
        with NoAnalysis(self):
            for kind in ("violin", "histogram", "heatmap", "scatter", "qq", "faceted", "line",
                         "frequency_polygon", "boxplot", "multi_boxplot"):
                ws.click(f"chart-kind-{kind}")
                self.assertEqual(entry.charts.view.kind, kind)
                self.assertIsNone(self.studio().error, kind)
            for layout in ("single", "panels", "sequential", "by_group"):
                ws.segment("chart-layout", layout)
                self.assertEqual(entry.charts.view.multibox_layout, layout)
            ws.check("chart-points", True)
            ws.choose("chart-palette", "grayscale")
        self.assertIs(entry.run, run)
        self.assertEqual(entry.run.result, numbers)
        self.assertEqual(len(ws.app.session.results), 2, "no new result")

    def test_multi_boxplot_layouts_warnings_and_explicit_z_scores(self):
        ws, entry = self.ws, self.entry
        ws.click("task-edit-chart")
        ws.segment("chart-layout", "sequential")
        self.assertEqual(ws.find("chart-page").value, "Figure 1 of 8")
        ws.click("chart-next")
        self.assertEqual(ws.find("chart-page").value, "Figure 2 of 8")
        ws.segment("chart-layout", "single")
        ws.check("chart-group", False)
        ws.check("chart-var-AssertiveAction", False)
        ws.check("chart-standardize", True)
        self.assertTrue(entry.charts.view.standardize)
        self.assertTrue(ws.has_text("z-scores"), "the transformation is stated")
        self.assertIn("z-score", cs.describe(entry.charts.view, entry.charts.data()))

    def test_comparable_ranges_share_an_axis_without_a_warning(self):
        ws = self.ws
        first = ws.app.session.results[0]          # UCLA with the eight scales
        ws.app.pages["charts"].open(first.id)
        ws.click("chart-kind-multi_boxplot")
        ws.segment("chart-layout", "single")
        self.assertEqual(first.charts.view.variables, ("UCLA", *fx.SCALES))
        self.assertFalse([w for w in first.charts.warnings() if "range" in w],
                         "spans 20–31 points are comparable")

    def test_exports_are_real_files(self):
        ws = self.ws
        ws.click("task-edit-chart")
        ws.segment("chart-layout", "sequential")
        studio = self.studio()
        ws.run(studio.save("png"))
        ws.run(studio.save("svg"))
        ws.run(studio.save("pdf"))
        png, svg, pdf = (path.read_bytes() for path in ws.saved[-3:])
        self.assertTrue(png.startswith(PNG))
        self.assertIn(b"<svg", svg[:400])
        self.assertIn(b"<desc>", svg, "alt text for screen readers")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertEqual(pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page "), 8,
                         "one page per scale in the sequential layout")
        self.assertTrue(ws.find("chart-feedback"))

    def test_copy_puts_an_image_on_the_clipboard(self):
        ws, entry = self.ws, self.entry
        ws.click("task-edit-chart")
        with mock.patch.object(image_clipboard, "copy_png",
                               return_value=image_clipboard.ClipboardOutcome(True, "windows")) as copy:
            ws.click("chart-copy")
        png = copy.call_args.args[0]
        self.assertTrue(png.startswith(PNG))
        self.assertEqual(png, entry.charts.render("png"), "the full-resolution chart")
        self.assertTrue(ws.has_text("Copied as an image"))
        with mock.patch.object(image_clipboard, "copy_png", return_value=image_clipboard
                               .ClipboardOutcome(False, "unavailable", "no helper")):
            ws.click("chart-copy")
        self.assertTrue(ws.has_text("Save the chart as PNG instead"))

    def test_the_result_figure_can_be_copied_from_results(self):
        ws, entry = self.ws, self.entry
        ws.click("task-open-result")
        with mock.patch.object(image_clipboard, "copy_png",
                               return_value=image_clipboard.ClipboardOutcome(True, "windows")) as copy:
            ws.click("result-copy-image")
        self.assertEqual(copy.call_args.args[0], entry.run.png)
        ws.click("result-edit-chart")
        self.assertEqual(ws.app.route, "charts")

    def test_the_word_report_uses_the_chosen_view(self):
        from docx import Document

        ws, entry = self.ws, self.entry
        ws.click("task-edit-chart")
        ws.click("chart-kind-violin")
        ws.type("chart-title", "Coping by fictional loneliness level")
        ws.click("chart-apply")
        ws.click("chart-report")
        self.assertTrue(entry.in_report)
        self.assertEqual(entry.charts.report, entry.charts.active)
        ws.click("nav-reports")
        ws.click("reports-export-docx")
        document = Document(str(ws.saved[-1]))
        text = "\n".join(p.text for p in document.paragraphs)
        self.assertIn("Coping by fictional loneliness level", text)
        self.assertIn("Violins are Gaussian kernel density estimates", text,
                      "the figure note is document text")
        self.assertEqual(len(document.inline_shapes), 1)

    def test_views_return_after_a_restart_and_draw_without_the_dataset(self):
        root = self.ws.root
        ws, entry = self.ws, self.entry
        ws.click("task-edit-chart")
        ws.click("chart-kind-heatmap")
        ws.click("chart-add-view")
        ws.click("chart-kind-multi_boxplot")
        ws.segment("chart-layout", "by_group")
        ws.click("chart-report")
        expected = [view.to_dict() for view in entry.charts.views]
        project_id = ws.app.projects.info().id
        record_id = entry.record_id
        ws.app.projects.close(clear=False)
        again = CountingWorkspace(root=root)
        self.addCleanup(again.close)
        again.app.projects.open(project_id)
        restored = next(e for e in again.app.session.results if e.record_id == record_id)
        self.assertEqual([view.to_dict() for view in restored.charts.views], expected)
        self.assertEqual((restored.charts.active, restored.charts.report), (1, 1))
        again.app.session.df = None                     # the data file is gone
        again.app.pages["charts"].open(restored.id)
        self.assertFalse(again.has_text("could not be shown"))
        self.assertTrue(again.find("chart-preview"))
        self.assertTrue(restored.charts.render("png").startswith(PNG))

    def test_changed_data_are_not_drawn_under_an_old_result(self):
        ws, entry = self.ws, self.entry
        changed = ws.app.session.df.copy()
        changed.loc[0, fx.SCALES[0]] += 1
        ws.app.session.set_dataset(changed, "changed.csv")
        for name, value in LEVELS.items():
            ws.app.session.confirm_level(name, value)
        ws.app.pages["charts"].open(entry.id)
        self.assertTrue(ws.find("chart-unavailable"))
        self.assertTrue(ws.has_text("not the version this result was calculated on"))
        self.assertIsNone(entry.charts)


class ChartStudioLanguageTests(unittest.TestCase):
    def test_every_control_is_translated(self):
        for language in ("lv", "ru"):
            ws = prepared_workspace()
            self.addCleanup(ws.close)
            kruskal_in_task(ws)
            ws.app.set_language(language)
            ws.click("task-edit-chart")
            raw = [t for t in ws.texts() if t.startswith("chart.")]
            self.assertEqual(raw, [], f"untranslated keys in {language}")


if __name__ == "__main__":
    unittest.main()
