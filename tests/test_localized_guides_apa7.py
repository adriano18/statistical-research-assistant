"""Localization, scholarly references, and safe APA-style figure exports."""

from io import BytesIO
import unittest

import flet as ft
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from apa_figures import DEFAULT_NOTE, make_apa7_export_png
from localization import tr
from output_workspace import PNG_SIGNATURE
from statistical_guide import (
    GUIDE_LABELS, SCREEN_TERMS, SOURCES, TERMS,
    method_guide_items, method_guide_text,
)
from ui_i18n import UITranslator


class ScientificGuideTests(unittest.TestCase):
    def test_all_seventeen_workspaces_have_source_backed_help(self):
        self.assertEqual(len(SCREEN_TERMS), 17)
        for screen in SCREEN_TERMS:
            with self.subTest(screen=screen):
                items = method_guide_items(screen)
                self.assertGreaterEqual(len(items), 3)
                for item in items:
                    self.assertIn(item["key"], TERMS)
                    self.assertTrue(item["reference"].strip())
                    self.assertTrue(item["url"].startswith("https://"))
                english = method_guide_text(screen, "en")
                russian = method_guide_text(screen, "ru")
                latvian = method_guide_text(screen, "lv")
                self.assertIn("Understanding", english)
                self.assertIn("Объяснение", russian)
                self.assertIn("Skaidrojumi", latvian)
                self.assertNotEqual(english, russian)
        for source in SOURCES.values():
            self.assertTrue(
                source.url.startswith(("https://doi.org/", "https://www.jstor.org/"))
            )
            self.assertIn("(", source.label)

    def test_sensitive_interpretive_limits_are_explicit(self):
        self.assertIn("not causation", TERMS["r"].en.lower())
        self.assertIn("not evidence", TERMS["omega"].en.lower())
        self.assertIn("not establish scale validity", TERMS["alpha"].en.lower())
        self.assertIn("not the probability", TERMS["p"].en.lower())
        self.assertIn("not a risk ratio", TERMS["or"].en.lower())
        self.assertIn("not interchangeable", TERMS["eta"].en.lower())
        self.assertIn("American Psychological Association", SOURCES["apa"].label)

    def test_untranslated_labels_fallback_to_english(self):
        self.assertEqual(tr("en", "Save question"), "Save question")
        self.assertEqual(tr("lv", "Save question"), "Saglabāt jautājumu")
        self.assertEqual(tr("ru", "Save question"), "Сохранить вопрос")
        self.assertEqual(tr("lv", "Calculate Cronbach’s α"), "Aprēķināt Kronbaha α")
        self.assertEqual(tr("ru", "Calculate Cronbach’s α"), "Рассчитать α Кронбаха")
        self.assertEqual(tr("ru", "Unknown term not in catalog"),
                         "Unknown term not in catalog")


class UITranslatorTests(unittest.TestCase):
    def test_labels_change_but_variable_keys_and_answers_do_not(self):
        translator = UITranslator()
        text = ft.Text("Save question")
        answer = ft.TextField(
            label="Question text", value="Strongly agree",
            hint_text="Your answer",
        )
        choices = ft.Dropdown(
            label="Response type",
            value="yes_no",
            options=[
                ft.DropdownOption(key="keep_code_1", text="Demographics")
            ],
        )
        button = ft.Button("Remove")
        root = ft.Column(controls=[text, answer, choices, button])
        translator.apply(root, "ru")
        self.assertEqual(text.value, "Сохранить вопрос")
        self.assertEqual(answer.label, "Текст вопроса")
        self.assertEqual(answer.value, "Strongly agree")
        self.assertEqual(choices.value, "yes_no")
        self.assertEqual(choices.options[0].key, "keep_code_1")
        self.assertEqual(choices.options[0].text, "Демография")
        translator.apply(root, "lv")
        self.assertEqual(text.value, "Saglabāt jautājumu")
        self.assertEqual(choices.options[0].key, "keep_code_1")
        translator.apply(root, "en")
        self.assertEqual(answer.label, "Question text")
        self.assertEqual(choices.options[0].text, "Demographics")

    def test_updated_result_is_not_replaced_by_stale_translation(self):
        translator = UITranslator()
        live = ft.Text("Variable")
        translator.apply(live, "ru")
        self.assertEqual(live.value, "Переменная")
        live.value = "The observed Pearson r = .32, N = 61"
        translator.apply(live, "lv")
        self.assertEqual(live.value, "The observed Pearson r = .32, N = 61")


class APAFigureTests(unittest.TestCase):
    def setUp(self):
        fig, ax = plt.subplots(figsize=(4, 2))
        ax.plot([1, 2, 3], [2, 3, 5])
        ax.set_xlabel("Time")
        ax.set_ylabel("Score")
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=110)
        plt.close(fig)
        self.plot = buf.getvalue()

    def test_figure_has_number_italic_title_and_print_dpi(self):
        png = make_apa7_export_png(
            self.plot, "Fictional Mood Ratings Over Time",
            figure_number=4, note="Note. Synthetic values; no participants.",
        )
        self.assertTrue(png.startswith(PNG_SIGNATURE))
        with Image.open(BytesIO(png)) as exported:
            self.assertIn("Figure 4", exported.info["Title"])
            self.assertIn("Synthetic values", exported.info["Description"])
            self.assertGreaterEqual(exported.width, 2400)
            self.assertGreaterEqual(exported.height, 1000)
            self.assertAlmostEqual(exported.info["dpi"][0], 300, delta=1)
        self.assertIn("Note.", DEFAULT_NOTE)

    def test_figure_is_explicit_and_rejects_bad_inputs(self):
        with self.assertRaisesRegex(ValueError, "valid PNG"):
            make_apa7_export_png(b"not a png", "Invalid")
        for number in (0, -1, 1000, "1", True):
            with self.subTest(number=number):
                with self.assertRaises(ValueError):
                    make_apa7_export_png(
                        self.plot, "Fictional data", figure_number=number
                    )
        with self.assertRaises(ValueError):
            make_apa7_export_png(self.plot, "")
        with self.assertRaises(ValueError):
            make_apa7_export_png(self.plot, "X", note="x" * 501)


if __name__ == "__main__":
    unittest.main()
