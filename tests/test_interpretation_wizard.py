"""Synthetic, offline verification of interpretation and editable APA Word export.

No patient/participant records or external API dependencies.
"""

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import flet as ft
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from interpretation_docx import build_apa_docx, save_apa_docx
from interpretation_ui import InterpretationWizardView
from interpretation_i18n import (
    ASSUMPTION_TEXT, METHOD_TEXT, translate_assumption, translate_method,
)
from interpretation_wizard import (
    METHOD_PROFILES, build_analysis_evidence,
    interpretation_summary, source_references,
)


def fake_correlation(method="pearson"):
    return SimpleNamespace(
        method=method,
        n_total=108, n_complete=94,
        coefficient=0.43651, p_value=0.000034,
        ci_low=0.263, ci_high=0.579,
        warnings=["Missing pairs were excluded."],
    )


def fake_png():
    fig, ax = plt.subplots(figsize=(4, 2.3))
    ax.scatter([1, 2, 3], [2, 1, 4], color="black")
    ax.set_xlabel("Fictional X")
    ax.set_ylabel("Fictional Y")
    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    plt.close(fig)
    return buffer.getvalue()


class InterpretationEvidenceTests(unittest.TestCase):
    def test_every_analysis_has_reviewable_assumptions(self):
        for name, profile in METHOD_PROFILES.items():
            with self.subTest(section=name):
                self.assertGreaterEqual(len(profile.assumptions), 3)
                self.assertTrue(profile.rationale)
                self.assertTrue(profile.limitation)

    def test_every_assumption_has_lv_ru_explanation(self):
        self.assertEqual(set(METHOD_TEXT), set(METHOD_PROFILES))
        original_assumptions = {
            assumption for profile in METHOD_PROFILES.values()
            for assumption in profile.assumptions
        }
        self.assertEqual(set(ASSUMPTION_TEXT), original_assumptions)
        for section, profile in METHOD_PROFILES.items():
            for language in ("ru", "lv"):
                with self.subTest(section=section, language=language):
                    self.assertNotEqual(
                        translate_method(
                            section, "rationale", profile.rationale, language
                        ), profile.rationale,
                    )
                    for original in profile.assumptions:
                        translated = translate_assumption(original, language)
                        self.assertNotEqual(translated, original)
                        self.assertTrue(translated)
        self.assertEqual(
            translate_assumption("unknown key", "ru"), "unknown key",
        )

    def test_correlation_numbers_come_from_result_not_report_text(self):
        result = fake_correlation()
        evidence = build_analysis_evidence(
            "correlation", "Bivariate correlation",
            "Do not parse: r = .99, N = 999.", None, result
        )
        self.assertEqual(evidence.rows[0].estimate, "94")
        self.assertEqual(evidence.rows[1].estimate, "108")
        self.assertEqual(evidence.rows[2].parameter, "Pearson r")
        self.assertEqual(evidence.rows[2].estimate, ".437")
        self.assertEqual(evidence.rows[2].ci, "[.263, .579]")
        self.assertEqual(evidence.rows[2].p, "< .001")
        self.assertEqual(evidence.source_report, "Do not parse: r = .99, N = 999.")
        text = interpretation_summary(evidence, reviewed=set())
        self.assertIn("3 check(s) remain unreviewed", text)
        self.assertNotIn("r = .99", text)
        self.assertIn("Missing pairs were excluded", text)
        self.assertIn("not causal", evidence.limitation.lower())

    def test_mean_difference_ci_must_not_be_labeled_as_cohen_d_ci(self):
        result = SimpleNamespace(
            method="welch", n_total=112, n_a=50, n_b=60,
            statistic=2.9, p_value=.0045,
            effect_name="Hedges g", effect_size=.533,
            mean_difference=1.26, ci_low=.36, ci_high=2.15,
            warnings=[],
        )
        evidence = build_analysis_evidence(
            "groups", "Independent-group comparison", "Source calculation",
            None, result,
        )
        effect = next(row for row in evidence.rows if row.parameter == "Hedges g")
        difference = next(row for row in evidence.rows
                          if row.parameter == "Mean difference")
        self.assertEqual(evidence.n_complete, 110)
        self.assertEqual(
            next(r.estimate for r in evidence.rows
                 if r.parameter == "Complete observations (N)"), "110",
        )
        self.assertEqual(effect.estimate, ".533")
        self.assertEqual(effect.ci, "Not calculated")
        self.assertEqual(difference.ci, "[.360, 2.150]")
        self.assertEqual(evidence.method, "Welch independent-samples t test")

    def test_numpy_scalar_estimates_and_counts_are_preserved(self):
        result = fake_correlation()
        result.n_complete = np.int64(94)
        result.n_total = np.int32(108)
        result.coefficient = np.float32(.432)
        result.p_value = np.float32(.008)
        result.ci_low = np.float32(.2)
        result.ci_high = np.float32(.6)
        evidence = build_analysis_evidence(
            "correlation", "Synthetic numeric scalars", "Raw result",
            None, result,
        )
        self.assertEqual(evidence.n_complete, 94)
        self.assertEqual(evidence.n_total, 108)
        self.assertEqual(evidence.rows[2].estimate, ".432")
        self.assertEqual(evidence.rows[2].ci, "[.200, .600]")

    def test_missing_spearman_ci_explicit_and_no_false_claim(self):
        result = fake_correlation("spearman")
        result.ci_low = None
        result.ci_high = None
        snapshot = build_analysis_evidence(
            "correlation", "Correlation", "Spearman test output", None, result,
        )
        row = snapshot.rows[-1]
        self.assertEqual(row.parameter, "Spearman ρ")
        self.assertEqual(row.ci, "Not calculated")
        self.assertTrue(any("confidence interval" in w for w in snapshot.warnings))
        self.assertIn("No confidence interval", interpretation_summary(snapshot, set()))

    def test_regression_uses_true_per_predictor_ci_values(self):
        result = SimpleNamespace(
            n_total=100, n_complete=88,
            r_squared=.315, adjusted_r_squared=.298,
            f_value=8.4, f_p=.003,
            coefficients=[
                SimpleNamespace(name="sleep", b=.512, p=.018,
                                ci_low=.092, ci_high=.932),
                SimpleNamespace(name="group", b=-.234, p=.4,
                                ci_low=-.8, ci_high=.5),
            ],
            warnings=["Interpret the diagnostics."],
        )
        evidence = build_analysis_evidence(
            "regression", "Linear regression",
            "Verbatim OLS report", fake_png(), result,
        )
        coef = next(row for row in evidence.rows if row.parameter == "B: sleep")
        self.assertEqual(coef.estimate, ".512")
        self.assertEqual(coef.ci, "[.092, .932]")
        self.assertEqual(coef.p, "= .018")
        self.assertEqual(len([row for row in evidence.rows if "B:" in row.parameter]), 2)

    def test_empty_structured_evidence_is_explicit(self):
        evidence = build_analysis_evidence(
            "descriptive", "Descriptive study", "M = 2.14; N = 20", None,
        )
        self.assertFalse(evidence.has_structured_values)
        self.assertEqual(evidence.rows[0].estimate, "Not captured")
        self.assertIn("Not captured", interpretation_summary(evidence, set()))

    def test_unhandled_section_rejected(self):
        with self.assertRaisesRegex(ValueError, "No interpretation profile"):
            build_analysis_evidence("nonexistent", "Test", "Report", None)
        with self.assertRaisesRegex(ValueError, "successful analysis"):
            build_analysis_evidence("correlation", "Test", "", None)

    def test_bibliography_is_scoped_to_the_selected_analysis(self):
        for section in ("correlation", "reliability", "regression", "paired"):
            with self.subTest(section=section):
                sources = source_references(section)
                self.assertGreaterEqual(len(sources), 2)
                self.assertTrue(all("https://" in reference for reference in sources))
                self.assertEqual(len(sources), len(set(sources)))
                self.assertTrue(any("American Psychological Association" in s
                                    for s in sources))


class APAWordExportTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_analysis_evidence(
            "correlation", "Fictional correlation",
            "Original calculator report: Pearson r = .437; N = 94.",
            fake_png(), fake_correlation(),
        )

    def test_structured_editable_docx_has_tables_bibliography_and_figure(self):
        doc = build_apa_docx(
            self.evidence,
            reviewed={self.evidence.assumptions[0]},
            researcher_notes="Interpret cautiously; synthetic example.",
            study_title="Fictional Stress and Sleep Study",
            figure_title="Association of Stress and Sleep",
        )
        all_text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("Fictional Stress and Sleep Study", all_text)
        self.assertIn("Method and research design", all_text)
        self.assertIn("Not reviewed", all_text)
        self.assertIn("Reviewed by researcher", all_text)
        self.assertIn("Table 1", all_text)
        self.assertIn("Figure 1", all_text)
        self.assertIn("Association of Stress and Sleep", all_text)
        self.assertIn("Appendix: Original calculation output", all_text)
        self.assertIn("Original calculator report", all_text)
        self.assertIn("References", all_text)
        self.assertLess(
            all_text.index("References"),
            all_text.index("Appendix: Original calculation output")
        )
        self.assertIn("Cumming", all_text)
        self.assertNotIn("Note. Note.", all_text)
        from docx.shared import RGBColor
        self.assertEqual(
            doc.styles["Title"].font.color.rgb, RGBColor(0, 0, 0)
        )
        self.assertGreaterEqual(len(doc.tables), 1)
        cells = doc.tables[0].rows[0].cells
        self.assertEqual([cell.text for cell in cells],
                         ["Statistic", "Estimate", "95% CI", "p"])
        self.assertEqual(doc.tables[0].rows[3].cells[1].text, ".437")
        self.assertEqual(doc.tables[0].rows[3].cells[2].text, "[.263, .579]")
        self.assertIn("w:insideV", doc.tables[0]._tbl.xml)
        self.assertIn('w:val="nil"', doc.tables[0]._tbl.xml)
        self.assertEqual(len(doc.inline_shapes), 1)
        self.assertEqual(doc.core_properties.author, "")
        self.assertTrue(doc.paragraphs[0].style.name == "Title")

    def test_word_is_saved_locally_and_reopened_as_editable(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_study.docx"
            saved = save_apa_docx(
                path, self.evidence,
                researcher_notes="No causal inference is warranted.",
            )
            self.assertEqual(saved, path)
            self.assertTrue(path.is_file())
            from docx import Document
            again = Document(path)
            self.assertGreater(len(again.tables[0].rows), 2)
            self.assertEqual(len(again.inline_shapes), 1)
            all_text = "\n".join(p.text for p in again.paragraphs)
            self.assertIn("No causal inference", all_text)
            self.assertIn("Original calculator report", all_text)
            # Change and resave a table cell: it is editable Word XML.
            again.tables[0].rows[1].cells[0].text = "Edited in Word"
            again.save(path)
            self.assertEqual(Document(path).tables[0].rows[1].cells[0].text,
                             "Edited in Word")

    def test_no_figure_inserts_no_dummy_image(self):
        evidence = build_analysis_evidence(
            "reliability", "Alpha", "Cronbach alpha = .81", None,
            SimpleNamespace(
                alpha=.81, ci_low=.76, ci_high=.87,
                n_total=48, n_complete=46,
                warnings=[],
            ),
        )
        doc = build_apa_docx(evidence)
        self.assertEqual(len(doc.inline_shapes), 0)
        self.assertEqual(doc.tables[0].rows[3].cells[2].text, "[.760, .870]")

    def test_export_validates_input_and_never_silently_overwrites_csv(self):
        with TemporaryDirectory() as folder:
            outside = Path(folder) / "participants.csv"
            outside.write_text("sensitive,keep\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, r"\.docx"):
                save_apa_docx(outside, self.evidence)
            self.assertEqual(outside.read_text(), "sensitive,keep\n")
            with self.assertRaisesRegex(ValueError, "too long"):
                build_apa_docx(self.evidence, researcher_notes="x" * 10001)

    def test_apa_table_caption_is_editable(self):
        doc = build_apa_docx(self.evidence)
        labels = [p for p in doc.paragraphs if p.text.startswith("Table 1")
                  or p.text.startswith("Verified Statistics")]
        self.assertEqual(len(labels), 2)
        self.assertTrue(labels[0].runs[0].bold)
        self.assertTrue(labels[1].runs[0].italic)


class DummyPage:
    def update(self):
        pass


class WizardViewTests(unittest.TestCase):
    def test_four_steps_and_reset_on_new_result(self):
        saved = []

        async def export(*args):
            saved.append(args)

        wizard = InterpretationWizardView(
            DummyPage(), language_getter=lambda: "ru", on_export=export,
        )
        self.assertIn("Мастер интерпретации", wizard.root.title.value)
        self.assertIn("Сначала выполните анализ",
                      wizard.step_content.controls[0].value)
        evidence = build_analysis_evidence(
            "correlation", "Test", "Numerical report", None, fake_correlation(),
        )
        wizard.set_evidence(evidence)
        self.assertEqual(wizard.step, 0)
        wizard.next()
        self.assertEqual(wizard.step, 1)
        self.assertEqual(len(wizard.step_content.controls), 5)
        self.assertIn("Подтвердить", wizard.step_content.controls[1].label)
        wizard._mark_reviewed(evidence.assumptions[0], True)
        wizard.next()
        self.assertEqual(wizard.step, 2)
        wizard.next()
        self.assertEqual(wizard.step, 3)
        self.assertTrue(wizard.reviewed)
        wizard.set_evidence(None)
        self.assertEqual(wizard.step, 0)
        self.assertEqual(wizard.reviewed, set())
        self.assertTrue(wizard.next_button.disabled)


if __name__ == "__main__":
    unittest.main()
