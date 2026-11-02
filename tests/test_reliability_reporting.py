"""Offline checks for APA-style reliability reporting and PNG figures."""

from types import SimpleNamespace
import unittest

from reliability_reporting import (
    ALPHA_GUIDE, apa_coefficient, apa_reliability_report, interpret_alpha
)
from reliability_charts import make_reliability_chart


class ReliabilityPresentationTests(unittest.TestCase):
    def setUp(self):
        self.result = SimpleNamespace(
            alpha=0.939001697,
            ci_low=0.893,
            ci_high=0.968,
            n_total=32,
            n_complete=30,
            items=["stress_q1", "stress_q2", "stress_q3", "stress_q4"],
            alpha_if_deleted={
                "stress_q1": 0.922,
                "stress_q2": 0.904,
                "stress_q3": 0.918,
                "stress_q4": 0.937,
            },
        )

    def test_apa_decimal_format(self):
        self.assertEqual(apa_coefficient(0.939), ".94")
        self.assertEqual(apa_coefficient(-0.27), "-.27")
        self.assertEqual(apa_coefficient(0), ".00")
        self.assertEqual(apa_coefficient(1), "1.00")

    def test_heuristic_interpretation_is_not_validity(self):
        self.assertEqual(interpret_alpha(0.55), "Low")
        self.assertEqual(interpret_alpha(0.75), "Often acceptable")
        self.assertEqual(interpret_alpha(0.85), "Good")
        self.assertEqual(interpret_alpha(0.94), "Very high / excellent")
        self.assertIn("redundancy", interpret_alpha(0.97))
        self.assertIn("not pass/fail validity", ALPHA_GUIDE)

    def test_text_report(self):
        text = apa_reliability_report(self.result)
        self.assertIn("Cronbach’s α = .94", text)
        self.assertIn("95% CI [.89, .97]", text)
        self.assertIn("N = 30", text)
        self.assertIn("stress_q2: .90", text)

    def test_reliability_figure_is_png(self):
        png = make_reliability_chart(self.result)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))
        self.assertGreater(len(png), 2000)

    def test_negative_alpha_can_be_displayed(self):
        result = SimpleNamespace(
            alpha=-0.18, ci_low=-0.34, ci_high=0.05,
            alpha_if_deleted={"stress_q1": -0.07},
        )
        png = make_reliability_chart(result)
        self.assertTrue(png.startswith(bytes.fromhex("89504e470d0a1a0a")))


if __name__ == "__main__":
    unittest.main()
