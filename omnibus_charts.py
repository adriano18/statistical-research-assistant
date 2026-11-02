"""APA-style descriptive boxplot for three or more independent groups."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_omnibus_chart(result) -> bytes:
    k = len(result.labels)
    fig, ax = plt.subplots(figsize=(max(9, k * 1.3 + 5), 5.8))
    try:
        boxes = ax.boxplot(
            result.samples,
            tick_labels=[
                f"{label}\nn = {len(values)}"
                for label, values in zip(result.labels, result.samples)
            ],
            patch_artist=True,
            showfliers=False,
            widths=0.5,
        )
        for patch in boxes["boxes"]:
            patch.set_alpha(0.3)

        rng = np.random.default_rng(2026)
        for i, values in enumerate(result.samples, 1):
            # Jitter is for display only; calculations use original values.
            x = i + rng.uniform(-0.12, 0.12, len(values))
            ax.scatter(x, values, s=24, alpha=0.6, zorder=3,
                       edgecolors="black", linewidths=0.2)

        ax.set_ylabel(result.outcome_name)
        ax.set_xlabel(result.group_name)
        ax.grid(axis="y", alpha=0.18)
        fig.text(0.07, 0.978, "Figure 7", weight="bold", fontsize=11, va="top")
        fig.text(
            0.07, 0.933, "Outcome Distributions Across Independent Groups",
            style="italic", fontsize=11, va="top",
        )
        note = (
            "Note. Boxes display medians and interquartile ranges. "
            "Points are individual observations with display-only horizontal jitter. "
            "The figure does not identify significant pairs or imply causality."
        )
        fig.text(0.07, 0.035, textwrap.fill(note, width=115), fontsize=8.3)
        fig.tight_layout(rect=(0.03, 0.105, 0.98, 0.86))

        output = BytesIO()
        fig.savefig(output, format="png", dpi=115)
        return output.getvalue()
    finally:
        plt.close(fig)
