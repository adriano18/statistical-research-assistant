"""Unit tests for identifier hints used by the statistical assistant."""

import unittest

from variable_rules import looks_like_identifier


class VariableRulesTests(unittest.TestCase):
    def test_common_identifiers(self):
        for name in ("participant_id", "subject-id", "ID", "order_id"):
            with self.subTest(name=name):
                self.assertTrue(looks_like_identifier(name))

    def test_research_variables_are_not_identifiers(self):
        for name in ("age", "stress_q1", "wellbeing", "identity_score"):
            with self.subTest(name=name):
                self.assertFalse(looks_like_identifier(name))


if __name__ == "__main__":
    unittest.main()
