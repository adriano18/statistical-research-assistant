"""Display item-rest correlations and one-factor loadings for reviewer inspection."""

from io import BytesIO
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reliability_reporting import apa_coefficient


def make_omega_chart(result, ci=None) -> bytes:
    labels = [q.name for q in result.diagnostics]
    corrected = np.array(
        [q.corrected_item_rest_r for q in result.diagnostics]
    )
    loadings = np.array(
        [q.standardized_loading for q in result.diagnostics]
    )
    y = np.arange(len(labels))
    fig, axes = plt.subplots(
        1, 2,
        figsize=(12.2, max(4.9, 2.5 + len(labels) * .44)),
        sharey=True,
    )
    try:
        first, second = axes
        for ax, numbers, caption, color in [
            (first, corrected, "Corrected item–rest Pearson r", "#3889c7"),
            (second, loadings, "One-factor standardized loading", "#b78643"),
        ]:
            ax.barh(y, numbers, color=color, height=.6)
            ax.axvline(0, color="#313c48", linewidth=1)
            ax.set_xlim(-1.05, 1.05)
            ax.set_xlabel(caption)
            ax.grid(axis="x", alpha=.15)
            for index, value in enumerate(numbers):
                ha = "left" if value >= 0 else "right"
                offset = .035 if value >= 0 else -.035
                ax.text(
                    value+offset, index, apa_coefficient(float(value)),
                    va="center", ha=ha, fontsize=8.2,
                )
        first.set_yticks(y, labels=labels)
        first.invert_yaxis()
        fig.text(.055, .98, "Figure 13", weight="bold", va="top", fontsize=11)
        fig.text(
            .055, .94,
            "Item Diagnostics for a One-Factor Scale",
            style="italic", va="top", fontsize=11,
        )
        note = (
            f"Note. Complete-case N = {result.n_complete}; "
            f"standardized McDonald’s ω = {apa_coefficient(result.omega)}. "
            "Item–rest correlations exclude the item itself. Pearson factor "
            "loadings are descriptive; reverse coding must be confirmed "
            "from the scale manual. The figure does not prove scale validity."
        )
        if ci is not None:
            note += (
                f" Bootstrap percentile 95% CI "
                f"[{apa_coefficient(ci.lower)}, {apa_coefficient(ci.upper)}] "
                f"based on {ci.successful}/{ci.requested} valid refits."
            )
        fig.text(
            .055, .02, textwrap.fill(note, 145),
            va="bottom", fontsize=8,
        )
        fig.tight_layout(rect=(.01, .105, .99, .865))
        buffer = BytesIO()
        fig.savefig(buffer, format="png", dpi=125)
        return buffer.getvalue()
    finally:
        plt.close(fig)
