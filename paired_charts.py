"""Visualize individual before/after trajectories without changing data."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_paired_chart(result) -> bytes:
    fig, ax = plt.subplots(figsize=(9.2, 5.6))
    try:
        b, a = result.before_values, result.after_values
        n = len(b)
        show_lines = n <= 80
        if show_lines:
            for v1, v2 in zip(b, a):
                ax.plot([0, 1], [v1, v2], alpha=0.22, linewidth=1)
        else:
            ax.text(
                0.5, 0.02, "Individual lines omitted for readability (N > 80)",
                transform=ax.transAxes, ha="center", fontsize=9,
            )
        rng = np.random.default_rng(2026)
        ax.scatter(rng.normal(0, 0.025, n), b, s=28, alpha=0.7, zorder=3)
        ax.scatter(rng.normal(1, 0.025, n), a, s=28, alpha=0.7, zorder=3)
        ax.set_xlim(-0.32, 1.32)
        ax.set_xticks([0, 1], ["Before", "After"])
        ax.set_ylabel("Score")
        ax.set_title(
            f"{result.before_name}  →  {result.after_name}",
            fontsize=10, pad=11,
        )
        ax.grid(axis="y", alpha=0.18)

        fig.text(0.08, 0.975, "Figure 5", weight="bold", fontsize=11, va="top")
        fig.text(
            0.08, 0.935, "Within-Participant Change Before and After",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Each pair is the same participant. Connecting lines "
            "show individual changes when N ≤ 80. Jitter is visual only; "
            "all statistics use the original measurements. "
            "The plot does not imply causation."
        )
        fig.text(0.08, 0.035, textwrap.fill(note, 110), fontsize=8.3)
        fig.tight_layout(rect=(0.03, 0.105, 0.98, 0.86))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
