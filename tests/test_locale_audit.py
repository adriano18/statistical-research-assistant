"""Stage 36.8 (issue #62): the EN/LV/RU localization audit.

The checker logic is tested on synthetic texts and synthetic source files;
the repository itself must have no missing translation, no undefined key and
no placeholder mismatch. The other categories are review input and are only
counted, never required to be zero.
"""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("MPLBACKEND", "Agg")

import locale_audit as la  # noqa: E402


def entry(en, lv, ru, key="demo.key", table="workspace_text.T"):
    return la.Entry(table, key, en, lv, ru, "demo.py")


def details(findings, language=None):
    return [f.detail for f in findings if language is None or f.language == language]


class EntryCheckTests(unittest.TestCase):
    def test_missing_translation_and_missing_english_source(self):
        self.assertEqual(details(la.check_missing(entry("Save", "", "Сохранить"))),
                         ["no translation"])
        self.assertEqual([f.language for f in la.check_missing(entry("Save", None, None))],
                         ["lv", "ru"])
        self.assertEqual(details(la.check_missing(entry(None, "Saglabāt", None))),
                         ["translated but no English source text"])
        # Empty in every language is deliberate (e.g. a direction word "none").
        self.assertEqual(la.check_missing(entry("", "", "")), [])
        self.assertEqual(la.check_missing(entry("Save", "Saglabāt", "Сохранить")), [])

    def test_identical_text_counts_only_when_words_are_left(self):
        found = la.check_identical(entry("Open file", "Open file", "Открыть файл"))
        self.assertEqual([(f.language, f.detail) for f in found],
                         [("lv", "same as English: Open, file")])
        for same in ("Statistical Research Assistant", "EFA / PCA", "ANCOVA / GLM", "α", "N",
                     "{reason}", "H{number} ({priority}): {text}", "SPSS · CSV", "p", "#"):
            self.assertEqual(la.check_identical(entry(same, same, same)), [], same)
        # A translatable word next to an allowed name still counts.
        self.assertEqual(details(la.check_identical(entry("CSV separator", "CSV separator",
                                                          "Разделитель CSV")), "lv"),
                         ["same as English: separator"])

    def test_placeholder_sets_must_match_english(self):
        found = la.check_placeholders(entry("{count} rows of {name}", "{count} rindas",
                                            "{n} строк {name}"))
        self.assertEqual([(f.language, f.detail) for f in found],
                         [("lv", "missing {name}"),
                          ("ru", "missing {count}; unexpected {n}")])
        self.assertEqual(details(la.check_placeholders(entry("{name}", "{name", "{name}"))),
                         ["malformed braces"])
        self.assertEqual(details(la.check_placeholders(entry("{a", "{a}", "{a}"))),
                         ["malformed braces"])
        # Order, repetition and format specs do not matter; escaped braces are text.
        self.assertEqual(la.check_placeholders(entry("{a} and {b:.2f}", "{b} un {a} {a}",
                                                     "{{x}} {b} и {a}")), [])

    def test_style_problems(self):
        self.assertEqual(details(la.check_style(entry("Save file", "Saglabāt  failu",
                                                      "Сохранить файл")), "lv"),
                         ["doubled space"])
        self.assertIn("Latin words in Russian text: with, variables",
                      details(la.check_style(entry("UCLA with 8 variables", "UCLA ar 8 mainīgajiem",
                                                   "UCLA with 8 variables переменными")), "ru"))
        # Names, abbreviations, placeholders, file names and Latin terms are fine.
        self.assertEqual(la.check_style(entry(
            "Spearman’s ρ for {name} in data.csv (post hoc)",
            "Spīrmena ρ mainīgajam {name} failā data.csv (post hoc)",
            "ρ Спирмена для {name} в data.csv (post hoc), SPSS, ANOVA")), [])
        mixed = "Cвязь"                     # the first letter is a Latin C
        self.assertIn(f"“{mixed}” mixes Latin and Cyrillic letters",
                      details(la.check_style(entry("Association", "Sakarība", mixed)), "ru"))
        self.assertIn("Cyrillic letters in Latvian text",
                      details(la.check_style(entry("Data", "Данные", "Данные")), "lv"))
        self.assertIn("no Cyrillic letters in Russian text",
                      details(la.check_style(entry("Open the data file", "Atveriet datu failu",
                                                   "Atveriet datu failu")), "ru"))
        long_plain = "Sis rezultats ir aprekinats pirms datu kopas mainas un ir jaaprekina velreiz"
        self.assertIn("no Latvian diacritics in a long text",
                      details(la.check_style(entry("This result is stale.", long_plain,
                                                   "Результат устарел.")), "lv"))
        self.assertIn("“sagatavosana” lacks a diacritic (-šana)",
                      details(la.check_style(entry("Data preparation", "Datu sagatavosana",
                                                   "Подготовка данных")), "lv"))
        self.assertIn("whitespace at the end differs from English",
                      details(la.check_style(entry("small ", "vāja ", "слабая")), "ru"))
        self.assertEqual(la.check_style(entry("small ", "vāja ", "слабая ")), [])

    def test_length_risk_needs_ratio_and_a_real_length(self):
        found = la.check_length(entry("Backup…", "Rezerves kopija…", "Резервная копия…"))
        self.assertEqual([f.language for f in found], ["lv", "ru"])
        self.assertIn("2.3× English (7)", found[0].detail)
        # Short labels never wrap; translations close to English are fine.
        self.assertEqual(la.check_length(entry("Save", "Saglabāt", "Сохранить")), [])
        self.assertEqual(la.check_length(entry("Open the data file", "Atvērt datu failu",
                                               "Открыть файл данных")), [])
        # Placeholders count as a short value in every language.
        self.assertEqual(la.check_length(entry("Run {method}", "Palaist {method}",
                                               "Выполнить {method}")), [])


class TableShapeTests(unittest.TestCase):
    def spec(self, shape):
        return la.TableSpec("demo.TABLE", "demo", "TABLE", shape)

    def test_every_shape_becomes_entries(self):
        rows = la.entries_from(self.spec("triples"), {"a": ("A", "Ā", "А"), "b": ("B",)})
        self.assertEqual([(r.key, r.en, r.lv, r.ru) for r in rows],
                         [("a", "A", "Ā", "А"), ("b", "B", None, None)])
        rows = la.entries_from(self.spec("pairs"), {"Open": ["Atvērt", "Открыть"]})
        self.assertEqual((rows[0].key, rows[0].en, rows[0].lv, rows[0].ru),
                         ("Open", "Open", "Atvērt", "Открыть"))
        rows = la.entries_from(self.spec("languages"), {
            "en": {"title": "Title", "cols": ("A", "B")},
            "lv": {"title": "Nosaukums", "cols": ("Ā",)},
            "ru": {"cols": ("А", "Б"), "extra": "Лишнее"}})
        self.assertEqual([(r.key, r.en, r.lv, r.ru) for r in rows], [
            ("title", "Title", "Nosaukums", None), ("cols[0]", "A", "Ā", "А"),
            ("cols[1]", "B", None, "Б"), ("extra", None, None, "Лишнее")])
        rows = la.entries_from(self.spec("tuples"), {"en": ("A", "B"), "lv": ("Ā", "B̄"),
                                                     "ru": ("А",)})
        self.assertEqual([r.ru for r in rows], ["А", None])
        rows = la.entries_from(self.spec("plurals"), {"rows": {
            "en": ("row", "rows"), "lv": ("rinda", "rindas", "rindu"),
            "ru": ("строка", "строки", "строк")}})
        self.assertEqual([(r.key, r.en, r.lv, r.ru) for r in rows], [
            ("rows[0]", "row", "rinda", "строка"), ("rows[1]", "rows", "rindas", "строки"),
            ("rows[2]", "rows", "rindu", "строк")])
        rows = la.entries_from(self.spec("assumptions"), {"Check A": {"lv": "Pārbaudīt A"}},
                               english={"Check A": None, "Check B": None})
        self.assertEqual([(r.key, r.lv, r.ru) for r in rows],
                         [("Check A", "Pārbaudīt A", None), ("Check B", None, None)])
        rows = la.entries_from(self.spec("methods"), {"groups": {"lv": {"rationale": "Ā"}}},
                               english={"groups": {"rationale": "A", "limitation": "B"}})
        self.assertEqual([(r.key, r.en, r.lv, r.ru) for r in rows], [
            ("groups.rationale", "A", "Ā", None), ("groups.limitation", "B", None, None)])
        rows = la.entries_from(self.spec("scales"),
                               {"lv": {"agree": {5: ["Jā"]}}, "ru": {"agree": {5: []}}},
                               english={"agree": {5: ["Yes"]}})
        self.assertEqual([(r.key, r.en, r.lv, r.ru) for r in rows],
                         [("agree.5[0]", "Yes", "Jā", None)])
        with self.assertRaises(ValueError):
            la.entries_from(self.spec("unknown"), {})

    def test_static_tables_are_read_without_importing(self):
        with TemporaryDirectory() as folder:
            Path(folder, "starter.py").write_text(
                "raise SystemExit('never imported')\nSPLASH = {'en': ('Start',)}\n",
                encoding="utf-8")
            self.assertEqual(la._static_value(Path(folder), "starter", "SPLASH"),
                             {"en": ("Start",)})


DEMO_SOURCE = '''
import flet as ft
import workspace_components as wc

OPTIONS = (("first", "First choice"), ("second", "Second choice"))
LANGUAGES = (("en", "English"), ("lv", "Latviešu"), ("ru", "Русский"))
FORMATS = ((".0f", "0"), (".1f", "0.0"))


class Page:
    def build(self, ui, key):
        return [
            wc.text(ui, "Hello world"),
            wc.caption(ui, f"{key} rows loaded"),
            wc.text(ui, "data-reimport"),
            wc.text(ui, "SPSS · CSV"),
            wc.notice(ui, ui.t("demo.notice"), "warning", title="Careful now"),
            wc.chip(ui, ui.t("demo.chip"), "success"),
            wc.button(ui, ui.t("demo.save"), None, tooltip=self.app.t("demo.tip")),
            wc.button(ui, label or "Enlarge"),
            wc.dropdown(ui, ui.t("demo.pick"), [("a", "Auto detect"), ("b", ui.t("demo.b"))],
                        None),
            wc.segmented(ui, [("x", ui.t("demo.seg"))], "x", None),
            wc.step_card(ui, 1, ui.t("demo.step"), []),
            ft.Text("Open file"),
            ft.Text(ui.t(f"demo.kind.{key}")),
            ft.Text(ui.t("demo.prefix." + key)),
            ft.Text(ui.t("demo.undefined")),
            ft.TextButton(content=ui.t("demo.more")),
        ]
'''


class SourceScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = TemporaryDirectory()
        root = Path(cls.folder.name)
        (root / "workspace_demo.py").write_text(DEMO_SOURCE, encoding="utf-8")
        (root / "workspace_text.py").write_text("T = {'ignored': ('Not a screen',)}\n",
                                                encoding="utf-8")
        cls.scan = la.scan_source(root)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_english_literals_in_visible_parameters(self):
        literals = {(f.key, f.text) for f in self.scan.literals}
        self.assertEqual(literals, {
            ("wc.text", "Hello world"), ("wc.caption", "{} rows loaded"),
            ("wc.notice", "Careful now"), ("wc.button", "Enlarge"),
            ("wc.dropdown", "Auto detect"), ("ft.Text", "Open file"),
            ("(value, label) choices", "First choice"),
            ("(value, label) choices", "Second choice")})
        hello = next(f for f in self.scan.literals if f.text == "Hello world")
        self.assertEqual(hello.location, "workspace_demo.py:13")
        self.assertEqual(hello.detail, "English literal: Hello, world")

    def test_keys_patterns_and_button_labels(self):
        self.assertTrue({"demo.notice", "demo.chip", "demo.save", "demo.tip", "demo.pick",
                         "demo.b", "demo.seg", "demo.step", "demo.undefined",
                         "demo.more"} <= set(self.scan.keys))
        self.assertEqual(set(self.scan.patterns),
                         {r"^demo\.kind\.[^.]+$", r"^demo\.prefix\.[^.]+$"})
        self.assertEqual(self.scan.button_keys, {"demo.save", "demo.seg", "demo.step",
                                                  "demo.more"})
        self.assertTrue(la.is_button_key("imp.step.items", self.scan))
        self.assertTrue(la.is_button_key("journey.data", self.scan))
        self.assertFalse(la.is_button_key("journey.data.tip", self.scan))
        self.assertFalse(la.is_button_key("demo.notice", self.scan))

    def test_undefined_keys_are_missing(self):
        defined = [entry(k, k, k, key=k) for k in (
            "demo.notice", "demo.chip", "demo.save", "demo.tip", "demo.pick", "demo.b",
            "demo.seg", "demo.step", "demo.more", "demo.kind.box")]
        found = la.check_keys(self.scan, defined)
        self.assertEqual([(f.key, f.detail) for f in found], [
            ("demo.undefined", "used by the workspace but not defined (the screen shows the key)"),
            (r"^demo\.prefix\.[^.]+$", "no defined key matches this composed key")])
        self.assertEqual(found[0].location, "workspace_demo.py:28")

    def test_keys_written_twice(self):
        with TemporaryDirectory() as folder:
            Path(folder, "workspace_text.py").write_text(textwrap.dedent('''
                T = {"a": ("A", "Ā", "А"), "b": ("B", "B", "Б")}
                T.update({"a": ("A", "Ā2", "А")})
                LABELS = {"x": ("X", "Х"), "x": ("X", "Х")}
            '''), encoding="utf-8")
            found = la.duplicate_keys(Path(folder))
        self.assertEqual([(f.table, f.key, f.detail) for f in found], [
            ("workspace_text.T", "a", "key written 2 times (lines 2, 3); the last text is shown"),
            ("workspace_text.LABELS", "x", "key written 2 times (lines 4, 4); same text")])


class CommandLineTests(unittest.TestCase):
    def test_findings_never_fail_by_default_and_strict_names_categories(self):
        audit = la.Audit([la.Finding("length", "t", "k", "ru", "long")], 1, {"t": 1}, [])
        with TemporaryDirectory() as folder:
            out = Path(folder, "audit.md")
            with mock.patch.object(la, "run_audit", return_value=audit):
                with redirect_stdout(io.StringIO()) as printed:
                    self.assertEqual(la.main(["--markdown", str(out)]), 0)
                    self.assertEqual(la.main(["--strict", "missing,placeholder"]), 0)
                    with redirect_stdout(io.StringIO()), mock.patch("sys.stderr"):
                        self.assertEqual(la.main(["--strict", "length"]), 1)
                        self.assertEqual(la.main(["--strict", "all"]), 1)
            markdown = out.read_text(encoding="utf-8")
        self.assertIn("length", printed.getvalue())
        self.assertIn("| Long button and step labels (layout risk) (`length`) | 1 |", markdown)
        self.assertIn("## Missing translations and keys (0)", markdown)
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                la.main(["--strict", "spelling"])


class RepositoryTests(unittest.TestCase):
    """The application's own tables and workspace screens."""

    @classmethod
    def setUpClass(cls):
        cls.audit = la.run_audit(ROOT)

    def test_every_table_is_read(self):
        self.assertEqual(self.audit.errors, [])
        self.assertEqual(set(self.audit.tables), {spec.name for spec in la.TABLES})
        self.assertTrue(all(count > 0 for count in self.audit.tables.values()),
                        self.audit.tables)

    def test_no_missing_translation_or_undefined_key(self):
        self.assertEqual([(f.table, f.key, f.language, f.detail)
                          for f in self.audit.of("missing")], [])

    def test_no_placeholder_mismatch(self):
        self.assertEqual([(f.table, f.key, f.language, f.detail)
                          for f in self.audit.of("placeholder")], [])

    def test_import_options_and_shell_texts_are_not_hard_coded(self):
        leaks = [f for f in self.audit.of("hardcoded")
                 if f.table in ("workspace_shell.py", "workspace_components.py",
                                "workspace_questionnaires.py")]
        self.assertEqual([(f.location, f.text) for f in leaks], [])


class TranslatedScreensTests(unittest.TestCase):
    """The texts moved out of the code reach the screen in every language."""

    def dropdowns(self, ws):
        import flet as ft

        return {c.label: [o.text for o in c.options] for c in ws.controls()
                if isinstance(c, ft.Dropdown)}

    def test_import_options_in_russian_and_unchanged_in_english(self):
        from workspace_harness import Workspace
        from workspace_text import t

        for language, separator, comma, sheet, encoding in (
                ("ru", "Разделитель CSV", "Запятая ,", "Лист Excel", "Windows, кириллица (CP1251)"),
                ("en", "CSV separator", "Comma ,", "Excel worksheet", "Windows Cyrillic (CP1251)")):
            ws = Workspace(language=language)
            try:
                self.assertTrue(ws.run(ws.app.load_sample("sample_scale.csv")))
                ws.click("nav-data")
                dropdowns = self.dropdowns(ws)
                self.assertIn(comma, dropdowns[separator], language)
                self.assertIn(sheet, dropdowns, language)
                encodings = next(v for k, v in dropdowns.items() if "UTF-8" in v)
                self.assertIn(encoding, encodings, language)
                samples = next(v for k, v in dropdowns.items()
                               if any(t.endswith("sample_scale.csv") for t in v))
                self.assertIn(t(language, "sample.scale") + " · sample_scale.csv", samples)
            finally:
                ws.close()

    def test_table_numbers_follow_the_interface_language(self):
        import workspace_components as wc
        import workspace_tokens as tk

        for language, expected in (("en", "Table 2"), ("lv", "Tabula 2"), ("ru", "Таблица 2")):
            ui = wc.Ui(tk.palette("light"), language)
            table = wc.apa_table(ui, ("A",), (("1",),), number=2, title="Fictional")
            self.assertEqual(table.controls[0].value, expected)

    def test_report_assumptions_are_written_in_the_report_language(self):
        from datetime import datetime

        import research_report as rr
        from interpretation_i18n import ASSUMPTION_TEXT
        from interpretation_wizard import METHOD_PROFILES

        assumptions = METHOD_PROFILES["batch_correlation"].assumptions
        info = rr.ResultInfo(id=1, title="Fictional family", method="batch_correlation",
                             report="Engine report.", assumptions=assumptions,
                             reviewed=frozenset(assumptions[:1]), dataset="fictional.csv",
                             dataset_rows=40, dataset_sha="b" * 64, complete=40,
                             created=datetime(2026, 1, 2, 3, 4))
        for language in ("en", "lv", "ru"):
            report = rr.plan_report(rr.ReportInputs(title="Fictional", results=[info],
                                                    language=language))
            text = "\n".join(i.text or "" for i in report.section("assumptions").items)
            for index, assumption in enumerate(assumptions):
                shown = assumption if language == "en" else ASSUMPTION_TEXT[assumption][language]
                status = rr.text(language, "assumption_reviewed" if index == 0
                                 else "assumption_open")
                self.assertIn(f"{shown} — {status}", text, language)


if __name__ == "__main__":
    unittest.main()
