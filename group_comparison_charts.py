"""Side-by-side boxplots with all observations for independent groups."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_group_comparison_chart(result) -> bytes:
    """Draw descriptive distributions; do not visually assert significance."""
    fig, ax = plt.subplots(figsize=(9.4, 5.7))
    try:
        values = [result.values_a, result.values_b]
        labels = [
            f"{result.group_a} (n = {result.n_a})",
            f"{result.group_b} (n = {result.n_b})",
        ]
        box = ax.boxplot(
            values,
            tick_labels=labels,
            showfliers=False,
            patch_artist=True,
            widths=0.42,
        )
        for patch in box["boxes"]:
            patch.set_alpha(0.28)

        rng = np.random.default_rng(2026)
        for index, group in enumerate(values, start=1):
            xs = index + rng.uniform(-0.12, 0.12, len(group))
            ax.scatter(
                xs, group, s=32, alpha=0.7,
                edgecolors="black", linewidths=0.25,
                zorder=3,
            )

        ax.set_ylabel(result.outcome_name)
        ax.set_xlabel(result.group_name)
        ax.grid(axis="y", alpha=0.18)
        fig.text(0.08, 0.98, "Figure 4", weight="bold", fontsize=11, va="top")
        fig.text(
            0.08, 0.937,
            f"Distribution of {result.outcome_name} Across Independent Groups",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Boxes show median and interquartile range; whiskers use the "
            "1.5 × IQR convention. Individual points are horizontally jittered "
            "only for visibility. All calculations use original observations. "
            "A plot alone does not establish statistical significance or causation."
        )
        fig.text(
            0.08, 0.04, textwrap.fill(note, width=105),
            fontsize=8.5, va="bottom",
        )
        fig.tight_layout(rect=(0.03, 0.125, 0.98, 0.86))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
