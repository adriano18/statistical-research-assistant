"""Display repeated observations and their descriptive occasion means."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def make_repeated_chart(result) -> bytes:
    values = result.values
    n, k = values.shape
    fig, (ax, change_ax) = plt.subplots(
        1, 2, figsize=(12.7, 5.6),
        gridspec_kw={"width_ratios": [1.6, 1]},
    )
    try:
        x = np.arange(k)
        if n <= 60:
            for row in values:
                ax.plot(x, row, color="#8e9aa9", linewidth=0.75, alpha=0.28)
        else:
            ax.text(
                0.02, 0.03, "Individual lines omitted above N = 60",
                transform=ax.transAxes, fontsize=9,
            )
        ax.plot(
            x, values.mean(axis=0), marker="o", color="#2563eb",
            linewidth=2.5, label="Occasion mean",
        )
        ax.set_xticks(x, labels=result.columns, rotation=20)
        ax.set_ylabel("Observed score")
        ax.set_title("Individual trajectories and occasion means")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.18)

        differences = values[:, -1] - values[:, 0]
        change_ax.hist(
            differences, bins=min(12, max(5, int(np.sqrt(n)))),
            color="#7ca8ce", edgecolor="white",
        )
        change_ax.axvline(0, linestyle="--", color="#4b5563")
        change_ax.set_xlabel("Last − first occasion score")
        change_ax.set_ylabel("Number of participants")
        change_ax.set_title("Descriptive first–last changes")
        fig.text(
            0.06, 0.985, "Figure 10", weight="bold", fontsize=11, va="top"
        )
        fig.text(
            0.06, 0.947, "Within-Participant Changes Across Occasions",
            style="italic", fontsize=11, va="top"
        )
        note = (
            "Note. Lines connect scores from the same person. Means are "
            "descriptive, not corrected within-person confidence intervals. "
            "The first–last distribution is not a model assumption test. "
            "Neither this plot nor a significant test demonstrates causality."
        )
        fig.text(0.06, 0.025, textwrap.fill(note, 137),
                 fontsize=8.2, va="bottom")
        fig.tight_layout(rect=(0.02, 0.11, 0.98, 0.86))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=115)
        return buffer.getvalue()
    finally:
        plt.close(fig)
