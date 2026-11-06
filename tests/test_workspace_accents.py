"""Stage 34.5 (issue #32): accent colour presets, blue by default, each with
accessible contrast in both themes, chosen in Settings and kept."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import workspace_tokens as tk  # noqa: E402
from workspace_harness import Workspace  # noqa: E402


class AccentTests(unittest.TestCase):
    def test_every_accent_meets_wcag_aa_in_both_themes(self):
        for accent in tk.ACCENTS:
            for mode in ("light", "dark"):
                palette = tk.palette(mode, accent)
                for fg, bg in tk.TEXT_PAIRS:
                    ratio = tk.contrast_ratio(getattr(palette, fg), getattr(palette, bg))
                    with self.subTest(accent=accent, mode=mode, pair=(fg, bg)):
                        self.assertGreaterEqual(ratio, 4.5, f"{ratio:.2f}")
                for fg, bg in tk.UI_PAIRS:
                    ratio = tk.contrast_ratio(getattr(palette, fg), getattr(palette, bg))
                    with self.subTest(accent=accent, mode=mode, pair=(fg, bg)):
                        self.assertGreaterEqual(ratio, 3.0, f"{ratio:.2f}")

    def test_blue_is_the_default_and_unchanged(self):
        self.assertEqual(tk.DEFAULT_ACCENT, "blue")
        self.assertEqual(tk.palette("light"), tk.LIGHT)
        self.assertEqual(tk.palette("dark"), tk.DARK)
        self.assertEqual(tk.palette("light", "unknown"), tk.LIGHT)

    def test_an_accent_chosen_in_settings_applies_and_is_kept(self):
        ws = Workspace()
        self.addCleanup(ws.close)
        ws.app.navigate("settings")
        ws.segment("settings-accent", "teal")
        self.assertEqual(ws.app.session.accent, "teal")
        self.assertEqual(ws.app.ui.p.accent, tk.ACCENTS["teal"]["light"][0])
        self.assertEqual(ws.page.theme.color_scheme.primary, tk.ACCENTS["teal"]["light"][0])
        again = Workspace(root=ws.root)
        self.addCleanup(again.close)
        self.assertEqual(again.app.session.accent, "teal", "kept for the next start")
        fresh = Workspace()
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.app.session.accent, "blue", "another computer starts blue")


if __name__ == "__main__":
    unittest.main()
