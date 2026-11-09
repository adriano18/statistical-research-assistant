"""Stage 36.4 Chart Studio engine: specifications, prepared data, rendering.

Spec §9: charts are redrawn from stored data when their look changes, never
by re-running the analysis. Synthetic fixture only (tests/stage36_fixtures.py);
matplotlib's Agg backend.
"""

from __future__ import annotations

import contextlib
from dataclasses import FrozenInstanceError, fields, replace
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import warnings
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
from matplotlib.colors import is_color_like  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from scipy import stats  # noqa: E402

import chart_studio as cs  # noqa: E402
import stage36_fixtures as fx  # noqa: E402

PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")
SVG = "{http://www.w3.org/2000/svg}"
SCALES = tuple(fx.SCALES)


def synthetic_frame() -> pd.DataFrame:
    return pd.read_csv(fx.fixture(fx.CSV))


def chart(kind: str, *variables: str, **options) -> cs.ChartSpec:
    options.setdefault("dpi", 60)
    return cs.ChartSpec(kind=kind, variables=variables, **options)


#: At least one specification per kind, with the main variants.
EXAMPLES = {
    "histogram + KDE": chart("histogram", "UCLA", density="kde"),
    "histogram by group + normal": chart("histogram", "UCLA", group="Sex", density="normal"),
    "frequency polygon": chart("frequency_polygon", *SCALES[:3]),
    "boxplot by group": chart("boxplot", "UCLA", group="UCLA_Level", show_points=True),
    "multi-boxplot single": chart("multi_boxplot", *SCALES),
    "multi-boxplot panels": chart("multi_boxplot", *SCALES, multibox_layout="panels"),
    "multi-boxplot sequential": chart("multi_boxplot", *SCALES[:3],
                                      multibox_layout="sequential"),
    "multi-boxplot by group": chart("multi_boxplot", *SCALES[:3], group="UCLA_Level",
                                    multibox_layout="by_group"),
    "violin": chart("violin", *SCALES[:3], show_points=True),
    "scatter + OLS": chart("scatter", "UCLA", "AssertiveAction", trend="ols"),
    "scatter + LOWESS by group": chart("scatter", "UCLA", "AssertiveAction", trend="lowess",
                                       group="Sex"),
    "heatmap": chart("heatmap", *SCALES, correlation_method="spearman"),
    "Q-Q": chart("qq", "UCLA"),
    "Q-Q panels": chart("qq", *SCALES[:4]),
    "line": chart("line", "UCLA_Level", "AssertiveAction", "SocialJoining", show_points=True),
    "faceted histogram": chart("faceted", "UCLA", group="UCLA_Level", density="normal"),
    "faceted boxplot": chart("faceted", *SCALES[:3], group="Sex", facet_kind="boxplot"),
}


def pdf_pages(payload: bytes) -> int:
    return len(PdfReader(io.BytesIO(payload)).pages)


class SpecTests(unittest.TestCase):
    def test_json_round_trip(self):
        custom = chart("multi_boxplot", *SCALES[:2], group="Sex", title="Coping",
                       x_label="Scale", y_label="Score", legend="outside",
                       palette="okabe_ito", font_family="DejaVu Serif", font_size=11.5,
                       width_in=8.0, height_in=5.5, show_points=True, show_outliers=False,
                       grid=False, x_limits=(0, 10), y_limits=[5, 50], number_format=".3f",
                       apa_style=False, multibox_layout="by_group", standardize=True,
                       bins=12, bandwidth="silverman", group_order=("1", "0"),
                       units={SCALES[0]: "points", SCALES[1]: "points"},
                       note="Synthetic data.", figure_number=3)
        for spec in [*EXAMPLES.values(), custom, cs.ChartSpec()]:
            with self.subTest(spec=spec.kind):
                text = json.dumps(spec.to_dict())
                self.assertEqual(cs.ChartSpec.from_dict(json.loads(text)), spec)
                self.assertEqual(cs.ChartSpec.from_json(spec.to_json()), spec)

    def test_version_field_and_unknown_keys(self):
        spec = EXAMPLES["scatter + OLS"]
        payload = spec.to_dict()
        self.assertEqual(payload["version"], cs.SPEC_VERSION)
        payload["a_setting_from_a_later_version"] = {"anything": 1}
        payload["version"] = cs.SPEC_VERSION + 1
        self.assertEqual(cs.ChartSpec.from_dict(payload), spec)
        del payload["version"]
        self.assertEqual(cs.ChartSpec.from_dict(payload), spec)
        for version in ("1", 0, True, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                cs.ChartSpec.from_dict({**spec.to_dict(), "version": version})

    def test_values_are_normalised(self):
        spec = cs.ChartSpec(variables=["UCLA"], legend=True, x_limits=[1, 2],
                            units={"UCLA": " points "}, x_order=["a", "b"])
        self.assertEqual(spec.variables, ("UCLA",))
        self.assertEqual(spec.legend, "best")
        self.assertEqual(spec.x_limits, (1.0, 2.0))
        self.assertEqual(spec.units, (("UCLA", "points"),))
        self.assertEqual(spec.unit("UCLA"), "points")
        self.assertEqual(spec.x_order, ("a", "b"))
        self.assertEqual(cs.ChartSpec(legend=False).legend, "none")
        self.assertIsNone(cs.ChartSpec(variables=["UCLA"], group=" ").group)
        numpy_values = cs.ChartSpec(font_size=np.float64(11), dpi=np.int64(120), bins=12,
                                    figure_number=np.int32(4))
        self.assertEqual(numpy_values, cs.ChartSpec(font_size=11.0, dpi=120, bins=12,
                                                    figure_number=4))
        self.assertIs(type(numpy_values.dpi), int)
        json.dumps(numpy_values.to_dict())
        self.assertEqual(replace(spec, title="New").title, "New")
        with self.assertRaises(FrozenInstanceError):
            spec.title = "changed"

    def test_invalid_settings_are_refused(self):
        invalid = {
            "kind": {"kind": "pie"}, "palette": {"palette": "rainbow"},
            "bins zero": {"bins": 0}, "bins rule": {"bins": "sturges"},
            "bins bool": {"bins": True}, "format": {"number_format": "x"},
            "format text": {"number_format": "s"}, "limits": {"x_limits": (5, 1)},
            "limits shape": {"y_limits": (1, 2, 3)}, "font size": {"font_size": 100},
            "dpi": {"dpi": 5}, "variables string": {"variables": "UCLA"},
            "duplicate": {"variables": ("UCLA", "UCLA")},
            "group plotted": {"variables": ("UCLA",), "group": "UCLA"},
            "legend": {"legend": "somewhere"}, "flag": {"show_points": "yes"},
            "layout": {"multibox_layout": "grid"}, "trend": {"trend": "cubic"},
            "density": {"density": "histogram"}, "method": {"correlation_method": "phi"},
            "figure number": {"figure_number": 0}, "width": {"width_in": 100},
            "order": {"group_order": ("a", "a")},
        }
        for name, options in invalid.items():
            with self.subTest(name), self.assertRaises(ValueError):
                cs.ChartSpec(**options)

    def test_four_colour_blind_safe_palettes(self):
        self.assertEqual(cs.ChartSpec().palette, "scientific_blue")
        self.assertEqual(cs.DEFAULT_PALETTE, "scientific_blue")
        self.assertEqual(len(cs.PALETTES), 4)
        self.assertEqual(cs.PALETTES["scientific_blue"].colors[0], "#4477AA",
                         "the default leads with a calm blue")
        for palette in cs.PALETTES.values():
            with self.subTest(palette.name):
                self.assertGreaterEqual(len(palette.colors), 5)
                self.assertEqual(len(set(palette.colors)), len(palette.colors))
                self.assertGreaterEqual(len(palette.diverging), 3)
                self.assertTrue(all(map(is_color_like, palette.colors + palette.diverging)))
                self.assertTrue(palette.source and palette.label)

    def test_presentation_fields_are_spec_fields(self):
        names = {item.name for item in fields(cs.ChartSpec)}
        self.assertLessEqual(cs.PRESENTATION_FIELDS, names)
        for data_field in ("kind", "variables", "group", "standardize", "correlation_method",
                           "x_order", "multibox_layout", "density", "trend", "units"):
            self.assertNotIn(data_field, cs.PRESENTATION_FIELDS)


class RenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = synthetic_frame()

    def test_examples_cover_every_kind(self):
        self.assertEqual({spec.kind for spec in EXAMPLES.values()}, set(cs.KINDS))

    def test_every_kind_renders_png_svg_and_pdf(self):
        for name, spec in EXAMPLES.items():
            data = cs.prepare(spec, self.frame)
            with self.subTest(name):
                for png in cs.render_all(spec, data, "png"):
                    self.assertTrue(png.startswith(PNG_SIGNATURE))
                for svg in cs.render_all(spec, data, "svg"):
                    root = ET.fromstring(svg)
                    self.assertEqual(root.tag, f"{SVG}svg")
                for pdf in cs.render_all(spec, data, "pdf"):
                    self.assertTrue(pdf.startswith(b"%PDF"))
                    self.assertEqual(pdf_pages(pdf), 1)

    def test_png_size_and_metadata(self):
        spec = chart("boxplot", "UCLA", width_in=6.0, height_in=4.0, dpi=100)
        data = cs.prepare(spec, self.frame)
        with Image.open(io.BytesIO(cs.render(spec, data))) as image:
            self.assertEqual(image.size, (600, 400))
            self.assertNotIn("Software", image.text, "no software version in the file")
            self.assertEqual(image.text["Title"], "Boxplot of UCLA")
            self.assertEqual(image.text["Description"], cs.describe(spec, data))

    def test_format_and_index_are_checked(self):
        spec = EXAMPLES["Q-Q"]
        data = cs.prepare(spec, self.frame)
        self.assertTrue(cs.render(spec, data, "SVG").startswith(b"<?xml"))
        with self.assertRaises(ValueError):
            cs.render(spec, data, "gif")
        with self.assertRaises(ValueError):
            cs.render(spec, data, index=1)

    def test_text_is_never_parsed_as_mathematics(self):
        frame = self.frame.rename(columns={"UCLA": "Сумма $x_1$ ļ", "Age": "Vecums (gadi)"})
        spec = chart("scatter", "Vecums (gadi)", "Сумма $x_1$ ļ", trend="ols",
                     title="Šķēršļi — $test$")
        data = cs.prepare(spec, frame)
        self.assertTrue(cs.render(spec, data).startswith(PNG_SIGNATURE))
        self.assertIn("Сумма $x_1$ ļ", cs.describe(spec, data))

    def test_unavailable_font_falls_back_silently(self):
        self.assertEqual(cs.resolved_font("DejaVu Sans"), "DejaVu Sans")
        self.assertEqual(cs.resolved_font("No Such Font 36"), "DejaVu Sans")
        spec = chart("histogram", "UCLA", font_family="No Such Font 36")
        data = cs.prepare(spec, self.frame)
        expected = cs.render(replace(spec, font_family="DejaVu Sans"), data)
        self.assertEqual(cs.render(spec, data), expected)


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = synthetic_frame()

    def layout(self, layout: str, **options):
        spec = chart("multi_boxplot", *SCALES, multibox_layout=layout, **options)
        return spec, cs.prepare(spec, self.frame)

    def test_all_variables_on_one_axis(self):
        spec, data = self.layout("single")
        self.assertEqual(cs.figure_count(spec, data), 1)
        figure = cs.build_figure(spec, data)
        self.assertEqual(len(figure.axes), 1)
        self.assertEqual(len(figure.axes[0].get_xticks()), 8)

    def test_one_panel_per_variable(self):
        spec, data = self.layout("panels")
        self.assertEqual(cs.figure_count(spec, data), 1)
        figure = cs.build_figure(spec, data)
        self.assertEqual(len(figure.axes), 8)
        self.assertEqual([ax.get_title() for ax in figure.axes], list(SCALES))

    def test_sequential_view_gives_one_figure_per_variable(self):
        spec, data = self.layout("sequential")
        self.assertEqual(cs.figure_count(spec, data), 8)
        for index in range(8):
            self.assertEqual(len(cs.build_figure(spec, data, index).axes), 1)
        images = cs.render_all(spec, data)
        self.assertEqual(len(images), 8)
        self.assertEqual(len(set(images)), 8, "each figure shows another variable")
        self.assertEqual(images[2], cs.render(spec, data, index=2))
        with self.assertRaises(ValueError):
            cs.render(spec, data, index=8)
        document = cs.render_pdf_pages(spec, data)
        self.assertTrue(document.startswith(b"%PDF"))
        self.assertEqual(pdf_pages(document), 8)
        self.assertEqual(pdf_pages(cs.render_pdf_pages(spec, data)), 8)

    def test_boxes_split_by_group(self):
        spec, data = self.layout("by_group", group="UCLA_Level")
        figure = cs.build_figure(spec, data)
        self.assertEqual(len(figure.axes), 1)
        legend = figure.axes[0].get_legend()
        self.assertEqual([text.get_text() for text in legend.get_texts()], ["1", "2", "3"])
        reordered = cs.build_figure(replace(spec, group_order=("3", "1")), data)
        self.assertEqual([text.get_text() for text in reordered.axes[0].get_legend().get_texts()],
                         ["3", "1", "2"])
        with self.assertRaises(ValueError):
            cs.prepare(chart("multi_boxplot", *SCALES, multibox_layout="by_group"), self.frame)

    def test_panels_and_sequence_split_by_group(self):
        spec, data = self.layout("panels", group="Sex")
        figure = cs.build_figure(spec, data)
        self.assertEqual(len(figure.axes), 8)
        self.assertEqual(len(figure.axes[0].get_xticks()), 2, "one box per Sex level")
        spec, data = self.layout("sequential", group="UCLA_Level")
        self.assertEqual(len(cs.build_figure(spec, data, 3).axes[0].get_xticks()), 3)

    def test_other_multi_axis_kinds(self):
        counts = {"faceted histogram": 3, "faceted boxplot": 2, "Q-Q panels": 4,
                  "heatmap": 2}          # the heatmap's second axes is its colour bar
        for name, expected in counts.items():
            spec = EXAMPLES[name]
            with self.subTest(name):
                self.assertEqual(len(cs.build_figure(spec, cs.prepare(spec, self.frame)).axes),
                                 expected)


class WarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = synthetic_frame()

    def warnings_for(self, spec, frame=None):
        return " | ".join(cs.prepare(spec, self.frame if frame is None else frame).warnings)

    def test_incomparable_ranges_on_one_axis(self):
        message = "not comparable on one axis; consider panels"
        for spec in (chart("multi_boxplot", "Sex", "UCLA"),
                     chart("multi_boxplot", "Sex", "UCLA", group="UCLA_Level",
                           multibox_layout="by_group"),
                     chart("boxplot", "UCLA_Level", "UCLA"),
                     chart("violin", "Sex", "UCLA"),
                     chart("frequency_polygon", "Sex", "UCLA"),
                     chart("line", "Age", "Sex", "UCLA")):
            with self.subTest(kind=spec.kind, layout=spec.multibox_layout):
                self.assertIn(message, self.warnings_for(spec))
        for spec in (chart("multi_boxplot", *SCALES),
                     chart("multi_boxplot", "Sex", "UCLA", multibox_layout="panels"),
                     chart("multi_boxplot", "Sex", "UCLA", multibox_layout="sequential"),
                     chart("multi_boxplot", "Sex", "UCLA", standardize=True),
                     chart("scatter", "Sex", "UCLA")):
            with self.subTest(kind=spec.kind, layout=spec.multibox_layout):
                self.assertNotIn(message, self.warnings_for(spec))

    def test_different_declared_units(self):
        spec = chart("multi_boxplot", "Age", "UCLA", units={"Age": "years", "UCLA": "points"})
        text = self.warnings_for(spec)
        self.assertIn("different declared units (Age: years; UCLA: points)", text)
        self.assertIn("not comparable on one axis; consider panels", text)
        self.assertNotIn("not comparable", self.warnings_for(chart("multi_boxplot", "Age", "UCLA")),
                         "ranges 20 and 31 are comparable")

    def test_standardization_is_stated(self):
        spec = chart("multi_boxplot", "Sex", "UCLA", "Age", standardize=True)
        data = cs.prepare(spec, self.frame)
        self.assertIn("values shown as z-scores (each variable centred and scaled); not the raw "
                      "scale", " ".join(data.warnings))
        self.assertIn("z-scores", cs.describe(spec, data))
        self.assertEqual(cs.build_figure(spec, data).axes[0].get_ylabel(), "z-score")
        self.assertTrue(cs.render(spec, data).startswith(PNG_SIGNATURE))
        with self.assertRaises(ValueError):          # a constant has no z-scores
            cs.prepare(spec, self.frame.assign(Sex=1))

    def test_no_density_from_fewer_than_three_observations(self):
        spec = chart("histogram", "UCLA", density="kde")
        tiny = self.frame.head(2)
        data = cs.prepare(spec, tiny)
        self.assertIn("No density curve for UCLA: fewer than 3 observations (n = 2).",
                      data.warnings)
        self.assertEqual(len(cs.build_figure(spec, data).axes[0].lines), 0)
        self.assertEqual(len(cs.build_figure(spec, cs.prepare(spec, self.frame)).axes[0].lines), 1)
        self.assertTrue(cs.render(spec, data).startswith(PNG_SIGNATURE))
        violin = chart("violin", "UCLA", group="Sex")
        text = self.warnings_for(violin, self.frame.head(4))
        self.assertIn("No violin for UCLA (Sex = 0): fewer than 3 observations (n = 2)", text)
        self.assertTrue(cs.render(violin, cs.prepare(violin, self.frame.head(4))))

    def test_line_chart_needs_an_ordered_x(self):
        with self.assertRaisesRegex(ValueError, "ordered x axis.*'Code'.*unordered"):
            cs.prepare(chart("line", "Code", "UCLA"), self.frame)
        stages = self.frame.assign(
            Stage=self.frame["UCLA_Level"].map({1: "low", 2: "mid", 3: "high"}))
        with self.assertRaisesRegex(ValueError, "ordered"):
            cs.prepare(chart("line", "Stage", "UCLA"), stages)
        unordered = stages.assign(Stage=pd.Categorical(stages["Stage"]))
        with self.assertRaisesRegex(ValueError, "ordered"):
            cs.prepare(chart("line", "Stage", "UCLA"), unordered)
        with self.assertRaisesRegex(ValueError, "does not include: mid"):
            cs.prepare(chart("line", "Stage", "UCLA", x_order=("low", "high")), stages)
        explicit = cs.prepare(chart("line", "Stage", "UCLA", x_order=("low", "mid", "high")),
                              stages)
        self.assertEqual(explicit.x_categories, ("low", "mid", "high"))
        ordered = stages.assign(Stage=pd.Categorical(stages["Stage"], ["low", "mid", "high"],
                                                     ordered=True))
        spec = chart("line", "Stage", "UCLA")
        data = cs.prepare(spec, ordered)
        self.assertEqual(data.x_categories, ("low", "mid", "high"))
        self.assertEqual(
            [label.get_text() for label in cs.build_figure(spec, data).axes[0].get_xticklabels()],
            ["low", "mid", "high"])
        means = self.frame.groupby("UCLA_Level")["UCLA"].mean().to_numpy()
        line = cs.build_figure(spec, data).axes[0].lines[0]
        np.testing.assert_allclose(line.get_ydata(), means, rtol=0, atol=1e-12)
        with self.assertRaisesRegex(ValueError, "line chart"):
            cs.render(chart("boxplot", "Stage", "UCLA"), data)

    def test_missing_values_are_counted_and_stated(self):
        frame = self.frame.copy()
        frame.loc[[0, 3, 7], "UCLA"] = np.nan
        frame.loc[[1, 3], "AssertiveAction"] = np.nan
        frame.loc[[5], "UCLA_Level"] = np.nan
        boxes = cs.prepare(chart("boxplot", "UCLA", "AssertiveAction", group="UCLA_Level"), frame)
        self.assertEqual(boxes.missing, (3, 2))
        self.assertEqual(boxes.group_missing, 1)
        self.assertIn("Missing values left out (available cases): UCLA 3 of 55, "
                      "AssertiveAction 2 of 55.", boxes.warnings)
        self.assertIn("1 of 55 rows have no UCLA_Level value and are left out of the grouped "
                      "display.", boxes.warnings)
        scatter = chart("scatter", "UCLA", "AssertiveAction")
        pairs = cs.prepare(scatter, frame)
        self.assertIn("4 of 55 rows lack UCLA or AssertiveAction and are left out; the "
                      "scatterplot shows 51 complete pairs.", pairs.warnings)
        self.assertEqual(set(cs.CASE_HANDLING), set(cs.KINDS))
        note = " ".join(" ".join(text.get_text().split())
                        for text in cs.build_figure(scatter, pairs).texts)
        self.assertIn("N = 51 complete pairs of 55 rows. " + cs.CASE_HANDLING["scatter"], note)
        complete = cs.build_figure(scatter, cs.prepare(scatter, self.frame)).texts
        self.assertNotIn(cs.CASE_HANDLING["scatter"],
                         " ".join(" ".join(text.get_text().split()) for text in complete))

    def test_small_groups_are_flagged(self):
        text = self.warnings_for(EXAMPLES["boxplot by group"])
        self.assertIn("Small groups of UCLA_Level: 1 (n = 3).", text)

    def test_warnings_are_returned_never_printed(self):
        frame = self.frame.assign(Constant=1.0)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            heat = chart("heatmap", "UCLA", "Constant", "Age", correlation_method="pearson")
            data = cs.prepare(heat, frame)
            cs.render(heat, data)
            violin = chart("violin", "UCLA", group="Sex", font_family="No Such Font 36")
            tiny = cs.prepare(violin, frame.head(4))
            cs.render(violin, tiny, "svg")
            trend = chart("scatter", "Constant", "UCLA", trend="ols")
            flat = cs.prepare(trend, frame)
            cs.render(trend, flat, "pdf")
        self.assertEqual((stdout.getvalue(), stderr.getvalue(), caught), ("", "", []))
        self.assertIn("No coefficient for UCLA and Constant", " ".join(data.warnings))
        self.assertTrue(tiny.warnings)
        self.assertIn("No OLS trend line: Constant has no variation.", flat.warnings)

    def test_warnings_for_another_view_need_no_dataset(self):
        spec = chart("multi_boxplot", "Sex", "UCLA", multibox_layout="panels")
        data = cs.prepare(spec, self.frame)
        single = replace(spec, multibox_layout="single")
        self.assertEqual(cs.chart_warnings(single, data), cs.prepare(single, self.frame).warnings)
        self.assertEqual(cs.chart_warnings(spec, data), data.warnings)


class PurityTests(unittest.TestCase):
    #: A new value for every presentation field.
    CHANGES = {
        "title": "Loneliness and coping", "x_label": "Score", "y_label": "Count",
        "legend": "upper left", "palette": "okabe_ito", "font_family": "DejaVu Serif",
        "font_size": 12.0, "width_in": 8.0, "height_in": 6.0, "dpi": 72,
        "show_points": True, "show_outliers": False, "grid": False,
        "x_limits": (30.0, 75.0), "y_limits": (0.0, 20.0), "number_format": ".3f",
        "apa_style": False, "bins": 12, "bandwidth": "silverman", "group_order": ("1", "0"),
        "note": "Synthetic data only.", "figure_number": 2, "caption_in_image": False,
    }
    #: Fields a histogram does not draw; tested on a boxplot instead.
    BOX_FIELDS = {"show_points", "show_outliers"}

    @classmethod
    def setUpClass(cls):
        cls.frame = synthetic_frame()

    def test_render_never_touches_the_dataframe(self):
        frame = synthetic_frame()
        frame.attrs["source"] = "synthetic"
        original = frame.copy(deep=True)
        for spec in EXAMPLES.values():
            with self.subTest(spec.kind):
                data = cs.prepare(spec, frame)
                cs.render_all(spec, data, "png")
                pd.testing.assert_frame_equal(frame, original)
                self.assertEqual(frame.attrs, {"source": "synthetic"})

    def test_chart_data_is_immutable(self):
        data = cs.prepare(EXAMPLES["boxplot by group"], self.frame)
        before = cs.ChartData.from_dict(data.to_dict())
        with self.assertRaises(FrozenInstanceError):
            data.values = ()
        self.assertIsInstance(data.values[0], tuple)
        column = data.column("UCLA")
        column[:] = 0                                # a copy; the data stay as they were
        cs.render(EXAMPLES["boxplot by group"], data)
        self.assertEqual(data, before)

    def test_presentation_changes_keep_chart_data_and_change_the_image(self):
        self.assertEqual(set(self.CHANGES), set(cs.PRESENTATION_FIELDS))
        bases = {"histogram": chart("histogram", "UCLA", group="Sex", density="kde"),
                 "boxes": chart("multi_boxplot", *SCALES[:3])}
        prepared = {name: cs.prepare(base, self.frame) for name, base in bases.items()}
        images = {name: cs.render(base, prepared[name]) for name, base in bases.items()}
        for field_name, value in self.CHANGES.items():
            name = "boxes" if field_name in self.BOX_FIELDS else "histogram"
            changed = replace(bases[name], **{field_name: value})
            with self.subTest(field_name):
                self.assertEqual(cs.prepare(changed, self.frame), prepared[name],
                                 "a presentation change must not change the chart data")
                self.assertNotEqual(cs.render(changed, prepared[name]), images[name])

    def test_kind_and_layout_changes_reuse_the_stored_data(self):
        spec = chart("heatmap", *SCALES)
        data = cs.prepare(spec, self.frame)
        snapshot = cs.ChartData.from_dict(data.to_dict())
        forbidden = AssertionError("a statistic was recomputed")
        with mock.patch.object(cs, "_correlation_table", side_effect=forbidden), \
                mock.patch.object(cs.stats, "pearsonr", side_effect=forbidden), \
                mock.patch.object(cs.stats, "spearmanr", side_effect=forbidden), \
                mock.patch.object(cs.stats, "kendalltau", side_effect=forbidden), \
                mock.patch.object(cs, "prepare", side_effect=forbidden):
            views = [replace(spec, palette="tol_muted", number_format=".3f", title="Matrix"),
                     replace(spec, kind="multi_boxplot", multibox_layout="single"),
                     replace(spec, kind="multi_boxplot", multibox_layout="panels"),
                     replace(spec, kind="multi_boxplot", multibox_layout="sequential"),
                     replace(spec, kind="violin"), replace(spec, kind="qq"),
                     replace(spec, kind="histogram", standardize=True)]
            for view in views:
                with self.subTest(kind=view.kind, layout=view.multibox_layout):
                    for image in cs.render_all(view, data):
                        self.assertTrue(image.startswith(PNG_SIGNATURE))
                    self.assertTrue(cs.chart_warnings(view, data) is not None)
        self.assertEqual(data, snapshot)
        with self.assertRaisesRegex(ValueError, "prepare the chart again"):
            cs.render(replace(spec, correlation_method="kendall"), data)
        with self.assertRaisesRegex(ValueError, "other variables"):
            cs.render(chart("boxplot", "UCLA"), data)
        with self.assertRaisesRegex(ValueError, "no correlation"):
            boxes = chart("boxplot", *SCALES)
            cs.render(replace(boxes, kind="heatmap"), cs.prepare(boxes, self.frame))


class DeterminismTests(unittest.TestCase):
    def test_same_spec_and_data_give_identical_files(self):
        frame = synthetic_frame()
        # Jittered points, kernel densities, a confidence band and a colour mesh.
        for name in ("boxplot by group", "violin", "scatter + OLS", "heatmap"):
            spec = EXAMPLES[name]
            with self.subTest(name):
                first, second = cs.prepare(spec, frame), cs.prepare(spec, synthetic_frame())
                self.assertEqual(first, second)
                for fmt in ("png", "svg"):
                    self.assertEqual(cs.render(spec, first, fmt), cs.render(spec, second, fmt), fmt)
                pdf = cs.render(spec, first, "pdf")
                self.assertTrue(pdf.startswith(b"%PDF"))
                self.assertEqual(pdf_pages(pdf), pdf_pages(cs.render(spec, second, "pdf")))
                self.assertNotIn(b"CreationDate", pdf)
                self.assertNotIn(b"<dc:date>", cs.render(spec, first, "svg"))


class HeatmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frame = synthetic_frame()
        frame.loc[[0, 3, 7], "UCLA"] = np.nan
        frame.loc[[3, 11], "AssertiveAction"] = np.nan
        cls.frame = frame
        cls.names = ("UCLA", "Age", *SCALES[:4])

    def test_coefficients_equal_scipy(self):
        functions = {"pearson": stats.pearsonr, "spearman": stats.spearmanr,
                     "kendall": stats.kendalltau}
        for method, function in functions.items():
            data = cs.prepare(chart("heatmap", *self.names, correlation_method=method),
                              self.frame)
            table = data.correlation
            self.assertEqual(table.method, method)
            self.assertFalse(table.supplied)
            for i, first in enumerate(self.names):
                for j, second in enumerate(self.names):
                    keep = self.frame[first].notna() & self.frame[second].notna()
                    with self.subTest(method=method, pair=(first, second)):
                        self.assertEqual(table.pair_counts[i][j], int(keep.sum()))
                        if i == j:
                            self.assertEqual(table.coefficients[i][j], 1.0)
                            continue
                        expected = function(self.frame.loc[keep, first],
                                            self.frame.loc[keep, second]).statistic
                        self.assertAlmostEqual(table.coefficients[i][j], expected, delta=1e-12)

    def test_annotations_use_the_number_format(self):
        spec = chart("heatmap", *self.names, number_format=".3f")
        data = cs.prepare(spec, self.frame)
        texts = {text.get_text() for text in cs.build_figure(spec, data).axes[0].texts}
        value = data.correlation.coefficients[0][2]
        pairs = data.correlation.pair_counts[0][2]
        self.assertEqual(pairs, 51, "UCLA lacks rows 0, 3, 7 and AssertiveAction rows 3, 11")
        apa = f"{value:.3f}".replace("0.", ".", 1)
        self.assertIn(f"{apa}\nN = {pairs}", texts)
        self.assertIn(f"{value:.3f}\nN = {pairs}", {
            text.get_text() for text in
            cs.build_figure(replace(spec, apa_style=False), data).axes[0].texts})

    def test_supplied_coefficients_are_drawn_as_given(self):
        from correlation_matrix import analyze_correlation_matrix

        frame = synthetic_frame().assign(Constant=3.0)
        result = analyze_correlation_matrix(frame, [*SCALES[:3], "Constant"], "spearman",
                                            scales_confirmed=True)
        data = cs.correlation_chart_data(result.names, result.coefficients, result.pair_counts,
                                         method=result.method)
        self.assertTrue(data.correlation.supplied)
        self.assertFalse(data.has_values)
        self.assertEqual(data.correlation.coefficients[0][1], result.coefficients[0, 1])
        self.assertIsNone(data.correlation.coefficients[0][3])
        self.assertIn("not available in the supplied matrix", " ".join(data.warnings))
        spec = chart("heatmap", *result.names, correlation_method="spearman")
        self.assertTrue(cs.render(spec, data).startswith(PNG_SIGNATURE))
        self.assertIn("Spearman’s ρ", cs.describe(spec, data))
        with self.assertRaisesRegex(ValueError, "only a correlation matrix"):
            cs.render(replace(spec, kind="boxplot"), data)
        with self.assertRaises(ValueError):
            cs.correlation_chart_data(["a", "b"], [[1.0, 0.5], [0.4, 1.0]])
        with self.assertRaises(ValueError):
            cs.correlation_chart_data(["a", "b"], [[1.0, 1.5], [1.5, 1.0]])


class AccessibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = synthetic_frame()

    def test_every_figure_has_alt_text(self):
        for name, spec in EXAMPLES.items():
            data = cs.prepare(spec, self.frame)
            with self.subTest(name):
                text = cs.describe(spec, data)
                self.assertGreater(len(text), 40)
                for index in range(cs.figure_count(spec, data)):
                    self.assertTrue(cs.describe(spec, data, index).strip())
        spec = EXAMPLES["multi-boxplot single"]
        self.assertIn("Boxplots of 8 variables on one axis",
                      cs.describe(spec, cs.prepare(spec, self.frame)))

    def test_sequence_and_figures_are_described(self):
        spec = EXAMPLES["multi-boxplot sequential"]
        data = cs.prepare(spec, self.frame)
        self.assertIn("A sequence of 3 figures, one boxplot per variable", cs.describe(spec, data))
        self.assertIn(f"Figure 2 of 3: boxplot of {SCALES[1]} (N = 55)",
                      cs.describe(spec, data, 1))

    def test_apa_layout_title_number_and_note(self):
        spec = chart("boxplot", "UCLA", figure_number=2)
        data = cs.prepare(spec, self.frame)
        texts = {text.get_text(): text for text in cs.build_figure(spec, data).texts}
        self.assertEqual(texts["Figure 2"].get_fontweight(), "bold")
        self.assertEqual(texts["Boxplot of UCLA"].get_fontstyle(), "italic")
        self.assertTrue(any(text.startswith("Note. N = 55.") for text in texts))
        plain = {text.get_text(): text
                 for text in cs.build_figure(replace(spec, apa_style=False), data).texts}
        self.assertEqual(set(plain), {"Boxplot of UCLA"}, "no number and no note outside APA")
        self.assertEqual(plain["Boxplot of UCLA"].get_fontstyle(), "normal")

    def test_svg_carries_title_and_description(self):
        spec = chart("violin", *SCALES[:2], title="Coping & loneliness <draft>")
        data = cs.prepare(spec, self.frame)
        root = ET.fromstring(cs.render(spec, data, "svg"))
        self.assertEqual(root.find(f"{SVG}title").text, "Coping & loneliness <draft>")
        self.assertEqual(root.find(f"{SVG}desc").text, cs.describe(spec, data))


class ChartDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = synthetic_frame()

    def test_json_round_trip(self):
        stages = self.frame.assign(
            Stage=self.frame["UCLA_Level"].map({1: "low", 2: "mid", 3: "high"}))
        prepared = [cs.prepare(spec, self.frame) for spec in EXAMPLES.values()]
        prepared.append(cs.prepare(chart("line", "Stage", "UCLA", x_order=("low", "mid", "high")),
                                   stages))
        prepared.append(cs.correlation_chart_data(["a", "b"], [[1.0, 0.25], [0.25, 1.0]]))
        for data in prepared:
            with self.subTest(variables=data.variables[:2]):
                text = json.dumps(data.to_dict())
                self.assertEqual(cs.ChartData.from_dict(json.loads(text)), data)
        # A project stores settings and data as JSON; the restored pair redraws
        # the identical figure without the dataset.
        spec = EXAMPLES["violin"]
        data = cs.prepare(spec, self.frame)
        stored = json.loads(json.dumps({"spec": spec.to_dict(), "data": data.to_dict()}))
        restored_spec = cs.ChartSpec.from_dict(stored["spec"])
        restored_data = cs.ChartData.from_dict(stored["data"])
        for fmt in ("png", "svg"):
            self.assertEqual(cs.render(restored_spec, restored_data, fmt),
                             cs.render(spec, data, fmt))

    def test_only_the_needed_columns_are_kept(self):
        data = cs.prepare(EXAMPLES["boxplot by group"], self.frame)
        self.assertEqual(data.variables, ("UCLA",))
        self.assertEqual(data.group, "UCLA_Level")
        self.assertEqual(data.rows, 55)
        self.assertEqual(data.group_levels, ("1", "2", "3"))
        self.assertEqual(data.missing, (0,))
        np.testing.assert_array_equal(data.column("UCLA"), self.frame["UCLA"].to_numpy(float))

    def test_inconsistent_data_are_refused(self):
        payload = cs.prepare(EXAMPLES["boxplot by group"], self.frame).to_dict()
        broken = {
            "short column": {"values": [payload["values"][0][:-1]]},
            "unknown group": {"group_values": ["9"] * 55},
            "wrong missing": {"missing": [4]},
            "text value": {"values": [["x"] * 55]},
        }
        for name, change in broken.items():
            with self.subTest(name), self.assertRaises(ValueError):
                cs.ChartData.from_dict({**payload, **change})

    def test_non_numeric_and_identifier_columns_are_refused(self):
        frame = self.frame.astype({"UCLA": object})
        frame.loc[4, "UCLA"] = "n/a"
        with self.assertRaisesRegex(ValueError, "not numbers.*'n/a'"):
            cs.prepare(chart("histogram", "UCLA"), frame)
        with self.assertRaisesRegex(ValueError, "identifier"):
            cs.prepare(chart("histogram", "participant_id"),
                       self.frame.assign(participant_id=range(55)))
        with self.assertRaisesRegex(ValueError, "Not in the dataset: Missing"):
            cs.prepare(chart("histogram", "Missing"), self.frame)
        with self.assertRaisesRegex(ValueError, "exactly two"):
            cs.prepare(chart("scatter", "UCLA"), self.frame)


if __name__ == "__main__":
    unittest.main()
